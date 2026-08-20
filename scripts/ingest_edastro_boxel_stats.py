"""Ingest EDAstro's per-boxel statistics, for the helium-rich gas giant model.

Why this exists
---------------
`boxel-stats.csv` publishes, per boxel, the average/min/max **helium fraction** of the
gas giants scanned in it. That single column is the sharpest predictor we have for
helium-rich gas giants: over fully-scanned e/f/g systems the observed hit rate is a
flat **zero** below 28% helium and climbs monotonically to ~63% by 33.5%. See
`scripts/build_candidates.py`, which fits the curve at build time and emits `p_hr`.

Two properties of the file that the join depends on:

* **The boxel key includes the part number, separated by a SPACE** --
  `Thaileia ZK-O e 6`, not `Thaileia ZK-O e6`. Our own key uses `#` as the separator
  (`Thaileia ZK-O e#6`), so a translation is required. Getting this wrong fails
  silently and *specifically* drops every multi-part boxel, which is all of `d`.
* **Coverage is e/f/g/h only** -- 706,122 / 58,121 / 24,965 / 4,809 boxels, no `d` at
  all. That happens to match the BH/WR candidate pool exactly, so nothing is lost
  here, but it does mean the helium signal cannot be used to hunt `d`-mass systems
  even though they are where helium-rich giants are most common.

The helium figure is an AGGREGATE OF SCANNED BODIES, not a generator input: every one
of the 340,230 boxels carrying a figure has at least one gas giant recorded, and all
451,587 boxels with no gas giants have no figure. So it can only rate a boxel somebody
has already dipped into -- it predicts the *rest* of a sampled boxel, not a virgin one.

Output: table `edastro_boxel_stats`, keyed by our `#`-form boxel so it joins directly.

Usage:  python scripts/ingest_edastro_boxel_stats.py
"""
import duckdb, pathlib, urllib.request, datetime, shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
RAW.mkdir(exist_ok=True)
BASE = "https://edastro.com/mapcharts/files/"
FNAME = "boxel-stats.csv"


def fetch(fname):
    dest = RAW / f"edastro_{fname}"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        print(f"  {dest.name}: already present ({dest.stat().st_size/1e6:.1f} MB)", flush=True)
        return dest
    print(f"  downloading {BASE + fname} ...", flush=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(BASE + fname, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=900) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 20)
    tmp.replace(dest)
    print(f"    -> {dest.name} ({dest.stat().st_size/1e6:.1f} MB)", flush=True)
    return dest


import os
# Extracts land in `staging`, NEVER in `main`. The pipeline is
#     download -> staging -> merge -> main
# so a raw provider snapshot is a STAGED INPUT, and only an etl/ builder is
# allowed to write a model table. common.db.connect() sets
# search_path='main,staging', so builders still refer to these unqualified.
con = duckdb.connect(os.environ.get("ELITE_DB")
                     or str(ROOT / "elite_mapping.duckdb"))
con.execute("CREATE SCHEMA IF NOT EXISTS staging")
con.execute("SET memory_limit='6GB'")
con.execute("SET threads=8")

print("fetching EDAstro boxel statistics...", flush=True)
path = fetch(FNAME)

print("\nbuilding edastro_boxel_stats...", flush=True)
# EDAstro '<base> <part>' -> our '<base>#<part>'. Only the LAST space-separated token is
# a part number, and only when it is numeric -- sector names contain spaces too.
OURKEY = r"""CASE WHEN regexp_matches("Boxel", ' [0-9]+$')
                  THEN regexp_replace("Boxel", ' ([0-9]+)$', '#\1')
                  ELSE "Boxel" END"""
