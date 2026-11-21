# Reports inventory — AVO1203-13

| Check | Result at pinned main |
| --- | --- |
| R1: Tracked reports and evidence files | 160 files; last commit dates 2026-10-20 through 2026-11-18 |
| R2: Individual file references outside `reports/` | 84 named, linked or constructed; 76 without a confirmed file-specific reference (23 folder/name-only, 53 with no file evidence found) |
| R2: Clickable links | One explicit Markdown link found; no storefront page link found in the static scan |
| R3: Total blob bytes | 6,762,971 |
| R4: Recommendation | Keep this as a dated snapshot; no build unit needed now |

Read-only check on 2026-11-21. Fresh `origin/main` matched `37feae1dc5efa6968f90d17a1eda6daed29afd4a`. `AGENTS.md:3–5,13–17` identifies current versus historical source and the evidence limits. `reports/audit-1121/` is excluded, including this index. The brief’s `reports/hass-npp/G-QUESTIONS.md` is absent at that same baseline; `git ls-tree -r --name-only <base> -- '*G-QUESTIONS*'` returned no path. No conclusions were taken from that missing file.

## R1. Every tracked file

Bytes are committed blob sizes, not disk allocation. The date is the last committer date for that exact path (no rename following), not the date the report was prepared or its findings rechecked. A quoted first heading uses the file’s own line number; role labels replace personal names and HTML line breaks are flattened. `— /` means no applicable heading was extracted; the short topic is inferred from the path, not the contents. Paths are relative to `reports/` in this table.

`Link` = clickable link; `Ref` = file mention or code/test reference (not necessarily a read); `Output` = file produced by a checked-in naming rule; `Name only` = matching generated filename with a caller-chosen output directory; `Folder` = pointer to the enclosing evidence folder, not to the individual file. One witness per type is shown. None of these labels proves deployment.

