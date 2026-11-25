# The check before the yes, and the check after it (OFF demo, finish line)

**What this is:** one small command for the person attending the demo. Before you type `yes <code>`, it checks that the
listing, the picture you are holding, the version, the card that was really delivered in the chat and the shop all line up. If
anything does not match it prints `ABORT <reason>` and **you do not type the yes**. After the yes it checks that the shop is
serving the same photo, and reminds you of the take-down word.
**What it is not:** a yes, an approval or a live listing. It only reads. It never sends a message, writes a file or touches
Clover, the site or any service. The yes is still typed by G or Mike in their own chat. Test: `hass/tests/test_demo_pre_yes_gate.py` (L15).

## Run it

```
python3 -B scripts/hass/demo_pre_yes_gate.py before --state <state-dir> --media <media-dir> --worktree <shop worktree> \
    --job <job id> --photo <the photo file you hold> --version <n>
python3 -B scripts/hass/demo_pre_yes_gate.py after  --state <state-dir> --worktree <shop worktree> \
    --job <job id> --photo <the same photo file> --version <n>
```

`before` prints `READY yes <job>-<n>` (exit 0): type exactly that line, once. Anything else is `ABORT <reason>` (exit 1) and the
line to type is not given. `after` prints `SERVED undo` (exit 0): the shop serves your photo; `undo` is the one-step take-down.
Output is only a fixed word and reason; no name, text, path, id or picture is printed.

## What READY means (all must hold)

| Check | ABORT reason when it fails |
|---|---|
| the job exists | `no-such-listing` |
| the photo in your hand is the one this listing was started from | `photo-mismatch` |
| the listing is waiting for a yes (not already approved, closed or still being made) | `listing-not-waiting-for-a-yes` |
| the version is the newest one and the one you hold | `version-mismatch` |
| that version's card was delivered (confirmed) | `card-not-delivered` |
| the card file in the media folder is the delivered card (same bytes) | `card-bytes-missing-or-changed` |
| the saved chat has an outgoing message with that card | `card-not-in-chat` |
| a card showing the owner's own photo shows this photo | `card-photo-differs-from-listing-photo` |
| the listing has a name and the shop does not already serve it | `listing-has-no-name`, `already-served` |
| the photo file can be read (a plain PNG/JPEG file, not a link) | `photo-unreadable` |
| the shop's catalog can be read | `catalog-unreadable` |

`after` aborts with `photo-mismatch`, `not-served` (the listing is not in the served catalog) or `served-photo-differs` (the served
photo file is not your photo).

## Proven offline (fixtures, no service)

On a restored OFF install with two owners' cards both waiting, the matching trio for each owner was READY, and ten mismatches
(the other owner's photo both ways, version 2 when only version 1 exists, an unknown job, a card file changed, a card file missing,
a card not in the chat, a card saved but never delivered, a bad job id, an unreadable photo) each ABORTed with the transcript,
commits, public names and approvals unchanged. After one yes the served photo was that owner's photo, the other owner's card was
still only a card (its gate stayed READY), a second gate for the same listing refused, and `undo` took the listing down.

## Limits

- Fixture proof only. It does not prove the private 38/38 replay or the attended hidden TESTITEM on the real shop.
- `after` compares the served photo file with the photo you hold, byte for byte. If a real install serves a re-encoded copy of
  the photo, `after` will say `ABORT served-photo-differs`; treat that as "compare by eye and stop", not as a failed listing, and
  report it. The gate cannot see the live shop, only the worktree it is pointed at.
- A version-mismatch for a real version 2 edit uses the same check with the newer version; the fixture only has version 1.
