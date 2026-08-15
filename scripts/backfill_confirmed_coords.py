"""Fill in coordinates for entries in app/confirmed.json that have none.

`confirmed.json` records every system whose arrival class Elite revealed as a black
hole or Wolf-Rayet, so it can outlive both the candidate pool and your memory. The
app fills each entry's coordinates from candidates.parquet, or from NavRoute.json
when the system is not in the pool.

Neither source covers a system that has ALREADY left the pool and is no longer on a
plotted route -- and that is exactly the case the store exists for. The galaxy spine
in the DuckDB always knows, so this backfills from there. Safe to re-run; it only
touches entries that are missing x/y/z and never overwrites one that has them.

  python scripts/backfill_confirmed_coords.py
"""
import duckdb, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STORE = ROOT / "app" / "confirmed.json"

if not STORE.exists():
    sys.exit(f"no {STORE} yet -- run the app first")
data = json.loads(STORE.read_text(encoding="utf-8"))
missing = [n for n, r in data.items() if "x" not in r]
if not missing:
    print(f"all {len(data):,} entries already have coordinates; nothing to do")
    raise SystemExit

print(f"{len(missing):,} of {len(data):,} entries need coordinates:")
for n in missing:
    print(f"  {n}")

con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"), read_only=True)
con.execute("SET memory_limit='6GB'"); con.execute("SET threads=8")
con.execute("CREATE TEMP TABLE want(name VARCHAR)")
con.executemany("INSERT INTO want VALUES (?)", [[n] for n in missing])
rows = con.execute("""
    SELECT s.name, s.x, s.y, s.z, s.mass_code
    FROM sys_feat s JOIN want w ON w.name = s.name
""").fetchall()
con.close()

for name, x, y, z, mc in rows:
    r = data[name]
    r["x"], r["y"], r["z"] = float(x), float(y), float(z)
    r.setdefault("mc", mc or "?")
    r.setdefault("pred", False)
    print(f"  filled {name:32s} mc={mc}  ({x:,.1f}, {y:,.1f}, {z:,.1f})")

still = [n for n in missing if "x" not in data[n]]
if still:
    print(f"\n{len(still)} not found in sys_feat (hand-named or outside the spine):")
    for n in still:
        print(f"  {n}")

tmp = STORE.with_suffix(".tmp")
tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
tmp.replace(STORE)
print(f"\nwrote {STORE}  ({len(rows)} filled, {len(still)} still unresolved)")
