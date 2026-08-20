# ETL conventions

How data gets into `elite_mapping.duckdb`. These rules are not stylistic — each one
exists because breaking it has cost us, or would silently corrupt a key.

## 1. One script per table

`etl/build_<table_name>.py` and `etl/load_<table_name>.py`, where `<table_name>` is
the **exact** DuckDB table name. No script may create two tables; if you need two,
write two scripts. (A former `build_body_census.py` created two tables at once; it
was split for exactly this reason.)

The payoff is that "where does this table come from?" is answerable from the
filename alone, in a database with 31 tables and several near-identical names.

## 2. build vs load

Two kinds of table, and the file layout tells you which is which:

| kind | source of truth | scripts |
|---|---|---|
| **Loaded** | `input/<table>.parquet` | `build_<table>.py` seeds the parquet; `load_<table>.py` merges it into the DB |
| **Derived** | other DB tables | `build_<table>.py` only — no `input/` file, no loader |

- `build_` for a **loaded** table writes *only* the parquet and must **never touch
  the table**. It is a **one-time seeder**: once the `input/` file exists it refuses
  to run, and there is **no `--force`**. That file is authoritative and hand-editable,
  regenerating it from literals would discard those edits, and the script cannot know
  whether you meant that. **Corrections are made by hand.** A genuinely fresh seed
  means deleting the file first, knowingly.
- `load_` is the only thing allowed to write a loaded table.
- `build_` for a **derived** table writes the table directly, using the same merge
  semantics as a loader.
- Neither creates or reshapes a table. Both apply `schema/<table>.sql` (whose `CREATE`
  is `IF NOT EXISTS`, so a no-op) and then `assert_shape()`.

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

**The one documented exception is `system_predicted`, which deletes.** The rule above
protects surrogate keys that *other tables point at*; nothing has a foreign key into
`system_predicted`. More to the point, it is a **prediction** table: once a system has
been explored — or one of its bodies turns up in a catalogue — the row is not a retired
key, it is a **wrong row**, and leaving it in place would keep offering a target that no
longer exists. Its builder deletes rows the pool no longer produces and says how many.
Any future table that predicts rather than records may follow it; a table that *records*
must not. `system_phenomenon` is the worked example on the other side of that line: it
is built from the same volatile codex dumps, and it still **never deletes**, because a
phenomenon that drops out of a dump was still observed.

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
no-op it was. `build_system_predicted.py` reported 2.3M spurious updates for exactly
this reason; rounding the probabilities to 6 dp at the point of computation fixed it.
Rounding is not cosmetic here — it is what makes the merge idempotent.

### Schema changes: THE MODEL IS CREATED WITH THE DATABASE AND NEVER ALTERED

`schema/<table>.sql` is the **one** definition of a table — its DDL *and* its
`COMMENT ON` text. Every table is created from those files when the database is made,
by `scripts/migrate_new_model.py`, in dependency-tier order. **After that the shape
does not change.** To change a table: edit its `schema/<table>.sql` and build a new
database.

Builders call `common.db.assert_shape(con, table)`, which compares the live table to
what the file declares and **exits** on any difference. They do not migrate.

This replaced `ensure_columns()` and additive `ALTER TABLE ADD COLUMN`, and the reason
is what that cost. **DuckDB has no `ALTER TABLE ADD CONSTRAINT`,** so a column added
after creation can *never* carry a PRIMARY KEY, UNIQUE or FOREIGN KEY. `system_known.id_poi`
sat as an unenforced integer for exactly that reason; every big builder grew a
`CORE`/`ADDITIVE` split and a drift guard to work around it; and a schema file that had
quietly fallen behind its table silently dropped `sector.region_id` during a migration.
Creating once and asserting thereafter removes all of it: constraints bind, there is one
definition, and drift is an error instead of a silent repair.

`has_primary_key()` remains for reporting on databases that predate this rule.

## 3b. download -> staging -> merge -> main

The raw provider snapshots live in the **`staging`** schema; the model lives in
**`main`**. Nothing downloaded is ever written straight into a model table.

```
  download / parse          scripts/ingest_*.py, scripts/parse_spansh.py
        |                   write staging.<source>   (CREATE OR REPLACE is fine here:
        v                    a snapshot is replaced wholesale by the next download)
  staging.spansh_body, staging.edsm_star_system, staging.canonn_codex_event, ...
        |                   etl/build_*.py, etl/load_*.py
        v                   merge semantics -- insert unseen, update matched, never drop
  main.system_known, main.system_body, main.poi, ...
```

