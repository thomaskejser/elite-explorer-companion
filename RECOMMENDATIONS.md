# Exploration recommendations

A curated, evidence-checked register of actionable findings from the elite_mapping
prediction work. **Only vetted conclusions go here** — each entry states its
confidence and the check behind it. Numbers are re-verified from
`elite_mapping.duckdb` at the time of writing, not transcribed from chat output.

- Data snapshot: EDSM/EDAstro/Canonn 2026-07-10; Spansh galaxy dump 2026-07-12.
- Galaxy frame: Sol = (0,0,0); Sgr A* ≈ (25.2, −20.9, 25900); galactic plane = y≈0;
  `plane_r` = galactocentric disk radius (Sol ≈ 25.9 kly, rim ≈ 50 kly).
- Confidence legend: **A** = hard fact / near-deterministic · **B** = validated,
  moderate uncertainty · **C** = directional/ranking only, absolute values soft.

> **Recompute completed 2026-08-02.** The 2026-07-14 theorised-systems fix (script
> `03s`) invalidated the counts in R2–R5; those sections have now been **fully
> recomputed** and several conclusions **changed materially** (see the change log).
> The correction is also applied to `star_boxels` (`03u`) — it still carried the
> fill-from-0 bug, which inflated its `missing` column from a true 207,776 to
> 1,069,699,995.
>
> **The candidate pool is now the ~2.26M real in-db-unscanned systems** (catalogued
> records with exact coordinates that nobody has detail-scanned), computed per sector
> in the new table `sector_unscanned` (`03v`). The "theorised" layer (207,776
> enumerable internal gaps) is retained but is thin and heavily core-biased — it is
> **not** a usable basis for fringe estimates.
>
> **Gating (R1) and the de-biased rate model are unaffected** — they were always
> built on real scanned systems.

---

## R1 — Star type is gated by procedural "mass code" (confidence A)

The mass code (letter `a`–`h` in a system's procedural name, readable **without
scanning**) hard-gates these targets. Verified across scanned systems:

| mass code | scanned systems | black-hole rate | Wolf-Rayet rate |
| --- | --- | --- | --- |
| a, b, c, d | 72,261,736 | **0.000%** (0 objects) | **0.000%** (0 objects) |
| e | 2,005,329 | 3.86% | 0% |
| f | 285,900 | 50.9% | 0% |
| g | 198,814 | 39.7% | 0% |
| h | 167,005 | 45.9% | 27.6% |

**Recommendation:** only bother scanning for black holes in **e/f/g/h** systems and
Wolf-Rayets in **h** systems. Filter any target list by mass code first — it
eliminates ~99% of systems with zero false negatives. This is the single most
reliable rule in the whole analysis.

---

## R2 — REVISED: outside the core, black holes and Herbig Ae/Be dominate; Wolf-Rayets do **not** (confidence B)

**The previous version of R2 was wrong and is retracted.** It claimed Wolf-Rayets
were the richer undiscovered fringe target (~2,630 vs ~630 black holes). That
inverted ranking came entirely from fabricated mass-code-h theorised systems.

The rate observations that motivated it are still correct: black-hole rate collapses
with galactocentric radius while the Wolf-Rayet rate inside h systems stays flat.
Verified among scanned systems:

| plane_r band | e: BH% | f: BH% | g: BH% | h: BH% | h: WR% |
| --- | --- | --- | --- | --- | --- |
| 0–10 kly | 5.92 | 58.18 | 45.88 | 49.13 | 25.60 |
| 10–20 kly | 2.78 | 43.33 | 39.10 | 36.61 | 33.95 |
| 20–30 kly | 0.45 | 4.69 | 11.69 | 26.36 | 32.51 |
| 30 kly+ | 0.29 | 3.19 | 9.02 | 26.06 | 30.85 |

**What was missed: the fringe has almost no h systems to scan.** Real unscanned
records beyond 30 kly, by mass code — e **67,434**, f **1,245**, g **855**, h **35**.
Thirty-five. A 31% WR rate on 35 systems is ~11 finds; a 0.29% BH rate on 67,434
systems is ~196, plus ~120 more from f/g.

