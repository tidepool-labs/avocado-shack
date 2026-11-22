# AVO1520-03 — Hass install-script reachability

| Question | Result at audited main | Evidence below |
|---|---|---|
| R1. Who calls the scripts? | 29 of 29 have a test caller: 23 imported, six CLI-only. No non-test execution caller found in the scanned source; no script is standalone across **all** three caller types. | R1 and checks A–B |
| R2. What do the three docs name? | Zero of the 29. Zero stale `install_*.py` names in the three docs: none of the docs names that family at all. Other named Python and shell source paths exist. | R2 and check C |
| R3. What can change? | Four have explicit file writes, one can create a SQLite sidecar under some conditions, and 24 have no file-write path found. No script directly queries or changes service state. | R3 and check D |
| R4. What is worth building? | One candidate: document the boundary between the Mac shell kit and the separately tested Python tools. | R4 |

**Snapshot:** `tidepool-labs/avocado-shack` `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a` (matches the task baseline), read on 2026-11-21. This is a static source audit, not a live or CI check. No installer, test, shell kit, service command, or doc example was run. No runtime/config/credential file was needed. `git ls-tree -r --name-only origin/main -- reports/hass-npp/G-QUESTIONS.md` returned no path; the exclusions in the task were retained without inferring any additional owner decisions.

## R1. Every installer and its callers

Each filename in the first column is relative to `scripts/hass/`; `:2` is the docstring anchor. Test anchors in this table are relative to `hass/tests/`. **Import** includes both normal Python imports and `importlib` loaders that execute the module. **CLI** means a test subprocess invokes the file. An import does not by itself establish CLI coverage. Every row is **test-called / standalone outside tests** in the scan: no script or doc execution edge found (checks A–C).

| Script and docstring line | First docstring line (verbatim) | Called by | Test imports it? |
|---|---|---|---|
| `install_acceptance_receipt.py:2` | Check a saved Hass acceptance receipt without running acceptance. | Import `test_install_acceptance_receipt.py:11` | Yes |
| `install_allowlist_diff.py:2` | Check that two local commits have the same maker allowlist. | Import `test_install_allowlist_diff.py:14–18`; CLI `:84` | Yes |
| `install_backup_receipt.py:2` | Verify a completed editor-config backup offline without modifying either file. | Import `test_install_backup_receipt.py:16–20`; CLI `:66` | Yes |
| `install_ci_receipt.py:2` | Judge a saved check-runs capture against a release SHA, offline. | Import `test_install_ci_receipt.py:12–16` | Yes |
| `install_citation_drift.py:2` | Check install-kit citation spans against a local commit, not the checkout files. | CLI `test_install_citation_drift.py:11,51–52` | No — CLI |
| `install_config_attributes.py:2` | Check install-kit config and backup attributes without opening either file. | Import `test_install_config_attributes.py:11` | Yes |
| `install_digest_ledger.py:2` | Record or check a config digest in an offline, owner-only ledger. | Import `test_install_digest_ledger.py:16–20`; CLI `:84` | Yes |
| `install_entry_gate.py:2` | Find install entry-gate merge SHAs in a local Git checkout. | Import `test_install_entry_gate.py:15–19`; CLI `:63` | Yes |
| `install_launchagent.py:2` | Check two offline LaunchAgent plist copies and the configured forwarder path. | Import `test_install_launchagent.py:14–19` | Yes |
| `install_mac_parity.py:2` | Compare a supplied Mac forwarder copy with a selected Git commit, offline. | CLI `test_install_mac_parity.py:12,53–54` | No — CLI |
| `install_pending_work.py:2` | Count pending work in offline Hass stores before a switch or resume. | Import `test_install_pending_work.py:15–19` | Yes |
| `install_preflight_verdict.py:2` | Evaluate saved NPP preflight stdout and its separately recorded exit status. | Import `test_install_preflight_verdict.py:10` | Yes |
| `install_private_files.py:2` | Check private install paths without opening receipts or changing permissions. | Import `test_install_private_files.py:14–18` | Yes |
| `install_quiescence.py:2` | Check one saved snapshot, never the current state of a service. | Import `test_install_quiescence.py:10` | Yes |
| `install_rehearsal.py:2` | Rehearse the NPP switch and rollback on a disposable synthetic config. | Import `test_install_rehearsal.py:17–21`; CLI `:44–45` | Yes |
| `install_release_lineage.py:2` | Check release ancestry and tree paths using only a local Git checkout. | CLI `test_install_release_lineage.py:12,53–56` | No — CLI |
| `install_revert_scan.py:2` | Check a selected release for explicit reverts and restored pre-merge files. | Import `test_install_revert_scan.py:13–17` | Yes |
| `install_rollback_proof.py:2` | Check rollback config bytes without changing files or service state. | CLI `test_install_rollback_proof.py:13,31` | No — CLI |
| `install_runtime_readback.py:2` | Check the consistency of one saved, post-release Hass capture (JSON on stdin). | Import `test_install_runtime_readback.py:9` | Yes |
| `install_service_restart.py:2` | Check two saved service captures for a fresh start and no intervening restarts. | Import `test_install_service_restart.py:11–15` | Yes |
| `install_skill_parity.py:2` | Compare operator-resolved skill files with a selected local Git commit. | CLI `test_install_skill_parity.py:11,55–56` | No — CLI |
| `install_skill_restore_proof.py:2` | Read-only proof against an operator-approved roster and prior-state manifest. | Import `test_install_skill_restore_proof.py:13` | Yes |
| `install_skill_shadow.py:2` | Check skill precedence in operator-listed roots, without modifying them. | Import `test_install_skill_shadow.py:14–18` | Yes |
| `install_stage_file.py:2` | Check an adjacent config stage without changing either file. | Import `test_install_stage_file.py:15–19`; CLI `:53` | Yes |
| `install_store_schema.py:2` | Compare stable, checkpointed store copies with this checkout's schema. | CLI `test_install_store_schema.py:22,48–49`; import `:108–112` | Yes |
| `install_switch_projection.py:2` | Project the editor's three NPP switches for the flat preflight input. | CLI `test_install_switch_projection.py:12,27–28` | No — CLI |
| `install_switch_readback.py:2` | Check a candidate or installed JSON config against its pre-switch backup. | Import `test_install_switch_readback.py:12`; CLI `:128–129` | Yes |
| `install_tools_checkout.py:2` | Check the reviewed tools checkout offline (origin is a local config check). | Import `test_install_tools_checkout.py:13–17` | Yes |
| `install_window_clock.py:2` | Check an attended install JSON Lines log against the kit's time budgets. | Import `test_install_window_clock.py:12–16` | Yes |

