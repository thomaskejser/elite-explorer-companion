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
