"""Export the galactic-region lookup used by the app at runtime.

ED has 42 hand-drawn galactic regions (Inner Orion Spur, The Abyss, ...). They are
not derivable from a system's name or coordinates by formula, but EDAstro labels
572,833 systems with their region id, which is dense enough to classify any point by
nearest neighbour. Validated at 99.55% on a 20% hold-out (k=5 majority vote), and
spot-checked against known landmarks (Sol -> Inner Orion Spur, Sgr A* -> Galactic
Centre, Colonia -> Inner Scutum-Centaurus Arm, Beagle Point -> The Abyss).

Writes two small files next to the app so it needs no database at runtime:
  app/regions.parquet    x, y, z, region_id  (float32/int8 -- a few MB)
  app/region_names.json  region_id -> display name

Region NAMES come from canonn_codex_event, which contains entries uploaded by
non-English clients; the modal NON-NULL localised name per id is taken so we get
"Outer Scutum-Centaurus Arm" rather than "Bras Ecu-Croix externe".
"""
import duckdb, pathlib, json
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "app"
APP.mkdir(exist_ok=True)
con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"), read_only=True)
con.execute("SET memory_limit='5GB'")
con.execute("SET threads=8")

print("1/3 region id -> name (modal non-null localised name)...", flush=True)
rows = con.execute("""
WITH c AS (
  SELECT CAST(regexp_extract(region_name,'([0-9]+)',1) AS INT) rid,
         region_name_localised rname, count(*) n
  FROM canonn_codex_event
  WHERE region_name IS NOT NULL AND region_name_localised IS NOT NULL
  GROUP BY 1,2)
SELECT rid, rname FROM (SELECT *, row_number() OVER (PARTITION BY rid ORDER BY n DESC) rk FROM c)
WHERE rk = 1 ORDER BY rid
""").fetchall()
names = {int(r[0]): r[1] for r in rows}
print(f"    {len(names)} regions named; 18 = {names.get(18)!r}")

print("2/3 labelled points (edastro region joined to spansh coordinates)...", flush=True)
df = con.execute("""
SELECT CAST(e.region AS INT) rid, s.x, s.y, s.z
FROM edastro_star_system e JOIN spansh_system s ON s.name = e.name
WHERE e.region IS NOT NULL
""").df()
print(f"    labelled systems: {len(df):,}   distinct regions: {df.rid.nunique()}")

missing = sorted(set(df.rid.unique().tolist()) - set(names))
if missing:
    print(f"    ! region ids with no name: {missing} (will show as 'Region <id>')")

print("3/3 writing app files...", flush=True)
# written via DuckDB (pandas has no parquet engine installed here, and the app
# reads parquet through DuckDB anyway)
out = (APP / "regions.parquet").as_posix()
con.register("reg_df", df)
con.execute(f"""
COPY (SELECT CAST(x AS FLOAT) x, CAST(y AS FLOAT) y, CAST(z AS FLOAT) z,
             CAST(rid AS SMALLINT) region_id
      FROM reg_df) TO '{out}' (FORMAT PARQUET)
""")
con.unregister("reg_df")
con.close()
with open(APP / "region_names.json", "w", encoding="utf-8") as f:
    json.dump({str(k): v for k, v in sorted(names.items())}, f, ensure_ascii=False, indent=0)

sz = (APP / "regions.parquet").stat().st_size / 1e6
print(f"    wrote app/regions.parquet ({len(df):,} rows, {sz:.1f} MB)")
print(f"    wrote app/region_names.json ({len(names)} names)")
print("\nDONE_BUILD_REGIONS")
