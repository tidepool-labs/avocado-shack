"""HASS-LINK: the private link table and Mike's one-yes link draft (docs/hass/CLOVER.md section 2, "The link").

Cache and local products only: no token, no network, no editor call, so a link or unlink never sets a website word. Only an EXACT name
(mapper.norm_name) on exactly one unlinked active site product and exactly one unlinked till item is suggested; two-sided clashes and
one-sided items are listed and never linked. Files are private (folder 0700, files 0600, atomic replace).
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path

from hass.clover import cache, reports
from hass.clover.mapper import norm_name

DRAFT = "link-draft.json"


def _ident(item, group):
    """A till item's label inside its same-name group: its SKU only if nonempty and no other item has that SKU (or id), else its item id."""
    sku = (item.sku or "").strip().lower()
    return item.sku.strip() if sku and not any(sku in ((o.sku or "").strip().lower(), o.id.lower()) for o in group if o is not item) else item.id


def _labels(products, items):
    """One label per member of a same-name group (site products, then till items), distinct over the whole group: a site product's id, a
    till item's SKU-or-id; any label equal to another's (either side) becomes "site <id>" / "till <item id>"."""
    raw = [(p["id"], f"site {p['id']}") for p in products] + [(_ident(i, items), f"till {i.id}") for i in items]
    out = [pre if sum(r.lower() == o.lower() for o, _ in raw) > 1 else r for r, pre in raw]
    if len({o.lower() for o in out}) < len(out):   # a plain label that equals a prefixed one: prefix them all
        out = [pre for _, pre in raw]
    assert len(set(out)) == len(out), out
    return out


def reserved(items, links):
    """Till item ids that existing links already hold, resolved as mapper.match resolves them (stored cloverId first, else the one till item
    with the link's SKU), so a recreated till item (new id, same SKU) stays held by its old link and is never offered or linked again."""
    by_id, by_sku, held = {i.id for i in items}, {}, set()
    for i in items:
        if i.sku:
            by_sku.setdefault(i.sku.casefold(), []).append(i.id)
    for pid in sorted(links):
        v = links[pid]
        if not isinstance(v, dict):
            continue
        same = by_sku.get(str(v.get("sku", "")).casefold(), [])
        if v.get("cloverId") in by_id and v["cloverId"] not in held:
            held.add(v["cloverId"])
        elif len(same) == 1 and same[0] not in held:
            held.add(same[0])
    return held


def _checked(content, links):
    """Refuse a malformed catalog or link table by one fixed name, before anything is read further or written (no value is echoed)."""
    products = content.get("products") if isinstance(content, dict) else None
    if not isinstance(links, dict) or not isinstance(products, list) or not all(
            isinstance(p, dict) and isinstance(p.get("id"), str) and isinstance(p.get("name"), str) for p in products):
        raise ValueError("link inputs")
    return products


def suggest(snapshot, content, links):
    """(pairs {product id: link}, clashes, site_only, till_only): the last three list EVERY item left over, never linked. A name on both
    sides with more than one item on either side is a clash and lists all its site products and till items. A name shared by several
    items carries a label unique in its whole group (see _labels); a name with one item stays plain. A malformed catalog or link table
    raises ValueError("link inputs"), so draft() and apply() write nothing."""
    products = _checked(content, links)
    taken = reserved(snapshot.items, links)
    site, till = {}, {}
    for p in products:
        if p.get("status") == "active" and p["id"] not in links:
            site.setdefault(norm_name(p["name"]), []).append(p)
    for i in snapshot.items:
        if i.id not in taken:
            till.setdefault(norm_name(i.name), []).append(i)
    pairs, rows = {}, ([], [], [])   # rows: clashes, site only, till only
    for name in sorted(site.keys() | till.keys()):
        ps, items = site.get(name, []), till.get(name, [])
        if len(ps) == 1 == len(items):
            pairs[ps[0]["id"]] = {"cloverId": items[0].id, **({"sku": items[0].sku} if items[0].sku else {})}
            continue
        ids = _labels(ps, items)
        rows[0 if ps and items else 1 if ps else 2].extend(
            f"{n} ({i})" if len(ids) > 1 else n for n, i in zip([p["name"] for p in ps] + [i.name for i in items], ids))
    return (pairs, *rows)


def write(path, value):
    """Atomic private write of a JSON value or text; an existing destination that is not our private regular file is refused."""
    path = Path(path)
    cache._private_dir(path.parent, True)
    if path.exists() or path.is_symlink():
        st = path.lstat()
        if not path.is_file() or path.is_symlink() or st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_nlink != 1:
            raise cache.CacheUnsafe("links")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".link-")   # created 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(value if isinstance(value, str) else json.dumps(value, sort_keys=True))
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def table(state):
    return Path(state) / "clover" / "links.json"


def draft(state, snapshot, content, links):
    """Save the draft (code, the cache's as-of, every pair) and a private list for Mike to read; (code, *suggest())."""
    found = suggest(snapshot, content, links)
    as_of = snapshot.fetched_at.isoformat()
    code = hashlib.sha256(json.dumps([found[0], as_of], sort_keys=True).encode()).hexdigest()[:8]
    write(Path(state) / "clover" / DRAFT, {"code": code, "asOf": as_of, "pairs": found[0]})
    names = {p["id"]: p["name"] for p in content["products"]}
    sections = (("Will link: link all " + code, [f"{names[pid]} ({pid}) = {v['cloverId']}" for pid, v in found[0].items()]),
                ("Same name more than once (name the SKU: link X to SKU)", found[1]), ("On the site, not on the till", found[2]),
                ("On the till, not on the site", found[3]))
    write(Path(state) / "clover" / "reports" / "link-suggest.md", "\n".join(
        f"## {h} ({len(rows)})\n\n" + "".join(f"- {reports._safe(r)}\n" for r in rows) + "\n" for h, rows in sections))
    return (code, *found)


def apply(state, code, snapshot, content, links):
    """('ok', pairs written under this one yes), ('unknown', 0: no waiting draft has that code) or ('stale', 0: the cache changed since
    the draft, or a pair is no longer an exact unlinked match). Anything but 'ok' writes nothing."""
    try:
        d = json.loads(reports._read_regular(Path(state) / "clover" / DRAFT))
        known = d["code"] == code and bool(d["pairs"])
    except Exception:  # noqa: BLE001 - no or unreadable draft: nothing to apply
        known = False
    if not known:
        return "unknown", 0
    now = suggest(snapshot, content, links)[0]
    if d["asOf"] != snapshot.fetched_at.isoformat() or any(now.get(pid) != v for pid, v in d["pairs"].items()):
        return "stale", 0
    write(table(state), {**links, **d["pairs"]})
    (Path(state) / "clover" / DRAFT).unlink()
    return "ok", len(d["pairs"])
