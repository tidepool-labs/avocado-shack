# Storefront JSON readers

| Input | Browser reader at the audited main | Result |
| --- | --- | --- |
| `community.json` | `community.js:152–155`, static fallback | Reads events and route ideas; the checked-in event array is empty. `showSamples` is an optional switch. |
| `hiking-preview.json` | `community.js:157–160`, hike page | Reads sample invitation and history; the shared invitation helper also probes an absent `upcoming.status`. |
| `assets/trails/point-buchon.json` | `trail-explorer.js:20`, when the map mounts | Reads geometry, elevation and profile points. No missing field in those reads. |
| `shop-data.json`, `catalog.json`, `held-products.json`, `producers.json` | None; see R1 and `storefront-mockup/README.md:10–16`, `hass/sitegen.py:469–483,502–524` | The active shop uses JavaScript globals, not these files. An unread file is not necessarily disposable. |

**Basis:** `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, checked offline after cloning on 2026-11-21. Paths in the tables are relative to `storefront-mockup/` unless prefixed otherwise. Scope is the ten page scripts and their current page wiring, not archive pages, generators, QA consumers or deployed behavior. `[]` is an array item; `[*]` is an entry addressed by a dynamic key. Counts are key presence, including nulls, not counts of non-empty values. No community record values were printed for the census.

## R1. What each script loads and reads

| Script | File fetch, or other input | Properties read (dotted paths and source anchors) |
| --- | --- | --- |
| `shop.js` | No file fetch. Home loads `catalog-products.js` and `producers.js` before it (`index.html:32`; `hass/templates/index.html:20`). | `catalog[].producerKey`, `.name`, `.image`, `.imageAlt`, `.supplier`, `.availability`, `.displayBrand`, `.brand`, `.sellingPrice`, `.id`, `.category`, `.description` (`shop.js:2–24`; same `catalog[]` prefix throughout). Also `catalog[].availabilityState`, `.availabilityCheckedOn`, `catalogFreshness.selectionCheckedOn` (`:44–46`), `catalog[].addedOn` (`:52,76–77`). `producers[*]` membership/lookup and `.name`, `.place`, `.story`, `.url` (`:2–17,91,98`). `catalog[].availability` is recomputed in the browser (`:44–45`). The selection line takes `dataset.checkedOn` and `dataset.phone` from the DOM (`:46`), not JSON. |
| `specials.js` | No JSON fetch or parse (`specials.js:1`; generated inclusion at `hass/specials.py:24`). | None from JSON. Reads DOM `dataset.start` and `.end`. |
| `producers.js` | No fetch; declares `producers` at `producers.js:1`. | None; provides maker entries to `shop.js`. The `.js` and `.json` forms come from the same generator projection (`hass/sitegen.py:212–221`). |
| `catalog.js` | No fetch; declares `catalog`, `merch`, `boxes` at `catalog.js:1–3`. Not included by the active pages or static publish list (`index.html:32`, `hike/index.html:29`, `hass/sitegen.py:469–476`). | None; stores literals, not a reader. Do not confuse it with `catalog-products.js`. |
| `catalog-products.js` | No fetch; declares `catalog`, `catalogFreshness` at `catalog-products.js:1–2`. | None; provides the arrays/objects read by `shop.js` (generator: `hass/sitegen.py:197–209`). |
| `community.js` | `/community.json` (`community.js:152–155`) if the API does not yield data; on published pages the service marker skips the API (`:143–149`; `hass/sitegen.py:487–499,513–515`). Both home and hike can take this path (`community.js:181–187`). | `events`, `showSamples`, `routeIdeas` (`:9,122–132,155,183`). `events[].id`, `.title`, `.status`, `.startsAt`, `.timezone`, `.trailId`, `.description`, `.recap`, `.cancelNote`, `.capacity`, `.rsvpEnabled`, `.accessNote`, `.bring`, `.difficulty`, `.distance`, `.duration`, `.meetTime`, `.meetingAddress`, `.meetingPoint`, `.returnTime`, `.walkTime` (`:3–29,34–55,79–88,98–110,114,122–129,178–186`; `own('meetingPoint')` is an indirect read at `:80–83`). Also reads normalized `events[].confirmedGuests`, `.remaining`, `.rsvpOpen`, `.staticSite`, **not** those fields from disk: `:155` overwrites or adds them before rendering (`:17,51,101,110,178`). `routeIdeas[].id`, `.sourceUrl`, `.sourceName`, `.title`, `.distance`, `.difficulty`, `.elevation`, `.elevationLabel`, `.duration`, `.place`, `.description`, `.routeType`, `.terrain` (`:9,19,33–55,75–88`). |
| `community.js` | `/hiking-preview.json` (`community.js:159–160`; hike page branch at `:187`). | `enabled`, `upcoming`, `past` (`:123,127,129–132`); `upcoming.trailId`, `.status`, `.startsAt`, `.walkTime`, `.invitation`, `.meetTime`, `.meetingPoint`, `.meetingAddress`, `.returnTime`, `.bring`, `.accessNote` (`:34–51,73,123`). `past[].trailId`, `.dateLabel` (`:74–76,129`). The sample looks up its route in the club response; it does not read those route properties from the preview file. |
| `community.js` | JSON HTTP responses, not files: GET `/api/community` (`community.js:145–153`); optional POSTs to the subscription/RSVP endpoints (`:165–174,178`). | GET: same club/event/route paths above, plus `acceptsSubmissions` (`:151`); the server computes event `.confirmedGuests`, `.remaining`, `.rsvpOpen` (`community-server.py:67–79`). The browser probes `.staticSite` on the shared event shape; only the file adapter adds it. POST responses: `message`, `error` (`community.js:169–171`); form payloads are not file reads. |
| `trail-explorer.js` | `/assets/trails/point-buchon.json` (`trail-explorer.js:20`); `community.js:91–95,133` mounts the map near view. | `distanceMeters`, `gainMeters`, `lossMeters` (`trail-explorer.js:27`); `bounds3857` (four positional entries, `:51–52`), `coordinates` (positional lon/lat pairs, `:52–54`), `profile` (`:37,50`), `maxElevationMeters` (`:93`), `oneWayMeters` (`:107`), `profile[].distanceMeters`, `.elevationMeters`, `.lon`, `.lat` (`:95,105–113`). |
| `banner.js` | No JSON fetch or parse (`banner.js:1`; generated inclusion at `hass/notice.py:13`). | None from JSON. Reads DOM `dataset.start` and `.end`. |
| `notice.js` | No JSON fetch or parse (`notice.js:1`; generated inclusion at `hass/notice.py:30`). | None from JSON. Reads DOM `dataset.from` and `.until`. |
| `script.js` | No JSON file fetch. Parses JSON in the inline HTML `data-weekly-hours` attribute (`index.html:27`; `hass/sitegen.py:141`; `script.js:28–34`). | Inline array record keys `weeklyHours[].closed`, `.opens`, `.closes` (`script.js:32,44–46`). Also reads notice DOM `dataset.from` and `.until` (`:40`). |

## R2. Read keys absent from every checked-in record

| JSON file and record set | Absent path | Missing / total | Read line (relevant expression) and effect |
| --- | --- | ---: | --- |
| `community.json`, root | `showSamples` | 1/1 | `community.js:123`: `const samplesOn=club.showSamples!==false,demo=samplesOn&&preview?.enabled&&preview.upcoming&&trailById(preview.upcoming.trailId);` Missing intentionally leaves the sample switch on. `hass/sitegen.py:478–483` permits the key in the static projection. |
| `hiking-preview.json`, `/upcoming` | `upcoming.status` | 1/1 | `community.js:35`: `const x=e.status==='cancelled',started=label==='TODAY';` The shared helper reads the key, but this comparison is false for the sample. The sample takes its own display branches (`:34–51,59,73`); this is not a failing required read. |

No other absent read in a non-empty **fetched file** record set: `community.json#/routeIdeas` (3 records); `hiking-preview.json#/past` (2); `assets/trails/point-buchon.json` root (1) and `#/profile` (217). There are **0** records in `community.json#/events`, so no event field is classified as missing. That also means this snapshot does not prove the event schema is exercised. `acceptsSubmissions` is API-only (`community.js:151`); the four static adapter fields are created before use (`:155`), not missing disk reads. The four unfetched files have no script reads to test for absence.

