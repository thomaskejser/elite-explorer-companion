# The prediction model

How `system_predicted` gives each unscanned system a chance of holding each rare star, and the measurements each step rests on.
`etl/system_predicted/load.py` runs the steps; the `schema/transform/pred_*.sql` files hold the SQL and `schema/system_predicted.sql` documents every column.

- Galaxy frame: Sol = (0,0,0); Sgr A* ≈ (25.2, −20.9, 25900); the galactic plane is y ≈ 0; `plane_r` is the galactocentric disk radius (Sol ≈ 25.9 kly, rim ≈ 50 kly).
- Confidence: **A** = hard fact, near-deterministic · **B** = validated, moderate uncertainty · **C** = directional, absolute values soft.
- Unless a section says otherwise, the measurements here were taken on the 2026-07-12 Spansh dump and the 2026-07-10 EDSM, EDAstro and Canonn data, and re-queried from `elite_mapping.duckdb` when written.
  Counts have grown with later deltas; re-derive an absolute count before quoting it.

## The steps

| step | transform | what it does |
| --- | --- | --- |
| labels | `pred_labels` | flags which targets `system_body` records in each system; a system counts as scanned only with a star row from a scan source |
| explored boxels | `pred_boxel_scan` | how much of each boxel is scanned |
| base rates | `pred_rate` | each target's rate per mass code and `plane_r` band, fitted on boxels at least 90% scanned (else 80%, else every scan) and outside the cross |
| cross | `pred_cross` | a suppression factor per distance band from the x = 0 and z = 0 planes |
| calibration | `pred_calibration` | found / expected on fully surveyed resolved predictions per mass code and band, shrunk toward 1 by 20 pseudo-hits and capped at 1 |
| value | `pred_value` | expected bodies and full-scan value per mass code |
| pool | `pred_pool` | unscanned catalogued systems plus the boxel-predicted ones (`pred_boxel_gap`, `pred_boxel_first`) |
| score | `system_predicted` | p = min(rate × cross × calibration, 1) × p_exist |

- Rates come from explored boxels because commanders pick systems by the star class the galaxy map shows, so a rate over every scan runs high for every target the map shows.
- Recalibration runs on every load, so each refresh corrects the model against every prediction resolved so far (`prediction_outcome`, `revealed_by = 'survey'`).
- `scripts/score_predictions.py` scores a pre-refresh snapshot against what the refresh revealed: the only out-of-sample test.

## Mass code gates star type (confidence A)

- The mass code is the letter `a`–`h` in a procedural name, readable without scanning.
- No black hole or Wolf-Rayet occurs below mass code e, and Wolf-Rayets occur only at h, so the pool holds only e/f/g/h systems.
- Check: rates across scanned systems.

| mass code | scanned systems | black-hole rate | Wolf-Rayet rate |
| --- | --- | --- | --- |
| a, b, c, d | 72,261,736 | **0.000%** (0 objects) | **0.000%** (0 objects) |
| e | 2,005,329 | 3.86% | 0% |
| f | 285,900 | 50.9% | 0% |
| g | 198,814 | 39.7% | 0% |
| h | 167,005 | 45.9% | 27.6% |

The other targets gate the same way:

| target | gate | peak | confidence |
| --- | --- | --- | --- |
| Supergiant | e+ | h: 7.9% | B |
| O-type star | f+ | g: 42.5% | B |
| White dwarf | d+ | f: 6.0% | C |
| Neutron star | d+ | e: 27% | partial |
| Herbig Ae/Be | e+ | g: 12.7% | B |

- Neutron stars and white dwarfs gate at d, and most live in d systems, which the pool leaves out: d's pool is enormous, and neutron stars are already mapped by the community neutron highway.
  Their p_* covers the e/f/g/h subset only.
- Rates are per band, not per boxel: a boxel's rate is noisy (±10–20 pp), so treat every p_* as a ranking.

## Rates fall with galactocentric radius, except Wolf-Rayet and Herbig (confidence B)

- Black-hole rates collapse with `plane_r`, while the Wolf-Rayet rate in h systems stays flat, which is why rates are fitted per band.
- Herbig Ae/Be is the only target whose rate rises with radius: 4.6% in e and about 18% in f/g beyond 30 kly.
- The fringe holds almost no h systems, so its Wolf-Rayet predictions are few even at a high rate.

