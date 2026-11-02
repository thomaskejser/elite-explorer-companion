import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import duckdb

from common.runlog import LOG_DB

LATEST = """
WITH steps AS (
    SELECT run_id, count(*) FILTER (WHERE kind = 'merge') AS merges,
           sum(inserted) AS inserted, sum(updated) AS updated,
           sum(rows_after) FILTER (WHERE kind = 'stage') AS staged
    FROM main.etl_run_step GROUP BY 1
),
ranked AS (
    SELECT r.*, row_number() OVER (PARTITION BY r.script ORDER BY r.started_utc DESC) AS rn,
           median(r.seconds) FILTER (WHERE r.status = 'ok') OVER (PARTITION BY r.script) AS median_ok,
           count(*) OVER (PARTITION BY r.script) AS runs
    FROM main.etl_run r
    WHERE r.script ILIKE ?
)
SELECT r.script, strftime(r.started_utc, '%Y-%m-%d %H:%M') AS started, r.status, r.seconds, r.median_ok,
       r.runs, s.merges, s.inserted, s.updated, s.staged, r.error
FROM ranked r LEFT JOIN steps s USING (run_id)
WHERE r.rn = 1
ORDER BY r.started_utc DESC
"""

HISTORY = """
SELECT r.run_id, strftime(r.started_utc, '%Y-%m-%d %H:%M:%S') AS started, r.script, r.status, r.seconds,
       st.kind, st.table_name, st.rows_before, st.rows_after, st.inserted, st.updated, st.orphaned, r.argv
FROM main.etl_run r
LEFT JOIN main.etl_run_step st USING (run_id)
WHERE r.script ILIKE ?
ORDER BY r.started_utc DESC, st.step_no
LIMIT ?
"""


def duration(s):
    if s is None:
        return "-"
    m, sec = divmod(int(round(s)), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{sec:02d}s" if h else f"{m}m{sec:02d}s" if m else f"{s:.1f}s"


def num(v):
    return "-" if v is None else f"{int(v):,}"


def latest(con, pattern):
    rows = con.execute(LATEST, [pattern]).fetchall()
    print(f"{'script':<34}{'last run (UTC)':<18}{'status':<12}{'took':>10}{'median ok':>11}"
          f"{'runs':>6}{'merges':>8}{'inserted':>13}{'updated':>13}{'staged':>14}")
    for script, started, status, seconds, median_ok, runs, merges, ins, upd, staged, error in rows:
        print(f"{script[:33]:<34}{started:<18}{status:<12}{duration(seconds):>10}{duration(median_ok):>11}"
              f"{runs:>6}{num(merges):>8}{num(ins):>13}{num(upd):>13}{num(staged):>14}")
        if error:
            print(f"{'':<34}{error[:110]}")
    print(f"\n{len(rows)} script(s). 'took' is the latest run; 'median ok' is over every successful run.")


def history(con, pattern, limit):
    rows = con.execute(HISTORY, [pattern, limit]).fetchall()
    last = None
    for run_id, started, script, status, seconds, kind, table, before, after, ins, upd, orphans, argv in rows:
        if run_id != last:
            print(f"\n{started}  {script}  {status}  {duration(seconds)}  {argv}")
            last = run_id
        if kind == "merge":
            print(f"    merge {table:<34} {num(ins):>12} inserted {num(upd):>12} updated "
                  f"{num(before):>14} -> {num(after):<14} {num(orphans)} orphaned")
        elif kind == "stage":
            print(f"    stage {table:<34} {num(after):>12} row(s)")


def main():
    parser = argparse.ArgumentParser(description="How long each ETL script took and how many rows it changed.")
    parser.add_argument("script", nargs="?", default="", help="part of a script name, e.g. station or system_known")
    parser.add_argument("--history", type=int, metavar="N", help="list the last N steps instead of one line per script")
    args = parser.parse_args()
    pattern = f"%{args.script}%"
    if not LOG_DB.exists():
        raise SystemExit(f"{LOG_DB} does not exist yet: no ETL run has finished since run logging began")
    con = duckdb.connect(str(LOG_DB), read_only=True)
    con.execute("SET TimeZone='UTC'")
    try:
        if args.history:
            history(con, pattern, args.history)
        else:
            latest(con, pattern)
    finally:
        con.close()


if __name__ == "__main__":
    main()
