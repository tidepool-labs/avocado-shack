"""HASS-HIKE-LOOKUP-1: find a hike on open map data and propose it to Mike in plain words (prototype, offline).

Design and the answers to the six questions: docs/hass/HIKE-LOOKUP.md. Data: OpenStreetMap (names, route lines) and
USGS 3DEP (elevation). This module has NO network code and no clock of its own: everything it learns arrives through a
``Transport`` object, so the tests replay recorded answers (hass/tests/fixtures/hike_lookup/). The one place that can
make a live call is the manual script scripts/hike_lookup_manual.py, which is never run by the tests or CI.

What it does, in order:
  1. ``name_tokens`` / ``overpass_query``: a typed or spoken hike name becomes a loose search (San Luis Obispo County
     first, then Nominatim over California).
  2. ``build_groups`` / ``analyse``: matched trail pieces are chained by shared points; the distance is the haversine
     sum of the route line; the shape is a loop, out-and-back or point-to-point, or the answer is "not sure".
  3. ``elevation_gain_ft``: climbing from 3DEP samples every 50 m or so (never more than 120 samples per route).
  4. ``lookup`` returns a ``LookupResult``; ``proposal`` and ``choices`` word it for Mike (hass/voice.py rules).
  5. ``plan_ops`` turns a confirmed candidate into the EXISTING ops ``route.add`` (and ``hike.create`` once Mike has
     confirmed a day, time and meeting place). It never writes anything itself.

Nothing here invents a fact: a number that cannot be measured is left out and said so. Only the hike name ever leaves
the box (see ``outbound_names``).
"""
from __future__ import annotations

import difflib
import hashlib
import json
import math
import os
import re
import statistics
import threading
import time
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

try:
    import fcntl  # POSIX file locking: the day count's cross-process lock. Without it no request is made (fails closed)
except ImportError:  # pragma: no cover - not on the Linux/macOS hosts Hass runs on
    fcntl = None

from hass import voice
from hass.content_model import FORBIDDEN_TEXT, INVISIBLE_RE

VERSION = "hike-lookup-1"
SOURCE_NAME = "OpenStreetMap contributors and USGS 3DEP"
SOURCE_LICENCE = "OpenStreetMap data is open data under the ODbL; USGS 3DEP elevation is a US government work"

# south, west, north, east
SLO_BBOX = (34.90, -121.45, 35.80, -119.40)
CALIFORNIA_VIEWBOX = (-124.50, 42.10, -114.10, 32.50)  # Nominatim: left, top, right, bottom
HOME = (35.2828, -120.6596)  # downtown San Luis Obispo: only used to order several matches

MATCH_MIN = 0.75  # name similarity needed to count as a match
MAX_OFFER = 3  # Mike is never offered more than this many
MAX_NAME_WORDS = 6  # the search uses at most this many words of the name, and no word with a digit in it
MIN_HIKE_M = 480.0  # a mapped line shorter than this (0.3 mile) is not offered as a hike
SAMPLE_SPACING_M = 50.0
MAX_SAMPLES = 120
BRIDGE_MAX_M = 200.0  # same-name pieces closer than this are treated as one trail; the gap is counted
BRIDGE_SHARE_MAX = 0.08  # ... but only while the gaps are at most this share of the route
SPUR_SHARE_MAX = 0.12  # side spurs up to this share of a branched route are left out; more than that is "not sure"
SUMMIT_NEAR_M = 150.0
LENGTH_DISAGREE = 0.25  # the map line and the source's own stated length may differ by this much
M_PER_MILE = 1609.344
FT_PER_M = 3.28084

STOP_WORDS = {"the", "a", "an", "trail", "trails", "hike", "hikes", "walk", "trailhead", "to", "at", "on"}
TRAIL_WORDS = {"trail", "trails", "road", "fire", "connector", "loop", "path", "track", "spur", "summit", "access", "route"}
PATH_TYPES = {"path", "footway", "track", "bridleway", "steps", "hiking", "foot", "trail"}  # Nominatim result types that are trails, not roads
ABBREVIATIONS = {"mt": "mount", "mtn": "mountain", "pt": "point", "rd": "road", "cyn": "canyon"}
DESTINATION_WORDS = {"peak", "summit", "point", "hill", "rock", "falls", "lookout", "overlook", "dome", "mountain", "mount",
                     "cerro", "knob", "butte"}  # a name that is a place to walk TO; "bluff" or "beach" trails run along something
CLOSURE_WORDS = re.compile(r"\b(clos(?:ed|ure)|washout|washed out|damage[d]?|detour|re-?rout\w*|unsafe|impassable|"
                           r"landslide|storm|temporar\w+|do not enter|no entry)\b", re.I)
CLOSURE_ACCESS = {"no", "private", "closed"}
CLOSURE_KEYS = ("note", "description", "fixme", "warning", "access:note", "check_date:note")

SHAPE_WORDS = {"loop": "a loop", "out-and-back": "out and back", "point-to-point": "one way"}
SHAPE_ROUTE_TYPE = {"loop": "Loop", "out-and-back": "Out & back", "point-to-point": "Point to point"}


# -- transport ------------------------------------------------------------------------------------------------------


class TransportError(Exception):
    """kind: ``network`` (cannot reach it), ``slow`` (no answer in time), ``busy`` (it said try later), ``budget`` (our own
    request limit), ``missing`` (a fixture has no recorded answer), ``bad`` (an answer we cannot read)."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


@dataclass(frozen=True)
class Response:
    body: object
    retrieved: date  # the day the answer was really fetched (a saved copy keeps its own day)
    stale: bool = False  # True: older than its lifetime and the live refresh failed


def request_key(service: str, request: dict) -> str:
    """Stable key of one outbound request: ``<service>:<16 hex of sha256(canonical request)>``."""
    core = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{service}:{hashlib.sha256(core.encode('utf-8')).hexdigest()[:16]}"


class FixtureTransport:
    """Replays recorded answers: a folder of ``*.json`` files ``{"meta": {...}, "responses": {key: {"retrieved", "body", "request"}}}``.
    A request with no recorded answer raises ``TransportError("missing")``, so a test can never reach the network."""

    def __init__(self, *paths):
        self.responses: dict = {}
        self.meta: dict = {}
        self.calls: list = []
        for path in paths:
            data = json.loads(Path(path).read_text("utf-8"))
            self.meta[Path(path).stem] = data.get("meta", {})
            self.responses.update(data["responses"])

    def get(self, service: str, request: dict) -> Response:
        key = request_key(service, request)
        self.calls.append((service, key))
        if key not in self.responses:
            raise TransportError("missing", key)
        rec = self.responses[key]
        return Response(rec["body"], date.fromisoformat(rec["retrieved"]))


# service -> (lifetime in days, minimum seconds between two requests to it)
LIFETIME_DAYS = {"overpass": 30, "nominatim_search": 30, "nominatim_reverse": 90, "elevation": 365}
MIN_INTERVAL_S = {"overpass": 2.0, "nominatim_search": 1.1, "nominatim_reverse": 1.1, "elevation": 0.5}
# the public server a service really talks to: the two Nominatim calls are ONE host with ONE "a request a second" policy
SERVICE_HOST = {"overpass": "overpass", "nominatim_search": "nominatim", "nominatim_reverse": "nominatim", "elevation": "elevation"}
MAX_PER_LOOKUP = 8
MAX_PER_DAY = 60
COUNT_FILE = "day-count.json"
COUNT_LOCK_FILE = "day-count.lock"
COUNT_LOCK_SECONDS = 5.0  # how long a request waits for another client to finish writing the count before it is refused
COUNT_DAYS_KEPT = 7


def _unique_tmp(path: Path) -> Path:
    """A temp file name beside ``path`` that no other process or thread is using."""
    return path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.{time.monotonic_ns()}.tmp")


def _fsync(path: Path) -> None:
    """Flush a just-written file to disk (best effort: a file system that cannot is not a reason to refuse)."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


