"""HASS-CLOVER-1/2: read-only Clover REST v3 client with an injected HTTP layer.

READ ONLY: the client has no write method. It can only GET the paths in READ_PATHS: the merchant's basic record, items, item stocks and
categories (nothing about sales, orders, payments, customers or employees); any other path, method or host is refused before a request
exists. The HTTP layer is a callable `transport(Request) -> Response` that is passed in; tests pass recorded fixtures.

Errors carry a status number or a fixed phrase, never a header, a body, a URL query or the token. Nothing here logs a header.
Rate limits (docs.clover.com/dev/docs/api-usage-rate-limits): 16 requests/s and 5 concurrent per token. This client is
synchronous (one request in flight), paces itself well under that, honours Retry-After on a 429 and gives up after `max_retries`.
"""
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode

LOG = logging.getLogger("hass.clover")

HOSTS = {"sandbox": "https://apisandbox.dev.clover.com", "production": "https://api.clover.com"}  # production = North America
USER_AGENT = "AvocadoShack-Hass/1 (read-only inventory client)"
MERCHANT_RE = re.compile(r"[A-Za-z0-9]{8,20}")
ID = r"[A-Za-z0-9]{1,32}"
# HASS-CLOVER-2: the ONLY reads: "" is the merchant's basic record (GET /v3/merchants/{mId}); then items, item stocks, categories.
READ_PATH_TEXT = ("", r"/items", rf"/items/{ID}", r"/item_stocks", rf"/item_stocks/{ID}", r"/categories")
READ_PATHS = tuple(re.compile(p) for p in READ_PATH_TEXT)
READ_METHODS = frozenset({"GET"})
PAGE_SIZE = 1000                 # documented maximum `limit` for GET /items
MAX_PAGES = 50                   # 50,000 items is far beyond a shop; a longer loop is a bug
RETRY_STATUS = frozenset({429, 500, 502, 503, 504, 507})
BODY_LIMIT = 8 * 1024 * 1024
EXPAND = "itemStock,categories,tags"


