"""Tier-1 rare stars: local de-biased rate (kNN within mass code) + validation +
near-Sol / fringe sector rankings. Reuses the validated BH/WR method.
"""
import duckdb, pathlib, numpy as np
from scipy.spatial import cKDTree
np.random.seed(11)
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")

bx = con.execute("SELECT * FROM star_boxels").df()
bx["well"] = (bx.scanned>=10) & (bx.scanned>=0.8*bx["pop"])
TARGETS = [("n_neutron","Neutron star"),("n_wd","White dwarf"),("n_herbig","Herbig Ae/Be"),
           ("n_otype","O-type star"),("n_supergiant","Supergiant")]
MCS = ["e","f","g","h"]

def local_rate(cand, num_col, anchors, k=12, k0=10.0):
    """kNN pooled rate WITHIN each mass code, shrunk toward the per-mass-code
    global well-sampled mean (empirical Bayes). Shrinking toward the mass-code
    mean (not a flat prior) avoids a spurious floor where the target is ~absent
    (e.g. O-type in mass code e -> mean 0 -> rate 0)."""
    out = np.zeros(len(cand))
    for mc in MCS:
        cm = cand.mass_code.values==mc; anc = anchors[anchors.mass_code.values==mc]
        if cm.sum()==0: continue
        mu = anc[num_col].sum()/anc["scanned"].sum() if anc["scanned"].sum()>0 else 0.0
        if len(anc) >= 30:
            tree = cKDTree(anc[["x","y","z"]].values)
            d,idx = tree.query(cand[cm][["x","y","z"]].values, k=min(k,len(anc)))
            if idx.ndim==1: idx=idx[:,None]
            num = anc[num_col].values[idx].sum(1); den = anc["scanned"].values[idx].sum(1)
            out[np.where(cm)] = (num + k0*mu)/(den + k0)
        else:
            out[np.where(cm)] = mu
    return out

def validate(num_col, label):
    w = bx[bx.well & (bx.scanned>0)].copy()
    te = np.random.rand(len(w))<0.20
    tr, tst = w[~te], w[te]
    pred = local_rate(tst, num_col, tr)
    actual = (tst[num_col]/tst.scanned).values
    base = tr[num_col].sum()/tr.scanned.sum()
    wt = tst.scanned.values
    mae_l = np.average(np.abs(pred-actual),weights=wt); mae_b=np.average(np.abs(base-actual),weights=wt)
    return mae_l, mae_b

# compute de-biased expected per boxel for every target
well = bx[bx.well]
for num_col,label in TARGETS:
    bx["rate_"+num_col] = local_rate(bx, num_col, well)
    bx["exp_"+num_col]  = bx["missing"] * bx["rate_"+num_col]

# persist sector-level table
agg = {"dist_sol":("dist_sol","mean"),"plane_r":("plane_r","mean"),
       "x":("x","mean"),"y":("y","mean"),"z":("z","mean"),"theorised":("missing","sum")}
for num_col,_ in TARGETS:
    agg["found_"+num_col]=(num_col,"sum"); agg["exp_"+num_col]=("exp_"+num_col,"sum")
g = bx.groupby("sector").agg(**agg).reset_index()
con.register("g_df", g); con.execute("CREATE OR REPLACE TABLE rare_star_sectors AS SELECT * FROM g_df"); con.unregister("g_df")

for num_col,label in TARGETS:
    ml, mb = validate(num_col, label)
    print(f"\n########## {label.upper()}  (validation: local MAE={100*ml:.2f}pp vs baseline {100*mb:.2f}pp"
          f" -> {mb/ml:.1f}x) ##########")
    ecol="exp_"+num_col; fcol="found_"+num_col
    near = g[(g[ecol]>=1.5) & (g.theorised>=15)].sort_values("dist_sol").head(6)
    print(f"  closest-to-Sol sectors (exp>=1.5, theo>=15):")
    print(f"    {'sector':18}{'dist_Sol':>9}{'plane_r':>8}{'theo':>6}{'found':>6}{'exp':>7}")
    for _,r in near.iterrows():
        print(f"    {str(r['sector'])[:16]:16s}{int(r.dist_sol):>9,}{int(r.plane_r):>8,}{int(r.theorised):>6,}{int(r[fcol]):>6,}{r[ecol]:>7.1f}")
    fr = g[(g.plane_r>30000)&(g.theorised>=15)].sort_values(ecol,ascending=False).head(6)
    print(f"  fringe sectors (plane_r>30kly) by expected:")
    for _,r in fr.iterrows():
        print(f"    {str(r['sector'])[:16]:16s}{int(r.dist_sol):>9,}{int(r.plane_r):>8,}{int(r.theorised):>6,}{int(r[fcol]):>6,}{r[ecol]:>7.1f}")
con.close()
print("\nDONE_03N")
