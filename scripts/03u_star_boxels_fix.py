"""Apply the 03s theorised correction to star_boxels.

star_boxels (03m) still carries the fill-from-0 bug: missing = max(idx)+1 - in_db,
which fabricates every index below a boxel's minimum observed index.  Rebuild
`missing` with the same rule 03s established for theorised_system:

    missing = internal gaps only (strictly between min and max observed index),
              and only in boxels dense enough for a gap to be trustworthy
              (observed >= DENSITY_MIN of the min..max range); 0 otherwise.

Also records min_idx/max_idx/dense so downstream code can tell "no enumerable
gaps" apart from "genuinely complete".  Columns consumed by 03n (pop, scanned,
in_db, the n_* counts) are preserved unchanged -- only `missing` is corrected.
"""
import duckdb, pathlib, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"))
con.execute("SET memory_limit='6GB'"); con.execute("SET threads=8")
con.execute("SET preserve_insertion_order=false")
KB = r"regexp_replace(name,'[0-9]+(-[0-9]+)?$','')"
TK = r"regexp_extract(name,'([0-9]+(-[0-9]+)?)$',1)"
BX = f"CASE WHEN {TK} LIKE '%-%' THEN {KB}||'#'||split_part({TK},'-',1) ELSE {KB} END"
IX = f"CASE WHEN {TK} LIKE '%-%' THEN CAST(split_part({TK},'-',2) AS BIGINT) ELSE CAST({TK} AS BIGINT) END"
DENSITY_MIN = 0.5

t0 = time.time()
old = con.execute("SELECT count(*), sum(missing) FROM star_boxels").fetchone()
print(f"star_boxels: {old[0]:,} boxels, OLD missing total {int(old[1]):,}", flush=True)

print("computing per-boxel min/max observed index (e/f/g/h)...", flush=True)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE mm AS
SELECT {BX} AS boxel, min({IX}) AS mn, max({IX}) AS mx, count(*) AS obs
FROM sys_feat WHERE mass_code IN ('e','f','g','h') AND {TK} <> ''
GROUP BY 1
""")

# internal gaps = (span of observed index range) - (distinct observed indices in it).
# obs counts systems, which equals distinct indices here (index is unique per boxel).
print("rewriting star_boxels.missing as dense-boxel internal gaps...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE star_boxels AS
SELECT s.* EXCLUDE (missing),
       m.mn AS min_idx, m.mx AS max_idx,
       (m.mx > m.mn AND m.obs::DOUBLE / (m.mx - m.mn + 1) >= {DENSITY_MIN}) AS dense,
       CASE WHEN m.mx > m.mn AND m.obs::DOUBLE / (m.mx - m.mn + 1) >= {DENSITY_MIN}
            THEN (m.mx - m.mn + 1) - m.obs ELSE 0 END AS missing
FROM star_boxels s JOIN mm m ON m.boxel = s.boxel
""")

new = con.execute("SELECT count(*), sum(missing), count(*) FILTER (WHERE dense) FROM star_boxels").fetchone()
print(f"\nNEW: {new[0]:,} boxels ({new[2]:,} dense/enumerable), missing total {int(new[1]):,}"
      f"   (was {int(old[1]):,})")
print(f"\n  {'mc':>4}{'boxels':>10}{'dense':>10}{'in_db':>14}{'unscanned':>12}{'theorised':>11}")
for r in con.execute("""
    SELECT mass_code, count(*), count(*) FILTER (WHERE dense),
           sum(in_db), sum(in_db - scanned), sum(missing)
    FROM star_boxels GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]:>4}{r[1]:>10,}{r[2]:>10,}{int(r[3]):>14,}{int(r[4]):>12,}{int(r[5]):>11,}")
con.close()
print(f"\nDONE_03U  ({(time.time()-t0)/60:.1f} min)", flush=True)
