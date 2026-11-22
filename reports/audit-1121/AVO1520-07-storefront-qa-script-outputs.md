# AVO1520-07 — Storefront QA script outputs

| Question | Finding |
|---|---|
| R1 — What writes what? | Six tracked JSON results match current QA writer names, but only three are written to their tracked paths. A seventh JSON, `asset-QA.json`, comes from the image optimizer. See the writer table. |
| R2 — What has no named writer? | 17 of 31 tracked PNG/JPG files have no matching output name in the audited scripts. All seven result JSON names have a writer once the optimizer is included. The numbered JPGs match a template, but cannot be regenerated from the tracked product assets alone. |
| R3 — What is missing? | Seven direct writers name 13 fixed JSON or PNG outputs whose names are absent from main. All 13 are written outside the repository. |
| R4 — What should happen next? | No build unit recommended. Use the inventory to distinguish saved evidence from fresh output; do not backfill scratch results into Git. |

## R1. Writers, tracked files, and prerequisites

Start tree: `37feae1dc5efa6968f90d17a1eda6daed29afd4a` (cloned `origin/main`, same as the supplied baseline). Scope is the QA evidence kept directly in `storefront-mockup/` and all 17 top-level `*-qa.*` sources, including the extra helper, fixture test and Python wrapper. The historical archive, other reports, and site assets are not part of the screenshot census (`AGENTS.md:3–5`; `storefront-mockup/README.md:17,28,41,77–79`). The contrast Markdown is included below only to distinguish it from the collector's JSON. No QA script was run, no image was opened, and no saved result is treated as a new pass (`AGENTS.md:15–16`).

Source anchors in the table are `storefront-mockup/<script>:<line>` unless another path is shown. **Tracked** means the exact output path is in main; **same name** means a tracked copy has that basename but the writer targets `out/` outside the repository; **absent** means the named artifact is not in main. `out/` here denotes the resolved output directory, not a repo path: `qa-env.cjs:19–38` uses `QA_OUT_DIR` outside the repository or a fresh temp folder, and its preview gate requires explicit loopback HTTP. The Python community wrapper does its own output and URL checks (`community-qa.py:5–14`). “Server” says whether the check exercises HTTP and whether the caller supplies the server. Fixtures and in-memory captures are called out but not counted as QA result files.

