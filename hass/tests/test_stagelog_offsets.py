"""Stage table omits a derived offset that cannot be represented, without changing timestamp admission."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

from hass import stagelog

SCRIPT = str(Path(stagelog.__file__))
A, H, R, Q = "a" * 12, "b" * 12, "c" * 12, "d" * 12


def line(t, stage, ident=A, extra=""):
    return '{"t": %s, "stage": "%s", "id": "%s"%s}' % (t, stage, ident, extra)


class T(unittest.TestCase):
    def write(self, *lines, name="s.jsonl"):
        p = os.path.join(tempfile.mkdtemp(), name)
        Path(p).write_text("\n".join(lines) + "\n")
        return p

    def cli(self, *paths):
        r = subprocess.run([sys.executable, "-B", SCRIPT, *paths], capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    def test_finite_float_inputs_do_not_emit_infinite_offset(self):
        p = self.write(line("-1e308", "accepted"), line("1e308", "handled"))
        before = Path(p).read_bytes()
        rows = stagelog.read(p)
        self.assertEqual([r["t"] for r in rows], [-1e308, 1e308])
        self.assertEqual(stagelog.table(rows), [(A, {"accepted": 0.0})])
        self.assertEqual(self.cli(p), (0, "%s accepted=0.0\n" % A, ""))
        self.assertEqual(Path(p).read_bytes(), before)

    def test_overflowing_stage_does_not_lose_healthy_message_or_stage(self):
        p = self.write(line("-1e308", "accepted"), line("0", "ack-end"), line("1e308", "handled"),
                       line("1.0", "accepted", H), line("2.0", "handled", H))
        self.assertEqual(stagelog.table(stagelog.read(p)),
                         [(A, {"accepted": 0.0, "ack-end": 1e308}), (H, {"accepted": 0.0, "handled": 1.0})])
        self.assertEqual(self.cli(p), (0, "%s accepted=0.0 ack-end=1e+308\n%s accepted=0.0 handled=1.0\n" % (A, H), ""))

    def test_individually_usable_integer_extremes_have_guarded_difference(self):
        big = 10 ** 308
        self.assertTrue(stagelog._usable(big) and stagelog._usable(-big) and not stagelog._usable(2 * big))
        p = self.write(line(-big, "accepted"), line(big, "handled"), line(0, "ack-end"))
        rows = stagelog.read(p)
        self.assertEqual([(r["t"], type(r["t"])) for r in rows], [(-big, int), (big, int), (0, int)])
        self.assertEqual(stagelog.table(rows), [(A, {"accepted": 0, "ack-end": big})])
        self.assertEqual(self.cli(p)[1], "%s accepted=0 ack-end=%d\n" % (A, big))
        q = self.write(line(-big, "accepted"), line("1e308", "handled"), line("1.0", "ack-end"))
        self.assertEqual(stagelog.table(stagelog.read(q)), [(A, {"accepted": 0, "ack-end": float(big) + 1.0})])

    def test_reply_correlation_and_stage_order_survive_overflow(self):
        a = self.write(line("-1e308", "accepted"), line("-1e308", "reply-queued", A, ', "rid": "%s"' % R), name="a.jsonl")
        b = self.write(line("1e308", "reply-pulled", R), line("-1e308", "bb-send-end", R), line("5", "reply-pulled", Q), name="b.jsonl")
        rows = stagelog.read(a) + stagelog.read(b)
        self.assertEqual(stagelog.table(rows), [(A, {"accepted": 0.0, "reply-queued": 0.0, "bb-send-end": 0.0})])
        self.assertEqual(self.cli(a, b), (0, "%s accepted=0.0 reply-queued=0.0 bb-send-end=0.0\n" % A, ""))
        self.assertEqual([(r["id"], r.get("rid")) for r in rows], [(A, None), (A, R), (R, None), (R, None), (Q, None)])

    def test_conflicting_reply_bindings_leave_send_unattributed_in_either_order(self):
        # A last-wins join credits one of the two turns; falling back to the raw reply id credits R.
        # An identical binding for a different reply must still yield its measured send duration.
        good = "e" * 12
        bind_r, bind_q = (', "rid": "%s"' % rid for rid in (R, Q))
        with tempfile.TemporaryDirectory() as tmp:
            host, mac = (Path(tmp) / name for name in ("host.jsonl", "mac.jsonl"))
            host.write_text("\n".join([
                line(10, "accepted", A), line(11, "accepted", H), line(12, "accepted", R),
                line(13, "accepted", good), line(14, "reply-queued", A, bind_r),
                line(14, "reply-queued", A, bind_r), line(15, "reply-queued", H, bind_r),
                line(16, "reply-queued", good, bind_q), line(16, "reply-queued", good, bind_q),
            ]) + "\n")
            mac.write_text("\n".join([
                line(17, "reply-pulled", R), line(18, "bb-send-start", R), line(20, "bb-send-end", R),
                line(19, "reply-pulled", Q), line(21, "bb-send-start", Q), line(24, "bb-send-end", Q),
            ]) + "\n")
            rows = stagelog.read(host) + stagelog.read(mac)
        for order, records in (("forward", rows), ("reverse", rows[::-1])):
            stages = dict(stagelog.table(records))
            with self.subTest(order=order, control="matching duplicate"):
                self.assertEqual(stages[good], {"accepted": 0, "reply-queued": 3, "reply-pulled": 6,
                                                "bb-send-start": 8, "bb-send-end": 11})
            with self.subTest(order=order, control="conflict and id collision"):
                self.assertEqual({i: stages[i] for i in (A, H, R)},
                                 {A: {"accepted": 0, "reply-queued": 4},
                                  H: {"accepted": 0, "reply-queued": 4}, R: {"accepted": 0}})

    def test_duplicate_overflow_does_not_choose_a_different_occurrence(self):
        p = self.write(line("-1e308", "accepted"), line("1e308", "handled"), line("1.5e308", "handled"),
                       line("0", "ack-end"), line("7", "ack-end"), line("3", "weird"))
        self.assertEqual(stagelog.table(stagelog.read(p)), [(A, {"accepted": 0.0, "ack-end": 1e308, "weird": 1e308})])

    def test_normal_negative_fractional_and_large_same_sign_offsets_are_unchanged(self):
        hi = 2.0 ** 1000
        p = self.write(line(hi, "accepted"), line(2 * hi, "handled"), line("-3", "accepted", H), line("-2.5", "handled", H),
                       line("1.23456", "accepted", Q), line("3", "ack-end", Q), "[" * 100000, "NaN", line("1e400", "sent", Q))
        self.assertEqual(stagelog.table(stagelog.read(p)),
                         [(H, {"accepted": 0, "handled": 0.5}), (Q, {"accepted": 0.0, "ack-end": 1.765}),
                          (A, {"accepted": 0.0, "handled": hi})])
        spaced = self.write(line("1", "accepted", "x y"))
        self.assertEqual(self.cli(spaced)[1], "%s accepted=0\n" % json.dumps("x y"))


if __name__ == "__main__":
    unittest.main()
