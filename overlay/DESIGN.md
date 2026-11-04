# Explorers Companion — sector-ranked rare-object HUD

`explorers-companion.exe`: a HUD of eight panes laid around the game's screen, each shown on the game screens it serves, plus a standard application window with tabs.
`README.md` covers the build, where the state lives and the flags; this file is why it behaves as it does.

```
explorers-companion.cmd                        # follow the journal, state in elite_mapping_current.duckdb
explorers-companion.exe                        # follow the journal, state in %LOCALAPPDATA%\explorers-companion
explorers-companion.exe --sector "Eol Prou"    # force a sector, ignore the journal
```

Everything a player chooses is on the Settings tab and saved in the `setting` table (see *The Settings tab*); the flags are for development.

## What it shows

The sector the commander is in and the 26 around it, one row each, as a bare table that drags from anywhere (see *Sector table*); selecting a row copies the best system in that sector.

- Chrome is hidden by default; the Settings tab's "Title bar and footer" adds the title bar, the live status line (current system, row counts, clock) and the footer.
  With the chrome hidden, footer lines go to the log on every refresh rather than being dropped.

| Column | Meaning |
| --- | --- |
| `SYSTEM` | Predicted system name. Dimmed once the galaxy map has revealed its arrival class, because it is no longer a gamble. |
| `LY` | Light-years from the commander, on every table. A leading `~` marks a boxel centroid rather than a position, good to about ±640 ly at mass code `h`. POIs and plot-only systems have exact coordinates and get a plain number. A dash means unlocated, which is not the same as near. |
| `TYPE` | What kind of target the row is; for a boxel-gap prediction its mass code, rendered `Mass H` and highlighted at `h`. Not called `MC`, because POIs, neutrons and carriers share the column and are not mass codes. |
| `BLK HOLE` `WOLF-RAY` | Black hole, Wolf-Rayet: the two that decide the ordering. |
| `HERBIG` | Herbig Ae/Be, the only prediction whose rate rises with galactocentric radius, so the best rim-ward target. |
| `O-TYPE` | O-type star (~30,000–50,000 K, blue). Concentrated in mass code `g`; the richest sectors sit ~55 kly from Sol on the far side of the core, so check distance before routing. |
| `SUPERGNT` | Supergiant. Mostly mass code `e` by count, densest at `h`. A route plot confirms one only as probable; see below. |
| `NEUTRON` `WHT DWRF` | Neutron star, white dwarf; near their base rate almost everywhere. |

**Every column must be confirmable by a route plot**, because the only thing the overlay learns about an unvisited system is its arrival star.
A helium-rich gas giant fails it, being a planet, so it is not predicted (`DEAD_ENDS.md`).

### Supergiants are confirmed from the letter and the mass code

- The journal's `StarClass` (`FSDTarget`, `StartJump`, `NavRoute.json`) is short codes only: a B supergiant plots as plain `B`.
  The long `B_BlueWhiteSuperGiant` spellings belong to `Scan`, which needs the ship in the system.
- The mass code in the system's name supplies the rest, because a supergiant is far heavier than a main-sequence star of its letter.
  `kinds::arrival_class()` reads a letter in these mass codes as the supergiant, measured over known first stars in the model:

  | Letter | Mass codes | Supergiant share | Elsewhere |
  | --- | --- | --- | --- |
  | `A` | `f` `g` `h` | 100% | 7.8% in `e`, 0 of 2.3 M in `d` |
  | `B` | `h` | 56% | 2.3% in `f`, 0.01% in `e` |
  | `F` | `e` | 67% | 0 of 4.8 M in `d` |
  | `G` | `e` | 55% | 0 of 3.5 M in `c` and `d` |
  | `M` | `e` | 63% | none in `a`–`c` |

- So a `SUPERGNT` confirmation is **probable, not certain**, unlike every other kind; `system_confirmed.star_class` keeps the plain letter, which says so.
- Kinds declare these pairs in `by_mass`; the Rust (`arrival_class`), the SQL (`arrival_sql`, the `ARRIVAL_S`/`ARRIVAL_T` fragments and `CLASS_CASE`) and the known-system probe in `etl/refresh_current.py` all read them from there.
- A `Scan` names the luminosity class, so `system_outcome.found_supergiant` is exact.
- Giants (`K_OrangeGiant`, `M_RedGiant`) are not a kind: they are common (a red giant in about 106,000 `b` and 74,000 `d` systems) and sit in the `d` pool the model does not predict.

### Probability cells

- Each probability is a two-decimal fraction (`0.38`), right-aligned, shown separately.
- Colour is a 10-step red→orange→yellow→green ramp, linear over `0.05`–`0.60`, fixed rather than stretched per sector so a number is always the same colour.
  The range is measured: the 3,669,169 displayed values at or above `0.05` have median `0.163`, p99 `0.576`, max `0.576`, so most cells land red or orange and green stays rare enough to mean something.
- A `-` (below `0.01`, `theme::MIN_SHOWN_PROBABILITY`) is uniformly dim.
  That bound is deliberately not the gradient's `0.05`: one answers "is this worth a line at all", the other "what does a colour mean"; values between clamp to the bottom step.
- A sector row's probability cells sum each probability over every boxel-predicted, unvisited system in the sector: the expected number of undiscovered objects of each type.
  Plot-only systems are not summed; their count is in the footer.
  The table keeps room for the 27 sectors and the `REGION` line.
  These sums use the **count** ramp: the same ten colours, log-scaled over 0.1 to 100 expected objects, fixed, because 0.6 expected black holes must not paint the same green as a 60% chance of one.

### Probabilities are never combined

- There is no headline `RARE%`: the `p_wr` column comment says it competes with `p_bh` for the same primary star, so the two must never be added or multiplied.
- The ranking uses `max(BH, WR)`, which needs no independence assumption.
- Only BH and WR sort the list; the other five are shown but not ranked on, because neutrons and white dwarfs would rank by how ordinary a system is.
- A sector's candidates are ranked heaviest mass code first, then by probability, then by expected body count and alphabetically; never by distance, because everything in a sector is already close.
  Mass code leads so that every `h` system in the sector is offered before any lighter one, whatever its odds; `Σ H` says how many there are.

### Read the ranking with this caveat

Every `p` is fitted per (mass code, plane_r band), and a sector sits inside one band, so a sector offers about four distinct rows, one per mass code present.
**Within a mass code the ordering is not meaningful**; that is the first thing to fix before trusting a rank inside one.

### What is in the pool

**Boxel-predicted only.** The `is_catalog` column comment says "always filter or group by this":

| | rows | what it is |
| --- | ---: | --- |
| `is_catalog = TRUE` | 2,300,895 | **Excluded.** Plot only: in the dumps with exact coordinates but no body data, the shape a plotted route leaves (`SOURCES.md`). The model's column is still `is_catalog`. |
| `is_catalog = FALSE` | 306,770 | **Shown.** Boxel-predicted: in no dump, inferred from a gap in the Stellar Forge's index, or a sector's guessed first `h` or `g` system. |

- Gaps reach only 5,428 of 12,110 sectors; with the first-system guesses, 11,669 sectors have a row before any gate opens, most of them only guesses at a low `p_exist`; the overlay says which kind of empty a table is.
- Mass code `e` dominates: e 159,045, f 14,336, g 94,174, h 39,215 (g and h include 86,035 first-system guesses, 60,934 of them gated).
  An `e` row's best rare can be an order of magnitude below an `h` row's.
- Coordinates are the boxel centroid, up to 1280 ly across: you can arrive at the exact point and find nothing.
- The gap layer is thin and core-biased: a lower bound, not a census; the first-system guesses read high (`p_exist`).

**At least 1% on one rare** (`MIN_RARE` in `src/database.rs`): `≥ 0.01` on at least one of `BH`, `WR`, `HERBIG`, `O-TYPE`, `SUPERGNT`, per column, never summed.

- `NEUTRON` and `WHT DWRF` are excluded from the test because, at base rate everywhere, they would pass everything.
- It removes 9,002 of 306,770 rows (7,522 `e`, 160 `f`, 657 `g`, 663 `h`), leaving 297,768 across 11,809 sectors; the weakest survivor offers 0.0102 on its best rare.
  It is in practice a filter on `e`, and raising it would cut into `e` first and hardly touch `f`/`g`/`h`.
- A sector's candidates exempt `h` from it, so all of a sector's `h` systems are offered whatever their odds; the footer's counts (`sql/sector_summary.sql`) still apply it.

**Not marked wrong.** A system `SHIFT+BACKSPACE` put in `system_wrong` leaves the rows and every sum built from this pool: the sector rows, the `REGION` total and the Map tab, so retiring a sector's only Wolf-Rayet candidate takes that sector's `WOLF-RAY` sum to zero at once.

**Not gated.** The first system of a sector's g boxel (`<sector> <letters> g0`) is predicted only behind the sector's `AA-A h0`: where the model does not know that h0, the row's `gated_by` names it, and the `{{UNGATED}}` fragment (part of `{{OFFERABLE}}`, the one filter every pool applies) keeps the row out of the rows and every sum until the h0 is in `system_seen` (plotted) or `system_visited`.
So plotting a sector's h0 adds its g probes at once, with no refresh.
Lookups that recognise a system (`record_seen`, `system_pos`, `outcome_visit`) read past the gate, so a gated system plotted directly is still known as a prediction.

**Probabilities include existence.** A first-system guess may not exist, so its `p_*` columns arrive already multiplied by `p_exist` from the model; the HUD shows and sums them as they are.

**Not visited, and arrival class not yet revealed.** A route plot rewrites `NavRoute.json` with every hop's class and `FSDTarget` gives one; a boxel prediction asks only "what is the arrival star", so a revealed class settles it (rare: it moves to Confirmed; ordinary: nothing is left to gamble on).

- Every pool applies this test: the sector rows' sums and candidates and the `REGION` total.
  Applying it to the rows alone makes a route plot through a neighbour invisible: Graea Hypa had 160 unvisited predictions of which 106 were already classed, summing to 45.5 expected black holes against a true 3.5, and 172 sectors carried some version of that error.
- A revealed class reaches a prediction three ways (`{{SEEN_JOIN}}` in `database::fragments()`): by name, by the hop's `SystemAddress`, and through `system_alias`.
- The address arm also covers boxel predictions, which have no id64 in the model: `sql/boxel_id64.sql` derives the address from the mass code, the grid cell holding the boxel centroid and the index at the end of the name.
  Crafted sector spheres overlap, so the galaxy map routes a predicted name such as `Col 359 Sector IH-V e2-13` to a system it calls `Stock 1 Sector HW-W e1-13`.
  Both names point at the same boxel and index, so the hop's address equals the derived one and the plot settles the row with no keypress.
  The derived address agrees with the hop's address for all 20 `SHIFT+A` aliases whose two names share an index; the 3 that disagree pair different indices.

## Sector table

The left pane's one table: the 27 grid cubes of the 3×3×3 block centred on the ship's, the ship's own among them, each with the expected objects left in it, so "is this sector worth staying in" is decided against its neighbours.
The ship's sector is not listed system by system: selecting its row copies its best system, exactly as a neighbour's row does.

| Column | Meaning |
| --- | --- |
| `SYSTEM` | the sector's name; the ship's own sector in green |
| `Σ H` `Σ G` `Σ F` `Σ E` | how many systems of mass code `h`, `g`, `f`, `e` the sector's pool holds; `Σ H` highlighted when above zero |
| `LY` | light years from the ship to the system the row copies, with `~` because it is a boxel centroid; a dash when the row copies nothing but the sector name |
| probabilities | expected objects of each type, summed over the pool, on the count ramp |

- Procedural sectors are 1280 ly cubes on one grid, origin (−49985, −40985, −24105), and `sector.sector_id` is the cell, `x + 128·y + 16384·z`.
  The ship's cell is computed from its position, so it works inside a hand-named sphere too.
- There are always 27 rows, in three groups ordered as they stand in space: the 9 cubes above the ship's layer, then the 9 in it, then the 9 below it.
  Each group starts with the cube straight above, at, or below the ship's, then goes clockwise from north as seen from above: N, NE, E, SE, S, SW, W, NW, with north +z and east +x.
  The grid has six populated layers, and the galactic plane sits on the boundary between the middle two (y ≈ −25 ly), so near the plane one vertical group is tens of light-years away.
- The table has no picture of where a cube lies: the selected row lights its sector's name on the map pane (see *The sector mini map*).
- A faint dotted 1 px line, one dot in every `TABLE_RULE_STEP` (3) pixels in `TABLE_RULE`, divides the sector table's rows; Nearest has none.
- An empty cube keeps its row with `-` in every column.
  A named one is still selectable and copies the sector's own name, so its emptiness can be checked against the galaxy map or EDSM; an unnamed one is skipped, because nothing in it can be copied.
- A cube no system we know of lies in has no `sector` row and so no name; it shows `unnamed sector` in grey and is reached by hand on the galaxy map.
  Most of these sit beyond the outermost populated layers.
- Systems named under a hand-authored sector are not counted in the cube they lie in: their `sector` is the sphere's name, which has no grid cell.
- The pool is the same for every row (boxel-predicted, not plot only, not visited, not classed, not marked wrong), or the comparison would be between two different things.
- Its last line is the current region's `REGION` total over the same boxel-predicted pool, so a sector reads against the whole region; it shows the region's bare name, and the cursor skips it.
  The region is the sector's; in a hand-named system, whose `crafted` sentinel has none, it is the `region_map` cell under the ship (`sql/region_of.sql`).
  The region's plot-only total is not shown: no HUD table lists plot-only systems.
  In hand-named space there is no region, so there is no line.

### The sector mini map

The map pane is the sector table's 3×3×3 block seen from above, a 3×3 grid with north (+z) up and east (+x) right, set in the galaxy around it.

- The pane fills the space above the left pane: as wide as it, and as tall as is left up to the top of the screen the left pane is on (`MonitorFromWindow`), with `EDGE_MARGIN` between the two and at the top, as at the left pane's edges.
  `Overlay::fit_above()` re-measures this on every redraw, so it follows the left pane's size and position; it cannot be dragged itself.
- The grid keeps its own size, centred in the pane: every cell is square, because sectors are 1,280 ly cubes, and as wide as the longest of the 27 names.
  The rest of the pane shows the galaxy around the block at the grid's scale, so a larger pane shows more of it, not a larger grid.
- Each cell is one column of the block and lists its three sectors top to bottom: the one above the ship's layer, the one in it, the one below.
  The names are deliberately quiet greys, so the route and the stars read first: the ship's own `MINIMAP_NAME_HERE`, the rest of its layer `MINIMAP_NAME`, above, below and any `unnamed sector` the faintest, `MINIMAP_NAME_OFF`.
- The names come from the rows the sector table already holds (`App::rows[SECT]`), so the map agrees with the table by construction.
- The sector table's selected row lights its name on the map in `MINIMAP_NAME_LIT`, in whichever of the three lines it stands, so moving the cursor through the table shows where each sector lies; with the cursor in another table nothing is lit.
- The background is `galaxy_density`, the Map tab's star glow, and the region borders from `region_map`, the Map tab's 49.35 ly region grid, drawn where two neighbouring pixels fall in different regions, in `MINIMAP_REGION_BORDER`.
  `sql/minimap_density.sql` and `sql/minimap_regions.sql` return both for the block plus `MINIMAP_PAD_CELLS` (64) density cells, about 6,300 ly, on every side, enough for the pane at any HUD font; they are asked when the ship moves, and by every refresh until one asked from the ship's position has been painted (`App::painted_pos`), as a newer refresh supersedes an unstarted one.
  `MiniDensity::at()` interpolates the glow between cell centres so the 98.7 ly cells do not show as blocks.
- The glow is stretched on a log scale between the 2nd and 99th percentile of what is drawn (`MINIMAP_STRETCH`), so neither a uniformly dense block nor one bright cell flattens it.
- It fades to nothing over the last third of a cell's width at the pane's edges (`MINIMAP_MARGIN_DIV`), round at the corners.
  The glow is drawn at `MINIMAP_ALPHA` (0.55) of the pane's opacity and the region borders at `MINIMAP_REGION_ALPHA` (0.7), so the game shows through; text, grid lines and the route stay fully opaque except where they cross the fading edge.
  The ship's cell is tinted toward `CUBE_FOOTPRINT`.
- The background is computed once per block and pane size and cached (`Overlay::backdrop()`), because it costs a log and an interpolation per pixel of a pane that can be a million pixels.
- This commander's confirmed objects not yet visited (`sql/map_confirmed.sql`, the Map tab's dots) are `MINIMAP_DOT` (2) pixel squares in their kind's heading colour from the sector table (`theme::kind_colour()`, the header colour for a kind with none), under the route.
  They are drawn in `theme::dot_rank()` order, so where dots overlap a Wolf-Rayet covers the rest and a black hole covers everything.
  They are re-read with every table refresh, so a plot that confirms new ones shows them at once.
- The commander's carrier route is drawn under the ship's route, one pixel of quiet violet (`MINIMAP_CARRIER_ROUTE`) with a small dot at each stop.
  It is `Database::carrier_path()`: from the carrier's position, the pick of `sql/carrier_next.sql` repeated from each stop at the full 500 ly until the Carrier tab's destination, at most `CARRIER_PATH_HOPS` (100), so its first leg is the carrier's next jump.
  Each pick takes ~40 ms, so the chain is worked out only when the carrier view is re-read (a carrier event or a new destination), not on every redraw.
  It does not follow a jump scheduled in game to anywhere else; with no destination set there is no line.