For comparison, the active JS literal `catalog-products.js:1` has 170 products. The following are absent from all 170; this is not a JSON file mismatch. The generator includes optional fields only when supplied (`hass/content_model.py:36–37`; `hass/sitegen.py:197–209`).

| JS property | Missing / total | Read line (relevant expression) |
| --- | ---: | --- |
| `catalog[].imageAlt` | 170/170 | `shop.js:11`, `p.imageAlt\|\|p.name` (falls back to name). |
| `catalog[].supplier` | 170/170 | `shop.js:12`, `return p.supplier?` (falls back to maker or general source text). |
| `catalog[].sellingPrice` | 170/170 | `shop.js:21`, `const amount=p.sellingPrice?` (omits the price display). |
| `catalog[].availabilityState`, `catalog[].availabilityCheckedOn` | 170/170 each | `shop.js:45`, `availabilityWord(p.availabilityState,p.availabilityCheckedOn,checked,today)` (no word without valid inputs). |
| `catalog[].addedOn` | 170/170 | `shop.js:52`, `dayNumber(p.addedOn)` (no New badge); also `:77` for sorting. |
| `catalog[].availability` | 170/170 | `shop.js:13`, `p.availability?`; this property is derived/cleared in `:45`, not expected from disk. |

`catalogFreshness.selectionCheckedOn` is present in the one object (`catalog-products.js:2`); null is not a missing key. No missing maker keys in `producers.js:1` among the 26 entries (R1 reads four keys per entry). The inline weekly-hours shape is intentionally either `closed` or `opens`/`closes`, as checked at `script.js:32`; it is not a file read.

