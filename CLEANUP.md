# Disk cleanup notes

Tracking large / regenerable artifacts so we can reclaim space later. Nothing here is
deleted automatically — this is a checklist for a manual sweep.

Last updated: 2026-09-04

## The two databases

| Path | Approx size | Status |
| --- | --- | --- |
| `elite_mapping_v2.duckdb` | ~60 GiB | **KEEP.** The model. `main` = the model tables, `staging` = 62 ingest and work tables, 23 of them `RAW SOURCE`, read through 19 views. Self-sufficient: every `etl/` builder runs against it. |
| `elite_mapping_v2_current.duckdb` | MBs | **KEEP — and back it up.** App state: what this commander has seen, visited and found. *The only database the app writes to.* It is the one thing here that is **not reproducible**: losing the model costs a re-ingest, losing this costs every hour actually spent flying. |

### `input/unmigrated/` — flight history with no table yet

Fifteen JSON stores written by an earlier build of the overlay, 2.2 MB, tracked in git.
**Three of them cannot be reproduced from anything AND still have no table** — they are records of flying, not
derived data, so nothing can regenerate them and they are the reason the directory exists:

| Store | Rows | What it is |
| --- | ---: | --- |
| `observations.jsonl` | 3,357 | Append-only prediction-vs-reality log — the input to the p = L×S×R calibration loop |
| `outcomes.json` | 2,037 | Per-system verdicts: 3 hit / 586 miss / 1,448 partial |
| `carrier_gone.json` | 3 | Carrier callsigns no longer at their recorded system |

`wrong.json` (12 systems established not to exist) was the fourth. It now has a table --
`system_wrong` in the app-state database, written by the overlay on SHIFT+BACKSPACE --
and all 12 rows are migrated, so it is belt-and-braces like the other eleven.

**Do not delete the directory until the remaining three have tables.** The other eleven
(`starclass.json`, `starpos.json`, `visited.json`, `confirmed.json`, `nsp_seen.json`,
`poi_seen.json`, `calibration.json`, `class_rates.json`, `region_names.json`, the two
`*_meta.json`) are already in `elite_mapping_v2_current.duckdb` (17,156 seen /
3,428 visited / 734 poi_visited **as of 2026-08-29**; these grow every session and are
not re-counted here, because the overlay holds that database while flying) and are kept
only as belt-and-braces.

## Large files that can be reclaimed

| Path | Approx size | Safe to delete once… | Notes |
| --- | --- | --- | --- |
| `raw/spansh_galaxy.json.gz` | ~114 GB | ✅ parsed into `staging.spansh_galaxy_body` (569,697,301 rows) + `staging.spansh_galaxy_system` (194,696,927 rows) | **KEEP for now** (user request), but safe to delete anytime. Re-downloadable via `python scripts/ingest_sources.py --full --only spansh_galaxy`. Single biggest reclaimable item. |
| `raw/incr/*` | ~2.4 GB | staged and merged | Incremental slices (1-day / 7-day). Re-downloadable with `--incremental`. |
| `raw/edsm_star_system.json.gz` | ~3.6 GB | ingested | Re-downloadable. |
| other `raw/*.json*` | small | ingested | 7-day windows, all re-downloadable. |

All downloads are recorded in `staging.ingest_manifest` (source URL, bytes, row count,
role, timestamp, staging table), so **provenance survives even if the raw files are
deleted**. Deleting them costs only the ability to re-parse without re-downloading.
`python scripts/ingest_sources.py --list` shows what is staged.

## Regenerable derived artifacts

- `raw/spansh_parse.checkpoint` — parser resume marker; delete only for a full
  re-parse from scratch.
- `staging.pred_*`, `staging.sys_bridge`, `staging.src_*`, `staging.sb_*`,
  `staging.poi_*`, `staging.ph_*` in v2 — builder work tables, recreated on each run.
  Free to drop **except the two snapshot tables below**, and `sys_bridge` (200.7M rows)
  is expensive to rebuild and is what `common/current.py:resolve_id64()` probes.
- `staging.pred_snapshot_20260829` + `staging.scanned_before_20260829` — **NOT
  regenerable, despite the `pred_*` prefix.** They record what `system_predicted` said
  and which systems had body data *before* a refresh, which is the only out-of-sample
  test this model has (`scripts/score_predictions.py`). A snapshot of a past state
  cannot be recomputed from the present one. Treat them like the app-state database.
- `staging.pred_hr_fit` — **orphaned, and unlike the rest of `pred_*` it will not come
  back.** It was the helium-rich gas giant fit; `p_hr` was removed from
  `etl/build_system_predicted.py`, so nothing recreates it and nothing reads it. Small,
  and safe to drop whenever the model is next open for writing.
- `system_predicted.p_hr` in the existing model database — the column itself is now an
  orphan for the same reason. It is not dropped in place (the schema is created with the
  database and never altered) and it is no longer in `schema/system_predicted.sql`, so
  it disappears when the database is next built from the schema files. Until then it
  holds whatever the last build wrote. **Nothing reads it.**

## Do NOT delete

- `elite_mapping_v2.duckdb` and `elite_mapping_v2_current.duckdb`.
- `input/unmigrated/*.json` — the flight history, and `elite_mapping_v2_current.duckdb`
  is authoritative over it: the overlay writes the database directly and reads none of
  these files. Kept because three of them still have no table (above) and the rest are
  belt-and-braces on data no re-ingest can reproduce.
- `input/*.parquet` — hand-curated authoritative inputs: `poi`, `region`, `body`,
  `system_catalog`, `system_catalog_alias`. Hand-edited and never regenerated — the
  `build_` seeder refuses to overwrite one and there is no `--force`.
- `schema/`, `common/`, `etl/`, `scripts/` — the code.
- `*.md` research notes and `sources.md`.
