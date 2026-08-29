"""ed_overlay -- sector-ranked rare-object HUD. Entry point and wiring only.

    python -m app.main

Everything it knows is split across siblings and this file just connects them:

    journal.py  where the commander is        (the only module that reads the journal)
    names.py    which sector that name means  (pure string parsing, no IO)
    store.py    what is in that sector        (the only module containing SQL)
    table.py    how the ten rows look         (the only module that lays out cells)
    overlay.py  the window they live in       (the only module that knows Tk chrome)
    theme.py    every colour and width        (the only module with literals)

    hotkeys.py  which key means which row     (the only module that hooks the keyboard)

FOUR TABLES AND ONE CURSOR. They stack from the top-left corner in descending
certainty: Confirmed (the game has already said it is there), Current sector (what might
be here), Adjacent sectors (what might be next door), Nearest parked carriers (where to
dock if none of it works out). PAGE UP/DOWN moves between them, UP/DOWN within one, and
whatever the cursor lands on is copied to the clipboard.

SHIFT+BACKSPACE is the one key that writes something: the selected system DOES NOT
EXIST -- the galaxy map refused to plot to it. That is the only negative evidence this
project can collect, so it is recorded rather than acted on and forgotten.
"""
import argparse
import datetime
import sys
import time

from . import clipboard, focus, journal, names, timing
from . import hotkeys as keys
from .hotkeys import Hotkeys
from .overlay import Overlay
from . import notify
from .store import (RARE_CLASSES, ROW_CATALOG, ROW_PREDICTED, ROW_SECTOR,
                    ROW_TOTAL, ROW_UNFOUND, Store)
from .table import TargetTable
from .theme import Fonts

TITLE = "::: sector rares :::"
SECTOR_TITLE = "Current sector"
CONFIRMED_TITLE = "Confirmed"
ADJACENT_TITLE = "Adjacent sectors"
CARRIER_TITLE = "Nearest carriers and neutron stars"
ROWS = 10
CARRIER_ROWS = 3
# Neutron stars share the carrier table: both are places to GO rather than things
# to find, and neither carries a prediction. Three of each.
NEUTRON_ROWS = 3
# Rows of the Current sector table given to system_unfound: real catalogued stars whose
# POSITION lands in this sector and which no game system matches. Three, because they
# are a different question from everything above them -- "is this system there at all"
# rather than "what is in it" -- and a long list of them would bury the predictions
# that are the point of the table. Only 43 sectors hold any at all, so the rows are
# blank almost everywhere and cost nothing when they are.
UNFOUND_ROWS = 3
# Summary lines under the Current sector table: SECTOR + its catalogued half, then
# REGION + its catalogued half. store.sector_totals() and region_totals() each return a
# PAIR, so this is 2 x 2 and not a number to be tuned.
SUMMARY_ROWS = 4
# The tick drives both the key poll and the journal poll. Keys need to feel instant, a
# journal read does not, so the tick is fast and the journal is rate-limited inside it.
KEY_POLL_MS = 120


