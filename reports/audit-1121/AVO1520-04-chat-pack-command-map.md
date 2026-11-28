# Hass chat packs and the staff guides

| Check | Result |
| --- | --- |
| R1 · What is defined | Three handler packs share one parser. `COMMANDS.md` covers every parser outcome in its main table; it does not list every accepted phrase or short form. `NATURAL_LANGUAGE.md` is a phrase guide, not a second command index. |
| R2 · What is listed but not registered | No unsupported parser outcome in the main command table. The guides also list reader examples, listing-flow replies and conditional till commands; those are not new registrations in the three packs. Two natural-language examples have a direct route that differs from the guide. |
| R3 · Overlap and order | No double registration among the three mixins. Core hands `cost` to Reports; it does not register a second `cost`. `?` and some other inputs can be claimed by separate routes before the default handler runs. |
| R4 · What to check first | Reconcile the documented undo/cancel hint behavior before filling in shortcuts. One proposed documentation-only follow-up; nothing implemented here. |

Inspected 2026-11-21: cloned `tidepool-labs/avocado-shack`; `git rev-parse origin/main` returned `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, the task baseline. No existing map surfaced in `git grep -niE 'chat.pack|command.map' origin/main -- reports docs/hass/COMMANDS.md docs/hass/NATURAL_LANGUAGE.md docs/hass/PHONE_GUIDE.md` (no matches), and `git ls-tree -r --name-only origin/main -- reports/audit-1121` was empty. This is source evidence, not a check of an installed service. The catalog is `storefront-mockup/` (`AGENTS.md:3–5`); nothing here changes approval, holds, cloud data, networking or procedures.

## R1. Triggers by pack

Path keys in all tables: **C** = `docs/hass/COMMANDS.md`, **N** = `docs/hass/NATURAL_LANGUAGE.md`, **P** = `docs/hass/PHONE_GUIDE.md`, **X** = `hass/chat/commands.py`, **Core** = `hass/chat/core_pack.py`, **Site** = `hass/chat/site_pack.py`, **Reports** = `hass/chat/reports_pack.py`, **Route** = `hass/conversation.py`. A doc citation lists the send form, not just the same word in a different context. `—` means not independently listed there; `undocumented` means no direct listing in any of these three docs. `usage` means the parser takes the short or incomplete form; it need not return useful data or make a change. `N:7–8` links to the fuller guides.

`hass/chat/__init__.py:1–4` and `Route:508,2674–2701` describe mixins and central routing, not per-pack registration tables. `hass/chat/shared.py:19–46` and `hass/chat/wording.py:266–275` supply shared helpers and reply wording, not matchers. The tables group aliases and argument variants by destination.

| Core pack send form | Parser → handler | C | N | P |
| --- | --- | --- | --- | --- |
| `history`; `history <words>` | X:19,234–236,252–253 → Core:70,95; Route:2696,2698–2701 | 34–35 | — | 73–75 |
| `status`; `did it work`, `did that work`, `did my change work` (with or without `?`) | X:20,252–253 → Core:483–486,503; Route:2682 | 12,39–40 (question examples) | 7,21,72 (`status`, not those aliases) | 37,84–86 (`status`) |
| `pause`, `pause changes`, `stop`, `stop changes` | X:20,252–253 → Core:483–493; Route:2682 | 41 | — | 82–83 (`pause changes`) |
| `resume`, `resume changes` | X:21,252–253 → Core:483–501; Route:2682 | 42 | — | 90–91 (`resume changes`) |
| `show <code>`; bare `show` repeats newest waiting proposal | X:23,248 → Core:217–225; Route:2684 | 50; bare form mentioned at 266, not explained there | — | — |
| `again <code>`; bare `again` gives usage | X:31,231 → Core:179–184; Route:2697 | 38 (coded); bare usage undocumented | — | 92–93 (coded) |
| `backlog` | X:30,232 → Core:249; Route:2693 | 69 | — | — |
| `remember <key>: <text>` (including spaced keys); bare `remember` or no colon goes through validation | X:123,256–267 → Core:271,315–335; Route:1315,1330 | 15,18–19,43; malformed usage undocumented | — | 104,106 |
| `forget <key>` (spaces, `it`, `design.<n>` and `cost.<product id>` included); `forget alias <name>` or direct `forget alias.<slug>` key | X:123,256–258,274–283 → Core:271,299–314 | 16–20,44,46–47,264; dotted alias form undocumented as such | — | 104,107 (key/design) |
| `forget backlog.<n>` | X:123,274–283 → Core:264–269,274 | 70 | — | — |
| `memory`, `notes` (also `memory?`, `notes?`) | X:123,284–285,306–310 → Core:275–295 | 12,45 (`memory`); literal `notes` alias and `notes?` undocumented | — | 20,104,109 (`memory`) |
| `alias <name>: <product or maker>`; bare `alias` or missing operand reaches usage/refusal | X:123,268–270 → Core:297,341–362 | 46; bare usage undocumented | — | 20,94 (use of saved alias, not the save command) |
| `costs` (not `cost`) | X:33,226 → Core:412; Route:2694 | 12,47–48 | — | — |

| Reports pack send form | Parser → handler | C | N | P |
| --- | --- | --- | --- | --- |
| `report`, `morning report` | X:24,247 → Reports:56; Route:2685 | 51 | — | 94 (`report`) |
| `post <product id/name/alias>`; bare `post` gives usage | X:25,243–246 → Reports:146–162,167–192; Route:1288–1289,2686 | 52 | — (`post a hike …` at 44 is a different request) | 94,98 |
| `post hike <hike>`; bare `post hike` gives usage | X:25,243–246 → Reports:156–157,166,238–254 | 53; bare usage not explained | — | 94 |
| `post maker <key>`; `post maker` with no key gives usage | X:184–197,218,300 → Reports:155,165,219–236 | 12,54 | — | 94–95 |
| `post notice` | X:25,243–246 → Reports:164,206–217 | 55 | — | — |
| `margin <pack cost> for <units> at <margin>%`; `margin <product> at <margin>%`, optionally `shrink <S>%` and `ending .99` or `ending .49` | X:26,242 → Reports:32–35,88–106; Route:2688 | 56,58 | — | 94,103 (examples) |
| `margin <pack cost> for <units> price <P>`; `margin <product> price <P>`, optionally `shrink <S>%` (no ending); bare `margin` gives usage | X:26,242 → Reports:36–38,88–106 | 56–57,59 | — | 94,102 (pack-price example) |
| `cost <product>: <pack cost> for <units>`; bare `cost` or missing operand reaches usage/refusal | X:124,271–273 → Core:296–298 → Reports:284–323 | 47; bare usage undocumented | — | 94 |

| Site pack send form | Parser → handler | C | N | P |
| --- | --- | --- | --- | --- |
| `find <words>`; bare `find` gives usage | X:22,250 → Site:30,160; Route:2683 | 12,49 (query); bare usage undocumented | — | 20,84–89 (lookup) |
| `listing <id/name/alias>` (product, maker, hike or route idea as applicable); bare `listing` gives usage | X:23,237–240 → Site:141–158,242–269; Route:1286–1287,2690 | 63 | — | 88–89,94,99 |
| `listing store` (reserved argument) | X:23,237–240 → Site:211,249 | 67 | — | 94,97 |
| `hidden` | X:27,241 → Site:364; Route:2689 | 12,60 | — | — |
| `held` | X:34,225 → Site:384; Route:2695 | 12,61 | — | — |
| `photos to take` | X:29,233 → Site:306; Route:2691 | 64 | — | 32–33 |
| `shelf <name or id>`; bare `shelf` or an unknown name shows choices (stock-update shapes are excluded) | X:32,36,227–230 → Site:331–338; Route:2692 | 68 | — | 94,96 (bare use named; chooser not explained) |
| `look`, `look hike`, `look <product id/name/alias>` | X:200–212,219 → Site:45–51,105–127; Route:2687 | 62 | — | — |

| Shared parser / Conversation (not a fourth handler pack) | Trigger and dispatch | C | N | P |
| --- | --- | --- | --- | --- |
| `help`, `commands`, `?`, `what can you do`, `what do you do`, `what can I say` (last three allow `?`) | X:21,41–106,249 → Route:2678–2681; contextual `?` in R3 | 65 | 7,90 (`help`) | 94 (`help`) |
| `help <word>` or `help <known multiword name>` | X:49–84,109–119,221 → Route:2675–2677. Known multiword names are `morning report`, `photos to take`, the three `did … work` aliases, `stop changes`, `pause changes`, `resume changes`, and the three capability questions. Any single token gets help detail or unknown-command guidance. Prefixes are not arbitrary: e.g. `help post hike` does not match. | 66 (rule and examples) | — | 94,101 (`help undo`) |
| `undo [<code>]`; bare aliases `undo that`, `undo it`, `undo last`, `undo the last change`, `please undo` | X:15,19,222,251 → Route:2702–2739 | 36–37,72 | 7,73 (`undo that` described as a hint; see R2) | 76–79 |
| `yes`, `approve`, `approved`; `no`, `cancel`, `reject` (all with optional short hex code); bare `cancel that`, `cancel it`, `never mind`, `nevermind` | X:14,16–17,130–138 → Route:1357,1387–1448 (including context and refusal branches) | 4,28–31,72 | 4–7,21,74 (`never mind` described as a hint; see R2) | 9–11,28,52,78–80 (examples) |
| `no all`, `cancel all`, `cancel everything`; `yes all`, `approve all` (refusal only) | X:127,130–138 → Route:1299–1311,1484–1501 | 32–33 | — | 94,100 (`no all`, `yes all`) |
| Coded phone replies in either order with courtesy words, emoji and punctuation; question forms and a lone waiting code are hints only on this route | X:153–174 → Route:1297–1298,1357,1370–1377 | 22–24 | — | 9–12,84 |
| Nonhex code-like token (4–12 alphanumeric with a digit) after an approve/reject word; refusal-only check, not a new approval | X:141–150 → Route:1346–1352 (with waiting-code-prefix exception) | 24 (unknown code in question guidance, not this refusal form) | — | 9 (unknown code not approval, no exact grammar) |
| Near-approval hints: `ok`, `okay`, `yes please`, `yep`, `yeah`, `sure`, `go ahead`, `do it`, `sounds good`, `looks good` (optional short hex code) | X:18,177–181 → Route:1357–1369. Listed three examples only; the other seven and the optional code form are undocumented in these guides. | 174 (generic reference) | 75 (`ok`, `go ahead`, `looks good`) | — |
| Closing `?` on a read: `history`, `status`, `help`, `find`, `show`, `report`, `post`, `margin`, `hidden`, `listing`, `backlog`, `look`, `shelf`, `costs`, `held`; also `memory`/`notes` via its own wrapper | X:288–310; maker key punctuation is preserved; `photos to take?` is not accepted by this rule. | 12; `backlog?`, `look?`, `shelf?`, `notes?` undocumented | — | 84–87 (general rule with examples) |

For punctuation and case outside the question wrapper, see X:130–138,184–223,261–285 and C:8–24. Bare verbs that only reach usage are not missing features. `HELP_ENTRIES` describes usage, not an alternate registry; in particular the listing-photo instruction is explicitly not a photo command (X:38–48).

## R2. Listed phrases without a pack registration

No unexplained missing command in the 43-row main table (C:28–70): the existing command-card test checks examples and discovered parser outcomes (`hass/tests/test_commands_doc.py:9–55`). The following are the apparent extras when reading the guides beyond that table. Quotations are the send-side text or relevant excerpts, not suggested wording.

| Guide quote | What actually handles it |
| --- | --- |
| N:72: “`did it go up?`, `is it live`, `what's waiting`” | No direct pack match. Reader guidance, not `status` aliases (X:20–21; `hass/interpreter_prompt.py:127–129`; Route:1383–1386). |
| N:73: “`undo that`, `take it back`” / “Tells you to send `undo`” | `take it back` is reader guidance. `undo that` actually parses as `undo` (X:15,222); it enters draft handling, not merely a hint (Route:2702–2739; C:36,72; P:78). |
| N:74: “`never mind`, `scratch that` (with a draft waiting)” / “Tells you to send `no a1b2`” | `scratch that` is reader guidance. `never mind` actually parses as bare rejection (X:16,134); it enters cancellation handling (Route:1392–1401,1406–1430; C:31,72; P:78). |
| N:76: “`what time do we close saturday?`, `when's the next hike?`” | Examples for the reader, not spellings registered by a pack. C:177–185 shows the same distinction and names the permitted outputs; `hass/interpret_check.py:30,119–126` and Route:2059–2072 validate and dispatch an allowed output. |
| N:77: “jokes, thanks, off-topic”; C:164–165: “`thanks`, `thank you`, `great, thanks`, `hi`, `hello`, `good morning`” and “only emoji”; P:3–4: “`thanks`” and “`👍`” | The fixed phrases and emoji are handled by `hass/social_message.py:18–19,125–134` and Route:1357–1369, not a pack. Jokes and off-topic requests are not a fixed social matcher. |
| C:170–172: “`histroy`, `staus`, `reprot`, `memroy`, `undp`” and “`stow`”; P:104–105: “`histroy`” | Typo suggestions only (Route:99–120,1378–1382), never alternative command spellings. Related extra outside the packs: courtesy-wrapped pause/stop/resume gets guidance only, not a control action (Route:88–96,1290–1293; exact courtesy forms undocumented in C/N/P). |
| C:82–87: “received”, “set”, “is sold out”, “new item:”, “change price of”, “hide … on the till”, “show … on the till” (operands elided); C:88–89: “`yes <code>` / `no <code>`” and “`undo <code>`” | Conditional till grammar, not a catalog pack. See `hass/clover/chat.py:25–32,130–161,164–172` and Route:1316–1318,1334–1345. Only the general approval/undo forms are shared; the first-pass till cases are in R3. Not tested against a till. |
| C:131: “before, with or after the photo”; C:139–142: “Edit the preview with”, “`What's next` or `?` repeats the current preview”, “`yes <code>` applies the latest preview” | These are the **simple intake** finance caption, remove/add/price/name/brand/category edits, and preview replay (examples with operands not reproduced here). `hass/skills/intake_simple.py:14–31,113–175`; `hass/skills/dispatch.py:659–675,688–695`; Route:1283–1285,1313–1315,1353–1356,2074–2077. No new pack verbs. For the separate NPP path, tagged `yes <code>-<version>` is mentioned in X:42–47 and parsed outside the packs (`hass/npp/job.py:53–54`, Route:1503–1546). NPP edit routing is grammar/state-dependent; `?` is taken for retry, not a general NPP preview replay (`hass/npp/reply.py:91–103`, `hass/npp/job.py:145–148`). `docs/hass/NPP-EDIT-PHRASES.md:3,7–13,61` documents grammar cases, not global chat commands. |
| C:160: “Send `skip` to keep only the town line”; P:9: “Answer in plain words, or say skip.” | An answer to a maker-story question, not a global command (`hass/skills/item_add.py:100`, `hass/skills/dispatch.py:714–730`). |

