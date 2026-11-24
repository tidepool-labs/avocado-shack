"""HASS-LIVE-AUDIT-1: scripts/hass/live_selftest.sh --synthetic-only (scripts/hass/live_selftest_synth.py) passes on
this checkout; scripts/hass/live_selftest_model.py refuses an unknown case id before any model call; and the full
(live) mode, run against fake git/systemctl/journalctl and fake health/inbox output in a temp dir, FAILs when an
acquisition fails (health crash, git exit 128, journalctl exit 1) instead of reporting clean/healthy/zero, while the
valid controls (clean git, backup-age-only health, an empty successful journal query) still pass or warn.
Run: python3 -B -m unittest hass.tests.test_live_selftest"""

import os, shutil, subprocess, sys, tempfile, unittest  # noqa: E401
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "hass"
ENV = {"HASS_PYTHON": sys.executable, "PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}
if os.environ.get("TMPDIR"):
    ENV["TMPDIR"] = os.environ["TMPDIR"]  # child temp files stay in the configured scratch dir

# Stand-ins, selected by the PROBE_* variables. The fake interpreter answers for the synthetic and model helpers,
# health.py and inbox.py and hands every other script (the real live_selftest_parse.py) to the real interpreter.
# PROBE_BAD=<acquisition> makes exactly that one read print its normal, plausible good value and then exit 1.
FAKE_PY = f"""#!{sys.executable}
import os, sys
script = sys.argv[2] if len(sys.argv) > 2 else ""
health = os.environ.get("PROBE_HEALTH", "ok")
bad = os.environ.get("PROBE_BAD", "")
def good(text, name):
    print(text)
    sys.exit(1 if bad == name else 0)
if script.endswith("live_selftest_synth.py"):
    good('{{"failed": 0, "ran": 6, "synthetic": "pass"}}', "synthetic")
elif script.endswith("live_selftest_model.py"):
    good('{{"result": "pass", "cases": 3, "passed": 3}}', "model")
elif script.endswith("health.py"):
    if health == "crash":
        print("Traceback (most recent call last): simulated crash", file=sys.stderr)
        sys.exit(1)
    if health == "backup-age":
        print('{{"ok": false, "problems": [{{"check": "backup-age", "detail": "x"}}], "info": {{}}, "fingerprint": "f"}}')
        sys.exit(1)
    good('{{"ok": true, "problems": [], "info": {{}}, "fingerprint": "f"}}', "health")
elif script.endswith("inbox.py"):
    age = os.environ.get("PROBE_INBOX_AGE", "null")  # a raw JSON literal, e.g. 1e309
    note = os.environ.get("PROBE_INBOX_NOTE", "")
    good('{{"pending": 0, "done": 3, "history": 3, "oldest_pending_minutes": ' + age + ', "note": "' + note + '"}}', "inbox")
elif script.endswith("live_selftest_parse.py") and bad == "parse-" + sys.argv[3]:
    sys.stdin.read()
    good("" if sys.argv[3] == "health" else "0 null 3", bad)
else:
    os.execv({sys.executable!r}, [{sys.executable!r}] + sys.argv[1:])
"""
FAKE_GIT = """#!/bin/sh
[ "${PROBE_GIT:-ok}" = fail ] && exit 128
case "$*" in
  *rev-parse*) echo 0123456789ab; [ "${PROBE_BAD:-}" = git-rev-parse ] && exit 1 ;;
  *status*) [ "${PROBE_BAD:-}" = git-status ] && exit 1 ;;  # empty output would read as clean
esac
exit 0
"""
FAKE_SYSTEMCTL = """#!/bin/sh
case "$*" in
  *is-active*hass-receiver.service*) echo active; [ "${PROBE_BAD:-}" = is-active-service ] && exit 1 ;;
  *is-active*hass-health.timer*) echo active; [ "${PROBE_BAD:-}" = is-active-timer ] && exit 1 ;;
  *is-active*) echo active ;;
  *NRestarts*hass-receiver*) echo 0; [ "${PROBE_BAD:-}" = nrestarts ] && exit 1 ;;
  *NRestarts*) echo 0 ;;
  *LastTriggerUSec*hass-health*)
    case "${PROBE_TIMER:-ok}" in fail) exit 1 ;; never) echo 'n/a' ;; *) echo 'Sat 2026-11-07 14:40:03 PST' ;; esac
    [ "${PROBE_BAD:-}" = last-trigger ] && exit 1 ;;
  *LastTriggerUSec*)
    case "${PROBE_TIMER:-ok}" in fail) exit 1 ;; never) echo 'n/a' ;; *) echo 'Sat 2026-11-07 14:40:03 PST' ;; esac ;;
  *ExecMainStatus*hass-health*) echo 0; [ "${PROBE_BAD:-}" = exec-main-status ] && exit 1 ;;
  *ExecMainStatus*) echo 0 ;;
esac
exit 0
"""
FAKE_JOURNALCTL = """#!/bin/sh
case "${PROBE_JOURNAL:-empty}" in fail) exit 1 ;; lines) printf 'a\\nb\\nc\\n' ;; esac
[ "${PROBE_BAD:-}" = journalctl ] && exit 1  # no output with exit 0 would read as 0 lines
exit 0
"""


FAKE_DU = """#!/bin/sh
case "${PROBE_DU:-ok}" in partial) echo "123	$2"; exit 1 ;; esac
[ "${PROBE_BAD:-}" = du ] && { echo "123	$2"; exit 1; }
exec /usr/bin/du "$@"
"""
FAKE_DF = """#!/bin/sh
case "${PROBE_DF:-ok}" in partial) printf 'Filesystem 1M-blocks Used Available Capacity Mounted\\nx 10 1 9999 1%% /\\n'; exit 1 ;; esac
[ "${PROBE_BAD:-}" = df ] && { printf 'Filesystem 1M-blocks Used Available Capacity Mounted\\nx 10 1 9999 1%% /\\n'; exit 1; }
exec /usr/bin/df "$@"
"""
FAKE_FIND = """#!/bin/sh
[ "${PROBE_BAD:-}" = find ] && { echo "$1/hass-state-synthetic.tar"; exit 1; }
exec /usr/bin/find "$@"
"""
FAKE_DATE = """#!/bin/sh
[ "${PROBE_BAD:-}" = date ] && [ "$1" = +%s ] && { echo 1794000000; exit 1; }
[ "${PROBE_BAD:-}" = date-utc ] && [ "$1" = -u ] && { echo 2026-11-08T00:00:00Z; exit 1; }
exec /usr/bin/date "$@"
"""

# The class rule as a table: (PROBE_BAD acquisition, the check that must FAIL, extra script arguments).
BAD_READS = (
    ("git-status", "runtime", ()), ("git-rev-parse", "runtime", ()),
    ("synthetic", "synthetic", ()),
    ("is-active-service", "service:hass-receiver", ()), ("nrestarts", "service:hass-receiver", ()),
    ("is-active-timer", "timer:hass-health", ()), ("last-trigger", "timer:hass-health", ()),
    ("exec-main-status", "timer:hass-health", ()),
    ("find", "backup", ()),
    ("health", "health", ()), ("parse-health", "health", ()),
    ("inbox", "inbox", ()), ("parse-inbox", "inbox", ()),
    ("model", "model", ("--model", "m")),
    ("date", "growth", ()), ("du", "growth", ()), ("df", "growth", ()), ("journalctl", "growth", ()),
    ("date-utc", "clock", ()),
)
SPECIFIC = {  # the wording the disposition names for the systemctl reads
    "is-active-service": "hass-receiver.service state unknown (systemctl exit 1)",
    "is-active-timer": "hass-health.timer state unknown (systemctl exit 1)",
    "nrestarts": "restart counter unknown (systemctl exit 1)",
    "last-trigger": "last trigger query failed (systemctl exit 1)",
    "exec-main-status": "last run exit status unknown (systemctl exit 1)",
    "date-utc": "summary clock unknown (date exit 1)",
}


class LiveSelftestScript(unittest.TestCase):
    def test_synthetic_only_passes_and_touches_no_live_path(self):
        r = subprocess.run(["bash", str(SCRIPTS / "live_selftest.sh"), "--synthetic-only"], capture_output=True, text=True,
                           timeout=600, env=ENV, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('PASS synthetic {"failed": 0, "ran": 6, "synthetic": "pass"}', r.stdout)
        self.assertRegex(r.stdout, r"HASS-SELFTEST \S+Z pass=1 warn=0 fail=0 skip=0\n$")

    def test_model_helper_refuses_an_unknown_case_without_calling_a_model(self):
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "live_selftest_model.py"), "--url", "http://127.0.0.1:9",
                            "--model", "m", "--ids", "nope"], capture_output=True, text=True, timeout=60, cwd=ROOT)
        self.assertEqual((r.returncode, r.stdout.strip()), (2, '{"result": "error", "error": "--ids: unknown case id"}'))


