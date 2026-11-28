# Research and image log integrity

| Check | Result |
| --- | --- |
| R1. Log records | 204 rows across six files: 202 with an item ID, one correction without an ID, and one synthetic research contact. |
| R2. Catalog matches | All 202 ID-bearing rows (185 distinct IDs) match a checked catalog or historical item list. 183 rows match the current generated catalog. The research contact is not a product match. |
| R2. Asset matches | 308 of 316 filename references are absent under tracked `assets/` (232 distinct missing names). The only hit is `logo.png`, referenced eight times. All 170 rows in the current generated catalog separately point to tracked assets. |
| R3. Correction overlap | Zero shared IDs between the two named corrections files (8 rows versus 3). There is no same-product entry to compare or declare in conflict. |
| R4. Next step | No build needed for this snapshot audit. |

Checked offline on 2026-11-21 at `origin/main` `37feae1dc5efa6968f90d17a1eda6daed29afd4a`, identical to the task baseline. The results describe the Git tree, not a deployed site, private photo archive or external generation folder. Only asset names were checked, not image bytes or derivation. Nothing here decides rights, policy, claim truth, or whether a product should be restored or removed.

## R1. Shapes and counts

Log and storefront catalog filenames below are relative to `storefront-mockup/`. `#` denotes the JSON root; array indexes are zero-based. Count array elements and the singleton `/firstProduct` object, not metadata strings. The aliases in the first column identify logs in the later tables.

| Log | Top-level keys | Rows and anchors | Product or name key | Image filename keys on the row |
| --- | --- | --- | --- | --- |
| `research`: `producer-research-log.json` | `note`, `contacts` | 1 at `#/contacts` | `name` is a contact name, not a product key; no product ID | None |
| `generation`: `image-generation-log.json` | `mode`, `products`, `merchAndBoxes`, `corrections`, `firstProduct` | 109: 94 at `#/products`, 10 at `#/merchAndBoxes`, 4 at `#/corrections`, 1 at `#/firstProduct` | `id` except at `#/corrections/0` | `path` on product, merch/box and correction rows; `refs[]` on merch/box rows; `photo` on 3 correction rows; `source` on `firstProduct`, which has no `path` |
| `expanded`: `expanded-image-log.json` | None (array) | 9 at `#` | `id` | `path` |
| `completion`: `completion-image-log.json` | None (array) | 74 at `#` | `id` | `path`, `refs[]` |
| `final-image`: `final-image-corrections.json` | None (array) | 8 at `#` | `id` | `path` (destination PNG); `resultHint` mentions a separate generated PNG |
| `image-final`: `image-final-corrections.json` | None (array) | 3 at `#` | `id` | `photo`, `path` |

## R2. What resolves and what does not

### Product identifiers and names

Match `id` by exact, case-sensitive equality. For a name-only row, compare exact `name` to catalog `name` separately; do not treat prompt/target prose, a shared source photo, or a similar name as a product key. The two cited catalogs are `catalog.json#` (95 rows) and `new-products.json#` (9). Also check `completion-new-products.json#` (70), `held-products.json#/products` (2), and `shop-data.json#/products`, `#/merch`, `#/boxes` (170, 8, 3). Counts are per source, not additive across files. The generated display list is `catalog-products.js:1`; its ID set equals the active subset of `hass/content/products.json#/products`. `storefront-mockup/README.md:10-16` distinguishes the generated display list from the historical extraction and commerce files.

| Log (R1 anchors) | Rows with ID | Distinct IDs within log | In the two cited catalogs | In all checked item lists | In current generated catalog |
| --- | ---: | ---: | ---: | ---: | ---: |
| research | 0 | 0 | 0 | 0 | 0 |
| generation | 108 | 105 | 98 | 108 | 94 |
| expanded | 9 | 9 | 9 | 9 | 9 |
| completion | 74 | 74 | 0 | 74 | 69 |
| final-image | 8 | 8 | 0 | 8 | 8 |
| image-final | 3 | 3 | 3 | 3 | 3 |
| Total | 202 | 185 across logs | 110 | 202 | 183 |

- **No logged ID is absent from every checked catalog/item file.** Restricting the comparison to the two cited catalogs excludes the ten `generation#/merchAndBoxes` rows and every `completion` and `final-image` row. The 70 completion food IDs and all eight final-image IDs match `completion-new-products.json#`; the remaining four completion rows (`#/69` and `#/71`–`#/73`) and the ten generation merch/box rows match the historical `shop-data.json#/merch` or `#/boxes`.
- **Outside the generated catalog:** the 14 merch/box row occurrences above, plus `"photo-product-020"` and `"photo-product-036"` (`generation#/products/19/id`, `#/products/32/id`, both present in `catalog.json#`) and the held IDs `"photo-product-040"` (`generation#/products/40/id` and `#/corrections/2/id`) and `"photo-product-133"` (`completion#/32/id`), recorded in `held-products.json:20,29`. These are differences in catalog scope, not recommendations to list anything.
- **Unmatched name:** `"Example Farm"` (`research#/contacts/0/name`) is absent from the checked product `name` fields. `research#/note` labels the file a synthetic stand-in. Its one contact is not evidence of either a product or a missing product, and the private original was not inspected.
- **Unkeyed row:** `generation#/corrections/0` has no `id` or `name`. It is counted, but cannot be joined on either field. The only repeated IDs within `generation` are `"photo-product-035"`, `"photo-product-040"`, and `"photo-product-056"` (each twice across the row collections in R1).