The other plain-word site examples are deliberately not counted as missing commands: N:29–64, P:6–71 and C:106–126,149–161,177–265 distinguish requests, attachment replies and internal operation names from whole-message commands. For literal reproduction of the excerpts above, read the cited lines; C:82–87 contains the full synthetic till examples.

## R3. Duplicate commands and precedence

- **No same trigger registered independently in two packs.** Python method lookup is `Conversation → CorePack → SitePack → ReportsPack → object` (`Route:508`). That is not a sequence of parser trials. The shared parser returns a verb and `_command` branches on it (`Route:1280,2674–2701`). The three pack classes also have no duplicate method names in the offline check. `cost` is the clearest overlap in responsibility: the Core memory handler explicitly delegates to Reports, and Core's `costs` is a different trigger (`Core:271–298,412`, `Reports:284`). Similarly, Reports reuses Core's waiting lines and Site's product lookup helpers; neither adds a second `report` or `post` (`Reports:70–74,160–175`, `Core:547–554`, `Site:83–91`).
- **Actual message order.** For an eligible text turn, `read_command` is tried first: special `post maker` keeps its key punctuation; read-only `?` handling and `parse_command` handle the rest (X:215–253,288–303). Conversation next offers the turn to NPP, checks the simple-intake `?` exception and the multiword `listing`/`post` name guards, then offers near-control guidance (Route:1280–1293). After phone recognition and early bulk handling, it considers memory only without a command or intake answer. A configured `TillDesk.first` can preempt both for a matching till code or `show <item> on the till`; ordinary till parsing is a fallback, not a blanket priority over pack commands (Route:1297–1318,1325–1345; `hass/clover/chat.py:130–161`).
- **Then** unmatched turns can hit the unknown-code check, an open skill answer, keyword/decorated approval or rejection, social/near-approval/phone guidance or a typo hint, and finally the ordinary request path if no keyword matched (Route:1346–1387). Keyword execution still has its own guards (Route:1387–1448). NPP may handle a status response while reusing Core's `_status`, and NPP or simple intake can intercept `?` under their own conditions; neither is a second mixin registering `status` or `?` (Route:1280–1285,1503–1546; `hass/skills/dispatch.py:659–665`).

