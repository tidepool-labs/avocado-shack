# Commerce gateway test pairs and export mentions

| Check | Result |
| --- | --- |
| R1. Same-name pairs | 20 of 25 modules; five have no matching gateway test file. |
| R2. Export mentions | 7 of 45 names do not appear in any of the 21 gateway test files. |
| R2. Tests without a same-name module | One: `setup.test.mjs` tests an existing script outside `gateway/`. |
| R3. Runner selection | The package script selects all 21 tests; the check workflow selects 20, excluding `owner-photo.test.mjs`. |
| R4. Follow-up | None needed for the historical prototype. |

Source: `origin/main` at `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, inspected offline after cloning on 2026-11-21. The summary follows R1–R4 below. The current source is `storefront-mockup/`; `commerce/` is historical (`AGENTS.md:3–5`, `HERMES_HANDOFF.txt:33–38`). This inventory does not test the active catalog or Hass pipeline.

## R1. Module inventory

All filenames below are relative to `commerce/gateway/`. `L` marks the line containing the export, including both names on the grouped export in `server.mjs`. Line counts include blank and comment lines. A pair means an exact basename match, not a coverage claim. The directory has 47 tracked files: 25 modules, 21 tests and `schema.sql` (not a JS module).

| Module | Lines | Paired test | Exported names |
| --- | ---: | --- | --- |
| `astra-client.mjs` | 20 | `astra-client.test.mjs` | `labelProposal` (L4), `proposalFields` (L18), `groundedProposal` (L19), `propose` (L20) |
| `availability.mjs` | 2 | `availability.test.mjs` | `variantAvailability` (L2) |
| `box-revision.mjs` | 5 | `box-revision.test.mjs` | `revisionFields` (L1) |
| `boxes.mjs` | 22 | `boxes.test.mjs` | `validateBox` (L8), `interpretBox` (L19) |
| `catalog-item.mjs` | 1 | `catalog-item.test.mjs` | `catalogItem` (L1) |
| `discount-rule.mjs` | 9 | `discount-rule.test.mjs` | `discountRule` (L2) |
| `editorial.mjs` | 15 | `editorial.test.mjs` | `defaultContent` (L1), `validateContent` (L2), `validateSlot` (L3), `interpretContentMessage` (L5), `interpretFeatureMessage` (L10), `featureRevision` (L15) |
| `interpret.mjs` | 30 | `interpret.test.mjs` | `interpret` (L3), `questions` (L28), `validateFields` (L29), `assertVersion` (L30) |
| `marketing.mjs` | 1 | `marketing.test.mjs` | `productAnnouncement` (L1) |
| `offer-time.mjs` | 8 | none | `offerTime` (L3) |
| `owner-photo.mjs` | 12 | `owner-photo.test.mjs` | `ownerPhoto` (L4) |
| `packing.mjs` | 2 | `packing.test.mjs` | `packSheet` (L1), `verifyPacked` (L2) |
| `photo-proposal.mjs` | 14 | none | `photoProposal` (L2), `combinePhotoProposals` (L9) |
| `pickup-command.mjs` | 10 | `pickup-command.test.mjs` | `pickupCommand` (L1), `assertPickupWindows` (L7) |
| `pickup-time.mjs` | 1 | `pickup-time.test.mjs` | `utcFromLocal` (L1) |
| `primary-photo.mjs` | 5 | `primary-photo.test.mjs` | `primaryPhoto` (L1) |
| `product-details.mjs` | 4 | `product-details.test.mjs` | `detailKeys` (L1), `productDetails` (L2) |
| `quote.mjs` | 6 | `quote.test.mjs` | `sameQuoteItems` (L2), `samePurchaseItems` (L3) |
| `safety-buffer.mjs` | 5 | `safety-buffer.test.mjs` | `bufferAvailable` (L1) |
| `scheduled-special-routes.mjs` | 17 | none | `scheduledSpecialRoutes` (L3) |
| `scheduled-special.mjs` | 13 | `scheduled-special.test.mjs` | `scheduledSpecialCommand` (L4), `assertScheduledSource` (L13) |
| `server.mjs` | 126 | none | `app` (L126), `applyDraft` (L126) |
| `special-command.mjs` | 24 | `special-command.test.mjs` | `specialCommand` (L4), `assertSpecialSource` (L17) |
| `stock.mjs` | 11 | `stock.test.mjs` | `stockTarget` (L1) |
| `vision.mjs` | 3 | none | `labelEvidence` (L3) |

Replay from the repo root, with `base` fixed to the inspected commit:

```sh
base=37feae1dc5efa6968f90d17a1eda6daed29afd4a
git ls-tree -r --name-only "$base" -- commerce/gateway
for p in $(git ls-tree -r --name-only "$base" -- commerce/gateway); do
  case "$p" in *.test.mjs) continue ;; *.mjs) ;; *) continue ;; esac
  printf '%s: ' "$p"
  git show "$base:$p" | wc -l
  git grep -n -E '^[[:space:]]*export[[:space:]]' "$base" -- "$p"
