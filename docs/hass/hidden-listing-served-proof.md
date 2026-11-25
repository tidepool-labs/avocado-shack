# Hass served-page proof for a listing (finish line, offline)

**What this proves:** what a visitor's browser is *served* for a listing (the Market page, the catalog script, the item photo),
fetched over HTTP from the site folder of a throwaway repo, is exactly the version the owner approved. **What it does not
prove:** anything on the real site, a real browser render, Clover, or the phone. The real attended proof is the checklist in
[finish-hidden-testitem.md](finish-hidden-testitem.md) and [CLOVER-TESTITEM.md](CLOVER-TESTITEM.md).

Test: `hass/tests/test_hidden_listing_served_projection.py` (fixtures only, loopback `127.0.0.1`, no network beyond it).

| Step | Served page must show | Fails when |
|---|---|---|
| publish (one coded yes) | the approved name, descriptor, public price, photo description, and the approved photo bytes (SHA-256 from the approved draft, not from the site); only public fields; no chat or sender id in the served catalog | any field differs, a field is non-public, a field name or any word inside a field value (the approved descriptor included) is cost/qty/quantity/stock/count/margin/wholesale/supplier, the photo is missing or different, the Market page has no runnable `<script src>` element that resolves (against the page address and any `<base>`) to the same-origin catalog at `/catalog-products.js` that the proof fetches (a comment, visible text, an inline script, a `link`, a non-JavaScript `type`, a script inside `<template>` or `<noscript>`, a different path, file name or origin does not count) |
| edit | the edited descriptor and nothing else changed (the old approval no longer matches the page) | the old descriptor is still served, or any other field or the photo moved |
| take-down (editor hide, or chat `undo` + one yes) | the card is not served; the served catalog bytes equal the pre-publication site; `undo` alone changes nothing a visitor sees | the card is still served |
| stale photo (a cache still holds an older image) | fails with `the served photo is not the approved photo`, **even though the catalog record is right** | passes |
| stale catalog (a cache holds the catalog from another version) | fails with `the card is not on the served page` or `served description is not the approved one`, **even though the photo is right** | passes |

## Operator checklist for the attended proof (G or Mike present; no agent runs it)

1. On the live hidden TESTITEM only, after each step, open the item the way a visitor does (a private browser window, not a
   logged-in one) and compare name, descriptor, price, photo and photo description with the preview card you approved.
2. After an edit or a photo change, reload with the cache bypassed (hard reload). If an old photo or text still shows, **stop**:
   that is the stale-page case this test names; do not approve the next step.
3. After take-down, the item must not appear on the Market page or by its direct link; look at both.
4. Do not paste screenshots, transcripts or codes into Git, a ticket or a public chat.

## Limits

- The test serves files from disk with a stand-in for a stale cache; it does not exercise the real web host, CDN or browser
  JavaScript. A render in a real browser is the attended step above.
- The photo is compared by bytes (SHA-256), not by how it looks.
