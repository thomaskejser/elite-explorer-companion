# Exploration recommendations

The register of vetted, actionable findings from the prediction work.
Each entry carries a confidence grade and the check behind it, and every number was re-queried from the model database (`elite_mapping.duckdb`) when written, never transcribed from chat output.

- Data snapshot: EDSM/EDAstro/Canonn 2026-07-10; Spansh galaxy dump 2026-07-12.
- Every count in R1–R8 is that snapshot and has not been recomputed since.
  The model has grown with later deltas (verified 2026-09-04): `system_known` 197.6M → 200,676,922, the catalogued unscanned pool 2,255,468 → 2,253,534, the boxel-gap layer 207,776 → 220,489.
  Rankings are the durable part; re-derive an absolute count before quoting it.
- Galaxy frame: Sol = (0,0,0); Sgr A* ≈ (25.2, −20.9, 25900); galactic plane = y≈0; `plane_r` = galactocentric disk radius (Sol ≈ 25.9 kly, rim ≈ 50 kly).
- Confidence: **A** = hard fact, near-deterministic · **B** = validated, moderate uncertainty · **C** = directional/ranking only, absolute values soft.
- R2–R5 were recomputed 2026-08-02 over the real in-db-unscanned pool (~2.26M catalogued systems with exact coordinates that nobody has detail-scanned), per sector.
  The boxel-gap layer enumerates only internal gaps (207,776); filling a boxel's index range from 0 instead inflates it to 1,069,699,995.
  The gap layer is thin and core-biased, so it is not a basis for fringe estimates.
- R1 and the de-biased rate model rest on real scanned systems and are unaffected by the gap layer.

## R1 — Star type is gated by procedural mass code (confidence A)

- Scan for black holes only in mass code **e/f/g/h** systems and for Wolf-Rayets only in **h**.
- The mass code is the letter `a`–`h` in a procedural name, readable without scanning.
- Filtering a target list by mass code first eliminates ~99% of systems with zero false negatives; it is the most reliable rule in the analysis.
- Check: rates across scanned systems.

| mass code | scanned systems | black-hole rate | Wolf-Rayet rate |
| --- | --- | --- | --- |
| a, b, c, d | 72,261,736 | **0.000%** (0 objects) | **0.000%** (0 objects) |
| e | 2,005,329 | 3.86% | 0% |
| f | 285,900 | 50.9% | 0% |
| g | 198,814 | 39.7% | 0% |
| h | 167,005 | 45.9% | 27.6% |

## R2 — Outside the core, Herbig Ae/Be and black holes dominate; Wolf-Rayets do not (confidence B)

- For rim-ward trips, Herbig Ae/Be is the richest undiscovered target by an order of magnitude, and the only one whose rate rises with radius.
- Do not plan a fringe trip around Wolf-Rayets: the fringe has almost no h systems.
- Per system, an unscanned h system is still the best single target anywhere (26% BH + 31% WR); they are just almost absent out there.
- A ranking with Wolf-Rayets ahead (~2,630 vs ~630 black holes) comes only from fabricated mass-code-h boxel-gap systems and is retracted.

Black-hole rate collapses with galactocentric radius while the Wolf-Rayet rate in h systems stays flat (scanned systems):

| plane_r band | e: BH% | f: BH% | g: BH% | h: BH% | h: WR% |
| --- | --- | --- | --- | --- | --- |
| 0–10 kly | 5.92 | 58.18 | 45.88 | 49.13 | 25.60 |
| 10–20 kly | 2.78 | 43.33 | 39.10 | 36.61 | 33.95 |
| 20–30 kly | 0.45 | 4.69 | 11.69 | 26.36 | 32.51 |
| 30 kly+ | 0.29 | 3.19 | 9.02 | 26.06 | 30.85 |

- Real unscanned records beyond 30 kly by mass code: e 67,434, f 1,245, g 855, h 35.
- A 31% WR rate on 35 systems is ~11 finds; a 0.29% BH rate on 67,434 systems is ~196, plus ~120 more from f/g.

