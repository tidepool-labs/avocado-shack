# Hass commands (owner card)

In live mode, proposals show the full previous text and name the site the change goes live on.
Approval must name the draft: `yes a1b2`, not a bare `yes`. A bare `no` still cancels.
A protected change says it cannot go live from chat. A saved reply is not a website outcome;
Hass sends a separate message about the website.

These are the only messages Hass treats as commands. Send each one as the whole message. Capital letters in the command
do not matter (`YES A1B2` is the same as `yes a1b2`). Codes are the short codes Hass puts in its replies; `A1B2` below
is only a placeholder.

A trailing `.` or `!` is ignored for every command except `remember` and `forget` (`Status.` and `Memory.` work). `post maker <key>` is the one other exception: its key is kept exactly as sent, so a final `.`, `!` or `?` stays part of the key. A trailing `?` is also ignored, but only for the read-only commands `status`, `history`, `report`, `memory`, `find`, `show`, `post`, `listing`, `hidden`, `held`, `margin`, `costs` and `help` (`status?`, `find eggs?` and `show a1b2?` work). A `?` never runs `yes`, `no`, `undo`, `stop`, `resume`, `remember`, `forget` or `alias`.
The two note commands are stricter:

- `remember <key>: <text>` saves the text exactly as sent, so its capitals and any final `.` or `!` are kept.
- `forget <key>` ignores a trailing `!` but not a `.`, because a key may contain `.`: `forget parking.` looks for a
  note called `parking.` and leaves the `parking` note alone. Send `forget parking` with no full stop.
- A note name may have spaces, as an alias name does: they become `-` and capitals fold, so `remember Parking Spot: use the back lot`
  saves `parking-spot` (the reply names that key) and `forget parking spot` removes it. A name still invalid after that gets
  the usual refusal. `forget it` removes a note called `it`; `forget it all` is not a command.

A yes or no with its code works in either order and survives everyday phone typing: commas and other punctuation, emoji and the words please, thanks, thank you, ok and okay are ignored, so `Yes, a1b2`, `yes a1b2 thanks`, `A1B2 yes` and `no a1b2 please` act as `yes a1b2` and `no a1b2`. Any other word keeps its meaning: `yes but make it 10am` and `no, 5pm` are still change requests.

A question mark means a question, never an answer. `yes a1b2?`, `no a1b2?`, `a1b2 yes?`, `yes?`, `no?`, a waiting code on its own (`a1b2` or `a1b2?`) and similar forms apply nothing, cancel nothing, record no approval and make no interpreter call. Hass replies `Nothing was changed. To apply a1b2, reply yes a1b2; to cancel it, no a1b2.` (with no or an unknown code, it lists the waiting codes).

