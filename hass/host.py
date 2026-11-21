#!/usr/bin/env python3
"""HASS-RCV-1: the receiver host on AgentOrange. Subcommands (each takes --host host.json):
  serve        sealed POST /v1/inbound (store only) and POST /v1/relay (the Mac pulls replies) on a loopback or
               Tailscale address; allowedPeers only; never drains, never applies.
  work         drains the inbox through Receiver + Conversation; in `private` mode an owner `yes` is applied by the
               editor's single-writer path; every reply goes to the relay store for the Mac to pull.
  start-point  --at ISO: records the inbox start point once.
  check        validates host.json, the key file and the runtime identity; opens no socket. HASS-CLOVER-2: also the optional
               `clover` block and its token file by stat only ("clover": "not configured" | "ok" | one problem word).
  mode         MODE: HASS-LIVE-PLAN-1, the one-line switch: rewrites `approvals` (hold | private | live) in host.json, keeping it 0600,
               and refuses (changing nothing) if the result would not load. Then `systemctl --user restart hass-worker`.
Exit 0 ok, 2 config / secret / start point / runtime refused (one JSON line, field names only), 1 any other error.
Nothing prints message text, a sender, a chat id, a URL, a secret or a path.
"""
import argparse, base64, collections, contextlib, ipaddress, json, logging, os, secrets, signal, socket, socketserver, sqlite3, stat, subprocess, sys, threading, time  # noqa: E401
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import answer_reader, bridge, cloud_codex, conversation, editor as editor_mod, inbox as inbox_mod, interpreter_local, interpreter_prompt  # noqa: E402
from hass import label_reader, nl_prep, preview, receiver, relay, relay_photos, sandbox, stagelog  # noqa: E402
from hass.content_model import load_content  # noqa: E402
from hass.ops import load_registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("hass.host")
MAX_HOST_JSON, MAX_BODY, ROUTES = 64 * 1024, 64 * 1024, ("/v1/inbound", "/v1/relay", "/v1/photo")
METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH"})  # a logged method is one of these, never client text
KEYS = {"state", "secretFile", "listen", "allowedPeers", "approvals", "interpreter", "previewer", "runtimeCommit", "pictures", "photos", "release", "clover", "live", "off", "mode_gen", "looks"}
OPTIONAL = {"previewer", "pictures", "photos", "release", "clover", "live", "off", "mode_gen", "looks"}  # HASS-CLOVER-2: `clover` absent = Clover not configured; nothing else changes
PHOTO_BODY, PHOTOS_PER_MIN = 12 * 1024 * 1024, 8
PICTURES_PER_MIN = 10  # HASS-ATTACH-1: more picture requests in a minute get `gone` with no data
TAILSCALE = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))
LIVE_REASON = "live release is not installed"


class HostConfigError(Exception):
    """host.json is unusable. `fields` are field names only; `reason` is a fixed phrase or None."""
    def __init__(self, fields, reason=None):
        super().__init__(",".join(fields))
        self.fields, self.reason = list(fields), reason


class Refuse(Exception):
    def __init__(self, out):
        super().__init__(out["result"])
        self.out = out


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _private_json(path):
    try:
        st = os.lstat(path)
        ok = stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and not st.st_mode & 0o177 and st.st_size <= MAX_HOST_JSON
        data = Path(path).read_bytes() if ok else None
        cfg = json.loads(data.decode("utf-8"), object_pairs_hook=receiver._pairs, parse_constant=receiver._no_constant) if ok else None
    except (OSError, ValueError, RecursionError):
        cfg = None
    if not isinstance(cfg, dict): raise HostConfigError(["host"])
    return cfg


def _ip(value):
    try: return ipaddress.ip_address(value)
    except (ValueError, TypeError): return None


