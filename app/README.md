# ed_overlay — sector-ranked rare-object HUD

The overlay. Pinned to the **top-left corner** of the screen.

```
python -m app.main                        # follow the journal
python -m app.main --sector "Eol Prou"    # force a sector, ignore the journal
python -m app.main --font 13 --opacity 1.0 --x 40 --y 200
```

## What it shows

The **top 10 predictions in the sector you are currently in**. Table only — no title
bar, no status line, no footer. Drag it from anywhere on the table.

| Column | Meaning |
| --- | --- |
| `SYSTEM` | Predicted system name. Dimmed if the galaxy map has already revealed its arrival class, because that one is no longer a gamble. |
| `DIST` | Light-years from the commander, on every table. A leading **`~`** means the coordinates are a **boxel centroid**, not a position — good to about ±640 ly at mass code `h`. POIs and catalogued systems come from the dumps with exact coordinates and get a plain number. A dash means unlocated, which is not the same as near. |
| `TYPE` | What kind of target the row is. Today every row is a boxel-gap prediction, so the kind is its mass code, rendered `Mass H`. Highlighted at `h`. Not called `MC` because POIs, neutrons and carriers will land in this same column and are not mass codes. |
| `BLK HOLE` `WOLF-RAY` | Black hole, Wolf-Rayet. The two that decide the ordering. |
| `HERBIG` | Herbig Ae/Be — the only prediction whose rate *rises* with galactocentric radius, so the best rim-ward target. |
| `O-TYPE` | **O-type star** — the hottest and most massive main-sequence class (~30,000–50,000 K, blue). Concentrated in mass code `g`; the richest sectors sit ~55 kly from Sol on the far side of the core, so check distance before routing. |
| `NEUTRON` `WHT DWRF` | Neutron star, white dwarf. Common enough to be near their base rate almost everywhere. |

> **Two columns have been removed, for the same reason: nothing the overlay sees could
> ever settle them.**
>
> **`He GIANT`**, and with it `p_hr`. A helium-rich gas giant is a *planet*, and the only
> thing this overlay ever learns about an unvisited system is its **arrival star**.
>
> **`SUPERGNT`**, and with it `p_supergiant` — which stings, because at 2.4× observed
> over expected it was the best-validated prediction in the project. A supergiant *is* an
> arrival star, so it looked confirmable. It is not: the journal's `StarClass` field —
> what `FSDTarget`, `StartJump` and `NavRoute.json` write, and the only vocabulary this
> tool ever reads — is **short codes**. Across 201 journals the entire set is `M K N F G
> TTS A L T Y H B AeBe WO DC O DA WNC D WN WC SupermassiveBlackHole DQ DAZ DAB CN`. A
> B supergiant plots as plain `B`, indistinguishable from a B main-sequence star. The
> long `B_BlueWhiteSuperGiant` spellings the code matched on belong to the **`Scan`**
> event, which needs the ship to be in the system. The result was a column that had
> confirmed **0** systems in the app's entire history while `HERBIG` had confirmed 140.
>
> Both enrichments are real and stay recorded in `DEAD_ENDS.md`; they are simply not
> actionable from here. Every column left is a *star*, and every one of them is
> confirmable by a route plot.

Every probability is a **two-decimal fraction** (`0.38`), right-aligned, each shown
separately and **colour-coded on a 10-step red→orange→yellow→green ramp**. The scale is
linear over `0.05`–`0.60`, fixed rather than stretched per sector, so the same number is
always the same colour. It was measured, not guessed: over every displayed column,
the 3,669,169 values at or above `0.05` have median `0.163`, p99 `0.576`, max `0.576`. Most cells therefore
land red or orange — because most predictions really are unlikely — and green stays rare
enough to mean something.

A `-` (below `0.01`, `theme.MIN_SHOWN_PROBABILITY`) is uniformly dim in every column.
That bound is **deliberately not** the gradient's `0.05`: one answers "is this worth a
line at all", the other "what does a colour mean", and values between the two clamp to
the bottom step. The eye skips straight to the
numbers. The final row of the sector table is **`<sector> TOTAL`**: the same
probabilities *summed* across every not-catalogued, unvisited system in the sector,
which is the expected number of undiscovered objects of each type still out there. It
is not a destination — the cursor skips it, because you cannot fly to a sum. It IS coloured, but on the **count** ramp rather than the probability one:
same ten colours, log-scaled over 0.1 to 100 expected objects, because a count is not a
probability and 0.6 expected black holes must not paint the same green as a 60% chance of
one. Fixed, not stretched to the screen, so a colour means a quantity.

### They are never combined, and that is deliberate

An earlier version showed a single `RARE%` built as `1 − (1−p_bh)(1−p_wr)`. That was
wrong, and the model says so itself — the `p_wr` column comment reads:

> Competes with `p_bh` for the same primary star — **one star cannot be both, so never
> add or multiply them.**

Independence is the wrong assumption and addition is the wrong one too. So there is no
headline number; the ranking uses `max(BH, WR)`, which needs no assumption at all.

Only BH and WR sort the list. The other six are shown but excluded from ranking:
neutrons and white dwarfs sit near their base rate almost everywhere, so including them
would rank by *how ordinary* a system is.

### Read the numbers with this caveat

Every `p` is fitted per **(mass code, plane_r band)**, and a sector sits inside one
band. A sector therefore offers only about **four distinct rows** — one per mass code
present. Two systems of the same mass code in the same sector are, to this model,
*identical*.

So the ranking is really *"highest mass code first"*, tie-broken on expected body
count (computed but no longer displayed) and then alphabetically. **Within a mass code the ordering is not meaningful**, which
is the first thing to fix before binding F1–F10 to it. With the chrome hidden this
warning is printed to stdout on every refresh rather than silently dropped.

### What is in the pool

Two filters decide what can appear at all.

**Boxel-predicted only.** `system_predicted` holds two very different things, and the
`is_catalog` column comment says *"always filter or group by this"*:

| | rows | what it is |
| --- | ---: | --- |
| `is_catalog = TRUE` | 2,253,534 | **Excluded.** Catalogued: in the dumps with exact coordinates, merely not detail-scanned. |
| `is_catalog = FALSE` | 220,489 | **Shown.** Boxel-predicted: in no dump at all, its existence inferred from a gap in the Stellar Forge's index. |

That is a 10× reduction, and it has consequences worth knowing before you fly:

- **Only 5,409 of 12,100 sectors** hold any predicted system, so an empty table is
  still the common case. The overlay says which kind of empty it is.
- **Mass code `e` dominates the pool** — e 156,845, f 16,012, g 15,565, h 32,067. That
  matters because `e` is the weakest gate in R1: it is where nearly every row failing
  the bar below comes from, and an `e` row's best rare can be an order of magnitude
  below an `h` row's.
- **Coordinates are the boxel centroid**, up to 1280 ly across — you can arrive at the
  exact point and find nothing there.
- The layer is thin and core-biased; it is a lower bound, not a census.

**At least 1% on one rare** (`database.MIN_RARE`). A system must offer `≥ 0.01` on at
least one of `BH`, `WR`, `HERBIG`, `O-TYPE` — per column, never summed.
`NEUTRON` and `WHT DWRF` are excluded from the test despite being displayed: both sit
near their base rate everywhere, so including them would pass everything.

> **This bar does now bite, and it did not always.** It removes **7,870 of 220,489**
> rows, leaving 212,619 across 5,363 sectors; the weakest survivor offers **0.0149** on
> its best rare. The removals are **7,736 mass-code `e` and 134 `f`** — the bar is in
> practice a filter on `e`, which is why the pool's shift toward `e` turned a dormant
> guard into a working one. Raising it further would cut into `e` first and hardly touch
> `f`/`g`/`h`.

Already-**visited** systems are excluded, and so are systems whose **arrival class the
game has already told us** — a route plot rewrites `NavRoute.json` with the class of
every hop, and an `FSDTarget` gives one. A boxel prediction asks exactly one question,
"what is the arrival star", so a revealed class settles it: rare, and it moves to
Confirmed; ordinary, and there is nothing left to gamble on.

> That exclusion used to apply to the **ten rows only**, not to the sums under them or
> to the Adjacent sectors table, on the reasoning that a non-rare arrival star still
> leaves the rest of the system worth a look. It made the richest event the app ever
> sees invisible: plot a route through a neighbouring sector, learn the class of dozens
> of its predictions, and its Adjacent row did not move. Graea Hypa was the live case —
> 160 unvisited boxel predictions of which **106 were already classed**, still summed as
> 160 and still advertising **45.5** expected black holes against a true **3.5**. 172
> sectors carried some version of that error. All four pools — the sector rows, the
> `SECTOR`/`REGION` totals, and the Adjacent sums — now apply the same test.

## Chrome

Hidden by default. `--chrome` brings back the title bar, the live status line
(current system, row counts, clock) and the footer.

## Ranked by probability, not distance

Sorting candidates by distance means grinding outward through whatever happens to be
nearby. Everything in a sector is already close, so the only question left is which one
is most likely to hold something — and that is what the ordering answers.

## Adjacent sectors

