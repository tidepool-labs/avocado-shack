# AVO1343-04 — Hass site template partial use

| Question | Finding |
| --- | --- |
| What is in the tree? | 14 files: four page templates and ten partials (R1). |
| What is unused, missing, or aliased? | No unused partials, no missing file-backed slots, and no file included under two different slot names. The *same slot names* select different nav/footer files on home versus other pages (R2). |
| What appears where? | Home gets the strip, home nav, ordered sections and home footer links. Hike and the four info routes share the strip and hike nav/footer links. The optional banner follows the strip where enabled. The 404 is standalone (R3). |
| What needs attention? | A small test could catch a deleted include marker that otherwise goes unnoticed; no current missing-file repair was found (R4). |

**Source and scope.** Fresh `origin/main` on 2026-11-21: `37feae1dc5efa6968f90d17a1eda6daed29afd4a` (the specified baseline). Anchors below refer to that tree. `AGENTS.md:3–5,13–17` sets the storefront scope. This is a source audit with a synthetic, in-memory render, not a check of any live or deployed site. The front-end guide describes sections and info pages (`docs/hass/skills/front.md:13–29,54–70`); the copy-claims report lists some template sources (`reports/site-copy-claims-2026-11.md:274–279`) but does not map all includes or their order. This audit does not assess copy, consent, product status, or approval rules.

## R1. Every template and its readers

Paths in the first and last columns are relative to `hass/templates/`. **E** = `hass/editor.py:25–29,40–47` opens the file to hash the revision. **D** = `hass/design_preview.py:38–45,49–59` reads the Git blob from a ref using the allowlist in `hass/design_check.py:24–32`; this is not a page inclusion. The direct generator reads below all use `hass/sitegen.py`.

| Template | Direct readers (besides test fixtures) | Included or reached from another template |
| --- | --- | --- |
| `404.html` | `hass/sitegen.py:471,516–517` (`publish_files` only) | None. A standalone output, not an included fragment. |
| `hike/index.html` | `hass/sitegen.py:51,371–372`; E, D | No include. Route links: `/hike/` in `404.html:12,18,21`; `/hike` in `index.html:16` and `home/{nav,footer,hike-nav,hike-footer}.html:1`. |
| `home/banner.html` | `hass/sitegen.py:323–332` (only with banner data); E | `{{front.bannerHtml}}`: `index.html:12`, `hike/index.html:13`, `info/index.html:11`. Appended by Python after the strip; the strip file does not include it. |
| `home/footer.html` | `hass/sitegen.py:307–317`; E | `{{home.footerLinksHtml}}`: `index.html:18`. |
| `home/hike-footer.html` | `hass/sitegen.py:307–317`; E | `{{home.footerLinksHtml}}`: `hike/index.html:27`, `info/index.html:17`. |
| `home/hike-nav.html` | `hass/sitegen.py:307–317`; E | `{{home.navHtml}}`: `hike/index.html:15`, `info/index.html:12`. |
| `home/market.html` | `hass/sitegen.py:307–316`; E; `scripts/hass/template_compat_chain_check.py:20–38,86–90` via `hass/template_compat.py:12–18` | `{{home.sections}}`: `index.html:17`. Anchor links (`#market` or `/#market`): `index.html:11,16`, `404.html:12,17`, `home/nav.html:1`, `home/hike-nav.html:1`. |
| `home/nav.html` | `hass/sitegen.py:307–317`; E | `{{home.navHtml}}`: `index.html:14`. |
| `home/newsletter.html` | `hass/sitegen.py:307–316`; E | `{{home.sections}}`: `index.html:17`. Anchor links: `404.html:12,21`, `hike/index.html:24`, `home/{nav,footer,hike-nav,hike-footer}.html:1`. |
| `home/our-way.html` | `hass/sitegen.py:307–316`; E | `{{home.sections}}`: `index.html:17`; no incoming section-anchor link in this tree. |
| `home/strip.html` | `hass/sitegen.py:323–329`; E | `{{front.bannerHtml}}`: `index.html:12`, `hike/index.html:13`, `info/index.html:11`. |
| `home/visit.html` | `hass/sitegen.py:307–316`; E | `{{home.sections}}`: `index.html:17`. Anchor links: `404.html:11–12,21`, `home/market.html:8`, `home/{nav,footer,hike-nav,hike-footer}.html:1`, and `home/strip.html:1` through `{{front.visitHref}}` (`hass/sitegen.py:327–329`). |
| `index.html` | `hass/sitegen.py:51,371–372`; E, D | No include. `/` links in `404.html:12`, `hike/index.html:15`, `info/index.html:12`; home section links listed above. |
| `info/index.html` | `hass/sitegen.py:377–378` (one read per info route); E, D | No include or literal filename link. Python adds links to shown routes at the footer button (`hass/sitegen.py:340–343,376,384`); configured banner links can also target those routes (`hass/notice.py:16–23`, `hass/content_model.py:612–614`). |

