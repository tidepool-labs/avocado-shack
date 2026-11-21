# Hass ops module test map

## R1. Module inventory

| `hass/ops/` file | Lines | Public definitions (`line`) | Direct importers in `hass/tests/` (add `.py` before `:line`) |
| --- | ---: | --- | --- |
| `__init__.py` | 199 | Classes `Arg:30`, `Op:42`, `OpContext:49`, `Touched:80`, `NeedsDetails:92`, `NotFound:98`, `Refused:103`; functions `load_registry:107`, **`has_control_chars:119`**, `check_args:190` | 94; full list below |
| `catalog.py` | 486 | `lookup:431` | `test_catalog_badge:8`, `test_catalog_lookup_fold:8`, `test_catalog_ops:13`, `test_catalog_place:10`, `test_catalog_unchanged:11`, `test_catalog_unchanged_spacing:12`, `test_maker_rename_warning:13`, `test_maker_twin_shadow:14`, `test_memory_alias:10`, `test_organic_sync:15`, `test_question_missing_fields:10`, `test_restore_image_rule:17` |
| `club.py` | 37 | none | none |
| `front.py` | 143 | **`sections_value:11`**, **`banner_problem:20`**, **`page_value:67`**, **`faq_value:92`** | none |
| `hikes.py` | 446 | `guest_counts_checked:42`, `guest_counts:56` | `test_content_starts_at:16`, `test_hike_create_capacity_conflict:12`, `test_hike_far_future:10`, `test_hike_guest_rows:16`, `test_hike_guest_warning:13`, `test_hike_ids:10`, `test_hike_meeting_warning:12`, `test_hike_move_warning:10`, `test_hike_repeat:18`, `test_hike_rsvp_on:9`, `test_hike_twin:12`, `test_hike_update_spacing:11`, `test_hike_update_twin:12`, `test_skills_reports:654`, `test_time_arg:8`, `test_undo_guest_warnings:17`, `test_undo_meeting_warning:11` |
| `history.py` | 227 | none | `test_history_revert_deep:12`, `test_restore_image_rule:18`, `test_undo_guest_warnings:17`, `test_undo_meeting_warning:11`, `test_undo_product_restore:18` |
| `home.py` | 136 | none | none |
| `photos.py` | 321 | Classes `Retake:80`, `PictureVariant:223`; functions `house_picture:144`, `house_check:158`, **`select_variant:229`**, `install:268` | `test_house_render_seam:23`, `test_newitem:21`, `test_newitem_render_translucent_luma:14`, `test_npp_photo:15`, `test_photo_polish:32`, `test_photo_store_oserror:11`, `test_product_add_photo:11`, `test_publish_gate:14`, `test_set_photo_alt:8`, `test_set_photo_alt_article:8`, `test_set_photo_alt_cameras:8`, `test_set_photo_alt_defaults:8`, `test_set_photo_alt_length:9`, `test_set_photo_folder:14`, `test_skills_item_picture:23`, `test_store_home_image:19` |
| `restock.py` | 52 | none | none |
| `routes.py` | 175 | none | `test_hike_lookup:23`, `test_route_edit:12`, `test_route_edit_spacing:11`, `test_route_edit_titles:10`, `test_route_edit_unicode:10`, `test_route_link_warning:20`, `test_trial_handover_doc:11` |
| `samples.py` | 28 | none | none |
| `specials.py` | 216 | none | `test_specials_edit_titles:9`, `test_specials_op_clock:10` |
| `store.py` | 189 | none | `test_limits_doc:156`, `test_store_hours_warning:14` |

