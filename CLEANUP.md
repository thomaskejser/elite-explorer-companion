# Disk cleanup notes

Tracking large / regenerable artifacts so we can reclaim space later. Nothing
here is deleted automatically — this is a checklist for a manual sweep.

Last updated: 2026-07-12

## Large files that can be reclaimed

| Path | Approx size | Safe to delete once… | Notes |
| --- | --- | --- | --- |
| `raw/spansh_galaxy.json.gz` | ~114 GB | ✅ DONE — `spansh_body` (569,697,301 rows) + `spansh_system` (194,696,927 rows) populated & validated (0 dup IDs) 2026-07-12 | **KEEP for now** (user request), but now SAFE to delete anytime to reclaim 114 GB. Re-downloadable from https://downloads.spansh.co.uk/galaxy.json.gz (nightly → newer snapshot). Single biggest reclaimable item. |
| `raw/edsm_star_system.json.gz` | ~3.6 GB | ingested (already in DB) | Re-downloadable from EDSM nightly dumps. |
| `raw/edastro_planet.json.gz` | ~0.5 GB | ingested | 7-day rolling window; re-downloadable. |
| `raw/edsm_celestial_body.json.gz` | ~0.4 GB | ingested | 7-day window; re-downloadable. |
| `raw/edsm_codex_entry.json.gz` | ~0.37 GB | ingested | Re-downloadable. |
| `raw/canonn_codex_event.json.gz` | ~0.28 GB | ingested | Re-downloadable. |
| `raw/edastro_star.json.gz` | ~0.11 GB | ingested | 7-day window. |
| other `raw/*.json*` | small | ingested | — |

All `raw/*` files are raw provider snapshots recorded in the `ingest_manifest`
table (source URL, bytes, row count, timestamp), so provenance survives even if
the raw files are deleted. Deleting them only costs the ability to re-parse
without re-downloading.

## Regenerable derived artifacts

- `raw/spansh_parse.checkpoint` — parser resume marker; delete only if you want
  a full re-parse from scratch.
- `norm.*` views in the DB — defined by `scripts/01_normalize.sql`; free to drop
  and recreate.

## Do NOT delete

- `elite_mapping.duckdb` — the actual database (the point of all this).
- `scripts/` — ingestion/parsing/normalization code.
- `*.md` research notes and `sources.md` / `ingest_manifest`.
