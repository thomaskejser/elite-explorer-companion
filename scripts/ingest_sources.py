"""Download every provider feed and stage it. One script, full automation.

    download -> staging -> merge -> main

This owns the FIRST arrow: it fetches each feed and lands it in `staging`. The `etl/`
builders own the second and merge staging into the model. Nothing here writes a model
table.

*** THE STAGING TABLE IS NAMED AFTER THE DOWNLOAD. *** Not after the role it plays:

    galaxy_1day.json.gz                 -> staging.spansh_galaxy_1day_body
    galaxy.json.gz                      -> staging.spansh_galaxy_body
    bodies7days.json.gz                 -> staging.edsm_bodies7days
    systemsWithCoordinates.json.gz      -> staging.edsm_systemswithcoordinates
    edastro_planets7days.jsonl.gz       -> staging.edastro_planets7days
    boxel-stats.csv                     -> staging.edastro_boxel_stats

The name therefore states WHAT WAS DOWNLOADED, so a 7-day slice can never be mistaken
for the full catalogue by reading its name -- which is the single most expensive class
of mistake in this project's history. `staging.edsm_bodies7days` cannot be misread the
way a table called `edsm_celestial_body` can.

*** THE MERGE RESOLVES THE TABLE BY ROLE, NOT BY HARDCODED NAME. *** Every ingest
records (role, staging_table) in staging.ingest_manifest, and builders ask
`common.db.staged(con, "spansh_body")` for the newest staged table filling that role.
So a builder does not care whether today's source was the full dump or a one-day delta:
it merges from whatever was last staged, and the manifest says exactly which file that
came from and when.

MERGE SEMANTICS MAKE DELTAS SAFE. The model merges -- insert unseen, update matched,
never drop -- so a system absent from a delta is not deleted, it simply did not change.
That is what makes a routine `--incremental` refresh correct rather than destructive.

*** A DELTA IS STILL NOT A CATALOGUE. *** Never fit a rate or quote a census from one:
`staging.spansh_galaxy_1day_body` holds the bodies that changed yesterday, so counting
black holes in it measures commander traffic, not the galaxy. Their comments say so in
capitals.

Usage:
    python scripts/ingest_sources.py --incremental              # all feeds, delta
    python scripts/ingest_sources.py --full                     # complete catalogues
    python scripts/ingest_sources.py --incremental --only spansh,edsm_star_system
    python scripts/ingest_sources.py --list                     # what is staged, how old
    ELITE_DB=...v2.duckdb python scripts/ingest_sources.py --incremental
"""
import datetime, os, pathlib, re, shutil, subprocess, sys, urllib.request

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
DB = pathlib.Path(os.environ.get("ELITE_DB") or (ROOT / "elite_mapping.duckdb"))
UA = {"User-Agent": "Mozilla/5.0 (elite_mapping ingest)"}

