# Storefront CSS selector use

## R1. Summary by stylesheet

| Stylesheet | Class names | Seen in checked-in HTML/JS | Seen including generator | ID names | Seen in checked-in HTML/JS | Seen including generator | No source match, including generator |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `style.css` | 102 | 63 | 67 | 10 | 6 | 6 | 39 |
| `hiking.css` | 41 | 40 | 40 | 1 | 1 | 1 | 1 |
| `trail-explorer.css` | 39 | 39 | 39 | 0 | 0 | 0 | 0 |

**Finding:** 40 names have no match in the scanned source (36 classes and 4 uncertain IDs). Four additional classes look unused in the checked-in storefront but are emitted by the generator. There are 56 names without an explicit class or ID rule; that does not mean 56 broken styles.

**Source and check:** Offline scan on 2026-11-21 of `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, identical to the requested baseline. Paths in the tables are relative to `storefront-mockup/` unless prefixed with `hass/`. The scan read the three stylesheets, six tracked pages (home, about, FAQ, getting here, hike and policies) and ten top-level `.js` files, including scripts not tagged in the checked-in pages. It excluded `archive/`, `commerce/` and QA scripts. A separate generator pass read literal `class`/`id` attributes in `hass/templates/`, `hass/sitegen.py`, `hass/notice.py` and `hass/specials.py`, without rendering or reading any runtime inputs. See `AGENTS.md:3–4` for the active source boundary.

**Match method:** Count each distinct case-sensitive `.class` or `#id` name once per sheet, including names in compound selectors, comma lists, `:not()` and media queries. Match classes to complete class tokens and IDs to complete ID tokens. The scan walked parsed CSS rules (not declarations, so hex colors do not count) and searched page markup, JavaScript string/template markup, literal DOM assignments and lookups (`$` and `q` included), class-list operations, fragment and ID references, and the SVG helper's class attributes. Product-data `id` properties and `data-product-id` are not DOM IDs (`shop.js:22`). Three conditional class strings were resolved from their literal alternatives (`community.js:59,61,108`); `community.js:114` instead takes an ID from event data, so its produced names cannot be enumerated here.

**Limits:** “Seen” means a source reference, not proof that the script runs, the page loads that stylesheet, or the full selector matches in a browser. The scan does not resolve general string concatenation, runtime/API data, or selector composition and does not evaluate reachability, cascade, inheritance or layout. The three local stylesheets are linked at `index.html:7`, `about/index.html:7`, `faq/index.html:7`, `getting-here/index.html:7`, `hike/index.html:7–9` and `policies/index.html:7`; no inline `<style>` block or CSS `@import` was found in these inputs.

**Read-only evidence:** In the 2026-11-21 parsed output, total class/ID token occurrences (counting repetition) were `514/19`, `240/6`, `118/0` respectively; occurrences with a name match including generator markup were `404/14`, `234/6`, `118/0`. To reproduce the inventory and spot-check the anchors from a clone at the source commit:

```sh
git rev-parse origin/main
git ls-files -- 'storefront-mockup/*.html' 'storefront-mockup/*.js' 'storefront-mockup/*.css' ':!storefront-mockup/archive'
git grep -n -o -w -e special-deal -e special-image -e special-link -e catalog-note -- 'storefront-mockup/*.css' hass/sitegen.py hass/specials.py
git grep -n -o -w -e trail-map -e trail-photograph -- storefront-mockup/community.js storefront-mockup/hiking.css storefront-mockup/trail-explorer.css
```

## R2. Selector names with no source match

All 40, sorted by name (limit 60). The four `Uncertain` rows have no named reference. The event renderer can nevertheless emit an ID from data if it does not duplicate an existing ID (`community.js:59,88,113–114,158`). No source indicates that these four names are intended event IDs. No comparable unresolved class builder was found. `.catalog-note`, `.special-deal`, `.special-image` and `.special-link` are **not** in this table: their exact emissions are at `hass/sitegen.py:169` and `hass/specials.py:33,35,38`.