The ten nearest **other** sectors, with the expected objects left in each. Where the
`<sector> TOTAL` row says what is left *here*, this says what is left next door — so
"is this sector worth staying in" can be decided against something instead of in the
abstract. Every number is an expected **count** summed over the whole sector, formatted
and coloured exactly like the totals row — the log **count** ramp — because it means the
same kind of thing. That table exists to answer "is anywhere next door better than here",
and with every cell painted one neutral grey the answer took reading ten rows of numbers;
on the ramp it is one glance. The
pool is identical too — boxel-predicted, not catalogued, not visited, not already
classed — or the comparison would be between two different things.

**Distance is to the sector centroid and is approximate**, marked with a leading `~`.
A sector's bounding ball has a median radius of 1,727 ly while neighbouring centroids
sit about 1,280 ly apart, so the balls overlap heavily and the nearest centroid is not
always the nearest system.

Only sectors that **have** something appear: just 5,409 of 12,100 sectors hold any
boxel prediction, and 5,363 hold one clearing the bar, so the ten nearest outright
would often be rows of zeroes. This
table is at its most useful exactly where the sector table is empty, which is common.

### What an Adjacent row copies

The **best system in that sector**, by `database.RANK_BY` — `greatest(p_bh, p_wr)`, the
same expression the Current sector table ranks its ten rows on. There is only one such
expression in the app, deliberately: `ALT+F3` hands back exactly the system `F1` would
offer once you arrived, so the two tables cannot recommend different places.

> An earlier version ranked this on the **summed** per-type probabilities instead, on
> the reasoning that a table of aggregates should hand over the system with the largest
> aggregate. Measured, that cost real ground: across the 2,874 sectors holding a boxel
> prediction the two picks differed in **444**, differed about the **mass code** in all
> 444, and the summed pick was worse on `greatest(p_bh, p_wr)` in **444 of 444** — mean
> **0.46 → 0.40**. Summing lets neutrons and white dwarfs, which are numerous, outweigh
> the one column the whole project is about.

The **sector** columns are still sums, and should be — they answer "is this sector worth
the trip", which is a question about everything in it. Only the choice of *system*
within a sector is a rarity ranking.

### The row caches ten systems, not one

The row *displays* one system; the query returns **ten** (`database.SECTOR_CANDIDATES`),
carried on the row as `candidates` in ranking order, `candidates[1]` being the pick. One
is enough to display and not enough to *react*.

Plot a route to that pick and the plot answers it — `NavRoute.json` carries the arrival
class — so the pick changes, and what belongs on the clipboard is the next candidate.
`place_cursor()` step 3 always did that correctly, but at the *end* of the repaint, so
the clipboard waited behind ~2.0 s of SQL that decides what is on screen and not what is
on the clipboard. `App.advance_clipboard()` now answers it from memory, before anything
touches the database: `candidates[2]` **is** what the query returns as the pick once
element 1 is answered, and for every other table the successor is the first surviving row
below the cursor in `self.rows`. Both skip *every* answered name, since one plot often
settles several.

Verified against the database rather than argued: settle the pick, re-query, and the new
pick is the cached next one; settle two, and it is the cached third. The extra nine cost
~3 ms — the window function already ranked the whole partition to find the first.

## Unfound catalogue stars

Under the predictions, up to three rows from `system_unfound`: **real catalogued stars
— HIP, GJ, HR — whose position falls in this sector and which no game system can be
matched to**, by name or by any cross-identification the alias bridge holds. 235 of them
galaxy-wide, across 45 sectors, so these rows are blank almost everywhere.

**They ask a different question from every other row on screen**, which is why they are
their own row kind in their own colour (rose) and never blended into the ranking. The
predictions ask *what is in this system*; these ask *is this system there at all*. The
answer is a visit, not a scan, and it is one of three things:

1. the game **has** it, under a name no catalogue assigns (~15,800 systems carry names
   Frontier invented outright);
2. **nobody has visited it**, so no dump carries it — the interesting one;
3. Frontier **did not ship it**.

They carry **no probabilities**, because nobody computed any: the prediction area holds
the band, the spectral type, and the nearest hand-named system with the length of that
last hop. The galaxy map takes a name and not a coordinate, so that anchor is the only
practical way in — plot to it and look around from there.

**The sector is assigned by nearest centroid**, not parsed from a name; these stars have
no procedural name to parse, which is the whole reason they are here. Reliable for a
`NEAR` row, whose position is good to a few light years. A `MID` row's position is good
only to 100–333 ly, so it gets the same leading `~` on its distance that a boxel centroid
does, and its sector is a hint rather than a fact.

**Paste the name itself first.** If the galaxy map resolves it, the row was stale and the
star was there under its own name after all — which is worth knowing, and is the fastest
way this list corrects itself. If it does not resolve, `SHIFT+BACKSPACE`.

## Nearest — one carrier, one neutron, beside Confirmed

**It shares the top line with the Confirmed table.** Confirmed went narrow when it
became one row per kind, leaving ~394 px of the window's width unused beside it, and
Nearest is two rows. It packs to the **right** of a frame that fills the window, so its
right edge lands on the edge of the sector and adjacent tables below rather than beside
Confirmed — the three of them share one margin.

**Every row answers the same question, so every row has the same shape**: what kind of
thing this is, how many jumps away it is, and **which system to jump to next**.
`theme.NEAREST_COLUMNS` is `TYPE 7 | JUMPS 5 | NEXT 26` — 334 px of the 394 available.

| column | |
| --- | --- |
| `TYPE` | `NEUTRON`, `CARRIER`, or a route's far end: `COLONIA`, `FOUNDER`. Seven characters, which all four happen to be. |
| `JUMPS` | How many jumps away. **The range depends on how you would get there**: a neutron star is the thing you fly to in order to supercharge, so it is counted at the ship's own unboosted range; a carrier or the far end of a route is reached *along* a chain of cones, so it is counted at the boosted range (`main.BOOSTED_LY`, 500 for now). Rounded up, because a part jump is a jump. A route row does not divide at all — it **counts** its remaining hops, which is exact, and counts the jump to the next one. |
| `NEXT` | The system to jump to. For a neutron or carrier that is the destination itself; for a route it is the next hop rather than the far end. One column, one meaning, and it is the cell the cursor copies. |

There is no `SYSTEM` column because `NEXT` *is* it, and no `DIST` because `JUMPS` is the
same fact in the unit you act on.

**The carrier's name appears in `NEXT` once you are in the carrier's system.** At that
point there is nothing left to jump to, so the cell stops being a destination and becomes
the thing you actually need there — which of the ships in orbit is the one you came for.
Everywhere else the name is not shown at all; it is in `detail`, and it was never what
you paste.

Cursor order follows the eye: Confirmed, Nearest, Current sector, Adjacent sectors —
the top line left to right, then the tables under it.

### Following a stored route

**The chains are solved live, from where the ship is, at the range the ship flies.**
Not read from a table: `common/neutron_route.py` plots one in a second or two over half a
million neutron stars, so there is no reason to fly somebody else's answer. A chain
solved from Colonia is worthless once you are 3,000 ly along it, and one solved for a
500 ly boost is unflyable in a ship that makes 472.

`main.route` still matters, but only for its **endpoints**: a name and a position for
each end of whatever is stored, which is the only place the app-state database knows
where "Shinrarta Dezhra" is. Storing a route is how a destination gets registered.

**The nearest carrier is a destination like any other** and gets the same treatment — its
row's `JUMPS` is a solved chain rather than a distance divided by a range, and its `NEXT`
is the first hop toward it. The only difference is that it moves, so the chain follows
whichever carrier is nearest now.

**The row's `NEXT` cell is the hop, not the far end.** That is what the cursor copies and
what you paste, so it has to be the thing you are flying to; where the chain *goes* is
what `TYPE` says.

### When a chain is re-solved

Three reasons, and **no timer**: there is no chain; the ship no longer jumps the range it
was solved at; or the ship has left it, meaning no hop of it is within one boosted jump.
Flying the chain never triggers a re-solve, because the next hop is always within range
by construction — which is what keeps a 1.5–4 s solve off the worker on every jump.

A solve that comes back empty is remembered, and not asked for again until the
destination or the ship changes. Failing is the expensive case: each widening step
re-primes a larger corridor and searches one jump further, so an unreachable place would
otherwise cost ten seconds of worker time on every single jump.

**The hop shown is the nearest one that is both reachable in a single jump and closer to
the end that row is flying to.** Two tests, and neither is optional:

- **Progress.** It must be closer to this row's destination than the ship is now. That is
  what makes the two directions differ once you are on the chain — from hop 20 the
  Founders row offers 21 and the Colonia row 19 — and it is also why standing *on* a hop
  offers the next one rather than the one underfoot: your own hop is exactly as far from
  the end as you are, and "closer" is strict. Nearest alone would hand back the system
  you are sitting in, or the one behind you.
- **Reach.** It must be inside `boosted_ly`, the range the chain was *solved* for, which
  is stored on every row precisely so it can be applied here. Offering a hop the ship
  cannot make in one go is offering a paste that will not plot.

Nearest among those, because the hops are a chain: the nearest one that still makes
progress **is** the next link, and reaching past it would skip a supercharge the rest of
the chain assumes.

