# Hass and storefront TODO marker inventory

| Question | Result |
| --- | --- |
| R1 — Markers | 4 `TODO` placeholders, all in the offline regression-case scaffolder. No `FIXME`, `XXX` or `HACK` work markers. Four related mentions are listed separately. |
| R2 — Named missing functions, files or tests | None. The placeholders ask for values in a generated case, not named missing artifacts. |
| R3 — Concentration | `scripts/hass/`: 4; `hass/`: 0; `storefront-mockup/`: 0. |
| R4 — Ranked gaps | One group of unfinished scaffold fields, ranked below in case-writing order. No build unit needed on this evidence. |

Audited 2026-11-21. The fresh clone's `git rev-parse origin/main` returned `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, the stated baseline. All source anchors below are at that commit. The scan covered tracked Hass Python, CommonJS and HTML templates, all tracked text scripts under `scripts/hass/`, and tracked JS, CommonJS, Python, HTML and CSS in the current storefront, excluding its archive. It did not inspect historical `commerce/`, data, binaries or live state. `AGENTS.md:3–5,13–16` sets the current-source and privacy boundaries. `git ls-tree -r --name-only origin/main -- reports/hass-npp` printed nothing; the referenced G-questions file is not on this snapshot. This audit uses the task's stated limits and does not infer any missing owner answers.

## R1. Every marker, with blame date and age

There were no matching source comments. The four markers are string values deliberately emitted into a starter case; the quoted text below is the exact value. To reproduce the candidates (including the related mentions), run from the clone at the pinned `origin/main`:

```sh
 git grep -nI -E '(^|[^[:alnum:]_])(TODOs?|FIXMEs?|XXX|HACK)([^[:alnum:]_]|$)|\\b(TODO|FIXME|XXX|HACK)\\b' origin/main -- \
   ':(glob)hass/**/*.py' ':(glob)hass/**/*.cjs' ':(glob)hass/templates/**/*.html' scripts/hass \
   ':(glob)storefront-mockup/**/*.js' ':(glob)storefront-mockup/**/*.cjs' ':(glob)storefront-mockup/**/*.py' \
   ':(glob)storefront-mockup/**/*.html' ':(glob)storefront-mockup/**/*.css' ':(exclude)storefront-mockup/archive'
```

The command returned seven lines. A broader substring search also hit words like `SHACK` and identifiers containing it; those are not markers. The reference-only check `git grep -nI -E 'TODOs?|FIXMEs?|XXX|HACK' origin/main -- ':(glob)docs/hass/*.md'` had no output (exit 1). Docs are not counted as code.

| File:line | Marker | Quoted text | Blamed commit date | Age (calendar days) |
| --- | --- | --- | --- | ---: |
| `scripts/hass/npp_case_new.py:49` | `TODO` | `TODO: describe the contract this regression protects` | 2026-11-20 | 1 |
| `scripts/hass/npp_case_new.py:50` | `TODO` | `TODO: describe the bug that makes the case fail` | 2026-11-20 | 1 |
| `scripts/hass/npp_case_new.py:55` | `TODO` | `TODO: replace with a synthetic turn` | 2026-11-20 | 1 |
| `scripts/hass/npp_case_new.py:58` | `TODO` | `TODO` | 2026-11-20 | 1 |

Related mentions, not additional unfinished work:

| File:line | Word | Quoted text | Why not a work marker | Blamed commit date | Age (calendar days) |
| --- | --- | --- | --- | --- | ---: |
| `scripts/hass/npp_case_new.py:2` | `TODOs` | `Start an offline NPP regression case; replace all TODOs before committing it.` | Docstring explaining the starter fields | 2026-11-20 | 1 |
| `hass/tests/test_npp_case_new.py:85` | `TODO` | `'TODO' != 'asking'` | Expected assertion failure for an unfinished case | 2026-11-20 | 1 |
| `hass/tests/test_publish.py:44` | `TODO` | `\bTODO\b` | Regex alternative in a publication test | 2026-11-03 | 18 |
| `hass/tests/test_publish.py:44` | `FIXME` | `\bFIXME\b` | Second alternative in the same regex | 2026-11-03 | 18 |

