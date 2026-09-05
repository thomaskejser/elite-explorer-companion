import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (INPUT, connect, count_then_update, prepare_table,
                       report_merge, table_count)

SRC = INPUT / "system_catalog.parquet"
TABLE = "system_catalog"

if not SRC.exists():
    sys.exit("{} is missing -- seed it first:\n  python etl/system_catalog/build.py"
             .format(SRC))

con = connect()
print("database: {}".format(con.execute("SELECT current_database()").fetchone()[0]))
before = prepare_table(con, TABLE, SRC.name)

con.execute("""CREATE OR REPLACE TEMP TABLE src AS
               SELECT system, type, designation FROM '{}'""".format(SRC.as_posix()))
n_src = table_count(con, 'src')
print("  source: {:,} rows from {}".format(n_src, SRC.name))

con.execute("""INSERT INTO system_catalog (system, type, designation, system_id)
               SELECT s.system, s.type, s.designation, NULL FROM src s
               WHERE NOT EXISTS (SELECT 1 FROM system_catalog t
                                 WHERE t.system = s.system)""")
after_insert = table_count(con, TABLE)
inserted = after_insert - before

updated = count_then_update(
    con,
    """SELECT count(*) FROM system_catalog t JOIN src s ON s.system = t.system
       WHERE t.type <> s.type OR t.designation <> s.designation""",
    """UPDATE system_catalog AS t SET type = s.type, designation = s.designation
       FROM src AS s WHERE s.system = t.system
         AND (t.type <> s.type OR t.designation <> s.designation)""")

orphans = con.execute("""SELECT type, count(*) FROM system_catalog t
                         WHERE NOT EXISTS (SELECT 1 FROM src s WHERE s.system = t.system)
                         GROUP BY 1 ORDER BY 2 DESC""").fetchall()
after = table_count(con, TABLE)
report_merge(TABLE, before, after, inserted, updated,
             ["{}: {:,} row(s)".format(t, n) for t, n in orphans])

cleared = count_then_update(
    con,
    """SELECT count(*) FROM system_catalog c WHERE c.system_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM system_known k WHERE k.sector_id = 0
                         AND k.system_in_sector = c.system)""",
    # Every alias-resolved system_id is reset and re-derived on each load, so
    # correcting the alias parquet is enough to correct the model (ETL.md 3).
    """UPDATE system_catalog AS c SET system_id = NULL
       WHERE c.system_id IS NOT NULL
         AND NOT EXISTS (SELECT 1 FROM system_known k WHERE k.sector_id = 0
                           AND k.system_in_sector = c.system)""")
print("  cleared {:,} previously alias-resolved system_id(s) for recomputation"
      .format(cleared))

resolved = count_then_update(
    con,
    """SELECT count(*) FROM system_catalog t
       WHERE t.system_id IS NULL AND EXISTS (
         SELECT 1 FROM system_known k
         WHERE k.sector_id = 0 AND k.system_in_sector = t.system)""",
    """UPDATE system_catalog AS t SET system_id = k.system_id
       FROM system_known AS k
       WHERE k.sector_id = 0 AND k.system_in_sector = t.system
         AND t.system_id IS NULL""")
known = con.execute(
    "SELECT count(system_id) FROM system_catalog").fetchone()[0]
print("  by name:  {:,} resolved this run, {:,}/{:,} carry the game's own spelling "
      "({:.1%})".format(resolved, known, after, known / after if after else 0))

NEIGHBOURS = """SELECT system_a AS name, system_b AS other FROM system_catalog_alias
                UNION ALL
                SELECT system_b AS name, system_a AS other FROM system_catalog_alias"""
RESOLVED = """SELECT system AS name, system_id FROM system_catalog
              WHERE system_id IS NOT NULL
              UNION ALL
              SELECT system_in_sector AS name, system_id FROM system_known
              WHERE sector_id = 0"""
AGREED = """SELECT n.name, min(r.system_id) AS system_id
            FROM ({nb}) n
            JOIN ({rs}) r ON r.name = n.other
            GROUP BY 1 HAVING count(DISTINCT r.system_id) = 1""".format(
    nb=NEIGHBOURS, rs=RESOLVED)

has_alias = con.execute("""SELECT count(*) FROM duckdb_tables()
                           WHERE table_name = 'system_catalog_alias'""").fetchone()[0]
if not has_alias:
    print("\n  system_catalog_alias does not exist -- skipping identity resolution."
          "\n  Seed and load it to resolve stars the game ships under another name:"
          "\n    python etl/system_catalog_alias/build.py"
          "\n    python etl/system_catalog_alias/load.py")
