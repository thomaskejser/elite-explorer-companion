# ETL conventions

How data gets into the databases. These rules are not stylistic — each one exists
because breaking it has cost us, or would silently corrupt a key.

## 0. Two databases

| file | what it is | who writes it | size |
|---|---|---|---|
| `elite_mapping_v2.duckdb` | **the model** — what the galaxy is, per Spansh/EDSM/EDAstro/Canonn. `main` holds the model, `staging` the raw ingests. | `etl/`, `scripts/ingest_sources.py` | ~60 GiB |
| `elite_mapping_v2_current.duckdb` | **app state** — what *this commander* has done: seen, visited, found. | the overlay, plus `etl/load_system_*.py` | MBs |

**The app writes to `elite_mapping_v2_current.duckdb` and to nothing else.** The model
is *background information*: the app reads it, and may never write to it.

1. **The model is derived.** Every row is reproducible from `input/` and `raw/` by
   re-running `etl/`. 
2. **The app runs while you fly.** It is a live HUD reacting to journal events.
3. **ETL only writes to the model database**

## 1. One folder per table

`etl/<table_name>/build.py` and `etl/<table_name>/load.py`, where `<table_name>` is
the **exact** DuckDB table name and matches `schema/<table_name>.sql`. The folder
names the table, the file names the job. No script may create two tables; if you need
two, write two scripts, in two folders.

The payoff is that "where does this table come from?" is answerable from the path
alone, in a database with several near-identical names — and that everything belonging
to one table sits together.

Each script reaches the repo root with
`sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))`.
Three levels, because the script is two directories deep. Get it wrong and `common/`
does not import at all.

## 2. build vs load

Two kinds of table, and the file layout tells you which is which:

| kind | source of truth | scripts |
|---|---|---|
| **Loaded** | `input/<table>.parquet` | `<table>/build.py` seeds the parquet; `<table>/load.py` merges it into the DB |
| **Derived** | other DB tables | `<table>/build.py` only — no `input/` file, no loader |

- `build.py` for a **loaded** table writes *only* the parquet and must **never touch
  the table**. It is a **one-time seeder**: once the `input/` file exists it refuses
  to run, and there is **no `--force`**. That file is authoritative and hand-editable,
  regenerating it from literals would discard those edits, and the script cannot know
  whether you meant that. **Corrections are made by hand.** A genuinely fresh seed
  means deleting the file first, knowingly.
- `load.py` is the only thing allowed to write a loaded table.
- `build.py` for a **derived** table writes the table directly, using the same merge
  semantics as a loader.
- Neither creates or reshapes a table. Both apply `schema/<table>.sql` (whose `CREATE`
  is `IF NOT EXISTS`, so a no-op), which also re-asserts its `COMMENT ON` text.

Don't put derived statistics in an `input/` file. `input/` means authoritative
input; a row count belongs in the DB and gets recomputed on load. `body.observed`
and `body.bodies` work this way — the parquet's copies are an ignored snapshot,
which is why a merge can report updates even when the file is untouched.

## 3. Merge; never drop

**No `CREATE OR REPLACE TABLE`. No `DROP TABLE`. No truncate-and-reload.** Use
`CREATE TABLE IF NOT EXISTS` plus `INSERT ... WHERE NOT EXISTS` and `UPDATE ... FROM`.

- Match on the **natural key**, never the surrogate id — `(type, body)` for `body`,
  `(type, sub_type)` for `body_type_census`, `sector` for `sector`. `region` is the
  exception that proves the rule: its `region_id` is the GAME's id, not ours, so the
  loader matches on it and takes it as given rather than allocating `max+1`.
- Insert unseen rows. Update matched rows' attributes. **Never renumber a
  surrogate id.**
- Allocate a new surrogate id as `max+1`. Honour an id supplied by the input file
  when it is free; otherwise reassign.
- Rows in the table but absent from the source are **left in place** and reported.
  Their keys are **retired, never reused**. Deleting one is a manual decision,
  because something may already reference it.
- Report `inserted / updated / orphaned`. A no-op run must *look* like a no-op.

**There are exactly THREE documented exceptions, and all three delete for the same
reason: the row is not stale, it is WRONG.**

