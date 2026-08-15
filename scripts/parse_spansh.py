"""Stream-parse the Spansh galaxy dump (galaxy.json.gz) into DuckDB.

The dump is a JSON array with ONE system object per line. We read the gzip
stream line-by-line, so the ~2TB decompressed form is never written to disk --
only the extracted, columnar body/system rows land in the DuckDB file.

Usage:
    python scripts/parse_spansh.py --test        # dry-run on partial file, no DB writes
    python scripts/parse_spansh.py               # full ingest into elite_mapping.duckdb

Resumable: a checkpoint file records how many input lines are committed; on
restart we skip that many lines (no re-parse) and continue.
"""
import gzip, io, orjson, duckdb, pathlib, sys, time, json

ROOT = pathlib.Path(__file__).resolve().parent.parent
GZ   = ROOT / "raw" / "spansh_galaxy.json.gz"
DB   = ROOT / "elite_mapping.duckdb"
CKPT = ROOT / "raw" / "spansh_parse.checkpoint"

TEST  = "--test" in sys.argv
LIMIT = 50_000 if TEST else None
FLUSH_BODIES = 400_000          # rows buffered before a DB insert

GEO = "$SAA_SignalType_Geological;"
BIO = "$SAA_SignalType_Biological;"

DDL_SYSTEM = """
CREATE TABLE IF NOT EXISTS spansh_system (
    system_id64 BIGINT, name VARCHAR, x DOUBLE, y DOUBLE, z DOUBLE,
    population BIGINT, declared_body_count INTEGER, scanned_body_count INTEGER,
    date TIMESTAMP
);"""
DDL_BODY = """
CREATE TABLE IF NOT EXISTS spansh_body (
    system_id64 BIGINT, body_id BIGINT, body_id64 BIGINT, name VARCHAR,
    type VARCHAR, sub_type VARCHAR, dist_to_arrival_ls DOUBLE, is_landable BOOLEAN,
    gravity DOUBLE, earth_masses DOUBLE, radius DOUBLE, surface_temp_k DOUBLE,
    surface_pressure DOUBLE, volcanism_type VARCHAR, atmosphere_type VARCHAR,
    terraforming_state VARCHAR, solar_masses DOUBLE, solar_radius DOUBLE,
    spectral_class VARCHAR, luminosity VARCHAR, absolute_magnitude DOUBLE,
    age BIGINT, main_star BOOLEAN, ring_count INTEGER, ring_types VARCHAR,
    signal_geology INTEGER, signal_biology INTEGER, genuses VARCHAR,
    update_time VARCHAR
);"""

SYS_COLS  = ["system_id64","name","x","y","z","population","declared_body_count","scanned_body_count","date"]
BODY_COLS = ["system_id64","body_id","body_id64","name","type","sub_type","dist_to_arrival_ls",
             "is_landable","gravity","earth_masses","radius","surface_temp_k","surface_pressure",
             "volcanism_type","atmosphere_type","terraforming_state","solar_masses","solar_radius",
             "spectral_class","luminosity","absolute_magnitude","age","main_star","ring_count",
             "ring_types","signal_geology","signal_biology","genuses","update_time"]


def body_row(sid, b):
    rings = b.get("rings") or []
    sig = b.get("signals") or {}
    sigmap = sig.get("signals") or {}
    genuses = sig.get("genuses")
    return (
        sid, b.get("bodyId"), b.get("id64"), b.get("name"),
        b.get("type"), b.get("subType"), b.get("distanceToArrival"), b.get("isLandable"),
        b.get("gravity"), b.get("earthMasses"), b.get("radius"), b.get("surfaceTemperature"),
        b.get("surfacePressure"), b.get("volcanismType"), b.get("atmosphereType"),
        b.get("terraformingState"), b.get("solarMasses"), b.get("solarRadius"),
        b.get("spectralClass"), b.get("luminosity"), b.get("absoluteMagnitude"),
        b.get("age"), b.get("mainStar"), len(rings),
        ",".join(sorted({r.get("type") for r in rings if r.get("type")})) or None,
        sigmap.get(GEO), sigmap.get(BIO),
        json.dumps(genuses) if genuses else None,
        b.get("updateTime"),
    )


