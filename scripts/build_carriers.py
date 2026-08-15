"""Build the fleet-carrier lookup the app uses to find Universal Cartographics.

Source: https://edastro.com/mapcharts/files/fleetcarriers.csv  (~20 MB, ~88k carriers,
EDDN-derived, refreshed roughly every two days). Universal Cartographics appears as
the `exploration` service, in both this file and the game journal.

We keep only what is useful and small:
  * every carrier with Universal Cartographics  (~22.6k)
  * every DSSA carrier regardless of services   (name-prefixed 'DSSA')

DSSA carriers are flagged because they are the RELIABLE ones -- the Deep Space
Support Array parks carriers in fixed public locations for a year or more, and many
show LastMoved dates from 2020. An ordinary carrier can jump at any moment, so
`last_moved` is carried through as the staleness signal.

There is no public DSSA roster file (EDAstro publishes only DSSAdisplaced.csv, a
single displaced entry), so DSSA membership is inferred from the name prefix.

Usage:  python scripts/build_carriers.py
"""
import duckdb, pathlib, urllib.request, json, datetime, os

SRC = "https://edastro.com/mapcharts/files/fleetcarriers.csv"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) elite_mapping/1.0"}
ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "app"
RAW = ROOT / "raw" / "edastro_fleetcarriers.csv"
OUT = APP / "carriers.parquet"
META = APP / "carriers_meta.json"

APP.mkdir(exist_ok=True)
RAW.parent.mkdir(exist_ok=True)

print(f"downloading {SRC} ...", flush=True)
req = urllib.request.Request(SRC, headers=UA)
with urllib.request.urlopen(req, timeout=300) as r, open(RAW, "wb") as f:
    while True:
        b = r.read(1 << 20)
        if not b:
            break
        f.write(b)
print(f"  {RAW.stat().st_size/1e6:.1f} MB -> {RAW}")

con = duckdb.connect(":memory:")
con.execute("SET threads=8")
src = RAW.as_posix()
total = con.execute(f"SELECT count(*) FROM read_csv_auto('{src}')").fetchone()[0]

con.execute(f"""
CREATE OR REPLACE TEMP TABLE c AS
SELECT Callsign AS callsign,
       coalesce(Name, '') AS name,
       LastSystem AS system,
       CAST(Coord_X AS DOUBLE) x, CAST(Coord_Y AS DOUBLE) y, CAST(Coord_Z AS DOUBLE) z,
       EstimatedRegion AS region,
       CAST(LastMoved AS VARCHAR) AS last_moved,
       lower(coalesce(Services, '')) LIKE '%exploration%' AS has_uc,
       upper(coalesce(Name, '')) LIKE 'DSSA%' AS is_dssa
FROM read_csv_auto('{src}')
WHERE Coord_X IS NOT NULL AND LastSystem IS NOT NULL
""")
con.execute(f"""
COPY (SELECT * FROM c WHERE has_uc OR is_dssa ORDER BY callsign)
TO '{OUT.as_posix()}' (FORMAT PARQUET)
""")

n = con.execute(f"SELECT count(*) FROM '{OUT.as_posix()}'").fetchone()[0]
uc = con.execute(f"SELECT count(*) FROM '{OUT.as_posix()}' WHERE has_uc").fetchone()[0]
dssa = con.execute(f"SELECT count(*) FROM '{OUT.as_posix()}' WHERE is_dssa").fetchone()[0]
dssa_uc = con.execute(f"SELECT count(*) FROM '{OUT.as_posix()}' WHERE is_dssa AND has_uc").fetchone()[0]
con.close()

with open(META, "w", encoding="utf-8") as f:
    json.dump({"source": SRC,
               "fetched_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "carriers_in_source": total, "kept": n,
               "with_universal_cartographics": uc, "dssa": dssa, "dssa_with_uc": dssa_uc}, f, indent=1)

print(f"\nsource carriers            : {total:,}")
print(f"kept (UC or DSSA)          : {n:,}   -> {OUT} ({OUT.stat().st_size/1e6:.1f} MB)")
print(f"  with Universal Cartog.   : {uc:,}")
print(f"  DSSA                     : {dssa:,}  (of which UC: {dssa_uc:,})")
print(f"provenance -> {META}")
print("\nNOTE: ordinary carriers move at will; `last_moved` is the staleness signal.")
print("DONE_BUILD_CARRIERS")
