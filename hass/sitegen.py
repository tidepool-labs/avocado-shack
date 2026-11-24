"""Generate the private site's content files from hass/content (H01).

    python3 hass/sitegen.py --check          # exit 1 if any generated file differs
    python3 hass/sitegen.py --write          # rewrite changed site files atomically
    python3 hass/sitegen.py --out DIR        # render into DIR (same relative paths)
    python3 hass/sitegen.py --publish DIR    # build the publishable static site into a new/empty DIR (allowlist)
    python3 hass/sitegen.py --check-publish DIR  # read-only: exit 0 only if DIR holds exactly what --publish would write now
                                             # (1 lists missing/changed/extra files; 2 refused DIR); not deploy approval

The publishable site is never the storefront-mockup folder itself: --publish copies only the PUBLISH_* allowlist,
a public community.json and the active catalog's images (see publish_files).

Generated files (do not edit them by hand; edit hass/content or hass/templates):
    storefront-mockup/catalog-products.js   active products only
    storefront-mockup/producers.js          maker profiles (browser)
    storefront-mockup/producers.json        maker profiles (same data, JSON)
    storefront-mockup/community.json        club info, real events, route ideas
    storefront-mockup/index.html            hass/templates/index.html + store info
    storefront-mockup/hike/index.html       hass/templates/hike/index.html + store info

Not generated: held-products.json (historical hold evidence; held status lives in
products.json) and hiking-preview.json (labelled samples, kept separate).
"""

from __future__ import annotations

import argparse
import errno
import html
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote_plus

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass.content_model import (  # noqa: E402
    DEFAULT_CLUB_INTRO, DEFAULT_HEADLINE, DEFAULT_INTRO, DEFAULT_STORY, PRODUCT_OPTIONAL_PUBLIC, PRODUCT_PUBLIC_FIELDS, REPO_ROOT, Content, ContentError,
    checked_on, iso_day, load_and_validate, shop_today, INFO_PAGES,
)
from hass import specials  # noqa: E402
from hass.notice import BANNER_JS, banner_link, NOTICE_JS, slots as notice_slots, stale_paths  # noqa: E402,F401

TEMPLATE_DIR = REPO_ROOT / "hass" / "templates"
SITE_PREFIX = "storefront-mockup/"
TEMPLATES = ("index.html", "hike/index.html")
SLOT_RE = re.compile(r"\{\{([a-zA-Z.]+)\}\}")
# SHOP-1: freshness words come only from Michael's recorded check (store.selection_checked_on), never from the clock.
# The generation date is used only to decide whether that stored date is more than STALE_AFTER_DAYS old.
STALE_AFTER_DAYS = 7
AVAILABILITY_WORDS = {"yes": "Available today", "limited": "Limited", "no": "Sold out"}
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December")


def _day_text(day) -> str:
    """'Friday, October 23' (fixed English names; no locale)."""
    return f"{_DAYS[day.weekday()]}, {_MONTHS[day.month - 1]} {day.day}"


def phone_text(d: str) -> str:
    """'8055550123' -> '(805) 555-0123'."""
    return f"({d[:3]}) {d[3:6]}-{d[6:]}"


def _phone_html(d) -> str:  # only validated digits reach the href; "" without a phone
    return f'<p class="visit-phone"><a href="tel:+1{d}">{phone_text(d)}</a></p>' if d else ""


_HOURS_DAY = "(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
_HOURS_RANGE = f"{_HOURS_DAY}(?: *[-\u2013] *{_HOURS_DAY})?"
_HOURS_TIME = "(1[0-2]|[1-9])(?::([0-5][0-9]))?(am|pm)"
_HOURS_OPEN = re.compile(f"{_HOURS_RANGE} +{_HOURS_TIME} *[-\u2013] *{_HOURS_TIME}")
_HOURS_CLOSED = re.compile(f"Closed +{_HOURS_RANGE}")


def _hours_minutes(hour: str, minute: str | None, half: str) -> int:
    return (int(hour) % 12 + (12 if half == "pm" else 0)) * 60 + int(minute or 0)


