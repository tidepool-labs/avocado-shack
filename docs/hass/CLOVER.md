# Hass and Clover: items and stock straight from the till (HASS-CLOVER-1, HASS-CLOVER-2)

**Status (HASS-CLOVER-2): READ-ONLY connection to the real store, built and fixture-tested; the operator turns it on after review and merge
("Go live: read-only", below).** Hass reads items and stock into a private cache and answers Mike's stock questions. It cannot change the till:
the deployed chat has no write path, and the installed token is Inventory: Read only. HASS-CLOVER-3 adds an unconnected fixture-qualified engine; HASS-CLOVER-4 wiring and live enablement remain separately gated.
G decided on 2026-11-09 that Hass talks to Clover directly so that Mike (the owner) can make SKUs and manage inventory by text. This page is the
design (the seven questions, one chosen answer each) and describes the code in `hass/clover/`. It builds on `reports/hass/SKILLS-SPEC.md`
(5.2 asked these questions; the answers are mapped at the end) and `docs/hass/TASKMAP.md` (T26 "Price change", gated until Clover).

## Reports

AVB-14 adds **cache-only** reports. They do not load a token, call Clover, use a
model, change stock or update the site. These commands are for the deterministic
Hass service/operator, not permission for a model to read live financial records:

```text
python3 -B hass/clover/cli.py report stock --host /path/to/host.json
python3 -B hass/clover/cli.py report mismatch --host /path/to/host.json
python3 -B hass/clover/cli.py report --all --host /path/to/host.json
```

Files: `<state>/clover/reports/YYYY-MM-DD-stock.md` and `...-mismatch.md`, dated in
America/Los_Angeles. Folder 0700, files 0600; same-day reruns replace atomically.
`--out DIR` chooses another private directory outside the runtime/writer checkout
(the parent must exist); unsafe modes, symlinks and unsafe destination files are
refused, never repaired. Each successful write prunes only regular, owned,
single-link `YYYY-MM-DD-stock.md` / `...-mismatch.md` files in that output folder
whose Pacific date is at least 90 days old. Other files and subfolders stay put.
These are local, finance-local-class files: never attach them to chat, commit them,
feed live records to a cloud model or publish them. This version emits no prices.

Stock: all cached items, including hidden ones (marked), with sold-out counts
(<=0), positive counts at or below `lowStockThreshold` (default 5), and no-count
items. Every file labels last sync and freshness/outage, including historical
snapshots over 24 hours old. Another till's or unidentified cache is refused.

Mismatch: writer worktree `hass/content/products.json`, active site products only,
and private `<state>/clover/links.json` with shape
`{"product-id": {"cloverId": "CLOVERID", "sku": "OPTIONAL-SAVED-SKU"}}`.
An absent link table is an explicit gap, not proof of absence. No fuzzy/name join:
reports list both unlinked sides, missing/inactive link endpoints, changed saved
SKUs, different names, and stock-word disagreements (`yes`/`limited` with count
<=0 or `no` with count >0). Unknown counts/absent words are not guessed. Nothing
is automatically fixed. A malformed/unsafe link table refuses the comparison.

G can text **`till report`** in the configured `gChat` from a `gSenders` address,
even while changes are paused. The response computes the same headings from the
current cache, with totals only: no item names, SKUs, prices, paths or file text.
It does not write a file. Owners (including Mike), strangers, wrong chats,
attachments, edited messages and echoes cannot use this command. Existing age
and outage wording applies; counts over 24 hours old are not quoted in chat.
Mismatch headline totals count findings across sections, not unique products.

`deploy/hass/hass-clover-report.service` / `.timer` are **uninstalled templates**:
`report --all`, daily at 06:00 America/Los_Angeles, persistent across missed runs.
Installation/enablement is an operator step after review and a runtime move; this
PR does not install, enable or restart anything. Rollback: disable/remove that
timer, then the operator may delete the reports folder; revert the PR for code.

Rendered stock sample from the synthetic #571 fixtures (not live inventory):

```markdown
# Low stock

Last sync: 2026-11-10T20:00:00+00:00
Snapshot: fresh
Comparison uses saved links only; unlinked items are gaps, not confirmed absences.

## Sold out (2)

- Eggs, dozen \(FAKEITEM00003\): 0
- Old honey jar \(FAKEITEM00004\): 0; hidden on till

## Low stock (at or under 5) (0)

- None.

## No count (1)

- Market special \(ring up price\) \(FAKEITEM00006\): no count
```

## Website stock words

`clover.siteStock` is **off by default**; choices are `off`, `auto`, `draft`.
`siteStockWords` defaults to `words` (Available today / Sold out); `limited`
also uses Limited at or below `lowStockThreshold` (5 by default). Activation
still needs G's STOCK-AUTO/SITE-WORDS choices, reviewed LINK wiring, and an
attended runtime/service-template move. This code installs/enables nothing.

The sync template adds one `stock_site.py run --host ...` post-step. Because
the existing unit accepts sync exit 1, the post-step also independently checks
the identity, successful last attempt, matching asOf/lastAttempt, age <=20
minutes, strictly newer read, and >=90% of the last item count. Failed, skipped,
stale or partial reads never touch the queue or the site. The old health alert
after two hours remains. No network or token is needed to read this cache.

Only a crossing changes a word; a hand-set word otherwise stays. First sync
and each new/relinked product make a reconcile preview, never an automatic
release. `stock yes stk-...` approves exactly that set; `stock no stk-...` drops
the remaining words even between batches. LINK authenticates sender/chat and
excludes groups before calling `stock_site.approve(state, code, owner_role)`
or `decline`; these library functions do not authenticate chat themselves.
Proposals are private files/state, not outbound messages. More than
max(5, 10% of links) new Sold outs needs that same one yes and a warning.

The private, atomic 0600 `clover/site-stock.json` keeps counts, pending words,
hashed sets and inflight batch progress, under a nonblocking stock lock. A
corrupt file fails closed, never resets. Deferred words retry on later good
reads; latest crossing wins and a later owner edit wins. Before every retry,
unlinked/relinked/gone entries are dropped with an audit row; missing/no-count,
hidden till or inactive site items are parked, with no attempt charged.
Re-eligible words are recomputed; an approved word changing needs a new set
when it came from reconciliation. Turning off leaves the queue untouched.