def _interpreter_ok(itp, nested=False) -> bool:
    """host.json `interpreter`: url + model, optional timeout (1-120) and think (Ollama only), and (HASS-INTERP-OPENAI-1) `api`
    ("ollama" default, "openai") and, with api openai only, `fallback`: the same keys for the Ollama model asked once when the
    first answer fails. url is loopback http. HASS-CLOUD-CODEX-1: api "codex" is hass.cloud_codex.block_ok (no url)."""
    if not nested and isinstance(itp, dict) and itp.get("api") == "codex": return cloud_codex.block_ok(itp, lambda fb: _interpreter_ok(fb, True))
    allowed = {"url", "model", "timeout", "think"} | (set() if nested else {"api", "fallback"})
    if not (isinstance(itp, dict) and {"url", "model"} <= set(itp) <= allowed): return False
    api = itp.get("api", "ollama")
    ok = (isinstance(itp["model"], str) and 0 < len(itp["model"]) <= 100
          and type(itp.get("timeout", 30)) is int and 1 <= itp.get("timeout", 30) <= 120
          and type(itp.get("think", False)) is bool and api in interpreter_local.APIS
          and not ("think" in itp and api == "openai")  # the openai request is always non-thinking
          and ("fallback" not in itp or api == "openai") and (nested or "fallback" not in itp or _interpreter_ok(itp["fallback"], True)))
    if ok:
        try: interpreter_local.check_url(itp["url"])
        except ValueError: return False
    return ok


def _listen(value, allow_zero):
    host, _, port = value.rpartition(":") if isinstance(value, str) else ("", "", "")
    ip = _ip(host.strip("[]"))
    if ip is None or not port.isdigit() or not (1 if not allow_zero else 0) <= int(port) <= 65535: return None
    if ip.version == 6 and ip.ipv4_mapped: return None
    return (ip, int(port)) if ip.is_loopback or any(ip in net for net in TAILSCALE) else None


def load_host(path, allow_port_zero=False) -> dict:
    """host.json: a regular 0600 file of this user, <= 64 KiB, closed keys. Returns the config plus `addr`, `peers`."""
    raw = _private_json(path)
    bad = sorted(set(raw) - KEYS) + sorted(KEYS - OPTIONAL - set(raw))
    try: sandbox.policy(raw)
    except sandbox.ModeError as exc: bad.append(exc.code)
    text = lambda v: isinstance(v, str) and 0 < len(v) <= 4096  # noqa: E731
    itp = raw.get("interpreter")
    peers = raw.get("allowedPeers")
    checks = {"photos": type(raw.get("photos", False)) is bool, "pictures": type(raw.get("pictures", False)) is bool, "state": text(raw.get("state")), "secretFile": text(raw.get("secretFile")),
              "looks": type(raw.get("looks", False)) is bool,  # HASS-SITE-LOOK-1b: website look changes by text, default off
              "approvals": raw.get("approvals") in ("hold", "private", "live"),
              "previewer": type(raw.get("previewer", False)) is bool,
              "runtimeCommit": isinstance(raw.get("runtimeCommit"), str) and len(raw["runtimeCommit"]) == 40
              and all(c in "0123456789abcdef" for c in raw["runtimeCommit"]),
              "interpreter": _interpreter_ok(itp),
              "allowedPeers": isinstance(peers, list) and all(_ip(p) for p in peers),
              "listen": _listen(raw.get("listen"), allow_port_zero) is not None}
    bad += [name for name, ok in checks.items() if not ok and name not in bad]
    if "clover" in raw:  # HASS-CLOVER-2: the read-only Clover block; field names only, never a value or the token path
        from hass.clover.config import ConfigProblem, from_settings
        try: from_settings(raw["clover"])
        except ConfigProblem as exc: bad += [f"clover.{f}" if f != "clover" else "clover" for f in exc.fields]
    if not bad and not peers and not _listen(raw["listen"], allow_port_zero)[0].is_loopback: bad.append("allowedPeers")
    if raw.get("approvals") == "live" or isinstance(raw.get('live'), list) and "site" in raw['live']:
        from hass.publish_live import release_config
        try: raw["release"] = release_config(raw.get("release"))
        except ValueError as exc: bad.append(str(exc))
        for name in ("previewer", "pictures"):
            if raw.get(name) is not True: bad.append(name)
        try:
            settings = conversation.load_settings(Path(raw["state"]))
            if settings.get("liveSite") != "theavocadoman.com": bad.append("liveSite")
            if settings.get("approvalNeedsCode") is not True: bad.append("approvalNeedsCode")
        except (conversation.ConfigError, KeyError, TypeError): bad.append("state")
    if bad: raise HostConfigError(bad)
    ip, port = _listen(raw["listen"], allow_port_zero)
    return {**raw, "addr": (str(ip), port), "peers": frozenset(str(_ip(p)) for p in peers), "previewer": raw.get("previewer", False),
            "photos": raw.get("photos", False), "pictures": raw.get("pictures", False), "hostDir": str(Path(path).resolve().parent), "hostPath": str(Path(path).resolve())}


