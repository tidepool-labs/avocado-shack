# AVO1015-11 — Hass CI timing coverage and shard balance

| Check | Result |
| --- | --- |
| Timing coverage (R1) | **659 of 901 modules** have recorded weights; **242** are missing and **0** entries are stale. |
| Time totals (R1) | **3,158 s recorded**; **3,884 s estimated** by the planner, including 726 s of fallback weights. |
| Default four shards (R2) | **971 s each** by the planner's estimates; **0 s spread**. Actual runtime balance is unknown. |
| Concentration (R3) | Top ten: **987 s (31.25% of recorded seconds)**; only `test_skills_cases` exceeds a quarter of its four-way shard. |
| Recommendation (R4) | Check timing coverage before treating the zero spread as evidence that CI wall times match. |

Read-only replay on **2026-11-21 UTC**, from `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`. Against the task baseline `1f8510907cb2989bb50391fde45d6211e4735879`, the planner, weight file and workflow are identical; three test modules were added to the inventory. See the comparison and replay below. No tests were imported or run, and no hosted run or live repository variable was queried.

## R1. Timing coverage

Module names come from `hass/tests/ci_shards.py:75–90`; the replay also checks them against the tracked `hass/tests/**/test_*.py` inventory (including top-level files). Recorded entries come from `hass/tests/ci_weights.json` at `/seconds`; `/measured` describes the original measurements and the later backfill, not a measurement of this checkout.

| Count or sum | Result |
| --- | ---: |
| Current modules | 901 |
| Recorded entries | 659 |
| Current modules with a recorded weight | 659 |
| Current modules with no recorded weight | 242 |
| Recorded weights with no current module | 0 (none to list) |
| Sum of all recorded weights | 3,158 s |
| Sum of matched recorded weights | 3,158 s |
| Planner fallback contribution (242 × 3 s, estimate) | 726 s |
| Total planner load (estimate) | 3,884 s |

The workflow's **~1,150 s** suite total and **~290 s** per shard are comments, not the sum of the current weights (`.github/workflows/check.yml:52–55`).

<details>
<summary>All 242 modules with no recorded weight (short names under hass.tests)</summary>

```text
test_again_reverted
test_alert_log_window
test_answer_reader_request
test_attachment_input_types
test_audit_calendar
test_audit_log_days
test_availability_own_day
test_backlog_forget_bounds
test_cancel_all
test_catalog_file_check
test_chaos_suite
test_cloud_codex
test_clover_apply
test_clover_apply_identity
test_clover_cache_category_shapes
test_clover_chat_line_separators
test_clover_chat_writes
test_clover_checks
test_clover_config_merchant_ids
test_clover_count_phrases
test_clover_credential_parent
test_clover_drafts_extreme_count
test_clover_dryrun
test_clover_fake
test_clover_host_engine
test_clover_item_ids
test_clover_journal_lock_open
test_clover_links
test_clover_pos
test_clover_qty_words
test_clover_reads_elapsed
test_clover_report_source_file
test_clover_retry_after_input
test_clover_sku_iterables
test_clover_sku_suffix
test_clover_transport_close
test_clover_write_readiness
test_command_typo
test_content_schema_version_type
test_corrlog_short_write
test_corrlog_time_edges
test_cost_by_name
test_costs_command
test_description_style_audit
test_design_notes
test_drill_export_compare
test_editor_candidate
test_forwarder_photo
test_forwarder_receipt
test_front_sections_colour_words
test_health_memory_offsets
test_health_pause_redaction
test_held_command
test_help_listing
test_help_text_voice_check
test_hike_cache_shapes
test_hike_decimal_capacity
test_hike_fetch_finite_json
test_history_times
test_hours_keep_day
test_house_style_product_id
test_house_style_product_maker_link
test_inbox_retry_metadata
test_info_pages_check
test_install_acceptance_receipt
test_install_allowlist_diff
test_install_backup_receipt
test_install_ci_receipt
test_install_citation_drift
test_install_config_attributes
test_install_digest_ledger
test_install_entry_gate
test_install_launchagent
test_install_mac_parity
test_install_pending_work
test_install_preflight_verdict
test_install_private_files
test_install_quiescence
test_install_rehearsal
test_install_release_lineage
test_install_revert_scan
test_install_rollback_proof
test_install_runtime_readback
test_install_service_restart
test_install_skill_parity
test_install_skill_restore_proof
test_install_skill_shadow
test_install_stage_file
test_install_store_schema
test_install_switch_projection
test_install_switch_readback
test_install_target_inspection
test_install_tools_checkout
test_install_window_clock
test_intake_simple
test_interpret_check_lookup
test_interpreter_audit_report
test_item_both
test_item_intake_priced_text
test_item_intake_unit_admission
test_item_picture_unicode_home_rejection
test_item_price_numbers
test_itemstd_duplicate_keys
test_itemstd_gap_diff
test_itemstd_surrogates
test_label_case_coverage
test_label_reader_compact_fractions
test_listing_by_name
test_listing_exact_identity
test_listing_store
test_live_selftest_check_ids
test_look_change
test_look_command
test_look_engine
test_maker_price_words
test_maker_site_break_spacing
test_maker_site_hidden_meta
test_maker_story_case
test_margins_say_precision
test_media_ifd_bounds
test_media_verify_original_kind
test_migration_maker_urls
test_nl_corpus_ops_check
test_nl_eval_selection_args
test_nl_intent_coverage
test_nl_prep_ordinal_words
test_non_hike_question_turns
test_npp_answers
test_npp_assets
test_npp_caption_table
test_npp_case_new
test_npp_chat_page
test_npp_copy
test_npp_edit_eval
test_npp_edit_phrases
test_npp_edits
test_npp_evidence
test_npp_findings
test_npp_identify
test_npp_job
test_npp_jobs
test_npp_missing
test_npp_owner_guide
test_npp_photo
test_npp_posted_link
test_npp_preflight
test_npp_price_provenance
test_npp_private_numbers
test_npp_render_evidence
test_npp_research
test_npp_review_export
test_npp_second_product
test_npp_stages
test_npp_status_line
test_npp_transcript_check
test_npp_undo_journey
test_npp_validate
test_page_photo_dual_destination
test_phone_wording
test_photo_detail_read
test_photo_polish
test_photo_polish_ocr_box
test_photo_polish_ocr_tsv
test_photo_polish_runner_shapes
test_photo_retry
test_pilot_approvals
test_pilot_card_png
test_pilot_change_record
test_pilot_content_diff
test_pilot_inbound
test_pilot_photo_receipts
test_pilot_private_scan
test_pilot_receipt_new
test_pilot_reply_match
test_pilot_scenario_check
test_pilot_sender_check
test_plain_shelf_check
test_post_availability
test_post_by_name
test_post_notice_command
test_producers_file_check
test_product_claims_receipt_shape
test_proposal_notice_words
test_publish_gate
test_publish_sources_check
test_question_lookup
test_relay_photos
test_relay_receipt
test_release_journal_strict_read
test_release_pending_recovery
test_rendered_a11y_check
test_rendered_anchor_check
test_rendered_jsonld_check
test_rendered_link_check
test_repeat_outcome
test_restock_more_counts
test_restock_prefix_multiplier
test_retention_report_diff
test_retention_uncounted_tables
test_retention_web_temp_files
test_route_idea_dates
test_sandbox_member_shapes
test_saved_cost_dates
test_scaffold_setup_depth
test_screenshot_refs
test_second_question
test_selftest_summary_check
test_set_availability_all
test_shelf_check_except
test_shelf_command
test_shop_length_replies
test_site_hours_abbreviations
test_site_hours_word_ranges
test_sitegen_selling_price
test_skills_contact_missing_phone
test_skills_plan_output_shapes
test_social_draft_notice
test_social_negated_posting
test_special_contact_patterns
test_specials_edit_titles
test_stagelog_destinations
test_stagelog_read_files
test_statebackup_clover
test_statebackup_exact_modes
test_statebackup_worktree_nul
test_stock_product_choice
test_stock_single_token_references
test_stock_site
test_store_hours_report
test_template_compat_chain_check
test_testkit_reply_shapes
test_till_yes_durable
test_tlds_freshness_check
test_transcript
test_transcript_attachment_shapes
test_transcript_export_blob
test_transcript_inbound_parity
test_transcript_latency_report
test_transcript_window_counts
test_undo_cancel_phrases
test_units_template_parity
test_weekday_date_mismatch
```

