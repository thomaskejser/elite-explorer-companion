import argparse
import json
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np
from PIL import Image

import fss_wavelets as w

SLOT = 0.00506
SLOT_ZERO = 0.00037
TIP = 0.012
OWN = 0.012
CLEAR = 0.02
SHARE = 0.35
LONE_WEIGHT = 2
FIRST_SLOT, LAST_SLOT = 60, 185
RANGES = {w.CLUSTER: w.CLUSTER_RANGE, **w.RANGES}
ALWAYS_DRAWN = {w.CLUSTER}
STRIP = re.compile(r"-strip-(\d+)-(\d+)-(\d+)x(\d+)\.png$")
TABLE = w.ROOT / "overlay" / "src" / "slots.rs"


def stamp(p):
    return datetime.strptime(p.name[:16], "%Y%m%dT%H%M%SZ")


def at_slot(k):
    return SLOT_ZERO + k * SLOT


def frame(p, tmp):
    m = STRIP.search(p.name)
    if not m:
        return p
    x, y, width, height = map(int, m.groups())
    full = Image.new("RGB", (width, height))
    full.paste(Image.open(p), (x, y))
    path = f"{tmp}/{p.name}"
    full.save(path)
    return path


def lit_slots(p, geometry, tmp, above_only=False):
    top, bottom, left, right = geometry[p.name]
    sided = w.sides(frame(p, tmp), top, bottom, left, right)
    length = right - left
    up = np.array([u for u, _ in sided], float)
    s = up - np.array([d for _, d in sided], float)
    rise = up if above_only else s
    tip = TIP * length
    lit = set()
    for i in range(1, len(s) - 1):
        k = (i / length - SLOT_ZERO) / SLOT
        if not above_only and s[i] <= -tip and s[i] <= s[i - 1] and s[i] < s[i + 1]:
            lit.add(round(k))
        if rise[i] >= tip and rise[i] >= rise[i - 1] and rise[i] > rise[i + 1]:
            lit.add(round(k - 0.5))
    return {k for k in lit if FIRST_SLOT <= k <= LAST_SLOT}


def near(k, lo, hi):
    return lo - OWN <= at_slot(k) <= hi + OWN


def opening(bodies, captures, geometry, tmp):
    for p in captures:
        if not p.name.endswith(("-open.png", "-watch.png")):
            continue
        unresolved = [b for b in bodies.values() if b["at"] > stamp(p) or b["cls"] in ALWAYS_DRAWN]
        if unresolved:
            return lit_slots(p, geometry, tmp), unresolved
    return None


def votes_from_opening(lit, unresolved, votes):
    for k in lit:
        owners = [c for c in {b["cls"] for b in unresolved} if near(k, *RANGES[c])]
        if len(owners) != 1:
            continue
        atmospheres = {b["atmosphere"] for b in unresolved if b["cls"] == owners[0]}
        if len(atmospheres) == 1:
            votes[k][(owners[0], atmospheres.pop())] += 1


def votes_from_last_ones(bodies, captures, geometry, votes, tmp):
    lone = 0
    for cls, (lo, hi) in RANGES.items():
        mine = sorted((b for b in bodies.values() if b["cls"] == cls), key=lambda b: b["at"])
        if not mine:
            continue
        last = mine[-1]
        before = [p for p in captures if stamp(p) < last["at"] and all(b["at"] <= stamp(p) for b in mine[:-1])]
        after = [p for p in captures if stamp(p) >= last["at"]]
        if not before or not after:
            continue
        p = before[-1]
        crowded = any(b["cls"] != cls and b["at"] > stamp(p) and RANGES[b["cls"]][0] < hi + CLEAR and RANGES[b["cls"]][1] > lo - CLEAR
                      for b in bodies.values())
        if crowded:
            continue
        alone = {k for k in lit_slots(p, geometry, tmp, True) if near(k, lo, hi)}
        still = {k for k in lit_slots(after[0], geometry, tmp, True) if near(k, lo, hi)}
        if alone and not still:
            lone += 1
            for k in alone:
                votes[k][(cls, last["atmosphere"])] += LONE_WEIGHT
    return lone


