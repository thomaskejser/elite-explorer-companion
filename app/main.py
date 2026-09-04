"""ed_overlay -- sector-ranked rare-object HUD. Entry point and wiring only.

    python -m app.main

Everything it knows is split across siblings and this file just connects them:

    journal.py  where the commander is        (the only module that reads the journal)
    names.py    which sector that name means  (pure string parsing, no IO)
    database.py    what is in that sector        (the only module containing SQL)
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
import math
import sys
import time

from . import clipboard, focus, journal, names, route, ship, timing
from . import hotkeys as keys
from .hotkeys import Hotkeys
from .dbworker import Ask, DbWorker, Ref
from .overlay import Overlay
from . import notify
from .database import (CHIME_CLASSES, CHIME_IF_PREDICTED, P_NONE, RARE_CLASSES, ROW_CATALOG,
                    ROW_NEUTRON, ROW_PREDICTED, ROW_SECTOR, ROW_TOTAL, ROW_UNFOUND,
                    Database)
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
# ask a different question from everything above them -- "is this system there at all"
# rather than "what is in it" -- and a long list would bury the predictions the table
# is for. Only 43 sectors hold any, so the rows are usually blank.
UNFOUND_ROWS = 3
# Summary lines under the Current sector table: SECTOR + its catalogued half, then
# REGION + its catalogued half. database.sector_totals() and region_totals() each
# return a PAIR, so this is 2 x 2 and not a number to be tuned.
SUMMARY_ROWS = 4
# The tick drives both the key poll and the journal poll. Keys need to feel instant, a
# journal read does not, so the tick is fast and the journal is rate-limited inside it.
KEY_POLL_MS = 120


def _db_out(line):
    """Worker breakdowns, marked so the two threads' timings cannot be confused."""
    print(f"[db] {line}", flush=True)