Two read dependencies are not execution edges: `scripts/hass/install_tools_checkout.py:51–65` lists and hashes all 29 tracked files, including itself; the CI planner (`.github/workflows/check.yml:97`, `hass/tests/ci_shards.py:150–151,179–205`) reads and parses tracked Python source to select tests. `scripts/hass/mac_install.sh:145–153` prints instructions naming `mac_setup_check.sh`; it does not invoke it there. No `install_*.py` is called by the Mac shell kit in the scanned sources. CLI references inside a script's own docstring/help are self-documentation, not another caller. These results say nothing about an operator's private kit or manual invocations outside the repo.

## R2. Docs and missing paths

| Doc | What it names instead (quoted filenames or short excerpt) | `install_*.py` names |
|---|---|---|
| `docs/hass/INSTALL-LIVE-FIX-2.md` | “Deploy the reviewed Hass runtime through the normal release path” (`:3`); no literal Python or shell script name. | None |
| `docs/hass/MAC_RUNBOOK.md` | `hass/acceptance.py` (`:60`), `hass/editor.py` (`:103`), `hass/host.py` (`:110`), `hass/inbox.py` (`:117`), `hass/publish_live.py` (`:142–151`) and `mac/hass_forwarder.py` (`:160`). | None |
| `docs/hass/MAC_MINI_FINAL_STEPS.md` | “Everything else is in two scripts” (`:4`): `mac_install.sh` and `mac_setup_check.sh`; the test plan also names `hass/inbox.py` and `mac/hass_forwarder.py` (`:67–68`). | None |

**Missing scripts named by the three docs: none.** Check C returned no `install_*.py` mention, and all source `.py`/`.sh` names in the table resolve as tracked files. The runbook's `.plist` destination is a generated artifact, not a missing source script: it names a tracked `.plist.template` as the input (`docs/hass/MAC_RUNBOOK.md:84`; check C).

**Existing scripts no doc names:** every literal filename in R1, `install_acceptance_receipt.py` through `install_window_clock.py` inclusive. The three-doc match result on 2026-11-21 was **empty output (exit 1)**. Check B also found no direct references to the 29 names in the broader tracked prose paths scanned; that is not a claim about untracked or external docs.

## R3. Files and services (static only)

