"""H08 prep: BlueBubbles bridge adapter (fixtures only). Nothing here listens, connects to a Mac or runs on its own.

- normalize(event): a BlueBubbles webhook event -> Inbound, or a named Drop. Owner identity stays in Conversation.
  A tapback (associatedMessageType set) is kind "reaction"; an updated-message without dateEdited (delivery/read)
  is Drop("receipt"); a real edit stays kind "edited".
  Each real edit is its own message: provider_id "<guid>:edited:<dateEdited>", received_at from dateEdited.
- seal()/unseal(): the Mac -> Agent Orange envelope (HMAC-SHA256, 300 s clock window, nonce replay refusal).
- BlueBubblesSender: Outbox adapter posting to the loopback-only REST API. The password travels in the query string
  (the documented `password` parameter), so no error raised here ever carries the URL, the query or the password.
Field names follow docs.bluebubbles.app (REST API & Webhooks, its Postman collection and the webhook example).
"""
import hashlib, hmac, json, os, re, stat, sys, urllib.error, urllib.parse, urllib.request, uuid  # noqa: E401
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass.conversation import Inbound  # noqa: E402

EVENT_KINDS = {"new-message": "new", "updated-message": "edited"}
DIRECT_CHAT_RE = re.compile(r"[^;]+;-;[^;]+")  # one-to-one `iMessage;-;<address>`; groups are `iMessage;+;chat...`
NONCE_RE, MAC_RE = re.compile(r"(?:[0-9a-f]{2}){16,}"), re.compile(r"[0-9a-f]{64}")
SURROGATE_RE = re.compile(r"[\ud800-\udfff]")  # a JSON-escaped lone surrogate: str that cannot be UTF-8 encoded
ENVELOPE_KEYS = {"v", "ts", "nonce", "body", "mac"}
# Reply references are local adapter metadata; the v1 Mac wire contract is unchanged.
BODY_TYPES = {f.name: {"from_me": bool, "attachments": int}.get(f.name, str)
              for f in fields(Inbound) if f.name != "reply_to"}
MAX_SKEW, MIN_KEY = 300, 32
SEND_PATH, SEND_TIMEOUT = "/api/v1/message/text", 10
LOOPBACK = ("127.0.0.1", "localhost")
PICTURE_NOTE = "(Preview picture not sent: this chat link sends text only. It is saved with the draft.)"


@dataclass(frozen=True)
class Drop:
    """An event that is not passed to Conversation, with the reason it was dropped."""
    reason: str


