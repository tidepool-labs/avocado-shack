# AVO1203-15 — Dead paths in the Avocado Shack entry docs

| Check | Result |
| --- | --- |
| R1 · Paths | The current start-page links resolve. The handoff still names a checkout location, not a portable repo path. Most absent repo paths are dated commerce evidence or old deployment artifacts; one old QA path has a tracked archive match (`README.md:11–23,44`; `HERMES_HANDOFF.txt:12,60–61`; `BUILD_LEDGER.md:119–129,476,486–505`). |
| R2 · Commands | No missing tracked entry script in the current start instructions after resolving the checkout prefix. Two incomplete CLI examples: bare `--queue` needs a value, and health examples that show only an optional switch still need `--state` (`hass/README.md:159–162,206,264`; `hass/fixture_chat.py:126–135`; `hass/health.py:452–465`). |
| R3 · Current vs. historical | Current guides agree on the site tree. The handoff's “FILES TO EDIT” list conflicts with the later generated-file guidance (`AGENTS.md:3–5`; `HERMES_HANDOFF.txt:73–84`; `hass/README.md:5–15`). |
| R4 · Recommendation | One small docs follow-up: clarify editable sources and qualify old checkout examples; leave dated ledger evidence and private artifacts alone. |

Evidence: fresh clone of `tidepool-labs/avocado-shack`, checked November 21, 2026 (Pacific), `origin/main` and initial `HEAD` both `37feae1dc5efa6968f90d17a1eda6daed29afd4a`. All anchors below refer to that tree. Read the six scoped docs; `mac/README.md` is a read-only cross-check (its paths are included separately in the same inventory by anchor). The card's four exclusions were applied as stated; `git ls-tree -r --name-only origin/main -- reports/hass-npp` was empty, so this audit makes no claim to have read a checked-in G answers file. No external services, site or documented operating commands were exercised. Existence here is not a deployment, install, authorization or freshness check.

## R1. Repository path inventory

A row groups repeated mentions of the same spelling and target; commas after a filename anchor are separate line numbers. A right arrow supplies the repo-root spelling for a relative link, module, contextual basename or shortened mention. `yes` means a tracked Git file or directory; `no` is not necessarily a defect. For `no`, the last column is the closest tracked parent (`.` = repository root), except where a confirmed same-name archive match is more useful. Patterns are marked separately. The dated ledger's evidence basenames inherit the evidence folder where context establishes it; missing historical evidence is not permission to recover it. The docs' numbered features, Git refs/branches, URLs/routes (for example `/hike`), field names, executable names on `PATH` and non-path slash prose are not repo paths.

Reproduce: `git rev-parse origin/main`; `git ls-tree -r --name-only origin/main` (files); `git ls-tree -r -d --name-only origin/main` (directories). Use `git show origin/main:BUILD_LEDGER.md | nl -ba` or substitute the cited doc to recover line context. For a single literal target use `git cat-file -t origin/main:<repo-path>` (a missing path errors); for globs use `git ls-tree -r --name-only origin/main -- <parent>` and match the documented pattern against those filenames, not the checkout's untracked files.