At most one batch per read, bounded by min(editor.MAX_OPS,
live_policy.MAX_RECORDS), currently 10. Automatic crossings go first, then
oldest approved set; Sold out, Limited, Available today within each batch.
One live wrapper apply performs its own baseline check and editor apply.
No editor/live-policy limit, shelf-check-today rule, STOP, sandbox binding,
writer lock, settling check or read-back gate is bypassed. A not-published
writer/site divergence stays held for the operator, never treated as success.
Three daily slots are reserved for owner changes, including approved stock
sets: normally seven batches (70 words) a day, only on shelf-check days.

`clover/reports/site-stock-totals.json` is counts/reason/age/batches only; POS-2
and the dashboard can read it. `stock-reconcile-<date>-stk-<code>.md` lists
the private per-product preview; `stock-reconcile-<date>-gaps.md` lists missing
and parked links. Folder 0700, files 0600, reconcile reports pruned at 90 days.
Keep these finance-local files off models, the repo and the website. Site ops
contain only product ids and words, never count, price or SKU.

Each completed batch adds one audit row (`who: timer`, `skill: stock.sync`)
and correspondence row (`reason: stock-sync-published`). The stock state also
records `actor: stock-sync` and the change id. Existing revert-last **does pick
the latest landed stock release**: POS-2 must read that marker and say
“That was a stock update from the till”; changing undo targeting is not here.

## Credential rule (read this first)

G's standing fleet rule is that no agent handles credentials; this design keeps its spirit.

* The Clover API token is created by **G himself** and put by **G himself** into **one file** on AgentOrange (steps in "What G does", below).
* The only program that ever reads the file is the **Hass service** (a deterministic program, never an LLM worker). The code that reads it is
  `hass/clover/credential.py`, and it is the only code that holds the value.
* **No worker, reviewer, operator session, card body, comment, log, test fixture, error message or chat may contain, read or print the token or the
  file's content.** Tests use a made-up fake token and recorded fixtures; a test fails if a token-shaped string appears in a fixture.
* The module reads the token's **path** from the host/state settings (`tokenFile`), never the token itself.
* Before reading, the module checks on the open descriptor that the file is a regular file (no symlink), **owned by the service user**, mode **exactly 600**,
  not empty or larger than 512 bytes, in a folder only that user can write to. Any other state is refused with one fixed reason word
  (`missing`, `unreadable`, `not-regular`, `owner`, `mode`, `folder`, `size`, `format`); the reason never contains the path or any bytes.
  `hass/host.py check` and `hass/health.py` judge the file by `lstat` only (`credential.inspect`): they never open it.
* The `Token` object prints as `Token(<redacted>)`, cannot be pickled, copied or inspected, and the Authorization header exists only inside the request
  handed to the HTTP layer. Request headers print as names only. **No code path logs a header.** A foreign error message (a transport failure, a Clover
  error body) is never repeated: the client reports a status number or a fixed phrase.
* A note on G's wording "root-only file": the Hass service runs as the owner's user account (`systemctl --user`), and a root-owned file is unreadable
  by it. So the file is owned by that service user, mode 600 (root can still read it; no other account can). If G wants a root-owned file, the alternative
  is a systemd `LoadCredential=` unit setting, which needs root and a decision from G; it is not chosen here.

## The seven answers in one line each

1. **Auth and scopes:** Clover Platform REST v3 with a *merchant-generated API token* (one merchant, internal tool), Bearer header; the token permission page only has coarse Read/Write per data category, so READ = *Inventory: Read* and every write kind = *Inventory: Write* (nothing else ticked); sandbox first, production only after a go-live card.
2. **Data model:** a private link table (`product id -> Clover item id + SKU`) keeps the site free of SKUs and prices; match by link, then the link's SKU, then **exact** name, never fuzzy for writes; one-sided items are reported, never auto-created.
3. **SKU:** `AS-<CAT>-<NAME up to 18>-<NN>`, e.g. `AS-PAN-SUNSHINE-OLIVE-OIL-01`; deterministic, issued once and never changed, collision-checked against every SKU and barcode in the till and again live right before the create.
4. **Write safety:** every write is a draft in plain words, needs the owner's `yes <code>` bound to the asker, daily cap, one yes even for a big price move, no deletes (hide only), journalled before and after so `undo` restores, Clover decides price and stock, the site never shows a price; no checkout, payment, refund, discount or order calls exist.
5. **Inventory flows:** `how many X`, `low stock` (reads); `received 12 X`, `set X to 7`, `X sold out`, `new item: ...`, `change price of X to ...` (drafts); a count that reaches zero (or restarts from zero) carries the website's Sold out / Available word in the same draft, one yes.
6. **Sync:** read-only pull every 15 minutes plus on demand, a private cache, answers older than 20 minutes labelled "as of", "can't reach the till" when it is down, nothing quoted after 24 hours, writes never from cache; only items and stock are pulled, no sales or customer data, nothing leaves the box except the HTTPS calls to Clover.
7. **Rollout:** G makes a developer account, a sandbox merchant and a sandbox token; build cards follow on the sandbox; a go-live card (G approves) swaps in a read-only production token first and a write token only after a clean read-only week.

---

## 1. Auth and scopes

**API and token type.** Clover REST Platform API v3, JSON over HTTPS, `Authorization: Bearer <token>`, a `User-Agent` header (Clover's reference lists it as
required). Clover offers two token kinds: an *OAuth* token (needs a developer app, a site URL, a browser consent by the merchant, access tokens that expire in 30
minutes and a refresh token the program must rotate and store) and a *merchant-generated API token* made in the merchant's own dashboard. Clover's own FAQ recommends the
second for "internal tools or integrations where you control both the application and the merchant environment" and "if your integration is intended for only one
merchant". That is this case, and it keeps one static secret in one file instead of a rotating pair. **Chosen: merchant-generated API token.**
Open risk, to be settled in the sandbox and at go-live: Clover's pages describe these tokens mostly for test merchants, and say test-merchant tokens are for the
sandbox only ("do not use the test merchant API tokens in the production environment"; "production apps must use API tokens generated using the relevant OAuth flow").
So the **sandbox token and the production token are different tokens in different files**, and the go-live checklist includes a step where G confirms Mike's real dashboard
offers *Settings, Business Operations, API tokens*. If it does not, the fallback is a private OAuth app, which is a separate design and a G decision.