def merged(per_system, skip=None):
    votes = defaultdict(Counter)
    for address, slots in per_system.items():
        if address != skip:
            for k, v in slots.items():
                votes[k].update(v)
    return votes


def table(votes):
    rows = []
    for k in sorted(votes):
        by_class = Counter()
        for (cls, _), n in votes[k].items():
            by_class[cls] += n
        total = sum(by_class.values())
        for cls, n in by_class.most_common():
            if n >= SHARE * total:
                atmosphere = sum(m for (c, a), m in votes[k].items() if c == cls and a) * 2 > n
                rows.append((k, cls, atmosphere, n))
    return rows


def score(per_system, openings):
    tally, unknown = Counter(), 0
    for address, (lit, unresolved) in openings.items():
        owned = defaultdict(set)
        for k, cls, _, _ in table(merged(per_system, address)):
            owned[k].add(cls)
        predicted = set().union(*(owned[k] for k in lit)) if lit else set()
        unknown += sum(1 for k in lit if not owned[k])
        truth = {b["cls"] for b in unresolved}
        tally["right"] += len(truth & predicted)
        tally["false"] += len(predicted - truth)
        tally["missed"] += len(truth - predicted)
    return f"scored {len(openings)} systems, each left out of its table: {tally['right']} right, {tally['false']} false, {tally['missed']} missed, {unknown} unknown slot(s)"


def rust(rows):
    lines = ["use crate::bands::Slot;", "", f"pub const SLOTS: [Slot; {len(rows)}] = ["]
    lines += [f"    Slot {{ slot: {k}, class: \"{cls}\", atmosphere: {str(a).lower()} }}," for k, cls, a, _ in rows]
    return "\n".join(lines + ["];", ""])


def main():
    parser = argparse.ArgumentParser(description="Learn which FSS spectrum slots each body class lights, from the overlay's saved captures and the journal.")
    parser.add_argument("--write", action="store_true", help=f"write the table the overlay compiles in, {TABLE.relative_to(w.ROOT)}")
    parser.add_argument("--score", action="store_true", help="score the table against the journal, leaving each system out of the table it is scored with")
    args = parser.parse_args()
    w.OUT.mkdir(parents=True, exist_ok=True)
    bodies = w.journal_bodies(RANGES)
    systems = defaultdict(list)
    for p in sorted(w.FSS.glob("*-*.png")):
        address = p.name.split("-")[1]
        if address in bodies:
            systems[address].append(p)
    geometry = w.bars([p for ps in systems.values() for p in ps])
    per_system, openings, lone = {}, {}, 0
    with tempfile.TemporaryDirectory() as tmp:
        for address, captures in systems.items():
            captures = [p for p in captures if p.name in geometry]
            votes = defaultdict(Counter)
            first = opening(bodies[address], captures, geometry, tmp)
            if first:
                openings[address] = first
                votes_from_opening(*first, votes)
            lone += votes_from_last_ones(bodies[address], captures, geometry, votes, tmp)
            per_system[address] = votes
    rows = table(merged(per_system))
    votes = merged(per_system)
    json.dump({str(k): {f"{c}|{a}": n for (c, a), n in v.items()} for k, v in sorted(votes.items())}, open(w.OUT / "slot_votes.json", "w"), indent=1)
    lines = [f"{len(rows)} slot owners from {len(systems)} systems ({len(openings)} opening readings, {lone} confirmed last-one-left waves)", ""]
    lines += [f"slot {k:3}  {at_slot(k):.4f}  {cls:34} {'atm' if a else '   '}  {n} vote(s)" for k, cls, a, n in rows]
    lines += ["", "classes with no slot yet: " + ", ".join(c for c in RANGES if c not in {r[1] for r in rows})]
    if args.score:
        lines += ["", score(per_system, openings)]
    text = "\n".join(lines)
    (w.OUT / "slots.txt").write_text(text, encoding="utf-8")
    print(text)
    if args.write:
        TABLE.write_text(rust(rows), encoding="utf-8")
        print(f"\nwrote {TABLE}")


if __name__ == "__main__":
    main()
