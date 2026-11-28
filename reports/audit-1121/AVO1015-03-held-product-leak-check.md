# Held-product leak check — 2026-11-21

| Held product | Visitor can find a card or open its photo on the published catalog? (estimate) | What still exists on main | Direct file access in the private sandbox? (estimate) |
|---|---|---|---|
| `photo-product-040` — Raw milk white cheddar | **No** | Held record, older extraction row under the name “Sierra Nevada cheese,” and the WebP itself (R2–R3). | **Yes** — raw hold and extraction data and the WebP; **no** catalog card. |
| `photo-product-133` — Raw Milk Goat Cheddar | **No** | Held record and older completion row; WebP reference but no tracked WebP (R2–R3). | **Yes** — raw hold and completion data; **no** catalog card or tracked photo. |

Checked offline at `origin/main` **`37feae1dc5efa6968f90d17a1eda6daed29afd4a`**. “Published” means the allowlisted build, not the source folder or public Git repository. The live release, caches, private photo library and installed sandbox were not checked. The sandbox estimates assume a visitor already has access to a stock sandbox serving this checkout (`AGENTS.md:3–7`; `storefront-mockup/community-server.py:7,52–58,67–68`).

## R1. What the hold records

`storefront-mockup/held-products.json:2` — reason: “Manufacturer site displays Graziers raw-milk cheese recall; hold pending exact product/lot verification”. Line 3 — source: “https://sierranevadacheese.com/”. This is a quote of the recorded concern, not a current check of the manufacturer's site.

| Recorded name | ID | Source photo | Catalog image (AI visualization) | Evidence in `storefront-mockup/held-products.json` |
|---|---|---|---|---|
| Raw milk white cheddar | `photo-product-040` | `IMG_9722.jpg` | `assets/products/photo-product-040.webp` | lines 6, 9, 17–21, 24 (`/products/0`) |
| Raw Milk Goat Cheddar | `photo-product-133` | `IMG_9722.jpg` | `assets/products/photo-product-133.webp` | lines 29–30, 36–41, 43 (`/products/1`) |

## R2. Where the products or filenames appear

| Reader or serving path | What it reads | Held products reachable? (runtime estimate) |
|---|---|---|
| Catalog home `/` | `storefront-mockup/index.html:32` and `hass/templates/index.html:20` load `catalog-products.js`, `producers.js`, `script.js`, `shop.js` and `community.js`. `shop.js:2,11,19–24,76–92` draws/searches cards from `catalog`, not the older JSON files. `hass/sitegen.py:199–209` generates `catalog` from `active_products()`; `hass/content_model.py:127–128,154–179` reads Hass content and selects only `active`. | **No** for both, including direct `?item=` links: an ID missing from `catalog` yields a generic notice, not a product (`shop.js:136–146`). |
| Hiking, info and 404 pages | Hiking loads shared UI, trail and community scripts (`storefront-mockup/hike/index.html:29`; `community.js:139–154` uses the community API/JSON). Info pages and 404 load shared `script.js`, not catalog data (`hass/templates/info/index.html:19`, `hass/templates/404.html:23`; checked-in info pages under `about/`, `faq/`, `getting-here/`, `policies/` each at `index.html:19`). | **No** for both. No literal held ID, exact name or photo filename in the storefront HTML or Hass page templates. |
| Allowlisted static files | `hass/sitegen.py:466–476,502–524` ships generated pages/scripts, selected static files, public community JSON and only the active catalog's product images plus the home image. Hass's live builder calls the same `publish_files` (`hass/publish_live.py:223–231`). | **No** for both: neither raw hold/legacy JSON nor either held WebP is in the checked build. |
| Private sandbox raw paths | Static GETs fall through to the handler rooted in `storefront-mockup/` (`community-server.py:7,52–58,67–68`). This is not the allowlisted build. | **Yes**, both records via `/held-products.json`, plus `040` via `/catalog.json` and its WebP path, and `133` via `/completion-new-products.json`. These are file reads, not product cards. |
| Archived commerce preview | `storefront-mockup/archive/commerce-preview/index.html:9` references its own relative `catalog.js`; none is tracked alongside it (tree check below). | **No** held listing in the checked archive; not copied to the publish build (`hass/sitegen.py:466–476`). |

### Storefront and Hass data matches

`040` and `133` below denote the two exact IDs above. “Shared JPG” is a match on `IMG_9722.jpg` only; it does not identify a held product. Path pointers are relative to the named JSON document (for `catalog.js`, to the array assigned to `catalog`). Files under `storefront-mockup/` can be read directly in the private sandbox estimate above, but none of the matching files here is loaded by the current catalog page or shipped in the publish build. Hass data is outside the sandbox root.