class App:
    def __init__(self, args):
        self.args = args
        # Instrumentation is ALWAYS ON; --slow-ms sets the threshold at which a hitch
        # explains itself, not whether it is measured. See timing.py.
        self.timing = (timing.Phases(args.slow_ms) if args.slow_ms >= 0
                       else timing.NullPhases())
        # ITS OWN Phases, NOT self.timing. A phase recorded on the worker would
        # otherwise land inside whatever span the Tk thread had open, and the breakdown
        # would stop adding up -- which is exactly what the instrumentation is for.
        self.db_timing = (timing.Phases(args.slow_ms, out=_db_out) if args.slow_ms >= 0
                          else timing.NullPhases())
        self.db = Database(self.db_timing)
        # THE DATABASE RUNS ON ITS OWN THREAD. Started in run(), after the synchronous
        # startup work, so that work still runs here and owns its own sessions.
        self.worker = DbWorker(self.db, args.model_idle)
        self._req = 0
        self._pending = {}          # req_id -> callback, run on THIS thread
        self._keyed = {}            # coalescing group -> its latest req_id
        self.reader = journal.JournalReader(args.journal_dir)
        fonts = Fonts(args.font)

        self.ui = Overlay(TITLE, fonts=fonts, opacity=args.opacity,
                          x=args.x, y=args.y, draggable=not args.fixed,
                          chrome=args.chrome)
        # Sector table first so the Confirmed table can be packed BEFORE it and stay
        # on top even after being hidden and re-shown.
        #
        # ROWS + UNFOUND_ROWS + SUMMARY_ROWS: all three groups are appended after the
        # targets rather than pinned to the bottom of the grid, so each sits directly
        # under the last real row instead of behind a gap of blanks -- and in a sector
        # with no unfound star the summary simply moves up.
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
            # "CALLSIGN" is exactly 8 characters, which is the width database.py pads
            # the callsign to -- so the two words in this heading sit directly over the
            # two fields beneath them with no fiddling.
            hide_when_empty=True, wide_heading="CALLSIGN  CARRIER NAME")
        self.carriers.blank()
        # Adjacent sectors between the two, and built AFTER carriers purely so
        # `before` has something to point at: pack() appends, so this is the only way
        # to land it above a table that already exists.
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
        # TWO CACHES, NOT ONE COMBINED LIST. Both halves of that table depend only
        # on position, but the route replaces the NEUTRON half by itself and
        # leaves the carriers alone -- and re-querying carriers is the single
        # most expensive read in a repaint. Split, a route plot costs neither.
        self._carrier_rows = None
        self._neutron_rows = None
        # NEUTRON JUMP MODE. `route` is the hops STILL AHEAD, nearest first, in the
        # shared row shape; `route_dest` is where it ends. Both None when the mode is
        # off, and that one test gates the display, the arrival copy, and what the next
        # SHIFT+N means.
        #
        # IN MEMORY ONLY, deliberately. The app-state database records what the
        # COMMANDER has seen, visited and found -- durable facts. A route is a plan: the
        # next plot invalidates it and one keypress rebuilds it. Restarting drops it.
        self.route = None
        self.route_dest = None
        # Full-tank range, computed once at startup. None if the drive is unknown, in
        # which case SHIFT+N refuses rather than guessing how far you can jump.
        self.jump_range = None
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

    # -- the database, off this thread ----------------------------------------------
    def ask(self, asks, then, write=False, key=None):
        """Queue database work; run `then(results)` on the Tk thread when it lands.

        `key` coalesces: submitting again under the same key drops the older request if
        it has not started, because its inputs are stale. NEVER pass a key for a write.
        """
        self._req += 1
        if key is not None:
            self._pending.pop(self._keyed.get(key), None)
            self._keyed[key] = self._req
        self._pending[self._req] = then
        self.worker.submit(self._req, asks, write=write, key=key)

    def drain_db(self):
        """Hand every finished request to its callback. Called first in every tick."""
        for req_id, payload in self.worker.drain():
            then = self._pending.pop(req_id, None)
            if then is None:
                continue                        # superseded while it was in flight
            if isinstance(payload, Exception):
                self.note(f"database error: {type(payload).__name__}: {payload}", "warn")
                continue
            with self.timing.phase("db_result"):
                then(payload)

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

        # BEFORE the refresh below, so the repaint it triggers already shows the
        # shortened route rather than painting the old one and correcting it a frame
        # later. Silent and harmless when the mode is off.
        if record:
            self.advance_route(system)

        if record:
            self.ask([Ask("record_arrival", (system, ts))], self._arrived, write=True)

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

    def _arrived(self, r):
        """The arrival write landed. Its only visible product is the POI note."""
        _new, poi = r["record_arrival"]
        self.recount()                              # a write moved them
        if poi:
            self.note(f"POI logged here: {poi}", "ok")

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

        Truncation is the one thing the rows cannot tell you: a grid silently showing
        10 of 19 reads as "there are 10", which is the same class of mistake as a query
        with an unstated LIMIT. The sector name and a plain row count are left out --
        the summary line below carries the first and the rows themselves the second.
        """
        if len(rows) > ROWS:
            return f"{base}   (showing {ROWS} of {len(rows)})"
        return base

    def note(self, text, role="dim"):
        """Say something. Footer when there is one, stdout when there is not -- a
        bare-table overlay must not swallow its own warnings. Phased because without
        --chrome it PRINTS, which is a syscall on the drawing thread."""
        with self.timing.phase("p_note"):
            self.ui.set_footer(text, role)
            if not self.ui.chrome:
                print(text, flush=True)

    def _read_asks(self, moved):
        """Every query one repaint needs, as Asks. Call order is the order they run.

        Confirmed first: anything in it is EXCLUDED from the sector table, so a certain
        find appears exactly once. It and the carrier and adjacent lists are GALAXY-WIDE
        and position-ranked, so they are fetched whether or not the sector is procedural.

        *** CARRIERS AND NEUTRONS ONLY WHEN YOU HAVE ACTUALLY MOVED. *** Neither can
        have changed otherwise -- the reliable set is fixed between model rebuilds and
        the only variable is distance from here. Plotting a route does not move you.
        """
        asks = [Ask("confirmed_targets", (self.pos,), {"limit": ROWS})]
        if moved or self._carrier_rows is None:
            asks.append(Ask("carrier_targets", (self.pos,), {"limit": CARRIER_ROWS}))
        if moved or self._neutron_rows is None:
            asks.append(Ask("neutron_targets", (self.pos,), {"limit": NEUTRON_ROWS}))
        asks.append(Ask("adjacent_sectors", (self.sector, self.pos), {"limit": ROWS}))
        if self.sector:
            asks += [
                Ask("top_targets", (self.sector, ROWS), {"pos": self.pos}),
                Ask("unfound_targets", (self.sector, UNFOUND_ROWS), {"pos": self.pos}),
                # The totals PAIR summarises the WHOLE sector, not these ten rows, split
                # into the boxel-predicted and catalogued populations. region_totals is
                # a second pass over pages sector_totals just warmed.
                Ask("sector_totals", (self.sector,)),
                Ask("region_totals", (self.sector,)),
                Ask("sector_summary", (self.sector,)),
            ]
        return asks

    def refresh(self, moved=True):
        """Ask for everything a repaint needs. Paints on a later tick, not now."""
        sector = self.sector
        self.ask(self._read_asks(moved),
                 lambda r: self._paint_from(r, sector), key="refresh")

    def _paint_from(self, r, sector):
        """Unpack a result set and paint it. Drops a result the world has outrun."""
        if sector != self.sector:
            return
        # Cached, not re-read, when the commander has not moved -- see _read_asks().
        if "carrier_targets" in r:
            self._carrier_rows = r["carrier_targets"]
        if "neutron_targets" in r:
            self._neutron_rows = r["neutron_targets"]
        # THE ROUTE REPLACES THE NEUTRON HALF, AND ONLY THAT HALF: those three rows
        # answer "where is the nearest cone", and while a route is up the useful
        # question is "which cones are next". The carriers answer something else.
        carriers = self._carrier_rows + (self.route[:NEUTRON_ROWS]
                                         if self.route is not None
                                         else self._neutron_rows)
        with self.timing.phase("paint"):
            self._paint(r["confirmed_targets"], carriers, r["adjacent_sectors"],
                        r.get("top_targets", []), r.get("unfound_targets", []),
                        r.get("sector_totals", []), r.get("region_totals") or [],
                        r.get("sector_summary", (0, 0, 0, 0)))

    def _paint(self, confirmed, carriers, adjacent, targets, unfound,
               totals, region, summary):
        """Everything after the reads: fill the grids, move the cursor, say what
        happened. Split out so timing.py can price it separately from the SQL, which
        has very different fixes."""
        # PHASED PER GRID. The expensive paint is the FIRST one -- Tk realising the
        # window when a hide_when_empty container is first packed, ~91 ms against ~10
        # in steady state. p_cursor is separate because it reaches the WIN32 CLIPBOARD.
        with self.timing.phase("p_carriers"):
            self.carriers.show(carriers)
            # The heading says which of its two jobs the table is doing. Retitled on
            # every repaint because the count in it changes with every hop flown.
            self.carriers.set_title(
                f"Neutron route -> {self.route_dest}   ({len(self.route)} jump(s) left)"
                if self.route is not None else CARRIER_TITLE)
        with self.timing.phase("p_confirmed"):
            self.confirmed.show(confirmed)
            self.confirmed.set_title(self._title(CONFIRMED_TITLE, confirmed))
        with self.timing.phase("p_adjacent"):
            self.adjacent.show(adjacent)
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
            with self.timing.phase("p_cursor"):
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
        # 2,874 of 8,741 hold a boxel prediction -- and that is when the region lines
        # matter most.
        #
        # UNFOUND ROWS SIT BETWEEN THE TARGETS AND THE SUMMARY, and they are
        # DESTINATIONS -- the cursor walks onto them and copies the name, which for
        # these is the whole point: paste it into the galaxy map and if it resolves,
        # the row was stale and the star was there under its own name after all.
        with self.timing.phase("p_sector"):
            self.table.show(targets + unfound + totals + region)
        # Both summary rows are excluded: you cannot fly to a sum. They are appended
        # after the targets, so every index here still matches its grid row.
        self.rows[SECTOR_TITLE] = [r for r in targets + unfound
                                   if r.get("row_grp") != ROW_TOTAL]
        with self.timing.phase("p_cursor"):
            self.place_cursor()
        self.table.set_title(self._title(SECTOR_TITLE, targets))
        total, visited, settled, catalogued = summary
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
            # Empty is the COMMON case, not a fault: only 2,874 of 8,741 sectors
            # hold any boxel-predicted system. Say which kind of empty it is, or the
            # blank table reads as a broken overlay.
            if total == 0:
                why = (f"no boxel-predicted systems in {self.sector}"
                       + (f" ({catalogued:,} catalogued, excluded)" if catalogued
                          else ""))
            else:
                # *** VISITED AND SETTLED ARE DIFFERENT CLAIMS. *** A settled
                # prediction was answered by a route plot or an FSDTarget handing over
                # the arrival class, with no trip involved, so folding it into
                # "already visited" would claim a journey that never happened.
                gone = " and ".join(
                    p for p in (f"{visited:,} visited" if visited else "",
                                f"{settled:,} already classed" if settled else "") if p)
                # No visits and no reveals leaves the other two exclusions the table
                # applies: a confirmed find, or a system the game refused to plot to.
                why = (f"all {total:,} predicted system(s) in {self.sector} "
                       f"settled -- {gone}" if gone else
                       f"the {total:,} predicted system(s) in {self.sector} are all "
                       f"confirmed or marked wrong")
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
                f"{settled:,} already classed, "
                f"{catalogued:,} catalogued  |  {len(spread)} distinct BH/WR rate(s) "
                f"in the top {len(targets)}  |  nearest confirmed: "
                f"{self._nearest(confirmed)}")

    def recount(self):
        """Refresh the cached row counts -- but ONLY if anything will read them.

        They exist for the status line, and the status line only exists with --chrome,
        which is off by default and off in flight. Counting four tables costs ~200 ms
        per reveal, which is not worth spending on a number nothing will display.
        """
        if self.ui.status is not None:
            self.ask([Ask("counts")], self._counted, key="counts")

    def _counted(self, r):
        self._counts = r["counts"]
        self.update_status()

    def update_status(self):
        """Repaint the status line from CACHED counts -- no database access."""
        if self.ui.status is None:
            return
        now = datetime.datetime.now().strftime("%H:%M")
        # .get, not [] -- the counts arrive from the worker a tick or two after startup,
        # and a status line is not worth a KeyError.
        c = self._counts
        self.ui.set_status(
            f"{self.system or 'waiting for a jump'}   "
            f"seen {c.get('system_seen', 0):,} / "
            f"visited {c.get('system_visited', 0):,} / "
            f"found {c.get('system_confirmed', 0):,}   {now}")

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
        deleting from system_predicted or system_unfound -- see Database.mark_wrong().
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
        # FIRST, and with no query: SHIFT+BACKSPACE is pressed WITH the galaxy map
        # open, having just been refused the route, so the next name to paste is what
        # is wanted now. A marked system is retired from one more kind of row than a
        # class settles -- see RETIRED_BY_WRONG.
        self.advance_clipboard({system}, self.RETIRED_BY_WRONG)
        # The write and the re-read in one request, so the row leaves the list now
        # rather than at the next jump.
        sector = self.sector
        self.ask([Ask("mark_wrong", (system, source), {"sector": sector})]
                 + self._read_asks(False),
                 lambda r: self._marked(r, system, sector), write=True)

    def _marked(self, r, system, sector):
        self.recount()
        self.note(f"{system}: marked as not existing"
                  + ("" if r["mark_wrong"] else " (already marked)"), "warn")
        self._paint_from(r, sector)

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
        # ITS OWN PHASE: OpenClipboard can BLOCK on another process holding the
        # clipboard, so it must not be hidden inside the paint total.
        with self.timing.phase("p_clipboard"):
            ok = clipboard.copy(text, self.ui.root)
        if ok:
            # Remembered so place_cursor() can tell "my target moved" from "my target
            # is gone" -- the two need opposite responses.
            self.copied = text
            self.note(f"{name} {self.cursor + 1}: copied {what}", "ok")
        else:
            self.note(f"could not reach the clipboard ({what})", "warn")

    # WHICH ROW KINDS EACH THING TAKES OFF THE SCREEN. Nearly the same and NOT one set:
    # an unfound star is retired by a refused route, never by its class -- it asks
    # whether the system EXISTS, and a class does not answer that.
    SETTLED_BY_CLASS = frozenset({ROW_PREDICTED, ROW_CATALOG, ROW_SECTOR})
    RETIRED_BY_WRONG = frozenset({ROW_PREDICTED, ROW_CATALOG, ROW_SECTOR, ROW_UNFOUND})

    def advance_clipboard(self, gone, removable):
        """The system on the clipboard has just been ANSWERED. Hand over the next
        candidate NOW, from rows already in memory. -> True if the clipboard moved.

        *** THE FAST PATH FOR THE ONE MOMENT THE OVERLAY MUST BE INSTANT. *** You copy
        a target, alt-tab, paste, plot -- and the plot answers that target, so the row
        leaves the list and the next candidate is the next paste. place_cursor() step 3
        reaches the same answer but only at the end of the repaint, behind ~2.0 s of
        SQL deciding what is on SCREEN. This needs no query at all: it goes out in the
        same tick that reads NavRoute.json.

        The successor is already in memory, two different ways:

          ADJACENT rows carry `candidates`, SECTOR_CANDIDATES deep in the query's own
            ranking order, so element 2 IS the next pick.
          EVERY OTHER TABLE has its visible list in self.rows: the row that moves up is
            the first below the cursor that survives. Off the bottom returns None --
            place_cursor() would clamp upwards and guessing that is not worth it.

        Skips EVERY answered name, not just the first: one plot often settles several.

        The repaint does not copy again -- place_cursor() step 1 follows the cursor to
        the name we just copied. Both are the same ranking over the same filters, so
        they cannot disagree; if they ever did, the repaint wins in that tick.
        """
        if self.copied is None or not gone:
            return False
        live = self.filled()
        if self.active not in live:
            return False
        name, _table = self.tables[self.active]
        rows = self.rows[name]
        if not 0 <= self.cursor < len(rows):
            return False
        row = rows[self.cursor]
        # ONLY WHEN THE ROW UNDER THE CURSOR IS THE ONE THAT WAS ANSWERED. A plot
        # reveals every hop, and a reveal elsewhere on screen is a repaint, not a
        # clipboard event -- overwriting the commander's chosen target because a
        # passing hop was classed would be worse than any latency.
        if self.target_of(row) not in gone or row.get("row_grp") not in removable:
            return False
        nxt = self._successor(rows, gone, removable)
        if nxt is None or nxt == self.copied:
            return False
        if not clipboard.copy(nxt, self.ui.root):
            # Silent: copy_selected() at the end of the repaint tries again and says
            # so there. One failure, one message.
            return False
        self.copied = nxt
        self.note(f"{name} {self.cursor + 1}: answered -- copied {nxt}", "ok")
        return True

    def _successor(self, rows, gone, removable):
        """-> the name that will be under the cursor once `gone` leaves, or None."""
        cached = rows[self.cursor].get("candidates")
        if cached:
            return next((c for c in cached if c not in gone), None)
        for r in rows[self.cursor + 1:]:
            if self.target_of(r) in gone and r.get("row_grp") in removable:
                continue
            return self.target_of(r)
        return None

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

    def chime_worthy(self, finds, fresh, boxel):
        """Does this reveal earn a sound? -> bool. `boxel` is predicted_boxel()'s answer.

        Three tests, and a find has to pass all of the ones that apply to it:

          1. FRESH. Not just on the route -- newly learned. `finds` lists every rare
             star among the hops, including ones confirmed weeks ago, so without this
             a replot re-announces them.
          2. CHIME_CLASSES. BH, WR, supergiant, Herbig, O-type sound unconditionally.
             White dwarfs never do.
          3. CHIME_IF_PREDICTED. A neutron sounds only where the system is a boxel
             prediction of OURS -- see Database.predicted_boxel(). A neutron you steered
             toward is not news; a neutron in a system we asserted into existence out
             of an index gap is the model being right.

        The predicted_boxel() probe is only ASKED FOR when a neutron is among the
        finds -- see record_revealed() -- so an ordinary plot costs nothing.
        """
        if not finds:
            return False
        candidates = [(n, c) for n, c in finds if n in fresh]
        if any(c in CHIME_CLASSES for _n, c in candidates):
            return True
        return any(n in boxel for n, c in candidates if c in CHIME_IF_PREDICTED)

    def record_revealed(self, rows, note=None):
        """Write revealed arrival classes and repaint if anything actually changed.

        A reveal moves a system one way or the other: rare, and it appears in
        Confirmed; ordinary, and it drops out of the sector table because the question
        it was asking has been answered. Either way the display is now stale.
        """
        if not rows:
            return
        # *** BEFORE ANYTHING THAT TOUCHES THE DATABASE. *** The names and classes came
        # out of NavRoute.json, so "the target I copied has been answered" needs no
        # query -- and this is the moment the commander is waiting on, with the galaxy
        # map open and a paste to make. Everything below is the display catching up.
        self.advance_clipboard({n for n, c, *_ in rows if n and c},
                               self.SETTLED_BY_CLASS)
        stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds")
        # Rares GALAXY-WIDE, not just this sector: a black hole revealed 15,000 ly away
        # still belongs on screen and still deserves saying out loud.
        finds = [(n, c) for n, c, *_ in rows if c in RARE_CLASSES]
        # ASKED FOR ONLY WHEN A NEUTRON IS AMONG THE FINDS. A neutron sounds only where
        # WE predicted the system, which is the one test needing the model; an ordinary
        # plot reveals no neutron and never pays for the probe. Not filtered by
        # freshness yet -- that needs record_seen's answer, so chime_worthy() does it.
        maybe = [n for n, c in finds if c in CHIME_IF_PREDICTED]
        # ONE REQUEST, ONE SESSION, IN ORDER: the write, then the promotion that depends
        # on it, then the reads that observe both. Ref() carries record_seen's answer
        # into promote_confirmed without a second round trip. NO COALESCING KEY -- this
        # carries a write, and a dropped write is a lost find.
        asks = [Ask("record_seen", (rows, stamp)),
                Ask("promote_confirmed", (), {"only": Ref("record_seen")})]
        if maybe:
            asks.append(Ask("predicted_boxel", (maybe,)))
        asks += self._read_asks(False)
        sector = self.sector
        self.ask(asks, lambda r: self._revealed(r, finds, note, sector), write=True)

    def _revealed(self, r, finds, note, sector):
        """The reveal landed: repaint, then say so on both channels."""
        new = set(r["record_seen"])
        self._promoted = r.get("promote_confirmed") or 0
        worth_hearing = self.chime_worthy(finds, new, r.get("predicted_boxel") or set())
        self.recount()
        self._paint_from(r, sector)
        if finds:
            what = ", ".join(f"{n} [{c}]" for n, c in finds[:3])
            more = f" (+{len(finds) - 3})" if len(finds) > 3 else ""
            self.note(f"CONFIRMED {len(finds)} rare -- {what}{more}", "ok")
            # ANY rare class, not just BH and WR. AFTER the repaint, which is what
            # put the rows on screen.
            self.confirmed.flash([n for n, _ in finds])
            # THE CHIME IS NARROWER THAN THE FLASH: the flash is free and addresses rows
            # already drawn, a sound interrupts and has to earn it. See chime_worthy().
            if worth_hearing:
                notify.chime(enabled=not self.args.no_sound)
        elif note:
            self.note(f"{note}, {len(new)} new", "dim")

    def toggle_neutron_route(self):
        """SHIFT+N. Plot a neutron-boosted route to the selected row, or tear one down.

        A TOGGLE, so this is the only place deciding which of the two it is. Pressing it
        while a route is up clears the mode WHATEVER row the cursor is on -- "again to
        cancel" has to mean that unconditionally, or the key is not a toggle but a guess.
        """
        if self.route is not None:
            self.clear_neutron_route("neutron jump mode OFF")
            return
        name, _table = self.tables[self.active]
        rows = self.rows[name]
        if not 0 <= self.cursor < len(rows):
            self.note("nothing selected to route to", "warn")
            return
        row = rows[self.cursor]
        dest = self.target_of(row)
        xyz = (row.get("x"), row.get("y"), row.get("z"))
        if None in xyz:
            # An Adjacent-sector row names a SECTOR and copies the best system inside
            # it, so the coordinates on the row are not the destination's. Name the
            # tables that do work rather than route to the wrong place.
            self.note(f"no coordinates for {dest} -- SHIFT+N routes from the sector, "
                      f"confirmed, unfound and neutron tables", "warn")
            return
        if not self.pos:
            self.note("no position yet -- cannot plot a route from nowhere", "warn")
            return
        self.plot_neutron_route(dest, tuple(float(v) for v in xyz))

    def plot_neutron_route(self, dest, dest_xyz):
        """Find the minimum-jump chain of cones to `dest_xyz`, and enter the mode."""
        if self.jump_range is None:
            self.note("no jump range -- cannot plot without knowing how far you jump",
                      "warn")
            return
        direct = math.dist(self.pos, dest_xyz)
        if direct > route.MAX_ROUTE_LY:
            self.note(f"{dest} is {direct:,.0f} ly away -- neutron routing is capped at "
                      f"{route.MAX_ROUTE_LY:,.0f} ly", "warn")
            return
        # WIDEN ONCE BEFORE BELIEVING A FAILURE. The first corridor is tight, to keep
        # the fetch small; "no route" out of it means "not in the box we drew", which is
        # not the same statement as "not in the galaxy". The widening is a SECOND request
        # rather than both corridors up front, so the common case fetches once.
        self._route_attempt(dest, dest_xyz, (600.0, 2500.0))

    def _route_attempt(self, dest, dest_xyz, pads):
        pad, rest = pads[0], pads[1:]
        self.ask([Ask("neutron_corridor", (self.pos, dest_xyz), {"pad": pad})],
                 lambda r: self._routed(r, dest, dest_xyz, rest), key="route")

    def _routed(self, r, dest, dest_xyz, rest):
        boosted = self.jump_range * ship.NEUTRON_BOOST
        direct = math.dist(self.pos, dest_xyz)
        names, xyz = r["neutron_corridor"]
        with self.timing.phase("route_search"):
            hops = route.plan(xyz, self.pos, dest_xyz, self.jump_range, boosted)
        if hops is None and rest:
            self._route_attempt(dest, dest_xyz, rest)
            return
        if hops is None:
            self.note(f"no neutron route to {dest} ({direct:,.0f} ly) at "
                      f"{self.jump_range:.1f} ly "
                      f"({boosted:.0f} ly boosted) -- nothing reachable in the corridor",
                      "warn")
            return
        self.route = [self._route_row(names[i], xyz[i]) for i in hops]
        self.route.append(self._route_row(dest, dest_xyz, final=True))
        self.route_dest = dest
        # THE FIRST HOP, NOT THE DESTINATION. It is the only name the galaxy map can
        # usefully take right now; pasting the destination would plot the ordinary
        # route this mode exists to replace.
        self._copy_next_hop(f"neutron route to {dest}: {len(self.route)} jump(s)")
        self.refresh(moved=False)

    def clear_neutron_route(self, why):
        """Leave the mode; put the carriers and the nearest cones back."""
        self.route = self.route_dest = None
        # The carrier cache is untouched -- the route never displaced it. The nearest
        # cones are still cached and still correct: they depend on position alone, and
        # plotting a route does not move you.
        self.note(why)
        self.refresh(moved=False)

    def _route_row(self, name, xyz, final=False):
        """One hop, in the shared row shape the tables render.

        Built HERE and not in database.py, the single exception to that module owning
        every row: these come from a computation rather than a query, and handing the
        solved path back to SQL to be re-selected is a round trip to dress up data
        already in hand.
        """
        x, y, z = (float(v) for v in xyz)
        return {"rank": 0, "system": name,
                "type_label": "ARRIVE" if final else "BOOST",
                "dist_ly": math.dist(self.pos, (x, y, z)) if self.pos else None,
                "dist_approx": False,
                # Every prediction column, all NULL -- a computed hop is a place to
                # fly through, not a guess about what is in it. Spread from database
                # so a new kind cannot leave this dict one key short of what the
                # renderer asks for.
                **P_NONE,
                "confirmed_col": None, "row_grp": ROW_NEUTRON,
                "wide_text": "DESTINATION" if final else "-",
                "detail": None, "mass_code": None, "boxel": None,
                "x": x, "y": y, "z": z, "dist_sol": None, "star_class": None}

    def _copy_next_hop(self, prefix):
        """Put the next system on the route on the clipboard, and say so."""
        if not self.route:
            return
        nxt = self.route[0]["system"]
        if clipboard.copy(nxt, self.ui.root):
            # The same field place_cursor() uses, so the cursor FOLLOWS the hop instead
            # of fighting it. The clipboard has exactly one owner either way.
            self.copied = nxt
            self.note(f"{prefix} -- copied {nxt}", "ok")
        else:
            self.note(f"{prefix} -- could not reach the clipboard ({nxt})", "warn")

    def advance_route(self, system):
        """Arrived at `system`: drop the hops now behind us, copy the next. -> bool.

        MATCHES ANYWHERE IN THE REMAINING ROUTE, not only at hop zero. A cone route is
        flown by hand and you will overshoot it -- a longer jump than planned, or two
        hops plotted at once in the galaxy map -- and a router that recognised only the
        very next system would sit there insisting on one you had already passed.

        Arriving somewhere NOT on the route is neither an error nor a reason to tear the
        route down: you detoured to scoop, which this router cannot plan for and the
        route survives. It is left exactly as it was.
        """
        if not self.route:
            return False
        at = next((i for i, r in enumerate(self.route) if r["system"] == system), None)
        if at is None:
            return False
        last = self.route[at] is self.route[-1]
        self.route = self.route[at + 1:]
        if last or not self.route:
            self.clear_neutron_route(
                f"neutron route complete: arrived at {self.route_dest}")
            return True
        skipped = f", {at} skipped" if at else ""
        self._copy_next_hop(f"{len(self.route)} jump(s) left to "
                            f"{self.route_dest}{skipped}")
        return True

    def check_focus(self):
        """Hide the HUD unless Elite -- or this window -- has the foreground."""
        if self.args.always_visible:
            return
        self.ui.set_visible(focus.is_foreground())

    def tick(self):
        with self.timing.span("tick"):
            self._tick()

    def _tick(self):
        # FIRST. Every database answer arrives here, and a repaint waiting a whole extra
        # tick for its results is a repaint 120 ms late for no reason.
        self.drain_db()
        with self.timing.phase("focus"):
            self.check_focus()
        # *** GATED ON FOCUS, AND THAT IS NOT OPTIONAL. *** The navigation keys are the
        # ARROWS and PAGE UP/DOWN, hooked globally because the overlay never holds
        # focus. Ungated, every arrow press anywhere on the machine -- an editor, a
        # browser, a file rename -- would move the cursor and overwrite the clipboard.
        # is_foreground() is true for Elite or for this window, which is exactly when a
        # press could have been meant for us.
        #
        # THE WRITE KEY FIRST, and on its own slot -- see Hotkeys.take_wrong(). Gated
        # on focus for the same reason and more so: SHIFT+BACKSPACE is an ordinary
        # chord in a text field, and an ungated hook would record a galaxy-wide absence
        # every time the commander deleted a word somewhere else.
        if self.hotkeys.take_wrong() and focus.is_foreground():
            with self.timing.phase("key_wrong"):
                self.mark_wrong()
        # Its own slot, like the write key, and drained before the arrows for the same
        # reason: a toggle lost to a same-tick keypress leaves the mode inverted.
        if self.hotkeys.take_route() and focus.is_foreground():
            with self.timing.phase("key_route"):
                self.toggle_neutron_route()
        pressed = self.hotkeys.take()
        if pressed is not None and focus.is_foreground():
            with self.timing.phase("key"):
                self.move(pressed)
        # EVERY TICK, not on the --poll timer. read_navroute() is gated on the file's
        # mtime and costs 0.016 ms when nothing has changed -- a bare os.path.getmtime
        # -- while rate-limiting it puts up to 2 SECONDS between plotting a route and
        # the clipboard catching up.
        #
        # *** ONE record_revealed PER TICK, NOT TWO. *** The route file and the journal
        # both reveal arrival classes, and they are the same kind of fact, so they go
        # in together: one session, one write, one repaint per tick.
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
        # *** THE WORKER OWNS THE DATABASE, INCLUDING THE STARTUP WORK. *** Started
        # first, so the connection is created on that thread and this one never touches
        # it -- Database._connection() asserts as much.
        self.worker.start()
        # Everything the current session already revealed, before the tail starts, plus
        # ONE FULL SELF-HEALING PROMOTION PASS. Merge-only, so a no-op once caught up,
        # which is what it should normally be -- the scoped promotion on the reveal
        # path only ever covers reveals the app SAW.
        harvested = self.reader.harvest_classes()
        asks = []
        if harvested:
            asks.append(Ask("record_seen",
                            ([(nm, cl, None, None, None) for nm, cl in harvested],)))
        asks.append(Ask("promote_confirmed"))
        self.ask(asks, lambda r: self._caught_up(r, len(harvested)), write=True)
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
        self.show_jump_range()
        self.check_focus()
        # The key poll rides the same tick as the journal poll, but a keypress must
        # feel immediate -- two seconds of lag on a copy is unusable -- so the tick
        # runs fast and the journal is only actually re-read every --poll seconds.
        self.ui.every(KEY_POLL_MS, self.tick)
        try:
            self.ui.run()
        finally:
            # Closes the model attachment on the thread that owns it. Without this the
            # process can outlive its window.
            self.worker.stop()

    def _caught_up(self, r, harvested):
        """Startup's own request landed. Prints rather than notes: this is the log."""
        if harvested:
            print(f"harvested {harvested} revealed class(es) from the journal, "
                  f"{len(r.get('record_seen') or [])} new", flush=True)
        if r.get("promote_confirmed"):
            print(f"promoted {r['promote_confirmed']} rare sighting(s) into the find "
                  f"log", flush=True)
        self.recount()

    def show_jump_range(self):
        """Write the ship's range to the right of the carrier/neutron heading.

        THAT TABLE AND NOT ANOTHER: its rows are the nearest jet cones, and the number
        that decides whether one is worth flying to is how far you jump -- boosted and
        unboosted. Putting it over the neutron rows means the question and its answer
        are read in one glance instead of two places on screen.

        Silent on failure BY DESIGN. A missing Loadout or an unrecognised drive means
        ship.py refused to guess, and the honest display of "we do not know your jump
        range" is no jump range -- not a plausible number nobody can check in flight.

        Written once, at startup, like the keys. An outfitting change mid-session will
        not update it: the price of keeping a journal re-read off the paint path.
        """
        loadout = journal.read_loadout(self.args.journal_dir)
        if not loadout:
            return
        # Kept as a number as well as a string: the heading wants it rendered, and
        # SHIFT+N wants it to route with. Computed ONCE, from one loadout read, so the
        # two can never describe different ships.
        self.jump_range = ship.jump_range(loadout)
        text = ship.summary(loadout)
        if text:
            self.carriers.set_title_right(text)

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
