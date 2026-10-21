# Dead ends / negative results

Investigations that did not yield a usable prediction, with the reason and what could revisit them, so the work is not repeated.
Facts were verified against the model database when written.

## Green Gas Giants (GGGs) — no reliable predictor (2026-07-13)

**Status:** parked; not in `RECOMMENDATIONS.md`, as there is no vetted pattern to stand behind.

- **Target:** predict where undiscovered Green Gas Giants are.
- **What they are:** gas giants that render bright green ("radioplankton" in lore).
  Technically a colour-selection bug: green is the default before the calculation runs, and some value in the gas giant's characteristics pushes the colour picker out of range so it stays green.
  Deterministic, but driven by an internal generation value, and extremely rare (~1 per 2M systems discovered).
- **Positive set:** GGGs are codex-labelled — EDSM `codex_ent_green_sudarsky_class_i/ii/iii`, `green_giant_with_water_life`, `green_water_giant`; Canonn "Green Class I/II/III/IV Gas Giant", "Green Gas Giant with Ammonia Life".
  That gives 67 distinct known systems (codex + the 60 EDAstro POIs, largely overlapping).
  `codex_ent_gas_clds_green` is green clouds, a different NSP with ~1,020 systems; do not confuse it with green giants.
- **Co-occurrences:** K10-Type Anomaly (8/60 systems), green NSP clouds, silicate/sulphur geology.

Why it is dead (three independent reasons):

1. **No spatial pattern.** The 67 systems are scattered galaxy-wide: galactocentric radius 604 → 41,247 ly, Sol-distance 300 → 56,707 ly, with only a faint near-core hint (the Byoomao systems).
2. **No strong property pattern in what we hold.** Only mild subtype enrichment (Class IV ~1.5×, water-based-life ~1.4×), diluted because a green system holds several gas giants of which only one is green.
3. **The likely trigger, atmosphere composition, is not in the full corpus.** `spansh_body` drops composition, and of the 67 green giants only 1 appears in the 7-day tables that carry it.
   The bug may also key off an internal per-body value not exposed in public dumps at all.

- The community, with dedicated effort, has found no predictive pattern either: discovery is "largely a matter of luck."
- Method: ad-hoc queries (GGG codex + POI join, spatial map, composition feasibility check).

**What could revisit it** (a research gamble, not a likely win): re-extract atmosphere + solid composition for gas giants from the raw Spansh dump (`raw/spansh_galaxy.json.gz`), then test whether a composition signature separates the 67 green giants from the ~48M normal ones (ML on a tiny positive set).
~1–2 h compute; if the colour bug keys off an internal value absent from the dumps, no composition data will predict it.

## Planet classes are not boxel-predictable (2026-08-10)

**Status:** closed.

- **Target:** point the boxel lever — the strongest predictor this project has — at valuable planet classes: Earth-likes, ammonia worlds, water worlds and exobiology.
- **Why it looked promising:** R1 gates star types by mass code, and the BH/WR and neutron work found a boxel's own rate beats any global rate by a wide margin; rare stars show 3–13× binomial overdispersion per boxel.
- **Why it is dead:** mass code and boxel decide which stars a system gets; planets are rolled essentially per system.
  Conditioning on arrival star class collapses what little spread there is (ELW 1.4× → 1.1–1.4×), so the boxel adds no information independent of the star.
  There is no rich-boxel tail to route to: the top 1% of boxels reach only 7.7% for ELW, against 45.1% for helium-rich gas giants in the same test.
- **Check:** denominator = 22,004,981 fully-scanned systems (`spansh_system.scanned_body_count >= declared_body_count`, both > 0), since in a partly-scanned system "no ELW" only means nobody looked.
  Overdispersion = observed spread of per-boxel rates ÷ the binomial spread of independent rolls, over boxels with ≥25 fully-scanned systems.

