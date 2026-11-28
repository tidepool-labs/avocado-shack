# AVO1015-02 — Storefront asset reference coverage

| Result | Count |
| --- | ---: |
| Tracked files under `storefront-mockup/assets/` | 197 |
| Tracked files named by at least one in-scope local reference | 190 |
| Tracked files with no in-scope local reference | 7 (10,870,338 bytes) |
| Dangling local references | 98 occurrences, naming 31 distinct missing paths |

Offline audit, 2026-11-21 UTC, at `37feae1dc5efa6968f90d17a1eda6daed29afd4a` (`origin/main` at clone time). The in-scope source and asset paths matched the card's baseline. This is a source inventory, not a deployed-site check or a removal list.

## R1. How the counts were made

A scratch Python script read Git blobs at the pinned commit. It scanned **46 files**: 21 top-level storefront JSON files (including historical catalogs and logs), five `hass/content/*.json` files, the trail JSON under `assets/trails/`, six HTML pages (home, about, FAQ, getting here, hike, policies), all three top-level storefront CSS files, and ten top-level storefront `.js` files. It excluded `commerce/` and `storefront-mockup/archive/` (`AGENTS.md:3–5`), and treated the optimizer as QA evidence only.

The script walked JSON string values with zero-based JSON pointers and scanned HTML, CSS and JS text by line. It looked for local `assets/…` paths, including `/assets/…`, `./assets/…` and repo-relative `storefront-mockup/assets/…`. It stripped query and fragment, decoded URL escapes, resolved dot segments and compared the full case-sensitive path against the Git inventory. Relative HTML references were resolved from the page directory; the other relative paths in scope use the storefront root. External URLs, embedded data and old machine-local paths in image logs were not storefront references. A bare source-photo basename is not a URL into `assets/`. The script expanded the one asset path assembled by the trail layer switch: `aerial` and `topo` come from `storefront-mockup/trail-explorer.js:29`, and are substituted at line 118. Its JSON fetch (`:20`) counts because the target is itself a tracked asset.

Read-only result on 2026-11-21: `inventory 197 referenced 190 unreferenced 7 dangling paths 31 dangling occurrences 98`. The inventory splits into 182 product files, 11 directly under `assets/`, and four trail files; 185 are WebP. To reproduce the inventory and review path candidates at the audited revision (the text search is a cross-check, not the JSON parser or template expansion):

```sh
base=37feae1dc5efa6968f90d17a1eda6daed29afd4a
git ls-tree -rl "$base" -- storefront-mockup/assets
git grep -n -o -E 'assets/[[:alnum:]_.%+/-]+' "$base" -- \
  ':(glob)storefront-mockup/*.json' ':(glob)hass/content/*.json' \
  ':(glob)storefront-mockup/*.html' ':(glob)storefront-mockup/*/index.html' \
  ':(glob)storefront-mockup/*.css' ':(glob)storefront-mockup/*.js' \
  storefront-mockup/assets/trails/point-buchon.json
git grep -n -o -E 'data-map-layer="[^"]+"|point-buchon-\$\{[^}]+\}\.webp' "$base" -- storefront-mockup/trail-explorer.js
```

A source reference is not necessarily a page request. For example, the 11 earlier box and merchandise images are named in `storefront-mockup/catalog.js:2–3` and `shop-data.json` (`/boxes`, `/merch`), so they count as referenced even though the current page does not use them (`storefront-mockup/README.md:12–17`). The static export is narrower than the checkout: `hass/sitegen.py:474–476,518–523` copies an asset allowlist plus active product and configured home photos, not the entire asset tree. The scan did not run a browser, start a server, build the export or contact a site.

## R2. Files with no in-scope local reference

Bytes are Git blob sizes from `git ls-tree -rl` above, not allocated disk space or measured network savings. Format is by extension.

