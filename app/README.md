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
| `SUPERGNT` | **Supergiant**, any spectral class — an evolved massive star, vastly larger and brighter than main sequence. The **best-validated** prediction in the project: 2.4× observed over expected. |
| `O-TYPE` | **O-type star** — the hottest and most massive main-sequence class (~30,000–50,000 K, blue). Concentrated in mass code `g`; the richest sectors sit ~55 kly from Sol on the far side of the core, so check distance before routing. |
| `NEUTRON` `WHT DWRF` | Neutron star, white dwarf. Common enough to be near their base rate almost everywhere. |

> **`He GIANT` was removed**, and with it the `p_hr` prediction behind it. A
> helium-rich gas giant is a *planet*, and the only thing this overlay ever learns
> about an unvisited system is its **arrival star** — so it was the one column on
> screen that no route plot, `FSDTarget` or arrival could ever settle. It was already
> outside the visibility bar, so it gated nothing either: eight characters of width
> spent on a number that could only ever stay a guess. The 5.4× enrichment it was built
> on is real and stays recorded in `DEAD_ENDS.md`; it is simply not actionable from
> here. Every column left is a *star*, and every one of them is confirmable.

Every probability is a **two-decimal fraction** (`0.38`), right-aligned, each shown
separately and **colour-coded on a 10-step red→orange→yellow→green ramp**. The scale is
linear over `0.05`–`0.60`, fixed rather than stretched per sector, so the same number is
always the same colour. It was measured, not guessed: across all seven columns, values
at or above `0.05` have median `0.163`, p99 `0.567`, max `0.576`. Most cells therefore
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
least one of `BH`, `WR`, `HERBIG`, `SUPERGNT`, `O-TYPE` — per column, never summed.
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

## Nearest carriers and neutron stars

One table, two kinds of row, because both answer the same question — *somewhere to go
that is not a gamble* — as against the three tables above them, which are all guesses.

### Carriers


Three rows, galaxy-wide, nearest first, from `carrier.is_reliable` — parked over a year
ago **and** seen within the last 90 days. Both halves matter: 30,262 carriers have an
old `last_moved` simply because nobody has looked at them since, and arriving to find
empty space is the one outcome that makes a carrier list worthless.

A carrier row has **no predictions**, so its callsign and name span the whole
prediction area instead of showing eight dashes — and the header over that span reads
`CALLSIGN  CARRIER NAME` rather than eight column names that will never hold a number.
The callsign comes **first, padded to 8**, because it is the fixed-width half (2,513 of
2,524 reliable carriers have a 7-character callsign) while names run from `Barachiel` to
`CONSTELLATION EURYALE` — leading with the ragged field scattered the callsigns across
the table. `CALLSIGN` is itself 8 characters, so the heading sits over its column. `TYPE`
reads `CARR+UC` when the carrier buys exploration data.

### Neutron stars

The three nearest systems whose **primary star** is a neutron — a **jet cone boost**,
nominally 300% on the FSD, though measured on this ship it is ×6.0 of the unboosted
range rather than the ×4 that implies; see *The ship's jump range*. Primary *is* arrival, so you drop out of witchspace next to it and
supercruise nowhere.

**Deliberately not filtered against `system_visited` or `is_known`.** Everything else on
this overlay is about finding what nobody has found; a neutron is about *getting*
somewhere. The boost works exactly as well the second time you use it, and whether or
not somebody else logged the star first. Filtering it the way Confirmed is filtered
would hide the nearest boost *because you had already used it*.

Callsign and carrier name are blank — a dash — since a neutron has neither.

**These three rows are what a plotted route replaces** — see *Neutron jump mode*. The
question changes from "where is the nearest cone" to "which cones are next", and both
cannot be the useful one at once. The three carrier rows above are untouched: a route
does not make the nearest shipyard less interesting. Cached separately for that reason,
which also means plotting costs neither query.

