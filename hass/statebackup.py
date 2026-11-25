"""Hass private state backup, verify and isolated restore drill (H20 prep).

    python3 hass/statebackup.py create --state DIR --out DIR [--media DIR] | verify BACKUP
                                | restore BACKUP --into DIR --worktree WT [--paused] [--media-into DIR] | list --out DIR
                                | drill BACKUP --into DIR --worktree WT [--media-into DIR] | diff OLD NEW

create refuses a symlinked or odd config.json/writer.lock before anything opens it, takes the writer lock and copies a
settled state dir (config.json, drafts, changes, screenshots, the audit log and consistent sqlite snapshots of inbox.sqlite3, then
conversation.sqlite3, transcript.sqlite3 and the till's clover/cache.sqlite3, clover/journal.sqlite3 and clover/bundles.sqlite3
if present, the latter two while holding their own flock; plus clover/links.json and clover/receipts/<day>-<code>.json copied whole;
never writer.lock, a till lock file, a journal, a symlink or an unknown entry) into a new private
<out>/hass-state-<UTC stamp>/ (out: an existing 0700 user dir; built aside, renamed in) and writes MANIFEST.json last.
verify re-checks every hash and mode, refuses extra entries and symlinks and runs the sqlite integrity check on each
store, and that config.json is an object naming the manifest's exact worktree; listed photo originals and sidecars must pair one-to-one
and match media.originals. restore verifies first, then builds a NEW state dir bound
to a separate drill worktree (only config.json `worktree` is rewritten). Isolation rule: nothing restores over an existing
dir or onto the recorded writer worktree (an attended operation); backups stay private (0700/0600) and outside the
repository, the worktrees and the state dir. No network, no Git writes, no deletes of source data. One JSON line out;
exit 0 ok, 1 any other result, 2 unsafe dir or usage. list (read-only): a line per hass-state-* entry, complete or not.
diff (read-only): files added, removed and changed from OLD to NEW (photo originals as counts), i.e. what a restore of
OLD would lose. diff reads manifests only; run verify for integrity.
A new backup's MANIFEST.json also records `contentCommit`, the writer worktree's HEAD (read-only git; null if unreadable).
With a contentCommit, create also writes content.bundle (a full `git bundle` of that HEAD: site content and committed web
photos), listed and hashed like any file; verify requires its head to be contentCommit. Without --content-into DIR
restore skips it; with it, restore/drill clone it into a NEW dir at contentCommit and run its sitegen --check (FAV-08).
"""
import argparse, contextlib, ctypes, errno, fcntl, hashlib, json, os, re, shutil, sqlite3, stat, subprocess, sys, time  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import corrlog, editor, media as photos  # noqa: E402
from hass.conversation import CONTROL, _iso  # noqa: E402
from hass.content_model import REPO_ROOT  # noqa: E402
from hass.editor import UnsafeState  # noqa: E402
from hass.npp.job import job_photos  # noqa: E402
from hass.npp.receipt import CARD_RE, JOB_RE, read_artifact  # noqa: E402

MANIFEST, CONFIG, DB, LOCK = "MANIFEST.json", "config.json", "conversation.sqlite3", "writer.lock"
INBOX = "inbox.sqlite3"  # H16 inbound queue; snapshotted like DB
TRANSCRIPT = "transcript.sqlite3"  # Private append-only conversation history; online snapshot like DB.
CLOVER = "clover/cache.sqlite3"  # till cache (hass/clover/cache.py); snapshotted; the item link table will join it
JOURNAL, BUNDLES = "clover/journal.sqlite3", "clover/bundles.sqlite3"  # till write state (HCI-16): undo journal, change bundles
LINKS = "clover/links.json"  # site product <-> Clover item link table; atomically replaced by its writer, so copied whole
RECEIPT_DIR = "clover/receipts"  # private inventory receipts <YYYY-MM-DD>-<code>.json (hass/clover/inventory_receipt.py)
RECEIPT = RECEIPT_DIR + r"/[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9a-f]{8}\.json"
STORES = (DB, INBOX, TRANSCRIPT, CLOVER, JOURNAL, BUNDLES)  # sqlite stores: online snapshot, then integrity check on verify
LOCKS = {JOURNAL: "clover/journal.lock", BUNDLES: "clover/bundles.lock"}  # each till store's own flock; skipped, never copied
LOCK_WAIT = 5.0  # seconds create waits for a till store's flock (a write in flight) before answering `busy`
BUNDLE = "content.bundle"  # FAV-07: git bundle of the writer worktree's HEAD == contentCommit
DIRS = ("drafts", "changes", "screenshots", "audit")  # AVB-10: audit/ is the one audit log (ids only), kept with the state
ORIG = "media/originals/"  # H10 photo originals <aa>/<sha>.<ext> + <aa>/<sha>.json, aa == sha[:2] (hass/media.py)
NPP = "media/npp/"  # private listing receipts and immutable, content-addressed card PNGs
MEDIA = (ORIG, NPP)
FALLBACK_JPEG = r"screenshots/([0-9a-f]{64})\.jpg"  # frozen listing picture, named by its bytes; never arbitrary JPEGs
FILE_RE = re.compile(r"config\.json|conversation\.sqlite3|inbox\.sqlite3|transcript\.sqlite3|clover/cache\.sqlite3|content\.bundle"
                     r"|clover/(?:journal|bundles)\.sqlite3|clover/links\.json"
                     rf"|{RECEIPT}"
                     r"|(drafts|changes)/chg-[0-9A-Za-z_-]+\.json"
                     r"|screenshots/[0-9A-Za-z_-][0-9A-Za-z._-]*\.png"
                     rf"|{FALLBACK_JPEG}"
                     rf"|{NPP}{JOB_RE}/(?:receipt\.json|{CARD_RE})"
                     r"|audit/[0-9]{4}-[0-9]{2}-[0-9]{2}\.jsonl"
                     r"|media/originals/(?P<aa>[0-9a-f]{2})/(?P=aa)[0-9a-f]{62}\.(json|%s)"
                     % "|".join(sorted(set(photos.EXT.values()))))