def runtime_problem(cfg, root=ROOT) -> bool:
    """D8: the checkout holding this host.py is at runtimeCommit, clean, and not the editor's writer worktree."""
    root = Path(root).resolve()

    def git(*args): return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    top, head, dirty = git("rev-parse", "--show-toplevel"), git("rev-parse", "HEAD"), git("status", "--porcelain")
    if top.returncode or head.returncode or dirty.returncode: return True
    if Path(top.stdout.strip()).resolve() != root or head.stdout.strip() != cfg["runtimeCommit"] or dirty.stdout.strip(): return True
    return Path(_worktree(cfg)).resolve() == root


def _worktree(cfg) -> str:
    if not Path(cfg["state"]).is_dir(): raise HostConfigError(["state"])
    try:
        sdir = editor_mod.open_state(cfg["state"])
        return editor_mod._read_config(sdir / "config.json")["worktree"]
    except editor_mod.UnsafeState: raise HostConfigError(["state"]) from None


def _pause_waiting(db, schema="main") -> bool:
    """True when a pause command sits unread or is being handled in the inbox (`pending`; or a queued payload cannot be
    read): the pause is on its way. `schema` names the attached inbox."""
    for (payload,) in db.execute(f"SELECT payload FROM {schema}.inbound WHERE state = 'pending'"):
        try:
            text = json.loads(payload)["text"]
            found = conversation.read_command(text) or conversation.parse_command(text)
        except (TypeError, ValueError, KeyError, AttributeError):
            return True  # cannot tell what it says: treat it as a pause
        if found and found[0] == "pause": return True
    return False


def _flag_set(db) -> bool:
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'control'").fetchone()
                and db.execute("SELECT 1 FROM control WHERE name = 'paused'").fetchone() is not None)


def paused_flag(state) -> bool:
    """HASS-FAST-1: True when changes are paused, when a pause command is queued or being handled (the worker may be busy
    with an earlier message, or moving the pause from the inbox into the control flag right now), or when this cannot be
    read. Read-only (`mode=ro`), nothing written, asked fresh on every 👀; the Mac sends its 👀 only when this is False.

    One read-only connection and one transaction hold both stores (the inbox is attached read-only). A pause is in the
    inbox as `pending` the whole time it is being handled (Inbox.drain marks it done only after Conversation has committed
    the flag), so the reads go in the order that cannot miss that move: the inbox first, then the flag. The flag is read
    a second time in a new transaction after the snapshot; if the two flag reads disagree (a pause or resume landed while
    this was reading) the answer is paused. Any error, an unreadable store or an unreadable queued payload is paused."""
    try:
        base = Path(state).resolve()
        path, inbox = base / "conversation.sqlite3", base / "inbox.sqlite3"
        if not path.is_file(): return True
        with contextlib.closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=1, isolation_level=None)) as db:
            attached = inbox.is_file()
            if attached: db.execute("ATTACH DATABASE ? AS inb", (f"{inbox.as_uri()}?mode=ro",))
            db.execute("BEGIN")
            try:
                if attached and _pause_waiting(db, "inb"): return True  # pending or in progress: the pause is on its way
                first = _flag_set(db)
            finally:
                db.execute("ROLLBACK")
            if first: return True
            return _flag_set(db) != first  # the second look, in a new transaction: any disagreement is paused (first is False here)
    except (OSError, ValueError, sqlite3.Error):
        return True


