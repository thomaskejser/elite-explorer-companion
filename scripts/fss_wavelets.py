import argparse
import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from common.game import journal_dir
FSS = ROOT / "log" / "fss"
OUT = FSS / "analysis"
JOURNALS = journal_dir()

CLUSTER = "Asteroid cluster"
CLUSTER_NAME = "Belt Cluster"
CLUSTER_RANGE = (0.322, 0.358)
RANGES = {
    "Metal rich body": (0.359, 0.382),
    "High metal content body": (0.385, 0.417),
    "Rocky body": (0.420, 0.452),
    "Icy body": (0.453, 0.486),
    "Rocky ice body": (0.486, 0.521),
    "Earthlike body": (0.522, 0.547),
    "Ammonia world": (0.548, 0.579),
    "Water world": (0.582, 0.614),
    "Water giant": (0.615, 0.626),
    "Gas giant with water based life": (0.676, 0.707),
    "Gas giant with ammonia based life": (0.712, 0.734),
    "Sudarsky class I gas giant": (0.738, 0.761),
    "Sudarsky class II gas giant": (0.770, 0.793),
    "Sudarsky class III gas giant": (0.797, 0.831),
    "Sudarsky class IV gas giant": (0.836, 0.866),
    "Sudarsky class V gas giant": (0.870, 0.898),
    "Helium rich gas giant": (0.908, 0.931),
}
ISOLATION = 0.03
STROKE_GAP = 0.006
FLOOR = 6
WIDTH = (8, 12)
WINDOW = 12
BIG_AT = 7
BAR = re.compile(r"^(\S+\.png) Some\(Bar \{ top: (\d+), bottom: (\d+), left: (\d+), right: (\d+) \}\)")


def openings():
    return sorted(p for p in FSS.glob("*.png") if p.name.endswith(("-open.png", "-watch.png")))


def bars(paths):
    with tempfile.TemporaryDirectory() as tmp:
        for p in paths:
            shutil.copy(p, tmp)
        env = dict(os.environ, FSS_DIR=tmp)
        run = subprocess.run(
            ["cargo", "test", "--release", "-j", "8", "reads_every_capture", "--", "--ignored", "--nocapture"],
            cwd=ROOT / "overlay", env=env, capture_output=True, text=True,
        )
    found = {}
    for line in run.stdout.splitlines():
        m = BAR.match(line)
        if m:
            found[m.group(1)] = tuple(int(v) for v in m.groups()[1:])
    return found


def journal_bodies(ranges=RANGES):
    bodies = {}
    for f in sorted(glob.glob(str(JOURNALS / "Journal.*.log"))):
        for line in open(f, encoding="utf-8", errors="replace"):
            if '"event":"Scan"' not in line or ('"PlanetClass"' not in line and CLUSTER_NAME not in line):
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            cls = e.get("PlanetClass") or (CLUSTER if CLUSTER_NAME in e.get("BodyName", "") else None)
            if cls not in ranges or not e.get("SystemAddress"):
                continue
            bodies.setdefault(str(e["SystemAddress"]), {})[e["BodyName"]] = dict(
                cls=cls,
                atmosphere=bool(e.get("Atmosphere")),
                rings=bool(e.get("Rings")),
                at=datetime.strptime(e["timestamp"], "%Y-%m-%dT%H:%M:%SZ"),
                distance=e.get("DistanceFromArrivalLS"),
                mass=e.get("MassEM"),
                radius=e.get("Radius"),
                temperature=e.get("SurfaceTemperature"),
            )
    return bodies


def sides(path, top, bottom, left, right):
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    length = right - left
    reach = round(0.026 * length)
    line = np.median(a[top:bottom + 1, left:right + 1].reshape(-1, 3), axis=0)
    xs = slice(left, right + 1)
    backdrop = np.median(a[top - round(0.06 * length):top - round(0.035 * length), xs], axis=0)
    apart = np.abs(line - backdrop).sum(axis=1)
    rows = np.arange(top - reach, bottom + reach + 1)
    pixels = a[rows, xs]
    lit = (np.abs(pixels - line).sum(axis=2) < 0.6 * apart) & (np.abs(pixels - backdrop).sum(axis=2) >= 0.5 * apart)
    lit[lit.mean(axis=1) > 0.5] = False
    above = lit[:reach][::-1]
    below = lit[len(rows) - reach:]
    gap = round(STROKE_GAP * length)

    def joined(side):
        last = np.zeros(side.shape[1], int)
        for d in range(1, reach + 1):
            last = np.where(side[d - 1] & (d - last <= gap), d, last)
        return last

    return list(zip(joined(above).tolist(), joined(below).tolist()))


