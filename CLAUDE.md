# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A DuckDB data warehouse plus prediction engine for rare Elite Dangerous discoveries (black holes, Wolf-Rayets, Herbig Ae/Be, supergiants, notable phenomena), and a live in-game HUD (`overlay/`, Rust) that routes the commander to candidates.
The data side is pure Python + DuckDB SQL with no build system, no package manifest and no test suite; the overlay is a Cargo project.

**`ETL.md` is authoritative for anything touching data.**
Read it before editing `etl/`, `schema/` or `scripts/`.
Every rule in it exists because breaking it cost real work, and the file states the cost each time.

## Two databases, one direction of writes

| file | what | who writes |
|---|---|---|
| `elite_mapping.duckdb` (**90.9 GiB**, gitignored) | **the model** — the galaxy per Spansh/EDSM/EDAstro/Canonn. `main` = the model tables (one per `schema/*.sql`), `staging` = the provider downloads (48 tables, 35 of them `RAW SOURCE`, read through 15 role views) plus the loaders' work tables, `transform` = each load's reshaped input | `etl/` |
| `elite_mapping_current.duckdb` (~700 MB) | `main` = **app state** — what *this commander* has seen, visited and found, **not reproducible, back it up**. `model` = a **mirror** of the ten model tables the overlay reads, pure cache | the overlay writes `main`; `etl/refresh_current.py` rebuilds `model`, which `overlay/bundle.py` packs into the binary |

- **The model file never shrinks in place.**
  Dropping a table gives no byte back: DuckDB reuses freed blocks for later writes but has no `VACUUM` and does not truncate the file.
  Only writing a new file reclaims space — `scripts/build_fresh_db.py` does that (139.9 GiB became 75.2), and loads grow it again, so the size is not "how much data we hold".
- **The overlay never opens the model.**
  It reads the mirror `etl/refresh_current.py` puts in the app-state file's `model` schema, as packed into `ed-overlay.exe` by `overlay/bundle.py`, and attaches only the app-state file, so the model can be re-merged while the HUD is flying.
- **DuckDB allows one writer per file, and any other handle blocks it** — a READ-ONLY attach from a second process fails too.
  "The model is free" means no handle at all, including a finished script whose process is still alive.
  Close any `duckdb` CLI before an ETL write; the overlay needs closing only for a write to the app-state file, which includes the mirror refresh.
- **The mirror is a cache**, dropped and rebuilt whole on each refresh, so merge-never-drop does not reach it and nothing may be written there.
  It goes stale silently: after any load touching a mirrored table, re-run `python etl/refresh_current.py`, then rebuild the overlay so the binary carries it.
  `common/current.py` lists the mirrored tables in `MODEL_TABLES`, `DERIVED_TABLES` and `PROBE_TABLE`.
- `system_neutron` exists only in the mirror, derived from `system_known` at refresh time; `schema/system_neutron.sql` must stay even though the model has no such table.
- `ELITE_DB` selects the model file and is **read at import time** of `common.db`: setting `os.environ` after importing it silently targets the previous database.

## Layout

- `etl/` — one folder per table, named for the table exactly, holding `stage.py` (download → `staging`), `load.py` (`staging`/`transform` → `MERGE INTO main`), `refresh.py` (both on one connection — the command a person runs) and the table's `.sql` files.
  A script never writes two model tables.
  A derived table has no `stage.py`.
  A hand-edited `input/<table>.parquet` is staged like a download; the `seed.py` that first wrote it refuses to overwrite it (there is no `--force`).
- `schema/<table>.sql` — DDL **and** all `COMMENT ON` text for that table in one file, so a schema change cannot drift from its documentation.
  It serves both databases; `common/current.py:CURRENT_TABLES` is the only thing saying which table belongs to which database.
- `common/` — shared plumbing, imported never copied:
  - `db.py` — model: `connect`, `staged`, `report_merge`, `apply_comment_file`.
  - `current.py` — app state.
  - `poi_link.py` — the single decision of system-level vs body-level POI, so two builders cannot disagree.
  - `neutron_route.py` — fewest-jump neutron routing: primes from the app-state neutron mirror, solves in memory, writes `input/route.parquet`.
    It is the only runnable module here, because a solver with no way to run it is a library nobody calls.