**Read on 2026-11-21:** fresh `origin/main` was `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, exactly the requested baseline. `git ls-files 'hass/ops/*.py' 'hass/tests/test_ops*.py' '*G-QUESTIONS.md'` lists the 13 Python source files above (12 submodules plus the package initializer), no `test_ops*.py`, and no tracked `G-QUESTIONS.md` at this revision. No live inputs or owner decisions were used; this is a report only (`AGENTS.md:3–16`).

**How counted:** From the repo root, `wc -l hass/ops/*.py` gives file sizes; `git grep -nE '^(async def|def|class) [[:alpha:]][[:alnum:]_]*' -- hass/ops` gives definition anchors. Public here means a top-level `def`, `async def`, or `class` not starting with `_`, not imported names, methods, constants, or strings registered in `OPS`. For imports, parse the tracked Python sources under `hass/tests/` with Python's AST; walk every node (including local scopes). Count `from hass.ops.<module> import …`, `from hass.ops import <module>`, and `import hass.ops.<module>` for that module, and bare package imports and imports of initializer symbols for the package, not for every submodule. Aliasing does not change the result. A comment, dynamic load or import of a different module with a similar name is not a direct import. A file can appear in more than one row. Support is separate: `hass/tests/fixture_ops.py:7` imports the package, but is not a test file.

**Collection only:** Called the repo's `all_modules()` (`hass/tests/ci_shards.py:75–90`) from a workspace script with the checkout on its import path, then compared the names with tracked `test*.py` under `hass/tests/`: 901 module names matched exactly on 2026-11-21; 911 tracked Python files including support. No test modules were imported and no test cases or CI jobs ran. `load_weights()` (`hass/tests/ci_shards.py:93–108`) read 659 keys at `hass/tests/ci_weights.json#/seconds`; these are shard-balancing weights, not evidence that a module or function was exercised (`#/measured`). The CI planner treats `hass/ops/` changes as full tier because of dynamic loading (`hass/tests/ci_shards.py:8–12,63`).

**Package importers** (`hass/tests/`, add `.py` before `:line`):

- `test_auto_policy:9`, `test_capabilities:13`, `test_catalog_unchanged:12`, `test_catalog_unchanged_spacing:11`, `test_clear_availability:13`, `test_club_intro:22`, `test_front:19`, `test_front_pages:12`, `test_hike_repeat:18`, `test_hike_samples:93`, `test_hike_update_spacing:11`, `test_house_render_seam:23`, `test_image_arg:8`.
- `test_interpret_check:11`, `test_interpret_check_count:13`, `test_interpret_check_enum:10`, `test_interpret_check_names:12`, `test_interpret_check_prices:11,77`, `test_interpret_check_repeat:12`, `test_interpret_check_spacing:12`, `test_interpreter_eval:9`, `test_interpreter_no_undo:13,18`, `test_interpreter_prompt:16`, `test_interpreter_prompt_brand:11`, `test_interpreter_prompt_community:10`, `test_interpreter_prompt_descriptions:131`, `test_interpreter_prompt_skills:9`, `test_interpreter_prompt_store:10`.
- `test_limits_doc:271`, `test_live_add:27`, `test_live_drill:22`, `test_live_owners:11`, `test_live_table:12`, `test_maker_hide_products:18`, `test_maker_optional_story:25`, `test_maker_optional_url:18`, `test_maker_product_batch:14`, `test_maker_rename_warning:12`, `test_maker_twin_shadow:14`, `test_nl_eval:8`, `test_nl_eval_expected_limit:7`, `test_nl_eval_failure_codes:7`, `test_nl_eval_latency:7`, `test_nl_eval_order:7`, `test_nl_eval_schema:7`, `test_nl_eval_words:8`, `test_notice_calendar_bounds:11`, `test_owners_two:19`.
- `test_product_default_brand:11`, `test_publish_gate:14`, `test_publish_live:19`, `test_restock_op:15`, `test_restore_image_rule:16`, `test_revert_parent_directory:14`, `test_route_edit_titles:9`, `test_route_edit_unicode:9`, `test_route_link_warning:19`, `test_sandbox:10`, `test_sandbox_draft_roots:7`, `test_sec2_release:20`, `test_selection_refusal_atomic:13`, `test_set_availability_all:13`, `test_set_photo:16`, `test_set_photo_folder:14`, `test_sitegen_selling_price:6`.
- `test_skills_hikes:20`, `test_skills_item_add:15`, `test_skills_item_picture:23`, `test_skills_items:21`, `test_skills_lint:7`, `test_skills_makers:18`, `test_skills_model:8`, `test_skills_plan_output_shapes:7`, `test_skills_reports:20`, `test_skills_restock:21`, `test_skills_scaffold:20`, `test_skills_shop:18`, `test_skills_social:19`, `test_skills_specials:23`, `test_skills_stock:19`.
- `test_specials:13`, `test_specials_edit_titles:9`, `test_specials_op_clock:10`, `test_statebackup:14`, `test_statebackup_inbox:8`, `test_statebackup_paused:8`, `test_stock_site:355`, `test_store_hours_warning:14`, `test_store_notice:16`, `test_time_arg:8`, `test_trial_handover_doc:10`, `test_undo:16`, `test_undo_guest_warnings:17`, `test_undo_product_restore:17`.

**Named tests and direct imports are different.** Seven submodules have both: catalog, hikes, history, photos, routes, specials and store (intersect R1's importers with R3's filename rule). Three have same-subject filenames but no direct import (club, front, restock); two have focused tests named for their registered feature instead (home, samples). The registry imports each submodule and registers its `OPS` (`hass/ops/__init__.py:107–116`); the editor uses it by default (`hass/editor.py:172,627`). The table below gives an indirect path for each of the five. “Indirect” is not “HTTP routes only”: some tests call a registered handler themselves, while others use the editor or chat/skill route. Also, `hass/skills/front.py:5` imports two front helpers, and `hass/skills/restock.py:35` imports restock constants; the lack of direct **test** imports does not rule out those paths.

| No-direct-import module | Example test file focused on its operations | Source-to-test evidence |
| --- | --- | --- |
| `club.py` | `hass/tests/test_club_intro.py` | `club.set_intro` at `hass/ops/club.py:37`; the test sends the op through the editor fixture at `hass/tests/test_club_intro.py:28,56–67,116–126`. |
| `front.py` | `hass/tests/test_front.py`, `hass/tests/test_front_pages.py` | Ops at `hass/ops/front.py:129–143`; registry-backed checks at `hass/tests/test_front.py:39–43,56–93` and `hass/tests/test_front_pages.py:29–33,63–94`. |
| `home.py` | `hass/tests/test_store_headline.py` | `store.set_headline` belongs to `home.py`, not `store.py` (`hass/ops/home.py:131`); edit and undo via `hass/tests/test_store_headline.py:21,45–56`. |
| `restock.py` | `hass/tests/test_restock_op.py` | `product.set_restock` at `hass/ops/restock.py:50–52`; registry lookup and direct handler application at `hass/tests/test_restock_op.py:70–78`. |
| `samples.py` | `hass/tests/test_hike_samples.py` | `hike.samples` at `hass/ops/samples.py:28`; editor-fixture hide/show checks at `hass/tests/test_hike_samples.py:23,42–53`. |

## R2. Largest public functions no test names

Only **six** qualified, so there are no ranks 7–10. Bold names in R1 are the same six. The size estimate is the definition-to-last-body-line span inclusive (`end_lineno - lineno + 1` in the AST), including internal blank lines and docstrings, not a complexity score. A mention means the exact identifier anywhere in tracked Python test/support text (including comments, strings and imports), or the full name as an underscore-delimited part of a `test…` function/method name. This deliberately counts some mentions that are not calls; e.g. `house_check` is named in `hass/tests/test_house_render_seam.py:6`. Conversely, an indirect caller can exercise a function without naming it. The exact-token cross-check across all tracked `hass/tests` files returned no output, exit 1, on 2026-11-21:

```sh
git grep -nE '(^|[^[:alnum:]_])(faq_value|page_value|banner_problem|select_variant|has_control_chars|sections_value)([^[:alnum:]_]|$)' -- hass/tests
```

An additional source scan checked those same six as full name segments in test definitions (e.g. `test_<function>_<case>`); no match. No tests were run to measure coverage.

| Rank | Function and estimated lines | What a first focused test would check (not work ordered) |
| ---: | --- | --- |
| 1 | `faq_value`, 25 (`hass/ops/front.py:92–116`) | A case/space variant replaces the existing question rather than duplicating it; removing the last entry hides the page and leaves the input unchanged. |
| 2 | `page_value`, 23 (`hass/ops/front.py:67–89`) | A partial edit preserves unspecified fields; a hide keeps existing content, and hiding an already-hidden page is refused. |
| 3 | `banner_problem`, 16 (`hass/ops/front.py:20–35`) | With a fixed date and synthetic store, the same otherwise valid banner is accepted for a shown page and refused for a hidden page. |
| 4 | `select_variant`, 14 (`hass/ops/photos.py:229–242`) | After a rejected house render, fallback uses the original web bytes and extension, never the rejected render; without fallback it returns a refusal/retake. |
| 5 | `has_control_chars`, 8 (`hass/ops/__init__.py:119–126`) | Detect a control character in a dictionary key nested inside a list; clean nested keys and values are accepted. |
| 6 | `sections_value`, 7 (`hass/ops/front.py:11–17`) | Preserve the requested order and visibility for valid sections; duplicate hidden entries yield a validation problem. |

## R3. Test filenames that suggest an ops module but do not import it

There is no literal `test_ops*.py` at this main (`git ls-files` above). For the broader, reproducible naming check, use `test_` (optionally followed by `ops_`) then the module name as the first whole token; accept singular forms for hikes/photos/routes/samples/specials and `hiking` for hikes. Inventory with `git ls-files 'hass/tests/test*.py'` and compare against the R1 import columns. The grep used to cross-check candidate import lines was:

```sh
git grep -nE 'from hass\.ops(\.[[:alnum:]_]+)? import|import hass\.ops' -- 'hass/tests/test_catalog*.py' 'hass/tests/test_club*.py' 'hass/tests/test_front*.py' 'hass/tests/test_hik*.py' 'hass/tests/test_history*.py' 'hass/tests/test_home*.py' 'hass/tests/test_photo*.py' 'hass/tests/test_restock*.py' 'hass/tests/test_route*.py' 'hass/tests/test_sample*.py' 'hass/tests/test_special*.py' 'hass/tests/test_store*.py' 'hass/tests/test_ops*.py'
```

The grep is line-based: a hit can be a comment, import the package only, import a different submodule, or omit names split across lines. E.g. `test_hike_lookup.py:23` imports **routes**, and `test_store_home_image.py:19` imports **photos**. Use the Python import parse, not grep alone, for the final classification. The filename rule is a subject hint, not proof of intent; it misses other prefixes (`test_set_photo_*`, `test_skills_*`) and can pick up tests of skills, UI, validation, or other layers. Neither scan follows aliases through helpers or resolves dynamic calls. Under this rule the files below do not directly import their indicated module; names are stems under `hass/tests/`.

| Module | Matching name(s) without a direct import |
| --- | --- |
| `__init__` | none |
| `catalog` | `test_catalog_clear_filters`, `test_catalog_dupes`, `test_catalog_file_check`, `test_catalog_limits`, `test_catalog_new_order` |
| `club` | `test_club_intro` |
| `front` | `test_front`, `test_front_page_literal_style`, `test_front_pages`, `test_front_sections_colour_words` |
| `hikes` | `test_hike_anchor`, `test_hike_cache_shapes`, `test_hike_cancel_note`, `test_hike_capacity_ceiling`, `test_hike_capacity_rsvp_off`, `test_hike_change_words`, `test_hike_chat_capacity_conflict`, `test_hike_chat_meeting`, `test_hike_chat_meeting_limit`, `test_hike_chat_offer_limit`, `test_hike_chat_route_specificity`, `test_hike_chat_title_boundary`, `test_hike_clear`, `test_hike_coordinate_overflow`, `test_hike_decimal_capacity`, `test_hike_difficulty_case`, `test_hike_elevation_identity`, `test_hike_fetch_finite_json`, `test_hike_fetch_http_errors`, `test_hike_flow`, `test_hike_ics`, `test_hike_journal`, `test_hike_limits`, `test_hike_lookup`, `test_hike_lookup_chat`, `test_hike_nonprice_packing`, `test_hike_ops`, `test_hike_recap`, `test_hike_recap_spacing`, `test_hike_repeat_claims`, `test_hike_rsvp_reenable`, `test_hike_samples`, `test_hike_signup_mismatch`, `test_hike_time_text`, `test_hike_trail_refused` |
| `history` | `test_history_approved`, `test_history_search`, `test_history_times` |
| `home` | none by prefix; see `test_store_headline.py:21,45–56` and `hass/ops/home.py:131` |
| `photos` | `test_photo_batch`, `test_photo_caption_reader_failed`, `test_photo_detail_read`, `test_photo_draft`, `test_photo_home_image`, `test_photo_limits`, `test_photo_new_product`, `test_photo_on_product`, `test_photo_polish_ocr_box`, `test_photo_polish_ocr_tsv`, `test_photo_polish_runner_shapes`, `test_photo_retry`, `test_photo_trial`, `test_photo_trial_output_errors`, `test_photos_to_take` |
| `restock` | `test_restock_decimal_counts`, `test_restock_more_counts`, `test_restock_op`, `test_restock_prefix_multiplier`, `test_restock_spoken_counts` |
| `routes` | `test_route_add`, `test_route_hide`, `test_route_idea_dates`, `test_route_limits` |
| `samples` | none by prefix; see `test_hike_samples.py:23,42–53` and `hass/ops/samples.py:28` |
| `specials` | `test_special_contact_patterns`, `test_special_title_resolution`, `test_specials` |
| `store` | `test_store_clear_home_image`, `test_store_field_undo`, `test_store_headline`, `test_store_home_image`, `test_store_hours_numbering`, `test_store_hours_repeat`, `test_store_hours_report`, `test_store_intro`, `test_store_limits`, `test_store_notice`, `test_store_ops`, `test_store_phone`, `test_store_spacing_only`, `test_store_story`, `test_store_words` |

## R4. Ranked gaps and one possible follow-up

1. **Request parsing: narrow edge case worth checking.** `has_control_chars` scans dictionary keys as well as values (`hass/ops/__init__.py:119–126`); `hass/editor.py:158–160` uses it to refuse malformed requests. The named editor test at `hass/tests/test_editor_request_duplicates.py:57–67` explicitly checks a control character in a value, not in a key. This is a candidate assertion gap, not a defect or a measured coverage gap.
2. **Photo selection: unnamed helper, useful indirect test already present.** The legacy installer reaches `select_variant` through `_installation_picture` (`hass/ops/photos.py:245–265,280`), and `hass/tests/test_npp_photo.py:29–59` checks a variant matrix, refusal and output identity. Do not add a second matrix just to make a name appear.
3. **Front helpers: weak direct visibility, stronger operation-level evidence.** Sections/banner refusal checks at `hass/tests/test_front.py:72–93` and FAQ replace/remove and page refusal checks at `hass/tests/test_front_pages.py:63–94` exercise the helpers through `hass/ops/front.py:38–46,57–64,119–143`. The other no-direct-import cases have focused tests in R1. Renaming tests or adding import-only tests would not protect more behavior.

**One possible unit, estimated 30–60 minutes, not implemented:** Extend only `hass/tests/test_editor_request_duplicates.py` at the existing request-parser test (`:57–67`), if a focused review confirms no equivalent key-specific case. Add an escaped control in a synthetic nested argument key and require the existing control-character refusal, with a clean-key control. A regression that drops `has_control_chars(k)` but still checks values should fail the new assertion while retaining the current value check. Use the existing parser boundary and no production seam. Offline acceptance, from the repo root: `python3 -B -m unittest hass.tests.test_editor_request_duplicates` with local test dependencies and fixture-only inputs. This command is for that future unit; it was not run for the report.
