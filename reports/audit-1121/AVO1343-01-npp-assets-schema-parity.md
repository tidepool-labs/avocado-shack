# AVO1343-01 — New-product pipeline asset and schema audit

| Check | Result at `37feae1dc5efa6968f90d17a1eda6daed29afd4a` |
|---|---|
| R1 · What gets read? | 43 files in nine skill folders plus the root README. The pin loader opens and hash-checks all 43; 17 have a downstream NPP consumer and 26 are hash-checked only within NPP. |
| R2 · What is missing? | No missing runtime asset or bad hash. The references absent from this tree are for replay, judging, documentation or private evidence, not stage inputs. One missing replay runner is required by the install preflight. |
| R3 · Do the examples fit? | 12 gallery goldens, four synthetic calibration cards and six identify outputs pass required-key and type checks. Three schemas have no matching output-fixture JSON in their asset folders. |
| R4 · What matters first? | Resolve the replay/preflight gap before treating an asset check as release readiness. No runtime asset repair is indicated by this audit. |

Checked 2026-11-21 on the public repository's `origin/main`, exactly the supplied baseline (`git rev-parse origin/main HEAD` before the report commit). This is an offline source audit, not a site, model, judge, live Hass or installed-release check. The brief's `reports/hass-npp/G-QUESTIONS.md` is not tracked at this input (`git ls-files -- reports/hass-npp/G-QUESTIONS.md`); no private copy was sought. The audit does not make owner, policy, claim or publication decisions.

## R1. Every tracked asset and its reader

**Every row has the same disk opener:** `hass/npp/__init__.py:16–23` (path at line 17, read at line 20). The `pins.json` line identifies the key driving that open. `hass/conversation.py:549–557` calls the loader only on the NPP-enabled initialization path. The last column shows who uses the already-read content, not who opens it again. **Hash only** means unread *as content* by the pipeline after the required pin check; it does not mean unused by tests, tools or people. Module paths in that column are relative to `hass/npp/`.

