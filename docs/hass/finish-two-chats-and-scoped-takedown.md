# Two owners' listings and a scoped take-down (finish line, offline rehearsal)

**What this proves:** with the real chat, listing job, editor and local writer on throwaway repos, (1) two owners each
waiting on their own card survive one backup and restore without their cards, photos or confirmation codes mixing, and
(2) taking one item down touches only that item. **What it does not prove:** anything on the real site, in Clover, or on a
phone, and it is not the private 38/38 replay. Fixtures only: no network, no service, no live site. Tests:
`hass/tests/test_two_chat_restore.py` (L8) and `hass/tests/test_scoped_takedown.py` (L9). Run:
`python3 -B -m unittest hass.tests.test_two_chat_restore hass.tests.test_scoped_takedown`.

## Two conversations through one restore (L8)

| Step | What was proved |
|---|---|
| Both owners send a photo and a price in their own one-to-one chat | Two different listings with two different codes and two visibly different cards. Each chat received only its own card and only its own code. Each draft carries its own photo bytes. |
| A yes carrying the other chat's code (`yes <code>-1` or `yes <code>`), before and after the restore | Refused (`no-target` or `unsupported`). Nothing is saved, no approval is recorded, and the answer never repeats the other chat's code. |
| Backup, verify, restore into a new place and a new worktree | The restore starts paused. The saved conversation keeps each chat's rows apart: own code, own pictures, no picture shared. Both owners' photo originals are in the restored photo store. |
| After `resume changes`, one yes from the right chat | Exactly that chat's listing is saved: its name, price, photo description and photo bytes. A repeat saves nothing. The other listing is not in the catalog. The source install never moves. |
| The other owner's yes afterwards | Their card was made before the first listing was saved, so it is out of date. Hass says "Nothing changed. Please send the photo again for a fresh card." Nothing is saved and the first listing stays exactly as it was. |
| That owner sends the photo again | A fresh card with a NEW code. The old code stays dead and the first owner cannot use the new one. One yes saves it with its own price and photo. Both listings are then in the catalog, each with its own photo. |
| A backup with one changed byte | Refused. Nothing is restored. |

## Take-down reaches only the item it names (L9)

Two live fixture listings, a hidden-item fixture (the target) and a neighbor, each with its own photo.

| Step | What was proved |
|---|---|
| Unknown, mistyped, shortened or empty item id | Refused before any draft exists. The site does not move. |
| The WRONG real item taken down by mistake | The success check says no: the target is still public and unchanged. (The check is "target gone AND every other record and photo byte identical".) Putting the neighbor back restores the exact earlier state. |
| Take the target down (`product.hide`) | One record leaves the public catalog. The neighbor's record and photo bytes are identical to before. Nothing else changed. Hiding it a second time is refused, with no new change. |
| OFF restart (backup, verify, restore on a new worktree) | The hidden item is still hidden after the restart, and the catalog bytes are identical. Putting it back in the restored copy returns exactly the original card (photo bytes included); taking it down again leaves the neighbor untouched. The source install never moves. |
| A damaged backup | Refused, nothing restored, the live site stays down for that item. |

## Safe recovery steps for a person (G-H)

1. **Wrong item went down:** do not say `undo` again blindly. Put that item back with the editor (`product.restore` with
   that item's id), then take down the right one. Check afterwards that the other cards and photos look exactly as before.
2. **Two people have cards waiting and one is saved first:** the second card becomes out of date. Hass says so and saves
   nothing. The second person sends the photo again and uses the NEW code. Never reuse an old code.
3. **After any restore:** it starts paused. Check the hidden items are still hidden, then say `resume changes`. Do not
   restore a backup over a running install.
4. **Take-down uncertain** (reply unclear, preview different from the item): stop and look at the site; do not repeat the
   message.
5. Keep transcripts and receipts local; never paste them into Git or a public chat.
