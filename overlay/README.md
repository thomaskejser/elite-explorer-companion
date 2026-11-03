# Explorers Companion — the HUD and its window

The in-game overlay and its application window, built as `explorers-companion.exe`, which Windows shows as Explorers Companion.
`DESIGN.md` is the design document: what it shows, why, and how each part behaves.
This file covers building it, what ships with it and where its state lives.

## Build

```
cargo build --release                  # in overlay/; the first build compiles DuckDB (~4 min)
python etl/build_seed.py               # in the repo root: the seed database a release ships beside the exe
dotnet build -c Release installer      # in overlay/: the MSI, target/dist/installer/ExplorersCompanion-<version>.msi
```

- The exe carries no galaxy data: the model mirror lives in the app-state database, which starts as a copy of the seed.
- The `calibrate` feature, on by default, saves FSS screenshots and shows the Settings tab's "Keep every FSS screenshot"; the release build leaves it out and writes no screenshots.
- `.cargo/config.toml` sets `jobs = 8`, half of this 16-core machine, so a build leaves room for the game while it compiles.
- DuckDB is pinned to the version the ETL uses (1.5.4), so both read and write the same file format.
- `build.rs` writes the resource script (the icon, and a version resource naming the product Explorers Companion at the `Cargo.toml` version) and compiles it with the Windows SDK's `rc.exe`, so the SDK must be installed.
- The icon is `assets/explorers-companion.ico`, drawn by `python overlay/assets/icon.py`; re-run it after changing the drawing.
- Licensed under Apache 2.0 (`LICENSE` and `NOTICE` in the repo root).

## What ships and where state lives

