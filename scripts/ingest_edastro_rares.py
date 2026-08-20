"""Ingest EDAstro's FULL per-class star catalogues.

Why this exists
---------------
`is_scanned` is derived from `spansh_body`, and Spansh's galaxy dump is missing
body data that EDAstro has held since 2017. Our other body sources are no help:
every EDAstro / EDSM file in `ingest_manifest` is a **7-day** slice
(`edastro_stars7days`, `edsm_bodies7days`, ...), so a system scanned years ago can
never appear in them. Net effect: systems that were discovered and fully scanned
long ago were still being offered as undiscovered BH/WR candidates.

EDAstro publishes complete per-class catalogues, refreshed daily. They are the only
non-slice body source we have, so everything here is ground truth about what is
already on somebody's map.

Two outputs, for two different jobs:

`edastro_known_rare`  -- black holes and Wolf-Rayets, used as the EXCLUSION signal
    for the candidate pool. If a system is in either file its rare primary is
    already discovered and it is not a find any more. ALL rows count, not just
    `Main Star = yes`: a row at all means somebody scanned that system.

`edastro_neutron_star` -- every known neutron star, used for NAVIGATION rather than
    exclusion. Neutrons are not a discovery target (4.1M of them are catalogued);
    they are FSD jet-cone boosts, and for that you want the complete confirmed list.
    Spansh's body dump knows only 3.53M of these systems, so building the app's
    neutron table from `star_agg.has_neutron` alone loses ~377k boost stars. Body
    level, not system level: `Rotation Period Seconds` is per star, and it is the
    only rotation data in the whole database.
"""
import duckdb, pathlib, urllib.request, datetime, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
RAW.mkdir(exist_ok=True)
BASE = "https://edastro.com/mapcharts/files/"
FILES = [("black_hole", "Black-Holes.csv"), ("wolf_rayet", "Wolf-Rayet-stars.csv")]
NEUTRON_CSV = "neutron-stars.csv"


def fetch(fname):
    """Download to raw/ unless already there. Returns the local path."""
    dest = RAW / f"edastro_{fname}"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        print(f"  {dest.name}: already present ({dest.stat().st_size/1e6:.1f} MB)", flush=True)
        return dest
    url = BASE + fname
    print(f"  downloading {url} ...", flush=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=600) as r, open(tmp, "wb") as f:
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

print("fetching EDAstro rare-star catalogues...", flush=True)
paths = {kind: fetch(f) for kind, f in FILES}

# EDAstro's export has a malformed row or two (a literal '".int(8+9)."' leaks into
# System Bodies), so read every column as VARCHAR and skip unparseable lines.
sel = []
for kind, path in paths.items():
    sel.append(f"""
      SELECT "System" AS name, '{kind}' AS kind,
             "Main Star" = 'yes' AS is_main_star,
             nullif("Mass Code",'') AS mass_code,
             nullif("Type",'') AS star_type,
             nullif("Timestamp",'') AS scanned_at,
             nullif("EDSM Discovery Date",'') AS discovered_at
      FROM read_csv('{path.as_posix()}', header=true, all_varchar=true, ignore_errors=true)
      WHERE "System" IS NOT NULL AND "System" <> ''""")