def _hours_clause(clause: str) -> dict | None:
    """{day index: {"closed": True} or {"opens", "closes"}} for one clause, None when it does not read."""
    m = _HOURS_CLOSED.fullmatch(clause)
    entry = {"closed": True}
    if not m:
        m = _HOURS_OPEN.fullmatch(clause)
        if not m:
            return None
        opens, closes = _hours_minutes(*m.group(3, 4, 5)), _hours_minutes(*m.group(6, 7, 8))
        if opens >= closes:
            return None
        entry = {"opens": opens, "closes": closes}
    start = _DAYS.index(m.group(1))
    end = _DAYS.index(m.group(2)) if m.group(2) else start
    if m.group(2) and start >= end:  # a range climbs Monday to Sunday: no wrap, no one-day "range"
        return None
    return {day: dict(entry) for day in range(start, end + 1)}


def parse_hours(lines) -> dict:
    """AV1104-03: read the weekly hours lines with one strict rule. Returns {"days": seven Monday-first entries (None = day
    not named, {"closed": True}, or {"opens": minutes, "closes": minutes}) or None, "errors": [{"line": 1-based, "text": line}]}.

    A line is clauses joined by U+00B7: ``<Day>`` or ``<Day>-<Day>`` (ascending; hyphen or en dash) then ``<time>-<time>``
    (hour 1-12, optional :MM, lowercase am/pm, opening before closing), or ``Closed <Day or range>``. One line that does
    not read, or a day named twice anywhere, leaves ``days`` None: never a partial week. Bad input never raises."""
    if not isinstance(lines, list):
        return {"days": None, "errors": []}
    week: dict[int, dict] = {}
    errors = []
    for number, line in enumerate(lines, 1):
        found: dict[int, dict] = {}
        ok = isinstance(line, str)
        for clause in line.split("\u00b7") if ok else ():
            got = _hours_clause(clause.strip())
            if got is None or found.keys() & got.keys() or week.keys() & got.keys():
                ok = False
                break
            found.update(got)
        if ok:
            week.update(found)
        else:
            errors.append({"line": number, "text": line})
    if errors or not week:
        return {"days": None, "errors": errors}
    return {"days": [week.get(day) for day in range(7)], "errors": []}


def _hours_status_html(hours) -> str:
    """The weekly times as data for the page script, never a finished Open/Closed sentence; empty when a line does not read."""
    days = parse_hours(hours)["days"]
    if days is None:
        return ""
    data = json.dumps(days, separators=(",", ":"))
    return f'<p class="micro visit-open-status" hidden data-weekly-hours="{html.escape(data, quote=True)}"></p>'


def _check_state(store: dict, today):
    """(check date or None, stale?) where stale means older than STALE_AFTER_DAYS at generation date ``today``."""
    day = checked_on(store)
    return day, day is not None and (today - day).days > STALE_AFTER_DAYS


def checked_line(store: dict, today) -> str | None:
    """The catalog's freshness sentence, or None before Michael's first recorded check (the page then says nothing)."""
    day, stale = _check_state(store, today)
    if day is None:
        return None
    phone = store.get("phone")  # AV1222-04
    tail = f" (more than a week ago - call {phone_text(phone)} or visit to confirm)" if stale and phone else \
        " (more than a week ago - call or visit to confirm)" if stale else ""
    return f"Selection last checked by Michael on {_day_text(day)}{tail}."


def checked_note(store: dict, today) -> str:
    """The whole freshness paragraph for the index template, or '' when there is no check yet or its day is still to come."""
    line = checked_line(store, today)
    day = checked_on(store)
    if line is None or (day is not None and day > today):  # AV1124C-05: a future check is never a fresh check (as availability_label)
        return ""
    # AV1622-04: shop.js re-ages this paragraph in the browser from its own stored date (and phone); this text is the no-JS fallback.
    phone = store.get("phone")
    attrs = f' data-checked-on="{day.isoformat() if day else ""}"' + (f' data-phone="{phone}"' if phone else "")
    return f'<p class="catalog-note selection-checked"{attrs}>{html.escape(line, quote=False)}</p>'


def _known_word(value) -> bool:
    """True only for a string that is one of the availability words. Checked by type first: a hand-edited list or dict
    value is unhashable and would raise TypeError in a dict membership test instead of counting as not confirmed."""
    return isinstance(value, str) and value in AVAILABILITY_WORDS


