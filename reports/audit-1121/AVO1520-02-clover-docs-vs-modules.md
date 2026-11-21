# Clover docs versus modules

| Check | Result on main |
| --- | --- |
| R1 — Clover and POS reference | Most named files and operator commands exist. The Clover design describes some paths the current chat does not take; POS's report is wired but its dedicated chat views are not (R1). |
| R2 — Count phrases | The published baseline reproduces: **37/60 exact**. Of 19 positive gaps, 13 return no intent and six return the wrong intent; the four documented false accepts still accept. The standalone parser is not the chat parser (R2). |
| R3 — Public callables | No public module-level definitions in `chat.py`; ten public methods and six `reports.py` functions are inventoried below. The docs describe some of their effects but rarely name the callables (R3). |
| R4 — Follow-up | One optional docs-only clarification, estimated 45–75 minutes after separate approval; no change recommended to parser or routing in this audit (R4). |

Source: `origin/main` = `37feae1dc5efa6968f90d17a1eda6daed29afd4a` (matched card baseline on 2026-11-21). Below, C = `docs/hass/CLOVER.md`, Q = `docs/hass/CLOVER-COUNT-PHRASES.md`, P = `docs/hass/POS.md`. Source anchors beginning `clover/` mean `hass/clover/`. “Present” means tracked code, a static route or a fixture, not an installed service or successful live call. Commands and example sentences are quoted from the repo; personal paths and merchant identity are not repeated. No credentials, real config or runtime data opened. Nothing here adjudicates design versus behavior or deployment.

## R1. Reference inventory

### Modules, symbols and files

Expanded brace lists name separate files. `git ls-files -- <path>` reproduces the tracked-file checks; no private path was probed on disk.

