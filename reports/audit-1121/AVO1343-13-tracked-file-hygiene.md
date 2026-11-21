# Tracked-file hygiene — Avocado Shack

| Check | Result on main |
| --- | --- |
| R1. Largest files | 40 of 2,419 tracked blobs, totaling 39,250,168 bytes. 34 have a reference found; 6 do not in this pass. |
| R2. Private-looking names | 72 path matches; no effective ignore-rule matches, and one explicit exception. Names are not evidence of private contents. |
| R3. Likely copies | 9 same-name, same-size groups across 20 paths. |
| R4. Build output and next step | No standard build/cache path found by the stated filter. Some of the largest files are tracked QA or review outputs. No implementation unit proposed. |

Snapshot: `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, checked **2026-11-21**. Scope is the tracked tree (not Git history, untracked files, or the live site). `AGENTS.md:3–5` distinguishes current storefront source from historical commerce; `storefront-mockup/README.md:41` identifies archived commerce QA. `AGENTS.md:13–16` sets the data boundary. The cited `reports/hass-npp/G-QUESTIONS.md` was not tracked at the requested base (`git ls-tree -r --name-only origin/main`); no decisions from it were inferred or changed.

## R1. The 40 largest tracked files

Source: `git ls-tree -r -l origin/main`. Sort blob rows by byte size descending, breaking ties by full path ascending (byte order); show the last filename extension. These are uncompressed blob sizes, not Git pack size or deployed transfer size.

**Yes** means a tracked page, script (including tests or generators) or doc names the path, a resolvable filename, a matching output family, an import, or an implicit tooling input as noted. A test exclusion, output producer, or historical mention is a reference, not a current customer-facing use. **No** means not found in this bounded scan, not unused or safe to remove.

| Rank | Tracked path | Bytes | Ext. | Ref.? | Evidence on main |
| --- | --- | --- | --- | --- | --- |
| 1 | `storefront-mockup/assets/vegetables.jpg` | 3,139,056 | `.jpg` | Yes | Test exclusion, `hass/tests/test_publish.py:32–37` |
| 2 | `storefront-mockup/desktop.png` | 3,112,582 | `.png` | Yes | QA output, `storefront-mockup/archive/commerce-preview/qa/qa.cjs:2`; test exclusion, `hass/tests/test_publish.py:36` |
| 3 | `storefront-mockup/assets/pantry.jpg` | 2,556,164 | `.jpg` | Yes | Test exclusion, `hass/tests/test_publish.py:32–37` |
| 4 | `storefront-mockup/assets/berries.jpg` | 2,464,670 | `.jpg` | No | No match in the scan below |
| 5 | `storefront-mockup/assets/avocados.jpg` | 2,309,890 | `.jpg` | No | No match in the scan below |
| 6 | `storefront-mockup/assets/trails/point-buchon-aerial.webp` | 1,807,066 | `.webp` | Yes | Trail script, `storefront-mockup/trail-explorer.js:31`; site generator, `hass/sitegen.py:475` |
| 7 | `branding/logo-refresh/04-growers-stamp.png` | 1,602,734 | `.png` | Yes | Branding review page, `branding/logo-refresh/gallery.html:1` |
| 8 | `storefront-mockup/catalog-desktop.png` | 1,556,624 | `.png` | Yes | QA output, `storefront-mockup/catalog-qa.cjs:2` |
| 9 | `branding/logo-refresh/05-coast-woodcut.png` | 1,509,798 | `.png` | Yes | Branding review page, `branding/logo-refresh/gallery.html:1` |
| 10 | `branding/logo-refresh/06-neighbor-avocado.png` | 1,346,292 | `.png` | Yes | Branding review page, `branding/logo-refresh/gallery.html:1` |
| 11 | `branding/logo-refresh/01-coastal-shack.png` | 1,345,151 | `.png` | Yes | Branding review page, `branding/logo-refresh/gallery.html:1` |
| 12 | `branding/logo-refresh/09-growers-coast.png` | 1,259,375 | `.png` | Yes | Branding review page, `branding/logo-refresh/gallery.html:1` |
| 13 | `branding/logo-refresh/03-coastal-cut.png` | 1,240,564 | `.png` | Yes | Branding review page, `branding/logo-refresh/gallery.html:1` |
| 14 | `branding/logo-refresh/07-market-crate.png` | 1,233,664 | `.png` | Yes | Branding review page, `branding/logo-refresh/gallery.html:1` |
| 15 | `branding/logo-refresh/08-shack-script.png` | 1,233,051 | `.png` | Yes | Branding review page, `branding/logo-refresh/gallery.html:1` |
| 16 | `branding/logo-refresh/10-as-mark.png` | 1,224,395 | `.png` | Yes | Branding review page, `branding/logo-refresh/gallery.html:1` |
| 17 | `storefront-mockup/mobile.png` | 1,200,681 | `.png` | Yes | QA output, `storefront-mockup/archive/commerce-preview/qa/qa.cjs:2`; test exclusion, `hass/tests/test_publish.py:36` |
| 18 | `branding/logo-refresh/02-market-lettering.png` | 1,193,567 | `.png` | Yes | Branding review page, `branding/logo-refresh/gallery.html:1` |
| 19 | `reports/hass/newitem-1/before-after.png` | 913,017 | `.png` | Yes | Report, `reports/hass/NEWITEM-1.md:65`; demo output, `hass/newitem_demo.py:72` |
| 20 | `storefront-mockup/catalog-only-desktop.png` | 676,368 | `.png` | Yes | Documented screenshot family, `storefront-mockup/README.md:31` (`catalog-only-*.png`) |
| 21 | `commerce/package-lock.json` | 648,901 | `.json` | Yes | Implicit npm input, `commerce/README.md:13` (`npm ci` in the commerce setup) |
| 22 | `BUILD_LEDGER.md` | 503,724 | `.md` | Yes | Repository guide, `AGENTS.md:4` |
| 23 | `branding/logo-refresh/ten-logo-directions.jpg` | 422,032 | `.jpg` | Yes | Generated review sheet, `branding/logo-refresh/build-review.cjs:3` |
| 24 | `storefront-mockup/assets/trails/point-buchon-topo.webp` | 407,836 | `.webp` | Yes | Site generator, `hass/sitegen.py:476` |
| 25 | `reports/hass-image-1/contact-sheet-t2.jpg` | 341,653 | `.jpg` | Yes | Report, `reports/hass-image-1/README.md:13` |
| 26 | `reports/hass/hikepage-1/01-live-static-hike-page.jpg` | 326,973 | `.jpg` | Yes | Doc, `docs/hass/HIKE-PAGE.md:30` |
| 27 | `storefront-mockup/assets/store.jpg` | 326,973 | `.jpg` | Yes | Storefront page, `storefront-mockup/index.html:16` |
| 28 | `reports/avo-shop-clean-1/before-1280.png` | 323,893 | `.png` | No | No match in the scan below |
| 29 | `storefront-mockup/assets/trails/point-buchon-coast.webp` | 303,016 | `.webp` | Yes | Doc, `docs/hass/HIKE-PAGE.md:45`; site generator, `hass/sitegen.py:475` |
| 30 | `storefront-mockup/mobile-visual-390-hero.png` | 280,397 | `.png` | No | No match in the scan below |
| 31 | `storefront-mockup/catalog-only-hero-mobile.png` | 273,354 | `.png` | Yes | Documented screenshot family, `storefront-mockup/README.md:31` (`catalog-only-*.png`) |
| 32 | `storefront-mockup/mobile-visual-375-hero.png` | 270,694 | `.png` | No | No match in the scan below |
| 33 | `reports/avo-shop-clean-1/after-1280.png` | 267,710 | `.png` | No | No match in the scan below |
| 34 | `storefront-mockup/archive/commerce-preview/qa/evidence/mobile-visual-390-boxes.png` | 249,965 | `.png` | Yes | Archive-location test, `hass/tests/test_qa_scripts_live.py:8` and `hass/tests/test_qa_scripts_live.py:26–28` |
| 35 | `reports/avo-specials-1/specials-phone-top.png` | 245,392 | `.png` | Yes | QA output filename, `hass/tests/specials_page.cjs:33` |
| 36 | `storefront-mockup/assets/michael.jpg` | 238,470 | `.jpg` | Yes | Storefront page, `storefront-mockup/hike/index.html:19` |
| 37 | `storefront-mockup/archive/commerce-preview/qa/evidence/mobile-visual-375-boxes.png` | 237,784 | `.png` | Yes | Archive-location test, `hass/tests/test_qa_scripts_live.py:8` and `hass/tests/test_qa_scripts_live.py:26–28` |
| 38 | `storefront-mockup/assets/logo.png` | 222,924 | `.png` | Yes | Site publish test, `hass/tests/test_publish.py:47` |
| 39 | `storefront-mockup/image-review-9.jpg` | 217,881 | `.jpg` | Yes | Computed QA output name, `storefront-mockup/image-qa.cjs:2` |
| 40 | `storefront-mockup/image-review-1.jpg` | 215,887 | `.jpg` | Yes | Computed QA output name, `storefront-mockup/image-qa.cjs:2` |

**Scan receipt (2026-11-21):** 1,468 eligible tracked text sources. Paths came from `git ls-tree -r -l -z origin/main`. Before requesting any source blob, the scan excluded R2 names, standard build/cache paths, sensitive-looking locations and other names (handoff, deployment, inventory intake, commerce evidence, host/config/state, credentials and logs/archives). It scanned only regular files with HTML, Markdown, reStructuredText, text, CSS/SCSS, JS/TS, Python or shell extensions, plus Makefiles, `package.json` and workflow YAML. It looked for case-sensitive full paths, source-relative paths, unambiguous suffixes or standalone unique basenames, with URL escapes decoded. Module imports, README output globs, the image review template and the commerce `npm ci` input were checked separately. One source anchor per positive suffices; there is no content scan of JSON datasets, media or ignored paths, and no attempt to resolve arbitrary runtime paths or external links.

## R2. Private-looking tracked names

Case-insensitive path screen (including directory names): substrings `backup`, `dump`, `token`, `secret`, `credential`, `participant`, `community`; delimited words `key`, `keys`, `env`, `runtime`, `private`; common SSH key basenames; suffixes `.db`, `.sqlite` (including numbered and sidecar forms), `.env`, `.pem`, `.key`, `.p12`, `.pfx`. The deliberately broad screen also catches code, docs, tests and examples by name. No listed file was opened. The table gives only paths, blob sizes and ignore-rule evidence, not a finding of actual exposure.

Reproduce from the tree command in R1 and feed the matching paths to `git -c core.excludesFile=/dev/null check-ignore --no-index -v -n --stdin` in a checkout at the base. `--no-index` asks how the rules would treat an untracked path; ignore rules do not remove tracked files. The only rule result was the exception at `.gitignore:6`, overriding `.gitignore:4–5`; all other rows had no effective rule. For comparison, `.gitignore:2–10` covers the root community-data and handoff-backup locations, env files, `.sqlite3` and sidecars, `.db`, and `.runtime` directories; it does not cover generic `.sqlite` or `.pem` names. `commerce/.gitignore:1–6` adds commerce-local rules. Neither current rule coverage nor an exception tells us what rules existed when a file was added.

| Tracked path | Bytes | Matching ignore rule |
| --- | --- | --- |
| `.github/actions/test-env/action.yml` | 2,782 | None |
| `.github/actions/test-env/install-playwright.sh` | 3,237 | None |
| `commerce/.env.example` | 358 | `.gitignore:6` (`!.env.example`; exception) |
| `commerce/scripts/backup.mjs` | 1,139 | None |
| `commerce/scripts/private-media-smoke.mjs` | 2,395 | None |
| `commerce/storefront/next-env.d.ts` | 288 | None |
| `deploy/hass/hass-backup.service` | 323 | None |
| `deploy/hass/hass-backup.timer` | 162 | None |
| `docs/hass/RUNTIME-RELEASE.md` | 6,500 | None |
| `hass/clover/credential.py` | 7,753 | None |
| `hass/content/community.json` | 2,663 | None |
| `hass/npp/private_numbers.py` | 7,898 | None |
| `hass/runtime_release.py` | 16,239 | None |
| `hass/statebackup.py` | 41,846 | None |
| `hass/tests/chaos/tapes/edit-cost-qty-private.json` | 2,592 | None |
| `hass/tests/fixtures/qa_env_driver.cjs` | 209 | None |
| `hass/tests/npp/cases/case-13-glue-private-numbers.json` | 3,293 | None |
| `hass/tests/test_bridge_photos_metadata_keys.py` | 4,428 | None |
| `hass/tests/test_clover_credential.py` | 9,254 | None |
| `hass/tests/test_clover_credential_parent.py` | 6,803 | None |
| `hass/tests/test_community_email_controls.py` | 8,180 | None |
| `hass/tests/test_health_backup_content.py` | 4,889 | None |
| `hass/tests/test_health_backup_verify.py` | 8,965 | None |
| `hass/tests/test_install_backup_receipt.py` | 7,432 | None |
| `hass/tests/test_install_private_files.py` | 7,688 | None |
| `hass/tests/test_install_runtime_readback.py` | 7,589 | None |
| `hass/tests/test_interpreter_prompt_community.py` | 11,498 | None |
| `hass/tests/test_itemstd_duplicate_keys.py` | 2,710 | None |
| `hass/tests/test_nl_prep_hours_day_tokens.py` | 5,932 | None |
| `hass/tests/test_npp_private_numbers.py` | 3,870 | None |
| `hass/tests/test_pilot_private_scan.py` | 5,250 | None |
| `hass/tests/test_preview_write_private.py` | 4,783 | None |
| `hass/tests/test_qa_env.py` | 10,648 | None |
| `hass/tests/test_runtime_release.py` | 22,018 | None |
| `hass/tests/test_statebackup.py` | 18,428 | None |
| `hass/tests/test_statebackup_atomic.py` | 7,990 | None |
| `hass/tests/test_statebackup_bundle.py` | 9,041 | None |
| `hass/tests/test_statebackup_clover.py` | 3,218 | None |
| `hass/tests/test_statebackup_commit.py` | 6,748 | None |
| `hass/tests/test_statebackup_config_shape.py` | 4,400 | None |
| `hass/tests/test_statebackup_config_size.py` | 4,181 | None |
| `hass/tests/test_statebackup_content.py` | 10,045 | None |
| `hass/tests/test_statebackup_diff.py` | 8,829 | None |
| `hass/tests/test_statebackup_drill.py` | 9,449 | None |
| `hass/tests/test_statebackup_exact_modes.py` | 1,970 | None |
| `hass/tests/test_statebackup_inbox.py` | 7,886 | None |
| `hass/tests/test_statebackup_list.py` | 7,182 | None |
| `hass/tests/test_statebackup_manifest_read.py` | 8,802 | None |
| `hass/tests/test_statebackup_media.py` | 12,263 | None |
| `hass/tests/test_statebackup_paused.py` | 7,530 | None |
| `hass/tests/test_statebackup_restore_atomic.py` | 5,615 | None |
| `hass/tests/test_statebackup_worktree_binding.py` | 6,818 | None |
| `hass/tests/test_statebackup_worktree_nul.py` | 5,212 | None |
| `hass/tests/test_stock_single_token_references.py` | 4,542 | None |
| `hass/tests/test_tracked_private.py` | 5,345 | None |
| `reports/hermes-handoff/backup-community.py` | 1,117 | None |
| `reports/hiking-club/map-private-installation-20261027.json` | 1,438 | None |
| `scripts/hass/install_backup_receipt.py` | 3,415 | None |
| `scripts/hass/install_private_files.py` | 3,116 | None |
| `scripts/hass/install_runtime_readback.py` | 5,810 | None |
| `scripts/hass/pilot_private_scan.py` | 4,545 | None |
| `storefront-mockup/community-api-QA.json` | 346 | None |
| `storefront-mockup/community-hikes-desktop.png` | 134,205 | None |
| `storefront-mockup/community-hikes-mobile.png` | 77,036 | None |
| `storefront-mockup/community-newsletter-mobile.png` | 57,891 | None |
| `storefront-mockup/community-qa.py` | 12,785 | None |
| `storefront-mockup/community-server.py` | 9,001 | None |
| `storefront-mockup/community-ui-QA.json` | 453 | None |
| `storefront-mockup/community-ui-qa.cjs` | 52,595 | None |
| `storefront-mockup/community.js` | 26,602 | None |
| `storefront-mockup/community.json` | 2,617 | None |
| `storefront-mockup/qa-env.cjs` | 2,988 | None |

## R3. Same name and size in different directories

From `git ls-tree -r -l -z origin/main`, group the blob rows by the exact, case-sensitive basename and byte size. List every group with two or more paths. Groups below are by name only. This does not look for files copied under different names or decide whether separate paths are intentional.

| Basename | Tracked paths |
| --- | --- |
| `bag-bench-small.jpg` | `hass/tests/fixtures/skills-acceptance/photos/bag-bench-small.jpg`<br>`reports/hass/newitem-1/synthetic/bag-bench-small.jpg` |
| `bag-red-cloth.jpg` | `hass/tests/fixtures/skills-acceptance/photos/bag-red-cloth.jpg`<br>`reports/hass/newitem-1/synthetic/bag-red-cloth.jpg` |
| `bottle-bench-png.png` | `hass/tests/fixtures/skills-acceptance/photos/bottle-bench-png.png`<br>`reports/hass/newitem-1/synthetic/bottle-bench-png.png` |
| `bottle-grey-wall-tilted.jpg` | `hass/tests/fixtures/skills-acceptance/photos/bottle-grey-wall-tilted.jpg`<br>`reports/hass/newitem-1/synthetic/bottle-grey-wall-tilted.jpg` |
| `index.html` | `storefront-mockup/about/index.html`<br>`storefront-mockup/faq/index.html`<br>`storefront-mockup/getting-here/index.html`<br>`storefront-mockup/policies/index.html` |
| `jar-cutout-alpha.png` | `hass/tests/fixtures/skills-acceptance/photos/jar-cutout-alpha.png`<br>`reports/hass/newitem-1/synthetic/jar-cutout-alpha.png` |
| `jar-dark-wood.jpg` | `hass/tests/fixtures/skills-acceptance/photos/jar-dark-wood.jpg`<br>`reports/hass/newitem-1/synthetic/jar-dark-wood.jpg` |
| `jar-phone-rotated.jpg` | `hass/tests/fixtures/skills-acceptance/photos/jar-phone-rotated.jpg`<br>`reports/hass/newitem-1/synthetic/jar-phone-rotated.jpg` |
| `jar-white-sheet.jpg` | `hass/tests/fixtures/skills-acceptance/photos/jar-white-sheet.jpg`<br>`reports/hass/newitem-1/synthetic/jar-white-sheet.jpg` |

## R4. Ranked gaps

1. **Private-looking data names deserve review before disk savings.** R2 includes community JSON, community QA outputs and a private-labelled installation report by name. No effective ignore rule covers those paths; several other hits are plainly source/test-shaped names. Check any actual data or retention question through the authorized owner, not by opening those files in this audit. The `.sqlite`/`.pem` coverage gaps are prospective; there were no tracked matches for those suffixes (R2; `.gitignore:1–10`).
2. **Generated QA and review images are mixed in with site assets.** R1 documents screenshot outputs, a generated review sheet and test-only references alongside actual page assets. A names-only filter for directory components `build`, `dist`, `out`, `coverage`, `node_modules`, `.next`, `.medusa`, `__pycache__`, `.runtime` or suffixes `.map`, `.pyc`, `.pyo` found zero tracked paths (2026-11-21 tree receipt). It does not catch outputs saved in normal source or report directories, and the historical commerce lockfile is an npm input, not disposable build output (`commerce/README.md:13`).
3. **Duplicate names and sizes are leads, not removal candidates.** R3 spans both test/report artwork and distinct storefront routes. Keep deployment roles, provenance and retention decisions separate from path/size similarity (`AGENTS.md:14–16`).

**Buildable follow-up:** None proposed from this evidence. The pass establishes an inventory and reference leads, not a privacy incident, evidence expiry or a safe cleanup. No tracked file was removed, moved, regenerated, or checked against the live site.
