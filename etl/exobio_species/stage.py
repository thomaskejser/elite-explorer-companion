import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import INPUT, connect, run_sql_file, staging_file, table_count

CURATED = INPUT / "exobio_species.parquet"
TABLE = "staging.exobio_species_curated"
COLUMNS = "species, genus, species_key, genus_key, cr_value, colony_m"


def stage(con):
    if not CURATED.exists():
        sys.exit(f"missing {CURATED} -- it is authoritative and hand-edited. Restore it "
                 f"from git, or seed a fresh one with: python etl/exobio_species/seed.py")
    run_sql_file(con, staging_file("exobio_species_curated"))
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(f"TRUNCATE {TABLE}")
        con.execute(f"INSERT INTO {TABLE} ({COLUMNS}) "
                    f"SELECT {COLUMNS} FROM '{CURATED.as_posix()}'")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    n = table_count(con, TABLE)
    print(f"{TABLE}: {n:,} row(s) from {CURATED.name}")
    return n


def main():
    con = connect()
    try:
        stage(con)
    finally:
        con.close()
    print("DONE_STAGE_EXOBIO_SPECIES")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()
