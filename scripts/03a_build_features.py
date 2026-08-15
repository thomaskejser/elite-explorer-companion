"""Build the BH/WR modelling feature tables and print base rates.

Outputs two persistent tables in elite_mapping.duckdb:
  bhwr_system : per-SCANNED-system star aggregate (has_bh/has_wr/has_neutron, n_stars)
  sys_feat    : per-KNOWN-system features over all ~195M Spansh systems --
                mass_code (from procedural name, available even when unscanned),
                galactic-position features, labels, and is_scanned flag.

Coverage-aware by construction: labels/negatives come only from scanned systems;
unscanned systems are candidates, never negatives.
"""
import duckdb, pathlib, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'")
con.execute("SET threads=8")
con.execute("SET preserve_insertion_order=false")   # lower memory for big ops

# Sagittarius A* (galactic centre) in ED coords; galactic plane is y=0.
SGRA = "25.21875, -20.90625, 25899.96875"
MASS = r"regexp_extract(name, '([a-h])[0-9]+(-[0-9]+)?$', 1)"

t0 = time.time()
print("building bhwr_system (aggregate over 570M bodies)...", flush=True)
con.execute("""
CREATE OR REPLACE TABLE bhwr_system AS
SELECT system_id64,
       max((sub_type='Black Hole')::INT)          AS has_bh,
       max((sub_type ILIKE 'Wolf-Rayet%')::INT)   AS has_wr,
       max((sub_type='Neutron Star')::INT)        AS has_neutron,
       count(*) FILTER (WHERE type='Star')         AS n_stars,
       count(*)                                    AS n_bodies_scanned
FROM spansh_body
GROUP BY system_id64
""")
print(f"  bhwr_system rows: {con.execute('select count(*) from bhwr_system').fetchone()[0]:,}  "
      f"({(time.time()-t0)/60:.1f} min)", flush=True)

t1 = time.time()
print("building sys_feat (all ~195M known systems)...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE sys_feat AS
SELECT
    s.system_id64,
    s.name,
    s.x, s.y, s.z,
    {MASS}                                          AS mass_code,
    sqrt(pow(s.x-25.21875,2)+pow(s.y+20.90625,2)+pow(s.z-25899.96875,2)) AS r_sgra,
    sqrt(pow(s.x-25.21875,2)+pow(s.z-25899.96875,2))                     AS plane_r,
    abs(s.y)                                        AS height,
    s.declared_body_count,
    (a.system_id64 IS NOT NULL)                     AS is_scanned,
    coalesce(a.n_stars, 0)                          AS n_stars,
    coalesce(a.has_bh, 0)                           AS has_bh,
    coalesce(a.has_wr, 0)                           AS has_wr,
    coalesce(a.has_neutron, 0)                      AS has_neutron,
    (coalesce(a.has_bh,0)=1 OR coalesce(a.has_wr,0)=1)::INT AS has_target
FROM spansh_system s
LEFT JOIN bhwr_system a USING (system_id64)
""")
print(f"  sys_feat rows: {con.execute('select count(*) from sys_feat').fetchone()[0]:,}  "
      f"({(time.time()-t1)/60:.1f} min)", flush=True)

def show(title, sql):
    print(f"\n=== {title} ===", flush=True)
    for row in con.execute(sql).fetchall():
        print("  " + "  ".join(f"{v:,}" if isinstance(v,(int,)) else
                                (f"{v:.5f}" if isinstance(v,float) else str(v)) for v in row), flush=True)

# Base rate of BH/WR among SCANNED systems, by mass code.
show("BH/WR rate among SCANNED systems, by mass_code",
     """
     SELECT coalesce(nullif(mass_code,''),'(named)') AS mass_code,
            count(*)                                  AS scanned_systems,
            sum(has_bh)                               AS bh_systems,
            sum(has_wr)                               AS wr_systems,
            round(100.0*sum(has_bh)/count(*), 4)      AS bh_pct,
            round(100.0*sum(has_wr)/count(*), 4)      AS wr_pct
     FROM sys_feat WHERE is_scanned
     GROUP BY 1 ORDER BY 1
     """)

# Base rate by distance-from-core shell (scanned only).
show("BH/WR rate among SCANNED systems, by distance-from-Sgr A* (ly)",
     """
     SELECT width_bucket(r_sgra, 0, 30000, 10)*3000 AS shell_start_ly,
            count(*) scanned, sum(has_bh) bh, sum(has_wr) wr,
            round(100.0*sum(has_bh)/count(*),4) bh_pct,
            round(100.0*sum(has_wr)/count(*),4) wr_pct
     FROM sys_feat WHERE is_scanned
     GROUP BY 1 ORDER BY 1
     """)

# How many candidates (unscanned) sit in each mass code -- the search space.
show("Candidate (UNSCANNED) systems by mass_code",
     """
     SELECT coalesce(nullif(mass_code,''),'(named)') AS mass_code,
            count(*) unscanned_systems
     FROM sys_feat WHERE NOT is_scanned
     GROUP BY 1 ORDER BY 1
     """)

con.close()
print(f"\nDONE_03A total {(time.time()-t0)/60:.1f} min", flush=True)