Nothing is pinned — not the last thing copied, not a stored position along the chain — so
the row is right after a deviation, a restart, or a jump somebody else plotted. When
nothing is in reach, which is what being off the route entirely looks like, the nearest
progressing hop is offered anyway: the honest answer is "this is where you rejoin", and
its `DIST` cell, larger than the jump range, says plainly that it is not one jump. At
either end of the chain the spent direction offers nothing and its row is simply absent.

**The overlay says so when the ship is short of the range a route assumes.** The hops are
spaced to fill `boosted_ly`, so a ship that jumps less far cannot plot some of them at
all — and without the warning it would discover that one paste at a time, in the galaxy
map, mid-flight.

**Landing the cursor on a route row starts following it**, because in this HUD landing on
a row is what copies it, and the clipboard is the statement of intent. Copying any other
row stops it. While a route is live its row is prefixed `>`, and **arriving anywhere on
that chain copies the next hop** — matched against any hop rather than only the one
handed over, so a skipped jump still advances from where the ship actually is, and an
arrival off the route leaves the clipboard alone rather than guessing. Arriving at the
last hop ends the mode.

Route rows are `keycap` grey, the colour this HUD already uses for something you press
rather than something you read.

One table, two kinds of row, because both answer the same question — *somewhere to go
that is not a gamble* — as against the three tables above them, which are all guesses.

### Carriers


**One row**, galaxy-wide, from `carrier.is_reliable` — parked over a year ago **and**
seen within the last 90 days. Both halves matter: 30,262 carriers have an old
`last_moved` simply because nobody has looked at them since, and arriving to find empty
space is the one outcome that makes a carrier list worthless.

One, because "where is the nearest carrier" has one answer. Three rows were three
answers to a question with one, and the space is now worth more to the tables around it.

The row shows the carrier's **name**, not its callsign: the name is what the docking
request shows and what you recognise from orbit, where the callsign is a string you
would have to look up to use. It stays on the row as `detail`, so anything needing to
identify the ship itself still can. **`+UC` leads the name** when the carrier buys
exploration data — that is the reason to divert to one carrier over another, and the
`NAME` column is 18 characters against names running to `CONSTELLATION EURYALE`, so a
marker at the end would be the first thing truncated away.

### Neutron stars

The nearest system whose **primary star** is a neutron — a **jet cone boost**,
×6.0 of the unboosted range in a **Caspian** and ×4.0 in everything else — a property of
the hull, not of the drive; see *The ship's jump range*. Primary *is* arrival, so you drop out of witchspace next to it and
supercruise nowhere.

**Deliberately not filtered against `system_visited` or `is_known`.** Everything else on
this overlay is about finding what nobody has found; a neutron is about *getting*
somewhere. The boost works exactly as well the second time you use it, and whether or
not somebody else logged the star first. Filtering it the way Confirmed is filtered
would hide the nearest boost *because you had already used it*.

**One row here too**, typed `NEUTRON`, and it is the one row whose `JUMPS` is counted at
the **unboosted** range: a cone is what you fly to in order to get the boost, so you
cannot have had it on the way. Carrier and neutron are also told apart by the `NEXT`
colour, amber against pale blue, which is the row-kind language every other table uses.

**This row is what a plotted route replaces** — see *Neutron jump mode*. The
question changes from "where is the nearest cone" to "the one you are flying to", and
both cannot be the useful one at once. The carrier row above is untouched: a route does
not make the nearest shipyard less interesting. Cached separately for that reason, which
also means plotting costs neither query.

Reads the **mirror's** `system_neutron`: 3.5M rows instead of scanning 200.8M. There is
no model-side table behind it any more — `etl/refresh_current.py` derives it from
`system_known` and `body` at refresh time. The nearest is ranked on **coordinates alone**
and named afterwards — `system_neutron` carries `x/y/z`, but composing the pasteable name
needs `sector`, and joining all 3.5M rows to it before the `ORDER BY` built 3.5M names to
keep three. The
scan is 30 ms; the join was the other 250. Ranking first took the read from 283 ms to
**32 ms**.

## The overlay never opens the model

It reads a **mirror**: `etl/refresh_current.py` copies the ten model tables the overlay
needs into a `model` schema inside `elite_mapping_v2_current.duckdb`, and
`Database._connection()` attaches that one file and nothing else.

The point is not speed, though the attach fell from ~145 ms to ~17 ms. It is that the
overlay and `etl/` no longer contend for the same file: **the model can be re-merged
while the HUD is flying.** DuckDB allows one writer per file and read-only readers still
block writes, so a running overlay used to mean no ETL run at all.

The mirror is affordable because the overlay's read surface is small. It touches
`system_known` (200.8M rows) and `system_body` (577.6M) **nowhere** — every mention of
either in `database.py` is a comment. That is exactly what `system_neutron`,
`carrier_position` and `system_poi` were materialised for, so the ten tables come to
13.1M rows against the model's 570M, and 700 MB against 60 GiB.

| in the mirror | rows |
|---|---:|
| `system_neutron` | 3,462,397 |
| `system_predicted` | 2,474,023 |
| `system_known_probe` | 6,943,571 |
| `carrier` / `carrier_position` | 89,012 / 88,175 |
| `system_poi` / `poi` | 66,544 / 260 |
| `sector` / `region` | 12,100 / 42 |
| `system_unfound` | 235 |

> **The `model` schema is a cache; `main` is not.** Every table in it is dropped and
> rebuilt whole on each refresh, so the merge-never-drop rule does not reach it — and
> anything written there is gone at the next refresh with nothing to show it had been.
> A new app-state table belongs in `main`. The list of what is mirrored lives in
> `common/current.py` as `MODEL_TABLES` and `PROBE_TABLE`.

**It goes stale.** Nothing detects it. Re-run `python etl/refresh_current.py` after any
`etl/` load that touches a mirrored table, or the overlay serves the previous galaxy.

## What the overlay reads, and why three model tables exist only for it

Every read was measured warm and with DuckDB's buffer pool dropped. Three were slow not
for what they computed but for what they walked:

| read | warm before | cold before | now |
|---|---:|---:|---:|
| `carrier_targets` | 1,440 ms | 5,224 ms | **8 ms** |
| `top_targets` | 272 ms | 2,141 ms | **12 ms** |
| `neutron_targets` | 343 ms | 376 ms | **32 ms** |
| **jump repaint** | **2,695 ms** | **8,289 ms** | **143 ms** |

The pattern was identical in all three: a tiny row set — 2,524 reliable carriers, 260
POIs, 3 neutron rows — resolved through a table of hundreds of millions with nothing to
probe on, so DuckDB scanned the whole thing.

- **`carrier_position`** (88,175 rows) replaces resolving `carrier.system_id` through
  `system_known`'s 200,816,169.
- **`system_poi`** (66,544 rows) replaces the two-branch POI union, whose body half
  scanned `system_body`'s 577,639,044 rows to reach 10,023.
- **`system_neutron`** was already there for exactly this reason. It needed no new table,
  only ranking on coordinates *before* joining `sector` for the name: the scan is 30 ms,
  the join to build 3.5M names and keep three was the other 250.

All three **add no facts** and are snapshots, so they go stale until their builder runs
again; `ETL.md` carries that warning. `poi_in_system()` reads `system_poi` for the same
reason — it carries the pasteable name, so the name is the key, with nothing to resolve
through. 2.2 ms per arrival, and the overlay reads no staging table at all — which is what
later made it possible to drop the model attachment entirely.

## One bad tick costs one frame, never the session

`Overlay.every()` is the only thing that schedules anything, and Tk **drops a callback
that raises** — it hands the traceback to `report_callback_exception`, which prints to
stderr, and never runs that callback again. Re-arming the timer *after* `fn()` therefore
turned any single-tick exception into a permanently frozen HUD, and one that is easy to
misread as a hang: the window stays up, topmost and answering the message loop, the db
thread sits idle in `queue.get`, the global key hook keeps firing, and the table goes on
showing the sector the commander left. The process burns **no CPU at all**, which is the
tell — a live tick never reads as 0.0 s over a sampling interval. The traceback that
would have explained it goes to whatever console launched the overlay, which by then is
usually closed.

So the `after()` call sits in a `finally`, and the exception goes to an `on_error`
callback that `main.py` routes into `note()` — the same on-screen line a failed database
request already uses. A failure must cost ONE frame and be SAID, which is the rule
`dbworker.py` had already stated for the worker thread; the timer just was not holding
it.

## The database runs on its own thread

Tk runs the timer, the keys and every repaint on one thread, so a query is not merely
slow — it is that long with no arrow key read and no window redrawn. With the joins
materialised the split was ~100–145 ms of SQL against ~10 ms of drawing, so the freeze
was almost entirely SQL. DuckDB releases the GIL — a slow query on a worker leaves a
polling loop at its **2.1 ms** idle gap, against **1,460 ms** on the loop's own thread —
so `dbworker.py` moves it off. Worst tick now **0–6 ms** in steady state, 34 ms for the
first paint of a session.