| Doc:line | Named path → target where needed | Exists on main | Nearest tracked path if no |
| --- | --- | --- | --- |
| README.md:11; README.txt:3; BUILD_LEDGER.md:1154, 1807, 1815; HERMES_HANDOFF.txt:114 | `docs/hass/README.md` | yes | — |
| README.md:12; README.txt:5; BUILD_LEDGER.md:2167, 2529, 2531 | `docs/hass/FEATURES.md` | yes | — |
| README.md:13; README.txt:4; BUILD_LEDGER.md:602, 3121; HERMES_HANDOFF.txt:115 | `docs/hass/HERMES_START.md` | yes | — |
| README.md:14, 33; BUILD_LEDGER.md:898, 938, 970, 978, 1058, 1066, 1074, 1695, 1727, 1775, 1783, 1927, 2111, 2119, 2135, 2877, 2885, 2893, 2917, 3457, 3465, 3473, 3489, 3497, 3505 | `docs/hass/COMMANDS.md` | yes | — |
| README.md:15, 33; BUILD_LEDGER.md:1943, 2183, 2973, 3521; hass/README.md:251 | `docs/hass/PHONE_GUIDE.md` | yes | — |
| README.md:16, 33; BUILD_LEDGER.md:1154, 1194, 1943, 2175, 2893, 2949, 2973, 3489, 3521; hass/README.md:163, 265 | `docs/hass/LIMITS.md` | yes | — |
| README.md:17; BUILD_LEDGER.md:762, 778, 782, 826, 858, 918, 946, 1130, 1138, 1146, 1274, 1282, 2199, 3361; hass/README.md:165 | `docs/hass/SUPPORT.md` | yes | — |
| README.md:18 | `docs/hass/CONNECT.md` | yes | — |
| README.md:19; BUILD_LEDGER.md:1815, 2831 | `docs/hass/HANDOVER.md` | yes | — |
| README.md:20; BUILD_LEDGER.md:882, 906, 954, 1162, 1799 | `docs/hass/IMPLEMENTATION.md` | yes | — |
| README.md:21, 51; README.txt:13, 15; BUILD_LEDGER.md:4, 540, 543; AGENTS.md:3; hass/README.md:58 | `HERMES_HANDOFF.txt` | yes | — |
| README.md:22; README.txt:16; BUILD_LEDGER.md:696, 2617; HERMES_HANDOFF.txt:29, 84 | `storefront-mockup/README.md` | yes | — |
| README.md:23; README.txt:17; BUILD_LEDGER.md:3537; HERMES_HANDOFF.txt:133; AGENTS.md:4, 17; hass/README.md:221, 232, 241, 253, 277, 286 | `BUILD_LEDGER.md` | yes | — |
| README.md:32; README.txt:9; BUILD_LEDGER.md:1266, 2215 | `storefront-mockup/community-server.py` | yes | — |
| README.md:34; BUILD_LEDGER.md:606, 652, 660, 670, 680, 688, 746, 748, 756, 802, 804, 1695, 1697, 1879, 2087, 2103, 2223, 2229, 2443, 2507, 2515, 2571, 2587, 2601, 2603; hass/README.md:23, 24, 25 | `hass/sitegen.py` | yes | — |
| README.md:34, 37; README.txt:7; BUILD_LEDGER.md:2, 476; HERMES_HANDOFF.txt:17, 83; AGENTS.md:3; hass/README.md:60 | `storefront-mockup/` | yes | — |
| README.md:37; README.txt:28; HERMES_HANDOFF.txt:33; AGENTS.md:4 | `commerce/` | yes | — |
| README.md:44; HERMES_HANDOFF.txt:12 | `[legacy checkout; repository root]` → `.` | yes | — |
| README.txt:3 | `README.md` | yes | — |
| README.txt:26; BUILD_LEDGER.md:543 | `storefront README` → `storefront-mockup/README.md` | yes | — |
| BUILD_LEDGER.md:3, 543; AGENTS.md:3; hass/README.md:58 | `README.txt` | yes | — |
| BUILD_LEDGER.md:6 | `reports/hermes-handoff/` | yes | — |
| BUILD_LEDGER.md:12 | `docs/hass/INSTALL-LIVE-FIX-2.md` | yes | — |
| BUILD_LEDGER.md:74, 2254 | `hass/skills/backlog.py` | yes | — |
| BUILD_LEDGER.md:82 | `docs/hass/CLOVER.md` | yes | — |
| BUILD_LEDGER.md:86 | `hass/tests/ci_shards.py` | yes | — |
| BUILD_LEDGER.md:88, 2250, 2887 | `hass.tests.test_ci_shards` → `hass/tests/test_ci_shards.py` | yes | — |
| BUILD_LEDGER.md:94, 2272 | `hass/capabilities.py` | yes | — |
| BUILD_LEDGER.md:100 | `hass/skills/testkit.py` | yes | — |
| BUILD_LEDGER.md:103 | `planning/Avocado_Shack_Website_Build_Goal.docx` | no | `.` |
| BUILD_LEDGER.md:112 | `backend/.env` → `commerce/backend/.env` | no | `commerce/backend/` |
| BUILD_LEDGER.md:112 | `commerce/.runtime/access.txt` | no | `commerce/` |
| BUILD_LEDGER.md:119, 383 | `dictated-unit-live.log` → `commerce/evidence/dictated-unit-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:119, 367 | `photo-candidates-live.log` → `commerce/evidence/photo-candidates-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:119, 313 | `photo-orientation-heic-live.log` → `commerce/evidence/photo-orientation-heic-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:120 | `approval-stock-race-live.log` → `commerce/evidence/approval-stock-race-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:120, 292 | `photo-readback-live.log` → `commerce/evidence/photo-readback-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:121, 378 | `catalog-availability-build.log` → `commerce/evidence/catalog-availability-build.log` | no | `commerce/` |
| BUILD_LEDGER.md:121, 378 | `catalog-availability-live.log` → `commerce/evidence/catalog-availability-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:122 | `stock-race-smoke.log` → `commerce/evidence/stock-race-smoke.log` | no | `commerce/` |
| BUILD_LEDGER.md:122, 232 | `stock-receipt-restart-summary.json` → `commerce/evidence/stock-receipt-restart-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:123, 125 | `current-sample-journey.log` → `commerce/evidence/current-sample-journey.log` | no | `commerce/` |
| BUILD_LEDGER.md:123 | `late-refund-live.log` → `commerce/evidence/late-refund-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:123, 258 | `payment-webhook-summary.json` → `commerce/evidence/payment-webhook-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:125 | `customer-photo-history-live.log` → `commerce/evidence/customer-photo-history-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:126 | `current-handoff-restore.log` → `commerce/evidence/current-handoff-restore.log` | no | `commerce/` |
| BUILD_LEDGER.md:126 | `order-task-recovery-live.log` → `commerce/evidence/order-task-recovery-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:126, 361 | `paid-order-restart-summary.json` → `commerce/evidence/paid-order-restart-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:127 | `dictated-unit-unit.log` → `commerce/evidence/dictated-unit-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:127 | `private-media-live.log` → `commerce/evidence/private-media-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:127, 346 | `static-contrast-summary.json` → `commerce/evidence/static-contrast-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:127 | `worker-stock-grounding-unit.log` → `commerce/evidence/worker-stock-grounding-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:129 | `commerce/evidence` | no | `commerce/` |
| BUILD_LEDGER.md:146, 371 | `commerce/README.md` | yes | — |
| BUILD_LEDGER.md:151 | `commerce/evidence/packing-stages-smoke.log` | no | `commerce/` |
| BUILD_LEDGER.md:153 | `box-revision-guards-smoke.log` → `commerce/evidence/box-revision-guards-smoke.log` | no | `commerce/` |
| BUILD_LEDGER.md:155 | `box-intake-atomic-smoke.log` → `commerce/evidence/box-intake-atomic-smoke.log` | no | `commerce/` |
| BUILD_LEDGER.md:157 | `content-message-smoke.log` → `commerce/evidence/content-message-smoke.log` | no | `commerce/` |
| BUILD_LEDGER.md:159 | `hours-message-smoke.log` → `commerce/evidence/hours-message-smoke.log` | no | `commerce/` |
| BUILD_LEDGER.md:161 | `activity-smoke.log` → `commerce/evidence/activity-smoke.log` | no | `commerce/` |
| BUILD_LEDGER.md:163 | `feature-message-smoke.log` → `commerce/evidence/feature-message-smoke.log` | no | `commerce/` |
| BUILD_LEDGER.md:165 | `clean-install-summary.json` → `commerce/evidence/clean-install-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:165 | `clean-storefront-summary.json` → `commerce/evidence/clean-storefront-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:165 | `commerce lockfile` → `commerce/package-lock.json` | yes | — |
| BUILD_LEDGER.md:165 | `storefront lockfile` → `commerce/storefront/package-lock.json` | yes | — |
| BUILD_LEDGER.md:167 | `clean-engine-summary.json` → `commerce/evidence/clean-engine-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:167 | `index.ts` → `commerce/backend/src/providers/hosted-checkout/index.ts` | yes | — |
| BUILD_LEDGER.md:167 | `native-loader-commerce-smoke.log` → `commerce/evidence/native-loader-commerce-smoke.log` | no | `commerce/` |
| BUILD_LEDGER.md:167 | `service.ts` → `commerce/backend/src/providers/hosted-checkout/service.ts` | yes | — |
| BUILD_LEDGER.md:169 | `first-run-summary.json` → `commerce/evidence/first-run-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:171 | `pickup-command-smoke.log` → `commerce/evidence/pickup-command-smoke.log` | no | `commerce/` |
| BUILD_LEDGER.md:173 | `pickup-completion-smoke.log` → `commerce/evidence/pickup-completion-smoke.log` | no | `commerce/` |
| BUILD_LEDGER.md:179 | `commerce/evidence/unpacked-refund-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:180 | `commerce/evidence/refund-release-regression.log` | no | `commerce/` |
| BUILD_LEDGER.md:185 | `commerce/evidence/order-facts-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:185 | `order-facts-live.log` → `commerce/evidence/order-facts-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:186 | `commerce/evidence/restore-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:192 | `commerce/evidence/pickup-set-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:192 | `pickup-set-live.log` → `commerce/evidence/pickup-set-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:199 | `commerce/evidence/special-command-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:199 | `special-command-live.log` → `commerce/evidence/special-command-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:205 | `commerce/evidence/special-source-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:205 | `special-source-live.log` → `commerce/evidence/special-source-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:210 | `commerce/evidence/frozen-price-recovery.log` | no | `commerce/` |
| BUILD_LEDGER.md:216 | `commerce/evidence/native-dated-pricing-probe.ts.txt` | no | `commerce/` |
| BUILD_LEDGER.md:216 | `native-dated-pricing-summary.json` → `commerce/evidence/native-dated-pricing-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:224 | `commerce/evidence/scheduled-special-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:224 | `scheduled-final-unit.log` → `commerce/evidence/scheduled-final-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:224 | `scheduled-natural-expiry.log` → `commerce/evidence/scheduled-natural-expiry.log` | no | `commerce/` |
| BUILD_LEDGER.md:224 | `scheduled-packing-regression.log` → `commerce/evidence/scheduled-packing-regression.log` | no | `commerce/` |
| BUILD_LEDGER.md:224 | `scheduled-recovery-regression.log` → `commerce/evidence/scheduled-recovery-regression.log` | no | `commerce/` |
| BUILD_LEDGER.md:224 | `scheduled-special-build.log` → `commerce/evidence/scheduled-special-build.log` | no | `commerce/` |
| BUILD_LEDGER.md:225, 233, 253, 272, 298, 388 | `restore-summary.json` → `commerce/evidence/restore-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:232 | `commerce/evidence/stock-receipt-recovery.log` | no | `commerce/` |
| BUILD_LEDGER.md:232 | `product-stock-receipt.log` → `commerce/evidence/product-stock-receipt.log` | no | `commerce/` |
| BUILD_LEDGER.md:232 | `stock-receipt-correction-regression.log` → `commerce/evidence/stock-receipt-correction-regression.log` | no | `commerce/` |
| BUILD_LEDGER.md:232 | `stock-receipt-packing-regression.log` → `commerce/evidence/stock-receipt-packing-regression.log` | no | `commerce/` |
| BUILD_LEDGER.md:232 | `stock-receipt-special-regression.log` → `commerce/evidence/stock-receipt-special-regression.log` | no | `commerce/` |
| BUILD_LEDGER.md:233 | `stock-receipt-restore.log` → `commerce/evidence/stock-receipt-restore.log` | no | `commerce/` |
| BUILD_LEDGER.md:238 | `commerce/evidence/superseded-product-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:239 | `superseded-draft-build.log` → `commerce/evidence/superseded-draft-build.log` | no | `commerce/` |
| BUILD_LEDGER.md:239 | `superseded-rejection-regression.log` → `commerce/evidence/superseded-rejection-regression.log` | no | `commerce/` |
| BUILD_LEDGER.md:248 | `commerce/evidence/late-refund-first-failure.log` | no | `commerce/` |
| BUILD_LEDGER.md:250 | `cancellation-intent-live.log` → `commerce/evidence/cancellation-intent-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:250 | `commerce/evidence/late-refund-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:250 | `late-refund-build.log` → `commerce/evidence/late-refund-build.log` | no | `commerce/` |
| BUILD_LEDGER.md:250 | `late-refund-packing-regression.log` → `commerce/evidence/late-refund-packing-regression.log` | no | `commerce/` |
| BUILD_LEDGER.md:250 | `late-refund-recovery-regression.log` → `commerce/evidence/late-refund-recovery-regression.log` | no | `commerce/` |
| BUILD_LEDGER.md:250 | `late-refund-reset-regression.log` → `commerce/evidence/late-refund-reset-regression.log` | no | `commerce/` |
| BUILD_LEDGER.md:250 | `legacy-late-refund-summary.json` → `commerce/evidence/legacy-late-refund-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:253 | `commerce/evidence/late-refund-restore.log` | no | `commerce/` |
| BUILD_LEDGER.md:258 | `commerce/evidence/payment-webhook-offline.log` | no | `commerce/` |
| BUILD_LEDGER.md:259 | `commerce/evidence/current-unit-suite.log` | no | `commerce/` |
| BUILD_LEDGER.md:264 | `commerce/evidence/percentage-full-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:264 | `percentage-build.log` → `commerce/evidence/percentage-build.log` | no | `commerce/` |
| BUILD_LEDGER.md:264 | `percentage-immediate-live.log` → `commerce/evidence/percentage-immediate-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:264 | `percentage-scheduled-live.log` → `commerce/evidence/percentage-scheduled-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:271 | `commerce/evidence/original-photo-availability.json` | no | `commerce/` |
| BUILD_LEDGER.md:271 | `heic-full-unit.log` → `commerce/evidence/heic-full-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:271 | `heic-upload-live.log` → `commerce/evidence/heic-upload-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:271 | `heic-upload-summary.json` → `commerce/evidence/heic-upload-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:272 | `commerce/evidence/heic-restore.log` | no | `commerce/` |
| BUILD_LEDGER.md:277 | `commerce/evidence/fulfillment-recovery-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:277 | `commerce/scripts/fulfillment-recovery-smoke.mjs` | yes | — |
| BUILD_LEDGER.md:282 | `commerce/evidence/numeric-intake-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:282 | `commerce/evidence/numeric-intake-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:287 | `commerce/evidence/text-details-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:287 | `commerce/evidence/text-details-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:292 | `commerce/evidence/photo-snapshot-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:292 | `photo-readback-typescript.log` → `commerce/evidence/photo-readback-typescript.log` | no | `commerce/` |
| BUILD_LEDGER.md:292 | `photo-snapshot-commerce.log` → `commerce/evidence/photo-snapshot-commerce.log` | no | `commerce/` |
| BUILD_LEDGER.md:292 | `photo-snapshot-persisted.json` | no | `.` |
| BUILD_LEDGER.md:297 | `commerce/evidence/photo-replacement-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:297 | `photo-replacement-summary.json` → `commerce/evidence/photo-replacement-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:297 | `scripts/photo-replacement-smoke.mjs` → `commerce/scripts/photo-replacement-smoke.mjs` | yes | — |
| BUILD_LEDGER.md:298 | `commerce/evidence/photo-replacement-restore.log` | no | `commerce/` |
| BUILD_LEDGER.md:303 | `commerce/evidence/packing-inline-build.log` | no | `commerce/` |
| BUILD_LEDGER.md:308 | `commerce/evidence/multi-photo-invalid-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:308 | `multi-photo-validation-unit.log` → `commerce/evidence/multi-photo-validation-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:313 | `commerce/evidence/photo-orientation-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:319 | `approval-comparison-build.log` → `commerce/evidence/approval-comparison-build.log` | no | `commerce/` |
| BUILD_LEDGER.md:319 | `commerce/evidence/approval-comparison-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:323 | `commerce/evidence/approval-stock-race-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:324 | `commerce/evidence/imported-cache-verification.json` | no | `commerce/` |
| BUILD_LEDGER.md:329 | `commerce/evidence/import-label-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:329 | `import-label-replay-summary.json` → `commerce/evidence/import-label-replay-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:329 | `import-label-replay.log` → `commerce/evidence/import-label-replay.log` | no | `commerce/` |
| BUILD_LEDGER.md:329 | `import-label-summary.json` → `commerce/evidence/import-label-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:329 | `scripts/import-label-evidence.mjs` → `commerce/scripts/import-label-evidence.mjs` | yes | — |
| BUILD_LEDGER.md:333 | `commerce/evidence/import-label-access-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:333 | `import-label-access-summary.json` → `commerce/evidence/import-label-access-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:333 | `import-label-restore.log` → `commerce/evidence/import-label-restore.log` | no | `commerce/` |
| BUILD_LEDGER.md:335 | `commerce/evidence/private-media-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:335 | `private-media-summary.json` → `commerce/evidence/private-media-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:340 | `commerce/evidence/customer-photo-history-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:340 | `customer-photo-history-summary.json` → `commerce/evidence/customer-photo-history-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:340 | `scripts/customer-photo-history-smoke.mjs` → `commerce/scripts/customer-photo-history-smoke.mjs` | yes | — |
| BUILD_LEDGER.md:346 | `commerce/evidence/static-contrast.log` | no | `commerce/` |
| BUILD_LEDGER.md:346 | `static-accessibility-build.log` → `commerce/evidence/static-accessibility-build.log` | no | `commerce/` |
| BUILD_LEDGER.md:351 | `commerce/evidence/worker-stock-grounding-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:351 | `worker-grounding-details-live.log` → `commerce/evidence/worker-grounding-details-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:351 | `worker-grounding-numeric-live.log` → `commerce/evidence/worker-grounding-numeric-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:356 | `commerce/evidence/order-task-recovery-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:356 | `order-task-recovery-summary.json` → `commerce/evidence/order-task-recovery-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:356 | `scripts/order-task-recovery-smoke.mjs` → `commerce/scripts/order-task-recovery-smoke.mjs` | yes | — |
| BUILD_LEDGER.md:361 | `commerce/evidence/paid-order-restart-prepare.log` | no | `commerce/` |
| BUILD_LEDGER.md:361 | `paid-order-backup-restore.log` → `commerce/evidence/paid-order-backup-restore.log` | no | `commerce/` |
| BUILD_LEDGER.md:361 | `paid-order-clean-restore.log` → `commerce/evidence/paid-order-clean-restore.log` | no | `commerce/` |
| BUILD_LEDGER.md:361 | `paid-order-restart-verify.log` → `commerce/evidence/paid-order-restart-verify.log` | no | `commerce/` |
| BUILD_LEDGER.md:361 | `scripts/paid-order-restart-smoke.mjs` → `commerce/scripts/paid-order-restart-smoke.mjs` | yes | — |
| BUILD_LEDGER.md:365 | `commerce/evidence/import-label-review-source.json` | no | `commerce/` |
| BUILD_LEDGER.md:365 | `import-photo-candidates.json` | no | `.` |
| BUILD_LEDGER.md:367 | `commerce/evidence/photo-candidates-import.log` | no | `commerce/` |
| BUILD_LEDGER.md:367 | `photo-candidates-build.log` → `commerce/evidence/photo-candidates-build.log` | no | `commerce/` |
| BUILD_LEDGER.md:367 | `photo-candidates-replay.log` → `commerce/evidence/photo-candidates-replay.log` | no | `commerce/` |
| BUILD_LEDGER.md:372 | `commerce/evidence/handoff-owner-access.log` | no | `commerce/` |
| BUILD_LEDGER.md:372 | `handoff-media-access.log` → `commerce/evidence/handoff-media-access.log` | no | `commerce/` |
| BUILD_LEDGER.md:378 | `commerce/evidence/catalog-availability-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:383 | `commerce/evidence/dictated-unit-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:387 | `commerce/evidence/current-sample-journey.log` | no | `commerce/` |
| BUILD_LEDGER.md:387 | `current-media-boundary.log` → `commerce/evidence/current-media-boundary.log` | no | `commerce/` |
| BUILD_LEDGER.md:388 | `commerce/evidence/current-handoff-restore.log` | no | `commerce/` |
| BUILD_LEDGER.md:393 | `commerce/evidence/context-photo-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:393 | `context-photo-build.log` → `commerce/evidence/context-photo-build.log` | no | `commerce/` |
| BUILD_LEDGER.md:393 | `context-shelf-regression.log` → `commerce/evidence/context-shelf-regression.log` | no | `commerce/` |
| BUILD_LEDGER.md:399 | `commerce/evidence/fixed-package-unit.log` | no | `commerce/` |
| BUILD_LEDGER.md:399 | `fixed-package-build.log` → `commerce/evidence/fixed-package-build.log` | no | `commerce/` |
| BUILD_LEDGER.md:399 | `fixed-package-live.log` → `commerce/evidence/fixed-package-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:403 | `commerce/evidence/dependency-audit.json` | no | `commerce/` |
| BUILD_LEDGER.md:417 | `local-vision-live.log` → `commerce/evidence/local-vision-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:417 | `primary-photo-live.log` → `commerce/evidence/primary-photo-live.log` | no | `commerce/` |
| BUILD_LEDGER.md:418 | `browser-qa-summary.json` → `commerce/evidence/browser-qa-summary.json` | no | `commerce/` |
| BUILD_LEDGER.md:423 | `local-vision-worker-regression.log` → `commerce/evidence/local-vision-worker-regression.log` | no | `commerce/` |
| BUILD_LEDGER.md:424 | `mobile-primary-photo-review.png` | no | `.` |
| BUILD_LEDGER.md:430 | `QA.json` → `storefront-mockup/archive/commerce-preview/qa/evidence/QA.json` | yes | — |
| BUILD_LEDGER.md:434 | `catalog-extraction.csv` → `storefront-mockup/catalog-extraction.csv` | yes | — |
| BUILD_LEDGER.md:434 | `storefront-mockup/catalog.json` | yes | — |
| BUILD_LEDGER.md:449 | `image-final-corrections.json` → `storefront-mockup/image-final-corrections.json` | yes | — |
| BUILD_LEDGER.md:449 | `storefront-mockup/image-generation-log.json` | yes | — |
| BUILD_LEDGER.md:459 | `expanded-image-log.json` → `storefront-mockup/expanded-image-log.json` | yes | — |
| BUILD_LEDGER.md:466, 476, 606, 608; hass/README.md:17 | `held-products.json` → `storefront-mockup/held-products.json` | yes | — |
| BUILD_LEDGER.md:476 | `storefront-mockup/asset-QA.json` | yes | — |
| BUILD_LEDGER.md:476 | `storefront-mockup/scroll-QA.json` | yes | — |
| BUILD_LEDGER.md:476 | `storefront-mockup/shop-QA.json` | no | `storefront-mockup/archive/commerce-preview/qa/evidence/shop-QA.json` |
| BUILD_LEDGER.md:476 | `storefront-mockup/story-QA.json` | yes | — |
| BUILD_LEDGER.md:483 | `mobile-function-reverify.json` → `storefront-mockup/archive/commerce-preview/qa/evidence/mobile-function-reverify.json` | yes | — |
| BUILD_LEDGER.md:486, 490 | `deployment/slofishreport-upload.zip` | no | `.` |
| BUILD_LEDGER.md:490 | `deployment/namecheap-hosting-cart.jpg` | no | `.` |
| BUILD_LEDGER.md:499 | `deployment/live-storefront.jpg` | no | `.` |
| BUILD_LEDGER.md:499 | `expiry-QA.json` | no | `.` |
| BUILD_LEDGER.md:499 | `live-assets-QA.json` | no | `.` |
| BUILD_LEDGER.md:502 | `deployment/mobile-boxes-live.jpg` | no | `.` |
| BUILD_LEDGER.md:496, 499 | `.htaccess` (old deployment; no repo counterpart at root) | no | `.` |
| BUILD_LEDGER.md:502 | `revisedindex.html` (run-together prose, not a literal tracked file) | no | `.`; current page is `storefront-mockup/index.html` |
| BUILD_LEDGER.md:586, 606; HERMES_HANDOFF.txt:74 | `index.html` → `storefront-mockup/index.html` | yes | — |
| BUILD_LEDGER.md:505 | `deployment/share-QA.json` | no | `.` |
| BUILD_LEDGER.md:505 | `share.jpg` → `storefront-mockup/assets/share.jpg` | yes | — |
| BUILD_LEDGER.md:507 | `branding/logo-refresh` | yes | — |
| BUILD_LEDGER.md:511 | `storefront-mockup/archive/commerce-preview` | yes | — |
| BUILD_LEDGER.md:514 | `Newcatalog-products.js` (run-together prose, not a literal tracked file) | no | `storefront-mockup/catalog-products.js` is the intended file |
| BUILD_LEDGER.md:606; HERMES_HANDOFF.txt:76 | `catalog-products.js` → `storefront-mockup/catalog-products.js` | yes | — |
| BUILD_LEDGER.md:515, 523; HERMES_HANDOFF.txt:104 | `catalog-only-QA.json` → `storefront-mockup/catalog-only-QA.json` | yes | — |
| BUILD_LEDGER.md:521 | `regularcommunity.json` (run-together prose, not a literal tracked file) | no | `storefront-mockup/community.json` is the intended file |
| BUILD_LEDGER.md:606; HERMES_HANDOFF.txt:29, 78 | `community.json` → `storefront-mockup/community.json` | yes | — |
| BUILD_LEDGER.md:522, 614, 1657; HERMES_HANDOFF.txt:79; hass/README.md:58, 117 | `community-server.py` → `storefront-mockup/community-server.py` | yes | — |
| BUILD_LEDGER.md:523; HERMES_HANDOFF.txt:104 | `community-api-QA.json` → `storefront-mockup/community-api-QA.json` | yes | — |
| BUILD_LEDGER.md:523; HERMES_HANDOFF.txt:105 | `community-ui-QA.json` → `storefront-mockup/community-ui-QA.json` | yes | — |
| BUILD_LEDGER.md:530 | `inventory-evidence.json` → `reports/hermes-handoff/inventory-evidence.json` | yes | — |
| BUILD_LEDGER.md:530 | `reports/hermes-handoff/Avocado_Shack_Hermes_Handoff_Report.html` | yes | — |
| BUILD_LEDGER.md:537; HERMES_HANDOFF.txt:57 | `community-data` | no | `.` |
| BUILD_LEDGER.md:538; HERMES_HANDOFF.txt:51 | `avocado-shack-sandbox.service` → `reports/hermes-handoff/avocado-shack-sandbox.service` | yes | — |
| BUILD_LEDGER.md:540, 543 | `AGENTS.md` | yes | — |
| BUILD_LEDGER.md:540 | `Avocado_Shack_Hermes_Handoff_Ready.html` → `reports/hermes-handoff/Avocado_Shack_Hermes_Handoff_Ready.html` | yes | — |
| BUILD_LEDGER.md:540 | `backup helper` → `reports/hermes-handoff/backup-community.py` | yes | — |
| BUILD_LEDGER.md:540, 543; HERMES_HANDOFF.txt:122 | `migration-verification.json` → `reports/hermes-handoff/migration-verification.json` | yes | — |
| BUILD_LEDGER.md:540 | `owner/product brief` → `reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt` | yes | — |
| BUILD_LEDGER.md:540 | `service file` → `reports/hermes-handoff/avocado-shack-sandbox.service` | yes | — |
| BUILD_LEDGER.md:543 | `owner brief` → `reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt` | yes | — |
| BUILD_LEDGER.md:544, 606, 620; HERMES_HANDOFF.txt:77; hass/README.md:71 | `producers.js` → `storefront-mockup/producers.js` | yes | — |
| BUILD_LEDGER.md:544, 606, 620; HERMES_HANDOFF.txt:77; hass/README.md:71 | `producers.json` → `storefront-mockup/producers.json` | yes | — |
| BUILD_LEDGER.md:545, 696, 2227 | `catalog-only-qa.cjs` → `storefront-mockup/catalog-only-qa.cjs` | yes | — |
| BUILD_LEDGER.md:545, 696, 1012 | `community-qa.py` → `storefront-mockup/community-qa.py` | yes | — |
| BUILD_LEDGER.md:545, 696, 2565 | `community-ui-qa.cjs` → `storefront-mockup/community-ui-qa.cjs` | yes | — |
| BUILD_LEDGER.md:549, 606, 2465, 2469; HERMES_HANDOFF.txt:27; hass/README.md:17, 78 | `hiking-preview.json` → `storefront-mockup/hiking-preview.json` | yes | — |
| BUILD_LEDGER.md:552 | `reports/hiking-club/qa-20261027.json` | yes | — |
| BUILD_LEDGER.md:563; HERMES_HANDOFF.txt:82 | `reports/hiking-club/TRAIL_MAP_SOURCES.txt` | yes | — |
| BUILD_LEDGER.md:565 | `reports/hiking-club/map-upgrade-qa-20261027.json` | yes | — |
| BUILD_LEDGER.md:569 | `reports/hiking-club/map-private-installation-20261027.json` | yes | — |
| BUILD_LEDGER.md:576 | `reports/hiking-club/catalog-hike-qa-20261028.json` | yes | — |
| BUILD_LEDGER.md:578 | `reports/hiking-club/catalog-hike-installed-20261028.json` | yes | — |
| BUILD_LEDGER.md:584 | `reports/catalog-card-update-20261028.json` | yes | — |
| BUILD_LEDGER.md:586, 1126, 1657, 1857, 2051, 2227, 2229, 2569, 2593; HERMES_HANDOFF.txt:76 | `shop.js` → `storefront-mockup/shop.js` | yes | — |
| BUILD_LEDGER.md:586, 1969; HERMES_HANDOFF.txt:75 | `style.css` → `storefront-mockup/style.css` | yes | — |
| BUILD_LEDGER.md:594; hass/README.md:230 | `docs/hass/` | yes | — |
| BUILD_LEDGER.md:596 | `reports/hass-plan-verification-20261030.json` | yes | — |
| BUILD_LEDGER.md:600; hass/README.md:3 | `docs/hass` | yes | — |
| BUILD_LEDGER.md:606, 1010, 1575 | `community.json` → `hass/content/community.json` | yes | — |
| BUILD_LEDGER.md:606; hass/README.md:7, 42 | `hass/content/` | yes | — |
| BUILD_LEDGER.md:606 | `hass/templates/` | yes | — |
| BUILD_LEDGER.md:606, 616; HERMES_HANDOFF.txt:74; hass/README.md:14 | `hike/index.html` → `storefront-mockup/hike/index.html` | yes | — |
| BUILD_LEDGER.md:606, 610, 922, 1575 | `makers.json` → `hass/content/makers.json` | yes | — |
| BUILD_LEDGER.md:606, 610 | `products.json` → `hass/content/products.json` | yes | — |
| BUILD_LEDGER.md:606 | `store.json` → `hass/content/store.json` | yes | — |
| BUILD_LEDGER.md:608, 610, 616, 622, 628, 634, 636, 638, 644, 652, 660, 670, 680, 688, 732, 740, 748, 756, 764, 772, 780, 788, 796, 812, 828, 860, 876, 892, 908, 916, 1012, 1052, 1180, 1188, 1196, 1204, 1212, 1220, 1236, 1244, 1252, 1841, 1977, 1985, 2009, 2017, 2025, 2041, 2049, 2073, 2323, 2355, 2403; hass/README.md:27 | `hass/tests` | yes | — |
| BUILD_LEDGER.md:608 | `migration-baseline.json` → `hass/content/migration-baseline.json` | yes | — |
| BUILD_LEDGER.md:608, 610, 616, 622, 628, 634, 636, 638, 644 | `migration_check.py` → `hass/migration_check.py` | yes | — |
| BUILD_LEDGER.md:608, 610, 616, 620, 622, 628, 634, 636, 638, 644, 2433 | `sitegen.py` → `hass/sitegen.py` | yes | — |
| BUILD_LEDGER.md:614, 810, 882, 1863; hass/README.md:38, 46, 47, 48, 49, 57, 120 | `hass/editor.py` | yes | — |
| BUILD_LEDGER.md:614; hass/README.md:38 | `hass/ops/` | yes | — |
| BUILD_LEDGER.md:616 | `hass/tests/fixture_ops.py` | yes | — |
| BUILD_LEDGER.md:616, 1719, 1959; hass/README.md:14 | `storefront-mockup/index.html` | yes | — |
| BUILD_LEDGER.md:620, 2205; hass/README.md:82 | `content_model.py` → `hass/content_model.py` | yes | — |
| BUILD_LEDGER.md:620, 746, 1122, 1695; hass/README.md:66 | `hass/ops/catalog.py` | yes | — |
| BUILD_LEDGER.md:626, 1106, 1114, 1234, 1671, 2103, 2917; hass/README.md:78 | `hass/ops/hikes.py` | yes | — |
| BUILD_LEDGER.md:632, 668, 1050, 1066, 1090, 1154, 1186, 1194, 1202, 1210, 1218, 1226, 1639, 1727, 1759, 1775, 1783, 1863, 1871, 1895, 1927, 1935, 1951, 2111, 2119, 2135, 2869, 3465, 3473, 3481, 3489; hass/README.md:94, 153 | `hass/conversation.py` | yes | — |
| BUILD_LEDGER.md:632, 650, 770, 818, 994; hass/README.md:107, 206 | `hass/fixture_chat.py` | yes | — |
| BUILD_LEDGER.md:636, 650, 652, 686, 706, 762, 778, 786, 826, 834, 842, 850, 866, 914, 994, 1082, 1106, 1114, 1122, 2095, 2167, 2529, 2531 | `hass/README.md` | yes | — |
| BUILD_LEDGER.md:642, 794, 1683; hass/README.md:122, 179 | `editor.py` → `hass/editor.py` | yes | — |
| BUILD_LEDGER.md:642, 1242, 1631, 2095 | `hass/ops/history.py` | yes | — |
| BUILD_LEDGER.md:642, 1018, 1863, 1871, 1887, 1895, 2917; hass/README.md:117 | `hass/preview.py` | yes | — |
| BUILD_LEDGER.md:642, 1018, 1863, 1871, 1887, 1895, 2565; hass/README.md:117 | `hass/screenshot.cjs` | yes | — |
| BUILD_LEDGER.md:646, 812, 844, 892, 900, 908, 924, 940, 964, 1060, 1068, 1092, 1156, 1164, 1633, 1761, 1777, 1785, 1929, 1937, 1953, 2331, 2611, 2725, 2887, 3179 | `hass.tests.test_conversation` → `hass/tests/test_conversation.py` | yes | — |
| BUILD_LEDGER.md:646, 836, 852, 1084, 1108, 1116, 1617, 1673, 2105, 2619 | `hass.tests.test_hike_ops` → `hass/tests/test_hike_ops.py` | yes | — |
| BUILD_LEDGER.md:646, 812, 884, 1004, 1036, 1228, 1617, 1633, 1681, 2001, 2097, 2523, 2579, 2661 | `hass.tests.test_undo` → `hass/tests/test_undo.py` | yes | — |
| BUILD_LEDGER.md:650 | `conversation-preview.jsonl` → `hass/tests/fixtures/conversation-preview.jsonl` | yes | — |
| BUILD_LEDGER.md:650 | `hass/tests/test_fixture_chat.py` | yes | — |
| BUILD_LEDGER.md:652, 660, 670, 680, 688, 756, 802, 804; hass/README.md:26 | `hass/migration_check.py` | yes | — |
| BUILD_LEDGER.md:658, 754, 778, 826, 874, 1146, 1282, 1831; hass/README.md:169, 172, 173, 174, 175, 176 | `hass/statebackup.py` | yes | — |
| BUILD_LEDGER.md:658 | `hass/tests/test_statebackup.py` | yes | — |
| BUILD_LEDGER.md:668 | `hass/tests/test_status_pause.py` | yes | — |
| BUILD_LEDGER.md:678, 1002, 1695, 1879; hass/README.md:136 | `hass/ops/store.py` | yes | — |
| BUILD_LEDGER.md:678 | `hass/tests/test_store_ops.py` | yes | — |
| BUILD_LEDGER.md:686, 1170, 1178; hass/README.md:189 | `hass/bridge.py` | yes | — |
| BUILD_LEDGER.md:686; hass/README.md:189 | `hass/tests/fixtures/bridge/` | yes | — |
| BUILD_LEDGER.md:686, 842 | `hass/tests/test_bridge.py` | yes | — |
| BUILD_LEDGER.md:696 | `hass/tests/fixtures/qa_env_driver.cjs` | yes | — |
| BUILD_LEDGER.md:696 | `hass/tests/test_qa_env.py` | yes | — |
| BUILD_LEDGER.md:696 | `section-navigation-qa.cjs` → `storefront-mockup/section-navigation-qa.cjs` | yes | — |
| BUILD_LEDGER.md:696 | `storefront-mockup/qa-env.cjs` | yes | — |
| BUILD_LEDGER.md:706, 786, 986, 1687; hass/README.md:198 | `hass/inbox.py` | yes | — |
| BUILD_LEDGER.md:706 | `hass/tests/test_inbox.py` | yes | — |
| BUILD_LEDGER.md:714, 738, 762, 858, 946, 1130, 1138, 1274, 2199; hass/README.md:159 | `hass/health.py` | yes | — |
| BUILD_LEDGER.md:714, 738 | `hass/tests/test_health.py` | yes | — |
| BUILD_LEDGER.md:722, 1623, 1639 | `hass/memory.py` | yes | — |
| BUILD_LEDGER.md:722 | `hass/tests/test_memory.py` | yes | — |
| BUILD_LEDGER.md:730 | `conversation-demo-interpreter.json` → `hass/tests/fixtures/conversation-demo-interpreter.json` | yes | — |
| BUILD_LEDGER.md:730, 794; hass/README.md:119 | `fixture_chat.py` → `hass/fixture_chat.py` | yes | — |
| BUILD_LEDGER.md:730 | `hass/tests/fixtures/conversation-demo.jsonl` | yes | — |
| BUILD_LEDGER.md:730 | `hass/tests/test_demo_transcript.py` | yes | — |
| BUILD_LEDGER.md:732, 772, 820, 892, 924, 996, 1092 | `hass.tests.test_demo_transcript` → `hass/tests/test_demo_transcript.py` | yes | — |
| BUILD_LEDGER.md:732 | `reports/hermes-handoff` | yes | — |
| BUILD_LEDGER.md:738 | `hass/tests/test_health_inbox.py` | yes | — |
| BUILD_LEDGER.md:740, 764, 860, 940, 1132, 1140, 1148, 1276, 2201 | `hass.tests.test_health` → `hass/tests/test_health.py` | yes | — |
| BUILD_LEDGER.md:740, 860, 988, 1276 | `hass.tests.test_health_inbox` → `hass/tests/test_health_inbox.py` | yes | — |
| BUILD_LEDGER.md:740, 772, 780, 788, 988 | `hass.tests.test_inbox` → `hass/tests/test_inbox.py` | yes | — |
| BUILD_LEDGER.md:746, 1695, 1879, 2087, 2103, 2917 | `hass/content_model.py` | yes | — |
| BUILD_LEDGER.md:746 | `hass/tests/fixtures/shop_photo_driver.cjs` | yes | — |
| BUILD_LEDGER.md:746 | `hass/tests/test_product_alt.py` | yes | — |
| BUILD_LEDGER.md:746, 1655, 1703, 1711, 1855, 1959, 2159, 3291, 3299, 3441, 3449; hass/README.md:113 | `storefront-mockup/shop.js` | yes | — |
| BUILD_LEDGER.md:748, 884, 900, 1076, 1084, 1124, 2579, 2661 | `hass.tests.test_catalog_ops` → `hass/tests/test_catalog_ops.py` | yes | — |
| BUILD_LEDGER.md:748, 804, 1084, 1617, 1697, 1721, 1881, 2089, 2097, 2105, 2443, 2451, 2459, 2467, 2499, 2515, 2823 | `hass.tests.test_content` → `hass/tests/test_content.py` | yes | — |
| BUILD_LEDGER.md:748, 1084, 1705, 1713, 2161, 3443 | `hass.tests.test_product_alt` → `hass/tests/test_product_alt.py` | yes | — |
| BUILD_LEDGER.md:754 | `hass.conversation` → `hass/conversation.py` | yes | — |
| BUILD_LEDGER.md:754 | `hass/tests/test_statebackup_paused.py` | yes | — |
| BUILD_LEDGER.md:756, 780, 1148, 2201 | `hass.tests.test_statebackup` → `hass/tests/test_statebackup.py` | yes | — |
| BUILD_LEDGER.md:756, 780, 1148 | `hass.tests.test_statebackup_paused` → `hass/tests/test_statebackup_paused.py` | yes | — |
| BUILD_LEDGER.md:756, 836, 868, 900, 940, 972, 1060, 1092, 1100, 1156, 1228, 1729, 1777, 2121, 2611, 3171 | `hass.tests.test_status_pause` → `hass/tests/test_status_pause.py` | yes | — |
| BUILD_LEDGER.md:762 | `hass/` | yes | — |
| BUILD_LEDGER.md:762 | `hass/tests/test_support_doc.py` | yes | — |
| BUILD_LEDGER.md:762, 794, 830, 1851 | `health.py` → `hass/health.py` | yes | — |
| BUILD_LEDGER.md:764, 780, 860, 1132, 1140, 1148, 1284, 1801, 1809, 1817, 2081, 2169, 2185, 2201, 2411, 2531 | `hass.tests.test_support_doc` → `hass/tests/test_support_doc.py` | yes | — |
| BUILD_LEDGER.md:766, 794, 862, 1286 | `statebackup.py` → `hass/statebackup.py` | yes | — |
| BUILD_LEDGER.md:770, 818 | `hass/tests/test_fixture_chat_queue.py` | yes | — |
| BUILD_LEDGER.md:772, 788, 820 | `hass.tests.test_fixture_chat_queue` → `hass/tests/test_fixture_chat_queue.py` | yes | — |
| BUILD_LEDGER.md:778 | `hass/tests/test_statebackup_inbox.py` | yes | — |
| BUILD_LEDGER.md:780, 988 | `hass.tests.test_statebackup_inbox` → `hass/tests/test_statebackup_inbox.py` | yes | — |
| BUILD_LEDGER.md:786 | `hass/tests/test_inbox_nonces.py` | yes | — |
| BUILD_LEDGER.md:788, 844, 1172 | `hass.tests.test_bridge` → `hass/tests/test_bridge.py` | yes | — |
| BUILD_LEDGER.md:788 | `hass.tests.test_inbox_nonces` → `hass/tests/test_inbox_nonces.py` | yes | — |
| BUILD_LEDGER.md:794; hass/README.md:34 | `hass/tests/test_output_hygiene.py` | yes | — |
| BUILD_LEDGER.md:796, 2033 | `hass.tests.test_output_hygiene` → `hass/tests/test_output_hygiene.py` | yes | — |
| BUILD_LEDGER.md:802 | `hass/tests/test_generated_io.py` | yes | — |
| BUILD_LEDGER.md:804, 812, 884, 2661 | `hass.tests.test_editor` → `hass/tests/test_editor.py` | yes | — |
| BUILD_LEDGER.md:804, 2105, 2435 | `hass.tests.test_generated_io` → `hass/tests/test_generated_io.py` | yes | — |
| BUILD_LEDGER.md:810 | `hass/tests/test_editor_cli_io.py` | yes | — |
| BUILD_LEDGER.md:812 | `hass.tests.test_editor_cli_io` → `hass/tests/test_editor_cli_io.py` | yes | — |
| BUILD_LEDGER.md:814, 1755, 2339, 2417 | `conversation.py` → `hass/conversation.py` | yes | — |
| BUILD_LEDGER.md:818 | `hass/tests/test_fixture_chat_rows.py` | yes | — |
| BUILD_LEDGER.md:820, 892, 996 | `hass.tests.test_fixture_chat` → `hass/tests/test_fixture_chat.py` | yes | — |
| BUILD_LEDGER.md:820 | `hass.tests.test_fixture_chat_rows` → `hass/tests/test_fixture_chat_rows.py` | yes | — |
| BUILD_LEDGER.md:822, 1827, 2043 | `bridge.py` → `hass/bridge.py` | yes | — |
| BUILD_LEDGER.md:826 | `hass/tests/test_statebackup_list.py` | yes | — |
| BUILD_LEDGER.md:828 | `test_statebackup*.py` → `hass/tests/test_statebackup*.py` | yes (matches) | — |
| BUILD_LEDGER.md:834 | `hass/tests/test_hike_rsvp_on.py` | yes | — |
| BUILD_LEDGER.md:836, 852, 876, 1108 | `hass.tests.test_hike_rsvp_on` → `hass/tests/test_hike_rsvp_on.py` | yes | — |
| BUILD_LEDGER.md:842 | `hass/tests/test_bridge_pictures.py` | yes | — |
| BUILD_LEDGER.md:844, 876, 1172 | `hass.tests.test_bridge_pictures` → `hass/tests/test_bridge_pictures.py` | yes | — |
| BUILD_LEDGER.md:850 | `hass/tests/test_hike_guest_warning.py` | yes | — |
| BUILD_LEDGER.md:852, 876, 1108, 1673 | `hass.tests.test_hike_guest_warning` → `hass/tests/test_hike_guest_warning.py` | yes | — |
| BUILD_LEDGER.md:858 | `hass/tests/test_health_seen.py` | yes | — |
| BUILD_LEDGER.md:860, 876, 1276 | `hass.tests.test_health_seen` → `hass/tests/test_health_seen.py` | yes | — |
| BUILD_LEDGER.md:866 | `hass/tests/test_status_rsvp_off.py` | yes | — |
| BUILD_LEDGER.md:868, 876, 972, 1100 | `hass.tests.test_status_rsvp_off` → `hass/tests/test_status_rsvp_off.py` | yes | — |
| BUILD_LEDGER.md:874 | `hass/tests/test_statebackup_atomic.py` | yes | — |
| BUILD_LEDGER.md:876 | `hass.tests.test_statebackup_atomic` → `hass/tests/test_statebackup_atomic.py` | yes | — |
| BUILD_LEDGER.md:882, 1034, 1679 | `hass/ops/photos.py` | yes | — |
| BUILD_LEDGER.md:882 | `hass/tests/test_set_photo.py` | yes | — |
| BUILD_LEDGER.md:884, 980, 1649, 2315 | `hass.tests.test_media_web` → `hass/tests/test_media_web.py` | yes | — |
| BUILD_LEDGER.md:884, 964, 996, 1036, 1681, 2315 | `hass.tests.test_set_photo` → `hass/tests/test_set_photo.py` | yes | — |
| BUILD_LEDGER.md:890, 1026 | `hass/interpret_check.py` | yes | — |
| BUILD_LEDGER.md:890 | `hass/tests/test_interpret_check.py` | yes | — |
| BUILD_LEDGER.md:892, 908, 924, 996, 1028, 1044, 1052, 1108 | `hass.tests.test_interpret_check` → `hass/tests/test_interpret_check.py` | yes | — |
| BUILD_LEDGER.md:898 | `hass/tests/test_memory_alias.py` | yes | — |
| BUILD_LEDGER.md:900, 940, 972, 980, 1060, 1068, 1076, 1697, 1777, 1785, 1801, 1809, 1817, 1929, 1937, 1953, 2081, 2113, 2121, 2137, 2169, 2185, 2363, 2419, 2523, 2531, 2579, 2611, 2725, 2749, 2807, 2815, 2831, 2879, 2887, 2975, 3035, 3059, 3339, 3347, 3379 | `hass.tests.test_commands_doc` → `hass/tests/test_commands_doc.py` | yes | — |
| BUILD_LEDGER.md:900, 1625, 1641, 1761 | `hass.tests.test_memory` → `hass/tests/test_memory.py` | yes | — |
| BUILD_LEDGER.md:900, 996, 1761, 2419, 3043, 3491 | `hass.tests.test_memory_alias` → `hass/tests/test_memory_alias.py` | yes | — |
| BUILD_LEDGER.md:900, 1625, 1641, 1761, 1929, 3043, 3491 | `hass.tests.test_memory_chat` → `hass/tests/test_memory_chat.py` | yes | — |
| BUILD_LEDGER.md:906, 1759, 3481 | `hass/interpreter_local.py` | yes | — |
| BUILD_LEDGER.md:906 | `hass/tests/test_interpreter_local.py` | yes | — |
| BUILD_LEDGER.md:908, 932, 996, 1164, 1761, 2693, 3363 | `hass.tests.test_interpreter_local` → `hass/tests/test_interpreter_local.py` | yes | — |
| BUILD_LEDGER.md:914, 1839; hass/README.md:215 | `hass/retention.py` | yes | — |
| BUILD_LEDGER.md:914 | `hass/tests/test_retention.py` | yes | — |
| BUILD_LEDGER.md:916, 996 | `hass.tests.test_retention` → `hass/tests/test_retention.py` | yes | — |
| BUILD_LEDGER.md:922, 2385 | `hass/claims.py` | yes | — |
| BUILD_LEDGER.md:922 | `hass/tests/test_claims.py` | yes | — |
| BUILD_LEDGER.md:924, 996, 1761, 2001, 2387, 2775, 2807, 2943 | `hass.tests.test_claims` → `hass/tests/test_claims.py` | yes | — |
| BUILD_LEDGER.md:930, 1735, 1743, 1751, 1759, 1911, 2901 | `hass/interpreter_prompt.py` | yes | — |
| BUILD_LEDGER.md:930, 1911, 3315 | `hass/tests/fixtures/interpreter-prompt.txt` | yes | — |
| BUILD_LEDGER.md:930 | `hass/tests/test_interpreter_prompt.py` | yes | — |
| BUILD_LEDGER.md:932, 996, 1737, 1745, 1753, 1761, 1769, 1913, 2089, 2097, 2331, 2579, 2653, 2693, 2775, 2807, 2903, 2911, 3315 | `hass.tests.test_interpreter_prompt` → `hass/tests/test_interpreter_prompt.py` | yes | — |
| BUILD_LEDGER.md:938 | `hass/tests/test_interpreter_cap.py` | yes | — |
| BUILD_LEDGER.md:940, 996, 1913, 2693, 3147 | `hass.tests.test_interpreter_cap` → `hass/tests/test_interpreter_cap.py` | yes | — |
| BUILD_LEDGER.md:946 | `hass/tests/test_health_model.py` | yes | — |
| BUILD_LEDGER.md:954, 1767, 2191, 3409 | `hass/interpreter_eval.py` | yes | — |
| BUILD_LEDGER.md:954, 3409 | `hass/tests/fixtures/interpreter-eval.jsonl` | yes | — |
| BUILD_LEDGER.md:954, 1919 | `hass/tests/test_interpreter_eval.py` | yes | — |
| BUILD_LEDGER.md:962 | `hass/tests/test_photo_draft.py` | yes | — |
| BUILD_LEDGER.md:964, 1172, 2137 | `hass.tests.test_attachment_reply` → `hass/tests/test_attachment_reply.py` | yes | — |
| BUILD_LEDGER.md:964, 980, 988, 996, 3139 | `hass.tests.test_photo_draft` → `hass/tests/test_photo_draft.py` | yes | — |
| BUILD_LEDGER.md:970 | `hass/tests/test_status_photos.py` | yes | — |
| BUILD_LEDGER.md:972, 996, 1777 | `hass.tests.test_status_photos` → `hass/tests/test_status_photos.py` | yes | — |
| BUILD_LEDGER.md:978 | `hass/tests/test_photo_limits.py` | yes | — |
| BUILD_LEDGER.md:978 | `test_photo_draft.py` → `hass/tests/test_photo_draft.py` | yes | — |
| BUILD_LEDGER.md:980, 1164, 1649 | `hass.tests.test_media` → `hass/tests/test_media.py` | yes | — |
| BUILD_LEDGER.md:980, 996, 2315 | `hass.tests.test_photo_limits` → `hass/tests/test_photo_limits.py` | yes | — |
| BUILD_LEDGER.md:986 | `hass/tests/test_attachment_retry.py` | yes | — |
| BUILD_LEDGER.md:988, 996 | `hass.tests.test_attachment_retry` → `hass/tests/test_attachment_retry.py` | yes | — |
| BUILD_LEDGER.md:988 | `hass.tests.test_inbox_unreadable` → `hass/tests/test_inbox_unreadable.py` | yes | — |
| BUILD_LEDGER.md:994; hass/README.md:112 | `-interpreter.json` → `hass/tests/fixtures/conversation-demo-photo-interpreter.json` | yes | — |
| BUILD_LEDGER.md:994; hass/README.md:112 | `conversation-demo-photo.jsonl` → `hass/tests/fixtures/conversation-demo-photo.jsonl` | yes | — |
| BUILD_LEDGER.md:994; hass/README.md:112 | `hass/tests/test_demo_transcript_photo.py` | yes | — |
| BUILD_LEDGER.md:996, 1905, 3139 | `hass.tests.test_demo_transcript_photo` → `hass/tests/test_demo_transcript_photo.py` | yes | — |
| BUILD_LEDGER.md:996, 1276 | `hass.tests.test_health_model` → `hass/tests/test_health_model.py` | yes | — |
| BUILD_LEDGER.md:996, 1028, 1737, 1745, 1753, 1769, 1921, 2193, 2427, 2523, 2693, 2741, 2839, 2967, 3107, 3411 | `hass.tests.test_interpreter_eval` → `hass/tests/test_interpreter_eval.py` | yes | — |
| BUILD_LEDGER.md:998 | `test_demo_transcript.py` → `hass/tests/test_demo_transcript.py` | yes | — |
| BUILD_LEDGER.md:1002 | `hass/tests/test_store_hours_repeat.py` | yes | — |
| BUILD_LEDGER.md:1002 | `test_store_limits.py` → `hass/tests/test_store_limits.py` | yes | — |
| BUILD_LEDGER.md:1004 | `hass.tests.test_store_hours_repeat` → `hass/tests/test_store_hours_repeat.py` | yes | — |
| BUILD_LEDGER.md:1004, 2089, 2177 | `hass.tests.test_store_limits` → `hass/tests/test_store_limits.py` | yes | — |
| BUILD_LEDGER.md:1004, 1020, 1084, 1697, 1881, 2089, 2523, 2951 | `hass.tests.test_store_ops` → `hass/tests/test_store_ops.py` | yes | — |
| BUILD_LEDGER.md:1010, 1250, 1258, 1719, 1721, 2491, 2499, 2709, 2767 | `storefront-mockup/community-ui-qa.cjs` | yes | — |
| BUILD_LEDGER.md:1010, 1250, 1258, 1719, 2151, 2917 | `storefront-mockup/community.js` | yes | — |
| BUILD_LEDGER.md:1012 | `check.yml` → `.github/workflows/check.yml` | yes | — |
| BUILD_LEDGER.md:1012, 1252, 1260, 1891, 2059, 2767; HERMES_HANDOFF.txt:79 | `community.js` → `storefront-mockup/community.js` | yes | — |
| BUILD_LEDGER.md:1018 | `hass/tests/test_preview_store_address.py` | yes | — |
| BUILD_LEDGER.md:1018 | `test_store_ops.py` → `hass/tests/test_store_ops.py` | yes | — |
| BUILD_LEDGER.md:1020, 1228, 1865 | `hass.tests.test_preview` → `hass/tests/test_preview.py` | yes | — |
| BUILD_LEDGER.md:1020, 2451 | `hass.tests.test_preview_overlay` → `hass/tests/test_preview_overlay.py` | yes | — |
| BUILD_LEDGER.md:1020, 1873, 2057 | `hass.tests.test_preview_store_address` → `hass/tests/test_preview_store_address.py` | yes | — |
| BUILD_LEDGER.md:1020, 2563, 2709 | `hass.tests.test_preview_viewports` → `hass/tests/test_preview_viewports.py` | yes | — |
| BUILD_LEDGER.md:1026 | `hass/tests/test_interpret_check_names.py` | yes | — |
| BUILD_LEDGER.md:1026 | `test_interpret_check.py` → `hass/tests/test_interpret_check.py` | yes | — |
| BUILD_LEDGER.md:1028 | `hass.tests.test_interpret_check_names` → `hass/tests/test_interpret_check_names.py` | yes | — |
| BUILD_LEDGER.md:1034 | `hass/tests/test_set_photo_alt.py` | yes | — |
| BUILD_LEDGER.md:1036 | `hass.tests.test_set_photo_alt` → `hass/tests/test_set_photo_alt.py` | yes | — |
| BUILD_LEDGER.md:1042 | `hass/tests/test_interpret_check_repeat.py` | yes | — |
| BUILD_LEDGER.md:1044 | `hass.tests.test_interpret_check_repeat` → `hass/tests/test_interpret_check_repeat.py` | yes | — |
| BUILD_LEDGER.md:1050 | `hass/tests/test_needs_details_expiry.py` | yes | — |
| BUILD_LEDGER.md:1050 | `hass/tests/test_revises_expired_vs_unknown.py` | yes | — |
| BUILD_LEDGER.md:1052, 2331, 2815 | `hass.tests.test_needs_details_expiry` → `hass/tests/test_needs_details_expiry.py` | yes | — |
| BUILD_LEDGER.md:1052 | `hass.tests.test_revises_expired_vs_unknown` → `hass/tests/test_revises_expired_vs_unknown.py` | yes | — |
| BUILD_LEDGER.md:1058, 2869 | `hass/tests/test_cancel_question.py` | yes | — |
| BUILD_LEDGER.md:1060 | `hass.tests.test_cancel_question` → `hass/tests/test_cancel_question.py` | yes | — |
| BUILD_LEDGER.md:1066 | `hass/tests/test_help.py` | yes | — |
| BUILD_LEDGER.md:1068, 1076, 1777, 1785, 1929, 1937, 1953, 2113, 2121, 2137, 2363, 2523, 2579, 2611, 2725, 2879, 2887, 3035, 3163, 3323, 3379, 3475 | `hass.tests.test_help` → `hass/tests/test_help.py` | yes | — |
| BUILD_LEDGER.md:1074 | `hass/tests/test_find.py` | yes | — |
| BUILD_LEDGER.md:1076, 1777, 1953, 2113, 2419, 2611, 2879 | `hass.tests.test_find` → `hass/tests/test_find.py` | yes | — |
| BUILD_LEDGER.md:1082 | `hass/tests/test_text_limits.py` | yes | — |
| BUILD_LEDGER.md:1082 | `test_hike_ids.py` → `hass/tests/test_hike_ids.py` | yes | — |
| BUILD_LEDGER.md:1084, 2113 | `hass.tests.test_hike_ids` → `hass/tests/test_hike_ids.py` | yes | — |
| BUILD_LEDGER.md:1084, 2177 | `hass.tests.test_text_limits` → `hass/tests/test_text_limits.py` | yes | — |
| BUILD_LEDGER.md:1086; hass/README.md:38 | `hass/ops/__init__.py` | yes | — |
| BUILD_LEDGER.md:1090 | `hass/tests/test_proposal_full_text.py` | yes | — |
| BUILD_LEDGER.md:1092, 1164, 2371 | `hass.tests.test_proposal_full_text` → `hass/tests/test_proposal_full_text.py` | yes | — |
| BUILD_LEDGER.md:1098 | `hass/tests/test_status_past_hikes.py` | yes | — |
| BUILD_LEDGER.md:1098 | `test_status_pause.py` → `hass/tests/test_status_pause.py` | yes | — |
| BUILD_LEDGER.md:1098 | `test_status_rsvp_off.py` → `hass/tests/test_status_rsvp_off.py` | yes | — |
| BUILD_LEDGER.md:1100, 2153, 2563 | `hass.tests.test_status_past_hikes` → `hass/tests/test_status_past_hikes.py` | yes | — |
| BUILD_LEDGER.md:1106 | `hass/tests/test_hike_clear.py` | yes | — |
| BUILD_LEDGER.md:1108 | `hass.tests.test_hike_capacity_rsvp_off` → `hass/tests/test_hike_capacity_rsvp_off.py` | yes | — |
| BUILD_LEDGER.md:1108, 1116 | `hass.tests.test_hike_clear` → `hass/tests/test_hike_clear.py` | yes | — |
| BUILD_LEDGER.md:1108, 1673 | `hass.tests.test_hike_move_warning` → `hass/tests/test_hike_move_warning.py` | yes | — |
| BUILD_LEDGER.md:1114 | `hass/tests/test_hike_recap.py` | yes | — |
| BUILD_LEDGER.md:1116, 2547, 2563 | `hass.tests.test_hike_recap` → `hass/tests/test_hike_recap.py` | yes | — |
| BUILD_LEDGER.md:1122 | `hass/tests/test_catalog_place.py` | yes | — |
| BUILD_LEDGER.md:1124 | `hass.tests.test_catalog_badge` → `hass/tests/test_catalog_badge.py` | yes | — |
| BUILD_LEDGER.md:1124 | `hass.tests.test_catalog_place` → `hass/tests/test_catalog_place.py` | yes | — |
| BUILD_LEDGER.md:1124 | `hass.tests.test_catalog_unchanged` → `hass/tests/test_catalog_unchanged.py` | yes | — |
| BUILD_LEDGER.md:1130 | `hass/tests/test_health_unverified.py` | yes | — |
| BUILD_LEDGER.md:1132 | `hass.tests.test_health_unreadable` → `hass/tests/test_health_unreadable.py` | yes | — |
| BUILD_LEDGER.md:1132, 1140, 1228 | `hass.tests.test_health_unverified` → `hass/tests/test_health_unverified.py` | yes | — |
| BUILD_LEDGER.md:1138 | `hass/tests/test_health_guests.py` | yes | — |
| BUILD_LEDGER.md:1140, 2129 | `hass.tests.test_health_guests` → `hass/tests/test_health_guests.py` | yes | — |
| BUILD_LEDGER.md:1142 | `hikes.py` → `hass/ops/hikes.py` | yes | — |
| BUILD_LEDGER.md:1146 | `hass/tests/test_statebackup_drill.py` | yes | — |
| BUILD_LEDGER.md:1148 | `hass.tests.test_statebackup_drill` → `hass/tests/test_statebackup_drill.py` | yes | — |
| BUILD_LEDGER.md:1154; hass/README.md:163 | `hass/tests/test_limits_doc.py` | yes | — |
| BUILD_LEDGER.md:1156, 1801, 1809, 1817, 1945, 2081, 2169, 2177, 2379, 2419, 2627, 2749, 2879, 2951, 2975, 3043, 3099, 3403, 3523 | `hass.tests.test_limits_doc` → `hass/tests/test_limits_doc.py` | yes | — |
| BUILD_LEDGER.md:1162; hass/README.md:208 | `hass/label_reader.py` | yes | — |
| BUILD_LEDGER.md:1162 | `hass/tests/test_label_reader.py` | yes | — |
| BUILD_LEDGER.md:1164, 2943, 3139 | `hass.tests.test_label_reader` → `hass/tests/test_label_reader.py` | yes | — |
| BUILD_LEDGER.md:1164, 1649 | `hass.tests.test_media_time` → `hass/tests/test_media_time.py` | yes | — |
| BUILD_LEDGER.md:1170 | `hass/tests/test_bridge_reactions.py` | yes | — |
| BUILD_LEDGER.md:1170 | `reaction.json` → `hass/tests/fixtures/bridge/reaction.json` | yes | — |
| BUILD_LEDGER.md:1170 | `receipt.json` → `hass/tests/fixtures/bridge/receipt.json` | yes | — |
| BUILD_LEDGER.md:1170 | `test_attachment_reply.py` → `hass/tests/test_attachment_reply.py` | yes | — |
| BUILD_LEDGER.md:1172 | `hass.tests.test_bridge_reactions` → `hass/tests/test_bridge_reactions.py` | yes | — |
| BUILD_LEDGER.md:1178 | `hass/tests/test_bridge_edit_ids.py` | yes | — |
| BUILD_LEDGER.md:1180 | `hass.tests.test_bridge_edit_ids` → `hass/tests/test_bridge_edit_ids.py` | yes | — |
| BUILD_LEDGER.md:1186 | `hass/tests/test_not_read_reply.py` | yes | — |
| BUILD_LEDGER.md:1188 | `hass.tests.test_not_read_reply` → `hass/tests/test_not_read_reply.py` | yes | — |
| BUILD_LEDGER.md:1194 | `hass/tests/test_owner_text_cap.py` | yes | — |
| BUILD_LEDGER.md:1196, 2419, 2815 | `hass.tests.test_owner_text_cap` → `hass/tests/test_owner_text_cap.py` | yes | — |
| BUILD_LEDGER.md:1202 | `hass/tests/test_bare_yes_question.py` | yes | — |
| BUILD_LEDGER.md:1204 | `hass.tests.test_bare_yes_question` → `hass/tests/test_bare_yes_question.py` | yes | — |
| BUILD_LEDGER.md:1210 | `hass/tests/test_proposal_added.py` | yes | — |
| BUILD_LEDGER.md:1210 | `test_proposal_full_text.py` → `hass/tests/test_proposal_full_text.py` | yes | — |
| BUILD_LEDGER.md:1212, 2371 | `hass.tests.test_proposal_added` → `hass/tests/test_proposal_added.py` | yes | — |
| BUILD_LEDGER.md:1218 | `hass/tests/test_hike_time_text.py` | yes | — |
| BUILD_LEDGER.md:1220, 3267 | `hass.tests.test_hike_time_text` → `hass/tests/test_hike_time_text.py` | yes | — |
| BUILD_LEDGER.md:1226 | `hass/tests/test_verify_all_records.py` | yes | — |
| BUILD_LEDGER.md:1228 | `hass.tests.test_verify_all_records` → `hass/tests/test_verify_all_records.py` | yes | — |
| BUILD_LEDGER.md:1234, 1663 | `hass/tests/test_hike_twin.py` | yes | — |
| BUILD_LEDGER.md:1236, 1665 | `hass.tests.test_hike_twin` → `hass/tests/test_hike_twin.py` | yes | — |
| BUILD_LEDGER.md:1242 | `hass/tests/test_undo_guest_warnings.py` | yes | — |
| BUILD_LEDGER.md:1244 | `hass.tests.test_undo_guest_warnings` → `hass/tests/test_undo_guest_warnings.py` | yes | — |
| BUILD_LEDGER.md:1252, 1260, 1266, 1268, 1721, 2065, 2475, 2483, 2547, 2555, 2563, 2709, 2767 | `storefront-mockup/community-qa.py` | yes | — |
| BUILD_LEDGER.md:1274 | `hass/tests/test_health_disk.py` | yes | — |
| BUILD_LEDGER.md:1276 | `hass.tests.test_health_backup_verify` → `hass/tests/test_health_backup_verify.py` | yes | — |
| BUILD_LEDGER.md:1276 | `hass.tests.test_health_disk` → `hass/tests/test_health_disk.py` | yes | — |
| BUILD_LEDGER.md:1303, 2011, 2173, 2317, 2405, 2415, 2625, 3041, 3097; hass/README.md:239 | `LIMITS.md` → `docs/hass/LIMITS.md` | yes | — |
| BUILD_LEDGER.md:1308 | `hass/README` → `hass/README.md` | yes | — |
| BUILD_LEDGER.md:1535, 2075 | `SUPPORT.md` → `docs/hass/SUPPORT.md` | yes | — |
| BUILD_LEDGER.md:1542 | `memory.py` → `hass/memory.py` | yes | — |
| BUILD_LEDGER.md:1609 | `hass/install.py` | yes | — |
| BUILD_LEDGER.md:1610 | `CONNECT.md` → `docs/hass/CONNECT.md` | yes | — |
| BUILD_LEDGER.md:1615, 2095, 2103, 2831; hass/README.md:88 | `hass/ops/routes.py` | yes | — |
| BUILD_LEDGER.md:1615 | `hass/tests/test_route_edit.py` | yes | — |
| BUILD_LEDGER.md:1617, 1633 | `hass.tests.test_revert_records` → `hass/tests/test_revert_records.py` | yes | — |
| BUILD_LEDGER.md:1617, 2097, 2105 | `hass.tests.test_route_edit` → `hass/tests/test_route_edit.py` | yes | — |
| BUILD_LEDGER.md:1623 | `hass/tests/test_memory_source.py` | yes | — |
| BUILD_LEDGER.md:1623 | `test_memory.py` → `hass/tests/test_memory.py` | yes | — |
| BUILD_LEDGER.md:1623 | `test_memory_history.py` → `hass/tests/test_memory_history.py` | yes | — |
| BUILD_LEDGER.md:1625 | `hass.tests.test_memory_history` → `hass/tests/test_memory_history.py` | yes | — |
| BUILD_LEDGER.md:1625, 1641, 1761 | `hass.tests.test_memory_source` → `hass/tests/test_memory_source.py` | yes | — |
| BUILD_LEDGER.md:1631 | `hass/tests/test_undo_twice.py` | yes | — |
| BUILD_LEDGER.md:1633, 2661 | `hass.tests.test_undo_twice` → `hass/tests/test_undo_twice.py` | yes | — |
| BUILD_LEDGER.md:1635, 2027, 2083, 2509, 2533, 3033, 3041, 3057 | `COMMANDS.md` → `docs/hass/COMMANDS.md` | yes | — |
| BUILD_LEDGER.md:1639 | `hass/tests/test_memory_unchanged.py` | yes | — |
| BUILD_LEDGER.md:1641, 3043, 3491 | `hass.tests.test_memory_unchanged` → `hass/tests/test_memory_unchanged.py` | yes | — |
| BUILD_LEDGER.md:1647, 1847 | `hass/media.py` | yes | — |
| BUILD_LEDGER.md:1647 | `hass/tests/test_media_time.py` | yes | — |
| BUILD_LEDGER.md:1649 | `hass.tests.test_statebackup_media` → `hass/tests/test_statebackup_media.py` | yes | — |
| BUILD_LEDGER.md:1655, 1657, 1703, 1705, 1711, 1713, 1855, 1857, 1959, 1961, 1969, 2229, 2459, 2571, 2677, 3291, 3299, 3443, 3451; hass/README.md:144 | `storefront-mockup/catalog-only-qa.cjs` | yes | — |
| BUILD_LEDGER.md:1663 | `hass/tests/test_hike_create_repeat.py` | no | `hass/tests/` (superseding coverage: `hass/tests/test_hike_twin.py`) |
| BUILD_LEDGER.md:1671 | `hass/tests/test_hike_guest_rows.py` | yes | — |
| BUILD_LEDGER.md:1673 | `hass.tests.test_hike_guest_rows` → `hass/tests/test_hike_guest_rows.py` | yes | — |
| BUILD_LEDGER.md:1679 | `assets/products` → `storefront-mockup/assets/products` | yes | — |
| BUILD_LEDGER.md:1679 | `hass/tests/test_set_photo_folder.py` | yes | — |
| BUILD_LEDGER.md:1679 | `test_set_photo.py` → `hass/tests/test_set_photo.py` | yes | — |
| BUILD_LEDGER.md:1679 | `test_set_photo_site_read.py` → `hass/tests/test_set_photo_site_read.py` | yes | — |
| BUILD_LEDGER.md:1681 | `hass.tests.test_set_photo_folder` → `hass/tests/test_set_photo_folder.py` | yes | — |
| BUILD_LEDGER.md:1687 | `hass/tests/test_inbox_payload_types.py` | yes | — |
| BUILD_LEDGER.md:1687 | `inbox.py` → `hass/inbox.py` | yes | — |
| BUILD_LEDGER.md:1689 | `hass.tests.test_inbox_payload_types` → `hass/tests/test_inbox_payload_types.py` | yes | — |
| BUILD_LEDGER.md:1695, 1727, 2127 | `hass/morning_report.py` | yes | — |
| BUILD_LEDGER.md:1697, 2579, 2847, 2983, 3315 | `hass.tests.test_auto_policy` → `hass/tests/test_auto_policy.py` | yes | — |
| BUILD_LEDGER.md:1697, 1777, 2121, 2129 | `hass.tests.test_morning_report` → `hass/tests/test_morning_report.py` | yes | — |
| BUILD_LEDGER.md:1697 | `hass.tests.test_morning_report_names` → `hass/tests/test_morning_report_names.py` | yes | — |
| BUILD_LEDGER.md:1697 | `hass.tests.test_selection_backdate_window` → `hass/tests/test_selection_backdate_window.py` | yes | — |
| BUILD_LEDGER.md:1697, 1713, 1881, 1961, 1969, 3259 | `hass.tests.test_selection_checked` → `hass/tests/test_selection_checked.py` | yes | — |
| BUILD_LEDGER.md:1697, 2579 | `hass.tests.test_selection_per_product_day` → `hass/tests/test_selection_per_product_day.py` | yes | — |
| BUILD_LEDGER.md:1703, 1711, 1719, 1959, 1967 | `storefront-mockup/style.css` | yes | — |
| BUILD_LEDGER.md:1711 | `hass/tests/test_availability_words_pin.py` | yes | — |
| BUILD_LEDGER.md:1713 | `hass.tests.test_availability_words_pin` → `hass/tests/test_availability_words_pin.py` | yes | — |
| BUILD_LEDGER.md:1719, 2288 | `hass/templates/index.html` | yes | — |
| BUILD_LEDGER.md:1721, 1969, 2161 | `hass.tests.test_design_check` → `hass/tests/test_design_check.py` | yes | — |
| BUILD_LEDGER.md:1721, 2161 | `hass.tests.test_generated_links` → `hass/tests/test_generated_links.py` | yes | — |
| BUILD_LEDGER.md:1721, 1961, 1969 | `hass.tests.test_generated_targets` → `hass/tests/test_generated_targets.py` | yes | — |
| BUILD_LEDGER.md:1727 | `hass/tests/test_status_shelf_check.py` | yes | — |
| BUILD_LEDGER.md:1729 | `hass.tests.test_content_deep_json` → `hass/tests/test_content_deep_json.py` | yes | — |
| BUILD_LEDGER.md:1729, 1777, 3259 | `hass.tests.test_status_shelf_check` → `hass/tests/test_status_shelf_check.py` | yes | — |
| BUILD_LEDGER.md:1735 | `hass/tests/test_interpreter_prompt_brand.py` | yes | — |
| BUILD_LEDGER.md:1737, 2911 | `hass.tests.test_interpreter_prompt_brand` → `hass/tests/test_interpreter_prompt_brand.py` | yes | — |
| BUILD_LEDGER.md:1737, 1745, 1753, 1913, 2097, 2105, 2693 | `hass.tests.test_interpreter_prompt_community` → `hass/tests/test_interpreter_prompt_community.py` | yes | — |
| BUILD_LEDGER.md:1737, 1745, 1753, 1913, 2693, 2911 | `hass.tests.test_interpreter_prompt_shapes` → `hass/tests/test_interpreter_prompt_shapes.py` | yes | — |
| BUILD_LEDGER.md:1737, 1745, 1753, 1881, 2089, 2693 | `hass.tests.test_interpreter_prompt_store` → `hass/tests/test_interpreter_prompt_store.py` | yes | — |
| BUILD_LEDGER.md:1745 | `hass.tests.test_interpreter_prompt_home_text` → `hass/tests/test_interpreter_prompt_home_text.py` | yes | — |
| BUILD_LEDGER.md:1753, 1769, 1921, 2193, 2635, 2693, 2741, 2839, 2967, 3107, 3411 | `hass.tests.test_interpreter_eval_cases` → `hass/tests/test_interpreter_eval_cases.py` | yes | — |
| BUILD_LEDGER.md:1753, 1769, 1921, 2193, 2693, 2839, 2967, 3411 | `hass.tests.test_interpreter_eval_out` → `hass/tests/test_interpreter_eval_out.py` | yes | — |
| BUILD_LEDGER.md:1753, 1881, 2911, 3027, 3315, 3371 | `hass.tests.test_interpreter_prompt_design` → `hass/tests/test_interpreter_prompt_design.py` | yes | — |
| BUILD_LEDGER.md:1759 | `hass/tests/test_interpreter_notes.py` | yes | — |
| BUILD_LEDGER.md:1761, 2693 | `hass.tests.test_interpreter_local_strict` → `hass/tests/test_interpreter_local_strict.py` | yes | — |
| BUILD_LEDGER.md:1761, 2807, 3371, 3483 | `hass.tests.test_interpreter_notes` → `hass/tests/test_interpreter_notes.py` | yes | — |
| BUILD_LEDGER.md:1761, 1913, 2193, 2693, 2839, 2967 | `hass.tests.test_interpreter_request_encode` → `hass/tests/test_interpreter_request_encode.py` | yes | — |
| BUILD_LEDGER.md:1761, 1993, 2693, 3483 | `hass.tests.test_interpreter_today` → `hass/tests/test_interpreter_today.py` | yes | — |
| BUILD_LEDGER.md:1767 | `hass/tests/test_interpreter_eval_cases.py` | yes | — |
| BUILD_LEDGER.md:1775 | `hass/tests/test_report_waiting.py` | yes | — |
| BUILD_LEDGER.md:1777, 1937, 2137, 3339, 3459 | `hass.tests.test_post_command` → `hass/tests/test_post_command.py` | yes | — |
| BUILD_LEDGER.md:1777, 2121, 2701, 3355 | `hass.tests.test_report_command` → `hass/tests/test_report_command.py` | yes | — |
| BUILD_LEDGER.md:1777 | `hass.tests.test_report_waiting` → `hass/tests/test_report_waiting.py` | yes | — |
| BUILD_LEDGER.md:1783 | `hass/tests/test_margin_chat.py` | yes | — |
| BUILD_LEDGER.md:1785, 3499, 3507 | `hass.tests.test_margin_chat` → `hass/tests/test_margin_chat.py` | yes | — |
| BUILD_LEDGER.md:1785, 1929, 1945 | `hass.tests.test_margins` → `hass/tests/test_margins.py` | yes | — |
| BUILD_LEDGER.md:1785 | `hass.tests.test_margins_percent_decimals` → `hass/tests/test_margins_percent_decimals.py` | yes | — |
| BUILD_LEDGER.md:1785 | `hass.tests.test_margins_plain_numbers` → `hass/tests/test_margins_plain_numbers.py` | yes | — |
| BUILD_LEDGER.md:1785 | `hass.tests.test_margins_price_check` → `hass/tests/test_margins_price_check.py` | yes | — |
| BUILD_LEDGER.md:1791, 1817, 2537, 2539, 2643, 2757, 2847, 2981, 3417, 3419, 3529, 3531, 3537; hass/README.md:229 | `hass/acceptance.py` | yes | — |
| BUILD_LEDGER.md:1791 | `hass/tests/test_acceptance_runner.py` | yes | — |
| BUILD_LEDGER.md:1793, 2523, 2539, 2643, 2757, 2847, 2983, 3115, 3419, 3531, 3537 | `hass.tests.test_acceptance_runner` → `hass/tests/test_acceptance_runner.py` | yes | — |
| BUILD_LEDGER.md:1797; hass/README.md:230 | `IMPLEMENTATION.md` → `docs/hass/IMPLEMENTATION.md` | yes | — |
| BUILD_LEDGER.md:1801, 1809, 1817, 1945, 2081, 2169, 2185, 2419, 2627, 2733, 2749, 2831, 2975, 3099, 3403, 3523 | `hass.tests.test_phone_guide` → `hass/tests/test_phone_guide.py` | yes | — |
| BUILD_LEDGER.md:1801, 1809, 1817 | `hass.tests.test_tracked_private` → `hass/tests/test_tracked_private.py` | yes | — |
| BUILD_LEDGER.md:1807, 2831 | `docs/hass/TRIAL.md` | yes | — |
| BUILD_LEDGER.md:1823; hass/README.md:191 | `hass/bridge_photos.py` | yes | — |
| BUILD_LEDGER.md:1823 | `hass/tests/test_bridge_photos_unicode.py` | yes | — |
| BUILD_LEDGER.md:1825 | `hass.tests.test_bridge_photos` → `hass/tests/test_bridge_photos.py` | yes | — |
| BUILD_LEDGER.md:1825 | `hass.tests.test_bridge_photos_ids` → `hass/tests/test_bridge_photos_ids.py` | yes | — |
| BUILD_LEDGER.md:1825 | `hass.tests.test_bridge_photos_size` → `hass/tests/test_bridge_photos_size.py` | yes | — |
| BUILD_LEDGER.md:1825 | `hass.tests.test_bridge_photos_tail` → `hass/tests/test_bridge_photos_tail.py` | yes | — |
| BUILD_LEDGER.md:1825 | `hass.tests.test_bridge_photos_unicode` → `hass/tests/test_bridge_photos_unicode.py` | yes | — |
| BUILD_LEDGER.md:1825, 2033, 2250, 3537 | `hass.tests.test_ledger_rf1120` → `hass/tests/test_ledger_rf1120.py` | yes | — |
| BUILD_LEDGER.md:1831 | `hass/tests/test_statebackup_restore_atomic.py` | yes | — |
| BUILD_LEDGER.md:1833 | `hass.tests.test_statebackup_restore_atomic` → `hass/tests/test_statebackup_restore_atomic.py` | yes | — |
| BUILD_LEDGER.md:1839 | `hass/tests/test_retention_screenshots.py` | yes | — |
| BUILD_LEDGER.md:1841 | `test_retention*.py` → `hass/tests/test_retention*.py` | yes (matches) | — |
| BUILD_LEDGER.md:1847 | `hass/tests/test_media_verify_web.py` | yes | — |
| BUILD_LEDGER.md:1847 | `media.py` → `hass/media.py` | yes | — |
| BUILD_LEDGER.md:1849 | `hass.tests.test_media_verify_web` → `hass/tests/test_media_verify_web.py` | yes | — |
| BUILD_LEDGER.md:1865 | `hass.tests.test_preview_checks_shape` → `hass/tests/test_preview_checks_shape.py` | yes | — |
| BUILD_LEDGER.md:1865 | `hass.tests.test_preview_product_checks` → `hass/tests/test_preview_product_checks.py` | yes | — |
| BUILD_LEDGER.md:1865, 1873, 1881, 1897, 2523, 2563, 2709 | `hass.tests.test_preview_target_shapes` → `hass/tests/test_preview_target_shapes.py` | yes | — |
| BUILD_LEDGER.md:1871, 1879, 1895 | `hass/owner_answers.py` | yes | — |
| BUILD_LEDGER.md:1873 | `hass.tests.test_owner_answers` → `hass/tests/test_owner_answers.py` | yes | — |
| BUILD_LEDGER.md:1873 | `hass.tests.test_owner_answers_shapes` → `hass/tests/test_owner_answers_shapes.py` | yes | — |
| BUILD_LEDGER.md:1873, 1881 | `hass.tests.test_preview_store_checks` → `hass/tests/test_preview_store_checks.py` | yes | — |
| BUILD_LEDGER.md:1881, 1945 | `hass.tests.test_store_phone` → `hass/tests/test_store_phone.py` | yes | — |
| BUILD_LEDGER.md:1887 | `hass/tests/test_preview_hike_results.py` | yes | — |
| BUILD_LEDGER.md:1889, 2057, 2547, 2563, 2709, 3363 | `hass.tests.test_preview_hike_results` → `hass/tests/test_preview_hike_results.py` | yes | — |
| BUILD_LEDGER.md:1891, 2288 | `screenshot.cjs` → `hass/screenshot.cjs` | yes | — |
| BUILD_LEDGER.md:1897, 3243 | `hass.tests.test_preview_route_results` → `hass/tests/test_preview_route_results.py` | yes | — |
| BUILD_LEDGER.md:1903 | `hass/tests/test_demo_browser_photo.py` | yes | — |
| BUILD_LEDGER.md:1905 | `hass.tests.test_demo_browser` → `hass/tests/test_demo_browser.py` | yes | — |
| BUILD_LEDGER.md:1905 | `hass.tests.test_demo_browser_photo` → `hass/tests/test_demo_browser_photo.py` | yes | — |
| BUILD_LEDGER.md:1919 | `hass/tests/test_interpreter_eval_out.py` | yes | — |
| BUILD_LEDGER.md:1929 | `hass.tests.test_purchase_cost` → `hass/tests/test_purchase_cost.py` | yes | — |
| BUILD_LEDGER.md:1935 | `hass/tests/test_post_hike_command.py` | yes | — |
| BUILD_LEDGER.md:1937 | `hass.tests.test_post_hike_command` → `hass/tests/test_post_hike_command.py` | yes | — |
| BUILD_LEDGER.md:1937, 2145, 2717 | `hass.tests.test_social_draft_hike` → `hass/tests/test_social_draft_hike.py` | yes | — |
| BUILD_LEDGER.md:1939, 2143, 3457 | `hass/social_draft.py` | yes | — |
| BUILD_LEDGER.md:1951 | `hass/tests/test_hidden_command.py` | yes | — |
| BUILD_LEDGER.md:1953, 3379 | `hass.tests.test_hidden_command` → `hass/tests/test_hidden_command.py` | yes | — |
| BUILD_LEDGER.md:1961 | `hass.tests.test_catalog_clear_filters` → `hass/tests/test_catalog_clear_filters.py` | yes | — |
| BUILD_LEDGER.md:1967 | `hass/tests/test_style_no_commerce.py` | yes | — |
| BUILD_LEDGER.md:1969 | `hass.tests.test_style_no_commerce` → `hass/tests/test_style_no_commerce.py` | yes | — |
| BUILD_LEDGER.md:1977, 1985, 2009, 2017, 2025, 2041, 2049, 2073 | `test*.py` → `hass/tests/test*.py` | yes (matches) | — |
| BUILD_LEDGER.md:2001, 2387, 2943 | `hass.tests.test_claims_sources` → `hass/tests/test_claims_sources.py` | yes | — |
| BUILD_LEDGER.md:2033 | `hass.tests.test_owner_sender_match` → `hass/tests/test_owner_sender_match.py` | yes | — |
| BUILD_LEDGER.md:2033 | `hass.tests.test_state_db_nofollow` → `hass/tests/test_state_db_nofollow.py` | yes | — |
| BUILD_LEDGER.md:2087, 2831; hass/README.md:149 | `hass/ops/home.py` | yes | — |
| BUILD_LEDGER.md:2089 | `hass.tests.test_store_intro` → `hass/tests/test_store_intro.py` | yes | — |
| BUILD_LEDGER.md:2089, 2523, 2831, 2927, 3307 | `hass.tests.test_store_notice` → `hass/tests/test_store_notice.py` | yes | — |
| BUILD_LEDGER.md:2095 | `history.py` → `hass/ops/history.py` | yes | — |
| BUILD_LEDGER.md:2097, 2831 | `hass.tests.test_route_add` → `hass/tests/test_route_add.py` | yes | — |
| BUILD_LEDGER.md:2097 | `hass.tests.test_route_edit_spacing` → `hass/tests/test_route_edit_spacing.py` | yes | — |
| BUILD_LEDGER.md:2097 | `hass.tests.test_route_edit_titles` → `hass/tests/test_route_edit_titles.py` | yes | — |
| BUILD_LEDGER.md:2105 | `hass.tests.test_migration_baseline_shape` → `hass/tests/test_migration_baseline_shape.py` | yes | — |
| BUILD_LEDGER.md:2105, 2831 | `hass.tests.test_route_hide` → `hass/tests/test_route_hide.py` | yes | — |
| BUILD_LEDGER.md:2113, 2611 | `hass.tests.test_find_hikes` → `hass/tests/test_find_hikes.py` | yes | — |
| BUILD_LEDGER.md:2121, 2129 | `hass.tests.test_morning_report_future` → `hass/tests/test_morning_report_future.py` | yes | — |
| BUILD_LEDGER.md:2121, 2129 | `hass.tests.test_morning_report_shapes` → `hass/tests/test_morning_report_shapes.py` | yes | — |
| BUILD_LEDGER.md:2129 | `hass.tests.test_morning_report_hikes` → `hass/tests/test_morning_report_hikes.py` | yes | — |
| BUILD_LEDGER.md:2137, 2145, 2717, 3459 | `hass.tests.test_social_draft` → `hass/tests/test_social_draft.py` | yes | — |
| BUILD_LEDGER.md:2137, 2145, 2717, 3459 | `hass.tests.test_social_draft_inputs` → `hass/tests/test_social_draft_inputs.py` | yes | — |
| BUILD_LEDGER.md:2137, 2145, 2717, 3459 | `hass.tests.test_social_draft_shapes` → `hass/tests/test_social_draft_shapes.py` | yes | — |
| BUILD_LEDGER.md:2137, 2145, 2717, 3459 | `hass.tests.test_social_draft_tags` → `hass/tests/test_social_draft_tags.py` | yes | — |
| BUILD_LEDGER.md:2137, 2145, 2717, 3459 | `hass.tests.test_social_draft_text` → `hass/tests/test_social_draft_text.py` | yes | — |
| BUILD_LEDGER.md:2143, 2715 | `social_draft.py` → `hass/social_draft.py` | yes | — |
| BUILD_LEDGER.md:2153 | `hass.tests.test_content_starts_at` → `hass/tests/test_content_starts_at.py` | yes | — |
| BUILD_LEDGER.md:2153, 2475, 2483, 2547, 2555, 2563, 2709, 2757 | `hass.tests.test_hike_ics` → `hass/tests/test_hike_ics.py` | yes | — |
| BUILD_LEDGER.md:2153, 2161 | `hass.tests.test_https_links` → `hass/tests/test_https_links.py` | yes | — |
| BUILD_LEDGER.md:2201 | `hass.tests.test_health_backup_content` → `hass/tests/test_health_backup_content.py` | yes | — |
| BUILD_LEDGER.md:2205; hass/README.md:275 | `hass/ops/specials.py` | yes | — |
| BUILD_LEDGER.md:2205; hass/README.md:273 | `hass/specials.py` | yes | — |
| BUILD_LEDGER.md:2205 | `hass/tests/test_specials.py` | yes | — |
| BUILD_LEDGER.md:2209; HERMES_HANDOFF.txt:80 | `trail-explorer.js` → `storefront-mockup/trail-explorer.js` | yes | — |
| BUILD_LEDGER.md:2209 | `trail-map-retry-qa.cjs` → `storefront-mockup/trail-map-retry-qa.cjs` | yes | — |
| BUILD_LEDGER.md:2211 | `storefront-mockup/trail-map-retry-qa.cjs` | yes | — |
| BUILD_LEDGER.md:2215 | `hass/tests/test_community_email_controls.py` | yes | — |
| BUILD_LEDGER.md:2217 | `hass.tests.test_community_email_controls` → `hass/tests/test_community_email_controls.py` | yes | — |
| BUILD_LEDGER.md:2221; HERMES_HANDOFF.txt:83 | `script.js` → `storefront-mockup/script.js` | yes | — |
| BUILD_LEDGER.md:2221, 2441, 2497 | `static-site-qa.cjs` → `storefront-mockup/static-site-qa.cjs` | yes | — |
| BUILD_LEDGER.md:2223, 2435, 2443, 2451, 2459, 2467, 2475, 2483, 2491, 2499, 2515, 2767, 3307 | `storefront-mockup/static-site-qa.cjs` | yes | — |
| BUILD_LEDGER.md:2235, 2237 | `openreq.py` → `hass/skills/openreq.py` | yes | — |
| BUILD_LEDGER.md:2235 | `test_open_requests.py` → `hass/tests/test_open_requests.py` | yes | — |
| BUILD_LEDGER.md:2237 | `hass.tests.test_open_requests` → `hass/tests/test_open_requests.py` | yes | — |
| BUILD_LEDGER.md:2241 | `hass/corrlog.py` | yes | — |
| BUILD_LEDGER.md:2241 | `test_corrlog.py` → `hass/tests/test_corrlog.py` | yes | — |
| BUILD_LEDGER.md:2243 | `hass.tests.test_corrlog` → `hass/tests/test_corrlog.py` | yes | — |
| BUILD_LEDGER.md:2248 | `preview.json` → `reports/hass/newitem-1/preview/preview.json` | yes | — |
| BUILD_LEDGER.md:2250 | `hass.tests.test_newitem` → `hass/tests/test_newitem.py` | yes | — |
| BUILD_LEDGER.md:2256 | `hass.tests.test_skills_backlog` → `hass/tests/test_skills_backlog.py` | yes | — |
| BUILD_LEDGER.md:2260; hass/README.md:210, 211 | `hass/label_eval.py` | yes | — |
| BUILD_LEDGER.md:2262, 2967 | `hass.tests.test_label_eval` → `hass/tests/test_label_eval.py` | yes | — |
| BUILD_LEDGER.md:2272 | `CAPABILITIES.md` → `docs/hass/CAPABILITIES.md` | yes | — |
| BUILD_LEDGER.md:2272, 2288 | `docs/hass/capabilities.json` | yes | — |
| BUILD_LEDGER.md:2278 | `docs/hass/SANDBOX.md` | yes | — |
| BUILD_LEDGER.md:2278 | `host.py` → `hass/host.py` | yes | — |
| BUILD_LEDGER.md:2282 | `docs/hass/RUNTIME-RELEASE.md` | yes | — |
| BUILD_LEDGER.md:2282 | `hass/runtime_release.py` | yes | — |
| BUILD_LEDGER.md:2286, 2305 | `hass/ops/front.py` | yes | — |
| BUILD_LEDGER.md:2286, 2305 | `hass/skills/front.py` | yes | — |
| BUILD_LEDGER.md:2286, 2288, 2307 | `hass/templates/home/*.html` | yes (matches) | — |
| BUILD_LEDGER.md:2288 | `home/market.html` → `hass/templates/home/market.html` | yes | — |
| BUILD_LEDGER.md:2305 | `hass/templates/info/index.html` | yes | — |
| BUILD_LEDGER.md:2315 | `hass.tests.test_media_orientation` → `hass/tests/test_media_orientation.py` | yes | — |
| BUILD_LEDGER.md:2323 | `hass.tests.test_product_add_photo` → `hass/tests/test_product_add_photo.py` | yes | — |
| BUILD_LEDGER.md:2331, 2693, 2815 | `hass.tests.test_pending_ops` → `hass/tests/test_pending_ops.py` | yes | — |
| BUILD_LEDGER.md:2331 | `hass.tests.test_settings_config_file` → `hass/tests/test_settings_config_file.py` | yes | — |
| BUILD_LEDGER.md:2339, 2653, 3139 | `hass.tests.test_photo_new_product` → `hass/tests/test_photo_new_product.py` | yes | — |
| BUILD_LEDGER.md:2347, 2379 | `hass.tests.test_late_yes` → `hass/tests/test_late_yes.py` | yes | — |
| BUILD_LEDGER.md:2355, 3147 | `hass.tests.test_undo_skip_undo` → `hass/tests/test_undo_skip_undo.py` | yes | — |
| BUILD_LEDGER.md:2363, 2371, 2611 | `hass.tests.test_show` → `hass/tests/test_show.py` | yes | — |
| BUILD_LEDGER.md:2371 | `hass.tests.test_proposal_photo_words` → `hass/tests/test_proposal_photo_words.py` | yes | — |
| BUILD_LEDGER.md:2379, 3483 | `hass.tests.test_late_reply` → `hass/tests/test_late_reply.py` | yes | — |
| BUILD_LEDGER.md:2379 | `hass.tests.test_outbox_delayed` → `hass/tests/test_outbox_delayed.py` | yes | — |
| BUILD_LEDGER.md:2387 | `hass.tests.test_claims_access` → `hass/tests/test_claims_access.py` | yes | — |
| BUILD_LEDGER.md:2387, 2943 | `hass.tests.test_claims_grades` → `hass/tests/test_claims_grades.py` | yes | — |
| BUILD_LEDGER.md:2395 | `hass.tests.test_claims_numbers` → `hass/tests/test_claims_numbers.py` | yes | — |
| BUILD_LEDGER.md:2403 | `hass.tests.test_store_hours_numbering` → `hass/tests/test_store_hours_numbering.py` | yes | — |
| BUILD_LEDGER.md:2411 | `hass.tests.test_health_unused_photos` → `hass/tests/test_health_unused_photos.py` | yes | — |
| BUILD_LEDGER.md:2427 | `hass.tests.test_demo_negative` → `hass/tests/test_demo_negative.py` | yes | — |
| BUILD_LEDGER.md:2435, 2443, 2451, 2459, 2467, 2499, 2507, 2515, 2603, 2619, 2709, 2733, 2823, 2959 | `hass.tests.test_publish` → `hass/tests/test_publish.py` | yes | — |
| BUILD_LEDGER.md:2435, 2459, 2483 | `hass.tests.test_publish_home_image` → `hass/tests/test_publish_home_image.py` | yes | — |
| BUILD_LEDGER.md:2435, 2459, 2515, 2523, 2831 | `hass.tests.test_store_home_image` → `hass/tests/test_store_home_image.py` | yes | — |
| BUILD_LEDGER.md:2441 | `hass/templates/404.html` | yes | — |
| BUILD_LEDGER.md:2443, 2451, 2823 | `hass.tests.test_publish_404` → `hass/tests/test_publish_404.py` | yes | — |
| BUILD_LEDGER.md:2449 | `assets/favicon.png` → `storefront-mockup/assets/favicon.png` | yes | — |
| BUILD_LEDGER.md:2449 | `assets/logo-header.png` → `storefront-mockup/assets/logo-header.png` | yes | — |
| BUILD_LEDGER.md:2449 | `logo.png` → `storefront-mockup/assets/logo.png` | yes | — |
| BUILD_LEDGER.md:2459 | `hass.tests.test_image_dimensions` → `hass/tests/test_image_dimensions.py` | yes | — |
| BUILD_LEDGER.md:2459, 2523 | `hass.tests.test_store_clear_home_image` → `hass/tests/test_store_clear_home_image.py` | yes | — |
| BUILD_LEDGER.md:2491 | `storefront-mockup/section-navigation-qa.cjs` | yes | — |
| BUILD_LEDGER.md:2505 | `hass/ops/samples.py` | yes | — |
| BUILD_LEDGER.md:2507 | `hass.tests.test_hike_samples` → `hass/tests/test_hike_samples.py` | yes | — |
| BUILD_LEDGER.md:2515 | `hass.tests.test_local_business_data` → `hass/tests/test_local_business_data.py` | yes | — |
| BUILD_LEDGER.md:2547, 2563 | `hass.tests.test_hike_anchor` → `hass/tests/test_hike_anchor.py` | yes | — |
| BUILD_LEDGER.md:2563 | `hass.tests.test_hike_journal` → `hass/tests/test_hike_journal.py` | yes | — |
| BUILD_LEDGER.md:2571 | `hass.tests.test_browser_freshness` → `hass/tests/test_browser_freshness.py` | yes | — |
| BUILD_LEDGER.md:2579 | `hass.tests.test_clear_availability` → `hass/tests/test_clear_availability.py` | yes | — |
| BUILD_LEDGER.md:2579, 2661 | `hass.tests.test_undo_product_restore` → `hass/tests/test_undo_product_restore.py` | yes | — |
| BUILD_LEDGER.md:2587 | `hass.tests.test_product_new` → `hass/tests/test_product_new.py` | yes | — |
| BUILD_LEDGER.md:2593, 2595 | `hass.tests.test_organic_sync` → `hass/tests/test_organic_sync.py` | yes | — |
| BUILD_LEDGER.md:2611, 3339, 3379 | `hass.tests.test_listing_command` → `hass/tests/test_listing_command.py` | yes | — |
| BUILD_LEDGER.md:2619, 2709, 2959 | `hass.tests.test_qa_env` → `hass/tests/test_qa_env.py` | yes | — |
| BUILD_LEDGER.md:2625, 3097; hass/README.md:239 | `PHONE_GUIDE.md` → `docs/hass/PHONE_GUIDE.md` | yes | — |
| BUILD_LEDGER.md:2653, 3139 | `hass.tests.test_photo_home_image` → `hass/tests/test_photo_home_image.py` | yes | — |
| BUILD_LEDGER.md:2661 | `hass.tests.test_catalog_dupes` → `hass/tests/test_catalog_dupes.py` | yes | — |
| BUILD_LEDGER.md:2661 | `hass.tests.test_maker_product_batch` → `hass/tests/test_maker_product_batch.py` | yes | — |
| BUILD_LEDGER.md:2669 | `hass.tests.test_maker_hide_products` → `hass/tests/test_maker_hide_products.py` | yes | — |
| BUILD_LEDGER.md:2677 | `hass.tests.test_maker_optional_url` → `hass/tests/test_maker_optional_url.py` | yes | — |
| BUILD_LEDGER.md:2677 | `hass.tests.test_preview_maker` → `hass/tests/test_preview_maker.py` | yes | — |
| BUILD_LEDGER.md:2685 | `hass.tests.test_hike_repeat` → `hass/tests/test_hike_repeat.py` | yes | — |
| BUILD_LEDGER.md:2685, 2943 | `hass.tests.test_hike_repeat_claims` → `hass/tests/test_hike_repeat_claims.py` | yes | — |
| BUILD_LEDGER.md:2693 | `hass.tests.test_interpreter_prompt_text` → `hass/tests/test_interpreter_prompt_text.py` | yes | — |
| BUILD_LEDGER.md:2701 | `hass.tests.test_status_notice` → `hass/tests/test_status_notice.py` | yes | — |
| BUILD_LEDGER.md:2717, 3459 | `hass.tests.test_social_draft_fullwidth` → `hass/tests/test_social_draft_fullwidth.py` | yes | — |
| BUILD_LEDGER.md:2717 | `hass.tests.test_social_draft_maker` → `hass/tests/test_social_draft_maker.py` | yes | — |
| BUILD_LEDGER.md:2725 | `hass.tests.test_post_maker_command` → `hass/tests/test_post_maker_command.py` | yes | — |
| BUILD_LEDGER.md:2733 | `hass.tests.test_set_photo_site_read` → `hass/tests/test_set_photo_site_read.py` | yes | — |
| BUILD_LEDGER.md:2741, 2967, 3411 | `hass.tests.test_interpreter_eval_compare` → `hass/tests/test_interpreter_eval_compare.py` | yes | — |
| BUILD_LEDGER.md:2741, 2967 | `hass.tests.test_interpreter_eval_diagnostics` → `hass/tests/test_interpreter_eval_diagnostics.py` | yes | — |
| BUILD_LEDGER.md:2741, 2967, 3411 | `hass.tests.test_interpreter_eval_modes` → `hass/tests/test_interpreter_eval_modes.py` | yes | — |
| BUILD_LEDGER.md:2775, 2943 | `hass.tests.test_claims_lists` → `hass/tests/test_claims_lists.py` | yes | — |
| BUILD_LEDGER.md:2775, 2807 | `hass.tests.test_interpreter_no_undo` → `hass/tests/test_interpreter_no_undo.py` | yes | — |
| BUILD_LEDGER.md:2783, 3083 | `hass.tests.test_field_words` → `hass/tests/test_field_words.py` | yes | — |
| BUILD_LEDGER.md:2783, 2815, 3083 | `hass.tests.test_question_missing_fields` → `hass/tests/test_question_missing_fields.py` | yes | — |
| BUILD_LEDGER.md:2791, 3475 | `hass.tests.test_product_default_brand` → `hass/tests/test_product_default_brand.py` | yes | — |
| BUILD_LEDGER.md:2799, 2879, 2887, 3051 | `hass.tests.test_history_search` → `hass/tests/test_history_search.py` | yes | — |
| BUILD_LEDGER.md:2799 | `hass.tests.test_named_records` → `hass/tests/test_named_records.py` | yes | — |
| BUILD_LEDGER.md:2807 | `hass.tests.test_interpreter_aliases` → `hass/tests/test_interpreter_aliases.py` | yes | — |
| BUILD_LEDGER.md:2815, 3147 | `hass.tests.test_social_message` → `hass/tests/test_social_message.py` | yes | — |
| BUILD_LEDGER.md:2821 | `reports/site-copy-claims-2026-11.md` | yes | — |
| BUILD_LEDGER.md:2831 | `hass.tests.test_trial_handover_doc` → `hass/tests/test_trial_handover_doc.py` | yes | — |
| BUILD_LEDGER.md:2871 | `hass.tests.test_unknown_approval_code` → `hass/tests/test_unknown_approval_code.py` | yes | — |
| BUILD_LEDGER.md:2879, 3051 | `hass.tests.test_history_approved` → `hass/tests/test_history_approved.py` | yes | — |
| BUILD_LEDGER.md:2885, 3497 | `hass/chat/commands.py` | yes | — |
| BUILD_LEDGER.md:2885 | `hass/chat/core_pack.py` | yes | — |
| BUILD_LEDGER.md:2887, 3379 | `hass.tests.test_again` → `hass/tests/test_again.py` | yes | — |
| BUILD_LEDGER.md:2895 | `hass.tests.test_media_batch` → `hass/tests/test_media_batch.py` | yes | — |
| BUILD_LEDGER.md:2895 | `hass.tests.test_photo_batch` → `hass/tests/test_photo_batch.py` | yes | — |
| BUILD_LEDGER.md:2903 | `hass.tests.test_interpreter_prompt_shelf_maker` → `hass/tests/test_interpreter_prompt_shelf_maker.py` | yes | — |
| BUILD_LEDGER.md:2911 | `hass.tests.test_interpreter_prompt_descriptions` → `hass/tests/test_interpreter_prompt_descriptions.py` | yes | — |
| BUILD_LEDGER.md:2919 | `hass.tests.test_hike_cancel_note` → `hass/tests/test_hike_cancel_note.py` | yes | — |
| BUILD_LEDGER.md:2919 | `hass.tests.test_preview_cancel_note` → `hass/tests/test_preview_cancel_note.py` | yes | — |
| BUILD_LEDGER.md:2927 | `hass.tests.test_notice_calendar_bounds` → `hass/tests/test_notice_calendar_bounds.py` | yes | — |
| BUILD_LEDGER.md:2927, 3307 | `hass.tests.test_notice_start` → `hass/tests/test_notice_start.py` | yes | — |
| BUILD_LEDGER.md:2935, 3307 | `hass.tests.test_club_intro` → `hass/tests/test_club_intro.py` | yes | — |
| BUILD_LEDGER.md:2943 | `hass.tests.test_claims_farm` → `hass/tests/test_claims_farm.py` | yes | — |
| BUILD_LEDGER.md:2943 | `hass.tests.test_claims_health_awards` → `hass/tests/test_claims_health_awards.py` | yes | — |
| BUILD_LEDGER.md:2943 | `hass.tests.test_claims_negation` → `hass/tests/test_claims_negation.py` | yes | — |
| BUILD_LEDGER.md:2943 | `hass.tests.test_label_matches` → `hass/tests/test_label_matches.py` | yes | — |
| BUILD_LEDGER.md:2943 | `hass.tests.test_label_reader_forbidden` → `hass/tests/test_label_reader_forbidden.py` | yes | — |
| BUILD_LEDGER.md:2951 | `hass.tests.test_store_field_undo` → `hass/tests/test_store_field_undo.py` | yes | — |
| BUILD_LEDGER.md:2951 | `hass.tests.test_store_story` → `hass/tests/test_store_story.py` | yes | — |
| BUILD_LEDGER.md:2957 | `reports/site-contrast-2026-11.md` | yes | — |
| BUILD_LEDGER.md:2959 | `storefront-mockup/site-contrast-qa.cjs` | yes | — |
| BUILD_LEDGER.md:2959 | `storefront-mockup/site-contrast-qa.py` | yes | — |
| BUILD_LEDGER.md:2959 | `storefront-mockup/site-contrast.test.cjs` | yes | — |
| BUILD_LEDGER.md:3009, 3011 | `reports/held-cheese-recall-2026-11.md` | yes | — |
| BUILD_LEDGER.md:3011; hass/README.md:42 | `hass/content/products.json` | yes | — |
| BUILD_LEDGER.md:3019 | `hass.tests.test_interpret_check_enum` → `hass/tests/test_interpret_check_enum.py` | yes | — |
| BUILD_LEDGER.md:3019 | `hass.tests.test_shelf_labels` → `hass/tests/test_shelf_labels.py` | yes | — |
| BUILD_LEDGER.md:3027 | `hass.tests.test_interpret_check_prices` → `hass/tests/test_interpret_check_prices.py` | yes | — |
| BUILD_LEDGER.md:3035 | `hass.tests.test_photos_to_take` → `hass/tests/test_photos_to_take.py` | yes | — |
| BUILD_LEDGER.md:3043 | `hass.tests.test_memory_listing` → `hass/tests/test_memory_listing.py` | yes | — |
| BUILD_LEDGER.md:3051 | `hass.tests.test_audit` → `hass/tests/test_audit.py` | yes | — |
| BUILD_LEDGER.md:3051 | `hass.tests.test_history_times` → `hass/tests/test_history_times.py` | yes | — |
| BUILD_LEDGER.md:3059 | `hass.tests.test_undo_cancel_phrases` → `hass/tests/test_undo_cancel_phrases.py` | yes | — |
| BUILD_LEDGER.md:3067 | `hass.tests.test_proposal_notice_words` → `hass/tests/test_proposal_notice_words.py` | yes | — |
| BUILD_LEDGER.md:3067, 3259 | `hass.tests.test_shelf_check_flow` → `hass/tests/test_shelf_check_flow.py` | yes | — |
| BUILD_LEDGER.md:3075 | `hass.tests.test_catalog_new_order` → `hass/tests/test_catalog_new_order.py` | yes | — |
| BUILD_LEDGER.md:3083 | `hass.tests.test_maker_optional_story` → `hass/tests/test_maker_optional_story.py` | yes | — |
| BUILD_LEDGER.md:3089, 3091 | `reports/hiking-club/route-map-sources-2026-11.md` | yes | — |
| BUILD_LEDGER.md:3091; hass/README.md:42 | `hass/content/community.json` | yes | — |
| BUILD_LEDGER.md:3139 | `hass.tests.test_qa1_new_item_chat` → `hass/tests/test_qa1_new_item_chat.py` | yes | — |
| BUILD_LEDGER.md:3147 | `hass.tests.test_near_approval` → `hass/tests/test_near_approval.py` | yes | — |
| BUILD_LEDGER.md:3147, 3467 | `hass.tests.test_phone_answers` → `hass/tests/test_phone_answers.py` | yes | — |
| BUILD_LEDGER.md:3147 | `hass.tests.test_qa1_waiting_reminders` → `hass/tests/test_qa1_waiting_reminders.py` | yes | — |
| BUILD_LEDGER.md:3147, 3171 | `hass.tests.test_voice` → `hass/tests/test_voice.py` | yes | — |
| BUILD_LEDGER.md:3155, 3163, 3171, 3187, 3283 | `hass.tests.test_demo_rehearsal` → `hass/tests/test_demo_rehearsal.py` | yes | — |
| BUILD_LEDGER.md:3155 | `hass.tests.test_skills_reports` → `hass/tests/test_skills_reports.py` | yes | — |
| BUILD_LEDGER.md:3155 | `hass.tests.test_skills_router` → `hass/tests/test_skills_router.py` | yes | — |
| BUILD_LEDGER.md:3179 | `hass.tests.test_repeat_outcome` → `hass/tests/test_repeat_outcome.py` | yes | — |
| BUILD_LEDGER.md:3187 | `hass.tests.test_phone_wording` → `hass/tests/test_phone_wording.py` | yes | — |
| BUILD_LEDGER.md:3195 | `hass.tests.test_clover_chat` → `hass/tests/test_clover_chat.py` | yes | — |
| BUILD_LEDGER.md:3195 | `hass.tests.test_clover_mapper` → `hass/tests/test_clover_mapper.py` | yes | — |
| BUILD_LEDGER.md:3203 | `hass.tests.test_nl_prep_calendar` → `hass/tests/test_nl_prep_calendar.py` | yes | — |
| BUILD_LEDGER.md:3211 | `hass.tests.test_weekday_date_mismatch` → `hass/tests/test_weekday_date_mismatch.py` | yes | — |
| BUILD_LEDGER.md:3219 | `hass.tests.test_nl_prep_ordinal_words` → `hass/tests/test_nl_prep_ordinal_words.py` | yes | — |
| BUILD_LEDGER.md:3227 | `hass.tests.test_stock_product_choice` → `hass/tests/test_stock_product_choice.py` | yes | — |
| BUILD_LEDGER.md:3235 | `hass.tests.test_candidate_answer_safety` → `hass/tests/test_candidate_answer_safety.py` | yes | — |
| BUILD_LEDGER.md:3235 | `hass.tests.test_non_hike_question_turns` → `hass/tests/test_non_hike_question_turns.py` | yes | — |
| BUILD_LEDGER.md:3243 | `hass.tests.test_second_question` → `hass/tests/test_second_question.py` | yes | — |
| BUILD_LEDGER.md:3251, 3259 | `hass.tests.test_plain_shelf_check` → `hass/tests/test_plain_shelf_check.py` | yes | — |
| BUILD_LEDGER.md:3251, 3259 | `hass.tests.test_skills_stock` → `hass/tests/test_skills_stock.py` | yes | — |
| BUILD_LEDGER.md:3259 | `hass.tests.test_qa1_fixes` → `hass/tests/test_qa1_fixes.py` | yes | — |
| BUILD_LEDGER.md:3259 | `hass.tests.test_shelf_check_except` → `hass/tests/test_shelf_check_except.py` | yes | — |
| BUILD_LEDGER.md:3267 | `hass.tests.test_hike_change_words` → `hass/tests/test_hike_change_words.py` | yes | — |
| BUILD_LEDGER.md:3267 | `hass.tests.test_hike_flow` → `hass/tests/test_hike_flow.py` | yes | — |
| BUILD_LEDGER.md:3275 | `hass.tests.test_chat_dead_end_reasons` → `hass/tests/test_chat_dead_end_reasons.py` | yes | — |
| BUILD_LEDGER.md:3307 | `hass.tests.test_front` → `hass/tests/test_front.py` | yes | — |
| BUILD_LEDGER.md:3307 | `hass.tests.test_publish_csp` → `hass/tests/test_publish_csp.py` | yes | — |
| BUILD_LEDGER.md:3307 | `hass.tests.test_specials` → `hass/tests/test_specials.py` | yes | — |
| BUILD_LEDGER.md:3307 | `hass/tests/fixtures/publish_csp_driver.cjs` | yes | — |
| BUILD_LEDGER.md:3315 | `hass.tests.test_live_table` → `hass/tests/test_live_table.py` | yes | — |
| BUILD_LEDGER.md:3315 | `hass.tests.test_set_availability_all` → `hass/tests/test_set_availability_all.py` | yes | — |
| BUILD_LEDGER.md:3323 | `hass.tests.test_shelf_command` → `hass/tests/test_shelf_command.py` | yes | — |
| BUILD_LEDGER.md:3331 | `hass.tests.test_listing_store` → `hass/tests/test_listing_store.py` | yes | — |
| BUILD_LEDGER.md:3339 | `hass.tests.test_listing_by_name` → `hass/tests/test_listing_by_name.py` | yes | — |
| BUILD_LEDGER.md:3339 | `hass.tests.test_post_by_name` → `hass/tests/test_post_by_name.py` | yes | — |
| BUILD_LEDGER.md:3347 | `hass.tests.test_cancel_all` → `hass/tests/test_cancel_all.py` | yes | — |
| BUILD_LEDGER.md:3355 | `hass.tests.test_command_typo` → `hass/tests/test_command_typo.py` | yes | — |
| BUILD_LEDGER.md:3363 | `hass.tests.test_photo_caption_reader_failed` → `hass/tests/test_photo_caption_reader_failed.py` | yes | — |
| BUILD_LEDGER.md:3363 | `hass.tests.test_status_reader_failed` → `hass/tests/test_status_reader_failed.py` | yes | — |
| BUILD_LEDGER.md:3371 | `hass.tests.test_design_notes` → `hass/tests/test_design_notes.py` | yes | — |
| BUILD_LEDGER.md:3385, 3387 | `reports/maker-links-2026-11.md` | yes | — |
| BUILD_LEDGER.md:3393 | `reports/organic-badges-2026-11.md` | yes | — |
| BUILD_LEDGER.md:3457, 3497, 3505 | `hass/chat/reports_pack.py` | yes | — |
| BUILD_LEDGER.md:3475 | `hass.tests.test_readonly_questions` → `hass/tests/test_readonly_questions.py` | yes | — |
| BUILD_LEDGER.md:3513 | `reports/unsourced-products-2026-11.md` | yes | — |
| HERMES_HANDOFF.txt:61 | `[checkout]/storefront-mockup/community-server.py` → `storefront-mockup/community-server.py` | yes | — |
| HERMES_HANDOFF.txt:75 | `hiking.css` → `storefront-mockup/hiking.css` | yes | — |
| HERMES_HANDOFF.txt:80 | `trail-explorer.css` → `storefront-mockup/trail-explorer.css` | yes | — |
| HERMES_HANDOFF.txt:81 | `assets/trails/` → `storefront-mockup/assets/trails` | yes | — |
| HERMES_HANDOFF.txt:85 | `reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt` | yes | — |
| HERMES_HANDOFF.txt:90 | `.gitignore` | yes | — |
| HERMES_HANDOFF.txt:97 | `reports/hermes-handoff/backup-community.py` | yes | — |
| HERMES_HANDOFF.txt:108 | `reports/hermes-handoff/migration-verification.json` | yes | — |
| hass/README.md:3 | `../docs/hass/README.md` → `docs/hass/README.md` | yes | — |
| hass/README.md:11 | `content/products.json` → `hass/content/products.json` | yes | — |
| hass/README.md:11 | `storefront-mockup/catalog-products.js` | yes | — |
| hass/README.md:12 | `content/makers.json` → `hass/content/makers.json` | yes | — |
| hass/README.md:12 | `storefront-mockup/producers.js` | yes | — |
| hass/README.md:12 | `storefront-mockup/producers.json` | yes | — |
| hass/README.md:13 | `content/community.json` → `hass/content/community.json` | yes | — |
| hass/README.md:13 | `storefront-mockup/community.json` | yes | — |
| hass/README.md:14, 136 | `content/store.json` → `hass/content/store.json` | yes | — |
| hass/README.md:15 | `templates/hike/index.html` → `hass/templates/hike/index.html` | yes | — |
| hass/README.md:15 | `templates/index.html` → `hass/templates/index.html` | yes | — |
| hass/README.md:24 | `hass/content` | yes | — |
| hass/README.md:30 | `content/migration-baseline.json` → `hass/content/migration-baseline.json` | yes | — |
| hass/README.md:42 | `hass/content/makers.json` | yes | — |
| hass/README.md:42 | `hass/content/store.json` | yes | — |
| hass/README.md:58 | `[checkout]/storefront-mockup` → `storefront-mockup` | yes | — |
| hass/README.md:107 | `hass/tests/fixtures/conversation-basic.jsonl` | yes | — |
| hass/README.md:112 | `hass/tests/fixtures/media` | yes | — |
| hass/README.md:127 | `hass/tests/test_preview.py` | yes | — |
| hass/README.md:149 | `../docs/hass/PHONE_GUIDE.md` → `docs/hass/PHONE_GUIDE.md` | yes | — |
| hass/README.md:206 | `hass/receiver.py` | yes | — |
| hass/README.md:210 | `hass/tests/fixtures/label-eval.jsonl` | yes | — |
| hass/README.md:230 | `HANDOVER.md` → `docs/hass/HANDOVER.md` | yes | — |
| hass/README.md:230 | `TRIAL.md` → `docs/hass/TRIAL.md` | yes | — |
| hass/README.md:284 | `FEATURES` → `docs/hass/FEATURES.md` | yes | — |
| hass/README.md:292 | `limits` → `docs/hass/LIMITS.md` | yes | — |
| hass/README.md:292 | `phone guide` → `docs/hass/PHONE_GUIDE.md` | yes | — |
| mac/README.md:7 | `mac/hass_forwarder.py` | yes | — |
| mac/README.md:32 | `the plist` → `mac/com.avocadoshack.hass-forwarder.plist.template` | yes | — |
| mac/README.md:47 | `runbook add-on` → `docs/hass/MAC_RUNBOOK.md` | yes | — |
| mac/README.md:70 | `hass/stagelog.py` | yes | — |

