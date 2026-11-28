# Producer source coverage — offline audit

| Check | Result |
|---|---|
| Producer inventory (R1) | 26 producers, all with a place and a stored `url`. Nine stories make an affirmative organic claim (one of these is historical only); AG Berries mentions an aspiration, not organic status. |
| Dated evidence (R1–R2) | 26 links have a recorded 2026-11-05 check; some checks support only a region, a different kind of location, or the wording without the maker attribution. The public research log has no matching entries or check dates. |
| Missing or report-only links (R2) | No producer lacks a URL altogether or has its only URL in a report. Some **additional, claim-specific** links appear only in reports. A stored URL does not by itself document a claim. |
| Hass comparison (R3) | 26 exact maker-key matches; no name, place or URL differences after JSON decoding. |

Read on 2026-11-21 at `origin/main` `37feae1dc5efa6968f90d17a1eda6daed29afd4a`. All references below are to that tree. No cited URL was opened for this audit; dates describe earlier recorded reads, not current verification. The report does not decide whether a claim is true, whether a badge may be shown, or whether a catalog record should change (`AGENTS.md:11–16`).

## R1. Every producer and its recorded location source

**P** = `storefront-mockup/producers.json`; the line range covers the whole record, including `name`, `place`, `story` and `url`. **M** = `hass/content/makers.json`, under `/makers`; “yes” means an exact key match. **L** = `reports/maker-links-2026-11.md`; the date in each row is the historic link check recorded there. The `url` is a stored Visit link, not a field that binds evidence separately to the place and organic wording (`reports/site-copy-claims-2026-11.md:200`).

**Organic claim** describes the producer `story` only: `yes` = the text asserts something organic, with the subject shown; `no` would mean it explicitly denies organic status (no such rows); `none` means no such assertion, not “not organic.” The data have no separate organic-claim field. Brand names, product copy and product badges do not count (`reports/organic-badges-2026-11.md:9–15`; `reports/site-copy-claims-2026-11.md:213–214`).

For every `none` in the Log column, see `storefront-mockup/producer-research-log.json#/note` and `#/contacts`: the checked-in file identifies itself as a synthetic stand-in. No public matching entry exists to point to. Historical log references quoted by reports (e.g. `reports/product-description-claims-2026-11.md:48,482,567` and `reports/unsourced-products-2026-11.md:103`) are second-hand and are not pointers into the current log. No private original was read.

