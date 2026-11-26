"""Case 14 (candle with food words): the acceptance runner observes `description_lacks` instead of reporting a gap."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_npp = _load("npp_run_description_lacks", ROOT / "hass" / "tests" / "npp" / "run_npp.py")
TERMS = json.loads((ROOT / "hass" / "tests" / "npp" / "cases" / "case-14-candle-food-words.json").read_text())[
    "expect"]["description_lacks"]


class DescriptionLacksTest(unittest.TestCase):
    def test_practical_candle_wording_passes(self):
        texts = {"shown": "Lavender Honey Candle for a calm room. Light it in the evening and let it burn evenly.",
                 "v1": "Lavender Honey Candle for a calm room. Light it in the evening and let it burn evenly."}
        self.assertEqual(run_npp.description_lacks_findings(texts, TERMS), [])

    def test_food_word_in_any_delivered_version_fails(self):
        texts = {"shown": "Lavender Honey Candle for a calm room.", "v1": "Taste it plain, then decide."}
        self.assertEqual(run_npp.description_lacks_findings(texts, TERMS),
                         ["description_lacks: v1 description holds 'taste'"])

    def test_word_start_match_not_substring(self):
        # 'eat' must find 'eating' but not 'great' or 'heat'; 'serve' finds 'Serve' in any case.
        self.assertEqual(run_npp.description_lacks_findings({"shown": "A great candle that holds its heat."}, TERMS), [])
        self.assertEqual(run_npp.description_lacks_findings({"shown": "Good for eating."}, TERMS),
                         ["description_lacks: shown description holds 'eat'"])
        self.assertEqual(run_npp.description_lacks_findings({"shown": "Serve warm."}, TERMS),
                         ["description_lacks: shown description holds 'serve'"])

    def test_missing_description_is_a_finding_never_a_pass(self):
        for value in (None, "", "   ", 3):
            with self.subTest(value=value):
                self.assertEqual(run_npp.description_lacks_findings({"shown": value}, TERMS),
                                 ["description_lacks: shown description is missing"])

    def test_the_observer_marks_description_lacks_covered(self):
        # Without coverage the strict runner reports case 14 as not-run ("unobserved expectations: description_lacks").
        source = (ROOT / "hass" / "tests" / "npp" / "run_npp.py").read_text()
        self.assertIn("newly_covered.add('description_lacks')", source)
        self.assertIn("description_lacks_findings(texts, want['description_lacks'])", source)


if __name__ == "__main__":
    unittest.main()