| Path under `reports/` | Bytes | Last commit | First heading / topic | Reference witness (R2) |
| --- | --- | --- | --- | --- |
| `avo-shop-clean-1/after-1280.png` | 267,710 | 2026-11-08 | — / Shop cleanup screenshot: after 1280 | None found |
| `avo-shop-clean-1/after-390.png` | 84,510 | 2026-11-08 | — / Shop cleanup screenshot: after 390 | None found |
| `avo-shop-clean-1/before-1280.png` | 323,893 | 2026-11-08 | — / Shop cleanup screenshot: before 1280 | None found |
| `avo-shop-clean-1/before-390.png` | 62,894 | 2026-11-08 | — / Shop cleanup screenshot: before 390 | None found |
| `avo-specials-1/specials-desktop.png` | 33,400 | 2026-11-08 | — / Specials screenshot: specials desktop | Name only: `hass/tests/specials_page.cjs:10,32–33` |
| `avo-specials-1/specials-phone-top.png` | 245,392 | 2026-11-08 | — / Specials screenshot: specials phone top | Name only: `hass/tests/specials_page.cjs:10,32–33` |
| `catalog-card-update-20261028.json` | 3,054 | 2026-10-28 | — / catalog card update 20261028 | Ref: `BUILD_LEDGER.md:584` |
| `catalog-shelves-2026-11.md` | 24,654 | 2026-11-05 | L1: Catalog shelves: decisions for [shop owner] (2026-11) | None found |
| `hass-chaos/CHAOS-REPORT.md` | 36,225 | 2026-11-17 | L1: HASS-CHAOS-1: drunk-owner test of Hass (2026-11-17) | None found |
| `hass-chaos/FIX-PLAN.md` | 10,794 | 2026-11-17 | L1: HASS-CHAOS-1 fix plan (ordered, card-ready) | Ref: `hass/tests/test_chaos_suite.py:4` |
| `hass-chaos/cards/approve-yes-please-t2.png` | 26,629 | 2026-11-17 | — / Chaos test card: approve yes please t2 | None found |
| `hass-chaos/cards/edit-no-wait-t2.png` | 25,633 | 2026-11-17 | — / Chaos test card: edit no wait t2 | None found |
| `hass-chaos/cards/edit-source-miners-t2.png` | 31,479 | 2026-11-17 | — / Chaos test card: edit source miners t2 | None found |
| `hass-chaos/cards/intake-glue-caption-t1.png` | 23,118 | 2026-11-17 | — / Chaos test card: intake glue caption t1 | None found |
| `hass-chaos/cards/intake-jam-organic-t1.png` | 25,091 | 2026-11-17 | — / Chaos test card: intake jam organic t1 | None found |
| `hass-chaos/cards/intake-nonfood-candle-t1.png` | 19,256 | 2026-11-17 | — / Chaos test card: intake nonfood candle t1 | None found |
| `hass-chaos/transcripts-compact.txt` | 58,550 | 2026-11-17 | — / Chaos test evidence: transcripts compact | None found |
| `hass-chaos/transcripts-full.txt` | 116,710 | 2026-11-17 | — / Chaos test evidence: transcripts full | None found |
| `hass-chaos/transcripts-text-openers.txt` | 39,416 | 2026-11-17 | — / Chaos test evidence: transcripts text openers | None found |
| `hass-image-1/README.md` | 4,886 | 2026-11-16 | L1: HASS-IMAGE-1: photo polish test evidence | Folder: `docs/hass/NEW-ITEM-FLOW.md:81` |
| `hass-image-1/contact-sheet-t2.jpg` | 341,653 | 2026-11-16 | — / Photo polish evidence: contact sheet t2 | Folder: `docs/hass/NEW-ITEM-FLOW.md:81` |
| `hass-image-1/t2-results.json` | 1,573 | 2026-11-16 | — / Photo polish evidence: t2 results | Folder: `docs/hass/NEW-ITEM-FLOW.md:81` |
| `hass-image-1/t3-bad-samples.jpg` | 153,795 | 2026-11-16 | — / Photo polish evidence: t3 bad samples | Folder: `docs/hass/NEW-ITEM-FLOW.md:81` |
| `hass-image-1/t3-results-recolour-product.json` | 1,924 | 2026-11-16 | — / Photo polish evidence: t3 results recolour product | Folder: `docs/hass/NEW-ITEM-FLOW.md:81` |
| `hass-image-1/t3-results.json` | 18,096 | 2026-11-16 | — / Photo polish evidence: t3 results | Folder: `docs/hass/NEW-ITEM-FLOW.md:81` |
| `hass-image-1/t4-card-phone-on.png` | 194,870 | 2026-11-16 | — / Photo polish evidence: t4 card phone on | Folder: `docs/hass/NEW-ITEM-FLOW.md:81` |
| `hass-image-1/t4-card-plain-on.png` | 183,167 | 2026-11-16 | — / Photo polish evidence: t4 card plain on | Folder: `docs/hass/NEW-ITEM-FLOW.md:81` |
| `hass-image-1/t4-phone-on.json` | 881 | 2026-11-16 | — / Photo polish evidence: t4 phone on | Folder: `docs/hass/NEW-ITEM-FLOW.md:81` |
| `hass-image-1/t4-plain-on.json` | 881 | 2026-11-16 | — / Photo polish evidence: t4 plain on | Folder: `docs/hass/NEW-ITEM-FLOW.md:81` |
| `hass-image-1/t5-results.json` | 8,619 | 2026-11-16 | — / Photo polish evidence: t5 results | Folder: `docs/hass/NEW-ITEM-FLOW.md:81` |
| `hass-plan-verification-20261030.json` | 2,476 | 2026-10-30 | — / hass plan verification 20261030 | Ref: `BUILD_LEDGER.md:596` |
| `hass/APPLY-TEST-1.md` | 49,649 | 2026-11-08 | L1: HASS-APPLY-TEST-1: apply, undo and failure cases through the real chat path, on a scratch copy | None found |
| `hass/E2E-HIKE-1.md` | 21,953 | 2026-11-08 | L1: HASS-E2E-HIKE-1: add / edit / cancel a hike, end to end, on a scratch copy | None found |
| `hass/FAST-1.md` | 21,860 | 2026-11-08 | L1: HASS-FAST-1: the 👀 on receipt, per-stage timing, faster replies | None found |
| `hass/HASS-LIVE-AUDIT-1.md` | 30,196 | 2026-11-07 | L1: HASS-LIVE-AUDIT-1: what works live, a self-test, and a ranked fix plan | Ref: `workspace/candidates/AUDINV-OLD-64/BASES.json:18` |
| `hass/HIKE-FLOW-1.md` | 13,511 | 2026-11-08 | L1: HASS-HIKE-FLOW-1: a hike request must end in a draft | Ref: `docs/hass/IMPLEMENTATION.md:51` |
| `hass/HIKEPAGE-1.md` | 17,047 | 2026-11-08 | L1: HASS-HIKEPAGE-1: the full hike page, spots left and the RSVP flow (design and audit) | Ref: `docs/hass/HIKE-PAGE.md:333` |
| `hass/INTERP-OPENAI-1.md` | 12,672 | 2026-11-07 | L1: HASS-INTERP-OPENAI-1: the Hass interpreter on the idle GPU Qwen, with the CPU model as fallback | Ref: `docs/hass/IMPLEMENTATION.md:49` |
| `hass/ITEMSTD-1.md` | 21,533 | 2026-11-08 | L1: HASS-ITEMSTD-1: the item standard, measured picture standard, catalog audit and the ask-[shop owner] flow | Ref: `docs/hass/ITEM-STANDARD.md:1` |
| `hass/LIVE-PLAN-1.md` | 19,642 | 2026-11-08 | L1: HASS-LIVE-PLAN-1: how an approved chat change reaches the live site | Ref: `docs/hass/PUBLISHING.md:73` |
| `hass/LIVE-STEPS-G-MICHAEL.md` | 6,978 | 2026-11-08 | L1: Going live: the steps only [project owner] and [shop owner] can do | Ref: `docs/hass/PUBLISHING.md:74` |
| `hass/NEWITEM-1.md` | 26,742 | 2026-11-07 | L1: HASS-NEWITEM-1: new-item skill (house-style picture, description, maker) from one photo and one plain message | Ref: `hass/tests/test_newitem.py:4` |
| `hass/NL-1.md` | 3,611 | 2026-11-08 | L1: HASS-NL-1: natural-language interpreter, before and after tables | None found |
| `hass/SHELFCHECK-FLOW-1.md` | 12,501 | 2026-11-08 | L1: HASS-SHELFCHECK-FLOW-1: "mark it sold out" works; the daily shelf check is one plain question | Ref: `docs/hass/IMPLEMENTATION.md:53` |
| `hass/SKILLS-ACCEPTANCE-TEMPLATE.md` | 1,386 | 2026-11-10 | L1: Skills acceptance report template (SKILLS-SPEC 4.3, card 18) | Ref: `hass/tests/fixtures/skills-acceptance/README.md:115` |
| `hass/SKILLS-SPEC.md` | 135,313 | 2026-11-18 | L1: HASS-SKILLS-DESIGN-1: skill model, catalog and build plan for Hass and the website | Ref: `docs/hass/CLOVER.md:7` |
| `hass/STORE-TEST-1-FOR-G.md` | 8,235 | 2026-11-08 | L1: Monday at the store with [shop owner]: the one-page plan for [project owner] | None found |
| `hass/STORE-TEST-1.md` | 81,617 | 2026-11-09 | L1: HASS-STORE-TEST-1: the live test with [shop owner] at the store (Monday 2026-11-09) | Ref: `docs/hass/HIKE-PAGE.md:346` |
| `hass/TAPBACK-1.md` | 10,131 | 2026-11-08 | L1: HASS-TAPBACK-1: a real tapback on the owner's message, never a text | Ref: `mac/hass_forwarder.py:21` |
| `hass/TASKMAP-1.md` | 5,498 | 2026-11-08 | L1: HASS-TASKMAP-1 report | None found |
| `hass/VOICE-1.md` | 16,028 | 2026-11-08 | L1: HASS-VOICE-1: plain, friendly, truthful wording for [shop owner] | None found |
| `hass/catalog-gaps.json` | 148,565 | 2026-11-08 | — / catalog gaps | Ref: `docs/hass/ITEM-STANDARD.md:343` |
| `hass/fast-1/prompt-sizes.json` | 321 | 2026-11-07 | — / Timing benchmark: prompt sizes | None found |
| `hass/fast-1/prompt_sizes.py` | 1,437 | 2026-11-07 | — / Timing benchmark: prompt sizes | None found |
| `hass/fast-1/stage-bench-results.json` | 10,409 | 2026-11-07 | — / Timing benchmark: stage bench results | None found |
| `hass/fast-1/stage_bench.py` | 8,960 | 2026-11-07 | — / Timing benchmark: stage bench | None found |
| `hass/fast-1/table.py` | 1,260 | 2026-11-07 | — / Timing benchmark: table | None found |
| `hass/hass-selftest.service.candidate` | 1,100 | 2026-11-07 | — / hass selftest.service | Ref: `docs/hass/OPERATIONS.md:134` |
| `hass/hass-selftest.timer.candidate` | 415 | 2026-11-07 | — / hass selftest.timer | Ref: `docs/hass/OPERATIONS.md:134` |
| `hass/hikepage-1/01-live-static-hike-page.jpg` | 326,973 | 2026-11-08 | — / Hike page evidence: 01 live static hike page | Ref: `docs/hass/HIKE-PAGE.md:30` |
| `hass/hikepage-1/02-scratch-hike-with-api.jpg` | 164,980 | 2026-11-08 | — / Hike page evidence: 02 scratch hike with api | Ref: `docs/hass/HIKE-PAGE.md:30` |
| `hass/hikepage-1/03-topo-layer.jpg` | 51,114 | 2026-11-08 | — / Hike page evidence: 03 topo layer | Ref: `docs/hass/HIKE-PAGE.md:30` |
| `hass/hikepage-1/scratch_race.py` | 1,407 | 2026-11-08 | — / Hike page evidence: scratch race | None found |
| `hass/hikepage-1/serve_scratch_api.py` | 2,458 | 2026-11-08 | — / Hike page evidence: serve scratch api | None found |
| `hass/interp-openai-1/gpu_labels.jsonl` | 1,067 | 2026-11-07 | — / Interpreter measurement: gpu labels | None found |
| `hass/interp-openai-1/gpu_text.jsonl` | 3,442 | 2026-11-07 | — / Interpreter measurement: gpu text | None found |
| `hass/interp-openai-1/labels_summary.json` | 4,381 | 2026-11-07 | — / Interpreter measurement: labels summary | None found |
| `hass/interp-openai-1/measure.py` | 8,604 | 2026-11-07 | — / Interpreter measurement: measure | None found |
| `hass/interp-openai-1/queue.json` | 1,069 | 2026-11-07 | — / Interpreter measurement: queue | None found |
| `hass/interp-openai-1/queue.py` | 3,151 | 2026-11-07 | — / Interpreter measurement: queue | None found |
| `hass/interp-openai-1/run1_gpu_text.jsonl` | 3,707 | 2026-11-07 | — / Interpreter measurement: run1 gpu text | None found |
| `hass/interp-openai-1/run1_text_summary.json` | 14,991 | 2026-11-07 | — / Interpreter measurement: run1 text summary | None found |
| `hass/interp-openai-1/text_summary.json` | 15,374 | 2026-11-07 | — / Interpreter measurement: text summary | None found |
| `hass/itemstd-1/analyze_pictures.py.txt` | 10,102 | 2026-11-08 | — / Item standard audit: analyze pictures.py | None found |
| `hass/itemstd-1/audit_catalog.py.txt` | 16,148 | 2026-11-08 | — / Item standard audit: audit catalog.py | None found |
| `hass/itemstd-1/best-and-worst.jpg` | 181,601 | 2026-11-08 | — / Item standard audit: best and worst | Ref: `docs/hass/ITEM-STANDARD.md:71` |
| `hass/itemstd-1/build_gaps.py.txt` | 11,190 | 2026-11-08 | — / Item standard audit: build gaps.py | None found |
| `hass/itemstd-1/check_envelope.py.txt` | 3,565 | 2026-11-08 | — / Item standard audit: check envelope.py | Ref: `docs/hass/ITEM-STANDARD.md:60` |
| `hass/itemstd-1/check_voice.py.txt` | 776 | 2026-11-08 | — / Item standard audit: check voice.py | Ref: `docs/hass/ITEM-STANDARD.md:298` |
| `hass/itemstd-1/measure_pictures.py.txt` | 6,218 | 2026-11-08 | — / Item standard audit: measure pictures.py | Ref: `docs/hass/ITEM-STANDARD.md:34` |
| `hass/itemstd-1/picture-envelope.json` | 4,177 | 2026-11-08 | — / Item standard audit: picture envelope | Ref: `docs/hass/ITEM-STANDARD.md:60` |
| `hass/itemstd-1/picture-measurements.json` | 82,548 | 2026-11-08 | — / Item standard audit: picture measurements | Ref: `docs/hass/ITEM-STANDARD.md:35` |
| `hass/live-add-2/README.md` | 783 | 2026-11-09 | — / Item-add rehearsal: README | Folder: `docs/hass/NEW-ITEM-FLOW.md:86` |
| `hass/live-add-2/rehearse-output.txt` | 2,200 | 2026-11-09 | — / Item-add rehearsal: rehearse output | Folder: `docs/hass/NEW-ITEM-FLOW.md:86` |
| `hass/live-add-2/rehearse.py` | 2,856 | 2026-11-09 | — / Item-add rehearsal: rehearse | Folder: `docs/hass/NEW-ITEM-FLOW.md:86` |
| `hass/live-add-2/result-house-picture.jpg` | 18,982 | 2026-11-09 | — / Item-add rehearsal: result house picture | Folder: `docs/hass/NEW-ITEM-FLOW.md:86` |
| `hass/live-add-2/sample-jar-white-sheet.jpg` | 30,583 | 2026-11-09 | — / Item-add rehearsal: sample jar white sheet | Folder: `docs/hass/NEW-ITEM-FLOW.md:86` |
| `hass/newitem-1/before-after.png` | 913,017 | 2026-11-07 | — / New-item demo: before after | Output: `hass/newitem_demo.py:19,72–73` |
| `hass/newitem-1/drafts.json` | 7,210 | 2026-11-07 | — / New-item demo: drafts | Output: `hass/newitem_demo.py:19,72–73` |
| `hass/newitem-1/preview/bag-bench-small-after-desktop.png` | 64,788 | 2026-11-07 | — / Shelf preview: bag bench small after desktop | Output: `hass/newitem_preview.py:39,89–106,126–137` |
| `hass/newitem-1/preview/bag-bench-small-after.png` | 44,588 | 2026-11-07 | — / Shelf preview: bag bench small after | Output: `hass/newitem_preview.py:39,89–106,126–137` |
| `hass/newitem-1/preview/bag-bench-small-before-desktop.png` | 62,506 | 2026-11-07 | — / Shelf preview: bag bench small before desktop | Output: `hass/newitem_preview.py:39,89–106,126–137` |
| `hass/newitem-1/preview/bag-bench-small-before.png` | 42,176 | 2026-11-07 | — / Shelf preview: bag bench small before | Output: `hass/newitem_preview.py:39,89–106,126–137` |
| `hass/newitem-1/preview/bottle-grey-wall-tilted-after-desktop.png` | 60,212 | 2026-11-07 | — / Shelf preview: bottle grey wall tilted after desktop | Output: `hass/newitem_preview.py:39,89–106,126–137` |
| `hass/newitem-1/preview/bottle-grey-wall-tilted-after.png` | 51,411 | 2026-11-07 | — / Shelf preview: bottle grey wall tilted after | Output: `hass/newitem_preview.py:39,89–106,126–137` |
| `hass/newitem-1/preview/bottle-grey-wall-tilted-before-desktop.png` | 57,201 | 2026-11-07 | — / Shelf preview: bottle grey wall tilted before desktop | Output: `hass/newitem_preview.py:39,89–106,126–137` |
| `hass/newitem-1/preview/bottle-grey-wall-tilted-before.png` | 49,483 | 2026-11-07 | — / Shelf preview: bottle grey wall tilted before | Output: `hass/newitem_preview.py:39,89–106,126–137` |
| `hass/newitem-1/preview/jar-white-sheet-after-desktop.png` | 67,235 | 2026-11-07 | — / Shelf preview: jar white sheet after desktop | Output: `hass/newitem_preview.py:39,89–106,126–137` |
| `hass/newitem-1/preview/jar-white-sheet-after.png` | 50,115 | 2026-11-07 | — / Shelf preview: jar white sheet after | Output: `hass/newitem_preview.py:39,89–106,126–137` |
| `hass/newitem-1/preview/jar-white-sheet-before-desktop.png` | 55,678 | 2026-11-07 | — / Shelf preview: jar white sheet before desktop | Output: `hass/newitem_preview.py:39,89–106,126–137` |
| `hass/newitem-1/preview/jar-white-sheet-before.png` | 38,485 | 2026-11-07 | — / Shelf preview: jar white sheet before | Output: `hass/newitem_preview.py:39,89–106,126–137` |
| `hass/newitem-1/preview/preview.json` | 10,080 | 2026-11-07 | — / Shelf preview: preview | Output: `hass/newitem_preview.py:39,89–106,126–137` |
| `hass/newitem-1/rendered/bag-bench-small.jpg` | 15,315 | 2026-11-07 | — / Demo render: bag bench small | Output: `hass/newitem_demo.py:19,48–55` |
| `hass/newitem-1/rendered/bag-red-cloth.jpg` | 47,525 | 2026-11-07 | — / Demo render: bag red cloth | Ref: `hass/tests/test_newitem.py:467–476`; Output: `hass/newitem_demo.py:19,48–55` |
| `hass/newitem-1/rendered/bottle-bench-png.jpg` | 13,103 | 2026-11-07 | — / Demo render: bottle bench png | Output: `hass/newitem_demo.py:19,48–55` |
| `hass/newitem-1/rendered/bottle-grey-wall-tilted.jpg` | 18,948 | 2026-11-07 | — / Demo render: bottle grey wall tilted | Ref: `hass/tests/test_newitem.py:467–476`; Output: `hass/newitem_demo.py:19,48–55` |
| `hass/newitem-1/rendered/jar-cutout-alpha.jpg` | 17,835 | 2026-11-07 | — / Demo render: jar cutout alpha | Output: `hass/newitem_demo.py:19,48–55` |
| `hass/newitem-1/rendered/jar-dark-wood.jpg` | 60,326 | 2026-11-07 | — / Demo render: jar dark wood | Ref: `hass/tests/test_newitem.py:467–476`; Output: `hass/newitem_demo.py:19,48–55` |
| `hass/newitem-1/rendered/jar-phone-rotated.jpg` | 16,736 | 2026-11-07 | — / Demo render: jar phone rotated | Ref: `hass/tests/test_newitem.py:467–476`; Output: `hass/newitem_demo.py:19,48–55` |
| `hass/newitem-1/rendered/jar-white-sheet.jpg` | 18,982 | 2026-11-07 | — / Demo render: jar white sheet | Ref: `hass/tests/test_newitem.py:467–476`; Output: `hass/newitem_demo.py:19,48–55` |
| `hass/newitem-1/synthetic/bag-bench-small.jpg` | 7,364 | 2026-11-07 | — / Synthetic input: bag bench small | Ref: `hass/tests/fixtures/skills/item_add/item.add.jsonl:8`; Output: `hass/newitem_demo.py:19,48–53` |
| `hass/newitem-1/synthetic/bag-red-cloth.jpg` | 78,714 | 2026-11-07 | — / Synthetic input: bag red cloth | Ref: `hass/tests/fixtures/skills/item_add/item.add.jsonl:11`; Output: `hass/newitem_demo.py:19,48–53` |
| `hass/newitem-1/synthetic/bottle-bench-png.png` | 26,768 | 2026-11-07 | — / Synthetic input: bottle bench png | Ref: `hass/tests/fixtures/demo/g-demo.jsonl:5`; Output: `hass/newitem_demo.py:19,48–53` |
| `hass/newitem-1/synthetic/bottle-grey-wall-tilted.jpg` | 28,082 | 2026-11-07 | — / Synthetic input: bottle grey wall tilted | Ref: `hass/tests/fixtures/skills/item_add/item.add.jsonl:4`; Output: `hass/newitem_demo.py:19,48–53` |
| `hass/newitem-1/synthetic/jar-cutout-alpha.png` | 5,978 | 2026-11-07 | — / Synthetic input: jar cutout alpha | Ref: `hass/tests/fixtures/skills/item_add/item.add.jsonl:7`; Output: `hass/newitem_demo.py:19,48–53` |
| `hass/newitem-1/synthetic/jar-dark-wood.jpg` | 136,764 | 2026-11-07 | — / Synthetic input: jar dark wood | Ref: `hass/tests/fixtures/skills/item_add/item.add.jsonl:27`; Output: `hass/newitem_demo.py:19,48–53` |
| `hass/newitem-1/synthetic/jar-phone-rotated.jpg` | 49,038 | 2026-11-07 | — / Synthetic input: jar phone rotated | Ref: `hass/tests/fixtures/skills/item_add/item.add.jsonl:10`; Output: `hass/newitem_demo.py:19,48–53` |
| `hass/newitem-1/synthetic/jar-white-sheet.jpg` | 30,583 | 2026-11-07 | — / Synthetic input: jar white sheet | Ref: `hass/tests/fixtures/skills/item_add/item.add.jsonl:1`; Output: `hass/newitem_demo.py:19,48–53` |
| `hass/rehearse_live_policy.out` | 2,630 | 2026-11-09 | — / rehearse live policy | Ref: `docs/hass/PUBLISHING.md:89` |
| `hass/rehearse_live_policy.py` | 6,929 | 2026-11-09 | — / rehearse live policy | Ref: `docs/hass/PUBLISHING.md:89` |
| `hass/rehearse_owners_transport.out` | 11,911 | 2026-11-09 | — / rehearse owners transport | None found |
| `hass/rehearse_owners_two.out` | 6,923 | 2026-11-09 | — / rehearse owners two | None found |
| `hass/rehearse_owners_two.py` | 7,990 | 2026-11-09 | — / rehearse owners two | None found |
| `held-cheese-recall-2026-11.md` | 10,384 | 2026-11-04 | L3: Held cheeses: official recall evidence (November 2026) | Ref: `BUILD_LEDGER.md:3009` |
| `hermes-handoff/Avocado_Shack_Hermes_Handoff_Ready.html` | 4,066 | 2026-10-20 | L1: Ready for Hermes. | Ref: `BUILD_LEDGER.md:540` |
| `hermes-handoff/Avocado_Shack_Hermes_Handoff_Report.html` | 16,207 | 2026-10-20 | L1: Where everything lives. / Preparing the Hermes handoff. | Ref: `BUILD_LEDGER.md:530` |
| `hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt` | 2,375 | 2026-10-20 | L1: AVOCADO SHACK — CURRENT BUSINESS CONTEXT FOR HERMES | Link: `docs/hass/HERMES_START.md:9`; Ref: `HERMES_HANDOFF.txt:85` |
| `hermes-handoff/archive-verification.json` | 863 | 2026-10-20 | — / Handoff evidence or helper: archive verification | Folder: `BUILD_LEDGER.md:6` |
| `hermes-handoff/avocado-shack-sandbox.service` | 474 | 2026-10-20 | — / Handoff evidence or helper: avocado shack sandbox | Ref: `BUILD_LEDGER.md:538` |
| `hermes-handoff/backup-community.py` | 1,117 | 2026-10-20 | — / Handoff evidence or helper: backup community | Ref: `HERMES_HANDOFF.txt:97` |
| `hermes-handoff/finish-handoff-report.py` | 5,772 | 2026-10-20 | — / Handoff evidence or helper: finish handoff report | Folder: `BUILD_LEDGER.md:6` |
| `hermes-handoff/inventory-evidence.json` | 880 | 2026-10-20 | — / Handoff evidence or helper: inventory evidence | Ref: `BUILD_LEDGER.md:530` |
| `hermes-handoff/migration-api-verification.json` | 402 | 2026-10-20 | — / Handoff evidence or helper: migration api verification | Folder: `BUILD_LEDGER.md:6` |
| `hermes-handoff/migration-verification.json` | 4,045 | 2026-10-20 | — / Handoff evidence or helper: migration verification | Ref: `HERMES_HANDOFF.txt:108` |
| `hermes-handoff/verify-archive.py` | 1,454 | 2026-10-20 | — / Handoff evidence or helper: verify archive | Folder: `BUILD_LEDGER.md:6` |
| `hermes-handoff/verify-migration.py` | 4,249 | 2026-10-20 | — / Handoff evidence or helper: verify migration | Folder: `BUILD_LEDGER.md:6` |
| `hiking-club/TRAIL_MAP_SOURCES.txt` | 5,504 | 2026-10-27 | L1: POINT BUCHON MAP — SOURCES AND METHOD | Ref: `BUILD_LEDGER.md:563` |
| `hiking-club/build-trail-data.py` | 6,225 | 2026-10-27 | — / Hiking map or catalog QA: build trail data | Ref: `docs/hass/HIKE-LOOKUP.md:54` |
| `hiking-club/catalog-hike-installed-20261028.json` | 1,407 | 2026-10-28 | — / Hiking map or catalog QA: catalog hike installed 20261028 | Ref: `BUILD_LEDGER.md:578` |
| `hiking-club/catalog-hike-qa-20261028.json` | 5,263 | 2026-10-28 | — / Hiking map or catalog QA: catalog hike qa 20261028 | Ref: `BUILD_LEDGER.md:576` |
| `hiking-club/map-private-installation-20261027.json` | 1,438 | 2026-10-27 | — / Hiking map or catalog QA: map private installation 20261027 | Ref: `BUILD_LEDGER.md:569` |
| `hiking-club/map-qa.cjs` | 8,989 | 2026-10-27 | — / Hiking map or catalog QA: map qa | Ref: `storefront-mockup/README.md:63` |
| `hiking-club/map-sources/osm-trail-subset.json` | 30,058 | 2026-10-27 | — / Hiking map or catalog QA: osm trail subset | None found |
| `hiking-club/map-sources/point-buchon-aerial-export.json` | 372 | 2026-10-27 | — / Hiking map or catalog QA: point buchon aerial export | None found |
| `hiking-club/map-sources/point-buchon-elevation.json` | 19,396 | 2026-10-27 | — / Hiking map or catalog QA: point buchon elevation | None found |
| `hiking-club/map-sources/point-buchon-route.geojson` | 11,274 | 2026-10-27 | — / Hiking map or catalog QA: point buchon route | None found |
| `hiking-club/map-sources/point-buchon-topo-export.json` | 365 | 2026-10-27 | — / Hiking map or catalog QA: point buchon topo export | None found |
| `hiking-club/map-sources/route-sampling.json` | 3,794 | 2026-10-27 | — / Hiking map or catalog QA: route sampling | None found |
| `hiking-club/map-sources/usgs-elevation-service.json` | 11,127 | 2026-10-27 | — / Hiking map or catalog QA: usgs elevation service | None found |
| `hiking-club/map-upgrade-qa-20261027.json` | 3,766 | 2026-10-27 | — / Hiking map or catalog QA: map upgrade qa 20261027 | Ref: `BUILD_LEDGER.md:565` |
| `hiking-club/qa-20261027.json` | 3,450 | 2026-10-27 | — / Hiking map or catalog QA: qa 20261027 | Ref: `BUILD_LEDGER.md:552` |
| `hiking-club/route-map-sources-2026-11.md` | 15,076 | 2026-11-04 | L1: Cass Hill and Fiscalini Ranch — map source readiness (November 2026) | Ref: `BUILD_LEDGER.md:3089` |
| `hiking-club/trail-research.txt` | 2,024 | 2026-10-27 | L1: NORTH COAST HIKING CLUB — TRAIL FACTS AND SAMPLE BOUNDARIES | Ref: `storefront-mockup/README.md:60` |
| `maker-links-2026-11.md` | 12,142 | 2026-11-05 | L1: Maker website link check, November 2026 | Ref: `BUILD_LEDGER.md:3385` |
| `organic-badges-2026-11.md` | 10,661 | 2026-11-05 | L1: Organic badge evidence by product (AV1052-14) | Ref: `BUILD_LEDGER.md:3393` |
| `product-description-claims-2026-11.md` | 141,501 | 2026-11-05 | L1: Product description claims — recorded sources (AV1104-11) | None found |
| `site-a11y-2026-11.md` | 19,169 | 2026-11-18 | L1: Site accessibility audit (WCAG 2.2 AA, criteria other than contrast), November 2026 | None found |
| `site-contrast-2026-11.md` | 110,718 | 2026-11-05 | L1: Site text contrast audit, November 2026 | Ref: `BUILD_LEDGER.md:2957`; Output: `storefront-mockup/site-contrast-qa.py:219` |
| `site-copy-claims-2026-11.md` | 60,175 | 2026-11-15 | L1: Site copy claims audit, November 2026 (AV0007-08) | Ref: `BUILD_LEDGER.md:2821` |
| `unsourced-products-2026-11.md` | 9,914 | 2026-11-05 | L1: Unsourced products — worksheet for [shop owner] (2026-11) | Ref: `BUILD_LEDGER.md:3513` |

