# AVO1343-10 — Historical commerce script map

| Finding | Result at the audited main |
| --- | --- |
| Inventory | 80 tracked files in `commerce/scripts/`: 65 `*-smoke.mjs`, the standalone `smoke.mjs`, 13 other `.mjs` files and one Swift file (R1 inventory command). |
| Package wiring | 3 distinct files: `database.mjs`, `start.mjs`, and `setup.mjs` (`commerce/package.json:5–9`). None of the 66 smoke files is reached from a package script. |
| `check` workflow wiring | 1 file, `setup.mjs`, through the gateway setup unit test; this is already in the package count (`.github/workflows/check.yml:102–107`; `commerce/gateway/setup.test.mjs:1–16`). |
| Orphaned from both | 77 files, including all 66 smoke files (R1). Some have manual callers or are imported by other orphaned scripts. |
| Missing gateway references | No missing gateway module or route identified in the tracked source; there are runtime-only prerequisites (R2). |
| Recommendation | Keep the archive out of the active site and Hass pipeline. No build unit is needed (R4; `AGENTS.md:3–5,16`). |

Audited 2026-11-21. The fresh clone's `origin/main` was the requested `37feae1dc5efa6968f90d17a1eda6daed29afd4a`. The current catalog source is `storefront-mockup/`; `commerce/` is historical (`AGENTS.md:3–5`; `HERMES_HANDOFF.txt:33–35`). This is a static map: only tracked source and documentation were inspected. No commerce scripts or services were run, and no credential files or private artifacts were opened.

## R1. Every script and what it needs

Bare script names and line-only references in the tables are relative to `commerce/scripts/`. **Orphaned** means no executable path from the tracked package scripts or `check.yml`, not unused everywhere. `No` in a dependency column means the cited source does not require that resource. Network includes loopback TCP (including PostgreSQL); the script-level network targets are local. That is not a guarantee about a backend configured outside the documented simulator mode (`commerce/README.md:39–43`). `Yes, gateway` in the DB column means indirect: the cited login starts a DB-backed session (`commerce/gateway/server.mjs:4,10`); `Yes, direct` means a connection from the script itself. `Files only` means no running DB. Secret means required private credential or configuration input; this includes a file the code insists on loading even when it does not use every value. No credential values are included here.