# -- serve ---------------------------------------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    timeout = 10  # a slow client cannot hold the single-threaded server
    server_version, sys_version = "hass", ""

    def log_message(self, *args): pass

    def log_request(self, code="-", size="-"):  # method, known path and status only: no peer, body, header or query
        path = getattr(self, "path", "")
        method = getattr(self, "command", "")
        LOG.info("%s %s %s", method if method in METHODS else "-", path if path in ROUTES else "-", code)

    def _send(self, code, obj=None):
        data = b"" if obj is None else json.dumps(obj, sort_keys=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _guard(self) -> bool:
        peer = _ip(self.client_address[0].split("%")[0])
        if peer is None or str(peer) not in self.server.peers: return self._send(403) or False
        if self.command != "POST" or self.path not in ROUTES: return self._send(404) or False
        return True

    do_GET = do_PUT = do_DELETE = do_HEAD = do_PATCH = do_OPTIONS = do_POST = lambda self: self._handle()

    def _handle(self):
        if not self._guard(): return
        length = self.headers.get("Content-Length", "")
        if not length.isdigit(): return self._send(411)
        if int(length) > (PHOTO_BODY if self.path == "/v1/photo" else MAX_BODY): return self._send(413)
        body, srv = self.rfile.read(int(length)), self.server
        now = srv.clock()
        if self.path == "/v1/inbound":
            return self._send(200, {"result": srv.receiver.accept(body, secret=srv.secret, now=now)["result"]})
        try:
            env = json.loads(body, object_pairs_hook=receiver._pairs, parse_constant=receiver._no_constant)
            msg = relay.unseal_control(env, srv.secret, now=now, seen=srv.receiver.inbox.seen())
        except (ValueError, UnicodeDecodeError, RecursionError, bridge.EnvelopeError):
            return self._send(400, {"result": "rejected"})
        secs = int(now.timestamp())
        if self.path == "/v1/photo":
            if msg["op"] not in ("photo", "photo-refused") or not srv.photos: return self._send(400, {"result": "rejected"})
            while srv.photo_times and secs - srv.photo_times[0] >= 60: srv.photo_times.popleft()
            if len(srv.photo_times) >= PHOTOS_PER_MIN: return self._send(429)
            srv.photo_times.append(secs)
            try: srv.photos.put(msg, secs)
            except ValueError: return self._send(400, {"result": "rejected"})
            out = {"op": "photo-ok", "guid": msg["guid"], "idx": msg["idx"]}
        elif msg["op"] == "pull":
            out = {"op": "replies", "items": srv.store.pull(msg["max"], secs, card_receipts=msg.get("card_receipts", False))}
        elif msg["op"] == "ack":
            if "receipt" in msg: srv.store.acknowledge_receipt(msg["ids"][0], msg["receipt"], now)
            else: srv.store.ack(msg["ids"], secs)
            out = {"op": "acked", "ids": msg["ids"]}
        elif msg["op"] == "state" and "paused" not in msg: out = {"op": "state", "paused": srv.paused()}  # HASS-FAST-1, read-only
        elif msg["op"] == "picture":
            while srv.pic_times and secs - srv.pic_times[0] >= 60: srv.pic_times.popleft()
            shot = None if len(srv.pic_times) >= PICTURES_PER_MIN else srv.store.picture(msg["id"], msg["idx"])
            srv.pic_times.append(secs)
            out = ({"op": "picture", "id": msg["id"], "idx": msg["idx"], "sha256": shot[0],
                    "b64": base64.b64encode(shot[1]).decode("ascii")} if shot else {"op": "gone", "id": msg["id"], "idx": msg["idx"]})
        else: return self._send(400, {"result": "rejected"})
        self._send(200, relay.seal_control(out, srv.secret, nonce=secrets.token_hex(16), now=now))


class Server(HTTPServer):
    def __init__(self, cfg, secret, rx, store, clock=_now, paused=lambda: True):
        self.address_family = socket.AF_INET6 if ":" in cfg["addr"][0] else socket.AF_INET
        self.peers, self.secret, self.receiver, self.store, self.clock = cfg["peers"], secret, rx, store, clock
        self.paused = paused  # HASS-FAST-1: () -> bool, True when changes are paused or unknown (no 👀)
        self.pic_times, self.photo_times = collections.deque(), collections.deque()
        self.photos = relay_photos.RelayPhotos(cfg["hostDir"], clock, Path(cfg["state"]) / "inbox.sqlite3") if cfg.get("photos") else None
        super().__init__(cfg["addr"], Handler)

    def server_bind(self):  # no reverse DNS lookup of the Tailscale address
        socketserver.TCPServer.server_bind(self)
        self.server_port = self.server_address[1]

    def handle_error(self, request, client_address):
        LOG.warning("request failed: %s", sys.exc_info()[0].__name__)


# -- work ----------------------------------------------------------------------------------------------------------
class _Timed:
    """HASS-FAST-1: stage times around each interpreter call; every other attribute (last_error ...) passes through."""
    def __init__(self, inner, worker): self._inner, self._worker = inner, worker

    def interpret(self, *args, **kwargs):
        w = self._worker
        w.stage("interp-start", w.current)
        try: return self._inner.interpret(*args, **kwargs)
        finally: w.stage("interp-end", w.current)

    def __getattr__(self, name): return getattr(self._inner, name)


def owner_chat_order(settings) -> tuple:
    """HASS-OWNERS-2: every owner chat, the configured main `ownerChat` first (it need not be first in `ownerChats`), then the others in
    config order. Without `ownerChats` it is the one chat, as before."""
    main = settings["ownerChat"]
    return (main, *(c for c in settings.get("ownerChats", ()) if c != main))


class Worker:
    def __init__(self, conv, rx, store, worktree, build, clock=_now, shots_dir=None, stage=stagelog.off):
        self.conv, self.rx, self.worktree, self.build, self.clock = conv, rx, Path(worktree), build, clock
        self.stage, self.current = stage, ""  # HASS-FAST-1: `current` is the message being handled (stage log only)
        conv.stage = stage
        self.sender = relay.RelaySender(store, owner_chat_order(conv.settings), lambda: int(clock().timestamp()), shots_dir, conv.settings.get("gChat"))
        self.receipt_for = self.sender.receipt_for
        self.rev = editor_mod.content_revision(self.worktree)
        conv.interpreter = _Timed(conv.interpreter, self)
        conv.early_flush = lambda: conv.flush(self.sender)  # HASS-INTAKE-2: a photo's first question goes out on receipt, before the photo is fetched
        raw_send = self.sender.send

        def send(chat, text, attachments=()):
            rid = raw_send(chat, text, attachments)
            self.stage("reply-queued", self.current, rid=stagelog.short(rid))
            return rid
        self.sender.send = send
        handle = rx.handle

        def refreshed(msg, *a, **kw):  # an earlier message in the same drain may have applied a change
            self._refresh()
            self.current = msg.provider_id
            self.stage("worker-pickup", msg.provider_id)
            try: return handle(msg, *a, **kw)
            finally:
                # HASS-FAST-1: this message's replies go out now, not after the rest of the drain (a slow earlier message
                # used to hold a quick command's reply). A failure here changes nothing: cycle() flushes again and raises as before.
                try: self.conv.flush(self.sender)
                except Exception: pass  # noqa: BLE001,S110
                self.stage("handled", msg.provider_id)
        rx.handle = refreshed

    def _refresh(self):
        if (rev := editor_mod.content_revision(self.worktree)) != self.rev:
            self.conv.interpreter, self.rev = _Timed(self.build(), self), rev

    def cycle(self):
        """Rebuild the interpreter prompt when the content changed (before every message), drain the inbox, queue the replies.
        HASS-CHAT-1: a store that is busy (sqlite "database is locked": another process, such as the 5-minute health check or
        the receiver, held a lock longer than the busy timeout, as at 19:50:01 on 2026-11-09 under load 44) is retried here with
        backoff (BUSY_WAITS) instead of failing the cycle; any other error, or still busy after the last wait, is raised as
        before (run() logs it and backs off). Retrying is safe: a message whose answer was not committed is still pending, and
        one that was is a duplicate."""
        for wait in (*BUSY_WAITS, None):
            try:
                return self._cycle_once()
            except sqlite3.OperationalError as exc:
                if wait is None or not is_busy(exc): raise
                LOG.warning("store busy, retrying the cycle in %.1f s", wait)
                self.sleep(wait)

    def _cycle_once(self):
        self._refresh()
        self.rx.drain()
        if hasattr(self.conv.editor, "reconcile"): self.conv.editor.reconcile()
        if hasattr(self.conv, "retry_previews"): self.conv.retry_previews()  # HASS-CHAT-1: a picture that failed 30 s ago
        self.conv.flush(self.sender)

    sleep = staticmethod(time.sleep)  # tests replace it

    def run(self, stop):
        wait = 1
        while not stop.is_set():
            try:
                self.cycle()
                wait = 1
            except Exception as exc:  # noqa: BLE001 - class name only; the message stays pending (health: inbox-stuck)
                # HASS-CHAT-1: sqlite's own message ("database is locked", "disk I/O error") names the cause and holds no owner text
                LOG.error("cycle failed: %s%s", type(exc).__name__, f": {str(exc)[:80]}" if isinstance(exc, sqlite3.Error) else "")
                wait = min(60, wait * 2)
            stop.wait(wait)


BUSY_WAITS = (0.5, 1.0, 2.0, 4.0, 8.0)  # HASS-CHAT-1: about 15 s in all, on top of each connection's own busy timeout


def is_busy(exc) -> bool:
    """True for sqlite's "database is locked" / "database table is locked" / busy errors, which clear when the other holder lets go."""
    return isinstance(exc, sqlite3.OperationalError) and any(w in str(exc).lower() for w in ("locked", "busy"))


def interpreter_builder(cfg, worktree):
    def build():
        content = load_content(Path(worktree) / "hass" / "content")
        prompt = interpreter_prompt.build(load_registry(), content)
        itp, hinter = cfg["interpreter"], nl_prep.make_hinter(content)  # HASS-NL-1

        def one(c, api):
            if api == "codex": return interpreter_local.LocalInterpreter(None, c["model"], prompt, timeout=c.get("timeout", 12), hinter=hinter,
                                                                         api=api, transport=cloud_codex.CodexTransport(c.get("effort", "low")))
            return interpreter_local.LocalInterpreter(c["url"], c["model"], prompt, timeout=c.get("timeout", 30),
                                                      think=c.get("think"), hinter=hinter, api=api)
        main = one(itp, itp.get("api", "ollama"))
        if "fallback" not in itp: return main  # HASS-INTERP-OPENAI-1: no fallback block, no second call
        fb = one(itp["fallback"], itp["fallback"].get("api", "ollama"))
        if main.api == "codex": cloud_codex.budget(main.transport, fb)  # HASS-CLOUD-CODEX-1: cloud + local inside the 30 s deadline
        return interpreter_local.FallbackInterpreter(main, fb, lambda r: conversation._checked(r) is r)
    return build


def clover_state(cfg) -> str:
    """HASS-CLOVER-2: 'not configured' (no `clover` block), 'ok', or one credential.REASONS word for the token file. stat only: the
    token is never opened, and neither the path nor any byte is returned."""
    if cfg.get("clover") is None: return "not configured"
    from hass.clover.credential import inspect
    return inspect(cfg["clover"]["tokenFile"]) or "ok"


def site_gate(cfg):
    """The sandbox Gate bound to this host config's recorded target identities."""
    def source():
        try: current = load_host(cfg['hostPath'])
        except HostConfigError: raise sandbox.ModeError('env-changed') from None
        if current['state'] != cfg['state']: raise sandbox.ModeError('env-changed')
        return current

    def identities():
        current = source()
        ids = {('site', 'sandbox'): _worktree(current), ('local', 'sandbox'): current['state'], ('local', 'live'): current['state']}
        if current.get('release'):
            r = current['release']
            ids[('site', 'live')] = json.dumps([_worktree(current), r['siteCheckout'], r['siteRemote'], 'main'])
        return ids
    return sandbox.Gate(source, identities)


def make_worker(cfg, store, *, editor=None, build=None, clock=_now, stage=stagelog.off) -> Worker:
    worktree = _worktree(cfg)
    build = build or interpreter_builder(cfg, worktree)
    if editor is None:
        from hass.publish_live import LiveEditor
        from hass.sandbox_editor import SiteEditor

        def live_factory():
            current = site_gate(cfg).source()
            return LiveEditor(cfg['state'], current['release'], current['hostDir'], clock=clock)

        editor = SiteEditor(cfg['state'], site_gate(cfg), live_factory, clock=clock)
    photos, labels = None, None
    if cfg.get("photos"):
        photos = relay_photos.RelayPhotos(cfg["hostDir"], clock, Path(cfg["state"]) / "inbox.sqlite3")
        itp = cfg["interpreter"]
        if itp.get("api") == "codex":
            labels = cloud_codex.reader(label_reader.LabelReader, itp)
        else:
            fallback = itp.get("fallback")
            labels = label_reader.LabelReader(itp["url"], itp["model"], timeout=itp.get("timeout", 30), api=itp.get("api", "ollama"),
                fallback=label_reader.LabelReader(fallback["url"], fallback["model"], timeout=fallback.get("timeout", 30)) if fallback else None)
    conv = conversation.Conversation(cfg["state"], editor or conversation.Editor(cfg["state"]), build(), clock,
                                     previewer=preview.Previewer(worktree) if cfg["previewer"] else None, photos=photos, labels=labels)
    if hasattr(conv.editor, 'sync_settings'):
        conv.editor.conv = conv
        conv.editor.sync_settings(conv.settings)
    elif 'site' not in cfg.get('live', []):
        conv.settings.pop("liveSite", None)
    conv.looks = cfg.get("looks") is True  # HASS-SITE-LOOK-1b: the host.json switch for look changes (read by the conversation)
    if cfg["approvals"] == "live" and not hasattr(conv.editor, 'gate'):
        conv.editor.conv = conv
        conv.editor.reconcile()
    if conv.settings.get("itemIntake") is True:  # HASS-INTAKE-2: the same local model service reads one odd intake answer (first try only)
        itp = cfg["interpreter"]
        try: conv.answer_reader = (cloud_codex.reader(answer_reader.AnswerReader, itp, think=itp["fallback"].get("think")) if itp.get("api") == "codex" else
                                   answer_reader.AnswerReader(itp["url"], itp["model"], timeout=itp.get("timeout", 30), api=itp.get("api", "ollama"), think=itp.get("think")))
        except (KeyError, ValueError): conv.answer_reader = None  # none set up: an odd answer is asked again, never guessed
    if (settings := cfg.get("clover")) is not None:
        from hass.clover.chat import TillDesk
        engine = None
        if settings.get("writeMode") is not None:
            from hass.clover import credential, dryrun
            from hass.clover.chat import BundleEngine
            from hass.clover.config import from_settings

            clover = from_settings(settings)
            rehearsal = clover.write_mode == "dry-run"
            factory = dryrun.make_client_factory(clover, credential.load_token, dry_run=rehearsal)
            owner = conv.settings
            chat_id = owner["ownerChat"]
            mike_keys = owner.get("chatKeys", {}).get(chat_id, owner["ownerKeys"])
            mike = min(mike_keys), chat_id
            engine_clock = lambda: clock().timestamp()
            if rehearsal:
                engine = dryrun.DryRunEngine(cfg["state"], clover, factory, mike=mike, clock=engine_clock)
                # A waiting rehearsal code must never become a live approval after a mode switch.
                engine.journal.path = engine.journal.path.with_name("rehearsal.sqlite3")
            else:
                engine = BundleEngine(cfg["state"], clover, factory, mike=mike, clock=engine_clock)
            engine.owners.update((key, chat_id) for key in mike_keys)
            if owner.get("gOwner") is True:  # validated gIsOwner in conversation settings
                engine.owners.update((key, owner["gChat"]) for key in owner["gKeys"])
        conv.till = TillDesk(cfg["state"], settings, engine=engine)
    rx = receiver.Receiver(state=inbox_mod.Inbox(cfg["state"], clock=clock), settings=conv,
                           apply=cfg["approvals"] in ("private", "live"))
    return Worker(conv, rx, store, worktree, build, clock, Path(cfg["state"]).resolve() / "screenshots" if cfg["pictures"] else None, stage)


# -- commands ------------------------------------------------------------------------------------------------------
def _ready(args, root, need_start=True):
    cfg = load_host(args.host)
    if runtime_problem(cfg, root): raise Refuse({"result": "runtime-mismatch"})
    key = relay.read_key(cfg["secretFile"])
    if need_start:
        try: inbox_mod.Inbox(cfg["state"]).close()
        except ValueError: raise Refuse({"result": "no-start-point"}) from None
    return cfg, key


def _stopper():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *a: stop.set())  # finish the current cycle, exit 0
    return stop