| Named reference | Doc | Tracked location or source use |
| --- | --- | --- |
| `hass/clover/` | C:7,362,443 | Present; `git ls-files -- hass/clover`. |
| `hass/clover/cli.py`, `cli.py`, `hass.clover.cli` | C:17–19,240,364,394–400,439; P:45 | Same entry point; `clover/cli.py:235–260`. |
| `cache.py`, `hass/clover/cache.py` | C:342,439; P:24–25 (cache) | `clover/cache.py:31–42,159–178`. |
| `sync.py` | C:439 | `clover/sync.py:74`; called at `clover/cli.py:147–159`. |
| `chat.py` | C:440 | `clover/chat.py:119–125,139–162`. |
| `credential.py`, `credential.inspect`, `Token`, `credential.load_write_token` | C:145,152–155,441,443,478 | `clover/credential.py:40,94,188`; callers `hass/host.py:413–420,565–571`, `hass/health.py:261–277`, `clover/dryrun.py:39–55`. Source only. |
| `client.py`, `RateLimited`, `CloverWriteClient` | C:211,443,481 | `clover/client.py:56,92,242–250,256–275`. |
| `transport.py` | C:443 | `clover/transport.py:20–50` (real and replay transports). |
| `mapper.py`, `hass.clover.mapper.match`, `resolve_exact`, `suggest` | C:249–253,444 | `clover/mapper.py:224,277,309`; `suggest` in this paragraph is the read helper, not `links.suggest` or the CLI subcommand. |
| `sku.py` / `hass/clover/sku.py` | C:275,444 | `clover/sku.py:39–79`; SKU shape, category map, normalization and collision loop; apply-time collision guard `clover/apply.py:69–74` checks the live item list, not the example's SKU-filtering request. |
| `config.py`, `CloverConfig.writes_allowed` | C:216,444 | `clover/config.py:27–49,55–87`. `liveApproved` is not sufficient by itself. |
| `clover`, `environment`, `merchantId`, `tokenFile`, `liveApproved`, `writeTokenFile`, `writes`, `writeMode` (`dry-run`, `live`), `dailyWriteCap`, `priceConfirmPct`, `maxPriceCents`, `maxStock`, `categoryMap`, `lowStockThreshold`, `clover.siteStock`, `siteStockWords` | C:33,85–87,148,215–217,228,294–296,385–390,476–482,491,497–511 | Setting names, not commands: `clover/config.py:13–15,27–48,55–87`; `hass/host.py:475–501,555–571`; draft limits and warning `clover/drafts.py:85–115,169–192`. No live settings read. |
| `drafts.py`, `hass/clover/drafts.py`, `build_undo`, `set_stock` | C:289,300,444; P:29 | `clover/drafts.py:22,31,237–250,292–329`; `set_stock` is a draft kind, not a function of that name. |
| `reads.py`, `hass/clover/reads.py` | C:350,445; P:40 | `clover/reads.py:30–64,91–152`. |
| `hass/clover/links.py` | C:238 | `clover/links.py:55–76,79–133`. |
| `hass/clover/pos.py` | P:5 | `clover/pos.py:30–129,150–169`. |
| `stock_site.py`, `stock_site`, `stock_site.approve(state, code, owner_role)`, `decline` / `stock_site.decline` | C:91,102–103,246–247 | `hass/stock_site.py:267–305`; actual third parameter is named `owner` (the chat caller passes `"owner"`, `clover/chat.py:261–272`). No chat authentication inside these library functions. |
| `hass/host.py`, `host.py`, `KEYS`, `make_worker` | C:152,364,391,440,501 | `hass/host.py:31,438,475–502,555–597`. |
| `hass/health.py` | C:152 | `hass/health.py:261–277`; `clover-token` and `clover-sync` are health labels, not CLI verbs. |
| `hass/conversation.py` | C:441 | `hass/conversation.py:1316–1343,1662–1679`. |
| `editor.MAX_OPS`, `live_policy.MAX_RECORDS`, `live_policy.COMMERCE_WORDS` / `COMMERCE_WORDS`, editor `recover`, interpreter `PRICE_REPLY` | C:116–117,225,300,308–309 | `hass/editor.py:34,470`; `hass/live_policy.py:25–29,453`; `hass/interpret_check.py:27`. |
| `ApplyEngine`, `g_is_owner`, `gIsOwner` | C:468–470,509 | `clover/apply.py:15–33`; `hass/host.py:478–501`. Distinguish Python argument from config spelling. |
| `product.set_availability`, `product.clear_availability` | C:303,331 | Typed operation names, not Python calls: `clover/chat.py:32`; `clover/drafts.py:117–125,195–211`; `git grep -n -e product.set_availability -e product.clear_availability -- hass/editor.py hass`. |
| `docs/hass/TASKMAP.md`, `reports/hass/SKILLS-SPEC.md`, `AGENTS.md`, `docs/hass/MAC_RUNBOOK.md` | C:7–8,227,383,430 | All tracked by `git ls-files -- AGENTS.md docs/hass/TASKMAP.md reports/hass/SKILLS-SPEC.md docs/hass/MAC_RUNBOOK.md`; documentary, not executable. |
| `docs/hass/COMMANDS.md` / `COMMANDS.md`, `docs/hass/CLOVER.md` / `CLOVER.md` | C:292,317,362,366; P:5,20 | Both tracked at `docs/hass/`; current chat command/help implementation at `hass/chat/commands.py:15–28,49–84`, `hass/conversation.py:2675–2681`. |
| `hass/tests/test_clover_{cli,chat,host}.py`, `hass/tests/test_clover_{credential,client,mapper,sku,drafts,reads}.py`, `hass/tests/fixtures/clover/` | C:442,445–446 | All nine named test files and fixture directory tracked: `git ls-files -- 'hass/tests/test_clover*' 'hass/tests/fixtures/clover/*'`. |
| `hass/tests/test_clover_count_phrases.py` | Q:4 | Present at lines 23–113 (cases) and 173–191 (doc parity); imports `clover/qty_words.py:85` at test line 10. HCI-03 and HCI-21 are labels, not module names. |
| `hass/acceptance.py` | C:446 | Tracked (`git ls-files -- hass/acceptance.py`); not run by this audit. |
| `deploy/hass/hass-clover-report.service` / `.timer`, `deploy/hass/hass-clover-sync.{service,timer}` / `hass-clover-sync.timer` | C:54–58,347,402–408,441 | All four templates present: `git ls-files -- 'deploy/hass/hass-clover*'`; run/interval definitions in their `[Service]` / `[Timer]` sections. See CLI and service words below. |
| `hass-worker`, `hass-health` | C:404,407–408 | Service stems present in `deploy/hass/hass-worker.service`, `deploy/hass/hass-health.service`; no live inspection. |
| `hass/content/products.json` | C:37; P:45 (local products) | Tracked path; `clover/reports.py:108–110` reads the writer copy, not this audit. |
| `host.json` (all placeholder/runtime forms) | C:17–19,152,240,364,385–400,404,423,440,493,497–504; P:45 | Not found as that tracked runtime file; a CLI argument, not repository input. `clover/cli.py:60–75,235–250`; `hass/host.py:589–597`. |
| `<state>/clover/` and `<state>/clover/reports/` | C:22,58,401,424,484; P:46 | Runtime paths, not tracked outputs; constructors `clover/cache.py:77–78`, `clover/reports.py:149–157`, `clover/pos.py:150–160`. |
| `<state>/clover/reports/YYYY-MM-DD-stock.md`, `…-mismatch.md` (including `YYYY-MM-DD-stock.md` / `…-mismatch.md`) | C:22–28 | Runtime outputs `clover/reports.py:18–19,141–183`; `--out DIR` changes destination. |
| `YYYY-MM-DD-pos.md`, dated `-pos.md`, `pos-totals.json` | P:18,30–33,48–52 | Runtime outputs `clover/pos.py:18–22,113–129,150–169`. |
| `<state>/clover/links.json`, `<state>/clover/link-draft.json`, `<state>/clover/reports/link-suggest.md` | C:38,236,241–242 | Runtime paths `clover/reports.py:108–125`, `clover/links.py:16,99–118`. |
| `clover/site-stock.json`, `clover/reports/site-stock-totals.json`, `stock-reconcile-<date>-stk-<code>.md`, `stock-reconcile-<date>-gaps.md` | C:107,126–129 | Runtime paths `hass/stock_site.py:48–52,100–106,116–129,195–205`; POS currently sets waiting total to `None` at `clover/pos.py:119`. |
| `<state>/clover/journal.sqlite3` / `journal.sqlite3`, `<state>/clover/cache.sqlite3` / runtime `cache.sqlite3` | C:299,342,401,484; P:5–6 | Runtime stores `clover/journal.py:12–22`, `clover/cache.py:31–42,77–78,159–178`. `snapshots` is a table, not a file (`clover/cache.py:41,168–174,276–295`; P:24). |
| `sandbox.token`, `production-read.token`, `production-write.token`, runtime config/systemd directories, `LoadCredential=` | C:156–158,381–387,401–403,423–428 | No tracked live file evidence; intentionally not inspected. Paths are operator-supplied (`clover/config.py:55–87`, `clover/credential.py:85–119,188–194`); systemd source templates above, no installed paths verified. `LoadCredential=` is an alternative in the design, not found in the tracked Hass unit templates (`git grep -n LoadCredential -- deploy/hass`). |

