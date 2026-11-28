# AVO1015-07 — Shopping words in the catalog source

| Area | Finding at the audited main |
|---|---|
| Scope | `AGENTS.md:3–8` names `storefront-mockup/` as current and says “no prices, basket, boxes, merch or checkout.” `storefront-mockup/README.md:7` places the former interface in the archive. |
| Visitor copy | One distinct visible phrase: “produce buyer’s curiosity” in the home Visit story (`storefront-mockup/index.html:27`; source `hass/content_model.py:82`). It describes a person, not something a visitor can do online. |
| Price capability vs. current data | A product card can display a read-only amount, but no checked-in catalog record supplies the field. The QA helper explicitly masks the exact matching amount when one is shown. That capability and the written “no prices” scope differ; this report does not decide which should change (`shop.js:19–22`, `qa-env.cjs:40–53`, R1/R3). |
| Historical material | Old commerce assumptions also remain **outside** the archive directory: `storefront-mockup/catalog.js:1`, `catalog.json` and `shop-data.json`. They are not loaded by the current home page or in the static publish allowlist (`storefront-mockup/index.html:32`, `hass/sitegen.py:467–475,509–522`). |

Paths shortened to a filename in the table above are under `storefront-mockup/`. Checked offline on **2026-11-21** from `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`. `git diff --name-only 1f8510907cb2989bb50391fde45d6211e4735879 origin/main -- AGENTS.md storefront-mockup hass/content hass/templates hass/sitegen.py hass/content_model.py` printed nothing (exit 0). The existing copy-claims audit notes the historical `catalog.js` price field (`reports/site-copy-claims-2026-11.md:194`); it does not inventory these terms. From the clone root, `python3 -B hass/sitegen.py --check` exited 0: `ok: 10 generated files match hass/content (170 active products, 26 makers)`. No browser, server, live site or runtime data was used; QA findings below are source inspection, not a fresh QA pass.

## R1. Search and totals

From the task workspace, run the uncommitted `scan-scope-words.py` (provided with the handoff) against the clone:

```sh
python3 scan-scope-words.py avocado-shack 37feae1dc5efa6968f90d17a1eda6daed29afd4a --mode totals
python3 scan-scope-words.py avocado-shack 37feae1dc5efa6968f90d17a1eda6daed29afd4a --mode table
```

The script lists tracked paths (`git ls-tree`) and reads pinned blobs (`git show`). It counts **occurrences**, not lines or screens: `price`/`prices`/`priced`/`pricing`; `cart(s)`; `basket(s)`; `box`/`boxes`/`boxed`; `merch`/`merchandise`; `checkout(s)`/`check out(s)`/`check-out(s)`; `buy`/`buys`/`buying`/`buyer(s)`/`bought`; `order(s)`/`ordered`/`ordering`; `shop(s)`/`shopping`/`shopper(s)`; `pickup(s)`/`pick up(s)`/`pick-up(s)`; `delivery`/`deliveries`; and literal `$` (including source syntax). Matching ignores case, splits on punctuation and underscores, and recognizes an ASCII lower-case/digit to upper-case boundary, so `samplePrice` counts but `carton` and plain `checkbox` do not. No decoding of escaped text or OCR; not a synonym or behavior detector.

File groups: `AGENTS.md`; root and one-level `index.html` pages under `storefront-mockup/`; its root `.js`, `.json` and `.css` files plus the published trail JSON; `hass/content/*.json`; HTML recursively under `hass/templates/`; the named QA and its helper; and the renderer and schema (`hass/sitegen.py`, `hass/content_model.py`). `storefront-mockup/archive/`, `commerce/` and `reports/` are excluded from the census. Binaries, CSV, other tests, docs and pipeline modules are not counted. Current checked-in content only; no inference about later edits, another build or live input.

| Group | Files | price | cart | basket | box | merch | checkout | buy | order | shop | pickup | delivery | $ | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Policy | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 6 |
| Site HTML | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 2 |
| Site JS | 10 | 423 | 0 | 24 | 59 | 41 | 0 | 0 | 4 | 172 | 1 | 0 | 291 | 1015 |
| Site JSON | 22 | 958 | 1 | 45 | 59 | 58 | 0 | 0 | 0 | 257 | 2 | 0 | 2 | 1382 |
| Hass JSON | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Hass HTML templates | 14 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 |
| QA source | 2 | 7 | 0 | 1 | 20 | 2 | 0 | 0 | 64 | 7 | 1 | 2 | 106 | 210 |
| Site CSS | 3 | 0 | 0 | 0 | 14 | 0 | 0 | 0 | 1 | 9 | 0 | 0 | 0 | 24 |
| Generator support | 2 | 17 | 0 | 0 | 0 | 0 | 1 | 1 | 17 | 23 | 0 | 1 | 10 | 70 |
| All | 65 | 1406 | 1 | 71 | 153 | 102 | 2 | 2 | 86 | 470 | 4 | 4 | 409 | 2710 |

## R2. Every hit in those file groups

