"""NPP acceptance runner: every retake sentence is classified as a retake reply.

``hass.ops.photos.RETAKE`` maps each picture defect code (busy, dark, blurry, small, style) to the one plain sentence
Hass sends instead of a draft. The runner compared a reply to the whole mapping (``text == RETAKE``), which is never
true, so a correct retake reply ended in "?" and was counted as a question: case 28 ("an unsafe raw photo gets the
existing retake sentence") could not pass even when production sent exactly that sentence.
Contract: each RETAKE sentence is ``retake``; a question, a guard, a posted reply and an unrelated sentence keep their
kinds; a near-miss of a retake sentence is not a retake. Fixtures only: no model, network or private recording.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_npp = _load("npp_run_retake_reply_kind_under_test", ROOT / "hass" / "tests" / "npp" / "run_npp.py")
from hass.ops import photos  # noqa: E402

REPLIES = {"guards": {"render_failed": "I couldn't finish that card. Nothing was posted."},
           "questions": {"price": "What price should it be?"}}


class RetakeReplyKind(unittest.TestCase):
    def test_every_retake_sentence_is_a_retake(self):
        self.assertEqual(set(photos.RETAKE), {"busy", "dark", "blurry", "small", "style"})
        for code, sentence in photos.RETAKE.items():
            with self.subTest(code=code):
                self.assertTrue(sentence.endswith("?"))  # why the old comparison fell through to "question"
                self.assertEqual(run_npp.reply_kind(sentence, REPLIES), "retake")

    def test_other_kinds_unchanged(self):
        self.assertEqual(run_npp.reply_kind("What price should it be?", REPLIES), "question")
        self.assertEqual(run_npp.reply_kind("I can't tell what this is. What is it?", REPLIES), "question")
        self.assertEqual(run_npp.reply_kind(REPLIES["guards"]["render_failed"], REPLIES), "guard")
        self.assertEqual(run_npp.reply_kind("Posted: Wildflower Honey", REPLIES), "posted")
        self.assertEqual(run_npp.reply_kind("Thanks.", REPLIES), "other")

    def test_near_miss_is_not_a_retake(self):
        style = photos.RETAKE["style"]
        for text in (style.rstrip("?"), style + " ", style.lower(), style + " Thanks."):
            with self.subTest(text=text):
                self.assertNotEqual(run_npp.reply_kind(text, REPLIES), "retake")


if __name__ == "__main__":
    unittest.main()
