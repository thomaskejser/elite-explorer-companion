"""Predict undiscovered black holes along the Reorte->Riedquat corridor (the Raxxla
clue line, extended outward toward the Formidine Rift), and find where to start.

Corridor = points within PERP ly of the line through Riedquat with direction
Reorte->Riedquat, projected outward (t>0) toward the rim. BH-capable systems only
(mass code e/f/g/h). De-biased BH rate pi(galactocentric radius) from validated
well-sampled curve (03j). Undiscovered = theorised (never-in-DB) systems * pi.
"""
import duckdb, pathlib, numpy as np
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")

R = con.execute("SELECT x,y,z FROM spansh_system WHERE name='Reorte'").fetchone()
Q = con.execute("SELECT x,y,z FROM spansh_system WHERE name='Riedquat'").fetchone()
v = np.array(Q)-np.array(R); u = v/np.linalg.norm(v)
qx,qy,qz = Q; ux,uy,uz = u
PERP = 2000.0   # corridor half-width (ly); clue tolerance is tighter, this is a search band
print(f"Riedquat={tuple(round(c,1) for c in Q)}  direction Reorte->Riedquat={tuple(round(c,3) for c in u)}  corridor half-width={PERP:.0f}ly")

# de-biased BH rate pi(galactocentric radius kly) -- pooled well-sampled curve (03j)
xk = np.array([1.25,3.75,6.25,8.75,11.25,13.75,16.25,18.75,21.25,23.75,26.25,31.25])
pk = np.array([0.117,0.49,0.55,0.49,0.41,0.40,0.27,0.0485,0.037,0.051,0.062,0.093])
def pi_bh(plane_r_ly):
    return np.interp(plane_r_ly/1000.0, xk, pk, left=pk[0], right=pk[-1])

# corridor projection/perp expressions
T   = f"(({{X}}-{qx})*{ux} + ({{Y}}-{qy})*{uy} + ({{Z}}-{qz})*{uz})"
def perp_sql(X,Y,Z):
    t=f"(({X}-{qx})*{ux}+({Y}-{qy})*{uy}+({Z}-{qz})*{uz})"
    return f"sqrt(pow(({X}-{qx})-{t}*{ux},2)+pow(({Y}-{qy})-{t}*{uy},2)+pow(({Z}-{qz})-{t}*{uz},2))", t

# --- FOUND black holes + scanned/known in the corridor (from sys_feat) ---
perp,t = perp_sql("x","y","z")
found = con.execute(f"""
  SELECT count(*) FILTER (WHERE is_scanned) scanned,
         sum(has_bh) found_bh,
         count(*) in_db,
         count(*) FILTER (WHERE NOT is_scanned) in_db_unscanned
  FROM sys_feat
  WHERE mass_code IN ('e','f','g','h') AND {t} > 0 AND {perp} < {PERP}
""").fetchone()
print(f"\ncorridor (e/f/g/h, outward): in_db={found[2]:,}  scanned={found[0]:,}  "
      f"FOUND black holes={int(found[1] or 0):,}  in-db-unscanned={found[3]:,}")

# --- THEORISED (predicted, never-in-DB) systems in the corridor + expected BH ---
perp2,t2 = perp_sql("x","y","z")
th = con.execute(f"""
  SELECT x,y,z, sqrt(pow(x-25.2,2)+pow(z-25900,2)) plane_r, {t2} tproj
  FROM theorised_system
  WHERE {t2} > 0 AND {perp2} < {PERP}
""").df()
th["pi"] = pi_bh(th.plane_r.values)
exp_bh = th["pi"].sum()
print(f"theorised (predicted) f/g/h systems in corridor: {len(th):,}")
print(f"==> EXPECTED UNDISCOVERED black holes in corridor (de-biased): {exp_bh:,.0f}")
print(f"    (found {int(found[1] or 0):,} already; so ~{100*exp_bh/(exp_bh+(found[1] or 0)+1e-9):.0f}% still to find)")

# --- WHERE TO START: segment by distance along the line from Riedquat ---
th["seg"] = (th.tproj//5000*5).astype(int)
print("\nby distance OUT along the RR line from Riedquat (where to start = highest expected, nearest):")
print(f"  {'segment_kly':>12}{'plane_r_kly':>12}{'theorised':>11}{'exp_BH':>9}")
g = th.groupby("seg").agg(pr=("plane_r","mean"), n=("x","size"), e=("pi","sum")).reset_index().sort_values("seg")
for _,r in g.iterrows():
    print(f"  {int(r.seg):>6}-{int(r.seg)+5:<5}{r.pr/1000:>12.1f}{int(r.n):>11,}{r.e:>9.1f}")

# best individual starting boxels (nearest 3 segments, highest local expected)
near = th[th.tproj < 15000].copy()
near["cell"] = (near.x//640).astype(int).astype(str)+"_"+(near.y//640).astype(int).astype(str)+"_"+(near.z//640).astype(int).astype(str)
top = near.groupby("cell").agg(x=("x","mean"),y=("y","mean"),z=("z","mean"),
        pr=("plane_r","mean"),n=("x","size"),e=("pi","sum"),t=("tproj","mean")).reset_index()
top = top.sort_values("e", ascending=False).head(10)
print("\nbest STARTING boxel-cells (t<15kly out, ranked by expected BH):")
print(f"  {'along_line_ly':>13}{'plane_r':>9}{'theo':>6}{'exp_BH':>8}  coords(x,y,z)")
for _,r in top.iterrows():
    print(f"  {int(r.t):>13,}{int(r.pr):>9,}{int(r.n):>6}{r.e:>8.2f}  ({int(r.x):,},{int(r.y):,},{int(r.z):,})")
con.close()
