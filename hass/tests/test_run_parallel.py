"""Regression coverage for the CI runner's unittest discovery contract."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hass.tests import run_parallel


class ParallelDiscoveryTests(unittest.TestCase):
    def test_discovery_matches_unittest(self):
        for relative in ("testother.py", "nested/test_nested.py"):
            with self.subTest(path=relative), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tests = root / "hass" / "tests"
                tests.mkdir(parents=True)
                for package in (root / "hass", tests, tests / "nested"):
                    package.mkdir(exist_ok=True)
                    (package / "__init__.py").touch()
                source = (
                    "import unittest\n"
                    "class Sample(unittest.TestCase):\n"
                    "    def test_included(self):\n"
                    "        self.fail('discovery sentinel')\n"
                )
                (tests / relative).write_text(source)
                # Keep a conventional module so the old runner can falsely pass.
                (tests / "test_sample.py").write_text(
                    "import unittest\nclass Control(unittest.TestCase):\n"
                    "    def test_control(self): pass\n"
                )
                shutil.copyfile(run_parallel.__file__, tests / "run_parallel.py")
                serial = subprocess.run(
                    [sys.executable, "-m", "unittest", "discover", "-s", "hass/tests", "-t", ".", "-v"],
                    cwd=root, capture_output=True, text=True,
                )
                parallel = subprocess.run(
                    [sys.executable, "hass/tests/run_parallel.py", "--jobs", "2"],
                    cwd=root, capture_output=True, text=True,
                )
                self.assertEqual(serial.returncode, 1, serial.stdout + serial.stderr)
                self.assertEqual(parallel.returncode, 1, parallel.stdout + parallel.stderr)
                self.assertIn("discovery sentinel", parallel.stdout + parallel.stderr)
                self.assertIn("test_control", parallel.stdout + parallel.stderr)

    def test_each_shard_has_its_own_empty_tmpdir(self):
        # Two concurrently running shards each list their temp directory before and
        # after writing to it. A shared TMPDIR (the old runner) shows the sibling's file.
        source = (
            "import os, tempfile, time, unittest\n"
            "class Owned(unittest.TestCase):\n"
            "    def test_only_own_scratch(self):\n"
            "        tmp = tempfile.gettempdir()\n"
            "        self.assertEqual(os.environ.get('TMPDIR'), tmp)\n"
            "        self.assertEqual(os.listdir(tmp), [])\n"
            "        with tempfile.NamedTemporaryFile(prefix='hass-h02-'):\n"
            "            time.sleep(1.0)\n"
            "            self.assertEqual(len(os.listdir(tmp)), 1, os.listdir(tmp))\n"
            "        print('SHARD-TMP', tmp)\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tests = root / "hass" / "tests"
            tests.mkdir(parents=True)
            for package in (root / "hass", tests):
                (package / "__init__.py").touch()
            for name in ("test_a.py", "test_b.py"):
                (tests / name).write_text(source)
            shutil.copyfile(run_parallel.__file__, tests / "run_parallel.py")
            outer = root / "outer-tmp"
            outer.mkdir()
            env = dict(os.environ, TMPDIR=str(outer))
            parallel = subprocess.run(
                [sys.executable, "hass/tests/run_parallel.py", "--jobs", "2"],
                cwd=root, capture_output=True, text=True, env=env,
            )
            out = parallel.stdout + parallel.stderr
            self.assertEqual(parallel.returncode, 0, out)
            dirs = set(re.findall(r"SHARD-TMP (\S+)", out))
            self.assertEqual(len(dirs), 2, out)
            for path in dirs:
                self.assertTrue(Path(path).is_relative_to(outer), path)
                # Only "/hpXXXXXXXX/N" deeper than the inherited TMPDIR (AF_UNIX paths are short).
                self.assertLessEqual(len(path) - len(str(outer)), len("/hpXXXXXXXX/9"), path)
            self.assertEqual(os.listdir(outer), [])  # shard dirs are removed with the run
