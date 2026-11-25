# Hass OFF install, backup, restore and rollback drill (finish line, offline)

**What this proves:** the OFF install path, the private state backup and the rollback all work on throwaway copies, with
numbers. **What it does not prove:** anything about the running service, the live host config, Clover or the website.
Nothing here starts, stops or reloads a service, touches the network or reads live state. Workers never run the live steps.

## Drill result (isolated sandbox, main `dd21b6cd`)

Driver: `finish/hass-listing/off-drill/off_drill.py` (agent-work, not in this repo; it only calls the repo tools below).
Run: `python3 -B off_drill.py <repo> <receipt-dir>`. One JSON receipt (0600) with counts, hashes and timings, no private text.
Result: **pass**, 0 service calls, 0 network calls.

| # | Stage | Tool | Result | Time |
|---|---|---|---|---|
| 1 | Refuse an already-enabled config | the drill's own check (`npp` or `photo_polish` true) | enabled config refused and left byte-identical; OFF config accepted | <0.01 s |
| 2 | Switch rehearsal: backup, edit, readback, rollback | `scripts/hass/install_rehearsal.py` | PASS backup, edit, readback, rollback | 0.04 s |
| 3 | Config rollback by bytes | `install_backup_receipt.py`, `install_rollback_proof.py pre` / `post` | backup receipt 0; `pre` accepts the candidate digest, **refuses a wrong digest**; after the restore `post` accepts the original digest; restored bytes equal the original (`4aecc1ef…f6c3`); switches OFF again | 0.08 s |
| 4 | State backup, verify, restore drill, diff | `hass/statebackup.py create` / `verify` / `drill` / `diff` | 17 files; verify ok; drill ok and **paused**, no health problems; 3 history entries; 14 transcript rows identical after restore; restored tree all 0700/0600; source state and writer worktree **unchanged**; backup outside the repo | create 0.86 s, verify 0.16 s, drill 0.24 s, diff 0.15 s |

The state in stage 4 is a real conversation in a throwaway repo (two changes, one undo, a history reply), not a live copy.

## Commands for the attended OFF install (operator, not workers)

Order and stop rules, using only existing tools:

1. Read the live host config once, privately. If any of `npp`, `photo_polish` is already `true`, **stop**: this is not an OFF install.
2. Make the backup copy beside it (mode 0600, parent directory 0700) and prove it:
   `python3 -B scripts/hass/install_backup_receipt.py --config <config> --backup <config.before> --owner-uid <uid>` must print `PASS install_backup_receipt` and the backup SHA-256. Record that digest.
3. State backup: `python3 hass/statebackup.py create --state <state-dir> --out <private-0700-dir>`, then `verify <backup>`, then `drill <backup> --into <new-dir> --worktree <drill-worktree>`. Require `result: ok` each time and a paused, problem-free drill.
4. After the attended change, record the candidate digest and run `python3 -B scripts/hass/install_rollback_proof.py pre --current <config> --candidate-sha <64 hex>`.
5. **Rollback:** copy `config.before` back over the config (the one attended write), then
   `python3 -B scripts/hass/install_rollback_proof.py post --restored <config-copy> --backup <config.before> --original-sha <64 hex>`. It checks bytes only; a service health check is separate (see [RUNTIME-RELEASE.md](RUNTIME-RELEASE.md)).
6. Never restore a state backup over an existing state directory; restore only into a new directory (statebackup refuses otherwise).

## Limits

- Byte checks and sandbox restores, not live service health or the real 15-minute window.
- Rollback restores config bytes, not databases or actions processed after services started (see RUNTIME-RELEASE.md).
- Timings are for a tiny fixture state; a real state with photos takes longer.