| | where it lives | written by |
|---|---|---|
| the program | `explorers-companion.exe` | `cargo build` |
| the seed: the app-state tables empty, the model mirror, `model.seed_info` | `elite_mapping_seed.duckdb` beside the exe | `etl/build_seed.py` |
| the commander's state, the model mirror and the settings (key bindings, keeping FSS screenshots) | `%LOCALAPPDATA%\explorers-companion\state.duckdb`, or the file `--state` names | the overlay; the mirror by the seed install |
| the run log | `%LOCALAPPDATA%\explorers-companion\log\explorers-companion.log`, or `--log` | the overlay |
| FSS screenshots, only with `calibrate` | `screenshots\` beside the exe: `last.png` alone, or every capture when the Settings tab keeps them | the overlay |

- **Installing and updating.**
  At start, with no `--state`, the overlay reads the seed beside the exe (else `elite_mapping_seed.duckdb` in the data directory):
  - no state file yet: the seed is copied in as `state.duckdb`;
  - the state file holds the same seed (`model.seed_info.id`): nothing happens;
  - a different seed: the state file is renamed `state-<UTC stamp>.duckdb` and kept, the seed is copied in, and every `main` table is migrated across by column name (`id64` becomes `system_id`), then `is_known` is re-derived against the new mirror.
    A failed migration puts the old file back.
  An installer therefore only places the exe and the seed; the next start does the rest.
- **A file named with `--state` is never replaced.**
  `explorers-companion.cmd` and `explorers-companion.sh` pass `--state elite_mapping_current.duckdb`, so the overlay and the ETL share the one irreplaceable file, whose mirror `etl/refresh_current.py` refreshes.
- On first start the data directory of an earlier build, `%LOCALAPPDATA%\ed-overlay`, is renamed `explorers-companion`, its unpacked-model caches are deleted, and the key bindings in its `keybindings.json` are imported into the `setting` table once.
- The journal is found through Windows' Saved Games known folder, so a moved or redirected Saved Games still works.
- Only one overlay may hold a state file at a time: DuckDB allows one writer per file.

## The installer

- `installer/ExplorersCompanion.wixproj` is a WiX 5 project: `dotnet build` fetches `WixToolset.Sdk` 5.0.2 from NuGet, so a clone needs only the .NET SDK (6 or later) besides Rust and the Windows SDK.
- It builds the exe without `calibrate` into `target/dist`, leaving the development exe in `target/release` alone, and packs it with `seed/elite_mapping_seed.duckdb` into an MSI of about 500 MB.
  The version is the one in `Cargo.toml`.
  `-p:Seed=<path>` takes the seed from elsewhere, such as a downloaded release asset, for a clone without the model.
- It installs per user, with no administrator prompt:
  - the exe and the seed into `%LOCALAPPDATA%\Programs\Explorers Companion`;
  - a Start menu shortcut;
  - the folders the overlay writes to, `%LOCALAPPDATA%\explorers-companion` and its `log`.
- A higher `Cargo.toml` version replaces the installed one, so bump it for every release; the `UpgradeCode` in `installer/Package.wxs` must never change.
- The MSI never touches `state.duckdb`: the next start finds the new seed and migrates the commander's tables as above.
- Uninstalling removes the exe, the seed, the shortcut and any folder left empty; the commander's state and the log stay.
- The MSI is not signed, so SmartScreen warns on first run.

## Run

```
explorers-companion.exe                                     # follow the journal
explorers-companion.exe --state C:\path\to\elite_mapping_current.duckdb
explorers-companion.exe --sector "Eol Prou" --trace
```

- `explorers-companion.exe --help` lists every flag; they are for development: where the files are, a forced sector, tracing and timing.
- Everything a player chooses is on the Settings tab, saved in the `setting` table: sounds, throttle lights, navigation keys, showing the HUD when Elite is not in front, the title bar, dragging, HUD size and opacity, and, with `calibrate`, keeping FSS screenshots.
  A new choice belongs there, not in a new flag.
- The HUD sizes itself to the game window's height, 100% at 1440 px; see `DESIGN.md`, *Size follows the game*.
- Launched from a terminal it prints to it as well as to the log; double-clicked it opens no console.

## Inspecting reads

```
explorers-companion.exe --dump --state <copy of elite_mapping_current.duckdb> --pos X Y Z [--sector S] [--chain-to X Y Z --range R]
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
| `win/expected_table.rs` | the sortable expected-objects table: the Map tab's list of a region's top sectors |
| `win/sector_systems.rs` | the Map tab's list of the systems tracked in one sector, click to copy |
| `win/settings.rs` | the Settings tab: keep every FSS screenshot, rebind the navigation keys, and the prediction against the outcome of each visited predicted system; settings are saved in the `setting` table |
| `win/trade.rs` | the Trade tab: nearest tech brokers and material traders |
| `win/stats.rs` | the Stats tab: confirmed objects visited and confirmed per day, one line per kind |
| `win/carrier_card.rs`, `market.rs` | the Carrier tab's card, with the cheapest Tritium from Spansh |
| `carriers.rs` | the HUD's Nearest carrier: the nearest carrier anyone may dock at, searched live on Spansh |
| `sirius.rs`, `sirius_brokers.py` | the nearest Sirius tech broker, from the compiled-in `assets/sirius_brokers.csv`, and the one-time pull that wrote it |
| `engineers.rs`, `engineers.py`, `odyssey_engineers.py` | the Engineers tab: the nearest grade-5 engineer per module type and the nearest Odyssey engineer per suit or weapon modification, from the compiled-in `assets/engineers.csv` and `assets/odyssey_engineers.csv`, and the one-time pulls that wrote them |
| `alien.rs`, `alien_sites.py` | the Guardian and Thargoid tabs: the nearest site of each kind, from the compiled-in `assets/alien_sites.csv`, and the extract from the model's Canonn codex that wrote it |
| `win/map.rs` | the Map tab: regions shaded by expected objects, click for the region's top sectors, double-click to open the region's sector grid, click a sector for its systems, Zoom out back to the galaxy |
| `win/hotkeys.rs`, `win/clipboard.rs`, `win/focus.rs`, `win/notify.rs`, `win/vkb.rs` | a low-level keyboard hook, the clipboard, the focus gate, sounds, the VKB throttle |
| `paths.rs` | where things live: the data directory, the journal, the seed, the log and screenshot folders |
| `dump.rs` | `--dump` |
