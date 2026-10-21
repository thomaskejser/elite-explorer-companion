# ETL conventions

How data gets into the databases.
Each rule exists because breaking it has cost real work or would silently corrupt a key; the cost is stated with the rule.

## 0. Two databases

| file | what it is | who writes it | size |
|---|---|---|---|
| `elite_mapping.duckdb` | **the model**: the galaxy per Spansh/EDSM/EDAstro/Canonn. `main` holds the model, `staging` the downloaded sources, `transform` the reshaping between them. | `etl/` | ~91 GiB |
| `elite_mapping_current.duckdb` | **app state**: what *this commander* has seen, visited and found. Its `model` schema is a mirror of the model tables the overlay reads. | the overlay (`main`); `etl/refresh_current.py` (`model`); `etl/route/load.py` (`route`) | MBs |

- **The overlay writes to `elite_mapping_current.duckdb` and nothing else.**
  It never opens the model; it reads the mirror.
- **The model is derived**: every row is reproducible by re-running `etl/`.
- **The overlay runs while you fly**: it is a live HUD reacting to journal events.
- **A read-only attach is not a free pass.**
  DuckDB refuses to open a file another process holds (`Cannot open file ... being used by another process`), even with `ATTACH ... (READ_ONLY)`.
  "The model is free" means no handle at all, including a finished script whose process is still alive.
- **`ELITE_DB` points any script at another model file.**
  It is read at import time of `common/db.py`, so setting `os.environ` after importing that module silently targets the previous database.

```
ELITE_DB=C:/Source/elite_mapping/elite_mapping.duckdb python etl/region/refresh.py
```

## 1. One folder per table: `stage`, `load`, `refresh`

`etl/<table_name>/` is named for the exact DuckDB table and matches `schema/<table_name>.sql`.
The folder names the table, the file names the job.

| script | what it does |
|---|---|
| `stage.py` | Gets the source data, **including downloading it**, into one or more `staging` tables. |
| `load.py` | Merges what is in `staging` into `main`. |
| `refresh.py` | Calls `stage` then `load`. The one entry point a person runs. |

- **No script writes two model tables**; two tables means two folders.
- **Every script is self-contained.**
  `python etl/region/refresh.py` is the complete instruction: no prior step, no separate ingest command.
- **A derived table** (built only from other `main` tables) has no `stage.py`; its `load.py` is the whole job.
- `stage.py` and `load.py` each expose `stage(con)` / `load(con)` as well as `main()`, so `refresh.py` runs both on one connection instead of opening the model twice.
- Each script reaches the repo root with `sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))`.
  Three levels, because the script is two directories deep; get it wrong and `common/` does not import.

## 2. SQL lives in `.sql` files, not in Python strings

A script runs SQL with `common.db.run_sql_file(con, path)`, which returns the last statement's result.
Python sequences the steps and prints the report; the SQL can be read, diffed and run by hand.

| file | holds |
|---|---|
| `schema/<table>.sql` | DDL **and** `COMMENT ON` for a `main` table |
| `schema/staging/<table>.sql` | DDL **and** `COMMENT ON` for a `staging` table |
| `schema/transform/<table>.sql` | the definition **and** population of a `transform` table |
| `etl/<table>/load.sql` | the `MERGE INTO` that loads the table |
| `etl/<table>/counts.sql` | the `(inserted, updated)` counts for that merge, see §4 |
| `etl/<table>/orphans.sql` | rows in `main` the source no longer produces |
| `etl/<table>/skipped.sql` | rows the transform could not accept, and why |

- Paths resolve through `comment_file()`, `staging_file()` and `transform_file()` in `common/db.py`.
- Merge SQL sits in the table's folder, not `schema/`, because `schema/` holds definitions and a merge is not one.
- **A windowed source is the one exception and uses `${table}` placeholders.**
  A feed published at several widths stages into a table named after the download, so one definition would otherwise be copied per window with the same thirty column comments.
  `schema/staging/spansh_galaxy_system.sql` carries `${table}`, `${provenance}` and `${url}`, filled by `common.db.run_staging_template()`, so the window still shows in both the table name and its comment.

## 3. The three schemas

```
  the internet          etl/<table>/stage.py, via common.sources.download()
        |
        v
  staging.canonn_codex_event, staging.spansh_body, ...   as downloaded, unshaped
        |               schema/transform/<table>.sql
        v
  transform.region, ...                                  shaped to fit the target
        |               etl/<table>/load.sql -- MERGE INTO
        v
  main.region, main.system_known, ...                    the model
```