## R2. Reference gaps

### No confirmed inbound file reference

The 76 rows below have no individual repo-file reference in the scanned sources. They can still be reached by a folder pointer, referred to from another report, or used outside this clone. This is not a deletion list. In particular, `docs/hass/NEW-ITEM-FLOW.md:81,86` points to whole evidence folders; `.github/workflows/check.yml:100` and `hass/tests/test_live_add.py:70` name the handoff directory. No individual file is credited for those directory hits.

- **(root)** (3): `catalog-shelves-2026-11.md`, `product-description-claims-2026-11.md`, `site-a11y-2026-11.md`.
- **avo-shop-clean-1** (4): `after-1280.png`, `after-390.png`, `before-1280.png`, `before-390.png`.
- **avo-specials-1** (2): `specials-desktop.png`, `specials-phone-top.png`.
- **hass** (34): `APPLY-TEST-1.md`, `E2E-HIKE-1.md`, `FAST-1.md`, `NL-1.md`, `STORE-TEST-1-FOR-G.md`, `TASKMAP-1.md`, `VOICE-1.md`, `fast-1/prompt-sizes.json`, `fast-1/prompt_sizes.py`, `fast-1/stage-bench-results.json`, `fast-1/stage_bench.py`, `fast-1/table.py`, `hikepage-1/scratch_race.py`, `hikepage-1/serve_scratch_api.py`, `interp-openai-1/gpu_labels.jsonl`, `interp-openai-1/gpu_text.jsonl`, `interp-openai-1/labels_summary.json`, `interp-openai-1/measure.py`, `interp-openai-1/queue.json`, `interp-openai-1/queue.py`, `interp-openai-1/run1_gpu_text.jsonl`, `interp-openai-1/run1_text_summary.json`, `interp-openai-1/text_summary.json`, `itemstd-1/analyze_pictures.py.txt`, `itemstd-1/audit_catalog.py.txt`, `itemstd-1/build_gaps.py.txt`, `live-add-2/README.md`, `live-add-2/rehearse-output.txt`, `live-add-2/rehearse.py`, `live-add-2/result-house-picture.jpg`, `live-add-2/sample-jar-white-sheet.jpg`, `rehearse_owners_transport.out`, `rehearse_owners_two.out`, `rehearse_owners_two.py`.
- **hass-chaos** (10): `CHAOS-REPORT.md`, `cards/approve-yes-please-t2.png`, `cards/edit-no-wait-t2.png`, `cards/edit-source-miners-t2.png`, `cards/intake-glue-caption-t1.png`, `cards/intake-jam-organic-t1.png`, `cards/intake-nonfood-candle-t1.png`, `transcripts-compact.txt`, `transcripts-full.txt`, `transcripts-text-openers.txt`.
- **hass-image-1** (11): `README.md`, `contact-sheet-t2.jpg`, `t2-results.json`, `t3-bad-samples.jpg`, `t3-results-recolour-product.json`, `t3-results.json`, `t4-card-phone-on.png`, `t4-card-plain-on.png`, `t4-phone-on.json`, `t4-plain-on.json`, `t5-results.json`.
- **hermes-handoff** (5): `archive-verification.json`, `finish-handoff-report.py`, `migration-api-verification.json`, `verify-archive.py`, `verify-migration.py`.
- **hiking-club** (7): `map-sources/osm-trail-subset.json`, `map-sources/point-buchon-aerial-export.json`, `map-sources/point-buchon-elevation.json`, `map-sources/point-buchon-route.geojson`, `map-sources/point-buchon-topo-export.json`, `map-sources/route-sampling.json`, `map-sources/usgs-elevation-service.json`.