class SpacingLimiter:
    """Minimum time between two requests to one public server, shared by every ``CachedTransport`` given the same limiter (thread-safe).

    A new ``CachedTransport`` is made for each chat lookup, so a limiter of its own would forget the last request every time; the chat
    uses ``shared_limiter()`` so the spacing holds across lookups. Requests to one server (``SERVICE_HOST``: both Nominatim calls are
    one) are also made one at a time. This spaces requests inside ONE process; the day count (below) is what is shared between
    processes."""

    def __init__(self):
        self._guard = threading.Lock()
        self._locks: dict = {}
        self._last: dict = {}

    @contextmanager
    def hold(self, service: str, clock: Callable[[], float], sleep: Callable[[float], None], deadline: float | None = None):
        """Wait for this server's turn and its spacing, then let the caller make its request. ``deadline`` (a ``clock`` reading, or None
        for no limit) bounds ALL the waiting: a turn not won, or a spacing that would run past it, raises ``TransportError("slow")``
        and no request is made. The caller still works out what is left of its time once the wait is over."""
        host = SERVICE_HOST[service]
        with self._guard:
            lock = self._locks.setdefault(host, threading.Lock())
        if not lock.acquire(blocking=False):  # another request to this server is running: wait for its turn, but only as long as there is time
            left = None if deadline is None else deadline - clock()
            if left is None:
                lock.acquire()
            elif left <= 0 or not lock.acquire(timeout=min(left, threading.TIMEOUT_MAX)):
                raise TransportError("slow", "the lookup took too long")
        try:
            wait = MIN_INTERVAL_S[service] - (clock() - self._last.get(host, -1e9))
            if wait > 0:
                if deadline is not None and clock() + wait >= deadline:
                    raise TransportError("slow", "the lookup took too long")  # the request would start with nothing left: do not sleep to it
                sleep(wait)
            try:
                yield
            finally:
                self._last[host] = clock()
        finally:
            lock.release()


_SHARED_LIMITERS: dict = {}
_SHARED_GUARD = threading.Lock()


def shared_limiter(clock: Callable[[], float] | None = None) -> SpacingLimiter:
    """The one limiter of this process for ``clock`` (default ``time.monotonic``): what the chat gives every lookup's transport."""
    with _SHARED_GUARD:
        return _SHARED_LIMITERS.setdefault(clock or time.monotonic, SpacingLimiter())