| target | galactic rate | boxel ratio | within one arrival-star class |
| --- | --- | --- | --- |
| Water world | 7.659% | 1.9× | 1.2–1.6× |
| Gas giant w/ water-based life | 6.601% | 2.2× | — |
| Earth-like world | 0.743% | **1.4×** | 1.1–1.4× |
| Ammonia world | 1.211% | **1.3×** | 1.1–1.3× |
| Exobiology (a body with ≥3 bio signals) | 6.28% | 2.2× | — |

- **Honk-time ELW detection is also dead.** `FSSDiscoveryScan` carries only `BodyCount`, `NonBodyCount`, `Progress`, `SystemName`, `SystemAddress` — nothing per body, verified over 2,128 honks.
  Of 27 ELW finds in the journals, zero were revealed at the honk timestamp.
  Predicting from what the honk does give (arrival star class × body count) spans 0.003% → 3.65%: real triage, but the best cell is still 96% disappointment.
- Two fragments worth keeping, both closer to `RECOMMENDATIONS.md` territory:
  - `BodyCount ≤ 2` is a clean zero for ELW (134 hits in 5.8M systems).
  - ELW arrival distance is tightly bound by arrival star class (K: 285–504 Ls, only 5.4% of all planets), which orders FSS tuning though it cannot predict presence.
- **Helium-rich gas giants** (5.4× with a hard radial gate) are the one exception in the same sweep, and are out of the pipeline and the overlay for the same reason one step further along.
  The signal is real, but a gas giant is a planet, and nothing this project observes of an unvisited system reports anything but its arrival star, so `p_hr` could never be confirmed, scored or acted on.
  The fit, both gates and the constants are in the git history of `etl/system_predicted/build.py` if a body-level observation channel ever appears.
- Method: ad-hoc queries (per-class boxel overdispersion, honk timeline over 154 journals, ELW arrival-distance bands).

**What could revisit it:** nothing in this data.
A per-system planet model would need generator inputs we do not hold, and the boxel-level aggregates that exist (`edastro_boxel_stats`) describe stars and gas-giant composition, not terrestrials.

## Supergiants — predictable, not confirmable (2026-09-06)

**Status:** closed. `p_supergiant` and the `SUPERGNT` kind are not on the overlay (`overlay/src/kinds.rs`, `overlay/src/theme.rs` and the SQL generated from them).
The column in `main.system_predicted` stays: the schema is master data, the fit is sound, and the model is the right place for a number the display cannot act on.

- **Target:** rank sectors by where an undiscovered supergiant arrival star is.
- **Why it is dead:** the overlay can never learn that it was right.
- **The prediction is the best in the project:** fitted per (mass code, plane_r band) like the rest, it validates at 2.4× observed over expected, the highest of the seven (confidence B, `RECOMMENDATIONS.md` R5).
  It gates at mass code e and rises steeply: median `p_supergiant` is 0.0962 at `h` against 0.0088 at `e`, an 11× per-system edge (max 0.1365 at `h`).
  It is not `h`-only: 2,143,844 `e` systems carry a non-zero probability, and by expected count `e` holds the bulk — 40,199 expected supergiants against 4,604 at `h` — because the `e` pool is 47× larger.
- **The observation channel cannot name one.** The only thing the overlay observes of an unvisited system is its arrival star class, read from `StarClass` (written by `FSDTarget`, `StartJump` and `NavRoute.json`), a short-code vocabulary.
  Across 201 journals the complete set of values it has held is:

  > `M K N F G TTS A L T Y H B AeBe WO DC O DA WNC D WN WC SupermassiveBlackHole DQ DAZ DAB CN`

  There is no supergiant string in it: a B supergiant plots as plain `B`, an M supergiant as `M`.
  The long spellings — `A_BlueWhiteSuperGiant`, `B_BlueWhiteSuperGiant`, `F_WhiteSuperGiant`, `G_WhiteSuperGiant`, `M_RedSuperGiant` — belong to the `Scan` event's `StarType`, which requires the ship to be in the system and the star scanned.
