import gzip
import io
import json
import time

import orjson
import pandas as pd

from common.db import run_staging_template, table_count
from common.sources import (download, read_staged_state, source_meta, validator,
                            write_staged_state)

WINDOWS = {
    "1day": ("https://downloads.spansh.co.uk/galaxy_1day.json.gz",
             "systems Spansh saw CHANGE in the last 24 hours"),
    "7days": ("https://downloads.spansh.co.uk/galaxy_7days.json.gz",
              "systems Spansh saw CHANGE in the last 7 days"),
    "1month": ("https://downloads.spansh.co.uk/galaxy_1month.json.gz",
               "systems Spansh saw CHANGE in the last 30 days"),
    "full": ("https://downloads.spansh.co.uk/galaxy.json.gz",
             "THE COMPLETE CATALOGUE, every system Spansh holds"),
}

FLUSH_BODIES = 400_000
GEO = "$SAA_SignalType_Geological;"
BIO = "$SAA_SignalType_Biological;"

SYS_COLS = ["system_id64", "name", "x", "y", "z", "population",
            "declared_body_count", "scanned_body_count", "date"]
BODY_COLS = ["system_id64", "body_id", "body_id64", "name", "type", "sub_type",
             "dist_to_arrival_ls", "is_landable", "gravity", "earth_masses", "radius",
             "surface_temp_k", "surface_pressure", "volcanism_type", "atmosphere_type",
             "terraforming_state", "solar_masses", "solar_radius", "spectral_class",
             "luminosity", "absolute_magnitude", "age", "main_star", "ring_count",
             "ring_types", "signal_geology", "signal_biology", "genuses", "update_time"]


def tables(window):
    base = "spansh_galaxy" if window == "full" else f"spansh_galaxy_{window}"
    return f"{base}_system", f"{base}_body"


def raw_name(window):
    return "galaxy.json.gz" if window == "full" else f"galaxy_{window}.json.gz"


def _body_row(sid, b):
    rings = b.get("rings") or []
    sig = b.get("signals") or {}
    sigmap = sig.get("signals") or {}
    genuses = sig.get("genuses")
    return (
        sid, b.get("bodyId"), b.get("id64"), b.get("name"),
        b.get("type"), b.get("subType"), b.get("distanceToArrival"), b.get("isLandable"),
        b.get("gravity"), b.get("earthMasses"), b.get("radius"),
        b.get("surfaceTemperature"), b.get("surfacePressure"), b.get("volcanismType"),
        b.get("atmosphereType"), b.get("terraformingState"), b.get("solarMasses"),
        b.get("solarRadius"), b.get("spectralClass"), b.get("luminosity"),
        b.get("absoluteMagnitude"), b.get("age"), b.get("mainStar"), len(rings),
        ",".join(sorted({r.get("type") for r in rings if r.get("type")})) or None,
        sigmap.get(GEO), sigmap.get(BIO),
        json.dumps(genuses) if genuses else None,
        b.get("updateTime"),
    )


