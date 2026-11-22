# NPP tapes

Replay data for `hass/tests/npp/run_npp.py` (design `PIPELINE-DESIGN.md` 3.4). A tape is keyed by
`(kind, asset sha, input sha, ordinal)`; a call the tape does not hold fails the run (a tape miss). Nothing here calls a
model or the network.

| File | Kind | Source | Holds |
|---|---|---|---|
| `s2.json` | `s2` | **hand-authored** | the S2 reading (what the identify step returns for a photo) for the question-path cases 18a, 18b, 20, 22 and 33. No model produced it; the private host replaces it with a recorded tape (`run_npp.py --record`). |
| `MANIFEST.json` | n/a | generated | the sha256 of the case files, pages, photos, edit stand-ins, every tape file, `pins.json`, the asset set and the model pins this run depends on. |
| `judge/` | n/a | private-host runs | recorded judge scores per judge version, so a later run is compared item by item (`npp_eval.py --judge --calibrate --scores`). Not created yet: the first calibrated private-host run adds it. |

The manifest ties cases, tapes and pins together: change any of them and `run_npp.py` refuses to replay until
`python3 -B hass/tests/npp/run_npp.py --update-manifest` is run in the same PR (design 4d: an asset or pin change is a
reviewed change that passes the replay, the private-host strict run and the judge). `renderer_commit` in the manifest is
`null` until a private-host `--preview` run records the renderer; `pins.json` is owned by NPP-A and is not edited here.

The research cases (29, 30, 31, 37, 38) need no tape: their synthetic web and model stubs are in the case files, and the
real `hass/npp/research.py` runs over them (G decision 2026-11-18 14:00: search only to locate the maker's own site;
identity must match the owner's words or a confident label; facts only from that site, cited and checked against its
visible text; not confident means no story).