- **Nothing downloaded is written straight into a model table**, and nothing is reshaped inside the merge.
  Staging data that does not fit the target becomes a `transform` table with a file in `schema/transform/`, not a subquery in the merge or a temporary object between the two.
- **A `transform` table is where input validation belongs.**
  Declare the constraints the target needs (`NOT NULL`, `PRIMARY KEY`, `UNIQUE`, `CHECK`) so bad input fails before it reaches `main`; `schema/transform/region.sql` is the worked example.

| schema | may be dropped or replaced? |
|---|---|
| `main` | **No.** Merge only; four documented exceptions in §4. |
| `staging`, tables commented `RAW SOURCE` | **No.** Re-obtainable only by re-downloading and re-parsing, which takes hours. |
| `staging`, work tables | Yes. Intermediate state, `CREATE OR REPLACE`d freely. |
| `transform` | Always. Rebuilt from staging on every load and never edited. |

- `--clean-staging` on `etl/system_body/stage.py` keeps every table whose comment begins `RAW SOURCE` and `TRUNCATE`s the rest, so work tables come back empty rather than missing.
- `--include-raw` overrides that and takes 894M rows of irreplaceable source with it: the one flag here that costs hours of re-download.

## 4. Merge with `MERGE INTO`; never drop

One statement, from the staging or transform table directly to the target:

```sql
MERGE INTO main.region AS t
USING transform.region AS s ON t.region_id = s.region_id
WHEN MATCHED AND t.region IS DISTINCT FROM s.region THEN UPDATE SET region = s.region
WHEN NOT MATCHED THEN INSERT (region_id, region) VALUES (s.region_id, s.region);
```

- **Match on the natural key, never a surrogate id**: `(type, body)` for `body`, `(type, sub_type)` for a census, `sector` for `sector`.
  Where the game supplies the id, that id is the natural key (see *Derive the key* below).
- **Guard the update arm with `IS DISTINCT FROM`**, or every matched row counts as a change and a no-op run stops looking like one.
- **Count with a `counts.sql`, never with `RETURNING`.**
  `counts.sql` returns `(inserted, updated)` from predicates that mirror the merge's, run by `common.db.merge_counts()` before the merge.
  `MERGE ... RETURNING` fails on any table a foreign key points at, and only on the first run that actually changes something.
  The duplicated predicate is the cost; `report_merge` cross-checks the insert count against the row-count delta and warns when the two files drift.
- **No `WHEN NOT MATCHED BY SOURCE THEN DELETE`.**
  Rows absent from the source stay in place and are reported by `orphans.sql`; their keys are retired, never reused.
  Deleting one is a manual decision, because something may reference it.
- **Never renumber a surrogate id.**
  Allocate a new one as `max+1`; honour an id the source supplies when it is free, otherwise reassign.
- Report `inserted / updated / orphaned` through `common.db.report_merge`.
  **A no-op run must look like a no-op.**

### Derive the key, never allocate it

A surrogate `max+1` id is a last resort; the central tables have none.
Where the game names a thing, that name is the key:

| table | key | where it comes from |
|---|---|---|
| `region` | `region_id` | the game's region id, parsed out of the codex token |
| `sector` | `sector_id` | the grid cell its systems' id64s encode (`sector_id_from_id64()`), packed as `x + 128y + 16384z` |
| `system_known` | `system_id` | `system_id()`: **the system's id64**, verbatim |

- The macros live in `schema/macro/` and `common.db.connect()` applies them to every write connection, so SQL and Python share one derivation.
- **Hand-authored things get a negative id from a hash of their name.**
  `sector_id_from_name()` and `system_id_from_name()` hash the cleaned name to 32 bits and negate it, for a sector with no grid cell or a system no feed gives an id64 for.
  A real address is positive, so the spaces cannot collide and the sign says whose id it is.
- **A hashed id is only as stable as `hash()`**, which DuckDB does not promise across versions.
  Stored rows are safe; a row first seen after a hash change is keyed differently than it would have been before.
- **A merge needs no allocation pass**: no `max+1`, no `row_number()`, so two concurrent loads cannot collide.
- **Every dump joins directly**: a dump's `id64` is `system_known.system_id`, with no bridge table.
- **The name is not an identity.**
  `(sector_id, system_in_sector)` is not unique on `system_known`: 1,477 pairs sit on more than one system, 3,349 rows.
  A lookup by name can return more than one row and callers must handle it (see *Never derive a system name by concatenating sector*).

### A re-key invalidates every join to a table it did not re-key

A join that finds nothing is not an error: it is a quiet, complete, plausible-looking wrong answer, and every downstream script reports success.