| Name | CSS lines containing the selector | Result |
| --- | --- | --- |
| `.action` | `style.css:1` | No source match |
| `.add` | `style.css:1, 3` | No source match |
| `.approval` | `style.css:1` | No source match |
| `.attachment` | `style.css:1` | No source match |
| `#bag` | `style.css:1, 12` | Uncertain (event-ID input) |
| `.box-options` | `style.css:1` | No source match |
| `.boxes` | `style.css:1` | No source match |
| `.brief` | `style.css:1` | No source match |
| `.bubble` | `style.css:1` | No source match |
| `.chat-controls` | `style.css:1` | No source match |
| `.chat-head` | `style.css:1` | No source match |
| `#chat-note` | `style.css:1` | Uncertain (event-ID input) |
| `.club-content` | `style.css:21, 22` | No source match |
| `.club-section-head` | `style.css:21, 22` | No source match |
| `.conversation` | `style.css:1` | No source match |
| `.detail-visit` | `style.css:16` | No source match |
| `.food-detail` | `style.css:16` | No source match |
| `.fulfillment` | `style.css:1, 9` | No source match |
| `.hass` | `style.css:1` | No source match |
| `.maker-note` | `style.css:16, 17, 18` | No source match |
| `#messages` | `style.css:1` | Uncertain (event-ID input) |
| `.method-choice` | `style.css:3` | No source match |
| `.owner-grid` | `style.css:1` | No source match |
| `.owner-intro` | `style.css:1` | No source match |
| `.owner-main` | `style.css:1` | No source match |
| `.past-hike` | `style.css:21` | No source match |
| `.product-actions` | `style.css:3, 4, 6` | No source match |
| `.product-story` | `style.css:6` | No source match |
| `.prompts` | `style.css:1` | No source match |
| `.route-character` | `style.css:24` | No source match |
| `.route-idea` | `style.css:24` | No source match |
| `.route-ideas` | `style.css:24` | No source match |
| `.route-place` | `style.css:24` | No source match |
| `.route-title` | `style.css:24` | No source match |
| `.shop-directory` | `style.css:3` | No source match |
| `.signup` | `style.css:1` | No source match |
| `.subtotal` | `style.css:3` | No source match |
| `#toast` | `style.css:1` | Uncertain (event-ID input) |
| `.trail-map` | `hiking.css:24, 25, 26, 27, 80` | No source match |
| `.user` | `style.css:1` | No source match |

## R3. Names used without an explicit rule in any of the three stylesheets

All 56 (limit 60), including the 54 found from storefront HTML/JS alone. Each row quotes the relevant attribute, name or selector fragment, not the rest of its source line. An ID may be a link target, form label or script hook rather than a styling target. A class can be a hook or receive styling through a different selector. `#route-ideas-heading` is a legacy fragment, not a missing element to add: `script.js:24–25` redirects it to `#hikes`.

