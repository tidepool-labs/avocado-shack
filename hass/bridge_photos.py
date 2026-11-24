"""H10: BlueBubblesPhotos, a photo source for Conversation(photos=...). Fixtures only: nothing here runs on its own.

fetch(guid, n) asks loopback BlueBubbles for one message's attachment list, then downloads the first n attachments and
returns their bytes. Same safety rules as bridge.BlueBubblesSender: loopback base URL only (explicit nonzero port required), no proxy, no redirect, the
password read fresh per call from a private file and sent only in the documented `password` query parameter, and no
error raised here ever carries the URL, the query, the password or a response body.
REST (docs.bluebubbles.app): GET /api/v1/message/{guid}?with=attachment -> {"data": {"attachments": [{"guid", ...}]}};
GET /api/v1/attachment/{guid}/download?original=true -> raw original bytes (without `original`, BlueBubbles converts a HEIC
to JPEG, so the length no longer matches totalBytes; the parameter is `original` in the BlueBubbles client, commit f2e5354
"Add support for downloading original attachment if converted by server", github.com/BlueBubblesApp/bluebubbles-app).
A download whose length differs from the attachment's declared int totalBytes is refused as size-mismatch.
Attachments after the first n are never read or checked.
A repeated JSON member `data`, `attachments`, or (in the first n attachments) `guid` or `totalBytes` is ambiguous: a `shape`
refusal before any download, even for equal values or escaped spellings. Other repeated members, and repeats after n, are ignored.
A guid is scalar text: non-empty, at most MAX_GUID code points, no C0/C1 control and no surrogate code point
(U+D800-U+DFFF, which UTF-8 cannot encode); a bad attachment guid in the first n is a `shape` refusal before any download.
"""
import json, sys, urllib.error, urllib.parse, urllib.request  # noqa: E401
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import media  # noqa: E402
from hass.bridge import LOOPBACK, BridgeError, _NoRedirect, _private_file  # noqa: E402

META_LIMIT, MAX_GUID, MAX_COUNT = 256 * 1024, 200, 10
MESSAGE_PATH, DOWNLOAD_PATH = "/api/v1/message/{}?with=attachment&", "/api/v1/attachment/{}/download?original=true&"

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)  # no proxy, no redirect


class _ShortBody(Exception):
    """The body ended before its announced Content-Length, or came under an unsupported transfer coding (internal: _get
    turns it into `size-mismatch`)."""


def _announced(response):
    """The announced Content-Length as an int, or None when absent or malformed, or when exact `chunked` encoding (which
    http.client decodes and which overrides Content-Length) is in use. Any other Transfer-Encoding (identity, gzip, a
    list...) is not decoded by http.client, so the body cannot be shown complete: _ShortBody."""
    coding = response.headers.get("Transfer-Encoding")
    if isinstance(coding, str):  # http.client headers give str or None; a non-str stub value is treated as absent
        if coding.strip().lower() == "chunked": return None
        raise _ShortBody()
    value = response.headers.get("Content-Length")
    return int(value) if isinstance(value, str) and value.isascii() and value.isdigit() else None


def _urllib_transport(url, headers, timeout, limit):
    """(status, body) for one GET; reads at most limit + 1 bytes so an oversized body is seen, never held whole.
    A body of at most limit bytes that is shorter than its announced Content-Length raises _ShortBody (read() alone
    returns the cut-off bytes without error); an oversized body is left to the caller's too-large check."""
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            body, announced = response.read(limit + 1), _announced(response)
            if announced is not None and len(body) <= limit and len(body) < announced: raise _ShortBody()
            return response.status, body
    except urllib.error.HTTPError as exc:
        exc.close()
        return exc.code, b""


class _Obj(dict):
    """Decoded JSON object that remembers which decoded key names were repeated (names only, no values)."""
    dups = frozenset()


def _pairs(pairs):
    obj, seen = _Obj(), set()
    for k, v in pairs:
        if k in obj: seen.add(k)
        obj[k] = v
    obj.dups = frozenset(seen)
    return obj


def _valid_guid(value):
    """True only for a non-empty str of at most MAX_GUID code points with no control or surrogate code point.
    The exact values "." and ".." are refused: they stay literal in a quoted URL path and resolve as dot segments."""
    return isinstance(value, str) and value not in (".", "..") and 0 < len(value) <= MAX_GUID and not any(
        ord(c) < 32 or 127 <= ord(c) < 160 or 0xD800 <= ord(c) <= 0xDFFF for c in value)


