#!/usr/bin/env python3
"""AVB-04: attended runtime release. Default is a metadata-only plan, never apply.

Run from a stable tools checkout, NOT the runtime being switched. See
 docs/hass/RUNTIME-RELEASE.md. No unit installation, secret access, or publication.
"""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

SHA = re.compile(r"[0-9a-f]{40}\Z")
UNITS = ("hass-receiver.service", "hass-worker.service", "hass-health.timer")
PENDING_WORK_ZERO = {"outbox_unsent 0", "relay_unacked 0", "card_receipt_pending 0", "inbound_pending 0"}
STAGING_BUDGET_SECONDS = 5400  # >= 1.5x the measured on-host acceptance + run_parallel time (docs)
INVOCATION = re.compile(r"[0-9a-f]{32}\Z")  # systemd InvocationID
BACKUP = "hass-backup.service"
TICK_NS = 1_000_000_000 // os.sysconf("SC_CLK_TCK")  # /proc/<pid>/stat starttime unit


class Refused(Exception):
    pass


def boot_id():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def invocation_ok(value):
    return bool(INVOCATION.fullmatch(value)) and value != "0" * 32


def monotonic_us():
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC) // 1000


def process_start_ticks(pid):
    """Kernel start of the process (CLOCK_BOOTTIME, truncated to clock ticks)."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except (OSError, IndexError):
        raise Refused("unit-launch") from None
    if len(fields) < 20 or not fields[19].isdigit():
        raise Refused("unit-launch")
    return int(fields[19])


def private_read(path):
    """No symlinks; reject unsafe files without reading them. Never print contents."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        st = os.fstat(stream.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600 or st.st_size > 65536:
            raise Refused("private-file")
        return stream.read(65537)