### Image files

Compare the last component of every logged filename against the case-sensitive basenames of the 197 tracked paths under `storefront-mockup/assets/`, recursively. No guessing extensions, substituting a similarly named WebP, or using `ok` as proof a file is tracked. The eight references with repo-relative asset suffixes that match by filename all point to `assets/logo.png` at that exact suffix. The eight `assets/products/*.png` destination suffixes in `final-image#/0`–`#/7` all miss both by suffix and by basename. Host prefixes and free-text hints are omitted; count the single PNG filename in each `resultHint` once. There were no filename literals in the `prompt` or `target` fields.

| Log and fields (R1 anchors) | `path`: missing / total | Inputs (`photo`, `source`, `refs[]`): missing / total | `resultHint`: missing / total | All fields: missing / total |
| --- | ---: | ---: | ---: | ---: |
| research | 0/0 | 0/0 | 0/0 | 0/0 |
| generation `/products` | 94/94 | 0/0 | 0/0 | 94/94 |
| generation `/merchAndBoxes` | 10/10 | 9/16 | 0/0 | 19/26 |
| generation `/corrections` | 4/4 | 3/3 | 0/0 | 7/7 |
| generation `/firstProduct` | 0/0 | 1/1 | 0/0 | 1/1 |
| expanded | 9/9 | 0/0 | 0/0 | 9/9 |
| completion | 74/74 | 82/83 | 0/0 | 156/157 |
| final-image | 8/8 | 0/0 | 8/8 | 16/16 |
| image-final | 3/3 | 3/3 | 0/0 | 6/6 |
| Total | 202/202 | 98/106 | 8/8 | 308/316 |