| Path | Bytes | Format |
| --- | ---: | --- |
| `storefront-mockup/assets/avocados.jpg` | 2,309,890 | JPEG |
| `storefront-mockup/assets/berries.jpg` | 2,464,670 | JPEG |
| `storefront-mockup/assets/logo.png` | 222,924 | PNG |
| `storefront-mockup/assets/pantry.jpg` | 2,556,164 | JPEG |
| `storefront-mockup/assets/point-buchon-trail.svg` | 3,377 | SVG |
| `storefront-mockup/assets/share.jpg` | 174,257 | JPEG |
| `storefront-mockup/assets/vegetables.jpg` | 3,139,056 | JPEG |
| **Total** | **10,870,338** | |

In particular, `logo.png` is documented as master art, not the header or favicon served by the pages (`storefront-mockup/README.md:77–79`); it also appears in machine-local provenance entries (`completion-image-log.json:626`, `image-generation-log.json:574`). The old trail SVG is documented as retained but no longer displayed (`storefront-mockup/README.md:45`). Neither finding is a removal recommendation.

## R3. References with no tracked target

The first 30 rows are all 95 `/image` values in the historical `storefront-mockup/catalog.json`, which is not loaded by the current catalog page (`storefront-mockup/README.md:12–17`, `storefront-mockup/index.html:32`). Each brace list below abbreviates exact pointers: `/{1,2}/image` means `/1/image` and `/2/image`; ranges are inclusive. “None” means no exact or recognizable nearby asset basename or stem, not merely that other JPEGs are present. The numeric neighbors in the last row are name matches only, not replacement images.

| Referring file and JSON pointer(s) | Path as named | Nearest existing file by name |
| --- | --- | --- |
| `storefront-mockup/catalog.json` `/{1–4}/image` | `assets/catalog/IMG_9707.jpg` | None |
| `storefront-mockup/catalog.json` `/5/image` | `assets/catalog/IMG_9708.jpg` | None |
| `storefront-mockup/catalog.json` `/{6,82–86,91–94}/image` | `assets/catalog/IMG_9709.jpg` | None |
| `storefront-mockup/catalog.json` `/{7–11}/image` | `assets/catalog/IMG_9710.jpg` | None |
| `storefront-mockup/catalog.json` `/12/image` | `assets/catalog/IMG_9711.jpg` | None |
| `storefront-mockup/catalog.json` `/13/image` | `assets/catalog/IMG_9712.jpg` | None |
| `storefront-mockup/catalog.json` `/14/image` | `assets/catalog/IMG_9713.jpg` | None |
| `storefront-mockup/catalog.json` `/{0,15}/image` | `assets/catalog/IMG_9714.jpg` | None |
| `storefront-mockup/catalog.json` `/{16,17}/image` | `assets/catalog/IMG_9715.jpg` | None |
| `storefront-mockup/catalog.json` `/{18,19}/image` | `assets/catalog/IMG_9716.jpg` | None |
| `storefront-mockup/catalog.json` `/{20–23}/image` | `assets/catalog/IMG_9717.jpg` | None |
| `storefront-mockup/catalog.json` `/{24–27}/image` | `assets/catalog/IMG_9719.jpg` | None |
| `storefront-mockup/catalog.json` `/{28–31}/image` | `assets/catalog/IMG_9720.jpg` | None |
| `storefront-mockup/catalog.json` `/{32–35}/image` | `assets/catalog/IMG_9721.jpg` | None |
| `storefront-mockup/catalog.json` `/{36–39}/image` | `assets/catalog/IMG_9722.jpg` | None |
| `storefront-mockup/catalog.json` `/{40,41,87–90}/image` | `assets/catalog/IMG_9723.jpg` | None |
| `storefront-mockup/catalog.json` `/{42,43}/image` | `assets/catalog/IMG_9724.jpg` | None |
| `storefront-mockup/catalog.json` `/{44–46}/image` | `assets/catalog/IMG_9725.jpg` | None |
| `storefront-mockup/catalog.json` `/{47–50}/image` | `assets/catalog/IMG_9726.jpg` | None |
| `storefront-mockup/catalog.json` `/{51,52}/image` | `assets/catalog/IMG_9727.jpg` | None |
| `storefront-mockup/catalog.json` `/{53,54}/image` | `assets/catalog/IMG_9728.jpg` | None |
| `storefront-mockup/catalog.json` `/{55–58}/image` | `assets/catalog/IMG_9729.jpg` | None |
| `storefront-mockup/catalog.json` `/{59–64}/image` | `assets/catalog/IMG_9730.jpg` | None |
| `storefront-mockup/catalog.json` `/{65–67}/image` | `assets/catalog/IMG_9731.jpg` | None |
| `storefront-mockup/catalog.json` `/{68–70}/image` | `assets/catalog/IMG_9732.jpg` | None |
| `storefront-mockup/catalog.json` `/{71–75}/image` | `assets/catalog/IMG_9733.jpg` | None |
| `storefront-mockup/catalog.json` `/{76,77}/image` | `assets/catalog/IMG_9734.jpg` | None |
| `storefront-mockup/catalog.json` `/{78,79}/image` | `assets/catalog/IMG_9735.jpg` | None |
| `storefront-mockup/catalog.json` `/80/image` | `assets/catalog/IMG_9736.jpg` | None |
| `storefront-mockup/catalog.json` `/81/image` | `assets/catalog/IMG_9738.jpg` | None |
| `hass/content/products.json` `/products/171/image`; `storefront-mockup/completion-new-products.json` `/28/image`; `storefront-mockup/held-products.json` `/products/1/image` | `assets/products/photo-product-133.webp` | `storefront-mockup/assets/products/photo-product-132.webp` and `storefront-mockup/assets/products/photo-product-134.webp` (tie) |