Paths in the first column are relative to `scripts/hass/`. “Writes” means a file created, changed or replaced by the tool or a dependency on its normal CLI path, including temporary files and conditional sidecars; not stdout/stderr, caller redirection, or incidental interpreter bytecode caches. “Service” includes live queries as well as control, but excludes reading saved output and running local Git inspections. Each `No` is a static finding for the cited entry path, not a runtime guarantee for arbitrary environments.

| Script | Writes any file? | Touches a service? | Source evidence |
|---|---|---|---|
| `install_acceptance_receipt.py` | No | No | `:110–126` reads and validates saved files and prints a verdict. |
| `install_allowlist_diff.py` | No | No | `:59–80,97–120` reads Git revision/blob data and prints a comparison. |
| `install_backup_receipt.py` | No | No | `:41–42,76–106` opens inputs read-only and prints a digest/verdict. |
| `install_ci_receipt.py` | No | No | `:25,81–117` reads a saved check-runs capture, not the CI service. |
| `install_citation_drift.py` | No | No | `:19–21,39–47,54–95` inspects locally stored Git objects and prints results. |
| `install_config_attributes.py` | No | No | `:29,63–66,73–92` checks file metadata and backup-path vacancy. |
| `install_digest_ledger.py` | **Yes — record mode** | No | `:100–105,116–139,144–172` creates or appends to the ledger; match mode reads. |
| `install_entry_gate.py` | No | No | `:28,65–104,138–152` reads the supplied units file and searches the local Git history/tree. |
| `install_launchagent.py` | No | No | `:18,66–106` reads and compares plist files; no LaunchAgent control or query. |
| `install_mac_parity.py` | No | No | `:27–39,54–55,70–88` compares local Git bytes to a supplied copy; no Mac connection. |
| `install_pending_work.py` | **Yes, potentially — SQLite WAL sidecar** | No | `:23–49` opens the supplied path with `mode=ro` and executes `BEGIN`/`SELECT`. No intentional database-content write, but SQLite can create or update shared-memory sidecar state when reading a WAL database; no isolated copy here. Not reproduced on this card. |
| `install_preflight_verdict.py` | No | No | `:115–144` reads saved stdout and a supplied exit status, then prints; does not run preflight. |
| `install_private_files.py` | No | No | `:19,37–42,69–89` uses metadata reads, then reports findings; no permission changes. |
| `install_quiescence.py` | No | No | `:2–13,39,64–72` checks a saved snapshot, not live service state. |
| `install_rehearsal.py` | **Yes — synthetic temporary files** | No | `:21–35,63–109` writes, backs up, replaces and restores a disposable synthetic config. |
| `install_release_lineage.py` | No | No | `:28,55–76,95–114,118–135` reads a manifest and inspects local Git objects and ancestry. |
| `install_revert_scan.py` | No | No | `:19–28,42–75,96–105,140–151` reads local Git objects/history and prints findings. |
| `install_rollback_proof.py` | No | No | `:24–38,48–84` compares digests of read-only file handles; no rollback performed. |
| `install_runtime_readback.py` | No | No | `:110–132` consumes a saved capture on stdin and prints consistency; no current-state readback. |
| `install_service_restart.py` | No | No | `:27,79–115` compares two saved captures; does not restart or query units. |
| `install_skill_parity.py` | No | No | `:38–51,62–69,98–129` reads Git blobs and supplied local skill files. |
| `install_skill_restore_proof.py` | No | No | `:60–78,153–177` reads and checks the supplied evidence; no restore performed. |
| `install_skill_shadow.py` | No | No | `:34,42,114–119,127–177` reads a roster and scans supplied roots for precedence/digests. |
| `install_stage_file.py` | No | No | `:49–50,66–94` reads a config and stage; does not promote the stage. |
| `install_store_schema.py` | **Yes — temporary databases and snapshot copies** | No | `:27–55,60–80` creates scratch dirs, initializes SQLite reference stores and copies input bytes before checking; no intended writes next to inputs. Local constructors: `hass/relay.py:173–184` and `hass/inbox.py:90–100`. |
| `install_switch_projection.py` | **Yes — with an output path** | No | `:69–73,78–96` creates a new file when requested; otherwise stdout. Does not edit the input config. |
| `install_switch_readback.py` | No | No | `:38,89–118` reads and compares candidate/installed and backup JSON. |
| `install_tools_checkout.py` | No | No | `:22–28,39,51–65,81–96` reads Git metadata/status with optional locks disabled, and hashes local files; it does not contact the origin. |
| `install_window_clock.py` | No | No | `:45,107–125` reads a saved log and prints time-budget results. |

