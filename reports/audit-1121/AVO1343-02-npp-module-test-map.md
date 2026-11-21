# New-product pipeline: public definitions and test references

| `hass/npp` module | Public definitions | Definitions with a bound reference | Test files importing module directly |
|---|---:|---:|---:|
| `__init__` | 2 | 2 | 10 |
| `copy` | 8 | 4 | 2 |
| `edits` | 7 | 6 | 3 |
| `evidence` | 3 | 3 | 2 |
| `identify` | 2 | 1 | 2 |
| `job` | 7 | 4 | 11 |
| `missing` | 4 | 2 | 1 |
| `picture` | 3 | 3 | 1 |
| `private_numbers` | 7 | 4 | 4 |
| `receipt` | 4 | 0 | 0 |
| `reply` | 8 | 7 | 2 |
| `research` | 4 | 0 | 0 |
| `research_hermes` | 3 | 2 | 1 |
| `stages` | 3 | 2 | 3 |
| `validate` | 5 | 4 | 3 |
| **Total** | 70 | 44 | — |

**Main audited:** `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, the fetched `origin/main` on 2026-11-21. The table covers the 14 named modules plus the package initializer, shown separately. `research` and `receipt` have no direct test import; both have evidence of exercise through callers (R2). No product change or owner decision is proposed. The brief's `reports/hass-npp/G-QUESTIONS.md` is not tracked at this SHA (`git ls-tree -r --name-only origin/main -- '*G-QUESTIONS*'` returned nothing); the constraints stated in the brief still apply.

## R1. Public functions and classes by module

**Scope and checks (2026-11-21):** `git ls-files -- hass/tests` supplied 911 tracked Python files, of which 901 had a basename starting with `test_` (30 matched `hass/tests/test_npp*.py`). All 911 parsed as Python; only the 901 test files count toward R1. No modules were imported and no tests were collected or run. None of the 30 `test_npp*` stems is a key in `hass/tests/ci_weights.json#/seconds`; the file describes weights as shard balancing, not coverage (`hass/tests/ci_weights.json:3`).

- **Public definition:** a top-level `def`, `async def` or `class` whose name does not start with `_`. Methods and imported names are not additional definitions. Reproduce the definition anchors with `git grep -nE '^(async def|def|class) [A-Za-z]' origin/main -- 'hass/npp/*.py'`.
- **Name mentions:** distinct files containing the exact case-sensitive identifier as a whole word, including imports, comments, strings and unrelated uses. The first witness is in path order. For example, substitute a definition name in `git grep -lwF -e read_artifact origin/main -- ':(glob)hass/tests/**/test_*.py'`; use `-n` instead of `-l` for line anchors.
- **Bound references:** distinct test files with a Python expression referring to the definition through a visible `hass.npp` import binding, not counting import statements themselves. The syntax scan maps each explicit import to its alias or original name and matches loaded names and dotted attributes against those bindings. A match could be a patch target, comparison or call; it is not proof that the function ran or that a useful assertion exists. The scan is not scope- or flow-sensitive and does not follow reassignments, arbitrary dynamic imports, string lookups, or indirect callers. The replay in task scratch is `python3 ../scan_npp.py` from the clone root.

### `__init__`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `assets` (function, `hass/npp/__init__.py:12`) | 131 (`hass/tests/test_again.py:303`) | 10 (`hass/tests/test_npp_caption_table.py:163`) |
| `stages_for` (function, `hass/npp/__init__.py:29`) | 2 (`hass/tests/test_npp_edits.py:211`) | 2 (`hass/tests/test_npp_edits.py:211`) |

### `copy`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `Fact` (class, `hass/npp/copy.py:19`) | 1 (`hass/tests/test_npp_copy.py:8`) | 1 (`hass/tests/test_npp_copy.py:76`) |
| `Context` (class, `hass/npp/copy.py:31`) | 5 (`hass/tests/test_margins_context.py:8`) | 2 (`hass/tests/test_npp_copy.py:26`) |
| `Copy` (class, `hass/npp/copy.py:49`) | 2 (`hass/tests/test_memory_history_cells.py:30`) | none found |
| `codex_selector` (function, `hass/npp/copy.py:56`) | 2 (`hass/tests/test_npp_caption_table.py:132`) | 1 (`hass/tests/test_npp_copy.py:57`) |
| `words` (function, `hass/npp/copy.py:84`) | 167 (`hass/tests/test_answer_reader_request.py:77`) | none found |
| `plain` (function, `hass/npp/copy.py:88`) | 188 (`hass/tests/test_again.py:353`) | none found |
| `eligible` (function, `hass/npp/copy.py:93`) | 5 (`hass/tests/test_health_backup_verify.py:138`) | none found |
| `Writer` (class, `hass/npp/copy.py:99`) | 3 (`hass/tests/test_conversation.py:4`) | 2 (`hass/tests/test_npp_copy.py:22`) |