- Moving `system_known.system_id` from a surrogate in 1..200,676,922 to the id64 left `staging.sys_bridge` unrebuilt, and `JOIN sys_bridge g ON g.system_id = k.system_id` kept matching 73,243 rows out of 200.7M through accidental collisions.
  That rebuilt `system_known_probe` at 52,519 rows instead of 6,976,174, a 99.2% collapse, and the refresh printed success.
  An emptied probe answers "nobody has reported this system" for the entire galaxy, so the overlay's Confirmed table fills with other commanders' discoveries presented as untouched finds.

Three rules follow:

- **Rebuild every derived table a re-key touches, in the same operation.**
  Anything holding a copy of the key is part of the re-key, whether it lives in `main` or not.
- **Print `was N` beside every count**; that number is the only tell.
  `report_merge` and `etl/refresh_current.py` do this.
- **Delete a redundant key column rather than keeping it in step.**
  A caller that still uses it then fails with a Binder Error instead of silently returning collisions.

### No foreign keys: referential integrity is ETL's job

**`schema/` declares no `FOREIGN KEY`, and the model carries none.**

- DuckDB refuses to update any row a foreign key still references, by `MERGE`, `UPDATE ... FROM` or any other statement, whether or not the referenced column changes: `Violates foreign key constraint because key "..." is still referenced by a foreign key in a different table`.
  On a dimension that a child references, a merge can insert new rows but never correct one; `region` is the case, since `system_known` and `system_neutron` carry `region_id`.
- `INSERT ... WHERE NOT EXISTS` plus `UPDATE ... FROM` fails identically, as does adding `RETURNING` to any of them.
  Verified on DuckDB 1.5.4, where the failure is also inconsistent: the same statement shape can pass on one table and fail on another, so treat any inbound reference as blocking.
  The INSERT arm always succeeds and the UPDATE arm is refused, so a loader looks healthy for as long as its source only grows.
- DuckDB has no `ALTER TABLE DROP CONSTRAINT` (`No support for that ALTER TABLE option yet!`), so a foreign key added to a schema file is permanent in every database built from it, and a `RENAME` of a referenced table is refused.
- **`common.db.REFERENCES` is the only record of which column points at what**; a new reference must be added there or nothing knows it exists.
- `check_references(con, table)` counts dangling rows for one table's references, or all of them, printing a line each; `fail=True` makes a loader refuse to finish.
  Run it at the end of any `load.py` that writes a listed column.

```
  system_known.region_id -> region.region_id: 0
  system_known.poi_id -> poi.poi_id: 0   <== DANGLING would appear here
```

A dangling id is possible; the trade is deliberate, because a correction can always be applied and the check reports the truth afterwards.

### Four documented exceptions delete, because the row is wrong rather than stale

| table | why a row is deleted | nothing references it because |
|---|---|---|
| `system_predicted` | It is a prediction: once a system is explored, or one of its bodies turns up in a catalogue, the row is false. The loader deletes rows the pool no longer produces and says how many. | it is a leaf table |
| `system_catalog_alias` | A row is an assertion ("these two catalogue names are one star") keyed on itself. A retracted edge is a claim withdrawn, and while it sits there `etl/system_catalog/load.py` copies a `system_id` across it and merges two stars. One bad CNS3 field once chained 159 unrelated names onto one game system. | it is read only by the catalogue loader |
| `system_unfound` | A row claims a catalogued star cannot be found in the game. An alias that resolves it, or a commander who visits it, makes the claim false, and a hunting list offering settled places is worse than none. | it is a leaf table |
| `route` (app state) | Key `(route, hop)`, and a hop number is an order, not an identity. If a 46-jump chain re-solves to 44, hops 45 and 46 name waypoints the route no longer passes. | no row points at a hop |

- A table that predicts or asserts may delete; a table that records must not.
  `system_phenomenon` is built from the same volatile codex dumps and never deletes, because a phenomenon that drops out of a dump was still observed.
- `system_catalog.system_id` resolved through an alias is recomputed, not sticky: it is reset to NULL and re-derived on every load, so correcting the source corrects the model.
- `etl/route/load.py` deletes hops above what the seed holds only for routes the seed still names, and reports the count.
  A route dropped from the seed entirely is left alone and reported as an orphan.

### Never derive a system name by concatenating sector

- **Only `sector_id = 0` means "this system's name stands alone".**
  `sector.is_crafted` is TRUE for 424 real named sectors ("NGC 2546 Sector", "Col 359 Sector"), not just the `sector_id = 0` sentinel row literally named `'crafted'`.
  Treating `is_crafted` as the test strips the prefix off 5M systems; treating sector 0 as a prefix produces `'crafted Sol'`.
  Both mistakes were made here and each manufactured a multi-million-row phantom gap.
