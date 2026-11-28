# Hass source-to-test map under the CI shard rule

| Question | Result |
| --- | --- |
| R1. What does the planner reach? | 167 Hass source paths (165 Python, 2 CommonJS); 901 discovered test modules. A one-path PR was affected-only for 22 paths and full for 145. |
| R2. What has zero matching tests? | None. All 167 have a reference match; none forces full CI for being **unmapped**. |
| R3. What is missing on the test side? | No confirmed removed or renamed Hass module referenced by a test. One real absent path is named in a staged-release fixture. All 901 test modules have at least one Hass-source match under the shard rule; 39 have no Hass-source graph edge before the extra text matching. |
| R4. What is worth doing next? | If this needs repeating, add one offline reporting script. Do not add a test just to change the shard selection. |

Snapshot: `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, inspected 2026-11-21 with Python **3.12.3**. Unless otherwise noted, the counts below are from that offline replay. The planner, weights and workflow have no diff from the task baseline `1f8510907cb2989bb50391fde45d6211e4735879` (`git diff 1f8510907cb2989bb50391fde45d6211e4735879 origin/main -- hass/tests/ci_shards.py hass/tests/ci_weights.json .github/workflows/check.yml`). The named `reports/hass-npp/G-QUESTIONS.md` is not tracked at either snapshot (`git ls-tree -r --name-only <snapshot> -- reports/hass-npp/G-QUESTIONS.md`). This report uses the exclusions stated in the task and makes no decision about them.

## R1. Every source path and its matching tests

The inventory is all tracked planner-code files under `hass/` outside `hass/tests/`, including package initializers, `hass/skills/` and two `.cjs` files. It does not count templates, JSON, assets, or scripts outside `hass/` as Hass modules; the planner still builds the reference graph from tracked code across the repository. The test denominator is the planner's `all_modules()` discovery, not the count of every file in `hass/tests/` (`hass/tests/ci_shards.py:68-69,76-90,139-142,179-199`).

**Matches** means the real selector's path-hit set *before* full-tier decisions, not code coverage, one dedicated test per module, or a count of all tests that ultimately run. It includes the test's transitive reference closure and selector text matches. `test_…` names below are short names under `hass.tests`, sorted and limited to the first three. A dot-suffix or a basename shared by several files can match without a test targeting that source. Python comments and docstrings are omitted from the graph when parsing succeeds (`hass/tests/ci_shards.py:164-176,196-254,257-271,278-320`).

**One-path PR** is the result of `make_plan()` with only that path changed, using the unmodified policy and checked-in weights. `Full: rule` means `hass/__init__.py` or `hass/ops/` triggers the early full-suite rule; `Full: shared` means more than half of the test modules match; `Full: budget` means the affected set plus mandatory tests exceeds 480 planner seconds. `Affected` does not include unrelated files a real PR might change. Weights are not an elapsed-time measurement of this replay: `/seconds` in `hass/tests/ci_weights.json` has 659 current entries and zero stale names; the other 242 use the 3-second default. The planner uses weights for both packing and the affected budget (`.github/workflows/check.yml:16-25,97`; `hass/tests/ci_shards.py:53-64,93-120,334-372`).

| Hass source path | Matches | First three test modules | One-path PR |
| --- | ---: | --- | --- |
| `hass/__init__.py` | 849 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/acceptance.py` | 22 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_auto_policy` | Affected |
| `hass/answer_reader.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/audit.py` | 817 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/auto_policy.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/bridge.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/bridge_attach.py` | 20 | `test_attach`, `test_attachment_input_types`, `test_auto_policy` | Affected |
| `hass/bridge_photos.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/capabilities.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/chat/__init__.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/chat/commands.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/chat/core_pack.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/chat/reports_pack.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/chat/shared.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/chat/site_pack.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/chat/wording.py` | 817 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/claims.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/cloud_codex.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/cloud_codex_hermes.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/__init__.py` | 825 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/apply.py` | 821 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/approvals.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/bundle.py` | 818 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/cache.py` | 829 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/chat.py` | 841 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/checks.py` | 821 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/cli.py` | 24 | `test_auto_policy`, `test_ci_shards`, `test_cloud_codex` | Affected |
| `hass/clover/client.py` | 823 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/config.py` | 833 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/credential.py` | 821 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/drafts.py` | 818 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/dryrun.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/journal.py` | 830 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/links.py` | 817 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/mapper.py` | 821 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/pos.py` | 24 | `test_auto_policy`, `test_ci_shards`, `test_cloud_codex` | Affected |
| `hass/clover/qty_words.py` | 11 | `test_auto_policy`, `test_ci_shards`, `test_clover_count_phrases` | Affected |
| `hass/clover/reads.py` | 819 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/reports.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/sku.py` | 819 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/sync.py` | 817 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/clover/transport.py` | 827 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/content_model.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/conversation.py` | 817 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/corrlog.py` | 817 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/design_check.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/design_preview.py` | 17 | `test_auto_policy`, `test_ci_shards`, `test_design_check_launch` | Affected |
| `hass/editor.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/field_words.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/fixture_chat.py` | 373 | `test_acceptance_jpeg_segment_order`, `test_again`, `test_again_reverted` | Full: budget |
| `hass/health.py` | 822 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/hike_chat.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/hike_fetch.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/hike_lookup.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/host.py` | 831 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/house_style.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/inbox.py` | 818 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/install.py` | 840 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/interpret_check.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/interpreter_eval.py` | 89 | `test_audit`, `test_auto_policy`, `test_availability_own_day` | Full: budget |
| `hass/interpreter_local.py` | 820 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/interpreter_prompt.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/itemstd.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/label_eval.py` | 12 | `test_auto_policy`, `test_ci_shards`, `test_install_tools_checkout` | Affected |
| `hass/label_reader.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/live_policy.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/look_change.py` | 10 | `test_auto_policy`, `test_ci_shards`, `test_install_tools_checkout` | Affected |
| `hass/look_guard.py` | 10 | `test_auto_policy`, `test_ci_shards`, `test_install_tools_checkout` | Affected |
| `hass/maker_site.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/margins.py` | 820 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/media.py` | 817 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/memory.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/migration_check.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/morning_report.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/newitem.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/newitem_demo.py` | 11 | `test_auto_policy`, `test_ci_shards`, `test_install_tools_checkout` | Affected |
| `hass/newitem_preview.py` | 13 | `test_auto_policy`, `test_ci_shards`, `test_install_tools_checkout` | Affected |
| `hass/newitem_render.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/newitem_screenshot.cjs` | 5 | `test_newitem`, `test_newitem_claim_omission`, `test_newitem_name_grounding` | Affected |
| `hass/newitem_synthetic.py` | 30 | `test_auto_policy`, `test_ci_shards`, `test_house_render_seam` | Affected |
| `hass/nl_eval.py` | 79 | `test_audit`, `test_auto_policy`, `test_availability_own_day` | Full: budget |
| `hass/nl_prep.py` | 817 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/notice.py` | 823 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/__init__.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/copy.py` | 827 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/edits.py` | 821 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/evidence.py` | 817 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/identify.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/job.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/missing.py` | 863 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/picture.py` | 822 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/private_numbers.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/receipt.py` | 823 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/reply.py` | 834 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/research.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/research_hermes.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/stages.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/npp/validate.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/ops/__init__.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/ops/catalog.py` | 825 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/ops/club.py` | 817 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/ops/front.py` | 819 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/ops/hikes.py` | 818 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/ops/history.py` | 825 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/ops/home.py` | 826 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/ops/photos.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/ops/restock.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/ops/routes.py` | 817 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/ops/samples.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/ops/specials.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/ops/store.py` | 843 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: rule |
| `hass/owner_answers.py` | 818 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/photo_polish.py` | 819 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/photo_polish_hermes.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/preview.py` | 824 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/product_claims.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/publish_live.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/receiver.py` | 826 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/relay.py` | 822 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/relay_photos.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/release_journal.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/retention.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/runtime_release.py` | 9 | `test_auto_policy`, `test_ci_shards`, `test_install_tools_checkout` | Affected |
| `hass/sandbox.py` | 830 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/sandbox_editor.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/screenshot.cjs` | 817 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: budget |
| `hass/sitegen.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/__init__.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/acceptance_run.py` | 15 | `test_acceptance_jpeg_segment_order`, `test_auto_policy`, `test_ci_shards` | Affected |
| `hass/skills/answer_site.py` | 9 | `test_auto_policy`, `test_ci_shards`, `test_install_tools_checkout` | Affected |
| `hass/skills/backlog.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/dispatch.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/faq.py` | 9 | `test_auto_policy`, `test_ci_shards`, `test_install_tools_checkout` | Affected |
| `hass/skills/front.py` | 819 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/hikes.py` | 818 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/intake_simple.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/item_add.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/item_intake.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/item_picture.py` | 16 | `test_auto_policy`, `test_ci_shards`, `test_install_tools_checkout` | Affected |
| `hass/skills/items.py` | 825 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/kinds.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/makers.py` | 818 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/model.py` | 828 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/openreq.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/pages.py` | 825 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/photo_trial.py` | 11 | `test_auto_policy`, `test_ci_shards`, `test_install_tools_checkout` | Affected |
| `hass/skills/prompt.py` | 823 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/reports.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/restock.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/router.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/scaffold.py` | 9 | `test_auto_policy`, `test_ci_shards`, `test_install_tools_checkout` | Affected |
| `hass/skills/shop.py` | 823 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/social.py` | 817 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/specials.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/stock.py` | 827 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/skills/testkit.py` | 65 | `test_acceptance_jpeg_segment_order`, `test_auto_policy`, `test_availability_own_day` | Full: budget |
| `hass/social_draft.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/social_message.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/specials.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/stagelog.py` | 823 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/statebackup.py` | 104 | `test_acceptance_runner`, `test_auto_policy`, `test_ci_shards` | Affected |
| `hass/stock_site.py` | 815 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/template_compat.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/tlds.py` | 816 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/transcript.py` | 819 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |
| `hass/trial_summary.py` | 14 | `test_auto_policy`, `test_ci_shards`, `test_install_tools_checkout` | Affected |
| `hass/voice.py` | 822 | `test_acceptance_jpeg_segment_order`, `test_acceptance_runner`, `test_additive_state` | Full: shared |

