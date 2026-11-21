# Hass script inventory

| Baseline kind (R1–R3) | Scripts | Named by tests | Named by documents | Named by neither |
|---|---:|---:|---:|---:|
| Audit or report tool | 41 | 41 | 0 | 0 |
| Helper | 6 | 6 | 1 | 0 |
| Install step | 32 | 32 | 2 | 0 |
| Self-test or rehearsal | 6 | 6 | 4 | 0 |
| One-off | 0 | 0 | 0 | 0 |
| **Total** | 85 | 85 | 7 | 0 |

## How to reproduce

The first SHA below fixes the requested cohort. All line anchors refer to `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, the fetched `origin/main` at the start of this audit. The baseline-to-main diff added three script/test pairs and changed none of the original scripts, tests, or documents. They are shown separately below so the 85-script count remains comparable. The install kit and the G questions were not tracked at this head; no off-repo copy, pending PR, historical commerce prototype, or storefront archive was used.

```sh
git ls-tree -r --name-only 1f8510907cb2989bb50391fde45d6211e4735879 scripts/hass
git ls-tree -r --name-only 37feae1dc5efa6968f90d17a1eda6daed29afd4a scripts/hass reports/hass-npp
git diff --name-status 1f8510907cb2989bb50391fde45d6211e4735879 37feae1dc5efa6968f90d17a1eda6daed29afd4a
```

For each row, substitute its path in `git show 37feae1dc5efa6968f90d17a1eda6daed29afd4a:scripts/hass/install_quiescence.py | nl -ba` (or use `wc -l` for the physical line count). R1 quotes the first line of each Python module docstring; `none` for shell scripts means no Python-style docstring, and the stated purpose comes from the opening comment. Kind is an editorial label, not an assertion about deployment. “Install step” includes install checks/receipts, not just installers. A reusable check for a drill or pilot is not called a one-off just because the event is named.

For R2, search by filename and also by module stem. The example below finds filename mentions and extensionless mentions, such as the `from scripts.hass import install_quiescence` at `hass/tests/test_install_quiescence.py:10`. For other rows replace the stem and suffix as appropriate; discard coincidental identifiers (e.g., the `npp_jobs` database table is not the `npp_jobs.py` script). Scan the named Hass docs and reports plus other tracked Markdown outside the two historical roots. Compress multiple lines in one document as `path:line,line`. `none` means no name found in the scanned scope, not that the script has no caller anywhere. A test naming a script can be an import, execution, or source check; it does not prove coverage of every mode.

```sh
git grep -n -w -e install_quiescence 37feae1dc5efa6968f90d17a1eda6daed29afd4a -- ':(glob)hass/tests/**/test_*.py' '*.md' ':(exclude)commerce/**' ':(exclude)storefront-mockup/archive/**'
git show 37feae1dc5efa6968f90d17a1eda6daed29afd4a:hass/tests/ci_weights.json
```

Found 82 distinct naming test modules; 3 have keys in `/seconds` (compare the R2 test basenames without `.py`). The CI weights describe shard balancing, not test admission or proof that a test passed (`hass/tests/ci_weights.json:3`, `/seconds`). The audit read tracked source only; it did not run the scripts, tests, or a live service.

## R1 and R2 — Script inventory

| Script path and source line | Lines | Kind | First docstring line (or purpose from shell comment) | Naming test modules | Naming documents |
|---|---:|---|---|---|---|
| `scripts/hass/alert_log_window.py:2` | 97 | Audit or report tool | “Check a saved alert log for Hass health alerts in an attended window.” | `hass/tests/test_alert_log_window.py:11` | none |
| `scripts/hass/audit_log_days.py:2` | 109 | Audit or report tool | “Count audit day files by UTC date without opening or deleting them.” | `hass/tests/test_audit_log_days.py:16` | none |
| `scripts/hass/catalog_file_check.py:2` | 125 | Audit or report tool | “Check a copied catalog against validated content without writing either input.” | `hass/tests/test_catalog_file_check.py:14` | none |
| `scripts/hass/clover_write_readiness.py:1` | 160 | Audit or report tool | “Check Clover write readiness from private, quiescent local state files only.” | `hass/tests/test_clover_write_readiness.py:21` | none |
| `scripts/hass/demo_rehearsal.py:2` | 474 | Self-test or rehearsal | “HASS-DEMO-REHEARSAL-1 (A4): the owner demo script as a reproducible run.” | `hass/tests/test_demo_rehearsal.py:3` | none |
| `scripts/hass/description_style_audit.py:2` | 92 | Audit or report tool | “Audit active product descriptions from a content copy without printing text.” | `hass/tests/test_description_style_audit.py:17` | none |
| `scripts/hass/drill_export_compare.py:2` | 80 | Audit or report tool | “Compare two transcript JSONL exports without displaying their contents.” | `hass/tests/test_drill_export_compare.py:13` | none |
| `scripts/hass/help_text_voice_check.py:2` | 53 | Audit or report tool | “Report the size and voice-rule count of Hass's registry-generated help.” | `hass/tests/test_help_text_voice_check.py:15` | none |
| `scripts/hass/install_acceptance_receipt.py:2` | 131 | Install step | “Check a saved Hass acceptance receipt without running acceptance.” | `hass/tests/test_install_acceptance_receipt.py:11` | none |
| `scripts/hass/install_allowlist_diff.py:2` | 124 | Install step | “Check that two local commits have the same maker allowlist.” | `hass/tests/test_install_allowlist_diff.py:14` | none |
| `scripts/hass/install_backup_receipt.py:2` | 110 | Install step | “Verify a completed editor-config backup offline without modifying either file.” | `hass/tests/test_install_backup_receipt.py:16` | none |
| `scripts/hass/install_ci_receipt.py:2` | 121 | Install step | “Judge a saved check-runs capture against a release SHA, offline.” | `hass/tests/test_install_ci_receipt.py:12` | none |
| `scripts/hass/install_citation_drift.py:2` | 99 | Install step | “Check install-kit citation spans against a local commit, not the checkout files.” | `hass/tests/test_install_citation_drift.py:11` | none |
| `scripts/hass/install_config_attributes.py:2` | 96 | Install step | “Check install-kit config and backup attributes without opening either file.” | `hass/tests/test_install_config_attributes.py:11` | none |
| `scripts/hass/install_digest_ledger.py:2` | 181 | Install step | “Record or check a config digest in an offline, owner-only ledger.” | `hass/tests/test_install_digest_ledger.py:16` | none |
| `scripts/hass/install_entry_gate.py:2` | 156 | Install step | “Find install entry-gate merge SHAs in a local Git checkout.” | `hass/tests/test_install_entry_gate.py:15` | none |
| `scripts/hass/install_launchagent.py:2` | 110 | Install step | “Check two offline LaunchAgent plist copies and the configured forwarder path.” | `hass/tests/test_install_launchagent.py:15` | none |
| `scripts/hass/install_mac_parity.py:2` | 92 | Install step | “Compare a supplied Mac forwarder copy with a selected Git commit, offline.” | `hass/tests/test_install_mac_parity.py:12` | none |
| `scripts/hass/install_pending_work.py:2` | 72 | Install step | “Count pending work in offline Hass stores before a switch or resume.” | `hass/tests/test_install_pending_work.py:15` | none |
| `scripts/hass/install_preflight_verdict.py:2` | 148 | Install step | “Evaluate saved NPP preflight stdout and its separately recorded exit status.” | `hass/tests/test_install_preflight_verdict.py:10` | none |
| `scripts/hass/install_private_files.py:2` | 93 | Install step | “Check private install paths without opening receipts or changing permissions.” | `hass/tests/test_install_private_files.py:14` | none |
| `scripts/hass/install_quiescence.py:2` | 76 | Install step | “Check one saved snapshot, never the current state of a service.” | `hass/tests/test_install_quiescence.py:10` | none |
| `scripts/hass/install_rehearsal.py:2` | 114 | Self-test or rehearsal | “Rehearse the NPP switch and rollback on a disposable synthetic config.” | `hass/tests/test_install_rehearsal.py:17` | none |
| `scripts/hass/install_release_lineage.py:2` | 139 | Install step | “Check release ancestry and tree paths using only a local Git checkout.” | `hass/tests/test_install_release_lineage.py:12` | none |
| `scripts/hass/install_revert_scan.py:2` | 155 | Install step | “Check a selected release for explicit reverts and restored pre-merge files.” | `hass/tests/test_install_revert_scan.py:13` | none |
| `scripts/hass/install_rollback_proof.py:2` | 88 | Install step | “Check rollback config bytes without changing files or service state.” | `hass/tests/test_install_rollback_proof.py:13` | none |
| `scripts/hass/install_runtime_readback.py:2` | 136 | Install step | “Check the consistency of one saved, post-release Hass capture (JSON on stdin).” | `hass/tests/test_install_runtime_readback.py:9` | none |
| `scripts/hass/install_service_restart.py:2` | 119 | Install step | “Check two saved service captures for a fresh start and no intervening restarts.” | `hass/tests/test_install_service_restart.py:11` | none |
| `scripts/hass/install_skill_parity.py:2` | 133 | Install step | “Compare operator-resolved skill files with a selected local Git commit.” | `hass/tests/test_install_skill_parity.py:11` | none |
| `scripts/hass/install_skill_restore_proof.py:2` | 181 | Install step | “Read-only proof against an operator-approved roster and prior-state manifest.” | `hass/tests/test_install_skill_restore_proof.py:13` | none |
| `scripts/hass/install_skill_shadow.py:2` | 181 | Install step | “Check skill precedence in operator-listed roots, without modifying them.” | `hass/tests/test_install_skill_shadow.py:14` | none |
| `scripts/hass/install_stage_file.py:2` | 98 | Install step | “Check an adjacent config stage without changing either file.” | `hass/tests/test_install_stage_file.py:15` | none |
| `scripts/hass/install_store_schema.py:2` | 143 | Install step | “Compare stable, checkpointed store copies with this checkout's schema.” | `hass/tests/test_install_store_schema.py:22` | none |
| `scripts/hass/install_switch_projection.py:2` | 103 | Install step | “Project the editor's three NPP switches for the flat preflight input.” | `hass/tests/test_install_switch_projection.py:12` | none |
| `scripts/hass/install_switch_readback.py:2` | 122 | Install step | “Check a candidate or installed JSON config against its pre-switch backup.” | `hass/tests/test_install_switch_readback.py:12` | none |
| `scripts/hass/install_tools_checkout.py:2` | 111 | Install step | “Check the reviewed tools checkout offline (origin is a local config check).” | `hass/tests/test_install_tools_checkout.py:13` | none |
| `scripts/hass/install_window_clock.py:2` | 129 | Install step | “Check an attended install JSON Lines log against the kit's time budgets.” | `hass/tests/test_install_window_clock.py:12` | none |
| `scripts/hass/interpreter_audit_report.py:2` | 191 | Audit or report tool | “Summarize interpreter calls in a half-open window from a saved SQLite store.” | `hass/tests/test_interpreter_audit_report.py:17` | none |
| `scripts/hass/label_case_coverage.py:2` | 72 | Audit or report tool | “Report aggregate coverage of the offline label-reader case set.” | `hass/tests/test_label_case_coverage.py:13` | none |
| `scripts/hass/live_selftest.sh:2` | 215 | Self-test or rehearsal | none — Run synthetic and (unless requested otherwise) operational Hass checks. | `hass/tests/test_live_selftest.py:1` | `docs/hass/OPERATIONS.md:123`; `reports/hass/HASS-LIVE-AUDIT-1.md:77,131,133`; `reports/hass/STORE-TEST-1.md:201` |
| `scripts/hass/live_selftest_model.py:2` | 52 | Self-test or rehearsal | “HASS-LIVE-AUDIT-1: the live-model draft round trip of scripts/hass/live_selftest.sh (operator only, never in CI).” | `hass/tests/test_live_selftest.py:2` | `reports/hass/HASS-LIVE-AUDIT-1.md:72,134` |
| `scripts/hass/live_selftest_parse.py:2` | 84 | Self-test or rehearsal | “HASS-LIVE-AUDIT-1: validate the JSON that scripts/hass/live_selftest.sh gets from hass/health.py and hass/inbox.py.” | `hass/tests/test_live_selftest.py:18`; `hass/tests/test_live_selftest_check_ids.py:1` | `reports/hass/HASS-LIVE-AUDIT-1.md:134,142` |
| `scripts/hass/live_selftest_synth.py:2` | 195 | Self-test or rehearsal | “HASS-LIVE-AUDIT-1: the synthetic half of scripts/hass/live_selftest.sh.” | `hass/tests/test_live_selftest.py:1` | `reports/hass/HASS-LIVE-AUDIT-1.md:134` |
| `scripts/hass/mac_install.sh:2` | 153 | Install step | none — Install BlueBubbles Server on the Mac; includes plan and dry-run modes. | `hass/tests/test_mac_kit.py:10` | `docs/hass/BRIDGE_WIRING.md:62`; `docs/hass/MAC_MINI_FINAL_STEPS.md:4,21,35,40,42` |
| `scripts/hass/mac_setup_check.sh:2` | 132 | Install step | none — Check the Mac setup without changing it or sending anything. | `hass/tests/test_mac_kit.py:9` | `docs/hass/BRIDGE_WIRING.md:61`; `docs/hass/MAC_MINI_FINAL_STEPS.md:4,21,35,52` |
| `scripts/hass/nl_corpus_ops_check.py:2` | 93 | Audit or report tool | “Check expected NL corpus ops against the editor registry offline.” | `hass/tests/test_nl_corpus_ops_check.py:15` | none |
| `scripts/hass/nl_intent_coverage.py:2` | 76 | Audit or report tool | “Report offline interpreter corpus coverage without printing case text.” | `hass/tests/test_nl_intent_coverage.py:16` | none |
| `scripts/hass/npp_case_new.py:2` | 90 | Helper | “Start an offline NPP regression case; replace all TODOs before committing it.” | `hass/tests/test_npp_case_new.py:14` | none |
| `scripts/hass/npp_chat_page.py:2` | 337 | Helper | “Render a Hass JSONL export and an attachment copy as a private offline page.” | `hass/tests/test_npp_chat_page.py:20` | none |
| `scripts/hass/npp_edit_eval.py:2` | 149 | Audit or report tool | “Score S10 mapper recordings offline, or collect one on the attended private host.” | `hass/tests/test_npp_edit_eval.py:14` | none |
| `scripts/hass/npp_findings.py:2` | 215 | Helper | “Maintain the private NPP findings ledger in an operator-owned directory outside Git.” | `hass/tests/test_npp_findings.py:15` | none |
| `scripts/hass/npp_jobs.py:2` | 111 | Audit or report tool | “List job metadata from a standalone copy of the Hass state database.” | `hass/tests/test_npp_jobs.py:19` | none |
| `scripts/hass/npp_limits.py:2` | 167 | Helper | “HASS-NPP-A: derive the gallery field limits from the measured TSV, and keep the asset pins current.” | `hass/tests/test_npp_assets.py:647` | `docs/hass/skills/hass-npp-maintain/SKILL.md:21,22`; `hass/npp/assets/README.md:19,20`; `hass/npp/assets/hass-gallery-style/SKILL.md:124` |
| `scripts/hass/npp_preflight.py:2` | 237 | Install step | “Read-only Hass NPP install preflight. READY is not install authority.” | `hass/tests/test_npp_preflight.py:1` | none |
| `scripts/hass/npp_review_export.py:2` | 221 | Helper | “Project a private Hass transcript export and NPP receipts to local review JSONL.” | `hass/tests/test_npp_review_export.py:11` | none |
| `scripts/hass/npp_transcript_check.py:2` | 133 | Audit or report tool | “Check a checkpointed state DB copy against a private transcript JSONL export.” | `hass/tests/test_npp_transcript_check.py:16` | none |
| `scripts/hass/pilot_approvals.py:2` | 102 | Audit or report tool | “Report the stored approval binding for one pilot change (read only).” | `hass/tests/test_pilot_approvals.py:18` | none |
| `scripts/hass/pilot_card_png.py:2` | 90 | Audit or report tool | “Check a pilot card's PNG structure and report its SHA-256 without decoding pixels.” | `hass/tests/test_pilot_card_png.py:16` | none |
| `scripts/hass/pilot_change_record.py:2` | 89 | Audit or report tool | “Read one stored pilot install outcome without opening the site.” | `hass/tests/test_pilot_change_record.py:14` | none |
| `scripts/hass/pilot_content_diff.py:2` | 133 | Audit or report tool | “Report public catalog changes between two local writer commits.” | `hass/tests/test_pilot_content_diff.py:14` | none |
| `scripts/hass/pilot_inbound.py:2` | 84 | Audit or report tool | “List inbound metadata as JSON lines, followed by counts. Never reads payloads.” | `hass/tests/test_pilot_inbound.py:19` | none |
| `scripts/hass/pilot_photo_receipts.py:2` | 120 | Audit or report tool | “Report stored photo digests and receipt completeness, without reading photo bytes.” | `hass/tests/test_pilot_photo_receipts.py:16` | none |
| `scripts/hass/pilot_private_scan.py:2` | 127 | Audit or report tool | “Check captured pilot replies and card HTML for listed private numbers.” | `hass/tests/test_pilot_private_scan.py:13` | none |
| `scripts/hass/pilot_receipt_new.py:2` | 114 | Helper | “Create a blank pilot receipt in a private directory.” | `hass/tests/test_pilot_receipt_new.py:19` | none |
| `scripts/hass/pilot_reply_match.py:2` | 114 | Audit or report tool | “Classify one captured NPP reply offline; a text match is not live verification.” | `hass/tests/test_pilot_reply_match.py:15` | none |
| `scripts/hass/pilot_scenario_check.py:2` | 177 | Audit or report tool | “Check the listing-specific expectations in one offline pilot receipt.” | `hass/tests/test_pilot_scenario_check.py:14` | none |
| `scripts/hass/pilot_sender_check.py:2` | 99 | Audit or report tool | “Check which chats sent messages in a pilot window using a read-only store.” | `hass/tests/test_pilot_sender_check.py:16` | none |
| `scripts/hass/producers_file_check.py:2` | 121 | Audit or report tool | “Check a copied producers file against validated content without changing either.” | `hass/tests/test_producers_file_check.py:14` | none |
| `scripts/hass/publish_sources_check.py:2` | 86 | Audit or report tool | “List missing or symlinked static publish sources without publishing.” | `hass/tests/test_publish_sources_check.py:16` | none |
| `scripts/hass/release_pending_recovery.py:2` | 153 | Audit or report tool | “Report pending Hass release metadata offline. Never attempt recovery.” | `hass/tests/test_release_pending_recovery.py:14` | none |
| `scripts/hass/rendered_a11y_check.py:2` | 150 | Audit or report tool | “Render a content copy in memory and report basic HTML accessibility counts.” | `hass/tests/test_rendered_a11y_check.py:17` | none |
| `scripts/hass/rendered_anchor_check.py:2` | 113 | Audit or report tool | “Check fragment targets in an offline render without writing site files.” | `hass/tests/test_rendered_anchor_check.py:18` | none |
| `scripts/hass/rendered_jsonld_check.py:2` | 126 | Audit or report tool | “Check the home page's rendered store JSON-LD without writing site files.” | `hass/tests/test_rendered_jsonld_check.py:16` | none |
| `scripts/hass/rendered_link_check.py:2` | 138 | Audit or report tool | “Check internal href and src targets in offline renders of a Hass content copy.” | `hass/tests/test_rendered_link_check.py:16` | none |
| `scripts/hass/retention_report_diff.py:2` | 113 | Audit or report tool | “Compare two saved Hass retention reports without opening live state.” | `hass/tests/test_retention_report_diff.py:11` | none |
| `scripts/hass/retention_uncounted_tables.py:2` | 107 | Audit or report tool | “List row counts for tables omitted by the Hass retention report.” | `hass/tests/test_retention_uncounted_tables.py:17` | none |
| `scripts/hass/route_idea_dates.py:2` | 87 | Audit or report tool | “Check route ideas in a content copy for calendar-day wording.” | `hass/tests/test_route_idea_dates.py:16` | none |
| `scripts/hass/screenshot_refs.py:2` | 140 | Audit or report tool | “Count draft screenshot references against a stable offline state directory.” | `hass/tests/test_screenshot_refs.py:18` | none |
| `scripts/hass/selftest_summary_check.py:2` | 79 | Audit or report tool | “Check the counts in saved live self-test stdout without printing details.” | `hass/tests/test_selftest_summary_check.py:10` | none |
| `scripts/hass/store_hours_report.py:2` | 70 | Audit or report tool | “Report whether copied store hours read for open-now status and JSON-LD.” | `hass/tests/test_store_hours_report.py:14` | none |
| `scripts/hass/template_compat_chain_check.py:2` | 100 | Audit or report tool | “Check that recorded edits rebuild earlier templates in a checkout copy.” | `hass/tests/test_template_compat_chain_check.py:17` | none |
| `scripts/hass/transcript_inbound_parity.py:2` | 150 | Audit or report tool | “Compare inbound coverage in stable offline SQLite snapshots, as counts only.” | `hass/tests/test_transcript_inbound_parity.py:15` | none |
| `scripts/hass/transcript_latency_report.py:2` | 168 | Audit or report tool | “Report inbound transcript latency for a half-open time window, offline.” | `hass/tests/test_transcript_latency_report.py:16` | none |
| `scripts/hass/transcript_window_counts.py:2` | 112 | Audit or report tool | “Count events in a stable transcript snapshot over a half-open time window.” | `hass/tests/test_transcript_window_counts.py:16` | none |
| `scripts/hass/units_template_parity.py:2` | 118 | Install step | “Compare installed Hass service and timer files with a selected Git commit.” | `hass/tests/test_units_template_parity.py:13` | none |

### Three additions since the task baseline (not in the summary counts)

| Script path and source line | Lines | Kind | First docstring line (or purpose from shell comment) | Naming test modules | Naming documents |
|---|---:|---|---|---|---|
| `scripts/hass/info_pages_check.py:2` | 102 | Audit or report tool | “Check the visibility, robots tags, and links of four offline-rendered info pages.” | `hass/tests/test_info_pages_check.py:13` | none |
| `scripts/hass/itemstd_gap_diff.py:2` | 79 | Audit or report tool | “Compare new item-standard gaps between two saved content directories.” | `hass/tests/test_itemstd_gap_diff.py:11` | none |
| `scripts/hass/tlds_freshness_check.py:2` | 115 | Audit or report tool | “Compare the pinned Hass TLD set with a saved IANA list (offline).” | `hass/tests/test_tlds_freshness_check.py:14` | none |

## R3 — Orphan candidates and wording drift

- **Orphan candidates: none.** Every baseline script has at least one naming test module (R2). Missing operator docs are a discoverability gap, not evidence of disuse. In particular, the install checks without doc hits are not validated as installed or retired by this scan; the tracked tree does not contain the install kit.
- **Wrong CLI named in a docstring:** `scripts/hass/live_selftest_synth.py:12–13` calls the separate model step “the live model round trip is a separate step of the shell script (hass/interpreter_eval.py --live on synthetic cases).” The shell actually runs `live_selftest_model.py` with `--url` and `--model` (`scripts/hass/live_selftest.sh:161–166`). That wrapper calls the evaluator's Python functions (`scripts/hass/live_selftest_model.py:36–41`), not its `--live` CLI. This is a documentation mismatch, not a second or missing model step.
- **Usage omissions, not contradictory flags:** The two usage lines in `scripts/hass/demo_rehearsal.py:4–5` omit `--skills-mode` (declared at `scripts/hass/demo_rehearsal.py:437`; applied at :444). The documented `--live` requirements agree with :440–442. `release_pending_recovery.py` is not a recovery command: its docstring explicitly says “Never attempt recovery” (`scripts/hass/release_pending_recovery.py:2`), and its CLI takes `--runtime` and `--receipts` (:137–138). No other direct filename or argument contradiction was found in the module headers and entry-point argument declarations reviewed.

## R4 — Ranked follow-up

1. **Make the install checks findable.** Naming tests exist for all 32 install-step entries, but 30 have no tracked Markdown reference (R1–R2), and the install-kit path is absent. Document these checks before adding more standalone audit tools.
2. **Clarify the self-test handoff when updating operator docs.** R3 identifies the wrong entry point in the synthetic self-test docstring; the shell already calls the correct wrapper. Do not edit scripts in this unit.
3. **Do not start an orphan cleanup.** R2 has no double-negative rows; it cannot establish what is currently installed or used.

**One proposed unit (estimate: 60–90 minutes):** Add a doc-only index for the install-step rows that have no tracked document reference. For each, link the script and one naming test and state what input it checks and what it does *not* prove, from the pinned source. Where a result depends on a saved receipt, identify it as saved evidence, not live verification. Acceptance: every included link resolves, every install-step row without a doc hit has exactly one index entry, and the proposed diff changes only the new index. No script edit, rename, removal, operational instructions, or new install authority.