class CloverError(Exception):
    """Any client failure. `status` is the HTTP status when there was one; the message is fixed text plus that number."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class CloverRefused(CloverError):
    """The client refused to build the request (path, method or host not allowed). Nothing was sent."""


class CloverAuthError(CloverError):
    """401. Clover returns 401 both for a bad token and for a token without the needed permission."""


class CloverNotFound(CloverError):
    pass


class RateLimited(CloverError):
    """429 after every retry. `retry_after` is the number of seconds Clover last asked for."""

    def __init__(self, retry_after):
        super().__init__("clover rate limit; retries used up", 429)
        self.retry_after = retry_after


class CloverUnavailable(CloverError):
    """No usable answer: the network failed, or Clover answered 5xx on every retry."""


class SecretHeaders(dict):
    """Request headers; printing one shows the names only."""

    def __repr__(self):
        return "SecretHeaders(" + ", ".join(sorted(self)) + ")"

    __str__ = __repr__


@dataclass(frozen=True)
class Request:
    method: str
    url: str
    headers: SecretHeaders = field(repr=False)
    body: "bytes | None" = None


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict = field(default_factory=dict, repr=False)  # lower-case names
    body: bytes = field(default=b"", repr=False)


class CloverClient:
    """Reads items and stock. `token` is a credential.Token; `transport` is the injected HTTP layer."""

    def __init__(self, merchant_id, token, transport, environment="sandbox", *, page_size=PAGE_SIZE, max_retries=3,
                 min_interval=0.25, sleep=time.sleep, monotonic=time.monotonic):
        if environment not in HOSTS:
            raise CloverRefused("unknown environment")
        if not isinstance(merchant_id, str) or not MERCHANT_RE.fullmatch(merchant_id):
            raise CloverRefused("bad merchant id")
        if not 1 <= page_size <= PAGE_SIZE or not 0 <= max_retries <= 5:
            raise CloverRefused("bad client setting")
        self._merchant, self._token, self._transport, self.environment = merchant_id, token, transport, environment
        self._page_size, self._max_retries, self._min_interval = page_size, max_retries, min_interval
        self._sleep, self._monotonic, self._last = sleep, monotonic, None
        self._lock = threading.Lock()  # one request in flight: well inside Clover's 5-concurrent limit

    def __repr__(self):
        return f"CloverClient(environment={self.environment!r}, read-only)"

    def __reduce__(self):
        raise TypeError("CloverClient cannot be serialised")

    # ---- the read API -------------------------------------------------------------------------------------------------
    def get_merchant(self):
        """The merchant's basic record (GET /v3/merchants/{mId}, no expand). `check` uses its status and id only."""
        return self._get("", {})

    def first_items(self, limit=1):
        """One page of items, no expand: `check` proves the token can read inventory. Returns the raw page document."""
        if type(limit) is not int or not 1 <= limit <= 10:
            raise CloverRefused("bad limit")
        doc = self._get("/items", {"limit": limit})
        self._elements(doc)
        return doc

    def list_items(self, modified_since_ms=None):
        """All items with stock, categories and tags, page by page. `modified_since_ms` limits to items changed since then."""
        query = {"expand": EXPAND, "limit": self._page_size}
        if modified_since_ms is not None:
            if type(modified_since_ms) is not int or modified_since_ms < 0:
                raise CloverRefused("bad filter")
            query["filter"] = f"modifiedTime>={modified_since_ms}"
        return self._pages("/items", query)

    def _pages(self, path, query):
        out = []
        for page in range(MAX_PAGES):
            got = self._elements(self._get(path, {**query, "offset": page * self._page_size}))
            out.extend(got)
            if len(got) < self._page_size:
                return out
        raise CloverError("too many pages")

    def get_item(self, item_id):
        return self._get(f"/items/{item_id}", {"expand": EXPAND})

    def get_stock(self, item_id):
        return self._get(f"/item_stocks/{item_id}", {})

    def list_stocks(self):
        """Every item stock record (items the merchant counts), page by page."""
        return self._pages("/item_stocks", {"limit": self._page_size})

    def list_categories(self):
        return self._pages("/categories", {"limit": self._page_size})

    def find_by_sku(self, sku):
        """Items whose SKU equals `sku` exactly (the collision check made right before a create)."""
        if not isinstance(sku, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", sku):
            raise CloverRefused("bad sku")
        return self._elements(self._get("/items", {"filter": f"sku={sku}", "limit": 10}))

    # ---- internals ----------------------------------------------------------------------------------------------------
    @staticmethod
    def _elements(doc):
        els = doc.get("elements") if isinstance(doc, dict) else None
        if not isinstance(els, list) or not all(isinstance(e, dict) for e in els):
            raise CloverError("unexpected response shape")
        return els

    def build(self, method, path, query):
        """The Request for an allowed read, or CloverRefused. Public so tests can prove what is refused."""
        if method not in READ_METHODS:
            raise CloverRefused("method not allowed")
        if not any(p.fullmatch(path) for p in READ_PATHS):
            raise CloverRefused("path not allowed")
        qs = urlencode(query, safe=">=,")  # modifiedTime>=123 and expand=a,b stay readable; everything else is escaped
        url = f"{HOSTS[self.environment]}/v3/merchants/{self._merchant}{path}" + (f"?{qs}" if qs else "")
        headers = SecretHeaders({"Authorization": self._token.authorization(), "Accept": "application/json", "User-Agent": USER_AGENT})
        return Request("GET", url, headers)

    def _get(self, path, query):
        request = self.build("GET", path, query)
        with self._lock:
            attempt = 0
            while True:
                self._pace()
                failure, response = self._send(request)
                status = failure or getattr(response, "status", None)
                LOG.info("clover GET %s -> %s", path or "(merchant)", status)  # path template + status only; never a header, query or body
                if failure is None and status == 200:
                    return self._json(response)
                wait = self._retry_wait(response, attempt)
                if status in RETRY_STATUS and attempt < self._max_retries:
                    attempt += 1
                    self._sleep(wait)
                    continue
                break
        self._raise(status, wait)

    def _send(self, request):
        """(failure, response): failure is a fixed word when the transport raised; its message is dropped (it may name a header)."""
        try:
            response = self._transport(request)
        except Exception:  # noqa: BLE001 - any transport failure; the foreign message is deliberately not kept
            return "transport", None
        if not isinstance(response, Response) or not isinstance(response.status, int):
            return "transport", None
        return None, response

    def _pace(self):
        now = self._monotonic()
        if self._last is not None and now - self._last < self._min_interval:
            self._sleep(self._min_interval - (now - self._last))
        self._last = self._monotonic()

    @staticmethod
    def _retry_wait(response, attempt):
        """Seconds to wait: Retry-After when Clover sent a whole number (1-30), else 1, 2, 4 ..."""
        raw = (response.headers.get("retry-after") if response is not None else None) or ""
        text = raw.strip()
        if text and text.isascii() and text.isdigit():  # ASCII digits only: int() refuses e.g. superscripts
            digits = text.lstrip("0")
            # clamp on length first so a huge digit string is never converted to an int
            return 30 if len(digits) > 2 else max(1, min(30, int(digits or "0")))
        return min(30, 2 ** attempt)

    @staticmethod
    def _json(response):
        if len(response.body) > BODY_LIMIT:
            raise CloverError("response too large", response.status)
        try:
            doc = json.loads(response.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            doc = None
        if not isinstance(doc, dict):
            raise CloverError("response is not a JSON object", response.status)
        return doc

    @staticmethod
    def _raise(status, wait):
        if status == "transport":
            raise CloverUnavailable("clover could not be reached")
        if status == 429:
            raise RateLimited(wait)
        if status == 401:
            raise CloverAuthError("clover refused the key (invalid, or missing the inventory permission)", 401)
        if status == 404:
            raise CloverNotFound("clover has no such item", 404)
        if status in RETRY_STATUS:
            raise CloverUnavailable(f"clover unavailable ({status})", status)
        raise CloverError(f"clover answered {status}", status)


class CloverWriteClient(CloverClient):
    """Separate service write client; the existing read-only client remains read-only."""

    def write(self, method, path, payload):
        """One attempt only: an ambiguous write must be recovered by read-back, never retried."""
        allowed = (method == "POST" and re.fullmatch(rf"/items(?:/{ID})?|/category_items", path)
                   or method == "PUT" and re.fullmatch(rf"/item_stocks/{ID}", path))
        if not allowed:
            raise CloverRefused("write path not allowed")
        request = self.build("GET", "/items", {})
        request.headers["Content-Type"] = "application/json"
        request = Request(method, request.url.removesuffix("/items") + path, request.headers,
                          json.dumps(payload, allow_nan=False).encode())
        with self._lock:
            self._pace()
            failure, response = self._send(request)
        status = failure or response.status
        if failure is None and status in (200, 201, 204):
            return self._json(response) if response.body else {}
        self._raise(status, 1)
