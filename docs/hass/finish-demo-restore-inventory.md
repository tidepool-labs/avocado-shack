# The restore inventory before a restore (OFF demo, finish line)

**What this is:** one small read-only command for the demo owner. Before restoring a Hass state backup (or when choosing between
two), it lists every listing in it by job code and says whether the pieces a restore needs are all there together: the saved chat,
the photo original, the delivered card picture and the shop as it was served. If a backup has the chat and pictures but not the
served-state input, it is refused. Restoring it could replay a `yes` for something the shop does not show, or hide that a listing is
already live.
**What it is not:** a restore, a yes or a live listing. It never writes to a backup, a state folder, a worktree, the site or any
service (the content bundle is unpacked into a private scratch folder that is deleted afterwards). Test:
`hass/tests/test_demo_restore_inventory.py` (L18).

## Run it

```
python3 -B scripts/hass/demo_restore_inventory.py <backup dir>
python3 -B scripts/hass/demo_restore_inventory.py <backup dir> --against <other backup dir>
```

One backup prints `BACKUP ok items=<n> served-state=present` then a line per listing:
`ITEM <job> <class> history=<photo messages in>/<card messages out> originals=<n> card=<0|1> served=<yes|no>`.
With `--against` it prints `COMPARE same` (exit 0) or `COMPARE differs` (exit 1) followed by `CONTENT served-state-commit-differs` when
the shop snapshot is a different one and a `DIFF <job> <labels>` line per listing that differs. Output is only fixed words, job
codes and counts: no name, text, price, path or picture. Refusals are `REFUSED <reason>` (exit 1).

## Classes (first that applies)

| Class | Meaning |
|---|---|
| `served` | the approved name is in the served catalog (once) and the served photo is the approved photo |
| `served-photo-differs` | the name is served but the photo is not the approved one, or the name is served twice |
| `ended` | the listing was closed and is not served |
| `incomplete-photo-original-missing` | the photo original is not in the backup |
| `incomplete-card-not-delivered` / `in-progress` | the newest card was never delivered (in-progress when the listing is still being made) |
| `incomplete-card-file-missing` | the delivered card picture file is not in the backup |
| `incomplete-photo-not-in-history`, `incomplete-card-not-in-history` | the listing's own chat does not hold its photo message (marked with the job code) or its card message (marked with `<job>-<version>`); another owner's message with the same picture does not count |
| `incomplete-listing-has-no-name` | the newest version has no name to compare with the shop |
| `waiting-for-yes` | everything is in place and the listing is waiting for its yes |

`--against` labels per listing: `only-in-first`, `only-in-second`, `class-differs`, `history-differs`, `media-differs`, `served-differs`.

## Refusals

| Reason | Meaning |
|---|---|
| `no-served-state` | the backup has no content bundle (history and media only) |
| `backup-not-intact` | it does not verify (missing, changed or extra file, wrong mode, a link on the path, not a backup) |
| `history-unreadable` | the saved chat or the conversation store cannot be read |
| `served-state-unreadable` | the content bundle or its catalog cannot be read, or the catalog is not a list of named records |
| `bad-listing-record` | a listing's job code, photo or card hash, chat or version in the saved conversation is not the expected shape (nothing else is ever printed) |
| `could-not-check` | anything else; never a traceback |

## Proven offline (fixtures, no service)

Two owners' cards waiting (backup A), then one real yes for one of them (backup B): A listed both `waiting-for-yes` with all pieces,
B listed one `served` (with its photo) and one `waiting-for-yes`; A against B named only that listing (`class-differs,served-differs`) and
the changed shop snapshot; two backups of the same state compared `same`. A backup without its bundle, an altered card file, a
missing backup, a linked backup (leaf or parent), a loose mode and a transcript without its events were each refused with the
reason above. Backups that still verify but lack a photo original, a card file, the chat's card or photo message were named per
listing, a closed unserved listing printed `ended`, and a served name with another owner's photo in the bundle printed
`served-photo-differs`. Every file of both backups, the live state folder, its commits and the scratch folders were identical
before and after every run. Each check was mutation-tested.

## Limits

- Fixture proof only. It does not prove the private 38/38 replay or the attended hidden TESTITEM on the real shop.
- It reads the shop as it was inside the backup's content bundle, not the live shop. Use `demo_served_comparison.py` (L17) after a yes.
- A backup taken while the shop's checkout was unreadable has no bundle and is refused: take a new one.