def availability_label(product: dict, store: dict, today) -> str | None:
    """Card words for an active product, or None (no check yet, or availability not confirmed). AV1922-02: the word shows
    while its own day is current (availability_state); otherwise "Last confirmed <its own day>"."""
    day, on = checked_on(store), iso_day(product.get("available_on"))
    if day is None or day > today or on is None or on > today or not _known_word(product.get("available")):
        return None
    word = availability_state(product, store, today)
    return AVAILABILITY_WORDS[word] if word else f"Last confirmed {_day_text(on)}"


def availability_state(product: dict, store: dict, today) -> str | None:
    """AV1922-02: the product's word (yes|limited|no) while current, else None. Current: a known word whose own day is not
    before the store's last full check, not after ``today`` and at most STALE_AFTER_DAYS old (shop.js has the same rule)."""
    day, on, word = checked_on(store), iso_day(product.get("available_on")), product.get("available")
    if day is None or on is None or not _known_word(word) or not (day <= on <= today):
        return None
    return word if (today - on).days <= STALE_AFTER_DAYS else None


def _catalog_js(content: Content) -> bytes:
    """AV1622-04: the catalog carries the recorded check dates and raw state, never a finished word or the build date;
    shop.js turns them into words with the same rule as availability_label/checked_line against the visitor's Pacific day."""
    records = []
    for p in content.active_products():
        record = {k: v for k, v in p.items() if k in PRODUCT_PUBLIC_FIELDS + PRODUCT_OPTIONAL_PUBLIC}
        if _known_word(p.get("available")) and iso_day(p.get("available_on")) is not None:
            record["availabilityState"], record["availabilityCheckedOn"] = p["available"], p["available_on"]
        records.append(record)
    day = checked_on(content.store)
    fresh = {"selectionCheckedOn": day.isoformat() if day else None}
    return ("const catalog=" + json.dumps(records, ensure_ascii=False) + ";\n"
            "const catalogFreshness=" + json.dumps(fresh) + ";\n").encode("utf-8")


def _visible_makers(content: Content) -> dict:
    return {k: m for k, m in content.makers.items() if "hidden" not in m}


def _producers_js(content: Content) -> bytes:
    return ("const producers=" + json.dumps(_visible_makers(content)) + ";").encode("utf-8")


def _producers_json(content: Content) -> bytes:
    return json.dumps(_visible_makers(content), indent=2).encode("utf-8")


def _community_json(content: Content) -> bytes:
    data = dict(content.community["club"])
    data["events"] = content.community["events"]
    data["routeIdeas"] = [i for i in content.community["routeIdeas"] if i["status"] == "idea"]  # AV1322-03: not hidden
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


_JSON_LD_ESCAPES = {"<": "\\u003c", ">": "\\u003e", "&": "\\u0026", "\u2028": "\\u2028", "\u2029": "\\u2029"}


_SCHEMA_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _opening_hours_specification(hours) -> list[dict]:
    """AV1922-05: one OpeningHoursSpecification per open day from AV1104-03's parse_hours (Monday first); closed and unnamed
    days left out. Empty (nothing added, never guessed) when any hours line does not read or no day is open."""
    days = parse_hours(hours)["days"]
    return [{"@type": "OpeningHoursSpecification", "dayOfWeek": f"https://schema.org/{_SCHEMA_DAYS[i]}",
             "opens": f"{day['opens'] // 60:02d}:{day['opens'] % 60:02d}",
             "closes": f"{day['closes'] // 60:02d}:{day['closes'] % 60:02d}"}
            for i, day in enumerate(days or ()) if day and "opens" in day]


def local_business_json(store: dict) -> str:
    """schema.org JSON-LD for the home page <script>; no store text can close the script (AV1422-11)."""
    obj = {"@context": "https://schema.org", "@type": "GroceryStore", "name": store["name"],
           "address": {"@type": "PostalAddress", "streetAddress": store["streetAddress"],
                       "addressLocality": store["town"], "addressRegion": "CA", "addressCountry": "US"}}
    if store.get("phone"):
        d = store["phone"]
        obj["telephone"] = f"+1-{d[:3]}-{d[3:6]}-{d[6:]}"
    specs = _opening_hours_specification(store.get("hours"))
    if specs:
        obj["openingHoursSpecification"] = specs
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return "".join(_JSON_LD_ESCAPES.get(c, c) for c in text)