class CachedTransport:
    """The polite wrapper the live skill uses around a raw fetch function ``fetch(service, request) -> body``.

    * a saved answer younger than its lifetime is returned with no request at all;
    * otherwise one request is made, at least ``MIN_INTERVAL_S`` after the last one to that server (``limiter``: pass
      ``shared_limiter()`` to keep the spacing across several transports; the default is private to this one);
    * at most ``MAX_PER_LOOKUP`` requests per ``begin_lookup()`` and ``MAX_PER_DAY`` per day (``budget`` error after);
    * when a refresh fails and an older saved answer exists, that is returned marked ``stale``;
    * ``max_seconds`` (optional): once a lookup (``begin_lookup`` to now) has run that long, no further request is made (``slow``), so a
      slow public server cannot keep the chat waiting for the sum of eight 60 second timeouts;
    * ``log(row)`` gets one row per request: when, service, key, outcome, seconds. Never the owner's message.
    The clock, the sleep and the log are injected, so the tests run in no time and touch no network.

    The per-day count is kept ON DISK (``day-count.json`` in the saved-answer folder, HIKE-LOOKUP-2), so a restart of Hass cannot
    reset it: every counted request is written before it is made. Checking the limit, adding one and writing the file is ONE step
    under a lock on ``day-count.lock`` (``flock``), so two clients of the same folder (Hass and the manual script, or two chat turns)
    can neither both take the last request nor overwrite each other's count. A count file that cannot be read or written fails CLOSED:
    the lookup is refused (``budget``) for the rest of that day, and the damaged file is set aside as ``day-count.bad``.
    """

    def __init__(self, fetch: Callable, folder, *, now: Callable[[], datetime] | None = None,
                 sleep: Callable[[float], None] | None = None, clock: Callable[[], float] | None = None,
                 log: Callable[[dict], None] | None = None, per_lookup: int = MAX_PER_LOOKUP, per_day: int = MAX_PER_DAY,
                 max_seconds: float | None = None, limiter: SpacingLimiter | None = None):
        self.fetch, self.folder = fetch, Path(folder)
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.sleep = sleep or time.sleep
        self.clock = clock or time.monotonic
        self.log = log or (lambda row: None)
        self.per_lookup, self.per_day, self.max_seconds = per_lookup, per_day, max_seconds
        self.limiter = limiter or SpacingLimiter()
        self.used_lookup, self.day_counts, self.began = 0, {}, None

    def begin_lookup(self):
        self.used_lookup = 0
        self.began = self.clock()

    def _path(self, key: str) -> Path:
        return self.folder / (key.replace(":", "-") + ".json")

    @property
    def counts_path(self) -> Path:
        return self.folder / COUNT_FILE

    def _counts(self, today: date) -> dict:
        """{iso day: requests made that day} from disk. No file is an empty record; a file that is not exactly that shape is
        set aside and today is counted as already used up (fail closed until tomorrow)."""
        try:
            raw = self.counts_path.read_text("utf-8")
        except FileNotFoundError:
            return {}
        except OSError:
            return {today.isoformat(): self.per_day}
        try:
            data = json.loads(raw)
            counts = data["counts"]
            if not isinstance(counts, dict) or not all(
                    isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and v >= 0 for k, v in counts.items()):
                raise ValueError("counts")
            for k in counts:
                date.fromisoformat(k)
            return dict(counts)
        except (ValueError, KeyError, TypeError, RecursionError):
            full = {today.isoformat(): self.per_day}
            try:
                self.counts_path.replace(self.counts_path.with_suffix(".bad"))
                self._write_counts(full)  # a fresh file that says "used up today", so the next call does not start from zero
            except OSError:
                pass
            return full

    def _write_counts(self, counts: dict):
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        keep = dict(sorted(counts.items())[-COUNT_DAYS_KEPT:])
        tmp = _unique_tmp(self.counts_path)  # never a name another writer could be using
        try:
            tmp.write_text(json.dumps({"counts": keep}, sort_keys=True), "utf-8")
            _fsync(tmp)
            tmp.replace(self.counts_path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return keep

    def day_count(self, today: date | None = None) -> int:
        """How many requests were made on ``today`` (default: the clock's day), read from disk."""
        today = today or self.now().date()
        self.day_counts = self._counts(today)
        return self.day_counts.get(today.isoformat(), 0)

    @contextmanager
    def _count_lock(self):
        """Exclusive lock on ``day-count.lock``, shared by every client of this folder (other processes and other threads). Waits at
        most ``COUNT_LOCK_SECONDS``; a lock that cannot be taken at all is an ``OSError`` (the caller refuses the request)."""
        if fcntl is None:
            raise OSError("no file locking on this system")
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.folder / COUNT_LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            deadline = time.monotonic() + COUNT_LOCK_SECONDS
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise OSError("the day count is busy") from None
                    time.sleep(0.01)
            yield
        finally:
            os.close(fd)  # closing the descriptor drops the lock

    def _reserve(self, today: date) -> bool:
        """ONE step, under the lock: read the day count, and if it is under ``per_day`` add one and write it to disk. True: this request
        is reserved (and counted) and may be made; False: the day's limit is used up. Raises ``TransportError("budget")`` when the count
        cannot be read, locked or saved."""
        try:
            with self._count_lock():
                counts = self._counts(today)
                if counts.get(today.isoformat(), 0) >= self.per_day:
                    self.day_counts = counts
                    return False
                counts[today.isoformat()] = counts.get(today.isoformat(), 0) + 1
                self.day_counts = self._write_counts(counts)
                return True
        except OSError:
            raise TransportError("budget", "the day count cannot be saved") from None

    def _read(self, key: str):
        try:
            rec = json.loads(self._path(key).read_text("utf-8"))
            return rec["body"], date.fromisoformat(rec["retrieved"])
        except (OSError, ValueError, KeyError, TypeError):  # TypeError: valid JSON with a wrong root or a non-text date is a miss too
            return None

    def _write(self, key, request, body, day):
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = _unique_tmp(self._path(key))
        try:
            tmp.write_text(json.dumps({"retrieved": day.isoformat(), "request": request, "body": body}, ensure_ascii=False), "utf-8")
            tmp.replace(self._path(key))
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def _time_left(self, at=None):
        """Seconds of the lookup's ``max_seconds`` still left (at clock reading ``at``, default now), or None when there is no limit
        (or no lookup has begun)."""
        if self.max_seconds is None or self.began is None:
            return None
        return self.max_seconds - ((self.clock() if at is None else at) - self.began)

    def _too_slow(self, service, key, saved) -> Response:
        self.log({"at": self.now().isoformat(), "service": service, "key": key, "outcome": "slow", "seconds": 0})
        if saved is not None:
            return Response(saved[0], saved[1], stale=True)
        raise TransportError("slow", "the lookup took too long")  # the chat is waiting: stop asking after ``max_seconds`` in all

    def _fetch(self, service, request, left):
        """One raw request. A fetch function that says it takes a ``timeout`` (``accepts_timeout``, as ``hike_fetch.LiveFetch`` does) is
        given the time left, so a request that starts just inside ``max_seconds`` cannot run on past it."""
        if left is not None and getattr(self.fetch, "accepts_timeout", False):
            return self.fetch(service, request, timeout=left)
        return self.fetch(service, request)

    def get(self, service: str, request: dict) -> Response:
        key, today = request_key(service, request), self.now().date()
        saved = self._read(key)
        age_ok = saved is not None and (today - saved[1]).days <= LIFETIME_DAYS[service]
        if age_ok:
            self.log({"at": self.now().isoformat(), "service": service, "key": key, "outcome": "saved", "seconds": 0})
            return Response(saved[0], saved[1])
        left = self._time_left()
        if left is not None and left <= 0:
            return self._too_slow(service, key, saved)
        try:
            over = self.used_lookup >= self.per_lookup or not self._reserve(today)  # counted on disk before the request is made
        except TransportError:
            over = True
        if over:
            if saved is not None:
                return Response(saved[0], saved[1], stale=True)
            self.log({"at": self.now().isoformat(), "service": service, "key": key, "outcome": "budget", "seconds": 0})
            raise TransportError("budget")
        self.used_lookup += 1
        deadline = None if self.max_seconds is None or self.began is None else self.began + self.max_seconds
        started, body, failure = None, None, None
        try:
            with self.limiter.hold(service, self.clock, self.sleep, deadline):  # waits its turn for this server, stamps the time when done
                started = self.clock()
                left = self._time_left(started)  # always worked out here, after the day count, the turn and the spacing took what time they took
                if left is not None and left <= 0:
                    failure = TransportError("slow", "the lookup took too long")
                else:
                    try:
                        body = self._fetch(service, request, left)
                    except TransportError as exc:
                        failure = exc
        except TransportError as exc:  # the turn or the spacing could not be had inside the lookup's time
            failure = exc
        if failure is not None:
            self.log({"at": self.now().isoformat(), "service": service, "key": key, "outcome": failure.kind,
                      "seconds": 0 if started is None else round(self.clock() - started, 2)})
            if saved is not None:
                return Response(saved[0], saved[1], stale=True)
            raise failure
        self._write(key, request, body, today)
        self.log({"at": self.now().isoformat(), "service": service, "key": key, "outcome": "fetched",
                  "seconds": round(self.clock() - started, 2)})
        return Response(body, today)


# -- names -------------------------------------------------------------------------------------------------------------


def _fold(text: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", plain.casefold().replace("'", "").replace("\u2019", "")).strip()


def name_tokens(text: str) -> list:
    """The words that identify a hike name: accents and punctuation folded, ``Mt``/``Pt`` spelled out, filler dropped. A word with
    a digit in it (a phone number, a zip code) is never kept, and at most ``MAX_NAME_WORDS`` words are: this is the only text of
    Mike's that can reach a map service."""
    text = re.sub(r"\S+@\S+|(?:https?://|www\.)\S+", " ", str(text))  # an address or link typed into the name never goes out
    words = [ABBREVIATIONS.get(w, w) for w in _fold(text).split()]
    return [w for w in words if w not in STOP_WORDS and not any(ch.isdigit() for ch in w)][:MAX_NAME_WORDS]


def name_regex(tokens) -> str:
    """A loose search pattern: the first four letters of each long word, in order. Typos past the fourth letter still find it;
    ``name_score`` then judges the real similarity."""
    return ".*".join(t[:4] if len(t) >= 5 else t for t in tokens)


def name_score(tokens, name) -> float:
    cand = name_tokens(name)
    if not cand:
        return 0.0
    q, c = " ".join(tokens), " ".join(cand)
    if q == c:
        return 1.0
    ratio = difflib.SequenceMatcher(None, q, c).ratio()
    if set(tokens) <= set(cand):  # all the words are there; the extra words decide how sure that is
        return max(ratio, 0.9 if set(cand) - set(tokens) <= TRAIL_WORDS else 0.78)
    return ratio


def overpass_query(tokens, bbox=SLO_BBOX) -> str:
    s, w, n, e = bbox
    rx = name_regex(tokens)
    return (f'[out:json][timeout:40];\n(\n'
            f' relation["route"~"^(hiking|foot)$"]["name"~"{rx}",i]({s},{w},{n},{e});\n'
            f' way["highway"~"^(path|footway|track|bridleway|steps)$"]["name"~"{rx}",i]({s},{w},{n},{e});\n'
            f' node["natural"="peak"]["name"~"{rx}",i]({s},{w},{n},{e});\n);\nout tags geom;')


def overpass_ids_query(ways, relations) -> str:
    parts = []
    if ways:
        parts.append("way(id:" + ",".join(str(i) for i in sorted(ways)) + ");")
    if relations:
        parts.append("relation(id:" + ",".join(str(i) for i in sorted(relations)) + ");")
    return "[out:json][timeout:40];\n(" + "".join(parts) + ");\nout tags geom;"


def nominatim_search_request(name: str) -> dict:
    left, top, right, bottom = CALIFORNIA_VIEWBOX
    return {"q": " ".join(str(name).split())[:80], "viewbox": f"{left},{top},{right},{bottom}", "bounded": 1,
            "countrycodes": "us", "limit": 10}


def outbound_names(name: str) -> dict:
    """Everything the first outbound requests carry from Mike's words: the search text built from the hike name. Used by the
    privacy test: it proves no other owner text, date, place or contact detail is in a request."""
    tokens = name_tokens(name)
    return {"overpass": overpass_query(tokens), "nominatim": nominatim_search_request(" ".join(tokens))}


# -- public-safe text ----------------------------------------------------------------------------------------------------


def clean_public(text, limit: int = 120) -> str:
    """Plain text safe for the page and for Mike: no markup, no invisible or control characters, one line, at most ``limit``."""
    out = re.sub(r"<[^>]*>", " ", INVISIBLE_RE.sub(" ", str(text)))  # whole tags go first, then any stray marker character
    for bad in FORBIDDEN_TEXT:
        out = out.replace(bad, " ")
    out = " ".join(unicodedata.normalize("NFC", out).split())
    return out[:limit].rstrip()


# -- geometry ----------------------------------------------------------------------------------------------------------


def haversine(a, b) -> float:
    """Metres between two (lat, lon) points."""
    (y1, x1), (y2, x2) = (tuple(map(math.radians, a)), tuple(map(math.radians, b)))
    h = math.sin((y2 - y1) / 2) ** 2 + math.cos(y1) * math.cos(y2) * math.sin((x2 - x1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def _vertex(point):
    return (round(point[0], 7), round(point[1], 7))


@dataclass
class Piece:
    ident: str  # "way/123" or "relation/45"
    name: str
    tags: dict
    coords: list  # [(lat, lon), ...]
    score: float = 0.0


def _bad(detail: str):
    return TransportError("bad", detail)


def _number(value, what: str) -> float:
    """A finite JSON number (never a bool or a string), or the answer is unreadable."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _bad(what)
    try:
        finite = math.isfinite(value)
    except OverflowError:  # an integer too large for a float cannot be used in the distance maths
        finite = False
    if not finite:
        raise _bad(what)
    return value


def _elements(body) -> list:
    """The ``elements`` list of an Overpass answer; anything else is an answer we cannot read."""
    if not isinstance(body, dict) or not isinstance(body.get("elements"), list):
        raise _bad("overpass body")
    return body["elements"]


def _geometry(raw, what: str) -> list:
    """[(lat, lon)] from an Overpass ``geometry`` list. A missing list is empty; a hole or a non-number is unreadable
    (dropping a point would quietly shorten the route)."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise _bad(what)
    out = []
    for g in raw:
        if not isinstance(g, dict):
            raise _bad(what)
        out.append((_number(g.get("lat"), what), _number(g.get("lon"), what)))
    return out


def _element_id(el) -> int | str:
    ident = el.get("id")
    if isinstance(ident, bool) or not (isinstance(ident, int) or (isinstance(ident, str) and ident.isascii() and ident.isdigit())):
        raise _bad("element id")
    return ident


def _pieces(elements, tokens):
    """Trail pieces and summit points from Overpass elements. A structure that is not what Overpass sends raises
    ``TransportError("bad")`` (the documented unreadable-answer reply) instead of an arbitrary Python error."""
    if not isinstance(elements, list):
        raise _bad("elements")
    pieces, summits = [], []
    for el in elements:
        if not isinstance(el, dict):
            raise _bad("element")
        tags = el.get("tags")
        if tags is None:
            tags = {}
        if not isinstance(tags, dict):
            raise _bad("tags")
        name = tags.get("name") or ""
        if not isinstance(name, str):
            raise _bad("name")
        score = name_score(tokens, name)
        if score < MATCH_MIN:
            continue
        if el.get("type") == "node":
            if "lat" in el and "lon" in el:
                summits.append((_vertex((_number(el["lat"], "node point"), _number(el["lon"], "node point"))), name))
        elif el.get("type") == "way":
            coords = _geometry(el.get("geometry"), "way geometry")
            if len(coords) >= 2:
                pieces.append(Piece(f"way/{_element_id(el)}", name, tags, coords, score))
        elif el.get("type") == "relation":
            members = el.get("members")
            if members is None:
                members = []
            if not isinstance(members, list):
                raise _bad("relation members")
            for member in members:
                if not isinstance(member, dict):
                    raise _bad("relation member")
                if member.get("type") != "way":
                    continue
                coords = _geometry(member.get("geometry"), "member geometry")
                if len(coords) >= 2:
                    pieces.append(Piece(f"relation/{_element_id(el)}", name, tags, coords, score))
    return pieces, summits


class _Union:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def join(self, a, b):
        self.p[self.find(a)] = self.find(b)


def build_groups(pieces):
    """Groups of pieces that make one trail: pieces sharing a point, pieces of one relation, and pieces with the same name whose
    nearest points are within ``BRIDGE_MAX_M`` (those gaps are returned so they can be counted, never hidden).
    Returns [(pieces, bridges)] where a bridge is (point_a, point_b, metres)."""
    union, by_vertex = _Union(len(pieces)), {}
    for i, piece in enumerate(pieces):
        for v in {_vertex(c) for c in piece.coords}:
            if v in by_vertex:
                union.join(i, by_vertex[v])
            else:
                by_vertex[v] = i
    by_relation = {}
    for i, piece in enumerate(pieces):
        if piece.ident.startswith("relation/"):
            union.join(i, by_relation.setdefault(piece.ident, i))
    bridges_by_root = {}
    names = {}
    for i, piece in enumerate(pieces):
        names.setdefault(" ".join(name_tokens(piece.name)), []).append(i)
    for same in names.values():  # nearest-point gaps between same-name pieces, joined shortest first
        gaps = []
        for x in range(len(same)):
            for y in range(x + 1, len(same)):
                a, b = pieces[same[x]], pieces[same[y]]
                best = min(((haversine(p, q), p, q) for p in (a.coords[0], a.coords[-1]) for q in (b.coords[0], b.coords[-1])),
                           key=lambda t: t[0])
                if best[0] <= BRIDGE_MAX_M:
                    gaps.append((best[0], same[x], same[y], best[1], best[2]))
        for metres, i, j, p, q in sorted(gaps):
            if union.find(i) != union.find(j):
                union.join(i, j)
                bridges_by_root.setdefault("all", []).append((i, j, _vertex(p), _vertex(q), metres))
    groups = {}
    for i, piece in enumerate(pieces):
        groups.setdefault(union.find(i), []).append(i)
    out = []
    for members in groups.values():
        member_set = set(members)
        bridges = [(p, q, m) for i, j, p, q, m in bridges_by_root.get("all", []) if i in member_set and j in member_set]
        out.append(([pieces[i] for i in members], bridges))
    return out


@dataclass
class Route:
    shape: str = ""  # loop | out-and-back | point-to-point | "" (not sure)
    one_way_m: float = 0.0  # length of the walked line (the loop, or one way of the path)
    miles: float = 0.0  # what Mike is told: the loop, the round trip, or one way
    path: list = field(default_factory=list)  # [(lat, lon)] of the walked line, one way
    unsure: str = ""  # why the skill is not sure; empty when it is sure
    bridge_m: float = 0.0
    spur_m: float = 0.0
    basis: str = ""  # how the shape was decided


def analyse(group_pieces, bridges, summits=()) -> Route:
    """Chain one group into a walkable line. See docs/hass/HIKE-LOOKUP.md question 2."""
    edges = {}
    for piece in group_pieces:
        for a, b in zip(piece.coords, piece.coords[1:]):
            va, vb = _vertex(a), _vertex(b)
            if va != vb:
                edges[frozenset((va, vb))] = (va, vb, haversine(a, b))
    for p, q, metres in bridges:
        if p != q:
            edges.setdefault(frozenset((p, q)), (p, q, metres))
    if not edges:
        return Route(unsure="no usable line")
    adj = {}
    for va, vb, metres in edges.values():
        adj.setdefault(va, []).append((vb, metres))
        adj.setdefault(vb, []).append((va, metres))
    bridge_m = sum(m for _p, _q, m in bridges)
    total = sum(m for _a, _b, m in edges.values())
    route = Route(bridge_m=bridge_m)
    if bridge_m > BRIDGE_SHARE_MAX * total:
        route.unsure = "the pieces do not join up"
        return route
    cycles = len(edges) - len(adj) + 1  # connected by construction
    leaves = [v for v, nb in adj.items() if len(nb) == 1]
    if cycles == 0:
        path, length = _longest_path(adj, leaves)
        route.spur_m = total - length
        if route.spur_m > SPUR_SHARE_MAX * total:
            route.unsure = "the trail branches in several places"
            return route
        route.path, route.one_way_m = path, length
        near_summit = any(haversine(path[0], s) <= SUMMIT_NEAR_M or haversine(path[-1], s) <= SUMMIT_NEAR_M for s, _n in summits)
        named = any(w in DESTINATION_WORDS for p in group_pieces for w in name_tokens(p.name))
        if near_summit or named:
            route.shape, route.basis = "out-and-back", "summit end" if near_summit else "destination name"
            route.miles = 2 * length / M_PER_MILE
        else:
            route.shape, route.basis = "point-to-point", "open line, no destination marked"
            route.miles = length / M_PER_MILE
    elif cycles == 1 and not leaves:
        route.shape, route.basis = "loop", "closed ring"
        route.path, route.one_way_m, route.miles = _ring(adj), total, total / M_PER_MILE
    else:
        route.unsure = "the trail has a loop with extra trail attached" if cycles == 1 else "the trail has several loops"
        return route
    if len(route.path) < 2 or route.miles <= 0:
        route.shape, route.unsure = "", "no usable line"
    elif route.one_way_m < MIN_HIKE_M:
        route.shape, route.unsure = "", "the map only has a very short piece of it"
    return route


def _longest_path(adj, leaves):
    """Leaf to leaf path of greatest length (a tree): two sweeps of Dijkstra."""
    import heapq

    def far(start):
        dist, prev, heap = {start: 0.0}, {}, [(0.0, start)]
        while heap:
            d, v = heapq.heappop(heap)
            if d > dist[v]:
                continue
            for w, m in adj[v]:
                if d + m < dist.get(w, 1e18):
                    dist[w], prev[w] = d + m, v
                    heapq.heappush(heap, (d + m, w))
        end = max(leaves, key=lambda v: dist.get(v, -1))
        return end, dist[end], prev

    a, _d, _p = far(sorted(leaves)[0])
    b, length, prev = far(a)
    path = [b]
    while path[-1] != a:
        path.append(prev[path[-1]])
    return path[::-1], length


def _ring(adj):
    start = sorted(adj)[0]
    path, prev, cur = [start], None, start
    while True:
        nxt = next((w for w, _m in sorted(adj[cur]) if w != prev), None)
        if nxt is None or nxt == start:
            break
        path.append(nxt)
        prev, cur = cur, nxt
    return path + [start]


# -- elevation --------------------------------------------------------------------------------------------------------


def sample_points(path):
    """Evenly spaced (lat, lon) along the line, both ends included, spacing >= 50 m, at most ``MAX_SAMPLES`` points."""
    cum = [0.0]
    for a, b in zip(path, path[1:]):
        cum.append(cum[-1] + haversine(a, b))
    length = cum[-1]
    n = max(2, min(MAX_SAMPLES, math.ceil(length / SAMPLE_SPACING_M) + 1))
    out, j = [], 1
    for k in range(n):
        d = length * k / (n - 1)
        while j < len(cum) - 1 and cum[j] < d:
            j += 1
        span = cum[j] - cum[j - 1]
        t = 0.0 if span == 0 else (d - cum[j - 1]) / span
        a, b = path[j - 1], path[j]
        out.append((round(a[0] + (b[0] - a[0]) * t, 6), round(a[1] + (b[1] - a[1]) * t, 6)))
    return out


def elevation_request(points) -> dict:
    return {"points": [[lon, lat] for lat, lon in points]}


def elevations_from(body, count):
    """Metres for each sample, in order, or None when the answer is incomplete or unreadable."""
    try:
        samples = body["samples"]
        if len(samples) != count:
            return None
        values = [None] * count
        for s in samples:
            i = _sample_position(s["locationId"])
            if i is None or i >= count or values[i] is not None:
                return None
            values[i] = float(s["value"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return values if all(math.isfinite(v) for v in values) else None


def _sample_position(raw):
    """A locationId as a route position: a non-bool int or ASCII digits only; anything else is None."""
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw if raw >= 0 else None
    if isinstance(raw, str) and raw.isascii() and raw.isdigit():
        return int(raw)
    return None


def climb_m(z, shape):
    """Metres climbed walking the whole route. 3-point median filter against sensor noise. Out and back: up out plus up back
    (= up plus down one way). Point to point: walked from the lower end. Loop: as sampled."""
    smooth = [z[0]] + [statistics.median(z[i - 1:i + 2]) for i in range(1, len(z) - 1)] + [z[-1]]
    if shape == "point-to-point" and smooth[0] > smooth[-1]:
        smooth.reverse()
    up = sum(max(0.0, b - a) for a, b in zip(smooth, smooth[1:]))
    down = sum(max(0.0, a - b) for a, b in zip(smooth, smooth[1:]))
    return up + down if shape == "out-and-back" else up


def elevation_gain_ft(z, shape) -> int:
    return int(round(climb_m(z, shape) * FT_PER_M, -1))


# -- candidates and the lookup -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    name: str
    miles: float | None  # rounded to 0.1; None when not sure
    gain_ft: int | None  # nearest 10 ft; None when unknown
    shape: str  # loop | out-and-back | point-to-point | "" (not sure)
    source: str
    retrieved: date
    place: str = ""
    osm: tuple = ()  # ("way/175094087", ...)
    unsure: str = ""
    notes: tuple = ()  # closure or warning text found in the source tags (public-safe)
    stale: bool = False
    stage: str = "slo"  # slo | california
    score: float = 0.0
    basis: str = ""
    record: dict = field(default_factory=dict, compare=False)

    @property
    def sure(self) -> bool:
        return not self.unsure and self.miles is not None


@dataclass(frozen=True)
class LookupResult:
    status: str  # one | several | none | unsure | place_only | known | unavailable
    reply: str  # what Mike reads (voice rules; marked words are the map's names)
    candidates: tuple = ()
    total: int = 0  # how many matched before the offer was cut to MAX_OFFER
    stale: bool = False
    failure: str = ""  # network | slow | busy | budget | bad when status is unavailable
    idea_id: str = ""  # status known: the existing route idea to put the hike on


def _group_name(group_pieces, tokens) -> str:
    names = {p.name for p in group_pieces}
    if len(names) == 1:
        return clean_public(next(iter(names)))
    split = [n.split() for n in names]
    prefix = []
    for words in zip(*split):
        if len({w.casefold() for w in words}) != 1:
            break
        prefix.append(words[0])
    if prefix and set(name_tokens(" ".join(prefix))) >= set(tokens[:len(prefix)]) and len(name_tokens(" ".join(prefix))) >= min(2, len(tokens)):
        return clean_public(" ".join(prefix))
    longest = max(group_pieces, key=lambda p: sum(haversine(a, b) for a, b in zip(p.coords, p.coords[1:])))
    return clean_public(longest.name)  # no shared name: the longest piece names the group


def closure_notes(group_pieces) -> tuple:
    found = []
    for piece in group_pieces:
        tags = piece.tags
        if str(tags.get("access", "")).casefold() in CLOSURE_ACCESS:
            found.append(f"access is marked {clean_public(tags['access'], 20)}")
        if any(k in tags for k in ("disused:highway", "abandoned:highway", "construction")) or tags.get("highway") == "construction":
            found.append("the trail is marked as under construction or no longer used")
        for key in CLOSURE_KEYS:
            if key in tags and CLOSURE_WORDS.search(str(tags[key])):
                found.append(clean_public(tags[key], 120))
    return tuple(dict.fromkeys(found))


def _centre(path):
    return (sum(p[0] for p in path) / len(path), sum(p[1] for p in path) / len(path))


def _place_from(body) -> str:
    addr = (body or {}).get("address") if isinstance(body, dict) else None
    if not isinstance(addr, dict):
        return ""
    for key in ("hamlet", "village", "town", "city", "suburb", "neighbourhood", "county"):
        if addr.get(key):
            return clean_public(addr[key], 60)
    return ""


def _finish(transport, group_pieces, bridges, summits, tokens, stage, today, geometry=()):
    """One candidate: route, place and climb, every number from the retrieved records. ``geometry``: the (retrieved, stale)
    of each answer the names and lines came from, so a saved copy of the map is never passed off as fresh."""
    route = analyse(group_pieces, bridges, summits)
    used, retrieved, stale = [], [d for d, _old in geometry], any(old for _d, old in geometry)
    path = route.path or [group_pieces[0].coords[0]]
    centre = _centre(path)
    place = ""
    try:
        r = transport.get("nominatim_reverse", {"lat": round(centre[0], 4), "lon": round(centre[1], 4), "zoom": 12})
        place, retrieved, stale = _place_from(r.body), retrieved + [r.retrieved], stale or r.stale
        used.append("nominatim_reverse")
    except TransportError:
        place = ""  # the place is a nicety; the numbers are what matter
    gain = None
    if route.shape and not route.unsure:
        points = sample_points(route.path)
        try:
            r = transport.get("elevation", elevation_request(points))
            z = elevations_from(r.body, len(points))
            if z is not None:
                gain = elevation_gain_ft(z, route.shape)
                retrieved.append(r.retrieved)
                stale = stale or r.stale
                used.append("elevation")
        except TransportError:
            gain = None
    ident = tuple(dict.fromkeys(p.ident for p in group_pieces))
    name = _group_name(group_pieces, tokens)
    day = min(retrieved) if retrieved else today  # the oldest record used: a stale part makes the whole answer that old
    miles = round(route.miles, 1) if route.shape and not route.unsure else None
    record = {"version": VERSION, "query": " ".join(tokens), "osm": list(ident), "name": name, "shape": route.shape,
              "shape_basis": route.basis, "one_way_m": round(route.one_way_m, 1), "bridge_m": round(route.bridge_m, 1),
              "spur_m": round(route.spur_m, 1), "miles": miles, "gain_ft": gain, "unsure": route.unsure,
              "sources": {"names_and_lines": "OpenStreetMap contributors (ODbL) via Overpass",
                          "elevation": "USGS 3DEP", "place": "OpenStreetMap Nominatim"},
              "retrieved": day.isoformat(), "samples": len(sample_points(route.path)) if route.path else 0,
              "tags": {p.ident: {k: v for k, v in p.tags.items() if k in ("name", "highway", "route", "access", "surface")} for p in group_pieces}}
    return Candidate(name=name, miles=miles, gain_ft=gain, shape=route.shape if not route.unsure else "", source=SOURCE_NAME,
                     retrieved=day, place=place, osm=ident, unsure=route.unsure, notes=closure_notes(group_pieces), stale=stale,
                     stage=stage, score=max(p.score for p in group_pieces), basis=route.basis, record=record)


def _rank(groups, summits=()):
    """Best first: a trail whose distance is known before one that is not, then the closest name, then the nearest to the shop."""
    def key(item):
        group_pieces, bridges = item
        centre = _centre([c for p in group_pieces for c in p.coords])
        sure = not analyse(group_pieces, bridges, summits).unsure
        return (not sure, -round(max(p.score for p in group_pieces), 2), haversine(centre, HOME))
    return sorted(groups, key=key)


def _unavailable(kind) -> LookupResult:
    return LookupResult("unavailable", UNAVAILABLE[kind if kind in UNAVAILABLE else "network"], failure=kind)


def known_route_idea(name: str, route_ideas) -> dict | None:
    """Step 0: a route idea Hass already has (reviewed, from hass/content/community.json) that fits the name. It is used as it is
    and nothing is looked up online. Best score of at least MATCH_MIN wins; a tie is no answer (ask, never pick)."""
    tokens = name_tokens(name)
    scored = sorted(((name_score(tokens, i.get("title") or ""), i) for i in route_ideas or ()
                     if isinstance(i, dict) and i.get("status") == "idea"), key=lambda t: -t[0])
    if not scored or scored[0][0] < MATCH_MIN or (len(scored) > 1 and scored[1][0] >= MATCH_MIN and scored[1][0] == scored[0][0]):
        return None
    return scored[0][1]


def known_reply(idea: dict) -> str:
    far = f", {idea['distance']}" if idea.get("distance") else ""
    return (f"You already have a route idea called {voice.quote(clean_public(idea['title'], 60))}{far}. I'll use that one, with no new lookup. "
            "Tell me the day, the time and where to meet, and I'll set up the hike.")


def lookup(name: str, transport, *, today: date | None = None, max_offer: int = MAX_OFFER, route_ideas=None) -> LookupResult:
    """A hike name in, candidates and the words for Mike out. ``transport.get(service, request) -> Response``.
    ``route_ideas``: the route ideas Hass already has; a fit is used first and nothing goes out."""
    today = today or date.today()
    tokens = name_tokens(name)
    if len("".join(tokens)) < 3:
        return LookupResult("none", NEED_A_NAME)
    if (idea := known_route_idea(name, route_ideas)) is not None:
        return LookupResult("known", known_reply(idea), idea_id=idea["id"])
    try:
        found = transport.get("overpass", {"query": overpass_query(tokens)})
        pieces, summits = _pieces(_elements(found.body), tokens)
        stage, stale, geometry = "slo", found.stale, [(found.retrieved, found.stale)]
        if not pieces:
            pieces, summits_ca, places, geometry_ca = _california(tokens, transport)
            stage, stale = "california", any(old for _d, old in geometry_ca)
            geometry = geometry_ca + (geometry if summits else [])  # the county answer counts only if its summit point is used
            summits = summits + summits_ca
            if not pieces:
                return LookupResult("place_only" if places else "none", (PLACE_ONLY if places else NO_MATCH).format(name=voice.quote(clean_public(name, 60))))
        groups = _rank(build_groups(pieces), summits)
        offered = groups[:max_offer]
        candidates = tuple(_finish(transport, gp, br, summits, tokens, stage, today, geometry) for gp, br in offered)
    except TransportError as exc:
        return _unavailable(exc.kind)
    stale = stale or any(c.stale for c in candidates)
    total = len(groups)
    if total == 1:
        c = candidates[0]
        return LookupResult("one" if c.sure else "unsure", proposal(c) if c.sure else not_sure(c), candidates, total, stale)
    return LookupResult("several", choices(candidates, total), candidates, total, stale)


def _california(tokens, transport):
    """Second stage: Nominatim over California, then the geometry of the trails it names. Returns the pieces, summits,
    places and the (retrieved, stale) of every answer the trails came from."""
    r = transport.get("nominatim_search", nominatim_search_request(" ".join(tokens)))
    if not isinstance(r.body, list) or not all(isinstance(h, dict) for h in r.body):
        raise _bad("nominatim body")
    for h in r.body:  # the fields read below must be text, or the answer is unreadable
        if any(h.get(k) is not None and not isinstance(h.get(k), str) for k in ("name", "display_name", "category", "type", "osm_type")):
            raise _bad("nominatim hit")
    hits = [h for h in r.body if name_score(tokens, h.get("name") or (h.get("display_name") or "").split(",")[0]) >= MATCH_MIN]
    trails = [h for h in hits if h.get("category") in ("highway", "route") and h.get("type") in PATH_TYPES]  # never a street
    for h in trails:
        if isinstance(h.get("osm_id"), bool) or not isinstance(h.get("osm_id"), int):
            raise _bad("nominatim id")
    ways = {h["osm_id"] for h in trails if h.get("osm_type") == "way"}
    relations = {h["osm_id"] for h in trails if h.get("osm_type") == "relation"}
    places = [h for h in hits if h.get("category") in ("natural", "place", "leisure", "boundary", "tourism")]
    if not (ways or relations):
        return [], [], places, [(r.retrieved, r.stale)]
    g = transport.get("overpass", {"query": overpass_ids_query(ways, relations)})
    pieces, _s = _pieces(_elements(g.body), tokens)
    return pieces, [], places, [(r.retrieved, r.stale), (g.retrieved, g.stale)]


# -- words for Mike ------------------------------------------------------------------------------------------------------

NEED_A_NAME = "Which hike do you mean? Tell me its name, like Bishop Peak."
NO_MATCH = ("I couldn't find a trail called {name} on the map. I won't guess. "
            "Could you say it another way, or tell me the park or trailhead it is near?")
PLACE_ONLY = ("I found a place called {name} on the map, but no trail to it, so I can't give you a distance. "
              "Do you know how far it is?")
UNAVAILABLE = {
    "network": "I can't reach the map right now, so I couldn't look that hike up. Nothing was changed. "
               "Try again in a little while, or tell me the distance yourself.",
    "slow": "The map is slow to answer right now, so I stopped waiting. Nothing was changed. Try again in a few minutes.",
    "busy": "The map asked me to wait a bit before asking again. Nothing was changed. Try again in a few minutes.",
    "budget": "I've looked up a lot of trails today, so I'm stopping for now. Nothing was changed. Try again tomorrow, "
              "or tell me the distance yourself.",
    "missing": "I can't reach the map right now, so I couldn't look that hike up. Nothing was changed. "
               "Try again in a little while, or tell me the distance yourself.",
    "bad": "The map gave me an answer I can't read, so I couldn't look that hike up. Nothing was changed. "
           "Try again later, or tell me the distance yourself.",
}


def _day(d: date) -> str:
    return f"{d:%b} {d.day}"


def _gain_words(c: Candidate) -> str:
    return f"about {c.gain_ft:,} feet of climbing" if c.gain_ft is not None else "no climbing figure I trust"


def _facts(c: Candidate) -> str:
    lower = " from the lower end" if c.shape == "point-to-point" and c.gain_ft is not None else ""
    return f"about {c.miles:.1f} miles {SHAPE_WORDS[c.shape]} on the map, with {_gain_words(c)}{lower}"


def _where(c: Candidate) -> str:
    if not c.place:
        return ""
    return f" in {voice.quote(c.place)}" if c.place.endswith("County") else f" near {voice.quote(c.place)}"


def _closure(c: Candidate) -> str:
    if not c.notes:
        return ""
    return f" The map notes say {voice.quote(c.notes[0])}. Please check with the park before we plan anything."


def _stale(c: Candidate) -> str:
    return f" This is from a saved copy from {_day(c.retrieved)}, and I couldn't check it again today." if c.stale else ""


def facts(c: Candidate) -> str:
    """``about 2.4 miles out and back on the map, with about 740 feet of climbing`` for a sure candidate (measured numbers only)."""
    return _facts(c)


def warnings(c: Candidate) -> list:
    """The park-check and saved-copy sentences of a candidate (each a whole sentence), for the line beside a draft."""
    return [s.strip() for s in (_closure(c), _stale(c)) if s.strip()]


def proposal(c: Candidate) -> str:
    """THE proposal sentence for one sure candidate:
    ``Did you mean "<name>" near <place>, about <x.x> miles <a loop | out and back | one way>, with about <n> feet of climbing? Reply yes to use it, or no and tell me more.``"""
    lead = "I didn't find that near San Luis Obispo. " if c.stage == "california" else ""
    return (f"{lead}Did you mean {voice.quote(c.name)}{_where(c)}, {_facts(c)}?{_closure(c)}{_stale(c)} "
            "Reply yes to use it, or no and tell me more.")


def not_sure(c: Candidate) -> str:
    return (f"I found {voice.quote(c.name)}{_where(c)}, but {c.unsure}, so I'm not sure how far it is or what shape it is."
            f"{_closure(c)}{_stale(c)} I won't guess. Do you know the distance, or have a link to a trail guide?")


def _line(n: int, c: Candidate) -> str:
    if c.sure:
        return f"{n}. {voice.quote(c.name)}{_where(c)}, {_facts(c)}"
    return f"{n}. {voice.quote(c.name)}{_where(c)}, and I'm not sure of its distance"


def _line_notes(n: int, c: Candidate) -> str:
    """The park-check warning for one offered trail, tied to its number."""
    if not c.notes:
        return ""
    return f" For {n}, the map notes say {voice.quote(c.notes[0])}. Please check with the park before we plan anything."


def _stale_many(cands) -> str:
    """One saved-copy sentence for the offered trails that rest on an old answer (dated by the oldest of them)."""
    old = [(i, c) for i, c in enumerate(cands, 1) if c.stale]
    if not old:
        return ""
    day = _day(min(c.retrieved for _i, c in old))
    nums = [str(i) for i, _c in old]
    joined = nums[0] if len(nums) == 1 else ", ".join(nums[:-1]) + " and " + nums[-1]
    which = "These are" if len(old) == len(cands) else f"For {joined}, this is"
    return f" {which} from a saved copy from {day}, and I couldn't check it again today."


def choices(cands, total: int) -> str:
    n = len(cands)
    more = f" There are more than {n} that fit; tell me more of the name if none is right." if total > n else ""
    pick = "Reply 1 or 2" if n == 2 else f"Reply {', '.join(str(i) for i in range(1, n))} or {n}"
    lines = " ".join(_line(i, c) for i, c in enumerate(cands, 1))
    notes = "".join(_line_notes(i, c) for i, c in enumerate(cands, 1)) + _stale_many(cands)
    return f"I found {n} that fit. Which one do you mean? {lines}.{notes} {pick}, or no if it isn't one of these.{more}"


# -- into the existing Hass path ----------------------------------------------------------------------------------------


def route_id(title: str, used=()) -> str:
    """The id ``route.add`` will give a new route idea (same slug rule as hass.ops.routes._route_add)."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", title) if not unicodedata.combining(c))
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    base = f"idea-{slug}"[:60].rstrip("-")
    new, n = base, 1
    while new in used:
        n += 1
        new = f"{base}-{n}"
    return new


def source_url(c: Candidate) -> str:
    kind, _, num = (c.osm[0] if c.osm else "").partition("/")
    return f"https://www.openstreetmap.org/{kind}/{num}" if kind in ("way", "relation") and num.isascii() and num.isdigit() else "https://www.openstreetmap.org/"


def route_add_args(c: Candidate) -> dict:
    """The arguments of the existing ``route.add`` op for a confirmed candidate. Only measured numbers; every other required
    text says it is still to be confirmed (the page already prints that sentence for a missing fact)."""
    if not c.sure:
        raise ValueError("a candidate that is not sure is never turned into a route idea")
    tbc = "To be confirmed"
    gain = f"About {c.gain_ft:,} ft" if c.gain_ft is not None else tbc
    return {"title": c.name, "place": c.place or ("San Luis Obispo County area" if c.stage == "slo" else "California"),
            "character": tbc, "distance": f"{c.miles:.1f} miles", "difficulty": tbc, "elevation": gain,
            "elevationLabel": "Elevation gain", "duration": tbc, "routeType": SHAPE_ROUTE_TYPE[c.shape], "terrain": tbc,
            "description": f"About {c.miles:.1f} miles, {SHAPE_WORDS[c.shape]}. Michael will share the details soon.",
            "sourceUrl": source_url(c), "sourceName": f"{c.source}, retrieved {_day(c.retrieved)}, {c.retrieved.year}"}


def plan_ops(c: Candidate, hike: dict | None = None, used_ids=()) -> list:
    """Ops for the existing editor. With no ``hike`` the plan is ONE ``route.add`` (a route idea: undated, no sign-up). A hike
    is added only from Mike's own confirmed ``date`` (YYYY-MM-DD), ``time`` (HH:MM) and ``meetingPoint``; the time zone is
    the shop's (the ``hike.create`` op fixes America/Los_Angeles). Anything missing raises, so a looked-up route can never
    become a real event by itself."""
    ops = [{"op": "route.add", "args": route_add_args(c)}]
    if hike is None:
        return ops
    missing = [k for k in ("date", "time", "meetingPoint") if not str(hike.get(k) or "").strip()]
    if missing:
        raise ValueError("a hike needs the confirmed " + ", ".join(missing))
    args = {"title": hike.get("title") or c.name, "date": hike["date"], "time": hike["time"], "meetingPoint": hike["meetingPoint"],
            "rsvpEnabled": bool(hike.get("rsvpEnabled", False)), "trailId": route_id(c.name, used_ids)}
    for k in ("capacity", "noCapacityLimit", "description", "bring", "difficulty"):
        if k in hike:
            args[k] = hike[k]
    ops.append({"op": "hike.create", "args": args})
    return ops


# -- HIKE-LOOKUP-2: what the chat flow keeps and reads -------------------------------------------------------------------


LOG_FILE = "requests.log"
LOG_MAX_BYTES = 1_000_000  # the request log stops growing at 1 MB (rows are small: no text, no coordinates)
_OSM_ID = re.compile(r"(?:way|relation)/\d+")
CONTACT_RE = re.compile(r"(?:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|https://[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[A-Za-z0-9._~%/-]*)?)")
CONTACT_MAX = 100


def valid_contact(value) -> str | None:
    """The operator's contact address for the map services' User-Agent (the ``hikeLookup.contact`` setting): an e-mail address
    or an https link, printable ASCII, no spaces, at most ``CONTACT_MAX`` characters. Anything else is None. No address is built in."""
    if not isinstance(value, str) or not value.isascii() or len(value) > CONTACT_MAX:
        return None
    return value if CONTACT_RE.fullmatch(value) else None


def file_log(folder) -> Callable[[dict], None]:
    """A ``CachedTransport`` log that appends one JSON row per request (when, service, key, outcome, seconds: never query text,
    coordinates or reply text) to ``<folder>/requests.log``. A write that fails is dropped: the log is a record, not a gate."""
    path = Path(folder) / LOG_FILE

    def write(row: dict) -> None:
        try:
            Path(folder).mkdir(parents=True, exist_ok=True, mode=0o700)
            if path.exists() and path.stat().st_size > LOG_MAX_BYTES:
                return
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({k: row.get(k) for k in ("at", "service", "key", "outcome", "seconds")}, sort_keys=True) + "\n")
        except OSError:
            pass

    return write


def candidate_to_json(c: Candidate) -> dict:
    """A candidate as plain JSON (kept privately between the question and Mike's answer)."""
    return {"name": c.name, "miles": c.miles, "gain_ft": c.gain_ft, "shape": c.shape, "source": c.source,
            "retrieved": c.retrieved.isoformat(), "place": c.place, "osm": list(c.osm), "unsure": c.unsure,
            "notes": list(c.notes), "stale": c.stale, "stage": c.stage, "score": c.score, "basis": c.basis, "record": c.record}


def _own_text(data: dict, key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(key)
    return value


def candidate_from_json(data) -> Candidate | None:
    """The candidate ``candidate_to_json`` wrote, or None when the data is not exactly that (a damaged or edited file is never
    half-trusted). Text is cleaned again, and a number without a known shape is dropped."""
    try:
        if not isinstance(data, dict):
            return None
        miles, gain, shape, osm, notes = data["miles"], data["gain_ft"], _own_text(data, "shape"), data["osm"], data["notes"]
        if miles is not None:
            miles = float(_number(miles, "miles"))
        if gain is not None and (isinstance(gain, bool) or not isinstance(gain, int)):
            return None
        if shape not in SHAPE_WORDS and shape != "":
            return None
        if not (isinstance(osm, list) and all(isinstance(o, str) and _OSM_ID.fullmatch(o) for o in osm)):
            return None
        if not (isinstance(notes, list) and all(isinstance(n, str) for n in notes)) or data["stage"] not in ("slo", "california"):
            return None
        if not isinstance(data["stale"], bool) or not isinstance(data["record"], dict):
            return None
        unsure = clean_public(_own_text(data, "unsure"))
        if not shape or unsure:
            miles, shape = None, ""
        return Candidate(name=clean_public(_own_text(data, "name")), miles=miles, gain_ft=gain, shape=shape,
                         source=_own_text(data, "source"), retrieved=date.fromisoformat(_own_text(data, "retrieved")),
                         place=clean_public(_own_text(data, "place"), 60), osm=tuple(osm), unsure=unsure,
                         notes=tuple(clean_public(n) for n in notes), stale=data["stale"], stage=data["stage"],
                         score=float(_number(data["score"], "score")), basis=_own_text(data, "basis"), record=data["record"])
    except (KeyError, ValueError, TypeError, TransportError):
        return None


_YES_WORDS = {"yes", "yeah", "yep", "yup", "y", "ok", "okay", "sure", "correct", "right", "exactly", "please", "thanks", "thank",
              "you", "that", "thats", "that's", "is", "it", "the", "one", "use", "do"}
_YES_FIRST = {"yes", "yeah", "yep", "yup", "y", "ok", "okay", "sure", "correct", "right", "exactly", "that", "thats", "that's", "use", "do"}
_NO_FIRST = {"no", "nope", "nah", "neither", "none", "not"}
_ORDINAL = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3}


def read_answer(text, offered: int) -> tuple:
    """Mike's short reply to the identity question as ``(kind, index)``: ``("pick", i)`` (a 0-based position of the trail he chose;
    for ONE offered trail a plain yes is a pick), ``("yes", None)`` (a yes when several were offered: which one is not said),
    ``("no", None)`` (no, or no and something more) or ``("other", None)`` (anything else, including a long message). Never
    guesses: a number outside the offered range is ``other``."""
    words = re.sub(r"[^a-z0-9' ]+", " ", str(text).casefold().replace("\u2019", "'")).split()
    if not words:
        return ("other", None)
    if len(words) == 2 and re.fullmatch(r"[0-9a-f]{4,12}", words[1]) and words[0] in _YES_FIRST | _NO_FIRST:
        return ("other", None)  # "yes a1b2" / "no a1b2" name a draft by its code: that is an approval or a cancel, never this answer
    if words[0] in _NO_FIRST:
        return ("no", None)
    if len(words) > 5:
        return ("other", None)
    if len(words) > 1 and words[0] in ("number", "option", "the"):
        words = words[1:]
    if len(words) == 2 and words[1] == "one" and words[0] in _ORDINAL:
        words = words[:1]
    pick = None
    if len(words) == 1:
        pick = int(words[0]) if words[0].isdigit() and len(words[0]) == 1 else _ORDINAL.get(words[0])
    if pick is not None:
        return ("pick", pick - 1) if 1 <= pick <= offered else ("other", None)
    if words[0] in _YES_FIRST and all(w in _YES_WORDS for w in words):
        return ("pick", 0) if offered == 1 else ("yes", None)
    return ("other", None)
