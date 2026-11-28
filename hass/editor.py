"""Hass private typed editing service (H02): drafts, revision hash, single writer.

    python3 hass/editor.py init --state DIR --worktree WT | prepare REQUEST.json
    python3 hass/editor.py apply CHANGE_ID --hash DRAFT_HASH | show CHANGE_ID | recover | ops | history [--limit N]
    python3 hass/editor.py install CHANGE_ID   # separate step: copy an applied commit's site files to site_dir
prepare binds typed ops to the content revision; apply (internal caller only) locks, re-checks worktree and revision,
writes only owned paths, runs the H01 checks and commits signed off. No listener, no push. One JSON object out.
I/O errors: result io-error, exit 2 (history lists a corrupt change record as state unreadable).
"""
import argparse, contextlib, copy, errno, fcntl, hashlib, json, os, re, stat, subprocess, sys  # noqa: E401
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import design_check, migration_check, sitegen, template_compat  # noqa: E402
from hass.content_model import IMAGE_RE, REPO_ROOT, ContentError, load_and_validate, validate  # noqa: E402
from hass.field_words import field_list  # noqa: E402
from hass.ops import (  # noqa: E402
    NeedsDetails, NotFound, OpContext, Refused, check_args, has_control_chars, load_registry)

CONTENT_PATHS = tuple(f"hass/content/{n}.json" for n in ("products", "makers", "community", "store"))
HOME_PARTS = tuple(f"hass/templates/home/{n}.html" for n in (  # AVB-19-B1: the home/hike page parts (sitegen.front_parts)
    "banner", "footer", "hike-footer", "hike-nav", "market", "nav", "newsletter", "our-way", "strip", "visit"))
INFO_PATHS = tuple(page + "/index.html" for page in sitegen.INFO_PAGES)
REVISION_PATHS = tuple(sorted(CONTENT_PATHS + HOME_PARTS + ("hass/templates/index.html", "hass/templates/hike/index.html",
                                                        "hass/templates/info/index.html")))
GENERATED_PATHS = tuple(sitegen.SITE_PREFIX + n for n in (
    "catalog-products.js", "producers.js", "producers.json", "community.json", "index.html", "hike/index.html") + INFO_PATHS)
OWNED_PATHS = CONTENT_PATHS + GENERATED_PATHS
COLLECTION_FILE = dict(products="products", makers="makers", events="community", routeIdeas="community", store="store", club="community")
MAX_REQUEST, MAX_OPS = 64 * 1024, 20
CHANGE_ID_RE = re.compile(r"chg-[0-9a-f]{12}")
LOOK_BRANCH = re.compile(r"look/[a-z0-9][a-z0-9-]{0,23}")  # hass/look_change.py's branch names

class UnsafeState(Exception): """The state dir is missing, shared, foreign-owned or inside a checkout (CLI exit 2)."""

def content_revision(root, *, previous=False) -> str:
    """previous=True: the revision as it was before a recorded template edit (hass.template_compat), or "" if none applies."""
    digest, used = hashlib.sha256(), False
    for rel in REVISION_PATHS:
        data = (Path(root) / rel).read_bytes()
        if previous and (old := template_compat.previous_bytes(rel, data)) is not None: data, used = old, True
        digest.update(rel.encode() + b"\0" + str(len(data)).encode() + b"\0" + data)
    return "sha256:" + digest.hexdigest() if used or not previous else ""

def _now(now=None) -> str:
    return (now if now is not None else datetime.now(timezone.utc)).isoformat()

def _git(wt, *args):
    return subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True)

def _out(wt, *args) -> str:
    return _git(wt, *args).stdout.strip()

def _read(path: Path):
    return json.loads(path.read_text("utf-8"))

def _write_json(path: Path, obj) -> None:
    data = json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
    path.parent.mkdir(mode=0o700, exist_ok=True)
    sitegen.write_files({path.name: data}, path.parent)
    os.chmod(path, 0o600)

def _common_dir(wt: Path) -> Path:
    return (wt / _out(wt, "rev-parse", "--git-common-dir")).resolve()

def open_state(state=None, worktree=None, *, create=True) -> Path:
    raw = state or os.environ.get("HASS_STATE_DIR")
    if not raw: raise UnsafeState("a state dir is required (--state DIR or HASS_STATE_DIR)")
    path = Path(raw).resolve()
    if not path.exists():
        if not create: raise UnsafeState("state dir is not initialised; run init first")
        path.mkdir(mode=0o700, parents=True)
    st = path.stat()
    if not path.is_dir() or st.st_uid != os.getuid(): raise UnsafeState("state dir must be owned by the current user")
    if st.st_mode & 0o077: raise UnsafeState("state dir must not be group/other accessible (use mode 0700)")
    roots = [REPO_ROOT.resolve()]
    if worktree is not None:
        wt = Path(worktree).resolve()
        roots += [wt, _common_dir(wt).parent] if _git(wt, "rev-parse").returncode == 0 else [wt]
    if any(path == root or root in path.parents for root in roots):
        raise UnsafeState("state dir must lie outside the repository and the writer worktree")
    return path

