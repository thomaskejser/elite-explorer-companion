import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (bind_role, connect, is_delta_window, model_gap_days,
                       record_ingest, stage_json, table_count, window_covering,
                       window_for_gap)
from common.sources import (RAW, download, read_staged_state, source_meta,
                            validator, write_staged_state)
from common import spansh

WINDOWS = ("1day", "7days", "1month", "full")

EDSM = {
    "7days": ("https://www.edsm.net/dump/systemsWithCoordinates7days.json.gz",
              "edsm_systemswithcoordinates7days",
              "systems EDSM saw CHANGE in the last 7 days"),
    "full": ("https://www.edsm.net/dump/systemsWithCoordinates.json.gz",
             "edsm_systemswithcoordinates",
             "EVERY system EDSM holds coordinates for"),
}

EDASTRO = {
    "7days": ("https://edastro.com/mapcharts/files/edastro_systems7days.jsonl.gz",
              "edastro_systems7days",
              "systems EDAstro saw CHANGE in the last 7 days -- the only width it publishes"),
}

EDSM_SELECT = """SELECT name, id, id64,
       {{'x': coords.x, 'y': coords.y, 'z': coords.z}} AS coords,
       CAST(date AS TIMESTAMP) AS date
FROM read_json_auto('{path}', ignore_errors=true)"""

EDASTRO_SELECT = """SELECT ID AS id, id64, name,
       {{'x': coords.x, 'y': coords.y, 'z': coords.z}} AS coords,
       CAST(region AS INTEGER)              AS region,
       mainStarType                         AS main_star_type,
       TRY_CAST(bodyCount AS INTEGER)       AS body_count,
       TRY_CAST(nonbodyCount AS INTEGER)    AS non_body_count,
       TRY_CAST(FSSprogress AS DOUBLE)      AS fss_progress,
       sol_dist, edsm_id, eddb_id, date_added,
       updateTime                           AS update_time
FROM read_json_auto('{path}', ignore_errors=true)"""


def _stage_feed(con, role, url, table, provenance, schema_name, select, window, force):
    name = f"{table}.json.gz"
    if adopt(con, window, name, table, force):
        record_ingest(con, role, table, url, None, table_count(con, f"staging.{table}"),
                      is_delta_window(window), provenance)
        bind_role(con, role, table)
        return table_count(con, f"staging.{table}")
    path = download(url, name, min_bytes=100_000)
    fingerprint = list(validator(source_meta(name)))
    state = read_staged_state(name)
    if state.get("complete") and state.get("validator") == fingerprint and not force:
        n = table_count(con, f"staging.{table}")
        print(f"    staging.{table} already holds this download ({n:,} rows)")
    else:
        write_staged_state(name, {"validator": fingerprint, "table": table,
                                  "complete": False})
        n = stage_json(con, table, schema_name,
                       dict(provenance=provenance, url=url),
                       select.format(path=path.as_posix()))
        write_staged_state(name, {"validator": fingerprint, "table": table,
                                  "complete": True, "rows": n})
        print(f"    staging.{table}: {n:,} row(s)")
    record_ingest(con, role, table, url, path, n, is_delta_window(window), provenance)
    bind_role(con, role, table)
    return n


def adopt(con, window, name, table, force):
    """Take an already-populated FULL staging table rather than downloading it again.

    Same rule as common.spansh.adopt and for the same reason: a catalogue is a snapshot
    and re-fetching it arrives at the same bytes, while a DELTA rewrites the same
    filename every day and must always be settled against the server.
    """
    if force or window != "full" or read_staged_state(name).get("validator"):
        return False
    if not con.execute("""SELECT count(*) FROM duckdb_tables()
                          WHERE schema_name='staging' AND table_name = ?""",
                       [table]).fetchone()[0]:
        return False
    n = table_count(con, f"staging.{table}")
    if not n:
        return False
    print(f"    *** ADOPTING staging.{table} AS THE CATALOGUE *** {n:,} rows already "
          f"staged, with no record of which download they came from, NOT validated "
          f"against the server. --force re-fetches.")
    return True


def pick(feed, window, gap):
    """Which window of `feed` to stage: the budget if one was given, else the gap."""
    return (window_covering(feed, WINDOWS, window) if window
            else window_for_gap(feed, gap))


def stage(con, window=None, only=None, force=False):
    only = set(only or ("spansh", "edsm", "edastro"))
    con.execute("CREATE SCHEMA IF NOT EXISTS staging")
    gap = None
    if not window:
        gap = model_gap_days(con)
        if gap is None:
            gap = float("inf")
            print("  no first_seen in main.system_known -- taking the full catalogue")
        else:
            print(f"  main.system_known last gained a row {gap:.2f} day(s) ago; "
                  f"asking each provider for the narrowest window that spans it")

    if "spansh" in only:
        w = pick(spansh.WINDOWS, window, gap)
        if w is None:
            print(f"  spansh   SKIPPED -- publishes no window at or below '{window}'")
        else:
            print(f"  spansh   [{w}]")
        if w == "full":
            print("    *** THE FULL CATALOGUE IS ~114 GB AND PARSES FOR HOURS. ***")
        if w is not None:
            t_sys, t_body = spansh.stage(con, w, force=force)
            url, provenance = spansh.WINDOWS[w]
            path = RAW / spansh.raw_name(w)
            for role, table in (("spansh_system", t_sys), ("spansh_body", t_body)):
                record_ingest(con, role, table, url, path,
                              table_count(con, f"staging.{table}"),
                              is_delta_window(w), provenance)
                bind_role(con, role, table)

    if "edsm" in only:
        w = pick(EDSM, window, gap)
        if w is None:
            print(f"  edsm     SKIPPED -- narrowest EDSM publishes is 7days, wider "
                  f"than the '{window}' budget")
        else:
            url, table, provenance = EDSM[w]
            print(f"  edsm     [{w}]")
            _stage_feed(con, "edsm_star_system", url, table, provenance,
                        "edsm_star_system", EDSM_SELECT, w, force)

    if "edastro" in only:
        w = pick(EDASTRO, window, gap)
        if w is None:
            print(f"  edastro  SKIPPED -- it publishes a 7-day window and nothing "
                  f"else, wider than the '{window}' budget")
        else:
            url, table, provenance = EDASTRO[w]
            print(f"  edastro  [{w}]")
            _stage_feed(con, "edastro_star_system", url, table, provenance,
                        "edastro_star_system", EDASTRO_SELECT, w, force)


def _arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main():
    window = _arg("--window")
    if window and window not in WINDOWS:
        raise SystemExit(f"--window must be one of {', '.join(WINDOWS)}")
    only = _arg("--only")
    con = connect()
    try:
        stage(con, window, only.split(",") if only else None, "--force" in sys.argv)
    finally:
        con.close()
    print("DONE_STAGE_SYSTEM_KNOWN")


if __name__ == "__main__":
    main()
