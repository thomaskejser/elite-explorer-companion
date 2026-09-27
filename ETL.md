# ETL conventions

How data gets into the databases. These rules are not stylistic — each one exists
because breaking it has cost us, or would silently corrupt a key.

## 0. Two databases

| file | what it is | who writes it | size |
|---|---|---|---|
| `elite_mapping_v2.duckdb` | **the model** — what the galaxy is, per Spansh/EDSM/EDAstro/Canonn. `main` holds the model, `staging` the downloaded sources, `transform` the reshaping between them. | `etl/` | ~91 GiB |
| `elite_mapping_v2_current.duckdb` | **app state** — what *this commander* has done: seen, visited, found. | the overlay | MBs |

**The app writes to `elite_mapping_v2_current.duckdb` and to nothing else.** The model
is *background information*: the app reads it, and may never write to it.

1. **The model is derived.** Every row is reproducible by re-running `etl/`.
2. **The app runs while you fly.** It is a live HUD reacting to journal events.
3. **ETL only writes to the model database.**

Point any script at another model file with the **`ELITE_DB`** environment variable. It is
read at **import time** of `common/db.py`, so setting `os.environ` after importing that
module silently targets the previous database.

```
ELITE_DB=C:/Source/elite_mapping/elite_mapping_v2.duckdb python etl/region/refresh.py
```

## 1. One folder per table: `stage`, `load`, `refresh`

`etl/<table_name>/`, where `<table_name>` is the **exact** DuckDB table name and matches
`schema/<table_name>.sql`. The folder names the table, the file names the job. No script
may write two model tables; if you need two, write two folders.

| script | what it does |
|---|---|
| `stage.py` | Gets the source data — **including downloading it** — into one or more `staging` tables. |
| `load.py` | Takes what is in `staging` and merges it into `main`. |
| `refresh.py` | Calls `stage` then `load`. The one entry point a person runs. |

**Every script is self-contained.** Running a table's `refresh.py` must produce that table,
with no prior step to remember and no separate ingest command to run first. That is the
whole point of the shape: `python etl/region/refresh.py` is the complete instruction.

A **derived** table — one built entirely from other `main` tables, with no external source
— has no `stage.py`. Its `load.py` is the whole job and its `refresh.py` calls only that.

`stage.py` and `load.py` each expose a function taking a connection (`stage(con)`,
`load(con)`) as well as a `main()`, so `refresh.py` runs both on one connection instead of
opening the 60 GiB file twice.

Each script reaches the repo root with
`sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))`.
Three levels, because the script is two directories deep. Get it wrong and `common/` does
not import at all.

## 2. SQL lives in `.sql` files, not in Python strings

A script reads and executes files with `common.db.run_sql_file(con, path)`. Python is there
to sequence the steps and print the report; the SQL is data on disk that can be read,
diffed, and run by hand against the database.

| file | holds |
|---|---|
| `schema/<table>.sql` | DDL **and** `COMMENT ON` for a `main` table |
| `schema/staging/<table>.sql` | DDL **and** `COMMENT ON` for a `staging` table |
| `etl/<table>/skipped.sql` | rows the transform could not accept, and why |
| `schema/transform/<table>.sql` | the definition **and** population of a `transform` table |
| `etl/<table>/load.sql` | the `MERGE INTO` that loads the table |
| `etl/<table>/orphans.sql` | rows in `main` the source no longer produces |

Resolved by `comment_file()`, `staging_file()` and `transform_file()` in `common/db.py`.

**A WINDOWED source is the one exception, and it uses `${table}` placeholders.** A feed
published at several widths stages into a table named after the DOWNLOAD, so one file
would otherwise have to be copied out per window with the same thirty column comments in
each. `schema/staging/spansh_galaxy_system.sql` carries `${table}`, `${provenance}` and
`${url}` instead, and `common.db.run_staging_template()` fills them in — one definition,
and the window still says itself in both the table name and the table comment.
The merge SQL sits in the table's own folder rather than `schema/`, because `schema/` holds
definitions and a merge is not one.

`run_sql_file` returns the last statement's result, which is how `load.py` gets the merge's
`RETURNING` rows back.

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

**Nothing downloaded is ever written straight into a model table**, and nothing is reshaped
on the way *through* the merge. If staging data does not fit the target, that is a
`transform` table with a file in `schema/transform/` — not a subquery buried in the merge,
and not a temporary object created between the two.

| schema | may be dropped or replaced? |
|---|---|
| `main` | **NO.** Merge only. Four documented exceptions, below. |
| `staging`, tables commented `RAW SOURCE` | **NO.** Re-obtainable only by re-downloading and re-parsing — hours. |
| `staging`, work tables | Yes. Intermediate state, `CREATE OR REPLACE`d freely. |
| `transform` | **Always.** Rebuilt from staging on every load; derived by definition, never edited. |

A `transform` table is where input validation belongs. Declare the constraints the target
needs — `NOT NULL`, `PRIMARY KEY`, `UNIQUE`, `CHECK` — and bad input fails there, before
anything reaches `main`, instead of being checked by hand in Python.
`schema/transform/region.sql` is the worked example.

