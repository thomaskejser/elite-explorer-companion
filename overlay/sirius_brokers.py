import csv
import json
import pathlib
import urllib.request
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "assets" / "sirius_brokers.csv"
PAGE = "https://elitedangerousutilities.azurewebsites.net/customtable/display?id=sirius%20brokers"
STATIONS = "https://spansh.co.uk/api/stations/search"
UA = {"User-Agent": "elite-explorer-companion/1.0", "Content-Type": "application/json"}
COLUMNS = ["System", "Civilization", "Station", "Arrival Dist. Ls"]


class Table(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = ""

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(self.cell.replace(" ", " ").split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def fetch(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data, UA), timeout=120) as r:
        return r.read().decode("utf-8")


def locate(system):
    found = json.loads(fetch(STATIONS, {"filters": {"system_name": {"value": system}}, "size": 50, "page": 0}))["results"]
    hits = [s for s in found if s["system_name"] == system]
    if not hits:
        raise SystemExit(f"Spansh has no station in {system!r} to read its coordinates from")
    return hits[0]


def main():
    if OUT.exists():
        raise SystemExit(f"{OUT} exists and is the record the overlay ships; delete it to pull again")
    table = Table()
    table.feed(fetch(PAGE))
    header = next((r for r in table.rows if r[:len(COLUMNS)] == COLUMNS), None)
    if header is None:
        raise SystemExit(f"{PAGE} has no table headed {COLUMNS}; its layout changed")
    rows = [r for r in table.rows if len(r) == len(header) and r != header]
    if not rows:
        raise SystemExit(f"{PAGE} lists no brokers")
    out = []
    for system, _, station, arrival in (r[:4] for r in rows):
        s = locate(system)
        out.append([system, station, int(arrival), s["system_x"], s["system_y"], s["system_z"]])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["system", "station", "arrival_ls", "x", "y", "z"])
        w.writerows(sorted(out))
    print(f"wrote {OUT}: {len(out)} Sirius tech broker(s)")


if __name__ == "__main__":
    main()