De-biased expected undiscovered beyond 30 kly, over the real unscanned pool (71,155 systems):

| target | expected | why |
| --- | --- | --- |
| **Herbig Ae/Be** | **~2,982** | rate rises with radius (4.6% in e, ~18% in f/g) |
| Black hole | ~319 | low rate, very large e pool |
| O-type | ~369 | 51% of fringe g systems, but only 855 of them |
| Supergiant | ~149 | — |
| Wolf-Rayet | **~14** | high rate, but only 35 candidate systems exist |

## R3 — Best sectors near Sol (confidence B for ranking, C for counts)

- The ~3.5–5 kly band gives the best balance of travel time and unexplored pool; **Bleae Thaa**, **Drojeae** and **Traikoa** are the strongest.
- Every one of these is a black-hole trip.
- Ranked over the real in-db-unscanned pool: the closest sectors with expected BH+WR ≥ 3 and ≥ 100 unscanned systems.
- `unscanned` = real catalogued systems nobody has detail-scanned (exact coordinates); `gap layer` = additionally enumerable internal-gap systems (boxel-centroid coordinates only).

| sector | dist from Sol (ly) | unscanned | gap layer | found BH | exp BH | exp WR | coords (x,y,z) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Prae Drye | 3,462 | 560 | 330 | 0 | 3.8 | 0.0 | (−3261, −588, 855) |
| Pru Eurk | 3,463 | 711 | 486 | 1 | 3.1 | 0.0 | (−3276, 531, 845) |
| Smojue | 3,559 | 755 | 217 | 0 | 4.1 | 0.0 | (−729, 564, 3399) |
| Aucofs | 3,955 | 628 | 396 | 5 | 4.2 | 0.0 | (−3253, −592, 2105) |
| **Bleae Thaa** | 3,968 | 883 | 596 | 2 | **7.4** | 0.0 | (−3282, 519, 2110) |
| Byeia Thaa | 4,011 | 1,060 | 511 | 1 | 6.9 | 0.0 | (−1983, 527, 3409) |
| **Drojeae** | 4,031 | 967 | 425 | 12 | **7.4** | 0.0 | (−1984, −648, 3410) |
| Sifou | 4,651 | 353 | 154 | 1 | 3.8 | 0.0 | (−4521, 506, 834) |
| Smojoo | 4,776 | 709 | 347 | 3 | 7.2 | 0.0 | (−3271, 517, 3400) |
| **Traikoa** | 5,149 | 1,512 | 879 | 8 | **7.8** | 0.0 | (−1988, 547, 4690) |

Wolf-Rayets are not a near-Sol target:

- There are zero unscanned mass-code-h systems within 5,000 ly of Sol (all 58 known h systems inside that radius are scanned), and only 37 between 5–10 kly.
- The nearest sector holding any unscanned h system is Thailoea at 6,639 ly (one system).
- A real WR pool appears only past ~10 kly (e.g. Ellaisms 11.4 kly, exp 15.8; Xeehia 12.1 kly, exp 11.9; Skaude 10.8 kly, exp 8.9).
- 7–17 expected WR per near-Sol sector is a gap-layer artifact.

## R4 — Best deep-fringe sectors (confidence C, ranking only)

- **Best all-round: Eafots and Gludgoea/Gludgoe** — top-3 for Herbig, black holes and neutron stars at once.
  They sit within 5–8 kly of Sol despite being past 30 kly galactocentric: rim-ward of Sol's own arm, not across the galaxy.
- Ranked for `plane_r` > 30 kly over the real unscanned pool; use the ordering, not the numbers.