Blame and date checks (age is the date difference from 2026-11-21, not elapsed hours):

```sh
git blame --date=short -L 49,58 origin/main -- scripts/hass/npp_case_new.py
git blame --date=short -L 2,2 origin/main -- scripts/hass/npp_case_new.py
git blame --date=short -L 85,85 origin/main -- hass/tests/test_npp_case_new.py
git blame --date=short -L 44,44 origin/main -- hass/tests/test_publish.py
git show -s --format='%H %as %cs' 6c00e2fd3 0a064f71a9
```

The author and committer calendar dates agree for both blamed commits.

## R2. Confirmed missing named functions, files or tests

None. The quoted markers at `scripts/hass/npp_case_new.py:49–58` request a contract description, bug description, synthetic turn and expected state for the next case. None specifies a missing artifact by name. As a cross-check, the scaffolder and the tests that identify or reject its unfinished state are present:

```sh
git grep -nI -e 'def scaffold(' -e 'def test_c3_unfinished_fails(' \
  -e 'def test_expect_keys_and_checks_are_in_the_documented_vocabulary(' origin/main -- \
  scripts/hass/npp_case_new.py hass/tests/test_npp_case_new.py hass/tests/test_npp_assets.py
```

Output (2026-11-21):

```text
origin/main:hass/tests/test_npp_assets.py:774:    def test_expect_keys_and_checks_are_in_the_documented_vocabulary(self):
origin/main:hass/tests/test_npp_case_new.py:76:    def test_c3_unfinished_fails(self):
origin/main:scripts/hass/npp_case_new.py:18:def scaffold(cases, day, words, path, title):
```

`hass/tests/test_npp_case_new.py:79–91` expects the unfinished question case to fail this check, then replaces the placeholder with the case's terminal state and runs the check again. The comparison is at `hass/tests/test_npp_assets.py:787`. These were source reads, not test runs.

## R3. Counts by directory and top files

Counting R1 by occurrence, with related mentions broken out (both alternatives at `test_publish.py:44` count as separate mentions):

| Directory (recursive) | TODO | FIXME | XXX | HACK | Related mentions (not markers) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `hass/` | 0 | 0 | 0 | 0 | 3 (all in `hass/tests/`) |
| `scripts/hass/` | 4 | 0 | 0 | 0 | 1 |
| `storefront-mockup/` | 0 | 0 | 0 | 0 | 0 |
| **Total** | **4** | **0** | **0** | **0** | **4** |

| Rank by marker count | File | Markers | Related mentions |
| --- | --- | ---: | ---: |
| 1 | `scripts/hass/npp_case_new.py` | 4 | 1 |

Only one file has a nonzero marker count, so there are no meaningful places 2–5. For the broader count including mentions, the same file leads with 5, followed by `hass/tests/test_publish.py` with 2 and `hass/tests/test_npp_case_new.py` with 1. The R1 scan and tables reproduce both counts.

## R4. Ranked gaps and build decision

This is case-writing order, not a product priority or severity ranking:

1. **Define the regression contract and the bug that would break it.** `scripts/hass/npp_case_new.py:49–50` leaves both descriptions open.
2. **Supply a synthetic turn that exercises that bug.** `scripts/hass/npp_case_new.py:55` emits a placeholder instead of a scenario.
3. **Set the expected state for that scenario.** `scripts/hass/npp_case_new.py:57–58` leaves the state unfinished; `hass/tests/test_npp_case_new.py:76–91` explicitly checks that it is rejected until filled in.

No build unit is needed on this evidence: all four values belong to a future, specific regression case, and the existing scaffolder and unfinished-state check already exist. No product behavior, policy or owner decision was evaluated or changed.
