# Hass skill reachability — AVO1203-01

| Question | Result at `37feae1dc5efa6968f90d17a1eda6daed29afd4a` |
|---|---|
| What loads? | 29 Python modules including the package initializer; 16 export 42 distinct skill IDs. 41 are active; `page.faq` is retired (R1–R2, offline probe, 2026-11-21). |
| What can route? | Each active ID ranked first for at least one of its own checked-in triggers in a router-only probe. That is not an end-to-end route: the stock host builds a prompt without the skill list, and normal skill dispatch requires both an enabled mode and a skill-shaped reply (R1). |
| What's dead or doubled? | One retired ID has leftover branches. Thirteen modules export no skill but have helper or tooling roles. No duplicate skill ID loaded; `page.faq` and `front.faq` are not aliases (R2). |
| Does the guide match? | It describes the registry, not the active catalog. It names two IDs and describes the retired FAQ path as current; the generated catalog is the inventory (R3). |

`origin/main` matched the requested baseline on 2026-11-21. Scope: tracked source and offline input fixtures only (`AGENTS.md:3–16`). The cited `reports/hass-npp/G-QUESTIONS.md` is not tracked at this pin (`git ls-tree -r --name-only origin/main -- reports/hass-npp` returned nothing); no owner answer is inferred. No model call, host configuration, service, real catalog content/state, approval or write path was exercised.

## R1. Every module and its routes

“Kind” below means the dotted **skill ID** (`Skill.name`), not a slot type, command verb or typed op. `hass/skills/__init__.py:19–31` discovers/imports every sibling and registers only the entries exported as `SKILLS`, once per name; the registry's `get` and `active` filter retired entries (`hass/skills/model.py:331–341`). Thus all sibling rows have that importer even when the direct-import column says “none.”

In the table, bare Python filenames on either side mean `hass/skills/<file>`. `C` = `hass/conversation.py`; `D` = `hass/skills/dispatch.py`. The import column lists direct named import sites in tracked `hass/` outside tests and `scripts/hass/` (including lazy imports); test import counts and examples are in the replay probe. “Guide” is a literal module/ID census of `docs/hass/SKILLS.md`, not the separate per-skill pages.

