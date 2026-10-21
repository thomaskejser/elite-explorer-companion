import argparse
import json
import math
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

import app.database as pydb
from app import route as pyroute
from app.table import cell_colour, cell_text
from app.theme import COLUMNS, CONFIRMED_COLUMNS, NEAREST_COLUMNS

EXE = ROOT / "target" / "release" / "ed-overlay.exe"
TABLES = {
    "confirmed_targets": CONFIRMED_COLUMNS,
    "carrier_targets": NEAREST_COLUMNS,
    "neutron_targets": NEAREST_COLUMNS,
    "trader_targets": NEAREST_COLUMNS,
    "adjacent_sectors": COLUMNS,
    "top_targets": COLUMNS,
    "unfound_targets": COLUMNS,
    "sector_totals": COLUMNS,
    "region_totals": COLUMNS,
}


def python_side(db, pos, sector, chain_to, rng, plain):
    out = {
        "confirmed_targets": db.confirmed_targets(pos),
        "carrier_targets": db.carrier_targets(pos, limit=1),
        "neutron_targets": db.neutron_targets(pos, limit=1),
        "trader_targets": db.trader_targets(pos, per_type=1),
        "adjacent_sectors": db.adjacent_sectors(sector, pos, limit=10),
    }
    if sector:
        out["top_targets"] = db.top_targets(sector, 10, pos=pos)
        out["unfound_targets"] = db.unfound_targets(sector, 3, pos=pos)
        out["sector_totals"] = db.sector_totals(sector)
        out["region_totals"] = db.region_totals(sector) or []
        out["sector_summary"] = list(db.sector_summary(sector))
    if chain_to:
        t0 = time.perf_counter()
        hops = db.solve_route(pos, chain_to, rng, names=("(start)", "(goal)"))
        out["solve_route"] = {"hops": [h["system"] for h in hops] if hops else None,
                              "secs": time.perf_counter() - t0}
        t0 = time.perf_counter()
        names, xyz = db.neutron_corridor(pos, chain_to, pad=600.0)
        plan = pyroute.plan(xyz, pos, chain_to, plain, rng)
        out["plan"] = {"corridor": len(names),
                       "hops": [names[i] for i in plan] if plan is not None else None,
                       "secs": time.perf_counter() - t0}
    return out


def rust_side(state, pos, sector, chain_to, rng, plain):
    cmd = [str(EXE), "--dump", "--state", str(state), "--pos", *map(str, pos)]
    if sector:
        cmd += ["--sector", sector]
    if chain_to:
        cmd += ["--chain-to", *map(str, chain_to), "--range", str(rng), "--plain-range", str(plain)]
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if done.returncode:
        raise SystemExit(f"rust dump failed: {done.stderr or done.stdout}")
    line = [l for l in done.stdout.splitlines() if l.startswith("{")][-1]
    return json.loads(line)


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is b
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def compare(py, rs, label):
    problems = []
    for name, columns in TABLES.items():
        if name not in py:
            continue
        prow, rrow = py[name], rs[name]["rows"]
        if len(prow) != len(rrow):
            problems.append(f"{name}: {len(prow)} python rows vs {len(rrow)} rust rows")
            continue
        for i, (p, r) in enumerate(zip(prow, rrow)):
            for key, value in p.items():
                if key not in r:
                    continue
                if not same(value, r[key]):
                    problems.append(f"{name}[{i}].{key}: python {value!r} vs rust {r[key]!r}")
            cells = [[cell_text(p, a, k, w), cell_colour(p, a, role, k).lower()]
                     for a, _h, w, _an, role, k in columns]
            if cells != rs[name]["cells"][i]:
                problems.append(f"{name}[{i}] cells: python {cells} vs rust {rs[name]['cells'][i]}")
    if "sector_summary" in py and py["sector_summary"] != rs.get("sector_summary"):
        problems.append(f"sector_summary: python {py['sector_summary']} vs rust {rs.get('sector_summary')}")
    for name in ("solve_route", "plan"):
        if name in py:
            ph, rh = py[name]["hops"], rs[name]["hops"]
            pj = None if ph is None else len(ph)
            rj = None if rh is None else len(rh)
            verdict = "same hops" if ph == rh else ("same length" if pj == rj else "DIFFERENT LENGTH")
            print(f"  {label} {name}: python {pj} in {py[name]['secs']:.2f}s, "
                  f"rust {rj} in {rs[name]['secs']:.2f}s -- {verdict}")
            if pj != rj:
                problems.append(f"{name}: python {pj} hops vs rust {rj}")
    counted = sum(len(py[n]) for n in TABLES if n in py)
    status = "OK" if not problems else f"{len(problems)} DIFFERENCES"
    print(f"{label}: {counted} rows compared -- {status}")
    for p in problems[:25]:
        print(f"    {p}")
    return not problems


def scenarios(db, extra):
    con = db._connection()
    picks = con.execute(f"""
        WITH busy AS (
          SELECT sector, count(*) AS n FROM {pydb.MODEL}.system_predicted
          WHERE NOT is_catalog GROUP BY sector ORDER BY n DESC LIMIT 3),
        unfound AS (SELECT DISTINCT sector FROM {pydb.MODEL}.system_unfound LIMIT 2),
        pois AS (SELECT sector FROM {pydb.MODEL}.system_poi GROUP BY sector
                 ORDER BY count(*) DESC LIMIT 1)
        SELECT s.sector, s.x, s.y, s.z FROM {pydb.MODEL}.sector s
        WHERE s.sector IN (SELECT sector FROM busy UNION SELECT sector FROM unfound
                           UNION SELECT sector FROM pois)
        ORDER BY s.sector""").fetchall()
    out = [("Sol (crafted)", (0.0, 0.0, 0.0), "crafted", None),
           ("Colonia (crafted)", (-9530.5, -910.28125, 19808.125), "crafted",
            (0.0, 0.0, 0.0))]
    for sector, x, y, z in picks:
        out.append((sector, (x + 11.0, y - 7.0, z + 5.0), sector, None))
    out.append(("no sector", (25.0, -20.0, 25000.0), None, (-1111.5625, -134.21875, 65269.75)))
    out.append(("Sol to Colonia", (0.0, 0.0, 0.0), "crafted", (-9530.5, -910.28125, 19808.125)))
    out.append(("Sol out 3 kly", (0.0, 0.0, 0.0), "crafted", (1500.0, -200.0, 2600.0)))
    return out + extra


def main():
    ap = argparse.ArgumentParser(description="Compare the Rust overlay's reads with the Python overlay's.")
    ap.add_argument("--state", type=pathlib.Path, required=True,
                    help="a COPY of elite_mapping_v2_current.duckdb; both sides read it")
    ap.add_argument("--range", type=float, default=285.0, help="boosted range for the route checks")
    ap.add_argument("--plain-range", type=float, default=71.3)
    args = ap.parse_args()
    pydb.CURRENT_DB = args.state
    db = pydb.Database()
    ok = True
    for label, pos, sector, chain_to in scenarios(db, []):
        py = python_side(db, pos, sector, chain_to, args.range, args.plain_range)
        db.close()
        rs = rust_side(args.state, pos, sector, chain_to, args.range, args.plain_range)
        ok &= compare(py, rs, label)
    print("ALL MATCH" if ok else "MISMATCHES FOUND")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
