# Elite Mapping research notebook

The evidence base and working pipeline for a database and prediction engine for rare Elite Dangerous discoveries.
It separates _observations_ (what commanders and game telemetry have reported) from _inference_ (which unexplored systems are promising candidates).
The research notes (`01-`…`04-*.md`) are a snapshot taken on 2026-07-10.

## Files

| File | Purpose |
| --- | --- |
| `01-data-sources.md` | Source inventory, access paths, coverage and reliability. |
| `02-rare-discoverables.md` | Taxonomy of phenomena worth modelling. |
| `03-prediction-engine-design.md` | Proposed schema, features, labels and validation plan. |
| `04-dataset-overlap-and-lineage.md` | Validated source lineage and EDAstro overlap analysis. |
| `RECOMMENDATIONS.md` | Curated, evidence-checked exploration recommendations (vetted conclusions only). |
| `lore/RAXXLA.md` | Running investigation log for the hunt for Raxxla (search-space narrowing, never a claimed find). |
| `lore/RAXXLA_LORE.md` | Compiled Raxxla lore and clues, with per-clue interpretation and key system coordinates. |
| `DEAD_ENDS.md` | Investigations that did not yield a predictor (e.g. Green Gas Giants), with reasons. |
| `CLEANUP.md` | Reclaimable large artifacts, and what blocks deleting each one. |
| `ETL.md` | **Authoritative** ETL conventions: the two databases, one folder per table, build vs load, merge-never-drop, schema files. Read it before touching `etl/`. |
| `schema/` | One `<table>.sql` per table — DDL and `COMMENT ON` in the same file, for both databases. |
| `etl/` | One folder per table, holding its `stage.py` / `load.py` / `refresh.py` and `.sql` files. `refresh.py` is the command to run. |
| `common/` | Shared plumbing: `db.py` (model), `current.py` (app state). |
| `scripts/` | Tooling: `build_fresh_db.py`, `check_sql.py`, `create_current_db.py`, `refine_rare_rates.py`, `score_predictions.py`. |
| `overlay/` | The overlay, one Rust binary (`ed-overlay.exe`, started by `overlay.cmd` / `overlay.sh`): a sector-ranked rare-object HUD on the left screen edge that writes to `elite_mapping_current.duckdb`. See `overlay/README.md` and `overlay/DESIGN.md`. |
| `input/unmigrated/` | Flight-history JSON, kept because it is not reproducible. Three stores have no table — `observations.jsonl` (calibration-loop input), `outcomes.json`, `carrier_gone.json`. Nothing reads them; see `CLEANUP.md`. |
| `sources.md` | Clickable source register and date-sensitive caveats. |

## The two databases

| File | What it is | Written by |
| --- | --- | --- |
| `elite_mapping.duckdb` | **The model** — what the galaxy is, merged from Spansh/EDSM/EDAstro/Canonn. `main` = model tables, `staging` = raw downloads, `transform` = each load's reshaped input. | `etl/` |
| `elite_mapping_current.duckdb` | **App state** — what *this commander* has seen, visited and found (`main`), plus `model`, a mirror of the model tables the overlay reads. | the overlay and `etl/route/load.py` (`main`); `etl/refresh_current.py` (`model`) |

- **The overlay writes to `elite_mapping_current.duckdb` and to nothing else.**
- The overlay never opens the model: it reads the mirror, packed into the binary by `overlay/bundle.py` and attached `READ_ONLY`.
- The model is derived and fully rebuildable, so anything written into it would be erased by the next merge.
- The full rationale is in `ETL.md` §0.

## Scope and constraints

- The game exposes no complete public catalogue of every generated system and no server API for undiscovered bodies.
  Community datasets are therefore a large, biased sample of player-observed space.
- The prediction engine ranks candidate systems and bodies and quantifies uncertainty; it cannot establish that a phenomenon exists until an in-game scan confirms it.
- Target the **Live 4.0 galaxy** unless Legacy is intentionally modelled as a separate universe.
  The two diverged after Update 14, and most community ingestion prioritises Live.