[Full occurrence table](#r2-occurrence-table). Each line:column is one occurrence, in characters starting at 1. Identical excerpts within a file share a row but retain every location. Quotes use up to 120 source characters; legacy data and log entries use shorter field/value fragments to keep amounts, counts, messages and contact details out. The file heading supplies the path for each row; `--mode table --path shop.js` is an example of a focused replay.

- **Visitor-visible text** counts the Visit paragraph and its generating fallback separately in source, but they are the same displayed copy. **Attribute** covers `src="shop.js"`, the conditional `product-price` class and SVG `viewBox`, not labels or transactional controls.
- **Code/comment** covers policy/QA strings, names such as `availBox`, display order, CSS box sizing and source `$` syntax. The first `$` at `storefront-mockup/shop.js:21:69` is a literal **conditional** price prefix; the second at `:21:70` starts interpolation. Neither is actual visitor text in this snapshot: R1 finds no `sellingPrice` in `hass/content/products.json` or `storefront-mockup/catalog-products.js`; the card emits no price paragraph without it (`hass/content_model.py:37,250–251,284–285`; `hass/sitegen.py:197–209`; `shop.js:19–22`).
- **Data field not rendered** includes the old catalog/extraction data, mock prices and commerce collections, and recorded image/QA evidence. `cart` only matches the QA artifact's `cartPreserved` key (`storefront-mockup/scroll-QA.json:7`); it is not a site cart. Compare the home page script list (`storefront-mockup/index.html:32`), `storefront-mockup/README.md:14–17,28` and the publish allowlist (`hass/sitegen.py:467–475,509–522`). Archived features are historical and not conflated with either these working-tree leftovers or the visitor site.

## R3. What catalog-only QA covers

`storefront-mockup/catalog-only-qa.cjs:8–12` opens `/?view=all` and runs these two commerce assertions before the later scroll to draw all cards (`:218–223`):

```js
assert.equal(await page.locator('[data-add],#bag,#boxes,#merch,#owner,#order-preview,.price,[data-product],.food-detail,#hikes').count(),0);
assert.doesNotMatch(await commerceAuditText(page),/\$\d|add to basket|pickup|local delivery|weekly boxes|online shop|merchandise|Discover this food|Food & maker story/i);
```

| Covered by these assertions | Not covered |
|---|---|
| Exact DOM selectors, including `.price`, `#boxes`, `#merch` and `#order-preview`. Hidden matching nodes still count. | Other selectors and attributes, including `.product-price` (a different class) and `src="shop.js"`. Not a scan of JS, CSS, JSON, comments, or QA records. |
| On the sampled home DOM, an unmasked dollar immediately followed by a digit, or the listed phrases (e.g. `add to basket`, `weekly boxes`, `local delivery`, `online shop`, `merchandise`). | Not the R1 word families in general: standalone `price`, `cart`, `basket`, `box`, `merch`, `checkout`, `buy`/`buyer`, `order`, `shop`, `delivery` and `$` alone do not match; `pick-up` is not `pickup`. The actual `buyer` hit does not match. Nor do later-paged or collapsed text that is not in that `innerText` snapshot, other routes, or source data. |
| `qa-env.cjs:45–53` keeps the rest of `document.body.innerText`: other eligible text can still fail the regex. | It temporarily blanks only a matching catalog-card paragraph with a single text node equal to `'$'+price`, when the corresponding `sellingPrice` passes the helper's format check. It restores the text in `finally`. Thus it deliberately does **not** check the one read-only price line described in R2. |

Reference only: `storefront-mockup/static-site-qa.cjs:32–33,64–69` checks more words on the publishable pages, with the same mask. Neither test is a substitute for reconciling the price capability with `AGENTS.md:8`. No test or policy change is proposed here.

## R4. Visitor-visible hits, ranked

| Rank | Visitor sees | Smallest change if the owner requests one |
|---|---|---|
| 1 (only actual hit) | “produce buyer’s curiosity” in `storefront-mockup/index.html:27`, Visit section `section#visit > div > p` (story paragraph, not a button). Its generating text is `DEFAULT_STORY` at `hass/content_model.py:82`, inserted by `hass/sitegen.py:277` through `hass/templates/home/visit.html:1`. | Change only the owner-approved phrase in the story supplied to that element, then regenerate the home output per `storefront-mockup/README.md:10`; do not hand-edit the generated paragraph. Preserve the rest of the story, including its factual claims. |

**No wording unit is needed on the evidence of this search.** The one visible phrase describes in-person sourcing; it does not offer purchase. The dormant amount paragraph (`shop.js:21–22`) is not a second visible hit at this main. Whether to retain the existing price capability or reconcile it with the scope language is an owner decision, not a copy change silently included here.

### R2 occurrence table
#### `AGENTS.md` (6)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 8:39 | `prices` | Code/comment | “- Preserve the catalog-only scope: no prices, basket, boxes, merch or checkout.” |
| 8:47 | `basket` | Code/comment | “- Preserve the catalog-only scope: no prices, basket, boxes, merch or checkout.” |
| 8:55 | `boxes` | Code/comment | “- Preserve the catalog-only scope: no prices, basket, boxes, merch or checkout.” |
| 8:62 | `merch` | Code/comment | “- Preserve the catalog-only scope: no prices, basket, boxes, merch or checkout.” |
| 8:71 | `checkout` | Code/comment | “- Preserve the catalog-only scope: no prices, basket, boxes, merch or checkout.” |
| 9:54 | `delivery` | Code/comment | “- Preserve separate newsletter/hiking consent. Email delivery is unconnected.” |

#### `hass/content_model.py` (58)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 8:9 | `price` | Code/comment | “selling price is the only finance field admitted to product records.” |
| 34:7 | `order` | Code/comment | “# key order (the migrated records use three historical orders; the generator” |
| 34:56 | `orders` | Code/comment | “# key order (the migrated records use three historical orders; the generator” |
| 35:27 | `order` | Code/comment | “# preserves each record's order so output stays byte-identical).” |
| 37:59 | `Price` | Code/comment | “PRODUCT_OPTIONAL_PUBLIC = ("imageAlt", "addedOn", "sellingPrice", "supplier")  # public when present” |
| 38:39 | `$` | Code/comment | “# Canonical intake USD decimal, up to &#36;[amount withheld], with the basis only if supplied.” |
| 39:9 | `PRICE` | Code/comment | “SELLING_PRICE_RE = re.compile(r"(?:0&#124;[1-9][0-9]{0,5})&#92;.[0-9]{2}(?: per lb&#124; each)?")” |
| 40:9 | `PRICE` | Code/comment | “SELLING_PRICE_ERROR = "must be 0.00 to 999999.99 in USD, optionally followed by ' per lb' or ' each'"” |
| 41:110 | `SHOP` | Code/comment | “PRODUCT_INTERNAL_FIELDS = ("status", "hold", "available", "available_on",  # owner-set word + its check day (SHOP-1)” |
| 45:1 | `SHOP` | Code/comment | “SHOP_TZ = ZoneInfo("America/Los_Angeles")” |
| 75:59 | `order` | Code/comment | “SPECIAL_FIELDS = ("id", "title", "deal", "start", "end", "order")” |
| 78:50 | `ORDER` | Code/comment | “MAX_SPECIAL_TITLE, MAX_SPECIAL_DEAL, MAX_SPECIAL_ORDER = 60, 60, 99” |
| 80:76 | `$` | Code/comment | “HOME_IMAGE_RE = re.compile(r"^assets/products/photo-[0-9a-f]{16}&#92;.(jpg&#124;png)&#36;")  # the path photos.install writes” |
| 82:49 | `buyer` | Visitor-visible text | “a produce buyer’s curiosity and long-standing grower relationships to the Shack.” |
| 101:46 | `$` | Code/comment | “ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}&#36;")” |
| 102:94 | `$` | Code/comment | “IMAGE_RE = re.compile(r"^assets/products/[A-Za-z0-9][A-Za-z0-9._-]{0,80}&#92;.(webp&#124;jpg&#124;jpeg&#124;png)&#36;")” |
| 107:30 | `$` | Code/comment | “FORBIDDEN_TEXT = ("&lt;", "&gt;", "&#36;", "{{", "}}")” |
| 167:55 | `price` | Code/comment | “# version and the payload. Anything else (a stray price or private note) is” |
| 250:19 | `price` | Code/comment | “def valid_selling_price(value):” |
| 251:47 | `PRICE` | Code/comment | “return isinstance(value, str) and SELLING_PRICE_RE.fullmatch(value) is not None” |
| 284:20, 284:74 | `Price` | Code/comment | “if "sellingPrice" in rec and not valid_selling_price(rec["sellingPrice"]):” |
| 284:56 | `price` | Code/comment | “if "sellingPrice" in rec and not valid_selling_price(rec["sellingPrice"]):” |
| 285:46 | `Price` | Code/comment | “problems.append(f"{where}.sellingPrice: {SELLING_PRICE_ERROR}")” |
| 285:62 | `PRICE` | Code/comment | “problems.append(f"{where}.sellingPrice: {SELLING_PRICE_ERROR}")” |
| 309:26 | `shop` | Code/comment | “elif added &gt; shop_today():” |
| 317:81 | `shop` | Code/comment | “le_on" in rec and iso_day(rec["available_on"]) &gt; (today or shop_today()):  # may follow the full check, never the future” |
| 391:67 | `delivery` | Code/comment | “problems.append("community.club.emailConnected: email delivery is not connected; must be false")” |
| 475:5 | `shop` | Code/comment | “def shop_today(now: datetime &#124; None = None) -&gt; date:” |
| 476:12 | `shop` | Code/comment | “"""The shop's calendar date (Pacific) at &#96;&#96;now&#96;&#96; (default: the current time)."""” |
| 477:33, 477:54 | `SHOP` | Code/comment | “return (now or datetime.now(SHOP_TZ)).astimezone(SHOP_TZ).date()” |
| 509:125, 509:144 | `$` | Code/comment | “Za-z]&#124;&#92;b&#92;w+&#92;s+(?:at&#124;&#92;(at&#92;))&#92;s+&#92;w+&#92;s+dot&#92;s+&#92;w+", re.I)  # a real email; "2 @ &#36;[amount withheld]" and "3 @ 2 for &#36;[amount withheld]" price notation is not” |
| 509:148 | `price` | Code/comment | “Za-z]&#124;&#92;b&#92;w+&#92;s+(?:at&#124;&#92;(at&#92;))&#92;s+&#92;w+&#92;s+dot&#92;s+&#92;w+", re.I)  # a real email; "2 @ &#36;[amount withheld]" and "3 @ 2 for &#36;[amount withheld]" price notation is not” |
| 511:62 | `$` | Code/comment | “SPECIAL_FORBIDDEN = tuple(c for c in FORBIDDEN_TEXT if c != "&#36;") + ("&amp;lt", "&amp;gt", "&amp;#", "&amp;amp")” |
| 516:45 | `price` | Code/comment | “numbers. Only the deal line may carry a price (&#96;&#96;&#36;&#96;&#96;); the title may not."""” |
| 516:54 | `$` | Code/comment | “numbers. Only the deal line may carry a price (&#96;&#96;&#36;&#96;&#96;); the title may not."""” |
| 530:9 | `$` | Code/comment | “if "&#36;" in value and not deal:” |
| 531:35 | `price` | Code/comment | “return "may not contain a price; put it in the deal line"” |
| 542:75, 542:82 | `order` | Code/comment | “"""The specials whose first day &lt;= Pacific today &lt;= last day, in show order (order, then title). The one rule” |
| 544:20, 603:20 | `shop` | Code/comment | “day = today or shop_today()” |
| 550:48 | `order` | Code/comment | “return sorted(out, key=lambda sp: (sp.get("order", 0), sp.get("title", ""), sp.get("id", "")))” |
| 592:9, 592:25 | `order` | Code/comment | “order = sp.get("order")” |
| 593:23, 593:54, 593:78 | `order` | Code/comment | “if isinstance(order, bool) or not isinstance(order, int) or not 0 &lt;= order &lt;= MAX_SPECIAL_ORDER:” |
| 593:99 | `ORDER` | Code/comment | “if isinstance(order, bool) or not isinstance(order, int) or not 0 &lt;= order &lt;= MAX_SPECIAL_ORDER:” |
| 594:39 | `order` | Code/comment | “problems.append(f"{where}.order: must be a whole number 0 to {MAX_SPECIAL_ORDER}")” |
| 594:87 | `ORDER` | Code/comment | “problems.append(f"{where}.order: must be a whole number 0 to {MAX_SPECIAL_ORDER}")” |
| 653:61 | `shop` | Code/comment | “problems.append("The banner link must be one of the shop's own places.")” |
| 665:26 | `shop` | Code/comment | “from hass.skills.shop import price_problem” |
| 665:38 | `price` | Code/comment | “from hass.skills.shop import price_problem” |
| 670:19 | `price` | Code/comment | “if why := price_problem(value):” |
| 719:30 | `shop` | Code/comment | “elif day &gt; (today or shop_today()):” |

#### `hass/sitegen.py` (12)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 44:45 | `shop` | Code/comment | “checked_on, iso_day, load_and_validate, shop_today, INFO_PAGES,” |
| 53:3 | `SHOP` | Code/comment | “# SHOP-1: freshness words come only from Michael's recorded check (store.selection_checked_on), never from the clock.” |
| 166:18 | `shop` | Code/comment | “# AV1622-04: shop.js re-ages this paragraph in the browser from its own stored date (and phone); this text is the no” |
| 190:95 | `shop` | Code/comment | “before the store's last full check, not after &#96;&#96;today&#96;&#96; and at most STALE_AFTER_DAYS old (shop.js has the same rule)."""” |
| 199:5 | `shop` | Code/comment | “shop.js turns them into words with the same rule as availability_label/checked_line against the visitor's Pacific da” |
| 279:55 | `shop` | Code/comment | “**notice_slots(store.get("notice"), (today or shop_today()).isoformat()),” |
| 304:46 | `order` | Code/comment | “"""AVB-19: the home parts in their saved order and the header/footer links of the shown parts. Template text” |
| 321:58 | `shop` | Code/comment | “"""AVB-19: the top strip. Without a banner it is the shop's default line, byte for byte; with one, the default” |
| 359:98 | `shop` | Code/comment | “"""Return {repo-relative path: bytes} for every generated site file. &#96;&#96;today&#96;&#96; (default: the shop's current date)” |
| 361:22 | `shop` | Code/comment | “today = today or shop_today()” |
| 472:82 | `shop` | Code/comment | “PUBLISH_STATIC = ("style.css", "hiking.css", "trail-explorer.css", "script.js", "shop.js", "community.js",” |
| 643:102 | `checkout` | Code/comment | “parser.add_argument("--repo", type=Path, default=REPO_ROOT, help="repository root (default: this checkout)")” |

#### `hass/templates/index.html` (1)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 20:126 | `shop` | Attribute | “&lt;script src="shop.js"&gt;&lt;/script&gt;” |

#### `storefront-mockup/catalog-only-qa.cjs` (200)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 11:52 | `boxes` | Code/comment | “assert.equal(await page.locator('[data-add],#bag,#boxes,#merch,#owner,#order-preview,.price,[data-product],.food-detail” |
| 11:59 | `merch` | Code/comment | “assert.equal(await page.locator('[data-add],#bag,#boxes,#merch,#owner,#order-preview,.price,[data-product],.food-detail,” |
| 11:73 | `order` | Code/comment | “wait page.locator('[data-add],#bag,#boxes,#merch,#owner,#order-preview,.price,[data-product],.food-detail,#hikes').count” |
| 11:88 | `price` | Code/comment | “age.locator('[data-add],#bag,#boxes,#merch,#owner,#order-preview,.price,[data-product],.food-detail,#hikes').count(),0);” |
| 12:54 | `$` | Code/comment | “assert.doesNotMatch(await commerceAuditText(page),/&#92;&#36;&#92;d&#124;add to basket&#124;pickup&#124;local delivery&#124;weekly boxes&#124;online shop&#124;me” |
| 12:65 | `basket` | Code/comment | “.doesNotMatch(await commerceAuditText(page),/&#92;&#36;&#92;d&#124;add to basket&#124;pickup&#124;local delivery&#124;weekly boxes&#124;online shop&#124;merchandi” |
| 12:72 | `pickup` | Code/comment | “tMatch(await commerceAuditText(page),/&#92;&#36;&#92;d&#124;add to basket&#124;pickup&#124;local delivery&#124;weekly boxes&#124;online shop&#124;merchandise&#124;Disc” |
| 12:85 | `delivery` | Code/comment | “ommerceAuditText(page),/&#92;&#36;&#92;d&#124;add to basket&#124;pickup&#124;local delivery&#124;weekly boxes&#124;online shop&#124;merchandise&#124;Discover this food” |
| 12:101 | `boxes` | Code/comment | “t(page),/&#92;&#36;&#92;d&#124;add to basket&#124;pickup&#124;local delivery&#124;weekly boxes&#124;online shop&#124;merchandise&#124;Discover this food&#124;Food &amp; maker s” |
| 12:114 | `shop` | Code/comment | “/&#92;&#36;&#92;d&#124;add to basket&#124;pickup&#124;local delivery&#124;weekly boxes&#124;online shop&#124;merchandise&#124;Discover this food&#124;Food &amp; maker story/i);” |
| 12:119 | `merchandise` | Code/comment | “/&#92;&#36;&#92;d&#124;add to basket&#124;pickup&#124;local delivery&#124;weekly boxes&#124;online shop&#124;merchandise&#124;Discover this food&#124;Food &amp; maker story/i);” |
| 21:101 | `$` | Code/comment | “of ['catalog-products','producers'])await page.unroute(&#96;**/&#36;{f}.js&#96;).catch(()=&gt;{});await page.unroute('**/assets/logo-he” |
| 23:165 | `$` | Code/comment | “body:(await res.text())+&#96;;catalog.length=0;catalog.push(...&#36;{JSON.stringify(prods)});&#36;{fresh?&#96;catalogFreshness.selection” |
| 23:191 | `$` | Code/comment | “catalog.length=0;catalog.push(...&#36;{JSON.stringify(prods)});&#36;{fresh?&#96;catalogFreshness.selectionCheckedOn=&#36;{JSON.stringify” |
| 23:236 | `$` | Code/comment | “alog.push(...&#36;{JSON.stringify(prods)});&#36;{fresh?&#96;catalogFreshness.selectionCheckedOn=&#36;{JSON.stringify(fresh)};&#96;:''}&#96;})});” |
| 24:149 | `$` | Code/comment | “.fetch();r.fulfill({response:res,body:(await res.text())+&#96;;Object.assign(producers,&#36;{JSON.stringify(PRODUCERS)});&#96;})})};” |
| 26:36 | `box` | Code/comment | “const st=()=&gt;page.evaluate(()=&gt;({box:&#36;('#product-search').value,q:new URLSearchParams(location.search).get('q'),order:” |
| 26:40 | `$` | Code/comment | “const st=()=&gt;page.evaluate(()=&gt;({box:&#36;('#product-search').value,q:new URLSearchParams(location.search).get('q'),order:” |
| 26:115 | `order` | Code/comment | “').value,q:new URLSearchParams(location.search).get('q'),order:filteredProducts().map(p=&gt;p.id),cards:[...document.queryS” |
| 26:249 | `$` | Code/comment | “All('#catalog-grid article')].map(a=&gt;a.dataset.productId),count:&#36;('#catalog-count').textContent,visible:visibleCount}));” |
| 30:21 | `order` | Code/comment | “assert.ok(same(s.order,want),&#96;&#36;{label}: '&#36;{t}' wants &#36;{want.join(',')} got &#36;{s.order.join(',')}&#96;);assert.ok(same(s.ca” |
| 30:34, 30:45, 30:57 | `$` | Code/comment | “assert.ok(same(s.order,want),&#96;&#36;{label}: '&#36;{t}' wants &#36;{want.join(',')} got &#36;{s.order.join(',')}&#96;);assert.ok(same(s.ca” |
| 30:79 | `$` | Code/comment | “.order,want),&#96;&#36;{label}: '&#36;{t}' wants &#36;{want.join(',')} got &#36;{s.order.join(',')}&#96;);assert.ok(same(s.cards,want.slice(0,12” |
| 30:83 | `order` | Code/comment | “,want),&#96;&#36;{label}: '&#36;{t}' wants &#36;{want.join(',')} got &#36;{s.order.join(',')}&#96;);assert.ok(same(s.cards,want.slice(0,12)),&#96;&#36;{” |
| 30:144, 30:155 | `$` | Code/comment | “.order.join(',')}&#96;);assert.ok(same(s.cards,want.slice(0,12)),&#96;&#36;{label}: '&#36;{t}' draws the same cards in the same order&#96;);” |
| 30:194 | `order` | Code/comment | “.order.join(',')}&#96;);assert.ok(same(s.cards,want.slice(0,12)),&#96;&#36;{label}: '&#36;{t}' draws the same cards in the same order&#96;);” |
| 31:26, 31:54 | `$` | Code/comment | “assert.equal(s.count,&#96;&#36;{want.length} selections · &#36;{Math.min(12,want.length)} shown&#96;,&#96;&#36;{label}: '&#36;{t}' count line&#96;);r” |
| 31:90, 31:101 | `$` | Code/comment | “.equal(s.count,&#96;&#36;{want.length} selections · &#36;{Math.min(12,want.length)} shown&#96;,&#96;&#36;{label}: '&#36;{t}' count line&#96;);return s};” |
| 32:13 | `order` | Code/comment | “// Source order interleaves description-only (s01, s05, s10), metadata-only (s02 name, s06 brand, s07 town, s08 shelf,” |
| 39:137 | `order` | Code/comment | “['s02','s03','s06','s07','s01','s05'],'name, both, brand and town first; description-only after, each in source order');” |
| 46:86 | `order` | Code/comment | “assert.ok(same(await page.evaluate(()=&gt;catalog.map(p=&gt;p.id)),F1ALL),'the catalog order is unchanged');” |
| 48:100 | `$` | Code/comment | “en']){const meta=await page.evaluate(t=&gt;catalog.filter(p=&gt;&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''}&#96;.toLowerCase().in” |
| 48:110 | `$` | Code/comment | “t meta=await page.evaluate(t=&gt;catalog.filter(p=&gt;&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''}&#96;.toLowerCase().includes(t))” |
| 48:121 | `$` | Code/comment | “t page.evaluate(t=&gt;catalog.filter(p=&gt;&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''}&#96;.toLowerCase().includes(t)).map(p=&gt;p.i” |
| 50:175 | `order` | Code/comment | “(i))];await page.locator('#product-search').fill(t);const s=await st();assert.ok(same(s.order,want),'real catalog '+t);}” |
| 62:38 | `box` | Code/comment | “// The 80 code point limit: the box, the results and the address agree; typed, pasted and ?q= give one result.” |
| 65:29, 65:45 | `box` | Code/comment | “assert.equal([...typed.box].length,80,'box cut to 80 code points');assert.equal(typed.q,A.repeat(80));assert.ok(sam” |
| 65:129 | `order` | Code/comment | “code points');assert.equal(typed.q,A.repeat(80));assert.ok(same(typed.order,['f06']),'the 81st code point is ignored');” |
| 67:103 | `box` | Code/comment | “ent(A.repeat(100)));{const r=await st();assert.ok(same([r.box,r.order,r.cards,r.count],[typed.box,typed.order,typed.card” |
| 67:109 | `order` | Code/comment | “epeat(100)));{const r=await st();assert.ok(same([r.box,r.order,r.cards,r.count],[typed.box,typed.order,typed.cards,typed” |
| 67:139 | `box` | Code/comment | “t();assert.ok(same([r.box,r.order,r.cards,r.count],[typed.box,typed.order,typed.cards,typed.count]),'?q= and typed text” |
| 67:149 | `order` | Code/comment | “t.ok(same([r.box,r.order,r.cards,r.count],[typed.box,typed.order,typed.cards,typed.count]),'?q= and typed text agree');}” |
| 68:100 | `box` | Code/comment | “oard.insertText(A.repeat(79)+'q'));assert.equal([...exact.box].length,80);assert.ok(same(exact.order,['f07']),'exactly 8” |
| 68:137 | `order` | Code/comment | “q'));assert.equal([...exact.box].length,80);assert.ok(same(exact.order,['f07']),'exactly 80 code points is kept whole');” |
| 73:141 | `order` | Code/comment | “ait page.waitForTimeout(150);assert.ok(same((await st()).order,['f08']),'hostile ?q= matches the description as text');a” |
| 76:29 | `Order` | Code/comment | “descriptionSearchKeepsNewOrder:async()=&gt;{const N=(id,name,ago,o={})=&gt;P(id,name,{...(ago===null?{}:{addedOn:dAgo(ago)}” |
| 77:15 | `order` | Code/comment | “// Source order: o1 old/name, nd1 New 3 days/description, nm1 + nm2 New 1 day/name (tie), nd2 New today/description,” |
| 80:105 | `order` | Code/comment | “await search('',['nd2','nm1','nm2','nd1','o1','od1','om1'],'New first, newest first, ties in source order');” |
| 83:89 | `order` | Code/comment | “valuate(()=&gt;catalog.map(p=&gt;p.id)),src),'the source array order is unchanged');assert.ok(same(await page.evaluate(()=&gt;JSO” |
| 84:62 | `order` | Code/comment | “await go('?view=all&amp;q=goat');assert.ok(same((await st()).order,['nm1','nm2','o1','om1','nd2','nd1','od1']),'?q= restores” |
| 85:153 | `order` | Code/comment | “fill('goat');assert.ok(same((await st()).cards,['nm1','nm2','o1','om1','nd2','nd1','od1']),'drawn in the same order');},” |
| 87:96 | `$` | Code/comment | “4;G.push(P('g'+String(i).padStart(2,'0'),k===0?&#96;Honey item &#36;{i}&#96;:&#96;Plain item &#36;{i}&#96;,{brand:i%2?'Acme':'Bolt',category:['p” |
| 87:114 | `$` | Code/comment | “ing(i).padStart(2,'0'),k===0?&#96;Honey item &#36;{i}&#96;:&#96;Plain item &#36;{i}&#96;,{brand:i%2?'Acme':'Bolt',category:['pantry','dairy','br” |
| 87:256 | `$` | Code/comment | “:i%5===0?'ZF':null,description:k===3?'Salty.':&#96;Sweet honey &#36;{i}.&#96;,availabilityState:i%7&lt;3?'yes':'no',availabilityChecked” |
| 95:101 | `$` | Code/comment | “'+f.from:''));if(f.shelf)await page.locator(&#96;[data-filter="&#36;{f.shelf}"]&#96;).click();if(f.brand)await page.locator('#brand-” |
| 97:23 | `order` | Code/comment | “assert.ok(same(s.order,w),label+': both groups, filters applied');assert.ok(same(s.cards,w.slice(0,12)),label+': fi” |
| 97:154 | `$` | Code/comment | “w.slice(0,12)),label+': first page');assert.equal(s.count,&#96;&#36;{w.length} selections · &#36;{Math.min(12,w.length)} shown&#96;,labe” |
| 97:179 | `$` | Code/comment | “el+': first page');assert.equal(s.count,&#96;&#36;{w.length} selections · &#36;{Math.min(12,w.length)} shown&#96;,label+': count line');” |
| 98:164 | `order` | Code/comment | “)=&gt;loadMore());s=await st();assert.ok(same(s.cards,w.slice(0,s.visible)),label+': each page continues the same order');}” |
| 99:148 | `$` | Code/comment | “k(same(s.cards,w),label+': no gaps');assert.equal(s.count,&#96;&#36;{w.length} selections · &#36;{w.length} shown&#96;,label+': all show” |
| 99:173 | `$` | Code/comment | “me(s.cards,w),label+': no gaps');assert.equal(s.count,&#96;&#36;{w.length} selections · &#36;{w.length} shown&#96;,label+': all shown');” |
| 104:80 | `box` | Code/comment | “&amp;q=goat&amp;view=all#market');let s=await st();assert.equal(s.box,'goat');assert.ok(same(s.order,GOAT)&amp;&amp;same(s.cards,GOAT),w” |
| 104:109 | `order` | Code/comment | “s=await st();assert.equal(s.box,'goat');assert.ok(same(s.order,GOAT)&amp;&amp;same(s.cards,GOAT),width+': ?q= restores the two g” |
| 106:136 | `order` | Code/comment | “);await page.waitForSelector('#catalog-grid article');assert.ok(same((await st()).cards,GOAT),'reload keeps the order');” |
| 109:175 | `box` | Code/comment | “==='s05',null,{timeout:5000});s=await st();assert.equal(s.box,'','a valid item clears the search');assert.ok(same(s.card” |
| 114:36 | `order` | Code/comment | “s=await st();assert.ok(same(s.order,GOAT),'typing after an item link searches both groups');assert.equal(await page” |
| 116:40 | `order` | Code/comment | “// AV1104-01: every typed word, any order, across name/brand/town/shelf/badge (first group) and the description (seco” |
| 117:22 | `Order` | Code/comment | “searchEveryWordAnyOrder:async()=&gt;{” |
| 118:41 | `Shop` | Code/comment | “const W=[P('w03','Jam',{brand:'Poly Shop',description:'Cal sweet.'}),P('w01','Strawberry Jam',{brand:'Cal Poly'}),P(” |
| 121:170 | `order` | Code/comment | “s in any field; w03 needs its description, so it follows');await search('jam poly cal',['w01','w02','w03'],'any order');” |
| 123:191 | `order` | Code/comment | “lf word or name word first; description after');await search('cheese stepladder',['w04','w05','w09','w07'],'any order');” |
| 127:130 | `order` | Code/comment | “l(t);const s=await st();for(const id of must)assert.ok(s.order.includes(id),&#96;real catalog '&#36;{t}' includes &#36;{id}&#96;);assert” |
| 127:164 | `$` | Code/comment | “t id of must)assert.ok(s.order.includes(id),&#96;real catalog '&#36;{t}' includes &#36;{id}&#96;);assert.equal(s.count.split(' &#92;u00b7 ')” |
| 127:179 | `$` | Code/comment | “sert.ok(s.order.includes(id),&#96;real catalog '&#36;{t}' includes &#36;{id}&#96;);assert.equal(s.count.split(' &#92;u00b7 ')[0],&#96;&#36;{s.order.” |
| 127:230 | `$` | Code/comment | “eal catalog '&#36;{t}' includes &#36;{id}&#96;);assert.equal(s.count.split(' &#92;u00b7 ')[0],&#96;&#36;{s.order.length} selections&#96;);return s};” |
| 127:234 | `order` | Code/comment | “eal catalog '&#36;{t}' includes &#36;{id}&#96;);assert.equal(s.count.split(' &#92;u00b7 ')[0],&#96;&#36;{s.order.length} selections&#96;);return s};” |
| 129:47 | `order` | Code/comment | “const jam=(await real('cal poly jam',[])).order;assert.ok(jam.length&gt;=3&amp;&amp;await page.evaluate(ids=&gt;ids.every(i=&gt;catal” |
| 139:114 | `order` | Code/comment | “oto-product-056','photo-product-008','photo-product-106'])assert.ok(s.order.includes(id),'real strawberries finds '+id);” |
| 140:85 | `order` | Code/comment | “oduct-search').fill('strawberry');assert.ok((await st()).order.includes('photo-product-056'),'real strawberry finds Stra” |
| 144:116 | `order` | Code/comment | “h('plum red',[...meta,...desc],'both words: name-and-name first, then name plus description, source order within each');” |
| 145:97 | `$` | Code/comment | “ch').fill('red plum');assert.equal(await page.evaluate(()=&gt;&#36;('#catalog-count').textContent),'30 selections &#92;u00b7 12 sho” |
| 147:93 | `order` | Code/comment | “er').selectOption('Orchard');assert.ok(same((await st()).order,[...meta,...desc].filter(id=&gt;M.find(p=&gt;p.id===id).brand==” |
| 147:247 | `order` | Code/comment | “nd AND words');assert.equal((await st()).visible,Math.min(12,(await st()).order.length),'a filter starts a fresh page');” |
| 148:151 | `box` | Code/comment | “await page.locator('#product-search').fill('x'.repeat(81)+' plum');assert.equal((await st()).box.length,80,'cut at 80');” |
| 150:121 | `order` | Code/comment | “utm=x#market');const back=await st();assert.ok(same(back.order,[...meta,...desc]),'restore gives the same order');assert” |
| 150:170 | `order` | Code/comment | “me(back.order,[...meta,...desc]),'restore gives the same order');assert.equal(back.box,'plum   RED');assert.equal(back.c” |
| 150:196 | `box` | Code/comment | “.desc]),'restore gives the same order');assert.equal(back.box,'plum   RED');assert.equal(back.count,'30 selections &#92;u00b” |
| 151:116 | `order` | Code/comment | “onerror=alert(1)&gt; plum'));assert.deepEqual((await st()).order,[]);assert.equal(await page.locator('img[src="x"]').count” |
| 161:39 | `order` | Code/comment | “let s=await st();assert.ok(same(s.order,all),'All: Sold out last, rest in source order: '+s.order.join(','));assert.” |
| 161:86 | `order` | Code/comment | “ok(same(s.order,all),'All: Sold out last, rest in source order: '+s.order.join(','));assert.ok(same(s.cards,all),'cards” |
| 161:97 | `order` | Code/comment | “rder,all),'All: Sold out last, rest in source order: '+s.order.join(','));assert.ok(same(s.cards,all),'cards drawn in th” |
| 161:167 | `order` | Code/comment | “n source order: '+s.order.join(','));assert.ok(same(s.cards,all),'cards drawn in the same order, Sold out still shown');” |
| 165:22 | `order` | Code/comment | “assert.ok(same(s.order,['z02','z04','z05','z06','z01','z03','z07','z08']),'search: name group (available, then Sold” |
| 165:182 | `order` | Code/comment | “'search: name group (available, then Sold out), then description group (available, then Sold out): '+s.order.join(','));” |
| 167:87, 167:124 | `order` | Code/comment | “or('[data-filter="bread"]').click();s=await st();assert.ok(same(s.order,['z09','z10']),'one shelf: '+s.order.join(','));” |
| 169:44 | `order` | Code/comment | “// Every card Sold out stays in source order.” |
| 170:155, 170:201 | `order` | Code/comment | “ve(S,dAgo(0));await go('?view=all');s=await st();assert.ok(same(s.order,['y1','y2','y3']),'all Sold out: source order');” |
| 174:17 | `order` | Code/comment | “assert.ok(s.order.indexOf('g00')===13&amp;&amp;s.cards.includes('g00'),'?item loads enough cards to reach the Sold out card” |
| 175:22 | `order` | Code/comment | “assert.ok(same(s.order.slice(0,14),[...G.slice(3).map(p=&gt;p.id),'g00']),'order for item');assert.equal(s.count,'16 se” |
| 175:77 | `order` | Code/comment | “s.order.slice(0,14),[...G.slice(3).map(p=&gt;p.id),'g00']),'order for item');assert.equal(s.count,'16 selections &#92;u00b7 24” |
| 194:315 | `order` | Code/comment | “.document.querySelectorAll('#catalog-grid article h3')].map(e=&gt;e.textContent),order:filteredProducts().map(p=&gt;p.id)}))};” |
| 200:23 | `order` | Code/comment | “assert.ok(sameSet(r.order.slice(0,n),meta),label+': metadata hits come first');assert.ok(sameSet(r.order.slice(n),extr” |
| 200:102 | `order` | Code/comment | “,label+': metadata hits come first');assert.ok(sameSet(r.order.slice(n),extra),label+': then exactly the description-onl” |
| 200:210 | `order` | Code/comment | “exactly the description-only cards');assert.equal(r.cards,Math.min(12,r.order.length),label+': drawn cards');return r};” |
| 201:77 | `$` | Code/comment | “ait ids(()=&gt;catalog.filter(p=&gt;organic(p)&#124;&#124;/organic/i.test(&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''}&#96;)).map(p=&gt;p.id));” |
| 201:87 | `$` | Code/comment | “=&gt;catalog.filter(p=&gt;organic(p)&#124;&#124;/organic/i.test(&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''}&#96;)).map(p=&gt;p.id));assert.ok(” |
| 201:98 | `$` | Code/comment | “ilter(p=&gt;organic(p)&#124;&#124;/organic/i.test(&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''}&#96;)).map(p=&gt;p.id));assert.ok(orgWant.len” |
| 203:83 | `$` | Code/comment | “&gt;page.evaluate(([s,w])=&gt;catalog.filter(p=&gt;p.category===s&#124;&#124;&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''}&#96;.toLowerCase().in” |
| 203:93 | `$` | Code/comment | “uate(([s,w])=&gt;catalog.filter(p=&gt;p.category===s&#124;&#124;&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''}&#96;.toLowerCase().includes(w))” |
| 203:104 | `$` | Code/comment | “)=&gt;catalog.filter(p=&gt;p.category===s&#124;&#124;&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''}&#96;.toLowerCase().includes(w)).map(p=&gt;p.i” |
| 207:137 | `$` | Code/comment | “ata-filter]')].map(b=&gt;b.textContent).join(' ');const h=p=&gt;&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''} &#36;{labels} organic” |
| 207:147 | `$` | Code/comment | “]')].map(b=&gt;b.textContent).join(' ');const h=p=&gt;&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''} &#36;{labels} organic&#96;.toLowerC” |
| 207:158 | `$` | Code/comment | “&gt;b.textContent).join(' ');const h=p=&gt;&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''} &#36;{labels} organic&#96;.toLowerCase();retur” |
| 207:181 | `$` | Code/comment | “');const h=p=&gt;&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''} &#36;{labels} organic&#96;.toLowerCase();return catalog.flatMap(p=&gt;St” |
| 208:186 | `order` | Code/comment | “),r=await q(descOnly);assert.ok(want.length&gt;0&amp;&amp;sameSet(r.order,want)&amp;&amp;r.cards&gt;0,'a word only in descriptions finds exact” |
| 211:122 | `order` | Code/comment | “ion&#92;u2019s','LION&#92;u2018S','lion&#92;u02bcs']){const r=await tiered(t,lion,t);assert.ok(sameSet(r.order.slice(0,2),lion),t);}” |
| 231:342 | `$` | Code/comment | “eout(250);await page.screenshot({path:out+&#96;/catalog-inline-&#36;{width}.png&#96;});await page.locator('#brand-filter').selectOpt” |
| 231:565 | `$` | Code/comment | “&gt;e.scrollIntoView({behavior:'instant',block:'start'}));await page.screenshot({path:out+&#96;/catalog-maker-&#36;{width}.png&#96;});}” |
| 234:9 | `SHOP` | Code/comment | “// AVO-SHOP-CLEAN-1: the shop opens on packaged goods. These older checks assume the whole catalog, so open() adds view” |
| 234:27 | `shop` | Code/comment | “// AVO-SHOP-CLEAN-1: the shop opens on packaged goods. These older checks assume the whole catalog, so open() adds view” |
| 257:59 | `box` | Code/comment | “// Typed or pasted text past 80 characters is cut in the box as well, so the box, the results and the address agree, an” |
| 257:79 | `box` | Code/comment | “text past 80 characters is cut in the box as well, so the box, the results and the address agree, and a reload restores” |
| 258:37 | `box` | Code/comment | “const view=()=&gt;page.evaluate(()=&gt;({box:document.querySelector('#product-search').value,q:new URLSearchParams(location.s” |
| 260:21, 260:39 | `box` | Code/comment | “assert.equal(live.box,want,label+': box');assert.equal(live.q,want,label+': address');” |
| 262:53 | `$` | Code/comment | “const long=await page.evaluate(()=&gt;catalog.map(p=&gt;&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''}&#96;).find(t=&gt;[...t].length&gt;” |
| 262:63 | `$` | Code/comment | “nst long=await page.evaluate(()=&gt;catalog.map(p=&gt;&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''}&#96;).find(t=&gt;[...t].length&gt;80&amp;” |
| 262:74 | `$` | Code/comment | “ait page.evaluate(()=&gt;catalog.map(p=&gt;&#96;&#36;{p.name} &#36;{p.brand} &#36;{maker(p)?.place&#124;&#124;''}&#96;).find(t=&gt;[...t].length&gt;80&amp;&amp;!/&#92;s/.test” |
| 269:225 | `$` | Code/comment | “tor('[data-filter][aria-pressed="true"]').dataset.filter,q:&#36;('#product-search').value,maker:&#36;('#brand-filter').value,y:s” |
| 269:258 | `$` | Code/comment | “-filter][aria-pressed="true"]').dataset.filter,q:&#36;('#product-search').value,maker:&#36;('#brand-filter').value,y:scrollY}});” |
| 278:20 | `$` | Code/comment | “await open(&#96;?item=&#36;{encodeURIComponent(fruit)}&amp;shelf=bread&amp;q=zzz&amp;maker=Etto&#96;);await inView(fruit);let s=await shown();” |
| 322:144 | `$` | Code/comment | “fill({response:res,body:(await res.text()).replace(&#96;"id": "&#36;{id40}"&#96;,&#96;"id": &#36;{JSON.stringify(odd)}&#96;).replace(&#96;"id": "&#36;{i” |
| 322:161 | `$` | Code/comment | “s,body:(await res.text()).replace(&#96;"id": "&#36;{id40}"&#96;,&#96;"id": &#36;{JSON.stringify(odd)}&#96;).replace(&#96;"id": "&#36;{id41}"&#96;,&#96;"id": "&#36;{” |
| 322:202, 322:220 | `$` | Code/comment | “es.text()).replace(&#96;"id": "&#36;{id40}"&#96;,&#96;"id": &#36;{JSON.stringify(odd)}&#96;).replace(&#96;"id": "&#36;{id41}"&#96;,&#96;"id": "&#36;{long81}"&#96;)})});” |
| 324:151 | `$` | Code/comment | “'#catalog-grid article:focus a.card-link').getAttribute('href');assert.match(oddHref,/^&#92;?item=a%26b%20%3F%23c#market&#36;/);” |
| 339:41 | `$` | Code/comment | “await page.evaluate(k=&gt;{activeFrom='';&#36;('#product-search').value='';&#36;('#brand-filter').value='';selectShelf(&#36;('[data-f” |
| 339:71 | `$` | Code/comment | “e.evaluate(k=&gt;{activeFrom='';&#36;('#product-search').value='';&#36;('#brand-filter').value='';selectShelf(&#36;('[data-filter="all"” |
| 339:111 | `$` | Code/comment | “-search').value='';&#36;('#brand-filter').value='';selectShelf(&#36;('[data-filter="all"]'));limit=catalog.length;renderCatalog(” |
| 340:69, 340:85 | `$` | Code/comment | “const button=page.locator('[data-from]').filter({hasText:&#96;See all &#36;{multi.n} from &#36;{multi.name}&#96;}).first();” |
| 342:52, 342:68 | `$` | Code/comment | “assert.equal(await button.textContent(),&#96;See all &#36;{multi.n} from &#36;{multi.name}&#96;);” |
| 344:70 | `$` | Code/comment | “rrent=page.locator('[data-from]').filter({hasText:&#96;See all &#36;{multi.n} from &#36;{multi.name}&#96;}).first();await current.locato” |
| 344:86 | `$` | Code/comment | “or('[data-from]').filter({hasText:&#96;See all &#36;{multi.n} from &#36;{multi.name}&#96;}).first();await current.locator('xpath=ancesto” |
| 365:275 | `$` | Code/comment | “y:(await res.text())+&#96;;catalogFreshness.selectionCheckedOn=&#36;{JSON.stringify(checked)};&#36;{JSON.stringify(rows)}.forEach(([” |
| 365:302 | `$` | Code/comment | “logFreshness.selectionCheckedOn=&#36;{JSON.stringify(checked)};&#36;{JSON.stringify(rows)}.forEach(([s,o],i)=&gt;{catalog[i].availa” |
| 374:37 | `$` | Code/comment | “await page.locator(&#96;[data-filter="&#36;{empty}"]&#96;).click();assert.equal(await page.locator('#catalog-grid article').count(” |
| 388:83 | `$` | Code/comment | “gFreshness.selectionCheckedOn="2026-10-31";catalog.slice(0,&#36;{n}).forEach(p=&gt;{p.availabilityState="yes";p.availabilityChe” |
| 389:106 | `$` | Code/comment | “nCheckedOn="2026-10-31";catalog.splice(0,catalog.length,...&#36;{JSON.stringify(rows)}.map(p=&gt;({...catalog[0],...p,availabil” |
| 395:161 | `$` | Code/comment | “document.querySelectorAll('.avail-filter').length),checked:&#36;('#avail-filter')?.checked??null,count:&#36;('#catalog-count').t” |
| 395:201 | `$` | Code/comment | “').length),checked:&#36;('#avail-filter')?.checked??null,count:&#36;('#catalog-count').textContent,ids:filteredProducts().map(p=” |
| 395:562 | `$` | Code/comment | “:scrollY,view:activeView,shelf:activeCategory,q:searchText(&#36;('#product-search').value),brand:&#36;('#brand-filter').value,fr” |
| 395:596 | `$` | Code/comment | “iveCategory,q:searchText(&#36;('#product-search').value),brand:&#36;('#brand-filter').value,from:activeFrom,item:linkedItem,stat” |
| 395:660 | `$` | Code/comment | “rand-filter').value,from:activeFrom,item:linkedItem,status:&#36;('#catalog-item-status').hidden?null:&#36;('#catalog-item-status” |
| 395:698 | `$` | Code/comment | “e,from:activeFrom,item:linkedItem,status:&#36;('#catalog-item-status').hidden?null:&#36;('#catalog-item-status').textContent}));” |
| 398:180 | `ordered` | Code/comment | “.ids.slice(0,s.cards.length)),label+': cards follow the ordered list');assert.equal(s.count,&#96;&#36;{s.ids.length} selections” |
| 398:217 | `$` | Code/comment | “l+': cards follow the ordered list');assert.equal(s.count,&#96;&#36;{s.ids.length} selections · &#36;{s.cards.length} shown&#96;,label+'” |
| 398:246 | `$` | Code/comment | “follow the ordered list');assert.equal(s.count,&#96;&#36;{s.ids.length} selections · &#36;{s.cards.length} shown&#96;,label+': count')};” |
| 435:19 | `$` | Code/comment | “await go(&#96;?item=&#36;{encodeURIComponent(id30)}&amp;utm=x&amp;utm=y#market&#96;,real(2));s=await st();const n0=s.cards.length;assert.d” |
| 437:84 | `$` | Code/comment | “ntrols,s.replaced,s.item,s.search,s.hash],[0,0,id30,&#96;?item=&#36;{encodeURIComponent(id30)}&amp;utm=x&amp;utm=y&#96;,'#market'],'valid it” |
| 462:174 | `$` | Code/comment | “y:(await res.text())+&#96;;catalogFreshness.selectionCheckedOn=&#36;{JSON.stringify(pacificAgo(current?0:8))};catalog.splice(0,c” |
| 462:252 | `$` | Code/comment | “cificAgo(current?0:8))};catalog.splice(0,catalog.length,...&#36;{JSON.stringify(rows)}.map(p=&gt;({...catalog[0],...p,availabil” |
| 465:173 | `$` | Code/comment | “atalog-grid article')].map(e=&gt;e.dataset.productId),checked:&#36;('#avail-filter')?.checked??null,search:location.search,hash” |
| 465:274 | `$` | Code/comment | “ocation.search,hash:location.hash,history:history.length,q:&#36;('#product-search').value,brand:&#36;('#brand-filter').value,she” |
| 465:307 | `$` | Code/comment | “,history:history.length,q:&#36;('#product-search').value,brand:&#36;('#brand-filter').value,shelf:activeCategory,view:activeView” |
| 467:192 | `$` | Code/comment | “valuate(e=&gt;e.open=true);assert.equal(await b.textContent(),&#96;See all &#36;{makerRows.length} from Jayleaf&#96;);await b.click()};” |
| 494:264 | `$` | Code/comment | “selectionCheckedOn=null;catalog.splice(0,catalog.length,...&#36;{JSON.stringify(rows)}.map(p=&gt;({...catalog[0],...p,availabil” |
| 503:134 | `box` | Code/comment | “ear filters shows for any one filter, resets all five, keeps other parameters and the hash, then focuses the search box.” |
| 510:51 | `Box` | Code/comment | “await open('?q=jam');const bx=await clr.boundingBox();assert.ok(bx.height&gt;=44,'tap target '+width);assert.equal(await” |
| 512:108 | `order` | Code/comment | “f with no product in the published catalog is hidden (really invisible, out of the Tab order); All shelves always shows.” |
| 513:260 | `$` | Code/comment | “body:(await res.text())+&#96;;for(let i=catalog.length;i--;)if(&#36;{JSON.stringify(drop)}.includes(catalog[i].category))catalog” |
| 513:334 | `$` | Code/comment | “y(drop)}.includes(catalog[i].category))catalog.splice(i,1);&#36;{after}&#96;})});await (await page.context().newCDPSession(page)” |
| 527:184 | `order` | Code/comment | “es '+drop);assert.deepEqual(tabbed,ALL9.filter(k=&gt;!drop.includes(k)),'Tab visits exactly the visible shelves in order');” |
| 544:20 | `SHOP` | Code/comment | “// AV1352-01 / AVO-SHOP-CLEAN-1: the three catalog notices (Based in, seasons and deliveries, illustrations) are gone fr” |
| 544:83 | `deliveries` | Code/comment | “AN-1: the three catalog notices (Based in, seasons and deliveries, illustrations) are gone from the page; a generated pi” |
| 560:9 | `SHOP` | Code/comment | “// AVO-SHOP-CLEAN-1: the shop opens on packaged goods. Produce = fruit, vegetables, flowers; photo-product-018 (tortill” |
| 560:27 | `shop` | Code/comment | “// AVO-SHOP-CLEAN-1: the shop opens on packaged goods. Produce = fruit, vegetables, flowers; photo-product-018 (tortill” |
| 568:44 | `$` | Code/comment | “const vis=f=&gt;page.locator(&#96;[data-filter="&#36;{f}"]&#96;).isVisible();” |
| 573:76 | `$` | Code/comment | “PRODUCE)assert.match(raw,new RegExp(&#96;&lt;button data-filter="&#36;{f}" aria-pressed="false" hidden&gt;&#96;),'served page: no produce” |
| 617:40, 617:48 | `$` | Code/comment | “if(want===null)assert.equal(s,null,&#96;&#36;{name} &#36;{iso}: no status node&#96;);” |
| 618:58, 618:66, 618:96 | `$` | Code/comment | “else if(want==='')assert.ok(s&amp;&amp;s.hidden&amp;&amp;s.text==='',&#96;&#36;{name} &#36;{iso}: hidden and empty, got &#36;{JSON.stringify(s)}&#96;);” |
| 619:48, 619:56, 619:70, 619:84 | `$` | Code/comment | “else assert.ok(s&amp;&amp;!s.hidden&amp;&amp;s.text===want,&#96;&#36;{name} &#36;{iso}: want "&#36;{want}", got &#36;{JSON.stringify(s)}&#96;);” |
| 669:40 | `order` | Code/comment | “// Notice dates must be real days in order: an impossible day or a first day after the last silences the status, like” |
| 670:117, 670:139 | `$` | Code/comment | “:h=&gt;h.replace(/data-from="2026-11-26" data-until="2026-11-26"/,(f===null?'':&#96;data-from="&#36;{f}" &#96;)+&#96;data-until="&#36;{u}"&#96;)});” |

#### `storefront-mockup/catalog.js` (679)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 1:238 | `price` | Data field not rendered | “"price":” |
| 1:359 | `$` | Data field not rendered | “"evidence":” “&#36;” (value excerpt) |
| 1:387 | `pickup` | Data field not rendered | “"evidence":” “pickup” (value excerpt) |
| 1:518, 1:1277, 1:2029, 1:2780, 1:3528, 1:4287, 1:4969, 1:5731, 1:6493, 1:7255, 1:8036, 1:8792 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:9557, 1:10346, 1:11104, 1:11877, 1:12692, 1:13471, 1:14229, 1:14978, 1:15712, 1:16444, 1:17215, 1:17927 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:18646, 1:19391, 1:20142, 1:20889, 1:21675, 1:22442, 1:23250, 1:24064, 1:24846, 1:25605, 1:26369, 1:27137 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:27905, 1:28686, 1:29479, 1:30277, 1:31075, 1:31941, 1:32718, 1:33564, 1:34408, 1:35184, 1:35950, 1:36694 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:37466, 1:38228, 1:39097, 1:39947, 1:40711, 1:41453, 1:42305, 1:43084, 1:43819, 1:44536, 1:45290, 1:46030 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:46754, 1:47502, 1:48224, 1:48976, 1:49725, 1:50461, 1:51181, 1:51944, 1:52709, 1:53460, 1:54197, 1:54934 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:55679, 1:56436, 1:57219, 1:57975, 1:58785, 1:59501, 1:60446, 1:61198, 1:61971, 1:62734, 1:63509, 1:64268 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:65007, 1:65741, 1:66473, 1:67208, 1:67965, 1:68750, 1:69500, 1:70267, 1:70890, 1:71744, 1:72570, 1:73315 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:74149, 1:74976, 1:75757, 1:76470, 1:77222, 1:77832, 1:78586, 1:79344, 1:80104, 1:80865, 1:81634, 1:82398 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:83149, 1:83892, 1:84646, 1:85404, 1:86154, 1:86916, 1:87684, 1:88444, 1:89188, 1:89939, 1:90660, 1:91427 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:92174, 1:92936, 1:93692, 1:94408, 1:95137, 1:95921, 1:96663, 1:97416, 1:98193, 1:98965, 1:99746, 1:100525 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:101293, 1:102097, 1:102845, 1:103597, 1:104336, 1:105073, 1:105816, 1:106552, 1:107320, 1:108065, 1:108809, 1:109540 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:110276, 1:111022, 1:111794, 1:112551, 1:113298, 1:114060, 1:114834, 1:115589, 1:116339, 1:117097, 1:117854, 1:118609 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:119369, 1:120117, 1:120868, 1:121622, 1:122375, 1:123128, 1:123854, 1:124592, 1:125323, 1:126066, 1:126784, 1:127513 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:128227, 1:128971, 2:144, 2:514, 2:877, 2:1234, 2:1567, 2:1898, 2:2240, 2:2589, 3:142, 3:842 | `Price` | Data field not rendered | “"samplePrice":” |
| 3:1762 | `Price` | Data field not rendered | “"samplePrice":” |
| 1:597, 1:1365, 1:2117, 1:2868, 1:3617, 1:4374, 1:5058, 1:5819, 1:6581, 1:7343, 1:8126, 1:8881 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:9649, 1:10435, 1:11193, 1:11959, 1:12774, 1:13553, 1:14318, 1:15067, 1:15801, 1:16533, 1:17302, 1:18013 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:18732, 1:19480, 1:20231, 1:20976, 1:21764, 1:22531, 1:23339, 1:24151, 1:24933, 1:25692, 1:26456, 1:27224 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:27992, 1:28773, 1:29566, 1:30364, 1:31164, 1:32028, 1:32807, 1:33653, 1:34497, 1:35273, 1:36039, 1:36783 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:37555, 1:38317, 1:39186, 1:40036, 1:40799, 1:41541, 1:42393, 1:43172, 1:43901, 1:44618, 1:45372, 1:46112 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:46836, 1:47584, 1:48306, 1:49058, 1:49807, 1:50551, 1:51271, 1:52026, 1:52799, 1:53542, 1:54279, 1:55016 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:55761, 1:56518, 1:57301, 1:58057, 1:58867, 1:59583, 1:60535, 1:61281, 1:62054, 1:62821, 1:63592, 1:64351 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:65095, 1:65828, 1:66561, 1:67296, 1:68048, 1:68839, 1:69583, 1:70350, 1:70877, 1:71731, 1:72557, 1:73302 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:74136, 1:74963, 1:75744, 1:76457, 1:77209, 1:77819, 1:78573, 1:79331, 1:80091, 1:80852, 1:81621, 1:82385 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:83136, 1:83879, 1:84633, 1:85391, 1:86141, 1:86903, 1:87671, 1:88431, 1:89175, 1:89926, 1:90647, 1:91414 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:92161, 1:92923, 1:93679, 1:94395, 1:95124, 1:95908, 1:96650, 1:97403, 1:98180, 1:98952, 1:99733, 1:100512 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:101280, 1:102084, 1:102832, 1:103584, 1:104323, 1:105060, 1:105803, 1:106539, 1:107307, 1:108052, 1:108796, 1:109527 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:110263, 1:111009, 1:111781, 1:112538, 1:113285, 1:114047, 1:114821, 1:115576, 1:116326, 1:117084, 1:117841, 1:118596 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:119356, 1:120104, 1:120855, 1:121609, 1:122362, 1:123115, 1:123841, 1:124579, 1:125310, 1:126053, 1:126771, 1:127500 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:128214, 1:128958 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1:975, 1:1727, 1:2478, 1:3226, 1:3985, 1:4667, 1:5429, 1:6191, 1:6953, 1:7734, 1:8490, 1:9255 | `price` | Data field not rendered | “"price":null” |
| 1:10044, 1:10802, 1:11560, 1:12390, 1:13169, 1:13927, 1:14676, 1:15410, 1:16142, 1:16898, 1:17625, 1:18344 | `price` | Data field not rendered | “"price":null” |
| 1:19089, 1:19840, 1:20587, 1:21373, 1:22140, 1:22948, 1:23762, 1:24544, 1:25303, 1:26067, 1:26835, 1:27603 | `price` | Data field not rendered | “"price":null” |
| 1:28384, 1:29177, 1:29975, 1:30773, 1:31639, 1:32416, 1:33262, 1:34106, 1:34882, 1:35648, 1:36392, 1:37164 | `price` | Data field not rendered | “"price":null” |
| 1:37926, 1:38795, 1:39645, 1:40409, 1:41151, 1:42003, 1:42782, 1:43517, 1:44234, 1:44988, 1:45728, 1:46452 | `price` | Data field not rendered | “"price":null” |
| 1:47200, 1:47922, 1:48674, 1:49423, 1:50159, 1:50879, 1:51642, 1:52407, 1:53158, 1:53895, 1:54632, 1:55377 | `price` | Data field not rendered | “"price":null” |
| 1:56134, 1:56902, 1:57673, 1:58483, 1:59199, 1:60144, 1:60933, 1:61706, 1:62469, 1:63244, 1:64003, 1:64742 | `price` | Data field not rendered | “"price":null” |
| 1:65476, 1:66208, 1:66943, 1:67686, 1:68471, 1:69221, 1:69988, 1:70922, 1:71783, 1:72609, 1:73352, 1:74182 | `price` | Data field not rendered | “"price":null” |
| 1:75009, 1:75790, 1:76507, 1:77255, 1:78246, 1:79000, 1:79758, 1:80518, 1:81277, 1:82046, 1:82810, 1:83561 | `price` | Data field not rendered | “"price":null” |
| 1:84304, 1:85058, 1:85816, 1:86566, 1:87328, 1:88096, 1:88856, 1:89608, 1:90359, 1:91073, 1:91840, 1:92587 | `price` | Data field not rendered | “"price":null” |
| 1:93348, 1:94104, 1:94820, 1:95551, 1:96335, 1:97077, 1:97832, 1:98609, 1:99379, 1:100160, 1:100939, 1:101707 | `price` | Data field not rendered | “"price":null” |
| 1:102513, 1:103261, 1:104013, 1:104752, 1:105489, 1:106232, 1:106968, 1:107729, 1:108474, 1:109218, 1:109949, 1:110685 | `price` | Data field not rendered | “"price":null” |
| 1:111435, 1:112207, 1:112964, 1:113711, 1:114473, 1:115247, 1:116002, 1:116755, 1:117513, 1:118270, 1:119025, 1:119778 | `price` | Data field not rendered | “"price":null” |
| 1:120526, 1:121277, 1:122031, 1:122784, 1:123537, 1:124268, 1:125001, 1:125732, 1:126475, 1:127200, 1:127929, 1:128643 | `price` | Data field not rendered | “"price":null” |
| 1:129387 | `price` | Data field not rendered | “"price":null” |
| 1:1307, 1:2059, 1:2810, 1:5761, 1:6523, 1:7285, 1:40741, 1:41483, 1:42335, 1:43114, 1:65037, 1:66503 | `basket` | Data field not rendered | “"sampleUnit":” “"one basket"” |
| 1:67238, 1:71774, 1:72600, 1:111050, 1:111822, 1:112579, 1:113326, 1:114088, 1:114862, 1:115617 | `basket` | Data field not rendered | “"sampleUnit":” “"one basket"” |
| 1:72770 | `baskets` | Data field not rendered | “"evidence":” “baskets” (value excerpt) |
| 1:72825 | `baskets` | Data field not rendered | “"notes":” “baskets” (value excerpt) |
| 1:78189, 1:78943, 1:79701, 1:80461, 1:81220, 1:81989, 1:82753, 1:83504, 1:84247, 1:85001, 1:85759, 1:86509 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 1:87271, 1:88039, 1:88799, 1:89551, 1:90302, 1:91016, 1:91783, 1:92530, 1:93291, 1:94047, 1:94763, 1:95494 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 1:96278, 1:97020, 1:97775, 1:98552, 1:99322, 1:100103, 1:100882, 1:101650, 1:102456, 1:103204, 1:103956, 1:104695 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 1:105432, 1:106175, 1:106911, 1:107672, 1:108417, 1:109161, 1:109892, 1:110628, 1:111378, 1:112150, 1:112907, 1:113654 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 1:114416, 1:115190, 1:115945, 1:116698, 1:117456, 1:118213, 1:118968, 1:119721, 1:120469, 1:121220, 1:121974, 1:122727 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 1:123480, 1:124211, 1:124944, 1:125675, 1:126418, 1:127143, 1:127872, 1:128586, 1:129330 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 2:7 | `merch` | Data field not rendered | “merch” (data excerpt) |
| 2:21 | `merch` | Data field not rendered | “"id":” “"merch-tee"” |
| 2:112, 2:482, 2:845, 2:1202, 2:1535, 2:1866, 2:2208, 2:2557 | `merch` | Data field not rendered | “"category":” “"merch"” |
| 2:130, 2:500, 2:863, 2:1220, 2:1553, 2:1884, 2:2226, 2:2575 | `merch` | Data field not rendered | “"section":” “"merch"” |
| 2:199 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-tee.webp"” |
| 2:356, 2:718, 2:1073, 2:1414, 2:1752, 2:2078, 2:2428 | `Merchandise` | Data field not rendered | “"imageKind":” “"Merchandise design concept"” |
| 2:392 | `merch` | Data field not rendered | “"id":” “"merch-coast"” |
| 2:569 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-coast.webp"” |
| 2:754 | `merch` | Data field not rendered | “"id":” “"merch-sweat"” |
| 2:932 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-sweat.webp"” |
| 2:1109 | `merch` | Data field not rendered | “"id":” “"merch-mug"” |
| 2:1289 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-mug.webp"” |
| 2:1450 | `merch` | Data field not rendered | “"id":” “"merch-tote"” |
| 2:1622 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-tote.webp"” |
| 2:1788 | `merch` | Data field not rendered | “"id":” “"merch-cap"” |
| 2:1953 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-cap.webp"” |
| 2:2114 | `merch` | Data field not rendered | “"id":” “"merch-stickers"” |
| 2:2294 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-stickers.webp"” |
| 2:2464 | `merch` | Data field not rendered | “"id":” “"merch-bottle"” |
| 2:2644 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-bottle.webp"” |
| 2:2784 | `Merchandise` | Data field not rendered | “"imageKind":” “"Merchandise concept"” |
| 3:7 | `boxes` | Data field not rendered | “boxes” (data excerpt) |
| 3:21 | `box` | Data field not rendered | “"id":” “"box-small"” |
| 3:56 | `Box` | Data field not rendered | “"name":” “"Small Vegetable Box"” |
| 3:110, 3:810, 3:1730 | `boxes` | Data field not rendered | “"category":” “"boxes"” |
| 3:128, 3:828, 3:1748 | `boxes` | Data field not rendered | “"section":” “"boxes"” |
| 3:170, 3:870, 3:1790 | `box` | Data field not rendered | “"sampleUnit":” “"one box"” |
| 3:416 | `box` | Data field not rendered | “"image":” “"assets/products/box-small.webp"” |
| 3:448, 3:1229, 3:2216 | `box` | Data field not rendered | “"imageKind":” “"AI box concept"” |
| 3:719 | `box` | Data field not rendered | “"id":” “"box-medium"” |
| 3:756 | `Box` | Data field not rendered | “"name":” “"Medium Vegetable Box"” |
| 3:1196 | `box` | Data field not rendered | “"image":” “"assets/products/box-medium.webp"” |
| 3:1641 | `box` | Data field not rendered | “"id":” “"box-large"” |
| 3:1676 | `Box` | Data field not rendered | “"name":” “"Large Vegetable Box"” |
| 3:2184 | `box` | Data field not rendered | “"image":” “"assets/products/box-large.webp"” |

#### `storefront-mockup/catalog.json` (97)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 9:6 | `price` | Data field not rendered | “"price":” |
| 12:53 | `$` | Data field not rendered | “"evidence":” “&#36;” (value excerpt) |
| 12:81 | `pickup` | Data field not rendered | “"evidence":” “pickup” (value excerpt) |
| 27:6, 45:6, 63:6, 81:6, 99:6, 117:6, 135:6, 153:6, 171:6, 189:6, 207:6, 225:6 | `price` | Data field not rendered | “"price": null” |
| 243:6, 261:6, 279:6, 298:6, 316:6, 334:6, 352:6, 370:6, 388:6, 406:6, 424:6, 443:6 | `price` | Data field not rendered | “"price": null” |
| 461:6, 479:6, 497:6, 515:6, 533:6, 551:6, 569:6, 587:6, 605:6, 623:6, 641:6, 659:6 | `price` | Data field not rendered | “"price": null” |
| 677:6, 695:6, 713:6, 731:6, 749:6, 767:6, 785:6, 803:6, 821:6, 839:6, 857:6, 875:6 | `price` | Data field not rendered | “"price": null” |
| 893:6, 911:6, 929:6, 947:6, 965:6, 983:6, 1001:6, 1019:6, 1037:6, 1055:6, 1073:6, 1091:6 | `price` | Data field not rendered | “"price": null” |
| 1109:6, 1127:6, 1145:6, 1163:6, 1181:6, 1199:6, 1217:6, 1235:6, 1253:6, 1271:6, 1289:6, 1307:6 | `price` | Data field not rendered | “"price": null” |
| 1325:6, 1343:6, 1361:6, 1379:6, 1397:6, 1416:6, 1434:6, 1452:6, 1470:6, 1488:6, 1506:6, 1524:6 | `price` | Data field not rendered | “"price": null” |
| 1542:6, 1560:6, 1578:6, 1596:6, 1614:6, 1632:6, 1650:6, 1668:6, 1686:6, 1704:6 | `price` | Data field not rendered | “"price": null” |

#### `storefront-mockup/community.js` (139)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 8:93 | `$` | Code/comment | “eduled'&amp;&amp;new Date(e.startsAt)&lt;=new Date()?&#96;Today — started &#36;{new Date(e.startsAt).toLocaleTimeString('en-US',{timeZone:'” |
| 12:47, 12:69, 12:82 | `$` | Code/comment | “const metric=(label,value,link='')=&gt;&#96;&lt;div&gt;&lt;dt&gt;&#36;{esc(label)}&lt;/dt&gt;&lt;dd&gt;&#36;{esc(value)}&#36;{link}&lt;/dd&gt;&lt;/div&gt;&#96;;” |
| 15:52 | `$` | Code/comment | “const directions=a=&gt;&#96; · &lt;a class="text-link" href="&#36;{esc('https://www.google.com/maps/search/?api=1&amp;query='+encodeURICom” |
| 17:212, 17:236 | `$` | Code/comment | “return &#96;&lt;p class="hike-attendance"&gt;&lt;strong data-confirmed-guests&gt;&#36;{n}&lt;/strong&gt; confirmed &#36;{n===1?'guest':'guests'}&lt;/p&gt;&#96;}” |
| 18:52 | `$` | Code/comment | “function details(e){return &#96;&lt;dl class="hike-facts"&gt;&#36;{[['Meet',e.meetingPoint],['Meet at',e.meetTime],['Address',e.meetin” |
| 18:376, 55:203 | `$` | Code/comment | “&gt;metric(k,v,k==='Address'?directions(v):'')).join('')}&lt;/dl&gt;&#36;{set(e.accessNote)?&#96;&lt;p class="hike-access"&gt;&#36;{esc(e.accessNot” |
| 18:420 | `$` | Code/comment | “=='Address'?directions(v):'')).join('')}&lt;/dl&gt;&#36;{set(e.accessNote)?&#96;&lt;p class="hike-access"&gt;&#36;{esc(e.accessNote)}&lt;/p&gt;&#96;:''}&#96;}” |
| 19:186 | `$` | Code/comment | “col==='https:'}catch{}return &#96;&lt;p class="hike-route"&gt;Route: &#36;{esc(t.title)}&#36;{https?&#96; · &lt;a class="text-link" href="&#36;{esc(t” |
| 19:201 | `$` | Code/comment | “catch{}return &#96;&lt;p class="hike-route"&gt;Route: &#36;{esc(t.title)}&#36;{https?&#96; · &lt;a class="text-link" href="&#36;{esc(t.sourceUrl)}" t” |
| 19:240 | `$` | Code/comment | “ute: &#36;{esc(t.title)}&#36;{https?&#96; · &lt;a class="text-link" href="&#36;{esc(t.sourceUrl)}" target="_blank" rel="noopener"&gt;&#36;{esc(t.s” |
| 19:292 | `$` | Code/comment | “href="&#36;{esc(t.sourceUrl)}" target="_blank" rel="noopener"&gt;&#36;{esc(t.sourceName&#124;&#124;'Trail information')} &lt;span aria-hidden="” |
| 22:53 | `$` | Code/comment | “const icsText=s=&gt;String(s??'').replace(/[&#92;&#92;;,]/g,'&#92;&#92;&#36;&amp;').replace(/&#92;r&#92;n?&#124;&#92;n/g,'&#92;&#92;n').replace(/[&#92;x00-&#92;x1f&#92;x7f]/g,'');” |
| 25:189 | `$` | Code/comment | “DID:-//Avocado Shack//Hiking Club//EN','BEGIN:VEVENT',&#96;UID:&#36;{icsText(e.id)}@avocadoshack&#96;,&#96;DTSTAMP:&#36;{t}&#96;,&#96;DTSTART:&#36;{t}&#96;,” |
| 25:229 | `$` | Code/comment | “BEGIN:VEVENT',&#96;UID:&#36;{icsText(e.id)}@avocadoshack&#96;,&#96;DTSTAMP:&#36;{t}&#96;,&#96;DTSTART:&#36;{t}&#96;,'DURATION:PT2H',&#96;SUMMARY:&#36;{icsText(e.tit” |
| 25:244 | `$` | Code/comment | “UID:&#36;{icsText(e.id)}@avocadoshack&#96;,&#96;DTSTAMP:&#36;{t}&#96;,&#96;DTSTART:&#36;{t}&#96;,'DURATION:PT2H',&#96;SUMMARY:&#36;{icsText(e.title)}&#96;,&#96;LOCATION” |
| 25:275 | `$` | Code/comment | “ck&#96;,&#96;DTSTAMP:&#36;{t}&#96;,&#96;DTSTART:&#36;{t}&#96;,'DURATION:PT2H',&#96;SUMMARY:&#36;{icsText(e.title)}&#96;,&#96;LOCATION:&#36;{icsText(set(e.meetingAddress” |
| 25:306 | `$` | Code/comment | “}&#96;,'DURATION:PT2H',&#96;SUMMARY:&#36;{icsText(e.title)}&#96;,&#96;LOCATION:&#36;{icsText(set(e.meetingAddress)?(set(e.meetingPoint)?e.meetin” |
| 25:462 | `$` | Code/comment | “ngAddress):e.meetingPoint)}&#96;,...(d=&gt;d.length?[&#96;DESCRIPTION:&#36;{icsText(d.join('&#92;n'))}&#96;]:[])([['Meet',e.meetTime],['Bring',” |
| 25:607 | `$` | Code/comment | “ssNote]].filter(x=&gt;set(x[1])).map(x=&gt;x[0]+': '+x[1])),&#96;URL:&#36;{location.origin}/hike#&#36;{encodeURIComponent(e.id)}&#96;,'END:VEV” |
| 25:631 | `$` | Code/comment | “[1])).map(x=&gt;x[0]+': '+x[1])),&#96;URL:&#36;{location.origin}/hike#&#36;{encodeURIComponent(e.id)}&#96;,'END:VEVENT','END:VCALENDAR'].ma” |
| 27:125 | `$` | Code/comment | “xported; a zone-less one would take the visitor's zone. JS &#36; (no m flag) matches only the true end, so a final newline f” |
| 28:155 | `$` | Code/comment | “]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2})?(Z&#124;[+-][0-9]{2}:[0-9]{2})&#36;/.test(s))return null;const t=Date.parse(s);return Number.is” |
| 29:149 | `$` | Code/comment | “&amp;&amp;t&gt;Date.now()?&#96;&lt;p&gt;&lt;a class="text-link hike-ics" download="&#36;{esc(e.id)}.ics" href="&#36;{esc('data:text/calendar;charset=utf” |
| 29:173 | `$` | Code/comment | “ass="text-link hike-ics" download="&#36;{esc(e.id)}.ics" href="&#36;{esc('data:text/calendar;charset=utf-8,'+encodeURIComponent(” |
| 43:17, 43:71, 43:92 | `$` | Code/comment | “title:sample?&#96;&#36;{esc(t.title)}&lt;br&gt;&lt;em&gt;A morning on the coast.&lt;/em&gt;&#96;:&#96;&#36;{x?'Cancelled: ':''}&#36;{esc(e.title)}&#96;,” |
| 44:17 | `$` | Code/comment | “place:sample?&#96;&#36;{esc(t.place)} · Central Coast, California&#96;:set(t?.place)?esc(t.place):'',” |
| 45:131 | `$` | Code/comment | “med&lt;/p&gt;':&#96;&lt;p class="trail-invitation-date"&gt;&lt;time datetime="&#36;{esc(e.startsAt)}"&gt;&#36;{esc(day)}&lt;/time&gt; · &#36;{esc(e.walkTime)}&lt;/” |
| 45:151 | `$` | Code/comment | “trail-invitation-date"&gt;&lt;time datetime="&#36;{esc(e.startsAt)}"&gt;&#36;{esc(day)}&lt;/time&gt; · &#36;{esc(e.walkTime)}&lt;/p&gt;&#96;):&#96;&lt;p class="hike” |
| 45:172 | `$` | Code/comment | “"&gt;&lt;time datetime="&#36;{esc(e.startsAt)}"&gt;&#36;{esc(day)}&lt;/time&gt; · &#36;{esc(e.walkTime)}&lt;/p&gt;&#96;):&#96;&lt;p class="hike-date"&gt;&#36;{esc(hikeDate” |
| 45:219 | `$` | Code/comment | “etime="&#36;{esc(e.startsAt)}"&gt;&#36;{esc(day)}&lt;/time&gt; · &#36;{esc(e.walkTime)}&lt;/p&gt;&#96;):&#96;&lt;p class="hike-date"&gt;&#36;{esc(hikeDate(e))}&lt;/p&gt;&#96;,” |
| 49:178 | `$` | Code/comment | “p class="trail-map-unavailable"&gt;&lt;a class="text-link" href="&#36;{esc(guide)}" target="_blank" rel="noopener"&gt;Trail map: offi” |
| 50:116 | `$` | Code/comment | “railhead.&lt;/h3&gt;&lt;dl class="trail-logistics"&gt;&lt;div&gt;&lt;dt&gt;Meet at &#36;{esc(e.meetTime)}&lt;/dt&gt;&lt;dd&gt;&#36;{esc(e.meetingPoint)}&lt;br&gt;&lt;span&gt;&#36;{” |
| 50:143 | `$` | Code/comment | “ail-logistics"&gt;&lt;div&gt;&lt;dt&gt;Meet at &#36;{esc(e.meetTime)}&lt;/dt&gt;&lt;dd&gt;&#36;{esc(e.meetingPoint)}&lt;br&gt;&lt;span&gt;&#36;{esc(e.meetingAddress)}&lt;/spa” |
| 50:175 | `$` | Code/comment | “&#36;{esc(e.meetTime)}&lt;/dt&gt;&lt;dd&gt;&#36;{esc(e.meetingPoint)}&lt;br&gt;&lt;span&gt;&#36;{esc(e.meetingAddress)}&lt;/span&gt;&lt;/dd&gt;&lt;/div&gt;&lt;div&gt;&lt;dt&gt;On the tra” |
| 50:247 | `$` | Code/comment | “ngAddress)}&lt;/span&gt;&lt;/dd&gt;&lt;/div&gt;&lt;div&gt;&lt;dt&gt;On the trail&lt;/dt&gt;&lt;dd&gt;&#36;{esc(e.walkTime)} start · back &#36;{esc(e.returnTime.toLowerCas” |
| 50:279 | `$` | Code/comment | “v&gt;&lt;dt&gt;On the trail&lt;/dt&gt;&lt;dd&gt;&#36;{esc(e.walkTime)} start · back &#36;{esc(e.returnTime.toLowerCase())}.&lt;br&gt;&lt;span&gt;Time includes a” |
| 50:424 | `$` | Code/comment | “ong the way.&lt;/span&gt;&lt;/dd&gt;&lt;/div&gt;&lt;div&gt;&lt;dt&gt;Bring along&lt;/dt&gt;&lt;dd&gt;&#36;{esc(e.bring)}&lt;/dd&gt;&lt;/div&gt;&lt;/dl&gt;&lt;p class="trail-access"&gt;&#36;{esc(” |
| 50:479 | `$` | Code/comment | “&lt;dd&gt;&#36;{esc(e.bring)}&lt;/dd&gt;&lt;/div&gt;&lt;/dl&gt;&lt;p class="trail-access"&gt;&#36;{esc(e.accessNote)}&lt;/p&gt;&lt;a class="text-link" href="&#36;{esc(t.so” |
| 50:530 | `$` | Code/comment | “access"&gt;&#36;{esc(e.accessNote)}&lt;/p&gt;&lt;a class="text-link" href="&#36;{esc(t.sourceUrl)}" target="_blank" rel="noopener"&gt;Trail acc” |
| 51:129 | `$` | Code/comment | “H US&lt;/p&gt;&lt;h3 id="preview-rsvp-heading"&gt;I’ll come along.&lt;/h3&gt;&#36;{attendance({confirmedGuests:0})}&lt;p&gt;Tell us who’s coming and” |
| 51:612 | `$` | Code/comment | “e="partySize" aria-label="People attending, including you"&gt;&#36;{Array.from({length:6},(_,i)=&gt;&#96;&lt;option value="&#36;{i+1}"&gt;&#36;{i+1}” |
| 51:659 | `$` | Code/comment | “luding you"&gt;&#36;{Array.from({length:6},(_,i)=&gt;&#96;&lt;option value="&#36;{i+1}"&gt;&#36;{i+1} &#36;{i?'people':'person'}&lt;/option&gt;&#96;).join('')}&lt;/s” |
| 51:667 | `$` | Code/comment | “ou"&gt;&#36;{Array.from({length:6},(_,i)=&gt;&#96;&lt;option value="&#36;{i+1}"&gt;&#36;{i+1} &#36;{i?'people':'person'}&lt;/option&gt;&#96;).join('')}&lt;/select&gt;&lt;/” |
| 51:674 | `$` | Code/comment | “rray.from({length:6},(_,i)=&gt;&#96;&lt;option value="&#36;{i+1}"&gt;&#36;{i+1} &#36;{i?'people':'person'}&lt;/option&gt;&#96;).join('')}&lt;/select&gt;&lt;/div&gt;&lt;/d” |
| 51:1168 | `$` | Code/comment | “ndex="-1"&gt;&lt;/p&gt;&lt;/form&gt;&lt;/div&gt;&#96;:&#96;&lt;div class="trail-rsvp-wrap"&gt;&#36;{attendance(e)}&#36;{calendar(e)}&#36;{x?&#96;&#36;{typeof e.cancelNote==='s” |
| 51:1184 | `$` | Code/comment | “form&gt;&lt;/div&gt;&#96;:&#96;&lt;div class="trail-rsvp-wrap"&gt;&#36;{attendance(e)}&#36;{calendar(e)}&#36;{x?&#96;&#36;{typeof e.cancelNote==='string'&amp;&amp;e.cancel” |
| 51:1198 | `$` | Code/comment | “&lt;div class="trail-rsvp-wrap"&gt;&#36;{attendance(e)}&#36;{calendar(e)}&#36;{x?&#96;&#36;{typeof e.cancelNote==='string'&amp;&amp;e.cancelNote?&#96;&lt;p class” |
| 51:1203 | `$` | Code/comment | “class="trail-rsvp-wrap"&gt;&#36;{attendance(e)}&#36;{calendar(e)}&#36;{x?&#96;&#36;{typeof e.cancelNote==='string'&amp;&amp;e.cancelNote?&#96;&lt;p class="clu” |
| 51:1304 | `$` | Code/comment | “Note?&#96;&lt;p class="club-small hike-cancel-note" data-hike-id="&#36;{esc(e.id)}"&gt;&#36;{esc(e.cancelNote)}&lt;/p&gt;&#96;:''}&lt;p class="club-sma” |
| 51:1318 | `$` | Code/comment | “="club-small hike-cancel-note" data-hike-id="&#36;{esc(e.id)}"&gt;&#36;{esc(e.cancelNote)}&lt;/p&gt;&#96;:''}&lt;p class="club-small"&gt;This hike” |
| 51:1604 | `$` | Code/comment | “ft'&#124;&#124;state.kind==='nolimit')?&#96;&lt;button class="button" data-rsvp="&#36;{esc(e.id)}"&gt;RSVP to this hike ↗&lt;/button&gt;&#96;:''}&lt;/div&gt;&#96;};” |
| 55:104 | `$` | Code/comment | “the trailhead.&lt;/h3&gt;&lt;dl class="hike-facts trail-logistics"&gt;&#36;{rows.filter(x=&gt;set(x[1])).map(([k,v])=&gt;metric(k,v,k==='Addr” |
| 55:247, 55:276 | `$` | Code/comment | “tions(v):'')).join('')}&lt;/dl&gt;&#36;{set(e.accessNote)?&#96;&lt;p class="hike-access"&gt;&#36;{esc(e.accessNote)}&lt;/p&gt;&#96;:''}&#36;{route(e)}&lt;/div&gt;&#96;;” |
| 59:18, 59:48 | `$` | Code/comment | “return &#96;&lt;article&#36;{sample?'':anchor(e)} class="&#36;{sample?'':'hike-event'+(m.cancelled?' hike-cancelled':'')+' '}trail-inv” |
| 59:130 | `$` | Code/comment | “'+(m.cancelled?' hike-cancelled':'')+' '}trail-invitation" &#36;{sample?'aria-labelledby="featured-hike-title"':&#96;aria-label=” |
| 59:192 | `$` | Code/comment | “e-cancelled':'')+' '}trail-invitation" &#36;{sample?'aria-labelledby="featured-hike-title"':&#96;aria-label="&#36;{esc(e.title)}"&#96;}&gt;” |
| 60:55 | `$` | Code/comment | “&lt;div class="trail-invitation-head"&gt;&lt;p class="label"&gt;&#36;{m.label}&lt;/p&gt;&#36;{sample?'&lt;p class="sample-caption"&gt;Sample invitatio” |
| 60:69 | `$` | Code/comment | “ass="trail-invitation-head"&gt;&lt;p class="label"&gt;&#36;{m.label}&lt;/p&gt;&#36;{sample?'&lt;p class="sample-caption"&gt;Sample invitation · plans” |
| 61:28 | `$` | Code/comment | “&lt;div class="trail-feature&#36;{m.photo?'':' trail-feature-no-photo'}"&gt;” |
| 62:36, 62:46 | `$` | Code/comment | “&lt;div class="trail-feature-copy"&gt;&#36;{sample?&#96;&#36;{m.place?&#96;&lt;p class="trail-place"&gt;&#36;{m.place}&lt;/p&gt;&#96;:''}&lt;h2 id="featured-hike-” |
| 62:80 | `$` | Code/comment | “-feature-copy"&gt;&#36;{sample?&#96;&#36;{m.place?&#96;&lt;p class="trail-place"&gt;&#36;{m.place}&lt;/p&gt;&#96;:''}&lt;h2 id="featured-hike-title"&gt;&#36;{m.title}&lt;/h” |
| 62:128 | `$` | Code/comment | “ail-place"&gt;&#36;{m.place}&lt;/p&gt;&#96;:''}&lt;h2 id="featured-hike-title"&gt;&#36;{m.title}&lt;/h2&gt;&#36;{m.date}&#96;:&#96;&#36;{m.date}&lt;h2&gt;&#36;{m.title}&lt;/h2&gt;&#36;{m.pl” |
| 62:143 | `$` | Code/comment | “place}&lt;/p&gt;&#96;:''}&lt;h2 id="featured-hike-title"&gt;&#36;{m.title}&lt;/h2&gt;&#36;{m.date}&#96;:&#96;&#36;{m.date}&lt;h2&gt;&#36;{m.title}&lt;/h2&gt;&#36;{m.place?&#96;&lt;p class="” |
| 62:155 | `$` | Code/comment | “''}&lt;h2 id="featured-hike-title"&gt;&#36;{m.title}&lt;/h2&gt;&#36;{m.date}&#96;:&#96;&#36;{m.date}&lt;h2&gt;&#36;{m.title}&lt;/h2&gt;&#36;{m.place?&#96;&lt;p class="trail-place"” |
| 62:168 | `$` | Code/comment | “atured-hike-title"&gt;&#36;{m.title}&lt;/h2&gt;&#36;{m.date}&#96;:&#96;&#36;{m.date}&lt;h2&gt;&#36;{m.title}&lt;/h2&gt;&#36;{m.place?&#96;&lt;p class="trail-place"&gt;&#36;{m.place}&lt;/” |
| 62:183 | `$` | Code/comment | “le"&gt;&#36;{m.title}&lt;/h2&gt;&#36;{m.date}&#96;:&#96;&#36;{m.date}&lt;h2&gt;&#36;{m.title}&lt;/h2&gt;&#36;{m.place?&#96;&lt;p class="trail-place"&gt;&#36;{m.place}&lt;/p&gt;&#96;:''}&#96;}&lt;p&gt;&#36;{e” |
| 62:217 | `$` | Code/comment | “.date}&lt;h2&gt;&#36;{m.title}&lt;/h2&gt;&#36;{m.place?&#96;&lt;p class="trail-place"&gt;&#36;{m.place}&lt;/p&gt;&#96;:''}&#96;}&lt;p&gt;&#36;{esc(m.description)}&lt;/p&gt;&lt;p class="tr” |
| 62:241 | `$` | Code/comment | “&gt;&#36;{m.place?&#96;&lt;p class="trail-place"&gt;&#36;{m.place}&lt;/p&gt;&#96;:''}&#96;}&lt;p&gt;&#36;{esc(m.description)}&lt;/p&gt;&lt;p class="trail-host-note"&gt;A communi” |
| 63:4 | `$` | Code/comment | “&#36;{m.photo}” |
| 65:57 | `$` | Code/comment | “&lt;dl class="trail-stats" aria-label="Hike at a glance"&gt;&#36;{m.stats}&lt;/dl&gt;” |
| 66:3, 66:13 | `$` | Code/comment | “&#36;{m.spots}&#36;{m.map}” |
| 68:4 | `$` | Code/comment | “&#36;{m.plan}” |
| 69:4 | `$` | Code/comment | “&#36;{m.join}” |
| 76:100, 88:112 | `$` | Code/comment | “ntry"&gt;&lt;div class="trail-journal-marker" aria-hidden="true"&gt;&#36;{index===0?'↗':'≈'}&lt;/div&gt;&lt;div class="trail-journal-copy"&gt;&lt;p” |
| 76:181 | `$` | Code/comment | “div&gt;&lt;div class="trail-journal-copy"&gt;&lt;p class="trail-place"&gt;&#36;{esc(t.place)} &lt;span&gt;· &#36;{esc(item.dateLabel)}&lt;/span&gt;&lt;/p&gt;&lt;h3&gt;” |
| 76:205 | `$` | Code/comment | “urnal-copy"&gt;&lt;p class="trail-place"&gt;&#36;{esc(t.place)} &lt;span&gt;· &#36;{esc(item.dateLabel)}&lt;/span&gt;&lt;/p&gt;&lt;h3&gt;&#36;{esc(t.title)}&lt;/h3&gt;&lt;p&gt;&#36;” |
| 76:242 | `$` | Code/comment | “esc(t.place)} &lt;span&gt;· &#36;{esc(item.dateLabel)}&lt;/span&gt;&lt;/p&gt;&lt;h3&gt;&#36;{esc(t.title)}&lt;/h3&gt;&lt;p&gt;&#36;{esc(t.description)}&lt;/p&gt;&lt;dl class="tr” |
| 76:265 | `$` | Code/comment | “{esc(item.dateLabel)}&lt;/span&gt;&lt;/p&gt;&lt;h3&gt;&#36;{esc(t.title)}&lt;/h3&gt;&lt;p&gt;&#36;{esc(t.description)}&lt;/p&gt;&lt;dl class="trail-journal-stats"&gt;&#36;{me” |
| 76:322 | `$` | Code/comment | “p&gt;&#36;{esc(t.description)}&lt;/p&gt;&lt;dl class="trail-journal-stats"&gt;&#36;{metric('Distance',t.distance)}&#36;{metric('Difficulty',t.diffi” |
| 76:354 | `$` | Code/comment | “lass="trail-journal-stats"&gt;&#36;{metric('Distance',t.distance)}&#36;{metric('Difficulty',t.difficulty)}&#36;{metric(t.elevationLabel” |
| 76:390 | `$` | Code/comment | “'Distance',t.distance)}&#36;{metric('Difficulty',t.difficulty)}&#36;{metric(t.elevationLabel,t.elevation)}&#36;{metric('Allow',t.dur” |
| 76:429 | `$` | Code/comment | “ulty',t.difficulty)}&#36;{metric(t.elevationLabel,t.elevation)}&#36;{metric('Allow',t.duration)}&lt;/dl&gt;&lt;a class="text-link" href="” |
| 76:490 | `$` | Code/comment | “metric('Allow',t.duration)}&lt;/dl&gt;&lt;a class="text-link" href="&#36;{esc(t.sourceUrl)}" target="_blank" rel="noopener"&gt;Explore t” |
| 87:26, 87:58, 87:78 | `$` | Code/comment | “const when=month?&#96;&lt;span&gt;&#36;{place?'· ':''}&lt;time datetime="&#36;{esc(e.startsAt)}"&gt;&#36;{esc(month)}&lt;/time&gt;&lt;/span&gt;&#96;:'';” |
| 88:18 | `$` | Code/comment | “return &#96;&lt;article&#36;{anchor(e)} class="trail-journal-entry"&gt;&lt;div class="trail-journal-marker" aria-hidden="true"&gt;&#36;{index==” |
| 88:193 | `$` | Code/comment | “div&gt;&lt;div class="trail-journal-copy"&gt;&lt;p class="trail-place"&gt;&#36;{place?esc(place)+' ':''}&#36;{when}&lt;/p&gt;&lt;h3&gt;&#36;{esc(e.title)}&lt;/h3&gt;” |
| 88:219 | `$` | Code/comment | “nal-copy"&gt;&lt;p class="trail-place"&gt;&#36;{place?esc(place)+' ':''}&#36;{when}&lt;/p&gt;&lt;h3&gt;&#36;{esc(e.title)}&lt;/h3&gt;&lt;p class="trail-journal-re” |
| 88:234 | `$` | Code/comment | “ass="trail-place"&gt;&#36;{place?esc(place)+' ':''}&#36;{when}&lt;/p&gt;&lt;h3&gt;&#36;{esc(e.title)}&lt;/h3&gt;&lt;p class="trail-journal-recap"&gt;&#36;{esc(e.re” |
| 88:285 | `$` | Code/comment | “&lt;/p&gt;&lt;h3&gt;&#36;{esc(e.title)}&lt;/h3&gt;&lt;p class="trail-journal-recap"&gt;&#36;{esc(e.recap&#124;&#124;e.description&#124;&#124;'')}&lt;/p&gt;&#36;{stats?&#96;&lt;dl class="tra” |
| 88:323 | `$` | Code/comment | “trail-journal-recap"&gt;&#36;{esc(e.recap&#124;&#124;e.description&#124;&#124;'')}&lt;/p&gt;&#36;{stats?&#96;&lt;dl class="trail-journal-stats"&gt;&#36;{stats}&lt;/dl&gt;&#96;:''}&#36;{” |
| 88:364 | `$` | Code/comment | “cription&#124;&#124;'')}&lt;/p&gt;&#36;{stats?&#96;&lt;dl class="trail-journal-stats"&gt;&#36;{stats}&lt;/dl&gt;&#96;:''}&#36;{https?&#96;&lt;a class="text-link" href="&#36;{esc(t” |
| 88:382 | `$` | Code/comment | “&#36;{stats?&#96;&lt;dl class="trail-journal-stats"&gt;&#36;{stats}&lt;/dl&gt;&#96;:''}&#36;{https?&#96;&lt;a class="text-link" href="&#36;{esc(t.sourceUrl)}" targ” |
| 88:418 | `$` | Code/comment | “ats"&gt;&#36;{stats}&lt;/dl&gt;&#96;:''}&#36;{https?&#96;&lt;a class="text-link" href="&#36;{esc(t.sourceUrl)}" target="_blank" rel="noopener"&gt;Explore t” |
| 104:54 | `$` | Code/comment | “if(c===null)return {kind:'unknown',text:&#96;Limited to &#36;{cap} people · availability unconfirmed; ask at the Shack&#96;};” |
| 106:28, 106:37 | `$` | Code/comment | “return {kind:'left',text:&#96;&#36;{c} spot&#36;{c===1?'':'s'} left&#96;};” |
| 108:43, 108:70 | `$` | Code/comment | “const spotsMarkup=s=&gt;&#96;&lt;p class="club-small&#36;{s.full?' hike-full':''}"&gt;&#36;{esc(s.text)}&lt;/p&gt;&#96;;” |
| 114:143 | `$` | Code/comment | “(typeof id!=='string'&#124;&#124;id===''&#124;&#124;staticIds.has(id)&#124;&#124;usedIds.has(id))return '';usedIds.add(id);return &#96; id="&#36;{esc(id)}"&#96;};” |
| 125:2 | `$` | Code/comment | “&#36;('#upcoming-hikes').innerHTML=next.length?next.map(e=&gt;{const x=e.status==='cancelled',t=started(e),trail=trailById(e.t” |
| 130:2 | `$` | Code/comment | “&#36;('#history-context').textContent=samplePast?'Sample archive · these outings are not confirmed club history.':'Places a” |
| 131:2 | `$` | Code/comment | “&#36;('#past-hikes').classList.toggle('trail-journal',!!(past.length&#124;&#124;samplePast));” |
| 132:2 | `$` | Code/comment | “&#36;('#past-hikes').innerHTML=past.length?past.map(pastEntry).join(''):samplePast?preview.past.map(sampleHistory).join('')” |
| 135:13 | `$` | Code/comment | “const form=&#36;('#preview-hike-rsvp');” |
| 161:8 | `$` | Code/comment | “}catch{&#36;('#upcoming-hikes').innerHTML='&lt;p&gt;The hike calendar isn’t available right now. Please try again shortly.&lt;/p&gt;';&#36;(” |
| 161:119 | `$` | Code/comment | “isn’t available right now. Please try again shortly.&lt;/p&gt;';&#36;('#past-hikes').innerHTML='&lt;p class="club-small"&gt;Past outing” |
| 173:4, 173:23 | `$` | Code/comment | “if(&#36;('#hike-updates'))&#36;('#hike-updates').onsubmit=e=&gt;{e.preventDefault();send(e.currentTarget,'/api/community/subscripti” |
| 174:4, 174:31 | `$` | Code/comment | “if(&#36;('#community-newsletter'))&#36;('#community-newsletter').onsubmit=e=&gt;{e.preventDefault();send(e.currentTarget,'/api/comm” |
| 177:20, 177:47 | `$` | Code/comment | “for(const form of [&#36;('#community-newsletter'),&#36;('#hike-updates')])if(form)liveService().then(ok=&gt;{if(ok)return;form.quer” |
| 178:4, 178:25 | `$` | Code/comment | “if(&#36;('#upcoming-hikes'))&#36;('#upcoming-hikes').onclick=e=&gt;{const button=e.target.closest('[data-rsvp]');if(!button)return;” |
| 178:280 | `$` | Code/comment | “NORTH COAST HIKING CLUB&lt;/p&gt;&lt;h2&gt;Join the next hike.&lt;/h2&gt;&lt;h3&gt;&#36;{esc(event.title)}&lt;/h3&gt;&lt;p&gt;&#36;{esc(dateLabel(event))}&lt;/p&gt;&#36;{deta” |
| 178:307 | `$` | Code/comment | “&lt;h2&gt;Join the next hike.&lt;/h2&gt;&lt;h3&gt;&#36;{esc(event.title)}&lt;/h3&gt;&lt;p&gt;&#36;{esc(dateLabel(event))}&lt;/p&gt;&#36;{details(event)}&lt;form id="hike-r” |
| 178:335 | `$` | Code/comment | “&lt;h3&gt;&#36;{esc(event.title)}&lt;/h3&gt;&lt;p&gt;&#36;{esc(dateLabel(event))}&lt;/p&gt;&#36;{details(event)}&lt;form id="hike-rsvp"&gt;&lt;label for="rsvp-name"&gt;” |
| 178:724 | `$` | Code/comment | “luding you&lt;/label&gt;&lt;select id="rsvp-party" name="partySize"&gt;&#36;{Array.from({length:Math.min(6,event.remaining??6)},(_,i)=&gt;&#96;” |
| 178:800 | `$` | Code/comment | “gth:Math.min(6,event.remaining??6)},(_,i)=&gt;&#96;&lt;option value="&#36;{i+1}"&gt;&#36;{i+1}&lt;/option&gt;&#96;).join('')}&lt;/select&gt;&lt;p class="setup-n” |
| 178:808 | `$` | Code/comment | “.min(6,event.remaining??6)},(_,i)=&gt;&#96;&lt;option value="&#36;{i+1}"&gt;&#36;{i+1}&lt;/option&gt;&#96;).join('')}&lt;/select&gt;&lt;p class="setup-note"&gt;You” |
| 178:1046 | `$` | Code/comment | “/button&gt;&lt;p class="form-status" role="status"&gt;&lt;/p&gt;&lt;/form&gt;&#96;);&#36;('#hike-rsvp').onsubmit=async e=&gt;{e.preventDefault();const f” |
| 184:74 | `$` | Code/comment | “const at=new Date(e.startsAt),tz=e.timezone&#124;&#124;'America/Los_Angeles',line=&#36;('#next-hike-line');” |
| 186:78 | `$` | Code/comment | “a class="text-link" href="/hike#upcoming-hikes"&gt;Next hike: &#36;{esc(when)} - &#36;{esc(e.title)}&lt;/a&gt;&#96;;line.hidden=false}catch{}” |
| 186:93 | `$` | Code/comment | “class="text-link" href="/hike#upcoming-hikes"&gt;Next hike: &#36;{esc(when)} - &#36;{esc(e.title)}&lt;/a&gt;&#96;;line.hidden=false}catch{}}” |
| 187:4, 187:40 | `$` | Code/comment | “if(&#36;('#upcoming-hikes'))load();else if(&#36;('#next-hike-line'))loadNext();” |

#### `storefront-mockup/completion-image-log.json` (22)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 624:12 | `merch` | Data field not rendered | “"id":” “"merch-bottle"” |
| 642:12 | `box` | Data field not rendered | “"id":” “"box-small"” |
| 649:90, 661:91, 673:90 | `Box` | Data field not rendered | “"prompt":” “Box” (value excerpt) |
| 649:159, 661:160, 673:159 | `shop` | Data field not rendered | “"prompt":” “shop” (value excerpt) |
| 649:211, 649:423, 649:574, 661:212, 661:501, 661:652, 673:211, 673:566, 673:717 | `box` | Data field not rendered | “"prompt":” “box” (value excerpt) |
| 649:655, 661:733, 673:798 | `price` | Data field not rendered | “"prompt":” “price” (value excerpt) |
| 654:12 | `box` | Data field not rendered | “"id":” “"box-medium"” |
| 666:12 | `box` | Data field not rendered | “"id":” “"box-large"” |

#### `storefront-mockup/completion-new-products.json` (287)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 7:17, 26:17, 45:17, 64:17, 83:17, 102:17, 121:17, 140:17, 159:17, 178:17, 197:17, 216:17 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 235:17, 254:17, 273:17, 292:17, 311:17, 330:17, 349:17, 368:17, 387:17, 406:17, 425:17, 444:17 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 463:17, 482:17, 501:17, 520:17, 539:17, 558:17, 577:17, 596:17, 615:17, 634:17, 653:17, 672:17 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 691:17, 710:17, 729:17, 748:17, 767:17, 786:17, 805:17, 824:17, 843:17, 862:17, 881:17, 900:17 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 919:17, 938:17, 957:17, 976:17, 995:17, 1014:17, 1033:17, 1052:17, 1071:17, 1090:17, 1109:17, 1128:17 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1147:17, 1166:17, 1185:17, 1204:17, 1223:17, 1242:17, 1261:17, 1280:17, 1299:17, 1318:17 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 8:12, 27:12, 46:12, 65:12, 84:12, 103:12, 122:12, 141:12, 160:12, 179:12, 198:12, 217:12 | `Price` | Data field not rendered | “"samplePrice":” |
| 236:12, 255:12, 274:12, 293:12, 312:12, 331:12, 350:12, 369:12, 388:12, 407:12, 426:12, 445:12 | `Price` | Data field not rendered | “"samplePrice":” |
| 464:12, 483:12, 502:12, 521:12, 540:12, 559:12, 578:12, 597:12, 616:12, 635:12, 654:12, 673:12 | `Price` | Data field not rendered | “"samplePrice":” |
| 692:12, 711:12, 730:12, 749:12, 768:12, 787:12, 806:12, 825:12, 844:12, 863:12, 882:12, 901:12 | `Price` | Data field not rendered | “"samplePrice":” |
| 920:12, 939:12, 958:12, 977:12, 996:12, 1015:12, 1034:12, 1053:12, 1072:12, 1091:12, 1110:12, 1129:12 | `Price` | Data field not rendered | “"samplePrice":” |
| 1148:12, 1167:12, 1186:12, 1205:12, 1224:12, 1243:12, 1262:12, 1281:12, 1300:12, 1319:12 | `Price` | Data field not rendered | “"samplePrice":” |
| 18:30, 37:30, 56:30, 75:30, 94:30, 113:30, 132:30, 151:30, 170:30, 189:30, 208:30, 227:30 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 246:30, 265:30, 284:30, 303:30, 322:30, 341:30, 360:30, 379:30, 398:30, 417:30, 436:30, 455:30 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 474:30, 493:30, 512:30, 531:30, 550:30, 569:30, 588:30, 607:30, 626:30, 645:30, 664:30, 683:30 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 702:30, 721:30, 740:30, 759:30, 778:30, 797:30, 816:30, 835:30, 854:30, 873:30, 892:30, 911:30 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 930:30, 949:30, 968:30, 987:30, 1006:30, 1025:30, 1044:30, 1063:30, 1082:30, 1101:30, 1120:30, 1139:30 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 1158:30, 1177:30, 1196:30, 1215:30, 1234:30, 1253:30, 1272:30, 1291:30, 1310:30, 1329:30 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 19:6, 38:6, 57:6, 76:6, 95:6, 114:6, 133:6, 152:6, 171:6, 190:6, 209:6, 228:6 | `price` | Data field not rendered | “"price": null” |
| 247:6, 266:6, 285:6, 304:6, 323:6, 342:6, 361:6, 380:6, 399:6, 418:6, 437:6, 456:6 | `price` | Data field not rendered | “"price": null” |
| 475:6, 494:6, 513:6, 532:6, 551:6, 570:6, 589:6, 608:6, 627:6, 646:6, 665:6, 684:6 | `price` | Data field not rendered | “"price": null” |
| 703:6, 722:6, 741:6, 760:6, 779:6, 798:6, 817:6, 836:6, 855:6, 874:6, 893:6, 912:6 | `price` | Data field not rendered | “"price": null” |
| 931:6, 950:6, 969:6, 988:6, 1007:6, 1026:6, 1045:6, 1064:6, 1083:6, 1102:6, 1121:6, 1140:6 | `price` | Data field not rendered | “"price": null” |
| 1159:6, 1178:6, 1197:6, 1216:6, 1235:6, 1254:6, 1273:6, 1292:6, 1311:6, 1330:6 | `price` | Data field not rendered | “"price": null” |
| 864:24, 883:24, 902:24, 921:24, 940:24, 959:24, 978:24 | `basket` | Data field not rendered | “"sampleUnit":” “"one basket"” |

#### `storefront-mockup/expanded-image-log.json` (10)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 4:538, 9:524, 14:482, 19:519, 24:512, 29:500, 34:490, 39:470, 44:482 | `prices` | Data field not rendered | “"prompt":” “prices” (value excerpt) |
| 14:161 | `baskets` | Data field not rendered | “"prompt":” “baskets” (value excerpt) |

#### `storefront-mockup/held-products.json` (7)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 12:8, 45:8 | `price` | Data field not rendered | “"price": null” |
| 22:14, 34:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 25:19, 33:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 44:32 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |

#### `storefront-mockup/image-generation-log.json` (246)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 7:399, 13:403, 19:409, 25:406, 31:417, 37:408, 43:405, 49:416, 55:405, 61:405, 67:400, 73:404 | `price` | Data field not rendered | “"prompt":” “price” (value excerpt) |
| 79:401, 85:398, 91:404, 97:400, 103:404, 109:403, 115:402, 121:410, 127:409, 133:401, 139:395, 145:400 | `price` | Data field not rendered | “"prompt":” “price” (value excerpt) |
| 151:400, 157:393, 163:401, 169:410, 175:391, 181:402, 187:407, 193:413, 199:401, 205:406, 211:401, 217:407 | `price` | Data field not rendered | “"prompt":” “price” (value excerpt) |
| 223:407, 229:407, 235:404, 241:416, 247:407, 253:422, 259:406, 265:424, 271:420, 277:412, 283:414, 289:432 | `price` | Data field not rendered | “"prompt":” “price” (value excerpt) |
| 295:418, 301:423, 307:421, 313:426, 319:410, 325:399, 331:409, 337:408, 343:408, 349:411, 355:405, 361:413 | `price` | Data field not rendered | “"prompt":” “price” (value excerpt) |
| 367:403, 373:405, 379:412, 385:402, 391:405, 397:419, 403:403, 409:412, 415:404, 421:413, 427:406, 433:403 | `price` | Data field not rendered | “"prompt":” “price” (value excerpt) |
| 439:405, 445:405, 451:404, 457:419, 463:405, 469:407, 475:407, 481:404, 487:402, 493:388, 499:424, 505:414 | `price` | Data field not rendered | “"prompt":” “price” (value excerpt) |
| 511:413, 517:421, 523:409, 529:408, 535:419, 541:410, 547:412, 553:413, 559:423, 565:411 | `price` | Data field not rendered | “"prompt":” “price” (value excerpt) |
| 7:890, 13:894, 19:900, 25:897, 31:908, 37:899, 43:896, 49:907, 55:896, 61:896, 67:891, 73:895 | `pricing` | Data field not rendered | “"prompt":” “pricing” (value excerpt) |
| 79:892, 85:889, 91:895, 97:891, 103:895, 109:894, 115:893, 121:901, 127:900, 133:892, 139:886, 145:891 | `pricing` | Data field not rendered | “"prompt":” “pricing” (value excerpt) |
| 151:891, 157:884, 163:892, 169:901, 175:882, 181:893, 187:898, 193:904, 199:892, 205:897, 211:892, 217:898 | `pricing` | Data field not rendered | “"prompt":” “pricing” (value excerpt) |
| 223:898, 229:898, 235:895, 241:907, 247:898, 253:913, 259:897, 265:915, 271:911, 277:903, 283:905, 289:923 | `pricing` | Data field not rendered | “"prompt":” “pricing” (value excerpt) |
| 295:909, 301:914, 307:912, 313:917, 319:901, 325:890, 331:900, 337:899, 343:899, 349:902, 355:896, 361:904 | `pricing` | Data field not rendered | “"prompt":” “pricing” (value excerpt) |
| 367:894, 373:896, 379:903, 385:893, 391:896, 397:910, 403:894, 409:903, 415:895, 421:904, 427:897, 433:894 | `pricing` | Data field not rendered | “"prompt":” “pricing” (value excerpt) |
| 439:896, 445:896, 451:895, 457:910, 463:896, 469:898, 475:898, 481:895, 487:893, 493:879, 499:915, 505:905 | `pricing` | Data field not rendered | “"prompt":” “pricing” (value excerpt) |
| 511:904, 517:912, 523:900, 529:899, 535:910, 541:901, 547:903, 553:904, 559:914, 565:902 | `pricing` | Data field not rendered | “"prompt":” “pricing” (value excerpt) |
| 569:4 | `merch` | Data field not rendered | “merch” (field name excerpt) |
| 569:12 | `Boxes` | Data field not rendered | “Boxes” (field name excerpt) |
| 571:14 | `merch` | Data field not rendered | “"id":” “"merch-tee"” |
| 572:133, 581:133, 590:133, 599:133, 608:133, 617:133, 648:133 | `merchandise` | Data field not rendered | “"prompt":” “merchandise” (value excerpt) |
| 572:669, 581:661, 590:649, 599:656, 608:656, 617:646, 626:654, 637:707, 648:661, 657:737 | `prices` | Data field not rendered | “"prompt":” “prices” (value excerpt) |
| 580:14 | `merch` | Data field not rendered | “"id":” “"merch-mug"” |
| 589:14 | `merch` | Data field not rendered | “"id":” “"merch-sweat"” |
| 598:14 | `merch` | Data field not rendered | “"id":” “"merch-coast"” |
| 607:14 | `merch` | Data field not rendered | “"id":” “"merch-tote"” |
| 616:14 | `merch` | Data field not rendered | “"id":” “"merch-cap"” |
| 625:14 | `box` | Data field not rendered | “"id":” “"box-small"” |
| 626:172, 637:173, 657:172 | `Box` | Data field not rendered | “"prompt":” “Box” (value excerpt) |
| 626:211, 626:332, 626:455, 626:576, 637:212, 637:333, 637:508, 637:629, 657:211, 657:332, 657:538, 657:659 | `box` | Data field not rendered | “"prompt":” “box” (value excerpt) |
| 690:221 | `box` | Data field not rendered | “"prompt":” “box” (value excerpt) |
| 626:373, 637:374, 637:394, 657:394, 690:136, 690:272 | `basket` | Data field not rendered | “"prompt":” “basket” (value excerpt) |
| 636:14 | `box` | Data field not rendered | “"id":” “"box-medium"” |
| 647:14 | `merch` | Data field not rendered | “"id":” “"merch-stickers"” |
| 656:14 | `box` | Data field not rendered | “"id":” “"box-large"” |
| 657:373 | `baskets` | Data field not rendered | “"prompt":” “baskets” (value excerpt) |
| 676:79, 683:79, 690:79 | `shop` | Data field not rendered | “"prompt":” “shop” (value excerpt) |
| 689:50, 689:186 | `basket` | Data field not rendered | “basket” (value excerpt) |
| 689:135 | `box` | Data field not rendered | “box” (value excerpt) |

#### `storefront-mockup/index.html` (2)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 27:150 | `buyer` | Visitor-visible text | “a produce buyer’s curiosity and long-standing grower relationships to the Shack.” |
| 32:126 | `shop` | Attribute | “&lt;script src="shop.js"&gt;&lt;/script&gt;” |

#### `storefront-mockup/new-products.json` (31)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 13:17, 35:17, 57:17, 79:17, 101:17, 123:17, 145:17, 167:17, 189:17 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 14:12, 36:12, 58:12, 80:12, 102:12, 124:12, 146:12, 168:12, 190:12 | `Price` | Data field not rendered | “"samplePrice":” |
| 16:6, 38:6, 60:6, 82:6, 104:6, 126:6, 148:6, 170:6, 192:6 | `price` | Data field not rendered | “"price": null” |
| 37:24, 59:24 | `basket` | Data field not rendered | “"sampleUnit":” “"one basket"” |
| 64:46 | `baskets` | Data field not rendered | “"evidence":” “baskets” (value excerpt) |
| 65:43 | `baskets` | Data field not rendered | “"notes":” “baskets” (value excerpt) |

#### `storefront-mockup/qa-env.cjs` (10)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 28:31 | `$` | Code/comment | “const port=u&amp;&amp;(u.port&#124;&#124;/:&#92;d+&#36;/.test((/^http:&#92;/&#92;/([^/?#]*)/i.exec(raw)&#124;&#124;[])[1]&#124;&#124;''));” |
| 31:39 | `$` | Code/comment | “base=u.origin+u.pathname.replace(/&#92;/&#36;/,'');” |
| 45:124 | `price` | Code/comment | “p of document.querySelectorAll('#catalog-grid article[data-product-id] .food-identity &gt; p.product-meta.product-price')){” |
| 47:10 | `price` | Code/comment | “const price=catalog.find(record=&gt;record.id===id)?.sellingPrice;” |
| 47:61 | `Price` | Code/comment | “const price=catalog.find(record=&gt;record.id===id)?.sellingPrice;” |
| 48:14, 48:92 | `price` | Code/comment | “if(typeof price!=='string'&#124;&#124;!/^(?:0&#124;[1-9][0-9]{0,5})&#92;.[0-9]{2}(?: per lb&#124; each)?&#36;/.test(price)&#124;&#124;” |
| 48:84 | `$` | Code/comment | “if(typeof price!=='string'&#124;&#124;!/^(?:0&#124;[1-9][0-9]{0,5})&#92;.[0-9]{2}(?: per lb&#124; each)?&#36;/.test(price)&#124;&#124;” |
| 49:89 | `$` | Code/comment | “p.childNodes.length!==1&#124;&#124;p.firstChild.nodeType!==Node.TEXT_NODE&#124;&#124;p.textContent!=='&#36;'+price)continue;” |
| 49:92 | `price` | Code/comment | “p.childNodes.length!==1&#124;&#124;p.firstChild.nodeType!==Node.TEXT_NODE&#124;&#124;p.textContent!=='&#36;'+price)continue;” |

#### `storefront-mockup/script.js` (12)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 2:7 | `$` | Code/comment | “const &#36;=s=&gt;document.querySelector(s);” |
| 3:14 | `$` | Code/comment | “const dialog=&#36;('#dialog');” |
| 5:2 | `$` | Code/comment | “&#36;('#dialog-content').innerHTML=html;” |
| 6:16 | `$` | Code/comment | “const heading=&#36;('#dialog-content h2');” |
| 11:1 | `$` | Code/comment | “&#36;('.close').onclick=()=&gt;dialog.close();” |
| 12:132 | `box` | Code/comment | “s either its backdrop or its own padding/border; only a pointer outside the dialog's box (measured now) is the backdrop.” |
| 14:1 | `$` | Code/comment | “&#36;('[data-policy]').onclick=()=&gt;show('&lt;h2&gt;Your privacy matters.&lt;/h2&gt;&lt;p&gt;This site doesn’t use cookies, analytics or advert” |
| 15:161 | `box` | Code/comment | “rop is a selection, not a dismissal; only a press that began outside the dialog box, released outside it too, closes it.” |
| 17:14 | `Box` | Code/comment | “const outsideBox=e=&gt;{const r=dialog.getBoundingClientRect();return e.clientX&lt;r.left&#124;&#124;e.clientX&gt;r.right&#124;&#124;e.clientY&lt;r.top&#124;” |
| 18:108 | `Box` | Code/comment | “dialog.addEventListener('pointerdown',e=&gt;{downOutside=e.isPrimary&amp;&amp;e.button===0&amp;&amp;e.target===dialog&amp;&amp;outsideBox(e)});” |
| 21:109 | `Box` | Code/comment | “entListener('click',e=&gt;{const ok=downOutside;downOutside=false;if(e.target===dialog&amp;&amp;ok&amp;&amp;outsideBox(e))dialog.close()});” |
| 31:110 | `$` | Code/comment | “const DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],DATE=/^&#92;d{4}-&#92;d{2}-&#92;d{2}&#36;/;” |

#### `storefront-mockup/scroll-QA.json` (1)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 7:4 | `cart` | Data field not rendered | “"cartPreserved":” |

#### `storefront-mockup/shop-data.json` (679)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 10:8 | `price` | Data field not rendered | “"price":” |
| 13:55 | `$` | Data field not rendered | “"evidence":” “&#36;” (value excerpt) |
| 13:83 | `pickup` | Data field not rendered | “"evidence":” “pickup” (value excerpt) |
| 20:14, 46:14, 72:14, 98:14, 124:14, 150:14, 176:14, 202:14, 228:14, 254:14, 280:14, 306:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 332:14, 358:14, 384:14, 411:14, 437:14, 463:14, 489:14, 515:14, 541:14, 567:14, 594:14, 620:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 646:14, 672:14, 698:14, 724:14, 750:14, 776:14, 803:14, 830:14, 856:14, 882:14, 908:14, 934:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 960:14, 986:14, 1012:14, 1038:14, 1064:14, 1091:14, 1117:14, 1144:14, 1171:14, 1197:14, 1223:14, 1249:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 1275:14, 1301:14, 1327:14, 1353:14, 1379:14, 1405:14, 1432:14, 1458:14, 1484:14, 1510:14, 1536:14, 1562:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 1588:14, 1614:14, 1640:14, 1666:14, 1692:14, 1718:14, 1744:14, 1770:14, 1796:14, 1822:14, 1848:14, 1874:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 1900:14, 1926:14, 1953:14, 1979:14, 2005:14, 2031:14, 2058:14, 2084:14, 2110:14, 2136:14, 2162:14, 2188:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 2214:14, 2240:14, 2266:14, 2292:14, 2318:14, 2344:14, 2370:14, 2396:14, 2417:14, 2442:14, 2467:14, 2492:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 2517:14, 2542:14, 2567:14, 2592:14, 2617:14, 2636:14, 2658:14, 2680:14, 2702:14, 2724:14, 2746:14, 2768:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 2790:14, 2812:14, 2834:14, 2856:14, 2878:14, 2900:14, 2922:14, 2944:14, 2966:14, 2988:14, 3010:14, 3032:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 3054:14, 3076:14, 3098:14, 3120:14, 3142:14, 3164:14, 3186:14, 3208:14, 3230:14, 3252:14, 3274:14, 3296:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 3318:14, 3340:14, 3362:14, 3384:14, 3406:14, 3428:14, 3450:14, 3472:14, 3494:14, 3516:14, 3538:14, 3560:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 3582:14, 3604:14, 3626:14, 3648:14, 3670:14, 3692:14, 3714:14, 3736:14, 3758:14, 3780:14, 3802:14, 3824:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 3846:14, 3868:14, 3890:14, 3912:14, 3934:14, 3956:14, 3978:14, 4000:14, 4022:14, 4044:14, 4066:14, 4088:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 4110:14, 4132:14, 4156:14, 4175:14, 4194:14, 4213:14, 4226:14, 4239:14, 4252:14, 4265:14, 4280:14, 4321:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 4377:14 | `Price` | Data field not rendered | “"samplePrice":” |
| 23:19, 49:19, 75:19, 101:19, 127:19, 153:19, 179:19, 205:19, 231:19, 257:19, 283:19, 309:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 335:19, 361:19, 387:19, 414:19, 440:19, 466:19, 492:19, 518:19, 544:19, 570:19, 597:19, 623:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 649:19, 675:19, 701:19, 727:19, 753:19, 779:19, 806:19, 833:19, 859:19, 885:19, 911:19, 937:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 963:19, 989:19, 1015:19, 1041:19, 1067:19, 1094:19, 1120:19, 1147:19, 1174:19, 1200:19, 1226:19, 1252:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1278:19, 1304:19, 1330:19, 1356:19, 1382:19, 1408:19, 1435:19, 1461:19, 1487:19, 1513:19, 1539:19, 1565:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1591:19, 1617:19, 1643:19, 1669:19, 1695:19, 1721:19, 1747:19, 1773:19, 1799:19, 1825:19, 1851:19, 1877:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 1903:19, 1929:19, 1956:19, 1982:19, 2008:19, 2034:19, 2061:19, 2087:19, 2113:19, 2139:19, 2165:19, 2191:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 2217:19, 2243:19, 2269:19, 2295:19, 2321:19, 2347:19, 2373:19, 2399:19, 2416:19, 2441:19, 2466:19, 2491:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 2516:19, 2541:19, 2566:19, 2591:19, 2616:19, 2635:19, 2657:19, 2679:19, 2701:19, 2723:19, 2745:19, 2767:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 2789:19, 2811:19, 2833:19, 2855:19, 2877:19, 2899:19, 2921:19, 2943:19, 2965:19, 2987:19, 3009:19, 3031:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 3053:19, 3075:19, 3097:19, 3119:19, 3141:19, 3163:19, 3185:19, 3207:19, 3229:19, 3251:19, 3273:19, 3295:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 3317:19, 3339:19, 3361:19, 3383:19, 3405:19, 3427:19, 3449:19, 3471:19, 3493:19, 3515:19, 3537:19, 3559:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 3581:19, 3603:19, 3625:19, 3647:19, 3669:19, 3691:19, 3713:19, 3735:19, 3757:19, 3779:19, 3801:19, 3823:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 3845:19, 3867:19, 3889:19, 3911:19, 3933:19, 3955:19, 3977:19, 3999:19, 4021:19, 4043:19, 4065:19, 4087:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 4109:19, 4131:19 | `shop` | Data field not rendered | “"section":” “"shop"” |
| 36:8, 62:8, 88:8, 114:8, 140:8, 166:8, 192:8, 218:8, 244:8, 270:8, 296:8, 322:8 | `price` | Data field not rendered | “"price": null” |
| 348:8, 374:8, 400:8, 427:8, 453:8, 479:8, 505:8, 531:8, 557:8, 583:8, 610:8, 636:8 | `price` | Data field not rendered | “"price": null” |
| 662:8, 688:8, 714:8, 740:8, 766:8, 793:8, 820:8, 846:8, 872:8, 898:8, 924:8, 950:8 | `price` | Data field not rendered | “"price": null” |
| 976:8, 1002:8, 1028:8, 1054:8, 1081:8, 1107:8, 1134:8, 1161:8, 1187:8, 1213:8, 1239:8, 1265:8 | `price` | Data field not rendered | “"price": null” |
| 1291:8, 1317:8, 1343:8, 1369:8, 1395:8, 1422:8, 1448:8, 1474:8, 1500:8, 1526:8, 1552:8, 1578:8 | `price` | Data field not rendered | “"price": null” |
| 1604:8, 1630:8, 1656:8, 1682:8, 1708:8, 1734:8, 1760:8, 1786:8, 1812:8, 1838:8, 1864:8, 1890:8 | `price` | Data field not rendered | “"price": null” |
| 1916:8, 1942:8, 1969:8, 1995:8, 2021:8, 2048:8, 2074:8, 2100:8, 2126:8, 2152:8, 2178:8, 2204:8 | `price` | Data field not rendered | “"price": null” |
| 2230:8, 2256:8, 2282:8, 2308:8, 2334:8, 2360:8, 2386:8, 2419:8, 2444:8, 2469:8, 2494:8, 2519:8 | `price` | Data field not rendered | “"price": null” |
| 2544:8, 2569:8, 2594:8, 2619:8, 2647:8, 2669:8, 2691:8, 2713:8, 2735:8, 2757:8, 2779:8, 2801:8 | `price` | Data field not rendered | “"price": null” |
| 2823:8, 2845:8, 2867:8, 2889:8, 2911:8, 2933:8, 2955:8, 2977:8, 2999:8, 3021:8, 3043:8, 3065:8 | `price` | Data field not rendered | “"price": null” |
| 3087:8, 3109:8, 3131:8, 3153:8, 3175:8, 3197:8, 3219:8, 3241:8, 3263:8, 3285:8, 3307:8, 3329:8 | `price` | Data field not rendered | “"price": null” |
| 3351:8, 3373:8, 3395:8, 3417:8, 3439:8, 3461:8, 3483:8, 3505:8, 3527:8, 3549:8, 3571:8, 3593:8 | `price` | Data field not rendered | “"price": null” |
| 3615:8, 3637:8, 3659:8, 3681:8, 3703:8, 3725:8, 3747:8, 3769:8, 3791:8, 3813:8, 3835:8, 3857:8 | `price` | Data field not rendered | “"price": null” |
| 3879:8, 3901:8, 3923:8, 3945:8, 3967:8, 3989:8, 4011:8, 4033:8, 4055:8, 4077:8, 4099:8, 4121:8 | `price` | Data field not rendered | “"price": null” |
| 4143:8 | `price` | Data field not rendered | “"price": null” |
| 47:26, 73:26, 99:26, 203:26, 229:26, 255:26, 1380:26, 1406:26, 1433:26, 1459:26, 2215:26, 2267:26 | `basket` | Data field not rendered | “"sampleUnit":” “"one basket"” |
| 2293:26, 2443:26, 2468:26, 3605:26, 3627:26, 3649:26, 3671:26, 3693:26, 3715:26, 3737:26 | `basket` | Data field not rendered | “"sampleUnit":” “"one basket"” |
| 2473:48 | `baskets` | Data field not rendered | “"evidence":” “baskets” (value excerpt) |
| 2474:45 | `baskets` | Data field not rendered | “"notes":” “baskets” (value excerpt) |
| 2646:32, 2668:32, 2690:32, 2712:32, 2734:32, 2756:32, 2778:32, 2800:32, 2822:32, 2844:32, 2866:32, 2888:32 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 2910:32, 2932:32, 2954:32, 2976:32, 2998:32, 3020:32, 3042:32, 3064:32, 3086:32, 3108:32, 3130:32, 3152:32 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 3174:32, 3196:32, 3218:32, 3240:32, 3262:32, 3284:32, 3306:32, 3328:32, 3350:32, 3372:32, 3394:32, 3416:32 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 3438:32, 3460:32, 3482:32, 3504:32, 3526:32, 3548:32, 3570:32, 3592:32, 3614:32, 3636:32, 3658:32, 3680:32 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 3702:32, 3724:32, 3746:32, 3768:32, 3790:32, 3812:32, 3834:32, 3856:32, 3878:32, 3900:32, 3922:32, 3944:32 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 3966:32, 3988:32, 4010:32, 4032:32, 4054:32, 4076:32, 4098:32, 4120:32, 4142:32 | `price` | Data field not rendered | “"notes":” “price” (value excerpt) |
| 4149:4 | `merch` | Data field not rendered | “"merch":” |
| 4151:14 | `merch` | Data field not rendered | “"id":” “"merch-tee"” |
| 4154:20, 4173:20, 4192:20, 4211:20, 4224:20, 4237:20, 4250:20, 4263:20 | `merch` | Data field not rendered | “"category":” “"merch"” |
| 4155:19, 4174:19, 4193:19, 4212:19, 4225:19, 4238:19, 4251:19, 4264:19 | `merch` | Data field not rendered | “"section":” “"merch"” |
| 4158:33 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-tee.webp"” |
| 4167:21, 4186:21, 4205:21, 4218:21, 4231:21, 4244:21, 4257:21 | `Merchandise` | Data field not rendered | “"imageKind":” “"Merchandise design concept"” |
| 4170:14 | `merch` | Data field not rendered | “"id":” “"merch-coast"” |
| 4177:33 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-coast.webp"” |
| 4189:14 | `merch` | Data field not rendered | “"id":” “"merch-sweat"” |
| 4196:33 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-sweat.webp"” |
| 4208:14 | `merch` | Data field not rendered | “"id":” “"merch-mug"” |
| 4215:33 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-mug.webp"” |
| 4221:14 | `merch` | Data field not rendered | “"id":” “"merch-tote"” |
| 4228:33 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-tote.webp"” |
| 4234:14 | `merch` | Data field not rendered | “"id":” “"merch-cap"” |
| 4241:33 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-cap.webp"” |
| 4247:14 | `merch` | Data field not rendered | “"id":” “"merch-stickers"” |
| 4254:33 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-stickers.webp"” |
| 4260:14 | `merch` | Data field not rendered | “"id":” “"merch-bottle"” |
| 4267:33 | `merch` | Data field not rendered | “"image":” “"assets/products/merch-bottle.webp"” |
| 4270:21 | `Merchandise` | Data field not rendered | “"imageKind":” “"Merchandise concept"” |
| 4273:4 | `boxes` | Data field not rendered | “"boxes":” |
| 4275:14 | `box` | Data field not rendered | “"id":” “"box-small"” |
| 4276:32 | `Box` | Data field not rendered | “"name":” “"Small Vegetable Box"” |
| 4278:20, 4319:20, 4375:20 | `boxes` | Data field not rendered | “"category":” “"boxes"” |
| 4279:19, 4320:19, 4376:19 | `boxes` | Data field not rendered | “"section":” “"boxes"” |
| 4281:26, 4322:26, 4378:26 | `box` | Data field not rendered | “"sampleUnit":” “"one box"” |
| 4290:33 | `box` | Data field not rendered | “"image":” “"assets/products/box-small.webp"” |
| 4291:24, 4335:24, 4393:24 | `box` | Data field not rendered | “"imageKind":” “"AI box concept"” |
| 4316:14 | `box` | Data field not rendered | “"id":” “"box-medium"” |
| 4317:33 | `Box` | Data field not rendered | “"name":” “"Medium Vegetable Box"” |
| 4334:33 | `box` | Data field not rendered | “"image":” “"assets/products/box-medium.webp"” |
| 4372:14 | `box` | Data field not rendered | “"id":” “"box-large"” |
| 4373:32 | `Box` | Data field not rendered | “"name":” “"Large Vegetable Box"” |
| 4392:33 | `box` | Data field not rendered | “"image":” “"assets/products/box-large.webp"” |

#### `storefront-mockup/shop.js` (134)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 4:1 | `$` | Code/comment | “&#36;('#catalog-grid').insertAdjacentHTML('beforebegin','&lt;p class="catalog-from" hidden&gt;&lt;/p&gt;');” |
| 6:1 | `$` | Code/comment | “&#36;('#catalog-grid').insertAdjacentHTML('beforebegin','&lt;p class="micro" id="catalog-item-status" role="status" hidden&gt;&lt;/p&gt;” |
| 9:116 | `$` | Code/comment | “d owner photo (same shape as content_model.HOME_IMAGE_RE) is not an illustration; JS &#36; without the m flag is a true end.” |
| 10:95 | `$` | Code/comment | “const installedImage=s=&gt;typeof s==='string'&amp;&amp;/^assets&#92;/products&#92;/photo-[0-9a-f]{16}&#92;.(jpg&#124;png)&#36;/.test(s);” |
| 11:84 | `$` | Code/comment | “&#96;&lt;img loading=&#92;"lazy&#92;" width=&#92;"800&#92;" height=&#92;"800&#92;" src=&#92;"&#36;{esc(p.image)}&#92;" alt=&#92;"&#36;{esc((p.imageAlt&#124;&#124;p.name)+(installed” |
| 11:108 | `$` | Code/comment | “width=&#92;"800&#92;" height=&#92;"800&#92;" src=&#92;"&#36;{esc(p.image)}&#92;" alt=&#92;"&#36;{esc((p.imageAlt&#124;&#124;p.name)+(installedImage(p.image)?'':' (ill” |
| 12:44 | `$` | Code/comment | “function origin(p){return p.supplier?&#96;From &#36;{p.supplier}&#96;:maker(p)?&#96;Based in &#36;{maker(p).place}&#96;:'Ask us about the source” |
| 12:78 | `$` | Code/comment | “gin(p){return p.supplier?&#96;From &#36;{p.supplier}&#96;:maker(p)?&#96;Based in &#36;{maker(p).place}&#96;:'Ask us about the source in store.'}” |
| 13:160 | `$` | Code/comment | “pan&gt;New&lt;/span&gt;':'');return (tags?&#96;&lt;div class="food-badges"&gt;&#36;{tags}&lt;/div&gt;&#96;:'')+(p.availability?&#96;&lt;p class="product-meta av” |
| 13:233 | `$` | Code/comment | “="food-badges"&gt;&#36;{tags}&lt;/div&gt;&#96;:'')+(p.availability?&#96;&lt;p class="product-meta availability"&gt;&#36;{esc(p.availability)}&lt;/p&gt;&#96;:'')}” |
| 17:86 | `$` | Code/comment | “aker-story"&gt;&lt;summary&gt;Meet the maker&lt;span class="sr-only"&gt;: &#36;{esc(m.name)}&lt;/span&gt;&lt;/summary&gt;&lt;div class="maker-story-conten” |
| 17:150 | `$` | Code/comment | “(m.name)}&lt;/span&gt;&lt;/summary&gt;&lt;div class="maker-story-content"&gt;&#36;{story?&#96;&lt;p&gt;&#36;{esc(m.story)}&lt;/p&gt;&#96;:&#96;&lt;p class="maker-place"&gt;Base” |
| 17:162 | `$` | Code/comment | “pan&gt;&lt;/summary&gt;&lt;div class="maker-story-content"&gt;&#36;{story?&#96;&lt;p&gt;&#36;{esc(m.story)}&lt;/p&gt;&#96;:&#96;&lt;p class="maker-place"&gt;Based in &#36;{esc(m” |
| 17:216 | `$` | Code/comment | “?&#96;&lt;p&gt;&#36;{esc(m.story)}&lt;/p&gt;&#96;:&#96;&lt;p class="maker-place"&gt;Based in &#36;{esc(m.place)}&lt;/p&gt;&#96;}&#36;{link?&#96;&lt;a href="&#36;{esc(m.url)}" target="” |
| 17:237 | `$` | Code/comment | “/p&gt;&#96;:&#96;&lt;p class="maker-place"&gt;Based in &#36;{esc(m.place)}&lt;/p&gt;&#96;}&#36;{link?&#96;&lt;a href="&#36;{esc(m.url)}" target="_blank" rel="noopener” |
| 17:254 | `$` | Code/comment | “aker-place"&gt;Based in &#36;{esc(m.place)}&lt;/p&gt;&#96;}&#36;{link?&#96;&lt;a href="&#36;{esc(m.url)}" target="_blank" rel="noopener"&gt;Visit &#36;{esc(m.n” |
| 17:306 | `$` | Code/comment | “href="&#36;{esc(m.url)}" target="_blank" rel="noopener"&gt;Visit &#36;{esc(m.name)} &lt;span aria-hidden="true"&gt;↗&lt;/span&gt;&lt;/a&gt;&#96;:''}&#36;{ma” |
| 17:363 | `$` | Code/comment | “t &#36;{esc(m.name)} &lt;span aria-hidden="true"&gt;↗&lt;/span&gt;&lt;/a&gt;&#96;:''}&#36;{makerCounts.get(p.producerKey)&gt;=2?&#96;&lt;button type="button" cl” |
| 17:451 | `$` | Code/comment | “ey)&gt;=2?&#96;&lt;button type="button" class="text-link" data-from="&#36;{esc(p.producerKey)}"&gt;See all &#36;{makerCounts.get(p.producerKe” |
| 17:482 | `$` | Code/comment | “lass="text-link" data-from="&#36;{esc(p.producerKey)}"&gt;See all &#36;{makerCounts.get(p.producerKey)} from &#36;{esc(m.name)}&lt;/button” |
| 17:521 | `$` | Code/comment | “om="&#36;{esc(p.producerKey)}"&gt;See all &#36;{makerCounts.get(p.producerKey)} from &#36;{esc(m.name)}&lt;/button&gt;&#96;:''}&lt;/div&gt;&lt;/details&gt;&#96;}” |
| 21:24, 21:85 | `Price` | Code/comment | “const amount=p.sellingPrice?&#96;&lt;p class="product-meta product-price"&gt;&#36;&#36;{esc(p.sellingPrice)}&lt;/p&gt;&#96;:'';” |
| 21:62 | `price` | Attribute | “class="product-meta product-price"” (conditional) |
| 21:69 | `$` | Code/comment | “&gt;&#36;&#36;{esc(p.sellingPrice)}&lt;/p&gt;” (literal dollar; renders only if the price field is set) |
| 21:70 | `$` | Code/comment | “const amount=p.sellingPrice?&#96;&lt;p class="product-meta product-price"&gt;&#36;&#36;{esc(p.sellingPrice)}&lt;/p&gt;&#96;:'';” |
| 22:36 | `$` | Code/comment | “return &#96;&lt;article data-product-id="&#36;{esc(p.id)}" data-category="&#36;{esc(p.category)}"&#36;{m?&#96; data-maker-key="&#36;{esc(p.produce” |
| 22:65 | `$` | Code/comment | “rn &#96;&lt;article data-product-id="&#36;{esc(p.id)}" data-category="&#36;{esc(p.category)}"&#36;{m?&#96; data-maker-key="&#36;{esc(p.producerKey)” |
| 22:84 | `$` | Code/comment | “roduct-id="&#36;{esc(p.id)}" data-category="&#36;{esc(p.category)}"&#36;{m?&#96; data-maker-key="&#36;{esc(p.producerKey)}"&#96;:''}&gt;&lt;div class=” |
| 22:106 | `$` | Code/comment | “}" data-category="&#36;{esc(p.category)}"&#36;{m?&#96; data-maker-key="&#36;{esc(p.producerKey)}"&#96;:''}&gt;&lt;div class="food-card-top"&gt;&lt;div c” |
| 22:188 | `$` | Code/comment | “:''}&gt;&lt;div class="food-card-top"&gt;&lt;div class="product-image"&gt;&#36;{photo(p)}&lt;/div&gt;&lt;div class="food-identity"&gt;&lt;p class="product” |
| 22:256 | `$` | Code/comment | “)}&lt;/div&gt;&lt;div class="food-identity"&gt;&lt;p class="product-meta"&gt;&#36;{esc(brand(p))}&lt;/p&gt;&lt;h3&gt;&#36;{esc(p.name)}&lt;/h3&gt;&#36;{amount}&lt;p class=” |
| 22:280 | `$` | Code/comment | “-identity"&gt;&lt;p class="product-meta"&gt;&#36;{esc(brand(p))}&lt;/p&gt;&lt;h3&gt;&#36;{esc(p.name)}&lt;/h3&gt;&#36;{amount}&lt;p class="origin-label"&gt;&#36;{esc(ori” |
| 22:299 | `$` | Code/comment | “="product-meta"&gt;&#36;{esc(brand(p))}&lt;/p&gt;&lt;h3&gt;&#36;{esc(p.name)}&lt;/h3&gt;&#36;{amount}&lt;p class="origin-label"&gt;&#36;{esc(origin(p))}&lt;/p&gt;&#36;{m?&#96;&lt;s” |
| 22:332 | `$` | Code/comment | “/p&gt;&lt;h3&gt;&#36;{esc(p.name)}&lt;/h3&gt;&#36;{amount}&lt;p class="origin-label"&gt;&#36;{esc(origin(p))}&lt;/p&gt;&#36;{m?&#96;&lt;span class="sr-only maker-name"&gt;&#36;{” |
| 22:353 | `$` | Code/comment | “&lt;/h3&gt;&#36;{amount}&lt;p class="origin-label"&gt;&#36;{esc(origin(p))}&lt;/p&gt;&#36;{m?&#96;&lt;span class="sr-only maker-name"&gt;&#36;{esc(m.name)}&lt;/span&gt;&#96;:” |
| 22:391 | `$` | Code/comment | “&#36;{esc(origin(p))}&lt;/p&gt;&#36;{m?&#96;&lt;span class="sr-only maker-name"&gt;&#36;{esc(m.name)}&lt;/span&gt;&#96;:''}&#36;{badges(p)}&lt;/div&gt;&lt;/div&gt;&lt;p class="f” |
| 22:417 | `$` | Code/comment | “&lt;span class="sr-only maker-name"&gt;&#36;{esc(m.name)}&lt;/span&gt;&#96;:''}&#36;{badges(p)}&lt;/div&gt;&lt;/div&gt;&lt;p class="food-description"&gt;&#36;{esc(p.d” |
| 22:469 | `$` | Code/comment | “n&gt;&#96;:''}&#36;{badges(p)}&lt;/div&gt;&lt;/div&gt;&lt;p class="food-description"&gt;&#36;{esc(p.description)}&lt;/p&gt;&#36;{makerStory(p)}&lt;a class="text-link” |
| 22:494 | `$` | Code/comment | “&lt;/div&gt;&lt;p class="food-description"&gt;&#36;{esc(p.description)}&lt;/p&gt;&#36;{makerStory(p)}&lt;a class="text-link card-link" href="?item=&#36;{” |
| 22:553 | `$` | Code/comment | “&#36;{makerStory(p)}&lt;a class="text-link card-link" href="?item=&#36;{esc(encodeURIComponent(p.id))}#market"&gt;Link to this&lt;/a&gt;&lt;/ar” |
| 24:181 | `$` | Code/comment | “tion');o.value=b;o.textContent=b==='Producer not identified'?'Other market selections':b;&#36;('#brand-filter').append(o)});” |
| 32:109, 32:119, 32:130 | `$` | Code/comment | “(now){const q={};for(const x of PACIFIC_DAY.formatToParts(now))q[x.type]=x.value;return &#96;&#36;{q.year}-&#36;{q.month}-&#36;{q.day}&#96;}” |
| 34:56 | `$` | Code/comment | “function dayNumber(s){const m=/^(&#92;d{4})-(&#92;d{2})-(&#92;d{2})&#36;/.exec(typeof s==='string'?s:'');if(!m)return null;const y=+m[1]” |
| 35:66 | `$` | Code/comment | “on dayText(s){const t=new Date(dayNumber(s)*864e5);return &#96;&#36;{DAY_NAMES[t.getUTCDay()]}, &#36;{MONTH_NAMES[t.getUTCMonth()]}” |
| 35:95, 35:127 | `$` | Code/comment | “t=new Date(dayNumber(s)*864e5);return &#96;&#36;{DAY_NAMES[t.getUTCDay()]}, &#36;{MONTH_NAMES[t.getUTCMonth()]} &#36;{t.getUTCDate()}&#96;}” |
| 39:21, 39:48 | `$` | Code/comment | “const call=/^&#92;d{10}&#36;/.test(phone&#124;&#124;'')?&#96; call (&#36;{phone.slice(0,3)}) &#36;{phone.slice(3,6)}-&#36;{phone.slice(6)} or&#96;:' call or'” |
| 39:69, 39:89 | `$` | Code/comment | “const call=/^&#92;d{10}&#36;/.test(phone&#124;&#124;'')?&#96; call (&#36;{phone.slice(0,3)}) &#36;{phone.slice(3,6)}-&#36;{phone.slice(6)} or&#96;:' call or';” |
| 40:47 | `$` | Code/comment | “return &#96;Selection last checked by Michael on &#36;{dayText(checked)}&#36;{age&gt;STALE_AFTER_DAYS?&#96; (more than a week ago -&#36;{call}” |
| 40:66 | `$` | Code/comment | “n &#96;Selection last checked by Michael on &#36;{dayText(checked)}&#36;{age&gt;STALE_AFTER_DAYS?&#96; (more than a week ago -&#36;{call} visit” |
| 40:114 | `$` | Code/comment | “ecked by Michael on &#36;{dayText(checked)}&#36;{age&gt;STALE_AFTER_DAYS?&#96; (more than a week ago -&#36;{call} visit to confirm)&#96;:''}.&#96;}” |
| 43:96 | `$` | Code/comment | “return o&gt;=dayNumber(checked)&amp;&amp;t-o&lt;=STALE_AFTER_DAYS?AVAILABILITY_WORDS[state]:&#96;Last confirmed &#36;{dayText(on)}&#96;}” |
| 55:119 | `Box` | Code/comment | “URRENT=new Set(['Available today','Limited','Sold out']),AVAIL=new Set(['Available today','Limited']);let availBox=null;” |
| 56:50 | `$` | Code/comment | “if(catalog.some(p=&gt;CURRENT.has(p.availability))){&#36;('#brand-filter').closest('label').insertAdjacentHTML('afterend','&lt;lab” |
| 56:218 | `Box` | Code/comment | “el class="avail-filter"&gt;&lt;input type="checkbox" id="avail-filter"&gt; Available today&lt;/label&gt;');availBox=&#36;('#avail-filter')}” |
| 56:222 | `$` | Code/comment | “el class="avail-filter"&gt;&lt;input type="checkbox" id="avail-filter"&gt; Available today&lt;/label&gt;');availBox=&#36;('#avail-filter')}” |
| 61:8 | `SHOP` | Code/comment | “// AVO-SHOP-CLEAN-1: the shop opens on packaged goods. The shelves split into packaged goods and fresh produce (fruit, v” |
| 61:26 | `shop` | Code/comment | “// AVO-SHOP-CLEAN-1: the shop opens on packaged goods. The shelves split into packaged goods and fresh produce (fruit, v” |
| 70:174 | `$` | Code/comment | “&amp;&amp;activeView!=='all'&amp;&amp;viewOfShelf(cur.dataset.filter)!==activeView)selectShelf(&#36;('[data-filter="all"]'));shelfButtons()}” |
| 76:10 | `ordered` | Code/comment | “function orderedProducts(now=renderNow){const d=catalog.map((p,i)=&gt;({p,i,n:isNew(p,now)}));” |
| 81:114 | `ordered` | Code/comment | “052-01: a search term also matches the description, after the card's own words. One stable pass splits the ordered list:” |
| 86:49 | `$` | Code/comment | “const forms=w=&gt;{const f=new Set([w]);if(/^&#92;p{L}+&#36;/u.test(w)&amp;&amp;[...w].length&gt;=4){const add=x=&gt;{if([...x].length&gt;=3)f.add(x” |
| 88:58 | `$` | Code/comment | “function filteredProducts(){const pieces=fold(searchText(&#36;('#product-search').value)).split(/&#92;s+/).filter(Boolean),brand” |
| 88:122 | `$` | Code/comment | “){const pieces=fold(searchText(&#36;('#product-search').value)).split(/&#92;s+/).filter(Boolean),brand=&#36;('#brand-filter').value;” |
| 89:13 | `ordered` | Code/comment | “const list=orderedProducts().filter(p=&gt;inView(p)&amp;&amp;(!activeFrom&#124;&#124;p.producerKey===activeFrom)&amp;&amp;(activeCategory==='all'&#124;&#124;p” |
| 89:184 | `Box` | Code/comment | “gory==='all'&#124;&#124;p.category===activeCategory)&amp;&amp;(!brand&#124;&#124;p.brand===brand)&amp;&amp;(!availBox?.checked&#124;&#124;AVAIL.has(p.availability)));” |
| 96:38 | `Box` | Code/comment | “function retireStaleAvail(){if(!availBox&#124;&#124;catalog.some(p=&gt;CURRENT.has(p.availability)))return false;availBox.checked=fal” |
| 96:106 | `Box` | Code/comment | “og.some(p=&gt;CURRENT.has(p.availability)))return false;availBox.checked=false;availBox.closest('.avail-filter').remove();a” |
| 96:129, 96:172 | `Box` | Code/comment | “RRENT.has(p.availability)))return false;availBox.checked=false;availBox.closest('.avail-filter').remove();availBox=null;” |
| 98:198 | `$` | Code/comment | “pacificDay(renderNow)){append=false;renderNow=t}const chip=&#36;('.catalog-from');chip.hidden=!activeFrom;chip.innerHTML=act” |
| 98:273 | `$` | Code/comment | “');chip.hidden=!activeFrom;chip.innerHTML=activeFrom?&#96;From &#36;{esc(producers[activeFrom].name)} &lt;button type="button" data” |
| 98:449 | `$` | Code/comment | “eredProducts(),end=Math.min(limit,list.length);if(!append){&#36;('#catalog-grid').innerHTML='';visibleCount=0}&#36;('#catalog-gr” |
| 98:496 | `$` | Code/comment | “if(!append){&#36;('#catalog-grid').innerHTML='';visibleCount=0}&#36;('#catalog-grid').insertAdjacentHTML('beforeend',drawCards(l” |
| 98:604 | `$` | Code/comment | “,drawCards(list.slice(visibleCount,end)));visibleCount=end;&#36;('#catalog-count').textContent=&#96;&#36;{list.length} selections ·” |
| 98:637 | `$` | Code/comment | “t,end)));visibleCount=end;&#36;('#catalog-count').textContent=&#96;&#36;{list.length} selections · &#36;{visibleCount} shown&#96;;&#36;('#catalo” |
| 98:665 | `$` | Code/comment | “'#catalog-count').textContent=&#96;&#36;{list.length} selections · &#36;{visibleCount} shown&#96;;&#36;('#catalog-sentinel').textContent=vis” |
| 98:688 | `$` | Code/comment | “ontent=&#96;&#36;{list.length} selections · &#36;{visibleCount} shown&#96;;&#36;('#catalog-sentinel').textContent=visibleCount&lt;list.length?'” |
| 98:1033 | `$` | Code/comment | “. Try All items, another category, or clear your filters.';&#36;('#more-products').hidden=('IntersectionObserver' in window)” |
| 98:1122 | `$` | Code/comment | “products').hidden=('IntersectionObserver' in window)&#124;&#124;visibleCount&gt;=list.length;&#36;('#clear-filters').hidden=!anyFilter()}” |
| 99:91 | `$` | Code/comment | “iveView!=='packaged'&#124;&#124;activeCategory!=='all'&#124;&#124;!!searchText(&#36;('#product-search').value)&#124;&#124;!!&#36;('#brand-filter').value&#124;&#124;!!ac” |
| 99:122 | `$` | Code/comment | “tegory!=='all'&#124;&#124;!!searchText(&#36;('#product-search').value)&#124;&#124;!!&#36;('#brand-filter').value&#124;&#124;!!activeFrom&#124;&#124;!!availBox?.checked}” |
| 99:169 | `Box` | Code/comment | “tegory!=='all'&#124;&#124;!!searchText(&#36;('#product-search').value)&#124;&#124;!!&#36;('#brand-filter').value&#124;&#124;!!activeFrom&#124;&#124;!!availBox?.checked}” |
| 101:44 | `$` | Code/comment | “linkedItem='';p.delete('item');const gone=&#36;('#catalog-item-status');gone.hidden=true;gone.textContent='';  // A filter” |
| 102:218 | `$` | Code/comment | “veFrom?'all':'packaged')?'':activeView);set('q',searchText(&#36;('#product-search').value));set('maker',&#36;('#brand-filter').v” |
| 102:259 | `$` | Code/comment | “et('q',searchText(&#36;('#product-search').value));set('maker',&#36;('#brand-filter').value);set('avail',availBox?.checked?'1':'” |
| 102:302 | `Box` | Code/comment | “'q',searchText(&#36;('#product-search').value));set('maker',&#36;('#brand-filter').value);set('avail',availBox?.checked?'1':'');” |
| 105:1 | `$` | Code/comment | “&#36;('#clear-filters').onclick=()=&gt;{setView('packaged');selectShelf(&#36;('[data-filter="all"]'));&#36;('#product-search').value=''” |
| 105:66 | `$` | Code/comment | “ear-filters').onclick=()=&gt;{setView('packaged');selectShelf(&#36;('[data-filter="all"]'));&#36;('#product-search').value='';&#36;('#b” |
| 105:92 | `$` | Code/comment | “{setView('packaged');selectShelf(&#36;('[data-filter="all"]'));&#36;('#product-search').value='';&#36;('#brand-filter').value='';act” |
| 105:122 | `$` | Code/comment | “lf(&#36;('[data-filter="all"]'));&#36;('#product-search').value='';&#36;('#brand-filter').value='';activeFrom='';if(availBox)availBo” |
| 105:172 | `Box` | Code/comment | “alue='';&#36;('#brand-filter').value='';activeFrom='';if(availBox)availBox.checked=false;resetCatalog();&#36;('#product-search')” |
| 105:181 | `Box` | Code/comment | “('#brand-filter').value='';activeFrom='';if(availBox)availBox.checked=false;resetCatalog();&#36;('#product-search').focus()}” |
| 105:214 | `$` | Code/comment | “'#brand-filter').value='';activeFrom='';if(availBox)availBox.checked=false;resetCatalog();&#36;('#product-search').focus()};” |
| 107:54, 107:70 | `box` | Code/comment | “// Typed or pasted text past the limit is cut in the box too, so the box, the results and a shared address agree.” |
| 108:1, 108:45 | `$` | Code/comment | “&#36;('#product-search').oninput=()=&gt;{const box=&#36;('#product-search');if([...box.value.trim()].length&gt;80)box.value=searchText” |
| 108:41 | `box` | Code/comment | “&#36;('#product-search').oninput=()=&gt;{const box=&#36;('#product-search');if([...box.value.trim()].length&gt;80)box.value=searchText” |
| 108:73 | `box` | Code/comment | “arch').oninput=()=&gt;{const box=&#36;('#product-search');if([...box.value.trim()].length&gt;80)box.value=searchText(box.value);re” |
| 108:101 | `box` | Code/comment | “x=&#36;('#product-search');if([...box.value.trim()].length&gt;80)box.value=searchText(box.value);resetCatalog()};&#36;('#brand-filt” |
| 108:122 | `box` | Code/comment | “);if([...box.value.trim()].length&gt;80)box.value=searchText(box.value);resetCatalog()};&#36;('#brand-filter').onchange=resetCa” |
| 108:149 | `$` | Code/comment | “.length&gt;80)box.value=searchText(box.value);resetCatalog()};&#36;('#brand-filter').onchange=resetCatalog;if(availBox)availBox” |
| 108:198 | `Box` | Code/comment | “talog()};&#36;('#brand-filter').onchange=resetCatalog;if(availBox)availBox.onchange=resetCatalog;&#36;('#more-products').onclick” |
| 108:207 | `Box` | Code/comment | “&#36;('#brand-filter').onchange=resetCatalog;if(availBox)availBox.onchange=resetCatalog;&#36;('#more-products').onclick=loadMore” |
| 108:233 | `$` | Code/comment | “('#brand-filter').onchange=resetCatalog;if(availBox)availBox.onchange=resetCatalog;&#36;('#more-products').onclick=loadMore;” |
| 112:212 | `$` | Code/comment | “From(key))return;activeFrom=key;setView('all');selectShelf(&#36;('[data-filter="all"]'));&#36;('#product-search').value='';&#36;('#b” |
| 112:238 | `$` | Code/comment | “m=key;setView('all');selectShelf(&#36;('[data-filter="all"]'));&#36;('#product-search').value='';&#36;('#brand-filter').value='';if(” |
| 112:268 | `$` | Code/comment | “lf(&#36;('[data-filter="all"]'));&#36;('#product-search').value='';&#36;('#brand-filter').value='';if(availBox)availBox.checked=fals” |
| 112:304 | `Box` | Code/comment | “uct-search').value='';&#36;('#brand-filter').value='';if(availBox)availBox.checked=false;resetCatalog();&#36;('#catalog-grid').s” |
| 112:313 | `Box` | Code/comment | “h').value='';&#36;('#brand-filter').value='';if(availBox)availBox.checked=false;resetCatalog();&#36;('#catalog-grid').scrollInto” |
| 112:346 | `$` | Code/comment | “ilter').value='';if(availBox)availBox.checked=false;resetCatalog();&#36;('#catalog-grid').scrollIntoView({block:'start'})});” |
| 116:13 | `$` | Code/comment | “const edge=&#36;('#catalog-sentinel').getBoundingClientRect();” |
| 125:22, 125:37 | `$` | Code/comment | “if(target&amp;&amp;target!==&#36;('#market')&amp;&amp;!&#36;('#market').contains(target)){sectionNavigation=true;waitForSectionScroll()}” |
| 136:45 | `$` | Code/comment | “if(shelf&amp;&amp;!shelf.hidden)selectShelf(shelf);&#36;('#product-search').value=searchText(u.get('q'));&#36;('#brand-filter').value=m” |
| 136:95 | `$` | Code/comment | “f(shelf);&#36;('#product-search').value=searchText(u.get('q'));&#36;('#brand-filter').value=mk&amp;&amp;[...&#36;('#brand-filter').options].” |
| 136:128 | `$` | Code/comment | “).value=searchText(u.get('q'));&#36;('#brand-filter').value=mk&amp;&amp;[...&#36;('#brand-filter').options].some(o=&gt;o.value===mk)?mk:'';” |
| 139:65 | `ordered` | Code/comment | “const item=u.get('item'),i=item&amp;&amp;[...item].length&lt;=80?soldLast(orderedProducts()).findIndex(p=&gt;p.id===item):-1;” |
| 140:52 | `$` | Code/comment | “if(i&gt;=0){activeFrom='';setView('all');selectShelf(&#36;('[data-filter="all"]'));&#36;('#product-search').value='';&#36;('#brand-fil” |
| 140:78 | `$` | Code/comment | “om='';setView('all');selectShelf(&#36;('[data-filter="all"]'));&#36;('#product-search').value='';&#36;('#brand-filter').value='';lim” |
| 140:108 | `$` | Code/comment | “lf(&#36;('[data-filter="all"]'));&#36;('#product-search').value='';&#36;('#brand-filter').value='';limit=Math.max(12,Math.ceil((i+1)” |
| 140:202, 140:211 | `Box` | Code/comment | “('#brand-filter').value='';limit=Math.max(12,Math.ceil((i+1)/12)*12);linkedItem=item;if(availBox)availBox.checked=false}” |
| 141:10, 141:19 | `Box` | Code/comment | “if(availBox)availBox.checked=u.get('avail')==='1'&amp;&amp;i&lt;0;” |
| 144:46 | `$` | Code/comment | “if(i&lt;0&amp;&amp;item&amp;&amp;[...item].length&lt;=80){const s=&#36;('#catalog-item-status');s.textContent='That item is not in our catalog ri” |
| 144:400 | `Box` | Code/comment | “u.has('from')&amp;&amp;!activeFrom){u.delete('from');fix=true}if(u.has('avail')&amp;&amp;!availBox?.checked){u.delete('avail');fix=true}” |
| 158:19 | `$` | Code/comment | “observer.observe(&#36;('#catalog-sentinel'));” |

#### `storefront-mockup/story-QA.json` (2)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 3:4 | `merch` | Data field not rendered | “"merch":” |
| 4:13 | `Boxes` | Data field not rendered | “Boxes” (field name excerpt) |

#### `storefront-mockup/style.css` (19)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 1:86 | `box` | Code/comment | “:#faf7ef;--soft:#eeeadd;--orange:#ac4828;--line:#d3d7c9}*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-paddi” |
| 1:104 | `box` | Code/comment | “eeadd;--orange:#ac4828;--line:#d3d7c9}*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:30px}body{m” |
| 1:3592 | `boxes` | Code/comment | “ight:1.5}.market&gt;.micro{margin-top:22px;max-width:720px}.boxes{display:grid;grid-template-columns:1fr 1fr;background:var” |
| 1:3695 | `boxes` | Code/comment | “fr;background:var(--ink);color:var(--cream);margin:0 4%}.boxes&gt;img{height:490px;width:100%;object-fit:cover;object-posit” |
| 1:3771 | `boxes` | Code/comment | “0px;width:100%;object-fit:cover;object-position:50% 30%}.boxes&gt;div{padding:50px}.box-options{border-top:1px solid #68867” |
| 1:3795 | `box` | Code/comment | “it:cover;object-position:50% 30%}.boxes&gt;div{padding:50px}.box-options{border-top:1px solid #688679;margin:25px 0}.box-op” |
| 1:3851 | `box` | Code/comment | “}.box-options{border-top:1px solid #688679;margin:25px 0}.box-options button{color:var(--cream);width:100%;text-align:le” |
| 1:8029 | `boxes` | Code/comment | “uto;white-space:nowrap}.filters button{padding:8px 12px}.boxes{grid-template-columns:1fr;margin:0}.boxes&gt;img{height:230p” |
| 1:8071 | `boxes` | Code/comment | “ding:8px 12px}.boxes{grid-template-columns:1fr;margin:0}.boxes&gt;img{height:230px}.boxes&gt;div{padding:32px 6%}.story{grid-t” |
| 1:8095 | `boxes` | Code/comment | “d-template-columns:1fr;margin:0}.boxes&gt;img{height:230px}.boxes&gt;div{padding:32px 6%}.story{grid-template-columns:1fr;padd” |
| 3:2 | `shop` | Code/comment | “.shop-directory{margin:35px 4% 0;display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid var(--line);borde” |
| 3:153 | `shop` | Code/comment | “px solid var(--line);border-bottom:1px solid var(--line)}.shop-directory a{padding:24px;text-decoration:none;font:30px G” |
| 3:258 | `shop` | Code/comment | “one;font:30px Georgia;border-right:1px solid var(--line)}.shop-directory a:last-child{border:0}.shop-directory span{font” |
| 3:296 | `shop` | Code/comment | “solid var(--line)}.shop-directory a:last-child{border:0}.shop-directory span{font:11px Arial;display:block;margin-botto” |
| 3:386 | `shop` | Code/comment | “ial;display:block;margin-bottom:12px;color:var(--orange)}.shop-directory small{display:block;font:13px Arial;margin-top:” |
| 3:1404 | `shop` | Code/comment | “var(--orange);outline-offset:3px}@media(max-width:800px){.shop-directory{margin:24px 5% 0;grid-template-columns:1fr}.sho” |
| 3:1463 | `shop` | Code/comment | “hop-directory{margin:24px 5% 0;grid-template-columns:1fr}.shop-directory a{padding:18px 0;border-right:0;border-bottom:1” |
| 3:1562 | `shop` | Code/comment | “ght:0;border-bottom:1px solid var(--line);font-size:27px}.shop-directory small{margin-top:7px}.shop-directory span{displ” |
| 3:1599 | `shop` | Code/comment | “ine);font-size:27px}.shop-directory small{margin-top:7px}.shop-directory span{display:inline;margin-right:12px}.product-” |

#### `storefront-mockup/trail-explorer.css` (5)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 24:74 | `order` | Code/comment | “label{fill:#173c2e;stroke:#fffbed;stroke-width:4px;paint-order:stroke;stroke-linejoin:round;font:700 11px Arial,sans-ser” |
| 27:96 | `box` | Code/comment | “-map-tools{position:absolute;top:14px;right:14px;display:grid;gap:1px;background:#c8cebd;box-shadow:0 1px 8px #122e3026}” |
| 59:84 | `box` | Code/comment | “%;height:44px;padding:0;margin:0;border:0;border-radius:0;box-shadow:none;display:block;accent-color:#214d3d;cursor:ew-r” |
| 62:164 | `box` | Code/comment | “;height:18px;border-radius:50%;background:#214d3d;border:2px solid #faf7ef;margin-top:-7px;box-shadow:0 0 0 1px #214d3d}” |
| 64:120 | `box` | Code/comment | “thumb{width:16px;height:16px;border-radius:50%;background:#214d3d;border:2px solid #faf7ef;box-shadow:0 0 0 1px #214d3d}” |

#### `storefront-mockup/trail-explorer.js` (51)

| Line:column | Hit | Class | Quoted source |
|---|---|---|---|
| 8:78 | `$` | Code/comment | “ion,label,symbol)=&gt;&#96;&lt;button type="button" data-map-action="&#36;{action}" aria-label="&#36;{label}" title="&#36;{label}"&gt;&lt;svg viewBo” |
| 8:101 | `$` | Code/comment | “tton type="button" data-map-action="&#36;{action}" aria-label="&#36;{label}" title="&#36;{label}"&gt;&lt;svg viewBox="0 0 24 24" aria-hidd” |
| 8:118 | `$` | Code/comment | “" data-map-action="&#36;{action}" aria-label="&#36;{label}" title="&#36;{label}"&gt;&lt;svg viewBox="0 0 24 24" aria-hidden="true" fill="n” |
| 8:137 | `Box` | Attribute | “{action}" aria-label="&#36;{label}" title="&#36;{label}"&gt;&lt;svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="current” |
| 8:225 | `$` | Code/comment | “Box="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7"&gt;&#36;{icon(symbol)}&lt;/svg&gt;&lt;/button&gt;&#96;;” |
| 29:166 | `$` | Code/comment | “3 id="trail-explorer-heading"&gt;Follow the coastline.&lt;/h3&gt;&lt;p&gt;&#36;{miles} miles out &amp;amp; back · from Coon Creek parking&lt;/p&gt;&lt;/” |
| 32:73 | `Box` | Attribute | “"trail-compass" aria-hidden="true"&gt;&lt;span&gt;N&lt;/span&gt;&lt;svg viewBox="0 0 22 30"&gt;&lt;path d="M11 2 20 27 11 21 2 27Z" fill="curren” |
| 33:72 | `$` | Code/comment | “s="trail-map-tools" role="group" aria-label="Map controls"&gt;&#36;{control('in','Zoom in','plus')}&#36;{control('out','Zoom out','” |
| 33:105 | `$` | Code/comment | “aria-label="Map controls"&gt;&#36;{control('in','Zoom in','plus')}&#36;{control('out','Zoom out','minus')}&#36;{control('fit','Show ful” |
| 33:141 | `$` | Code/comment | “'in','Zoom in','plus')}&#36;{control('out','Zoom out','minus')}&#36;{control('fit','Show full route','fit')}&#36;{control('expand','” |
| 33:182 | `$` | Code/comment | “rol('out','Zoom out','minus')}&#36;{control('fit','Show full route','fit')}&#36;{control('expand','Enlarge map','expand')}&lt;/div&gt;” |
| 37:110 | `$` | Code/comment | “levation-heading"&gt;&lt;h4&gt;The ups &amp;amp; downs.&lt;/h4&gt;&lt;p&gt;&lt;span&gt;↗ ~&#36;{gain} ft gain&lt;/span&gt;&lt;span&gt;↘ ~&#36;{loss} ft loss&lt;/span&gt;&lt;/p&gt;&lt;/di” |
| 37:141 | `$` | Code/comment | “amp; downs.&lt;/h4&gt;&lt;p&gt;&lt;span&gt;↗ ~&#36;{gain} ft gain&lt;/span&gt;&lt;span&gt;↘ ~&#36;{loss} ft loss&lt;/span&gt;&lt;/p&gt;&lt;/div&gt;&lt;div class="trail-profile-cha” |
| 37:296 | `$` | Code/comment | “role="img" aria-label="Estimated elevation profile for the &#36;{miles}-mile round trip. The return retraces the outbound ro” |
| 37:616 | `$` | Code/comment | “distance" class="trail-distance" type="range" min="0" max="&#36;{d.profile.length-1}" step="1" value="0" aria-label="Distanc” |
| 38:278 | `$` | Code/comment | “l northern loop is not included. Our mapped route is about &#36;{miles} miles; PG&amp;amp;E describes the trail as 6.6 miles rou” |
| 45:49 | `$` | Code/comment | “if(failed&#124;&#124;!/point-buchon-(aerial&#124;topo)&#92;.webp&#36;/.test(photo.getAttribute('href'))&#124;&#124;!host.isConnected&#124;&#124;!(enlarged&#124;&#124;host” |
| 54:38, 54:50, 54:69 | `$` | Code/comment | “const routePath=points.map((p,i)=&gt;&#96;&#36;{i?'L':'M'}&#36;{p[0].toFixed(3)},&#36;{p[1].toFixed(3)}&#96;).join(' ');” |
| 66:26 | `Box` | Attribute | “svg.setAttribute('viewBox',&#96;&#36;{view.cx-halfW} &#36;{view.cy-halfH} &#36;{view.width} &#36;{view.height}&#96;);” |
| 66:32, 66:49, 66:66, 66:80 | `$` | Code/comment | “svg.setAttribute('viewBox',&#96;&#36;{view.cx-halfW} &#36;{view.cy-halfH} &#36;{view.width} &#36;{view.height}&#96;);” |
| 69:49, 69:61, 69:80 | `$` | Code/comment | “element.setAttribute('transform',&#96;translate(&#36;{point[0]} &#36;{point[1]}) scale(&#36;{scale})&#96;);” |
| 78:44 | `$` | Code/comment | “q('.trail-map-scale span').textContent=&#96;&#36;{scaleMetres} m&#96;;q('.trail-map-scale i').style.width=&#96;&#36;{scaleMetres/metresPe” |
| 78:99 | `$` | Code/comment | “scale span').textContent=&#96;&#36;{scaleMetres} m&#96;;q('.trail-map-scale i').style.width=&#96;&#36;{scaleMetres/metresPerScreenPixel}px&#96;;” |
| 94:28 | `Box` | Attribute | “chart.setAttribute('viewBox',&#96;0 0 &#36;{w} &#36;{h}&#96;);chart.replaceChildren();” |
| 94:38, 94:43 | `$` | Code/comment | “chart.setAttribute('viewBox',&#96;0 0 &#36;{w} &#36;{h}&#96;);chart.replaceChildren();” |
| 97:216 | `$` | Code/comment | “de('text',{x,y:h-7,'text-anchor':m===0?'start':'middle',class:'profile-axis'});t.textContent=&#96;&#36;{m} mi&#96;;chart.append(t);}” |
| 98:35, 98:47 | `$` | Code/comment | “const line=profile.map((p,i)=&gt;&#96;&#36;{i?'L':'M'}&#36;{xy(p).map(v=&gt;v.toFixed(2)).join(',')}&#96;).join(' ');” |
| 99:33, 99:42, 99:53 | `$` | Code/comment | “chart.append(node('path',{d:&#96;&#36;{line} L&#36;{w-right},&#36;{h-bottom} L&#36;{left},&#36;{h-bottom} Z&#96;,class:'profile-area'}),node('pat” |
| 99:66 | `$` | Code/comment | “rt.append(node('path',{d:&#96;&#36;{line} L&#36;{w-right},&#36;{h-bottom} L&#36;{left},&#36;{h-bottom} Z&#96;,class:'profile-area'}),node('path',{d:” |
| 99:74 | `$` | Code/comment | “d(node('path',{d:&#96;&#36;{line} L&#36;{w-right},&#36;{h-bottom} L&#36;{left},&#36;{h-bottom} Z&#96;,class:'profile-area'}),node('path',{d:line,cla” |
| 108:24, 108:64 | `$` | Code/comment | “output.textContent=&#96;&#36;{mi(p.distanceMeters).toFixed(1)} mi · &#36;{elevation} ft&#96;;” |
| 109:42 | `$` | Code/comment | “slider.setAttribute('aria-valuetext',&#96;&#36;{mi(p.distanceMeters).toFixed(1)} miles &#36;{direction}, &#36;{elevation} feet above” |
| 109:83, 109:97 | `$` | Code/comment | “tAttribute('aria-valuetext',&#96;&#36;{mi(p.distanceMeters).toFixed(1)} miles &#36;{direction}, &#36;{elevation} feet above sea level&#96;);” |
| 113:69 | `box` | Code/comment | “selectFromPointer(e){const chart=q('.trail-profile-svg'),box=chart.getBoundingClientRect();if(!chart._plot)return;const” |
| 113:174 | `box` | Code/comment | “ot)return;const distance=Math.max(0,Math.min(1,(e.clientX-box.left-chart._plot.left)/chart._plot.plotW))*d.distanceMeter” |
| 118:161 | `$` | Code/comment | “yer;photo.setAttribute('href',&#96;/assets/trails/point-buchon-&#36;{layer.dataset.mapLayer}.webp&#96;);wrapper.querySelectorAll('[d” |
| 137:130 | `$` | Code/comment | “ail-stats dd');if(stats?.length===4){stats[0].textContent=&#96;&#36;{miles} miles&#96;;stats[2].textContent=&#96;~&#36;{gain} ft&#96;;stats[2].p” |
| 137:169 | `$` | Code/comment | “ats[0].textContent=&#96;&#36;{miles} miles&#96;;stats[2].textContent=&#96;~&#36;{gain} ft&#96;;stats[2].previousElementSibling.textContent='Est.” |