## R3. Keys present in more than 90% of records and never read

Each row uses the stated JSON pointer as the record set. The empty pointer (`root`) denotes the top-level object or, for `catalog.json`, the top-level array's items. Each listed key has the indicated coverage; none met the threshold at less than full coverage. Classifications use R1, not a grep for the same spelling in unrelated data. For unfetched files all qualifying keys are unread **from those files**. In particular, the producer keys below are all read from the parallel `producers.js` representation. The maker names used as map indexes are not record fields.

| File and record set | Present / total per key | Keys only |
| --- | ---: | --- |
| `community.json` root | 1/1 | `clubName`, `emailConnected`, `intendedSender`, `organizer` |
| `community.json#/routeIdeas` | 3/3 | `character`, `rsvpEnabled`, `status` |
| `hiking-preview.json` root | 1/1 | `purpose` |
| `hiking-preview.json#/upcoming` | 1/1 | `id` |
| `assets/trails/point-buchon.json` root | 1/1 | `endLabel`, `id`, `imagery`, `method`, `minElevationMeters`, `name`, `routeCredit`, `routeLicense`, `sources`, `startLabel` |
| `shop-data.json` root | 1/1 | `boxes`, `merch`, `photoReviewNotes`, `products` |
| `shop-data.json#/products` | 170/170 | `brand`, `category`, `description`, `displayBrand`, `evidence`, `id`, `image`, `imageKind`, `name`, `notes`, `photo`, `photos`, `price`, `producerKey`, `samplePrice`, `sampleUnit`, `section`, `status` |
| `shop-data.json#/merch` | 8/8 | `brand`, `category`, `description`, `id`, `image`, `imageKind`, `name`, `samplePrice`, `sampleUnit`, `section`, `sizes` |
| `shop-data.json#/boxes` | 3/3 | `brand`, `category`, `components`, `contents`, `description`, `id`, `image`, `imageKind`, `name`, `samplePrice`, `sampleUnit`, `section` |
| `shop-data.json#/boxes` → each box's `/components` items | 23/23 | `productId`, `quantity` |
| `shop-data.json#/photoReviewNotes` | 1/1 | `limits`, `unassignedCartons` |
| `catalog.json` root array | 95/95 | `brand`, `category`, `evidence`, `id`, `image`, `name`, `notes`, `onlineQuantity`, `photo`, `photos`, `price`, `sellable`, `status`, `unit` |
| `producers.json` map values | 26/26 | `name`, `place`, `story`, `url` |
| `held-products.json` root | 1/1 | `products`, `reason`, `source` |
| `held-products.json#/products` | 2/2 | `brand`, `category`, `evidence`, `id`, `image`, `imageKind`, `name`, `notes`, `photo`, `photos`, `price`, `samplePrice`, `sampleUnit`, `section`, `status` |

