# Explorers Companion

An Elite Dangerous companion for explorers: an in-game HUD for Windows that tells you where the rare things are and routes you to them.
The HUD, `explorers-companion.exe`, is backed by a model of the galaxy built from the community's data (Spansh, EDSM, EDAstro, Canonn).
The model predicts which unvisited systems hold rare arrival stars (black holes, Wolf-Rayets, Herbig Ae/Be, O-types, supergiants, neutron stars, white dwarfs) and where exobiology and geology nobody has logged are likely to be.
The HUD follows your journal as you fly, shows only what matters on the screen you are on, and puts the next system to plot on the clipboard for the galaxy map's search.

- It reads the game's journal and `Status.json`, and captures the screen only to read the FSS spectrum bar; it never sends input to the game.
- Predictions are odds, not finds: nothing is certain until the game reveals the star or a scan confirms it.
- A route plot on the galaxy map reveals every hop's arrival star, so one plot can confirm rare stars thousands of light years away before anyone flies there.

## What you see in game

The HUD is a set of transparent panes drawn over the game, each shown only on the screen it is for, and all hidden when Elite is not in front.
`overlay/DESIGN.md` describes every pane in full.

### In flight

A pane at the top centre, between the canopy's comms and ship panels:

- **Nearest**: the nearest confirmed find of each rare kind (stars your route plots revealed that nobody has scanned), the nearest open fleet carrier, the nearest neutron star and the nearest unvisited point of interest.
  A target more than one boosted jump away gets a neutron chain solved live at your ship's range, and the row shows the next hop to plot.
- **Next jump**: the route still ahead, scaled by distance, with neutron-boosted legs in their own colour.
  The system being jumped to shows its star spelled out (with Spansh's or EDSM's subtype once looked up), its jump length, whether a carrier is there, and who discovered it and when, or `Undiscovered`.
  When the target has unlogged biology predicted, a line gives its expected value, its candidate bodies and the likely species.
- **The system line**: icons and counts for the system you are in: bodies, bodies with biological signals, geological signals (green when the geology is probably new to your codex for this region), Earth-like, water and ammonia worlds, signal sources, stations and carriers.
  Before any scan the biology count and the worlds can come from the FSS spectrum prediction, marked `~` or `>0` as probable.
- **The carrier line**: your fleet carrier's state (ready, jumping with a countdown, or cooling down) and the clock.

A plot that adds rare arrival stars shows a popup for two seconds listing them.

### On the galaxy map

- **Sector table** (bottom left): your sector and the 26 around it, each with the expected number of undiscovered objects of each kind and how many heavy (mass code `h`, `g`, `f`, `e`) predicted systems it holds, plus the region's total.
  Moving the cursor onto a row copies the best system in that sector.
- **Sector mini map** (above the sector table): the same block seen from above over the galaxy's star glow and region borders, with your plotted route, your carrier's route, your unvisited confirmed finds and your ship.
- **Plan pane** (right edge):
  - the ten nearest unvisited points of interest (anomalies, notable stellar phenomena, Guardian and Thargoid sites, generation ships and more);
  - your carrier's next five stops towards the destination set on the Carrier tab;
  - the most valuable systems within 250 ly with biology nobody has logged.

### On the system map

A list of every body in the current system still worth landing on, ranked for landing:

- the body's icon and name, and a flag when nobody has set foot on it;
- each genus it may hold, with its chance, or its value once a surface scan has named it;
- geological signals, green when probably new to your codex;
- the body's value at base Vista Genomics prices;
- the system's points of interest under it.

A body leaves the list once everything on it is logged.

### In the FSS

When the FSS opens, the overlay reads the spectrum bar and draws the predicted body icons above it, where the game will draw them once the bodies are resolved, so Earth-like, water and ammonia worlds and signal sources show before you tune to them.
`overlay/FSS_SPECTRUM.md` explains the spectrum and how the prediction is learned.

### Sounds and lights

- A short chime when a plot reveals a rare star, and a tick when the clipboard changes.
- On a VKB STECS throttle, its three LEDs show fuel, the arrival star of the next jump (neutron, white dwarf, black hole), and cargo scoop and shield state.

## The application window

A standard window beside the HUD, in the taskbar and Alt+Tab; closing it quits the overlay.