`--clean-staging`, on `etl/system_body/stage.py`, holds the
RAW SOURCE line: it reads the comments, **keeps** every table beginning `RAW SOURCE`, and
`TRUNCATE`s the rest rather than dropping them, so the work
tables come back empty instead of missing. `--include-raw` overrides the allow-list and
takes 894M rows of irreplaceable source with it — the one flag here that costs hours of
re-download.

## 4. Merge with `MERGE INTO`; never drop

One statement, from the staging or transform table **directly** to the target:

```sql
MERGE INTO main.region AS t
USING transform.region AS s ON t.region_id = s.region_id
WHEN MATCHED AND t.region IS DISTINCT FROM s.region THEN UPDATE SET region = s.region
WHEN NOT MATCHED THEN INSERT (region_id, region) VALUES (s.region_id, s.region);
```

- Match on the **natural key**, never a surrogate id — `(type, body)` for `body`,
  `(type, sub_type)` for a census, `sector` for `sector`. Where the GAME
  supplies the id, that id **is** the natural key and the table is keyed on it directly:
  `region.region_id`, `sector.sector_id` and `system_known.system_id` are all the game's
  own address, taken as given rather than allocated `max+1`. See *Derive the key, never
  allocate it* below.
- **Guard the update arm with `IS DISTINCT FROM`.** Without it every matched row counts as
  a change and a no-op run stops looking like one.
- **Count with a `counts.sql`, never with `RETURNING`.** Beside every `load.sql` sits a
  `counts.sql` returning `(inserted, updated)` from predicates that MIRROR the merge's, run
  by `common.db.merge_counts()` **before** the merge. `MERGE ... RETURNING` is unusable on
  any table a foreign key points at — see below — and it silently works until the first run
  that actually changes something, which is the worst way for it to fail. The duplicated
  predicate is the cost; `report_merge` cross-checks the insert count against the row-count
  delta and prints a warning when the two files drift apart.
- **No `WHEN NOT MATCHED BY SOURCE THEN DELETE`.** Rows in the table but absent from the
  source are **left in place** and reported by `orphans.sql`. Their keys are **retired,
  never reused**. Deleting one is a manual decision, because something may already
  reference it.
- **Never renumber a surrogate id.** Allocate a new one as `max+1`; honour an id supplied by
  the source when it is free, otherwise reassign.
- Report `inserted / updated / orphaned` through `common.db.report_merge`. **A no-op run
  must look like a no-op.**

### Derive the key, never allocate it

**A surrogate `max+1` id is a last resort, and this project no longer has one on its
central tables.** Where the game names a thing, that name IS the key:

| table | key | where it comes from |
|---|---|---|
| `region` | `region_id` | the game's region id, parsed out of the codex token |
| `sector` | `sector_id` | the grid cell its systems' id64s encode (`sector_id_from_id64()`), packed as `x + 128y + 16384z` |
| `system_known` | `system_id` | `system_id()` — **the system's id64**, verbatim |

The macros live in `schema/macro/` and are applied to every write connection by
`common.db.connect()`, so the derivation is one definition that SQL and Python share.

**Hand-authored things get a NEGATIVE id from a hash of their name.** A sector with no
grid cell, a system no feed gives an id64 for: `sector_id_from_name()` and
`system_id_from_name()` hash the cleaned name to 32 bits and negate it. A real address is
positive, so the two spaces cannot collide and **the sign of the column says whose id it
is**. An id is only as stable as `hash()`, which DuckDB does not promise across versions —
existing rows are safe because they are already stored, but a row first seen after a hash
change would be keyed differently than it would have been before.

Three things follow, and all three are worth more than the surrogate was:

- **A merge needs no allocation pass.** There is no `max+1`, no `row_number()` over the
  source, and therefore no reason two concurrent loads could collide.
- **Every dump joins directly.** `staging.sys_bridge` existed only to carry
  id64 → system_id; with the id64 in the key column there is nothing to bridge.
- **The name stops being an identity.** `(sector_id, system_in_sector)` is NOT unique on
  `system_known`: **1,477 pairs sit on more than one system, 3,349 rows**, and 96 id64
  values used to sit on two rows each under two SPELLINGS of one name. Keying on the name
  lost the first kind and duplicated the second. **The price is that a lookup by name can
  return more than one row, and callers must handle it** — see the rule below.

### No foreign keys: referential integrity is ETL's job

**`schema/` declares no `FOREIGN KEY`, anywhere.** That is deliberate, and the reason is
that DuckDB refuses to update any row a foreign key still references — by `MERGE`, by
`UPDATE ... FROM`, by any statement, and whether or not the referenced column is the one
being changed. It reports `Violates foreign key constraint because key "..." is still
referenced by a foreign key in a different table`. On a dimension anything points at, that
made a merge able to insert a new row but never to correct an existing one, which is not a
constraint on bad data — it is a constraint on fixing data. `region` was the live case:
`system_known` and `system_neutron` carry `region_id`, so a renamed region could not be
merged at all.

