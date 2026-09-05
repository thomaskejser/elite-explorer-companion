import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (INPUT, connect, count_then_update, prepare_table,
                       report_merge, table_count)

SRC = INPUT / "system_catalog_alias.parquet"
TABLE = "system_catalog_alias"

if not SRC.exists():
    sys.exit("{} is missing -- seed it first:\n"
             "  python etl/system_catalog_alias/build.py".format(SRC))

con = connect()
print("database: {}".format(con.execute("SELECT current_database()").fetchone()[0]))
before = prepare_table(con, TABLE, SRC.name)

con.execute("""CREATE OR REPLACE TEMP TABLE src AS
               SELECT system_a, system_b, source FROM '{}'""".format(SRC.as_posix()))
n_src = table_count(con, 'src')
print("  source: {:,} identities from {}".format(n_src, SRC.name))

bad = con.execute("SELECT count(*) FROM src WHERE system_a >= system_b").fetchone()[0]
if bad:
    sys.exit("  {:,} row(s) are not canonically ordered (system_a < system_b).\n"
             "  Swap the columns on those rows -- an unordered pair would be stored "
             "twice.".format(bad))

con.execute("""INSERT INTO system_catalog_alias (system_a, system_b, source)
               SELECT s.system_a, s.system_b, s.source FROM src s
               WHERE NOT EXISTS (SELECT 1 FROM system_catalog_alias t
                                 WHERE t.system_a = s.system_a
                                   AND t.system_b = s.system_b)""")
after_insert = table_count(con, TABLE)
inserted = after_insert - before

updated = count_then_update(
    con,
    """SELECT count(*) FROM system_catalog_alias t
       JOIN src s ON s.system_a = t.system_a AND s.system_b = t.system_b
       WHERE t.source IS DISTINCT FROM s.source""",
    """UPDATE system_catalog_alias AS t SET source = s.source
       FROM src AS s WHERE s.system_a = t.system_a AND s.system_b = t.system_b
         AND t.source IS DISTINCT FROM s.source""")

# DELETES, one of the two documented exceptions to merge-never-drop (ETL.md 3). An edge
# the parquet no longer asserts is not a retired key but a wrong identity, and it does
# damage while it sits here: etl/system_catalog/load.py copies a system_id across it and
# merges two different stars.
orphans = con.execute("""SELECT source, count(*) FROM system_catalog_alias t
                         WHERE NOT EXISTS (SELECT 1 FROM src s
                                           WHERE s.system_a = t.system_a
                                             AND s.system_b = t.system_b)
                         GROUP BY 1 ORDER BY 2 DESC""").fetchall()
con.execute("""DELETE FROM system_catalog_alias t
               WHERE NOT EXISTS (SELECT 1 FROM src s WHERE s.system_a = t.system_a
                                                       AND s.system_b = t.system_b)""")
after = table_count(con, TABLE)
# Empty orphan list: report_merge says "LEFT IN PLACE, keys RETIRED", the opposite of
# what just happened, so the deletions are reported below instead.
report_merge(TABLE, before, after, inserted, updated, [])
if orphans:
    print("  DELETED {:,} identity(ies) the parquet no longer asserts:"
          .format(sum(n for _, n in orphans)))
    for s, n in orphans:
        print("    {:<18}{:>10,}".format(s, n))
    print("  *** re-run etl/system_catalog/load.py -- it recomputes every "
          "alias-resolved system_id, and will drop the ones these edges justified.")

print("\n  identities by source:")
for src_label, n in con.execute("""SELECT source, count(*) FROM system_catalog_alias
                                   GROUP BY 1 ORDER BY 2 DESC""").fetchall():
    print("    {:<18}{:>10,}".format(src_label, n))

reach = con.execute("""WITH n AS (SELECT system_a AS s FROM system_catalog_alias
                                 UNION SELECT system_b FROM system_catalog_alias)
                       SELECT count(*) FROM n""").fetchone()[0]
tot = table_count(con, 'system_catalog')
print("\n  {:,} of {:,} catalogue names ({:.1%}) sit on at least one identity"
      .format(reach, tot, reach / tot if tot else 0))
print("  next:  python etl/system_catalog/load.py    # walks these into system_id")

con.close()
print("\nDONE_LOAD_SYSTEM_CATALOG_ALIAS")
