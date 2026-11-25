# The comparison after the yes (OFF demo, finish line)

**What this is:** one small read-only command for the person attending the demo, to run right after the `yes`. It compares what
the shop is serving with the card that was approved: the name, price, descriptor, picture text, shelf and brand, and the exact
photo bytes. If anything differs it prints `MISMATCH <reason>` and you take the listing down (`undo`) and report it.
**What it is not:** a yes, a take-down or a live listing. It never sends a message, writes a file or touches Clover, the site or
any service. It does not look at the approval history: "posted" in the chat does not make a mismatch pass. It is the sibling of
the check before the yes (`docs/hass/finish-demo-pre-yes-gate.md`, its `after` word only compares the photo). Test:
`hass/tests/test_demo_served_comparison.py` (L17).

## Run it

```
python3 -B scripts/hass/demo_served_comparison.py --state <state-dir> --worktree <shop worktree> \
    --job <job id> --photo <the photo file you hold> --version <n>
```

Prints `MATCH undo` (exit 0): the shop serves exactly the approved card, and `undo` is the one-step take-down word. Anything else
is `MISMATCH <reason>[,<reason>...]` (exit 1, reasons sorted). Output is only fixed words: no name, price, text, path, id or
picture is printed. Every path (state, worktree, photo, served photo) must be free of links: each part is opened without following
a link. A link anywhere on a path is refused.

## Reasons

| Reason | Meaning |
|---|---|
| `photo-unreadable`, `no-such-listing`, `photo-mismatch`, `version-mismatch` | the photo you hold is not this listing's photo, or the job or version does not exist |
| `not-approved` | no yes has been typed for this version yet (there is no approved card to compare) |
| `approved-card-missing` | the saved approved card is missing or its photo does not match the version |
| `catalog-unreadable`, `could-not-check` | the shop's catalog or the saved conversation could not be read safely |
| `not-served` | no served item carries the approved name (also: the record now claims another item's name) |
| `name-differs`, `price-differs`, `descriptor-differs`, `picture-text-differs`, `shelf-differs`, `brand-differs`, `maker-differs` | that served field is not the approved one |
| `display-brand-differs` | the brand a visitor actually sees (the record's `displayBrand`, else `brand`, as the shop page shows it) is not the approved one; the approved one is the card's `displayBrand`, else the catalog's own default for its brand ("From the market" for an unidentified producer) |
| `served-photo-unreadable` | the served photo file is missing, is a link, or its path leaves the shop |
| `served-photo-differs` | the served photo bytes are not the approved photo (a stale or another owner's photo, even when the catalog is right) |
| `photo-on-another-item` | a different served item shows the approved photo (a wrong neighbor) |
| `other-photo-unreadable` | another served item names a picture that is a link, is missing, or leaves the shop folder: the command fails closed, because a site might still follow a link to the approved photo |
| `duplicate-served` | the approved item is served twice (a leftover record) |
| `non-public-field` | the served record has a field outside the public set (id, name, brand, category, image, description, producerKey, displayBrand, imageAlt, sellingPrice, addedOn) |
| `private-word` | a served field mentions cost, qty, quantity, stock, count, margin, wholesale or supplier (whole words) |

## Proven offline (fixtures, no service)

On a restored OFF install with two owners' cards waiting: before any yes, both listings print `not-approved`. After Mike's one yes
the command printed `MATCH undo` and every mismatch above printed its reason while the approval row was still on file. The other owner's
listing still printed `not-approved`, and asking about Mike's listing with the other owner's photo printed `photo-mismatch`. The transcript bytes, commits, public names,
approvals and the worktree status were identical before and after every run. Each check was mutation-tested: disabling the photo,
field, shown-brand, neighbor-photo, unreadable-neighbor, duplicate, non-public or private-word check made the test fail.

## Limits

- Fixture proof only. It does not prove the private 38/38 replay or the attended hidden TESTITEM on the real shop.
- It compares the served photo with the approved photo byte for byte. If a real install serves a re-encoded copy,
  it prints `served-photo-differs`; treat that as "compare by eye and stop", not as proof of a wrong listing, and report it.
- `private-word` is deliberately blunt (whole words, any case): a descriptor that legitimately says "count" would print it. Report it
  rather than ignoring it.
- It can only see the worktree and the state it is pointed at, not the live shop.
