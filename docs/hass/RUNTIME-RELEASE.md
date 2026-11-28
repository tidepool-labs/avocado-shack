# One-command Hass runtime release (AVB-04)

**The script is not a deployment, and it is not live proof.** An attended operator can
move the detached runtime and its matching host pin together, or automatically put
both back after a failed move. Without `--apply --attended` it prints a plan using
Git metadata only: no host/config reads, service calls or writes.

## Before the operator runs it

- Use an independently reviewed, stable tools checkout **outside the live runtime**.
  Invoke it with the Hass venv Python; do not install it into `~/agent-work/bin`.
- Obtain the existing attended release approval and ask G to stay off the chat.
  Flags acknowledge that approval; they do not create it. Workers never run apply.
- Choose an exact, independently reviewed and CI-green merged-main commit. Fetch
  main separately and confirm that commit is on it. The script checks local
  `origin/main` ancestry, not GitHub approval/CI freshness; it never fetches or merges.
- Record the current full detached runtime SHA. Both SHAs must be 40 lowercase
  hex characters; abbreviated IDs, symbolic refs and no-op moves are refused.
- The old runtime must be clean, correctly pinned, healthy, inbox clear, services
  and backup timer active, with zero receiver/worker restarts. **No pre-existing
  self-test failure is waived.** AVB-03's recorded `relay-stuck` failure must clear
  before a move with this script. Its pending phone check remains a separate gate.
- No state/schema migration, new service, unit edit, interpreter change, Clover
  activation, token, publishing or Mac-forwarder upgrade is included. Do not use
  this tool for a target requiring incompatible persistent-state changes: rollback
  restores code/config, **not** databases or actions processed after services start.

## One command

Replace `TOOLS`, `OLD40`, and `TARGET40` below with the stable tools checkout path
and the two full SHAs. Default host/runtime/state paths are the AVB-03 paths.

```text
~/.local/share/hass/venv/bin/python3 -B TOOLS/hass/runtime_release.py --expected-old OLD40 --target TARGET40 --apply --attended
```

Omit `--apply --attended` for the metadata-only plan. Apply requires an interactive
terminal. `--runtime`, `--host`, `--state-root`, `--python` and `--receipts` are explicit
path overrides, intended for isolated fixtures or an operator-confirmed layout;
never point tests at live paths. Path overrides do not grant release authority.

## What happens

1. Verify the clean detached runtime and target ancestry. Acquire a nonblocking
   per-runtime lock in Git metadata, independent of the receipt path. A pending
   interrupted move refuses a new move, even with a different receipt directory.
2. Privately validate the host file and matching pin. Run the existing host check
   and live self-test (no model test). No host values or child-command output are
   printed. The existing host checker may validate the installed key; the release
   tool itself never opens, copies, changes or prints any credential file.
3. Make a separate detached staging worktree. Run `hass/acceptance.py` and
   `hass/tests/run_parallel.py` with the service interpreter. Any nonzero result
   stops before downtime; AVB-03's parallel-only failures are not excused/retried.
4. Run the existing backup oneshot and require `Result=success`. Save the original
   host bytes as a private 0600 `host.before`. No state/database copy is restored.
5. Record recovery metadata **before** stopping health timer, worker and receiver.
   Verify all inactive and health service idle. Recheck runtime and unchanged host.
6. Switch the runtime, atomically change **only** `runtimeCommit` semantically,
   run the host check, start receiver/worker/health timer, wait 30 seconds, and
   require active services, zero restarts, a passing live self-test, and clean HEAD.
7. On failure or SIGINT/SIGTERM after stopping begins: verify stopped, restore old
   detached HEAD and exact host bytes, validate, start and self-test again. A dirty
   checkout, unexpected HEAD or externally edited host is never overwritten.

Staging (`acceptance.py` + `run_parallel.py`) has its own shared 5400-second budget
(`STAGING_BUDGET_SECONDS`), with no retries or timeout override flag. The value is
at least 1.5 times a completed passing on-host rehearsal of both phases (service
interpreter, Node 22, nothing else running): acceptance 971 s plus
run_parallel 1944 s = 2915 s (2026-11-27; 1.5x = 4373 s). The old 1800-second cap refused that
run before backup. Run the release from a terminal whose `node` is v22; a Node 18
`PATH` (for example a bare `systemd-run`) fails the renderer tests and refuses.
`run_parallel.py` gives every shard its own empty `TMPDIR`, as hosted CI does, so
tests that inspect the temporary directory cannot see a sibling shard. The release
runs both staging phases with a `TMPDIR` it creates and owns; a timeout SIGKILLs
the children (so their own cleanup never runs) and the release then removes that
whole tree. Shard directories add only `/hpXXXXXXXX/N` to the path, and tests that
bind Unix sockets under `TMPDIR` bind a relative name, so a deep `TMPDIR` (for
example an agent scratch directory) cannot hit the ~107-byte socket path limit. The normal
work budget remains 900 seconds excluding those staging tests; switching only
starts with at least 180 seconds left of that budget. Recovery gets a separate 180 seconds plus
one bounded emergency-stop attempt. A timeout kills the whole child process group
before recovery. The backup timer is left alone; no units are installed/reloaded.

## Results and interrupted recovery

- Exit **0**: plan-only, or `RELEASE released`. Distinguish these explicitly.
- Exit **1**: refused before the move, or `RELEASE rolled-back`; read the phase.
- Exit **2**: `RELEASE rollback-failed`; an emergency stop was attempted, **not a
  promise that the stop succeeded**. The operator must inspect actual unit state.

Private receipts: `~/.local/state/hass-releases/run-*/receipt.json` contain only
phase, commit IDs, paths, elapsed seconds and a `witness`: the InvocationID of the
backup this run started, the boot ID and the monotonic time (microseconds) taken
after the host pin was replaced, and each service's InvocationID and monotonic
launch time. A launch not after the pin, or on another boot, rolls the move back;
readers compare on that one clock, never wall time. `host.before` is private config,
not a report attachment: never paste, commit or export it. Keep the same receipt
root. Staging cleanup is best-effort, never forced.

SIGKILL, power loss or a second interruption can prevent automatic recovery.
`runtime-release.pending` in `git rev-parse --absolute-git-dir` points to the private
run folder. A pending marker is a STOP, not permission to retry. The attended
operator verifies the receipt and original pin, stops all three units, confirms
inactive/health idle and a clean expected HEAD, checks out the receipt's old SHA,
restores that run's `host.before` with mode preserved, runs the existing host check,
then starts the three units and runs the live self-test. Preserve an externally
edited host for manual reconciliation; never restore over it blindly. Remove the
pending marker only after verified recovery. No automatic resume or retry exists.

## Evidence boundary

`python3 -B -m unittest hass.tests.test_runtime_release -v` exercises real temporary
Git checkouts and host-file writes with synthetic host data. Service/test boundaries
are simulated; subprocess failure/timeout and the plan CLI also execute for real.
These tests prove rollback mechanics, not live service behavior or a 15-minute move.
**The required second live move, its elapsed time, fail=0 self-test and G's phone
status check must be supplied by the attended operator before AVB-04 is accepted.**
