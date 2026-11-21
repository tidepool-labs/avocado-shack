# Hass skill documentation parity

| Check | Result at the audited main |
|---|---|
| R1 · Module coverage | 29 Python files, including the package initializer; 16 are covered by a dedicated or shared page (including one intake helper); 13 have no page. All 12 ordinary skill pages point to existing implementations. The two NPP `SKILL.md` pages are operator procedures, not registry modules. |
| R2 · Parity | The clearest broken references are the NPP design/replay/eval paths. Several catalog pages describe wiring or boundaries from when they were written rather than the current source. See the page-by-page table. |
| R3 · Authoring guide | Both real skill IDs named in `SKILLS.md` exist; one is retired and exported from a different file than the guide implies. Five files are named individually; 24 are not. |
| R4 · Priority | First clarify the NPP maintenance references, then correct claims about catalog execution, then improve navigation. One documentation-only follow-up is proposed, not performed. |

**Source and limits.** Checked 2026-11-21 against `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, exactly the supplied baseline (`git rev-parse HEAD origin/main` before branching). Paths and line numbers below are from that commit. Current site source is `storefront-mockup/` (`AGENTS.md:3–5`); historical trees are not replacements for missing paths. `reports/hass-npp/G-QUESTIONS.md` is not tracked at this ref (`git ls-tree` check below); no external copy was read or policy inferred. These were offline Git, line-count, Python syntax-tree/JSON reads and source comparisons, not tests of message handling, deployed behavior, live data, model routing or publication. No runtime files were opened.

## R1. Module to skill page

Module paths below are relative to `hass/skills/`; page paths are relative to `docs/hass/skills/`. “Page” includes a shared page that substantively describes a module's skill, with code identity verified, but not a passing mention of a helper, hook or caller. The right column identifies a source line or export that makes this distinction reproducible. Counts are physical lines, including blanks and comments (`wc -l hass/skills/*.py`).

| Module | Lines | Page and anchor | Module evidence |
|---|---:|---|---|
| `__init__.py` | 66 | no page | `:19` registry loader; guide is separate |
| `acceptance_run.py` | 1165 | no page | `:1` acceptance runner |
| `answer_site.py` | 4 | `reports.md:77–80` (shared, by skill ID) | `:2–4` exports `ANSWER_SITE` from `reports.py:353` |
| `backlog.py` | 248 | no page | `:148–191` owns `backlog.log`; defines retired `page.faq` described on `front.md:75`, but exports only `BACKLOG_LOG`; see `faq.py` |
| `dispatch.py` | 1365 | no page | `:1–29` dispatcher; e.g. `hikes.md:118–138` is an interface mention |
| `faq.py` | 4 | `front.md:73–77` (shared, by retired ID) | `:2–4` exports `PAGE_FAQ` from `backlog.py:173–189` |
| `front.py` | 231 | `front.md:3,44–52` | `:231` four front skills |
| `hikes.py` | 1146 | `hikes.md:4,11–20` | `:1066` six hike skills |
| `intake_simple.py` | 285 | no page | `:1` helper; `item_add.md:130–155` describes full intake, not a separate page for simple intake |
| `item_add.py` | 1115 | `item_add.md:1–4` | `:1083,1115` `item.add` |
| `item_intake.py` | 770 | `item_add.md:130–155` (shared, by full intake flow) | `:1–24,743–769` full interview/private intake record helper; no `SKILLS` export |
| `item_picture.py` | 452 | `item_picture.md:1–7` | `:414,452` `item.picture` |
| `items.py` | 584 | `items.md:1–12` | `:576` three item skills |
| `kinds.py` | 208 | no page | `:77,170` resolvers; guide is separate |
| `makers.py` | 625 | `makers.md:1–12` | `:499–625` four maker skills |
| `model.py` | 341 | no page | `:74–98,332–341` data model and registry; guide is separate |
| `openreq.py` | 422 | no page | `:1–4,27–33` request storage |
| `pages.py` | 407 | `shop.md:106–157` (shared, by skill ID) | `:12,407` back-link and `page.home`, `page.about`, `page.photo` |
| `photo_trial.py` | 306 | no page | `:1` photo trial helper |
| `prompt.py` | 111 | no page | `:84` prompt builder, cited as a helper at `reports.md:96–100` |
| `reports.py` | 383 | `reports.md:1–4,77–80` | `:143,353,368` `report.shelf` export and `answer.site` definition |
| `restock.py` | 202 | `restock.md:1–6` | `:166,202` `stock.restock` |
| `router.py` | 213 | no page | `:1` router, cited as a helper at `reports.md:62–66` |
| `scaffold.py` | 758 | no page | `:738` scaffolder; guide is separate |
| `shop.py` | 648 | `shop.md:1–14,31–105` | `:648` three `shop.*` skills |
| `social.py` | 373 | `social.md:1–14` | `:360–362` four social skills |
| `specials.py` | 752 | `specials.md:1–14` | `:737` five specials skills |
| `stock.py` | 343 | `stock.md:9–14` | `:343` three stock skills |
| `testkit.py` | 901 | no page | `:855–860` case runner, not a catalog skill page |

The 12 same-stem modules are the literal matches. Four more are covered by substance rather than a same-stem page (`answer_site`, `faq`, `item_intake`, `pages`), giving **16 with coverage and 13 with no page** if the hosted intake workflow counts as a page for its helper. Counting only modules with a covered registry declaration or export gives 15: `item_intake.py` is covered by `item_add.md:130–155` but exports no registry skill of its own. Neither NPP procedure has a counterpart named `hass_npp_maintain.py` or `hass_npp_review.py`; `scripts/hass/npp_preflight.py:22–39` lists NPP code and the two procedural pages separately.

## R2. Page-by-page reference and wording check

Page paths in the left column are relative to `docs/hass/skills/`. Quotes show the documented wording or name and the code counterpart; “not tracked” means no corresponding Git path, not evidence that a generated or host-side file does not exist. A model-facing example need not be an exact `Trigger` to work, and a template with substitutions need not contain the fully rendered sentence as a literal. Example wording differences below are not routing failures. Authoring-guide drift is listed under R3.

| Page | Quoted doc reference or claim → what source actually has |
|---|---|
| `front.md` | **Wording:** `:20` “the four page names wait for B2” is time-bound; the four names are already in `BANNER_PAGES` (`hass/content_model.py:612–614`), and `banner_link` suppresses the link until the page is shown (`hass/notice.py:16–20`). `:26` “`notice.BANNER_JS` swaps them” names a real constant, but its value is a script tag for `/banner.js`, not the switching logic (`hass/notice.py:13`, `storefront-mockup/banner.js`). `:51,80` “hide Our policies page” is not the verbatim trigger; `hass/skills/front.py:209` has “take Our policies page off the site”. The page's `registry.get("page.faq")` reference is real; the legacy ID is retired (`hass/skills/backlog.py:189`, `hass/skills/model.py:332–341`). |
| `hass-npp-maintain/SKILL.md` | **Missing tracked paths:** `:11` `reports/hass-npp/PIPELINE-DESIGN.md`; `:24` `hass/tests/npp/run_npp.py` (explicitly conditional on NPP-H; `scripts/hass/npp_preflight.py:32` still lists it); `:29` `npp_eval.py --judge` (no tracked `npp_eval.py`, no replacement inferred). `hass/tests/npp/cases/FORMAT.md:3–6` distinguishes the checked-in data from the future runner. `:15` says `contracts`, but the current format has `contract` and `bug` (`FORMAT.md:16–21`). `:21–24` `scripts/hass/npp_limits.py` and `hass/tests/test_npp_assets.py` are real; the checked-in `limits.json` is under `hass/npp/assets/hass-gallery-style/` and `copy-templates.json` under `hass/npp/assets/hass-listing-copy/`. |
| `hass-npp-review/SKILL.md` | **Case format:** `:26,32` “`npp-YYYYMMDD-n`” and `"contracts"` do not describe the current case files: `scripts/hass/npp_case_new.py:32–66` writes `case-NN-slug.json` with numeric `id`, `contract`, `bug`; the older dated form is still accepted by the findings parser (`scripts/hass/npp_findings.py:25`) and echoed by `hass/tests/npp/cases/FORMAT.md:6`. **External references:** `:9` `HASS-NPP-WEEKLY` is a procedure label, not a registry ID; `:20` `metrics.tsv` is not tracked, and no host path was checked. `:14` `receipt.json` is a generated artifact, not a missing source file (`hass/npp/receipt.py:62–75,92–103`); `:27` `hass-npp-maintain` is the neighboring procedure, not a Python symbol. |
| `hikes.md` | **Stale integration:** `:131` “Not consumed yet by the real dispatcher” / `:135` “`I set: signup: False`” are no longer the normal hook path: `hass/skills/dispatch.py:74,346–355` has `SET_PHRASES` and consumes it; `hass/skills/hikes.py:542–548` supplies `set_line` and the `hike.add` hook. `:188` “the kit refuses both” is false for `undo: true` (`hass/skills/testkit.py:54,574,592`); `kind: "undo"` as a test row is distinct from that flag. `:100` `recap_announcement(content, hike_id)` exists, but the parameter in code is `event_id` (`hass/skills/hikes.py:1070`); the actual social skill uses `social_draft.build_recap` (`hass/skills/social.py:277–290`). |
| `item_add.md` | **Stale integration:** `:181–182` “not merged” for the router and “until it merges” for the hooks are not the state of the tree; `hass/skills/router.py`, `hass/skills/dispatch.py:358–375,941–968,994–1009` and `hass/conversation.py:542–546` contain them. `:23` the fully spelled out “Which shelf does it go on: …?” is assembled from `SHELF_LABELS`, not a missing prompt (`hass/skills/item_add.py:80,593`). `:24,65,87` the description and story lines use templates (`:99,750–751,874` in the module). `:90–99` `robots.txt` is a target-site path, not a repository file; `:125,153` `maker-sources.jsonl` and `item-intake.jsonl` are runtime outputs, named in `hass/skills/dispatch.py:398–402` and `hass/skills/item_intake.py:24,743–769`. |
| `item_picture.md` | **Stale boundary rationale:** `:78` “`product.set_photo` is not in the live boundary” is contradicted by the op in `hass/live_policy.py:193`. The skill declaration itself is still `live_class="private-only"` (`hass/skills/item_picture.py:438`, manifest line 19); neither fact establishes live host settings or changes permissions. `:54` `picture_review` is real in `hass/skills/item_add.py:993`; `:71` `photo-<sha16>.<jpg|png>` is a generated filename pattern, not one tracked image. |
| `items.md` | **Stale integration:** `:112,114` “does not show these lines yet” and “router and dispatch are not merged yet” are contradicted by `items.notes` (`hass/skills/items.py:452–475`) and the caller that collects proposal notes (`hass/skills/dispatch.py:994–1009,1033`; constructor in `hass/conversation.py:542–546`). **Moved, not missing:** `:129` `conversation.COMMAND_RE` is imported from `hass/chat/commands.py:19–24` (`hass/conversation.py:34–38`); the `show` pattern still accepts a suffix, so the example collision is not claimed fixed. |
| `makers.md` | No confirmed missing named function or source path. `:99,103,105` `find_maker`, `Refusal`, `Outcome` and all four `describe_*` functions are present (`hass/skills/makers.py:51–63,264,324,372,447,472`). `:76,78–79` example questions with placeholders are constructed, not fixed literals (`:264–287,372–386` in the same module). |
| `reports.md` | **Stale limit:** `:21` “caps its own text at 1200 characters” describes the base block, not the complete output. `hass/morning_report.py:153–170` appends all `restock_text` lines after the `MAX_CHARS` check; `hass/skills/reports.py:131–135` calls that renderer. `:73–74` “the lint's ‘undo row’ count cannot be met” is not a requirement for read-only skills (`hass/skills/model.py:323–325`). `:50` `conversation.parse_command` is a re-export of the real function (`hass/chat/commands.py:215`, `hass/conversation.py:34–38`). `:90,96–100` `guest_counts_checked` and `skills_section` resolve at `hass/ops/hikes.py:42` and `hass/skills/prompt.py:84`. |
| `restock.md` | No confirmed missing named function, live-table entry claimed to exist, or path. `:21` the two-product sentence is real (`hass/skills/restock.py:172`, `hass/tests/test_skills_restock.py:263`): one `item` per call, not a list in one call (`hass/skills/restock.py:104–109,137,180–188`). `:54` “more expected” is produced by `restock_text` (`hass/morning_report.py:99–101,169–170`). `:68` the op's absence from the two tables is as documented (`hass/live_policy.py:185–222`). |
| `shop.md` | **Stale routing and tooling:** `:134` “no such page: `page.faq` writes it down” is obsolete: `page.faq` is retired, and `page.about` now points to “fill the About page” (`hass/skills/backlog.py:189`, `hass/skills/pages.py:355–380`, `hass/skills/front.py:207–216`). `:170` “The kit has no media store” is outdated (`hass/skills/testkit.py:320–335` supports row photos). `:175–183` “until SKILLS-FW-2 and SKILLS-FW-3 are merged” and “generic … line” are historical: settings and dispatcher wiring exist (`hass/conversation.py:455–457,542–546`); `_plan_stopped`'s reply handling below the plan (`hass/skills/dispatch.py:941–968`) uses a nonempty `exc.reply`, with the generic fallback otherwise. `SkillStop` still has `reason`, not `backlog` (`hass/skills/shop.py:35–41`); the dispatcher reads `backlog` for that path, so the old proposed `exc.reason` hook is not the current contract. |
| `social.md` | No confirmed missing named function or path. `:11–14` “`social_draft.build`”, “`build_hike`”, “`build_maker`”, “`build_recap`” resolve in `hass/social_draft.py:81,117,168,145`. `:41–45` “No photo is attached here.”, `READ_ONLY_LONG` and `Ctx.site_dir` have source counterparts (`hass/skills/social.py:26,362–370`, `hass/skills/dispatch.py:76,87–101`). |
| `specials.md` | **Stale integration:** `:40–45` “dispatcher … is not on main” / “when that module exists” are outdated (`hass/skills/dispatch.py:68–76`, `hass/skills/specials.py:737–752`). `:50` “`STRING_KINDS` lacked it” is historical: `"deal"` is in `hass/interpret_check.py:23`. `:55` the generic refusal claim is no longer true when an exception carries `.reply` (`hass/skills/dispatch.py:941–968`); rule hits are a separate path (`:912–922`). `:56` “kit rows have no `undo` field” is contradicted by the `undo` field and validation (`hass/skills/testkit.py:54,574,592`). `:37–38` `private-only` is still declaration metadata, but the four ops themselves are listed in `LIVE` (`hass/live_policy.py:190`, manifest lines 37–40); the op list is not evidence of host permission. `:52–54` proposal text and screenshot are separate: don't read the historical proposal-line example as the current preview; the preview's `specials` target carries `title` and `deal` (`hass/preview.py:132–133`). |
| `stock.md` | **Moved storage name:** `:19` “keeping the change in `open_asks`” names the old table. `open_requests` is current; `open_asks` remains in migration code (`hass/conversation.py:129,547–549`, `hass/skills/openreq.py:27–33,107–132`). `:34` the example containing “I change six at a time. Which ones should I do first?” is formatted from `TOO_MANY` (`hass/skills/stock.py:36`); `:62–64` `kinds.product_ref` and `BAD_ITEM` are not dead names (`hass/skills/stock.py:46,96–107`). |

## R3. `docs/hass/SKILLS.md` versus modules and skill IDs

| Named ID or example | Source result |
|---|---|
| `backlog.log` (`:17,117`) | Exists and active: `hass/skills/backlog.py:149,191`; manifest line 5. |
| `page.faq` (`:17,117–119`) | Exists and **retired**, not a missing module/ID. Defined at `hass/skills/backlog.py:173–189`, exported separately by `hass/skills/faq.py:2–4`; manifest line 26. `Registry.get` excludes it (`hass/skills/model.py:332–341`). “Plus the skills `backlog.log` and `page.faq`” at `:17` describes where their definitions are, but misses the wrapper and retirement. “A later card wires `conversation.py`” at `:118` is stale: `hass/conversation.py:542–546` creates the dispatcher and `hass/skills/dispatch.py:678–711` shows the retired-ID check. |
| `group.verb` / `product.hide` (`:26,38–44,57`) | A placeholder and an op, respectively, not claims of registered skill IDs. The registered skill is `item.hide` (`hass/skills/items.py:484`; manifest line 18); `product.hide` is registered as an op (`hass/ops/catalog.py`, search below). |

**Skills the guide names with no module: none.** `SKILLS.md:14–18` names five actual files: `model.py`, `__init__.py`, `kinds.py`, `backlog.py`, `scaffold.py` (the unqualified `kinds.py` at `:106` repeats one). The other **24** under `hass/skills/` have no individual line in the guide:

`acceptance_run.py`, `answer_site.py`, `dispatch.py`, `faq.py`, `front.py`, `hikes.py`, `intake_simple.py`, `item_add.py`, `item_intake.py`, `item_picture.py`, `items.py`, `makers.py`, `openreq.py`, `pages.py`, `photo_trial.py`, `prompt.py`, `reports.py`, `restock.py`, `router.py`, `shop.py`, `social.py`, `specials.py`, `stock.py`, `testkit.py`.

The guide calls itself an authoring guide (`:1,7–8`), not an exhaustive inventory. The generated manifest has 42 rows, including the retired ID (`docs/hass/capabilities.json:4–45`; active lookup in `hass/skills/model.py:332–341`). Do not conflate those rows with Python file count or deployed enablement. The guide's skill-lint prototype at `:100` also omits that `repo_root` and `golden` are keyword-only (`hass/skills/__init__.py:34`).

## R4. Ranked gaps and one possible follow-up

1. **Missing NPP maintenance entry points and stale case format.** These can send a maintainer looking for a nonexistent runner or using an outdated case shape (`hass-npp-maintain/SKILL.md:11,15,24,29`; `hass-npp-review/SKILL.md:26–34`; R2). No substitute for a future runner, judge, or external source was assumed.
2. **Old catalog wiring and mixed boundary terminology.** Prioritize `item_picture.md:78`, `shop.md:134,170–183`, `hikes.md:131–135` and `specials.md:37–56` (R2). A declaration, an op table, and deployed permission are separate facts.
3. **Navigation rather than new pages.** `SKILLS.md:10–21,74–79` and R1/R3 favor linking the authoring guide and generated manifest over writing a page per helper. A missing page is not a missing skill.

**One possible unit, estimated 60–90 minutes, not performed:** Clarify NPP maintenance references in `docs/hass/skills/hass-npp-maintain/SKILL.md` only. Mark the untracked design, replay and judge references as unavailable in this checkout, and reconcile `contracts` with the current `contract`/`bug` case format. Leave operator rules, prerequisites, thresholds, code, tests and assets unchanged. Offline acceptance: use `git ls-files` to confirm the retained paths, and compare the case wording to `hass/tests/npp/cases/FORMAT.md:16–21` and `scripts/hass/npp_case_new.py:32–66`; `git diff --check` and `git diff --name-only` should show a clean one-page change. Do not run the runner, judge or a live preview for that check.

### Reproduce the source checks

From the repository root at the audited SHA (or replace `origin/main` below with the full SHA to avoid a moving ref):

```text
git ls-tree -r --name-only origin/main -- hass/skills docs/hass/skills
wc -l hass/skills/*.py
git grep -n -E 'SKILLS =|name=|^from hass.skills' origin/main -- hass/skills
git grep -n -E 'hass/skills/|kinds.py|backlog.log|page.faq|group.verb|product.hide' origin/main -- docs/hass/SKILLS.md
git grep -nc '"name":' origin/main -- docs/hass/capabilities.json
git grep -n -F '"product.hide"' origin/main -- hass/ops/catalog.py
git ls-tree -r --name-only origin/main -- reports/hass-npp hass/tests/npp scripts/hass
git ls-tree -r --name-only origin/main -- '*npp_eval.py' '*metrics.tsv' '*PIPELINE-DESIGN.md' '*G-QUESTIONS.md'
git grep -n -E 'SET_PHRASES|_skill_notes|def _plan_stopped|open_requests|open_asks' origin/main -- hass/skills hass/conversation.py
git grep -n -F 'hide Our policies page' origin/main -- hass/skills/front.py hass/tests/test_front_pages.py
```

The last exact-phrase check had no hits (exit 1); use `git show origin/main:hass/skills/front.py` to see the alternative trigger. For all other R2 pairs, `git show origin/main:<cited-path> | nl -ba` reproduces both cited sides; use the named source template when the words are assembled. The line inventory used Git blobs and Python AST inspection as a cross-check, without importing the skill package. The generated JSON was read, not regenerated. No product, content, setting, approval or owner decision changed.