De-biased expected undiscovered beyond 30 kly, over the real unscanned pool (71,155
systems):

| target | expected | why |
| --- | --- | --- |
| **Herbig Ae/Be** | **~2,982** | rate *rises* with radius (4.6% in e, ~18% in f/g) |
| Black hole | ~319 | low rate, very large e pool |
| O-type | ~369 | 51% of fringe g systems, but only 855 of them |
| Supergiant | ~149 | — |
| Wolf-Rayet | **~14** | high rate, but only 35 candidate systems exist |

**Recommendation (corrected):** for rim-ward trips, **Herbig Ae/Be is by far the
richest undiscovered target** — an order of magnitude above everything else, and the
only target whose rate *improves* as you go out. Do **not** plan a fringe trip around
Wolf-Rayets. That said, per-system an unscanned h system remains the best single
target anywhere (26% BH + 31% WR); they are simply almost absent out there.

---

## R3 — REVISED: best sectors near Sol (confidence B for ranking, C for counts)

Ranked over the **real in-db-unscanned pool**, not theorised. Closest sectors with
expected BH+WR ≥ 3 and ≥ 100 unscanned systems. `unscan` = real catalogued systems
nobody has detail-scanned (exact coordinates); `theo` = additionally enumerable
internal-gap systems (boxel-centroid coordinates only).

| sector | dist from Sol (ly) | unscanned | theorised | found BH | exp BH | exp WR | coords (x,y,z) |
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

**Recommendation:** the ~3.5–5 kly band still gives the best balance of travel time
and unexplored pool — **Bleae Thaa**, **Drojeae** and **Traikoa** are the strongest.
Every one of these is a **black-hole** trip.

> **⚠ Wolf-Rayets are not a near-Sol target at all.** There are **zero** unscanned
> mass-code-h systems within 5,000 ly of Sol (all 58 known h systems inside that
> radius are already scanned), and only **37** between 5–10 kly. The nearest sector
> holding any unscanned h system is **Thailoea at 6,639 ly** (one system). The
> earlier R3 column claiming 7–17 expected WR per near-Sol sector was pure artifact.
> A real WR pool only appears past ~10 kly (e.g. Ellaisms 11.4 kly, exp 15.8;
> Xeehia 12.1 kly, exp 11.9; Skaude 10.8 kly, exp 8.9).

---

## R4 — REVISED: best deep-fringe sectors (confidence C — ranking only)

For rim-ward trips (`plane_r` > 30 kly), over the real unscanned pool. Use the
ordering, not the numbers.

- **Herbig Ae/Be (the reason to go):** Eafots (exp 20.3, 495 unscanned), Gludgoea
  (15.5), Gludgoe (15.0), Hypiae Aihm (12.1), Gludgoi (11.6), Hypuae Aim (11.3).
- **Black holes:** Eafots (3.3), Gludgoe (2.9), Hypheerld (2.6), Phroi Hypue (2.6),
  Phaa Ain (2.6), Gludgoea (2.6).
- **Supergiants:** Hypiae Aihm (2.5), Pheia Aihm (2.4), Phua Aihm (2.2).
- **O-type:** Pyrivai (8.2), Proo Graae (6.0), Drootue (4.1) — note these all sit
  **~55 kly from Sol** (far side of the core), unlike the others at 5–10 kly.
- **Wolf-Rayets:** best fringe sector is ~0.5 expected. Not worth routing for.

**Best all-round:** **Eafots** and **Gludgoea/Gludgoe** — top-3 for Herbig, black
holes and neutron stars simultaneously, and all within 5–8 kly of Sol despite
sitting past 30 kly galactocentric (they are rim-ward *of Sol's own arm*, not across
the galaxy).

---

## R5 — REVISED: rare stellar exotics: neutron, white dwarf, Herbig Ae/Be, O-type, supergiant

