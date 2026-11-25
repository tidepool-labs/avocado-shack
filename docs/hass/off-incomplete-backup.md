# A backup that stopped half way (finish line, offline rehearsal)

**What this proves:** when a copy of the Hass state is cut short, partly written or missing its last step, the check says
so, nothing is restored from it, nothing on the install moves, and the installer can fall back to the newest earlier backup
that checks out. That earlier backup brings back the listing and photo that were already on the site and replays no yes.
**What it does not prove:** anything on the real site, in Clover, or on a phone, and it is not the private 38/38 replay.
Fixtures only: throwaway repos, no network, no service, no live site, nothing deleted. Test:
`hass/tests/test_off_incomplete_backup.py` (L10). Run: `python3 -B -m unittest hass.tests.test_off_incomplete_backup`.

## The rehearsal

Listing 1 is posted, then backup **A** is taken. Listing 2 is then only a card waiting for its yes, and backup **B** is
taken. B is copied and the copy is hurt in each of seven ways.

| Damage to the newest copy | What the checks said |
|---|---|
| Saved conversation cut in half | `verify` says corrupt and names the problem; `drill` stops at the verify step |
| One photo cut in half | same |
| Saved site (content bundle) cut in half | same |
| Settings file emptied | same |
| One listed file gone | same |
| Last step never written (no manifest, as when the copy stops early) | same; `list` shows it as "no manifest (interrupted)" |
| The backup's own list cut short | same |

In every case: no restore folder and no photo folder appeared, the drill worktree stayed clean, the damaged copy and the
good backups were left where they were (nothing deleted or repaired), and the source install's head, catalog bytes and
commit count did not change. The untouched B still verifies, so the refusals are not a side effect of the setup.

| Recovery step | Result |
|---|---|
| `list` the backup folder, newest first, and `verify` each in turn | Damaged copies are skipped, even when their names sort newest. A half-built folder from a stopped `create` (a dot-name `.partial-` folder) is never listed. |
| Restore the first one that verifies (here A) with `drill`, paused | The restored site has listing 1 with its approved price, photo description and photo bytes, and not listing 2. The saved chat knows listing 1 only. |
| Restart the chat on the restored copy | Nothing posts by itself. |
| `yes <code>` for listing 1 while paused, then after `resume changes` | Saves nothing, then "no target". No second commit. |
| `yes` for listing 2's code, or a bare `yes` | Refused. Nothing is saved: the restored copy never saw listing 2. |
| Control: newest backup intact | Chosen first; it brings back listing 2's waiting card paused, and a yes while paused saves nothing. |
| Restore into a folder that already exists | Refused ("left untouched"); its files are byte-identical afterwards. |
| A hand-copied state folder with the saved conversation cut in half | The health check reports it. Do not start Hass on it. |

## Safe recovery steps for a person (G-H)

1. Never repair or delete a damaged backup in place. Leave it for later and work from a copy or a different folder.
2. List the backups (`python3 hass/statebackup.py list --out <backup-dir>`) and check the newest with
   `python3 hass/statebackup.py verify <backup>`. A line saying "no manifest (interrupted)" or any result other than `ok`
   means: do not restore it.
3. Check the next older backup the same way until one says `ok`. Restore only that one, into a NEW folder and a NEW
   worktree, with `drill` (it starts paused).
4. Look at the restored site: the listings you expect are there with the right photos. A listing that was only a waiting
   card at the damaged backup's time will not be there. Ask for a fresh card; do not reuse an old yes or code.
5. Only then say `resume changes`. Do not restore over a running install, and do not run a second restore into a folder
   that already holds files.
6. Keep transcripts and backups local; never paste them into Git or a public chat.
