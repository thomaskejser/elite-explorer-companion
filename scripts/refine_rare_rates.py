"""Compare estimators for the rare-object rates that feed system_predicted.

WHY. build_system_predicted fits p_bh / p_wr as `positives / scanned systems`, banded
by (mass_code, plane_r). That estimator answers "what fraction of SCANNED systems hold
one", but the number is used to answer "what is the chance an UNSCANNED system holds
one" -- and those differ by however biased the scanning was. Commanders do not scan at
random: they fly to systems that already look interesting, so the scanned set is
enriched for exotic stars and the naive rate reads high.

THE CATALOGUE FLOOR. EDAstro publishes COMPLETE catalogues of every black hole and
Wolf-Rayet ever REPORTED (edastro_known_rare), so catalogued positives / all known
systems is a hard LOWER bound on the true rate. It is a floor and not a ceiling, which
is easy to get backwards: an unscanned system counts as a negative here even when it
holds an undiscovered object, so the ratio can only understate. A fitted rate ABOVE the
floor is therefore expected and proves nothing.

THREE ESTIMATORS, per (mass_code, plane_r band):

  A  naive_scanned      positives / scanned systems.  What the builder uses today.
  B  debiased_boxel     the same ratio, but ONLY over WELL-SAMPLED boxels -- >= 10
                        scanned systems AND >= 80% of the boxel's known systems
                        scanned. Where nearly everything in a boxel has been looked
                        at, the scanned set approximates the population and the ratio
                        is close to unbiased. Validated against the fringe sectors,
                        where the biased and de-biased rankings diverge most.
  C  catalogue_floor    catalogued positives / ALL known systems of that mass code.
                        A LOWER bound: it assumes every BH/WR that exists has already
                        been reported, which is false for unexplored space. The truth
                        for an unscanned system sits between C and B, never above B.

This script only MEASURES -- it writes nothing, and there is no --apply. The
correction it justified is IN etl/system_predicted/build.py, where the model is built;
a probability that depends on which flag someone remembered to pass is not a model.
Re-run this after new data to check whether the depletion slope still holds.

Usage:
    ELITE_DB=C:/Source/elite_mapping/elite_mapping_v2.duckdb \\
        python scripts/refine_rare_rates.py
"""
import os, pathlib, sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
DB = pathlib.Path(os.environ.get("ELITE_DB") or (ROOT / "elite_mapping_v2.duckdb"))

BAND = ("CASE WHEN plane_r < 10000 THEN '0-10k' WHEN plane_r < 20000 THEN '10-20k' "
        "WHEN plane_r < 30000 THEN '20-30k' ELSE '30k+' END")
PLANE = "sqrt(pow(k.x - 25.21875, 2) + pow(k.z - 25899.96875, 2))"
BH = "('H','SuperMassiveBlackHole')"
WR = "('W','WN','WNC','WC','WO')"
CATALOGUE_ONLY = "('edastro_rare','edastro_neutron','canonn_codex')"
MIN_SCANNED = 10        # a boxel needs this many scanned systems to say anything
MIN_FRACTION = 0.80     # ... and this fraction of it scanned to be near-unbiased

con = duckdb.connect(str(DB), read_only=True)
for s in ("SET memory_limit='14GB'", "SET threads=10",
          "SET preserve_insertion_order=false", "SET enable_progress_bar=false"):
    con.execute(s)
con.execute("SET temp_directory='C:/Users/thoma/AppData/Local/Temp/claude/duck_tmp3'")
con.execute("SET max_temp_directory_size='400GB'")
print(f"database: {DB.name}\n")

# ---- per-system labels + whether the system counts as scanned -------------------
print("labelling...", flush=True)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE lbl AS
SELECT sb.system_id,
       max(CASE WHEN b.code IN {BH} THEN 1 ELSE 0 END) AS has_bh,
       max(CASE WHEN b.code IN {WR} THEN 1 ELSE 0 END) AS has_wr,
       count(*) FILTER (WHERE b.type = 'star')                       AS n_stars,
       count(*) FILTER (WHERE sb.source NOT IN {CATALOGUE_ONLY}
                           OR sb.source IS NULL)                     AS n_scan_rows
FROM system_body sb JOIN body b ON b.body_id = sb.body_id
GROUP BY 1""")

con.execute(f"""
CREATE OR REPLACE TEMP TABLE sysx AS
SELECT k.system_id, k.mass_code, k.sector_id, k.cube_id, k.sub_cube_id,
       {BAND.replace('plane_r', PLANE)} AS band,
       coalesce(l.has_bh, 0) AS has_bh, coalesce(l.has_wr, 0) AS has_wr,
       CASE WHEN coalesce(l.n_scan_rows,0) > 0 AND coalesce(l.n_stars,0) > 0
            THEN 1 ELSE 0 END AS scanned
FROM system_known k LEFT JOIN lbl l ON l.system_id = k.system_id
WHERE k.mass_code IN ('e','f','g','h')""")

# ---- the ceiling test -----------------------------------------------------------
print("\n=== CEILING TEST: catalogues are COMPLETE, so this bounds the truth ===")
print(f"  {'mc':<4}{'known systems':>15}{'with BH':>12}{'with WR':>12}"
      f"{'BH floor':>12}{'WR floor':>12}")
for r in con.execute("""SELECT mass_code, count(*), sum(has_bh), sum(has_wr)
                        FROM sysx GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]:<4}{r[1]:>15,}{r[2]:>12,}{r[3]:>12,}"
          f"{r[2]/r[1]:>12.2%}{r[3]/r[1]:>12.2%}")
print("  (floor = catalogued positives / ALL known systems of that mass code. It is a")
print("   LOWER bound, NOT a ceiling: an unscanned system counts as a negative even")
print("   when it holds an undiscovered object, so a fitted rate above it is expected.)")

