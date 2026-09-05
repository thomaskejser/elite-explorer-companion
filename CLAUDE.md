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
| `elite_mapping_v2.duckdb` (~60 GiB, gitignored) | **the model** — the galaxy per Spansh/EDSM/EDAstro/Canonn. `main` = the model tables (one per `schema/*.sql`), `staging` = the provider ingests (62 tables, 23 of them `RAW SOURCE`, read through 19 views) plus the builders' work tables | `etl/`, `scripts/ingest_sources.py` |
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

- `etl/` — one folder per table, named for the table exactly, holding that table's
  `build.py` and `load.py`. A script never creates two tables. Loaded tables:
  `build.py` seeds `input/<table>.parquet` once and refuses to overwrite it (that file
  is authoritative and hand-edited; there is no `--force`), `load.py` merges it in.
  Derived tables: `build.py` only, no `input/` file, no loader.
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
  `create_current_db.py`, `refine_rare_rates.py` (measures estimators, applies nothing),
  `score_predictions.py` (scores a pre-refresh snapshot of `system_predicted` against
  what the delta revealed — the only out-of-sample test the model has).
- `app/` — the overlay. **The database runs on its own thread** (`dbworker.py`): Tk is
  single-threaded, so a query froze the HUD for as long as it ran. The worker's
  vocabulary is `database.py`'s public method names and nothing else; which datasets a
  view needs stays in `main.py:_read_asks()`. One thread owns the connection and
  `Database._connection()` asserts it; every read returns dicts from `Database._rows()`,
  the one place a cursor becomes Python. Strict module separation: `kinds.py` owns the
  vocabulary (one
  row per predictable object, carrying every name it goes by — the frozen key stored in
  `system_confirmed.kind`, the column, the one on-screen abbreviation), `database.py` owns
  **all** SQL and returns display-ready strings, `table.py` places text and computes
  nothing, `theme.py` owns every colour, width and column order and asserts its column
  list covers the same kinds. `app/README.md` records the design
  decisions behind the overlay — read it before changing behaviour.
- `input/unmigrated/` — 8 JSON stores of flight history. **Three** cannot be reproduced
  from anything and still have no table (`observations.jsonl` is the calibration-loop
  input), so the directory stays until they have loaders. Nothing in the tree reads any
  of them.

## Data rules that bite

- **Merge, never drop.** No `CREATE OR REPLACE TABLE`, `DROP` or truncate-and-reload on
  a `main` table. Match on the **natural key**, never the surrogate; insert unseen rows,
  update matched ones, leave absent rows in place and report them; never renumber a
  surrogate id. **Three** tables are documented exceptions and delete: `system_predicted`
  (a stale prediction is a wrong row, not a retired key), `system_catalog_alias` (a
  retracted cross-ID actively corrupts `system_catalog.system_id` by merging two stars,
  so a hand-edited input file must be able to take an assertion back) and
  `system_unfound` (a star that turns out to be findable was never unfound). Everything
  that *records* never deletes.
- `staging` tolerates `CREATE OR REPLACE` **only** for work tables. Tables whose comment
  begins `RAW SOURCE` cost hours of re-download and re-parse, so `--clean-staging`
  keeps those and truncates only the work tables. `--include-raw` is the flag that
  destroys them.
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
  enforces this — the only automated check is in `scripts/apply_schema.py`, and it
  covers views only — so the bar is held by review.

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
python etl/body/build.py && python etl/body/load.py
python etl/sector/build.py
python etl/system_known/build.py --limit 1000                 # smoke-test first
python etl/system_known/build.py --all
python etl/system_body/build.py --all                         # 577.6M rows, resumable
python etl/system_predicted/build.py --build
python etl/system_phenomenon/build.py --build
python etl/system_unfound/build.py                            # catalogued stars no game system matches
python scripts/apply_schema.py system_all                     # the main.system_all view

# Real star catalogues (the only NETWORK builders; order matters, aliases first)
python etl/system_catalog_alias/load.py       # 1.14M "same star" cross-IDs
python etl/system_catalog/load.py             # name match, then walks the aliases

# POI links: dimension first, then each owning table's builder under --poi
python etl/poi/build.py && python etl/poi/load.py
python etl/system_known/build.py --poi
python etl/system_body/build.py --poi
python etl/poi/load.py
python etl/system_poi/build.py                # materialise the union the overlay reads

# Overlay latency: snapshots of a join, re-run after their source loads
python etl/carrier_position/build.py          # after etl/carrier/build.py
python etl/system_poi/build.py                # after either --poi pass

# App-state database, once
python scripts/create_current_db.py [--show]

# Point any script at another model file
ELITE_DB=C:/Source/elite_mapping/elite_mapping_v2.duckdb python etl/poi/build.py
```

**The big loads bucket and resume: re-run the identical command to continue.** Finished
buckets are no-ops thanks to the `NOT EXISTS` guard. Do not clean staging first and do
not pass `--rebuild-staging` — `staging.src_body` alone costs a 569.7M × 200.7M join to
rebuild. To see how far a load got, count rows per bucket (`system_body` on
`system_id % 128`, `system_known` on `hash(name) % 64`), not the total.

## Comments describe the code as it is

**Keep them to one or two succinct sentences, or write none.** Prefer no comment;
anything longer than two sentences belongs in the relevant `.md` file instead.

**`ETL.md` §5 is the rule and it applies to every file here** — `#`, docstrings and
`COMMENT ON` alike. A comment states what the code does *now*; git holds the history.
Never write what a line used to be, what it replaced, what an earlier version got wrong,
or when a column was added. Two things that look like history and are not, so keep them:
a constraint stated as a prohibition ("MUST NOT BE `Palette.key`") and a measurement
that is still the live reason, phrased in the present tense. Say each thing once — a
paragraph restating its own point, or a sentence left half-finished by an edit, is a
defect like any other. When behaviour changes, **rewrite** the comment rather than
appending the correction to it.

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
`app/README.md` overlay design decisions ·
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
