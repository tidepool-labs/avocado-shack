# Hass README index drift

| Check | Result |
| --- | --- |
| R1 · Coverage | The index links 12 of 54 other tracked files. It omits 42, including all 14 skill documents and `capabilities.json`. |
| R2 · Broken links | No broken local targets or anchors in the Hass index. No broken Hass targets in the root READMEs. Five external issue links were not checked live. |
| R3 · Outdated purpose | One clear mismatch: the Clover pointer calls the guide a design and prototype, but the guide opens with a built, fixture-tested read-only connection. |
| R4 · Proposed additions | 42 proposed rows and one README-only follow-up. Nothing in the index changed in this audit. |

**Source:** `tidepool-labs/avocado-shack` `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, read offline on 2026-11-21 after cloning. Compared with the brief's `1f8510907cb2989bb50391fde45d6211e4735879`: no change to `docs/hass/`, the root READMEs or `AGENTS.md`; the full diff between those commits adds three scripts and three tests, not docs. The brief's `reports/hass-npp/G-QUESTIONS.md` is not tracked at either pin; this audit requires no answers from it and changes no decisions or behavior. Open PRs, live services and hosted URLs were not audited. All line references below are at the audited main.

## R1. Files missing from the index

`docs/hass/README.md` is the index, not a document it needs to link to itself. Of the 55 tracked files, 12 distinct targets are directly linked: `CLOVER`, `COMMANDS`, `CONNECT`, `FEATURES`, `HANDOVER`, `HERMES_START`, `IMPLEMENTATION`, `LIMITS`, `NATURAL_LANGUAGE`, `PHONE_GUIDE`, `SUPPORT` and `TRIAL` (all `.md`; link source lines in R2).

The last column gives **all local clickable backlinks found** from other tracked Markdown docs, plus selected non-clickable path mentions (`mention`). The three root TXT paths are covered in R2. A dash means no clickable backlink or useful path mention listed, not no topical discussion. `TASKMAP.md` has no clickable backlink to an omitted file; it names `SKILLS.md` and `skills/item_add.md` in work rows at lines 889 and 905. The four omitted files reachable by following links from the Hass README through other Hass docs are `CAPABILITIES.md` via `COMMANDS.md:65`, `MAC_RUNBOOK.md` via `CONNECT.md:22`, and `RETENTION-OPTIONS.md` and `SIGNUP-OPTIONS.md` via `HANDOVER.md:27,31`. Other inbound links below do not imply a route from the Hass README.

Paths and source anchors without a `docs/hass/` prefix are relative to that directory, except `BUILD_LEDGER.md` and paths beginning `reports/` or `hass/`, which are repo-relative. The date is the last-change commit's **committer** date, not the file's modification time.

| Omitted path | First heading (source line) | Last changed | Other links and useful path mentions |
| --- | --- | --- | --- |
| `AUDIT.md` | The audit log (AVB-10) · 1 | 2026-11-13 | Mention: `COMMANDS.md:34` |
| `BRIDGE_WIRING.md` | Hass bridge wiring: BlueBubbles, the Mac forwarder and AgentOrange (HASS-MAC-KIT-1) · 1 | 2026-11-09 | `MAC_MINI_FINAL_STEPS.md:71` |
| `CAPABILITIES.md` | What Hass can do · 1 | 2026-11-14 | `COMMANDS.md:65`, `SKILLS.md:76` |
| `CLOVER-COUNT-PHRASES.md` | Clover count phrases: offline baseline · 1 | 2026-11-20 | — |
| `HIKE-LOOKUP.md` | Hike lookup: name a hike, Hass finds it, proposes it, then builds the page (HASS-HIKE-LOOKUP-1) · 1 | 2026-11-13 | Mention: `skills/hikes.md:148` |
| `HIKE-PAGE.md` | The hike page, spots left and RSVPs (design, HASS-HIKEPAGE-1) · 1 | 2026-11-13 | Mention: `HIKE-LOOKUP.md:63,237` |
| `HIKE-SIGNUP-DESIGN.md` | Real guest sign-up for hikes: what it needs, options, recommendation (HASS-CHAT-1, design only) · 1 | 2026-11-09 | — |
| `INSTALL-LIVE-FIX-2.md` | Install note: one listing, a supplier line, and styled product photos · 1 | 2026-11-17 | `BUILD_LEDGER.md:12` |
| `ITEM-STANDARD.md` | The item standard (HASS-ITEMSTD-1, version 1, DRAFT until G answers the decisions in reports/hass/ITEMSTD-1.md) · 1 | 2026-11-08 | Mention: `reports/hass/ITEMSTD-1.md:4` |
| `MAC_MINI_FINAL_STEPS.md` | Hass Mac mini: G's final steps (HASS-MAC-KIT-1) · 1 | 2026-11-07 | `BRIDGE_WIRING.md:56` |
| `MAC_RUNBOOK.md` | Hass: G-only Mac-to-live runbook · 1 | 2026-11-16 | `BRIDGE_WIRING.md:4`, `CONNECT.md:22`, `MAC_MINI_FINAL_STEPS.md:5` |
| `NEW-ITEM-FLOW.md` | New item from a photo: what exists and how it fits (HASS-LIVE-ADD-2) · 1 | 2026-11-16 | Mention: `PHONE_GUIDE.md:24` |
| `NPP-EDIT-PHRASES.md` | Hass listing edits: grammar-only baseline · 1 | 2026-11-21 | — |
| `NPP-OWNER-GUIDE.md` | List a product with Hass · 1 | 2026-11-20 | — |
| `NPP-SECOND-PRODUCT.md` | What happens when another product photo arrives? · 1 | 2026-11-20 | — |
| `OPERATIONS.md` | Running Hass on AgentOrange (HASS-SVC-1) · 1 | 2026-11-16 | Mention: `reports/hass/HASS-LIVE-AUDIT-1.md:136` |
| `PHOTOS.md` | Product-photo detail reads · 1 | 2026-11-16 | — |
| `PILLOW-HOST.md` | Pillow on the Hass host (operator steps) · 1 | 2026-11-08 | `NEW-ITEM-FLOW.md:18` |
| `POS.md` | Hass till views (HASS-POS-1) · 1 | 2026-11-19 | — |
| `PUBLISHING.md` | Hass live publishing (HASS-PUBLISH-1) · 1 | 2026-11-09 | Mention: `reports/hass/HIKEPAGE-1.md:40,63` |
| `RETENTION-OPTIONS.md` | How long to keep private data (H21) - options and questions · 1 | 2026-11-16 | `HANDOVER.md:27`, `SIGNUP-OPTIONS.md:70` |
| `RUNTIME-RELEASE.md` | One-command Hass runtime release (AVB-04) · 1 | 2026-11-14 | `OPERATIONS.md:4` |
| `SANDBOX.md` | One per-target sandbox switch (AVB-11) · 1 | 2026-11-13 | Mention: `BUILD_LEDGER.md:2278` |
| `SIGNUP-OPTIONS.md` | Signup options — an open decision · 1 | 2026-11-15 | `HANDOVER.md:31` |
| `SKILLS.md` | Hass skills: authoring guide · 1 | 2026-11-14 | Mentions: `TASKMAP.md:889`, `skills/item_add.md:6` |
| `TASKMAP.md` | Hass task map: every everyday job as a skill (HASS-TASKMAP-1) · 1 | 2026-11-08 | `reports/hass/TASKMAP-1.md:4`; mention: `CLOVER.md:8` |
| `VOICE.md` | How Hass talks to Mike (HASS-VOICE-1) · 1 | 2026-11-20 | Mentions: `ITEM-STANDARD.md:95`, `SKILLS.md:133` |
| `capabilities.json` | No heading (JSON object at line 1) | 2026-11-16 | Mentions: `CAPABILITIES.md:3`, `SKILLS.md:76` |
| `skills/front.md` | Front-end skills, part 1 (AVB-19-B1) · 1 | 2026-11-14 | Mention: `hass/tests/fixtures/skills-acceptance/README.md:80` |
| `skills/hass-npp-maintain/SKILL.md` | Maintain the Hass new-product pipeline assets · 6 | 2026-11-18 | Mention: `hass/npp/assets/README.md:20` |
| `skills/hass-npp-review/SKILL.md` | Weekly review of the Hass new-product pipeline · 6 | 2026-11-18 | — |
| `skills/hikes.md` | Hike skills (SKILLS-HIKES-1) · 1 | 2026-11-13 | Mention: `reports/hass/HIKEPAGE-1.md:18,60` |
| `skills/item_add.md` | Add a new item: `item.add` · 1 | 2026-11-16 | `NEW-ITEM-FLOW.md:6`; mention: `TASKMAP.md:905` |
| `skills/item_picture.md` | Item picture: put a new photo on one product · 1 | 2026-11-09 | Mention: `reports/hass/SKILLS-SPEC.md:608` |
| `skills/items.md` | Items: hide, restore and edit a product · 1 | 2026-11-08 | Mention: `reports/hass/SKILLS-SPEC.md:599` |
| `skills/makers.md` | Maker skills: add, edit, hide and restore a maker and their about text · 1 | 2026-11-10 | Mention: `reports/hass/ITEMSTD-1.md:81` |
| `skills/reports.md` | Shelf report skill (SKILLS-SOCIAL-1 part 3, AV1109-08) · 1 | 2026-11-10 | — |
| `skills/restock.md` | Stock restock: note when more of a product is coming · 1 | 2026-11-09 | Mention: `reports/hass/SKILLS-SPEC.md:601` |
| `skills/shop.md` | Shop and page skills (SKILLS-SHOP-1) · 1 | 2026-11-10 | Mention: `reports/hass/SKILLS-SPEC.md:604` |
| `skills/social.md` | Social caption skills (social.item, social.hike, social.maker, social.recap) · 1 | 2026-11-09 | Mention: `reports/hass/SKILLS-SPEC.md:605` |
| `skills/specials.md` | Weekly specials skills (SKILLS-SPECIALS-1) · 1 | 2026-11-08 | Mention: `hass/tests/fixtures/skills-acceptance/README.md:79` |
| `skills/stock.md` | Stock skills: what is on the shelf (SKILLS-STOCK-1) · 1 | 2026-11-16 | Mention: `CLOVER.md:22,27` |

## R2. Broken targets or anchors

| Source | Occurrences checked | Broken |
| --- | --- | --- |
| `docs/hass/README.md:43,55–60,66–68,71,85,91` | 18 local links (repeats included); both fragments resolve: `#bridge-research-and-open-questions` → `docs/hass/IMPLEMENTATION.md:130`; `#later-store-manager-work` → `docs/hass/FEATURES.md:55`. The other 16 have no fragment. | None |
| `README.md:11–20,33` | 13 Markdown links into `docs/hass/`; all are tracked files with no fragment. | None |
| `README.txt:3–5` | 3 plain paths (`README.md`, `HERMES_START.md`, `FEATURES.md` under `docs/hass/`), all tracked. These are text references, not Markdown links. | None |
| `docs/hass/README.md:55,66–69` | 5 external links to the issue list and four issues on the old repository path, not this clone's origin. The root `README.md:25` also points to the old issue list, not into `docs/hass/`. | Not determined offline. A different repository path is not proof of a dead link. |