The following are deliberately not treated as missing tracked source:

| Doc:line | Off-tree reference class | Why not a checkout fix |
| --- | --- | --- |
| `README.md:44–46`; `HERMES_HANDOFF.txt:9–14,55–61,93–99`; `BUILD_LEDGER.md:112,496–498,537–539` | Historical absolute checkout / backup locations, deployment files, credential and database locations. Host paths omitted. | The relative targets inside the checkout are above; installed copies and private data were not probed. `community-data` is explicitly ignored (`.gitignore:2`). |
| `hass/README.md:41–49,58,61,96–97,117–119,127–132,158,172–182,198,211,215`; `mac/README.md:11–18,32–34,37–39,69–71,78–79,89–93` | State and backup filenames/patterns, temporary screenshots, config/CLI placeholders, browser dependencies, Mac tools and installed service identifiers. | Inputs or outputs at runtime, not expected files under `main`; no actual runtime inputs were read. |
| `BUILD_LEDGER.md:882,1679,1857,1873,1953,2241,2943` | Generated image path pattern, tool dependencies, external pre-push helper, synthetic bad-date filename. | The image directory is tracked; the runtime-derived filename/negative fixture is not a missing source file. A pre-push receipt does not name a repo script. |

## R2. Script and flag checks

No tracked entry script is absent from the current checkout commands after resolving their documented context. The mismatches below are important distinctions: an old absolute path is not a missing Git blob; a missing archive receipt is not a missing executable; and an incomplete invocation is not evidence that a flag was removed.