| Name | Source line | Quote | Reference type |
| --- | --- | --- | --- |
| `#avail-filter` | `shop.js:56` | `id="avail-filter"` | markup |
| `.availability` | `shop.js:13` | `class="product-meta availability"` | markup |
| `#brand-filter` | `index.html:21` | `id="brand-filter"` | markup |
| `.card-link` | `shop.js:22` | `class="text-link card-link"` | markup |
| `#catalog-count` | `index.html:24` | `id="catalog-count"` | markup |
| `#catalog-item-status` | `shop.js:6` | `id="catalog-item-status"` | markup |
| `#community-newsletter` | `index.html:28` | `id="community-newsletter"` | markup |
| `#dialog` | `about/index.html:18` | `id="dialog"` | markup |
| `#dialog-title` | `script.js:7` | `id='dialog-title'` | DOM API |
| `#featured-hike-title` | `community.js:62` | `id="featured-hike-title"` | markup |
| `.food-identity` | `shop.js:22` | `class="food-identity"` | markup |
| `.hike-access` | `community.js:18` | `class="hike-access"` | markup |
| `.hike-cancel-note` | `community.js:51` | `class="club-small hike-cancel-note"` | markup |
| `.hike-cancelled` | `community.js:59` | `hike-cancelled` in class template | markup |
| `#hike-email` | `hike/index.html:24` | `id="hike-email"` | markup |
| `.hike-full` | `community.js:108` | `hike-full` in class template | markup |
| `.hike-ics` | `community.js:29` | `class="text-link hike-ics"` | markup |
| `.hike-route` | `community.js:19` | `class="hike-route"` | markup |
| `#hike-updates` | `hike/index.html:24` | `id="hike-updates"` | markup |
| `#hikes` | `hike/index.html:17` | `id="hikes"` | markup |
| `#hiking-heading` | `hike/index.html:19` | `id="hiking-heading"` | markup |
| `#history-context` | `hike/index.html:23` | `id="history-context"` | markup |
| `.home-notice` | `hass/notice.py:64` | `class="home-notice"` | generator markup |
| `#main` | `about/index.html:13` | `id="main"` | markup |
| `.maker-name` | `shop.js:22` | `class="sr-only maker-name"` | markup |
| `#market` | `index.html:17` | `id="market"` | markup |
| `#newsletter` | `index.html:28` | `id="newsletter"` | markup |
| `#newsletter-email` | `index.html:28` | `id="newsletter-email"` | markup |
| `#newsletter-heading` | `index.html:28` | `id="newsletter-heading"` | markup |
| `#next-hike-line` | `index.html:16` | `id="next-hike-line"` | markup |
| `#our-way` | `index.html:26` | `id="our-way"` | markup |
| `#past-heading` | `hike/index.html:23` | `id="past-heading"` | markup |
| `#past-hikes` | `hike/index.html:23` | `id="past-hikes"` | markup |
| `#preview-rsvp-email` | `community.js:51` | `id="preview-rsvp-email"` | markup |
| `#preview-rsvp-heading` | `community.js:51` | `id="preview-rsvp-heading"` | markup |
| `#preview-rsvp-name` | `community.js:51` | `id="preview-rsvp-name"` | markup |
| `#preview-rsvp-party` | `community.js:51` | `id="preview-rsvp-party"` | markup |
| `.product-price` | `shop.js:21` | `class="product-meta product-price"` | markup |
| `#product-search` | `index.html:21` | `id="product-search"` | markup |
| `#route-ideas-heading` | `script.js:24` | `#route-ideas-heading` | fragment |
| `#rsvp-email` | `community.js:178` | `id="rsvp-email"` | markup |
| `#rsvp-name` | `community.js:178` | `id="rsvp-name"` | markup |
| `#rsvp-party` | `community.js:178` | `id="rsvp-party"` | markup |
| `.selection-checked` | `hass/sitegen.py:169` | `class="catalog-note selection-checked"` | generator markup |
| `#specials-heading` | `hass/specials.py:49` | `id="specials-heading"` | generator markup |
| `.trail-basemap` | `trail-explorer.js:31` | `class="trail-basemap"` | markup |
| `#trail-distance` | `trail-explorer.js:37` | `id="trail-distance"` | markup |
| `#trail-elevation-readout` | `trail-explorer.js:37` | `id="trail-elevation-readout"` | markup |
| `#trail-explorer-heading` | `trail-explorer.js:29` | `id="trail-explorer-heading"` | markup |
| `.trail-journal-recap` | `community.js:88` | `class="trail-journal-recap"` | markup |
| `#trail-map-help` | `trail-explorer.js:36` | `id="trail-map-help"` | markup |
| `.trail-route-markers` | `trail-explorer.js:31` | `class="trail-route-markers"` | markup |
| `#upcoming-hikes` | `hike/index.html:22` | `id="upcoming-hikes"` | markup |
| `#visit` | `index.html:27` | `id="visit"` | markup |
| `.visit-open-status` | `index.html:27` | `class="micro visit-open-status"` | markup |
| `.visit-phone` | `hass/sitegen.py:73` | `class="visit-phone"` | generator markup |

## R4. Ranked gaps

1. **Check whether the hike state needs more visual distinction before calling it a CSS bug.** `.hike-cancelled`, `.hike-cancel-note` and `.hike-full` have no named rule, but the script supplies visible state text and reuses existing styles (`community.js:51,59,108`; `style.css:21`). A missing dedicated rule alone does not show an accessibility or layout defect.
2. **Keep generator cases in any future cleanup review.** The specials rules at `style.css:74–83` cover markup from `hass/specials.py:33–49`, and `.selection-checked` shares the styled `.catalog-note` element (`hass/sitegen.py:169`; `style.css:16`; `shop.js:46`). These are not dead-weight or typo findings. Likewise, `.maker-name` shares `.sr-only` (`shop.js:22`; `style.css:27`).
3. **Review the unmatched style groups only if there is a cleanup goal.** `style.css:1,3` contain basket/box and owner-chat names with no scoped reference; `hiking.css:24–27,80` contains `.trail-map`, while the renderer uses the separately styled `.trail-photograph` and `.trail-map-unavailable` (`community.js:31,49`; `trail-explorer.css:2–5`; `hiking.css:94,96`). These are candidates for review, not a deletion recommendation.

**Buildable unit: none recommended from this scan alone.** No styling defect or safe removal was established by the static checks. No site, generator, browser, tests against live inputs, or owner decision was exercised; no stylesheet, page or script was changed.