**1. `system_predicted`.** The rule above protects surrogate keys that *other tables point
at*; nothing has a foreign key into `system_predicted`. More to the point, it is a **prediction** table: once a system has
been explored — or one of its bodies turns up in a catalogue - the row is deleted. 
Its builder deletes rows the pool no longer produces and says how many.
Any future table that predicts rather than records may follow it; a table that *records*
must not. `system_phenomenon` is the worked example on the other side of that line: it
is built from the same volatile codex dumps, and it still **never deletes**, because a
phenomenon that drops out of a dump was still observed.

**2. `system_catalog_alias`.** Its rows are ASSERTIONS ("these two catalogue names are one
star"), its key is the assertion itself, and nothing has a foreign key into it. A retracted
edge is therefore not a retired key but a claim withdrawn — and one that does damage while
it sits there, because `etl/system_catalog/load.py` copies a `system_id` across it and thereby
merges two different stars. That is not theoretical: the first seed chained 159 unrelated
names onto one game system through a single bad CNS3 field, and merge-never-drop would have
made the fix impossible to apply. The paired rule is that the resolution it feeds is
**recomputed, not sticky** — every alias-resolved `system_catalog.system_id` is reset to
NULL and re-derived on each load, so correcting the parquet is enough to correct the model.
A hand-editable input file has to be able to take something BACK.

**3. `system_unfound`.** A row is the claim that a catalogued star cannot be found in the
game. An alias that resolves it, or a commander who visits it and puts it in a dump, makes
that claim FALSE — and a hunting list that keeps offering places already settled is worse
than no list. Nothing has a foreign key into it. Same line as `system_predicted`: it
asserts rather than records.

### Never derive a system name by concatenating sector

`sector.is_crafted` is TRUE for **424 real named sectors** ("NGC 2546 Sector",
"Col 359 Sector"), not just for the `sector_id = 0` sentinel row that is literally named
`'crafted'`. Only `sector_id = 0` means "this system's name stands alone". Treating
`is_crafted` as that test silently strips the prefix off 5M systems and makes them look
absent; treating sector_id 0 as a prefix produces `'crafted Sol'`. Both mistakes were
made here, and both manufactured a multi-million-row phantom "gap".

**Use `staging.sys_bridge` (id64 → system_id) instead.** It is the only reliable join
between a dump and `system_known`, and it resolves all but ~1,000 rows of every source
we hold.

Why it matters: `body.body_id` is a stable `INTEGER PRIMARY KEY` that other tables
key to. `CREATE OR REPLACE` would both renumber it and **silently drop any foreign
key pointing at it** — DuckDB does not warn you.

### Comparing for changes

Use `IS DISTINCT FROM`, not `<>`. After an additive migration a new column is `NULL`
on existing rows, and `NULL <> 1` evaluates to `NULL`, so `<>` skips the backfill
entirely and the column stays empty forever. This bit us for real on a migrated
column: the merge reported success while leaving the column all NULL.

**Round any column you derive from a float aggregate before you store it.** `avg()`
and `sum()` over millions of rows are evaluated in parallel with
`preserve_insertion_order=false`, so the summation *order* varies between runs, and
float addition is not associative — the last bits move. `IS DISTINCT FROM` is doing
its job when it then flags every row as changed, but the run stops looking like the
no-op it was. `etl/system_predicted/build.py` reported 2.3M spurious updates for exactly
this reason; rounding the probabilities to 6 dp at the point of computation fixed it.
Rounding is not cosmetic here — it is what makes the merge idempotent.

### Schema changes: THE MODEL IS CREATED WITH THE DATABASE AND NEVER ALTERED

`schema/<table>.sql` is the **one** definition of a table — its DDL *and* its
`COMMENT ON` text. Every table is created from those files when the database is made,
in dependency-tier order (parents before children, or the foreign keys will not
resolve). **After that the shape does not change.** To change a table: edit its
`schema/<table>.sql` and build a new database.

*** THERE IS NO SCRIPT THAT BUILDS A FRESH MODEL DATABASE, AND WRITING ONE IS THE FIRST
STEP OF ANY SHAPE CHANGE. *** It has to create every table from `schema/<table>.sql` in
dependency-tier order and then `INSERT ... SELECT` the rows across from the current file.
Budget real time for it: a plain streaming copy moves 570M rows in about 134 seconds, and
everything beyond that is CONSTRAINT MAINTENANCE, which is where it gets expensive.
Measured on `system_body`: no constraints 134s, PRIMARY KEY only 738s, PRIMARY KEY plus a
composite UNIQUE dead at 14.9 GiB after 898s. That measurement is why
`schema/system_body.sql` does not declare that UNIQUE.


## 3b. download -> staging -> merge -> main

The raw provider snapshots live in the **`staging`** schema; the model lives in
**`main`**. Nothing downloaded is ever written straight into a model table.

```
  download / parse          scripts/ingest_*.py, scripts/parse_spansh.py
        |                   write staging.<source>   (CREATE OR REPLACE is fine here:
        v                    a snapshot is replaced wholesale by the next download)
  staging.spansh_body, staging.edsm_star_system, staging.canonn_codex_event, ...
        |                   etl/<table>/build.py, etl/<table>/load.py
        v                   merge semantics -- insert unseen, update matched, never drop
  main.system_known, main.system_body, main.poi, ...
```


Point any script at the new database with the **`ELITE_DB`** environment variable:

```
ELITE_DB=C:/Source/elite_mapping/elite_mapping_v2.duckdb python etl/poi/build.py
```

### `staging` now holds two very different kinds of table

| kind | example | may be dropped? |
|---|---|---|
| **RAW SOURCE** | `staging.spansh_body` | **NO.** Re-obtainable only by re-downloading and re-parsing — hours. Their comments begin `RAW SOURCE`. |
| **work table** | `staging.src_body`, `staging.sys_bridge` | Yes. Intermediate state, `CREATE OR REPLACE`d freely — though `sys_bridge` is resume state mid-load. |

`--clean-staging`, on `etl/system_known/build.py` and `etl/system_body/build.py`, holds that
line: it reads the comments, **keeps** every table beginning `RAW SOURCE`, and
`TRUNCATE`s the rest rather than dropping them, so the work tables come back empty
instead of missing. `--include-raw` overrides the allow-list and takes 894M rows of
irreplaceable source with it — the one flag here that costs hours of re-download.

## 4. Where things live

| folder | contents |
|---|---|
| `etl/` | one folder per table, holding its `build.py` / `load.py` |
| `schema/` | `<table>.sql` per table — DDL **and** its COMMENT ON |
| `common/` | shared code, imported not copied |
| `input/` | authoritative hand-editable source parquets |
| `scripts/` | ingest and non-per-table utilities |

### Shared code in `common/`

Anything used by more than one script goes in `common/` at the repo root, not
copy-pasted.

## 5. Comments describe the CODE AS IT IS, never how it got there

**A comment is documentation, not a changelog.** Git holds the history; a comment that
narrates it goes stale silently and costs every future reader the time to work out
whether it still applies. Write every comment as a statement about the code that is
there now.


**Say it once.** A rewritten paragraph that repeats its own point, a docstring that
states the same rule twice in different words, and a sentence left half-finished by an
edit are all as much of a defect as a wrong comment. Every claim earns its line or goes.

This applies to `COMMENT ON` text exactly as it does to `#` and docstrings — see 6.

## 6. Every table AND every column carries a COMMENT

Non-negotiable, and **NOTHING ENFORCES IT** — there is no repo-wide checker, so the bar
is held by review alone. (`scripts/apply_schema.py` refuses to finish on an undocumented
column, but only for a view.) Comments must state what the table **is**, where it came
**from**, and what it is **not** (slice vs full catalogue, bound vs estimate). Every
expensive mistake in this project has been a provenance mistake.

**Columns too.** Every column of every table we own carries a `COMMENT ON COLUMN`.
A column comment should say what the value *means* and what it must not be
used for — `body.is_terraform_candidate` records that Earth-like is deliberately
FALSE and that the column must not be used for scan value; `sector.radius` records
that it is a lower bound, not the sector size.

DDL and comment text — table and all columns — live **together in
`schema/<table>.sql`**, one file per table, resolved by `common.db.comment_file(table)`
and applied via `apply_comment_file()`. One file, because a schema change and the
documentation of that change must not be able to drift apart. Applying the file is safe
at any time: its `CREATE TABLE IF NOT
EXISTS` is a no-op on an existing table, so re-asserting comments cannot reshape
anything. **Re-assert it after any
schema change** — a migration is the one thing that silently drops comments, which is
why every builder calls `apply_comment_file()` after its merge and then prints its
`column comments: n/n` count.

Every table above also has `schema/<table>.sql`.

## The model database

`elite_mapping_v2.duckdb` is self-contained: `main` holds the `etl/`-managed tables,
`staging` holds the provider ingests they are built from -- 62 tables, 23 of them
commented `RAW SOURCE`, read through 19 views that give each feed one stable name. Everything needed to rebuild any
model table is inside that one file, so a builder never depends on a download still being
on disk.

**The `id_poi` foreign keys bind, and that is only possible because the tables were
created together from `schema/<table>.sql`.** DuckDB has no `ALTER TABLE ADD CONSTRAINT`,
so a key declared after a table exists is decoration — 7 foreign keys are enforced here,
and adding an eighth to an existing table means a fresh build (above).

**`system_known.id64` carries the id64 -> system_id mapping**, so nothing has to keep a
transient staging table alive to preserve a join. `common/poi_link.py` and
`etl/system_phenomenon/build.py` join it directly.

**`id64` is deliberately NOT UNIQUE.** It is unique in the game, but 96 id64 values sit
on two `system_known` rows each — the same system recorded under two name spellings
(`CoRoT-9`/`Corot-9`, `Eskimo Sector VE-P b6-0`/`NGC 2392 Sector VE-P b6-0`). Those 192
rows are a duplicate-system defect the column *exposed*; de-duplicate them and the key
can be declared on the next fresh build.


### Schema files

`schema/<table>.sql` holds the CREATE TABLE DDL **and** the COMMENT ON text for that
table. A new model table needs that one file. A table with **no** foreign key into it
can simply be created by its own loader (`apply_comment_file()` runs `CREATE TABLE IF NOT
EXISTS`); one that other tables must point AT has to exist before them, which means a
fresh build in dependency-tier order — see the note above about there being no such
script right now.

## Current inventory

| table | kind | scripts |
|---|---|---|
| `body` | loaded | `etl/body/build.py`, `etl/body/load.py` |
| `region` | loaded, **hand-maintained** | `etl/region/build.py`, `etl/region/load.py` |
| `body_type_census` | derived | `etl/body_type_census/build.py` |
| `sector` | derived | `etl/sector/build.py` |
| `system_known` | derived | `etl/system_known/build.py` (`--limit N` / `--all`) |
| `system_body` | derived, populated | `etl/system_body/build.py` (`--limit N` / `--all`) |
| `poi` | loaded, **hand-curated** | `etl/poi/build.py`, `etl/poi/load.py` |
| `system_predicted` | derived | `etl/system_predicted/build.py` (`--build`) |
| `system_phenomenon` | derived | `etl/system_phenomenon/build.py` (`--build`) |
| `carrier` | derived | `etl/carrier/build.py` (needs `ingest_sources.py --full --only edastro_fleet_carrier`) |
| `system_catalog` | loaded | `etl/system_catalog/build.py` (**network**), `etl/system_catalog/load.py` |
| `system_catalog_alias` | loaded, **deletes** | `etl/system_catalog_alias/build.py` (**network**), `etl/system_catalog_alias/load.py` |
| `system_neutron` | derived | `etl/system_neutron/build.py` |
| `carrier_position` | derived | `etl/carrier_position/build.py` (re-run after every `carrier` load) |
| `system_poi` | derived | `etl/system_poi/build.py` (re-run after either `--poi` pass) |
| `system_unfound` | derived | `etl/system_unfound/build.py` |
| `system_all` | derived **VIEW**, not a table | `scripts/apply_schema.py system_all` — no builder; a view stores nothing |

**Three of these tables exist only so the overlay does not scan a giant one.**
`system_neutron`, `carrier_position` and `system_poi` add no facts — every value is copied
from `system_known`, `system_body`, `carrier` or `sector`. The HUD asks their question on
every jump and DuckDB has nothing to probe on: 2,524 carriers resolved through
`system_known` scanned all 200,676,922 rows (1,440 ms warm, 5,224 cold), and the 10,023
`system_body` rows carrying an `id_poi` scanned all 577,639,044. Materialised: 1.8 ms and
1.6 ms. **They are snapshots of a join and go stale silently** — a carrier that jumped
keeps its old position until the builder runs again. Re-run each after its source loads;
both are merge-only, so a no-op run looks like one.

**The two catalogue tables are the only builders that read the NETWORK** (VizieR/CDS and
the NASA Exoplanet Archive), because real star catalogues are astronomy rather than an
Elite data source: they change once a decade, so mirroring 4.8M rows of them into
`staging` to read straight back out would buy nothing. Downloads cache in `raw/catalog/`.

**Load them in this order** — the alias edges must exist before the catalogue walks them,
and re-running the second is what applies any correction to the first:

```
python etl/system_catalog_alias/load.py   # 1.14M "same star" assertions
python etl/system_catalog/load.py         # resolves by name, then walks the edges
```

### App-state tables — `elite_mapping_v2_current.duckdb`

Created once by `python scripts/create_current_db.py`, which applies every
`schema/<table>.sql` named in `common/current.py:CURRENT_TABLES`. **The model is created
when the database is made and does not change after that**; loaders merge into tables
that already exist and never create one. Schema files live in the same flat `schema/`
directory as the model's — the filename cannot say which database a table belongs to,
so `CURRENT_TABLES` is the only thing that does. Add a table there or
`create_current_db.py` will not build it, silently.

All five tables — `system_seen`, `system_visited`, `system_confirmed`, `poi_visited`
and `system_wrong` — are written by the overlay and have no loader. The one-off
migrations that seeded them from the pre-table flight-history JSON are gone, along with
the stores they read.

`system_visited` is **not** a subset of `system_seen` and there is no FK between them —
7 systems were arrived at without ever being plotted to.

### Linking POIs

`poi` is the dimension; `system_known.id_poi` and `system_body.id_poi` are the two
foreign keys into it. Neither is written by a script of its own — the table's **owning
builder** writes it, under a `--poi` phase that runs standalone:

```
python etl/poi/build.py && python etl/poi/load.py   # dimension first
python etl/system_known/build.py --poi              # system-level POIs
python etl/system_body/build.py  --poi              # body-level POIs, INSERTS bodies
python etl/poi/load.py                              # again, for systems/bodies counts
```

The split between system-level and body-level is decided **once**, in
`common/poi_link.py`. If the two scripts disagreed about what counts as body-level, a
POI would be written to both tables or to neither.

`etl/system_body/build.py --poi` **inserts rows**: a Canonn report naming a body is evidence
that body exists, so a missing one is added with `source='canonn_codex'` and `body_id`
NULL — we know it is there, not what *type* it is. That also makes its system count as
explored, so it leaves `system_predicted`.

**A foreign key added after the table exists is not enforced.** DuckDB has no
`ALTER TABLE ADD CONSTRAINT`, so the `FOREIGN KEY (id_poi)` in either `CREATE` binds
only on a fresh build; here `id_poi` is a plain integer. Both `--poi` phases therefore
re-validate it in SQL after writing and print the dangling count. Columns in this
position belong in the script's `ADDITIVE`/`EXTRA` map, never in `CORE`/`WANT` — the
schema-drift guard compares against those and would otherwise demand a
create-copy-swap of a 570M-row table.

### Resuming a bucketed load

`system_known` (200.7M rows) and `system_body` (577.6M) merge in hash buckets, and a run
that dies partway leaves whole completed buckets plus untouched ones — never a half-written
bucket, because each bucket is one `INSERT`. **Re-run the same command to resume**; the
`NOT EXISTS` guard makes finished buckets no-ops. Do not clean staging first: the
`staging` tables are the resume state, and `staging.src_body` alone costs a
569.7M × 200.7M join to rebuild. Only `--rebuild-staging` forces that, so omit it.

To see how far a load got, count rows per bucket rather than trusting the total —
`system_body` buckets on `system_id % 128`, `system_known` on `hash(name) % 64`:

```sql
SELECT system_id % 128 AS bucket, count(*) FROM system_body GROUP BY 1 ORDER BY 1;
```

Phases 1–2 are re-entrant but not all free: Phase 1 is skipped outright when
`staging.src_body` exists, whereas Phase 2's `staging.sb_disc` is a `CREATE OR REPLACE`
and is always recomputed.

## No deviations

Every script in the repo follows this document. `etl/` is the pattern for anything new —
one script per table, named for the table it writes; cross-cutting utilities that are not
per-table stay in `scripts/`.