# role  = what the data IS, and what a builder asks for. Stable.
# table = what was DOWNLOADED, derived from the filename. Varies with full vs delta.
# kind  = json (read_json_auto) | csv (read_csv_auto) | sub (streaming parser)
SOURCES = {
 "spansh": dict(kind="sub", provider="spansh", roles=["spansh_system", "spansh_body"],
   full="https://downloads.spansh.co.uk/galaxy.json.gz",
   incr="https://downloads.spansh.co.uk/galaxy_1day.json.gz",
   note="Spansh galaxy dump, the ONLY body source at galaxy scale. Streamed by "
        "scripts/parse_spansh.py -- a JSON array with one system per line, never "
        "decompressed to disk."),
 "edsm_star_system": dict(kind="json", provider="edsm", roles=["edsm_star_system"],
   full="https://www.edsm.net/dump/systemsWithCoordinates.json.gz",
   incr="https://www.edsm.net/dump/systemsWithCoordinates7days.json.gz",
   note="EDSM systems with coordinates. Origin of most name/coordinate resolution and "
        "of the ~2.9M systems Spansh lacks."),
 "edsm_celestial_body": dict(kind="json", provider="edsm", roles=["edsm_celestial_body"],
   full=None, incr="https://www.edsm.net/dump/bodies7days.json.gz",
   note="EDSM bodies. *** NO FULL DUMP EXISTS *** -- EDSM publishes only a 7-day "
        "window. Superseded by spansh_body for body facts; kept for its richer structs."),
 "edsm_codex_entry": dict(kind="json", provider="edsm", roles=["edsm_codex_entry"],
   full="https://www.edsm.net/dump/codex.json.gz", incr=None,
   note="EDSM codex. FULL only. Source of NSP labels and Green Gas Giant rows."),
 "edastro_star_system": dict(kind="json", provider="edastro",
   roles=["edastro_star_system"], full=None,
   incr="https://edastro.com/mapcharts/files/edastro_systems7days.jsonl.gz",
   note="EDAstro systems. 7-DAY WINDOW ONLY. ~99.1% a SUBSET of EDSM, not a superset."),
 "edastro_star": dict(kind="json", provider="edastro", roles=["edastro_star"],
   full=None, incr="https://edastro.com/mapcharts/files/edastro_stars7days.jsonl.gz",
   note="EDAstro stars. 7-DAY WINDOW ONLY. For a full star census use "
        "edastro_known_rare / edastro_neutron_star, which ARE complete catalogues."),
 "edastro_planet": dict(kind="json", provider="edastro", roles=["edastro_planet"],
   full=None, incr="https://edastro.com/mapcharts/files/edastro_planets7days.jsonl.gz",
   note="EDAstro planets. 7-DAY WINDOW ONLY. Superseded by spansh_body; retains a "
        "materials struct Spansh lacks."),
 "edastro_point_of_interest": dict(kind="json", provider="edastro",
   roles=["edastro_point_of_interest"],
   full="https://edastro.com/gec/json/combined", incr=None,
   note="EDAstro Galactic Exploration Catalog, curated POIs. FULL, and small. GOTCHA: "
        "`name` is the POI's own nickname, NOT the system name -- joining on it "
        "inflates the 67 green-gas-giant systems to 117. Join on id64 only."),
 "canonn_codex_event": dict(kind="json", provider="canonn", roles=["canonn_codex_event"],
   full="https://storage.googleapis.com/canonn-downloads/codex.json.gz", incr=None,
   note="Canonn codex. FULL only. hud_category='Cloud' is the reliable Notable Stellar "
        "Phenomena flag and is broader than it sounds; 'Geology' needs a landing."),
 "edastro_boxel_stats": dict(kind="csv", provider="edastro", roles=["edastro_boxel_stats"],
   full="https://edastro.com/mapcharts/files/boxel-stats.csv", incr=None,
   note="EDAstro per-boxel aggregates. FULL, e/f/g/h ONLY. helium_avg aggregates "
        "SCANNED bodies, so it carries discovery bias. Drives p_hr."),
 "edastro_neutron_star": dict(kind="csv", provider="edastro", roles=["edastro_neutron_star"],
   full="https://edastro.com/mapcharts/files/neutron-stars.csv", incr=None,
   note="EDAstro neutron catalogue. FULL, not a slice. A NAVIGATION source -- neutrons "
        "stay valid targets, so this is never an exclusion signal."),
}

FULL = "--full" in sys.argv
INCR = "--incremental" in sys.argv
LIST = "--list" in sys.argv
ONLY = ({s.strip() for s in sys.argv[sys.argv.index("--only") + 1].split(",")}
        if "--only" in sys.argv else None)


def stem(url, provider):
    """staging table name from the DOWNLOAD, e.g.
    'https://.../galaxy_1day.json.gz' + spansh -> 'spansh_galaxy_1day'."""
    base = url.rstrip("/").rsplit("/", 1)[-1]
    base = re.sub(r"\.(json|jsonl|csv)(\.gz)?$", "", base, flags=re.I)
    base = re.sub(r"[^0-9A-Za-z]+", "_", base).strip("_").lower()
    if not base or base == "combined":          # GEC's URL ends /json/combined
        base = "gec_combined"
    return base if base.startswith(provider) else f"{provider}_{base}"


def fetch(url, dest, min_bytes=1000):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size >= min_bytes:
        print(f"    have {dest.name} ({dest.stat().st_size/1e6:,.1f} MB)", flush=True)
        return dest
    print(f"    GET {url}", flush=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=3600) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 22)
    tmp.replace(dest)
    print(f"    -> {dest.name} ({dest.stat().st_size/1e6:,.1f} MB)", flush=True)
    return dest