### `edits`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `Edit` (class, `hass/npp/edits.py:60`) | 4 (`hass/tests/test_again.py:99`) | 2 (`hass/tests/test_npp_edit_phrases.py:21`) |
| `Grammar` (class, `hass/npp/edits.py:116`) | 3 (`hass/tests/test_npp_edit_eval.py:39`) | 3 (`hass/tests/test_npp_edit_eval.py:39`) |
| `valid_mapping` (function, `hass/npp/edits.py:195`) | 1 (`hass/tests/test_npp_edit_eval.py:59`) | 1 (`hass/tests/test_npp_edit_eval.py:59`) |
| `price_patch` (function, `hass/npp/edits.py:247`) | none found | none found |
| `read` (function, `hass/npp/edits.py:255`) | 336 (`hass/tests/test_again.py:36`) | 3 (`hass/tests/test_npp_edit_eval.py:61`) |
| `apply` (function, `hass/npp/edits.py:279`) | 166 (`hass/tests/test_again.py:319`) | 1 (`hass/tests/test_npp_edits.py:138`) |
| `codex_mapper` (function, `hass/npp/edits.py:302`) | 1 (`hass/tests/test_npp_edits.py:125`) | 1 (`hass/tests/test_npp_edits.py:125`) |

### `evidence`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `role_for` (function, `hass/npp/evidence.py:95`) | 1 (`hass/tests/test_npp_evidence.py:6`) | 1 (`hass/tests/test_npp_evidence.py:140`) |
| `validate` (function, `hass/npp/evidence.py:101`) | 27 (`hass/tests/test_availability_phrase_overlap.py:3`) | 1 (`hass/tests/test_npp_evidence.py:114`) |
| `Evidence` (class, `hass/npp/evidence.py:124`) | 2 (`hass/tests/test_npp_chat_page.py:17`) | 2 (`hass/tests/test_npp_chat_page.py:355`) |

### `identify`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `Reading` (class, `hass/npp/identify.py:78`) | 7 (`hass/tests/test_clover_qty_words.py:37`) | none found |
| `Identifier` (class, `hass/npp/identify.py:100`) | 3 (`hass/tests/test_npp_caption_table.py:131`) | 2 (`hass/tests/test_npp_identify.py:27`) |

### `job`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `owner_item` (function, `hass/npp/job.py:59`) | none found | none found |
| `dump` (function, `hass/npp/job.py:64`) | 14 (`hass/tests/test_fixture_chat_jsonl_framing.py:28`) | none found |
| `job_photos` (function, `hass/npp/job.py:68`) | none found | none found |
| `Plan` (class, `hass/npp/job.py:94`) | 7 (`hass/tests/test_npp_answers.py:5`) | 4 (`hass/tests/test_npp_answers.py:16`) |
| `Card` (class, `hass/npp/job.py:103`) | 5 (`hass/tests/test_npp_edits.py:12`) | 4 (`hass/tests/test_npp_edits.py:259`) |
| `Work` (class, `hass/npp/job.py:114`) | 4 (`hass/tests/test_interpreter_today.py:19`) | 3 (`hass/tests/test_npp_caption_table.py:145`) |
| `Jobs` (class, `hass/npp/job.py:124`) | 4 (`hass/tests/test_intake_simple.py:16`) | 2 (`hass/tests/test_npp_caption_table.py:133`) |

### `missing`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `OwnerPrice` (class, `hass/npp/missing.py:20`) | 1 (`hass/tests/test_npp_missing.py:9`) | 1 (`hass/tests/test_npp_missing.py:35`) |
| `Maker` (class, `hass/npp/missing.py:32`) | 29 (`hass/tests/test_catalog_badge.py:53`) | none found |
| `Decision` (class, `hass/npp/missing.py:46`) | none found | none found |
| `MissingInfo` (class, `hass/npp/missing.py:120`) | 1 (`hass/tests/test_npp_missing.py:9`) | 1 (`hass/tests/test_npp_missing.py:16`) |