- `scripts/`:
  - `build_fresh_db.py` writes a new model file from `schema/*.sql` and copies every table across in resumable, checksum-verified batches; `--swap` puts it in place and keeps the old file.
  - `check_sql.py`, `create_current_db.py`.
  - `refine_rare_rates.py` measures estimators and applies nothing.
  - `score_predictions.py` scores a pre-refresh snapshot of `system_predicted` against what the refresh revealed — the only out-of-sample test the model has.
  - `ingest_sources.py` and `parse_spansh.py` predate the self-contained loaders; no loader needs them.
- `overlay/` — the overlay in Rust, shipped as one self-contained `ed-overlay.exe` with the model mirror compiled in.
  `overlay/README.md` covers the build and where its state lives; `overlay/DESIGN.md` records the design decisions — read it before changing behaviour.
  - **The database runs on its own thread** (`dbworker.rs`), so a query never freezes the HUD.
  - `kinds.rs` owns the vocabulary: one row per predictable object, carrying every name it goes by — the frozen key stored in `system_confirmed.kind`, the column, the one on-screen abbreviation, and the arrival classes `etl/refresh_current.py` reads from it.
  - `database.rs` and `sql/*.sql` own **all** SQL and return display-ready strings.
  - `lights.rs` owns what the three VKB throttle LEDs mean (left: fuel; middle: the arrival star of the next jump; right: cargo scoop and shields); `win/vkb.rs` drives them.
  - `table.rs` places text and computes nothing; `theme.rs` owns every colour, width and column order.
- `log/` — every run's output.
  Each entry point calls `common/runlog.py:start()`, which tees stdout **and** stderr into `log/<folder>-<script>.log` while still printing to the terminal, so a run is logged whether or not anyone redirected it.
  One file per script, appended, rotated at 16 MB, gitignored.
  Do not redirect on top of it: `> foo.log` only makes a second copy somewhere worse.
- `input/unmigrated/` — 8 JSON stores of flight history.
  **Three** cannot be reproduced from anything and have no table (`observations.jsonl` is the calibration-loop input), so the directory stays until they have loaders.
  Nothing in the tree reads any of them.

## Data rules that bite

- **`system_known.system_id` is the game's id64**, derived by the `system_id()` macro, not a surrogate this project allocates.
  A negative value is ours — a hash of the name, for a system no feed gives an id64 for — exactly as `sector_id()` works.
  **Nothing in the database enforces it: no `PRIMARY KEY`, no unique index, no foreign keys anywhere.**
  A unique index over this table needs more memory than the machine can give a load, so the merge holds uniqueness — it matches on `system_id` and never inserts a present one — and every lookup by id is a scan.
  `(sector_id, system_in_sector)` is **not** unique.
- **`sector.sector_id` is the game's sector address**: the grid cell a procedural sector's systems encode in their id64 (`sector_id_from_id64()`), a negative name hash for a hand-authored sector, 0 only for the `'crafted'` sentinel.
  It is never renumbered: `etl/sector/load.sql` matches on the name, only inserts, and reports where EDAstro publishes a different cell (Juenae and Aucopp, where EDAstro is wrong).
- **`system_body` is keyed `(system_body, system_id, body_no)`**, unenforced like `system_known`, with no surrogate.
  `body_no` is the dump's `bodyId`; **`-1` means a real body whose index is unknown** (a catalogue hit, a Canonn POI body), and the loader writes the real index into that row when a feed supplies it rather than adding a second one.
- **Merge, never drop.**
  No `CREATE OR REPLACE TABLE`, `DROP` or truncate-and-reload on a `main` table.
  Match on the **natural key**, never the surrogate; insert unseen rows, update matched ones, leave absent rows in place and report them; never renumber a surrogate id.
  Everything that *records* never deletes.
  **Four** documented exceptions delete:

  | table | why it deletes |
  |---|---|
  | `system_predicted` | a stale prediction is a wrong row, not a retired key |
  | `system_catalog_alias` | a retracted cross-ID corrupts `system_catalog.system_id` by merging two stars, so a hand-edited input file must be able to take an assertion back |
  | `system_unfound` | a star that turns out to be findable was never unfound |
  | `route` | a hop number is an order, so a re-solved shorter chain must lose its old tail rather than keep offering waypoints it no longer passes |

