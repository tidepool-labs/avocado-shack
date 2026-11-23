"""HRM-20: docs/hass/NPP-WEEKLY.md, the weekly NPP review runbook, stays runnable and plain (stdlib, offline).

C1 runs each documented `python3 -B <path>.py` command with `--help` only; nothing reads Hass state or the network.
"""
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "hass" / "NPP-WEEKLY.md"
SKILL = "docs/hass/skills/hass-npp-review/SKILL.md"
COMMAND_RE = re.compile(r"python3 -B ((?:scripts/)?hass/[\w/]+\.py)\b")
TOOLS = {"hass/transcript.py", "scripts/hass/npp_review_export.py", "scripts/hass/npp_findings.py",
         "scripts/hass/npp_case_new.py"}
# C2 allows digits only in the interpreter name, command flags and <placeholders>, plus the design-section
# reference that C3 requires.
ALLOWED_RE = re.compile(r"<[^<>\n]*>|--[A-Za-z][\w-]*|\bpython3\b|\bsection 4c\b")
HOME_RE = re.compile(r"/home/|/Users/|/root\b|~/|\$HOME|%USERPROFILE%", re.I)


def doc() -> str:
    return DOC.read_text(encoding="utf-8")


def stray_digits(text: str) -> list:
    """(line number, line) for each line that still has a digit after the allowed spans are removed."""
    return [(n, line) for n, line in enumerate(text.splitlines(), 1) if re.search(r"\d", ALLOWED_RE.sub("", line))]


class NppWeeklyDocTest(unittest.TestCase):
    def test_c1_commands_exist(self):
        scripts = set(COMMAND_RE.findall(doc()))
        self.assertTrue(TOOLS <= scripts, f"runbook is missing commands for {sorted(TOOLS - scripts)}")
        for script in sorted(scripts):
            with self.subTest(script=script):
                self.assertTrue((ROOT / script).is_file(), f"{script} does not exist")
                run = subprocess.run([sys.executable, "-B", script, "--help"], cwd=ROOT, capture_output=True,
                                     text=True, timeout=60)
                self.assertEqual(run.returncode, 0, f"{script} --help exited {run.returncode}: {run.stderr[-300:]}")
                self.assertIn("usage:", run.stdout)

    def test_c2_plain(self):
        text = doc()
        self.assertEqual([m.group(0) for m in HOME_RE.finditer(text)], [], "absolute home path in the runbook")
        self.assertEqual(stray_digits(text), [], "digit outside a command flag or placeholder")

    def test_c3_refs(self):
        text = doc()
        self.assertRegex(text, r"\bdesign section 4c\b")
        self.assertIn(f"`{SKILL}`", text)
        self.assertTrue((ROOT / SKILL).is_file(), f"{SKILL} does not exist")


if __name__ == "__main__":
    unittest.main()
