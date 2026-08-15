"""Re-attach model scores to the CORRECTED theorised_boxels (post-03s).

03s rebuilt theorised_boxels from internal gaps only and, in doing so, dropped the
columns 03g/03j consume (pop, observed already kept as `observed`; but p_bh, p_wr,
exp_bh, exp_wr are gone).  This refits the same HistGradientBoosting models 03f
used and writes the biased ("naive") per-boxel scores back on, so the downstream
naive-vs-de-biased comparison is reproduced faithfully against corrected `missing`.

Nothing here changes the corrected gap enumeration -- only adds score columns.
"""
import duckdb, pathlib, numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = pathlib.Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"))
con.execute("SET memory_limit='6GB'"); con.execute("SET threads=8")
con.execute("SET preserve_insertion_order=false")
MC = {'e': 0, 'f': 1, 'g': 2, 'h': 3}
FEATS = ["mc", "r_sgra", "plane_r", "height", "x", "y", "z"]

cols = [c[0] for c in con.execute("DESCRIBE theorised_boxels").fetchall()]
if "exp_bh" in cols:
    print("theorised_boxels already scored; rebuilding scores anyway.")

print("1/4 loading training set (scanned e/f/g/h)...", flush=True)
tr = con.execute("""SELECT mass_code,x,y,z,r_sgra,plane_r,height,has_bh,has_wr
                    FROM sys_feat WHERE mass_code IN ('e','f','g','h') AND is_scanned""").df()
tr["mc"] = tr["mass_code"].map(MC).astype("float32")
print(f"    train rows: {len(tr):,}", flush=True)

print("2/4 fitting BH + WR models...", flush=True)
bh = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, min_samples_leaf=200
     ).fit(tr[FEATS].values.astype("float32"), tr["has_bh"].values.astype(int))
h = tr[tr.mass_code == 'h']
wr = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, min_samples_leaf=200
     ).fit(h[FEATS].values.astype("float32"), h["has_wr"].values.astype(int))
del tr, h

print("3/4 scoring the 16.7k corrected boxels...", flush=True)
# `height` (= avg abs(y), as 03f used it) was not persisted by 03s -> recompute it
# per boxel from sys_feat rather than approximating with abs(avg(y)).
KB = r"regexp_replace(name,'[0-9]+(-[0-9]+)?$','')"
TK = r"regexp_extract(name,'([0-9]+(-[0-9]+)?)$',1)"
BX = f"CASE WHEN {TK} LIKE '%-%' THEN {KB}||'#'||split_part({TK},'-',1) ELSE {KB} END"
con.execute(f"""
CREATE OR REPLACE TEMP TABLE _h AS
SELECT {BX} AS boxel, avg(height) AS height
FROM sys_feat WHERE mass_code IN ('f','g','h') AND {TK} <> '' GROUP BY 1
""")
bx = con.execute("""SELECT b.boxel, b.mass_code, b.sector, b.x, b.y, b.z, b.plane_r, b.r_sgra,
                           b.observed, b.min_idx, b.max_idx, b.missing,
                           coalesce(h.height, abs(b.y)) AS height
                    FROM theorised_boxels b LEFT JOIN _h h USING(boxel)""").df()
bx["mc"] = bx["mass_code"].map(MC).astype("float32")
X = bx[FEATS].values.astype("float32")
bx["p_bh"] = bh.predict_proba(X)[:, 1]
bx["p_wr"] = np.where(bx.mass_code.values == 'h', wr.predict_proba(X)[:, 1], 0.0)
bx["exp_bh"] = bx["missing"] * bx["p_bh"]
bx["exp_wr"] = bx["missing"] * bx["p_wr"]

keep = ["boxel", "mass_code", "sector", "x", "y", "z", "plane_r", "r_sgra",
        "observed", "min_idx", "max_idx", "missing", "p_bh", "p_wr", "exp_bh", "exp_wr"]
con.register("bxdf", bx[keep])
con.execute("CREATE OR REPLACE TABLE theorised_boxels AS SELECT * FROM bxdf")
con.unregister("bxdf")

print("4/4 report...", flush=True)
r = con.execute("""SELECT count(*), sum(missing), round(sum(exp_bh),1), round(sum(exp_wr),1)
                   FROM theorised_boxels""").fetchone()
print(f"    boxels={r[0]:,}  theorised={int(r[1]):,}  naive E[BH]={r[2]:,}  naive E[WR]={r[3]:,}")
for row in con.execute("""SELECT mass_code, count(*) b, sum(missing) m,
                                 round(sum(exp_bh),1), round(sum(exp_wr),1)
                          FROM theorised_boxels GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"    mc={row[0]}  boxels={row[1]:>7,}  theorised={int(row[2]):>7,}"
          f"  E[BH]={row[3]:>8,}  E[WR]={row[4]:>8,}")
con.close()
print("\nDONE_03T", flush=True)
