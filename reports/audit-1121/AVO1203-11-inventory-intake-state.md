# Inventory intake: manifest, workflow and test coverage

| Question | Finding |
| --- | --- |
| R1. What is in the folder? | Six tracked files. The manifest records 36 source entries: 33 photo rows and 3 linked duplicates. None of the named originals, converted photos or previews ships in the checkout. See the R1 tree and filename comparison. |
| R2. What can you run? | `workflow.txt` describes eight human/process steps, not shell commands. Neither script parses arguments. The importer is tied to a fixed Mac input location; the builder only generates review artifacts. See R2. |
| R3. Do the tool and test agree? | All 11 review-builder tests passed offline on Python 3.12.3. `.github/workflows/check.yml` does not run them. See R3. |
| R4. What next? | Do not treat the checkout as a portable intake kit. If the renderer is to be maintained, wire its existing test into `quick`; no media or product decision is needed for that unit. See R4. |

Checked 2026-11-21 UTC in a fresh clone of `tidepool-labs/avocado-shack`. Both `git rev-parse HEAD` and `git rev-parse origin/main` returned the task baseline, `37feae1dc5efa6968f90d17a1eda6daed29afd4a`. All source anchors are at that commit. This is about the legacy intake folder, not the active catalog (`AGENTS.md:3–15`). No real files were imported, no checkout review page was rebuilt, and no site, private storage or service was accessed.

## R1. Folder and manifest

| Tracked file | Role and anchor |
| --- | --- |
| `manifest.json` | Recorded input rows, duplicate links and private draft observations (`/0`, `/33`). |
| `import_photos.py` | Reads the fixed source set, hashes originals, links duplicate hashes, converts photos, and writes previews, contact sheets and the manifest (`:5–22`). |
| `build_review.py` | Reads the sibling manifest, checks observation field types, writes back draft metadata and generates the sibling review page (`:4–21`). |
| `test_build_review.py` | Runs copies of the builder against temporary inputs, including a copy of the checked-in manifest (`:80–97`, `:273–288`). |
| `review.html` | Saved private review page. Its 33 photo links and 33 preview links use the same basenames as the 33 photo rows (`:1`; comparison below). |
| `workflow.txt` | Historical photo-to-approval procedure and its original evidence counts (`:1–13`). |

`manifest.json` is a JSON array (root pointer `""`). In the next two tables, `/0` through `/32` refer to the photo rows; `/33` through `/35` refer to the duplicate-only rows. These are recorded values, not newly verified source hashes or product facts.

| Rows | Fields present on every row of that kind | Counts and values |
| --- | --- | --- |
| `/0`–`/32` | `source_file`, `sha256`, `photo`, `status`, `product_name`, `quantity`, `stock_pool`, `unit`, `price_minor_units`, `currency`, `claims`, `observed_category`, `visual_observation`, `publication_status`, `shipping_eligibility`, `stock_count_inferred` | 33 rows, 33 distinct source hashes. `source_file` and `photo` are absolute paths; `photo` names the converted JPEG under the intake `photos/` directory. Both observation fields are nonempty strings on 33/33. All 33 have `status: needs_review`, `publication_status: private_draft`, `shipping_eligibility: unverified`, `stock_count_inferred: false`, `currency: USD`, `claims: []`, and `null` for `product_name`, `quantity`, `stock_pool`, `unit` and `price_minor_units`. |
| `/33`–`/35` | `source_file`, `sha256`, `duplicate_of` | 3 rows, no `photo` field. Each names the original source basename and repeats the target row's recorded hash. There are 33 distinct recorded hashes across all 36 rows. |

**Manifest → files.** Every row below has a missing source in the checkout. For photo rows, the named JPEG and the review's expected preview (same JPEG basename) are also absent. Original host paths are omitted; no check was made on that host. The output folders and contact sheets are deliberately ignored in Git (`.gitignore:19–24`).