| Command or reference | Offline result and source |
| --- | --- |
| `python3 storefront-mockup/community-server.py --port 3101` (`README.txt:8–9`; `HERMES_HANDOFF.txt:59–61`) | Tracked entry; `--port` is declared at `storefront-mockup/community-server.py:134`. The handoff's absolute checkout prefix (omitted here) is not portable; this audit did not look at the host path. |
| `python3 reports/hermes-handoff/backup-community.py` (`HERMES_HANDOFF.txt:96–99`) | Entry exists and declares both documented options (`reports/hermes-handoff/backup-community.py:4`); the private paths are operands, not tracked files. |
| `sitegen.py` publish, check-publish, check, write and out forms (`README.md:34`; `hass/README.md:23–25,273`; `BUILD_LEDGER.md:2223,2229,2601`) | All named switches still declared (`hass/sitegen.py:633–644`). `BUILD_LEDGER.md:2229` describes a published build in prose, not a complete copy-paste command: `--publish` requires `DIR`. |
| `migration_check.py`; `unittest discover`; named dotted test modules (`hass/README.md:26–27`; ledger test receipts) | Entry and discovery folder tracked; dotted repo test paths and glob targets are indexed in R1. The absent `hass/tests/test_hike_create_repeat.py` is explicitly a cancelled design, not an invocation or an acceptance test to recreate (`BUILD_LEDGER.md:1663`). |
| `editor.py` init, prepare, apply, show/recover/ops, install, history (`hass/README.md:46–49,57,120,122`) | Names and flags declared (`hass/editor.py:643–656`). The `show … \| recover \| ops` typography at line 49 means alternatives, not a literal shell pipeline. |
| `fixture_chat.py` fixture, preview, photos and queue forms (`hass/README.md:107–112,119,206`; `BUILD_LEDGER.md:768–770`) | Entry and the named fixture files exist. The bare `--queue` shorthand at line 206 is not a complete invocation: the accepted flag takes `START_AT`, as the earlier ledger spells out (`hass/fixture_chat.py:126–135`). `--state`, `--fixture` and `--interpreter` are required; `--photos` takes a directory. |
| `health.py` (`hass/README.md:159–162,264`; `BUILD_LEDGER.md:946,2407–2409`) | `--seen`, `--model`, `--model-name`, `--unverified-hours`, `--min-free-mb` and `--writer` are all accepted. The shorthand is not standalone: parser requires `--state` (`hass/health.py:452–469`). |
| `statebackup.py` create/list/verify/restore/drill; retention report (`hass/README.md:172–176,215`; `BUILD_LEDGER.md:754,826,914,1146,1282`) | Entries and documented flags exist. `--paused` belongs to `restore`, not `drill` (`hass/statebackup.py:573–585`); the drill note describes the internal restore step. Retention's `--days`, `--state`, `--now`, `--media`, `--backups` are declared (`hass/retention.py:178–185`). |
| `label_eval.py` score and operator-only live forms; `acceptance.py` (`hass/README.md:210–211,229`; `BUILD_LEDGER.md:2539,2643,3537`) | Score/live options shown are accepted in their respective modes (`hass/label_eval.py:137–155`); `--only` exists (`hass/acceptance.py:132–135`). No model or acceptance runner used for this audit. |
| `backlog.py top`, `capabilities.py --check`, `testkit.py selftest` (`BUILD_LEDGER.md:74,94,100`) | Entries and switches/subcommands exist (`hass/skills/backlog.py:194–203`; `hass/capabilities.py:100–104`; `hass/skills/testkit.py:852–861`). |
| Historical Node/Python QA (`BUILD_LEDGER.md:545,1252,1260,1268,1857,1961,2065,2211,2223,2229,2443,2515,2571,2767,2959`) | `catalog-only-qa.cjs`, `community-qa.py`, `community-ui-qa.cjs`, `trail-map-retry-qa.cjs`, `static-site-qa.cjs`, `site-contrast.test.cjs`, `site-contrast-qa.cjs` and `site-contrast-qa.py` exist under `storefront-mockup/`. Static QA expects a directory (`storefront-mockup/static-site-qa.cjs:12`); contrast `--write`/`--check` exist (`storefront-mockup/site-contrast-qa.py:216–222`). A bare QA script name in a dated receipt does not supply its fixture, dependencies or operands. |
| Historical `npm ci` / optimized build (`BUILD_LEDGER.md:165`) | The commerce and nested storefront manifests and locks are tracked. There is a root `package-lock.json`, but no root `package.json`. This is not a root install instruction and not a missing npm script. Reproduce with `git ls-tree origin/main -- package.json package-lock.json` and `git ls-tree -r --name-only origin/main -- commerce/package.json commerce/package-lock.json commerce/storefront/package.json commerce/storefront/package-lock.json`. |
| Mac cross-check (`mac/README.md:7,65–67,69–71,92–93`) | The forwarder and stage-log script are tracked. `serve`, `status`, `check`, `ackcheck` and `--config` are declared (`mac/hass_forwarder.py:810–812`); `stagelog` takes positional logs (`hass/stagelog.py:105–115`). Git, SSH, systemctl/journalctl and launchctl are outside the missing-repo-script test. Installed applicability is unverified. |

