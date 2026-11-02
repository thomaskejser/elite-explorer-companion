# Raxxla investigation log

An evidence-checked log of the data-driven search for **Raxxla**, the legendary, never-confirmed location in Elite lore.
Findings are verified against the model database before being written here; lore and developer statements are in `RAXXLA_LORE.md`.
Started: 2026-07-13.

## Premise and hard limits

- Raxxla is a **single, hand-placed, unique secret** with **zero confirmed examples**.
  Our statistical predictors (mass-code gating, spatial models) work because their targets are Stellar-Forge procedural objects with huge training sets.
  **A one-off with n=0 cannot be statistically predicted**, so this log is *search-space narrowing*, never a claim of location.
- The data is **community-reported only** (Spansh/EDSM).
  Anything **permit-locked or never-visited is absent**; if Raxxla is hidden behind a permit, it is almost certainly not in our 200.7M systems at all.

## Findings

### F1 — Not present in the data

- Scanning every POI text field for `raxxla / dark wheel / etalon / thule / dynasty / formidine / oracle / generation ship` gives **0 Raxxla matches**, consistent with it being undiscovered.
- The data can map Raxxla's *neighbourhood*, not the object.

### F2 — Ruled out: Raxxla is not a "disguised" procedural system

- Procedural names are spatially deterministic (a sector = one ~1280 ly cube).
- Across all ~194.5M procedural systems, the **maximum** deviation of a system from its own sector's centroid is **1,681 ly**, and **zero** systems lie beyond 2,500 ly.
- No system's name is inconsistent with its location: no hand-placed system hides under a fake procedural name in the visible data.

### F3 — The special-system landscape (candidate pool, all known)

- **15,405 hand-authored systems** (non-procedural, no catalogue digits), counted by an ad-hoc sweep and **not persisted**.
  No table holds them, so the figure stands as recorded and reproducing it means writing the query again.
  Deep ones are all *known* landmarks: expedition waypoints (Beagle Point, Rendezvous Point), the **Colonia** cluster (~30 named systems ≈ 22 kly out), and notable real objects (Sagittarius A*, Great Annihilator).