| File | Purpose (source lines) | Package / `check` wiring | Network | Database | Secret |
| --- | --- | --- | --- | --- | --- |
| `activity-smoke.mjs` | Owner-only persisted activity, ordering and result limits (6–10). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `approval-comparison-smoke.mjs` | Exact approval comparison; role/version/stock checks and receipt invalidation (4–10). | orphaned | Yes :2 | Yes, gateway :2 | Yes :2 |
| `astra-worker-smoke.mjs` | Worker authentication, interpretation and outage fallback; runs simulated packing/refund afterward (2–7). | orphaned | Yes :2–5 | Yes, gateway :5 | Yes :2–5 |
| `backup.mjs` | Copies stopped DB, media, intake and private config to local backup (2–4). | orphaned | No :2–4 | Yes, files only :2–4 | Yes :4 |
| `bootstrap.mjs` | Seeds prototype settings, imported drafts, confirmed sample and pickup windows (5–17). | orphaned | Yes, PG :4 | Yes, direct :4–5 | Yes :3–4 |
| `box-draft-smoke.mjs` | Box-text draft replay; blocks incomplete box approval and catalog exposure (6–11). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `box-intake-atomic-smoke.mjs` | Rolls back failed box/evidence insert; retries multi-photo intake and event replay (7–18). | orphaned | Yes :3 | Yes, direct :2,7–10 | Yes :2–3 |
| `box-revision-guards-smoke.mjs` | Revision endpoint role, event and source guard checks (5–12). | orphaned | Yes :3 | Yes, direct :2,6 | Yes :2–3 |
| `cancel-status-smoke.mjs` | Per-session order status, cancellation/replay and blocked payment after cancel (5–9). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `cancellation-intent-smoke.mjs` | Interrupted cancellation, closed-session recovery and late-payment/refund handling (3–8). | orphaned | Yes :2 | Yes, direct :2–7 | Yes :2 |
| `candidate-smoke.mjs` | Splits one shelf-photo candidate into a linked private draft and checks replay (5). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `catalog-availability-smoke.mjs` | Reservation changes reported catalog availability; cancel releases the hold (2). | orphaned | Yes :1 | Yes, gateway :1 | Yes :1 |
| `checkout-recovery-smoke.mjs` | Interrupted cart preparation recovers the same hold/cart/session; expiry releases holds (5–9). | orphaned | Yes :3 | Yes, direct :2,5–9 | Yes :2–3 |
| `checkout-reset-smoke.mjs` | Rejects changed frozen basket and other-session reset; checks reset replay and new checkout (7–18). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `checkout-smoke.mjs` | Server-priced checkout, simulator payment and one order/task after replay; writes a summary (3). | orphaned; imported by `fulfillment-recovery-smoke.mjs:2`, `packing-atomic-smoke.mjs:2`, `packing-exception-smoke.mjs:2`, `photo-replacement-smoke.mjs:2` | Yes :2 | Yes, gateway :2 | Yes :2 |
| `content-message-smoke.mjs` | Owner text accumulates in unpublished copy; rejects stale approval and restores prior draft state (6–19). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `context-photo-smoke.mjs` | Context-only overview photos cannot split or publish; checks persistence through edits (2). | orphaned | Yes :1 | Yes, direct :1–2 | Yes :1 |
| `contrast-check.mjs` | Static CSS color pairs, hover selector and dimensions; no rendered browser check (2). | orphaned | No :1–2 | No :1–2 | No :1–2 |
| `correction-history-smoke.mjs` | Stock correction links an earlier same-product movement; checks persistence, roles and stock readback (8–23). | orphaned | Yes :3,8 | Yes, direct :2,7,22 | Yes :2–3,8 |
| `customer-photo-history-smoke.mjs` | Accepted order photo survives replacement; unrelated customer denied; refunds test order (3–5). | orphaned | Yes :2 | Yes, gateway :2 | Yes :2 |
| `database.mjs` | Initializes/starts embedded PostgreSQL and creates the application DB if missing (8–15). | `npm run database` (`commerce/package.json:6`); also `npm start` via `start.mjs:9` (`commerce/package.json:7`) | Yes, PG :9–11 | Yes, starts/queries :9–12 | Yes on existing DB; generates for fresh :7–9 |
| `dictated-unit-smoke.mjs` | Sends text for unit/price extraction; missing stock stays unknown (2). | orphaned | Yes :1 | Yes, gateway :1 | Yes :1 |
| `draft-rejection-smoke.mjs` | Exact-version rejection retains evidence, blocks stale/packer actions and checks replay (5–16). | orphaned | Yes :3 | Yes, direct :2,14–15 | Yes :2–3 |
| `editorial-smoke.mjs` | Copy approval plus ordering-pause and pickup-window checkout guards; restores settings (8–22). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `feature-message-smoke.mjs` | Private homepage feature proposal, exact approval, revision guard and restoration (8–24). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `fixed-package-smoke.mjs` | Weight-priced intake asks for fixed package; unsupported sale stays unpublished (1). | orphaned | Yes :1 | Yes, gateway :1 | Yes :1 |
| `frozen-price-recovery-smoke.mjs` | Cart recovery/payment preserve saved quote despite a later catalog price update (6–14). | orphaned | Yes :3 | Yes, direct :2,6–8 | Yes :2–3 |
| `fulfillment-recovery-smoke.mjs` | Lost ready/collected acknowledgments recover one fulfillment and one audit per step; refund cleanup (14–27). | orphaned | Yes :4 | Yes, direct :14–18 | Yes :3–4,14 |
| `heic-upload-smoke.mjs` | Generated HEIC-format fixture: local decode, bounded JPEG, private original and replay (2–5). | orphaned | Yes :3 | Yes, gateway :3 | Yes :3 |
| `hours-message-smoke.mjs` | Hours copy stays private; earlier copy, pickup windows and accepted task snapshots preserved (6–19). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `import-label-access-smoke.mjs` | Owner can read private imported OCR evidence; visitor and packer cannot (4–5). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `import-label-evidence.mjs` | Imports local OCR into eligible drafts and verifies that replay leaves versions/fields unchanged (2–4). | orphaned | Yes, PG :2–3; OCR is local executable (`commerce/gateway/vision.mjs:3`) | Yes, direct :2–4 | Yes :2 |
| `import-photo-candidates.mjs` | Imports reviewed candidate notes into eligible private drafts; idempotent audit entries (1). | orphaned | Yes, PG :1 | Yes, direct :1 | Yes :1 |
| `integrity-test.mjs` | Auth, stale approvals, concurrent reservation, expiry and approval replay (6–20). | orphaned | Yes :3,13 | Yes, direct :2,15–17 | Yes :2–3 |
| `late-payment-smoke.mjs` | Injects late simulator payment; checks review status without a packing task (6–18). | orphaned | Yes :3 | Yes, direct :2,9–13 | Yes :2–3 |
| `late-refund-smoke.mjs` | Repairs earlier capture/refund, retries lost acknowledgment and checks release without a pack task (3–12). | orphaned | Yes :2 | Yes, direct :2–3,6–10 | Yes :2 |
| `legacy-late-refund-smoke.mjs` | Adopts legacy simulated payment into native session and refunds exactly once (3–5). | orphaned | Yes :4 | Yes, direct :2–3,5 | Yes :2,4 |
| `local-vision-corpus.mjs` | Batch-evaluates preview photos with the local model; writes evidence, not catalog changes (1–4). | orphaned | Yes, local model :2,4; `commerce/astra/photo-model.mjs:3–4,10` | No :1–4 | No :1–4; `commerce/astra/photo-model.mjs:3–10` |
| `local-vision-smoke.mjs` | Uploads photos and checks local interpretation, unknown fields and unpublished drafts (6–14). | orphaned | Yes :3,8 | Yes, gateway :3 | Yes :2–3 |
| `marketing-smoke.mjs` | Creates private marketing drafts and checks owner gate and event replay; no sending (5). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `multi-photo-invalid-smoke.mjs` | Rejects mixed valid/invalid batch with no saved media or persisted evidence (2–4). | orphaned | Yes :3–4 | Yes, direct :2,4 | Yes :2–3 |
| `multi-photo-smoke.mjs` | Private multi-photo draft, duplicate linking and original/derivative access (4–7). | orphaned | Yes :3–5 | Yes, gateway :3 | Yes :2–3 |
| `numeric-intake-smoke.mjs` | Fractional quantity and excessive price precision stay unknown and block approval (3–4). | orphaned | Yes :2 | Yes, gateway :2 | Yes :2 |
| `ocr.swift` | “Local label evidence only.” Apple Vision OCR reads a local image and writes JSON (4–20). | orphaned; gateway invokes a runtime binary, not this file (`commerce/gateway/vision.mjs:3`) | No :5–20 | No :5–20 | No :5–20 |
| `order-task-recovery-smoke.mjs` | Native paid order survives failed task checkpoint; replay keeps one order/task (3–5). | orphaned | Yes :2 | Yes, direct :2–5 | Yes :2 |
| `packing-atomic-smoke.mjs` | Audit fault rolls back staff assignment, then completes/refunds the same test order (9–20). | orphaned | Yes :6,12 | Yes, direct :5,7–16 | Yes :3,5–6 |
| `packing-exception-smoke.mjs` | Assignment/shortage resolution and ordered packing transitions, collection and simulator refund (6–17). | orphaned; imported by `astra-worker-smoke.mjs:7`, `packing-atomic-smoke.mjs:19`, `photo-replacement-smoke.mjs:14`, `pickup-worker-smoke.mjs:8` | Yes :4 | Yes, gateway :4 | Yes :3–4 |
| `packing-order-smoke.mjs` | Read-only task sort check: active before terminal, each sorted by pickup due time (4–7). | orphaned | Yes :3–4 | Yes, gateway :3 | Yes :2–3 |
| `packing-smoke.mjs` | One transition on an existing paid task; rejects packer catalog approval (2). | orphaned | Yes :2 | Yes, gateway :2 | Yes :2 |
| `paid-order-restart-smoke.mjs` | Captures paid-order record hashes, or compares them after an external restart and checks replay/refund (3–4). | orphaned | Yes :2 | Yes, direct :2–4 | Yes :2 |
| `pause-restore-smoke.mjs` | Product pause blocks checkout; copy history restore creates a versioned draft (5–9). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `payment-webhook-smoke.mjs` | Offline provider signature and event persistence checks in a rolled-back transaction (6–18). | orphaned; manual check documented in `commerce/README.md:113` | Yes, PG :3–5; no Stripe API :6–7 | Yes, direct via provider connection :5,10–18 | Yes, local DB config :3; no real Stripe key required :4–7 |
| `photo-candidates-smoke.mjs` | Reviewed photo-note inventory, context-only overviews and private child replay (2). | orphaned | Yes :1 | Yes, gateway :1 | Yes :1 |
| `photo-replacement-smoke.mjs` | Replaces catalog photo without changing an accepted snapshot; completes packing cleanup (8–14). | orphaned | Yes :4,8–11 | Yes, direct :4,10 | Yes :3–4 |
| `photo-retention-smoke.mjs` | Text-only update retains approved product photo through publication (2). | orphaned; imported by `feature-message-smoke.mjs:14` | Yes :2 | Yes, gateway :2 | Yes :2 |
| `pickup-command-smoke.mjs` | Versioned pickup closure/reopen, replay, role guards and preserved accepted instructions (9–25). | orphaned | Yes :3 | Yes, direct :4,15 | Yes :2–4 |
| `pickup-completion-smoke.mjs` | Existing checkout completes after a pickup closure; reopening and cleanup follow (18–29). | orphaned | Yes :4 | Yes, gateway :4 | Yes :3–4 |
| `pickup-worker-smoke.mjs` | Last-slot race plus local OCR outage; simulated order/packing/refund during outage (5–9). | orphaned | Yes :3–4 | Yes, gateway :3 | Yes :2–3 |
| `prepare-media.mjs` | Prepares local preview media and optionally derives a portrait (1–3). | orphaned | No :1–3 | No :1–3 | No :1–3 |
| `primary-photo-smoke.mjs` | Requires valid primary-photo selection, checks persisted choice and blocks unreviewed publication (2). | orphaned | Yes :1–2 | Yes, gateway :1 | Yes :1 |
| `private-media-smoke.mjs` | Role access to imported/uploaded and historical task images, while allowed catalog assets remain accessible (1–3). | orphaned | Yes :1 | Yes, direct :3 | Yes :1,3 |
| `product-details-smoke.mjs` | Rejects malformed details and verifies approved detail readback (3–12). | orphaned | Yes :2–3 | Yes, gateway :2 | Yes :2 |
| `product-stock-receipt-smoke.mjs` | Product approval retry after lost audit acknowledgment preserves later stock movement (6–15). | orphaned | Yes :2 | Yes, direct :2–3,6–8 | Yes :2 |
| `recovery-queue-smoke.mjs` | Role-restricted recovery queue and reconciliation without duplicate pack work (5–7). | orphaned | Yes :3 | Yes, direct :2,6–7 | Yes :2–3 |
| `refund-smoke.mjs` | Owner simulator refund and replay; denies packer and checks catalog unchanged (6–11). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `restore-product-photo.mjs` | Uploads and applies the sample product photo through draft approval; a write utility (2). | orphaned | Yes :2 | Yes, gateway :2 | Yes :2 |
| `restore-test.mjs` | Starts isolated restored DB and compares row hashes, assets and private configuration against original (2–8). | orphaned | Yes, PG :4,7–8 | Yes, direct :4,7–8 | Yes :2,4,8 |
| `safety-buffer-smoke.mjs` | Version and role guards on buffer values; competing baskets respect availability (8–20). | orphaned | Yes :3,8 | Yes, direct :2,7 | Yes :2–3,8 |
| `scheduled-expiry-smoke.mjs` | Native timed special expires without a scheduler update; pre-expiry quote honored (5–9). | orphaned | Yes :2 | Yes, gateway :2 | Yes :2 |
| `scheduled-special-smoke.mjs` | Dated offer proposal, approval/conflict gates, pricing and checkout/cancellation (8–21). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `setup.mjs` | Prepares or preserves private configuration and role access files (2–6). | `npm run setup` (`commerce/package.json:9`); `npm test` (`:8`) and workflow “Commerce gateway unit tests” (`.github/workflows/check.yml:102–107`) call `prepare` via `commerce/gateway/setup.test.mjs:1–16`; neither invokes the CLI (:6). | No :2–6 | No running DB; version marker only :2 | No preexisting secret on fresh setup; yes on existing DB :2–3 |
| `smoke.mjs` | Authenticated bootstrap and exact-sample draft approval with catalog readback (5–7). | orphaned | Yes :3–4 | Yes, gateway :3 | Yes :2–3 |
| `special-command-smoke.mjs` | Immediate special review/approval; previous checkout quote retained and test offer removed (7–15). | orphaned | Yes :3 | Yes, gateway :3 | Yes :2–3 |
| `start.mjs` | Launches and waits for local DB, backend, gateway and storefront, with optional vision components (6–9). | `npm start` (`commerce/package.json:7`) | Yes, local probes :7–9 | Yes, starts and probes :9 | Yes :9 |
| `stock-race-smoke.mjs` | Competing checkout holds and counter transfer cannot overdraw; checks movement replay (7–16). | orphaned | Yes :3,11 | Yes, direct :2,10,14–15 | Yes :2–3,11 |
| `stock-receipt-recovery-smoke.mjs` | Retries a stock receipt after audit failure without undoing later movement (6–15). | orphaned | Yes :2 | Yes, direct :2–3,6–7 | Yes :2 |
| `stock-receipt-restart-smoke.mjs` | Replays an already-applied stock receipt against a running backend and checks no overwrite (3–4). | orphaned | Yes :4 | Yes, direct :2–3 | Yes :2,4 |
| `superseded-product-smoke.mjs` | Older interrupted approval cannot overwrite a replacement; verifies exact-version closure (7–19). | orphaned | Yes :2 | Yes, direct :2–3,6–7 | Yes :2 |
| `text-details-smoke.mjs` | Takes structured detail text into a private replay-safe draft without updating catalog (3–8). | orphaned | Yes :2,4 | Yes, gateway :2 | Yes :2 |
| `unpacked-refund-smoke.mjs` | Verifies paid snapshot and reservation release after refund without physical restock (6–10). | orphaned | Yes :3 | Yes, direct :2,7–9 | Yes :2–3 |