</details>

## R2. Full-tier shard assignment

Replay: `python3 -B replay_shards.py avocado-shack shard-membership.txt` with **Python 3.12.3** (script below). It uses the same `partition()` as the full tier (`hass/tests/ci_shards.py:111–120,365–367`): heaviest first, then onto the lightest shard, with lower shard index breaking load ties. All four partitions assign each of the 901 modules exactly once. Shard numbers are zero-based; the appendix gives every assignment.

The missing-weight lookup at `hass/tests/ci_shards.py:108` is `return weights.get(name, DEFAULT_WEIGHT)`. Line 56 defines `DEFAULT_WEIGHT = 3  # seconds for a module with no measurement yet`. Missing weights therefore do **not** drop tests from the full plan.

| Shards | Module counts by shard index | Estimated seconds by shard index | Largest − smallest |
| ---: | --- | --- | ---: |
| 1 | 901 | 3,884 | 0 s |
| 2 | 449, 452 | 1,942, 1,942 | 0 s |
| 4 | 221, 226, 227, 227 | 971, 971, 971, 971 | 0 s |
| 8 | 85, 116, 116, 117, 116, 117, 117, 117 | 486, 486, 486, 486, 485, 485, 485, 485 | 1 s |

Four is the workflow default, not a claim about the live `HASS_SHARD_JOBS` variable (`.github/workflows/check.yml:52–55,95–97`). The **480 s** figure is a threshold for estimated *selected* time in the PR affected tier, not a full-tier shard cap (`.github/workflows/check.yml:16–25`; `hass/tests/ci_shards.py:355–367`). The sums above exclude job setup and queue time and do not establish current wall time.

## R3. Heaviest recorded modules

| Rank | Module (JSON pointer in `hass/tests/ci_weights.json`) | Recorded seconds |
| ---: | --- | ---: |
| 1 | `/seconds/test_skills_cases` | 333 |
| 2 | `/seconds/test_skills_scaffold` | 114 |
| 3 | `/seconds/test_skills_testkit_clock` | 113 |
| 4 | `/seconds/test_skills_acceptance_groups` | 101 |
| 5 | `/seconds/test_preview_hike_results` | 78 |
| 6 | `/seconds/test_live_drill` | 64 |
| 7 | `/seconds/test_fast_ack` | 47 |
| 8 | `/seconds/test_demo_rehearsal` | 46 |
| 9 | `/seconds/test_skills_acceptance_chain` | 46 |
| 10 | `/seconds/test_preview_store_checks` | 45 |

The ten hold **987 / 3,158 s (31.25%)** of recorded time (ties ordered by name). At four shards the quarter-shard threshold is **971 / 4 = 242.75 s**. Only **`test_skills_cases`**, at **333 s** on shard **0**, exceeds it. These comparisons are against stored weights and the modeled shard loads, not fresh timings.

## R4. Ranked next steps

1. **Validate the missing weights first.** R1 finds 242 modules at the flat 3 s fallback; R2's zero spread is only as good as those estimates. Use already-produced full-tier records where available (`hass/tests/ci_shards.py:482–488`), keeping results tied to their run and source revision. Report unmatched modules as unknown.
2. **Check the heavy outlier next.** Compare `test_skills_cases` across comparable existing runs before considering any optimization; R3 shows why it matters, not why it is slow.
3. **Leave shard count and packing alone on this evidence.** R2 shows no four-way imbalance in the input model. A different width changes job fan-out (`.github/workflows/check.yml:52–55`), and this audit does not measure that trade-off.

**One proposed follow-up (60–90 minutes, estimate):** a read-only receipt check. Take one recent successful full-tier run with records from every shard and record its SHA and attempt. Join its `module_seconds` to the R1 missing list; report matched and unmatched counts, runner-recorded shard elapsed seconds from `seconds`, and their spread. Acceptance: every shard record is accounted for or explicitly marked unavailable, with no invented timing for unmatched modules. No test rerun, weight or planner edit, or change to workflow settings is part of this unit.

## Reproduce offline

From the directory containing the pinned checkout named `avocado-shack`:

```sh
git -C avocado-shack rev-parse HEAD
git -C avocado-shack diff --name-status 1f8510907cb2989bb50391fde45d6211e4735879 HEAD -- hass/tests .github/workflows/check.yml
python3 -B replay_shards.py avocado-shack shard-membership.txt
```

Save this as `replay_shards.py` outside the checkout. Use a new output filename if `shard-membership.txt` already exists. The probe imports the planner, not the test modules; it calls neither `plan` (which imports test modules to count cases) nor `run` (`hass/tests/ci_shards.py:390–399,460–480`).

