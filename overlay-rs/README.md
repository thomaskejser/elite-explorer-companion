# ed-overlay — the HUD as one Windows binary

A Rust rewrite of `app/` that ships as a single self-contained `ed-overlay.exe`.
It shows the same four tables, takes the same keys, writes the same rows and draws the same pixels as `python -m app.main`.
`app/README.md` is the design document for both; this file covers only what differs.

## Build

```
python overlay-rs/bundle.py            # pack the mirror + commander snapshot into overlay-rs/bundle/
cargo build --release                  # in overlay-rs/; the first build compiles DuckDB (~4 min)
```

- `bundle.py` reads `elite_mapping_v2_current.duckdb`, so the Python overlay must be idle or closed while it runs.
- Re-run both commands after `python etl/refresh_current.py`, or the binary serves the previous galaxy.
- The build fails if `overlay-rs/bundle/` is missing: the galaxy is compiled into the executable with `include_bytes!`.
- DuckDB is pinned to the version the Python side uses (1.5.4), so both read and write the same file format.

## What the binary carries

| | where it lives | written by |
|---|---|---|
| the model mirror (11 tables, pruned to the columns the overlay reads) | compiled in, zlib-packed, unpacked once to `%LOCALAPPDATA%\ed-overlay\model-<id>.duckdb` and attached `READ_ONLY` | `bundle.py` |
| the commander's state (`system_seen`, `system_visited`, `system_confirmed`, `poi_visited`, `system_wrong`, `route`, `system_alias`) | `%LOCALAPPDATA%\ed-overlay\state.duckdb`, or the file `--state` names | the overlay |
| the run log | `%LOCALAPPDATA%\ed-overlay\overlay.log`, or `--log` | the overlay |

- On first run with no `--state`, the state file is created from `schema/*.sql` and filled from the commander snapshot the bundle carries.
- From then on it is the binary's own copy and diverges from `elite_mapping_v2_current.duckdb`.
- To keep one irreplaceable file while the ETL is in Python, pass `--state ..\elite_mapping_v2_current.duckdb` instead.
- Only one overlay may hold a state file at a time: DuckDB allows one writer per file.

## Run

```
ed-overlay.exe                                     # follow the journal
ed-overlay.exe --state C:\path\to\elite_mapping_v2_current.duckdb
ed-overlay.exe --sector "Eol Prou" --always-visible
```

Every flag of `app.main` is accepted with the same meaning; `--state` and `--log` are the two additions.
Launched from a terminal it prints to it as well as to the log; double-clicked it opens no console.

## Where it deliberately differs from the Python overlay

- `--sector` paints the forced sector.
  The Python overlay queues the reads but never starts its worker or its tick, so that mode shows empty tables.
- The window never takes focus, so clicking or dragging it leaves Elite in front.
- The key slots are guarded by a mutex.
  `Hotkeys.take()` in Python reads and clears in two steps, and a press landing between them is lost.
- A refused SHIFT+A says it was refused; Python reports the refusal as `aliased`.
- SHIFT+BACKSPACE on an Adjacent sectors row records that row's sector, as `App.mark_wrong()` intends; Python overwrites it with the current sector.
- The Nearest carrier row is dressed on a copy.
  Python's `dress_nearest()` mutates the cached carrier rows, so the carrier chain's destination becomes its own next hop after a repaint.
- A partly written journal line is kept until it is complete rather than parsed, failed and skipped.
- `OpenClipboard` is retried briefly when another process holds the clipboard; Python falls back to Tk's clipboard, which empties on exit.
- With `--chrome` the footer is clipped to the tables' width instead of widening the window.
- `system_alias` is created when the database is opened, so a state file without it does not break every read.
- Sounds are played from memory; nothing is written to the temp directory.

## Comparing against the Python overlay

```
python overlay-rs/compare.py --state <copy of elite_mapping_v2_current.duckdb>
```

- Runs every read a repaint makes on both sides, over a set of sectors and positions, and diffs every row, every rendered cell text and every cell colour.
- Also solves the same neutron chains and SHIFT+N routes on both sides and compares jump counts and hops.
- Point it at a copy: both sides attach the file read-write.
- `ed-overlay.exe --dump --state <file> --pos X Y Z [--sector S] [--chain-to X Y Z --range R]` is the Rust half, printing JSON.

## Layout

| module | Python counterpart |
|---|---|
| `kinds.rs`, `names.rs`, `theme.rs`, `table.rs`, `journal.rs`, `ship.rs`, `route.rs`, `lights.rs`, `timing.rs`, `trace.rs` | the module of the same name |
| `neutron_route.rs`, `kdtree.rs` | `common/neutron_route.py`, and SciPy's `cKDTree` |
| `database.rs`, `sql/*.sql` | `app/database.py`; kinds-derived fragments are filled into `{{NAME}}` slots once at start-up |
| `dbworker.rs` | `app/dbworker.py`; `Ask` and `Answer` are enums rather than method names |
| `app.rs` | `app/main.py` |
| `win/overlay.rs` | `app/overlay.py`, drawn with GDI to Tk's pack and grid metrics |
| `win/hotkeys.rs`, `win/clipboard.rs`, `win/focus.rs`, `win/notify.rs`, `win/vkb.rs` | `app/hotkeys.py` (a low-level keyboard hook), `clipboard.py`, `focus.py`, `notify.py`, `common/vkb.py` |
| `bundle.rs`, `bundle.py` | none: unpacking the compiled-in model, and building it |