`commerce/README.md:14–19,41–45,113` documents manual commands, not automation. In particular, manual bootstrap, media prep, backup, restore and webhook checks do not change the wiring count. The package `test` entry selects `commerce/gateway/*.test.mjs` from the package root; the workflow invokes that suite directly, excluding `owner-photo.test.mjs` because it needs `sharp` (`commerce/package.json:8`; `.github/workflows/check.yml:102–107`). The only path from those tests into `commerce/scripts/` is setup. The workflow's site check starts the separate current-site server (`.github/workflows/check.yml:226–235`), not the commerce preview.

## R2. Missing gateway modules or routes

**None identified in the tracked tree.** This does not establish that a running service, runtime artifact or required fixture is available. These are easy references to misread:

| Quoted script reference | What resolves it at this main |
| --- | --- |
| `../gateway/pickup-time.mjs`, `../gateway/interpret.mjs` (`bootstrap.mjs:1–2`); `../gateway/vision.mjs`, `../gateway/astra-client.mjs` (`import-label-evidence.mjs:1`); `../gateway/owner-photo.mjs` (`heic-upload-smoke.mjs:1`); `../gateway/packing.mjs` (`fulfillment-recovery-smoke.mjs:1`, `packing-exception-smoke.mjs:1`, `packing-smoke.mjs:1`, `pickup-completion-smoke.mjs:1`); `gateway/server.mjs` (`start.mjs:9`) | All are tracked in `commerce/gateway/` (R2 tree command). |
| `/api/health` (`start.mjs:9`), `/health` and `/interpret` (`astra-worker-smoke.mjs:2–3`) | Gateway health is `commerce/gateway/server.mjs:124`; the other two are on the separate worker (`commerce/astra/server.mjs:4–5`). |
| `'/scheduled-specials/'` (`scheduled-special-smoke.mjs:9–14`, `scheduled-expiry-smoke.mjs:5,9`) | The caller adds `/api`; handlers are registered in `commerce/gateway/scheduled-special-routes.mjs:5,12`, attached from `commerce/gateway/server.mjs:123`. |
| `/internal/catalog`, `/internal/stock`, `/internal/move-stock` (`integrity-test.mjs:13`, `correction-history-smoke.mjs:8`, `safety-buffer-smoke.mjs:8`, `stock-race-smoke.mjs:11`, `stock-receipt-restart-smoke.mjs:4`) | These are backend, not gateway, URLs. `commerce/backend/src/api/internal/[operation]/route.ts:7–8,74,81` implements the GET catalog and the named POST operations; the backend middleware guards `/internal/*` (`commerce/backend/src/api/middlewares.ts:3`). |
| `/api/drafts/` with `/preview`, `/api/attempts/` with `/late-refund`, and `/media/` with the original filename (`import-label-access-smoke.mjs:4`, `legacy-late-refund-smoke.mjs:4`, `heic-upload-smoke.mjs:4`) | The gateway declares parameterized handlers (`commerce/gateway/server.mjs:19,32,53`); the tests' rejection/not-found assertions concern authorization or file visibility, not absence of the route. |
| `'../.runtime/ocr'` (`pickup-worker-smoke.mjs:7`) | Not a gateway module or route. The gateway's vision wrapper executes a runtime binary (`commerce/gateway/vision.mjs:3`); `ocr.swift:4–20` is tracked source. No claim about the binary on any host. |

