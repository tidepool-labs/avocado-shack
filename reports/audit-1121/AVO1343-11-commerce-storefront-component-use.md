# AVO1343-11 — Historical commerce storefront component use

| Question | Finding |
| --- | --- |
| R1. Which files are used? | All 13 tracked app files are reachable in the historical Next.js app: 2 framework entry files, 9 components imported directly by the page, 1 component imported through `BoxReview`, and 1 stylesheet imported by the layout. None are dead in that source tree. |
| R2. Which fetches have no route? | None: 47 request call sites reduce to 41 distinct HTTP method/path pairs, all registered by the gateway. |
| R3. Do the local guides agree? | Yes by reference: the storefront’s `CLAUDE.md` contains only `@AGENTS.md`. |
| R4. What should change? | No build unit needed. The route matches are static evidence about the historical prototype, not a reason to change or revive it. |

Source: `tidepool-labs/avocado-shack` `origin/main`, checked 2026-11-21 at `37feae1dc5efa6968f90d17a1eda6daed29afd4a` (exactly the requested baseline). Root `AGENTS.md:3–5` names `storefront-mockup/` as current source and `commerce/` as historical. All line references below are to that pinned tree. The supplied `reports/hass-npp/G-QUESTIONS.md` path is not tracked at that pin (see the tree command below); this audit makes no decision on the topics in that brief.

## R1. Every tracked file under `commerce/storefront/app/`

Filenames in this table are relative to `commerce/storefront/app/`. Ranges include blank lines. “None” in the import column means no explicit source import, not necessarily unused: in the Next.js App Router, `page.tsx` is the `/` entry and `layout.tsx` wraps it through `children` (`layout.tsx:4`); Next is declared at `commerce/storefront/package.json#/dependencies/next`. `page.tsx:3–11` imports the nine components it renders at `page.tsx:58–59`. `BoxReview` in turn renders `SwapEditor` at `box-review.tsx:8`. The table separates direct fetches from page callbacks and page-loaded data.

| File:lines | Imported by | Direct fetch or page wiring (browser-facing paths) |
| --- | --- | --- |
| `activity.tsx:1–3` | `page.tsx:9` | No fetch. Renders events from `GET /api/activity` (`page.tsx:32, 58`). |
| `box-review.tsx:1–9` | `page.tsx:3` | No fetch. Save, revise, and approve callbacks: `PATCH /api/boxes/{id}`, `POST /api/boxes/{id}/revise`, `POST /api/boxes/{id}/approve` (`box-review.tsx:8`, `page.tsx:58`); draft data can come from the page’s bootstrap (`page.tsx:32, 58`). |
| `editorial-controls.tsx:1–2` | `page.tsx:6` | No fetch. Page callbacks: `POST /api/content/restore`, `PATCH /api/content`, `POST /api/content/approve`, `PATCH /api/ordering`, `PATCH /api/pickup-slots/{id}` (`editorial-controls.tsx:2`, `page.tsx:58`); content/history/ordering and slots are supplied by the page (`page.tsx:32, 58`, `commerce/gateway/server.mjs:18`). |
| `globals.css:1–43` | `layout.tsx:1` | No fetch. Layout stylesheet. |
| `layout.tsx:1–4` | none (root layout) | No fetch; renders `children` (`layout.tsx:4`). |
| `marketing-controls.tsx:1–2` | `page.tsx:8` | No fetch. Prepare callback: `POST /api/marketing-drafts`; drafts come from `GET /api/bootstrap` (`marketing-controls.tsx:2`, `page.tsx:32, 58`, `commerce/gateway/server.mjs:18`). |
| `pack-task.tsx:1–3` | `page.tsx:7` | No fetch. Page callbacks: `PATCH /api/tasks/{id}`, `POST /api/tasks/{id}/resolve`, `POST /api/tasks/{id}/refund`; task list from `GET /api/bootstrap` (`pack-task.tsx:3`, `page.tsx:32, 42, 59`). |
| `page.tsx:1–62` | none (root page) | All app `fetch` expressions are here: `fetch('/api'+path, …)` at line 13 and `fetch('/api/drafts', …)` at line 58. Every resolved request path is listed in R2. |
| `pickup-review.tsx:1–2` | `page.tsx:10` | No fetch. Approval callback: `POST /api/pickup-proposals/{id}/approve`; proposals also come from bootstrap (`pickup-review.tsx:2`, `page.tsx:32, 58`, `commerce/gateway/server.mjs:18`). |
| `safety-buffer-controls.tsx:1–6` | `page.tsx:5` | No fetch. Page loads `GET /api/safety-buffers` and saves via `PATCH /api/safety-buffers/{product}` (`safety-buffer-controls.tsx:1–6`, `page.tsx:32, 58`). |
| `scheduled-special-review.tsx:1–4` | `page.tsx:11` | No fetch. Page callbacks: `POST /api/scheduled-specials/{id}/approve` and `POST /api/scheduled-specials/{id}/close`; drafts also come from bootstrap (`scheduled-special-review.tsx:4`, `page.tsx:32, 58`, `commerce/gateway/server.mjs:18`). |
| `stock-controls.tsx:1–18` | `page.tsx:4` | No fetch. Page loads `GET /api/stock-movements`; apply callback posts to the same path (`stock-controls.tsx:1–18`, `page.tsx:32, 58`). |
| `swap-editor.tsx:1–2` | `box-review.tsx:3` | No fetch; calls `onChange` to update parent form state (`swap-editor.tsx:2`, `box-review.tsx:8`). The parent’s separate save callback goes to `PATCH /api/boxes/{id}` (`page.tsx:58`). |

