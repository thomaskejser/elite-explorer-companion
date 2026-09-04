# Elite Mapping research notebook

Research snapshot: 2026-07-10; pipeline current as of 2026-08-21.  This folder is the
evidence base *and* the working pipeline for a database and prediction engine for rare
Elite Dangerous discoveries.
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
| `CLEANUP.md` | Reclaimable large artifacts, and what still blocks deleting each one. |
| `ETL.md` | **Authoritative** ETL conventions: the two databases, one-script-per-table, build vs load, merge-never-drop, schema files. Read this before touching `etl/`. |
| `schema/` | One `<table>.sql` per table — DDL **and** `COMMENT ON` in the same file, for both databases. |
| `etl/` | The v2 pipeline: one `build_<table>.py` / `load_<table>.py` per table. |
| `common/` | Shared plumbing: `db.py` (model), `current.py` (app state). |
| `scripts/` | Live tooling: `ingest_sources.py`, `parse_spansh.py`, `create_current_db.py`, `refine_rare_rates.py`, `score_predictions.py`. |
| `app/` | **The overlay.** Sector-ranked rare-object HUD, left screen edge, writes to `elite_mapping_v2_current.duckdb`. See `app/README.md`. |
| `input/unmigrated/` | Flight-history JSON, kept because it is **not reproducible**. Three still have no table — `observations.jsonl` (calibration-loop input), `outcomes.json`, `carrier_gone.json`; `wrong.json` has been migrated into `system_wrong`. Read only by the loaders that migrate them; see `CLEANUP.md`. |
| `sources.md` | Clickable source register and date-sensitive caveats. |

## The two databases

| File | What it is | Written by |
| --- | --- | --- |
| `elite_mapping_v2.duckdb` | **The model** — what the galaxy is, merged from Spansh/EDSM/EDAstro/Canonn. `main` = model tables, `staging` = raw ingests. | `etl/`, `scripts/ingest_sources.py` |
| `elite_mapping_v2_current.duckdb` | **App state** — what *this commander* has seen, visited and found. | the overlay, `etl/load_system_*.py` |


**The app writes to `elite_mapping_v2_current.duckdb` and to nothing else.** The model
is background information it reads; it is derived, fully rebuildable, and anything
written into it would be erased by the next merge. `common/current.py` enforces this by
attaching the model `READ_ONLY`. The full rationale is in `ETL.md` §0.

## Scope and important constraint

The game does not expose a complete public catalogue of every generated system
or a server API for undiscovered bodies.  Community datasets are therefore a
large, biased sample of player-observed space.  A prediction engine should rank
candidate systems/bodies and quantify uncertainty; it cannot establish that a
phenomenon exists until an in-game scan confirms it.

Target the **Live 4.0 galaxy** unless Legacy is intentionally modelled as a
separate universe.  The two diverged after Update 14, and most current
community ingestion prioritises Live.
