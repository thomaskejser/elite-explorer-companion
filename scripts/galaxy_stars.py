import argparse
import csv
import pathlib
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from common import runlog

GALAXY = ROOT / "log" / "fss" / "galaxy"
OUT = GALAXY / "analysis"

UI_BOXES = [
    (0.0, 0.0, 0.287, 1.0),
    (0.716, 0.0, 1.0, 1.0),
    (0.265, 0.0, 0.580, 0.140),
    (0.320, 0.860, 0.695, 0.980),
]
BG_STEP = 8
BG_SIZE = 25
BG_PERCENTILE = 20
MIN_PEAK = 60.0
LOW = 25.0
PLATEAU = 4
RAY = 96
MIN_DISC = 4
MIN_CORE = 5
ZONE_GAP = 0.15
ZONE_WIDTH = 0.6
ZONE_MIN = 3
REF_PERCENTILE = 90
MIN_GIANT_DISC = 6
MIN_HALO_RATIO = 0.5
MAX_HALO_RATIO = 0.8
MAX_CROSS = 1.6
MIN_WHITE = 240
MAX_ELONG = 1.5
HALO_LEVEL = 0.25
COLOUR_WINDOW = 60
COLOUR_BACKDROP = 55.0
MIN_HALO_RING = 2
INNER_FROM = 0.4
INNER_TO = 0.8
MIN_INNER_WHITE = 0.68
MIN_WHITE_DISC = 8
_CY, _CX = np.mgrid[-COLOUR_WINDOW:COLOUR_WINDOW + 1, -COLOUR_WINDOW:COLOUR_WINDOW + 1]
_CR = np.hypot(_CY, _CX)
HOLE_LEVEL = 16
MIN_HOLE_AREA = 6
MIN_HOLE_FILL = 0.6
MAX_HOLE_ASPECT = 1.3
HOLE_RING_FROM = 1.6
HOLE_RING_TO = 3.0
HOLE_RING_PAD = 3.0
HOLE_DARK_LEVEL = 30
MAX_HOLE_DARK = 0.02
MIN_HOLE_SURROUND = 50.0
AXES = ((0, -1), (0, 1), (-1, 0), (1, 0))
DIAGONALS = ((-1, -1), (-1, 1), (1, -1), (1, 1))
PANEL_LEVEL = 30
PANEL_SIZE = 5
PANEL_GROW = 2
PICK_RADIUS = 40
CYAN_GROW = 6
MARK = 40