### Mentions of paths absent from the pinned tree

These are textual path mentions, not all broken links. Paths shown are normalized to the `reports/` suffix only; the original prefix determines whether a path belongs to runtime state, another checkout, or this repository. Ranges below span the first and last matching lines, not necessarily every line.

| Absent path | Where | Meaning |
| --- | --- | --- |
| `reports/hass-npp/PIPELINE-DESIGN.md` | `docs/hass/skills/hass-npp-maintain/SKILL.md:11`; `hass/tests/npp/cases/FORMAT.md:3` | Design cited by the maintenance skill and offline case format; missing from main. |
| `reports/hass/SEC-1.md` | `hass/maker_site.py:9`; `hass/tests/test_maker_site_sec3.py:1`; `hass/tests/test_sec2_late_yes.py:1`; `hass/tests/test_sec2_live_gate.py:1`; `hass/tests/test_sec2_release.py:1` | Review evidence cited by code and test comments; no claim that those tests read this file. |
| `reports/hass/QA-1.md` | `hass/tests/fixtures/skills/README.md:103`; `hass/tests/test_qa1_fixes.py:1` | Explicitly described as an external agent-work report. |
| `reports/hass/CLOUD-3.md` | `docs/hass/TASKMAP.md:905` | Planned deliverable in a task table, not an existing-file assertion. |
| `reports/hass-demo-clover/02-DEMO-PLAN.md` | `hass/tests/fixtures/demo/g-demo.jsonl:1`; `scripts/hass/demo_rehearsal.py:7` | Demo-plan provenance in a fixture and script comment. |
| `reports/backlog-plan-1/results/AVB-05/receipts` | `hass/tests/fixtures/skills/qa1/owner-battery.jsonl:27–35` | Receipt directory mentioned in QA fixture provenance, not a file input established by this scan. |
| `reports/hass-npp/metrics.tsv` | `docs/hass/skills/hass-npp-review/SKILL.md:20` | External metrics file, not a checkout-relative link. |
| `reports/YYYY-MM-DD-stock.md` | `docs/hass/CLOVER.md:22` | Dated Clover state output; the same line documents the mismatch variant. |
| `reports/2026-11-10-mismatch.md` | `hass/tests/test_clover_reports.py:153` | Dated Clover state output in a test. |
| `reports/site-stock-totals.json` | `docs/hass/CLOVER.md:126`; `hass/tests/test_stock_site.py:306` | Clover state output, also asserted under a scratch state root. |
| `reports/link-suggest.md` | `docs/hass/CLOVER.md:242`; `hass/clover/cli.py:223`; `hass/tests/test_clover_links.py:116–118` | Clover state output, not repo evidence. |
| `reports/report.shelf.jsonl` | `docs/hass/skills/reports.md:70`; `hass/skills/reports.py:163`; `hass/tests/test_skills_reports.py:82`; `workspace/candidates/AUDINV-OLD-63/BASES.json:1` | Hass state log, not a missing tracked report. |
| `reports/answer.site.jsonl` | `hass/skills/reports.py:365`; `workspace/candidates/AUDINV-OLD-63/BASES.json:1` | Hass state log, not a missing tracked report. |
| `reports/nope.md` | `hass/tests/test_ledger_rf1120.py:273` | Intentional negative fixture. |
| `reports/hermes-handoff/private-*` | `.gitignore:30` | Ignore glob, not a missing report. |
| `reports/hermes-handoff/transfer-*.log` | `.gitignore:29` | Ignore glob, not a missing report. |

