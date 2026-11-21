# Hass capability inventory versus code

| Check | Result | Evidence |
|---|---|---|
| R1. JSON → code | 42 unique IDs: 41 `active`, all with code; one `retired`, with refusal/backlog code, not a page-creation action. | `docs/hass/capabilities.json:4–45`; R1 trace below |
| R2. Code → JSON | No missing registered skills. Fixed chat commands, the separate new-product flow, and some catalog/site operations are outside the manifest. The nine slot resolvers are not capabilities. | `hass/capabilities.py:29–40`; `hass/chat/commands.py:49–83`; `hass/conversation.py:549–558`; `hass/skills/kinds.py:207–208` |
| R3. Docs → JSON | `CAPABILITIES.md` agrees on all IDs and rendered statuses. `FEATURES.md` shares no IDs: 25 H milestones and 12 F features, with some overlapping topics but different acceptance boundaries. | `docs/hass/CAPABILITIES.md:14–78`; `docs/hass/FEATURES.md:15–72`; replay below |
| R4. First gap to address | Clarify what the generated owner page covers; do not add new skills or widen permissions. | `docs/hass/CAPABILITIES.md:1–12`; `docs/hass/SKILLS.md:76–96`; R4 below |

**Source and limits.** Offline inspection on 2026-11-21 at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, which matched the freshly cloned `origin/main`. The cited sources did not move from the requested baseline. The public tree did not contain `reports/hass-npp/G-QUESTIONS.md` at that revision (the tree query below printed nothing); this report uses the boundaries in the task brief and does not infer any further decisions. This is source evidence for the current catalog (`AGENTS.md:3–16`), not an installed-feature check. No live Hass, host settings, state, credentials, participant data, site, till, bridge, or model was read or exercised. No policy, hold, or owner decision is changed.

## R1. Every JSON ID and its implementation

The JSON field used as the ID is `name`. Pack counts: site 30, front 5 (including the retired entry), reports 5, core 2, till 0. `load_skills()` discovers exported `SKILLS` and rejects duplicate names; the generator lints the registry and serializes selected metadata, not implementation, command grammar or slot shapes (`hass/skills/__init__.py:19–31`, `hass/capabilities.py:29–40`). The table names the planner that builds the action, the function that supplies an answer, or the refusal path. It does not claim each action was run or is usable in every chat mode (`docs/hass/CAPABILITIES.md:5–10`).