Reads `main.system_neutron`, materialised for this: 3.4M rows instead of scanning
200.7M. The three nearest are ranked on **coordinates alone** and named afterwards —
`system_neutron` carries `x/y/z`, but composing the pasteable name needs `sector`, and
joining all 3.4M rows to it before the `ORDER BY` built 3.4M names to keep three. The
scan is 30 ms; the join was the other 250. Ranking first took the read from 283 ms to
**32 ms**.

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
  `system_known`'s 200,676,922.
- **`system_poi`** (66,548 rows) replaces the two-branch POI union, whose body half
  scanned `system_body`'s 577,639,044 rows to reach 10,023.
- **`system_neutron`** was already there for exactly this reason. It needed no new table,
  only ranking on coordinates *before* joining `sector` for the name: the scan is 30 ms,
  the join to build 3.4M names and keep three was the other 250.

All three **add no facts** and are snapshots, so they go stale until their builder runs
again; `ETL.md` carries that warning. `poi_in_system()` reads `system_poi` rather than
`staging.sys_bridge` for the same reason — it carries the pasteable name, so the name is
the key. 2.2 ms per arrival, and the overlay reads no staging table at all.

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

The idle model release is the worker's own housekeeping rather than a command — closing
the hub is a session-owning act. And because a cold repaint now costs ~450 ms instead of
8 s, `--model-idle` could safely go *down*, handing the model back to `etl/` sooner.

`route.plan()` still runs on the Tk thread: it is CPU, not SQL, and the corridor fetch
that feeds it is now an ask. The widening retry is a second request rather than both
corridors up front, so the common case fetches once.

### The paint is 10 ms; the 91 ms at startup is startup

`paint` as one number read 91 ms, which four grids of at most eleven rows cannot cost.
Phased per grid, the answer is Tk realising the window: three tables are
`hide_when_empty`, so the first `show()` with rows calls `_show_container(True)` and the
`pack()` makes Tk lay out the window and measure fonts. Later paints are pure
`label.config()` — 3.0 ms for the Confirmed grid, against 16.2 ms on its first call.

| refresh | `read` | `paint` | `p_confirmed` | `p_sector` | `p_adjacent` | `p_carriers` | `p_cursor` |
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
O-type and the supergiants all trigger it. The trigger set is `database.RARE_CLASSES`, so
adding a class to the table adds it here with no second edit.

**The row flashes.** The system name fades from white through to the confirmed green it
will keep — 12 steps at 60 ms, 0.72 s in all. White because it is the only colour on this
HUD that means nothing else, so the eye is pulled by something it has never had to
interpret. It FADES rather than blinks: a blink says "look here now" and keeps saying it,
a fade says "this just happened" and then gets out of the way, which is the honest claim —
the row is still there afterwards and the green is doing the work by then.

Only the SYSTEM cell flashes. Tinting the whole row would wash out the probabilities at
exactly the moment they are worth reading, and the name is what you copy anyway. The
animation runs on Tk's own `after`, not the two-second tick, or it would be four frames a
second — a stutter, not a fade. It survives the repaint that the confirmation itself
triggers, because the flash state lives on the table and the refresh replaces the row
dicts underneath it.

**A chime plays**, asynchronously. A perfect fifth (A5 over E6), 0.26 s, soft attack and
exponential decay, at 22% of full scale — it plays over the game, and an alert that talks
over the ship is one you turn off. It is synthesised into the temp directory on first use
rather than shipped as a `.wav`: eight lines of arithmetic beats a binary blob nobody can
diff. `winsound.Beep` was not an option — it is synchronous, and a 250 ms tone would
freeze the HUD on the same thread that is drawing the thing the sound announces.

`--no-sound` silences the chime and keeps the flash. Any failure — no sound device, no
`winsound`, an unwritable temp directory — degrades to silence rather than an error: none
of them is a reason to stop telling you about a black hole.

**The chime is narrower than the flash, on two axes**, and both narrowings were made
after it fired on essentially every route plotted. The flash is free and addresses rows
already on screen, so it covers every find. A sound interrupts, so it has to earn the
interruption.