| Manifest row pointer | `source_file` basename (absent) | `photo` and preview basename (both absent) | `duplicate_of` target (recorded hash matches) |
| --- | --- | --- | --- |
| `/0` | `IMG_9707.heic` | `IMG_9707.jpg` | — |
| `/1` | `IMG_9708.heic` | `IMG_9708.jpg` | — |
| `/2` | `IMG_9709.heic` | `IMG_9709.jpg` | — |
| `/3` | `IMG_9710.heic` | `IMG_9710.jpg` | — |
| `/4` | `IMG_9711.heic` | `IMG_9711.jpg` | — |
| `/5` | `IMG_9712.heic` | `IMG_9712.jpg` | — |
| `/6` | `IMG_9713.heic` | `IMG_9713.jpg` | — |
| `/7` | `IMG_9714.heic` | `IMG_9714.jpg` | — |
| `/8` | `IMG_9715.heic` | `IMG_9715.jpg` | — |
| `/9` | `IMG_9716.heic` | `IMG_9716.jpg` | — |
| `/10` | `IMG_9717.heic` | `IMG_9717.jpg` | — |
| `/11` | `IMG_9718.heic` | `IMG_9718.jpg` | — |
| `/12` | `IMG_9719.heic` | `IMG_9719.jpg` | — |
| `/13` | `IMG_9720.heic` | `IMG_9720.jpg` | — |
| `/14` | `IMG_9721.heic` | `IMG_9721.jpg` | — |
| `/15` | `IMG_9722.heic` | `IMG_9722.jpg` | — |
| `/16` | `IMG_9723.heic` | `IMG_9723.jpg` | — |
| `/17` | `IMG_9724.heic` | `IMG_9724.jpg` | — |
| `/18` | `IMG_9725.heic` | `IMG_9725.jpg` | — |
| `/19` | `IMG_9726.heic` | `IMG_9726.jpg` | — |
| `/20` | `IMG_9727.heic` | `IMG_9727.jpg` | — |
| `/21` | `IMG_9728.heic` | `IMG_9728.jpg` | — |
| `/22` | `IMG_9729.heic` | `IMG_9729.jpg` | — |
| `/23` | `IMG_9730.heic` | `IMG_9730.jpg` | — |
| `/24` | `IMG_9731.heic` | `IMG_9731.jpg` | — |
| `/25` | `IMG_9732.heic` | `IMG_9732.jpg` | — |
| `/26` | `IMG_9733.heic` | `IMG_9733.jpg` | — |
| `/27` | `IMG_9734.heic` | `IMG_9734.jpg` | — |
| `/28` | `IMG_9735.heic` | `IMG_9735.jpg` | — |
| `/29` | `IMG_9736.heic` | `IMG_9736.jpg` | — |
| `/30` | `IMG_9737.heic` | `IMG_9737.jpg` | — |
| `/31` | `IMG_9738.heic` | `IMG_9738.jpg` | — |
| `/32` | `IMG_9739.heic` | `IMG_9739.jpg` | — |
| `/33` | `IMG_9709 2.heic` | Not named | `IMG_9709.heic` (`/2`) |
| `/34` | `IMG_9708 2.heic` | Not named | `IMG_9708.heic` (`/1`) |
| `/35` | `IMG_9708 3.heic` | Not named | `IMG_9708.heic` (`/1`) |

**Files → manifest.** The table is exhaustive for the named directories at the pinned tree. Ranges are inclusive and preserve three-digit padding. The comparison is by exact basename, not a claim about image identity, catalog usage or publication eligibility.

| Tree directory | Tracked files in no manifest entry | Count |
| --- | --- | ---: |
| `inventory-intake/photos/` | None present | 0 |
| `inventory-intake/previews/` | None present | 0 |
| `storefront-mockup/assets/products/` | `photo-product-NNN.webp` for `001–019`, `021–035`, `037–132`, `134–174` | 171 |
| `storefront-mockup/assets/products/` | `box-large.webp`, `box-medium.webp`, `box-small.webp` | 3 |
| `storefront-mockup/assets/products/` | `merch-bottle.webp`, `merch-cap.webp`, `merch-coast.webp`, `merch-mug.webp`, `merch-stickers.webp`, `merch-sweat.webp`, `merch-tee.webp`, `merch-tote.webp` | 8 |

Reproduce in the pinned clone: `git ls-tree -r --name-only origin/main -- inventory-intake storefront-mockup/assets/products/`. Parse `git show origin/main:inventory-intake/manifest.json` as JSON, group keys and distinct `sha256` by presence of `photo`, and compare the `source_file`, `photo` and `duplicate_of` basenames to the tree list. For the saved page, read `git show origin/main:inventory-intake/review.html`, URL-decode the names after `photos/` and `previews/`, and compare each list with the manifest's `photo` basenames. The 2026-11-21 read returned 0 files in each intake media directory and 182 product asset names with 0 exact matches. `workflow.txt:12` describes an earlier local visual review; this check does not repeat it or test original/converted image bytes.

## R2. Workflow versus actual script arguments

`inventory-intake/workflow.txt:1–13` contains **no command, argument list or script invocation**. Its prescribed order is below. The script column refers to files under `inventory-intake/`.

