"""pgnames: translate Elite procedural system names <-> coordinates, anchored to
our 194.7M-system data (so it is self-validating and works for the realistic case
where a clue system's SECTOR has other uploaded systems even if the system itself
was never uploaded).

Build:   python scripts/pgnames.py build      # sector lookup + validation
Locate:  python scripts/pgnames.py locate "Praea Euq AB-C d1-23"
Near:    python scripts/pgnames.py near 100 -20 25900 50     # x y z radius_ly
"""
import duckdb, pathlib, sys, re

DB = pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"
NAME_RE = re.compile(r'^(?P<sector>.+?) (?P<l1>[A-Z])(?P<l2>[A-Z])-(?P<l3>[A-Z]) '
                     r'(?P<mc>[a-h])(?P<num>[0-9]+(?:-[0-9]+)?)$')

def con(readonly=True):
    c = duckdb.connect(str(DB), read_only=readonly)
    c.execute("SET memory_limit='7GB'"); c.execute("SET threads=8")
    return c

def parse(name):
    m = NAME_RE.match(name.strip())
    if not m: return None
    d = m.groupdict()
    num = d["num"]
    pre = num.split("-")[0] if "-" in num else "0"       # pre-dash = part of boxel address
    idx = num.split("-")[1] if "-" in num else num        # dense system index in boxel
    d["boxel_prefix"] = f'{d["sector"]} {d["l1"]}{d["l2"]}-{d["l3"]} {d["mc"]}{pre if "-" in num else ""}'
    d["boxel_key"] = f'{d["sector"]} {d["l1"]}{d["l2"]}-{d["l3"]} {d["mc"]}#{pre}'
    d["sys_index"] = int(idx)
    return d

def build():
    c = con(readonly=False)
    SECTOR = r"regexp_replace(name,' [A-Z][A-Z]-[A-Z] [a-h][0-9]+(-[0-9]+)?$','')"
    print("building sector_lookup (centroid per procedural sector)...", flush=True)
    c.execute(f"""
    CREATE OR REPLACE TABLE sector_lookup AS
    SELECT {SECTOR} AS sector, count(*) n, avg(x) cx, avg(y) cy, avg(z) cz
    FROM spansh_system WHERE regexp_matches(name,'[A-Z][A-Z]-[A-Z] [a-h][0-9]')
    GROUP BY 1
    """)
    n = c.execute("select count(*) from sector_lookup").fetchone()[0]
    print(f"  sectors: {n:,}")
    # validation: locate 5000 random known systems by their sector centroid; error should be < ~1109 ly (half sector diagonal)
    print("validating: sector-centroid error on 5000 random known systems...", flush=True)
    r = c.execute(f"""
      WITH s AS (SELECT name, x, y, z, {SECTOR} sector FROM spansh_system
                 WHERE regexp_matches(name,'[A-Z][A-Z]-[A-Z] [a-h][0-9]') USING SAMPLE 5000)
      SELECT median(sqrt(pow(s.x-l.cx,2)+pow(s.y-l.cy,2)+pow(s.z-l.cz,2))) med,
             quantile_cont(sqrt(pow(s.x-l.cx,2)+pow(s.y-l.cy,2)+pow(s.z-l.cz,2)),0.95) p95,
             max(sqrt(pow(s.x-l.cx,2)+pow(s.y-l.cy,2)+pow(s.z-l.cz,2))) mx
      FROM s JOIN sector_lookup l USING(sector)
    """).fetchone()
    print(f"  sector-level locate error (ly): median={r[0]:.0f}  p95={r[1]:.0f}  max={r[2]:.0f}")
    print("  (a sector is 1280 ly; corner-to-centre <=1109 ly, so this bounds precision)")
    c.close()

def locate(name):
    c = con(); p = parse(name)
    if not p:
        row = c.execute("SELECT name,x,y,z FROM spansh_system WHERE name = ? LIMIT 1", [name]).fetchone()
        if row: print(f"  '{name}' is a NAMED system present in data at ({row[1]:.0f}, {row[2]:.0f}, {row[3]:.0f})")
        else:   print(f"  '{name}' is not procedural and not found in data.")
        c.close(); return
    print(f"  parsed: sector='{p['sector']}'  boxel={p['l1']}{p['l2']}-{p['l3']} {p['mc']}  sys_index={p['sys_index']}")
    exact = c.execute("SELECT x,y,z FROM spansh_system WHERE name = ? LIMIT 1", [name]).fetchone()
    print(f"  exact system in data: {'YES @ (%.0f, %.0f, %.0f)'%exact if exact else 'NO (absent -- consistent with a pre-automation visit)'}")
    # boxel-mates (same sector+letters+mc+pre-dash) pin location tightly
    pref = p["boxel_prefix"]
    bm = c.execute("SELECT count(*), avg(x), avg(y), avg(z) FROM spansh_system WHERE name LIKE ? || '%'", [pref]).fetchone()
    if bm[0] and bm[0] > (1 if exact else 0):
        print(f"  boxel neighbours in data: {bm[0]:,}  -> boxel centre ~({bm[1]:.0f}, {bm[2]:.0f}, {bm[3]:.0f}) (+/- boxel size)")
    sec = c.execute("SELECT n,cx,cy,cz FROM sector_lookup WHERE sector = ? LIMIT 1", [p["sector"]]).fetchone()
    if sec:
        print(f"  sector '{p['sector']}' centre ~({sec[1]:.0f}, {sec[2]:.0f}, {sec[3]:.0f}) from {sec[0]:,} known systems (+/- ~640 ly)")
    else:
        print(f"  sector '{p['sector']}' has NO uploaded systems -> cannot locate from data (needs generative pgnames).")
    c.close()

def near(x, y, z, radius):
    c = con()
    print(f"  known systems within {radius} ly of ({x}, {y}, {z}):")
    for r in c.execute("""
        SELECT name, sqrt(pow(x-?,2)+pow(y-?,2)+pow(z-?,2)) d, x, y, z FROM spansh_system
        WHERE abs(x-?)<? AND abs(y-?)<? AND abs(z-?)<?
          AND sqrt(pow(x-?,2)+pow(y-?,2)+pow(z-?,2)) <= ?
        ORDER BY d LIMIT 40""",
        [x,y,z, x,radius,y,radius,z,radius, x,y,z,radius]).fetchall():
        print(f"    {str(r[0])[:34]:34s} {r[1]:>8.1f} ly  ({r[3]:.0f}, {r[4]:.0f}, {r[5]:.0f})")
    c.close()

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build": build()
    elif cmd == "locate": locate(sys.argv[2])
    elif cmd == "near": near(float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]))
    else: print(__doc__)