## R4. Ranked gaps and one possible follow-up

1. **Direct draft/cancel vs a hint.** N:73–74 describes `undo that` and `never mind` as reminders, but C:31,36,72 and the actual branches show direct routing (R2). This is more consequential than a missing alias. Do not infer that either phrase applies a site change or that the guide grants a different approval rule.
2. **Keep the two listing flows distinct.** C:139–142 describes a particular simple-intake route. The NPP path checks tagged approvals and its own state/grammar, with `?` special-cased for retry (R2–R3). Also, C:4 and C:29 differ on bare-yes scope; `Route:1392–1405,1439–1448` gives context and code-required checks. These are documentation observations, not proposals to change approval or intake behavior.
3. **Discoverability.** Exact forms missing from the three guides include `notes`, the extra read-question forms and additional near-yes forms in R1. C:50,266 gives the coded `show` and mentions bare `show` without explaining its selection. The C:8 exclusivity statement is broader than its main table; C:76–104 and C:128–142 themselves document other routes. The shorter guides intentionally link to C rather than duplicate it (N:7–8; P:104).

**One possible follow-up, estimated 45–75 minutes, not started:** reconcile only the undo/cancel examples in `docs/hass/NATURAL_LANGUAGE.md` against the existing direct and reader-only forms. Proposed scope is that file alone; no runtime change, and no wording or owner decision here. Offline test: rerun `python3 -B -m unittest hass.tests.test_commands_doc` from the repo root, and compare the edited N:73–74 entries against X:15–17,130–138,215–223 and Route:1392–1430,2702–2739. Use `undo that`/`never mind` as direct controls, `take it back`/`scratch that` as non-matching controls. The existing test does not assert the N guide text; the comparison is a separate acceptance check.

