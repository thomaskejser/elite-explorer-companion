"""Find 'out of place' systems: names that don't match their location.

Procedural names are spatially deterministic -- every system in sector 'Foo' must
sit in one ~1280 ly cube. So:
 (1) name/coordinate mismatch: a procedural system far from its sector's centroid
     -> its name is inconsistent with where it actually is (glitch, or oddity).
 (2) non-procedural (hand-named) systems -> not Stellar-Forge auto-generated at all.
Both are candidate 'special' systems worth a human look.
"""
import duckdb, pathlib
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")

PROC = r"regexp_matches(name, '[A-Z][A-Z]-[A-Z] [a-h][0-9]')"   # has a procedural boxel token
SECTOR = r"regexp_replace(name,' [A-Z]{1,2}-[A-Z] [a-h][0-9]+(-[0-9]+)?$','')"

print("=== (1) procedural systems most OUT OF PLACE vs their sector centroid ===")
print("    (a 1280 ly sector spans <=~2200 ly corner-to-corner; deviation >> that is anomalous)")
con.execute(f"""
CREATE OR REPLACE TEMP TABLE proc AS
SELECT system_id64, name, x, y, z, {SECTOR} AS sector
FROM spansh_system WHERE {PROC}
""")
con.execute("""
CREATE OR REPLACE TEMP TABLE cent AS
SELECT sector, count(*) n, avg(x) cx, avg(y) cy, avg(z) cz,
       stddev_pop(x)+stddev_pop(y)+stddev_pop(z) AS spread
FROM proc GROUP BY 1
""")
print(f"  distinct procedural sectors: {con.execute('select count(*) from cent').fetchone()[0]:,}")
print(f"  {'system':30}{'sector_n':>9}{'deviation_ly':>13}  actual(x,y,z)")
for r in con.execute("""
    SELECT p.name, c.n, sqrt((p.x-c.cx)^2+(p.y-c.cy)^2+(p.z-c.cz)^2) dev, p.x, p.y, p.z
    FROM proc p JOIN cent c USING(sector)
    WHERE c.n >= 8
    ORDER BY dev DESC LIMIT 25
""").fetchall():
    print(f"  {str(r[0])[:28]:28s}{int(r[1]):>9,}{int(r[2]):>13,}  ({int(r[3]):,}, {int(r[4]):,}, {int(r[5]):,})")

print("\n=== deviation distribution (how many procedural systems are far from their sector) ===")
for r in con.execute("""
    SELECT CASE WHEN dev<2500 THEN '1 <2.5k (normal)' WHEN dev<5000 THEN '2 2.5-5k'
                WHEN dev<10000 THEN '3 5-10k' WHEN dev<50000 THEN '4 10-50k'
                ELSE '5 >50k' END band, count(*) c
    FROM (SELECT sqrt((p.x-c.cx)^2+(p.y-c.cy)^2+(p.z-c.cz)^2) dev
          FROM proc p JOIN cent c USING(sector) WHERE c.n>=8)
    GROUP BY 1 ORDER BY 1
""").fetchall():
    print(f"  {r[0]:>18}: {r[1]:>14,}")

print("\n=== (2) non-procedural (hand-named) systems: how many, and the deep-space ones ===")
r = con.execute(f"SELECT count(*) FROM spansh_system WHERE NOT ({PROC})").fetchone()[0]
print(f"  non-procedural named systems: {r:,}")
print(f"  {'name':34}{'dist_from_Sol_ly':>17}  coords")
for r in con.execute(f"""
    SELECT name, sqrt(x*x+y*y+z*z) d, x, y, z FROM spansh_system
    WHERE NOT ({PROC}) AND name NOT LIKE 'HIP %' AND name NOT LIKE 'HD %'
      AND name NOT LIKE 'Col % Sector%' AND name NOT LIKE '% Sector %'
    ORDER BY d DESC LIMIT 20
""").fetchall():
    print(f"  {str(r[0])[:32]:32s}{int(r[1]):>17,}  ({int(r[2]):,}, {int(r[3]):,}, {int(r[4]):,})")
con.close()
