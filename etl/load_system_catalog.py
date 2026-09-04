"""MERGE input/system_catalog.parquet into the `system_catalog` table.

The only thing allowed to write that table, per ETL.md rule 2. Merge semantics
throughout: insert unseen names, update changed attributes, leave rows the source no
longer produces IN PLACE and report them. No CREATE OR REPLACE, no DROP, no truncate.

The natural key is `system` -- the name itself -- and it is also the PRIMARY KEY, so
there is no surrogate to allocate and none to accidentally renumber. That is the whole
reason the table has no id column: ETL.md's "match on the natural key, never the
surrogate" is trivially satisfied when the only key IS the natural one.

AFTER MERGING IT RESOLVES system_id, which is the point of the table. A catalogue name
belongs to a hand-named system or to nothing, so the lookup is restricted to
system_known rows with sector_id = 0 -- both correct (a real-catalogue name never has a
procedural sector) and cheap (149,749 candidate rows instead of a 197.6M-row scan).
Remember the sentinel rule from ETL.md: for sector_id = 0 the full system name IS
system_in_sector, with NO sector prefix. Concatenating "crafted" onto it is the bug that
has been made twice in this project.

NULLs are re-resolved on every run and non-NULLs are never revisited. A NULL goes stale
in one direction only -- somebody reports the system to a dump and the next model
rebuild makes it resolvable -- while a name that resolved once does not become a
different system.

*** RESOLUTION HAS TWO PHASES, AND THE ORDER IS THE POINT. ***

  1. BY NAME. The catalogue's own spelling, against system_known. If Frontier shipped the
     star as "HIP 1000", the HIP 1000 row resolves here.
  2. BY IDENTITY, walking system_catalog_alias. Frontier ships each real star under ONE
     designation and it is often not the one you looked up -- the game names a Hipparcos
     star HIP inside ~1000 ly and HD beyond it -- so "HIP 1000 is not in the game" was
     usually false: the star is there, as HD 812. This phase copies that system_id onto
     every other name for the same star, iterating to a fixpoint so a chain
     (TYC -> HIP -> HD -> BD) resolves end to end.

Phase 1 runs first and phase 2 only fills NULLs, so a name the game actually uses always
wins over an identity inferred from a cross-ID.

*** PHASE 1 IS STICKY, PHASE 2 IS RECOMPUTED FROM SCRATCH ON EVERY RUN. *** A name match
is an observation and does not go stale; an identity is DERIVED from system_catalog_alias,
so if an edge is corrected or retracted the system_id it justified has to go with it.
Every alias-resolved row is therefore reset to NULL before phase 2 runs, and re-derived.
Leaving them in place would make a bad cross-ID permanent -- one bad CNS3 field is
enough to merge a hundred unrelated names onto one system, and a "never revisit a
non-NULL" rule would keep that merge after the fix. Where a name's resolved neighbours
disagree about WHICH system they mean, nothing is written and the count is reported: two
catalogues contradicting each other about a component of a multiple star is a fact to
look at, not a coin to toss.

*** WHAT A NULL MEANS AFTERWARDS. *** "Not in the game, with the alias graph exhausted".
It does NOT mean "Frontier did not use THIS catalogue's spelling" -- that is a separate,
weaker fact, and it is a join rather than a NULL. The coverage report at the end of this
script prints both:

    SELECT count(*) FROM system_catalog c JOIN system_known k USING (system_id)
    WHERE k.system_in_sector = c.system      -- shipped under its own name

Usage:  python etl/load_system_catalog.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (INPUT, apply_comment_file, comment_file, connect,
                       count_then_update, report_merge)

SRC = INPUT / "system_catalog.parquet"
TABLE = "system_catalog"

if not SRC.exists():
    sys.exit("{} is missing -- seed it first:\n  python etl/build_system_catalog.py"
             .format(SRC))

con = connect()
# Re-asserting the schema file is free (CREATE TABLE IF NOT EXISTS) and is the only
# thing that keeps the COMMENT ON text alive across a migration.
apply_comment_file(con, comment_file(TABLE))
before = con.execute("SELECT count(*) FROM {}".format(TABLE)).fetchone()[0]
print("database: {}".format(con.execute("SELECT current_database()").fetchone()[0]))

con.execute("""CREATE OR REPLACE TEMP TABLE src AS
               SELECT system, type, designation FROM '{}'""".format(SRC.as_posix()))
n_src = con.execute("SELECT count(*) FROM src").fetchone()[0]
print("  source: {:,} rows from {}".format(n_src, SRC.name))

# ---------------------------------------------------------------- insert -----------
# system_id is left NULL here rather than resolved inline: the resolve step below is
# re-run for every NULL on every load, so doing it twice would only make this slower.
con.execute("""INSERT INTO system_catalog (system, type, designation, system_id)
               SELECT s.system, s.type, s.designation, NULL FROM src s
               WHERE NOT EXISTS (SELECT 1 FROM system_catalog t
                                 WHERE t.system = s.system)""")
after_insert = con.execute("SELECT count(*) FROM {}".format(TABLE)).fetchone()[0]
inserted = after_insert - before

# ---------------------------------------------------------------- update -----------
# Counted with a SELECT carrying the same predicate rather than UPDATE ... RETURNING:
# DuckDB refuses RETURNING on a table referenced by a foreign key, and this one
# references system_known. See common.db.count_then_update.
updated = count_then_update(
    con,
    """SELECT count(*) FROM system_catalog t JOIN src s ON s.system = t.system
       WHERE t.type <> s.type OR t.designation <> s.designation""",
    """UPDATE system_catalog AS t SET type = s.type, designation = s.designation
       FROM src AS s WHERE s.system = t.system
         AND (t.type <> s.type OR t.designation <> s.designation)""")

# ---------------------------------------------------------------- orphans ----------
# Present in the table but no longer produced by the source. LEFT IN PLACE per ETL.md:
# a catalogue entry that vanishes from a re-seed is far more likely to be a narrowed
# download than a star that stopped existing.
orphans = con.execute("""SELECT type, count(*) FROM system_catalog t
                         WHERE NOT EXISTS (SELECT 1 FROM src s WHERE s.system = t.system)
                         GROUP BY 1 ORDER BY 2 DESC""").fetchall()
after = con.execute("SELECT count(*) FROM {}".format(TABLE)).fetchone()[0]
report_merge(TABLE, before, after, inserted, updated,
             ["{}: {:,} row(s)".format(t, n) for t, n in orphans])

# ------------------------------------------------------- reset derived resolution --
# *** RUNS BEFORE PHASE 1, SO EVERY COUNT BELOW MEANS WHAT IT SAYS. *** With the
# reset after the name phase, its "present in the game" line reported the PREVIOUS
# run's alias resolutions as though they were the game's own spelling.
#
# Note what it does NOT touch: a row whose own name IS the game's name
# for its system. That is phase 1's work and an observation, not a derivation. Everything
# else with a system_id got it from an edge, so it is rebuilt below from today's edges.
cleared = count_then_update(
    con,
    """SELECT count(*) FROM system_catalog c WHERE c.system_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM system_known k WHERE k.sector_id = 0
                         AND k.system_in_sector = c.system)""",
    """UPDATE system_catalog AS c SET system_id = NULL
       WHERE c.system_id IS NOT NULL
         AND NOT EXISTS (SELECT 1 FROM system_known k WHERE k.sector_id = 0
                           AND k.system_in_sector = c.system)""")
print("  cleared {:,} previously alias-resolved system_id(s) for recomputation"
      .format(cleared))

# ---------------------------------------------------------------- resolve ----------
# *** sector_id = 0 IS THE 'crafted' SENTINEL AND ITS NAME STANDS ALONE. *** For those
# rows system_in_sector IS the full pasteable name; do NOT prefix the sector. Restricting
# to the sentinel is also what makes this cheap -- every real-catalogue name is
# hand-named, so nothing outside it can ever match.
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

# ------------------------------------------------------------- resolve by identity ---
# *** THE SAME STAR UNDER ANOTHER CATALOGUE'S NAME. *** Walk system_catalog_alias from a
# name that did not resolve to one that did, and copy its system_id. Both directions of
# every edge, because the table stores each identity once, in canonical order.
#
# ITERATED TO A FIXPOINT rather than done once: identities chain (TYC -> HIP -> HD -> BD)
# and a single pass moves a system_id one hop only. The loop terminates because every pass
# either fills at least one NULL or stops, and a resolved row is never revisited -- so it
# cannot oscillate. The cap is a backstop, not the mechanism.
#
# *** ONLY WHERE THE NEIGHBOURS AGREE. *** count(DISTINCT system_id) = 1 is not caution
# for its own sake: the Durchmusterungs and CNS3 disagree about which component of a
# multiple star carries a designation, and a disagreement settled by min() would
# silently assert one of them. Those rows stay NULL and are counted.
NEIGHBOURS = """SELECT system_a AS name, system_b AS other FROM system_catalog_alias
                UNION ALL
                SELECT system_b AS name, system_a AS other FROM system_catalog_alias"""
# *** A NEIGHBOUR MAY BE A GAME NAME RATHER THAN A CATALOGUE NAME. *** Some edges end at
# what FRONTIER calls the system -- "Sirius", "Alpha Centauri", "Wolf 359" -- which is not
# a catalogue designation and so has no system_catalog row to carry a system_id. Those are
# the only edges that can reach a bright star, so the resolved universe is both: catalogue
# rows that resolved, UNION the hand-named systems themselves.
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
          "\n    python etl/build_system_catalog_alias.py"
          "\n    python etl/load_system_catalog_alias.py")
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
    # Reported, never guessed at. A handful is expected -- multiple stars whose components
    # the catalogues split differently -- but a large number means a rendering bug in
    # build_system_catalog_alias.py has put two different stars on one edge.
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

# --------------------------------------------------- missing_coordinate -----------
# *** THE ONE PROPERTY THAT EXPLAINS AN ABSENCE. *** Measured over Hipparcos: a star with
# no parallax is absent from the game 98.1% of the time, one with a negative parallax
# 66.2%, against 1.3% of shipped stars having no usable parallax at all. Stellar Forge
# needs somewhere to put a star, and where the astronomy could not say, Frontier did not
# guess. So the column is worth carrying on every row, not just the ones we asked about.
#
# PROPAGATED ACROSS THE ALIAS GRAPH, because only three of the thirteen catalogues here
# publish a parallax. A Tycho-2 entry has none of its own; if it is the same star as a
# Hipparcos entry that does, the star has a distance and this column must say so. Same
# fixpoint walk as the system_id resolution above, and for the same reason -- an identity
# chain is two or three hops deep (TYC -> HIP, CD -> HD -> HIP).
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
        n_added = con.execute("SELECT count(*) FROM placed").fetchone()[0]
        if hops == 1:
            prev = 0
        if n_added == prev or hops >= 8:
            break
        prev = n_added
    n_placed = con.execute("SELECT count(*) FROM placed").fetchone()[0]
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

# ---------------------------------------------------------------- the answer -------
# The reason the table exists, printed on every load so a merge that quietly changed a
# coverage rate cannot go unnoticed.
# TWO RATES, AND CONFLATING THEM IS THE MISTAKE THIS SPLIT EXISTS TO PREVENT.
#   own name  -- Frontier shipped the star under THIS catalogue's spelling. The one to
#                quote about a CATALOGUE's naming.
#   in game   -- the star is in the game under ANY name. The one to quote about the SKY.
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