| JSON ID | `status` | JSON source | Implementing code |
|---|---|---|---|
| `answer.site` | `active` | `docs/hass/capabilities.json:4` | `hass/skills/reports.py:298` — site answer |
| `backlog.log` | `active` | `docs/hass/capabilities.json:5` | `hass/skills/dispatch.py:1295–1297`, `hass/skills/dispatch.py:1310–1322` — record the unsupported request without a site edit |
| `front.banner` | `active` | `docs/hass/capabilities.json:6` | `hass/skills/front.py:72` — banner plan |
| `front.faq` | `active` | `docs/hass/capabilities.json:7` | `hass/skills/front.py:184`, `hass/ops/front.py:119–126` — fixed Questions entry changes |
| `front.page` | `active` | `docs/hass/capabilities.json:8` | `hass/skills/front.py:169` — fixed page plan |
| `front.sections` | `active` | `docs/hass/capabilities.json:9` | `hass/skills/front.py:43` — home sections plan |
| `hike.add` | `active` | `docs/hass/capabilities.json:10` | `hass/skills/hikes.py:820` — new hike plan |
| `hike.cancel` | `active` | `docs/hass/capabilities.json:11` | `hass/skills/hikes.py:871` — cancel plan |
| `hike.edit` | `active` | `docs/hass/capabilities.json:12` | `hass/skills/hikes.py:841` — edit plan |
| `hike.recap` | `active` | `docs/hass/capabilities.json:13` | `hass/skills/hikes.py:887` — recap plan |
| `hike.repeat` | `active` | `docs/hass/capabilities.json:14` | `hass/skills/hikes.py:881` — repeat plan |
| `hike.reschedule` | `active` | `docs/hass/capabilities.json:15` | `hass/skills/hikes.py:858` — reschedule plan |
| `item.add` | `active` | `docs/hass/capabilities.json:16` | `hass/skills/item_add.py:929` — registered add plan; separate photo intake in R2 |
| `item.edit` | `active` | `docs/hass/capabilities.json:17` | `hass/skills/items.py:415` — edit plan |
| `item.hide` | `active` | `docs/hass/capabilities.json:18` | `hass/skills/items.py:246` — hide plan |
| `item.picture` | `active` | `docs/hass/capabilities.json:19` | `hass/skills/item_picture.py:373` — picture plan |
| `item.restore` | `active` | `docs/hass/capabilities.json:20` | `hass/skills/items.py:299` — restore plan, not a decision to restore anything |
| `maker.add` | `active` | `docs/hass/capabilities.json:21` | `hass/skills/makers.py:347` — add plan |
| `maker.edit` | `active` | `docs/hass/capabilities.json:22` | `hass/skills/makers.py:421` — edit plan |
| `maker.hide` | `active` | `docs/hass/capabilities.json:23` | `hass/skills/makers.py:467` — hide plan |
| `maker.restore` | `active` | `docs/hass/capabilities.json:24` | `hass/skills/makers.py:480` — restore plan |
| `page.about` | `active` | `docs/hass/capabilities.json:25` | `hass/skills/pages.py:228` — home story plan |
| `page.faq` | `retired` | `docs/hass/capabilities.json:26` | `hass/skills/backlog.py:171–189`, `hass/skills/dispatch.py:708–711` — retired request refusal and backlog; **none found** for arbitrary page creation under this ID |
| `page.home` | `active` | `docs/hass/capabilities.json:27` | `hass/skills/pages.py:165` — headline/intro plan |
| `page.photo` | `active` | `docs/hass/capabilities.json:28` | `hass/skills/pages.py:305` — home photo plan |
| `report.shelf` | `active` | `docs/hass/capabilities.json:29` | `hass/skills/reports.py:122` — shelf report reply; fixed chat counterpart at `hass/chat/reports_pack.py:56` |
| `shop.contact` | `active` | `docs/hass/capabilities.json:30` | `hass/skills/shop.py:524` — site contact plan |
| `shop.hours` | `active` | `docs/hass/capabilities.json:31` | `hass/skills/shop.py:367` — opening hours plan |
| `shop.notice` | `active` | `docs/hass/capabilities.json:32` | `hass/skills/shop.py:448` — notice plan |
| `social.hike` | `active` | `docs/hass/capabilities.json:33` | `hass/skills/social.py:246` — hike caption |
| `social.item` | `active` | `docs/hass/capabilities.json:34` | `hass/skills/social.py:232` — product caption |
| `social.maker` | `active` | `docs/hass/capabilities.json:35` | `hass/skills/social.py:258` — maker caption |
| `social.recap` | `active` | `docs/hass/capabilities.json:36` | `hass/skills/social.py:277` — recap caption |
| `specials.add` | `active` | `docs/hass/capabilities.json:37` | `hass/skills/specials.py:525` — add plan |
| `specials.clear_expired` | `active` | `docs/hass/capabilities.json:38` | `hass/skills/specials.py:577` — clear expired plan |
| `specials.edit` | `active` | `docs/hass/capabilities.json:39` | `hass/skills/specials.py:556` — edit plan |
| `specials.remove` | `active` | `docs/hass/capabilities.json:40` | `hass/skills/specials.py:570` — remove plan |
| `specials.show` | `active` | `docs/hass/capabilities.json:41` | `hass/skills/specials.py:587` — specials reply, not the draft `show` command |
| `stock.checked` | `active` | `docs/hass/capabilities.json:42` | `hass/skills/stock.py:155` — shelf check plan |
| `stock.clear` | `active` | `docs/hass/capabilities.json:43` | `hass/skills/stock.py:237` — clear stock word plan |
| `stock.restock` | `active` | `docs/hass/capabilities.json:44` | `hass/skills/restock.py:104` — restock day plan |
| `stock.set` | `active` | `docs/hass/capabilities.json:45` | `hass/skills/stock.py:130` — stock word and check-day plan |

## R2. Code and kinds not listed in JSON

**No registry-only skill IDs.** `--check` passed, and the direct registry/JSON set comparison found no difference. The omission of fixed commands and the separate till parser as *skills* is explicit in `docs/hass/SKILLS.md:93–96`. General chat help combines a fixed command index with the generated skill section; help for one command uses the fixed entries (`hass/chat/commands.py:49–84`, `hass/chat/commands.py:105–119`, `hass/conversation.py:2674–2681`). The table accounts for all 27 fixed help entries by function, including overlaps. Aliases and parsing variations do not get separate capability IDs.

