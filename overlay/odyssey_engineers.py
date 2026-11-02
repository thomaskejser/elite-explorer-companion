import csv
import io
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "assets" / "odyssey_engineers.csv"
ENGINEERS = "https://raw.githubusercontent.com/EDCD/FDevIDs/master/engineers.csv"
WIKI = "https://elite-dangerous.fandom.com/api.php?action=parse&prop=wikitext&format=json&page="
STATIONS = "https://spansh.co.uk/api/stations/search"
UA = {"User-Agent": "elite-explorer-companion/1.0", "Content-Type": "application/json"}
SECTIONS = {"Suit Modifications": "Suit", "Weapon Modifications": "Weapon"}
PAUSE_S = 1.0
MIN_ENGINEERS = 10


def fetch(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data, UA), timeout=120) as r:
        return r.read().decode("utf-8")


def modifications(name):
    page = json.loads(fetch(WIKI + urllib.parse.quote(name.replace(" ", "_"))))
    if "parse" not in page:
        return []
    text = page["parse"]["wikitext"]["*"]
    found, section = [], None
    for line in text.splitlines():
        heading = re.match(r"^=+\s*(.*?)\s*=+$", line.strip())
        if heading:
            section = SECTIONS.get(heading.group(1))
            continue
        item = re.match(r"^\*\s*\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", line.strip())
        if section and item:
            found.append((section, item.group(1).strip()))
    return found


def sentence(text):
    return text[:1] + text[1:].lower()


def main():
    if OUT.exists():
        raise SystemExit(f"{OUT} exists and is the record the overlay ships; delete it to pull again")
    engineers = {r["name"]: int(r["market_id"]) for r in csv.DictReader(io.StringIO(fetch(ENGINEERS)))}
    mods = {}
    for name in sorted(engineers):
        got = modifications(name)
        if got:
            mods[name] = got
        time.sleep(PAUSE_S)
    if len(mods) < MIN_ENGINEERS:
        raise SystemExit(f"only {len(mods)} engineer page(s) list suit or weapon modifications; the wiki layout changed")
    stations = json.loads(fetch(STATIONS, {"filters": {"market_id": {"value": sorted(engineers[n] for n in mods)}},
                                           "size": len(mods), "page": 0}))["results"]
    by_market = {s["market_id"]: s for s in stations}
    rows = []
    for name, items in mods.items():
        s = by_market.get(engineers[name])
        if s is None:
            raise SystemExit(f"{name} has no workshop in Spansh (market {engineers[name]})")
        for kind, mod in items:
            rows.append([f"{kind}: {sentence(mod)}", name, s["system_name"], s["name"],
                         round(s.get("distance_to_arrival") or 0), s["system_x"], s["system_y"], s["system_z"]])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["module", "engineer", "system", "station", "arrival_ls", "x", "y", "z"])
        w.writerows(sorted(rows))
    print(f"wrote {OUT}: {len(rows)} engineer/modification pairs, {len({r[0] for r in rows})} modifications, "
          f"{len(mods)} engineers: {', '.join(sorted(mods))}")


if __name__ == "__main__":
    main()
