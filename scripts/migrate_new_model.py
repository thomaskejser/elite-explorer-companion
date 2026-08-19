"""Build a FRESH elite_mapping_v2.duckdb holding only the new model.

WHY A NEW FILE. Constraints cannot be retrofitted in DuckDB -- no ALTER TABLE ADD
PRIMARY KEY, no ADD CONSTRAINT -- so system_known.id_poi and system_body.id_poi are
unenforced integers in the old database and can never become real foreign keys there.
Creating the tables fresh from schema/<table>.sql is the only way to bind them. It is
also the only way DuckDB ever returns disk: DROP frees pages for reuse inside the file,
it does not shrink it.

ORDER IS A DEPENDENCY ORDER, not alphabetical. Tier 1 has no parents; tier 2 needs
tier 1; tier 3 needs tier 2. Loading out of order fails the foreign key checks that
are the entire point of doing this.

A PLAIN INSERT ... SELECT IS ALL THIS NEEDS, and an earlier version of this script was
wrong to chunk it. With preserve_insertion_order=false the copy streams in constant
memory: 570.8M rows in 134s flat. Every second beyond that, and every out-of-memory
failure, came from CONSTRAINT maintenance, not from the copy -- measured on
system_body: no constraints 134s, PRIMARY KEY only 738s, PRIMARY KEY plus the composite
(system_id, system_body) UNIQUE dead at 14.9GiB after 898s. That is why
schema/system_body.sql no longer declares that one UNIQUE.

NO STAGING IS COPIED. system_known.id64 now holds the id64 -> system_id mapping that
used to exist ONLY in staging.sys_bridge, so the model is self-contained and a
197.5M-row staging table no longer has to ride along just to keep a join alive.

Usage:  python scripts/migrate_new_model.py [--fresh]
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import duckdb
from common.db import ROOT, SCHEMA, TEMP_DIR

OLD = ROOT / "elite_mapping.duckdb"
NEW = ROOT / "elite_mapping_v2.duckdb"

TIERS = [
    ("tier 1  dimensions, no parents",
     ["body", "region", "sector", "poi", "body_type_census"]),
    ("tier 2  needs tier 1",
     ["system_known"]),
    ("tier 3  needs system_known",
     ["system_body", "system_phenomenon", "system_predicted"]),
]

ALL = [t for _, ts in TIERS for t in ts]

if "--fresh" in sys.argv and NEW.exists():
    NEW.unlink()
    for suf in (".wal",):
        p = NEW.with_suffix(NEW.suffix + suf)
        if p.exists():
            p.unlink()
    print(f"removed existing {NEW.name}")

con = duckdb.connect(str(NEW))
for s in ("SET memory_limit='26GB'", "SET threads=6",
          "SET preserve_insertion_order=false", "SET enable_progress_bar=false"):
    con.execute(s)
TEMP_DIR.mkdir(parents=True, exist_ok=True)
con.execute(f"SET temp_directory='{TEMP_DIR.as_posix()}'")
con.execute("SET max_temp_directory_size='400GB'")
con.execute(f"ATTACH '{OLD.as_posix()}' AS old (READ_ONLY)")

# ---------------------------------------------------------------- DDL --------
print("applying schema/<table>.sql ...")
for t in ALL:
    f = SCHEMA / f"{t}.sql"
    if not f.exists():
        sys.exit(f"missing {f} -- every model table needs its DDL file")
    con.execute(f.read_text(encoding="utf-8"))
print(f"  {len(ALL)} tables created with PRIMARY KEYs and FOREIGN KEYs BOUND")

# ---------------------------------------------------------------- copy -------
def cols(table):
    return [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]

total = 0
for label, tables in TIERS:
    print(f"\n{label}")
    for t in tables:
        have = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        want = con.execute(f"SELECT count(*) FROM old.main.{t}").fetchone()[0]
        if have == want and have:
            print(f"  {t:<20} already complete, {have:,} rows -- skipped")
            total += have
            continue
        if have:
            sys.exit(f"{t} holds {have:,} of {want:,} -- a PARTIAL copy. Drop the table "
                     f"and re-create it from schema/{t}.sql, or re-run with --fresh. "
                     f"Topping it up would duplicate rows.")
        c = cols(t)
        oc = [r[0] for r in con.execute(f"DESCRIBE old.main.{t}").fetchall()]
        # BIDIRECTIONAL, and it has to be. An earlier version only checked "new column
        # the old database lacks", so when schema/sector.sql forgot region_id -- a
        # column build_sector.py adds with ensure_columns() rather than in its CREATE --
        # the copy silently dropped it. Data loss that reports success is the exact
        # failure ETL.md exists to prevent, so BOTH directions are fatal here.
        missing = [x for x in c if x not in oc]
        dropped = [x for x in oc if x not in c]
        if missing:
            sys.exit(f"{t}: old database lacks {missing}")
        if dropped:
            sys.exit(f"{t}: schema/{t}.sql omits {dropped}, which the old database HAS. "
                     f"Copying would silently discard those columns. Add them to the "
                     f"DDL (append them -- ALTER TABLE ADD COLUMN only appends, so a "
                     f"fresh build must end up in the same column order).")
        sel = ", ".join(f'"{x}"' for x in c)
        t0 = time.time()
        con.execute(f"INSERT INTO {t} ({sel}) SELECT {sel} FROM old.main.{t}")
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        total += n
        print(f"  {t:<20} {n:>14,} rows  ({time.time() - t0:,.1f}s)", flush=True)

# ------------------------------------------------------------- comments ------
print("\napplying schema/<table>_comment.sql ...")
for t in ALL:
    f = SCHEMA / f"{t}_comment.sql"
    if not f.exists():
        sys.exit(f"missing {f}")
    con.execute(f.read_text(encoding="utf-8"))
print(f"  {len(ALL)} tables commented")
con.close()
print(f"\n{NEW.name}: {total:,} rows across {len(ALL)} tables")
print("DONE_MIGRATE")