`DbWorker` is a transport and knows nothing about the UI. Its vocabulary is `Database`'s
public method names: `Ask("top_targets", (sector, 10), {"pos": pos})`. Which datasets a
view needs stays in `main.py:_read_asks()`, because that is a UI decision — carriers are
skipped when only a reveal changed things, the sector reads are skipped in hand-named
space. If the worker can't be driven from a plain script with no display, the boundary
has leaked.

Six rules hold it together, each because the alternative fails:

- **One worker, one FIFO.** Writes are never reordered, so `record_seen` still lands
  before the reads that observe it. Two workers would break that silently.
- **Last wins, unstarted requests only, and only under a `key`.** Jump twice quickly and
  the first answer describes the sector you left. Writes never carry a key — a dropped
  write is a lost find. Same decision `Hotkeys.take()` makes for keypresses.
- **`Ref`** substitutes an earlier ask's result inside one request, which is what lets
  `record_seen` and the `promote_confirmed(only=…)` that depends on it share one request.
- **One thread owns the connection,** asserted in `Database._connection()`. DuckDB accepts
  a `DETACH` of a database another cursor is reading *without complaint* — verified — so
  no error means no guard. Every read and write reaches the database through that one
  method, so the single assert covers all of them. Startup work runs on the main thread
  and ownership transfers at `worker.start()`.
- **Failures travel as values.** Vanishing into the thread would leave the HUD frozen on
  stale rows with nothing said.
- **A `Phases` per thread.** A phase recorded on the worker otherwise lands inside
  whatever span Tk had open and the breakdown stops adding up. Worker lines are `[db]`.

The idle release is the worker's own housekeeping rather than a command — closing the
hub is a session-owning act. It no longer hands the *model* back, because the overlay
never holds it: `--model-idle` now only governs how soon `etl/` may write the app-state
file. The flag keeps its old name; the name is the stale part, not the behaviour.

`route.plan()` still runs on the Tk thread: it is CPU, not SQL, and the corridor fetch
that feeds it is now an ask. The widening retry is a second request rather than both
corridors up front, so the common case fetches once.

### The paint is 10 ms; the 91 ms at startup is startup

`paint` as one number read 91 ms, which four grids of at most eleven rows cannot cost.
Phased per grid, the answer is Tk realising the window: three tables are
`hide_when_empty`, so the first `show()` with rows calls `_show_container(True)` and the
`pack()` makes Tk lay out the window and measure fonts. Later paints are pure
`label.config()` — 3.0 ms for the Confirmed grid, against 16.2 ms on its first call.

| refresh | `read` | `paint` | `p_confirmed` | `p_sector` | `p_adjacent` | `p_nearest` | `p_cursor` |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1st of the session | 523 | **32** | 19 | 5 | 3 | 1 | 3 |
| 3rd | 147 | **10** | 2 | 4 | 3 | 1 | 0 |

No database call and no file access is inside `paint`: every `q_*` and both `db_attach` /
`db_detach` are the worker's, and the journal and `NavRoute.json` are read in the tick as
`journal` and `navroute`. The only phase leaving Tk is `p_cursor`, which reaches the
**Win32 clipboard** — phased because `OpenClipboard` can block on another process holding
it. Measured at 0–3 ms.

## Confirming a rare says so twice

A confirmation is the one moment this tool has something to say that the game does not,
so it is announced on two channels at once — and for **every** rare class the Confirmed
table can show, not just black holes and Wolf-Rayets: neutron, white dwarf, Herbig,
O-type and the white dwarfs all trigger it. The trigger set is `database.RARE_CLASSES`, so
adding a class to the table adds it here with no second edit.

**The row flashes.** The system name fades from white into the confirmed green it will
keep — 12 steps at 60 ms, 0.72 s in all. White because it is the only colour on this HUD
that means nothing else, so the eye is pulled by something it has never had to interpret.
It FADES rather than blinks: a blink says "look here now" and keeps saying it, a fade says
"this just happened" and then gets out of the way, which is the honest claim — the row is
still there afterwards and the green is doing the work by then.

Only the SYSTEM cell flashes. Tinting the whole row would wash out the probabilities at
exactly the moment they are worth reading, and the name is what you copy anyway. The
animation runs on Tk's own `after`, not the two-second tick, or it would be four frames a
second — a stutter, not a fade. It survives the repaint that the confirmation itself
triggers, because the flash state lives on the table and the refresh replaces the row
dicts underneath it.

## Three events flash, one animation

The fade ENDS ON THE COLOUR THE CELL WOULD HAVE HAD ANYWAY — `cell_colour()` decides the
endpoint and `theme.blend()` mixes the highlight into it — so the same twelve frames serve
a confirmed find, a catalog-grey backfill row and a gold sector count without any of them
ending on a colour it does not settle at. Only the highlight differs, and none of the
three is a row-kind or gradient colour, so a flash can never be misread as a value taking
on a new meaning.

| highlight | says |
|---|---|
| white (`FLASH_CONFIRM`) | the game has just revealed a rare here |
| pale blue (`FLASH_APPEAR`) | this row was not in the table a moment ago |
| amber (`FLASH_COPIED`) | this row is what is on the clipboard |

**Only Confirmed flashes its own arrivals** (`flash_new=True`). Its rows are galaxy-wide
and one per kind, so a name changes there for exactly one reason: a nearer find of that
kind, or a kind that had none. A plot 15,000 ly away answers a system and the line
changes under you in a table you were not looking at — that is worth a flash, and it is
rare enough to stay one. The other three tables turn over whenever the ship moves, and
flashing that would be flashing the fact that you are flying. MEMBERSHIP DECIDES IT, never the values:
every row's distance changes on every jump, so flashing a changed cell would flash the
whole table each time you move, and a signal that fires constantly says nothing. The
first fill flashes nothing either, or the overlay would flash every row it has at startup.

**The clipboard flash is for the handovers you did not press a key for.** `copy_selected`,
`advance_clipboard` and the route's next-hop copy all go through
`Companion.took_clipboard()`, the one place `self.copied` is set, so nothing can hand the
clipboard over without saying which row it came from. The case it exists for is the
alt-tabbed one: you plot to the best system in an adjacent sector, the plot answers it,
the row leaves and its successor is copied while you are still in the galaxy map. Coming
back, the amber says which line is in the paste buffer — and for a Current sector or
Adjacent sectors row that is worth more than elsewhere, because what those rows copy is a
system that is written nowhere on screen until the cursor is on it.

**It is QUEUED, not painted where it is asked for**, and that ordering is the whole point.
`advance_clipboard()` deliberately runs BEFORE the repaint — it is the fast path, ahead of
~2 s of SQL — so flashing there would light the row up at the position it is about to
leave, and the repaint would then move it. The flash belongs to the moment BOTH things are
true: the name is on the clipboard and the row has arrived at its new place. So
`took_clipboard()` only records the name, and `place_cursor()` fires it as its **step 4**,
after the tables have been refilled and the cursor placed. Every path that can move a row
ends in `place_cursor()`, so there is exactly one point where the clipboard and the screen
are both settled, and that is where the amber appears. A name no table holds any more
flashes nothing.

The name is offered to **all four tables** and only the row holding it flashes, so the
caller needs no opinion about which table the cursor is in. A table matches on the
displayed system OR on `copy_text`, since an Adjacent sectors row copies a string that
appears nowhere in its SYSTEM column.

**A chime plays**, asynchronously. A perfect fifth (A5 over E6), 0.26 s, soft attack and
exponential decay, at 22% of full scale — it plays over the game, and an alert that talks
over the ship is one you turn off. It is synthesised into the temp directory on first use
rather than shipped as a `.wav`: eight lines of arithmetic beats a binary blob nobody can
diff. `winsound.Beep` was not an option — it is synchronous, and a 250 ms tone would
freeze the HUD on the same thread that is drawing the thing the sound announces.

`--no-sound` silences the chime and keeps the flash. Any failure — no sound device, no
`winsound`, an unwritable temp directory — degrades to silence rather than an error: none
of them is a reason to stop telling you about a black hole.

**The clipboard tick is the second sound, and the gentlest thing the overlay makes.**
Every cursor move copies, so it is by far the most frequent — the only sound that can be
heard several times a second — and that constrains it completely: it is the chime's root
note ALONE, 0.09 s at 9% of full scale, against the chime's two notes, 0.26 s and 18%.
Same voice, so the two belong to one instrument; a third the length and half the
amplitude, so a copy can never be mistaken for a find. `--no-sound` silences it too.

It plays from `took_clipboard()`, which is the one place every copy passes through — a
key, an answered row, a flown hop — and is therefore already where the copy flash is
queued. Unlike the flash it is **not** queued: the flash waits for the repaint because it
has to light the row where the row ends up, whereas the sound only says the clipboard
changed, which is true immediately. Holding it back would put it ~2 s of SQL after the
key that caused it.

Both sounds are cached in the temp directory under a name carrying a digest of the
numbers that made them, so changing a tone or a decay changes the file name and a stale
`.wav` can never go on playing the old sound.

**The chime is narrower than the flash, on two axes**, and both narrowings were made
after it fired on essentially every route plotted. The flash is free and addresses rows
already on screen, so it covers every find. A sound interrupts, so it has to earn the
interruption.

