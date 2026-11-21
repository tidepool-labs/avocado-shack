# Hass site output map

| Where | What writes there | Bottom line |
| --- | --- | --- |
| Working `storefront-mockup/` | `sitegen --write` or the content editor using the same renderer | Ten tracked outputs: six HTML, two JS and two JSON. None of the six active tracked HTML files is hand-kept at its output path (`hass/sitegen.py:357–385,671–682`; `hass/editor.py:24–32,211–217,527`; R2 name check). |
| Separate static build | `sitegen --publish` or the live release wrapper using the same publish map | The working tree is not the deploy tree. The build has a publish-only 404, conditional info pages, a reduced community file, and allowlisted source copies (`hass/sitegen.py:466–539`; `hass/publish_live.py:220–231,368–375`). |
| Preview | `Previewer` | Copies the tracked working site and overlays supplied bytes in a disposable directory; writes private screenshots, not source pages (`hass/preview.py:315–344,393–404`). |
| Maker and stock helpers | `maker_site` and `stock_site` | Maker research returns draft data; stock writes private queue artifacts and delegates site changes. Neither has its own page generator (`hass/maker_site.py:486–519,851–882`; `hass/stock_site.py:46–58,85–108,214–237`). |

Source: fresh `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, equal to the requested baseline (2026-11-21, `git rev-parse HEAD origin/main` before branching). `AGENTS.md:3–4` identifies the active tree; `hass/sitegen.py:466–468` excludes the historical archive from publication. This maps paths and writers, not what is deployed or authorized.

## R1. Output paths and inputs

**Working tree / render copy.** Read the four JSON collections under `hass/content/` and validate against the working site (`hass/content_model.py:154–159,803–806`; `hass/sitegen.py:646–649`). The paths below are relative to the repo for `--write` (changed files only), and relative to `DIR` for `--out DIR` (all ten, still with the `storefront-mockup/` prefix). The common disk write is `hass/sitegen.py:436–463`: temporary sibling `.<basename>.<random>.tmp` at line 450, bytes at 453, replacement at 457. The CLI calls it at 668 and 681. `--check` and `--check-publish` compare only; `render` and `publish_files` return maps in memory (`hass/sitegen.py:357–385,502–524,573–621,656–682`).

| Working destination (under `storefront-mockup/`) | Input | Path assignment in `hass/sitegen.py` |
| --- | --- | --- |
| `catalog-products.js` | Active `products.json` records, selected public fields and recorded availability fields; `store.json` supplies the selection check date. | 363; data at 197–209; active filter at `hass/content_model.py:127–128` |
| `producers.js` | `makers.json`, omitting entries with a `hidden` key; wrapped for the browser. | 364; 212–217 |
| `producers.json` | Same visible maker map, serialized as JSON. | 365; 212–221 |
| `community.json` | `hass/content/community.json`: club fields, events, and route ideas with `status == "idea"`. | 366; 224–228 |
| `index.html` | `hass/templates/index.html`, selected `home/*.html` fragments in stored order, and store/freshness/specials/notice/banner/footer slots. Specials consult product records; date-sensitive slots use the generation day unless overridden. | 49–51, 262–287, 303–343, 357–376 |
| `hike/index.html` | `hass/templates/hike/index.html`, shared slots including club intro from community content, hiking nav/footer fragments and shared strip/banner fragments. | 49–51, 303–343, 368–376 |
| `about/index.html` | `hass/templates/info/index.html` + shared hiking nav/footer and strip/banner fragments + `store.json` `/pageAbout`. | 377–384; `hass/content_model.py:657–658` |
| `getting-here/index.html` | Same template and fragments + `/pageGettingHere`. | 377–384; `hass/content_model.py:657–658` |
| `policies/index.html` | Same template and fragments + `/pagePolicies`. | 377–384; `hass/content_model.py:657–658` |
| `faq/index.html` | Same template and fragments + `/pageFaq`. | 377–384; `hass/content_model.py:657–658` |

All four info paths are rendered locally even when not shown; the hidden form is a noindex placeholder with default chrome, and shown pages get footer links (`hass/sitegen.py:340–354,377–384`). Templates, including `hass/templates/home/*.html`, are inputs, not destinations; `template_compat.previous_bytes` reconstructs prior bytes for a draft revision in memory, not on disk (`hass/template_compat.py:21–27`; `hass/editor.py:24–47`).

**Publish tree.** The names below are directly under the separate output root, with no `storefront-mockup/` directory wrapper. `--publish` requires a new or empty destination outside the repo and calls the same actual disk writer at `hass/sitegen.py:539` (bytes/replacement at 453/457). Static inputs are byte copies, not rendered in place (`hass/sitegen.py:520–523`).

| Publish destination(s) | Input / difference from working tree | Path assignment in `hass/sitegen.py` |
| --- | --- | --- |
| `index.html`, `hike/index.html` | Fresh renders, with the publish-only `club-service=none` meta marker. | 469, 487–499, 508–514 |
| `catalog-products.js`, `producers.js` | Fresh renders, with no publish-specific transform. | 469, 508–509 |
| `about/index.html`, `getting-here/index.html`, `policies/index.html`, `faq/index.html` | Same info renders, each copied to the output map only if its store flag `shown` is true. | 510–512 |
| `community.json` | Reduced projection of the working community render (keeps present keys from `clubName`, `events`, `routeIdeas`, `showSamples`). | 478–484, 515 |
| `404.html` | Slot-free `hass/templates/404.html`, rendered with an empty slot map; not taken from the working site. | 470–471, 516–517 |
| `style.css`, `hiking.css`, `trail-explorer.css`, `script.js`, `shop.js`, `community.js`, `trail-explorer.js`, `hiking-preview.json`, `notice.js`, `specials.js`, `banner.js` | Same-name working-site source files, verbatim. | 472–473, 520–523 |
| `assets/logo-header.png`, `assets/favicon.png`, `assets/store.jpg`, `assets/michael.jpg`, `assets/trails/point-buchon.json`, `assets/trails/point-buchon-coast.webp`, `assets/trails/point-buchon-aerial.webp`, `assets/trails/point-buchon-topo.webp` | Same-name working-site assets, verbatim. | 474–476, 520–523 |
| `assets/products/<file>` | Deduplicated image paths from active product `image` fields plus `store.json` `/homeImage/image` if set, copied from the working site; not a directory-wide copy. | 518–523; validated path patterns at `hass/content_model.py:80,102,301,741` |

There is no published `producers.json`. Neither build generates `held-products.json`; `hiking-preview.json` is a copied, separately kept input, not generated club data (`hass/sitegen.py:21–22,362–367,469–478,508–524`). The live release wrapper consumes this same publish map: it writes to `<release-root>/build/<change-id>/out/` and the configured site checkout, and the attended baseline path can write to `<release-root>/build/baseline-preview/` (`hass/publish_live.py:156,220–231,368–375,610–613`).

**Preview and inputs upstream of generation.** These are not additional working-site pages. State and temporary roots below are symbolic.

| Destination or return value | Input and actual writer |
| --- | --- |
| `<preview-tmp>/storefront-mockup/<tracked non-asset path>` | `git ls-files` selects paths; preview copies current worktree bytes via `shutil.copyfile` (`hass/preview.py:315–323`). |
| `<preview-tmp>/storefront-mockup/<supplied non-asset path>` | Overlay of caller-provided path-to-bytes map. Proposal caller passes the editor render; result caller supplies committed generated files (`hass/conversation.py:865–866,2627–2634`; `hass/editor.py:211–221,570–573`). Preview writes at `hass/preview.py:198–217,329`. |
| `<preview-tmp>/storefront-mockup/assets` or `assets/<entry>` and `assets/products/<entry>` | Links to worktree assets by default; with proposed photos, links for the other entries and private files for supplied product photo bytes, not writes through a link (`hass/preview.py:220–247,324–328`). The editor also installs admitted photo bytes separately from render (`hass/editor.py:201–217,527`). |
| `<preview-tmp>/fixture.sqlite3`; `<preview-tmp>/shot.png`, `<preview-tmp>/shot-desktop.png` | The local preview server is pointed at a fixture DB; Chromium writes viewport images (`hass/preview.py:338–364`; `storefront-mockup/community-server.py:9–20`; `hass/screenshot.cjs:242,249`). |
| Caller `out_png`, optional `<out-stem>-desktop.png`, and transient `.<basename>.<random>.tmp` siblings | Admitted viewport bytes, saved privately; chat callers name them `<state>/screenshots/<change-id>-proposal.png` or `<change-id>-result[-<n>].png` before the desktop suffix (`hass/preview.py:180–195,393–404`; `hass/conversation.py:865–866,2633–2634`). |
| No file from `maker_site`; in-memory fetched blocks/cache, proposed story and provenance | Maker page becomes draft data for item intake; `record()` returns a dict, not a site file (`hass/maker_site.py:486–519,851–882`; `hass/skills/item_add.py:824–828,1035`). Maker records stored by the editor can feed both producer outputs above. |
| `<state>/clover/site-stock.lock`, `site-stock.json` in the same folder | Private lock and queue state, not publish data (`hass/stock_site.py:46–64,66–85`). |
| `<state>/clover/reports/site-stock-totals.json`, `stock-reconcile-<day>-<code>.md`, `stock-reconcile-<day>-gaps.md` in the same reports folder | Private queue aggregates, proposal and gap reports from cached stock/link/queue inputs (`hass/stock_site.py:102–108,113–126,135–150,200–202`). Queue JSON and report writes stage a `.stock-<random>` sibling at 34–39. Stock events also call the shared daily audit/correspondence logs (`hass/stock_site.py:87–93`; `hass/audit.py:174–213`; `hass/corrlog.py:4,76–100`). |
| No independent site file from `stock_site` | Sends `product.set_availability` operations to the configured preparer and delegates application to the live editor; the render/publish chain above owns any resulting site files (`hass/stock_site.py:47–49,214–237,299–302`). |

## R2. Hand-kept files and overlapping writers

| Overlap | Classification at the pinned main |
| --- | --- |
| Working renderer ∩ tracked files | All ten are tracked. `index.html`, `hike/index.html`, `about/index.html`, `getting-here/index.html`, `policies/index.html`, `faq/index.html` are generated pages, not hand-kept copies. The one tracked HTML path outside the renderer is historical `archive/commerce-preview/index.html`, not an active target. No `storefront-mockup/404.html` is tracked. See the name inventory and replay below; compare `storefront-mockup/README.md:10`, which names only the original six generated files. |
| Publish copies ∩ hand-kept sources | Every item in the two fixed copy rows and the referenced image pattern in R1 reads its counterpart under `storefront-mockup/`. These are maintained inputs to the site renderer/publisher (images can also be created by the editor), not in-place render targets. The 404 is hand-kept **under `hass/templates/`**, not `storefront-mockup/` (`hass/sitegen.py:469–476,516–523`; `hass/editor.py:211–217,527`). |
| Working renderer ∩ publish map, by relative site name | Always `index.html`, `hike/index.html`, `catalog-products.js`, `producers.js`, `community.json`; also each of the four info paths when shown. The roots differ. Home/hike and community bytes are intentionally transformed; the other shared paths use renderer bytes. `producers.json` stays working-tree-only; `404.html` is publish-only (`hass/sitegen.py:362–384,469–471,508–517`). |
| Same working destination | CLI `--write` and editor apply can both write the same ten paths when changed. They share `sitegen.render`/`write_files`, not competing page implementations. A proposal preview may overwrite its copied counterpart at the same relative path (all ten for the editor render), but only in the preview temp root. Maker and stock do not introduce another direct site writer (`hass/sitegen.py:646–649,671–682`; `hass/editor.py:211–217,527,570–573`; `hass/preview.py:315–330`; R1). |

## R3. Does `PUBLISHING.md` list the same outputs?

No. It describes live release control and recovery, not a second or conflicting output list. The closest wording is “built before local site writes/commit” (`docs/hass/PUBLISHING.md:28–30`), “`baseline`: build/check and show a manifest confirmation” (57–59) and “on the built tree” (86–88). None names the working-tree outputs, publish-only 404, conditional info routes, static copies, or differences in shared names/bytes. The wrapper really uses `sitegen.publish_files` for its built tree (`hass/publish_live.py:220–231`); the durable books in the guide (25–27) are release records, not website output. Its authorization caveat (3–5) is unaffected.

The working-site README is a more direct but incomplete description: “Generated (since H01): catalog-products.js, producers.js, producers.json, community.json, index.html and hike/index.html” (`storefront-mockup/README.md:10`) omits the four local info pages; “the two pages” (28) omits `404.html` and the optionally published info pages. `hass/sitegen.py:13–19` likewise lists only the original six. Compare `hass/sitegen.py:377–384,510–517`. No change to the publishing guide or storefront README was made.

## R4. Ranked gaps and one possible follow-up

1. **Output roots and exceptions are missing from the release guide.** This matters most for interpreting a release manifest: the 404 has no working copy, and a tracked info placeholder need not be released at all (`docs/hass/PUBLISHING.md:25–39,54–61`; `hass/sitegen.py:346–354,377–384,510–517`).
2. **The working-site edit instructions list six outputs when there are ten.** The omission makes info output paths look like places to edit source (`storefront-mockup/README.md:10`; `hass/sitegen.py:13–19,377–384`).
3. **Shared relative names hide different ownership and sometimes different bytes.** Editorial apply and CLI are two entry points to one renderer; preview is an isolated overlay, and publish applies deliberate changes to three common outputs (`hass/editor.py:211–217,527`; `hass/sitegen.py:508–515,671–682`; `hass/preview.py:315–330`). No second independent renderer to remove was found in this scope.

**One possible follow-up (estimate: 60–90 minutes, documentation only, separate authorization):** update `docs/hass/PUBLISHING.md` and `storefront-mockup/README.md` with an edit-here/build-there path table. Offline acceptance: on a pinned checkout, compare the documented working paths to `render()` keys and the publish paths to `publish_files()` keys in memory on the baseline plus a synthetic `shown: true` info record; require the 404 only in publish, the info path in both for the synthetic record, and no `producers.json` in publish. No implementation, wording/policy decision about page content, approval change or change in publication is proposed here.

### Read-only checks and limits

Reproduce the source and tracked-name comparison from the pinned revision:

```text
 git rev-parse origin/main
 git ls-tree -r --name-only origin/main -- storefront-mockup/ hass/templates/
 git ls-tree -r --name-only origin/main -- reports/hass-npp/ reports/audit-1121/
 git grep -nE 'INFO_PAGES|PUBLISH_|write_files|_write_overlay|_write_private' origin/main -- hass/sitegen.py hass/content_model.py hass/preview.py hass/editor.py hass/publish_live.py
 git grep -nEi 'built|manifest|generated|sitegen|the two pages' origin/main -- docs/hass/PUBLISHING.md storefront-mockup/README.md
```

2026-11-21, `python3 -B sitegen-readonly.py avocado-shack` (uncommitted workspace probe): loaded tracked repo content, called `render()` and `publish_files()` with `today=2026-11-21`, compared only names and byte equality to each other and names to `git ls-tree`, and repeated the publish map with four synthetic shown flags/titles in memory. Exit 0. Selected output (site-relative names):

```text
render: about/index.html, catalog-products.js, community.json, faq/index.html, getting-here/index.html, hike/index.html, index.html, policies/index.html, producers.js, producers.json
tracked HTML outside render: archive/commerce-preview/index.html
baseline publish HTML: 404.html, hike/index.html, index.html
baseline publish paths with no working-tree counterpart: 404.html
baseline common render/publish: catalog-products.js, community.json, hike/index.html, index.html, producers.js
baseline same bytes in common: catalog-products.js, producers.js
in-memory all-shown publish HTML: 404.html, about/index.html, faq/index.html, getting-here/index.html, hike/index.html, index.html, policies/index.html
ok (path sets and byte comparisons; no site writes)
```

The cited G-questions file is absent from this checkout (`git ls-tree` above); scope exclusions in the task were kept. Working-tree HTML was inventoried by name only. The probe blocked the disk writer and sockets; no on-disk generation, browser, host configuration, live service, release, or product decision was exercised. The replay checks path selection and common byte differences, not equivalence with a running site or approval to publish.