MAX_CONFIG = 1024 * 1024

def _read_config(path: Path) -> dict:
    """H20: a regular, non-link file <= 1 MiB holding an object with a non-empty string worktree, else UnsafeState."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        raise UnsafeState("state dir is not initialised; run init first") from None
    bad = UnsafeState("state config is unreadable")  # never the path or the file's bytes
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_CONFIG: raise bad  # link, FIFO, socket, folder, too big
    with open(path, "rb") as fh:
        data = fh.read(MAX_CONFIG + 1)
    try:
        cfg = json.loads(data.decode("utf-8")) if len(data) <= MAX_CONFIG else None
    except (UnicodeDecodeError, ValueError, RecursionError):
        cfg = None
    if not isinstance(cfg, dict) or not isinstance(cfg.get("worktree"), str) or not cfg["worktree"]: raise bad
    return cfg

def _load(state, *, create=True):
    sdir = open_state(state, create=create)
    cfg = _read_config(sdir / "config.json")
    open_state(str(sdir), cfg["worktree"], create=create)
    return sdir, cfg, Path(cfg["worktree"])

def worktree_problems(wt: Path, recovering=False) -> list[str]:
    """Fail-closed writer preconditions: linked worktree, named non-main branch (enough to recover), clean, identity."""
    top = _git(wt, "rev-parse", "--show-toplevel")
    if top.returncode or Path(top.stdout.strip()).resolve() != wt.resolve() or not (wt / "hass/content").is_dir():
        return ["writer worktree is not the top of a Hass Git checkout"]
    if Path(_out(wt, "rev-parse", "--absolute-git-dir")).resolve() == _common_dir(wt):
        return ["the main checkout is refused; use a linked writer worktree"]
    branch = _git(wt, "symbolic-ref", "-q", "--short", "HEAD")
    problems = ["detached HEAD is refused"] if branch.returncode else \
        ["branch main is refused"] if branch.stdout.strip() == "main" else []
    if recovering: return problems
    status = _git(wt, "status", "--porcelain")
    if status.returncode: problems.append("git status failed")
    elif status.stdout.strip(): problems.append("writer worktree has uncommitted changes")
    problems += [f"git {key} is not configured" for key in ("user.name", "user.email") if not _out(wt, "config", key)]
    return problems

def init(state, worktree) -> dict:
    wt = Path(worktree).resolve()
    sdir = open_state(state, wt)
    if problems := worktree_problems(wt): return {"result": "refused", "problems": problems}
    _write_json(sdir / "config.json", {"worktree": str(wt), "settings": {}})
    return {"result": "ok", "worktree": str(wt)}

def _unique_members(pairs):
    """RF0540-10: a repeated member in any request object (equal, conflicting or escaped alike) is ambiguous: refuse it,
    never draft last-key-wins. Fixed text only; the offending key and value are not echoed."""
    out = {}
    for key, value in pairs:
        if key in out: raise ValueError("duplicate JSON member")
        out[key] = value
    return out

def _parse_request(request):
    try:
        raw = request if isinstance(request, (bytes, str)) else json.dumps(request, ensure_ascii=False)
        raw = raw.encode("utf-8") if isinstance(raw, str) else raw
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_members) if len(raw) <= MAX_REQUEST else None
        json.dumps(doc, ensure_ascii=False).encode("utf-8")  # escaped lone surrogates cannot be stored or rendered
    except (ValueError, RecursionError) as exc:  # RF1920-5: nested too deep is not valid JSON, never a traceback
        return None, ["request has unpaired surrogate characters" if isinstance(exc, UnicodeEncodeError)
                      else "request is not valid JSON"]
    if len(raw) > MAX_REQUEST: return None, ["request is larger than 64 KiB"]
    if not isinstance(doc, dict) or set(doc) != {"ops"}: return None, ['request must be {"ops": [...]} only']
    ops = doc["ops"]
    if not isinstance(ops, list) or not 1 <= len(ops) <= MAX_OPS:
        return None, [f"ops must be a list of 1-{MAX_OPS} operations"]
    try: control = has_control_chars(doc)
    except RecursionError: return None, ["request is not valid JSON"]  # json parsed it, but too deep to walk
    if control: return None, ["control characters are not allowed"]
    return ops, [f'ops[{i}]: must be {{"op": name, "args": {{...}}}}' for i, call in enumerate(ops)
                 if not isinstance(call, dict) or set(call) != {"op", "args"} or not isinstance(call["op"], str)
                 or not isinstance(call["args"], dict)]

def _serialize(content, name: str) -> bytes:
    doc = {"products": {"schemaVersion": 1, "products": content.products},
           "makers": {"schemaVersion": 1, "makers": content.makers},
           "community": {"schemaVersion": 1, **content.community}, "store": content.store}[name]
    return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

def _compute(ops, wt: Path, settings, registry, now, sdir=None) -> dict:
    site, registry = wt / "storefront-mockup", load_registry() if registry is None else registry
    content = load_and_validate(wt / "hass" / "content", site)
    problems, missing = [], []
    provisional = dict(content.makers)  # AV1937-02: current makers plus keys of clean maker.add calls EARLIER in this list
    for i, call in enumerate(ops):
        op = registry.get(call["op"])
        found, absent = check_args(op, call["args"], provisional, site) if op else (["unknown op"], [])
        problems += [f"ops[{i}] {call['op']!r}: {p}" for p in found]
        missing += [name for name in absent if name not in missing]
        if op and call["op"] == "maker.add" and not found and not absent:
            provisional.setdefault(call["args"]["key"], {})  # provisional membership only; the real add may still refuse
    if problems: return {"result": "invalid", "problems": problems}
    if missing:
        return {"result": "needs-details", "missing": missing, "question": "Please provide: " + field_list(missing)}
    base, new = content_revision(wt), copy.deepcopy(content)
    ctx = OpContext(now or datetime.now(timezone.utc), site, MappingProxyType(dict(settings)), state_dir=sdir)
    records, summary = [], []
    for i, call in enumerate(ops):
        found, absent = check_args(registry[call["op"]], call["args"], new.makers, site)  # against what earlier ops really did
        if found: return {"result": "invalid", "problems": [f"ops[{i}] {call['op']!r}: {p}" for p in found]}
        if absent:
            return {"result": "needs-details", "missing": absent, "question": "Please provide: " + field_list(absent)}
        out = registry[call["op"]].apply(new, copy.deepcopy(call["args"]), ctx)
        if isinstance(out, NeedsDetails):
            return {"result": "needs-details", "missing": list(out.missing), "question": out.question}
        if isinstance(out, NotFound): return {"result": "not-found", "key": out.key}
        if isinstance(out, Refused): return {"result": "refused", "reason": out.reason}
        records += [asdict(t) for t in out]
        summary.append(f"{call['op']}: " + (", ".join(f"{t.collection}/{t.key}" for t in out) or "no records"))
    if bad := [p for p in ctx.assets if not IMAGE_RE.fullmatch(p) or ".." in p]:
        return {"result": "refused", "reason": f"photo path is not assets/products/<file>: {bad[0]}"}
    if ctx.assets and not (site / "assets/products").resolve().is_relative_to(wt.resolve()):
        return {"result": "refused", "reason": "the photo folder is outside the writer worktree"}
    try:
        validate(new, site)
    except ContentError as exc:  # a photo this change adds is not on disk until apply writes it
        missing_photo = [f"image file {a} does not exist" for a in ctx.assets]
        if rest := [p for p in exc.problems if not any(p.endswith(m) for m in missing_photo)]:
            raise ContentError(rest) from None
    files = sitegen.render(new, wt / "hass" / "templates")
    generated = sitegen.diff_paths(files, wt)
    names = sorted({COLLECTION_FILE[r["collection"]] for r in records})
    writes = {f"hass/content/{n}.json": _serialize(new, n) for n in names}
    writes = {p: data for p, data in writes.items() if (wt / p).read_bytes() != data}
    writes.update({p: files[p] for p in generated})
    writes.update({sitegen.SITE_PREFIX + p: data for p, data in ctx.assets.items()})
    if not writes: return {"result": "refused", "reason": "the operations change nothing"}
    assets = {p: "sha256:" + hashlib.sha256(data).hexdigest() for p, data in sorted(ctx.assets.items())}  # SKILLS-PIC-1
    return {"result": "ok", "base": base, "records": records, "generated": generated, "assets": assets,
            "warnings": list(ctx.warnings), "summary": summary, "writes": writes, "files": files, "store": new.store}

def _design_call(sdir: Path, ops):
    """HASS-SITE-LOOK-1b: the one call of a design draft (design.apply, or history.revert of a design change), else None."""
    call = ops[0] if len(ops) == 1 else {}
    cid = str((call.get("args") or {}).get("changeId"))
    if call.get("op") == "history.revert" and CHANGE_ID_RE.fullmatch(cid):
        try:
            rec = sdir / "changes" / f"{cid}.json"
            st = os.lstat(rec)
            if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_CONFIG: return None  # link, FIFO, socket, folder, too big: never opened
            return call if _read(rec).get("kind") == "design" else None
        except (OSError, ValueError, AttributeError, RecursionError): return None  # the history op names an unreadable record
    return call if call.get("op") == "design.apply" else None

def _design_compute(call, wt: Path, sdir: Path) -> dict:
    """Check a design draft against writer HEAD; nothing is written. design.apply lands the approved look/<code> head (a LOOK-1
    `ok` result: its one parent must be HEAD and design_check must say ok); its undo reverts exactly that commit (still HEAD)."""
    refuse = lambda reason: {"result": "refused", "reason": reason}  # noqa: E731
    head, args = _out(wt, "rev-parse", "HEAD"), call["args"]
    if call["op"] == "history.revert":
        cid = args["changeId"]
        rec, draft = _read(sdir / "changes" / f"{cid}.json"), _read(sdir / "drafts" / f"{cid}.json")
        if rec.get("state") != "applied" or rec.get("revertedBy"): return refuse(f"{cid} is not an applied change that can be undone")
        if any(c.get("op") == "history.revert" for c in draft.get("ops", [])):
            return refuse(f"{cid} is an undo; to bring the change back, ask for it again")
        if rec.get("commit") != head: return refuse(f"conflict: the website files changed after {cid}")
        land, paths = ("revert", head), _out(wt, "diff-tree", "--no-commit-id", "--name-only", "--no-renames", "-r", head).splitlines()
        problems = [p for p in paths if p not in design_check.DESIGN]
    else:
        if set(args) != {"branch", "base", "head"} or not all(isinstance(v, str) for v in args.values()) \
                or not LOOK_BRANCH.fullmatch(args["branch"]):
            return refuse("design.apply needs the branch, base and head of an ok look draft")
        if _out(wt, "rev-parse", "-q", "--verify", f"refs/heads/{args['branch']}^{{commit}}") != args["head"]:
            return refuse("the look branch is not at the approved look head")
        if args["base"] != head or _out(wt, "rev-list", "--parents", "-n", "1", args["head"]).split() != [args["head"], head]:
            return {"result": "stale", "problems": ["the look draft was not made on the current writer HEAD"]}
        try: count, problems = design_check.check(head, args["head"], str(wt))
        except design_check.Usage: count, problems = 0, ["the look draft could not be checked"]
        land, paths = ("cherry-pick", args["head"]), _out(wt, "diff", "--name-only", "--no-renames", head, args["head"]).splitlines()
        problems = problems or ([] if count else ["the look draft changes nothing"])
    if problems: return refuse("not only design files: " + ", ".join(problems))
    return {"result": "ok", "base": content_revision(wt), "records": [], "generated": [], "assets": {}, "warnings": [],
            "summary": [f"{call['op']}: {land[0]} {land[1]}"], "land": land, "paths": sorted(paths)}

def _draft_hash(draft):
    seed = {k: draft[k] for k in ('base', 'ops')}
    for key in ('environment', 'assets'):
        if key in draft: seed[key] = draft[key]
    if 'hash_attempt' in draft: seed['attempt'] = draft['hash_attempt']
    core = json.dumps(seed, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return 'sha256:' + hashlib.sha256(core.encode('utf-8')).hexdigest()

def _draft_hash_matches(draft):
    try:
        return _draft_hash(draft) == draft['draft_hash']
    except (KeyError, TypeError, ValueError, RecursionError):
        return False

def _matching_draft(path, draft):
    if path.is_symlink() or not path.is_file(): return None
    try:
        stored = _read(path)
    except ValueError:
        return None
    if (not isinstance(stored, dict) or stored.get('change_id') != draft['change_id']
            or stored.get('draft_hash') != draft['draft_hash']):
        return None
    if 'hash_attempt' in draft and 'hash_attempt' not in stored and 'environment' not in stored:
        # Legacy unbound retries omitted the attempt. Check their seed with the
        # candidate's attempt, but leave the existing file and return shape intact.
        return stored if _draft_hash_matches(dict(stored, hash_attempt=draft['hash_attempt'])) else None
    return stored if _draft_hash_matches(stored) else None

def candidate(request, *, state=None, registry=None, now=None, environment=None) -> dict:
    """Build a draft in memory. No state/worktree writes; private media caching is allowed."""
    sdir, cfg, wt = _load(state, create=False)
    ops, problems = _parse_request(request)
    if problems: return {"result": "invalid", "problems": problems}
    try:
        design = _design_call(sdir, ops)
        if design:  # a design draft is checked against a clean writer HEAD under the writer lock, as apply will (a dirty writer is refused up front)
            with _writer_lock(sdir, create=False) as held:
                if not held: return {"result": "busy"}
                if problems := worktree_problems(wt): return {"result": "refused", "problems": problems}
                out = _design_compute(design, wt, sdir)
        else: out = _compute(ops, wt, cfg.get("settings", {}), registry, now, sdir)
    except ContentError as exc:
        return {"result": "invalid", "problems": exc.problems}
    if out["result"] != "ok": return out
    draft = {"base": out["base"], "ops": ops,
             "records": out["records"], "generated": out["generated"], "warnings": out["warnings"],
             "created_at": _now(now), **({"assets": out["assets"]} if out["assets"] else {})}
    if environment is not None: draft["environment"] = copy.deepcopy(environment)
    while True:  # a recorded change id is never reused
        draft_hash = _draft_hash(draft)
        change_id = 'chg-' + draft_hash[7:19]
        if not os.path.lexists(sdir / 'changes' / f'{change_id}.json'): break
        draft['hash_attempt'] = draft.get('hash_attempt', 0) + 1
    draft.update(change_id=change_id, draft_hash=draft_hash)
    path = sdir / 'drafts' / f'{change_id}.json'
    if stored := _matching_draft(path, draft):
        draft = dict(stored, hash_attempt=draft['hash_attempt']) if 'hash_attempt' in draft else stored
    return {"result": "ok", "draft": draft}

def persist_candidate(draft, *, state=None, guard=None) -> dict:
    """Persist the validated candidate without recomputing; apply checks asset freshness."""
    stale = {'result': 'stale'}
    if not isinstance(draft, dict) or not _draft_hash_matches(draft): return stale
    cid = 'chg-' + draft['draft_hash'][7:19]
    if draft.get('change_id') != cid: return stale
    sdir, _cfg, wt = _load(state, create=False)
    with _writer_lock(sdir, create=False) as held:
        if not held: return {'result': 'busy'}
        drafts, changes = sdir / 'drafts', sdir / 'changes'
        if any(folder.is_symlink() or (folder.exists() and not folder.is_dir()) for folder in (drafts, changes)):
            return stale
        if os.path.lexists(changes / f'{cid}.json'): return stale
        try:
            if content_revision(wt) != draft['base']: return stale
        except FileNotFoundError:
            return stale
        if guard is not None: guard()
        path = drafts / f'{cid}.json'
        if os.path.lexists(path):
            stored = _matching_draft(path, draft)
            return {'result': 'ok', 'draft': stored} if stored is not None else stale
        try:
            _write_json(path, draft)
        except (TypeError, ValueError, RecursionError):
            return stale
    return {'result': 'ok', 'draft': draft}

def prepare(request, *, state=None, registry=None, now=None, environment=None) -> dict:
    out = candidate(request, state=state, registry=registry, now=now, environment=environment)
    return persist_candidate(out['draft'], state=state) if out['result'] == 'ok' else out

@contextlib.contextmanager
def _writer_lock(sdir: Path, *, create=True):
    # Share exclusion even before writer.lock exists, without creating a state
    # entry when persisting (or refusing) a draft.
    fd = os.open(sdir, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        with _file_writer_lock(sdir, create) as held:
            yield held
    finally:
        os.close(fd)

@contextlib.contextmanager
def _file_writer_lock(sdir: Path, create):
    bad = UnsafeState("writer lock is not a regular file")  # H20: never a lock created or held through a link
    try:
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        fd = os.open(sdir / "writer.lock", flags | (os.O_CREAT if create else 0), 0o600)
    except FileNotFoundError:
        if create: raise
        yield True
        return
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.EISDIR, errno.ENXIO): raise bad from None  # link, folder, FIFO/socket
        raise
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise bad
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)

def _drop_new_assets(wt: Path, paths) -> None:
    """Undo photo files a failed apply wrote: restore one HEAD has, else unstage and unlink it (no stray file left)."""
    site = sitegen.SITE_PREFIX
    for p in (p for p in paths or () if isinstance(p, str) and p.startswith(site) and IMAGE_RE.fullmatch(p[len(site):])):
        if _git(wt, "cat-file", "-e", f"HEAD:{p}").returncode == 0: _git(wt, "checkout", "HEAD", "--", p)
        else:
            _git(wt, "rm", "-q", "--cached", "--ignore-unmatch", "--", p)
            if (wt / p).parent.resolve().is_relative_to(wt.resolve()): (wt / p).unlink(missing_ok=True)

def _design_undo_problems(wt: Path, journal: dict, draft: dict) -> list[str]:
    """Interrupted design apply: refuse unless every dirty path is exactly the apply's own staged content (HEAD's or the landed
    commit's blob); else return [] after restoring just those paths (never a blanket reset --hard: it would eat unrelated edits)."""
    ops, paths = draft.get("ops") or [{}], journal.get("paths") or []
    args = (ops[0].get("args") or {}) if isinstance(ops[0], dict) else {}
    target = args.get("head") if ops[0].get("op") == "design.apply" else "HEAD^"
    blob = lambda ref, p: _out(wt, "rev-parse", "-q", "--verify", f"{ref}:{p}") if ref else ""  # noqa: E731
    dirty = [e[3:] for e in _out(wt, "status", "--porcelain", "-z", "--no-renames", "-uall").split("\0") if e]
    if not paths or not target or set(dirty) - set(paths): return ["interrupted design apply: other worktree changes; needs reconciliation"]
    def tree(ref, p):  # (mode, blob) at ref, None when absent
        r = _out(wt, "ls-tree", ref, "--", p).split()
        return (r[0], r[2]) if r else None
    def work(p):  # (mode, blob) of the worktree entry: type, exec bit and bytes/link target
        try: st = os.lstat(wt / p)
        except OSError: return None
        if stat.S_ISLNK(st.st_mode):
            d = os.fsencode(os.readlink(wt / p))
            return ("120000", hashlib.sha1(b"blob %d\0" % len(d) + d).hexdigest())
        if not stat.S_ISREG(st.st_mode): return ("?", "")
        return ("100755" if st.st_mode & 0o100 else "100644", _out(wt, "hash-object", "--", p))
    for p in dirty:
        ours = {tree("HEAD", p), tree(target, p)}
        s = _out(wt, "ls-files", "-s", "--", p).split()
        if work(p) not in ours or ((s[0], s[1]) if s else None) not in ours:
            return [f"interrupted design apply: {p} changed since the crash; needs reconciliation"]
    for p in dirty:
        if blob("HEAD", p): _git(wt, "checkout", "HEAD", "--", p)
        else:
            _git(wt, "rm", "-q", "--cached", "--ignore-unmatch", "--", p)
            (wt / p).unlink(missing_ok=True)
    return []