| Script | Files written and tree status (source lines) | Browser? | HTTP server? |
|---|---|---|---|
| `catalog-qa.cjs` | **Tracked:** `catalog-desktop.png`, `catalog-mobile.png` (`:2`, repo-relative). JSON to stdout only (`:2`). | Yes, Chromium (`:1–2`). | Yes, supplied loopback on port 3101 (`:2`). |
| `catalog-only-qa.cjs` | **Same name:** `out/catalog-only-QA.json` (`:696`). **Absent:** `out/catalog-inline-390.png`, `out/catalog-inline-1440.png`, `out/catalog-maker-390.png`, `out/catalog-maker-1440.png` (`:231`). | Yes, Chromium (`:4–6`). | Yes, supplied `PREVIEW_URL` (`:2,8`; `qa-env.cjs:25–31`). |
| `community-qa.py` | **Same name:** `out/community-api-QA.json` (`:132`). Also creates temporary fixture `community.json` and `community.sqlite3` (not result files; `:21–26`); delegates all UI outputs in the next row (`:128–129`). | Yes end to end, via the UI child (`:128–129`; `community-ui-qa.cjs:2–6`); no browser in the Python API assertions (`:30–36`). | Yes, starts a loopback fixture on a free port (`:23–35`); also requires supplied `PREVIEW_URL` for the UI child's preview leg (`:5–7,129`; `community-ui-qa.cjs:1,165`). |
| `community-ui-qa.cjs` | **Same name:** `out/community-ui-QA.json` (`:414`). **Absent:** `out/hiking-intro-mobile.png`, `out/hiking-invitation-mobile.png`, `out/hiking-history-mobile.png`, `out/hiking-desktop.png` (`:202–206`, respectively). | Yes, Chromium (`:2–6`). | Yes, supplied `COMMUNITY_TEST_URL` fixture and `PREVIEW_URL` preview (`:1,11–15,165`); the Python caller supplies the first (`community-qa.py:129`). |
| `dialog-pointer-qa.cjs` | No named file output; assertion and console check (`:10–69`). | Yes, Chromium (`:6,11`). | No. Browser routes supply the synthetic page, JS and CSS and abort other requests (`:16–18`). |
| `image-qa.cjs` | **Tracked by template:** `image-review-1.jpg`, `image-review-2.jpg`, `image-review-3.jpg`, `image-review-4.jpg`, `image-review-5.jpg`, `image-review-6.jpg`, `image-review-7.jpg`, `image-review-8.jpg`, `image-review-9.jpg`, `image-review-10.jpg`. It writes one JPEG contact sheet per batch of up to 20 sorted `.png` inputs (`:2`, repo-relative). The tracked product folder has zero such inputs (see commands below), so the pinned tree alone selects zero outputs, not a missing eleventh sheet. | No, uses Sharp (`:1–2`). | No, local files only (`:2`). |
| `invitation-qa.cjs` | No named file output; exported assertion helper (`:3–end`), called by `community-ui-qa.cjs:412` and `static-site-qa.cjs:281`. | Yes, browser supplied by caller (`:3–4`). | Yes, caller supplies `base` for page loads; API and JSON responses can be intercepted (`:3,11–13,43`). |
| `resource-qa.cjs` | **Tracked:** `resource-QA.json` (`:1`, repo-relative). | No, uses HTTP `fetch` without Playwright (`:1`). | Yes, supplied loopback on port 3101 (`:1`). |
| `scroll-qa.cjs` | **Tracked:** `category-mobile.png`, `scroll-QA.json` (`:2`, repo-relative). | Yes, Chromium (`:1–2`). | Yes, supplied loopback on port 3101 (`:2`). |
| `section-navigation-qa.cjs` | **Absent:** `out/section-navigation-QA.json` (`:20`). | Yes, Chromium (`:2,5`). | Yes, supplied `PREVIEW_URL` (`:1,9`; `qa-env.cjs:25–31`). |
| `site-a11y-qa.cjs` | No named QA result file: JSON to stdout (`:151`); screenshot pairs are buffers without a path (`:58`). Publishes a temporary site as a fixture (`:8–11`). | Yes, Chromium (`:7,146`). | Yes, starts its own loopback static fixture (`:17–21,91,147`). |
| `site-contrast-qa.cjs` | **Absent:** `out/contrast.json` (`:156,644`); pixel samples are in-memory screenshots (`:366–368`). This row describes the CLI, not the library import (`:151`). | Yes, Chromium (`:499–500`). | Yes, starts two loopback fixture servers (`:171–181,497–498`). |
| `site-contrast-qa.py` | Delegates `contrast.json` to the JS collector in a temporary tree (`:66–75,226–229,257–258`). Optional JSON at the caller's `--json-out` path (`:221,230–231`), so no fixed path to check. **Tracked:** `reports/site-contrast-2026-11.md` (`:24`); on `--write` only, and only when changed or missing (`:218–220,245–255`); path overridable by `--report`. Also writes two temporary site fixtures (`:44–58,228`). | Yes, via collector (`:66–72,223–229`; `site-contrast-qa.cjs:499–500`). | Yes, via collector; no prestarted server (`:66–72`; `site-contrast-qa.cjs:171–181,497`). |
| `static-site-qa.cjs` | **Absent:** `out/static-site-QA.json` (`:286`). | Yes, Chromium (`:10,42`). | Yes, starts its own loopback server; caller supplies a published folder, not a running service (`:12–15,21–29,40–42`). |
| `story-qa.cjs` | **Tracked:** `story-mobile.png`, `story-QA.json` (`:2`, repo-relative). | Yes, Chromium (`:1–2`). | Yes, supplied loopback on port 3101 (`:2`). |
| `trail-map-retry-qa.cjs` | **Absent:** `out/trail-map-retry-QA.json` (`:175`). | Yes, Chromium (`:4,172`). | Yes, starts its own loopback fixture (`:11,171`). |
| `trail-observer-qa.cjs` | **Absent:** `out/trail-observer-QA.json` (`:115`). | Yes, Chromium (`:4,112`). | Yes, starts its own loopback fixture (`:10,111`). |

Related non-QA writer: `storefront-mockup/optimize-images.cjs:1–2` writes the tracked `storefront-mockup/asset-QA.json` at its repo path, after image conversion completes without missing sources. It uses local files and Sharp, with neither browser nor server. `qa-env.cjs` is an output-directory helper, not an artifact writer (`:23–38,55`).

## R2. Tracked evidence with no matching output name

No JSON is unmatched across the identified writers. For the `*-qa.*` set alone, the only unmatched JSON name is `asset-QA.json` (optimizer exception above). The following are names only, relative to `storefront-mockup/`. Compare the tree-name inventory with the output call sites in R1; this does not assign historical authorship. In particular, `README.md:31,53` groups older screenshots with the catalog/community checks, but the current output names differ (`catalog-only-qa.cjs:231`; `community-ui-qa.cjs:202–206`).

