# Raxxla investigation log

A running, evidence-checked log of the data-driven search for **Raxxla** — the
legendary, never-confirmed location in Elite lore. Findings are verified against
`elite_mapping.duckdb` before being written here.

Started: 2026-07-13.

## Premise and hard limits (read first)

- Raxxla is a **single, hand-placed, unique secret** with **zero confirmed
  examples**. Our statistical predictors (mass-code gating, spatial models) work
  because their targets are Stellar-Forge procedural objects with huge training
  sets. **A one-off with n=0 cannot be statistically predicted.** This log is
  *search-space narrowing*, never a claim of location.
- The data is **community-reported only** (Spansh/EDSM). Anything **permit-locked
  or never-visited is absent**. If Raxxla is hidden behind a permit, it is almost
  certainly not in our 194.7M systems at all.

## Findings

### F1 — Not present in the data (as expected)
Scanning every POI text field for `raxxla / dark wheel / etalon / thule / dynasty
/ formidine / oracle / generation ship`: **0 Raxxla matches**. Consistent with it
being undiscovered. The data can map Raxxla's *neighbourhood*, not the object.

### F2 — RULED OUT: Raxxla is not a "disguised" procedural system
Procedural names are spatially deterministic (a sector = one ~1280 ly cube). Across
all ~194.5M procedural systems, the **maximum** deviation of a system from its own
sector's centroid is **1,681 ly**, and **zero** systems lie beyond 2,500 ly. So no
system's name is inconsistent with its location — there is no hand-placed system
hiding under a fake procedural name in the visible data.

### F3 — The special-system landscape (candidate pool, all known)
- **15,405 hand-authored systems** (non-procedural, no catalogue digits) →
  persisted as table `special_systems`. Deep ones are all *known* landmarks:
  expedition waypoints (Beagle Point, Rendezvous Point), the **Colonia** cluster
  (~30 named systems ≈ 22 kly out), and notable real objects (Sagittarius A*,
  Great Annihilator).
- **Curated mystery layer** (edastro POIs): generation ships (Artemis, Atlas,
  Hyperion…), Guardian/Thargoid sites, **Merope** and **Delphi**, and — most
  relevant — the **Formidine Rift / Project Dynasty** complex (Formidine Rift,
  Hawking's Gap, Conflux settlements; **The Zurara** megaship @ Syreadiae JX-F c0).
- **Restricted / permit-locked sectors:** Bleia 1–5, Regor, Bovomit, Hyponia,
  Sidgoir, Praei, and several NGC/Col sectors.

### F4 — Geometric anomalies (option 3): explained, not mysterious
- **Off-plane (|y|):** the disk is thin — 178.8M systems at |y|<1000; only **49**
  above |y|>6000 (extreme |y| = 39,518). Beyond-rim max galactocentric radius
  ≈ 50,095 ly.
- **Isolation:** **14,872 systems have no known neighbour within ~100 ly** (beyond
  normal jump range). But the extreme off-plane, beyond-rim, AND isolated systems
  are **overwhelmingly hand-named real catalogue stars** (HIP/HD/PSR/X-ray binaries
  like `Swift J1753.5-0127`) placed at their true 3D coordinates — geometrically
  extreme but *explained by real astronomy*.
- **Conclusion:** geometry surfaces **no unexplained procedural outlier**. Nothing
  in the visible data is both anomalous and inexplicable.

## PREMISE REVISED (2026-07-13): visited pre-automation, likely a *predicted* system

New working fact (from the user): **Raxxla's system has been visited — but probably
before automated data collection (EDDN/EDMC) was common** — so it may simply never
have been uploaded, and would sit among the systems we *predict exist* rather than
ones we have data for.

This flips the earlier conclusion. "Absent from data" no longer implies
"hidden/permit-locked"; it implies **not uploaded**. The object is therefore a
**normal, reachable, Stellar-Forge-generated system in the predicted / gap space** —
exactly what our procedural machinery reasons about.

Consequences:
- The anomaly-detection track (F2, F4) is **retired** — it can only ever see uploaded
  systems, and we've confirmed there's nothing odd among them.
- The **pgnames name↔coordinate translator** becomes the critical tool: translate a
  clue (name or coordinate) into a specific predicted system, verify it's absent from
  our 195M (absence now *supports* a candidate), and characterise its neighbourhood
  from nearby systems we do have. Validate the translator by round-tripping known
  systems (name→coords must match stored coords).
- The binding constraint is now **lore clues**, not data: the predicted space is
  ~10^11 systems; data + one constraint (region / name fragment / described property)
  yields a concrete shortlist. Data's role is translate-and-verify, not unaided search.

Still-useful earlier leads (F3): the **Formidine Rift / Project Dynasty** region and
the systems bordering permit-locked sectors remain worth mapping once clues arrive.

## F5 — Tool built + lore reviewed (2026-07-13)
- **pgnames translator built & validated** (`scripts/pgnames.py`): name→coordinate
  via data-anchored sector lookup; median locate error **546 ly** (p95 863) on known
  systems — sector-level precision as expected for 1280 ly sectors. Reports whether a
  clue system is present/absent and refines to boxel level; covers the 12,064 sectors
  that have uploaded systems. `near x y z r` lists neighbours of any coordinate.
- **Lore compiled → `RAXXLA_LORE.md`** with per-clue interpretation. Key takeaways:
  - **Reorte→Riedquat line (C1)** verified: unit (−0.787, 0, −0.616) to the −x/−z rim
    = the Formidine Rift. But this thread resolved to the **Zurara**, not Raxxla —
    likely **spent**.
  - **Strongest thematic hint (C3):** the "silver disc / double spiral turning like a
    galaxy, blur of light at centre" + "gateway to other Universes" reads as an
    **accretion disc around a (rotating) black hole** — Raxxla may sit *at/near a black
    hole*. Direction/theme, not coordinates; not statistically predictable (n=0).
  - Merope 5C, Tau Ceti, the Reorte/Riedquat/Tionisla cluster are known anchors to
    inspect, not predict.
  - **Honest:** no public clue has ever *located* Raxxla; all are direction or theme.

## Ruled out
- Disguised procedural system (F2). · Unexplained geometric/isolation outlier among
  visible systems (F4). · Any system already named "Raxxla"/lore-tagged in data (F1).

## Open threads (next steps under the revised premise)
- **[priority] Build + validate the pgnames name↔coordinate translator** (validate by
  round-tripping known systems). Required for every clue path.
- Obtain lore clues (system name fragment / coordinate region / described property)
  and translate them into specific *predicted* candidate systems; verify each is
  absent from our data and characterise its neighbourhood.
- Map documented clues (Witch Head / Merope alignments, "43/42" numeric clues, Dark
  Wheel references, original-Elite galaxy positions) to coordinate regions.
- Enumerate permit-locked sector *edges* (visible bordering systems) — lower priority
  now that "hidden" is not the leading hypothesis.

## Method / provenance
- Scripts: `03o_anomalies.py` (naming coherence, hand-named), `03p_special_systems.py`
  (special systems + mystery POIs), `03q_geometric_anomalies.py` (off-plane, rim,
  isolation), `pgnames.py` (name↔coordinate translator; `build`/`locate`/`near`).
  Tables: `special_systems` (15,405), `sector_lookup` (12,064). Isolation regenerable
  via 03q. Lore reference: `RAXXLA_LORE.md`.
- Everything here is a ranked hypothesis / characterisation, never a confirmed find.
