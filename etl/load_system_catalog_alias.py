"""MERGE input/system_catalog_alias.parquet into the `system_catalog_alias` table.

The only thing allowed to write that table, per ETL.md rule 2. Merge semantics: insert
unseen identities and update a changed `source`. No CREATE OR REPLACE, no DROP, no
truncate.

The natural key is the identity itself -- (system_a, system_b) -- and it is also the
PRIMARY KEY, so there is no surrogate to allocate and none to renumber. The builder
canonicalises the pair so that system_a < system_b, which is what stops the same identity
arriving twice in opposite directions.

*** THIS LOADER DELETES ORPHANS, AND IS THE SECOND DOCUMENTED EXCEPTION TO ETL.md'S
MERGE-NEVER-DROP -- FOR THE SAME REASON AS system_predicted. *** That rule protects
surrogate keys other tables point at; nothing has a foreign key into this table, and its
key is the identity itself. More to the point, an edge the parquet no longer asserts is
not a retired key, it is a WRONG IDENTITY -- and a wrong identity here does active damage,
because load_system_catalog.py copies a system_id across it and silently merges two
different stars. That is not hypothetical: the first seed of this table chained 159
unrelated names onto `Gliese 452.3` through one bad CNS3 field, and leaving those edges in
place would have preserved the merge for as long as the table existed. Corrections to the
parquet must be able to REMOVE an assertion, so deletions are counted and reported.

*** THIS SCRIPT DOES NOT TOUCH system_catalog.system_id. *** Propagating an identity into
that column is etl/load_system_catalog.py's job, because system_catalog is its table and
one-script-per-table means exactly that. Run them in this order:

    python etl/load_system_catalog_alias.py     # the edges
    python etl/load_system_catalog.py           # resolves names, then walks the edges

Usage:  python etl/load_system_catalog_alias.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (INPUT, apply_comment_file, comment_file, connect,
                       count_then_update, report_merge)

SRC = INPUT / "system_catalog_alias.parquet"
TABLE = "system_catalog_alias"

if not SRC.exists():
    sys.exit("{} is missing -- seed it first:\n"
             "  python etl/build_system_catalog_alias.py".format(SRC))

con = connect()
# Re-asserting the schema file is free (CREATE TABLE IF NOT EXISTS) and is the only thing
# that keeps the COMMENT ON text alive across a migration. It is also what CREATES this
# table on first run: nothing has a foreign key into it, so no fresh build is needed.
apply_comment_file(con, comment_file(TABLE))
before = con.execute("SELECT count(*) FROM {}".format(TABLE)).fetchone()[0]
print("database: {}".format(con.execute("SELECT current_database()").fetchone()[0]))

con.execute("""CREATE OR REPLACE TEMP TABLE src AS
               SELECT system_a, system_b, source FROM '{}'""".format(SRC.as_posix()))
n_src = con.execute("SELECT count(*) FROM src").fetchone()[0]
print("  source: {:,} identities from {}".format(n_src, SRC.name))

# ---------------------------------------------------------------------------------
# The builder canonicalises, but a HAND-EDITED parquet might not -- the file is meant to
# be corrected by hand, so check rather than trust. A reversed pair would insert a second
# row for an identity we already hold and silently double it.
# ---------------------------------------------------------------------------------
bad = con.execute("SELECT count(*) FROM src WHERE system_a >= system_b").fetchone()[0]
if bad:
    sys.exit("  {:,} row(s) are not canonically ordered (system_a < system_b).\n"
             "  Swap the columns on those rows -- an unordered pair would be stored "
             "twice.".format(bad))

# ---------------------------------------------------------------------------------- insert
con.execute("""INSERT INTO system_catalog_alias (system_a, system_b, source)
               SELECT s.system_a, s.system_b, s.source FROM src s
               WHERE NOT EXISTS (SELECT 1 FROM system_catalog_alias t
                                 WHERE t.system_a = s.system_a
                                   AND t.system_b = s.system_b)""")
after_insert = con.execute("SELECT count(*) FROM {}".format(TABLE)).fetchone()[0]
inserted = after_insert - before

# ---------------------------------------------------------------------------------- update
# IS DISTINCT FROM, not <>: ETL.md's rule, and it matters the first time a column is
# added to this table with NULLs on the existing rows.
updated = count_then_update(
    con,
    """SELECT count(*) FROM system_catalog_alias t
       JOIN src s ON s.system_a = t.system_a AND s.system_b = t.system_b
       WHERE t.source IS DISTINCT FROM s.source""",
    """UPDATE system_catalog_alias AS t SET source = s.source
       FROM src AS s WHERE s.system_a = t.system_a AND s.system_b = t.system_b
         AND t.source IS DISTINCT FROM s.source""")

# ------------------------------------------------------------------------- delete stale
# See the module docstring: a retracted identity is a wrong row, not a retired key.
orphans = con.execute("""SELECT source, count(*) FROM system_catalog_alias t
                         WHERE NOT EXISTS (SELECT 1 FROM src s
                                           WHERE s.system_a = t.system_a
                                             AND s.system_b = t.system_b)
                         GROUP BY 1 ORDER BY 2 DESC""").fetchall()
con.execute("""DELETE FROM system_catalog_alias t
               WHERE NOT EXISTS (SELECT 1 FROM src s WHERE s.system_a = t.system_a
                                                       AND s.system_b = t.system_b)""")
after = con.execute("SELECT count(*) FROM {}".format(TABLE)).fetchone()[0]
# No orphan list passed to report_merge: its wording is "LEFT IN PLACE, keys RETIRED",
# which is right for every other table here and the opposite of what this one does.
report_merge(TABLE, before, after, inserted, updated, [])
if orphans:
    print("  DELETED {:,} identity(ies) the parquet no longer asserts:"
          .format(sum(n for _, n in orphans)))
    for s, n in orphans:
        print("    {:<18}{:>10,}".format(s, n))
    print("  *** re-run etl/load_system_catalog.py -- it recomputes every "
          "alias-resolved system_id, and will drop the ones these edges justified.")

# ---------------------------------------------------------------------------------- report
print("\n  identities by source:")
for src_label, n in con.execute("""SELECT source, count(*) FROM system_catalog_alias
                                   GROUP BY 1 ORDER BY 2 DESC""").fetchall():
    print("    {:<18}{:>10,}".format(src_label, n))

# How much of the catalogue these edges can even reach. Not the same as how much they
# RESOLVE -- that depends on which endpoint the game happens to carry, and is reported by
# load_system_catalog.py after it walks them.
reach = con.execute("""WITH n AS (SELECT system_a AS s FROM system_catalog_alias
                                 UNION SELECT system_b FROM system_catalog_alias)
                       SELECT count(*) FROM n""").fetchone()[0]
tot = con.execute("SELECT count(*) FROM system_catalog").fetchone()[0]
print("\n  {:,} of {:,} catalogue names ({:.1%}) sit on at least one identity"
      .format(reach, tot, reach / tot if tot else 0))
print("  next:  python etl/load_system_catalog.py    # walks these into system_id")

con.close()
print("\nDONE_LOAD_SYSTEM_CATALOG_ALIAS")