### `picture`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `FrozenPicture` (class, `hass/npp/picture.py:26`) | 1 (`hass/tests/test_npp_photo.py:56`) | 1 (`hass/tests/test_npp_photo.py:56`) |
| `read_text` (function, `hass/npp/picture.py:41`) | 286 (`hass/tests/test_again.py:100`) | 1 (`hass/tests/test_npp_photo.py:163`) |
| `choose` (function, `hass/npp/picture.py:66`) | 4 (`hass/tests/test_npp_photo.py:22`) | 1 (`hass/tests/test_npp_photo.py:25`) |

### `private_numbers`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `Number` (class, `hass/npp/private_numbers.py:21`) | none found | none found |
| `values` (function, `hass/npp/private_numbers.py:28`) | 155 (`hass/tests/test_again.py:2`) | 2 (`hass/tests/test_npp_caption_table.py:230`) |
| `problem` (function, `hass/npp/private_numbers.py:53`) | 38 (`hass/tests/test_acceptance_runner.py:110`) | 1 (`hass/tests/test_npp_private_numbers.py:17`) |
| `literal_spans` (function, `hass/npp/private_numbers.py:78`) | none found | none found |
| `picture_problem` (function, `hass/npp/private_numbers.py:84`) | 1 (`hass/tests/test_npp_private_numbers.py:46`) | 1 (`hass/tests/test_npp_private_numbers.py:46`) |
| `Finance` (class, `hass/npp/private_numbers.py:95`) | 1 (`hass/tests/test_npp_private_numbers.py:1`) | none found |
| `finance` (function, `hass/npp/private_numbers.py:108`) | 14 (`hass/tests/test_clover_drafts.py:259`) | 3 (`hass/tests/test_npp_copy.py:40`) |

### `receipt`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `instant` (function, `hass/npp/receipt.py:20`) | 18 (`hass/tests/test_again.py:217`) | none found |
| `confirmation` (function, `hass/npp/receipt.py:28`) | 5 (`hass/tests/test_fast_ack.py:1120`) | none found |
| `read_artifact` (function, `hass/npp/receipt.py:44`) | none found | none found |
| `Artifacts` (class, `hass/npp/receipt.py:62`) | none found | none found |

### `reply`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `compose` (function, `hass/npp/reply.py:25`) | 3 (`hass/tests/test_npp_assets.py:300`) | 1 (`hass/tests/test_npp_edits.py:156`) |
| `ready_line` (function, `hass/npp/reply.py:44`) | 1 (`hass/tests/test_npp_edits.py:149`) | 1 (`hass/tests/test_npp_edits.py:149`) |
| `guard` (function, `hass/npp/reply.py:51`) | 28 (`hass/tests/test_bridge_pictures.py:46`) | 1 (`hass/tests/test_npp_edits.py:163`) |
| `posted` (function, `hass/npp/reply.py:58`) | 27 (`hass/tests/test_commands_doc.py:143`) | 2 (`hass/tests/test_npp_edits.py:165`) |
| `question` (function, `hass/npp/reply.py:65`) | 209 (`hass/tests/test_additive_state.py:41`) | 1 (`hass/tests/test_npp_edits.py:132`) |
| `one_line` (function, `hass/npp/reply.py:74`) | 1 (`hass/tests/test_npp_edits.py:163`) | 1 (`hass/tests/test_npp_edits.py:163`) |
| `Stages` (class, `hass/npp/reply.py:82`) | 3 (`hass/tests/test_npp_edits.py:173`) | 1 (`hass/tests/test_npp_edits.py:173`) |
| `build_stages` (function, `hass/npp/reply.py:150`) | none found | none found |

### `research`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `Page` (class, `hass/npp/research.py:59`) | 1 (`hass/tests/test_skills_hikes.py:334`) | none found |
| `parse_page` (function, `hass/npp/research.py:137`) | none found | none found |
| `Result` (class, `hass/npp/research.py:291`) | 4 (`hass/tests/test_skills_acceptance_chain.py:296`) | none found |
| `research` (function, `hass/npp/research.py:300`) | 7 (`hass/tests/test_install_allowlist_diff.py:39`) | none found |