### Operator commands and API command words

| Word, invocation or path shape | Doc | Status and anchor |
| --- | --- | --- |
| `python3 [-B] hass/clover/cli.py report stock`, `report mismatch`, `report --all`, `report pos`, `--host`, `--out DIR` | C:17–24,55; P:33,45 | Present: `clover/cli.py:182–219,243–247`. `--all` includes POS as well as stock and mismatch, as P says; C's two-output list is incomplete. `-B` is a Python option. |
| `python3 -B hass/clover/cli.py link suggest --host host.json` | C:240; P:20 | Present `clover/cli.py:221–232,248–250`; `clover/links.py:55–76,103–115`. |
| `python3 -B hass/clover/cli.py check/sync/status` (individual subcommands), `-m hass.clover.cli check`, `--force` | C:194,224,348,356,364,394–400,439 | Present `clover/cli.py:104–180,235–260`; `--force` is sync-only. Check's redacted bucketing and merchant response handling are source-only here. |
| `hass/host.py check --host …`, `python3 -B hass/acceptance.py`, `hass/host.py make_worker` | C:152,391,440,446,501 | `check` is CLI (`hass/host.py:555–600`); `make_worker` is Python, not a CLI command (`hass/host.py:438,589–597`); acceptance entry point tracked, not run. |
| `stock_site.py run --host …` | C:91 | `hass/stock_site.py:286–305`; `deploy/hass/hass-clover-sync.service` `[Service]` post-step. Template, not installed evidence. |
| `systemctl --user` / `daemon-reload` / `enable --now` / `restart` / `disable --now`; `cp`, `stat -c`, `chmod`, `chown`, `cat`, `install -d`, `umask`, `read -rs`, `printf`, `unset`, `ls -l` | C:156,383,393,401–408,424–425 | OS and shell words, not Hass commands; not executed. Templates and stat-only Python checks are indexed above. `cat` is explicitly prohibited there, not a workflow step. |
| Clover v3 merchant base, `GET /v3/merchants/{mId}`, `GET /items`, `GET /items/{id}`, `GET /item_stocks`, `GET /item_stocks/{id}`, `GET /categories` | C:174,184–194,343–344,354–355 | `clover/client.py:23–33,115–156,172–181`. Host and route allow-list only; no account test. |
| `expand=itemStock,categories,tags`, `limit`, `offset`, `filter=modifiedTime>=ms`, `filter=sku=…`, `GET /items?filter=sku=<sku>` / `filter=sku=` | C:193,280,340,371,457–459 | `clover/client.py:29–33,127–146,158–162`; incremental filtering is a client option, not the current periodic pull (`clover/sync.py:74–76`). Standalone `GET /tags` not found in allow-list, distinct from expansion. |
| `POST /items`, `POST /items/{id}`, `POST /category_items`, `PUT /item_stocks/{id}`, `quantity`, `hidden`, `sku`, `price` payload examples | C:195–207,297–298,370–371,460 | `clover/client.py:259–275`, `clover/drafts.py:133–166,169–192,214–239,264–289`. External sandbox semantics (including clearing SKU and decimal count behavior) not verified. |
| `DELETE`, `/orders`, `/payments`, `/customers`, `/employees`, `/refunds`, `/tags` | C:297,311,354–356 | Not found as enabled calls in `clover/client.py:26–27,172–180,259–263`. Public developer reference URLs at C:448–461 are external citations, not Hass routes or local files; not fetched. |

### Chat examples and command words

`X`, `<item>` and `<code>` denote placeholders. “Not found” below means no matching dedicated path found, not that a general conversation could never answer. R2 is the exact-match inventory for **all** Q:26–51 phrases.

