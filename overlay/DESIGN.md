# Explorers Companion — sector-ranked rare-object HUD

`ed-overlay.exe`: a HUD pinned to the top-left corner of the screen, plus a standard application window with tabs.
`README.md` covers the build, where the state lives and every flag; this file is why it behaves as it does.

```
overlay.cmd                                    # follow the journal, state in elite_mapping_current.duckdb
ed-overlay.exe                                 # follow the journal, state in %LOCALAPPDATA%\ed-overlay
ed-overlay.exe --sector "Eol Prou"             # force a sector, ignore the journal
ed-overlay.exe --font 13 --opacity 1.0 --x 40 --y 200
```

## What it shows

The top 10 predictions in the commander's current sector, as a bare table that drags from anywhere.

- Chrome is hidden by default; `--chrome` adds the title bar, the live status line (current system, row counts, clock) and the footer.
  With the chrome hidden, footer lines go to the log on every refresh rather than being dropped.

| Column | Meaning |
| --- | --- |
| `SYSTEM` | Predicted system name. Dimmed once the galaxy map has revealed its arrival class, because it is no longer a gamble. |
| `DIST` | Light-years from the commander, on every table. A leading `~` marks a boxel centroid rather than a position, good to about ±640 ly at mass code `h`. POIs and plot-only systems have exact coordinates and get a plain number. A dash means unlocated, which is not the same as near. |
| `TYPE` | What kind of target the row is; for a boxel-gap prediction its mass code, rendered `Mass H` and highlighted at `h`. Not called `MC`, because POIs, neutrons and carriers share the column and are not mass codes. |
| `BLK HOLE` `WOLF-RAY` | Black hole, Wolf-Rayet: the two that decide the ordering. |
| `HERBIG` | Herbig Ae/Be, the only prediction whose rate rises with galactocentric radius, so the best rim-ward target. |
| `O-TYPE` | O-type star (~30,000–50,000 K, blue). Concentrated in mass code `g`; the richest sectors sit ~55 kly from Sol on the far side of the core, so check distance before routing. |
| `NEUTRON` `WHT DWRF` | Neutron star, white dwarf; near their base rate almost everywhere. |

**Every column must be confirmable by a route plot**, because the only thing the overlay learns about an unvisited system is its arrival star.
Two predictions fail that test and are not shown (both stay recorded in `DEAD_ENDS.md`):

- `He GIANT` (`p_hr`): a helium-rich gas giant is a planet.
- `SUPERGNT` (`p_supergiant`), despite 2.4× observed over expected, the best-validated prediction in the project.
  The journal's `StarClass` (`FSDTarget`, `StartJump`, `NavRoute.json`) is short codes only; across 201 journals the set is `M K N F G TTS A L T Y H B AeBe WO DC O DA WNC D WN WC SupermassiveBlackHole DQ DAZ DAB CN`.
  A B supergiant plots as plain `B`; the long `B_BlueWhiteSuperGiant` spellings belong to `Scan`, which needs the ship in the system.
  The column confirmed 0 systems while `HERBIG` confirmed 140.

### Probability cells

- Each probability is a two-decimal fraction (`0.38`), right-aligned, shown separately.
- Colour is a 10-step red→orange→yellow→green ramp, linear over `0.05`–`0.60`, fixed rather than stretched per sector so a number is always the same colour.
  The range is measured: the 3,669,169 displayed values at or above `0.05` have median `0.163`, p99 `0.576`, max `0.576`, so most cells land red or orange and green stays rare enough to mean something.
- A `-` (below `0.01`, `theme::MIN_SHOWN_PROBABILITY`) is uniformly dim.
  That bound is deliberately not the gradient's `0.05`: one answers "is this worth a line at all", the other "what does a colour mean"; values between clamp to the bottom step.
- The last row, `<sector> TOTAL`, sums each probability over every boxel-predicted, unvisited system in the sector: the expected number of undiscovered objects of each type.
  The cursor skips it, because you cannot fly to a sum.
  Plot-only systems get no total row; their count is in the footer.
  It carries the cube icon with the centre cell blue and the `REGION` line's colour, and the adjacent sectors follow it in the same table.
  The table keeps room for ten targets, the total, the 26 adjacent sectors and the `REGION` line, and grows by up to three rows only when unfound catalogue stars are listed.
  It uses the **count** ramp: the same ten colours, log-scaled over 0.1 to 100 expected objects, fixed, because 0.6 expected black holes must not paint the same green as a 60% chance of one.

### Probabilities are never combined

- There is no headline `RARE%`: the `p_wr` column comment says it competes with `p_bh` for the same primary star, so the two must never be added or multiplied.
- The ranking uses `max(BH, WR)`, which needs no independence assumption.
- Only BH and WR sort the list; the other six are shown but not ranked on, because neutrons and white dwarfs would rank by how ordinary a system is.
- Rows are ranked by probability, not distance: everything in a sector is already close, so the remaining question is which system is most likely to hold something.

### Read the ranking with this caveat

Every `p` is fitted per (mass code, plane_r band), and a sector sits inside one band, so a sector offers about four distinct rows, one per mass code present.
The ranking is effectively highest mass code first, tie-broken on expected body count (computed, not displayed) and then alphabetically.
**Within a mass code the ordering is not meaningful**; that is the first thing to fix before trusting a rank inside one.

### What is in the pool

**Boxel-predicted only.** The `is_catalog` column comment says "always filter or group by this":

| | rows | what it is |
| --- | ---: | --- |
| `is_catalog = TRUE` | 2,253,534 | **Excluded.** Plot only: in the dumps with exact coordinates but no body data, the shape a plotted route leaves (`sources.md`). The model's column is still `is_catalog`. |
| `is_catalog = FALSE` | 220,489 | **Shown.** Boxel-predicted: in no dump, inferred from a gap in the Stellar Forge's index. |

- Only 5,409 of 12,100 sectors hold any predicted system, so an empty table is common; the overlay says which kind of empty it is.
- Mass code `e` dominates: e 156,845, f 16,012, g 15,565, h 32,067.
  An `e` row's best rare can be an order of magnitude below an `h` row's.