| Step in `workflow.txt` | What the scripts actually do |
| --- | --- |
| 1 (`:3`): “Capture original image/message with actor and event ID; link exact duplicates” | The importer reads a fixed list of filenames and links duplicate hashes; it records no actor or event ID (`import_photos.py:5–14`). |
| 2 (`:4`): “Classify single product versus multi-product shelf versus store context” | The importer does not classify. The builder makes one card per photo row, not one per product (`import_photos.py:11–15`; `build_review.py:7–18`). |
| 3 (`:5`): “Suggest product identity and readable label evidence.” | The builder uses existing row-local observations or fallback text; it does not read pixels or identify products (`build_review.py:5–18`). |
| 4 (`:6`): “Ask: arrival, transfer, or total count?” then unit, price and allocation | The builder displays an owner-confirmation reminder, not a form or dialogue (`build_review.py:18–20`). |
| 5 (`:7`): “For new products collect name/variant” and other product details | The importer initializes unknown fields; the builder adds private draft/unverified metadata, not a product or shipping decision (`import_photos.py:14`; `build_review.py:15–20`). |
| 6 (`:8`): “Show exact before/after” and “approve once in authenticated owner session” | Neither script implements a product/stock diff or approval (`import_photos.py:7–22`; `build_review.py:7–21`). |
| 7 (`:9`): “Apply through supported commerce interfaces; read back and record the result.” | The scripts write local intake artifacts only, not commerce transactions (`import_photos.py:11–22`; `build_review.py:19–21`). |
| 8 (`:10–11`): “Only approved catalog and allocated online stock become purchasable.” | Neither script implements publication or checkout. The saved-page template explicitly says nothing is available to order (`build_review.py:18–21`); the current site is catalog-only (`AGENTS.md:3–8`). |

- **Importer, first by data dependency, not by a documented command:** `import_photos.py:1–22` reads no command-line arguments. The inputs are the hard-coded `names` list under a fixed Downloads path and a Pillow installation (`:1–8`). It invokes `sips` with `'-s', 'format', 'jpeg', str(p), '--out', str(dest)` (`:12`). It expects `photos/` and `previews/` to exist and writes `manifest.json` last (`:11–21`). No caller-supplied input/output path, help or dry-run is parsed.
- **Review builder, next by data dependency:** `build_review.py:1–21` also reads no command-line arguments; it locates the sibling `'manifest.json'` via `Path(__file__).resolve().parent`. It checks `'observed_category'` and `'visual_observation'` types before writing `'manifest.json'` and `'review.html'` (the latter uses `'photos/'` and `'previews/'` links). It does not check that either media file exists. No input/output, help or dry-run switch is parsed. Neither script's entry point was run on the checkout manifest.

## R3. CI reach and offline result

**No: `check.yml` does not execute `inventory-intake/test_build_review.py`.** `quick` runs scoped Pillow discovery, compilation of two other directories, Commerce Node tests and the affected Hass runner (`.github/workflows/check.yml:91–116`). Full shards are also delegated to the Hass runner (`:138–176`), whose discovery is rooted at `hass/tests/` and whose module names use `hass.tests.` (`hass/tests/ci_shards.py:50–53,76–90,479`). `inventory-intake/` is a known changed-path area, not a test search root (`.github/workflows/check.yml:16–25`; `hass/tests/ci_shards.py:63–67`). `site` runs catalog/community and published-site checks (`.github/workflows/check.yml:226–263`); the required `check` aggregates jobs and verifies shard records (`:269–300`). A local `git grep -n -E 'test_build_review|build_review\.py' origin/main -- .github hass/tests` found no literal invocation (exit 1); the discovery boundaries above explain why it is not picked up implicitly.

Run 2026-11-21 UTC from the scratch clone root: `python3 --version`, then `python3 -B inventory-intake/test_build_review.py`. The launcher unset `BUILD_REVIEW_SCRIPT` and set `TMPDIR` to a task-local directory. Exit **0**; complete output:

```text
Python 3.12.3
...........
----------------------------------------------------------------------
Ran 11 tests in 0.609s

OK
```

The suite runs the builder in temporary copies, tests row-local observations, escaping, unknown-value fallbacks and refusal before writes, then checks the real manifest's observations and 33/3 split in another temporary copy (`test_build_review.py:80–97,124–284`). It does not run the importer, read any photos, or check that links resolve. The checkout stayed clean after the test (`git status --porcelain`, no output).

## R4. Ranked gaps and one possible follow-up

1. **The review images cannot be opened from the checkout.** The manifest and saved page agree on names, but Git excludes the media and the builder does not check link targets (R1; `.gitignore:19–24`; `build_review.py:17–20`). This is a checkout limitation, not evidence that originals should be recovered or committed.
2. **The workflow is not a runbook for these tools.** The importer is machine-specific, and the documented approval, commerce apply and checkout steps have no counterpart in either script (R2; `workflow.txt:3–11`; `AGENTS.md:3–8`).
3. **A renderer regression can miss required CI.** The existing focused suite passes but is outside `check.yml`'s runners (R3). A green workflow would not assert these escaping and row-association contracts.

**One proposed unit, only if maintainers want CI coverage for the legacy renderer (estimate: 30–60 minutes):** Change only `.github/workflows/check.yml` to run the existing `python3 -B inventory-intake/test_build_review.py` in `quick` under its existing Python 3.12 setup (`:77–79`). Offline acceptance: replay that exact step from a fresh checkout with a disposable `TMPDIR` and no `BUILD_REVIEW_SCRIPT` override; require 11 passing tests, an unchanged checkout, and the exact command present as a `quick` step outside the Hass tier conditional. This would catch a regression in existing renderer contracts without importing photos or inspecting a live site. It would not validate the availability, identity, rights or claims of any image. No follow-up was implemented here.
