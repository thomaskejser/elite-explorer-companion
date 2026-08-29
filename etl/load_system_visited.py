"""LOAD system_visited from the app's JSON store. Merge; never drop.

SOURCE: app/visited.json -- a bare JSON array of system names, no timestamps. That is
all the store ever kept, so first_visited_utc / last_visited_utc land NULL for every
migrated row and are populated only going forward. NULL here means "before the
migration", not "unknown".

DELETION IS NEVER CORRECT ON THIS TABLE. The store exists because Elite deletes old
journals: the whole point is that "been there" outlives the evidence. A name absent
from visited.json is a name whose journal aged out, not a visit that did not happen, so
the merge only ever adds.

*** WRITES ONLY TO elite_mapping_v2_current.duckdb. *** See common/current.py.

    python etl/load_system_visited.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.current import APP, begin, finish

TABLE = "system_visited"
VISITED_JSON = APP / "visited.json"

con, before = begin(TABLE)

con.execute(f"""
CREATE OR REPLACE TEMP TABLE src AS
SELECT DISTINCT unnest((content::JSON)::VARCHAR[]) AS system
FROM read_text('{VISITED_JSON.as_posix()}')""")
print(f"  staged {con.execute('SELECT count(*) FROM src').fetchone()[0]:,} name(s)")

# INSERT only -- there is nothing to update. The source carries no fact beyond
# membership, so a name already present has nothing new to say.
con.execute(f"""
    INSERT INTO {TABLE} (system, id64, first_visited_utc, last_visited_utc)
    SELECT s.system, NULL, NULL, NULL FROM src s
    WHERE NOT EXISTS (SELECT 1 FROM {TABLE} t WHERE t.system = s.system)""")

after = finish(con, TABLE, before)

# Rows the table holds and the store does not. Reported, NEVER deleted -- see above.
stale = con.execute(f"""SELECT count(*) FROM {TABLE} t
    WHERE NOT EXISTS (SELECT 1 FROM src s WHERE s.system = t.system)""").fetchone()[0]
if stale:
    print(f"  {stale:,} row(s) in the table but NOT in the store -- LEFT IN PLACE. "
          f"Expected: journals age out and the store forgets. The table does not.")

# The two app-state tables record DIFFERENT things and neither contains the other.
# Visited-but-never-seen is the direction that surprises people, so state it every run.
only_v, only_s, both = con.execute("""
    SELECT count(*) FILTER (WHERE s.system IS NULL),
           count(*) FILTER (WHERE v.system IS NULL),
           count(*) FILTER (WHERE v.system IS NOT NULL AND s.system IS NOT NULL)
    FROM system_visited v FULL OUTER JOIN system_seen s USING (system)""").fetchone()
print(f"\n  visited AND seen        {both:>8,}")
print(f"  visited, never seen     {only_v:>8,}  (arrived without plotting -- normal)")
print(f"  seen, never visited     {only_s:>8,}  (revealed from the galaxy map)")

print("\nDONE_LOAD_SYSTEM_VISITED")
