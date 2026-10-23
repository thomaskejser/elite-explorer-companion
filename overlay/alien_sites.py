import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from common.db import connect

OUT = ROOT / "assets" / "alien_sites.csv"
CATEGORIES = ("Guardian", "Thargoid")
ROLES = {
    "Guardian Data Terminal": "Guardian Data Terminal (blueprints)",
    "Guardian Relic Tower": "Guardian Relic Tower (materials)",
}
MIN_SITES = {"Guardian": 300, "Thargoid": 200}


def main():
    if OUT.exists():
        raise SystemExit(f"{OUT} exists and is the record the overlay ships; delete it to pull again")
    con = connect(read_only=True)
    rows = con.execute("""
        SELECT hud_category, english_name, system, body, count(*) AS reports,
               strftime(max(reported_at), '%Y-%m-%d') AS last_reported,
               round(median(try_cast(x AS DOUBLE)), 5), round(median(try_cast(y AS DOUBLE)), 5),
               round(median(try_cast(z AS DOUBLE)), 5)
        FROM staging.canonn_codex_event
        WHERE hud_category IN (SELECT unnest(?::VARCHAR[]))
          AND english_name IS NOT NULL AND system IS NOT NULL AND body IS NOT NULL
          AND try_cast(x AS DOUBLE) IS NOT NULL
        GROUP BY 1, 2, 3, 4
        ORDER BY 1, 2, 3, 4""", [list(CATEGORIES)]).fetchall()
    con.close()
    for category, minimum in MIN_SITES.items():
        n = sum(1 for r in rows if r[0] == category)
        if n < minimum:
            raise SystemExit(f"only {n} {category} site(s) in staging.canonn_codex_event; refusing to write")
    if any("," in str(v) for r in rows for v in r[:4]):
        raise SystemExit("a name contains a comma, which the overlay's CSV reader does not quote")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category", "kind", "system", "body", "reports", "last_reported", "x", "y", "z"])
        w.writerows([r[0], ROLES.get(r[1], r[1]), *r[2:]] for r in rows)
    for category in CATEGORIES:
        kinds = {r[1] for r in rows if r[0] == category}
        print(f"  {category}: {sum(1 for r in rows if r[0] == category)} site(s) of {len(kinds)} kind(s)")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