def store_slots(store: dict, today=None) -> dict[str, str]:
    """HTML-escaped values for the store-info slots in the page templates."""
    street, town, name = store["streetAddress"], store["town"], store["name"]
    maps = "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{name} {street} {town}")
    first, second = (html.escape(line, quote=False) for line in store.get("headline") or DEFAULT_HEADLINE)
    return {
        "store.addressLine": html.escape(f"{street}, {town}", quote=False),
        "store.addressShort": html.escape(f"{street} · {town}", quote=False),
        "store.hoursHtml": "<br>".join(html.escape(line, quote=False) for line in store["hours"]),
        "store.hoursStatusHtml": _hours_status_html(store["hours"]),
        "store.phoneHtml": _phone_html(store.get("phone")),
        "store.jsonLd": local_business_json(store),
        "store.mapsUrl": html.escape(maps, quote=True),
        "store.introHtml": html.escape(store.get("intro") or DEFAULT_INTRO, quote=False),
        "store.headlineHtml": f"{first}<br><em>{second}</em>",
        "store.storyHtml": html.escape(store.get("story") or DEFAULT_STORY, quote=False),
        "store.heroImageHtml": _hero_image(store.get("homeImage")),
        **notice_slots(store.get("notice"), (today or shop_today()).isoformat()),
    }


def _hero_image(home) -> str:  # default store.jpg carries its 1600x900 size; an owner photo's size is not stored
    default = ("assets/store.jpg", "Produce and pantry shelves inside Avocado Shack in Morro Bay")
    image, alt = (home["image"], home["imageAlt"]) if home else default
    size = "" if home else ' width="1600" height="900"'
    return f'<img class="hero-image" src="{html.escape(image, quote=True)}" alt="{html.escape(alt, quote=True)}"{size}>'


def render_template(text: str, slots: dict[str, str]) -> str:
    unknown = sorted({m for m in SLOT_RE.findall(text) if m not in slots})
    if unknown:
        raise ContentError([f"template: unknown slot(s) {unknown}"])
    out = SLOT_RE.sub(lambda m: slots[m.group(1)], text)
    if "{{" in out or "}}" in out:
        raise ContentError(["template: unrendered '{{' or '}}' left in output"])
    return out


HIDDEN = " hidden"  # AV1052-03: no inline style (CSP); style.css gives .preview[hidden] its display:none


def front_parts(store, template_dir, rel):
    """AVB-19: the home parts in their saved order and the header/footer links of the shown parts. Template text
    only (it may hold other slots, so it is put in before the slot pass); no owner word is in it."""
    from hass.content_model import default_sections
    home = Path(template_dir) / "home"
    sections = store.get("homeSections", default_sections())
    shown = {r["id"] for r in sections if r["shown"]}
    read = lambda name: (home / (name + ".html")).read_bytes().decode("utf-8")  # noqa: E731
    prefix = "" if rel == "index.html" else "hike-"

    def links(name):
        return re.sub(r'<a href="/?#([^"\s]+)"[^>]*>.*?</a>', lambda m: m[0] if m[1] in shown else "", read(prefix + name))

    return {"home.sections": "".join(read(r["id"]) for r in sections if r["shown"]) if rel == "index.html" else "",
            "home.navHtml": links("nav"), "home.footerLinksHtml": links("footer")}


def front_banner(store, template_dir, rel, day):
    """AVB-19: the top strip. Without a banner it is the shop's default line, byte for byte; with one, the default
    line and the banner line are both rendered, the one for ``day`` visible, and BANNER_JS swaps them in the browser."""
    home = Path(template_dir) / "home"
    read = lambda name: (home / (name + ".html")).read_bytes().decode("utf-8")  # noqa: E731
    banner = store.get("banner")
    live = bool(banner) and banner["start"] <= day.isoformat() <= banner["end"]
    visit = "#visit" if rel == "index.html" else "/#visit"
    strip = render_template(read("strip"), {"front.stripAttrs": (" data-banner-default" + (HIDDEN if live else "")) if banner else "",
                                            "front.visitHref": visit})
    if banner:
        link = banner_link(banner, store)
        strip += render_template(read("banner"), {
            "front.bannerHidden": "" if live else HIDDEN,
            "front.start": html.escape(banner["start"], quote=True), "front.end": html.escape(banner["end"], quote=True),
            "front.text": html.escape(banner["text"], quote=False),
            "front.linkHtml": f'<a href="{html.escape(link, quote=True)}">Find out more ↗</a>' if link else ""})
    return {"front.bannerHtml": strip, "front.bannerScript": BANNER_JS if banner else ""}