**Base URLs.** Sandbox `https://apisandbox.dev.clover.com`; production, North America, `https://api.clover.com`. The client has exactly these two hosts, builds every URL
itself, never follows a redirect (the real transport refuses 3xx, so the Authorization header cannot be sent to another host) and refuses any other host or scheme.

**Scopes.** Clover's token permissions are per data category and only Read or Write ("Each category of endpoints corresponds to either a Read or Write permission"). There is
no per-item or per-field scope, so *"the minimum for each write"* is the same single permission, and the limit between "set price" and "set stock" is kept in code (drafts,
the client's path allow-list), not by the token.

| Need | Clover permission to tick | Endpoints (all under `/v3/merchants/{mId}`) |
|---|---|---|
| Read items, stock, categories | **Inventory: Read** only | `GET /items` (`expand=itemStock,categories,tags`, `limit` up to 1000, `offset`, `filter=modifiedTime>=ms`, `filter=sku=...`), `GET /items/{id}`, `GET /item_stocks` (paged), `GET /item_stocks/{id}`, `GET /categories` |
| The merchant's basic record (`check` only) | Merchant: Read (**not** ticked; see below) | `GET /v3/merchants/{mId}` (no expand). With an Inventory-only token Clover may answer 401/403: `check` then shows `"merchant": "4xx"` and still passes on the items read |
| Create item | **Inventory: Write** | `POST /items` (required: `name`, `price` in cents), then `POST /category_items` to file it |
| Set price | **Inventory: Write** | `POST /items/{id}` with `{"price": cents}` |
| Set stock | **Inventory: Write** | `PUT /item_stocks/{id}` with `{"quantity": n}` (the item update cannot change stock: Clover says so) |
| Set SKU | **Inventory: Write** | `POST /items/{id}` with `{"sku": "..."}` |
| Hide / show (the only "remove") | **Inventory: Write** | `POST /items/{id}` with `{"hidden": true|false}` |

Never ticked: Customers, Employees, Merchant, Orders, Payments, Ecommerce, or anything else. So even a stolen token could not read sales or customers or take a payment.
Because Write is one indivisible permission, the production rollout uses **two token files**: a *read* token (Inventory: Read only) first, and a second *write* token
(Inventory: Read + Write) created only at the write go-live. Until the write file exists, Hass cannot change anything in the till however the code behaves.
Clover answers **401 for both a bad token and a missing permission** (its 401 page says so), so a permission mistake looks like "the till refused the key".

**What Hass writes to Clover.** `name`, `price` (cents), `priceType: FIXED`, `sku`, `hidden`, the item-category link, and the stock `quantity`. Never `code` (the barcode:
read, used for matching, never written), tax (the till's default applies and the draft says so), `cost`, `available` or `autoManage` (Clover manages those; Hass leaves them).

**Rate limits** (Clover, "API usage and rate limits"): **16 requests per second and 5 concurrent per token** (50/s and 10 concurrent per app); a breach is HTTP 429 with an
`X-RateLimit-...` header naming the limit, and a concurrency breach carries `Retry-After`. The client is synchronous (one request at a time), spaces requests at least 0.25 s
(4/s), retries 429 and 5xx up to 3 times (waiting `Retry-After` seconds, clamped to 1-30, else 1, 2, 4 seconds), then raises `RateLimited` (the reply says "the till is busy,
try again in a minute"). A normal day is a handful of requests every 15 minutes; the limits are not a design pressure.

**Sandbox.** All build and rehearsal use a Clover **sandbox test merchant** (created in the developer dashboard under *Test Merchants*; Clover provides a sample inventory file to
import). HASS-CLOVER-2: G installed a **production read token** (Inventory: Read only) on 2026-11-10 and the real store is connected READ-ONLY with
`environment: production`, `liveApproved: false`. `liveApproved` now gates WRITES only (`CloverConfig.writes_allowed`); no write path exists yet, and a
write card must also hold a separate write token.

## 2. Data model

| Clover item field | Hass site product field | Rule |
|---|---|---|
| `id` | (none: kept in the private link) | the stable key for every write |
| `name` | `name` | **never synced**. The site's name and the till's name may differ; a mismatch is reported (`status`), not fixed |
| `sku` | (none: kept in the private link) | the site has no SKU by design; `sku` is a refused word in site text (`live_policy.COMMERCE_WORDS`) |
| `code` (barcode) | (none) | read-only to Hass; a matching aid |
| `price` (cents), `priceType` (`FIXED`, `VARIABLE`, `PER_UNIT`), `unitName` | **never** | prices stay off the site (AGENTS.md catalog-only scope; the live policy refuses price words). Variable-price items have no price to change |
| `categories` (names) | `category` (one of the nine site words) | a settings map `categoryMap` {site word: Clover category name}; Hass never creates a Clover category |
| `tags` | none | read and cached, used for nothing in v1 |
| `itemStock.quantity`, `stockAlertThreshold` | `available` (`yes` / `limited` / `no`) | approved draft (flow 5), or the separately opted-in Website stock words path below. The site never shows a count |
| `hidden`, `available`, `autoManage` | `status` (`active`/`hidden`/`held`) | different meanings (hidden on the Register vs. hidden on the website); a disagreement is reported, never copied |
| `modifiedTime` (ms) | (none) | the stale check and the incremental sync |
| `cost`, tax rates, modifiers, employee or customer fields | n/a | **dropped on read** (the mapper is a whitelist) |
| (none) | `brand`, `producerKey`, `description`, `image`, `displayBrand` | site-only; never sent to Clover |

**The link.** The private table `<state>/clover/links.json` (mode 0600, never in Git, written only by the `link` commands below and by the SKU recorded at creation) holds
`{product id: {"cloverId": ..., "sku": ...}}`. A site product has no price, SKU or count and the content model is closed, so this table is the only place the two sides meet.
HASS-LINK adds the commands (`hass/clover/links.py`; cache and local products only, no token, no network, no editor call, so linking or unlinking never sets a website word):

* Operator: `python3 -B hass/clover/cli.py link suggest --host host.json` suggests **exact names only** (the step-3 rule below): exactly one unlinked active site product and exactly one
  unlinked till item with that name. It saves one draft (`<state>/clover/link-draft.json`: code, the cache's as-of, the pairs) and a private list
  `<state>/clover/reports/link-suggest.md` for Mike to read; stdout is counts and the code, never a name. Same-name clashes (a name on both sides with more than one item on either side: every site product and every till item of that name) and one-sided items are listed, never linked; items sharing a name carry a label unique across the whole name group, site and till together (site product id; till SKU only when no other item of that name shares it, else the till item id; a label equal to another's becomes `site <id>` / `till <item id>`).
* Owner only (his private chat; another sender or a group changes nothing): `link all <code>` is the one yes that writes **every** pair in the draft at once. It is refused as stale,
  writing nothing, when the cache changed since the draft or any pair is no longer an exact unlinked match; the list must then be made again. `link X to <SKU>` links one exact
  website name (or product id, for two products with one name) to one exact till SKU (both unlinked); `unlink X` removes a link.
* Website stock words (STOCK-SITE): a newly linked product is new to `stock_site`, so the next good read proposes the usual one-line preview. The owner answers `stock yes <code>` or
  `stock no <code>` (the `stk-...` code); either calls `stock_site.approve` / `decline` once. An unknown, stale, finished or already approved code makes no call.

**Matching order** (`hass.clover.mapper.match`): (1) the stored link, (2) the SKU in that link when the item's id changed (item recreated), (3) the **exact** name, ignoring only
letter case, spacing and curly apostrophes (accents stay significant), and only when exactly one site product and exactly one till item hold that name. A name match is good for
reading; it is stored as a link only after Mike's `yes` to "link these?". Anything with two candidates is *ambiguous* and Hass asks Mike to name the SKU. A link whose item vanished is
*broken* and is reported, **not** repaired by name behind his back. **Writes never use anything looser than an exact SKU or an exact visible name** (`resolve_exact`); the "Did you
mean ..." help (`suggest`, every word of the query present in the name) is read-only and can never pick a write target. A hidden item is writable only by its exact SKU.

**One side only.**
* *On the till, not on the site:* listed on request ("on the till but not on the site: 14"). Hass never creates a site product from it; "put X on the site" starts the existing new-product flow with its own picture and words.
* *On the site, not on the till:* stock questions say "X is on the website but not in the till, so I have no count." Hass offers to add it to the till (Mike supplies the price; the draft is flow 6).
* *Broken or ambiguous link:* named, with the SKUs to choose from. No write happens until Mike names one.

## 3. SKU generation

Mike: "new item: Sunshine olive oil, 12.50, pantry". Hass reads it with a fixed pattern (no model), turns `12.50` into **1250 cents** by integer arithmetic (no floats; more than two decimals, zero,
negative or over $1,000.00 is refused with a plain sentence), checks `pantry` is one of the site's nine categories, and builds:

> Did you mean to add this to the till?
>   Item: Sunshine olive oil
>   SKU: AS-PAN-SUNSHINE-OLIVE-OIL-01 (made up by me, the next free number)
>   Price: $12.50 each
>   Category: Pantry
>   Count: not counted yet (say 'received 12 Sunshine olive oil' to start counting)
>   Tax: your till's usual setting; I set none
> Nothing goes on the website.
> Reply yes a1b2 to do this, or no a1b2 to drop it. Nothing changes until you say yes.

**Scheme** (`hass/clover/sku.py`): `AS-<CAT>-<NAME>-<NN>`.
* `AS` marks a SKU Hass made. `CAT` is three letters from the site category (fruit FRU, vegetables VEG, dairy DAI, eggs EGG, meat MEA, pantry PAN, drinks DRK, bread BRD, flowers FLW; anything else `GEN`).
* `NAME`: accents dropped, capitals, apostrophes removed (`Linn's` becomes `LINNS`), small joining words (the, a, of, and, ...) left out, cut at a word boundary to at most 18 characters.
* `NN`: the first of 01-99 not already used by **any** SKU **or barcode** in the till, hidden items included, compared ignoring case. At most 28 characters in all.
* **Deterministic:** the same name, category and till contents always give the same SKU. **Readable:** a person can tell what it is. **Stable:** a SKU is issued once and never regenerated: renaming an item
  or changing its category leaves it; Hass refuses to change a SKU that exists. **Unique:** checked against the cache when the draft is made and again against the live till (`GET /items?filter=sku=<sku>`)
  right before the create is sent; a clash there means a new draft with the next number, never an overwrite.
* **Duplicate name:** if the till already has a visible item with exactly this name there is no new SKU: "Sunshine olive oil is already in the till (SKU AS-PAN-SUNSHINE-OLIVE-OIL-01). Did you mean to change its price or its count?"
  A longer name that shortens to the same 18 characters ("Sunshine olive oil 1 litre") gets the next number (`-02`).
* "give X a SKU" (for an item already in the till with none) drafts the same scheme and only for an item with an empty SKU. 99 numbers used up for one short name is reported ("give the item a more specific name").
* Unknown until the sandbox rehearsal: Clover's maximum SKU length and whether it matches case-insensitively. The scheme stays well under any plausible limit and compares case-insensitively to be safe.

## 4. Write safety (money-adjacent)

* **Every Clover write is a draft** (`hass/clover/drafts.py`): plain words for the exact change (item, SKU, price before and after, count before and after), the exact Clover calls it would make, a journal record
  (`before`, `after`), and the stale-check values. Builders only build; nothing here sends anything.
* **Approval is the existing approval.** The conversation layer turns the draft into a proposal with a code; only the owner's `yes <code>` applies it, bound to sender, chat, change id, draft hash, base revision and expiry,
  exactly as for a site change (`docs/hass/COMMANDS.md`). A bare `yes`, a reaction, an edit or a `yes?` approves nothing. `stop changes` stops Clover writes too. A draft's id is `clv-` plus 12 hex of the SHA-256 of
  its full content, so a changed draft is a different draft and needs its own yes.
* **Daily cap:** at most `dailyWriteCap` Clover changes per Pacific day (default 20). Over the cap: "I have already made 20 changes to the till today, which is my daily limit. Nothing was changed. The count starts again at
  midnight Pacific." Checked when the draft is made and again at apply. `undo` is exempt (it only puts back what was there) but still needs its own yes.
* **One owner yes for every kind, including prices.** G amended this on 2026-11-16: `priceConfirmPct` never requires a second yes (the legacy setting only affects warnings). A price must stay between $0.01 and `maxPriceCents` (default $1,000.00) as a typo guard.
* **No deletes, hide only.** There is no DELETE call anywhere in the code (a test checks every draft's methods are POST or PUT on `/items`, `/item_stocks` or `/category_items`). Taking an item off is `hidden: true`;
  "show it again" is `hidden: false`. A count record is never deleted either.
* **Journal and undo.** Before a call, the apply step writes an *intent* row (draft, before, after) to `<state>/clover/journal.sqlite3` (0600); after the call it reads the item back from Clover, compares, and settles
  the row `applied` or `failed`. A restart settles rows left `intent` by reading the item (the same idea as the editor's `recover`): it never applies twice. `undo` drafts the inverse (`build_undo`): old price,
  old count, old SKU, hidden flag back, or hide a created item. It **refuses to overwrite a newer value**: if the price, count or SKU changed again after the draft, Hass says so and asks what Mike wants.
  A stock draft that changes the site word also journals the word the site showed before (`before`/`after` `site`); its undo puts that word back, and only while the site still shows the word the draft set. A product that had no word before gets
  no word back (`product.clear_availability`), never an invented "Available today"; a journal that does not say what the site showed is refused with a plain reason.
  One honest limit: the first-ever count on an item that had none cannot be undone (that would be deleting the count record, which Hass never does); Hass says so and offers "set X to <number>".
* **Durable till yes (M2):** before acknowledging a yes, its bounded job is saved in the same conversation transaction as the provider id. Desk attachment at startup and provider redelivery reconcile these jobs under a process lock. Drafts may run once through all existing gates; interrupted intents become durable uncertainty and are never resent. Settled results only enqueue an outcome to the approving owner's chat. Job completion and that outbox row commit together; completed jobs may be pruned, pending jobs are never evicted (256-row cap, backpressure before acknowledgement). This guarantees one queued outcome, not exactly-once transport delivery across a lost send receipt. Website bundle crash recovery remains a separate gate; no engine is connected by this change.
* **Stale check at apply:** the item is re-read live; if its `modifiedTime` or its stock's `modifiedTime` moved since the draft (a sale decrements stock on its own), the draft is stale, nothing is written, and Mike gets a fresh draft
  that needs its own yes. "Received 12" is computed from the till's current count and shown as both numbers ("Count: 12 -> 24"), and the live re-read makes that arithmetic race-safe.
* **Clover is the source of truth for price and stock.** The site never shows a price or a count; the live policy still refuses price words in site changes (`COMMERCE_WORDS`, the "prices" protected sentences, the
  interpreter's `PRICE_REPLY`). Clover messages are parsed by fixed patterns **before** the interpreter, so a price Mike types for the till never enters a site draft, an interpreter prompt or the audit; a site operation
  produced by a Clover draft carries only a product id and one of the three availability words (a test checks no price, count or SKU can ride along).
* **No checkout, payment, refund, discount or order authority, ever.** The token has no Orders or Payments permission, the client's path allow-list has no such path, and the draft builders have no such kind. Adding one
  would be a new design, a new card and a G decision.
* **Data class `finance-local`.** Prices and counts are handled by local code only: no model writes a Clover reply or sees a Clover answer, and none of it is sent to a cloud model.

## 5. Inventory flows Mike can text

Clover commands are exact patterns; anything else still goes to the interpreter exactly as today. (Build card HASS-CLOVER-4 adds them to `COMMANDS.md`, `help` and the parser tests; this card changes none of those.)

| Mike texts | Kind | Hass replies | Also changes the website? |
|---|---|---|---|
| `how many Sunshine olive oil do we have` | read | `Sunshine olive oil: 12 in the till.` (labelled if old; a near name is a "Did you mean", never a guess) | no |
| `low stock` | read | `Sold out: ... Low (5 or fewer): Eggs, dozen 2. 1 item(s) have no count in the till, so I can't tell.` | no |
| `received 12 Sunshine olive oil` | write (set count = till count + 12) | `Add stock to ...? Count: 12 -> 24, Received: 12` + yes line | only if the site says Sold out: marks it **Available today** in the same draft |
| `set Sunshine olive oil to 7` / `... to 0` / `Sunshine olive oil is sold out` | write (set count) | `Set the count of ...? Count: 12 -> 7` or `Mark ... as sold out? Count: 12 -> 0` | at 0: marks it **Sold out** (if the site does not already say so); from 0 up, back to Available; otherwise no site change |
| `new item: Sunshine olive oil, 12.50, pantry` | write (create + category link) | the "Did you mean to add ..." draft in section 3 | no (a new till item is not on the site until Mike says "put it on the site") |
| `change price of Sunshine olive oil to 14.00` | write (set price) | `Change the price of ...? Price: $12.50 -> $14.00 each (+12.0%)`; one yes even for a big move | **never** (the site shows no price) |
| `give X a SKU`, `hide X on the till`, `show X on the till` | write | the plain draft for that change | no |
| `undo` / `undo <code>` | write (inverse) | the restoring draft, or the reason it cannot | the site part is reversed in the same draft when the original had one |

Every write ends `Reply yes <code> to do this, or no <code> to drop it. Nothing changes until you say yes.` Reads work while paused and change nothing.
**One change, one yes:** "sold out on Clover marks sold out on the site through the EXISTING live path" means the draft carries the typed op `product.set_availability {id, available}` next to the Clover calls. One proposal,
one `yes <code>`. Apply order: Clover first (read back and journalled), then the site op through the normal editor and live-release path. If the Clover write fails, the site is not touched. If Clover succeeds and the site step
fails, Hass says exactly that ("The till is updated; the website is not yet - I'll try again / say 'retry'"); the next sync shows the difference and offers a draft to mark the site, never a silent change. `undo` reverses both.
The existing shelf-check rule is unchanged: when no shelf check is recorded for today, the existing question ("Before I change that, is the shelf list right for today?") comes first and the bundle waits for it.
**Precedence:** when a product is linked to a till item and Clover is reachable, a count message goes to the bundle above; when it is not linked, or the till is unreachable, the message follows today's site-only stock skill
unchanged. "Got more honey in" with a linked product asks "How many came in?" (a till count needs a number); "just mark it available" keeps the site-only path.

## 6. Sync, cache, staleness, privacy

* **Pull** (read-only, the client in section 1): every 15 minutes an incremental pull (`filter=modifiedTime>=` the last pull minus 2 minutes, `expand=itemStock,categories,tags`), plus a full pull nightly at 03:15 Pacific that replaces the
  cache (this catches items removed in the till). **On demand:** a question about one item re-reads that item first if the cache is over 5 minutes old; a write always re-reads the item live (at draft time and again at apply).
* **Cache (HASS-CLOVER-2, built):** `<state>/clover/cache.sqlite3` (folder 0700, file 0600, owner the service user; `hass/clover/cache.py`). One sync replaces every row
  in one transaction. Per item: id, name, SKU, barcode `code`, price in cents, price type, unit, category ids and names, hidden, available, the stock count (from
  `GET /item_stocks` where the merchant counts the item, else none) and modified times; plus `asOf`, `lastAttempt`, `lastResult` (one fixed word), `failures` and
  `nextAttempt`. It is derivable and not in the state backup; it is never in git (the sync refuses a state folder inside the repository) and never on the site.
  No `cost`, no tax, no sales, no customer or employee data exists in it.
* **Built in HASS-CLOVER-2:** a FULL pull every 15 minutes (`hass-clover-sync.timer`; a shop's few hundred items are 2 requests), paging, pacing (0.25 s),
  retries (429/5xx, `Retry-After`), and a backoff between failing runs (15, 30, 60, 120, then every 240 minutes; `--force` ignores it). The incremental pull and
  the on-demand re-read above are not built (a later card may add them).
* **Staleness label** (`hass/clover/reads.py`): up to 20 minutes old, answered as is; older, `(till count as of 3:09 pm)` (`Sun 4:30 pm` if not today); Clover unreachable: `I can't reach the till right now. The last count I have is from 2:00 pm,
  so treat it as old.` before the answer; over 24 hours old: no count is quoted at all ("I have not been able to read the till since Sun 2:30 pm, so I will not quote a count that old.").
* **When Clover is unreachable** (network down, 5xx after retries, 429 after retries, 401 after the token is revoked or expired): reads answer from the cache with the label above; **writes are refused** ("I can't reach the till, so nothing
  was changed") and a 401 is reported as a health problem to the operator by reason word only (the token is never mentioned). The site and the rest of Hass are unaffected.
* **Privacy:** only the read endpoints above are ever called (HASS-CLOVER-2: the allow-list is exactly the merchant's basic record, items, item stocks and
  categories; `/tags` was dropped; a test pins it) (the client refuses `/orders`, `/payments`, `/customers`, `/employees`, `/refunds`, anything else, any other method, any other host); sales and customer data are **never**
  requested; nothing leaves the box except the HTTPS requests to the Clover host, and no model is involved (section 4). Logs carry the path template and the status number only. `status` shows counts of items, never prices.

## 7. Rollout and who does what

| Step | Who | What |
|---|---|---|
| 0. This card | sonnet-coder, reviewer queued by the operator | design, `hass/clover/`, fixture tests, `docs/hass/CLOVER.md`. No credential, no network |
| 1. Accounts | **G** | Clover developer account, one sandbox test merchant (with Clover's sample inventory imported), one sandbox API token, stored as below |
| 2. HASS-CLOVER-2 (build) | worker | done: settings block `clover` in **host.json** (`hass/host.py` KEYS and check), `cli.py check/sync/status`, cache, 15-minute timer template, the three read replies, health `clover-token` / `clover-sync`; **production, read-only** (G installed the read token first, skipping the sandbox for reads) |
| 3. HASS-CLOVER-3 (build) | worker | apply step (intent row, live re-read, stale check, call, read-back, journal), undo, cap, one owner yes; fixtures only |
| 4. HASS-CLOVER-4 (build) | worker | owner commands, `help`, `COMMANDS.md`, parser-before-interpreter wiring, the site bundle and its undo |
| 5. Sandbox rehearsal | worker + G reads | run section "Sandbox acceptance" with the sandbox token; evidence on the card |
| 6. Go-live card | **G approves** | see the checklist |

**Sandbox acceptance** (all unverified facts from Clover's pages that the rehearsal must prove): partial `POST /items/{id}` changes only the sent field; `POST /items` with `sku`; `POST /category_items` path and body; `PUT /item_stocks/{id}`
with `{"quantity": n}` sets (not adds) and works on an item with no stock record; `GET /items?filter=sku=` works; `sku: ""` clears a SKU; the SKU length limit and case rule; 401 vs 403 behaviour; 429 headers; paging
past 1000; a sale in the sandbox register changes the count (so the stale check fires); a hidden item stays listed; and that the only requests made are the six reads and the four writes (the transport's request log).

**Go-live checklist** (G approves each): (a) sandbox acceptance evidence reviewed; (b) G confirms Mike's real Clover dashboard has *Settings, Business Operations, API tokens* (else stop: OAuth fallback is a new design); (c) G creates a **production read token**
(Inventory: Read only), stores it in the production token file, and sets `environment: production`, `liveApproved: true` via a reviewed config change; (d) **read-only week:** sync and reads only, compared with the till by eye;
(e) G creates the **write token** (Inventory: Read + Write) and a second file; the daily cap starts at 5; (f) first live writes watched by G on one test item that Mike creates and hides; (g) revocation drill: G revokes the token in the Clover
dashboard and Hass shows the reason word and refuses writes; (h) the cap is raised to its normal value.

## Go live: read-only (HASS-CLOVER-2; the operator, after review and merge)

Facts: merchant id `W68KRZHTAH801` (an identifier, not a secret); environment `production` (`https://api.clover.com`); token file
`/home/user/.config/hass/clover/production-read.token` (mode 600, folder 700, owned by the service user, created by G). **Nobody reads, prints, copies or
`cat`s that file**; `stat` is fine. The runtime worktree is updated the usual way (`docs/hass/MAC_RUNBOOK.md`); nothing here is run from a writer worktree.

1. **Settings block.** In the private `~/.local/state/hass/host/host.json` (mode 600) add, keeping every other key:
   ```
   "clover": {"environment": "production", "merchantId": "W68KRZHTAH801", "tokenFile": "/home/user/.config/hass/clover/production-read.token", "liveApproved": false}
   ```
   Optional keys, all range-checked: `lowStockThreshold` (default 5), `dailyWriteCap`, `priceConfirmPct`, `maxPriceCents`, `maxStock`, `categoryMap` (writes; unused yet).
   Closed keys: anything else is refused by field name (`clover.<field>`), never by value.
2. **Static check (no network):** from the runtime, `python3 -B hass/host.py check --host ~/.local/state/hass/host/host.json`.
   Expected `{"clover": "ok", "result": "ok"}`. A token problem is one word: `{"clover": "mode", "result": "clover"}` (`missing`, `unreadable`, `not-regular`,
   `owner`, `mode`, `folder`, `size`); fix it with `chmod`/`chown` on the file or folder only. A bad block is `{"fields": ["clover.<field>"], "result": "config"}`.
3. **Live check (two GETs):** `python3 -B hass/clover/cli.py check --host ~/.local/state/hass/host/host.json` (or `python3 -B -m hass.clover.cli check --host ...`
   from the runtime folder). One JSON line, e.g. `{"elapsedMs": 412, "environment": "production", "itemCount": null, "items": "2xx", "itemsOnPage": 1,
   "merchant": "4xx", "merchantId": "W68KRZHTAH801", "merchantMatches": null, "readOnly": true, "result": "ok", "tokenAccepted": true, "tokenFileOk": true}`.
   `merchant` may be `4xx` (the token has no Merchant permission; expected). `items: "4xx"` with `tokenAccepted: false` = Clover refused the key (wrong token or
   missing *Inventory: Read*): stop and tell G (no retries). `unreachable` = network. It never prints a header, the token, a body, a name or a price.
4. **First sync:** `python3 -B hass/clover/cli.py sync --host ~/.local/state/hass/host/host.json`. Expected `{"asOf": "...", "counted": <n>, "elapsedMs": ...,
   "items": <n>, "result": "ok", "skipped": 0}`; then `python3 -B hass/clover/cli.py status --host ...` shows the same `asOf` and `itemCount`.
   Check `stat -c '%a %U' ~/.local/state/hass/state/clover ~/.local/state/hass/state/clover/cache.sqlite3` reads `700` and `600`.
5. **Timer:** `cp ~/.local/share/hass/runtime/deploy/hass/hass-clover-sync.{service,timer} ~/.config/systemd/user/`, `systemctl --user daemon-reload`,
   `systemctl --user enable --now hass-clover-sync.timer`. Exit 1 (Clover down this time) is recorded and is not a failed unit; exit 2 (config, token, state) is.
6. **Chat:** `systemctl --user restart hass-worker` (the worker reads host.json at start; with the block it answers till questions). Owner smoke test:
   `how many <item> do we have`, `low stock`, `is <item> in stock`, `is <item> sold out` answer from the cache; `change the price of <item> to 5` answers
   "I can read the till but I can't change it yet."; a hike or website question is unchanged.
7. **Health:** `hass-health` now also reports `clover-token` (one word) and `clover-sync` (no good pull for over 2 h, with the last result word).
8. **Turn it off:** `systemctl --user disable --now hass-clover-sync.timer`, remove the `clover` block, restart `hass-worker`. The cache may stay (private) or be
   removed by the operator. G revokes the token in the Clover dashboard if it is ever exposed.

What the owner sees (voice rules): counts as the till has them; after 20 minutes `(till count as of 3:05 pm)`; when the last pull failed, "I can't reach the
till right now. The last count I have is from 2:00 pm, so treat it as old."; over 24 hours, no count at all; before the first pull, "I haven't been able to
read the till yet ..."; any add/change of an item, count or price: "I can read the till but I can't change it yet." A question is claimed only when it uses
stock words (`do we have`, `left`, `in stock`, `on hand`, `sold out`) or names a till item; hike, sign-up, website, draft or photo questions go on as before.

## What G does (the exact steps)

All of this is G's own hands; no worker, tool or chat sees the token. **Sandbox first.**
1. In the Clover **Global Developer Dashboard** create a developer account if there is none, then *Test Merchants*, create one (a sandbox test merchant) and import Clover's sample inventory.
2. *Launch Dashboard* on that test merchant, then **Settings, View all settings, Business Operations, API tokens, Create new token**. Name it `hass-sandbox`. Tick **only** the inventory permissions: **Inventory: Read** and **Inventory: Write**
   (the sandbox token is allowed both; the labels in Clover's page are "Read inventory" and "Write inventory"). Tick **nothing** for customers, employees, merchant, orders, payments or ecommerce. Create the token and keep the page open.
   (Clover suggests a dedicated Admin employee for generating tokens; do that.)
3. On AgentOrange, as the Hass service user, with `<state>` the `state` folder named in `host.json`:
   `install -d -m 700 <state>/clover`, then `umask 077; read -rs T; printf '%s' "$T" > <state>/clover/sandbox.token; unset T; chmod 600 <state>/clover/sandbox.token`
   (paste the token at the silent prompt; it is not echoed and not stored in shell history). Check with `ls -l <state>/clover/sandbox.token`: it must read `-rw-------`, owned by the service user, and nothing else may be printed or shared.
4. Give the **sandbox merchant id** (13 characters, shown in the dashboard URL; it is an identifier, not a secret) on the HASS-CLOVER-2 card.
5. Later, only at the go-live card: the **production read token** (Inventory: **Read** only, name `hass-read`, file `<state>/clover/production-read.token`), and after the read-only week the **write token** (Inventory Read + Write, name `hass-write`,
   file `<state>/clover/production-write.token`). Same mode 600, same owner. Never paste a token into a card, comment or chat.

## Mapping to the open questions in SKILLS-SPEC 5.2

1 POS: Clover. 2 Direction: read and, by approved draft, write items and stock only. 3 Source of truth: Clover for price and count; Hass content for words, pictures, makers; the site word follows only through an approved draft. 4 Identity: the private
link table, exact matching, one-sided items reported. 5 Prices on the site: never. 6 Approvals: the same owner `yes <code>`, a daily cap, one yes even for big price moves, no deletes. 7 Money/customer data: items and stock only; no sales,
customers or card data, ever. 8 Where processed: local code only; no model sees Clover data. 9 Credentials: G creates and installs one file; the service reads it; revocation drill at go-live. 10 Counts vs words: counts live in Clover; the site
shows a word. 11 Failure: cached answers labelled old, writes refused, nothing quoted after 24 hours. 12 Refunds, voids, shrink, spoilage: not pulled (they are sales data); a count can drift when sales happen, which is why every write re-reads first.

## The code

HASS-CLOVER-2 adds `cache.py` (the private cache), `sync.py` (one pull: items + item stocks, whitelisted rows), `cli.py` (`check`, `sync`, `status`),
`chat.py` (the owner's three reads and the write refusal, from the cache only; wired by `hass/host.py make_worker` when host.json has a `clover` block,
and called by `hass/conversation.py` before the interpreter), `credential.inspect` (stat-only check), the `deploy/hass/hass-clover-sync.{service,timer}`
templates and tests `hass/tests/test_clover_{cli,chat,host}.py` (recorded fixtures, sockets patched, a token leak test and a forbidden-path test).
The transport now ignores environment proxies. HASS-CLOVER-1's `hass/clover/` (stdlib only): `credential.py` (token file check, `Token`, redaction), `client.py` (read-only client, injected transport, pacing, retries, allow-list), `transport.py` (the real HTTPS layer with host allow-list and
no redirects, never called by a test against a network; plus the replay layer the tests use), `mapper.py` (whitelist parse, cents maths, matching, exact resolve), `sku.py`, `config.py`, `drafts.py` (five write kinds plus undo), `reads.py` (read replies and
staleness). Tests: `hass/tests/test_clover_{credential,client,mapper,sku,drafts,reads}.py` on hand-written fixtures in `hass/tests/fixtures/clover/` (fake merchant `FAKEMERCH0001`, fake ids, fake token string); every test runs with sockets
patched so any network attempt fails the run. `python3 -B hass/acceptance.py` is unaffected.

## Sources (public Clover developer pages; retrieved 2026-11-09)

* Rate limits: https://docs.clover.com/dev/docs/api-usage-rate-limits
* Permissions (Read/Write per category; inventory endpoints): https://docs.clover.com/dev/docs/permissions
* Merchant-specific API tokens: https://docs.clover.com/dev/docs/gdp-create-merchant-specific-api-token and https://docs.clover.com/dev/docs/generate-a-test-api-token
* Test merchant id and token; sandbox only: https://docs.clover.com/dev/docs/merchant-id-and-api-token-for-development
* OAuth and tokens FAQ (merchant-generated tokens for internal tools; 30-minute OAuth tokens): https://docs.clover.com/dev/docs/oauth-and-tokens-faqs
* Base URLs, Bearer auth: https://docs.clover.com/dev/docs/making-rest-api-calls ; 401 behaviour: https://docs.clover.com/dev/docs/401-unauthorized
* Manage items (create, view with `expand=itemStock`, money in cents): https://docs.clover.com/dev/docs/managing-items-item-groups
* Reference: https://docs.clover.com/dev/reference/inventorygetitems (filters, `limit` max 1000), https://docs.clover.com/dev/reference/inventorycreateitem, https://docs.clover.com/dev/reference/inventoryupdateitem (cannot change stock),
  https://docs.clover.com/dev/reference/inventoryupdateitemstock, https://docs.clover.com/dev/reference/inventorygetitemstock
* Filters and expansion: https://docs.clover.com/dev/docs/applying-filters ; tags: https://docs.clover.com/dev/docs/managing-tags
* Item-category association (`POST /v3/merchants/{mId}/category_items`): named in Clover's reference index https://docs.clover.com/dev/reference/llms.txt; the path was read from a third-party mirror of the spec
  (https://skmtc.dev/clover/apis/platform-api/docs/v3/merchants/:mId/category_items/post), so it is on the sandbox acceptance list.

Limits of this research: only public pages were read, no Clover account was used, and the token-permission dialog itself (its exact checkbox labels) was not seen, only Clover's text about it. Where a fact came from a search excerpt rather than a full page it is
on the sandbox acceptance list above.

## HASS-CLOVER-3 engine and write go-live (2026-11-16)

The standalone `ApplyEngine` now offers persisted, expiring `clv-` drafts with a
random approval code bound to an explicit owner `(sender, private chat)` pair.
Mike owns changes; G owns them only with `g_is_owner` enabled by the service.
Original private `yes <code>` only: groups, edits, reactions and bare yes refuse.
`stop changes` persists a pause. Chat wiring and site bundles remain CLOVER-4;
the engine refuses a draft carrying site ops rather than silently omitting them.
There is no live write enablement in this PR. Read-only client behaviour stays unchanged.

Write service construction requires `writes: true`, `liveApproved: true` and
an absolute `writeTokenFile` distinct from `tokenFile`, even for sandbox.
`credential.load_write_token` applies the same private-file checks and refuses
aliases of the read file. Only the deterministic service may load it; workers
and reviewers never read any real token file. The client factory must construct
`CloverWriteClient` with that token, the configured merchant/environment and the
existing allowlisted transport. Writes are single-attempt POST/PUT only.

`journal.sqlite3` is private 0600 in the private Clover folder; operations hold
one cross-process lock. Intent commits before the live stale check, then calls,
read-back and settlement. Recovery only reads: it never retries a write or a
partially completed create/category bundle. Uncertain outcomes need attended
reconciliation; attempted/uncertain changes conservatively consume the cap.
Undo uses the recorded read-back revision and gets a separate approval; it is
cap-exempt but cannot overwrite a later till edit. Default cap is 20 per Pacific
day. At the separately reviewed write go-live set `dailyWriteCap: 5`; the first
live write must be **TESTITEM**, watched by G. This fixture PR neither installs
credentials nor changes host.json, services, chat routes or the live till.

## M4b: writeMode and count sentences

Set `writeMode` inside the private host's `clover` block. Omit it to keep
cache-backed questions and no write engine. Use `"dry-run"` for rehearsal: the
engine uses the read token and records the proposed Clover calls locally without
sending a write. Rehearsal codes and receipts are kept in a separate private
journal and are not live approvals. When set, `host.py check` reports `writeMode`
as `dry-run` or `live` alongside `clover`; when unset, the output has no
`writeMode` key. It checks the read token by file metadata, and the write token
too in live mode. It does not open either token.

`"live"` is an attended operator setting, not a default. It also requires
`writes: true`, `liveApproved: true` and a separate `writeTokenFile`, even in
sandbox. The service loads that token only when the live engine needs a client.
Mike is the owner; G's own private chat is eligible only with `gIsOwner`.
Complete the attended rehearsal and the write go-live checklist before enabling
live mode. Remove `writeMode` to return to read-only on the next worker start.

For a supported count sentence such as `set Example mug to 12`, review the exact
before/after count and reply with the preview's `yes <code>`. The M4b goal is to
support everyday count sentences too; this host switch does not change the parser,
approval rules or undo. Prices, counts and rehearsal records stay finance-local.