def set_mode(path, mode, target='site') -> dict:
    _private_json(path)  # refuse an unsafe host before creating a lock beside it
    with editor_mod._writer_lock(Path(path).resolve().parent) as held:
        return _set_mode(path, mode, target) if held else {'result': 'busy'}


def _set_mode(path, mode, target) -> dict:
    """Rewrite host.json `approvals` atomically (same folder, 0600, replaced in one step). The new file must load, so a switch to
    `live` without its release block, liveSite or pictures is refused and the old file stays."""
    raw = _private_json(path)
    current = sandbox.policy(raw)
    live = set(current['live'])
    if target not in ('site', 'till') or mode not in ('hold', 'private', 'sandbox', 'live'): raise HostConfigError(['live'])
    if mode == 'live': live.add(target)
    elif mode != 'hold': live.discard(target)
    approvals = 'hold' if mode == 'hold' else ('live' if 'site' in live else 'private')
    updated = {**raw, 'approvals': approvals, 'live': sorted(live), 'mode_gen': current['mode_gen'] + 1}
    target = Path(path)
    tmp = target.with_name(target.name + ".mode.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh: json.dump(updated, fh, indent=2, sort_keys=True)
        load_host(tmp)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError): os.unlink(tmp)
        raise
    return {"result": "ok", "approvals": approvals, "next": "systemctl --user restart hass-worker"}


