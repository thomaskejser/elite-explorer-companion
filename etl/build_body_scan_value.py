"""SUPERSEDED 2026-08-15 -- DO NOT RUN. Kept only for its provenance notes.

The scan-value constants are now COLUMNS of the `body` table (cr_value,
cr_value_terraformable, value_formula), not a table of their own, so they live in
input/body.parquet with the rest of the body dimension and are merged by
etl/load_body.py. The literals below were folded into etl/build_body.py, which is now
the single place they are defined; input/body_scan_value.parquet was joined into
input/body.parquet on the natural key (type, body) and is no longer read by anything.

*** Edit the constants in etl/build_body.py, and correct values by hand in
input/body.parquet. Editing this file changes nothing. *** It exits immediately rather
than reseeding a file the pipeline has stopped reading.

Original header follows.
--------------------------------------------------------------------------------
SEED input/body_scan_value.parquet -- scan-value constants per body type.

ONE-TIME SEEDER (ETL.md): writes only the parquet, refuses if it already exists, and has
no --force. Corrections are made by hand.

WHAT THIS IS. The RAW INPUT to Frontier's exploration-value formula: the per-body-type `k`
constant, in both its non-terraformable and terraformable form. The columns are named
cr_value / cr_value_terraformable because k IS denominated in credits -- but it is NOT the
payout. The payout depends on the body's MASS, so a single credit figure per type does not
exist:

    planets:  base = max(k + k * mass_em^0.2 * 0.56591828, 500)
    stars:    base = k + solar_masses * k / 66.25

Then multipliers apply, none of which are per-type so none are stored here:
    first discovered                    x2.6
    already discovered + mapped         x3.3333333
    first mapped only                   x8.0956
    first discovered AND first mapped   x3.699622554  (then x2.6)
    efficient mapping bonus             x1.25
    Odyssey mapping bonus               + max(v * 0.3, 555)   on mapped values only
STARS CANNOT BE MAPPED, so only the base and first-discovered values apply to them.

SOURCE. EDDiscovery's ScanEstimatedValues, EliteDangerousCore at
EliteDangerous/FrontierData/Enumerations/EstimatedValues.cs, which cites MattG's
"Exploration value formulae" thread on the Frontier forums. Re-fetched and byte-compared
2026-08-12: unchanged.
*** ONLY THE ED 3.3+ BRANCH IS CURRENT. *** That file carries three sets of constants
(pre-2.2, pre-3.3, 3.3+) selected by the scan's timestamp. The higher figures quoted in
many places online -- 155581 for water worlds, 2880 for ordinary stars, 54309 for black
holes -- are the SUPERSEDED 3.2 set. Everything here is the 3.3+ set.

Names come from input/body.parquet so they join to `body` exactly; nothing here reads the
database. Star constants are keyed on body.code (the journal star code), planet constants
on the body name.

Usage:  python etl/build_body_scan_value.py
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import duckdb
from common.db import INPUT

sys.exit("SUPERSEDED: the scan-value constants are now columns of `body`.\n"
         "  define them in   etl/build_body.py\n"
         "  correct them in  input/body.parquet  (by hand)\n"
         "  load them with   python etl/load_body.py")

SRC = INPUT / "body.parquet"
OUT = INPUT / "body_scan_value.parquet"

if OUT.exists():
    sys.exit(f"{OUT} already exists and is AUTHORITATIVE -- refusing to overwrite.\n"
             f"This seeder runs once; correct the file by hand, or delete it to reseed.")
if not SRC.exists():
    sys.exit(f"missing {SRC} -- run etl/build_body.py first")

# --- stars: keyed on the journal code ---------------------------------------
WD = ("D", "DA", "DAB", "DAO", "DAZ", "DAV", "DB", "DBZ", "DBV", "DO", "DOV", "DQ",
      "DC", "DCV", "DX")
STAR_K = {c: 14057.0 for c in WD}          # every white dwarf variant
STAR_K["N"] = 22628.0                       # neutron star
STAR_K["H"] = 22628.0                       # black hole -- same k as a neutron
STAR_K["SuperMassiveBlackHole"] = 33.5678   # NOT a typo: three orders of magnitude LOWER
STAR_DEFAULT_K = 1200.0                     # every other star, Wolf-Rayet included

# --- planets: keyed on the body name, (non-terraformable, terraformable) -----
# Earth-like carries the terraform bonus unconditionally (k = 64831 + 116295), so it has
# no separate terraformable figure. Ammonia and Class I gas giants have no bonus at all.
PLANET_K = {
    "Metal-rich body":                   (21790.0, 21790.0 + 65631.0),
    "High metal content world":          (9654.0, 9654.0 + 100677.0),
    "Class II gas giant":               (9654.0, 9654.0 + 100677.0),
    "Water world":                      (64831.0, 64831.0 + 116295.0),
    "Earth-like world":                 (64831.0 + 116295.0, None),
    "Ammonia world":                    (96932.0, None),
    "Class I gas giant":                (1656.0, None),
}
PLANET_DEFAULT = (300.0, 300.0 + 93328.0)   # every other planet class

con = duckdb.connect(":memory:")
rows = con.execute(f"""SELECT type, body, code FROM '{SRC.as_posix()}'
                       ORDER BY body_id""").fetchall()
print(f"read {len(rows)} body type(s) from {SRC.name}")

out = []
for typ, body, code in rows:
    if typ == "star":
        k = STAR_K.get(code, STAR_DEFAULT_K)
        out.append((typ, body, code, k, None, "star"))
    else:
        k, kt = PLANET_K.get(body, PLANET_DEFAULT)
        out.append((typ, body, code, k, kt, "planet"))

con.execute("""CREATE TABLE v (type VARCHAR, body VARCHAR, code VARCHAR,
                               cr_value DOUBLE, cr_value_terraformable DOUBLE,
                               value_formula VARCHAR)""")
con.executemany("INSERT INTO v VALUES (?,?,?,?,?,?)", out)

INPUT.mkdir(exist_ok=True)
con.execute(f"""COPY (SELECT * FROM v ORDER BY value_formula, cr_value DESC, body)
                TO '{OUT.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
