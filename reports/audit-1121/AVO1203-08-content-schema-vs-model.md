# AVO1203-08 — Hass content fields and migration baseline

| File under `hass/content/` | Records checked | Result |
| --- | --- | --- |
| `products.json` | 172 products: 170 active, 0 hidden, 2 held (plus 2 nested hold objects) | All present fields fit the model; held records have a different required set. |
| `makers.json` | 26 maker profiles | All fit the model. |
| `community.json` | 1 club, 3 route ideas, 0 real events | All present records fit the model. |
| `store.json` | 1 store, with 2 hours strings | Fits the model. |
| `migration-baseline.json` | 1 snapshot containing 170 listing IDs, 26 maker keys, 30 source entries, 2 held IDs and 6 output hashes | Snapshot shape and preservation checks pass. Only 2 of 6 historical hashes match; all 10 current outputs match the checkout. |

Evidence: fresh `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, equal to the supplied baseline for this audit. Quoted results below are from offline reads on 2026-11-21 (Pacific). The separate *historical migration base* is identified in R3. This checks committed JSON and local generated files, not a running site, live services, provenance truth, rights or policy decisions. The brief's `reports/hass-npp/G-QUESTIONS.md` was not tracked at this main (`git ls-tree -r --name-only origin/main -- reports/hass-npp`); the brief's exclusions still apply.

## R1. Record inventory and field sets

Pointers are relative to the file in each row. Ranges and `*` are shorthand for every member of the array or map, not literal JSON pointers. `U` means present in at least one record; `I` means present in every record. `U = I` gives the exact field set of each record in that row. For one object, both sets are its own keys. The empty events array has no observed intersection. All four content roots require integer `schemaVersion` equal to `1` (`hass/content_model.py:154–179`).

| File / record pointers | Count and observed keys | Required by the model | Optional or conditional |
| --- | --- | --- | --- |
| `products.json` root | 1; U = I: `schemaVersion, products` | Both; `products` is an array | None (`content_model.py:154–176,259–262`). |
| `products.json` `/products/*` | 172; I: `id, name, brand, category, image, status`. U: I + `description, displayBrand, producerKey, hold`. `/products/0`–`/products/169` each have I + `description, displayBrand, producerKey`; `/products/170`–`/products/171` each have I + `hold`. | I for all. Active and hidden also require `description, displayBrand, producerKey` (`producerKey` is nullable); held require `hold`. | All statuses may have `imageAlt, addedOn, sellingPrice, supplier, available, available_on, restock_on, labelSource, ownerSource`. `available_on` needs `available` and a recorded `store.selection_checked_on`. `hold` is forbidden outside held. The three additional public keys are allowed but not required on held; their normal value checks are skipped there (`content_model.py:33–46,259–346`). |
| `products.json` `/products/170/hold`, `/products/171/hold` | 2; U = I: `reason, source, evidence, record` | `reason, source` | `evidence, record` (`content_model.py:46,321–329`). Optional `labelSource` and `ownerSource` objects occur zero times; each, if present, requires exactly `source, photo, text` (`content_model.py:288–295`; `hass/product_claims.py:96–100`). |
| `makers.json` root | 1; U = I: `schemaVersion, makers` | Both; `makers` is a nonempty object keyed by maker identifier | None (`content_model.py:154–176,349–352`). |
| `makers.json` `/makers/*` | 26; U = I: `name, place, story, url` | `name, place` | `story, url, hidden`; present `hidden` must be `true` (`content_model.py:48,349–365`). The migration checker separately requires a URL on every pinned maker (`migration_check.py:165–172`). |
| `community.json` root | 1; U = I: `schemaVersion, club, events, routeIdeas` | All four; `club` is an object and `events` and `routeIdeas` are arrays | None (`content_model.py:154–179,382–387,398–402,423–426`). |
| `community.json` `/club` | 1; U = I: `clubName, organizer, intendedSender, emailConnected` | All four; `emailConnected` must be `false` | `showSamples, intro` (`content_model.py:49–51,386–397`). |
| `community.json` `/routeIdeas/0`–`/routeIdeas/2` | 3; U = I: `id, title, place, character, distance, difficulty, elevation, elevationLabel, duration, routeType, terrain, description, sourceUrl, sourceName, status, rsvpEnabled` | All 16; `rsvpEnabled` must be `false` | None (`content_model.py:53–56,398–422`). |
| `community.json` `/events` | 0; U: empty; I: not applicable | For any event: `id, title, startsAt, timezone, status` | `meetingPoint, meetingAddress, distance, difficulty, duration, description, recap, meetTime, walkTime, returnTime, invitation, bring, accessNote, rsvpEnabled, capacity, trailId, cancelNote`; `meetingPoint` is required when `rsvpEnabled` is `true` (`content_model.py:59–68,423–472`). |
| `store.json` root | 1; U = I: `schemaVersion, name, streetAddress, town, hours`. `/hours/0` and `/hours/1` are strings, not object records. | All five | `selection_checked_on, intro, headline, story, homeImage, notice, phone, specials, homeSections, banner, pageAbout, pageGettingHere, pagePolicies, pageFaq` (`content_model.py:71–76,712–788`; `hass/content/store.json:1–10`). |

No optional store subobjects are present. For completeness, these are their rules if added (`hass/content_model.py`):

| Optional location in `store.json` | Required keys when present | Optional keys |
| --- | --- | --- |
| `/homeImage` (739–746) | `image, imageAlt` | None |
| `/notice` (749–762) | `text, until` | `from` |
| `/specials/*` (553–608) | `id, title, deal, start, end, order` | `product, picture`; `picture` must be `true` and needs `product` |
| `/homeSections/*` (622–630) | `id, shown` (exactly four rows) | None |
| `/banner` (633–653) | `text, start, end` | `link` |
| `/pageAbout`, `/pageGettingHere`, `/pagePolicies` (656–658,674–709) | `shown, title, intro, paragraphs` | None |
| `/pageFaq`, `/pageFaq/entries/*` (674–702) | Page: `shown, title, entries`; entry: `q, a` | Page: `intro`; entry: none |

The baseline is not a fifth `Content` payload (`hass/content_model.py:154–179`). For the baseline rows below, `U = I` at each singleton; the maps have dynamic keys, not fixed record fields. Required means checked by `_baseline_problem`, not inferred from the example (`hass/migration_check.py:43–72,128–136`).

| `migration-baseline.json` pointers | Count and observed keys | Required by checker; other fields |
| --- | --- | --- |
| Root | 1; `schemaVersion, purpose, baseCommit, listings, makers, sources, held, siteFileSha256` | `baseCommit` text, five objects (`listings, makers, sources, held, siteFileSha256`); `schemaVersion` and `purpose` are present but not checked. |
| `/listings` | 1; `count, ids`; 170 string IDs | `count` integer, `ids` array of nonempty strings; count and unique IDs checked at `migration_check.py:146–149`. |
| `/makers` | 1; `count, keys`; 26 string keys | `keys` array of strings; `count` present but not checked by the migration checker. |
| `/sources` | 1; `makerUrls, routeIdeaSources, heldSource` | Both maps and `heldSource` text. |
| `/held` | 1; `ids, reason, source`; 2 string IDs | `ids` array of strings, `reason` and `source` text. |
| `/sources/makerUrls`, `/sources/routeIdeaSources`, `/siteFileSha256` | 1 map each: 26, 3, 6 entries respectively, all string values | String values; keysets are not closed and hash format is not separately validated. The shape checker does not reject extra keys at any level. |

## R2. Missing fields, unknown fields and wrong types

**No exceptions to list or quote** for the checked-in records. The model reported zero missing required, unknown or wrong-type fields; the baseline also passed its separate reader and shape checks. The quoted read-only result on 2026-11-21 was `content validate: PASS; baseline shape: None`. Both JSON readers reject duplicate object keys (`hass/content_model.py:131–151`; `hass/migration_check.py:109–125`). The main loader plus validator checks the root envelopes and present records (`hass/content_model.py:154–179,237–247,791–806`); the baseline shape checker is narrower as shown above.

Two differences in field presence are valid: the two held products omit `description`, `displayBrand` and `producerKey` (`products.json#/products/170` and `#/products/171`; `hass/content_model.py:321–340`), and 65 of 170 active records have `"producerKey": null` (105 are strings; dated inventory result, `hass/content_model.py:338–343`). `null` is not a missing field or a wrong type there. Neither the absence of optional store fields nor the empty `community.json#/events` array is an error.

## R3. What the migration snapshot pins and what differs

`migration-baseline.json#/baseCommit` names `59d1880f6c870e7827d8c827f6f7561c569fc3b0`. The snapshot is a preservation check, not a requirement to keep every value, listing order or output byte frozen (`hass/migration_check.py:1–23,146–244`). Counts below are the dated replay results, not live catalog or inventory counts.

| Baseline pointers | Current comparison | Match? |
| --- | --- | --- |
| `/listings/count`, `/listings/ids` | 170/170 IDs preserved, all active, none hidden, no additional active/hidden IDs; 170/170 current images are regular files, not symlinks. The check does not pin the image names or bytes (`migration_check.py:99–106,146–162`). | Yes; no differing listing IDs. |
| `/makers/count`, `/makers/keys`, `/sources/makerUrls` | 26/26 maker keys, no additions, and 26/26 URLs match their original maker keys in a separate keyed comparison. The checker itself requires source URLs in aggregate plus a URL on each pinned maker (`migration_check.py:164–181`). | Yes; no differing maker keys or URLs. |
| `/sources/routeIdeaSources` | 3/3 route IDs and URLs match by ID, no additional ideas; 0 real events and no sample promoted. The checker tests route IDs and pooled source membership separately (`migration_check.py:173–185,208–217`); the content model keeps ideas undated with RSVP disabled (`content_model.py:398–438`). | Yes; no differing route IDs or URLs. |
| `/held/ids`, `/held/reason`, `/held/source`, `/sources/heldSource` | Both held products (`products.json#/products/170` and `#/products/171`) still held, both excluded from generated catalog, no additional holds; both reason/source pairs and the committed held-file IDs/reason/source pass, and the two baseline source fields agree. Together with 26 maker and 3 route entries, all 30 pinned source entries are preserved (`migration_check.py:173–206`). | Yes; no differing hold IDs, reasons or sources. |
| `/siteFileSha256` | 6 pins, all still generated. 2 identical, 4 changed; 4 additional outputs have no old hash. The fresh in-memory render matches all 10 committed outputs, independent of the checker's historical notice/special/banner allowances (`migration_check.py:219–244`; `hass/notice.py:68–111`; `hass/sitegen.py:357–408`). | Preservation passes; historical byte equality does not. |

Exact JSON pointers into `migration-baseline.json` for the two matching digests: `/siteFileSha256/storefront-mockup~1producers.js`, `/siteFileSha256/storefront-mockup~1producers.json`. Four differing pointers:

- `/siteFileSha256/storefront-mockup~1catalog-products.js`
- `/siteFileSha256/storefront-mockup~1community.json`
- `/siteFileSha256/storefront-mockup~1index.html`
- `/siteFileSha256/storefront-mockup~1hike~1index.html`

The unpinned output paths are `storefront-mockup/about/index.html`, `storefront-mockup/faq/index.html`, `storefront-mockup/getting-here/index.html`, `storefront-mockup/policies/index.html`; these are not missing pins from the frozen snapshot (`hass/sitegen.py:377–384`; `hass/content_model.py:656–658`).

**Replay.** From the repository root, `python3 -B hass/migration_check.py` exited 0, ending in `migration check passed`, with `baselineListingsPreserved: 170`, `baselineImagesPresent: 170/170`, `sourceLinksPreserved: 30`, `generatedFiles: 10` and `identicalToPreMigration: 2/6`. It reads local files and renders into memory (`hass/migration_check.py:128–139,219–225,248–265`). The separate workspace-only `audit_content.py` (replay attachment; run `python3 -B audit_content.py avocado-shack` from the clone's parent) enumerated every object key set, ran the real model and migration validators, compared source URLs by record key, and classified each baseline hash against the in-memory render. The dated quoted outputs include `maker source by key differences []`, `route source by id differences []`, `held source equality True True`, `hash not generated []` and `strict current render diff []`. No network requests to source URLs, generation writes, runtime checks or changes were made during the audit.

## R4. Ranked gaps and follow-up

1. **Current-record schema or migration preservation gaps: none.** No row needs a field or type fix, and nothing required by the migration preservation check is missing (R2 and R3).
2. **Checker coverage limits, not current mismatches.** Source membership is pooled rather than bound to the original maker or route key, and the baseline envelope does not enforce `schemaVersion`, `purpose` or `/makers/count`. The audit's keyed comparisons found no source mismatch, and the recorded maker count is 26, matching `/makers/keys` and the current maker map (`hass/migration_check.py:43–72,164–185`; R1 and R3).
3. **Historical byte differences, not stale generated files.** The four differing hashes and four unpinned pages are listed above; no current generated file differs from its committed counterpart. The checker reports the historical hash comparison without making it a failure (`hass/migration_check.py:219–245`; R3).

**No build unit needed to reconcile these files.** This report does not propose tightening the baseline contract, updating its pins, changing content or making any decision about holds or claims (R2 and R3).