def info_footer(store, text):
    links = "".join(f'<a href="/{page}/">{html.escape(value["title"], quote=False)}</a>'
                    for page, (key, _) in INFO_PAGES.items() if (value := store.get(key, {})).get("shown"))
    return text.replace('<button data-policy>', links + '<button data-policy>') if links else text


def info_slots(value):
    if not value.get("shown"):
        return {"info.robots": '<meta name="robots" content="noindex">', "info.title": "Nothing here yet",
                "info.wordsHtml": '<p>Nothing here yet.</p><p><a href="/">Back home</a></p>'}
    esc = lambda text: html.escape(text, quote=False)
    words = (f'<p>{esc(value["intro"])}</p>' if value.get("intro") else "")
    words += "".join(f'<p>{esc(p)}</p>' for p in value.get("paragraphs", []))
    words += "".join(f'<details><summary>{esc(e["q"])}</summary><p>{esc(e["a"])}</p></details>' for e in value.get("entries", []))
    return {"info.robots": "", "info.title": esc(value["title"]), "info.wordsHtml": words}


def render(content: Content, template_dir: Path = TEMPLATE_DIR, today=None, *, notice_today=None,
           specials_today=None, banner_today=None) -> dict[str, bytes]:
    """Return {repo-relative path: bytes} for every generated site file. ``today`` (default: the shop's current date)
    decides selection staleness and notice expiry; ``notice_today`` and ``specials_today`` override only notice and specials expiry for artifact checks."""
    today = today or shop_today()
    files = {
        SITE_PREFIX + "catalog-products.js": _catalog_js(content),
        SITE_PREFIX + "producers.js": _producers_js(content),
        SITE_PREFIX + "producers.json": _producers_json(content),
        SITE_PREFIX + "community.json": _community_json(content),
    }
    slots = {**store_slots(content.store, notice_today or today), "selection.checkedNote": checked_note(content.store, today),
             "club.introHtml": html.escape(content.community["club"].get("intro", DEFAULT_CLUB_INTRO), quote=False),  # AV2152-09
             **specials.slots(content.store, content.products, specials_today or today)}
    for rel in TEMPLATES:
        text = (Path(template_dir) / rel).read_bytes().decode("utf-8")
        for key, value in front_parts(content.store, template_dir, rel).items():
            text = text.replace("{{" + key + "}}", value)
        page = {**slots, **front_banner(content.store, template_dir, rel, banner_today or today)}
        files[SITE_PREFIX + rel] = info_footer(content.store, render_template(text, page)).encode("utf-8")
    for path, (key, _) in INFO_PAGES.items():
        text = (Path(template_dir) / "info/index.html").read_text(encoding="utf-8")
        value = content.store.get(key, {})
        page_store = content.store if value.get("shown") else {}
        for name, part in front_parts(page_store, template_dir, path).items():
            text = text.replace("{{" + name + "}}", part)
        page = {**info_slots(value), **front_banner(page_store, template_dir, path, banner_today or today)}
        files[SITE_PREFIX + path + "/index.html"] = info_footer(page_store, render_template(text, page)).encode("utf-8")
    return files


def _linked(root: Path, rel: str) -> bool:
    """True when the generated file or a folder between root and it is a symlink (root itself may be a link)."""
    parts = Path(rel).parts
    return any(os.path.islink(Path(root, *parts[:i])) for i in range(1, len(parts) + 1))


def diff_paths(files: dict[str, bytes], root: Path) -> list[str]:
    """Generated paths that are symlinked (file or folder below root), missing, not regular files, or differ in bytes.
    A symlinked path is never read, so --check agrees with --write, which refuses it."""
    changed = []
    for rel, data in files.items():
        target = Path(root) / rel
        if _linked(root, rel) or not target.is_file() or _differs(target, data):
            changed.append(rel)
    return changed


def _differs(target: Path, data: bytes) -> bool:
    """Compare a regular file with expected bytes, reading at most len(data) + 1 bytes (extra byte = drift)."""
    with target.open("rb") as handle:
        return handle.read(len(data) + 1) != data



