# ED Black-Hole / Wolf-Rayet router

Finds undiscovered **black hole** (mass code f/g/h) and **Wolf-Rayet** (mass code h)
candidates near you and routes you through them, updating on every jump.

| tool | what it is |
| --- | --- |
| **`ed_bh_overlay.py`** | **The app.** In-game HUD overlay — always-on-top route panel, anchored bottom-right, with global hotkeys. |
| `ed_router.py` | The same routing engine as a terminal tool, and the shared core the overlay imports. |

## Requirements
- Python 3 with `duckdb` and `numpy` (`pip install duckdb numpy`), plus `tkinter`
  (bundled with standard Python on Windows).
- `pip install keyboard` for global hotkeys — optional; without it the HUD still
  works, just without hotkeys. May need the terminal run **as admin** on some setups.
- `candidates.parquet` in this folder (regenerate with
  `python ../scripts/build_candidates.py` if missing).

---

## The overlay (main app)

```
python ed_bh_overlay.py                    # click-through HUD, bottom-right, + hotkeys
python ed_bh_overlay.py --interactive      # + [copy] buttons, draggable
python ed_bh_overlay.py --radius 2000 --topn 12
python ed_bh_overlay.py --sort route       # shortest-path order instead of best-odds
python ed_bh_overlay.py --anchor tl --margin 50
python ed_bh_overlay.py --work-area        # clear the taskbar (see Positioning)
python ed_bh_overlay.py --fn-prefix ctrl+alt   # if a bare F-key clashes
```

**Run Elite in Borderless or Windowed mode** — overlays cannot draw over exclusive
fullscreen. This is a *screen* overlay: Elite has **no API** to put markers on the
actual galaxy/system map, so nothing can do that.

### What it does on every jump
1. Collects **every** unvisited BH/WR candidate within `--radius` (default 1000 ly).
2. Ranks all of them by **odds**: probability first, ties to `~pred` systems — visiting
   one settles both what is in it *and* whether it exists — then to the nearer system.
   Distance never outranks probability inside the radius; the radius *is* the reach
   filter, so a 47% target at its edge should beat a 17% one next door.
3. Shows the top `--topn` (default 12, one per function key).

Nothing is copied to the clipboard on its own — press `F1`–`F12` (or click a `[copy]`
button in `--interactive`) for the row you want. The route re-solves on every jump, so
an automatic copy would overwrite your clipboard at moments you did not pick.

`--sort route` swaps step 3 for a shortest-path solve through the same set
(nearest-neighbour, then 2-opt under `--route-ms`), which is the older behaviour: the
`dist` column becomes `leg` + `cum`, the distance from the previous waypoint and a
running total. Use it when you intend to fly the whole list in one sweep; the default
suits picking the best target from where you are.

### Reading the panel
```
@ Ahayan   1 target(s) within 1,000 ly
  ! only 1 in radius -> 11 more added beyond (+)
       system                     dist            BH    WR
 [ F1] Blua Hypa AA-A h26          312           32%   32% ~pred
 [ F2]+Blo Aescs BA-A f1386        201           28%     - pri:K
```
- `[F1]`…`[F12]` — the function key that copies that row.
- `dist` — distance from **you** (in `--sort route` mode: `leg` from the previous
  waypoint, plus a cumulative `cum`).
- `+` — entry added *beyond* the radius (dimmed); unmarked rows are in-radius. The fill
  is chosen by **proximity** and only then ranked, since outside the radius there is
  always a better-odds system somewhere — so `+` always means "outside your radius"
  rather than "worse odds".
- `~pred` — a PREDICTED system: inferred from an internal boxel gap, likely-real but
  unconfirmed, and its coordinates are the **boxel centre**, so its distance is
  approximate. Unmarked candidates are real catalogued systems with exact coordinates.
  Predicted systems are exempt from the `--rule-out-below` retirement only while their
  arrival class is **unknown** — once Elite reveals a class the system has proved it
  exists, which is all the exemption was protecting, so a disproving primary retires it
  like any other candidate.
- `p` — de-biased probability estimate. A *likelihood*, not a promise; scan to confirm.