def _recover_locked(sdir: Path, wt: Path, now, guard=None) -> dict:
    """Resolve every journal: committed -> applied; HEAD still at base -> restore and failed. Never re-apply."""
    if problems := worktree_problems(wt, recovering=True): return {"result": "refused", "problems": problems}
    done = []
    for jpath in sorted((sdir / "journal").glob("chg-*.json")):
        cid, journal, head = jpath.stem, _read(jpath), _out(wt, "rev-parse", "HEAD")
        if guard and (problem := guard(cid)): return problem
        draft = _read(sdir / "drafts" / f"{cid}.json") if (sdir / "drafts" / f"{cid}.json").is_file() else {}
        if CHANGE_ID_RE.fullmatch(cid) and _out(wt, "log", "-1", "--format=%s") == f"hass content: {cid}":
            rec = {"state": "applied", "change_id": cid, "commit": head, "revision": content_revision(wt),
                   "recovered": True, "applied_at": _now(now), **{k: draft.get(k) for k in ("base", "records", "generated")},
                   **({"environment": draft["environment"]} if "environment" in draft else {}),
                   **({"kind": "design"} if journal.get("kind") == "design" else {})}
        elif CHANGE_ID_RE.fullmatch(cid) and head == journal.get("base_commit"):
            if journal.get("kind") == "design":  # only the interrupted apply's own files are taken back
                if problems := _design_undo_problems(wt, journal, draft): return {"result": "refused", "problems": problems}
            else: _git(wt, "checkout", "HEAD", "--", *OWNED_PATHS)
            _drop_new_assets(wt, journal.get("paths"))
            rec = {"state": "failed", "change_id": cid, "problems": ["interrupted; needs a new approval"],
                   "failed_at": _now(now)}
        else:
            done.append({"change_id": cid, "state": "unresolved"})
            continue
        _write_json(sdir / "changes" / f"{cid}.json", rec)
        if rec["state"] == "applied": _mark_reverted(sdir, draft, cid)
        jpath.unlink()
        done.append({"change_id": cid, "state": rec["state"]})
    return {"result": "ok", "recovered": done}