| plane_r band | e: BH% | f: BH% | g: BH% | h: BH% | h: WR% |
| --- | --- | --- | --- | --- | --- |
| 0–10 kly | 5.92 | 58.18 | 45.88 | 49.13 | 25.60 |
| 10–20 kly | 2.78 | 43.33 | 39.10 | 36.61 | 33.95 |
| 20–30 kly | 0.45 | 4.69 | 11.69 | 26.36 | 32.51 |
| 30 kly+ | 0.29 | 3.19 | 9.02 | 26.06 | 30.85 |

## The Stellar Forge cross (confidence A)

- Rare objects are suppressed in two slabs straddling the x = 0 and z = 0 planes, a plus sign through Sol on a top-down map.
- Wolf-Rayets are absent within 1,200 ly of either plane at every mass code: 0 observed against 354 expected.
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

- `pred_cross` applies the factor per band, and `pred_rate` fits its base rates outside the slabs so the effect is not counted twice.
- The cross is measured, not assumed, and is re-measured on every load.

## Two candidate pools (`is_catalog`)

- **Catalogued** (`is_catalog` TRUE): real systems in the dumps with exact coordinates that nobody has detail-scanned.
  This is the reliable pool.
- **Boxel-predicted** (`is_catalog` FALSE): systems in no dump, inferred from internal gaps in a boxel's index sequence or guessed as the first system of a sector's h or g boxel, at boxel-centroid coordinates (±≤1280 ly).
  - Gaps are enumerated only in boxels at least 50% observed, which skew hard toward explored space: 93% of gap systems sit inside 20 kly galactocentric.
    The layer is thin and core-biased, so it is no basis for fringe estimates.
  - Gaps lie only between known indices of a boxel; index 0 is guessed only by `pred_boxel_first`, weighted by `p_exist`.
- **Both pools are floors.**
  A boxel nobody has visited holds neither records nor enumerable gaps, and enumerating it needs a name-to-coordinate generator the repo does not have.
- Never average a probability across the pools without also grouping by mass code, and for e by radius band as well (`schema/system_predicted.sql`).

## Scan value

- `exp_scan_value_cr` is the mean base value of scanned systems of the same mass code, divided by scan completeness.
- **Stratify by mass code, never use a global mean per system.**
  Value per system varies 25× across mass codes, and the unscanned remainder has a poorer mix than the scanned set, which over-represents big bright systems.

| mass code | Cr/system |
| --- | --- |
| a | 4,418 |
| b | 23,053 |
| c | 60,794 |
| d | 111,585 |
| e | 68,581 |
| f / g / h | ~55,000 |

- **Distance from Sol is nearly neutral** (index 0.84–1.15 from the bubble to past 30 kly), so value is not banded by distance and `dist_sol` is no predictor.
- **Scanned systems are only 77.1% scanned**: across the 27.9M systems whose sources report a body count, we hold 77.1% of the bodies, so `pred_value` divides by the measured completeness to reach a full scan.
- **Base value only.**
  First discovery pays ×2.6 and first mapping takes planets to ×9.62, but no source we hold has a DSS or mapped flag; only the commander's journals record it.
  Value is realised only on sale to Universal Cartographics.
- Planets carry 94.4% of scanned value, and High Metal Content worlds alone 57.0%, so the mass code's planet mix is what moves the value.

## Rules a change to the model keeps

- **Negatives come only from thoroughly scanned systems.**
  An unvisited or partly scanned system is unknown, never a negative, which is why rates are fitted on explored boxels.
- **No feature may carry the target.**
  A codex entry, signal text or anything reported after the discovery leaks the answer into the prediction.
- **Score only on what was revealed after the prediction.**
  `staging.pred_snapshot_*` and `prediction_outcome` freeze the prediction before the refresh that resolves it.
- **Hold out by space, not at random.**
  Exploration follows routes, so a random split scores the model on neighbours of its own training systems and overstates it.
- **Never invent body facts for a boxel-predicted system.**
  Such a row is a guess that the system exists (`p_exist`), at boxel-centroid coordinates, and carries only the rates of its cell.

## Caveats

- **A has_* of 0 is "not reported", not "absent".**
  Every rate over reported bodies is a lower bound.
- **The resolved set is not random**: commanders scan what already looks interesting, so calibration only ever lowers a rate.
- **No Live/Legacy split** exists in the dumps (`galaxy_version` = unknown).
- A target is confirmed only by an in-game scan; every row is a ranked hypothesis, never a claimed discovery.
- A route plot names a supergiant by its letter only, so the overlay confirms one only as probable (`overlay/DESIGN.md`, supergiants).
