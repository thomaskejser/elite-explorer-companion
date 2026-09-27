import re
import sys, pathlib, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (DB, apply_comment_file, check_references, comment_file, connect,
                       run_sql_file, table_count, transform_file)

NEW = DB.with_name(DB.stem + "_fresh.duckdb")
KEEP = DB.with_name(DB.stem + "_pre_fresh.duckdb")
DONE = "staging.fresh_build_done"
MAP = "staging.sector_rekey"
STAGED_SK = "staging.fresh_system_known"
SK_BATCHES = "staging.fresh_system_known_batches"
WORK = (DONE, MAP, STAGED_SK, SK_BATCHES)

SKIP_MAIN = {"system_known_pre_rekey"}
KEEP_STAGING = {"ingest_manifest", "catalog_parallax",
                "pred_snapshot_20260829", "scanned_before_20260829",
                "pred_snapshot_20260925", "scanned_before_20260925"}
REKEYED = {"sector": "sector_id", "system_known": "sector_id", "system_unfound": "sector_id"}
DROPPED = {"system_body": {"system_body_id"}, "system_predicted": {"p_hr"}}
RESHAPED = {"system_body"}
BODY_BUCKETS, BODY_THREADS, THREADS = 64, 4, 8
SOURCE_RANK = """CASE source WHEN 'spansh' THEN 1 WHEN 'edsm' THEN 2 WHEN 'edastro' THEN 3
                     WHEN 'edastro_neutron' THEN 4 WHEN 'edastro_rare' THEN 5 ELSE 6 END"""
BATCH_ROWS = 8_000_000
SK_BATCH_ROWS = 4_000_000
MEMORY = "4GB"

MAP_SQL = f"""
CREATE OR REPLACE TABLE {MAP} AS
WITH c AS (
    SELECT sector_id AS old_id, mode(sector_id_from_id64(system_id)) AS cell
    FROM old.main.system_known
    WHERE system_id > 0 AND sector_id <> 0
    GROUP BY 1
),
ruled AS (
    SELECT o.sector_id AS old_id, o.sector, o.is_crafted AS old_crafted, c.cell,
           t.sector_id AS published,
           CASE WHEN o.sector_id = 0 THEN 0
                WHEN t.sector_id >= 0 AND c.cell IS NOT NULL THEN c.cell
                WHEN t.sector_id > 0 THEN t.sector_id
           END AS ruled_id
    FROM old.main.sector o
    LEFT JOIN c ON c.old_id = o.sector_id
    LEFT JOIN transform.sector t ON t.sector = o.sector
)
SELECT old_id, sector, old_crafted, cell, published,
       coalesce(ruled_id,
                CASE WHEN NOT old_crafted AND cell IS NOT NULL
                          AND NOT EXISTS (SELECT 1 FROM ruled r WHERE r.ruled_id = ruled.cell)
                          AND (SELECT count(*) FROM ruled r
                               WHERE r.ruled_id IS NULL AND r.cell = ruled.cell) = 1
                     THEN cell
                     ELSE sector_id_from_name(sector) END) AS new_id
FROM ruled"""


def done(con, name):
    return con.execute(f"SELECT count(*) FROM {DONE} WHERE step = ?", [name]).fetchone()[0]


def step(con, name, fn):
    if done(con, name):
        return False
    t0 = time.time()
    con.execute("BEGIN TRANSACTION")
    try:
        fn()
        con.execute(f"INSERT INTO {DONE} VALUES (?, now())", [name])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    print(f"    {name:<52}{time.time()-t0:>7.0f}s", flush=True)
    return True


def columns(con, catalog, schema, table):
    return [r[0] for r in con.execute(
        """SELECT column_name FROM duckdb_columns()
           WHERE database_name = ? AND schema_name = ? AND table_name = ?
           ORDER BY column_index""", [catalog, schema, table]).fetchall()]


def tables(con, catalog, schema):
    return con.execute(
        """SELECT table_name, coalesce(comment, '') FROM duckdb_tables()
           WHERE database_name = ? AND schema_name = ? ORDER BY table_name""",
        [catalog, schema]).fetchall()


def quote(text):
    return "'" + text.replace("'", "''") + "'"


