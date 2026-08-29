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
| `He GIANT` | Helium-rich gas giant — the one *planet* class that is predictable at all. |

Every probability is a **two-decimal fraction** (`0.38`), right-aligned, each shown
separately and **colour-coded on a 10-step red→orange→yellow→green ramp**. The scale is
linear over `0.05`–`0.60`, fixed rather than stretched per sector, so the same number is
always the same colour. It was measured, not guessed: across all eight columns, values
above the threshold have median `0.148`, p99 `0.538`, max `0.626`. Most cells therefore
land red or orange — because most predictions really are unlikely — and green stays rare
enough to mean something.

A `-` (below `0.05`) is uniformly dim in every column, so the eye skips straight to the
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
| `is_catalog = TRUE` | 2,207,261 | **Excluded.** Catalogued: in the dumps with exact coordinates, merely not detail-scanned. |
| `is_catalog = FALSE` | 61,763 | **Shown.** Boxel-predicted: in no dump at all, its existence inferred from a gap in the Stellar Forge's index. |

That is a 36× reduction, and it has consequences worth knowing before you fly:

- **Only 2,874 of 8,741 sectors** hold any predicted system, so an empty table is the
  normal case. The overlay says which kind of empty it is.
- **No mass code `e`.** The predicted pool is f (14,115), g (15,396) and h (32,252).
- **Coordinates are the boxel centroid**, up to 1280 ly across — you can arrive at the
  exact point and find nothing there.
- The layer is thin and core-biased; it is a lower bound, not a census.

**At least 5% on one rare.** A system must offer `≥ 0.05` on at least one of `BH`, `WR`,
`HERBIG`, `SUPERGNT`, `O-TYPE` — per column, never summed. `NEUTRON` and `WHT DWRF` are excluded from the
test despite being displayed (both sit near their base rate everywhere, so including
them would pass everything), as is `He GIANT`, which is a planet class and is hard-gated to
zero exactly where the rare stars are.

> **This bar currently removes nothing.** The weakest boxel-predicted system in the
> galaxy still offers **0.157** on its best rare, so all 61,763 clear 0.05. It is a
> guard for later, not a working filter today. Raising it to ~0.40 would start to bite.

Already-**visited** systems are excluded. Already-**seen** ones are not: seeing a system
on the galaxy map reveals only its arrival star, so a non-rare class still leaves the
rest of the system worth a look.

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
pool is identical too — boxel-predicted, not catalogued, not visited — or the
comparison would be between two different things.

**Distance is to the sector centroid and is approximate**, marked with a leading `~`.
A sector's bounding ball has a median radius of 1,727 ly while neighbouring centroids
sit about 1,280 ly apart, so the balls overlap heavily and the nearest centroid is not
always the nearest system.

Only sectors that **have** something appear: just 2,874 of 12,065 sectors hold any
boxel prediction, so the ten nearest outright would usually be ten rows of zeroes. This
table is at its most useful exactly where the sector table is empty, which is common.

### What an Adjacent row copies

The **best system in that sector**, by `store.RANK_BY` — `greatest(p_bh, p_wr)`, the
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

## Unfound catalogue stars

Under the predictions, up to three rows from `system_unfound`: **real catalogued stars
— HIP, GJ, HR — whose position falls in this sector and which no game system can be
matched to**, by name or by any cross-identification the alias bridge holds. 235 of them
galaxy-wide, across 43 sectors, so these rows are blank almost everywhere.

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
300% on the FSD. Primary *is* arrival, so you drop out of witchspace next to it and
supercruise nowhere.

**Deliberately not filtered against `system_visited` or `is_known`.** Everything else on
this overlay is about finding what nobody has found; a neutron is about *getting*
somewhere. The boost works exactly as well the second time you use it, and whether or
not somebody else logged the star first. Filtering it the way Confirmed is filtered
would hide the nearest boost *because you had already used it*.

Callsign and carrier name are blank — a dash — since a neutron has neither.

Reads `main.system_neutron`, materialised for this: 3.4M rows instead of scanning
197.6M, and 232 ms inside a batched refresh.

## Confirming a rare says so twice

A confirmation is the one moment this tool has something to say that the game does not,
so it is announced on two channels at once — and for **every** rare class the Confirmed
table can show, not just black holes and Wolf-Rayets: neutron, white dwarf, Herbig,
O-type and the supergiants all trigger it. The trigger set is `store.RARE_CLASSES`, so
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

Every prediction the table shows can be confirmed this way **except `He GIANT`** — a
helium-rich gas giant is a planet, and a route plot only ever reveals the arrival star:

| | classes matched |
| --- | --- |
| `BH` | `H`, `SupermassiveBlackHole`, `SuperMassiveBlackHole` |
| `WR` | `W` `WN` `WNC` `WC` `WO` |
| `SUPERGNT` | the five `*SuperGiant` codes |
| `HERBIG` | `AeBe` |
| `O-TYPE` | `O` |
| `NEUTRON` | `N` |
| `WHT DWRF` | the fifteen `D*` codes |

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
> bound (50,212 galaxy-wide, heavily core-biased). Filtering on "must also be predicted"
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

Writes go to `../elite_mapping_v2_current.duckdb` and **nowhere else**. The model
database is attached `READ_ONLY`, so an accidental write raises instead of landing —
it is derived and fully rebuilt by `etl/`, so anything written there would be silently
erased by the next merge. Rationale in `ETL.md` §0.

On arrival the app writes `system_visited`, and `poi_visited` if the model knows the
system holds a point of interest. Both are idempotent, so a replayed journal event
cannot double-count.

### Connections are short-lived, on purpose

DuckDB lets **one process** hold a database file. An overlay that kept the app-state
database open would lock out every loader and every read — you could not inspect your
own flight log while flying. So the file is opened per operation and closed at once:
~175 ms for open + attach model + query + close, nothing against a jump every thirty
seconds. The two-second UI tick touches **no** database at all (row counts are cached
and refreshed only when the app itself changes them), so the file is free essentially
always and `python etl/load_system_seen.py` runs happily mid-flight.

### All presentation is SQL

Every string the table shows — the `F1` label, `Mass H`, the percentages, the thousands
separators — is produced by the query, not by Python. `store.top_targets()` returns
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
| `theme.py` | every colour, font, column width | data, Tk widgets |
| `names.py` | parsing `Blaa Hypai BA-A g5` → sector, mass code | IO, database |
| `journal.py` | finding, tailing and rolling over `Journal.*.log` | what an event *means* |
| `store.py` | **all** SQL, both databases | Tk, the journal |
| `table.py` | laying out the 10×7 grid | SQL, ranking, formatting |
| `overlay.py` | frameless/topmost/drag/placement | what is inside it |
| `main.py` | wiring the above together | any of their internals |

Two rules that keep it that way: `store.top_targets()` returns **display-ready
strings**, so `table.py` places text rather than computing it; and `theme.COLUMNS` is
**one** list driving both the header and the cells, so the two cannot drift.

The table is **refilled, not rebuilt** — labels are created once and only their text
changes, because destroying and recreating them every jump flickers and leaks Tk
objects.

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
