# AVO1520-15 — NPP pins versus files

| Check | Result | Evidence |
|---|---:|---|
| SHA-256 entries | 43 of 43 match | R1; `hass/npp/pins.json:75–119` |
| Recorded hashes that differ / pinned files missing | 0 / 0 | R1; `pins --check` returned `pins ok` |
| Unpinned files inside `hass/npp/assets/` | 0 | R2; recursive inventory and `pins --check` |
| Unpinned files elsewhere under `hass/npp/` | 16 | R2; 15 Python files and the manifest itself, outside the documented asset directory |

Checked offline on 2026-11-21 at `origin/main` `37feae1dc5efa6968f90d17a1eda6daed29afd4a` (the task baseline). This is a checkout audit, not a live or release check. No tests, models, site or runtime were run. `git ls-tree -r --name-only origin/main -- reports/hass-npp` returned no paths, so the brief's `G-QUESTIONS.md` was not available from main; no decision from that document was inferred or revisited.

## R1. Every file-hash pin

The repo's check quotes `hashlib.sha256(p.read_bytes()).hexdigest()` (`scripts/hass/npp_limits.py:116–119`). It uses the raw bytes, without decoding, newline normalization or JSON reserialization, and compares the lowercase hex result directly to the recorded string (`:122–129`). The runtime asset reader does the same comparison on the bytes it returns (`hass/npp/__init__.py:12–26`). A separate stdlib pass applied that exact hash expression to each named file after `Path.is_file()`; all 43 returned `Match`. To reproduce the set comparison from the repo root at the checked main, run `python3 -B scripts/hass/npp_limits.py pins --check`. On 2026-11-21 it printed `pins ok` and exited 0 (`scripts/hass/npp_limits.py:138–151`).

The keys below are literal children of `/assets` in `hass/npp/pins.json:76–118`, in manifest order.

