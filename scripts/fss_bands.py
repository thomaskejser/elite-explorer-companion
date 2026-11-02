import argparse
import pathlib

import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent

TUNED = "read_csv(?, header = true, quote = '\"', columns = {'stamp': 'VARCHAR', 'address': 'VARCHAR', 'body': 'VARCHAR', 'class': 'VARCHAR', 'icon': 'DOUBLE'})"

BANDS = f"""
SELECT class,
       count(*) AS scans,
       count(DISTINCT address) AS systems,
       count(icon) AS icons,
       round(min(icon), 3) AS icon_lowest,
       round(median(icon), 3) AS icon_median,
       round(max(icon), 3) AS icon_highest
FROM {TUNED}
GROUP BY class
ORDER BY median(icon) NULLS LAST
"""

UNTUNED = f"""
SELECT count(*) FILTER (WHERE icon IS NULL) AS unlabelled, count(*) AS scans
FROM {TUNED}
"""


def main():
    parser = argparse.ArgumentParser(description="Where each body class sits on the FSS spectrum bar, from the overlay's tuned captures.")
    parser.add_argument("--tuned", default=str(ROOT / "log" / "fss" / "tuned.csv"))
    args = parser.parse_args()
    if not pathlib.Path(args.tuned).exists():
        raise SystemExit(f"{args.tuned} does not exist: resolve some bodies in the FSS with the overlay running")
    con = duckdb.connect()
    print(con.execute(BANDS, [args.tuned]).df().to_string(index=False))
    unlabelled, scans = con.execute(UNTUNED, [args.tuned]).fetchone()
    print(f"\n{scans} scan(s), {unlabelled} with no new icon to label")


if __name__ == "__main__":
    main()
