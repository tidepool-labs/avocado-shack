#!/usr/bin/env python3
"""Draw the checked-in NPP golden cases using the offline phone-card preview."""
import argparse
from base64 import b64encode
from datetime import datetime, timezone
from functools import partial
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from hass import claims, editor, media, preview, sandbox, sandbox_editor  # noqa: E402
from hass.content_model import load_content  # noqa: E402
from hass.conversation import Conversation  # noqa: E402
from hass.npp import assets, copy, missing, picture, private_numbers, validate  # noqa: E402

CASES = ROOT / 'hass/tests/npp/cases'
GOLDENS = ROOT / 'hass/npp/assets/hass-gallery-style/golden'
CASE_IDS = tuple(f'{i:02}' for i in range(1, 13))


def _json(path):
    return json.loads(path.read_bytes())


def _output_path(raw):
    out = raw.expanduser().resolve()
    for parent in (out, *out.parents):
        # Also catches linked worktrees and submodules, where .git is a file.
        if os.path.lexists(parent / '.git'):
            raise ValueError('output inside a git worktree')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError('output must be a new or empty directory')
    return out


def _dependencies(previewer, requested):
    node = shutil.which(requested or 'node')
    if node is None:
        return 'node'
    node = os.path.abspath(node)
    try:
        check = subprocess.run([node, '--version'], capture_output=True, text=True,
                               env={k: previewer.env[k] for k in ('PATH', 'HOME') if k in previewer.env},
                               timeout=5)
        if check.returncode or not check.stdout.strip().startswith('v22.'):
            return 'node'
    except (OSError, subprocess.TimeoutExpired):
        return 'node'
    previewer.env['NODE'] = node
    configured = previewer.env.get('PLAYWRIGHT_MODULE')
    modules = ([Path(configured).expanduser()] if configured else
               [p / 'node_modules/playwright' for p in preview.SCRIPT.parents])
    for module in modules:
        try:
            if _json(module / 'package.json')['version'] == preview.PLAYWRIGHT_VERSION:
                previewer.env['PLAYWRIGHT_MODULE'] = str(module.resolve())
                return None
        except (OSError, ValueError, KeyError):
            continue
    return 'playwright'


def _sandbox(box):
    """Stage a catalog without the golden originals, so product.add isn't a duplicate."""
    worktree = box / 'catalog'
    for rel in editor.REVISION_PATHS:
        dest = worktree / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if rel != 'hass/content/products.json':
            dest.symlink_to(ROOT / rel)
            continue
        doc = _json(ROOT / rel)
        golden_ids = {path.stem for path in GOLDENS.glob('*.json')}
        doc['products'] = [row for row in doc['products'] if row['id'] not in golden_ids]
        dest.write_text(json.dumps(doc), encoding='utf-8')
    site = worktree / preview.SITE
    for rel in ('assets', 'assets/products'):
        dest = site / rel
        dest.mkdir(parents=True, exist_ok=True)
        for src in (ROOT / preview.SITE / rel).iterdir():
            if src.name != 'products':
                (dest / src.name).symlink_to(src)
    state = editor.open_state(box / 'state', worktree)
    media_root = box / 'media'
    now = datetime.now(timezone.utc)
    editor._write_json(state / 'config.json', {'worktree': str(worktree), 'settings': {'mediaRoot': str(media_root)}})
    gate = sandbox.Gate(lambda: {'approvals': 'private'}, lambda: {('site', 'sandbox'): str(worktree)})
    return sandbox_editor.SiteEditor(state, gate, None, clock=lambda: now), media_root, now, load_content(worktree / 'hass/content')


def _draw(case, session, writer, media_root, now, catalog):
    turn = case['turns'][0]
    # These fixtures supply a separate, already answered price clause. Parse it as
    # such so item wording (e.g. half-and-half) cannot be mistaken for finance.
    owner, _, price_clause = turn['text'].rpartition(', ')
    finance = private_numbers.finance(price_clause, answer_unit='each')
    if not finance.price_span:
        raise ValueError('no fixture price')
    # Golden cases supply a category and known-maker hint; do not run S2 or S4.
    fields = case['expect']['listing']
    category = fields['category']
    kind = {'flowers': 'non-food', 'drinks': 'drink'}.get(category, 'food')
    maker = missing._maker(case['inputs']['known_maker'], {}, catalog.makers)
    brand = (maker.phrase or '') if maker.state == 'known' else ''
    photo = (CASES / 'photos' / turn['photos'][0].removeprefix('npp:')).read_bytes()
    ident = media.store_original(media_root, photo, received_at=now.isoformat(), source='gallery-fixture')['sha256']
    web = media.web_copy(media_root, ident)
    source_read = picture.read_text(Path(web['path']).read_bytes())
    ctx = copy.Context(kind, category, 'raw', owner.rsplit(', ', 1)[-1], owner,
                       brand=brand, source_read=source_read or '', private=finance.private,
                       other_descriptions=tuple(p['description'] for p in catalog.active_products() if p.get('description')))
    written = writer.write(ctx, None)
    if written is None:
        raise ValueError('copy defaults refused')
    args = {k: written.text[k] for k in ('name', 'description', 'imageAlt')}
    args.update(category=category, brand=brand or claims.PLACEHOLDER, photo=ident, sellingPrice=finance.selling_price)
    place = None
    if maker.state == 'known':
        args['producerKey'] = maker.key
        place = catalog.makers[maker.key].get('place')
    prepared = session.editor.candidate([{'op': 'product.add', 'args': args}])
    if prepared.get('result') != 'ok':
        raise ValueError('sandbox candidate refused')
    draft = prepared['draft']
    product = draft['records'][0]['after']
    # The same capture as ProductionStages.render_listing, without creating a chat or running a job.
    shot = Conversation._capture(session, draft, candidate=True)
    if not shot.get('ok'):
        return product, None, preview.failure_kind(shot.get('error'))
    png = Path(shot['png']).read_bytes()
    if not png.startswith(preview.PNG_SIGNATURE) or not isinstance(shot.get('picture'), bytes):
        return product, None, 'invalid-capture'
    verdict = validate.listing(writer, ctx, written, draft, finance=finance,
                               origin=f'Based in {place}' if place else validate.ORIGIN_UNKNOWN,
                               makers=catalog.makers, live_site=None, photo_sha=ident,
                               frozen_sha=web['web_sha256'], rendered_sha=sha256(shot['picture']).hexdigest(),
                               picture_read=picture.read_text(shot['picture']), card_evidence=shot.get('cardEvidence'),
                               card_png=png, added_on_now=now)
    validation = 'PASS' if verdict.ok else 'REFUSED: ' + ', '.join(verdict.problems)
    return product, png, validation