*Not every rare class.* `CHIME_CLASSES` is `BH, WR, HERBIG, O-TYPE` — it drops
NEUTRON and WHT DWRF, which are 1,229 of the 1,778 chime-triggering classes on record,
neutrons alone being 66%. A neutron is a ROUTING CHOICE: chiming for one is the tool
congratulating you on arriving where you aimed. It is a flag of its own on the kind,
never derived from another: what is worth a sound and what is worth a line answer
different questions, even where they name the same kinds today.

*Not every hop.* `finds` is every rare star ON the route, including ones confirmed weeks
ago, so re-plotting the same route re-announced them. `record_seen` returns the NAMES of
the systems it had never seen — not a count, which is what it used to return — and only
those count as a REVEAL. A route past a known black hole is not news.

*Neutrons, but only where we called it.* `CHIME_IF_PREDICTED` is a third tier between
the two above: a neutron sounds only if the system is a BOXEL PREDICTION of ours —
`system_predicted.is_catalog = FALSE`, which the schema defines as "in NO dump". A
neutron you steered toward is not news, but a neutron in a system we asserted into
existence from a gap in the boxel index, that appears in no catalogue and nobody has
visited, is the model being right about a place nobody had looked.

`is_catalog` is the whole test, and no `is_known` probe is needed beside it: the
catalogued half of `system_predicted` is by construction the half that resolves to
`system_known`, so the flag already says "not known". Probing to re-derive that would
cost something to learn nothing; the flag costs 3 ms.

All three tiers meet in `App.chime_worthy()`, called INSIDE the reveal batch so the
decision rides the session that is already open. That used to save a 160 ms attach of
the model; the mirror has made the saving small, but the placement is still right —
the lookup runs only if a fresh neutron got that far, so an ordinary plot pays nothing.

## Where colour is used

Two things carry colour and nothing else does:

| | means |
| --- | --- |
| `SYSTEM` | the row **kind**: bright green = confirmed, violet = POI, blue-grey = catalogued backfill, dimmed = class already revealed |
| the numbers | the probability gradient |

Everything else stays on its column default. Earlier the row kind tinted *every* cell,
which turned whole rows violet or blue-grey and left almost nothing at its normal
colour — the tint stopped meaning anything because it was everywhere.

## Confirming systems from the galaxy map

**This is the tool's edge.** Plotting a route rewrites `NavRoute.json` with the arrival
`StarClass` *and* exact `StarPos` of **every hop**, so one plot across the galaxy
confirms dozens of systems at once — for free, thousands of ly before anyone flies
there. `FSDTarget`/`StartJump` add the same fact one system at a time. All of it lands
in `system_seen`, and the **Confirmed** table is built straight out of it.

The whole route is harvested, not just the destination. The file is mtime-gated, so it
is only re-parsed when a plot actually happens.

**Every prediction the table shows can be confirmed this way**, without exception —
which is the standing test a column has to pass to be on screen at all. Two have failed
it and been removed: `He GIANT`, a planet where a route plot only ever reveals the
arrival star, and `SUPERGNT`, an arrival star the plot names only by its base letter.

The mapping is `kinds.py`, and the two columns below are the two names an object has
here: the **stored** key that lands in `system_confirmed.kind`, and the **shown**
abbreviation that is also the column heading. They differ for exactly two kinds, which
is why the screen used to disagree with itself.

| stored `kind` | shown | classes matched |
| --- | --- | --- |
| `BH` | `BLK HOLE` | `H`, `SupermassiveBlackHole`, `SuperMassiveBlackHole` |
| `WR` | `WOLF-RAY` | `W` `WN` `WNC` `WC` `WO` |
| `HERBIG` | `HERBIG` | `AeBe` |
| `O-TYPE` | `O-TYPE` | `O` |
| `NEUTRON` | `NEUTRON` | `N` |
| `WHT DWRF` | `WHT DWRF` | the fifteen `D*` codes |

### A system somebody has already reported is not a find

**Confirmed excludes anything present in the model's `system_known`.** That table's own
comment is the argument: *"observed, NOT predicted — every row is a system somebody has
actually reported."* Reporting means honking, honking discovers the arrival star, so the
rare object already has someone else's name on it. The overlay tests it against
`model.system_known_probe`, the pruned mirror of that table — see the note on its
one-sidedness below.

It filters out about half the table, and it bites hardest on the numerous kinds —
neutrons and O-types sit beside plotted routes, so somebody has usually honked them
already. Black holes and Wolf-Rayets survive it more often than they used to: the
columns are no longer empty, and a `BLK HOLE` row here is a find nobody has reported.

> **The filter is `known`, never `not predicted`.** Most survivors are in *no dump and no
> prediction either* — and those are the best rows in the table. They are missing from
> `system_predicted` only because the boxel-gap enumeration is a documented lower bound,
> heavily core-biased. Filtering on "must also be predicted" would delete them to keep
> the already-catalogued ones.

Stored, not computed: `system_seen.is_known` and `system_confirmed.is_known`, resolved by
`common.current.resolve_known()` against `model.system_known_probe` — a pruned 6,943,571
name list built by `etl/refresh_current.py`. Probing inside the query was the obvious
implementation and cost **1.8 s per call** against the full 200.8M-row name bridge; the
probe is ~300 ms cold and 3 ms warm, and needs no model database.

> **The probe is one-sided: a hit is proof, a miss is not.** It drops systems the dumps
> positively rule out and systems below mass code `e`, which is what makes it 76 MB
> instead of 2.33 GB. So `resolve_known()` writes `TRUE` on a hit and leaves `NULL` on a
> miss — never `FALSE`. Measured against `system_confirmed`: of 1,655 systems that *are*
> in the dumps it finds 1,250, and every one of the 405 it misses is a neutron or white
> dwarf, which the Forge builds one mass code below the floor. The five headline kinds
> have no rows below it and are exact.

`NULL` means *not yet checked* and is shown, because hiding a genuine find until a loader
has run is the expensive direction to be wrong in.

**The Confirmed table is GALAXY-WIDE**, unlike everything else on the overlay.
Confirmed finds are certainties and there are few of them, so hiding the ones outside
the current sector threw away the point — these are worth diverting for. The sector
table stays sector-scoped because predictions are plentiful everywhere and only nearby
ones matter.

### One line per kind, and a narrower table for it

**The table is the vocabulary, one row each: the nearest confirmed find of every kind.**
`BLK HOLE` says where the closest black hole is, `NEUTRON` where the closest neutron is,
and neither can push the other off the list. That is not a cosmetic ordering — the
confirmed population is wildly uneven, and ranked purely by distance the table was
neutrons. Of the **1,363** finds standing today, **816 are neutrons and 398 O-types
against 8 black holes**, so the numerous kinds are nearer essentially always. A row each
answers the question actually being asked, and it needs no quota to do it.

Rows sit in **rarity order** — `kinds.py`'s own order — not by distance, because a fixed
set of rows is worth finding by position: the black hole line is always the top line.
The distance is on the row for whoever wants it, and the footer's *nearest confirmed*
takes the minimum across the rows and names the kind, since the top row is no longer it.

A kind with nothing confirmed simply has no line. Systems with no coordinates sort
**last** within their kind, not first: `system_seen` holds `x/y/z` only when a *route
plot* revealed the system — an `FSDTarget` gives the class alone — and unlocated is not
the same as near.

| column | |
| --- | --- |
| `SYSTEM` | the nearest system of this kind |
| `TYPE` | the kind, in the same eight characters the prediction columns use as headings |
| `DIST` | how far, in ly |
| `Σ` | how many of this kind are confirmed and **still uncollected** — the same pool the row was picked from, so the tally and the row agree by construction |

**So this table drops the prediction columns and draws narrow** — 400 px against the
sector table's 794. A confirmed find is a certainty; a probability cell on one of
these rows could only ever say "not applicable", six columns of it on every row.
`theme.CONFIRMED_COLUMNS` is every text column of `COLUMNS`, no predictions, plus
`TALLY` — derived rather than written out, so a width or an order changed for one table
still reaches the other. `TALLY` sits outside `COLUMNS` on purpose: on any other table
that cell would have nothing to count. The
renderers are unchanged: `TargetTable` takes the column list as a parameter and walks
whichever one it was given.

> Both spellings of the supermassive black hole are matched deliberately: the journal
> writes `SupermassiveBlackHole`, the model's `body` table writes
> `SuperMassiveBlackHole`. One capital apart, and matching only one would silently drop
> Sagittarius A*.

## Storage: DuckDB, no JSON

Writes go to `elite_mapping_v2_current.duckdb` at the repo root — `common.current`
resolves it by path as `CURRENT_DB` — and **nowhere else**. The model
database is attached `READ_ONLY`, so an accidental write raises instead of landing —
it is derived and fully rebuilt by `etl/`, so anything written there would be silently
erased by the next merge. Rationale in `ETL.md` §0.

On arrival the app writes `system_visited`, and `poi_visited` if the model knows the
system holds a point of interest. Both are idempotent, so a replayed journal event
cannot double-count.

### One connection, released when idle

DuckDB lets **one process** hold a database file, so an overlay that held the app-state
database forever would lock out every loader and every read — you could not inspect your
own flight log while flying.

