# Elite Mapping research notebook

Research snapshot: 2026-07-10.  This folder is the initial evidence base for
building a database and prediction engine for rare Elite Dangerous discoveries.
It deliberately separates _observations_ (what commanders/game telemetry have
reported) from _inference_ (which unexplored systems are promising candidates).

## Files

| File | Purpose |
| --- | --- |
| `01-data-sources.md` | Source inventory, access paths, coverage and reliability. |
| `02-rare-discoverables.md` | Taxonomy of phenomena worth modelling. |
| `03-prediction-engine-design.md` | Proposed schema, features, labels and validation plan. |
| `04-dataset-overlap-and-lineage.md` | Validated source lineage and EDAstro overlap analysis. |
| `RECOMMENDATIONS.md` | Curated, evidence-checked exploration recommendations (vetted conclusions only). |
| `RAXXLA.md` | Running investigation log for the hunt for Raxxla (search-space narrowing, never a claimed find). |
| `RAXXLA_LORE.md` | Compiled Raxxla lore/clues with per-clue interpretation and key system coordinates. |
| `DEAD_ENDS.md` | Investigations that did not yield a predictor (e.g. Green Gas Giants), with reasons. |
| `CLEANUP.md` | Reclaimable large artifacts (e.g. the 114GB Spansh dump). |
| `scripts/` | Ingestion, normalization, and the black-hole/Wolf-Rayet prediction pipeline (03a–03v). |
| `app/` | In-game HUD router (`ed_bh_overlay.py`): recomputes a route through nearby undiscovered BH/WR candidates on every jump, copies a row to the clipboard when you press its function key, and retires targets you've visited. `ed_router.py` is the same engine in the terminal. |
| `sources.md` | Clickable source register and date-sensitive caveats. |

## Scope and important constraint

The game does not expose a complete public catalogue of every generated system
or a server API for undiscovered bodies.  Community datasets are therefore a
large, biased sample of player-observed space.  A prediction engine should rank
candidate systems/bodies and quantify uncertainty; it cannot establish that a
phenomenon exists until an in-game scan confirms it.

Target the **Live 4.0 galaxy** unless Legacy is intentionally modelled as a
separate universe.  The two diverged after Update 14, and most current
community ingestion prioritises Live.