class InboxReportParserTests(unittest.TestCase):
    """Saved reports run through the real stdin parser CLI, without services."""

    BOUNDED = "invalid inbox report: oldest_pending_minutes not a number or null\n"

    def parse(self, age):
        text = '{"pending": 1, "done": 3, "oldest_pending_minutes": %s}\n' % age
        return self.parse_report("inbox", text)

    def parse_report(self, mode, text):
        r = subprocess.run([sys.executable, "-B", str(SCRIPTS / "live_selftest_parse.py"), mode], input=text,
                           capture_output=True, text=True, timeout=60, cwd=ROOT)
        return r.returncode, r.stdout, r.stderr

    def test_inbox_parser_refuses_nonfinite_age(self):
        for age in ("1e309", "Infinity", "NaN", "-Infinity", "-1e309"):
            with self.subTest(age=age):
                self.assertEqual(self.parse(age), (3, self.BOUNDED, ""))

    def test_inbox_parser_preserves_finite_and_null(self):
        big = "9" * 400  # an integer far beyond float range stays valid and exact
        for age, shown in (("0", "0"), ("2.5", "2"), ("null", "null"), ("7", "7"), (big, big)):
            with self.subTest(age=age[:12]):
                self.assertEqual(self.parse(age), (0, f"1 {shown} 3\n", ""))
        for age in ("true", "-1", "-0.5", '"5"'):
            with self.subTest(age=age):
                self.assertEqual(self.parse(age), (3, self.BOUNDED, ""))

    def test_inbox_parser_refuses_duplicate_pending(self):
        # Last-key-wins would let a later zero conceal pending work.
        quiet = 'diagnostic note\n{"pending": 0, "done": 3, "oldest_pending_minutes": null}\n\n'
        contradictory = quiet.replace('"pending": 0', '"pending": 9, "pending": 0')
        self.assertEqual(self.parse_report("inbox", quiet), (0, "0 null 3\n", ""))
        self.assertEqual(self.parse_report("inbox", contradictory),
                         (3, "invalid inbox report: report is not JSON\n", ""))

    def test_health_parser_refuses_duplicate_ok(self):
        # A later true must not overwrite an earlier false and yield healthy output.
        healthy = 'diagnostic note\n{"ok": true, "problems": []}\n\n'
        contradictory = healthy.replace('"ok": true', '"ok": false, "ok": true')
        self.assertEqual(self.parse_report("health", healthy), (0, "\n", ""))
        self.assertEqual(self.parse_report("health", contradictory),
                         (3, "invalid health report: report is not JSON\n", ""))

    def test_parser_refuses_duplicate_keys_in_nested_objects(self):
        # Checking only the top level would miss ambiguity inside an ignored nested field.
        healthy = '{"ok": true, "problems": [], "info": [{"fixture": 1}, {"fixture": 2}]}\n'
        duplicate = healthy.replace('{"fixture": 2}', '{"fixture": 2, "fixture": 2}')
        self.assertEqual(self.parse_report("health", healthy), (0, "\n", ""))
        self.assertEqual(self.parse_report("health", duplicate),
                         (3, "invalid health report: report is not JSON\n", ""))


