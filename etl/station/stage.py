import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect, record_ingest, stage_json, table_count
from common.sources import download, read_staged_state, source_meta, validator, write_staged_state

URL = "https://downloads.spansh.co.uk/galaxy_stations.json.gz"
TABLE = "spansh_galaxy_station"
RAW_NAME = "spansh_galaxy_stations.json.gz"
MIN_BYTES = 1_000_000_000
MIN_ROWS = 50_000
PROVENANCE = "the WHOLE galaxy as Spansh last dumped it -- every system holding a station"
STATION = ("STRUCT(name VARCHAR, id BIGINT, updateTime VARCHAR, distanceToArrival DOUBLE, type VARCHAR, "
           "services VARCHAR[], landingPads STRUCT(large INTEGER, medium INTEGER, small INTEGER))")
COLUMNS = {"id64": "BIGINT", "name": "VARCHAR", "coords": "STRUCT(x DOUBLE, y DOUBLE, z DOUBLE)",
           "stations": f"{STATION}[]", "bodies": f"STRUCT(stations {STATION}[])[]"}

SELECT = """WITH sys AS (
    SELECT * FROM read_json('{path}', format = 'array', columns = {columns},
                            maximum_object_size = 536870912)
),
st AS (
    SELECT id64, name, coords, unnest(stations) AS s FROM sys
    UNION ALL
    SELECT id64, name, coords, unnest(b.stations) AS s
    FROM (SELECT id64, name, coords, unnest(bodies) AS b FROM sys)
)
SELECT s.id AS id, s.name AS name, s.type AS type, id64 AS system_id64, name AS system_name,
       coords.x AS x, coords.y AS y, coords.z AS z, s.distanceToArrival AS distance_to_arrival,
       s.landingPads.large AS large_pads, s.landingPads.medium AS medium_pads,
       s.landingPads.small AS small_pads, s.services AS services,
       try_cast(s.updateTime AS TIMESTAMPTZ) AS update_time
FROM st"""


def fetch():
    return download(URL, RAW_NAME, min_bytes=MIN_BYTES)


def stage(con, path):
    fingerprint = list(validator(source_meta(RAW_NAME)))
    state = read_staged_state(RAW_NAME)
    if state.get("complete") and state.get("validator") == fingerprint:
        n = table_count(con, f"staging.{TABLE}")
        print(f"staging.{TABLE} already holds this download ({n:,} station(s))")
        return n
    write_staged_state(RAW_NAME, {"validator": fingerprint, "table": TABLE, "complete": False})
    print(f"parsing {path.name} ({path.stat().st_size / 1e9:,.1f} GB)...", flush=True)
    n = stage_json(con, TABLE, TABLE, dict(provenance=PROVENANCE, url=URL),
                   SELECT.format(path=path.as_posix(), columns=COLUMNS))
    if n < MIN_ROWS:
        raise SystemExit(f"staging.{TABLE} holds only {n:,} station(s) -- the dump did not parse")
    write_staged_state(RAW_NAME, {"validator": fingerprint, "table": TABLE, "complete": True, "rows": n})
    record_ingest(con, TABLE, TABLE, URL, path, n, False, PROVENANCE)
    carriers, uc, vista = con.execute(f"""
        SELECT count(*) FILTER (WHERE type = 'Drake-Class Carrier'),
               count(*) FILTER (WHERE list_contains(services, 'Universal Cartographics')),
               count(*) FILTER (WHERE list_contains(services, 'Vista Genomics'))
        FROM staging.{TABLE}""").fetchone()
    print(f"staging.{TABLE}: {n:,} station(s), {carriers:,} fleet carrier(s), "
          f"{uc:,} with Universal Cartographics, {vista:,} with Vista Genomics")
    return n


def main():
    path = fetch()
    con = connect(memory_limit="8GB", threads=8)
    try:
        stage(con, path)
    finally:
        con.close()
    print("DONE_STAGE_STATION")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()