## R3. Names that can misstate what runs

| Script | Quoted evidence and scope difference |
| --- | --- |
| `pickup-worker-smoke.mjs` | “Last-slot race: one checkout accepted, competitor rejected.” (:6); “Local photo reader offline” (:8). It tests two different things, not a dedicated pickup worker: booking contention and an OCR outage, then the imported packing journey (:5–9). |
| `stock-receipt-restart-smoke.mjs`, `paid-order-restart-smoke.mjs` | “After full process/database restart” (`stock-receipt-restart-smoke.mjs:4`); “After full restart” (`paid-order-restart-smoke.mjs:4`). The former only replays against an already-running backend (:2–5); the latter has prepare and verify phases but no restart command (:1–4). The names describe a manual scenario, not self-contained restart coverage (`BUILD_LEDGER.md:232,361`). |
| `payment-webhook-smoke.mjs` | “No Stripe API methods are available in this offline test” (:6). It calls `provider.getWebhookActionAndData` directly (:12–15); there is no HTTP webhook delivery or live Stripe end-to-end test. |
| `dictated-unit-smoke.mjs`, `heic-upload-smoke.mjs` | `call('/drafts',` (`dictated-unit-smoke.mjs:2`) receives a typed fixture, not phone dictation. “original camera file unavailable” (`heic-upload-smoke.mjs:5`): checks an encoded HEIC fixture and upload, not camera-origin capture. |
| `smoke.mjs` | “Owner-confirmed avocado applied:” (:6). A broad smoke name hides a specific state-changing approval, not a general read-only health probe (:5–7). |