class LiveModeAcquisitionFailures(unittest.TestCase):
    """The live checks, isolated: fakes on PATH, a temp state root with a fresh backup, a temp growth file."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hass-selftest-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        bins = self.tmp / "bin"
        bins.mkdir()
        for name, body in (("python", FAKE_PY), ("git", FAKE_GIT), ("systemctl", FAKE_SYSTEMCTL),
                           ("journalctl", FAKE_JOURNALCTL), ("du", FAKE_DU), ("df", FAKE_DF), ("find", FAKE_FIND),
                           ("date", FAKE_DATE)):
            (bins / name).write_text(body)
            (bins / name).chmod(0o700)
        self.state = self.tmp / "hass"
        (self.state / "backups").mkdir(parents=True)
        (self.state / "backups" / "hass-state-synthetic.tar").write_text("x")
        self.growth = self.tmp / "growth.tsv"
        self.env = dict(ENV, PATH=f"{bins}:/usr/bin:/bin", HASS_PYTHON=str(bins / "python"))

    def run_live(self, *args, **probes):
        r = subprocess.run(["bash", str(SCRIPTS / "live_selftest.sh"), "--state-root", str(self.state),
                            "--growth-file", str(self.growth), "--min-free-mb", "1", *args],
                           capture_output=True, text=True, timeout=120, env=dict(self.env, **probes), cwd=self.tmp)
        lines = {ln.split(" ", 2)[1]: ln for ln in r.stdout.splitlines() if ln[:5] in ("PASS ", "WARN ", "FAIL ", "SKIP ")}
        return r, lines

    def test_valid_controls_pass(self):
        r, lines = self.run_live()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(lines["runtime"], "PASS runtime checkout 0123456789ab clean")
        self.assertEqual(lines["runtime-after"], "PASS runtime-after still clean")
        self.assertEqual(lines["health"], "PASS health no problems")
        self.assertEqual(lines["inbox"], "PASS inbox pending 0, done 3")
        self.assertRegex(lines["growth"], r"^PASS growth state \d+ KB, free \d+ MB, hass journal 0 lines/24h$")
        self.assertRegex(self.growth.read_text(), r"^\d+ \d+ \d+ 0\n$")
        self.assertRegex(r.stdout, r"pass=11 warn=0 fail=0 skip=1\n$")

    def test_nonfinite_inbox_measurement_fails_without_report_leak(self):
        marker = "PRIVATE-MARKER-7f3a"
        for age in ("1e309", "Infinity", "NaN"):
            with self.subTest(age=age):
                r, lines = self.run_live(PROBE_INBOX_AGE=age, PROBE_INBOX_NOTE=marker)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertEqual(lines["inbox"], "FAIL inbox invalid report (parser exit 3): "
                                 "invalid inbox report: oldest_pending_minutes not a number or null")
                self.assertIn("failed:inbox", r.stdout)
                for leak in (marker, "Traceback", "OverflowError", age, "oldest_pending_minutes\":"):
                    self.assertNotIn(leak, r.stdout + r.stderr)

    def test_backup_age_only_health_is_a_warning(self):
        r, lines = self.run_live(PROBE_HEALTH="backup-age", PROBE_JOURNAL="lines")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(lines["health"], "WARN health problems: backup-age")
        self.assertIn("hass journal 3 lines/24h", lines["growth"])

    def test_health_crash_fails(self):
        r, lines = self.run_live(PROBE_HEALTH="crash")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(lines["health"].startswith("FAIL health health.py exit 1 without a valid report"), lines["health"])
        self.assertNotIn("Traceback", r.stdout)
        self.assertIn("failed:health", r.stdout)

    def test_git_failure_is_not_clean(self):
        r, lines = self.run_live(PROBE_GIT="fail")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(lines["runtime"], "FAIL runtime cannot read the checkout head (git rev-parse exit 128)")
        self.assertEqual(lines["runtime-after"], "FAIL runtime-after checkout state unknown (git status exit 128)")
        self.assertNotIn("clean", lines["runtime"] + lines["runtime-after"])

    def test_journal_failure_is_not_zero_lines(self):
        self.growth.write_text("1 2 3 4\n")
        r, lines = self.run_live(PROBE_JOURNAL="fail")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(lines["growth"].startswith("FAIL growth "), lines["growth"])
        self.assertIn("hass journal unknown lines/24h", lines["growth"])
        self.assertIn("not measured: hass journal (journalctl exit 1)", lines["growth"])
        self.assertNotIn("journal 0 lines", lines["growth"])
        self.assertEqual(self.growth.read_text(), "1 2 3 4\n")  # the previous baseline is kept

    def test_du_partial_total_with_nonzero_exit_fails_and_keeps_baseline(self):
        self.growth.write_text("1 2 3 4\n")
        r, lines = self.run_live(PROBE_DU="partial")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(lines["growth"].startswith("FAIL growth "), lines["growth"])
        self.assertIn("not measured: state size (du exit 1)", lines["growth"])
        self.assertIn("state unknown KB", lines["growth"])
        self.assertEqual(self.growth.read_text(), "1 2 3 4\n")

    def test_df_partial_output_with_nonzero_exit_fails_and_keeps_baseline(self):
        self.growth.write_text("1 2 3 4\n")
        r, lines = self.run_live(PROBE_DF="partial")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("not measured: free disk (df exit 1)", lines["growth"])
        self.assertEqual(self.growth.read_text(), "1 2 3 4\n")

    def test_timer_query_failure_fails_but_never_triggered_timer_only_warns(self):
        r, lines = self.run_live(PROBE_TIMER="fail")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(lines["timer:hass-health"], "FAIL timer:hass-health last trigger query failed (systemctl exit 1)")
        self.assertIn("failed:timer:hass-health,timer:hass-backup", r.stdout)
        r, lines = self.run_live(PROBE_TIMER="never")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(lines["timer:hass-health"], "WARN timer:hass-health active, has not run yet")

    def test_every_failed_read_fails_its_check_even_with_good_looking_output(self):
        """Class rule: each acquisition prints a plausible good value and exits 1; the script must FAIL that check."""
        r, lines = self.run_live("--model", "m")  # control: every fake good, the model helper included
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL ", r.stdout)
        self.assertTrue(lines["model"].startswith("PASS model "), lines["model"])
        r, lines = self.run_live(PROBE_TIMER="never")  # control: a timer that successfully answers it never ran
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(lines["timer:hass-health"], "WARN timer:hass-health active, has not run yet")
        rows = BAD_READS + (("exec-main-status", "timer:hass-health", ()),)  # second pass below: with never-ran
        for i, (bad, check, args) in enumerate(rows):
            extra = {"PROBE_TIMER": "never"} if i == len(BAD_READS) else {}
            with self.subTest(bad=bad, **extra):
                self.growth.write_text("1 2 3 4\n")
                r, lines = self.run_live(*args, PROBE_BAD=bad, **extra)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertTrue(lines[check].startswith(f"FAIL {check} "), lines[check])
                self.assertIn(check, r.stdout.splitlines()[-1].split("failed:", 1)[1].split(","))
                if bad in SPECIFIC:
                    self.assertIn(SPECIFIC[bad], lines[check])
                if check == "growth":
                    self.assertIn("not measured:", lines[check])
                    self.assertEqual(self.growth.read_text(), "1 2 3 4\n")  # the baseline is kept


if __name__ == "__main__":
    unittest.main()