def recover(*, state=None, now=None, guard=None) -> dict:
    sdir, _cfg, wt = _load(state)
    with _writer_lock(sdir) as held:
        return _recover_locked(sdir, wt, now, guard) if held else {"result": "busy"}

def _post_checks(wt: Path) -> list[str]:
    try:
        content = load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
        stale = sitegen.stale_paths(content, wt)
    except ContentError as exc:
        return list(exc.problems)
    return [f"generated file out of date: {p}" for p in stale] + migration_check.run_checks(wt)[0]

def apply(change_id, draft_hash, *, state=None, registry=None, now=None, guard=None, recovery_guard=None) -> dict:
    sdir, cfg, wt = _load(state)
    if not CHANGE_ID_RE.fullmatch(str(change_id)): return {"result": "invalid", "problems": ["malformed change id"]}
    with _writer_lock(sdir) as held:
        if not held: return {"result": "busy"}
        if guard and (problem := guard()): return problem
        if (recovered := _recover_locked(sdir, wt, now, recovery_guard))["result"] != "ok": return recovered
        if any(r["state"] == "unresolved" for r in recovered["recovered"]):
            return {"result": "refused", "problems": ["an interrupted change needs reconciliation"]}
        return _apply_locked(sdir, cfg, wt, change_id, draft_hash, registry, now, guard)

