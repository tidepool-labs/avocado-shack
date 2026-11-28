# AVO1015-01 — Product data parity

| ID | File | Food records | Other product records | Read by the current catalog? |
|---|---|---:|---:|---|
| C | `storefront-mockup/catalog.json` | 95 | 0 | No |
| S | `storefront-mockup/shop-data.json` | 170 | 11 (8 merch, 3 boxes) | No |
| N | `storefront-mockup/new-products.json` | 9 | 0 | No |
| P | `storefront-mockup/completion-new-products.json` | 70 | 0 | No |
| H | `hass/content/products.json` | 172 (170 active, 2 held) | 0 | Indirectly, via `catalog-products.js` |

**The five files do not agree.** The union is 174 food products, or 185 records including historic merch and boxes. No product is in all five files. The 170 S food rows agree with the 170 active H rows on raw ID, name, brand, category and display image path. The checked-in storefront output also agrees with those active H rows on all five fields. The differences are between historical snapshots or between historical and current source, not evidence of two current pages showing different versions (R1–R3).

Read-only comparison on **2026-11-21 PST** at `origin/main` **`37feae1dc5efa6968f90d17a1eda6daed29afd4a`**. The five inputs, storefront readers, extraction and the inspected site generation/NPP readers had no diff from `1f8510907cb2989bb50391fde45d6211e4735879` in the paths checked. All counts and tables below are dated results from those Git blobs. No live site, Hass instance, photo originals or image pixels were checked. No inference about current stock, rights, claim truth or whether to restore or remove anything.

## R1. Presence and matches

The five file IDs above stand for the full paths. `C#/0`, for example, means the first record at JSON pointer `/0` in `storefront-mockup/catalog.json`. The pointer alone in a file's R1 column means **present**; `—` means **absent**. Food comes from the top-level array (C, N, P) or `/products` (S, H). The historical `/merch` and `/boxes` rows are included separately; box component references are not rows. The CSV is extraction evidence, not a sixth source (`storefront-mockup/catalog-extraction.csv:1–2` identifies the fields and the first catalog ID).

Match exact `id` strings first. For unmatched identities, check normalized name: Unicode case-fold, NFKD, drop combining marks and keep only letters and digits. Only a unique, non-conflicting cross-file name would qualify; no fuzzy or manual merges. **Name fallback matches: none.** All food rows had IDs, no ID appeared twice within a source and no normalized food name with a different ID qualified. For the display label in the matrix, prefer H, then S, C, N, P; raw name differences are in R2.

| Food presence pattern | Products |
|---|---:|
| C, S, H | 92 |
| S, P, H | 69 |
| S, N, H | 9 |
| C only | 2 |
| C, H | 1 |
| P, H | 1 |