else:
    aliased, rounds = 0, 0
    while True:
        rounds += 1
        moved = count_then_update(
            con,
            """SELECT count(*) FROM system_catalog t JOIN ({a}) x ON x.name = t.system
               WHERE t.system_id IS NULL""".format(a=AGREED),
            """UPDATE system_catalog AS t SET system_id = x.system_id
               FROM ({a}) AS x WHERE x.name = t.system
                 AND t.system_id IS NULL""".format(a=AGREED))
        aliased += moved
        print("    pass {}: {:,} resolved via an alias".format(rounds, moved))
        if moved == 0 or rounds >= 12:
            break
    ambiguous = con.execute(
        """SELECT count(*) FROM (
             SELECT n.name FROM ({nb}) n
             JOIN ({rs}) r ON r.name = n.other
             JOIN system_catalog u ON u.system = n.name AND u.system_id IS NULL
             GROUP BY 1 HAVING count(DISTINCT r.system_id) > 1)""".format(
            nb=NEIGHBOURS, rs=RESOLVED)).fetchone()[0]
    known = con.execute("SELECT count(system_id) FROM system_catalog").fetchone()[0]
    print("  by identity: {:,} resolved in {} pass(es); {:,} name(s) left NULL because "
          "their neighbours disagree".format(aliased, rounds, ambiguous))
    print("  total: {:,}/{:,} present in the game ({:.1%})"
          .format(known, after, known / after if after else 0))

if not con.execute("""SELECT count(*) FROM duckdb_tables()
                      WHERE schema_name='staging'
                        AND table_name='catalog_parallax'""").fetchone()[0]:
    print("  staging.catalog_parallax is absent -- missing_coordinate left as it is.")
else:
    con.execute("""CREATE OR REPLACE TEMP TABLE placed AS
        SELECT DISTINCT system AS name FROM staging.catalog_parallax WHERE usable""")
    hops = 0
    while True:
        hops += 1
        added = con.execute("""INSERT INTO placed
            SELECT DISTINCT n.other FROM ({nb}) n JOIN placed p ON p.name = n.name
            WHERE NOT EXISTS (SELECT 1 FROM placed q WHERE q.name = n.other)"""
            .format(nb=NEIGHBOURS)).fetchone()
        n_added = table_count(con, 'placed')
        if hops == 1:
            prev = 0
        if n_added == prev or hops >= 8:
            break
        prev = n_added
    n_placed = table_count(con, 'placed')
    updated_mc = count_then_update(
        con,
        """SELECT count(*) FROM system_catalog c
           WHERE c.missing_coordinate IS DISTINCT FROM
                 NOT EXISTS (SELECT 1 FROM placed p WHERE p.name = c.system)""",
        """UPDATE system_catalog AS c
           SET missing_coordinate =
               NOT EXISTS (SELECT 1 FROM placed p WHERE p.name = c.system)
           WHERE c.missing_coordinate IS DISTINCT FROM
                 NOT EXISTS (SELECT 1 FROM placed p WHERE p.name = c.system)""")
    mc = con.execute("""SELECT count(*) FILTER (WHERE missing_coordinate),
                               count(*) FILTER (WHERE NOT missing_coordinate)
                        FROM system_catalog""").fetchone()
    print("  missing_coordinate: {:,} placeable name(s) after {} hop(s); "
          "{:,} row(s) updated".format(n_placed, hops, updated_mc))
    print("    {:,} rows CANNOT be placed, {:,} can".format(mc[0], mc[1]))

print("\n  COVERAGE -- how much of each real catalogue Frontier shipped:")
print("    {:<6}{:>12}{:>11}{:>9}{:>11}{:>9}"
      .format("type", "catalogue", "own name", "rate", "in game", "rate"))
con.execute("""CREATE OR REPLACE TEMP TABLE cov AS
    SELECT c.type, count(*) AS n, count(c.system_id) AS got,
           count(*) FILTER (WHERE c.system_id IS NOT NULL AND EXISTS (
             SELECT 1 FROM system_known k WHERE k.sector_id = 0
               AND k.system_in_sector = c.system)) AS own
    FROM system_catalog c GROUP BY 1""")
for typ, n, got, own in con.execute(
        "SELECT type, n, got, own FROM cov ORDER BY got DESC, n DESC").fetchall():
    print("    {:<6}{:>12,}{:>11,}{:>8.1%}{:>11,}{:>8.1%}"
          .format(typ, n, own, own / n, got, got / n))
tot_n, tot_g, tot_o = con.execute(
    "SELECT sum(n), sum(got), sum(own) FROM cov").fetchone()
print("    {:<6}{:>12,}{:>11,}{:>8.1%}{:>11,}{:>8.1%}"
      .format("ALL", tot_n, tot_o, tot_o / tot_n, tot_g, tot_g / tot_n))
print("\n  A row still NULL is a real star Frontier did not ship, with the alias graph"
      "\n  exhausted -- including the edges that end at a GAME name, so a star the game"
      "\n  ships as Sirius or Alpha Centauri resolves rather than reads as absent. What"
      "\n  stays unreachable is a star whose game name no catalogue cross-identifies.")

con.close()
print("\nDONE_LOAD_SYSTEM_CATALOG")
