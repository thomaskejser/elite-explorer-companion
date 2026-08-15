"""Local de-biased rate (kNN from fully-sampled boxels) -> validate -> rank the
best sectors to explore, preferring proximity to Sol (0,0,0).

Why local: BH rate has directional structure, so a radius-only curve fails
cross-region (shown in 03k). A candidate boxel's true rate is best estimated
from the nearest FULLY-SAMPLED (unbiased) boxels, which captures direction.
Reliable where fully-sampled anchors are dense (near Sol / explored space);
uncertain in the deep fringe (few anchors) -> we report anchor distance as a
confidence signal.
"""
import duckdb, pathlib, numpy as np
from scipy.spatial import cKDTree
np.random.seed(7)
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")
KB=r"regexp_replace(name,'[0-9]+(-[0-9]+)?$','')"; TK=r"regexp_extract(name,'([0-9]+(-[0-9]+)?)$',1)"
BX=f"CASE WHEN {TK} LIKE '%-%' THEN {KB}||'#'||split_part({TK},'-',1) ELSE {KB} END"
IX=f"CASE WHEN {TK} LIKE '%-%' THEN CAST(split_part({TK},'-',2) AS BIGINT) ELSE CAST({TK} AS BIGINT) END"

df = con.execute(f"""
WITH b AS (
  SELECT {BX} boxel, mass_code, avg(x) x, avg(y) y, avg(z) z, avg(plane_r) plane_r,
         max({IX})+1 pop, count(*) FILTER (WHERE is_scanned) scanned,
         sum(has_bh) FILTER (WHERE is_scanned) bh, sum(has_wr) FILTER (WHERE is_scanned) wr
  FROM sys_feat WHERE mass_code IN ('f','g','h') AND {TK}<>'' GROUP BY 1,2)
SELECT b.*, t.sector, t.missing FROM b JOIN theorised_boxels t ON b.boxel=t.boxel
""").df()
df["well"] = (df.scanned>=10) & (df.scanned>=0.8*df["pop"])
df["dist_sol"] = np.sqrt(df.x**2 + df.y**2 + df.z**2)

def knn_rate(anchors, pts, num_col, den_col, k=12, a=2.0, b=8.0):
    tree = cKDTree(anchors[["x","y","z"]].values)
    d, idx = tree.query(pts[["x","y","z"]].values, k=min(k, len(anchors)))
    if idx.ndim == 1: idx = idx[:,None]; d = d[:,None]
    num = anchors[num_col].values[idx].sum(1); den = anchors[den_col].values[idx].sum(1)
    return (num + a) / (den + b), d[:,0]

# ---------- validation: random 20% hold-out of fully-sampled boxels ----------
def validate(anchors_all, num, label):
    a = anchors_all[anchors_all.scanned>0].copy()
    te = np.random.rand(len(a)) < 0.20
    train, test = a[~te], a[te]
    pred, _ = knn_rate(train, test, num, "scanned")
    actual = (test[num]/test.scanned).values
    naive_global = train[num].sum()/train.scanned.sum()      # single-number baseline
    w = test.scanned.values
    mae_local = np.average(np.abs(pred-actual), weights=w)
    mae_naive = np.average(np.abs(naive_global-actual), weights=w)
    print(f"  [{label}] holdout weighted MAE:  local-kNN={100*mae_local:.2f}pp  "
          f"global-mean baseline={100*mae_naive:.2f}pp  -> local {mae_naive/mae_local:.1f}x better")

print("=== validation: predict held-out fully-sampled boxels' true rate ===")
validate(df[df.well], "bh", "BH  (f/g/h)")
validate(df[df.well & (df.mass_code=='h')], "wr", "WR  (h)")

# ---------- apply local de-biased rate to ALL candidate boxels ----------
wbh = df[df.well]
wwr = df[df.well & (df.mass_code=='h')]
df["rate_bh"], df["anchor_dist_bh"] = knn_rate(wbh, df, "bh", "scanned")
rate_wr, adist_wr = knn_rate(wwr, df, "wr", "scanned")
df["rate_wr"] = np.where(df.mass_code=='h', rate_wr, 0.0)
df["exp_bh"] = df.missing * df.rate_bh
df["exp_wr"] = df.missing * df.rate_wr

# ---------- aggregate to sector, rank closest-to-Sol among worthwhile ----------
g = df.groupby("sector").agg(
    dist_sol=("dist_sol","mean"), plane_r=("plane_r","mean"),
    x=("x","mean"), y=("y","mean"), z=("z","mean"),
    theorised=("missing","sum"), found_bh=("bh","sum"), found_wr=("wr","sum"),
    exp_bh=("exp_bh","sum"), exp_wr=("exp_wr","sum"),
    anchor_dist=("anchor_dist_bh","mean")).reset_index()
g["exp_total"] = g.exp_bh + g.exp_wr

con.register("g_df", g)
con.execute("CREATE OR REPLACE TABLE explore_sectors AS SELECT * FROM g_df")
con.unregister("g_df")

WORTH = g[(g.exp_total >= 3) & (g.theorised >= 15)].sort_values("dist_sol").head(30)
print(f"\n=== BEST SECTORS TO EXPLORE (closest to Sol first; exp finds>=3, theorised>=15) ===")
print(f"  {'sector':20}{'dist_Sol_ly':>12}{'plane_r':>9}{'theo':>6}{'foundBH':>8}{'foundWR':>8}"
      f"{'expBH':>7}{'expWR':>7}  coords(x,y,z)")
for _,r in WORTH.iterrows():
    print(f"  {str(r['sector'])[:18]:18s}{int(r.dist_sol):>12,}{int(r.plane_r):>9,}{int(r.theorised):>6,}"
          f"{int(r.found_bh):>8,}{int(r.found_wr):>8,}{r.exp_bh:>7.1f}{r.exp_wr:>7.1f}"
          f"  ({int(r.x):,},{int(r.y):,},{int(r.z):,})")
con.close()
