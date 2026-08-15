"""Raxxla scoping, option 3: geometric anomalies.
 A) off-plane outliers (extreme |y| height above/below the galactic disk)
 B) beyond-rim / extreme-coordinate systems
 C) ISOLATION -- systems with no known neighbour within ~100 ly (beyond normal
    jump range => 'unreachable'), via a 100 ly grid + 27-cell neighbourhood check.
Exploratory; won't find Raxxla (not in data) but characterises geometric oddities.
"""
import duckdb, pathlib
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")
PROC = r"regexp_matches(name, '[A-Z][A-Z]-[A-Z] [a-h][0-9]')"

print("### A) height off the galactic plane (|y|) ###")
for r in con.execute("""
  SELECT CASE WHEN abs(y)<1000 THEN '1 <1k (disk)' WHEN abs(y)<2000 THEN '2 1-2k'
              WHEN abs(y)<3500 THEN '3 2-3.5k' WHEN abs(y)<6000 THEN '4 3.5-6k'
              ELSE '5 >6k (halo!)' END band, count(*) c, round(max(abs(y))) maxy
  FROM spansh_system GROUP BY 1 ORDER BY 1
""").fetchall():
    print(f"  {r[0]:>16}: {r[1]:>13,}   (max |y| in band {int(r[2]):,})")
print("  most extreme off-plane systems:")
for r in con.execute(f"""
  SELECT name, round(y) y, round(sqrt(x*x+z*z)) plane_r, NOT {PROC} AS handnamed
  FROM spansh_system ORDER BY abs(y) DESC LIMIT 12
""").fetchall():
    print(f"    {str(r[0])[:30]:30s} y={int(r[1]):>8,}  plane_r={int(r[2]):>7,}  {'HAND-NAMED' if r[3] else ''}")

print("\n### B) beyond the rim (largest galactocentric radius) ###")
for r in con.execute(f"""
  SELECT name, round(sqrt(pow(x-25.2,2)+pow(z-25900,2))) plane_r, round(y) y, NOT {PROC} h
  FROM spansh_system ORDER BY plane_r DESC LIMIT 8
""").fetchall():
    print(f"    {str(r[0])[:30]:30s} plane_r={int(r[1]):>7,}  y={int(r[2]):>7,}  {'HAND-NAMED' if r[3] else ''}")

print("\n### C) isolation: no known neighbour within ~100 ly ###")
R=100
con.execute(f"""
CREATE OR REPLACE TEMP TABLE cells AS
SELECT floor(x/{R}) cx, floor(y/{R}) cy, floor(z/{R}) cz, count(*) n
FROM spansh_system GROUP BY 1,2,3
""")
con.execute("CREATE OR REPLACE TEMP TABLE singles AS SELECT cx,cy,cz FROM cells WHERE n=1")
print(f"  occupied {R}ly cells: {con.execute('select count(*) from cells').fetchone()[0]:,}"
      f"   singleton cells: {con.execute('select count(*) from singles').fetchone()[0]:,}")
# offsets -1..1 in each axis
con.execute("""CREATE OR REPLACE TEMP TABLE off AS
  SELECT a.d dx, b.d dy, c.d dz FROM (VALUES(-1),(0),(1)) a(d),(VALUES(-1),(0),(1)) b(d),(VALUES(-1),(0),(1)) c(d)""")
con.execute("""
CREATE OR REPLACE TEMP TABLE isolated AS
SELECT s.cx, s.cy, s.cz
FROM singles s JOIN off o ON true
LEFT JOIN cells c ON c.cx=s.cx+o.dx AND c.cy=s.cy+o.dy AND c.cz=s.cz+o.dz
GROUP BY s.cx,s.cy,s.cz HAVING sum(coalesce(c.n,0))=1
""")
niso = con.execute("select count(*) from isolated").fetchone()[0]
print(f"  systems with NO neighbour within ~{R}ly: {niso:,}")
# where are they? by galactocentric radius
print("  isolation by region (are they just deep-fringe, or anomalous inner systems?):")
for r in con.execute(f"""
  WITH iso AS (SELECT ss.name, ss.x, ss.y, ss.z FROM isolated i JOIN spansh_system ss
    ON floor(ss.x/{R})=i.cx AND floor(ss.y/{R})=i.cy AND floor(ss.z/{R})=i.cz)
  SELECT CASE WHEN sqrt(pow(x-25.2,2)+pow(z-25900,2))<30000 THEN '1 inner/mid (<30kly) ANOMALOUS'
              WHEN sqrt(pow(x-25.2,2)+pow(z-25900,2))<45000 THEN '2 outer 30-45kly'
              ELSE '3 rim >45kly (expected sparse)' END reg, count(*) c
  FROM iso GROUP BY 1 ORDER BY 1
""").fetchall():
    print(f"    {r[0]:>34}: {r[1]:>9,}")
print("  isolated systems in the INNER/MID galaxy (most anomalous -- alone despite populated region):")
for r in con.execute(f"""
  WITH iso AS (SELECT ss.name, ss.x, ss.y, ss.z FROM isolated i JOIN spansh_system ss
    ON floor(ss.x/{R})=i.cx AND floor(ss.y/{R})=i.cy AND floor(ss.z/{R})=i.cz)
  SELECT name, round(sqrt(pow(x-25.2,2)+pow(z-25900,2))) plane_r, round(y) y,
         NOT {PROC} h FROM iso
  WHERE sqrt(pow(x-25.2,2)+pow(z-25900,2))<25000 ORDER BY abs(y) DESC LIMIT 15
""").fetchall():
    print(f"    {str(r[0])[:30]:30s} plane_r={int(r[1]):>7,}  y={int(r[2]):>7,}  {'HAND-NAMED' if r[3] else ''}")
con.close()