No qualifying key in `hiking-preview.json#/past` or `assets/trails/point-buchon.json#/profile`: all keys there are read. Empty event arrays and arrays of primitives/tuples contribute no record keys. The static publish projection keeps `clubName` but excludes the other three unread root keys above (`hass/sitegen.py:478–484`). `routeIdeas[].status` is used upstream to select published route ideas (`hass/sitegen.py:224–228`) even though the browser doesn't read it. The active product and producer JS literals have no record keys above the threshold that `shop.js` does not read (R1; `catalog-products.js:1–2`, `producers.js:1`).

## R4. Ranked gaps and next step

1. **Event coverage, not a missing-field bug.** With an empty event array, this audit cannot establish that the static event renderer and the API agree for real events. Keep the file adapter and API fields distinct (`community.json#/events`; `community.js:98–110,145–155`; `community-server.py:67–79`).
2. **Optional sample reads.** The two absent file keys in R2 do not block rendering; one is opt-out and the other is a shared status check on a sample (`community.js:35,59,73,123`).
3. **Unused browser data.** R3 separates genuinely unread delivered keys from a parallel maker representation and retained extraction/hold records. Browser non-use is not evidence those records or attribution fields can be removed (`storefront-mockup/README.md:15–16,28`; `hass/sitegen.py:21–22,224–228,469–484`).

**No build unit needed on this evidence.** No required field was found missing in a non-empty fetched record set. No code, data, publication, hold, or policy change is proposed.

### Reproduce offline

From a clean checkout at the pinned main, the following locate the fetches, page wiring, data declarations and quoted expressions without running the site:

```sh
git rev-parse origin/main
git grep -nE 'fetch\(|JSON\.parse\(|\.json\(' origin/main -- 'storefront-mockup/*.js' ':!storefront-mockup/archive/**'
git grep -nE '<script[^>]*src=' origin/main -- 'storefront-mockup/*.html' 'hass/templates/*.html' ':!storefront-mockup/archive/**'
git grep -nE 'PUBLISH_(GENERATED|STATIC|ASSETS)|PUBLIC_COMMUNITY_KEYS' origin/main -- hass/sitegen.py
git grep -nE 'x=e\.status|samplesOn=club\.showSamples' origin/main -- storefront-mockup/community.js
```

For the counts, save this read-only `jq` filter as `key-counts.jq` in scratch outside the clone. It emits only names and presence counts, never data values. Use `root` for a root object, `array` for root-array items, `map` for maker entries, `boxChildren` for box components, or the collection key for a named object or array. Subtract the key's `present` count (zero if unlisted) from `records` for R2; for R3 compare qualifying keys (`present` greater than `0.9 * records`) to R1 at the same path.

```jq
def tally:
  {records: length, present: (reduce (.[] | keys_unsorted[]) as $k
    ({}; .[$k] += 1))};
if $set == "map" then [.[]]
elif $set == "root" then [.]
elif $set == "array" then .
elif $set == "boxChildren" then [.boxes[].components[]]
elif (.[$set] | type) == "object" then [.[$set]]
else .[$set] end | tally
```

For example, from the clone with the filter in the parent scratch directory:

```sh
jq -c --arg set events -f ../key-counts.jq storefront-mockup/community.json
jq -c --arg set routeIdeas -f ../key-counts.jq storefront-mockup/community.json
jq -c --arg set upcoming -f ../key-counts.jq storefront-mockup/hiking-preview.json
jq -c --arg set profile -f ../key-counts.jq storefront-mockup/assets/trails/point-buchon.json
jq -c --arg set products -f ../key-counts.jq storefront-mockup/shop-data.json
```

For the JS literal comparison, strip the `const <name>=` prefix and final semicolon on the cited declaration line, then apply the same filter with `array` (`catalog`), `root` (`catalogFreshness`) or `map` (`producers`). The 2026-11-21 check parsed those declarations as data without executing JavaScript, counted the seven JSON files, and traced named and indirect property reads in the pinned sources. It did not run a browser, server, publishing step or live API.