def _run(args, root, clock):
    if args.cmd == "mode": return set_mode(args.host, args.value, args.target)
    if args.cmd == "start-point":
        cfg = load_host(args.host)
        _worktree(cfg)
        try: inbox_mod.Inbox(cfg["state"], start_at=args.at).close()
        except ValueError: raise Refuse({"result": "start-point-refused"}) from None
        return {"result": "ok", "start_at": args.at}
    cfg, key = _ready(args, root, need_start=args.cmd != "check")
    if args.cmd == "check":  # Clover token files are checked by stat only.
        clover = clover_state(cfg)
        write_mode = cfg.get("clover", {}).get("writeMode")
        if clover == "ok" and write_mode == "live":
            from hass.clover.credential import inspect
            clover = inspect(cfg["clover"]["writeTokenFile"]) or "ok"
        output = {"clover": clover}
        if write_mode is not None:
            output["writeMode"] = write_mode
        if clover not in ("ok", "not configured"): raise Refuse({"result": "clover", **output})
        return {"result": "ok", **output}
    host_dir = Path(args.host).resolve().parent
    stage = stagelog.StageLog(host_dir / "stages.jsonl")  # HASS-FAST-1: read-only stage times, ids hashed, no text
    if args.cmd == "work":
        stop = _stopper()
        make_worker(cfg, relay.RelayStore(host_dir), clock=clock, stage=stage).run(stop)
    elif args.cmd == "serve":
        stop, rx = _stopper(), receiver.Receiver(state=inbox_mod.Inbox(cfg["state"], clock=clock), settings=None)
        rx.stage = stage
        srv = Server(cfg, key, rx, relay.RelayStore(host_dir), clock, paused=lambda: paused_flag(cfg["state"]))
        srv.timeout = 1
        while not stop.is_set(): srv.handle_request()
    return {"result": "ok"}


def main(argv=None, *, root=ROOT, clock=_now) -> int:
    ap = argparse.ArgumentParser(prog="hass/host.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("serve", "work", "check", "start-point", "mode"):
        p = sub.add_parser(name)
        if name == "mode":
            p.add_argument("value", choices=("hold", "private", "sandbox", "live"))
            p.add_argument("--target", choices=("site", "till"), default="site")
        p.add_argument("--host", required=True)
        if name == "start-point": p.add_argument("--at", required=True)
    args = ap.parse_args(argv)
    try:
        out, code = _run(args, root, clock), 0
    except Refuse as exc: out, code = exc.out, 2
    except HostConfigError as exc:
        out, code = {"result": "refused", "reason": exc.reason} if exc.reason else {"result": "config", "fields": exc.fields}, 2
    except relay.KeyFileError as exc: out, code = {"result": "secret", "code": exc.code}, 2
    except Exception as exc:  # noqa: BLE001 - class name only
        out, code = {"result": "error", "error": type(exc).__name__}, 1
    print(json.dumps(out, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
