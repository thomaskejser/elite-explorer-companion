import sys, pathlib, uuid
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.current import (MODEL_DB, MODEL_SCHEMA, SEED_DB, SEED_INFO_TABLE,
                            apply_state_schema, connect)
from common.db import comment_file, run_sql_file
from etl.refresh_current import refresh


def previous_counts():
    if not SEED_DB.exists():
        return {}
    con = connect(read_only=True, path=SEED_DB)
    try:
        return {t: con.execute(f"SELECT count(*) FROM {MODEL_SCHEMA}.{t}").fetchone()[0]
                for (t,) in con.execute("""SELECT table_name FROM duckdb_tables()
                                           WHERE schema_name = ?""", [MODEL_SCHEMA]).fetchall()}
    finally:
        con.close()


def build(con, before):
    apply_state_schema(con)
    counts = refresh(con, SEED_DB.name)
    changed = [(t, was, n) for t, _, n in counts if (was := before.get(t)) is not None and was != n]
    if changed:
        print("\nagainst the previous seed:")
        for t, was, n in changed:
            print(f"  {t:<20}{n:>12,}   was {was:,}")
    con.execute(f"SET search_path='{MODEL_SCHEMA}'")
    run_sql_file(con, comment_file(SEED_INFO_TABLE))
    con.execute("SET search_path='main'")
    seed_id = uuid.uuid4().hex[:16]
    con.execute(f"INSERT INTO {MODEL_SCHEMA}.{SEED_INFO_TABLE} VALUES (?, now())", [seed_id])
    print(f"seed id {seed_id}")


def main():
    before = previous_counts()
    SEED_DB.parent.mkdir(exist_ok=True)
    work = SEED_DB.with_name(SEED_DB.stem + ".building.duckdb")
    work.unlink(missing_ok=True)
    print(f"source: {MODEL_DB} (read only)")
    con = connect(path=work)
    try:
        build(con, before)
        con.execute("CHECKPOINT")
    finally:
        con.close()
    work.replace(SEED_DB)
    print(f"{SEED_DB}: {SEED_DB.stat().st_size / 1e6:,.0f} MB")
    print("DONE_BUILD_SEED")


if __name__ == "__main__":
    from common.runlog import start
    start()
    main()