print("\nbuilding edastro_known_rare...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE staging.edastro_known_rare AS
SELECT name, kind, max(is_main_star) AS is_main_star,
       any_value(mass_code) AS mass_code, any_value(star_type) AS star_type,
       min(scanned_at) AS scanned_at, min(discovered_at) AS discovered_at
FROM ({' UNION ALL '.join(sel)})
GROUP BY name, kind
""")
con.execute("CREATE INDEX IF NOT EXISTS idx_ekr_name ON edastro_known_rare(name)")

for r in con.execute("""SELECT kind, count(*) systems,
                               count(*) FILTER (WHERE is_main_star) as_primary
                        FROM edastro_known_rare GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  {r[0]:<12} {r[1]:>9,} systems  ({r[2]:,} with it as the PRIMARY)")
tot = con.execute("SELECT count(DISTINCT name) FROM edastro_known_rare").fetchone()[0]
print(f"  distinct systems overall: {tot:,}")

def manifest(table, urls, files, note):
    """Record what this table was built from, replacing any earlier entry."""
    con.execute("DELETE FROM ingest_manifest WHERE table_name = ?", [table])
    con.execute("""
    INSERT INTO ingest_manifest (table_name, source_url, raw_file, raw_bytes, row_count,
                                 ingested_at_utc, note)
    VALUES (?, ?, ?, ?, ?, ?, ?)""", [
        table, urls, " + ".join(str(p) for p in files),
        sum(p.stat().st_size for p in files),
        con.execute(f"SELECT count(*) FROM {table}").fetchone()[0],
        datetime.datetime.now(datetime.timezone.utc), note])


manifest("edastro_known_rare",
         BASE + "Black-Holes.csv + " + BASE + "Wolf-Rayet-stars.csv",
         list(paths.values()),
         "FULL per-class catalogues (not a 7-day slice); used to drop already-discovered "
         "BH/WR from the candidate pool")

# --- neutron stars: the complete confirmed list, for FSD jet-cone routing ---------
print("\nfetching EDAstro neutron-star catalogue...", flush=True)
npath = fetch(NEUTRON_CSV)

# The catalogue is keyed by id64 and carries the body name, not the system name, so
# the system name is resolved in three steps -- spine, then EDSM, then derived from
# the body name. The third step matters: 39,467 systems here are in NEITHER of our
# system tables, and every one of them is procedurally named, so truncating the body
# name after its `XX-X <masscode><n>[-<n>]` token recovers the system exactly. Where
# the spine also knows the name, that derivation agrees with it 99.9993% of the time
# (27 disagreements in 3.97M), which is what licenses using it as the fallback.
PG = r"""nullif(regexp_extract(body_name, '^(.* [A-Z][A-Z]-[A-Z] [a-h][0-9]+(-[0-9]+)?)', 1), '')"""
print("building edastro_neutron_star...", flush=True)
con.execute(f"""
CREATE OR REPLACE TABLE staging.edastro_neutron_star AS
WITH raw AS (
  SELECT "ID64 SystemAddress"::BIGINT               AS system_id64,
         "Name"                                     AS body_name,
         TRY_CAST("Rotation Period Seconds" AS DOUBLE) AS rot_period_s,
         TRY_CAST("Region ID" AS INTEGER)           AS region,
         TRY_CAST(X AS DOUBLE) AS cat_x, TRY_CAST(Y AS DOUBLE) AS cat_y,
         TRY_CAST(Z AS DOUBLE) AS cat_z
  FROM read_csv('{npath.as_posix()}', header=true, all_varchar=true, ignore_errors=true)
  WHERE "ID64 SystemAddress" IS NOT NULL
)
SELECT r.system_id64,
       coalesce(s.name, e.name, {PG})               AS system_name,
       r.body_name,
       coalesce(s.name, e.name, {PG}) = r.body_name AS is_arrival_star,
       r.rot_period_s, r.region,
       -- the spine's coordinates win where we have them: 733 catalogue rows disagree
       -- with it by more than 1 ly (0.018%), and the spine is what every other table
       -- here is positioned against. Catalogue coordinates are the only source for
       -- the 164,759 systems missing from the spine entirely.
       coalesce(s.x, r.cat_x) AS x,
       coalesce(s.y, r.cat_y) AS y,
       coalesce(s.z, r.cat_z) AS z
FROM raw r
LEFT JOIN sys_feat s          ON s.system_id64 = r.system_id64
LEFT JOIN edsm_star_system e  ON e.id64        = r.system_id64
""")
con.execute("CREATE INDEX IF NOT EXISTS idx_ens_sys ON edastro_neutron_star(system_id64)")

r = con.execute("""SELECT count(*), count(DISTINCT system_id64),
                          count(*) FILTER (WHERE is_arrival_star),
                          count(*) FILTER (WHERE system_name IS NULL),
                          count(*) FILTER (WHERE x IS NULL)
                   FROM edastro_neutron_star""").fetchone()
print(f"  {r[0]:,} neutron stars in {r[1]:,} systems")
print(f"  {r[2]:,} are the system's arrival star ({r[2]/r[0]:.1%})")
print(f"  unnamed: {r[3]:,}   without coordinates: {r[4]:,}")
gain = con.execute("""SELECT count(DISTINCT n.system_id64)
                      FROM edastro_neutron_star n
                      LEFT JOIN star_agg a USING(system_id64)
                      WHERE coalesce(a.has_neutron, 0) = 0""").fetchone()[0]
print(f"  {gain:,} of these systems are NOT in star_agg.has_neutron -- that is what "
      f"the app gains")
manifest("edastro_neutron_star", BASE + NEUTRON_CSV, [npath],
         "FULL neutron catalogue (not a 7-day slice); body level, carries rotation "
         "period. Navigation source for app/neutron.parquet, not an exclusion signal.")

print("\nimpact on the current candidate definition:")
for r in con.execute("""
  SELECT s.mass_code, count(*) candidates,
         count(*) FILTER (WHERE k.name IS NOT NULL) already_known
  FROM sys_feat s
  LEFT JOIN (SELECT DISTINCT name FROM edastro_known_rare) k ON k.name = s.name
  WHERE NOT s.is_scanned AND s.mass_code IN ('e','f','g','h')
  GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"  mc={r[0]}  candidates={r[1]:>9,}  already-known BH/WR={r[2]:>7,}  ({r[2]/r[1]:.2%})")
con.close()
print("\ndone. re-run scripts/build_candidates.py to apply.")