## R2. Modules with zero matching tests

| Directory | Paths checked | Zero matches | Paths |
| --- | ---: | ---: | --- |
| `hass/` | 80 | 0 | None |
| `hass/chat/` | 7 | 0 | None |
| `hass/clover/` | 23 | 0 | None |
| `hass/npp/` | 15 | 0 | None |
| `hass/ops/` | 13 | 0 | None |
| `hass/skills/` | 29 | 0 | None |

There were **no** `unmapped` fallbacks among these code paths. The 145 full plans were 14 by an early rule, 126 by the shared-library threshold and 5 by the budget (R1 replay; `hass/tests/ci_shards.py:288-315,354-367`). Four paths had no reference-graph edge from any test closure but still matched in the selector's additional text scan: `hass/ops/club.py`, `hass/ops/samples.py`, `hass/skills/answer_site.py`, `hass/skills/faq.py`. Neither the zero-unmapped result nor those four paths establish a behavior-coverage gap (R1 replay and `hass/tests/ci_shards.py:244-254,257-271,292-305`).

## R3. Missing names and tests without a source match

**Missing names.** No missing explicit `import hass.…` or missing `from hass.…` base was found in the 901 test modules. A static scan compared absolute and relative imports, package members, and literal dotted names and code filenames with the tracked tree. For candidates that might actually name a former path, `git log --full-history --format= --diff-filter=D --name-only --no-renames origin/main -- hass` returned no deleted Hass paths in this public main history on 2026-11-21. That does not establish what existed on unpublished branches or at runtime. Package members such as `hass.ops.load_registry`, `hass.skills.skill_lint` and `hass.npp.stages_for` are real symbols, not missing submodules (`hass/ops/__init__.py:107`, `hass/skills/__init__.py:34`, `hass/npp/__init__.py:29`).

