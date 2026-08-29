# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A DuckDB data warehouse plus prediction engine for rare Elite Dangerous discoveries
(black holes, Wolf-Rayets, Herbig Ae/Be, supergiants, notable phenomena), and a live
in-game HUD (`app/`) that routes the commander to candidates. Pure Python +
DuckDB SQL; no build system, no package manifest, no test suite.

**`ETL.md` is authoritative for anything touching data.** Read it before editing
`etl/`, `schema/` or `scripts/`. Every rule in it exists because breaking it cost real
work, and the file states the cost each time.

## Two databases, one direction of writes

| file | what | who writes |
|---|---|---|
| `elite_mapping_v2.duckdb` (~60 GiB, gitignored) | **the model** — the galaxy per Spansh/EDSM/EDAstro/Canonn. `main` = the model tables (one per `schema/*.sql`), `staging` = 54 raw ingests plus work tables | `etl/`, `scripts/ingest_sources.py` |
| `elite_mapping_v2_current.duckdb` (MBs) | **app state** — what *this commander* has seen, visited and found. **Not reproducible; back it up** | the overlay, `etl/load_system_*.py` |

The app reads the model and may never write it: `common/current.py:connect()` opens the
app-state file **by path** and `attach_model()` attaches the model `READ_ONLY`. The
model is derived and fully rebuildable, so anything written there would be erased by the
next merge.

**DuckDB allows one writer per file, and read-only readers still block writes.** Close
the overlay and any `duckdb` CLI before an ETL write, or the loader dies on a lock. The
overlay opens per operation (~175 ms) and closes again, precisely so loaders can run
mid-flight.

`ELITE_DB` selects the model file and is **read at import time** of `common.db` —
setting `os.environ` after importing it silently targets the previous database.

## Layout

- `etl/` — one `build_<table>.py` / `load_<table>.py` per table, table name exact. A
  script never creates two tables. Loaded tables: `build_` seeds
  `input/<table>.parquet` once and refuses to overwrite it (that file is authoritative
  and hand-edited; there is no `--force`), `load_` merges it in. Derived tables:
  `build_` only, no `input/` file, no loader.
- `schema/<table>.sql` — DDL **and** all `COMMENT ON` text for that table, in one file
  so a schema change cannot drift from its documentation. Serves both databases;
  `common/current.py:CURRENT_TABLES` is the only thing saying which table belongs to
  which database.
- `common/` — shared plumbing, imported never copied: `db.py` (model: `connect`,
  `staged`, `report_merge`, `apply_comment_file`), `current.py` (app state),
  `poi_link.py` (the single decision of system-level vs body-level POI, so two builders
  cannot disagree).
- `scripts/` — `ingest_sources.py` (download → staging, every feed),
  `parse_spansh.py` (streams the 114 GB gzip, resumable, never decompressed to disk),
  `create_current_db.py`, `refine_rare_rates.py` (measures estimators, applies nothing).
- `app/` — the overlay. Strict module separation: `store.py` owns **all** SQL and
  returns display-ready strings, `table.py` places text and computes nothing,
  `theme.py` owns every colour and width. `app/README.md` records every design
  decision and what it replaced — read it before changing behaviour.
- `input/unmigrated/` — 15 JSON stores of flight history. **Three** are reproducible
  from nothing and still have no table (`observations.jsonl` is the calibration-loop
  input), so the directory stays until they have loaders. `wrong.json` left that set
  when `system_wrong` was created. Read only by the three `load_` scripts that migrate
  it, via `common.current.STORES` — which points HERE and deliberately not at `app/`,
  now that `app/` is the overlay package.

## Data rules that bite

- **Merge, never drop.** No `CREATE OR REPLACE TABLE`, `DROP` or truncate-and-reload on
  a `main` table. Match on the **natural key**, never the surrogate; insert unseen rows,
  update matched ones, leave absent rows in place and report them; never renumber a
  surrogate id. **Two** tables are documented exceptions and delete: `system_predicted`
  (a stale prediction is a wrong row, not a retired key) and `system_catalog_alias` (a
  retracted cross-ID actively corrupts `system_catalog.system_id` by merging two stars,
  so a hand-edited input file must be able to take an assertion back). Everything that
  *records* never deletes.
- `staging` tolerates `CREATE OR REPLACE` **only** for work tables. Tables whose comment
  begins `RAW SOURCE` cost hours of re-download and re-parse. Do not run
  `build_system_known.py --clean-staging` — it drops the schema indiscriminately.
- **The schema is created with the database and never altered.** DuckDB has no
  `ALTER TABLE ADD CONSTRAINT`, so a column or foreign key added after creation can
  never be enforced. To change a table's shape, edit `schema/<table>.sql` and build a
  new database. Builders neither migrate nor check — the file is the master data.