Links to page routes or section anchors navigate to output; they do not load another template. Likewise, `scripts/hass/publish_sources_check.py:26–34,60–66` checks the existence/type of `404.html`, but does not open its body. `hass/look_guard.py:15–16,38–51` checks diff paths rather than opening template files.

Other callers use the same opener rather than implementing a second include scheme: the generator CLI (`hass/sitegen.py:643–660`), editor (`hass/editor.py:211`), migration check (`hass/migration_check.py:139`), staleness check (`hass/notice.py:81–86,109`), new-item preview (`hass/newitem_preview.py:91`), fixture kit (`hass/skills/testkit.py:407,482`), and the in-memory checks in `scripts/hass/`: `info_pages_check.py:61`, `rendered_a11y_check.py:120`, `rendered_anchor_check.py:73`, `rendered_jsonld_check.py:92`, `rendered_link_check.py:127`. The publisher builder (`hass/publish_live.py:231`) and storefront contrast fixture (`storefront-mockup/site-contrast-qa.py:47–57`) call `publish_files`; they also reach the 404 reader. Test-only consumers can copy the entire input tree (`hass/tests/test_content.py:39–45`) or inspect individual files, e.g. `test_publish_404.py:16,66`, `test_rendered_jsonld_check.py:70`, `test_signup_options_doc.py:85–86,219`, `test_catalog_clear_filters.py:18–19`, `test_shelf_labels.py:31–34` and `test_template_compat_chain_check.py:18,36` under `hass/tests/`. These are not additional page includes.

## R2. Unused files, missing includes, and names

- **Unused partial filenames:** none. Compare the tracked inventory to the four section IDs (`hass/content_model.py:611–630`), the two nav/footer pairs (`hass/sitegen.py:307–317`), and the strip/banner pair (`hass/sitegen.py:323–337`). `banner.html` is conditional, not orphaned; the default render need not open it. There is no template-to-template include directive or literal partial-filename include in the tree (see searches below).
- **File-backed markers with no matching file:** none. The four exact markers are `{{home.sections}}`, `{{home.navHtml}}`, `{{home.footerLinksHtml}}`, `{{front.bannerHtml}}`. The names are keys into the builders, not basenames. `{{home.sections}}` aggregates sections; `{{front.bannerHtml}}` aggregates strip and optional banner. `{{home.navHtml}}` maps to `nav.html` or `hike-nav.html`; `{{home.footerLinksHtml}}` maps to `footer.html` or `hike-footer.html`. No individual file is resolved through two different include keys (`hass/sitegen.py:303–337,371–384`).
- **Markers with no file by design (quoted):** `{{store.addressLine}}`, `{{store.addressShort}}`, `{{store.hoursHtml}}`, `{{store.hoursStatusHtml}}`, `{{store.phoneHtml}}`, `{{store.jsonLd}}`, `{{store.mapsUrl}}`, `{{store.introHtml}}`, `{{store.headlineHtml}}`, `{{store.storyHtml}}`, `{{store.heroImageHtml}}` are store values (`hass/sitegen.py:262–280`). `{{store.noticeHtml}}` and `{{store.noticeScript}}` come from `hass/notice.py:56–65`; `{{specials.html}}` and `{{specials.script}}` from `hass/specials.py:41–50`; `{{selection.checkedNote}}` and `{{club.introHtml}}` from `hass/sitegen.py:161–169,368–370`. `{{info.robots}}`, `{{info.title}}`, `{{info.wordsHtml}}` are generated by `hass/sitegen.py:346–354`. `{{front.stripAttrs}}`, `{{front.visitHref}}`, `{{front.bannerHidden}}`, `{{front.start}}`, `{{front.end}}`, `{{front.text}}`, `{{front.linkHtml}}`, `{{front.bannerScript}}` are Python values (`hass/sitegen.py:320–337`; the script tag is supplied by `hass/notice.py`). None is a broken include. Unknown or still-unexpanded markers are errors in the final slot pass (`hass/sitegen.py:52,290–297`).

## R3. Page-by-page order

Names below omit `home/` and `.html`. The file-read order and the order in the resulting HTML differ: Python fills `home.*` before building `front.bannerHtml`, but the banner marker occurs earlier in each shell (`hass/sitegen.py:303–337,371–384`; shell markers in R1). Brackets mean conditional. These are default section positions; the four home sections follow the saved order of the shown rows when provided. `market` and `visit` cannot be hidden in validated content (`hass/content_model.py:611–630`).

