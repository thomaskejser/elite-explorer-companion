# The FSS spectrum

How the game draws the FSS spectrum, as measured from captures and checked against the journal.
`overlay/DESIGN.md` says how the overlay reads and marks it.
Positions are shares of the bar, 0 at LOW and 1 at HIGH; L is the bar's length.

## Slots

- The line is drawn through fixed points: about 198 slots, `SLOT` (0.00506 L) apart, slot 0 at 0.00037.
- Each slot holds one wave cycle: a downward tip on the slot, an upward tip half a slot after it.
- Tips land on their slot to within a pixel; no position finer than a slot is drawn.
- A body lights one or two neighbouring slots.
- Each class lights its own set of slots, airless bodies low in the set and atmospheric ones high.
- `overlay/src/slots.rs` is the learned table of which class lights which slot.
- Slot 83 is shared by high metal content with an atmosphere and airless rocky; the game's needle label names both there.
- Slot 96 is shared by icy with an atmosphere and airless rocky ice.
- Asteroid clusters light slots 62 to 68 (0.314 to 0.344), reaching a slot below their published range; the game resolves them on the honk, yet their wave stays on the bar in about two systems of three that have them.
- Sudarsky class V lights slot 173 (0.876), learned from one system.
- Sudarsky class IV lights slots 167 to 170; one giant lit 168, 169 or both in four systems, and two giants lit 167 to 169 in the one system holding two, so a third neighbouring spike may mean a second giant.
- Classes with no slot yet: helium-rich gas giant.

## Waves

- Every body draws the same shape: a small cycle, then a big one, about 12 columns wide.
- A wave reaches at most 0.026 L from the line; it grows taller with the body's distance from the arrival star.
- Waves of different slots add; bodies on the same slot merge into one wave.
- A class shows one body, two, or "three or more": a fourth body of the same class and atmosphere does not change the wave.
- Rings do not change the wave.
- A body resolved before the FSS opens may still draw a wave.

## Icons

- The game draws one icon per group of resolved bodies, under the line at the group's slot, with a count from two bodies up.
- A ringed body's icon has a slash; atmosphere changes the icon's position, not its glyph.
- An icon cuts into the wave below the line, so after the first body of a class is resolved only the wave above the line is whole.

## Data

| what | where |
|---|---|
| saved captures | `log/fss/<UTC stamp>-<SystemAddress>-<open\|watch\|honk\|scan-<class>>.png`, scan strips as `...-strip-<x>-<y>-<W>x<H>.png` |
| each scan's class and the position of its new icon | `log/fss/tuned.csv` |
| the truth: class, atmosphere, rings, distance, scan time | the game journals' `Scan` events |
| the slot learner's output | `log/fss/analysis/slots.txt`, `slot_votes.json` |
| the single-body template | `log/fss/analysis/template.npy`, `report.txt` |

`log/` is gitignored, so the captures stay on the machine that took them.
The overlay keeps every capture only while the Settings tab's "Keep every FSS screenshot" is ticked; otherwise it keeps just `last.png`.
It writes to `screenshots\` beside the exe; for calibrating, make that folder a junction to `log/fss` (`mklink /J screenshots <repo>\log\fss`).

## Calibrating

The `calibrate-fss` skill runs the whole procedure.

- `python scripts/fss_slots.py --score` learns the slot table from the saved captures and scores it, leaving each system out of the table it is scored with.
  - An opening reading votes each lit slot to the one class with an unresolved body within 0.012 of its published range; an asteroid cluster counts as unresolved even after the honk resolved it, because its wave stays.
  - The journal names no class for a cluster, so a `Scan` whose body name holds `Belt Cluster` is an asteroid cluster.
  - Slots 60 to 185 are learned; below 60 lie the signal sources, which the overlay names from their published ranges.
  - The capture just before the last body of a class is resolved votes that class's slots twice, when nothing else unresolved lies within 0.02 and the next capture shows the wave gone.
  - A class owns a slot with at least 35% of its votes.
- `--write` writes `overlay/src/slots.rs`; rebuild the overlay to use it.
- `python scripts/fss_wavelets.py` rebuilds the single-body template and its shape statistics.
- `python scripts/fss_bands.py` summarises where each class's icons land, from `tuned.csv`.

Last score, 69 systems: 214 classes right, 30 false, 21 missed, 19 unknown slots; asteroid clusters cost 10 of the misses (systems whose clusters drew no wave), and 18 of the false marks are high metal content or rocky bodies.

## Open questions

- Which body property sets a body's slot within its class?
- Does a class lighting more neighbouring slots than one body does mean two or more bodies of that class?
- What sets the size of a wave's small cycle against its big one (0.24 to 0.89)?
- Can the neighbouring slots tell high metal content with an atmosphere from airless rocky on slot 83?