| target | sectors (expected) |
| --- | --- |
| **Herbig Ae/Be** (the reason to go) | Eafots (20.3, 495 unscanned), Gludgoea (15.5), Gludgoe (15.0), Hypiae Aihm (12.1), Gludgoi (11.6), Hypuae Aim (11.3) |
| Black holes | Eafots (3.3), Gludgoe (2.9), Hypheerld (2.6), Phroi Hypue (2.6), Phaa Ain (2.6), Gludgoea (2.6) |
| Supergiants | Hypiae Aihm (2.5), Pheia Aihm (2.4), Phua Aihm (2.2) |
| O-type | Pyrivai (8.2), Proo Graae (6.0), Drootue (4.1) — all ~55 kly from Sol, on the far side of the core |
| Wolf-Rayets | best fringe sector is ~0.5 expected; not worth routing for |

## R5 — Rare stellar exotics: neutron, white dwarf, Herbig Ae/Be, O-type, supergiant

- Each is name-predictable by the same method as BH/WR: mass-code gate → local de-biased rate → sector ranking.
- Standout nearby target: **Swoilz / Swoiwns / Praea Euq** (~1.3–1.5 kly) for Herbig Ae/Be.
  Col 359 Sector ranks below them but remains the best cluster destination, ranking for several targets at once.
- Check: gating among scanned systems, and validation of local vs baseline rate:

| target | gate | peak | validation (local vs baseline) | coverage |
| --- | --- | --- | --- | --- |
| **Supergiant** † | e+ | h: 7.9% | **2.4×** (best) | full — confidence **B** |
| **O-type star** | f+ | g: 42.5% | 1.8× | full (0 below f) — confidence **B** |
| **White dwarf** | d+ | f: 6.0% | 1.4× | partial; rare/uniform — confidence **C** |
| **Neutron star** | d+ | e: 27% | 1.4× | **partial** — e/f/g/h only (see below) |
| **Herbig Ae/Be** | e+ | g: 12.7% | 1.1× | full — confidence **B** (strong spatial pattern) |

- † Supergiant is not on the overlay.
  The rate is the best-fitting of the seven, but the journal's `StarClass` names a supergiant by its base letter only, so a route plot can never confirm one; predict offline and do not expect the HUD to score it (see `DEAD_ENDS.md`).
- Neutron stars and white dwarfs gate at mass code d, and most of them live in d systems, which are not modelled here: d's pool is enormous, and neutron stars are already well mapped via the community neutron highway.
  The sectors below are the e/f/g/h subset only.
- Galaxy-wide expected undiscovered over the 2.26M-system unscanned pool: neutron ~236,000 · Herbig ~84,000 · black hole ~74,000 · O-type ~21,000 · white dwarf ~11,500 · Wolf-Rayet ~5,200 · supergiant ~5,100.

Best sectors (distance from Sol, expected count):

| target | near Sol | fringe / far side |
| --- | --- | --- |
| **Herbig Ae/Be** (B) — young stars, clustered in nebulae and young clusters | **`Swoilz`** (1.35 kly, 11.1), **`Swoiwns`** (1.45 kly, 11.1), `Praea Euq` (1.32 kly, 10.4), **`Col 359 Sector`** (0.93 kly, 4.4), `Col 173 Sector` (1.41 kly, 4.1), `Synuefai` (1.24 kly, 3.5), `Wregoe` (1.15 kly, 3.2) | `Eafots` (20.3), `Gludgoea` (15.5), `Gludgoe` (15.0) |
| **O-type** (B) | `Smojue` (3.6 kly, 5.2), `Traikaae` (4.8 kly, 3.8), `Traikoa` (5.1 kly, 3.5), `Bleae Eurk` (5.7 kly, 3.4), `Thailoi` (5.8 kly, 3.4) | `Pyrivai` (8.2), `Proo Graae` (6.0) |
| **Supergiant** (B, low counts) | `Pro Eurl` (2.16 kly, 2.3), `Prua Dryoae` (2.18 kly, 2.6), `Synuefue` (2.18 kly, 2.5), `Blaa Eork` (2.88 kly, 2.5), `Aucopp` (3.0 kly, 2.6) | `Hypiae Aihm` (2.5), `Pheia Aihm` (2.4) |
| **Neutron** (e/f/g/h subset) | `Sifi` (2.30 kly, 2.0), `Prooe Drye` (2.31 kly, 2.0), `Bleae Thua` (2.36 kly, 2.1), `Bleia Eohn` (2.39 kly, 2.0), `Phylur` (2.99 kly, 2.7) | `Gludgoe` (2.8), `Gludgoea` (2.7), `Eafots` (2.5) |
| **White dwarf** (e/f/g/h subset, C) — low everywhere, nothing worthwhile near Sol | — | all 10–13 kly out: `Skaude` (16.4), `Flyae Eaec` (8.3), `Ellaidst` (7.2), `Prua Phoe` (4.8), `Preia Phoe` (4.4) |

