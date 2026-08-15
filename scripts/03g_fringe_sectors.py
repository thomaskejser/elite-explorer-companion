"""Rank FRINGE sectors (outer galactic disk) likely to hold undiscovered BH/WR.

Fringe metric = plane_r (galactocentric disk radius; Sol ~= 25.9 kly, rim ~50 kly).
Core is excluded. Uses the theorised_boxels layer (per-boxel expected undiscovered
counts). Rankings are the trustworthy output; absolute counts are upper-ish.
"""
import duckdb, pathlib
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='6GB'"); con.execute("SET threads=8")

print("=== signal by galactocentric radius band (all theorised f/g/h) ===")
print(f"{'plane_r band':>16}{'boxels':>10}{'theorised':>13}{'E[BH]':>12}{'E[WR]':>10}")
for r in con.execute("""
    SELECT CASE WHEN plane_r<10000 THEN '0-10k (core)'
                WHEN plane_r<20000 THEN '10-20k'
                WHEN plane_r<30000 THEN '20-30k'
                WHEN plane_r<40000 THEN '30-40k'
                WHEN plane_r<50000 THEN '40-50k'
                ELSE '50k+ (rim)' END AS band,
           min(plane_r) ord, count(*) boxels, sum(missing) theo,
           round(sum(exp_bh)) ebh, round(sum(exp_wr)) ewr
    FROM theorised_boxels GROUP BY 1 ORDER BY ord
""").fetchall():
    print(f"{r[0]:>16}{r[2]:>10,}{int(r[3]):>13,}{int(r[4]):>12,}{int(r[5]):>10,}")

FRINGE = "plane_r > 30000"   # outer disk, well beyond Sol's ~26 kly radius

def sectors(title, order_col, pcol, where=""):
    print(f"\n=== {title} (fringe: {FRINGE}) ===")
    print(f"  {'sector':26}{'E[BH]':>8}{'E[WR]':>7}{'theorised':>10}{'plane_r':>9}{'best_p':>8}  location(x,y,z)")
    q = f"""
        SELECT sector,
               round(sum(exp_bh),1) ebh, round(sum(exp_wr),1) ewr,
               sum(missing) theo, round(avg(plane_r)) pr, round(max({pcol}),3) bestp,
               round(avg(x)) x, round(avg(y)) y, round(avg(z)) z
        FROM theorised_boxels
        WHERE {FRINGE} {where}
        GROUP BY sector HAVING sum(missing) >= 10
        ORDER BY {order_col} DESC LIMIT 20
    """
    for r in con.execute(q).fetchall():
        print(f"  {str(r[0])[:24]:24s}{r[1]:>8}{r[2]:>7}{int(r[3]):>10,}{int(r[4]):>9,}{r[5]:>8}"
              f"  ({int(r[6]):,}, {int(r[7]):,}, {int(r[8]):,})")

sectors("TOP FRINGE SECTORS for undiscovered BLACK HOLES", "sum(exp_bh)", "p_bh")
sectors("TOP FRINGE SECTORS for undiscovered WOLF-RAYET", "sum(exp_wr)", "p_wr", "AND mass_code='h'")
con.close()
