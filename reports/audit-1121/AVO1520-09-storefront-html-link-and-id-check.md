# Storefront HTML link and ID check

## R1. Counts by page

| Page (under `storefront-mockup/`) | Navigation links | Script references | Stylesheet references | Other `<link>` references | IDs (occurrences / distinct) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `index.html` | 14 | 5 | 1 | 1 | 17 / 17 |
| `about/index.html` | 11 | 1 | 1 | 1 | 3 / 3 |
| `faq/index.html` | 11 | 1 | 1 | 1 | 3 / 3 |
| `getting-here/index.html` | 11 | 1 | 1 | 1 | 3 / 3 |
| `hike/index.html` | 12 | 3 | 3 | 1 | 10 / 10 |
| `policies/index.html` | 11 | 1 | 1 | 1 | 3 / 3 |
| **Total** | **70** | **12** | **8** | **6** | **39 / 39** |

Read-only run: **2026-11-21 UTC**, fresh `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, matching the specified baseline. The non-archive glob also finds `about/index.html`, so it is included alongside the five named pages. Navigation counts `<a href>` and `<area href>` by occurrence, including the external link and bare `#`. Script references require `src`; the inline JSON-LD at `storefront-mockup/index.html:8` is not a file reference. Other `<link>` entries are favicons (line 4 of each page). Distinct IDs are tallied per page, then summed.

## R2. Missing files and fragment targets

| Result | Occurrences | Evidence |
| --- | ---: | --- |
| Local link or reference resolves to no file | 0 | Of the 96 link/reference occurrences, 95 were local. All 95 resolved to tracked files: 48 without a fragment, 46 with a matching nonempty fragment, and one with an empty fragment. See the run in R3. |
| Nonempty local fragment has no matching `id` | 0 | All 46 matched on the resolved page, not necessarily on the source page. See the run in R3. |
| Empty fragment (not a missing ID) | 1 | `storefront-mockup/index.html:14`: `<a class="brand" href="#">`. This URL refers to the top of the current document, not an element with an empty ID. |
| External link (not checked) | 1 | `storefront-mockup/index.html:27`; the source has an `https:` URL. No network check was made. |

## R3. Duplicate IDs, method and limits

**No duplicate IDs within a page** (zero duplicate groups; there are no pairs of source lines to quote). Across pages, reusing an ID is not a duplicate for this check.

The workspace-only `audit_storefront_html.py` read pinned HTML blobs with `git show` and only listed target file names and modes with `git ls-tree`. Python's standard-library `HTMLParser` collected each relevant attribute, the raw start tag, and its starting line. It grouped parsed, case-sensitive ID values per file. `urllib.parse` resolved file-relative and root-relative URLs against a placeholder origin with `storefront-mockup/` as the document root. Resolution ignored the query, decoded percent escapes, and used `<directory>/index.html` for directory URLs. A nonempty decoded fragment was compared to the IDs in the destination HTML. No `<base href>` was encountered; the script would stop on one instead of guessing a base.

Local commands (from the task clone; script in its workspace parent):

```sh
git ls-files -- ':(glob)storefront-mockup/**/*.html' ':(exclude,glob)storefront-mockup/archive/**'
python3 ../audit_storefront_html.py --self-test
python3 ../audit_storefront_html.py 37feae1dc5efa6968f90d17a1eda6daed29afd4a
```

Read-only parser output from 2026-11-21 UTC (totals excerpt):

```text
Controls passed: 8 URL cases and one duplicate-ID line-pair case.
Totals: {'distinct-ids-per-page': 39, 'empty-fragment': 1, 'external': 1, 'file-ok': 48, 'id-ok': 46, 'ids': 39, 'link': 70, 'other-link-rel': 6, 'script': 12, 'stylesheet': 8} duplicate-id-groups: 0
```

This checks literal tags in tracked, non-archive HTML, not a browser DOM. It does not execute scripts, follow CSS imports, inspect image or form URL attributes, validate legacy named anchors or ID references in other attributes, or test server routing, deployment behavior, or off-site URLs. An existing target file is not proof it loads or runs correctly.

## R4. Ranked gaps and follow-up

1. **Static defects: none found.** The R2–R3 run found no missing local file, missing named fragment, or duplicated ID. The home brand's bare `#` is accounted for separately and does not need an anchor target (`storefront-mockup/index.html:14`).
2. **Unverified, not defects:** Browser-generated links and IDs, served routes, and the single off-site URL remain outside the check (R2–R3). The report makes no claim about whether those work in a live environment.

No buildable repair unit is needed on this evidence. No storefront files were changed.
