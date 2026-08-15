# Prediction engine: data model and first experiment

## Questions the engine can answer

- Which **unexplored or incompletely explored** systems most resemble systems
  with confirmed NSPs?
- Given a scanned body, which exobiology or geological labels are plausible?
- Which targets offer the highest expected discovery value after travel cost and
  confidence are considered?

It should never claim a discovery. Output is a ranked hypothesis with evidence,
data coverage and an in-game verification route.

## Core entities

| Table | Key fields |
| --- | --- |
| `system` | `system_id64`, name, x/y/z, procedural-sector metadata, population, `galaxy_version` |
| `body` | `body_id`, system ID, parent/orbit, class/star type, mass/radius/gravity, temperatures, atmosphere, volcanism, composition, rings, landable |
| `scan_event` | source event ID, body/system ID, raw JSON, event time, game build, commander's anonymised hash |
| `signal_observation` | body/system ID, signal type, count, signal name, method (FSS/DSS/visual), observer time, coverage confidence |
| `phenomenon_site` | site ID, parent system/body/ring, placement (Lagrange/ring/belt/surface), family, variant, coordinates if applicable, confirmed state |
| `codex_entry` | codex ID/name, region, state (rumoured/reported/discovered), scan time, discoverer pseudonym if permitted |
| `poi` | curated type, location, source, coordinate precision, authored/procedural classification |
| `source_record` | origin URL/stream, retrieved time, checksum, licence/terms, version |

Use stable numeric IDs where available; preserve canonical name as an attribute.

## Feature sets

**System:** galactic x/y/z; distance from plane/core/Sol; Codex region; density
of known stars and prior discoveries in several radii; primary star and all-star
class counts; multiplicity; body count; age/metallicity; population; permit
state; procedural name components.

**Body/ring:** parent type; semi-major axis; equilibrium/surface temperature;
mass, radius and gravity; atmosphere and pressure; volcanism; landability;
materials; ring/belt count, class, composition, mass and radius; moon/parent
relationships.

**Observation quality:** source count, last observation date, whether FSS/DSS
completed, number of scanned bodies versus expected, and known visitation. These
features prevent “unseen” from masquerading as “absent.”

## First model: NSP candidate ranking

1. Build positives from confirmed `Notable Stellar Phenomena` signal/site
   observations. Make system-level and parent-body/ring-level data sets.
2. Build **reliable negatives only** from thoroughly scanned systems with no NSP
   signal. Keep unknown/unvisited systems out of supervised negatives.
3. Split train/test spatially (by sector or large 3-D blocks), not randomly.
   This tests extrapolation rather than memorising local exploration routes.
4. Begin with calibrated logistic regression and gradient-boosted trees. Compare
   against simple baselines: nearest known NSP, star-class/ring rules and Codex
   region rate.
5. Evaluate precision@K, recall, PR-AUC, calibration/Brier score and discovery
   yield per 1,000 ly. Report performance by galactic region and exploration
   completeness.
6. Rank unvisited candidates only when feature coverage is sufficient. Show
   nearest positive analogues, feature contributions and uncertainty interval.

## Leakage and bias controls

- Do not use `has_nsp`/Codex status, exact signal text or post-discovery dates
  as features for the same target.
- Separate training facts known before a prediction cut-off from later reports.
- Correct or stratify by exploration intensity and route proximity. A random
  split will substantially overstate performance.
- Sample candidate systems from generated-name/coordinate spaces only when their
  existence and coordinate accuracy are verified. Never fabricate star/body
  facts for an arbitrary coordinate.
- Maintain source terms/licensing and an audit trail so labels can be retracted.

## Candidate output contract

```json
{
  "target": {"system_id64": 0, "body_id": 0},
  "hypothesis": "Notable Stellar Phenomena / mollusc-bearing site",
  "score": 0.0,
  "calibrated_probability": 0.0,
  "uncertainty": "high|medium|low",
  "evidence": ["ring composition", "nearby spatial analogue"],
  "data_coverage": {"scan_completeness": "partial", "sources": ["EDSM"]},
  "verification": "FSS system scan; inspect concentrated signal sources; approach parent ring/Lagrange point"
}
```

Probability must refer to a precisely defined event, e.g. “a detectable NSP in
this system under full FSS scan,” and the model version/training cut-off must be
included in actual output.