Nothing about that was specific to `MERGE INTO`; the older `INSERT ... WHERE NOT EXISTS`
plus `UPDATE ... FROM` pattern failed identically on the same row, and so does adding
`RETURNING` to any of them. Verified on DuckDB 1.5.4, where the failure is also
**inconsistent** — the same statement shape can pass on one table and fail on another, so
treat any inbound reference as blocking rather than probing for a form that slips through.
The INSERT arm alone always succeeds; it is the UPDATE arm that is refused, which is why a
loader can appear healthy for as long as its source only ever grows.

**What replaces it.** `common.db.REFERENCES` lists every child→parent relationship the
database has — 15 of them — and is now the only record of which column points at what, so a
new one must be added there or nothing knows it exists. `check_references(con, table)`
counts dangling rows for one table's references, or all of them, and prints a line each;
pass `fail=True` to make a loader refuse to finish. Run it at the end of a `load.py` that
writes a column appearing in that list.

```
  system_known.region_id -> region.region_id: 0
  system_known.id_poi -> poi.poi_id: 0   <== DANGLING would appear here
```

A dangling id is now *possible*, which it was not before. The trade is deliberate: a
correction can always be applied, and the check tells you the truth after the fact instead
of a constraint refusing the fix in advance.

**The model database carries none**: `scripts/build_fresh_db.py` created every table from
these files. DuckDB has no `ALTER TABLE DROP CONSTRAINT` — verified, `No support for that
ALTER TABLE option yet!` — so a foreign key added to a schema file is permanent in every
database built from it, and a `RENAME` of a table another table references is refused.

### There are exactly FOUR documented exceptions, and all four delete for the same reason: the row is not stale, it is WRONG

**1. `system_predicted`.** The rule above protects surrogate keys that *other tables point
at*; nothing references `system_predicted`. More to the point, it is a
**prediction** table: once a system has been explored — or one of its bodies turns up in a
catalogue — the row is deleted. Its loader deletes rows the pool no longer produces and says
how many. Any future table that predicts rather than records may follow it; a table that
*records* must not. `system_phenomenon` is the worked example on the other side of that
line: it is built from the same volatile codex dumps, and it still **never deletes**,
because a phenomenon that drops out of a dump was still observed.