```python
from pathlib import Path
import runpy
import sys
from collections import Counter
import subprocess

root = Path(sys.argv[1])
p = runpy.run_path(str(root / 'hass/tests/ci_shards.py'))
names = p['all_modules']()
w = p['load_weights']()
current, recorded = set(names), set(w)
tracked_files = subprocess.check_output(['git', '-C', root, 'ls-tree', '-r', '--name-only', 'HEAD', '--', 'hass/tests'], text=True).splitlines()
assert {p['test_path'](n) for n in names} == {s for s in tracked_files if Path(s).match('test_*.py')}
missing, stale = sorted(current - recorded), sorted(recorded - current)
matched = sum(w[n] for n in current & recorded)
print(sys.version.split()[0], len(names), len(current & recorded), len(w), len(missing), len(stale), sum(w.values()), matched)
print('Missing:', ', '.join(missing))
print('Stale:', [(n, w[n]) for n in stale])
actual = lambda n: p['weight'](n, w)
widths = (1, 2, 4, 8)
assignment = {}
for k in widths:
    groups = p['partition'](names, k, w)
    sums = [sum(map(actual, g)) for g in groups]
    counts = [len(g) for g in groups]
    assert Counter(n for g in groups for n in g) == Counter(names)
    assignment[k] = {n: i for i, g in enumerate(groups) for n in g}
    print(k, counts, sums, max(sums) - min(sums), sum(sums))
    if k == 4:
        print('Quarter nominal:', sum(sums) / 16, 'Quarters per shard:', [s / 4 for s in sums])
        print('Over quarter:', [(i, n, actual(n)) for i, g in enumerate(groups) for n in g if 4 * actual(n) > sums[i]])
for label, pool in [('recorded', recorded), ('matched', recorded & current)]:
    top = sorted(pool, key=lambda n: (-w[n], n))[:10]
    subtotal, total = sum(w[n] for n in top), sum(w[n] for n in pool)
    print(label, [(n, w[n]) for n in top], subtotal, total, f'{subtotal / total:.4%}')
print('Appendix rows:', len(names))
if len(sys.argv) > 2:
    with Path(sys.argv[2]).open('x') as out:
        for n in names:
            print(n, *(assignment[k][n] for k in widths), file=out)
```

<details>
<summary>Full membership for all four widths (901 rows)</summary>

Each column holds that module's zero-based shard ID at the stated width.