| Module | IDs and registration (definition line → export; reply hook if separate) | Direct named importers outside tests | Guide |
|---|---|---|---|
| `__init__.py` | No ID; registers all exports at :19–31 | Package callers include `C:25,545`, `hass/capabilities.py:16`, `hass/sandbox_editor.py:33`; all package-level imports in the probe | :15 |
| `acceptance_run.py` | No ID; acceptance runner :1116–1165 | None | No |
| `answer_site.py` | `answer.site` (`reports.py:353` → `answer_site.py:4`); reply `reports.py:379` | None | No |
| `backlog.py` | `backlog.log` :149 → :191; `page.faq` defined at :173 but **not** exported here. Special dispatch `D:1291–1314` | `hass/chat/core_pack.py:252,266`; `C:827,2013`; `D:678,709,1254,1293,1312`; `faq.py:2`; `router.py:26` | :17,115–127; both IDs named |
| `dispatch.py` | No ID; validates and executes selected skills :735–765,861–939,1101–1148,1291–1308 | `hass/chat/core_pack.py:16`; `C:25`; `hikes.py:1114`; `reports.py:374`; `social.py:367`; `specials.py:743` | No |
| `faq.py` | `page.faq` (`backlog.py:173,189` → `faq.py:4`), **retired** | None | Module no; ID named at :17,117 |
| `front.py` | `front.sections` :100, `front.banner` :115, `front.page` :207, `front.faq` :220 → :231 | None | No |
| `hikes.py` | `hike.add` :909, `hike.edit` :941, `hike.reschedule` :967, `hike.cancel` :992, `hike.repeat` :1017, `hike.recap` :1042 → :1066; rule/default hooks :1111–1128 | None | No |
| `intake_simple.py` | No separate ID; `item.add` path through `D:521–566,616–675,861–863` | `C:25,903`; `hass/npp/edits.py:23`; `hass/npp/reply.py:16`; `D:523,618` | No |
| `item_add.py` | `item.add` :1083 → :1115; intake and photo entry in `D:445–451,501–519,1325–1359` | `D:556`; `item_picture.py:33` | No |
| `item_intake.py` | No separate ID; `item.add` support (`item_add.py:57`; `D:501–519,776–807,853–858`) | `hass/clover/qty_words.py:8`; `C:25`; `hass/npp/private_numbers.py:8`; `D:41`; `intake_simple.py:10`; `item_add.py:57` | No |
| `item_picture.py` | `item.picture` :414 → :452 | `photo_trial.py:183` | No |
| `items.py` | `item.hide` :484, `item.restore` :511, `item.edit` :537 → :576 | None | No |
| `kinds.py` | No skill ID. Slot resolver names: `product_ref`, `maker_ref`, `hike_ref`, `route_ref`, `shelf`, `availability`, `day`, `clock`, `attachment` :207–208; `D:275–276,302–316` uses the map | `C:2159`; `D:41`; `openreq.py:390`; `reports.py:29`; `router.py:27`; `stock.py:28` | :16,106–113 |
| `makers.py` | `maker.add` :502, `maker.edit` :534, `maker.hide` :571, `maker.restore` :601, inline in export :499 | `item_add.py:57` | No |
| `model.py` | No ID; declares the skill/slot schema and registry :15–38,77–114,331–341 | `hass/capabilities.py:18`; `__init__.py:13`; `acceptance_run.py:339`; `backlog.py:30`; `D:42`; `front.py:6`; `hikes.py:44`; `item_add.py:58`; `item_picture.py:34`; `items.py:33`; `makers.py:37`; `pages.py:23`; `prompt.py:14`; `reports.py:30`; `restock.py:36`; `router.py:28`; `scaffold.py:47`; `shop.py:27`; `social.py:20`; `specials.py:32`; `stock.py:29` | :14 |
| `openreq.py` | No ID; request store and short-answer resolver (`D:703–733,1325–1330`) | `C:25`; `hass/npp/job.py:19`; `acceptance_run.py:844`; `D:41` | No |
| `pages.py` | `page.home` :328, `page.about` :357, `page.photo` :384 → :407 | `front.py:7` | No |
| `photo_trial.py` | No ID; standalone photo trial :269–304 | None | No |
| `prompt.py` | No ID; builds optional skill prompt :84–111 | `hass/interpreter_prompt.py:29` | No |
| `reports.py` | `report.shelf` :143 → :368; `answer.site` defined at :353 but exported only by `answer_site.py`; both reply hooks :371–383 | `answer_site.py:2` | No |
| `restock.py` | `stock.restock` :166 → :202 | None | No |
| `router.py` | No ID; ranks registry entries :66–73,101–138; separate reply helper :161–213 | `D:466` (literal dynamic import) | No |
| `scaffold.py` | No ID; developer CLI :735–758. :424 is inside its source template, not an export from this module | None | :18,23–53 |
| `shop.py` | `shop.hours` :570, `shop.notice` :595, `shop.contact` :623 → :648 | `hass/content_model.py:665`; `hass/ops/front.py:25`; `front.py:8`; `pages.py:24` | No |
| `social.py` | `social.item` :301, `social.hike` :316, `social.maker` :330, `social.recap` :345 → :360; replies :362–373 | None | No |
| `specials.py` | `specials.add` :619, `specials.edit` :650, `specials.remove` :682, `specials.clear_expired` :705, `specials.show` :722 → :737; rule/reply hooks :740–752 | None | No |
| `stock.py` | `stock.set` :262, `stock.checked` :289, `stock.clear` :320 → :343; no separate `stock.restock` export here | `C:2078,2137,2159` | No |
| `testkit.py` | No ID; offline skill case runner :794–797,852 onward | `acceptance_run.py:265,288,391,409,439,685,739,864,877`; `scaffold.py:47`; `scripts/hass/demo_rehearsal.py:59`. Historical rehearsal import: `reports/hass/live-add-2/rehearse.py:32` | No |

The broad import search also found an `openreq` reference in a staged candidate, `workspace/candidates/AUDINV-OLD-62/candidate.py:100`; neither that candidate nor the historical rehearsal is an owner-chat route. `hass.chat.commands` does not register any skill; compare `hass/chat/commands.py:9–37,215–253` with `hass/skills/__init__.py:19–31`.

### Phrases: candidate versus actual dispatch