MANIFEST = """CREATE TABLE IF NOT EXISTS staging.ingest_manifest (
    role VARCHAR, staging_table VARCHAR, source_url VARCHAR, raw_file VARCHAR,
    raw_bytes BIGINT, row_count BIGINT, is_delta BOOLEAN,
    ingested_at_utc TIMESTAMPTZ, note VARCHAR)"""


def ensure_manifest(con):
    """Create the manifest, migrating the pre-role shape if it is there.

    The original manifest keyed on `table_name` alone, from when a source had exactly
    one possible staging table. Now that the table is named after the DOWNLOAD, a role
    can be filled by different tables over time (full dump today, delta tomorrow), so
    the key is (role, staging_table). Old rows are carried across rather than dropped:
    they record which file a table came from and when, which is the whole point of
    keeping a provenance ledger.
    """
    cols = [r[0] for r in con.execute(
        """SELECT column_name FROM duckdb_columns()
           WHERE schema_name='staging' AND table_name='ingest_manifest'""").fetchall()]
    if cols and "role" not in cols:
        print("  migrating staging.ingest_manifest to the (role, staging_table) shape")
        con.execute("ALTER TABLE staging.ingest_manifest RENAME TO ingest_manifest_v1")
        con.execute(MANIFEST)
        con.execute("""INSERT INTO staging.ingest_manifest
            SELECT table_name AS role, table_name AS staging_table, source_url, raw_file,
                   raw_bytes, row_count, false AS is_delta, ingested_at_utc, note
            FROM staging.ingest_manifest_v1""")
        n = con.execute("SELECT count(*) FROM staging.ingest_manifest").fetchone()[0]
        con.execute("DROP TABLE staging.ingest_manifest_v1")
        print(f"    carried {n} historical row(s) across")
    else:
        con.execute(MANIFEST)


def record(con, role, table, url, path, rows, is_delta, note):
    """One row per (role, staging_table). The manifest is how a builder finds its
    source, so this is not bookkeeping -- it is the lookup table for the merge."""
    ensure_manifest(con)
    con.execute("DELETE FROM staging.ingest_manifest WHERE role=? AND staging_table=?",
                [role, table])
    con.execute("INSERT INTO staging.ingest_manifest VALUES (?,?,?,?,?,?,?,?,?)",
                [role, table, url, str(path), path.stat().st_size, rows, is_delta,
                 datetime.datetime.now(datetime.timezone.utc), note])


def comment(con, table, note, is_delta):
    """RAW SOURCE marks a downloaded input so --clean-staging will not truncate it."""
    q = note.replace("'", "''")
    lead = ("RAW SOURCE (INCREMENTAL DELTA -- NOT a catalogue; only what changed in the "
            "last 1-7 days, so NEVER fit a rate or quote a census from it): "
            if is_delta else "RAW SOURCE (not a work table -- never drop or rebuild): ")
    con.execute(f"COMMENT ON TABLE staging.{table} IS '{lead}{q}'")


def bind_role(con, role):
    """Point staging.<role> at the newest staging table filling that role.

    The physical table is named after the DOWNLOAD (staging.spansh_galaxy_1day_body),
    which is what makes a delta impossible to misread as a catalogue. But 35 places in
    etl/ join by role, and rewriting each to interpolate a resolved name would put the
    lookup in 35 places and break silently wherever the SQL is not an f-string.

    So the role name becomes a VIEW, defined literally as SELECT * FROM the staged
    table. One definition, refreshed on every ingest, and `staging.ingest_manifest`
    plus `--list` say which physical table is behind it. A builder still merges "from
    the staging table" -- it just does not have to know today's filename.

    A role-named TABLE left over from the migration is renamed to its own
    download-derived name and registered, rather than dropped: it is the FULL
    catalogue, and a delta must never quietly destroy it.
    """
    newest = con.execute(
        """SELECT staging_table FROM staging.ingest_manifest
           WHERE role = ? ORDER BY ingested_at_utc DESC LIMIT 1""", [role]).fetchone()
    if not newest:
        return None
    tbl = newest[0]
    if tbl == role:
        return role
    kind = con.execute(
        """SELECT table_name FROM duckdb_tables()
           WHERE schema_name='staging' AND table_name = ?""", [role]).fetchone()
    if kind:
        legacy = f"{role}_superseded"
        con.execute(f"DROP TABLE IF EXISTS staging.{legacy}")
        con.execute(f"ALTER TABLE staging.{role} RENAME TO {legacy}")
        n = con.execute(f"SELECT count(*) FROM staging.{legacy}").fetchone()[0]
        print(f"    kept the previous full snapshot as staging.{legacy} ({n:,} rows)")
    con.execute(f"CREATE OR REPLACE VIEW staging.{role} AS SELECT * FROM staging.{tbl}")
    print(f"    staging.{role} -> VIEW over staging.{tbl}")
    return tbl


