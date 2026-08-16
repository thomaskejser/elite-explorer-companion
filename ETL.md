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

### Schema changes

Additive only, via `ALTER TABLE ADD COLUMN` — use `common.db.ensure_columns()`,
which is idempotent. **Constraints cannot be retrofitted:** DuckDB has no
`ALTER TABLE ADD PRIMARY KEY`, so a table created before its builder declared a key
stays unconstrained, and the `CREATE` only applies the key on a fresh database.
Scripts should check `has_primary_key()` and say so rather than pretend.

## 4. Where things live

| folder | contents |
|---|---|
| `etl/` | one `build_<table>.py` / `load_<table>.py` per table |
| `schema/` | `<table>_comment.sql` per table, plus `comment_tables.py` |
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

Comment text — table and all columns — lives in **`schema/<table>_comment.sql`**, one
file per table, resolved by `common.db.comment_file(table)` and applied via
`apply_comment_file()`. Keeping it in `schema/` rather than beside the loader means the
seeder and the loader assert identical text and there is a single place to edit. **Re-assert it after any
schema change** — a migration is the one thing that silently drops comments, which is
why every builder calls `apply_comment_file()` after its merge and then prints its
`column comments: n/n` count.

A table whose builder owns its comment is registered in `schema/comment_tables.py`'s
`SELF_DOCUMENTED` map; that script then only *verifies* the comment is non-empty
rather than overwriting it.

Every table above also has `schema/<table>_comment.sql`.

## Current inventory

| table | kind | scripts |
|---|---|---|
| `body` | loaded | `etl/build_body.py`, `etl/load_body.py` |
| `region` | loaded, **hand-maintained** | `etl/build_region.py`, `etl/load_region.py` |
| `body_type_census` | derived | `etl/build_body_type_census.py` |
| `sector` | derived | `etl/build_sector.py` |
| `system_known` | derived | `etl/build_system_known.py` (`--limit N` / `--all`) |
| `system_body` | derived, populated | `etl/build_system_body.py` (`--limit N` / `--all`) |
| `system_predicted` | derived | `etl/build_system_predicted.py` (`--build`) |

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