back = con.execute(f"SELECT count(*) FROM '{OUT.as_posix()}'").fetchone()[0]
print(f"wrote {OUT}  ({back} rows, {OUT.stat().st_size:,} bytes)")
same = con.execute(f"""SELECT count(*) FROM (
    SELECT * FROM v EXCEPT SELECT * FROM '{OUT.as_posix()}')""").fetchone()[0]
print(f"  round-trips identical: {same == 0}")

print(f"\n  {'type':<7}{'body':<36}{'code':<22}{'cr':>10}{'cr terraform':>14}")
for r in con.execute(f"""SELECT type, body, coalesce(code,''), cr_value,
                                cr_value_terraformable
                         FROM '{OUT.as_posix()}'
                         ORDER BY value_formula, cr_value DESC, body""").fetchall():
    kt = "-" if r[4] is None else f"{r[4]:,.0f}"
    print(f"  {r[0]:<7}{r[1][:35]:<36}{r[2][:21]:<22}{r[3]:>10,.4f}{kt:>14}")

print(f"\n  {'group':<44}{'types':>7}{'cr':>12}")
for r in con.execute(f"""SELECT value_formula, cr_value, cr_value_terraformable,
                                count(*) AS n
                         FROM '{OUT.as_posix()}' GROUP BY 1, 2, 3
                         ORDER BY 1, 2 DESC""").fetchall():
    kt = "" if r[2] is None else f"  (+tf {r[2]:,.0f})"
    print(f"  {r[0] + kt:<44}{r[3]:>7}{r[1]:>12,.4f}")
con.close()
print("\nNOTE this file is the RAW INPUT. It is not a credit amount -- the payout needs the")
print("body's mass through the formula in this script's docstring, then the multipliers.")
print("\nDONE_BUILD_BODY_SCAN_VALUE")