### `research_hermes`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `Web` (class, `hass/npp/research_hermes.py:42`) | 2 (`hass/tests/test_interpreter_eval_cases.py:594`) | 1 (`hass/tests/test_npp_research.py:38`) |
| `Models` (class, `hass/npp/research_hermes.py:88`) | none found | none found |
| `run` (function, `hass/npp/research_hermes.py:145`) | 402 (`hass/tests/test_acceptance_runner.py:1`) | 1 (`hass/tests/test_npp_research.py:76`) |

### `stages`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `OfficialPage` (class, `hass/npp/stages.py:18`) | 1 (`hass/tests/test_npp_caption_table.py:150`) | 1 (`hass/tests/test_npp_caption_table.py:150`) |
| `ProductionStages` (class, `hass/npp/stages.py:78`) | 2 (`hass/tests/test_npp_caption_table.py:130`) | 2 (`hass/tests/test_npp_caption_table.py:130`) |
| `build` (function, `hass/npp/stages.py:266`) | 70 (`hass/tests/test_bridge_photos_port_zero.py:15`) | none found |

### `validate`

| Public definition | Name mentions | Bound references |
|---|---:|---:|
| `field_problem` (function, `hass/npp/validate.py:27`) | 1 (`hass/tests/test_npp_validate.py:96`) | 1 (`hass/tests/test_npp_validate.py:96`) |
| `captured_dom` (function, `hass/npp/validate.py:82`) | 1 (`hass/tests/test_npp_render_evidence.py:7`) | 1 (`hass/tests/test_npp_render_evidence.py:69`) |
| `dom_problem` (function, `hass/npp/validate.py:91`) | 2 (`hass/tests/test_editor_candidate.py:11`) | 2 (`hass/tests/test_editor_candidate.py:183`) |
| `Verdict` (class, `hass/npp/validate.py:161`) | 1 (`hass/tests/test_clover_checks.py:80`) | none found |
| `listing` (function, `hass/npp/validate.py:170`) | 57 (`hass/tests/test_catalog_file_check.py:198`) | 1 (`hass/tests/test_npp_validate.py:35`) |

## R2. Filename matches and modules with no direct import

Read-only grep used from the clone root:

```sh
git grep -nE 'hass\.npp|from[[:space:]]+hass[[:space:]]+import.*\bnpp\b' origin/main -- 'hass/tests/*.py'
```

This finds package strings and common single-line imports, but also finds comments, script names and string patch targets, and may miss split statements. The Python syntax scan checked explicit imports throughout all 911 Python files, including indented and multiline statements and aliases. It did not treat a package-only import as an import of every submodule. Neither check proves absence of test exercise through another module, nor exhausts dynamic imports (the computed photo references at `hass/tests/test_npp_assets.py:620–633` come from `hass/npp/assets/hass-product-photo/photo.json#/existing_refs`, which names neither missing module).

**Filename rule:** strip `test_npp_`; match the longest module stem at the start of the remaining name, with an end or underscore boundary. This keeps `jobs` from falsely matching `job`. The exact and suffix rule matched ten files:

| Test file | Named module | Direct import from the named module? |
|---|---|---|
| `hass/tests/test_npp_copy.py` | `copy` | Yes, line 8 |
| `hass/tests/test_npp_edits.py` | `edits` | Yes, line 11 |
| `hass/tests/test_npp_evidence.py` | `evidence` | Yes, line 6 |
| `hass/tests/test_npp_identify.py` | `identify` | Yes, line 8 |
| `hass/tests/test_npp_job.py` | `job` | Yes, line 14 |
| `hass/tests/test_npp_missing.py` | `missing` | Yes, line 9 |
| `hass/tests/test_npp_private_numbers.py` | `private_numbers` | Yes, line 5 |
| `hass/tests/test_npp_research.py` | `research` | **No**; line 11 imports `research_hermes` instead |
| `hass/tests/test_npp_stages.py` | `stages` | Yes, line 11 |
| `hass/tests/test_npp_validate.py` | `validate` | Yes, line 8 |

Nearby names are not necessarily mismatches: `test_npp_photo.py:14` imports `picture`, `test_npp_jobs.py:15` imports `job`, `test_npp_edit_eval.py:13` and `test_npp_edit_phrases.py:16` import `edits`, and `test_npp_posted_link.py:12` imports `reply` (all under `hass/tests/`). `hass/tests/test_npp_render_evidence.py:7` targets render validation via `validate`, not the `evidence` module; `hass/tests/test_npp_assets.py:15–19,644–648` checks files rather than a same-named module (`assets` is a package function).