- **Phrase scoring is not a command map.** The router scores stemmed trigger examples, hints and the open request, and returns up to three. A unique exact read-only trigger can lead without making the final decision. `D:463–498` uses `router.candidates`, then can ask rather than accept the model's pick; `D:735–765` and `:1101–1148` look up actual calls. No non-test caller of `router.route` was found in tracked Hass source. Photo competition is limited to `item.add`, `item.picture` and `page.photo` in the baseline probe (`router.py:111–118`, `D:445–451`); the separate intake branch can pick `item.add` without a model reply (`D:1325–1359`).
- **Phrase replay, 2026-11-21.** For each named declaration in the table, take its ordered `triggers` list at the definition anchor. With the full baseline registry and no hints, attachment or open request, trigger **#1** ranked its owning active ID first for every row except `stock.set` (**#2** first) and retired `page.faq` (never a candidate). Every active trigger reached its own top three except `item.add` trigger #3, “add this” (`item_add.py:1088`), which returned `backlog.log`, `front.faq`, `hike.add` in that order. These are checked-in examples only, not real messages or proof of action/approval.
- **Host and dispatcher are different seams.** `C:455–457,542–546,2074–2077,2104–2128` defaults to `ops-only`; `both` and `skills-first` admit a skill reply, and `skills-first` rejects raw ops in owned families. `hass/host.py:393–408` builds the interpreter prompt with only ops and content; `hass/interpreter_prompt.py:339–352` adds the Skills block only when given skills. `C:2100–2107` does not pass candidates; `D:463–467,478` asks for ranking after a pick. Thus the handlers are present and callable with the right envelope, but the normal host source does not provide the per-message prompt wiring described in `router.py:6–9`. No claim is made about what a deployed interpreter emits, whether it is enabled or what any owner may do.
- **Fixed phrases can bypass all of that.** `report` / `morning report`, `post`, `listing`, and `backlog` are command verbs, not alternate registry IDs (`hass/chat/commands.py:24–30,232–247`; `C:1280–1289,2685–2693`). `report` goes to `_report`, not `report.shelf`; `post` goes to `_post`, not `social.*`; `listing` goes to `_listing`, not `item.add` or `answer.site`; `backlog` lists, unlike `backlog.log` which records. A multiword `post` or `listing` argument that does not name something can fall through (`C:1286–1289`). “shelf check done” and the fixed “all good except …” form use the `stock.checked` plan directly, including in `ops-only`, subject to the existing checks (`stock.py:203–235`; `C:2077–2084,2134–2178`).

## R2. Unregistered modules, retired paths and apparent duplicates

- **No skill export (13 modules).** Framework/runtime support: `__init__`, `dispatch`, `intake_simple`, `item_intake`, `kinds`, `model`, `openreq`, `prompt`, `router`. Developer or offline tooling: `acceptance_run`, `photo_trial`, `scaffold`, `testkit`. All are loaded by the time `load_skills()` returns; none is its own phrase destination. The CLI trio `acceptance_run`, `photo_trial`, and `scaffold` had no non-test named importer in the scan, not zero uses (R1 CLI anchors). `answer_site`, `faq`, `front`, `hikes`, `items`, `restock`, `social` and `specials` likewise have no non-test named importer, but their exports are loaded by discovery. None of the 29 is unimported by the registry path.
- **One retired skill, not an orphan file.** `page.faq` is retained in the inventory. In the normal registry its `get` returns `None`; the fixed FAQ matcher itself recognized its first declared trigger, but `Dispatcher._explicit_page` returned `False` (2026-11-21 probe). The stale fixed, read-only and router backlog branches refer to `"page.faq"` (`D:677–711,1291–1294`; `router.py:208–212`). `"front.faq"` is a distinct active draft skill (`front.py:184–200,220–231`), not a second registration or spelling of the retired ID. On that same retired trigger the active `front.faq` ranked first, not a guaranteed draft. A model reply naming the retired ID goes to the unknown-skill branch (`D:747–752`).
- **No duplicate name or alias in `SKILLS`.** The loader completed with 42 entries and raises on even one repeated exact ID (`__init__.py:22–30`). `"page.faq"` and `"answer.site"` are each defined in one module and exported by another, once apiece (`backlog.py:171–191` → `faq.py:2–4`; `reports.py:353–383` → `answer_site.py:2–4`). `"stock.restock"` lives in `restock.py`, not `stock.py`. Another near pair, `"hike.recap"` and `"social.recap"`, means writing a recap versus producing a caption from one (`hikes.py:1042–1066`; `social.py:277–286,344–362`). No evidence of a spelling alias in registry lookup, which uses the exact key (`model.py:336–338`).
- **Same names in separate maps are not two skills.** The probe found seven `READ_ONLY` dispatch keys: `answer.site`, `report.shelf`, `social.hike`, `social.item`, `social.maker`, `social.recap`, `specials.show`. All except `answer.site` are also in `READ_ONLY_LONG` (the single reply path also permits a long `answer.site` maker story; `D:1298–1305`). The two backlog-related IDs use explicit branches rather than that map, with `page.faq` inactive as noted above. A real repeated **rule key**, not a skill ID, is `"no-price"`: `RULES.setdefault("no-price", _no_price)` (`D:84`) and `"no-price": rule_no_price` (`hikes.py:459`), copied with `dispatch.RULES.setdefault(rule_id, fn)` (`hikes.py:1117–1118`), so the dispatcher's existing key wins. Other local checks of the same name are not automatically dispatcher registrations (for example `pages.py:161,224`; `shop.py:363,438`).