| Key under `/assets` | File | Exists? | SHA-256 |
|---|---|---|---|
| `README.md` | `hass/npp/assets/README.md` | Yes | Match |
| `hass-gallery-style/SKILL.md` | `hass/npp/assets/hass-gallery-style/SKILL.md` | Yes | Match |
| `hass-gallery-style/card.schema.json` | `hass/npp/assets/hass-gallery-style/card.schema.json` | Yes | Match |
| `hass-gallery-style/gallery-fields.tsv` | `hass/npp/assets/hass-gallery-style/gallery-fields.tsv` | Yes | Match |
| `hass-gallery-style/golden/photo-product-002.json` | `hass/npp/assets/hass-gallery-style/golden/photo-product-002.json` | Yes | Match |
| `hass-gallery-style/golden/photo-product-006.json` | `hass/npp/assets/hass-gallery-style/golden/photo-product-006.json` | Yes | Match |
| `hass-gallery-style/golden/photo-product-007.json` | `hass/npp/assets/hass-gallery-style/golden/photo-product-007.json` | Yes | Match |
| `hass-gallery-style/golden/photo-product-015.json` | `hass/npp/assets/hass-gallery-style/golden/photo-product-015.json` | Yes | Match |
| `hass-gallery-style/golden/photo-product-018.json` | `hass/npp/assets/hass-gallery-style/golden/photo-product-018.json` | Yes | Match |
| `hass-gallery-style/golden/photo-product-021.json` | `hass/npp/assets/hass-gallery-style/golden/photo-product-021.json` | Yes | Match |
| `hass-gallery-style/golden/photo-product-024.json` | `hass/npp/assets/hass-gallery-style/golden/photo-product-024.json` | Yes | Match |
| `hass-gallery-style/golden/photo-product-025.json` | `hass/npp/assets/hass-gallery-style/golden/photo-product-025.json` | Yes | Match |
| `hass-gallery-style/golden/photo-product-042.json` | `hass/npp/assets/hass-gallery-style/golden/photo-product-042.json` | Yes | Match |
| `hass-gallery-style/golden/photo-product-044.json` | `hass/npp/assets/hass-gallery-style/golden/photo-product-044.json` | Yes | Match |
| `hass-gallery-style/golden/photo-product-052.json` | `hass/npp/assets/hass-gallery-style/golden/photo-product-052.json` | Yes | Match |
| `hass-gallery-style/golden/photo-product-138.json` | `hass/npp/assets/hass-gallery-style/golden/photo-product-138.json` | Yes | Match |
| `hass-gallery-style/limits.json` | `hass/npp/assets/hass-gallery-style/limits.json` | Yes | Match |
| `hass-listing-copy/SKILL.md` | `hass/npp/assets/hass-listing-copy/SKILL.md` | Yes | Match |
| `hass-listing-copy/copy-templates.json` | `hass/npp/assets/hass-listing-copy/copy-templates.json` | Yes | Match |
| `hass-listing-copy/listing.schema.json` | `hass/npp/assets/hass-listing-copy/listing.schema.json` | Yes | Match |
| `hass-listing-copy/voice-phrases.json` | `hass/npp/assets/hass-listing-copy/voice-phrases.json` | Yes | Match |
| `hass-listing-edit/SKILL.md` | `hass/npp/assets/hass-listing-edit/SKILL.md` | Yes | Match |
| `hass-listing-edit/edit-grammar.json` | `hass/npp/assets/hass-listing-edit/edit-grammar.json` | Yes | Match |
| `hass-listing-edit/edit.schema.json` | `hass/npp/assets/hass-listing-edit/edit.schema.json` | Yes | Match |
| `hass-maker-research/SKILL.md` | `hass/npp/assets/hass-maker-research/SKILL.md` | Yes | Match |
| `hass-maker-research/facts.schema.json` | `hass/npp/assets/hass-maker-research/facts.schema.json` | Yes | Match |
| `hass-maker-research/sources.json` | `hass/npp/assets/hass-maker-research/sources.json` | Yes | Match |
| `hass-maker-research/verify.md` | `hass/npp/assets/hass-maker-research/verify.md` | Yes | Match |
| `hass-missing-info/SKILL.md` | `hass/npp/assets/hass-missing-info/SKILL.md` | Yes | Match |
| `hass-missing-info/missing-info.json` | `hass/npp/assets/hass-missing-info/missing-info.json` | Yes | Match |
| `hass-npp-reply/reply-templates.json` | `hass/npp/assets/hass-npp-reply/reply-templates.json` | Yes | Match |
| `hass-product-identify/SKILL.md` | `hass/npp/assets/hass-product-identify/SKILL.md` | Yes | Match |
| `hass-product-identify/examples.json` | `hass/npp/assets/hass-product-identify/examples.json` | Yes | Match |
| `hass-product-identify/identify.schema.json` | `hass/npp/assets/hass-product-identify/identify.schema.json` | Yes | Match |
| `hass-product-photo/SKILL.md` | `hass/npp/assets/hass-product-photo/SKILL.md` | Yes | Match |
| `hass-product-photo/photo.json` | `hass/npp/assets/hass-product-photo/photo.json` | Yes | Match |
| `hass-style-judge/SKILL.md` | `hass/npp/assets/hass-style-judge/SKILL.md` | Yes | Match |
| `hass-style-judge/calibration/bad/bad-invented-story.json` | `hass/npp/assets/hass-style-judge/calibration/bad/bad-invented-story.json` | Yes | Match |
| `hass-style-judge/calibration/bad/bad-serving-on-nonfood.json` | `hass/npp/assets/hass-style-judge/calibration/bad/bad-serving-on-nonfood.json` | Yes | Match |
| `hass-style-judge/calibration/bad/bad-spec-list.json` | `hass/npp/assets/hass-style-judge/calibration/bad/bad-spec-list.json` | Yes | Match |
| `hass-style-judge/calibration/bad/bad-superlatives.json` | `hass/npp/assets/hass-style-judge/calibration/bad/bad-superlatives.json` | Yes | Match |
| `hass-style-judge/calibration/manifest.json` | `hass/npp/assets/hass-style-judge/calibration/manifest.json` | Yes | Match |
| `hass-style-judge/rubric.json` | `hass/npp/assets/hass-style-judge/rubric.json` | Yes | Match |

The rest of the manifest is metadata or settings, not SHA-256 entries (`hass/npp/pins.json:2–74`). The two renderer paths are worth separating from the table: `git ls-tree origin/main -- storefront-mockup/shop.js hass/screenshot.cjs` lists both. `/renderer/files/0` names `storefront-mockup/shop.js` and `/renderer/files/1` names `hass/screenshot.cjs`. Neither has a recorded SHA-256 to compare; `/renderer/commit` is `null` and `/renderer/set_by` names a later recording step. `/research/allowlist_in` is a reference rather than a second hash pin for `hass-maker-research/sources.json` (`:61–65,102`).

## R2. Files without a pin

`git ls-files hass/npp` and a recursive `Path.rglob('*')` / `is_file()` walk returned the same 59 paths in the fresh checkout. Subtract the repo-relative paths in R1. The README says every file **in `assets/`** is pinned (`hass/npp/assets/README.md:1–5,19–20`); the skill describes SHA-256 pins for runtime assets and directs asset edits to that directory (`docs/hass/skills/hass-npp-maintain/SKILL.md:8–12,14–23`). Neither calls for hash-pinning the following package files in this manifest. The checker also explicitly limits its inventory to `assets/` (`scripts/hass/npp_limits.py:25–29,116–128`).