Similar names do not by themselves indicate swapped flows: `candidate-smoke.mjs:5` focuses on one split, while `photo-candidates-smoke.mjs:2` adds reviewed-note and overview checks. `packing-order-smoke.mjs:4–7` checks sorting, whereas `packing-smoke.mjs:2` checks a state transition and a role guard.

## R4. Ranked gaps and recommendation

1. **Manual-run risk.** An orphan is not necessarily safe to run. Some stop or move a worker (`astra-worker-smoke.mjs:4`; `pickup-worker-smoke.mjs:7–8`), apply drafts (`smoke.mjs:6`), or deliberately write faults and cleanup to the DB (`packing-atomic-smoke.mjs:9–19`). Do not treat them as generic checks.
2. **Coverage attribution.** A green `check` is not evidence of checkout, worker outage, packing or payment smoke behavior. The workflow selects gateway unit tests and current-site checks, not the historical smoke entry points (`.github/workflows/check.yml:102–107,226–235`; R1). The historical docs themselves distinguish simulator results from real payment validation (`commerce/README.md:39–45`).
3. **Uncaptured prerequisites.** Some plausible names hide manual restart boundaries, runtime artifacts, or test-to-test dependencies (R2–R3; `heic-upload-smoke.mjs:2`; `restore-test.mjs:2–8`; `packing-exception-smoke.mjs:2–3`). Static source matches do not qualify these integrations.

