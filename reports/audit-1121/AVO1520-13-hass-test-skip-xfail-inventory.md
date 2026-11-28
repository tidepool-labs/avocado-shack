# Hass test skip and expected-failure inventory

| Check | Finding at the audited main |
| --- | --- |
| R1 · Explicit uses | 115 live source sites: 89 `skipUnless`, 3 `skipIf`, 21 `skipTest`, 1 raised `SkipTest`, 1 `expectedFailure` factory that marks 4 tests. Another 5 sites are inside synthetic runner fixtures. No pytest skip/xfail use found. |
| R2 · CI reachability | Two dispatcher guards cite work already present. Browser, Node and Pillow provision and the Ubuntu platform make many other skips inactive in a normally provisioned job. Shallow checkout has the opposite effect on history checks. |
| R3 · Silent exits and assertions | No direct return found in a test body. One file has no direct assertion-like check in any test body; all five tests delegate to shared assertion helpers. |
| R4 · Priority | First make missing NPP stage coverage visible by test ID; leave test behavior and release policy unchanged. |

Audited `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a` on 2026-11-21. The public clone matched the brief's baseline exactly (`git rev-parse origin/main`). Scope is tracked `hass/tests/` plus read-only CI and implementation evidence where it explains a guard. `git ls-files hass/tests | wc -l` returned `1279`; the source scan parsed all 911 tracked Python files. `git ls-files '*pytest.ini' '*pyproject.toml' '*conftest.py' '*tox.ini' '*setup.cfg'` returned no files. CI uses `unittest` (`hass/tests/ci_shards.py:329–331,474–484`); `hass/tests/ci_weights.json` `/measured` and `/seconds` describe balancing, not test selection or skips (`hass/tests/ci_shards.py:93–120`). An absent timing entry, a draft job skip, and a module not selected for an affected run are not test skip marks (`.github/workflows/check.yml:61–65,94–116,138–142`).

## R1. Explicit skips and expected failures

One row per live source site, not per test instance. The condition is written in the direction that **causes the skip** (or applies the expected-failure mark). Class decorators cover the class's tests; setup and helper skips can affect callers. A dash means the decorator carries no inline reason. The separate fixture and generated-case tables reconcile textual sites with actual test marks. To reproduce the text cross-check from the pinned clone:

```sh
git grep -niE 'skipif|skipunless|skiptest|expectedfailure|importorskip|xfail|[.]skip([^[:alnum:]_]|$)|collect_ignore|__unittest_(skip|expecting_failure)' -- hass/tests
git ls-files 'hass/tests/*.js' 'hass/tests/*.mjs' 'hass/tests/*.ts' 'hass/tests/*.sh'
```

The `[.]skip` branch uses a literal dot and requires a non-word character or end of line after `skip`, with no backslashes to escape. The first command should include `hass/tests/test_acceptance_runner.py:680:        @unittest.skip("x")`, a synthetic fixture match. The second command found no tracked files of those types. The AST pass classified decorators, calls, and raised exceptions and inspected bare names/attributes for alias candidates. The textual pass also caught synthetic Python embedded in strings.

