# NPP weekly review: runbook

This page lists the commands for the Monday learning loop of the Hass new-product pipeline (design section 4c).
The skill at `docs/hass/skills/hass-npp-review/SKILL.md` says what counts as a finding and how to redact one. This
page only puts the tools in order. It creates no timer. Run it when Astra opens the weekly card on Monday.

## Who

- **local-worker** (local model) runs steps one to four. Only this lane reads private transcripts and receipts.
- **A builder** (the lane the weekly card names) runs steps five and six, one defect at a time.
- **codex-reviewer** checks each fix PR at its exact head. Merging follows the standing approval.

## Placeholders

- `<state-dir>`: the Hass state directory, which holds the private transcript store.
- `<media-root>`: the Hass media root. Job receipts are in `<media-root>/npp/<job-id>/receipt.json`.
- `<private-dir>`: a directory the operator names. It is outside every Git worktree and only the Hass host account can read it.
- `<ledger>`: the operator's private findings file. Use the same path every week, outside Git.
- `<since>`: last Monday's date as `YYYY-MM-DD`. `<week>`: that week as `YYYY-Www`. `<this-week>`: the current week.

## Steps

**One. Export last week's transcript** (read-only, JSONL to standard output):

```
python3 -B hass/transcript.py export --state <state-dir> --since <since> > <private-dir>/transcript.jsonl
```

**Two. Turn it and the receipts into redacted review rows:**

```
python3 -B scripts/hass/npp_review_export.py --export <private-dir>/transcript.jsonl --receipts <media-root>/npp --since <since> --out <private-dir>/review.jsonl
```

You should see `PASS npp_review_export <n> events <n> jobs`. A `NOTE bad-receipt <job-id>` line counts as a finding.
On any `FAIL` line, stop and report it on the card. Never hand-edit the inputs. To re-run over an existing file, add `--force`.

**Three. Read.** Follow the skill: read the metrics trend first, then `review.jsonl`. Note every owner edit, fallback,
question, "no", slow job and low judge score, and name the stage of each. The tool has already replaced numbers, money,
contacts and addresses. Check every summary again before you write it down.

**Four. Record each finding** (one redacted line: no digits, no `@`, no `$`):

```
python3 -B scripts/hass/npp_findings.py --ledger <ledger> add --week <week> --stage S<n> --class <failure-class> --summary "<redacted summary>"
```

The tool prints the finding id `F-<week>-<n>`. If the class already has a closed finding, the new row is saved as
`repeat`, which is a repeat incident. Post each id with its stage, class and redacted summary on the weekly card, then
hand the card to the builder.

**Five. Builder: one failing case for each real defect.** Run this in a worktree made from current `origin/main`:

```
python3 -B scripts/hass/npp_case_new.py --cases hass/tests/npp/cases --day <YYYY-MM-DD> --slug <short-words> --path listing --title "<synthetic title>"
```

`--day` is the day the failure happened. `--path` is `listing`, `question` or `contract`, and the tool prints `PASS npp_case_new <case-file>`. Replace every
TODO with synthetic turns and the expected state. Use no real price, cost, quantity, name, message text or photo of a
person. Show the case failing, fix the asset or code, and show the case passing. Then open one fix PR with the case and the
fix together, sign off every commit with `git commit -s`, and name the finding id and codex-reviewer on the fix card.

**Six. Close the finding** once its case file exists and the fix card is open. A chat note never closes a finding.

```
python3 -B scripts/hass/npp_findings.py --ledger <ledger> close F-<week>-<n> --case <case-file> --card <card-id>
python3 -B scripts/hass/npp_findings.py --ledger <ledger> close F-<week>-<n> --reason <reason-slug> --card <card-id>
```

Use the `--reason` form only when there is no defect, for example `--reason not-a-defect`.

**Seven. Weekly check, last:**

```
python3 -B scripts/hass/npp_findings.py --ledger <ledger> report --week <this-week>
```

`PASS npp_findings` closes the week. `FAIL npp_findings stale` means a finding has been open for more than two weeks.
Name it on the weekly card for Astra.

## What never leaves the host

- The transcript export, `review.jsonl`, receipts, photos, the findings ledger and the private metrics file stay on the host.
- None of the following go into Git, a PR, an alert, a chat or a cloud-model prompt: raw message text, prices, costs,
  quantities, names, phone numbers, emails, addresses, chat or sender ids, or real paths.
- Only these leave the host: finding ids, stages, classes and redacted summaries on the card, plus synthetic case files and the fix in the PR.