*Not every rare class.* `CHIME_CLASSES` is `BH, WR, SUPERGNT, HERBIG, O-TYPE` — it drops
NEUTRON and WHT DWRF, which are 1,229 of the 1,778 chime-triggering classes on record,
neutrons alone being 66%. A neutron is a ROUTING CHOICE: chiming for one is the tool
congratulating you on arriving where you aimed. It is stated explicitly rather than
derived from `CAPPED_KINDS`, which answers the unrelated question "would this kind swamp
a ten-row list" and happens to name the same two kinds today.

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
`system_known`, so the flag already says "not known". Probing the 197M-row bridge to
re-derive that would cost 1,729 ms; the flag costs 3 ms.

All three tiers meet in `App.chime_worthy()`, which is called INSIDE the reveal batch
because the model is already attached there — deciding it afterwards would buy a 160 ms
attach for a boolean. The model lookup runs only if a fresh neutron got that far, so an
ordinary plot pays nothing.

## Where colour is used

Three things carry colour and nothing else does:

| | means |
| --- | --- |
| `SYSTEM` | the row **kind**: bright green = confirmed, violet = POI, blue-grey = catalogued backfill, dimmed = class already revealed |
| the numbers | the probability gradient, and the confirmed **✓** in the same bright green so the eye pairs it with the name |

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

**Every prediction the table shows can be confirmed this way** — which is true without
an exception now that `He GIANT` is gone. It was the one that could not be: a planet,
where a route plot only ever reveals the arrival star.

The mapping is `kinds.py`, and the two columns below are the two names an object has
here: the **stored** key that lands in `system_confirmed.kind`, and the **shown**
abbreviation that is also the column heading. They differ for exactly two kinds, which
is why the screen used to disagree with itself.

| stored `kind` | shown | classes matched |
| --- | --- | --- |
| `BH` | `BLK HOLE` | `H`, `SupermassiveBlackHole`, `SuperMassiveBlackHole` |
| `WR` | `WOLF-RAY` | `W` `WN` `WNC` `WC` `WO` |
| `SUPERGNT` | `SUPERGNT` | the five `*SuperGiant` codes |
| `HERBIG` | `HERBIG` | `AeBe` |
| `O-TYPE` | `O-TYPE` | `O` |
| `NEUTRON` | `NEUTRON` | `N` |
| `WHT DWRF` | `WHT DWRF` | the fifteen `D*` codes |

### A system somebody has already reported is not a find

**Confirmed excludes anything present in the model's `system_known`.** That table's own
comment is the argument: *"observed, NOT predicted — every row is a system somebody has
actually reported."* Reporting means honking, honking discovers the arrival star, so the
rare object already has someone else's name on it.

Of 1,087 confirmed systems, **408 were already in the dumps** and are now filtered out.
The breakdown is the reason this matters:

| kind | total | in dumps | survives |
| --- | --- | --- | --- |
| NEUTRON | 629 | 279 | 350 |
| O-TYPE | 298 | 76 | 222 |
| HERBIG | 111 | 24 | 87 |
| WHT DWRF | 28 | 8 | 20 |
| **BH** | **11** | **11** | **0** |
| **WR** | **9** | **9** | **0** |

**Every confirmed black hole and Wolf-Rayet was already reported.** All twenty. Black
holes are the most-hunted objects in the game and these sat beside plotted routes, so an
empty `BLK HOLE` column in this table is a true statement about the galaxy, not a broken
query.

> **The filter is `known`, never `not predicted`.** 455 of the survivors are in *no dump
> and no prediction either* — and those are the best rows in the table. They are missing
> from `system_predicted` only because the boxel-gap enumeration is a documented lower
> bound (220,489 galaxy-wide, heavily core-biased). Filtering on "must also be predicted"
> would delete all 455 to keep 131 already-catalogued ones.

Stored, not computed: `system_seen.is_known` and `system_confirmed.is_known`, resolved
against the 197M-row `staging.sys_bridge` by `common.current.resolve_known()`. Probing
the bridge inside the query was the obvious implementation and cost **1.8 s per call** —
the app opens a fresh connection per operation, so the scan starts cold every time and
there is no index. `NULL` means *not yet checked* and is shown, because hiding a genuine
find until a loader has run is the expensive direction to be wrong in.