### Reproduce the audit

Run in the cloned repo. `nl -ba` preserves the line anchors used above; add the individual handler, guide and outside-route paths named in the tables to inspect those files.

```text
git rev-parse origin/main
git ls-tree -r --name-only origin/main -- hass/chat
nl -ba hass/chat/commands.py
nl -ba hass/conversation.py
nl -ba docs/hass/COMMANDS.md
nl -ba docs/hass/NATURAL_LANGUAGE.md
nl -ba docs/hass/PHONE_GUIDE.md
nl -ba docs/hass/NPP-EDIT-PHRASES.md
python3 -B -m unittest hass.tests.test_commands_doc
```

Actual offline result on 2026-11-21: the workspace-only `python3 -B probe.py` ran the same `hass.tests.test_commands_doc` suite under a socket/subprocess-denying audit hook: `Ran 15 tests` / `OK` (exit 0). It counted 43 command-table rows and printed the 27 outcomes from the test's `parser_verbs()` helper (not a count of distinct phrases). It checked the class order and disjoint pack methods; `show`, `shelf?`, `look?`, `backlog?`, `notes?`, the undo/cancel pairs in R2, the three status-like reader examples, `What's next`, `photos to take?` and `help post hike` were parser-only positive/negative controls, not live messages. No handlers were executed against a site, till or host. The test's sampling and its main-table scope (`hass/tests/test_commands_doc.py:17–43`) do not establish full alias coverage or verify either secondary guide.