| Fixed help entries / other path | What is absent or already represented |
|---|---|
| `yes`, `no` | No stand-alone approval/rejection skill. Fixed parsing includes bulk words; the conversation handles the decisions, including bulk handling. The approval metadata on a listed skill is not itself a command listing (`hass/chat/commands.py:127–138`, `hass/conversation.py:1307–1314`, `hass/conversation.py:1388–1447`, `hass/conversation.py:1482–1498`). |
| `undo`, `show`, `again` | No separate draft undo, draft readback, or re-draft skill. `specials.show` is not draft readback (`hass/chat/commands.py:53–55`, `hass/conversation.py:2702–2739`, `hass/chat/core_pack.py:179`, `hass/chat/core_pack.py:217`; JSON line 41). |
| `find`, `listing`, `shelf` | No separate named search, catalog/store listing readback, or shelf-by-category skill. `answer.site` overlaps on site answers, but the command handlers are separate; `report.shelf` is the morning report, not the category lookup (`hass/chat/site_pack.py:160`, `hass/chat/site_pack.py:211`, `hass/chat/site_pack.py:242`, `hass/chat/site_pack.py:331`; JSON lines 4 and 29). |
| `hidden`, `held` | No separate hidden/held list commands in JSON. They are reads, not the listed hide/restore changes (`hass/chat/site_pack.py:364`, `hass/chat/site_pack.py:384`; JSON lines 18 and 20). |
| `report` | Overlap: morning shelf report is already represented by `report.shelf`; no `report` command row as such (`hass/chat/commands.py:62`, `hass/chat/reports_pack.py:56`; JSON line 29). |
| `post` | Product, maker and hike branches overlap `social.item`, `social.maker` and `social.hike`; recap is a registered skill. The home-notice caption branch has no equivalent JSON entry (`hass/chat/reports_pack.py:160–176`, `hass/chat/reports_pack.py:206–244`, `hass/social_draft.py:190`; JSON lines 32–36). `shop.notice` edits the notice, not the caption. |
| `look`, `photos to take` | No site preview/picture lookup or missing-photo list entries in JSON (`hass/chat/commands.py:66–67`, `hass/chat/site_pack.py:105`, `hass/chat/site_pack.py:306`). |
| `margin`, `cost`, `costs` | No private margin estimate, cost note, or saved cost readback entry. These chat handlers do not establish that the catalog shows prices (`hass/chat/reports_pack.py:88`, `hass/chat/reports_pack.py:284`, `hass/chat/core_pack.py:297–298`, `hass/chat/core_pack.py:412`; `AGENTS.md:8`). |
| `remember`, `forget`, `notes`, `alias`, `backlog` | Note and alias functions, backlog listing and single-row removal are not separate JSON entries. `backlog.log` covers recording an unsupported request, not this command set (`hass/chat/commands.py:261–285`, `hass/chat/core_pack.py:249–304`, `hass/chat/core_pack.py:341`; JSON line 5). |
| `history`, `status`, `stop changes`, `resume changes`, `help` | No separate history/search, status, pause/resume, or help skills (`hass/chat/core_pack.py:70`, `hass/chat/core_pack.py:95`, `hass/chat/core_pack.py:483–503`, `hass/conversation.py:2674–2682`, `hass/conversation.py:2696–2701`). |
| New-product photo flow (no fixed verb) | `help listing` documents a separate path. `item.add` represents the product-add outcome, not the optional listing-job intake, card revision and version-bound approval path. The branch and the registered fallback are visible in `hass/chat/commands.py:42–48`, `hass/conversation.py:549–558`, `hass/conversation.py:1503–1557`, `hass/conversation.py:1605`, `hass/conversation.py:2367–2370`, `hass/npp/job.py:475–516`; JSON line 16. No claim about how the host is configured. |
| Undated route ideas | `route.add`, `route.edit`, `route.hide`, `route.restore` exist as typed site operations, not registry skill IDs. `hike.add` can include adding a confirmed trail, but is not a listing of stand-alone route actions (`hass/ops/routes.py:169–175`, `hass/skills/hikes.py:807–820`, `hass/conversation.py:2210–2214`; JSON line 10). This compares op names without asserting chat reachability or live permission. |
| Separate till parser (inventory boundary only) | No till skills in JSON. Chat has a separate conditional till path and appends till help in a specific configuration. That does not conflict with “Nothing registered yet.” No till operation was audited or run (`hass/conversation.py:1316–1343`, `hass/conversation.py:2678–2681`, `docs/hass/CAPABILITIES.md:59–61`). |