done
```

## R2. No name mention and unmatched tests

A mention is the exact, case-sensitive identifier in the text of any tracked `commerce/gateway/*.test.mjs`, even a different stem. This is not line or branch coverage: an import or comment can count as a mention, and a test can exercise behavior without naming the export. The other 38 exports each have at least one mention in that set.

| Export with no mention | Export anchor | Same-name test? |
| --- | --- | --- |
| `propose` | `commerce/gateway/astra-client.mjs:20` | Yes |
| `featureRevision` | `commerce/gateway/editorial.mjs:15` | Yes |
| `detailKeys` | `commerce/gateway/product-details.mjs:1` | Yes |
| `scheduledSpecialRoutes` | `commerce/gateway/scheduled-special-routes.mjs:3` | No |
| `app` | `commerce/gateway/server.mjs:126` | No |
| `applyDraft` | `commerce/gateway/server.mjs:126` | No |
| `labelEvidence` | `commerce/gateway/vision.mjs:3` | No |

`offer-time.mjs` and `photo-proposal.mjs` have no same-name test but do have direct tests elsewhere: `commerce/gateway/scheduled-special.test.mjs:7–8` names `offerTime`, and `commerce/gateway/astra-client.test.mjs:12,14` names `photoProposal` and `combinePhotoProposals`. `detailKeys` is used by `productDetails` (`commerce/gateway/product-details.mjs:1–3`), and the filter is exercised through that function (`commerce/gateway/product-details.test.mjs:1–2`).

`setup.test.mjs` is the only test with no same-name gateway module. It imports `prepare` from `../scripts/setup.mjs` (`commerce/gateway/setup.test.mjs:1`; export at `commerce/scripts/setup.mjs:2`). Its target still exists. No gateway test in this inventory was found to have lost its target module; the missing sibling is not evidence of a deletion (`git log "$base" -- commerce/gateway/setup.mjs` returned no entries on 2026-11-21).

Replay with the same `base`: the first command has no matches (exit 1); the second exposes the local imports, including the dynamic photo-proposal imports.

```sh
git grep -n -w -e propose -e featureRevision -e detailKeys -e scheduledSpecialRoutes -e app -e applyDraft -e labelEvidence "$base" -- ':(glob)commerce/gateway/*.test.mjs'
git grep -n -E "(from |import\()['\"]\.\.?/" "$base" -- ':(glob)commerce/gateway/*.test.mjs'
```

## R3. Which tests each runner selects

- **Package:** `commerce/package.json:8` (`/scripts/test`) says `"test": "node --test gateway/*.test.mjs"`. From `commerce/`, that selects all 20 paired test filenames in R1 plus `setup.test.mjs` (21). The historical README documents the same glob (`commerce/README.md:41`).
- **Check workflow:** `.github/workflows/check.yml:102–107`, under `quick`, runs the two lines below rather than calling the npm script. This selects the same set **except** `owner-photo.test.mjs` (20: 19 paired plus `setup.test.mjs`). The excluded test imports `sharp` (`commerce/gateway/owner-photo.test.mjs:1`), the stated reason for excluding it (`check.yml:103–104`). The `quick` job skips draft PRs (`check.yml:62–65`); this is the selection when the step is reached, not proof of a hosted run.

```sh
tests=$(ls commerce/gateway/*.test.mjs | grep -v '/owner-photo\.test\.mjs$')
node --test $tests
```

Read-only replay of the two input lists (repo root, same `base`):

```sh
git ls-tree -r --name-only "$base" -- commerce/gateway | grep -E '/[^/]+\.test\.mjs$'
git ls-tree -r --name-only "$base" -- commerce/gateway | grep -E '/[^/]+\.test\.mjs$' | grep -v '/owner-photo\.test\.mjs$'
```

The selection was checked from source and the tracked filenames. The gateway suites and GitHub workflow were not executed; no runtime, dependency install, live service or pass/fail result was checked.

## R4. Ranked gaps

1. **A known runner difference:** `owner-photo.test.mjs` is selected by the package script but intentionally omitted by the workflow because it needs `sharp` (R3). A green workflow would not tell us whether this test passes.
2. **Exports not named by tests:** seven names, including the server and scheduled-special route exports and the interpreter and OCR entry points (R2). These are source-level leads, not demonstrated behavior defects. A missing name such as `detailKeys` can still sit on a tested path (R2).
3. **Filename differences that overstate gaps:** `offer-time` and `photo-proposal` are tested in other files; the setup test targets a script outside the gateway (R2). A rename just to make the inventory symmetrical is not needed.

**No buildable follow-up is needed for this status report.** The prototype is historical (`AGENTS.md:3–5`); none of the findings warrants changing the site, historical code, tests, or workflow as part of this audit.
