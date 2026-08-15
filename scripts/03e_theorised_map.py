"""Enumerate theorised (Stellar-Forge-implied, not-in-DB) f/g/h systems at BOXEL
granularity and rank them for undiscovered black holes / Wolf-Rayet stars.

Grounding & honesty:
- A boxel with >=1 observed system is located by its known siblings (boxel <=
  320/640/1280 ly, fine for a ~kly regional model). We do NOT fabricate exact
  catalogue names or per-system coordinates.
- Missing systems in a boxel = (max observed index + 1) - observed count. Indices
  are dense 0..K-1 in the Stellar Forge, so this is a lower bound on theorised
  unscanned systems in that boxel.
- Model score is ~constant within a boxel (fixed mass_code + boxel-centroid
  position), so expected undiscovered = missing * P(target | boxel).
- Scores are ranking-grade / upper-ish (scanned systems over-represent the bright
  massive primary). Reported as such.
"""
import duckdb, pathlib, numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = pathlib.Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")
MC = {'e':0,'f':1,'g':2,'h':3}
FEATS = ["mc","r_sgra","plane_r","height","x","y","z"]

# --- refit models on scanned systems (same recipe as 03c) ---
print("refitting BH/WR models on scanned systems...", flush=True)
tr = con.execute("""SELECT mass_code,x,y,z,r_sgra,plane_r,height,has_bh,has_wr
                    FROM sys_feat WHERE mass_code IN ('e','f','g','h') AND is_scanned""").df()
tr["mc"] = tr["mass_code"].map(MC).astype("float32")
bh = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, min_samples_leaf=200
     ).fit(tr[FEATS].values.astype("float32"), tr["has_bh"].values.astype(int))
h = tr[tr.mass_code=='h']
wr = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, min_samples_leaf=200
     ).fit(h[FEATS].values.astype("float32"), h["has_wr"].values.astype(int))

# --- boxel aggregates for f/g/h (located by observed siblings) ---
print("aggregating observed systems into boxels...", flush=True)
con.execute(r"""
CREATE OR REPLACE TABLE theorised_boxels AS
WITH p AS (
  SELECT mass_code, x, y, z, r_sgra, plane_r, height,
         regexp_replace(name, '[0-9]+(-[0-9]+)?$', '') AS boxel_key,
         regexp_extract(name, '([0-9]+(-[0-9]+)?)$', 1) AS idx_raw
  FROM sys_feat WHERE mass_code IN ('f','g','h')
),
i AS (
  SELECT *, CASE WHEN idx_raw LIKE '%-%'
              THEN CAST(split_part(idx_raw,'-',1) AS BIGINT)*1000 + CAST(split_part(idx_raw,'-',2) AS BIGINT)
              ELSE CAST(idx_raw AS BIGINT) END AS idx
  FROM p WHERE idx_raw <> ''
)
SELECT mass_code, boxel_key,
       regexp_replace(boxel_key, ' [A-Z]{1,2}-[A-Z] [a-h]$', '') AS sector,
       avg(x) AS x, avg(y) AS y, avg(z) AS z,
       avg(r_sgra) AS r_sgra, avg(plane_r) AS plane_r, avg(height) AS height,
       max(idx)+1 AS boxel_pop, count(*) AS observed,
       (max(idx)+1) - count(*) AS missing
FROM i GROUP BY 1,2,3
""")

bx = con.execute("SELECT * FROM theorised_boxels").df()
bx["mc"] = bx["mass_code"].map(MC).astype("float32")
X = bx[FEATS].values.astype("float32")
bx["p_bh"] = bh.predict_proba(X)[:,1]
bx["p_wr"] = np.where(bx.mass_code=='h', wr.predict_proba(X)[:,1], 0.0)
bx["exp_bh"] = bx["missing"] * bx["p_bh"]
bx["exp_wr"] = bx["missing"] * bx["p_wr"]

con.register("bx_df", bx[["mass_code","boxel_key","sector","x","y","z","r_sgra",
                          "boxel_pop","observed","missing","p_bh","p_wr","exp_bh","exp_wr"]])
con.execute("CREATE OR REPLACE TABLE theorised_boxels AS SELECT * FROM bx_df")
con.unregister("bx_df")

def line(*v): print("  " + "  ".join(str(x) for x in v), flush=True)

print("\n=== TOTALS (theorised f/g/h systems not in any DB) ===")
for mc in ['f','g','h']:
    d = bx[bx.mass_code==mc]
    line(f"mc={mc}", f"boxels={len(d):,}", f"theorised_systems={int(d.missing.sum()):,}",
         f"E[BH]={int(d.exp_bh.sum()):,}", f"E[WR]={int(d.exp_wr.sum()):,}")
line("TOTAL", f"boxels={len(bx):,}", f"theorised_systems={int(bx.missing.sum()):,}",
     f"E[BH]={int(bx.exp_bh.sum()):,}", f"E[WR]={int(bx.exp_wr.sum()):,}")

print("\n=== TOP 15 SECTORS by expected undiscovered BLACK HOLES ===")
for r in con.execute("""SELECT sector, round(sum(exp_bh)) e_bh, sum(missing) theorised,
                        round(min(r_sgra)) r_core FROM theorised_boxels
                        GROUP BY 1 ORDER BY 2 DESC LIMIT 15""").fetchall():
    line(f"{str(r[0])[:24]:24s}", f"E[BH]={int(r[1]):>7,}", f"theorised={int(r[2]):>9,}",
         f"r_core~{int(r[3]):,}ly")

print("\n=== TOP 15 SECTORS by expected undiscovered WOLF-RAYET ===")
for r in con.execute("""SELECT sector, round(sum(exp_wr)) e_wr, sum(missing) theorised,
                        round(min(r_sgra)) r_core FROM theorised_boxels
                        WHERE mass_code='h' GROUP BY 1 ORDER BY 2 DESC LIMIT 15""").fetchall():
    line(f"{str(r[0])[:24]:24s}", f"E[WR]={int(r[1]):>6,}", f"theorised_h={int(r[2]):>7,}",
         f"r_core~{int(r[3]):,}ly")
con.close()
print("\nDONE_03E", flush=True)