Reproduce the argument findings without running any script: `git grep -n -E 'add_argument|add_parser|parse_args|process\.argv' origin/main -- hass/sitegen.py hass/editor.py hass/fixture_chat.py hass/health.py hass/statebackup.py hass/retention.py hass/label_eval.py storefront-mockup/community-server.py storefront-mockup/static-site-qa.cjs mac/hass_forwarder.py`; read the cited surrounding lines for required arguments and mode rules. No documented application flag was verified as removed from an extant CLI. No live site, network, state, commands involving owner messages, or historical check was replayed.

## R3. Current and historical folders

| Topic | Statements on main | Reading |
| --- | --- | --- |
| Site tree vs. prototypes | `AGENTS.md:3–5`: “Current source is storefront-mockup/. The commerce/ prototype and older proposals are historical.” `README.md:37`: “The active code is in [`storefront-mockup/`](storefront-mockup/). The `commerce/` prototype and earlier proposals are historical.” `README.txt:7,28`: “Current project: storefront-mockup/” and “commerce/ is the earlier Medusa prototype, retained for reference.” `HERMES_HANDOFF.txt:17,33–34`: “The active site is storefront-mockup/” and “The commerce/ folder is a HISTORICAL Medusa/Next.js prototype, not the active site”. | No contradiction about the active site directory. `BUILD_LEDGER.md:2–4` also says “The active product is the private catalog/community website in storefront-mockup/. Earlier commerce objectives below are historical.” Its older “a complete private branded commerce website” objective (`:103`) is historical, not a second instruction for current work. `BUILD_LEDGER.md:511` says “Preserve previous commerce UI under storefront-mockup/archive/commerce-preview”; `storefront-mockup/README.md:7,41` corroborates that the UI and evidence there are prior versions. |
| Where to edit content | `HERMES_HANDOFF.txt:73–83`: “FILES TO EDIT”, “shop.js: catalog interactions; catalog-products.js: active food records.”, “producers.json and producers.js: keep both maker datasets in sync.” and “All above are under storefront-mockup/.” `hass/README.md:7`: “`hass/content/` is the single editable source for site content. Edit it, never the generated files.” `storefront-mockup/README.md:10`: “Edit the source there; a hand edit here fails the check.” | **Conflict if followed literally.** The handoff lists generated output as editable. `hass/README.md:9–15` distinguishes `hass/content/` data and `hass/templates/` layouts from the generated storefront files. Not all storefront files are generated; the disagreement is about generated targets, not which folder contains the site. |
| Working copy across the migration | `BUILD_LEDGER.md:530`: “Authoritative working copy remains on Mac.” `HERMES_HANDOFF.txt:38`: “Older plans and ledger entries are historical, not authorization to restore them.” `README.md:44–46` distinguishes its working-checkout entry from the “Preserved original project”. | Time-dependent difference, not competing current instructions. Ledger `:536–540` explicitly records the later migration. None of these statements establishes that a particular host location serves this audited revision. |