| Input or example family | Doc | Status and anchor |
| --- | --- | --- |
| `till report` | C:46–52 | Present as a restricted conversation route, not a `TillDesk.parse` verb (`hass/conversation.py:1662–1679`; `clover/chat.py:196–209`; `clover/reports.py:128–138`). |
| `how many X`, `how many Sunshine olive oil do we have`, `how many <item> do we have`, `is <item> in stock`, `is <item> sold out`, `low stock`; stock cues `do we have`, `left`, `in stock`, `on hand`, `sold out` | C:166,321–322,405,414; P:13–14 | Present with claim guards `clover/chat.py:82–95,149–157,174–186`; answered by `clover/reads.py:91–152` via `clover/chat.py:219–228`. POS `price_of` is not the same as `how many`. |
| `received 12 X`, `received 12 Sunshine olive oil`, `set X to 7`, `set Sunshine olive oil to 7` / `… to 0`, `set X to <number>`, `set Example mug to 12` | C:166,270,304,307,323–324,513 | Present as numeric write patterns with an engine; `clover/chat.py:25–31,158–172,289–305`. Bare “Received 12” at C:307 describes arithmetic, not a full product-bearing input. These full examples also match standalone grammar, which has no production caller found (R2). |
| `X sold out`, `Sunshine olive oil is sold out` | C:166,324 | Present when exact till item resolves in cache (`clover/chat.py:29,164–172`). Distinct from the question form. |
| `new item: …`, `new item: Sunshine olive oil, 12.50, pantry`, `AS-PAN-SUNSHINE-OLIVE-OIL-01`, `Linn's` → `LINNS`, `Sunshine olive oil 1 litre` / suffix `-02` | C:164,166,262–284,325 | Input route and SKU draft present (`clover/chat.py:30,293–298`; `clover/drafts.py:133–166`; `clover/sku.py:39–79`). SKU examples are illustrative given suitable inputs/collisions, not fixed outputs. |
| `change price of X to …`, `change price of Sunshine olive oil to 14.00`, `change the price of <item> to 5`; “set price” / “set stock” | C:166,188,326,405 | Price-change pattern and builder present (`clover/chat.py:27,96–102,158–161,301–305`, `clover/drafts.py:169–192`). “Set price” is a description/refusal cue, not the documented write pattern. “Set stock” is a description; the actual set-count pattern needs `<item> to <amount>`. |
| `give X a SKU`; “give the item a more specific name” | C:284,327 | SKU builder present (`clover/drafts.py:264–275`, `clover/sku.py:35–36,67–79`); dedicated write chat route **not found**. `STOCK_WRITE` recognizes a refusal cue (`clover/chat.py:100,160–161,213–214`), not a dispatch to that builder (`clover/chat.py:25–31,289–305`). |
| `hide X on the till`, `show X on the till`, “show it again”, “remove” | C:199,298,327 | Explicit hide/show forms present (`clover/chat.py:31,130–134,299–302`); the short prose examples alone are not those patterns. Unique exact hidden-name `show` can resolve without a SKU despite broader C:253 wording. |
| `yes <code>`, `no <code>`, `yes a1b2`, `no a1b2`, bare `yes`, `yes?`, reactions/edits | C:165,251,273,291–295,330–332,433,469–472,513–514 | Till-specific coded path uses **eight** hex digits plus journal/sender/chat match (`clover/chat.py:32,63–65,130–137`; `hass/conversation.py:1299–1343`; `clover/apply.py:42–63`). Four-digit mock till replies do not match that route; generic site approval is separate. Bare yes has no Clover code. Do not infer punctuation guarantees from the design: `_clean` strips trailing `?` before the coded matcher; bare `yes?` still has no code. |
| `undo`, `undo <code>`, “revert-last” | C:135–137,165,295,300–304,328,334 | Coded till undo exists (`clover/chat.py:32,69–76,130–137,281–282`); bare `undo` is a general conversation command, not a till-journal selector (`hass/chat/commands.py:15–21`; `hass/conversation.py:2702–2738`). Stock-release marker exists at `hass/stock_site.py:242`; no consumer of `lastStockRelease` found in current undo path (`git grep -n lastStockRelease -- hass`). |
| `stop changes`, `help` | C:292,317,366,472 | General chat commands `hass/chat/commands.py:19–22,79–82`; till help appended when engine exists (`hass/conversation.py:2675–2681`, `clover/chat.py:41–45`). Till pause handling `clover/apply.py:42–63`, `hass/conversation.py:1320–1343`. |
| `link all <code>`, `link X to <SKU>`, `unlink X`, `stock yes stk-…`, `stock no stk-…`, `stock yes <code>` / `stock no <code>`; POS's `link` shorthand | C:100–103,243–247; P:20 | Present with engine/owner/match checks (`clover/chat.py:44–46,146–148,230–272`; `clover/links.py:118–133`). Bare `link` is not the owner form; operator `link suggest` is a different CLI. “link these?” is design wording, not an extra link approval command. |
| `put X on the site` / “put it on the site”, `got more honey in`, “just mark it available” | C:256,325,335–336 | Website-only examples, not dedicated Clover commands (`clover/chat.py:25–31,139–172`). Stock skill has the `got more honey in` trigger (`hass/skills/stock.py:265–276`); a Clover “How many came in?” follow-up on that phrase was not found in this route. General NPP/stock handling not replayed. |
| `retry` after till succeeds but site fails | C:333 | Dedicated till-bundle `retry` verb **not found**. Current reply says to tell Hass again if the website still needs it (`clover/chat.py:38`; `hass/conversation.py:1221–1255`). |
| `till summary`, `price of`, `what sold today` / `this week`, `website vs till` | P:12–16 | View names/helpers present (`clover/pos.py:60–73,84–110`); dedicated chat dispatch **not found**, consistent with P:5. `low stock`, `how many`, `till report` are separate implemented routes above. |