The supplemental scan also found the following absent path strings in historical `workspace/candidates/` artifacts. These are provenance pointers, not shown to be missing runtime inputs or current storefront links. One example per distinct path:

- `reports/AUDIT-AVOCADO-HASS-2026-11-01.md` — `workspace/candidates/AUDINV-OLD-57/SOURCES.json:61`
- `reports/CI-WEIGHT-AUDIT-2026-11-03.md` — `workspace/candidates/AUDINV-CIW-06/SOURCES.json:9`
- `reports/QUEUE-AUDIT-APPLIED.json` — `workspace/candidates/AUDINV-FIX-041/avocado-76-decision-reconciliation.tsv:2`
- `reports/QUEUE-AUDIT.tsv` — `workspace/candidates/AUDINV-FIX-041/README.md:3`
- `reports/audit-inventory/INVENTORY.tsv` — `workspace/candidates/AUDINV-OLD-57/SOURCES.json:70`
- `reports/ci-audit-raw-avocado-shack.json` — `workspace/candidates/AUDINV-CIW-06/SOURCES.json:6`
- `reports/ci-metrics-cache/jobs.json` — `workspace/candidates/AUDINV-CIW-10/BASES.json:11`
- `reports/ci-metrics-cache/runs-avocado-shack-2026-11-13.json` — `workspace/candidates/AUDINV-CIW-10/BASES.json:9`
- `reports/ci-metrics-cache/runs-avocado-shack-2026-11-14.json` — `workspace/candidates/AUDINV-CIW-10/BASES.json:10`
- `reports/milestone-map-1/MILESTONE-MAP.tsv` — `workspace/candidates/AUDINV-FIX-041/README.md:28`
- `reports/oc-specs/AUDINV-OLD-57.md` — `workspace/candidates/AUDINV-OLD-57/SOURCES.json:95`
- `reports/oc-specs/AUDINV-OLD-58.md` — `workspace/candidates/AUDINV-OLD-58/RESULT.md:48`

