"""Export CATALOGUED points of interest worth routing to, for the app's target list.

Replaces the older build_nsp.py. These are not predictions -- every row is a system
where somebody has already reported the thing -- and that is exactly why they belong
here: they count as a discovery for YOU no matter how many commanders got there first,
so unlike a black hole there is no reason to restrict them to uncatalogued systems.
Two labels so far, both rendered in the app's Mass column:

  NSP  Notable Stellar Phenomena and anomalies -- 68,583 systems. Canonn's
       `hud_category='Cloud'` plus its `Anomaly` category, plus EDSM's codex. The
       Cloud category is broader than its name suggests and correctly so: ice and
       metallic crystals, peduncle trees, bulb molluscs and quadripartite pods are all
       space-based and all announce themselves as "Notable stellar phenomena" in the
       nav panel. Surface geology (`hud_category='Geology'`, 97,788 systems) is NOT
       included -- it needs a landing, not a look.

  GGG  Green gas giants -- 67 systems, the entire known galactic population. A colour
       bug rather than a body type: green is the default before the colour calculation
       runs, and something in a few giants' characteristics keeps it there. Unearned by
       any model -- see DEAD_ENDS.md, which records why they cannot be predicted -- so
       a catalogue is the only way to reach one.

Three sources are unioned for GGG because each is missing systems the others have, and
they are joined on id64, never on name: EDAstro's GEC rows carry the POI's OWN name
(often a nickname), so a name union inflates 67 systems to 117.

Coordinates come from `sys_feat` -- all 67 GGG and nearly all NSP systems are in the
spine, and it is what every distance in the app is measured against. Canonn's own x/y/z
is the fallback for NSP systems the spine does not have.

Usage:  python scripts/build_poi.py
"""
import duckdb, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "app"
OUT = APP / "poi.parquet"
APP.mkdir(exist_ok=True)

con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"), read_only=True)
con.execute("SET memory_limit='6GB'")
con.execute("SET threads=8")
con.execute("SET preserve_insertion_order=false")

print("collapsing NSP codex observations to systems...", flush=True)
con.execute("""
CREATE OR REPLACE TEMP TABLE nsp AS
SELECT system_id64,
       any_value(system_name)                                   AS obs_name,
       count(*)                                                 AS obs,
       string_agg(DISTINCT nsp_family, '+' ORDER BY nsp_family)  AS kinds,
       min(x) AS ox, min(y) AS oy, min(z) AS oz
FROM norm.codex_observation
WHERE is_nsp AND system_id64 IS NOT NULL
GROUP BY 1
""")

# Green giants. `hud_category='Tourist'` AND both 'green' and 'giant' in the name is the
# filter that matters: `$Codex_Ent_Gas_Clds_Green_*` (Viride Lagrange Cloud) is a green
# CLOUD, hud_category='Cloud', and is already an NSP row. Conflating the two is the
# specific mistake DEAD_ENDS.md warns about.
print("collecting green gas giants from all three catalogues...", flush=True)
con.execute("""
CREATE OR REPLACE TEMP TABLE ggg AS
WITH src AS (
  SELECT id64 AS system_id64, system AS obs_name, english_name AS kind,
         TRY_CAST(x AS DOUBLE) ox, TRY_CAST(y AS DOUBLE) oy, TRY_CAST(z AS DOUBLE) oz
  FROM canonn_codex_event
  WHERE hud_category = 'Tourist'
    AND lower(english_name) LIKE '%green%' AND lower(english_name) LIKE '%giant%'
  UNION ALL
  SELECT systemId64, systemName, 'Green Gas Giant', NULL, NULL, NULL
  FROM edsm_codex_entry WHERE name = 'Green Gas Giant'
  UNION ALL
  -- the GEC row's `name` is the POI's nickname, not the system, so it is not used
  SELECT id64, NULL, 'Green Gas Giant',
         CASE WHEN len(coordinates)=3 THEN coordinates[1] END,
         CASE WHEN len(coordinates)=3 THEN coordinates[2] END,
         CASE WHEN len(coordinates)=3 THEN coordinates[3] END
  FROM edastro_point_of_interest WHERE type = 'Green Gas Giants'
)
SELECT system_id64,
       any_value(obs_name) AS obs_name,
       count(*)            AS obs,
       -- The Sudarsky class is the interesting part, so keep the distinct set -- but
       -- EDSM and the GEC only ever say "Green Gas Giant", and pasting that next to
       -- "Green Class III Gas Giant" tells you nothing. Keep the generic label only
       -- when it is all we have.
       coalesce(string_agg(DISTINCT nullif(kind, 'Green Gas Giant'), '+'
                           ORDER BY nullif(kind, 'Green Gas Giant')),
                'Green Gas Giant') AS kinds,
       min(ox) AS ox, min(oy) AS oy, min(oz) AS oz
FROM src WHERE system_id64 IS NOT NULL
GROUP BY 1
""")
for r in con.execute("""SELECT count(*), count(ox) FROM ggg""").fetchall():
    print(f"  {r[0]} green-giant systems ({r[1]} with catalogue coordinates)")

print("resolving names and coordinates...", flush=True)
con.execute(f"""
COPY (
  SELECT * FROM (
    SELECT 'NSP' AS label,
           coalesce(s.name, n.obs_name)       AS name,
           CAST(coalesce(s.x, n.ox) AS FLOAT) AS x,
           CAST(coalesce(s.y, n.oy) AS FLOAT) AS y,
           CAST(coalesce(s.z, n.oz) AS FLOAT) AS z,
           coalesce(n.kinds, 'nsp')           AS kinds, n.obs
    FROM nsp n LEFT JOIN sys_feat s USING(system_id64)
    UNION ALL
    SELECT 'GGG',
           coalesce(s.name, g.obs_name),
           CAST(coalesce(s.x, g.ox) AS FLOAT),
           CAST(coalesce(s.y, g.oy) AS FLOAT),
           CAST(coalesce(s.z, g.oz) AS FLOAT),
           coalesce(g.kinds, 'green gas giant'), g.obs
    FROM ggg g LEFT JOIN sys_feat s USING(system_id64)
  )
  WHERE name IS NOT NULL AND x IS NOT NULL
) TO '{OUT.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
""")

n = con.execute(f"SELECT count(*) FROM '{OUT.as_posix()}'").fetchone()[0]
print(f"\nwrote {OUT}  ({n:,} rows, {OUT.stat().st_size/1e6:.1f} MB)")
print(f"  {'label':<7}{'systems':>10}")
for r in con.execute(f"""SELECT label, count(*) FROM '{OUT.as_posix()}'
                         GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]:<7}{r[1]:>10,}")
print(f"\n  {'label':<7}{'kinds':<44}{'systems':>9}")
for r in con.execute(f"""SELECT label, kinds, count(*) c FROM '{OUT.as_posix()}'
                         GROUP BY 1,2 ORDER BY 1, c DESC LIMIT 14""").fetchall():
    print(f"  {r[0]:<7}{str(r[1])[:43]:<44}{r[2]:>9,}")
dup = con.execute(f"""SELECT count(*) FROM (SELECT name FROM '{OUT.as_posix()}'
                      GROUP BY 1 HAVING count(*) > 1)""").fetchone()[0]
if dup:
    print(f"\n  {dup:,} system(s) carry both labels -- each gets its own row")
con.close()
print("\nDONE_BUILD_POI")
