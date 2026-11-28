#!/usr/bin/env bash
# Offline fast check; does not replace required CI.
# Install Ruff and the CI-pinned Pillow version locally. Use the Node version,
# Playwright module and Chromium from the check workflow's test environment.
# Commerce TypeScript checks are not part of this local gate.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

: "${PLAYWRIGHT_MODULE:?Set PLAYWRIGHT_MODULE to the absolute path to the installed Playwright module}"
ruff check --no-cache --select E9,F63,F7,F82 hass/

# A missing or failing test is nonzero; unittest otherwise treats skips as
# success. Require exactly four executed cases and no skips or expected failures.
tests=(
  hass.tests.test_status_pause.PauseTests.test_pause_blocks_apply_until_resume_and_survives_restart
  hass.tests.test_photo_draft.PhotoDraftTests.test_photo_opens_one_needs_details_draft_and_stores_the_original_once
  hass.tests.test_unknown_approval_code.UnknownCodeTestCase.test_unknown_code_never_approves_or_cancels
  hass.tests.test_publish_csp.BrowserPolicy.test_pages_work_under_the_policy_and_it_blocks_injected_execution_and_foreign_resources
)
if ! output=$(python3 -B -m unittest -v "${tests[@]}" 2>&1); then
  printf '%s\n' "$output" >&2
  exit 1
fi
printf '%s\n' "$output"
if ! grep -Eq '^Ran 4 tests in ' <<< "$output" || ! grep -Fxq 'OK' <<< "$output"; then
  printf '%s\n' 'Fast check requires exactly four passing tests (no skips).' >&2
  exit 1
fi
