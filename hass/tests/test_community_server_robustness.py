"""AV1124C-04: one unreadable hike record must not stop the local community API; look-alike email
characters are refused. Each test names the bug that fails it: .replace() on a non-text start,
e['id'] on an id-less event (both closed the connection), and a zero-width space or 'a@b..co' accepted. Synthetic fixtures only."""
import datetime
import http.client
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from unittest import mock
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EMAIL_ERROR = "Please enter a valid email address."


def _load():
    # The module reads these two variables at import, so point both at a scratch folder first.
    with tempfile.TemporaryDirectory(prefix="av1124c-04-") as tmp:
        env = {"AVOSHACK_COMMUNITY_CONFIG": str(Path(tmp) / "community.json"),
               "AVOSHACK_COMMUNITY_DB": str(Path(tmp) / "community.sqlite3")}
        with mock.patch.dict(os.environ, env):
            spec = importlib.util.spec_from_file_location("community_server_av1124c_04", REPO / "storefront-mockup/community-server.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module


server = _load()


def _future(days=7):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)).isoformat()


def _good(**extra):
    return {"id": "good-hike", "title": "Good", "status": "scheduled", "startsAt": _future(),
            "meetingPoint": "Lot", "rsvpEnabled": True, "capacity": 10, **extra}


class ScheduledTests(unittest.TestCase):
    def test_scheduled_never_raises_on_unreadable_start(self):
        for bad in (None, 5, 1.5, True, ["2030-01-01T00:00:00Z"], {}, "", "   ", "not a date", "2099-01-01T10:00:00"):
            with self.subTest(startsAt=repr(bad)):
                self.assertIs(server.scheduled({"startsAt": bad, "status": "scheduled"}), False)
        for event in ({"status": "scheduled"}, None, [], "text"):
            with self.subTest(event=repr(event)):
                self.assertIs(server.scheduled(event), False)

    def test_scheduled_healthy_control(self):
        self.assertIs(server.scheduled({"startsAt": _future(), "status": "scheduled"}), True)
        self.assertIs(server.scheduled({"startsAt": "2099-01-01T10:00:00Z", "status": "scheduled"}), True)
        self.assertIs(server.scheduled({"startsAt": _future(), "status": "completed"}), False)
        self.assertIs(server.scheduled({"startsAt": "2000-01-01T10:00:00Z", "status": "scheduled"}), False)


class ListingTests(unittest.TestCase):
    def setUp(self):
        self.good = _good()
        tmp = tempfile.TemporaryDirectory(prefix="av1124c-04-")
        self.addCleanup(tmp.cleanup)
        cfg = Path(tmp.name) / "community.json"
        cfg.write_text(json.dumps({"clubName": "Test Club", "routeIdeas": [], "events": [
            {"id": "null-start", "status": "scheduled", "startsAt": None, "meetingPoint": "Lot"},
            {"title": "No id", "status": "scheduled", "startsAt": _future(), "meetingPoint": "Lot"},
            {"id": 7, "title": "Number id", "status": "scheduled", "startsAt": _future()},
            "not an object", None, 5,
            self.good,
        ]}), "utf-8")
        saved = (server.DB, server.CONFIG)
        server.DB, server.CONFIG = Path(tmp.name) / "community.sqlite3", cfg
        self.addCleanup(lambda: (setattr(server, "DB", saved[0]), setattr(server, "CONFIG", saved[1])))
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port = httpd.server_port
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)

    def get(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("GET", "/api/community")
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_listing_skips_unreadable_event_and_answers(self):
        # A null start is kept but closed to RSVPs (it has a text id); only the good event is open.
        expected_good = {**self.good, "confirmedGuests": 0, "remaining": 10, "rsvpOpen": True}
        for attempt in range(2):  # the second request proves the server kept answering
            with self.subTest(attempt=attempt):
                status, body = self.get()
                self.assertEqual(status, 200)
                ids = [e["id"] for e in body["events"]]
                self.assertEqual(ids, ["null-start", "good-hike"])
                self.assertEqual(body["events"][1], expected_good)
                self.assertIs(body["events"][0]["rsvpOpen"], False)


class EmailTests(unittest.TestCase):
    def test_email_refuses_invisible_and_empty_label(self):
        for raw in ("a\u200b@b.co", "a@b\u202e.co", "a@b..co", " a@.b.c ", "a@b.c.", "a@b\ue000.co", "a@b\ud800.co", "a\ufeff@b.co", "a@b.co\u200d"):
            with self.subTest(raw=ascii(raw)):
                with self.assertRaises(server.FormError) as caught:
                    server.email_address(raw)
                self.assertEqual(str(caught.exception), EMAIL_ERROR)

    def test_email_healthy_control(self):
        self.assertEqual(server.email_address("a@b.co"), "a@b.co")
        self.assertEqual(server.email_address("A@B.CO"), "a@b.co")
        self.assertEqual(server.email_address(" a..b@x.example.co "), "a..b@x.example.co")
        at_limit = "a" * (254 - len("@example.invalid")) + "@example.invalid"
        self.assertEqual(len(at_limit), 254)
        self.assertEqual(server.email_address(at_limit), at_limit)
        with self.assertRaises(server.FormError):
            server.email_address("b" + at_limit)


if __name__ == "__main__":
    unittest.main()