- `staging` tolerates `CREATE OR REPLACE` **only** for work tables.
  Tables whose comment begins `RAW SOURCE` cost hours of re-download and re-parse, so `--clean-staging` keeps those and truncates only the work tables; `--include-raw` is the flag that destroys them.
- **The schema is created with the database and never altered.**
  DuckDB has no `ALTER TABLE ADD CONSTRAINT`, so a column or foreign key added after creation can never be enforced.
  To change a table's shape, edit `schema/<table>.sql` and build a new database (see the end of this file).
  Builders neither migrate nor check — the file is the master data.
- Compare with `IS DISTINCT FROM`, not `<>`, or a NULL column silently skips its own backfill.
- **Round anything derived from a float aggregate** before storing it: `preserve_insertion_order=false` varies the summation order, so an unrounded value reports millions of spurious updates on the next run.
- **Never derive a system name by concatenating sector.**
  Only `sector_id = 0` means the name stands alone; `sector.is_crafted` is TRUE for 424 genuinely named sectors.
  Join a dump's id64 to `system_known.system_id`, which is that id64.
  Either mistake manufactures multi-million-row phantom gaps.
- **Never key on a composed name**: 1,481 full names belong to more than one system.
- **Provenance is the expensive class of error in this project.**
  Staging tables are named after the *download*, so a 7-day slice can never be misread as a catalogue.
  Never fit a rate or quote a census from a `*7days` / `*_1day` table.
  Never quote a `spansh_body` count as a galaxy total: only 38.6% of systems have body data, and no source carries a DSS/mapped flag.
  Every table and column carries a `COMMENT ON` saying what it is, where it came from, and what it must **not** be used for.
  Only views are checked automatically (`scripts/apply_schema.py`), so the bar is held by review.

## Commands

```bash
# The overlay: pack the mirror, then build (re-run both after refresh_current.py), then
# start it against the app-state file (the start-overlay skill does this and checks it)
python overlay/bundle.py && (cd overlay && cargo build --release)
./overlay.sh                                                  # or overlay.cmd; any flag passes through
./overlay.sh --chrome --sector "Eol Prou" --no-hotkeys        # --sector forces one, else it follows the journal

# A full refresh is the refresh-data skill (.claude/skills/refresh-data/SKILL.md): it
# holds the order, the snapshot the scorer needs, and what each step must print.

# Every table: refresh.py downloads what it needs, stages it and merges it. Order matters
# where one table resolves against another.
python etl/sector/refresh.py                                  # FIRST: system_known resolves sectors by name
python etl/system_known/refresh.py                            # window from the gap; --window 1day|7days|1month|full
python etl/system_known/refresh.py --window 1month --only spansh,edastro
python etl/body/refresh.py
python etl/system_body/refresh.py --limit 1                   # one bucket only: the smoke test
python etl/system_body/refresh.py                             # reuses the Spansh window system_known merged
python etl/system_predicted/refresh.py --refresh-value        # after any system_body load
python etl/system_phenomenon/refresh.py
python etl/region/refresh.py
python etl/carrier/refresh.py && python etl/carrier_position/refresh.py
python etl/station_service/refresh.py                        # material traders + technology brokers

# POI links: dimension first, then each owning table's linker, then the counts and snapshot
python etl/poi/refresh.py
python etl/system_known/poi.py
python etl/system_body/poi.py                                 # INSERTS bodies a Canonn report proves exist
python etl/poi/load.py
python etl/system_poi/refresh.py

# Real star catalogues (aliases first: the catalogue walks them)
python etl/system_catalog_alias/refresh.py
python etl/system_catalog/refresh.py
python etl/system_unfound/refresh.py                          # needs staging.catalog_parallax, which no script creates
python scripts/apply_schema.py system_all                     # a VIEW, no loader
python scripts/apply_schema.py body_type_census               # a VIEW, no loader

# Score the model: needs staging.pred_snapshot_<date> + scanned_before_<date> taken BEFORE
python scripts/score_predictions.py

# Mirror the model tables the overlay reads into the app-state file. Re-run after any
# load touching one of them, then bundle.py and cargo build, or the overlay serves the
# previous galaxy. ~1 min.
python etl/refresh_current.py

# A new model file from schema/ (every table recreated, then copied and checksummed)
python scripts/build_fresh_db.py                              # resumable: re-run the same command
python scripts/build_fresh_db.py --swap                       # only after it reports verified

# App-state database, once; routes the overlay offers to follow
python scripts/create_current_db.py [--show]
python -m common.neutron_route --from Colonia --to "Shinrarta Dezhra" --range 500
python etl/route/load.py

# Point any script at another model file
ELITE_DB=C:/Source/elite_mapping/elite_mapping.duckdb python etl/poi/refresh.py
```