def load(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def ui_mask(rgb, lum):
    h, w, _ = rgb.shape
    mask = np.zeros((h, w), bool)
    for x0, y0, x1, y1 in UI_BOXES:
        mask[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = True
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    cyan = (g > 140) & (b > 140) & (g - r > 70) & (b - r > 70)
    box = np.ones((PANEL_SIZE, PANEL_SIZE), bool)
    small = ndimage.binary_closing(ndimage.binary_opening(lum[::BG_STEP, ::BG_STEP] < PANEL_LEVEL, structure=box), structure=box)
    small = ndimage.binary_dilation(small, iterations=PANEL_GROW)
    panel = np.repeat(np.repeat(small, BG_STEP, 0), BG_STEP, 1)[:h, :w]
    return mask | panel | ndimage.binary_dilation(cyan, iterations=CYAN_GROW)


def background(lum, mask):
    small = lum[::BG_STEP, ::BG_STEP].copy()
    hidden = mask[::BG_STEP, ::BG_STEP]
    shown = small[~hidden]
    small[hidden] = np.partition(shown, shown.size // 2)[shown.size // 2]
    bg = ndimage.percentile_filter(small, BG_PERCENTILE, size=BG_SIZE)
    bg = np.repeat(np.repeat(bg, BG_STEP, 0), BG_STEP, 1)
    return bg[:lum.shape[0], :lum.shape[1]]


def ray(res, y, x, dy, dx):
    h, w = res.shape
    out = np.zeros(RAY + 1, np.float32)
    for r in range(RAY + 1):
        k = r if dy == 0 or dx == 0 else int(round(r / 1.4142))
        yy, xx = y + dy * k, x + dx * k
        out[r] = res[yy, xx] if 0 <= yy < h and 0 <= xx < w else 0.0
    return out


def run_length(profile, level):
    below = np.nonzero(profile < level)[0]
    return int(below[0]) if below.size else len(profile)


def halo_blue(rgb, x, y, disc, halo):
    patch = rgb[y - COLOUR_WINDOW:y + COLOUR_WINDOW + 1, x - COLOUR_WINDOW:x + COLOUR_WINDOW + 1].astype(np.float64)
    base = np.median(patch[_CR > COLOUR_BACKDROP], axis=0)
    ring = (_CR > disc) & (_CR <= disc + max(halo, MIN_HALO_RING))
    glow = (patch[ring] - base).clip(0).sum(axis=0)
    return float(glow[2] / max(glow.sum(), 1.0))


def inner_white(rgb, x, y, disc):
    patch = rgb[y - COLOUR_WINDOW:y + COLOUR_WINDOW + 1, x - COLOUR_WINDOW:x + COLOUR_WINDOW + 1].astype(np.float64)
    band = (_CR >= disc * INNER_FROM) & (_CR < disc * INNER_TO)
    if not band.any():
        return 1.0
    mean = patch[band].mean(axis=0)
    return float(mean.min() / max(mean.max(), 1.0))


def black_holes(lum, mask):
    h, w = lum.shape
    labels, _ = ndimage.label(lum <= HOLE_LEVEL)
    holes = []
    for i, sl in enumerate(ndimage.find_objects(labels), 1):
        own = labels[sl] == i
        area = int(own.sum())
        if area < MIN_HOLE_AREA:
            continue
        bh, bw = own.shape
        if area / (bw * bh) < MIN_HOLE_FILL or max(bw, bh) > MAX_HOLE_ASPECT * min(bw, bh) + 1:
            continue
        cy, cx = np.nonzero(own)
        y, x = int(sl[0].start + cy.mean()), int(sl[1].start + cx.mean())
        if mask[y, x]:
            continue
        radius = float(np.sqrt(area / np.pi))
        reach = int(HOLE_RING_TO * radius) + 4
        if y < reach or x < reach or y + reach >= h or x + reach >= w:
            continue
        yy, xx = np.mgrid[-reach:reach + 1, -reach:reach + 1]
        d = np.hypot(yy, xx)
        ring = lum[y - reach:y + reach + 1, x - reach:x + reach + 1][(d >= HOLE_RING_FROM * radius) & (d <= HOLE_RING_TO * radius + HOLE_RING_PAD)]
        if np.mean(ring <= HOLE_DARK_LEVEL) > MAX_HOLE_DARK or np.median(ring) < MIN_HOLE_SURROUND:
            continue
        holes.append({"x": x, "y": y, "radius": round(radius, 4)})
    return holes


def measure(path):
    rgb = load(path)
    lum = rgb.max(axis=2)
    mask = ui_mask(rgb, lum)
    bg = background(lum, mask)
    res = lum - bg
    labels, count = ndimage.label((res >= LOW) & ~mask)
    h, w = lum.shape
    rows = []
    for i, sl in enumerate(ndimage.find_objects(labels), 1):
        own = labels[sl] == i
        sub = np.where(own, lum[sl], 0)
        top = sub.max()
        if top - bg[sl].max() < MIN_PEAK:
            continue
        plateau = own & (sub >= top - PLATEAU)
        depth = ndimage.distance_transform_cdt(np.pad(plateau, 1), metric="taxicab")[1:-1, 1:-1]
        inner = depth >= max(1, (int(depth.max()) + 1) // 2)
        core_labels, _ = ndimage.label(inner)
        sizes = np.bincount(core_labels[inner])
        big = [k for k in range(1, len(sizes)) if sizes[k] >= MIN_CORE]
        n_cores = len(big)
        for core in ([core_labels == k for k in big] or [inner]):
            row = star_at(rgb, res, core, sl, n_cores, h, w)
            if row:
                rows.append(row)
    ref = float(np.percentile([r["disc"] for r in rows], REF_PERCENTILE)) if rows else 1.0
    for row in rows:
        row["rel"] = round(row["disc"] / ref, 2)
    rows.sort(key=lambda r: (not r["giant"], -r["rel"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rgb, rows, black_holes(lum, mask)


def star_at(rgb, res, core, sl, n_cores, h, w):
    cy, cx = np.nonzero(core)
    cov = np.cov(np.vstack([cy, cx])) if cy.size > 2 else np.eye(2)
    eig = np.linalg.eigvalsh(cov + np.eye(2) * 0.25)
    elong = float(np.sqrt(eig[1] / eig[0]))
    y, x = int(round(sl[0].start + cy.mean())), int(round(sl[1].start + cx.mean()))
    if y < RAY or x < RAY or y >= h - RAY or x >= w - RAY:
        return None
    peak = float(res[y, x])
    if peak < MIN_PEAK:
        return None
    axes = [ray(res, y, x, dy, dx) for dy, dx in AXES]
    diags = [ray(res, y, x, dy, dx) for dy, dx in DIAGONALS]
    disc = int(np.median([run_length(d, peak - PLATEAU * 2) for d in diags]))
    if disc < MIN_DISC:
        return None
    start = disc + max(1, int(disc * ZONE_GAP))
    zone = slice(start, start + max(ZONE_MIN, int(disc * ZONE_WIDTH)))
    halo = int(np.median([run_length(d, peak * HALO_LEVEL) for d in diags])) - disc
    cross = np.median([a[zone].mean() for a in axes]) / max(np.median([d[zone].mean() for d in diags]), 1.0)
    white = int(rgb[y, x].min())
    return {
        "x": x, "y": y,
        "peak": int(peak),
        "disc": disc,
        "halo": halo,
        "halo_ratio": round(halo / disc, 2),
        "cross": round(float(cross), 2),
        "white": white,
        "cores": n_cores,
        "elong": round(elong, 2),
        "blue": round(halo_blue(rgb, x, y, disc, halo), 2),
        "inner_white": round(inner_white(rgb, x, y, disc), 2),
        "white_filled": bool(disc >= MIN_WHITE_DISC and inner_white(rgb, x, y, disc) >= MIN_INNER_WHITE),
        "giant": bool(disc >= MIN_GIANT_DISC and MIN_HALO_RATIO <= halo / disc <= MAX_HALO_RATIO and cross < MAX_CROSS
                      and white >= MIN_WHITE and elong < MAX_ELONG),
    }


def annotate(rgb, rows, path):
    img = Image.fromarray(rgb.astype(np.uint8))
    draw = ImageDraw.Draw(img)
    for row in rows[:MARK]:
        r = 10 + row["disc"]
        draw.ellipse((row["x"] - r, row["y"] - r, row["x"] + r, row["y"] + r), outline=(0, 255, 0), width=2)
        draw.text((row["x"] + r + 2, row["y"] - r), str(row["rank"]), fill=(0, 255, 0))
    img.save(path)


def nearest(rows, tx, ty):
    near = [r for r in rows if (r["x"] - tx) ** 2 + (r["y"] - ty) ** 2 <= PICK_RADIUS ** 2]
    return max(near, key=lambda r: r["disc"]) if near else None


def main():
    runlog.start()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=pathlib.Path, default=GALAXY)
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()
    with open(args.dir / "targets.csv", newline="") as f:
        targets = list(csv.DictReader(f))
    OUT.mkdir(parents=True, exist_ok=True)
    keys = ["rank", "x", "y", "peak", "disc", "halo", "halo_ratio", "cross", "white", "cores", "elong", "blue", "inner_white", "white_filled", "rel", "giant"]
    all_holes = []
    with open(OUT / "blobs.csv", "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["file", "target", "view", "is_target"] + keys)
        for t in targets:
            name = t["file"]
            rgb, rows, holes = measure(args.dir / name)
            all_holes.extend((name, hole) for hole in holes)
            annotate(rgb, rows, OUT / name.replace(".png", "-blobs.png"))
            hit = nearest(rows, int(t["tx"]), int(t["ty"])) if t["tx"] else None
            for row in rows:
                out.writerow([name, t["target"], t["view"], row is hit] + [row[k] for k in keys])
            print(f"\n{name}  {t['target']}  {t['class']}  view={t['view']}  stars={len(rows)}")
            print("    " + "  ".join(f"{k:>7}" for k in keys))
            for row in rows[:args.top]:
                print(("  * " if row is hit else "    ") + "  ".join(f"{row[k]:>7}" for k in keys))
            if hit and hit["rank"] > args.top:
                print("  * " + "  ".join(f"{hit[k]:>7}" for k in keys))

    with open(OUT / "holes.csv", "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["file", "x", "y", "radius"])
        for name, hole in all_holes:
            out.writerow([name, hole["x"], hole["y"], hole["radius"]])


if __name__ == "__main__":
    main()