- The plotted route (`NavRoute.json`, the hops *Next jump* reads) is drawn over it by `jump::map_route()`: a dot at every stop with known coordinates, joined by lines.
  The next leg is `JUMP_CYAN`, a leg longer than the unboosted range is `JUMP_TEAL`, any other leg `JUMP_ORANGE`; legs already flown, and the stops they leave, take the dim `JUMP_DIM` / `JUMP_TEAL_DIM`.
  The ship's place on the route is its current system; when that is not on the route, the first leg is the next.
  It is projected on the galactic plane, ignoring y, from the block's corner `sql/minimap_density.sql` returns (one row even where nothing is known), and clipped to the pane.
- Two icons are drawn last, over the dots, both routes and the sector names, with the same projection and clipped to the pane; a position that is unknown or falls outside the pane draws nothing.
  - The carrier: the carrier line's icon (`carrier_icon()`), as tall as a text line and in the same state colour, at the carrier's position (`journal::Carrier::pos`, as the carrier view resolved it: the journal's `StarPos`, else the model's position for the system, else the centre of its id64 boxel).
    That is the carrier route's first point when a destination is set, and it is drawn without one too.
  - The ship, over the carrier: a dot in `MINIMAP_SHIP` (`#00ffff`, the galaxy map's own colour for the current system) at the current system (`App::pos`), its radius swelling from `MINIMAP_SHIP_R` 2 to 5 pixels and back every `MINIMAP_SHIP_PULSE_MS` (1.2 s) on a cosine (`pulse_radius()`).
  - The pulse runs on `PULSE_TIMER`, every `MINIMAP_SHIP_STEP_MS` (80 ms) on the map pane's own window, started by `App::check_focus()` only while the map pane is shown and the position known, and killed otherwise.
    A step repaints the map pane alone, and only when the whole-pixel radius has changed, about 6 repaints a period; the backdrop is cached, so a repaint costs the copy and the alpha pass over the pane's pixels, not the glow.
- The glow measures where commanders have reported systems, not real star density, as the Map tab's does.
- With no position there are no sector rows, and the pane is empty.

### What a sector row copies

- The best system in that sector: heaviest mass code first, then the `{{RANK_BY}}` fragment `database::fragments()` builds (`greatest(p_bh, p_wr)`), the one ranking expression in the app.
- With no candidate it hands back the sector name (`Row::target()` falls back to the shown name).
  That name is not a guess, so marking it wrong and aliasing it refuse (`Row::names_a_system()`).
- Summed per-type probabilities are not used to pick the system: across 2,874 sectors the two picks differed in 444, differed about the mass code in all 444, and the summed pick was worse on `greatest(p_bh, p_wr)` in 444 of 444 (mean 0.46 → 0.40), because numerous neutrons and white dwarfs outweigh the column that matters.
- The sector columns stay sums: they answer "is this sector worth the trip", a question about everything in it.

### The row caches ten systems, not one

- The query returns `database::SECTOR_CANDIDATES` (10) candidates in ranking order, carried on the row as `candidates`; `candidates[1]` is the pick.
- Plotting to the pick answers it, so what belongs on the clipboard is the next candidate.
  `App::advance_clipboard()` answers from memory before anything touches the database, instead of waiting ~2.0 s of SQL for `App::place_cursor()` at the end of the repaint.
- Through `App::successor()` the second candidate is what the query would return once the first is answered; for every other table the successor is the first surviving row below the cursor in the rows last painted.
  Both skip every answered name, since one plot often settles several.
- Verified against the database: settle the pick and re-query, and the new pick is the cached next one; settle two, and it is the cached third.
  The extra nine cost ~3 ms, because the window function already ranked the whole partition.

## Eight HUD panes

The HUD is eight layered windows of the one `Overlay` type, told apart by `win::overlay::Pane`, all repainted from the one `Scene` on every redraw.

### Size follows the game

The HUD is drawn in the game's pixels, not Windows' DPI: its size is `win::overlay::hud_scale()`, the game window's client height over `REFERENCE_HEIGHT` (1440) times the Settings tab's HUD size.

- 1440 is the height every pixel constant in `theme.rs` was tuned at, so a 1440-high game at 100% draws exactly those pixels.
  A 1080 game draws at 0.75, so the top pane still fits between the canopy's comms and ship panels; a 2160 one at 1.5.
- The game decides how big the canopy is, so Windows' display scaling, which the game ignores, must not change the HUD either.
- The automatic part never goes under `MIN_AUTO_SCALE` (0.5), below which the text stops being legible; the HUD size (70–175%) multiplies on top.
- The scale is applied in one place: `Style` carries it, fonts are made at `FONT_PT` (11) minus the pane's drop times the scale, and every pixel constant passes through `Overlay::px()`.
  Most geometry is in characters and lines and follows the fonts on its own.
- Without the game window the primary screen's height stands in; the journal poll re-reads the game's height, and a change re-styles every pane (`App::follow_game_height()`), which also re-anchors them, each to its saved place if it has one.
- The FSS marks are sized from the bar they sit on, never from the scale.

- **Left** (`Pane::Left`, at the screen's left edge, its bottom `EDGE_MARGIN` above the screen's bottom): the sector table, with no heading, and the footer.
  - Its font is `theme::SECTOR_FONT_DROP` (1) point under `FONT_PT`, its rows `SECTOR_ROW_TRIM` (1) pixel shorter than the other tables'.
  - It sits on a dark panel, `PANEL_BG` at `PANEL_ALPHA` (0.6) of the pane's opacity, because at the bottom of the screen it lies over the lit cockpit interior.
  - It keeps its bottom edge when it resizes, and dragging it moves that edge, so it grows upward.
- **Top** (`Pane::Top`, centred on the primary screen): what is happening now and next.
  The Nearest table on the left, the route being flown on the right (see *Next jump*), and under both the carrier line (see *The carrier line*).
  - Its width never changes: the table is as wide as its columns, `TOP_TABLE_GAP` (4) characters separate it from the route, and the route is `ROUTE_CHARS` (54) characters, all fixed by the font.
    A centred pane that resized with a system name would shift every heading on every jump.
  - Its height is at least the Nearest table's full row count, reserved before the table's first rows arrive, so the pane is drawn at its size from the start.
  - The route fits its text into that width, ending anything too long with `…` (`Overlay::clipped()`).
  - The total must fit between the game's own comms panel and ship panel at the top of the canopy, about 800 px apart on a 5120 px wide screen.
  - It sits on the same dark panel as the left pane, so it reads over a dense star field.
  - Its font is `theme::TOP_FONT_DROP` (2) points under `FONT_PT`; it keeps its centre when it resizes, and dragging it moves that centre.
- **System** (`Pane::System`, centred across the primary screen, its top `SYSTEM_MAP_TOP` pixels down at a 1440 px game height and scaled with it, below the system map's system name): every body in the system the commander is in worth flying to and the system's points of interest (see *The system map pane*), in the top pane's font, on the dark panel.
  It keeps its centre when it resizes, and dragging it moves that centre.
- **Coords** (`Pane::Coords`, centred across the primary screen, its top `GALAXY_MAP_TOP` pixels down at a 1440 px game height and scaled with it, below the galaxy map's search bar): the coordinates of the current system and the plotted route's destination (see *Coordinates on the galaxy map*), in the top pane's font, on the dark panel.
  It keeps its centre when it resizes, and dragging it moves that centre.
- **Popup** (`Pane::Popup`, centred across the primary screen, its middle three quarters of the way down so it clears the galaxy map's centre): the route popup (see *Route popup*), in `FONT_PT`; it cannot be dragged.
- **Map** (`Pane::Map`, above the left pane up to the screen's top): the sector mini map (see *The sector mini map*), in the top pane's font.
- **Plan** (`Pane::Plan`, against the primary screen's right edge, `EDGE_MARGIN` from the top): the galaxy-map Nearest table, under it the `POI` table, then the carrier table, and under that the unlogged biology nearby (see *Exobiology*), in the top pane's font, on the dark panel because the galaxy map behind it is busy.
  Every target worth choosing a destination for is in this one place, on the screen where the destination is chosen.
  It keeps its right edge when it resizes; it cannot be dragged.
  - The galaxy-map Nearest table (`theme::plan_nearest_columns()`): the stars and the carrier of the top pane's Nearest, as `NEAREST`, `SYSTEM` and `LY` (see *Nearest on the galaxy map*).
  - `POI`: the `POI_TABLE_ROWS` (10) nearest points of interest not yet visited (`sql/poi_nearest.sql`), as `POI` (what is there: `K08-Type Anomaly`, `Flavum Bullet Mollusc`), `SYSTEM` and `LY`.
    The same query feeds Nearest's `POI` row, its first row, so the two cannot disagree.
  - The carrier table: the first `CARRIER_STOPS` (5) stops of the carrier route drawn on the map (`Database::carrier_path()`, `App::set_carrier_jump()`), as `CARRIER` (`Next`, then `Jump 2`…`Jump 5`), `SYSTEM`, and `LY`, the length of that jump.
    Its first row is the carrier's next jump, which nothing else on the HUD shows.
    A route longer than that adds its last stop as a sixth row, `Jump N` where N is the number of jumps to get there; it is the destination unless the route stops short of it.
    It has rows only while a carrier destination is set and a known system within range gets closer to it, and moves with every carrier event.
  - The three tables' first columns are all `POI_TYPE_W` (24) wide, so they align, and every table and sheet in the pane ends `SYSTEM`, `LY`.
  - The nearby-biology sheet under them is stretched to their width: its `SYSTEM` column takes the difference (`MIN_FLEX_CHARS`, 8, at least), and a name too long for it ends with `…`.
- **Marks** (`Pane::Marks`, laid along the game's own spectrum bar, wherever the last reading found it): the predicted icons and warnings (see *Marks on the bar*); it cannot be dragged and moves with the bar.
- The marks pane is drawn fully opaque, whatever the HUD opacity, because the game's icons are: at the default 0.85 the background tinted its grey-white icons blue.
  It shows in screen captures, its own included, which is safe: the prediction's one reading is taken as the FSS opens, before any mark is drawn, a labelling scan reads only the icon row below the line, and the marks sit 0.029 to 0.055 of the bar above the line, beyond the spikes' 0.026.
- Each pane is shown or hidden by the game screen, read from `Status.json`'s `GuiFocus` (`GUI_SHOWS_PLANNING` / `GUI_HIDES_TOP` / `GUI_SYSTEM_MAP` in `src/app.rs`), and all hide when Elite loses focus.
  The left, map and plan panes are for choosing where to go, so they appear only on the galaxy map, whether opened from the ship or from carrier management.
  The system pane shows on the system map, for choosing which body to fly to, and the coords pane on the galaxy map, for where the destination is; each only while it has a row:

  | screen (`GuiFocus`) | left | top | system | coords | map | plan |
  | --- | --- | --- | --- | --- | --- | --- |
  | galaxy map (6) | shown: where a target is copied from for the map's search | hidden: it covers the map's search and info panels | hidden | shown: the destination's coordinates | shown: the plotted route is drawn on it | shown |
  | system map (7) | hidden | hidden | shown: the body to fly to is chosen there | hidden | hidden | hidden |
  | station services (5), FSS (9), DSS (10) | hidden | hidden | hidden | hidden | hidden | hidden |
  | every other screen, flight included | hidden | shown | hidden | hidden | hidden | hidden |

  `GuiFocus` can stay at 11 (Codex) after the Codex is closed, even on the galaxy map; while it does, the planning panes stay hidden, and opening and closing the Codex resets it.
  "Show the HUD when Elite is not in front" overrides only the focus test, not this one.

## Next jump

The right side of the top pane, modelled on SrvSurvey's `PlotJumpInfo`; its logic is `src/jump.rs`, which draws nothing and is unit-tested.

- **The route is shown** while the next jump target (`FSDTarget`) is a hop still ahead on the plotted route (`NavRoute.json`), or while the FSD is charging (`Status.json` flag `1 << 17`).
- **Without a route** only the top is drawn: the system the ship is in, its star and its system line (`jump::stay`).
- **Above the line**, level with Nearest's headings: the target's counts and its biology line, each only when it has something to say.
- **The line**: what is left of the route, top to bottom, down to the bottom of the Nearest table beside it and never shorter than `ROUTE_LINE_MIN_ROWS` (3) rows below the system the ship is in and its line (`jump::ahead`).
  Hops already flown are not drawn, so it rescales with every jump.
  - **Top**: the system the ship is in, named and ticked in cyan, with its star spelled out and coloured as the next system's is (below), from the jump's `StarClass` or the arrival star's `Scan`, with Spansh's subtype once looked up.
  - **Under the top**: the system's line (see *The system line*), in the name column.
  - The leg from the top to the next system ends in a filled arrowhead `ROUTE_ARROW_H` (8) px tall and `2 × ROUTE_ARROW_HALF` (10) px wide, its point on the next system's tick, in the next system's light grey (`ROUTE_NEXT`): the direction of travel.
  - **Next**: the system being jumped to, named and ticked in light grey (`ROUTE_NEXT`): its name, the carrier icon, its star and the jump's length right-aligned; under it, the discovery line, starting where the system names start, as the current system's body icon does.
    Cyan and light grey are the galaxy map's own colours for these two.
  - **Bottom**: the final destination in orange, its star from its `NavRoute.json` `StarClass` (`Panel::dest_star`, `jump::destination`), and the light years left from the ship right-aligned (`jump::ahead_ly`).
    Only the target is looked up, so the destination's star is its class spelled out, never Spansh's subtype.
  - The three stars share one column: `ROUTE_GAP_CHARS` (2) characters past the widest of the names shown, measured in the row font with GDI, the next system's counting its carrier icon (`jump::star_column`), so a name one digit longer than another does not shift its star.
  - Between them each hop is a tick, unnamed: 2 px tall (`ROUTE_TICK_H`), 19 px across for a scoopable star (`KGBFOAM`, `ROUTE_TICK`) and 13 px for any other (`ROUTE_TICK_SHORT`).
  - Every hop after the next one is orange, or teal where it is longer than the ship's unboosted range (`ship::jump_range`): a neutron or injection boost.
    The leg to the next system is `ROUTE_NEXT` whatever its length, the colour of the system it points at.
  - The next system sits a fixed row below the system line, so the first hop is not to scale.
    From the next system on, the line is scaled by distance, so a neutron jump reads as long as it is.
- **In hyperspace** the line holds as it was when the jump began, from `StartJump` (`JumpType` `Hyperspace`) to the arrival's `FSDJump`, `CarrierJump` or `Location`.
  - The game writes the following hop's `FSDTarget`, or `NavRouteClear`, about 6 s into the tunnel, before the ship has arrived; redrawn from that, the line would move on while the ship is still between the two systems.
  - The leg from the ship's system to the one being jumped to, bar and arrowhead, glows up and down like a standby light: a cosine once per `HYPER_PULSE_MS` (2.4 s), between `ROUTE_NEXT` and `HYPER_REST` (0.6) of the way to the panel (`overlay::standby_glow`, `App::step_hyper`, every `HYPER_STEP_MS`, 40 ms).
  - Look-ups for the new target keep running underneath, so the line redrawn on arrival already has what they found.
  - A jump with no arrival after `HYPER_MAX_S` (90 s), a crash or a lost journal line, lets the line go.
- **Star**: spelled out from the route's class code (`jump::star_name`: `A (Blue-White) Star`, `White Dwarf (DA) Star`), with EDSM's or Spansh's main-star subtype and spectral class once known (`A9 VI`).
  - A letter that `kinds::arrival_class()` reads as a supergiant from the mass code is spelled as the supergiant with a leading `~` (`~B (Blue-White super giant) Star`, `jump::class_text`), the HUD's mark for a value that is probable rather than reported (see *Supergiants are confirmed from the letter and the mass code*); a looked-up subtype replaces it.
  A predicted kind takes its kind's colour, the one its sector-table heading and map dots wear (`jump::target_rgb`, `theme::kind_colour`); any other class takes the galaxy map's star-class legend (`theme::star_colour`), orange where the legend has no entry.
- **Discovery and counts**, fetched once per target on a background thread (`src/lookup.rs`), so a slow request never stalls the HUD:
  - EDSM `api-system-v1/bodies?systemName=` gives the discoverer, the date and the body count; the Spansh dump `api/dump/<id64>/` gives the bodies, their biological and geological signals, and the stations and carriers.
  - The discovery line reads `Discovered by <cmdr> YYYY-MM-DD` (EDSM's real-world date, never the in-game year) or `Undiscovered`, which means neither feed has a body for it: green (`Role::Confirmed`) on a rare class, a first discovery and the case this project exists for, blue otherwise.
  - The counts read `Bodies: 24 (3 bio)`, then biological and geological signals, stations and carriers, non-zero ones only (`jump::counts_text`).
  - The carrier icon shows when Spansh lists a carrier at the target (`jump::carrier`): amber if any there lets everyone dock (`carrierDockingAccess` `All`), grey if all are restricted.
    Only the target is looked up, so no other hop carries one.
- **Biology**: when the target has a `system_exobio` row (`sql/exobio_target.sql`, matched on its id64 from the route or `FSDTarget`), `exobio::target_line`: its expected value, candidate bodies (`orbit-only/all` when some have signals), the best body with its likely species, and the year it was last reported; dim when somebody has already mapped or codexed a body there.

## Route popup

A plot that rewrites `NavRoute.json` puts a box in the lower half of the screen listing every target on the new route, so the plot's finds are seen on the galaxy map where the route was plotted.

- **Rows**: each hop after the origin whose arrival class is a Confirmed kind (`kinds::is_rare_class` after `kinds::arrival_class`, so a supergiant read from the letter and mass code counts), in route order, the system name in white and the star spelled out (`jump::star_name`) in its kind's colour (`jump::target_rgb`).
- **Title**: `N targets on this route`, in the header band's orange over the header band's background, which fills the whole box so it reads over the map.
- It shows for `ROUTE_POPUP` (2 s, `src/app.rs`) from the plot, on every screen including the galaxy map, and hides at once when Elite loses focus.
- A route with no target shows nothing, and neither does the route already in `NavRoute.json` when the overlay starts.
- It lists what the plot revealed, so a system somebody has already scanned is listed too; Nearest's find rows leave those out.
- The logic is `jump::route_popup`, unit-tested; the pane only draws it.

## Exobiology

Where biology nobody has logged is likely to be, from the model's `exobio_odds` and `system_exobio` (`ETL.md` has how they are built) and from the journal.
The current system's biology is on the system map, in the system pane (see *The system map pane*), and the systems nearby are in the plan pane on the galaxy map, where a system to fly to is chosen.
The logic is `src/exobio.rs`, unit-tested, and the selection is `sql/exobio_*.sql`.
The jump target's biology is a line beside the route (see *Next jump*).

- **Nearby** (`sql/exobio_nearby.sql`): the 8 most valuable `system_exobio` systems within `EXOBIO_RANGE_LY` (250 ly), excluding systems visited; re-read on every arrival.
  Its columns are `SEEN` (the year somebody last reported biology there), `BODIES`, `VALUE`, `SYSTEM`, `LY`.
  A system where somebody has already mapped or codexed a body is dim.
- Values are base Vista Genomics prices in `M`/`G`, before the first-log bonus, and the model's are low (`schema/exobio_odds.sql` says by how much); rank by them rather than bank them.

## Coordinates on the galaxy map

The galaxy map shows no system's coordinates, so the coords pane shows them there as one `Coordinates` sheet (`jump::coords_sheet()`, `App::update_coords()`).

- `CURRENT`: the system the commander is in, at the position the journal's last jump or location event gave.
- `DESTINATION`: the last system of the plotted route, at its `StarPos` in `NavRoute.json`.
- `DIFFERENCE`: the destination less the current system, on each axis, while both are known.
- The columns are the galaxy's axes as compass directions: `EAST/WEST` is x, `NORTH/SOUTH` is z, toward the galactic core being north, and `UP/DOWN` is y, the height above the galactic plane.
  Each value is a distance followed by an arrow for its direction, so no sign has to be read: `→` east and `←` west, `↑` north and `↓` south as the map is drawn, `▲` up and `▼` down (`6,750.75 ←`).
- Distances are shown to 0.01 ly; the journal gives positions in 1/32 ly steps.

## The system map pane

Every body in the current system worth flying to, ranked for landing, in the system pane on the system map; its logic is `exobio::Here` and `exobio::body_list()`, unit-tested, and the selection is `sql/system_bodies.sql` and `sql/system_pois.sql`.

- `exobio::Here` folds the journal: a jump or `Location` to a new `SystemAddress` starts it afresh.
  - `Scan` gives the planet class, atmosphere, temperature, `Volcanism`, distance from arrival, `Landable` and `WasFootfalled`.
  - `FSSBodySignals` and `SAASignalsFound` give the biological and geological signal counts, and a surface scan's `Genuses` the genera present.
  - `ScanOrganic` (`Analyse`) gives each species logged; the arrival star comes from `StartJump`'s `StarClass` or the scan of the star at 0 ls.
  - A `CodexEntry` in this system re-reads the pane, so a geology just logged turns white.
  - A body the journal has scanned, or given signals for, has known signals: no biology signal means none.
- On start the latest journal is folded whole, so a restart keeps what was scanned.
- The bodies the Spansh dump reports (`lookup::SystemInfo.targets`, the same fetch as the next-jump counts, made on arrival when the system was not a jump target) are listed before they are scanned: those with a biological or geological signal, Earth-like, water and ammonia worlds, and landable bodies with a thin atmosphere.
  Their atmosphere is put into the journal's spelling, and the journal's own scan and signal counts replace theirs.
  Spansh's signals count as known only where the dump carries a `signals` object.
- **The chances come from the model's `exobio_odds`**, mirrored into the app-state file, by the body's cell: atmosphere, body type, 20 K temperature band and arrival star.
  - The cell is the arrival star's own where it has `EXOBIO_MIN_BODIES` (200) fitted bodies for `p_bio` and `signals_bio`, and `EXOBIO_MIN_CODEXED` (20) codexed bodies for `cr_species` and `likely_species`; the every-star cell otherwise.
  - The journal and Spansh spell classes differently (`High metal content body` / `world`, `Earthlike body` / `Earth-like world`, `sulfur` / `Sulphur`, `neon rich` / `Neon-rich`); the query maps them.
- **One line per body worth landing on, not a table**, drawn like the system line in the top pane (`Overlay::draw_system_list()`), `SYSTEM_ROW_PCT` (150%) of a text line apart, above a closing `Targets: <system>` line with the system's total value at the right:
  - the body's FSS icon (`vector::body()`), its family read from the type (`exobio::family_of()`: rocky, high metal content and metal-rich as rock, icy and rocky ice as ice, then Earth-like, water, ammonia and gas giants);
  - the body's name without the system's, in capitals as the game writes it (`2 A`);
  - a flag (`vector::flag()`, `FIRST_FOOTFALL` on a white pole) in its own column when nobody has set foot on the landable body;
  - each genus the body may hold or holds, as its own icon (`vector::genus()`, each genus always in its own colour from `GENUS_RGB`, whatever the odds) followed by its chance (`53%`) or, once a surface scan has named it, its value (`12.4M`);
  - when the body has biology signals but no genus can be named or predicted, the DNA icon and the signal count instead;
  - the volcano icon and the geological signal count;
  - the body's value, right-aligned in the last column.
  - Names, flags and values each line up in a column, and every genus has its own column, in `GENUS_RGB` order with the bare DNA count last, so a genus sits at the same place on every line; text is the clock's outlined white, so it reads over the bright system map.
- **The genera come from `exobio_genus_odds`** (mirrored), by the body's cell, the arrival star's own rows where its `exobio_odds` cell has `EXOBIO_MIN_CODEXED` (20) codexed bodies and the every-star rows otherwise:
  - before a surface scan, the genera whose chance is at least `GENUS_MIN_CHANCE` (5%), at most `GENUS_ROWS` (4), likeliest first; the chance is the genus's share of codexed bodies when the body has biology signals, and `p_bio` times that share when its signals are unknown;
  - after one, exactly the genera it named (`SAASignalsFound`'s `Genuses`, or Spansh's), each valued at the cell's `cr_genus`, or the mean of the genus's species in `exobio_species` where the cell never saw it;
  - a genus logged with the scanner (`ScanOrganic` `Analyse`, kept as `Body::logged_genera`) leaves the line.
- **Every biology value on a body nobody has set foot on is multiplied by `FIRST_FOOTFALL_BONUS` (5)**, the game's first-logged payout: the journal's `WasFootfalled` false on a body that may be landable, the same test that draws the flag.
- **A body is listed only while something on it is left to do**: a genus not yet logged, biology signals not all logged, a chance of biology with a value, or geology new to the codex.
  A body whose genera are all logged leaves the list, so the pane only ever shows places worth flying to.
- **Value**: the named, unlogged genera's values added up after a surface scan; before it, the unlogged signals times the cell's `cr_species`, or `p_bio × signals_bio × cr_species` when the signals are unknown; each times the first-footfall bonus where it applies.
  Base prices, before the first-log bonus.
- **Order**, in the query: bodies with biology left first, then bodies whose biology is possible, then geology alone; within each, the higher value, then the more geology, then the nearer; at most `SYSTEM_BODY_ROWS` (12).
- **Geology new to the codex**: the geology count is green when the body's geology is probably missing from the commander's codex, and white (`CLOCK_TEXT`) otherwise (`exobio::geo_rgb()`).
  - "In the codex" means a `CodexEntry` in any journal whose `Name` is that geology entry and whose `Region` is the region the system is in, because the codex records geology once per galactic region.
    The region is the current sector's, or the region map's at the ship's position (`sql/region_of.sql`), the same rule as the Codex tab.
  - The geology entries are the 23 `codex_sighting` rows of category `Geology`, keyed `codex_ent_<form>_<material>`: forms `fumarole`, `gas_vents`, `geysers`, `lava_spouts`, `icefumarole`, `icegeysers`; materials such as `watergeysers`, `silicatevapourgeysers`, `ironmagma`.
  - **The FSS settles the material; only the form stays open.** The FSS's `Scan` of a body gives its `Volcanism` (Spansh's `volcanismType` gives it before arrival), which names the material: `metallic magma` reads as `ironmagma`, `rocky magma` as `silicatemagma`, the rest by name.
    No DSS is needed, and a DSS adds nothing: `SAASignalsFound` lists genera for biology but only a count for geology.
    What no scan names is the form (fumarole, gas vent, geyser, lava spout); the candidates are that material's entries in the icy forms on an icy or rocky ice body and the others elsewhere, and only landing tells which form is there.
    The body is green when any candidate is not logged; where a material has one form the answer is exact, otherwise the form present may be one the commander already has.
  - A volcanism with no geology entry of its material (water, ammonia, nitrogen or methane magma), no `Volcanism` yet, or no known region leaves the count white: nothing says it is new.
- **Points of interest**: a small table under the list with the system's POIs from `system_poi` and `poi`, matched on the `SystemAddress` or the name, surface ones first.
  The model attributes POIs to a system, not to a body, so they are not placed on bodies.
- Biology has no pane in flight: the system line's biology count and the jump target's biology line are on the top pane, and the nearby systems on the galaxy map's plan pane.

## FSS spectrum capture

The journal never describes the spectrum: `FSSDiscoveryScan` carries only counts, and a body's class arrives only when it is resolved.
So the overlay captures the screen while the FSS is open and reads the bar with a fixed procedure (`src/spectrum.rs`).
It predicts each body class from the slots the waves light, using a table learned from the commander's captures (`src/slots.rs`).
`overlay/FSS_SPECTRUM.md` describes the spectrum itself and how to recalibrate the table.

- Captures:
  - `GuiFocus` turning 9 (FSS open) starts one after `fss::OPEN_SETTLE` (1.5 s), once the screen has drawn in.
  - An `FSSDiscoveryScan` with the FSS open starts one after `fss::HONK_SETTLE` (1 s).
  - A `Detailed` `Scan` with the FSS open starts one after `fss::SCAN_SETTLE` (1.5 s), once the resolved body's icon is drawn; its class is the `PlanetClass` or `Star <StarType>`, and a belt cluster starts none.
  - While the system has no prediction, a `watch` capture runs every `fss::WATCH_EVERY` (2 s) until one finds the bar, because the bar flashes as the FSS opens.
- A capture is the client area of `Elite - Dangerous (CLIENT)`, copied with `BitBlt`.
  It needs the game borderless, and is skipped when the game is not in the foreground.
- Capturing, reading and PNG encoding run on the `fss` thread.
  Each capture returns a `fss::Watch`: the system, and when the bar was found, its screen position, tips, lit slots and icons.
- By default only the newest open, honk or scan capture is kept, overwriting `last.png`; a first reading that lights a slot the table does not know is logged as `N unknown slot(s)`.
- Screenshots are written only by a build with the `calibrate` feature, which the release leaves out.
- With the Settings tab's "Keep every FSS screenshot" ticked (`fss.keep_captures` in the `setting` table), every capture is kept as calibration data for `scripts/fss_slots.py`.
  Screenshots go to `screenshots\` beside the exe; a developer makes that folder a junction to `log/fss`, where `scripts/fss_slots.py` reads the learning set:
  - open, honk and watch captures as full frames, `<UTC stamp>-<SystemAddress>-<open|honk|watch>.png`;
  - scan captures as full frames, `...-scan-<class>.png`, while fewer than `FRAMES_PER_CLASS` (3) exist, then as a strip around the bar, `...-scan-<class>-strip-<x>-<y>-<width>x<height>.png`, which `reads_every_capture_in_fss_dir` pastes back into a frame;
  - every scan as a row of `tuned.csv` (`stamp,address,body,class,icon`), its icon being the one icon new since the last capture, more than 0.01 from all earlier ones.

### Reading the bar

Everything is measured in shares of the bar's own length L, so the reading does not depend on resolution, aspect ratio or HUD scale.
`reads_the_same_bar_at_other_resolutions` checks this from 1600×900 to 3840×2160.

- **The tick rule** is the longest centred run of ruled pixels in rows 0.50 to 0.97 of the height.
  A ruled pixel is strong (largest channel above 150, 100 above the smallest) and stands out from the rows `RULE_APART` (0.006 of the height) above and below, so a bright nebula does not merge rows into one block.
  A run shorter than a quarter of the height, or more than 0.05 of the width off centre, is not a rule.
- **The line** is the row 0.025 to 0.08 L above the rule with the most columns whose chroma is 30 above the rows 0.012 L above and below.
  - It must reach 60% of the columns; rows within 80% of the best join it, up to 0.004 L either side.
  - Of the rules with a line, the longest wins.
  - The bar is centred on the screen, so its ends are the rule end further from the centre and its mirror, less 0.014 L for the brackets; the needle's glow can break the rule's other end.
  - Positions run from 0 at LOW to 1 at HIGH.
- **A wave pixel** is within 0.6 of the line-to-backdrop distance of the line's colour and at least half that distance from the backdrop, the median of its column 0.035 to 0.06 L above the line.
  Stars, nebulae and grid lines fail this in any HUD colour; a row lit across more than half the bar is a grid line and is ignored.
- **The envelope** of a column is how far wave pixels reach from the line on each side, up to 0.026 L, counting only pixels joined to the line with gaps up to 0.006 L.
- **A spike** is a run of columns whose envelope reaches 0.006 L, gaps up to 0.009 L bridged.
  A run narrower than 0.006 L is kept only if it reaches `TALL_SPIKE` (0.010 L) on both sides of the line and nothing line-coloured lies 0.004 to 0.012 L past the reach, which keeps a spike the needle cuts to a sliver and drops icon glow and scan trails.
  Spikes feed the log, not the prediction.
- **A tip** is a local extreme of the envelope above minus the envelope below, at least `TIP` (0.012 L) from the line.
  A downward tip names its nearest slot, an upward tip the slot half a slot before it (`spectrum::tips()`, `Reading::slots()`); slots are `SLOT` (0.00506 L) apart from `SLOT_ZERO` (0.00037).
- **An icon** is a blob of glyph pixels joined within 0.003 L, 0.008 to 0.035 L below the line:
  - a glyph pixel is white (every channel above 170), or coloured (a channel above 200, chroma above 100) and kept by a 3×3 opening (`DISC_OPEN`, 0.001 L), which erases the 1 to 2 px wave strokes of the same hue;
  - in the needle's columns only white pixels are dropped, so a coloured icon under the needle stays whole;
  - 0.007 to 0.022 L wide, under 0.022 L tall, at least 0.04 L of pixels, centred 0.021 ± 0.004 L below the line;
  - with a halo: the ring 0.0075 to 0.0105 L from its centre at least 20 brighter than the ring 0.012 to 0.014 L out, which a star lacks.
- `spectrum.rs` is tested on painted bars and on crops of real captures in `tests/fixtures/`, pasted back at (1980, 1000) into a 5120×1440 frame.
  `FSS_DIR=../log/fss cargo test --release reads_every -- --ignored --nocapture` prints the reading of every saved capture.

### Naming the slots

- `slots::SLOTS` lists, per slot, each class that lights it and whether those bodies have an atmosphere; `scripts/fss_slots.py --write` writes it.
- `bands::marks()` turns the lit slots into marks:
  - each class of a lit slot gets a mark, so a shared slot (83: high metal content with an atmosphere and airless rocky) gets one per class;
  - lit slots of one class within `SAME_GROUP` (2) slots form one group, marked at their mean, as the game draws one icon per group;
  - an unknown slot is a signal source or asteroid cluster where `bands::RANGES` puts those, and otherwise a warning;
  - an icon the game has already drawn is marked by the nearest range in `RANGES`, unless its class has a mark.
- `bands::RANGES` is Deep Space Network's published range per type (`SOURCES.md`), with asteroid clusters starting at 0.322 where their icons land; it names signals, asteroid clusters and drawn icons, and gives every class its colour family.
- `bands::notable()` lists the worth-scanning families among the marks: Earth-like, water world, ammonia world and signal sources.

### Marks on the bar

Predicted icons are drawn above the line where the game will draw them below it, so prediction and result can be compared icon by icon.

- The prediction is made once per system, from the first reading that finds the bar, and never revised (`App::fss_prediction`, logged as `fss: predicted N mark(s), U unknown, from S lit slot(s) in the <reason> reading`).
  A honk inside the FSS replaces a prediction with no marks.
  Zooming, the needle and resolved bodies change the game's bar, not the marks.
- The marks window lies over the bar the prediction read: the bar's length plus `FSS_MARK_SIDE` (0.02 L) each side, `2 × FSS_MARK_HALF` (0.032 L) tall, centred `FSS_MARK_ABOVE` (0.042 L) above the line, clear of the waves.
- A mark is the game's icon: a disc of radius `FSS_ICON_DISC` (0.005 L) and a halo ring of radius `FSS_ICON_HALO_R` (0.0071 L), `FSS_ICON_RING_W` (0.00095 L) wide, at least 1 px, as thin and as close to the disc as the game's (`vector::body()`); `FSS_ICON_RING_R` (0.0086 L) is the icon's footprint, which places and spaces the marks.
  - The halo is the disc's colour at `FSS_ICON_RING_ALPHA` (0.75), translucent like the game's but bright enough that a 1 px ring still shows at the HUD's size; both are drawn anti-aliased (see *Icons are drawn anti-aliased*).
  - Colours are the game's: rock and metal `0xe7e7e7`, ice and signals `0x00ffff`, giants `0xffe600`, water worlds `0x1604ff`, asteroid clusters white, Earth-like `0x00ff00`, ammonia `0x849e9e`.
  - A signal source is three bars, since a cyan disc means ice.
  - An atmospheric mark draws its halo in `FSS_ICON_ATMOSPHERE` (`0x3c78ff`) instead of the disc's colour; the game has no atmosphere glyph.
    That blue is darker and bluer than the ice cyan `0x00ffff` (luminance 0.22 against 0.79), so an icy body with an atmosphere still reads as two colours, and it keeps a contrast of about 5:1 against the panel's near-black.
  - Marks never carry the game's ring slash, as the spectrum does not show rings.
  - Marks on one slot are drawn side by side.
- An unknown slot is a warning triangle `FSS_WARN_SIDE` (0.018 L) tall with a `!`.
- Every tip the reading found is a dot of radius `FSS_TIP_R` (0.0015 L), `FSS_TIP_INSET` (0.0025 L) above the window's bottom, just clear of the waves: white for upward tips, orange for downward ones.

## The system line

What the system the ship is in holds, in the tables' font: under the system's name at the top of the route (see *Next jump*), or centred on the carrier line before the ship's system is known.

- It is icons and numbers (`jump::here_line`, drawn by `Overlay::here_info`), each icon `HERE_ICON_PCT` (95%) of the row's height and followed by its number after `HERE_ICON_GAP_PCT` (30%) of its width:
  - **Bodies**: the game's star-system icon from the galaxy map's tab column, a star inside two orbits with two planets on each (`system_icon()`), in the line's text colour, then the body count.
    After a honk the count is the honk's (`FSSDiscoveryScan` `BodyCount`), before it Spansh's; with neither it is left out.
  - **Biology**: the game's exobiology icon, a diagonal double helix whose strands cross twice, a half loop at each end and a full loop between, with five rungs, thinner than the strands, so it reads as DNA even at 19 px (`vector::dna()`), in its colour `EXO_DNA` (`#9cffff`), then the bodies with a biological signal: the larger of Spansh's count and those the journal's `FSSBodySignals` and `SAASignalsFound` have shown (`exobio::Here::signals`).
    While neither has shown one, it is the FSS prediction's count, `~N`, `~` marking it probable (`bands::bio_candidates`).
    The prediction counts the marks of rocky, high metal content, icy and rocky ice bodies with an atmosphere; slot 83, shared by high metal content with an atmosphere and airless rocky, counts as one.
    It shrinks as the FSS resolves bodies: a mark whose class already has a scanned body with an atmosphere is settled, since that scan's signals (or their absence) are the answer (`Here::scanned_with_atmosphere()`), and once the FSS has found every body (`FSSAllBodiesFound`) no estimate is left, so a system whose atmospheres all turned out thick shows no biology at all.
    It is a count of candidates, not of finds: the spectrum does not tell a thin atmosphere from a thick one, and in the commander's journals biology is on 79% of landable rocky bodies with an atmosphere, 58% of icy, 41% of high metal content, and on no body with a thick atmosphere; a mark can also hold more than one body.
  - **Geology**: a small volcano, a grey-brown cone (`GEO_CONE`, `#8a7866`) with a notched crater and three fireballs rising from it in `GEO_VOLCANO` (`#ff7a33`) (`vector::volcano()`), then the geological signals: the larger of Spansh's and the journal's.
    The count is green when any body in the system has geology probably missing from the commander's codex for this region (`HereLine::geo_new`, by the system pane's rule in *The system map pane*), and white otherwise.
  - **Worlds**: Earth-like, water world and ammonia world, in that order, each drawn like the FSS bar's own icon (`vector::body()`) and followed by its count (`jump::worlds`).
    - Before the FSS has found every body, the count is the larger of Spansh's (`subType`) and the journal's `Scan`s (`exobio::Here::worlds`).
    - After `FSSAllBodiesFound` it is the journal's alone, which is then exact.
    - A kind the FSS prediction shows (`bands::notable()`) that neither has counted reads `>0`: the spectrum shows a class, not how many bodies of it (see `overlay/FSS_SPECTRUM.md`).
      The point is to honk, flick the FSS open for one reading, and decide from the flight HUD whether the system is worth scanning.
    - A kind with no count and no prediction is left out; once the FSS has found every body, so is a predicted kind it did not find.
  - **Signal sources**: when the prediction shows one, the signal icon, three cyan bars inside the ring like the game's transient-signal icon (a cyan disc is the icy bodies' icon), with no count.
  - **Stations** stay text, `Stations: N`, left out at none.
  - **Carriers**: the fleet-carrier icon of the carrier line (`carrier_icon()`) in `JUMP_CARRIER` (`#ffb347`), then Spansh's count of carriers in the system, left out at none.
- Its text, beside every icon, is the clock's near-white with a dark edge (`CLOCK_TEXT`, `CLOCK_EDGE`), on the route as on the carrier line, so it reads over any background.

## The carrier line

The top pane's last line, always present, in the tables' font: the carrier icon and the carrier's state at the left, the clock at the right (see *Width and the clock*).
Where the carrier is and where it is going are on the plan pane and the Carrier tab.

- The state is `journal::carrier_state`, the Carrier tab's, counting down every second: `Ready`, `Jumping in m:ss`, `Jumping now` or `Cooling down m:ss`.
- Icon and state share one colour: green when ready (`CARRIER_READY`, `journal::carrier_ready`), red while a jump is scheduled (`CARRIER_JUMPING`), blue while it cools down (`CARRIER_COOLING`).
  With no `CarrierLocation` in the journals neither is drawn.
- The icon is Elite's own, from the carrier management tile: an upward arrowhead with a flat top and two feet, holding a ring with a bar across it, drawn in outline as tall as a text line (`carrier_icon()`, its outline `theme::CARRIER_ICON_HULL`).

## Unfound catalogue stars

Up to three rows under the predictions from `system_unfound`: real catalogued stars (HIP, GJ, HR) positioned in this sector that no game system matches by name or through the alias bridge.
235 galaxy-wide across 45 sectors, so the rows are blank almost everywhere.

- They ask whether a system is there at all, not what is in it, so they are their own row kind in their own colour (rose) and never ranked with predictions.
- The answer is a visit, and is one of: the game has it under an invented name (~15,800 systems carry names Frontier invented); nobody has visited it, so no dump carries it (the interesting case); Frontier did not ship it.
- They carry no probabilities.
  The prediction area holds the band, the spectral type and the nearest hand-named system with the length of that last hop, because the galaxy map takes a name, not a coordinate.
- The sector is assigned by nearest centroid, since these stars have no procedural name.
  A `NEAR` row's position is good to a few light years; a `MID` row's only to 100–333 ly, so its distance gets the `~` and its sector is a hint.
- Paste the name itself first: if the galaxy map resolves it, the row was stale.
  If it does not, `SHIFT+BACKSPACE`.

## Nearest

Places that are not a gamble, in one table at the left of the top pane: the nearest confirmed find of each kind (see *Confirmed*), then one carrier, one neutron, one point of interest and the live route chains.
Material traders and technology brokers are on the app window's Trade tab.

`theme::nearest_columns()` = `NEAREST 8 | SYSTEM 26 | LY 6`; the first column is headed with the table's name:

| column | |
| --- | --- |
| `NEAREST` | The row's type: a confirmed kind (`BLK HOLE`, `WOLF-RAY`, …), `NEUTRON`, `CARRIER`, `POI` or a route's far end (`COLONIA`, `FOUNDER`). |
| `SYSTEM` | The system to jump to next, and the cell the cursor copies. |
| `LY` | Light years from the ship to where the row leads: the find, the neutron, the carrier or the route's far end, which for a chained row is further than its `SYSTEM`. |

- **A row copies the next jump, not the far end.** A confirmed find or the carrier farther than one boosted jump gets a solved neutron chain (see *Route chains*), and its `SYSTEM` is that chain's next hop (`App::dress_nearest()`).
- Rows take their kind's colour: finds the find green, the rest as below.
- It is the only table the cursor reaches in flight.

### Nearest on the galaxy map

The plan pane's first table is the top pane's Nearest cut down to what a destination is chosen for on the galaxy map.

- It holds the confirmed finds, the carrier and the nearest neutron, from the same rows as the top pane's Nearest; the `POI` row and the route chains are left out, the POI table under it and the route rows being for flight.
- Each row names the find itself, not a chain's next hop: on the galaxy map the find is what gets plotted.
- Supergiants get one row per spectral letter (`~SUPERGNT B`, `~SUPERGNT F`, …), the nearest of each, where the top pane keeps only the nearest supergiant.
  `sql/confirmed_targets.sql` ranks a kind with `by_mass` pairs per letter (`{{BY_LETTER}}`), and `App::nearest_per_kind()` keeps the first row of each kind for the top pane.
- The `~` marks a supergiant read from its letter and mass code, which is probable, not reported (`kinds::letter_label()`); a scanned spelling shows without it.

### Carriers

- One carrier row, galaxy-wide: the nearest Drake-class carrier that lets everyone dock (`carrier_docking_access` `All`) and that Spansh has a report of from the last 7 days (`carriers::FRESH_DAYS`).
  A carrier restricted to friends or a squadron is never offered: it cannot be landed on.
- It is a live Spansh station search (`src/carriers.rs`), on its own thread like the Tritium search, asked once at start and again each time the ship moves; a burst of jumps collapses to one request for the latest position.
  The model's `carrier` table is not used, because it records no docking access.
- A failed search keeps the last answer and says so in the log; with no answer yet there is no carrier row.
- A recent report is not a promise: Spansh says when a carrier was last seen, not when it last jumped, so a carrier reported yesterday may have moved since.
- Once you are in the carrier's system, `SYSTEM` shows the carrier's callsign, the thing you need there; Spansh's search does not return the carrier's own name.
  `+UC` leads it when the carrier buys exploration data, the reason to choose one carrier over another, placed first so truncation cannot remove it.

### Neutron stars

- The nearest system whose primary star is a neutron, since primary is arrival.
- Not filtered against `system_visited` or `is_known`: a neutron is for getting somewhere, and the boost works as well the second time.
- Reads the mirror's `system_neutron` (3.5M rows, derived by `etl/refresh_current.py` from `system_known` and `body`) instead of scanning 200.8M.
- Ranked on coordinates alone and named afterwards: joining all 3.5M rows to `sector` for the name before the `ORDER BY` builds 3.5M names to keep three.
  The scan is 30 ms and the join was the other 250; the read is 32 ms.
- A plotted `SHIFT+N` route replaces this row (see *Neutron jump mode*); the carrier row is unaffected, and each is cached separately so plotting costs neither query.

### Points of interest

- The nearest system holding any POI in the mirror's `system_poi` (`sql/poi_nearest.sql`): notable stellar phenomena, anomalies, Galactic Exploration Catalog entries, Guardian and Thargoid sites, generation ships.
- Systems already visited, or whose POI is in `poi_visited`, are left out, unlike the neutron: a POI is somewhere to see, once.
- Typed `POI` and drawn in the POI colour (`Role::Poi`), as POI rows are in the sector table; the plan pane's `POI` table names what is there.
- Asked at start and on every move, like the neutron row, and cached between.

### Route chains

Chains are solved live, from where the ship is, at the range it flies.

- `Corridor::solve()` in `src/neutron_route.rs` (the same solver as `common/neutron_route.py`) plots one in a second or two over half a million neutron stars, on the worker as `Ask::SolveRoute`.
  A chain solved from Colonia is worthless 3,000 ly along it, and one solved for a 500 ly boost is unflyable in a ship that makes 472.
- The app-state `route` table supplies only the endpoints, a name and position for each end (`Ask::RouteHops`, read at startup); storing a route is how a destination is registered.
- The nearest carrier and every confirmed find beyond one boosted jump get a solved chain too (`App::chain_targets()`), labelled with the row's type: their `SYSTEM` is the next hop of the chain, following whichever system is currently the nearest of its kind.
  A find within one boosted jump needs no chain, so none is solved for it.
- Route rows are `keycap` grey, the colour for something you press rather than read.

**Re-solving.** There is no timer; a chain is re-solved only when:

- there is no chain;
- its range is more than 1 ly off the ship's boosted range, since hops spaced for more range than the ship has fail one paste at a time in the galaxy map;
- the ship has left it, meaning no hop is within one boosted jump.

Flying the chain never triggers a re-solve, because the next hop is in range by construction, which keeps a 1.5–4 s solve off the worker on every jump.
An empty solve is remembered and not retried until the destination or the ship changes, because each widening step searches a larger corridor and an unreachable place would cost ten seconds of worker time per jump.
A solve that finds nothing says so in the footer.

**The hop shown** is the nearest one that is both:

- **Progressing:** strictly closer to this row's destination than the ship is.
  This makes the two directions differ on the chain (from hop 20 the Founders row offers 21, the Colonia row 19) and makes standing on a hop offer the next one rather than the one underfoot.
- **In reach:** inside the ship's boosted range (`App::boosted_range()`); an unreachable hop is a paste that will not plot.

Nearest among those is the next link; reaching past it would skip a supercharge the chain assumes.
Nothing is pinned, so the row is right after a deviation, a restart or a jump somebody else plotted.
With nothing in reach (off the route), the nearest progressing hop is offered anyway as the place to rejoin.
At either end of the chain the spent direction's row is absent.

**Following.** Landing the cursor on a chained row starts following it, because landing on a row copies it and the clipboard is the statement of intent; copying any other row stops it, and the footer says which.

- Arriving anywhere on that chain copies the next hop, matched against any hop so a skipped jump still advances; an arrival off the route leaves the clipboard alone.
- Arriving at the last hop ends following.

## Confirmed

### Confirming from the galaxy map

**This is the tool's edge.** A route plot rewrites `NavRoute.json` with the arrival `StarClass` and exact `StarPos` of every hop, so one plot confirms dozens of systems thousands of ly before anyone flies there.

- `FSDTarget`/`StartJump` add the same fact one system at a time.
- Everything lands in `system_seen`, and Nearest's find rows are built from it.
- The whole route is harvested; the file is mtime-gated, so it is re-parsed only when a plot happens.

`KINDS` in `src/kinds.rs` maps classes to kinds; `key` is stored in `system_confirmed.kind`, `abbr` is the column heading:

| stored `kind` | shown | classes matched |
| --- | --- | --- |
| `BH` | `BLK HOLE` | `H`, `SupermassiveBlackHole`, `SuperMassiveBlackHole` |
| `WR` | `WOLF-RAY` | `W` `WN` `WNC` `WC` `WO` |
| `HERBIG` | `HERBIG` | `AeBe` |
| `O-TYPE` | `O-TYPE` | `O` |
| `SUPERGNT` | `SUPERGNT` | the five `*SuperGiant` spellings, and a bare letter in its `by_mass` codes (see the supergiant section) |
| `NEUTRON` | `NEUTRON` | `N` |
| `WHT DWRF` | `WHT DWRF` | the fifteen `D*` codes |

Both supermassive spellings are matched: the journal writes `SupermassiveBlackHole`, the model's `body` table `SuperMassiveBlackHole`, and matching one would drop Sagittarius A*.

### A system somebody has reported is not a find

**Confirmed excludes any system somebody has already scanned**: one with body data in the model's `system_body`, whose rare arrival star is therefore already discovered.
Being in `system_known` is not enough: a route plot alone puts a system there with its arrival-star class and no bodies (`SOURCES.md`), and its rare star is still undiscovered.

- A `BLK HOLE` row here is a black hole nobody has scanned, often one a route plot already put into the dumps.
- **The filter is `known`, never `not predicted`.** Most survivors are in no dump and no prediction, and they are the best rows; they are missing from `system_predicted` only because the boxel-gap enumeration is a core-biased lower bound.
- Stored, not computed: `system_seen.is_known` and `system_confirmed.is_known` are resolved by `sql/record_seen.sql`, FALSE where `system_predicted` holds the system (it holds only systems with no body data), then TRUE where `model.system_known_probe` does: the scanned systems that could hold a rare arrival star, built by `etl/refresh_current.py`.
  `etl/refresh_current.py` re-derives every stored value from the rebuilt mirror, so a value reflects the last refresh rather than the rules it was first written under.
  Probing the full 200.8M-row name bridge costs 1.8 s per call; the probe costs ~300 ms cold and 3 ms warm and needs no model database.
- **The probe is one-sided: a hit is proof, a miss is not.** It drops systems the dumps rule out and systems below mass code `e`, so it writes `TRUE` on a hit and leaves `NULL` on a miss, never `FALSE`.
  Of 1,655 confirmed systems that are in the dumps it finds 1,250; all 405 misses are neutrons or white dwarfs, which the Forge builds one mass code below the floor, so the other kinds are exact.
- `NULL` (not yet checked) is shown, because hiding a genuine find is the expensive direction to be wrong in.

### One line per kind, galaxy-wide

The finds are the first rows of the Nearest table (`sql/confirmed_targets.sql`), each typed with its kind in the same eight characters as the prediction headings.

- Galaxy-wide, unlike everything else: finds are few certainties worth diverting for, while predictions are plentiful and only nearby ones matter.
- One row per kind, the nearest confirmed find of that kind, so the numerous kinds cannot push the rare ones off.
  Of 1,363 finds, 816 are neutrons and 398 O-types against 8 black holes; ranked by distance the rows would be neutrons.
- Rows sit in rarity order (the order of `KINDS`), so the black hole is always the top line, and a kind with nothing confirmed has none.
  The footer's *nearest confirmed* takes the minimum across rows and names the kind.
- Systems without coordinates sort last within their kind: `system_seen` holds `x/y/z` only from a route plot (`FSDTarget` gives the class alone), and unlocated is not near.
- The HUD shows no count per kind; the Stats tab has the counts, and `--dump` prints the query's `kind_count` through `theme::confirmed_columns()`.

## Flashes and sounds

### Flashes

One animation, three highlights; none is a row-kind or gradient colour, so a flash cannot be misread as a value.

| highlight | says |
|---|---|
| white (`FLASH_CONFIRM`) | the game has just revealed a rare here |
| pale blue (`FLASH_APPEAR`) | this row was not in the table a moment ago |
| amber (`FLASH_COPIED`) | this row is what is on the clipboard |

- The fade is 12 steps at 60 ms (0.72 s), on its own `FLASH_TIMER` (`theme::FLASH_STEP_MS`), started by `App::redraw()` while any table has a flash and killed when none has; the 120 ms tick would make it a stutter.
- It fades rather than blinks: a fade says "this just happened" and gets out of the way.
- It ends on the colour the cell would have had anyway: `table::cell_colour()` decides the endpoint and `theme::blend()` mixes the highlight in.
- Only the `SYSTEM` cell flashes; tinting the row would wash out the probabilities when they are worth reading.
- Flash state lives on the `TargetTable`, so it survives the repaint the event itself triggers.

**Confirm** fires for every rare class a find row can show, `kinds::is_rare_class()`, so adding a class to `KINDS` adds it here.
White is the only colour on the HUD that means nothing else.

**Appear** is for find rows only (`flash_new` on `TargetTable::new()`, keyed in `TargetTable::note_arrivals()`).

- Finds are galaxy-wide and one per kind, so a name changes only for a nearer find or a new kind, which is rare enough to flash.
- A chained find is left out, since its `SYSTEM` is a hop that changes with every jump, and so is every other row: they turn over whenever the ship moves, and flashing that flashes the fact that you are flying.
- Membership decides it, never values: every distance changes on every jump.
- The first fill flashes nothing.

**Copied** is for handovers you did not press a key for, typically alt-tabbed in the galaxy map when a plot answers a row and its successor is copied.

- `copy_selected`, `advance_clipboard`, `copy_next_hop` and `advance_follow` all go through `App::took_clipboard()`, the one place `copied` is set.
- It is queued, not painted at the request: `advance_clipboard()` runs before the repaint, so flashing there would light the row's old position.
  `took_clipboard()` records the name and `place_cursor()` fires `flash_copied()` as its last step, the one point where clipboard and screen are both settled.
- The name is offered to every table and only the row holding it flashes, matched on the displayed system or on `copy_text` (a sector row copies a name its `SYSTEM` cell does not show).
  A name no table holds flashes nothing.

### Sounds

Both are synthesised in memory by `src/win/notify.rs` on first use and played with `PlaySoundW` and `SND_MEMORY | SND_ASYNC | SND_NODEFAULT`.

- Synthesised, not a shipped `.wav`: a few lines of arithmetic are diffable, and no file can go on playing an old tone.
- Asynchronous, because a synchronous tone would freeze the thread drawing the thing it announces.
- Any failure degrades to silence; `SND_NODEFAULT` stops Windows substituting its beep.
- The Settings tab's "Play sounds" silences both and keeps the flashes.

| sound | notes | length | level |
| --- | --- | ---: | ---: |
| chime (a find) | perfect fifth, A5 over E6, soft attack, exponential decay | 0.26 s | 22% |
| tick (a copy) | the chime's root note alone | 0.09 s | 10% |

- The chime plays over the game, and an alert that talks over the ship gets turned off.
- The tick is the most frequent sound (every cursor move copies), so it is the same voice at a third the length and about half the amplitude, and cannot be mistaken for a find.
- The tick plays from `took_clipboard()` immediately, not queued like the flash: it only says the clipboard changed, and waiting would put it ~2 s of SQL after the key.

**The chime is narrower than the flash**, because a sound interrupts and has to earn it; all three tiers meet in `App::chime_worthy()`.

- **Kinds:** only kinds with the `chime` flag, `BH, WR, HERBIG, O-TYPE, SUPERGNT` (`kinds::is_chime_class()`).
  NEUTRON and WHT DWRF are 1,229 of 1,778 chime-triggering classes on record, neutrons alone 66%, and a neutron is a routing choice.
- **Reveals only:** `Database::record_seen()` returns the names of systems it had never seen, and only those count; re-plotting a route past a known black hole is not news.
- **Neutrons we predicted:** `chime_predicted` (`kinds::is_chime_if_predicted()`) sounds for a neutron only in a boxel prediction of ours (`system_predicted.is_catalog = FALSE`, "in NO dump"): the model being right about a place nobody had looked.
  No `is_known` probe is needed, since the plot-only half is by construction the half in `system_known`; the flag costs 3 ms.
  The lookup is an `Ask::PredictedBoxel` riding the reveal request, added only when a find's class is a `chime_predicted` one.

## Where colour is used

Two things carry colour and nothing else does, so neither tint loses its meaning by being everywhere:

| | means |
| --- | --- |
| `SYSTEM` | the row kind: a confirmed row in its star colour (and its TYPE with it), violet = POI, blue-grey = plot-only backfill, rose = unfound catalogue star, dimmed = class already revealed, green = the ship's own sector |
| the numbers | the probability ramp, or the count ramp on sums |

Nearest's `SYSTEM` colour follows the same row-kind language (carrier amber, neutron blue, route keycap grey).

A star is the colour of its class in the galaxy map's star-class view, sampled from the in-game legend, so a confirmed find or a jump destination reads the same on the HUD as on the map (`theme::star_colour`); a giant or supergiant takes its spectral letter's colour.
The sector table's probability headings take the same colours (`theme::heading_colour`), except `SUPERGNT`, which spans five letters and keeps the header colour:

| kind | colour | legend entry |
| --- | --- | --- |
| black hole | `#c7c7c8` grey | Non sequence stars |
| Wolf-Rayet | `#ffffff` white | Wolf-Rayet stars |
| Herbig Ae/Be | `#f50100` red | Proto stars |
| O-type | `#8c84ff` | O-type stars, `#1700ff`, lifted because that blue is unreadable on the HUD |
| neutron | `#2f9bff` blue | Non sequence stars share the black hole's grey, so neutrons take a blue of their own |
| white dwarf | `#b9ceff` pale blue | White dwarf stars |
| B | `#a091ff` | B-type stars, `#4022ff`, lifted like O |
| A | `#c4a4ff` | A-type stars, `#8848ff`, lifted like O |
| F | `#c8c8ff` | F-type stars |
| G | `#ffff92` | G-type stars |
| K | `#ff7c44` | K-type stars |
| M | `#f43715` | M-type stars |
| L | `#f32d00` | L-type stars |
| T | `#c41e1e` | T-type stars, `#870000`, lifted because it vanishes on the HUD |
| Y | `#f50100` | Y-type stars |
| T Tauri | `#f50100` | Proto stars, with Herbig |
| carbon, S, MS | `#ffff92` | Carbon stars |
| exotic | `#c7c7c8` | Non sequence stars |

### Headers take Elite's own palette

Table titles and column headings use the colours of Elite's panel tab bar, sampled from the game at full resolution, in both the HUD and the app window:

| | sampled from | value (`theme.rs`) |
| --- | --- | --- |
| heading text | the body of the tab letters, below the bloom | `HEADER_TEXT` `#ff8707` |
| heading band | median inside three tab cells | `HEADER_BG` `#612f18` |
| rule under the band | the line beneath the tabs | `HEADER_LINE` `#dc6707` |
| app table rows | the panel body | `TABLE_ROW` `#0e0000` |

- In the HUD the band is semi-transparent: `HEADER_ALPHA` (0.55) of the HUD opacity, while text stays at the HUD opacity.
- That takes per-pixel alpha, so the HUD draws into a 32-bit DIB and presents it with `UpdateLayeredWindow`.
  After drawing, one pass sets each pixel's alpha: the `KEY` background 0, the exact `HEADER_BG` colour the band alpha, everything else the HUD opacity.
  Alpha-0 pixels stay click-through, as the colour key made them.
- The app window's header is drawn whole in custom draw, because the dark theme paints its own header background under any text colour.

## Data access

### The overlay never opens the model

It reads a mirror in the `model` schema of its own app-state file, so `etl/` can re-merge the model while the HUD is flying; DuckDB allows one writer per file and read-only readers still block writes.

- `etl/refresh_current.py` copies the needed model tables into the `model` schema of `elite_mapping_current.duckdb`.
- `etl/build_seed.py` derives the same mirror from the model into `seed/elite_mapping_seed.duckdb`, beside empty app-state tables and a `model.seed_info` row naming the build; a player's state file starts as a copy of it (see *Storage*).
- The overlay touches `system_known` (200.8M rows) and `system_body` (577.6M) nowhere in `sql/`, so the mirror is 16.8M rows against the model's 570M, a 1.2 GB seed against 91 GiB.

| in the mirror | rows |
|---|---:|
| `system_neutron` | 3,484,617 |
| `system_exobio` | 3,288,906 |
| `system_predicted` | 2,607,665 |
| `system_known_probe` | 7,004,030 |
| `carrier` / `carrier_position` | 90,364 / 90,297 |
| `system_poi` / `poi` | 67,544 / 260 |
| `station_service` | 4,279 |
| `sector` / `region` | 12,110 / 42 |
| `system_unfound` | 236 |

- **The `model` schema is a cache; `main` is not.** Each mirrored table is dropped and rebuilt on every refresh, so anything written there vanishes; a new app-state table belongs in `main`.
  The mirrored list is `MODEL_TABLES`, `DERIVED_TABLES` and `PROBE_TABLE` in `common/current.py`.
- **It goes stale silently.** After any `etl/` load touching a mirrored table, re-run `python etl/refresh_current.py` with the overlay closed, and `python etl/build_seed.py` for a release.

### Three model tables exist for the overlay

Each resolves a tiny row set (88,175 carrier positions, 260 POIs, 3 neutron rows) that would otherwise be found by scanning a table of hundreds of millions with nothing to probe on:

| read | through the big table, warm | cold | materialised |
|---|---:|---:|---:|
| `top_targets` | 272 ms | 2,141 ms | 12 ms |
| `neutron_targets` | 343 ms | 376 ms | 32 ms |
| jump repaint | 2,695 ms | 8,289 ms | 143 ms |

- `carrier_position` (88,175 rows) replaces resolving `carrier.system_id` through `system_known`'s 200,816,169.
- `system_poi` (66,544 rows) replaces a POI union whose body half scanned `system_body`'s 577,639,044 rows to reach 10,023.
- `system_neutron` needs only ranking before naming (see *Neutron stars*).
- All three add no facts and are snapshots, stale until their builder runs; `ETL.md` carries that warning.
- `Database::poi_in_system()` reads `system_poi` keyed on the pasteable name: 2.2 ms per arrival.
- The overlay reads no staging table, which is what lets it run on a mirror.

### Storage

- Writes go only to the app-state file: `%LOCALAPPDATA%\explorers-companion\state.duckdb`, or the file `--state` names (`explorers-companion.cmd` passes `elite_mapping_current.duckdb`).
- All state lives in that file, settings included (`setting`); only the run log (`%LOCALAPPDATA%\explorers-companion\log`) and, in a `calibrate` build, the FSS screenshots beside the exe are files.
- Without `--state`, each start installs the seed beside the exe (`database::install()`):
  - no state file: the seed is copied in;
  - the same `model.seed_info.id`: nothing changes;
  - a different seed: the state file is renamed `state-<UTC stamp>.duckdb` and kept, the seed copied in, and every `main` table migrated by column name in one transaction, `id64` mapping to `system_id`; a table the seed lacks is copied whole, a column with no place is logged, and `is_known` is re-derived (`sql/rederive_known.sql`).
    Any failure deletes the new file and renames the old one back.
- A file named with `--state` is never replaced: the commander's own `elite_mapping_current.duckdb` is refreshed by `etl/refresh_current.py` alone.
- On arrival the app writes `system_visited`, and `poi_visited` if the system holds a POI; both are idempotent, so a replayed journal event cannot double-count.
- The app never resolves `system_id` by name: `system_visited`, `poi_visited` and `system_wrong` get `NULL`, and `system_seen` keeps only the `SystemAddress` a hop or `FSDTarget` gives.
  Probing the name bridge takes seconds; the app-state loaders backfill through `common.current.resolve_id64()`.

### One connection, released when idle

- `Database::connection()` builds one in-memory DuckDB connection with the app-state file attached read-write as `cur`; the model mirror is its `cur.model` schema.
- DuckDB lets one process hold a file, so an overlay holding the app-state file forever would lock out every loader and every read of your own flight log.
- `Database::release_if_idle()` closes the connection after `--model-idle` seconds without a query and it is rebuilt in ~17 ms on the next request; the worker checks once a second while its queue is empty.
  The flag governs the app-state file, not the model; the name is stale, the behaviour is not.
- A read-write connection cannot make a read raise on write, so `database::WRITES` names the writing methods and `DbWorker` refuses one in a request not declared a write, naming the method.

### All selection is SQL

- Which rows exist, their order and every word on them (`Mass H`, a POI's class, a sector's mass-code counts and best system) come from the query.
- `Database::top_targets()` returns typed `Row`s; `table::cell_text()` formats (two decimals, `-` below the floor, thousands separators, the `~`) and `table::cell_colour()` colours from raw columns carried alongside (`mass_code`, `star_class`, `row_grp`).
- The app displays and tracks; it does not rank, filter or sum.
- Every distance in light years, on the HUD, in the app window and in log lines, goes through `table::light_years()`: no decimals, digits grouped by the Windows user locale (`LOCALE_STHOUSAND` and `LOCALE_SGROUPING`, read once at startup by `win/locale.rs`).
  Other counts keep `table::thousands()` and its comma, because a locale that groups with `.` would make `0.38` and `1.234` read alike.
- Route rows are the one exception (`App::route_row()`): they come from a computation, and sending the solved path back through SQL would be a round trip to dress up data already in hand.

## Threads and the tick

### One bad tick costs one frame

- The tick is a Windows timer (`TICK_TIMER`, every `KEY_POLL_MS` = 120 ms) set once in `main()`; `SetTimer` keeps firing, so a failing tick cannot cancel the next.
- `wndproc` runs `App::tick()` inside `catch_unwind`; a panic goes to `App::note()` as `tick error: …`, and the panic hook writes the full message to the log.
- The failure guarded against is a permanently frozen HUD that looks like a hang: window up, message loop answering, table stuck on the old sector, and 0.0 s CPU, which is the tell.
- A failure must cost one frame and be said; `src/dbworker.rs` holds the same rule.

### The database runs on its own thread

The message loop runs the tick, the flash timer, the keys and every repaint on one thread, so a query there means no key read and no redraw for its duration (~100–145 ms of SQL against ~10 ms of drawing).
`src/dbworker.rs` moves SQL to a thread named `db`; the UI thread only submits requests and drains answers, both non-blocking.

- `DbWorker` is a transport: one `Ask` variant per public `Database` method, named after it (`Ask::TopTargets { sector, limit: 10, pos }`).
- Which datasets a view needs is a UI decision in `App::read_asks()`; neutrons are re-read only when the ship has moved or nothing is cached.
- `--dump` (`src/dump.rs`) drives `Database` with no window; if that stops working, the boundary has leaked.

Rules, each because the alternative fails:

- **One worker, one FIFO**, so `record_seen` lands before the reads that observe it.
- **Last wins, for unstarted requests under a `key` only.** `DbWorker::submit()` records the newest id per key, the worker skips superseded requests and `App::ask()` drops their continuations, so a quick double jump does not paint the sector you left.
  Writes never carry a key, because a dropped write is a lost find.
- **`Only::FromRecordSeen`** hands an earlier ask's answer to a later one in the same request, so `record_seen` and the `promote_confirmed` depending on it share one request.
- **One thread owns the connection.** `Database` is built on the worker and its `Rc`-based `Phases` makes it unsendable.
  DuckDB accepts a `DETACH` of a database another cursor is reading without complaint (verified), so the guard must be the type system.
  Startup work is asks too: `App::run_startup()` queues the journal catch-up as one write request.
- **Failures travel as values.** `serve()` returns a `Result`, a panic in a request returns as its text, and `App::drain_db()` puts it on the footer.
- **A `Phases` per thread**, or a worker phase lands inside the UI's open span; worker lines are tagged `[db]`.

`route::plan()` runs on the UI thread in `App::routed()` because it is CPU, not SQL; its corridor fetch is an ask (`Ask::NeutronCorridor`), and the widening retry is a second request so the common case fetches once.

### The paint does no IO

- `App::paint()` (phases `p_confirmed`, `p_sector`, `p_nearest`, `p_cursor`) only hands rows to each `TargetTable`.
- `Overlay::refresh()` lays out, resizes if the layout changed and invalidates; drawing happens on `WM_PAINT` into an off-screen bitmap blitted in one go, so a refill does not flicker and there are no per-cell objects.
- Queries and `db_connect` are the worker's; the journal and `NavRoute.json` are read in the tick (`journal`, `navroute`).
- The only phase leaving the process is `p_clipboard` inside `p_cursor`: `OpenClipboard` can block on another process, so `clipboard::copy()` retries five times 10 ms apart, then says so on the footer.

## The main window

A standard application window beside the HUD, for what does not belong over the game.

- It is an ordinary top-level window, so it has a taskbar button and takes part in Alt+Tab; the HUD stays a topmost tool window that never takes focus.
- It opens without activating, so starting the overlay does not pull Elite out of the foreground.
- It opens against the right edge of its monitor's work area, top-aligned, leaving the left of the screen to the HUD.
- Closing it quits the app, HUD included; minimising it leaves the HUD running.
- Both windows run on the UI thread and share one message loop.
- The tabs are a Win32 tab control; `build.rs` embeds the manifest that selects common controls 6, without which they draw in the Windows 95 style.
- The tabs run Map, Codex, Trade, Engineers, Guardian, Thargoid, Carrier, Stats, Settings, Log, and the window opens on Map, the first.
  Each `*_TAB` constant in `win/main_window.rs` is both the tab's position and the index of its page in `pages`, which is filled by those constants, so reordering the tabs is a change to the constants and `TAB_NAMES` alone.
- The icon is resource 1 in the executable, so Explorer shows it for the file and the window class loads it for the title bar, taskbar and Alt+Tab.
  It is drawn per size by `assets/icon.py`, simplified below 32 px, because a downscaled 256 px drawing turns to mush at 16.
- No image is fetched from EDSM: its pages and `/img/` assets are behind a Cloudflare browser challenge, and its API returns no image fields.

### The Log tab

- Streams the run log (`--log`) into a read-only edit control, polling the file every 250 ms.
- It opens on the last 512 KB, starting at a line boundary, and appends only complete lines, so a line being written is never shown half-way.
- A shorter file than last read means it was rotated, and the tab follows it from the start.
- It follows the end while the view is scrolled to the bottom; scrolled up, the view and any selection stay put while lines arrive.
- Past 2 M characters it drops the oldest lines down to 1 M, so a long session cannot grow the control without bound.

### The Map tab

The galaxy's regions drawn as a map, each shaded by how many of one kind of object it is still expected to hold; double-clicking a region opens it as the grid of its sectors, double-clicking a square of that grid opens the 3×3 squares around it with every sector named, and clicking a name lists that sector's likeliest systems.

- The map has three levels:
  - **Galaxy**: every region, shaded by its expected count of the chosen kind, with the selected region's best sectors in the panel at the right.
  - **Region**: one region, zoomed so its sector grid fills the map, each sector column a single colour by its own expected count, with no names.
  - **Sectors**: the 3×3 columns around one column, the HUD mini map's block, large enough to name every sector in them; clicking a name lists that sector's systems in the panel at the right.
    The block is zoomed with one column of margin all round, and only its nine cells are coloured, so the squares around it show the galaxy.
- Double-clicking a region at the galaxy level opens it; at the region level, double-clicking a square opens the sectors level around it, and double-clicking another region outside the open region's grid opens that one.
- At the sectors level, double-clicking a square other than the centre moves the 3×3 block onto it.
- Double-clicking a sector in the galaxy level's list opens its region at the sectors level with the sector picked, as the search box does.
- **Zoom out**, in the map's top left corner, goes up one level: from the sectors to the region, and from the region to the galaxy, where the region stays selected; it is shown only below the galaxy level.
  A right-click anywhere on the map does the same.
  It is owner-drawn like **Carrier Route**.
- The map is a top-down projection on x and z, north (+z) up and east (+x) right; y places nothing.

#### Above the map

- The dropdown picks the kind; the map, its legend and both lists follow it.
- **Include plot only**, off at every start, adds the plot-only predictions to the map, its legend and both lists.
  Off, they count boxel predictions only, the pool the HUD's sector rows and `REGION` line count, so the two agree; the checkbox itself says which pool is shown, so the legend does not repeat it.
- The search box finds a sector by name, completing as it is typed: the sectors whose name starts with the text, then those that contain it, case-insensitive, at most 200.
  Picking one from the list, or pressing Enter on a typed name, opens the sector's region at the region level and picks the sector there; Enter on a partial name takes the first match.
  The region is the sector's `region_id`, or the `region_map` cell under the centre of its box where it has none.
- The 12,109 names (`sql/sector_names.sql`, every sector but the `crafted` sentinel) are read once, the first time the tab is opened, and matched in memory on the UI thread.
- Nothing is written for what the mouse is over below the galaxy level: a square under the mouse is only tinted, because clicking it lists its sectors in the table.
- **Carrier Route**, right-aligned under the list in the panel, makes the last system a sector click copied the fleet carrier's destination and fills the Carrier tab; pressed before any sector click, it says so in the log.
  It is owner-drawn in the header palette (`HEADER_BG` fill, `HEADER_TEXT` label, `HEADER_LINE` border) and flashes white text on bright orange (`FLASH_TEXT` on `TABLE_FLASH`) while pressed and for 350 ms after a click, on a one-shot timer, so a click can be seen.

#### The galaxy level

- Region shapes come from `region_map`, klightspeed's published region grid (MIT): 2,048 x 2,048 cells of about 49 ly over the galactic plane, the lookup EDDiscovery and EDMC use.
  Frontier publishes no region boundaries, and EDAstro's region maps are pictures without stated coordinates, so neither lines up with a click.
- The texture under the colour is `galaxy_density`: known systems per cell of the same grid at half resolution, log-scaled.
  It shows where commanders have reported systems, which is the galaxy's explored shape, not its real star density.
- A region's shade is the gradient at `sqrt(value / max)`: the core regions run to tens of thousands of expected black holes and the rim to single digits, and a linear scale would leave the rim one colour.
  The legend is marked at its left, middle and right in whole numbers of the kind: 0, a quarter of the maximum (the middle of a square-root scale) and the maximum.
  The gradient runs in ten steps from dark red (fewest) through orange, amber and yellow-green to green (most) (`MAP_GRADIENT` in `theme.rs`).
- A region expecting none of the kind (under `MAP_ZERO`, 0.5, which reads as 0) is left uncoloured, showing the galaxy beneath, and colour fades in over the bottom `MAP_FADE` (15%) of the scale, so the gradient starts from transparent; the legend fades the same way.
- The region totals are `sql/region_expected.sql`, one pass over `system_predicted` joined to its region through the sector name, read at startup and again each time the tab is opened, so they reflect every arrival since.
- Labels are placed highest-value first, and one that would overlap a placed label is skipped, so the crowded core keeps the names that matter.
- The grid is read once at startup; the per-pixel region, density, border and sector-column lookups are cached per window size and level, so hovering and changing the kind only re-shade.
- The map fills its whole area with the galaxy texture at the current zoom; what is zoomed to is fitted to the area below **Zoom out**, left-aligned at the galaxy level and centred below it.
  The list sits in a panel on its right, with no caption: the dropdown already names the kind and the summary row the region.
- Clicking a region asks `sql/sector_expected.sql` for its top sectors by expected count of the chosen kind.
- The list holds at most the top 20 sectors and ends in a summary row, as the HUD sector table ends in its `REGION` row: the region's bare name and its total for the kind.
  The list is exactly as tall as its rows, never scrolls, and is as wide as the panel; **Carrier Route** sits under it, and the colour legend at the panel's bottom, captioned `Expected <kind> per region` or `per square`, centred over its bar, in the dialog font.
- Both lists fill the panel's width: the first column takes the width the others leave, and the last runs to the border (`expected_table::stretch_first_column`).
  The region level's systems list is the same height, with the legend in the same place.
- The list shows the sector, its expected count of the chosen kind, to one decimal, and `Conf`, its confirmed finds of the kind not yet visited; both headings follow the dropdown (`win/expected_table.rs`).
  `Conf` counts `system_confirmed` rows by their `sector` (`CONF_COUNTS` in `database.rs`), the same not-yet-visited finds the map's dots show, so it replaces the dots' count line; the summary row's `Conf` is the region's, or the square's.
- The summary row's figure is the region's total for the kind, the same figure the map is shaded by, not the sum of the sectors shown.
- A sector whose value rounds to 0.0 is left out; if none remains the list is a single `<none>` row with no total.
- Clicking a sector in the list copies its most likely target to the clipboard: the unvisited, unrevealed, not-marked-wrong system with the highest probability of the chosen kind (`sql/sector_best.sql`), boxel-predicted only unless **Include plot only** is ticked.
  The log names the system and its chance; a sector with nothing left says so.
  The clicked row flashes white text on bright orange (`FLASH_TEXT` on `TABLE_FLASH`) for 350 ms on a one-shot timer, then settles into the selected colour; the total and `<none>` rows do nothing.

#### The region level

- The grid is the game's sector grid: procedural sectors are 1,280 ly cubes from the origin x = −49985, z = −24105 (`sql/minimap_density.sql` places the HUD's mini map on the same grid).
  It is drawn the way the HUD's sector mini map draws its 3×3 block, 1 px cell outlines in `MAP_SECTOR_GRID` (the mini map's `CUBE_LAYER`), but over every column the region touches.
- The columns are every 1,280 ly column holding at least one `region_map` cell of the region (`map::region_columns`), so a column on the boundary is drawn whole although part of it lies in a neighbour.
  The region's own outline is its `region_map` border, in `MAP_SELECTED`; the map is zoomed to the grid plus half a column on every side, and centred.
- `sql/region_sectors.sql` works out the same columns from `region_map` and returns every named procedural sector in them, whatever region the sector itself is filed under, with its predictions, its known systems from `sector_known` and its expected count of every kind, over the pool the galaxy level counts.
  On a copy of the app-state file region 29, the largest, has 648 such sectors in 224 columns.
- A column is a stack of sectors, one per 1,280 ly layer of y: of the 3,231 columns with a named sector, 1,041 hold 2, 1,626 hold 4 and 471 hold 6.
- The region level names nothing on the map.
  A single click on a square lists its sectors in the panel, each with its expected count of the kind, sorted as the galaxy level's list is, and a `Square total` row; the square is outlined in `MAP_SELECTED`.
  Clicking a sector there copies its best target and double-clicking it opens the sectors level on it, as in the galaxy level's list.
- At the sectors level a cell lists every sector in its column, one name per line, top layer first, as a mini map cell does.
  - All nine cells share one line height: the cell's height over the most sectors any of them holds, between three quarters of the small font and 160% of it.
  - A name too wide for the cell is cut with an ellipsis; where the lines still do not fit, the last line reads `+k more`, or the picked sector when it is one of them, and clicking it steps through the rest.
  - Only the nine cells are outlined, and drawing is clipped to the map, so the rest of the region's grid does not run under the panel.
- Names are drawn in `MAP_SECTOR_NAME` with a 1 px black edge on four sides (`MAP_SECTOR_EDGE`, the HUD's `CLOCK_EDGE`), so they read on every shade.
- Clicking a name picks that sector: its name turns `MAP_SELECTED`, with nothing behind it, and its column is outlined 2 px in `MAP_SELECTED`, which the region level shows too.
- A sector picked from the search box or the galaxy level's list opens the sectors level on its column once the region's sectors have loaded.
- The grid is shaded on the galaxy's scale, not the region's: `max` is the largest column total anywhere in the galaxy for the kind and pool (the second statement of `sql/region_sectors.sql`), so most columns are dark and the busiest columns of the core are green.
  - A column's value is the sum of its sectors' expected counts of the kind, coloured at `sqrt(value / max)` as at the galaxy level.
  - Each square is one colour at `MAP_SECTOR_ALPHA` (60%) over the galaxy texture, so the galaxy shows through it.
  - Colour starts at `MAP_SECTOR_ZERO` (0.05) rather than `MAP_ZERO`, because a column holds a small share of a region's total; the legend says `per square`.
- Clicking a sector copies its most likely target, as a click in the galaxy level's list does, and lists its systems at the right.
- The list is the sector's 20 likeliest predictions of the chosen kind, `sql/sector_systems.sql`, from the same pool and with the same exclusions as `sql/sector_best.sql`: unvisited, unrevealed and not marked wrong, boxel-predicted only unless **Include plot only** is ticked.
  - It shows the system, its mass code, parsed from the name (`PROCEDURAL`) and shown in capitals as everywhere else, and its chance of the kind.
  - Its last row is the sector's summary: its name with how many predictions it holds, and their summed chance, the sector's expected number of the kind.
  - A system with no chance of the kind is left out, so a sector with none reads `<none predicted>`.
  - Changing the kind or **Include plot only** lists the picked sector again.
- Clicking a system copies it to the clipboard, as on the Trade tab.
- A hand-authored sector has no grid cell; picked with the search box, its box is its centre plus and minus its recorded radius, which overstates most of them, outlined and named in `MAP_SELECTED` (`sql/sector_find.sql` turns both kinds of box into map cells).
  Systems named under a hand-authored sector are not in the columns they lie in, as in the HUD's sector table.

#### At both levels

- Every confirmed find of the chosen kind not yet visited is a 3 px light grey dot (`MAP_CONFIRMED`) with a 1 px `MAP_SPACE` rim, so it reads on every shade of the gradient; `sql/map_confirmed.sql` reads `system_confirmed`, leaves out a find whose row is `visited` or whose system is in `system_visited`, takes a position from `system_seen` where the find has none, and leaves out the finds with no position in either (about a tenth).
  A find somebody else has already scanned is still drawn: the map is the find rows' pool before their `is_known` filter.
  The finds are read at startup and again each time the tab is opened, so a find made in flight appears on the next visit.
  The dots sit under the region labels and the sector grid.
- Every page window sits above the tab control in z-order, and the controls above the map: a sibling below a `WS_CLIPSIBLINGS` window it overlaps is painted over, and the map was invisible until the tab control was moved to the bottom.

#### The lists

- Both lists are ListViews styled as Elite's HUD: orange text on near-black rows striped with dark amber, the header in Elite's tab-bar palette, and a total row brighter.
  The colours are `TABLE_*` and `HEADER_*` in `theme.rs`, drawn through ListView and header custom draw.
- Clicking a heading of the sector list sorts by that column, numbers descending and the name ascending; the total row stays at the bottom whatever the sort.
- A fill turns redraw off: refilling a visible list with redraw on repaints after every cell and costs about 300 ms of the UI thread.
- A click highlights a row in solid orange; the list's own selection is refused, because the dark theme paints selection in its blue over any custom colour.
- The row under the mouse is drawn white on a lighter brown (`TABLE_HOVER_TEXT` on `TABLE_HOVER`) by every table's custom draw (`colour_row`), which clears the item's hot state so the dark theme's own near-black hover is never painted.

### The Codex tab

The codex entries of one galactic region the commander has not logged yet, and where to find them.

- The dropdown lists the 42 regions as `Odin's Hold · 34 of 752 logged`.
  The tab opens on the region the ship is in (`sql/region_of.sql`) until one is picked, and keeps the pick after that.
- **Logged** comes from the game journals: every `CodexEntry` event in every `Journal.*.log`, keyed on its `Name` token (`$Codex_Ent_DAB_Type_Name;` becomes `codex_ent_dab_type`) and the region id in its `Region` token.
  `journal::read_codex` runs on the `db` thread and caches each file's events by modification time, so only the live journal is read again; it reads only what is still on disk, so an entry logged in a deleted journal shows as not logged.
- **The entries** come from `codex_sighting`, EDSM's codex reports reduced per entry, region and sector (`etl/codex_sighting/`), the only source covering stars and planets as well as biology.
  It is a floor: the game publishes no list of what each region holds, so an entry nobody has reported to EDSM in a region is missing here.
- One table per category, in `theme::CODEX_CATEGORIES` order (`win/codex.rs`), each headed `Biology · 12 of 40 not logged` and listing only the entries not logged, by name.
  A category with nothing left reads `<all N logged>`, one with no reports in the region `<none reported in this region>`.
- The tables fill two columns, split where the two are closest in height; a column too short for its tables shares the height in proportion to their rows, at least three rows each, and scrolls.
- The columns are Entry, Systems reported (in the region), Nearest reported and its distance.
  Nearest is the closest of one system per sector, the first in it to report the entry (`sql/codex_entries.sql`), so it can miss a nearer report in the same sector.
- Clicking a row copies its nearest reported system.
- It is re-read when the tab is opened or another region is picked; an entry logged while the tab is open shows after that.

### The Trade tab

The services worth a detour from where the ship is.

| row | from |
|---|---|
| Universal Cartographics, Vista Genomics, Large pad, repair and rearm | the nearest listed station of each in `station`, `sql/trade_targets.sql` |
| Universal Cartographics (carrier) | the nearest fleet carrier with UC reported in the last 7 days (`CARRIER_FRESH_DAYS`); an older report is not a position |
| Human and Guardian tech broker, Raw, Manufactured and Encoded material trader | the nearest listed station of each in `station_service`, `sql/trade_targets.sql` |
| Sirius tech broker | the nearest of the megaships in `assets/sirius_brokers.csv` |

- Clicking a row copies its system name, highlights the row and logs the copy.
- `assets/sirius_brokers.csv` is pulled once by `overlay/sirius_brokers.py`, from the Elite Dangerous Utilities "sirius brokers" table, because Spansh and the station feeds know only Human and Guardian brokers.
  The brokers are on megaships, which Frontier moves, so a row can go stale; the coordinates are the system's, from any station Spansh lists there.
- Every row is re-read on each jump and when the tab is opened; distances are from the ship.

### The Engineers tab

The nearest engineer for each kind of work, in the Trade tab's table: same columns, same click-to-copy, no Tritium row.

| row | from |
|---|---|
| G5 and a module type, one row per type | the nearest engineer who works that module to grade 5, from `assets/engineers.csv` |
| Suit: or Weapon: and a modification, one row per modification | the nearest Odyssey engineer who offers it, from `assets/odyssey_engineers.csv` |

- Computed on the UI thread from the compiled-in CSVs (`src/engineers.rs`), with no database read: a few hundred rows of arithmetic.
  Re-computed on each jump and when the tab is opened.
- `assets/engineers.csv` is compiled in and changes only when Frontier moves an engineer, so it is pulled once by `overlay/engineers.py`, which refuses to overwrite it.
  The engineers and their market ids come from EDCD's `FDevIDs/engineers.csv`, the grade-5 engineers per module from EDCD's `coriolis-data` blueprints, and each workshop's system, coordinates and name from Spansh by market id.
  To pull again, delete the file and run the script.
- `assets/odyssey_engineers.csv` is pulled the same way by `overlay/odyssey_engineers.py`: the suit and weapon modifications each engineer's Elite Dangerous Wiki page lists, read through the wiki's `api.php`, and each workshop from Spansh by market id.

### The Guardian and Thargoid tabs

Two tabs, one per category: the nearest site of every kind the Canonn codex records, one row per kind, 6 Guardian kinds and 21 Thargoid, each in the Trade tab's table with no Tritium row.

- `assets/alien_sites.csv` is written once by `overlay/alien_sites.py` from the Canonn codex the model stages (`staging.canonn_codex_event`), one row per kind and body, and refuses to overwrite itself; delete it and rerun after an ETL refresh to take newer reports.
- Two kinds carry their role in the name: a Guardian Data Terminal is a structure, where blueprints unlock, and a Guardian Relic Tower is a ruin, where Guardian materials come from.
- The station column names the body; the note gives the number of codex reports and the date of the last one, because Thargoid sites come and go and an old last report is a site that may be gone.
- A site's coordinates are the median of its reports.
- Computed on the UI thread from the compiled-in CSV (`src/alien.rs`, `nearest(pos, category)`), on each jump and when either tab is opened.
- The codex is used rather than the model's `system_poi`, which keeps one point of interest per system: it holds 207 systems with a Relic Tower where the codex has 352.

### The Carrier tab

Where the fleet carrier is, where it is going, the next system to send it to, and the Tritium to fill it with.
It is no table but a card (`win/carrier_card.rs`), painted on the window's dark background: one section per subject under an orange heading, each a column of labelled fields, and a **Copy** button at the right edge of every system's line that puts it on the clipboard and flashes.
Above the card, a text box and **Plot carrier route**: paste any system name and press it to make that system the carrier's destination, as the Map tab's **Carrier Route** does.
Beside them, **To Shinrarta** and **To Colonia** make Shinrarta Dezhra or Colonia the destination, drawn and flashing like **Carrier Route**.

| section | fields |
|---|---|
| Carrier | name and callsign, Location (Copy), the position's error when estimated, the distance From ship, the jump Status, and the Tritium in the tank from the latest `CarrierStats` with when that was read |
| Destination | the System set by a carrier button or **Plot carrier route** (Copy), its Position when only estimated, its Distance from the carrier, the Jumps of the planned route with their total length, and the Tritium for the whole route against what is in the tank |
| Next jump | the known System no more than 500 ly from the carrier that ends closest to the destination (`sql/carrier_next.sql`, Copy), the Jump's length, its Tritium, and the distance left Then |
| Tritium, cheapest | the cheapest station selling it within 250 ly of the ship, asked of Spansh: System (Copy), Station and its type, Distance, Price with the stock and the price's age |
| Tritium, 1,000 t or more | the nearest station holding at least 1,000 t (`BULK_SUPPLY`), at any distance, the same fields |

- `journal::read_carrier` reads the newest journals backwards, at most 60 files, for the carrier's `CarrierLocation`s, the latest `CarrierStats`, `CarrierJumpRequest` and `CarrierJumpCancelled`.
- The jump state, `journal::carrier_phase`, the same text on this tab and on the HUD's carrier line:
  - **jumping to X in m:ss** while the latest request has no later arrival and no later cancel, counting down to its `DepartureTime`; a `CarrierLocation` at the old system written by a login during the countdown is not an arrival;
  - **cooling down, ready in about m:ss** for 5 minutes after the arrival (`CARRIER_COOLDOWN_S`), an estimate, because the game logs no cooldown;
  - **ready to jump** otherwise.
  - A departure more than a minute past with no arrival logged, the commander offline, is taken as an arrival a minute after departure.
- The journal gives the carrier's system but not its coordinates.
  They come from the commander's own `FSDJump`, `CarrierJump` or `Location` there, newest first, and otherwise from the overlay's data (`sql/system_pos.sql`): `system_seen`, a plot-only system of `system_predicted` by id64 or name, or a station's system.
  A carrier sent to a system the Carrier tab suggested is always found, since the suggestions come from the same tables.
- A system nobody has reported, one the commander has not visited either, has no coordinates anywhere: Spansh and EDSM both answer "not found".
  Its position is then the centre of the boxel its id64 encodes (`names::boxel_centre`), at most half the boxel's diagonal out: 69 ly for a `d` system, 139 ly for an `e`.
  The Next jump is then searched within 500 ly less that error, so a suggested hop cannot exceed the carrier's range from wherever in the boxel the carrier really is, and the Carrier row says the position is estimated and by how much.
- The landing candidates are the systems the overlay holds exact coordinates for: the plot-only systems of `system_predicted`, every listed non-carrier station's system, and `system_seen`, plus the destination itself, which ends the route once it is within range.
  A boxel-predicted destination has only its boxel's centre, so the last jump to it is approximate.
- Tritium per jump is `5 + distance / 8 x (1 + (used space + Tritium in the tank) / 25,000)`, rounded (`journal::carrier_tritium`), where used space is `TotalCapacity - FreeSpace` from `CarrierStats`.
  It reproduces the three carrier jumps in the commander's journals to the ton: 30, 28 and 99 t.
- **The planned route** is the next-jump pick repeated from each stop at the full 500 ly until the destination is reached (`Database::carrier_path`, at most `CARRIER_PATH_HOPS`, 100); the Jumps are its stops counted, "at least" when the cap or a stop with no closer system cuts it short.
  The route's Tritium (`journal::route_tritium`) charges each jump with the tank as the jumps before it left it, says how many tons short the tank is when it is, and is unknown until carrier management has logged a `CarrierStats`.
- **The destination's coordinates**, in order:
  - EDSM's (`api-v1/system?showCoordinates=1`, `lookup::Locate`, on its own thread, asked whenever the destination changes; the view is re-read when it answers);
  - the overlay's own data, as for any target (`sql/carrier_next.sql`): `system_predicted`, `system_seen`, a station's system, so a confirmed find seen on a route plot is placed exactly although EDSM has never heard of it;
  - otherwise the centre of the boxel its procedural name encodes (`names::name_centre`): the sector's grid cell from `sector.sector_id`, and the boxel from the letters and leading number read as one base-128 position, `AB-C d1-23` giving `A + 26B + 676C + 17,576 x 1`.
    Checked against 35,245 plot-only systems with exact coordinates, every one lies inside its boxel; the Destination says the position is estimated and by how much, up to 1,108 ly for an `h` system.
  - A hand-named system nobody has reported has none of these, and the Destination says it has no coordinates.
- The destination is kept in app-state `carrier_destination`, one row per callsign, and read back at startup, newest first.
- Re-read when the tab is opened, when a carrier button is pressed and when the journal writes a carrier event; the countdown is re-rendered every second it changes.
- Tritium comes from Spansh's station search (`src/market.rs`), on its own thread so a slow answer never touches the HUD or the database; a burst of jumps collapses to one request for the latest position, which asks both searches in turn.
  - The bulk row is for filling a carrier or a long trip: the cheapest row is often a settlement holding 10 t, and a price is no use without the stock behind it.
  - Only markets updated in the last 30 days count: unfiltered, the cheapest Tritium near Sol is a 2020 price.
  - Stations only, by station type: fleet carriers are left out.
    Carriers sell Tritium at a few thousand credits and stations at tens of thousands, often from a settlement holding 10 t, so the price shown is a station price.
  - Ties on price go to the nearest seller, and ties on distance in the bulk search to the cheaper.
  - Inara is not used: its `robots.txt` disallows the `formbrief=` query its commodity search runs on, and it offers no market API.
- `src/market.rs`, `src/carriers.rs` and `src/lookup.rs` (the jump target's bodies, and a carrier destination's coordinates) are the only parts of the overlay that touch the network.

### The Stats tab

Two line charts, one above the other, painted with GDI (`win/stats.rs`): the confirmed objects visited per day, and the objects confirmed per day.

- One line per kind in `kinds.rs` order, each in its own colour (`STATS_KIND` in `theme.rs`, the first seven categorical slots of the validated dark palette, checked against the map's `MAP_SPACE` background); a kind keeps its colour in both charts and on every day.
- A legend above each chart names every kind with its total over the days shown; it is always there because colour alone never identifies a line.
- Visited (`sql/stats_visited.sql`) is a `system_visited` row joined to `system_confirmed` by name and counted on the UTC day of `first_visited_utc`, so a revisit counts once, on the first day.
  Rows migrated from `visited.json` have no time and are left out.
- Confirmed (`sql/stats_confirmed.sql`) counts `system_confirmed` on its `found_date`, the day Elite revealed the arrival class; rows with no `found_date` are left out.
- Only days holding at least one counted row are on the x axis, evenly spaced, so a week away from the game is not a flat stretch; the axis labels are thinned to fit and read `MM-DD`.
- The y axis is logarithmic, plotting `log10(n + 1)` with gridlines at 0, 1, 10, 100 and 1,000 up to the decade above the largest count: neutron stars run to hundreds a day while black holes and Wolf-Rayets stay in single figures, and on a linear axis every rare kind would lie flat on zero.
- A kind with no count on a day sits on the zero line there; a marker is drawn only on a day it has a count, and a kind with no count on any day draws no line.
- Hovering a chart puts a crosshair on the nearest day and a tooltip naming the date, each kind's count that day and the total.
- Both charts are re-read whenever the tab is opened.

### The Settings tab

Everything a player chooses about the HUD, each saved as a `setting` row the moment it changes and applied at once, without a restart (`prefs.rs`, `App::apply_prefs()`).

| control | `setting` row | default |
| --- | --- | --- |
| Play sounds | `hud.sound` | on |
| Drive the VKB throttle lights | `hud.lights` | on |
| Global navigation keys (the keyboard hook) | `hud.hotkeys` | on |
| Show the HUD when Elite is not in front | `hud.always_visible` | off |
| Title bar and footer on the sector table | `hud.chrome` | off |
| Drag panes with the mouse | `hud.draggable` | on |
| HUD size, 70–175% of the game-fitted size | `hud.size_pct` | 100 |
| HUD opacity, 50–100% | `hud.opacity_pct` | 85 |
| Keep every FSS screenshot | `fss.keep_captures` | off |

- A row that does not parse, or a size or opacity not among the choices, keeps its default and is logged.
- They are not flags: one place to change them, and the state file carries them to the next start.
- A dragged pane's place is saved when the mouse is released, as `hud.place.<pane>` = `x,y` (`prefs::set_place()`): the point the pane keeps when it resizes, its centre's x and its top for a centred pane, its left and bottom for the sector table.
- A saved place off the primary screen is ignored, so a change of screen cannot strand a pane out of sight.

The navigation keys follow, one row per action with its current key; click a row and press the new key.

- The capture runs in the same low-level keyboard hook as the bindings, so it sees the chord exactly as the HUD will: modifiers held with one other key.
  Escape alone cancels; leaving the tab cancels too, so an armed capture cannot take a later keypress meant for the game.
- While capturing, no action fires, so the key being assigned does not also act.
- A chord another action already has swaps with it, and the log says so: two actions never share a key.
- Changes are saved as `key.<action>` rows of the `setting` table and loaded at startup, before the database thread opens the file; an entry that does not parse keeps its default and is logged, never dropped silently.
- A `keybindings.json` left in the data directory by an earlier build is imported once, while the table holds no binding.

Below the bindings, the prediction against the outcome for every predicted system the commander visited, from `system_outcome` in the app-state database.

- The first arrival in a system `system_predicted` holds copies its prediction into `system_outcome` (`sql/outcome_visit.sql`); a later visit never changes it, so the row is the prediction as it stood before the commander saw the system.
- Each star `Scan` there turns on the `found_` flag of the kind its `StarType` belongs to (`sql/outcome_scan.sql`), and `FSSAllBodiesFound` marks the system complete.
- The summary gives, per kind, the visits, the mean prediction and the share found, over all visits and over the complete ones only.
  A kind not found in an incomplete system may simply not have been scanned, so only the complete columns measure absence.
- A system with no prediction gets no row: there is nothing to test.
- The galaxy-wide counterpart is `prediction_outcome` in the model, which records every prediction a refresh resolves.

## Module layout

Each concern has exactly one home.

| Module (`src/`) | Owns | Knows nothing about |
| --- | --- | --- |
| `kinds.rs` | what a predictable object is: stored key, column, on-screen abbreviation, arrival classes, and four flags saying what it is for | the window, colour, widths |
| `theme.rs` | every colour, font, column width and column order | data, drawing |
| `names.rs` | parsing `Blaa Hypai BA-A g5` → sector, mass code, boxel index, and the `PROCEDURAL` regex every SQL file parses a name with | IO, database |
| `journal.rs` | finding, tailing and rolling over `Journal.*.log`; reading `NavRoute.json`, `Status.json`, the `Loadout` and every `CodexEntry` | what an event means |
| `database.rs` + `sql/*.sql` | all SQL, both attached databases | the window, the journal |
| `dbworker.rs` | the `db` thread and the `Ask`/`Answer` vocabulary | what a view needs |
| `table.rs` | a table's rows, cursor and flashes, and each cell's text and colour | SQL, ranking, layout |
| `win/overlay.rs` | the window: per-pixel-alpha layered/topmost/no-activate, drag, placement, scale (`Style`), layout and GDI drawing | what is inside it |
| `win/vector.rs` | anti-aliased icons: strokes, per-pixel coverage, blending into the frame, and each icon's geometry | where an icon goes |
| `win/main_window.rs` | the application window, its tabs and the Log tab's tail of the run log | the HUD, the database |
| `win/expected_table.rs` | the sortable expected-objects table, used by the Map tab's list of a region's top sectors | where its rows come from |
| `win/map.rs` | the Map tab's map at both levels: region shading, labels, the sector grid of an open region, hover, click, double-click and zoom | the database, the dropdown, the search box |
| `win/sector_systems.rs` | the Map tab's list of one sector's systems and click-to-copy | where its rows come from |
| `win/trade.rs` | the Trade tab's table and click-to-copy | where its rows come from |
| `win/codex.rs` | the Codex tab's per-category tables of unlogged entries, their two-column placement and click-to-copy | where its rows come from |
| `fss.rs` / `win/screen.rs` | the FSS capture thread, its PNG and CSV files and the icon labelling / copying the game window's pixels and reading its height | what the spectrum means / when to capture |
| `prefs.rs` | the player's HUD choices: their `setting` names, defaults, allowed values and parsing | the controls, applying them |
| `spectrum.rs` | reading the bar, its spikes and the icons under it from a frame | files, classes |
| `bands.rs` | the published ranges, the learned clusters of each class, the marks on the bar, the worth-scanning kinds and each class's icon family | pixels, drawing |
| `win/carrier_card.rs` | the Carrier tab's card: sections of labelled fields, Copy buttons, the Tritium sections from `market.rs` | where the carrier's fields come from (`app.rs`) |
| `win/settings.rs` | the Settings tab: key bindings and click-to-rebind, and the prediction outcomes of visited systems | how a key is matched, where outcomes are recorded |
| `market.rs` | the Tritium price thread | the window |
| `carriers.rs` | the nearest open carrier, searched live on Spansh on its own thread | the window, SQL |
| `ship.rs`, `route.rs`, `neutron_route.rs` + `kdtree.rs` | jump range; the SHIFT+N router; the live chain solver | the window, SQL |
| `lights.rs` / `win/vkb.rs` | what the throttle LEDs mean / the HID wire | each other's job |
| `win/hotkeys.rs`, `win/clipboard.rs`, `win/focus.rs`, `win/notify.rs` | the keyboard hook, the clipboard, the foreground test, the two sounds | the tables |
| `app.rs` | wiring; `main.rs` parses `args.rs` and runs the message loop | any of their internals |

- `Database::top_targets()` returns finished rows, so `table.rs` renders values rather than choosing them.
- `theme::columns()` is one list driving both header and cells, so they cannot drift.
- Every name for an object comes from `kinds.rs`, so the screen cannot call one thing two things.

### One vocabulary

Separate spellings of one object drift (a TYPE cell truncated one character short of its heading; a prediction reaching the renderer under a second name), so `KINDS` holds one row per object with three names that answer different questions:

| field | what it is | may it change? |
| --- | --- | --- |
| `key` | the classification stored in `system_confirmed.kind` | **No.** It is in the one database that cannot be rebuilt; renaming splits a kind's history in two |
| `column` | the `system_predicted` column and the name a cell asks a `Row` for (`Row::number()`) | with the model |
| `abbr` | the one on-screen abbreviation: column heading and TYPE cell (`TYPE` is 8 wide to hold it) | freely |

- The `ranks`, `rare`, `chime` and `chime_predicted` flags are not derived from one another: what ranks, what is worth a line and what is worth a sound are different questions, even where they name the same kinds.
- `database::fragments()` generates every SQL list and `CASE` ladder from `KINDS` (`{{CLASS_CASE}}`, `{{ARRIVAL_S}}`, `{{ARRIVAL_T}}`, `{{ABBR_CASE}}`, `{{RANK_CASE}}`, `{{RANK_BY}}`, `{{RARE_MAX}}`, `{{ALL_CLASSES}}`, the `p_*` lists) and fills the `.sql` files once at startup.
- `kinds::assert_vocabulary()` checks at startup that no arrival class names two kinds and that at least two kinds rank.
- `theme::assert_columns_cover_kinds()` checks that `theme.rs`'s column list and `KINDS` name the same set, since a kind missing from one would be computed, ranked, chimed for and never shown.

## The ship's jump range

`src/ship.rs` computes it, the overlay's only flight physics besides the routers.

- It is written to the log (`ship: jump 75.3 ly   neutron 452 ly (x6, explorer_nx)`) at startup and whenever it changes, not shown: on the HUD it would be a line that never moves, taking width from rows that move every jump.
- `SHIFT+N`, the chains and `lights::fuel_fraction()` (from `FuelCapacity`) use the parsed `Loadout`.
- A missing `Loadout` or an unrecognised drive yields nothing rather than a guess: in flight a plausible number nobody can check is worse than a blank.
- With `--sector` the journal is not read, and there is no range.

```
range = optmass/(unladen + fuel + reserve)
        * (min(maxfuel, fuel)/fuelmul) ** (1/fuelpower)
        + jumpboost
```

- `optmass`, `unladen`, `fuel` and `reserve` come from the `Loadout` event, the only source that knows the engineering.
- `fuelmul`, `fuelpower`, `maxfuel` and `jumpboost` appear in no journal event and are transcribed from EDCD/coriolis-data into a static table, so the overlay never reaches the network.
- Checked with zero free parameters against 1,192 unboosted jumps on one loadout: 24 breaches of the predicted ceiling, worst +0.063 ly (0.08%); the largest fuel burn on record was 6.80 t against the table's `maxfuel` of 6.8.
  Selecting those jumps needs a hash of the full module list (slot, item, blueprint, experimental, every modifier); `ShipID` plus `UnladenMass` is not enough, as ShipIDs are reused.
- `Loadout.UnladenMass` is used, not a reconstruction from module masses: coriolis-data lacks modules such as `int_fighterbaymk2_size5_class1_free`, an unknown module counts zero, and the result comes out 10 t light, always optimistic.
- `Loadout.MaxJumpRange` is not used: it is the on-fumes ceiling (unladen plus one jump of fuel), reproduced by the formula at `unladen + maxfuel` as 82.615, against a real full-tank 75.3, a 10% overstatement.
- A full tank is the range used: the heaviest fuelled state, so every leg stays flyable as the tank drains.

### The neutron multiplier belongs to the hull

Nothing in the journal reports a supercharged range, so the multiplier is measured from `BoostUsed: 4` jumps:

| ship | boosted jumps on record | max flown | ÷ laden range |
| --- | ---: | ---: | ---: |
| `explorer_nx` (Caspian) | 563 | 469.06 ly | **5.97×** |
| `mandalay` | 10 | 360.14 ly | **3.87×** |

- Neither maximum exceeds its multiplier, the shape of a game-side cap; both fall just under because the longest jump was not flown at the heaviest fuel state.
- `ship::neutron_boost()` is the one place that decides: `SHIP_NEUTRON_BOOST` gives `explorer_nx` 6.0, and every other hull gets `DEFAULT_NEUTRON_BOOST` 4.0, the standard rule.

### Loadout is watched, not read once

- The game writes a `Loadout` on login, every outfitting change and every ship swap; `App::take_loadout()` takes each one from the journal poll, so a swap re-ranges the overlay within a poll and every chain, which records its solve range, goes stale and re-plots.
  A Caspian and a Mandalay differ by half the boosted range: a 49-jump chain against one that cannot be flown.
- `INTEREST_KEYS`, the substring reject `journal::interesting()` runs on every journal line, must name `"Loadout"`, since a `Loadout` carries neither `StarPos` nor `StarClass`.
  Without it the range is frozen at startup and the fuel light divides a live `FuelMain` by the previous ship's tank (a 64 t Type-9 swapped for a full 16 t Cobra shows exactly 0.25, solid red, on a full tank).
- `journal::read_loadout()` and `latest_journal()` pick the newest journal by mtime, not name: old `Journal.<yymmddhhmmss>` files sort above `Journal.<iso8601>` ones.
- `App::run_startup()` takes the newest `Loadout` on disk once; after that every `Loadout` arrives through the ordinary poll, so no journal is re-read on the paint path.

## Neutron jump mode

`SHIFT+N` on a selected row plots a minimum-jump route to it through neutron stars; `SHIFT+N` again tears it down.

- The next hop takes the Nearest table's neutron row, and the footer reads `<n> jump(s) left to <destination>` each time the next hop is copied.
- `route::plan()` in `src/route.rs` is the pathfinder; `Database::neutron_corridor()` (`sql/neutron_corridor.sql`) is its one query.
- Arrival matches anywhere in the remaining route, because a hand-flown cone route gets overshot; hops behind are dropped and the count updates, and the next hop is copied.
- Arriving off the route is not an error and does not tear it down, so a detour to scoop leaves it intact.
- The route is in memory only: the app-state database records what was seen, visited and found, and a plan is one keypress to rebuild; a restart drops it.

Pathfinding:

- **Breadth-first is exact.** Every edge costs one jump, so a levelled BFS (each node asking `src/kdtree.rs` for every cone in boosted range, no cone revisited) is provably minimum-hop; A* has nothing to improve.
- **The first leg may be several plain jumps.** From one real deep-space position the nearest neutron was 115.9 ly against a 75.3 ly range, so the first cone may be up to three unboosted jumps away (`START_LEGS`), and a destination that close needs no cone.
  The galaxy map's own plotter finds the ordinary systems in between (they outnumber neutrons about 58 to 1), so nothing checks they exist.
- **The corridor allowance is absolute.** Nodes come from a prolate spheroid with the endpoints as foci, `dist(start) + dist(dest) <= direct + pad`.
  A proportional 15% on a 22,820 ly run permits a 3,423 ly detour, selecting 654,108 neutrons in 789 ms, because the spheroid fattens with the square of the allowance.
  The pad is 600 ly, widened once to 2,500 before reporting failure, since "no route in this box" is not "no route".
- **Capped at 10,000 ly** (`route::MAX_ROUTE_LY`): past that the honest advice is a fleet carrier or the neutron highway; a 48,578 ly plot to Sol selected 2.95M neutrons and spent 4.5 s fetching them before the search started.
- **Fuel is not modelled.** A supercharged jump burns the drive's maximum fuel and you cannot scoop at a neutron star, so the router answers "shortest chain of cones", not "can I get there".

## Keys and visibility

- **One cursor, not a key per row**: rows reorder and drop out as they are answered, so a per-row key would mean something else by the time it is pressed.
- **Whatever the cursor lands on is copied**, with no confirm key; the selected row's solid background band (`theme::SEL_BG`) is the only indicator.
- Every key copies a system name, what the galaxy map's search accepts; a sector row copies the best system inside its sector and the footer names it.
- **The cursor reaches only the tables on screen.** On the galaxy map (`GuiFocus` 6, `App::set_planning()`) the keys cycle the sector table, `POI` and the carrier table; everywhere else Nearest is the only table.
  - Opening the map puts the cursor on the sector last picked there, or the ship's own sector the first time; closing it returns the cursor to Nearest.
    Neither copies: the clipboard changes only when a key moves the cursor.
  - A repaint that changes the selected row's system re-copies it only while the last copy came from the table the cursor is in (`App::copied_in`), so switching screens never overwrites what was copied on the other one.
- Table paging skips empty tables and remembers each table's position by row target, not index, since rows reorder; an answered target is gone and paging back lands on the top.
  The sector table remembers the sector's name instead, because the system a sector row copies changes as its candidates are answered.
- Row movement wraps.
- The `REGION` row is not selectable.
- The cursor is clamped, not reset, on refresh.
- `BINDINGS` in `src/win/hotkeys.rs` holds the default bindings; the Settings tab rebinds them and the `setting` table keeps the changes.

### The focus gate

- Keys are captured by a global low-level hook (`WH_KEYBOARD_LL`), because the overlay never holds focus; it always passes the key on so the game still sees it.
- `App::tick()` drains a press only when `focus::is_foreground()` holds: a window titled `Elite - Dangerous`, one of the overlay's own, or no foreground window.
  Ungated, every arrow press anywhere on the machine would move the cursor and overwrite the clipboard.
- A binding fires only when the keys held are exactly its chord, so `SHIFT+Down` in a text field is not a cursor move.
- The hook only records presses into slots behind one mutex; `hotkeys::take()` and its siblings read and clear in one step.
  Navigation shares a last-press-wins slot; `SHIFT+BACKSPACE`, `SHIFT+N` and `SHIFT+A` each have their own, or an arrow in the same 120 ms tick would swallow the press that records or toggles something.
  A lost toggle leaves the key meaning the opposite on the next press, and a key-repeat burst collapses to one toggle.
- The clipboard is written through Win32 (`src/win/clipboard.rs`) as `CF_UNICODETEXT` handed to the system, so a copy outlives the overlay.
- The Settings tab's "Global navigation keys" removes and restores the hook.
- The overlay hides unless Elite or the overlay has the foreground; it never takes focus (`WS_EX_NOACTIVATE`, `MA_NOACTIVATE`), so clicking or dragging it leaves Elite in front.
  "Show the HUD when Elite is not in front" disables hiding.

### `SHIFT+BACKSPACE`: no such system

The only key that records a finding: the name would not plot, or you arrived and nothing was there.

- **It filters, it does not delete**: a row goes into `system_wrong` in the app-state database, and every read offering a destination filters against it.
  The app may never write the model, whose builders would undo a deletion on the next rebuild, and this is the only negative evidence the project collects.
- Pipeline re-runs cannot reproduce these rows, so they belong with the flight log: back them up.
- Only guesses can be marked: predictions, plot-only backfill, a sector row's best system and unfound catalogue stars.
  A confirmed find, POI, carrier or neutron is a place the game says exists, so failing to plot is a spelling or stale-dump problem; the footer says so.
- The focus gate matters most here: `SHIFT+BACKSPACE` is an ordinary chord in a text field.

### `SHIFT+A`: same system, renamed

The galaxy map sometimes resolves a predicted name to a system the game spells differently.
A rename that keeps the boxel and index settles itself through the derived address (see *Not visited, and arrival class not yet revealed*); `SHIFT+A` is for the rest.

- With a route plotted, `SHIFT+A` (or whatever key Settings binds) on a prediction, plot-only backfill, a sector row or unfound catalogue star records in app-state `system_alias` that the row's system is the route's destination (`NavRoute.json`'s last hop, with id64, position and class).
- An aliased unfound star leaves the Current sector table at once (`sql/unfound_targets.sql` skips a `system_alias` name), as one marked wrong does.
- An unfound star's alias reaches the model through `scripts/export_commander_aliases.py`, which copies the aliases of real catalogue stars into `input/commander_alias.parquet`; `etl/system_catalog` then sets that star's `system_id` from the alias's id64, and the next `etl/system_unfound` refresh drops it.
- A refusal names the key actually bound, read from the binding, never a hard-coded `SHIFT+A`.
- Every read settling a prediction by revealed class (`{{SEEN_JOIN}}` in `database::fragments()`) follows the alias.
- It writes only to the app-state database, only for a guess.
- A destination already claimed by a different system is refused, naming it; a differing boxel index is recorded with a warning.
- `system_alias` is created when the database is opened, so an older state file still reads.

### No key hints on the HUD

- The HUD shows no list of its keys: the Settings tab lists every binding and rebinds it, so a hint bar would only take height over the canopy.
- Key labels in Settings are title case, abbreviated only where unambiguous (`[Pg Up]`, `[Shift+Backspace]`); upper case reads as shouting.

### Icons are drawn anti-aliased

GDI draws no anti-aliased lines, and at the HUD's 19 px a curve built from them snaps to the pixel grid and reads as boxes.

- `win/vector.rs` describes an icon as round-ended strokes, samples each pixel's coverage 4 × 4, and blends the colour into the frame by that coverage.
- It paints after the alpha pass, straight into the premultiplied pixels, so an edge pixel fades into whatever is beneath it, the dark panel or the game, instead of being given one of `apply_alpha`'s fixed alphas.
- The DNA, volcano and body icons are drawn this way; `cargo test --release preview_icons -- --include-ignored` with `ICON_PREVIEW=<png>` (and `ICON_ZOOM`, default 8) writes each at 19 and 48 px for a look.

### Width and the clock

- The left pane is sized from its table alone (plus the title bar with the chrome on); the chrome's footer is clipped at the edge, so a 400-character line renders at 934 px instead of 2,820.
  A clipped hint is recoverable from this file; a window covering the canopy is not.
- The clock (`hh:mm` local) sits at the right end of the carrier line, which is always drawn to hold it.
  It is near-white (`CLOCK_TEXT`) with a one-pixel dark edge (`CLOCK_EDGE`), so it reads over any background; the edge is not `KEY` black, which would cut holes in the text.
- `App::update_clock()` redraws only when the minute turns.

## The throttle LEDs

The VKB STECS has three RGB LEDs.
`src/win/vkb.rs` (`Throttle`) is the wire, HID feature report `0x59`, and a no-op on every call with no VKB plugged in; `src/lights.rs` is the policy and the only module picking an LED colour.
The Settings tab's "Drive the VKB throttle lights" turns them off, darkening them first.

| LED | shows | dark when |
| --- | --- | --- |
| left: fuel, fraction of the main tank | green above 80%, gradient through yellow to red between 80% and 25%, fast red flash below 25% | no reading: game not running, or no `Loadout` has given the tank size |
| middle: arrival star of the next jump | blue for neutron, flashing blue for white dwarf, flashing red for black hole | any other class, or no jump targeted |
| right: ship state | white while the cargo scoop is out, flashing blue while shields are down; shields win | otherwise, and whenever not `InMainShip` |

- A stale fuel level after the game closes is a lie the commander cannot see, so no reading is dark.
- The middle light stays dark for ordinary stars, or it would mean "a jump is targeted" instead of "look at this one"; which classes count comes from `kinds::key_of_class()`.
- Shields win over the scoop: a warning a note can hide is not a warning.
- Right-light state comes from `Status.json` `Flags` bits `CargoScoopDeployed`, `ShieldsUp` and `InMainShip`, named in `journal.rs`'s `STATUS_FLAGS` and read through `journal::flag()`.
- `ShieldsUp` is clear on a ship with no shield generator, so `ship::has_shields()` must find a generator in the `Loadout` before the light may warn.
- `Flags` is 0 at the main menu, so `lights::ship_color()` requires `InMainShip` before either state lights; that `Status.json` has no `Fuel` either, so fuel is already dark.

### The middle light needs two sources to agree

- `FSDTarget` gives the next system and its class, about six seconds after each jump, but nothing retracts it.
- `Status.json`'s `Destination` is retracted when the route ends or the target changes, but never gives the class.
- The light requires the same system name from both and that it is not the current system, since the game leaves the destination naming the system you arrived at.
- `NavRoute.json` is not used: its first entry is the origin and it does not shrink as you fly.
- `App::run_startup()` seeds `next_jump` from the last row of `JournalReader::harvest_classes()` (file order, so the most recent target), or the light stays dark after a restart; the `Destination` check keeps an old seed safe.

### Writing to the device

- Every report replaces the device's whole table and an omitted LED goes dark, so `Lights` holds all three as one state and `Throttle::show()` resends them together.
- VKB gives 3 bits per channel, so the gradient is 15 steps; `#ff8000` comes back as `#ff9200`.
- `Lights` sends nothing when the colour has not moved; the tick runs eight times a second, the light changes a few times an hour, and HID is enumerated once, so the write stays on the UI thread.
- Fuel comes from `Status.json`, the only live source (module health is only in `Loadout`, a login snapshot).
  `journal::read_status()` is mtime-gated, but the game rewrites the file in place, so a parse failure leaves the remembered mtime untouched and the next tick retries.
- An override holds until the throttle is power-cycled and the protocol has no release (`Throttle::off()` darkens, it does not hand back), so `App::shutdown()` calls `Lights::clear()` before unhooking the keys and stopping the worker.