That used to be solved by opening the file per operation, with `batch()` pinning one
session for the length of a repaint to amortise the ~1.3 ms attach. Both are gone. One
thread owns the database now, so there is nothing to amortise and nothing to coordinate:
`Database._connection()` builds a single connection holding the app-state file
read-write, and every query runs on it. The model is not attached — its ten tables are
mirrored into that same file's `model` schema, so `etl/` can merge the 60 GiB original
while the HUD is flying.

The file stays free by a different mechanism — `release_if_idle()` closes the whole
connection after `--model-idle` seconds without a query, which is exactly when a loader
wants it, and rebuilds in ~17 ms on the next request. It is the worker's own
housekeeping rather than a command, since closing the connection is a session-owning act.
The tick itself touches no database at all.

One guard was lost and replaced. The app-state file used to be attached `READ_ONLY` for a
repaint, so a read that tried to write raised. A single connection cannot do that, so the
check moved up: `Database.WRITES` names the writing methods and `DbWorker` refuses one in
a request not declared as a write — which fails with the offending method's name instead
of a DuckDB error.

### All presentation is SQL

Every string the table shows — the `F1` label, `Mass H`, the percentages, the thousands
separators — is produced by the query, not by Python. `database.top_targets()` returns
display-ready rows and `table.py` places them verbatim. The app displays and tracks; it
does not compute. The only Python that touches a value is per-cell **colour**, which
reads raw columns (`mass_code`, `star_class`) carried alongside the formatted ones.

`id64` is deliberately left `NULL` by the app. Resolving it means probing the
name bridge — seconds of work, fine in a loader, not inside a UI callback on every
jump. `etl/load_system_*.py` backfill it later.

## Layout

Strict separation; each concern has exactly one home.

| Module | Owns | Knows nothing about |
| --- | --- | --- |
| `kinds.py` | **what a predictable object IS** — its stored key, its column, its one on-screen abbreviation, its arrival classes, and the four flags that say what it is *for* | SQL, Tk, colour, widths |
| `theme.py` | every colour, font, column width, and the **order** columns sit in | data, Tk widgets |
| `names.py` | parsing `Blaa Hypai BA-A g5` → sector, mass code | IO, database |
| `journal.py` | finding, tailing and rolling over `Journal.*.log` | what an event *means* |
| `database.py` | **all** SQL, both databases | Tk, the journal |
| `table.py` | laying out the 10×7 grid | SQL, ranking, formatting |
| `overlay.py` | frameless/topmost/drag/placement | what is inside it |
| `main.py` | wiring the above together | any of their internals |

Three rules that keep it that way: `database.top_targets()` returns **display-ready
strings**, so `table.py` places text rather than computing it; `theme.COLUMNS` is
**one** list driving both the header and the cells, so the two cannot drift; and
**every name for an object comes from `kinds.py`**, so the screen cannot call one thing
two things.

### One vocabulary

A black hole was spelled four ways in four files: `p_bh` in the model, `BLK HOLE` in
`theme.py`, `BH` in the TYPE cell and in `system_confirmed.kind`, and prose in the
footer. Nothing tied them together, and they drifted: a TYPE cell truncated one
character short of the heading four columns over, and a prediction reaching the renderer
under a second, shorter name for no reason anyone could recover. `kinds.py` now holds one
row per object, and the four names on it are four *because they answer different
questions*:

| field | what it is | may it change? |
| --- | --- | --- |
| `key` | the classification **stored** in `system_confirmed.kind` | **No.** Every row of `system_confirmed` carries one, in the one database that cannot be rebuilt; renaming one splits a kind's own history in two |
| `column` | the `system_predicted` column *and* the row-dict key — now the same string | with the model |
| `abbr` | the **one** on-screen abbreviation: column heading **and** TYPE cell | freely — it is display |
| `name` | prose, for footer messages where an abbreviation reads as noise | freely |

So a confirmed black hole's TYPE cell now reads `BLK HOLE`, under a heading reading
`BLK HOLE` — one word for one object. `TYPE` widened from 7 to 8 to hold it. The
`rare` / `ranks` / `chime` flags live on the same row and are deliberately **not**
derived from one another; `kinds.py` records what went wrong each time a previous
version derived one from another.

Everything in `database.py` that used to be a parallel list — `DISPLAY_P`,
`CONFIRMED_CLASSES`, `RARE_COLUMNS`, `CHIME_KINDS`, `RANK_BY`, and the
four SQL `CASE` ladders — is now generated from it. `theme.py` still owns column
**order** and width, and asserts at import that its list and `kinds.py` name the same
set, because a kind added to one and missed in the other would be computed, ranked,
chimed for and never shown.

The table is **refilled, not rebuilt** — labels are created once and only their text
changes, because destroying and recreating them every jump flickers and leaks Tk
objects.

## The ship's jump range

`ship: jump 75.3 ly   neutron 452 ly` is **printed to the log at startup, not shown on
screen**. It is a standing fact about the ship and it does not change while you fly, so
on the HUD it was a line that never moved, taking width from tables whose rows move on
every jump. In the log it sits with the keybinds and the startup counts — the rest of
what the session decided about itself — and is there when you want it.

The loadout is still read: `SHIFT+N` routes on `self.jump_range` and `lights.py` turns
`FuelCapacity` into a fuel fraction, so it is parsed whether or not a number is
displayed. Failure stays silent by design — a missing `Loadout` or an unrecognised drive
means `ship.py` refused to guess, and the honest report is nothing at all rather than a
plausible number nobody can check in flight.

`app/ship.py` computes it; it is the overlay's only piece of physics, and the only module
here that is neither a database query nor a log read.

**The unboosted range is read from the game; the boost multiplier cannot be.** The range
comes out of the `Loadout` event's real engineering — optimal mass, unladen mass, fuel,
boosters — checked against 1,192 unboosted jumps with worst breach +0.063 ly (0.08%).
Nothing in the journal reports a *supercharged* range, so the multiplier is measured from
`BoostUsed: 4` jumps instead, and it belongs to the **hull**:

| ship | boosted jumps on record | max flown | ÷ laden range |
| --- | ---: | ---: | ---: |
| `explorer_nx` (Caspian) | 563 | 469.06 ly | **5.97×** |
| `mandalay` | 10 | 360.14 ly | **3.87×** |

Neither maximum exceeds its multiplier — a hard game-side cap rather than a lucky tail —
and both fall just under because the longest jump on record was not flown at the heaviest
fuel state. `ship.neutron_boost()` is the one place that decides; anything not in the
table gets 4.0, which is the rule rather than a guess.

**`Loadout` is watched, not read once.** The game writes one on login, on every outfitting
change and on every ship swap, so swapping ships re-ranges the overlay within a tick —
and because every chain records the range it was solved at, all of them go stale and
re-plot on their own. A Caspian and a Mandalay differ by half the boosted range, which is
the difference between a 49-jump chain and one that cannot be flown at all.

**The cheap reject in `_interesting()` has to name every event set.** It runs on every
line of a journal that is hundreds of thousands long, so it stays a substring test — but
it listed only `StarPos` and `StarClass`, and a `Loadout` carries neither. `Loadout` was
in `INTEREST_EVENTS` and handled by `take_loadout()`, and no `Loadout` ever reached
either: the range really was read once at startup and assumed for the session, and the
fuel light divided a live `FuelMain` by the previous ship's tank. Swapping a 64 t Type-9
for a full 16 t Cobra put the left light at exactly 0.25 — the bottom of the gradient,
solid red — on a full tank. `INTEREST_KEYS` now names `Loadout` too.

**`read_loadout()` picks the newest journal by mtime, not by name.** Elite's old
`Journal.<yymmddhhmmss>` filenames still sit in the directory beside the current
`Journal.<iso8601>` ones, and they sort **above** them, so a reverse-name walk starts at
a file that can be years old. `latest_journal()` had always used mtime; the two now give
the same answer to the same question.

```
range = optmass/(unladen + fuel + reserve + cargo)
        * (min(maxfuel, fuel)/fuelmul) ** (1/fuelpower)
        + jumpboost
```

`optmass`, `unladen`, `fuel` and `reserve` come from the journal's `Loadout` event —
the only source that knows your engineering. `fuelmul`, `fuelpower`, `maxfuel` and
`jumpboost` appear in no journal event at all and are transcribed from EDCD/coriolis-data
into a static table, so the overlay never reaches the network in flight.

### It does not use `Loadout.MaxJumpRange`, which looks like the answer

`MaxJumpRange` is the range at unladen mass carrying exactly **one jump** of fuel — the
on-fumes ceiling. The formula at `unladen + maxfuel` reproduces the reported 82.615 to
three decimals, and the real full-tank range is **75.3**. Plotting on 82.6 overstates by
10% and hands you legs you cannot fly.

**A full tank is deliberately the number shown.** It is the heaviest fuelled state, so it
is the shortest range you will have, and every leg stays flyable as the tank drains. The
other convention is the one that strands you.

### The neutron multiplier is 6.0, not the 4.0 everyone quotes

Measured, not assumed: 241 jumps carrying `BoostUsed: 4` on one fingerprinted loadout,
19 of them within 0.5% of 6.0 and none above it — the shape of a game-side cap, not a
lucky tail. Measured on **one drive**, so a different ship needs re-measuring; that is
why it is a single named constant and not a table whose other rows would look equally
authoritative.