**Kinds are input helpers, not missing features.** `hass/skills/kinds.py:207–208` exposes all nine: `product_ref`, `maker_ref`, `hike_ref`, `route_ref`, `shelf`, `availability`, `day`, `clock`, `attachment`. None gets a JSON row or a slot field. The dispatcher calls them to resolve inputs before planning (`hass/skills/dispatch.py:257–278`, `hass/skills/dispatch.py:302–318`); `route_ref`, for example, resolves a trail for `hike.add`, not a stand-alone route command (`hass/skills/kinds.py:129–137`, `hass/skills/hikes.py:928`). `stock_items` is a separately declared shape-only kind; neither it nor the inherited operation kinds are owner capabilities (`hass/skills/model.py:15–23`).

## R3. Agreement between the documents and JSON

**`CAPABILITIES.md`: yes.** All 42 IDs appear once. The same generator renders `active` as “registered” and `retired` as “retired”; it carries the label, summary, approval wording, target list and declared log fields but does not print every JSON field (`hass/capabilities.py:43–47`, `hass/capabilities.py:75–97`). `--check` compared both tracked outputs byte-for-byte against the generator. There are no ID/status differences to quote. There *is* a shared wording tension: “The site has no FAQ page and a new page is a design change: say so and write it down” (`docs/hass/CAPABILITIES.md:57`; JSON line 26) sits beside “Add or edit a question and answer on Questions, or remove a question; the first entry shows the page” (`docs/hass/CAPABILITIES.md:54`; JSON line 7). Code supports a fixed Questions template and keeps a refusal for the retired request (`hass/ops/front.py:119–142`, `hass/skills/dispatch.py:708–711`). This is not evidence about whether Questions is currently visible.

**`FEATURES.md`: no common ID or status vocabulary.** It says “States are as of the 2026-11-02 feature audits” and “Numbers define development order, not completion” (`docs/hass/FEATURES.md:3`). Its row IDs are H01–H25 and F01–F12; none is a JSON `name` (replay below). `Done`, `Partly` and `Needs G` are milestone judgments, not equivalents of `active` or `retired`. These are the closest overlaps and the material differences:

| Backlog wording | Related JSON rows and difference |
|---|---|
| H03 “Add, edit, hide and restore a product or maker” (`docs/hass/FEATURES.md:21`) | The item and maker packs split these into actions (JSON lines 16–24). `item.picture` is additionally split out. The backlog has one acceptance statement, not individual skill statuses. |
| H04 “Draft and update real hikes”; H14 “Hike management and guest totals” (`docs/hass/FEATURES.md:22`, `docs/hass/FEATURES.md:37`) | JSON lines 10–15 split the hike changes; `answer.site` says “confirmed sign-ups only” (JSON line 4). Guest totals and route safeguards in the backlog are not stand-alone skill IDs. |
| H05 “Approve, revise or cancel”; H06 “Preview, result and undo”; H15 “Owner memory and useful clarification”; H17 “Clear status and control” (`docs/hass/FEATURES.md:23–24`, `docs/hass/FEATURES.md:38–40`) | These cut across skills and fixed chat handlers (R2). Per-skill gates and preview labels are not a listing for approval, undo, notes, status or pause. |
| H10 “Partly: label reader never run on a real vision model or photo”; H12 “One conversation for text plus attachments” (`docs/hass/FEATURES.md:33`, `docs/hass/FEATURES.md:35`) | `item.add` and `item.picture` are `active` (JSON lines 16 and 19). Registry status does not assert completed trial evidence or describe the separate listing-job route. |
| H13 “Hours, home-page copy and image changes”; H24 “no path from an owner request to a checked code change” (`docs/hass/FEATURES.md:36`, `docs/hass/FEATURES.md:52`) | `shop.hours` and `page.*` address particular fields (JSON lines 25–28 and 31); `front.*` covers fixed surfaces (JSON lines 6–9). Those are not arbitrary designs or code changes. |
| F03 “Record purchase costs; suggest sale prices and margins”; F04 “Low-stock warnings and a concise morning report” (`docs/hass/FEATURES.md:63–64`) | Private cost/margin are fixed chat paths (R2), not JSON skills. `report.shelf` is based on “the last shelf check” and says “Not stock counts; sends nothing” (JSON line 29); `stock.*` is site words/dates (JSON lines 42–45), not F04's shared sales and inventory prerequisites. |
| F07 “Prepare branded post, caption and schedule”; F08 “Community newsletter and hiking notifications” (`docs/hass/FEATURES.md:67–68`) | The caption skills say “Nothing is posted” or “Nothing is posted or sent” (JSON lines 33–36). `hike.cancel` says “Nobody is told” and `hike.reschedule` says “Guests who signed up are not told” (JSON lines 11 and 15). These are not delivery or scheduling integrations. |