| Folder under `hass/npp/assets/` | File | `hass/npp/pins.json` line | Downstream NPP consumer |
|---|---|---:|---|
| (root) | `README.md` | 76 | Hash only |
| `hass-gallery-style` | `SKILL.md` | 77 | Hash only |
| `hass-gallery-style` | `card.schema.json` | 78 | Hash only |
| `hass-gallery-style` | `gallery-fields.tsv` | 79 | Hash only |
| `hass-gallery-style` | `golden/photo-product-002.json` | 80 | Hash only |
| `hass-gallery-style` | `golden/photo-product-006.json` | 81 | Hash only |
| `hass-gallery-style` | `golden/photo-product-007.json` | 82 | Hash only |
| `hass-gallery-style` | `golden/photo-product-015.json` | 83 | Hash only |
| `hass-gallery-style` | `golden/photo-product-018.json` | 84 | Hash only |
| `hass-gallery-style` | `golden/photo-product-021.json` | 85 | Hash only |
| `hass-gallery-style` | `golden/photo-product-024.json` | 86 | Hash only |
| `hass-gallery-style` | `golden/photo-product-025.json` | 87 | Hash only |
| `hass-gallery-style` | `golden/photo-product-042.json` | 88 | Hash only |
| `hass-gallery-style` | `golden/photo-product-044.json` | 89 | Hash only |
| `hass-gallery-style` | `golden/photo-product-052.json` | 90 | Hash only |
| `hass-gallery-style` | `golden/photo-product-138.json` | 91 | Hash only |
| `hass-gallery-style` | `limits.json` | 92 | `copy.py:110` |
| `hass-listing-copy` | `SKILL.md` | 93 | `copy.py:106` |
| `hass-listing-copy` | `copy-templates.json` | 94 | `copy.py:103` |
| `hass-listing-copy` | `listing.schema.json` | 95 | `copy.py:105` |
| `hass-listing-copy` | `voice-phrases.json` | 96 | `copy.py:104` |
| `hass-listing-edit` | `SKILL.md` | 97 | `edits.py:27,124` |
| `hass-listing-edit` | `edit-grammar.json` | 98 | `edits.py:25,122` |
| `hass-listing-edit` | `edit.schema.json` | 99 | `edits.py:26,123` |
| `hass-maker-research` | `SKILL.md` | 100 | `research_hermes.py:92–96` |
| `hass-maker-research` | `facts.schema.json` | 101 | `research.py:312`, `research_hermes.py:94`, `copy.py:111` |
| `hass-maker-research` | `sources.json` | 102 | `research.py:311`, `stages.py:88` |
| `hass-maker-research` | `verify.md` | 103 | `research_hermes.py:97` |
| `hass-missing-info` | `SKILL.md` | 104 | Hash only |
| `hass-missing-info` | `missing-info.json` | 105 | `missing.py:14,123` |
| `hass-npp-reply` | `reply-templates.json` | 106 | `__init__.py:9,26` parses once; `reply.py:30,46,55,62,68–70,87`, `missing.py:138–139,190` and `job.py:128,313–337` use the parsed rules |
| `hass-product-identify` | `SKILL.md` | 107 | `identify.py:107` |
| `hass-product-identify` | `examples.json` | 108 | `identify.py:106–108` |
| `hass-product-identify` | `identify.schema.json` | 109 | `identify.py:105,107` |
| `hass-product-photo` | `SKILL.md` | 110 | Hash only |
| `hass-product-photo` | `photo.json` | 111 | Hash only |
| `hass-style-judge` | `SKILL.md` | 112 | Hash only |
| `hass-style-judge` | `calibration/bad/bad-invented-story.json` | 113 | Hash only |
| `hass-style-judge` | `calibration/bad/bad-serving-on-nonfood.json` | 114 | Hash only |
| `hass-style-judge` | `calibration/bad/bad-spec-list.json` | 115 | Hash only |
| `hass-style-judge` | `calibration/bad/bad-superlatives.json` | 116 | Hash only |
| `hass-style-judge` | `calibration/manifest.json` | 117 | Hash only |
| `hass-style-judge` | `rubric.json` | 118 | Hash only |

Examples of use outside NPP modules: the limits generator reads the TSV (`scripts/hass/npp_limits.py:27,60–62`); the asset tests read the card schema, goldens and calibration files (`hass/tests/test_npp_assets.py:217–224,683–697`). S6 delegates the picture choice to code (`hass/npp/picture.py:76–89`); the polish call uses the constant in `hass/photo_polish.py:59,120`. A test compares that constant with the photo asset (`hass/tests/test_npp_assets.py:612–617`); this does not make `photo.json` a stage input. The reply folder contains only its template file, not a `SKILL.md`; its reader asks for the template, not a skill file (`hass/npp/__init__.py:9,26`).

Reproduce the inventory and trace from the repo root:

```sh
 git ls-files -- hass/npp/assets
 git grep -nE 'read_bytes|read_text|open\(|glob\(|assets\[|files\[|pinned\[1\]' -- ':(glob)hass/npp/**/*.py'
 python3 -B scripts/hass/npp_limits.py pins --check
```

The audit's local `pathlib`/`json`/`hashlib` check on 2026-11-21 printed: `files 43 folders 9 pins 43`; `unpinned [] missing pins []`; `digest mismatches []`. It compared tracked asset paths to `/assets` in `hass/npp/pins.json` and hashed the bytes of each pin target.

## R2. Missing paths referenced by code or a skill

The R1 trace resolves every literal or assembled filename requested by the NPP asset consumers to a tracked, pinned file. I also checked the references in all tracked `SKILL.md` files, resolving sibling paths within their skill and named cross-skill assets relative to `hass/npp/assets/`. The catalog references such as `producers.json` (`hass-maker-research/SKILL.md:17`) resolve under `storefront-mockup/`. There is no missing runtime asset. The public tree does lack the following nearby references; these are not equivalent to missing pin targets.