def _check_folders(root: Path, rel: str) -> None:
    """Refuse an absolute/escaping key, a symlinked folder or an existing non-directory folder below root
    (root itself may be a link). Metadata only: a special file is never opened. Missing folders are allowed."""
    key = Path(rel)
    parts = key.parts
    if key.is_absolute() or key.drive or not parts or ".." in parts:
        raise ValueError("generated path escapes root")
    for i in range(1, len(parts)):
        parent = Path(root, *parts[:i])
        if os.path.islink(parent):
            raise OSError(errno.ELOOP, "generated folder is a symlink")
        if os.path.lexists(parent) and not parent.is_dir():
            raise NotADirectoryError(errno.ENOTDIR, "generated folder is not a directory")


def _check_target(root: Path, rel: str) -> None:
    """Refuse a generated target that is a symlink (even dangling) or an existing non-regular file."""
    p = Path(root) / rel
    if os.path.islink(p):
        raise OSError(errno.ELOOP, "generated target is a symlink")
    if os.path.lexists(p) and not p.is_file():
        raise OSError(errno.EISDIR if p.is_dir() else errno.EINVAL, "generated target is not a regular file")


def write_files(files: dict[str, bytes], root: Path, only: list[str] | None = None) -> list[str]:
    """Atomically replace each (changed) file under root; return written paths.
    Every target is checked before any file is replaced; a refused target leaves all files untouched."""
    written = []
    selected = [(rel, data) for rel, data in files.items() if only is None or rel in only]
    for rel, _ in selected:
        _check_folders(Path(root), rel)
        _check_target(Path(root), rel)
    for rel, data in selected:
        target = Path(root) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = target.stat().st_mode & 0o777 if target.exists() else 0o644
        if os.path.islink(target):
            raise OSError(errno.ELOOP, "generated target is a symlink")
        fd, tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp, mode)
            os.replace(tmp, target)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        written.append(rel)
    return written


# AVO-LAUNCH-1: the publishable site is an allowlist, never the working folder. storefront-mockup/ also holds the
# local server, QA scripts and screenshots, research logs with third-party contact details, hold notes and the
# archived commerce preview; none of that is copied. Everything published is listed here or derived from content.
PUBLISH_GENERATED = ("index.html", "hike/index.html", "catalog-products.js", "producers.js")
# Slot-free pages rendered only for the published site (never by render(): the editor and --check pin its output).
PUBLISH_PAGES = ("404.html",)
PUBLISH_STATIC = ("style.css", "hiking.css", "trail-explorer.css", "script.js", "shop.js", "community.js",
                  "trail-explorer.js", "hiking-preview.json", "notice.js", "specials.js", "banner.js")
PUBLISH_ASSETS = ("assets/logo-header.png", "assets/favicon.png", "assets/store.jpg", "assets/michael.jpg", "assets/trails/point-buchon.json",
                  "assets/trails/point-buchon-coast.webp", "assets/trails/point-buchon-aerial.webp",
                  "assets/trails/point-buchon-topo.webp")
# The public club file carries what the page reads (and what /api/community returns); not the proposed sender address.
PUBLIC_COMMUNITY_KEYS = ("clubName", "events", "routeIdeas", "showSamples")  # showSamples only when false


def _public_community_json(content: Content) -> bytes:
    data = json.loads(_community_json(content))
    return (json.dumps({k: data[k] for k in PUBLIC_COMMUNITY_KEYS if k in data}, indent=2, ensure_ascii=False)
            + "\n").encode("utf-8")


# AV-08: the published site is plain static files with no club service behind /api/community, so a page that asked for it
# would log a 404 in the visitor's console on every load. The published club pages say so up front and community.js
# (which reads this marker) goes straight to the published community.json. The source pages and the local server, which
# do answer /api/community, never carry it; a host that adds the service drops this marker.
NO_CLUB_SERVICE_MARKER = '<meta name="club-service" content="none">'
NO_CLUB_SERVICE_PAGES = ("index.html", "hike/index.html")


def _mark_no_club_service(rel: str, page: bytes) -> bytes:
    text, anchor = page.decode("utf-8"), '<meta charset="utf-8">'
    if text.count(anchor) != 1 or NO_CLUB_SERVICE_MARKER in text:
        raise ValueError(f"publish: cannot place the club-service marker in {rel}")
    return text.replace(anchor, anchor + NO_CLUB_SERVICE_MARKER).encode("utf-8")


