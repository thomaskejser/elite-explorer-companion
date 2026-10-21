# Disk cleanup notes

Large and regenerable artifacts, and what each one needs before it can go.
Nothing here is deleted automatically; this is a checklist for a manual sweep.

## The databases

| Path | Approx size | Status |
| --- | --- | --- |
| `elite_mapping.duckdb` | ~90.9 GiB | **Keep.** The model. `main` = the model tables, `staging` = 48 ingest and work tables, 35 of them `RAW SOURCE`, read through 15 views. Self-sufficient: every `etl/` builder runs against it. |
| `elite_mapping_current.duckdb` | MBs | **Keep, and back it up.** App state: what this commander has seen, visited and found, and the only database the overlay writes to. It is the one thing here that is not reproducible: losing the model costs a re-ingest, losing this costs every hour spent flying. |
| `elite_mapping_pre_fresh.duckdb` | ~139.9 GiB | The previous model file, kept by `scripts/build_fresh_db.py --swap` as the fallback. Safe to delete once the swapped-in model is trusted; the single biggest reclaimable item. |

## `input/unmigrated/` — flight history with no table

Eight JSON stores of flight history, tracked in git.
Three cannot be reproduced from anything and have no table — they are records of flying, not derived data, and they are the reason the directory exists:

| Store | Rows | What it is |
| --- | ---: | --- |
| `observations.jsonl` | 3,358 | Append-only prediction-vs-reality log — the input to the p = L×S×R calibration loop |
| `outcomes.json` | 2,037 | Per-system verdicts: 3 hit / 586 miss / 1,448 partial |
| `carrier_gone.json` | 3 | Carrier callsigns no longer at their recorded system |

- **Do not delete the directory until those three have tables.**
- The other five (`calibration.json`, `candidates_meta.json`, `carriers_meta.json`, `class_rates.json`, `region_names.json`) are kept only as belt-and-braces.

## Large files that can be reclaimed

| Path | Approx size | Safe to delete once… | Notes |
| --- | --- | --- | --- |
| `raw/spansh_galaxy.json.gz` | ~114 GB | ✅ parsed into `staging.spansh_galaxy_body` (569,697,301 rows) + `staging.spansh_galaxy_system` (194,696,927 rows) | **Keep for now** (user request), but safe to delete anytime. `python etl/system_known/refresh.py --window full` re-downloads the dump, as `galaxy.json.gz`. |
| `raw/galaxy_1month.json.gz` | ~5.6 GB | staged and merged | The Spansh 1-month window; re-downloadable. |
| `raw/incr/*` | ~7.9 GB | staged and merged | Incremental slices (1-day / 7-day); re-downloadable. |
| `raw/edsm_star_system.json.gz` | ~3.6 GB | ingested | Re-downloadable. |
| other `raw/*.json*` | small | ingested | 7-day windows, all re-downloadable. |

- `staging.ingest_manifest` records every download (source URL, bytes, row count, role, timestamp, staging table), so provenance survives deleting the raw files.
- Deleting them costs only the ability to re-parse without re-downloading.

## Regenerable derived artifacts

- `staging` work tables (`poi_body`, `poi_body_merge`, `poi_event`, `poi_rarity`, `poi_sys`, `primary_star`, `sys_value`) are recreated by their builders and free to drop.
  `scripts/build_fresh_db.py` does not copy them into a new file.
- `staging.canonn_codex` (4.7M rows), `staging.edsm_codex` (15.8M) and `staging.edastro_gec_combined` (2,749) are superseded and nothing reads them.
  `region` and `poi` stage the same three downloads under their role names (`canonn_codex_event`, `edsm_codex_entry`, `edastro_point_of_interest`), and those copies are newer.
  They are `RAW SOURCE`, so `--clean-staging` keeps them, but `python etl/poi/refresh.py` re-downloads them.

## Do not delete

- `elite_mapping.duckdb` and `elite_mapping_current.duckdb`.
- `staging.pred_snapshot_<date>` + `staging.scanned_before_<date>` (20260829 and 20260925) — **not regenerable, despite the `pred_*` prefix.**
  They record what `system_predicted` said and which systems had body data before a refresh, the only out-of-sample test this model has (`scripts/score_predictions.py`).
  A snapshot of a past state cannot be recomputed from the present one, so treat them like the app-state database.
- `staging.pred_baseline_20261021` — **not regenerable.**
  The predictions of the all-scans rate fit, kept to score it against the explored-boxel refit on later reveals.
  Every `pred_snapshot_*` feeds `etl/prediction_outcome`; this one is deliberately named otherwise, so it does not.
- `staging.catalog_parallax` — no script creates it, and `etl/system_unfound/refresh.py` reads it.
- `input/unmigrated/*.json` — flight history nothing reads; three stores still have no table (above) and the rest are belt-and-braces on data no re-ingest can reproduce.
- `input/*.parquet` — hand-curated authoritative inputs: `poi`, `region`, `body`, `system_catalog`, `system_catalog_alias`.
  They are hand-edited and never regenerated: the `seed.py` that first wrote one refuses to overwrite it, and there is no `--force`.
  `input/route.parquet` is the route `etl/route/load.py` reads, written by `python -m common.neutron_route`.
- `schema/`, `common/`, `etl/`, `scripts/`, `overlay/` — the code.
- `*.md` research notes and `sources.md`.
