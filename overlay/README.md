# Explorers Companion — the HUD and its window as one Windows binary

The in-game overlay and its application window, shipped as a single self-contained `ed-overlay.exe` that Windows shows as Explorers Companion.
`DESIGN.md` is the design document: what it shows, why, and how each part behaves.
This file covers building it, what the binary carries and where its state lives.

## Build

```
python overlay/bundle.py               # pack the mirror + commander snapshot into overlay/bundle/
cargo build --release                  # in overlay/; the first build compiles DuckDB (~4 min)
```

- `bundle.py` reads `elite_mapping_current.duckdb`, so the overlay must be idle or closed while it runs.
- Re-run both commands after `python etl/refresh_current.py`, or the binary serves the previous galaxy.
- The build fails if `overlay/bundle/` is missing: the galaxy is compiled into the executable with `include_bytes!`.
- DuckDB is pinned to the version the ETL uses (1.5.4), so both read and write the same file format.
- `build.rs` writes the resource script (the icon, and a version resource naming the product Explorers Companion at the `Cargo.toml` version) and compiles it with the Windows SDK's `rc.exe`, so the SDK must be installed.
- The icon is `assets/ed-overlay.ico`, drawn by `python overlay/assets/icon.py`; re-run it after changing the drawing.

## What the binary carries

| | where it lives | written by |
|---|---|---|
| the model mirror (15 tables, pruned to the columns the overlay reads) | compiled in, zlib-packed, unpacked once to `%LOCALAPPDATA%\ed-overlay\model-<id>.duckdb` and attached `READ_ONLY` | `bundle.py` |
| the commander's state (`system_seen`, `system_visited`, `system_confirmed`, `poi_visited`, `system_wrong`, `route`, `system_alias`) | `%LOCALAPPDATA%\ed-overlay\state.duckdb`, or the file `--state` names | the overlay |
| the run log | `%LOCALAPPDATA%\ed-overlay\overlay.log`, or `--log` | the overlay |

- On first run with no `--state`, the state file is created from `schema/*.sql` and filled from the commander snapshot the bundle carries.
  From then on it is the binary's own copy and diverges from `elite_mapping_current.duckdb`.
- `overlay.cmd` and `overlay.sh` pass `--state elite_mapping_current.duckdb`, so the overlay and the ETL share the one irreplaceable file.
- Only one overlay may hold a state file at a time: DuckDB allows one writer per file.

## Run

```
ed-overlay.exe                                     # follow the journal
ed-overlay.exe --state C:\path\to\elite_mapping_current.duckdb
ed-overlay.exe --sector "Eol Prou" --always-visible
```

- `ed-overlay.exe --help` lists every flag.
- Launched from a terminal it prints to it as well as to the log; double-clicked it opens no console.

## Inspecting reads

```
ed-overlay.exe --dump --state <copy of elite_mapping_current.duckdb> --pos X Y Z [--sector S] [--chain-to X Y Z --range R]
```

- Runs every read a repaint makes at that position, plus an optional neutron chain, and prints the rows as JSON.
- Point it at a copy: it attaches the state file read-write.

## Layout

| module | owns |
|---|---|
| `kinds.rs` | the vocabulary: one row per predictable object, every name it goes by and its arrival classes |
| `database.rs`, `sql/*.sql` | all SQL; kinds-derived fragments are filled into `{{NAME}}` slots once at start-up |
| `dbworker.rs` | the database thread; `Ask` and `Answer` are the requests and replies |
| `app.rs` | the event loop: journal, status, keys, repaints |
| `theme.rs`, `table.rs`, `row.rs` | colours, widths and column order; placing text |
| `journal.rs`, `ship.rs`, `route.rs`, `names.rs` | the journal and `NavRoute.json`, jump range, stored routes, procedural names |
| `neutron_route.rs`, `kdtree.rs` | fewest-jump neutron chains |
| `lights.rs`, `timing.rs`, `trace.rs`, `log.rs` | what the throttle LEDs mean, slow-read timing, tracing, the run log |
| `win/overlay.rs` | the HUD window, drawn with GDI |
| `win/main_window.rs` | the application window and its tabs: Log streams the run log |
| `win/expected_table.rs` | the sortable expected-objects table: the Regions tab and the Map tab's sector list |
| `win/trade.rs`, `market.rs` | the Trade tab: nearest tech brokers and material traders, and the cheapest Tritium from Spansh |
| `win/map.rs` | the Map tab: regions shaded by expected objects, click for the region's top sectors, as many as fit beside the map |
| `win/hotkeys.rs`, `win/clipboard.rs`, `win/focus.rs`, `win/notify.rs`, `win/vkb.rs` | a low-level keyboard hook, the clipboard, the focus gate, sounds, the VKB throttle |
| `bundle.rs`, `bundle.py` | unpacking the compiled-in model, and building it |
| `dump.rs` | `--dump` |
