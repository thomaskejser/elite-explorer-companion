"""Validate the de-biasing by SPATIAL hold-out.

Ground truth = BH/WR rate in fully-sampled boxels (>=10 scanned, >=80% covered).
Split the galaxy by x-sign into train / test hemispheres.
 - Fit pi(radius) on TRAIN fully-sampled boxels.
 - On TEST fully-sampled boxels (ground truth), compare, per radius band:
       actual rate   (truth)
       de-biased pi  (predicted from TRAIN curve)   <- should match actual
       naive rate    (ALL test scanned incl low-coverage = the biased estimate)
Report weighted MAE: de-biased should beat naive against ground truth.
"""
import duckdb, pathlib, numpy as np
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")
KBASE=r"regexp_replace(name,'[0-9]+(-[0-9]+)?$','')"; TOK=r"regexp_extract(name,'([0-9]+(-[0-9]+)?)$',1)"
BOXEL=f"CASE WHEN {TOK} LIKE '%-%' THEN {KBASE}||'#'||split_part({TOK},'-',1) ELSE {KBASE} END"
IDX=f"CASE WHEN {TOK} LIKE '%-%' THEN CAST(split_part({TOK},'-',2) AS BIGINT) ELSE CAST({TOK} AS BIGINT) END"

con.execute(f"""
CREATE OR REPLACE TEMP TABLE boxstat AS
SELECT {BOXEL} boxel, mass_code, avg(plane_r) plane_r, avg(x) x,
       max({IDX})+1 pop, count(*) FILTER (WHERE is_scanned) scanned,
       sum(has_bh) FILTER (WHERE is_scanned) bh, sum(has_wr) FILTER (WHERE is_scanned) wr
FROM sys_feat WHERE mass_code IN ('f','g','h') AND {TOK}<>'' GROUP BY 1,2
""")
BAND=2500
def curve(where, target, mcs):
    inl=",".join(f"'{m}'" for m in mcs)
    rows=con.execute(f"""SELECT floor(plane_r/{BAND})*{BAND}+{BAND/2} b, sum({target}) t, sum(scanned) sc
        FROM boxstat WHERE mass_code IN ({inl}) AND scanned>=10 AND scanned>=0.8*pop AND {where}
        GROUP BY 1 HAVING sum(scanned)>=150 ORDER BY 1""").fetchall()
    return np.array([r[0] for r in rows],float), np.array([r[1]/r[2] for r in rows],float)
def pi_at(x,pi,q):
    return np.interp(q,x,pi,left=pi[0] if len(pi) else 0,right=pi[-1] if len(pi) else 0)

for target, mcs, label in [("bh",["f","g","h"],"BLACK HOLE"),("wr",["h"],"WOLF-RAYET")]:
    xk,pk = curve("x < 0", target, mcs)                      # train hemisphere
    # test-hemisphere ground truth (well-sampled) + naive (all scanned) by band
    rows=con.execute(f"""
        SELECT floor(plane_r/{BAND})*{BAND}+{BAND/2} b,
          sum({target}) FILTER (WHERE scanned>=10 AND scanned>=0.8*pop) gt_t,
          sum(scanned) FILTER (WHERE scanned>=10 AND scanned>=0.8*pop) gt_sc,
          sum({target}) all_t, sum(scanned) all_sc
        FROM boxstat WHERE mass_code IN ({','.join(f"'{m}'" for m in mcs)}) AND x>=0
        GROUP BY 1 HAVING sum(scanned) FILTER (WHERE scanned>=10 AND scanned>=0.8*pop) >= 150
        ORDER BY 1""").fetchall()
    print(f"\n=== {label}: TEST hemisphere (x>=0), pi fit on TRAIN (x<0) ===")
    print(f"  {'radius_kly':>10}{'actual%':>9}{'debiased%':>11}{'naive%':>9}{'gt_scanned':>11}")
    num_d=num_n=den=0
    for b,gt_t,gt_sc,all_t,all_sc in rows:
        actual=gt_t/gt_sc; deb=float(pi_at(xk,pk,b)); naive=all_t/all_sc
        num_d+=abs(deb-actual)*gt_sc; num_n+=abs(naive-actual)*gt_sc; den+=gt_sc
        print(f"  {int(b/1000):>10}{100*actual:>9.2f}{100*deb:>11.2f}{100*naive:>9.2f}{int(gt_sc):>11,}")
    print(f"  weighted MAE vs ground truth:  de-biased={100*num_d/den:.2f}pp   naive={100*num_n/den:.2f}pp"
          f"   -> de-biased is {num_n/num_d:.1f}x closer")
con.close()