The brace shorthand at `docs/hass/OPERATIONS.md:134` and `scripts/hass/live_selftest.sh:3` expands to two files that are **both present**. No missing clickable link was found by the static link scan. A missing Markdown design file cited in prose is still a discoverability problem.

## R3. Size totals

Folder totals are recursive; nested rows are included in parent rows. `(root files only)` counts files immediately under `reports/`. Kinds use the final suffix (`.py.txt` counts as `.txt`; service/timer proposals ending in `.candidate` count as `.candidate`).

| Folder under `reports/` | Files | Bytes |
| --- | --- | --- |
| `(root files only)` | 11 | 404,848 |
| `avo-shop-clean-1/` | 4 | 739,007 |
| `avo-specials-1/` | 2 | 278,792 |
| `hass-chaos/` | 11 | 412,901 |
| `hass-chaos/cards/` | 6 | 151,206 |
| `hass-image-1/` | 11 | 910,345 |
| `hass/` | 92 | 3,845,646 |
| `hass/fast-1/` | 5 | 22,387 |
| `hass/hikepage-1/` | 5 | 546,932 |
| `hass/interp-openai-1/` | 9 | 55,786 |
| `hass/itemstd-1/` | 9 | 316,325 |
| `hass/live-add-2/` | 5 | 55,404 |
| `hass/newitem-1/` | 31 | 2,146,246 |
| `hass/newitem-1/preview/` | 13 | 653,958 |
| `hass/newitem-1/rendered/` | 8 | 208,770 |
| `hass/newitem-1/synthetic/` | 8 | 363,291 |
| `hermes-handoff/` | 12 | 41,904 |
| `hiking-club/` | 17 | 129,528 |
| `hiking-club/map-sources/` | 7 | 76,386 |