def bound_hash_valid(draft):
    return isinstance(draft, dict) and 'environment' in draft and _draft_hash_matches(draft)

def _apply_locked(sdir, cfg, wt, change_id, draft_hash, registry, now, guard=None) -> dict:
    draft_path, rec_path = sdir / "drafts" / f"{change_id}.json", sdir / "changes" / f"{change_id}.json"
    if not draft_path.is_file(): return {"result": "not-found", "key": change_id}
    draft = _read(draft_path)
    if draft.get("draft_hash") != draft_hash:
        return {"result": "invalid", "problems": ["draft hash does not match the stored draft"]}
    if 'environment' in draft and not bound_hash_valid(draft):
        return {"result": "env-changed"}
    rec = _read(rec_path) if rec_path.is_file() else {}
    if rec.get("state") == "applied": return {"result": "already-applied", **rec}
    if rec: return {**rec, "result": "failed", "problems": rec["problems"] + ["prepare again and get a new approval"]}
    if problems := worktree_problems(wt): return {"result": "refused", "problems": problems}
    if (rev := content_revision(wt)) != draft["base"] and draft["base"] != content_revision(wt, previous=True): return {"result": "stale", "base": draft["base"], "current": rev}
    design = _design_call(sdir, draft["ops"])
    try:
        out = _design_compute(design, wt, sdir) if design else _compute(draft["ops"], wt, cfg.get("settings", {}), registry, now, sdir)
    except ContentError as exc:
        return {"result": "invalid", "problems": exc.problems}
    if design and out["result"] != "ok": return out  # the design check's own refusal (a moved look branch, a moved HEAD)
    if (out["result"] != "ok" or out["records"] != draft["records"] or out["generated"] != draft["generated"]
            or out["assets"] != draft.get("assets", {})):  # also the picture bytes (a setting turned on or off since prepare)
        return {"result": "stale", "problems": ["re-running the operations gave a different result"]}
    paths, journal = out["paths"] if design else sorted(out["writes"]), sdir / "journal" / f"{change_id}.json"
    if guard and (problem := guard()): return problem
    _write_json(journal, {"phase": "writing", "change_id": change_id, "paths": paths,
                          "base_commit": _out(wt, "rev-parse", "HEAD"), **({"kind": "design"} if design else {})})
    if design:  # git cherry-pick / git revert of exactly the checked commit, onto the clean HEAD it was checked against
        failed = _git(wt, out["land"][0], "--no-commit", out["land"][1]).returncode
        problems = ["git could not apply the look change"] if failed else _post_checks(wt)
    else:
        sitegen.write_files(out["writes"], wt)
        problems = _post_checks(wt)
    if not problems:
        _git(wt, "add", "--", *paths)
        message = ["-m", f"hass content: {change_id}", "-m", "\n".join(out["summary"])]
        if _git(wt, "commit", "-q", "-s", *message).returncode: problems = ["git commit failed"]
    if problems:
        _git(wt, "checkout", "HEAD", "--", *OWNED_PATHS)
        if design: _git(wt, "reset", "-q", "--hard", "HEAD")  # the worktree was checked clean: takes back only this apply's files
        _drop_new_assets(wt, paths)
        _write_json(rec_path, {"state": "failed", "change_id": change_id, "problems": problems, "failed_at": _now(now)})
        journal.unlink()
        return {"result": "failed", "problems": problems}
    rec = {"state": "applied", "change_id": change_id, "commit": _out(wt, "rev-parse", "HEAD"), "applied_at": _now(now),
           "revision": content_revision(wt), **{k: draft[k] for k in ("base", "records", "generated")},
           **({"environment": draft["environment"]} if "environment" in draft else {}), **({"kind": "design"} if design else {})}
    _write_json(rec_path, rec)
    _mark_reverted(sdir, draft, change_id)
    journal.unlink()
    return {"result": "applied", **rec}