HEX_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
ATTENDED = "restoring onto the recorded writer worktree is an attended operation"
MANIFEST_MAX, SMALL_MAX = 8 << 20, 64 << 10  # bytes: MANIFEST.json (~80 000 listed files); a media sidecar

def _read(path: Path) -> bytes:
    """Bytes of a regular file; a symlink is never followed."""
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as fh:
        return fh.read()

def _read_small(path: Path, limit: int) -> bytes:
    """Bytes of a regular file of at most `limit` bytes. A symlink, FIFO, folder or device is OSError and a FIFO is
    opened non-blocking (never waits for a writer); a longer file is ValueError."""
    with os.fdopen(fd := os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as fh:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise OSError(errno.EINVAL, "not a regular file", str(path))
        data = fh.read(limit + 1)
    if len(data) > limit: raise ValueError(f"over {limit} bytes: {path}")
    return data

def _write_new(path: Path, data: bytes) -> None:
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as fh:
        fh.write(data)
    os.chmod(path, 0o600)

def _copy(src: Path, dst: Path) -> None:
    _write_new(dst, _read(src))

def _read_fallback(path: Path, digest: str) -> bytes:
    data = _read_small(path, photos.MAX_BYTES)
    if not data.startswith(photos.KINDS["jpeg"]) or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("invalid frozen listing picture")
    return data

def _rename_noreplace(src: Path, dst: Path) -> None:
    """Atomic rename that raises FileExistsError if dst exists, even as an empty dir (os.rename would replace it)."""
    libc, a, b = ctypes.CDLL(None, use_errno=True), os.fsencode(src), os.fsencode(dst)
    if hasattr(libc, "renameat2"): rc = libc.renameat2(-100, a, -100, b, 1)  # AT_FDCWD, RENAME_NOREPLACE (Linux)
    elif hasattr(libc, "renamex_np"): rc = libc.renamex_np(a, b, 4)  # RENAME_EXCL (macOS)
    else: raise OSError(errno.ENOSYS, "no atomic no-replace rename here", str(dst))
    if rc: raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), str(dst))  # EEXIST: FileExistsError

def _connect_ro(path: Path):
    return contextlib.closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True))

def _private_dirs(path: Path) -> None:
    """mkdir -p with every directory it makes 0700 whatever the umask: mkdir(parents=True) gives the parents
    0777 & ~umask, so a media/npp made that way fails verify's mode check under the usual umask 022."""
    missing = []
    while not path.exists():
        missing.append(path)
        path = path.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)

def _snapshot(src: Path, dst: Path) -> None:  # a consistent copy via the sqlite online backup API
    _write_new(dst, b"")
    with _connect_ro(src) as source, contextlib.closing(sqlite3.connect(dst)) as target:
        source.backup(target)
    os.chmod(dst, 0o600)

class _StoreBusy(Exception):
    """A till store's flock is held by a write in flight and stayed held for LOCK_WAIT seconds."""

