"""Export CONFIRMED neutron-star systems for the app's nearest-neutron table.

These are not predictions: every row is a system where a neutron star has actually
been seen and uploaded. That is what you want for FSD supercharging -- a jet-cone
boost needs a neutron that is definitely there, not one that is 27% likely.

Two sources, unioned, because neither is complete on its own:

  edastro_neutron_star   EDAstro's full per-class catalogue (4.07M systems). Not a
                         7-day slice, so it holds scans going back to 2017.
  star_agg.has_neutron   derived from spansh_body (3.53M systems).

EDAstro carries 376,849 systems Spansh's bodies do not, and Spansh carries 916
EDAstro is missing, so the union beats either. 164,759 of EDAstro's systems are not
in `sys_feat` at all -- the catalogue's own coordinates are the only way to reach
them, which is why this reads x/y/z from `edastro_neutron_star` rather than joining
back to the spine (the ingest already resolved coordinates and names there).

Coordinates are stored as float32: a neutron star is a navigation waypoint, and
float32 holds ~7 significant digits, which is sub-ly precision anywhere in the
galaxy. Halves the file against float64.

Usage:  python scripts/build_neutron.py
"""
import duckdb, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "app"
OUT = APP / "neutron.parquet"
APP.mkdir(exist_ok=True)

con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"), read_only=True)
con.execute("SET memory_limit='6GB'")
con.execute("SET threads=8")
con.execute("SET preserve_insertion_order=false")

has_cat = con.execute("""SELECT count(*) FROM duckdb_tables()
                         WHERE table_name='edastro_neutron_star'""").fetchone()[0]
if not has_cat:
    raise SystemExit("missing table edastro_neutron_star -- run "
                     "scripts/ingest_edastro_rares.py first")

print("exporting confirmed neutron-star systems...", flush=True)
con.execute(f"""
COPY (
  SELECT name, CAST(x AS FLOAT) x, CAST(y AS FLOAT) y, CAST(z AS FLOAT) z
  FROM (
    -- EDAstro's complete catalogue, one row per system
    SELECT any_value(system_name) AS name, any_value(x) x, any_value(y) y, any_value(z) z,
           system_id64
    FROM edastro_neutron_star
    WHERE system_name IS NOT NULL AND x IS NOT NULL
    GROUP BY system_id64
    UNION
    -- the handful Spansh has and EDAstro does not
    SELECT s.name, s.x, s.y, s.z, s.system_id64
    FROM sys_feat s JOIN star_agg a USING(system_id64)
    WHERE a.has_neutron = 1
      AND NOT EXISTS (SELECT 1 FROM edastro_neutron_star n
                      WHERE n.system_id64 = s.system_id64)
  )
) TO '{OUT.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
""")
n = con.execute(f"SELECT count(*) FROM '{OUT.as_posix()}'").fetchone()[0]
dup = con.execute(f"""SELECT count(*) - count(DISTINCT name) FROM '{OUT.as_posix()}'""").fetchone()[0]
con.close()
print(f"  {n:,} systems -> {OUT}  ({OUT.stat().st_size/1e6:.1f} MB)")
if dup:
    print(f"  note: {dup:,} duplicate system names (distinct id64, same name)")
print("\nDONE_BUILD_NEUTRON")
