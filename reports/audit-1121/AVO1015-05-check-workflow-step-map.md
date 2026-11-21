# AVO1015-05: What `check` runs

| Job | `pull_request` (not draft) | `push` to `main` | `schedule` | `workflow_dispatch` | Source |
|---|---|---|---|---|---|
| `quick` | Pillow version test, Hass plan, Python syntax, commerce unit tests; also runs the selected Hass modules **only** on the affected tier | Same checks and plan, no Hass test execution here | Same as main push | Same as main push | W:62–136 |
| `hass` (`hass shard N`) | Only if `quick` succeeds with a full plan; one job per shard | Full plan, one job per shard after `quick` succeeds | Same as main push | Same as main push | W:138–196; H:334–372 |
| `site` | Catalog + community QA, then published static-site QA in the **same job** | Same | Same | Same | W:198–267 |
| `check` | Waits for `quick`, `hass`, `site`; verifies results and Hass receipts, not the tests themselves | Same | Same | Same | W:269–300; H:495–584 |

**Source:** `tidepool-labs/avocado-shack` `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, read 2026-11-21 UTC. `W` = `.github/workflows/check.yml`; `H` = `hass/tests/ci_shards.py`; `A` = `.github/actions/test-env/action.yml`; `P` = `.github/actions/test-env/install-playwright.sh`. The cited workflow, composite action, planner, weights and commerce manifest did not change from the requested baseline `1f8510907cb2989bb50391fde45d6211e4735879`. The full-tree name diff showed only three additions each under `hass/tests/` and `scripts/hass/`: the test inventory grew, but the selection and execution rule did not. See the read-only commands below.

## R1. Events, conditions and commands

W:26–33 triggers on PR opened, synchronize, reopened, ready-for-review and converted-to-draft; push only to `main`; nightly `23 10 * * *` (10:23 UTC); and manual dispatch (no ref filter in YAML). All four jobs skip on draft PRs (W:64,141,200,276). The nightly gets a separate concurrency group; `cancel-in-progress` is true only for PRs (W:38–45). All jobs request `ubuntu-latest` (W:65,142,201,277).

On non-PR events the Hass tier is always `full`. For PRs, selection uses the diff from `HEAD^1` to `HEAD` (renames count as two paths) and follows imports and code references to determine which tests can reach the changed files. Changes under `.github/`, non-test infrastructure under `hass/tests/`, `hass/__init__.py`, `hass/ops/`, `hass/content/`, `hass/templates/` or `package-lock.json` force `full`; so do a shared Hass or `scripts/hass/` Python file reached by more than half the modules, an unreached `hass/` path, an otherwise unknown unmapped path, or an unavailable mapping. Unreached paths in known areas and Markdown do not by themselves force `full`. An affected plan always adds the shard smoke and tracked-private tests (the latter if present), then switches to `full` if the estimated selection exceeds 480 seconds. Shard count is `vars.HASS_SHARD_JOBS` or 4, clamped to 1–8 and no greater than the module count (W:52–55,75,95–97; H:8–27,53–67,111–120,278–372).

Read each job's rows in order. Unless stated otherwise, a step requires previous steps to succeed. “All” means all four event columns in the summary, excluding draft PRs. This inventories the workflow's `uses:` and `run:` steps and expands the repository-owned setup action; it does not expand external GitHub actions into their implementation internals.

| Job | Event / additional condition | Actions and shell commands, in order | Source |
|---|---|---|---|
| `quick` | All | `actions/checkout@v4` (no credential persistence, depth 2); `actions/setup-python@v5` (3.12); `actions/setup-node@v4` (22) | W:72–83 |
| `quick` | All | `dir="$RUNNER_TEMP/pillow"`; `python3 -m pip install --quiet --disable-pip-version-check --no-input --only-binary=:all: --target "$dir" "Pillow==$PILLOW_VERSION"`; `echo "PYTHONPATH=$dir" >> "$GITHUB_ENV"` | W:85–89 |
| `quick` | All | `python3 -m unittest discover -s tests -p test_pillow_ci.py -v`; `python3 hass/tests/ci_shards.py plan --event "$GITHUB_EVENT_NAME" --base HEAD^1 --shards "$HASS_SHARD_JOBS"` (step `plan`, exports `plan`, `tier`, `shards`) | W:67–70,91–97; H:390–413 |
| `quick` | All | `python3 -m compileall -q storefront-mockup reports/hermes-handoff`; set `tests` from `ls commerce/gateway/*.test.mjs` piped through `grep -v '/owner-photo\.test\.mjs$'`; `node --test $tests` | W:99–107 |
| `quick` | Affected PR only | `./.github/actions/test-env` (expanded below); with `HASS_PLAN` from step `plan`, `python3 -u hass/tests/ci_shards.py run --shard quick --record-dir "$RUNNER_TEMP/hass-records"` | W:109–116 |
| `quick` | Affected PR only; JSON `always()`, log `failure()` | `actions/upload-artifact@v4`: `hass-record-quick` from `$RUNNER_TEMP/hass-records/*.json`, then `hass-log-quick` from `*.log`. Both retain one day and ignore no matches | W:118–132 |
| `quick` | All, `always()` | Cleanup below | W:134–136 |
| `hass` | Full PR, main push, schedule, dispatch; successful `quick` with `tier == 'full'` | Matrix from `fromJSON(needs.quick.outputs.shards \|\| '["0"]')`, `fail-fast: false`. Per leg: `actions/checkout@v4` (no credential persistence, default depth); `actions/setup-python@v5` (3.12); `actions/setup-node@v4` (22); `./.github/actions/test-env` | W:138–162 |
| `hass` | Each admitted leg | Same Pillow install block as `quick` (W:87–89), without the separate pin test; with `HASS_PLAN` from `quick` and `SHARD` from the matrix, `python3 -u hass/tests/ci_shards.py run --shard "$SHARD" --record-dir "$RUNNER_TEMP/hass-records"` | W:164–176 |
| `hass` | Each leg; JSON `always()`, log `failure()` | `actions/upload-artifact@v4`: `hass-record-${{ matrix.shard }}` from `$RUNNER_TEMP/hass-records/*.json`, then `hass-log-${{ matrix.shard }}` from `*.log`. Both retain one day and ignore no matches | W:178–192 |
| `hass` | Each leg, `always()` | Cleanup below | W:194–196 |
| `site` | All | `actions/checkout@v4` (no credential persistence, default depth); `actions/setup-python@v5` (3.12); `actions/setup-node@v4` (22); `./.github/actions/test-env` as step `site-env` | W:198–218 |
| `site` | All; normal success condition | Catalog + community shell block below | W:226–250 |
| `site` | All; `!cancelled()` and `site-env.outcome == 'success'`, even after a catalog/community failure | Static shell block below | W:252–263 |
| `site` | All, `always()` | Cleanup below | W:265–267 |
| `check` | All, after dependencies finish, if `!cancelled()`; not gated on their success | `actions/checkout@v4` (no credential persistence, depth 2); `actions/setup-python@v5` (3.12); `actions/download-artifact@v4` (pattern `hass-*`, merge into `$RUNNER_TEMP/hass-records`, `continue-on-error: true`); with `HASS_PLAN` from `quick` and `HASS_NEEDS` set to `toJSON(needs)`, `python3 hass/tests/ci_shards.py verify --record-dir "$RUNNER_TEMP/hass-records" --base HEAD^1 --shards "$HASS_SHARD_JOBS"` | W:273–300 |

| Block | Commands and conditions | Source |
|---|---|---|
| Test environment: Playwright | `bash "$GITHUB_ACTION_PATH/install-playwright.sh"`. With `set -euo pipefail`, validate `PLAYWRIGHT_VERSION` (bad value: `echo` and `exit 2`); `mkdir -p "$root"`; `exec 9>"$root/.lock"`; `flock -w 900 9` (timeout: `echo` and `exit 1`). If `.ready` exists, print reuse; otherwise `rm -rf "$prefix"`, `mkdir -p "$prefix"`, `npm install --prefix "$prefix" --no-save --no-audit --no-fund "playwright@$version"`, `PLAYWRIGHT_BROWSERS_PATH="$browsers" "$prefix/node_modules/.bin/playwright" install chromium`, `touch "$prefix/.ready"`, and print installed. `flock -u 9`; require exactly one executable headless shell (otherwise `echo` and `exit 1`); print the module and shell and, when `GITHUB_ENV` exists, append `PLAYWRIGHT_MODULE`, `PLAYWRIGHT_BROWSERS_PATH` and `CHROMIUM_PATH` via `echo`. | A:14–16; P:22–58 |
| Test environment: libraries and smoke | `"$PLAYWRIGHT_MODULE/../.bin/playwright" install-deps chromium` only when `runner.environment == 'github-hosted'`; then `node -e "require(process.env.PLAYWRIGHT_MODULE).chromium.launch().then(b => b.close())"` | A:18–30 |
| Test environment: temp | Use `/dev/shm` if present and writable, else `$RUNNER_TEMP`; best-effort `find "$base" -maxdepth 1 -name 'avo-ci-*' -user "$(id -u)" -mmin +720 -exec rm -rf {} + 2>/dev/null \|\| true`; `dir="$(mktemp -d "$base/avo-ci-${GITHUB_RUN_ID}-${GITHUB_JOB}-XXXXXX")"`; `echo` `TMPDIR` and `AVO_CI_TMPDIR` into `$GITHUB_ENV` and print `TMPDIR`. | A:37–46 |
| Site: catalog + community | Export `TMPDIR` from `mktemp -d "${AVO_CI_TMPDIR:?}/community.XXXXXX"` and `QA_OUT_DIR="$TMPDIR/qa"`; `mkdir -p "$QA_OUT_DIR"`. Set `log="$TMPDIR/server.log"`; background `AVOSHACK_COMMUNITY_DB="$TMPDIR/site.sqlite3" python3 -u storefront-mockup/community-server.py --port 0` with log redirection; capture `$!` and `trap 'kill "$server_pid" 2>/dev/null \|\| true' EXIT`. Poll with `seq 1 100`, `grep` for a loopback URL in the log, `head -1`, `grep` for the port, `tr -d /`, `kill -0`, and `sleep 0.1`; stop once the port is found or the server dies. No port: `echo`, `cat "$log"`, `exit 1`. Export and print `PREVIEW_URL`; `curl -fsS --max-time 10 "$PREVIEW_URL/" >/dev/null`; `kill -0 "$server_pid"` (if dead, `cat "$log"` and `exit 1`); `node storefront-mockup/catalog-only-qa.cjs`; `python3 storefront-mockup/community-qa.py` (also invokes Node on `community-ui-qa.cjs` using a separate loopback fixture server). | W:226–250; `storefront-mockup/community-qa.py:21–36,128–133` |
| Site: static | Export `TMPDIR` from `mktemp -d "${AVO_CI_TMPDIR:?}/static.XXXXXX"` and `QA_OUT_DIR="$TMPDIR/qa"`; `mkdir -p "$QA_OUT_DIR"`; `site="$(mktemp -d "$TMPDIR/published-site.XXXXXX")"`; `python3 hass/sitegen.py --publish "$site"`; `node storefront-mockup/static-site-qa.cjs "$site"`. This builds a local copy for QA; it does not deploy. | W:252–263; `storefront-mockup/static-site-qa.cjs:1–15,40–42` |
| Cleanup | `if [ -n "${AVO_CI_TMPDIR:-}" ]; then rm -rf "$AVO_CI_TMPDIR"; fi` | W:134–136,194–196,265–267 |

## R2. What runs more than once on the same event

| Event / scope | Finding | Evidence |
|---|---|---|
| Each eligible event, one workflow attempt | **No whole-suite duplicate at the workflow level.** Affected PRs run Hass tests in `quick` only; full runs use disjoint shard lists, never the affected step as well. `plan` loads and counts tests (on full it also counts discovery), `verify` recomputes selection and checks receipts, and only `run` executes the planned unittest cases. | W:95–97,109–116,138–148,172–176,296–300; H:111–136,329–331,390–413,460–491,495–584 |
| Each eligible event, commerce and Pillow | The historical commerce manifest's `/scripts/test` would run an overlapping superset, but `npm test` is **not** called here. `quick` runs 20 of the 21 tracked gateway test files, excluding `owner-photo.test.mjs`. Pillow's version test runs once in `quick`, outside the `hass/tests` inventory; on full runs the wheel install repeats in each shard, not the version test. | `commerce/package.json:5–9`; W:85–107,164–176; H:50–52,76–90; `git ls-files` below |
| Each eligible event, browser setup | The **same Chromium launch/close smoke command** runs in `site` and again in `quick` on affected PRs or in **each** `hass` leg on full runs. That is two launches on an affected PR and five on a default four-shard full run, if all setup succeeds. Playwright setup also repeats across those jobs; this is not a repeat of their functional browser suites. | W:55,109–110,138–162,217–218; A:14–30 |
| Full events, plus affected PRs selecting `test_qa_env` | `test_qa_env` invokes `catalog-only-qa.cjs`, `community-qa.py`, and `community-ui-qa.cjs` entry points that `site` also uses. In Hass's test they must **refuse** invalid preview/output settings before starting a browser or server. These are shared entry points, not a second successful functional suite. | H:278–372; `hass/tests/test_qa_env.py:1–14,22–60,170–176`; W:249–250; `storefront-mockup/community-qa.py:128–129` |
| Each eligible event, functional site coverage | Some assertions cover the same behavior on different surfaces. For example, catalog and static QA both check for no commerce surface and a packaged-goods default; community UI and static QA both check sample invitation and journal rendering. The site blocks run different commands against a community-backed preview and the local published build, respectively; neither runs the other's suite. | `storefront-mockup/catalog-only-qa.cjs:8–12,560–580`; `storefront-mockup/community-ui-qa.cjs:164–187`; `storefront-mockup/static-site-qa.cjs:59–108`; W:226–263 |

This is not a census of equivalent individual assertions inside the test bodies. In particular, the serial-vs-parallel discovery test intentionally runs the same **synthetic** fixture in both modes, not the checkout's Hass suite (`hass/tests/test_run_parallel.py:13–46`). At the pinned tree `git ls-tree` lists only `.github/workflows/check.yml` under `.github/workflows`, so no second checked-in workflow runs any of these sets. PR and subsequent main checks are separate events, as are nightly and dispatch (W:26–33).

## R3. Network, pins, secrets and failure paths

For a non-draft, non-cancelled run, `check` expects `quick` and `site` to be successful and `hass` to be successful on full or skipped on affected. A missing/invalid plan fails before result comparison. Otherwise `verify` compares plan/actual shard lists, coverage, record status and total test count and prints available failing shard logs. A draft PR or cancelled workflow has no guaranteed aggregate verdict; the job is gated out or can be cancelled (W:273–300; H:495–584).

| Step / dependency | Network, pin or credential | If it fails |
|---|---|---|
| Hosted action resolution and checkout (all jobs) | GitHub supplies version-tagged actions and the checkout fetches the repo. It uses the Actions-provided `GITHUB_TOKEN` by default; `contents: read`, `persist-credentials: false`, no custom token. | In `quick`: no plan, so `hass` skips and `check` fails if it reaches `verify`. In `hass` or `site`: bad job result, so `check` fails. In `check`: that job fails directly before verification. W:35–37,72–75,138–152,198–207,273–283; H:499–504,546–552. |
| Python 3.12 in all jobs; Node 22 in `quick`, `hass`, `site` | Setup actions can use the runner tool cache or fetch a matching runtime on a miss. These select version series, not exact patch versions; the action refs are major tags, not commit hashes. | Same job-specific effects as checkout. W:77–83,154–160,209–215,285–287; H:499–504,546–552. |
| Pillow in `quick` and `hass` | `pip install` may fetch the exact `12.0.0` wheel from its configured package index; binaries only. The subsequent pin proof is in `quick`. | In `quick`, install or pin proof failure prevents the plan; `check` fails for no plan. In a shard, install failure prevents tests; `check` fails on the shard job result and missing receipt. W:49–51,85–97,164–184; H:499–504,519–523,546–552. |
| Playwright npm package and Chromium in test-env | Exact `PLAYWRIGHT_VERSION` `1.64.1` from npm; the matching Chromium comes via Playwright's browser download. Only the installer cold path downloads; the ready marker is local to a host/version, not a shared Actions cache. | A failed install, lock, or missing shell fails setup. In affected `quick` or a shard: the plan exists but the test receipt is missing and the job fails. In `site`: **both** QA blocks skip after setup failure and `check` rejects `site`. W:48,109–124,162–184,217–228,253–263; P:22–48; H:499–504,519–523. |
| Hosted Chromium system libraries and launch proof | `install-deps chromium` uses the hosted OS package manager and its mirrors; no individual library version is pinned here. Launch/close and temp setup are local, not downloads. | A library, launch or temp allocation failure has the same test-env failure path as above; the stale-directory sweep is best effort and ignored if it alone fails. A:18–46; W:109–116,162–176,217–228,253–263; H:499–504,519–523. |
| JSON and failure-log uploads | `upload-artifact@v4` uses GitHub's run-scoped artifact service; the workflow supplies no custom secret. | An upload error is not continued: `quick` or `hass` is unsuccessful and `check` fails. No matching files is intentionally ignored by the uploader; missing expected JSON still fails `verify`. Failure logs are diagnostic, not required evidence, but an actual log-upload error is not suppressed. W:118–132,178–192; H:499–504,519–523,563–580. |
| Rollup artifact download | `download-artifact@v4` uses the same run's GitHub artifact service, with no custom token. | Download error alone is tolerated; `verify` still runs. Missing or unreadable required JSON, mismatched or failed records, coverage/count problems or a bad dependency make `check` red. If all required readable records and successful results are present, a missing diagnostic log alone does not fail it. W:289–300; H:495–584. |
| Local site HTTP | `curl` and the QA clients use loopback; catalog/community use temporary databases and static QA serves the temporary build. These are not external site requests or a deploy step. | Catalog/community failure makes `site` fail, but static QA still runs if setup succeeded and the run is not cancelled. Static failure also makes `site` fail. Either makes `check` fail. W:220–267; `storefront-mockup/community-qa.py:21–36`; `storefront-mockup/static-site-qa.cjs:21–42`; H:499–504. |

No repository or deployment secret is referenced by the workflow or local setup action. The GitHub runtime credentials above are distinct from configured secrets; `$HASS_PLAN`, `$HASS_NEEDS`, the pin variables and `vars.HASS_SHARD_JOBS` are not secrets (W:35–37,47–55,71–300; A:14–46; P:20–58). No credential or value was inspected.

## R4. Recorded time, not timeouts

| Job | Time evidence | Configured timeout |
|---|---|---|
| `quick` | No measured job duration recorded in W or the weights. “Allow up to eight measured minutes in quick” refers to the affected **selection budget**, not job wall time (H:56–58,355–362). | 20 min (W:66) |
| `hass shard N` | W:52–54 says “~1150 s of measured module time” and “4 shards are ~290 s each”; those are historical sizing figures. W:143 separately records “Hosted shard jobs reached 30:16 at the old limit.” Current four-way **estimated module loads** are 971 seconds each (3,884 seconds total), not observed hosted wall time. The offline inventory/partition check on 2026-11-21 found 901 modules, 659 weight entries and loads `[971, 971, 971, 971]`, using the planner's 3-second fallback for unmeasured modules (H:53–56,76–120,375–379; `hass/tests/ci_weights.json:/seconds`). | 46 min per leg (W:143–148) |
| `site` | “Measured inside the old single job: catalog + community 5.7 min, static site 3.8 min.” Those are historical step times, not a current `site` job measurement (W:198–203). | 30 min (W:203) |
| `check` | No measured job duration recorded in W or the weights. It waits for its dependencies, then runs checkout, Python setup, download and verification (W:273–300). | 10 min (W:278) |

`hass/tests/ci_weights.json:/measured` says “wall seconds rounded up; used only to balance shards (a missing or stale entry changes balance, never coverage)” and identifies a 2026-11-06 host measurement plus 2026-11-16 additions drawn from a main full-tier run. The composite action's “160 s with TMPDIR on /dev/shm” used six modules at a time on the old host, not today's hosted shard jobs (A:32–36). The “one 23-minute job” in W:7 is also historical, not an estimate for any present job.

**No build unit proposed.** The duplicate launch is a per-runner setup proof, not a repeated functional suite (A:18–30; W:57–60). The historic timing comments do not establish a current job bottleneck; this audit did not time hosted jobs.

### Read-only reproduction

Run from the repo with the pinned source at `origin/main`, or substitute the pinned SHA for `origin/main`. The source diff and workflow inventory were read on 2026-11-21 UTC. The weights check called only `all_modules`, `load_weights`, `partition`, `union_proof` and `weight` from H:76–136 with shard count 4; it did not import or execute test modules. No workflow, browser suite, live service, installation or network-based timing check was run for this audit.

```sh
git rev-parse origin/main
git diff --name-status 1f8510907cb2989bb50391fde45d6211e4735879 origin/main
git diff --name-status 1f8510907cb2989bb50391fde45d6211e4735879 origin/main -- .github hass/tests/ci_shards.py hass/tests/ci_weights.json commerce/package.json reports/audit-1121
git ls-tree -r --name-only origin/main .github/workflows
git ls-files 'commerce/gateway/*.test.mjs' 'tests/test_pillow_ci.py'
git grep -n -E 'catalog-only-qa|community-qa\.py|community-ui-qa|static-site-qa|test_pillow_ci|node --test' origin/main -- .github hass/tests storefront-mockup/community-qa.py
git grep -n -E 'secrets\.|token:|npm (ci|install)|pip install' origin/main -- .github/workflows .github/actions
git show origin/main:.github/workflows/check.yml | nl -ba
git show origin/main:.github/actions/test-env/action.yml | nl -ba
git show origin/main:.github/actions/test-env/install-playwright.sh | nl -ba
git show origin/main:hass/tests/ci_shards.py | nl -ba
git show origin/main:hass/tests/ci_weights.json | nl -ba
```