class App:
    def __init__(self, args):
        self.args = args
        # Instrumentation is ALWAYS ON; --slow-ms sets the threshold at which a hitch
        # explains itself, not whether it is measured. See timing.py.
        self.timing = (timing.Phases(args.slow_ms) if args.slow_ms >= 0
                       else timing.NullPhases())
        self.store = Store(self.timing)
        self.reader = journal.JournalReader(args.journal_dir)
        fonts = Fonts(args.font)

        self.ui = Overlay(TITLE, fonts=fonts, opacity=args.opacity,
                          x=args.x, y=args.y, draggable=not args.fixed,
                          chrome=args.chrome)
        # Sector table first so the Confirmed table can be packed BEFORE it and stay
        # on top even after being hidden and re-shown. Both are TargetTables, so one
        # header renderer and one row renderer draw them.
        # ROWS + UNFOUND_ROWS + SUMMARY_ROWS. All three groups are appended after
        # the targets rather than pinned to the bottom of the grid, so each sits
        # directly under the last real row instead of behind a gap of blanks -- and in
        # the 8,700-odd sectors with no unfound star the summary simply moves up.
        #
        # FOUR summary lines, in two pairs: SECTOR then its catalogued half, REGION
        # then its catalogued half. Widening scale as the eye travels down, which is
        # the same order the four tables themselves are stacked in.
        self.table = TargetTable(self.ui.body,
                                 rows=ROWS + UNFOUND_ROWS + SUMMARY_ROWS, fonts=fonts,
                                 title=SECTOR_TITLE)
        self.confirmed = TargetTable(
            self.ui.body, rows=ROWS, fonts=fonts, title=CONFIRMED_TITLE,
            # Only rendered when it has rows: a Confirmed heading over an empty grid
            # would suggest there is nothing out there, when the usual truth is simply
            # that nothing has been revealed in THIS sector yet.
            hide_when_empty=True, before=self.table.container)
        self.confirmed.blank()
        # Carriers last: they are a fallback destination, not the reason you are out
        # here, so they sit under the predictions.
        self.carriers = TargetTable(
            self.ui.body, rows=CARRIER_ROWS + NEUTRON_ROWS, fonts=fonts,
            title=CARRIER_TITLE,
            # "CALLSIGN" is exactly 8 characters, which is the width store.py pads
            # the callsign to -- so the two words in this heading sit directly over the
            # two fields beneath them with no fiddling.
            hide_when_empty=True, wide_heading="CALLSIGN  CARRIER NAME")
        self.carriers.blank()
        # Adjacent sectors between the two, and built AFTER carriers purely so
        # `before` has something to point at: pack() appends, so this is the only way
        # to land it above a table that already exists. Reading order is
        # Confirmed -> Current sector -> Adjacent -> Carriers, which is descending
        # certainty: what is definitely there, what might be here, what might be next
        # door, and where to dock if none of it works out.
        self.adjacent = TargetTable(
            self.ui.body, rows=ROWS, fonts=fonts, title=ADJACENT_TITLE,
            hide_when_empty=True, before=self.carriers.container)
        self.adjacent.blank()
        # With no title bar the tables are the only thing on screen, so they have to be
        # the drag handle too. Done here and not in Overlay because the cells only
        # exist once the TargetTables have built them.
        self.ui.enable_drag_on(self.ui.body)

        self.system = None
        self.sector = None
        # True while the commander is in HAND-NAMED space, where `sector` is the
        # 'crafted' sentinel rather than a real sector. Kept as a flag because the
        # sentinel behaves like a sector in SQL and not at all like one in the sky: its
        # members are scattered across the whole galaxy, so its totals are galaxy-wide
        # and its "nearest POI" can be 39,000 ly away. The footer has to say so.
        self.crafted = False
        # Where the commander is. The Confirmed table is galaxy-wide and ordered by
        # distance from here, so this is not decoration -- without it that table can
        # only fall back to rarest-first.
        self.pos = None
        # The rows each key group addresses, in key order. Rebuilt by refresh(), so a
        # press always resolves against exactly what is on screen. Two lists, because
        # each table numbers its own rows from 1 -- F4 is the fourth prediction and
        # CTRL+F4 the fourth confirmed find, regardless of how long the other table is.
        # THE FOUR TABLES IN CURSOR ORDER, top to bottom on screen. PAGE UP/DOWN walks
        # this list and skips whatever is currently empty, so the cursor never lands on
        # a heading with nothing under it.
        self.tables = [(CONFIRMED_TITLE, self.confirmed), (SECTOR_TITLE, self.table),
                       (ADJACENT_TITLE, self.adjacent), (CARRIER_TITLE, self.carriers)]
        # The rows each table currently offers as DESTINATIONS, in display order.
        # Rebuilt by refresh(). Index into this is index into the grid, which is what
        # lets TargetTable.set_selected() take the same number -- true only because the
        # one non-destination row (the sector TOTAL) is appended LAST.
        self.rows = {name: [] for name, _t in self.tables}
        self.active = 0        # which table the cursor is in
        self.cursor = 0        # which row of it
        # The last thing actually put on the clipboard. None until the commander moves
        # the cursor, which is what stops the app grabbing the clipboard at startup.
        self.copied = None
        # Cached: see _read(). Only re-queried when the commander moves.
        self._carriers = None
        self.hotkeys = Hotkeys()
        self._last_poll = 0.0
        self._navroute_mtime = None
        # CACHED. The tick runs every couple of seconds and each database open costs
        # ~175 ms; re-counting four tables that only change when WE change them would
        # hold the file for a fifth of every tick and lock out the loaders. Refreshed
        # on startup and after each arrival, which is exactly when it can differ.
        # Empty when there is no status line to read them -- see recount().
        self._counts = {}
        self.recount()

    # -- event handling ------------------------------------------------------------
    def on_position(self, event, record=True):
        """A position event arrived. Record it, and refresh if the sector changed."""
        system, xyz, ts = journal.position_of(event)
        if not system:
            return
        self.system = system
        moved = xyz != self.pos and xyz[0] is not None
        if moved:
            self.pos = xyz

        if record:
            with self.timing.phase("record_arrival"):
                _new, poi = self.store.record_arrival(system, ts)
            self.recount()                          # a write moved them
            if poi:
                self.note(f"POI logged here: {poi}", "ok")

        # A hand-named system has no procedural sector, so it falls back to the
        # model's own sentinel rather than to nothing. That is what puts "SECTOR
        # crafted" on screen instead of a blank table -- the sentinel is a real row in
        # the sector table and every hand-named system points at it, so the summary
        # lines and the POI list have something to sum and something to list.
        sector = names.sector_of(system)
        self.crafted = sector is None
        if self.crafted:
            sector = names.CRAFTED_SECTOR
        # Refresh on a sector change OR on any move: the Confirmed table is ranked by
        # distance from here, so every jump reorders it even when the sector does not
        # change.
        if sector != self.sector or moved:
            self.sector = sector
            self.refresh()
        self.update_status()

    @staticmethod
    def _nearest(confirmed):
        """'962 ly' for the closest confirmed find, or why there is none."""
        if not confirmed:
            return "none"
        d = confirmed[0].get("dist_ly")
        return f"{d:,.0f} ly" if d is not None else "distance unknown"

    @staticmethod
    def _title(base, rows):
        """Table heading with its row count, flagging truncation explicitly.

        A grid that silently shows 10 of 19 reads as "there are 10", which is the same
        class of mistake as a query with an unstated LIMIT.

        The sector NAME is deliberately not here: the totals row already carries
        "<sector> TOTAL", and repeating it in the heading directly above spends a line
        of a HUD on something the eye has already read. Nor is a plain row count -- you
        can see how many rows there are by looking at them.

        What DOES belong here is truncation, because that is the one thing the rows
        cannot tell you: a grid silently showing 10 of 19 reads as "there are 10",
        which is the same class of mistake as a query with an unstated LIMIT.
        """
        if len(rows) > ROWS:
            return f"{base}   (showing {ROWS} of {len(rows)})"
        return base

    def note(self, text, role="dim"):
        """Say something. Goes to the footer when there is one, and to stdout when
        there is not -- a bare-table overlay must not swallow its own warnings."""
        self.ui.set_footer(text, role)
        if not self.ui.chrome:
            print(text, flush=True)

    def _read(self, moved):
        """Every query one repaint needs, in one place. Call inside store.batch().

        Confirmed first: anything in it is EXCLUDED from the sector table, so a certain
        find appears exactly once, in the table that says it is certain. It and the
        carrier and adjacent lists are GALAXY-WIDE and position-ranked, so they are
        fetched whether or not we are in procedurally-named space.
        """
        with self.timing.phase("q_confirmed"):
            confirmed = self.store.confirmed_targets(self.pos, limit=ROWS)
        # *** CARRIERS ONLY WHEN YOU HAVE ACTUALLY MOVED. *** At 1,311 ms this is the
        # most expensive read in a repaint -- it joins 88,663 carriers against the 197M
        # -row system_known with no index to help. And it CANNOT have changed unless the
        # commander moved: the reliable set is fixed between model rebuilds and the only
        # variable is distance from here. Plotting a route does not move you, so on a
        # reveal-driven refresh the cached rows are not stale, they are correct.
        if moved or self._carriers is None:
            # Carriers then neutrons, in ONE list for ONE table -- both answer "somewhere
            # to go that is not a gamble", and the cursor walks them as a single run.
            # Neutrons are cached on the same terms: they too depend only on position.
            with self.timing.phase("q_carriers"):
                car = self.store.carrier_targets(self.pos, limit=CARRIER_ROWS)
            with self.timing.phase("q_neutrons"):
                neu = self.store.neutron_targets(self.pos, limit=NEUTRON_ROWS)
            self._carriers = car + neu
        with self.timing.phase("q_adjacent"):
            adjacent = self.store.adjacent_sectors(self.sector, self.pos, limit=ROWS)
        if not self.sector:
            return confirmed, self._carriers, adjacent, [], [], [], [], (0, 0, 0)
        with self.timing.phase("q_top"):
            targets = self.store.top_targets(self.sector, ROWS, pos=self.pos)
        # Real catalogued stars whose position lands here. A 235-row table probed on
        # one indexed-in-practice column, so this is the cheapest read in the repaint;
        # it is separate from top_targets() because it answers a different question and
        # must never be blended into the prediction ranking.
        with self.timing.phase("q_unfound"):
            unfound = self.store.unfound_targets(self.sector, UNFOUND_ROWS,
                                                 pos=self.pos)
        # The totals PAIR summarises the WHOLE sector, not these ten rows -- expected
        # undiscovered objects of each type across every unvisited system in it, split
        # into the boxel-predicted and catalogued populations because the table above
        # lists both and one number covering only the first agreed with the list it sat
        # under in 53 of 8,790 sectors.
        with self.timing.phase("q_sector"):
            totals = self.store.sector_totals(self.sector)
        # And the same sums again over the whole REGION. Cheap next to q_sector rather
        # than free: it reads the same columns of the same table, which sector_totals()
        # has just pulled into the buffer pool, so it is a second pass over warm pages.
        with self.timing.phase("q_region"):
            region = self.store.region_totals(self.sector) or []
        return (confirmed, self._carriers, adjacent, targets, unfound, totals, region,
                self.store.sector_summary(self.sector))

    def refresh(self, moved=True):
        """Re-query and repaint. `moved` is False when only a REVEAL changed things."""
        with self.timing.span("refresh"):
            self._refresh(moved)

    def _refresh(self, moved):
        # ONE CONNECTION for every read -- six opens at 167 ms each was a full second
        # of the repaint, more than any single query in it. See Store.batch().
        with self.timing.phase("read"), self.store.batch():
            (confirmed, carriers, adjacent, targets, unfound,
             totals, region, summary) = self._read(moved)
        with self.timing.phase("paint"):
            self._paint(confirmed, carriers, adjacent, targets, unfound,
                        totals, region, summary)

    def _paint(self, confirmed, carriers, adjacent, targets, unfound,
               totals, region, summary):
        """Everything after the reads: fill the grids, move the cursor, say what
        happened. Split out ONLY so timing.py can price it separately from the SQL --
        the two have very different fixes and lumping them hid which was which."""
        self.carriers.show(carriers)
        self.confirmed.show(confirmed)
        self.adjacent.show(adjacent)
        self.confirmed.set_title(self._title(CONFIRMED_TITLE, confirmed))
        self.adjacent.set_title(self._title(ADJACENT_TITLE, adjacent))
        # Set BEFORE the hand-named early return below. All three of these tables are
        # position-ranked rather than sector-scoped, so they are on screen and
        # selectable even when there is no sector, and leaving their rows stale would
        # point the cursor at whatever was confirmed several jumps ago.
        self.rows[CONFIRMED_TITLE] = confirmed[:ROWS]
        self.rows[ADJACENT_TITLE] = adjacent
        self.rows[CARRIER_TITLE] = carriers

        if not self.sector:
            self.rows[SECTOR_TITLE] = []
            self.place_cursor()
            # No position yet -- the journal has not reported one. Not the same as
            # hand-named space, which now renders through the 'crafted' sentinel below.
            self.table.blank()
            self.note("waiting for a position from the journal", "warn")
            return

        # SECTOR, its catalogued half, REGION, its catalogued half -- ALL FOUR ALWAYS,
        # even with no targets above them and even when every sum is zero. They only
        # mean anything together: "41 of 1,387 are here" is the comparison, and a line
        # that disappears when its pool empties leaves the survivors looking as though
        # they disagree with something. An empty sector is the common case -- only
        # 2,874 of 8,741 hold a boxel prediction -- and that is exactly when the region
        # lines matter most, so it is the last moment to drop any of them.
        #
        # Both lists are empty only in hand-named space, which returns earlier anyway.
        # UNFOUND ROWS SIT BETWEEN THE TARGETS AND THE SUMMARY, and they are
        # DESTINATIONS -- the cursor walks onto them and copies the name, which for
        # these is the whole point: paste it into the galaxy map and if it resolves,
        # the row was stale and the star was there under its own name after all.
        self.table.show(targets + unfound + totals + region)
        # Both summary rows are excluded: you cannot fly to a sum. They are appended
        # after the targets, so every index here still matches its grid row.
        self.rows[SECTOR_TITLE] = [r for r in targets + unfound
                                   if r.get("row_grp") != ROW_TOTAL]
        self.place_cursor()
        self.table.set_title(self._title(SECTOR_TITLE, targets))
        total, visited, catalogued = summary
        if self.crafted:
            # *** THE SUMS AND DISTANCES HERE ARE GALAXY-WIDE, NOT LOCAL. *** Every
            # hand-named system in the game shares this one sentinel sector, so its
            # "sector total" is a total over all of them and its nearest POI may be tens
            # of thousands of light years away. The rows are real and the distances are
            # honest; it is the word SECTOR that is doing something unusual, so say so
            # rather than let the heading imply locality it does not have.
            self.note(
                f"{self.system} is hand-named -- no procedural sector. Showing the "
                f"'crafted' sentinel, which collects EVERY hand-named system in the "
                f"galaxy, so these totals and distances are galaxy-wide.", "warn")
        elif not targets:
            # Empty is the COMMON case now, not a fault: only 2,874 of 8,741 sectors
            # hold any boxel-predicted system. Say which kind of empty it is, or the
            # blank table reads as a broken overlay.
            if total == 0:
                why = (f"no boxel-predicted systems in {self.sector}"
                       + (f" ({catalogued:,} catalogued, excluded)" if catalogued
                          else ""))
            else:
                why = (f"all {total:,} predicted system(s) in {self.sector} "
                       f"already visited")
            # The unfound rows are still on screen and are still somewhere to go, so
            # "empty" would be wrong as well as discouraging.
            if unfound:
                why += (f" -- but {len(unfound)} catalogued star(s) should be here and "
                        f"cannot be found by name")
            self.note(why, "warn")
        else:
            # Say this out loud rather than let the columns imply more than they can.
            # The model fits every p per (mass_code, plane_r band) and a sector spans
            # one band, so these ten rows carry only a handful of distinct values and
            # the ordering is really by mass code, broken by expected body count.
            spread = {(t["p_bh"], t["p_wr"]) for t in targets}
            self.note(
                f"{self.sector}: {total:,} boxel-predicted, {visited:,} visited, "
                f"{catalogued:,} catalogued  |  {len(spread)} distinct BH/WR rate(s) "
                f"in the top {len(targets)}  |  nearest confirmed: "
                f"{self._nearest(confirmed)}")

    def recount(self):
        """Refresh the cached row counts -- but ONLY if anything will read them.

        They exist for the status line, and the status line only exists with --chrome,
        which is off by default and off in flight. Counting four tables opens its own
        session and cost 200 ms on EVERY reveal, to produce a number nothing was going
        to display -- a sixth of the whole plot-to-clipboard latency spent on invisible
        output.
        """
        if self.ui.status is not None:
            self._counts = self.store.counts()

    def update_status(self):
        """Repaint the status line from CACHED counts -- no database access.

        Returns immediately when there is no status line. set_status() is already a
        no-op in that case, but the f-string below is evaluated BEFORE the call and
        would raise KeyError on the empty dict recount() leaves behind.
        """
        if self.ui.status is None:
            return
        now = datetime.datetime.now().strftime("%H:%M")
        c = self._counts
        self.ui.set_status(
            f"{self.system or 'waiting for a jump'}   "
            f"seen {c['system_seen']:,} / visited {c['system_visited']:,} / "
            f"found {c['system_confirmed']:,}   {now}")

    # -- keys ------------------------------------------------------------------------
    def filled(self):
        """Indices of the tables that currently have something to select."""
        return [i for i, (name, _t) in enumerate(self.tables) if self.rows[name]]

    @staticmethod
    def target_of(row):
        """What a row would put on the clipboard. The ONE place that is decided.

        Adjacent sectors rows display a SECTOR but copy the best system inside it, so
        the displayed name and the copied name are different strings and only this one
        matters for "am I still pointing at the same place".
        """
        return row.get("copy_text") or row.get("system")

    def place_cursor(self, copy=False):
        """Clamp the cursor to something real, repaint the highlight, keep the
        clipboard honest.

        Called after ANY change to the rows -- a jump, a reveal, a keypress -- because
        all three can move, shorten or reorder the list the cursor is sitting in. Three
        things happen, in this order, and the order is the design:

        1. FOLLOW. If the system we last copied is still somewhere in the active table,
           the cursor moves to it. Rows reorder constantly -- Confirmed is sorted by
           distance, so every jump reshuffles it -- and a cursor pinned to an INDEX
           would drift off your chosen target while you fly toward it.

        2. CLAMP. Otherwise the cursor keeps its index, bounded by the list. Land on
           row 6 of Confirmed, fly two jumps, and you are still on row 6 unless there
           is no longer a row 6.

        3. RE-COPY IF THE TARGET IS GONE. *** This is what makes plotting a route feel
           finished. *** Plot to the best system in an adjacent sector, and the plot
           reveals its arrival class -- so the question it was asking is settled and it
           leaves the list. Step 1 finds nothing to follow, the cursor stays put, and
           whatever moved up into that slot is now under the cursor but NOT on the
           clipboard. Copying it here means the next paste into the galaxy map is the
           next candidate rather than the one you just did.

           Only when the copied target actually disappeared. A row that merely moved is
           handled by step 1, so ordinary flying never churns the clipboard.
        """
        live = self.filled()
        if not live:
            for _name, t in self.tables:
                t.set_selected(None)
            return
        if self.active not in live:
            self.active = live[0]
        name, _table = self.tables[self.active]
        rows = self.rows[name]
        if not copy and self.copied is not None:
            at = next((i for i, r in enumerate(rows)
                       if self.target_of(r) == self.copied), None)
            if at is not None:
                self.cursor = at
        self.cursor = max(0, min(self.cursor, len(rows) - 1))
        for i, (_n, t) in enumerate(self.tables):
            t.set_selected(self.cursor if i == self.active else None)
        now = self.target_of(rows[self.cursor]) if rows else None
        # `copied is not None` guards startup: the app must not seize the clipboard
        # before the commander has asked it for anything.
        if copy or (self.copied is not None and now != self.copied):
            self.copy_selected()

    def move(self, action):
        """Apply one navigation key. Every move copies what it lands on."""
        live = self.filled()
        if not live:
            self.note("nothing to select yet", "warn")
            return
        if action in (keys.NEXT_TABLE, keys.PREV_TABLE):
            step = 1 if action == keys.NEXT_TABLE else -1
            if self.active in live:
                nxt = live[(live.index(self.active) + step) % len(live)]
            else:
                nxt = live[0]
            self.active, self.cursor = nxt, 0
        else:
            name, _t = self.tables[self.active]
            n = len(self.rows[name])
            step = 1 if action == keys.NEXT_ROW else -1
            # WRAPS. Ten rows and no scrollbar -- running off the bottom and stopping
            # dead is worse than coming back to the top, which is one more press away
            # from anywhere.
            self.cursor = (self.cursor + step) % max(n, 1)
        self.place_cursor(copy=True)

    # Which row kinds SHIFT+BACKSPACE will accept, and what `source` it records.
    #
    # *** ONLY THE ROWS THAT ARE A GUESS. *** A prediction (boxel or catalogued
    # backfill), an adjacent sector's best system -- which is a prediction one sector
    # away -- and an unfound catalogue star. Everything else on screen is a place the
    # game has already told us exists: a confirmed find, a POI, a carrier, a neutron.
    # If one of those will not plot, the fault is a spelling or a stale dump and the
    # answer is to look at it, not to record a galaxy-wide absence.
    WRONG_SOURCE = {ROW_PREDICTED: "predicted", ROW_CATALOG: "predicted",
                    ROW_SECTOR: "predicted", ROW_UNFOUND: "unfound"}

    def mark_wrong(self):
        """SHIFT+BACKSPACE: the selected system does not exist. Record and re-read.

        Writes to system_wrong in the APP-STATE database and filters, rather than
        deleting from system_predicted or system_unfound -- see Store.mark_wrong() for
        why that is not merely the tidier of two options.
        """
        name, _t = self.tables[self.active]
        rows = self.rows[name]
        if not 0 <= self.cursor < len(rows):
            self.note("nothing selected to mark", "warn")
            return
        row = rows[self.cursor]
        source = self.WRONG_SOURCE.get(row.get("row_grp"))
        if source is None:
            self.note(f"{name} {self.cursor + 1} is not a prediction -- "
                      f"SHIFT+BACKSPACE only retires a guess", "warn")
            return
        # An Adjacent sectors row DISPLAYS a sector and OFFERS the best system in it,
        # so the thing being marked is what would have been pasted -- never the sector,
        # which certainly does exist.
        system = self.target_of(row)
        # WHICH SECTOR IT WAS OFFERED UNDER. An Adjacent row's SYSTEM cell IS a sector
        # name; every other row was offered under the one we are standing in. Passed
        # explicitly because an unfound star is named "HIP 29525" and no sector can be
        # parsed out of it -- that is exactly why system_unfound carries a sector at
        # all, and dropping it here would throw the same information away twice.
        sector = row["system"] if row.get("row_grp") == ROW_SECTOR else self.sector
        first = self.store.mark_wrong(system, source, sector=sector)
        self.recount()
        self.note(f"{system}: marked as not existing"
                  + ("" if first else " (already marked)"), "warn")
        # Re-read so it leaves the list now rather than at the next jump, and so the
        # cursor lands on the next candidate with it on the clipboard -- the same
        # "plotting a route feels finished" behaviour place_cursor() gives a settled
        # prediction.
        self.refresh(moved=False)

    def copy_selected(self):
        """Put the selected row's system name on the clipboard.

        Copying, and nothing else. Pasting into the galaxy map search is the one step
        the game gives no other way to automate. Marking a target visited is the
        JOURNAL's job -- it happens when you arrive, not when you decide to go.

        WHAT IS COPIED IS NOT ALWAYS WHAT IS SHOWN. An Adjacent sectors row displays a
        SECTOR, which the galaxy map's search box will not accept, so those rows carry
        `copy_text`: the best system inside that sector. Every other row copies the name
        in its SYSTEM column.
        """
        name, _t = self.tables[self.active]
        rows = self.rows[name]
        if not 0 <= self.cursor < len(rows):
            return
        row = rows[self.cursor]
        text = self.target_of(row)
        what = text if text == row["system"] else f"{text}  (best in {row['system']})"
        if clipboard.copy(text, self.ui.root):
            # Remembered so place_cursor() can tell "my target moved" from "my target
            # is gone" -- the two need opposite responses.
            self.copied = text
            self.note(f"{name} {self.cursor + 1}: copied {what}", "ok")
        else:
            self.note(f"could not reach the clipboard ({what})", "warn")

    def poll_navroute(self):
        """Harvest the plotted route ON ITS OWN. Startup only -- the tick inlines this
        so the route hops and the journal reveals share one write.

        Every hop, not just the destination.

        A plot is the richest single event this app sees: NavRoute.json is rewritten
        with the arrival StarClass AND exact StarPos of EVERY system on the route, so
        one plot across the galaxy can confirm dozens of systems at once. Taking only
        the destination -- which is what "where am I going" would suggest -- would
        throw away almost all of it.
        """
        rows, self._navroute_mtime = journal.read_navroute(
            self.args.journal_dir, self._navroute_mtime)
        if rows:
            self.record_revealed(rows, note=f"route plotted: {len(rows)} hop(s)")

    def record_revealed(self, rows, note=None):
        """Write revealed arrival classes and repaint if anything actually changed.

        A reveal moves a system one way or the other: rare, and it appears in
        Confirmed; ordinary, and it drops out of the sector table because the question
        it was asking has been answered. Either way the display is now stale.
        """
        if not rows:
            return
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds")
        # ONE SESSION FOR THE WRITE AND THE REPAINT THAT FOLLOWS IT. Opening a session
        # and attaching the 60 GiB model costs ~160 ms, detaching it another ~85 ms, and
        # this path used to pay that twice -- once to record the reveal, once to re-read
        # what it changed. batch() nests, so refresh()'s own read batch reuses this one.
        # read_only=False because record_seen writes; the reads inside are unaffected.
        with self.timing.span("reveal"), self.store.batch(read_only=False):
            with self.timing.phase("record_seen"):
                new = self.store.record_seen(rows, stamp)
            with self.timing.phase("recount"):
                self.recount()

            # Rares GALAXY-WIDE, not just this sector -- the Confirmed table stopped
            # being sector-scoped, so a black hole revealed 15,000 ly away still
            # belongs on screen and still deserves saying out loud.
            finds = [(n, c) for n, c, *_ in rows if c in RARE_CLASSES]
            if new or finds:
                # moved=False: a reveal changes what is worth flying to, never where you
                # are, so the carrier and neutron lists cannot have shifted.
                self.refresh(moved=False)
        if finds:
            what = ", ".join(f"{n} [{c}]" for n, c in finds[:3])
            more = f" (+{len(finds) - 3})" if len(finds) > 3 else ""
            self.note(f"CONFIRMED {len(finds)} rare -- {what}{more}", "ok")
            # *** ANY rare class, not just BH and WR. *** `finds` is already filtered on
            # RARE_CLASSES, which is every class the Confirmed table can show -- neutron,
            # white dwarf, Herbig, O-type and the supergiants included. A confirmation is
            # the one moment this tool has something to say that the game does not, so it
            # says it twice: the row flashes, and a chime plays.
            #
            # AFTER refresh(), never before. The flash addresses rows that only exist
            # once the repaint above has put them on screen.
            self.confirmed.flash([n for n, _ in finds])
            notify.chime(enabled=not self.args.no_sound)
        elif note:
            self.note(f"{note}, {new} new", "dim")

    def check_focus(self):
        """Hide the HUD unless Elite -- or this window -- has the foreground."""
        if self.args.always_visible:
            return
        self.ui.set_visible(focus.is_foreground())

    def tick(self):
        with self.timing.span("tick"):
            self._tick()

    def _tick(self):
        with self.timing.phase("focus"):
            self.check_focus()
        # Hand the model back when nothing has needed it for a while, so etl/ can write
        # it without the overlay being stopped. Costs a monotonic() read per tick.
        self.store.release_if_idle(self.args.model_idle)
        # *** GATED ON FOCUS, AND THAT IS NOT OPTIONAL. *** The navigation keys are the
        # ARROWS and PAGE UP/DOWN, hooked globally because the overlay never holds
        # focus. Ungated, every arrow press anywhere on the machine -- an editor, a
        # browser, a file rename -- would move the cursor and overwrite the clipboard.
        # is_foreground() is true for Elite or for this window, which is exactly when a
        # press could have been meant for us.
        # THE WRITE KEY FIRST, and on its own slot -- see Hotkeys.take_wrong(). Gated
        # on focus for the same reason as the arrows, and more so: SHIFT+BACKSPACE is a
        # perfectly ordinary chord in a text field, and an ungated hook would record a
        # galaxy-wide absence every time the commander deleted a word somewhere else.
        if self.hotkeys.take_wrong() and focus.is_foreground():
            with self.timing.phase("key_wrong"):
                self.mark_wrong()
        pressed = self.hotkeys.take()
        if pressed is not None and focus.is_foreground():
            with self.timing.phase("key"):
                self.move(pressed)
        # EVERY TICK, not on the --poll timer. read_navroute() is gated on the file's
        # mtime and costs 0.016 ms when nothing has changed -- a bare os.path.getmtime.
        # Rate-limiting it alongside the journal read was lumping a free check in with
        # an expensive one, and it put up to 2 SECONDS between plotting a route and the
        # clipboard catching up. That was the single largest part of the lag.
        # *** ONE record_revealed PER TICK, NOT TWO. *** The route file and the journal
        # both reveal arrival classes, and each used to be written separately -- two
        # sessions, two writes, two repaints, for one tick's worth of news. Measured at
        # 731 ms of record_seen alone. They are the same kind of fact, so they go in
        # together and the tick pays for one of everything.
        with self.timing.phase("navroute"):
            hops, self._navroute_mtime = journal.read_navroute(
                self.args.journal_dir, self._navroute_mtime)
        rows = list(hops or [])
        note = f"route plotted: {len(hops)} hop(s)" if hops else None
        events = []
        now = time.monotonic()
        if now - self._last_poll >= self.args.poll:
            self._last_poll = now
            with self.timing.phase("journal"):
                events = self.reader.poll()
            rows += [(n, c, None, None, None)
                     for n, c in (journal.class_of(e) for e in events
                                  if e.get("event") in journal.CLASS_EVENTS) if n and c]
        self.record_revealed(rows, note=note)
        for e in events:
            if e.get("event") in journal.POS_EVENTS:
                self.on_position(e)
        if events:
            with self.timing.phase("status"):
                self.update_status()

    # -- lifecycle -------------------------------------------------------------------
    def run(self):
        # Everything the current session already revealed, before the tail starts.
        harvested = self.reader.harvest_classes()
        if harvested:
            n = self.store.record_seen(
                [(nm, cl, None, None, None) for nm, cl in harvested])
            self.recount()
            print(f"harvested {len(harvested)} revealed class(es) from the journal, "
                  f"{n} new", flush=True)
        self.poll_navroute()
        primed = self.reader.prime()
        if primed:
            # Do not record a visit on startup: the priming event is usually the
            # `Location` written when the game loaded, which may be hours old. Writing
            # it would stamp last_visited_utc with the time the OVERLAY started rather
            # than the time the commander arrived.
            self.on_position(primed, record=False)
        else:
            self.table.blank()
            self.note(
                f"no Journal.*.log in {self.args.journal_dir} -- "
                f"is Elite installed and has it run?", "warn")
            self.update_status()
        self.register_hotkeys()
        # Built once: the keys do not change while the app runs. Composed from the
        # BINDINGS themselves, so the hint and the registered key cannot disagree.
        self.ui.set_help(keys.help_segments(self.hotkeys.bindings))
        self.check_focus()
        # The key poll rides the same tick as the journal poll, but a keypress must
        # feel immediate -- two seconds of lag on a copy is unusable -- so the tick
        # runs fast and the journal is only actually re-read every --poll seconds.
        self.ui.every(KEY_POLL_MS, self.tick)
        self.ui.run()

    def register_hotkeys(self):
        if self.args.no_hotkeys:
            print("hotkeys disabled (--no-hotkeys)", flush=True)
            return
        ok, failed = self.hotkeys.register()
        if ok:
            for line in self.hotkeys.describe():
                print(f"hotkeys: {line}", flush=True)
        for f in failed:
            print(f"hotkey FAILED {f}", flush=True)
        if failed and not ok:
            self.note("no hotkeys -- the table still works", "warn")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="app",
        description="Top-10 rare-object predictions in the CURRENT SECTOR.")
    p.add_argument("--journal-dir", default=journal.DEFAULT_JOURNAL_DIR,
                   help="Elite's saved-games directory")
    p.add_argument("--x", type=int, default=None,
                   help="window x (default: pinned to the left screen edge)")
    p.add_argument("--y", type=int, default=None,
                   help="window y (default: pinned to the top screen edge)")
    p.add_argument("--font", type=int, default=11, help="base font size (default 11)")
    p.add_argument("--opacity", type=float, default=0.85,
                   help="0.0-1.0 window opacity (default 0.85)")
    p.add_argument("--poll", type=float, default=2.0,
                   help="seconds between journal polls (default 2)")
    p.add_argument("--model-idle", type=float, default=30.0, metavar="SECONDS",
                   help="release the read-only hold on the model database after this "
                        "many idle seconds, so etl/ can write it (default 30)")
    p.add_argument("--slow-ms", type=int, default=250, metavar="MS",
                   help="log a breakdown for any tick slower than this (default 250; "
                        "0 logs every tick, -1 switches timing off)")
    p.add_argument("--no-sound", action="store_true",
                   help="never play the confirm chime (the flash still runs)")
    p.add_argument("--no-hotkeys", action="store_true",
                   help="do not register the global navigation keys")
    p.add_argument("--always-visible", action="store_true",
                   help="do not hide the overlay when Elite loses focus")
    p.add_argument("--chrome", action="store_true",
                   help="show the title bar, status line and footer "
                        "(default: table only)")
    p.add_argument("--fixed", action="store_true",
                   help="do not allow dragging the window")
    p.add_argument("--sector", default=None,
                   help="show this sector and ignore the journal (for testing)")
    return p.parse_args(argv)


def main(argv=None):
    # stdout is where note() reports when the chrome is hidden, and on Windows a
    # REDIRECTED stdout defaults to cp1252 -- which raises on the first character
    # outside it. A window title or a sector name is enough to kill the app that way,
    # so widen it before anything can print.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    args = parse_args(argv)
    app = App(args)
    if args.sector:
        app.sector = args.sector
        app.system = f"(forced: {args.sector})"
        app.refresh()
        app.update_status()
        app.ui.run()
    else:
        app.run()


if __name__ == "__main__":
    main()