## R6 — Black holes along the Reorte→Riedquat corridor (re-verified 2026-08-02)

- The corridor has undiscovered black holes (~40), but spread thinly across many low-odds e systems: not a rich or concentrated target.
- Confidence **B** that undiscovered black holes exist and are findable here (119 are already confirmed and completeness is low); **C** on the absolute count.
- The corridor is the Raxxla "clue line" (Reorte→Riedquat, extended outward toward the Formidine Rift; direction (−0.787, 0, −0.616)), taken 2,000 ly wide.
- Found: 119 confirmed black holes (e/f/g/h systems); 49,312 systems in-db, 33,797 scanned.
- Expected still-undiscovered: ~40 from the real unscanned pool, plus ~3 from the 35 enumerable boxel-gap systems → ~43.
- The corridor points away from the core, so it is BH-poor: found-rates e 0.19%, f 2.03%, g 6.38%, h 29.3%.
  The estimate is dominated by the numerous real unscanned e systems (15,165 × 0.19% ≈ 29), plus f (278 × 2.03% ≈ 6) and g (72 × 6.38% ≈ 5).
- There are 0 unscanned h systems in the corridor (all 41 are scanned).
- There is no h-boxel target ladder here: the "~40–56 unscanned h" boxels (Prooe Drye, Flyae Drye, Slegoae …) are a gap-enumeration artifact, retracted 2026-07-14.

## R7 — What is left to scan is worth ~2× everything found so far (confidence B for the catalogued pool, C for the galaxy)

- At first-discovery rates (×2.6) the unscanned catalogue is ≈22.3 Tn Cr, roughly twice the ~12 Tn the entire playerbase has earned discovering everything found to date.
- Value is overwhelmingly planetary: planets are 94.4% of it, and High Metal Content worlds alone are 57.0% (2.63 Tn), being numerous and carrying the terraformable bonus k (110,331 vs 9,654) on the ~8.5M that rolled terraformable.
- Check: computed 2026-08-16 from `system_body` + `body` alone; cross-checked against an independent `spansh_body` computation at 4.610 Tn vs 4.609 Tn (0.03%, the EDSM/EDAstro slice bodies `system_body` carries and Spansh lacks).
- All figures are base value with no multiplier: k from `body.cr_value` / `body.cr_value_terraformable`, mass from `system_body.solar_masses` / `earth_masses`, `is_terraformable` selecting the k.

| population | systems | base value |
| --- | --- | --- |
| **scanned** (have body data) | 74,990,817 | **4.610 Tn Cr** |
| **catalogued but unscanned** | 122,569,859 | **8.57 Tn Cr** (completeness-corrected) |

### Never extrapolate the global mean per system

- Post-stratify by mass code: the global mean (61,478 Cr/system) overstates the remainder by 14.1%.
- Value per system varies 25× across mass code, and the unscanned remainder has a poorer mix than the scanned set, which over-represents big bright systems.
- This is the calibration rule (never fit rates on scanned systems) reached from a different direction: mass code gates value just as it gates star type in R1.