class EnvelopeError(Exception):
    """unseal() refused an envelope: shape, version, mac, stale or replay."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class BridgeError(Exception):
    """A send failed. args are (code, status, path): never the URL, query string or password."""
    def __init__(self, code, status=None):
        super().__init__(code, status, SEND_PATH)
        self.code, self.status = code, status


def _utc(ms):
    """Integer provider milliseconds -> UTC ISO text: whole seconds as before, else exactly three fractional digits.
    Integer arithmetic only (no float round trip), so a sub-second time keeps its cutoff and drain order."""
    dt = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=ms)
    return dt.isoformat(timespec="seconds" if ms % 1000 == 0 else "milliseconds")


def normalize(event):
    """Inbound for a one-to-one message event (attachments as a count only); otherwise Drop(<reason>). Pure: no I/O,
    no owner check."""
    if not isinstance(event, dict) or not isinstance(event.get("type"), str): return Drop("malformed")
    kind = EVENT_KINDS.get(event["type"])
    if kind is None: return Drop("unsupported-event")
    msg = event.get("data")
    if not isinstance(msg, dict): return Drop("malformed")
    guid, created, from_me, handle = msg.get("guid"), msg.get("dateCreated"), msg.get("isFromMe"), msg.get("handle")
    chats, attachments = msg.get("chats"), msg.get("attachments")
    if not (isinstance(guid, str) and guid and type(created) is int and created >= 0 and type(from_me) is bool
            and isinstance(chats, list) and isinstance(attachments, list)):
        return Drop("malformed")
    if not (isinstance(handle, dict) and isinstance(handle.get("address"), str) and handle["address"]):
        return Drop("malformed")  # required for echoes (isFromMe) too: no sender is ever invented
    if len(chats) != 1 or not isinstance(chats[0], dict) or not isinstance(chats[0].get("guid"), str) \
            or not DIRECT_CHAT_RE.fullmatch(chats[0]["guid"]):
        return Drop("group-or-unknown-chat")
    text = msg.get("text")
    if attachments:  # attachment-only events carry empty, null or U+FFFC (object replacement) text
        text = text.replace("\ufffc", "") if isinstance(text, str) else ""
    if not isinstance(text, str) or any(map(SURROGATE_RE.search, (guid, handle["address"], chats[0]["guid"], text))):
        return Drop("malformed")
    try:
        received = _utc(created)
    except (OverflowError, OSError, ValueError):
        return Drop("malformed")
    edited = msg.get("dateEdited")
    if event["type"] == "updated-message" and not (type(edited) is int and edited > 0):
        return Drop("receipt")  # checked first: a delivery/read update of a tapback is a receipt too
    tapback = msg.get("associatedMessageType")
    if tapback is not None and tapback != "":
        if not (type(tapback) is int or isinstance(tapback, str)): return Drop("malformed")
        kind = "reaction"  # text passes through unchanged; never read as a new change request
    pid = guid
    if kind == "edited":  # an edit keeps the original guid: its own id, timed by the edit, so the inbox keeps it
        pid = f"{guid}:edited:{edited}"
        try: received = _utc(edited)
        except (OverflowError, OSError, ValueError): return Drop("malformed")
    return Inbound(provider_id=pid, chat=chats[0]["guid"], sender=handle["address"], text=text, from_me=from_me,
                   kind=kind, received_at=received, attachments=len(attachments))


def _check_key(key) -> bytes:
    if not isinstance(key, (bytes, bytearray)) or len(key) < MIN_KEY:
        raise ValueError(f"envelope key must be at least {MIN_KEY} bytes")
    return bytes(key)


def _seconds(now) -> int:
    return int(now.timestamp()) if isinstance(now, datetime) else int(now)


def _mac(key: bytes, envelope: dict) -> str:
    data = json.dumps({k: v for k, v in envelope.items() if k != "mac"}, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def seal(inbound: Inbound, key, *, nonce: str, now) -> dict:
    """Envelope {v, ts, nonce, body, mac}; nonce is lower-case hex of at least 16 bytes, now a datetime or epoch s."""
    key = _check_key(key)
    if not isinstance(nonce, str) or not NONCE_RE.fullmatch(nonce): raise ValueError("nonce must be hex >= 16 bytes")
    body = asdict(inbound)
    body.pop("reply_to")
    envelope = {"v": 1, "ts": _seconds(now), "nonce": nonce, "body": body}
    envelope["mac"] = _mac(key, envelope)
    return envelope


def unseal(envelope, key, *, now, seen) -> Inbound:
    """The Inbound inside a valid envelope; adds its nonce to `seen` (anything with __contains__ and add)."""
    key = _check_key(key)
    if not isinstance(envelope, dict) or set(envelope) != ENVELOPE_KEYS: raise EnvelopeError("shape")
    if type(envelope["v"]) is not int or envelope["v"] != 1: raise EnvelopeError("version")
    body, ts, nonce, mac = envelope["body"], envelope["ts"], envelope["nonce"], envelope["mac"]
    if not (type(ts) is int and isinstance(nonce, str) and NONCE_RE.fullmatch(nonce) and isinstance(mac, str)
            and MAC_RE.fullmatch(mac) and isinstance(body, dict) and set(body) == set(BODY_TYPES)
            and all(type(body[k]) is t for k, t in BODY_TYPES.items()) and body["attachments"] >= 0
            and not any(type(v) is str and SURROGATE_RE.search(v) for v in body.values())):
        raise EnvelopeError("shape")  # checked before the MAC, so unencodable text never reaches canonicalization
    if not hmac.compare_digest(_mac(key, envelope), mac): raise EnvelopeError("mac")
    if abs(_seconds(now) - ts) > MAX_SKEW: raise EnvelopeError("stale")
    if nonce in seen: raise EnvelopeError("replay")
    seen.add(nonce)
    return Inbound(**body)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # a 3xx is reported as a failed send, never followed to another host


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)  # no proxy, no redirect


def _urllib_transport(url, body, headers, timeout) -> int:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code


def _private_file(path: str) -> str:
    """The path when it is a regular file (not a symlink) with no group/other permissions; else ValueError."""
    try:
        st = os.lstat(path)
    except OSError:
        st = None
    if st is None or not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077:
        raise ValueError("password file must be a regular file with no group/other access")
    return path


class BlueBubblesSender:
    """Outbox adapter: send(chat, text, attachments) -> one POST to loopback BlueBubbles, or BridgeError."""
    def __init__(self, base_url, password_file, transport=None):
        try:
            parts = urllib.parse.urlsplit(base_url)
            port = parts.port
        except (TypeError, ValueError, AttributeError):
            parts, port = None, None
        if parts is None or parts.scheme not in ("http", "https") or parts.hostname not in LOOPBACK \
                or port is None or port == 0 or parts.username is not None or parts.password is not None \
                or parts.path not in ("", "/") or parts.query or parts.fragment:
            raise ValueError("base_url must be http(s)://127.0.0.1:<port> or http(s)://localhost:<port>")
        self._base = f"{parts.scheme}://{parts.hostname}:{port}"
        self._password_file = _private_file(str(password_file))
        self._transport = transport or _urllib_transport

    def __repr__(self):
        return f"BlueBubblesSender({self._base!r})"

    def send(self, chat, text, attachments=()):
        # text only: attachments add one fixed note; their paths are never opened, stat'ed, logged or sent
        message = text + "\n" + PICTURE_NOTE if attachments else text
        code, status = None, None
        try:
            password = Path(_private_file(self._password_file)).read_text("utf-8").strip()
        except (OSError, ValueError, UnicodeDecodeError):
            password = ""
        if not password:
            code = "password-unreadable"
        else:
            body = json.dumps({"chatGuid": chat, "tempGuid": str(uuid.uuid4()), "message": message,
                               "method": "apple-script"}).encode("utf-8")
            url = f"{self._base}{SEND_PATH}?{urllib.parse.urlencode({'password': password})}"
            try:
                status = self._transport(url, body, {"Content-Type": "application/json"}, SEND_TIMEOUT)
            except Exception:  # noqa: BLE001 - any transport failure; its text may hold the URL, so it is dropped
                code = "transport-error"
            if code is None and not (type(status) is int and 200 <= status < 300):
                code, status = "http-error", status if type(status) is int else None
        if code is not None:
            raise BridgeError(code, status)  # raised outside the except block: no __cause__ or __context__