def publish_files(content: Content, repo: Path, template_dir: Path | None = None, today=None) -> dict[str, bytes]:
    """{site-relative path: bytes} for the publishable static site: generated pages and scripts, the allowlisted
    static files, a public community.json, and only the assets the pages and the active catalog use (the home
    photo, when store.homeImage is set, is one of them: it is rendered into index.html)."""
    repo = Path(repo)
    site = repo / SITE_PREFIX
    rendered = render(content, template_dir or repo / "hass" / "templates", today=today)
    files = {rel: rendered[SITE_PREFIX + rel] for rel in PUBLISH_GENERATED}
    for path, (key, _) in INFO_PAGES.items():
        if content.store.get(key, {}).get("shown"):
            files[path + "/index.html"] = rendered[SITE_PREFIX + path + "/index.html"]
    for rel in NO_CLUB_SERVICE_PAGES:
        files[rel] = _mark_no_club_service(rel, files[rel])
    files["community.json"] = _public_community_json(content)
    for rel in PUBLISH_PAGES:
        files[rel] = render_template((Path(template_dir or repo / "hass" / "templates") / rel).read_bytes().decode("utf-8"), {}).encode("utf-8")
    home = content.store.get("homeImage")
    images = sorted({p["image"] for p in content.active_products()} | ({home["image"]} if home else set()))
    for rel in PUBLISH_STATIC + PUBLISH_ASSETS + tuple(images):
        if _linked(site, rel) or not (site / rel).is_file():
            raise OSError(errno.ENOENT, f"publish source missing or a symlink: {rel}")
        files[rel] = (site / rel).read_bytes()
    return files


def publish(content: Content, repo: Path, out: Path) -> list[str]:
    """Write the publishable site into ``out``, which must be outside the repository and absent or empty, so no stale
    or private file can ride along. Returns the written paths."""
    out_abs = Path(os.path.abspath(out))
    repo_abs = Path(os.path.realpath(repo))
    resolved = Path(os.path.realpath(out_abs))
    if resolved == repo_abs or repo_abs in resolved.parents:
        raise ValueError("publish folder must be outside the repository")
    if os.path.islink(out_abs) or (out_abs.exists() and (not out_abs.is_dir() or any(out_abs.iterdir()))):
        raise OSError(errno.EEXIST, "publish folder must be new or empty")
    files = publish_files(content, repo)
    out_abs.mkdir(parents=True, exist_ok=True)
    return write_files(files, out_abs)


def _check_root(repo: Path, root: Path) -> Path:
    """AV1622-08: the folder to compare must be an existing real directory outside the repository, reached through no
    symlink (the folder itself, dangling links and every parent included). Metadata only; nothing is created."""
    # Walk the path as given, ``..`` included, before any normalisation: collapsing ``link/..`` or ``missing/..`` first
    # would check a different folder than the one named. Each prefix must exist and be no link; lstat raises otherwise.
    given = Path(os.path.join(os.getcwd(), os.fspath(root)))
    for i in range(1, len(given.parts) + 1):
        prefix = Path(*given.parts[:i])
        if os.path.islink(prefix):
            raise OSError(errno.ELOOP, "folder or one of its parents is a symlink")
        os.lstat(prefix)
    top = Path(os.path.abspath(given))  # safe now: every component is a real, existing directory or file, no link
    for found in (top, Path(os.path.realpath(top))):
        for base in (Path(os.path.abspath(repo)), Path(os.path.realpath(repo))):
            if found == base or base in found.parents:
                raise ValueError("folder must be outside the repository")
    if not stat.S_ISDIR(os.lstat(top).st_mode):
        raise NotADirectoryError(errno.ENOTDIR, "folder is not a directory")
    return top