## R4. Ranked gaps and one possible follow-up

1. **Wrong edit target:** following `HERMES_HANDOFF.txt:73–83` literally risks changing committed outputs instead of generator inputs (`hass/README.md:7–15`; `storefront-mockup/README.md:10`).
2. **Nonportable quickstart and incomplete CLI shorthand:** `README.md:44`, `HERMES_HANDOFF.txt:12,59–61`, `hass/README.md:159,206,264`; the repo-relative server target exists, but the historical checkout prefix and missing required operands are not safe defaults for a new builder (R2).
3. **Old evidence paths:** `BUILD_LEDGER.md:119–129,476,486–505,1663`. The archived `shop-QA.json` has a confirmed match. Missing private/historical evidence and the intentionally unbuilt repeat test are not current blockers and should not be recreated to make names resolve.

**One proposed docs-only unit (estimate: 60–90 minutes; not implemented here).** In `HERMES_HANDOFF.txt`, label the old checkout example as historical and distinguish generated site outputs from their editable source; in `hass/README.md`, make the fixture queue and health shorthand show required placeholder operands. Leave service/network procedures, historical evidence, installed paths/config, approval rules and data unchanged. Offline acceptance: `git diff --check`; verify every newly written tracked path with `git cat-file -t HEAD:<path>` and compare each amended switch/required placeholder to the parser anchors in R2 with `git grep`. No server, historical QA, model or owner action is needed for that check. This report itself changes neither of those docs.