- Coordinates are the boxel centroid, up to 1280 ly across: you can arrive at the exact point and find nothing.
- The layer is thin and core-biased: a lower bound, not a census.

**At least 1% on one rare** (`MIN_RARE` in `src/database.rs`): `≥ 0.01` on at least one of `BH`, `WR`, `HERBIG`, `O-TYPE`, per column, never summed.

- `NEUTRON` and `WHT DWRF` are excluded from the test because, at base rate everywhere, they would pass everything.
- It removes 7,870 of 220,489 rows (7,736 `e`, 134 `f`), leaving 212,619 across 5,363 sectors; the weakest survivor offers 0.0149 on its best rare.
  It is in practice a filter on `e`, and raising it would cut into `e` first and hardly touch `f`/`g`/`h`.

**Not visited, and arrival class not yet revealed.** A route plot rewrites `NavRoute.json` with every hop's class and `FSDTarget` gives one; a boxel prediction asks only "what is the arrival star", so a revealed class settles it (rare: it moves to Confirmed; ordinary: nothing is left to gamble on).

- All four pools apply this test: the sector rows, the `SECTOR`/`REGION` totals and the adjacent sectors' sums.
  Applying it to the rows alone makes a route plot through a neighbour invisible: Graea Hypa had 160 unvisited predictions of which 106 were already classed, summing to 45.5 expected black holes against a true 3.5, and 172 sectors carried some version of that error.
- A revealed class reaches a prediction three ways (`{{SEEN_JOIN}}` in `database::fragments()`): by name, by the hop's `SystemAddress`, and through `system_alias`.
- The address arm also covers boxel predictions, which have no id64 in the model: `sql/boxel_id64.sql` derives the address from the mass code, the grid cell holding the boxel centroid and the index at the end of the name.
  Crafted sector spheres overlap, so the galaxy map routes a predicted name such as `Col 359 Sector IH-V e2-13` to a system it calls `Stock 1 Sector HW-W e1-13`.
  Both names point at the same boxel and index, so the hop's address equals the derived one and the plot settles the row with no keypress.
  The derived address agrees with the hop's address for all 20 `SHIFT+A` aliases whose two names share an index; the 3 that disagree pair different indices.

## Adjacent sectors

Below the current sector's `SECTOR` row, in the same table, come the 26 grid cubes touching the one the ship is in, with the expected objects left in each, so "is this sector worth staying in" is decided against something.
One table keeps the current sector and its neighbours in one column layout and under one cursor, and the `SECTOR` row's centre-blue icon places the current sector in the same picture as its neighbours.

- Procedural sectors are 1280 ly cubes on one grid, origin (−49985, −40985, −24105), and `sector.sector_id` is the cell, `x + 128·y + 16384·z`.
  The ship's cell is computed from its position, so it works inside a hand-named sphere too.
- There are always 26 rows, in three groups: the 8 cubes in the ship's layer, then the 9 below it, then the 9 above it, each group nearest first.
  The grid has six populated layers, and the galactic plane sits on the boundary between the middle two (y ≈ −25 ly), so near the plane one vertical group is tens of light-years away.
- Distance is exact: from the ship to the nearest point of the cube, 0 when touching it.
- The icon in front of the name shows the cube's place: a 3×3 parallelogram is the ship's layer seen in perspective, north (+z) at the back, with the ship's cube left out as a hole.
  A cube in the same layer is filled blue; a cube above or below floats blue over or under its footprint, joined to it by a line.
- An empty cube keeps its row with `-` in every column, and the cursor skips it, because nothing in it can be copied.
- A cube no system we know of lies in has no `sector` row and so no name; it shows `unnamed sector` in grey and is reached by hand on the galaxy map.
  Most of these sit beyond the outermost populated layers.
- Systems named under a hand-authored sector are not counted in the cube they lie in: their `sector` is the sphere's name, which has no grid cell.
- Cells are expected counts summed over the sector, formatted and coloured like the `TOTAL` row on the count ramp, so the better neighbour is one glance.
- The pool is identical to the sector table's (boxel-predicted, not plot only, not visited, not classed), or the comparison would be between two different things.
- Its last line is the current region's `REGION` total over the same boxel-predicted pool, so a neighbour reads against the whole region; the cursor skips it, as it skips the sector table's totals.
  The region is the sector's; in a hand-named system, whose `crafted` sentinel has none, it is the `region_map` cell under the ship (`sql/region_of.sql`).
  The region's plot-only total is not shown: no HUD table lists plot-only systems.
  In hand-named space there is no region, so there is no line.

### What an adjacent-sector row copies

- The best system in that sector, by the `{{RANK_BY}}` fragment `database::fragments()` builds (`greatest(p_bh, p_wr)`), the one ranking expression in the app.
  So an adjacent-sector row hands back the system that sector's top row would offer on arrival, and the two cannot disagree.
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

## Two HUD panes

The HUD is two layered windows of the one `Overlay` type, told apart by `win::overlay::Pane`.