| mass code | scanned | unscanned | % of unscanned | Cr/system |
| --- | --- | --- | --- | --- |
| a | 3,051,145 | 8,310,726 | 6.8% | **4,418** |
| b | 24,659,755 | 48,032,769 | **39.2%** | 23,053 |
| c | 22,213,518 | 35,865,343 | 29.3% | 60,794 |
| d | 22,265,206 | 27,976,581 | 22.8% | **111,585** |
| e | 2,003,593 | 2,102,975 | 1.7% | 68,581 |
| f / g / h | 651,100 | 278,241 | 0.2% | ~55,000 |

- Distance from Sol is nearly neutral; do not correct for it.
  Index 0.84–1.15 from the bubble to past 30 kly (0–500 ly: 61,065 Cr/sys; 20–30 kly: 70,716; 30 kly+: 61,916).

### Scanned systems are only 77% scanned

- Every per-system figure from our data understates a full scan by 1.30×, and the unscanned estimate applies that correction (6.61 Tn as-held → 8.57 Tn completed).
- Check: across the 27,898,532 systems whose true `body_count` the sources report, we hold 250,269,237 of 324,654,751 bodies = 77.1%.

### Whole galaxy (confidence C, order of magnitude only)

- Use ~23 Qn; treat the high row below as an upper bound, not an alternative estimate.
- We hold 197,560,676 systems, 0.0494% of Frontier's stated ~400 billion.
- Two unverifiable inputs dominate: the 400B figure itself, and the remainder's mass-code mix, a 3× swing.
- The galaxy is dominated by M dwarfs and brown dwarfs (mass codes a and b), and our catalogue is only 5.7% mass code a, so the low row is much closer to the truth.

| assumed mix of the remainder | Cr/system | base | at ×2.6 |
| --- | --- | --- | --- |
| our catalogue's mix | 53,902 | 27.95 Qn | 72.7 Qn |
| 90% mass code a/b | 17,170 | 8.90 Qn | **23.1 Qn** |

### What these numbers are not

- **No mapping.** First-mapped takes planets to ×9.62 rather than ×2.6, roughly tripling every figure here.
  It is excluded because no source we hold has a DSS/mapped flag or discovery attribution; only the commander's journals record it (`WasDiscovered` / `WasMapped` on `Scan` events).
- **Not realised credits.** Value is paid only on sale to Universal Cartographics, and nothing in our data distinguishes data uploaded from a journal but never sold.
- **232,433 bodies (0.04%) are unvalued** because their `sub_type` matches no `body` row, and 27,744 stars are valued at mass 0; both are rounding errors at this scale.

## R8 — The Stellar Forge "cross": two slabs with no Wolf-Rayets at all (confidence A)

- Do not fly a Wolf-Rayet hunt within 1,200 ly of the x = 0 or z = 0 plane at any mass code: 0 observed against 354 expected, the widest gate of any object.
- Rare objects are suppressed near both planes, which read as a giant plus sign through Sol on a top-down map.
- Black holes are not zero there, only ~1,000× rarer: 7 within 100 ly of a plane where 3,144 were expected.
- Check: 2.86M scanned e/f/g/h systems measured by `least(|x|, |z|)` against rates fitted outside the slabs.

| distance to nearer plane | BH | WR | neutron | white dwarf | O-type | supergiant |
| --- | --- | --- | --- | --- | --- | --- |
| 0–100 ly | 0.001× | **0×** | **0×** | 0.005× | 0.054× | **0×** |
| 100–200 | 0.006× | **0×** | **0×** | 0.013× | 0.126× | 0.002× |
| 200–400 | 0.031× | **0×** | 0.023× | 0.014× | 0.157× | 0.017× |
| 400–600 | 0.262× | **0×** | 0.230× | 0.008× | 0.690× | 0.312× |
| 600–800 | 0.557× | **0×** | 0.363× | 0.221× | 0.664× | 0.375× |
| 800–1200 | 0.81–0.95× | **0×** | 0.75–0.92× | 0.69–0.90× | ~0.60× | 0.45–0.69× |
| 2000+ | 1.00× | 1.00× | 1.00× | 1.00× | 1.00× | 1.00× |