| tab | what it shows |
| --- | --- |
| Map | the galactic regions shaded by how many of one kind are still expected there; click a region for its best sectors, click a sector to copy its best target |
| Regions | one sortable row per region with its predicted systems, visited systems and expected objects of each kind |
| Sectors | one sector found by name: where it lies, and every system in it the overlay tracks |
| Codex | the codex entries of a region you have not logged yet, and the nearest system where each was reported |
| Trade | the nearest Universal Cartographics, Vista Genomics, large-pad repair, technology brokers and material traders |
| Engineers | the nearest engineer for each module type at grade 5, and for each Odyssey suit and weapon modification |
| Guardian | the nearest site of each Guardian kind |
| Thargoid | the nearest site of each Thargoid kind |
| Carrier | your fleet carrier: where it is, its jump state, a destination with the planned route and Tritium needed, and the cheapest and bulk Tritium nearby |
| Stats | confirmed objects found and visited per day, one line per kind |
| Settings | everything you choose about the HUD, the key bindings, and how the predictions fared in the systems you visited |
| Log | the overlay's run log, live |

Clicking a row that names a system copies it to the clipboard.

## Getting started

- **There is no installer or published release yet.**
  Running the overlay today means building it from source and building the seed database from the model (see *For developers*).
- What a release will ship is two files side by side:
  - `explorers-companion.exe`, the program;
  - `elite_mapping_seed.duckdb`, the seed: the model's predictions and lookups, about 1.2 GB.
- On first start the seed is copied to `%LOCALAPPDATA%\explorers-companion\state.duckdb`, which then holds everything the overlay learns about your flying: systems seen, visited and confirmed, systems marked wrong, and your settings.
  It cannot be rebuilt from anything, so back it up.
  A newer seed placed beside the exe is installed on the next start, and your own tables are migrated across into it; the old file is kept beside it.
- The journal is found through Windows' Saved Games folder, so no path needs setting.
- Run the game **borderless**: the FSS reading captures the game's window and cannot see a fullscreen one.
- The HUD sizes itself to the game window's height (100% at 1440 px), whatever Windows' display scaling; the Settings tab scales it further.
- Only one overlay can use a state file at a time.

### Settings

Everything you choose is on the Settings tab, saved as you change it and applied at once, on four pages:

- General: play sounds, drive the VKB throttle lights, global navigation keys, show the HUD when Elite is not in front, drag panes with the mouse, HUD size (70–175%) and opacity (50–100%);
- Keybinds: click an action's button, then press the new key;
- Mini Map: which kinds get dots on the galaxy map's mini map;
- Debug: keep every FSS screenshot, for recalibrating the spectrum prediction.

### Keys

The keys work only while Elite or the overlay is in front, and always pass through to the game.

| default key | action |
| --- | --- |
| `Up` / `Down` | previous / next row; the row the cursor lands on is copied to the clipboard |
| `Page Up` / `Page Down` | previous / next table on screen |
| `Shift+N` | plot a fewest-jump neutron route to the selected row; again to clear it |
| `Shift+Backspace` | mark the selected prediction as not existing: it would not plot, or nothing was there |
| `Shift+A` | the selected prediction is the plotted route's destination under another name |

Paste the copied name into the galaxy map's search and plot.

## For developers

The project has two halves sharing one data contract:

- **The model** (Python and DuckDB SQL, `etl/`, `schema/`, `common/`, `scripts/`): downloads Spansh, EDSM, EDAstro and Canonn data and merges it into `elite_mapping.duckdb`, then derives the predictions, the exobiology odds and everything else the overlay reads.
  It has no build system or package manifest: it needs Python with the `duckdb` package at the version the overlay pins (1.5.4); some scripts also use `numpy`, `pandas`, `orjson` or `Pillow`.
- **The overlay** (Rust, `overlay/`): the HUD and the application window, reading a mirror of the model in its own state file and never the model itself.

### Build the overlay

```bash
(cd overlay && cargo build --release)   # needs the Windows SDK for rc.exe; the first build compiles DuckDB
python etl/build_seed.py                 # the seed the exe installs from, built from the model
./explorers-companion.sh                 # or explorers-companion.cmd: runs it against elite_mapping_current.duckdb
```

- `overlay/README.md` covers the build, the flags, what ships and where state lives.
- `explorers-companion.exe --help` lists the flags; they are for development, and everything a player chooses is on the Settings tab.

### Refresh the data

