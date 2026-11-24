"""HASS-CLOVER-1: the read-only client against recorded fixtures, with no network. Only a FAKE token and a fake merchant id are used.
Run: python3 -B -m unittest hass.tests.test_clover_client
"""
import email.message
import io
import json
import logging
import pickle
import traceback
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from hass.clover import client as cl
from hass.clover.credential import Token
from hass.clover.transport import ALLOWED_NETLOCS, ReplayTransport, UrllibTransport, _NoRedirect

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "clover"
FAKE_TOKEN = "FAKE-TOKEN-FOR-TESTS-ONLY-0001"
MID = "FAKEMERCH0001"
BASE = f"/v3/merchants/{MID}"
ITEMS_Q = "expand=itemStock,categories,tags&limit=1000&offset=0"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class NoNetwork(unittest.TestCase):
    """Any attempt to open a socket in a test fails the test (the client's own error handling cannot hide it: the mock is asserted)."""

    def setUp(self):
        super().setUp()
        patches = [mock.patch("socket.socket.connect"), mock.patch("socket.create_connection"), mock.patch("socket.getaddrinfo")]
        self.net = [p.start() for p in patches]
        self.addCleanup(mock.patch.stopall)
        self.addCleanup(lambda: [self.assertFalse(m.called, "a test touched the network") for m in self.net])


class FakeClock:
    def __init__(self):
        self.now, self.sleeps = 0.0, []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def make(recorded, **kw):
    transport = ReplayTransport(recorded)
    clock = kw.pop("clock", None) or FakeClock()
    kw.setdefault("min_interval", 0)
    client = cl.CloverClient(MID, Token(FAKE_TOKEN), transport, sleep=clock.sleep, monotonic=clock.monotonic, **kw)
    return client, transport, clock


ITEMS_OK = {f"{BASE}/items?{ITEMS_Q}": (200, {}, fixture("items.json"))}


class ReadTests(NoNetwork):
    def test_list_items_sends_one_authorised_get_and_returns_the_elements(self):
        client, transport, _ = make(ITEMS_OK)
        items = client.list_items()
        self.assertEqual([i["id"] for i in items], [f"FAKEITEM0000{n}" for n in range(1, 7)])
        (req,) = transport.seen
        self.assertEqual(req.method, "GET")
        self.assertEqual(req.url, f"https://apisandbox.dev.clover.com{BASE}/items?{ITEMS_Q}")
        self.assertEqual(req.headers["Authorization"], "Bearer " + FAKE_TOKEN)
        self.assertIn("read-only", req.headers["User-Agent"])
        self.assertIsNone(req.body)

    def test_production_uses_the_production_host_only_when_asked(self):
        transport = ReplayTransport({f"{BASE}/categories?limit=1000&offset=0": (200, {}, fixture("categories.json"))})
        client = cl.CloverClient(MID, Token(FAKE_TOKEN), transport, "production", min_interval=0)
        client.list_categories()
        self.assertTrue(transport.seen[0].url.startswith("https://api.clover.com/v3/merchants/"))

    def test_paging_follows_offsets_until_a_short_page(self):
        els = fixture("items.json")["elements"]
        q = "expand=itemStock,categories,tags&limit=2&offset="
        client, transport, _ = make({f"{BASE}/items?{q}0": (200, {}, {"elements": els[0:2]}), f"{BASE}/items?{q}2": (200, {}, {"elements": els[2:4]}),
                                     f"{BASE}/items?{q}4": (200, {}, {"elements": els[4:5]})}, page_size=2)
        self.assertEqual(len(client.list_items()), 5)
        self.assertEqual(len(transport.seen), 3)

    def test_incremental_pull_filters_on_modified_time(self):
        client, transport, _ = make({f"{BASE}/items?expand=itemStock,categories,tags&limit=1000&filter=modifiedTime>=1794250000000&offset=0":
                                     (200, {}, {"elements": []})})
        self.assertEqual(client.list_items(modified_since_ms=1794250000000), [])
        for bad in (-1, True, "1", 1.5):
            with self.assertRaises(cl.CloverRefused):
                client.list_items(modified_since_ms=bad)

    def test_the_other_reads(self):
        client, _, _ = make({f"{BASE}/items/FAKEITEM00001?expand=itemStock,categories,tags": (200, {}, fixture("items.json")["elements"][0]),
                             f"{BASE}/item_stocks/FAKEITEM00001": (200, {}, fixture("item_stock.json")),
                             f"{BASE}/item_stocks?limit=1000&offset=0": (200, {}, {"elements": [fixture("item_stock.json")]}),
                             f"{BASE}/categories?limit=1000&offset=0": (200, {}, fixture("categories.json")),
                             f"{BASE}/items?filter=sku=AS-PAN-SUNSHINE-OLIVE-OIL-01&limit=10": (200, {}, {"elements": [{"id": "FAKEITEM00001"}]})})
        self.assertEqual(client.get_item("FAKEITEM00001")["name"], "Sunshine olive oil")
        self.assertEqual(client.get_stock("FAKEITEM00001")["quantity"], 12.0)
        self.assertEqual(len(client.list_stocks()), 1)
        self.assertEqual([c["name"] for c in client.list_categories()][:2], ["Pantry", "Fruit"])
        self.assertEqual(len(client.find_by_sku("AS-PAN-SUNSHINE-OLIVE-OIL-01")), 1)