| File kind | Files | Bytes |
| --- | --- | --- |
| `.candidate` | 2 | 1,515 |
| `.cjs` | 1 | 8,989 |
| `.geojson` | 1 | 11,274 |
| `.html` | 2 | 20,273 |
| `.jpg` | 22 | 1,808,996 |
| `.json` | 34 | 423,255 |
| `.jsonl` | 3 | 8,216 |
| `.md` | 34 | 983,185 |
| `.out` | 3 | 21,464 |
| `.png` | 29 | 3,136,683 |
| `.py` | 15 | 63,869 |
| `.service` | 1 | 474 |
| `.txt` | 13 | 274,778 |

Five largest, by committed bytes:

| Rank | Path | Bytes |
| --- | --- | --- |
| 1 | `reports/hass/newitem-1/before-after.png` | 913,017 |
| 2 | `reports/hass-image-1/contact-sheet-t2.jpg` | 341,653 |
| 3 | `reports/hass/hikepage-1/01-live-static-hike-page.jpg` | 326,973 |
| 4 | `reports/avo-shop-clean-1/before-1280.png` | 323,893 |
| 5 | `reports/avo-shop-clean-1/after-1280.png` | 267,710 |

## R4. Ranked gaps

1. **The NPP design citation cannot be followed in this checkout.** The maintenance skill and case format point to the same absent design, while the brief’s question file is also absent (R2; `docs/hass/skills/hass-npp-maintain/SKILL.md:11`, `hass/tests/npp/cases/FORMAT.md:3`). The canonical destination is not established here; do not infer or recreate the design or owner answers.
2. **Much of the evidence is discoverable only through the tree.** R1/R2 distinguish the one clickable link from plain-text references, generators, and folder pointers. Start with the index rather than treating an unreferenced file as disposable.
3. **Paths in different storage locations look alike.** R2 separates tracked evidence, expected state outputs, test negatives, and provenance elsewhere. A repository-wide broken-link rule that conflated these would produce false alarms.