The [missing-filename table](#missing-filename-table) quotes all 232 names with their JSON pointers. Separately, every `image` value in `catalog-products.js:1` resolves as an exact tracked asset path. In the historical JSON lists above, 199 of the 202 ID-bearing log rows match at least one catalog record with a tracked `image` path. The three exceptions are `"photo-product-020"` and `"photo-product-036"` at `generation#/products/19` and `#/products/32`, and `"photo-product-133"` at `completion#/32`. None is in the generated display list. A catalog asset with the same ID is not proof that it came from a particular log row.

## R3. The two corrections files

The intersection of the `id` sets is empty. The quoted IDs and image basenames below are the compared entries' relevant fields; full paths and prompt/hint prose are not reproduced. A dash means there is no row on that side, not that fields agree. No precedence follows from either filename.

| `final-image-corrections.json` (pointer · `id` · `path` basename) | `image-final-corrections.json` (pointer · `id` · `photo` · `path` basename) |
| --- | --- |
| `#/0` · `"photo-product-140"` · `"photo-product-140.png"` | — |
| `#/1` · `"photo-product-141"` · `"photo-product-141.png"` | — |
| `#/2` · `"photo-product-129"` · `"photo-product-129.png"` | — |
| `#/3` · `"photo-product-138"` · `"photo-product-138.png"` | — |
| `#/4` · `"photo-product-139"` · `"photo-product-139.png"` | — |
| `#/5` · `"photo-product-142"` · `"photo-product-142.png"` | — |
| `#/6` · `"photo-product-143"` · `"photo-product-143.png"` | — |
| `#/7` · `"photo-product-144"` · `"photo-product-144.png"` | — |
| — | `#/0` · `"photo-product-080"` · `"IMG_9735.jpg"` · `"exec-33ed1477-5856-4b3e-84c9-57649b0157ce.png"` |
| — | `#/1` · `"photo-product-069"` · `"IMG_9732.jpg"` · `"exec-b268c93f-adb6-4d17-a349-e655b959df94.png"` |
| — | `#/2` · `"photo-product-081"` · `"IMG_9736.jpg"` · `"exec-6f716a1e-cfe3-4047-8e51-1b8917b98c37.png"` |

## R4. Ranked gaps

1. **Image provenance cannot be replayed from this checkout.** None of the 202 `path` filenames resolves (R2). All eight destination PNGs in `final-image` have same-ID WebPs under `assets/products/`, but the filenames alone do not establish that the WebPs derive from those corrections. `README.txt:32-35` also distinguishes the separately kept files from optimized WebPs in Git. This is not a finding of broken current catalog image paths.
2. **One correction has no stable product key.** `generation#/corrections/0` cannot be matched without guessing. The similarly named files in R3 are disjoint, not evidence of a conflicting edit.
3. **The public research file cannot prove product-level research coverage.** `research#/note` and `#/contacts` give a synthetic record, not a product-to-research index.

No build needed for this report. No remediation, private archive access, or owner decision is proposed here.

### Offline replay

The tables are the read-only results from 2026-11-21. Run `python3 reconcile.py` from the task workspace with the verifier's scratch replay script alongside the `avocado-shack` clone. It reads pinned blobs using `git show` and names using `git ls-tree`; its only output file is a scratch copy of the missing-filename table. To inspect the inputs directly from the clone, for example:

```text
git show 37feae1dc5efa6968f90d17a1eda6daed29afd4a:storefront-mockup/catalog.json
git ls-tree -r --name-only 37feae1dc5efa6968f90d17a1eda6daed29afd4a -- storefront-mockup/assets/
```

### Missing-filename table

Each filename is listed once; pointers use the log aliases from R1. Repeated references to the same name are in the same row. No external folder was searched.

| Missing filename | Log and JSON pointer(s) |
| --- | --- |
| `exec-c1b7e605-9927-4b48-ad15-ae9fb97f0308.png` | `generation#/products/0/path` |
| `exec-5a0919c1-53c8-4b59-aabd-8feec4925eb8.png` | `generation#/products/1/path` |
| `exec-79156eb5-0436-47af-974b-cd9f6acb25d0.png` | `generation#/products/2/path` |
| `exec-36ce5886-a593-4499-9a84-2833f2a1ea98.png` | `generation#/products/3/path` |
| `exec-029d044b-c636-4f1b-9580-b4bdf59264cf.png` | `generation#/products/4/path` |
| `exec-0fa434a5-8fa6-429f-a34f-45fa17115776.png` | `generation#/products/5/path` |
| `exec-2fd6b40c-9843-417e-b920-a4b2d0187f65.png` | `generation#/products/6/path` |
| `exec-7cd797a0-0ebd-4c54-8ee4-c4d9c2e89616.png` | `generation#/products/7/path` |
| `exec-2bc2d3a0-e78f-4b28-a48f-b8615f20e99f.png` | `generation#/products/8/path` |
| `exec-a7f527b1-0683-4847-a199-887737ae8b18.png` | `generation#/products/9/path` |
| `exec-9ff0854a-0400-47d7-aa34-c64706f8f7fc.png` | `generation#/products/10/path` |
| `exec-c04caa48-6fcc-48b8-8a1a-d5748cd4fd36.png` | `generation#/products/11/path` |
| `exec-2e08d470-be09-4a68-8004-a7aa9aabde20.png` | `generation#/products/12/path` |
| `exec-8ec15314-052d-4aef-a646-dab1fc669ccb.png` | `generation#/products/13/path` |
| `exec-21cbd18b-5a80-4c76-9a88-0dbfc07eb1c0.png` | `generation#/products/14/path` |
| `exec-3d6da2b1-2028-495f-9a9d-68d81dbd2314.png` | `generation#/products/15/path` |
| `exec-03c91d74-8945-4e07-b3b2-97ddff498ccc.png` | `generation#/products/16/path` |
| `exec-c03f32cf-2219-401f-ab6e-8a1a785f1c48.png` | `generation#/products/17/path` |
| `exec-64bc8f23-9840-4b7f-a4c1-a1ab5ac0eefd.png` | `generation#/products/18/path` |
| `exec-75b7eff7-733f-4e83-9fd1-411545a7199e.png` | `generation#/products/19/path` |
| `exec-8b03abd7-8b3e-4496-9b25-6ffe921003d2.png` | `generation#/products/20/path` |
| `exec-9d3678e9-c1e9-4cd8-99e3-e141e8f61a30.png` | `generation#/products/21/path` |
| `exec-d78e06ea-6095-4138-9b6d-724b030d56c0.png` | `generation#/products/22/path` |
| `exec-e6e35914-2274-48c1-9149-a7d3ab47dfbc.png` | `generation#/products/23/path` |
| `exec-c58ef09d-18d2-4be7-ad4b-14b9863b44c5.png` | `generation#/products/24/path` |
| `exec-911f6e1a-7383-454c-b71e-a9bdf1fa7524.png` | `generation#/products/25/path` |
| `exec-2e1ce891-fd19-4db6-a1af-3c2949c19459.png` | `generation#/products/26/path` |
| `exec-6cdcdf16-d270-41b3-8137-ec13693b36e2.png` | `generation#/products/27/path` |
| `exec-5064356c-f9ac-4a5b-9156-576488be9994.png` | `generation#/products/28/path` |
| `exec-c32eafba-ad96-488f-83c1-b783ed120a64.png` | `generation#/products/29/path` |
| `exec-93904814-317d-4bba-89e6-147070bef51a.png` | `generation#/products/30/path` |
| `exec-7c934622-0525-49db-8a2a-368f1090c9b1.png` | `generation#/products/31/path` |
| `exec-9dc25ef2-4e90-4f6d-9685-cc56df123d9d.png` | `generation#/products/32/path` |
| `exec-cdfca26b-c41b-4e25-a734-d6b33e69de84.png` | `generation#/products/33/path` |
| `exec-8617a32c-0538-40b0-a34f-9b8ce61192ae.png` | `generation#/products/34/path` |
| `exec-fde622fa-9c44-4d5e-838f-0c031c92b041.png` | `generation#/products/35/path` |
| `exec-bee9077e-1b30-4d92-b01a-f5f73d966c6a.png` | `generation#/products/36/path` |
| `exec-9940fe7c-e8da-4418-b77f-dd1d86cc2282.png` | `generation#/products/37/path` |
| `exec-17f47aa9-bbc3-4f34-8261-4687f24df750.png` | `generation#/products/38/path` |
| `exec-d3420a1e-9439-4ce7-9140-7a35bea8f8ad.png` | `generation#/products/39/path` |
| `exec-3e2258fc-953c-4e99-829d-6db579cb893d.png` | `generation#/products/40/path` |
| `exec-42ce978d-b859-4ec8-b417-932ef3640754.png` | `generation#/products/41/path` |
| `exec-164ebb32-77d0-4439-b8d0-24204ab68119.png` | `generation#/products/42/path` |
| `exec-546b12d6-41d9-4f2c-badc-448459e5c531.png` | `generation#/products/43/path` |
| `exec-743734ee-49b9-4411-ac36-0473558931ab.png` | `generation#/products/44/path` |
| `exec-c7910e67-21a0-45a8-bab5-ce6cd06e4b75.png` | `generation#/products/45/path` |
| `exec-531ddc33-2040-47b8-bfe8-13ed8128188d.png` | `generation#/products/46/path` |
| `exec-568aac48-0909-4697-8790-06b626713419.png` | `generation#/products/47/path` |
| `exec-83c112de-aacd-45d0-92b3-a877d5cd2f85.png` | `generation#/products/48/path` |
| `exec-8c7c66ea-10ec-4db1-a905-0e18e4239b5a.png` | `generation#/products/49/path` |
| `exec-43226f50-0bb8-461b-8f4d-b74e34316c85.png` | `generation#/products/50/path` |
| `exec-b40d970d-059c-4808-abdd-e4895911f2c8.png` | `generation#/products/51/path` |
| `exec-7ca3bcc4-ec5e-4d0f-8883-1e6e42614f9f.png` | `generation#/products/52/path` |
| `exec-91662245-c72f-4e15-9d57-8918ac4340fb.png` | `generation#/products/53/path` |
| `exec-39086515-7506-444f-9624-43bcb01f69a0.png` | `generation#/products/54/path` |
| `exec-43c3cbd0-2c27-432c-8385-1d21c69a7221.png` | `generation#/products/55/path` |
| `exec-cf52a17b-f8be-4d2f-ba5e-c4a399ba5416.png` | `generation#/products/56/path` |
| `exec-d1995319-413a-4567-88ae-ed243c927259.png` | `generation#/products/57/path` |
| `exec-7dc14b0e-0e02-4e46-81cf-19beca1e2777.png` | `generation#/products/58/path` |
| `exec-542fb583-6076-4a17-a1f5-6e6d202cf167.png` | `generation#/products/59/path` |
| `exec-2cc715bb-7bf9-46d2-b073-45e62fe15643.png` | `generation#/products/60/path` |
| `exec-f3be8b53-01ad-49d2-9be5-6275dfdd9082.png` | `generation#/products/61/path` |
| `exec-73766963-15e0-471a-8d44-807e66a57a22.png` | `generation#/products/62/path` |
| `exec-cb1cf5ab-4ba5-46fc-b80f-48f1b8c32eac.png` | `generation#/products/63/path` |
| `exec-0621ccc2-9f40-41da-bad5-2f283c315d1a.png` | `generation#/products/64/path` |
| `exec-ce8b985a-e624-4ad3-94b9-27a55d617a84.png` | `generation#/products/65/path` |
| `exec-9b4897a8-4ed5-404b-a8ed-99552222d070.png` | `generation#/products/66/path` |
| `exec-31a09804-413e-4e56-b84c-b7e2a6bc8ca2.png` | `generation#/products/67/path` |
| `exec-3cfe9600-8d1b-449f-bf40-dc04bcdaf2e3.png` | `generation#/products/68/path` |
| `exec-53cf8495-e3e4-4e91-b784-cf927efed13a.png` | `generation#/products/69/path` |
| `exec-ec38b97d-5b4b-4e22-8c11-13a510ca301c.png` | `generation#/products/70/path` |
| `exec-0eeb2174-b451-4b6a-9d8b-e16f9615fe00.png` | `generation#/products/71/path` |
| `exec-4481437f-c2b2-46f0-8541-114a91f6e15c.png` | `generation#/products/72/path` |
| `exec-4b552e96-9884-4c80-ad71-a38b584a4320.png` | `generation#/products/73/path` |
| `exec-0fc55440-f6d2-4eec-81ef-fa9299e8004b.png` | `generation#/products/74/path` |
| `exec-02831528-d9ca-4401-9417-c81aba0f1e75.png` | `generation#/products/75/path` |
| `exec-9020e59e-1e27-482d-bbb6-c621d71b6bd2.png` | `generation#/products/76/path` |
| `exec-3c492a04-5da0-4d55-8936-33ff2bfebc1c.png` | `generation#/products/77/path` |
| `exec-f4399d9d-77a8-4763-900a-1baac2b275f7.png` | `generation#/products/78/path` |
| `exec-e96c271d-5a1b-4f95-b899-dfcfbf8f4df6.png` | `generation#/products/79/path` |
| `exec-e6681b97-9266-4acd-9737-f25625353fde.png` | `generation#/products/80/path` |
| `exec-59014888-06a8-47e1-b1ba-3ee14ffa3f03.png` | `generation#/products/81/path` |
| `exec-cf318c41-6c98-4fb9-bc82-968d46bf6d31.png` | `generation#/products/82/path` |
| `exec-2f2aa9df-e20e-4daa-9dce-c142193333f5.png` | `generation#/products/83/path` |
| `exec-4bd5c972-717d-474f-bb7e-4b7cf0b974a9.png` | `generation#/products/84/path` |
| `exec-6a1dfcb3-d104-48b0-b4b1-ba3ab29c425c.png` | `generation#/products/85/path` |
| `exec-81eebd89-c734-4547-8911-efab5962b7b5.png` | `generation#/products/86/path` |
| `exec-62db391d-b35e-4a3d-813e-a6fd81d4f2b5.png` | `generation#/products/87/path` |
| `exec-1011b27d-3cd4-4ab2-b65d-a97d1ce1da64.png` | `generation#/products/88/path` |
| `exec-d65088e3-49d1-4cbe-8613-78190ea214f3.png` | `generation#/products/89/path` |
| `exec-5caea232-76d1-4883-afb2-5d4532556f0b.png` | `generation#/products/90/path` |
| `exec-dd8a9710-e7b5-4fff-bd98-041075673eae.png` | `generation#/products/91/path` |
| `exec-278ae6bb-c2ad-4bcb-abbe-271b36d6deaf.png` | `generation#/products/92/path` |
| `exec-59ff29d9-cde6-47c7-9e78-168c39e6a3e8.png` | `generation#/products/93/path` |
| `exec-8a6714d2-b8d3-45e1-8f0d-d3082c9deab3.png` | `generation#/merchAndBoxes/0/path` |
| `exec-54eb3171-6461-44d9-b784-3d3c5976e951.png` | `generation#/merchAndBoxes/1/path` |
| `exec-ee1fc1a3-ffbe-42a9-84e9-0d303c3e9ff8.png` | `generation#/merchAndBoxes/2/path` |
| `exec-ff41d094-a0f5-401e-b063-2c6c278f9e46.png` | `generation#/merchAndBoxes/3/path` |
| `exec-04a87883-6be1-4c02-ac3f-4a51fa7e9856.png` | `generation#/merchAndBoxes/4/path` |
| `exec-6b5266dd-d4ca-4e61-bf43-ea705aec32af.png` | `generation#/merchAndBoxes/5/path` |
| `IMG_9714.jpg` | `generation#/merchAndBoxes/6/refs/0`, `generation#/merchAndBoxes/7/refs/0`, `generation#/merchAndBoxes/9/refs/0` |
| `IMG_9729.jpg` | `generation#/merchAndBoxes/6/refs/1`, `generation#/merchAndBoxes/7/refs/1`, `generation#/merchAndBoxes/9/refs/1`, `generation#/corrections/3/photo` |
| `IMG_9731.jpg` | `generation#/merchAndBoxes/6/refs/2`, `generation#/merchAndBoxes/7/refs/2`, `generation#/merchAndBoxes/9/refs/2`, `completion#/40/refs/0`, `completion#/41/refs/0`, `completion#/42/refs/0`, `completion#/43/refs/0`, `completion#/47/refs/0`, `completion#/71/refs/2`, `completion#/72/refs/2`, `completion#/73/refs/2` |
| `exec-4ec66962-e955-4102-b531-3d2d2bb85553.png` | `generation#/merchAndBoxes/6/path` |
| `exec-d78623ce-885a-4deb-b4b8-547828d6aea4.png` | `generation#/merchAndBoxes/7/path` |
| `exec-ad4d15ba-cd58-4a27-ad37-2a915c4bc6be.png` | `generation#/merchAndBoxes/8/path` |
| `exec-690052c7-52bc-463b-8fb2-a10e1bd6b55d.png` | `generation#/merchAndBoxes/9/path` |
| `exec-ef1b6083-6c77-425c-9f75-11b814b01089.png` | `generation#/corrections/0/path` |
| `IMG_9721.jpg` | `generation#/corrections/1/photo` |
| `exec-94688584-9440-4971-b931-821204074cf1.png` | `generation#/corrections/1/path` |
| `IMG_9722.jpg` | `generation#/corrections/2/photo`, `completion#/25/refs/0`, `completion#/26/refs/0`, `completion#/27/refs/0`, `completion#/32/refs/0` |
| `exec-38cd6ee5-d880-41dc-bcb4-74d7565c8ed0.png` | `generation#/corrections/2/path` |
| `exec-00db5a70-2098-48e1-93d3-f9530a9529dc.png` | `generation#/corrections/3/path` |
| `IMG_9723.jpg` | `generation#/firstProduct/source` |
| `exec-2d9d1339-8970-4931-8188-edfd0898a2dc.png` | `expanded#/0/path` |
| `exec-55275486-d2e0-4896-be95-32aa5ecb885c.png` | `expanded#/1/path` |
| `exec-9755a42c-3fd3-422a-9330-c06c207e645b.png` | `expanded#/2/path` |
| `exec-f17497ef-4769-44c3-9b40-82bf41f2aacf.png` | `expanded#/3/path` |
| `exec-6b5359a4-c258-4fcd-b566-e9aa1a99e2cc.png` | `expanded#/4/path` |
| `exec-f2917e1a-cac3-4141-9927-786933cc91bf.png` | `expanded#/5/path` |
| `exec-9b98f855-6704-43ca-ac9c-6e19c95878ba.png` | `expanded#/6/path` |
| `exec-f86fb616-57dd-4d8e-9c13-3551ed91f05c.png` | `expanded#/7/path` |
| `exec-97f65953-4d12-4a55-9cb5-5728afb19b0c.png` | `expanded#/8/path` |
| `IMG_9707.jpg` | `completion#/0/refs/0`, `completion#/2/refs/0`, `completion#/4/refs/0`, `completion#/6/refs/0` |
| `exec-1c7443d3-0e86-4ae4-823a-364ec1f231e5.png` | `completion#/0/path` |
| `IMG_9710.jpg` | `completion#/1/refs/0`, `completion#/3/refs/0`, `completion#/5/refs/0`, `completion#/7/refs/0`, `completion#/8/refs/0`, `completion#/9/refs/0`, `completion#/10/refs/0`, `completion#/11/refs/0`, `completion#/12/refs/0`, `completion#/13/refs/0`, `completion#/14/refs/0` |
| `exec-d80c0200-d981-4a52-8722-ca38f8b9904a.png` | `completion#/1/path` |
| `exec-bb8167d5-3649-464f-8028-df3c3a4838cb.png` | `completion#/2/path` |
| `exec-fd42213a-d5f4-48b6-afe2-1a448024414b.png` | `completion#/3/path` |
| `exec-e9c33499-06b9-41b7-a77b-bb798c94a882.png` | `completion#/4/path` |
| `exec-9f04cc6e-dcaa-4fd9-b5a1-bb15f98519a0.png` | `completion#/5/path` |
| `exec-1308baa8-b3c1-4a83-9986-de4e236264c6.png` | `completion#/6/path` |
| `exec-047316b9-b3a8-4ebb-8b42-b65570eb5eda.png` | `completion#/7/path` |
| `exec-6717f16e-10c1-41eb-a409-be94dc45dcb1.png` | `completion#/8/path` |
| `exec-4bcdc5e2-3112-4aee-ab22-245732433104.png` | `completion#/9/path` |
| `exec-281e520a-b212-44c3-a782-7aeffd9310c0.png` | `completion#/10/path` |
| `exec-866678bd-8f11-4079-9bcb-5c9a02410773.png` | `completion#/11/path` |
| `exec-26ca4f67-d519-4fbd-ab73-86b17a79113f.png` | `completion#/12/path` |
| `exec-0e401751-fd00-482d-9075-5be157a87134.png` | `completion#/13/path` |
| `exec-08650fa7-dba9-4daf-b51e-746dcc838c5e.png` | `completion#/14/path` |
| `IMG_9711.jpg` | `completion#/15/refs/0`, `completion#/16/refs/0` |
| `exec-70137bc7-b999-4a1e-ade4-f8efecadcce9.png` | `completion#/15/path` |
| `exec-2c5ab1a3-de04-4ae2-a9ab-6437fe092e95.png` | `completion#/16/path` |
| `IMG_9713.jpg` | `completion#/17/refs/0`, `completion#/18/refs/0`, `completion#/20/refs/0` |
| `exec-16dcfb26-f5a0-4ba3-a4bd-6e876b9baf86.png` | `completion#/17/path` |
| `exec-7fcdba3e-77e6-4c14-b06d-e7407b904e15.png` | `completion#/18/path` |
| `IMG_9719.jpg` | `completion#/19/refs/0`, `completion#/21/refs/0`, `completion#/22/refs/0` |
| `exec-00f14de3-0ebe-497b-8f31-03d1baf192e5.png` | `completion#/19/path` |
| `exec-020f95ec-7ed1-45ff-9d73-8cd2dc68a130.png` | `completion#/20/path` |
| `exec-d2d3ba6c-5aa6-477c-8bab-50ec4987d790.png` | `completion#/21/path` |
| `exec-2b277729-12cc-4167-8509-78207ae1a90b.png` | `completion#/22/path` |
| `IMG_9720.jpg` | `completion#/23/refs/0`, `completion#/24/refs/0` |
| `exec-2d77e937-9443-4116-8782-225a769fbf62.png` | `completion#/23/path` |
| `exec-8a40e224-48cc-49f1-b542-0e3ea5885c68.png` | `completion#/24/path` |
| `exec-a66d9bd2-5921-4045-8cf5-6158e49ba51e.png` | `completion#/25/path` |
| `exec-48420920-cccf-4847-b109-36200124b784.png` | `completion#/26/path` |
| `exec-bc212038-f0a0-4645-a728-f036e67b37b6.png` | `completion#/27/path` |
| `IMG_9724.jpg` | `completion#/28/refs/0`, `completion#/29/refs/0`, `completion#/30/refs/0`, `completion#/33/refs/0` |
| `exec-5585d3b8-42b3-4960-bf56-69bb718b3bc4.png` | `completion#/28/path` |
| `exec-1d4286ac-9375-471d-b5a8-4ac2e003f282.png` | `completion#/29/path` |
| `exec-1ba73ffc-fd8f-4303-ae9d-98c0a801cd3c.png` | `completion#/30/path` |
| `IMG_9728.jpg` | `completion#/31/refs/0`, `completion#/34/refs/0`, `completion#/35/refs/0`, `completion#/36/refs/0`, `completion#/37/refs/0`, `completion#/38/refs/0`, `completion#/39/refs/0` |
| `exec-d9e73f21-46ba-47ab-bc0d-93544cbb49a3.png` | `completion#/31/path` |
| `exec-07f3892b-88e7-4f81-9646-e684d08b0db2.png` | `completion#/32/path` |
| `exec-14dc869e-1158-4307-96e6-3dfb6e9c4726.png` | `completion#/33/path` |
| `exec-e1f9d211-867c-40ce-b800-3ae1b01d37a3.png` | `completion#/34/path` |
| `exec-a02bb8c0-04d9-441f-a67e-190b838348f4.png` | `completion#/35/path` |
| `exec-cfc888c1-5435-479f-a510-9119f4c26053.png` | `completion#/36/path` |
| `exec-772142b9-35ec-4f2f-b54a-0b51231db0c2.png` | `completion#/37/path` |
| `exec-09704f73-7795-4816-840b-9aa0efcb5db2.png` | `completion#/38/path` |
| `exec-0005104a-302b-4756-9579-470ba3bee52b.png` | `completion#/39/path` |
| `exec-fe97e3ef-97de-4d92-83f8-e952fe8853a8.png` | `completion#/40/path` |
| `exec-295591e9-2b92-4030-9a6c-a65b5af5463d.png` | `completion#/41/path` |
| `exec-c4dc9bc7-4759-4366-826f-0865a1387991.png` | `completion#/42/path` |
| `exec-d33f1ecd-13a3-4913-a0a5-92809b7a1403.png` | `completion#/43/path` |
| `IMG_9732.jpg` | `completion#/44/refs/0`, `completion#/45/refs/0`, `completion#/46/refs/0`, `completion#/48/refs/0`, `completion#/49/refs/0`, `completion#/50/refs/0`, `completion#/51/refs/0`, `image-final#/1/photo` |
| `exec-e3fbdb11-4e1b-4f16-9608-1dd6f95cb6ac.png` | `completion#/44/path` |
| `exec-ee6009e8-39cb-4763-94df-7fa8ce015ec3.png` | `completion#/45/path` |
| `exec-a4d8531c-c140-493a-8c7a-a3ed9d8f352d.png` | `completion#/46/path` |
| `exec-7d2481e9-5272-4d48-a6e7-f0ce218e41d3.png` | `completion#/47/path` |
| `exec-3a375593-9edb-437a-b320-4405fda6f067.png` | `completion#/48/path` |
| `exec-e9bf191c-e021-40c8-9d1e-2f8396f0e20a.png` | `completion#/49/path` |
| `exec-7d743133-b634-45b0-b89a-4a157bf2a351.png` | `completion#/50/path` |
| `exec-4f429877-62d4-4be3-a777-12e17708fcb8.png` | `completion#/51/path` |
| `IMG_9733.jpg` | `completion#/52/refs/0`, `completion#/53/refs/0`, `completion#/54/refs/0`, `completion#/55/refs/0`, `completion#/56/refs/0`, `completion#/57/refs/0`, `completion#/58/refs/0`, `completion#/59/refs/0`, `completion#/60/refs/0`, `completion#/61/refs/0` |
| `exec-3cbac061-4a7c-453a-953e-68d1b95f9e26.png` | `completion#/52/path` |
| `exec-6797c7aa-2c43-4ac1-b655-48d0e38953ed.png` | `completion#/53/path` |
| `exec-c23549db-e4fc-47b5-943a-02ed7ae855da.png` | `completion#/54/path` |
| `exec-0f65ed55-d3bd-4ac5-b794-ea5abe8806f7.png` | `completion#/55/path` |
| `exec-786d35e6-d624-4cbf-a7c3-c4b9b1b22abe.png` | `completion#/56/path` |
| `exec-58fdf8c4-22fe-42e7-be44-ba7f46ea6d89.png` | `completion#/57/path` |
| `exec-56b88b6a-90ec-4d61-b35e-a13621fa35b5.png` | `completion#/58/path` |
| `exec-0c798782-0888-4f89-8470-e8fcf80c57ba.png` | `completion#/59/path` |
| `exec-86e2ed02-9b2f-4db0-82ec-d8e5b01af0d8.png` | `completion#/60/path` |
| `exec-260de783-2f85-436a-9551-e0a34126ad88.png` | `completion#/61/path` |
| `IMG_9730.jpg` | `completion#/62/refs/0`, `completion#/71/refs/1`, `completion#/72/refs/1`, `completion#/73/refs/1` |
| `exec-f9d64a7c-6d2c-4d31-8196-d73c56a1f477.png` | `completion#/62/path` |
| `IMG_9734.jpg` | `completion#/63/refs/0`, `completion#/64/refs/0`, `completion#/66/refs/0`, `completion#/71/refs/3`, `completion#/72/refs/3`, `completion#/73/refs/3` |
| `exec-c150d55a-679b-4ed3-b5ff-5dcfcf072ce7.png` | `completion#/63/path` |
| `exec-ab59dc18-2239-49be-8233-e389b3d15236.png` | `completion#/64/path` |
| `IMG_9738.jpg` | `completion#/65/refs/0`, `completion#/67/refs/0`, `completion#/68/refs/0`, `completion#/70/refs/0` |
| `exec-f2b650d4-33fa-418f-8166-9ab3f51826d6.png` | `completion#/65/path` |
| `exec-3f399a63-bd3e-45d4-b640-960ae95e3810.png` | `completion#/66/path` |
| `exec-02449a6c-666c-48f2-9fd2-43d370a490eb.png` | `completion#/67/path` |
| `exec-157c0e1a-2808-416f-8648-d6d3e27c75d2.png` | `completion#/68/path` |
| `exec-e70e709e-180d-4797-8a87-ebb554bda5ef.png` | `completion#/69/path` |
| `exec-10dd3d96-e661-4e92-80cc-4fbc6bfd72b1.png` | `completion#/70/path` |
| `IMG_9715.jpg` | `completion#/71/refs/0`, `completion#/72/refs/0`, `completion#/73/refs/0` |
| `exec-a1e70c73-a8d9-465d-abd7-f0345d31ed2f.png` | `completion#/71/path` |
| `exec-47497f80-d5d6-4fb0-9b9d-0cfb3fbfc420.png` | `completion#/72/path` |
| `exec-00e17d70-b36a-4935-96bf-d00815cb0225.png` | `completion#/73/path` |
| `photo-product-140.png` | `final-image#/0/path` |
| `exec-f9bdec75-5b92-4d3b-9f49-0540a52acbbf.png` | `final-image#/0/resultHint` |
| `photo-product-141.png` | `final-image#/1/path` |
| `exec-b3225c4d-d6de-43f7-ab1b-facc428fc446.png` | `final-image#/1/resultHint` |
| `photo-product-129.png` | `final-image#/2/path` |
| `exec-7bcbfc87-d1d4-45cc-b831-708c3b0def34.png` | `final-image#/2/resultHint` |
| `photo-product-138.png` | `final-image#/3/path` |
| `exec-5a25e1c3-3655-4662-9df0-d533ec92c46a.png` | `final-image#/3/resultHint` |
| `photo-product-139.png` | `final-image#/4/path` |
| `exec-5544e116-64d4-4ed8-979d-11b70fa8f380.png` | `final-image#/4/resultHint` |
| `photo-product-142.png` | `final-image#/5/path` |
| `exec-965d1431-e6e5-4f80-9d53-39fe2bee790b.png` | `final-image#/5/resultHint` |
| `photo-product-143.png` | `final-image#/6/path` |
| `exec-2b9735dc-61c6-4318-a4ef-ce87e64dca75.png` | `final-image#/6/resultHint` |
| `photo-product-144.png` | `final-image#/7/path` |
| `exec-1968b554-6c74-4cf3-8073-3d9a63716950.png` | `final-image#/7/resultHint` |
| `IMG_9735.jpg` | `image-final#/0/photo` |
| `exec-33ed1477-5856-4b3e-84c9-57649b0157ce.png` | `image-final#/0/path` |
| `exec-b268c93f-adb6-4d17-a349-e655b959df94.png` | `image-final#/1/path` |
| `IMG_9736.jpg` | `image-final#/2/photo` |
| `exec-6f716a1e-cfe3-4047-8e51-1b8917b98c37.png` | `image-final#/2/path` |
