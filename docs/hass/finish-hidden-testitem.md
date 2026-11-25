# Hass hidden-item drill: preview, publish, edit, hide, restore (finish line, offline)

**What this proves:** with the real chat, NPP job, editor and local writer on a throwaway repo, a listing can be published
with one coded yes, edited, hidden in one step, put back exactly, and hidden again, and the public card is always what the
step should give. **What it does not prove:** anything on the real site, in Clover or on the phone. The real attended proof
is in [CLOVER-TESTITEM.md](CLOVER-TESTITEM.md); this page is the rehearsal and the checklist for what to look at.

## Rehearsal result (fixtures only, main `dd21b6cd`)

Driver: `finish/hass-listing/hidden-drill/hidden_drill.py` (agent-work; it reuses `hass/tests/test_npp_undo_journey.py`).
Run: `python3 -B hidden_drill.py <repo> <receipt-dir>`. Result **pass**, 0 service calls, 0 network calls, no private text in
the receipt.

| Step | What happens | What is compared | Result |
|---|---|---|---|
| publish | owner photo + `sell $12.34`, card preview, one `yes <code>` | public card = name, descriptor, price, photo description, photo bytes (SHA-256) | card present; price and photo description as sent; no cost/qty/quantity field anywhere |
| edit | editor draft `product.edit` changes the descriptor only | same fields | only the descriptor moved; name, price, photo description and photo bytes identical |
| hide | `product.hide`, one step | public catalog bytes | card gone; catalog bytes equal the pre-publication site; product kept as `hidden` |
| restore | `product.restore` | public card | exactly the edited card returns, photo bytes included |
| hide again | `product.hide` | catalog bytes, repo status | card gone, catalog equals pre-publication, repo clean |

Together with the chat undo test in `hass/tests/test_listing_finish_journey.py` (`undo` drafts, one coded `yes` hides), the
take-down is one step both through chat and through the editor.

## Operator checklist for the attended proof (G or Mike present; no agent runs it)

1. Use only the hidden TESTITEM from [CLOVER-TESTITEM.md](CLOVER-TESTITEM.md). It stays hidden at the end; no real item is listed.
2. Before each `yes <code>`, read the preview card: name, descriptor, public price, photo and photo description. Confirm
   there is no cost, count or private word. A mismatch means stop.
3. After publish, look at the item page once, then say `undo`. Nothing changes until the second message `yes <code>`
   with the **new** code. After that one yes, the item must be gone from the site and the register view must stay hidden.
4. Keep the private transcript and receipts local. Never paste them into Git, a ticket or a public chat.
5. Stop if a preview differs, a write is refused or the outcome is unclear; do not resend an uncertain write.
