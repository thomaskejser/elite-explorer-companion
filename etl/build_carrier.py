"""BUILD carrier from the staged EDAstro roster. Merge; never drop.

    python scripts/ingest_sources.py --full --only edastro_fleet_carrier
    python etl/build_carrier.py

SOURCE: staging.edastro_fleet_carrier (the role view over whatever download last filled
it), 88,663 carriers, EDDN-derived, refreshed about every two days.

WHY THIS SOURCE. Fleet carriers also appear in Spansh's galaxy_stations.json.gz
(4.3 GB) and EDSM's stations.json.gz (2.7 GB), both of which carry every station in the
galaxy to deliver the same handful of fields. EDAstro publishes the carriers alone, with
LastMoved, in 20 MB.

WHAT THE TABLE IS FOR: finding carriers that have stayed put long enough to be treated
as permanent stations. The Deep Space Support Array is the famous example, but it is 86
carriers -- this finds the other few thousand.

*** AND THE TRAP: "has not moved in two years" is not "is definitely still there". ***
Both facts come from EDDN, which only knows what commanders report. A carrier nobody has
visited since 2021 has an old last_moved because nobody has watched it, not because it
stayed. `last_seen` is carried through precisely so the two can be told apart, and the
run prints the cross-tabulation every time rather than leaving it to be rediscovered.

All the work is SQL; Python only drives it.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (apply_comment_file, comment_file, connect,
                       count_then_update, report_merge, staged)

TABLE = "carrier"

con = connect()
con.execute(comment_file(TABLE).read_text(encoding="utf-8"))
SRC = staged(con, "edastro_fleet_carrier")
before = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
print(f"{TABLE}: {before:,} row(s) before; source {SRC}")

# Location resolves through the game's own id64 (EDAstro calls it SystemAddress), not
# through the name. A name join would have to compose "<sector> <system>" over 197M
# rows, and it rescues nothing anyway -- measured: of the 322 carriers id64 cannot
# place, exactly 0 are findable by name.
#
# min(system_id) because 96 id64 values sit on two system_known rows each (the same
# system recorded under two name spellings). Picking the lowest is arbitrary but
# STABLE, so a rebuild cannot silently move a carrier between duplicate rows.
# *** THE SOURCE REPEATS 153 CALLSIGNS, AND 64 OF THEM DISAGREE ABOUT WHERE THE
# CARRIER IS. *** Not a parse error: EDAstro emits more than one row for the same
# carrier, sometimes naming two different systems with identical timestamps
# (B0V-09G is listed in both "Cephei Sector DQ-Y b1" and "HIP 75593", same LastMoved,
# same LastUpdated). LastMoved never conflicts, so the disagreement is purely about
# position -- two commanders reporting from different places, or a stale row that was
# never superseded.
#
# One row must win, and the choice must be STABLE or a rebuild would silently teleport
# 64 carriers. Newest report first, then the lowest SystemAddress purely as a
# tiebreaker. The remaining ambiguity is real and cannot be resolved from this file;
# it is 0.07% of the table and the run reports it.
con.execute(f"""
CREATE OR REPLACE TEMP TABLE src AS
WITH one_per_id64 AS (
  SELECT id64, min(system_id) AS system_id FROM system_known
  WHERE id64 IS NOT NULL GROUP BY id64
),
deduped AS (
  SELECT *, row_number() OVER (PARTITION BY Callsign
                               ORDER BY LastUpdated DESC NULLS LAST,
                                        LastMoved DESC NULLS LAST,
                                        SystemAddress) AS rn
  FROM {SRC} WHERE Callsign IS NOT NULL
)
SELECT f.Callsign                                        AS callsign,
       nullif(trim(coalesce(f.Name, '')), '')            AS carrier_name,
       try_cast(f.LastMoved   AS TIMESTAMP)              AS last_moved,
       try_cast(f.LastUpdated AS TIMESTAMP)              AS last_seen,
       lower(coalesce(f.Services, '')) LIKE '%exploration%'
                                                         AS has_universal_cartographics,
       -- Recomputed from now() on EVERY build, because it is a statement about the
       -- present: parked long ago AND confirmed recently. Storing it rather than
       -- deriving it at query time keeps the definition in one place instead of
       -- copied into every consumer, which is how two of them drift apart.
       (try_cast(f.LastMoved AS TIMESTAMP) < now() - INTERVAL 365 DAY
        AND try_cast(f.LastUpdated AS TIMESTAMP) > now() - INTERVAL 90 DAY)
                                                         AS is_reliable,
       k.system_id                                       AS system_id