| Absent from this checkout | Quoting line at the baseline | What the absence means |
|---|---|---|
| `hass/tests/npp/run_npp.py` | `docs/hass/skills/hass-npp-maintain/SKILL.md:24`: “`hass/tests/npp/run_npp.py`, once NPP-H has landed”; `scripts/hass/npp_preflight.py:32`: `"hass/tests/npp/run_npp.py"` | Documented future replay runner, already in the preflight's required stage list. The tree alone lacks one required member (`scripts/hass/npp_preflight.py:176–193`); no installed release was inspected. |
| `npp_eval.py` (no tracked path by this basename) | `hass/npp/assets/hass-style-judge/SKILL.md:9`: “`npp_eval.py --judge` (NPP-H)”; `docs/hass/skills/hass-npp-maintain/SKILL.md:29`: “`npp_eval.py --judge`, calibration first” | Documented private-host judge entry point; absence here does not establish private-host availability. |
| `hass/tests/npp/tapes/judge/`; `metrics.tsv` (no tracked path by this basename) | `hass/npp/assets/hass-style-judge/SKILL.md:20–21`: “the reason goes to `metrics.tsv`. Commit the recorded scores under `hass/tests/npp/tapes/judge/`” | Outputs, not fixture or runtime inputs. The review skill points to an out-of-repo metrics file (`docs/hass/skills/hass-npp-review/SKILL.md:20`); not inspected. |
| `reports/hass-npp/PIPELINE-DESIGN.md` | `docs/hass/skills/hass-npp-maintain/SKILL.md:11`: “`reports/hass-npp/PIPELINE-DESIGN.md` (sections 2 and 4)” | Missing design reference in this checkout, not a loader input. |
| `shots/`, `g-examples/`, `g-examples/site-gallery-today.jpg`, `g-examples/hass-reply-today.jpg` (relative to the gallery study) | `hass/npp/assets/hass-gallery-style/SKILL.md:12`: “screenshots in `shots/`. The supplied owner examples are `g-examples/site-gallery-today.jpg` and `g-examples/hass-reply-today.jpg`”; lines 124–125: “stay in the private report folder and are not runtime assets” | Intentional exclusions. No private images or historical site were checked. |

The manifest's actual public inputs all exist: `hass/npp/assets/hass-style-judge/calibration/manifest.json#/good` and `#/bad`, joined with `#/good_dir` and `#/bad_dir` and a `.json` suffix, name exactly the 12 goldens and four calibration cards in R1. `#/private_host_extras` is not a public fixture list. `storefront-mockup/assets/products/photo-product-NNN.webp` in the gallery skill at line 56 is a filename pattern, not a literal asset needed by an NPP module. The review skill's `<mediaRoot>/npp/<job-id>/receipt.json` (line 14) is a runtime path pattern, not a repo dependency.

Reproduce the reference scan and the two tracked-path checks below. Both `ls-files` commands returned no paths on 2026-11-21.

```sh
 git grep -nE -o '`[^`]+`|\]\([^)]+\)' -- ':(glob)**/SKILL.md'
 git ls-files -- hass/tests/npp/run_npp.py hass/tests/npp/tapes/judge reports/hass-npp/PIPELINE-DESIGN.md ':(glob)**/npp_eval.py' ':(glob)**/metrics.tsv'
 git ls-files -- hass/npp/assets/hass-gallery-style/shots hass/npp/assets/hass-gallery-style/g-examples