- `etl/system_predicted/load.py` applies it as a factor per band from `transform.pred_cross` (`schema/transform/pred_cross.sql`), with base rates fitted outside the slabs so the effect is not subtracted twice.
- 397,778 of 2,474,023 pooled systems have `p_wr` forced to zero; `Gria Hypue` and `Eorld Bloo` are mass-code-h sectors that would otherwise read `p_wr = 0.139`.
- The community traces the cross to a check meant to keep exotica out of the starting bubble that shipped with the wrong bounds; routing depends only on the measurement.

## Method, confidence and caveats

- **Two candidate layers, very different reliability:**
  - **In-db-unscanned (2,255,468 systems; e 2,015,262 / f 175,510 / g 44,586 / h 20,110)** — real catalogued records with exact coordinates, not detail-scanned.
    This is the reliable pool and the basis for every count in R2–R6.
  - **Boxel-gap layer (207,776)** — internal index gaps in densely observed boxels (≥50% of the min..max range observed); likely real but unconfirmed, with boxel-centre coordinates (±≤1280 ly).
    Only 117,356 of 981,286 boxels are dense enough to enumerate, and those skew hard toward explored/core space: 93% of gap-layer systems sit inside 20 kly galactocentric, and only 481 f/g/h systems (zero h) survive past 30 kly.
    The gap layer cannot support fringe estimates.
- **De-biasing:** scanned systems over-represent rare stars because explorers preferentially scan the bright massive primary.
  The true Forge rate is estimated from fully-sampled boxels (≥10 scanned, ≥80% covered) and applied locally (k-nearest fully-sampled boxels).
  A radius-only curve is rejected: it fails a spatial hold-out, because density has directional/arm structure.
- **Validation:** random 20% hold-out of fully-sampled boxels.
  Local de-biased BH rate MAE 22.1 pp vs 28.5 pp for a global-mean baseline (1.3× better); WR 11.1 vs 12.0 pp (1.1×, rate is spatially uniform); supergiant 2.4×, O-type 1.8×, white dwarf 1.4×, neutron 1.4×, Herbig 1.1×.
  Boxel-level rates remain noisy (±10–20 pp), so rank the sectors and do not trust the decimals; reliability is highest near Sol and lowest at the deep fringe.
- **Both layers are floors.** Entirely unvisited boxels contain neither real records nor enumerable gaps, so true undiscovered totals are higher.
  Enumerating those needs a full name→coordinate generator, which the repo does not have; the boxel-gap enumeration reaches only the 12,064 sectors that already have uploaded systems.
- **Coordinates are boxel/sector centroids** (±≤1280 ly): good for routing, not for pinpointing a system.
  Individual unscanned systems have exact coordinates, carried on `system_predicted` where `is_catalog`.
- **No Live/Legacy split** in the underlying dumps (`galaxy_version` = unknown).
- Objects are confirmed only by an in-game scan; everything here is a ranked hypothesis with a verification route, never a claimed discovery.

## Provenance

Every number here was computed over the full-galaxy spine (194.7M systems, 569.7M bodies, Spansh dump of 2026-07-12) plus the per-system rare-star labels derived from it.
To re-derive one, the equivalents in `elite_mapping.duckdb` are:

| what the number was computed over | where it is now |
| --- | --- |
| system spine, coordinates, mass code | `system_known` (200.7M rows today) |
| per-system rare-star flags | `system_body` JOIN `body` |
| the real unscanned candidate pool | `system_predicted` WHERE `is_catalog` |
| the boxel-gap layer | `system_predicted` WHERE NOT `is_catalog` |
| per-sector rollups | `sector`, plus a GROUP BY over the above |

Sector rankings are per-sector aggregates of that pool with the kNN de-biasing step above, measured by `scripts/refine_rare_rates.py`.