### Output examples, not commands

Fixture values are not repeated here where a template is enough to identify the example. These are source matches, not a snapshot of inventory.

| Example or wording family | Doc | Template evidence or absence |
| --- | --- | --- |
| Stock markdown title, `Last sync`, `Snapshot`, saved-links disclaimer, `Sold out`, `Low stock (at or under …)`, `No count`, hidden row, escaped product name, `None.` | C:60–81 | `clover/reports.py:22–27,69–88`. |
| “Available today”, “Limited”, “Sold out”; `yes` / `limited` / `no` | C:42,85–87,98–105,118,230,303,323–324,330–336 | Stock words, not chat commands: `hass/stock_site.py:16–19,95–96,115–125`; typed ops `clover/drafts.py:117–125,195–211`; mismatch test `clover/reports.py:61–63`. |
| `Token(<redacted>)`; `missing`, `unreadable`, `not-regular`, `owner`, `mode`, `folder`, `size`, `format`; “the till refused the key” / “the till is busy” | C:149–155,204,211–212,392–398 | Token repr and fixed reason words `clover/credential.py:32–66,94–117,146–181`; status mapping and retries `clover/client.py:183–200,242–252`; CLI classes `clover/cli.py:51–57,104–133`. The colloquial error examples are not CLI strings. |
| `site <id>` / `till <item id>` labels; “Did you mean …” | C:242,252–253,321 | Link labels `clover/links.py:19–33`; stock suggestions `clover/reads.py:82–89`, `clover/mapper.py:309–316`. |
| “on the till but not on the site: …”, “X is on the website but not in the till, so I have no count” | C:256–258 | Report buckets for unlinked items present (`clover/reports.py:42–65`); exact dedicated replies **not found** in `clover/chat.py:174–228` / `clover/reads.py:82–117`. An unlinked record is not treated there as proof of absence. |
| New item preview (“Did you mean to add …”, item, SKU, price, category, count, tax, website, reply line); duplicate-name example | C:265–284,325,330 | Analogous builders, not verbatim full historical mock: `clover/drafts.py:31–65,133–166`, `clover/sku.py:27–35` (duplicate); four-digit code mismatch above. |
| “I have already made …”, stale refusal, first-ever count cannot undo, before/after count arrows, change price / percent and mark-sold-out drafts | C:294–307,323–326 | `clover/apply.py:34–40,70–86`; `clover/drafts.py:169–192,214–261,292–329`. Templates exist; absolute/relative counts use separate builders. |
| Count and low-stock chat fixture replies | C:321–322 | `clover/reads.py:54–64,91–104,136–152`; output is formatted from cache, sample values not literals to require. |
| “Before I change that, is the shelf list right for today?”, “How many came in?”, “That was a stock update from the till” | C:137,334–336 | Shelf prompt present (`hass/conversation.py:127–132,1334–1342`); quantity follow-up not found on the described route; stock-update sentence in marker, no undo consumer found (rows above). |
| “as of” time examples, “can't reach the till”, stale 24h refusal, never-read and read-only replies | C:167,350–353,405–406,411–414; P:40–41 | `clover/reads.py:30–64`; `clover/chat.py:24,35,79–80,188–204,211–221`. Do not infer an on-demand refresh from the wording. |
| Host check JSON (`clover`, `result`, `fields`, `writeMode`), CLI check JSON (`merchant`, `items`, `tokenAccepted`, `tokenFileOk`, etc.), sync/status JSON (`asOf`, `counted`, `itemCount`, `skipped`, etc.), mode output | C:194,391–403,501–504 | Field producers `hass/host.py:555–582`, `clover/cli.py:104–180`; filesystem mode check described in docs, not run. Literal merchant identifier and host paths omitted. |
| Till summary and “stock words waiting: not available yet”, price/count example, sold-today ranking (“includes stock edits”, “not exact sales”), website mismatch headings | P:12–19,29–30 | `clover/pos.py:18–22,60–73,84–110`; templates present even without chat routing. `price_of` shows price; standard `how many` routes to `reads.how_many`, which does not. |
| Missing-count example, “Left out …”, “incomplete …”, “an item no longer on the till list”, no-earlier-read sentence | P:31–36 | `clover/cache.py:168–175,276–295`; `clover/pos.py:20,34–57,60–81,118–123` (including `countDropNote`, `countDropLeftOut`, `countDropIncomplete`). |
| POS report output example: `asOf`, `tillReachable`, `stockWordsWaiting`, snapshot state, redacted stdout | P:18,45–52 | Totals and report headings `clover/pos.py:113–129`; writes and pruning `clover/pos.py:150–169`; CLI JSON `clover/cli.py:215–218,253–260`. |
| Q's `None`, `code` and `ask` | Q:4,22,24–51 | `None` is parser refusal; `code` and `ask` are test/document classifications, not commands or returned modes (`hass/tests/test_clover_count_phrases.py:93–113,146–161`; `clover/qty_words.py:85–107`). |