class RefusalTests(NoNetwork):
    """Read-only and items-and-stock-only are enforced before a request exists."""

    def setUp(self):
        super().setUp()
        self.client, self.transport, _ = make({})

    def test_only_the_item_stock_category_and_tag_reads_exist(self):
        public = {n for n in dir(self.client) if not n.startswith("_")}
        self.assertEqual(public, {"build", "environment", "find_by_sku", "get_item", "get_stock", "list_categories", "list_items", "list_stocks",
                                  "get_merchant", "first_items"})

    def test_sales_customer_and_staff_paths_are_refused(self):
        for path in ("/orders", "/orders/ABC", "/payments", "/payments/ABC", "/customers", "/employees", "/employees/ABC/shifts", "/refunds",
                     "/credits", "/devices", "/properties", "/tags", "/", "/items/", "/items/AB/orders", "/items/../orders", "/items/A%2Fb",
                     "/items/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "/v3/merchants/OTHER/items", "/category_items", "/item_groups"):
            with self.subTest(path=path), self.assertRaises(cl.CloverRefused):
                self.client.build("GET", path, {})
        self.assertEqual(self.transport.seen, [])

    def test_every_method_but_get_is_refused(self):
        for method in ("POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "get"):
            with self.subTest(method=method), self.assertRaises(cl.CloverRefused):
                self.client.build(method, "/items", {})

    def test_bad_settings_and_ids_are_refused(self):
        with self.assertRaises(cl.CloverRefused):
            cl.CloverClient(MID, Token(FAKE_TOKEN), self.transport, "staging")
        for mid in ("", "../x", "FAKE MERCH 01", "a" * 40, None, 5):
            with self.subTest(mid=mid), self.assertRaises(cl.CloverRefused):
                cl.CloverClient(mid, Token(FAKE_TOKEN), self.transport)
        for sku in ("", "a b", "x" * 100, "a&b=c", None):
            with self.subTest(sku=sku), self.assertRaises(cl.CloverRefused):
                self.client.find_by_sku(sku)
        for kw in ({"page_size": 0}, {"page_size": 1001}, {"max_retries": 6}):
            with self.assertRaises(cl.CloverRefused):
                cl.CloverClient(MID, Token(FAKE_TOKEN), self.transport, **kw)

    def test_a_malformed_item_id_in_the_path_is_refused(self):
        for bad in ("x/../y", "a b", "a?b=c", "a" * 40):
            with self.subTest(bad=bad), self.assertRaises(cl.CloverRefused):
                self.client.get_item(bad)


class ErrorTests(NoNetwork):
    def run_status(self, status, headers=None, **kw):
        client, transport, clock = make({f"{BASE}/categories?limit=1000&offset=0": [(status, headers or {}, {"message": "x"})]}, **kw)
        with self.assertRaises(cl.CloverError) as ctx:
            client.list_categories()
        return ctx.exception, transport, clock

    def test_status_mapping(self):
        exc, _, _ = self.run_status(401)
        self.assertIsInstance(exc, cl.CloverAuthError)
        self.assertIn("inventory permission", str(exc))
        self.assertIsInstance(self.run_status(404)[0], cl.CloverNotFound)
        exc, transport, _ = self.run_status(400)
        self.assertEqual((type(exc), exc.status, len(transport.seen)), (cl.CloverError, 400, 1))   # a 4xx is never retried
        self.assertIsInstance(self.run_status(403)[0], cl.CloverError)

    def test_429_honours_retry_after_then_succeeds(self):
        client, transport, clock = make({f"{BASE}/categories?limit=1000&offset=0": [(429, {"Retry-After": "2"}, {}), (200, {}, fixture("categories.json"))]})
        self.assertEqual(client.list_categories()[0]["name"], "Pantry")
        self.assertEqual((len(transport.seen), clock.sleeps), (2, [2]))

    def test_429_without_a_header_backs_off_1_2_4_then_gives_up(self):
        exc, transport, clock = self.run_status(429)
        self.assertIsInstance(exc, cl.RateLimited)
        self.assertEqual((exc.status, len(transport.seen), clock.sleeps), (429, 4, [1, 2, 4]))
        self.assertEqual(exc.retry_after, 8)

    def test_retry_after_is_clamped_and_junk_is_ignored(self):
        for header, wait in (("999", 30), ("0", 1), ("abc", 1), ("", 1), ("-5", 1), ("5", 5)):
            with self.subTest(header=header):
                _, _, clock = self.run_status(429, {"Retry-After": header}, max_retries=1)
                self.assertEqual(clock.sleeps, [wait])

    def test_retries_can_be_switched_off(self):
        exc, transport, clock = self.run_status(429, max_retries=0)
        self.assertEqual((len(transport.seen), clock.sleeps, type(exc)), (1, [], cl.RateLimited))

    def test_server_trouble_is_retried_then_reported_as_unavailable(self):
        for status in (500, 502, 503, 504):
            with self.subTest(status=status):
                exc, transport, _ = self.run_status(status)
                self.assertIsInstance(exc, cl.CloverUnavailable)
                self.assertEqual((exc.status, len(transport.seen)), (status, 4))
        client, transport, _ = make({f"{BASE}/categories?limit=1000&offset=0": [(503, {}, {}), (200, {}, fixture("categories.json"))]})
        self.assertEqual(len(client.list_categories()), 4)

    def test_507_is_retried_then_reported(self):
        # Protects: a read answered 507 follows the documented 5xx schedule (1, 2, 4), and a write is still sent once.
        # Catches: 507 missing from RETRY_STATUS, so one recoverable 507 aborts a read with CloverError and no retry.
        client, transport, clock = make({f"{BASE}/categories?limit=1000&offset=0": [(507, {}, {}), (200, {}, fixture("categories.json"))]})
        self.assertEqual(client.list_categories()[0]["name"], "Pantry")
        self.assertEqual((len(transport.seen), clock.sleeps), (2, [1]))
        exc, transport, clock = self.run_status(507)
        self.assertIsInstance(exc, cl.CloverUnavailable)
        self.assertEqual((exc.status, len(transport.seen), clock.sleeps), (507, 4, [1, 2, 4]))
        for method, path in (("POST", "/items"), ("PUT", "/item_stocks/ABC123")):
            with self.subTest(method=method):
                sent = []
                writer = cl.CloverWriteClient(MID, Token(FAKE_TOKEN), lambda r: sent.append(r) or cl.Response(507), min_interval=0, sleep=clock.sleep)
                with self.assertRaises(cl.CloverUnavailable):
                    writer.write(method, path, {})
                self.assertEqual(len(sent), 1)

    def test_a_dead_transport_is_reported_with_a_fixed_phrase(self):
        client, _, _ = make({})       # no recorded answer: the replay layer raises LookupError
        with self.assertRaises(cl.CloverUnavailable) as ctx:
            client.list_categories()
        self.assertEqual(str(ctx.exception), "clover could not be reached")
        self.assertIsNone(ctx.exception.__context__)

    def test_a_transport_returning_junk_is_reported_not_trusted(self):
        for junk in (None, "x", object(), cl.Response("200")):
            client = cl.CloverClient(MID, Token(FAKE_TOKEN), lambda r, j=junk: j, min_interval=0, sleep=lambda s: None)
            with self.subTest(junk=type(junk).__name__), self.assertRaises(cl.CloverUnavailable):
                client.list_categories()

    def test_bad_bodies(self):
        for body in (b"not json", b"[1, 2]", b'{"elements": "no"}', b'{"elements": [1]}', b"\xff\xfe", b"{}"):
            client, _, _ = make({f"{BASE}/categories?limit=1000&offset=0": (200, {}, body)})
            with self.subTest(body=body[:12]), self.assertRaises(cl.CloverError):
                client.list_categories()

    def test_an_oversized_body_is_refused(self):
        client, _, _ = make({f"{BASE}/categories?limit=1000&offset=0": (200, {}, b" " * (cl.BODY_LIMIT + 1))})
        with self.assertRaises(cl.CloverError):
            client.list_categories()

    def test_pacing_keeps_requests_apart(self):
        clock = FakeClock()
        client, _, _ = make({f"{BASE}/categories?limit=1000&offset=0": (200, {}, fixture("categories.json"))}, clock=clock, min_interval=0.25)
        for _ in range(3):
            client.list_categories()
        self.assertEqual(clock.sleeps, [0.25, 0.25])
        self.assertLessEqual(1 / 0.25, 16)       # four requests a second: under Clover's 16 per second per token


class LeakTests(NoNetwork):
    """The fake token never appears in a log, an error, a traceback, a repr or a pickle, even when the far side echoes it."""

    def collect(self, fn):
        records = []
        handler = logging.Handler()
        handler.emit = lambda r: records.append(r.getMessage())
        root = logging.getLogger()
        old = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            try:
                fn()
            except cl.CloverError as exc:
                return records, "\n".join([str(exc), repr(exc), "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))])
            return records, ""
        finally:
            root.removeHandler(handler)
            root.setLevel(old)

    def hostile(self, request):
        raise RuntimeError(f"connect failed, sent Authorization: Bearer {FAKE_TOKEN} to {request.url}")

    def test_token_is_in_the_request_but_in_nothing_that_prints(self):
        client, transport, _ = make({f"{BASE}/categories?limit=1000&offset=0": (200, {}, fixture("categories.json"))})
        records, _ = self.collect(client.list_categories)
        (req,) = transport.seen
        self.assertIn(FAKE_TOKEN, req.headers["Authorization"])       # the transport does need it
        shown = [repr(req), str(req), repr(req.headers), str(req.headers), repr(client), str(client), repr(client._token), *records]
        self.assertTrue(records, "the client logged nothing, so this test would pass vacuously")
        for text in shown:
            self.assertNotIn(FAKE_TOKEN, text)
        self.assertEqual(repr(req.headers), "SecretHeaders(Accept, Authorization, User-Agent)")
        with self.assertRaises(TypeError):
            pickle.dumps(client)

    def test_a_hostile_transport_message_is_dropped(self):
        client = cl.CloverClient(MID, Token(FAKE_TOKEN), self.hostile, min_interval=0)
        records, text = self.collect(client.list_categories)
        self.assertIn("could not be reached", text)
        for out in [text, *records]:
            self.assertNotIn(FAKE_TOKEN, out)
            self.assertNotIn("Bearer", out)

    def test_a_far_side_that_echoes_the_token_is_not_repeated(self):
        for status in (400, 401, 404, 429, 500):
            echo = {"message": f"bad token {FAKE_TOKEN}", "Authorization": f"Bearer {FAKE_TOKEN}"}
            client, _, _ = make({f"{BASE}/categories?limit=1000&offset=0": (status, {"X-Echo": FAKE_TOKEN}, echo)}, max_retries=0)
            records, text = self.collect(client.list_categories)
            with self.subTest(status=status):
                self.assertTrue(text)
                for out in [text, *records]:
                    self.assertNotIn(FAKE_TOKEN, out)
        client, _, _ = make({f"{BASE}/categories?limit=1000&offset=0": (200, {}, {"elements": [{"name": FAKE_TOKEN}]})})
        self.assertEqual(client.list_categories(), [{"name": FAKE_TOKEN}])   # a 200 body is data for the caller; the client never logs it
        records, _ = self.collect(client.list_categories)
        self.assertTrue(all(FAKE_TOKEN not in r for r in records))


class TransportTests(NoNetwork):
    def request(self, url, token=FAKE_TOKEN):
        return cl.Request("GET", url, cl.SecretHeaders({"Authorization": "Bearer " + token}))

    def test_only_the_two_clover_hosts_over_https(self):
        self.assertEqual(ALLOWED_NETLOCS, {"apisandbox.dev.clover.com", "api.clover.com"})
        transport = UrllibTransport()
        for url in ("http://api.clover.com/v3/merchants/X/items", "https://evil.example/v3/merchants/X/items", "https://api.clover.com.evil.example/x",
                    "https://api.clover.com@evil.example/x", "https://user:pw@api.clover.com/x", "https://api.eu.clover.com/x", "file:///etc/passwd",
                    "ftp://api.clover.com/x", "//api.clover.com/x", ""):
            with self.subTest(url=url), self.assertRaises(ValueError):
                transport(self.request(url))

    def test_a_redirect_is_never_followed(self):
        transport = UrllibTransport()
        self.assertTrue(any(isinstance(h, _NoRedirect) for h in transport._opener.handlers))
        self.assertIsNone(_NoRedirect().redirect_request(mock.Mock(), None, 302, "Found", {}, "https://evil.example/"))
        hdrs = email.message.Message()
        hdrs["Location"] = "https://evil.example/"
        err = urllib.error.HTTPError("https://api.clover.com/x", 302, "Found", hdrs, io.BytesIO(b"secret body"))
        with mock.patch.object(transport, "_opener") as opener:
            opener.open.side_effect = err
            got = transport(self.request("https://api.clover.com/v3/merchants/X/items"))
        self.assertEqual((got.status, got.headers["location"], got.body), (302, "https://evil.example/", b""))

    def test_a_good_answer_is_returned_with_lower_case_header_names(self):
        transport = UrllibTransport()
        reply = mock.MagicMock()
        reply.status, reply.headers, reply.read.return_value = 200, {"Retry-After": "3"}, b"{}"
        reply.__enter__.return_value = reply
        with mock.patch.object(transport, "_opener") as opener:
            opener.open.return_value = reply
            got = transport(self.request("https://apisandbox.dev.clover.com/v3/merchants/X/items"))
            sent = opener.open.call_args[0][0]
        self.assertEqual((got.status, got.headers, got.body), (200, {"retry-after": "3"}, b"{}"))
        self.assertEqual((sent.get_method(), opener.open.call_args[1]["timeout"]), ("GET", 15))

    def test_the_replay_layer_fails_loudly_on_an_unrecorded_request(self):
        with self.assertRaises(LookupError):
            ReplayTransport({})(self.request("https://api.clover.com/v3/merchants/X/items"))


class FixtureHygieneTests(unittest.TestCase):
    def test_fixtures_hold_no_token_shaped_or_real_looking_data(self):
        import re
        names = sorted(p.name for p in FIXTURES.iterdir())
        self.assertIn("items.json", names)
        for p in FIXTURES.iterdir():
            text = p.read_text(encoding="utf-8")
            with self.subTest(file=p.name):
                self.assertNotRegex(text, r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")   # Clover tokens are UUID-shaped
                self.assertNotRegex(text, r"(?i)bearer|authorization|access_token|api[_-]?key|secret|password")
                self.assertNotRegex(text, r"@[A-Za-z0-9.-]+\.[a-z]{2,}")                                                   # no e-mail address
                for ident in re.findall(r'"id": "([A-Za-z0-9]+)"', text):
                    self.assertTrue(ident.startswith("FAKE"), ident)


if __name__ == "__main__":
    unittest.main()