**No build unit needed.** These are reference gaps for an explicitly historical prototype, not a reason to wire it into active CI, rename files, or run it against existing data (`AGENTS.md:3–5,13–16`).

### Offline reproduction

From the clone root, use the audited `origin/main` above (or substitute that full SHA if main has moved). These are source reads; no `node`, `npm`, workflow or service invocation is required. On 2026-11-21 the inventory returned 80 paths; the entry-point trace found the three package targets and the setup test bridge; the route pass checked the tracked modules and handlers, not HTTP responses.

```text
git rev-parse origin/main
git ls-tree -r --name-only origin/main -- commerce/scripts
git ls-tree -r --name-only origin/main -- commerce/gateway commerce/backend/src/api commerce/astra .github
git show origin/main:commerce/package.json
git show origin/main:.github/workflows/check.yml
git grep -n -o -E 'scripts/[a-z-]+\.mjs|\./[a-z-]+-smoke\.mjs' origin/main -- commerce/gateway commerce/scripts .github ':(glob)**/package.json'
git grep -n -o -E 'fetch\(|\b(Pool|Client|EmbeddedPostgres)\b|\.(query|connect)\(|config\.json' origin/main -- commerce/scripts
git grep -n -o -E "app\.(get|post|put|patch|delete)\('/[^']+'|scheduledSpecialRoutes|function (GET|POST)|op==='[^']+'" origin/main -- commerce/gateway/server.mjs commerce/gateway/scheduled-special-routes.mjs commerce/astra/server.mjs commerce/backend/src/api
git log --oneline origin/main -- commerce/gateway commerce/scripts
```

For each table row, use `git show origin/main:commerce/scripts/<file>` and inspect the cited lines. Trace relative module imports and child launches against the tree, and combine named request-helper suffixes with their prefix and method before comparing to parameterized route registrations. This does not detect external/manual invocations or runtime-only routing. No smoke pass, current hosted CI result, or current site availability is asserted.
