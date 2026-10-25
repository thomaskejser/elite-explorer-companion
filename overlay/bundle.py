import hashlib
import pathlib
import sys
import time
import zlib

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from common.current import CURRENT_DB, CURRENT_TABLES, MODEL_SCHEMA

OUT = ROOT / "bundle"
WORK = OUT / "work.duckdb"
PACKED = OUT / "model.duckdb.z"
ID = OUT / "model.id"

MODEL_COLUMNS = {
    "region": "region_id, region",
    "sector": "sector_id, sector, x, y, z, region_id",
    "poi": "poi_id, poi, poi_class",
    "system_predicted": "system, system_id, mass_code, sector, boxel, x, y, z, dist_sol, "
                        "p_bh, p_wr, p_neutron, p_wd, p_herbig, p_otype, p_supergiant, exp_bodies, is_catalog, gated_by, p_exist",
    "system_poi": "poi_id, system, sector, x, y, z",
    "carrier": "callsign, carrier_name, has_universal_cartographics, is_reliable",
    "carrier_position": "callsign, system, x, y, z",
    "system_unfound": "system, x, y, z, dist_ly, sp_type, band, sector, nearest, nearest_ly",
    "station_service": "system, station, distance_to_arrival_ls, material_trader, technology_broker, is_listed, "
                       "x, y, z",
    "station": "system, station, is_carrier, distance_to_arrival_ls, large_pads, has_universal_cartographics, "
               "has_vista_genomics, has_repair, has_restock, last_reported, is_listed, x, y, z",
    "system_neutron": "sector_id, system_in_sector, mass_code, x, y, z",
    "region_known": "region_id, systems",
    "sector_known": "sector_id, systems",
    "galaxy_density": "cell_x, cell_z, systems",
    "region_map": "z_row, x_start, length, region_id",
    "system_known_probe": "system",
}
SEED_TABLES = CURRENT_TABLES + ["system_alias"]


def main():
    OUT.mkdir(exist_ok=True)
    WORK.unlink(missing_ok=True)
    t0 = time.perf_counter()
    con = duckdb.connect(str(WORK))
    con.execute(f"ATTACH '{CURRENT_DB.as_posix()}' AS cur (READ_ONLY)")
    have = {(s, t) for s, t in con.execute(
        "SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name = 'cur'"
    ).fetchall()}
    con.execute("CREATE SCHEMA model")
    for table, cols in MODEL_COLUMNS.items():
        if (MODEL_SCHEMA, table) not in have:
            sys.exit(f"{CURRENT_DB.name} has no {MODEL_SCHEMA}.{table} -- "
                     f"run python etl/refresh_current.py first")
        con.execute(f"CREATE TABLE model.{table} AS "
                    f"SELECT {cols} FROM cur.{MODEL_SCHEMA}.{table}")
        n = con.execute(f"SELECT count(*) FROM model.{table}").fetchone()[0]
        print(f"model.{table:<20}{n:>12,}")
    con.execute("CREATE SCHEMA seed")
    for table in SEED_TABLES:
        if ("main", table) not in have:
            print(f"seed.{table:<21}{'absent':>12}")
            continue
        con.execute(f"CREATE TABLE seed.{table} AS SELECT * FROM cur.main.{table}")
        n = con.execute(f"SELECT count(*) FROM seed.{table}").fetchone()[0]
        print(f"seed.{table:<21}{n:>12,}")
    con.execute("DETACH cur")
    con.execute("CHECKPOINT")
    con.close()
    raw = WORK.read_bytes()
    packed = zlib.compress(raw, 9)
    PACKED.write_bytes(packed)
    ID.write_text(hashlib.sha1(packed).hexdigest()[:16], encoding="ascii")
    WORK.unlink()
    print(f"\n{len(raw) / 1e6:,.1f} MB -> {len(packed) / 1e6:,.1f} MB packed, "
          f"id {ID.read_text()}, {time.perf_counter() - t0:.0f} s")
    print(f"wrote {PACKED}\n  now: cargo build --release")


if __name__ == "__main__":
    main()