# ---- boxel sampling completeness -------------------------------------------------
con.execute(f"""
CREATE OR REPLACE TEMP TABLE bx AS
SELECT sector_id, cube_id, mass_code, sub_cube_id,
       count(*) AS known, sum(scanned) AS scanned,
       sum(scanned)::DOUBLE / count(*) AS frac
FROM sysx GROUP BY 1,2,3,4""")
print("\n=== boxel sampling ===")
for r in con.execute(f"""SELECT mass_code, count(*) AS boxels,
       count(*) FILTER (WHERE scanned >= {MIN_SCANNED} AND frac >= {MIN_FRACTION})
         AS well_sampled,
       round(avg(frac), 4) AS mean_frac
    FROM bx GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  mc={r[0]}  boxels {r[1]:>8,}   well-sampled {r[2]:>7,}   "
          f"mean scanned fraction {r[3]:.1%}")

# ---- the three estimators --------------------------------------------------------
con.execute(f"""
CREATE OR REPLACE TEMP TABLE est AS
WITH well AS (
  SELECT sector_id, cube_id, mass_code, sub_cube_id FROM bx
  WHERE scanned >= {MIN_SCANNED} AND frac >= {MIN_FRACTION}
),
a AS (SELECT mass_code, band, count(*) n, avg(has_bh) bh, avg(has_wr) wr
      FROM sysx WHERE scanned = 1 GROUP BY 1,2),
b AS (SELECT s.mass_code, s.band, count(*) n, avg(s.has_bh) bh, avg(s.has_wr) wr
      FROM sysx s JOIN well w USING (sector_id, cube_id, mass_code, sub_cube_id)
      WHERE s.scanned = 1 GROUP BY 1,2),
c AS (SELECT mass_code, band, count(*) n, avg(has_bh) bh, avg(has_wr) wr
      FROM sysx GROUP BY 1,2)
SELECT a.mass_code, a.band, a.n AS n_scanned, b.n AS n_well, c.n AS n_all,
       a.bh AS bh_naive, b.bh AS bh_deb, c.bh AS bh_floor,
       a.wr AS wr_naive, b.wr AS wr_deb, c.wr AS wr_floor
FROM a LEFT JOIN b USING (mass_code, band) LEFT JOIN c USING (mass_code, band)""")

for target in ("bh", "wr"):
    print(f"\n=== {target.upper()} rate by estimator ===")
    print(f"  {'mc':<4}{'band':<8}{'scanned':>11}{'well-samp':>11}"
          f"{'A naive':>10}{'B debiased':>12}{'C floor':>10}{'A/B':>8}")
    for r in con.execute(f"""SELECT mass_code, band, n_scanned, n_well,
            {target}_naive, {target}_deb, {target}_floor FROM est
            ORDER BY mass_code, band""").fetchall():
        ratio = (r[4] / r[5]) if r[5] else None
        well = f"{r[3]:,}" if r[3] else "-"
        deb = f"{r[5]:.2%}" if r[5] is not None else "n/a"
        rat = f"{ratio:.2f}x" if ratio else "-"
        print(f"  {r[0]:<4}{r[1]:<8}{r[2]:>11,}{well:>11}"
              f"{r[4]:>10.2%}{deb:>12}{r[6]:>10.2%}{rat:>8}")

print("\nRead A/B as the inflation factor of the current estimator. A value near 1.0")
print("means scanning bias is small in that cell; a large value means the naive rate is")
print("mostly selection effect. Cells with no well-sampled boxels show n/a -- there the")
print("floor (C) is the only defensible anchor.")
# ---- DEPLETION TEST -------------------------------------------------------------
# The decisive question is not "what fraction of KNOWN systems hold one" -- the
# complete catalogues answer that outright. It is "what fraction of the systems NOBODY
# HAS LOOKED AT hold one", and those are not the same population if commanders found
# the easy ones first.
#
# If discovery were unbiased WITHIN a boxel, the measured rate would not depend on how
# much of that boxel has been scanned. If commanders cherry-picked, a lightly scanned
# boxel shows an inflated rate -- only the systems that looked interesting were
# visited -- and the rate FALLS as completeness rises. The slope across completeness
# deciles measures exactly the bias that matters, because the prediction pool IS the
# residue of the most-explored boxels.
print("\n=== DEPLETION TEST: rate vs how completely the boxel has been scanned ===")
for mc in ("e", "f", "g", "h"):
    rows = con.execute(f"""
      SELECT least(cast(floor(b.frac * 10) as int) + 1, 10) AS decile,
             count(*) AS systems, avg(s.has_bh) AS bh, avg(s.has_wr) AS wr
      FROM sysx s JOIN bx b USING (sector_id, cube_id, mass_code, sub_cube_id)
      WHERE s.mass_code = '{mc}' AND s.scanned = 1 AND b.scanned >= {MIN_SCANNED}
      GROUP BY 1 ORDER BY 1""").fetchall()
    if not rows:
        continue
    print(f"\n  mass code {mc}")
    print(f"    {'boxel scanned':<16}{'systems':>12}{'BH rate':>10}{'WR rate':>10}")
    for r in rows:
        lo = (r[0] - 1) * 10
        print(f"    {f'{lo}-{lo+10}%':<16}{r[1]:>12,}{r[2]:>10.2%}{r[3]:>10.2%}")

con.close()
print("\nThis script MEASURES ONLY. The correction it justifies now lives in")
print("etl/system_predicted/build.py, which fits Wolf-Rayet over fully-explored boxels")
print("and leaves black holes naive -- see the note at its rate fit for why the same")
print("move is not defensible for BH. Re-run this after new data to re-check the slope.")
print("\nDONE_REFINE_DIAGNOSTIC")