**The Confirmed table is GALAXY-WIDE and ordered nearest-first**, unlike everything
else on the overlay. Confirmed finds are certainties and there are only ~1,066 of them,
so hiding the ones outside the current sector threw away the point — these are worth
diverting for. The sector table stays sector-scoped because predictions are plentiful
everywhere and only nearby ones matter.

**At most 3 of `NEUTRON` + `WHT DWRF` + `O-TYPE` combined** among the ten. Distance
alone produced a list of ten neutrons: the confirmed population is wildly uneven, so the
numerous kinds are nearer essentially always and the table stopped being a list of finds.

| | | | |
| --- | ---: | --- | ---: |
| `NEUTRON` | 1,041 | `HERBIG` | 122 |
| `O-TYPE` | 301 | `BH` | 70 |
| `WHT DWRF` | 50 | `WR` | 32 |
| | | `SUPERGNT` | 0 |

The cap **lifts** when there are not enough uncapped finds to fill the slots — an empty
row helps nobody. `HERBIG` at 122 is the next candidate and is left uncapped for now;
it already outnumbers black holes, so if the list fills with Herbigs that is the line to
change.

Rarity otherwise only breaks distance ties, so at equal range a black hole still beats a
white dwarf. Systems with no coordinates sort **last**, not first: `system_seen` holds
`x/y/z` only when a *route plot* revealed the system — an `FSDTarget` gives the class
alone — so 95 of the 1,066 are unlocated, and unlocated is not the same as near.

A confirmed row puts a **✓** in the one prediction column the game settled, and keeps
the kind in `TYPE`. So a single column reads `0.40` — "we think" — on a prediction and
`✓` — "yes" — on a confirmation. The other seven stay `--`: an arrival star answers one
question, not eight, and `0.00` there would be a claim nobody made.

Confirmed rows are ordered **rarest first**, so a sector's white dwarfs can never crowd
its black holes out of the ten visible slots.

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
`Database._connection()` builds a single connection with the model attached `READ_ONLY`
and the app-state file read-write, and every query runs on it.

The file stays free by a different mechanism — `release_if_idle()` closes the whole
connection after `--model-idle` seconds without a query, which is exactly when a loader
wants it, and rebuilds in ~145 ms on the next request. It is the worker's own
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

`id64` is deliberately left `NULL` by the app. Resolving it means probing a 197M-row
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
footer. Nothing tied them together, and they drifted — the TYPE column rendered
`SUPERG…` at seven characters wide while the heading four columns over said `SUPERGNT`,
and `p_supergiant` reached the renderer under the second name `p_supg` for no reason
anyone could recover. `kinds.py` now holds one row per object, and the four names on it
are four *because they answer different questions*:

| field | what it is | may it change? |
| --- | --- | --- |
| `key` | the classification **stored** in `system_confirmed.kind` | **No.** 1,877 rows in the one database that cannot be rebuilt carry these strings; renaming one splits a kind's own history in two |
| `column` | the `system_predicted` column *and* the row-dict key — now the same string | with the model |
| `abbr` | the **one** on-screen abbreviation: column heading **and** TYPE cell | freely — it is display |
| `name` | prose, for footer messages where an abbreviation reads as noise | freely |

So a confirmed black hole's TYPE cell now reads `BLK HOLE`, under a heading reading
`BLK HOLE`, with the checkmark in that column — one word for one object. `TYPE` widened
from 7 to 8 to hold it. The `rare` / `ranks` / `capped` / `chime` flags live on the same
row and are deliberately **not** derived from one another; `kinds.py` records what went
wrong each time a previous version derived one from another.

Everything in `database.py` that used to be a parallel list — `DISPLAY_P`,
`CONFIRMED_CLASSES`, `RARE_COLUMNS`, `CHIME_KINDS`, `CAPPED_KINDS`, `RANK_BY`, and the
four SQL `CASE` ladders — is now generated from it. `theme.py` still owns column
**order** and width, and asserts at import that its list and `kinds.py` name the same
set, because a kind added to one and missed in the other would be computed, ranked,
chimed for and never shown.

The table is **refilled, not rebuilt** — labels are created once and only their text
changes, because destroying and recreating them every jump flickers and leaks Tk
objects.