### Hotkeys
Work even while the game is focused and in click-through mode.
- **`F1` … `F12` → copy row 1–12.** One key per row, no modifier, which is why `--topn`
  defaults to 12. Add one with `--fn-prefix ctrl+alt` if a bare F-key gets in the way:
  **F10 is Elite's own screenshot key and F12 is Steam's**, so those two are the likely
  clashes. `--suppress` stops the press reaching the game at all.
- `<prefix>+1` … `<prefix>+9` → rows 1–9, `<prefix>+0` → row 10. Still registered as a
  fallback (`--hotkey-prefix`, default `ctrl+alt`); it cannot reach rows 11–12.
- Each key is bound individually, so one unavailable combo (Windows can refuse a key
  another program already hooked) does not disable the rest — the console lists any that
  failed.
- Uses an OS-level keyboard hook and only *copies text* — no gameplay automation.

### Positioning
Anchored **bottom-right** by default and re-anchored after every render, since the
panel's height changes with the waypoint count. `--anchor {br,bl,tr,tl}`,
`--margin` (px, default 30), or `--x/--y` for an explicit position. In
`--interactive` mode, dragging the title strip pins it where you drop it.

By default it anchors to the **full screen**, which is what you want in-game:
Borderless covers the taskbar, so anchoring to the usable desktop would leave a
taskbar-sized gap. Pass `--work-area` to clear the taskbar when you're on the
desktop instead.

---

## Terminal version

Same engine, printed to the console. Useful on a second monitor or for testing.

```
python ed_router.py                  # watch the journal live
python ed_router.py --once           # solve for your current position, then exit
python ed_router.py --pos X Y Z      # solve for explicit coordinates
python ed_router.py --radius 2000 --topn 10
```

---

## Behaviour notes

**Short target sets.** If fewer than `--topn` targets lie in radius, the route is
extended past it by nearest-neighbour so you always get a full list; extended
waypoints are marked `+`. Zero in radius therefore behaves as: *fly to the nearest
target, then continue through the next nine.* The header always states which
waypoints came from where.

**Visited targets are retired permanently.** On startup every journal file is scanned
for systems you've jumped to, and each new jump is added live. The set is also
written to `visited.json`, so targets stay retired even after old journals are
deleted — a journal scan alone cannot know about those. `--include-visited` disables
the filtering.

**`--max-nodes` (default 2000)** bounds the TSP. 2-opt needs several O(n²) arrays
(~72 bytes per node pair), so an unbounded solve would exhaust memory — a 5,000 ly
radius over mass codes `efgh` is ~45,000 targets, needing ~143 GB. Above the cap the
**nearest** `--max-nodes` targets are routed and the header reports how many were
excluded. Since only `--topn` waypoints are shown and the route is re-solved every
jump, the legs you actually fly are unaffected. Measured: 574 targets in radius →
531 ms; 5,539 → 609 ms; 840,154 → 719 ms.

**`--route-ms` (default 250 in the HUD)** bounds 2-opt refinement. The HUD is
single-threaded, so this is also the longest it can pause on a jump.

---

## Honest limits

- **The mass-code gate is a hard fact**: black holes occur only in e/f/g/h systems
  and Wolf-Rayets only in h, readable from the procedural name — so it works for
  unscanned systems. Mass code `e` is excluded from the black-hole list by default
  (`--bh-codes efgh` to include it); its rate is low enough to swamp the route with
  poor odds.
- **Probabilities are de-biased rate estimates**, not promises. Only an in-game scan
  confirms anything.
- **Candidates come from community data** (Spansh/EDSM snapshot 2026-07). Brand-new
  or never-reported systems near you will not appear. Rebuild `candidates.parquet`
  periodically to refresh.
- **Inside the bubble almost nothing survives** the "unvisited AND never
  detail-scanned" filter — at the time of writing there was **1** black-hole target
  within 1000 ly of the author's position, so the route immediately extends outward.
  Routing gets genuinely useful a few thousand ly out.
- **Only journals still present** in your journal folder can be scanned; systems from
  deleted journals are covered only if they were already recorded in `visited.json`.
