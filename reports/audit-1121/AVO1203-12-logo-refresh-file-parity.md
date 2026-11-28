# Logo-refresh file parity

| Check | Result | Evidence |
| --- | --- | --- |
| Names and counts | 10 direction PNGs, 10 prompt records and 10 gallery cards agree by filename and label. | R1 inventory; R2 path and gallery checks |
| Paths | All 10 JSON `path` values are absolute paths outside the checkout; their basenames match the local PNGs. All 20 gallery references resolve locally. | R2 dated parser results |
| Pixel size | Every PNG is 1254 × 1254; every prompt asks for a square 1024px presentation. The contact sheet is 1400 × 2600. | R1 header reads; R2 contact sheet |
| Bytes | Exact PNG and contact-sheet sizes are below. Neither the JSON nor the gallery declares byte counts to compare. | R1 commands and source anchors; R2 contact sheet |

Source: `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a` (also the task baseline), checked 2026-11-21. This was a local, read-only inspection of `branding/logo-refresh/`: no image rendering, regeneration, browser check or visual comparison of the logos. No logo is recommended or ranked.

## R1. The ten direction images and their prompt records

Paths below are relative to `branding/logo-refresh/`. The pointer is the zero-based record in `prompts-and-files.json`: append `/prompt` for the original prompt or `/path` for the recorded path. Only the filename part of each `path` is reproduced here. The gallery `alt` text and the unnumbered part of each heading match the JSON `name` (R2).

| PNG filename (JSON `path` basename) | Bytes | Pixels (W × H) | JSON record | `id` | `name` |
| --- | ---: | --- | --- | --- | --- |
| `01-coastal-shack.png` | 1,345,151 | 1254 × 1254 | `/1` | `01-coastal-shack` | Coastal Shack |
| `02-market-lettering.png` | 1,193,567 | 1254 × 1254 | `/2` | `02-market-lettering` | Market Lettering |
| `03-coastal-cut.png` | 1,240,564 | 1254 × 1254 | `/0` | `03-coastal-cut` | Coastal Cut |
| `04-growers-stamp.png` | 1,602,734 | 1254 × 1254 | `/3` | `04-growers-stamp` | Growers’ Stamp |
| `05-coast-woodcut.png` | 1,509,798 | 1254 × 1254 | `/4` | `05-coast-woodcut` | Coast Woodcut |
| `06-neighbor-avocado.png` | 1,346,292 | 1254 × 1254 | `/5` | `06-neighbor-avocado` | The Friendly Neighbor |
| `07-market-crate.png` | 1,233,664 | 1254 × 1254 | `/7` | `07-market-crate` | Market Crate |
| `08-shack-script.png` | 1,233,051 | 1254 × 1254 | `/6` | `08-shack-script` | Shack Script |
| `09-growers-coast.png` | 1,259,375 | 1254 × 1254 | `/8` | `09-growers-coast` | Growers & Coast |
| `10-as-mark.png` | 1,224,395 | 1254 × 1254 | `/9` | `10-as-mark` | AS Market Monogram |

From the repo root on the pinned checkout, `git ls-tree -l -r origin/main branding/logo-refresh/` shows the tracked byte lengths, `stat -c '%s %n' branding/logo-refresh/*.png branding/logo-refresh/ten-logo-directions.jpg` gives exact file byte lengths, and `file branding/logo-refresh/*.png branding/logo-refresh/ten-logo-directions.jpg` reads dimensions from headers. The PNG dimensions were also read directly from IHDR. All entries contain `id`, `name`, `path` and `prompt` only (`prompts-and-files.json:1–62`); the prompts' `Square 1024px presentation` wording is a request, not measured output metadata. The gallery declares neither native pixel dimensions nor expected byte counts (`gallery.html:1`).

## R2. Missing entries, files and gallery targets

| Check | Finding | Anchor |
| --- | --- | --- |
| JSON entries with no file at the recorded path in a checkout | All 10 (`/0/path` through `/9/path`) point outside the checkout. This check did not look for those files on the original machine. | `prompts-and-files.json:1–62` |
| JSON entries with no matching local basename | None. No duplicate basename or ID. | R1 row pointers; parser results below |
| Direction PNGs with no JSON entry | None. | R1; parser results below |
| Other files with no JSON entry | `build-review.cjs`, `gallery.html`, `prompts-and-files.json`, `ten-logo-directions.jpg`. The JPEG is the generated contact sheet, not an eleventh direction: **422,032 bytes, 1400 × 2600**. | `git ls-tree` and `file` commands in R1; `build-review.cjs:3` |
| Unresolved gallery references | None; 10 `href` and 10 `src` references each name a present PNG beside the gallery, so there is no broken line to quote. Example from `gallery.html:1`: `<a href="01-coastal-shack.png"><img src="01-coastal-shack.png" alt="Coastal Shack"></a>`. | `gallery.html:1`; parser results below |

Read-only parser output, 2026-11-21 (compared JSON basenames and every HTML `href`/`src` to the same-folder file list):

```text
Files, direction PNGs, JSON entries, gallery refs: 14 10 10 20
Absolute JSON paths (indices only): [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
Locally missing JSON basename targets: []
Files without JSON basename: ['build-review.cjs', 'gallery.html', 'prompts-and-files.json', 'ten-logo-directions.jpg']
Duplicate JSON basenames, duplicate IDs: [] []
JSON entries with 1024px prompt: 10
Gallery unresolved count: 0
Gallery href/src match sorted PNGs: True
Gallery alt/heading match JSON names: True True
JSON order: 03, 01, 02, 04, 05, 06, 08, 07, 09, 10
```

## R3. What `build-review.cjs` reads and writes

| Access | Names | Anchor |
| --- | --- | --- |
| Loads | `fs`, `sharp` | `build-review.cjs:1` |
| Reads | `branding/logo-refresh/`, the ten numbered PNGs listed in R1 | `build-review.cjs:3` |
| Writes | `ten-logo-directions.jpg`, `gallery.html` | `build-review.cjs:3` |
| Does not read or write | `prompts-and-files.json` | `build-review.cjs:1–3` |

Source inspected only; the builder was not run.

## R4. Ranked gaps and one possible follow-up

1. **Manifest paths are not portable.** All ten `path` fields point outside the checkout even though all ten basenames are present (R2; `prompts-and-files.json:/0/path` through `/9/path`).
2. **The builder is tied to a machine-specific dependency path.** The `sharp` import uses an absolute path, so a plain checkout does not supply that dependency at the location named by the script (`build-review.cjs:1`). No build failure was tested.
3. **Prompt size differs from PNG size.** The saved files are uniformly 1254 × 1254, not the requested 1024 × 1024. This is an observed difference, not a finding about the visual design or a reason to rescale the files (`prompts-and-files.json:/0/prompt` through `/9/prompt`; R1).

The different array order is not a broken mapping: the gallery uses numbered filename order and the builder sorts the filenames and uses its own label list, rather than reading JSON order (`gallery.html:1`; `build-review.cjs:2–3`; R2).

**One proposed unit, not performed (estimate: 45 minutes):** Make the ten `path` values in `branding/logo-refresh/prompts-and-files.json` relative to the manifest's directory. Touch only that file in the follow-up. Offline test: parse the candidate manifest, require ten distinct relative sibling paths that resolve to the exact PNG set in R1, and compare all non-`path` fields and record order with the base. On in-memory copies, substitute one missing filename and one absolute path and require both to fail. No regeneration or logo decision is needed.