def window(signal):
    big = int(np.argmin(signal))
    padded = np.pad(signal, (WINDOW, WINDOW))
    start = big - BIG_AT + WINDOW
    return padded[start:start + WINDOW]


def extract():
    paths = openings()
    geometry = bars(paths)
    bodies = journal_bodies()
    cases, seen = [], set()
    for p in paths:
        if p.name not in geometry:
            continue
        address = p.name.split("-")[1]
        stamp = datetime.strptime(p.name[:16], "%Y%m%dT%H%M%SZ")
        unresolved = [b for b in bodies.get(address, {}).values() if b["at"] > stamp]
        top, bottom, left, right = geometry[p.name]
        length = right - left
        signal = None
        for cls, (lo, hi) in RANGES.items():
            mine = [b for b in unresolved if b["cls"] == cls]
            near = [b for b in unresolved if b["cls"] != cls and RANGES[b["cls"]][0] < hi + ISOLATION and RANGES[b["cls"]][1] > lo - ISOLATION]
            if len(mine) != 1 or near or (address, cls) in seen:
                continue
            if signal is None:
                signal = sides(p, top, bottom, left, right)
            i0, i1 = max(0, round((lo - ISOLATION) * length)), min(length, round((hi + ISOLATION) * length))
            seg = signal[i0:i1 + 1]
            amp = [max(u, d) for u, d in seg]
            lit = [i for i, v in enumerate(amp) if v >= FLOOR]
            if not lit:
                continue
            width = lit[-1] - lit[0] + 1
            centre = (i0 + sum(i * amp[i] for i in lit) / sum(amp[i] for i in lit)) / length
            body = mine[0]
            seen.add((address, cls))
            cases.append(dict(
                capture=p.name, address=address, cls=cls, atmosphere=body["atmosphere"], rings=body["rings"],
                distance=body["distance"], mass=body["mass"], radius=body["radius"], temperature=body["temperature"],
                centre=round(centre, 4), width=width, peak=max(amp),
                signal=[u - d for u, d in seg[max(0, lit[0] - 3):lit[-1] + 4]],
            ))
    return cases


def report(cases):
    clean = [c for c in cases if WIDTH[0] <= c["width"] <= WIDTH[1]]
    windows = np.array([window(np.array(c["signal"], float)) for c in clean])
    template = windows.mean(axis=0)
    lines = [f"{len(cases)} single-body cases, {len(clean)} clean (width {WIDTH[0]} to {WIDTH[1]} columns)", ""]
    lines.append("shared template (above minus below, px): " + " ".join(f"{v:.1f}" for v in template))
    lines.append("")
    lines.append(f"{'class':34} {'atm':3} {'ring':4} {'match':>5} {'small/big':>9} {'height':>6} {'dist ls':>8} {'centre':>7}  wavelet")
    stats = []
    for c, w in sorted(zip(clean, windows), key=lambda x: (x[0]["cls"], x[0]["rings"])):
        big, small = np.max(np.abs(w[6:])), np.max(np.abs(w[:6]))
        ratio = small / big if big else 0.0
        match = float(np.corrcoef(w, template)[0, 1])
        stats.append((c, ratio, big))
        lines.append(
            f"{c['cls'][:34]:34} {'atm' if c['atmosphere'] else '':3} {'ring' if c['rings'] else '':4} {match:5.2f} {ratio:9.2f} "
            f"{big:6.0f} {c['distance'] or 0:8.0f} {c['centre']:7.4f}  {np.round(w).astype(int).tolist()}"
        )
    lines.append("")
    for ringed in (True, False):
        r = [s[1] for s in stats if s[0]["rings"] == ringed]
        if r:
            lines.append(f"small/big cycle, {'ringed' if ringed else 'unringed'}: n={len(r)} median {np.median(r):.2f} range {min(r):.2f}-{max(r):.2f}")
    d = [(np.log10(max(s[0]["distance"] or 1, 1)), s[2]) for s in stats]
    if len(d) > 2:
        lines.append(f"height against log distance from arrival: r={np.corrcoef(*zip(*d))[0, 1]:.2f}")
    lines.append("")
    lines.append("classes with no clean single-body case yet (their shape is a guess): "
                 + ", ".join(sorted(set(RANGES) - {c["cls"] for c in clean})))
    return template, "\n".join(lines)


def main():
    argparse.ArgumentParser(description="Extract single-body FSS wavelets from the opening captures and report their shapes.").parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cases = extract()
    json.dump(cases, open(OUT / "cases.json", "w"), indent=1)
    template, text = report(cases)
    np.save(OUT / "template.npy", template)
    (OUT / "report.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