The two C-only rows are `photo-product-020` (C#/19) and `photo-product-036` (C#/35). The two H rows absent from S are `photo-product-040` (H#/products/170/status) and `photo-product-133` (H#/products/171/status); both are `"held"`. They are not missing active listings. Every N and P food ID has an H row.

### Food product matrix

| ID | Name | C | S | N | P | H |
| --- | --- | --- | --- | --- | --- | --- |
| `"photo-product-001"` | `"Hass avocado"` | `C#/0` | `S#/products/0` | — | — | `H#/products/0` |
| `"photo-product-002"` | `"Linn's triple berry preserves"` | `C#/1` | `S#/products/1` | — | — | `H#/products/90` |
| `"photo-product-003"` | `"Linn's blueberry preserves"` | `C#/2` | `S#/products/2` | — | — | `H#/products/91` |
| `"photo-product-004"` | `"Linn's boysenberry preserves"` | `C#/3` | `S#/products/3` | — | — | `H#/products/92` |
| `"photo-product-005"` | `"Linn's orange marmalade"` | `C#/4` | `S#/products/4` | — | — | `H#/products/93` |
| `"photo-product-006"` | `"Mixed flower bouquet"` | `C#/5` | `S#/products/5` | — | — | `H#/products/169` |
| `"photo-product-007"` | `"Fair Hills Farm apple juice"` | `C#/6` | `S#/products/6` | — | — | `H#/products/154` |
| `"photo-product-008"` | `"Cal Poly strawberry jam"` | `C#/7` | `S#/products/7` | — | — | `H#/products/94` |
| `"photo-product-009"` | `"Cal Poly raspberry jam"` | `C#/8` | `S#/products/8` | — | — | `H#/products/95` |
| `"photo-product-010"` | `"Cal Poly blackberry jam"` | `C#/9` | `S#/products/9` | — | — | `H#/products/96` |
| `"photo-product-011"` | `"Sweet Hickory BBQ sauce"` | `C#/10` | `S#/products/10` | — | — | `H#/products/97` |
| `"photo-product-012"` | `"Cal Poly chocolate"` | `C#/11` | `S#/products/11` | — | — | `H#/products/98` |
| `"photo-product-013"` | `"Original hot sauce"` | `C#/12` | `S#/products/12` | — | — | `H#/products/99` |
| `"photo-product-014"` | `"Zero non-alcoholic cider"` | `C#/13` | `S#/products/13` | — | — | `H#/products/155` |
| `"photo-product-015"` | `"Brian's sourdough bread"` | `C#/14` | `S#/products/14` | — | — | `H#/products/86` |
| `"photo-product-016"` | `"Oranges"` | `C#/15` | `S#/products/15` | — | — | `H#/products/1` |
| `"photo-product-017"` | `"Lemons"` | `C#/16` | `S#/products/16` | — | — | `H#/products/2` |
| `"photo-product-018"` | `"Montaña de Oro Sea Salt tortilla chips"` | `C#/17` | `S#/products/17` | — | — | `H#/products/13` |
| `"photo-product-019"` | `"Organic beet juice"` | `C#/18` | `S#/products/18` | — | — | `H#/products/156` |
| `"photo-product-020"` | `"Bottled juice"` | `C#/19` | — | — | — | — |
| `"photo-product-021"` | `"Alle-Pia Calabrese salamini"` | `C#/20` | `S#/products/19` | — | — | `H#/products/151` |
| `"photo-product-022"` | `"Alle-Pia guanciale"` | `C#/21` | `S#/products/20` | — | — | `H#/products/152` |
| `"photo-product-023"` | `"Alle-Pia mortadella"` | `C#/22` | `S#/products/21` | — | — | `H#/products/153` |
| `"photo-product-024"` | `"Cal Poly eggs"` | `C#/23` | `S#/products/22` | — | — | `H#/products/65` |
| `"photo-product-025"` | `"Straus half-and-half"` | `C#/24` | `S#/products/23` | — | — | `H#/products/66` |
| `"photo-product-026"` | `"Straus heavy whipping cream"` | `C#/25` | `S#/products/24` | — | — | `H#/products/67` |
| `"photo-product-027"` | `"Organic whole milk"` | `C#/26` | `S#/products/25` | — | — | `H#/products/68` |
| `"photo-product-028"` | `"Straus butter"` | `C#/27` | `S#/products/26` | — | — | `H#/products/69` |
| `"photo-product-029"` | `"Ragged Point cheese"` | `C#/28` | `S#/products/27` | — | — | `H#/products/70` |
| `"photo-product-030"` | `"Stepladder cultured butter"` | `C#/29` | `S#/products/28` | — | — | `H#/products/71` |
| `"photo-product-031"` | `"Guacamole"` | `C#/30` | `S#/products/29` | — | — | `H#/products/100` |
| `"photo-product-032"` | `"Garlic pesto"` | `C#/31` | `S#/products/30` | — | — | `H#/products/101` |
| `"photo-product-033"` | `"Stepladder Rocky Butte cheese"` | `C#/32` | `S#/products/31` | — | — | `H#/products/72` |
| `"photo-product-034"` | `"Stepladder Bixby cheese"` | `C#/33` | `S#/products/32` | — | — | `H#/products/73` |
| `"photo-product-035"` | `"Chèvre"` | `C#/34` | `S#/products/33` | — | — | `H#/products/74` |
| `"photo-product-036"` | `"Eggs"` | `C#/35` | — | — | — | — |
| `"photo-product-037"` | `"Cal Poly chipotle cheddar"` | `C#/36` | `S#/products/34` | — | — | `H#/products/75` |
| `"photo-product-038"` | `"Cal Poly white cheddar"` | `C#/37` | `S#/products/35` | — | — | `H#/products/76` |
| `"photo-product-039"` | `"Cal Poly Highland cheddar"` | `C#/38` | `S#/products/36` | — | — | `H#/products/77` |
| `"photo-product-040"` | `"Raw milk white cheddar"` | `C#/39` | — | — | — | `H#/products/170` |
| `"photo-product-041"` | `"Stepladder avocado blossom honey"` | `C#/40` | `S#/products/37` | — | — | `H#/products/102` |
| `"photo-product-042"` | `"Big Sur Honey Company honey"` | `C#/41` | `S#/products/38` | — | — | `H#/products/103` |
| `"photo-product-043"` | `"Sunshine Estate olive oil"` | `C#/42` | `S#/products/39` | — | — | `H#/products/104` |
| `"photo-product-044"` | `"Dried mushrooms"` | `C#/43` | `S#/products/40` | — | — | `H#/products/105` |
| `"photo-product-045"` | `"Sunshine Olive Spanish Oaks Picual olive oil"` | `C#/44` | `S#/products/41` | — | — | `H#/products/106` |
| `"photo-product-046"` | `"Dried lion’s mane mushrooms"` | `C#/45` | `S#/products/42` | — | — | `H#/products/107` |
| `"photo-product-047"` | `"Dried maitake mushrooms"` | `C#/46` | `S#/products/43` | — | — | `H#/products/108` |
| `"photo-product-048"` | `"Fair Hills Farm chamomile tea"` | `C#/47` | `S#/products/44` | — | — | `H#/products/157` |
| `"photo-product-049"` | `"Fair Hills Farm black tea"` | `C#/48` | `S#/products/45` | — | — | `H#/products/158` |
| `"photo-product-050"` | `"Fair Hills Farm cinnamon black tea"` | `C#/49` | `S#/products/46` | — | — | `H#/products/159` |
| `"photo-product-051"` | `"Ginger black tea"` | `C#/50` | `S#/products/47` | — | — | `H#/products/160` |
| `"photo-product-052"` | `"Maple Valley dark and robust maple syrup"` | `C#/51` | `S#/products/48` | — | — | `H#/products/109` |
| `"photo-product-053"` | `"Sean's muesli munch"` | `C#/52` | `S#/products/49` | — | — | `H#/products/110` |
| `"photo-product-054"` | `"Massa Organics brown rice"` | `C#/53` | `S#/products/50` | — | — | `H#/products/111` |
| `"photo-product-055"` | `"Cashews"` | `C#/54` | `S#/products/51` | — | — | `H#/products/112` |
| `"photo-product-056"` | `"Strawberries"` | `C#/55` | `S#/products/52` | — | — | `H#/products/3` |
| `"photo-product-057"` | `"Raspberries"` | `C#/56` | `S#/products/53` | — | — | `H#/products/4` |
| `"photo-product-058"` | `"Blueberries"` | `C#/57` | `S#/products/54` | — | — | `H#/products/5` |
| `"photo-product-059"` | `"Golden raspberries"` | `C#/58` | `S#/products/55` | — | — | `H#/products/6` |
| `"photo-product-060"` | `"Fennel"` | `C#/59` | `S#/products/56` | — | — | `H#/products/14` |
| `"photo-product-061"` | `"Broccoli"` | `C#/60` | `S#/products/57` | — | — | `H#/products/15` |
| `"photo-product-062"` | `"Romaine lettuce"` | `C#/61` | `S#/products/58` | — | — | `H#/products/16` |
| `"photo-product-063"` | `"Bok choy"` | `C#/62` | `S#/products/59` | — | — | `H#/products/17` |
| `"photo-product-064"` | `"Leeks"` | `C#/63` | `S#/products/60` | — | — | `H#/products/18` |
| `"photo-product-065"` | `"Celery"` | `C#/64` | `S#/products/61` | — | — | `H#/products/19` |
| `"photo-product-066"` | `"Bunched carrots"` | `C#/65` | `S#/products/62` | — | — | `H#/products/20` |
| `"photo-product-067"` | `"Potatoes"` | `C#/66` | `S#/products/63` | — | — | `H#/products/21` |
| `"photo-product-068"` | `"Lettuce"` | `C#/67` | `S#/products/64` | — | — | `H#/products/22` |
| `"photo-product-069"` | `"Spring Greens"` | `C#/68` | `S#/products/65` | — | — | `H#/products/23` |
| `"photo-product-070"` | `"Wild Arugula"` | `C#/69` | `S#/products/66` | — | — | `H#/products/24` |
| `"photo-product-071"` | `"Mushrooms"` | `C#/70` | `S#/products/67` | — | — | `H#/products/25` |
| `"photo-product-072"` | `"Sunflower microgreens"` | `C#/71` | `S#/products/68` | — | — | `H#/products/26` |
| `"photo-product-073"` | `"Ginger"` | `C#/72` | `S#/products/69` | — | — | `H#/products/27` |
| `"photo-product-074"` | `"Turmeric"` | `C#/73` | `S#/products/70` | — | — | `H#/products/28` |
| `"photo-product-075"` | `"Eggplant"` | `C#/74` | `S#/products/71` | — | — | `H#/products/29` |
| `"photo-product-076"` | `"Peppers"` | `C#/75` | `S#/products/72` | — | — | `H#/products/30` |
| `"photo-product-077"` | `"Tomatoes"` | `C#/76` | `S#/products/73` | — | — | `H#/products/31` |
| `"photo-product-078"` | `"Watermelon"` | `C#/77` | `S#/products/74` | — | — | `H#/products/7` |
| `"photo-product-079"` | `"Cantaloupe"` | `C#/78` | `S#/products/75` | — | — | `H#/products/32` |
| `"photo-product-080"` | `"Honeydew-type melon"` | `C#/79` | `S#/products/76` | — | — | `H#/products/8` |
| `"photo-product-081"` | `"Keitt mango"` | `C#/80` | `S#/products/77` | — | — | `H#/products/9` |
| `"photo-product-082"` | `"Artisan short-cut pasta"` | `C#/81` | `S#/products/78` | — | — | `H#/products/113` |
| `"photo-product-083"` | `"Albino Coast Redwood Blend"` | `C#/82` | `S#/products/79` | — | — | `H#/products/161` |
| `"photo-product-084"` | `"Cone Peak Blend"` | `C#/83` | `S#/products/80` | — | — | `H#/products/162` |
| `"photo-product-085"` | `"Dream Girl Decaf"` | `C#/84` | `S#/products/81` | — | — | `H#/products/163` |
| `"photo-product-086"` | `"Peace Be With You Blend"` | `C#/85` | `S#/products/82` | — | — | `H#/products/164` |
| `"photo-product-087"` | `"Packer’s Blend coffee bags"` | `C#/86` | `S#/products/83` | — | — | `H#/products/165` |
| `"photo-product-088"` | `"Cranberry Orange granola"` | `C#/87` | `S#/products/84` | — | — | `H#/products/114` |
| `"photo-product-089"` | `"Oaxacan Chocolate granola"` | `C#/88` | `S#/products/85` | — | — | `H#/products/115` |
| `"photo-product-090"` | `"Lemon Blueberry granola"` | `C#/89` | `S#/products/86` | — | — | `H#/products/116` |
| `"photo-product-091"` | `"Turmeric Goji Berry granola"` | `C#/90` | `S#/products/87` | — | — | `H#/products/117` |
| `"photo-product-092"` | `"Avocado Shack Blend (Hut)"` | `C#/91` | `S#/products/88` | — | — | `H#/products/166` |
| `"photo-product-093"` | `"Avocado Shack (Hands)"` | `C#/92` | `S#/products/89` | — | — | `H#/products/118` |
| `"photo-product-094"` | `"Cass Hill Blend"` | `C#/93` | `S#/products/90` | — | — | `H#/products/167` |
| `"photo-product-095"` | `"Cambria Blend"` | `C#/94` | `S#/products/91` | — | — | `H#/products/168` |
| `"photo-product-096"` | `"Passion fruit"` | — | `S#/products/92` | `N#/0` | — | `H#/products/10` |
| `"photo-product-097"` | `"Figs"` | — | `S#/products/93` | `N#/1` | — | `H#/products/11` |
| `"photo-product-098"` | `"Blackberries"` | — | `S#/products/94` | `N#/2` | — | `H#/products/12` |
| `"photo-product-099"` | `"Garlic"` | — | `S#/products/95` | `N#/3` | — | `H#/products/33` |
| `"photo-product-100"` | `"Shallots"` | — | `S#/products/96` | `N#/4` | — | `H#/products/34` |
| `"photo-product-101"` | `"Yellow onions"` | — | `S#/products/97` | `N#/5` | — | `H#/products/35` |
| `"photo-product-102"` | `"Red onions"` | — | `S#/products/98` | `N#/6` | — | `H#/products/36` |
| `"photo-product-103"` | `"Radicchio"` | — | `S#/products/99` | `N#/7` | — | `H#/products/37` |
| `"photo-product-104"` | `"Purple daikon"` | — | `S#/products/100` | `N#/8` | — | `H#/products/38` |
| `"photo-product-105"` | `"Sunshine Peach preserves"` | — | `S#/products/101` | — | `P#/0` | `H#/products/119` |
| `"photo-product-106"` | `"Strawberry preserves"` | — | `S#/products/102` | — | `P#/1` | `H#/products/120` |
| `"photo-product-107"` | `"California Apricot preserves"` | — | `S#/products/103` | — | `P#/2` | `H#/products/121` |
| `"photo-product-108"` | `"Blood Orange marmalade"` | — | `S#/products/104` | — | `P#/3` | `H#/products/122` |
| `"photo-product-109"` | `"Peppermint Crunch chocolate"` | — | `S#/products/105` | — | `P#/4` | `H#/products/123` |
| `"photo-product-110"` | `"Cookies and Cream chocolate"` | — | `S#/products/106` | — | `P#/5` | `H#/products/124` |
| `"photo-product-111"` | `"Zesty Orange chocolate"` | — | `S#/products/107` | — | `P#/6` | `H#/products/125` |
| `"photo-product-112"` | `"Dark chocolate"` | — | `S#/products/108` | — | `P#/7` | `H#/products/126` |
| `"photo-product-113"` | `"Milk chocolate"` | — | `S#/products/109` | — | `P#/8` | `H#/products/127` |
| `"photo-product-114"` | `"Lemon Bar white chocolate"` | — | `S#/products/110` | — | `P#/9` | `H#/products/128` |
| `"photo-product-115"` | `"Habanero chocolate"` | — | `S#/products/111` | — | `P#/10` | `H#/products/129` |
| `"photo-product-116"` | `"S’mores chocolate"` | — | `S#/products/112` | — | `P#/11` | `H#/products/130` |
| `"photo-product-117"` | `"Lemon Lavender white chocolate"` | — | `S#/products/113` | — | `P#/12` | `H#/products/131` |
| `"photo-product-118"` | `"Birthday Cake chocolate"` | — | `S#/products/114` | — | `P#/13` | `H#/products/132` |
| `"photo-product-119"` | `"Mustang Kick BBQ sauce"` | — | `S#/products/115` | — | `P#/14` | `H#/products/133` |
| `"photo-product-120"` | `"Carrot Habanero hot sauce"` | — | `S#/products/116` | — | `P#/15` | `H#/products/134` |
| `"photo-product-121"` | `"Green hot sauce"` | — | `S#/products/117` | — | `P#/16` | `H#/products/135` |
| `"photo-product-122"` | `"Rye bread"` | — | `S#/products/118` | — | `P#/17` | `H#/products/87` |
| `"photo-product-123"` | `"Rosemary Sourdough with Olive Oil"` | — | `S#/products/119` | — | `P#/18` | `H#/products/88` |
| `"photo-product-124"` | `"Cracked Wheat Sourdough"` | — | `S#/products/120` | — | `P#/19` | `H#/products/89` |
| `"photo-product-125"` | `"Whole Milk Plain European Style yogurt"` | — | `S#/products/121` | — | `P#/20` | `H#/products/78` |
| `"photo-product-126"` | `"Greek Whole Milk Plain yogurt"` | — | `S#/products/122` | — | `P#/21` | `H#/products/79` |
| `"photo-product-127"` | `"Sour cream"` | — | `S#/products/123` | — | `P#/22` | `H#/products/80` |
| `"photo-product-128"` | `"Big Sur cheese"` | — | `S#/products/124` | — | `P#/23` | `H#/products/81` |
| `"photo-product-129"` | `"Marinated Fromage Blanc"` | — | `S#/products/125` | — | `P#/24` | `H#/products/82` |
| `"photo-product-130"` | `"Gouda"` | — | `S#/products/126` | — | `P#/25` | `H#/products/83` |
| `"photo-product-131"` | `"Hatch Chile Sierra Jack"` | — | `S#/products/127` | — | `P#/26` | `H#/products/84` |
| `"photo-product-132"` | `"Habanero Sierra Jack"` | — | `S#/products/128` | — | `P#/27` | `H#/products/85` |
| `"photo-product-133"` | `"Raw Milk Goat Cheddar"` | — | — | — | `P#/28` | `H#/products/171` |
| `"photo-product-134"` | `"Dried morels"` | — | `S#/products/129` | — | `P#/29` | `H#/products/136` |
| `"photo-product-135"` | `"Dried shiitake"` | — | `S#/products/130` | — | `P#/30` | `H#/products/137` |
| `"photo-product-136"` | `"Dried king oyster mushrooms"` | — | `S#/products/131` | — | `P#/31` | `H#/products/138` |
| `"photo-product-137"` | `"Mushroom Umami Sauce"` | — | `S#/products/132` | — | `P#/32` | `H#/products/139` |
| `"photo-product-138"` | `"Crimson lentils"` | — | `S#/products/133` | — | `P#/33` | `H#/products/140` |
| `"photo-product-139"` | `"Red beans"` | — | `S#/products/134` | — | `P#/34` | `H#/products/141` |
| `"photo-product-140"` | `"Black beans"` | — | `S#/products/135` | — | `P#/35` | `H#/products/142` |
| `"photo-product-141"` | `"Chickpeas"` | — | `S#/products/136` | — | `P#/36` | `H#/products/143` |
| `"photo-product-142"` | `"Almonds"` | — | `S#/products/137` | — | `P#/37` | `H#/products/144` |
| `"photo-product-143"` | `"Pistachios"` | — | `S#/products/138` | — | `P#/38` | `H#/products/145` |
| `"photo-product-144"` | `"Trail mix"` | — | `S#/products/139` | — | `P#/39` | `H#/products/146` |
| `"photo-product-145"` | `"Gold potatoes"` | — | `S#/products/140` | — | `P#/40` | `H#/products/39` |
| `"photo-product-146"` | `"Red potatoes"` | — | `S#/products/141` | — | `P#/41` | `H#/products/40` |
| `"photo-product-147"` | `"Purple potatoes"` | — | `S#/products/142` | — | `P#/42` | `H#/products/41` |
| `"photo-product-148"` | `"Loose carrots"` | — | `S#/products/143` | — | `P#/43` | `H#/products/42` |
| `"photo-product-149"` | `"Green cabbage"` | — | `S#/products/144` | — | `P#/44` | `H#/products/43` |
| `"photo-product-150"` | `"Lion’s mane mushrooms"` | — | `S#/products/145` | — | `P#/45` | `H#/products/44` |
| `"photo-product-151"` | `"King oyster mushrooms"` | — | `S#/products/146` | — | `P#/46` | `H#/products/45` |
| `"photo-product-152"` | `"Shiitake mushrooms"` | — | `S#/products/147` | — | `P#/47` | `H#/products/46` |
| `"photo-product-153"` | `"Maitake mushrooms"` | — | `S#/products/148` | — | `P#/48` | `H#/products/47` |
| `"photo-product-154"` | `"Chanterelle mushrooms"` | — | `S#/products/149` | — | `P#/49` | `H#/products/48` |
| `"photo-product-155"` | `"Lobster mushrooms"` | — | `S#/products/150` | — | `P#/50` | `H#/products/49` |
| `"photo-product-156"` | `"Crimini mushrooms"` | — | `S#/products/151` | — | `P#/51` | `H#/products/50` |
| `"photo-product-157"` | `"Cilantro microgreens"` | — | `S#/products/152` | — | `P#/52` | `H#/products/51` |
| `"photo-product-158"` | `"Radish Mix microgreens"` | — | `S#/products/153` | — | `P#/53` | `H#/products/52` |
| `"photo-product-159"` | `"Arugula microgreens"` | — | `S#/products/154` | — | `P#/54` | `H#/products/53` |
| `"photo-product-160"` | `"Broccoli microgreens"` | — | `S#/products/155` | — | `P#/55` | `H#/products/54` |
| `"photo-product-161"` | `"Horseradish"` | — | `S#/products/156` | — | `P#/56` | `H#/products/55` |
| `"photo-product-162"` | `"Jalapeños"` | — | `S#/products/157` | — | `P#/57` | `H#/products/56` |
| `"photo-product-163"` | `"Sweet peppers"` | — | `S#/products/158` | — | `P#/58` | `H#/products/57` |
| `"photo-product-164"` | `"Red bell peppers"` | — | `S#/products/159` | — | `P#/59` | `H#/products/58` |
| `"photo-product-165"` | `"Poblano peppers"` | — | `S#/products/160` | — | `P#/60` | `H#/products/59` |
| `"photo-product-166"` | `"Zucchini"` | — | `S#/products/161` | — | `P#/61` | `H#/products/60` |
| `"photo-product-167"` | `"Green onions"` | — | `S#/products/162` | — | `P#/62` | `H#/products/61` |
| `"photo-product-168"` | `"San Marzano tomatoes"` | — | `S#/products/163` | — | `P#/63` | `H#/products/62` |
| `"photo-product-169"` | `"Cherry tomatoes"` | — | `S#/products/164` | — | `P#/64` | `H#/products/63` |
| `"photo-product-170"` | `"Sun Gold tomatoes"` | — | `S#/products/165` | — | `P#/65` | `H#/products/64` |
| `"photo-product-171"` | `"Radiatori pasta"` | — | `S#/products/166` | — | `P#/66` | `H#/products/147` |
| `"photo-product-172"` | `"Rigatoni pasta"` | — | `S#/products/167` | — | `P#/67` | `H#/products/148` |
| `"photo-product-173"` | `"Casarecce pasta"` | — | `S#/products/168` | — | `P#/68` | `H#/products/149` |
| `"photo-product-174"` | `"Conchiglie pasta"` | — | `S#/products/169` | — | `P#/69` | `H#/products/150` |

### Shop-data-only historical merch and boxes

| ID | Name | C | S | N | P | H |
| --- | --- | --- | --- | --- | --- | --- |
| `"merch-tee"` | `"The Original Shack Tee"` | — | `S#/merch/0` | — | — | — |
| `"merch-coast"` | `"Morro Bay Coast Tee"` | — | `S#/merch/1` | — | — | — |
| `"merch-sweat"` | `"Fog Morning Crewneck"` | — | `S#/merch/2` | — | — | — |
| `"merch-mug"` | `"Morning at the Shack Mug"` | — | `S#/merch/3` | — | — | — |
| `"merch-tote"` | `"Market Day Tote"` | — | `S#/merch/4` | — | — | — |
| `"merch-cap"` | `"Shack Cap"` | — | `S#/merch/5` | — | — | — |
| `"merch-stickers"` | `"Coastal Sticker Pack"` | — | `S#/merch/6` | — | — | — |
| `"merch-bottle"` | `"Coastal Market Bottle"` | — | `S#/merch/7` | — | — | — |
| `"box-small"` | `"Small Vegetable Box"` | — | `S#/boxes/0` | — | — | — |
| `"box-medium"` | `"Medium Vegetable Box"` | — | `S#/boxes/1` | — | — | — |
| `"box-large"` | `"Large Vegetable Box"` | — | `S#/boxes/2` | — | — | — |

## R2. Every differing field for matched products

Each line groups equal values from all present sources and gives the pointer for each source; different groups on the same line are the disagreements. A missing key gives the pointer where that key would be. `""` is a stored empty string, not an absent key. `image` is the display asset reference; `photo` is the source filename and `photos` the source filename list. They are compared separately, not treated as interchangeable. `brand`, `category` and `notes` are the literal keys, not `displayBrand`, `legacyCategory`, `description`, `hold` or `evidence`. No filename comparison proves that two images depict the same item.

| Field | Food products with a difference (of 172 matched) |
|---|---:|
| `id` | 0 |
| `name` | 21 |
| `brand` | 15 |
| `category` | 64 |
| `image` | 93 |
| `photo` | 172 (H has no key) |
| `photos` | 172 (H has no key) |
| `notes` | 172 (H has no key) |

### Identity, category and display asset

| Product ID | Field | Quoted values and locations |
| --- | --- | --- |
| `"photo-product-001"` | `category` | `"produce"` — `C#/0/category`; `"fruit"` — `S#/products/0/category`, `H#/products/0/category` |
| `"photo-product-001"` | `image` | `"assets/catalog/IMG_9714.jpg"` — `C#/0/image`; `"assets/products/photo-product-001.webp"` — `S#/products/0/image`, `H#/products/0/image` |
| `"photo-product-002"` | `image` | `"assets/catalog/IMG_9707.jpg"` — `C#/1/image`; `"assets/products/photo-product-002.webp"` — `S#/products/1/image`, `H#/products/90/image` |
| `"photo-product-003"` | `image` | `"assets/catalog/IMG_9707.jpg"` — `C#/2/image`; `"assets/products/photo-product-003.webp"` — `S#/products/2/image`, `H#/products/91/image` |
| `"photo-product-004"` | `image` | `"assets/catalog/IMG_9707.jpg"` — `C#/3/image`; `"assets/products/photo-product-004.webp"` — `S#/products/3/image`, `H#/products/92/image` |
| `"photo-product-005"` | `image` | `"assets/catalog/IMG_9707.jpg"` — `C#/4/image`; `"assets/products/photo-product-005.webp"` — `S#/products/4/image`, `H#/products/93/image` |
| `"photo-product-006"` | `image` | `"assets/catalog/IMG_9708.jpg"` — `C#/5/image`; `"assets/products/photo-product-006.webp"` — `S#/products/5/image`, `H#/products/169/image` |
| `"photo-product-007"` | `category` | `"pantry"` — `C#/6/category`; `"drinks"` — `S#/products/6/category`, `H#/products/154/category` |
| `"photo-product-007"` | `image` | `"assets/catalog/IMG_9709.jpg"` — `C#/6/image`; `"assets/products/photo-product-007.webp"` — `S#/products/6/image`, `H#/products/154/image` |
| `"photo-product-008"` | `image` | `"assets/catalog/IMG_9710.jpg"` — `C#/7/image`; `"assets/products/photo-product-008.webp"` — `S#/products/7/image`, `H#/products/94/image` |
| `"photo-product-009"` | `image` | `"assets/catalog/IMG_9710.jpg"` — `C#/8/image`; `"assets/products/photo-product-009.webp"` — `S#/products/8/image`, `H#/products/95/image` |
| `"photo-product-010"` | `image` | `"assets/catalog/IMG_9710.jpg"` — `C#/9/image`; `"assets/products/photo-product-010.webp"` — `S#/products/9/image`, `H#/products/96/image` |
| `"photo-product-011"` | `name` | `"Cal Poly barbecue sauce"` — `C#/10/name`; `"Sweet Hickory BBQ sauce"` — `S#/products/10/name`, `H#/products/97/name` |
| `"photo-product-011"` | `image` | `"assets/catalog/IMG_9710.jpg"` — `C#/10/image`; `"assets/products/photo-product-011.webp"` — `S#/products/10/image`, `H#/products/97/image` |
| `"photo-product-012"` | `image` | `"assets/catalog/IMG_9710.jpg"` — `C#/11/image`; `"assets/products/photo-product-012.webp"` — `S#/products/11/image`, `H#/products/98/image` |
| `"photo-product-013"` | `name` | `"Cayucos hot sauce"` — `C#/12/name`; `"Original hot sauce"` — `S#/products/12/name`, `H#/products/99/name` |
| `"photo-product-013"` | `image` | `"assets/catalog/IMG_9711.jpg"` — `C#/12/image`; `"assets/products/photo-product-013.webp"` — `S#/products/12/image`, `H#/products/99/image` |
| `"photo-product-014"` | `name` | `"SLO cider"` — `C#/13/name`; `"Zero non-alcoholic cider"` — `S#/products/13/name`, `H#/products/155/name` |
| `"photo-product-014"` | `brand` | `"SLO"` — `C#/13/brand`; `"SLO Cider"` — `S#/products/13/brand`, `H#/products/155/brand` |
| `"photo-product-014"` | `category` | `"pantry"` — `C#/13/category`; `"drinks"` — `S#/products/13/category`, `H#/products/155/category` |
| `"photo-product-014"` | `image` | `"assets/catalog/IMG_9712.jpg"` — `C#/13/image`; `"assets/products/photo-product-014.webp"` — `S#/products/13/image`, `H#/products/155/image` |
| `"photo-product-015"` | `image` | `"assets/catalog/IMG_9713.jpg"` — `C#/14/image`; `"assets/products/photo-product-015.webp"` — `S#/products/14/image`, `H#/products/86/image` |
| `"photo-product-016"` | `category` | `"produce"` — `C#/15/category`; `"fruit"` — `S#/products/15/category`, `H#/products/1/category` |
| `"photo-product-016"` | `image` | `"assets/catalog/IMG_9714.jpg"` — `C#/15/image`; `"assets/products/photo-product-016.webp"` — `S#/products/15/image`, `H#/products/1/image` |
| `"photo-product-017"` | `name` | `"Citrus"` — `C#/16/name`; `"Lemons"` — `S#/products/16/name`, `H#/products/2/name` |
| `"photo-product-017"` | `category` | `"produce"` — `C#/16/category`; `"fruit"` — `S#/products/16/category`, `H#/products/2/category` |
| `"photo-product-017"` | `image` | `"assets/catalog/IMG_9715.jpg"` — `C#/16/image`; `"assets/products/photo-product-017.webp"` — `S#/products/16/image`, `H#/products/2/image` |
| `"photo-product-018"` | `name` | `"Taco Works chips"` — `C#/17/name`; `"Montaña de Oro Sea Salt tortilla chips"` — `S#/products/17/name`, `H#/products/13/name` |
| `"photo-product-018"` | `category` | `"produce"` — `C#/17/category`; `"vegetables"` — `S#/products/17/category`, `H#/products/13/category` |
| `"photo-product-018"` | `image` | `"assets/catalog/IMG_9715.jpg"` — `C#/17/image`; `"assets/products/photo-product-018.webp"` — `S#/products/17/image`, `H#/products/13/image` |
| `"photo-product-019"` | `name` | `"Fair Hills Farm beet juice"` — `C#/18/name`; `"Organic beet juice"` — `S#/products/18/name`, `H#/products/156/name` |
| `"photo-product-019"` | `brand` | `"Fair Hills Farm"` — `C#/18/brand`; `"Love Beets"` — `S#/products/18/brand`, `H#/products/156/brand` |
| `"photo-product-019"` | `category` | `"chilled"` — `C#/18/category`; `"drinks"` — `S#/products/18/category`, `H#/products/156/category` |
| `"photo-product-019"` | `image` | `"assets/catalog/IMG_9716.jpg"` — `C#/18/image`; `"assets/products/photo-product-019.webp"` — `S#/products/18/image`, `H#/products/156/image` |
| `"photo-product-021"` | `category` | `"chilled"` — `C#/20/category`; `"meat"` — `S#/products/19/category`, `H#/products/151/category` |
| `"photo-product-021"` | `image` | `"assets/catalog/IMG_9717.jpg"` — `C#/20/image`; `"assets/products/photo-product-021.webp"` — `S#/products/19/image`, `H#/products/151/image` |
| `"photo-product-022"` | `category` | `"chilled"` — `C#/21/category`; `"meat"` — `S#/products/20/category`, `H#/products/152/category` |
| `"photo-product-022"` | `image` | `"assets/catalog/IMG_9717.jpg"` — `C#/21/image`; `"assets/products/photo-product-022.webp"` — `S#/products/20/image`, `H#/products/152/image` |
| `"photo-product-023"` | `category` | `"chilled"` — `C#/22/category`; `"meat"` — `S#/products/21/category`, `H#/products/153/category` |
| `"photo-product-023"` | `image` | `"assets/catalog/IMG_9717.jpg"` — `C#/22/image`; `"assets/products/photo-product-023.webp"` — `S#/products/21/image`, `H#/products/153/image` |
| `"photo-product-024"` | `category` | `"chilled"` — `C#/23/category`; `"eggs"` — `S#/products/22/category`, `H#/products/65/category` |
| `"photo-product-024"` | `image` | `"assets/catalog/IMG_9717.jpg"` — `C#/23/image`; `"assets/products/photo-product-024.webp"` — `S#/products/22/image`, `H#/products/65/image` |
| `"photo-product-025"` | `category` | `"chilled"` — `C#/24/category`; `"dairy"` — `S#/products/23/category`, `H#/products/66/category` |
| `"photo-product-025"` | `image` | `"assets/catalog/IMG_9719.jpg"` — `C#/24/image`; `"assets/products/photo-product-025.webp"` — `S#/products/23/image`, `H#/products/66/image` |
| `"photo-product-026"` | `category` | `"chilled"` — `C#/25/category`; `"dairy"` — `S#/products/24/category`, `H#/products/67/category` |
| `"photo-product-026"` | `image` | `"assets/catalog/IMG_9719.jpg"` — `C#/25/image`; `"assets/products/photo-product-026.webp"` — `S#/products/24/image`, `H#/products/67/image` |
| `"photo-product-027"` | `name` | `"Straus milk"` — `C#/26/name`; `"Organic whole milk"` — `S#/products/25/name`, `H#/products/68/name` |
| `"photo-product-027"` | `category` | `"chilled"` — `C#/26/category`; `"dairy"` — `S#/products/25/category`, `H#/products/68/category` |
| `"photo-product-027"` | `image` | `"assets/catalog/IMG_9719.jpg"` — `C#/26/image`; `"assets/products/photo-product-027.webp"` — `S#/products/25/image`, `H#/products/68/image` |
| `"photo-product-028"` | `category` | `"chilled"` — `C#/27/category`; `"dairy"` — `S#/products/26/category`, `H#/products/69/category` |
| `"photo-product-028"` | `image` | `"assets/catalog/IMG_9719.jpg"` — `C#/27/image`; `"assets/products/photo-product-028.webp"` — `S#/products/26/image`, `H#/products/69/image` |
| `"photo-product-029"` | `name` | `"Stepladder cheese"` — `C#/28/name`; `"Ragged Point cheese"` — `S#/products/27/name`, `H#/products/70/name` |
| `"photo-product-029"` | `category` | `"chilled"` — `C#/28/category`; `"dairy"` — `S#/products/27/category`, `H#/products/70/category` |
| `"photo-product-029"` | `image` | `"assets/catalog/IMG_9720.jpg"` — `C#/28/image`; `"assets/products/photo-product-029.webp"` — `S#/products/27/image`, `H#/products/70/image` |
| `"photo-product-030"` | `category` | `"chilled"` — `C#/29/category`; `"dairy"` — `S#/products/28/category`, `H#/products/71/category` |
| `"photo-product-030"` | `image` | `"assets/catalog/IMG_9720.jpg"` — `C#/29/image`; `"assets/products/photo-product-030.webp"` — `S#/products/28/image`, `H#/products/71/image` |
| `"photo-product-031"` | `brand` | `"Producer not identified"` — `C#/30/brand`; `"Stardust Grove"` — `S#/products/29/brand`, `H#/products/100/brand` |
| `"photo-product-031"` | `category` | `"chilled"` — `C#/30/category`; `"pantry"` — `S#/products/29/category`, `H#/products/100/category` |
| `"photo-product-031"` | `image` | `"assets/catalog/IMG_9720.jpg"` — `C#/30/image`; `"assets/products/photo-product-031.webp"` — `S#/products/29/image`, `H#/products/100/image` |
| `"photo-product-032"` | `name` | `"Pesto"` — `C#/31/name`; `"Garlic pesto"` — `S#/products/30/name`, `H#/products/101/name` |
| `"photo-product-032"` | `brand` | `"Producer not identified"` — `C#/31/brand`; `"Stardust Grove"` — `S#/products/30/brand`, `H#/products/101/brand` |
| `"photo-product-032"` | `category` | `"chilled"` — `C#/31/category`; `"pantry"` — `S#/products/30/category`, `H#/products/101/category` |
| `"photo-product-032"` | `image` | `"assets/catalog/IMG_9720.jpg"` — `C#/31/image`; `"assets/products/photo-product-032.webp"` — `S#/products/30/image`, `H#/products/101/image` |
| `"photo-product-033"` | `category` | `"chilled"` — `C#/32/category`; `"dairy"` — `S#/products/31/category`, `H#/products/72/category` |
| `"photo-product-033"` | `image` | `"assets/catalog/IMG_9721.jpg"` — `C#/32/image`; `"assets/products/photo-product-033.webp"` — `S#/products/31/image`, `H#/products/72/image` |
| `"photo-product-034"` | `category` | `"chilled"` — `C#/33/category`; `"dairy"` — `S#/products/32/category`, `H#/products/73/category` |
| `"photo-product-034"` | `image` | `"assets/catalog/IMG_9721.jpg"` — `C#/33/image`; `"assets/products/photo-product-034.webp"` — `S#/products/32/image`, `H#/products/73/image` |
| `"photo-product-035"` | `name` | `"Stepladder chèvre"` — `C#/34/name`; `"Chèvre"` — `S#/products/33/name`, `H#/products/74/name` |
| `"photo-product-035"` | `category` | `"chilled"` — `C#/34/category`; `"dairy"` — `S#/products/33/category`, `H#/products/74/category` |
| `"photo-product-035"` | `image` | `"assets/catalog/IMG_9721.jpg"` — `C#/34/image`; `"assets/products/photo-product-035.webp"` — `S#/products/33/image`, `H#/products/74/image` |
| `"photo-product-037"` | `category` | `"chilled"` — `C#/36/category`; `"dairy"` — `S#/products/34/category`, `H#/products/75/category` |
| `"photo-product-037"` | `image` | `"assets/catalog/IMG_9722.jpg"` — `C#/36/image`; `"assets/products/photo-product-037.webp"` — `S#/products/34/image`, `H#/products/75/image` |
| `"photo-product-038"` | `category` | `"chilled"` — `C#/37/category`; `"dairy"` — `S#/products/35/category`, `H#/products/76/category` |
| `"photo-product-038"` | `image` | `"assets/catalog/IMG_9722.jpg"` — `C#/37/image`; `"assets/products/photo-product-038.webp"` — `S#/products/35/image`, `H#/products/76/image` |
| `"photo-product-039"` | `category` | `"chilled"` — `C#/38/category`; `"dairy"` — `S#/products/36/category`, `H#/products/77/category` |
| `"photo-product-039"` | `image` | `"assets/catalog/IMG_9722.jpg"` — `C#/38/image`; `"assets/products/photo-product-039.webp"` — `S#/products/36/image`, `H#/products/77/image` |
| `"photo-product-040"` | `name` | `"Sierra Nevada cheese"` — `C#/39/name`; `"Raw milk white cheddar"` — `H#/products/170/name` |
| `"photo-product-040"` | `category` | `"chilled"` — `C#/39/category`; `"dairy"` — `H#/products/170/category` |
| `"photo-product-040"` | `image` | `"assets/catalog/IMG_9722.jpg"` — `C#/39/image`; `"assets/products/photo-product-040.webp"` — `H#/products/170/image` |
| `"photo-product-041"` | `image` | `"assets/catalog/IMG_9723.jpg"` — `C#/40/image`; `"assets/products/photo-product-041.webp"` — `S#/products/37/image`, `H#/products/102/image` |
| `"photo-product-042"` | `image` | `"assets/catalog/IMG_9723.jpg"` — `C#/41/image`; `"assets/products/photo-product-042.webp"` — `S#/products/38/image`, `H#/products/103/image` |
| `"photo-product-043"` | `name` | `"Sunshine Olive oil"` — `C#/42/name`; `"Sunshine Estate olive oil"` — `S#/products/39/name`, `H#/products/104/name` |
| `"photo-product-043"` | `image` | `"assets/catalog/IMG_9724.jpg"` — `C#/42/image`; `"assets/products/photo-product-043.webp"` — `S#/products/39/image`, `H#/products/104/image` |
| `"photo-product-044"` | `brand` | `"Producer not identified"` — `C#/43/brand`; `"Mighty Cap Mushrooms"` — `S#/products/40/brand`, `H#/products/105/brand` |
| `"photo-product-044"` | `image` | `"assets/catalog/IMG_9724.jpg"` — `C#/43/image`; `"assets/products/photo-product-044.webp"` — `S#/products/40/image`, `H#/products/105/image` |
| `"photo-product-045"` | `image` | `"assets/catalog/IMG_9725.jpg"` — `C#/44/image`; `"assets/products/photo-product-045.webp"` — `S#/products/41/image`, `H#/products/106/image` |
| `"photo-product-046"` | `brand` | `"Producer not identified"` — `C#/45/brand`; `"Mighty Cap Mushrooms"` — `S#/products/42/brand`, `H#/products/107/brand` |
| `"photo-product-046"` | `image` | `"assets/catalog/IMG_9725.jpg"` — `C#/45/image`; `"assets/products/photo-product-046.webp"` — `S#/products/42/image`, `H#/products/107/image` |
| `"photo-product-047"` | `brand` | `"Producer not identified"` — `C#/46/brand`; `"Mighty Cap Mushrooms"` — `S#/products/43/brand`, `H#/products/108/brand` |
| `"photo-product-047"` | `image` | `"assets/catalog/IMG_9725.jpg"` — `C#/46/image`; `"assets/products/photo-product-047.webp"` — `S#/products/43/image`, `H#/products/108/image` |
| `"photo-product-048"` | `category` | `"pantry"` — `C#/47/category`; `"drinks"` — `S#/products/44/category`, `H#/products/157/category` |
| `"photo-product-048"` | `image` | `"assets/catalog/IMG_9726.jpg"` — `C#/47/image`; `"assets/products/photo-product-048.webp"` — `S#/products/44/image`, `H#/products/157/image` |
| `"photo-product-049"` | `category` | `"pantry"` — `C#/48/category`; `"drinks"` — `S#/products/45/category`, `H#/products/158/category` |
| `"photo-product-049"` | `image` | `"assets/catalog/IMG_9726.jpg"` — `C#/48/image`; `"assets/products/photo-product-049.webp"` — `S#/products/45/image`, `H#/products/158/image` |
| `"photo-product-050"` | `category` | `"pantry"` — `C#/49/category`; `"drinks"` — `S#/products/46/category`, `H#/products/159/category` |
| `"photo-product-050"` | `image` | `"assets/catalog/IMG_9726.jpg"` — `C#/49/image`; `"assets/products/photo-product-050.webp"` — `S#/products/46/image`, `H#/products/159/image` |
| `"photo-product-051"` | `name` | `"Fair Hills Farm ginger black tea"` — `C#/50/name`; `"Ginger black tea"` — `S#/products/47/name`, `H#/products/160/name` |
| `"photo-product-051"` | `category` | `"pantry"` — `C#/50/category`; `"drinks"` — `S#/products/47/category`, `H#/products/160/category` |
| `"photo-product-051"` | `image` | `"assets/catalog/IMG_9726.jpg"` — `C#/50/image`; `"assets/products/photo-product-051.webp"` — `S#/products/47/image`, `H#/products/160/image` |
| `"photo-product-052"` | `image` | `"assets/catalog/IMG_9727.jpg"` — `C#/51/image`; `"assets/products/photo-product-052.webp"` — `S#/products/48/image`, `H#/products/109/image` |
| `"photo-product-053"` | `image` | `"assets/catalog/IMG_9727.jpg"` — `C#/52/image`; `"assets/products/photo-product-053.webp"` — `S#/products/49/image`, `H#/products/110/image` |
| `"photo-product-054"` | `image` | `"assets/catalog/IMG_9728.jpg"` — `C#/53/image`; `"assets/products/photo-product-054.webp"` — `S#/products/50/image`, `H#/products/111/image` |
| `"photo-product-055"` | `name` | `"Packaged nuts"` — `C#/54/name`; `"Cashews"` — `S#/products/51/name`, `H#/products/112/name` |
| `"photo-product-055"` | `brand` | `"Producer not identified"` — `C#/54/brand`; `"Avocado Shack"` — `S#/products/51/brand`, `H#/products/112/brand` |
| `"photo-product-055"` | `image` | `"assets/catalog/IMG_9728.jpg"` — `C#/54/image`; `"assets/products/photo-product-055.webp"` — `S#/products/51/image`, `H#/products/112/image` |
| `"photo-product-056"` | `category` | `"produce"` — `C#/55/category`; `"fruit"` — `S#/products/52/category`, `H#/products/3/category` |
| `"photo-product-056"` | `image` | `"assets/catalog/IMG_9729.jpg"` — `C#/55/image`; `"assets/products/photo-product-056.webp"` — `S#/products/52/image`, `H#/products/3/image` |
| `"photo-product-057"` | `brand` | `"Producer not identified"` — `C#/56/brand`; `"AG Berries"` — `S#/products/53/brand`, `H#/products/4/brand` |
| `"photo-product-057"` | `category` | `"produce"` — `C#/56/category`; `"fruit"` — `S#/products/53/category`, `H#/products/4/category` |
| `"photo-product-057"` | `image` | `"assets/catalog/IMG_9729.jpg"` — `C#/56/image`; `"assets/products/photo-product-057.webp"` — `S#/products/53/image`, `H#/products/4/image` |
| `"photo-product-058"` | `category` | `"produce"` — `C#/57/category`; `"fruit"` — `S#/products/54/category`, `H#/products/5/category` |
| `"photo-product-058"` | `image` | `"assets/catalog/IMG_9729.jpg"` — `C#/57/image`; `"assets/products/photo-product-058.webp"` — `S#/products/54/image`, `H#/products/5/image` |
| `"photo-product-059"` | `name` | `"Golden berries"` — `C#/58/name`; `"Golden raspberries"` — `S#/products/55/name`, `H#/products/6/name` |
| `"photo-product-059"` | `category` | `"produce"` — `C#/58/category`; `"fruit"` — `S#/products/55/category`, `H#/products/6/category` |
| `"photo-product-059"` | `image` | `"assets/catalog/IMG_9729.jpg"` — `C#/58/image`; `"assets/products/photo-product-059.webp"` — `S#/products/55/image`, `H#/products/6/image` |
| `"photo-product-060"` | `category` | `"produce"` — `C#/59/category`; `"vegetables"` — `S#/products/56/category`, `H#/products/14/category` |
| `"photo-product-060"` | `image` | `"assets/catalog/IMG_9730.jpg"` — `C#/59/image`; `"assets/products/photo-product-060.webp"` — `S#/products/56/image`, `H#/products/14/image` |
| `"photo-product-061"` | `category` | `"produce"` — `C#/60/category`; `"vegetables"` — `S#/products/57/category`, `H#/products/15/category` |
| `"photo-product-061"` | `image` | `"assets/catalog/IMG_9730.jpg"` — `C#/60/image`; `"assets/products/photo-product-061.webp"` — `S#/products/57/image`, `H#/products/15/image` |
| `"photo-product-062"` | `category` | `"produce"` — `C#/61/category`; `"vegetables"` — `S#/products/58/category`, `H#/products/16/category` |
| `"photo-product-062"` | `image` | `"assets/catalog/IMG_9730.jpg"` — `C#/61/image`; `"assets/products/photo-product-062.webp"` — `S#/products/58/image`, `H#/products/16/image` |
| `"photo-product-063"` | `category` | `"produce"` — `C#/62/category`; `"vegetables"` — `S#/products/59/category`, `H#/products/17/category` |
| `"photo-product-063"` | `image` | `"assets/catalog/IMG_9730.jpg"` — `C#/62/image`; `"assets/products/photo-product-063.webp"` — `S#/products/59/image`, `H#/products/17/image` |
| `"photo-product-064"` | `category` | `"produce"` — `C#/63/category`; `"vegetables"` — `S#/products/60/category`, `H#/products/18/category` |
| `"photo-product-064"` | `image` | `"assets/catalog/IMG_9730.jpg"` — `C#/63/image`; `"assets/products/photo-product-064.webp"` — `S#/products/60/image`, `H#/products/18/image` |
| `"photo-product-065"` | `category` | `"produce"` — `C#/64/category`; `"vegetables"` — `S#/products/61/category`, `H#/products/19/category` |
| `"photo-product-065"` | `image` | `"assets/catalog/IMG_9730.jpg"` — `C#/64/image`; `"assets/products/photo-product-065.webp"` — `S#/products/61/image`, `H#/products/19/image` |
| `"photo-product-066"` | `category` | `"produce"` — `C#/65/category`; `"vegetables"` — `S#/products/62/category`, `H#/products/20/category` |
| `"photo-product-066"` | `image` | `"assets/catalog/IMG_9731.jpg"` — `C#/65/image`; `"assets/products/photo-product-066.webp"` — `S#/products/62/image`, `H#/products/20/image` |
| `"photo-product-067"` | `category` | `"produce"` — `C#/66/category`; `"vegetables"` — `S#/products/63/category`, `H#/products/21/category` |
| `"photo-product-067"` | `image` | `"assets/catalog/IMG_9731.jpg"` — `C#/66/image`; `"assets/products/photo-product-067.webp"` — `S#/products/63/image`, `H#/products/21/image` |
| `"photo-product-068"` | `category` | `"produce"` — `C#/67/category`; `"vegetables"` — `S#/products/64/category`, `H#/products/22/category` |
| `"photo-product-068"` | `image` | `"assets/catalog/IMG_9731.jpg"` — `C#/67/image`; `"assets/products/photo-product-068.webp"` — `S#/products/64/image`, `H#/products/22/image` |
| `"photo-product-069"` | `name` | `"Packaged spring greens"` — `C#/68/name`; `"Spring Greens"` — `S#/products/65/name`, `H#/products/23/name` |
| `"photo-product-069"` | `brand` | `"Producer not identified"` — `C#/68/brand`; `"Jayleaf"` — `S#/products/65/brand`, `H#/products/23/brand` |
| `"photo-product-069"` | `category` | `"produce"` — `C#/68/category`; `"vegetables"` — `S#/products/65/category`, `H#/products/23/category` |
| `"photo-product-069"` | `image` | `"assets/catalog/IMG_9732.jpg"` — `C#/68/image`; `"assets/products/photo-product-069.webp"` — `S#/products/65/image`, `H#/products/23/image` |
| `"photo-product-070"` | `name` | `"Packaged arugula"` — `C#/69/name`; `"Wild Arugula"` — `S#/products/66/name`, `H#/products/24/name` |
| `"photo-product-070"` | `brand` | `"Producer not identified"` — `C#/69/brand`; `"Jayleaf"` — `S#/products/66/brand`, `H#/products/24/brand` |
| `"photo-product-070"` | `category` | `"produce"` — `C#/69/category`; `"vegetables"` — `S#/products/66/category`, `H#/products/24/category` |
| `"photo-product-070"` | `image` | `"assets/catalog/IMG_9732.jpg"` — `C#/69/image`; `"assets/products/photo-product-070.webp"` — `S#/products/66/image`, `H#/products/24/image` |
| `"photo-product-071"` | `category` | `"produce"` — `C#/70/category`; `"vegetables"` — `S#/products/67/category`, `H#/products/25/category` |
| `"photo-product-071"` | `image` | `"assets/catalog/IMG_9732.jpg"` — `C#/70/image`; `"assets/products/photo-product-071.webp"` — `S#/products/67/image`, `H#/products/25/image` |
| `"photo-product-072"` | `name` | `"Green Gold microgreens"` — `C#/71/name`; `"Sunflower microgreens"` — `S#/products/68/name`, `H#/products/26/name` |
| `"photo-product-072"` | `brand` | `"Producer not identified"` — `C#/71/brand`; `"Green Gold"` — `S#/products/68/brand`, `H#/products/26/brand` |
| `"photo-product-072"` | `category` | `"produce"` — `C#/71/category`; `"vegetables"` — `S#/products/68/category`, `H#/products/26/category` |
| `"photo-product-072"` | `image` | `"assets/catalog/IMG_9733.jpg"` — `C#/71/image`; `"assets/products/photo-product-072.webp"` — `S#/products/68/image`, `H#/products/26/image` |
| `"photo-product-073"` | `category` | `"produce"` — `C#/72/category`; `"vegetables"` — `S#/products/69/category`, `H#/products/27/category` |
| `"photo-product-073"` | `image` | `"assets/catalog/IMG_9733.jpg"` — `C#/72/image`; `"assets/products/photo-product-073.webp"` — `S#/products/69/image`, `H#/products/27/image` |
| `"photo-product-074"` | `category` | `"produce"` — `C#/73/category`; `"vegetables"` — `S#/products/70/category`, `H#/products/28/category` |
| `"photo-product-074"` | `image` | `"assets/catalog/IMG_9733.jpg"` — `C#/73/image`; `"assets/products/photo-product-074.webp"` — `S#/products/70/image`, `H#/products/28/image` |
| `"photo-product-075"` | `category` | `"produce"` — `C#/74/category`; `"vegetables"` — `S#/products/71/category`, `H#/products/29/category` |
| `"photo-product-075"` | `image` | `"assets/catalog/IMG_9733.jpg"` — `C#/74/image`; `"assets/products/photo-product-075.webp"` — `S#/products/71/image`, `H#/products/29/image` |
| `"photo-product-076"` | `category` | `"produce"` — `C#/75/category`; `"vegetables"` — `S#/products/72/category`, `H#/products/30/category` |
| `"photo-product-076"` | `image` | `"assets/catalog/IMG_9733.jpg"` — `C#/75/image`; `"assets/products/photo-product-076.webp"` — `S#/products/72/image`, `H#/products/30/image` |
| `"photo-product-077"` | `category` | `"produce"` — `C#/76/category`; `"vegetables"` — `S#/products/73/category`, `H#/products/31/category` |
| `"photo-product-077"` | `image` | `"assets/catalog/IMG_9734.jpg"` — `C#/76/image`; `"assets/products/photo-product-077.webp"` — `S#/products/73/image`, `H#/products/31/image` |
| `"photo-product-078"` | `category` | `"produce"` — `C#/77/category`; `"fruit"` — `S#/products/74/category`, `H#/products/7/category` |
| `"photo-product-078"` | `image` | `"assets/catalog/IMG_9734.jpg"` — `C#/77/image`; `"assets/products/photo-product-078.webp"` — `S#/products/74/image`, `H#/products/7/image` |
| `"photo-product-079"` | `category` | `"produce"` — `C#/78/category`; `"vegetables"` — `S#/products/75/category`, `H#/products/32/category` |
| `"photo-product-079"` | `image` | `"assets/catalog/IMG_9735.jpg"` — `C#/78/image`; `"assets/products/photo-product-079.webp"` — `S#/products/75/image`, `H#/products/32/image` |
| `"photo-product-080"` | `name` | `"Melon"` — `C#/79/name`; `"Honeydew-type melon"` — `S#/products/76/name`, `H#/products/8/name` |
| `"photo-product-080"` | `category` | `"produce"` — `C#/79/category`; `"fruit"` — `S#/products/76/category`, `H#/products/8/category` |
| `"photo-product-080"` | `image` | `"assets/catalog/IMG_9735.jpg"` — `C#/79/image`; `"assets/products/photo-product-080.webp"` — `S#/products/76/image`, `H#/products/8/image` |
| `"photo-product-081"` | `name` | `"Mangoes"` — `C#/80/name`; `"Keitt mango"` — `S#/products/77/name`, `H#/products/9/name` |
| `"photo-product-081"` | `brand` | `"Producer not identified"` — `C#/80/brand`; `"Ava’s"` — `S#/products/77/brand`, `H#/products/9/brand` |
| `"photo-product-081"` | `category` | `"produce"` — `C#/80/category`; `"fruit"` — `S#/products/77/category`, `H#/products/9/category` |
| `"photo-product-081"` | `image` | `"assets/catalog/IMG_9736.jpg"` — `C#/80/image`; `"assets/products/photo-product-081.webp"` — `S#/products/77/image`, `H#/products/9/image` |
| `"photo-product-082"` | `name` | `"Etto pasta"` — `C#/81/name`; `"Artisan short-cut pasta"` — `S#/products/78/name`, `H#/products/113/name` |
| `"photo-product-082"` | `image` | `"assets/catalog/IMG_9738.jpg"` — `C#/81/image`; `"assets/products/photo-product-082.webp"` — `S#/products/78/image`, `H#/products/113/image` |
| `"photo-product-083"` | `category` | `"pantry"` — `C#/82/category`; `"drinks"` — `S#/products/79/category`, `H#/products/161/category` |
| `"photo-product-083"` | `image` | `"assets/catalog/IMG_9709.jpg"` — `C#/82/image`; `"assets/products/photo-product-083.webp"` — `S#/products/79/image`, `H#/products/161/image` |
| `"photo-product-084"` | `category` | `"pantry"` — `C#/83/category`; `"drinks"` — `S#/products/80/category`, `H#/products/162/category` |
| `"photo-product-084"` | `image` | `"assets/catalog/IMG_9709.jpg"` — `C#/83/image`; `"assets/products/photo-product-084.webp"` — `S#/products/80/image`, `H#/products/162/image` |
| `"photo-product-085"` | `category` | `"pantry"` — `C#/84/category`; `"drinks"` — `S#/products/81/category`, `H#/products/163/category` |
| `"photo-product-085"` | `image` | `"assets/catalog/IMG_9709.jpg"` — `C#/84/image`; `"assets/products/photo-product-085.webp"` — `S#/products/81/image`, `H#/products/163/image` |
| `"photo-product-086"` | `category` | `"pantry"` — `C#/85/category`; `"drinks"` — `S#/products/82/category`, `H#/products/164/category` |
| `"photo-product-086"` | `image` | `"assets/catalog/IMG_9709.jpg"` — `C#/85/image`; `"assets/products/photo-product-086.webp"` — `S#/products/82/image`, `H#/products/164/image` |
| `"photo-product-087"` | `category` | `"pantry"` — `C#/86/category`; `"drinks"` — `S#/products/83/category`, `H#/products/165/category` |
| `"photo-product-087"` | `image` | `"assets/catalog/IMG_9709.jpg"` — `C#/86/image`; `"assets/products/photo-product-087.webp"` — `S#/products/83/image`, `H#/products/165/image` |
| `"photo-product-088"` | `image` | `"assets/catalog/IMG_9723.jpg"` — `C#/87/image`; `"assets/products/photo-product-088.webp"` — `S#/products/84/image`, `H#/products/114/image` |
| `"photo-product-089"` | `image` | `"assets/catalog/IMG_9723.jpg"` — `C#/88/image`; `"assets/products/photo-product-089.webp"` — `S#/products/85/image`, `H#/products/115/image` |
| `"photo-product-090"` | `image` | `"assets/catalog/IMG_9723.jpg"` — `C#/89/image`; `"assets/products/photo-product-090.webp"` — `S#/products/86/image`, `H#/products/116/image` |
| `"photo-product-091"` | `image` | `"assets/catalog/IMG_9723.jpg"` — `C#/90/image`; `"assets/products/photo-product-091.webp"` — `S#/products/87/image`, `H#/products/117/image` |
| `"photo-product-092"` | `category` | `"pantry"` — `C#/91/category`; `"drinks"` — `S#/products/88/category`, `H#/products/166/category` |
| `"photo-product-092"` | `image` | `"assets/catalog/IMG_9709.jpg"` — `C#/91/image`; `"assets/products/photo-product-092.webp"` — `S#/products/88/image`, `H#/products/166/image` |
| `"photo-product-093"` | `image` | `"assets/catalog/IMG_9709.jpg"` — `C#/92/image`; `"assets/products/photo-product-093.webp"` — `S#/products/89/image`, `H#/products/118/image` |
| `"photo-product-094"` | `category` | `"pantry"` — `C#/93/category`; `"drinks"` — `S#/products/90/category`, `H#/products/167/category` |
| `"photo-product-094"` | `image` | `"assets/catalog/IMG_9709.jpg"` — `C#/93/image`; `"assets/products/photo-product-094.webp"` — `S#/products/90/image`, `H#/products/167/image` |
| `"photo-product-095"` | `category` | `"pantry"` — `C#/94/category`; `"drinks"` — `S#/products/91/category`, `H#/products/168/category` |
| `"photo-product-095"` | `image` | `"assets/catalog/IMG_9709.jpg"` — `C#/94/image`; `"assets/products/photo-product-095.webp"` — `S#/products/91/image`, `H#/products/168/image` |
| `"photo-product-099"` | `brand` | `"Producer not identified"` — `S#/products/95/brand`, `H#/products/33/brand`; `"Christopher Ranch (carton)"` — `N#/3/brand` |
| `"photo-product-100"` | `brand` | `"Producer not identified"` — `S#/products/96/brand`, `H#/products/34/brand`; `"Hummingbird (bag label)"` — `N#/4/brand` |
### Source photo filenames and extraction notes

| Product ID | Field | Quoted values and locations |
| --- | --- | --- |
| `"photo-product-001"` | `photo` | `"IMG_9714.jpg"` — `C#/0/photo`, `S#/products/0/photo`; *(key absent)* — `H#/products/0/photo` |
| `"photo-product-001"` | `photos` | `["IMG_9714.jpg"]` — `C#/0/photos`, `S#/products/0/photos`; *(key absent)* — `H#/products/0/photos` |
| `"photo-product-001"` | `notes` | `"Variety and selling terms confirmed by owner; photograph shows a mixed fruit display, not proof of variety."` — `C#/0/notes`, `S#/products/0/notes`; *(key absent)* — `H#/products/0/notes` |
| `"photo-product-002"` | `photo` | `"IMG_9707.jpg"` — `C#/1/photo`, `S#/products/1/photo`; *(key absent)* — `H#/products/90/photo` |
| `"photo-product-002"` | `photos` | `["IMG_9707.jpg"]` — `C#/1/photos`, `S#/products/1/photos`; *(key absent)* — `H#/products/90/photos` |
| `"photo-product-002"` | `notes` | `""` — `C#/1/notes`, `S#/products/1/notes`; *(key absent)* — `H#/products/90/notes` |
| `"photo-product-003"` | `photo` | `"IMG_9707.jpg"` — `C#/2/photo`, `S#/products/2/photo`; *(key absent)* — `H#/products/91/photo` |
| `"photo-product-003"` | `photos` | `["IMG_9707.jpg"]` — `C#/2/photos`, `S#/products/2/photos`; *(key absent)* — `H#/products/91/photos` |
| `"photo-product-003"` | `notes` | `""` — `C#/2/notes`, `S#/products/2/notes`; *(key absent)* — `H#/products/91/notes` |
| `"photo-product-004"` | `photo` | `"IMG_9707.jpg"` — `C#/3/photo`, `S#/products/3/photo`; *(key absent)* — `H#/products/92/photo` |
| `"photo-product-004"` | `photos` | `["IMG_9707.jpg"]` — `C#/3/photos`, `S#/products/3/photos`; *(key absent)* — `H#/products/92/photos` |
| `"photo-product-004"` | `notes` | `""` — `C#/3/notes`, `S#/products/3/notes`; *(key absent)* — `H#/products/92/notes` |
| `"photo-product-005"` | `photo` | `"IMG_9707.jpg"` — `C#/4/photo`, `S#/products/4/photo`; *(key absent)* — `H#/products/93/photo` |
| `"photo-product-005"` | `photos` | `["IMG_9707.jpg"]` — `C#/4/photos`, `S#/products/4/photos`; *(key absent)* — `H#/products/93/photos` |
| `"photo-product-005"` | `notes` | `""` — `C#/4/notes`, `S#/products/4/notes`; *(key absent)* — `H#/products/93/notes` |
| `"photo-product-006"` | `photo` | `"IMG_9708.jpg"` — `C#/5/photo`, `S#/products/5/photo`; *(key absent)* — `H#/products/169/photo` |
| `"photo-product-006"` | `photos` | `["IMG_9708.jpg"]` — `C#/5/photos`, `S#/products/5/photos`; *(key absent)* — `H#/products/169/photos` |
| `"photo-product-006"` | `notes` | `""` — `C#/5/notes`, `S#/products/5/notes`; *(key absent)* — `H#/products/169/notes` |
| `"photo-product-007"` | `photo` | `"IMG_9709.jpg"` — `C#/6/photo`, `S#/products/6/photo`; *(key absent)* — `H#/products/154/photo` |
| `"photo-product-007"` | `photos` | `["IMG_9709.jpg"]` — `C#/6/photos`, `S#/products/6/photos`; *(key absent)* — `H#/products/154/photos` |
| `"photo-product-007"` | `notes` | `""` — `C#/6/notes`, `S#/products/6/notes`; *(key absent)* — `H#/products/154/notes` |
| `"photo-product-008"` | `photo` | `"IMG_9710.jpg"` — `C#/7/photo`, `S#/products/7/photo`; *(key absent)* — `H#/products/94/photo` |
| `"photo-product-008"` | `photos` | `["IMG_9710.jpg"]` — `C#/7/photos`, `S#/products/7/photos`; *(key absent)* — `H#/products/94/photos` |
| `"photo-product-008"` | `notes` | `""` — `C#/7/notes`, `S#/products/7/notes`; *(key absent)* — `H#/products/94/notes` |
| `"photo-product-009"` | `photo` | `"IMG_9710.jpg"` — `C#/8/photo`, `S#/products/8/photo`; *(key absent)* — `H#/products/95/photo` |
| `"photo-product-009"` | `photos` | `["IMG_9710.jpg"]` — `C#/8/photos`, `S#/products/8/photos`; *(key absent)* — `H#/products/95/photos` |
| `"photo-product-009"` | `notes` | `""` — `C#/8/notes`, `S#/products/8/notes`; *(key absent)* — `H#/products/95/notes` |
| `"photo-product-010"` | `photo` | `"IMG_9710.jpg"` — `C#/9/photo`, `S#/products/9/photo`; *(key absent)* — `H#/products/96/photo` |
| `"photo-product-010"` | `photos` | `["IMG_9710.jpg"]` — `C#/9/photos`, `S#/products/9/photos`; *(key absent)* — `H#/products/96/photos` |
| `"photo-product-010"` | `notes` | `""` — `C#/9/notes`, `S#/products/9/notes`; *(key absent)* — `H#/products/96/notes` |
| `"photo-product-011"` | `photo` | `"IMG_9710.jpg"` — `C#/10/photo`, `S#/products/10/photo`; *(key absent)* — `H#/products/97/photo` |
| `"photo-product-011"` | `photos` | `["IMG_9710.jpg"]` — `C#/10/photos`, `S#/products/10/photos`; *(key absent)* — `H#/products/97/photos` |
| `"photo-product-011"` | `notes` | `"variety to confirm"` — `C#/10/notes`, `S#/products/10/notes`; *(key absent)* — `H#/products/97/notes` |
| `"photo-product-012"` | `photo` | `"IMG_9710.jpg"` — `C#/11/photo`, `S#/products/11/photo`; *(key absent)* — `H#/products/98/photo` |
| `"photo-product-012"` | `photos` | `["IMG_9710.jpg"]` — `C#/11/photos`, `S#/products/11/photos`; *(key absent)* — `H#/products/98/photos` |
| `"photo-product-012"` | `notes` | `"variety to confirm"` — `C#/11/notes`, `S#/products/11/notes`; *(key absent)* — `H#/products/98/notes` |
| `"photo-product-013"` | `photo` | `"IMG_9711.jpg"` — `C#/12/photo`, `S#/products/12/photo`; *(key absent)* — `H#/products/99/photo` |
| `"photo-product-013"` | `photos` | `["IMG_9711.jpg"]` — `C#/12/photos`, `S#/products/12/photos`; *(key absent)* — `H#/products/99/photos` |
| `"photo-product-013"` | `notes` | `"variety to confirm"` — `C#/12/notes`, `S#/products/12/notes`; *(key absent)* — `H#/products/99/notes` |
| `"photo-product-014"` | `photo` | `"IMG_9712.jpg"` — `C#/13/photo`, `S#/products/13/photo`; *(key absent)* — `H#/products/155/photo` |
| `"photo-product-014"` | `photos` | `["IMG_9712.jpg"]` — `C#/13/photos`, `S#/products/13/photos`; *(key absent)* — `H#/products/155/photos` |
| `"photo-product-014"` | `notes` | `"variety and alcohol content to confirm"` — `C#/13/notes`, `S#/products/13/notes`; *(key absent)* — `H#/products/155/notes` |
| `"photo-product-015"` | `photo` | `"IMG_9713.jpg"` — `C#/14/photo`, `S#/products/14/photo`; *(key absent)* — `H#/products/86/photo` |
| `"photo-product-015"` | `photos` | `["IMG_9713.jpg"]` — `C#/14/photos`, `S#/products/14/photos`; *(key absent)* — `H#/products/86/photos` |
| `"photo-product-015"` | `notes` | `"variety to confirm"` — `C#/14/notes`, `S#/products/14/notes`; *(key absent)* — `H#/products/86/notes` |
| `"photo-product-016"` | `photo` | `"IMG_9714.jpg"` — `C#/15/photo`, `S#/products/15/photo`; *(key absent)* — `H#/products/1/photo` |
| `"photo-product-016"` | `photos` | `["IMG_9714.jpg", "IMG_9736.jpg"]` — `C#/15/photos`, `S#/products/15/photos`; *(key absent)* — `H#/products/1/photos` |
| `"photo-product-016"` | `notes` | `"variety to confirm"` — `C#/15/notes`, `S#/products/15/notes`; *(key absent)* — `H#/products/1/notes` |
| `"photo-product-017"` | `photo` | `"IMG_9715.jpg"` — `C#/16/photo`, `S#/products/16/photo`; *(key absent)* — `H#/products/2/photo` |
| `"photo-product-017"` | `photos` | `["IMG_9715.jpg"]` — `C#/16/photos`, `S#/products/16/photos`; *(key absent)* — `H#/products/2/photos` |
| `"photo-product-017"` | `notes` | `"variety to confirm"` — `C#/16/notes`; `"Yellow citrus visible in IMG_9715; precise lemon variety unconfirmed."` — `S#/products/16/notes`; *(key absent)* — `H#/products/2/notes` |
| `"photo-product-018"` | `photo` | `"IMG_9715.jpg"` — `C#/17/photo`, `S#/products/17/photo`; *(key absent)* — `H#/products/13/photo` |
| `"photo-product-018"` | `photos` | `["IMG_9715.jpg"]` — `C#/17/photos`, `S#/products/17/photos`; *(key absent)* — `H#/products/13/photos` |
| `"photo-product-018"` | `notes` | `"package to confirm"` — `C#/17/notes`, `S#/products/17/notes`; *(key absent)* — `H#/products/13/notes` |
| `"photo-product-019"` | `photo` | `"IMG_9716.jpg"` — `C#/18/photo`, `S#/products/18/photo`; *(key absent)* — `H#/products/156/photo` |
| `"photo-product-019"` | `photos` | `["IMG_9716.jpg"]` — `C#/18/photos`, `S#/products/18/photos`; *(key absent)* — `H#/products/156/photos` |
| `"photo-product-019"` | `notes` | `""` — `C#/18/notes`, `S#/products/18/notes`; *(key absent)* — `H#/products/156/notes` |
| `"photo-product-021"` | `photo` | `"IMG_9717.jpg"` — `C#/20/photo`, `S#/products/19/photo`; *(key absent)* — `H#/products/151/photo` |
| `"photo-product-021"` | `photos` | `["IMG_9717.jpg"]` — `C#/20/photos`, `S#/products/19/photos`; *(key absent)* — `H#/products/151/photos` |
| `"photo-product-021"` | `notes` | `""` — `C#/20/notes`, `S#/products/19/notes`; *(key absent)* — `H#/products/151/notes` |
| `"photo-product-022"` | `photo` | `"IMG_9717.jpg"` — `C#/21/photo`, `S#/products/20/photo`; *(key absent)* — `H#/products/152/photo` |
| `"photo-product-022"` | `photos` | `["IMG_9717.jpg"]` — `C#/21/photos`, `S#/products/20/photos`; *(key absent)* — `H#/products/152/photos` |
| `"photo-product-022"` | `notes` | `""` — `C#/21/notes`, `S#/products/20/notes`; *(key absent)* — `H#/products/152/notes` |
| `"photo-product-023"` | `photo` | `"IMG_9717.jpg"` — `C#/22/photo`, `S#/products/21/photo`; *(key absent)* — `H#/products/153/photo` |
| `"photo-product-023"` | `photos` | `["IMG_9717.jpg"]` — `C#/22/photos`, `S#/products/21/photos`; *(key absent)* — `H#/products/153/photos` |
| `"photo-product-023"` | `notes` | `""` — `C#/22/notes`, `S#/products/21/notes`; *(key absent)* — `H#/products/153/notes` |
| `"photo-product-024"` | `photo` | `"IMG_9717.jpg"` — `C#/23/photo`, `S#/products/22/photo`; *(key absent)* — `H#/products/65/photo` |
| `"photo-product-024"` | `photos` | `["IMG_9717.jpg", "IMG_9718.jpg"]` — `C#/23/photos`, `S#/products/22/photos`; *(key absent)* — `H#/products/65/photos` |
| `"photo-product-024"` | `notes` | `"carton size to confirm"` — `C#/23/notes`, `S#/products/22/notes`; *(key absent)* — `H#/products/65/notes` |
| `"photo-product-025"` | `photo` | `"IMG_9719.jpg"` — `C#/24/photo`, `S#/products/23/photo`; *(key absent)* — `H#/products/66/photo` |
| `"photo-product-025"` | `photos` | `["IMG_9719.jpg"]` — `C#/24/photos`, `S#/products/23/photos`; *(key absent)* — `H#/products/66/photos` |
| `"photo-product-025"` | `notes` | `""` — `C#/24/notes`, `S#/products/23/notes`; *(key absent)* — `H#/products/66/notes` |
| `"photo-product-026"` | `photo` | `"IMG_9719.jpg"` — `C#/25/photo`, `S#/products/24/photo`; *(key absent)* — `H#/products/67/photo` |
| `"photo-product-026"` | `photos` | `["IMG_9719.jpg"]` — `C#/25/photos`, `S#/products/24/photos`; *(key absent)* — `H#/products/67/photos` |
| `"photo-product-026"` | `notes` | `""` — `C#/25/notes`, `S#/products/24/notes`; *(key absent)* — `H#/products/67/notes` |
| `"photo-product-027"` | `photo` | `"IMG_9719.jpg"` — `C#/26/photo`, `S#/products/25/photo`; *(key absent)* — `H#/products/68/photo` |
| `"photo-product-027"` | `photos` | `["IMG_9719.jpg"]` — `C#/26/photos`, `S#/products/25/photos`; *(key absent)* — `H#/products/68/photos` |
| `"photo-product-027"` | `notes` | `"variety to confirm"` — `C#/26/notes`, `S#/products/25/notes`; *(key absent)* — `H#/products/68/notes` |
| `"photo-product-028"` | `photo` | `"IMG_9719.jpg"` — `C#/27/photo`, `S#/products/26/photo`; *(key absent)* — `H#/products/69/photo` |
| `"photo-product-028"` | `photos` | `["IMG_9719.jpg"]` — `C#/27/photos`, `S#/products/26/photos`; *(key absent)* — `H#/products/69/photos` |
| `"photo-product-028"` | `notes` | `"package to confirm"` — `C#/27/notes`, `S#/products/26/notes`; *(key absent)* — `H#/products/69/notes` |
| `"photo-product-029"` | `photo` | `"IMG_9720.jpg"` — `C#/28/photo`, `S#/products/27/photo`; *(key absent)* — `H#/products/70/photo` |
| `"photo-product-029"` | `photos` | `["IMG_9720.jpg"]` — `C#/28/photos`, `S#/products/27/photos`; *(key absent)* — `H#/products/70/photos` |
| `"photo-product-029"` | `notes` | `"variety to confirm"` — `C#/28/notes`, `S#/products/27/notes`; *(key absent)* — `H#/products/70/notes` |
| `"photo-product-030"` | `photo` | `"IMG_9720.jpg"` — `C#/29/photo`, `S#/products/28/photo`; *(key absent)* — `H#/products/71/photo` |
| `"photo-product-030"` | `photos` | `["IMG_9720.jpg"]` — `C#/29/photos`, `S#/products/28/photos`; *(key absent)* — `H#/products/71/photos` |
| `"photo-product-030"` | `notes` | `""` — `C#/29/notes`, `S#/products/28/notes`; *(key absent)* — `H#/products/71/notes` |
| `"photo-product-031"` | `photo` | `"IMG_9720.jpg"` — `C#/30/photo`, `S#/products/29/photo`; *(key absent)* — `H#/products/100/photo` |
| `"photo-product-031"` | `photos` | `["IMG_9720.jpg"]` — `C#/30/photos`, `S#/products/29/photos`; *(key absent)* — `H#/products/100/photos` |
| `"photo-product-031"` | `notes` | `"producer and package to confirm"` — `C#/30/notes`, `S#/products/29/notes`; *(key absent)* — `H#/products/100/notes` |
| `"photo-product-032"` | `photo` | `"IMG_9720.jpg"` — `C#/31/photo`, `S#/products/30/photo`; *(key absent)* — `H#/products/101/photo` |
| `"photo-product-032"` | `photos` | `["IMG_9720.jpg"]` — `C#/31/photos`, `S#/products/30/photos`; *(key absent)* — `H#/products/101/photos` |
| `"photo-product-032"` | `notes` | `"producer and package to confirm"` — `C#/31/notes`, `S#/products/30/notes`; *(key absent)* — `H#/products/101/notes` |
| `"photo-product-033"` | `photo` | `"IMG_9721.jpg"` — `C#/32/photo`, `S#/products/31/photo`; *(key absent)* — `H#/products/72/photo` |
| `"photo-product-033"` | `photos` | `["IMG_9721.jpg"]` — `C#/32/photos`, `S#/products/31/photos`; *(key absent)* — `H#/products/72/photos` |
| `"photo-product-033"` | `notes` | `""` — `C#/32/notes`, `S#/products/31/notes`; *(key absent)* — `H#/products/72/notes` |
| `"photo-product-034"` | `photo` | `"IMG_9721.jpg"` — `C#/33/photo`, `S#/products/32/photo`; *(key absent)* — `H#/products/73/photo` |
| `"photo-product-034"` | `photos` | `["IMG_9721.jpg"]` — `C#/33/photos`, `S#/products/32/photos`; *(key absent)* — `H#/products/73/photos` |
| `"photo-product-034"` | `notes` | `""` — `C#/33/notes`, `S#/products/32/notes`; *(key absent)* — `H#/products/73/notes` |
| `"photo-product-035"` | `photo` | `"IMG_9721.jpg"` — `C#/34/photo`, `S#/products/33/photo`; *(key absent)* — `H#/products/74/photo` |
| `"photo-product-035"` | `photos` | `["IMG_9721.jpg"]` — `C#/34/photos`, `S#/products/33/photos`; *(key absent)* — `H#/products/74/photos` |
| `"photo-product-035"` | `notes` | `""` — `C#/34/notes`, `S#/products/33/notes`; *(key absent)* — `H#/products/74/notes` |
| `"photo-product-037"` | `photo` | `"IMG_9722.jpg"` — `C#/36/photo`, `S#/products/34/photo`; *(key absent)* — `H#/products/75/photo` |
| `"photo-product-037"` | `photos` | `["IMG_9722.jpg"]` — `C#/36/photos`, `S#/products/34/photos`; *(key absent)* — `H#/products/75/photos` |
| `"photo-product-037"` | `notes` | `""` — `C#/36/notes`, `S#/products/34/notes`; *(key absent)* — `H#/products/75/notes` |
| `"photo-product-038"` | `photo` | `"IMG_9722.jpg"` — `C#/37/photo`, `S#/products/35/photo`; *(key absent)* — `H#/products/76/photo` |
| `"photo-product-038"` | `photos` | `["IMG_9722.jpg"]` — `C#/37/photos`, `S#/products/35/photos`; *(key absent)* — `H#/products/76/photos` |
| `"photo-product-038"` | `notes` | `""` — `C#/37/notes`, `S#/products/35/notes`; *(key absent)* — `H#/products/76/notes` |
| `"photo-product-039"` | `photo` | `"IMG_9722.jpg"` — `C#/38/photo`, `S#/products/36/photo`; *(key absent)* — `H#/products/77/photo` |
| `"photo-product-039"` | `photos` | `["IMG_9722.jpg"]` — `C#/38/photos`, `S#/products/36/photos`; *(key absent)* — `H#/products/77/photos` |
| `"photo-product-039"` | `notes` | `""` — `C#/38/notes`, `S#/products/36/notes`; *(key absent)* — `H#/products/77/notes` |
| `"photo-product-040"` | `photo` | `"IMG_9722.jpg"` — `C#/39/photo`; *(key absent)* — `H#/products/170/photo` |
| `"photo-product-040"` | `photos` | `["IMG_9722.jpg"]` — `C#/39/photos`; *(key absent)* — `H#/products/170/photos` |
| `"photo-product-040"` | `notes` | `"variety to confirm"` — `C#/39/notes`; *(key absent)* — `H#/products/170/notes` |
| `"photo-product-041"` | `photo` | `"IMG_9723.jpg"` — `C#/40/photo`, `S#/products/37/photo`; *(key absent)* — `H#/products/102/photo` |
| `"photo-product-041"` | `photos` | `["IMG_9723.jpg"]` — `C#/40/photos`, `S#/products/37/photos`; *(key absent)* — `H#/products/102/photos` |
| `"photo-product-041"` | `notes` | `""` — `C#/40/notes`, `S#/products/37/notes`; *(key absent)* — `H#/products/102/notes` |
| `"photo-product-042"` | `photo` | `"IMG_9723.jpg"` — `C#/41/photo`, `S#/products/38/photo`; *(key absent)* — `H#/products/103/photo` |
| `"photo-product-042"` | `photos` | `["IMG_9723.jpg"]` — `C#/41/photos`, `S#/products/38/photos`; *(key absent)* — `H#/products/103/photos` |
| `"photo-product-042"` | `notes` | `"variety to confirm"` — `C#/41/notes`, `S#/products/38/notes`; *(key absent)* — `H#/products/103/notes` |
| `"photo-product-043"` | `photo` | `"IMG_9724.jpg"` — `C#/42/photo`, `S#/products/39/photo`; *(key absent)* — `H#/products/104/photo` |
| `"photo-product-043"` | `photos` | `["IMG_9724.jpg"]` — `C#/42/photos`, `S#/products/39/photos`; *(key absent)* — `H#/products/104/photos` |
| `"photo-product-043"` | `notes` | `"variety to confirm"` — `C#/42/notes`, `S#/products/39/notes`; *(key absent)* — `H#/products/104/notes` |
| `"photo-product-044"` | `photo` | `"IMG_9724.jpg"` — `C#/43/photo`, `S#/products/40/photo`; *(key absent)* — `H#/products/105/photo` |
| `"photo-product-044"` | `photos` | `["IMG_9724.jpg"]` — `C#/43/photos`, `S#/products/40/photos`; *(key absent)* — `H#/products/105/photos` |
| `"photo-product-044"` | `notes` | `"species and package to confirm"` — `C#/43/notes`, `S#/products/40/notes`; *(key absent)* — `H#/products/105/notes` |
| `"photo-product-045"` | `photo` | `"IMG_9725.jpg"` — `C#/44/photo`, `S#/products/41/photo`; *(key absent)* — `H#/products/106/photo` |
| `"photo-product-045"` | `photos` | `["IMG_9725.jpg"]` — `C#/44/photos`, `S#/products/41/photos`; *(key absent)* — `H#/products/106/photos` |
| `"photo-product-045"` | `notes` | `""` — `C#/44/notes`, `S#/products/41/notes`; *(key absent)* — `H#/products/106/notes` |
| `"photo-product-046"` | `photo` | `"IMG_9725.jpg"` — `C#/45/photo`, `S#/products/42/photo`; *(key absent)* — `H#/products/107/photo` |
| `"photo-product-046"` | `photos` | `["IMG_9725.jpg"]` — `C#/45/photos`, `S#/products/42/photos`; *(key absent)* — `H#/products/107/photos` |
| `"photo-product-046"` | `notes` | `""` — `C#/45/notes`, `S#/products/42/notes`; *(key absent)* — `H#/products/107/notes` |
| `"photo-product-047"` | `photo` | `"IMG_9725.jpg"` — `C#/46/photo`, `S#/products/43/photo`; *(key absent)* — `H#/products/108/photo` |
| `"photo-product-047"` | `photos` | `["IMG_9725.jpg"]` — `C#/46/photos`, `S#/products/43/photos`; *(key absent)* — `H#/products/108/photos` |
| `"photo-product-047"` | `notes` | `""` — `C#/46/notes`, `S#/products/43/notes`; *(key absent)* — `H#/products/108/notes` |
| `"photo-product-048"` | `photo` | `"IMG_9726.jpg"` — `C#/47/photo`, `S#/products/44/photo`; *(key absent)* — `H#/products/157/photo` |
| `"photo-product-048"` | `photos` | `["IMG_9726.jpg"]` — `C#/47/photos`, `S#/products/44/photos`; *(key absent)* — `H#/products/157/photos` |
| `"photo-product-048"` | `notes` | `""` — `C#/47/notes`, `S#/products/44/notes`; *(key absent)* — `H#/products/157/notes` |
| `"photo-product-049"` | `photo` | `"IMG_9726.jpg"` — `C#/48/photo`, `S#/products/45/photo`; *(key absent)* — `H#/products/158/photo` |
| `"photo-product-049"` | `photos` | `["IMG_9726.jpg"]` — `C#/48/photos`, `S#/products/45/photos`; *(key absent)* — `H#/products/158/photos` |
| `"photo-product-049"` | `notes` | `""` — `C#/48/notes`, `S#/products/45/notes`; *(key absent)* — `H#/products/158/notes` |
| `"photo-product-050"` | `photo` | `"IMG_9726.jpg"` — `C#/49/photo`, `S#/products/46/photo`; *(key absent)* — `H#/products/159/photo` |
| `"photo-product-050"` | `photos` | `["IMG_9726.jpg"]` — `C#/49/photos`, `S#/products/46/photos`; *(key absent)* — `H#/products/159/photos` |
| `"photo-product-050"` | `notes` | `""` — `C#/49/notes`, `S#/products/46/notes`; *(key absent)* — `H#/products/159/notes` |
| `"photo-product-051"` | `photo` | `"IMG_9726.jpg"` — `C#/50/photo`, `S#/products/47/photo`; *(key absent)* — `H#/products/160/photo` |
| `"photo-product-051"` | `photos` | `["IMG_9726.jpg"]` — `C#/50/photos`, `S#/products/47/photos`; *(key absent)* — `H#/products/160/photos` |
| `"photo-product-051"` | `notes` | `""` — `C#/50/notes`, `S#/products/47/notes`; *(key absent)* — `H#/products/160/notes` |
| `"photo-product-052"` | `photo` | `"IMG_9727.jpg"` — `C#/51/photo`, `S#/products/48/photo`; *(key absent)* — `H#/products/109/photo` |
| `"photo-product-052"` | `photos` | `["IMG_9727.jpg"]` — `C#/51/photos`, `S#/products/48/photos`; *(key absent)* — `H#/products/109/photos` |
| `"photo-product-052"` | `notes` | `""` — `C#/51/notes`, `S#/products/48/notes`; *(key absent)* — `H#/products/109/notes` |
| `"photo-product-053"` | `photo` | `"IMG_9727.jpg"` — `C#/52/photo`, `S#/products/49/photo`; *(key absent)* — `H#/products/110/photo` |
| `"photo-product-053"` | `photos` | `["IMG_9727.jpg"]` — `C#/52/photos`, `S#/products/49/photos`; *(key absent)* — `H#/products/110/photos` |
| `"photo-product-053"` | `notes` | `""` — `C#/52/notes`, `S#/products/49/notes`; *(key absent)* — `H#/products/110/notes` |
| `"photo-product-054"` | `photo` | `"IMG_9728.jpg"` — `C#/53/photo`, `S#/products/50/photo`; *(key absent)* — `H#/products/111/photo` |
| `"photo-product-054"` | `photos` | `["IMG_9728.jpg"]` — `C#/53/photos`, `S#/products/50/photos`; *(key absent)* — `H#/products/111/photos` |
| `"photo-product-054"` | `notes` | `"package to confirm"` — `C#/53/notes`; `"Rice displayed in reused Straus bottles; Massa Organics shelf label is visible. Confirm current packaging."` — `S#/products/50/notes`; *(key absent)* — `H#/products/111/notes` |
| `"photo-product-055"` | `photo` | `"IMG_9728.jpg"` — `C#/54/photo`, `S#/products/51/photo`; *(key absent)* — `H#/products/112/photo` |
| `"photo-product-055"` | `photos` | `["IMG_9728.jpg"]` — `C#/54/photos`, `S#/products/51/photos`; *(key absent)* — `H#/products/112/photos` |
| `"photo-product-055"` | `notes` | `"variety to confirm"` — `C#/54/notes`; `"Displayed in a reused Straus glass bottle; the bottle brand is not the nut producer."` — `S#/products/51/notes`; *(key absent)* — `H#/products/112/notes` |
| `"photo-product-056"` | `photo` | `"IMG_9729.jpg"` — `C#/55/photo`, `S#/products/52/photo`; *(key absent)* — `H#/products/3/photo` |
| `"photo-product-056"` | `photos` | `["IMG_9729.jpg"]` — `C#/55/photos`, `S#/products/52/photos`; *(key absent)* — `H#/products/3/photos` |
| `"photo-product-056"` | `notes` | `"selling package to confirm"` — `C#/55/notes`, `S#/products/52/notes`; *(key absent)* — `H#/products/3/notes` |
| `"photo-product-057"` | `photo` | `"IMG_9729.jpg"` — `C#/56/photo`, `S#/products/53/photo`; *(key absent)* — `H#/products/4/photo` |
| `"photo-product-057"` | `photos` | `["IMG_9729.jpg"]` — `C#/56/photos`, `S#/products/53/photos`; *(key absent)* — `H#/products/4/photos` |
| `"photo-product-057"` | `notes` | `"selling package to confirm"` — `C#/56/notes`, `S#/products/53/notes`; *(key absent)* — `H#/products/4/notes` |
| `"photo-product-058"` | `photo` | `"IMG_9729.jpg"` — `C#/57/photo`, `S#/products/54/photo`; *(key absent)* — `H#/products/5/photo` |
| `"photo-product-058"` | `photos` | `["IMG_9729.jpg"]` — `C#/57/photos`, `S#/products/54/photos`; *(key absent)* — `H#/products/5/photos` |
| `"photo-product-058"` | `notes` | `"selling package to confirm"` — `C#/57/notes`, `S#/products/54/notes`; *(key absent)* — `H#/products/5/notes` |
| `"photo-product-059"` | `photo` | `"IMG_9729.jpg"` — `C#/58/photo`, `S#/products/55/photo`; *(key absent)* — `H#/products/6/photo` |
| `"photo-product-059"` | `photos` | `["IMG_9729.jpg"]` — `C#/58/photos`, `S#/products/55/photos`; *(key absent)* — `H#/products/6/photos` |
| `"photo-product-059"` | `notes` | `"identity to confirm"` — `C#/58/notes`, `S#/products/55/notes`; *(key absent)* — `H#/products/6/notes` |
| `"photo-product-060"` | `photo` | `"IMG_9730.jpg"` — `C#/59/photo`, `S#/products/56/photo`; *(key absent)* — `H#/products/14/photo` |
| `"photo-product-060"` | `photos` | `["IMG_9730.jpg"]` — `C#/59/photos`, `S#/products/56/photos`; *(key absent)* — `H#/products/14/photos` |
| `"photo-product-060"` | `notes` | `""` — `C#/59/notes`, `S#/products/56/notes`; *(key absent)* — `H#/products/14/notes` |
| `"photo-product-061"` | `photo` | `"IMG_9730.jpg"` — `C#/60/photo`, `S#/products/57/photo`; *(key absent)* — `H#/products/15/photo` |
| `"photo-product-061"` | `photos` | `["IMG_9730.jpg"]` — `C#/60/photos`, `S#/products/57/photos`; *(key absent)* — `H#/products/15/photos` |
| `"photo-product-061"` | `notes` | `""` — `C#/60/notes`, `S#/products/57/notes`; *(key absent)* — `H#/products/15/notes` |
| `"photo-product-062"` | `photo` | `"IMG_9730.jpg"` — `C#/61/photo`, `S#/products/58/photo`; *(key absent)* — `H#/products/16/photo` |
| `"photo-product-062"` | `photos` | `["IMG_9730.jpg"]` — `C#/61/photos`, `S#/products/58/photos`; *(key absent)* — `H#/products/16/photos` |
| `"photo-product-062"` | `notes` | `""` — `C#/61/notes`, `S#/products/58/notes`; *(key absent)* — `H#/products/16/notes` |
| `"photo-product-063"` | `photo` | `"IMG_9730.jpg"` — `C#/62/photo`, `S#/products/59/photo`; *(key absent)* — `H#/products/17/photo` |
| `"photo-product-063"` | `photos` | `["IMG_9730.jpg"]` — `C#/62/photos`, `S#/products/59/photos`; *(key absent)* — `H#/products/17/photos` |
| `"photo-product-063"` | `notes` | `""` — `C#/62/notes`, `S#/products/59/notes`; *(key absent)* — `H#/products/17/notes` |
| `"photo-product-064"` | `photo` | `"IMG_9730.jpg"` — `C#/63/photo`, `S#/products/60/photo`; *(key absent)* — `H#/products/18/photo` |
| `"photo-product-064"` | `photos` | `["IMG_9730.jpg"]` — `C#/63/photos`, `S#/products/60/photos`; *(key absent)* — `H#/products/18/photos` |
| `"photo-product-064"` | `notes` | `""` — `C#/63/notes`, `S#/products/60/notes`; *(key absent)* — `H#/products/18/notes` |
| `"photo-product-065"` | `photo` | `"IMG_9730.jpg"` — `C#/64/photo`, `S#/products/61/photo`; *(key absent)* — `H#/products/19/photo` |
| `"photo-product-065"` | `photos` | `["IMG_9730.jpg"]` — `C#/64/photos`, `S#/products/61/photos`; *(key absent)* — `H#/products/19/photos` |
| `"photo-product-065"` | `notes` | `""` — `C#/64/notes`, `S#/products/61/notes`; *(key absent)* — `H#/products/19/notes` |
| `"photo-product-066"` | `photo` | `"IMG_9731.jpg"` — `C#/65/photo`, `S#/products/62/photo`; *(key absent)* — `H#/products/20/photo` |
| `"photo-product-066"` | `photos` | `["IMG_9731.jpg"]` — `C#/65/photos`, `S#/products/62/photos`; *(key absent)* — `H#/products/20/photos` |
| `"photo-product-066"` | `notes` | `""` — `C#/65/notes`, `S#/products/62/notes`; *(key absent)* — `H#/products/20/notes` |
| `"photo-product-067"` | `photo` | `"IMG_9731.jpg"` — `C#/66/photo`, `S#/products/63/photo`; *(key absent)* — `H#/products/21/photo` |
| `"photo-product-067"` | `photos` | `["IMG_9731.jpg"]` — `C#/66/photos`, `S#/products/63/photos`; *(key absent)* — `H#/products/21/photos` |
| `"photo-product-067"` | `notes` | `"variety to confirm"` — `C#/66/notes`, `S#/products/63/notes`; *(key absent)* — `H#/products/21/notes` |
| `"photo-product-068"` | `photo` | `"IMG_9731.jpg"` — `C#/67/photo`, `S#/products/64/photo`; *(key absent)* — `H#/products/22/photo` |
| `"photo-product-068"` | `photos` | `["IMG_9731.jpg"]` — `C#/67/photos`, `S#/products/64/photos`; *(key absent)* — `H#/products/22/photos` |
| `"photo-product-068"` | `notes` | `"variety to confirm"` — `C#/67/notes`, `S#/products/64/notes`; *(key absent)* — `H#/products/22/notes` |
| `"photo-product-069"` | `photo` | `"IMG_9732.jpg"` — `C#/68/photo`, `S#/products/65/photo`; *(key absent)* — `H#/products/23/photo` |
| `"photo-product-069"` | `photos` | `["IMG_9732.jpg"]` — `C#/68/photos`, `S#/products/65/photos`; *(key absent)* — `H#/products/23/photos` |
| `"photo-product-069"` | `notes` | `""` — `C#/68/notes`, `S#/products/65/notes`; *(key absent)* — `H#/products/23/notes` |
| `"photo-product-070"` | `photo` | `"IMG_9732.jpg"` — `C#/69/photo`, `S#/products/66/photo`; *(key absent)* — `H#/products/24/photo` |
| `"photo-product-070"` | `photos` | `["IMG_9732.jpg"]` — `C#/69/photos`, `S#/products/66/photos`; *(key absent)* — `H#/products/24/photos` |
| `"photo-product-070"` | `notes` | `""` — `C#/69/notes`, `S#/products/66/notes`; *(key absent)* — `H#/products/24/notes` |
| `"photo-product-071"` | `photo` | `"IMG_9732.jpg"` — `C#/70/photo`, `S#/products/67/photo`; *(key absent)* — `H#/products/25/photo` |
| `"photo-product-071"` | `photos` | `["IMG_9732.jpg"]` — `C#/70/photos`, `S#/products/67/photos`; *(key absent)* — `H#/products/25/photos` |
| `"photo-product-071"` | `notes` | `"species to confirm"` — `C#/70/notes`, `S#/products/67/notes`; *(key absent)* — `H#/products/25/notes` |
| `"photo-product-072"` | `photo` | `"IMG_9733.jpg"` — `C#/71/photo`, `S#/products/68/photo`; *(key absent)* — `H#/products/26/photo` |
| `"photo-product-072"` | `photos` | `["IMG_9733.jpg"]` — `C#/71/photos`, `S#/products/68/photos`; *(key absent)* — `H#/products/26/photos` |
| `"photo-product-072"` | `notes` | `"variety to confirm"` — `C#/71/notes`, `S#/products/68/notes`; *(key absent)* — `H#/products/26/notes` |
| `"photo-product-073"` | `photo` | `"IMG_9733.jpg"` — `C#/72/photo`, `S#/products/69/photo`; *(key absent)* — `H#/products/27/photo` |
| `"photo-product-073"` | `photos` | `["IMG_9733.jpg"]` — `C#/72/photos`, `S#/products/69/photos`; *(key absent)* — `H#/products/27/photos` |
| `"photo-product-073"` | `notes` | `""` — `C#/72/notes`, `S#/products/69/notes`; *(key absent)* — `H#/products/27/notes` |
| `"photo-product-074"` | `photo` | `"IMG_9733.jpg"` — `C#/73/photo`, `S#/products/70/photo`; *(key absent)* — `H#/products/28/photo` |
| `"photo-product-074"` | `photos` | `["IMG_9733.jpg"]` — `C#/73/photos`, `S#/products/70/photos`; *(key absent)* — `H#/products/28/photos` |
| `"photo-product-074"` | `notes` | `""` — `C#/73/notes`, `S#/products/70/notes`; *(key absent)* — `H#/products/28/notes` |
| `"photo-product-075"` | `photo` | `"IMG_9733.jpg"` — `C#/74/photo`, `S#/products/71/photo`; *(key absent)* — `H#/products/29/photo` |
| `"photo-product-075"` | `photos` | `["IMG_9733.jpg"]` — `C#/74/photos`, `S#/products/71/photos`; *(key absent)* — `H#/products/29/photos` |
| `"photo-product-075"` | `notes` | `""` — `C#/74/notes`, `S#/products/71/notes`; *(key absent)* — `H#/products/29/notes` |
| `"photo-product-076"` | `photo` | `"IMG_9733.jpg"` — `C#/75/photo`, `S#/products/72/photo`; *(key absent)* — `H#/products/30/photo` |
| `"photo-product-076"` | `photos` | `["IMG_9733.jpg"]` — `C#/75/photos`, `S#/products/72/photos`; *(key absent)* — `H#/products/30/photos` |
| `"photo-product-076"` | `notes` | `"variety to confirm"` — `C#/75/notes`, `S#/products/72/notes`; *(key absent)* — `H#/products/30/notes` |
| `"photo-product-077"` | `photo` | `"IMG_9734.jpg"` — `C#/76/photo`, `S#/products/73/photo`; *(key absent)* — `H#/products/31/photo` |
| `"photo-product-077"` | `photos` | `["IMG_9734.jpg"]` — `C#/76/photos`, `S#/products/73/photos`; *(key absent)* — `H#/products/31/photos` |
| `"photo-product-077"` | `notes` | `"variety to confirm"` — `C#/76/notes`, `S#/products/73/notes`; *(key absent)* — `H#/products/31/notes` |
| `"photo-product-078"` | `photo` | `"IMG_9734.jpg"` — `C#/77/photo`, `S#/products/74/photo`; *(key absent)* — `H#/products/7/photo` |
| `"photo-product-078"` | `photos` | `["IMG_9734.jpg", "IMG_9735.jpg"]` — `C#/77/photos`, `S#/products/74/photos`; *(key absent)* — `H#/products/7/photos` |
| `"photo-product-078"` | `notes` | `"selling unit to confirm"` — `C#/77/notes`, `S#/products/74/notes`; *(key absent)* — `H#/products/7/notes` |
| `"photo-product-079"` | `photo` | `"IMG_9735.jpg"` — `C#/78/photo`, `S#/products/75/photo`; *(key absent)* — `H#/products/32/photo` |
| `"photo-product-079"` | `photos` | `["IMG_9735.jpg"]` — `C#/78/photos`, `S#/products/75/photos`; *(key absent)* — `H#/products/32/photos` |
| `"photo-product-079"` | `notes` | `"selling unit to confirm"` — `C#/78/notes`, `S#/products/75/notes`; *(key absent)* — `H#/products/32/notes` |
| `"photo-product-080"` | `photo` | `"IMG_9735.jpg"` — `C#/79/photo`, `S#/products/76/photo`; *(key absent)* — `H#/products/8/photo` |
| `"photo-product-080"` | `photos` | `["IMG_9735.jpg"]` — `C#/79/photos`, `S#/products/76/photos`; *(key absent)* — `H#/products/8/photos` |
| `"photo-product-080"` | `notes` | `"variety to confirm"` — `C#/79/notes`; `"Pale smooth-skinned melon; exact variety still needs confirmation."` — `S#/products/76/notes`; *(key absent)* — `H#/products/8/notes` |
| `"photo-product-081"` | `photo` | `"IMG_9736.jpg"` — `C#/80/photo`, `S#/products/77/photo`; *(key absent)* — `H#/products/9/photo` |
| `"photo-product-081"` | `photos` | `["IMG_9736.jpg"]` — `C#/80/photos`, `S#/products/77/photos`; *(key absent)* — `H#/products/9/photos` |
| `"photo-product-081"` | `notes` | `"variety to confirm"` — `C#/80/notes`, `S#/products/77/notes`; *(key absent)* — `H#/products/9/notes` |
| `"photo-product-082"` | `photo` | `"IMG_9738.jpg"` — `C#/81/photo`, `S#/products/78/photo`; *(key absent)* — `H#/products/113/photo` |
| `"photo-product-082"` | `photos` | `["IMG_9738.jpg"]` — `C#/81/photos`, `S#/products/78/photos`; *(key absent)* — `H#/products/113/photos` |
| `"photo-product-082"` | `notes` | `"shape and package to confirm"` — `C#/81/notes`; `"Pasta shape identification is visual; confirm exact packaging SKU."` — `S#/products/78/notes`; *(key absent)* — `H#/products/113/notes` |
| `"photo-product-083"` | `photo` | `"IMG_9709.jpg"` — `C#/82/photo`, `S#/products/79/photo`; *(key absent)* — `H#/products/161/photo` |
| `"photo-product-083"` | `photos` | `["IMG_9709.jpg"]` — `C#/82/photos`, `S#/products/79/photos`; *(key absent)* — `H#/products/161/photos` |
| `"photo-product-083"` | `notes` | `""` — `C#/82/notes`, `S#/products/79/notes`; *(key absent)* — `H#/products/161/notes` |
| `"photo-product-084"` | `photo` | `"IMG_9709.jpg"` — `C#/83/photo`, `S#/products/80/photo`; *(key absent)* — `H#/products/162/photo` |
| `"photo-product-084"` | `photos` | `["IMG_9709.jpg"]` — `C#/83/photos`, `S#/products/80/photos`; *(key absent)* — `H#/products/162/photos` |
| `"photo-product-084"` | `notes` | `""` — `C#/83/notes`, `S#/products/80/notes`; *(key absent)* — `H#/products/162/notes` |
| `"photo-product-085"` | `photo` | `"IMG_9709.jpg"` — `C#/84/photo`, `S#/products/81/photo`; *(key absent)* — `H#/products/163/photo` |
| `"photo-product-085"` | `photos` | `["IMG_9709.jpg"]` — `C#/84/photos`, `S#/products/81/photos`; *(key absent)* — `H#/products/163/photos` |
| `"photo-product-085"` | `notes` | `""` — `C#/84/notes`, `S#/products/81/notes`; *(key absent)* — `H#/products/163/notes` |
| `"photo-product-086"` | `photo` | `"IMG_9709.jpg"` — `C#/85/photo`, `S#/products/82/photo`; *(key absent)* — `H#/products/164/photo` |
| `"photo-product-086"` | `photos` | `["IMG_9709.jpg"]` — `C#/85/photos`, `S#/products/82/photos`; *(key absent)* — `H#/products/164/photos` |
| `"photo-product-086"` | `notes` | `""` — `C#/85/notes`, `S#/products/82/notes`; *(key absent)* — `H#/products/164/notes` |
| `"photo-product-087"` | `photo` | `"IMG_9709.jpg"` — `C#/86/photo`, `S#/products/83/photo`; *(key absent)* — `H#/products/165/photo` |
| `"photo-product-087"` | `photos` | `["IMG_9709.jpg"]` — `C#/86/photos`, `S#/products/83/photos`; *(key absent)* — `H#/products/165/photos` |
| `"photo-product-087"` | `notes` | `""` — `C#/86/notes`, `S#/products/83/notes`; *(key absent)* — `H#/products/165/notes` |
| `"photo-product-088"` | `photo` | `"IMG_9723.jpg"` — `C#/87/photo`, `S#/products/84/photo`; *(key absent)* — `H#/products/114/photo` |
| `"photo-product-088"` | `photos` | `["IMG_9723.jpg"]` — `C#/87/photos`, `S#/products/84/photos`; *(key absent)* — `H#/products/114/photos` |
| `"photo-product-088"` | `notes` | `""` — `C#/87/notes`, `S#/products/84/notes`; *(key absent)* — `H#/products/114/notes` |
| `"photo-product-089"` | `photo` | `"IMG_9723.jpg"` — `C#/88/photo`, `S#/products/85/photo`; *(key absent)* — `H#/products/115/photo` |
| `"photo-product-089"` | `photos` | `["IMG_9723.jpg"]` — `C#/88/photos`, `S#/products/85/photos`; *(key absent)* — `H#/products/115/photos` |
| `"photo-product-089"` | `notes` | `""` — `C#/88/notes`, `S#/products/85/notes`; *(key absent)* — `H#/products/115/notes` |
| `"photo-product-090"` | `photo` | `"IMG_9723.jpg"` — `C#/89/photo`, `S#/products/86/photo`; *(key absent)* — `H#/products/116/photo` |
| `"photo-product-090"` | `photos` | `["IMG_9723.jpg"]` — `C#/89/photos`, `S#/products/86/photos`; *(key absent)* — `H#/products/116/photos` |
| `"photo-product-090"` | `notes` | `""` — `C#/89/notes`, `S#/products/86/notes`; *(key absent)* — `H#/products/116/notes` |
| `"photo-product-091"` | `photo` | `"IMG_9723.jpg"` — `C#/90/photo`, `S#/products/87/photo`; *(key absent)* — `H#/products/117/photo` |
| `"photo-product-091"` | `photos` | `["IMG_9723.jpg"]` — `C#/90/photos`, `S#/products/87/photos`; *(key absent)* — `H#/products/117/photos` |
| `"photo-product-091"` | `notes` | `""` — `C#/90/notes`, `S#/products/87/notes`; *(key absent)* — `H#/products/117/notes` |
| `"photo-product-092"` | `photo` | `"IMG_9709.jpg"` — `C#/91/photo`, `S#/products/88/photo`; *(key absent)* — `H#/products/166/photo` |
| `"photo-product-092"` | `photos` | `["IMG_9709.jpg"]` — `C#/91/photos`, `S#/products/88/photos`; *(key absent)* — `H#/products/166/photos` |
| `"photo-product-092"` | `notes` | `""` — `C#/91/notes`, `S#/products/88/notes`; *(key absent)* — `H#/products/166/notes` |
| `"photo-product-093"` | `photo` | `"IMG_9709.jpg"` — `C#/92/photo`, `S#/products/89/photo`; *(key absent)* — `H#/products/118/photo` |
| `"photo-product-093"` | `photos` | `["IMG_9709.jpg"]` — `C#/92/photos`, `S#/products/89/photos`; *(key absent)* — `H#/products/118/photos` |
| `"photo-product-093"` | `notes` | `""` — `C#/92/notes`, `S#/products/89/notes`; *(key absent)* — `H#/products/118/notes` |
| `"photo-product-094"` | `photo` | `"IMG_9709.jpg"` — `C#/93/photo`, `S#/products/90/photo`; *(key absent)* — `H#/products/167/photo` |
| `"photo-product-094"` | `photos` | `["IMG_9709.jpg"]` — `C#/93/photos`, `S#/products/90/photos`; *(key absent)* — `H#/products/167/photos` |
| `"photo-product-094"` | `notes` | `""` — `C#/93/notes`, `S#/products/90/notes`; *(key absent)* — `H#/products/167/notes` |
| `"photo-product-095"` | `photo` | `"IMG_9709.jpg"` — `C#/94/photo`, `S#/products/91/photo`; *(key absent)* — `H#/products/168/photo` |
| `"photo-product-095"` | `photos` | `["IMG_9709.jpg"]` — `C#/94/photos`, `S#/products/91/photos`; *(key absent)* — `H#/products/168/photos` |
| `"photo-product-095"` | `notes` | `""` — `C#/94/notes`, `S#/products/91/notes`; *(key absent)* — `H#/products/168/notes` |
| `"photo-product-096"` | `photo` | `"IMG_9714.jpg"` — `S#/products/92/photo`, `N#/0/photo`; *(key absent)* — `H#/products/10/photo` |
| `"photo-product-096"` | `photos` | `["IMG_9714.jpg"]` — `S#/products/92/photos`, `N#/0/photos`; *(key absent)* — `H#/products/10/photos` |
| `"photo-product-096"` | `notes` | `"Purple round fruit with smooth and wrinkled shells visible beside avocados; variety not determined."` — `S#/products/92/notes`, `N#/0/notes`; *(key absent)* — `H#/products/10/notes` |
| `"photo-product-097"` | `photo` | `"IMG_9729.jpg"` — `S#/products/93/photo`, `N#/1/photo`; *(key absent)* — `H#/products/11/photo` |
| `"photo-product-097"` | `photos` | `["IMG_9729.jpg"]` — `S#/products/93/photos`, `N#/1/photos`; *(key absent)* — `H#/products/11/photos` |
| `"photo-product-097"` | `notes` | `"FIGS shelf sign and green/purple fruit behind strawberry display; variety not determined."` — `S#/products/93/notes`, `N#/1/notes`; *(key absent)* — `H#/products/11/notes` |
| `"photo-product-098"` | `photo` | `"IMG_9729.jpg"` — `S#/products/94/photo`, `N#/2/photo`; *(key absent)* — `H#/products/12/photo` |
| `"photo-product-098"` | `photos` | `["IMG_9729.jpg"]` — `S#/products/94/photos`, `N#/2/photos`; *(key absent)* — `H#/products/12/photos` |
| `"photo-product-098"` | `notes` | `"Blackberries shelf sign and baskets visible."` — `S#/products/94/notes`, `N#/2/notes`; *(key absent)* — `H#/products/12/notes` |
| `"photo-product-099"` | `photo` | `"IMG_9715.jpg"` — `S#/products/95/photo`, `N#/3/photo`; *(key absent)* — `H#/products/33/photo` |
| `"photo-product-099"` | `photos` | `["IMG_9715.jpg"]` — `S#/products/95/photos`, `N#/3/photos`; *(key absent)* — `H#/products/33/photos` |
| `"photo-product-099"` | `notes` | `"Garlic displayed in Christopher Ranch carton; carton does not conclusively establish grower."` — `S#/products/95/notes`, `N#/3/notes`; *(key absent)* — `H#/products/33/notes` |
| `"photo-product-100"` | `photo` | `"IMG_9715.jpg"` — `S#/products/96/photo`, `N#/4/photo`; *(key absent)* — `H#/products/34/photo` |
| `"photo-product-100"` | `photos` | `["IMG_9715.jpg"]` — `S#/products/96/photos`, `N#/4/photos`; *(key absent)* — `H#/products/34/photos` |
| `"photo-product-100"` | `notes` | `"Hummingbird shallots bag among loose shallots; attribution needs confirmation."` — `S#/products/96/notes`, `N#/4/notes`; *(key absent)* — `H#/products/34/notes` |
| `"photo-product-101"` | `photo` | `"IMG_9715.jpg"` — `S#/products/97/photo`, `N#/5/photo`; *(key absent)* — `H#/products/35/photo` |
| `"photo-product-101"` | `photos` | `["IMG_9715.jpg"]` — `S#/products/97/photos`, `N#/5/photos`; *(key absent)* — `H#/products/35/photos` |
| `"photo-product-101"` | `notes` | `"Brown-skinned onions visible; exact cultivar not established."` — `S#/products/97/notes`, `N#/5/notes`; *(key absent)* — `H#/products/35/notes` |
| `"photo-product-102"` | `photo` | `"IMG_9715.jpg"` — `S#/products/98/photo`, `N#/6/photo`; *(key absent)* — `H#/products/36/photo` |
| `"photo-product-102"` | `photos` | `["IMG_9715.jpg"]` — `S#/products/98/photos`, `N#/6/photos`; *(key absent)* — `H#/products/36/photos` |
| `"photo-product-102"` | `notes` | `"Purple/red-skinned onions visible."` — `S#/products/98/notes`, `N#/6/notes`; *(key absent)* — `H#/products/36/notes` |
| `"photo-product-103"` | `photo` | `"IMG_9730.jpg"` — `S#/products/99/photo`, `N#/7/photo`; *(key absent)* — `H#/products/37/photo` |
| `"photo-product-103"` | `photos` | `["IMG_9730.jpg"]` — `S#/products/99/photos`, `N#/7/photos`; *(key absent)* — `H#/products/37/photos` |
| `"photo-product-103"` | `notes` | `"Radicchio shelf label and purple heads visible."` — `S#/products/99/notes`, `N#/7/notes`; *(key absent)* — `H#/products/37/notes` |
| `"photo-product-104"` | `photo` | `"IMG_9730.jpg"` — `S#/products/100/photo`, `N#/8/photo`; *(key absent)* — `H#/products/38/photo` |
| `"photo-product-104"` | `photos` | `["IMG_9730.jpg"]` — `S#/products/100/photos`, `N#/8/photos`; *(key absent)* — `H#/products/38/photos` |
| `"photo-product-104"` | `notes` | `"Purple Daikon shelf label and purple roots visible."` — `S#/products/100/notes`, `N#/8/notes`; *(key absent)* — `H#/products/38/notes` |
| `"photo-product-105"` | `photo` | `"IMG_9707.jpg"` — `S#/products/101/photo`, `P#/0/photo`; *(key absent)* — `H#/products/119/photo` |
| `"photo-product-105"` | `photos` | `["IMG_9707.jpg"]` — `S#/products/101/photos`, `P#/0/photos`; *(key absent)* — `H#/products/119/photos` |
| `"photo-product-105"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/101/notes`, `P#/0/notes`; *(key absent)* — `H#/products/119/notes` |
| `"photo-product-106"` | `photo` | `"IMG_9707.jpg"` — `S#/products/102/photo`, `P#/1/photo`; *(key absent)* — `H#/products/120/photo` |
| `"photo-product-106"` | `photos` | `["IMG_9707.jpg"]` — `S#/products/102/photos`, `P#/1/photos`; *(key absent)* — `H#/products/120/photos` |
| `"photo-product-106"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/102/notes`, `P#/1/notes`; *(key absent)* — `H#/products/120/notes` |
| `"photo-product-107"` | `photo` | `"IMG_9707.jpg"` — `S#/products/103/photo`, `P#/2/photo`; *(key absent)* — `H#/products/121/photo` |
| `"photo-product-107"` | `photos` | `["IMG_9707.jpg"]` — `S#/products/103/photos`, `P#/2/photos`; *(key absent)* — `H#/products/121/photos` |
| `"photo-product-107"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/103/notes`, `P#/2/notes`; *(key absent)* — `H#/products/121/notes` |
| `"photo-product-108"` | `photo` | `"IMG_9707.jpg"` — `S#/products/104/photo`, `P#/3/photo`; *(key absent)* — `H#/products/122/photo` |
| `"photo-product-108"` | `photos` | `["IMG_9707.jpg"]` — `S#/products/104/photos`, `P#/3/photos`; *(key absent)* — `H#/products/122/photos` |
| `"photo-product-108"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/104/notes`, `P#/3/notes`; *(key absent)* — `H#/products/122/notes` |
| `"photo-product-109"` | `photo` | `"IMG_9710.jpg"` — `S#/products/105/photo`, `P#/4/photo`; *(key absent)* — `H#/products/123/photo` |
| `"photo-product-109"` | `photos` | `["IMG_9710.jpg"]` — `S#/products/105/photos`, `P#/4/photos`; *(key absent)* — `H#/products/123/photos` |
| `"photo-product-109"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/105/notes`, `P#/4/notes`; *(key absent)* — `H#/products/123/notes` |
| `"photo-product-110"` | `photo` | `"IMG_9710.jpg"` — `S#/products/106/photo`, `P#/5/photo`; *(key absent)* — `H#/products/124/photo` |
| `"photo-product-110"` | `photos` | `["IMG_9710.jpg"]` — `S#/products/106/photos`, `P#/5/photos`; *(key absent)* — `H#/products/124/photos` |
| `"photo-product-110"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/106/notes`, `P#/5/notes`; *(key absent)* — `H#/products/124/notes` |
| `"photo-product-111"` | `photo` | `"IMG_9710.jpg"` — `S#/products/107/photo`, `P#/6/photo`; *(key absent)* — `H#/products/125/photo` |
| `"photo-product-111"` | `photos` | `["IMG_9710.jpg"]` — `S#/products/107/photos`, `P#/6/photos`; *(key absent)* — `H#/products/125/photos` |
| `"photo-product-111"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/107/notes`, `P#/6/notes`; *(key absent)* — `H#/products/125/notes` |
| `"photo-product-112"` | `photo` | `"IMG_9710.jpg"` — `S#/products/108/photo`, `P#/7/photo`; *(key absent)* — `H#/products/126/photo` |
| `"photo-product-112"` | `photos` | `["IMG_9710.jpg"]` — `S#/products/108/photos`, `P#/7/photos`; *(key absent)* — `H#/products/126/photos` |
| `"photo-product-112"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/108/notes`, `P#/7/notes`; *(key absent)* — `H#/products/126/notes` |
| `"photo-product-113"` | `photo` | `"IMG_9710.jpg"` — `S#/products/109/photo`, `P#/8/photo`; *(key absent)* — `H#/products/127/photo` |
| `"photo-product-113"` | `photos` | `["IMG_9710.jpg"]` — `S#/products/109/photos`, `P#/8/photos`; *(key absent)* — `H#/products/127/photos` |
| `"photo-product-113"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/109/notes`, `P#/8/notes`; *(key absent)* — `H#/products/127/notes` |
| `"photo-product-114"` | `photo` | `"IMG_9710.jpg"` — `S#/products/110/photo`, `P#/9/photo`; *(key absent)* — `H#/products/128/photo` |
| `"photo-product-114"` | `photos` | `["IMG_9710.jpg"]` — `S#/products/110/photos`, `P#/9/photos`; *(key absent)* — `H#/products/128/photos` |
| `"photo-product-114"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/110/notes`, `P#/9/notes`; *(key absent)* — `H#/products/128/notes` |
| `"photo-product-115"` | `photo` | `"IMG_9710.jpg"` — `S#/products/111/photo`, `P#/10/photo`; *(key absent)* — `H#/products/129/photo` |
| `"photo-product-115"` | `photos` | `["IMG_9710.jpg"]` — `S#/products/111/photos`, `P#/10/photos`; *(key absent)* — `H#/products/129/photos` |
| `"photo-product-115"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/111/notes`, `P#/10/notes`; *(key absent)* — `H#/products/129/notes` |
| `"photo-product-116"` | `photo` | `"IMG_9710.jpg"` — `S#/products/112/photo`, `P#/11/photo`; *(key absent)* — `H#/products/130/photo` |
| `"photo-product-116"` | `photos` | `["IMG_9710.jpg"]` — `S#/products/112/photos`, `P#/11/photos`; *(key absent)* — `H#/products/130/photos` |
| `"photo-product-116"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/112/notes`, `P#/11/notes`; *(key absent)* — `H#/products/130/notes` |
| `"photo-product-117"` | `photo` | `"IMG_9710.jpg"` — `S#/products/113/photo`, `P#/12/photo`; *(key absent)* — `H#/products/131/photo` |
| `"photo-product-117"` | `photos` | `["IMG_9710.jpg"]` — `S#/products/113/photos`, `P#/12/photos`; *(key absent)* — `H#/products/131/photos` |
| `"photo-product-117"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/113/notes`, `P#/12/notes`; *(key absent)* — `H#/products/131/notes` |
| `"photo-product-118"` | `photo` | `"IMG_9710.jpg"` — `S#/products/114/photo`, `P#/13/photo`; *(key absent)* — `H#/products/132/photo` |
| `"photo-product-118"` | `photos` | `["IMG_9710.jpg"]` — `S#/products/114/photos`, `P#/13/photos`; *(key absent)* — `H#/products/132/photos` |
| `"photo-product-118"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/114/notes`, `P#/13/notes`; *(key absent)* — `H#/products/132/notes` |
| `"photo-product-119"` | `photo` | `"IMG_9710.jpg"` — `S#/products/115/photo`, `P#/14/photo`; *(key absent)* — `H#/products/133/photo` |
| `"photo-product-119"` | `photos` | `["IMG_9710.jpg"]` — `S#/products/115/photos`, `P#/14/photos`; *(key absent)* — `H#/products/133/photos` |
| `"photo-product-119"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/115/notes`, `P#/14/notes`; *(key absent)* — `H#/products/133/notes` |
| `"photo-product-120"` | `photo` | `"IMG_9711.jpg"` — `S#/products/116/photo`, `P#/15/photo`; *(key absent)* — `H#/products/134/photo` |
| `"photo-product-120"` | `photos` | `["IMG_9711.jpg"]` — `S#/products/116/photos`, `P#/15/photos`; *(key absent)* — `H#/products/134/photos` |
| `"photo-product-120"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/116/notes`, `P#/15/notes`; *(key absent)* — `H#/products/134/notes` |
| `"photo-product-121"` | `photo` | `"IMG_9711.jpg"` — `S#/products/117/photo`, `P#/16/photo`; *(key absent)* — `H#/products/135/photo` |
| `"photo-product-121"` | `photos` | `["IMG_9711.jpg"]` — `S#/products/117/photos`, `P#/16/photos`; *(key absent)* — `H#/products/135/photos` |
| `"photo-product-121"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/117/notes`, `P#/16/notes`; *(key absent)* — `H#/products/135/notes` |
| `"photo-product-122"` | `photo` | `"IMG_9713.jpg"` — `S#/products/118/photo`, `P#/17/photo`; *(key absent)* — `H#/products/87/photo` |
| `"photo-product-122"` | `photos` | `["IMG_9713.jpg"]` — `S#/products/118/photos`, `P#/17/photos`; *(key absent)* — `H#/products/87/photos` |
| `"photo-product-122"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/118/notes`, `P#/17/notes`; *(key absent)* — `H#/products/87/notes` |
| `"photo-product-123"` | `photo` | `"IMG_9713.jpg"` — `S#/products/119/photo`, `P#/18/photo`; *(key absent)* — `H#/products/88/photo` |
| `"photo-product-123"` | `photos` | `["IMG_9713.jpg"]` — `S#/products/119/photos`, `P#/18/photos`; *(key absent)* — `H#/products/88/photos` |
| `"photo-product-123"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/119/notes`, `P#/18/notes`; *(key absent)* — `H#/products/88/notes` |
| `"photo-product-124"` | `photo` | `"IMG_9713.jpg"` — `S#/products/120/photo`, `P#/19/photo`; *(key absent)* — `H#/products/89/photo` |
| `"photo-product-124"` | `photos` | `["IMG_9713.jpg"]` — `S#/products/120/photos`, `P#/19/photos`; *(key absent)* — `H#/products/89/photos` |
| `"photo-product-124"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/120/notes`, `P#/19/notes`; *(key absent)* — `H#/products/89/notes` |
| `"photo-product-125"` | `photo` | `"IMG_9719.jpg"` — `S#/products/121/photo`, `P#/20/photo`; *(key absent)* — `H#/products/78/photo` |
| `"photo-product-125"` | `photos` | `["IMG_9719.jpg"]` — `S#/products/121/photos`, `P#/20/photos`; *(key absent)* — `H#/products/78/photos` |
| `"photo-product-125"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/121/notes`, `P#/20/notes`; *(key absent)* — `H#/products/78/notes` |
| `"photo-product-126"` | `photo` | `"IMG_9719.jpg"` — `S#/products/122/photo`, `P#/21/photo`; *(key absent)* — `H#/products/79/photo` |
| `"photo-product-126"` | `photos` | `["IMG_9719.jpg"]` — `S#/products/122/photos`, `P#/21/photos`; *(key absent)* — `H#/products/79/photos` |
| `"photo-product-126"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/122/notes`, `P#/21/notes`; *(key absent)* — `H#/products/79/notes` |
| `"photo-product-127"` | `photo` | `"IMG_9719.jpg"` — `S#/products/123/photo`, `P#/22/photo`; *(key absent)* — `H#/products/80/photo` |
| `"photo-product-127"` | `photos` | `["IMG_9719.jpg"]` — `S#/products/123/photos`, `P#/22/photos`; *(key absent)* — `H#/products/80/photos` |
| `"photo-product-127"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/123/notes`, `P#/22/notes`; *(key absent)* — `H#/products/80/notes` |
| `"photo-product-128"` | `photo` | `"IMG_9720.jpg"` — `S#/products/124/photo`, `P#/23/photo`; *(key absent)* — `H#/products/81/photo` |
| `"photo-product-128"` | `photos` | `["IMG_9720.jpg"]` — `S#/products/124/photos`, `P#/23/photos`; *(key absent)* — `H#/products/81/photos` |
| `"photo-product-128"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/124/notes`, `P#/23/notes`; *(key absent)* — `H#/products/81/notes` |
| `"photo-product-129"` | `photo` | `"IMG_9720.jpg"` — `S#/products/125/photo`, `P#/24/photo`; *(key absent)* — `H#/products/82/photo` |
| `"photo-product-129"` | `photos` | `["IMG_9720.jpg"]` — `S#/products/125/photos`, `P#/24/photos`; *(key absent)* — `H#/products/82/photos` |
| `"photo-product-129"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/125/notes`, `P#/24/notes`; *(key absent)* — `H#/products/82/notes` |
| `"photo-product-130"` | `photo` | `"IMG_9722.jpg"` — `S#/products/126/photo`, `P#/25/photo`; *(key absent)* — `H#/products/83/photo` |
| `"photo-product-130"` | `photos` | `["IMG_9722.jpg"]` — `S#/products/126/photos`, `P#/25/photos`; *(key absent)* — `H#/products/83/photos` |
| `"photo-product-130"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/126/notes`, `P#/25/notes`; *(key absent)* — `H#/products/83/notes` |
| `"photo-product-131"` | `photo` | `"IMG_9722.jpg"` — `S#/products/127/photo`, `P#/26/photo`; *(key absent)* — `H#/products/84/photo` |
| `"photo-product-131"` | `photos` | `["IMG_9722.jpg"]` — `S#/products/127/photos`, `P#/26/photos`; *(key absent)* — `H#/products/84/photos` |
| `"photo-product-131"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/127/notes`, `P#/26/notes`; *(key absent)* — `H#/products/84/notes` |
| `"photo-product-132"` | `photo` | `"IMG_9722.jpg"` — `S#/products/128/photo`, `P#/27/photo`; *(key absent)* — `H#/products/85/photo` |
| `"photo-product-132"` | `photos` | `["IMG_9722.jpg"]` — `S#/products/128/photos`, `P#/27/photos`; *(key absent)* — `H#/products/85/photos` |
| `"photo-product-132"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/128/notes`, `P#/27/notes`; *(key absent)* — `H#/products/85/notes` |
| `"photo-product-133"` | `photo` | `"IMG_9722.jpg"` — `P#/28/photo`; *(key absent)* — `H#/products/171/photo` |
| `"photo-product-133"` | `photos` | `["IMG_9722.jpg"]` — `P#/28/photos`; *(key absent)* — `H#/products/171/photos` |
| `"photo-product-133"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `P#/28/notes`; *(key absent)* — `H#/products/171/notes` |
| `"photo-product-134"` | `photo` | `"IMG_9724.jpg"` — `S#/products/129/photo`, `P#/29/photo`; *(key absent)* — `H#/products/136/photo` |
| `"photo-product-134"` | `photos` | `["IMG_9724.jpg"]` — `S#/products/129/photos`, `P#/29/photos`; *(key absent)* — `H#/products/136/photos` |
| `"photo-product-134"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/129/notes`, `P#/29/notes`; *(key absent)* — `H#/products/136/notes` |
| `"photo-product-135"` | `photo` | `"IMG_9724.jpg"` — `S#/products/130/photo`, `P#/30/photo`; *(key absent)* — `H#/products/137/photo` |
| `"photo-product-135"` | `photos` | `["IMG_9724.jpg"]` — `S#/products/130/photos`, `P#/30/photos`; *(key absent)* — `H#/products/137/photos` |
| `"photo-product-135"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/130/notes`, `P#/30/notes`; *(key absent)* — `H#/products/137/notes` |
| `"photo-product-136"` | `photo` | `"IMG_9724.jpg"` — `S#/products/131/photo`, `P#/31/photo`; *(key absent)* — `H#/products/138/photo` |
| `"photo-product-136"` | `photos` | `["IMG_9724.jpg"]` — `S#/products/131/photos`, `P#/31/photos`; *(key absent)* — `H#/products/138/photos` |
| `"photo-product-136"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/131/notes`, `P#/31/notes`; *(key absent)* — `H#/products/138/notes` |
| `"photo-product-137"` | `photo` | `"IMG_9724.jpg"` — `S#/products/132/photo`, `P#/32/photo`; *(key absent)* — `H#/products/139/photo` |
| `"photo-product-137"` | `photos` | `["IMG_9724.jpg"]` — `S#/products/132/photos`, `P#/32/photos`; *(key absent)* — `H#/products/139/photos` |
| `"photo-product-137"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/132/notes`, `P#/32/notes`; *(key absent)* — `H#/products/139/notes` |
| `"photo-product-138"` | `photo` | `"IMG_9728.jpg"` — `S#/products/133/photo`, `P#/33/photo`; *(key absent)* — `H#/products/140/photo` |
| `"photo-product-138"` | `photos` | `["IMG_9728.jpg"]` — `S#/products/133/photos`, `P#/33/photos`; *(key absent)* — `H#/products/140/photos` |
| `"photo-product-138"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/133/notes`, `P#/33/notes`; *(key absent)* — `H#/products/140/notes` |
| `"photo-product-139"` | `photo` | `"IMG_9728.jpg"` — `S#/products/134/photo`, `P#/34/photo`; *(key absent)* — `H#/products/141/photo` |
| `"photo-product-139"` | `photos` | `["IMG_9728.jpg"]` — `S#/products/134/photos`, `P#/34/photos`; *(key absent)* — `H#/products/141/photos` |
| `"photo-product-139"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/134/notes`, `P#/34/notes`; *(key absent)* — `H#/products/141/notes` |
| `"photo-product-140"` | `photo` | `"IMG_9728.jpg"` — `S#/products/135/photo`, `P#/35/photo`; *(key absent)* — `H#/products/142/photo` |
| `"photo-product-140"` | `photos` | `["IMG_9728.jpg"]` — `S#/products/135/photos`, `P#/35/photos`; *(key absent)* — `H#/products/142/photos` |
| `"photo-product-140"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/135/notes`, `P#/35/notes`; *(key absent)* — `H#/products/142/notes` |
| `"photo-product-141"` | `photo` | `"IMG_9728.jpg"` — `S#/products/136/photo`, `P#/36/photo`; *(key absent)* — `H#/products/143/photo` |
| `"photo-product-141"` | `photos` | `["IMG_9728.jpg"]` — `S#/products/136/photos`, `P#/36/photos`; *(key absent)* — `H#/products/143/photos` |
| `"photo-product-141"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/136/notes`, `P#/36/notes`; *(key absent)* — `H#/products/143/notes` |
| `"photo-product-142"` | `photo` | `"IMG_9728.jpg"` — `S#/products/137/photo`, `P#/37/photo`; *(key absent)* — `H#/products/144/photo` |
| `"photo-product-142"` | `photos` | `["IMG_9728.jpg"]` — `S#/products/137/photos`, `P#/37/photos`; *(key absent)* — `H#/products/144/photos` |
| `"photo-product-142"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/137/notes`, `P#/37/notes`; *(key absent)* — `H#/products/144/notes` |
| `"photo-product-143"` | `photo` | `"IMG_9728.jpg"` — `S#/products/138/photo`, `P#/38/photo`; *(key absent)* — `H#/products/145/photo` |
| `"photo-product-143"` | `photos` | `["IMG_9728.jpg"]` — `S#/products/138/photos`, `P#/38/photos`; *(key absent)* — `H#/products/145/photos` |
| `"photo-product-143"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/138/notes`, `P#/38/notes`; *(key absent)* — `H#/products/145/notes` |
| `"photo-product-144"` | `photo` | `"IMG_9728.jpg"` — `S#/products/139/photo`, `P#/39/photo`; *(key absent)* — `H#/products/146/photo` |
| `"photo-product-144"` | `photos` | `["IMG_9728.jpg"]` — `S#/products/139/photos`, `P#/39/photos`; *(key absent)* — `H#/products/146/photos` |
| `"photo-product-144"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/139/notes`, `P#/39/notes`; *(key absent)* — `H#/products/146/notes` |
| `"photo-product-145"` | `photo` | `"IMG_9731.jpg"` — `S#/products/140/photo`, `P#/40/photo`; *(key absent)* — `H#/products/39/photo` |
| `"photo-product-145"` | `photos` | `["IMG_9731.jpg"]` — `S#/products/140/photos`, `P#/40/photos`; *(key absent)* — `H#/products/39/photos` |
| `"photo-product-145"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/140/notes`, `P#/40/notes`; *(key absent)* — `H#/products/39/notes` |
| `"photo-product-146"` | `photo` | `"IMG_9731.jpg"` — `S#/products/141/photo`, `P#/41/photo`; *(key absent)* — `H#/products/40/photo` |
| `"photo-product-146"` | `photos` | `["IMG_9731.jpg"]` — `S#/products/141/photos`, `P#/41/photos`; *(key absent)* — `H#/products/40/photos` |
| `"photo-product-146"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/141/notes`, `P#/41/notes`; *(key absent)* — `H#/products/40/notes` |
| `"photo-product-147"` | `photo` | `"IMG_9731.jpg"` — `S#/products/142/photo`, `P#/42/photo`; *(key absent)* — `H#/products/41/photo` |
| `"photo-product-147"` | `photos` | `["IMG_9731.jpg"]` — `S#/products/142/photos`, `P#/42/photos`; *(key absent)* — `H#/products/41/photos` |
| `"photo-product-147"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/142/notes`, `P#/42/notes`; *(key absent)* — `H#/products/41/notes` |
| `"photo-product-148"` | `photo` | `"IMG_9731.jpg"` — `S#/products/143/photo`, `P#/43/photo`; *(key absent)* — `H#/products/42/photo` |
| `"photo-product-148"` | `photos` | `["IMG_9731.jpg"]` — `S#/products/143/photos`, `P#/43/photos`; *(key absent)* — `H#/products/42/photos` |
| `"photo-product-148"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/143/notes`, `P#/43/notes`; *(key absent)* — `H#/products/42/notes` |
| `"photo-product-149"` | `photo` | `"IMG_9731.jpg"` — `S#/products/144/photo`, `P#/44/photo`; *(key absent)* — `H#/products/43/photo` |
| `"photo-product-149"` | `photos` | `["IMG_9731.jpg"]` — `S#/products/144/photos`, `P#/44/photos`; *(key absent)* — `H#/products/43/photos` |
| `"photo-product-149"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/144/notes`, `P#/44/notes`; *(key absent)* — `H#/products/43/notes` |
| `"photo-product-150"` | `photo` | `"IMG_9732.jpg"` — `S#/products/145/photo`, `P#/45/photo`; *(key absent)* — `H#/products/44/photo` |
| `"photo-product-150"` | `photos` | `["IMG_9732.jpg"]` — `S#/products/145/photos`, `P#/45/photos`; *(key absent)* — `H#/products/44/photos` |
| `"photo-product-150"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/145/notes`, `P#/45/notes`; *(key absent)* — `H#/products/44/notes` |
| `"photo-product-151"` | `photo` | `"IMG_9732.jpg"` — `S#/products/146/photo`, `P#/46/photo`; *(key absent)* — `H#/products/45/photo` |
| `"photo-product-151"` | `photos` | `["IMG_9732.jpg"]` — `S#/products/146/photos`, `P#/46/photos`; *(key absent)* — `H#/products/45/photos` |
| `"photo-product-151"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/146/notes`, `P#/46/notes`; *(key absent)* — `H#/products/45/notes` |
| `"photo-product-152"` | `photo` | `"IMG_9732.jpg"` — `S#/products/147/photo`, `P#/47/photo`; *(key absent)* — `H#/products/46/photo` |
| `"photo-product-152"` | `photos` | `["IMG_9732.jpg"]` — `S#/products/147/photos`, `P#/47/photos`; *(key absent)* — `H#/products/46/photos` |
| `"photo-product-152"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/147/notes`, `P#/47/notes`; *(key absent)* — `H#/products/46/notes` |
| `"photo-product-153"` | `photo` | `"IMG_9732.jpg"` — `S#/products/148/photo`, `P#/48/photo`; *(key absent)* — `H#/products/47/photo` |
| `"photo-product-153"` | `photos` | `["IMG_9732.jpg"]` — `S#/products/148/photos`, `P#/48/photos`; *(key absent)* — `H#/products/47/photos` |
| `"photo-product-153"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/148/notes`, `P#/48/notes`; *(key absent)* — `H#/products/47/notes` |
| `"photo-product-154"` | `photo` | `"IMG_9732.jpg"` — `S#/products/149/photo`, `P#/49/photo`; *(key absent)* — `H#/products/48/photo` |
| `"photo-product-154"` | `photos` | `["IMG_9732.jpg"]` — `S#/products/149/photos`, `P#/49/photos`; *(key absent)* — `H#/products/48/photos` |
| `"photo-product-154"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/149/notes`, `P#/49/notes`; *(key absent)* — `H#/products/48/notes` |
| `"photo-product-155"` | `photo` | `"IMG_9732.jpg"` — `S#/products/150/photo`, `P#/50/photo`; *(key absent)* — `H#/products/49/photo` |
| `"photo-product-155"` | `photos` | `["IMG_9732.jpg"]` — `S#/products/150/photos`, `P#/50/photos`; *(key absent)* — `H#/products/49/photos` |
| `"photo-product-155"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/150/notes`, `P#/50/notes`; *(key absent)* — `H#/products/49/notes` |
| `"photo-product-156"` | `photo` | `"IMG_9732.jpg"` — `S#/products/151/photo`, `P#/51/photo`; *(key absent)* — `H#/products/50/photo` |
| `"photo-product-156"` | `photos` | `["IMG_9732.jpg"]` — `S#/products/151/photos`, `P#/51/photos`; *(key absent)* — `H#/products/50/photos` |
| `"photo-product-156"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/151/notes`, `P#/51/notes`; *(key absent)* — `H#/products/50/notes` |
| `"photo-product-157"` | `photo` | `"IMG_9733.jpg"` — `S#/products/152/photo`, `P#/52/photo`; *(key absent)* — `H#/products/51/photo` |
| `"photo-product-157"` | `photos` | `["IMG_9733.jpg"]` — `S#/products/152/photos`, `P#/52/photos`; *(key absent)* — `H#/products/51/photos` |
| `"photo-product-157"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/152/notes`, `P#/52/notes`; *(key absent)* — `H#/products/51/notes` |
| `"photo-product-158"` | `photo` | `"IMG_9733.jpg"` — `S#/products/153/photo`, `P#/53/photo`; *(key absent)* — `H#/products/52/photo` |
| `"photo-product-158"` | `photos` | `["IMG_9733.jpg"]` — `S#/products/153/photos`, `P#/53/photos`; *(key absent)* — `H#/products/52/photos` |
| `"photo-product-158"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/153/notes`, `P#/53/notes`; *(key absent)* — `H#/products/52/notes` |
| `"photo-product-159"` | `photo` | `"IMG_9733.jpg"` — `S#/products/154/photo`, `P#/54/photo`; *(key absent)* — `H#/products/53/photo` |
| `"photo-product-159"` | `photos` | `["IMG_9733.jpg"]` — `S#/products/154/photos`, `P#/54/photos`; *(key absent)* — `H#/products/53/photos` |
| `"photo-product-159"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/154/notes`, `P#/54/notes`; *(key absent)* — `H#/products/53/notes` |
| `"photo-product-160"` | `photo` | `"IMG_9733.jpg"` — `S#/products/155/photo`, `P#/55/photo`; *(key absent)* — `H#/products/54/photo` |
| `"photo-product-160"` | `photos` | `["IMG_9733.jpg"]` — `S#/products/155/photos`, `P#/55/photos`; *(key absent)* — `H#/products/54/photos` |
| `"photo-product-160"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/155/notes`, `P#/55/notes`; *(key absent)* — `H#/products/54/notes` |
| `"photo-product-161"` | `photo` | `"IMG_9733.jpg"` — `S#/products/156/photo`, `P#/56/photo`; *(key absent)* — `H#/products/55/photo` |
| `"photo-product-161"` | `photos` | `["IMG_9733.jpg"]` — `S#/products/156/photos`, `P#/56/photos`; *(key absent)* — `H#/products/55/photos` |
| `"photo-product-161"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/156/notes`, `P#/56/notes`; *(key absent)* — `H#/products/55/notes` |
| `"photo-product-162"` | `photo` | `"IMG_9733.jpg"` — `S#/products/157/photo`, `P#/57/photo`; *(key absent)* — `H#/products/56/photo` |
| `"photo-product-162"` | `photos` | `["IMG_9733.jpg"]` — `S#/products/157/photos`, `P#/57/photos`; *(key absent)* — `H#/products/56/photos` |
| `"photo-product-162"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/157/notes`, `P#/57/notes`; *(key absent)* — `H#/products/56/notes` |
| `"photo-product-163"` | `photo` | `"IMG_9733.jpg"` — `S#/products/158/photo`, `P#/58/photo`; *(key absent)* — `H#/products/57/photo` |
| `"photo-product-163"` | `photos` | `["IMG_9733.jpg"]` — `S#/products/158/photos`, `P#/58/photos`; *(key absent)* — `H#/products/57/photos` |
| `"photo-product-163"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/158/notes`, `P#/58/notes`; *(key absent)* — `H#/products/57/notes` |
| `"photo-product-164"` | `photo` | `"IMG_9733.jpg"` — `S#/products/159/photo`, `P#/59/photo`; *(key absent)* — `H#/products/58/photo` |
| `"photo-product-164"` | `photos` | `["IMG_9733.jpg"]` — `S#/products/159/photos`, `P#/59/photos`; *(key absent)* — `H#/products/58/photos` |
| `"photo-product-164"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/159/notes`, `P#/59/notes`; *(key absent)* — `H#/products/58/notes` |
| `"photo-product-165"` | `photo` | `"IMG_9733.jpg"` — `S#/products/160/photo`, `P#/60/photo`; *(key absent)* — `H#/products/59/photo` |
| `"photo-product-165"` | `photos` | `["IMG_9733.jpg"]` — `S#/products/160/photos`, `P#/60/photos`; *(key absent)* — `H#/products/59/photos` |
| `"photo-product-165"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/160/notes`, `P#/60/notes`; *(key absent)* — `H#/products/59/notes` |
| `"photo-product-166"` | `photo` | `"IMG_9733.jpg"` — `S#/products/161/photo`, `P#/61/photo`; *(key absent)* — `H#/products/60/photo` |
| `"photo-product-166"` | `photos` | `["IMG_9733.jpg"]` — `S#/products/161/photos`, `P#/61/photos`; *(key absent)* — `H#/products/60/photos` |
| `"photo-product-166"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/161/notes`, `P#/61/notes`; *(key absent)* — `H#/products/60/notes` |
| `"photo-product-167"` | `photo` | `"IMG_9730.jpg"` — `S#/products/162/photo`, `P#/62/photo`; *(key absent)* — `H#/products/61/photo` |
| `"photo-product-167"` | `photos` | `["IMG_9730.jpg"]` — `S#/products/162/photos`, `P#/62/photos`; *(key absent)* — `H#/products/61/photos` |
| `"photo-product-167"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/162/notes`, `P#/62/notes`; *(key absent)* — `H#/products/61/notes` |
| `"photo-product-168"` | `photo` | `"IMG_9734.jpg"` — `S#/products/163/photo`, `P#/63/photo`; *(key absent)* — `H#/products/62/photo` |
| `"photo-product-168"` | `photos` | `["IMG_9734.jpg"]` — `S#/products/163/photos`, `P#/63/photos`; *(key absent)* — `H#/products/62/photos` |
| `"photo-product-168"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/163/notes`, `P#/63/notes`; *(key absent)* — `H#/products/62/notes` |
| `"photo-product-169"` | `photo` | `"IMG_9734.jpg"` — `S#/products/164/photo`, `P#/64/photo`; *(key absent)* — `H#/products/63/photo` |
| `"photo-product-169"` | `photos` | `["IMG_9734.jpg"]` — `S#/products/164/photos`, `P#/64/photos`; *(key absent)* — `H#/products/63/photos` |
| `"photo-product-169"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/164/notes`, `P#/64/notes`; *(key absent)* — `H#/products/63/notes` |
| `"photo-product-170"` | `photo` | `"IMG_9734.jpg"` — `S#/products/165/photo`, `P#/65/photo`; *(key absent)* — `H#/products/64/photo` |
| `"photo-product-170"` | `photos` | `["IMG_9734.jpg"]` — `S#/products/165/photos`, `P#/65/photos`; *(key absent)* — `H#/products/64/photos` |
| `"photo-product-170"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/165/notes`, `P#/65/notes`; *(key absent)* — `H#/products/64/notes` |
| `"photo-product-171"` | `photo` | `"IMG_9738.jpg"` — `S#/products/166/photo`, `P#/66/photo`; *(key absent)* — `H#/products/147/photo` |
| `"photo-product-171"` | `photos` | `["IMG_9738.jpg"]` — `S#/products/166/photos`, `P#/66/photos`; *(key absent)* — `H#/products/147/photos` |
| `"photo-product-171"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/166/notes`, `P#/66/notes`; *(key absent)* — `H#/products/147/notes` |
| `"photo-product-172"` | `photo` | `"IMG_9738.jpg"` — `S#/products/167/photo`, `P#/67/photo`; *(key absent)* — `H#/products/148/photo` |
| `"photo-product-172"` | `photos` | `["IMG_9738.jpg"]` — `S#/products/167/photos`, `P#/67/photos`; *(key absent)* — `H#/products/148/photos` |
| `"photo-product-172"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/167/notes`, `P#/67/notes`; *(key absent)* — `H#/products/148/notes` |
| `"photo-product-173"` | `photo` | `"IMG_9738.jpg"` — `S#/products/168/photo`, `P#/68/photo`; *(key absent)* — `H#/products/149/photo` |
| `"photo-product-173"` | `photos` | `["IMG_9738.jpg"]` — `S#/products/168/photos`, `P#/68/photos`; *(key absent)* — `H#/products/149/photos` |
| `"photo-product-173"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/168/notes`, `P#/68/notes`; *(key absent)* — `H#/products/149/notes` |
| `"photo-product-174"` | `photo` | `"IMG_9738.jpg"` — `S#/products/169/photo`, `P#/69/photo`; *(key absent)* — `H#/products/150/photo` |
| `"photo-product-174"` | `photos` | `["IMG_9738.jpg"]` — `S#/products/169/photos`, `P#/69/photos`; *(key absent)* — `H#/products/150/photos` |
| `"photo-product-174"` | `notes` | `"Selling units, price and availability remain development assumptions."` — `S#/products/169/notes`, `P#/69/notes`; *(key absent)* — `H#/products/150/notes` |

## R3. Category words and readers

| File | Distinct literal `category` strings (food) | Other product collections |
|---|---|---|
| C | `bread`, `chilled`, `flowers`, `pantry`, `produce` | — |
| S | `bread`, `dairy`, `drinks`, `eggs`, `flowers`, `fruit`, `meat`, `pantry`, `vegetables` | `merch`, `boxes` |
| N | `fruit`, `vegetables` | — |
| P | `bread`, `dairy`, `pantry`, `vegetables` | — |
| H | `bread`, `dairy`, `drinks`, `eggs`, `flowers`, `fruit`, `meat`, `pantry`, `vegetables` | — |

- **Current catalog at `/`:** `storefront-mockup/index.html:32` (also `hass/templates/index.html:20`) loads `catalog-products.js` before `shop.js`. The generated `catalog` starts at `storefront-mockup/catalog-products.js:1`; `hass/content_model.py:127–128,154–175` and `hass/sitegen.py:197–209,363` trace it back to active H records only. `storefront-mockup/shop.js:2,11–24,88–89` uses those records for the display image, name, brand (including display overrides), product links and category filtering. Thus the visitor can find the Hass avocado under the `fruit` filter (H#/products/0/category), not C's `produce` (C#/0/category). Neither held H record reaches the generated array. Offline, parsing the checked-in array and comparing to active H by ID found the same 170 IDs and no ID, name, brand, category or display-image mismatches. That is not a deployment or image-rendering check.
- **No second current JSON-fed shop page:** `storefront-mockup/README.md:10–16` documents C and S as unloaded historical evidence. `storefront-mockup/optimize-images.cjs:2` shows the old S-to-`catalog.js` path; `storefront-mockup/catalog.js:1–3` defines the old catalog, merch and boxes rather than fetching JSON at page load. The current page does not include that script. The scoped reference search below found no current storefront HTML/JS load of N or P either. The archived commerce preview's HTML (`storefront-mockup/archive/commerce-preview/index.html:9`) is not a current entrypoint. The 11 merchandise/box records are not current catalog rows.
- **Hass new-product pipeline:** `hass/npp/stages.py:90–91,180,192–196` takes the comparison descriptions from active H rows; `hass/npp/validate.py:58–61` consumes that list. The design text at `hass/npp/assets/hass-listing-copy/copy-templates.json#/no_copying/compare_with` names S, but the code reads content, not S, for this comparison. The references checked do not show the historical differences feeding the current page or this NPP step.

## R4. Ranked gaps

1. **Easy to consult the wrong source.** C has two IDs that are absent from H (R1), and five input files do not represent five current readers. The NPP design text still names S for a comparison that runs on active H descriptions (R3). Treat this as a source-label mismatch, not a pipeline failure or a reason to add back either record.
2. **Historic listing and display drift.** R2 gives 64 category, 21 name, 15 brand and 93 display-image disagreements. For example C#/0/image refers to an extraction image while H#/products/0/image refers to the individual catalog asset. The checked-in active catalog agrees with H on the compared fields (R3), so aligning historical copies would not fix a demonstrated visitor bug.
3. **Historical photo and note fields are absent from H.** All 172 matched products have differences on `photo`, `photos` and `notes` (R2). Among the historical copies themselves, source photo names and lists agree wherever a product overlaps; five products have different stored note text. Keep the ancestry visible in the audit, not by copying old notes or filenames into current records. Held status stays a separate fact (R1).

**No build unit is needed on this evidence.** The current source-to-page comparison has no gap on the audited fields, and the traced NPP reader does not consume the disputed historical values. This report makes no data, content, pipeline or policy change.

### Reproduce the read-only checks

Run from the repository root with the audited base checked out. The first command shows record counts and per-file vocabularies in C, S, N, P, H order. The second gives one R2 example; use the R1 pointers to select another matched record, and compare the R2 keys literally, testing key presence separately from value. The last limits the reader search to current storefront/template HTML/JS, excluding the archived preview. These commands do not run any application or services.

```sh
jq -c 'if type=="object" then .products else . end | {count:length,categories:(map(.category)|unique)}' storefront-mockup/catalog.json storefront-mockup/shop-data.json storefront-mockup/new-products.json storefront-mockup/completion-new-products.json hass/content/products.json
jq -c 'if type=="object" then .products else . end | .[] | select(.id=="photo-product-001") | {id,name,brand,category,image,photo,photos,notes,hasNotes:has("notes"),hasPhoto:has("photo"),hasPhotos:has("photos")}' storefront-mockup/catalog.json storefront-mockup/shop-data.json hass/content/products.json
git grep -n -E '(src=.*(catalog|shop)\b|shop-data\.json|completion-new-products\.json|new-products\.json|catalog\.json)' 37feae1dc5efa6968f90d17a1eda6daed29afd4a -- 'storefront-mockup/*.html' 'storefront-mockup/*.js' 'hass/templates/*.html' ':!storefront-mockup/archive'
```