**No direct import found:** `hass.npp.research` and `hass.npp.receipt` only; see the import counts above. The research test calls the adapter (`hass/tests/test_npp_research.py:76`), which calls both core research and, via `Web.fetch`, the page parser (`hass/npp/research_hermes.py:85,145–152`). Job tests cover delivery and backup through callers (`hass/tests/test_npp_job.py:158–188,336–366`; `hass/npp/job.py:18,452–464`; `hass/statebackup.py:36`). This is a direct-import gap, not evidence that either module is untested.

## R3. Ten least-covered public functions, ranked by size

All ten are from the 15 functions with zero bound references (R1). Size is an **estimate**: inclusive physical lines from `def` to Python's syntax-tree `end_lineno`, including internal blanks and docstrings; ties sort by source path then name. The suggested checks are first **direct** tests, not claims that existing caller tests lack those assertions.

| Rank | Function and anchor | Est. lines | First direct check |
|---:|---|---:|---|
| 1 | `research` — `hass/npp/research.py:300–433` | 134 | A known local maker returns `known-maker` with no facts and never calls the fake ports. |
| 2 | `job_photos` — `hass/npp/job.py:68–90` | 23 | An expired synthetic request still contributes ordered, deduplicated attachments; malformed attachment JSON fails closed. |
| 3 | `read_artifact` — `hass/npp/receipt.py:44–59` | 16 | Read a valid synthetic digest-named PNG, then refuse a symlink to the same bytes. |
| 4 | `confirmation` — `hass/npp/receipt.py:28–41` | 14 | A matching confirmed receipt at queue time passes; an otherwise identical receipt just before queue time does not. |
| 5 | `build_stages` — `hass/npp/reply.py:150–157` | 8 | A stub builder raising `ValueError` yields `None`, never a partial port. |
| 6 | `price_patch` — `hass/npp/edits.py:247–252` | 6 | A price with an unknown unit produces only the selling-price patch; a cost alone yields no patch. |
| 7 | `instant` — `hass/npp/receipt.py:20–25` | 6 | Accept an offset-aware ISO timestamp and reject the same timestamp without an offset. |
| 8 | `parse_page` — `hass/npp/research.py:137–142` | 6 | Preserve the supplied URL and retrieval marker and retain visible text but not script text from synthetic HTML. |
| 9 | `build` — `hass/npp/stages.py:266–271` | 6 | A synthetic editor missing `persist_candidate` cannot construct a production stage port. |
| 10 | `eligible` — `hass/npp/copy.py:93–96` | 4 | A category exclusion wins over an otherwise matching kind, category and variant. |

## R4. Ranked gaps and one possible follow-up

1. **Frozen artifact reader:** no bound test references for `read_artifact` or `Artifacts` (R1). The existing backup test checks valid frozen bytes and an unrelated filename, not this reader's refusal of a valid-looking symlink (`hass/tests/test_npp_job.py:336–366`; `hass/npp/receipt.py:44–59`). A symlink test in the chat-page suite targets a different reader (`hass/tests/test_npp_chat_page.py:316`).
2. **Receipt timing boundary:** `confirmation` and `instant` have no bound references. The job journey already checks an unconfirmed state, a wrong digest, and a yes received before confirmation; those checks are not the same as a receipt timestamp just outside the allowed interval (`hass/tests/test_npp_job.py:158–188`; `hass/npp/receipt.py:20–41`).
3. **Core research and stage assembly:** prioritize a direct test only for decisions the caller suites do not already isolate. The adapter suite already checks visible citations, competing sites and deadline refusal, and the stage wrapper suite already checks a missing component (`hass/tests/test_npp_research.py:83,148,183`; `hass/tests/test_npp_edits.py:204–213`). The filename mismatch is not a reason to duplicate these tests.

**One prospective unit (estimate: 60–90 minutes; not implemented):** add `hass/tests/test_npp_receipt.py` only. In a temporary directory, exercise the real `read_artifact` with a synthetic PNG under its matching digest name, then pass a digest-named symlink to that identical fixture and assert refusal. This catches removal of `O_NOFOLLOW` while proving the same bytes pass the normal reader (`hass/npp/receipt.py:44–59`). Offline check for that future unit: `python3 -m unittest hass.tests.test_npp_receipt`. No service, model, site, transport, or owner input is needed. No test changes or test runs are part of this audit.