- **Join a dump's `id64` to `system_known.system_id`**: they are the same number, so there is nothing to resolve.
- **The composed name is not a key either.**
  1,477 full names are held by more than one system, across 3,349 rows: `NGC 2168 SB 746` is five different stars, `2MASS J03285461+3116512` four.
  All are hand-named systems at `sector_id = 0`, where the name passes through verbatim; Frontier shipped the same designation several times.
  There are zero duplicated `(sector_id, system_in_sector)` pairs in a real sector, so no composing rule fixes this.
- **Composing does not merge two sectors today, but not by construction.**
  Five sector names are space-delimited prefixes of longer ones (`Cepheus Dark Region` inside `Cepheus Dark Region B Sector`, and the same for Lupus, Puppis and Ophiuchus twice).
  A collision needs a designation in the short sector beginning `B Sector `; there are none, and if one ships nothing will say so.
- **A name lookup groups and keeps only `HAVING count(*) = 1`**, leaving an ambiguous name unresolved.
  Picking one writes a coin-flip id into a database that cannot be rebuilt; `common.current.resolve_id64` does this.

### Comparing for changes

- **Use `IS DISTINCT FROM`, not `<>`.**
  `NULL <> 1` is `NULL`, so `<>` skips the backfill of a NULL column entirely and the merge reports success while the column stays NULL.
- **Round any column derived from a float aggregate before storing it.**
  `avg()` and `sum()` over millions of rows run in parallel with `preserve_insertion_order=false`, so the summation order varies and the last bits move.
  `system_predicted` reports 2.3M spurious updates without it; its probabilities are rounded to 6 dp at the point of computation.
  Rounding is what makes the merge idempotent.

### The two big tables carry no key constraint

**DuckDB 1.5.4 cannot drop a `PRIMARY KEY`**: `ALTER TABLE ... DROP CONSTRAINT` gives `No support for that ALTER TABLE option yet!`, `DROP PRIMARY KEY` is a parse error, and the key's index is not exposed to `DROP INDEX`.
A declared key is maintained row by row through every bulk load for the life of the database.
Measured on 40M rows in 16 batches:

| | insert | index | total |
|---|---|---|---|
| `PRIMARY KEY` maintained during the load | 89.5s | — | **89.5s** |
| no key, `CREATE UNIQUE INDEX` afterwards | 2.4s | 7.8s | **10.1s** |

- On the real 200.8M rows the declared key runs out of memory at 13 GiB.
  A unique index built afterwards needs about 9 GiB for `system_known` alone, and `system_body`'s key (577M rows on `(system_body, system_id, body_no)`) does not fit this machine.
- **So `system_known` and `system_body` declare neither.**
  The merge holds uniqueness: `load.sql` matches on the key and never inserts a present one, and a second run reporting `0 inserted, 0 updated` is the check.
- The cost: every lookup by key is a scan and every merge batch is a hash join against the target.
- The small tables keep their `PRIMARY KEY`s, since nothing about their size makes one expensive.

Verify by query, since nothing else will say:

```sql
SELECT count(*) - count(DISTINCT system_id) FROM system_known;               -- 0
SELECT count(*) - count(DISTINCT (system_body, system_id, body_no)) FROM system_body;
```

### Merge in sector batches, cut on a running row count

`etl/system_known/load.sql` takes a `sector_id >= ? AND sector_id < ?` range, and `sector_batches()` cuts the staged sectors into ranges of roughly equal row count.
Never a fixed number of sectors: the 12,100 sectors differ by orders of magnitude and `sector_id = 0` alone holds every hand-named system.
200.8M rows come out as 49 batches.

- **The target is written in sector order**, so each 122,880-row group carries a tight `sector_id` range in its statistics and a sector filter skips whole row groups.
  Measured on all 200.8M rows, distinct sectors per row group fall from 6,915.5 to 219.6 (worst case 7,268 to 656):

  | | hash-bucketed | sector-ordered | |
  |---|---:|---:|---|
  | one sector | 57.5 ms | **3.0 ms** | 19x faster |
  | sector range | — | 6.1 ms | |
  | 100 ly x/y/z box | 386.9 ms | **531.5 ms** | 1.4x SLOWER |

- **The box regression is the price.**
  `sector_id` packs as `x + 128y + 16384z`, so consecutive sectors are adjacent in x and jump in y and z, scattering a spatial box across row groups.
  It is the right trade because the overlay filters by sector (`--sector`) and takes its spatial answers from the materialised snapshots.