**No build unit is needed for this snapshot.** Keep the evidence in place. A future correction to an NPP citation would first need a verified canonical destination and separate file scope; this audit neither changes links nor makes an owner decision.

## Reproduce offline

Use the pinned commit (not the audit branch) as `<base>`. For the inventory, read `git ls-tree -lr <base> -- reports` (drop `reports/audit-1121/`) and use `git log -1 --format=%cs <base> -- <path>` per row. For a heading, inspect only the opening heading of `git show <base>:<path>`: ATX or Setext outside fenced examples in Markdown, first HTML heading or opening plain-text title in the named text briefs. Do not open image, data, or transcript payloads to infer topics. To recreate R3, group those same byte rows by each ancestor folder and final extension, and sort by descending bytes for the top five.

For an R2 file witness, run `git grep -InoF -e <exact-path> -e <basename> <base> -- docs hass storefront-mockup ':(top,glob)*.md'` with the exclusions below. For missing tokens, repeat with `git grep -InoE -e '([.][.]/)*/?reports/[-a-zA-Z0-9_./*]+(\{[-a-zA-Z0-9_.,]+\}[-a-zA-Z0-9_./]+)?' <base> --` and the same source pathspecs. Compare tokens with `git ls-tree -r --name-only <base> -- reports`; use the cited lines to check prefixes, trailing sentence punctuation, extensions, short names and generated paths. The scratch replay `index_probe.py` (run as `python3 index_probe.py` beside the clone) batches these searches and repeats them over other tracked text outside `reports/` to catch extra references such as the handoff text, scripts, CI and historical workspace artifacts. `render_index.py --verify` compares the resulting index byte-for-byte with the deliverable. Both are uncommitted audit aids.

The scans skip binary files and credential-, token-, secret-, environment- and host-config-named files (`:(exclude)**/*credential*`, `:(exclude)**/*token*`, `:(exclude)**/*secret*`, `:(exclude)**/.env*`, `:(exclude)**/host.json`). The link check searched Markdown link destinations and HTML `href`/`src` text for `reports/` in tracked text outside the reports directory; no pages were rendered. Report bodies, untracked paths, external link targets, dynamically assembled paths beyond the cited code, and live systems were not inspected. A zero hit is not proof that a file has no reader.