| Unpinned path | Should the README or skill require a hash here? |
|---|---|
| Inside `hass/npp/assets/`: none | Every file there is covered. |
| `hass/npp/__init__.py` | No stated requirement; package code. |
| `hass/npp/copy.py` | No stated requirement; package code. |
| `hass/npp/edits.py` | No stated requirement; package code. |
| `hass/npp/evidence.py` | No stated requirement; package code. |
| `hass/npp/identify.py` | No stated requirement; package code. |
| `hass/npp/job.py` | No stated requirement; package code. |
| `hass/npp/missing.py` | No stated requirement; package code. |
| `hass/npp/picture.py` | No stated requirement; package code. |
| `hass/npp/pins.json` | No stated requirement; stores the hashes, not a hash of itself. |
| `hass/npp/private_numbers.py` | No stated requirement; package code. |
| `hass/npp/receipt.py` | No stated requirement; package code. |
| `hass/npp/reply.py` | No stated requirement; package code. |
| `hass/npp/research.py` | No stated requirement; package code. |
| `hass/npp/research_hermes.py` | No stated requirement; package code. |
| `hass/npp/stages.py` | No stated requirement; package code. |
| `hass/npp/validate.py` | No stated requirement; package code. |

## R3. Which tests read the manifest?

**None would fail on a mismatch found here: there were no mismatches.** This is source inspection, not a test pass. To locate the readers and follow the startup path, use `git grep -n -E 'pins\.json|pins_check|assets\(\)|npp_stages=' origin/main -- hass/tests hass/conversation.py`.

| Test or reader | What a real checkout asset mismatch would do |
|---|---|
| `PinsTest.test_every_asset_is_pinned_and_hashes_match` (`hass/tests/test_npp_assets.py:643–647`) | Fails directly: the default `pins_check()` reads the checkout and asserts no problems. It also fails for missing pinned files and extra unpinned assets. |
| `PinsTest.test_pinned_models_and_segment_follow_the_design` (`hass/tests/test_npp_assets.py:19,669–679`) | Reads the checkout manifest, but checks metadata, not asset bytes. A byte-only mismatch would not fail it. |
| `PinsTest.test_pin_check_catches_each_kind_of_drift` (`hass/tests/test_npp_assets.py:649–667`) | Reads a temporary manifest only. Expects the checker to report changed, added and missing fixture files; checkout drift does not fail it. |
| `PreflightTests` (`hass/tests/test_npp_preflight.py:25–78,80–173`), notably `test_npp_preflight`, `test_changed_and_deleted_assets_are_named`, `test_missing_manifest_and_missing_allowlist_block_independently` and `test_bad_json_or_pin_path_is_input_error` | Its CLI runs read temporary release manifests (or exercise the missing-manifest case). It does not use the checkout manifest. `scripts/hass/npp_preflight.py:118–142` hashes fixture bytes for listed assets; the changed/deleted test expects refusal for those fixtures. |
| `test_npp_edits.py:19`; `test_npp_identify.py:10` (all test paths here under `hass/tests/`) | Read the checkout via `hass.npp.assets()` at module import. A mismatch would stop import, not produce an assertion failure. |
| `CaptionTable` (`test_npp_caption_table.py:160–163`), `CopyTests` (`test_npp_copy.py:18–21`), `EditPhraseTests` (`test_npp_edit_phrases.py:193–196`), `SecondProductTests` (`test_npp_second_product.py:41–64`), `StageTests` (`test_npp_stages.py:17–27`), `ValidateTests` (`test_npp_validate.py:13–15`) | Read it via the runtime loader in setup; a mismatch would raise there. |
| `EditEvalTests.test_c1_phrase_file_valid` (`test_npp_edit_eval.py:36–38`), `PostedLinkTests` helper (`test_npp_posted_link.py:101,156`), `ResearchTests` fixture (`test_npp_research.py:25–29,82–85`) | Runtime loader calls in a test or fixture helper; a mismatch would raise when that path runs. |
| NPP-enabled conversation fixtures (e.g. `test_npp_job.py:103–115`, `test_npp_status_line.py:22–25`, `test_npp_undo_journey.py:106–113`) | Indirect read even with injected stages. The constructor catches the mismatch and leaves NPP disabled (`hass/conversation.py:549–558`); tests relying on it being enabled can then fail, rather than receiving the digest exception directly. |

## R4. Ranked gaps and follow-up

1. **No current asset drift or missing coverage to fix.** All 43 named files match, and the checker finds no missing or extra asset (`R1–R2`; `scripts/hass/npp_limits.py:122–129`).
2. **Install/startup checks are narrower than the checkout check.** They iterate listed assets, so they do not by themselves flag a newly added file with no pin (`scripts/hass/npp_preflight.py:125–142`; `hass/npp/__init__.py:12–26`). The maintenance checker and its existing coverage already check both directions (`scripts/hass/npp_limits.py:122–129`; `hass/tests/test_npp_assets.py:643–667`). No uncovered file was observed.
3. **Package source and renderer provenance are outside the SHA-256 asset map.** The 16 R2 files are not required by the cited docs to be hash-pinned here, and the renderer commit is explicitly unset on this main (`hass/npp/pins.json:67–75`). That is not evidence of stale asset bytes or a reason to change the manifest in this audit.

**No build unit is needed for the observed results.** No pin, runtime behavior or owner decision was changed.