def _mark_reverted(sdir: Path, draft: dict, change_id: str) -> None:
    """After a revert change is committed, record ``revertedBy`` on each change it undid (before returning)."""
    for call in draft.get("ops") or []:
        orig = sdir / "changes" / f"{(call.get('args') or {}).get('changeId')}.json"
        if call.get("op") == "history.revert" and orig.is_file():
            _write_json(orig, {**_read(orig), "revertedBy": change_id})

def render_draft(change_id, *, state=None, registry=None, now=None) -> dict:
    """Render a stored draft without writing state or worktree files."""
    sdir, cfg, wt = _load(state, create=False)
    path = sdir / "drafts" / f"{change_id}.json"
    if not CHANGE_ID_RE.fullmatch(str(change_id)) or not path.is_file(): return {"result": "not-found", "key": change_id}
    return _render_candidate(_read(path), sdir, cfg, wt, registry, now)

def render_candidate(draft, *, state=None, registry=None, now=None) -> dict:
    """Render in-memory ops. No state/worktree writes; private media caching is allowed."""
    sdir, cfg, wt = _load(state, create=False)
    return _render_candidate(draft, sdir, cfg, wt, registry, now)

def _render_candidate(draft, sdir, cfg, wt, registry, now):
    try:
        out = _compute(draft["ops"], wt, cfg.get("settings", {}), registry, now, sdir)
    except ContentError as exc:
        return {"result": "invalid", "problems": exc.problems}
    return {"result": "ok", "files": out["files"], "records": out["records"], "store": out["store"],
                           "assets": {k: v for k, v in out["writes"].items() if k.startswith(sitegen.SITE_PREFIX + "assets/")}} if out["result"] == "ok" else out