### What was checked, and what was rejected

The constants were tested with **zero free parameters** against 1,192 unboosted jumps on
a single loadout: 24 breaches of the predicted ceiling, worst +0.063 ly (0.08%), and the
largest fuel burn on record was 6.80 t against the table's `maxfuel` of exactly 6.8.

Selecting those jumps required **hashing the full module list** — slot, item, blueprint,
experimental effect and every modifier value. `ShipID` plus `UnladenMass` is not enough;
the journals hold a dozen configurations and ShipIDs are reused.

Reconstructing `UnladenMass` from hull and module masses was tried and **rejected**.
coriolis-data has no `int_fighterbaymk2_size5_class1_free`, an unknown module contributes
zero, and the result came out 10 t light — silently, and always **optimistic**, which is
the direction that strands you. `Loadout.UnladenMass` already accounts for every module
and every engineered mass change and cannot drift when Frontier ships a new part.

An unrecognised drive shows **nothing** rather than a guess. In flight, a plausible
number nobody can check is worse than a blank.

**Written once, at startup, like the keys.** An outfitting change mid-session will not
update it — the price of keeping a journal re-read off the paint path. It also rides that
table's `hide_when_empty`, so before the first position event there is nothing to show it
on; the carrier/neutron table is populated from then on.

## Neutron jump mode

`SHIFT+N` on a selected row plots a **minimum-jump** route to it through neutron stars
and takes over the carrier/neutron table with the next hops. `SHIFT+N` again tears it
down. Arriving at a system on the route drops the hops behind you and copies the next
one to the clipboard.

`app/route.py` is the pathfinder, `Database.neutron_corridor()` the one query it needs.

### Why breadth-first is the exact answer, not an approximation

Every edge costs exactly one jump — you are either in boosted range of the next cone or
you are not — so BFS returns a provably minimum-hop route. There is nothing for A* to
improve on and no heuristic to get wrong. It is levelled and vectorised: one
`query_ball_point` per **level** over the whole frontier, not one per node.

### The first leg is allowed to be several plain jumps, and has to be

You start wherever you are, which is usually not next to a cone. Measured from one real
position in deep space, the **nearest neutron was 115.9 ly against a 75.3 ly range** — a
router demanding a cone within one jump answers "no route" almost everywhere.

It costs nothing to allow, because every hop this produces is pasted into the galaxy map
and **Elite's own plotter finds the ordinary systems in between**. That is also why
nothing checks those systems exist: ordinary systems outnumber neutrons about 58 to 1,
and if the galaxy map cannot plot it, it says so long before you undock.

### The corridor allowance is absolute, not proportional

Nodes come from a prolate spheroid with the two systems as foci:
`dist(start) + dist(dest) <= direct + pad`.

A proportional slack sounds tight and is not. **15% on a 22,820 ly run permits a 3,423 ly
detour, which selected 654,108 neutrons and cost 789 ms.** The spheroid
fattens with the square of the allowance while the useful corridor does not, so a fixed
few hundred light years keeps a long route as cheap as a short one. The search widens
once — 600 ly, then 2,500 — before reporting failure, because "no route in the box we
drew" is not the same statement as "no route".

### Capped at 10,000 ly

Not really a performance guard. Past that distance the honest advice is a fleet carrier
or the neutron highway rather than a chain of cones held in a HUD — a 48,578 ly plot to
Sol selected 2.95M neutrons and spent 4.5 s fetching them before the search
started.

### What it does not model: fuel

A supercharged jump burns the drive's **maximum** fuel and **you cannot scoop at a
neutron star**. A long chain of boosted jumps will run the tank dry and this router will
hand you one anyway. It answers "what is the shortest chain of cones", which is not the
question "can I get there".

Detouring to a scoopable star costs nothing: arriving somewhere **not** on the route is
neither an error nor a reason to tear the route down, so the route is still there when
you rejoin it.

### Arrival matches anywhere in the remaining route

Not just at hop zero. A cone route is flown by hand and you will overshoot it — a longer
jump than planned, or two hops plotted at once in the galaxy map — and a router that
recognised only the very next system would sit there insisting on one you had passed.
Hops behind you are dropped and the count in the heading reflects it.

### The route is in memory only

The app-state database records what the commander has **seen, visited and found** —
durable facts about the galaxy. A route is a plan: the next plot invalidates it and one
keypress rebuilds it. Restarting the overlay drops it, deliberately.

### SHIFT+N gets its own press slot

Like `SHIFT+BACKSPACE`, and for one more reason. The shared slot is last-press-wins, so
an arrow key arriving in the same 120 ms tick would swallow it — and losing a **toggle**
does not merely drop an action, it leaves the key meaning the opposite of what it should
on the next press. A key-repeat burst collapses to one toggle for the same reason.

### Route rows are the one exception to database.py owning every row

They come from a computation rather than a query. Handing the solved path back to SQL to
be re-selected would be a round trip to dress up data already in hand.

## The clock

`hh:mm` local time, top-right, on the same line as the `Nearest` heading. It is
`place`d rather than packed, and that is the whole design: `Nearest` is packed to the
RIGHT precisely so its edge lands on the edge of the tables below it, and a packed
clock would claim that strip and push it out of line. Placed, it costs no layout at
all — it sits in the empty right-hand end of that heading, which `set_title()` already
keeps short — and it stays in the corner on the ticks when `Nearest` has no rows and
hides itself, which is why the clock is not simply a second label inside that table.

It is `lift()`ed after the tables are built, because Tk stacks siblings in creation
order and the `Nearest` container covers the same corner. It is rewritten only when the
minute turns: the tick runs eight times a second and the label does not.

## The tables dictate the width, nothing else

The help bar is **two columns**, gridded, and **clamped to the width of the tables**.

```
[Pg Up] / [Pg Down]  Table    [Shift+Backspace]  No such system
[Up] / [Down]        Row      [Shift+N]          Neutron route
The highlighted row is copied
```

Measured: laid out in one line the six keys came to **1,002 px against the tables' 934**,
so the least important thing on screen was setting how much of the canopy the HUD
covered. This brings it to **481 px**.

**Four grid columns, not two** — key, description, key, description. The keys are ragged
(`[Up] / [Down]` against `[Shift+Backspace]`), so with each pair in one cell every
description started at a different x and the bar read as scattered words. Giving the
descriptions their own column is what lines them up, and alignment is the whole reason
to grid rather than pack. The pad alternates by column (`theme.HELP_PAD`) because the
joins differ: a key and its description are one phrase and take the tighter gap, while
the gap after a description separates one keybind from the next and must be the wider of
the two — otherwise the eye groups "table" with the key to its *right*.

The copy note is **not a keybind** — it is what the four keys above it do — so it gets
its own line beneath them rather than being tucked into a description column, where it
would read as the label for a fifth key that is not there. An **empty cell is absorbed
into the span of the one before it**, which is what lets that line lay out independently
of the four columns: put in column 0 without a span it would force its own width onto
that column and drag every column after it out of true. It is also why the bar came
*down* from 586 px — the line is no longer stretching column 3.

`theme.HELP_GAP` sets a gap between the last table and the bar. It is a different kind
of thing from the grids above it — it describes the HUD rather than reporting the galaxy
— and butted straight against the last row it read as one more row of that table. The
gap is pack `pady`, outside the frame, so it does not disturb the height the width clamp
fixes.

Descriptions are **capitalised**. They are labels, not sentence fragments, and at this
size a lower-case run after a bracketed keycap reads as continuing the key rather than
naming it.

Two pairs and not three: a third wins back little width and costs another line of
vertical space over a HUD already competing with the game's own.

Key labels are **title case and abbreviated only where the short form is unambiguous** —
`[Pg Up]`, but `[Shift+Backspace]` spelled out. Upper case reads as shouting at this
size and the brackets already mark it as a control. A slash joins a pair because PAGE UP
and PAGE DOWN are opposite ends of one control; merely adjacent, they read as two
separate bindings sharing a description. With 453 px of headroom left, abbreviating
further buys nothing and costs legibility.

`_clamp_help_width()` then fixes the bar to the body's requested width and turns
geometry propagation off, so anything too wide is **clipped** rather than allowed to
widen the window — a 400-character line renders at 934 px instead of 2,820. Clipping the
hint is the right failure: the hint is recoverable by reading this file, the window
covering the canopy is not.

**`grid_propagate`, not `pack_propagate`.** The cells inside are gridded, and each
geometry manager has its own propagation switch — turning off the one that is not
managing those children is a silent no-op, and the clamp measured as doing nothing at
all until this was the right call.

Cells, rather than one flat run of labels, because a column only lines up if the thing
in it is a single widget.

## Keys and visibility

**One cursor, not a key per row.** Rows reorder and drop out as they are answered, so a
key bound to a row means something different by the time you press it; a cursor is
wherever you last put it. `app/hotkeys.py` holds the bindings and the help bar at the
foot of the window spells them out on screen — it survives `--chrome` being off, because
that is the default and there would otherwise be nothing saying the overlay takes keys.

