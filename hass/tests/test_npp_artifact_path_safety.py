"""Exercise the audit's CLI contract and its response to fixture regressions."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_artifact_path_safety.py"
PASS = "PASS npp_artifact_path_safety"
FAIL = "FAIL npp_artifact_path_safety"
MODES = "modes root=700 job=700 card=600"


class NppArtifactPathSafetyTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        spec = importlib.util.spec_from_file_location("npp_artifact_path_safety", SCRIPT)
        if spec is None or spec.loader is None:
            self.fail("could not load the audit script")
        self.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.tool)
        self.store = self.tool.receipt.Artifacts

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args], cwd=self.root,
            env={**os.environ, "TMPDIR": str(self.root)},
            capture_output=True, text=True, timeout=8,
        )

    def main(self):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch.object(tempfile, "tempdir", str(self.root)):
            code = self.tool.main([])
        self.assertEqual(err.getvalue(), "")
        return code, out.getvalue().splitlines()

    def assert_pass(self, result):
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(result.stdout.splitlines()[-1:], [PASS])

    def assert_findings(self, *reasons, modes=MODES):
        code, lines = self.main()
        self.assertEqual(code, 1)
        self.assertEqual(lines[-1:], [FAIL])
        self.assertEqual([line for line in lines[:-1] if line != modes],
                         [f"FAIL {reason}" for reason in reasons])
        return lines[:-1]

    def test_c1_full_pass(self):
        # A false alarm on the unmodified store must not break the CLI exit contract.
        self.assert_pass(self.cli())

    def test_c2_findings_trailer(self):
        # Multiple violations must still have exactly one terminal failure summary.
        with patch.object(self.tool.receipt, "JOB_RE", r"[0-9A-Za-z]{3,13}"), \
                patch.object(self.tool.receipt, "RECEIPT_MAX", 1 << 20):
            self.assert_findings("job-accepted 0", "job-accepted 1", "job-accepted 2",
                                 "unsafe-write big-receipt")

    def test_c2_1_job_accepted(self):
        # Every bad input must be sent to the writer, even path-shaped and empty ids.
        bad = ("ABCD", "abc", "aaaaaaaaaaaaa", "../x", "abcd/e", "")
        write_card = self.store.write_card
        seen = []

        def accept(store, job, png):
            if job in bad:
                seen.append(job)
                return None
            return write_card(store, job, png)

        with patch.object(self.store, "write_card", accept):
            self.assert_findings(*(f"job-accepted {i}" for i in range(len(bad))))
        self.assertEqual(seen, list(bad))

    def test_c2_2_job_refused(self):
        # Rejecting valid ids (including either length endpoint) is also a finding.
        write_card = self.store.write_card
        for denied in ("abcd", "0123456789ab"):
            with self.subTest(job=denied):
                def write(store, job, png):
                    if job == denied:
                        raise ValueError
                    return write_card(store, job, png)

                with patch.object(self.store, "write_card", write):
                    self.assert_findings(f"job-refused {denied}")

    def test_c2_3_unsafe_read(self):
        # An accepting reader should be detected for each real negative file fixture.
        read_artifact = self.tool.receipt.read_artifact
        seen = set()

        def read(path):
            if path.is_symlink():
                seen.add("symlink")
            elif path.is_fifo():
                self.assertEqual(path.name, "receipt.json")
                seen.add("fifo")
            elif path.name == "card-" + "ef" * 32 + ".png":
                seen.add("bad-hash")
            elif path.name == "notes.txt":
                self.assertEqual(path.read_bytes(), b"{}")
                seen.add("other-name")
            else:
                return read_artifact(path)
            return b"unexpectedly accepted"

        kinds = ("symlink", "fifo", "bad-hash", "other-name")
        with patch.object(self.tool.receipt, "read_artifact", read):
            self.assert_findings(*(f"unsafe-read {kind}" for kind in kinds))
        self.assertEqual(seen, set(kinds))

    def test_c2_4_unsafe_write(self):
        # A relaxed cap, type, digest or directory check must not disappear into PASS.
        write_card, card, folder = self.store.write_card, self.store.card, self.store.folder

        def write(store, job, png):
            if png == b"GIF89a" or store.root.is_symlink():
                return None
            return write_card(store, job, png)

        def resolve(store, job, digest):
            if job == "abcd" and digest == "zz":
                return None
            return card(store, job, digest)

        def locate(store, job, **kwargs):
            if job == "beef" and (store.root / job).is_symlink():
                return store.root / job
            return folder(store, job, **kwargs)

        kinds = ("big-receipt", "not-png", "bad-digest", "symlink-dir", "symlink-root")
        with patch.object(self.tool.receipt, "RECEIPT_MAX", 1 << 20), \
                patch.object(self.store, "write_card", write), \
                patch.object(self.store, "card", resolve), \
                patch.object(self.store, "folder", locate):
            self.assert_findings(*(f"unsafe-write {kind}" for kind in kinds))

        # Rejecting only after changing the prior receipt is not safe either.
        write_receipt = self.store.write_receipt

        def corrupt(store, job, record):
            if "x" in record:
                (store.root / job / "receipt.json").write_bytes(b"{}")
                raise ValueError
            return write_receipt(store, job, record)

        with patch.object(self.store, "write_receipt", corrupt):
            self.assert_findings("unsafe-write big-receipt")

    def test_c2_5_mode(self):
        # Compare actual filesystem permissions, not constructor defaults.
        write_card = self.store.write_card

        def write(store, job, png):
            path, digest = write_card(store, job, png)
            if job == "abcd":
                store.root.chmod(0o755)
                path.parent.chmod(0o750)
                path.chmod(0o640)
            return path, digest

        modes = "modes root=755 job=750 card=640"
        with patch.object(self.store, "write_card", write):
            lines = self.assert_findings("mode root", "mode job", "mode card", modes=modes)
        self.assertEqual(lines[0], modes)

    def test_c2_6_round_trip(self):
        # Nonempty but differing reader bytes must be rejected independently of type.
        read_artifact = self.tool.receipt.read_artifact

        def altered(path):
            return read_artifact(path) + b" "

        with patch.object(self.tool.receipt, "read_artifact", altered):
            self.assert_findings("round-trip card", "round-trip receipt")

    def test_c2_7_temp_left(self):
        # A successful write can still leak a temporary receipt in the NPP root.
        write_receipt = self.store.write_receipt

        def leak(store, job, record):
            write_receipt(store, job, record)
            (store.root / ".receipt-left").touch()

        with patch.object(self.store, "write_receipt", leak):
            self.assert_findings("temp-left")

    def test_c2_8_check_error(self):
        # An unrelated filesystem error type cannot count as the expected refusal.
        with patch.object(self.store, "card", side_effect=RuntimeError("fixture detail")):
            self.assert_findings("check-error")

    def test_c3_usage_exit_2(self):
        # Even argparse's normal help and delimiter forms are not accepted here.
        for arg in ("extra", "--unknown", "--help", "-h", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("error:", result.stderr.splitlines()[-1])

    def test_c4_read_only(self):
        # Detect additions/removals and rewrites, including directory mtime changes.
        def snapshot():
            entries = {}
            for folder in (ROOT / "hass", ROOT / "storefront-mockup"):
                for path in (folder, *folder.rglob("*")):
                    info = path.lstat()
                    entries[path.relative_to(ROOT)] = (info.st_size, info.st_mtime_ns)
            return entries

        before = snapshot()
        self.assert_pass(self.cli())
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_c5_output_shape(self):
        # Debug output or duplicated mode lines would break the consumable report.
        result = self.cli()
        self.assert_pass(result)
        self.assertEqual(result.stdout.splitlines(), [MODES, PASS])
        with patch.object(self.tool.receipt, "JOB_RE", r"[0-9A-Za-z]{3,13}"):
            lines = self.assert_findings("job-accepted 0", "job-accepted 1", "job-accepted 2")
        self.assertEqual(lines, ["FAIL job-accepted 0", "FAIL job-accepted 1",
                                 "FAIL job-accepted 2", MODES])

    def test_c6_fixture(self):
        # The regex mutation exercises the actual writer rather than a copied rule.
        with patch.object(self.tool.receipt, "JOB_RE", r"[0-9A-Za-z]{3,13}"):
            self.assert_findings("job-accepted 0", "job-accepted 1", "job-accepted 2")

    def test_c7_live_pins(self):
        # Pin private modes measured on an untouched Linux checkout.
        result = self.cli()
        self.assert_pass(result)
        self.assertEqual(result.stdout.splitlines().count(MODES), 1)