Same method as BH/WR (name-readable mass-code gate → local de-biased rate → sector
ranking). Gating among scanned systems confirms each is name-predictable:

| target | gate | peak | validation (local vs baseline) | coverage |
| --- | --- | --- | --- | --- |
| **Supergiant** | e+ | h: 7.9% | **2.4×** (best) | full — confidence **B** |
| **O-type star** | f+ | g: 42.5% | 1.8× | full (0 below f) — confidence **B** |
| **White dwarf** | d+ | f: 6.0% | 1.4× | partial; rare/uniform — confidence **C** |
| **Neutron star** | d+ | e: 27% | 1.4× | **partial** — e/f/g/h only (see note) |
| **Herbig Ae/Be** | e+ | g: 12.7% | 1.1× | full — confidence **B** (strong spatial pattern) |

> **Note (neutron & white dwarf):** these gate at mass code **d** and the *bulk* of
> them live in d-code systems, which are **not** modelled here (d's pool is enormous,
> and neutron stars are already well-mapped via the community "neutron highway").
> The sectors below are the high-mass-code (e/f/g/h) subset only.

Galaxy-wide expected undiscovered over the 2.26M-system unscanned pool: neutron
~236,000 · Herbig ~84,000 · black hole ~74,000 · O-type ~21,000 · white dwarf
~11,500 · Wolf-Rayet ~5,200 · supergiant ~5,100.

**Herbig Ae/Be** (confidence B) — young stars, so they cluster in **nebulae/young
clusters**. Near Sol: **`Swoilz`** (1.35 kly, exp 11.1), **`Swoiwns`** (1.45 kly,
11.1), `Praea Euq` (1.32 kly, 10.4), **`Col 359 Sector`** (0.93 kly, exp 4.4),
`Col 173 Sector` (1.41 kly, 4.1), `Synuefai` (1.24 kly, 3.5), `Wregoe` (1.15 kly, 3.2).
Fringe: `Eafots` (20.3), `Gludgoea` (15.5), `Gludgoe` (15.0).

**O-type** (confidence B) — near Sol: `Smojue` (3.6 kly, exp 5.2), `Traikaae`
(4.8 kly, 3.8), `Traikoa` (5.1 kly, 3.5), `Bleae Eurk` (5.7 kly, 3.4), `Thailoi`
(5.8 kly, 3.4); far side/fringe: `Pyrivai` (8.2), `Proo Graae` (6.0).

**Supergiant** (confidence B, low counts) — near Sol: `Pro Eurl` (2.16 kly, 2.3),
`Prua Dryoae` (2.18 kly, 2.6), `Synuefue` (2.18 kly, 2.5), `Blaa Eork` (2.88 kly, 2.5),
`Aucopp` (3.0 kly, 2.6); fringe: `Hypiae Aihm` (2.5), `Pheia Aihm` (2.4).

**Neutron (e/f/g/h subset)** — near Sol: `Sifi` (2.30 kly, 2.0), `Prooe Drye`
(2.31 kly, 2.0), `Bleae Thua` (2.36 kly, 2.1), `Bleia Eohn` (2.39 kly, 2.0),
`Phylur` (2.99 kly, 2.7); fringe: `Gludgoe` (2.8), `Gludgoea` (2.7), `Eafots` (2.5).

**White dwarf (e/f/g/h subset, confidence C)** — expected counts low everywhere.
Best are all 10–13 kly out: `Skaude` (16.4), `Flyae Eaec` (8.3), `Ellaidst` (7.2),
`Prua Phoe` (4.8), `Preia Phoe` (4.4). Nothing worthwhile near Sol.

> **Standout nearby targets:** **Swoilz / Swoiwns / Praea Euq** (~1.3–1.5 kly) for
> Herbig Ae/Be — better than Col 359 on the corrected numbers, though Col 359 remains
> the best *cluster* destination and ranks for several targets at once.

---

## R6 — Black holes along the Reorte→Riedquat corridor (unchanged, re-verified 2026-08-02)