## R3. Purpose that no longer matches the opening

| Index wording | Destination opening | Drift |
| --- | --- | --- |
| `docs/hass/README.md:85`: “The Clover (items and stock) design and prototype is CLOVER.md.” The next line frames the integrations as “later projects.” | `docs/hass/CLOVER.md:3–5`, opening paragraph excerpt: “READ-ONLY connection to the real store, built and fixture-tested; the operator turns it on after review and merge”; “HASS-CLOVER-3 adds an unconnected fixture-qualified engine; HASS-CLOVER-4 wiring and live enablement remain separately gated.” | “Design and prototype” misses the distinction between an already built read-only path and separately gated work. This is a documentation comparison, not evidence the connection is live. |

The other index pointers still identify the subjects of their destinations. A shorter description is not drift just because the guide adds details: e.g. the phone guide covers the tasks advertised at `docs/hass/README.md:58` (sections at `docs/hass/PHONE_GUIDE.md:6,27,34,47,72,81`), and the owner trial is still labeled a proposal in both `docs/hass/README.md:60` and `docs/hass/TRIAL.md:3`.

## R4. Proposed rows (not applied)

These destinations are relative to `docs/hass/README.md`. Each row uses the file and heading cited in R1. Operator, draft, fixture and generated references should be labeled as such, not as features verified live.

