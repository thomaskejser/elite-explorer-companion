import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.current import CURRENT_DB
from common.db import INPUT, connect

OUT = INPUT / "commander_alias.parquet"
COLUMNS = "system, canonical, system_id, asserted_utc"


def main():
    con = connect(read_only=True)
    try:
        con.execute(f"ATTACH '{CURRENT_DB.as_posix()}' AS cur (READ_ONLY)")
    except Exception as exc:
        raise SystemExit(f"cannot read {CURRENT_DB.name} ({exc}); stop ed-overlay.exe, which holds it, and run this again")
    con.execute(f"""CREATE TEMP TABLE incoming AS
        SELECT a.system, a.canonical, a.system_id, CAST(a.asserted_utc AS TIMESTAMPTZ) AS asserted_utc
        FROM cur.main.system_alias a
        WHERE a.system IN (SELECT system FROM main.system_catalog)""")
    fresh = con.execute("SELECT count(*) FROM incoming").fetchone()[0]
    sources = "SELECT * FROM incoming"
    before = 0
    if OUT.exists():
        before = con.execute(f"SELECT count(*) FROM '{OUT.as_posix()}'").fetchone()[0]
        sources = f"SELECT {COLUMNS} FROM '{OUT.as_posix()}' UNION ALL " + sources
    rows = con.execute(f"""
        SELECT {COLUMNS} FROM ({sources})
        QUALIFY row_number() OVER (PARTITION BY system ORDER BY asserted_utc DESC NULLS LAST, canonical) = 1
        ORDER BY system""").fetchall()
    con.execute(f"""COPY (
        SELECT {COLUMNS} FROM ({sources})
        QUALIFY row_number() OVER (PARTITION BY system ORDER BY asserted_utc DESC NULLS LAST, canonical) = 1
        ORDER BY system) TO '{OUT.as_posix()}' (FORMAT PARQUET)""")
    con.close()
    print(f"{fresh} commander alias(es) for catalogue stars in {CURRENT_DB.name}; "
          f"{OUT.name}: {before} -> {len(rows)} row(s)")
    for system, canonical, system_id, _ in rows:
        print(f"  {system:<20} -> {canonical}  ({system_id})")
    print("next: python etl/system_catalog/refresh.py, then python etl/system_unfound/refresh.py")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()
    print("DONE_EXPORT_COMMANDER_ALIASES")