The Raxxla "clue line" (Reorte→Riedquat, extended outward toward the Formidine Rift;
direction (−0.787, 0, −0.616)) doubles as a concrete black-hole search corridor.
Confidence **B** that undiscovered black holes exist and are findable here (119 are
already confirmed and completeness is low); **C** on the absolute count.

- **Found:** 119 confirmed black holes in a 2,000 ly-wide corridor (e/f/g/h systems);
  49,312 systems in-db, 33,797 scanned.
- **Expected still-undiscovered:** ~**40** from the real unscanned pool, plus ~**3**
  from the 35 enumerable theorised systems → **~43**.
- **Character:** this corridor points *away* from the core, so it is BH-**poor** —
  found-rates e 0.19%, f 2.03%, g 6.38%, h 29.3%. The estimate is dominated by the
  **numerous real in-db-unscanned e systems** (15,165 × 0.19% ≈ 29), plus f (278 ×
  2.03% ≈ 6) and g (72 × 6.38% ≈ 5). **There are 0 unscanned h systems in this
  corridor** (all 41 are already scanned).

**⚠ Retraction (2026-07-14, still stands):** the earlier "target these mass-code-h
boxels" ladder (Prooe Drye, Flyae Drye, Slegoae … each "~40–56 unscanned h") was an
artifact of the theorised bug. There is **no h-boxel target ladder** here.

**Net:** the corridor genuinely has undiscovered black holes (~40), but they're
spread thinly across many low-odds e systems — not a rich or concentrated target.

---

## Method, confidence, and caveats

- **Two candidate layers, very different reliability:**
  - **In-db-unscanned (2,255,468 systems; e 2,015,262 / f 175,510 / g 44,586 /
    h 20,110)** — real catalogued records with exact coordinates, not detail-scanned.
    **This is the reliable pool** and the basis for every count in R2–R6.
  - **Theorised (207,776)** — internal index gaps in densely-observed boxels
    (≥50% of the min..max range observed). Likely-real but unconfirmed, coordinates
    are the boxel centre (±≤1280 ly). Only **117,356 of 981,286** boxels are dense
    enough to enumerate at all, and those skew hard toward explored/core space:
    93% of theorised systems sit inside 20 kly galactocentric, and only 481 f/g/h
    systems (zero h) survive past 30 kly. **Theorised cannot support fringe
    estimates** — that was the root of the retracted R2/R4 claims.
- **De-biasing:** scanned systems over-represent rare stars because explorers
  preferentially scan the bright massive primary. True Forge rate is estimated from
  **fully-sampled boxels** (≥10 scanned, ≥80% covered) and applied **locally**
  (k-nearest fully-sampled boxels — a radius-only curve was tried and *rejected*
  because it failed a spatial hold-out; density has directional/arm structure).
- **Validation:** random 20% hold-out of fully-sampled boxels. Local de-biased BH
  rate MAE 22.1 pp vs 28.5 pp for a global-mean baseline (1.3× better); WR 11.1 vs
  12.0 pp (1.1×, rate is spatially uniform); supergiant 2.4×, O-type 1.8×, white
  dwarf 1.4×, neutron 1.4×, Herbig 1.1×. Boxel-level rates remain noisy (±10–20 pp),
  so **rank the sectors, don't trust the decimals**. Reliability is highest near Sol,
  lowest at the deep fringe.
- **Both layers are floors.** Entirely-unvisited boxels contain neither real records
  nor enumerable gaps, so true undiscovered totals are higher. Enumerating those
  needs a full name→coordinate generator; `scripts/pgnames.py` does this only for
  the 12,064 sectors that already have uploaded systems.
- **Coordinates are boxel/sector centroids** (±≤1280 ly) — good for routing, not
  for pinpointing a single system. Individual unscanned systems have exact
  coordinates (see `app/candidates.parquet`).
- **No Live/Legacy split** in the underlying dumps (`galaxy_version` = unknown).
- Objects are only *confirmed* by an in-game scan; everything here is a ranked
  hypothesis with a verification route, never a claimed discovery.