```text
module  shards=1  shards=2  shards=4  shards=8
test_acceptance_jpeg_segment_order 0 1 2 3
test_acceptance_runner 0 0 2 4
test_additive_state 0 1 3 5
test_again 0 1 3 5
test_again_reverted 0 0 1 1
test_alert_log_window 0 1 1 2
test_answer_reader_request 0 0 2 3
test_attach 0 1 0 5
test_attachment_input_types 0 1 3 7
test_attachment_reply 0 1 3 1
test_attachment_retry 0 0 2 7
test_audit 0 1 0 6
test_audit_calendar 0 0 0 1
test_audit_log_days 0 1 1 2
test_auto_policy 0 0 0 6
test_auto_policy_dated 0 1 1 7
test_auto_policy_shapes 0 0 2 0
test_availability_own_day 0 0 2 3
test_availability_phrase_overlap 0 1 3 3
test_availability_words_pin 0 0 0 4
test_backlog_forget_bounds 0 1 3 4
test_bare_yes_question 0 1 0 2
test_bridge 0 1 1 5
test_bridge_edit_ids 0 0 2 6
test_bridge_photos 0 1 3 7
test_bridge_photos_ids 0 0 0 0
test_bridge_photos_metadata_keys 0 1 1 1
test_bridge_photos_port_zero 0 0 2 2
test_bridge_photos_size 0 1 3 3
test_bridge_photos_tail 0 0 0 4
test_bridge_photos_unicode 0 1 1 5
test_bridge_pictures 0 0 2 6
test_bridge_reactions 0 1 3 7
test_bridge_timestamp_precision 0 0 0 0
test_browser_freshness 0 1 1 1
test_cancel_all 0 0 0 5
test_cancel_question 0 0 3 3
test_candidate_answer_safety 0 1 1 6
test_capabilities 0 0 2 2
test_capabilities_check_errors 0 1 3 3
test_catalog_badge 0 1 0 4
test_catalog_clear_filters 0 0 0 4
test_catalog_dupes 0 0 2 7
test_catalog_file_check 0 1 3 1
test_catalog_limits 0 0 1 5
test_catalog_lookup_fold 0 1 1 5
test_catalog_new_order 0 1 2 6
test_catalog_ops 0 0 0 2
test_catalog_place 0 0 3 0
test_catalog_unchanged 0 1 0 1
test_catalog_unchanged_spacing 0 0 1 2
test_chaos_suite 0 1 1 3
test_chat_dead_end_reasons 0 0 2 4
test_chat_scenarios 0 0 3 5
test_ci_shards 0 0 2 6
test_claims 0 1 3 7
test_claims_access 0 0 0 0
test_claims_dash_negation 0 1 1 1
test_claims_farm 0 0 2 2
test_claims_grades 0 1 3 3
test_claims_health_awards 0 0 0 4
test_claims_lists 0 1 1 5
test_claims_maker_negation 0 0 2 6
test_claims_negation 0 1 3 7
test_claims_negation_spelling 0 0 0 0
test_claims_nested 0 1 1 1
test_claims_numbers 0 1 2 3
test_claims_source_negation 0 0 2 2
test_claims_sources 0 1 3 3
test_clear_availability 0 1 3 5
test_cloud_codex 0 0 0 6
test_clover_apply 0 1 1 7
test_clover_apply_identity 0 0 2 1
test_clover_cache 0 0 0 4
test_clover_cache_category_shapes 0 1 3 2
test_clover_chat 0 0 3 4
test_clover_chat_line_separators 0 0 0 3
test_clover_chat_writes 0 1 1 4
test_clover_checks 0 0 2 5
test_clover_cli 0 1 1 5
test_clover_client 0 0 2 6
test_clover_config_merchant_ids 0 1 3 6
test_clover_count_phrases 0 0 0 7
test_clover_credential 0 1 3 7
test_clover_credential_parent 0 1 1 1
test_clover_drafts 0 0 0 0
test_clover_drafts_extreme_count 0 0 2 2
test_clover_dryrun 0 1 3 3
test_clover_fake 0 0 0 4
test_clover_host 0 1 1 5
test_clover_host_engine 0 0 2 6
test_clover_item_ids 0 1 3 7
test_clover_journal_lock_open 0 0 0 1
test_clover_links 0 1 1 2
test_clover_mapper 0 1 1 1
test_clover_pos 0 0 2 3
test_clover_qty_words 0 1 3 4
test_clover_reads 0 0 2 2
test_clover_reads_elapsed 0 0 0 5
test_clover_report_source_file 0 1 1 6
test_clover_reports 0 1 0 5
test_clover_retry_after_input 0 0 2 7
test_clover_sku 0 1 3 3
test_clover_sku_iterables 0 1 3 1
test_clover_sku_suffix 0 0 0 2
test_clover_transport_close 0 1 1 3
test_clover_write_readiness 0 0 2 4
test_club_intro 0 0 0 5
test_command_typo 0 1 3 5
test_commands_doc 0 0 0 4
test_community_email_controls 0 0 0 6
test_content 0 1 1 5
test_content_deep_json 0 0 2 6
test_content_read_errors 0 1 3 7
test_content_schema_version_type 0 1 1 7
test_content_starts_at 0 0 0 0
test_content_text_chars 0 1 1 1
test_conversation 0 0 2 1
test_corrlog 0 1 3 3
test_corrlog_short_write 0 1 3 2
test_corrlog_time_edges 0 0 0 3
test_cost_by_name 0 1 1 4
test_costs_command 0 0 2 5
test_demo_browser 0 1 3 6
test_demo_browser_photo 0 0 3 3
test_demo_negative 0 0 1 6
test_demo_rehearsal 0 1 1 7
test_demo_transcript 0 1 2 7
test_demo_transcript_photo 0 0 3 5
test_deploy_units 0 0 2 2
test_description_style_audit 0 1 3 6
test_design_check 0 0 3 0
test_design_check_launch 0 1 3 3
test_design_check_merge_base 0 0 0 4
test_design_check_modes 0 1 1 5
test_design_check_relative 0 0 2 6
test_design_notes 0 0 0 7
test_design_preview 0 0 1 2
test_design_preview_artifacts 0 1 3 7
test_design_preview_blob_launch 0 1 0 1
test_design_preview_git_dirs 0 0 0 0
test_design_preview_png_signature 0 1 1 1
test_drill_export_compare 0 1 1 1
test_editor 0 0 2 2
test_editor_candidate 0 1 3 3
test_editor_cli_io 0 0 0 4
test_editor_config_read 0 0 1 2
test_editor_history_limit 0 0 2 2
test_editor_request_duplicates 0 1 2 3
test_editor_request_limits 0 0 3 4
test_editor_show_shape 0 1 0 5
test_fast_ack 0 0 1 6
test_field_words 0 1 3 3
test_find 0 0 1 6
test_find_hikes 0 1 2 7
test_fixture_chat 0 1 0 5
test_fixture_chat_deep_json 0 1 1 5
test_fixture_chat_id_encoding 0 0 1 7
test_fixture_chat_inputs 0 0 2 6
test_fixture_chat_jsonl_framing 0 1 3 7
test_fixture_chat_labels 0 1 2 1
test_fixture_chat_queue 0 0 3 2
test_fixture_chat_rows 0 0 3 0
test_fixture_chat_utc_range 0 1 0 1
test_forwarder 0 0 0 4
test_forwarder_photo 0 0 0 1
test_forwarder_receipt 0 1 1 2
test_front 0 0 2 5
test_front_page_literal_style 0 1 2 6
test_front_pages 0 1 3 6
test_front_sections_colour_words 0 0 2 3
test_generated_compare_bounds 0 1 1 5
test_generated_io 0 0 2 6
test_generated_links 0 1 3 7
test_generated_parent_types 0 0 0 0
test_generated_targets 0 1 1 1
test_health 0 0 2 2
test_health_backup_content 0 1 3 3
test_health_backup_verify 0 0 0 4
test_health_disk 0 1 1 5
test_health_guests 0 0 2 6
test_health_guests_mixed 0 1 3 7
test_health_host 0 0 0 0
test_health_inbox 0 1 1 1
test_health_label_model 0 0 2 2
test_health_media 0 1 3 3
test_health_memory 0 0 0 4
test_health_memory_offsets 0 1 3 4
test_health_model 0 1 1 5
test_health_pause_redaction 0 0 0 5
test_health_paused 0 0 2 6
test_health_seen 0 1 3 7
test_health_seen_read 0 0 0 0
test_health_state_db 0 1 1 1
test_health_unreadable 0 0 2 2
test_health_unused_photos 0 0 1 2
test_health_unverified 0 1 3 3
test_health_window_bounds 0 0 0 4
test_health_writer 0 1 2 3
test_held_command 0 1 1 6
test_help 0 1 1 5
test_help_listing 0 0 2 7
test_help_text_voice_check 0 1 3 1
test_hidden_command 0 0 3 4
test_hike_anchor 0 1 0 5
test_hike_cache_shapes 0 0 0 2
test_hike_cancel_note 0 1 2 5
test_hike_capacity_ceiling 0 0 1 6
test_hike_capacity_rsvp_off 0 0 1 1
test_hike_change_words 0 0 2 6
test_hike_chat_capacity_conflict 0 1 3 7
test_hike_chat_meeting 0 0 0 0
test_hike_chat_meeting_limit 0 1 2 7
test_hike_chat_offer_limit 0 1 1 1
test_hike_chat_route_specificity 0 0 2 2
test_hike_chat_title_boundary 0 1 3 3
test_hike_clear 0 1 1 3
test_hike_coordinate_overflow 0 0 0 4
test_hike_create_capacity_conflict 0 0 2 4
test_hike_decimal_capacity 0 1 3 5
test_hike_difficulty_case 0 0 3 0
test_hike_elevation_identity 0 1 1 5
test_hike_far_future 0 1 0 1
test_hike_fetch_finite_json 0 0 0 6
test_hike_fetch_http_errors 0 0 2 6
test_hike_flow 0 0 0 1
test_hike_guest_rows 0 1 0 3
test_hike_guest_warning 0 0 1 7
test_hike_ics 0 0 1 2
test_hike_ids 0 1 1 7
test_hike_journal 0 1 2 3
test_hike_limits 0 0 2 1
test_hike_lookup 0 0 3 4
test_hike_lookup_chat 0 1 3 2
test_hike_meeting_warning 0 1 1 2
test_hike_move_warning 0 1 2 4
test_hike_nonprice_packing 0 1 3 7
test_hike_ops 0 1 3 2
test_hike_recap 0 0 0 3
test_hike_recap_spacing 0 1 1 4
test_hike_repeat 0 1 1 2
test_hike_repeat_claims 0 1 0 5
test_hike_rsvp_on 0 0 2 5
test_hike_rsvp_reenable 0 1 3 6
test_hike_samples 0 0 0 1
test_hike_signup_mismatch 0 0 1 6
test_hike_time_text 0 0 0 0
test_hike_trail_refused 0 1 2 7
test_hike_twin 0 0 0 7
test_hike_update_spacing 0 0 3 0
test_hike_update_twin 0 1 1 1
test_history_approved 0 1 0 1
test_history_revert_deep 0 0 1 2
test_history_search 0 1 2 3
test_history_times 0 0 2 2
test_host 0 1 0 3
test_hours_keep_day 0 1 3 3
test_house_render_seam 0 0 2 1
test_house_style_cli_errors 0 1 1 1
test_house_style_maker_text 0 0 2 2
test_house_style_maker_url 0 1 3 3
test_house_style_owner_clauses 0 0 0 4
test_house_style_product_id 0 0 0 4
test_house_style_product_image 0 1 1 5
test_house_style_product_maker_link 0 1 1 5
test_house_style_product_text 0 0 2 6
test_https_links 0 1 3 7
test_image_arg 0 0 0 0
test_image_dimensions 0 0 3 4
test_inbound_deep_json 0 1 0 5
test_inbox 0 0 1 6
test_inbox_nofollow 0 1 1 1
test_inbox_nonces 0 1 2 7
test_inbox_payload_types 0 0 3 0
test_inbox_recorded_start 0 0 2 2
test_inbox_retry_metadata 0 0 2 6
test_inbox_status 0 1 3 3
test_inbox_status_clock 0 0 0 4
test_inbox_status_snapshot 0 1 1 5
test_inbox_status_start_at 0 0 2 6
test_inbox_unreadable 0 1 3 7
test_info_pages_check 0 1 3 7
test_install 0 0 3 5
test_install_acceptance_receipt 0 0 0 1
test_install_allowlist_diff 0 1 1 2
test_install_backup_receipt 0 0 2 3
test_install_ci_receipt 0 1 3 4
test_install_citation_drift 0 0 0 5
test_install_config_attributes 0 1 1 6
test_install_digest_ledger 0 0 2 7
test_install_entry_gate 0 1 3 1
test_install_launchagent 0 0 0 2
test_install_mac_parity 0 1 1 3
test_install_pending_work 0 0 2 4
test_install_preflight_verdict 0 1 3 5
test_install_preread 0 1 0 1
test_install_private_files 0 0 0 6
test_install_quiescence 0 1 1 0
test_install_records 0 0 2 7
test_install_rehearsal 0 1 3 1
test_install_release_lineage 0 0 0 2
test_install_revert_scan 0 1 1 3
test_install_rollback_proof 0 0 2 4
test_install_runtime_readback 0 1 3 5
test_install_service_restart 0 0 0 6
test_install_skill_parity 0 1 1 0
test_install_skill_restore_proof 0 0 2 7
test_install_skill_shadow 0 1 3 1
test_install_stage_file 0 0 0 2
test_install_status_shape 0 0 0 0
test_install_store_schema 0 1 1 3
test_install_switch_projection 0 0 2 4
test_install_switch_readback 0 1 3 5
test_install_target_inspection 0 0 0 6
test_install_tools_checkout 0 1 1 0
test_install_window_clock 0 0 2 7
test_intake_simple 0 1 3 1
test_interpret_check 0 1 1 1
test_interpret_check_count 0 0 2 2
test_interpret_check_enum 0 1 3 3
test_interpret_check_lookup 0 0 0 2
test_interpret_check_names 0 0 0 4
test_interpret_check_none 0 1 1 5
test_interpret_check_prices 0 0 2 6
test_interpret_check_repeat 0 1 3 7
test_interpret_check_skill_envelope 0 0 0 0
test_interpret_check_spacing 0 1 1 1
test_interpreter_aliases 0 0 1 2
test_interpreter_audit_report 0 1 1 3
test_interpreter_cap 0 1 2 3
test_interpreter_eval 0 0 2 2
test_interpreter_eval_cases 0 1 3 3
test_interpreter_eval_compare 0 0 0 4
test_interpreter_eval_diagnostics 0 1 1 5
test_interpreter_eval_modes 0 0 2 6
test_interpreter_eval_out 0 1 3 7
test_interpreter_fallback_depth 0 0 0 0
test_interpreter_fallback_exception 0 1 1 1
test_interpreter_local 0 0 2 2
test_interpreter_local_strict 0 1 3 3
test_interpreter_no_undo 0 0 0 4
test_interpreter_notes 0 0 3 4
test_interpreter_openai 0 0 2 4
test_interpreter_prompt 0 1 1 5
test_interpreter_prompt_brand 0 0 2 6
test_interpreter_prompt_club_shape 0 1 3 7
test_interpreter_prompt_community 0 0 0 0
test_interpreter_prompt_descriptions 0 1 1 1
test_interpreter_prompt_design 0 0 2 2
test_interpreter_prompt_home_text 0 1 3 3
test_interpreter_prompt_numeric_suffix 0 0 0 4
test_interpreter_prompt_shapes 0 1 1 5
test_interpreter_prompt_shelf_maker 0 0 2 6
test_interpreter_prompt_skills 0 1 0 5
test_interpreter_prompt_store 0 1 3 7
test_interpreter_prompt_surrogates 0 0 0 0
test_interpreter_prompt_text 0 1 1 1
test_interpreter_reply_numbers 0 0 2 2
test_interpreter_reply_unicode 0 1 3 3
test_interpreter_request_encode 0 0 0 4
test_interpreter_today 0 1 1 5
test_item_add_dispatch 0 1 3 5
test_item_both 0 1 3 5
test_item_hide_permanent_intent 0 0 1 6
test_item_intake_conversation 0 1 0 6
test_item_intake_priced_text 0 0 0 6
test_item_intake_unit_admission 0 1 1 0
test_item_picture_home_rejection 0 0 2 6
test_item_picture_unicode_choice 0 1 3 7
test_item_picture_unicode_home_rejection 0 0 2 7
test_item_price_numbers 0 1 3 1
test_item_price_spaces 0 0 0 0
test_itemstd 0 1 2 7
test_itemstd_duplicate_keys 0 0 0 2
test_itemstd_gap_diff 0 1 1 3
test_itemstd_schema_version 0 1 1 1
test_itemstd_surrogates 0 0 2 4
test_label_case_coverage 0 1 3 5
test_label_eval 0 0 2 2
test_label_eval_modes 0 1 3 3
test_label_matches 0 0 0 4
test_label_question_brand 0 1 1 5
test_label_reader 0 0 2 3
test_label_reader_amounts 0 0 2 6
test_label_reader_claim_lookalikes 0 1 3 7
test_label_reader_compact_fractions 0 0 0 6
test_label_reader_forbidden 0 0 0 0
test_label_reader_fractions 0 1 1 1
test_label_reader_multiplied_sizes 0 0 2 2
test_label_reader_separators 0 1 3 3
test_label_reader_spacing 0 0 0 4
test_late_reply 0 0 3 0
test_late_yes 0 1 0 1
test_ledger_rf1120 0 1 3 4
test_limits_doc 0 1 1 5
test_listing_by_name 0 1 1 0
test_listing_command 0 0 1 2
test_listing_exact_identity 0 0 2 7
test_listing_store 0 1 3 1
test_live_add 0 0 1 7
test_live_add_photo_undo 0 0 0 6
test_live_drill 0 0 2 5
test_live_owners 0 1 2 2
test_live_policy 0 0 2 6
test_live_proposal 0 0 1 1
test_live_selftest 0 0 1 1
test_live_selftest_check_ids 0 0 0 2
test_live_table 0 1 2 2
test_local_business_data 0 1 3 7
test_look_change 0 1 1 3
test_look_command 0 0 2 4
test_look_engine 0 1 3 5
test_lookalike_twins 0 1 2 3
test_loopback_port_zero 0 0 0 0
test_mac_kit 0 1 1 1
test_mac_runbook 0 0 2 2
test_maker_hide_products 0 0 0 6
test_maker_optional_story 0 0 3 3
test_maker_optional_url 0 0 3 4
test_maker_price_words 0 1 1 0
test_maker_product_batch 0 0 0 3
test_maker_rename_warning 0 0 2 7
test_maker_site 0 1 3 3
test_maker_site_break_spacing 0 1 3 1
test_maker_site_hidden_meta 0 0 0 2
test_maker_site_http_errors 0 0 0 4
test_maker_site_sec3 0 1 0 1
test_maker_story_case 0 1 1 3
test_maker_twin_shadow 0 1 1 5
test_margin_chat 0 1 0 5
test_margins 0 0 2 6
test_margins_context 0 1 3 7
test_margins_percent_decimals 0 0 0 0
test_margins_plain_numbers 0 1 1 1
test_margins_price_check 0 0 2 2
test_margins_say_context 0 1 3 3
test_margins_say_precision 0 0 2 4
test_media 0 0 0 4
test_media_audio 0 0 1 6
test_media_audio_compatible 0 1 1 5
test_media_audio_formats 0 1 2 7
test_media_batch 0 0 2 6
test_media_ifd_bounds 0 1 3 5
test_media_orientation 0 1 3 7
test_media_sidecar_read 0 0 0 0
test_media_time 0 1 1 1
test_media_verify 0 0 3 0
test_media_verify_original_kind 0 0 0 6
test_media_verify_sidecar 0 0 2 2
test_media_verify_web 0 1 3 3
test_media_web 0 0 0 4
test_memory 0 1 1 5
test_memory_alias 0 1 0 1
test_memory_blank 0 0 2 6
test_memory_chat 0 0 1 2
test_memory_hidden_chars 0 1 3 7
test_memory_history 0 0 0 0
test_memory_history_ancestors 0 1 1 1
test_memory_history_cells 0 0 2 2
test_memory_listing 0 1 2 3
test_memory_source 0 1 3 3
test_memory_unchanged 0 0 3 4
test_migration_assets 0 0 0 4
test_migration_aux_deep_json 0 1 1 5
test_migration_aux_duplicates 0 0 2 6
test_migration_base_commit_unicode 0 1 3 7
test_migration_baseline_shape 0 0 0 0
test_migration_maker_urls 0 1 1 0
test_migration_storefront_shape 0 1 1 1
test_morning_report 0 0 2 2
test_morning_report_future 0 1 3 3
test_morning_report_hikes 0 0 0 4
test_morning_report_names 0 1 1 5
test_morning_report_restock 0 0 2 6
test_morning_report_shapes 0 1 3 7
test_named_records 0 0 0 0
test_near_approval 0 1 0 5
test_needs_details_expiry 0 0 1 6
test_newitem 0 0 1 7
test_newitem_claim_omission 0 1 1 1
test_newitem_demo 0 0 2 2
test_newitem_demo_alpha 0 1 3 3
test_newitem_name_grounding 0 0 0 4
test_newitem_parse_facts 0 1 1 5
test_newitem_preview_identity 0 0 2 6
test_newitem_render_16bit 0 1 2 7
test_newitem_render_alpha 0 0 3 0
test_newitem_render_gradient 0 1 0 7
test_newitem_render_holes 0 1 1 4
test_newitem_render_scale_warning 0 1 0 1
test_newitem_render_shadow_continuity 0 0 1 2
test_newitem_render_translucent_luma 0 0 2 7
test_newitem_synthetic 0 1 3 7
test_newitem_synthetic_alpha 0 0 1 2
test_newitem_synthetic_format 0 0 0 0
test_newitem_synthetic_gps 0 1 1 1
test_newitem_synthetic_orientation 0 0 2 2
test_newitem_synthetic_selectors 0 1 3 3
test_nl_corpus_ops_check 0 1 3 1
test_nl_eval 0 0 0 4
test_nl_eval_expected_limit 0 1 1 5
test_nl_eval_failure_codes 0 0 2 6
test_nl_eval_latency 0 1 3 7
test_nl_eval_order 0 0 0 0
test_nl_eval_schema 0 1 1 1
test_nl_eval_selection_args 0 0 0 2
test_nl_eval_words 0 0 2 2
test_nl_intent_coverage 0 1 1 3
test_nl_prep 0 0 2 4
test_nl_prep_calendar 0 1 3 3
test_nl_prep_fuzzy 0 0 0 4
test_nl_prep_hours_day_tokens 0 1 1 5
test_nl_prep_ordinal_words 0 1 3 5
test_nl_prep_ordinals 0 0 2 6
test_non_hike_question_turns 0 0 0 6
test_noscript 0 1 3 7
test_not_read_reply 0 1 2 3
test_notice_calendar_bounds 0 0 1 4
test_notice_specials_coherence 0 0 3 4
test_notice_specials_prestart 0 0 0 0
test_notice_start 0 0 0 7
test_npp_answers 0 1 1 0
test_npp_assets 0 0 2 7
test_npp_caption_table 0 1 3 1
test_npp_case_new 0 0 0 2
test_npp_chat_page 0 1 1 3
test_npp_copy 0 0 2 4
test_npp_edit_eval 0 1 3 5
test_npp_edit_phrases 0 0 0 6
test_npp_edits 0 1 1 0
test_npp_evidence 0 0 2 7
test_npp_findings 0 1 3 1
test_npp_identify 0 0 0 2
test_npp_job 0 1 1 3
test_npp_jobs 0 0 2 4
test_npp_missing 0 1 3 5
test_npp_owner_guide 0 0 0 6
test_npp_photo 0 1 1 0
test_npp_posted_link 0 0 2 7
test_npp_preflight 0 1 3 1
test_npp_price_provenance 0 0 0 2
test_npp_private_numbers 0 1 1 3
test_npp_render_evidence 0 0 2 4
test_npp_research 0 1 3 5
test_npp_review_export 0 0 0 6
test_npp_second_product 0 1 1 0
test_npp_stages 0 0 2 7
test_npp_status_line 0 1 3 1
test_npp_transcript_check 0 0 0 2
test_npp_undo_journey 0 1 1 3
test_npp_validate 0 0 2 4
test_open_request_calendar 0 1 1 1
test_open_request_elapsed 0 0 2 2
test_open_request_repeat_photo 0 1 3 3
test_open_request_status_expiry 0 0 0 4
test_open_requests 0 1 3 5
test_opening_hours_data 0 1 1 5
test_organic_sync 0 1 0 5
test_outbox_delayed 0 0 2 6
test_output_hygiene 0 0 1 6
test_owner_answers 0 1 2 7
test_owner_answers_approved 0 1 3 7
test_owner_answers_future 0 0 0 0
test_owner_answers_rollback 0 1 1 1
test_owner_answers_shapes 0 0 2 2
test_owner_answers_summary 0 1 3 3
test_owner_answers_unknown_state 0 0 0 4
test_owner_answers_when 0 1 1 5
test_owner_chat_config 0 0 2 6
test_owner_sender_match 0 0 3 0
test_owner_text_cap 0 1 0 1
test_owners_transport 0 0 1 2
test_owners_two 0 0 0 1
test_page_claim_punctuation 0 1 3 7
test_page_photo_dual_destination 0 0 0 6
test_pending_ops 0 1 2 3
test_phone_answers 0 1 1 0
test_phone_guide 0 0 0 0
test_phone_wording 0 0 2 7
test_photo_batch 0 1 1 7
test_photo_caption_reader_failed 0 0 3 4
test_photo_detail_read 0 1 3 1
test_photo_draft 0 1 2 5
test_photo_home_image 0 1 1 7
test_photo_limits 0 0 0 2
test_photo_new_product 0 1 1 3
test_photo_on_product 0 0 3 6
test_photo_polish 0 0 2 4
test_photo_polish_ocr_box 0 1 3 5
test_photo_polish_ocr_tsv 0 0 0 6
test_photo_polish_runner_shapes 0 1 1 0
test_photo_retry 0 0 2 7
test_photo_store_oserror 0 1 3 1
test_photo_trial 0 0 1 3
test_photo_trial_output_errors 0 0 0 2
test_photos_to_take 0 1 0 5
test_pilot_approvals 0 1 1 3
test_pilot_card_png 0 0 2 4
test_pilot_change_record 0 1 3 5
test_pilot_content_diff 0 0 0 6
test_pilot_inbound 0 1 1 0
test_pilot_photo_receipts 0 0 2 7
test_pilot_private_scan 0 1 3 1
test_pilot_receipt_new 0 0 0 2
test_pilot_reply_match 0 1 1 3
test_pilot_scenario_check 0 0 2 4
test_pilot_sender_check 0 1 3 5
test_plain_shelf_check 0 0 0 6
test_post_availability 0 1 1 0
test_post_by_name 0 0 2 7
test_post_command 0 1 1 1
test_post_hike_command 0 0 2 2
test_post_maker_command 0 1 3 3
test_post_notice_command 0 1 3 1
test_preview 0 0 2 7
test_preview_cancel_note 0 1 1 1
test_preview_checks_shape 0 0 2 5
test_preview_event_before 0 0 0 4
test_preview_hike_results 0 1 3 4
test_preview_maker 0 1 1 6
test_preview_new_item_word 0 0 1 2
test_preview_new_photo 0 1 3 2
test_preview_overlay 0 1 1 5
test_preview_png_signature 0 0 2 6
test_preview_product_checks 0 1 3 1
test_preview_retry 0 0 1 6
test_preview_route_results 0 1 3 2
test_preview_store_address 0 0 0 4
test_preview_store_checks 0 1 3 6
test_preview_target_shapes 0 1 3 7
test_preview_viewports 0 1 0 4
test_preview_write_private 0 0 0 0
test_producers_file_check 0 0 0 2
test_product_add_photo 0 1 0 1
test_product_alt 0 1 1 3
test_product_claims_receipt_shape 0 0 2 4
test_product_default_brand 0 1 3 5
test_product_new 0 0 0 6
test_proposal_added 0 1 1 1
test_proposal_full_text 0 0 2 2
test_proposal_notice_words 0 1 1 0
test_proposal_photo_words 0 0 2 7
test_publish 0 1 3 3
test_publish_404 0 0 0 4
test_publish_csp 0 0 1 6
test_publish_gate 0 1 3 1
test_publish_home_image 0 1 1 5
test_publish_live 0 1 0 1
test_publish_sources_check 0 0 0 2
test_purchase_cost 0 1 1 3
test_qa1_fixes 0 0 2 6
test_qa1_new_item_chat 0 1 3 1
test_qa1_waiting_reminders 0 0 1 2
test_qa_env 0 0 2 4
test_qa_scripts_live 0 1 3 7
test_question_lookup 0 1 3 5
test_question_missing_fields 0 0 0 6
test_readonly_questions 0 0 0 0
test_receiver 0 1 1 0
test_receiver_atomic_intake 0 0 2 7
test_receiver_received_time 0 1 2 7
test_receiver_size 0 0 3 0
test_receiver_strict_json 0 1 0 1
test_relay 0 1 1 1
test_relay_op_shape 0 0 2 2
test_relay_photos 0 1 3 1
test_relay_receipt 0 0 0 2
test_relay_shot_index_types 0 1 3 3
test_release_journal 0 0 0 4
test_release_journal_strict_read 0 1 1 3
test_release_pending_recovery 0 0 2 4
test_rendered_a11y_check 0 1 3 5
test_rendered_anchor_check 0 0 0 6
test_rendered_jsonld_check 0 1 1 0
test_rendered_link_check 0 0 2 7
test_repeat_outcome 0 1 3 1
test_report_command 0 0 1 2
test_report_count_low_modifier 0 1 1 5
test_report_waiting 0 0 2 6
test_restock_decimal_counts 0 0 0 2
test_restock_more_counts 0 1 1 3
test_restock_op 0 0 2 4
test_restock_prefix_multiplier 0 1 3 5
test_restock_spoken_counts 0 0 0 6
test_restore_image_rule 0 1 1 0
test_retention 0 1 3 7
test_retention_approvals_memory 0 0 0 0
test_retention_bounds 0 1 1 1
test_retention_options_doc 0 0 2 2
test_retention_paths 0 1 3 3
test_retention_report_diff 0 0 2 7
test_retention_root_ancestors 0 0 0 4
test_retention_screenshots 0 1 1 5
test_retention_sidecar_read 0 0 2 6
test_retention_uncounted_tables 0 1 3 1
test_retention_utc_range 0 1 3 7
test_retention_web_orphans 0 0 0 0
test_retention_web_temp_files 0 0 0 2
test_revert_event_shape 0 1 1 3
test_revert_parent_directory 0 1 1 1
test_revert_record_files 0 0 2 4
test_revert_records 0 1 3 5
test_revises_expired_vs_unknown 0 0 2 2
test_route_add 0 1 2 3
test_route_edit 0 1 2 3
test_route_edit_spacing 0 0 3 4
test_route_edit_titles 0 1 0 5
test_route_edit_unicode 0 0 1 6
test_route_hide 0 0 0 6
test_route_idea_dates 0 1 1 0
test_route_limits 0 1 2 7
test_route_link_warning 0 0 3 0
test_run_parallel 0 1 3 3
test_runtime_release 0 1 0 1
test_sandbox 0 0 3 6
test_sandbox_draft_roots 0 0 1 2
test_sandbox_member_shapes 0 0 2 7
test_saved_cost_dates 0 1 3 1
test_scaffold_setup_depth 0 0 0 2
test_screenshot_refs 0 1 1 3
test_sec2_late_yes 0 1 2 3
test_sec2_live_gate 0 0 0 4
test_sec2_release 0 0 2 6
test_second_question 0 0 2 4
test_selection_backdate_window 0 0 3 4
test_selection_checked 0 1 3 5
test_selection_per_product_day 0 0 0 6
test_selection_refusal_atomic 0 1 1 5
test_selftest_summary_check 0 1 1 0
test_set_availability_all 0 0 2 7
test_set_photo 0 1 3 6
test_set_photo_alt 0 1 3 7
test_set_photo_alt_article 0 1 0 5
test_set_photo_alt_cameras 0 0 3 7
test_set_photo_alt_defaults 0 1 0 4
test_set_photo_alt_length 0 0 0 5
test_set_photo_folder 0 0 2 6
test_set_photo_site_read 0 0 1 5
test_settings_config_file 0 1 3 7
test_shelf_check_except 0 1 3 1
test_shelf_check_flow 0 0 1 4
test_shelf_command 0 0 0 2
test_shelf_labels 0 0 0 0
test_shop_length_replies 0 1 1 3
test_show 0 0 1 6
test_signup_options_doc 0 1 1 1
test_site_hours_abbreviations 0 0 2 4
test_site_hours_word_ranges 0 1 3 5
test_sitegen_selling_price 0 0 0 6
test_skill_dispatch 0 0 3 6
test_skill_dispatch_hooks 0 0 0 2
test_skill_hidden_route 0 0 2 2
test_skill_multicall_left_off 0 1 1 0
test_skill_notice_conflict 0 1 2 6
test_skill_original_read_bounds 0 1 3 3
test_skill_title_boundaries 0 1 2 7
test_skills_acceptance_chain 0 0 2 7
test_skills_acceptance_groups 0 1 3 3
test_skills_acceptance_json 0 0 0 4
test_skills_acceptance_offline 0 0 2 4
test_skills_backlog 0 1 1 5
test_skills_cases 0 0 0 0
test_skills_contact_missing_phone 0 0 2 7
test_skills_faq_preroute 0 1 2 3
test_skills_hikes 0 1 2 4
test_skills_hours_conjunction 0 0 2 6
test_skills_hours_unnamed_additions 0 0 3 0
test_skills_item_add 0 1 0 1
test_skills_item_picture 0 1 2 3
test_skills_items 0 1 1 3
test_skills_lint 0 1 3 7
test_skills_makers 0 1 3 7
test_skills_model 0 0 0 0
test_skills_photo_conflict 0 1 1 1
test_skills_photo_destination 0 0 2 2
test_skills_plan_output_shapes 0 1 3 1
test_skills_plans 0 1 3 3
test_skills_reports 0 1 2 3
test_skills_restock 0 0 3 1
test_skills_router 0 0 0 4
test_skills_scaffold 0 1 1 1
test_skills_shop 0 0 1 5
test_skills_social 0 1 0 2
test_skills_specials 0 1 2 4
test_skills_stock 0 0 2 5
test_skills_testkit_clock 0 1 2 2
test_social_draft 0 1 1 5
test_social_draft_fullwidth 0 0 2 6
test_social_draft_hike 0 1 3 7
test_social_draft_inputs 0 0 0 0
test_social_draft_maker 0 1 1 1
test_social_draft_notice 0 0 0 2
test_social_draft_now 0 0 2 2
test_social_draft_shapes 0 1 3 3
test_social_draft_tags 0 0 0 4
test_social_draft_text 0 1 1 5
test_social_message 0 0 1 3
test_social_negated_posting 0 1 1 3
test_social_recap 0 1 1 1
test_social_send_short 0 0 2 4
test_special_contact_patterns 0 1 3 5
test_special_title_resolution 0 0 2 6
test_specials 0 1 3 2
test_specials_edit_titles 0 0 0 6
test_specials_op_clock 0 1 3 7
test_stagelog_destinations 0 1 1 0
test_stagelog_jsonl_framing 0 0 0 0
test_stagelog_offsets 0 1 1 1
test_stagelog_output 0 0 2 2
test_stagelog_read_files 0 0 2 7
test_stagelog_timestamps 0 1 3 3
test_state_db_nofollow 0 0 0 4
test_statebackup 0 0 2 2
test_statebackup_atomic 0 1 3 3
test_statebackup_bundle 0 1 2 7
test_statebackup_clover 0 1 3 1
test_statebackup_commit 0 0 0 2
test_statebackup_config_shape 0 0 1 2
test_statebackup_config_size 0 0 3 4
test_statebackup_content 0 1 0 5
test_statebackup_diff 0 0 1 6
test_statebackup_drill 0 1 2 1
test_statebackup_exact_modes 0 1 1 3
test_statebackup_inbox 0 0 2 4
test_statebackup_list 0 1 3 5
test_statebackup_manifest_read 0 0 0 6
test_statebackup_media 0 1 1 0
test_statebackup_paused 0 1 2 3
test_statebackup_restore_atomic 0 0 3 4
test_statebackup_worktree_binding 0 0 2 7
test_statebackup_worktree_nul 0 1 3 1
test_status_notice 0 0 3 2
test_status_past_hikes 0 0 0 2
test_status_pause 0 1 0 3
test_status_photos 0 0 1 7
test_status_reader_failed 0 1 0 5
test_status_rsvp_off 0 1 1 3
test_status_shelf_check 0 0 1 6
test_stock_checked_conflict 0 1 2 4
test_stock_list_references 0 1 2 7
test_stock_product_choice 0 0 2 4
test_stock_single_token_references 0 1 3 5
test_stock_site 0 0 0 6
test_stock_today_date 0 0 3 0
test_store_clear_home_image 0 0 0 4
test_store_field_undo 0 1 2 5
test_store_headline 0 0 3 4
test_store_home_image 0 1 1 6
test_store_hours_numbering 0 1 1 5
test_store_hours_repeat 0 1 0 1
test_store_hours_report 0 1 1 0
test_store_hours_warning 0 0 3 5
test_store_intro 0 0 1 2
test_store_limits 0 0 2 6
test_store_notice 0 0 2 3
test_store_ops 0 0 2 7
test_store_phone 0 0 2 7
test_store_spacing_only 0 1 0 6
test_store_story 0 0 2 4
test_store_words 0 1 2 3
test_style_no_commerce 0 1 3 7
test_support_behaviour 0 0 0 0
test_support_doc 0 1 1 1
test_template_compat_chain_check 0 1 3 1
test_testkit_reply_shapes 0 0 0 2
test_text_limits 0 0 2 2
test_till_yes_durable 0 1 1 3
test_time_arg 0 1 3 3
test_tlds_freshness_check 0 0 2 4
test_tracked_private 0 0 0 4
test_transcript 0 1 3 5
test_transcript_attachment_shapes 0 0 0 6
test_transcript_export_blob 0 1 1 0
test_transcript_inbound_parity 0 0 2 7
test_transcript_latency_report 0 1 3 1
test_transcript_window_counts 0 0 0 2
test_trial_handover_doc 0 1 1 5
test_trial_summary 0 0 2 6
test_trial_summary_identifier_case 0 1 3 7
test_trial_summary_store_identity 0 0 0 0
test_trial_summary_timezone 0 1 1 1
test_undo 0 0 0 4
test_undo_cancel_phrases 0 1 1 3
test_undo_guest_warnings 0 0 3 7
test_undo_meeting_warning 0 0 2 4
test_undo_new_item 0 0 2 4
test_undo_product_restore 0 0 3 4
test_undo_skip_undo 0 1 0 5
test_undo_twice 0 1 3 5
test_units_template_parity 0 0 0 6
test_unknown_approval_code 0 0 1 6
test_verify_all_records 0 1 1 0
test_visit_hours 0 1 2 7
test_voice 0 1 0 7
test_voice_quote_markers 0 0 3 0
test_voice_time_edges 0 0 2 2
test_voice_visible_empty 0 1 3 3
test_weekday_date_mismatch 0 0 2 7
test_worker_busy 0 1 0 1
test_writer_lock_entry 0 0 1 2
test_yes_before_proposal 0 1 1 6
```

</details>