## R2. Count grammar: examples missing or misread, and implemented forms omitted

2026-11-21 offline replay of the 60 checked-in synthetic entries (`hass/tests/test_clover_count_phrases.py:23–91`) against `qty_words.parse`: **11/30** positive exact, **26/30** refusals exact. The existing two focused suites ran **13 tests, OK (expected failures=4)**; the four expected failures are the false accepts below, not fixes. Scratch replay reported zero socket/subprocess attempts. Q:3–20 accurately describes this fixture baseline. The tuples below are `(mode, quantity, unit, query)`; `—` means no unit. Every row is a synthetic parser result, not item lookup, draft creation, or a till count.

| Q line / phrase | Fixture expected | Actual on main / parser anchor |
| --- | --- | --- |
| 26 `12 apricot jams just came in` | add, 12, —, `apricot jams` | add, 12, —, `apricot jams just`; `clover/qty_words.py:69–82,101–102` |
| 27 `30 blue mugs in` | add, 30, —, `blue mugs` | count, 30, —, `blue mugs in`; `clover/qty_words.py:101–106` |
| 28 `the glass pitchers just arrived, 9 of them` | add, 9, —, `glass pitchers` | `None`; `clover/qty_words.py:19–23,31–49,99–107` |
| 29 `blue mug x30` | count, 30, —, `blue mug` | `None`; `clover/qty_words.py:31–49,96–106` |
| 30 `x14 linen bags` | count, 14, —, `linen bags` | `None`; `clover/qty_words.py:19,31–49` |
| 31 `pan scrapers = 11` | count, 11, —, `pan scrapers` | `None`; colon only, `clover/qty_words.py:96–106` |
| 32 `+7 lemon soaps` | add, 7, —, `lemon soaps` | `None`; `clover/qty_words.py:19,31–49` |
| 33 `we have 4lb of dried cherries` | count, 4, lb, `dried cherries` | `None`; `clover/qty_words.py:31–49,57–60` |
| 34 `just got 6 lb of split peas` | add, 6, lb, `split peas` | `None`; `clover/qty_words.py:21,99–106` |
| 35 `we have 15 each of the wax wraps` | count, 15, —, `wax wraps` | count, 15, —, `each of the wax wraps`; `clover/qty_words.py:57–60,69–82` |
| 36 `we got a dozen and a half cake boxes` | add, 18, —, `cake boxes` | add, 12, —, `and a half cake boxes`; `clover/qty_words.py:37–38,51–55,69–82` |
| 37 `a hundred and six paper straws` | count, 106, —, `paper straws` | `None`; `clover/qty_words.py:31–49`; `hass/skills/item_intake.py:394–413` |
| 38 `put 30 mugs on the shelf` | count, 30, —, `mugs` | `None`; Q labels this **ask**; parser has no clarification return value (`clover/qty_words.py:12–16,85–107`). |
| 39 `only 4 cedar soap dishes left` | count, 4, —, `cedar soap dishes` | `None`; `clover/qty_words.py:22–23,31–49,103–107` |
| 40 `we have 18 cork trivets in stock` | count, 18, —, `cork trivets` | count, 18, —, `cork trivets in stock`; `clover/qty_words.py:22–23,75–82,103–106` |
| 41 `on the shelf there's 7 butter crocks` | count, 7, —, `butter crocks` | `None`; `clover/qty_words.py:22–23,31–49,103–107` |
| 42 `recevied 8 maple spreaders` | add, 8, —, `maple spreaders` | `None`; `clover/qty_words.py:21,99–106` |
| 43 `there re 5 mixing bowls` | count, 5, —, `mixing bowls` | `None`; `clover/qty_words.py:22,103–107` |
| 44 `5 bown sugar scoops on the slehf` | count, 5, —, `bown sugar scoops` | count, 5, —, `bown sugar scoops on the slehf`; `clover/qty_words.py:23,75–82,103–106` |
| 48 `12 bucks for the tea tin` | `None` | count, 12, —, `bucks for the tea tin`; `clover/qty_words.py:25–28,75–82,103–106` |
| 49 `6 cloth bags and a fruit basket` | `None` | count, 6, —, `cloth bags and a fruit basket`; same guard `clover/qty_words.py:75–82,103–106` |
| 50 `9 miles for the ridge hike` | `None` | count, 9, —, `miles for the ridge hike`; `clover/qty_words.py:25–28,75–82,103–106` |
| 51 `set the website photo of the wooden ladle to 3` | `None` | set, 3, —, `website photo of the wooden ladle`; `clover/qty_words.py:20,72–82,93–95` |