def private_write(path, data):
    """Atomic same-directory replace, including durable directory entry."""
    fd, tmp = tempfile.mkstemp(prefix=".release-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def host_pin(data, expected, target):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise Refused("duplicate-host-key")
            out[key] = value
        return out
    def invalid_constant(value):
        raise Refused("host-json")
    cfg = json.loads(data, object_pairs_hook=pairs, parse_constant=invalid_constant)
    if not isinstance(cfg, dict) or cfg.get("runtimeCommit") != expected:
        raise Refused("host-pin")
    cfg["runtimeCommit"] = target
    return (json.dumps(cfg, indent=2, ensure_ascii=False) + "\n").encode()


class Release:
    def __init__(self, args):
        self.a = args
        self.start = time.monotonic()
        self.deadline = self.start + 900
        self.rollback_mode = False
        self.mutating = False  # services may have been stopped
        self.write_attempted = False  # checkout or host replacement may have started
        self.run_dir = None
        self.old_host = None
        self.new_host = None
        self.stage = None
        self.stage_tmp = None  # TMPDIR owned by this process for the staging children
        self.pending = None
        self.git_dir = None
        # Ordering evidence observed by this run (receipt "witness"): the backup this run
        # started, and the host pin and unit launches on ONE monotonic clock and boot.
        self.witness = {}

    def command(self, label, argv, cwd=None, timeout=60, codes=(0,), *, strip=True):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Refused("time-budget")
        # Child output is never forwarded: host checks, inbox and tests may contain
        # private fields on error. Public receipts contain fixed labels only.
        env = dict(os.environ, HASS_PYTHON=str(self.a.python))
        if self.stage_tmp is not None:
            env["TMPDIR"] = str(self.stage_tmp)
        child = subprocess.Popen([str(x) for x in argv], cwd=cwd, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 start_new_session=True, env=env)
        try:
            stdout, _ = child.communicate(timeout=min(timeout, remaining))
        except BaseException as exc:
            # Kill the whole test/service-client process group before rollback.
            # Killing systemctl does NOT cancel its systemd job; rollback re-stops
            # and verifies the units before touching either checkout or pin.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.communicate()
            if isinstance(exc, subprocess.TimeoutExpired):
                raise Refused(label + "-timeout") from None
            raise
        if child.returncode not in codes:
            raise Refused(label)
        return stdout.strip() if strip else stdout

    def git(self, *args):
        return self.command("git", ["git", "-C", self.a.runtime, *args])

    def clean_head(self, expected):
        if self.git("rev-parse", "HEAD") != expected or self.git("status", "--porcelain", "--untracked-files=all"):
            raise Refused("runtime-identity")
        if Path(self.git("rev-parse", "--show-toplevel")).resolve() != self.a.runtime:
            raise Refused("runtime-root")
        # Refuse a branch checkout: restoring only its SHA would lose its branch identity.
        if self.command("detached", ["git", "-C", self.a.runtime, "symbolic-ref", "-q", "HEAD"], codes=(0, 1)):
            raise Refused("runtime-not-detached")

    def units(self, active):
        for unit in UNITS:
            value = self.command("unit-state", ["systemctl", "--user", "is-active", unit], codes=(0,) if active else (3,))
            if value != ("active" if active else "inactive"):
                raise Refused("unit-state")
        if active:
            for unit in UNITS[:2]:
                if self.command("restart-count", ["systemctl", "--user", "show", "-p", "NRestarts", "--value", unit]) != "0":
                    raise Refused("restart-count")

    def stop(self):
        self.command("stop", ["systemctl", "--user", "stop", *reversed(UNITS)])
        self.require_stopped()

    def require_stopped(self):
        self.units(False)
        # A timer's triggered service may still be running after the timer stops.
        state = self.command("health-idle", ["systemctl", "--user", "is-active", "hass-health.service"], codes=(3,))
        if state != "inactive":
            raise Refused("health-not-idle")

    def start_units(self):
        self.command("start", ["systemctl", "--user", "start", *UNITS])
        time.sleep(30)
        self.units(True)

    def unit_show(self, label, unit, keys):
        """One `systemctl show` snapshot with exactly these properties."""
        out = self.command(label, ["systemctl", "--user", "show", *(f"--property={key}" for key in keys), unit])
        fields: dict[str, str] = {}
        for line in str(out).splitlines():
            key, _, value = line.partition("=")
            fields[key] = value
        if set(fields) != set(keys):
            raise Refused(label)
        return fields

    def unit_launches(self):
        """Each service's current main process was forked after the pin, same boot.

        The fork time is the kernel's own start time of the stable current main PID
        (CLOCK_BOOTTIME, rounded DOWN to a tick, so it is a lower bound), compared with
        CLOCK_BOOTTIME read after the pin replace returned. systemd's ExecMain stamp is
        not used: it can be later than the fork. No wall-clock value is compared.
        """
        keys = ("InvocationID", "MainPID", "ExecMainPID", "NRestarts", "ActiveState")
        launched = {}
        for unit in UNITS[:2]:
            if boot_id() != self.witness["boot_id"]:
                raise Refused("unit-launch-boot")
            first = self.unit_show("unit-launch", unit, keys)
            pid = first["MainPID"]
            if (not invocation_ok(first["InvocationID"]) or not pid.isdigit() or int(pid) <= 0
                    or first["ExecMainPID"] != pid or first["NRestarts"] != "0" or first["ActiveState"] != "active"):
                raise Refused("unit-launch")
            ticks = process_start_ticks(int(pid))
            # Same invocation, same main PID before and after the kernel read: the
            # ticks belong to this invocation's process, not a reused PID.
            if self.unit_show("unit-launch", unit, keys) != first or boot_id() != self.witness["boot_id"]:
                raise Refused("unit-launch-unstable")
            launch_min_ns = ticks * TICK_NS
            if launch_min_ns <= self.witness["pinned_boottime_ns"]:
                raise Refused("unit-launch-before-pin")
            launched[unit] = {"invocation": first["InvocationID"], "launch_boottime_min_ns": launch_min_ns}
        self.witness["units"] = launched

    def backup(self):
        """Run the state backup and bind THIS run's completed invocation (before any stop).

        Positive evidence: the unit was idle when this run asked; afterwards it reports a
        new successful invocation whose main process ran inside [asked, returned] on the
        monotonic clock; and the journal holds exactly one start job of the unit since
        `asked`, done, for that same invocation. Anything else is ambiguous: refuse.
        """
        self.witness["boot_id"] = boot_id()
        asked = monotonic_us()
        idle = self.unit_show("backup-before", BACKUP, ("ActiveState", "InvocationID"))
        if idle["ActiveState"] not in ("inactive", "failed"):
            raise Refused("backup-busy")
        self.command("backup", ["systemctl", "--user", "start", BACKUP], timeout=120)
        returned = monotonic_us()
        done = self.unit_show("backup-result", BACKUP, ("Result", "ActiveState", "ExecMainStatus", "InvocationID",
                              "ExecMainStartTimestampMonotonic", "ExecMainExitTimestampMonotonic"))
        if done["Result"] != "success" or done["ActiveState"] != "inactive" or done["ExecMainStatus"] != "0":
            raise Refused("backup-result")
        invocation = done["InvocationID"]
        if not invocation_ok(invocation) or invocation == idle["InvocationID"]:
            raise Refused("backup-invocation")
        began, ended = done["ExecMainStartTimestampMonotonic"], done["ExecMainExitTimestampMonotonic"]
        if not (began.isdigit() and ended.isdigit() and asked < int(began) <= int(ended) <= returned):
            raise Refused("backup-window")
        job = self.backup_job(asked)
        for _ in range(10):  # the journal may trail the job by a moment
            if job is not None:
                break
            time.sleep(0.2)
            job = self.backup_job(asked)
        if job is None or job[0] != invocation:
            raise Refused("backup-ambiguous")
        self.witness["backup_invocation"] = invocation
        self.witness["backup_job"] = job[1]

    def backup_job(self, since_us):
        """(invocation, job id) of the ONE completed start job since since_us, else None/refuse."""
        out = self.command("backup-journal", ["journalctl", "--user", "-b", "0", "-u", BACKUP, "-n", "200",
                                              "-o", "json", "--output-fields=JOB_ID,JOB_TYPE,JOB_RESULT,"
                                              "USER_UNIT,USER_INVOCATION_ID,_SYSTEMD_INVOCATION_ID,_BOOT_ID"])
        starts, dones, seen = [], [], set()
        for line in str(out).splitlines():
            try:
                entry = json.loads(line)
                stamp = int(entry["__MONOTONIC_TIMESTAMP"])
            except (ValueError, KeyError, TypeError):
                raise Refused("backup-journal") from None
            if entry.get("_BOOT_ID") != self.witness["boot_id"].replace("-", "") or stamp <= since_us:
                continue
            for key in ("USER_INVOCATION_ID", "_SYSTEMD_INVOCATION_ID"):  # any other run = ambiguous
                if entry.get(key) is not None:
                    seen.add(entry[key])
            if entry.get("USER_UNIT") == BACKUP and entry.get("JOB_TYPE") == "start":
                (dones if "JOB_RESULT" in entry else starts).append(entry)
        if not dones:
            return None
        if len(starts) != 1 or len(dones) != 1 or len(seen) != 1 or dones[0].get("JOB_RESULT") != "done":
            raise Refused("backup-ambiguous")
        if starts[0].get("JOB_ID") != dones[0].get("JOB_ID") or not str(dones[0].get("JOB_ID", "")).isdigit():
            raise Refused("backup-ambiguous")
        return dones[0]["USER_INVOCATION_ID"], int(dones[0]["JOB_ID"])

    def selftest(self):
        assert self.run_dir is not None
        output = self.command("selftest", ["bash", self.a.runtime / "scripts/hass/live_selftest.sh",
                               "--state-root", self.a.state_root, "--growth-file", self.run_dir / "growth.tsv"], timeout=180)
        if not output or not re.fullmatch(r"HASS-SELFTEST \S+ pass=[0-9]+ warn=[0-9]+ fail=0 skip=[0-9]+", output.splitlines()[-1]):
            raise Refused("selftest-summary")

    def host_check(self):
        self.command("host-check", [self.a.python, "-B", self.a.runtime / "hass/host.py", "check", "--host", self.a.host])

    def inbox_empty(self):
        report = json.loads(self.command("inbox", [self.a.python, "-B", self.a.runtime / "hass/inbox.py",
                                                  "status", "--state", self.a.state_root / "state"]))
        if not isinstance(report, dict) or type(report.get("pending")) is not int or report["pending"] != 0:
            raise Refused("inbox-not-empty")

    def state_path(self):
        assert self.old_host is not None
        configured = json.loads(self.old_host).get("state")
        if not isinstance(configured, str) or not Path(configured).is_absolute():
            raise Refused("pending-work-state")
        state = self.a.state_root / "state"
        if state != Path(configured).resolve() or state != state.resolve():
            raise Refused("pending-work-state")
        return state

    def pending_work_clear(self):
        # Receiver and worker both use cfg['state'] and a relay beside their host config.
        state = self.state_path()
        stores = {"inbox": state / "inbox.sqlite3", "conversation": state / "conversation.sqlite3",
                  "relay": self.a.host.parent / "relay.sqlite3"}
        identities = set()
        for path in stores.values():
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or path != path.resolve():
                    raise Refused("pending-work-store")
            except (OSError, RuntimeError):
                raise Refused("pending-work-store") from None
            identities.add((info.st_dev, info.st_ino))
        if len(identities) != len(stores):
            raise Refused("pending-work-store-alias")
        # Use the reviewed stable tools checkout, including for an inverse move
        # whose destination predates the complete checker. No partial/legacy fallback.
        checker = Path(__file__).resolve().parents[1] / "scripts/hass/install_pending_work.py"
        if not checker.is_file() or checker.resolve() != checker:
            raise Refused("pending-work-checker")
        argv = [self.a.python, "-B", checker, "--complete"]
        for role, path in stores.items():
            argv.extend([f"--{role}", path])
        lines = self.command("pending-work", argv, strip=False).splitlines()
        if len(lines) != 5 or lines[-1] != "PASS install_pending_work" or set(lines[:-1]) != PENDING_WORK_ZERO:
            raise Refused("pending-work-incomplete")

    def record(self, phase):
        if self.run_dir:
            private_write(self.run_dir / "receipt.json", (json.dumps({
                "phase": phase, "old": self.a.expected_old, "target": self.a.target,
                "runtime": str(self.a.runtime), "host": str(self.a.host),
                "elapsed_seconds": round(time.monotonic() - self.start, 3),
                "witness": self.witness,
            }, sort_keys=True) + "\n").encode())
        if self.pending is not None:
            if phase == "switching":
                private_write(self.pending, (str(self.run_dir) + "\n").encode())
            elif phase in ("released", "rolled-back"):
                self.pending.unlink()
        print("RELEASE " + phase, flush=True)

    def preflight(self):
        self.clean_head(self.a.expected_old)
        self.git("cat-file", "-e", self.a.target + "^{commit}")
        self.git("merge-base", "--is-ancestor", self.a.target, "origin/main")
        if self.a.target == self.a.expected_old:
            raise Refused("no-move")
        if Path(__file__).resolve().is_relative_to(self.a.runtime):
            raise Refused("use-stable-tools-checkout")

    def prepare(self):
        assert self.run_dir is not None
        self.old_host = private_read(self.a.host)
        self.new_host = host_pin(self.old_host, self.a.expected_old, self.a.target)
        self.units(True)
        if self.command("backup-timer", ["systemctl", "--user", "is-active", "hass-backup.timer"]) != "active":
            raise Refused("backup-timer")
        self.host_check()
        self.state_path()  # Bind the baseline and the later stopped read to the same editor state.
        self.selftest()  # No allow-list for existing failures (AVB-03 relay-stuck is a real gate).
        self.inbox_empty()
        self.stage = self.run_dir / "stage"
        self.command("stage", ["git", "-C", self.a.runtime, "worktree", "add", "--detach", self.stage, self.a.target])
        # Staging has its own shared deadline; it cannot consume or enlarge the
        # normal work/switch budget. Keep command()'s process-group timeout guard.
        staging_start = time.monotonic()
        work_deadline = self.deadline
        self.deadline = staging_start + STAGING_BUDGET_SECONDS
        # The staging children write their scratch (run_parallel's shard trees, test
        # fixtures) under a TMPDIR this process owns. A timeout SIGKILLs their process
        # group, so their own cleanup never runs; this process removes the whole tree.
        # Short name: the shard trees nest below it (see run_parallel.py).
        self.stage_tmp = Path(tempfile.mkdtemp(prefix="hs"))
        try:
            self.command("acceptance", [self.a.python, "-B", "hass/acceptance.py"],
                         cwd=self.stage, timeout=STAGING_BUDGET_SECONDS)
            self.command("tests", [self.a.python, "-B", "hass/tests/run_parallel.py"],
                         cwd=self.stage, timeout=STAGING_BUDGET_SECONDS)
        finally:
            self.deadline = work_deadline + (time.monotonic() - staging_start)
            stage_tmp, self.stage_tmp = self.stage_tmp, None
            shutil.rmtree(stage_tmp, ignore_errors=True)
        self.backup()
        private_write(self.run_dir / "host.before", self.old_host)
        self.record("prepared")

    def apply(self):
        self.prepare()
        if self.deadline - time.monotonic() < 180:
            raise Refused("insufficient-switch-budget")
        # Establish the recovery marker BEFORE the first stop (including partial stops).
        self.record("switching")
        self.mutating = True
        self.stop()
        self.clean_head(self.a.expected_old)
        if private_read(self.a.host) != self.old_host:
            raise Refused("host-changed")
        self.pending_work_clear()
        self.require_stopped()
        self.clean_head(self.a.expected_old)
        if private_read(self.a.host) != self.old_host:
            raise Refused("host-changed")
        # A pre-existing (e.g. ignored) file where target adds a tracked path would be
        # overwritten by checkout and could not be told apart from our own bytes.
        if any(os.path.lexists(self.a.runtime / path) for path in self.target_only_paths()):
            raise Refused("runtime-target-path-exists")
        # Recovery may remove an index lock left by our own killed checkout; it must not pre-date it.
        if self.git_dir is not None and os.path.lexists(self.git_dir / "index.lock"):
            raise Refused("runtime-index-locked")
        self.write_attempted = True  # a failed or interrupted checkout may still change files
        self.git("checkout", "--detach", self.a.target)
        self.clean_head(self.a.target)
        if private_read(self.a.host) != self.old_host:
            raise Refused("host-changed")
        assert self.new_host is not None
        private_write(self.a.host, self.new_host)
        # Taken after the atomic replace returned: any process the kernel forked later
        # on this boot saw the new pin. CLOCK_BOOTTIME is the clock of /proc/<pid>/stat
        # starttime; wall-clock steps cannot reorder it.
        self.witness["pinned_boottime_ns"] = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        if boot_id() != self.witness["boot_id"]:
            raise Refused("unit-launch-boot")
        self.host_check()
        self.start_units()
        self.selftest()
        self.units(True)
        self.unit_launches()
        self.clean_head(self.a.target)
        if private_read(self.a.host) != self.new_host:
            raise Refused("host-changed")
        self.record("released")
        self.mutating = False

    def target_only_paths(self):
        """Paths tracked by target but not by expected_old (Git tree listing, not status)."""
        def tree(commit):
            out = self.command("owned-tree", ["git", "-C", str(self.a.runtime), "ls-tree", "-r", "--name-only", "-z",
                                              commit], strip=False)
            return set(out.split("\0")) - {""}
        return sorted(tree(self.a.target) - tree(self.a.expected_old))

    def recover_checkout(self):
        """Return the runtime to expected_old after a checkout this release started.

        The runtime was verified clean at expected_old, with services stopped and the
        release lock held, immediately before the checkout. So the only changes this
        transaction can own are paths that differ between expected_old and target.
        Anything else (or a HEAD that is neither commit) is foreign: refuse and leave
        it untouched for the operator. A checkout killed part-way may leave
        modified/deleted tracked files, untracked files added by target and the
        index lock; all three are undone here and the result is re-verified.
        """
        old, target = self.a.expected_old, self.a.target
        head = self.git("rev-parse", "HEAD")
        if head not in (old, target):
            raise Refused("rollback-runtime-changed")
        if self.git_dir is not None:
            lock = self.git_dir / "index.lock"
            if os.path.lexists(lock):
                if lock.is_symlink() or not lock.is_file():
                    raise Refused("rollback-index-lock")
                lock.unlink()  # left by the killed checkout child (process group already reaped)
        runtime = str(self.a.runtime)
        owned = set(self.command("owned-paths", ["git", "-C", runtime, "diff", "--name-only", "-z", "--no-renames",
                                                 old, target], strip=False).split("\0")) - {""}

        def dirty():
            out = self.command("rollback-status", ["git", "-C", runtime, "status", "--porcelain=v1", "-z",
                                                   "--no-renames", "--untracked-files=all"], strip=False)
            entries = [(item[:2], item[3:]) for item in out.split("\0") if item]
            if any(len(code) != 2 or path not in owned for code, path in entries):
                raise Refused("rollback-foreign-change")
            return entries

        dirty()  # refuse before any recovery write if a foreign path changed
        self.git("checkout", "--detach", "--force", old)
        # Paths tracked by target but not by old survive a forced checkout as
        # untracked files, and an old-tree ignore rule can hide them from status.
        # So remove them by name from the two trees, not from what status shows.
        # apply() refused before the checkout if any of them already existed.
        added = self.target_only_paths()
        root = self.a.runtime
        for path in added:
            file = root / path
            if not os.path.lexists(file):
                continue
            if not file.parent.resolve().is_relative_to(root) or not (file.is_symlink() or file.is_file()):
                raise Refused("rollback-foreign-change")
            file.unlink()
            parent = file.parent
            while parent != root and parent.is_dir() and not parent.is_symlink() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
        if dirty() or any(os.path.lexists(root / path) for path in added):
            raise Refused("rollback-runtime-changed")

    def rollback(self):
        # Rollback has a separate 3-minute budget; never start a mixed runtime/pin.
        self.rollback_mode = True
        self.deadline = time.monotonic() + 180
        self.stop()
        if self.write_attempted:
            current = private_read(self.a.host)
            if current not in (self.old_host, self.new_host):
                raise Refused("rollback-host-changed")
            self.recover_checkout()
            self.clean_head(self.a.expected_old)
            if private_read(self.a.host) != current:
                raise Refused("rollback-host-changed")
            assert self.old_host is not None
            private_write(self.a.host, self.old_host)
        else:
            # A pre-write refusal changed neither artifact. Do not rewrite them.
            self.clean_head(self.a.expected_old)
        if private_read(self.a.host) != self.old_host:
            raise Refused("rollback-host-changed")
        self.state_path()
        self.host_check()
        self.start_units()
        self.selftest()
        self.units(True)
        self.clean_head(self.a.expected_old)
        if private_read(self.a.host) != self.old_host:
            raise Refused("rollback-host-changed")
        self.record("rolled-back")
        self.mutating = False

    def run(self):
        self.preflight()
        if not self.a.apply:
            print(json.dumps({"result": "plan-only", "old": self.a.expected_old,
                              "target": self.a.target, "apply": False}))
            return 0
        if not self.a.attended or not sys.stdin.isatty():
            raise Refused("attended-terminal-required")
        # Private transaction root is deliberately separate from live state and Git.
        root = self.a.receipts
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        st = root.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
            raise Refused("receipt-directory")
        # Lock is tied to this runtime's Git metadata, not a caller-selected
        # receipt folder: alternate --receipts cannot run two moves together.
        git_dir = Path(self.git("rev-parse", "--absolute-git-dir"))
        self.git_dir = git_dir
        lock_path = git_dir / "runtime-release.lock"
        self.pending = git_dir / "runtime-release.pending"
        with open(lock_path, "a+b", opener=lambda p, f: os.open(p, f | os.O_NOFOLLOW, 0o600)) as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Refused("release-locked") from None
            # Detect an interrupted earlier release rather than starting another one.
            if os.path.lexists(self.pending):
                raise Refused("unfinished-release-operator-recovery-required")
            self.run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=root))
            try:
                self.apply()
                return 0
            except (Exception, KeyboardInterrupt) as exc:
                cause = str(exc) if isinstance(exc, Refused) else "interrupted-or-error"
                print("RELEASE refused " + cause, flush=True)
                if self.mutating:
                    try:
                        self.rollback()
                    except (Exception, KeyboardInterrupt):
                        # A failed rollback must not leave new/unknown code answering.
                        self.deadline = time.monotonic() + 30
                        with contextlib.suppress(Exception):
                            self.command("emergency-stop", ["systemctl", "--user", "stop", *reversed(UNITS)])
                        self.record("rollback-failed")
                        return 2
                return 1
            finally:
                if self.stage and self.stage.exists():
                    with contextlib.suppress(Exception):
                        self.command("stage-cleanup", ["git", "-C", self.a.runtime, "worktree", "remove", self.stage])


