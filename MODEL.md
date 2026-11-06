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
| labels | `pred_labels` | flags which targets `system_body` records in each system, with its boxel and position, built in 16 system-id buckets; a system counts as scanned only with a star row from a scan source |
| explored boxels | `pred_boxel_scan` | how much of each boxel is scanned |
| base rates | `pred_rate` | each target's rate per mass code and `plane_r` band, fitted on boxels at least 90% scanned (else 80%, else every scan) and outside the cross |
| cross | `pred_cross` | a suppression factor per distance band from the x = 0 and z = 0 planes |
| calibration | `pred_calibration` | found / expected on fully surveyed resolved predictions (Wolf-Rayet, O-type and supergiant to the system's own declared body count, the rest to the mass code's mean) per mass code and band, shrunk toward 1 by 20 pseudo-hits and capped at 1 |
| value | `pred_value` | expected bodies and full-scan value per mass code |
| pool | `pred_pool` | unscanned catalogued systems plus the boxel-predicted ones (`pred_boxel_gap`, `pred_boxel_first`) |
| sector budget | `pred_h_count`, `pred_h_type`, `pred_h_sector` | each sector's mass-h count, the chance it is Wolf-Rayet-rich, and the Wolf-Rayets and black holes it still owes |
| score | `system_predicted` | p = min(rate × cross × calibration, 1) × p_exist; a mass-h name in a known procedural sector takes its sector's budget instead |

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

## Mass-h Wolf-Rayet and black-hole rates belong to the sector, not the band (confidence B)

- Within 10 kly of Sgr A*, a mass-h system's chance of a Wolf-Rayet or black hole is set by its sector, so the per-band h rates in `pred_rate` are a mixture true of no sector.
- Check: 111,845 scanned mass-h systems within 10 kly of Sgr A* in 1,073 procedural sectors, a system counted as scanned on a body row from a scan source, measured 2026-11-05.
- **The rate is not uniform within a band.**
  Across the 423 sectors with at least 50 scanned mass-h systems, the per-sector counts scatter 31× (Wolf-Rayet) and 36× (black hole) the binomial spread of a shared rate per 2 kly band and grid layer.
- **One grid layer is a population of its own.**
  Sectors are 1,280 ly cubes, and the layer spanning y = −25 to +1,255 is Wolf-Rayet-rich and black-hole-poor; the step sits on the sector face, not on a gradient in height.

  | sector layer (y) | sectors | scanned systems | Wolf-Rayet | black hole |
  | --- | --- | --- | --- | --- |
  | −2,585 to −1,305 | 194 | 27,148 | 0.177 | 0.353 |
  | −1,305 to −25 | 212 | 32,374 | 0.161 | 0.369 |
  | −25 to +1,255 | 212 | 24,949 | 0.393 | 0.057 |
  | +1,255 to +2,535 | 195 | 26,729 | 0.156 | 0.389 |

  - In the 320 ly below y = −25 the shares are 0.155 and 0.379 (7,442 systems); in the 320 ly above y = 0 they are 0.404 and 0.057 (6,256 systems).
  - 102 of the 104 sectors in that layer with at least 50 scanned systems have a black-hole share below 0.15.
- **In the other layers each sector draws its own type.**
  A Wolf-Rayet sector holds about 0.39 Wolf-Rayets and 0.07 black holes per scanned system, a black-hole sector about 0.13 and 0.44, and the two shares correlate at −0.66 across the 426 sectors with at least 50 scanned systems.
  13–19 of about 105 sectors in each of the other layers have a Wolf-Rayet share above 0.3.
- **A neighbour says nothing about a sector's type once its layer is known.**
  Face-adjacent sectors in one layer share a type 72% of the time, and the layer's own mix gives 74% by chance; sectors 3–8 cells apart agree as often.
- **The type does not blend at a sector face.**
  Across faces where a Wolf-Rayet sector meets a black-hole sector, the Wolf-Rayet share stays 0.386–0.408 on one side and 0.125–0.135 on the other in every 160 ly slice from the face inward.
- **Sector totals hold within a type.**
  In the six sectors the mass-h plot experiment left at least 80% observed, all black-hole sectors, the band rate times the sector's numbers gives 517 Wolf-Rayets and 1,558 black holes against 517 and 1,559 estimated from scans, plots and the plotted rate for the rest.
  In the five Wolf-Rayet sectors it plotted, the band rate gives 1,501 black holes where about 126 are found or estimated.