**Builders were not rewritten to say `staging.spansh_body`.** `common.db.connect()` sets
`search_path='main,staging'`, so an unqualified name resolves in whichever schema holds
it. `main` is listed FIRST deliberately: it is the default for `CREATE`, so anything a
script creates unqualified still lands in `main`, and a model table always wins a name
lookup against a staging table of the same name. In the old database the raw tables sit
in `main` as well, so the setting is a no-op there and the same scripts run against both.

Point any script at the new database with the **`ELITE_DB`** environment variable:

```
ELITE_DB=C:/Source/elite_mapping/elite_mapping_v2.duckdb python etl/build_poi.py
```

### `staging` now holds two very different kinds of table

| kind | example | may be dropped? |
|---|---|---|
| **RAW SOURCE** | `staging.spansh_body` | **NO.** Re-obtainable only by re-downloading and re-parsing — hours. Their comments begin `RAW SOURCE`. |
| **work table** | `staging.src_body`, `staging.sys_bridge` | Yes. Intermediate state, `CREATE OR REPLACE`d freely — though `sys_bridge` is resume state mid-load. |

`build_system_known.py --clean-staging` drops the schema **indiscriminately** and would
take 894M rows of irreplaceable source with it. It needs an allow-list before it is
pointed at a database where the two kinds coexist. Until then, do not run it there.

## 4. Where things live

| folder | contents |
|---|---|
| `etl/` | one `build_<table>.py` / `load_<table>.py` per table |
| `schema/` | `<table>.sql` per table — DDL **and** its COMMENT ON — plus `comment_tables.py` |
| `common/` | shared code, imported not copied |
| `input/` | authoritative hand-editable source parquets |
| `scripts/` | legacy pipeline + non-per-table utilities |

### Shared code in `common/`

Anything used by more than one script goes in `common/` at the repo root, not
copy-pasted. Currently `common/db.py`: `connect()` (with the 6GB limit and
`preserve_insertion_order=false` that the big tables need), `ensure_columns()`,
`has_primary_key()`, `report_merge()`, `apply_comment_file()`.