| Key | Name | Location text | Organic claim | Stored `url` | P lines | Log entry | M key? | Location evidence and checked date |
|---|---|---|---|---|---|---|---|---|
| Etto | Etto | Paso Robles, California | yes — durum wheat | `https://ettopastificio.com/pages/about-us` | 2–7 | none | yes | L:11 · 2026-11-05 · founding town |
| Stepladder | Stepladder | Cambria, California | none | `https://stepladdercreamery.com/pages/farm` | 8–13 | none | yes | L:12 · 2026-11-05 · ranch in hills of Cambria |
| Fair Hills Farm | Fair Hills Farm | San Miguel, California | yes — orchard | `https://www.fairhillsfarmorganic.com/thefarm` | 14–19 | none | yes | L:13 · 2026-11-05 · compatible region only; San Miguel not named |
| Ocean Ranch | Ocean Ranch | Carpinteria, California | yes — ingredients | `https://oceanranchorganics.com/about/` | 20–25 | none | yes | L:14 · 2026-11-05 · company base |
| Linn's | Linn's | Cambria, California | none | `https://www.linnseats.com/our-farm` | 26–31 | none | yes | L:15 · 2026-11-05 · restaurant in Cambria, not the farm town |
| Straus | Straus | Northern California | yes — family farm certified in 1994 | `https://www.strausfamilycreamery.com/about/our-story/` | 32–37 | none | yes | L:16 · 2026-11-05 · Marshall and surrounding counties fit region |
| Cal Poly | Cal Poly | San Luis Obispo, California | none | `https://fsn.calpoly.edu/our-products` | 38–43 | none | yes | L:17 · 2026-11-05 · university department page title |
| Alle-Pia | Alle-Pia | California’s Central Coast | none | `https://www.allepiasalumi.com/flavor-of-italy` | 44–49 | none | yes | L:18 · 2026-11-05 · same production region |
| Joebella / Avocado Shack | Joebella / Avocado Shack | Atascadero, California | yes — coffee beans and café/roastery certification | `https://www.joebellacoffee.com/our-story` | 50–55 | none | yes | L:19 · 2026-11-05 · founders' move; names Joebella, not the Shack; reported Atascadero roasting excerpt at `reports/product-description-claims-2026-11.md:567` |
| Corberosa | Corberosa | California’s Central Coast | none | `https://www.corberosa.com/` | 56–61 | none | yes | L:20 · 2026-11-05 · roasting region |
| Sunshine Olive | Sunshine Olive | Templeton, California | none | `https://sunshineoliveoil.com/` | 62–67 | none | yes | L:21 · 2026-11-05 · page title |
| Big Sur Honey Company | Big Sur Honey Company | Big Sur, California | none | `https://www.bigsurhoneycompany.com/about` | 68–73 | none | yes | L:22 · 2026-11-05 · south coast of Big Sur |
| Massa Organics | Massa Organics | Near Chico, California | yes — rice and almonds | `https://massaorganics.com/get-to-know-us/` | 74–79 | none | yes | L:23 · 2026-11-05 · near Chico |
| Mighty Cap Mushrooms | Mighty Cap Mushrooms | Paso Robles, California | none | `https://mightycapmushrooms.com/pages/about-us` | 80–85 | none | yes | L:24 · 2026-11-05 · farm and store town |
| AG Berries | AG Berries | Arroyo Grande, California | none — story mentions a dream of organic farming | `https://agberryfarm.com/` | 86–91 | none | yes | L:25 · 2026-11-05 · farm town |
| Green Gold | Green Gold | Arroyo Grande, California | yes — listed as certified by CCOF | `https://ccof.org/directory-member/green-gold-organic-farms-llc/` | 92–97 | none | yes | L:26 · 2026-11-05 · certifier directory and maker bio agree at town level |
| Stardust Grove | Stardust Grove | Cambria, California | none | `https://thestardustgrove.com/` | 98–103 | none | yes | L:27 · 2026-11-05 · farm town |
| Taco Works | Taco Works | San Luis Obispo, California | none | `https://www.tacoworks.net/pages/about-us` | 104–109 | none | yes | L:28 · 2026-11-05 · manufacturer town |
| Maple Valley | Maple Valley | Cashton, Wisconsin | yes — maple syrup | `https://www.maplevalleysyrup.coop/about-maple-valley-cooperative/` | 110–115 | none | yes | L:29 · 2026-11-05 · processing plant and offices, not the trees |
| Sierra Nevada | Sierra Nevada | Glenn County, California | none | `https://sierranevadacheese.com/pages/about-us` | 116–121 | none | yes | L:30 · 2026-11-05 · county/Willows address |
| Cayucos | Cayucos | Cayucos, California | none | `https://cayucoshotsauce.com/pages/about-us` | 122–127 | none | yes | L:31 · 2026-11-05 · Central Coast; town only in brand name |
| Brian's | Brian's | Atascadero, California | none | `https://briansartisanbread.com/about` | 128–133 | none | yes | L:32 · 2026-11-05 · separate Contact page, not stored About page; possible staleness noted |
| Jayleaf | Jayleaf | Hollister, California | none | `https://www.jayleaf.com/our-story` | 134–139 | none | yes | L:33 · 2026-11-05 · Contact page and maker social page, not stored story page |
| Sean's | Sean's | San Luis Obispo, California | yes — historical family farm only, not the muesli | `https://mueslimunch.com/pages/about-us` | 140–145 | none | yes | L:34 · 2026-11-05 · processing plant; shipping page also names town |
| Love Beets | Love Beets | Rochester, New York | none | `https://lovebeets.com/our-story/` | 146–151 | none | yes | L:35 · 2026-11-05 · production facility |
| Ava’s | Ava’s | Coachella Valley, California | none | `https://static1.squarespace.com/static/61d88f5cc75725423dd78068/t/6300fad4761f1941541aedaf/1661008598041/Earls_KeittMangosPOS.pdf` | 152–157 | none | yes | L:36 · 2026-11-05 · distributor PDF names valley and mango type but not Ava’s; prior verdict “cannot tell” |