## R2. Fetch-path comparison

**No unmatched paths.** `page.tsx:13` prefixes helper arguments with `'/api'` and uses the supplied method, otherwise `'POST'` with a body or `'GET'` without one. The multipart submit at `page.tsx:58` explicitly uses `POST` and bypasses the helper. `commerce/storefront/next.config.mjs:1` rewrites `'/api/:path*'` to the gateway with the same path; `commerce/gateway/server.mjs:125` is the matching listener. The only route file under `commerce/backend/src/api/` is `internal/[operation]/route.ts`, which exports `GET` and `POST` (lines 7–8); `middlewares.ts:3` matches `'/internal/*'`. The gateway constructs `'/internal/'+op` for engine requests (`server.mjs:12`); none of the browser fetches target `/internal/` directly.

Below, `{id}` and `{product}` stand for a dynamic segment in the browser fetch string (order references include the `encodeURIComponent(reference)` form at `page.tsx:33`). The right column quotes the exact registered path; the method on the left matches the registration. Gateway filenames are relative to `commerce/gateway/`. The scheduled-special registrations are mounted at `server.mjs:123`.

| Method and browser fetch path | Frontend call site(s) | Registered gateway path and source |
| --- | --- | --- |
| GET `/api/drafts/{id}/preview` | `page.tsx:31, 58` | `/api/drafts/:id/preview` at `server.mjs:32` |
| GET `/api/bootstrap` | `page.tsx:32` | `/api/bootstrap` at `server.mjs:18` |
| GET `/api/pickup-slots` | `page.tsx:32` | `/api/pickup-slots` at `server.mjs:113` |
| GET `/api/exceptions` | `page.tsx:32` | `/api/exceptions` at `server.mjs:120` |
| GET `/api/stock-movements` | `page.tsx:32` | `/api/stock-movements` at `server.mjs:108` |
| GET `/api/safety-buffers` | `page.tsx:32` | `/api/safety-buffers` at `server.mjs:106` |
| GET `/api/activity` | `page.tsx:32` | `/api/activity` at `server.mjs:119` |
| GET `/api/session` | `page.tsx:33` | `/api/session` at `server.mjs:11` |
| GET `/api/orders/{id}` | `page.tsx:33, 54, 55` | `/api/orders/:id` at `server.mjs:49` |
| POST `/api/login` | `page.tsx:48` | `/api/login` at `server.mjs:10` |
| POST `/api/checkout` | `page.tsx:53` | `/api/checkout` at `server.mjs:36` |
| POST `/api/checkout/reset` | `page.tsx:53` | `/api/checkout/reset` at `server.mjs:59` |
| POST `/api/simulate-payment` | `page.tsx:54` | `/api/simulate-payment` at `server.mjs:48` |
| POST `/api/checkout/{id}/cancel` | `page.tsx:54` | `/api/checkout/:id/cancel` at `server.mjs:58` |
| POST `/api/drafts` | `page.tsx:58` | `/api/drafts` at `server.mjs:21` |
| POST `/api/scheduled-specials/{id}/approve` | `page.tsx:58` | `/api/scheduled-specials/:id/approve` at `scheduled-special-routes.mjs:5` |
| POST `/api/scheduled-specials/{id}/close` | `page.tsx:58` | `/api/scheduled-specials/:id/close` at `scheduled-special-routes.mjs:12` |
| POST `/api/pickup-proposals/{id}/approve` | `page.tsx:58` | `/api/pickup-proposals/:id/approve` at `server.mjs:112` |
| PATCH `/api/boxes/{id}` | `page.tsx:58` | `/api/boxes/:id` at `server.mjs:95` |
| POST `/api/boxes/{id}/revise` | `page.tsx:58` | `/api/boxes/:id/revise` at `server.mjs:94` |
| POST `/api/boxes/{id}/approve` | `page.tsx:58` | `/api/boxes/:id/approve` at `server.mjs:96` |
| POST `/api/drafts/{id}/supersede` | `page.tsx:58` | `/api/drafts/:id/supersede` at `server.mjs:26` |
| POST `/api/drafts/{id}/split` | `page.tsx:58` | `/api/drafts/:id/split` at `server.mjs:23` |
| PATCH `/api/drafts/{id}` | `page.tsx:58` | `/api/drafts/:id` at `server.mjs:24` |
| POST `/api/drafts/{id}/approve` | `page.tsx:58` | `/api/drafts/:id/approve` at `server.mjs:33` |
| POST `/api/drafts/{id}/reject` | `page.tsx:58` | `/api/drafts/:id/reject` at `server.mjs:25` |
| POST `/api/marketing-drafts` | `page.tsx:58` | `/api/marketing-drafts` at `server.mjs:122` |
| POST `/api/reconcile` | `page.tsx:58` | `/api/reconcile` at `server.mjs:121` |
| POST `/api/attempts/{id}/late-refund` | `page.tsx:58` | `/api/attempts/:id/late-refund` at `server.mjs:53` |
| POST `/api/stock-movements` | `page.tsx:58` | `/api/stock-movements` at `server.mjs:97` |
| POST `/api/content/restore` | `page.tsx:58` | `/api/content/restore` at `server.mjs:118` |
| PATCH `/api/content` | `page.tsx:58` | `/api/content` at `server.mjs:109` |
| POST `/api/content/approve` | `page.tsx:58` | `/api/content/approve` at `server.mjs:110` |
| PATCH `/api/ordering` | `page.tsx:58` | `/api/ordering` at `server.mjs:111` |
| PATCH `/api/pickup-slots/{id}` | `page.tsx:58` | `/api/pickup-slots/:id` at `server.mjs:114` |
| PATCH `/api/products/{id}/state` | `page.tsx:58` | `/api/products/:id/state` at `server.mjs:116` |
| PATCH `/api/safety-buffers/{product}` | `page.tsx:58` | `/api/safety-buffers/:product` at `server.mjs:107` |
| PATCH `/api/tasks/{id}` | `page.tsx:59` | `/api/tasks/:id` at `server.mjs:75` |
| POST `/api/tasks/{id}/resolve` | `page.tsx:59` | `/api/tasks/:id/resolve` at `server.mjs:115` |
| POST `/api/tasks/{id}/refund` | `page.tsx:59` | `/api/tasks/:id/refund` at `server.mjs:88` |
| POST `/api/logout` | `page.tsx:61` | `/api/logout` at `server.mjs:11` |