| Site | Kind | Skip/mark when | Stated reason (source quote) |
| --- | --- | --- | --- |
| `hass/tests/test_catalog_new_order.py:30` | `skipUnless` | `not NODE` | `"node not installed"` |
| `hass/tests/test_clover_count_phrases.py:195` | `expectedFailure` | Unconditional | — |
| `hass/tests/test_club_intro.py:267` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_demo_browser.py:26` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_demo_browser_photo.py:26` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_design_preview.py:338` | `skipTest` | `not 0 < limit < 100000` | `"no finite component limit"` |
| `hass/tests/test_design_preview.py:530` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_editor_config_read.py:69` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"needs os.mkfifo"` |
| `hass/tests/test_fixture_chat.py:78` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_front.py:263` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `'PLAYWRIGHT_MODULE is not set'` |
| `hass/tests/test_front_pages.py:187` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `'PLAYWRIGHT_MODULE is not set'` |
| `hass/tests/test_generated_parent_types.py:61` | `skipTest` | `not kinds` | `"no FIFO/socket support"` |
| `hass/tests/test_generated_targets.py:65` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"no FIFOs on this platform"` |
| `hass/tests/test_health_seen.py:70` | `skipIf` | `hasattr(os, 'geteuid') and os.geteuid() == 0` | `"root ignores folder modes"` |
| `hass/tests/test_health_seen_read.py:69` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"needs os.mkfifo"` |
| `hass/tests/test_hidden_command.py:87` | `skipTest` | `len(ids) < 23` | `"fixture has fewer than 23 products"` |
| `hass/tests/test_hike_anchor.py:46` | `skipUnless` | `not NODE` | `"node is required to run community.js"` |
| `hass/tests/test_hike_ics.py:31` | `skipUnless` | `not NODE` | `"node is required to run community.js"` |
| `hass/tests/test_hike_journal.py:20` | `skipUnless` | `not NODE` | `"node is required to run community.js"` |
| `hass/tests/test_hike_samples.py:140` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_house_render_seam.py:80` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_house_render_seam.py:170` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_house_render_seam.py:250` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_house_render_seam.py:289` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_house_render_seam.py:335` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_house_style_cli_errors.py:70` | `skipTest` | `except hs.PillowMissing` | `"Pillow missing"` |
| `hass/tests/test_house_style_cli_errors.py:74` | `skipTest` | `not p.exists()` | `"rendered fixture absent"` |
| `hass/tests/test_image_dimensions.py:98` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_inbox_status.py:195` | `skipTest` | `not hasattr(os, 'mkfifo')` | `"no os.mkfifo on this platform"` |
| `hass/tests/test_item_add_dispatch.py:112` | `skipUnless` | `not HOOKS` | `"needs the SKILLS-FW-3d dispatcher hooks (stacked on SKILLS-FW-3, PR 526)"` |
| `hass/tests/test_itemstd.py:256` | `skipTest` | Current content blobs do not all match; `git show` for a pinned blob exits nonzero | `f"content changed and {SOURCE_COMMIT[:7]} is not in this clone"` |
| `hass/tests/test_ledger_rf1120.py:139` | `skipTest` | `not (REPO_ROOT / '.git').exists() or git('rev-parse', '--is-shallow-repository') == 'true'` | `"no .git (tarball checkout) or shallow clone: merge history not available"` |
| `hass/tests/test_ledger_rf1120.py:287` | `skipTest` | `not (REPO_ROOT / '.git').exists() or git('rev-parse', '--is-shallow-repository') == 'true'` | `"no .git (tarball checkout) or shallow clone: history not available"` |
| `hass/tests/test_maker_optional_story.py:186` | `skipUnless` | `not NODE` | `"node not installed"` |
| `hass/tests/test_maker_optional_url.py:160` | `skipTest` | `not node` | `"node not installed"` |
| `hass/tests/test_maker_site_sec3.py:627` | `skipTest` | `not tid.HOOKS` | `"needs the SKILLS-FW-3d dispatcher hooks"` |
| `hass/tests/test_media_sidecar_read.py:101` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"needs os.mkfifo"` |
| `hass/tests/test_memory_history.py:226` | `skipTest` | `os.lstat(self.db)` returns without `PermissionError` (inner `try` succeeds) | `"effective user is not refused by a mode-000 directory"` |
| `hass/tests/test_memory_source.py:79` | `skipTest` | `os.access(self.changes / 'chg-0000000000b6.json', os.R_OK)` | `"running as root"` |
| `hass/tests/test_newitem.py:96` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_newitem.py:108` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_newitem.py:464` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_newitem.py:484` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_newitem.py:581` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_newitem_demo.py:30` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_newitem_demo_alpha.py:16` | `skipUnless` | `not HAVE_PIL` | `"Pillow required"` |
| `hass/tests/test_newitem_render_16bit.py:48` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_newitem_render_alpha.py:34` | `skipUnless` | `not HAVE_PIL` | `"Pillow required"` |
| `hass/tests/test_newitem_render_gradient.py:50` | `skipIf` | `Image is None` | `"Pillow required"` |
| `hass/tests/test_newitem_render_gradient.py:83` | `skipIf` | `Image is None` | `"Pillow required"` |
| `hass/tests/test_newitem_render_holes.py:43` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_newitem_render_scale_warning.py:24` | `skipUnless` | `not HAVE_PIL` | `"Pillow needed"` |
| `hass/tests/test_newitem_render_shadow_continuity.py:38` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_newitem_render_translucent_luma.py:38` | `skipUnless` | `not HAVE_PIL` | `"Pillow not installed"` |
| `hass/tests/test_newitem_synthetic.py:24` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_newitem_synthetic_alpha.py:49` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_newitem_synthetic_alpha.py:114` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_newitem_synthetic_gps.py:31` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_newitem_synthetic_selectors.py:90` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_notice_start.py:204` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_notice_start.py:243` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_npp_posted_link.py:166` | `skipTest` | `not node` | `'NOT-RUN: Node 22 is not installed'` |
| `hass/tests/test_npp_posted_link.py:170` | `skipTest` | `not result.stdout.startswith('v22.')` | `'NOT-RUN: Node 22 is required'` |
| `hass/tests/test_npp_render_evidence.py:49` | `skipUnless` | `not preview.Previewer('.').env.get('PLAYWRIGHT_MODULE')` | `'Playwright not installed'` |
| `hass/tests/test_npp_stages.py:29` | `skipTest` | `self.port is None` | `'requires the real staged editor adapter'` |
| `hass/tests/test_npp_stages.py:267` | `skipUnless` | `not preview.Previewer('.').env.get('PLAYWRIGHT_MODULE')` | `'Playwright not installed'` |
| `hass/tests/test_owner_answers_when.py:25` | `skipTest` | `not hasattr(time, 'tzset')` | `"time.tzset unavailable: the host zone cannot be switched"` |
| `hass/tests/test_photo_polish.py:140` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_photo_polish.py:365` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_photo_polish.py:407` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_photo_polish_ocr_box.py:11` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_photo_polish_ocr_tsv.py:32` | `skipUnless` | `not HAVE_PIL` | `"Pillow is not installed"` |
| `hass/tests/test_photo_trial.py:178` | `skipTest` | `os.access(private, os.R_OK)` | `"this user can read a mode-0 folder (root)"` |
| `hass/tests/test_photo_trial.py:188` | `skipTest` | `os.access(parent, os.X_OK)` | `"this user can search a mode-0 folder (root)"` |
| `hass/tests/test_preview.py:47` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_preview.py:86` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_preview_cancel_note.py:36` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_preview_hike_results.py:128` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_preview_maker.py:54` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_preview_new_item_word.py:86` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_preview_new_photo.py:67` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_preview_product_checks.py:67` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_preview_route_results.py:67` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_preview_store_address.py:58` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_preview_store_checks.py:76` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_preview_viewports.py:160` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_product_alt.py:132` | `skipUnless` | `not NODE` | `"node is required for the storefront photo() driver"` |
| `hass/tests/test_publish_csp.py:164` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_qa_env.py:22` | `skipUnless` | `not NODE` | `"node is required for the QA scripts"` |
| `hass/tests/test_retention_paths.py:57` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"no FIFOs on this platform"` |
| `hass/tests/test_retention_paths.py:62` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"no FIFOs on this platform"` |
| `hass/tests/test_retention_paths.py:76` | `skipUnless` | `not hasattr(socket, 'AF_UNIX')` | `"no Unix sockets on this platform"` |
| `hass/tests/test_retention_paths.py:83` | `skipTest` | `sock.bind` raises `OSError` | `f"cannot bind a Unix socket here: {exc}"` |
| `hass/tests/test_retention_paths.py:104` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"no FIFOs on this platform"` |
| `hass/tests/test_retention_sidecar_read.py:90` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"no os.mkfifo"` |
| `hass/tests/test_revert_parent_directory.py:43` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"needs os.mkfifo"` |
| `hass/tests/test_revert_record_files.py:93` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"needs os.mkfifo"` |
| `hass/tests/test_revert_record_files.py:122` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"needs os.mkfifo"` |
| `hass/tests/test_set_photo_site_read.py:73` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"no FIFOs on this platform"` |
| `hass/tests/test_settings_config_file.py:54` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"needs os.mkfifo"` |
| `hass/tests/test_settings_config_file.py:113` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"needs os.mkfifo"` |
| `hass/tests/test_skills_acceptance_offline.py:356` | `skipTest` | Pillow import raises `ImportError` | `"Pillow is needed for synthetic images"` |
| `hass/tests/test_specials.py:418` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_statebackup_manifest_read.py:34` | `skipUnless` | `not hasattr(signal, 'setitimer')` | `"needs SIGALRM timers"` |
| `hass/tests/test_statebackup_manifest_read.py:69` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"needs os.mkfifo"` |
| `hass/tests/test_store_clear_home_image.py:87` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_store_headline.py:138` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_store_home_image.py:145` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_store_notice.py:166` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_store_notice.py:195` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_store_phone.py:118` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_store_story.py:120` | `skipUnless` | `not os.environ.get('PLAYWRIGHT_MODULE')` | `"PLAYWRIGHT_MODULE is not set"` |
| `hass/tests/test_tracked_private.py:69` | `raise SkipTest` | `except NotACheckout` | `"not a git checkout"` |
| `hass/tests/test_writer_lock_entry.py:76` | `skipUnless` | `not hasattr(os, 'mkfifo')` | `"needs os.mkfifo"` |
| `hass/tests/test_writer_lock_entry.py:84` | `skipUnless` | `not hasattr(socket, 'AF_UNIX')` | `"needs unix sockets"` |

### Generated cases and synthetic fixtures

The Clover decorator is one source site, not one test. `hass/tests/test_clover_count_phrases.py:194–206` attaches the mark unconditionally to each generated test, with the reason from this table. The bodies assert refusal; an unexpected success is not an ordinary pass in the shard runner (`hass/tests/ci_shards.py:479–484`).

| Case suffix after `test_c3_no_false_accepts_` | Reason source | Stated reason |
| --- | --- | --- |
| `bucks` | `hass/tests/test_clover_count_phrases.py:85` | “Treats bucks as part of the product name.” |
| `two_products` | `hass/tests/test_clover_count_phrases.py:86` | “Combines two products into one query.” |
| `hike_miles` | `hass/tests/test_clover_count_phrases.py:87` | “Treats the hike distance as a count.” |
| `website_photo` | `hass/tests/test_clover_count_phrases.py:88–89` | “Treats a photo choice as a stock set.” |

| Site | Kind | Condition | Stated reason |
| --- | --- | --- | --- |
| `hass/tests/test_acceptance_runner.py:662` | fixture `expectedFailure` | Unconditional in `UNEXP` | — |
| `hass/tests/test_acceptance_runner.py:669` | fixture `expectedFailure` | Unconditional in `UNEXP2`, `test_a` | — |
| `hass/tests/test_acceptance_runner.py:671` | fixture `expectedFailure` | Unconditional in `UNEXP2`, `test_b` | — |
| `hass/tests/test_acceptance_runner.py:678` | fixture `expectedFailure` | Unconditional in `EXPECTED` | — |
| `hass/tests/test_acceptance_runner.py:680` | fixture `unittest.skip` | Unconditional in `EXPECTED` | `"x"` |

These string fixtures exercise runner accounting; they are not quarantined Hass tests (`hass/tests/test_acceptance_runner.py:659–682,691–812`). `hass/tests/test_tracked_private.py:106` asserts that the `SkipTest` from line 69 **is raised** in a negative control; the assertion does not skip the control itself. No live unconditional `unittest.skip` decorator was found. The `load_tests` match in `hass/tests/test_acceptance_runner.py:45` is also embedded in a fixture; `hass/tests/run_parallel.py:23–34` walks suites, not a mark registry.

**Collect-only evidence (2026-11-21):** `python3 -B -m pytest --version` exited 1 (`No module named pytest`). Instead a scratch `unittest.TestLoader().discover('hass/tests', top_level_dir='.')` listing recursed over suites and printed each case ID and its class/method mark attributes. No `TestSuite.run`, test body or setup was called. The probe used a task-local empty HOME, no browser exports, a restricted environment, and a read-only import fence denying network, process and database activity. It exited 1 with `COLLECTED 8788; loader errors 82; decorator-skipped 94; expected-failure 4; denied events 164`; denial types were `ctypes.dlopen` and `open`. The 8,788 entries include loader placeholders. This partial, local listing confirms the four generated marks and that `RealDispatcher` was collectable without a skip mark; it does **not** measure hosted skip rates or cover runtime skips. R1 and R3 use the independently complete static source scan, not this incomplete import result.

## R2. Which guards should not fire in CI?

“Expected false” below means under the checked-in successful setup at this SHA, not a guarantee across future runner images, failed installations, changed fixtures, or environment modifications. These are source-based estimates unless a Git fact is stated separately. No hosted job or test body was run for this audit.

| R1 sites or condition family | Assessment and evidence |
| --- | --- |
| `test_item_add_dispatch.py:112`; `test_maker_site_sec3.py:627` | **Named change already present.** The old reason says “needs the SKILLS-FW-3d dispatcher hooks”. `hass/tests/test_item_add_dispatch.py:25–29` probes `hasattr(dispatch, "skill_hook")`; `hass/skills/dispatch.py:358–362` defines `skill_hook`, and lines 370 and 999 call it for `"question"` and `"notes"`. The maker setup uses the exact same `HOOKS` boolean (`hass/tests/test_maker_site_sec3.py:624–627`). This establishes the source prerequisite on main, not that the test bodies pass. |
| All `PLAYWRIGHT_MODULE` rows, including `Previewer(...).env` | **Expected false after successful setup.** Both execution routes call `test-env` (`.github/workflows/check.yml:109–116,150–176`). The installer exports `PLAYWRIGHT_MODULE` to `GITHUB_ENV` (`.github/actions/test-env/install-playwright.sh:50–57`), and the composite then verifies “Chromium launches” (`.github/actions/test-env/action.yml:23–30`). `Previewer` copies `os.environ` before any fallback (`hass/preview.py:292–303`). The quick *plan* imports before this step; collection-time marks there are not the subsequent test run's marks. |
| Node presence and the two Node-major guards | **Expected false after successful setup.** Both routes set `node-version: "22"` (`.github/workflows/check.yml:81–83,158–160`). Compare the PATH probes, e.g. `hass/tests/test_catalog_new_order.py:8,30`, `hass/tests/test_hike_journal.py:5,20`, and actual version prefix check at `hass/tests/test_npp_posted_link.py:164–170`. |
| Pillow availability, including exception skips | **Expected false after successful setup.** `reports/hass/NEWITEM-1.md:67` previously said “CI python (setup-python) has no Pillow”. CI now installs `Pillow==$PILLOW_VERSION` on the test import path in both routes (`.github/workflows/check.yml:49–51,85–92,164–168`); quick explicitly says “fails, never skips, without it”. This is dependency provisioning, not a proof that a feature-specific Pillow import cannot fail. |
| FIFO, Unix-socket **attribute** checks, `time.tzset`, `signal.setitimer` | **Expected false on the specified Ubuntu/CPython 3.12 jobs** (`.github/workflows/check.yml:65,77–79,142,154–156`). This includes the combined empty `kinds` check (`hass/tests/test_generated_parent_types.py:55–61`). It does not imply a socket bind must succeed (`hass/tests/test_retention_paths.py:79–83`), a particular effective UID, or a usable filesystem limit. |
| `test_house_style_cli_errors.py:74` | **False for an intact pinned checkout after Pillow imports.** `hass/tests/test_house_style_cli_errors.py:18,66–75` asks for two fixed image files; `git ls-tree origin/main -- reports/hass/newitem-1/rendered/jar-white-sheet.jpg reports/hass/newitem-1/rendered/bag-red-cloth.jpg` lists both as regular tracked blobs. This is not a promise about future checkouts. |
| `test_itemstd.py:256` | **Not reached at the pinned tree.** `git ls-tree origin/main -- hass/content/products.json hass/content/makers.json` returns the two exact hashes in `hass/tests/test_itemstd.py:24–26`, so `historical_content` takes its current-blob fast path at lines 248–250. If these blobs change, the shallow runner may lack the historical commit and the skip can fire (lines 251–256). |
| `test_tracked_private.py:69` | **Not expected for the normal CI Git checkout.** Both routes use `actions/checkout` (`.github/workflows/check.yml:71–75,149–152`); the no-checkout branch is intentionally covered with another directory (`hass/tests/test_tracked_private.py:62–69,101–106`). |
| `test_npp_stages.py:29` | **Adapter exists; still reachable on a regression.** The fixture installs a real `SiteEditor` and a previewer (lines 22–29). All three required editor methods exist (`hass/sandbox_editor.py:59,89,96`; predicate at `hass/npp/stages.py:266–271`). But `hass/npp/reply.py:150–157` can return `None` on `ImportError`, `KeyError`, `ValueError` or `TypeError`; this is not a dead guard. |
| `test_ledger_rf1120.py:139,287` | **Expected true when selected on shallow CI**, not dead. The quick checkout is explicitly depth 2 and the full checkout does not override checkout's default shallow depth (`.github/workflows/check.yml:71–75,149–152`). These tests require a non-shallow repository. The local clone used for source evidence was not a hosted checkout. |
| Remaining runtime predicates and Clover expected failures | **Not proved obsolete.** Permission checks, real socket bind, filename limits and minimum fixture size depend on setup/runtime or on the checked-out fixture (`hass/tests/test_health_seen.py:70`, `test_memory_history.py:220–229`, `test_memory_source.py:79`, `test_photo_trial.py:178,188`, `test_retention_paths.py:79–83`, `test_design_preview.py:336–338`, `test_hidden_command.py:56–58,85–92`; these short filenames are under `hass/tests/`). Clover's marks are assertions of currently documented false accepts, not conditions; collection cannot establish that any of those cases now refuses (`hass/tests/test_clover_count_phrases.py:83–90,194–206`). |

## R3. Files with early returns or no assertion in their test bodies

| File | Finding |
| --- | --- |
| None — direct early return | Zero Python `Return` nodes in the inspected test bodies, including conditional branches. Consequently no file had all its test bodies return early by this definition. `hass/tests/test_npp_caption_table.py:177–191` is a helper return **after** assertions, not a silent test return. `skipTest` is an exception, not a return, and is counted in R1. |
| `hass/tests/test_install_quiescence.py:41,46,53,68,76` | All five test bodies lack direct checks by the definition below. `check_rows` (38–39) and `verdict` (23–36) actually assert status and output. This is not a coverage hole. |

Method and 2026-11-21 receipt: `python3 -B audit.py` in scratch beside the clone used `git ls-files -z hass/tests` and `ast.parse`. Select direct module/class `def` or `async def` whose name starts `test` in files beginning `test`, and walk their bodies without entering inner function/class/lambda scopes. The scan reported 9,315 source definitions in 901 files, not 9,315 runtime cases. The only file with **no direct check in any body** was the one above, counting `assert` statements, calls whose bare or dotted name starts `assert` (including mock assertions), `fail`, `raises`, `check_call`/`check_output`, and non-skip `raise` as potential failure checks. A keyword-only definition of “assert” flagged 879 files because assertion methods do not use the keyword; that is not a coverage-loss list. The scan does not prove that a check is reached, that every path checks a result, or that helpers, inherited methods, setup, callbacks, generated tests and empty loops cannot silently lose coverage. No point in this report infers pass/fail from collection.

## R4. Ranked gaps and one bounded follow-up

| Rank | Gap |
| --- | --- |
| 1 | **NPP stage setup can hide a broken integration.** A `None` adapter skips the stage class, including duplicate-confirmation and draft-binding cases (`hass/tests/test_npp_stages.py:17–30,83,138,162,267–268`). CI's JSON receipt has a skip count but does not identify the skipped test IDs; IDs and reasons are visible only in the verbose runner log (`hass/tests/ci_shards.py:474–489`). |
| 2 | **History coverage can be missing even on a full test tier.** Both explicit shallow-history guards can fire in the checked-in workflow (R2); test selection alone cannot show that the two history checks ran (`hass/tests/test_ledger_rf1120.py:137–139,285–287`). |
| 3 | **Known refusal failures stay marked and old dispatcher reasons are misleading.** The former are four documented cases, not evidence of a current fix; the latter are two stale prerequisite explanations (R1/R2). Keep these separate from deliberate local portability guards and the helper-only file in R3. |

**At most one proposed unit (estimate: 60–90 minutes; not implemented):** Add stable skipped test IDs alongside the existing `skipped` count in the shard JSON receipt (`hass/tests/ci_shards.py:479–488`), without persisting free-text reasons, changing selection, changing the runner verdict, or changing any skip/xfail. Files: `hass/tests/ci_shards.py` and `hass/tests/test_ci_shards.py`. Offline test: extend the shard receipt tests with synthetic pass, decorator skip, setup skip and expected failure cases; confirm stable IDs for only the two skips, preserved counts and unchanged `ok`, then run `python3 -B -m unittest hass.tests.test_ci_shards` in that separately scoped build. No code, tests, data, or workflow changed in this audit.