def connect():
    con = duckdb.connect(str(DB))
    con.execute("CREATE SCHEMA IF NOT EXISTS staging")
    for s in ("SET memory_limit='8GB'", "SET threads=8",
              "SET preserve_insertion_order=false", "SET enable_progress_bar=false"):
        con.execute(s)
    return con


def main():
    if not (FULL or INCR or LIST):
        sys.exit(__doc__.strip().split("Usage:")[-1])
    con = connect()
    print(f"database: {DB.name}\n")

    if LIST:
        ensure_manifest(con)
        print(f"  {'role':<28}{'staging table':<34}{'rows':>13} delta  ingested")
        for r in con.execute("""SELECT role, staging_table, row_count, is_delta,
            ingested_at_utc FROM staging.ingest_manifest
            ORDER BY role, ingested_at_utc DESC""").fetchall():
            print(f"  {r[0]:<28}{r[1]:<34}{(r[2] or 0):>13,} "
                  f"{'YES' if r[3] else ' - ':<6}{r[4]}")
        con.close()
        return

    mode = "incr" if INCR else "full"
    is_delta = INCR
    sub = "incr" if INCR else "full"

    for name, spec in [(k, v) for k, v in SOURCES.items() if not ONLY or k in ONLY]:
        url = spec.get(mode)
        if not url:
            other = "full" if mode == "incr" else "incremental"
            print(f"  {name}: no {mode} feed (provider publishes {other} only) -- skipped")
            continue
        base = stem(url, spec["provider"])
        print(f"  {name}  [{mode}]  -> staging.{base}", flush=True)

        if spec["kind"] == "sub":
            gz = fetch(url, RAW / sub / f"{base}.json.gz", min_bytes=1_000_000)
            print(f"    handing off to parse_spansh.py -> staging.{base}_system / "
                  f"{base}_body", flush=True)
            con.close()                       # the parser opens its own connection
            rc = subprocess.call(
                [sys.executable, str(ROOT / "scripts" / "parse_spansh.py"),
                 "--gz", str(gz), "--prefix", base],
                env={**os.environ, "ELITE_DB": str(DB)})
            if rc:
                sys.exit(f"parse_spansh.py failed with exit {rc}")
            con = connect()
            for role, tbl in zip(spec["roles"], (f"{base}_system", f"{base}_body")):
                n = con.execute(f"SELECT count(*) FROM staging.{tbl}").fetchone()[0]
                comment(con, tbl, spec["note"], is_delta)
                record(con, role, tbl, url, gz, n, is_delta, spec["note"])
                print(f"    staging.{tbl}: {n:,} rows  (role {role})")
                bind_role(con, role)
            continue

        ext = ".csv" if spec["kind"] == "csv" else (
            ".json.gz" if url.endswith(".gz") else ".json")
        path = fetch(url, RAW / sub / f"{base}{ext}")
        reader = "read_csv_auto" if spec["kind"] == "csv" else "read_json_auto"
        con.execute(f"""CREATE OR REPLACE TABLE staging.{base} AS
                        SELECT * FROM {reader}('{path.as_posix()}', ignore_errors=true)""")
        n = con.execute(f"SELECT count(*) FROM staging.{base}").fetchone()[0]
        comment(con, base, spec["note"], is_delta)
        record(con, spec["roles"][0], base, url, path, n, is_delta, spec["note"])
        print(f"    staging.{base}: {n:,} rows  (role {spec['roles'][0]})")
        bind_role(con, spec["roles"][0])

    con.close()
    print("\nDONE_INGEST")


if __name__ == "__main__":
    main()