Separate from `fetch`: six literal image URLs of the form `/media/{name}` (`page.tsx:49, 51, 56–57`) fit the `'/media/:path*'` rewrite (`commerce/storefront/next.config.mjs:1`) and gateway `GET '/media/:name'` (`server.mjs:19`). This does not verify image file presence or data-supplied image URLs (`box-review.tsx:8`, `editorial-controls.tsx:2`, `marketing-controls.tsx:2`, `scheduled-special-review.tsx:4`, `page.tsx:51–53, 58`). The checkout URL assigned to `location.href` (`page.tsx:53`) is navigation, not another app fetch path.

## R3. Storefront instructions

- `commerce/storefront/AGENTS.md:3–5` says “This is NOT the Next.js you know.” It instructs agents to “Read the relevant guide in `node_modules/next/dist/docs/`” (resolve it from the storefront directory) “before writing any code. Heed deprecation notices.”
- `commerce/storefront/AGENTS.md:7` says “This block is written and re-added by `next dev`,” names `node_modules/next/dist/server/lib/generate-agent-files.js` as the verification source, and says “Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.” That is the file’s wording, not an observed dev-server result; `commerce/storefront/next.config.mjs:1` sets `agentRules:false`.
- `commerce/storefront/CLAUDE.md:1` is exactly `@AGENTS.md`: no extra wording or conflicting instruction; it points to the guide instead of repeating it. There is no tracked root `CLAUDE.md` at this pin (tree check below). This was a report-only read; no Next.js code was written and no dev server or installed generator was run.

