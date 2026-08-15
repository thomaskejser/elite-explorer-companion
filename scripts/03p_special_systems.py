"""Raxxla-hunt scoping: (1) truly hand-authored systems (non-procedural, no
catalogue digits) and (2) the curated mystery/restricted/historical POI layer.
Exploratory search-space narrowing -- NOT a prediction.
"""
import duckdb, pathlib
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")

PROC  = r"regexp_matches(name, '[A-Z][A-Z]-[A-Z] [a-h][0-9]')"   # procedural boxel token
DIGIT = r"regexp_matches(name, '[0-9]')"                          # catalogue names carry digits

print("### (1) hand-authored systems: non-procedural AND no catalogue digits ###")
tot = con.execute(f"SELECT count(*) FROM spansh_system WHERE NOT {PROC} AND NOT {DIGIT}").fetchone()[0]
print(f"  count: {tot:,}")
print("\n  deepest such systems (dist from Sol > 5000 ly) -- the special/waypoint/lore ones:")
print(f"  {'name':34}{'dist_Sol_ly':>13}  coords(x,y,z)")
for r in con.execute(f"""
    SELECT name, sqrt(x*x+y*y+z*z) d, x, y, z FROM spansh_system
    WHERE NOT {PROC} AND NOT {DIGIT} AND sqrt(x*x+y*y+z*z) > 5000
    ORDER BY d DESC LIMIT 40
""").fetchall():
    print(f"  {str(r[0])[:32]:32s}{int(r[1]):>13,}  ({int(r[2]):,}, {int(r[3]):,}, {int(r[4]):,})")

print("\n### (2) curated mystery / restricted / historical POIs ###")
for r in con.execute("""
    SELECT type, count(*) c FROM edastro_point_of_interest
    WHERE type ILIKE '%myster%' OR type ILIKE '%restrict%' OR type ILIKE '%historic%'
    GROUP BY 1 ORDER BY 2 DESC
""").fetchall():
    print(f"  {str(r[0]):24s} {r[1]:>4}")

print("\n  mystery / restricted POIs (name @ system):")
for r in con.execute("""
    SELECT type, name, galMapSearch FROM edastro_point_of_interest
    WHERE type ILIKE '%myster%' OR type ILIKE '%restrict%'
    ORDER BY type, name
""").fetchall():
    print(f"  [{str(r[0])[:16]:16s}] {str(r[1])[:44]:44s} @ {r[2]}")

print("\n### Raxxla / Dark Wheel / Etalon / Thule / Guardian-lore text matches across ALL POIs ###")
hits = con.execute("""
    SELECT type, name, galMapSearch FROM edastro_point_of_interest
    WHERE lower(name||' '||coalesce(summary,'')||' '||coalesce(descriptionMardown,'')) SIMILAR TO
          '%(raxxla|dark wheel|etalon|thule|dynasty|formidine|oracle|generation ship)%'
    ORDER BY type LIMIT 40
""").fetchall()
for r in hits:
    print(f"  [{str(r[0])[:18]:18s}] {str(r[1])[:46]:46s} @ {r[2]}")
print(f"  ({len(hits)} lore-term matches)")
con.close()
