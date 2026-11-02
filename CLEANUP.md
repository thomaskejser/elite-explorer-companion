# What must never be deleted

Files and tables that look disposable and are not.
`README.md` (*The databases*) says which database files exist and which can be rebuilt.

- `elite_mapping.duckdb` and `elite_mapping_current.duckdb`.
- `staging.pred_snapshot_<date>` + `staging.scanned_before_<date>` (20260829 and 20260925) — **not regenerable, despite the `pred_*` prefix.**
  They record what `system_predicted` said and which systems had body data before a refresh, the only out-of-sample test this model has (`scripts/score_predictions.py`).
  A snapshot of a past state cannot be recomputed from the present one, so treat them like the app-state database.
- `staging.pred_baseline_20261021` — **not regenerable.**
  The predictions of the all-scans rate fit, kept to score it against the explored-boxel refit on later reveals.
  Every `pred_snapshot_*` feeds `etl/prediction_outcome`; this one is deliberately named otherwise, so it does not.
- `staging.catalog_parallax` — no script creates it, and `etl/system_unfound/refresh.py` reads it.
- `staging` tables whose comment begins `RAW SOURCE` — each costs hours of re-download and re-parse; `--clean-staging` keeps them.
- `staging.ingest_manifest` — every download's source URL, bytes, row count, role and timestamp, so provenance survives the raw files, which are deleted once staged.
- `input/*.parquet` — hand-curated authoritative inputs: `poi`, `region`, `body`, `exobio_species`, `system_catalog`, `system_catalog_alias`.
  They are hand-edited and never regenerated: the `seed.py` that first wrote one refuses to overwrite it, and there is no `--force`.
  `input/route.parquet` is the route `etl/route/load.py` reads, written by `python -m common.neutron_route`.
  `input/commander_alias.parquet` is this commander's own and is backed up with `elite_mapping_current.duckdb`.
