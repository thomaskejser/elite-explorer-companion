import sys, pathlib, importlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (connect, record_ingest, stage_json, staged_source,
                       table_count)
from common.sources import (download, read_staged_state, source_meta, validator,
                            write_staged_state)

known_stage = importlib.import_module("etl.system_known.stage")

EDASTRO = "https://edastro.com/mapcharts/files/"

FEEDS = [
    dict(role="edsm_celestial_body", table="edsm_bodies7days", schema="edsm_body",
         delta=True, provenance="bodies EDSM saw CHANGE in the last 7 days -- the only width it publishes",
         downloads=[("https://www.edsm.net/dump/bodies7days.json.gz",
                     "edsm_bodies7days.json.gz", 100_000)],
         columns=("system_id64", "body_no", "name", "type", "sub_type", "is_main_star",
                  "solar_masses", "earth_masses", "terraforming_state"),
         select="""SELECT TRY_CAST(systemId64 AS BIGINT)   AS system_id64,
                          TRY_CAST(bodyId AS INTEGER)      AS body_no,
                          name,
                          type,
                          subType                          AS sub_type,
                          TRY_CAST(isMainStar AS BOOLEAN)  AS is_main_star,
                          TRY_CAST(solarMasses AS DOUBLE)  AS solar_masses,
                          TRY_CAST(earthMasses AS DOUBLE)  AS earth_masses,
                          terraformingState                AS terraforming_state
                   FROM read_json_auto('{0}', ignore_errors=true)"""),
    dict(role="edastro_planet", table="edastro_planets7days", schema="edastro_planet",
         delta=True, provenance="planets EDAstro saw CHANGE in the last 7 days -- the only width it publishes",
         downloads=[(EDASTRO + "edastro_planets7days.jsonl.gz",
                     "edastro_planets7days.jsonl.gz", 100_000)],
         columns=("system_id64", "body_no", "name", "sub_type", "earth_masses",
                  "terraforming_state"),
         select="""SELECT TRY_CAST(systemId64 AS BIGINT)  AS system_id64,
                          TRY_CAST(bodyId AS INTEGER)     AS body_no,
                          name,
                          subType                         AS sub_type,
                          TRY_CAST(earthMasses AS DOUBLE) AS earth_masses,
                          terraformingState               AS terraforming_state
                   FROM read_json_auto('{0}', ignore_errors=true)"""),
    dict(role="edastro_known_rare", table="edastro_known_rare", schema="edastro_known_rare",
         delta=False, provenance="Black-Holes.csv and Wolf-Rayet-stars.csv, unioned.",
         downloads=[(EDASTRO + "Black-Holes.csv", "edastro_Black-Holes.csv", 1_000_000),
                    (EDASTRO + "Wolf-Rayet-stars.csv", "edastro_Wolf-Rayet-stars.csv",
                     1_000_000)],
         select="""SELECT system_name, body_name, kind, max(is_main_star) AS is_main_star,
                          any_value(mass_code) AS mass_code,
                          any_value(star_type) AS star_type,
                          min(scanned_at) AS scanned_at,
                          min(discovered_at) AS discovered_at
                   FROM (SELECT "System" AS system_name, "Star" AS body_name,
                                'black_hole' AS kind, "Main Star" = 'yes' AS is_main_star,
                                nullif("Mass Code", '') AS mass_code,
                                nullif("Type", '') AS star_type,
                                nullif("Timestamp", '') AS scanned_at,
                                nullif("EDSM Discovery Date", '') AS discovered_at
                         FROM read_csv('{0}', header=true, all_varchar=true,
                                       ignore_errors=true)
                         UNION ALL
                         SELECT "System", "Star", 'wolf_rayet', "Main Star" = 'yes',
                                nullif("Mass Code", ''), nullif("Type", ''),
                                nullif("Timestamp", ''), nullif("EDSM Discovery Date", '')
                         FROM read_csv('{1}', header=true, all_varchar=true,
                                       ignore_errors=true))
                   WHERE system_name IS NOT NULL AND system_name <> ''
                   GROUP BY system_name, body_name, kind"""),
    dict(role="edastro_neutron_star", table="edastro_neutron_stars",
         schema="edastro_neutron_star", delta=False, provenance="neutron-stars.csv.",
         downloads=[(EDASTRO + "neutron-stars.csv", "edastro_neutron-stars.csv",
                     1_000_000)],
         select="""SELECT TRY_CAST("ID64 SystemAddress" AS BIGINT)     AS system_id64,
                          "Name"                                      AS body_name,
                          TRY_CAST("Rotation Period Seconds" AS DOUBLE) AS rotation_period_s,
                          TRY_CAST("Region ID" AS INTEGER)            AS region_id,
                          TRY_CAST("X" AS DOUBLE) AS x,
                          TRY_CAST("Y" AS DOUBLE) AS y,
                          TRY_CAST("Z" AS DOUBLE) AS z
                   FROM read_csv('{0}', header=true, all_varchar=true,
                                 ignore_errors=true)"""),
]