`etl/` scripts reach it with:

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import ROOT, INPUT, connect, report_merge
```

## 5. Every table AND every column carries a COMMENT

Non-negotiable — see `schema/comment_tables.py`, which **exits 1** listing any
undocumented table. Comments must state what the table **is**, where it came
**from**, and what it is **not** (slice vs full catalogue, bound vs estimate). Every
expensive mistake in this project has been a provenance mistake.

**Columns too.** Every column of every table we own carries a `COMMENT ON COLUMN`.
`comment_tables.py` **exits 1** listing any undocumented column on an `etl/`-managed
table. A column comment should say what the value *means* and what it must not be
used for — `body.is_terraform_candidate` records that Earth-like is deliberately
FALSE and that the column must not be used for scan value; `sector.radius` records
that it is a lower bound, not the sector size.

DDL and comment text — table and all columns — live **together in
`schema/<table>.sql`**, one file per table, resolved by `common.db.comment_file(table)`
and applied via `apply_comment_file()`. One file, because a schema change and the
documentation of that change must not be able to drift apart; they were briefly split
and that was a mistake. Applying the file is safe at any time: its `CREATE TABLE IF NOT
EXISTS` is a no-op on an existing table, so re-asserting comments cannot reshape
anything. **Re-assert it after any
schema change** — a migration is the one thing that silently drops comments, which is
why every builder calls `apply_comment_file()` after its merge and then prints its
`column comments: n/n` count.

A table whose builder owns its comment is registered in `schema/comment_tables.py`'s
`SELF_DOCUMENTED` map; that script then only *verifies* the comment is non-empty
rather than overwriting it.

Every table above also has `schema/<table>.sql`.

## The v2 database

`elite_mapping_v2.duckdb` holds the new model and nothing else: the nine
`etl/`-managed tables, no staging. It is built by `scripts/migrate_new_model.py --fresh`
and checked by `scripts/verify_new_model.py`.

**Two things it buys that the old file cannot be given.**

1. **The `id_poi` foreign keys actually bind.** DuckDB has no `ALTER TABLE ADD
   CONSTRAINT`, so a key declared after the table exists is decoration. Creating the
   tables fresh from `schema/<table>.sql` is the only way to enforce them, and it takes
   the count from 5 foreign keys to 7.
2. **Disk comes back.** `DROP TABLE` frees pages for reuse *inside* the file; it never
   shrinks it. Writing a new file is the only mechanism DuckDB has.

**No staging is copied, because `system_known.id64` now exists.** That mapping used to
live only in `staging.sys_bridge`, which made a transient staging table load-bearing and
not reconstructible without the raw dumps. `common/poi_link.py` and
`build_system_phenomenon.py` now join `system_known.id64` directly and produce
byte-identical results, so the model is self-contained.

**`id64` is deliberately NOT UNIQUE.** It is unique in the game, but 96 id64 values sit
on two `system_known` rows each — the same system recorded under two name spellings
(`CoRoT-9`/`Corot-9`, `Eskimo Sector VE-P b6-0`/`NGC 2392 Sector VE-P b6-0`). Those 192
rows are a duplicate-system defect the column *exposed*; de-duplicate them and the key
can be declared on a fresh build.

**What v2 deliberately does NOT hold:** the raw ingests and the legacy model. So v2 can
be READ and QUERIED, but `build_system_predicted.py`, `build_system_phenomenon.py` and
the `--poi` phases cannot yet be RE-RUN against it — they still read `sys_feat`,
`bhwr_system`, `star_agg`, `bhwr_candidates`, `theorised_system`,
`edastro_boxel_stats`, the codex dumps and `spansh_body`. Finishing migration steps 2-4
is what closes that gap. **Do not delete the old file until they are done.**

### Schema files

`schema/<table>.sql` holds the CREATE TABLE DDL **and** the COMMENT ON text for that
table. A new model table needs that one file, and it must be listed in the right
dependency tier in `migrate_new_model.py` or the foreign keys will not resolve.

## Current inventory

| table | kind | scripts |
|---|---|---|
| `body` | loaded | `etl/build_body.py`, `etl/load_body.py` |
| `region` | loaded, **hand-maintained** | `etl/build_region.py`, `etl/load_region.py` |
| `body_type_census` | derived | `etl/build_body_type_census.py` |
| `sector` | derived | `etl/build_sector.py` |
| `system_known` | derived | `etl/build_system_known.py` (`--limit N` / `--all`) |
| `system_body` | derived, populated | `etl/build_system_body.py` (`--limit N` / `--all`) |
| `poi` | loaded, **hand-curated** | `etl/build_poi.py`, `etl/load_poi.py` |
| `system_predicted` | derived | `etl/build_system_predicted.py` (`--build`) |
| `system_phenomenon` | derived | `etl/build_system_phenomenon.py` (`--build`) |

### Linking POIs

`poi` is the dimension; `system_known.id_poi` and `system_body.id_poi` are the two
foreign keys into it. Neither is written by a script of its own — the table's **owning
builder** writes it, under a `--poi` phase that runs standalone:

```
python etl/build_poi.py && python etl/load_poi.py   # dimension first
python etl/build_system_known.py --poi              # system-level POIs
python etl/build_system_body.py  --poi              # body-level POIs, INSERTS bodies
python etl/load_poi.py                              # again, for systems/bodies counts
```

The split between system-level and body-level is decided **once**, in
`common/poi_link.py`. If the two scripts disagreed about what counts as body-level, a
POI would be written to both tables or to neither.

`build_system_body.py --poi` **inserts rows**: a Canonn report naming a body is evidence
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

`system_known` (197.6M rows) and `system_body` (570M) merge in hash buckets, and a run
that dies partway leaves whole completed buckets plus untouched ones — never a half-written
bucket, because each bucket is one `INSERT`. **Re-run the same command to resume**; the
`NOT EXISTS` guard makes finished buckets no-ops. Do not clean staging first: the
`staging` tables are the resume state, and `staging.src_body` alone costs a
569.7M × 197.6M join to rebuild. Only `--rebuild-staging` forces that, so omit it.

To see how far a load got, count rows per bucket rather than trusting the total —
`system_body` buckets on `system_id % 128`, `system_known` on `hash(name) % 64`:

```sql
SELECT system_id % 128 AS bucket, count(*) FROM system_body GROUP BY 1 ORDER BY 1;
```

Phases 1–2 are re-entrant but not all free: Phase 1 is skipped outright when
`staging.src_body` exists, whereas Phase 2's `staging.sb_disc` is a `CREATE OR REPLACE`
and is always recomputed.

## Known deviation

The legacy prediction pipeline in `scripts/` (`01_normalize.sql`, `03a`–`03w`,
`build_candidates.py`, `ingest_*.py`, …) **predates all of this**: those scripts use
`CREATE OR REPLACE TABLE`, several create more than one table, and they are not
named for their output. They are not broken, and migrating them is a separate piece
of work. Treat `etl/` as the pattern for anything new, and migrate a legacy script
when you next have reason to touch it. Cross-cutting utilities that are not
per-table (`pgnames.py`) stay in `scripts/`.