Q is a gap report, not an exhaustive syntax guide. These positive forms are absent from its **inline examples** (Q:24–51); several already have examples in the linked fixture, so they are not missing from the whole evidence trail.

| Q's contrasting wording | Accepted form(s), quoted from tests | Parser / test proof |
| --- | --- | --- |
| `pan scrapers = 11`, `blue mug x30` | `ceramic strainers: 5`, `cork mats: 16!`, `The stone bowls: ninety-nine`: label-colon-amount; no extra product text after the amount. | `clover/qty_words.py:72–75,90,96–98`; held-out lines 27,32; `hass/tests/test_clover_qty_words.py:94–109` |
| `30 blue mugs in`, `12 apricot jams just came in`, `recevied 8 maple spreaders`, `just got 6 lb of split peas`, `+7 lemon soaps` | `received 30 blue mugs`, `we received two dozen of the eggs`, `we got 8 more of the enamel trays`, `30 more blue mugs came in`; optional `we`, `more`, `of`, article where the frame permits. | `clover/qty_words.py:21,69–75,99–102`; held-out line 26; seed lines 100–105 |
| `there re 5 mixing bowls`, `on the shelf there's 7 butter crocks`, `only 4 cedar soap dishes left`, `5 bown sugar scoops on the slehf`, `we have 18 cork trivets in stock` | `there are 0 blue mugs.`, `there is one baker’s basket`, `we have thirty blue mugs now`, `30 blue mugs on the shelf`, `11 jam spoons on the shelf now`, `30 of the blue mugs`; bare counts, supported prefixes/suffixes, case/space/apostrophe normalization. | `clover/qty_words.py:22–23,69–82,88–90,103–106`; held-out lines 46,49; seed lines 94–114 |
| `we have 15 each of the wax wraps`, `a hundred and six paper straws`, `we got a dozen and a half cake boxes` | `103 eggs`, `zero eggs`, `ninety nine eggs`, `ninety-nine eggs`, `a dozen eggs`, `2 dozen eggs`, `two dozen eggs`, `three dozen cloth filters came in`; digit integers, bounded words, integer dozen multiplier rather than `each` or mixed dozens. | `clover/qty_words.py:19,31–60`; `hass/skills/item_intake.py:394–413`; held-out lines 39,41,43; seed lines 41–57 |
| `we have 4lb of dried cherries` | `got 1.75 pounds of hazelnuts`, `ground rye: 2.25 lbs`, `3.125 lb eggs`: spaced `lb` / `lbs` / `pounds` (normalized to `lb`), up to three decimal places for weights; no fractional unitless counts. | `clover/qty_words.py:19,31–60`; held-out lines 34–36; seed lines 49–57 |
| `set the website photo of the wooden ladle to 3` (should refuse) | `set blue mugs to 7`, `set the count of the oats to 3.25 lb`: actual explicit `set` frame, including optional “the count of”, also supports number words. | `clover/qty_words.py:20,72–82,93–95`; seed lines 84–87,103,113 |

Reproduce the assertion-based results from the repo root (no service config):

```text
python3 -B -m unittest hass.tests.test_clover_qty_words hass.tests.test_clover_count_phrases
```

For tuple-level reproduction, iterate the checked-in `PHRASES` table (test lines 23–91), call `parse(text)` and compare against its expected `CountIntent` or `None`; report only cases where those differ. Tests pin the same aggregate and known examples at `hass/tests/test_clover_count_phrases.py:146–206`. The search `git grep -n qty_words -- hass` finds imports in those two tests, not a production route. Chat instead uses `TILL_WRITES` (`clover/chat.py:25–31,158–172`) via `hass/conversation.py:1316–1343`. Thus C:513–516 and Q:4 should be read at different layers: working fixed numeric chat examples do not establish everyday parser integration, and Q's false accepts do not establish live write reachability.

## R3. Public callables not named in the three docs

“Public” means defined here and not underscore-prefixed; imports, private helpers and dunders excluded. For completeness this includes methods. Compare exact API identifiers, not words such as “report” or “undo” used as chat/CLI commands. All listed callables lack a qualified API reference in C/Q/P; the last column distinguishes functional prose from names that are also absent as literals.

