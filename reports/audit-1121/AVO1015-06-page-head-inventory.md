# AVO1015-06 — Static page head inventory

| Page | Title | Description | Lang / viewport | Canonical | Robots | Open Graph / Twitter | Linked styles / file scripts (found / referenced) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/` | Unique | Present | Both present | Absent | Absent | Both absent | 1/1 · 5/5 |
| `/about/` | Shared placeholder | Absent | Both present | Absent | `noindex` | Both absent | 1/1 · 1/1 |
| `/faq/` | Shared placeholder | Absent | Both present | Absent | `noindex` | Both absent | 1/1 · 1/1 |
| `/getting-here/` | Shared placeholder | Absent | Both present | Absent | `noindex` | Both absent | 1/1 · 1/1 |
| `/hike/` | Unique | Present | Both present | Absent | Absent | Both absent | 3/3 · 3/3 |
| `/policies/` | Shared placeholder | Absent | Both present | Absent | `noindex` | Both absent | 1/1 · 1/1 |

**Scope.** The table summarizes R1 at starting `origin/main` `37feae1dc5efa6968f90d17a1eda6daed29afd4a`. The six checked-in pages, their site generator/templates and the two named QA scripts are unchanged from `1f8510907cb2989bb50391fde45d6211e4735879` (see commands below). This is a source inventory, not a live-site check. The four info pages in the tree are hidden-state placeholders; the publisher only emits an info route when its `shown` flag is set (`hass/sitegen.py:346–354,377–384,502–514`). No live settings or published artifact were inspected. The generated 404 is outside the six-page inventory but matters to R3 (`hass/sitegen.py:469–471,516–517`).

## R1. Exact values and file targets

`—` means no tag of that kind. Source paths in both tables are relative to `storefront-mockup/`. The source column spans the opening `<html>` and the full head, including the lines used to check absences.

| Page source | `<title>` | Meta description | `<html lang>` | Viewport content | Canonical | Robots content | Open Graph (`og:*`) | Twitter (`twitter:*`) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `index.html:2–9` | Avocado Shack · Good food, close to home. | Explore the food and people behind Avocado Shack in Morro Bay. Seasonal produce, local growers, small producers, and good things for your table. | `en` | `width=device-width,initial-scale=1` | — | — | — | — |
| `about/index.html:2–8` | Nothing here yet · Avocado Shack | — | `en` | `width=device-width,initial-scale=1` | — | `noindex` | — | — |
| `faq/index.html:2–8` | Nothing here yet · Avocado Shack | — | `en` | `width=device-width,initial-scale=1` | — | `noindex` | — | — |
| `getting-here/index.html:2–8` | Nothing here yet · Avocado Shack | — | `en` | `width=device-width,initial-scale=1` | — | `noindex` | — | — |
| `hike/index.html:2–10` | North Coast Hiking Club · Avocado Shack | Walk the Central Coast with Michael Wolfe and the North Coast Hiking Club. Explore the next hike, trail maps, elevation profiles and community outings. | `en` | `width=device-width,initial-scale=1` | — | — | — | — |
| `policies/index.html:2–8` | Nothing here yet · Avocado Shack | — | `en` | `width=device-width,initial-scale=1` | — | `noindex` | — | — |

All URLs below are as written and in source order within each column. **Yes** means the target resolves to a tracked file under `storefront-mockup/`, treating that directory as the site root; it does not mean a deployed URL was fetched. Scripts in the rightmost column are all in the body, not the head.

| Page | Head: `<link rel="stylesheet">` targets | Head: `<script>` | Body: `<script>` targets |
| --- | --- | --- | --- |
| `/` | `style.css` — yes (`index.html:7`) | Inline `application/ld+json` (`GroceryStore`); no `src`, so file N/A (`index.html:8`). Not a social tag. | `catalog-products.js` — yes; `producers.js` — yes; `script.js` — yes; `shop.js` — yes; `community.js` — yes (`index.html:32`) |
| `/about/` | `/style.css` — yes (`about/index.html:7`) | None (`about/index.html:3–8`) | `/script.js` — yes (`about/index.html:19`) |
| `/faq/` | `/style.css` — yes (`faq/index.html:7`) | None (`faq/index.html:3–8`) | `/script.js` — yes (`faq/index.html:19`) |
| `/getting-here/` | `/style.css` — yes (`getting-here/index.html:7`) | None (`getting-here/index.html:3–8`) | `/script.js` — yes (`getting-here/index.html:19`) |
| `/hike/` | `/style.css` — yes; `/hiking.css` — yes; `/trail-explorer.css` — yes (`hike/index.html:7–9`) | None (`hike/index.html:3–10`) | `/script.js` — yes; `/trail-explorer.js` — yes; `/community.js` — yes (`hike/index.html:29`) |
| `/policies/` | `/style.css` — yes (`policies/index.html:7`) | None (`policies/index.html:3–8`) | `/script.js` — yes (`policies/index.html:19`) |

**When rendered for publication.** Home and hike keep the audited title, description, language and viewport in their templates and gain `<meta name="club-service" content="none">` on publish (`hass/templates/index.html:2–9`, `hass/templates/hike/index.html:2–10`, `hass/sitegen.py:487–514`). A shown info page gets its title from content and drops the placeholder's `noindex`; the shared template still has no description, canonical or social tags (`hass/sitegen.py:346–354`, `hass/templates/info/index.html:2–8`). `banner.js` and `notice.js` exist but none of the six checked-in HTML files references them. The generator has conditional body includes: `/banner.js` for home, hike and shown info pages when configured; `/notice.js` and `/specials.js` for home when the corresponding slot emits a script. All three files are tracked and on the publish allowlist (`hass/templates/index.html:20–21`, `hass/templates/hike/index.html:29–30`, `hass/templates/info/index.html:19–20`, `hass/sitegen.py:330–337,377–384,469–473`, `hass/notice.py:13,30,60–65`, `hass/specials.py:24–50`). This does not establish which slots are active on a deployed site.

## R2. Repeats and missing fields, by estimated visibility

| Rank (estimate, most visible first) | Finding and likely surface |
| --- | --- |
| 1 | **Missing Open Graph and Twitter tags on all six.** Most visible for home and hike in shared-link previews; a platform may fall back to other page content. The four placeholders have the same absence, but are not emitted in their hidden state (R1; `hass/sitegen.py:510–512`). |
| 2 | **The same title on About, FAQ, Getting Here and Policies.** Directly visible in tabs if someone opens the checked-in placeholders, but not a duplicate-title finding about the public site: shown pages use content-supplied titles (R1; `hass/sitegen.py:346–354,510–512`). |
| 3 | **No meta description on those same four pages.** Low visibility for hidden placeholders. If shown, the template still has no description, so search engines may choose their own snippets (`hass/templates/info/index.html:2–8`). Home and hike have distinct descriptions; no present description is repeated (R1). |
| 4 | **No canonical link on any of the six.** Not visible in a normal visit; potentially relevant to which URL a crawler selects. This audit did not establish any duplicate-URL indexing problem (R1). |
| 5 | **No robots meta on home or hike.** No direct visitor effect; this is an absent page-level directive, not evidence that either route is indexed or needs a tag. The four placeholders do have `noindex` (R1). |

No missing title, language, viewport or referenced script/style file was found. Every page references at least one stylesheet and one script (R1). The placeholder title and robots behavior are not recommendations to change visibility or wording.

## R3. What QA already pins

| Check | Actual assertion or check | Boundary |
| --- | --- | --- |
| Published 404: robots and CSS (`storefront-mockup/static-site-qa.cjs:19,222–230`) | `assert.equal(await page.locator('head meta[name=robots][content=noindex]').count(),1,missing+': noindex');` and `assert.ok(await page.evaluate(()=>[...document.styleSheets].some(s=>s.cssRules.length>0)),missing+': stylesheet loaded');` | Both apply to missing URLs served with the generated 404, not to the six named page heads. The CSS assertion requires some loaded rules, not a specific href. |
| Published browser checks (`storefront-mockup/static-site-qa.cjs:51–76,84–92,94–109,181–187,283–284`) | `assert.deepEqual(errors,[]);assert.deepEqual(bad,[]);` and `assert.deepEqual(cspViolations,[],'CSP violations on the published pages');` | Indirect coverage: runtime errors, observed HTTP failures (with exceptions at line 55), and CSP violations. The catalog/hike interactions and computed hike heading styles also exercise some script/CSS behavior. The test sets a browser viewport; it does not assert the viewport tag or enumerate required `src`/`href` values. |
| Published no-club-service behavior (`storefront-mockup/static-site-qa.cjs:20,27–28,73–74,232–243`) | `assert.deepEqual(apiAsked,[],route+': asked for an /api path');assert.deepEqual(consoleErrors,[],route+': console errors');`; with the marker removed, `assert.equal(hits,1,route+': one GET /api/community');` | Behavioral coverage of the publish marker, not an inventory of head tags. |
| Catalog-image resource check (`storefront-mockup/resource-qa.cjs:1`) | `if(!r.ok)failed.push({id:p.id,status:r.status});` and `if(failed.length)process.exitCode=1` | Reads image URLs from `shop-data.json` and checks HTTP responses. It does not read HTML or check head fields, script targets or stylesheet targets. |
| Additional current-main info-page check (`scripts/hass/info_pages_check.py:30–35,65–98`; `hass/tests/test_info_pages_check.py:132,139`) | `self.assert_findings(self.invoke(), "shown-noindex 2")` and `self.assert_findings(self.invoke(), "hidden-indexable 4", "footer-hidden-link 1")` | Separately checks rendered info-page visibility against robots `noindex` and checks hidden links. It does not inventory the other metadata or assert a general robots rule for home/hike. |

The named suites do not pin title or description presence/uniqueness, the language or viewport tag, canonical or social metadata, or the exact script/stylesheet include lists for the six pages. Robots coverage is narrower: the published 404 in the static suite and shown/hidden info state in the separate offline check (table above). This is an assertion review, not a test-pass receipt. The browser and resource suites were not run; they drive a local server or make HTTP requests and write QA output (`static-site-qa.cjs:21–30,40–42,286–289` and `resource-qa.cjs:1`, both under `storefront-mockup/`).

## R4. One possible follow-up (not implemented)

**Estimate: 60–90 minutes.** Add one offline test file, `hass/tests/test_static_page_head.py`, using Python's `HTMLParser` to read the six checked-in pages. Assert one nonblank title in the head (not unique, since R2 identifies intentional placeholders), a nonblank root `lang`, one nonblank head viewport declaration, and that each local script `src` and stylesheet `href` resolves to a regular file under `storefront-mockup/`. Allow inline JSON-LD. Give failures the page and field or target; verify with `python3 -m unittest discover -s hass/tests -p test_static_page_head.py` and scratch HTML controls with a deleted viewport tag and a mistyped CSS path. These are credible regressions not directly pinned in R3. Do not set canonical/social/robots policy, require new description copy, edit pages or change CI registration as part of this follow-up.

### Reproduce offline

From the repository root, use the recorded commit (`base` below) rather than a moving branch. The first comparison returned no diff; the two inventory commands reproduce the R1 inputs and the tracked-file check. Compare the literal title and description values for R2, excluding absent descriptions. Read the cited assertions for R3, not only test names.

```sh
base=37feae1dc5efa6968f90d17a1eda6daed29afd4a
git diff --exit-code 1f8510907cb2989bb50391fde45d6211e4735879 "$base" -- AGENTS.md storefront-mockup hass/sitegen.py hass/templates hass/notice.py hass/specials.py reports/audit-1121
git grep -inE '<(html|head|/head|title|meta|link|script|base)([[:space:]]|>)' "$base" -- \
  storefront-mockup/index.html storefront-mockup/about/index.html storefront-mockup/faq/index.html \
  storefront-mockup/getting-here/index.html storefront-mockup/hike/index.html storefront-mockup/policies/index.html
git ls-tree --full-tree -r "$base" -- storefront-mockup/style.css storefront-mockup/hiking.css \
  storefront-mockup/trail-explorer.css storefront-mockup/catalog-products.js storefront-mockup/producers.js \
  storefront-mockup/script.js storefront-mockup/shop.js storefront-mockup/community.js storefront-mockup/trail-explorer.js \
  storefront-mockup/banner.js storefront-mockup/notice.js storefront-mockup/specials.js
git show "$base:storefront-mockup/static-site-qa.cjs" "$base:storefront-mockup/resource-qa.cjs" \
  "$base:scripts/hass/info_pages_check.py" "$base:hass/tests/test_info_pages_check.py"
```