@contextlib.contextmanager
def _store_lock(sdir: Path, rel: str):
    """Hold the till store's own flock (the one its writer takes: clover/journal.lock, clover/bundles.lock) around the
    snapshot. The lock file is opened without following a symlink, created 0600 if its writer has not yet, and must be
    a private regular file of ours (as the writer requires); it is never copied. Waits LOCK_WAIT s, then _StoreBusy."""
    flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    try: fd = os.open(sdir / LOCKS[rel], flags, 0o600)
    except OSError as exc: raise UnsafeState(f"unsafe till lock: {LOCKS[rel]} ({exc.strerror})") from None
    with os.fdopen(fd, "r+b"):
        if not stat.S_ISREG((st := os.fstat(fd)).st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise UnsafeState(f"unsafe till lock: {LOCKS[rel]}")
        deadline = time.monotonic() + LOCK_WAIT
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline: raise _StoreBusy(rel) from None
                time.sleep(0.05)
        yield

def _inside(path: Path, roots) -> bool:
    return any(path == root or root in path.parents for root in roots)

def _roots(wt: Path) -> list:
    """The checkout, a worktree and (if it is a Git checkout) its main checkout."""
    roots = [REPO_ROOT.resolve(), wt.resolve()]
    if editor._git(wt, "rev-parse").returncode == 0: roots.append(editor._common_dir(wt).parent)
    return roots

def _private_out(raw, roots) -> Path:
    path = Path(raw).resolve()
    if not path.is_dir(): raise UnsafeState("backup dir must already exist")
    if (st := path.stat()).st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise UnsafeState("backup dir must be owned by the current user with mode 0700")
    if _inside(path, roots):
        raise UnsafeState("backup dir must lie outside the state dir, the repository and the writer worktree")
    return path

def _scan(sdir: Path):
    """(files to copy, problems) for the known layout; symlinks and unknown entries are named, never followed."""
    files, bad = [], []
    for entry in sorted(os.scandir(sdir), key=lambda e: e.name):
        if entry.is_symlink(): bad.append(f"symlink: {entry.name}")
        elif entry.is_dir(follow_symlinks=False) and entry.name == corrlog.FOLDER:
            continue  # The private log is not backed up; never traverse its contents.
        elif entry.is_dir(follow_symlinks=False) and entry.name in DIRS + ("journal", "clover"):
            for sub in sorted(os.scandir(entry.path), key=lambda e: e.name):
                rel = f"{entry.name}/{sub.name}"
                if sub.is_symlink(): bad.append(f"symlink: {rel}")
                elif sub.is_file(follow_symlinks=False) and FILE_RE.fullmatch(rel): files.append(rel)
                elif sub.is_file(follow_symlinks=False) and rel in LOCKS.values(): continue  # a till store's flock file: never copied
                elif rel == RECEIPT_DIR and sub.is_dir(follow_symlinks=False):
                    for receipt in sorted(os.scandir(sub.path), key=lambda e: e.name):
                        name = f"{rel}/{receipt.name}"
                        if receipt.is_symlink(): bad.append(f"symlink: {name}")
                        elif receipt.is_file(follow_symlinks=False) and FILE_RE.fullmatch(name): files.append(name)
                        else: bad.append(f"unknown entry: {name}")
                else: bad.append(f"unknown entry: {rel}")
        elif entry.is_file(follow_symlinks=False) and entry.name in (CONFIG, DB, INBOX, TRANSCRIPT): files.append(entry.name)
        elif not (entry.is_file(follow_symlinks=False) and entry.name == LOCK): bad.append(f"unknown entry: {entry.name}")
    return files, bad

def _media_root(raw, roots) -> Path:  # create --media: the H10 photo store (hass/media.py)
    if os.path.islink(raw) or not os.path.isdir(raw): raise UnsafeState("media dir must be an existing dir, no symlink")
    if (st := os.lstat(raw)).st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise UnsafeState("media dir must be owned by the current user with mode 0700")
    if _inside(path := Path(raw).resolve(), roots):
        raise UnsafeState("media dir must lie outside the repository, the worktrees, the state dir and the backup dir")
    return path

def _scan_media(mroot: Path, strict=True):
    """(backup rels of settled originals + sidecars, refused names, unsettled names); nothing is followed.
    strict=False (the configured NPP root, never named by --media) takes only originals/ and npp/, ignoring web/ etc."""
    orig, pairs = mroot / "originals", {}
    bad = [f"unknown media entry: {e.name}" for e in os.scandir(mroot) if e.name not in ("originals", "npp") or e.is_symlink()
           or not e.is_dir()] if strict else [f"unsafe media entry: {e.name}" for e in os.scandir(mroot)
                                              if e.name in ("originals", "npp") and (e.is_symlink() or not e.is_dir())]
    subs = list(os.scandir(orig)) if orig.is_dir() and not orig.is_symlink() else []
    for entry in [s for s in subs if s.is_symlink() or not s.is_dir()] + [
            e for s in subs if s.is_dir(follow_symlinks=False) for e in os.scandir(s.path)]:
        rel = ORIG + os.path.relpath(entry.path, orig)  # media/originals/<aa>/<sha>.<ext>: the sha is rel[19:83]
        if entry.is_symlink(): bad.append(f"symlink: {rel}")
        elif entry.is_file(follow_symlinks=False) and FILE_RE.fullmatch(rel):
            pairs.setdefault(rel[19:83], []).append(rel)
        else: bad.append(f"unknown entry: {rel}")
    unsettled = [f"unsettled media: {sha[:12]}" for sha, rels in sorted(pairs.items())
                 if sorted(rel.endswith(".json") for rel in rels) != [False, True]]
    artifacts, invalid = _scan_npp(mroot)
    return sorted(sum(pairs.values(), []) + artifacts), sorted(bad + invalid), unsettled


def _scan_npp(mroot):
    npp, artifacts, bad = mroot / "npp", [], []
    if os.path.lexists(npp):
        if not npp.is_dir() or npp.is_symlink():
            return [], ["unsafe media/npp directory"]
        for job in os.scandir(npp):
            if not (job.is_dir(follow_symlinks=False) and re.fullmatch(JOB_RE, job.name)):
                bad.append(f"unknown entry: {NPP}{job.name}")
                continue
            for entry in os.scandir(job.path):
                rel = f"{NPP}{job.name}/{entry.name}"
                if entry.is_file(follow_symlinks=False) and FILE_RE.fullmatch(rel): artifacts.append(rel)
                else: bad.append(f"unknown entry: {rel}")
    return sorted(artifacts), sorted(bad)

def create(state, out, now=None, media=None) -> dict:
    if not state or not Path(state).is_dir(): raise UnsafeState("state dir must already exist")  # open_state creates
    top = [p for p in _scan(editor.open_state(state))[1] if p.split(": ", 1)[1] in (CONFIG, LOCK)]
    if top: return {"result": "refused", "problems": top}  # before _load reads config / _writer_lock creates the lock
    sdir, cfg, wt = editor._load(state)
    dest_root = _private_out(out, _roots(wt) + [sdir])
    settings = cfg.get("settings") or {}
    configured = settings.get("mediaRoot") if settings.get("npp") is True else None
    mroot = None if media is None else _media_root(media, _roots(wt) + [sdir, dest_root])
    nroot = _media_root(configured, _roots(wt) + [sdir, dest_root]) if configured and os.path.lexists(configured) else None
    with editor._writer_lock(sdir) as held, contextlib.ExitStack() as undo:
        if not held: return {"result": "busy"}
        if (journal := sdir / "journal").is_dir() and not journal.is_symlink() and any(journal.iterdir()):
            return {"result": "unsettled", "problems": ["an interrupted write is pending; run editor.py recover first"]}
        files, bad = _scan(sdir)
        mfiles, mbad, unsettled = _scan_media(mroot) if mroot else ([], [], [])
        if nroot and nroot != mroot:
            # The configured NPP root's jobs and the originals they name travel together; an explicit originals root can
            # differ but not claim a second job tree. The same sha names the same bytes, so a shared rel is kept once.
            nfiles, nbad, nunsettled = _scan_media(nroot, strict=False)
            if any(rel.startswith(NPP) for rel in mfiles): nbad.append("two NPP media roots")
            mfiles, mbad, unsettled = sorted(set(mfiles) | set(nfiles)), mbad + nbad, unsettled + nunsettled
        if bad or mbad: return {"result": "refused", "problems": bad + mbad}
        if unsettled: return {"result": "unsettled", "problems": unsettled}  # a photo write may be in flight
        now = now or datetime.now(timezone.utc)
        final = dest_root / f"hass-state-{now.strftime('%Y%m%dT%H%M%SZ')}"
        if os.path.lexists(final): return {"result": "exists", "backup": str(final)}
        dest = dest_root / f".{final.name}.partial-{os.getpid()}"  # built aside (dot name), renamed to final last
        dest.mkdir(mode=0o700)
        undo.callback(shutil.rmtree, dest, ignore_errors=True)  # any failure: only the folder this call created
        os.chmod(dest, 0o700)
        hashes = {}
        for sub in ("media", ORIG) if mfiles else (): (dest / sub).mkdir(mode=0o700)
        # The inbox goes first: a row it shows `done` was handled before, so the later DB snapshot holds its effect;
        # one handled in between stays `pending` here and a later drain answers it `duplicate` (no second write).
        for rel in sorted(files + mfiles, key=lambda rel: rel != INBOX):
            _private_dirs((dest / rel).parent)
            if rel.startswith(NPP):
                try: data = read_artifact((nroot or mroot) / rel[len("media/"):])
                except (OSError, ValueError, RecursionError):
                    return {"result": "refused", "problems": [f"invalid NPP artifact: {rel}"]}
                _write_new(dest / rel, data)
                hashes[rel] = hashlib.sha256(data).hexdigest()
                continue
            src = next(r for r in (mroot, nroot) if r and os.path.lexists(r / rel[6:])) / rel[6:] if rel.startswith(ORIG) else sdir / rel
            if fallback := re.fullmatch(FALLBACK_JPEG, rel):
                try: data = _read_fallback(src, fallback[1])
                except (OSError, ValueError):
                    return {"result": "refused", "problems": [f"invalid fallback picture: {rel}"]}
                _write_new(dest / rel, data)
                hashes[rel] = fallback[1]
                continue
            try:
                with _store_lock(sdir, rel) if rel in LOCKS else contextlib.nullcontext():
                    (_snapshot if rel in STORES else _copy)(src, dest / rel)
            except _StoreBusy: return {"result": "busy", "problems": [f"till store in use: {rel}"]}  # a write is in flight; retry
            hashes[rel] = hashlib.sha256(_read(dest / rel)).hexdigest()
        doc = {"schemaVersion": 1, "createdAt": now.isoformat(), "worktree": cfg["worktree"], "files": hashes}
        commit = _head(Path(cfg["worktree"]))  # inside the writer lock; read-only
        if commit:  # FAV-07: the content itself, made inside the same lock; read-only git
            doc["contentCommit"] = commit
            # pack.threads=1: multi-threaded delta search packs the same HEAD differently from run to run, so two backups
            # of one commit hashed differently and `diff` reported content.bundle as changed (main red, CI and local).
            _git_ro(cfg["worktree"], "-c", "pack.threads=1", "bundle", "create", str(dest / BUNDLE), "HEAD")
            if not _bundle_holds(dest / BUNDLE, commit):
                return {"result": "refused", "problems": ["content bundle does not hold contentCommit"]}
            os.chmod(dest / BUNDLE, 0o600)
            hashes[BUNDLE] = hashlib.sha256(_read(dest / BUNDLE)).hexdigest()
        originals = sum(rel.startswith(ORIG) for rel in mfiles) // 2
        if mroot or mfiles: doc["media"] = {"originals": originals}
        _write_new(dest / (MANIFEST + ".tmp"), json.dumps(doc, indent=2, sort_keys=True).encode("utf-8"))
        os.replace(dest / (MANIFEST + ".tmp"), dest / MANIFEST)  # last: a backup without it is incomplete
        _rename_noreplace(dest, final)  # a final dir that appeared meanwhile (even empty) is refused, never replaced
        undo.pop_all()  # renamed in: nothing left to clean up
    extra = {"media": originals} if mroot or nroot else {}  # settled: one sidecar per original
    return {"result": "ok", "backup": str(final), "files": len(hashes), "contentCommit": commit,
            "contentBundle": BUNDLE in hashes, **extra}

def _git_ro(wt, *args) -> str:
    """git stdout, or "" if git is missing or its output is not UTF-8 (e.g. a crafted ref name); read-only callers only."""
    old = os.environ.get("GIT_OPTIONAL_LOCKS")
    os.environ["GIT_OPTIONAL_LOCKS"] = "0"  # this call only: never refresh the writer's index
    try: return editor._out(wt, *args)
    except (OSError, UnicodeDecodeError): return ""
    finally:
        if old is None: os.environ.pop("GIT_OPTIONAL_LOCKS", None)
        else: os.environ["GIT_OPTIONAL_LOCKS"] = old

def _head(wt: Path):
    """The worktree's HEAD as 40 lowercase hex, else None (not a repo, unborn HEAD, git missing)."""
    return out if COMMIT_RE.fullmatch(out := _git_ro(wt, "rev-parse", "HEAD")) else None

def _bundle_holds(path: Path, commit) -> bool:  # `git bundle list-heads` reads the file only: no repository, no write
    return f"{commit} HEAD" in _git_ro(path.parent, "bundle", "list-heads", str(path)).splitlines()

def _manifest(bdir: Path):
    try:
        doc = json.loads(_read_small(bdir / MANIFEST, MANIFEST_MAX).decode("utf-8"))
        files = doc["files"]
        valid = doc.get("schemaVersion") == 1 and isinstance(doc.get("worktree"), str) and isinstance(files, dict) \
            and ("contentCommit" not in doc or isinstance(doc["contentCommit"], str)
                 and COMMIT_RE.fullmatch(doc["contentCommit"])) \
            and CONFIG in files and all(isinstance(rel, str) and FILE_RE.fullmatch(rel) and isinstance(digest, str)
                                        and HEX_RE.fullmatch(digest) for rel, digest in files.items())
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return None
    return doc if valid else None

def _intact(path: Path) -> bool:
    try:
        with _connect_ro(path) as db:
            return db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    except sqlite3.DatabaseError:
        return False

def _open_job_problems(db_path: Path, mrels) -> list:
    """One {job, why} per open NPP job that cannot resume: an original it reads (its photo_sha or an attachment of its
    stored request, via npp.job.job_photos) is not in the backup's media, or its request cannot be read. Empty means all
    resumable; no open jobs means empty. Any doubt (database unreadable) is a problem: fail closed."""
    have = {m[1] for r in mrels if (m := re.fullmatch(rf"{ORIG}[0-9a-f]{{2}}/([0-9a-f]{{64}})\.(?!json$)\w+", r))}
    problems = []
    try:
        with _connect_ro(db_path) as db:
            db.row_factory = sqlite3.Row
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'npp_jobs'").fetchone(): return []
            for job in db.execute("SELECT job_id, photo_sha, open_request_id FROM npp_jobs WHERE closed_at IS NULL ORDER BY rowid").fetchall():
                try:
                    missing = [sha for sha in job_photos(db, job) if sha not in have]
                    why = f"original missing: {', '.join(sha[:12] for sha in missing[:3])}" if missing else None
                except (ValueError, TypeError, KeyError, RecursionError) as exc:
                    why = str(exc) or "request unreadable"
                if why: problems.append({"job": str(job["job_id"]), "why": why})
    except sqlite3.DatabaseError: return [{"job": None, "why": "database unreadable"}]  # completeness cannot be established
    return problems

def _config_worktree(path: Path):  # the worktree a hashed config.json names, else None; never raises
    try: cfg = json.loads(_read_small(path, editor.MAX_CONFIG).decode("utf-8"))  # restore merges it as a dict, rewrites worktree
    except (OSError, ValueError, RecursionError): return None
    wt = cfg.get("worktree") if isinstance(cfg, dict) else None
    return wt if isinstance(wt, str) and wt != "" and "\x00" not in wt else None  # a NUL path can't be resolved (restore would crash)

def _config_ok(path: Path) -> bool: return _config_worktree(path) is not None

def verify(backup) -> dict:
    bdir = Path(backup).absolute()
    if bdir.is_symlink() or not bdir.is_dir(): return {"result": "corrupt", "problems": ["not a backup dir"]}
    doc = _manifest(bdir)
    if doc is None: return {"result": "corrupt", "problems": [f"{MANIFEST} missing or invalid"]}
    files, seen, problems = doc["files"], set(), []
    walkable = set(DIRS) | {"clover", RECEIPT_DIR} | ({"media", ORIG[:-1], NPP[:-1]} if "media" in doc else set())
    if stat.S_IMODE(bdir.stat().st_mode) != 0o700: problems.append("mode: backup dir")
    def walk(path: Path, prefix: str) -> None:
        for entry in sorted(os.scandir(path), key=lambda e: e.name):
            rel, mode = prefix + entry.name, entry.stat(follow_symlinks=False).st_mode
            if stat.S_ISLNK(mode): problems.append(f"symlink: {rel}")
            elif stat.S_ISDIR(mode) and (rel in walkable
                                         or prefix == ORIG and re.fullmatch("[0-9a-f]{2}", entry.name)
                                         or prefix == NPP and "media" in doc and re.fullmatch(JOB_RE, entry.name)):
                if stat.S_IMODE(mode) != 0o700: problems.append(f"mode: {rel}")
                walk(Path(entry.path), rel + "/")
            elif not stat.S_ISREG(mode) or (rel not in files and rel != MANIFEST): problems.append(f"unlisted: {rel}")
            else:
                seen.add(rel)
                if stat.S_IMODE(mode) != 0o600: problems.append(f"mode: {rel}")
    walk(bdir, "")
    for rel, digest in sorted(files.items()):
        if rel not in seen: problems.append(f"missing: {rel}")
        elif rel.startswith(NPP):
            try: actual = hashlib.sha256(read_artifact(bdir / rel)).hexdigest()
            except (OSError, ValueError, RecursionError): problems.append(f"invalid NPP artifact: {rel}")
            else:
                if actual != digest: problems.append(f"hash mismatch: {rel}")
        elif fallback := re.fullmatch(FALLBACK_JPEG, rel):
            try: _read_fallback(bdir / rel, fallback[1])
            except (OSError, ValueError): problems.append(f"invalid fallback picture: {rel}")
            if fallback[1] != digest: problems.append(f"hash mismatch: {rel}")
        elif hashlib.sha256(_read(bdir / rel)).hexdigest() != digest: problems.append(f"hash mismatch: {rel}")
        elif rel in STORES and not _intact(bdir / rel): problems.append(f"integrity check failed: {rel}")
        elif rel == CONFIG and (cfg_wt := _config_worktree(bdir / rel)) is None:
            problems.append("config: not a JSON object with a worktree")
        elif rel == CONFIG and cfg_wt != doc["worktree"]: problems.append("config: worktree does not match manifest")
        elif rel == BUNDLE and "contentCommit" not in doc: problems.append("content bundle without contentCommit")
        elif rel == BUNDLE and not _bundle_holds(bdir / rel, doc["contentCommit"]):
            problems.append("content bundle: head is not contentCommit")
        elif rel.startswith(ORIG) and not rel.endswith(".json"):  # the content address and the sidecar both hold
            sha, side = rel[19:83], rel[:84] + "json"  # media/originals/<aa>/<sha>.<ext>
            if hashlib.sha256(_read(bdir / rel)).hexdigest() != sha: problems.append(f"content mismatch: {rel}")
            if not (side in seen and _sidecar_sha(bdir / side) == sha): problems.append(f"sidecar mismatch: {rel}")
    problems += _pair_problems(doc)
    return {"result": "corrupt", "problems": problems} if problems else {"result": "ok", "files": len(files)}

def _pair_problems(doc) -> list:
    """Listed media in both directions: every sha has exactly one original and one sidecar, and media.originals
    equals the number of those complete pairs (a listed orphan sidecar or original is never restored as a store)."""
    pairs, problems, complete = {}, [], 0
    for rel in doc["files"]:
        if rel.startswith(ORIG): pairs.setdefault(rel[19:83], []).append(rel)
    for _, rels in sorted(pairs.items()):
        if sorted(rel.endswith(".json") for rel in rels) == [False, True]: complete += 1
        else: problems += [f"unpaired: {rel}" for rel in sorted(rels)]
    if "media" not in doc and not pairs and not any(rel.startswith(NPP) for rel in doc["files"]): return problems
    count = doc["media"].get("originals") if isinstance(doc.get("media"), dict) else None
    if type(count) is not int or count != complete: problems.append("media count mismatch")
    return problems

def _sidecar_sha(path: Path):
    try: return json.loads(_read_small(path, SMALL_MAX).decode("utf-8")).get("sha256")
    except (OSError, ValueError, AttributeError, RecursionError): return None

def _pause(path: Path, now) -> str:  # restore --paused, before the dir appears; an older pause keeps its set_at
    if not path.exists(): _write_new(path, b"")
    with contextlib.closing(sqlite3.connect(path)) as db, db:
        db.execute(CONTROL)
        db.execute("INSERT OR IGNORE INTO control(name, value, set_at, provider_id) VALUES ('paused', '1', ?, "
                   "'statebackup-restore')", (_iso(now or datetime.now(timezone.utc)),))
        since = db.execute("SELECT set_at FROM control WHERE name = 'paused'").fetchone()[0]
    os.chmod(path, 0o600)
    return since

def _clone_content(bundle: Path, tmp: Path, commit: str) -> None:  # from the backup's bundle alone; no remote kept
    for cwd, *args in ((tmp.parent, "clone", "--quiet", "--no-checkout", "--no-hardlinks", str(bundle), str(tmp)),
                       (tmp, "checkout", "--quiet", "--detach", commit), (tmp, "remote", "remove", "origin")):
        run = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                             env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        if run.returncode: raise OSError(f"git {args[0]} failed: {run.stderr.strip()[-300:]}")  # all-or-nothing
    if _head(tmp) != commit: raise OSError("content checkout HEAD is not contentCommit")

def _site_check(top: Path) -> str:  # the restored checkout's own sitegen --check, run in it; -B: it stays clean
    try: code = subprocess.run([sys.executable, "-B", "hass/sitegen.py", "--check"], cwd=top,
                               capture_output=True).returncode
    except OSError: return "failed"
    return "ok" if code == 0 else "failed"

def restore(backup, into, worktree, paused=False, now=None, media_into=None, content_into=None) -> dict:
    checked = verify(backup)
    if checked["result"] != "ok": return {"result": "corrupt", "problems": checked["problems"]}
    bdir = Path(backup).absolute()
    doc = _manifest(bdir)
    if doc is None: return {"result": "corrupt", "problems": [f"{MANIFEST} missing or invalid"]}
    mrels = [rel for rel in doc["files"] if rel.startswith(MEDIA)]
    if os.path.lexists(into): return {"result": "refused", "problems": ["restore dir already exists; left untouched"]}
    if not worktree: return {"result": "refused", "problems": ["--worktree (a separate drill worktree) is required"]}
    if media_into is not None and (not mrels or os.path.lexists(os.path.abspath(media_into))):
        return {"result": "refused", "problems": ["media restore dir already exists; left untouched" if mrels
                                                  else "no media in backup"]}
    if content_into is not None and (BUNDLE not in doc["files"] or os.path.lexists(os.path.abspath(content_into))):
        return {"result": "refused", "problems": ["content restore dir already exists; left untouched"
                                                  if BUNDLE in doc["files"] else "no content bundle in backup"]}
    target, wt, recorded = Path(into).resolve(), Path(worktree).resolve(), Path(doc["worktree"]).resolve()
    if wt == recorded: return {"result": "refused", "problems": [ATTENDED]}
    if problems := editor.worktree_problems(wt, recovering=True): return {"result": "refused", "problems": problems}
    if _inside(target, _roots(wt) + [recorded, bdir.resolve()]):
        raise UnsafeState("restore dir must lie outside the backup, the repository and the worktrees")
    mtarget = None if media_into is None else Path(media_into).resolve()
    if mtarget and _inside(mtarget, _roots(wt) + [recorded, bdir.resolve(), target]):
        raise UnsafeState("media restore dir must lie outside the backup, the repository, the worktrees and the state")
    ctarget = None if content_into is None else Path(content_into).resolve()
    if ctarget and _inside(ctarget, _roots(wt) + [recorded, bdir.resolve(), target] + ([mtarget] if mtarget else [])):
        raise UnsafeState("content restore dir must lie outside the backup, repository, worktrees, state and media")
    tmp = target.parent / f".{target.name}.restore-{os.getpid()}"
    mtmp = mtarget and mtarget.parent / f".{mtarget.name}.restore-{os.getpid()}"
    ctmp = ctarget and ctarget.parent / f".{ctarget.name}.restore-{os.getpid()}"
    tmp.mkdir(mode=0o700)
    made, renamed, mrenamed, npp_off = [tmp], False, False, []
    try:
        os.chmod(tmp, 0o700)
        if mtmp:
            mtmp.mkdir(mode=0o700)
            made.append(mtmp)
            (mtmp / "originals").mkdir(mode=0o700)
        for rel in sorted(doc["files"]):
            if rel == BUNDLE or rel.startswith(MEDIA) and not mtmp: continue  # bundle: FAV-08; media: mediaRestored
            dst = mtmp / rel[len("media/"):] if rel.startswith(MEDIA) else tmp / rel
            _private_dirs(dst.parent)
            if fallback := re.fullmatch(FALLBACK_JPEG, rel):
                _write_new(dst, _read_fallback(bdir / rel, fallback[1]))
                continue
            if rel != CONFIG:
                _copy(bdir / rel, dst)
                continue
            cfg = {**json.loads(_read(bdir / CONFIG).decode("utf-8")), "worktree": str(wt)}
            if isinstance(cfg.get("settings"), dict) and cfg["settings"].get("npp"):
                # A drill with no media, or media missing any original an open job reads, must not run NPP.
                npp_off = _open_job_problems(bdir / DB, mrels if mtarget else [])
                keep = mtarget and not npp_off
                cfg["settings"] = {**cfg["settings"], **({"mediaRoot": str(mtarget)} if keep else {"npp": False})}
            _write_new(tmp / CONFIG, json.dumps(cfg, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        if ctmp:
            ctmp.mkdir(mode=0o700)
            made.append(ctmp)
            _clone_content(bdir / BUNDLE, ctmp, doc["contentCommit"])
        extra = {"paused": True, "pausedSince": _pause(tmp / DB, now)} if paused else {}
        if os.path.lexists(target): raise FileExistsError(f"restore dir appeared during restore: {target}")
        _rename_noreplace(tmp, target)  # atomic: a dir that appeared since (even empty) is refused, never replaced
        renamed = True
        if mtmp and os.path.lexists(mtarget): raise FileExistsError(f"media restore dir appeared: {mtarget}")
        if mtmp: _rename_noreplace(mtmp, mtarget)
        mrenamed = bool(mtmp)
        if ctmp and os.path.lexists(ctarget): raise FileExistsError(f"content restore dir appeared: {ctarget}")
        if ctmp: _rename_noreplace(ctmp, ctarget)  # a dir that appeared since (even empty) is refused, never replaced
    except BaseException:
        if renamed: os.rename(target, tmp)  # take back the state dir this call made: leave neither target
        if mrenamed: os.rename(mtarget, mtmp)
        for path in made: shutil.rmtree(path, ignore_errors=True)  # only the temp dirs this call created
        raise
    if mrels: extra.update({"mediaRestored": bool(mtarget), "media": sum(rel.startswith(ORIG) for rel in mrels) // 2})
    if ctarget: extra.update({"contentRestored": True, "contentCheck": _site_check(ctarget)})  # failed: dir kept
    if npp_off: extra["nppOff"] = npp_off  # NPP was on but is now off: which open job cannot resume, and why
    return {"result": "ok", "state": str(target), "worktree": str(wt), "files": len(doc["files"]),
            "contentCommit": doc.get("contentCommit"), **extra}

STRUCTURAL = ("state", "settings", "db-integrity", "inbox-integrity")  # a drill fails on these health checks

def drill(backup, into, worktree, media_into=None, now=None, content_into=None) -> dict:
    """verify, restore --paused into a NEW dir, then the read-only health check and history on it; ids/counts only."""
    checked = verify(backup)
    if checked["result"] != "ok": return {"result": "corrupt", "step": "verify", "problems": checked["problems"]}
    out = restore(backup, into, worktree, paused=True, now=now, media_into=media_into, content_into=content_into)
    if out["result"] != "ok": return {**out, "step": "restore"}
    from hass import health  # lazy: health imports this module at its top
    problems, info, unsafe = health.check(out["state"], now=now)
    ids = sorted({p["check"] for p in problems})
    try: hist = editor.history(5, state=out["state"])
    except UnsafeState: hist = {"result": "unsafe-state"}
    step = "health" if unsafe or set(ids) & set(STRUCTURAL) else "history" if hist.get("result") != "ok" \
        else "content" if out.get("contentCheck") == "failed" else None
    return ({"result": "drill-failed", "step": step} if step else {"result": "ok"}) | {
        "state": out["state"], "worktree": out["worktree"], "files": out["files"], "paused": out["paused"],
        "contentCommit": out["contentCommit"], "health_problems": ids, "health_info": sorted({p["check"] for p in info}),
        "history": len(hist.get("history") or []),
        **{k: out[k] for k in ("media", "mediaRestored", "contentRestored", "contentCheck", "nppOff") if k in out}}

NAME_RE = re.compile(r"hass-state-[0-9]{8}T[0-9]{6}Z")  # create()'s folder name; the name is the UTC time
def _listed(entry):  # (manifest doc or None, problem or None); a symlink is never followed
    if entry.is_symlink(): return None, "symlink"
    if not entry.is_dir(follow_symlinks=False): return None, "not a folder"
    try: os.lstat(Path(entry.path, MANIFEST))
    except FileNotFoundError: return None, "no manifest (interrupted)"  # create() writes MANIFEST.json last
    except OSError: return None, "manifest invalid"
    return (doc := _manifest(Path(entry.path))), None if doc else "manifest invalid"

def list_backups(out):
    """list: one dict per hass-state-* entry, newest first. Read-only; no content hashing (that is verify)."""
    if not out or os.path.islink(re.sub(r"(/\.?)+$", "", out) or "/") or not os.path.isdir(out):  # 'link/' = link
        return {"result": "refused", "problems": ["--out must be a folder, not a link"]}
    rows = []
    for entry in sorted((e for e in os.scandir(out) if NAME_RE.fullmatch(e.name)), key=lambda e: e.name, reverse=True):
        doc, problem = _listed(entry)
        created = (doc or {}).get("createdAt")
        rows.append({"backup": entry.name, "createdAt": created if isinstance(created, str) else None,
                     "files": len(doc["files"]) if doc else None, "complete": doc is not None, "problem": problem,
                     "contentCommit": (doc or {}).get("contentCommit")})
    return rows

def diff(old, new) -> dict:
    """Two manifests compared by rel and recorded hash; no sqlite file is opened, nothing hashed, linked or written."""
    docs, problems = [], []
    for label, raw in (("OLD", old), ("NEW", new)):
        bdir = Path(raw).absolute()  # 'link/' is the link itself: refused, never followed
        if bdir.is_symlink() or not bdir.is_dir(): problems.append(f"{label}: not a backup dir")
        elif (doc := _manifest(bdir)) is None: problems.append(f"{label}: {MANIFEST} missing or invalid")
        else: docs.append(doc)
    if problems: return {"result": "corrupt", "problems": problems}
    (a, b), when = (d["files"] for d in docs), [d.get("createdAt") for d in docs]
    def rels(files, keep): return sorted(r for r in files if not r.startswith(ORIG) and keep(r))  # media never named
    def originals(files, other): return sum(r.startswith(ORIG) and not r.endswith(".json") and r not in other
                                            for r in files)
    try: order = {"order": "reversed"} if datetime.fromisoformat(when[0]) > datetime.fromisoformat(when[1]) else {}
    except (TypeError, ValueError): order = {"order": "unknown"}  # missing, odd or naive-vs-aware createdAt
    stamp = [w if isinstance(w, str) else None for w in when]
    commits = [d.get("contentCommit") for d in docs]
    return {"result": "ok", "added": rels(b, lambda r: r not in a), "removed": rels(a, lambda r: r not in b),
            "changed": rels(a, lambda r: r in b and a[r] != b[r]), "same": sum(a[r] == b.get(r) for r in a),
            "media_added": originals(b, a), "media_removed": originals(a, b), "older": stamp[0], "newer": stamp[1],
            "worktree_changed": docs[0]["worktree"] != docs[1]["worktree"], **order,
            "content_commit_changed": None if None in commits else commits[0] != commits[1]}

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/statebackup.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, params in (("create", ["--state", "--out"]), ("verify", ["backup"]), ("list", ["--out"]),
                         ("diff", ["old", "new"]),
                         ("drill", ["backup", "--into", "--worktree"]),  # before restore: --paused stays restore's
                         ("restore", ["backup", "--into", "--worktree"])):
        cmd = sub.add_parser(name)
        for param in params: cmd.add_argument(param, **({"required": True} if param.startswith("--") else {}))
    cmd.add_argument("--paused", action="store_true")  # restore only (the last parser)
    cmd.add_argument("--media-into")
    sub.choices["drill"].add_argument("--media-into")
    for name in ("restore", "drill"): sub.choices[name].add_argument("--content-into")
    sub.choices["create"].add_argument("--media")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "list":
            rows = list_backups(args.out)
            for row in [rows] if isinstance(rows, dict) else rows: print(json.dumps(row, ensure_ascii=False))
            return 2 if isinstance(rows, dict) else 0  # refused: --out missing or a link
        out = create(args.state, args.out, media=args.media) if args.cmd == "create" else verify(args.backup) \
            if args.cmd == "verify" else diff(args.old, args.new) if args.cmd == "diff" \
            else drill(args.backup, args.into, args.worktree, args.media_into, content_into=args.content_into) \
            if args.cmd == "drill" else restore(args.backup, args.into, args.worktree, paused=args.paused,
                                                media_into=args.media_into, content_into=args.content_into)
    except UnsafeState as exc:
        print(json.dumps({"result": "unsafe-state", "problems": [str(exc)]}))
        return 2
    except OSError as exc:
        out = {"result": "error", "problems": [f"{type(exc).__name__}: {exc.strerror or exc}"]}
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return 0 if out["result"] == "ok" and out.get("contentCheck") != "failed" else 1

if __name__ == "__main__":
    sys.exit(main())
