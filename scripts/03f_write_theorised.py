"""Write theorised (Stellar-Forge-implied, not-in-DB) f/g/h systems to DuckDB.

CORRECTED boxel model: the real boxel = (sector+letters+masscode [+ pre-dash
number]); the post-dash / plain number is the DENSE 0..K-1 system index within
that boxel (validated: h boxels ~99% dense). Every missing index below the max
observed index is therefore a real, not-yet-catalogued system -> a valid lower
bound. We store boxel + index + boxel-centroid coords (<=1280 ly) and model
scores. We do NOT fabricate exact catalogue name strings (the index->name
formatting for arbitrary indices is not reproduced), so the identity is
(boxel_key, boxel_index), which is exact.
"""
import duckdb, pathlib, numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = pathlib.Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")
con.execute("SET preserve_insertion_order=false")
MC = {'e':0,'f':1,'g':2,'h':3}; FEATS = ["mc","r_sgra","plane_r","height","x","y","z"]

# boxel/index expressions (reused for agg + anti-join so they match exactly)
KBASE = r"regexp_replace(name,'[0-9]+(-[0-9]+)?$','')"
TOK   = r"regexp_extract(name,'([0-9]+(-[0-9]+)?)$',1)"
BOXEL = f"CASE WHEN {TOK} LIKE '%-%' THEN {KBASE}||'#'||split_part({TOK},'-',1) ELSE {KBASE} END"
IDX   = f"CASE WHEN {TOK} LIKE '%-%' THEN CAST(split_part({TOK},'-',2) AS BIGINT) ELSE CAST({TOK} AS BIGINT) END"

print("1/5 refitting models...", flush=True)
tr = con.execute("""SELECT mass_code,x,y,z,r_sgra,plane_r,height,has_bh,has_wr
                    FROM sys_feat WHERE mass_code IN ('e','f','g','h') AND is_scanned""").df()
tr["mc"] = tr["mass_code"].map(MC).astype("float32")
bh = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, min_samples_leaf=200
     ).fit(tr[FEATS].values.astype("float32"), tr["has_bh"].values.astype(int))
h = tr[tr.mass_code=='h']
wr = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, min_samples_leaf=200
     ).fit(h[FEATS].values.astype("float32"), h["has_wr"].values.astype(int))

print("2/5 aggregating correct boxels...", flush=True)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE _bx AS
SELECT {BOXEL} AS boxel, mass_code,
       regexp_replace({KBASE},' [A-Z]{{1,2}}-[A-Z] [a-h]$','') AS sector,
       avg(x) x, avg(y) y, avg(z) z, avg(r_sgra) r_sgra, avg(plane_r) plane_r, avg(height) height,
       max({IDX})+1 AS pop, count(*) AS observed
FROM sys_feat WHERE mass_code IN ('f','g','h') AND {TOK} <> ''
GROUP BY 1,2,3
""")

print("3/5 scoring boxels...", flush=True)
bx = con.execute("SELECT * FROM _bx").df()
bx["mc"] = bx["mass_code"].map(MC).astype("float32")
X = bx[FEATS].values.astype("float32")
bx["p_bh"] = bh.predict_proba(X)[:,1]
bx["p_wr"] = np.where(bx.mass_code=='h', wr.predict_proba(X)[:,1], 0.0)
bx["missing"] = (bx["pop"] - bx["observed"]).astype("int64")
bx["exp_bh"] = bx["missing"]*bx["p_bh"]; bx["exp_wr"] = bx["missing"]*bx["p_wr"]
con.register("bxdf", bx[["boxel","mass_code","sector","x","y","z","r_sgra","plane_r","height",
                         "pop","observed","missing","p_bh","p_wr","exp_bh","exp_wr"]])
con.execute("CREATE OR REPLACE TABLE theorised_boxels AS SELECT * FROM bxdf")
con.unregister("bxdf")

print("4/5 generating individual theorised systems (missing indices)...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE theorised_system AS
WITH obs AS (
  SELECT {BOXEL} AS boxel, {IDX} AS idx
  FROM sys_feat WHERE mass_code IN ('f','g','h') AND {TOK} <> ''
),
gen AS (
  SELECT b.boxel, b.mass_code, b.sector, b.x, b.y, b.z, b.r_sgra,
         b.p_bh, b.p_wr, g.idx AS boxel_index
  FROM theorised_boxels b, generate_series(0, b.pop-1) AS g(idx)
)
SELECT gen.boxel AS boxel_key, gen.boxel_index, gen.mass_code, gen.sector,
       gen.x, gen.y, gen.z, gen.r_sgra, gen.p_bh, gen.p_wr,
       TRUE AS is_theorised
FROM gen
LEFT JOIN obs ON gen.boxel=obs.boxel AND gen.boxel_index=obs.idx
WHERE obs.boxel IS NULL
""")

print("5/5 report...", flush=True)
n = con.execute("SELECT count(*) FROM theorised_system").fetchone()[0]
print(f"\ntheorised_system rows written: {n:,}", flush=True)
for r in con.execute("""SELECT mass_code, count(*) systems,
                        round(sum(p_bh)) exp_bh, round(sum(p_wr)) exp_wr
                        FROM theorised_system GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  mc={r[0]}  theorised_systems={r[1]:>12,}  E[BH]={int(r[2]):>9,}  E[WR]={int(r[3]):>7,}", flush=True)
print("\nsample rows:", flush=True)
for r in con.execute("""SELECT boxel_key, boxel_index, mass_code, round(r_sgra) r, round(p_bh,3) pbh
                        FROM theorised_system ORDER BY p_bh DESC LIMIT 8""").fetchall():
    print(f"  {str(r[0])[:30]:30s} idx={r[1]:<5} mc={r[2]} r_core~{int(r[3]):,}ly p_bh={r[4]}", flush=True)
con.close()
print("\nDONE_03F", flush=True)