FROM deduped f
LEFT JOIN one_per_id64 k ON k.id64 = f.SystemAddress
WHERE f.rn = 1""")

dupes, conflicts = con.execute(f"""
    SELECT count(*), count(*) FILTER (WHERE n_addr > 1) FROM (
      SELECT Callsign, count(DISTINCT SystemAddress) AS n_addr
      FROM {SRC} GROUP BY 1 HAVING count(*) > 1)""").fetchone()
if dupes:
    print(f"  source repeats {dupes} callsign(s); {conflicts} of them name DIFFERENT "
          f"systems -- newest report kept, ties broken on SystemAddress")

n_src, n_placed = con.execute(
    "SELECT count(*), count(system_id) FROM src").fetchone()
print(f"  staged {n_src:,} carrier(s); {n_placed:,} placed in system_known "
      f"({n_placed / n_src:.1%})")

# UPDATE before INSERT, or the rows just inserted get scanned again. IS DISTINCT FROM
# so a value becoming NULL still counts as a change -- a carrier CAN move somewhere
# system_known has never heard of, and pretending we still know where it is would be
# worse than admitting we do not.
CHANGED = """t.carrier_name IS DISTINCT FROM s.carrier_name
          OR t.last_moved   IS DISTINCT FROM s.last_moved
          OR t.last_seen    IS DISTINCT FROM s.last_seen
          OR t.has_universal_cartographics
               IS DISTINCT FROM s.has_universal_cartographics
          OR t.is_reliable  IS DISTINCT FROM s.is_reliable
          OR t.system_id    IS DISTINCT FROM s.system_id"""
updated = count_then_update(
    con,
    f"SELECT count(*) FROM {TABLE} t JOIN src s USING (callsign) WHERE {CHANGED}",
    f"""UPDATE {TABLE} AS t
        SET carrier_name = s.carrier_name, last_moved = s.last_moved,
            last_seen = s.last_seen,
            has_universal_cartographics = s.has_universal_cartographics,
            is_reliable = s.is_reliable, system_id = s.system_id
        FROM src AS s WHERE s.callsign = t.callsign AND ({CHANGED})""")

con.execute(f"""
    INSERT INTO {TABLE} (callsign, carrier_name, last_moved, last_seen,
                         has_universal_cartographics, is_reliable, system_id)
    SELECT s.callsign, s.carrier_name, s.last_moved, s.last_seen,
           s.has_universal_cartographics, s.is_reliable, s.system_id
    FROM src s
    WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE t.callsign = s.callsign)""")

after = con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
# Carriers the roster no longer lists. NEVER deleted: a carrier absent from one refresh
# is usually one nobody reported that week, not one that stopped existing.
orphans = [r[0] for r in con.execute(f"""
    SELECT callsign FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM src s WHERE s.callsign = t.callsign)
    LIMIT 5""").fetchall()]
report_merge(TABLE, before, after, after - before, updated, orphans)

apply_comment_file(con, comment_file(TABLE))

# ---- the finding this table exists to surface -------------------------------------
# Print it every run. "Parked" and "confirmed still there" are different claims, and
# the gap between them is the single most misleading thing about this data.
print(f"\n  PARKED (last_moved) vs CONFIRMED (last_seen) -- read them together:\n")
print(f"  {'last seen':<20}{'total':>10}{'parked 1y+':>13}{'parked 2y+':>13}")
for r in con.execute(f"""
    SELECT CASE WHEN last_seen > now() - INTERVAL 90 DAY  THEN 'a: within 90 days'
                WHEN last_seen > now() - INTERVAL 365 DAY THEN 'b: within a year'
                ELSE 'c: over a year ago' END AS bucket,
           count(*),
           count(*) FILTER (WHERE last_moved < now() - INTERVAL 365 DAY),
           count(*) FILTER (WHERE last_moved < now() - INTERVAL 730 DAY)
    FROM {TABLE} GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0][3:]:<20}{r[1]:>10,}{r[2]:>13,}{r[3]:>13,}")

# WHERE the reliable carriers are. One flat "defensible pool" was misleading twice
# over: 84% of it sits in the bubble, where a parked carrier is of no use to an
# explorer, and a naive "> 5000 ly from Sol" test counts COLONIA -- a second population
# hub 22,000 ly out with 2,588 carriers of its own -- as deep space. Split all three,
# or the interesting number stays buried under the boring one.
COLONIA = "sqrt(pow(k.x + 9530.5, 2) + pow(k.y + 910.28, 2) + pow(k.z - 19808.13, 2))"
SOL = "sqrt(pow(k.x, 2) + pow(k.y, 2) + pow(k.z, 2))"
RELIABLE = "c.is_reliable"
print(f"\n  WHERE THE RELIABLE ONES ARE (parked 1y+ AND seen in the last 90d):\n")
print(f"  {'region':<26}{'carriers':>10}{'reliable':>10}{'with UC':>9}")
for r in con.execute(f"""
    SELECT CASE WHEN {SOL} <= 1000     THEN 'a: bubble (<1k ly)'
                WHEN {COLONIA} <= 500  THEN 'b: Colonia (2nd hub)'
                WHEN {SOL} <= 5000     THEN 'c: 1k-5k ly'
                ELSE 'd: DEEP SPACE' END AS region,
           count(*),
           count(*) FILTER (WHERE {RELIABLE}),
           count(*) FILTER (WHERE {RELIABLE} AND c.has_universal_cartographics)
    FROM {TABLE} c JOIN system_known k ON k.system_id = c.system_id
    GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0][3:]:<26}{r[1]:>10,}{r[2]:>10,}{r[3]:>9,}")

# Named networks, counted ONLY in genuine deep space -- the one place a network is
# doing something an explorer cares about. Membership is inferred from the name; no
# roster file exists for any of them.
print(f"\n  DEEP-SPACE NETWORKS (name-inferred, Colonia excluded):")
for r in con.execute(f"""
    SELECT CASE WHEN upper(coalesce(c.carrier_name, '')) LIKE 'DSSA%'   THEN 'DSSA'
                WHEN upper(coalesce(c.carrier_name, '')) LIKE '[IGAU]%' THEN '[IGAU]'
                WHEN upper(coalesce(c.carrier_name, '')) LIKE '[STAR]%' THEN '[STAR]'
                ELSE 'unaffiliated' END AS network,
           count(*) FILTER (WHERE {RELIABLE}) AS reliable, count(*) AS total
    FROM {TABLE} c JOIN system_known k ON k.system_id = c.system_id
    WHERE {SOL} > 5000 AND {COLONIA} > 500
    GROUP BY 1 ORDER BY reliable DESC""").fetchall():
    print(f"    {r[0]:<16}{r[1]:>5} reliable of {r[2]:>5}")

print("\nDONE_BUILD_CARRIER")
