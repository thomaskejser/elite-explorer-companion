"""Resolve every catalogued POI observation to (system_id, body suffix, poi_id).

Shared by `etl/system_known/poi.py` and `etl/system_body/poi.py`, which
own the two tables that carry `id_poi`. It lives here rather than in either script
because both need the IDENTICAL split -- if they disagreed about what counts as
body-level, a POI would be written to both tables or to neither.

THE SPLIT. Canonn is the only source that names a body, and its `body` column is the
FULL name including the system prefix ("Oodgosly GI-B d13-11 7 B Ring"), whereas
`system_body.system_body` holds the suffix RELATIVE to the system ("7 B Ring", or ''
for the primary star). So the suffix is derived by stripping the system prefix, and:

    body IS NULL, or body = system   ->  SYSTEM-level, goes to system_known.id_poi
    anything else                    ->  BODY-level,   goes to system_body.id_poi

`body = system` is not a rarity -- 8,166 Canonn Cloud events say the body IS the system,
which is the catalogue's way of recording "somewhere in here". Treating those as a body
would invent 8,166 bodies that do not exist.

THE CASCADE. `id_poi` is a single column, and 32,058 systems hold more than one POI
FAMILY with no body attribution, so something must win. RAREST WINS: the POI seen in
the fewest systems takes the column, because the rare thing is the reason you would
fly there at all -- a system with a Lagrange cloud and a bulb mollusc is a mollusc
trip. Ties break on poi_id so the choice is deterministic across runs. The full
multi-POI truth is NOT lost; it stays in `system_phenomenon`, which is keyed
(system_id, phenomenon) precisely so it can hold all of them.
"""

# This module maps to poi_id by NAME; the family lives on the poi dimension row.

def stage_poi_events(con, verbose=True):
    """Create staging.poi_event: one row per resolved observation.

    Columns: system_id, body_suffix (NULL = system-level), poi_id, reported_at.
    Requires a populated system_known and a loaded `poi` table. system_known.system_id
    IS the id64, so every source's id64 joins to it directly.
    """
    if not con.execute("SELECT count(*) FROM system_known").fetchone()[0]:
        raise SystemExit("system_known is empty -- run: python etl/system_known/refresh.py")
    if not con.execute("SELECT count(*) FROM poi").fetchone()[0]:
        raise SystemExit("`poi` is empty -- run: python etl/poi/refresh.py")

    if verbose:
        print("  resolving POI observations to systems and bodies...", flush=True)
    con.execute("""
CREATE OR REPLACE TABLE staging.poi_event AS
WITH raw AS (
    -- canonn: the only source with a body name and a hud_category
    SELECT c.id64                              AS system_id64,
           nullif(trim(c.body), '')            AS body_full,
           nullif(trim(c.system), '')          AS sys_name,
           c.english_name                      AS poi_name,
           TRY_CAST(c.reported_at AS TIMESTAMP) AS reported_at
    FROM canonn_codex_event c
    WHERE c.id64 IS NOT NULL
      AND (c.hud_category IN ('Cloud', 'Anomaly', 'Guardian', 'Thargoid')
           OR (c.hud_category = 'Tourist'
               AND lower(c.english_name) LIKE '%green%'
               AND lower(c.english_name) LIKE '%giant%'))
    UNION ALL
    SELECT e.systemId64, NULL, nullif(trim(e.systemName), ''), e.name,
           TRY_CAST(e.reportedOn AS TIMESTAMP)
    FROM edsm_codex_entry e
    WHERE e.systemId64 IS NOT NULL AND e.name = 'Green Gas Giant'
    UNION ALL
    -- GEC `name` is the POI's own nickname, never the system, so it is not used at all
    SELECT g.id64, NULL, NULL, g.type, CAST(NULL AS TIMESTAMP)
    FROM edastro_point_of_interest g
    WHERE g.id64 IS NOT NULL AND g.type IS NOT NULL
)
SELECT b.system_id,
       -- strip the system prefix; '' (the primary star) is a REAL suffix and must
       -- survive, so only body_full = sys_name collapses to system-level.
       CASE WHEN r.body_full IS NULL              THEN NULL
            WHEN r.sys_name IS NULL               THEN r.body_full
            WHEN r.body_full = r.sys_name         THEN NULL
            WHEN starts_with(r.body_full, r.sys_name)
                 THEN trim(substr(r.body_full, length(r.sys_name) + 1))
            ELSE r.body_full
       END                                        AS body_suffix,
       p.poi_id,
       r.reported_at
FROM raw r
JOIN system_known b        ON b.system_id = r.system_id64
JOIN poi p                ON p.poi = r.poi_name
""")

    # Rarity is measured over SYSTEMS, not observations: a heavily-trafficked system
    # gets many reports of one cloud, and letting that inflate a POI's apparent
    # commonness would hand the column to the wrong one.
    con.execute("""
CREATE OR REPLACE TABLE staging.poi_rarity AS
SELECT poi_id, count(DISTINCT system_id) AS n_systems
FROM staging.poi_event GROUP BY 1
""")

    if verbose:
        r = con.execute("""SELECT count(*), count(DISTINCT system_id),
               count(*) FILTER (WHERE body_suffix IS NOT NULL),
               count(DISTINCT poi_id) FROM staging.poi_event""").fetchone()
        print(f"    {r[0]:,} observations over {r[1]:,} systems "
              f"({r[2]:,} body-attributed, {r[3]:,} distinct POI kinds)")
    return "staging.poi_event"


def winner_sql(keys, where):
    """Rarest-POI-wins pick: one winning poi_id per `keys` tuple.

    `keys` is a list of column names to partition on -- ['system_id'] for the
    system-level pass, ['system_id', 'body_suffix'] for the body-level one. `where`
    filters staging.poi_event to that scope.

    Deterministic: ties break on poi_id, so two runs over unchanged data pick the same
    winner and the merge stays a genuine no-op. Without the tiebreak the choice follows
    parallel scan order and every re-run reports spurious updates -- the same class of
    bug as the unrounded float aggregates in ETL.md.
    """
    k = ", ".join(keys)
    return f"""
SELECT {k}, poi_id FROM (
    SELECT e.*, row_number() OVER (PARTITION BY {k}
                                   ORDER BY r.n_systems ASC, e.poi_id ASC) AS rn
    FROM (SELECT DISTINCT {k}, poi_id FROM staging.poi_event WHERE {where}) e
    JOIN staging.poi_rarity r ON r.poi_id = e.poi_id
) WHERE rn = 1"""
