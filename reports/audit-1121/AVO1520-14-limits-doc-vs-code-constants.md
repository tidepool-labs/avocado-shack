# Hass limits: documentation versus code

| Check | Result |
|---|---|
| R1 — Documented limits | All 58 numeric tags resolve and match under the repository's unit convention; the shelf-list tag also matches. Several untagged or prose claims differ in scope or behavior. |
| R2 — Numbers that differ | No tagged value differs as the existing checker measures it. There are differences in the units, inputs and paths described in prose. |
| R3 — Limits not found in docs | First 30 selected source limits with no equivalent bound found in the searched documentation. |
| R4 — Follow-up | Approval timing, live eligibility and undo wording rank above adding missing display caps. No build unit proposed before the relevant owners reconcile those claims. |

Source: fresh `origin/main`, `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, identical to the task baseline on 2026-11-21. This is a source audit, not a statement about settings or behavior on any installed host. `storefront-mockup/` is the current site (`AGENTS.md:3–4`). The scope note named `reports/hass-npp/G-QUESTIONS.md`, which is not tracked at this SHA (`git ls-tree -r --name-only origin/main -- reports/hass-npp/G-QUESTIONS.md` returns nothing); the explicit boundaries in the brief were used. No policy, defaults, owner decisions or deployed data were changed.

## R1. Documented claims and actual checks

The left column is a line number in `docs/hass/LIMITS.md`. A dotted name in parentheses is the exact doc tag, even where the definition moved and the original module re-exports it. Numeric caps are inclusive unless noted. Plan IDs and the approval date at lines 22–28 are labels, not quantities; no runtime date check for that annotation was found. The existing checker verifies bold numeric tags, some selected wording and the shelf list; it is not an oracle for every prose claim (line 3; `hass/tests/test_limits_doc.py:15–74,87–126,234–240,263–270,337–365`).

| Doc line and claim | Definition or enforcement | Value or behavior in code |
|---|---|---|
| 7 — 4 photos (`media.MAX_PHOTOS_PER_MESSAGE`) | `hass/media.py:31–35`; `hass/conversation.py:2338–2340` | 1–4 attachments on the photo path. |
| 7 — JPEG or PNG; 20 MB each (`media.MAX_BYTES`) | `hass/media.py:31–35,94–99,273–282` | JPEG/PNG by bytes; 20 × 1,024 × 1,024 bytes. |
| 8–11 — each new photo gets its own code/question; no duplicates, no batch caption, all checked before storage | `hass/conversation.py:2341–2379,2380–2412,2418–2460` | Ordinary path validates all first, names a failed attachment position and skips pending, same-batch and existing-product duplicates. Optional NPP takes one batch as one intake and uses caption text; single-photo skills can also join an open request. |
| 12–13 — rotated phone photos; no voice notes | `hass/media.py:38–52,74–99,354–364,382–389` | JPEG handles EXIF orientation; PNG with non-default EXIF rotation is refused. Recognized audio receives the type-it reply. |
| 17–18 — 4,000 characters (`conversation.MAX_OWNER_TEXT`) | `hass/conversation.py:73,2030–2034` | 4,000 code points on the change-request path; longer requests refused before interpretation. |
| 22–27 — closed live list; refused work saved for manual handling | `hass/live_policy.py:183–223,441–503`; `hass/conversation.py:823–844,871–876,1453–1458` | Closed operation/argument and record checks, including sign-up on either side of a hike edit, with private backlog handling on the proposal path. The code also includes `product.set_photo` for existing items and `store.confirm_selection`; this differs from the list. |
| 28–32 — new product needs its own picture and owner words in the request; new maker only with product and no link | `hass/ops/catalog.py:121–155`; `hass/live_policy.py:193–205,330–334,388–428`; `hass/conversation.py:2313–2319` | Live add checks stored photo and alt text. Maker creation requires a same-draft product referring to it; no maker URL. The owner-word check has house-placeholder exceptions and checks maker name/town on a new maker record, not on every product add. |
| 32, 35, 45–46 — at most 10 records; maker and hidden products counted (`live_policy.MAX_RECORDS`) | `hass/live_policy.py:25,441–456`; `hass/ops/catalog.py:287–309,389–407` | 10 draft record entries. Maker hide produces one maker entry and one per product hidden; maker hide itself is not live-eligible. |
| 33–34 — protected sentences; undo allowed | `hass/live_policy.py:251–272,441–503`; `hass/product_claims.py:103–128`; `hass/publish_live.py:305–311` | Compares protected sentence counts; owner-sourced and qualifying label claims have exceptions, as does validated selling-price data on a new product or its inverse. Undo still passes the live checks. |
| 37–39 — operator-set wait; time of reply, not processing | `hass/conversation.py:430,664–667,1035–1041,1140–1149,1294–1309,1387–1391,2275–2281` | `approvalTtlSeconds`, integer ≥60; proposals/coded questions expire at the cutoff. Valid sent-time approvals have a forwarding-age guard (TTL + 300 seconds), and replies to ordinary detail questions do not uniformly use that clock. Open requests have their own windows (96 below). |
| 40 — `again`, 7 days (`conversation.AGAIN_WINDOW_DAYS`) | `hass/conversation.py:43–44,2697`; `hass/chat/core_pack.py:31,112–122,154–215` | 7 days inclusive, plus re-preparation and matching keys/final values. Also renews an eligible reverted original within 7 days of linked undo; excludes the undo itself, photos, questions and cancelled, replaced or still-applied drafts. New code/expiry and separate approval; no apply on renewal. |
| 41–42 — over 15 minutes and named late prefix | `hass/conversation.py:148–150,284,307–319` | Strictly over 15 minutes from the original message, with a different prefix. Separate outbox wait prefix after 600 seconds when the original-message heading does not apply. |
| 43–44 — 20 operations (`editor.MAX_OPS`); one bulk stock op and no shelf-date movement | `hass/editor.py:34,156–157`; `hass/interpret_check.py:194–195`; `hass/ops/catalog.py:389–407` | 20 operations. One matching-active-products bulk op; it does not move the shelf-check date. One draft can contain that operation. |
| 45–46 — stopping a maker is one operation, no separate maker-size cap | `hass/ops/catalog.py:287–309`; `hass/live_policy.py:183–223,441–456` | One op, no separate product count cap in that op. The live cap of 10 does not make the op live-eligible. |
| 50 — last 5 approved changes (`conversation.HISTORY_MAX`) | `hass/conversation.py:43,2698–2700`; `hass/chat/core_pack.py:18,70–96` | 5; audit approval order with legacy fallback. |
| 51 — 10 search results, 60 characters (`conversation.HISTORY_SEARCH_MAX`, `conversation.HISTORY_TEXT_MAX`) | `hass/conversation.py:43,2696`; `hass/chat/core_pack.py:25,98–108` | 10 and 60 printable characters; AND of folded substrings, site draft row order descending, not approval-time order. |
| 52 — first 20 notes with remainder count (`conversation.MEMORY_LIST_MAX`) | `hass/conversation.py:43`; `hass/chat/core_pack.py:18,275–294` | 20 ordinary note lines; overflow is described but not counted. Separate design section. |
| 53 — first 20 aliases with remainder count (`conversation.ALIAS_LIST_MAX`) | `hass/conversation.py:43`; `hass/chat/core_pack.py:19,285–288` | 20 alias lines; overflow is described but not counted. |
| 54 — 60 active products (`chat.site_pack.SHELF_MAX`) | `hass/chat/site_pack.py:16,331–361`; `hass/content_model.py:127–128` | 60, with exact remainder; excludes hidden and held. |
| 55 — 20 costs, separated from memory (`conversation.COSTS_LIST_MAX`) | `hass/conversation.py:43`; `hass/chat/core_pack.py:20,275–294,412–456` | 20, newest dated entries first and exact remainder. `memory` counts costs separately. |
| 56 — 10 name candidates (`ops.catalog.MAX_CANDIDATES`) | `hass/ops/catalog.py:28,431–453` | 10 candidates. |
| 57 — 60 `find` characters (`conversation.FIND_TEXT_MAX`) | `hass/chat/shared.py:17`; `hass/conversation.py:33,2683`; `hass/chat/site_pack.py:180–208` | 1–60 characters. |
| 58 — 60 alias-name characters (`conversation.ALIAS_NAME_MAX`) | `hass/chat/shared.py:17`; `hass/conversation.py:33`; `hass/chat/core_pack.py:341–346` | 60, also subject to key validation. |
| 59 — first 5 photos to take (`conversation.PHOTOS_TO_TAKE_MAX`) | `hass/chat/site_pack.py:18,30,306–328`; `hass/conversation.py:2691` | 5; repeats the same first five if nothing changes, not a pagination cursor. |
| 63, 65 — product text (`content_model.TEXT_LIMITS[product]` keys `name`, `brand`, `description`, `imageAlt`) | `hass/content_model.py:91–92,280–299`; `hass/ops/catalog.py:29–38`; `hass/ops/photos.py:275–276` | Name 80, brand 60, description 600, photo description 200 characters. Content fields reject over-limit persisted text; not a universal promise about all upstream text handling. |
| 66 — one shelf, fixed list (`content_model.SHELF_LABELS`) | `hass/content_model.py:28–31,280–299`; `hass/ops/catalog.py:29–38,456–475` | One enum value; in doc order: Fruit, Vegetables, Dairy & cheese, Eggs, Meat, Pantry, Drinks & coffee, Bread, Flowers, General. Add-shelf operation not found. |
| 67 — maker text (`content_model.TEXT_LIMITS[maker]` keys `name`, `place`, `story`) | `hass/content_model.py:93,364–365`; `hass/skills/makers.py:101–109` | Name 80, place 60, story 600 characters. |
| 68 — hike text (`content_model.TEXT_LIMITS[event]` keys `title`, `description`, `meetingPoint`, `recap`, `bring`) | `hass/content_model.py:60–63,94–95`; `hass/ops/hikes.py:77–85,378–393` | 80, 800, 160, 2,000 and 400 characters respectively; the other fields in `EVENT_TEXT_FIELDS` default to 400. |
| 69 — each route text field 600 (`content_model.TEXT_LIMITS[routeIdea][description]`) | `hass/content_model.py:53–56,96,212–234,412–415`; `hass/ops/routes.py:51–56` | 600 characters for the mapped fields, not `sourceUrl` (500), `id` or `status`. |
| 70 — optional cancellation note: one line, 160 characters (`content_model.TEXT_LIMITS[event][cancelNote]`), no guest message | `hass/content_model.py:94–95`; `hass/ops/hikes.py:77–85,378–393`; `storefront-mockup/community.js:51` | One line, 160 characters, saved on cancelled card; no guest send in this operation. |
| 71 — club intro 400 characters (`content_model.MAX_CLUB_INTRO`) | `hass/content_model.py:51,97`; `hass/ops/club.py:22–37` | 400; one paragraph, minimum 20 letters (also `docs/hass/COMMANDS.md:253`). |
| 72 — 400 each for club name, organizer, sender (`content_model.TEXT_LIMITS[club][clubName]`) | `hass/content_model.py:49,97` | 400 each for `clubName`, `organizer`, `intendedSender`. |
| 73 — store text and hours (`content_model.TEXT_LIMITS[store]` keys `streetAddress`, `town`, `hoursLine`; `content_model.MAX_HOURS_LINES`) | `hass/content_model.py:86,98`; `hass/ops/store.py:57–89` | Street 80, town 80, hours line 60 characters; at most 7 lines. |
| 74 — note 500 characters (`memory.MAX_VALUE`); key 1–64, specified alphabet and punctuation | `hass/memory.py:22–45`; `hass/chat/commands.py:256–267`; `hass/chat/core_pack.py:304–318` | 500; 1–64 normalized key characters, spaces to hyphens, first ASCII letter/digit, then lowercase ASCII letters, digits, periods, hyphens. |
| 78 — US phone 10 digits (`ops.store.PHONE_DIGITS`) | `hass/content_model.py:69–70`; `hass/ops/store.py:33,114–125` | 10 stored digits with a pattern check; leading domestic `1` or `+1` can be stripped from input. |
| 79 — private purchase cost 100,000 dollars; 1–10,000 units (`margins.PACK_COST_MAX`, `margins.UNITS_MIN`, `margins.UNITS_MAX`) | `hass/margins.py:12–15,61–62,90–91`; `hass/chat/reports_pack.py:88–104,284–322` | 100,000 maximum, 1–10,000 whole units. Cost also has a 0.01 minimum. These are validation bounds, not actual product prices. |
| 83 — New for 14 Pacific calendar days (`shop.NEW_BADGE_DAYS`), add day included | `storefront-mockup/shop.js:48–52`; `hass/ops/catalog.py:170–171`; `hass/skills/item_add.py:903–908` | 14 (ages 0–13); no badge without `addedOn`. Sandbox opt-out; edit/restore do not stamp a new date (`hass/tests/test_product_new.py:127–150`). |
| 87 — intro 160 (`content_model.MAX_INTRO`) | `hass/content_model.py:84`; `hass/ops/store.py:101–110` | 160 characters. |
| 88 — headline line 40 (`content_model.MAX_HEADLINE_LINE`) | `hass/content_model.py:83`; `hass/ops/home.py:42–52` | 40 characters per line, exactly two lines. |
| 89 — story 400 (`content_model.MAX_STORY`) | `hass/content_model.py:81`; `hass/ops/home.py:59–77` | 400 characters. |
| 90 — notice 160 characters, last day ≤60 days ahead (`content_model.MAX_NOTICE`, `content_model.MAX_NOTICE_DAYS`), inclusive Pacific dates | `hass/content_model.py:79`; `hass/ops/home.py:97–120,131–135`; `hass/notice.py:56–65`; `storefront-mockup/notice.js:1` | 160 and 60; optional start defaults to today, cannot be past or after the end. Build/browser gate hides before start. The `shop.notice` skill does not emit a start field (`hass/skills/shop.py:448–470,608–611`). |
| 91 — home photo JPEG/PNG up to 20 MB (`media.MAX_BYTES`) | `hass/media.py:31–35,183–187`; `hass/ops/photos.py:268–279` | Same format and 20 × 1,024 × 1,024 bytes on Hass photo intake. |
| 92 — at least 3 letters in real photo description, no file name | `hass/ops/photos.py:183–190,268–279` | ≥3 letters, rejects camera/file-name patterns; same 200-character cap as product alt text. |
| 96 — 30 minutes idle, 120 total (`skills.openreq.TTL_MINUTES`, `skills.openreq.MAX_MINUTES`) | `hass/skills/openreq.py:37,66–70,200–228` | 30 and 120 for nonlegacy open requests; legacy path resets a 30-minute window without the 120-minute clamp. |
| 97 — 4,000 per text, 8,000 total (`skills.openreq.MAX_OWNER_TEXT`, `skills.openreq.MAX_TOTAL_TEXT`) | `hass/skills/openreq.py:38,73–80,200–228` | 4,000 and 8,000 stored characters; trims/drops prior text to fit. |
| 97 — erase after 24 hours (`skills.openreq.RETENTION_HOURS`) | `hass/skills/openreq.py:39,238–259,275–297` | 24-hour sweep threshold, not a scheduled deletion deadline; legacy rows can be cleared immediately. |
| 98 — owner only, `no`/`cancel`, 3 unresolved questions (`skills.openreq.MAX_UNRESOLVED`) | `hass/conversation.py:1257–1275,1392–1401,2004–2014`; `hass/skills/openreq.py:40`; `hass/skills/dispatch.py:781–801,955–988,1310–1322` | Owner gating and cancellation; ordinary same-question/slot path stops when it would re-ask a fourth time, not a universal all-intake cap. |
| 99 — backlog 10, 90 days, `forget backlog.<n>` (`skills.backlog.LIST_MAX`, `skills.backlog.RETENTION_DAYS`) | `hass/skills/backlog.py:36–37,86–92,104–130`; `hass/chat/core_pack.py:249–274`; `hass/conversation.py:1294,2008–2014` | 10 open entries newest first; one deletion per code; 90-day age threshold on a sweep, with unknown ages kept. |
| 103–106 — store undo field-wise; notice and specials each one detail; other records whole | `hass/ops/history.py:160–190`; `hass/ops/home.py:97–120`; `hass/ops/specials.py:92–103` | Compare changed store keys to their after-values and restore those keys only. Notice/specials are each one key. Other collections compare and restore whole records. |
| 107 — only through Pacific end date; 6 per day, 31 days, title and deal 60 characters each, no links/email/phone, deal-only price | `hass/content_model.py:77–78,508–549,575`; `hass/ops/specials.py:55–89`; `storefront-mockup/specials.js:1` | 6 concurrent, 31 inclusive days, 60/60; format checks and date-based render/hide. Deal line may contain price text. |
| 111–112 — 2+ separate owners, up to 8; 1 without list; setup step 6 | `hass/conversation.py:374,397–422,732–740`; `docs/hass/CONNECT.md:35–43` | List 1–8; shared mode at 2+. One configured chat without list. Step 6 is a guide locator, not executable. |
| 113–118, 130–131 — sender/chat pairing, isolated owner responses, `gChat` text-only, chat-bound yes/no and legacy sender binding | `hass/conversation.py:436–449,778–800,1257–1261,1689–1692`; `hass/relay.py:325–328` | Pair check; pending approvals bound to chat and, in shared mode, sender. Attachments stripped on non-owner replies. Optional `gIsOwner` is a separate owner-command path; `gChat` is still not an `ownerChats` entry. |
| 119–121 — one site/change open; other owner blocked | `hass/conversation.py:756–774,2030–2032,2338–2341,2729` | Other chat blocked while an eligible draft is pending/approved or a release is open; not a global one-draft count across all paths. |
| 122–124 — shared history/status/undo; only coded cross-owner undo; same requesting owner approves | `hass/chat/core_pack.py:70–108,483–509`; `hass/conversation.py:778–785,2665–2667,2709–2739` | Shared site lookup, names where available; bare undo will not take the other chat's change back. A matching code can draft an undo for separate approval. |
| 125–126 — shared pause/resume, daily limits and STOP; requests/questions separate | `hass/chat/core_pack.py:483–509`; `hass/conversation.py:433–435,1713–1724,2039–2089,2742–2744`; `hass/publish_live.py:48–52,196–205,305–311`; `hass/skills/openreq.py:140–169` | Shared flags/counters, per-chat open requests. Optional interpreter cap 1–10,000 (not all requests count); live default 10/day, allowed 1–50, normal live gate excludes undo. No installed settings inspected. |
| 127–129 — forwarder carries same list, second chat still waiting on older forwarder | `mac/hass_forwarder.py:66–76,97–100,396,550–559`; `hass/relay.py:325–345` | Current forwarder validates list and filters delivery by chat; unmatched rows are skipped. No blanket no-loss guarantee for all older versions found. Configuration/restart directions are operational prose, not an additional cap. |
| 135–138 — correspondence 90 days, 80 characters, redacted, excluded from backup | `hass/corrlog.py:4,27–38,50–62,106–147`; `hass/statebackup.py:39–49,196–244` | 90 days by UTC day-file cutoff on prune; first 80 characters after pattern masking. The state backup copies a named set, not correspondence. Not a universal test for all possible sensitive text. |
| 139–143 — `gSenders` empty by default, distinct from owner list; `gChat` only; last 10, top 3 with 1 suggestion, 2 waiting | `hass/conversation.py:436–449,477–479,1677–1683,280–294`; `hass/corrlog.py:149–155,165–181`; `hass/morning_report.py:178,197`; `hass/relay.py:29,325–328`; `mac/hass_forwarder.py:550` | Checks sender and chat. 10 recent; 3 kinds over 7 days, one suggestion each; morning weekly line is opt-in CLI output. Relay limits this text-only queue to 2 unacked answers. |
| 145–146 — no history codes, no older coded undo; bare undo takes last | `hass/chat/core_pack.py:70–108`; `hass/conversation.py:2702–2739` | History omits the codes, but older coded undo is implemented when the code is already known and eligibility checks pass. Bare undo selects the last eligible saved change, except when it addresses a waiting product-add draft. |
| 150–153 — never message guests/customers, take payment, show prices, invent listed claims, or change the public site on its own | `hass/conversation.py:787–801`; `hass/ops/hikes.py:378–393`; `hass/live_policy.py:183–223,251–272`; `hass/product_claims.py:103–128`; `hass/publish_live.py:305–311`; `storefront-mockup/shop.js:21` | Reviewed paths route to owner chats, not guests, and no payment-taking path found in scope. Specials and product cards can show prices. Claim checks and approval/publisher gates are path-specific; no universal enforcement of every phrase in this bullet set was found. |

## R2. Differences in numeric wording

| Doc wording | Code value or boundary |
|---|---|
| `LIMITS.md:7,91` — “20 MB” | `hass/media.py:31,185,278` — “20 * 1024 * 1024” bytes (20 MiB, not 20,000,000 bytes). `hass/tests/test_limits_doc.py:17,65–66` explicitly equates the doc's MB to MiB. |
| `LIMITS.md:69` — “each text field 600 characters” | `hass/content_model.py:96,212–234,412–415` — `sourceUrl` is excluded from `TEXT_LIMITS` and uses the “500” character URL check. |
| `LIMITS.md:78` — “10 digits … anything else is refused” | `hass/ops/store.py:114–125` — also accepts “1” / “+1” before the ten digits; the stored number remains 10 digits. |
| `LIMITS.md:96` — “never more than 120 minutes from your first one” | `hass/skills/openreq.py:217–228` — “120” clamps nonlegacy requests; legacy requests can renew the “30” minute window without a total clamp. |
| `LIMITS.md:97` — “erases … after 24 hours” | `hass/skills/openreq.py:238–259,275–297` — “24” is the nonlegacy sweep age; legacy close can erase immediately. |
| `LIMITS.md:119` — “one change is open at a time” | `hass/conversation.py:756–766,1655–1656,1685–1696` — the gate excludes the *other* owner; no hard count of one open change across all paths. |

The other R1 qualifications are differences in wording, applicability or omitted conditions, not differences between a stated number and the corresponding constant.

## R3. First 30 code limits not found in docs

Scan order is source path, then line, for the selected owner/operator-facing Hass NPP and catalog findings. Excludes standalone till operations, tests, fixture data, dormant helpers, and internal budgets without a visible effect. “Not found” means no equivalent bound for that *same path and field* in the tracked text, Markdown or docs JSON corpus searched below; a different limit with the same number is not a match. Defaults/settings are source-only, not deployed values.

| # | Runtime source | Visible limit |
|---:|---|---|
| 1 | `hass/answer_reader.py:98–109` | Fallback intake answer reader skips answers over 400 characters; not the general request cap. |
| 2 | `hass/chat/commands.py:200–212` | `look` arguments over 60 characters get usage, not a capture. The documented 10 matches are a different cap (`docs/hass/COMMANDS.md:62`). |
| 3 | `hass/chat/core_pack.py:503–509` | `status` daily-cap warning starts at 80% of the configured cap; `docs/hass/COMMANDS.md:39` says “near.” |
| 4 | `hass/chat/site_pack.py:22,283` | `listing` product description excerpt is 120 characters plus ellipsis. |
| 5 | `hass/chat/wording.py:132–149` | At most 3 distinct changed-field labels per record before “and more” in summaries. Separate from the documented whole-summary length (`hass/README.md:102`). |
| 6 | `hass/claims.py:308–317`; `hass/conversation.py:2315` | Clarification names at most 2 distinct unsupported claims; not a validation cap. |
| 7 | `hass/content_model.py:39,250–251` | Canonical product selling-price value has at most 6 whole digits, exactly 2 fractional digits, and an optional supported unit suffix. This is a format bound, not an actual product price. |
| 8 | `hass/content_model.py:92,336–340`; `hass/ops/catalog.py:29–38` | Separate `displayBrand` field has a 60-character cap; `LIMITS.md:65` tags `brand`, not this card override. |
| 9 | `hass/content_model.py:212–234,364–365,412–415` | HTTPS maker/route URL length ceiling of 500 characters. |
| 10 | `hass/conversation.py:373–384` | Settings file refuses more than 1 MiB. |
| 11 | `hass/conversation.py:424–428` | Optional displayed owner name up to 20 characters. `docs/hass/CONNECT.md:41–43` names the setting. |
| 12 | `hass/maker_site.py:71,533–555`; `hass/conversation.py:1122–1138` | Maker-site prefetch considers only the first 2 distinct eligible URLs in request order. Separate from the fetch budgets (`docs/hass/skills/item_add.md:96–103`). |
| 13 | `hass/margins.py:27–41,60–65,89–91` | Margin and shrink percentages accept 0–90%, up to 2 significant fractional digits. |
| 14 | `hass/margins.py:61–62,90–91` | Purchase cost has a 0.01 minimum. The documented purchase cost maximum and the separate expense-entry minimum in `docs/hass/TASKMAP.md:618` do not state this bound. |
| 15 | `hass/morning_report.py:25,153–170` | Starts with at most 10 rows per low, sold-out or hike list, then can trim further. The 1,200-character budget is documented separately (`docs/hass/skills/reports.md:18–21`). |
| 16 | `hass/newitem_render.py:30–35,246–259` | House renderer refuses decoded images above 50 megapixels, separately from the encoded file-size cap. |
| 17 | `hass/newitem_render.py:38–39,48–49,123–125,144,316` | House renderer needs a rounded short side ≥8 pixels at a 320-pixel working long side. |
| 18 | `hass/newitem_render.py:52,342–349` | Subject enlargement capped at 2.5× with a small-photo review warning. |
| 19 | `hass/npp/edits.py:175,238` | An edited name is cut to 40 characters in the source-clarification question, not in stored content. |
| 20 | `hass/ops/catalog.py:28,329–330` | Supplied maker key at most 64 characters, distinct from the display name and memory key. |
| 21 | `hass/relay.py:13,325–345` | Relay rejects reply text over 8,192 characters, separately from normal voice length rules. |
| 22 | `hass/skills/dispatch.py:487` | At most 3 distinct choices from the combined pick list in that clarification path. |
| 23 | `hass/skills/item_intake.py:27,542–548,582–584` | Fixed cleaned free-text intake answer capped at 400 characters, distinct from the fallback-reader cap. |
| 24 | `hass/skills/item_intake.py:391,415,435–452,609–628` | Leading parsed number capped at 1,000,000 for quantity/low-stock answers; dozens are multiplied after this check. |
| 25 | `hass/skills/item_intake.py:526–535,626` | Explicit intake year range 2000–2100 inclusive; fixed parser expands two-digit years with base 2000. |
| 26 | `hass/skills/makers.py:40,81–84,458–476` | Maker hide/restore reply names up to 5 products, then gives remainder; not a cap on changes. |
| 27 | `hass/skills/openreq.py:42,201–214` | Open request keeps at most the first 5 supplied attachment references; distinct from the per-message upload cap. |
| 28 | `hass/skills/reports.py:38,69–71` | Report intent sees the last 5 turns, cut to 400 characters each. |
| 29 | `hass/skills/specials.py:470,509` | Special selection prompts show up to 10 names, not the active-specials cap. |
| 30 | `hass/skills/specials.py:587–602` | `specials.show` lists only the first 3 upcoming by date, with no remainder line. |

## R4. Ranked gaps

1. **Live eligibility, protected copy and price scope.** The closed list and blanket wording do not describe the same cases as the gates and renderer (R1 lines 22–34, 107 and 150–153). The responsible owners need to reconcile the stated contract; this audit does not choose it.
2. **Approval timing and undo.** Separate sent, forwarded and processed clocks; legacy versus current open requests; known-code undo versus visibility of the code in history (R1 lines 37–42, 96–99 and 119–146).
3. **What the owner sees or can submit.** Optional intake caption behavior, memory overflow, notice start, rotation and width/length wording differ by path (R1 lines 7–13, 52–53, 69, 78 and 90; R3). These matter for explaining a refusal without suggesting a cap change.
4. **Coverage of the existing drift check.** Strong for tagged literals and the shelf list, narrower than line 3 suggests for untagged values, unit labels and prose (`hass/tests/test_limits_doc.py:15–74,87–126`). No build unit proposed now: the report is usable as evidence, and no change to the disputed policy or wording is needed to complete this audit.

### Reproduce offline

Run from the repo root. `git show` reads pinned blobs, and `nl -ba` gives the lines above. Repeat with each named file and source/doc regex; review the checks and their callers, not just the declarations.

```sh
r=37feae1dc5efa6968f90d17a1eda6daed29afd4a
git rev-parse origin/main
git diff --name-status "$r" origin/main -- docs/hass hass storefront-mockup reports/audit-1121
git show "$r":docs/hass/LIMITS.md | nl -ba
git show "$r":docs/hass/LIMITS.md | rg -o '<!-- [^>]+ -->' | wc -l
git show "$r":hass/tests/test_limits_doc.py | nl -ba
git show "$r":hass/conversation.py | nl -ba
git grep -nE 'MAX_|MIN_|LIMIT|TTL|\[:[0-9]+\]|at most|too (long|many|large)|[<>]=? [0-9]+' "$r" -- ':(glob)hass/**/*.py' ':!hass/tests/**' | LC_ALL=C sort -t: -k2,2 -k3,3n
git grep -niIE 'interpreterDailyCap|80%|80 percent|look <product>|60 characters|megapixels|2\.5×|2\.5x|8,192|8192|upcoming specials' "$r" -- '*.md' '*.txt' ':(glob)docs/**/*.json' ':!hass/tests/**' ':!storefront-mockup/archive/**' ':!commerce/**'
```

For R3, repeat the last search with the command/setting name, the limit's digits and spelled-out form, and field or behavior synonyms; a documented cap for a different command is not equivalent. `FEATURES.md:39,50` and `OPERATIONS.md:38,125` describe expiry/usage or adjacent operations, not substitutes for the source checks above. No live service, state, external model, browser or transport was exercised.

Focused baseline receipt (2026-11-21): `python3 -B -m unittest -v hass.tests.test_limits_doc.LimitsDocTest.test_every_number_matches_its_constant hass.tests.test_limits_doc.LimitsDocTest.test_every_text_limits_group_is_cited hass.tests.test_limits_doc.LimitsDocTest.test_photo_types_match_media_kinds` ran 3 tests, `OK`. That checks the tagged values, group coverage and image types; it does not test every row above.