def _quote(value):
    return urllib.parse.quote(value, safe="")  # one path segment: "/" and "?" never add a segment or a query


class BlueBubblesPhotos:
    """Photo source: fetch(guid, n) -> list of exactly n attachment byte strings, or BridgeError(code, status)."""
    def __init__(self, base_url, password_file, transport=None, timeout=20):
        try:  # URL rules copied from BlueBubblesSender.__init__ (bridge.py is not edited)
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
        if not (type(timeout) is int and 1 <= timeout <= 120):  # checked last: URL/password messages keep priority
            raise ValueError("timeout must be a whole number of seconds from 1 to 120")
        self._transport, self._timeout = transport or _urllib_transport, timeout

    def __repr__(self):
        return f"BlueBubblesPhotos({self._base!r})"

    def _get(self, path, accept, limit):
        """(code, status, body): code None on a 2xx within limit; the transport's error text is dropped."""
        try:
            status, body = self._transport(self._base + path, {"Accept": accept}, self._timeout, limit)
        except _ShortBody:
            return "size-mismatch", None, b""  # the same fixed code as a totalBytes mismatch: a cut-off body is a failed fetch
        except Exception:  # noqa: BLE001 - any transport failure; its text may hold the URL, so it is dropped
            return "transport-error", None, b""
        if not (type(status) is int and 200 <= status < 300):
            return "http-error", status if type(status) is int else None, b""
        if not isinstance(body, (bytes, bytearray)): return "transport-error", status, b""
        return ("too-large", status, b"") if len(body) > limit else (None, status, bytes(body))

    @staticmethod
    def _attachment_ids(meta, n):
        """(code, ids): the first n (guid, declared totalBytes or None) pairs from the metadata, or a failure code."""
        try:
            doc = json.loads(meta.decode("utf-8"), object_pairs_hook=_pairs)
        except (UnicodeDecodeError, ValueError, RecursionError):
            return "not-json", []
        data = doc.get("data") if isinstance(doc, dict) else None
        items = data.get("attachments") if isinstance(data, dict) else None
        if not isinstance(items, list) or "data" in doc.dups or "attachments" in data.dups: return "shape", []
        head = items[:n]
        if any(isinstance(a, _Obj) and a.dups & {"guid", "totalBytes"} for a in head): return "shape", []  # ambiguous key  # H10: only these are downloaded or checked; each guid bounded like the message guid, unique
        if not all(isinstance(a, dict) and isinstance(a.get("guid"), str) and a["guid"] for a in head):
            return "shape", []
        if len({a["guid"] for a in head}) < len(head) or any(
                not _valid_guid(a["guid"])
                or not (a.get("totalBytes") is None or type(a["totalBytes"]) is int and a["totalBytes"] >= 0)
                for a in head):
            return "shape", []  # a non-int (bool, str, float) or negative totalBytes is a shape error too
        if len(items) < n: return "attachment-count", []
        if any(type(a.get("totalBytes")) is int and a["totalBytes"] > media.MAX_BYTES for a in items[:n]):
            return "too-large", []  # declared too big: refused before any download
        return None, [(a["guid"], a.get("totalBytes")) for a in items[:n]]

    def fetch(self, guid, n):
        if not _valid_guid(guid):
            raise ValueError(f"guid must be a non-empty str of at most {MAX_GUID} chars without control characters "
                             "or surrogate code points, and must not be '.' or '..'")
        if type(n) is not int or not 1 <= n <= MAX_COUNT: raise ValueError(f"n must be an int from 1 to {MAX_COUNT}")
        code, status, out = None, None, []
        try:
            password = Path(_private_file(self._password_file)).read_text("utf-8").strip()
        except (OSError, ValueError, UnicodeDecodeError):
            password = ""
        if not password:
            code = "password-unreadable"
        else:
            query = urllib.parse.urlencode({"password": password})
            code, status, meta = self._get(MESSAGE_PATH.format(_quote(guid)) + query, "application/json", META_LIMIT)
            code, ids = (code, []) if code else self._attachment_ids(meta, n)
            for aid, declared in ids:
                code, status, data = self._get(DOWNLOAD_PATH.format(_quote(aid)) + query, "*/*", media.MAX_BYTES)
                code = code or (None if data else "empty")
                if not code and declared is not None and len(data) != declared:
                    code = "size-mismatch"  # a cut-off or padded download never becomes a photo
                if code: break
                out.append(data)
        if code is not None:  # raised outside any except block: no __cause__ or __context__
            raise BridgeError(code, status if code == "http-error" else None)
        return out
