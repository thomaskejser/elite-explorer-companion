"""Measure the selection bias: does observed BH/WR rate fall as boxel coverage
rises, holding mass_code + galactic radius fixed? If so, the high-coverage rate
is the de-biased (true Forge) rate.

coverage = scanned systems / boxel_pop (max index+1), per correct boxel.
"""
import duckdb, pathlib
con = duckdb.connect(str(pathlib.Path(__file__).resolve().parent.parent / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")

KBASE = r"regexp_replace(name,'[0-9]+(-[0-9]+)?$','')"
TOK   = r"regexp_extract(name,'([0-9]+(-[0-9]+)?)$',1)"
BOXEL = f"CASE WHEN {TOK} LIKE '%-%' THEN {KBASE}||'#'||split_part({TOK},'-',1) ELSE {KBASE} END"
IDX   = f"CASE WHEN {TOK} LIKE '%-%' THEN CAST(split_part({TOK},'-',2) AS BIGINT) ELSE CAST({TOK} AS BIGINT) END"

# per-boxel: pop (all in-db), scanned count, confirmed BH/WR (among scanned), radius
con.execute(f"""
CREATE OR REPLACE TEMP TABLE boxstat AS
SELECT {BOXEL} AS boxel, mass_code, avg(plane_r) plane_r,
       max({IDX})+1 AS pop,
       count(*) FILTER (WHERE is_scanned) AS scanned,
       sum(has_bh) FILTER (WHERE is_scanned) AS bh,
       sum(has_wr) FILTER (WHERE is_scanned) AS wr
FROM sys_feat WHERE mass_code IN ('f','g','h') AND {TOK} <> ''
GROUP BY 1,2
""")

def diag(mc, lo, hi, target):
    print(f"\n=== mass_code={mc}, plane_r {lo//1000}-{hi//1000} kly : {target} rate vs boxel coverage ===")
    print(f"  {'coverage bin':>14}{'boxels':>9}{'scanned':>10}{f'{target}':>8}{'rate%':>9}")
    for r in con.execute(f"""
        SELECT CASE WHEN scanned::float/pop < 0.01 THEN '1 <1%'
                    WHEN scanned::float/pop < 0.05 THEN '2 1-5%'
                    WHEN scanned::float/pop < 0.20 THEN '3 5-20%'
                    WHEN scanned::float/pop < 0.50 THEN '4 20-50%'
                    WHEN scanned::float/pop < 0.90 THEN '5 50-90%'
                    ELSE '6 >=90%' END AS covbin,
               count(*) boxels, sum(scanned) sc, sum({target}) t,
               round(100.0*sum({target})/nullif(sum(scanned),0),3) rate
        FROM boxstat
        WHERE mass_code='{mc}' AND plane_r>={lo} AND plane_r<{hi} AND pop>0
        GROUP BY 1 ORDER BY 1
    """).fetchall():
        print(f"  {r[0]:>14}{r[1]:>9,}{int(r[2]):>10,}{int(r[3]):>8,}{r[4]:>9}")

# Black holes: mass code f, in data-rich inner bands (control radius)
diag('f', 4000, 8000, 'bh')
diag('f', 8000, 12000, 'bh')
diag('f', 20000, 30000, 'bh')
# Wolf-Rayet: mass code h
diag('h', 4000, 10000, 'wr')
diag('h', 10000, 20000, 'wr')
con.close()