## R3. What the guide lists and what differs

- **Per module and per ID:** see R1's Guide column. `docs/hass/SKILLS.md:12–21` lists five modules as examples of where things live, not all 29; the only actual registry IDs named are `backlog.log` and `page.faq` (:17,117). `group.verb` is a template, `product.hide` an op example, and the resolver names at :16 are not skill IDs. The other 40 IDs in R1 are not listed in this guide; it expressly points to a generated catalog (:74–79). The probe found that `docs/hass/capabilities.json` (`/skills`, comparing each row's `name` and `status`) matched all 42 registry entries. The loader and duplicate-name explanation (:20–21) still matches R1.
- **Retired FAQ described as available.** The guide says `plus the skills backlog.log and page.faq` (:17, code formatting omitted), `The front-end FAQ entry currently records a request, not a page change` (:94), and `backlog.log and page.faq are read-only` (:117, code formatting omitted). R1 separates the retired `page.faq` from active `front.faq`, which plans a change; the generated view marks the difference explicitly (`docs/hass/CAPABILITIES.md:54,57`). The separate front-skill page already explains the retired path and the lookup guard (`docs/hass/skills/front.md:73–78`). `faq.py` is the export location; `backlog.py` is the declaration location.
- **Old wiring claim.** “a later card wires `conversation.py`” (:118) is stale for the live source connection: enabled `Conversation` already calls the dispatcher, which records backlog rows (`C:2074–2077,2124`; `D:1291–1322`). That connection does not make the retired FAQ handler active or imply host prompt wiring.

## R4. Ranked gaps and next unit

1. **Highest — host prompt and dispatcher support do not join up.** The normal builder supplies no skills or candidate list, while enabled `skills-first` can reject owned raw ops (`hass/host.py:393–408`; `C:2124–2128`). Treat that as a source wiring gap, not a report of an installed failure.
2. **Retirement is not obvious from the authoring guide or leftover branches.** The loader correctly filters `page.faq`; its old branches and the guide make the two FAQ IDs look interchangeable (R2–R3).
3. **One vague add trigger is ambiguous without context.** The router-only miss at `item_add.py:1088` does not justify changing ranks or intake policy: photo and open-request routes differ (R1).

**No build unit is needed for this audit.** Use the generated catalog to check IDs now. The source findings do not authorize changing host/model inputs, rewriting the retired FAQ path, or changing an approval, cap or timer. No such edits were made.

### Reproduce offline

From the checkout, run the static reads below; `git grep` exit 1 means no match, not a test failure. The first two enumerate modules and exports (read `scaffold.py:324–424` in context). The last two locate callers and guide entries; check any relative imports against their package.

```text
git rev-parse origin/main
git ls-tree --name-only origin/main:hass/skills
git grep -nE '^(SKILLS|.*READ_ONLY\.)|^[[:space:]]+name=' origin/main -- 'hass/skills/*.py'
git grep -nE 'load_skills\(|import_module\(|router\.route\(|router\.candidates\(|interpreter_prompt\.build\(' origin/main -- hass
git grep -nE 'hass\.skills|from hass import skills' origin/main -- '*.py'
git grep -nE 'backlog\.log|page\.faq|front\.faq|CAPABILITIES' origin/main -- docs/hass/SKILLS.md docs/hass/CAPABILITIES.md
```

The workspace-only replay `python3 -B skills-probe.py avocado-shack` (from the parent of the clone, supplied alongside the bundle) parsed tracked Python imports and loaded the baseline registry with I/O guards. It compared each declaration's ordered `triggers` with `router.candidates(trigger.text, skills=registry)`, read the dispatch maps and ran only pure parser/eligibility checks. On 2026-11-21 the replay exited 0, with registry/active counts `42 41`, three photo candidates, and the FAQ result `True … None … False` described above. The baseline module import reads the tracked item-standard schema (`hass/itemstd.py:31–38`); the probe allowed that specific file, but not host/runtime data. The probe did not run a plan, whole conversation, test suite or host.
