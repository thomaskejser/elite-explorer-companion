import sys, pathlib, json, time, urllib.request, urllib.error
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import connect, record_ingest, run_sql_file, staging_file
from common.sources import RAW

URL = "https://spansh.co.uk/api/stations/search"
NAME = "spansh_station_service"
TABLE = f"staging.{NAME}"
RAW_NAME = f"{NAME}.jsonl"
PAGE = 500
RESULT_CAP = 10000
MIN_ROWS = 1000
RETRIES = 4
BACKOFF = 5
DROP_FIELDS = ("market", "modules", "ships", "economies", "export_commodities",
               "import_commodities", "prohibited_commodities", "system_power",
               "distance")
UA = {"User-Agent": "elite-explorer-companion/1.0 (+https://github.com/)",
      "Content-Type": "application/json"}

FILTERS = [("material_trader", ["Encoded", "Manufactured", "Raw"]),
           ("technology_broker", ["Human", "Guardian"])]

COLUMNS = """
    market_id, id, name, type, system_id64, system_name, system_x, system_y, system_z,
    system_population, distance_to_arrival, is_planetary, body_id64, body_name,
    body_type, body_subtype, latitude, longitude, has_large_pad, large_pads,
    medium_pads, small_pads, has_market, has_outfitting, has_shipyard, material_trader,
    technology_broker, services, primary_economy, secondary_economy, government,
    allegiance, updated_at
"""

SELECT = f"""
    SELECT {COLUMNS}
    FROM (SELECT *, row_number() OVER (PARTITION BY market_id
                                       ORDER BY material_trader IS NULL,
                                                technology_broker IS NULL) AS pick
          FROM (SELECT r.* REPLACE (list_transform(r.services, s -> s.name) AS services)
                FROM read_json('{{path}}',
                               format='newline_delimited',
                               columns={{{{
                                   market_id: 'BIGINT', id: 'VARCHAR', name: 'VARCHAR',
                                   type: 'VARCHAR', system_id64: 'BIGINT',
                                   system_name: 'VARCHAR', system_x: 'DOUBLE',
                                   system_y: 'DOUBLE', system_z: 'DOUBLE',
                                   system_population: 'BIGINT',
                                   distance_to_arrival: 'DOUBLE',
                                   is_planetary: 'BOOLEAN', body_id64: 'BIGINT',
                                   body_name: 'VARCHAR', body_type: 'VARCHAR',
                                   body_subtype: 'VARCHAR', latitude: 'DOUBLE',
                                   longitude: 'DOUBLE', has_large_pad: 'BOOLEAN',
                                   large_pads: 'BIGINT', medium_pads: 'BIGINT',
                                   small_pads: 'BIGINT', has_market: 'BOOLEAN',
                                   has_outfitting: 'BOOLEAN', has_shipyard: 'BOOLEAN',
                                   material_trader: 'VARCHAR',
                                   technology_broker: 'VARCHAR',
                                   services: 'STRUCT(name VARCHAR)[]',
                                   primary_economy: 'VARCHAR',
                                   secondary_economy: 'VARCHAR',
                                   government: 'VARCHAR', allegiance: 'VARCHAR',
                                   updated_at: 'TIMESTAMP'}}}}) r))
    WHERE pick = 1
"""


def _post(body):
    req = urllib.request.Request(URL, json.dumps(body).encode(), UA)
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == RETRIES - 1:
                raise
            print(f"  {URL} returned HTTP {exc.code}; retrying in "
                  f"{BACKOFF * (attempt + 1)}s", flush=True)
            time.sleep(BACKOFF * (attempt + 1))


def _pull(flt, values):
    rows, page, reported = [], 0, None
    while True:
        d = _post({"filters": {flt: {"value": values}}, "size": PAGE, "page": page})
        if reported is None:
            reported = d.get("count")
            if reported == RESULT_CAP:
                raise SystemExit(
                    f"{URL} reported exactly {RESULT_CAP} rows for filter '{flt}'. That "
                    f"is the result cap, which is what an IGNORED filter returns -- the "
                    f"API accepts an unknown filter name silently. Refusing to stage a "
                    f"pull that may be the unfiltered galaxy.")
        got = d.get("results") or []
        rows += got
        if len(rows) >= reported or not got:
            break
        page += 1
    if len(rows) != reported:
        raise SystemExit(f"pulled {len(rows):,} row(s) for filter '{flt}' but the API "
                         f"reported {reported:,} -- refusing to stage a partial pull")
    print(f"  {flt}: {len(rows):,} row(s) in {page + 1} request(s)")
    return rows


def fetch():
    rows = []
    for flt, values in FILTERS:
        rows += _pull(flt, values)
    if len(rows) < MIN_ROWS:
        raise SystemExit(f"{URL} returned only {len(rows):,} row(s) in total -- "
                         f"refusing to replace raw/{RAW_NAME}")
    dest = RAW / RAW_NAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    with open(part, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps({k: v for k, v in row.items()
                                if k not in DROP_FIELDS}) + "\n")
    part.replace(dest)
    print(f"  -> {RAW_NAME} ({len(rows):,} row(s), {dest.stat().st_size / 1e6:,.1f} MB)")
    return dest


def _drop_view(con, name):
    if con.execute("""SELECT count(*) FROM duckdb_views()
                      WHERE schema_name = 'staging' AND view_name = ?""",
                   [name]).fetchone()[0]:
        con.execute(f"DROP VIEW staging.{name}")


def stage(con, path=None):
    path = path or fetch()
    _drop_view(con, NAME)
    run_sql_file(con, staging_file(NAME))
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"TRUNCATE {TABLE}")
        con.execute(f"INSERT INTO {TABLE} "
                    + SELECT.format(path=path.as_posix()))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    n, traders, brokers, both, unresolved = con.execute(f"""
        SELECT count(*),
               count(*) FILTER (material_trader IS NOT NULL),
               count(*) FILTER (technology_broker IS NOT NULL),
               count(*) FILTER (material_trader IS NOT NULL
                                AND technology_broker IS NOT NULL),
               count(*) FILTER (NOT EXISTS (SELECT 1 FROM main.system_known k
                                            WHERE k.system_id = s.system_id64))
        FROM {TABLE} s""").fetchone()
    print(f"{TABLE}: {n:,} station(s), {traders:,} material trader(s), "
          f"{brokers:,} technology broker(s), {both:,} carrying both")
    if unresolved:
        print(f"  {unresolved:,} station(s) whose system_id64 is not in "
              f"main.system_known -- they cannot be joined to the model")
    record_ingest(con, NAME, NAME, URL, path, n, False,
                  "Spansh station search, filtered to Material Trader and Technology "
                  "Broker. A FILTERED QUERY, NOT A DUMP: no ETag or Last-Modified "
                  "exists, so every run re-pulls and the row count is checked against "
                  "the count the API reports.")
    return n


def main():
    path = fetch()
    con = connect()
    try:
        stage(con, path)
    finally:
        con.close()
    print("DONE_STAGE_STATION_SERVICE")


if __name__ == "__main__":
    main()
