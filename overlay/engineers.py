import csv
import io
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "assets" / "engineers.csv"
ENGINEERS = "https://raw.githubusercontent.com/EDCD/FDevIDs/master/engineers.csv"
MODULES = "https://raw.githubusercontent.com/EDCD/coriolis-data/master/modifications/modules.json"
STATIONS = "https://spansh.co.uk/api/stations/search"
UA = {"User-Agent": "elite-explorer-companion/1.0", "Content-Type": "application/json"}
GRADE = "5"

MODULE_NAMES = {
    "am": "Auto field-maintenance unit", "bh": "Bulkheads", "bl": "Beam laser",
    "bsg": "Bi-weave shield generator", "c": "Cannon", "cc": "Collector limpet controller",
    "ch": "Chaff launcher", "cs": "Manifest scanner", "csl": "Caustic sink launcher",
    "ec": "Electronic countermeasure", "fc": "Fragment cannon", "fi": "FSD interdictor",
    "fs": "Fuel scoop", "fsd": "Frame shift drive", "fx": "Fuel transfer limpet controller",
    "hb": "Hatch breaker limpet controller", "hr": "Hull reinforcement package",
    "hs": "Heat sink launcher", "kw": "Kill warrant scanner", "ls": "Life support",
    "mc": "Multi-cannon", "advmc": "Advanced multi-cannon", "mr": "Missile rack",
    "amr": "Advanced missile rack", "nl": "Mine launcher", "pa": "Plasma accelerator",
    "pc": "Prospector limpet controller", "pd": "Power distributor", "pl": "Pulse laser",
    "po": "Point defence", "pp": "Power plant", "psg": "Prismatic shield generator",
    "rf": "Refinery", "rg": "Rail gun", "s": "Sensors", "sb": "Shield booster",
    "sg": "Shield generator", "ss": "Detailed surface scanner", "t": "Thrusters",
    "tp": "Torpedo pylon", "ul": "Burst laser", "ws": "Frame shift wake scanner",
}


def fetch(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data, UA), timeout=120) as r:
        return r.read().decode("utf-8")


def main():
    if OUT.exists():
        raise SystemExit(f"{OUT} exists and is the record the overlay ships; delete it to pull again")
    engineers = {r["name"].replace("'", '"'): int(r["market_id"])
                 for r in csv.DictReader(io.StringIO(fetch(ENGINEERS)))}
    stations = json.loads(fetch(STATIONS, {"filters": {"market_id": {"value": sorted(engineers.values())}},
                                           "size": len(engineers), "page": 0}))["results"]
    by_market = {s["market_id"]: s for s in stations}
    modules = json.loads(fetch(MODULES))
    rows = []
    for code, module in modules.items():
        names = set()
        for blueprint in module.get("blueprints", {}).values():
            names |= set(blueprint["grades"].get(GRADE, {}).get("engineers", []))
        for name in sorted(names):
            if code not in MODULE_NAMES:
                raise SystemExit(f"module code {code!r} has grade {GRADE} engineers but no name in MODULE_NAMES")
            if name not in engineers or engineers[name] not in by_market:
                raise SystemExit(f"{name} ({MODULE_NAMES[code]}) has no market in EDCD or Spansh")
            s = by_market[engineers[name]]
            rows.append([MODULE_NAMES[code], name.replace('"', "'"), s["system_name"], s["name"],
                         round(s.get("distance_to_arrival") or 0), s["system_x"], s["system_y"], s["system_z"]])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["module", "engineer", "system", "station", "arrival_ls", "x", "y", "z"])
        w.writerows(sorted(rows))
    print(f"wrote {OUT}: {len(rows)} grade-{GRADE} engineer/module pairs, "
          f"{len({r[0] for r in rows})} module types, {len({r[1] for r in rows})} engineers")


if __name__ == "__main__":
    main()