def history(limit=20, *, state=None) -> dict:
    """Change records newest first: id, state, applied_at, commit, one line per op, revertedBy."""
    if type(limit) is not int or not 1 <= limit <= 500: raise ValueError("limit must be 1-500")
    sdir, _cfg, _wt = _load(state)
    entries = []
    for path in (sdir / "changes").glob("chg-*.json") if (sdir / "changes").is_dir() else ():
        draft = sdir / "drafts" / path.name
        try:
            rec = _read(path)
            if not isinstance(rec, dict) or any(not isinstance(rec.get(k), (str, type(None)))
                                                for k in ("applied_at", "failed_at")):
                raise ValueError("record of the wrong shape")  # listed unreadable like a corrupt one
        except (OSError, ValueError):  # one corrupt record must not hide the others
            entries.append((("", path.stat().st_mtime_ns), {"change_id": path.stem, "state": "unreadable",
                            "applied_at": None, "commit": None, "revertedBy": None, "ops": []}))
            continue
        try:
            doc = _read(draft) if draft.is_file() else {}
        except (OSError, ValueError):
            doc = {}
        ops = doc.get("ops", []) if isinstance(doc, dict) else []
        if not isinstance(ops, list) or not all(isinstance(c, dict) and isinstance(c.get("op"), str)
                                                and isinstance(c.get("args"), dict) for c in ops):
            ops = []  # a draft of the wrong shape lists like a corrupt one
        entries.append(((rec.get("applied_at") or rec.get("failed_at") or "", path.stat().st_mtime_ns), {
            "change_id": path.stem, "state": rec.get("state"), "applied_at": rec.get("applied_at"),
            "commit": rec.get("commit"), "revertedBy": rec.get("revertedBy"), "install": install_status(rec),
            "ops": [f"{c['op']} {json.dumps(c['args'], ensure_ascii=False, sort_keys=True)}"[:160] for c in ops]}))
    entries.sort(key=lambda e: e[0], reverse=True)
    return {"result": "ok", "history": [e for _key, e in entries[:limit]]}

