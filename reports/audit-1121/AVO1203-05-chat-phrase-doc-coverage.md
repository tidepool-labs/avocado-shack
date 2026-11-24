# Hass chat phrase coverage — AVO1203-05

| Area | What the offline check found |
|---|---|
| Fixed commands | The concrete examples in the owner card's command table reach their advertised command syntax. A syntax hit is not a successful lookup, approval, or write. The card's closing-`?` list omits three command families (`COMMANDS.md:12`; `hass/chat/commands.py:288–310`). |
| Natural-language guidance | `undo that` and `never mind` are fixed aliases, not just requests for instructions. `did it go up?`, `is it live`, `what's waiting`, `take it back`, and `scratch that` have no fixed command match; that does not establish what an interpreter would return (`NATURAL_LANGUAGE.md:70–77`; `hass/chat/commands.py:15–21`; `hass/interpreter_prompt.py:127–131`). |
| New listings | The simple preview and the versioned listing card use different edit readers. `add: great for furniture` is recognized by both but does not produce a local description patch in the versioned reader; `name Wood Glue`, `brand Gorilla`, `category pantry`, and `remove Made in USA` are simple-preview forms in this replay (`COMMANDS.md:139–142`; `hass/skills/intake_simple.py:146–175`; `hass/npp/edits.py:162–192,255–271`). |
| Clover count baseline | Standalone count parser: **37/60 exact**. Of the 19 printed positive gaps, 13 return no count and six return the wrong intent or query. All four printed negatives still return an intent. This is not the chat till parser (`CLOVER-COUNT-PHRASES.md:3–4,26–51`; `hass/clover/qty_words.py:85–107`; `hass/clover/chat.py:139–172`). |