| Output, in page build order | Partial reads after opening the shell | Partial order in HTML |
| --- | --- | --- |
| `index.html` | market → our-way → visit → newsletter → nav → footer → strip → [banner] | strip → [banner] → nav → market → our-way → visit → newsletter → footer |
| `hike/index.html` | hike-nav → hike-footer → strip → [banner] | strip → [banner] → hike-nav → hike-footer |
| `about/index.html` | hike-nav → hike-footer → strip → [banner] | strip → [banner] → hike-nav → hike-footer |
| `getting-here/index.html` | hike-nav → hike-footer → strip → [banner] | strip → [banner] → hike-nav → hike-footer |
| `policies/index.html` | hike-nav → hike-footer → strip → [banner] | strip → [banner] → hike-nav → hike-footer |
| `faq/index.html` | hike-nav → hike-footer → strip → [banner] | strip → [banner] → hike-nav → hike-footer |
| `404.html` (publish only) | None | None |

| | Home | Hike |
| --- | --- | --- |
| Nav | `nav.html` | `hike-nav.html` |
| Footer | `footer.html` | `hike-footer.html` |

Info route names/order come from `hass/content_model.py:657–658`. The four shells are rendered even when hidden (default sections for link filtering, no banner and no generated info-route footer links on those placeholders); only shown info pages join the publish set (`hass/sitegen.py:340–354,377–384,508–517`). Home, hike and shown info pages get both strip and banner whenever banner data is present, even outside the dates: those dates determine which line is hidden, not whether the banner file is read (`hass/sitegen.py:325–337`). Hike and info read no home body sections; their nav/footer fragments can link back to them. The 404 has its own inline strip/nav/footer (`hass/templates/404.html:11–12,21`), with no partial or data pass beyond the empty-slot check (`hass/sitegen.py:516–517`).

## R4. Ranked gaps

1. **A deleted marker can drop a partial without a slot error.** Inserting a `home.*` value uses `str.replace` without checking for an occurrence; the final pass checks unknown/unexpanded markers, not absent ones (`hass/sitegen.py:290–297,373–376,381–384`). All expected markers exist today (R1). A separate **test-only** unit (estimate: 60 minutes) could extend `hass/tests/test_front.py` to require each expected file-backed marker exactly once in each shell, with a copy in memory that drops one home nav marker as the negative control; check offline with `python3 -B -m unittest hass.tests.test_front`. Not implemented here.
2. **404 markup is maintained separately.** Its inline strip/nav/footer do not pick up partial changes or section link filtering; the fixed 404 is intentional per `docs/hass/skills/front.md:25–29,67–70` and `hass/sitegen.py:470–471,516–517`. This is a drift risk, not an unused or missing include; no consolidation proposed.

### Checks and limits

Reproduce the static inventory from the pinned checkout (read-only; matcher outputs can include ordinary markup and code references):

```sh
git rev-parse origin/main
git ls-tree -r --name-only origin/main -- hass/templates
git grep -noE '\{\{[^}]+\}\}|<!--[^>]*-->|href="[^" ]+"' origin/main -- hass/templates
git grep -niE 'include|extends|\.html' origin/main -- hass/templates
git grep -nE 'hass/templates|"hass" / "templates"|front_parts\(|front_banner\(|sitegen\.(render|publish_files)|PUBLISH_PAGES|HOME_SECTIONS|INFO_PAGES' origin/main -- hass scripts/hass 'storefront-mockup/*.py' docs/hass
```

**Offline replay, 2026-11-21:** Ran the unchanged Python renderer with an empty synthetic catalog, synthetic store, and fixed date. Wrapped `Path.read_bytes`/`read_text` to record template reads and prefix each partial with a uniquely named HTML comment in memory. The default run rendered six pages with no `banner`; the all-shown publish-file run opened all 14 template paths and returned seven pages, with `strip banner nav market our-way visit newsletter footer` on home, `strip banner hike-nav hike-footer` on hike and all four info pages, and no partial marker on 404. The future-banner run still read `banner` for home and hike but not hidden info pages. Reordering the home sections and hiding the newsletter produced `strip nav visit our-way market footer`. No unresolved braces remained in any tested HTML output. Deleting `{{home.navHtml}}` from the in-memory home shell still read `home/nav.html` but produced no nav fragment and no render error. No generated files were written, and no server, real configuration, runtime data, or live service was used. These inputs verify the source paths and order, not any currently deployed settings.