| Test and anchor | Absent name on main | Finding |
| --- | --- | --- |
| `hass/tests/test_npp_preflight.py:13-17,25-45` | `hass/tests/npp/run_npp.py` | Real path named by the staged-release preflight, but created as fixture content by this test. The maintain guide explicitly conditions replay on the runner landing (`scripts/hass/npp_preflight.py:32`; `docs/hass/skills/hass-npp-maintain/SKILL.md:23-26`). Not evidence of a removed subject or broken import. |
| `hass/tests/test_ledger_rf1120.py:242-250` | `hass/tests/test_hike_create_repeat.py` | Deliberate absence assertion for a superseded unit, not a missing test dependency. |
| `hass/tests/test_cloud_codex.py:124-127` | `hass.cloud` | Logger name in `assertLogs`, not a module request. |
| `hass/tests/test_ci_shards.py:27-45`; `hass/tests/test_capabilities.py:83-91` | e.g. `hass/leaf.py`, `hass.skills.pack_probe` | Synthetic graph paths and a synthetic module installed by the test, not deleted production sources. |

Confirm the first two absences with `git ls-tree -r --name-only origin/main -- hass/tests/npp/run_npp.py hass/tests/test_hike_create_repeat.py` (no output on 2026-11-21). The literal scan is not runtime import resolution: computed names, external release files and non-literal dynamic loads are not certified by it. The test filename alone is not evidence of a renamed or deleted subject.