**Source:** public `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, checked 2026-11-21 Pacific; identical to the task baseline. Document names without paths below are relative to `docs/hass/`. `git ls-tree -r --name-only origin/main -- '*G-QUESTIONS.md'` returned no path. This audit keeps the task's stated boundaries: no decisions about model data, what can happen without a yes, transport, or procedures by text. Nothing here changes parser code, policy, caps, timers, or content.

## R1. Documented phrases and what matches

**Replay:** from the pinned clone, with the attached `phrase_replay.py` one level above the clone, run `python3 -B ../phrase_replay.py`. The scratch script selects the input examples from the Markdown tables and prose, de-duplicates identical spellings within each doc, and binds angle-bracket operands to explicit fixtures. It calls the actual command, memory, keyword, phone, near-control, typo, social, count, simple preview and NPP edit readers. It loads the three tracked NPP edit assets directly, with no mapper and no finance provided to `edits.read`. The card-turn check uses the real `Stages.takes_turn` at `card_out`; it is not an edit result and does not override an already matched command. For the natural-language page it also calls the date/time hint helpers with a fixed Monday. Till syntax and report operands are checked against the code's patterns; no till, catalog lookup, journal, conversation handler, settings or other runtime state is used. The script traps network, subprocess and database-connect audit events and asserts zero attempts. All amounts and quantities in the tables are document examples or parser fixtures, not observed prices or stock.

**Reading the tables:** `no match` means no applicable fixed phrase in this audit, not “Hass cannot understand it.” `shape`, `syntax`, `hint`, `ask`, and `lookup-gated` are not successful actions. Unrecognized free-form text can go to the request reader (`hass/conversation.py:1383–1386`); an active listing or question may instead take the turn (`hass/conversation.py:1280–1285,1503–1556`). Reply text, site labels, operation IDs, individual punctuation marks, and incomplete prose stems are not standalone owner messages. Argument options are checked on complete examples below. The two fixture-baseline docs are not promises that all their examples work.

### COMMANDS

| Document line(s) | Example | Offline result |
|---|---|---|
| 4, 9, 22 | `yes a1b2` | approve keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`); NPP YES shape (job-gated) (`hass/npp/job.py:53`) |
| 4, 12, 29, 88, 102, 174, 181, 206, 208 | `yes` | approve keyword (`hass/chat/commands.py:17`) |
| 4, 12, 31, 88, 102, 174, 181, 208 | `no` | reject keyword (`hass/chat/commands.py:17`); NPP NO shape (job-gated) (`hass/npp/job.py:54`) |
| 9, 28 | `YES A1B2` | approve keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`); NPP YES shape (job-gated) (`hass/npp/job.py:53`) |
| 9 | `A1B2` | phone hint (`hass/chat/commands.py:156`) |
| 12, 182 | `remember` | remember (`hass/chat/commands.py:123`) |
| 12, 182 | `forget` | no match |
| 12, 39 | `Status.` | status (`hass/chat/commands.py:20`) |
| 12 | `Memory.` | memory (`hass/chat/commands.py:123`) |
| 12, 54 | `post maker <key>` | fixture `post maker fixture-farm` → maker key first (`hass/chat/commands.py:184`); post reserved (`hass/chat/commands.py:25`) |
| 12, 65, 141 | `?` | help (`hass/chat/commands.py:21`); simple preview repeat (`hass/skills/intake_simple.py:14`) |
| 12, 39, 40, 179 | `status` | status (`hass/chat/commands.py:20`) |
| 12, 34, 179 | `history` | history (`hass/chat/commands.py:19`) |
| 12, 51, 179 | `report` | report (`hass/chat/commands.py:24`) |
| 12, 45 | `memory` | memory (`hass/chat/commands.py:123`) |
| 12 | `find` | find (`hass/chat/commands.py:22`) |
| 12 | `show` | show (`hass/chat/commands.py:23`) |
| 12, 52 | `post` | post (`hass/chat/commands.py:25`) |
| 12, 63 | `listing` | listing (`hass/chat/commands.py:28`) |
| 12, 60, 180 | `hidden` | hidden (`hass/chat/commands.py:27`) |
| 12, 61 | `held` | held (`hass/chat/commands.py:34`); typo hint (shadowed): help (`hass/conversation.py:115`) |
| 12 | `margin` | margin (`hass/chat/commands.py:26`); operand: usage only |
| 12, 48 | `costs` | costs (`hass/chat/commands.py:33`); typo hint (shadowed): cost (`hass/conversation.py:115`) |
| 12, 65 | `help` | help (`hass/chat/commands.py:21`) |
| 12 | `status?` | status (`hass/chat/commands.py:20`) |
| 12 | `find eggs?` | find (`hass/chat/commands.py:22`) |
| 12 | `show a1b2?` | show (`hass/chat/commands.py:23`) |
| 12, 36, 125, 142, 181 | `undo` | undo (`hass/chat/commands.py:19`) |
| 12, 41, 182 | `stop` | pause (`hass/chat/commands.py:20`); control hint (shadowed) (`hass/conversation.py:90`) |
| 12, 42, 182 | `resume` | resume (`hass/chat/commands.py:21`); control hint (shadowed) (`hass/conversation.py:90`) |
| 12, 182 | `alias` | alias (`hass/chat/commands.py:123`) |
| 15, 43 | `remember <key>: <text>` | fixture `remember fixture-farm: fixture note` → remember (`hass/chat/commands.py:123`) |
| 16, 44 | `forget <key>` | fixture `forget fixture-farm` → forget (`hass/chat/commands.py:123`) |
| 16 | `forget parking.` | forget (`hass/chat/commands.py:123`) |
| 17 | `forget parking` | forget (`hass/chat/commands.py:123`) |
| 18 | `remember Parking Spot: use the back lot` | remember (`hass/chat/commands.py:123`) |
| 19, 44 | `forget parking spot` | forget (`hass/chat/commands.py:123`) |
| 20 | `forget it` | forget (`hass/chat/commands.py:123`) |
| 20 | `forget it all` | no match |
| 22 | `Yes, a1b2` | phone code (`hass/chat/commands.py:156`) |
| 22 | `yes a1b2 thanks` | phone code (`hass/chat/commands.py:156`) |
| 22 | `A1B2 yes` | phone code (`hass/chat/commands.py:156`) |
| 22 | `no a1b2 please` | phone code (`hass/chat/commands.py:156`) |
| 22 | `no a1b2` | reject keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`); NPP NO shape (job-gated) (`hass/npp/job.py:54`) |
| 22 | `yes but make it 10am` | no match |
| 22 | `no, 5pm` | no match |
| 24 | `yes a1b2?` | phone hint (`hass/chat/commands.py:156`) |
| 24 | `no a1b2?` | phone hint (`hass/chat/commands.py:156`) |
| 24 | `a1b2 yes?` | phone hint (`hass/chat/commands.py:156`) |
| 24 | `yes?` | phone hint (`hass/chat/commands.py:156`) |
| 24 | `no?` | phone hint (`hass/chat/commands.py:156`) |
| 24 | `a1b2` | phone hint (`hass/chat/commands.py:156`) |
| 24 | `a1b2?` | phone hint (`hass/chat/commands.py:156`) |
| 28, 88, 101, 125, 142, 210, 214 | `yes <code>` | fixture `yes a1b2` → approve keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`); NPP YES shape (job-gated) (`hass/npp/job.py:53`); 8-character till fixture `yes a1b2c3d4` → approve keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`); till code shape (journal-gated) (`hass/clover/chat.py:32`); NPP YES shape (job-gated) (`hass/npp/job.py:53`) |
| 28 | `approve <code>` | fixture `approve a1b2` → approve keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`) |
| 28 | `approved <code>` | fixture `approved a1b2` → approve keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`) |
| 29 | `approve` | approve keyword (`hass/chat/commands.py:17`) |
| 29 | `approved` | approve keyword (`hass/chat/commands.py:17`) |
| 30, 88 | `no <code>` | fixture `no a1b2` → reject keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`); NPP NO shape (job-gated) (`hass/npp/job.py:54`); 8-character till fixture `no a1b2c3d4` → reject keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`); till code shape (journal-gated) (`hass/clover/chat.py:32`); NPP NO shape (job-gated) (`hass/npp/job.py:54`) |
| 30 | `cancel <code>` | fixture `cancel a1b2` → reject keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`); NPP NO shape (job-gated) (`hass/npp/job.py:54`) |
| 30 | `reject <code>` | fixture `reject a1b2` → reject keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`) |
| 30 | `cancel A1B2` | reject keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`); NPP NO shape (job-gated) (`hass/npp/job.py:54`) |
| 31 | `cancel` | reject keyword (`hass/chat/commands.py:17`); NPP NO shape (job-gated) (`hass/npp/job.py:54`) |
| 31 | `reject` | reject keyword (`hass/chat/commands.py:17`) |
| 31 | `cancel that` | cancel alias (`hass/chat/commands.py:16`) |
| 31 | `cancel it` | cancel alias (`hass/chat/commands.py:16`) |
| 31 | `never mind` | cancel alias (`hass/chat/commands.py:16`) |
| 31 | `nevermind` | cancel alias (`hass/chat/commands.py:16`) |
| 32 | `no all` | bulk reject (`hass/chat/commands.py:127`) |
| 32 | `cancel all` | bulk reject (`hass/chat/commands.py:127`) |
| 32 | `cancel everything` | bulk reject (`hass/chat/commands.py:127`) |
| 33 | `yes all` | bulk approve (`hass/chat/commands.py:127`) |
| 33 | `approve all` | bulk approve (`hass/chat/commands.py:127`) |
| 35 | `history <words>` | fixture `history eggs` → history (`hass/chat/commands.py:19`) |
| 35 | `history opening hours` | history (`hass/chat/commands.py:19`) |
| 36 | `undo that` | undo alias (`hass/chat/commands.py:15`) |
| 36 | `undo it` | undo alias (`hass/chat/commands.py:15`) |
| 36 | `undo last` | undo alias (`hass/chat/commands.py:15`) |
| 36 | `undo the last change` | undo alias (`hass/chat/commands.py:15`) |
| 36 | `please undo` | undo alias (`hass/chat/commands.py:15`) |
| 37, 89 | `undo <code>` | fixture `undo a1b2` → undo (`hass/chat/commands.py:19`); 8-character till fixture `undo a1b2c3d4` → undo (`hass/chat/commands.py:19`); till code shape (journal-gated) (`hass/clover/chat.py:32`) |
| 37 | `undo A1B2!` | undo (`hass/chat/commands.py:19`) |
| 38 | `again <code>` | fixture `again a1b2` → again (`hass/chat/commands.py:31`) |
| 38 | `again A1B2` | again (`hass/chat/commands.py:31`) |
| 40 | `did it work?` | status (`hass/chat/commands.py:20`) |
| 40 | `did that work?` | status (`hass/chat/commands.py:20`) |
| 40 | `did my change work?` | status (`hass/chat/commands.py:20`) |
| 41, 93 | `stop changes` | pause (`hass/chat/commands.py:20`); control hint (shadowed) (`hass/conversation.py:90`) |
| 41 | `pause` | pause (`hass/chat/commands.py:20`); control hint (shadowed) (`hass/conversation.py:90`) |
| 41 | `pause changes` | pause (`hass/chat/commands.py:20`); control hint (shadowed) (`hass/conversation.py:90`) |
| 42 | `resume changes` | resume (`hass/chat/commands.py:21`); control hint (shadowed) (`hass/conversation.py:90`) |
| 43 | `remember parking: use the back lot` | remember (`hass/chat/commands.py:123`) |
| 46 | `alias <name>: <product or maker>` | fixture `alias vegetables: fixture farm` → alias (`hass/chat/commands.py:123`) |
| 46 | `alias green jam: Linn's blueberry preserves` | alias (`hass/chat/commands.py:123`) |
| 46 | `forget alias <name>` | fixture `forget alias vegetables` → forget (`hass/chat/commands.py:123`) |
| 46 | `the green jam is sold out` | till sold_out shape (exact item needed) (`hass/clover/chat.py:29`) |
| 47 | `cost <product>: <pack cost> for <units>` | fixture `cost fixture product: 24.00 for 12` → cost (`hass/chat/commands.py:123`); cost operand (`hass/chat/reports_pack.py:39`) |
| 47 | `cost Hass avocado: 24 for 12` | cost (`hass/chat/commands.py:123`); cost operand (`hass/chat/reports_pack.py:39`) |
| 47 | `cost green jam: 24 for 12` | cost (`hass/chat/commands.py:123`); cost operand (`hass/chat/reports_pack.py:39`) |
| 47 | `forget cost.<product id>` | fixture `forget cost.fixture-product` → forget (`hass/chat/commands.py:123`) |
| 47 | `remember cost...` | remember (`hass/chat/commands.py:123`) |
| 49, 179 | `find <words>` | fixture `find eggs` → find (`hass/chat/commands.py:22`) |
| 49 | `find lion's mane` | find (`hass/chat/commands.py:22`) |
| 50 | `show <code>` | fixture `show a1b2` → show (`hass/chat/commands.py:23`) |
| 50 | `show A1B2` | show (`hass/chat/commands.py:23`) |
| 51 | `morning report` | report (`hass/chat/commands.py:24`) |
| 52 | `post <product>` | fixture `post fixture product` → post syntax; lookup-gated (`hass/chat/commands.py:25`) |
| 52 | `post Hass avocado` | post syntax; lookup-gated (`hass/chat/commands.py:25`) |
| 52 | `post green jam` | post syntax; lookup-gated (`hass/chat/commands.py:25`) |
| 52 | `alias green jam: <id>` | fixture `alias green jam: fixture-product` → alias (`hass/chat/commands.py:123`) |
| 52 | `post about the porch walk recap` | post syntax; lookup-gated (`hass/chat/commands.py:25`) |
| 53 | `post hike <hike>` | fixture `post hike Point Buchon` → post syntax; lookup-gated (`hass/chat/commands.py:25`) |
| 53 | `post hike Point Buchon` | post syntax; lookup-gated (`hass/chat/commands.py:25`) |
| 54 | `post maker fixture-farm` | maker key first (`hass/chat/commands.py:184`); post reserved (`hass/chat/commands.py:25`) |
| 54 | `post maker Linn's` | maker key first (`hass/chat/commands.py:184`); post reserved (`hass/chat/commands.py:25`) |
| 54 | `post maker linn's` | maker key first (`hass/chat/commands.py:184`); post reserved (`hass/chat/commands.py:25`) |
| 55 | `post notice` | post (`hass/chat/commands.py:25`) |
| 56 | `margin <pack cost> for <units> at <margin>%` | fixture `margin 24.00 for 12 at 35%` → margin (`hass/chat/commands.py:26`); MARGIN_RE (`hass/chat/reports_pack.py:34`) |
| 56 | `margin 24.00 for 12 at 35%` | margin (`hass/chat/commands.py:26`); MARGIN_RE (`hass/chat/reports_pack.py:34`) |
| 57 | `margin <pack cost> for <units> price <P>` | fixture `margin 24.00 for 12 price 3.49` → margin (`hass/chat/commands.py:26`); PRICE_RE (`hass/chat/reports_pack.py:37`) |
| 57 | `margin 24.00 for 12 price 3.49` | margin (`hass/chat/commands.py:26`); PRICE_RE (`hass/chat/reports_pack.py:37`) |
| 58 | `margin <product> at <margin>%` | fixture `margin fixture product at 35%` → margin (`hass/chat/commands.py:26`); MARGIN_ID_RE (`hass/chat/reports_pack.py:35`) |
| 58 | `margin Hass avocado at 35%` | margin (`hass/chat/commands.py:26`); MARGIN_ID_RE (`hass/chat/reports_pack.py:35`) |
| 58 | `margin sourdough at 35%` | margin (`hass/chat/commands.py:26`); MARGIN_ID_RE (`hass/chat/reports_pack.py:35`) |
| 59 | `margin <product> price <P>` | fixture `margin fixture product price 3.49` → margin (`hass/chat/commands.py:26`); PRICE_ID_RE (`hass/chat/reports_pack.py:38`) |
| 59 | `margin Hass avocado price 3.49` | margin (`hass/chat/commands.py:26`); PRICE_ID_RE (`hass/chat/reports_pack.py:38`) |
| 60 | `Bring back <name>` | fixture `Bring back vegetables` → no match |
| 62 | `look` | look (`hass/chat/commands.py:200`) |
| 62 | `look hike` | look (`hass/chat/commands.py:200`) |
| 62 | `look <product>` | fixture `look fixture product` → look (`hass/chat/commands.py:200`) |
| 63 | `listing <name>` | fixture `listing vegetables` → listing (`hass/chat/commands.py:28`) |
| 63 | `listing Etto` | listing (`hass/chat/commands.py:28`) |
| 63 | `listing sourdough` | listing (`hass/chat/commands.py:28`) |
| 64 | `photos to take` | photos (`hass/chat/commands.py:29`) |
| 65 | `commands` | help (`hass/chat/commands.py:21`) |
| 65 | `what can you do` | help (`hass/chat/commands.py:21`) |
| 65 | `what do you do` | help (`hass/chat/commands.py:21`) |
| 65 | `what can I say` | help (`hass/chat/commands.py:21`) |
| 65, 66 | `help undo` | help detail (`hass/chat/commands.py:118`) |
| 66 | `help <command>` | fixture `help undo` → help detail (`hass/chat/commands.py:118`) |
| 66 | `help yes` | help detail (`hass/chat/commands.py:118`) |
| 66 | `help stop changes` | help detail (`hass/chat/commands.py:118`) |
| 66 | `help photos to take` | help detail (`hass/chat/commands.py:118`) |
| 66 | `help a1b2` | help unknown name (`hass/chat/commands.py:118`) |
| 66 | `help remember` | help detail (`hass/chat/commands.py:118`) |
| 66 | `help me with avocados` | no match |
| 67 | `listing store` | listing (`hass/chat/commands.py:28`) |
| 68, 180 | `shelf <name>` | fixture `shelf vegetables` → shelf (`hass/chat/commands.py:32`) |
| 68 | `shelf vegetables` | shelf (`hass/chat/commands.py:32`) |
| 68 | `shelf dairy & cheese` | shelf (`hass/chat/commands.py:32`) |
| 69 | `backlog` | backlog (`hass/chat/commands.py:30`) |
| 70 | `forget backlog.<n>` | fixture `forget backlog.3` → forget (`hass/chat/commands.py:123`); backlog key (`hass/chat/core_pack.py:274`) |
| 70 | `forget backlog.3` | forget (`hass/chat/commands.py:123`); backlog key (`hass/chat/core_pack.py:274`) |
| 82 | `received 12 Sunshine olive oil` | till received shape (`hass/clover/chat.py:26`); standalone count: add (`hass/clover/qty_words.py:21`) |
| 83 | `set Sunshine olive oil to 7` | till set shape (`hass/clover/chat.py:28`); standalone count: set (`hass/clover/qty_words.py:20`) |
| 83 | `set Sunshine olive oil to 0` | till set shape (`hass/clover/chat.py:28`); standalone count: set (`hass/clover/qty_words.py:20`) |
| 84 | `Sunshine olive oil is sold out` | till sold_out shape (exact item needed) (`hass/clover/chat.py:29`) |
| 85 | `new item: Sunshine olive oil, 12.50, pantry` | till new shape (`hass/clover/chat.py:30`) |
| 86 | `change price of Sunshine olive oil to 14.00` | till price shape (`hass/clover/chat.py:27`) |
| 87 | `hide Sunshine olive oil on the till` | till hide shape (`hass/clover/chat.py:31`) |
| 87 | `show Sunshine olive oil on the till` | show (`hass/chat/commands.py:23`); till hide shape (`hass/clover/chat.py:31`) |
| 107 | `cancel the Point Buchon hike, rained out - we will pick a new date soon` | no match |
| 124 | `Add Test Orchard quince, brand Test Orchard` | no match |
| 131 | `bought 100 at $1, sell for $2` | simple finance: qty, cost, price (`hass/skills/item_intake.py:189–191`) |
| 139 | `remove Made in USA` | simple edit: description (`hass/skills/intake_simple.py:146`) |
| 139 | `add: great for furniture` | NPP add (`hass/npp/assets/hass-listing-edit/edit-grammar.json:52`); NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`); simple edit: description (`hass/skills/intake_simple.py:171`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 139 | `price 3` | simple finance: price (`hass/skills/item_intake.py:189–191`) |
| 139 | `name Wood Glue` | simple edit: name, image_alt (`hass/skills/intake_simple.py:154`) |
| 140 | `brand Gorilla` | simple edit: maker (`hass/skills/intake_simple.py:158`) |
| 140 | `category pantry` | simple edit: shelf (`hass/skills/intake_simple.py:162`) |
| 141 | `What's next` | simple preview repeat (`hass/skills/intake_simple.py:14`) |
| 160 | `skip` | intake skip shape (slot-gated; not a test of maker story) (`hass/skills/item_intake.py:40`) |
| 164 | `thanks` | social (`hass/social_message.py:125`) |
| 164 | `thank you` | social (`hass/social_message.py:125`) |
| 164 | `great, thanks` | social (`hass/social_message.py:125`) |
| 164 | `hi` | social (`hass/social_message.py:125`) |
| 164 | `hello` | social (`hass/social_message.py:125`) |
| 164 | `good morning` | social (`hass/social_message.py:125`) |
| 168 | `thanks, make the eggs sold out` | till sold_out shape (exact item needed) (`hass/clover/chat.py:29`) |
| 170 | `histroy` | typo hint: history (`hass/conversation.py:115`) |
| 170 | `staus` | typo hint: status (`hass/conversation.py:115`) |
| 170 | `reprot` | typo hint: report (`hass/conversation.py:115`) |
| 170 | `memroy` | typo hint: memory (`hass/conversation.py:115`) |
| 170 | `undp` | typo hint: undo (`hass/conversation.py:115`) |
| 172 | `stow` | typo hint: show / stop (`hass/conversation.py:115`) |
| 174 | `fine` | no match |
| 174 | `shop` | no match |
| 174 | `past` | no match |
| 174 | `most` | no match |
| 174 | `hold` | no match |
| 178 | `how many are coming Saturday?` | till read shape HOW_MANY (lookup/guards) (`hass/clover/chat.py:91`) |
| 178 | `is the sourdough sold out?` | till read shape IN_STOCK (lookup/guards) (`hass/clover/chat.py:94`) |
| 178 | `what's on the dairy shelf?` | no match |
| 178 | `what are my hours?` | no match |
| 180 | `listing <id or store>` | fixture `listing store` → listing (`hass/chat/commands.py:28`) |
| 184 | `can you mark the eggs sold out?` | no match |
| 194 | `I checked the selection today: the avocados are in, the eggs are limited, the sourdough is sold out.` | till sold_out shape (exact item needed) (`hass/clover/chat.py:29`) |
| 199 | `the eggs are sold out` | till sold_out shape (exact item needed) (`hass/clover/chat.py:29`) |
| 212 | `stop showing the eggs as sold out` | till sold_out shape (exact item needed) (`hass/clover/chat.py:29`) |
| 217 | `all the vegetables are in today` | no match |
| 217 | `everything from Cal Poly is sold out` | till sold_out shape (exact item needed) (`hass/clover/chat.py:29`) |
| 244 | `put the old photo back` | no match |
| 249 | `change the hiking club intro to: Mornings on the coast are for friends, fresh bread and a long walk.` | no match |
| 259 | `we stopped carrying Etto` | no match |
| 264 | `forget design.<n>` | fixture `forget design.3` → forget (`hass/chat/commands.py:123`) |

