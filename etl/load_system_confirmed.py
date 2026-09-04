"""LOAD system_confirmed from the app's JSON store. Merge; never drop.

SOURCE: input/unmigrated/confirmed.json --
name -> {cls, kind, mc, exact, pred, visited, found, x,y,z}.

The `visited` flag is the ONLY field that changes after a row is written: a find is
recorded when a route plot reveals its class, and flipped to visited if and when the
commander finally gets there. So the merge updates that and nothing else -- rewriting
coordinates or a class from a store that has since lost precision would be a downgrade,
not an update.

*** WRITES ONLY TO elite_mapping_v2_current.duckdb. *** See common/current.py.

    python etl/load_system_confirmed.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.current import STORES, begin, finish

TABLE = "system_confirmed"
STORE = STORES / "confirmed.json"

con, before = begin(TABLE)

# DuckDB parses the store directly: a name-keyed JSON object casts to
# MAP(VARCHAR, JSON), so unnesting gives one row per find. Fields are pulled out
# INDIVIDUALLY rather than by casting the value to a STRUCT, because a STRUCT cast
# demands every key be present and the store is not uniform -- the earliest finds
# predate the `exact` and `pred` flags and simply lack them. json_extract yields NULL
# for a missing key, which is the honest answer; the STRUCT cast raises instead.
con.execute(f"""
CREATE OR REPLACE TEMP TABLE src AS
WITH kv AS (
  SELECT unnest(map_keys(m)) AS system, unnest(map_values(m)) AS v
  FROM (SELECT (content::JSON)::MAP(VARCHAR, JSON) AS m
        FROM read_text('{STORE.as_posix()}'))
)
SELECT system,
       v ->> 'kind'                        AS kind,
       v ->> 'cls'                         AS star_class,
       v ->> 'mc'                          AS mass_code,
       try_cast(v ->> 'x' AS DOUBLE)       AS x,
       try_cast(v ->> 'y' AS DOUBLE)       AS y,
       try_cast(v ->> 'z' AS DOUBLE)       AS z,
       try_cast(v ->> 'exact' AS BOOLEAN)  AS was_exact,
       try_cast(v ->> 'pred' AS BOOLEAN)   AS was_predicted,
       coalesce(try_cast(v ->> 'visited' AS BOOLEAN), FALSE) AS visited,
       try_cast(v ->> 'found' AS DATE)     AS found_date
FROM kv""")

n_src, n_bh, n_wr = con.execute("""
    SELECT count(*), count(*) FILTER (WHERE kind = 'BH'),
           count(*) FILTER (WHERE kind = 'WR') FROM src""").fetchone()
print(f"  staged {n_src:,} find(s): {n_bh:,} black hole, {n_wr:,} Wolf-Rayet")

# UPDATE before INSERT, or the freshly inserted rows get scanned again. Only `visited`
# moves, and only FALSE -> TRUE: a find never becomes unvisited.
updated = con.execute(f"""
    SELECT count(*) FROM {TABLE} t JOIN src s USING (system)
    WHERE s.visited AND NOT t.visited""").fetchone()[0]
if updated:
    con.execute(f"""UPDATE {TABLE} AS t SET visited = TRUE
                    FROM src AS s
                    WHERE s.system = t.system
                      AND s.visited AND NOT t.visited""")

con.execute(f"""
    INSERT INTO {TABLE} (system, kind, star_class, mass_code, x, y, z,
                         id64, was_exact, was_predicted, visited, found_date)
    SELECT s.system, s.kind, s.star_class, s.mass_code, s.x, s.y, s.z,
           NULL, s.was_exact, s.was_predicted, s.visited, s.found_date
    FROM src s
    WHERE s.kind IS NOT NULL            -- kind is NOT NULL in the DDL; a row without
                                        -- one is not a find and must not be invented
      AND NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE t.system = s.system)""")

after = finish(con, TABLE, before, updated)

print(f"\n  {'kind':<6}{'finds':>7}{'visited':>9}{'predicted':>11}{'exact':>7}")
for r in con.execute(f"""SELECT kind, count(*), count(*) FILTER (WHERE visited),
        count(*) FILTER (WHERE was_predicted), count(*) FILTER (WHERE was_exact)
        FROM {TABLE} GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]:<6}{r[1]:>7,}{r[2]:>9,}{r[3]:>11,}{r[4]:>7,}")

# was_predicted is the column that scores the model, so surface it rather than making
# someone go looking: a find in the PREDICTED pool is evidence the boxel-gap
# enumeration works, which is a stronger claim than "scanning unscanned systems pays".
pred = con.execute(f"SELECT count(*) FILTER (WHERE was_predicted) FROM {TABLE}").fetchone()[0]
if after:
    print(f"\n  {pred:,}/{after:,} ({pred/after:.0%}) came from the PREDICTED pool -- "
          f"boxel gaps nobody had reported, not merely unscanned systems.")

print("\nDONE_LOAD_SYSTEM_CONFIRMED")