| File | `040` match | `133` match | Shared JPG matches |
|---|---|---|---|
| `storefront-mockup/held-products.json` | `/products/0`: ID, name, WebP | `/products/1`: ID, name, WebP | Both rows (R1) |
| `storefront-mockup/catalog.json` | `/39`: ID, older name “Sierra Nevada cheese” (`:707–723`) | None by ID, name or WebP | `/36`, `/37`, `/38`, `/39` (`:656–722`); all point to the source filename, not either WebP |
| `storefront-mockup/catalog-extraction.csv` | Line 41: ID, older name “Sierra Nevada cheese” | None by ID, name or WebP | Lines 38–41 |
| `storefront-mockup/catalog.js` | None by ID, name or WebP | None by ID, name or WebP | Line 1: `/34`, `/35`, `/36`, `/126`, `/127`, `/128` |
| `storefront-mockup/shop-data.json` | None by ID, name or WebP | None by ID, name or WebP | `/products/34`, `/products/35`, `/products/36`, `/products/126`, `/products/127`, `/products/128` (`:895–956,3188–3239`) |
| `storefront-mockup/new-products.json` | None | None | None |
| `storefront-mockup/completion-new-products.json` | None by ID, name or WebP | `/28`: ID, name, WebP (`:535–549`) | `/25`, `/26`, `/27`, `/28` (`:485–549`) |
| `storefront-mockup/image-generation-log.json` | Lines 245, 680–683: ID/name | None by ID, name or WebP | Line 681, with `040` |
| `storefront-mockup/completion-image-log.json` | None by ID, name or WebP | Lines 291–295: ID/name | Lines 230, 239, 248, 293 |
| `hass/content/products.json` | `/products/170`: ID, name, WebP, `status: held` (`:1875–1885`) | `/products/171`: ID, name, WebP, `status: held` (`:1889–1899`) | `/products/171/hold/evidence` |
| `hass/content/migration-baseline.json` | Line 249: ID | Line 250: ID | None |
| `storefront-mockup/catalog-products.js` and storefront HTML (including archived HTML) | None | None | None |

### Other tracked text matches

These are intake evidence, reports, documentation, code examples or tests, not visitor catalog data. All are outside the sandbox document root and absent from the publish build (`community-server.py:7,52–58`; `hass/sitegen.py:466–476,502–524`). The Git repository is a separate surface: a reader of the repository can see tracked matches regardless of the site build.

| File | `040` lines (ID/name/WebP) | `133` lines (ID/name/WebP) | Shared JPG lines |
|---|---|---|---|
| `inventory-intake/manifest.json` | — | — | 275 (`/15/photo`) |
| `inventory-intake/review.html` (intake review page, not storefront) | — | — | 1 |
| `docs/hass/skills/item_picture.md` | 34 | — | — |
| `hass/README.md` | 69 | — | — |
| `hass/skills/scaffold.py` | 50 | — | — |
| `reports/catalog-shelves-2026-11.md` | 9 | 9 | — |
| `reports/hass/catalog-gaps.json` | 3684–3685 | 3664–3665 | — |
| `reports/hass/itemstd-1/picture-measurements.json` | 50, 52 | — | — |
| `reports/held-cheese-recall-2026-11.md` | 7, 70, 98 | 7, 77, 98 | 80 |
| `reports/product-description-claims-2026-11.md` | 33 | 33 | 231, 241, 251 |
| `workspace/candidates/AUDINV-OLD-63/BASES.json` | 1 | — | — |

| File under `hass/tests/` | `040` lines | `133` lines |
|---|---|---|
| `fixtures/interpreter-eval-replies.jsonl` | 9 | — |
| `fixtures/interpreter-eval.jsonl` | 8 | — |
| `fixtures/skills-acceptance/messages.jsonl` | — | 76 |
| `fixtures/skills/item_picture/item.picture.jsonl` | 9 | — |
| `fixtures/skills/items/item.edit.jsonl` | 16 | — |
| `fixtures/skills/items/item.hide.jsonl` | 12 | — |
| `fixtures/skills/items/item.restore.jsonl` | 8 | — |
| `fixtures/skills/restock/stock.restock.jsonl` | 13 | — |
| `fixtures/skills/stock/stock.checked.jsonl` | 12 | — |
| `fixtures/skills/stock/stock.clear.jsonl` | 6 | — |
| `fixtures/skills/stock/stock.set.jsonl` | 10 | — |
| `test_catalog_dupes.py` | 38–39, 70–72 | — |
| `test_catalog_ops.py` | 127, 190–191 | — |
| `test_content.py` | 110, 280, 288, 314, 318 | 111, 280, 288 |
| `test_cost_by_name.py` | — | 14, 64–66 |
| `test_costs_command.py` | 18, 134 | — |
| `test_find.py` | 99–100 | — |
| `test_held_command.py` | 23–24, 39, 91, 175 | 25–26, 92 |
| `test_item_picture_home_rejection.py` | 16 | — |
| `test_item_picture_unicode_choice.py` | 17 | — |
| `test_listing_by_name.py` | — | 47–48 |
| `test_maker_hide_products.py` | 26 | — |
| `test_maker_product_batch.py` | 164 | — |
| `test_memory_alias.py` | 74 | — |
| `test_post_by_name.py` | 121 | 119 |
| `test_product_alt.py` | 11 | — |
| `test_purchase_cost.py` | 107–109 | — |
| `test_shelf_check_except.py` | 101 | — |
| `test_skills_item_picture.py` | 31, 398 | — |
| `test_skills_items.py` | 142, 179–180, 246–247, 257, 260, 301, 306, 312, 462, 541–542 | — |
| `test_skills_restock.py` | 26, 105, 254 | — |
| `test_skills_stock.py` | 27, 533 | — |
| `test_stock_list_references.py` | 19 | — |

