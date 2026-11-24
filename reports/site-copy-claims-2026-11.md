# Site copy claims audit, November 2026 (AV0007-08)

**Audit only; no copy or decision changed.** This file is evidence for Michael Wolfe (owner) and G. It proposes no replacement words. Any rewrite needs their decision.

| | |
| --- | --- |
| Audited commit | `77ed368d15c62d8cb53000b56b44aff3eaebc20e` (avocado-shack `main`, after AV2152-09 and AV1422-02 merged) |
| Date | 2026-11-15 |
| Surfaces | Home page `/` ([template](../hass/templates/index.html) plus the four home parts under [hass/templates/home/](../hass/templates/home/)), `/hike` ([template](../hass/templates/hike/index.html)), the publish-only 404 ([template](../hass/templates/404.html)) and the shared privacy dialog ([script.js:14](../storefront-mockup/script.js#L14)) |
| Method | Read the templates and scripts at the audited commit; compared each factual clause with the repository content records and documents. Content counts below were computed by reading the content JSON files with a throwaway script; the script is not part of this change. |
| Not done | No network requests. Stored source URLs are repository-recorded sources, not freshly checked external evidence. No file other than this report changed. |

## 1. How to read this report

**Fixed copy** is wording that sits in a template, in sitegen code or in `script.js` and that Hass cannot change through a typed edit. **Editable slots** (words Hass can change) are excluded and listed in section 9.

Statuses (exactly these four):

- `supported by repository record`: a content record, source file or code path at the audited commit states or implements the claim.
- `partially supported`: part of the claim has a record, or the record covers only some items or some deployment modes. The limitation column says which part.
- `no record`: nothing in the repository states it. This is not a finding that the claim is false.
- `aspirational/non-factual`: slogans, invitations, opinions and labels. Listed so the inventory is complete.

Rules applied from the repository's own guidance ([HERMES_HANDOFF.txt:43-44](../HERMES_HANDOFF.txt#L43-L44), [AGENTS.md:11](../AGENTS.md#L11)): a maker's base is not proof of where an ingredient was grown, a brand name or photograph is not proof of origin, organic status needs a documented claim, a route idea or sample invitation is not a real outing, and unknown origins stay unknown.

Row columns: id, element, verbatim quote, source (path:line of the quote), status, evidence (path:line), limitation. Repeated shared copy has one canonical row in section 2 (ids `SH-`); every surface and line it appears on is listed there. Row ids: `SH-` shared, `HM-` home, `HK-` /hike, `NF-` 404, `PV-` privacy dialog, `AJ-` script-written text on /hike.

## 2. Shared copy (home, /hike and 404 unless noted)

| ID | Element | Quote | Source | Status | Evidence | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| SH-01 | Brand line under the logo | `THE NEIGHBORHOOD MARKET` | [hass/templates/index.html:14](../hass/templates/index.html#L14); [hass/templates/hike/index.html:15](../hass/templates/hike/index.html#L15); [hass/templates/404.html:12](../hass/templates/404.html#L12) | partially supported | [reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt:3](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L3) | The owner brief calls it "a produce and specialty food market in Morro Bay"; no record defines "neighborhood". |
| SH-02 | Top line, first phrase | `Local food.` | [hass/templates/index.html:13](../hass/templates/index.html#L13); [hass/templates/hike/index.html:14](../hass/templates/hike/index.html#L14) (not on the 404) | partially supported | Maker bases in section 6; [HERMES_HANDOFF.txt:41](../HERMES_HANDOFF.txt#L41) | Brand intent ("local growers") is recorded; "local" is not defined anywhere. See finding L-1. |
| SH-03 | Top line, second phrase | `Familiar faces.` | [hass/templates/index.html:13](../hass/templates/index.html#L13); [hass/templates/hike/index.html:14](../hass/templates/hike/index.html#L14) | aspirational/non-factual | none | A hope, not a checkable statement. |
| SH-04 | Top strip (default banner line) | `GOOD FOOD. CLOSE TO HOME.` | [hass/templates/home/strip.html:1](../hass/templates/home/strip.html#L1) (home and /hike); [hass/templates/404.html:11](../hass/templates/404.html#L11) (hard-coded copy) | aspirational/non-factual | none | Slogan. |
| SH-05 | Top strip link | `Come visit the Shack` | [hass/templates/home/strip.html:1](../hass/templates/home/strip.html#L1); [hass/templates/404.html:11](../hass/templates/404.html#L11) | aspirational/non-factual | none | Invitation. |
| SH-06 | Footer name and slogan | `Good food, close to home.` | [hass/templates/index.html:18](../hass/templates/index.html#L18); [hass/templates/hike/index.html:27](../hass/templates/hike/index.html#L27); [hass/templates/404.html:21](../hass/templates/404.html#L21) | aspirational/non-factual | none | Slogan. Also the home page title (HM-01). |
| SH-07 | Footer link label | `Michael’s newsletter` | [hass/templates/home/footer.html:1](../hass/templates/home/footer.html#L1) (home); [hass/templates/home/hike-footer.html:1](../hass/templates/home/hike-footer.html#L1) (/hike); [hass/templates/404.html:21](../hass/templates/404.html#L21) | partially supported | [reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt:5-6](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L5-L6); [hass/content/community.json:7](../hass/content/community.json#L7) | The owner brief says Michael writes newsletters. Email delivery is not connected (`emailConnected` false). See finding C-4. |

Navigation and button labels shared by all surfaces (The food, Hiking club, Newsletter, Visit us, Hours &amp; location, Privacy, Skip links, Close details) carry no factual claim and are in the coverage register (section 9).

## 3. Home page `/`

### 3.1 Head and hero ([index.html](../hass/templates/index.html))

| ID | Element | Quote | Source | Status | Evidence | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| HM-01 | Page title | `Good food, close to home.` | [hass/templates/index.html:5](../hass/templates/index.html#L5) | aspirational/non-factual | none | Same slogan as SH-06. |
| HM-02 | Meta description, place | `Explore the food and people behind Avocado Shack in Morro Bay.` | [hass/templates/index.html:6](../hass/templates/index.html#L6) | partially supported | [hass/content/store.json:4-5](../hass/content/store.json#L4-L5); [reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt:3](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L3) | Shop address and town are recorded. "people behind" holds for the 105 active records that name a maker; 65 active records have no maker (finding P-3). |
| HM-03 | Meta description, produce | `Seasonal produce` | [hass/templates/index.html:6](../hass/templates/index.html#L6) | partially supported | [reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt:4](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L4); section 8 and the counts in findings P-3 and O-1 | Brand intent names seasonal produce. 66 active fruit, vegetable and flower records exist; none has a season or harvest field. Catalog is "not live stock" ([HERMES_HANDOFF.txt:44](../HERMES_HANDOFF.txt#L44)). |
| HM-04 | Meta description, growers | `local growers` | [hass/templates/index.html:6](../hass/templates/index.html#L6) | partially supported | [HERMES_HANDOFF.txt:41](../HERMES_HANDOFF.txt#L41); section 8 | Named growers with recorded bases exist (for example [hass/content/makers.json:89-92](../hass/content/makers.json#L89-L92), [hass/content/makers.json:95-98](../hass/content/makers.json#L95-L98)). "Local" is undefined (L-1). |
| HM-05 | Meta description, producers | `small producers` | [hass/templates/index.html:6](../hass/templates/index.html#L6) | partially supported | [hass/content/makers.json:23-26](../hass/content/makers.json#L23-L26) | Some stories say "small batches"; others (Straus, Sierra Nevada, Maple Valley, Love Beets) carry no size statement. |
| HM-06 | Meta description, closing | `good things for your table` | [hass/templates/index.html:6](../hass/templates/index.html#L6) | aspirational/non-factual | none | Invitation. |
| HM-07 | Structured data (head, not visible text) | `GroceryStore` | [hass/sitegen.py:223](../hass/sitegen.py#L223) | partially supported | [hass/content/store.json:3-5](../hass/content/store.json#L3-L5); [reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt:3](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L3) | Name, street and town come from the store record. The business type and the fixed `addressRegion` "CA" and `addressCountry` "US" ([sitegen.py:225](../hass/sitegen.py#L225)) are set in code, not in the record. |
| HM-08 | Hero label | `GOOD PEOPLE. GOOD FOOD.` | [hass/templates/index.html:16](../hass/templates/index.html#L16) | aspirational/non-factual | none | Slogan. |
| HM-09 | Hero text, produce | `Fresh fruit, vegetables with the season still in them` | [hass/templates/index.html:16](../hass/templates/index.html#L16) | partially supported | [hass/content/products.json:16](../hass/content/products.json#L16) (Oranges, "Producer not identified"); [hass/content/products.json:38](../hass/content/products.json#L38) | 13 fruit and 52 vegetable records are listed. "Fresh" and "the season still in them" have no record; listings come from photographs and are not stock ([README.md:22](../storefront-mockup/README.md#L22)). |
| HM-10 | Hero text, makers | `good things made by people who care` | [hass/templates/index.html:16](../hass/templates/index.html#L16) | aspirational/non-factual | none | Opinion. |
| HM-11 | Hero text, organic | `we seek out organic produce` | [hass/templates/index.html:16](../hass/templates/index.html#L16) | partially supported | [hass/content/makers.json:97](../hass/content/makers.json#L97); [storefront-mockup/shop.js:8](../storefront-mockup/shop.js#L8) | Only 5 of 66 active fruit/vegetable/flower records (the Green Gold microgreens, for example [hass/content/products.json:291](../hass/content/products.json#L291)) carry an organic label, resting on a stored "certified organic by CCOF" sentence. No other fresh-produce record makes an organic claim. See finding O-1. |
| HM-12 | Hero text, relationships | `build relationships with local growers` | [hass/templates/index.html:16](../hass/templates/index.html#L16) | no record | none | No record of any grower relationship (agreement, visit, purchase history). Named growers exist; the relationship is not recorded. |
| HM-13 | Hero text, small producers | `make room for small producers with something delicious to share` | [hass/templates/index.html:16](../hass/templates/index.html#L16) | partially supported | [hass/content/makers.json:3](../hass/content/makers.json#L3) (26 makers, section 8) | 26 makers are listed; size per HM-05. "Something delicious" is opinion. |
| HM-14 | Hero text, shelves | `Get to know what’s on our shelves and the people behind it.` | [hass/templates/index.html:16](../hass/templates/index.html#L16) | partially supported | [HERMES_HANDOFF.txt:44](../HERMES_HANDOFF.txt#L44); [storefront-mockup/shop.js:12](../storefront-mockup/shop.js#L12) | Listings are not live stock. 105 of 170 active records show a maker's base; the other 65 show "Ask us about the source in store." |
| HM-15 | Hero text, invitation | `Then come say hello. There’s always something worth talking about around good food.` | [hass/templates/index.html:16](../hass/templates/index.html#L16) | aspirational/non-factual | none | Invitation. |
| HM-16 | Value chip | `Seasonal food` | [hass/templates/index.html:16](../hass/templates/index.html#L16) | partially supported | as HM-03 | Brand intent only. |
| HM-17 | Value chip | `Small producers` | [hass/templates/index.html:16](../hass/templates/index.html#L16) | partially supported | as HM-05 | As HM-05. |
| HM-18 | Value chip | `Community at the table` | [hass/templates/index.html:16](../hass/templates/index.html#L16) | aspirational/non-factual | none | Slogan. |
| HM-19 | Hero link | `Good company, beyond the Shack` | [hass/templates/index.html:16](../hass/templates/index.html#L16) | aspirational/non-factual | none | Points to /hike; see HK rows for the club claims. |
| HM-20 | Hero caption | `A little of the Central Coast, all in one place.` | [hass/templates/index.html:16](../hass/templates/index.html#L16) | partially supported | section 8 (maker bases) | 4 active records name "California’s Central Coast" as the base; most other bases are named towns, and a few are far away (Wisconsin, New York). No record defines "Central Coast". |
| HM-21 | Hero image alt (default photo only; replaced when an owner photo is set) | `Produce and pantry shelves inside Avocado Shack in Morro Bay` | [hass/sitegen.py:255](../hass/sitegen.py#L255) | partially supported | [hass/tests/test_image_dimensions.py:77](../hass/tests/test_image_dimensions.py#L77) (file size only) | The file `assets/store.jpg` exists. No record states where or when it was taken. Reader's observation, not a record: it shows a rustic produce shop interior with a "HENRY RANCH WHOLESALE" sign visible. |

### 3.2 The food section ([market.html](../hass/templates/home/market.html))

| ID | Element | Quote | Source | Status | Evidence | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| HM-30 | Section label and heading | `GET TO KNOW YOUR FOOD` / `Good things on our shelves.` | [hass/templates/home/market.html:2](../hass/templates/home/market.html#L2) | partially supported | as HM-14 | "On our shelves" is a catalog of photographed products, not stock. |
| HM-31 | Side text | `Discover the food.` / `Meet the people behind it.` | [hass/templates/home/market.html:2](../hass/templates/home/market.html#L2) | partially supported | as HM-14 | Invitation; "people behind it" per HM-14. |
| HM-32 | Intro, avocado | `An avocado from Morro Bay.` | [hass/templates/home/market.html:3](../hass/templates/home/market.html#L3) | no record | [hass/content/products.json:5-13](../hass/content/products.json#L5-L13) (Hass avocado, `photo-product-001`) | The only fruit-category avocado record has `producerKey` null, brand "Avocado Shack", no origin field and no description of origin. No maker or product text names Morro Bay (the "Morro Bay" town appears only as the shop's own town in [hass/content/store.json:5](../hass/content/store.json#L5)). See finding P-1. |
| HM-33 | Intro, bread | `A loaf from Atascadero.` | [hass/templates/home/market.html:3](../hass/templates/home/market.html#L3) | supported by repository record | [hass/content/makers.json:131-134](../hass/content/makers.json#L131-L134); [hass/content/products.json:951](../hass/content/products.json#L951); [hass/content/products.json:963](../hass/content/products.json#L963); [hass/content/products.json:974](../hass/content/products.json#L974); [hass/content/products.json:985](../hass/content/products.json#L985) | The Brian's story says it "makes old-world-style loaves in Atascadero" (a production statement, not just a base). Source URL stored at [hass/content/makers.json:134](../hass/content/makers.json#L134) (repository-recorded, not rechecked). Four active bread records, all Brian's. |
| HM-34 | Intro, cheese | `Cheese made in Cambria.` | [hass/templates/home/market.html:3](../hass/templates/home/market.html#L3) | supported by repository record | [hass/content/makers.json:11-14](../hass/content/makers.json#L11-L14); [hass/content/products.json:775-783](../hass/content/products.json#L775-L783); [hass/content/products.json:797](../hass/content/products.json#L797); [hass/content/products.json:808](../hass/content/products.json#L808); [hass/content/products.json:897](../hass/content/products.json#L897) | Stepladder's story says it makes its cheeses in a restored barn in the hills of Cambria. Applies to the four Stepladder cheese records, not to every cheese on the shelf (other cheeses name other makers). Source URL at [hass/content/makers.json:14](../hass/content/makers.json#L14). |
| HM-35 | Intro, invitation | `Explore our selection` | [hass/templates/home/market.html:3](../hass/templates/home/market.html#L3) | aspirational/non-factual | none | Invitation. |
| HM-36 | Intro, traceability | `follow the flavors back to the farms, kitchens, and makers from our community` | [hass/templates/home/market.html:3](../hass/templates/home/market.html#L3) | partially supported | [storefront-mockup/shop.js:12](../storefront-mockup/shop.js#L12); [storefront-mockup/shop.js:17](../storefront-mockup/shop.js#L17) | 105 of 170 active records link to a maker story and source URL ("Visit" link). 65 have no maker. "From our community" is undefined (L-1). |
| HM-37 | Search placeholder | `Food, producer, or town` | [hass/templates/home/market.html:5](../hass/templates/home/market.html#L5) | partially supported | [storefront-mockup/README.md:71](../storefront-mockup/README.md#L71); [storefront-mockup/shop.js:74](../storefront-mockup/shop.js#L74) | Functional label. Town search relies on the recorded maker base, so it finds only the 105 records that have one. |
| HM-38 | No-script text, call | `You can still visit us or call to ask what is in today.` | [hass/templates/home/market.html:8](../hass/templates/home/market.html#L8) | no record | [hass/content/store.json:1-10](../hass/content/store.json#L1-L10) | No phone number is in the store record (the phone slot is optional and absent), so the page shows none. No record that anyone can say "what is in today" by phone or in person; availability is not synchronized to stock ([OWNER_AND_PRODUCT_BRIEF.txt:8-9](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L8-L9)). |

Filter button labels (Packaged goods, Fresh produce, All items, All shelves, Fruit, Vegetables, Dairy &amp; cheese, Eggs, Meat, Pantry, Drinks &amp; coffee, Bread, Flowers) match the nine product categories in the content (pantry 61, vegetables 52, dairy 22, drinks 15, fruit 13, bread 4, meat 3, eggs 1, flowers 1, all 172 records) and are not claims.

### 3.3 "Why we do it" ([our-way.html](../hass/templates/home/our-way.html))

| ID | Element | Quote | Source | Status | Evidence | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| HM-40 | Label and heading | `WHY WE DO IT` / `Know the food.` / `Know the people.` | [hass/templates/home/our-way.html:1](../hass/templates/home/our-way.html#L1) | aspirational/non-factual | none | Slogan. |
| HM-41 | Opinion | `Healthy, wholesome food should feel like a pleasure.` | [hass/templates/home/our-way.html:1](../hass/templates/home/our-way.html#L1) | aspirational/non-factual | none | Opinion. |
| HM-42 | Seasons | `We follow the seasons,` | [hass/templates/home/our-way.html:1](../hass/templates/home/our-way.html#L1) | partially supported | as HM-03 | Brand intent only; no season data. |
| HM-43 | Organic choices | `look for organic choices,` | [hass/templates/home/our-way.html:1](../hass/templates/home/our-way.html#L1) | partially supported | [storefront-mockup/shop.js:8](../storefront-mockup/shop.js#L8); [storefront-mockup/README.md:20](../storefront-mockup/README.md#L20) | 18 active records carry the organic badge. See finding O-1. |
| HM-44 | Flavor | `care about flavor first` | [hass/templates/home/our-way.html:1](../hass/templates/home/our-way.html#L1) | aspirational/non-factual | none | Opinion. |
| HM-45 | Illustrations | `the tomato you eat over the sink, the bread you tear before you get home` | [hass/templates/home/our-way.html:1](../hass/templates/home/our-way.html#L1) | aspirational/non-factual | none | Illustration. |
| HM-46 | Local relationships | `Local relationships are at the heart of the Shack.` | [hass/templates/home/our-way.html:1](../hass/templates/home/our-way.html#L1) | aspirational/non-factual | [HERMES_HANDOFF.txt:41](../HERMES_HANDOFF.txt#L41) | Ethos. The factual part (relationships exist) is HM-12: no record. |
| HM-47 | Know the grower | `We want you to know the grower, the town, and the work behind what you eat.` | [hass/templates/home/our-way.html:1](../hass/templates/home/our-way.html#L1) | partially supported | as HM-14 | A stated wish; the page can show grower, base and story for only 105 of 170 active records. |
| HM-48 | Farther afield | `You’ll also find good food from independent makers farther afield.` | [hass/templates/home/our-way.html:1](../hass/templates/home/our-way.html#L1) | partially supported | [hass/content/makers.json:113-116](../hass/content/makers.json#L113-L116) (Wisconsin); [hass/content/makers.json:149-152](../hass/content/makers.json#L149-L152) (New York) | Two makers are based outside California (1 record each). "Independent" is not recorded as a status for any maker. |
| HM-49 | Place and story | `Every good thing has a place and a story.` | [hass/templates/home/our-way.html:1](../hass/templates/home/our-way.html#L1) | partially supported | [storefront-mockup/shop.js:12](../storefront-mockup/shop.js#L12) | 65 of 170 active records have no maker, so no place or story; the page itself says "Ask us about the source in store." for them. |
| HM-50 | Closing | `Supporting a small farm or an independent maker keeps more than a product on a shelf. It keeps a relationship going.` / `That’s the kind of market we want to be.` | [hass/templates/home/our-way.html:1](../hass/templates/home/our-way.html#L1) | aspirational/non-factual | none | Ethos. |

### 3.4 Visit block ([visit.html](../hass/templates/home/visit.html))

| ID | Element | Quote | Source | Status | Evidence | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| HM-60 | Label | `COME ON IN` | [hass/templates/home/visit.html:1](../hass/templates/home/visit.html#L1) | aspirational/non-factual | none | Invitation. |
| HM-61 | Heading | `A market with` / `a person behind it.` | [hass/templates/home/visit.html:1](../hass/templates/home/visit.html#L1) | supported by repository record | [reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt:3](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L3) | Owner is recorded; the line is also a slogan. |
| HM-62 | Signature (also in the newsletter block, HM-72) | `With much gratitude,` / `Michael` | [hass/templates/home/visit.html:1](../hass/templates/home/visit.html#L1) | partially supported | [reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt:4-6](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L4-L6) | Owner voice ("gratitude") is recorded as brand intent. No record that Michael read or approved this signed wording. |
| HM-63 | Photo alt | `Michael Wolfe at Avocado Shack` | [hass/templates/home/visit.html:1](../hass/templates/home/visit.html#L1) | partially supported | [hass/content/community.json:5](../hass/content/community.json#L5); [hass/tests/test_image_dimensions.py:76](../hass/tests/test_image_dimensions.py#L76) | Name of the owner is recorded. No record of who is in `assets/michael.jpg` or where it was taken. Reader's observation, not a record: the photo shows a produce shop entrance. |

The Visit block's link `Find the Shack` is navigation to a Google Maps search built in code ([sitegen.py:236](../hass/sitegen.py#L236)); its words are in the register.

### 3.5 Newsletter ([newsletter.html](../hass/templates/home/newsletter.html))

| ID | Element | Quote | Source | Status | Evidence | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| HM-70 | Label and heading | `A LETTER FROM MICHAEL` / `A little news.` / `A little gratitude.` | [hass/templates/home/newsletter.html:1](../hass/templates/home/newsletter.html#L1) | partially supported | [reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt:5-6](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L5-L6); [hass/content/community.json:7](../hass/content/community.json#L7) | Michael's newsletters are described in the brief. No record that a newsletter has been sent through this site; delivery is not connected. |
| HM-71 | Description | `Good food, local people, and the things that bring us together.` | [hass/templates/home/newsletter.html:1](../hass/templates/home/newsletter.html#L1) | aspirational/non-factual | none | Slogan. |
| HM-72 | Subscribe promise | `Subscribe to Michael’s community newsletter for notes from the Shack and life here on the Central Coast.` | [hass/templates/home/newsletter.html:1](../hass/templates/home/newsletter.html#L1) | partially supported | [hass/content/community.json:7](../hass/content/community.json#L7); [storefront-mockup/README.md:47](../storefront-mockup/README.md#L47); [storefront-mockup/community.js:175-177](../storefront-mockup/community.js#L175-L177) | A signup form exists. Email delivery is not connected (`emailConnected` false) and on a static host the form is disabled and nothing is sent. See finding C-4 and the privacy rows PV-08 and PV-09. |
| HM-73 | Sign-off | `With much gratitude,` / `Michael` | [hass/templates/home/newsletter.html:1](../hass/templates/home/newsletter.html#L1) | partially supported | as HM-62 | As HM-62. |
| HM-74 | Checkbox | `Also send me North Coast Hiking Club updates.` | [hass/templates/home/newsletter.html:1](../hass/templates/home/newsletter.html#L1) | partially supported | [hass/content/community.json:7](../hass/content/community.json#L7); [hass/content/community.json:9](../hass/content/community.json#L9) | Same delivery caveat; the club has no scheduled event to send updates about (events empty). |
| HM-75 | Button | `Send me Michael’s newsletter` | [hass/templates/home/newsletter.html:1](../hass/templates/home/newsletter.html#L1) | partially supported | as HM-72 | The button promises sending; no sending path is connected. |
| HM-76 | Note | `Subscribe to hear from Michael.` | [hass/templates/home/newsletter.html:1](../hass/templates/home/newsletter.html#L1) | partially supported | as HM-72 | As HM-72. |
| HM-77 | Note | `No account needed.` | [hass/templates/home/newsletter.html:1](../hass/templates/home/newsletter.html#L1) | supported by repository record | [storefront-mockup/community.js:174](../storefront-mockup/community.js#L174) | The form takes an email address and the hiking checkbox only. |

## 4. /hike ([hike/index.html](../hass/templates/hike/index.html))

| ID | Element | Quote | Source | Status | Evidence | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| HK-01 | Page title | `North Coast Hiking Club` | [hass/templates/hike/index.html:5](../hass/templates/hike/index.html#L5) | supported by repository record | [hass/content/community.json:4](../hass/content/community.json#L4) | Club name is recorded. |
| HK-02 | Meta description, invitation | `Walk the Central Coast with Michael Wolfe and the North Coast Hiking Club.` | [hass/templates/hike/index.html:6](../hass/templates/hike/index.html#L6) | partially supported | [hass/content/community.json:4-5](../hass/content/community.json#L4-L5); [hass/content/community.json:9](../hass/content/community.json#L9) | Club and organizer are recorded. No scheduled or completed outing is recorded (`events` is empty), so no one can currently "walk with" him on a recorded date. |
| HK-03 | Meta description, next hike | `Explore the next hike,` | [hass/templates/hike/index.html:6](../hass/templates/hike/index.html#L6) | no record | [hass/content/community.json:9](../hass/content/community.json#L9); [reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt:17](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L17) | `events` is empty; "No actual next hike or past outings were supplied." A sample invitation exists in [hiking-preview.json](../storefront-mockup/hiking-preview.json) and is labelled as a sample on the page (AJ-02). |
| HK-04 | Meta description, maps and profiles | `trail maps, elevation profiles` | [hass/templates/hike/index.html:6](../hass/templates/hike/index.html#L6) | partially supported | [storefront-mockup/README.md:45](../storefront-mockup/README.md#L45); [storefront-mockup/community.js:11](../storefront-mockup/community.js#L11) | The trail explorer with map layers and a USGS-derived estimated elevation profile exists for Point Buchon only ([data file](../storefront-mockup/assets/trails/point-buchon.json)). The other two route ideas link out to external guides. |
| HK-05 | Meta description, outings | `and community outings.` | [hass/templates/hike/index.html:6](../hass/templates/hike/index.html#L6) | no record | [hass/content/community.json:9](../hass/content/community.json#L9); [reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt:17](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L17) | No outing recorded. Route ideas are "examples around SLO County, not scheduled events". |
| HK-06 | Hero label | `GOOD FOOD IS ONLY HALF THE STORY` | [hass/templates/hike/index.html:19](../hass/templates/hike/index.html#L19) | aspirational/non-factual | none | Slogan. |
| HK-07 | Heading | `North Coast` / `Hiking Club.` | [hass/templates/hike/index.html:19](../hass/templates/hike/index.html#L19) | supported by repository record | [hass/content/community.json:4](../hass/content/community.json#L4) | Name only. |
| HK-08 | Host photo alt | `Michael Wolfe, who leads the North Coast Hiking Club` | [hass/templates/hike/index.html:19](../hass/templates/hike/index.html#L19) | supported by repository record | [hass/content/community.json:5](../hass/content/community.json#L5) | `organizer` is Michael Wolfe. Photo provenance: see HK-09. |
| HK-09 | Host photo caption | `Out on the trail with` | [hass/templates/hike/index.html:19](../hass/templates/hike/index.html#L19) | no record | [hass/tests/test_image_dimensions.py:81](../hass/tests/test_image_dimensions.py#L81) | The same file `assets/michael.jpg` is described as "at Avocado Shack" on the home page (HM-63). No record of any trail outing. Reader's observation, not a record: the photo shows a produce shop entrance, not a trail (finding C-3). |
| HK-10 | Club description, ethos | `At the Shack, we care about what feeds us.` / `That includes getting outside.` | [hass/templates/hike/index.html:20](../hass/templates/hike/index.html#L20) | aspirational/non-factual | none | Opinion. |
| HK-11 | Club description, club | `Michael’s North Coast Hiking Club` | [hass/templates/hike/index.html:20](../hass/templates/hike/index.html#L20) | supported by repository record | [hass/content/community.json:4-5](../hass/content/community.json#L4-L5) | Club and organizer are recorded. |
| HK-12 | Club description, activity | `brings neighbors together for local walks,` | [hass/templates/hike/index.html:20](../hass/templates/hike/index.html#L20) | no record | [hass/content/community.json:9](../hass/content/community.json#L9); [reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt:17](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L17) | Present-tense activity. No walk (scheduled or completed) and no participant record exists. Route ideas and sample entries are not outings (finding C-1). "Neighbors" and "local" are undefined. |
| HK-13 | Club description, benefit | `a little exercise, and a closer look at this place we call home.` | [hass/templates/hike/index.html:20](../hass/templates/hike/index.html#L20) | aspirational/non-factual | none | Opinion. |
| HK-14 | Invitation | `Bring a friend, or come on your own. We’ll leave time for the view.` | [hass/templates/hike/index.html:20](../hass/templates/hike/index.html#L20) | aspirational/non-factual | none | Invitation; assumes a walk exists (HK-12). |
| HK-15 | Link | `Come along on the next hike` | [hass/templates/hike/index.html:20](../hass/templates/hike/index.html#L20) | no record | as HK-03 | Presupposes a next hike. |
| HK-16 | Loading text | `Loading the next hike…` | [hass/templates/hike/index.html:22](../hass/templates/hike/index.html#L22) | no record | as HK-03 | Presupposes a next hike; replaced by the empty state AJ-01 when events are empty. |
| HK-17 | No-script text | `Ask at the store for the next hike.` | [hass/templates/hike/index.html:22](../hass/templates/hike/index.html#L22) | no record | as HK-03; [hass/content/store.json:1-10](../hass/content/store.json#L1-L10) | No next hike is recorded and no record shows store staff hold hike details. |
| HK-18 | Journal heading | `THE CLUB’S TRAIL JOURNAL` / `A look back along the trail.` | [hass/templates/hike/index.html:23](../hass/templates/hike/index.html#L23) | no record | [hass/content/community.json:9](../hass/content/community.json#L9); [storefront-mockup/hiking-preview.json:1-3](../storefront-mockup/hiking-preview.json#L1-L3) | Implies past outings. None recorded. While samples are on, the section shows labelled sample entries instead (AJ-04). |
| HK-19 | Notify label | `AN INVITATION TO GET OUTSIDE` | [hass/templates/hike/index.html:24](../hass/templates/hike/index.html#L24) | aspirational/non-factual | none | Invitation. |
| HK-20 | Notify heading | `Hear about the next one.` | [hass/templates/hike/index.html:24](../hass/templates/hike/index.html#L24) | partially supported | [hass/content/community.json:7](../hass/content/community.json#L7); [storefront-mockup/community.js:175-177](../storefront-mockup/community.js#L175-L177) | A signup form exists; there is no next hike recorded and email delivery is not connected. |
| HK-21 | Notify text | `A new trail, a meeting time, and a good reason to get your shoes on.` | [hass/templates/hike/index.html:24](../hass/templates/hike/index.html#L24) | aspirational/non-factual | none | Invitation. |
| HK-22 | Separate consent | `Hiking updates only; Michael’s newsletter has its own signup.` | [hass/templates/hike/index.html:24](../hass/templates/hike/index.html#L24) | supported by repository record | [storefront-mockup/community.js:173-174](../storefront-mockup/community.js#L173-L174); [AGENTS.md:9](../AGENTS.md#L9) | The /hike form posts `newsletter:false,hikes:true`; the home form posts the newsletter choice with an optional hikes box. |
| HK-23 | Form button | `Keep me on the trail list` | [hass/templates/hike/index.html:24](../hass/templates/hike/index.html#L24) | partially supported | as HK-20 | The button promises a list; no delivery is connected. |

### 4.1 Text written onto /hike by `community.js` (adjacent; not in the templates)

These strings appear on the /hike page but live in the shared script. They are listed because they repeat or qualify the template claims above.

| ID | Element | Quote | Source | Status | Evidence | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| AJ-01 | Empty state | `No hike is currently scheduled.` | [storefront-mockup/community.js:127](../storefront-mockup/community.js#L127) | supported by repository record | [hass/content/community.json:9](../hass/content/community.json#L9) | Matches the empty events list. The same line also says "you’ll find the trail, date, meeting point, and RSVP here", a promise about the future. |
| AJ-02 | Sample caption | `Sample invitation · plans to be confirmed` | [storefront-mockup/community.js:60](../storefront-mockup/community.js#L60) | supported by repository record | [storefront-mockup/hiking-preview.json:3](../storefront-mockup/hiking-preview.json#L3) | Labels the sample correctly. The sample's date (2026-11-08) is already past on the audit date, so the page shows "Date to be confirmed" ([community.js:45](../storefront-mockup/community.js#L45)). |
| AJ-03 | Sample host note | `A community hike led by Michael Wolfe.` | [storefront-mockup/community.js:62](../storefront-mockup/community.js#L62) | no record | [hass/content/community.json:9](../hass/content/community.json#L9) | Printed on every invitation card including the sample; no hike is recorded as led by him. |
| AJ-04 | Sample archive note | `Sample archive · these outings are not confirmed club history.` | [storefront-mockup/community.js:130](../storefront-mockup/community.js#L130) | supported by repository record | [storefront-mockup/hiking-preview.json:4-7](../storefront-mockup/hiking-preview.json#L4-L7) | Correctly labelled. Sample dates "October 2026" and "September 2026" are not real outings. |
| AJ-05 | Default history note (shown when samples are off and no outing is recorded) | `Places and memories from our walks together.` | [storefront-mockup/community.js:130](../storefront-mockup/community.js#L130) | no record | [hass/content/community.json:9](../hass/content/community.json#L9) | Implies walks happened. |
| AJ-06 | Empty history | `We’re gathering the club’s past outings.` | [storefront-mockup/community.js:132](../storefront-mockup/community.js#L132) | no record | [hass/content/community.json:9](../hass/content/community.json#L9) | No record that anyone is gathering them. |
| AJ-07 | Sample RSVP result | `That’s how the RSVP will work. No details were saved or sent.` | [storefront-mockup/community.js:136](../storefront-mockup/community.js#L136) | supported by repository record | [storefront-mockup/community.js:136](../storefront-mockup/community.js#L136) | The handler cancels the submit and sends nothing. See PV-10. |
| AJ-08 | Signup closed | `Online signup isn’t open yet. Please say hello at the Shack instead.` | [storefront-mockup/community.js:176](../storefront-mockup/community.js#L176) | supported by repository record | [storefront-mockup/community.js:175-177](../storefront-mockup/community.js#L175-L177) | True when the page runs without the club service. |

## 5. 404 page ([404.html](../hass/templates/404.html))

The 404 repeats SH-01, SH-04, SH-05, SH-06 and SH-07. Its own copy:

| ID | Element | Quote | Source | Status | Evidence | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| NF-01 | Title and heading | `That page isn’t here.` | [hass/templates/404.html:15](../hass/templates/404.html#L15) | supported by repository record | [hass/templates/404.html:6](../hass/templates/404.html#L6) | True by definition of the page; the title uses the same words. |
| NF-02 | Explanation | `The link may be old, or the address may have a typo.` | [hass/templates/404.html:16](../hass/templates/404.html#L16) | aspirational/non-factual | none | Speculation, not a claim. |
| NF-03 | Pointer | `These two places are a good start.` | [hass/templates/404.html:16](../hass/templates/404.html#L16) | aspirational/non-factual | none | Opinion. |
| NF-04 | Link | `See the food` | [hass/templates/404.html:17](../hass/templates/404.html#L17) | aspirational/non-factual | none | Navigation. |
| NF-05 | Link | `Meet the hiking club` | [hass/templates/404.html:18](../hass/templates/404.html#L18) | partially supported | [hass/content/community.json:4-5](../hass/content/community.json#L4-L5) | The club exists; no meeting or event is recorded (HK-12). |

## 6. Privacy dialog (shared, `script.js:14`)

The dialog text is one string in [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14). It is opened by the Privacy button on the home page ([index.html:18](../hass/templates/index.html#L18), dialog [index.html:19](../hass/templates/index.html#L19)), /hike ([hike/index.html:27-28](../hass/templates/hike/index.html#L27-L28)) and the 404 ([404.html:21-22](../hass/templates/404.html#L21-L22)); the same wording therefore applies to all three, and also to the info pages (outside this audit).

Code inspected for the technical statements, at the audited commit: [script.js](../storefront-mockup/script.js), [shop.js](../storefront-mockup/shop.js), [catalog-products.js](../storefront-mockup/catalog-products.js), [producers.js](../storefront-mockup/producers.js), [community.js](../storefront-mockup/community.js), [trail-explorer.js](../storefront-mockup/trail-explorer.js), the three style sheets and the page templates. Search found no `document.cookie`, `localStorage`, `sessionStorage`, `sendBeacon`, `XMLHttpRequest`, analytics or tag-manager code, and no external script, font or style reference. The only `fetch` calls go to same-origin paths: `/api/community`, `/community.json`, `/hiking-preview.json`, the signup POST paths and `/assets/trails/point-buchon.json` ([community.js:147,154,159,168](../storefront-mockup/community.js#L147), [trail-explorer.js:19](../storefront-mockup/trail-explorer.js#L19)). This is bounded code evidence about this repository's files only, not a statement about the host, a proxy, or any later change.

| ID | Element | Quote | Source | Status | Evidence | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| PV-01 | Heading | `Your privacy matters.` | [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14) | aspirational/non-factual | none | Statement of intent. |
| PV-02 | Cookies | `This site doesn’t use cookies` | [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14) | supported by repository record | the code search above; the string `Set-Cookie` does not occur anywhere in [community-server.py](../storefront-mockup/community-server.py) | Bounded to inspected files. A host or proxy may set cookies; the repository does not show the host. |
| PV-03 | Analytics | `analytics` | [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14) | supported by repository record | the code search above | Same bound. Part of the sentence "doesn’t use cookies, analytics or advertising trackers". |
| PV-04 | Trackers | `advertising trackers` | [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14) | supported by repository record | the code search above | Same bound. No third-party script or font is loaded by the templates; links the visitor follows leave the site (PV-12). |
| PV-05 | Search | `Catalog search and filters work inside this page.` | [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14) | supported by repository record | [storefront-mockup/shop.js:74](../storefront-mockup/shop.js#L74); [storefront-mockup/shop.js:89](../storefront-mockup/shop.js#L89) | Filtering runs in the browser on the loaded catalog; `shop.js` contains no `fetch`. Applies to the home page; /hike and the 404 have no catalog. |
| PV-06 | No sales | `Nothing is sold on this website,` | [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14) | supported by repository record | [AGENTS.md:8](../AGENTS.md#L8); [hass/tests/test_publish.py:87](../hass/tests/test_publish.py#L87); [reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt:9](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L9) | The published build is checked for commerce markup. The working folder still holds an archived commerce preview and a historical `catalog.js` with a price field ([catalog.js:1](../storefront-mockup/catalog.js#L1)); the page templates do not load it. |
| PV-07 | Payment | `so no payment information is collected.` | [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14) | supported by repository record | as PV-06 | The signup forms collect an email address (and an optional checkbox), which the sentence does not mention. |
| PV-08 | Signup status | `Online signup for Michael’s newsletter and hiking updates isn’t open yet.` | [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14) | partially supported | [storefront-mockup/community.js:163](../storefront-mockup/community.js#L163); [storefront-mockup/community.js:176-177](../storefront-mockup/community.js#L176-L177); [hass/sitegen.py:462-463](../hass/sitegen.py#L462-L463); [storefront-mockup/community-server.py:89](../storefront-mockup/community-server.py#L89) | True on a static published build (the no-service marker and disabled forms). Not true on the local service-backed sandbox, where `acceptsSubmissions` is true and signups are saved ([README.md:47](../storefront-mockup/README.md#L47)). The repository does not record which mode a given host runs. |
| PV-09 | No send or save | `Until it is, those forms don’t send or save what you type,` | [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14) | partially supported | [storefront-mockup/community.js:167](../storefront-mockup/community.js#L167); [storefront-mockup/community.js:140](../storefront-mockup/community.js#L140); [storefront-mockup/community.js:147](../storefront-mockup/community.js#L147) | Without the service, `send()` stops before any POST and the forms are disabled. While the page asks `GET /api/community` (no visitor data) the forms are still enabled. In service-backed mode submissions are saved. The sentence is a static-mode statement only. |
| PV-10 | Sample RSVP | `and the sample hike RSVP never leaves your browser.` | [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14) | supported by repository record | [storefront-mockup/community.js:136](../storefront-mockup/community.js#L136); [storefront-mockup/README.md:45](../storefront-mockup/README.md#L45) | The sample handler prevents submission and has no network call. A real-event RSVP form can POST in service-backed mode ([community.js:178](../storefront-mockup/community.js#L178)); none is possible while events are empty. |
| PV-11 | Ask in store | `To hear about news or the next hike, ask us at the Shack.` | [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14) | no record | [hass/content/community.json:9](../hass/content/community.json#L9) | An operational promise. No next hike is recorded and no record shows how staff would give news. |
| PV-12 | Outbound links | `Links to producers, trail information and maps go to other websites,` | [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14) | supported by repository record | [storefront-mockup/shop.js:17](../storefront-mockup/shop.js#L17); [storefront-mockup/community.js:19](../storefront-mockup/community.js#L19); [hass/sitegen.py:236](../hass/sitegen.py#L236) | Producer "Visit" links use the stored maker URL; trail links use route-idea `sourceUrl`; "Find the Shack" and "Directions" open Google Maps. Photo-credit links to Wikimedia and Creative Commons ([community.js:31](../storefront-mockup/community.js#L31)) are not named in the sentence. |
| PV-13 | Their policies | `which have their own privacy policies.` | [storefront-mockup/script.js:14](../storefront-mockup/script.js#L14) | no record | none | No external site was checked and no policy is stored. Stored maker URLs (for example [hass/content/makers.json:14](../hass/content/makers.json#L14)) are repository-recorded, not rechecked. |

## 7. Findings by topic

**Places**

- P-1. "An avocado from Morro Bay" (HM-32): no record. The only fruit-category avocado is `photo-product-001`, no maker, no origin. Other active records whose name contains "avocado" are Stepladder avocado blossom honey (Stepladder, Cambria, [products.json:1127](../hass/content/products.json#L1127)) and two items whose names contain "Avocado Shack" (`photo-product-092`, `photo-product-093`); none is an avocado fruit and none names Morro Bay. A search for "Morro" in product and maker text finds only the word "tomorrow" in a melon description ([products.json:93-97](../hass/content/products.json#L93)). A historical, unloaded record ([catalog.json:3-12](../storefront-mockup/catalog.json#L3)) says the owner confirmed the variety (Hass) and selling terms, but gives no origin.
- P-2. "A loaf from Atascadero" and "Cheese made in Cambria" (HM-33, HM-34) are backed by production statements in the maker stories, not only by the maker's base. They hold for those makers' records, not for every loaf or cheese.
- P-3. 65 of 170 active records have no maker (`producerKey` null); the page shows "Ask us about the source in store." for them ([shop.js:12](../storefront-mockup/shop.js#L12)). Claims that every item has a place and story (HM-49) or can be followed back to a farm (HM-36) are therefore only partly supported.

**Organic**

- O-1. 18 active records carry the organic badge; the rule is "name contains organic" or the maker is Ocean Ranch, Straus, Green Gold or Massa Organics ([shop.js:8](../storefront-mockup/shop.js#L8)): 7 dairy (all Straus), 5 microgreens (all Green Gold), 5 pantry, 1 drink. For fresh produce, only the microgreens qualify; the other 61 fruit/vegetable/flower records have no organic claim. The record for the claim is a stored maker sentence (for example "certified organic by CCOF", [makers.json:97](../hass/content/makers.json#L97)); no certificate or number is stored. A maker's organic statement may cover a farm or product line rather than every record that carries the maker's name (Straus: "family farm became certified organic in 1994", [makers.json:37](../hass/content/makers.json#L37)).
- O-2. Organic wording in stories without a badge: Etto ([makers.json:7](../hass/content/makers.json#L7)), Fair Hills Farm ([makers.json:19](../hass/content/makers.json#L19)), Joebella coffee ("certified organic" café and roasting facility, [makers.json:55](../hass/content/makers.json#L55)), AG Berries ("her brother’s dream of organic farming", [makers.json:91](../hass/content/makers.json#L91)), Maple Valley ([makers.json:115](../hass/content/makers.json#L115)) and Sean's ([makers.json:145](../hass/content/makers.json#L145)). The badge rule and the stories are not aligned; the audit records this, not which is right.

**Local**

- L-1. "Local" appears in SH-02, HM-04, HM-12, HM-46, HM-71 and HK-12. No record defines it (distance, county or town list). Section 8 lists the 26 recorded maker bases without classifying any as local. The handoff says known maker location "does not prove every ingredient is local" ([HERMES_HANDOFF.txt:43](../HERMES_HANDOFF.txt#L43)).

**People**

- The only person named in fixed copy is Michael Wolfe (HM-63, HK-02, HK-08, HK-09, HK-11, AJ-03) plus the first-name signature "Michael" (HM-62, HM-73). The owner and organizer roles are recorded ([OWNER_AND_PRODUCT_BRIEF.txt:3](../reports/hermes-handoff/OWNER_AND_PRODUCT_BRIEF.txt#L3), [community.json:5](../hass/content/community.json#L5)). "Familiar faces" (SH-03) and "neighbors" (HK-12) name no one. Maker people named in stories are content records, not fixed copy.

**What the club does**

- C-1. The club exists in the record; its activity does not. `events` is empty, `emailConnected` is false, and the three route ideas (Point Buchon, Cass Hill, Fiscalini Ranch) are ideas with `status` "idea" and `rsvpEnabled` false ([community.json:9-64](../hass/content/community.json#L9)). Samples in `hiking-preview.json` are labelled as samples on the page (AJ-02, AJ-04). Present-tense claims (HK-12, HK-18, AJ-03, AJ-05) have no record of a real walk.
- C-2. Hike facts in the sample (meeting point, times) are sample content, not audited as fixed copy.
- C-3. One image file, `assets/michael.jpg`, is described as "at Avocado Shack" (HM-63) and captioned "Out on the trail" (HK-09). No record says where it was taken.
- C-4. The home newsletter block and /hike notify block invite signup (HM-72 to HM-76, HK-20, HK-23), while the privacy dialog says online signup is not open (PV-08, PV-09). Both are right in different modes: on a static host the forms are disabled with that message; in the sandbox they save but no email can be sent.

**Other observations (no verdict)**

- The 404 header and footer links are hard-coded copies ([404.html:12](../hass/templates/404.html#L12), [404.html:21](../hass/templates/404.html#L21)) and always show all four sections; the home and /hike link lists follow which home parts are shown.
- The catalog places the Taco Works tortilla chips (`photo-product-018`) in the "vegetables" category; that is a catalog matter outside this audit.

## 8. Maker bases recorded (all 26)

Recorded `place` text from [makers.json](../hass/content/makers.json), with the count of active product records that name the maker. A base is not an ingredient origin.

| Maker | Recorded base | makers.json | Active records | Story mentions "organic" |
| --- | --- | --- | --- | --- |
| Etto | Paso Robles, California | [makers.json:5](../hass/content/makers.json#L5) | 5 | yes |
| Stepladder | Cambria, California | [makers.json:11](../hass/content/makers.json#L11) | 8 | no |
| Fair Hills Farm | San Miguel, California | [makers.json:17](../hass/content/makers.json#L17) | 5 | yes |
| Ocean Ranch | Carpinteria, California | [makers.json:23](../hass/content/makers.json#L23) | 4 | yes |
| Linn's | Cambria, California | [makers.json:29](../hass/content/makers.json#L29) | 8 | no |
| Straus | Northern California | [makers.json:35](../hass/content/makers.json#L35) | 7 | yes |
| Cal Poly | San Luis Obispo, California | [makers.json:41](../hass/content/makers.json#L41) | 21 | no |
| Alle-Pia | California’s Central Coast | [makers.json:47](../hass/content/makers.json#L47) | 3 | no |
| Joebella / Avocado Shack | Atascadero, California | [makers.json:53](../hass/content/makers.json#L53) | 8 | yes |
| Corberosa | California’s Central Coast | [makers.json:59](../hass/content/makers.json#L59) | 1 | no |
| Sunshine Olive | Templeton, California | [makers.json:65](../hass/content/makers.json#L65) | 2 | no |
| Big Sur Honey Company | Big Sur, California | [makers.json:71](../hass/content/makers.json#L71) | 1 | no |
| Massa Organics | Near Chico, California | [makers.json:77](../hass/content/makers.json#L77) | 1 | yes |
| Mighty Cap Mushrooms | Paso Robles, California | [makers.json:83](../hass/content/makers.json#L83) | 7 | no |
| AG Berries | Arroyo Grande, California | [makers.json:89](../hass/content/makers.json#L89) | 1 | yes |
| Green Gold | Arroyo Grande, California | [makers.json:95](../hass/content/makers.json#L95) | 5 | yes |
| Stardust Grove | Cambria, California | [makers.json:101](../hass/content/makers.json#L101) | 2 | no |
| Taco Works | San Luis Obispo, California | [makers.json:107](../hass/content/makers.json#L107) | 1 | no |
| Maple Valley | Cashton, Wisconsin | [makers.json:113](../hass/content/makers.json#L113) | 1 | yes |
| Sierra Nevada | Glenn County, California | [makers.json:119](../hass/content/makers.json#L119) | 2 | no |
| Cayucos | Cayucos, California | [makers.json:125](../hass/content/makers.json#L125) | 3 | no |
| Brian's | Atascadero, California | [makers.json:131](../hass/content/makers.json#L131) | 4 | no |
| Jayleaf | Hollister, California | [makers.json:137](../hass/content/makers.json#L137) | 2 | no |
| Sean's | San Luis Obispo, California | [makers.json:143](../hass/content/makers.json#L143) | 1 | yes |
| Love Beets | Rochester, New York | [makers.json:149](../hass/content/makers.json#L149) | 1 | no |
| Ava’s | Coachella Valley, California | [makers.json:155](../hass/content/makers.json#L155) | 1 | no |
| (no maker) | none recorded | - | 65 | - |

## 9. Coverage register

**Inspected blocks (all fixed copy, in source order).**

- Home `index.html`: head (title HM-01, description HM-02 to HM-06, structured data HM-07), skip link "Skip to the food", top line (SH-02, SH-03; address slot excluded), brand lockup (SH-01, logo alt "Avocado Shack" is the name only), top strip (SH-04, SH-05), nav, hero (HM-08 to HM-21), `home.sections`, footer (SH-06, SH-07), privacy button and dialog shell, script includes.
- `home/market.html`: HM-30 to HM-38; filter and category buttons (labels, see 3.2), "See more food" and "Clear filters" buttons (non-factual).
- `home/our-way.html`: HM-40 to HM-50.
- `home/visit.html`: HM-60 to HM-63; the editable story, hours, phone and hours status are excluded; link "Find the Shack" (navigation).
- `home/newsletter.html`: HM-70 to HM-77; email placeholder `you@example.com` and label "Your email address" (non-factual).
- `home/nav.html`, `footer.html`, `hike-nav.html`, `hike-footer.html`, `banner.html`, `strip.html`: link labels and the strip (SH rows); banner text is an editable slot.
- `hike/index.html`: HK-01 to HK-23; skip link "Skip to the hiking club"; placeholder text (non-factual); script includes.
- `404.html`: NF-01 to NF-05; `noindex` meta (no claim); shared rows SH-01, SH-04 to SH-07; skip link "Skip to the page".
- `script.js:14`: PV-01 to PV-13; the dialog's close label "Close details" and `aria-label` "Avocado Shack" are non-factual.
- `community.js` strings written onto /hike: AJ-01 to AJ-08 (listed because they qualify the template claims). Other strings in that script (hike facts, buttons, error messages) are logistics or system messages and are not inventoried.

**Shared duplicates and where they appear.**

| Canonical | Appears on |
| --- | --- |
| SH-01 THE NEIGHBORHOOD MARKET | home index.html:14, hike:15, 404:12 |
| SH-02, SH-03 top line | home index.html:13, hike:14 |
| SH-04, SH-05 top strip | home and /hike via strip.html:1 (front.bannerHtml), 404:11 |
| SH-06 footer slogan | home 18, hike 27, 404 21 |
| SH-07 footer newsletter link | home footer.html:1, hike hike-footer.html:1, 404:21 |
| HM-62 / HM-73 signature | home visit.html:1 and newsletter.html:1 |
| PV-01 to PV-13 | script.js:14, opened from home, /hike and the 404 |

**Excluded as Hass-editable slots (not audited as fixed copy).** `store.headlineHtml` (default words at [content_model.py:80](../hass/content_model.py#L80)), `store.introHtml` (default at [:82](../hass/content_model.py#L82)), `store.storyHtml` (default at [:79](../hass/content_model.py#L79)), `club.introHtml` (the /hike opening paragraph, AV2152-09; default at [:49](../hass/content_model.py#L49)), the owner hero image and its alt when set, `store.noticeHtml`, `specials.html`, `front.bannerHtml` text, `selection.checkedNote` (a generated freshness sentence), `store.addressLine`, `store.addressShort`, `store.hoursHtml`, `store.hoursStatusHtml`, `store.phoneHtml`, the order and shown flags of the four home parts, the About, Getting here, Policies and FAQ pages, product and maker records, route ideas, events and `hiking-preview.json` sample content. The hours and address text come from [store.json:4-8](../hass/content/store.json#L4); they are the owner's and were not checked against any outside source.

## 10. Review checks run (manual, no new test code)

- `test_claim_inventory_complete`: each template was read in source order; every factual clause is a row or is named in the coverage register above.
- `test_unknown_origin_not_inferred`: HM-32 stays "no record"; a null maker, the honey and coffee name matches, base versus ingredient origin (P-2) and the narrow organic scope (O-1, O-2) are kept apart.
- `test_samples_not_real_events`: HK-03, HK-05, HK-12, HK-18 stay "no record" or "partially supported" because only route ideas and labelled samples exist; `events` empty is stated in C-1.
- `test_privacy_mode_qualifiers`: PV-08 and PV-09 are "partially supported" because static and service-backed modes differ; PV-02 to PV-04 are bounded to inspected files and say nothing about the host.
- `test_sources_and_duplicates`: every path:line in this report was resolved against the audited commit by a throwaway script (file exists, line exists, quoted words are on the cited line). Repeated shared copy maps to one canonical row with every location listed (section 9).

## 11. Unresolved evidence questions for Michael and G

None of these asks for new words. Any change to site copy needs their decision.

1. Is there an avocado sold at the Shack that comes from a Morro Bay grower? If so, which grower, and where would the record live?
2. What does "local" mean for the Shack (distance, county, a list of towns)?
3. Which fresh produce is organic, and where is the certificate or the supplier statement kept?
4. How are "seasonal" and "fresh" decided for the produce listings?
5. Which growers does the Shack have a relationship with, and in what sense?
6. Has any newsletter been sent, and from where? When will delivery and signup open?
7. Has the club held or planned any real outing? Until it has, the present-tense club claims remain without a record.
8. Where and when was `assets/michael.jpg` taken, and is it the right picture for both captions?
9. Should the page show a phone number, since the no-script text says "call"?
10. Which mode does the live host run (static or service-backed), and does the host set cookies or collect logs? The privacy dialog is true for the code only.
11. Who answers "ask us at the Shack" requests about news or the next hike, and is there a process?
12. Does "independent" describe every listed maker, and on what record?

**Decision:** this report changes no copy and makes no business decision. Michael and G decide whether any words are rewritten.