| Definition | Source | What the docs actually mention |
| --- | --- | --- |
| `chat.py` module-level functions | `clover/chat.py:108–119` | None public; `_clean` and `_query` are private. |
| `BundleEngine.offer` | `clover/chat.py:55–65` | No method name; draft offering described C:289–293,468–473. |
| `BundleEngine.undo` | `clover/chat.py:69–76` | `undo` command and `build_undo` named C:299–304,328; not this method. |
| `TillDesk.first` | `clover/chat.py:130–137` | No name; C:440–441 describes the earlier chat layer, not this pre-command check (`hass/conversation.py:1316–1318`). |
| `TillDesk.parse` | `clover/chat.py:139–162` | No method name; exact patterns and parser precedence discussed C:309,317,366,440–441. |
| `TillDesk.report` | `clover/chat.py:196–209` | `till report` command C:46–52, not the method. |
| `TillDesk.answer` | `clover/chat.py:211–228` | No method name; replies discussed C:319–328,405–414. |
| `TillDesk.drop` | `clover/chat.py:317–318` | No method name; `no` to drop a draft in C:273,330. |
| `TillDesk.bundle` | `clover/chat.py:320–325` | No method name; same-draft website op described C:331–334. |
| `TillDesk.site_moved` | `clover/chat.py:327–336` | No method name; broader newer-site-word safety appears C:110,301–303. Caller's two checks `hass/conversation.py:1224–1240`. |
| `TillDesk.approve` | `clover/chat.py:338–351` | Owner yes described C:291–293,330–332; the explicitly named `stock_site.approve` at C:102,247 is a different function. |
| `reports.low_stock` | `clover/reports.py:22–28` | No function name; stock sections C:32–35,63–80, P:14. |
| `reports.till_vs_site` | `clover/reports.py:31–66` | No function name; mismatch described C:37–44, P:16. |
| `reports.render_md` | `clover/reports.py:75–88` | No function name; sample render C:60–81. |
| `reports.read_inputs` | `clover/reports.py:108–125` | No function name; input paths and restrictions C:37–44, P:45–46. |
| `reports.headline` | `clover/reports.py:128–138` | No function name; totals-only behavior C:46–52. |
| `reports.write_report` | `clover/reports.py:141–183` | No function name; private atomic output and pruning C:22–30. |

Reproduce the candidate list with `git grep -nE '^(class |(    )?def )' -- hass/clover/chat.py hass/clover/reports.py` and the name comparison with `git grep -nwE 'BundleEngine|TillDesk|first|parse|answer|offer|undo|report|drop|bundle|site_moved|approve|low_stock|till_vs_site|render_md|read_inputs|headline|write_report' -- docs/hass/CLOVER.md docs/hass/CLOVER-COUNT-PHRASES.md docs/hass/POS.md` (inspect context for ordinary words).

## R4. Ranked gaps and one bounded option

1. **User-facing chat claims vs. reachability.** `give X a SKU` has a builder and a refusal cue but no write dispatch (C:284,327; `clover/chat.py:25–31,100–102,158–161,289–305`). Bare `undo` is not a till-journal selector and four-digit sample till codes do not match the eight-digit route (C:273,328; `clover/chat.py:32,63,130–137`; `hass/conversation.py:2702–2715`). C's older read-only descriptions coexist with later optional engine construction (C:3–5,215–217,439–442,495–516; `hass/host.py:475–501`). None proves what is installed.
2. **Standalone grammar vs. chat and lookup.** Q's fixture baseline is accurate; six wrong positive intents and four false accepts are more consequential than outright refusals if the grammar were ever wired. No production caller found; the code does not turn these into till actions (R2). C:335–336 also describes a follow-up not found in that path.
3. **File reports vs. chat views.** C lists stock and mismatch outputs but omits POS under `report --all`; P:33 and `clover/cli.py:197–219` include it. P:5 correctly says dedicated POS chat commands are later; avoid reading its table labels as runnable commands. The stock-totals file existing does not mean it feeds POS (`hass/stock_site.py:100–106`; `clover/pos.py:119`).
4. **Remaining design or interface detail.** The planning text about retry and on-demand reads is not the same as the current paths (C:333,340–349; `clover/chat.py:38,188–194`; `clover/sync.py:74–76`). Missing callable names are mainly a maintainer navigation issue, not evidence of missing behavior (R3).

**One possible follow-up, not implemented (estimate: 45–75 min):** after separate authorization, add a short source-status note in **`docs/hass/CLOVER.md` only** that separates present fixed chat routes from library-only/design examples and lists all `report --all` outputs. Keep existing owner decisions, operating limits, and history untouched. Offline acceptance: run the two parser suites above unchanged and use `git grep -nE 'TILL_WRITES|CODED|build_set_sku|args\.all|pos\.write_files' -- hass/clover/chat.py hass/clover/drafts.py hass/clover/cli.py` to verify the note distinguishes a builder from a route and includes the POS output. No tests or source changes in that option; no live command or deployment check in this audit.