### Reproduce the checks

From the repo root, set `base=37feae1dc5efa6968f90d17a1eda6daed29afd4a`. The text scan prints only the matched term and its location, not the containing line. The file-tree checks also cover names that never appear in text.

```sh
git diff --name-status 1f8510907cb2989bb50391fde45d6211e4735879.."$base"
git grep -in -w -o -E 'photo-product-(040|133)(\.webp)?|raw milk (white|goat) cheddar|IMG_9722\.jpg' "$base" -- ':!*.env*' ':!*credential*' ':!*token*'
git ls-tree -r --name-only "$base" | rg -i '(^|/)(IMG_9722\.jpg|photo-product-(040|133)\.webp|G-QUESTIONS\.md)$'
```

For just the three checked asset paths and the older preview tree:

```sh
git ls-tree -r "$base" -- storefront-mockup/assets/products/photo-product-040.webp storefront-mockup/assets/products/photo-product-133.webp storefront-mockup/assets/products/IMG_9722.jpg
git ls-tree -r --name-only "$base" -- storefront-mockup/archive/commerce-preview
```

2026-11-21 offline result: the actual `hass.sitegen.publish_files` called in memory with `load_and_validate` on this checkout returned **195 paths**, including `index.html`, `hike/index.html`, `404.html`, 170 catalog rows and a control image (`assets/products/photo-product-041.webp`). There were **zero** held-term matches in output pathnames or HTML/JSON/JS/CSS and **zero** raw legacy/hold datasets listed in the first data table. The working-folder `catalog-products.js` also had zero matches. No files were published. The baseline diff listed only three added Hass audit scripts and their three tests, with no changes to the cited storefront inputs or publishing path. The card's `reports/hass-npp/G-QUESTIONS.md` is not tracked on this main; none of the card's reserved topics or runtime surfaces was inspected.

## R3. Files and other records using them

| Filename | Tracked under `storefront-mockup/assets/products/`? | Other product records pointing to it? |
|---|---|---|
| `IMG_9722.jpg` | **No.** No tracked file with this basename anywhere in the checked tree. | **Yes.** Besides the two held products, `photo-product-037`, `038`, `039`, `130`, `131`, `132` (same ID prefix) refer to it as source evidence. See `catalog.json` `/36`–`/38`, `catalog.js` `/34`–`/36` and `/126`–`/128`, `shop-data.json` `/products/34`–`/products/36` and `/products/126`–`/products/128`, and `completion-new-products.json` `/25`–`/27`. `catalog-extraction.csv:38–40` has the three early candidates too. These are filename references, not evidence that either held product or the original photo is displayed. |
| `photo-product-040.webp` | **Yes**, tracked regular file (tree command above). | **No** other product record refers to it. References are to `040` itself, measurement/fixture evidence or a source pin (R2). |
| `photo-product-133.webp` | **No.** No tracked file with this basename anywhere in the checked tree. | **No** other product record refers to it. Its retained completion and hold records, Hass row and test fixture all refer to `133` itself (R2). |

## R4. Differences from the earlier report

- The earlier report compared product identity to recall notices and did not inspect storefront publication (`reports/held-cheese-recall-2026-11.md:5–8,66–82,92–98`). The new evidence is the checked split between no hits in the publish build and retained records plus one directly servable WebP in a checkout-backed private sandbox (R2–R3).
- The earlier report discussed the source photograph and goat-cheddar artwork (`:80`), not file presence or reuse. This check finds the original JPG referenced by six other candidate records but absent from Git, the `040` WebP present, and the `133` WebP absent (R3). No physical-label or recall finding is updated.
- **Owner decision:** whether to keep or retire retained sandbox evidence or artwork, and whether either product may ever be removed or restored after review of the manufacturer concern (`AGENTS.md:12`; earlier report `:98`). No decision made. **No buildable follow-up is needed for this report**; it does not request any change to the sandbox, catalog, data, hold or publish path.
