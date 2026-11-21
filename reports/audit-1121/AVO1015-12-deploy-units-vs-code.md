# AVO1015-12 — Hass systemd templates vs. code and operations guide

| Check | Result | Evidence |
| --- | --- | --- |
| Targets and arguments | All 6 `ExecStart` lines point to tracked Python files and their arguments parse. The additional `ExecStartPost` also passes. | R1 |
| Timer wiring | All 4 timers have a matching service. Only receiver and worker have no timer; the guide says both run “always.” | R2 |
| Operations guide | The four core services agree with the guide where it gives schedules and paths. The guide leaves out both Clover pairs, and abbreviates the health invocation and timer settings. | R3 |
| Recommendation | No unit repair indicated. One optional docs-and-test follow-up; nothing installed, started or changed. | R4 |

Read on **2026-11-21** at `tidepool-labs/avocado-shack` main `37feae1dc5efa6968f90d17a1eda6daed29afd4a`. The audited units, Python entry points, and cited operations/release/Clover docs and LaunchAgent helper were unchanged from the card baseline `1f8510907cb2989bb50391fde45d6211e4735879` (see reproduction below). This checks source templates, not deployed units or the installed runtime revision.

## R1. Unit, timer, schedule and parser

Each command below starts with `/usr/bin/python3 -B`; `-B` belongs to Python (see `python3 --help`), not to the script parser. `R` abbreviates the literal `%h/.local/share/hass/runtime`; `S` abbreviates `%h/.local/state/hass`. These are template strings, not inspected host paths. Each target after `R/` is a tracked source path on the audited main (see `git ls-tree` below).

| Service and command anchor | Timer and exact schedule directive | Target and command arguments | Parser definitions |
| --- | --- | --- | --- |
| `deploy/hass/hass-backup.service:7` | `deploy/hass/hass-backup.timer:5–6`: `OnCalendar=*-*-* 03:30 America/Los_Angeles`, daily at 03:30 Pacific; `Persistent=true`. | `R/hass/statebackup.py create --state S/state --out S/backups` | `create`, `--state`, `--out`: `hass/statebackup.py:574` (declarations), `:578–579` (registration). |
| `deploy/hass/hass-clover-report.service:7` | `deploy/hass/hass-clover-report.timer:5–6`: `OnCalendar=*-*-* 06:00 America/Los_Angeles`, daily at 06:00 Pacific; `Persistent=true`. | `R/hass/clover/cli.py report --all --host S/host/host.json` | `report`: `hass/clover/cli.py:243`; `--all`: `:245`; `--host`: `:246`. The optional `kind` is omitted (`:244`); the handler accepts `--all` without `kind` (`:197–199`). |
| `deploy/hass/hass-clover-sync.service:8` | `deploy/hass/hass-clover-sync.timer:5–8`: `OnCalendar=*:0/15`, every 15 minutes; `RandomizedDelaySec=60`, `AccuracySec=30s`, `Persistent=true`. No explicit time zone. | `R/hass/clover/cli.py sync --host S/host/host.json` | `sync`: `hass/clover/cli.py:238–239`; `--host`: `:240`. |
| `deploy/hass/hass-clover-sync.service:9` (**`ExecStartPost`**, same service) | Same timer as sync above; not a separate unit or schedule. | `R/hass/stock_site.py run --host S/host/host.json` | `run` (positional choice, not a subparser) and `--host`: `hass/stock_site.py:291`. |
| `deploy/hass/hass-health.service:7` | `deploy/hass/hass-health.timer:5–6`: `OnCalendar=*:0/5`, every 5 minutes; `AccuracySec=30s`. No explicit time zone or `Persistent=`. | `R/hass/health.py --state S/state --backups S/backups --seen S/health.seen --writer --model http://127.0.0.1:11434 --host-dir S/host --alert-log %h/agent-work/modes/ALERTS.log` (no subcommand). | `--state`: `hass/health.py:455`; `--backups`, `--seen`, `--model`, `--host-dir`, `--alert-log`: `:456–457`; `--writer`: `:463`. |
| `deploy/hass/hass-receiver.service:10` | None; intended to run continuously (R2). | `R/hass/host.py serve --host S/host/host.json` | `serve`: `hass/host.py:591–592`; `--host`: `:596`. |
| `deploy/hass/hass-worker.service:10` | None; intended to run continuously (R2). | `R/hass/host.py work --host S/host/host.json` | `work`: `hass/host.py:591–592`; `--host`: `:596`. |