def main():
    if not GZ.exists():
        print(f"missing {GZ}"); sys.exit(1)

    con = None
    if not TEST:
        con = duckdb.connect(str(DB))
        # System has ~32GB RAM but only ~10GB free; DuckDB's default 25GiB
        # buffer pool exhausts physical RAM and the OS kills us mid-run. Cap it
        # well under free RAM and let DuckDB spill to disk instead.
        con.execute("SET memory_limit='6GB'")
        con.execute("SET threads=4")
        con.execute(DDL_SYSTEM); con.execute(DDL_BODY)

    # Resume from ground truth: how many systems are already committed. Each
    # system is exactly one data line, so we skip that many data lines. This
    # cannot drift from the DB the way a side-file line counter can.
    skip_systems = 0
    if not TEST:
        skip_systems = con.execute("SELECT count(*) FROM spansh_system").fetchone()[0]
        if skip_systems:
            print(f"resuming: {skip_systems:,} systems already committed; skipping their lines")
    systems_skipped = 0

    sys_buf, body_buf = [], []
    n_lines = n_sys = n_bodies = 0
    flush_count = 0
    t0 = time.time()

    def flush():
        if TEST or (not body_buf and not sys_buf):
            return
        import pandas as pd
        # Atomic: systems and their bodies commit together or not at all, so the
        # committed spansh_system count is always a clean resume boundary.
        con.execute("BEGIN TRANSACTION")
        try:
            if sys_buf:
                df = pd.DataFrame(sys_buf, columns=SYS_COLS)
                con.register("sdf", df); con.execute("INSERT INTO spansh_system SELECT * FROM sdf"); con.unregister("sdf")
            if body_buf:
                df = pd.DataFrame(body_buf, columns=BODY_COLS)
                con.register("bdf", df); con.execute("INSERT INTO spansh_body SELECT * FROM bdf"); con.unregister("bdf")
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK"); raise
        sys_buf.clear(); body_buf.clear()
        nonlocal flush_count
        flush_count += 1
        if flush_count % 25 == 0:          # bound WAL + release buffer pool
            con.execute("CHECKPOINT")

    with gzip.open(GZ, "rb") as gzf:
        reader = io.BufferedReader(gzf, buffer_size=1 << 22)
        for raw in reader:
            n_lines += 1
            line = raw.strip()
            if not line or line in (b"[", b"]"):
                continue
            if systems_skipped < skip_systems:   # fast-forward past committed systems on resume
                systems_skipped += 1
                continue
            if line.endswith(b","):
                line = line[:-1]
            try:
                s = orjson.loads(line)
            except orjson.JSONDecodeError:
                # truncated final line of a partial download -> stop cleanly
                print(f"stopping at line {n_lines:,}: undecodable (likely partial file)")
                break
            sid = s.get("id64")
            c = s.get("coords") or {}
            bodies = s.get("bodies") or []
            sys_buf.append((sid, s.get("name"), c.get("x"), c.get("y"), c.get("z"),
                            s.get("population"), s.get("bodyCount"), len(bodies), s.get("date")))
            for b in bodies:
                if b.get("type") == "Barycentre":   # orbital placeholder, no physical data
                    continue
                body_buf.append(body_row(sid, b))
                n_bodies += 1
            n_sys += 1

            if len(body_buf) >= FLUSH_BODIES:
                flush()
            if n_sys % 200_000 == 0:
                el = time.time() - t0
                print(f"  {n_sys:,} systems  {n_bodies:,} bodies  "
                      f"{n_sys/el:,.0f} sys/s  {el/60:.1f} min")
            if LIMIT and n_sys >= LIMIT:
                print("test limit reached"); break

    flush()
    el = time.time() - t0
    print(f"\nDONE: {n_sys:,} systems, {n_bodies:,} bodies in {el/60:.1f} min "
          f"({n_bodies/max(el,1):,.0f} bodies/s)")

    if TEST:
        print("\n[TEST] sample extracted body rows:")
        for r in body_buf[:3] if body_buf else []:
            print("  ", r)
    else:
        con.close()


if __name__ == "__main__":
    main()