- **A sector's remaining budget, not its rate, sets an unscanned name's chance.**
  Wolf-Rayets and black holes show on the galaxy map, so they are reported first: 300 random never-reported mass-h names held no Wolf-Rayet arrival star, while 14 of 60 catalogued unscanned names did.

## Mass-h systems per sector follow radius within each grid layer (confidence B)

- A sector's count of mass-h systems is its highest known h number plus one.
  A random galaxy-map probe of 48 sectors at every radius, outside the cross, found the next number in 8 and the number five above it in none, so the count is within 4 of the end everywhere the probe reached.
- Check: the 4,421 procedural sectors outside the cross with at least one known mass-h system, measured 2026-11-05 on the log of the count; a sector with no known mass-h system is not in the fit.
- **Distance to the core alone explains 18% of the spread**; disk radius together with the 1,280 ly grid layer explains 76%.

  | fit | residual variance of ln count |
  | --- | --- |
  | none | 4.32 |
  | 1 kly band of distance to Sgr A* | 3.52 |
  | 1 kly band of disk radius | 3.56 |
  | disk radius band × grid layer | 1.02 |
  | the same, plus the mean of the 8 same-layer neighbours' residuals | 0.51 |

- **The grid layer from y = −1,305 to −25 holds the mass-h population far out**, and the layers either side of it fall away fast; geometric-mean count per sector:

  | disk radius | −2,585 to −1,305 | −1,305 to −25 | −25 to +1,255 | +1,255 to +2,535 |
  | --- | --- | --- | --- | --- |
  | 4–6 kly | 390 | 254 | 242 | 339 |
  | 8–10 kly | 24 | 118 | 116 | 28 |
  | 12–14 kly | 3 | 60 | 17 | 3 |
  | 20–22 kly | 1 | 47 | 2 | 1 |
  | 30–32 kly | – | 25 | 1 | – |

- **What remains is a smooth regional field**: after radius and layer, the residuals of same-layer sectors correlate at 0.56 for neighbours, 0.47 two cells apart and 0.29 four to six apart, so a sector's neighbours predict its count, unlike its Wolf-Rayet or black-hole type.

## Mass-h names share their sector's remaining budget (confidence C)

- For a mass-h name in a procedural sector with a known mass-h system, p_wr and p_bh come from the sector, not from the band rate.
  - `pred_h_count`: the sector's count of mass-h systems and the Wolf-Rayets and black holes found in them, catalogue hits included.
  - `pred_h_type`: the Wolf-Rayet-rich and black-hole-rich types, their rates per system fitted on sectors scanned through, and the chance a sector is Wolf-Rayet-rich by layer and size band, before its own scans count.
  - `pred_h_sector`: the chance this sector is Wolf-Rayet-rich, its scanned shares weighing in at the power τ = 0.1, and what it still owes: count × the type's rate − found, never below 0.
  - `system_predicted`: what the sector owes is shared over its unscanned names, a catalogued name weighted α = 10 against a never-reported one, floored at ε = 0.2 × the sector's rate, times the cross factor and p_exist; the calibration factor does not apply.
- **Backtest**: each snapshot's mass-h predictions outside the cross, scored on the systems first scanned after it, with the model built only from what was known at the snapshot and τ, α, ε chosen by 2-fold cross-validation over sectors.

  | snapshot | resolved | Wolf-Rayet AUC, band rate → budget | black-hole AUC, band rate → budget |
  | --- | --- | --- | --- |
  | 2026-08-29 | 1,380 | 0.33 → 0.83 | 0.35 → 0.84 |
  | 2026-09-25 | 1,396 | 0.34 → 0.84 | 0.34 → 0.82 |
  | 2026-10-21 | 880 | 0.48 → 0.90 | 0.54 → 0.97 |

  - The resolved set is chosen by commanders: 59% of the names resolved after 2026-08-29 held a Wolf-Rayet, so ranking is the fair comparison and the absolute level is not.
- **Random plots**: on 360 random mass-h names plotted on the galaxy map, scored on the arrival star with the parameters fitted on the 2026-10-21 snapshot:

  | target | found | expected, band rate | expected, budget | AUC, band rate → budget |
  | --- | --- | --- | --- | --- |
  | Wolf-Rayet | 14 | 70.1 | 25.1 | 0.50 → 0.51 |
  | black hole | 25 | 183.4 | 36.3 | 0.52 → 0.69 |

- **Open: catalogued Wolf-Rayets beyond the budget.**
  All 14 Wolf-Rayets in the random plots were catalogued unscanned names, most in sectors whose budget looks spent (Juenoe: 5 found, 0.2 expected), so the budget does not yet rank Wolf-Rayets among random names.

