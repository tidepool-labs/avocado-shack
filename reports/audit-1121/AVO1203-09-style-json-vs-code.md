# AVO1203-09 — Style JSON, checker and documentation audit

| Area | Match? | Evidence |
|---|---|---|
| Picture checks | No. The JSON supplies measured statistics, not the documented hard/soft rules or exceptions. | `house-style.json` `/pictures`; `hass/house_style.py:301–351`; `docs/hass/ITEM-STANDARD.md:58–68` |
| Item completeness | Partial. The required sets, ordering and templates are read; the upgrade and optional declarations are not. Completeness is not a save validator. | `hass/itemstd.py:36–59,92–173`; `item-standard.json` `/product_fields`, `/maker_fields` |
| Catalog display | Some values agree independently. CSS and JS do not take their rules from these files. | `storefront-mockup/shop.js:10–11,60–65`; `storefront-mockup/style.css:31,51–56` |
| Design scope checker | Not a style consumer. It checks changed paths, modes and template/page pairs, not picture or item contents. | `hass/design_check.py:24–32,80–93` |

Evidence: `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, checked 2026-11-21. Only the Hass new-product and current storefront code are in scope (`AGENTS.md:3–16`). The item-standard document is explicitly a draft; its companion report describes a historical design and audit, not an approval or current runtime result (`docs/hass/ITEM-STANDARD.md:1–7`; `reports/hass/ITEMSTD-1.md:3–17,96–99`).

## R1. Every JSON key and its reader

Paths below start at the named JSON root. A `{a,b}` group expands to one path per named key; `*` is every array row; `/**` covers the named key and **all** descendants (including dynamic object keys and fields of array rows). For image metrics, the second column explicitly partitions the seven statistic keys (`/min`, `/p05`, `/p25`, `/p50`, `/p75`, `/p95`, `/max`). “Unread” means no rule/diagnostic read found in the traced production code. Whole-file parsing, regeneration and equality are not enforcement: `hass/house_style.py:274–297,448–456` rebuilds and byte-compares the snapshot; `hass/tests/test_newitem.py:51–62` compares the text/record sections and checks counts/examples. JSON lists of strings or pairs have values, not additional object keys.

### `hass/style/house-style.json`: copy and records

| Key path(s) | Reader or `unread` |
|---|---|
| `/{schema,source}` | unread; generated at `hass/house_style.py:278` |
| `/descriptions` | `hass/house_style.py:362`; `hass/newitem.py:348,472`; `hass/skills/item_add.py:729` |
| `/descriptions/chars`, `/descriptions/chars/{min,max}` | `hass/house_style.py:374`; `hass/skills/item_add.py:739–743` (uses unpadded min/max) |
| `/descriptions/chars/{p05,p95}` | `hass/house_style.py:374` (detail); `hass/newitem.py:350` (writer prompt) |
| `/descriptions/chars/{p25,p50,p75}` | unread |
| `/descriptions/sentences`, `/descriptions/sentences/{min,max}` | `hass/house_style.py:375`; `hass/newitem.py:349`; `hass/skills/item_add.py:744–745` |
| `/descriptions/sentences/{p05,p25,p50,p75,p95}` | unread |
| `/descriptions/words_per_sentence`, `/descriptions/words_per_sentence/{min,max}` | `hass/house_style.py:376` |
| `/descriptions/words_per_sentence/{p05,p25,p50,p75,p95}` | unread |
| `/descriptions/{count,limit_chars,hype_words_absent}` | `hass/house_style.py:382,370,366`, respectively |
| `/descriptions/texts_with`, `/descriptions/texts_with/{digits,exclaims,questions,straight_apostrophes}` | `hass/house_style.py:372,378,382` |
| `/descriptions/texts_with/{all_caps_words,colons,curly_apostrophes,dashes,non_bmp,semicolons}` | unread; local metric names at `hass/house_style.py:194–204,380–382` are not these JSON values |
| `/descriptions/examples`, `/descriptions/examples/*/description` | `hass/newitem.py:471–473`: descriptions of the first four sampled rows as a fallback for the optional writer prompt, not validation; remaining sampled descriptions unread in production |
| `/descriptions/examples/*/{category,id,name}` | unread |
| `/descriptions/{common_first_words,common_later_openers,ends_with_period,hype_words_present,maker_named_in_description,sentence_count_histogram,term_hits,words}/**` | unread; writers at `hass/house_style.py:214–237`; serving vocabulary/openers come from product descriptions, not these aggregates (`hass/newitem.py:410–420`) |
| `/makers`, `/makers/chars`, `/makers/chars/{p05,p95}` | `hass/house_style.py:388,407–408` |
| `/makers/chars/{min,p25,p50,p75,max}` | unread |
| `/makers/{common_first_words,common_later_openers,count,ends_with_period,examples,fields,hype_words_absent,hype_words_present,key_equals_name,limits,name_chars,place_chars,place_pattern_fit,places,sentence_count_histogram,sentences,texts_with,url_scheme_https,with_url,words,words_per_sentence}/**` | unread; snapshot writer at `hass/house_style.py:207–222,241–252`; maker checks use content-model constants and their own logic (`:389–409`) |
| `/records/{brand_rule_counts,categories,highest_id_number,id_pattern,key_orders,limits,maker_example,maker_fields,name_chars,name_style,product_example,product_internal_fields,product_optional_public,product_public_fields,products_per_shelf,products_with_maker_key,products_without_maker_key,shelf_labels,store_fields,unknown_producer}/**`, and `/records` | unread; built at `hass/house_style.py:255–271`; `check_product` loads a spec but never indexes it (`:413–434`) |

### `hass/style/house-style.json`: pictures

All metric paths in the lower part of the table are relative to `/pictures/catalog/metrics`; the metric object itself is read wherever its leaves are read. A shared child list applies to each grouped metric independently.

| Key path(s) | Reader or `unread` |
|---|---|
| `/pictures`, `/pictures/catalog`, `/pictures/catalog/metrics` | `hass/house_style.py:323`; `hass/newitem_render.py:312`; `hass/photo_polish.py:384`; `hass/ops/photos.py:125` |
| `/pictures/catalog/{count,examples,formats,modes,naming,sizes,with_exif}/**` | unread in production; produced at `hass/house_style.py:153–179`; test-only count/example-size reads at `hass/tests/test_newitem.py:57–60` |
| `/pictures/frame/**` | unread; generated at `hass/house_style.py:280–286` (includes `alt_text` with `catalog_illustration` and `owner_photo`, `aspect`, `format_catalog`, `format_owner_photo`, `height`, `look`, `page_box`, `width`) |
| `/{bg_r,bg_g,bg_b}` | `min,max`: `hass/house_style.py:335`; `p50`: `hass/newitem_render.py:313`; `p05,p25,p75,p95`: unread |
| `/bg_spread` | `p95`: `hass/house_style.py:336`; `min,p05,p25,p50,p75,max`: unread |
| `/frame_clean` | `min`: `hass/house_style.py:337–338`; `p05,p25,p50,p75,p95,max`: unread |
| `/{holes,hole_area}` | `max`: `hass/house_style.py:339–340`; `min,p05,p25,p50,p75,p95`: unread |
| `/fill_max` | `p05,p95`: `hass/house_style.py:313–317,341`; `p50`: `hass/newitem_render.py:343`, `hass/photo_polish.py:397`; `min,p25,p75,max`: unread |
| `/area_ratio` | `min,max`: `hass/house_style.py:342`; `p05,p25,p50,p75,p95`: unread |
| `/center_x` | `p95`: `hass/house_style.py:343`; `min,p05,p25,p50,p75,max`: unread |
| `/{center_y,shadow_depth,subject_sat}` | `p05,p95`: `hass/house_style.py:313–317,344,346–349`; `min,p25,p50,p75,max`: unread |
| `/margin_bottom` | `p05`: `hass/house_style.py:345`; `min,p25,p50,p75,p95,max`: unread |
| `/subject_luma` | `p05,p95`: `hass/house_style.py:313–317,348`, `hass/newitem_render.py:356–359`; `min`: `hass/ops/photos.py:125` (advice); `p25,p50,p75,max`: unread |
| `/bytes` | `p95`: `hass/house_style.py:350`, `hass/newitem_render.py:376`, `hass/photo_polish.py:406`; `min,p05,p25,p50,p75,max`: unread |
| `/{bg_luma,corner_vs_edge,fill_h,fill_w,margin_left,margin_right,margin_top}/**` | unread; produced at `hass/house_style.py:170–174` |

### `hass/style/item-standard.json`

| Key path(s) | Reader or `unread` |
|---|---|
| `/{about,schemaVersion}` | unread; settings load at `hass/itemstd.py:32–48` has no schema-version check. `:206–219` checks the separate catalog-input schema, not this file. |
| `/codes` | `hass/itemstd.py:37,92–97,233,249,261–262`; `scripts/hass/itemstd_gap_diff.py:58` |
| `/product_fields`, `/product_fields/required` | `hass/itemstd.py:38,92–97,156,261–266`; required only affects the result **after** code has detected missing fields |
| `/product_fields/upgrade` | unread; `own_photo` is coded directly at `hass/itemstd.py:143–147,246` |
| `/maker_fields`, `/maker_fields/required` | `hass/itemstd.py:39,92–97,173,262–270`; same distinction |
| `/maker_fields/optional` | unread; `website` is coded directly at `hass/itemstd.py:170–173,271` |
| `/ask_order` | `hass/itemstd.py:40,92–97,156,244`; `scripts/hass/itemstd_gap_diff.py:58` |
| `/maker_ask_order` | `hass/itemstd.py:41,92–97,172–173`; all questions on this path use the town formatter even if another code is put into the order |
| `/shelves` | `hass/itemstd.py:42,114–115,222–235` |
| `/{fresh_shelves,packaged_ids}` | `hass/itemstd.py:43–44,149,152–153` (producer question choice) |
| `/{unknown_producer_labels,own_brand_labels}` | `hass/itemstd.py:55–56,127–135` (brand fallback when maker not resolved) |
| `/own_photo_pattern` | `hass/itemstd.py:47,143–147` |
| `/display_limits`, `/display_limits/{name_max,description_max}` | `hass/itemstd.py:46,112,139` (display notes) |
| `/region`, `/region/{names,prefixes,suffixes}` | `hass/itemstd.py:48,57–59,67–89`; indirectly called by maker skill at `hass/skills/makers.py:147–153` |
| `/questions`, `/questions/{name,shelf}` | `hass/itemstd.py:45,110–115,151–156`; generic `QUESTIONS[code]` when first missing askable field is name or shelf |
| `/questions/{producer_fresh,producer_packaged}` | `hass/itemstd.py:45,149,151–153` |
| `/questions/{producer_town,producer_town_no_label}` | `hass/itemstd.py:45,100–101,154,173` |

## R2. Rules in code, not in the style JSON

| Surface | Quoted rule and what the JSON does not control |
|---|---|
| Score and measurement | `"pass": not hard and score >= 80`, `_c(..., weight=1, hard=False)` (`hass/house_style.py:301–310`): neither weights nor pass threshold are JSON. `WORK = 160`, `RING, SUBJECT_DELTA, MIN_LINE = 6, 30, 3`, `MIN_PATCH = 12` and `band = round(WORK * .08)` define measurement, not entries in the snapshot (`:34–35,75–98,101–142`). |
| Picture hard checks | `== (800, 800)`, `== "RGB"`, `fmt in ("WEBP", "JPEG", "PNG")`, `not m["has_exif"]` and `"subject visible"` (`hass/house_style.py:327–332`); frame prose and historical counts do not drive these comparisons. Code checks EXIF and RGB mode, not a general ICC/XMP metadata rule (`:105–106,327–330`). Per-channel `min - 6` to `max + 6`, frame `min * .97` and background holes `max + 6` and `max * 1.5` are hard; the numbers in JSON are observations used in those formulas, not policy constants (`:333–340`). |
| Picture soft checks | `p95 * 1.5 + 1` for evenness; `scale=.25` and `<= 1.0` for longest side; area `min * .85` to `max * 1.1`; sideways `p95 + .04`; vertical `slack=.04`; bottom `p05 * .5`; shadow `is not None` and `slack=3, scale=.5`; brightness and colour `scale=.25`; bytes `p95 * 1.6` (`hass/house_style.py:313–317,336–350`). These are code-selected statistics, slack and weights, not configurable hard/soft classes. |
| Picture output and callers | `SIZE = 800`, `JPEG_QUALITIES = (90, 85, 80, 74)`, `MAX_UPSCALE = 2.5`, `NOISY = 12`, `STRAIGHTEN = (3.0, 20.0, 1.4)` and the `SHADOW` recipe (`hass/newitem_render.py:29–31,48–54,231–239`). Output uses `min(..., .90)`, exposure gain `.8`–`1.25`, placement `.006/.03/.045` and JPEG retry `p95 * 1.3` (`:326–376`; also `hass/photo_polish.py:387–408` for its independent frame). Input guard and cutout algorithm have their own thresholds (`hass/newitem_render.py:110–125,140–209,212–228,242–261,282–296`); none is a JSON style rule. Photos install adds retake checks (`hass/ops/photos.py:105–133`); polish allows the single `"no photo background left inside the product (patterned cloth, planks)"` hard-failure label on its own path (`hass/photo_polish.py:83–84,350–351`), not a catalog exception by ID. |
| Description scoring | `FORBIDDEN_TEXT` and the claim term lists/affirmation check are sourced from code, not `/term_hits`; `text == text.strip()`, `min * .9`, `max * 1.25`, words-per-sentence `min * .8` to `max * 1.3`, `not m["non_bmp"] and not m["all_caps_words"]`, full stop and straight apostrophe tolerance `0.3 * d["count"]` are code rules (`hass/house_style.py:358–383`; `hass/content_model.py:107`). Counts gate the no-digit and no-`!`/`?` checks; the latter and hype are soft here. The item-add path treats selected failures as reasons for refusal and uses the exact measured length bounds (`hass/skills/item_add.py:725–751,871–873`). Writer prompt and allowed source sentences are separately coded (`hass/newitem.py:346–355,443–479`); measurements do not decide claim truth. |
| House maker/product records | Maker `{"name", "place", "story"} <= set(rec)`, optional URL via `_https`, literal `80/60/600`, soft place regex (also accepts two named region forms), `key == rec.get("name")`, story `p05 * .35` to `p95 * 1.25` and trailing period (`hass/house_style.py:41,386–410`). Product `need <= set(rec) <= allowed`, `category in CATEGORIES`, `photo-product-\d{3,}`, fallback brand/display pairing, maker-link validity and `CATALOG_IMAGE_RE`/`OWNER_IMAGE_RE` path matching are code (`:36–37,413–434`; `hass/content_model.py:28–48,91–107,182–200`). The apparent “nine” in the check label does not constrain the imported ten-key enum. |
| Item missing/notes predicates | `if status == "held": return None`; `() if status == "hidden" else ASK_ORDER`; same suppression for a truthy maker `hidden` (`hass/itemstd.py:104–107,156,172–173`). Hard-coded field detection, not a generic JSON rule engine: `if not name`, `any(ch.isdigit() ...)`, `kind != "town"`, maker-key lookup plus named-brand fallback, `"!" in desc or "?" in desc`, `not desc.endswith(".")`, image blank vs owner-path match, blank `imageAlt`, blank maker `story`/`url` (`:109–149,159–173`). Display notes do not feed `complete`; only known missing codes intersecting the required set do (`:92–97`). Region regex is not a geocoder: code folds apostrophes/case/whitespace, handles possessives and requires two comma-separated letter-bearing parts with an allowed character set (`:51–59,67–89`). |
| Storefront and scope | `PRODUCE_SHELVES` and `PACKAGED_IDS` are independently hard-coded in `storefront-mockup/shop.js:64–65`; `installedImage` and the `" (illustration)"` suffix at `:10–11` are independent of both JSON files. `hass/design_check.py:24–32,89–93` hard-codes `DESIGN`, `PAIRS` and `PLAIN_MODE = "100644"` for visual diff scope, not for semantic enforcement. |

## R3. `ITEM-STANDARD.md` versus the JSON

| Draft wording | JSON and current implementation |
|---|---|
| “That one file is the only place the list lives” under `grandfathered`, with three exceptions and a catalog CI contract (`docs/hass/ITEM-STANDARD.md:64–68`) | No `/grandfathered`, nor separate hard/soft rule objects in `house-style.json` (root keys in R1); image check accepts bytes and spec, not a product ID (`hass/house_style.py:320–351`). The proposed envelope lives separately as historical script rules and report output (`reports/hass/itemstd-1/check_envelope.py.txt:19–50`; `reports/hass/ITEMSTD-1.md:16,26–29,79–80,96–99`). This is not evidence of an active exception or permission to change one. |
| “at most 160 KB; background within 28 levels of #fef8ec; clean frame at least 90%” and “no EXIF, colour profile or alpha” (`docs/hass/ITEM-STANDARD.md:41–46,62`) | `/pictures/catalog/metrics/{bytes,bg_r,bg_g,bg_b,frame_clean}` give distributions, not those cutoffs. `bytes/p95` is `99306` (used with a soft `* 1.6`); `frame_clean/min` is `0.8352` (used with hard `* .97`). Background is a three-channel envelope with padding, not distance from a fixed point; `with_exif` is a count, not ICC/alpha policy. Frame width/height are 800 in JSON and checker independently. See `hass/house_style.py:105–106,327–350`. |
| “Soft (advice only: a plain retake tip ... never a refusal)”; “shadow at most 7.5 levels”; “subject at least 80% ... 112 px phone thumbnail” (`docs/hass/ITEM-STANDARD.md:52,63,86`) | `/pictures/catalog/metrics` has measurements, not limits for the documented background 17, variation 6, longest side 79–97%, centre 4%/10%, bottom 2.5%, area 20–60% or shadow 7.5; no thumbnail key. Code uses the R2 formulas and counts soft losses toward `score >= 80`; there is no separate thumbnail check, and a missing shadow metric loses points (`hass/house_style.py:301–306,333–351`). |
| “desktop and tablet: a **4:3 box**” versus phone “**112 x 112 px square thumbnail**” (`docs/hass/ITEM-STANDARD.md:56,84`) | `/pictures/frame/page_box` says “square (aspect-ratio 1)” with no breakpoint. The current catalog-specific CSS agrees with the docs, not that JSON note (`storefront-mockup/style.css:31,51–56`). The stored image's square dimensions are not the displayed box. |
| “a new owner photo is saved as JPEG” and “OPTIONAL for stock pictures; REQUIRED for ... own photos” (`docs/hass/ITEM-STANDARD.md:23,42,54–55`) | `/pictures/frame/format_owner_photo` and `/own_photo_pattern` recognize both `.jpg` and `.png`; that recognition is wider than the documented JPEG output, not evidence that the renderer writes PNG (`hass/newitem_render.py:370–380`). `/pictures/frame/alt_text/owner_photo` adds “3..200 chars, not a file name”; the completeness checker only adds `alt_is_default` for blank owner-photo alt, and the page falls back to name and adds a suffix only for non-owner paths (`hass/itemstd.py:143–147`; `storefront-mockup/shop.js:10–11`). |
| “Picture ... REQUIRED” and “file must exist”; producer town “REQUIRED when a maker is named” (`docs/hass/ITEM-STANDARD.md:20,22`) | `/product_fields/required` includes town unconditionally, no `image` or `imageAlt`; `/product_fields/upgrade` has only `own_photo`. Code flags `picture_missing` without checking the filesystem or affecting `complete`; without a resolved maker it always adds `producer_town`, even for an unknown producer (`hass/itemstd.py:127–156`). This does not describe every editor save rule. |
| “one of 9”, “fresh = Fruit, Vegetables, Flowers”, “one hard-coded exception” (`docs/hass/ITEM-STANDARD.md:17–18`) | `/shelves` agrees with the nine documented and `/fresh_shelves` plus `/packaged_ids` agree with the current storefront values (`storefront-mockup/shop.js:64–65`). `/records/{categories,shelf_labels}` and `hass/content_model.py:28–31` include `general` as a tenth; `itemstd` flags it missing (`:114–115`). The separate intake classifier includes `eggs` in `FRESH_SHELVES` (`hass/skills/item_add.py:73,371`); do not assume the draft’s storefront meaning governs that classifier. |
| “at most 80 characters, no sizes or digits”; “2 or 3 short sentences, 59 to 167 characters measured, limit 600”; “ends with a full stop, no digit, `!`, `?`, price, size or hype word” (`docs/hass/ITEM-STANDARD.md:16,21`) | `/display_limits` gives only `80/600`; `/descriptions/{chars,sentences,limit_chars}` match the cited observations and ceiling; `/descriptions/hype_words_absent` is a corpus-derived list, not an exhaustive ban (e.g. `/descriptions/hype_words_present` contains `best`). Item completeness notes a subset and does not enforce sentence count, hype, size or price; style scorer and item-add pick different checks (R2). |
| “239 to 297 characters measured, limit 600” and “Public https only; never asked” (`docs/hass/ITEM-STANDARD.md:28–30`) | `/makers/chars/{min,max}` and `/makers/limits/story` agree; `/maker_fields/optional` lists website, but no URL scheme rule in item JSON. `/makers/url_scheme_https` is a count. `itemstd` checks merely blank/present and asks only town; `house_style` uses `_https` independently (`hass/itemstd.py:159–173`; `hass/house_style.py:397–408`). |
| “a doubtful one is asked as yes/no”; “Which state is ...?”, “Could you send me a photo ...?”, “Same farm as last time ...?” (`docs/hass/ITEM-STANDARD.md:17,93,169,316–326`) | `/questions/shelf` is “Which shelf should it go on?”; `/ask_order` agrees with the four-field order in §3 and `/maker_ask_order` asks town only. The extra follow-up templates and state code are not in `/questions` or `/codes`. §4 also covers workflow beyond the pure checker; absence does not say those skills lack separate wording, nor justify changes to transport, approvals, caps or timers. |
| “Status ... active / hidden / held”, optional availability and new badge, “Organic” derived (`docs/hass/ITEM-STANDARD.md:24–27`) | `/records/product_internal_fields` and `/records/product_optional_public` list some names only; no status enum, badge rule or timing model in either style JSON. The checker skips held products in code and suppresses questions about hidden ones (`hass/itemstd.py:104–107,156`); the catalogue’s separate badge implementation is identified by `reports/hass/ITEMSTD-1.md:57–58`. These are scope differences, not requests to change status or claims. |

## R4. Ranked gaps and one proposed unit

1. **Picture acceptance is materially different from the draft.** A picture can pass with a documented hard failure, while accumulating soft failures can make the actual score fail. The named catalog exceptions are not enforced by this JSON or checker (`docs/hass/ITEM-STANDARD.md:62–68`; `hass/house_style.py:301–351`).
2. **Completeness can be mistaken for save readiness.** A blank image path, a non-HTTPS website and the distinction between location format and actual place show the limits; upgrade/optional names are coded rather than read (`hass/itemstd.py:81–97,143–173`; `/product_fields/upgrade`, `/maker_fields/optional`).
3. **Separate shelf definitions can yield different results.** A valid `general` key in the catalog model is a missing shelf to the completeness checker. The intake classifier also defines fresh differently (`hass/content_model.py:28–31`; `hass/itemstd.py:114–115`; `hass/skills/item_add.py:73,371`).
4. **The snapshot looks more authoritative than it is.** Its page-box prose is stale, and most recorded facts (including `/records` and `/pictures/frame`) are not enforcement knobs (R1; `storefront-mockup/style.css:31,51–56`).

**One follow-up, not implemented (estimate: 60–90 minutes):** In a separately scoped documentation-only unit, edit only `docs/hass/ITEM-STANDARD.md` §2.1 to label the proposed envelope and historical exceptions separately from the current executable checker. Link the exact checker and JSON sections, without adopting or retiring any rule or exception. Offline acceptance: `git diff --name-only` lists only that doc; `git diff --check` exits 0; read the revised section against `git show HEAD:hass/house_style.py` and `git show HEAD:hass/style/house-style.json` and verify it no longer states that main reads `/grandfathered` or that the 160 KB threshold and 90% clean-frame value are enforced hard rules. Keep the draft thresholds intact and explicitly marked as proposals. No checker, data, page, photo, approval or operational change is required for this unit.

### Replay and limits

From the audited checkout: `git rev-parse origin/main`; `git diff --name-status 37feae1dc5efa6968f90d17a1eda6daed29afd4a origin/main -- hass/style hass/house_style.py hass/itemstd.py hass/design_check.py docs/hass/ITEM-STANDARD.md reports/hass/ITEMSTD-1.md` (empty). Enumerate the JSON object paths with `jq -r 'paths | select(.[-1] | type == "string") | map(tostring) | join("/")' hass/style/house-style.json` and the same command for `hass/style/item-standard.json`. Trace the loads with `git grep -nE 'house-style\.json|item-standard\.json|load_spec|SETTINGS\[' -- '*.py' '*.js' '*.cjs'`; use `nl -ba` on the cited files for caller and leaf reads. The path census is about checked-in readers, not external consumers.

Offline scratch checks, 2026-11-21, exit 0: normalizing array indices to `*` and expanding the R1 groups accounted for 506 distinct house-style object-key paths and 31 item-standard paths, with no omitted or overlapping paths. The behavioral probe printed `synthetic missing image: True ['own_photo'] ['picture_missing']`; a synthetic maker with non-HTTPS URL returned complete, and `general` was marked a missing shelf. Substituting valid dimensions/RGB/EXIF status and median metrics except an 88% clean frame into the actual image checker with 165,000 synthetic bytes returned `[] 97 True` (hard failures, score, pass); its file-size check was false and soft. This tests the scoring branch, not decoding real pixels. No browser, installed runtime, real configuration, network service, prompt/model or live state was exercised for this audit. Historical picture/layout counts were read, not remeasured.
