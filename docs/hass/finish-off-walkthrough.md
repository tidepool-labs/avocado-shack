# The OFF walkthrough in one command (finish line, offline)

**What this is:** one script an attending owner runs to rehearse the whole listing path in a throwaway shop: check the tools
checkout, check the photo, see the preview, give the one coded yes, look at what a visitor is served, then take it down with
one more yes. It prints PASS or FAIL for each step with the seconds it took and the total, and stops at the first FAIL.
**What it is not:** a live listing. It never touches Clover, the real site or any service, and it uses only a loopback address
on this computer. The real attended proof on the hidden TESTITEM is still the checklist in
[finish-hidden-testitem.md](finish-hidden-testitem.md) and [CLOVER-TESTITEM.md](CLOVER-TESTITEM.md). Test:
`hass/tests/test_hidden_listing_walkthrough.py` (L11).

## Run it

```
python3 -B scripts/hass/hidden_listing_walkthrough.py \
  --repo <tools checkout> --sha <reviewed 40-character commit> --remote-url <expected origin URL> \
  --photo <a PNG or JPEG file> --out <private receipt folder>
```

The receipt folder must already exist, be private (mode 0700) and sit outside both the tools checkout and this repository. The script writes one small
receipt there per run: step names, seconds, counts and 12-character photo fingerprints only. No photo, file path, code or chat
text goes in the receipt or on the screen.

## The steps

| Step | Passes when | A FAIL means |
|---|---|---|
| checkout | the tools checkout is exactly the reviewed commit, clean, with the expected origin (the existing `install_tools_checkout.py` check) | wrong commit, a changed or extra file, or the wrong origin. Nothing is made. Fix the checkout, run again. |
| photo | the file exists, is a plain file (not a link or folder), is a whole, readable PNG or JPEG (the real photo check, not just the first bytes), and is neither empty nor larger than 8 MB | missing or odd photo. No preview is made. |
| preview | the card is made from the supplied photo (same fingerprint), nothing is saved yet, and the site is unchanged | the card shows a different photo. **No yes is sent.** |
| confirm | one coded `yes` saves exactly one change and the public card is the approved one (name, descriptor, public price, photo description, photo) | the saved card is not what the preview showed |
| served | what a visitor is served over loopback equals the approved card; no cost, count or chat id | the page or the photo is not the approved one |
| takedown | `undo` alone changes nothing a visitor sees; one coded `yes` removes the card and the served catalog is byte-identical to before | the card is still public after the take-down |

## Time

A good run on this fixture takes about 2 to 3 seconds in total on the build machine (preview about 1 second, the rest well
under a second each). Real timing with a real phone and real replies will be longer; the receipt is the place to compare.

## For G-H

1. Run it with a **copy** of a synthetic photo first, never a private one.
2. A FAIL at `checkout` or `photo` is cheap: fix that and run again. A FAIL at `preview` or later means stop, keep the receipt,
   and tell the builder; do not retry in a loop.
3. A PASS here is not a go-live. The live hidden-item proof stays an attended step.
4. Keep receipts local. Never paste them into Git, a ticket or a public chat.
