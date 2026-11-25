#!/usr/bin/env python3
"""Produce the private Hass demo bundle from ONE strict recorded replay, then check it.

  npp_demo_bundle.py --recorded <private recording.json> --out <new private dir outside Git> [--node NODE]

In this process, on a clean checkout: runs run_npp.py --preview --json --strict --recorded <recording>.
While that runs, it notes every card version the chat transport actually received and confirmed. It then
draws the 12 gallery reference cards and writes three things into --out:
  replay.json    the replay report, byte for byte as run_npp printed it
  evidence.json  {checkout, replay_sha256, deliveries, reference_cards} (npp_demo_acceptance's schema)
  gallery/       the reference PNGs and their index page
The script then runs npp_demo_acceptance.check on those exact bytes and prints its verdict (counts only).

Deliveries come from this run's transport, never from the gallery. A gallery card counts as a reference
only if it was drawn and its validation passed. The script refuses a dirty checkout, or a HEAD that
changes during the run. This checks evidence only. It does not prove attendance, install, approval or a
live listing, and it makes no network call besides what the replay itself already does (none for a
recording).
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass.tests.npp import run_npp  # noqa: E402
from scripts.hass import npp_card_gallery, npp_demo_acceptance  # noqa: E402

DRAWN = re.compile(r'DRAWN (\d\d) Validate: PASS')


class Refused(Exception):
    """The run cannot produce acceptance evidence; the message is a short fixed reason."""


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def checkout(root=ROOT):
    """HEAD of a clean checkout; a modified or untracked file would make a mixed run."""
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True,
                              text=True, timeout=30).stdout
    try:
        head, dirty = git('rev-parse', 'HEAD').strip(), git('status', '--porcelain')
    except (OSError, subprocess.SubprocessError):
        raise Refused('checkout-unreadable') from None
    if not re.fullmatch('[0-9a-f]{40}', head):
        raise Refused('checkout-unreadable')
    if dirty.strip():
        raise Refused('checkout-dirty')
    return head


class Deliveries:
    """Collect confirmed chat deliveries per (case, variant, version) during one in-process replay."""

    def __init__(self):
        self.rows, self.variant = [], None

    def views(self, original):
        def case_views(case):
            for variant, view in original(case):
                self.variant = variant
                yield variant, view
        return case_views

    def check_card(self, original):
        def check_card(view, fx, state, versions, *args, **kwargs):
            self.note(view['id'], self.variant, fx.transport, versions)
            return original(view, fx, state, versions, *args, **kwargs)
        return check_card

    def note(self, case_id, variant, transport, versions):
        cards, receipts = getattr(transport, 'cards', {}), getattr(transport, 'receipts', {})
        for version in sorted(versions, key=lambda v: v['n']):
            row = version.get('outbox_id')
            card, receipt = cards.get(row), receipts.get(row)
            if row is None or card is None or not isinstance(receipt, dict) or not version.get('delivered_at'):
                continue
            # png: the frozen card the job queued; attachment: the bytes the chat actually received.
            self.rows.append({'id': case_id, 'variant': variant, 'n': version['n'],
                              'state': receipt.get('state'), 'png_sha256': version.get('card_png_sha'),
                              'attachment_sha256': sha256(card[1])})


def replay(recording, deliveries):
    """Run the strict recorded preview replay in this process; return the exact report bytes."""
    argv = ['--preview', '--json', '--strict', '--recorded', str(recording)]
    out = io.StringIO()
    with patch.object(run_npp, 'case_views', deliveries.views(run_npp.case_views)), \
            patch.object(run_npp, 'check_card', deliveries.check_card(run_npp.check_card)), \
            contextlib.redirect_stdout(out):
        run_npp.main(argv, environ={})
    text = out.getvalue()
    lines = text.splitlines()
    if len(lines) != 1:
        raise Refused('replay-output-not-one-report')
    try:
        report = json.loads(lines[0])
    except ValueError:
        raise Refused('replay-output-not-one-report') from None
    if not isinstance(report, dict) or 'cases' not in report:
        raise Refused('replay-did-not-run')
    return text.encode('utf-8')


def references(gallery_dir, node=None):
    """Draw the 12 gallery cards; keep only drawn cards whose validation passed, hashed from the file."""
    argv = ['--out', str(gallery_dir), '--strict'] + (['--node', node] if node else [])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        npp_card_gallery.main(argv)
    cards = []
    for case_id in dict.fromkeys(m.group(1) for m in DRAWN.finditer(out.getvalue())):
        png = gallery_dir / f'card-{case_id}.png'
        if png.is_file() and not png.is_symlink():
            cards.append({'id': case_id, 'png_sha256': sha256(png.read_bytes())})
    return cards


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)


def produce(recording, out, *, node=None, root=ROOT):
    """Return (checkout, recording_sha256, replay_bytes, evidence_bytes); files land in `out`."""
    out = npp_card_gallery._output_path(out)
    recording = Path(recording).resolve(strict=True)
    head = checkout(root)
    recorded = sha256(recording.read_bytes())
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    out.chmod(0o700)
    deliveries = Deliveries()
    raw = replay(recording, deliveries)
    if sha256(recording.read_bytes()) != recorded:
        raise Refused('recording-changed')
    cards = references(out / 'gallery', node)
    # Recheck everything at the very end: the gallery render can also change the checkout or the recording.
    if checkout(root) != head:
        raise Refused('checkout-changed')
    if sha256(recording.read_bytes()) != recorded:
        raise Refused('recording-changed')
    evidence = json.dumps({'checkout': head, 'replay_sha256': sha256(raw), 'deliveries': deliveries.rows,
                           'reference_cards': cards}, sort_keys=True).encode('utf-8')
    write_private(out / 'replay.json', raw)
    write_private(out / 'evidence.json', evidence)
    return head, recorded, raw, evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description='Produce and check the private Hass demo bundle from one run.')
    parser.add_argument('--recorded', type=Path, required=True, help='private recording (stays outside Git)')
    parser.add_argument('--out', type=Path, required=True, help='new or empty private directory outside Git')
    parser.add_argument('--node', help='Node 22 executable for the gallery')
    args = parser.parse_args(argv)
    os.umask(0o077)
    os.chdir(ROOT)
    try:
        head, recorded, raw, evidence = produce(args.recorded, args.out, node=args.node)
        result = npp_demo_acceptance.check(raw, evidence, checkout=head, recording_sha256=recorded)
    except Refused as why:
        result = {'status': 'hold', 'reasons': [str(why)]}
    except (OSError, ValueError, RecursionError):
        result = {'status': 'hold', 'reasons': ['unreadable-receipt-or-corpus']}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