def _parse(con, path, t_sys, t_body, skip):
    sys_buf, body_buf = [], []
    n_sys = n_bodies = flushes = 0
    t0 = time.time()

    def flush():
        nonlocal flushes
        if not sys_buf and not body_buf:
            return
        con.execute("BEGIN TRANSACTION")
        try:
            if sys_buf:
                con.register("sdf", pd.DataFrame(sys_buf, columns=SYS_COLS))
                con.execute(f"INSERT INTO staging.{t_sys} SELECT * FROM sdf")
                con.unregister("sdf")
            if body_buf:
                con.register("bdf", pd.DataFrame(body_buf, columns=BODY_COLS))
                con.execute(f"INSERT INTO staging.{t_body} SELECT * FROM bdf")
                con.unregister("bdf")
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        sys_buf.clear()
        body_buf.clear()
        flushes += 1
        if flushes % 25 == 0:
            con.execute("CHECKPOINT")

    skipped = 0
    with gzip.open(path, "rb") as gzf:
        for raw in io.BufferedReader(gzf, buffer_size=1 << 22):
            line = raw.strip()
            if not line or line in (b"[", b"]"):
                continue
            if skipped < skip:
                skipped += 1
                continue
            if line.endswith(b","):
                line = line[:-1]
            try:
                s = orjson.loads(line)
            except orjson.JSONDecodeError:
                print(f"    stopping: undecodable line after {n_sys:,} systems "
                      f"(a partial download)", flush=True)
                break
            sid = s.get("id64")
            c = s.get("coords") or {}
            bodies = [b for b in (s.get("bodies") or []) if b.get("type") != "Barycentre"]
            sys_buf.append((sid, s.get("name"), c.get("x"), c.get("y"), c.get("z"),
                            s.get("population"), s.get("bodyCount"), len(bodies),
                            s.get("date")))
            for b in bodies:
                body_buf.append(_body_row(sid, b))
            n_sys += 1
            n_bodies += len(bodies)
            if len(body_buf) >= FLUSH_BODIES:
                flush()
            if n_sys % 200_000 == 0:
                el = time.time() - t0
                print(f"    {n_sys:,} systems  {n_bodies:,} bodies  "
                      f"{n_sys/max(el,1):,.0f} sys/s  {el/60:.1f} min", flush=True)
    flush()
    el = time.time() - t0
    print(f"    parsed {n_sys:,} systems and {n_bodies:,} bodies in {el/60:.1f} min")
    return n_sys


def adopt(con, window, name, t_sys, t_body, force=False):
    """Take an already-parsed FULL catalogue as-is rather than fetching 114 GB again.

    Only for `full`, and only when there is no state file to check it against -- which is
    what a table parsed before the state file existed looks like. A DELTA is never
    adopted: the provider rewrites the same filename every day, so a delta table with no
    provenance beside it could be any window at all, and the download that settles the
    question costs minutes rather than hours.
    """
    if force or window != "full" or read_staged_state(name).get("validator"):
        return False
    n = table_count(con, f"staging.{t_sys}")
    if not n:
        return False
    print(f"    *** ADOPTING staging.{t_sys} / {t_body} AS THE CATALOGUE ***")
    print(f"    {n:,} systems and {table_count(con, f'staging.{t_body}'):,} bodies "
          f"already parsed, with no record of which download they came from.")
    print(f"    NOT validated against the server. Delete raw/{name}.staged.json's "
          f"table or pass --force to re-fetch.")
    return True


def stage(con, window="1day", force=False):
    if window not in WINDOWS:
        raise SystemExit(f"no Spansh '{window}' window -- have {', '.join(WINDOWS)}")
    url, provenance = WINDOWS[window]
    name = raw_name(window)
    t_sys, t_body = tables(window)
    fields = dict(provenance=provenance, url=url)
    run_staging_template(con, "spansh_galaxy_system", table=t_sys, **fields)
    run_staging_template(con, "spansh_galaxy_body", table=t_body, **fields)

    if adopt(con, window, name, t_sys, t_body, force):
        return t_sys, t_body

    path = download(url, name, min_bytes=1_000_000)

    fingerprint = list(validator(source_meta(name)))
    state = read_staged_state(name)
    same_file = state.get("validator") == fingerprint

    if same_file and state.get("complete") and not force:
        print(f"    staging.{t_sys} already holds this download "
              f"({table_count(con, f'staging.{t_sys}'):,} systems)")
        return t_sys, t_body

    if not same_file:
        con.execute(f"TRUNCATE staging.{t_sys}")
        con.execute(f"TRUNCATE staging.{t_body}")
        skip = 0
        print(f"    parsing {name} into staging.{t_sys} / {t_body}", flush=True)
    else:
        skip = table_count(con, f"staging.{t_sys}")
        print(f"    resuming {name}: {skip:,} systems already committed", flush=True)

    write_staged_state(name, {"validator": fingerprint, "table": t_sys,
                              "complete": False})
    _parse(con, path, t_sys, t_body, skip)
    write_staged_state(name, {"validator": fingerprint, "table": t_sys,
                              "complete": True,
                              "rows": table_count(con, f"staging.{t_sys}")})
    return t_sys, t_body