## R4. Ranked gaps and next step

1. **Highest if the archive is ever revisited: route registration does not prove runtime behavior.** R2 matches strings and methods; it does not prove authentication, response shapes, or that every action succeeds. The checked-in commerce CI step runs dependency-free gateway unit tests, not a Next.js storefront build or UI/route journey (`.github/workflows/check.yml:99–107`; the catalog/site checks use `storefront-mockup/`, lines 249–263).
2. **The historical page is harder to audit than the component list suggests.** `page.tsx:58` contains 27 request call sites on one physical line, including callbacks for seven of the eight components rendered there (`Activity` only receives data). A grep of each component for `fetch` alone misses those parent-owned calls; see R1 and the request census below.
3. **Do not take the generated-guide note as current runtime evidence.** The wording says `next dev` re-adds the block, while the checked-in config has `agentRules:false` (`commerce/storefront/AGENTS.md:7`, `commerce/storefront/next.config.mjs:1`). No generator run qualified that behavior.

**No build unit needed:** no dead app files or unmatched fetch routes were found in the pinned source (R1–R2), and root `AGENTS.md:3–5` marks it historical. No change to the prototype, the current catalog, or owner decisions is proposed.

### Offline reproduction

Run from the repo root. The tree check prints the 13 app paths and the local `CLAUDE.md`, with no root `CLAUDE.md` or `reports/hass-npp` paths. The import scan and line counts reproduce R1. Read the cited lines for callbacks; the request census includes two helper-definition tokens at `page.tsx:13` that are not separate request call sites. For the route comparison, add the `/api` prefix, substitute one path segment for each concatenated ID, and match HTTP method and path to the gateway output. Static replay against the pinned blobs returned 47 request sites, 41/41 method/path matches, and 6 literal image paths; no services, browser, installed dependencies, or commerce runtime were used.

```sh
base=37feae1dc5efa6968f90d17a1eda6daed29afd4a
git rev-parse origin/main
git ls-tree -r --name-only "$base" -- commerce/storefront/app commerce/storefront/CLAUDE.md CLAUDE.md reports/hass-npp reports/audit-1121
wc -l commerce/storefront/app/*
git grep -nEo '^(import |export .* from )|\b(import|require)\(' "$base" -- commerce/storefront/app
git grep -nEo '<(Activity|BoxReview|EditorialControls|MarketingControls|PackTask|PickupReview|SafetyBufferControls|ScheduledSpecialReview|StockControls|SwapEditor)[ >]' "$base" -- commerce/storefront/app
git grep -nEo '(api|fetch)\(' "$base" -- commerce/storefront/app | sort | uniq -c
git grep -nEo "api\('[^']+'(\+[^+ ,)]+(\+'[^']+')?)?|fetch\('/api[^']*'|'PATCH'" "$base" -- commerce/storefront/app
git grep -nEo "app\.(get|post|patch|put|delete|all)\('[^']+'|scheduledSpecialRoutes\(\{app" "$base" -- commerce/gateway
git ls-tree -r --name-only "$base" -- commerce/backend/src/api
git show "$base:commerce/storefront/AGENTS.md"
git show "$base:commerce/storefront/CLAUDE.md"
```