- **Curated mystery layer** (edastro POIs): generation ships (Artemis, Atlas, Hyperion…), Guardian/Thargoid sites, **Merope** and **Delphi**, and — most relevant — the **Formidine Rift / Project Dynasty** complex (Formidine Rift, Hawking's Gap, Conflux settlements; **The Zurara** megaship @ Syreadiae JX-F c0).
- **Restricted / permit-locked sectors:** Bleia 1–5, Regor, Bovomit, Hyponia, Sidgoir, Praei, and several NGC/Col sectors.

### F4 — Geometric anomalies (option 3): explained, not mysterious

- **Off-plane (|y|):** the disk is thin — 178.8M systems at |y|<1000; only **49** above |y|>6000 (extreme |y| = 39,518).
  Beyond-rim max galactocentric radius ≈ 50,095 ly.
- **Isolation:** **14,872 systems have no known neighbour within ~100 ly** (beyond normal jump range).
- The extreme off-plane, beyond-rim and isolated systems are **overwhelmingly hand-named real catalogue stars** (HIP/HD/PSR/X-ray binaries like `Swift J1753.5-0127`) at their true 3D coordinates — geometrically extreme but *explained by real astronomy*.
- Geometry surfaces **no unexplained procedural outlier**: nothing in the visible data is both anomalous and inexplicable.

### Premise of 2026-07-13: visited pre-automation, likely a *predicted* system

Working fact from the user: **Raxxla's system has been visited — but probably before automated data collection (EDDN/EDMC) was common** — so it may never have been uploaded and would sit among the systems we *predict exist*.

- Under this premise "absent from data" implies **not uploaded**, not "hidden/permit-locked", and the object is a **normal, reachable, Stellar-Forge-generated system in the predicted / gap space**.
- The anomaly-detection track (F2, F4) can only see uploaded systems, and found nothing odd among them.
- A **name<->coordinate translator** is the critical tool: translate a clue (name or coordinate) into a specific predicted system, verify it is absent from the spine (absence *supports* a candidate), and characterise its neighbourhood from nearby systems we hold.
  Validate it by round-tripping known systems (name→coords must match stored coords).
- The binding constraint is **lore clues**, not data: the predicted space is ~10^11 systems; data + one constraint (region / name fragment / described property) yields a concrete shortlist.
  Data's role is translate-and-verify, not unaided search.
- From F3, the **Formidine Rift / Project Dynasty** region and the systems bordering permit-locked sectors are worth mapping once clues arrive.

F6 shows this premise does not follow from its source.

### F5 — Translation measured, lore reviewed (2026-07-13)

- **Name<->coordinate translation validated**: name->coordinate via data-anchored sector lookup; median locate error **546 ly** (p95 863) on known systems — sector-level precision as expected for 1280 ly sectors.
  It reported whether a clue system is present/absent, refined to boxel level, covered the 12,064 sectors that have uploaded systems, and `near x y z r` listed neighbours of any coordinate.
- **Lore compiled → `RAXXLA_LORE.md`** with per-clue interpretation:
  - **Reorte→Riedquat line (C1)** verified: unit (−0.787, 0, −0.616) to the −x/−z rim = the Formidine Rift.
    The thread resolved to the **Zurara**, not Raxxla, so it is likely **spent**.
  - **Strongest thematic hint (C3):** the "silver disc / double spiral turning like a galaxy, blur of light at centre" + "gateway to other Universes" reads as an **accretion disc around a (rotating) black hole** — Raxxla may sit *at/near a black hole*.
    Direction/theme, not coordinates; not statistically predictable (n=0).
  - Merope 5C, Tau Ceti, the Reorte/Riedquat/Tionisla cluster are known anchors to inspect, not predict.
  - No public clue has ever *located* Raxxla; all are direction or theme.

### F6 — Developer-statement sweep (2026-08-26): the premise has a named source, and it is weak

Read the community compilation *FDev ED-relevant quotes/videos* (Jorki Rasalas, Frontier Forums; via the Wayback snapshot of 2025-08-15, as the live forum refuses automated fetches).
Every quote is recorded with speaker, date and status in `RAXXLA_LORE.md`, where its clues are C6–C10.

1. **The "visited" premise traces to one uncorroborated rumour, and it says something different from what we assumed.**
   The premise adopted on 2026-07-13 matches a quote attributed to Michael Brookes at a closed LaveCon 2017 Q&A: *"the system where Raxxla is located has been visited and honked but Raxxla was not detected."*
   Brookes later declined to comment, Arthur Tomlie had not heard it, and nobody else present has confirmed it.
   Even if it is true:
   - **"Honked" is not "pre-automation".**
     A discovery scan since 2015 is exactly what EDDN/EDMC upload, so the claim points *into* the spine we hold, not into the predicted gap space.
     The 2026-07-13 premise — absence-from-data as evidence *for* a candidate — does not follow from it.
   - **The operative half is "not detected".**
     A honk does not reveal Raxxla, which relocates the search to what a discovery scan misses, not to where the ship has not been.
2. **The target may not be a system at all.**
   Braben, on camera: *"Does Raxxla exist? … of course. You don't know what it is though!"*, and (via Drew Wagar) *"we know why people haven't been able to find it."*
   Both say the obstacle is not distance.
   Raxxla may be a body, a station, a megaship, a phenomenon or an event, and Ocellus stations can be fitted with engines and driven between systems, so a **mobile** target is not excluded.
   F1–F4 were all *system*-level tests; none constrains a body-level or non-body target.
3. **One genuinely computable lead, at body level.**
   Brookes on Mitterand's Hollow: *"a manually added body with some incorrect overrides — we can't blame Stellar Forge for that one."*
   This is the only developer-confirmed **signature of hand-placement**, and it is a property of bodies: hand-authored content is written over Stellar Forge output and can carry physically inconsistent parameters.
   It is a real query against `system_body`, but it surfaces the whole hand-authored population — every mission target, beacon and landmark — so it is a filter, not a candidate generator, worth running only because nothing else here is runnable.
4. **The most likely reason none of this works.**
   Brookes: the Raxxla story "should be played out in game".
   Braben: commanders "get invited to join a secret organisation" at points in their progression.
   Adam Bourke-Waite confirms an unreleased Raxxla **codex entry** (Beyond Ch.4, 2018-10-18).
   The Elite-rank / Founder missions long rumoured to be Dark-Wheel-related were **removed**.
   Several of these describe *access*, not *place*: if Raxxla is gated behind a trigger, coordinate work cannot reach it and this project can only characterise a neighbourhood once something else names one.
   Not falsifiable from our side; stated so it is not assumed away.

**Nothing in the compilation locates Raxxla**, consistent with F5: no public statement ever has.
Arthur Tomlie, ~2021: *"It's there. Clearly it's there… The payoff would have to be great, and that's all I will say on it."*

## Ruled out

- Disguised procedural system (F2).
- Unexplained geometric/isolation outlier among visible systems (F4).
- Any system already named "Raxxla"/lore-tagged in data (F1).

## Open threads

- **[priority] Body-level override sweep (C7).**
  Query `system_body` for bodies whose orbital/physical parameters are inconsistent with their parent, siblings, or themselves — the Mitterand's Hollow signature.
  Expect the full hand-authored population as output; the deliverable is that population, characterised, not a candidate.
  This is the only lead in F6 we can actually run.
- **Re-examine the "visited" premise rather than carry it.**
  Its one uncorroborated quote points *into* our data, not into the predicted gap, so absence from data is not evidence for a candidate.
- **Write a name↔coordinate translator** against `elite_mapping.duckdb` before any clue-translation work; none exists in the repo.
- Map documented clues (Witch Head / Merope alignments, "43/42" numeric clues, Dark Wheel references, original-Elite galaxy positions) to coordinate regions.
- Enumerate permit-locked sector *edges* (visible bordering systems) — lower priority.
  "Hidden behind a permit" is not the leading hypothesis, though Braben's "reserve areas of the galaxy for future expansion" keeps it alive.
- **Not actionable, recorded so it is not assumed away:** if Raxxla is gated behind an in-game trigger (C10), none of the above reaches it.

## Method / provenance

- Four sweeps produced the findings: naming coherence over hand-named systems; special systems and mystery POIs (15,405 candidates); geometric anomalies (off-plane, rim, isolation); and a name↔coordinate translation of the procedural lattice across the 12,064 known sectors.
- **None of them re-runs**: no script in the repo implements them, so the findings stand as recorded and a fresh sweep means writing the query again against `system_known` / `system_predicted`.
- Everything here is a ranked hypothesis / characterisation, never a confirmed find.
