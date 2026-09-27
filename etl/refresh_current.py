import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.kinds import KINDS
from common.current import (CURRENT_DB, DERIVED_TABLES, MODEL_DB, MODEL_SCHEMA,
                            MODEL_TABLES, PROBE_TABLE, attach_model, connect,
                            full_name_sql)
from common.db import comment_file, run_sql_file

SRC = "src"

# The mass-code floor below which an unrecorded system is not kept. *** THIS IS A
# DELIBERATE TRADE, NOT THE EXACT ANSWER. *** Measured over 74,697,020 recorded primary
# stars, mass code 'd' carries 2,909,302 neutrons and 361,366 white dwarfs, so a floor of
# 'e' cannot see an unrecorded one: those probe as "not in the dumps" and show as a find.
# Measured against system_confirmed that is 405 missed of 1,655 in-dump systems, all of
# them neutrons and white dwarfs; the other five kinds have no rows below 'e' and stay
# exact. Lower it to 'd' to trade roughly 300 MB back for that accuracy.
MASS_CODE_FLOOR = "e"

# The arrival classes app/kinds.py can confirm -- read from the vocabulary rather than
# restated, so the probe cannot come to disagree with what the overlay confirms.
CLASSES = sorted({c for k in KINDS for c in k.classes})

# THE NAME IS COMPOSED HERE, through common.current.full_name_sql() and never by hand.
# That function is the one definition of the rule ETL.md exists to protect -- sector_id 0
# is the `crafted` sentinel and its name stands alone, and composing it any other way is
# what manufactured multi-million-row phantom gaps twice.
#
# Composing costs nothing worth caching: 0.91 s for all 6,943,571 names, because
# system_known is indexed on system_id and sector is a 12,100-row hash build.
PROBE_SQL = """
INSERT INTO {schema}.{table} (system)
SELECT {full_name} AS sys_name
FROM {src}.main.system_known k
JOIN {src}.main.sector sc ON sc.sector_id = k.sector_id
WHERE k.primary_star_body_id IN (SELECT body_id FROM {src}.main.body
                                 WHERE code IN ({classes}))
   OR (k.primary_star_body_id IS NULL
       AND (k.mass_code IS NULL OR k.mass_code >= '{floor}'))
ORDER BY sys_name
"""


def refresh(con):
    if attach_model(con, SRC) is None:
        sys.exit(f"model database not found: {MODEL_DB}")
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {MODEL_SCHEMA}")

    print(f"database: {CURRENT_DB.name}, schema {MODEL_SCHEMA}")
    print(f"source:   {MODEL_DB.name}")
    con.execute(f"SET search_path='{MODEL_SCHEMA}'")
    # Dropping and CHECKPOINTing before any write keeps the file at one copy of the
    # data rather than two -- 738 MB against 1.47 GB. A failure below then leaves the
    # mirror empty, which is the safe way to fail: a half-replaced mirror is not.
    before = {}
    for table in MODEL_TABLES + list(DERIVED_TABLES) + [PROBE_TABLE]:
        if con.execute("""SELECT count(*) FROM duckdb_tables()
                          WHERE schema_name = ? AND table_name = ?""",
                       [MODEL_SCHEMA, table]).fetchone()[0]:
            before[table] = con.execute(
                f"SELECT count(*) FROM {MODEL_SCHEMA}.{table}").fetchone()[0]
            con.execute(f"DROP TABLE {MODEL_SCHEMA}.{table}")
    con.execute("CHECKPOINT")

    con.execute("BEGIN TRANSACTION")
    try:
        counts = []
        for table in MODEL_TABLES:
            run_sql_file(con, comment_file(table))
            cols = ", ".join(r[0] for r in con.execute(
                """SELECT column_name FROM duckdb_columns()
                   WHERE schema_name = ? AND table_name = ?
                   ORDER BY column_index""",
                [MODEL_SCHEMA, table]).fetchall())
            con.execute(f"""INSERT INTO {MODEL_SCHEMA}.{table} ({cols})
                            SELECT {cols} FROM {SRC}.main.{table}""")
            after = con.execute(
                f"SELECT count(*) FROM {MODEL_SCHEMA}.{table}").fetchone()[0]
            was = before.get(table, 0)
            counts.append((table, was, after))
            print(f"  {table:<20}{after:>12,}"
                  + ("" if was == after else f"   was {was:,}"))
        # DERIVED, NOT COPIED. A mirror table whose model-side twin is itself
        # derived has two chances to be right and one to drift: main.system_neutron was
        # a strict subset of its own definition, short by 34,743 systems, and the
        # overlay routed on it. Deriving here removes the intermediate entirely.
        for table, (cols, sql) in DERIVED_TABLES.items():
            run_sql_file(con, comment_file(table))
            con.execute(f"INSERT INTO {MODEL_SCHEMA}.{table} ({cols}) "
                        + sql.format(src=SRC))
            after = con.execute(
                f"SELECT count(*) FROM {MODEL_SCHEMA}.{table}").fetchone()[0]
            was = before.get(table, 0)
            counts.append((table, was, after))
            print(f"  {table:<20}{after:>12,}"
                  + ("" if was == after else f"   was {was:,}")
                  + "   DERIVED")

        run_sql_file(con, comment_file(PROBE_TABLE))
        # preserve_insertion_order is off on this connection for the mirror's sake, and
        # it would discard the ORDER BY that gives this table its zonemaps. The probe is
        # 21 ms sorted and seconds unsorted, so it is worth the one setting.
        con.execute("SET preserve_insertion_order=true")
        con.execute(PROBE_SQL.format(
            schema=MODEL_SCHEMA, table=PROBE_TABLE, src=SRC, floor=MASS_CODE_FLOOR,
            full_name=full_name_sql("k", "sc"),
            classes=", ".join(repr(c) for c in CLASSES)))
        con.execute("SET preserve_insertion_order=false")
        after = con.execute(
            f"SELECT count(*) FROM {MODEL_SCHEMA}.{PROBE_TABLE}").fetchone()[0]
        was = before.get(PROBE_TABLE, 0)
        counts.append((PROBE_TABLE, was, after))
        print(f"  {PROBE_TABLE:<20}{after:>12,}"
              + ("" if was == after else f"   was {was:,}")
              + f"   (mass code >= '{MASS_CODE_FLOOR}', {len(CLASSES)} classes)")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.execute("SET search_path='main'")

    total = sum(a for _, _, a in counts)
    print(f"\nmirrored {len(counts)} table(s), {total:,} rows into "
          f"{CURRENT_DB.name}:{MODEL_SCHEMA}")
    return counts


def main():
    con = connect()
    try:
        refresh(con)
        con.execute("CHECKPOINT")
    finally:
        con.close()
    print("DONE_REFRESH_CURRENT")


if __name__ == "__main__":
    main()
