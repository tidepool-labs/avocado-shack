# Clover count phrases: offline baseline

Exact matches: **41/60 (68.3%)**.
On [60 new synthetic phrases](../../hass/tests/test_clover_count_phrases.py), the HCI-03 parser with its four false-accept refusals got 11/30 counts or arrivals right and refused 30/30 non-counts. An exact match includes mode, quantity, unit and lookup query, or `None` for a refusal. This measures parsing only, not product lookup, previews or till changes.

| Category | Phrases | Exact |
| --- | ---: | ---: |
| word order | 5 | 2 |
| shorthand | 5 | 1 |
| units | 5 | 2 |
| number words | 5 | 3 |
| shelf words | 5 | 1 |
| typos | 5 | 2 |
| vague | 5 | 5 |
| money | 4 | 4 |
| two products | 5 | 5 |
| questions | 5 | 5 |
| prices | 4 | 4 |
| hikes | 3 | 3 |
| website edits | 4 | 4 |

**HCI-21:** No false accepts remain (the four former ones are refused by bounded rules in `qty_words.py`); keep it that way before widening the grammar. For the positive gaps, `code` means the parser can learn the phrasing; `ask` means clarify rather than guess whether to set a total, add an arrival or just move stock. Fix command typos without guessing product names.

| Positive gap | Fix class |
| --- | --- |
| `12 apricot jams just came in` | code |
| `30 blue mugs in` | code |
| `the glass pitchers just arrived, 9 of them` | code |
| `blue mug x30` | code |
| `x14 linen bags` | code |
| `pan scrapers = 11` | code |
| `+7 lemon soaps` | code |
| `we have 4lb of dried cherries` | code |
| `just got 6 lb of split peas` | code |
| `we have 15 each of the wax wraps` | code |
| `we got a dozen and a half cake boxes` | code |
| `a hundred and six paper straws` | code |
| `put 30 mugs on the shelf` | ask |
| `only 4 cedar soap dishes left` | code |
| `we have 18 cork trivets in stock` | code |
| `on the shelf there's 7 butter crocks` | code |
| `recevied 8 maple spreaders` | code |
| `there re 5 mixing bowls` | code |
| `5 bown sugar scoops on the slehf` | code |