**2. `system_catalog_alias`.** Its rows are ASSERTIONS ("these two catalogue names are one
star"), its key is the assertion itself, and nothing references it. A retracted
edge is therefore not a retired key but a claim withdrawn — and one that does damage while
it sits there, because `etl/system_catalog/load.py` copies a `system_id` across it and
thereby merges two different stars. That is not theoretical: the first seed chained 159
unrelated names onto one game system through a single bad CNS3 field, and merge-never-drop
would have made the fix impossible to apply. The paired rule is that the resolution it feeds
is **recomputed, not sticky** — every alias-resolved `system_catalog.system_id` is reset to
NULL and re-derived on each load, so correcting the source is enough to correct the model.

**3. `system_unfound`.** A row is the claim that a catalogued star cannot be found in the
game. An alias that resolves it, or a commander who visits it and puts it in a dump, makes
that claim FALSE — and a hunting list that keeps offering places already settled is worse
than no list. Nothing references it. Same line as `system_predicted`: it asserts
rather than records.

**4. `route` (app state).** A route's key is `(route, hop)`, and **a hop number is an
ORDER, not an identity** — re-solving a chain renumbers it, which is exactly what the ban
on renumbering a surrogate exists to prevent everywhere else. The difference is that no
row points at a hop and no hop means anything on its own: hop 31 of a 46-jump chain is
"the thirty-first system you arrive at", and if the re-solve is 44 jumps long then hops
45 and 46 name waypoints the route no longer passes. A navigation aid that offers a
waypoint it does not visit is worse than no aid. `etl/route/load.py` therefore deletes
hops above what the seed holds **for routes the seed still names**, and reports the
count; a route dropped from the seed entirely is left alone and reported as an orphan,
because that is the "row absent from the source" case the rule is actually about.

### Never derive a system name by concatenating sector

`sector.is_crafted` is TRUE for **424 real named sectors** ("NGC 2546 Sector",
"Col 359 Sector"), not just for the `sector_id = 0` sentinel row that is literally named
`'crafted'`. Only `sector_id = 0` means "this system's name stands alone". Treating
`is_crafted` as that test silently strips the prefix off 5M systems and makes them look
absent; treating sector_id 0 as a prefix produces `'crafted Sol'`. Both mistakes were made
here, and both manufactured a multi-million-row phantom "gap".

**Join a dump's `id64` to `system_known.system_id` instead.** They are the same number,
so there is nothing to resolve and no bridge to keep current.

**AND THE COMPOSED NAME IS NOT A KEY EITHER — BUT NOT BECAUSE OF ANYTHING WE DO.** 1,477
full system names are held by **more than one system**, across 3,349 rows: `NGC 2168 SB
746` is five different stars, `2MASS J03285461+3116512` four. **All 1,477 are hand-named
systems at `sector_id = 0`, where nothing is composed and the name passes through
verbatim** — Frontier shipped the same catalogue designation several times. There are
**zero** duplicated `(sector_id, system_in_sector)` pairs in a real sector, so composing
merges nothing and no amount of careful composing would fix this.

Composing cannot currently merge two sectors either, though **not by construction**: five
sector names are space-delimited prefixes of longer ones (`Cepheus Dark Region` inside
`Cepheus Dark Region B Sector`, and the same for Lupus, Puppis and Ophiuchus twice). A
collision needs a designation in the short sector beginning `B Sector `, and there are
none today. If one is ever shipped, two distinct systems get one name and nothing will
say so.

So a name lookup must **group and keep only `HAVING count(*) = 1`**, leaving an ambiguous
name unresolved: picking one arbitrarily writes a coin-flip id into a database that cannot
be rebuilt. `common.current.resolve_id64` does this.

### Comparing for changes

Use `IS DISTINCT FROM`, not `<>`. After an additive migration a new column is `NULL` on
existing rows, and `NULL <> 1` evaluates to `NULL`, so `<>` skips the backfill entirely and
the column stays empty forever. This bit us for real on a migrated column: the merge
reported success while leaving the column all NULL.

**Round any column you derive from a float aggregate before you store it.** `avg()` and
`sum()` over millions of rows are evaluated in parallel with
`preserve_insertion_order=false`, so the summation *order* varies between runs, and float
addition is not associative — the last bits move. `IS DISTINCT FROM` is doing its job when
it then flags every row as changed, but the run stops looking like the no-op it was.
`system_predicted` reported 2.3M spurious updates for exactly this reason; rounding the
probabilities to 6 dp at the point of computation fixed it. Rounding is not cosmetic here —
it is what makes the merge idempotent.

### The two big tables carry NO key constraint

**DuckDB 1.5.4 cannot drop a `PRIMARY KEY`.** Verified: `ALTER TABLE ... DROP CONSTRAINT`
gives `No support for that ALTER TABLE option yet!`, `DROP PRIMARY KEY` is a parse error,
and the key's index is not exposed to `DROP INDEX` either. A declared key is maintained row
by row through every bulk load, for the life of the database. Measured on 40M rows in 16
batches:

| | insert | index | total |
|---|---|---|---|
| `PRIMARY KEY` maintained during the load | 89.5s | — | **89.5s** |
| no key, `CREATE UNIQUE INDEX` afterwards | 2.4s | 7.8s | **10.1s** |

On the real 200.8M rows the declared key ran out of memory at 13 GiB. A unique index built
once afterwards needs about 9 GiB for `system_known` alone, and `system_body`'s key —
577M rows on `(system_body, system_id, body_no)` — does not fit this machine at all.

**So `system_known` and `system_body` declare neither.** Uniqueness is held by the merge:
`load.sql` matches on the key and never inserts a row whose key is present, and a second
run of the loader reporting `0 inserted, 0 updated` is the check. The cost is that every
lookup by key is a scan and every merge batch is a hash join against the target. Verify
by query, since nothing else will say:

```sql
SELECT count(*) - count(DISTINCT system_id) FROM system_known;               -- 0
SELECT count(*) - count(DISTINCT (system_body, system_id, body_no)) FROM system_body;
```

The small tables keep their `PRIMARY KEY`s: nothing about their size makes one expensive.

### Merge in SECTOR batches, cut on a running row count

`etl/system_known/load.sql` takes a `sector_id >= ? AND sector_id < ?` range, and
`sector_batches()` cuts the staged sectors into ranges of roughly equal ROW COUNT — never
a fixed number of sectors, because the 12,100 sectors differ by orders of magnitude and
`sector_id = 0` alone holds every hand-named system. 200.8M rows come out as 49 batches.

Two things a hash of the id cannot do:

- **The target is written in sector order**, so each 122,880-row group carries a tight
  `sector_id` range in its statistics and a filter on sector skips whole row groups.
  Measured on all 200.8M rows, distinct sectors per row group fell from **6,915.5 to
  219.6** (worst case 7,268 to 656) and:

  | | hash-bucketed | sector-ordered | |
  |---|---:|---:|---|
  | one sector | 57.5 ms | **3.0 ms** | 19x faster |
  | sector range | — | 6.1 ms | |
  | 100 ly x/y/z box | 386.9 ms | **531.5 ms** | 1.4x SLOWER |

  **The box regression is real and is the price.** `sector_id` packs as
  `x + 128y + 16384z`, so consecutive sectors are adjacent in x and jump in y and z; a
  spatial box wants row groups that this ordering scatters. It is the right trade only
  because the overlay filters by sector (`--sector`) and takes its spatial answers from
  the materialised snapshots instead.
- **A sector boundary is a meaningful resume point.** "Merged through sector X" stays true
  when the batch size changes; "bucket 37 of 64" does not.

DuckDB's pruning here is **statistics-driven, not constraint-driven** — measured on a
`UNION ALL` view over 8 range-partitioned tables, 7 legs were rewritten to `EMPTY_RESULT`
whether or not a `CHECK` constraint declared the range, while the same view partitioned on
`hash(id) % 8` pruned nothing at all and a join predicate pruned nothing in either case.
Only constant predicates prune.

### Schema changes: THE MODEL IS CREATED WITH THE DATABASE AND NEVER ALTERED

`schema/<table>.sql` is the **one** definition of a table — its DDL *and* its `COMMENT ON`
text. Every table is created from those files when the database is made, in dependency-tier
order (parents before children, so a child is never loaded against an empty parent).
**After that the
shape does not change.** To change a table: edit its `schema/<table>.sql` and build a new
database.

**`scripts/build_fresh_db.py` is that build.** It writes `elite_mapping_v2_fresh.duckdb`
next to the model:

1. Every `RAW SOURCE` staging table, plus the few work tables nothing rebuilds, is copied
   across in `rowid` batches of 8M rows.
2. Every `main` table is created from its `schema/<table>.sql`. A column the old table has
   and the file lacks stops the build, unless it is named in `DROPPED`.
3. The rows are copied, remapping a changed key through a map table on the way.
4. Every copied table is checksummed column by column against the source (`sum(hash(c))`
   per column), plus structural checks for whatever was re-keyed or reshaped.
5. `--swap` renames the old file to `elite_mapping_v2_pre_fresh.duckdb` and the new one into
   place, and refuses until step 4 has passed.

Every step records itself in `staging.fresh_build_done`, so a kill costs a re-run of the
same command. `transform` is not copied; the next load rebuilds it.

A plain streaming copy moves 570M rows in about 134 seconds. Everything beyond that is
constraint maintenance: on `system_body`, PRIMARY KEY only 738s, PRIMARY KEY plus a composite
UNIQUE dead at 14.9 GiB after 898s.

## 4b. Windows: `--window` picks how much of a source to stage

A provider that publishes deltas publishes them at fixed widths, and **the widths differ
per provider**, so one `--window` has to mean a different file for each:

| `--window` | Spansh | EDSM | EDAstro |
|---|---|---|---|
| `1day` (default) | `galaxy_1day` | *skipped* | *skipped* |
| `7days` | `galaxy_7days` | 7-day | 7-day |
| `1month` | `galaxy_1month` | 7-day | 7-day |
| `full` | `galaxy.json.gz` — 114 GB, hours | full | 7-day |

`common.db.window_covering()` picks the **widest window the provider publishes that is no
wider than the request**, and returns nothing when the provider has none — that provider
is then SKIPPED and the run says so on its own line. **An explicit window is a budget, not
a hint.** Asking for a day and being handed EDSM's 97M-row full dump is not a delta
refresh, it is a different job with a different cost; ask for the wider dump by asking for
it. `--only` narrows the set of providers further.

**Leave `--window` off and the gap decides.** `system_known.first_seen` records the
wall-clock instant each row was inserted, so `now() - max(first_seen)` is how far behind
the model actually is. `common.db.window_for_gap()` then asks each provider for the
**narrowest window it publishes that SPANS that gap** — pointing the opposite way to the
budget rule, and for a reason: a dump narrower than the gap leaves a hole that no later
delta reaches back to, because tomorrow's delta only goes back a day. A load that inserts
nothing leaves `max(first_seen)` where it was, so the next run asks for a wider dump
rather than silently skipping a window. An empty or `first_seen`-less table means "no
floor" and takes the catalogue.

**AN INTERRUPTED LOAD FOOLS IT.** The batches that did merge stamped their rows with this
run's `first_seen`, so `max(first_seen)` says the model is current when most of the window
never arrived. After a killed or failed `system_known` load, re-run with the same explicit
`--window`; letting the gap decide asks for a narrower dump and leaves a hole.

```
python etl/system_known/refresh.py                  # however far behind we are
python etl/system_known/refresh.py --only spansh    # ... from one provider
python etl/system_known/refresh.py --window 7days   # spend no more than a week's dump
```

**A FULL staging table with no state file beside it is ADOPTED, not re-downloaded.** That
is what a catalogue parsed before the state file existed looks like, and re-fetching
114 GB to arrive at the same bytes buys nothing. The run says loudly that it adopted the
table and did not validate it; `--force` re-fetches. A DELTA is never adopted — the
provider rewrites the same filename daily, so a delta table with no provenance beside it
could be any window at all.

**A window only ever ADDS.** The load that follows can insert and correct, but it can
never conclude a row is gone, which is why `orphans.sql` runs only when every staged
source was `full`.

**Re-staging is decided by the SERVER, not by what is on disk.** `raw/<name>.staged.json`
records the validator (`ETag`/`Last-Modified`/size) the staging table was built from. Same
validator and complete → nothing is re-read. Different validator → the table is truncated
and rebuilt, because the provider REWRITES the same filename every day and resuming into
yesterday's rows would silently ingest half a window. A file that is the same but
incomplete → the parse resumes from the committed row count, which is what makes a
114 GB dump survivable.

## 5. Downloads validate against the server

`common.sources.download(url, name)` fetches into `raw/<name>` and is the only way a
`stage.py` gets a file. Several tables are built from the same download, so every one of
their `stage.py` scripts calls it and only the first transfers anything.

**Idempotent means "ask the server", not "trust what is on disk".** Every call issues a
`HEAD` and compares against `raw/<name>.meta.json`, which records the `ETag`,
`Last-Modified` and size of what we actually hold. Strongest validator available wins:
`ETag` if both sides have one, else `Last-Modified`, else `Content-Length` against the file.
Unchanged → return the path, no transfer. Changed → fetch to a `.part` file and replace
atomically, then record the new validators.


**A READ-ONLY attach is not a free pass.** DuckDB refuses to open the file at all while
another process holds it — `Cannot open file ... being used by another process`, even for
`ATTACH ... (READ_ONLY)`. So "the model is free" has to mean **no handle at all**, not
merely no writer, and that includes a finished script whose process is still alive.

Two failure modes it handles rather than hides. A response shorter than `min_bytes` is
rejected instead of replacing a good file. A server that cannot be reached while a cached
copy exists produces a loud `USING THE CACHED ... WHICH MAY BE STALE` line rather than
failing the pipeline — that is the one path to stale data, and it announces itself.

## 6. Where things live

| folder | contents |
|---|---|
| `etl/<table>/` | `stage.py`, `load.py`, `refresh.py` and that table's `.sql` files |
| `schema/` | `<table>.sql` per `main` table — DDL **and** its COMMENT ON |
| `schema/staging/` | one file per `staging` table |
| `schema/transform/` | one file per `transform` table |
| `common/` | shared code, imported not copied |
| `raw/` | downloaded files and their `.meta.json` validators |
| `scripts/` | non-per-table utilities |

Anything used by more than one script goes in `common/`, not copy-pasted. `db.py` holds the
connection and merge plumbing, `sources.py` the downloader, `current.py` the app-state
database, `poi_link.py` the single system-level/body-level POI decision.

## 7. Write no comments

**No `#` comments, no `--` comments in `.sql` files, no docstrings.** The code says what it
does; a comment is a second thing that has to be kept true, and this repo has already paid
to remove roughly 2,080 lines of stale ones. If something needs explaining it belongs in
this file or another `.md`.

`COMMENT ON` is not a code comment and is required — see 8.

## 8. Every table AND every column carries a COMMENT

Non-negotiable, and **almost nothing enforces it** — `scripts/apply_schema.py` refuses to
finish on an undocumented column, but only for a view, so whether a comment is TRUE is
held by review alone.

Whether it PARSES is now checked. **`python scripts/check_sql.py` parses every statement
in `schema/**` and `etl/**` without executing it** (DuckDB's `extract_statements`, which
raises on a parse error), and it
exists because a single unescaped apostrophe — `model's` for `model''s`, inside a
`COMMENT ON` — made `etl/refresh_current.py` fail at the point where it had already
dropped the mirror, leaving **every app-state table at zero rows**. A comment is executable
code. Run the checker after editing any `.sql` file; it takes about a second for 154 files. Comments must state what the table **is**, where it came
**from**, and what it is **not** (slice vs full catalogue, bound vs estimate). Every
expensive mistake in this project has been a provenance mistake.

This applies to `staging` and `transform` tables as much as to `main`. A staging table is
the rawest, least self-explanatory thing in the database and the place a provenance mistake
starts: `staging.canonn_codex_event.index_id` is not a row id despite the name, its
`x`/`y`/`z` are VARCHAR, and its `_localised` columns are populated on 38% of rows. None of
that is guessable and all of it is in the comments.

**Columns too.** Every column of every table we own carries a `COMMENT ON COLUMN` saying
what the value *means* and what it must not be used for — `body.is_terraform_candidate`
records that Earth-like is deliberately FALSE and that the column must not be used for scan
value; `sector.radius` records that it is a lower bound, not the sector size.

DDL and comment text live **together in one file** so a schema change and the documentation
of that change cannot drift apart. Applying a file is safe at any time: `CREATE TABLE IF NOT
EXISTS` is a no-op on an existing table, so re-asserting comments cannot reshape anything.
**Re-assert after any schema change** — a migration is the one thing that silently drops
comments, which is why `common.db.prepare_table` applies the file before every merge.

### A RE-KEY INVALIDATES EVERY JOIN TO A TABLE IT DID NOT RE-KEY

And a join that finds nothing **is not an error**. It is a quiet, complete,
plausible-looking wrong answer, and every script downstream reports success.

The id64 re-key moved `system_known.system_id` from a surrogate in 1..200,676,922 to the
game's id64. `staging.sys_bridge` carried both columns and was NOT rebuilt, so
`JOIN sys_bridge g ON g.system_id = k.system_id` went on matching — **73,243 rows out of
200.7M**, accidental collisions between a small id64 and an unrelated surrogate. Worse
than an empty result, because the rows that survive are WRONG rather than missing. It
rebuilt `system_known_probe` at 52,519 rows instead of 6,976,174, a 99.2% collapse, and
the refresh printed success. The probe answers "has somebody already reported this
system"; emptied, it answers **no for the entire galaxy**, and the overlay's Confirmed
table fills with other commanders' discoveries presented as untouched finds.

Three rules out of it:

- **Rebuild every derived table a re-key touches, in the same operation.** Anything
  holding a copy of the key is part of the re-key whether it lives in `main` or not.
- **Print `was N` beside every count.** That number was the only tell. `report_merge`
  does this; so does `etl/refresh_current.py`.
- **Delete the redundant column rather than keeping it in step.** `sys_bridge` is now
  `(system_id64, sys_name)`: the `system_id` column is GONE, so the one caller that used
  it fails with a Binder Error instead of silently returning collisions. A loud break at
  the call site beats a correct-looking number.

## The model database

`elite_mapping_v2.duckdb` is self-contained. Everything needed to rebuild any model table is
inside that one file, so a loader never depends on a download still being on disk —
`stage.py` is what puts it there, and `load.py` reads only the database.

**No foreign key is declared**, in `schema/` or in the database — see section 4 for why, and
for what checks the references instead.

**`system_known.system_id` IS the id64**, so every dump joins to it directly and there is
no mapping to keep alive: `staging.sys_bridge` and the separate `id64` column both existed
only to carry that mapping and **both are gone**. `common/poi_link.py`,
`etl/system_phenomenon/` and `scripts/score_predictions.py` join `system_id` to a source's
`id64` with no bridge.

**DO NOT MATERIALISE THE SYSTEM NAME.** Two tables used to: `sys_bridge` and
`sys_name`, 200M rows each, ~11 GiB between them. Both are deleted. `system_known` is
indexed on `system_id` and `sector` is 12,100 rows, so composing a name on demand is
**0.5 ms for one system** against 82.8 ms scanning a name table that has no index, and
2.46 s to compose all 200.8M. Ask `system_known`.

A copy would buy only a narrow build side for the joins in `etl/system_body/transform.sql`
that resolve the dump rows. It is not worth a table: those joins select from
`main.system_known LEFT JOIN main.sector` inline, and the rule for composing the name is
written **once per file** beside them —

```sql
CASE WHEN k.sector_id = 0 OR sc.sector IS NULL THEN k.system_in_sector
     ELSE sc.sector || ' ' || k.system_in_sector END
```

— because `sector_id = 0` is the only test that means "this name stands alone". The
deleted `sys_name` tested `sector IS NULL` instead and emitted **"crafted 1 Epsilon
Equulei" for 149,726 systems**: sector row 0 is literally named `crafted`, so the row is
found and the prefix is pasted on. Those names are not places. That is the third time this
exact mistake has been made here.

## Current inventory

Every model table follows sections 1–5. Each row's `refresh.py` is the complete command:
it downloads what it needs, stages it and merges it.

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
| `system_neutron` | **NOT IN THE MODEL** — derived into the app-state mirror | `etl/refresh_current.py`; `schema/system_neutron.sql` must survive, see below |
| `body_type_census` | derived **VIEW**, not a table | `scripts/apply_schema.py body_type_census` |
| `system_all` | derived **VIEW**, not a table | `scripts/apply_schema.py system_all` |

**`staging.catalog_parallax` has no stager.** It carries the Hipparcos, CNS3 and Bright Star
parallaxes `system_unfound` and `system_catalog.missing_coordinate` are built from; the
cached VizieR files in `raw/catalog/` name the catalogues, but how the three were combined
and where `vmag`, `sp_type` and `usable` come from is recorded nowhere. It survives as a
table and nothing rebuilds it.

`route` is not in that table because it is not in that database: it is **app state**, in
`elite_mapping_v2_current.duckdb`, seeded from `input/route.parquet` by
`etl/route/load.py` — the one loader in `etl/` whose target is the app-state file. See
`common/current.py:CURRENT_TABLES`.

### If it adds no facts, ask whether the MODEL should hold it at all

`system_neutron`, `carrier_position` and `system_poi` exist only so the overlay does not
scan a giant table. They add no facts — every value is copied from `system_known`,
`system_body`, `carrier` or `sector`. But the overlay does not read them from the model:
it reads the **mirror** `etl/refresh_current.py` writes into the app-state file. So a
model-side copy is an intermediate between two derivations, and it is one more thing that
drifts.

**`system_neutron` is the proof.** Deriving it straight from `system_known` takes
**178 ms** and yields 3,462,397 rows; the stored table holds 3,427,654. **34,743 systems
are in the derivation and absent from the table, and none the other way** — a strict
subset, silently stale, exactly like every other derived copy this project has lost a day
to. Nothing in the model reads it. It is being deleted from the model and derived into the
mirror at refresh time.

**A mirror-only table still needs its `schema/<table>.sql`, and deleting it is worse than
leaving the table.** `etl/refresh_current.py` creates every mirror table by running that
file, and it drops and CHECKPOINTs before any write — so a missing file fails the refresh
at `CREATE TABLE` and leaves the app-state database with **no neutrons, no carriers and no
predictions**. Drop the model table, delete the builder, remove its `common.db.REFERENCES`
entries; keep the schema file and say in it that the table is mirror-only.

`carrier_position` and `system_poi` are the same shape and the same question; measure
before assuming they are worth their rows.

**`body_type_census` went the other way and is now a VIEW.** 63 rows aggregated from
569,697,301, read by no code at all, 5.2 s to compute. A stored copy of a pure aggregate
buys nothing and can be wrong. It names `staging.spansh_galaxy_body` rather than the
`spansh_body` role, so a 1-day stage cannot turn the galaxy census into a census of one
day. The HUD asks their question on
every jump and DuckDB has nothing to probe on: 2,524 carriers resolved through `system_known`
scanned all 200,676,922 rows (1,440 ms warm, 5,224 cold), and the 10,023 `system_body` rows
carrying an `id_poi` scanned all 577,639,044. Materialised: 1.8 ms and 1.6 ms. **They are
snapshots of a join and go stale silently** — a carrier that jumped keeps its old position
until the builder runs again. Re-run each after its source loads; both are merge-only, so a
no-op run looks like one.

**The two catalogue tables are the only builders that read the NETWORK directly**
(VizieR/CDS and the NASA Exoplanet Archive) rather than through `common.sources.download`,
because real star catalogues are astronomy rather than an Elite data source: they change
once a decade, so mirroring 4.8M rows of them into `staging` to read straight back out would
buy nothing. Downloads cache in `raw/catalog/`.

**Load them in this order** — the alias edges must exist before the catalogue walks them,
and re-running the second is what applies any correction to the first:

```
python etl/system_catalog_alias/load.py   # 1.14M "same star" assertions
python etl/system_catalog/load.py         # resolves by name, then walks the edges
```

### App-state tables — `elite_mapping_v2_current.duckdb`

Created once by `python scripts/create_current_db.py`, which applies every
`schema/<table>.sql` named in `common/current.py:CURRENT_TABLES`. **The model is created when
the database is made and does not change after that**; nothing merges into a table it had to
create. Schema files live in the same flat `schema/` directory as the model's — the filename
cannot say which database a table belongs to, so `CURRENT_TABLES` is the only thing that
does. Add a table there or `create_current_db.py` will not build it, silently.

All five tables — `system_seen`, `system_visited`, `system_confirmed`, `poi_visited` and
`system_wrong` — are written by the overlay and have no loader. The one-off migrations that
seeded them from the pre-table flight-history JSON are gone, along with the stores they read.

`system_visited` is **not** a subset of `system_seen` and there is no FK between them — 7
systems were arrived at without ever being plotted to.

### Linking POIs

`poi` is the dimension; `system_known.id_poi` and `system_body.id_poi` are the two
references into it. Each is written by a `poi.py` in the owning table's folder:

```
python etl/poi/refresh.py                           # dimension first
python etl/system_known/poi.py                      # system-level POIs
python etl/system_body/poi.py                       # body-level POIs, INSERTS bodies
python etl/poi/load.py                              # again, for systems/bodies counts
python etl/system_poi/refresh.py                    # the snapshot the overlay reads
```

The split between system-level and body-level is decided **once**, in `common/poi_link.py`.
If the two scripts disagreed about what counts as body-level, a POI would be written to both
tables or to neither.

`etl/system_body/poi.py` **inserts rows**: a Canonn report naming a body is evidence
that body exists, so a missing one is added with `source='canonn_codex'`, `body_no` -1 and `body_id` NULL
— we know it is there, not what *type* it is. That also makes its system count as explored,
so it leaves `system_predicted`.

**Nothing enforces either `id_poi`.** They are plain integers, like every reference here, so
both linkers re-validate in SQL after writing and print the dangling count —
`common.db.check_references` covers the same two.

### Resuming a batched load

A run that dies partway leaves whole completed batches plus untouched ones — never a
half-written one, because each batch is one statement. **Re-run the same command to
resume**: the merge matches on the key, so a finished batch is a no-op the second time.

`system_known` merges in `sector_id` ranges cut on a running row count (above).
`system_body` merges in buckets on `abs((system_id >> 3) % N)` — 8 for a delta, 128 for
anything catalogue-sized — and each bucket's slice of `transform.system_body` is rebuilt
from staging and merged before the next one starts, so a re-run needs no work table left
behind. **The `>> 3` matters**: the low three bits of an id64 are the mass code, so bucketing
on `system_id % 8` makes each bucket one mass class, and those buckets take from 35 s to
294 s.

To see which buckets a partial load reached, count per bucket rather than trusting the
total:

```sql
SELECT abs((system_id >> 3) % 8) AS bucket, count(*) FROM system_body GROUP BY 1 ORDER BY 1;
```