- **Check:** `system_seen` and `system_confirmed` hold 0 supergiants across the app's whole history, while `HERBIG` — rarer by the model's own numbers — holds 140 and `O-TYPE` 480.
  Nothing errored; the class never matched, so it could not be confirmed, chimed for, or scored by `scripts/score_predictions.py`.
- **They are out there and being found.** The commander's journals hold 9 supergiant `Scan` events — 7 `B_BlueWhiteSuperGiant`, 2 `F_WhiteSuperGiant` — in 8 systems, and 8 of those are `AA-A h` boxels, exactly where the model puts the density.
  The ninth is HIP 40361, a hand-named catalogued star, which is also the evidence against an `h`-only gate.
- This is the helium-rich gas giant case one step over: that one fails because a planet is not an arrival star, this one because an arrival star is not always named.

**What could revisit it:** an observation channel that reports `StarType`, such as reading `Scan` events.
A `Scan` means the ship has arrived, while the Confirmed table points at systems nobody has visited, so it would feed validation (`score_predictions.py` would have supergiant outcomes to score) rather than routing — a real gain and the cheapest way back in.

## Loading the billion-row all-sky surveys into `system_catalog` (2026-08-26)

**Status:** not done. `system_catalog` holds the 13 catalogues Frontier ingested wholesale (4,795,966 rows, 17.9 MB of parquet), where a coverage rate means something.

- **Target:** answer "which real-life catalogues exist in the game" for every catalogue with in-game presence, including the four all-sky surveys.
- **Why it looked worth doing:** DuckDB handles a billion rows without complaint, and 2MASS alone accounts for 8,205 in-game systems, more than HR, KOI or Tycho-2.
- **Blocker 1 — CDS does not distribute those four in bulk.** Their FTP directories (`II/246`, `I/297`, `I/252`, `I/305`) contain a ReadMe, a 1,000-row sample (`out.sam`) and a MOC coverage map, but no `catalog.dat.gz`; `I/259` (Tycho-2) ships 18 real data files.
  Loading them means separate bulk requests to IRSA, USNO/NOFS and MAST, and a bare `SELECT count(*)` over 2MASS through VizieR TAP times out at five minutes, so querying is no alternative.
- **Blocker 2 — the answer would be meaningless.** The four contribute 8,489 in-game systems (2MASS 8,205, USNO-A2.0 188, GSC 53, NOMAD1 43).
  A coverage rate of 0.000004% is a rounding error, saying only that Frontier never ingested NOMAD1 and those 43 names arrived incidentally via some cross-match; Hipparcos at 60.1% is a real finding about what Frontier shipped.
- **Size check** (10M synthetic rows per format, real designation shapes, on this machine):

| variant | B/row |
|---|---|
| full schema, 12-char designation | 11.75 |
| full schema, 17-char (2MASS form) | 17.67 |
| lean, name not stored | 5.51 |
| `UNIQUE(type, designation)` index | **+40.97** |
| Parquet zstd, sequential ids | 1.81 |
| Parquet zstd, position-coded ids | 15.21 |

- Extrapolated over NOMAD1 (1,117,612,732), GSC 2.3 (945,592,683), AllWISE (747,634,026), USNO-A2.0 (526,280,881), 2MASS (470,992,970) and the rest: 3,828,814,234 rows, ~50 GB of table, ~146 GB of index, ~23 GB of parquet, ~219 GB all in, against a 60 GB model database.
  The index alone is three times the data it indexes.

**What could revisit it:** a question that needs the survey rows themselves rather than a coverage rate; storage (50 GB of table) was never the problem.
Even then, resolve the ~8,500 in-game names against SIMBAD individually: a few thousand HTTP calls instead of 219 GB and a three-archive bulk-data negotiation, for the same answer.

**Also excluded — cluster-member designations.** In-game "NGC 2539 ZUG 25", "IC 4756 ALC 85", "Melotte 111 AV 186" are cluster plus member id, and NGC 2000.0 lists the 13,226 clusters, not their stars.
~6,000 in-game systems have this shape and need per-cluster membership catalogues or SIMBAD; this one is revisitable if the membership catalogues are findable.