- **A sector boundary is a meaningful resume point**: "merged through sector X" stays true when the batch size changes; "bucket 37 of 64" does not.
- **DuckDB's pruning is statistics-driven, not constraint-driven.**
  On a `UNION ALL` view over 8 range-partitioned tables, 7 legs were rewritten to `EMPTY_RESULT` whether or not a `CHECK` declared the range; partitioned on `hash(id) % 8` nothing pruned, and a join predicate pruned nothing in either case.
  Only constant predicates prune.

### Schema changes: constraints are fixed when a table is created

- `schema/<table>.sql` is the one definition of a table, DDL and `COMMENT ON` together.
- Every table is created from those files when the database is made, in dependency-tier order (parents before children, so a child is never loaded against an empty parent).
- **A column rename or type change is an `ALTER TABLE` in place**, made in the same change as the schema file and every reader.
  - A `TIMESTAMP` becomes `TIMESTAMPTZ` under the time zone it was written in; every connection runs `SET TimeZone='UTC'`.
  - A view over the table is re-applied with `scripts/apply_schema.py`, because DuckDB lets the rename through and the view fails only when next queried.
- **A new constraint, or a dropped column, needs a new database**: edit `schema/<table>.sql` and build one.

`scripts/build_fresh_db.py` is that build; it writes `elite_mapping_fresh.duckdb` next to the model:

1. Every `RAW SOURCE` staging table, plus the few work tables nothing rebuilds, is copied in `rowid` batches of 8M rows.
2. Every `main` table is created from its `schema/<table>.sql`.
   A column the old table has and the file lacks stops the build unless it is named in `DROPPED`.
3. The rows are copied, remapping a changed key through a map table on the way.
4. Every copied table is checksummed column by column against the source (`sum(hash(c))` per column), plus structural checks for whatever was re-keyed or reshaped.
5. `--swap` renames the old file to `elite_mapping_pre_fresh.duckdb` and moves the new one into place, and refuses until step 4 has passed.

- Every step records itself in `staging.fresh_build_done`, so a kill costs a re-run of the same command.
- `transform` is not copied; the next load rebuilds it.
- A plain streaming copy moves 570M rows in about 134 seconds; everything beyond that is constraint maintenance.
  On `system_body`, a `PRIMARY KEY` alone takes 738s, and a `PRIMARY KEY` plus a composite `UNIQUE` dies at 14.9 GiB after 898s.

## 4b. Windows: `--window` picks how much of a source to stage

A provider publishes deltas at fixed widths and the widths differ per provider, so one `--window` means a different file for each:

| `--window` | Spansh | EDSM | EDAstro |
|---|---|---|---|
| `1day` | `galaxy_1day` | *skipped* | *skipped* |
| `7days` | `galaxy_7days` | 7-day | 7-day |
| `1month` | `galaxy_1month` | 7-day | 7-day |
| `full` | `galaxy.json.gz` — 114 GB, hours | full | 7-day |

- **An explicit window is a budget, not a hint.**
  `common.db.window_covering()` picks the widest window the provider publishes that is no wider than the request; a provider with none is skipped, on its own line.
  Asking for a day and being handed EDSM's 97M-row full dump is a different job with a different cost; ask for the wider dump explicitly.
- `--only` narrows the set of providers.
- **Without `--window`, the gap decides.**
  `system_known.first_seen` records when each row was inserted, so `now() - max(first_seen)` is how far behind the model is.
  `common.db.window_for_gap()` asks each provider for the narrowest window that spans that gap, because a narrower dump leaves a hole no later delta reaches back to.
  A load that inserts nothing leaves `max(first_seen)` in place, so the next run asks for a wider dump; an empty or `first_seen`-less table takes the full catalogue.
- **An interrupted load fools the gap.**
  The batches that merged stamp this run's `first_seen`, so `max(first_seen)` says the model is current when most of the window never arrived.
  After a killed or failed `system_known` load, re-run with the same explicit `--window`.

```
python etl/system_known/refresh.py                  # however far behind we are
python etl/system_known/refresh.py --only spansh    # ... from one provider
python etl/system_known/refresh.py --window 7days   # spend no more than a week's dump
```

- **A full staging table with no state file beside it is adopted, not re-downloaded**: re-fetching 114 GB to arrive at the same bytes buys nothing.
  The run says loudly that it adopted the table without validating it; `--force` re-fetches.
- **A delta is never adopted**: the provider rewrites the same filename daily, so a delta table with no provenance could be any window.
- **A window only adds.**
  The load can insert and correct but never conclude a row is gone, so `orphans.sql` runs only when every staged source was `full`.
