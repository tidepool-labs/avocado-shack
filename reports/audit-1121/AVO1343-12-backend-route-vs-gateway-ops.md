# Historical commerce: backend operations and gateway callers

| Question | Result |
| --- | --- |
| R1. What does the route accept? | 15 named POST operations and one GET handler shared by all operation labels. `catalog` is the only GET label used in the caller census. |
| R2. What does not line up? | `hold-status` is the only named POST without a caller. No caller uses an unsupported method/name pair. |
| R3. Do the Medusa config keys differ? | No. Both files declare the same keys, including the hosted-checkout provider options. |
| R4. Is a follow-up needed now? | No. Record the method asymmetry, unused POST and duplicate config; leave the historical prototype unchanged. |

**Source and limits.** `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, read on 2026-11-21. `AGENTS.md:3–8,13–16` distinguishes current `storefront-mockup/` from historical `commerce/`. This is a static inventory of tracked source, not a statement about deployment, traffic or external callers. No service, script under audit, provider, config loader or smoke test was run. The paths and line numbers below are at that base.

## R1. Dispatch and callers

**File shorthand:** `route` = `commerce/backend/src/api/internal/[operation]/route.ts`; `G` = `commerce/gateway/server.mjs`; `S` = `commerce/gateway/scheduled-special-routes.mjs`. `scripts/` paths below are relative to `commerce/`.

`G:12` is the gateway transport: `engine(op, body)` sends POST with a body, GET without one. `G:123` passes it to the scheduled-special module (`S:3`). The backend middleware covers `/internal/*` and returns `403` unless the configured internal credential matches (`commerce/backend/src/api/middlewares.ts:3`). A name being accepted means it selects a handler; it does not promise the handler's prerequisites will pass.

| Method | Operation | Handler at the backend | Every caller naming it |
| --- | --- | --- | --- |
| GET | `catalog` | `route:7`: queries products and calculates variant prices. Same handler for any segment; it never reads `req.params.operation`. | `G:17`; `scripts/integrity-test.mjs:13` (unauthenticated probe asserting `403`, not a successful catalog call). |
| POST | `scheduled-special` | `route:9–14`: checks the approved offer and stock allocation, creates or reuses the price list, verifies readback. | `S:10` |
| POST | `cancel-scheduled-special` | `route:9–11`: checks the offer and moves an existing price list to draft without changing physical stock. | `S:14` |
| POST | `setup` | `route:16–25`: finds or creates pickup settings and returns their IDs. | `G:13` |
| POST | `apply` | `route:27–35`: creates or updates a product, verifies readback, then applies the approved inventory target. | `G:34` |
| POST | `box` | `route:37–42`: creates or finds the approved box and verifies its variant prices and shared-inventory links. | `G:96` |
| POST | `checkout` | `route:44–56`: prepares or recovers the cart, holds and hosted payment session for the stored attempt. | `G:37` |
| POST | `hold-status` | `route:58`: reads reservation items by ID; returns an empty list if none are supplied. | None found. |
| POST | `cancel-checkout` | `route:59`: resolves and closes the payment session if present; deletes checkout reservations. | `G:52`; `G:73` (2 calls) |
| POST | `fulfill` | `route:60`: creates or reuses a fulfillment; marks it delivered when collected. | `G:83` |
| POST | `late-refund` | `route:61–64`: simulator-only late-payment refund for a closed attempt; verifies the refund and releases holds. | `G:56` |
| POST | `refund` | `route:66–71`: verifies the order/payment match and full refund, then releases allocation without restocking. | `G:89`; `G:92` |
| POST | `product-state` | `route:73`: changes draft/published status and verifies readback. | `G:116` |
| POST | `move-stock` | `route:74–79`: matches a durable movement or scheduled offer, then applies its exact inventory target. | `G:103`; `S:10`; `scripts/stock-receipt-restart-smoke.mjs:4` |
| POST | `stock` | `route:81`: reads inventory levels for the specified items and location. | `G:17`, `G:21`, `G:32`, `G:34`, `G:36`, `G:100`; `S:8`; `scripts/correction-history-smoke.mjs:8`, `scripts/safety-buffer-smoke.mjs:8`, `scripts/stock-race-smoke.mjs:11` |
| POST | `complete` | `route:82`: removes the supplied temporary reservations and runs cart completion. | `G:46` |

The census counts 30 call sites, including the two calls on `G:73`. Gateway `/api/...` requests made by scripts are not themselves calls to the backend route. The shared stock helper records the target and receipt in one inventory-level update and verifies readback; replay returns current stock rather than reapplying the old target (`commerce/backend/src/lib/inventory-target.ts:5–16`; called by `route:35,79`). The hosted provider is registered with the payment module (`commerce/backend/src/providers/hosted-checkout/index.ts:1–3`). Its methods support the payment workflows, not additional operation names; for example, its webhook handler records the event rather than completing the cart (`commerce/backend/src/providers/hosted-checkout/service.ts:23–32`, `route:52–56,82`). The provider smoke imports that service directly (`commerce/scripts/payment-webhook-smoke.mjs:2`), not via this route.

## R2. Set differences

- **Accepted but not called:** `hold-status` (`route:58`); the tracked-source search below finds it only at that branch. The generic GET handler accepts other labels too, but those labels are not a finite list of named operations. No other GET label is used by the audited callers.
- **Called but not accepted:** none. `engine('catalog')` (`G:17`) selects GET (`G:12`) and does not need a POST case. The direct script probe also uses GET but tests the middleware rejection, not dispatch (`scripts/integrity-test.mjs:13`). The POST fallback says `'Unknown operation'` (`route:83`); no POST caller targets it by name.

From the repo root, rerun these offline against the audited `origin/main`:

```sh
git rev-parse origin/main
git grep -n -o -E "op==='[^']+'|export async function (GET|POST)|Unknown operation" origin/main -- ':(literal)commerce/backend/src/api/internal/[operation]/route.ts'
git grep -n -o -E "engine\\([[:space:]]*['\"][^'\"]+['\"]|/internal/[a-z-]+" origin/main -- 'commerce/gateway/*.mjs' 'commerce/scripts/*.mjs'
git grep -n -I -o -E '(/internal/|hold-status)' origin/main -- commerce reports docs hass storefront-mockup
```

The name search was cross-checked by reading the GET and POST bodies, the `engine` definition and its references, and the direct script requests for their methods. This does not infer calls from comments, test descriptions or database keys named `engine` (`G:13`; `commerce/gateway/boxes.mjs:7`).

## R3. `medusa-config.js` versus `medusa-config.ts`

| Config keys | `commerce/backend/medusa-config.js` | `commerce/backend/medusa-config.ts` |
| --- | --- | --- |
| `admin.disable`; `projectConfig.databaseUrl` | line 2 | lines 4–6 |
| `projectConfig.http.{storeCors,adminCors,authCors,jwtSecret,cookieSecret}` | line 2 | lines 7–12 |
| `modules[].{resolve,options}`; `modules[].options.providers[].{resolve,id,options}` | line 2 | line 14 |
| `modules[].options.providers[].options.{apiKey,webhookSecret,mode,storeUrl}` | line 2 | line 14 |
| Keys only in one file | None | None |

The JS file loads helpers with `require`; the TS file uses `import`. Both use `module.exports`. Only TS marks `jwtSecret` and `cookieSecret` with non-null assertions. A static comparison of the two `defineConfig` expressions matched after removing formatting, trailing delimiters and those assertions. This does not say which file a running Medusa process would load. To list keys without printing values:

```sh
git grep -n -o -P '(?:^|[,{])[ \t]*\K[A-Za-z_]\w*(?=:[ \t]*[^/\s])' origin/main -- commerce/backend/medusa-config.js commerce/backend/medusa-config.ts
```

## R4. Ranked gaps and disposition

1. **GET and POST use different name rules.** The documented caller label `catalog` works, but the GET handler does not validate the label as POST does (`route:7–9,83`; `G:12,17`). This is a contract distinction, not a broken call in the census.
2. **`hold-status` has no tracked caller.** The branch exists (`route:58`); the R2 search finds no use. Source absence is not evidence that it can be removed safely.
3. **Two config files duplicate the key set.** Divergence is possible with future edits, but no key drift was found (R3).

**No build unit needed.** No caller mismatch was found; changing a historical route or config is not needed for the current catalog (`AGENTS.md:3–8`).
