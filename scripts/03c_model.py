"""Predict undiscovered black holes and Wolf-Rayet stars.

Coverage-aware: trained ONLY on scanned systems (positives + reliable negatives),
using features that are ALSO known for unscanned candidates -- mass_code (from
the procedural name; a hard Stellar Forge gate) and galactic position. Scored
onto the unscanned pool to rank where undiscovered BH/WR most likely sit.

Spatial (GroupKFold by galactic block) CV, so we measure extrapolation to
unseen regions rather than memorised exploration routes. Predicted scores are a
RANKING: absolute rates are biased upward because explorers preferentially scan
the bright massive primary, so scanned systems over-represent BH/WR within a
cell. We report this rather than pretend calibration.
"""
import duckdb, pathlib, numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import GroupKFold
from sklearn.metrics import average_precision_score

ROOT = pathlib.Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")

MC = {'e':0,'f':1,'g':2,'h':3}
FEATS = ["mc","r_sgra","plane_r","height","x","y","z"]

def load(where):
    df = con.execute(f"""
        SELECT system_id64, name, mass_code, x, y, z, r_sgra, plane_r, height,
               has_bh, has_wr
        FROM sys_feat WHERE mass_code IN ('e','f','g','h') AND {where}
    """).df()
    df["mc"] = df["mass_code"].map(MC).astype("float32")
    return df

print("loading scanned e/f/g/h (training)...", flush=True)
tr = load("is_scanned")
print(f"  train rows: {len(tr):,}  BH+={tr.has_bh.sum():,}  WR+={tr.has_wr.sum():,}", flush=True)

def spatial_block(df):
    # ~2.5 kly cubic blocks -> group id; keeps nearby systems in the same fold
    return (np.floor(df.x/2500).astype(int).astype(str) + "_" +
            np.floor(df.z/2500).astype(int).astype(str)).values

def cv_report(df, label, mask=None):
    d = df if mask is None else df[mask]
    X = d[FEATS].values.astype("float32"); y = d[label].values.astype(int)
    groups = spatial_block(d)
    base = y.mean()
    aps = []
    for tri, tei in GroupKFold(n_splits=5).split(X, y, groups):
        m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1,
                                           max_leaf_nodes=31, min_samples_leaf=200)
        m.fit(X[tri], y[tri])
        p = m.predict_proba(X[tei])[:,1]
        aps.append(average_precision_score(y[tei], p))
    print(f"  [{label}] base rate={base:.4f}  spatial-CV PR-AUC={np.mean(aps):.4f}"
          f" (lift x{np.mean(aps)/base:.1f})  folds={[f'{a:.3f}' for a in aps]}", flush=True)

print("\nspatial cross-validation (extrapolation to unseen regions):", flush=True)
cv_report(tr, "has_bh")
cv_report(tr, "has_wr", mask=(tr.mass_code=='h').values)   # WR only exist in h

# ---- fit final models on all scanned, score unscanned candidates ----
def fit_full(df, label, mask=None):
    d = df if mask is None else df[mask]
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08,
                                       max_leaf_nodes=31, min_samples_leaf=200)
    m.fit(d[FEATS].values.astype("float32"), d[label].values.astype(int))
    return m

print("\nfitting final models + scoring unscanned candidates...", flush=True)
bh_model = fit_full(tr, "has_bh")
wr_model = fit_full(tr, "has_wr", mask=(tr.mass_code=='h').values)

cand = load("NOT is_scanned")
cand["p_bh"] = bh_model.predict_proba(cand[FEATS].values.astype("float32"))[:,1]
wr_mask = (cand.mass_code=='h').values
cand["p_wr"] = 0.0
if wr_mask.any():
    cand.loc[wr_mask,"p_wr"] = wr_model.predict_proba(cand[wr_mask][FEATS].values.astype("float32"))[:,1]
print(f"  scored {len(cand):,} unscanned candidates", flush=True)

# persist ranked candidates
con.register("cand_df", cand[["system_id64","name","mass_code","x","y","z","r_sgra","p_bh","p_wr"]])
con.execute("CREATE OR REPLACE TABLE bhwr_candidates AS SELECT * FROM cand_df")
con.unregister("cand_df")

def top(title, col, extra=""):
    print(f"\n=== {title} ===", flush=True)
    for r in con.execute(f"""SELECT name, mass_code, round(r_sgra) r_sgra_ly, round({col},3) p
                             FROM bhwr_candidates {extra} ORDER BY {col} DESC LIMIT 15""").fetchall():
        print(f"  {str(r[0])[:32]:32s}  mc={r[1]}  r_core={int(r[2]):>7,}ly  p={r[3]}", flush=True)

top("Top undiscovered BLACK HOLE candidates", "p_bh")
top("Top undiscovered WOLF-RAYET candidates", "p_wr", "WHERE mass_code='h'")

print("\n=== Expected undiscovered counts (sum of scores; ranking-grade, biased high) ===", flush=True)
for r in con.execute("""
    SELECT mass_code, count(*) candidates,
           round(sum(p_bh)) exp_bh, round(sum(p_wr)) exp_wr
    FROM bhwr_candidates GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  mc={r[0]}  candidates={r[1]:>10,}  E[BH]={int(r[2]):>8,}  E[WR]={int(r[3]):>7,}", flush=True)
con.close()
print("\nDONE_03C", flush=True)