def _same_bytes(path: Path, data: bytes) -> bool:
    """Compare an expected regular file with its bytes. Never follows a link: an entry that turned into a link or
    special file since it was listed is refused (OSError), not read (O_NONBLOCK keeps a FIFO from hanging the open)."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0))
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise OSError(errno.EINVAL, "entry changed type during the check")
        return handle.read(len(data) + 1) == data


def check_publish(files: dict[str, bytes], root: Path) -> tuple[list[str], list[str], list[str]]:
    """Compare ``root`` with the publish_files map without writing: (missing, changed, extra) site-relative paths, each
    sorted. Expected files are exactly the keys, allowed folders their parents; anything else (links, special entries,
    empty or hidden folders, private files) is extra. Links are never followed and only expected regular files are read."""
    dirs = {"/".join(Path(rel).parts[:i]) for rel in files for i in range(1, len(Path(rel).parts))}
    seen, changed, extra = set(), set(), set()

    def visit(rel_dir: str) -> None:
        with os.scandir(Path(root, rel_dir) if rel_dir else root) as entries:
            found = sorted(entries, key=lambda e: e.name)
        for entry in found:
            rel = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
            mode = entry.stat(follow_symlinks=False).st_mode
            if rel in files:
                seen.add(rel)
                if not stat.S_ISREG(mode) or not _same_bytes(Path(root, rel), files[rel]):
                    changed.add(rel)
            elif rel in dirs and not stat.S_ISDIR(mode):
                changed.add(rel)
            elif rel not in dirs:
                extra.add(rel)
            if stat.S_ISDIR(mode):  # a real folder only; a link has no S_ISDIR here and is never entered
                visit(rel)

    visit("")
    return sorted(set(files) - seen), sorted(changed), sorted(extra)


def _check_published(content: Content, repo: Path, root: Path) -> int:
    """Exit 0 when ``root`` holds exactly what --publish would write now, 1 listing the differences, 2 when the folder
    is refused or cannot be read. Never writes. Paths are JSON-quoted so a newline in a name cannot forge a line; no
    file content is printed. Concurrent changes are unsupported: check a quiescent copy."""
    try:
        top = _check_root(repo, root)
        files = publish_files(content, repo)
        groups = check_publish(files, top)
    except (OSError, ValueError) as exc:
        print(f"sitegen: check-publish refused: {getattr(exc, 'strerror', None) or exc}", file=sys.stderr)
        return 2
    if not any(groups):
        print(f"ok: {len(files)} published files match current content")
        return 0
    print("published folder differs from current content (not a deploy approval; nothing was changed):")
    for label, paths in zip(("missing", "changed", "extra"), groups):
        if paths:
            print(f"{label} ({len(paths)}):")
            for rel in paths:
                print("  " + json.dumps(rel))
    return 1


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except (OSError, ValueError) as exc:  # ContentError is handled inside _main first
        print(f"sitegen: io error: {type(exc).__name__}", file=sys.stderr)
        return 2


def _main(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="fail if generated files differ from the repo")
    mode.add_argument("--write", action="store_true", help="rewrite generated files that differ")
    mode.add_argument("--out", type=Path, help="render all generated files into this directory")
    mode.add_argument("--publish", type=Path, metavar="DIR",
                      help="build the publishable static site (allowlist only) into a new or empty DIR outside the repo")
    mode.add_argument("--check-publish", type=Path, metavar="DIR",
                      help="read-only: exit 0 only if existing DIR (outside the repo, not a symlink) holds exactly what --publish "
                           "would write now; 1 lists missing/changed/extra files; 2 refused. Check a quiescent copy")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help="repository root (default: this checkout)")
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    try:
        content = load_and_validate(repo / "hass" / "content", repo / "storefront-mockup")
        files = render(content, repo / "hass" / "templates")
    except ContentError as exc:
        print("content invalid:", file=sys.stderr)
        for problem in exc.problems:
            print("  " + problem, file=sys.stderr)
        return 2

    if args.check_publish is not None:
        return _check_published(content, repo, args.check_publish)
    if args.publish is not None:
        try:
            written = publish(content, repo, args.publish)
        except (OSError, ValueError) as exc:
            print(f"sitegen: publish refused: {getattr(exc, 'strerror', None) or exc}", file=sys.stderr)
            return 2
        print(f"published {len(written)} files into {args.publish} "
              f"({len(content.active_products())} active products)")
        return 0
    if args.out is not None:
        written = write_files(files, args.out)
        print(f"rendered {len(written)} files into {args.out}")
        return 0
    changed = stale_paths(content, repo) if args.check else diff_paths(files, repo)
    if args.check:
        if changed:
            print("generated files out of date (run python3 hass/sitegen.py --write):")
            for rel in changed:
                print("  " + rel + (" (symlink)" if _linked(repo, rel) else ""))
            return 1
        print(f"ok: {len(files)} generated files match hass/content "
              f"({len(content.active_products())} active products, {len(content.makers)} makers)")
        return 0
    written = write_files(files, repo, only=changed)
    print(f"wrote {len(written)} changed files" + "".join("\n  " + rel for rel in written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