- **Left** (`Pane::Left`, at the screen's left edge or `--x`/`--y`): the sector table, with no heading, and the footer.
  It gives the current sector and its 26 neighbours the full screen height.
- **Top** (`Pane::Top`, centred on the primary screen): Confirmed and Nearest side by side, the next-jump panel under them, and the carrier line.
  It keeps its centre when it resizes, and dragging it moves that centre.
  Its font is `theme::TOP_FONT_DROP` (2) points under the left pane's, the two tables carry no title line because their first column is headed `CONFIRMED` and `NEAREST`, and `theme::TOP_TABLE_GAP` (4) character widths separate them.
- Both hide together when Elite loses focus, and both repaint from the one `Scene` on every redraw.

## Next jump

A panel under Confirmed and Nearest, modelled on SrvSurvey's `PlotJumpInfo`, so the same information is in the HUD rather than in a second app.

- **Shown** while the next jump target (`FSDTarget`) is a hop still ahead on the plotted route (`NavRoute.json`), or while the FSD is charging (`Status.json` flag `1 << 17`); hidden on arrival at the target or once the route is cleared.
- **Header**: `Next jump:` and the target's name; `class: X` at the right, green for a rare class `kinds.rs` confirms, blue for a neutron, amber for scoopable and orange for anything else.
- **Route bar**: `#N of M` hops, then one segment per hop scaled by distance, then the whole route's length.
  - The next hop is cyan, with a cyan tick where the ship is and a chevron at the target.
  - A hop longer than the ship's unboosted range (`ship::jump_range`) is teal: a neutron or injection boost; dimmed once flown.
  - Every other hop is the dim base; a tick ends each hop, tall for a scoopable star (`KGBFOAM`), bright ahead and dim behind.
- **Status lines**, fetched once per target on a background thread (`src/lookup.rs`), so a slow request never stalls the HUD:
  - EDSM `api-system-v1/bodies?systemName=` gives the discoverer, the date and the body count.
  - The Spansh dump `api/dump/<id64>/` gives the bodies, their biological and geological signals and the stations and carriers.
  - `Undiscovered system` means neither feed has a body for it; on a rare class it reads as a first discovery in the confirmed green, the case this project exists for.
  - EDSM `api-system-v1/traffic?systemName=` gives `Traffic last 24 hours: d, week: w, ever: t (EDSM)`, shown only when somebody has ever been there.
  - The counts line lists only what is non-zero.
  - `Now entering: <region>` when the target lies in another galactic region than the ship, both read by position from `region_map` (`sql/region_of.sql` with no sector), asked once per target.
- The panel's logic is `src/jump.rs`; it draws nothing and is unit-tested.

## The carrier line

The top pane's last line, in the carrier colour, under the next-jump panel: `CARRIER <callsign> · <system> · <jump state> · Tritium <t> t`.

- The jump state is the Carrier tab's, counting down every second while a jump or the cooldown runs.
- The line is carrier amber; only its jump state turns green (`CARRIER_READY`, the confirmed-find green) when the carrier is ready to jump (`journal::carrier_ready`), so `journal::carrier_line` returns it in three parts: the callsign and system, the state, the Tritium.
- No line when the journals hold no `CarrierLocation`.

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

Places that are not a gamble: one carrier, one neutron and the live route chains, at most four rows. Material traders and technology brokers are on the app window's Trade tab, not here.

- It shares the top pane's first line with Confirmed; `Overlay::layout_top()` places it flush right so its right edge shares the margin of the next-jump panel below.
- Every row has the same shape, `theme::nearest_columns()` = `TYPE 7 | JUMPS 5 | NEXT 26` (334 px):

| column | |
| --- | --- |
| `TYPE` | `NEUTRON`, `CARRIER` or a route's far end (`COLONIA`, `FOUNDER`). Seven characters at most. |
| `JUMPS` | Jumps away, rounded up. A neutron is counted at the unboosted range, because you fly to it to get the boost. A carrier is counted at the boosted range: unboosted × `ship::neutron_boost()`, or `BOOSTED_LY` (500, `src/app.rs`) before a `Loadout` is read. A route row counts its remaining hops exactly. |
| `NEXT` | The system to jump to, and the cell the cursor copies. For a route it is the next hop, not the far end. |

- There is no `SYSTEM` column because `NEXT` is it, and no `DIST` because `JUMPS` is the same fact in the unit you act on.
- Cursor order follows the eye: Confirmed, Nearest, Current sector; the `SECTOR` and `REGION` rows and empty adjacent sectors are skipped.

### Carriers

- One carrier row, galaxy-wide, from `carrier.is_reliable`: parked over a year ago **and** seen within the last 90 days.
  Both halves matter: 30,262 carriers have an old `last_moved` only because nobody has looked since.
- Once you are in the carrier's system, `NEXT` shows the carrier's name, the thing you need there.
  `+UC` leads the name when it buys exploration data, the reason to choose one carrier over another, placed first so truncation cannot remove it.
  The callsign stays on the row as `detail`.

### Neutron stars

- The nearest system whose primary star is a neutron, since primary is arrival.
- Not filtered against `system_visited` or `is_known`: a neutron is for getting somewhere, and the boost works as well the second time.
- Carrier and neutron are told apart by the `NEXT` colour, amber against pale blue.
- Reads the mirror's `system_neutron` (3.5M rows, derived by `etl/refresh_current.py` from `system_known` and `body`) instead of scanning 200.8M.
- Ranked on coordinates alone and named afterwards: joining all 3.5M rows to `sector` for the name before the `ORDER BY` builds 3.5M names to keep three.
  The scan is 30 ms and the join was the other 250; the read is 32 ms.
- A plotted `SHIFT+N` route replaces this row (see *Neutron jump mode*); the carrier row is unaffected, and each is cached separately so plotting costs neither query.

### Route chains

Chains are solved live, from where the ship is, at the range it flies.

- `Corridor::solve()` in `src/neutron_route.rs` (the same solver as `common/neutron_route.py`) plots one in a second or two over half a million neutron stars, on the worker as `Ask::SolveRoute`.
  A chain solved from Colonia is worthless 3,000 ly along it, and one solved for a 500 ly boost is unflyable in a ship that makes 472.
- The app-state `route` table supplies only the endpoints, a name and position for each end (`Ask::RouteHops`, read at startup); storing a route is how a destination is registered.
- The nearest carrier gets a solved chain too: its `JUMPS` is the chain length and its `NEXT` the first hop, following whichever carrier is nearest.
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
- **In reach:** inside `boosted_ly`, the range the chain was solved for, stored on every row for this test; an unreachable hop is a paste that will not plot.

Nearest among those is the next link; reaching past it would skip a supercharge the chain assumes.
Nothing is pinned, so the row is right after a deviation, a restart or a jump somebody else plotted.
With nothing in reach (off the route), the nearest progressing hop is offered anyway as the place to rejoin.
At either end of the chain the spent direction's row is absent.

**Following.** Landing the cursor on a route row starts following it, because landing on a row copies it and the clipboard is the statement of intent; copying any other row stops it.

- A followed row is prefixed `>`.
- Arriving anywhere on that chain copies the next hop, matched against any hop so a skipped jump still advances; an arrival off the route leaves the clipboard alone.
- Arriving at the last hop ends following.

## Confirmed

### Confirming from the galaxy map

**This is the tool's edge.** A route plot rewrites `NavRoute.json` with the arrival `StarClass` and exact `StarPos` of every hop, so one plot confirms dozens of systems thousands of ly before anyone flies there.

- `FSDTarget`/`StartJump` add the same fact one system at a time.
- Everything lands in `system_seen`, and the Confirmed table is built from it.
- The whole route is harvested; the file is mtime-gated, so it is re-parsed only when a plot happens.

`KINDS` in `src/kinds.rs` maps classes to kinds; `key` is stored in `system_confirmed.kind`, `abbr` is the column heading:

| stored `kind` | shown | classes matched |
| --- | --- | --- |
| `BH` | `BLK HOLE` | `H`, `SupermassiveBlackHole`, `SuperMassiveBlackHole` |
| `WR` | `WOLF-RAY` | `W` `WN` `WNC` `WC` `WO` |
| `HERBIG` | `HERBIG` | `AeBe` |
| `O-TYPE` | `O-TYPE` | `O` |
| `NEUTRON` | `NEUTRON` | `N` |
| `WHT DWRF` | `WHT DWRF` | the fifteen `D*` codes |

Both supermassive spellings are matched: the journal writes `SupermassiveBlackHole`, the model's `body` table `SuperMassiveBlackHole`, and matching one would drop Sagittarius A*.

### A system somebody has reported is not a find

**Confirmed excludes any system somebody has already scanned**: one with body data in the model's `system_body`, whose rare arrival star is therefore already discovered.
Being in `system_known` is not enough: a route plot alone puts a system there with its arrival-star class and no bodies (`sources.md`), and its rare star is still undiscovered.

- A `BLK HOLE` row here is a black hole nobody has scanned, often one a route plot already put into the dumps.
- **The filter is `known`, never `not predicted`.** Most survivors are in no dump and no prediction, and they are the best rows; they are missing from `system_predicted` only because the boxel-gap enumeration is a core-biased lower bound.
- Stored, not computed: `system_seen.is_known` and `system_confirmed.is_known` are resolved by `sql/record_seen.sql`, FALSE where `system_predicted` holds the system (it holds only systems with no body data), then TRUE where `model.system_known_probe` does: the scanned systems that could hold a rare arrival star, built by `etl/refresh_current.py`.
  `etl/refresh_current.py` re-derives every stored value from the rebuilt mirror, so a value reflects the last refresh rather than the rules it was first written under.
  Probing the full 200.8M-row name bridge costs 1.8 s per call; the probe costs ~300 ms cold and 3 ms warm and needs no model database.
- **The probe is one-sided: a hit is proof, a miss is not.** It drops systems the dumps rule out and systems below mass code `e`, so it writes `TRUE` on a hit and leaves `NULL` on a miss, never `FALSE`.
  Of 1,655 confirmed systems that are in the dumps it finds 1,250; all 405 misses are neutrons or white dwarfs, which the Forge builds one mass code below the floor, so the other kinds are exact.
- `NULL` (not yet checked) is shown, because hiding a genuine find is the expensive direction to be wrong in.

### One line per kind, galaxy-wide

- Confirmed is galaxy-wide, unlike everything else: finds are few certainties worth diverting for, while predictions are plentiful and only nearby ones matter.
- One row per kind, the nearest confirmed find of that kind, so the numerous kinds cannot push the rare ones off.
  Of 1,363 finds, 816 are neutrons and 398 O-types against 8 black holes; ranked by distance the table would be neutrons.
- Rows sit in rarity order (the order of `KINDS`), so the black hole line is always the top line.
  The footer's *nearest confirmed* takes the minimum across rows and names the kind.
- A kind with nothing confirmed has no line.
- Systems without coordinates sort last within their kind: `system_seen` holds `x/y/z` only from a route plot (`FSDTarget` gives the class alone), and unlocated is not near.

| column | |
| --- | --- |
| `SYSTEM` | the nearest system of this kind |
| `TYPE` | the kind, in the same eight characters as the prediction headings |
| `DIST` | how far, in ly |
| `Σ` | how many of this kind are confirmed and still uncollected, from the same pool the row was picked from, so tally and row agree |

- No prediction columns, so it draws 400 px against the sector table's 794; on a certainty a probability cell could only say "not applicable".
- `theme::confirmed_columns()` is every non-probability column of `theme::columns()` plus `TALLY`, derived so a width or order change reaches both tables.
  `TALLY` sits outside `columns()` because on any other table it would have nothing to count.
- `TargetTable::new()` takes the column list as a parameter.

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

**Confirm** fires for every rare class the Confirmed table can show, `kinds::is_rare_class()`, so adding a class to `KINDS` adds it here.
White is the only colour on the HUD that means nothing else.

**Appear** is Confirmed only (`flash_new` on `TargetTable::new()`).

- Confirmed rows are galaxy-wide and one per kind, so a name changes only for a nearer find or a new kind, which is rare enough to flash.
- The other tables turn over whenever the ship moves, and flashing that flashes the fact that you are flying.
- Membership decides it, never values: every distance changes on every jump.
- The first fill flashes nothing.

**Copied** is for handovers you did not press a key for, typically alt-tabbed in the galaxy map when a plot answers a row and its successor is copied.

- `copy_selected`, `advance_clipboard`, `copy_next_hop` and `advance_follow` all go through `App::took_clipboard()`, the one place `copied` is set.
- It is queued, not painted at the request: `advance_clipboard()` runs before the repaint, so flashing there would light the row's old position.
  `took_clipboard()` records the name and `place_cursor()` fires `flash_copied()` as its last step, the one point where clipboard and screen are both settled.
- The name is offered to all three tables and only the row holding it flashes, matched on the displayed system or on `copy_text` (an adjacent-sector row copies a name its `SYSTEM` cell does not show).
  A name no table holds flashes nothing.

### Sounds

Both are synthesised in memory by `src/win/notify.rs` on first use and played with `PlaySoundW` and `SND_MEMORY | SND_ASYNC | SND_NODEFAULT`.

- Synthesised, not a shipped `.wav`: a few lines of arithmetic are diffable, and no file can go on playing an old tone.
- Asynchronous, because a synchronous tone would freeze the thread drawing the thing it announces.
- Any failure degrades to silence; `SND_NODEFAULT` stops Windows substituting its beep.
- `--no-sound` silences both and keeps the flashes.

| sound | notes | length | level |
| --- | --- | ---: | ---: |
| chime (a find) | perfect fifth, A5 over E6, soft attack, exponential decay | 0.26 s | 22% |
| tick (a copy) | the chime's root note alone | 0.09 s | 10% |

- The chime plays over the game, and an alert that talks over the ship gets turned off.
- The tick is the most frequent sound (every cursor move copies), so it is the same voice at a third the length and about half the amplitude, and cannot be mistaken for a find.
- The tick plays from `took_clipboard()` immediately, not queued like the flash: it only says the clipboard changed, and waiting would put it ~2 s of SQL after the key.

**The chime is narrower than the flash**, because a sound interrupts and has to earn it; all three tiers meet in `App::chime_worthy()`.

- **Kinds:** only kinds with the `chime` flag, `BH, WR, HERBIG, O-TYPE` (`kinds::is_chime_class()`).
  NEUTRON and WHT DWRF are 1,229 of 1,778 chime-triggering classes on record, neutrons alone 66%, and a neutron is a routing choice.
- **Reveals only:** `Database::record_seen()` returns the names of systems it had never seen, and only those count; re-plotting a route past a known black hole is not news.
- **Neutrons we predicted:** `chime_predicted` (`kinds::is_chime_if_predicted()`) sounds for a neutron only in a boxel prediction of ours (`system_predicted.is_catalog = FALSE`, "in NO dump"): the model being right about a place nobody had looked.
  No `is_known` probe is needed, since the plot-only half is by construction the half in `system_known`; the flag costs 3 ms.
  The lookup is an `Ask::PredictedBoxel` riding the reveal request, added only when a find's class is a `chime_predicted` one.

## Where colour is used

Two things carry colour and nothing else does, so neither tint loses its meaning by being everywhere:

| | means |
| --- | --- |
| `SYSTEM` | the row kind: bright green = confirmed, violet = POI, blue-grey = plot-only backfill, rose = unfound catalogue star, dimmed = class already revealed |
| the numbers | the probability ramp, or the count ramp on sums |

Nearest's `NEXT` colour follows the same row-kind language (carrier amber, neutron pale blue, route keycap grey).

### Headers take Elite's own palette

Table titles and column headings use the colours of Elite's panel tab bar, sampled from the game at full resolution, in both the HUD and the app window:

| | sampled from | value (`theme.rs`) |
| --- | --- | --- |
| heading text | the body of the tab letters, below the bloom | `HEADER_TEXT` `#ff8707` |
| heading band | median inside three tab cells | `HEADER_BG` `#612f18` |
| rule under the band | the line beneath the tabs | `HEADER_LINE` `#dc6707` |
| app table rows | the panel body | `TABLE_ROW` `#0e0000` |

- In the HUD the band is semi-transparent: `HEADER_ALPHA` (0.55) of `--opacity`, while text stays at `--opacity`.
- That takes per-pixel alpha, so the HUD draws into a 32-bit DIB and presents it with `UpdateLayeredWindow`.
  After drawing, one pass sets each pixel's alpha: the `KEY` background 0, the exact `HEADER_BG` colour the band alpha, everything else `--opacity`.
  Alpha-0 pixels stay click-through, as the colour key made them.
- The app window's header is drawn whole in custom draw, because the dark theme paints its own header background under any text colour.

## Data access

### The overlay never opens the model

It reads a mirror compiled into the binary, so `etl/` can re-merge the model while the HUD is flying; DuckDB allows one writer per file and read-only readers still block writes.

- `etl/refresh_current.py` copies the needed model tables into the `model` schema of `elite_mapping_current.duckdb`.
- `overlay/bundle.py` packs eleven of them, pruned to `MODEL_COLUMNS`, into `overlay/bundle/`, and `cargo build` embeds the pack.
- On start `bundle::extract()` unpacks it once to `%LOCALAPPDATA%\ed-overlay\model-<id>.duckdb`; the attach costs ~17 ms.
- The overlay touches `system_known` (200.8M rows) and `system_body` (577.6M) nowhere in `sql/`, so the mirror is 13.3M rows against the model's 570M, 273 MB unpacked (145 MB packed) against 60 GiB.

| in the mirror | rows |
|---|---:|
| `system_neutron` | 3,484,617 |
| `system_predicted` | 2,502,929 |
| `system_known_probe` | 7,004,030 |
| `carrier` / `carrier_position` | 90,364 / 90,297 |
| `system_poi` / `poi` | 67,544 / 260 |
| `station_service` | 4,279 |
| `sector` / `region` | 12,110 / 42 |
| `system_unfound` | 236 |

- **The `model` schema is a cache; `main` is not.** Each mirrored table is dropped and rebuilt on every refresh, so anything written there vanishes; a new app-state table belongs in `main`.
  The mirrored list is `MODEL_TABLES`, `DERIVED_TABLES` and `PROBE_TABLE` in `common/current.py`; what the binary carries is `MODEL_COLUMNS` in `bundle.py`.
- **It goes stale silently.** After any `etl/` load touching a mirrored table, re-run `python etl/refresh_current.py`, `python overlay/bundle.py` and `cargo build --release`.

### Three model tables exist for the overlay

Each resolves a tiny row set (2,524 reliable carriers, 260 POIs, 3 neutron rows) that would otherwise be found by scanning a table of hundreds of millions with nothing to probe on:

| read | through the big table, warm | cold | materialised |
|---|---:|---:|---:|
| `carrier_targets` | 1,440 ms | 5,224 ms | 8 ms |
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

- Writes go only to the app-state file: `%LOCALAPPDATA%\ed-overlay\state.duckdb`, or the file `--state` names (`overlay.cmd` passes `elite_mapping_current.duckdb`).
- Without `--state`, the first run creates that file from `schema/*.sql` and fills it from the commander snapshot in the bundle (`database::create_state()`).
- The bundled model is attached `READ_ONLY`, so an accidental write raises instead of landing in a file the next build replaces (`ETL.md` §0).
- On arrival the app writes `system_visited`, and `poi_visited` if the system holds a POI; both are idempotent, so a replayed journal event cannot double-count.
- The app never resolves `system_id` by name: `system_visited`, `poi_visited` and `system_wrong` get `NULL`, and `system_seen` keeps only the `SystemAddress` a hop or `FSDTarget` gives.
  Probing the name bridge takes seconds; the app-state loaders backfill through `common.current.resolve_id64()`.

### One connection, released when idle

- `Database::connection()` builds one in-memory DuckDB connection with the app-state file attached read-write as `cur` and the bundled model `READ_ONLY` as `mdl`.
- DuckDB lets one process hold a file, so an overlay holding the app-state file forever would lock out every loader and every read of your own flight log.
- `Database::release_if_idle()` closes the connection after `--model-idle` seconds without a query and it is rebuilt in ~17 ms on the next request; the worker checks once a second while its queue is empty.
  The flag governs the app-state file, not the model; the name is stale, the behaviour is not.
- A read-write connection cannot make a read raise on write, so `database::WRITES` names the writing methods and `DbWorker` refuses one in a request not declared a write, naming the method.

### All selection is SQL

- Which rows exist, their order and every word on them (`Mass H`, a POI's class, the `Σ` labels, an adjacent-sector row's best system) come from the query.
- `Database::top_targets()` returns typed `Row`s; `table::cell_text()` formats (two decimals, `-` below the floor, thousands separators, the `~`) and `table::cell_colour()` colours from raw columns carried alongside (`mass_code`, `star_class`, `row_grp`).
- The app displays and tracks; it does not rank, filter or sum.
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
- Which datasets a view needs is a UI decision in `App::read_asks()`; carriers and neutrons are re-read only when the ship has moved or nothing is cached.
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
- The tabs run Map, Regions, Trade, Engineers, Guardian, Thargoid, Carrier, Settings, Log, and the window opens on Map, the first.
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

### The Regions tab

One row per galactic region, summing each kind's predicted probability over the region's predictions: the number of that object still expected there.

| column | what it counts |
|---|---|
| Predicted systems | predictions in the region, the pool the expected counts are summed over |
| Visited systems | systems on record in the dumps, anyone's visit, from the mirror's `region_known` |
| one per kind | the expected number of that object, rounded to whole objects |

- It counts the same pool as the HUD's `Σ` rows: a system already visited or revealed by the galaxy map is no longer a prediction, so it leaves the sum.
- `sql/region_expected.sql` reads it in one pass over `system_predicted`, joined to its region through the sector name; 42 regions take about 80 ms on the `db` thread.
- Visited systems comes from `region_known`, a 42-row count `etl/refresh_current.py` derives from `system_known`, because the overlay never reads the 200M-row table.
- It is read at startup and again each time the tab is opened, so it reflects every arrival since.
- The table is a ListView: clicking a heading sorts by that column, numbers first descending and the region name ascending.
- A `Galaxy` total row stays at the bottom whatever the sort.
- The fill turns redraw off: refilling a visible list with redraw on repaints after every cell and costs about 300 ms of the UI thread.
- It is styled as Elite's HUD: orange text on near-black rows striped with dark amber, the header in Elite's tab-bar palette, and the `Galaxy` row brighter.
  The colours are `TABLE_*` and `HEADER_*` in `theme.rs`, drawn through ListView and header custom draw.
- A click highlights a row in solid orange; the list's own selection is refused, because the dark theme paints selection in its blue over any custom colour.
- The row under the mouse is drawn white on a lighter brown (`TABLE_HOVER_TEXT` on `TABLE_HOVER`) by every table's custom draw (`colour_row`), which clears the item's hot state so the dark theme's own near-black hover is never painted.

### The Map tab

The galactic regions drawn as a map, each shaded by how many of one kind of object it is still expected to hold, with the region's best sectors listed underneath.

- The dropdown picks the kind; the map, its legend and the sector list all follow it.
- **Include plot only**, off at every start, adds the plot-only predictions to the map, its legend and the sector list.
  Off, they count boxel predictions only, the pool the HUD's adjacent sectors and `REGION` line count, so the two agree; the legend names which pool is shown.
  The Regions tab always counts both.
- Region shapes come from `region_map`, klightspeed's published region grid (MIT): 2,048 x 2,048 cells of about 49 ly over the galactic plane, the lookup EDDiscovery and EDMC use.
  Frontier publishes no region boundaries, and EDAstro's region maps are pictures without stated coordinates, so neither lines up with a click.
- The texture under the colour is `galaxy_density`: known systems per cell of the same grid at half resolution, log-scaled.
  It shows where commanders have reported systems, which is the galaxy's explored shape, not its real star density.
- A region's shade is the gradient at `sqrt(value / max)`: the core regions run to tens of thousands of expected black holes and the rim to single digits, and a linear scale would leave the rim one colour.
  The legend is marked at its left, middle and right in whole numbers of the kind: 0, a quarter of the maximum (the middle of a square-root scale) and the maximum.
  The gradient runs in ten steps from dark red (fewest) through orange, amber and yellow-green to green (most) (`MAP_GRADIENT` in `theme.rs`).
- A region expecting none of the kind (under 0.5, which reads as 0) is left uncoloured, showing the galaxy beneath, and colour fades in over the bottom `MAP_FADE` (15%) of the scale, so the gradient starts from transparent; the legend fades the same way.
- Labels are placed highest-value first and a label that would overlap one already placed is skipped, so the crowded core keeps the names that matter; hovering names any region in the line above the map.
- The grid is read once at startup; the per-pixel region, density and border lookups are cached per window size, so hovering and changing the kind only re-shade.
- The map is left-aligned and the sector list sits in a panel on its right, under a caption naming the region and the kind.
- Clicking a region asks `sql/sector_expected.sql` for its top sectors by expected count of the chosen kind, over the same pool as the Regions tab.
- How many is however many rows fit beside the map (at least 5), measured from the list's own row height on every resize; a change in that number re-asks for the selected region.
- The list shows only the sector and the chosen kind, to one decimal, and its heading follows the dropdown; `win/expected_table.rs` serves it and the Regions table in two modes.
- Its last row is the region's total for the kind, the same figure the map is shaded by, not the sum of the sectors shown.
- A sector whose value rounds to 0.0 is left out; if none remains the list is a single `<none>` row with no total.
- Clicking a sector copies its most likely target to the clipboard: the unvisited, unrevealed, not-marked-wrong system with the highest probability of the chosen kind (`sql/sector_best.sql`), boxel-predicted only unless **Include plot only** is ticked.
  The log names the system and its chance; a sector with nothing left says so.
  The clicked row flashes white text on bright orange (`FLASH_TEXT` on `TABLE_FLASH`) for 350 ms on a one-shot timer, then settles into the selected colour; the total and `<none>` rows do nothing.
- **Carrier Route** makes the last system a sector click copied the fleet carrier's destination and fills the Carrier tab; pressed before any sector click, it says so in the log.
  It is owner-drawn in the header palette (`HEADER_BG` fill, `HEADER_TEXT` label, `HEADER_LINE` border) and flashes white text on bright orange (`FLASH_TEXT` on `TABLE_FLASH`) while pressed and for 350 ms after a click, on a one-shot timer, so a click can be seen.
- Every page window sits above the tab control in z-order, and the dropdown above the map: a sibling below a `WS_CLIPSIBLINGS` window it overlaps is painted over, and the map was invisible until the tab control was moved to the bottom.

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

Where the fleet carrier is, where it is going, the next system to send it to, and the Tritium to fill it with: rows in the Trade tab's table, each click copying its system.

| row | from |
|---|---|
| Carrier | the latest `CarrierLocation`, with the carrier's name and callsign, its jump state, its Tritium from the latest `CarrierStats` and when that was read; the distance is from the ship |
| Destination | the system set by **Carrier Route** on the Map tab; the distance is from the carrier |
| Next jump | the known system no more than 500 ly from the carrier (`CARRIER_RANGE_LY`) that ends closest to the destination (`sql/carrier_next.sql`), with that jump's Tritium and the distance left |
| Tritium, cheapest | the cheapest station selling it within 250 ly of the ship, asked of Spansh |
| Tritium, 1,000 t or more | the nearest station holding at least 1,000 t (`BULK_SUPPLY`), at any distance, with its price per ton, asked of Spansh |

- `journal::read_carrier` reads the newest journals backwards, at most 60 files, for the carrier's `CarrierLocation`s, the latest `CarrierStats`, `CarrierJumpRequest` and `CarrierJumpCancelled`.
- The jump state, `journal::carrier_phase`, the same text on this tab and on the HUD's carrier line:
  - **jumping to X in m:ss** while the latest request has no later arrival and no later cancel, counting down to its `DepartureTime`; a `CarrierLocation` at the old system written by a login during the countdown is not an arrival;
  - **cooling down, ready in about m:ss** for 5 minutes after the arrival (`CARRIER_COOLDOWN_S`), an estimate, because the game logs no cooldown;
  - **ready to jump** otherwise.
  - A departure more than a minute past with no arrival logged, the commander offline, is taken as an arrival a minute after departure.
- The journal gives the carrier's system but not its coordinates.
  They come from the commander's own `FSDJump`, `CarrierJump` or `Location` there, newest first, and otherwise from the overlay's data (`sql/system_pos.sql`): `system_seen`, a plot-only system of `system_predicted` by id64 or name, or a station's system.
  A carrier sent to a system the Carrier tab suggested is always found, since the suggestions come from the same tables.
- The landing candidates are the systems the overlay holds exact coordinates for: the plot-only systems of `system_predicted`, every listed non-carrier station's system, and `system_seen`, plus the destination itself, which ends the route once it is within range.
  A boxel-predicted destination has only its boxel's centre, so the last jump to it is approximate.
- Tritium per jump is `5 + distance / 8 x (1 + (used space + Tritium in the tank) / 25,000)`, rounded (`journal::carrier_tritium`), where used space is `TotalCapacity - FreeSpace` from `CarrierStats`.
  It reproduces the three carrier jumps in the commander's journals to the ton: 30, 28 and 99 t.
- "At least N more jumps" is the remaining distance over 500 ly, a floor: real jumps fall short of 500 ly.
- The destination is kept in app-state `carrier_destination`, one row per callsign, and read back at startup, newest first.
- Re-read when the tab is opened, when **Carrier Route** is pressed and when the journal writes a carrier event; the countdown is re-rendered every second it changes.
- Tritium comes from Spansh's station search (`src/market.rs`), on its own thread so a slow answer never touches the HUD or the database; a burst of jumps collapses to one request for the latest position, which asks both searches in turn.
  - The bulk row is for filling a carrier or a long trip: the cheapest row is often a settlement holding 10 t, and a price is no use without the stock behind it.
  - Only markets updated in the last 30 days count: unfiltered, the cheapest Tritium near Sol is a 2020 price.
  - Stations only, by station type: fleet carriers are left out.
    Carriers sell Tritium at a few thousand credits and stations at tens of thousands, often from a settlement holding 10 t, so the price shown is a station price.
  - Ties on price go to the nearest seller, and ties on distance in the bulk search to the cheaper.
  - Inara is not used: its `robots.txt` disallows the `formbrief=` query its commodity search runs on, and it offers no market API.
- `src/market.rs` is the only part of the overlay that touches the network.

### The Settings tab

The navigation keys, one row per action with its current key; click a row and press the new key.

- The capture runs in the same low-level keyboard hook as the bindings, so it sees the chord exactly as the HUD will: modifiers held with one other key.
  Escape alone cancels; leaving the tab cancels too, so an armed capture cannot take a later keypress meant for the game.
- While capturing, no action fires, so the key being assigned does not also act.
- A chord another action already has swaps with it, and the log says so: two actions never share a key.
- Changes are saved to `keybindings.json` in `%LOCALAPPDATA%\ed-overlay` and loaded at startup; an entry that does not parse keeps its default and is logged, never dropped silently.

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
| `kinds.rs` | what a predictable object is: stored key, column, on-screen abbreviation, arrival classes, and four flags saying what it is for | SQL, the window, colour, widths |
| `theme.rs` | every colour, font, column width and column order | data, drawing |
| `names.rs` | parsing `Blaa Hypai BA-A g5` → sector, boxel index | IO, database |
| `journal.rs` | finding, tailing and rolling over `Journal.*.log`; reading `NavRoute.json`, `Status.json` and the `Loadout` | what an event means |
| `database.rs` + `sql/*.sql` | all SQL, both attached databases | the window, the journal |
| `dbworker.rs` | the `db` thread and the `Ask`/`Answer` vocabulary | what a view needs |
| `table.rs` | a table's rows, cursor and flashes, and each cell's text and colour | SQL, ranking, layout |
| `win/overlay.rs` | the window: per-pixel-alpha layered/topmost/no-activate, drag, placement, layout and GDI drawing | what is inside it |
| `win/main_window.rs` | the application window, its tabs and the Log tab's tail of the run log | the HUD, the database |
| `win/expected_table.rs` | the sortable expected-objects table, used by the Regions tab and the Map tab's sector list | where its rows come from |
| `win/map.rs` | the Map tab's region map: shading, labels, hover and click | the database, the dropdown |
| `win/trade.rs` | the Trade tab's table and click-to-copy | where its rows come from |
| `win/settings.rs` | the Settings tab: key bindings and click-to-rebind, and the prediction outcomes of visited systems | how a key is matched, where outcomes are recorded |
| `market.rs` | the Tritium price thread: the overlay's only network access | the window |
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
- `database::fragments()` generates every SQL list and `CASE` ladder from `KINDS` (`{{CLASS_CASE}}`, `{{ABBR_CASE}}`, `{{RANK_CASE}}`, `{{RANK_BY}}`, `{{RARE_MAX}}`, `{{ALL_CLASSES}}`, the `p_*` lists) and fills the `.sql` files once at startup.
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
- Every key copies a system name, what the galaxy map's search accepts; an adjacent-sector row copies the best system inside its sector and the footer names it.
- Table paging skips empty tables and remembers each table's position by row target, not index, since rows reorder; an answered target is gone and paging back lands on the top.
- Row movement wraps.
- The `TOTAL` row is not selectable.
- The cursor is clamped, not reset, on refresh.
- `BINDINGS` in `src/win/hotkeys.rs` holds the default bindings; the Settings tab rebinds them and `%LOCALAPPDATA%\ed-overlay\keybindings.json` keeps the changes.

### The focus gate

- Keys are captured by a global low-level hook (`WH_KEYBOARD_LL`), because the overlay never holds focus; it always passes the key on so the game still sees it.
- `App::tick()` drains a press only when `focus::is_foreground()` holds: a window titled `Elite - Dangerous`, one of the overlay's own, or no foreground window.
  Ungated, every arrow press anywhere on the machine would move the cursor and overwrite the clipboard.
- A binding fires only when the keys held are exactly its chord, so `SHIFT+Down` in a text field is not a cursor move.
- The hook only records presses into slots behind one mutex; `hotkeys::take()` and its siblings read and clear in one step.
  Navigation shares a last-press-wins slot; `SHIFT+BACKSPACE`, `SHIFT+N` and `SHIFT+A` each have their own, or an arrow in the same 120 ms tick would swallow the press that records or toggles something.
  A lost toggle leaves the key meaning the opposite on the next press, and a key-repeat burst collapses to one toggle.
- The clipboard is written through Win32 (`src/win/clipboard.rs`) as `CF_UNICODETEXT` handed to the system, so a copy outlives the overlay.
- `--no-hotkeys` disables the hook.
- The overlay hides unless Elite or the overlay has the foreground; it never takes focus (`WS_EX_NOACTIVATE`, `MA_NOACTIVATE`), so clicking or dragging it leaves Elite in front.
  `--always-visible` disables hiding.

### `SHIFT+BACKSPACE`: no such system

The only key that records a finding: the name would not plot, or you arrived and nothing was there.

- **It filters, it does not delete**: a row goes into `system_wrong` in the app-state database, and every read offering a destination filters against it.
  The app may never write the model, whose builders would undo a deletion on the next rebuild, and this is the only negative evidence the project collects.
- Pipeline re-runs cannot reproduce these rows, so they belong with the flight log: back them up.
- Only guesses can be marked: predictions, plot-only backfill, an adjacent-sector row's best system and unfound catalogue stars.
  A confirmed find, POI, carrier or neutron is a place the game says exists, so failing to plot is a spelling or stale-dump problem; the footer says so.
- The focus gate matters most here: `SHIFT+BACKSPACE` is an ordinary chord in a text field.

### `SHIFT+A`: same system, renamed

The galaxy map sometimes resolves a predicted name to a system the game spells differently.
A rename that keeps the boxel and index settles itself through the derived address (see *Not visited, and arrival class not yet revealed*); `SHIFT+A` is for the rest.

- With a route plotted, `SHIFT+A` (or whatever key Settings binds) on a prediction, plot-only backfill, adjacent-sector row or unfound catalogue star records in app-state `system_alias` that the row's system is the route's destination (`NavRoute.json`'s last hop, with id64, position and class).
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

### Width and the clock

- `Overlay::layout()` sizes the window from the tables alone (plus the title bar with `--chrome`); the `--chrome` footer is clipped at the edge, so a 400-character line renders at 934 px instead of 2,820.
  A clipped hint is recoverable from this file; a window covering the canopy is not.
- The clock (`hh:mm` local) sits at the right end of the top pane's carrier line, and that line is kept for it when there is no carrier.
  It stays put when Nearest has no rows, which is why it is not a cell inside that table.
- `App::update_clock()` redraws only when the minute turns.

## The throttle LEDs

The VKB STECS has three RGB LEDs.
`src/win/vkb.rs` (`Throttle`) is the wire, HID feature report `0x59`, and a no-op on every call with no VKB plugged in; `src/lights.rs` is the policy and the only module picking an LED colour.
`--no-lights` turns them off.

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

## Not wired yet

- `observations.jsonl` (the calibration-loop input), `outcomes.json` and `carrier_gone.json` are unmigrated, not reproducible, and read by nothing; see `CLEANUP.md`.