- **Re-staging is decided by the server, not by what is on disk.**
  `raw/<name>.staged.json` records the validator (`ETag`/`Last-Modified`/size) the staging table was built from.

| validator vs `.staged.json` | action |
|---|---|
| same, complete | nothing is re-read |
| different | truncate and rebuild, because resuming into yesterday's rows of a rewritten file would ingest half a window |
| same, incomplete | resume the parse from the committed row count, which is what makes a 114 GB dump survivable |

## 5. Downloads validate against the server

`common.sources.download(url, name)` fetches into `raw/<name>` and is the only way a `stage.py` gets a file.
Several tables share a download, so each of their `stage.py` scripts calls it and only the first transfers anything.

- **Idempotent means "ask the server", not "trust the disk".**
  Every call issues a `HEAD` and compares against `raw/<name>.meta.json`, which records the `ETag`, `Last-Modified` and size of the file held.
- The strongest validator available wins: `ETag` if both sides have one, else `Last-Modified`, else `Content-Length` against the file.
- Unchanged returns the path with no transfer; changed fetches to a `.part` file, replaces atomically and records the new validators.
- A response shorter than `min_bytes` is rejected instead of replacing a good file.
- An unreachable server with a cached copy prints a loud `USING THE CACHED ... WHICH MAY BE STALE` line rather than failing the pipeline: the one path to stale data, and it announces itself.

## 6. Where things live

| folder | contents |
|---|---|
| `etl/<table>/` | `stage.py`, `load.py`, `refresh.py` and that table's `.sql` files |
| `schema/` | `<table>.sql` per `main` table, DDL **and** its `COMMENT ON` |
| `schema/staging/` | one file per `staging` table |
| `schema/transform/` | one file per `transform` table |
| `schema/macro/` | the key-derivation macros |
| `common/` | shared code, imported not copied |
| `raw/` | downloaded files and their `.meta.json` validators |
| `log/` | run output, teed there by `common/runlog.py` |
| `scripts/` | non-per-table utilities |

Anything used by more than one script goes in `common/`: `db.py` the connection and merge plumbing, `sources.py` the downloader, `current.py` the app-state database, `poi_link.py` the single system-level/body-level POI decision.

## 7. Write no comments

- **No `#` comments, no `--` comments in `.sql` files, no docstrings.**
  A comment is a second thing to keep true, and this repo has paid to remove roughly 2,080 lines of stale ones.
- What needs explaining belongs in this file or another `.md`.
- `COMMENT ON` is not a code comment and is required (§8).
- Any text that does exist, `COMMENT ON` included, describes the code as it is now, never its history.

## 8. Every table and every column carries a COMMENT

- **It applies to `staging` and `transform` tables as much as to `main`.**
  A staging table is the least self-explanatory thing in the database and where provenance mistakes start: `staging.canonn_codex_event.index_id` is not a row id, its `x`/`y`/`z` are VARCHAR, and its `_localised` columns are populated on 38% of rows.
- **A comment states what the table is, where it came from, and what it is not** (slice vs full catalogue, bound vs estimate).
  Every expensive mistake in this project has been a provenance mistake.
- **Every column too**: what the value means and what it must not be used for.
  `body.is_terraform_candidate` records that Earth-like is deliberately FALSE and that the column must not be used for scan value; `sector.radius` records that it is a lower bound, not the sector size.
- **Almost nothing enforces it.**
  `scripts/apply_schema.py` refuses an undocumented column only on a view, so whether a comment is true is held by review.