The last row is held in `hass/content/products.json` at `/products/171/status`; `hass/content_model.py:127–128` selects only active products, and `hass/sitegen.py:518–523` uses that selection for exported photos. None of the 98 occurrences was in the scanned HTML, CSS or JS. The 31 missing targets therefore do not establish a broken image on a current page. To check missing names and the numeric neighbors against the Git tree:

```sh
git ls-tree -r --name-only "$base" -- storefront-mockup/assets/catalog \
  storefront-mockup/assets/products/photo-product-132.webp \
  storefront-mockup/assets/products/photo-product-133.webp \
  storefront-mockup/assets/products/photo-product-134.webp
```

## R4. What image QA catches

- **`storefront-mockup/asset-QA.json:2–5`:** the recorded output says `"images": 181` and `"missing": []`. This file is a past receipt, not a check; it detects neither class on current main.
- **`storefront-mockup/optimize-images.cjs:2`:** `items=[...d.products,...d.merch,...d.boxes]` comes from `shop-data.json`. The script derives a source via `p.image.replace(/\.webp$/,'.png')`, then checks `if(!fs.existsSync(src)){missing.push(p.id);continue}` and throws `Error('Missing images: '+missing.join(','))` if any of those inputs is absent. That catches missing *conversion inputs* to that old catalog only. It does not inventory unused tracked assets or cross-check existing target paths across storefront and Hass references. It also writes images, catalog JS/JSON and the receipt, so it was read but not run.
- **One proposed follow-up (estimate: 90 minutes; not implemented):** add read-only `scripts/audit_storefront_assets.py` and an offline `hass/tests/test_audit_storefront_assets.py` fixture. Print unused files and missing references with locations, distinguishing historical/held data from current page sources. A small synthetic fixture should contain one referenced file, one orphan, one absent target named twice, and a remote URL containing `/assets/`; assert one missing path, two locations, correct orphan bytes and no remote match. `python3 -m unittest discover -s hass/tests -p test_audit_storefront_assets.py` would be the offline check. No product restoration, asset removal or policy change is proposed.