### NPP-EDIT-PHRASES

| Document line(s) | Example | Offline result |
|---|---|---|
| 3 | `add: great on toast` | NPP add (`hass/npp/assets/hass-listing-edit/edit-grammar.json:52`); NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`); simple edit: description (`hass/skills/intake_simple.py:171`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 10, 27 | `call it "Wildflower Honey"` | NPP name (`hass/npp/assets/hass-listing-edit/edit-grammar.json:34`); NPP result: name (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 10 | `call it Wildflower Honey` | NPP name (`hass/npp/assets/hass-listing-edit/edit-grammar.json:34`); NPP result: name (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 11, 36 | `use the photo I just sent` | NPP picture (`hass/npp/assets/hass-listing-edit/edit-grammar.json:62`); NPP result: picture_request (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 13, 23 | `make it four bucks` | NPP named amount (`hass/skills/intake_simple.py:30`); NPP result: ask_price (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 13, 26, 61 | `per pound please` | NPP lone unit (`hass/npp/edits.py:55`); NPP result: ask_price (`hass/npp/edits.py:162–192,255–271`) |
| 21 | `make it 4 bucks` | NPP named amount (`hass/skills/intake_simple.py:30`); NPP result: ask_price (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 22 | `$4.50 a pound` | NPP named amount (`hass/skills/intake_simple.py:30`); NPP result: ask_price (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 24 | `four dollars and fifty cents a pound` | NPP named amount (`hass/skills/intake_simple.py:30`); NPP result: ask_price (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 25 | `sell it for five dollars each` | NPP named amount (`hass/skills/intake_simple.py:30`); NPP result: ask_price (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 28 | `rename it to Orchard Honey` | NPP name (`hass/npp/assets/hass-listing-edit/edit-grammar.json:34`); NPP result: name (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 29 | `call it Wildflower Honey!` | NPP name (`hass/npp/assets/hass-listing-edit/edit-grammar.json:34`); NPP result: name (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 30 | `swap the supplier to Lantern Kitchen` | NPP supplier (`hass/npp/assets/hass-listing-edit/edit-grammar.json:16`); NPP result: supplier (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 31 | `shorter please` | NPP wording (`hass/npp/assets/hass-listing-edit/edit-grammar.json:73`); NPP result: rewrite (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 32 | `make the description a little shorter` | NPP wording (`hass/npp/assets/hass-listing-edit/edit-grammar.json:73`); NPP result: rewrite (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 33 | `move that to dairy` | NPP category (`hass/npp/assets/hass-listing-edit/edit-grammar.json:43`); NPP result: category (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 34 | `put it under fruit please` | NPP category (`hass/npp/assets/hass-listing-edit/edit-grammar.json:43`); NPP result: category (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 35 | `use my photo please` | NPP picture (`hass/npp/assets/hass-listing-edit/edit-grammar.json:62`); NPP result: picture_request (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 44 | `each not per lb` | no match; NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`) |
| 45 | `actually 4 or 5 bucks` | no match; NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`) |
| 46 | `it's Miners' honey` | no match; NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`) |
| 47 | `no maker` | no match; NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`) |
| 48 | `leave the maker blank` | no match; NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`) |
| 49 | `take the source off` | no match; NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`) |
| 50 | `make it 2 lines shorter` | no match; NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 51 | `say it's nice with tea on a cold day` | NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`); simple edit: description (`hass/skills/intake_simple.py:171`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 52 | `category: snacks` | no match; NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`) |
| 53 | `use photo 2` | no match; NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 54 | `asdf hjkl` | no match; NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`) |
| 55 | `what did you put for the maker` | no match; NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`) |
| 56 | `Hass, is this on the site yet?` | no match; NPP result: ask_edit_unclear (`hass/npp/edits.py:162–192,255–271`) |
| 60 | `call it Wildflower Honey please` | NPP name (`hass/npp/assets/hass-listing-edit/edit-grammar.json:34`); NPP result: name (`hass/npp/edits.py:162–192,255–271`); simple edit: name, image_alt (`hass/skills/intake_simple.py:154`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |
| 60 | `from Etto please` | NPP supplier (`hass/npp/assets/hass-listing-edit/edit-grammar.json:16`); NPP result: supplier (`hass/npp/edits.py:162–192,255–271`); simple supplier shape; asks (`hass/skills/intake_simple.py:177`); NPP card turn eligible (`hass/npp/reply.py:91–103`) |

### CLOVER-COUNT-PHRASES

| Document line(s) | Example | Offline result |
|---|---|---|
| 26 | `12 apricot jams just came in` | standalone count: add (`hass/clover/qty_words.py:101`); wrong parse (lookup query `apricot jams just`) |
| 27 | `30 blue mugs in` | standalone count: count (`hass/clover/qty_words.py:103`); wrong parse (lookup query `blue mugs in`) |
| 28 | `the glass pitchers just arrived, 9 of them` | no match |
| 29 | `blue mug x30` | no match |
| 30 | `x14 linen bags` | no match |
| 31 | `pan scrapers = 11` | no match |
| 32 | `+7 lemon soaps` | no match |
| 33 | `we have 4lb of dried cherries` | no match |
| 34 | `just got 6 lb of split peas` | no match |
| 35 | `we have 15 each of the wax wraps` | standalone count: count (`hass/clover/qty_words.py:103`); wrong parse (lookup query `each of the wax wraps`) |
| 36 | `we got a dozen and a half cake boxes` | standalone count: add (`hass/clover/qty_words.py:21`); wrong parse (lookup query `and a half cake boxes`) |
| 37 | `a hundred and six paper straws` | no match |
| 38 | `put 30 mugs on the shelf` | no match |
| 39 | `only 4 cedar soap dishes left` | no match |
| 40 | `we have 18 cork trivets in stock` | standalone count: count (`hass/clover/qty_words.py:103`); wrong parse (lookup query `cork trivets in stock`) |
| 41 | `on the shelf there's 7 butter crocks` | no match |
| 42 | `recevied 8 maple spreaders` | no match |
| 43 | `there re 5 mixing bowls` | no match |
| 44 | `5 bown sugar scoops on the slehf` | standalone count: count (`hass/clover/qty_words.py:103`); wrong parse (lookup query `bown sugar scoops on the slehf`) |
| 48 | `12 bucks for the tea tin` | standalone count: count (`hass/clover/qty_words.py:103`); false accept (lookup query `bucks for the tea tin`) |
| 49 | `6 cloth bags and a fruit basket` | standalone count: count (`hass/clover/qty_words.py:103`); false accept (lookup query `cloth bags and a fruit basket`) |
| 50 | `9 miles for the ridge hike` | standalone count: count (`hass/clover/qty_words.py:103`); false accept (lookup query `miles for the ridge hike`) |
| 51 | `set the website photo of the wooden ladle to 3` | till set shape (`hass/clover/chat.py:28`); standalone count: set (`hass/clover/qty_words.py:20`); false accept (lookup query `website photo of the wooden ladle`) |

### NATURAL_LANGUAGE

| Document line(s) | Example | Offline result |
|---|---|---|
| 4, 7 | `yes` | approve keyword (`hass/chat/commands.py:17`) |
| 5 | `a1b2` | phone hint (`hass/chat/commands.py:156`) |
| 7, 21 | `no` | reject keyword (`hass/chat/commands.py:17`); NPP NO shape (job-gated) (`hass/npp/job.py:54`) |
| 7, 21, 72 | `status` | status (`hass/chat/commands.py:20`) |
| 7, 73 | `undo` | undo (`hass/chat/commands.py:19`) |
| 7, 90 | `help` | help (`hass/chat/commands.py:21`) |
| 15 | `honey is sold out` | till sold_out shape (exact item needed) (`hass/clover/chat.py:29`) |
| 17 | `the big sur one` | no match |
| 26 | `can you change the shop hours to 9 to 5 on saturdays` | no match; date hint only (`hass/nl_prep.py:434–493`): saturday |
| 33 | `eggs are out` | no match |
| 33 | `egs r sold out again lol` | no match |
| 33 | `no more strawberries today` | no match; date hint only (`hass/nl_prep.py:434–493`): today |
| 34 | `avocados limited today` | no match; date hint only (`hass/nl_prep.py:434–493`): today |
| 34 | `peppers running low` | no match |
| 35 | `lemons are back` | no match |
| 35 | `got more honey in` | no match |
| 36 | `bread is gone` | no match |
| 38 | `checked the shelves: avocados in, eggs limited, bread sold out` | till sold_out shape (exact item needed) (`hass/clover/chat.py:29`) |
| 40 | `hide the plums` | no match |
| 40 | `take the cashews off the site` | no match |
| 40 | `bring back the lemons` | no match |
| 42 | `December 5 2027` | no match; date hint only (`hass/nl_prep.py:434–493`): december 5 2027 |
| 42 | `12/5/27` | no match; date hint only (`hass/nl_prep.py:434–493`): 12/5/27 |
| 42 | `2027-12-05` | no match; date hint only (`hass/nl_prep.py:434–493`): 2027-12-05 |
| 42 | `February 30 2027` | no match |
| 42 | `December 5 202` | no match |
| 44 | `post a hike at Cass Hill on Saturday at 9, meet at the trailhead gate` | post syntax; lookup-gated (`hass/chat/commands.py:25`); date hint only (`hass/nl_prep.py:434–493`): saturday |
| 45 | `add a hike Saturday at 8am, Mill Creek trailhead, easy, bring water` | no match; date hint only (`hass/nl_prep.py:434–493`): saturday; time hint only (`hass/nl_prep.py:496–507`): 8am |
| 47 | `create a new hike on Fiscalini Ranch this Saturday at 8am` | no match; date hint only (`hass/nl_prep.py:434–493`): this saturday; time hint only (`hass/nl_prep.py:496–507`): 8am |
| 48 | `cancel the Point Buchon walk, it's raining` | no match |
| 49 | `move Saturday's hike to 8:30` | no match; date hint only (`hass/nl_prep.py:434–493`): saturday; time hint only (`hass/nl_prep.py:496–507`): 8:30 |
| 49 | `do the Cass Hill hike again on the 29th at 9` | no match; date hint only (`hass/nl_prep.py:434–493`): 29th |
| 50 | `recap: 12 people, great morning` | no match |
| 52 | `next Saturday` | no match; date hint only (`hass/nl_prep.py:434–493`): next saturday |
| 54 | `we're open till 7 on fridays now` | no match; date hint only (`hass/nl_prep.py:434–493`): friday |
| 54 | `winter hours: 10 to 4 every day` | no match |
| 54 | `we're closed Thanksgiving` | no match; date hint only (`hass/nl_prep.py:434–493`): thanksgiving |
| 60 | `actually make that 10am` | no match; time hint only (`hass/nl_prep.py:496–507`): 10am |
| 60 | `wednesday instead` | no match; date hint only (`hass/nl_prep.py:434–493`): wednesday |
| 60 | `not strawberries, the raspberries` | no match |
| 64 | `eggs out, bread limited, and hide the plums` | no match |
| 72 | `did it go up?` | no match |
| 72 | `is it live` | no match |
| 72 | `what's waiting` | no match |
| 73 | `undo that` | undo alias (`hass/chat/commands.py:15`) |
| 73 | `take it back` | no match |
| 74 | `never mind` | cancel alias (`hass/chat/commands.py:16`) |
| 74 | `scratch that` | no match |
| 74 | `no a1b2` | reject keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`); NPP NO shape (job-gated) (`hass/npp/job.py:54`) |
| 75 | `ok` | near-approval hint (`hass/chat/commands.py:18`) |
| 75 | `go ahead` | near-approval hint (`hass/chat/commands.py:18`) |
| 75 | `looks good` | near-approval hint (`hass/chat/commands.py:18`) |
| 75 | `yes a1b2` | approve keyword (`hass/chat/commands.py:17`); phone code (`hass/chat/commands.py:156`); NPP YES shape (job-gated) (`hass/npp/job.py:53`) |
| 76 | `what time do we close saturday?` | no match; date hint only (`hass/nl_prep.py:434–493`): saturday |
| 76 | `when's the next hike?` | no match |
| 77 | `thanks` | social (`hass/social_message.py:125`) |
| 85 | `same as last time` | no match |
| 85 | `make it better` | no match |
| 89 | `Big Sur Honey Company honey is sold out` | till sold_out shape (exact item needed) (`hass/clover/chat.py:29`) |

Optional argument fragments in `COMMANDS.md:56–59` were also replayed on the same example templates:
- `margin 24.00 for 12 at 35% shrink 5% ending .99`: margin (`hass/chat/commands.py:26`); MARGIN_RE (`hass/chat/reports_pack.py:34`)
- `margin 24.00 for 12 at 35% ending .49`: margin (`hass/chat/commands.py:26`); MARGIN_RE (`hass/chat/reports_pack.py:34`)
- `margin 24.00 for 12 price 3.49 shrink 5%`: margin (`hass/chat/commands.py:26`); PRICE_RE (`hass/chat/reports_pack.py:37`)
- `margin Hass avocado at 35% shrink 5% ending .49`: margin (`hass/chat/commands.py:26`); MARGIN_ID_RE (`hass/chat/reports_pack.py:35`)
- `margin Hass avocado price 3.49 shrink 5%`: margin (`hass/chat/commands.py:26`); PRICE_ID_RE (`hass/chat/reports_pack.py:38`)

R2 spot checks (additional spellings, not additional doc rows):
- `notes`: memory (`hass/chat/commands.py:123`)
- `notes?`: memory (`hass/chat/commands.py:123`)
- `costs?`: costs (`hass/chat/commands.py:33`)
- `backlog?`: backlog (`hass/chat/commands.py:30`)
- `look?`: look (`hass/chat/commands.py:200`)
- `shelf vegetables?`: shelf (`hass/chat/commands.py:32`)
- `yes 9z9z`: unknown-code refusal (`hass/chat/commands.py:141`)
- `please stop changes`: control hint (`hass/conversation.py:90`)
- `resume now`: control hint (`hass/conversation.py:90`)
- `again`: again (`hass/chat/commands.py:31`)

## R2. Code forms the four docs do not show

“Not shown” means no equivalent example or explicit form in these four documents. This lists input branches and material aliases, not every spelling generated by a regex, every model intent, or every validation rule. A broader owner guide or on-phone help may already mention some of them. The right column gives the nearest comparison in the four-doc corpus.

| Pack | Forms or branches not shown | Evidence and nearest doc |
|---|---|---|
| Commands / core notes | `notes` is a synonym for `memory`; `notes?` works too. In the opposite direction, `costs?`, `backlog?`, `look?`, and `shelf vegetables?` all parse: `costs` is listed already, but the other three families aren't on the punctuation list. | `hass/chat/commands.py:71,123–124,284–310`; `COMMANDS.md:12,45,48,62,68–69`. |
| Commands / core drafts | Unknown alphanumeric code with a digit, e.g. `yes 9z9z`, gets a refusal shape, not approval. A trailing code is also accepted on a near-approval hint; `okay`, `yes please`, `yep`, `yeah`, `sure`, `do it`, and `sounds good` are near-approval aliases not enumerated as such. `ok` and `okay` in the phone courtesy rule are not the same feature. | `hass/chat/commands.py:18,141–181`; `hass/conversation.py:1346–1377`; `COMMANDS.md:22–24,174`; `NATURAL_LANGUAGE.md:75`. |
| Commands / core drafts | Bare `again` reaches usage; bare `show` has a handler path, separate from the documented `show <code>` form. Bare `find` and bare `shelf` reach their handlers too. These are not added write actions. | `hass/chat/commands.py:22–23,31–32,227–231,248–250`; `hass/chat/core_pack.py:183,217–224`; `hass/chat/site_pack.py:310–347`; `COMMANDS.md:38,49–50,68`. |
| Conversation controls | Courtesy around stop/pause/resume (`please stop changes`, `resume now`) prompts for the exact form instead of running it. | `hass/conversation.py:88–96,1290–1293`; `COMMANDS.md:41–42`. |
| Reports pack | Missing-operand `margin` is already described as usage, and bare `post` is documented. All five operand patterns (four margin forms and one cost form) are described. The shared numeric shape also admits sign, exponent and separator spellings before the numeric validator; the docs don't enumerate those spellings. This is not a claim that the calculator accepts each number. | `hass/chat/reports_pack.py:32–42,88–105,287–290`; `COMMANDS.md:47,52,56–59`. |
| Site pack | No separate undocumented input family in this pack. `listing store`, `look hike`, shelf lookup, hidden and held all have examples. Bare `find` and `shelf` are shared-parser branches noted above. | `hass/chat/site_pack.py:109–142,210–229,310–378`; `hass/chat/commands.py:22,32,200–212`; `COMMANDS.md:49,60–68`. |
| Wording / field words | None: these are output formatters. The photo path, phone shape and date format checks are on values from records, not owner message verbs. | `hass/chat/wording.py:13,85–98,173–185,235–289`; `hass/field_words.py:1–8,54–59`. |
| Simple intake adapter | `what next` and `next`; `leave out` / `delete` for an existing description fragment; `maker <value>` and `shelf <value>`; in-context `description:` / `say it's` for copy and standalone `in stock` / `low on stock` stock words. `say it's` is shown as an NPP gap, not as a simple-preview form. `from <value>`, or `this is from` / `supplier:` / `source:` / `we get it from` with a value, can select a supplier; the NPP page shows `from Etto please` and a rewritten supplier lead, not these other forms. | `hass/skills/intake_simple.py:14–21,139–187`; `COMMANDS.md:128–142`; `NPP-EDIT-PHRASES.md:30,51,60`. |
| Versioned NPP card | Version-suffixed `yes <code>-<version>` and `no`/`cancel` with the job code and optional version suffix. The four docs only describe the generic code shape, not a card version suffix. `cancel` is already documented as a generic alias. This does not specify which reply is acceptable for a given card. | `hass/npp/job.py:53–54`; `hass/conversation.py:1503–1543`; `hass/chat/commands.py:45–48`; `COMMANDS.md:28–31,139–145`. |
| NPP deterministic edits | Pinned `made by <maker>[, <town>]`; `name it` / `name:`; wording choices `simpler`, `plainer`, `less fancy`, `more fun`, `warmer`; photo aliases `use my own photo`, `try the picture again`, `redo the picture`, `different picture`, `change the picture`, `new picture`. The docs show the corresponding name/wording/photo families, not these forms. | `hass/npp/assets/hass-listing-edit/edit-grammar.json:24–38,61–79`; `NPP-EDIT-PHRASES.md:27–36`. |
| NPP edit fallback | `pls` / trailing `thank you`; `rename this/that as …`; `stick … onto …`; `make its copy/text/wording/blurb …`; `use my pic`; `a tad`; `sold by the pound` / `priced apiece`. These extend the fallback described in the doc. | `hass/npp/edits.py:33–56,81–113`; `NPP-EDIT-PHRASES.md:7–15`. |
| Till chat (separate from count baseline) | Fixed low-stock, count-of, how-many/how-much and stock questions. The docs do mention “is the sourdough sold out?” as a site question; they don't identify the other till branches or its competing interpretation of stock questions. `link all`, `link … to …`, `unlink …`, and `stock yes/no …` have their own gated grammar. Fixed writes also admit alternatives such as `we received …`, `new till item: …`, `change the price for …`, and `set the count of … to …`. | `hass/clover/chat.py:26–32,46,85–103,139–186`; `COMMANDS.md:76–89,177–184`; `CLOVER-COUNT-PHRASES.md:3–4`. |
| Standalone Clover count | `label: amount`; `there are/is …`, `we have …`, optional `on the shelf` / `now`; arrival `got` / `received` or terminal `came in`; standalone amount-first counts; exact spaced `lb`/`lbs`/`pounds`, fractional weight, and straightforward `dozen` with a product. The baseline names the categories and mainly prints gaps, not the working templates (some are exercised in the linked fixture, e.g. `ceramic strainers: 5`, `got 1.75 pounds of hazelnuts`, `three dozen cloth filters came in`). The owner card does show the narrower `received` and `set` forms. | `hass/clover/qty_words.py:19–23,31–60,85–107`; `hass/tests/test_clover_count_phrases.py:24–46`; `COMMANDS.md:82–83`; `CLOVER-COUNT-PHRASES.md:6–20,24–44`. |

## R3. Phrases matching more than one pattern

The overlaps below group the R1 witnesses by pattern pair. Quoted forms use regex source where short, otherwise quote the recognized template or rule with its full source anchor. A shared prefix plus a required operand check is listed separately from competing routes. This is a replay of the examples and stated controls, not an intersection proof over all possible messages.

| Witnesses | Matching patterns | What separates them |
|---|---|---|
| `yes a1b2`, `YES A1B2`, `no a1b2` and the bound `yes` / `approve` / `approved` / `no` / `cancel` / `reject` code forms | “`(yes\|approved\|approve\|no\|cancel\|reject)(?: ([0-9a-f]{4,12}))?`” (`hass/chat/commands.py:17`) and phone “one approve/cancel word and one code in either order” (`hass/chat/commands.py:156–174`). | Generic router uses `parse_keyword(...) or coded`; a decorated phone answer and a question take different paths (`hass/conversation.py:1297–1301,1357–1377`). |
| The same `yes`/`no` code examples, `cancel A1B2` and bound `cancel <code>`; bare `no` and `cancel` | Generic keyword above, plus “`yes ([0-9a-f]{4,12})(?:-([1-9][0-9]{0,8}))?`” or “`(?:no\|cancel)(?: ([0-9a-f]{4,12})(?:-[1-9][0-9]{0,8})?)?`” (`hass/npp/job.py:53–54`). | A matching NPP job or active card is checked first; overlapping syntax is not authority to approve or cancel either target (`hass/conversation.py:1280–1282,1503–1543`). |
| R1's eight-character `yes`, `no` and `undo` code fixtures | Generic keyword above or “`(undo)(?: ([0-9a-f]{4,12}))?`” (`hass/chat/commands.py:19`), plus till “`(yes\|no\|undo) ([0-9a-f]{8})`” (`hass/clover/chat.py:32`). | Till first pass checks the journal for the sender/chat, not only the shape (`hass/clover/chat.py:130–137`; `hass/conversation.py:1313–1318`). |
| `stop`, `stop changes`, `pause`, `pause changes`, `resume`, `resume changes` | “`(pause\|stop)(?: changes)?`” or “`(resume)(?: changes)?`” (`hass/chat/commands.py:20–21`), plus near-control “`(?:(?:please\|now\|thanks) )*(?:(pause\|stop)\|(resume))(?: changes)?(?: (?:please\|now\|thanks))*`” (`hass/conversation.py:90`). | Only when no command matched does the hint run (`hass/conversation.py:1289–1293`). |
| `?` | Help alternative “`\?`” (`hass/chat/commands.py:21`) and simple “`^(?:what['’]?s next\|what next\|next\|\?)[?!. ]*$`” (`hass/skills/intake_simple.py:14`). | Open simple intake suppresses help; an active NPP retry is checked even earlier. These are contexts, not two responses (`hass/conversation.py:1280–1285,1544–1552`). |
| `held`, `costs` | Exact “`(held)`” / “`(costs)`” plus typo “one edit from a whole one-word message of 4+ ASCII letters” (`hass/chat/commands.py:33–34`; `hass/conversation.py:99–120`). | Running the helper independently suggests `help` / `cost`; command dispatch returns first (`hass/conversation.py:1326–1329,1378–1382`). |
| `post maker fixture-farm`, `post maker Linn's`, `post maker linn's`, bound `post maker <key>` | “`post\s+maker(?:(\s+)(.*))?`” and “`(post)(?:\s+((?s:.*)))?`” (`hass/chat/commands.py:184,25`). | Maker runs first and retains case and punctuation; both sample key spellings parse, even if only one names a real maker (`hass/chat/commands.py:187–197,215–225,297–303`; `hass/chat/reports_pack.py:146–166`). |
| `show Sunshine olive oil on the till` | Chat “`(show)(?:\s+(.*))?`” and till “`(?P<v>hide\|show) (?P<q>.+?) on the till`” (`hass/chat/commands.py:23`; `hass/clover/chat.py:31`). | Till `first` has a special `show … on the till` branch when the engine is present (`hass/clover/chat.py:130–135`; `hass/conversation.py:1316–1318`). |
| `received 12 Sunshine olive oil`; both `set Sunshine olive oil to …` fixtures; `set the website photo of the wooden ladle to 3` | Arrival: “`(?:we )?received (?P<n>\d+(?:\.\d+)?) (?:of )?(?P<q>.+)`” vs “`(?:(?:we )?(?:got\|received)) (.+)`”. Set: “`set (?!(?:the )?price\b)(?:the count of )?(?P<q>.+?) to (?P<n>\d+(?:\.\d+)?)`” vs “`set (?!(?:the )?price\b)(?:the count of )?(.+?) to (.+)`” with `_amount` and `_intent` (`hass/clover/chat.py:26–28`; `hass/clover/qty_words.py:20–21,31–82,93–100`). | Standalone count has no production chat caller on this main (`git grep -n qty_words origin/main -- hass`). The photo sentence matches the active till **shape** too; no item resolution or change was attempted (`hass/clover/chat.py:164–172,289–305`). |
| `add: great for furniture`, `add: great on toast`; `call it Wildflower Honey please` | NPP “`add:\s*(?P<value>.{2,120})`” vs simple “`(?:(?:add\|description)\s*:\s*\|say\s+it['’]s\s+)(.+)`”; NPP “`(?:call it\|name it\|name:)\s*(?P<value>[A-Za-z][A-Za-z0-9' &-]{1,60})`” vs simple “`(?:name\|call it\|rename(?: it)?(?: to)?)\s*:?\s+(.+)`” (`hass/npp/assets/hass-listing-edit/edit-grammar.json:34,52`; `hass/skills/intake_simple.py:19,154,171`). | Independent edit readers, not sequential writes. The add-note grammar asks where simple intake edits a fixture description. The name patterns both keep the courtesy word as part of the value here (`hass/npp/edits.py:138–149,183–192`). |
| `from Etto please` | NPP “`from\s+(?P<value>[A-Za-z][A-Za-z' .&-]{1,40})`” vs simple “`from\s+(\D+)`” (`hass/npp/assets/hass-listing-edit/edit-grammar.json:16`; `hass/skills/intake_simple.py:177`). | NPP keeps `please` in the supplier value; simple intake matches the shape but asks instead (`hass/npp/edits.py:30,172–176`; `hass/skills/intake_simple.py:18,177–185`). |
| All `margin` rows and option fixtures | “`(margin)(?:\s+((?s:.*)))?`” plus one of “`<cost> for <units> at <margin>%`”, “`<product> at <margin>%`”, “`<cost> for <units> price <P>`”, or “`<product> price <P>`” (`hass/chat/commands.py:26`; `hass/chat/reports_pack.py:32–38`). | Verb then operand, not competing command routes. No documented numeric pack example also matches the product operand pattern (`hass/chat/reports_pack.py:34–38,91–100`). |
| Three `cost …: … for …` examples and `forget backlog.3` / its template | Memory alternatives “`(cost)(?:\s+(.*))?`” and “`(forget)\s+(\S.*)`”, then respectively “`\$?(\S+)\s+for\s+(\S+)`” on the cost operand and “`backlog\.[0-9]{1,9}`” on the forget key (`hass/chat/commands.py:123–124,264–283`; `hass/chat/reports_pack.py:39`; `hass/chat/core_pack.py:274`). | Nested operand checks, not competing commands. |

## R4. Ranked gaps and one possible follow-up

1. **Clarify which listing preview the owner is editing.** The owner card's examples are simple-preview forms; versioned NPP has a separate grammar and turn test. In particular, `add: great for furniture` can match without a local patch, and `per pound please` asks in the isolated edit reader but does not start a card edit turn (`COMMANDS.md:128–145`; `NPP-EDIT-PHRASES.md:26,38,61`; `hass/npp/reply.py:91–103`; R1). Do not treat those parser results as publication or approval outcomes.
2. **Keep Clover's false accepts separate from support claims.** The four negative examples remain false accepts in the standalone parser. The website/photo example also matches the separate chat till set shape. A match does not resolve an item; no connected till or live impact was verified. Don't widen the baseline based on the 13 refusals alone (`CLOVER-COUNT-PHRASES.md:22,26–51`; `hass/clover/qty_words.py:79–106`; `hass/clover/chat.py:164–172`; R1/R3).
3. **Distinguish real commands from phrases that may only get guidance.** `undo that` and `never mind` are already handled before the free-form reader. The other phrases in that natural-language table are not automatically fixed instructions or commands. Also, recognition of bare `yes` does not prove it applies a draft: the owner card has differing descriptions at lines 4 and 29, and code checks `approvalNeedsCode` as well as pending question/target state (`NATURAL_LANGUAGE.md:70–77`; `hass/conversation.py:1357–1407`). This audit does not choose a rule or claim which configuration is installed.
4. **Fill small discoverability gaps when next touching the guides.** The `notes` alias and the extra read-only `?` forms are examples of code exposed more broadly than the owner card describes (`COMMANDS.md:12,45,62,68–69`; `hass/chat/commands.py:123–124,288–310`).

**One possible separate unit (~75 minutes, estimate):** In `docs/hass/COMMANDS.md` only, label the simple preview examples at lines 128–142 as simple-preview examples and point to `docs/hass/NPP-EDIT-PHRASES.md` for the separate versioned NPP grammar and its no-patch cases. No new approval, price-publication, claim, or hold wording. Offline test: rerun the attached `python3 -B ../phrase_replay.py` from the clone root (if the doc lines move, update only the scratch selectors). Check `name Wood Glue` changes the simple fixture name but does not match the NPP name form, and `add: great for furniture` changes the simple fixture description but returns `ask_edit_unclear` in the no-mapper NPP replay. Read the revised paragraph against those outcomes; no handler or site run. No follow-up edit is part of this report.