## R4. Ranked gaps and one possible follow-up

1. **Scope is easy to mistake for completeness.** “What Hass can do” is a registry view, but the owner-facing help combines it with commands and the separate product-listing guide. That makes the omission especially misleading for new product intake and previews, even though the registry is complete (`docs/hass/CAPABILITIES.md:1–6`, `docs/hass/SKILLS.md:93–96`, `hass/conversation.py:2674–2681`, `docs/hass/NPP-OWNER-GUIDE.md:1–25`).
2. **Two Questions entries describe different paths without saying so together.** The retired refusal reads as a blanket claim even though `front.faq` has a fixed Questions template. This is a wording problem, not evidence that an action should be enabled or a page restored (R3; `docs/hass/CAPABILITIES.md:54–57`).
3. **The dated backlog cannot serve as a second skill inventory.** Its milestone and future-integration language can be mistaken for current availability or absence. Keep the state vocabularies separate (R3; `docs/hass/FEATURES.md:3`, `docs/hass/FEATURES.md:55–57`).

**One proposed unit, not implemented — estimate 60–90 minutes:** Clarify the inventory boundary in the generated owner-page introduction: registry skills only; fixed chat commands and the separate listing guide are documented separately; registered is not installed or enabled. Own `hass/capabilities.py` (owner-page introduction only), `docs/hass/CAPABILITIES.md` (regenerate), and `hass/tests/test_capabilities.py` (focused test). Offline acceptance: `python3 -B -m unittest hass.tests.test_capabilities` should assert the scope notice and that the existing ID/status set still matches the registry; `python3 -B hass/capabilities.py --check` should pass with JSON byte-identical to the unit's base. No command changes, new permissions, edits to the guide or backlog, or decisions about owner policy.

### Offline replay

Run from the repository root. On 2026-11-21, the checker exited 0 and printed `Capability manifest and owner page match the registry.` The census found 42 distinct JSON names, 42 matching Markdown rows, empty registry-only/JSON-only sets, and 37 feature rows with no overlapping ID. The commands below reproduce the counts or expose the source used for the classifications; the Markdown count is for skill rows, not table headings.

```sh
git rev-parse origin/main
git ls-tree -r --name-only origin/main -- reports/hass-npp/G-QUESTIONS.md
python3 -B hass/capabilities.py --check
jq '.skills | {rows: length, unique: (map(.name) | unique | length), statuses: (group_by(.status) | map({status: .[0].status, count: length})), packs: (group_by(.pack) | map({pack: .[0].pack, count: length}))}' docs/hass/capabilities.json
jq -r '.skills[] | [.name,.status] | @tsv' docs/hass/capabilities.json
git grep -n -E '^\| .*\([a-z]+\.[a-z_]+\) \|' -- docs/hass/CAPABILITIES.md
git grep -n -E '^\| [HF][0-9]{2} \|' -- docs/hass/FEATURES.md
git grep -n -E 'plan=|^SKILLS|^REPLIES|^RESOLVERS|^HELP_ENTRIES' -- hass/skills hass/chat/commands.py
git grep -n -E 'def _command|def _npp_|def _read_only|def _backlog' -- hass/conversation.py hass/skills/dispatch.py
```

The generator check and census were executed; implementation and command traces were read, not exercised. Neither is a substitute for live verification or required CI.
