# One OFF operator run: interrupted demo -> restore -> current preview -> one yes -> served check -> take-down -> resume

**What this is:** the order in which the person attending the OFF demo runs the shipped read-only commands after the demo
was interrupted (a crash, a restart or a moved machine) while a card was waiting for its `yes`. Each step names the
command, the only good answer, and what to do otherwise. Every command only reads; none of them sends a message, types a
`yes`, posts, takes down or touches Clover, the live site or a service. The owner (G or Mike) types the `yes` and `undo`
in the chat; the commands only tell you whether it is safe to.
**What it is not:** a live listing, the attended hidden TESTITEM proof or an authorization for either. Those stay with G
or Mike (`reports/goals/G-CARDS-READY.md`).
**Test:** `hass/tests/test_finish_off_operator_run.py` runs exactly this sequence as real commands on a synthetic
two-owner fixture (both cards delivered, no yes yet) and checks that every command left the restored state, transcript,
shop catalog and held photo byte-identical. The whole run takes a few seconds on the fixture; on a real OFF copy allow
about 10 minutes, most of it reading the card before the yes. `hass/tests/test_demo_resume_step.py` holds the
negative controls of the resume step (wrong chat, changed card bytes, served card edited, takedown proposed but not
approved, served state that contradicts a takedown).

Placeholders: `<backup>` a state backup folder (0700, outside the repo), `<state>` the restored state folder, `<media>`
the restored media folder, `<wt>` the shop worktree the OFF copy serves, `<job>` the listing's job code, `<photo>` the
photo file you hold for that listing, `<n>` the version number on the card you are looking at.

## 1. Before restoring: is the backup whole?

```
python3 -B scripts/hass/demo_restore_inventory.py <backup>
```

Good: `BACKUP ok items=<k> served-state=present`, then one `ITEM <job> <state> ...` line per listing. A listing that was
waiting shows `waiting-for-yes ... served=no`. `REFUSED <reason>` (for example `backup-not-intact` when any file of
the backup changed): stop, do not restore it; take the previous backup. `statebackup.py drill` refuses the same damaged
backup and creates nothing.

## 2. Restore on a paused OFF copy and resume

```
python3 hass/statebackup.py drill <backup> --into <new state folder> --worktree <wt> --media-into <media>
```

It prints one JSON line: require `"result": "ok"` and `"paused": true`. Never restore over an existing state folder. Then send `resume changes` in the
owner's chat (answer: resume).

## 3. What is next for this listing?

```
python3 -B scripts/hass/demo_resume_step.py --state <state> --media <media> --worktree <wt> --job <job> --photo <photo> --version <n>
```

| Answer | Next |
|---|---|
| `REVIEW_CURRENT_PREVIEW` | the card for version `<n>` is the delivered, current one and nothing is served yet: go to step 4 |
| `REVIEW_TAKEDOWN` | the approved card is what the shop serves: step 6 when you want it down |
| `NOT_SERVED` | that approved card is not served any more: do not post it again or repeat the take-down |
| `HOLD <reason>` | stop. `version-mismatch`: `<n>` is not the newest card; look at the newest card in the chat. Other reasons: the evidence is missing, changed or contradicts the shop |

## 4. Just before the yes

```
python3 -B scripts/hass/demo_pre_yes_gate.py before --state <state> --media <media> --worktree <wt> --job <job> --photo <photo> --version <n>
```

Only on `READY yes <job>-<n>` does the owner type exactly `yes <job>-<n>` in the chat that received the card. `ABORT
<reason>`: no yes (see `docs/hass/finish-demo-pre-yes-gate.md`). A READY you got earlier is not a receipt you can reuse:
run it again right before the yes; after the yes the same command answers `ABORT listing-not-waiting-for-a-yes`.

## 5. Right after the yes: does the shop serve the approved card?

```
python3 -B scripts/hass/demo_served_comparison.py --state <state> --worktree <wt> --job <job> --photo <photo> --version <n>
python3 -B scripts/hass/demo_resume_step.py --state <state> --media <media> --worktree <wt> --job <job> --photo <photo> --version <n>
```

Good: `MATCH undo`, then `REVIEW_TAKEDOWN`. `MISMATCH <reason>`: take it down at once (step 6) and report the reason
(`docs/hass/finish-demo-served-comparison.md`).

## 6. Take-down

The owner sends `undo`: it only proposes the take-down (nothing a visitor sees changes, and step 3 still says
`REVIEW_TAKEDOWN`). The owner then confirms with the coded `yes` the chat gives. Afterwards the shop is back to how it
was before the yes, step 3 says `NOT_SERVED` and `demo_served_comparison.py` says `MISMATCH not-served`.

## 7. Resume the next listing

Run step 3 for the next waiting listing (its own job, photo and version). A listing that waited through all of the above
is still `REVIEW_CURRENT_PREVIEW`, and step 4 is still `READY` for it.