- Compare with `IS DISTINCT FROM`, not `<>`, or a NULL column silently skips its own
  backfill. **Round anything derived from a float aggregate** before storing it:
  `preserve_insertion_order=false` varies the summation order, so an unrounded value
  reports millions of spurious updates on the next run.
- **Never derive a system name by concatenating sector.** Only `sector_id = 0` means the
  name stands alone; `sector.is_crafted` is TRUE for 424 genuinely named sectors. Join
  through `system_known.id64` / `staging.sys_bridge`. Both mistakes were made here and
  both manufactured multi-million-row phantom gaps.
- **Provenance is the expensive class of error in this project.** Staging tables are
  named after the *download*, so a 7-day slice can never be misread as a catalogue:
  never fit a rate or quote a census from a `*7days` / `*_1day` table, and never quote a
  `spansh_body` count as a galaxy total (only 38.6% of systems have body data, and no
  source carries a DSS/mapped flag). Every table and column carries a `COMMENT ON`
  saying what it is, where it came from, and what it must **not** be used for. Nothing
  enforces this — the only automated check is inside `etl/build_system_all.py`, and it
  covers that one view — so the bar is held by review.

## Commands

```bash
# Overlay (reads app state + model; --sector forces one, otherwise it follows the journal)
python -m app.main
python -m app.main --chrome --sector "Eol Prou" --no-hotkeys

# Ingest: download -> staging
python scripts/ingest_sources.py --list                       # what is staged, how old
python scripts/ingest_sources.py --incremental                # all feeds, delta
python scripts/ingest_sources.py --full --only spansh_galaxy  # complete catalogue

# Merge: staging -> main. Loaded tables build then load; derived tables build only.
python etl/build_body.py && python etl/load_body.py
python etl/build_sector.py
python etl/build_system_known.py --limit 1000                 # smoke-test first
python etl/build_system_known.py --all
python etl/build_system_body.py --all                         # 570M rows, resumable
python etl/build_system_predicted.py --build
python etl/build_system_phenomenon.py --build

# Real star catalogues (the only NETWORK builders; order matters, aliases first)
python etl/load_system_catalog_alias.py       # 1.03M "same star" cross-IDs
python etl/load_system_catalog.py             # name match, then walks the aliases

# POI links: dimension first, then each owning table's builder under --poi
python etl/build_poi.py && python etl/load_poi.py
python etl/build_system_known.py --poi
python etl/build_system_body.py --poi
python etl/load_poi.py

# App-state database, once
python scripts/create_current_db.py [--show]

# Point any script at another model file
ELITE_DB=C:/Source/elite_mapping/elite_mapping_v2.duckdb python etl/build_poi.py
```

**The big loads bucket and resume: re-run the identical command to continue.** Finished
buckets are no-ops thanks to the `NOT EXISTS` guard. Do not clean staging first and do
not pass `--rebuild-staging` — `staging.src_body` alone costs a 569.7M × 197.6M join to
rebuild. To see how far a load got, count rows per bucket (`system_body` on
`system_id % 128`, `system_known` on `hash(name) % 64`), not the total.

## Verification, in place of tests

There is no test suite. A change is checked by:

1. **`report_merge` output** — `inserted / updated / orphaned`. A no-op run must *look*
   like a no-op; spurious updates mean a float or `<>` bug, not success.
2. **Re-querying the database** for every number before publishing it.
   `RECOMMENDATIONS.md` (vetted conclusions only, each with a confidence grade and the
   check behind it) and `DEAD_ENDS.md` (targets ruled out, with the reason) both require
   this — never transcribe a figure from chat output into either.
3. **`--limit N`** on the big builders before committing to `--all`.

## Docs map

`ETL.md` conventions (authoritative) · `README.md` orientation and the database split ·
`app/README.md` overlay design decisions and what each replaced ·
`RECOMMENDATIONS.md` vetted findings · `DEAD_ENDS.md` negative results ·
`RAXXLA.md` / `RAXXLA_LORE.md` the Raxxla search log (n = 0, so search-space narrowing
only, never a claimed find) · `CLEANUP.md` reclaimable artifacts and what blocks
deleting them · `01-`…`04-*.md` the original research notebook · `sources.md` source
register with date-sensitive caveats.

**There is no script that builds a fresh model database**, so the "edit
`schema/<table>.sql` and build a new database" workflow needs one written first: create
every table from its schema file in dependency order, then `INSERT ... SELECT` across.
Budget for it — the copy itself is fast (570M rows in ~134s), constraint maintenance is
not (the same table takes 738s with a primary key). A brand-new table that nothing points
AT needs none of this: its loader's `apply_comment_file()` creates it.
