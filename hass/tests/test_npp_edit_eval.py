"""Offline behavioral contracts for the S10 edit mapper eval."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from hass import cloud_codex, cloud_codex_hermes
from hass.npp import assets, edits
from scripts.hass import npp_edit_eval as eval_cli


def mapping(*pairs):
    return {"action": "patch", "patches": [{"field": key, "value": value} for key, value in pairs], "ask_id": None}


ASK = {"action": "ask", "patches": [], "ask_id": "ask_edit_unclear"}


class EditEvalTests(unittest.TestCase):
    def setUp(self):
        self.phrases = json.loads(eval_cli.PHRASES.read_bytes())
        self.real_transport = self.enterContext(patch.object(edits, "CodexTransport", side_effect=AssertionError("offline only")))
        self.addCleanup(self.real_transport.assert_not_called)

    def run_eval(self, args, **kwargs):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = eval_cli.main(args, **kwargs)
        return rc, stdout.getvalue().splitlines()

    def test_c1_phrase_file_valid(self):
        # Reject drift into canned grammar or finance-routed phrases, not just malformed gold JSON.
        _, files, _ = assets()
        grammar = edits.Grammar(files)
        self.assertGreaterEqual(len(self.phrases), 30)
        self.assertEqual(len({p["id"] for p in self.phrases}), len(self.phrases))
        self.assertEqual(len({p["phrase"] for p in self.phrases}), len(self.phrases))
        self.assertIn("ask", [p["expected"] for p in self.phrases])
        self.assertTrue(any(isinstance(p["expected"], list) and len(p["expected"]) > 1 for p in self.phrases))
        for row in self.phrases:
            with self.subTest(id=row["id"]):
                self.assertTrue(row["id"].strip())
                self.assertTrue(row["phrase"].strip())
                self.assertNotRegex(row["phrase"], edits.DIGIT)
                self.assertFalse(cloud_codex.till_like(row["phrase"]))
                expected = row["expected"]
                if expected == "ask":
                    doc = ASK
                else:
                    self.assertIsInstance(expected, list)
                    self.assertTrue(expected)
                    self.assertEqual(len({p["field"] for p in expected}), len(expected))
                    doc = {"action": "patch", "patches": expected, "ask_id": None}
                self.assertIsNotNone(edits.valid_mapping(doc, grammar.schema))
                fake_mapper = Mock(return_value=doc)
                edit = edits.read(grammar, row["phrase"], {}, fake_mapper)
                fake_mapper.assert_called_once()
                if expected != "ask":
                    self.assertIsNone(edit.ask)

    def test_c2_replay_scores(self):
        # Detect missing rows in the denominator, order-sensitive patch matching, and threshold off-by-ones.
        answers = [
            ("multi-shelf-name", mapping(("name", "Cultured Butter"), ("category", "dairy")), "exact"),
            ("ask-vague", ASK, "exact"),
            ("multi-source-shelf", mapping(("category", "eggs"), ("supplier", "Other Farm")), "partial"),
            ("name-honey", mapping(("name", "Different Honey")), "wrong"),
            ("supplier-market", ASK, "wrong"),
            ("ask-shelf-choice", mapping(("category", "drinks")), "wrong"),
            ("name-beans", mapping(("cost", "PRIVATE-SENTINEL")), "invalid"),
            ("name-granola", None, "invalid"),
        ]
        data = [{"id": key, "output": output, "model": "fake-hidden-id"} for key, output, _ in answers]
        factory = Mock(side_effect=AssertionError("replay must not construct a transport"))
        with TemporaryDirectory() as tmp:
            tape = Path(tmp) / "replay.json"
            tape.write_text(json.dumps(data), encoding="utf-8")
            for minimum, expected_rc, trailer in (("0", 0, "PASS"), ("0.25", 0, "PASS"), ("0.251", 1, "FAIL")):
                with self.subTest(minimum=minimum):
                    rc, lines = self.run_eval(["--replay", str(tape), "--min", minimum], transport_factory=factory)
                    self.assertEqual(rc, expected_rc)
                    self.assertEqual(lines[:-2], [f"{key}: {score}" for key, _, score in answers])
                    self.assertEqual(lines[-2], "accuracy: 2/8 (25.00%); exact=2 partial=1 wrong=3 invalid=2")
                    self.assertEqual(lines[-1], f"{trailer} npp_edit_eval")
            factory.assert_not_called()

    def test_c3_record_guarded(self):
        # Refusal must happen before backend construction or output creation, not just after a model failure.
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "private.json"
            sink = ["--out", str(out)]
            yes, cap = ["--yes-record"], ["--max-calls", "1"]
            cases = [
                (sink, "requires --yes-record and --max-calls"),
                (yes + sink, "requires --yes-record and --max-calls"),
                (cap + sink, "requires --yes-record and --max-calls"),
                (yes + cap, "requires --out"),
                (["--yes-recor"] + cap + sink, "unrecognized arguments"),
            ]
            cases += [(yes + ["--max-calls", n] + sink, "between 1 and 60") for n in ("-1", "0", "61", "1000")]
            cases += [(yes + ["--max-calls", n] + sink, "invalid int value") for n in ("1.5", "many")]
            cases += [(yes + sink + ["--max-calls"], "expected one argument")]
            for flags, diagnostic in cases:
                with self.subTest(flags=flags):
                    factory = Mock(side_effect=AssertionError("refusal must not construct a transport"))
                    stderr = io.StringIO()
                    with self.assertRaises(SystemExit) as ctx, redirect_stderr(stderr):
                        eval_cli.main(["--record", *flags], transport_factory=factory)
                    self.assertEqual(ctx.exception.code, 2)
                    self.assertIn(diagnostic, stderr.getvalue())
                    factory.assert_not_called()
                    self.assertFalse(out.exists())

            # A symlink into a worktree, including linked worktrees (.git file), is not a private destination.
            worktree = Path(tmp) / "worktree"
            worktree.mkdir()
            (worktree / ".git").write_text("gitdir: fixture\n", encoding="utf-8")
            alias = Path(tmp) / "alias"
            alias.symlink_to(worktree, target_is_directory=True)
            factory = Mock(side_effect=AssertionError("refusal must not construct a transport"))
            stderr = io.StringIO()
            with self.assertRaises(SystemExit) as ctx, redirect_stderr(stderr):
                eval_cli.main(["--record", *yes, *cap, "--out", str(alias / out.name)], transport_factory=factory)
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("outside Git worktrees", stderr.getvalue())
            factory.assert_not_called()
            self.assertFalse((worktree / out.name).exists())

            # Both inclusive boundaries work, stop at the cap or corpus end, and never retry a failed call.
            for limit in (1, 60):
                with self.subTest(limit=limit):
                    fake_transport = Mock(return_value=(503, b"{}"))
                    factory = Mock(return_value=fake_transport)
                    output = Path(tmp) / f"cap-{limit}.json"
                    rc, lines = self.run_eval(["--record", *yes, "--max-calls", str(limit), "--out", str(output)],
                                              transport_factory=factory)
                    self.assertEqual((rc, lines[-1]), (0, "PASS npp_edit_eval"))
                    factory.assert_called_once()
                    self.assertEqual(fake_transport.call_count, min(limit, len(self.phrases)))

    def test_c4_record_shape(self):
        # Persist only the mapper payload and returned model, not the prompt, requested model or transport metadata.
        answer = mapping(("name", "Wildflower Honey"))
        first = {"model": "synthetic-returned-id", "request_id": "not-for-the-tape",
                 "choices": [{"message": {"content": json.dumps(answer)}}]}
        second = {"choices": [{"message": {"content": json.dumps(ASK)}}]}
        fake_transport = Mock(side_effect=[(200, json.dumps(first).encode()), (200, json.dumps(second).encode())])
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "private.json"
            rc, lines = self.run_eval(["--record", "--yes-record", "--max-calls", "2", "--out", str(output)],
                                      transport_factory=lambda step: fake_transport)
            self.assertEqual((rc, lines[-1]), (0, "PASS npp_edit_eval"))
            self.assertEqual(json.loads(output.read_bytes()), [
                {"id": self.phrases[0]["id"], "output": answer, "model": "synthetic-returned-id"},
                {"id": self.phrases[1]["id"], "output": ASK, "model": None},
            ])
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            rc, replay_lines = self.run_eval(["--replay", str(output)])
            self.assertEqual((rc, replay_lines), (0, lines))
        for phrase, call in zip(self.phrases[:2], fake_transport.call_args_list, strict=True):
            request = json.loads(call.args[1])
            self.assertIn(phrase["phrase"], request["messages"][1]["content"])
            self.assertNotEqual(request["model"], first["model"])

    def test_c4_attended_record_does_not_label_request_as_response(self):
        # Run the real CLI, adapter and Hermes response parser. The legacy
        # runner echoes the requested pin and drops the actual service ID.
        answer = mapping(("name", "Wildflower Honey"))
        events = [
            {"type": "response.output_text.delta", "delta": json.dumps(answer)},
            {"type": "response.completed", "response": {"model": "synthetic-service-id"}},
        ]
        post = Mock(return_value=(200, ["data: " + json.dumps(event) for event in events]))

        def fixture_runner(request):
            return cloud_codex_hermes.run(json.dumps(request), lambda: ("fixture", "https://example.invalid"), post)

        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "private.json"
            script = eval_cli.__file__
            argv = [script, "--record", "--yes-record", "--max-calls", "1", "--out", str(output)]
            with patch.object(edits, "CodexTransport", cloud_codex.CodexTransport), \
                 patch.object(cloud_codex, "Runner", return_value=fixture_runner), \
                 patch.object(sys, "argv", argv), patch.object(sys, "path", sys.path.copy()), \
                 redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as ctx:
                runpy.run_path(script, run_name="__main__")
            self.assertEqual(ctx.exception.code, 0)
            post.assert_called_once()
            self.assertEqual(json.loads(output.read_bytes()), [
                {"id": self.phrases[0]["id"], "output": answer, "model": None},
            ])


if __name__ == "__main__":
    unittest.main()
