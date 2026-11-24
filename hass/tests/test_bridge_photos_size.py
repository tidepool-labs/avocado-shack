"""RF0450-12 (H08/H10) tests: BlueBubblesPhotos.fetch refuses a download whose length differs from the attachment's
declared int totalBytes as `size-mismatch` (a cut-off photo is never returned), and refuses a message guid holding a
C0/C1 control character with ValueError before any call. Fake transports only: nothing listens, connects or downloads.
Run: python3 -m unittest hass.tests.test_bridge_photos_size -v"""

import http.client
import io
import unittest
from unittest import mock
from urllib.parse import urlsplit

from hass import bridge_photos
from hass.bridge import BridgeError
from hass.bridge_photos import BlueBubblesPhotos
from hass.tests import test_bridge_photos as _bp
from hass.tests.test_bridge_photos import JPG, PASSWORD, FakeTransport, _meta


class SizeMismatchTests(unittest.TestCase):
    setUp, photos, fails = _bp.PhotosTests.setUp, _bp.PhotosTests.photos, _bp.PhotosTests.fails  # helpers only, not its tests

    def mismatch(self, items, files, n=1):
        exc = self.fails(fake := FakeTransport(meta=_meta(*items), files=files), "size-mismatch", n=n)
        self.assertIsNone(exc.status)
        return fake

    def test_short_download_is_size_mismatch_without_password(self):
        fake = self.mismatch([{"guid": "att-1", "totalBytes": len(JPG)}], {"att-1": (200, JPG[:-10])})
        self.assertEqual(len(fake.calls), 2)
        with self.assertRaises(BridgeError) as ctx: self.photos(fake).fetch("msg-1", 1)
        for text in (str(ctx.exception), repr(ctx.exception)):
            self.assertNotIn(PASSWORD, text)
            self.assertNotIn("password=", text)

    def test_one_byte_short_or_long_is_size_mismatch(self):
        for body in (JPG[:-1], JPG + b"\x00"):
            with self.subTest(size=len(body)):
                self.mismatch([{"guid": "att-1", "totalBytes": len(JPG)}], {"att-1": (200, body)})

    def test_second_of_two_short_returns_nothing(self):
        items = [{"guid": "att-1", "totalBytes": len(JPG)}, {"guid": "att-2", "totalBytes": len(JPG)}]
        fake = self.mismatch(items, {"att-1": (200, JPG), "att-2": (200, JPG[:100])}, n=2)
        self.assertEqual(len(fake.calls), 3)

    def test_first_of_two_short_stops_before_second_download(self):
        items = [{"guid": "att-1", "totalBytes": len(JPG)}, {"guid": "att-2", "totalBytes": len(JPG)}]
        fake = self.mismatch(items, {"att-1": (200, JPG[:100]), "att-2": (200, JPG)}, n=2)
        self.assertEqual(len(fake.calls), 2)

    def test_matching_lengths_still_download(self):
        items = [{"guid": "att-1", "totalBytes": len(JPG)}, {"guid": "att-2", "totalBytes": len(JPG) + 1}]
        fake = FakeTransport(meta=_meta(*items), files={"att-1": (200, JPG), "att-2": (200, JPG + b"2")})
        self.assertEqual(self.photos(fake).fetch("msg-1", 2), [JPG, JPG + b"2"])

    def test_absent_or_none_total_bytes_accepts_any_length(self):
        for item in ({"guid": "att-1"}, {"guid": "att-1", "totalBytes": None}):
            for body in (JPG[:-10], JPG + b"x", b"x"):
                with self.subTest(item=item, size=len(body)):
                    fake = FakeTransport(meta=_meta(item), files={"att-1": (200, body)})
                    self.assertEqual(self.photos(fake).fetch("msg-1", 1), [body])

    def test_declared_zero_with_empty_body_is_empty(self):
        self.fails(FakeTransport(meta=_meta({"guid": "att-1", "totalBytes": 0}), files={"att-1": (200, b"")}), "empty")

    def test_declared_zero_with_a_body_is_size_mismatch(self):
        self.mismatch([{"guid": "att-1", "totalBytes": 0}], {"att-1": (200, JPG)})

    def test_http_error_keeps_its_code_and_status(self):
        fake = FakeTransport(meta=_meta({"guid": "att-1", "totalBytes": len(JPG)}), files={"att-1": (500, b"")})
        self.assertEqual(self.fails(fake, "http-error").status, 500)