## R4. Ranked gaps and one possible follow-up

1. **Discoverability.** None of the 29 is named in the three install docs, and the Mac mini doc points to the two shell scripts instead (R1; `docs/hass/MAC_MINI_FINAL_STEPS.md:4`). The source audit shows tested standalone helpers, not a checked-in chain to run.
2. **Read-only is not the same as no file effects.** The pending-work parser's `mode=ro` (`scripts/hass/install_pending_work.py:29–31`) is not the same isolation boundary as schema inspection's copy-first approach (`scripts/hass/install_store_schema.py:60–80`). The four explicit writers also have different output scopes (R3). Do not infer that these tools can all be used against the same kind of input.
3. **Import coverage is not the right proxy for missing tests.** The six no-import rows all have a test invoking the CLI (R1). That supports listing the test mode, not adding imports or duplicate tests. Neither mode establishes real Mac or service coverage.

**One proposed unit (estimate: 60–90 minutes; not part of this change):** In `docs/hass/MAC_MINI_FINAL_STEPS.md` only, add a short, non-executable index that separates the two shell-kit files from the separately tested Python helpers. Name the explicit output writers and the possible SQLite sidecar without adding run commands, rollout steps, time limits, or approval rules. **Offline acceptance:** inspect the resulting diff and resolve every listed repo-relative link against `git ls-files`; on a scratch text copy, rename one target to a nonexistent path and confirm the link check flags it. Do not invoke any link target. No file or procedure change is made by this report.

## Reproduce the static checks

Run in a checkout of the snapshot above. These commands read source/metadata only. For the source inspections, use `git show <audited-ref>:<path>` and the cited line numbers; no module imports are required.

Copy commands from the Markdown code blocks, not from a JSON-escaped representation. In the single-quoted extended regexes, `[.]` matches a literal dot, and each literal parenthesis uses one backslash.

**A. Inventory and first docstring lines**

```sh
git rev-parse origin/main
git ls-tree -r --name-only origin/main -- scripts/hass
git grep -n -E '^"""[^" ]' origin/main -- 'scripts/hass/install_*.py'
```

**B. Find caller candidates, then verify how each matching test loads or runs its target.** Ignore self-names, synthetic fixtures, unrelated functions like `install_locked`, and the wildcard read in `install_tools_checkout.py`. The name scan is bounded to the tracked source/prose paths below; it does not infer external or computed callers from a negative literal search.

```sh
git grep -n -o -E 'install_[*a-z0-9_]+([.]py)?' origin/main -- '*.py' '*.sh' '*.md' '*.txt' '*.yaml' '*.yml' '*.toml' '*.json' '*.service' ':(exclude)commerce/**' ':(exclude)storefront-mockup/**' ':(exclude,glob)**/*credential*' ':(exclude,glob)**/*token*' ':(exclude,glob)**/*secret*' ':(exclude,glob)**/host.json'
git grep -nE 'from scripts|exec_module|spec_from_file_location|subprocess[.](run|check_output)|str\((SCRIPT|CLI)\)' origin/main -- 'hass/tests/test_install_*.py'
```

**C. Compare the docs' script tokens to tracked source names**

```sh
git grep -n -o -E 'install_[a-z0-9_]+([.]py)?' origin/main -- docs/hass/INSTALL-LIVE-FIX-2.md docs/hass/MAC_RUNBOOK.md docs/hass/MAC_MINI_FINAL_STEPS.md
git grep -n -o -E '[A-Za-z0-9_.-]+[.](py|sh|plist)([.]template)?' origin/main -- docs/hass/INSTALL-LIVE-FIX-2.md docs/hass/MAC_RUNBOOK.md docs/hass/MAC_MINI_FINAL_STEPS.md
git ls-tree -r --name-only origin/main -- scripts/hass mac hass/acceptance.py hass/editor.py hass/host.py hass/inbox.py hass/publish_live.py
```

**D. Find I/O and service candidates, then read the enclosing functions and the local constructors named in R3.** A keyword hit alone is not a file write or live call.

```sh
git grep -nE 'write_text|write_bytes|[.]write\(|[.]open\(|open\(|mkdir|TemporaryDirectory|subprocess|[.]replace\(|unlink|chmod|shutil|sqlite3|launchctl|systemctl|urlopen|socket' origin/main -- 'scripts/hass/install_*.py'
```