- `catalog-only-cards-mobile.png`
- `catalog-only-desktop.png`
- `catalog-only-detail-mobile.png`
- `catalog-only-hero-mobile.png`
- `catalog-only-mobile.png`
- `community-hikes-desktop.png`
- `community-hikes-mobile.png`
- `community-newsletter-mobile.png`
- `desktop.png`
- `mobile-visual-375-footer.png`
- `mobile-visual-375-hero.png`
- `mobile-visual-375-market.png`
- `mobile-visual-375-purpose.png`
- `mobile-visual-390-footer.png`
- `mobile-visual-390-hero.png`
- `mobile-visual-390-market.png`
- `mobile.png`

## R3. Named output absent from main

| Direct writer | Absent fixed filenames and write anchors |
|---|---|
| `catalog-only-qa.cjs` | `catalog-inline-390.png`, `catalog-inline-1440.png`, `catalog-maker-390.png`, `catalog-maker-1440.png` (`:231`) |
| `community-ui-qa.cjs` | `hiking-intro-mobile.png`, `hiking-invitation-mobile.png`, `hiking-history-mobile.png`, `hiking-desktop.png` (`:202–206`) |
| `section-navigation-qa.cjs` | `section-navigation-QA.json` (`:20`) |
| `site-contrast-qa.cjs` | `contrast.json` (`:644`) |
| `static-site-qa.cjs` | `static-site-QA.json` (`:286`) |
| `trail-map-retry-qa.cjs` | `trail-map-retry-QA.json` (`:175`) |
| `trail-observer-qa.cjs` | `trail-observer-QA.json` (`:115`) |

The three **same name** JSON results in R1 are also never written to their tracked paths by these scripts. The two Python wrappers inherit their child outputs, not additional fixed result names (`community-qa.py:129`; `site-contrast-qa.py:66–75`). Scratch fixtures and caller-selected paths are not missing QA deliverables.

## R4. Ranked gaps

1. **Most likely to confuse a reviewer: old screenshot names read like current outputs.** The README's catalog and community evidence descriptions do not match the current screenshot writers (`storefront-mockup/README.md:31,53`; R2 and `catalog-only-qa.cjs:231`, `community-ui-qa.cjs:202–206`).
2. **The old image-review sheets are not reproducible from tracked inputs alone.** The writer selects only product PNGs, not the optimized assets (`image-qa.cjs:2`; product-name check below). That is an input limit, not a reason to bring original images into Git (`AGENTS.md:13–14`).
3. **A tracked result and a fresh result are not interchangeable.** The six JSON name matches in R1 include three copies the current guarded writers do not overwrite. All 13 absent fixed names intentionally go to `out/` by source design (`qa-env.cjs:19–38`; R3). This is not evidence of a failing QA run.

**No buildable unit is needed for these findings.** The inventory resolves which outputs to look for without a script change or a requirement to commit generated evidence.

### Reproduce the read-only checks

Run from the repo root. Inspect the whole matched call and follow wrappers; a `.screenshot` match without a path is not a file. The pinned inventory returns seven QA JSON names and 31 PNG/JPG names. The unmatched-name source scan, product PNG query, and fixed-name absence query each return no matches (exit 1, not a command error). The last command lists only the contrast Markdown report.

```sh
base=37feae1dc5efa6968f90d17a1eda6daed29afd4a
git ls-tree --name-only "$base:storefront-mockup" | rg -- '-qa[.][^.]+$'
git grep -nE 'screenshot[(]|[.]toFile[(]|writeFile(Sync)?[(]|write_(text|bytes)[(]|saveAs[(]|[.]launch[(]|[.]listen[(]|[.]goto[(]|urlopen|subprocess[.]run' "$base" -- ':(top,glob)storefront-mockup/*-qa.*' storefront-mockup/qa-env.cjs storefront-mockup/optimize-images.cjs
git ls-tree --name-only "$base:storefront-mockup" | rg -i '(-qa[.]json|[.](png|jpe?g))$'
git grep -nE 'catalog-only-(cards-mobile|desktop|detail-mobile|hero-mobile|mobile)[.]png|community-(hikes-desktop|hikes-mobile|newsletter-mobile)[.]png|mobile-visual-(375|390)-(footer|hero|market|purpose)[.]png|(^|[^[:alnum:]_.-])(desktop|mobile)[.]png' "$base" -- ':(top,glob)storefront-mockup/*.cjs' ':(top,glob)storefront-mockup/*.js' ':(top,glob)storefront-mockup/*.py'
git ls-tree --name-only "$base:storefront-mockup/assets/products" | rg '[.]png$'
git ls-tree -r --name-only "$base" | rg '(^|/)(contrast[.]json|catalog-(inline|maker)-(390|1440)[.]png|hiking-(intro-mobile|invitation-mobile|history-mobile|desktop)[.]png|section-navigation-QA[.]json|static-site-QA[.]json|trail-map-retry-QA[.]json|trail-observer-QA[.]json)$'
git ls-tree -r --name-only "$base" -- reports/site-contrast-2026-11.md storefront-mockup/contrast.json
```