The two interval expressions use the system manager's local time zone because neither expression names one. Pacific is explicit only on the two daily timer templates; this audit did not inspect the host clock or manager settings. The cadences are nominal, not exact start guarantees (`AccuracySec`/`RandomizedDelaySec` in the table).

## R2. Orphans and continuous services

- **Timers with no service: none.** None of the four `[Timer]` sections overrides `Unit=`, so each activates its same-basename `.service`: backup, clover-report, clover-sync and health. Each is a `Type=oneshot` service. See the full inventory and the `Type`, `Unit` and `OnCalendar` reproduction below.
- **Services with no timer: `hass-receiver.service` and `hass-worker.service` only.** `docs/hass/OPERATIONS.md:11–12` pairs `host.py serve` and `host.py work` with “always” for each. Both units declare `Type=simple`, `Restart=on-failure` and `WantedBy=default.target` (`deploy/hass/hass-receiver.service:7–18`, `deploy/hass/hass-worker.service:7–18`). This is the intended mode if enabled, not an observation of uptime; the guide documents a failed-start limit (`docs/hass/OPERATIONS.md:16–17`).

## R3. Guide wording versus templates

| Item | `docs/hass/OPERATIONS.md` says | Unit says; agreement or difference |
| --- | --- | --- |
| Runtime worktree | “The code runs from the **runtime worktree** `~/.local/share/hass/runtime`” (`:19`). | All six say `WorkingDirectory=%h/.local/share/hass/runtime` and use that same prefix in `ExecStart` (one line before each `ExecStart` in R1). `~` in prose and `%h` in the user templates name the same intended layout. The guide does not spell out the Python executable or `-B` in the service inventory. |
| Receiver / worker | “`host.py serve`” and “`host.py work`,” both “always” (`:11–12`); “`Restart=on-failure`” (`:17`). | `hass/host.py serve --host …` and `hass/host.py work --host …` under the runtime prefix, with `Restart=on-failure` (`deploy/hass/hass-receiver.service:10–11`, `deploy/hass/hass-worker.service:10–11`). Entrypoints and intended mode agree. The guide mentions `host.json` at `:20` but does not give the service's `--host` argument and template path there. |
| Backup | “`statebackup.py create`” and “03:30 Pacific, `Persistent=true`” (`:14`). | `OnCalendar=*-*-* 03:30 America/Los_Angeles` and `Persistent=true` (`deploy/hass/hass-backup.timer:5–6`). The script and schedule agree; the inventory omits `--state` and `--out` and their paths (`deploy/hass/hass-backup.service:7`). The guide's `hass/statebackup.py` verify/drill/restore examples are operator commands, not alternate timer targets (`:112–119`). |
| Health | “`health.py` with `--host-dir` and `--alert-log`” and “every 5 min” (`:13`); “appends one line to `~/agent-work/modes/ALERTS.log`” (`:69`). | `OnCalendar=*:0/5`, `AccuracySec=30s`, no `Persistent=` (`deploy/hass/hass-health.timer:4–6`). Script, nominal cadence and alert-log path (`--alert-log %h/agent-work/modes/ALERTS.log`) agree. The guide omits the timer accuracy, the host-dir value, and `--state`, `--backups`, `--seen`, `--writer` and `--model` in the scheduled invocation (`deploy/hass/hass-health.service:7`). |
| Clover report | No row in “What runs” (`:7–16`). | `report --all --host …` (`deploy/hass/hass-clover-report.service:7`); `OnCalendar=*-*-* 06:00 America/Los_Angeles`, `Persistent=true` (`deploy/hass/hass-clover-report.timer:5–6`). Missing from this guide, not contradicted. `docs/hass/CLOVER.md:19,54–56` gives the script command and calls this an uninstalled template at “06:00 America/Los_Angeles, persistent across missed runs.” |
| Clover sync | No row in “What runs” (`:7–16`); the Clover chat note at `:63` is not a timer entry. | `sync --host …` plus `ExecStartPost=…hass/stock_site.py run --host …` (`deploy/hass/hass-clover-sync.service:8–9`). `OnCalendar=*:0/15`, `RandomizedDelaySec=60`, `AccuracySec=30s`, `Persistent=true` (`deploy/hass/hass-clover-sync.timer:5–8`). Missing from this guide, not contradicted. `docs/hass/CLOVER.md:91–96,347–349,399–403` separately describes the post-step, the built 15-minute full sync, and the operator entry point. Its earlier incremental/nightly design (`:340–341`) is not the schedule in these templates. |

