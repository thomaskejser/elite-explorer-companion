"""Tier-1 rare stars: build per-system flags, show mass-code gating, build the
e/f/g/h boxel table with per-target counts (reuses BH/WR machinery).

Targets: neutron, white dwarf, Herbig Ae/Be, O-type, supergiant.
Frame = mass codes e/f/g/h (high-mass-code space where rare stars concentrate and
where our theorised/coverage machinery is validated). Gating table shows full a-h.
"""
import duckdb, pathlib, time
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8"); con.execute("SET preserve_insertion_order=false")
KB=r"regexp_replace(name,'[0-9]+(-[0-9]+)?$','')"; TK=r"regexp_extract(name,'([0-9]+(-[0-9]+)?)$',1)"
BX=f"CASE WHEN {TK} LIKE '%-%' THEN {KB}||'#'||split_part({TK},'-',1) ELSE {KB} END"
IX=f"CASE WHEN {TK} LIKE '%-%' THEN CAST(split_part({TK},'-',2) AS BIGINT) ELSE CAST({TK} AS BIGINT) END"

t0=time.time()
print("building star_agg (per-system rare-star flags)...", flush=True)
con.execute("""
CREATE OR REPLACE TABLE star_agg AS
SELECT system_id64,
  max((sub_type='Neutron Star')::INT)          AS has_neutron,
  max((sub_type LIKE 'White Dwarf%')::INT)     AS has_wd,
  max((sub_type='Herbig Ae/Be Star')::INT)     AS has_herbig,
  max((sub_type='O (Blue-White) Star')::INT)   AS has_otype,
  max((sub_type LIKE '%super giant%')::INT)    AS has_supergiant
FROM spansh_body WHERE type='Star' GROUP BY system_id64
""")
print(f"  star_agg rows: {con.execute('select count(*) from star_agg').fetchone()[0]:,}  ({(time.time()-t0)/60:.1f} min)", flush=True)

print("\n=== mass-code gating: rate% among SCANNED systems (full a-h) ===")
print(f"  {'mc':>4}{'scanned':>12}{'neutron%':>10}{'whiteDwarf%':>12}{'Herbig%':>9}{'Otype%':>8}{'supergiant%':>12}")
for r in con.execute("""
  SELECT s.mass_code, count(*) sc,
    round(100.0*sum(coalesce(a.has_neutron,0))/count(*),3),
    round(100.0*sum(coalesce(a.has_wd,0))/count(*),3),
    round(100.0*sum(coalesce(a.has_herbig,0))/count(*),4),
    round(100.0*sum(coalesce(a.has_otype,0))/count(*),4),
    round(100.0*sum(coalesce(a.has_supergiant,0))/count(*),4)
  FROM sys_feat s LEFT JOIN star_agg a USING(system_id64)
  WHERE s.is_scanned GROUP BY 1 ORDER BY 1
""").fetchall():
    mc = r[0] if r[0] else '(named)'
    print(f"  {mc:>4}{r[1]:>12,}{r[2]:>10}{r[3]:>12}{r[4]:>9}{r[5]:>8}{r[6]:>12}")

print("\nbuilding star_boxels (e/f/g/h) with per-target counts...", flush=True)
t1=time.time()
con.execute(f"""
CREATE OR REPLACE TABLE star_boxels AS
SELECT {BX} AS boxel, s.mass_code,
       regexp_replace({KB},' [A-Z]{{1,2}}-[A-Z] [a-h]$','') AS sector,
       avg(s.x) x, avg(s.y) y, avg(s.z) z, avg(s.plane_r) plane_r,
       sqrt(avg(s.x)^2+avg(s.y)^2+avg(s.z)^2) AS dist_sol,
       max({IX})+1 AS pop, count(*) AS in_db,
       count(*) FILTER (WHERE s.is_scanned) AS scanned,
       sum(coalesce(a.has_neutron,0))    AS n_neutron,
       sum(coalesce(a.has_wd,0))         AS n_wd,
       sum(coalesce(a.has_herbig,0))     AS n_herbig,
       sum(coalesce(a.has_otype,0))      AS n_otype,
       sum(coalesce(a.has_supergiant,0)) AS n_supergiant
FROM sys_feat s LEFT JOIN star_agg a USING(system_id64)
WHERE s.mass_code IN ('e','f','g','h') AND {TK}<>''
GROUP BY 1,2,3
""")
con.execute("ALTER TABLE star_boxels ADD COLUMN missing BIGINT")
con.execute("UPDATE star_boxels SET missing = pop - in_db")
n=con.execute("select count(*) from star_boxels").fetchone()[0]
print(f"  star_boxels rows: {n:,}  ({(time.time()-t1)/60:.1f} min)", flush=True)
print(f"\nDONE_03M total {(time.time()-t0)/60:.1f} min", flush=True)
con.close()