- **Run `python scripts/check_sql.py` after editing any `.sql` file.**
  It parses every statement in `schema/**` and `etl/**` without executing it (DuckDB's `extract_statements`), about a second for 154 files.
  A comment is executable code: one unescaped apostrophe (`model's` for `model''s`) in a `COMMENT ON` makes `etl/refresh_current.py` fail after it has dropped the mirror, leaving every app-state table at zero rows.
- DDL and comment text live in one file so a schema change cannot drift from its documentation.
- Applying a file is safe at any time: `CREATE TABLE IF NOT EXISTS` is a no-op on an existing table, and `common.db.prepare_table` re-applies the file before every merge.

## The model database

`elite_mapping.duckdb` is self-contained: `stage.py` puts every input in it and `load.py` reads only the database, so no loader depends on a download still being on disk.

- **`system_known.system_id` is the id64**, so `common/poi_link.py`, `etl/system_phenomenon/` and `scripts/score_predictions.py` join it to a source's `id64` with no bridge or separate `id64` column.
- **Do not materialise the system name.**
  Two 200M-row name tables cost ~11 GiB between them, while `sector` is 12,100 rows and composing a name on demand is 0.5 ms for one system against 82.8 ms scanning an unindexed name table, and 2.46 s for all 200.8M.
  Ask `system_known`.
- The joins in `etl/system_body/transform.sql` that resolve dump rows select from `main.system_known LEFT JOIN main.sector` inline, with the composing rule written once per file:

```sql
CASE WHEN k.sector_id = 0 OR sc.sector IS NULL THEN k.system_in_sector
     ELSE sc.sector || ' ' || k.system_in_sector END
```

- `sector_id = 0` is the only test that means "this name stands alone".
  Testing `sector IS NULL` instead finds sector row 0, literally named `crafted`, and emits "crafted 1 Epsilon Equulei" for 149,726 systems; this exact mistake has been made here three times.

## Current inventory

Every model table follows sections 1–5, and each `refresh.py` is the complete command: it downloads what it needs, stages it and merges it.

| table | kind | command |
|---|---|---|
| `region` | downloaded (Canonn codex) | `etl/region/refresh.py` |
| `sector` | downloaded (EDAstro sector list) | `etl/sector/refresh.py` — **before** `system_known` |
| `system_known` | downloaded (Spansh + EDSM + EDAstro) | `etl/system_known/refresh.py` (`--window`, `--only`); links POIs with `etl/system_known/poi.py` |
| `body` | hand-curated `input/body.parquet` | `etl/body/refresh.py`; `seed.py` wrote the file once |
| `system_body` | downloaded (Spansh + EDSM + EDAstro 7-day + the BH/WR and neutron catalogues) | `etl/system_body/refresh.py` (`--limit N`, `--buckets N`, `--window`); links POIs with `etl/system_body/poi.py` |
| `poi` | downloaded + **hand-curated** `input/poi.parquet` | `etl/poi/refresh.py` |
| `system_predicted` | derived, **deletes** | `etl/system_predicted/refresh.py` (`--refresh-value` after any `system_body` load) |
| `system_phenomenon` | downloaded (Canonn + EDSM codex, GEC) | `etl/system_phenomenon/refresh.py` |
| `carrier` | downloaded (EDAstro roster) | `etl/carrier/refresh.py` |
| `carrier_position` | derived | `etl/carrier_position/refresh.py` (re-run after every `carrier` load) |
| `station_service` | downloaded (Spansh station search, Material Trader + Technology Broker) | `etl/station_service/refresh.py` — pulls the API before it opens the database; never deletes, flags `is_listed` |
| `system_poi` | derived | `etl/system_poi/refresh.py` (re-run after either POI link) |
| `system_catalog_alias` | hand-editable `input/system_catalog_alias.parquet`, **deletes** | `etl/system_catalog_alias/refresh.py`; `seed.py` (**network**) wrote the file once |
| `system_catalog` | hand-editable `input/system_catalog.parquet` | `etl/system_catalog/refresh.py`, after the aliases; `seed.py` (**network**) wrote the file once |
| `system_unfound` | derived, **deletes** | `etl/system_unfound/refresh.py` — reads `staging.catalog_parallax`, which nothing re-creates |
| `system_neutron` | **not in the model**: derived into the app-state mirror | `etl/refresh_current.py`; `schema/system_neutron.sql` must survive, see below |
| `body_type_census` | derived **view**, not a table | `scripts/apply_schema.py body_type_census` |
| `system_all` | derived **view**, not a table | `scripts/apply_schema.py system_all` |

- **`staging.catalog_parallax` has no stager.**
  It carries the Hipparcos, CNS3 and Bright Star parallaxes `system_unfound` and `system_catalog.missing_coordinate` are built from.
  The cached VizieR files in `raw/catalog/` name the catalogues, but how the three were combined and where `vmag`, `sp_type` and `usable` come from is recorded nowhere, and nothing rebuilds the table.
- **`route` is app state**, in `elite_mapping_current.duckdb`, seeded from `input/route.parquet` by `etl/route/load.py`: the one loader in `etl/` whose target is the app-state file (see `common/current.py:CURRENT_TABLES`).

### If it adds no facts, ask whether the model should hold it at all

`system_neutron`, `carrier_position` and `system_poi` add no facts: every value is copied from `system_known`, `system_body`, `carrier` or `sector`.
The overlay reads them from the mirror `etl/refresh_current.py` writes, so a model-side copy is an intermediate between two derivations and one more thing that drifts.

- **`system_neutron` is derived into the mirror at refresh time and is not held in the model.**
  Deriving it from `system_known` takes 178 ms and yields 3,462,397 rows; a stored copy held 3,427,654, a strict subset missing 34,743 systems, silently stale.
- **A mirror-only table keeps its `schema/<table>.sql`.**
  `etl/refresh_current.py` creates every mirror table from that file after dropping and CHECKPOINTing, so a missing file fails at `CREATE TABLE` and leaves the app-state database with no neutrons, no carriers and no predictions.
  To move a table out of the model: drop the model table, delete the builder, remove its `common.db.REFERENCES` entries, and say in the schema file that the table is mirror-only.
- **`carrier_position` and `system_poi` stay materialised because the HUD asks their question on every jump and DuckDB has nothing to probe on.**
  2,524 carriers resolved through `system_known` scan all 200,676,922 rows (1,440 ms warm, 5,224 cold), and the 10,023 `system_body` rows carrying an `poi_id` scan all 577,639,044; materialised, 1.8 ms and 1.6 ms.
  They are snapshots of a join and go stale silently (a carrier that jumped keeps its old position), so re-run each after its source loads; both are merge-only, so a no-op run looks like one.
  Measure before assuming they are worth their rows.
- **`body_type_census` is a view.**
  63 rows aggregated from 569,697,301, read by no code, 5.2 s to compute: a stored copy of a pure aggregate buys nothing and can be wrong.
  It names `staging.spansh_galaxy_body` rather than the `spansh_body` role, so a 1-day stage cannot turn the galaxy census into a census of one day.

### Real star catalogues

- **The two catalogue tables are the only builders that read the network directly** (VizieR/CDS and the NASA Exoplanet Archive) rather than through `common.sources.download`.
  Real star catalogues change once a decade, so mirroring 4.8M rows into `staging` to read straight back out buys nothing; downloads cache in `raw/catalog/`.
- **Load the aliases first**: the catalogue walks the edges, and re-running it is what applies any alias correction.

```
python etl/system_catalog_alias/load.py   # 1.14M "same star" assertions
python etl/system_catalog/load.py         # resolves by name, then walks the edges
```

### App-state tables — `elite_mapping_current.duckdb`

- Created once by `python scripts/create_current_db.py`, which applies every `schema/<table>.sql` named in `common/current.py:CURRENT_TABLES`; nothing merges into a table it had to create.
- **`CURRENT_TABLES` is the only thing that says which database a table belongs to**, since both share the flat `schema/` directory.
  A table missing from it is silently not built.
- `system_seen`, `system_visited`, `system_confirmed`, `poi_visited` and `system_wrong` are written by the overlay and have no loader.
- `system_visited` is not a subset of `system_seen` and nothing links them: 7 systems were arrived at without ever being plotted to.

### Linking POIs

`poi` is the dimension; `system_known.poi_id` and `system_body.poi_id` reference it, each written by a `poi.py` in the owning table's folder:

```
python etl/poi/refresh.py                           # dimension first
python etl/system_known/poi.py                      # system-level POIs
python etl/system_body/poi.py                       # body-level POIs, INSERTS bodies
python etl/poi/load.py                              # again, for systems/bodies counts
python etl/system_poi/refresh.py                    # the snapshot the overlay reads
```

- **System-level vs body-level is decided once, in `common/poi_link.py`**; two scripts that disagreed would write a POI to both tables or to neither.
- **`etl/system_body/poi.py` inserts rows**: a Canonn report naming a body proves it exists, so a missing one is added with `source='canonn_codex'`, `body_no` -1 and `body_id` NULL (present, type unknown).
  That also makes its system count as explored, so it leaves `system_predicted`.
- **Nothing enforces either `poi_id`**: both linkers re-validate in SQL after writing and print the dangling count, and `common.db.check_references` covers the same two.

### Resuming a batched load

A run that dies leaves whole completed batches and untouched ones, never a half-written one, because each batch is one statement.
**Re-run the same command to resume**: the merge matches on the key, so a finished batch is a no-op the second time.

- `system_known` merges in `sector_id` ranges cut on a running row count (§4).
- `system_body` merges in buckets on `abs((system_id >> 3) % N)`: 8 for a delta, 128 for anything catalogue-sized.
  Each bucket's slice of `transform.system_body` is rebuilt from staging and merged before the next starts, so a re-run needs no leftover work table.
- **The `>> 3` matters**: the low three bits of an id64 are the mass code, so `system_id % 8` makes each bucket one mass class, and those buckets take from 35 s to 294 s.

To see which buckets a partial load reached, count per bucket rather than trusting the total:

```sql
SELECT abs((system_id >> 3) % 8) AS bucket, count(*) FROM system_body GROUP BY 1 ORDER BY 1;
```
