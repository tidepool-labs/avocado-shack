# Clover TESTITEM inventory proof

**Attended only: G must watch the whole step. No agent runs it.** Start only
under the separately approved Clover write go-live in [CLOVER.md](CLOVER.md),
after a clean read-only day. G handles the separate write-token setup. Use
Mike's private owner chat. Check that TESTITEM is unused and that `pantry` maps
to an existing till category before starting. The price and count below are
made-up test values, not store inventory.

Send these in order, one at a time. For each, inspect the preview before the
same owner replies `yes <code>` (replace `<code>` with that preview's code).
Wait for “Done, and I read the till back” before sending the next sentence.

1. `new till item: TESTITEM, 1.23, pantry` — The preview should show TESTITEM,
   a new SKU, the test price and the mapped category (not “none”), with no
   count yet and no website change. The read-back reply should confirm the
   item and its SKU.
2. `set TESTITEM to 7` — The preview should show that same item and the count
   changing from not counted to 7, with no website change. The read-back
   reply should say it now shows 7.
3. `hide TESTITEM on the till` — The preview should say showing → hidden for
   that same item. The read-back reply should say it is hidden. Leave it hidden;
   do not make another change to the item. G checks that it is not findable
   on the register.

Stop if a preview differs, a write is refused, or the outcome is uncertain.
G reconciles it before anything else is sent; don't resend an uncertain write.

From the repo root, the operator checks private, quiescent state (or its
private offline copy), using the matching host configuration:

```text
python3 -B scripts/hass/clover_write_readiness.py --host <private-host-config> --for inventory
```

Require exit 0, `result: pass` and `testitem_inventory: ok` before moving on
to any real item. This command reads local evidence; it doesn't contact Clover
or verify the register itself. Keep the journal and receipts private.
