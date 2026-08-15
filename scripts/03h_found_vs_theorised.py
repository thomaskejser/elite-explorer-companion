"""Found (confirmed, scanned) vs theorised BH/WR per fringe sector.

found_*  = hard count of confirmed objects in SCANNED systems (spansh scans).
exp_*    = model-expected undiscovered among enumerated theorised systems.
Lets us see what fraction is already discovered vs predicted remaining.
"""
import duckdb, pathlib
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")

SECTOR = r"regexp_replace(name,' [A-Z]{1,2}-[A-Z] [a-h][0-9]+(-[0-9]+)?$','')"

con.execute(f"""
CREATE OR REPLACE TEMP TABLE found_fringe AS
SELECT {SECTOR} AS sector,
       count(*) AS found_systems, sum(has_bh) AS found_bh, sum(has_wr) AS found_wr
FROM sys_feat
WHERE is_scanned AND mass_code IN ('f','g','h') AND plane_r > 30000
GROUP BY 1
""")
con.execute("""
CREATE OR REPLACE TEMP TABLE theo_fringe AS
SELECT sector, round(avg(plane_r)) plane_r, round(avg(x)) x, round(avg(y)) y, round(avg(z)) z,
       sum(missing) theo_systems, sum(exp_bh) exp_bh, sum(exp_wr) exp_wr
FROM theorised_boxels WHERE plane_r > 30000 GROUP BY 1
""")

print("=== WHOLE FRINGE (plane_r > 30 kly): found vs theorised ===")
r = con.execute("""
  SELECT sum(coalesce(f.found_systems,0)) fs, sum(coalesce(f.found_bh,0)) fbh, sum(coalesce(f.found_wr,0)) fwr,
         sum(coalesce(t.theo_systems,0)) ts, sum(coalesce(t.exp_bh,0)) ebh, sum(coalesce(t.exp_wr,0)) ewr
  FROM theo_fringe t FULL JOIN found_fringe f USING(sector)
""").fetchone()
fs,fbh,fwr,ts,ebh,ewr = r
print(f"  systems : found(scanned)={int(fs):,}   theorised(enumerable)={int(ts):,}   "
      f"-> theorised = {100*ts/(fs+ts):.1f}% of (found+theorised)")
print(f"  black holes: found={int(fbh):,}   theorised(exp)={ebh:,.0f}   "
      f"-> {100*ebh/(fbh+ebh):.1f}% still to find (of found+exp)")
print(f"  wolf-rayet : found={int(fwr):,}   theorised(exp)={ewr:,.0f}   "
      f"-> {100*ewr/(fwr+ewr):.1f}% still to find")
print("  NOTE: theorised is a FLOOR (only boxels with >=1 observed system are enumerable).")

def table(title, order):
    print(f"\n=== {title} ===")
    print(f"  {'sector':22}{'found_sys':>10}{'found_BH':>9}{'found_WR':>9}"
          f"{'theo_sys':>9}{'exp_BH':>8}{'exp_WR':>7}{'plane_r':>9}")
    for r in con.execute(f"""
        SELECT t.sector, coalesce(f.found_systems,0) fs, coalesce(f.found_bh,0) fbh,
               coalesce(f.found_wr,0) fwr, t.theo_systems, round(t.exp_bh,1), round(t.exp_wr,1),
               t.plane_r
        FROM theo_fringe t LEFT JOIN found_fringe f USING(sector)
        WHERE t.theo_systems >= 10 ORDER BY {order} DESC LIMIT 18
    """).fetchall():
        print(f"  {str(r[0])[:20]:20s}{r[1]:>10,}{r[2]:>9,}{r[3]:>9,}"
              f"{int(r[4]):>9,}{r[5]:>8}{r[6]:>7}{int(r[7]):>9,}")

table("TOP FRINGE SECTORS by expected undiscovered BLACK HOLES", "t.exp_bh")
table("TOP FRINGE SECTORS by expected undiscovered WOLF-RAYET", "t.exp_wr")
con.close()