- **The big loads batch and resume: re-run the identical command to continue.**
  Every merge matches on the key, so a finished batch is a no-op the second time.
- `system_known` merges in sector-range batches cut at ~4,000,000 staged rows each (`ROWS_PER_BATCH`).
- `system_body` merges in buckets on `abs((system_id >> 3) % n)`: 8 for a delta, 128 for a catalogue-sized load (over 60,000,000 staged rows).
  Never bucket on `system_id % n`: its low three bits are the mass code, and those buckets take 35-294 s each.
- **After an interrupted `system_known` load, pass `--window` explicitly.**
  The automatic window reads `max(first_seen)`, which the merged batches moved forward, so it asks for a narrower dump than the gap and leaves a hole no later delta fills.

## Comments describe the code as it is

- **Write no code comments** — no `#`, no `--` in `.sql`, no docstrings; anything that needs explaining belongs in the relevant `.md` file.
  `ETL.md` §7 ("Write no comments") is the rule, and it applies to every file here.
- `COMMENT ON` is not a code comment and is required (`ETL.md` §8); the rules below apply to it and to every `.md`.
- A comment states what the code does *now*; git holds the history.
  Never write what a line used to be, what it replaced, what an earlier version got wrong, or when a column was added.
- Two things look like history and are not, so keep them: a constraint stated as a prohibition ("MUST NOT BE `Palette.key`"), and a measurement that is still the live reason, phrased in the present tense.
- Say each thing once: a paragraph restating its own point, or a sentence left half-finished by an edit, is a defect.
- When behaviour changes, **rewrite** the comment rather than appending the correction.

## Verification, in place of tests

There is no test suite.
A change is checked by:

0. **`python scripts/check_sql.py`** after editing any `.sql` file.
   It parses every file in `schema/` and `etl/` (160) with DuckDB's own parser and fails on any error.
   A parse failure in a `COMMENT ON` can land after the mirror's drop and before its write, emptying the entire app-state mirror.
1. **`report_merge` output** — `inserted / updated / orphaned`.
   A no-op run must *look* like a no-op; spurious updates mean a float or `<>` bug, not success.
2. **Re-querying the database** for every number before publishing it.
   `RECOMMENDATIONS.md` (vetted conclusions only, each with a confidence grade and the check behind it) and `DEAD_ENDS.md` (targets ruled out, with the reason) both require this — never transcribe a figure from chat output into either.
3. **`--limit 1`** on `etl/system_body/refresh.py` before the full run: it merges one bucket (of 8, or 128 for a catalogue-sized load) and skips the primary cascade.
4. **Run a changed loader twice.**
   The second run must report `0 inserted, 0 updated`; anything else is a float, `<>` or ordering bug in the merge, not new data.

## Changing a table's shape

**Edit `schema/<table>.sql` and run `scripts/build_fresh_db.py`.**
It creates every table from its schema file, copies the rows across in batches, checksums every column against the source, and only then allows `--swap`.

- A column the new schema drops must be named in its `DROPPED` map or the build refuses.
- A brand-new table that nothing points at needs none of this: its loader's `prepare_table()` creates it.

## Docs map

| file | what |
|---|---|
| `ETL.md` | conventions (authoritative) |
| `README.md` | orientation and the database split |
| `overlay/README.md` | overlay build, binary contents, where its state lives |
| `overlay/DESIGN.md` | overlay design decisions |
| `RECOMMENDATIONS.md` | vetted findings |
| `DEAD_ENDS.md` | negative results |
| `lore/RAXXLA.md`, `lore/RAXXLA_LORE.md` | the Raxxla search log (n = 0, so search-space narrowing only, never a claimed find) |
| `CLEANUP.md` | reclaimable artifacts and what blocks deleting them |
| `01-`…`04-*.md` | the original research notebook |
| `sources.md` | source register with date-sensitive caveats |