def arguments(argv=None):
    home = Path.home()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Reviewed merged-main full commit SHA")
    parser.add_argument("--expected-old", required=True, help="Expected detached runtime full commit SHA")
    parser.add_argument("--runtime", type=Path, default=home / ".local/share/hass/runtime")
    parser.add_argument("--host", type=Path, default=home / ".local/state/hass/host/host.json")
    parser.add_argument("--state-root", type=Path, default=home / ".local/state/hass")
    parser.add_argument("--python", type=Path, default=home / ".local/share/hass/venv/bin/python3")
    parser.add_argument("--receipts", type=Path, default=home / ".local/state/hass-releases")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--attended", action="store_true", help="Operator confirms existing approval; does not grant it")
    args = parser.parse_args(argv)
    if not SHA.fullmatch(args.target) or not SHA.fullmatch(args.expected_old):
        parser.error("commits must be full lowercase 40-hex SHA values")
    for name in ("runtime", "host", "state_root", "python", "receipts"):
        value = getattr(args, name).expanduser()
        if not value.is_absolute() or (name != "python" and value != value.resolve()):
            parser.error(name + " must be an absolute non-symlink path")
        setattr(args, name, value)
    for path in (args.host, args.state_root, args.receipts):
        if path.is_relative_to(args.runtime):
            parser.error("private paths must be outside runtime")
    return args


def main(argv=None):
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    try:
        return Release(arguments(argv)).run()
    except (Refused, OSError, ValueError):
        print("RELEASE refused preflight", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