> | Link label | Destination | One-line purpose |
> | --- | --- | --- |
> | Audit log | `AUDIT.md` | Describes the audit record and its limits. |
> | Bridge wiring | `BRIDGE_WIRING.md` | Technical reference for the bridge and relay components. |
> | What Hass can do | `CAPABILITIES.md` | Generated human-readable capability list. |
> | Clover count phrases | `CLOVER-COUNT-PHRASES.md` | Offline baseline for count wording. |
> | Hike lookup | `HIKE-LOOKUP.md` | How a named hike is found and proposed before the page is built. |
> | Hike page design | `HIKE-PAGE.md` | Design for the hike page, remaining spots and RSVPs. |
> | Guest sign-up design | `HIKE-SIGNUP-DESIGN.md` | Design options for real hike sign-up. |
> | Installation note | `INSTALL-LIVE-FIX-2.md` | Installation reference for the listing, supplier line and photo changes. |
> | Item standard | `ITEM-STANDARD.md` | Draft standard for product information. |
> | Mac mini final steps | `MAC_MINI_FINAL_STEPS.md` | Owner/operator reference for final bridge setup. |
> | Mac-to-live runbook | `MAC_RUNBOOK.md` | G-only runbook for connecting the Mac to live Hass. |
> | New item from a photo | `NEW-ITEM-FLOW.md` | How the photo-led item flow fits together. |
> | Listing edit phrases | `NPP-EDIT-PHRASES.md` | Grammar-only baseline for editing listing fields. |
> | List a product with Hass | `NPP-OWNER-GUIDE.md` | Owner guide for preparing and reviewing a product listing. |
> | A second product photo | `NPP-SECOND-PRODUCT.md` | Offline findings and undecided options for another photo. |
> | Operations | `OPERATIONS.md` | Operator reference for running Hass. |
> | Photo detail reads | `PHOTOS.md` | Reference for reading detail from product photos. |
> | Pillow setup | `PILLOW-HOST.md` | Operator reference for the host's image dependency. |
> | Till views | `POS.md` | Reference for Hass's point-of-sale views. |
> | Publishing | `PUBLISHING.md` | Describes Hass's live publishing path. |
> | Retention options | `RETENTION-OPTIONS.md` | Options and open questions about retaining private data. |
> | Runtime release | `RUNTIME-RELEASE.md` | Reference for the operator's runtime release command. |
> | Per-target sandbox | `SANDBOX.md` | Describes the sandbox switch for each target. |
> | Signup options | `SIGNUP-OPTIONS.md` | Lists signup options for an open decision. |
> | Skill authoring guide | `SKILLS.md` | How skills are defined, checked and registered. |
> | Task map | `TASKMAP.md` | Maps everyday jobs to proposed or existing skills. |
> | Voice guide | `VOICE.md` | Describes Hass's conversational writing style. |
> | Capability data | `capabilities.json` | Generated machine-readable capability list (`SKILLS.md:74–79`). |
> | Front-end skills | `skills/front.md` | Reference for the first set of front-end skills. |
> | Maintain pipeline assets | `skills/hass-npp-maintain/SKILL.md` | Maintainer guide for new-product pipeline assets. |
> | Review the pipeline | `skills/hass-npp-review/SKILL.md` | Guide for the weekly new-product pipeline review. |
> | Hike skills | `skills/hikes.md` | Reference for the hike skill group. |
> | Add an item | `skills/item_add.md` | Reference for `item.add`. |
> | Change an item picture | `skills/item_picture.md` | Reference for replacing a product photo. |
> | Item skills | `skills/items.md` | Reference for hiding, restoring and editing items. |
> | Maker skills | `skills/makers.md` | Reference for maker records and their about text. |
> | Shelf report skill | `skills/reports.md` | Reference for the shelf report. |
> | Restock skill | `skills/restock.md` | Reference for recording an expected restock. |
> | Shop and page skills | `skills/shop.md` | Reference for shop and page edits. |
> | Social captions | `skills/social.md` | Reference for composing draft social captions. |
> | Weekly specials skills | `skills/specials.md` | Reference for weekly specials. |
> | Stock skills | `skills/stock.md` | Reference for what is on the shelf. |

