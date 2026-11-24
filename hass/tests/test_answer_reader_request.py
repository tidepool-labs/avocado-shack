"""RF1210-16: AnswerReader turns an unencodable request into a content-free {} + last_error "request" before any transport call.
Run: python3 -B -m unittest hass.tests.test_answer_reader_request"""
import json
import unittest
from datetime import date
from unittest import mock

from hass import answer_reader
from hass.answer_reader import AnswerReader

TODAY = date(2026, 11, 16)
LONE = (chr(0xD800), chr(0xDC00))


class Transport:
    def __init__(self, api, content='{"value": "9.57"}', status=200, raw=None):
        self.api, self.content, self.status, self.raw, self.sent = api, content, status, raw, []

    def __call__(self, url, body, headers, timeout):
        self.sent.append(body)
        if self.raw is not None:
            return self.status, self.raw
        if self.api == "ollama":
            reply = {"done": True, "message": {"content": self.content}}
        else:
            reply = {"choices": [{"finish_reason": "stop", "message": {"content": self.content}}]}
        return self.status, json.dumps(reply).encode()


def make(api, **kw):
    transport = Transport(api, **kw)
    return AnswerReader("http://127.0.0.1:9", "m", transport=transport, api=api), transport


class AnswerReaderRequestTests(unittest.TestCase):
    def test_surrogate_request_is_content_free_failure(self):
        for api in ("ollama", "openai"):
            for bad in LONE:
                reader, transport = make(api)
                self.assertEqual(reader.read("price", "nine " + bad, TODAY), {})
                self.assertEqual(reader.last_error, "request")
                self.assertEqual((transport.sent, reader.calls), ([], 0))
                self.assertGreaterEqual(reader.last_seconds, 0)

    def test_valid_unicode_control_and_recovery(self):
        for api in ("ollama", "openai"):
            reader, transport = make(api)
            self.assertEqual(reader.read("price", "café 🥑 nine fifty-seven", TODAY), {"value": "9.57"})
            self.assertIsNone(reader.last_error)
            sent = json.loads(transport.sent[0])
            user = json.loads(sent["messages"][1]["content"])
            self.assertEqual((user["answer"], user["question"], user["today"]), ("café 🥑 nine fifty-seven", "price", "2026-11-16"))
            self.assertIn("🥑".encode(), transport.sent[0])
            self.assertEqual(reader.read("price", "x" + LONE[0], TODAY), {})
            self.assertEqual((reader.last_error, reader.calls), ("request", 1))
            self.assertEqual(reader.read("price", "nine", TODAY), {"value": "9.57"})
            self.assertEqual((reader.last_error, reader.calls, len(transport.sent)), (None, 2, 2))

    def test_builder_serialization_failures_use_request_code(self):
        for api in ("ollama", "openai"):
            for exc in (TypeError, ValueError, UnicodeEncodeError, RecursionError):
                reader, transport = make(api)
                canary = "CANARY-SECRET"
                err = UnicodeEncodeError("utf-8", canary, 0, 1, canary) if exc is UnicodeEncodeError else exc(canary)
                with mock.patch.object(answer_reader.json, "dumps", side_effect=err), \
                        mock.patch("hass.interpreter_local.json.dumps", side_effect=err):
                    self.assertEqual(reader.read("price", "nine", TODAY), {})
                self.assertEqual((reader.last_error, transport.sent, reader.calls), ("request", [], 0))
            reader, _ = make(api)
            with mock.patch.object(answer_reader.json, "dumps", side_effect=RuntimeError("boom")), \
                    mock.patch("hass.interpreter_local.json.dumps", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    reader.read("price", "nine", TODAY)

    def test_existing_shape_and_response_failures_preserved(self):
        reader, transport = make("ollama")
        for key, words in (("nope", "a"), ("price", "  "), ("price", "x" * 401), ("price", 5)):
            self.assertEqual(reader.read(key, words, TODAY), {})
            self.assertEqual(reader.last_error, "shape")
        self.assertEqual((transport.sent, reader.calls), ([], 0))
        reader, transport = make("ollama", status=500, raw=b"x")
        self.assertEqual(reader.read("price", "nine", TODAY), {})
        self.assertEqual((reader.last_error, len(transport.sent), reader.calls), ("http-500", 1, 1))
        reader, transport = make("openai", raw=b'{"nope": 1}')
        reader.read("price", "nine", TODAY)
        self.assertEqual((reader.last_error, len(transport.sent)), ("shape", 1))

    def test_missing_value_key_uses_fallback(self):
        # Contract: a reply object WITHOUT "value" is a shape failure that tries the configured fallback once; {"value": null}
        # is a valid abstention (no fallback). Bug: treating {} as an answer drops a reply the fallback could read.
        for api in ("ollama", "openai"):
            for content, want_error, want_calls, want in (('{"other": 1}', "shape", 1, {"value": "9.57"}), ("{}", "shape", 1, {"value": "9.57"}),
                                                          ('{"value": null}', None, 0, {"value": None}), ('{"value": "4.31"}', None, 0, {"value": "4.31"})):
                fb_reader, fb_transport = make(api)
                primary_transport = Transport(api, content=content)
                reader = AnswerReader("http://127.0.0.1:9", "m", transport=primary_transport, api=api, fallback=fb_reader)
                self.assertEqual(reader.read("price", "nine", TODAY), want, (api, content))
                self.assertEqual((len(primary_transport.sent), len(fb_transport.sent), fb_reader.calls), (1, want_calls, want_calls), (api, content))
                self.assertIsNone(reader.last_error)
                self.assertEqual((reader.last_primary_error, reader.last_fallback), (want_error, bool(want_calls)), (api, content))
        reader, transport = make(api, content="{}")  # no fallback configured: still a recorded shape failure, no crash
        self.assertEqual((reader.read("price", "nine", TODAY), reader.last_error, len(transport.sent)), ({}, "shape", 1))

    def test_both_api_request_bytes_unchanged(self):
        reader, t = make("ollama", )
        reader.think = False
        reader.read("price", "nine", TODAY)
        body = json.loads(t.sent[0])
        self.assertEqual(set(body), {"model", "messages", "stream", "format", "options", "think"})
        self.assertEqual((body["format"], body["think"], body["messages"][0]["content"]), ("json", False, answer_reader.PROMPT))
        reader, t = make("openai")
        reader.read("price", "nine", TODAY)
        body = json.loads(t.sent[0])
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertNotIn("think", body)
        self.assertEqual(set(json.loads(body["messages"][1]["content"])), {"question", "form", "today", "answer"})


if __name__ == "__main__":
    unittest.main()