def _section(case_id, golden, product=None, digest=None, status=''):
    card = golden['card']
    reference = (ROOT / preview.SITE / golden['photo_path']).read_bytes()
    ref_src = 'data:image/webp;base64,' + b64encode(reference).decode('ascii')
    image = f'<img src="card-{case_id}.png" alt="Drawn card">' if digest else ''
    details = '' if product is None else (
        f'<p>Name: {escape(product["name"])}</p><p>Price: ${escape(product["sellingPrice"])}</p>'
        f'<p>Category: {escape(product["category"])}</p>')
    receipt = f'<p>PNG SHA-256: <code>{digest}</code></p>' if digest else ''
    return (f'<section><h2>Case {case_id}</h2><div class="pair"><article><h3>Drawn listing</h3>{image}{details}'
            f'<p>{escape(status)}</p>{receipt}</article><article><h3>Golden reference (saved fixture)</h3>'
            f'<img src="{ref_src}" alt="{escape(card["photo_alt"])}"><p>Name: {escape(card["name"])}</p>'
            f'<p>Category: {escape(golden["category"])}</p><p>{escape(card["description"])}</p></article></div></section>')


PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'">
<title>Private NPP card gallery</title>
<style>body{font:1rem system-ui;margin:1rem auto;padding:0 1rem;max-width:56rem}
.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem}
article{background:#f4f3ee;padding:.75rem;overflow-wrap:anywhere}img{max-width:100%;height:auto}
@media(max-width:36rem){.pair{grid-template-columns:1fr}}</style>
<h1>Private NPP card gallery</h1><p>Offline fixtures only. Prices are examples. Validation is not approval.</p>
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True, help='new or empty private directory outside Git')
    parser.add_argument('--strict', action='store_true', help='fail if capture dependencies are missing')
    parser.add_argument('--node', help='Node 22 executable')
    parser.add_argument('--case', nargs='+', action='extend', choices=CASE_IDS, help='case numbers (default: all 12)')
    args = parser.parse_args(argv)
    try:
        out = _output_path(args.out)
        previewer = preview.Previewer(ROOT, viewports=('phone',))
        dep = _dependencies(previewer, args.node)
        if dep and args.strict:
            print(f'FAIL missing {dep}')
            return 1
        out.mkdir(mode=0o700, parents=True, exist_ok=True)
        out.chmod(0o700)
        sections, failed, drawn = [], False, 0
        with tempfile.TemporaryDirectory(prefix='sandbox-', dir=out) as raw:
            draw = None
            if not dep:
                site_editor, media_root, now, content = _sandbox(Path(raw))
                session = SimpleNamespace(editor=site_editor, previewer=previewer, sdir=Path(site_editor.state))
                draw = partial(_draw, session=session, writer=copy.Writer(assets()), media_root=media_root,
                               now=now, catalog=content)
            for case_id in dict.fromkeys(args.case or CASE_IDS):
                case = _json(next(CASES.glob(f'case-{case_id}-golden-*.json')))
                golden = _json(GOLDENS / Path(case['golden']).name)
                product, png, verdict = None, None, ''
                if not dep and draw is not None:
                    try:
                        product, png, verdict = draw(case)
                    except (OSError, ValueError, media.Refused):
                        verdict = 'fixture-refused'
                    if png is None and verdict in ('playwright-missing', 'browser-missing', 'node-too-old', 'node-missing'):
                        dep = 'node' if verdict.startswith('node-') else 'playwright'
                        if args.strict:
                            print(f'FAIL missing {dep}')
                            return 1
                digest = None
                if dep:
                    status = f'NOT-RUN {case_id} {dep}'
                    print(status)
                elif png is None:
                    status = f'FAIL {case_id} {verdict}'
                    print(status)
                    failed = True
                else:
                    digest = sha256(png).hexdigest()
                    preview._write_private(out / f'card-{case_id}.png', png)
                    drawn += 1
                    status = f'Validate: {verdict}'
                    print(f'DRAWN {case_id} {status}')
                sections.append(_section(case_id, golden, product, digest, status))
        preview._write_private(out / 'index.html', (PAGE + '\n'.join(sections)).encode('utf-8'))
        print(f'DRAWN {drawn} card(s)')
        return int(failed)
    except (OSError, ValueError, editor.UnsafeState, StopIteration, KeyError):
        print('FAIL invalid output or fixture gallery unavailable')
        return 1


if __name__ == '__main__':
    sys.exit(main())