## R2. Missing and report-only citations

- **Producer with a place or organic claim and no URL in any audited file:** none. Every producer already has a `url` in P; the decoded `producers.js` mirror and M carry the same URLs (R1, checks below).
- **Producer whose only URL appears in a report:** none. **Additional URLs outside the data** are listed below. A URL appearing only in a report can be a corroborating source, a product comparison, or just a page that was checked; it is not automatically evidence for the producer story.

| Producer | Additional explicit URLs in the reports, absent from the producer/maker records | Recorded check and role |
|---|---|---|
| Green Gold | `https://www.instagram.com/greengoldorganicfarms/` | L:26 · 2026-11-05 · location and organic wording in bio; the bio’s separate website was not fetched |
| Brian's | `https://briansartisanbread.com/contact` | L:32 · 2026-11-05 · Atascadero address |
| Jayleaf | `https://www.jayleaf.com/contact-us`, `https://www.facebook.com/jayleaf.farms/` | L:33 · 2026-11-05 · Hollister address |
| Sean's | `https://mueslimunch.com/pages/contact-us` | L:34 · 2026-11-05 · shipping address, not farm evidence |
| Straus | `https://www.strausfamilycreamery.com/organic-dairy-products`; under `https://www.strausfamilycreamery.com/product/`: `organic-half-half/`, `organic-heavy-whipping-cream/`, `organic-cream-top-milk/`, `organic-unsalted-european-style-butter/`, `organic-european-yogurt-whole-plain/`, `organic-greek-yogurt-whole-plain/`, `organic-sour-cream/` | `reports/organic-badges-2026-11.md:26–32` · 2026-11-05 · product or family wording with the report's stated limits; not a dated citation for the 1994 farm claim |
| Massa Organics | `https://massaorganics.com/product/organic-brown-rice` | `reports/organic-badges-2026-11.md:33` · 2026-11-05 · product title; no certification statement or almond evidence in that row |
| Ocean Ranch | Under `https://oceanranchorganics.com/product/`: `cranberry-orange-organic-granola`, `oaxacan-chocolate-organic-granola`, `lemon-blueberry-organic-granola`, `turmeric-goji-berry-organic-granola` | `reports/organic-badges-2026-11.md:34–37` · 2026-11-05 · ingredient/page or listing wording, not product certification |
| Love Beets | `https://lovebeets.com/talk-to-us`, `https://lovebeets.com/meet-our-beets/`, `https://lovebeets.com/products/` | L:35 and `reports/organic-badges-2026-11.md:38` · 2026-11-05 · Contact adds no place text; product pages did not establish juice certification |

`reports/unsourced-products-2026-11.md:101–112` also gives report-only URLs for **SLO Cider**, but names it as an uninstalled candidate, not a producer in P. Its check date is not stated there. The worksheet concerns products without a maker record, a different denominator. Named leads without an explicit URL, and an unfetched website mentioned in L:26, are not counted as cited sources.

### Organic wording: what the cited material covers

| Story claim (from P in R1) | Coverage in the audited records |
|---|---|
| Etto — wheat | Location quote only at L:11; no claim-specific citation found for organic wheat. |
| Fair Hills Farm — orchard | L:13 quotes the region, not organic wording; no claim-specific citation found for the orchard's organic status. |
| Ocean Ranch — ingredients | The historical badge report quotes the stored About page on organically grown ingredients and records additional product URLs (`reports/organic-badges-2026-11.md:34–37`, 2026-11-05). Not certification evidence for the granolas. |
| Straus — 1994 farm certification | The story is repeated as secondary context (`reports/product-description-claims-2026-11.md:81–87`, report dated 2026-11-05). Product/family links above do not document the farm’s certification date. |
| Joebella / Avocado Shack — beans and premises | The earlier product-description report quotes organic roasting in Atascadero (`reports/product-description-claims-2026-11.md:562–569`, report dated 2026-11-05; log excerpt date not given). Neither that quotation nor L:19 expressly documents certification of both premises or identifies the Shack’s blend. |
| Massa Organics — rice and almonds | The historical badge report quotes the stored About page on organic rice farming and cites the organic brown-rice page (`reports/organic-badges-2026-11.md:33`, 2026-11-05). That row does not document organic almonds. |
| Green Gold — CCOF listing | L:26 and `reports/organic-badges-2026-11.md:21–25,47` record the stored directory listing with a historical certification date and separate maker bio wording (2026-11-05). The badge report did not accept the directory under its own source rules; no current status check here. |
| Maple Valley — syrup | `reports/product-description-claims-2026-11.md:477–491` quotes an older log result on cooperative-level organic wording (report dated 2026-11-05; log excerpt date not given). L:29 links the stored About page for location, not for the specific syrup grade or certification. |
| Sean's — historical farm | L:34 quotes processing-plant history, not organic wording. `reports/product-description-claims-2026-11.md:493–503` records an inconclusive historical query. No claim-specific citation found for the historical farm; no organic assertion about the finished muesli in P:143. |

