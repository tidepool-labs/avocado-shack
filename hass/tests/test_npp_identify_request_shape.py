"""Offline acceptance of the S2 request check, with faults at the wire boundary."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hass import interpreter_local
from hass.npp import identify


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/hass/npp_identify_request_shape.py"
NAME = "npp_identify_request_shape"
PASS = f"PASS {NAME}"
FAIL = f"FAIL {NAME}"
CLOUD = "reader cloud requests=1 images=3"
LOCAL = "reader local requests=1 images=3"


def snapshot():
    entries = {}
    for tree in (ROOT / "hass", ROOT / "storefront-mockup"):
        for path in (tree, *tree.rglob("*")):
            stat = path.lstat()
            entries[path.relative_to(ROOT)] = (stat.st_size, stat.st_mtime_ns)
    return entries


class IdentifyRequestShapeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cwd = Path(temporary.name)
        spec = importlib.util.spec_from_file_location(NAME, SCRIPT)
        assert spec is not None and spec.loader is not None
        self.tool = importlib.util.module_from_spec(spec)
        with patch.object(sys, "dont_write_bytecode", True), patch.object(sys, "path", sys.path.copy()):
            spec.loader.exec_module(self.tool)

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], cwd=self.cwd,
                              capture_output=True, text=True, timeout=10)

    def run_main(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.tool.main([])
        self.assertEqual(err.getvalue(), "")
        return code, out.getvalue().splitlines()

    def assert_main(self, code, *lines):
        exit_code, stdout = self.run_main()
        self.assertEqual(exit_code, code)
        self.assertEqual(stdout, list(lines))

    def wire_fault(self, api, transform):
        """Let production build/send the body, changing just one reader's wire data."""
        read_batch = identify._read_batch

        def run(reader, photos, prompt, schema):
            send = reader.transport

            def transport(url, body, headers, timeout):
                messages = json.loads(body)["messages"]
                transform(messages)
                return send(url, json.dumps({"messages": messages}).encode(), headers, timeout)

            if reader.api == api:
                with patch.object(reader, "transport", transport):
                    return read_batch(reader, photos, prompt, schema)
            return read_batch(reader, photos, prompt, schema)

        return patch.object(identify, "_read_batch", run)

    def test_c1_full_pass(self):
        # Catches the CLI returning a failure despite both complete checks.
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)

    def test_c2_findings_trailer(self):
        # A changed system prompt and dropped image must both be reported before FAIL.
        def change(messages):
            messages[0]["content"] += " extra"
            messages[1]["content"].pop()

        with self.wire_fault("codex", change):
            self.assert_main(1, "reader cloud requests=1 images=2", "FAIL photo-order cloud",
                             "FAIL prompt-shape cloud", LOCAL, FAIL)

    def test_c2_1_photo_order(self):
        # Catch dropped, duplicated, or swapped photos on either reader.
        for api, name in (("codex", "cloud"), ("ollama", "local")):
            for indices in ((0, 1), (0, 1, 2, 2), (0, 2, 1)):
                with self.subTest(reader=name, indices=indices):
                    def change(messages):
                        user = messages[1]
                        parts = user["content"] if api == "codex" else user["images"]
                        offset = int(api == "codex")
                        parts[offset:] = [parts[offset + index] for index in indices]

                    summary = f"reader {name} requests=1 images={len(indices)}"
                    reason = f"FAIL photo-order {name}"
                    lines = (summary, reason, LOCAL) if api == "codex" else (CLOUD, summary, reason)
                    with self.wire_fault(api, change):
                        self.assert_main(1, *lines, FAIL)

    def test_c2_2_prompt_shape(self):
        # Catch role drift, a weakened photo instruction, wrong user text, or an omitted pin.
        for api, name in (("codex", "cloud"), ("ollama", "local")):
            def user_text(messages):
                if api == "codex":
                    messages[1]["content"][0]["text"] = "Different instruction."
                else:
                    messages[1]["content"] = "Different instruction."

            for change in (list.reverse, lambda m: m[1].update(role="assistant"),
                           lambda m: m[0].update(content=m[0]["content"].splitlines()[0]),
                           user_text):
                with self.subTest(reader=name, change=change), self.wire_fault(api, change):
                    reason = f"FAIL prompt-shape {name}"
                    lines = (CLOUD, reason, LOCAL) if api == "codex" else (CLOUD, LOCAL, reason)
                    self.assert_main(1, *lines, FAIL)

        identifier = identify.Identifier
        for pin in ("schema", "examples"):
            def omit_pin(pinned, *args, **kwargs):
                ident = identifier(pinned, *args, **kwargs)
                if pin == "schema":
                    value = ident.schema
                else:
                    examples = json.loads(pinned[1][identify.ASSET + "examples.json"])["examples"]
                    value = [row["output"] for row in examples]
                ident.prompt = ident.prompt.replace(json.dumps(value), "")
                return ident

            with self.subTest(pin=pin), patch.object(identify, "Identifier", omit_pin):
                self.assert_main(1, CLOUD, "FAIL prompt-shape cloud", LOCAL, "FAIL prompt-shape local", FAIL)

    def test_c2_3_no_request(self):
        # Swallowing the send or replaying it must not pass the exactly-once check.
        read_batch = identify._read_batch
        for count in (0, 2):
            def run(reader, photos, prompt, schema):
                if reader.api == "ollama":
                    return read_batch(reader, photos, prompt, schema)
                send = reader.transport

                def transport(url, body, headers, timeout):
                    for _ in range(count):
                        send(url, body, headers, timeout)
                    return 500, b""

                with patch.object(reader, "transport", transport):
                    return read_batch(reader, photos, prompt, schema)

            with self.subTest(count=count), patch.object(identify, "_read_batch", run):
                self.assert_main(1, f"reader cloud requests={count} images=0",
                                 "FAIL no-request cloud", LOCAL, FAIL)

    def test_c2_4_check_error(self):
        # An unexpected exception is terse and does not prevent the other reader check.
        read_batch = identify._read_batch

        def run(reader, photos, prompt, schema):
            if reader.api == "codex":
                raise RuntimeError("fixture error detail")
            return read_batch(reader, photos, prompt, schema)

        with patch.object(identify, "_read_batch", run):
            self.assert_main(1, "reader cloud requests=0 images=0", "FAIL check-error", LOCAL, FAIL)

    def test_c3_usage_exit_2(self):
        # No argument, even a help or separator token, may silently run the check.
        for arg in ("positional", "--unknown", "--help", "--"):
            with self.subTest(arg=arg):
                result = self.cli(arg)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.splitlines()[-1].startswith(
                    f"{SCRIPT.name}: error: unrecognized arguments:"))

    def test_c4_read_only(self):
        # A cache or output under the repo would change paths, sizes or mtimes.
        before = snapshot()
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], PASS)
        self.assertEqual(snapshot(), before)
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_c5_output_shape(self):
        # Forbid debug chatter or payload dumps on the successful command path.
        result = self.cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, f"{CLOUD}\n{LOCAL}\n{PASS}\n")
        self.assertEqual(result.stderr, "")

    def test_c6_fixture(self):
        # Reversing inputs at the real batch call must trip both wire-order checks.
        read_batch = identify._read_batch

        def reverse(reader, photos, prompt, schema):
            return read_batch(reader, photos[::-1], prompt, schema)

        with patch.object(identify, "_read_batch", reverse):
            self.assert_main(1, CLOUD, "FAIL photo-order cloud", LOCAL, "FAIL photo-order local", FAIL)

    def test_c7_live_pins(self):
        # Observe (do not replace) the real HTTP-500 failures for both requests.
        errors = []
        read_batch = identify._read_batch

        def observe(reader, photos, prompt, schema):
            try:
                return read_batch(reader, photos, prompt, schema)
            except interpreter_local._Failed as error:
                errors.append((reader.api, error.args))
                raise

        with patch.object(identify, "_read_batch", observe):
            self.assert_main(0, CLOUD, LOCAL, PASS)
        self.assertEqual(errors, [("codex", ("http-500",)), ("ollama", ("http-500",))])
