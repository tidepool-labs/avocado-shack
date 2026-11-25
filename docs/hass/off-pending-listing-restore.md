# Hass pending listing through a backup and restore (OFF install rehearsal, offline)

**What this proves:** a listing that is still waiting for the owner's yes survives a state backup and a restore into a new,
paused copy without posting by itself, an old version's yes cannot post, and exactly one yes for the current version posts, once,
with the current price and the approved photo. **What it does not prove:** anything about the live service, the live site, Clover
or real timing. Nothing here starts or stops a service. Workers never run the live steps (see
[finish-off-install.md](finish-off-install.md) for the commands).

Test: `hass/tests/test_off_restore_pending_listing.py` (throwaway repos, fixture chat and transport, no network).

| # | Situation | Required result |
|---|---|---|
| R1 | Two versions are waiting (v1, then the owner changes the price and v2 replaces it). State is backed up (photo originals come with it when NPP is on), verified, and restored with `drill` into a **new** directory and a **new** worktree. A fresh chat starts on the copy, as after a restart. | The restore is paused. Flushing the chat any number of times posts nothing: same worktree head, same site catalog bytes, clean worktree. A `yes <job>-2` is answered with "Changes are paused, so nothing will be saved yet" and saves nothing. The source install never moves (head, site, commit count). |
| R2 | After `resume changes` on the copy | `yes <job>-1` (old version), `yes <job>` (bare job code) and a bare `yes` all post nothing. `yes <job>-2` posts: one commit, the v2 price (not v1's), the approved photo bytes (SHA-256 of the approved draft). Repeating any yes posts nothing more. The source install still has no card. |
| R3 | A backup with one changed byte | `verify` and `drill` refuse; no restored state or media directory appears. |

## Redacted recovery steps for the attended OFF install (G or Mike; no agent runs them)

1. Before any switch, make the state backup and run `verify` (see finish-off-install.md). A damaged backup is refused; do not restore it.
2. Restore only into a **new** directory with a **new** worktree. The restored copy is paused on purpose: a yes on it saves nothing.
3. If a waiting version existed when the backup was made, the owner must say `resume changes`, then reply with the code of the
   **newest** version. An older version's code is refused. If unsure which is newest, ask Hass to show the preview again; do not guess.
4. Never run the same yes against the source install and the restored copy. The test shows they are independent: a yes on the
   copy does not reach the source.
5. If the restore reports NPP off (`nppOff`: media or an original was missing), the pending version cannot be answered from the
   copy. Stop and use the source install; do not edit the restored config by hand.
6. Keep the backup, the restored state and the transcript private. Never paste them into Git, a ticket or a public chat.

## Limits

- Timings and sizes are for a tiny fixture state; a real state with photos takes longer.
- The restore drill's health check and the real service are separate (see RUNTIME-RELEASE.md).