These are distinctions in what the files record, not judgments about certification or badges. For example, AG Berries has a historical maker-page certification mention at L:25, but its story makes no certification assertion; Ava’s PDF and Love Beets product links contain organic wording that is not the producer story’s claim (L:36; `reports/organic-badges-2026-11.md:38`).

## R3. Name or location differences

**None.** No differing strings to quote: the `name` and `place` in each P row are identical to M at `/makers/<exact key>/name` and `/makers/<exact key>/place` (escape the slash in `Joebella / Avocado Shack` as `~1` in JSON Pointer). The curly apostrophe in `Ava’s` and `California’s Central Coast` matches after decoding; L’s straight-apostrophe typography is not a data mismatch (P:44–48,56–60,152–156; M:46–50,58–62,154–158; L:18,20,36).

## R4. Ranked gaps

1. **Exact organic wording has weaker citations than location.** Start with the explicit premises and historical certification assertions (Joebella and Straus), then the unsupported or partly supported ingredient/farm wording in R2. Do not use product-badge evidence as a substitute for claim-specific sourcing.
2. **Location attribution is weakest for Ava’s.** The PDF names the valley but not the maker (L:36). Fair Hills Farm and Cayucos have regional wording, and Linn's has a restaurant rather than a farm town (L:13,15,31). Brian's and Jayleaf rely on alternate pages (L:32–33).
3. **Public check history is split across reports.** The log is a stand-in (`/note`); the generic Visit URLs in P and M do not carry per-claim dates or reasons. Keep historical excerpts labeled as such rather than treating them as current log receipts.

**No build unit is needed for this audit.** The table brings together the existing citations and dates. Filling the evidence gaps would require evidence not recorded in the scope read here, not a code or data change justified by this report. Decisions on wording, badges and catalog records stay with the owner.

### Reproduce offline

Run from the repository root with the audited main checked out. The first command returns 26 entries, 26 nonempty places, 26 nonempty URLs, nine asserted organic stories after separating the AG Berries aspiration, and the ten stories with the word “organic.” The next two return `true` (complete decoded P vs M and P vs JS). The log command returns only structural keys to avoid contact fields. The grep prints recorded URL-bearing lines for side-by-side comparison; do not visit the URLs.

```sh
jq '{total:length, place:([.[] | select((.place // "") != "")] | length), url:([.[] | select((.url // "") != "")] | length), asserted:([to_entries[] | select(.key != "AG Berries" and (.value.story | test("\\borganic\\b"; "i")))] | length), mentions:[to_entries[] | select(.value.story | test("\\borganic\\b"; "i")) | .key]}' storefront-mockup/producers.json
jq -e --slurp '.[0] == .[1].makers' storefront-mockup/producers.json hass/content/makers.json
jq -e --rawfile js storefront-mockup/producers.js '. == ($js | sub("^const producers="; "") | sub(";[[:space:]]*$"; "") | fromjson)' storefront-mockup/producers.json
jq '{keys:keys, entry_count:(.contacts | length)}' storefront-mockup/producer-research-log.json
git grep -n -E 'https?://' -- reports/maker-links-2026-11.md reports/organic-badges-2026-11.md reports/unsourced-products-2026-11.md reports/product-description-claims-2026-11.md reports/site-copy-claims-2026-11.md
```