def copy_batched(con, target, source, select="*", join="", alias="s"):
    rows = table_count(con, source)
    top = con.execute(f"SELECT max(rowid) FROM {source}").fetchone()[0]
    if not rows or top is None:
        return
    batches = max(1, -(-rows // BATCH_ROWS))
    width = top // batches + 1
    for b in range(batches):
        lo, hi = b * width, (b + 1) * width
        step(con, f"copy {target} {b + 1}/{batches}",
             lambda lo=lo, hi=hi: con.execute(
                 f"""INSERT INTO {target} BY NAME
                     SELECT {select} FROM {source} {alias} {join}
                     WHERE {alias}.rowid >= {lo} AND {alias}.rowid < {hi}"""))
        if (b + 1) % 8 == 0:
            con.execute("CHECKPOINT")


def copy_comments(con, schema, table):
    comment = con.execute("""SELECT comment FROM duckdb_tables() WHERE database_name='old'
                             AND schema_name = ? AND table_name = ?""",
                          [schema, table]).fetchone()[0]
    if comment:
        con.execute(f"COMMENT ON TABLE {schema}.{table} IS {quote(comment)}")
    for col, text in con.execute(
            """SELECT column_name, comment FROM duckdb_columns() WHERE database_name='old'
               AND schema_name = ? AND table_name = ? AND comment IS NOT NULL""",
            [schema, table]).fetchall():
        con.execute(f'COMMENT ON COLUMN {schema}.{table}."{col}" IS {quote(text)}')


def copy_staging(con):
    print("\nstaging: RAW SOURCE tables and the ones nothing rebuilds", flush=True)
    kept = []
    for table, comment in tables(con, "old", "staging"):
        if not (comment.startswith("RAW SOURCE") or table in KEEP_STAGING):
            continue
        kept.append(table)
        step(con, f"create staging.{table}", lambda t=table: con.execute(
            f"CREATE TABLE staging.{t} AS SELECT * FROM old.staging.{t} LIMIT 0"))
        copy_batched(con, f"staging.{table}", f"old.staging.{table}")
        step(con, f"comment staging.{table}", lambda t=table: copy_comments(con, "staging", t))

    for view, sql in con.execute("""SELECT view_name, sql FROM duckdb_views()
                                    WHERE database_name='old' AND schema_name='staging'
                                    ORDER BY view_name""").fetchall():
        target = re.search(r"FROM staging\.(\w+)", sql)
        if target and target.group(1) in kept:
            con.execute(sql.rstrip().rstrip(";").replace(
                "CREATE VIEW", "CREATE OR REPLACE VIEW", 1))
    return kept


def create_main(con, table):
    def create():
        apply_comment_file(con, comment_file(table))
        lost = (set(columns(con, "old", "main", table))
                - set(columns(con, NEW.stem, "main", table)) - DROPPED.get(table, set()))
        if lost:
            raise SystemExit(f"schema/{table}.sql has no column {sorted(lost)} -- the copy "
                             f"would drop it. Fix the schema file first.")
    step(con, f"create main.{table}", create)


def build_map(con):
    def build():
        run_sql_file(con, transform_file("sector"))
        con.execute(MAP_SQL)
        n, distinct, zero = con.execute(f"""
            SELECT count(*), count(DISTINCT new_id),
                   count(*) FILTER (WHERE new_id = 0) FROM {MAP}""").fetchone()
        if n != distinct or zero != 1:
            raise SystemExit(f"sector map is not one-to-one: {n:,} sectors, {distinct:,} ids, "
                             f"{zero} at id 0")
        con.execute(f"""COMMENT ON TABLE {MAP} IS 'WORK TABLE for scripts/build_fresh_db.py:
the surrogate sector_id each sector holds in the source file, and the game-derived id it
takes in the new one. Dropped by --swap.'""")
    step(con, "sector map", build)
    for sector, old_crafted, new_id in con.execute(f"""
            SELECT sector, old_crafted, new_id FROM {MAP}
            WHERE old_id <> 0 AND old_crafted IS DISTINCT FROM (new_id < 0)
            ORDER BY sector""").fetchall():
        print(f"    is_crafted {old_crafted!s:<5} -> {new_id < 0!s:<5} {sector}")


def copy_sector(con):
    cols = columns(con, "old", "main", "sector")
    select = ", ".join("m.new_id AS sector_id" if c == "sector_id"
                       else "(m.new_id <= 0) AS is_crafted" if c == "is_crafted"
                       else f"s.{c}" for c in cols)
    step(con, "copy main.sector", lambda: con.execute(
        f"""INSERT INTO main.sector BY NAME SELECT {select}
            FROM old.main.sector s JOIN {MAP} m ON m.old_id = s.sector_id"""))


def copy_unfound(con):
    cols = columns(con, "old", "main", "system_unfound")
    select = ", ".join("m.new_id AS sector_id" if c == "sector_id" else f"s.{c}" for c in cols)
    step(con, "copy main.system_unfound", lambda: con.execute(
        f"""INSERT INTO main.system_unfound BY NAME SELECT {select}
            FROM old.main.system_unfound s LEFT JOIN {MAP} m ON m.old_id = s.sector_id"""))


def sk_batches(con):
    rows = con.execute(f"""SELECT sector_id, count(*) FROM {STAGED_SK}
                           GROUP BY 1 ORDER BY 1""").fetchall()
    out, lo, run = [], rows[0][0], 0
    for sector_id, n in rows:
        run += n
        if run >= SK_BATCH_ROWS:
            out.append((lo, sector_id + 1))
            lo, run = sector_id + 1, 0
    if run:
        out.append((lo, rows[-1][0] + 1))
    return out


def copy_system_known(con):
    step(con, f"create {STAGED_SK}", lambda: con.execute(
        f"CREATE TABLE {STAGED_SK} AS SELECT * FROM old.main.system_known LIMIT 0"))
    copy_batched(con, STAGED_SK, "old.main.system_known",
                 select="s.* REPLACE (m.new_id AS sector_id)",
                 join=f"JOIN {MAP} m ON m.old_id = s.sector_id")

    def plan():
        staged, source = table_count(con, STAGED_SK), table_count(con, "old.main.system_known")
        if staged != source:
            raise SystemExit(f"{STAGED_SK} holds {staged:,} rows, the source {source:,}")
        con.execute(f"CREATE TABLE {SK_BATCHES} (lo BIGINT, hi BIGINT)")
        con.executemany(f"INSERT INTO {SK_BATCHES} VALUES (?, ?)", sk_batches(con))
    step(con, "plan system_known batches", plan)

    batches = con.execute(f"SELECT lo, hi FROM {SK_BATCHES} ORDER BY lo").fetchall()
    for i, (lo, hi) in enumerate(batches, 1):
        step(con, f"copy main.system_known {i}/{len(batches)}",
             lambda lo=lo, hi=hi: con.execute(
                 f"""INSERT INTO main.system_known BY NAME SELECT * FROM {STAGED_SK}
                     WHERE sector_id >= {lo} AND sector_id < {hi}
                     ORDER BY sector_id, system_id"""))
        if i % 8 == 0:
            con.execute("CHECKPOINT")

    step(con, f"drop {STAGED_SK}", lambda: con.execute(f"DROP TABLE {STAGED_SK}"))


def copy_system_body(con):
    cols = [c for c in columns(con, NEW.stem, "main", "system_body") if c != "body_no"]
    select = ", ".join(f"o.{c}" for c in cols)
    bucket = "abs((({c}) >> 3) % {n}) = {b}"
    con.execute(f"SET threads={BODY_THREADS}")
    for b in range(BODY_BUCKETS):
        step(con, f"copy main.system_body {b + 1}/{BODY_BUCKETS}", lambda b=b: con.execute(f"""
            INSERT INTO main.system_body BY NAME
            WITH sp AS (
                SELECT g.system_id64 AS system_id,
                       CASE WHEN starts_with(g.name, s.name)
                            THEN trim(substr(g.name, length(s.name) + 1))
                            ELSE g.name END AS system_body,
                       min(g.body_id) AS body_no
                FROM staging.spansh_galaxy_body g
                JOIN staging.spansh_galaxy_system s ON s.system_id64 = g.system_id64
                WHERE {bucket.format(c='g.system_id64', n=BODY_BUCKETS, b=b)}
                  AND {bucket.format(c='s.system_id64', n=BODY_BUCKETS, b=b)}
                  AND g.name IS NOT NULL AND g.body_id IS NOT NULL
                GROUP BY 1, 2
            ),
            ranked AS (
                SELECT {select}, coalesce(sp.body_no, -1) AS body_no,
                       row_number() OVER (PARTITION BY o.system_id, o.system_body
                                          ORDER BY {SOURCE_RANK.replace('source', 'o.source')},
                                                   o.system_body_id) AS rn
                FROM old.main.system_body o
                LEFT JOIN sp ON sp.system_id = o.system_id AND sp.system_body = o.system_body
                WHERE {bucket.format(c='o.system_id', n=BODY_BUCKETS, b=b)}
            )
            SELECT * EXCLUDE (rn) FROM ranked WHERE rn = 1"""))
        if (b + 1) % 8 == 0:
            con.execute("CHECKPOINT")
    con.execute(f"SET threads={THREADS}")


def copy_main(con):
    print("\nmain: created from schema/, rows copied, sector re-keyed", flush=True)
    names = [t for t, _ in tables(con, "old", "main") if t not in SKIP_MAIN]
    for table in names:
        create_main(con, table)
    build_map(con)
    copy_sector(con)
    copy_unfound(con)
    for table in names:
        if table not in REKEYED and table not in RESHAPED:
            copy_batched(con, f"main.{table}", f"old.main.{table}",
                         select=", ".join(f's."{c}"' for c in columns(con, "old", "main", table)
                                          if c not in DROPPED.get(table, set())))
    copy_system_known(con)
    copy_system_body(con)

    for view in [v for (v,) in con.execute("""SELECT view_name FROM duckdb_views()
                                              WHERE database_name='old'
                                                AND schema_name='main'""").fetchall()]:
        step(con, f"view main.{view}", lambda v=view: apply_comment_file(con, comment_file(v)))
    return names


def checksums(con, catalog, schema, table, cols):
    select = ", ".join(f'sum(hash("{c}"))' for c in cols)
    return con.execute(f"SELECT count(*), {select} FROM {catalog}.{schema}.{table}").fetchone()


def verify_table(con, schema, table):
    cols = [c for c in columns(con, "old", schema, table) if c != REKEYED.get(table)
            and c not in DROPPED.get(table, set())
            and not (table == "sector" and c == "is_crafted")]
    a, b = checksums(con, "old", schema, table, cols), checksums(con, NEW.stem, schema, table, cols)
    print(f"      {schema}.{table:<40}{b[0]:>14,}  {'ok' if a == b else '<== DIFFERS'}", flush=True)
    if a != b:
        raise SystemExit(f"{schema}.{table} differs from the source")


def verify_sectors(con):
    name_counts = """SELECT CASE WHEN k.sector_id = 0 THEN '' ELSE s.sector END, count(*)
                     FROM {c}.main.system_known k LEFT JOIN {c}.main.sector s
                     ON s.sector_id = k.sector_id GROUP BY 1"""
    moved = con.execute(f"""SELECT count(*) FROM (
        ({name_counts.format(c='old')} EXCEPT {name_counts.format(c=NEW.stem)})
        UNION ALL
        ({name_counts.format(c=NEW.stem)} EXCEPT {name_counts.format(c='old')}))""").fetchone()[0]
    crafted = con.execute("""SELECT count(*) FROM main.sector
                             WHERE sector_id <> 0 AND is_crafted <> (sector_id < 0)""").fetchone()[0]
    print(f"      sectors whose system count changed across the re-key: {moved}; "
          f"is_crafted disagreeing with the sign of sector_id: {crafted}", flush=True)
    if moved or crafted:
        raise SystemExit("the sector re-key moved systems or broke is_crafted")


def verify_system_body(con):
    bucket = "abs(((system_id) >> 3) % {n}) = {b}"
    old_n = old_h = new_n = new_h = unknown = dup = 0
    con.execute(f"SET threads={BODY_THREADS}")
    try:
        for b in range(BODY_BUCKETS):
            w = bucket.format(n=BODY_BUCKETS, b=b)
            n, h = con.execute(f"""SELECT count(*), coalesce(sum(hash(system_id, system_body)), 0)
                                   FROM (SELECT DISTINCT system_id, system_body
                                         FROM old.main.system_body WHERE {w})""").fetchone()
            old_n, old_h = old_n + n, old_h + h
            n, h, u, d = con.execute(f"""
                SELECT count(*), coalesce(sum(hash(system_id, system_body)), 0),
                       count(*) FILTER (WHERE body_no = -1),
                       count(*) - count(DISTINCT (system_id, system_body))
                FROM main.system_body WHERE {w}""").fetchone()
            new_n, new_h, unknown, dup = new_n + n, new_h + h, unknown + u, dup + d
    finally:
        con.execute(f"SET threads={THREADS}")
    ok = old_n == new_n and old_h == new_h and not dup
    print(f"      main.system_body {new_n:,} rows, one per distinct (system, designation) in the "
          f"source ({old_n:,}): {'ok' if ok else '<== DIFFERS'}; {unknown:,} with body_no -1; "
          f"{dup} repeated designations", flush=True)
    for source, n, k in con.execute("""SELECT source, count(*), count(*) FILTER (WHERE body_no = -1)
                                        FROM main.system_body GROUP BY 1 ORDER BY 2 DESC""").fetchall():
        print(f"        {source or '(none)':<18}{n:>14,}{k:>12,} unknown index")
    if not ok:
        raise SystemExit("main.system_body does not hold one row per source (system, designation)")


def verify_constraints(con):
    fks = con.execute("""SELECT count(*) FROM duckdb_constraints()
                         WHERE constraint_type = 'FOREIGN KEY'
                           AND database_name = current_database()""").fetchone()[0]
    print(f"      FOREIGN KEY constraints in the new file: {fks}", flush=True)
    if fks:
        raise SystemExit("the new file carries a FOREIGN KEY")


def verify(con):
    print("\nverify: row counts and per-column checksums, source against new", flush=True)
    pairs = ([("main", t) for t, _ in tables(con, NEW.stem, "main")]
             + [("staging", t) for t, _ in tables(con, NEW.stem, "staging")
                if f"staging.{t}" not in WORK])
    for schema, table in pairs:
        if table not in RESHAPED:
            step(con, f"verify {schema}.{table}", lambda s=schema, t=table: verify_table(con, s, t))
    step(con, "verify sector re-key", lambda: verify_sectors(con))
    step(con, "verify main.system_body", lambda: verify_system_body(con))
    step(con, "verify constraints", lambda: verify_constraints(con))
    print("\n  references (informational -- a dangling id in the source copies across as one):")
    check_references(con)
    step(con, "verified", lambda: None)


def swap():
    con = connect(path=NEW, memory_limit=MEMORY)
    try:
        if not done(con, "verified"):
            raise SystemExit("the new file has not passed verification -- run without --swap")
        for table in WORK[1:] + WORK[:1]:
            con.execute(f"DROP TABLE IF EXISTS {table}")
        con.execute("CHECKPOINT")
    finally:
        con.close()
    for path in (DB, NEW):
        if path.with_name(path.name + ".wal").exists():
            raise SystemExit(f"{path.name}.wal exists -- something still holds the file")
    DB.rename(KEEP)
    NEW.rename(DB)
    print(f"{DB.name} is the new file; the previous one is {KEEP.name}")


def main():
    if "--swap" in sys.argv:
        swap()
        return
    con = connect(path=NEW, memory_limit=MEMORY, threads=THREADS)
    try:
        con.execute(f"ATTACH '{DB.as_posix()}' AS old (READ_ONLY)")
        con.execute("CREATE SCHEMA IF NOT EXISTS staging")
        con.execute(f"CREATE TABLE IF NOT EXISTS {DONE} (step VARCHAR, done_at TIMESTAMPTZ)")
        print(f"{DB.name} -> {NEW.name}")
        copy_staging(con)
        copy_main(con)
        con.execute("CHECKPOINT")
        verify(con)
    finally:
        con.close()
    print("\nDONE_BUILD_FRESH_DB -- inspect, then: python scripts/build_fresh_db.py --swap")


if __name__ == "__main__":
    main()