**One follow-up (estimate: 60–90 minutes):** edit only `docs/hass/README.md` to add the rows above and clarify the Clover pointer using R3. Offline acceptance: resolve the updated index's relative destinations and fragments against the tracked tree, require each of the 54 non-index files to have a working direct link, and check that `git diff --check` is clean and the index is the only changed file. No CI checker, code or runtime change is needed for that follow-up.

### Reproduce offline

Run from the repo root. The commands use Bash; set `base` to the full audited main SHA so later changes to `origin/main` cannot shift the results. For R1, subtract the normalized Hass README link destinations (drop fragments and external URLs) and the index itself from the tree listing. The heading/date command takes one repo-relative `path` at a time. The final search shows backlinks and plain mentions for that file; use `skills/<skill-dir>/SKILL.md` rather than the shared basename for the two nested skills. Check each backlink relative to the source document; backticks by themselves do not make a link. The audit checked inline Markdown links, not content in fenced examples or external URLs, and inspected the link syntax for reference definitions and HTML links.

```sh
base=37feae1dc5efa6968f90d17a1eda6daed29afd4a
brief=1f8510907cb2989bb50391fde45d6211e4735879
git diff --name-status "$brief" "$base"
git ls-tree -r --name-only "$base" -- docs/hass
git grep -n -E '\]\(|^[[:space:]]*\[[^]]+\]:|href=|docs/hass/' "$base" -- docs/hass/README.md README.md README.txt
git grep -n -E '^## (Bridge research and open questions|Later store-manager work)$' "$base" -- docs/hass/IMPLEMENTATION.md docs/hass/FEATURES.md
git grep -n -E '^#{1,6} ' "$base" -- "$path" | head -n 1
git log -1 --format=%cs "$base" -- "$path"
git grep -n -F "$filename" "$base" -- '*.md' '*.txt'
```

For R3, `git show "$base:docs/hass/README.md" | nl -ba` and `git show "$base:docs/hass/CLOVER.md" | nl -ba` give the quoted lines and their context. None of these checks verifies deployment, approved wording, or live behavior.