con.execute(f"""
CREATE OR REPLACE TABLE staging.edastro_boxel_stats AS
SELECT {OURKEY}                                AS boxel,
       "Boxel"                                 AS edastro_boxel,
       nullif("Mass Code", '')                 AS mass_code,
       TRY_CAST("Systems" AS BIGINT)           AS systems,
       TRY_CAST("Helium Avg" AS DOUBLE)        AS helium_avg,
       TRY_CAST("Helium Min" AS DOUBLE)        AS helium_min,
       TRY_CAST("Helium Max" AS DOUBLE)        AS helium_max,
       TRY_CAST("Hydrogen Avg" AS DOUBLE)      AS hydrogen_avg,
       TRY_CAST("Age Avg" AS DOUBLE)           AS age_avg,
       TRY_CAST("Total Gas Giants" AS DOUBLE)  AS gas_giants,
       TRY_CAST("Avg Gas Giants" AS DOUBLE)    AS gas_giants_avg,
       TRY_CAST("Avg Bodies" AS DOUBLE)        AS bodies_avg,
       TRY_CAST("Avg X" AS DOUBLE) AS x, TRY_CAST("Avg Y" AS DOUBLE) AS y,
       TRY_CAST("Avg Z" AS DOUBLE) AS z
FROM read_csv('{path.as_posix()}', header=true, all_varchar=true, ignore_errors=true)
WHERE "Boxel" IS NOT NULL
""")
con.execute("CREATE INDEX IF NOT EXISTS idx_ebs_boxel ON edastro_boxel_stats(boxel)")

r = con.execute("""SELECT count(*), count(helium_avg), min(helium_avg), max(helium_avg),
                          count(*) FILTER (WHERE boxel LIKE '%#%')
                   FROM edastro_boxel_stats""").fetchone()
print(f"  {r[0]:,} boxels;  {r[1]:,} carry a helium figure "
      f"(range {r[2]:.2f}% .. {r[3]:.2f}%)")
print(f"  {r[4]:,} are multi-part (translated ' N' -> '#N')")
print(f"  {'mc':>4}{'boxels':>12}{'with helium':>14}{'he>=29':>10}")
for row in con.execute("""SELECT mass_code, count(*), count(helium_avg),
                                 count(*) FILTER (WHERE helium_avg >= 29)
                          FROM edastro_boxel_stats GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {str(row[0]):>4}{row[1]:>12,}{row[2]:>14,}{row[3]:>10,}")

# join sanity: the key must actually match the spine, or the model silently sees nothing
TK = r"regexp_extract(name,'([0-9]+(-[0-9]+)?)$',1)"
KB = r"regexp_replace(name,'[0-9]+(-[0-9]+)?$','')"
BX = f"CASE WHEN {TK} LIKE '%-%' THEN {KB}||'#'||split_part({TK},'-',1) ELSE {KB} END"
print("\njoin check against sys_feat (e/f/g/h):", flush=True)
for row in con.execute(f"""
    WITH s AS (SELECT DISTINCT {BX} boxel, mass_code FROM sys_feat
               WHERE mass_code IN ('e','f','g','h') AND {TK} <> '')
    SELECT s.mass_code, count(*) boxels,
           count(*) FILTER (WHERE b.boxel IS NOT NULL) n_joined
    FROM s LEFT JOIN edastro_boxel_stats b USING(boxel)
    GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  mc={row[0]}  spine boxels={row[1]:>9,}  matched={row[2]:>9,} "
          f"({row[2]/row[1]:.1%})")

now = datetime.datetime.now(datetime.timezone.utc)
con.execute("DELETE FROM ingest_manifest WHERE table_name = 'edastro_boxel_stats'")
con.execute("""
INSERT INTO ingest_manifest (table_name, source_url, raw_file, raw_bytes, row_count,
                             ingested_at_utc, note)
VALUES (?, ?, ?, ?, ?, ?, ?)""", [
    "edastro_boxel_stats", BASE + FNAME, str(path), path.stat().st_size,
    con.execute("SELECT count(*) FROM edastro_boxel_stats").fetchone()[0], now,
    "per-boxel aggregates incl. gas-giant helium fraction; e/f/g/h only, no d. "
    "Helium is an aggregate of SCANNED bodies, not a generator input. Drives p_hr "
    "in build_candidates.py.",
])
con.close()
print("\ndone. re-run scripts/build_candidates.py to apply.")