def show(change_id, *, state=None) -> dict:
    sdir, _cfg, _wt = _load(state)
    if not CHANGE_ID_RE.fullmatch(str(change_id)): return {"result": "invalid", "problems": ["malformed change id"]}
    for kind in ("changes", "drafts"):
        if (sdir / kind / f"{change_id}.json").is_file():
            rec = _read(sdir / kind / f"{change_id}.json")
            if not isinstance(rec, dict):  # valid JSON of the wrong shape: named, never printed or traced
                return {"result": "unreadable", "key": change_id, "kind": kind[:-1]}
            return {"result": "ok", kind[:-1]: rec, **({"install": install_status(rec)} if kind == "changes" else {})}
    return {"result": "not-found", "key": change_id}

def install_status(rec: dict) -> str | None:
    """SHOP-2: whether an applied change reached the running site (`hass/install.py`); None if not applied."""
    if rec.get("state") != "applied": return None
    inst = {} if rec.get("install") is None else rec.get("install")
    if not isinstance(inst, dict) or ("state" in inst and not isinstance(inst["state"], str)):
        return "committed, not installed (install record unreadable)"  # RF1750-1: named, never printed or traced
    if inst.get("state") == "installed": return "installed"
    return "committed, not installed" + (f" (install failed: {inst.get('reason')})" if inst.get("state") else "")

def list_ops(registry=None) -> dict:
    registry = load_registry() if registry is None else registry
    return {"result": "ok", "ops": {name: {arg: asdict(spec) for arg, spec in op.args.items()}
                                    for name, op in sorted(registry.items())}}

def _read_request_file(path) -> bytes:
    """RF1920-5: a regular file, read only up to MAX_REQUEST + 1 bytes (longer is refused as larger than 64 KiB)."""
    if stat.S_ISDIR(mode := os.stat(path).st_mode): raise IsADirectoryError  # io-error name unchanged
    if not stat.S_ISREG(mode): raise ValueError("request is not a regular file")  # FIFO/device: never opened
    with open(path, "rb") as fh: return fh.read(MAX_REQUEST + 1)

def _limit(text):
    try: n = int(text)
    except ValueError: n = 0
    if not 1 <= n <= 500: raise argparse.ArgumentTypeError("must be a whole number from 1 to 500")
    return n

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hass/editor.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state", help="private state dir (default: HASS_STATE_DIR)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, params in (("init", ["--worktree"]), ("prepare", ["request"]), ("apply", ["change_id", "--hash"]),
                         ("show", ["change_id"]), ("recover", []), ("ops", []), ("history", []),
                         ("install", ["change_id"])):
        cmd = sub.add_parser(name, parents=[common])
        for param in params:
            cmd.add_argument(param, **({"required": True} if param.startswith("--") else {}))
        if name == "history": cmd.add_argument("--limit", type=_limit, default=20)
    args = parser.parse_args(argv)
    commands = {"ops": lambda: _load(args.state) and list_ops(), "init": lambda: init(args.state, args.worktree),
                "prepare": lambda: prepare(_read_request_file(args.request), state=args.state),
                "apply": lambda: apply(args.change_id, args.hash, state=args.state),
                "show": lambda: show(args.change_id, state=args.state), "recover": lambda: recover(state=args.state),
                "history": lambda: history(args.limit, state=args.state),
                "install": lambda: __import__("hass.install").install.install(args.change_id, state=args.state)}
    try:
        out = commands[args.cmd]()
    except UnsafeState as exc:
        print(json.dumps({"result": "unsafe-state", "problems": [str(exc)]}))
        return 2
    except (OSError, ValueError) as exc:  # class name only: never a path, request body or file content
        print(json.dumps({"result": "io-error", "problems": [type(exc).__name__]}))
        return 2
    for line in out["history"] if args.cmd == "history" else [out]:  # history: one JSON line per change
        print(json.dumps(line, ensure_ascii=False, sort_keys=True))
    return 0 if out["result"] in ("ok", "applied", "already-applied", "installed", "already_installed") else 1

if __name__ == "__main__":
    sys.exit(main())