**Whatever the cursor lands on is copied** — no confirm key. The selected row is painted
with a solid background band (`Palette.sel_bg`), which is the entire indicator.

Every key copies a **system name**, because that is what the galaxy map's search box
accepts. **Adjacent sectors is the exception**: it displays a sector, which the box will
not take, so it copies the best system *inside* that sector and the footer says which.

Table paging **skips empty tables**, so the cursor never lands on a heading with nothing
under it, and it **remembers where you were** in each table: page away from row 6 of
Confirmed and back, and you land on the row you left, not the top. The mark is the row's
target, not its index — the sector and adjacent tables reorder as you fly, and Confirmed
rewrites a line whenever a nearer find of that kind turns up, so an index would bring you
back to a different system. A target that has been answered while you were away
is gone from the list, and paging back lands on the top. Row movement **wraps** — ten rows with no scrollbar, and running off the
bottom and stopping dead is worse than coming back to the top. The sector `TOTAL` row is
not selectable: you cannot fly to a sum. The cursor is **clamped, not reset**, on every
refresh: land on row 6 of Confirmed, fly two jumps, and you are still on row 6 unless
there is no longer a row 6.

### `SHIFT+BACKSPACE` — the only key that writes anything

Every other key copies. This one records a **finding**: you pasted the name into the
galaxy map and it would not plot, or you arrived and there was nothing there.

**It filters, it does not delete**, and that is the whole design. The obvious
implementation is to remove the row from `system_predicted` or `system_unfound`. Two
reasons that is wrong, and either one alone settles it:

1. **The app may never write the model.** Both tables are derived, and both builders
   delete rows their pool no longer produces — so the correction would survive until
   the next rebuild and then vanish with nothing to show it had been made.
2. **It is the only negative evidence this project can collect.** Every other table
   here is built from what somebody reported *seeing*; nobody reports an absence.
   Deleting the row would throw the finding away in the act of recording it.

So the prediction stays exactly where it is, a row goes into `system_wrong` in the
**app-state** database, and every read that offers a destination filters against it.
Re-running the whole pipeline cannot reproduce a single one of those rows, which puts
them in the same class as the flight log: back them up.

**Only rows that are a guess.** Predictions, catalogued backfill, an adjacent sector's
best system, and unfound catalogue stars. A confirmed find, a POI, a carrier or a
neutron is a place the game has already said exists — if one of those will not plot the
fault is a spelling or a stale dump, and the answer is to look at it rather than to
record a galaxy-wide absence. The footer says so rather than silently doing nothing.

It has **its own key slot**, unlike the four navigation keys which are last-press-wins.
An arrow arriving in the same 120 ms tick would otherwise swallow the one press that
records something. And it is gated on foreground focus even harder than the arrows are:
`SHIFT+BACKSPACE` is an ordinary chord in a text field, and an ungated global hook would
record an absence every time the commander deleted a word somewhere else on the machine.

The 12 systems migrated from the old `wrong.json` — `Blaa Hypai AA-A h55` and `h68`
among them — are already in the table, so they no longer come back.

### The focus gate is not optional

The navigation keys are the **arrow keys**, hooked globally because the overlay never
holds focus. Ungated, every arrow press anywhere on the machine — an editor, a browser,
a file rename — would move the cursor and overwrite your clipboard. `main.tick()` drains
a press only when `focus.is_foreground()` is true, which means Elite or the overlay
itself. The F-keys were rare enough to get away without this; arrows are not.

Registered GLOBALLY via the `keyboard` library, with `suppress=False` so the game still
sees the key — swallowing the arrows would break the galaxy map for the sake of a HUD.
`--no-hotkeys` disables them entirely.

The callback fires on the `keyboard` hook thread and **Tk is not thread-safe**, so it
only records the key; the Tk loop drains it on its next tick. Clipboard writes go
through Win32 rather than Tk, because Tk's clipboard is emptied when the app exits —
copy a waypoint, close the overlay, and you would paste nothing.

**The overlay hides itself unless Elite has the foreground.** Its own window counts too,
or clicking to drag it would make it vanish under the cursor. `--always-visible` to
disable; on non-Windows it is always visible.

## The throttle LEDs

The VKB STECS has three RGB LEDs. `common/vkb.py` is the wire — HID feature report
`0x59`, and a **no-op on every call when no VKB is plugged in**, so nothing upstream
tests for one. `app/lights.py` is the policy, and is the only module that picks an LED
colour. `--no-lights` turns the whole thing off.

**The left light is fuel**, as a fraction of the main tank: green above 80%, a gradient
through yellow to red between 80% and 25%, and a **fast red flash below 25%**. It goes
dark when there is no reading — the game is not running, or no `Loadout` has said how
big the tank is. An LED still showing the last known level after the game closed is a
lie the commander cannot see.

**The middle light is the arrival star of the next jump**: blue for a neutron, flashing
blue for a white dwarf, flashing red for a black hole. Dark for everything else and dark
when no jump is targeted — lighting ordinary stars would make it mean "a jump is
targeted" instead of "look at this one". Which classes count is `kinds.py`'s answer, via
`KEY_OF_CLASS`, not a second list in `lights.py`.

**The right light is the ship's own state**: white while the cargo scoop is out,
flashing blue while the shields are down, dark otherwise, and dark whenever the
commander is not in the ship. All three come from bits of `Status.json`'s `Flags` —
`CargoScoopDeployed`, `ShieldsUp` and `InMainShip` — which `journal.py` names in
`STATUS_FLAGS` and reads through `flag()`.

**Shields win when both are true.** One is a warning and the other is a note, and a
warning a note can hide is not a warning.

### The shield light needs the loadout, not just the flag

`ShieldsUp` is simply **clear when the ship has no shield generator**, which is
indistinguishable from a shield that has just gone down. An explorer flying stripped
would get a permanent blue flash. `has_shields()` checks the `Loadout` for a generator
before the light is allowed to warn about one.

### `Flags` is zero at the main menu, and zero is not a warning

A shields-down reading is only a warning while there is a ship to lose. At the main
menu Elite writes `Flags` as a plain **0** — shields down, scoop stowed, and no ship at
all — so reading it straight left the right light flashing blue at a game nobody was
playing. `ship_color()` requires `InMainShip` before either state can light. The fuel
light never had the problem: that `Status.json` carries no `Fuel` object either, and no
reading is already dark.

### The LEDs are darkened on the way out

An override **holds until the throttle is power-cycled**, so an overlay that simply
exited left whatever it last wrote — a flash and all — lit on hardware nothing was
driving any more. `run()` calls `Lights.clear()` in the same `finally` that stops the
database worker.

### The middle light is seeded at startup

`harvest_classes()` is in file order, so its last row is the jump targeted most
recently. Without seeding `next_jump` from it, the light stays dark after a restart
until the commander happens to target something new. Seeding from an old journal is
safe because `targeted_class()` still needs `Status.json`'s `Destination` to name the
same system before it lights anything.

### Every report replaces the device's whole table

An LED left out of a report **goes dark**, so writing the middle light on its own blanked
the fuel light beside it. `Lights` holds all three as one state and resends the lot
whenever any of it moves. `Throttle.show()` is the call that takes them together.

### The middle light needs two sources to agree

`FSDTarget` carries the next system *and its arrival class*, and it fires about six
seconds after each jump — but **nothing retracts it**, so on its own it outlives the
route and leaves the light lit at a star already behind you. `Status.json`'s
`Destination` *is* retracted — it clears when the route ends and moves the instant
anything else is targeted — but never says what the star is. The light needs the same
system name from both, plus `!= self.system` to cover arriving *at* the target, where
the game leaves the destination naming the system you are sitting in.

`NavRoute.json` is the wrong source here: its first entry is the system you plotted
*from*, and it does not shrink as you fly, so "next jump" is never a fixed index into it.

### The gradient is 15 steps, not 256

VKB gives **3 bits per channel**, so red and green each move in eighths. `#ff8000` comes
back from the device as `#ff9200`. It reads as a gradient at a glance and will never
match a hex code on screen.

### Fuel comes from `Status.json`, which is the only live source

Elite rewrites that file on every change — a genuinely current number, unlike module
health, which appears **only** in `Loadout` and so is a snapshot from login. `read_status()`
is mtime-gated like `read_navroute()`, with one difference: the game rewrites the file
**in place**, so a read can catch it half-written, and a parse failure returns the OLD
mtime. That leaves the gate open for the next tick instead of freezing the reading until
the game happens to write again.

### The write is on the Tk thread, and that is safe here

A `paint()` costs **5 ms** — measured, median of 12 — and `Lights` holds the last state
it wrote and sends nothing when the colour has not moved. The tick runs eight times a
second; the light changes a few times an hour. The first call enumerates HID and costs
38 ms, once. That is why this does not need the `dbworker` treatment.

### The app owns those lights until the throttle is power-cycled

There is no "give it back to the VKB profile" in the protocol: `off()` darkens an LED,
it does not release it. So from the first write, the three LEDs are the overlay's,
including after it exits.

## Not wired yet
- `observations.jsonl` (the calibration-loop input), `outcomes.json`, `carrier_gone.json`
  — likewise unmigrated and not reproducible. See `CLEANUP.md`.