**Reverse map.** The union of the R1 hit sets covers all **901** test modules, so the list with no Hass-source match under the complete shard matching rule is empty. The reference graph alone (without the selector's extra text search) leaves **39** test modules without a Hass source in their closure. These are listed below; this is not a list of tests to remove. Graph edges to code outside Hass account for 38 of the 39 when tracked non-test code across the repository is allowed (`hass/tests/ci_shards.py:179-241,244-254,257-305`; dated replay below).

| Test module | Test module | Test module |
| --- | --- | --- |
| `test_alert_log_window` | `test_audit_log_days` | `test_drill_export_compare` |
| `test_install_allowlist_diff` | `test_install_backup_receipt` | `test_install_ci_receipt` |
| `test_install_citation_drift` | `test_install_digest_ledger` | `test_install_entry_gate` |
| `test_install_preflight_verdict` | `test_install_private_files` | `test_install_rehearsal` |
| `test_install_release_lineage` | `test_install_revert_scan` | `test_install_rollback_proof` |
| `test_install_service_restart` | `test_install_skill_parity` | `test_install_skill_shadow` |
| `test_install_stage_file` | `test_install_switch_projection` | `test_install_tools_checkout` |
| `test_install_window_clock` | `test_interpreter_audit_report` | `test_live_selftest_check_ids` |
| `test_mac_kit` | `test_pilot_card_png` | `test_pilot_change_record` |
| `test_pilot_content_diff` | `test_pilot_receipt_new` | `test_pilot_reply_match` |
| `test_pilot_scenario_check` | `test_release_pending_recovery` | `test_retention_report_diff` |
| `test_screenshot_refs` | `test_selftest_summary_check` | `test_style_no_commerce` |
| `test_transcript_latency_report` | `test_transcript_window_counts` | `test_units_template_parity` |

The one test without any non-test **code** node in its closure, `test_style_no_commerce`, reads current site CSS and HTML, rather than Hass Python (`hass/tests/test_style_no_commerce.py:6-28`; `AGENTS.md:3-5`). Single changes to `storefront-mockup/style.css`, `storefront-mockup/index.html` or `storefront-mockup/hike/index.html` each selected it in a full plan on 2026-11-21 (budget fallback). Also, **721** tests did not appear in any of the 22 affected-only Hass-source plans, even counting the always-added smoke and privacy tests. That is not an orphan count: the other 145 Hass-source plans run all 901 modules (`hass/tests/ci_shards.py:354-372`).

## R4. Ranked follow-up

1. **Make repeat audits cheap, if another snapshot is needed.** One buildable unit: a read-only `scripts/hass/test_module_map_report.py` (estimate: 75–100 minutes). Reuse the planner functions and emit sorted path hits, graph-only gaps, and full-tier reasons as distinct fields. At this pinned snapshot, independently verify the 167-row inventory, the zero-unmapped result and the `acceptance.py` / `audit.py` / `ops/catalog.py` affected / shared / mandatory-full controls from the replay. Do not install it in CI or edit the planner, weights, or tests. This is a proposal, not a change in this report.
2. **Keep the staged-release runner absence visible.** The preflight fixture and conditional maintain-guide instruction already explain it (R3); do not infer a restore or removal task from the public tree.
3. **Do not add tests purely to avoid a full run.** R2 found no source path that such a test could move out of the unmapped fallback; graph-only gaps need evidence of a distinct missing behavior before spending test time. No CI timing savings were measured.

## Reproduce the planner replay

Run `python3.12 -B audit_map.py avocado-shack` from scratch, pointing the script at a clean checkout of the pinned snapshot. The following is the table/reverse-map core; save it as a file in scratch. Only the planner module is imported. `make_plan()` is used instead of the CLI `plan`, which would import the test suites to count cases (`hass/tests/ci_shards.py:329-331,390-412`). The singleton path is supplied in memory and the planner's graph is reused. For raw counts only, the diagnostic call bypasses the early force-full constants and the shared cutoff in the isolated process, then restores them; it changes no matcher and no checkout file.

```python
import contextlib
import importlib.util
import io
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location('ci', root / 'hass/tests/ci_shards.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)
files = ci.tracked()
texts, edges = ci.build_graph(files=files)
mods = ci.all_modules()
weights = ci.load_weights()
paths = sorted(p for p in files if p.startswith('hass/') and
               not p.startswith('hass/tests/') and p.endswith(ci.CODE_SUFFIXES))
assert set(paths) <= texts.keys()
policy = ci.FULL_PREFIXES, ci.FULL_FILES, ci.SHARED_FRACTION
ci.build_graph = lambda: (texts, edges)
raw_union, quick_union = set(), set()
print(sys.version.split()[0], len(paths), len(mods), len(weights))
for p in paths:
    ci.changed_paths = lambda base: [p]
    with contextlib.redirect_stdout(io.StringIO()):
        plan = ci.make_plan('pull_request', 'origin/main', ci.DEFAULT_SHARDS, weights, mods)
    if plan['tier'] == 'affected':
        quick_union.update(plan['shards'][0])
    ci.FULL_PREFIXES, ci.FULL_FILES, ci.SHARED_FRACTION = (), set(), 1.0
    raw, reason = ci.select([p], mods, texts, edges)
    ci.FULL_PREFIXES, ci.FULL_FILES, ci.SHARED_FRACTION = policy
    assert raw is not None or 'unmapped' in reason
    hit = sorted(raw or ())
    raw_union.update(hit)
    print(p, len(hit), ', '.join(hit[:3]), plan['tier'], plan['reason'])
print('No source hit:', sorted(set(mods) - raw_union))
print('Absent from every affected-only plan:', len(set(mods) - quick_union))
non_test_code = {p for p in texts if not p.startswith(('hass/tests/', 'tests/'))}
closures = ci.closures([ci.test_path(t) for t in mods], edges)
for label, scope in [('Hass', set(paths)), ('repo code', non_test_code)]:
    print(label, 'no graph edge:', [t for t in mods if not scope & closures[ci.test_path(t)]])
print('No graph edge from any test:', sorted(set(paths) - set().union(*closures.values())))
```

For the site controls, repeat `make_plan()` with each site path above instead of `p`. As a scope check, a singleton change to this report's path also gave `full` (budget; planner weight 3,672 seconds), despite the report being the only change. These are planning results, not hosted CI, unittest runs, or live checks.
