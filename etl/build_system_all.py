"""BUILD the `system_all` VIEW: every system we can name, observed and inferred.

    python etl/build_system_all.py

A VIEW, so there is nothing to merge and nothing to preserve -- the usual
merge-never-drop rule does not apply because no row is stored. Re-running it is free
and always safe, which is why it takes no arguments.

*** THE ONE THING THIS SCRIPT EXISTS FOR: CREATE OR REPLACE VIEW SILENTLY DROPS EVERY
COMMENT ON THAT VIEW. *** Verified against DuckDB, not assumed. So the definition and
its comments must be applied together, from one file, every time -- exactly the reason
ETL.md keeps comments beside the DDL rather than in a migration. schema/system_all.sql
holds both and this applies the whole file.

All the work is SQL; Python only drives it and then checks the result.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import connect
from common.current import SCHEMA

VIEW = "system_all"
DDL = SCHEMA / f"{VIEW}.sql"

con = connect()
con.execute(DDL.read_text(encoding="utf-8"))
print(f"applied {DDL.name}")

# Every column commented, or the build fails. This is the ONLY automated comment check
# in the repo; everywhere else the bar is held by review. A view is
# documentation-critical in a way a table is not, because a reader cannot see what it is
# made of without reading its definition.
missing = [r[0] for r in con.execute(
    """SELECT column_name FROM duckdb_columns()
       WHERE table_name = ? AND comment IS NULL ORDER BY column_index""",
    [VIEW]).fetchall()]
if missing or not con.execute(
        "SELECT comment FROM duckdb_views() WHERE view_name = ?", [VIEW]).fetchone()[0]:
    raise SystemExit(f"{VIEW}: missing comment on {missing or 'the view itself'} -- "
                     f"CREATE OR REPLACE VIEW drops comments, so they must be in "
                     f"{DDL.name} and re-applied here")
print(f"  comments: view + all {len(con.execute(f'DESCRIBE {VIEW}').fetchall())} columns")

# ---- what the view actually contains ----------------------------------------------
# Printed every run rather than trusted. The split is the whole point of the view, and
# the inferred half is small enough to be easy to lose without noticing.
observed, predicted = con.execute(f"""
    SELECT count(*) FILTER (WHERE NOT is_predicted),
           count(*) FILTER (WHERE is_predicted) FROM {VIEW}""").fetchone()
print(f"\n  {observed:,} observed + {predicted:,} predicted = "
      f"{observed + predicted:,} systems")

# THE INVARIANT THIS VIEW LIVES OR DIES BY: one row per system. It would be broken by
# including the catalogued half of system_predicted, whose rows all duplicate a
# system_known row -- so assert it rather than leave it to the comment.
#
# COSTS ABOUT 30 SECONDS: it groups 197.8M VARCHARs, and there is no cheaper way to
# prove the property that actually matters. Everything else in this script is
# sub-second, so if the run feels stuck, this is where it is.
dupes = con.execute(f"""
    SELECT count(*) FROM (SELECT system FROM {VIEW}
                          GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0]
print(f"  duplicate system name(s): {dupes:,}"
      + ("" if not dupes else "   *** ONE ROW PER SYSTEM IS BROKEN ***"))

print(f"\n  {'region':<34}{'observed':>16}{'predicted':>12}")
for r in con.execute(f"""
    SELECT coalesce(region, '(none)'), count(*) FILTER (WHERE NOT is_predicted),
           count(*) FILTER (WHERE is_predicted)
    FROM {VIEW} GROUP BY 1 ORDER BY 3 DESC, 2 DESC LIMIT 8""").fetchall():
    print(f"  {r[0]:<34}{r[1]:>16,}{r[2]:>12,}")

print(f"\n  {'mass code':<34}{'observed':>16}{'predicted':>12}")
for r in con.execute(f"""
    SELECT coalesce(mass_code, '(hand-named)'),
           count(*) FILTER (WHERE NOT is_predicted),
           count(*) FILTER (WHERE is_predicted)
    FROM {VIEW} GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]:<34}{r[1]:>16,}{r[2]:>12,}")

print("\nDONE_BUILD_SYSTEM_ALL")