## Provenance (tables in elite_mapping.duckdb)

| table | rows | contents |
| --- | --- | --- |
| spansh_system | 194,696,927 | full-galaxy system spine |
| spansh_body | 569,697,301 | full-galaxy body corpus |
| sys_feat | 194,696,927 | per-system features (mass code, radii, scanned flag, BH/WR flags) |
| star_agg | 74,707,706 | per-system rare-star flags (neutron/WD/Herbig/O/supergiant) |
| **sector_unscanned** | **9,586** | **per-sector real unscanned pool + de-biased expected for all 7 targets (03v) — primary source for R2–R5** |
| star_boxels | 981,286 | e/f/g/h boxels, per-target counts; `missing` corrected 2026-08-02 (was 1,069,699,995 → 207,776) |
| theorised_system | 57,700 | f/g/h internal-gap systems in dense boxels (corrected 2026-07-14) |
| theorised_boxels | 16,698 | per-boxel rollup + model scores (rescored 2026-08-02) |
| explore_sectors | 4,396 | theorised-layer sector ranking (kNN de-biased); was 6,206 — the corrected theorised layer covers fewer sectors |
| fringe_sectors_debiased | 6 | deep-fringe theorised-layer sectors, biased vs de-biased; was 239 — only 6 fringe sectors retain ≥10 enumerable gaps, which is why R4 moved to the unscanned pool |
| rare_star_sectors | 9,586 | theorised-layer per-sector expected for each rare-star target |

## Change log

- 2026-07-13 — Initial register: R1 (mass-code gating), R2 (WR > BH outside core),
  R3 (near-Sol sectors), R4 (deep-fringe sectors). Built from the black-hole /
  Wolf-Rayet model (scripts 03a–03l) with local de-biasing and spatial validation.
- 2026-07-13 — Added R5 (rare stellar exotics; scripts 03m–03n) and R6 (Reorte→
  Riedquat black-hole corridor; script 03r). Fixed a Laplace-smoothing artifact that
  faked ~7 expected finds in target-absent sectors.
- 2026-07-14 — **Fixed the theorised-systems bug** (script 03s): index enumeration now
  keeps only internal gaps in densely-observed boxels (no filling from 0). Theorised
  72,050,995 → 57,700. Revised R6 down to ~40 and retracted its h-boxel ladder.
  R2–R5 flagged as pending recompute.
- 2026-08-02 — **R2–R5 recomputed** (scripts `03t` rescore, `03u` star_boxels fix,
  `03v` unscanned pool; `03g`/`03j`/`03l`/`03n`/`03r` re-run). Substantive changes:
  - **R2 inverted and rewritten.** The old "Wolf-Rayets are the richer fringe target"
    was an artifact of fabricated h-code theorised systems. Only **35** unscanned h
    systems exist past 30 kly, so fringe WR ≈ 14 vs BH ≈ 319. New headline: **Herbig
    Ae/Be (~2,982) is the dominant fringe target**, and the only one whose rate rises
    with radius.
  - **R3 rebuilt over the real unscanned pool** — new sector list (Bleae Thaa,
    Drojeae, Traikoa lead). Added the finding that there are **zero** unscanned
    mass-code-h systems within 5 kly of Sol, so the old WR column was fiction.
  - **R4 rebuilt** — Eafots / Gludgoea / Gludgoe lead; WR dropped from the fringe
    recommendation entirely.
  - **R5 recomputed** — counts fell ~5–10× (old Col 359 Herbig "exp 39" → 4.4);
    Swoilz/Swoiwns now outrank Col 359 near Sol. Gating and validation ratios
    unchanged; supergiant is the best-validated target (2.4×).
  - **R6 re-verified unchanged** (~40 + ~3 theorised = ~43).
  - `star_boxels.missing` corrected (1.07 billion → 207,776); new table
    `sector_unscanned` is now the primary source for R2–R5.