## The ship's jump range

`jump 75.3 ly   neutron 452 ly` sits at the **right of the "Nearest carriers and neutron
stars" heading**, and over that table rather than any other on purpose: those rows are the
nearest jet cones, and the number that decides whether one is worth flying to is how far
you jump — boosted and unboosted. Question and answer are then one glance, not two.

The heading is a Frame of two labels rather than one Label, because a Tk Label is a
single string end to end: right-aligning a suffix inside one means padding with spaces to
a pixel width the font decides, which breaks the moment the font or the column set
changes. `set_title_right()` is separate from `set_title()` because they change on
different clocks — the left side is retitled every repaint to carry the row count, the
right side is written once, and folding them together would make every repaint
responsible for not erasing the range.

`app/ship.py` computes it; it is the overlay's only piece of physics, and the only module
here that is neither a database query nor a log read.

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
detour, which selected 654,108 of the 3.4M neutrons and cost 789 ms.** The spheroid
fattens with the square of the allowance while the useful corridor does not, so a fixed
few hundred light years keeps a long route as cheap as a short one. The search widens
once — 600 ly, then 2,500 — before reporting failure, because "no route in the box we
drew" is not the same statement as "no route".

### Capped at 10,000 ly

Not really a performance guard. Past that distance the honest advice is a fleet carrier
or the neutron highway rather than a chain of cones held in a HUD — a 48,578 ly plot to
Sol selected 2.95M of the 3.4M neutrons and spent 4.5 s fetching them before the search
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

**One cursor, five keys.**

| key | does |
| --- | --- |
| `[PAGE UP]` `[PAGE DOWN]` | move to the previous / next table |
| `[UP]` `[DOWN]` | move to the previous / next row of that table |
| `[SHIFT+BACKSPACE]` | **this system does not exist** — the galaxy map refused to plot to it |

**Whatever the cursor lands on is copied** — no confirm key. The selected row is painted
with a solid background band (`Palette.sel_bg`), which is the entire indicator; there is
no cursor glyph and no key column. A help bar at the foot of the window spells the keys
out once, in the same bracketed keycap grey Elite's galaxy map uses, and it survives
`--chrome` being off because that is the default and there would otherwise be nothing on
screen saying the overlay responds to keys at all.

Every key copies a **system name** — that is what the galaxy map's search box accepts.
For three of the four tables that is the name in the `SYSTEM` column. **Adjacent sectors
is the exception**: it displays a sector, which the search box will not take, so it
copies the best system *inside* that sector and the footer says which.

`PAGE UP`/`PAGE DOWN` **skip empty tables**, so the cursor never lands on a heading with
nothing under it, and `UP`/`DOWN` **wrap** — ten rows with no scrollbar, and running off
the bottom and stopping dead is worse than coming back to the top. The sector `TOTAL`
row is not selectable: you cannot fly to a sum.

The cursor is **clamped, not reset**, on every refresh. Land on row 6 of Confirmed, fly
two jumps, and you are still on row 6 unless there is no longer a row 6.

> ### Why this replaced the F-keys
>
> It was `F1`–`F10` for the sector table, `CTRL+F1`–`F10` for Confirmed, `ALT+F1`–`F10`
> for Adjacent sectors and `SHIFT+F1`–`F3` for carriers. Three things were wrong:
>
> 1. **`ALT+F4` is "close the foreground window" on Windows.** Registered with
>    `suppress=False`, the chord passed through after we handled it — so the fourth
>    adjacent sector would have copied a system name *and closed Elite*.
> 2. **A row's key changed under you.** Consume a sector's last candidate and it drops
>    out of the Adjacent list; everything below shifts up and `ALT+F2` now means
>    somewhere else. A cursor is immune — it is wherever you last put it.
> 3. **33 chords is 33 chances to collide with a game binding**, and it cost a
>    10-character `KEY` column to advertise them.

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

## Not wired yet
- `observations.jsonl` (the calibration-loop input), `outcomes.json`, `carrier_gone.json`
  — likewise unmigrated and not reproducible. See `CLEANUP.md`.
