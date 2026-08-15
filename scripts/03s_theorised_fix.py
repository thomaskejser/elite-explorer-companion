"""CORRECTED theorised-systems enumeration.

Bug found (2026-07-13): the old method filled indices 0..max per boxel, but Forge
boxel numbering does NOT always start at 0 (~28% of h-boxels start higher; Blua
Eaec's h-systems run 8..111). Filling from 0 fabricated non-existent low-index
systems (confirmed in-game: 'Blua Eaec AA-A h0' = empty space).

Fix: theorised = INTERNAL gaps only (strictly between a boxel's min and max
observed index), and only in boxels dense enough that a gap is trustworthy
(observed >= DENSITY_MIN of the min..max range). No below-min, no above-max, no
inference from sparse boxels. Internal gaps are LIKELY-real (e.g. Blua Eaec h95
confirmed exists; h74 uncertain) -- not guaranteed.
"""
import duckdb, pathlib
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8"); con.execute("SET preserve_insertion_order=false")
KB=r"regexp_replace(name,'[0-9]+(-[0-9]+)?$','')"; TK=r"regexp_extract(name,'([0-9]+(-[0-9]+)?)$',1)"
BX=f"CASE WHEN {TK} LIKE '%-%' THEN {KB}||'#'||split_part({TK},'-',1) ELSE {KB} END"
IX=f"CASE WHEN {TK} LIKE '%-%' THEN CAST(split_part({TK},'-',2) AS BIGINT) ELSE CAST({TK} AS BIGINT) END"
SEC=f"regexp_replace({KB},' [A-Z]{{1,2}}-[A-Z] [a-h]$','')"
DENSITY_MIN = 0.5   # need >=50% of the min..max index range observed to trust gaps

print(f"old theorised_system rows: {con.execute('select count(*) from theorised_system').fetchone()[0]:,}")

con.execute(f"""
CREATE OR REPLACE TEMP TABLE obs AS
SELECT {BX} AS boxel, {IX} AS idx, mass_code, {SEC} AS sector, x, y, z,
       sqrt(pow(x-25.2,2)+pow(z-25900,2)) AS plane_r
FROM sys_feat WHERE mass_code IN ('f','g','h') AND {TK} <> ''
""")
con.execute("""
CREATE OR REPLACE TEMP TABLE bx AS
SELECT boxel, any_value(mass_code) mass_code, any_value(sector) sector,
       min(idx) mn, max(idx) mx, count(*) obs,
       avg(x) x, avg(y) y, avg(z) z, avg(plane_r) plane_r
FROM obs GROUP BY boxel
""")
# density-qualified boxels (trustworthy internal gaps)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE bx_ok AS
SELECT * FROM bx WHERE mx > mn AND obs::DOUBLE / (mx - mn + 1) >= {DENSITY_MIN}
""")
print("building corrected theorised_system (internal gaps in dense boxels)...", flush=True)
con.execute("""
CREATE OR REPLACE TABLE theorised_system AS
WITH gen AS (
  SELECT b.boxel, b.mass_code, b.sector, b.x, b.y, b.z, b.plane_r, t.gidx AS boxel_index
  FROM bx_ok b, unnest(range(b.mn, b.mx+1)) AS t(gidx)
)
SELECT gen.boxel AS boxel_key, gen.boxel_index, gen.mass_code, gen.sector,
       gen.x, gen.y, gen.z, gen.plane_r,
       sqrt(pow(gen.x-25.2,2)+pow(gen.y+20.9,2)+pow(gen.z-25900,2)) AS r_sgra,
       TRUE AS is_theorised
FROM gen LEFT JOIN obs o ON o.boxel=gen.boxel AND o.idx=gen.boxel_index
WHERE o.boxel IS NULL
""")
# corrected per-boxel rollup
con.execute("""
CREATE OR REPLACE TABLE theorised_boxels AS
SELECT b.boxel, b.mass_code, b.sector, b.x, b.y, b.z, b.plane_r,
       sqrt(pow(b.x-25.2,2)+pow(b.y+20.9,2)+pow(b.z-25900,2)) AS r_sgra,
       b.obs AS observed, b.mn AS min_idx, b.mx AS max_idx,
       coalesce(t.gaps,0) AS missing
FROM bx_ok b
LEFT JOIN (SELECT boxel_key, count(*) gaps FROM theorised_system GROUP BY 1) t
       ON t.boxel_key = b.boxel
""")

n=con.execute('select count(*) from theorised_system').fetchone()[0]
nb=con.execute('select count(*) from theorised_boxels').fetchone()[0]
print(f"\nNEW theorised_system rows: {n:,}   (dense qualified boxels: {nb:,})")
for r in con.execute("select mass_code, count(*) from theorised_system group by 1 order by 1").fetchall():
    print(f"  mc={r[0]}: {r[1]:,}")

print("\n=== Blua Eaec AA-A h verification (should be exactly the internal gaps 74, 95) ===")
for r in con.execute("select boxel_key, boxel_index from theorised_system where boxel_key like 'Blua Eaec AA-A h%' order by boxel_index").fetchall():
    print(f"  {r[0]}{r[1]}")
con.close()
print("\nDONE_03S")