def _http(body, announced=None, chunked=False):
    """A real http.client response parsed from raw bytes (no socket): `announced` is the Content-Length header, if any."""
    head = b"HTTP/1.1 200 OK\r\n" + (b"Transfer-Encoding: chunked\r\n" if chunked else b"")
    head += b"Content-Length: %d\r\n" % announced if announced is not None else b""
    raw = head + b"\r\n" + (b"%x\r\n%s\r\n0\r\n\r\n" % (len(body), body) if chunked else body)
    sock = mock.Mock(makefile=lambda *a, **k: io.BytesIO(raw))
    response = http.client.HTTPResponse(sock)
    response.begin()
    return response


class ShortBodyTests(unittest.TestCase):
    """Contract: the default transport never returns a body that ended before its announced HTTP Content-Length, even
    when the metadata omits totalBytes. Bug it catches: a bounded read() returns the cut-off bytes as the whole photo,
    so a short read is treated as complete, validation sees a truncated original and the caller's retry never runs."""
    setUp, photos = _bp.PhotosTests.setUp, _bp.PhotosTests.photos

    def fetch(self, body, announced=None, chunked=False, meta=None):
        meta = meta or {"guid": "att-1"}  # no totalBytes unless the test asks
        document = _meta(meta)[1]
        answers = {"message": _http(document, len(document)), "attachment": _http(body, announced, chunked)}
        opener = lambda request, timeout=None: answers[urlsplit(request.full_url).path.split("/")[3]]  # noqa: E731
        with mock.patch.object(bridge_photos._OPENER, "open", side_effect=opener):
            return BlueBubblesPhotos(_bp.BASE, self.pw).fetch("msg-1", 1)

    def test_short_body_without_total_bytes_is_refused(self):
        with self.assertRaises(BridgeError) as ctx: self.fetch(b"1234", announced=8)  # announced 8, received 4
        self.assertEqual((ctx.exception.code, ctx.exception.status), ("size-mismatch", None))
        self.assertEqual((ctx.exception.__cause__, ctx.exception.__context__), (None, None))
        self.assertEqual(self.fetch(b"12345678", announced=8), [b"12345678"])  # healthy control: 8 of 8

    def test_body_without_content_length_is_unchanged(self):
        self.assertEqual(self.fetch(b"1234"), [b"1234"])  # close-delimited, nothing announced
        self.assertEqual(self.fetch(b"1234", chunked=True), [b"1234"])
        self.assertEqual(self.fetch(b"1234", announced=99, chunked=True), [b"1234"])  # chunked wins over a stray header

    def test_size_cap_is_still_too_large_not_size_mismatch(self):
        with mock.patch.object(bridge_photos.media, "MAX_BYTES", 16):
            with self.assertRaises(BridgeError) as ctx: self.fetch(b"x" * 17, announced=100)  # read stops at limit + 1
        self.assertEqual(ctx.exception.code, "too-large")

    def test_short_body_with_matching_total_bytes_is_still_size_mismatch(self):
        with self.assertRaises(BridgeError) as ctx: self.fetch(b"1234", announced=8, meta={"guid": "att-1", "totalBytes": 8})
        self.assertEqual(ctx.exception.code, "size-mismatch")


class MessageGuidControlTests(unittest.TestCase):
    setUp, photos = _bp.PhotosTests.setUp, _bp.PhotosTests.photos

    def test_control_characters_refused_before_any_call(self):
        fake = FakeTransport()
        for guid in ("m\n1", "m\x00", "m\x7f", "m\x85", "m\x1f", "m\x9f", "\tm"):
            with self.subTest(guid=repr(guid)):
                with self.assertRaises(ValueError) as ctx: self.photos(fake).fetch(guid, 1)
                self.assertIn("without control characters", str(ctx.exception))
        self.assertEqual(fake.calls, [])

    def test_plain_and_printable_non_ascii_guids_still_work(self):
        for guid in ("m-1", "m\xa0é"):
            with self.subTest(guid=repr(guid)):
                fake = FakeTransport()
                self.assertEqual(self.photos(fake).fetch(guid, 1), [JPG])
                self.assertEqual(len(fake.calls), 2)


if __name__ == "__main__":
    unittest.main()
