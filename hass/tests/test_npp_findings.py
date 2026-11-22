"""Offline CLI contracts for the private findings ledger."""

from contextlib import ExitStack, redirect_stdout
import csv
import fcntl
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.hass import npp_findings


SCRIPT = Path(npp_findings.__file__).resolve()
GUARDS = SCRIPT.parents[2] / "hass/npp/assets/hass-npp-reply/reply-templates.json"
WEEK = "2099-W02"
HEADER = "id\tweek\tstage\tclass\tsummary\tcase_id\tcard\tstate\treason\n"


class FindingsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.ledger = self.root / "findings.tsv"

    def command(self, *args):
        return [sys.executable, "-B", str(SCRIPT), "--ledger", str(self.ledger), *args]

    def cli(self, *args, code=0):
        result = subprocess.run(self.command(*args), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, code, (result.stdout, result.stderr))
        return result.stdout.splitlines()

    @staticmethod
    def add_args(week=WEEK, stage="S1", kind="preview-fallback", summary="Preview fell back"):
        return ("add", "--week", week, "--stage", stage, "--class", kind, "--summary", summary)

    def add(self, **kwargs):
        finding, = self.cli(*self.add_args(**kwargs))
        return finding

    def rows(self):
        with self.ledger.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    def test_c1_add_refuses_private(self):
        # A partial redaction rule or TSV field injection must never reach storage.
        self.cli(*self.add_args(summary="Unredacted @ sentinel"), code=1)
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(self.add(summary="Résumé redacted <n> + fallback"), f"F-{WEEK}-1")
        self.assertEqual(self.add(stage="S13"), f"F-{WEEK}-2")
        self.assertEqual(self.add(week="2099-W03"), "F-2099-W03-1")
        self.assertEqual(self.add(), f"F-{WEEK}-3")
        self.assertTrue(self.ledger.read_text(encoding="utf-8").startswith(HEADER))
        self.assertEqual(stat.S_IMODE(self.ledger.stat().st_mode), 0o600)
        self.assertEqual(self.rows()[0], dict(
            id=f"F-{WEEK}-1", week=WEEK, stage="S1", summary="Résumé redacted <n> + fallback",
            case_id="", card="", state="open", reason="", **{"class": "preview-fallback"},
        ))
        original = self.ledger.read_bytes()
        for char in (*"0123456789", "@", "$", "+1", "\u0661", "\u00b2", "\t", "\n", "\r"):
            summary = f"Unredacted{char}sentinel"
            with self.subTest(char=char):
                self.assertEqual(self.cli(*self.add_args(summary=summary), code=1),
                                 ["FAIL summary must be redacted and on one line"])
                self.assertEqual(self.ledger.read_bytes(), original)
        for overrides in ({"week": "2099-W00"}, {"week": "2099-W54"}, {"week": "2099-W2"},
                          {"stage": "S0"}, {"stage": "S14"}, {"kind": "not a slug"}):
            with self.subTest(overrides=overrides):
                self.cli(*self.add_args(**overrides), code=1)
                self.assertEqual(self.ledger.read_bytes(), original)

    def test_c2_close_rules(self):
        # Missing card or ambiguous/invalid evidence must not mutate the finding.
        finding = self.add()
        original = self.ledger.read_bytes()
        for args, code in (([], 2), (["--card", "card-demo"], 2),
                           (["--case", "case-99-fixture.json"], 2),
                           (["--case", "case-99-fixture.json", "--reason", "duplicate",
                             "--card", "card-demo"], 2),
                           (["--case", "./case-99-fixture.json", "--card", "card-demo"], 1),
                           (["--case", "npp-demo", "--card", "card-demo"], 1),
                           (["--reason", "chat note", "--card", "card-demo"], 1),
                           (["--reason", "duplicate", "--card", ""], 1)):
            with self.subTest(args=args):
                self.cli("close", finding, *args, code=code)
                self.assertEqual(self.ledger.read_bytes(), original)
        self.cli("close", f"F-{WEEK}-99", "--reason", "duplicate", "--card", "card-demo", code=1)
        self.assertEqual(self.ledger.read_bytes(), original)
        closures = [("--case", "case-99-fixture.json"), ("--case", "npp-20990101-1"),
                    ("--reason", "fixture-only")]
        for index, (flag, value) in enumerate(closures):
            if index:
                finding = self.add(kind=f"fixture-{index}")
            self.assertEqual(self.cli("close", finding, flag, value, "--card", "card-demo"), [finding])
            row = next(row for row in self.rows() if row["id"] == finding)
            self.assertEqual((row["case_id"], row["card"], row["state"], row["reason"]),
                             (value if flag == "--case" else "", "card-demo", "closed",
                              value if flag == "--reason" else ""))

        original = self.ledger.read_bytes()
        self.cli("close", f"F-{WEEK}-1", "--reason", "overwrite", "--card", "card-demo", code=1)
        self.assertEqual(self.ledger.read_bytes(), original)

    def test_c3_repeat(self):
        # An open match is not a repeat; a closed exact class matches across weeks/stages.
        first = self.add()
        self.add(stage="S2")
        self.assertEqual([row["state"] for row in self.rows()], ["open", "open"])
        self.cli("close", first, "--reason", "fixture-only", "--card", "card-demo")
        repeat = self.add(week="2099-W03", stage="S13")
        self.add(week="2099-W03", kind="preview-fallback-other")
        self.add(week="2099-W03", kind="preview")
        self.add(week="2099-W03", stage="S2")
        self.assertEqual([row["state"] for row in self.rows()],
                         ["closed", "open", "repeat", "open", "open", "repeat"])
        self.cli("close", repeat, "--case", "case-99-fixture.json", "--card", "card-repeat")
        closed_repeat = self.rows()[2]
        self.assertEqual((closed_repeat["state"], closed_repeat["card"], closed_repeat["case_id"]),
                         ("repeat", "card-repeat", "case-99-fixture.json"))
        report = self.cli("report", "--week", "2099-W03")
        self.assertEqual(report[0], "open=4 closed=2 repeat=2")
        self.assertNotIn(repeat, report[1:-1])
        self.cli("close", f"F-{WEEK}-2", "--reason", "fixture-only", "--card", "card-demo")
        self.assertEqual(self.rows()[1]["state"], "closed")  # Not retroactively a repeat.

    def test_c4_report(self):
        # ISO rollover, the exact age boundary, and stale repeat/closed distinctions.
        old = self.add(week="2098-W51")
        self.cli("close", old, "--reason", "fixture-only", "--card", "card-demo")
        repeat = self.add(week="2098-W52")
        newer = self.add(kind="different")
        self.assertEqual(self.cli("report", "--week", "2099-W02"),
                         ["open=2 closed=1 repeat=1", repeat, newer, "PASS npp_findings"])
        self.assertEqual(self.cli("report", "--week", "2099-W03", code=1),
                         ["open=2 closed=1 repeat=1", repeat, newer, "FAIL npp_findings stale"])
        self.cli("close", repeat, "--reason", "fixture-only", "--card", "card-repeat")
        self.assertEqual(self.cli("report", "--week", "2099-W03"),
                         ["open=1 closed=2 repeat=1", newer, "PASS npp_findings"])

    def test_c5_atomic_bad(self):
        # A failed commit must leave complete old bytes, and writers must serialize.
        self.add()
        original = self.ledger.read_bytes()
        entries = set(self.root.iterdir())

        def interrupted_replace(temp, target):
            self.assertEqual(target, self.ledger.resolve())
            self.assertEqual(Path(temp).parent, target.parent)
            self.assertEqual(self.ledger.read_bytes(), original)
            self.assertTrue(Path(temp).read_bytes().startswith(original))
            with (target.parent / f".{target.name}.lock").open("rb") as rival:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)
            raise OSError("simulated replacement failure")

        with patch.object(npp_findings.os, "replace", side_effect=interrupted_replace) as replace:
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(npp_findings.main(["--ledger", str(self.ledger), *self.add_args()]), 1)
            replace.assert_called_once()
        self.assertEqual(output.getvalue().splitlines(), ["FAIL npp_findings ledger I/O"])
        self.assertEqual(self.ledger.read_bytes(), original)
        self.assertEqual(set(self.root.iterdir()), entries)
        old_snapshot = self.enterContext(self.ledger.open("rb"))
        with ExitStack() as stack:
            writers = [stack.enter_context(subprocess.Popen(
                self.command(*self.add_args()), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )) for _ in range(4)]
            results = set()
            for writer in writers:
                stdout, stderr = writer.communicate(timeout=10)
                self.assertEqual(writer.returncode, 0, stderr)
                results.add(stdout.strip())
        self.assertEqual(results, {f"F-{WEEK}-{i}" for i in range(2, 6)})
        self.assertEqual([row["id"] for row in self.rows()], [f"F-{WEEK}-{i}" for i in range(1, 6)])
        self.assertEqual(old_snapshot.read(), original)

        for corrupt, line in ((b"", 1), (b"bad header\n", 1),
                              (original + b"broken\n", 3), (original + b"\xff\n", 3),
                              (original + original.splitlines(keepends=True)[1], 3),
                              (original.replace(b"Preview fell back", b"Not redacted @"), 2),
                              (original.replace(b"\topen\t", b"\tclosed\t"), 2)):
            with self.subTest(line=line, fixture=corrupt):
                self.ledger.write_bytes(corrupt)
                for args in (("report", "--week", WEEK), self.add_args(),
                             ("close", f"F-{WEEK}-1", "--reason", "duplicate", "--card", "card-demo")):
                    self.assertEqual(self.cli(*args, code=1), [f"FAIL bad-ledger {line}"])
                    self.assertEqual(self.ledger.read_bytes(), corrupt)

    def test_c5_refuses_git_worktrees(self):
        # Both ordinary checkout markers and linked-worktree gitfiles are a boundary.
        checkout = self.root / "checkout"
        checkout.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(checkout, target_is_directory=True)
        marker = checkout / ".git"
        marker.mkdir()
        for directory in (checkout, alias):
            self.ledger = directory / "findings.tsv"
            self.assertEqual(self.cli(*self.add_args(), code=1), ["FAIL ledger must be outside Git worktrees"])
        marker.rmdir()
        marker.write_text("gitdir: ../fixture-metadata\n", encoding="utf-8")
        self.assertEqual(self.cli("report", "--week", WEEK, code=1), ["FAIL ledger must be outside Git worktrees"])
        self.assertEqual(list(checkout.iterdir()), [marker])

    # Import rows follow npp_review_export.py: event rows, then one row per job with its summary.
    @staticmethod
    def job_row(job, **facts):
        summary = dict(segment_s=[None], slow=False, stages=None, fallbacks=None, drifted_steps=None,
                       failed_checks=None, approval_role=None, edits=0, questions=0, evidence="missing")
        return dict(job=job, state="card_out", segments=1,
                    versions=[dict(n=1, state="delivered", image_variant="raw")], summary=summary | facts)

    @staticmethod
    def event_row(chat="chat-1", direction="out", text="Use this title"):
        return dict(day="2099-01-12", chat=chat, dir=direction, kind="text", text_redacted=text,
                    attachments=0, disposition="queued")

    def export(self, *rows, name="review.jsonl"):
        path = self.root / name
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path

    def import_export(self, path, week=WEEK, code=0):
        return self.cli("import", "--export", str(path), "--week", week, code=code)

    def table(self):
        return [(row["id"], row["stage"], row["class"], row["summary"], row["state"]) for row in self.rows()]

    def test_c6_import(self):
        # C6: one finding per job and class from each summary fact and each outgoing guard line; no finding for
        # a single question, no edits, an owner echoing a guard line, or ordinary replies; duplicates collapse.
        guards = json.loads(GUARDS.read_text(encoding="utf-8"))["guards"]
        stages = [dict(stage="S1", ms=400, outcome="ok"), dict(stage="S6", ms=75000, outcome="fallback"),
                  dict(stage="S2", ms=6000, outcome="fallback")]
        busy = self.job_row("c0de", slow=True, stages=stages, fallbacks=["label-local", "picture-raw"],
                            drifted_steps=["identify"], questions=2, edits=2, evidence="recorded")
        path = self.export(
            self.event_row(text=guards["not_ready"]), self.event_row(text=guards["not_ready"]),
            self.event_row(chat="chat-12", text=" " + guards["replaced"].upper()),
            self.event_row(direction="in", text=guards["which_card"]), self.event_row(text="Use this title"),
            busy,
            self.job_row("beef", questions=1, segment_s=[75.0]),
            self.job_row("cafe", slow=True, fallbacks=["picture-raw", "[redacted]", "[redacted]"], edits=1),
            self.job_row("cafe", slow=True, fallbacks=["picture-raw"], edits=1),
            self.job_row("f00d", questions=3, drifted_steps=["copy_select"], evidence="recorded"),
        )
        prior = self.add(kind="slow")
        self.cli("close", prior, "--reason", "fixture-only", "--card", "card-demo")
        week = "2099-W03"
        output = self.import_export(path, week)
        ids = [f"F-{week}-{n}" for n in range(1, 15)]
        self.assertEqual(output, [*ids, "PASS npp_findings import added=14 existing=0"])
        self.assertEqual(self.table()[1:], [(finding, *row) for finding, row in zip(ids, [
            ("S11", "guard-not-ready", "chat h: guard reply not ready sent", "open"),
            ("S11", "guard-replaced", "chat hi: guard reply replaced sent", "open"),
            ("S6", "slow", "job cgde: a work segment passed the time-to-card target", "repeat"),
            ("S2", "fallback-label-local", "job cgde: the card used fallback label-local", "open"),
            ("S6", "fallback-picture-raw", "job cgde: the card used fallback picture-raw", "open"),
            ("S3", "question", "job cgde: asked more than one question", "open"),
            ("S2", "drift-identify", "job cgde: step identify returned a model other than its pin", "open"),
            ("S10", "edit", "job cgde: edited after a card was delivered", "open"),
            ("S9", "slow", "job cafe: a work segment passed the time-to-card target", "repeat"),
            ("S6", "fallback-picture-raw", "job cafe: the card used fallback picture-raw", "open"),
            ("S9", "fallback-redacted", "job cafe: the card used fallback redacted", "open"),
            ("S10", "edit", "job cafe: edited after a card was delivered", "open"),
            ("S3", "question", "job fggd: asked more than one question", "open"),
            ("S5", "drift-copy-select", "job fggd: step copy-select returned a model other than its pin", "open"),
        ])])
        self.assertEqual(stat.S_IMODE(self.ledger.stat().st_mode), 0o600)
        self.assertEqual(self.cli("report", "--week", week)[0], "open=14 closed=1 repeat=2")

    def test_c7_idempotent(self):
        # C7: a second import of one export, a later export repeating its jobs, a closed import and
        # concurrent importers must never add a finding twice or rewrite the ledger for nothing.
        rows = [self.event_row(text=json.loads(GUARDS.read_text(encoding="utf-8"))["guards"]["replaced"]),
                self.job_row("c0de", slow=True, edits=1), self.job_row("beef", fallbacks=["picture-raw"])]
        path = self.export(*rows)
        first = self.import_export(path)
        self.assertEqual(first[-1], "PASS npp_findings import added=4 existing=0")
        original, inode = self.ledger.read_bytes(), self.ledger.stat().st_ino
        self.assertEqual(self.import_export(path), ["PASS npp_findings import added=0 existing=4"])
        self.assertEqual((self.ledger.read_bytes(), self.ledger.stat().st_ino), (original, inode))

        self.cli("close", first[1], "--reason", "fixture-only", "--card", "card-demo")
        closed = self.ledger.read_bytes()
        self.assertEqual(self.import_export(path), ["PASS npp_findings import added=0 existing=4"])
        self.assertEqual(self.ledger.read_bytes(), closed)

        # Next week's export lists every receipt again; only the new job and the new week's guard line are new.
        later = self.export(*rows, self.job_row("f00d", edits=1), name="later.jsonl")
        self.assertEqual(self.import_export(later, "2099-W03"),
                         ["F-2099-W03-1", "F-2099-W03-2", "PASS npp_findings import added=2 existing=3"])
        self.assertEqual([row["class"] for row in self.rows()][-2:], ["guard-replaced", "edit"])
        self.assertEqual(self.rows()[-1]["summary"], "job fggd: edited after a card was delivered")

        settled = self.ledger.read_bytes()
        racing = self.export(*rows, self.job_row("abcd", slow=True), self.job_row("dcba", questions=2),
                             name="racing.jsonl")
        with ExitStack() as stack:
            importers = [stack.enter_context(subprocess.Popen(
                self.command("import", "--export", str(racing), "--week", "2099-W03"),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)) for _ in range(4)]
            trailers = []
            for importer in importers:
                stdout, stderr = importer.communicate(timeout=10)
                self.assertEqual(importer.returncode, 0, stderr)
                trailers.append(stdout.splitlines()[-1])
        self.assertEqual(sorted(trailers), ["PASS npp_findings import added=0 existing=6"] * 3
                         + ["PASS npp_findings import added=2 existing=4"])
        self.assertTrue(self.ledger.read_bytes().startswith(settled))
        self.assertEqual([row["id"] for row in self.rows()][-2:], ["F-2099-W03-3", "F-2099-W03-4"])
        self.assertEqual(len(self.rows()), len({(row["class"], row["summary"], row["week"]) for row in self.rows()}))

    def test_c8_redacted_only(self):
        # C8: only the job id, the named summary facts and a matched guard key build a summary; raw or extra
        # fields, unredacted names and unmatched text never reach the ledger, and a bad export is refused whole.
        canaries = ("Canary Farm Lane", "canary@example.invalid", "canary.example.invalid", "7541",
                    "canarysender", "Canary-Mixed")
        event = self.event_row(text="Canary Farm Lane said hello") | dict(
            text="canary@example.invalid", sender="canarysender", kind="Canary-Mixed")
        job = self.job_row("feed", fallbacks=["canary.example.invalid", "price-7541", "Canary-Mixed",
                                              "-".join(["canary"] * 8), "[redacted]"],
                           drifted_steps=["canary.example.invalid"], failed_checks=["canarysender"],
                           approval_role="Canary Farm Lane", evidence="recorded", note="canary@example.invalid")
        job |= dict(title="Canary Farm Lane", cost="7541")
        result = subprocess.run(self.command("import", "--export", str(self.export(event, job)), "--week", WEEK),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(result.stdout.splitlines()[-1], "PASS npp_findings import added=2 existing=0")
        self.assertEqual([(row["class"], row["summary"]) for row in self.rows()], [
            ("fallback-redacted", "job feed: the card used fallback redacted"),
            ("drift-redacted", "job feed: step redacted returned a model other than its pin")])
        stored = (self.ledger.read_text(encoding="utf-8") + result.stdout).lower()
        self.assertNotIn("canary", stored)
        for canary in canaries:
            with self.subTest(canary=canary):
                self.assertNotIn(canary.lower(), stored)

        original = self.ledger.read_bytes()
        for bad in ('{"job": "Canary Farm Lane", "summary": {}}\n', "Canary Farm Lane 7541\n", "[]\n",
                    json.dumps(self.job_row("feed", edits="7541")) + "\n",
                    json.dumps(self.job_row("feed") | dict(summary=None)) + "\n",
                    json.dumps(self.event_row(chat="canarysender")) + "\n",
                    json.dumps(dict(cost="7541")) + "\n"):
            with self.subTest(bad=bad):
                path = self.root / "bad.jsonl"
                path.write_text(json.dumps(self.job_row("abcd", slow=True)) + "\n" + bad, encoding="utf-8")
                self.assertEqual(self.import_export(path, code=1), ["FAIL bad-export"])
                self.assertEqual(self.ledger.read_bytes(), original)
        self.assertEqual(self.import_export(self.root / "missing.jsonl", code=1), ["FAIL bad-export"])
