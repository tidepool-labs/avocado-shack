# NPP eval cases

The 38 offline cases of the new-product pipeline (design `reports/hass-npp/PIPELINE-DESIGN.md` section 3.1), as data. They
are inputs, turns, paths, terminal states and expectations only. The runner (`run_npp.py`), the virtual clock and the tapes
belong to NPP-H; nothing here runs the pipeline. Case ids are permanent: a case is never deleted or renumbered, and a real
failure adds one case (`npp-YYYYMMDD-n`) in the same PR as its fix.

Research cases (29, 30, 31, 37, 38) follow G's decision of 2026-11-18 14:00 (Hass may find the maker's own official website
by itself; search only to locate it; facts only from that site or the owner's words, cited and checked against visible page
text; not confident means no story). This replaces the design's "owner URL or G-allowlisted domain only, zero search" rule
(section 1.8, 6 Q2 and Q4). Cases 37 and 38 therefore expect fetches for the identity check but **zero extraction calls**
and no story.

## File

`case-NN-slug.json`, validated by `case.schema.json`:

| Key | Meaning |
|---|---|
| `id`, `slug`, `title` | permanent id 1 to 38, short name, one line |
| `contract`, `bug` | the contract the case protects and the believable bug that makes it fail (CI-ARTICLE-1) |
| `path` | `listing`: photo, optional question, delivered card v1, an edit, delivered card v2, `yes <code>-2`, one commit in the throwaway writer, then `undo`, which drafts the hide (a proposal with its own code; nothing is hidden until that yes). Only the cases with a `control` skip the edit. `question`: ends in `asking`, `retake` or `expired`, replies only, no draft, no prompt. `contract`: a scripted timing, restart or race sequence |
| `terminal` | `published`, `asking`, `retake`, `expired` or `card_out` |
| `settings` | the editor settings of the run (`npp`, `houseRender`, `photo_polish`, `itemIntake`, `liveSite`, `approvalTtlSeconds`) |
| `turns` | what the owner sends and when: `at_s` virtual seconds, `text`, `photos`, optional `reply_to` (`v<n>`: a channel reply to that version's delivered message), `alt_reply_to` (the same approval sent as a coded reply, a variant of the tag form), `restart` (drop and rebuild the Conversation and job runner over the same state), `retry_send` (let a failed pending outbox row send again). `{code}` is the job code |
| `control` | optional: why this `listing` case is exempt from the v1, edit, v2, `yes <code>-2` path (cases 23 and 24 only: spec rows that fix a restart or sole-delivered control); it still ends with `undo` |
| `variants` | independent runs of one case with a short id (`a`, `b`, `reply-to`) and a title. Each variant supplies its own `turns` or inherits the case's `turns`; `inputs` and `expect` are merged shallowly over the case's. Every variant reaches the case's `terminal` |
| `inputs` | `polish` (the image edit: `file` stand-in bytes under `edits/`, `record` for a real edit taped by NPP-H, `none` for a run where any edit call fails the case, `error` for a failing call), `web` (a synthetic web, below), `stubs` (model outputs the case forces), `outbox` (scripted send results per version), `private` (invented cost and quantity), `gate_expect` |
| `expect` | what must hold; keys listed in `x-expect-keys` of the schema. `checks` names the section 3.2 checks that must pass; `calls` counts model, search and fetch calls (a number, or `[min, max]`); `versions` lists each version's `delivered` and `approved` state; `edit_keeps` names the fields v2 copies unchanged from v1 (an edit never starts a second picture edit); `undo` (`{"draft": "hide", "commits": 1}`) says the reply to `undo` is a proposal of the hide (reply kind `undo_draft`) and the commit count stays 1 until its own yes |
| `settle_until_s` | run the clock to this time before asserting |

`expect.replies[].turn` is the replay step where a send is first observed. For a delayed card,
`answers_turn` separately checks the owner turn to which its outbox row is durably bound.

Photos are `npp:<file>` (this folder's `photos/`) or `chaos:<file>` (`hass/tests/chaos/photos/`). They are synthetic or
product-only: no person and no chat, except the deliberate drawn phone screen of case 28b. Costs, quantities and prices are
invented fixture values.

## Synthetic web (research cases)

`inputs.web.search` maps an exact query to results `{url, title}`; `inputs.web.pages` maps an address to a page file under
`pages/` with its retrieval day; `forbid_fetch` lists addresses that must never be fetched. All addresses use the reserved
`.example` domain except a denied host (a directory) that is only named. Queries follow the forms in
`hass-maker-research/sources.json` and carry no digits. A search or fetch that is not in the world is a tape miss.

## Picture stand-ins

`make_npp_photos.py` writes `photos/` and `edits/`: the twelve golden photos (the live gallery picture on a cluttered
counter, fixed seed), the drawn products, and for honey, elderberry, coffee and figs a good edit, a painted-relabel bad
edit and a recolour bad edit (HASS-IMAGE-1 T3 classes). `--verify-gate` runs the real `photo_polish.gate` over them: the
good edits pass and the bad ones are rejected (`text` or `colour`). For the golden photos the gallery picture used as the
edit passes the real gate for 015, 002, 044 and 021 only, so cases 1 to 12 take a recorded edit tape (`record`).