| Send | What happens | Example |
| --- | --- | --- |
| `yes <code>` (or `approve <code>`, `approved <code>`) | Applies that draft, then replies when it is done and checked. The reply says the change is saved but not on the website yet, because copying it to the website is a separate step. | `YES A1B2` |
| `yes` alone (or `approve`, `approved`) | Applies the one waiting draft. If more than one is waiting, Hass asks which. | `approve` |
| `no <code>` (or `cancel <code>`, `reject <code>`) | Cancels that draft or question; nothing changes on the site. | `cancel A1B2` |
| `no` alone (or `cancel`, `reject`, `cancel that`, `cancel it`, `never mind`, `nevermind`) | Cancels the waiting draft or question; nothing changes. | `no` |
| `no all` (or `cancel all`, `cancel everything`) | Cancels every draft and question waiting for you at once, and replies every code it cancelled: `Cancelled a1b2, c3d4; nothing changed.` A photo draft is cancelled too, and its photo stays stored privately, exactly as with `no <code>`. Only drafts still waiting (not timed out) are cancelled; nothing is applied and nothing changes on the site. With nothing waiting it replies `Nothing is waiting.` It never calls the interpreter and works while paused. | `cancel all` |
| `yes all` (or `approve all`) | Approves nothing: every draft needs its own `yes <code>`. Replies `Nothing was changed. Each draft needs its own yes <code>. Waiting codes: a1b2, c3d4.` A waiting question's code is listed too, and the reply then adds `Questions still need details before approval.` With nothing waiting it replies `Nothing is waiting.` It never calls the interpreter and works while paused. | `approve all` |
| `history` | Lists the last five approved changes in plain words, each with when you said yes (Pacific time, like "approved Tue Nov 3 2:14 pm"; "time unknown" when that time was not kept) and where it is now (on the website, saved but not confirmed on the website, or undone). The time is when your yes was recorded, not when the website changed. It reads the audit log (docs/hass/AUDIT.md), so a change on the till is listed too ("A change on the test till: saved."). With none yet it says "We haven't made any changes yet." It changes nothing. | `history` |
| `history <words>` | Lists up to 10 approved changes, newest first, whose summary contains every word you send, each with when you said yes (Pacific time, or "time unknown") and where it is now; capital letters and accents do not matter, and the words may come in any order. Only the summary is searched (not the time), across all approved history. Send 1–60 characters; no match says so ("I found no changes that match ..."), and no words gets a usage reply. It changes nothing, expires nothing and works while paused. | `history opening hours` |
| `undo` (or `undo that`, `undo it`, `undo last`, `undo the last change`, `please undo`) | Drafts an undo of the most recent applied change; a bare undo skips undos and takes the change before. It needs `yes <code>` like any draft. | `undo` |
| `undo <code>` | Drafts an undo of that applied change. It needs `yes <code>`. | `undo A1B2!` |
| `again <code>` | Re-drafts a change that expired at most 7 days ago (exactly 7 days still counts) as a new draft with a new code and a fresh expiry; it never calls the interpreter and never revives the old draft, which stays expired. Hass prepares the saved steps against the website as it is now and offers the new draft only when every record it changes would end with the same values the expired draft showed; otherwise it says `the site changed since <code>; send the change again`. A change to other records does not matter; another change to a record this draft touches does. It is refused by state for a draft still waiting for your yes or for details, a cancelled or replaced one, a saved or failed one, a question that expired before it was a proposal, and any photo draft (`send the photo again`); older than 7 days or unreadable details are refused too, and an unknown code says `No draft <code>`. It also re-drafts a change you undid, when the undo was applied at most 7 days ago (the age counts from the undo, not from the original change): the same saved steps are prepared on the website as it is now, with a new code and expiry, and offered only when every record they change would end with the values the original change wrote; otherwise it says `the site changed since <code>; send the change again`. The original stays undone. Undone more than 7 days ago says so; the code of an undo (or a draft with any undo in it) says `That code is for an undo` (and `undo` on it names the `again` command for the original); photo drafts are refused. It works while paused, but nothing is saved: the new draft needs `yes <new code>` (a bare `yes` never approves it, and neither does the old code's approval). | `again A1B2` |
| `status` | Says in plain words whether changes are paused (or that Hass is having trouble reading your messages), what is waiting for your yes or for details, a question of mine you have not answered yet, when you last did the shelf check (or that it is still needed) with, once there is a check, the same "On the shelves:" counts as `report` (a word set on its own day counts while it is current), the saved home-page notice with its last day (`Home notice: ... - through Thursday, November 26`; once that day has passed `... - ended Sunday, November 1; no longer shown`; a notice with its own first day names both days: `... - from Friday, November 20 through Thursday, November 26; not shown yet` before the first day, the same range while it shows, and `...; no longer shown` after the last day; no line when there is no notice; a notice can be set ahead with an optional first day, `store.set_notice` `from` (Pacific today up to its last day, e.g. from 2026-11-20 until 2026-11-26): it shows from that day through its last day, both included, and without JavaScript it appears, or an expired one goes, at the next regeneration), upcoming hike seat totals and your last change. Near the daily limit it adds "I'm close to the number of new requests I can read today." It also mentions photos that are waiting for details or still downloading when there are any. It changes nothing. | `Status.` |
| `did it work?` (or `did that work?`, `did my change work?`): the same as `status` | Answers "did my change work?" in its `Last change:` line: done and on the website now (with the time it was checked), saved but not confirmed on the website (and why; if copying it stopped part way some pages may already show it, so ask for help to copy it again), did not reach the website (the website is unchanged), or undone. It changes nothing. | `did it work?` |
| `stop changes` (or `stop`, `pause`, `pause changes`) | Stops any approval from applying and replies how many requests are waiting. Drafts can still be prepared; changes already on the website stay there. | `stop changes` |
| `resume` or `resume changes` | Lets approvals apply again. It never applies a waiting draft by itself. | `resume changes` |
| `remember <key>: <text>` | Saves a note for Hass (key: a-z, 0-9, `.` or `-`; spaces in the key become `-`). Sending the same key again updates it. | `remember parking: use the back lot` |
| `forget <key>` | Deletes that saved note, or a kept design note such as `design.2` (spaces in the key become `-`). | `forget parking spot` |
| `memory` | Lists your saved notes (up to 20, under "Notes I'm keeping:"), then your nicknames apart (up to 20, then "And a few more."); notes and nicknames are counted and capped separately. Your saved purchase costs are never listed among the notes: when there are any, the last line says `Costs saved: <n> (send costs)` (all of them counted, not just the ones `costs` shows), and nothing is added when there are none. A nickname line shows the product or maker name as it is on the website now, and says when it is hidden or on hold. A nickname whose product or maker is gone says so and how to forget it; when the saved copy cannot be read right now it says that, and nothing is deleted. Design requests I kept for the developer are listed apart under "Design notes (N):" (up to 20, then "And a few more."), each as `design.<n>` with your words and the date. It only reads: it changes nothing, does not expire drafts, and works while paused. | `memory` |
| `alias <name>: <product or maker>` | Saves your own nickname for a product or maker that exists now (say its name), so a lookup of that nickname finds it, and a plain-word change request ("the green jam is sold out") can use it to pick that record. Only nicknames whose record still exists, the newest 50, reach change requests; a nickname never establishes a claim. Send `forget alias <name>` to remove it. If a note named `alias-<name>` is saved and no nickname has that name, `forget alias <name>` removes the note; if both exist nothing is forgotten and the reply names the two exact forgets. | `alias green jam: Linn's blueberry preserves` |
| `cost <product>: <pack cost> for <units>` | Saves what you paid for one purchase of a product (say its id, its name or a nickname you saved with `alias`, as in `cost green jam: 24 for 12`; it must exist now, any status), as your private note; sending a new cost updates it and says what it was. The reply names the product by name and id. If the name fits several products it lists them (up to 10, with ids, then asks for another word) and saves nothing: send the cost again with the id; if it fits none it says to try `find`. A number that is out of range is named in plain words. The cost is never on the website, in a draft or in what is sent to the interpreter; `memory` does not list it (it only counts your saved costs) and `costs` shows it to you, and `forget cost.<product id>` removes it. `remember cost...` does not work, use this command. It changes no price and works while paused. | `cost Hass avocado: 24 for 12` |
| `costs` | Lists the purchase costs you saved with `cost`, newest saved first, one line each: `<product name> (<id>): $24.00 for 12 = $2.00 each, saved Tue Nov 3` (the day in Pacific time). The each figure is the cost per item from the same calculator as `margin`, never rounded to the cent here (`10 for 3` shows `$3.333333... each`). A product that is hidden or on hold keeps its name and says `(hidden)` or `(held)`; one no longer on the website says `Product no longer listed (<id>)`, and when the product names cannot be read right now the lines say `Product name unavailable (<id>)` and so on, with the cost kept. A saved cost or date that cannot be read stays in the list as one safe line (with how to forget it, or `saved date unavailable`); nothing is repaired or deleted. Up to 20 lines, then `... and <n> more`; none saved says `No purchase costs saved.` It is separate from `memory`, shows only your own private costs (no hold reason or maker detail), only reads, expires no draft and works while paused. | `costs` |
| `find <words>` | Lists up to 10 matching products, makers, hikes and route ideas by name (your nicknames too), each with its status in plain words (hidden, cancelled and done ones included) and hikes with the weekday, date and time. More than 10 ends with "There are more. Add a word to narrow it down." It changes nothing and works while paused. | `find lion's mane` |
| `show <code>` | Sends that draft again: a waiting draft's full proposal text and its preview screenshot, or an applied change's lines (with its commit) and its checked screenshot. An expired, cancelled or replaced draft is named as such. It changes nothing, expires nothing and works while paused. | `show A1B2` |
| `report` (or `morning report`) | Replies the morning shelf report from your last shelf check (Pacific today): when you last checked, counts of available, limited, sold out and not confirmed products, the limited and sold-out names, and hikes today or tomorrow. These are shelf checks, not stock counts. It then adds the same `Home notice:` line as `status` when a notice is saved, and a `Waiting for you:` block: each draft waiting for your yes or for details (code and summary, the same lines as `status`) and `Photos waiting for details: N`, or `Waiting for you: nothing`. It changes nothing on the site, expires nothing and works while paused. When today's shelf check is missing it ends with "Is the shelf list right for today? Reply yes if it is, or tell me what is different.", the first time that day; your bare `yes` then drafts the check for your normal approval. | `report` |
| `post <product>` | Takes a product id, name or saved alias (`post green jam` after `alias green jam: <id>`): an exact id works as before; otherwise exactly one *active* product that the name or alias fits acts as its id, so the reply is byte-for-byte what sending that id gives. Several active matches get up to 10 lines like `product <id>: <name> (active)` (with `There are more. Add a word to narrow it down.` when the list may be longer) and nothing else; a name that fits only held or hidden products gets `No active product matches "<words>"; send find <words> for ids.` A held or hidden product is never picked by name (its exact id still gets its plain-words reply). Several words count as this command only when they fit a product's name, brand or alias; otherwise (`post about the porch walk recap`) the message is read as an ordinary request, and one unknown word gets `I don't know a product called ...` and to use `find`. A bare `post` or a word over 60 characters gets the one-line usage. Replies a draft Instagram-style caption for that active product (its name, description and maker) with its site photo attached, then what the photo shows. When that photo is a catalog illustration rather than an installed owner photo (today every product), the reply first says so: `This picture is an illustration made from a shelf photo, not a photo of the product. Send a photo with the product name as its caption to post a real one.` An owner photo gets no such line; the caption and attachment are the same either way. AV2137-08: when the website card for that product shows Sold out or Limited, the reply also says `The website shows <name> as Sold out (checked <day>). A post now may send people in for something that is not on the shelf.` (Limited in the same words; `<day>` is the day saved with that word) after the illustration line and before the draft. Available today, Last confirmed or no word get no such line. The draft and photo are the same, and nothing is posted. Nothing is posted, scheduled or saved. A product that is unknown, not on the website or without a photo gets a plain-words reply. It changes nothing and works while paused. | `post Hass avocado` |
| `post hike <hike>` | Reserved: `post hike ...` is always a hike, never a product called "hike ...". Replies a ready-to-copy announcement draft for that scheduled, upcoming hike (title, time, meeting point, route). Say the hike's name. Nothing is posted, scheduled or saved. A hike that is unknown, cancelled, already past or not scheduled gets a plain-words reply. It changes nothing and works while paused. | `post hike Point Buchon` |
| `post maker <key>` | Reserved: `post maker ...` is always a maker key, never a product name or alias. Replies a draft "Meet the maker" caption for that maker, ready to copy: `Draft post (not posted; copy it yourself):` and then the caption exactly as the draft builder wrote it (name, place, story, how many active products are on the site, and the fixed tags), never cut. The key is everything after `post maker`, with spaces at the ends trimmed: its capitals, spaces and apostrophes count, and a final `.`, `!` or `?` is part of the key, so `post maker Linn's` works and `post maker linn's` does not. Send `find <words>` to see the keys; a maker's name or nickname is not a key. No key, or a line break in it, gets the one-line form to send. There is no photo. A maker that is unknown, hidden, without active products or missing its place or story gets a plain-words reply, and an unreadable catalog says nothing was changed. Nothing is posted, scheduled or saved. It changes nothing (no draft, waiting yes or pause is touched, no interpreter call) and works while paused. | `post maker fixture-farm` |
| `post notice` | Replies a draft caption for the home page notice the website shows today, ready to copy: `Draft post (not posted; copy it yourself):` and then the notice words exactly as you saved them, its days in words (`through Thursday, November 26`, or `from Monday, November 23 through Thursday, November 26` when the notice has a first day), the store name, the street and town, and the fixed tags `#AvocadoShack #MorroBay`. The first and last day both count, by the Pacific calendar. With no notice, one that has not started yet or one whose last day has passed, it says `There is no notice on the website to post.` A `#` or `@` followed by a letter, digit or `_` in the notice or the store details, or a caption over 2200 characters, gets a plain-words reply instead of a caption; nothing is cut or rewritten. Only the whole message `post notice` (any capitals, a final `.` or `!` ignored) does this; `post notice` plus other words is read as before. There is no photo. Nothing is posted, scheduled or saved. It changes nothing (no draft, waiting yes or pause is touched, no interpreter call) and works while paused. | `post notice` |
| `post today` | Replies a draft "In at the Shack today" caption, ready to copy: `Draft post (not posted; copy it yourself):` and then `In at the Shack today`, the names of the products you marked Available today or Limited in your shelf check, in the order of the website's catalog (at most 12, then `and more`), the store name, the street and town, and the fixed tags `#AvocadoShack #MorroBay`. It works only when your last shelf check is today by the Pacific calendar, and a product is named only when its own word was set in that check (or set since, the same day): a product that check did not name is never added because it was marked on an earlier day, and sold-out, hidden and held products are never named. When your last shelf check was an earlier day (or is dated later than today) it says `Your last shelf check was <day>; send today's shelf check first.`, so an old check is never posted as today's; with no shelf check recorded it says so and asks for one, and when the check names no Available or Limited product it says `No products were marked Available today or Limited in today's shelf check.` A `#` or `@` followed by a letter, digit or `_` in a named product or the store details, or a caption over 2200 characters, gets a plain-words reply instead of a caption; nothing is cut or rewritten. Only the whole message `post today` (any capitals, a final `.` or `!` ignored) does this; `post today` plus other words is read as before. There is no photo, price or count. Nothing is posted, scheduled or saved. It changes nothing (no draft, waiting yes or pause is touched, no interpreter call) and works while paused. | `post today` |
| `margin <pack cost> for <units> at <margin>%` (optional `shrink <S>%`, optional `ending .99` or `ending .49`) | Replies one friendly answer: the price to charge, what each one costs you, what you would earn and roughly what percentage that is, and that it is only an idea (nothing on the website changes). A `$` before the pack cost and spaces around the numbers are fine; without `shrink` it is 0%. `ending .99` (or `.49`) goes last, after `shrink`: the price is rounded up (never down) to the next such ending and the margin shown is the one that rounded price gives; any other ending gets the one-line form to send, and a shelf-price check (`price`) takes no ending. A number that is out of range is named in plain words; a message that starts with `margin` but is not in this form gets the one-line form to send. It stores nothing, puts no price on the site, does not read a change request and works while paused. | `margin 24.00 for 12 at 35%` |
| `margin <pack cost> for <units> price <P>` (optional `shrink <S>%`) | Checks a shelf price you already charge: replies the margin it gives with every step shown, and the line "Below cost: this price does not cover the cost per sellable unit." when the price does not cover the cost, then that it is only an idea. Same rules as the form above (without `shrink` it is 0%); a number out of range is named. It stores nothing, puts no price on the site, does not read a change request and works while paused. | `margin 24.00 for 12 price 3.49` |
| `margin <product> at <margin>%` (optional `shrink <S>%`, optional `ending .99` or `.49`) | Uses the cost you saved with `cost` for that product (say its id, name or saved nickname, as in `margin sourdough at 35%`; any status): replies "For <name> (<id>), using the cost you gave me <when>." and then the same answer as the form above. A pack form (`24 for 12 at 35%`) is always the numbers, never a name. If the name fits several products it lists them (up to 10, with ids) and works nothing out; if it fits none it says to try `find`. With a known product but no saved cost it names the product and says how to save one; a margin out of range is named. It stores nothing, drafts no price change and works while paused. | `margin Hass avocado at 35%` |
| `margin <product> price <P>` (optional `shrink <S>%`) | The same shelf-price check, using the cost you saved with `cost` for that product (id, name or saved nickname; replies "For <name> (<id>), using the cost you gave me <when>." first). Several or no matching products, and no saved cost, are answered as in the form above. It stores nothing and works while paused. | `margin Hass avocado price 3.49` |
| `hidden` | Lists the hidden products, then the hidden makers (marked as makers), by name, up to 20, then "And a few more.", and says how to bring one back ("Bring back <name>"). Held products are never listed. With nothing hidden it says so. It changes nothing and works while paused. | `hidden` |
| `held` | Lists the held products from the saved copy, by id, up to 20: `- <id>: <name> — <the recorded hold reason> (source <the recorded source link>)`, each complete, then `... and <n> more` when there are more than 20, and always ends `Held products stay off the website and Hass cannot release them. Check the package against the recall notice and tell G or the operator.` With none held it says only `No products are held.` The reason and link are what was recorded when the product was put on hold, not a fresh look at the source or a statement that a recall is still current; Hass does not check them, release a hold or say a product is safe, and nothing in this list changes a hold. If the saved copy or a hold's reason or link cannot be read it says so and lists nothing. Held products are in no other list: `hidden` leaves them out and `find` shows only that a product is on hold. It only reads: it changes nothing, expires no waiting change or open request and works while paused. | `held` |
| `look`, `look hike` or `look <product>` | Replies a fresh phone-width picture of the private preview as it is now, so you can see the site from your phone without a link: `The website now (private preview, phone):` with one picture. `look` is the home page, `look hike` the hike page, and `look` with a product id, name or saved nickname that matches exactly one active product is that product's card (a name that fits several lists them, ids first, up to 10, and asks for the id; a hidden or held product is \"not on the site\"; an unknown one says no active product matches; both point to `find <words>`). It uses the same preview as the draft pictures, with no draft changes in it and no desktop picture. If no preview is set up, the picture fails or its page checks fail, the whole reply is `I could not take a picture of the site right now; nothing changed.` with no picture. It makes no draft, expires nothing, never calls the interpreter, counts nothing against the daily limit and works while paused. | `look hike` |
| `listing <name>` | Replies what the saved copy shows for one product, maker, hike or route idea (an exact id first; then a name or a saved alias of one *active* product, as `listing sourdough`; a held or hidden product is found only by its exact id), starting "This is from my saved copy, not a live look at the website:" with its name, status, place and so on in plain words; anything not saved reads "nothing yet". Say a name or part of one. Several active products fitting gets the same `product <id>: <name> (active)` lines as `post` (up to 10); a maker, hike or route idea that fits is still shown first as before; if more than one thing of those fits it asks you to say a bit more of its name; none says `I don't know that one` and to use `find`. Several words count as this command only when they name something, as before. A bare `listing` or a word over 60 characters gets the one-line usage. It changes nothing and works while paused. | `listing Etto` |
| `photos to take` | Lists the first five active products that still show a stock picture instead of your own photo, with their shelves, then says to ask again for the next few and to send a photo with the product's name as its caption. Hidden and held products are left out. It reads the saved copy (not a live look at the website) and goes by the picture's file name only: it does not look at the picture or prove where one came from. It changes nothing, does not expire drafts, and works while paused. | `photos to take` |
| `help` (or `commands`, `?`, `what can you do`, `what do you do`, `what can I say`) | Replies a short index of the command names in four groups (Drafts, Look up, Notes, Control; one line each, none over 70 characters) and how to ask for one (`help undo`), then every registered skill grouped by pack with its approval, private-test support and status. This is the code's list, not proof of what is installed or live. The same list is in [What Hass can do](CAPABILITIES.md). The capability questions are matched as whole messages only, never go to the model and work while paused and in every skills mode. It changes nothing. | `help` |
| `help <command>` (any word the command goes by: `help undo`, `help yes`, `help stop changes`, `help photos to take`) | Replies that command's full usage lines, each ending in an example you can send. A name help does not know (`help a1b2`) gets `Unknown command. Send help with one of:` and the same grouped names; what you typed is not repeated. It never runs the command (`help yes` approves nothing, `help remember` saves nothing), never goes to the model, changes nothing and works while paused and after the daily limit. A longer sentence such as `help me with avocados` is still a change request. | `help undo` |
| `listing store` | Reserved: the whole word `store` is always the shop itself, never a product, ahead of any name. Replies what the site shows for the shop itself, from my saved copy (not a live look at the website), under the same first line as `listing <name>`: `Address:` (street · town), `Hours:` with each hours line as `- <line>`, `Phone:` only when one is saved, `Intro:`, `Headline:` (its two lines), `Story:` (the first 80 characters, then `…` when it is longer), `Home photo:` (`yours - <description>` or `the shop's own photo`), the same `Home notice:` line as `status` (days, `not shown yet` or `no longer shown` included; no line when there is no notice) and last the shelf check sentence the site uses (`Shelf check: not done yet` before the first one). Empty intro, headline or story show the site's own words. If the saved content cannot be read it says so and nothing else. Read it before changing the hours. It changes nothing, drafts nothing and works while paused. | `listing store` |
| `shelf <name>` | Lists one shelf's active products in the order the website shows them, each with the word the site shows for it (`Available today`, `Limited`, `Sold out`, `Last confirmed <day>`, or no word), up to 60 and then `... and N more`, so you can walk the shelf before a shelf check. The name is a shelf name or id (`shelf vegetables`, `shelf dairy & cheese`); anything else answers with the shelf names. Hidden and held products are left out. It reads the saved site content, not the live site, changes nothing and works while paused. | `shelf vegetables` |
| `backlog` | Lists the last 10 things you asked that Hass could not do yet (the request number, the day and one line), newest first, or says nothing is written down. It shows no more than that one line of what you sent, changes nothing on the website, and works while paused. | `backlog` |
| `forget backlog.<n>` | Takes that one request off the `backlog` list (the number is never used again). Only one at a time; there is no way to clear the whole list. This is the only `forget` that does not touch a saved note, so `backlog.<n>` cannot be a note name. | `forget backlog.3` |

Common ways to say undo and cancel work as the whole message (a trailing `.` or `!` and capitals are ignored). `undo that`, `undo it`, `undo last`, `undo the last change` and `please undo` are a bare `undo`: still a draft that needs `yes <code>`. `cancel that`, `cancel it`, `never mind` and `nevermind` are a bare `no`. They never take a code or extra words, never call the interpreter and do not count toward the daily limit. `forget it` is still a note command.

Saved notes never change the site, and pause does not affect them.

## Till changes (HASS-CLOVER-4)

Only when the till is connected for changes (a Clover write setup; without one Hass still answers till questions and replies
"I can read the till but I can't change it yet."). Each is one whole message in exactly these words, read by fixed patterns
**before** anything else reads the message, so prices and counts never go to the model or into a website change.

- `received 12 Sunshine olive oil` — Draft: `Add stock to ...? Count: 12 -> 24, Received: 12` (the till's count read live, plus 12).
- `set Sunshine olive oil to 7` — Draft: `Set the count of ...? Count: 12 -> 7`. `... to 0` is the sold-out draft.
- `Sunshine olive oil is sold out` — Draft: `Mark ... as sold out? Count: 12 -> 0`, only when the name is exactly a till item (otherwise it is the website's own stock words, as before).
- `new item: Sunshine olive oil, 12.50, pantry` — Draft to add a till item with a new SKU (the category is optional). Nothing goes on the website.
- `change price of Sunshine olive oil to 14.00` — Draft: `Price: $12.50 -> $14.00 each (+12.0%)`. One yes, even for a big change. Never on the website.
- `hide Sunshine olive oil on the till`, `show Sunshine olive oil on the till` — Draft to hide or show the item on the till. Nothing is ever deleted.
- `yes <code>` / `no <code>` — `yes` makes the change, reads the item back from the till and replies `Done, and I read the till back: ...`; `no` drops it.
- `undo <code>` — Drafts the change back (its own yes); it refuses when the item changed again since.

Every draft ends `Reply yes <code> to do this, or no <code> to drop it. Nothing changes until you say yes.` The code is 8
characters and works only from the owner who asked, in his own one-to-one chat; a group chat, someone else, an edit or a
reaction never drafts or approves. `stop changes` holds till yeses too. Over the daily limit the reply is "I have already made
20 changes to the till today, which is my daily limit. Nothing was changed. The count starts again at midnight Pacific."

**Count to 0 and back:** when the item is linked to a website product, a count reaching 0 also marks that product **Sold out**
(and a count up from 0 marks it Available today) in the same draft, under the same one yes. The till goes first; only when it is
read back does the website word go through the normal website change and its usual reply. If the website part does not go
through, Hass says "The till is updated; the website is not yet." The undo of such a change puts the website word back the same
way, only while the website still shows the word it set. The website word needs today's shelf check, as always: without one,
the `yes <code>` first asks "Before I change that, is the shelf list right for today?" and nothing changes, till or website,
until a bare `yes` (then the till, the shelf check and the website word go together) or `no` (the whole change is dropped).
If the website word changed after the draft (or the undo) was shown, nothing changes and Hass says so; the newer word stays.
`help` lists these sentences when the till is connected for changes. The conversation record keeps what you typed.

Cancelling a hike (a change request, needs `yes <code>`; not the `cancel <code>` command above, which only rejects a
waiting draft): say it in your own words, for example "cancel the Point Buchon hike, rained out - we will pick a new
date soon". `hike.cancel` takes the hike id and an optional `note`, for example `Rained out - we will pick a new date soon`.
The note is one line of plain text, at most 160 characters, and is public site copy: the cancelled hike's card shows it
exactly as written, above "This hike is cancelled." It is checked like other hike text (no markup, `$` or invisible
characters), and any claim in it, such as a distance or "organic", must come from your own message. Without a note the
card is unchanged. Cancelling notifies nobody. `undo` brings the hike back as scheduled and removes the note.

Photos: send 1 to 4 photos per message, as JPEG or PNG, up to 20 MB each. Each photo gets its own question and its own
code, in the order you sent them; answer each one with its code, the place and what it shows. A caption sent with
several photos is not read (the reply says so). If any one photo cannot be used, none of them is saved, and the reply
names which. Five or more photos in one message are refused. A phone photo's rotation is kept, so it shows upright
(only that rotation tag is kept, never its location, camera or date); only a PNG with a rotation tag is refused. Any
other file, or a photo that is too large, incomplete or unreadable,
gets a reply naming the limit, and nothing is saved or drafted.

A new product needs one brand. The card label (`displayBrand`) is optional: left out, the card shows that brand, and the
exact brand `Producer not identified` shows `From the market`. Give a label only to show something different; it changes
the card label only, not the maker link. Example: `Add Test Orchard quince, brand Test Orchard` with the photo. Hass
still asks for any other missing required fact and never invents one; the draft still needs `yes <code>`, and `undo`
works as for any change.

With `itemIntake: true`, a single product photo and your words make **one editable listing preview**:
name, brand, size, plain description, printed features/claims, shelf and any stock word you gave.
The preview is the review: there is no separate product confirmation, interview, claim-by-claim question
or “add claims” step. Send `bought 100 at $1, sell for $2` before, with or after the photo;
Hass keeps the numbers for the same listing. Cost, quantity and selling price appear in a clearly private
part of your chat preview and are saved to the private intake record after approval. The existing website
catalog has no price/count fields, so those numbers are not published or sent to the interpreter.
Normally only a missing selling price gets a question. If the picture cannot identify the item, Hass
needs its name; if you start with text only, it needs the product photo required by the catalog.
Unknown brand/location stays unknown; a new printed brand does not invent a maker profile or town.

Edit the preview with `remove Made in USA`, `add: great for furniture`, `price 3`, `name Wood Glue`,
`brand Gorilla` or `category pantry`. You get the updated preview with **the same code**; it refreshes
the exact approval hash, not an approval. `What's next` or `?` repeats the current preview instead of
getting stuck on a yes/no question. `yes <code>` applies the latest preview and `undo` still drafts an undo.
Printed text is not independent verification: the existing live-policy holds for origin/organic,
health and other protected claims still prevent publication where applicable and the preview says so.
Forbidden text, photo-price filtering, expiry, pause and owner approval gates are unchanged. Long label
text beyond the catalog description limit is explicitly listed as private overflow, not silently published.
Nothing in this intake prepares or writes a till item. The till half of “both” remains separate.

With `itemIntake` off, the earlier new-item flow is unchanged:
a new item from a photo (a change request, needs `yes <code>`): send the photo with a few words (what it is, who makes it,
which shelf, whether it is in). Hass asks one short question at a time for what is missing and shows one draft: the product, the
maker when new, the picture, the description and the shelf check. One `yes <code>` saves all of it and one `undo` takes all of
it back. The picture is made to match the others (an ivory square, the item in the middle). A photo on a busy background, or one
too dark, too blurry or too small, is not used: Hass asks you to take it again on a plain surface. The description is written in
the shop's voice from your words, never with a price, a size, where it comes from, organic, a health claim or an award; wording
of yours that carries one is replaced and listed under "Left off". Such a claim in the name, the maker's story or the picture
caption is refused in plain words and written down for Graham. A maker already on the site is reused. For a new maker Hass asks
"What should we say about <Maker>? A sentence is enough." and uses your words; if you send the maker's own web address it also
writes one or two short sentences from facts on that page (what they make, since when; the site's robots file obeyed, no
sentence copied), shown with the address and day; they go live only with your yes. Send `skip` to keep only the town line.
The maker's web address is never published. One photo is one product, and the new item uses one of the day's live-change slots.

Two kinds of whole message are not change requests and never reach the interpreter or the daily count: only thanks or
a greeting (`thanks`, `thank you`, `great, thanks`, `hi`, `hello`, `good morning`, any case, with a final `.`, `!` or
`?`), or only emoji. Emoji that are all thumbs-up, OK-hand or check marks get the near-approval answer (nothing is
applied; reply `yes <code>` to approve). Anything else of this kind gets `Nothing changed. Send a change in plain
words, or help.` They work while paused and after the daily limit, and nothing is approved. A message with any other
word, such as `thanks, make the eggs sold out`, is read as below.

A single word of four or more letters that is one letter off a command word (`histroy`, `staus`, `reprot`, `memroy`, `undp`: one
letter added, left out or changed, or two letters swapped) gets only a guess: `Did you mean status? Send status.` (both names, in
alphabetical order, when two fit, such as `stow`: `Did you mean show or stop? Send show or stop.`). The guess is never run: send the
word again to run it. It uses no reader call and no part of the daily limit, works while paused, and approves, cancels or changes
nothing. Real words (`fine`, `shop`, `past`, `most`, `hold`), `yes`, `no`, thanks, the casual yeses and every longer message are
handled as before.

Any other message is read once by the reader (one counted interpreter call). If it only asks what the site, shop or hikes
show (`how many are coming Saturday?`, `is the sourdough sold out?`, `what's on the dairy shelf?`, `what are my hours?`), the
reader may only pick one read-only command: `status`, `report`, `history` (with or without words), `find <words>`,
`listing <id or store>`, `shelf <name>` or `hidden`. Hass then replies `You asked, so nothing was drafted.` followed by exactly
that command's own reply. Nothing is drafted, approved, saved or expired by a question. Any other pick (`yes`, `no`, `undo`,
`stop`, `resume`, `remember`, `forget`, `alias`, or a word Hass does not know) gets only `Nothing changed. To look something up,
say status, report, or find and a few words.` Any other message is read as a change request, and a question that asks for a
change (`can you mark the eggs sold out?`) is still a change. Hass replies with a draft and its code (or a question if details are
missing). A draft is never applied until you reply `yes <code>`; drafts that wait too long expire and nothing changes.

New products (a change request, needs `yes <code>`): a product you add shows a "New" badge on its card for its first
14 days (counted in Pacific calendar days from the day it was added, worked out in the visitor's browser). Editing,
hiding or restoring a product, or undoing and restoring an add, never starts the 14 days again, and the products that
were already on the site have no "New" badge.

Checking the selection (change requests, not commands; each still needs `yes <code>`):

- `store.confirm_selection`: tell Hass you checked the shelves, for example "I checked the selection today: the
  avocados are in, the eggs are limited, the sourdough is sold out." The site then says "Selection last checked by
  Michael on <day>." and the named products show "Available today", "Limited" or "Sold out". You may name an
  earlier day you checked, never a future one or a day before the last recorded check. Products you do not name keep
  their last word, shown as "Last confirmed <day>" with the day they were last named.
- `product.set_availability`: change one product's word ("the eggs are sold out"). After your first recorded shelf check it
  needs no check today: the word gets its own day (Pacific today) and your last full check does not move, so the site
  still says "Selection last checked by Michael on <last full check>". The proposal says, for example, "Sold out from
  today (your last full shelf check was Monday, November 2)". The card shows the word while its own day is not older than
  that last check and not more than 7 days old, otherwise "Last confirmed <its day>" (so a newer full check that does
  not name the product, or the same word 8 days later, shows "Last confirmed"). Saying the word it already has changes
  nothing. With no recorded check at all (none yet) Hass does not refuse: it asks "Before I change that, is the shelf list right for
  today? Reply yes if it is, or tell me what is different.", keeps your request, and writes nothing. Your own bare `yes`
  then drafts one change that records today's check and makes the original change, which still waits for your normal
  `yes`; `no` closes the question and changes nothing; any other message is read as your next request (and an
  availability change asks again). The question closes after 30 minutes or at your next message of any kind, only you can
  answer it, and `yes <code>` still only approves that draft. A check dated after today is not asked about: Hass says the
  date looks wrong.
- `product.clear_availability`: take one product's word off its card ("stop showing the eggs as sold out"). Only that
  product changes: its word and its own check day are removed, so it is back to not confirmed (no word on the card).
  It never sets "Sold out" and leaves the store's selection check and every other product alone. It needs `yes <code>`
  even if shelf-check changes are set to apply automatically. It is refused when the product has no word set, is
  hidden or is held. `undo` puts the word and its day back exactly as they were.
- `product.set_availability_all`: one change for a whole shelf or maker ("all the vegetables are in today", "everything
  from Cal Poly is sold out"), instead of one change per product. Name a shelf, a maker or both (both means only the
  products on that shelf from that maker); with neither Hass asks which. It changes only the active products that do not
  have that word yet; hidden and held products and products already showing it stay as they are, and it is refused when
  none would change. The proposal gives the count and up to 10 names (with ids), then "... and N more". It needs the
  ordinary `yes <code>` (even if shelf-check changes are set to apply automatically), is one change, and `undo` puts each
  product's old word and day back. Each changed product gets its own day (Pacific today) after your first recorded
  shelf check, with the same "from today" explanation and the same seven-day card rule as `product.set_availability`; it
  never records a shelf-check date and does not move "Selection last checked"; only `store.confirm_selection` records that
  you checked the shelves.
- Until the first check the site shows no check line and no availability words. If
  the last check is more than a week old when the site is generated, the line adds "(more than a week ago - call or
  visit to confirm)" and the product words become "Last confirmed <day>". Hidden and held products never show them.

A maker without a website: `maker.add` needs only the key, name and place (the story is optional, see below); leave `url`
out and the maker's card shows its story and place with no "Visit" link. `maker.edit` with `clearUrl: true` removes a
maker's website (it cannot be combined with `url`); a maker with no website and nothing else changed is refused. Both are
change requests that need `yes <code>`, and `undo` restores the website exactly as it was. A website recorded as a
migrated source link cannot be removed: the change is blocked.

A maker without a story: a maker needs no story and no website, and Hass never writes a story you did not give. Say only
the name and place and the maker is added without one (a maker change request, no new command). The card's "Meet the
maker" panel then shows the place and the website link, or no panel at all when there is neither a story nor a website.
`maker.edit` with `clearStory: true` removes a story only when you explicitly ask (it cannot be combined with `story`; a
maker with no story and nothing else changed is refused). Both need the ordinary `yes <code>`, and `undo` restores the
story exactly as it was. `post maker <key>` for a maker with no story says so and writes no caption.

Home-page photo (a change request, needs `yes <code>`): `store.clear_home_image`, for example "put the old photo back",
shows the shop's own photo on the home page again, whatever store changes came after you set yours. It is refused when
no photo of yours is set; `undo` puts your photo back.

Hiking club opening paragraph (a change request, needs `yes <code>`; not a command, so it has no table row and no help line):
`club.set_intro`, for example "change the hiking club intro to: Mornings on the coast are for friends, fresh bread and a
long walk.", replaces the whole paragraph that opens the hiking club page (the line above "At the Shack, we care about what
feeds us"); nothing else on that page changes. Send the whole new paragraph. For a partial edit Hass starts from the
current words it keeps for the page and resends everything you did not change exactly, or asks you if it cannot see them.
It must be one paragraph of plain text, 20 letters to 400 characters: tags, links, `$`, `{{ }}` and line breaks are refused,
and so are the same words as now (extra spaces do not count as a change). Until you set one the page keeps its usual words.
Hass checks the page on a phone and on a desktop screen after it saves. `undo` puts the previous words (or the usual ones)
back; it is refused when the hiking club settings changed again after that change, so undo the later change first. Saved is
not published: the words are on the website only after the separate step that copies the saved site there.

Stop carrying a maker (a change request, needs `yes <code>`): `maker.hide` with `withProducts: true`, for example "we stopped
carrying Etto", hides the maker and all of its active products in one change. The proposal lists the maker and every
product id it will hide. Hidden and held products are left exactly as they are. Without `withProducts`, a maker that
still has active products is refused and the reply names them. `undo` brings the maker and every product back together.

When you ask for a design change (colours, fonts, layout, a new page) Hass says it cannot be made by message yet, keeps your first 500 characters as a dated note `design.<n>` for the developer, and says so. The note is kept here only: nothing is sent, the website does not change, and it is never used as a preference by the interpreter. `forget design.<n>` removes it.

Notice windows and shelf checks in a proposal: when a change touches the home notice or the shelf check date, the proposal and a later `show` repeat both the old and the new value in words, for example `Home notice: from nothing to Closed Thanksgiving Day - through Thursday, November 26` (or `- from Wednesday, November 25 through Thursday, November 26` when a first day is set) and `Shelf check: from Monday, November 2 to Tuesday, November 3`, so a wrong day is visible before you say yes. `undo` reads the same way with the days reversed and still needs your yes.