- Each model table has a folder `etl/<table>/` whose `refresh.py` downloads, stages and merges it; order matters where one table resolves against another.
- `.claude/skills/refresh-data/SKILL.md` is the full refresh in order, with the checks each step must pass; `CLAUDE.md` lists every command.
- After a load touching a table the overlay reads, run `python etl/refresh_current.py` with the overlay closed to rebuild its mirror.
- **Read `ETL.md` before changing anything under `etl/`, `schema/` or `scripts/`**: merge-never-drop, natural keys and provenance rules are enforced by review, not by the database.
- There is no test suite; `CLAUDE.md` (*Verification, in place of tests*) says how a change is checked.

### The databases

| file | what it is | written by |
| --- | --- | --- |
| `elite_mapping.duckdb` | **the model**, about 91 GiB: the galaxy per Spansh/EDSM/EDAstro/Canonn. `main` holds the model tables, `staging` the provider downloads, `transform` each load's reshaped input. | `etl/` |
| `elite_mapping_current.duckdb` | **app state**: what this commander has seen, visited and found, and the overlay's settings (`main`), plus `model`, a mirror of the model tables the overlay reads. | the overlay (`main`); `etl/refresh_current.py` (`model`) |
| `seed/elite_mapping_seed.duckdb` | **the installer seed**: the app-state tables empty plus the model mirror; a player's state file starts as a copy of it. | `etl/build_seed.py` |
| `etl_log.duckdb` | **the run log**: how long each ETL script ran, its outcome, and the rows each stage and merge touched; read with `python scripts/etl_report.py`. | `common/runlog.py` |

- The overlay writes only to its app-state file, and never opens the model, so the model can be re-merged while you fly.
- The model is derived and rebuildable; the app state is not, so back `elite_mapping_current.duckdb` up: losing the model costs a re-ingest, losing the app state costs every hour spent flying.
- `elite_mapping_pre_fresh.duckdb`, when present, is the previous model file `scripts/build_fresh_db.py --swap` keeps as a fallback; delete it once the new model is trusted.
- DuckDB allows one writer per file, and any other open handle blocks it.

### Docs

| file | what |
| --- | --- |
| `CLAUDE.md` | repository overview, the databases, every command, verification |
| `ETL.md` | ETL conventions (authoritative for anything touching data) |
| `overlay/README.md` | overlay build, what ships, where its state lives |
| `overlay/DESIGN.md` | what every pane and tab shows, and why |
| `overlay/FSS_SPECTRUM.md` | how the FSS spectrum is drawn and how the slot table is recalibrated |
| `MODEL.md` | the prediction model and the measurements behind each step |
| `DEAD_ENDS.md` | targets ruled out, with the reason |
| `SOURCES.md` | every source, what it feeds, how they overlap and what each can prove |
| `CLEANUP.md` | what must never be deleted, and why |
| `RARE_DISCOVERABLES.md` | the taxonomy of rare discoverables the model was designed from |
| `lore/RAXXLA.md`, `lore/RAXXLA_LORE.md` | the Raxxla search log and lore (search-space narrowing, never a claimed find) |

## Scope

- The game publishes no catalogue of its systems and no API for undiscovered bodies, so the community datasets are a large, biased sample of the space players have reported.
- The model ranks candidates and states its uncertainty; it cannot establish that anything exists until the game reveals it.
- It models the Live galaxy, not Legacy.

## Data sources and credits

- [Spansh](https://spansh.co.uk): galaxy, body and station dumps; the live carrier and Tritium searches; jump-target lookups.
- [EDSM](https://www.edsm.net): systems, bodies, codex reports and jump-target discovery data.
- [EDAstro](https://edastro.com): sectors, systems and points of interest.
- [Canonn](https://canonn.science): the codex reports behind the exobiology odds, stellar phenomena, points of interest, and the Guardian and Thargoid sites.
- klightspeed's [EliteDangerousRegionMap](https://github.com/klightspeed/EliteDangerousRegionMap) (MIT): the galactic region grid.
- The exobiology species, values and colony distances in `input/exobio_species.parquet` come from Silarn's GPL-2.0 EDMC plugins EDMC-BioScan and EDMC-ExploData (`schema/exobio_species.sql`).
- EDCD's FDevIDs and coriolis-data, the Elite Dangerous Wiki and Elite Dangerous Utilities supply the engineer, ship and Sirius broker tables compiled into the overlay.
- The next-jump panel is modelled on SrvSurvey's.
- `SOURCES.md` lists every source, what it feeds and its caveats.

## Licence

- Apache License 2.0: see `LICENSE` and `NOTICE`.
- Elite Dangerous is a trademark of Frontier Developments plc.
  This project is not affiliated with or endorsed by Frontier Developments.