def _exists(con, table, columns=()):
    have = {r[0] for r in con.execute("""SELECT column_name FROM duckdb_columns()
                                         WHERE schema_name = 'staging' AND table_name = ?""",
                                      [table]).fetchall()}
    return bool(have) and set(columns) <= have


def _stage_feed(con, feed, force):
    paths = [download(url, name, min_bytes=floor) for url, name, floor in feed["downloads"]]
    names = [name for _, name, _ in feed["downloads"]]
    fingerprint = [list(validator(source_meta(n))) for n in names]
    state = read_staged_state(names[0])
    table = feed["table"]
    if (state.get("complete") and state.get("validator") == fingerprint
            and _exists(con, table, feed.get("columns", ())) and not force):
        n = table_count(con, f"staging.{table}")
        print(f"    staging.{table} already holds this download ({n:,} rows)")
    else:
        write_staged_state(names[0], {"validator": fingerprint, "table": table,
                                      "complete": False})
        urls = ", ".join(url for url, _, _ in feed["downloads"])
        n = stage_json(con, table, feed["schema"],
                       dict(provenance=feed["provenance"], url=urls),
                       feed["select"].format(*[p.as_posix() for p in paths]))
        write_staged_state(names[0], {"validator": fingerprint, "table": table,
                                      "complete": True, "rows": n})
        print(f"    staging.{table}: {n:,} row(s)")
    record_ingest(con, feed["role"], table, feed["downloads"][0][0], paths[0], n,
                  feed["delta"], feed["provenance"])
    return n


def stage_spansh(con, window, force):
    if window:
        print(f"  spansh   [{window}] staging via etl/system_known/stage.py")
        known_stage.stage(con, window, ["spansh"], force)
        return
    row = staged_source(con, "spansh_body")
    if row:
        table, is_delta, at, rows = row
        print(f"  spansh   reusing staging.{table} ({(rows or 0):,} rows, "
              f"{'delta' if is_delta else 'FULL'}, staged {at:%Y-%m-%d %H:%M}) -- the "
              f"window etl/system_known/refresh.py last merged. --window W stages another.")
        return
    print("  spansh   nothing staged -- staging the window etl/system_known picks")
    known_stage.stage(con, None, ["spansh"], force)


def stage(con, window=None, force=False):
    con.execute("CREATE SCHEMA IF NOT EXISTS staging")
    stage_spansh(con, window, force)
    for feed in FEEDS:
        print(f"  {feed['role']}")
        _stage_feed(con, feed, force)


def clean(con, include_raw=False):
    raw = {r[0] for r in con.execute(
        """SELECT table_name FROM duckdb_tables()
           WHERE schema_name = 'staging' AND comment LIKE 'RAW SOURCE%'""").fetchall()}
    for (t,) in con.execute("""SELECT table_name FROM duckdb_tables()
                               WHERE schema_name = 'staging'
                               ORDER BY table_name""").fetchall():
        n = table_count(con, f"staging.{t}")
        if t in raw and not include_raw:
            print(f"  KEPT staging.{t} ({n:,} rows) -- RAW SOURCE, downloaded input")
            continue
        con.execute(f"TRUNCATE staging.{t}")
        print(f"  truncated staging.{t} ({n:,} rows removed, table kept)")


def _arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main():
    window = _arg("--window")
    if window and window not in known_stage.WINDOWS:
        raise SystemExit(f"--window must be one of {', '.join(known_stage.WINDOWS)}")
    con = connect()
    try:
        if "--clean-staging" in sys.argv:
            clean(con, "--include-raw" in sys.argv)
        else:
            stage(con, window, "--force" in sys.argv)
    finally:
        con.close()
    print("DONE_STAGE_SYSTEM_BODY")


if __name__ == "__main__":
    main()