R1 gives the full paths and flags behind the abbreviated quotes. “All four” (`docs/hass/OPERATIONS.md:16`) fits the four services listed there, not the six templates in `deploy/hass/`. Both Clover services also set `UMask=0077`, `NoNewPrivileges=true` and `PrivateTmp=true` (`deploy/hass/hass-clover-report.service:9–11`, `deploy/hass/hass-clover-sync.service:13–15`). The nightly self-test mentioned at `docs/hass/OPERATIONS.md:133–134` is a separate candidate outside `deploy/hass/`, not a fifth timer in the inventory. `docs/hass/RUNTIME-RELEASE.md:23–24,54–60,69–70` excludes Clover activation, describes receiver/worker/health as the three switched units, and leaves the backup timer alone. `scripts/hass/install_launchagent.py:1–2,66–74,87–98` compares plist copies and a forwarder argument; it is not a systemd launcher or a competing schedule source.

## R4. Ranked gaps and one possible follow-up

1. **Largest gap — two Clover pairs and the sync post-step are missing from the main operations inventory.** An operator using only that table would not see the 06:00 report or 15-minute cache sync, or that sync invokes a separate stock-site program (R3, Clover rows). Link to the dedicated Clover guide and distinguish templates from installed status; this is not an enablement recommendation.
2. **Smaller gap — the core summary is not a complete command reference.** The health row leaves out five script flags and its 30-second timer accuracy; the backup and host rows omit private-path arguments shown as template strings in R1. Nothing in the checked guide gives a conflicting path, daily time or cadence for those four services (R3, core rows).
3. **No broken source wiring found.** All target files, command arguments and timer/service links checked here resolve at the pinned source revision (R1–R2). Installed bytes, runtime/config validation and actual activation times were not checked.

**One proposed follow-up (estimate: 60–90 minutes, not built here):** Add a compact complete template inventory to `docs/hass/OPERATIONS.md`, and an offline check at `hass/tests/test_operations_unit_inventory.py`. `python3 -B -m unittest hass.tests.test_operations_unit_inventory -v` would parse only checked-in `[Service]` and `[Timer]` sections and compare the documented unit names, timer targets and literal timing directives to them. Exercise the unchanged templates and in-memory negatives for a missing Clover row, altered calendar value and orphan timer. A stale or missing row must fail, without importing or running Hass. This would not duplicate `scripts/hass/units_template_parity.py:47–81,101–114`, which compares installed-copy bytes against Git blobs, not template fields against the guide. No service or timer edit is proposed.

### Reproduce offline

From a checkout of the pinned main with these blobs present (set `BASE` to the main SHA above; do not use a moving ref):

```sh
BASE=37feae1dc5efa6968f90d17a1eda6daed29afd4a
git diff --no-renames --name-status 1f8510907cb2989bb50391fde45d6211e4735879 "$BASE" -- deploy/hass hass/statebackup.py hass/health.py hass/host.py hass/clover/cli.py hass/stock_site.py docs/hass/OPERATIONS.md docs/hass/RUNTIME-RELEASE.md docs/hass/CLOVER.md scripts/hass/install_launchagent.py scripts/hass/units_template_parity.py hass/tests/test_units_template_parity.py reports/audit-1121
git ls-tree -r "$BASE" -- deploy/hass hass/statebackup.py hass/health.py hass/host.py hass/clover/cli.py hass/stock_site.py
git grep -nE '^\[Timer\]|^\[Install\]|^(Description|Type|WorkingDirectory|ExecStart(Post)?|Unit|OnCalendar|Persistent|AccuracySec|RandomizedDelaySec|Restart|WantedBy)=' "$BASE" -- deploy/hass
git grep -nE 'add_(argument|parser)|parse_args|"create"|"sync"|"serve"|"work"|for flag' "$BASE" -- hass/statebackup.py hass/health.py hass/host.py hass/clover/cli.py hass/stock_site.py
git grep -nEi 'what runs|clover|timer|runtime worktree|host\.py|host\.json|health\.py|statebackup\.py|all four|ALERTS\.log' "$BASE" -- docs/hass/OPERATIONS.md
```

On 2026-11-21 a scratch probe on Python 3.12.3 also parsed the ten INI-style files with interpolation off, split the seven command lines, resolved same-basename timers, and passed the literal script arguments to the reviewed `argparse` setup from the five target files. Output: `PASS: 6 services, 4 timers, 7 command lines accepted` (exit 0). Only the parser setup ran; the probe did not import the application modules, expand `%h`, call any command handler, read live inputs, contact any runtime endpoint or start anything. This is not a native systemd or runtime smoke test.
