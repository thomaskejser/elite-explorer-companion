# Dead ends / negative results

Investigations that did **not** yield a usable prediction, with the reason and what
(if anything) could revisit them. Recording these so we don't repeat the work.
Facts verified against `elite_mapping.duckdb` at time of writing.

---

## Green Gas Giants (GGGs) — no reliable predictor (2026-07-13)

**Target:** predict where undiscovered Green Gas Giants are.

**What they are:** gas giants that render bright green. In-lore: fluorescing
"radioplankton." Technically: a **color-selection bug** — green is the default colour
before the calculation runs, and some value in the gas giant's characteristics pushes
the colour picker out of its intended range so it stays green. Deterministic, but
driven by an internal generation value. Extremely rare (~1 per 2M systems discovered).

**What we established (positives):**
- GGGs **are codex-labeled**: EDSM `codex_ent_green_sudarsky_class_i/ii/iii`,
  `green_giant_with_water_life`, `green_water_giant`; Canonn "Green Class I/II/III/IV
  Gas Giant", "Green Gas Giant with Ammonia Life". So we have a clean positive set:
  **67 distinct known systems** (codex + the 60 EDAstro POIs, largely overlapping).
  (Note: `codex_ent_gas_clds_green` = green *clouds*, a different NSP with ~1,020
  systems — do not confuse with green giants.)
- Confirmed co-occurrences: **K10-Type Anomaly** (8/60 systems), green NSP clouds,
  silicate/sulphur geology.

**Why it's a dead end (three independent reasons):**
1. **No spatial pattern.** The 67 systems are scattered galaxy-wide — galactocentric
   radius 604 → 41,247 ly, Sol-distance 300 → 56,707 ly. Only a faint near-core hint
   (the Byoomao systems). Location-based prediction is out.
2. **No strong property pattern in what we hold.** Only mild subtype enrichment
   (Class IV ~1.5×, water-based-life ~1.4×), and diluted because a green *system* holds
   several gas giants of which only one is green.
3. **The likely trigger (atmosphere composition) is not in the full corpus.** We kept
   `spansh_body` lean and dropped composition; of the 67 green giants only 1 appears in
   the 7-day tables that carry composition. The bug may also key off an internal
   per-body value **not exposed in public dumps** at all.
- Consistent with the community: with dedicated effort they have found no predictive
  pattern; discovery is "largely a matter of luck."

**What could revisit it (research gamble, not a likely win):**
- Re-extract **atmosphere + solid composition for gas giants** from the raw Spansh
  dump (`raw/spansh_galaxy.json.gz`, still retained), then test whether a composition
  signature separates the 67 green giants from the ~48M normal ones (ML on a tiny
  positive set). ~1–2 h compute; uncertain payoff — if the colour bug keys off an
  internal value absent from the dumps, no composition data will predict it.

**Status:** parked. Not added to `RECOMMENDATIONS.md` (no vetted pattern to stand
behind). Scripts used: ad-hoc queries this session (GGG codex + POI join, spatial map,
composition feasibility check).

---

## Planet classes are not boxel-predictable (2026-08-10)

**Target:** reuse the boxel lever — the strongest predictor this project has — on
valuable *planet* classes: Earth-likes, ammonia worlds, water worlds, and exobiology.

**Why it looked promising:** R1 gates star types by mass code, and the BH/WR model plus
the neutron work both found that a boxel's own rate beats any global rate by a wide
margin. Rare stars show **3–13×** binomial overdispersion per boxel. Nobody had pointed
that lever at planets.

**What we established.** Denominator = 22,004,981 **fully-scanned** systems
(`spansh_system.scanned_body_count >= declared_body_count`, both > 0); in a
partly-scanned system "no ELW" only means nobody looked. Overdispersion = observed
spread of per-boxel rates ÷ the binomial spread independent rolls would give, over
boxels with ≥25 fully-scanned systems:

| target | galactic rate | boxel ratio | within one arrival-star class |
| --- | --- | --- | --- |
| Water world | 7.659% | 1.9× | 1.2–1.6× |
| Gas giant w/ water-based life | 6.601% | 2.2× | — |
| Earth-like world | 0.743% | **1.4×** | 1.1–1.4× |
| Ammonia world | 1.211% | **1.3×** | 1.1–1.3× |
| Exobiology (a body with ≥3 bio signals) | 6.28% | 2.2× | — |

**Why it's a dead end:** the mass code and boxel decide which **stars** a system gets;
planets are rolled essentially per-system. Conditioning on the arrival star class
collapses what little spread there is (ELW 1.4× → 1.1–1.4×), so the boxel is not even
contributing information independent of the star. There is no rich-boxel tail to route
to — the top 1% of boxels reach only 7.7% for ELW, against 45.1% for helium-rich gas
giants in the same test.

**Also ruled out — honk-time ELW detection.** `FSSDiscoveryScan` carries only
`BodyCount`, `NonBodyCount`, `Progress`, `SystemName`, `SystemAddress` — nothing
per-body, verified over 2,128 honks. Across 27 ELW finds in the journals, **zero** were
revealed at the honk timestamp. Predicting from what the honk *does* give (arrival star
class × body count) spans 0.003% → 3.65%: real triage, but the best cell is still 96%
disappointment. Two fragments worth keeping, both already in `RECOMMENDATIONS.md`
territory rather than here: `BodyCount ≤ 2` is a clean **zero** for ELW (134 hits in
5.8M systems), and the ELW arrival distance is tightly bound by arrival star class
(K: 285–504 Ls, only 5.4% of all planets), which orders FSS tuning even though it
cannot predict presence.

**What could revisit it:** nothing in this data. A per-system planet model would need
generator inputs we do not hold; the boxel-level aggregates that exist
(`edastro_boxel_stats`) describe stars and gas-giant composition, not terrestrials.

**Status:** closed. The one exception found in the same sweep — **helium-rich gas
giants at 5.4× with a hard radial gate** — is a live target and is modelled as `p_hr`
in `scripts/build_candidates.py`. Scripts used: ad-hoc queries this session (per-class
boxel overdispersion, honk timeline over 154 journals, ELW arrival-distance bands).