```

## R3. Required keys and types in schema-matched fixtures

The independent Python standard-library check parsed all 32 asset JSON files. For each matching fixture, it walked the schema in this order: test `type` (including unions; a boolean is not a number), then check object `required` keys, then walk present `properties` in schema order or array `items` by index. Object requirements do not apply to `null`. It returns the first mismatch at a JSON pointer, naming the missing key or expected and actual types, without quoting fixture values. Synthetic controls rejected a boolean in a number field and a missing nested key and accepted a permitted `null`. No comparison below produced a violation to quote.

| Schema (paths relative to `hass/npp/assets/`) | Matching JSON checked; result | Nearby JSON not governed by this schema |
|---|---|---|
| `hass-gallery-style/card.schema.json` (`/required`, `/properties/card`) | All 12 `hass-gallery-style/golden/*.json` and all four `hass-style-judge/calibration/bad/*.json` from R1, at each document root: **16 pass, none fail**. The manifest's `/about` explicitly identifies the shared shape; “bad” denotes a deliberately poor style, not malformed JSON. | `hass-gallery-style/limits.json` is generated limits (`/source`, `/limits`), not a rendered card. `hass-style-judge/calibration/manifest.json` is an index (`/good`, `/bad`); `hass-style-judge/rubric.json` is scoring configuration (`/dimensions`). Neither has a neighboring schema. |
| `hass-listing-copy/listing.schema.json` (`/required`, `/properties`) | **No matching selection-output JSON in the folder.** The skill describes this as the returned selection (`hass-listing-copy/SKILL.md:13–23`). | `copy-templates.json#/templates` and `voice-phrases.json#/phrases` define the inputs the selection points into, not selection outputs. |
| `hass-listing-edit/edit.schema.json` (`/required`, `/properties/patches/items`) | **No matching edit-mapping output JSON in the folder.** The skill distinguishes the grammar and model mapping (`hass-listing-edit/SKILL.md:13–15`). | `edit-grammar.json#/forms` contains grammar rules and embedded input utterances, not model mappings. |
| `hass-maker-research/facts.schema.json` (`/required`, `/properties/facts/items`) | **No matching extracted-facts output JSON in the folder.** The skill names it as typed extraction output (`hass-maker-research/SKILL.md:37–41`). | `sources.json#/discovery` is research configuration, not extracted facts. |
| `hass-product-identify/identify.schema.json` (`/required`, `/properties/confidence`) | `hass-product-identify/examples.json#/examples/0/output` through `/examples/5/output`: **six pass, none fail**. The file is an examples envelope, not itself a single identify output (`hass/npp/identify.py:105–108`). | The envelope and photo references were not schema instances. |

The narrow check did not enforce enums, string lengths or patterns, numeric bounds, item counts, extra-property bans, duplicate JSON keys, or general JSON Schema keywords and references. It did not assess claim truth, prompt behavior or the quality of the card copy. The asset census supplies the list of schemas; having no matching output fixture *beside a schema* is not proof of no tests elsewhere.

As a separate cross-check, these three existing standard-library tests ran offline on 2026-11-21 and returned `Ran 3 tests` / `OK` (their assertions go beyond the narrow check above):

```sh
 python3 -B -m unittest hass.tests.test_npp_assets.GoldenTest.test_goldens_and_bad_cards_match_the_card_schema hass.tests.test_npp_assets.IdentifyAssetsTest.test_identify_examples_validate_against_the_schema hass.tests.test_npp_assets.JudgeAssetsTest.test_rubric_and_calibration_manifest_are_consistent
```

## R4. Ranked gaps

1. **Replay readiness:** The checked-in preflight requires a runner that this tree lacks. That is the one absence with a direct code consequence, when this tree is supplied as the release (`scripts/hass/npp_preflight.py:21–33,176–193`). Do not read the green asset check as a green preflight.
2. **Offline judge and maintenance evidence:** The judge procedure names tooling and outputs not present here; the maintenance skill also points to a design file not in this tree (R2). Local tests prove the calibration files exist and have the expected shape, not that the private judge ran or that its scores are current (`hass/tests/test_npp_assets.py:217–224,683–697`). The private screenshot exclusions are intentional, not gaps to fill.
3. **Fixture availability and provenance:** Three output schemas lack sibling output fixtures (R3). Separately, a valid pin proves bytes were read, not that an asset drove a stage (R1); S6 is the clearest example. Neither observation is a missing runtime input or a demonstrated schema failure.

**No buildable unit is needed within asset/schema parity.** The first gap belongs to replay/preflight scope, and the other findings do not justify changing inputs, inventing fixtures, or wiring offline material into runtime. This audit changes only this report.