## The Stellar Forge cross (confidence A)

- Rare objects are suppressed in two slabs straddling the x = 0 and z = 0 planes, a plus sign through Sol on a top-down map.
  - Players report it as a Stellar Forge suppression of black holes, neutron stars, white dwarfs, Wolf-Rayets, blue and large stars near the galaxy's axes, an 800 ly gap on EDAstro's star-type maps ([Scott Manley, 2019](https://x.com/DJSnM/status/1166234048919822336), [Stellar Forge wiki](https://elite-dangerous.fandom.com/wiki/Stellar_Forge)).
  - No source found gives its edges, so the edges below are this project's measurements.
  - The 800 ly gap is the core within about 400 ly of a plane, where black holes, neutrons and supergiants are near 0.
  - It is a slab, not an axis: at |x| < 300 the core is near 0 at every height, |y| < 300 through |y| > 1,500, and the Wolf-Rayet strip holds none at any height.
- Wolf-Rayets are absent in whole sector cells, not within a distance of the planes: sector columns 38–40 (x = −1,345 to +2,495) and rows 18–19 (z = −1,065 to +1,495), the macro `wr_cross`.
  - The cross is not centred on Sol: it reaches 2,495 ly on +x and only 1,065 ly on −z.
  - 0 of 3,882 scanned mass-h systems inside hold a Wolf-Rayet, 1,368 of them beyond 1,200 ly of either plane.
  - Outside, the share is about 19%, and it jumps to that within 20 ly of the x edges at −1,345 and +2,495.
  - The z edges rest on fewer systems: none of 81 scanned mass-h systems inside the z strip and outside the x strip holds one, where about 15 are expected.
  - Mass-h systems themselves are about 10× sparser inside the x strip.
  - Check: scanned mass-h systems with |z| > 2,500, in 20 ly bins of x across each edge, measured 2026-11-06.
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

- Every other target changes at the strip edges too, beyond the distance suppression near the planes.
  - Beyond 1,000 ly of a plane, black holes run 1.03–1.25× their rate outside the strips, while neutron stars run 0.82–0.99×, white dwarfs about 0.8–0.87× and supergiants about 0.7–0.87×.
  - Herbig Ae/Be runs 0.56–0.76× across the strips, stepping at x = −1,345.
  - O-types step down at x = −1,345, and on +x recover near 1,700 ly rather than at the edge.
  - Near the planes the suppression follows distance, not the grid: black holes, neutrons and supergiants are near 0 within about 350 ly of x = 0 and about half-rate out to about 900 ly.
  - Check: observed / expected per 160 ly bin of x for scanned e–h systems with |z| > 2,600, and of z for systems outside the x strip, measured 2026-11-06.
- `pred_cross` keys every factor by distance band and by `wr_cross`, so each target is measured separately inside and outside the strips; inside them a factor may exceed 1.
- Wolf-Rayet takes 0 in every cell inside `wr_cross` because none is observed there, not because it is assumed.
- A mass-h name priced from its sector's budget takes the factor capped at 1, since the sector's own count already carries the rise.
- `pred_rate` fits its base rates outside the slabs and outside `wr_cross`, so the effect is not counted twice.
- The cross is measured, not assumed, and is re-measured on every load.

## No procedural O-type supergiants (confidence B)

- The Stellar Forge does not generate O-type supergiants, so they are not a target and are not worth searching for.
- The journal has no O supergiant `StarType`: an O supergiant would be `StarType` `O` with a class-I `Luminosity`.
- Of 159,629 O stars with a procedural name, none has a class-I luminosity: 144,438 are Vz, 8,216 IVa, 6,966 IIIa and 9 have none.
- All 55 class-I O stars (53 `I`, 2 `Ib`) carry catalogue names in hand-placed space, such as Alnitak and Tau Canis Majoris.
  Hand-placed stars carry plain catalogue classes (`V`, `III`, `I`), copied from the real star rather than computed, and are physically small in game.
- The Forge does make supergiants of other letters: 16,660 A, 13,566 B, 7,895 F, 5,538 G and 2,906 M with procedural names.
- The largest procedural O stars are the IIIa giants.
- Check: `staging.spansh_galaxy_body`, the full Spansh galaxy dump, `sub_type = 'O (Blue-White) Star'`, procedural meaning a body name with an `AB-C d1` boxel, measured 2026-11-06.
  It holds only systems with body data, about 39% of them, so a very rare procedural case cannot be ruled out.

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
