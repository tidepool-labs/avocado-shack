# Hass listing edits: grammar-only baseline

On 65 synthetic owner texts, **grammar: 39** (patch or picture reply), **ask: 13** (recognized form asks instead of editing), **mapper: 8** (would reach an installed mapper; without one, returns `ask_edit_unclear`), **unclear: 5** (no form and no mapper call; returns `ask_edit_unclear` even with a mapper installed). HRM-14 **fixed: 16** of the 29 HRM-05 mapper and unclear rows in `hass/npp/edits.py` alone, with no asset or pin change. The [full fixture table](../../hass/tests/test_npp_edit_phrases.py) measures `edits.read`, not chat intake or model accuracy: raw prices are tested as typed, and separately labeled finance-split fixtures show what happens after local parsing supplies the price and unit. `add: great on toast` asks instead of copying the suggestion to the listing.

## How HRM-14 reads more without a model

If the pinned forms don't read a text as typed, Hass tries its everyday wording once. Any text a form read before is read the same way as before. The rules:

1. **Courtesy and end punctuation.** A leading `please`, a trailing `please` or `thanks`, and a trailing `.` or `!` are dropped. A `?` stays, so a question is never read as an edit.
2. **Quotes around a value** are removed, so `call it "Wildflower Honey"` reads like `call it Wildflower Honey`.
3. **Everyday lead-ins** at the start become the form's own: `change/set/switch/swap/update the name/maker/supplier/source/category/shelf to`, `rename it to`, `move/put that to/in/under`, `make the description`, `use the photo I just sent`. Each lead-in can match only the form it names, so a wording request cannot become a price edit. The value is still his words and the form still checks it. A tentative rename does not produce a local patch, and a category edit must name a known shelf.
4. **A degree word** before a wording change (`a little`, `a bit`, `slightly`) is dropped.
5. **A named amount or a lone unit** (`make it four bucks`, `per pound please`) goes to the price form. The price still comes only from the code-parsed finance slots, so without one Hass asks for the price. An unsure amount is not read.

At load, the grammar also checks each pinned negative in its everyday wording. Extra guard phrasings in the test file pin where these rules stop.

## Fixed by HRM-14

| Owner text | HRM-05 | Now |
| --- | --- | --- |
| `make it 4 bucks` | `ask_edit_unclear` | `ask_price` |
| `$4.50 a pound` | `ask_edit_unclear` | `ask_price` |
| `make it four bucks` | `mapper` | `ask_price` |
| `four dollars and fifty cents a pound` | `mapper` | `ask_price` |
| `sell it for five dollars each` | `mapper` | `ask_price` |
| `per pound please` | `mapper` | `ask_price` |
| `call it "Wildflower Honey"` | `mapper` | `patch name` |
| `rename it to Orchard Honey` | `mapper` | `patch name` |
| `call it Wildflower Honey!` | `mapper` | `patch name` |
| `swap the supplier to Lantern Kitchen` | `mapper` | `patch supplier` |
| `shorter please` | `mapper` | `patch rewrite` |
| `make the description a little shorter` | `mapper` | `patch rewrite` |
| `move that to dairy` | `mapper` | `patch category` |
| `put it under fruit please` | `mapper` | `patch category` |
| `use my photo please` | `mapper` | `picture_request` |
| `use the photo I just sent` | `mapper` | `picture_request` |

The price rows ask for the price when replayed without finance slots; the edit text is never the source of the amount. When local intake supplies a parsed amount, the recognized price request can produce a price patch from that slot.

## Rows left

| Owner text | Mapper eligibility or local ask ID | Left for | Reason |
| --- | --- | --- | --- |
| `each not per lb` | `mapper` | model | a correction with not is unsure wording, and a unit with no code-parsed price still asks for the price |
| `actually 4 or 5 bucks` | `ask_edit_unclear` | by design | an unsure amount is asked, never guessed, and a digit never reaches the model |
| `it's Miners' honey` | `mapper` | model | the name could be the maker, the supplier or part of the product name, and code cannot tell which field |
| `no maker` | `mapper` | HRM-33 | clearing a field has no typed patch: a value must be his words, so a blank needs a clear action in the assets |
| `leave the maker blank` | `mapper` | HRM-33 | clearing a field has no typed patch: a value must be his words, so a blank needs a clear action in the assets |
| `take the source off` | `mapper` | HRM-33 | clearing a field has no typed patch: a value must be his words, so a blank needs a clear action in the assets |
| `make it 2 lines shorter` | `ask_edit_unclear` | HRM-33 | a length has no typed slot, reading it as plain shorter would drop his number, and a digit never reaches the model |
| `say it's nice with tea on a cold day` | `mapper` | HRM-33 | owner copy is never pasted (F1), so it needs a typed note slot and a reviewed template |
| `category: snacks` | `mapper` | HRM-33 | snacks is not one of the ten shelves; a shelf synonym table is an asset change, and guessing a shelf is not safe |
| `use photo 2` | `ask_edit_unclear` | HRM-33 | a photo number has no typed slot, and a digit never reaches the model |
| `asdf hjkl` | `mapper` | model | there are no words to read; the model may still answer with one question |
| `what did you put for the maker` | `ask_edit_unclear` | by design | a question to Hass is not an edit; chat routing gives it its normal answer |
| `Hass, is this on the site yet?` | `ask_edit_unclear` | by design | a question to Hass is not an edit; chat routing gives it its normal answer |

## Notes for HRM-33

- The pinned name and supplier patterns take a trailing courtesy word into the value: `call it Wildflower Honey please` sets the name `Wildflower Honey please`, and `from Etto please` sets the supplier `Etto please`. Those forms read the text as typed, so HRM-14 leaves these HRM-05 rows unchanged. The fix belongs in the asset patterns.
- `Stages.takes_turn` in `hass/npp/reply.py` routes a turn by `Grammar.match`, so while a card is out the everyday wordings above now count as edits. A lone unit (`per pound please`) still doesn't start an edit turn there.
