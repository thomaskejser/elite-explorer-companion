import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from common.db import connect

OUT = ROOT / "assets" / "guardian_sites.csv"
SITES = {
    "Guardian Data Terminal": "Guardian structure (blueprints)",
    "Guardian Relic Tower": "Guardian ruins (materials)",
}
MIN_SITES = 50


def main():
    if OUT.exists():
        raise SystemExit(f"{OUT} exists and is the record the overlay ships; delete it to pull again")
    con = connect(read_only=True)
    rows = con.execute("""
        SELECT english_name, system, body, count(*) AS reports,
               round(median(try_cast(x AS DOUBLE)), 5), round(median(try_cast(y AS DOUBLE)), 5), round(median(try_cast(z AS DOUBLE)), 5)
        FROM staging.canonn_codex_event
        WHERE english_name IN (SELECT unnest(?::VARCHAR[])) AND system IS NOT NULL AND body IS NOT NULL
          AND try_cast(x AS DOUBLE) IS NOT NULL
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3""", [list(SITES)]).fetchall()
    con.close()
    for entry in SITES:
        n = sum(1 for r in rows if r[0] == entry)
        if n < MIN_SITES:
            raise SystemExit(f"only {n} {entry} site(s) in staging.canonn_codex_event; refusing to write")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["kind", "system", "body", "reports", "x", "y", "z"])
        w.writerows([SITES[r[0]], *r[1:]] for r in rows)
    for entry, kind in SITES.items():
        print(f"  {kind}: {sum(1 for r in rows if r[0] == entry)} site(s)")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
