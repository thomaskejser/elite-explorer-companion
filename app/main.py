"""ed_overlay -- sector-ranked rare-object HUD. Entry point and wiring only.

    python -m app.main

Everything it knows is split across siblings and this file just connects them:

    journal.py  where the commander is        (the only module that reads the journal)
    lights.py   what the throttle LEDs mean   (the only module that picks an LED colour)
    names.py    which sector that name means  (pure string parsing, no IO)
    database.py    what is in that sector        (the only module containing SQL)
    table.py    how the ten rows look         (the only module that lays out cells)
    overlay.py  the window they live in       (the only module that knows Tk chrome)
    theme.py    every colour and width        (the only module with literals)

    hotkeys.py  which key means which row     (the only module that hooks the keyboard)

FOUR TABLES AND ONE CURSOR, in descending certainty: Confirmed (the game has already
said it is there), Nearest (the closest parked carrier and the closest neutron -- two
places to GO rather than things to find), Current sector (what might be here) and
Adjacent sectors (what might be next door). The first two share the top line, Confirmed
on the left and Nearest right-aligned with the tables below; the other two are full
width under them. PAGE UP/DOWN moves between them in that order, UP/DOWN within one, and
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
import tkinter as tk
import traceback

from . import clipboard, focus, journal, lights, names, route, ship, timing
from . import hotkeys as keys
from .hotkeys import Hotkeys
from .dbworker import Ask, DbWorker, Ref
from .overlay import Overlay
from . import notify
from .database import (CHIME_CLASSES, CHIME_IF_PREDICTED, P_NONE, RARE_CLASSES,
                    ROW_CARRIER, ROW_CATALOG, ROW_NEUTRON, ROW_PREDICTED, ROW_ROUTE,
                    ROW_SECTOR, ROW_TOTAL, ROW_TRADER, ROW_UNFOUND, Database)
from .kinds import KINDS
from .table import TargetTable
from .theme import (CONFIRMED_COLUMNS, FLASH_CONFIRM, FLASH_COPIED, NEAREST_COLUMNS,
                    PAD_X, Fonts, Palette)

TITLE = "::: sector rares :::"
SECTOR_TITLE = "Current sector"
CONFIRMED_TITLE = "Confirmed"
ADJACENT_TITLE = "Adjacent sectors"
NEAREST_TITLE = "Nearest"
# The wall clock, top right. LOCAL TIME AND NO SECONDS: this answers "what time is it
# out here", which is a glance at the corner, not a stopwatch.
CLOCK_FORMAT = "%H:%M"
ROWS = 10
# ONE CARRIER AND ONE NEUTRON. Both are places to GO rather than things to find, and
# neither carries a prediction, so they share a table -- and the question each answers
# has exactly one answer: the closest. A list of three was three answers to a question
# with one, in a table that now has to fit beside Confirmed.
CARRIER_ROWS = 1
NEUTRON_ROWS = 1
# One row per END of each stored route -- fly it toward Colonia or toward the Founders,
# and the row names the hop you take next. Two, because one route has two directions.
ROUTE_ROWS = 2
TRADER_TYPES = 3
TRADER_PER_TYPE = 1
TRADER_ROWS = TRADER_TYPES * TRADER_PER_TYPE

# What a destination is CALLED in the TYPE cell. The systems have formal names and the
# commander does not use them: Shinrarta Dezhra is the Founders' world to everyone who
# flies there. Anything not listed falls back to the first word of the system name.
# Upper case and seven characters, to sit in the same column as NEUTRON and CARRIER.
ROUTE_ALIAS = {"Shinrarta Dezhra": "FOUNDER"}

# The boosted range used when the ship's own cannot be computed -- no Loadout, or a drive
# ship.py does not recognise. A ROUND NUMBER AND A LAST RESORT: every chain is otherwise
# solved at the range this ship makes, which is its laden range times the multiplier its
# HULL gets -- 6 for the Caspian, 4 for everything else. See ship.neutron_boost().
BOOSTED_LY = 500.0

# How far the ship may drift from a chain before it is re-solved. One jump: while you are
# flying the chain the next hop is always within range, so this never fires; leave the
# chain and it fires at once. A chain is ~1.5 s of worker time, so re-solving on every
# jump would cost more than the repaint it competes with.
CHAIN_SLACK = 1.0
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
        # THE TOP LINE HOLDS TWO TABLES SIDE BY SIDE. Confirmed went narrow when it
        # became one row per kind, which left ~394 px of the window's width empty
        # beside it; Nearest is two rows and fits there. `fill="x"` matters: the frame
        # takes the window's full width -- set by the sector table below -- so packing
        # Nearest to the RIGHT lands its edge on that table's edge rather than beside
        # Confirmed.
        self.top = tk.Frame(self.ui.body, bg=Palette.key)
        self.top.pack(anchor="w", fill="x", before=self.table.container)
        # THE WALL CLOCK, in the corner on the Nearest heading's line. `place` rather
        # than pack, so it costs no layout: a packed clock would take the right-hand
        # strip and push Nearest out of line with the tables below.
        self.clock = tk.Label(self.top, text="", font=fonts.title,
                              fg=Palette.clock, bg=Palette.key, anchor="e")
        self.clock.place(relx=1.0, x=-(PAD_X // 2), y=0, anchor="ne")
        # The last string written, so a tick that changes nothing touches no widget.
        self._clock_text = None
        # ONE ROW PER KIND, so the grid is exactly as tall as the vocabulary and can
        # never truncate -- there is nothing left over to leave off.
        self.confirmed = TargetTable(
            self.top, rows=len(KINDS), fonts=fonts, title=CONFIRMED_TITLE,
            # NARROW: the text columns and the tally, no predictions. A confirmed find
            # is a certainty, so a probability cell on one of these rows could only ever
            # say "not applicable" -- six columns of that, on every row.
            columns=CONFIRMED_COLUMNS,
            # Only rendered when it has rows: a Confirmed heading over an empty grid
            # would suggest there is nothing out there, when the usual truth is simply
            # that nothing has been revealed in THIS sector yet.
            hide_when_empty=True, pack_opts={"side": "left", "anchor": "n"},
            # THE ONLY TABLE THAT FLASHES ITS OWN ARRIVALS. Its rows come from anywhere
            # in the galaxy, so a line can appear here with nothing else on screen
            # changing; the other three turn over whenever the ship moves, and flashing
            # that would be flashing the fact that you are flying.
            flash_new=True)
        self.confirmed.blank()
        # To the RIGHT of Confirmed and on its own narrow columns -- see
        # theme.NEAREST_COLUMNS. No wide_heading: with no prediction cells to span,
        # the carrier's name is an ordinary column with an ordinary heading.
        self.nearest = TargetTable(
            self.top, rows=CARRIER_ROWS + NEUTRON_ROWS + ROUTE_ROWS + TRADER_ROWS,
            fonts=fonts,
            title=NEAREST_TITLE, columns=NEAREST_COLUMNS,
            hide_when_empty=True, pack_opts={"side": "right", "anchor": "n"})
        self.nearest.blank()
        # ABOVE THE TABLE IT OVERLAYS. Tk stacks siblings in creation order, so the
        # Nearest container -- built after the clock and covering the same corner --
        # would otherwise hide it completely.
        self.clock.lift()
        # Adjacent sectors last, under the sector table. Nothing follows it now, so it
        # needs no `before`: pack() appends, and the end IS where it belongs.
        self.adjacent = TargetTable(
            self.ui.body, rows=ROWS, fonts=fonts, title=ADJACENT_TITLE,
            hide_when_empty=True)
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
        # THE FOUR TABLES IN CURSOR ORDER, which is READING ORDER: the top line left to
        # right, then the tables under it. PAGE UP/DOWN walks this list and skips
        # whatever is currently empty, so the cursor never lands on a heading with
        # nothing under it.
        self.tables = [(CONFIRMED_TITLE, self.confirmed), (NEAREST_TITLE, self.nearest),
                       (SECTOR_TITLE, self.table), (ADJACENT_TITLE, self.adjacent)]
        # The rows each table currently offers as DESTINATIONS, in display order.
        # Rebuilt by refresh(). Index into this is index into the grid, which is what
        # lets TargetTable.set_selected() take the same number -- true only because the
        # one non-destination row (the sector TOTAL) is appended LAST.
        self.rows = {name: [] for name, _t in self.tables}
        self.active = 0        # which table the cursor is in
        self.cursor = 0        # which row of it
        # Per table, the target the cursor was on when PAGE UP/DOWN left it, so paging
        # back returns to it rather than to the top. Keyed by target_of(), not by index,
        # because the rows reorder while you are away.
        self.marks = {}
        # The name whose row is waiting to be flashed, once the repaint has put that
        # row where it now belongs. See took_clipboard().
        self._pending_flash = None
        # The last thing actually put on the clipboard. None until the commander moves
        # the cursor, which is what stops the app grabbing the clipboard at startup.
        self.copied = None
        # WHERE A ROUTE COULD GO: {label: (system, (x, y, z))}, read once at startup
        # from the endpoints of whatever main.route holds. The stored HOPS are not used
        # for navigation any more -- see solve_chains() -- but the endpoints are still
        # the only place the app knows a position for "Shinrarta Dezhra".
        self._dests = {}
        # THE CHAINS IN HAND: {label: {"hops", "range", "dest"}}, each solved from where
        # the ship was standing at the time, at the range it flies. Rebuilt when the ship
        # leaves one, never on a timer.
        self._chains = {}
        # Labels with a solve in flight, so a slow one is not asked for twice.
        self._solving = set()
        # {label: (destination, range)} that came back with nothing. A chain that cannot
        # be found is expensive to fail at -- every widening step re-primes and
        # re-searches -- so it is not asked for again until the destination or the ship
        # changes. Without this, one unreachable place costs ten seconds of worker on
        # every single jump.
        self._unsolvable = {}
        # WHICH CHAIN IS BEING FLOWN, or None: {"label", "next"} -- which destination,
        # and the hop currently on the clipboard. Arriving anywhere on that chain copies
        # the hop after it.
        self.follow = None
        # Cached: see _read(). Only re-queried when the commander moves.
        # TWO CACHES, NOT ONE COMBINED LIST. Both halves of that table depend only
        # on position, but the route replaces the NEUTRON half by itself and
        # leaves the carriers alone -- and re-querying carriers is the single
        # most expensive read in a repaint. Split, a route plot costs neither.
        self._carrier_rows = None
        self._neutron_rows = None
        self._trader_rows = None
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
        # The throttle LEDs, and a no-op object when no VKB is plugged in. The left one
        # shows fuel; see lights.py.
        self.lights = lights.Lights(enabled=not args.no_lights)
        self.loadout = None
        # (system, arrival class) of the jump the commander has TARGETED, from the last
        # FSDTarget or StartJump. Held rather than read per tick because the events are
        # the only place the class appears -- Status.json names the destination and not
        # what is in it -- and the middle light needs both to agree before it lights.
        self.next_jump = None
        self._last_poll = 0.0
        self._navroute_mtime = None
        self._status_mtime = None
        self._status = None
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
        # later. Silent and harmless when either mode is off.
        if record:
            self.advance_route(system)
            self.advance_follow(system)
        # AFTER the arrival handling, so a chain that was just advanced along is not
        # mistaken for one the ship has left. Cheap when every chain still fits.
        self.solve_chains()

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

    def dress_nearest(self, rows):
        """Fill in what the Nearest table shows that a query could not know. -> rows.

        Two things, both of which depend on where the ship is or what it flies:

        *** WHICH RANGE DEPENDS ON HOW YOU WOULD GET THERE. *** A neutron star is the
        thing you fly to in order to supercharge, so you reach it UNBOOSTED, on the
        ship's own jump range. A carrier or the far end of a route is reached ALONG a
        chain of cones, so it is counted at the boosted range.

        Rounded UP, because a part jump is a jump. NULL where there is no distance or no
        loadout to compute a range from -- an estimate nobody can check is worse than a
        dash. A route row already knows its answer exactly and keeps it: the hops are
        counted, not divided.

        And THE CARRIER'S NAME, once the ship is in the carrier's system. There is
        nothing to jump to at that point, so NEXT stops being a destination and becomes
        the thing you actually need there -- which of the ships in orbit is the one you
        came for.
        """
        chain = (self._chains.get("CARRIER") or {}).get("hops")
        for row in rows:
            arrived = (self.system and row.get("system") == self.system)
            if row.get("row_grp") == ROW_CARRIER and chain and not arrived:
                # THE SAME CHAIN THE ROUTE ROWS FLY, to a destination that moves. The
                # row keeps its own identity -- it is still the carrier row -- but what
                # it offers is the next hop toward it and the jumps that remain.
                target = self.chain_target(chain)
                if target is not None:
                    row["system"] = target["system"]
                    row["jumps"] = self.hops_left(chain, target["hop"], 1)
                    row["x"], row["y"], row["z"] = (target["x"], target["y"],
                                                    target["z"])
                    row["dist_ly"] = (math.dist(self.pos, (target["x"], target["y"],
                                                           target["z"]))
                                      if self.pos else None)
            if row.get("jumps") is None:
                ly = row.get("dist_ly")
                # A NEUTRON IS REACHED UNBOOSTED -- it is the thing you fly to in order
                # to get the boost, so you cannot have had it on the way. Everything
                # else here is either chained or close enough not to matter.
                reach = (self.jump_range if row.get("row_grp") == ROW_NEUTRON
                         else self.boosted_range())
                row["jumps"] = (math.ceil(ly / reach)
                                if ly is not None and reach else None)
            if row.get("row_grp") in (ROW_CARRIER, ROW_TRADER) and arrived:
                row["arrived_text"] = row.get("wide_text")
        return rows

    # -- live chains -----------------------------------------------------------------
    def boosted_range(self):
        """What one supercharged jump covers, in ly. The ship's own, or the fallback."""
        return (self.jump_range * ship.neutron_boost(self.loadout)
                if self.jump_range else BOOSTED_LY)

    def chain_targets(self):
        """{label: (system, xyz)} for everything worth plotting a chain to right now.

        The stored destinations, plus THE NEAREST CARRIER, which is a destination like
        any other -- it just moves, so it is read from the row rather than a table.
        """
        out = dict(self._dests)
        for row in (self._carrier_rows or []):
            if row.get("x") is not None:
                out["CARRIER"] = (row["system"], (row["x"], row["y"], row["z"]))
            break
        return out

    def chain_stale(self, label, dest, xyz):
        """Does this chain need solving again? -> bool.

        THREE REASONS AND NO TIMER. There is no chain; the ship no longer flies the
        range it was solved at; or the ship has left it -- no hop of it is within one
        jump, so the chain starts somewhere the ship cannot reach. Flying the chain
        never triggers a re-solve, because the next hop is always within range by
        construction, which is what keeps this off the worker on every jump.
        """
        chain = self._chains.get(label)
        if not chain or chain["dest"] != dest:
            return True
        if abs(chain["range"] - self.boosted_range()) > 1.0:
            return True
        if not self.pos:
            return False
        reach = self.boosted_range() * CHAIN_SLACK
        return not any(math.dist(self.pos, (h["x"], h["y"], h["z"])) <= reach
                       for h in chain["hops"])

    def solve_chains(self):
        """Ask the worker for any chain that is missing or stale. Cheap when none are.

        ONE ASK PER DESTINATION, each under its own coalescing key, so a second request
        for the same place replaces the first rather than queueing behind it. Never
        blocks the tick: the answer lands on a later one and the row is dashes until it
        does.
        """
        if not self.pos:
            return
        for label, (dest, xyz) in self.chain_targets().items():
            if label in self._solving or not self.chain_stale(label, dest, xyz):
                continue
            if dest == self.system:
                # Already there. Nothing to plot, and the row says so by other means --
                # a carrier shows its name, a destination shows no jumps.
                self._chains.pop(label, None)
                continue
            if self._unsolvable.get(label) == (dest, round(self.boosted_range())):
                continue
            self._solving.add(label)
            rng = self.boosted_range()
            self.ask([Ask("solve_route", (self.pos, xyz, rng),
                          {"names": (self.system or "here", dest)})],
                     lambda r, l=label, d=dest, g=rng: self._solved(r, l, d, g),
                     key=f"solve:{label}")

    def _solved(self, r, label, dest, rng):
        """A chain came back. Keep it, say how it went, and repaint through it."""
        self._solving.discard(label)
        hops = r.get("solve_route")
        if not hops:
            self.note(f"no neutron chain to {dest} at {rng:,.0f} ly boosted -- "
                      f"not retried until the ship or the destination changes", "warn")
            self._chains.pop(label, None)
            self._unsolvable[label] = (dest, round(rng))
            return
        self._unsolvable.pop(label, None)
        self._chains[label] = {"hops": hops, "range": rng, "dest": dest}
        self.note(f"{label}: {len(hops) - 1} jump(s) to {dest} at {rng:,.0f} ly "
                  f"boosted", "ok")
        self.refresh(moved=False)

    # -- the rows ---------------------------------------------------------------------
    def route_rows(self):
        """One row per chain in hand. -> rows in the shared shape.

        *** THE ROW NAMES THE HOP, NOT THE DESTINATION. *** `system` is the system to fly
        to next -- the NEXT column, and what the cursor copies -- while where the chain
        GOES is named in TYPE, as COLONIA or FOUNDER. So the row reads "to reach the
        Founders, jump to this system next, and it is that many jumps away".

        CARRIER IS NOT ONE OF THESE. Its row comes from the query, and gets its chain
        folded in by dress_nearest() -- one row for the carrier either way.
        """
        rows = []
        for label, chain in sorted(self._chains.items()):
            if label == "CARRIER":
                continue
            hops = chain["hops"]
            target = self.chain_target(hops)
            if target is None:
                continue
            rows.append({
                "system": target["system"],
                "type_label": label,
                "dist_ly": (math.dist(self.pos, (target["x"], target["y"],
                                                 target["z"]))
                            if self.pos else None),
                "dist_approx": False, **P_NONE,
                "row_grp": ROW_ROUTE,
                # COUNTED, NOT ESTIMATED. Every other row divides a distance by a range;
                # a chain knows its remaining hops exactly, and they are what will
                # actually be flown.
                "jumps": self.hops_left(hops, target["hop"], 1),
                "wide_text": None,
                "detail": (("following " if (self.follow or {}).get("label") == label
                            else "") + chain["dest"]),
                "mass_code": None, "boxel": None,
                "x": target["x"], "y": target["y"], "z": target["z"],
                "dist_sol": None, "star_class": None,
                "route": label, "route_step": 1})
        return rows

    @staticmethod
    def hops_left(hops, hop, step):
        """Jumps still to fly to reach this direction's end, from wherever the ship is.

        *** IT COUNTS THE JUMP TO `hop` ITSELF. *** `hop` is the one being flown to
        next, not the one underfoot, so from hop 20 of a 46-hop chain the next hop is 21
        and the answer is 26 -- jumping to 21 is one of them. Counting from the target
        instead gives 25 and quietly loses the jump you are about to make.
        """
        return abs(((len(hops) - 1) if step > 0 else 0) - hop) + 1

    def chain_target(self, hops):
        """The hop this chain should be offering right now, or None at the end of it.

        THE NEAREST HOP THAT IS BOTH REACHABLE IN ONE JUMP AND CLOSER TO THE DESTINATION.
        Two tests, and neither is optional:

          PROGRESS. A hop must be closer to the chain's end than the ship is now. That is
            why standing ON a hop offers the next one rather than the one underfoot: your
            own hop is exactly as far from the end as you are, and "closer" is strict.
          REACH. And it must be within one boosted jump. Offering a hop the ship cannot
            make in one go is offering a paste that will not plot.

        Nearest among those, because the hops are a chain: the nearest one that still
        makes progress IS the next link, and reaching past it would skip a supercharge
        the rest of the chain assumes.

        *** WHEN NOTHING IS IN REACH, THE NEAREST PROGRESSING HOP IS OFFERED ANYWAY. ***
        The ship has drifted off the chain, and the honest answer is "this is where you
        rejoin" rather than no answer -- and its JUMPS cell, counted from a hop the ship
        cannot reach in one go, is why solve_chains() is about to replace the chain.
        """
        located = [h for h in hops if h["x"] is not None]
        if not located or not self.pos:
            return located[0] if located else None
        goal = (hops[-1]["x"], hops[-1]["y"], hops[-1]["z"])
        here = math.dist(self.pos, goal)
        away = lambda h: math.dist(self.pos, (h["x"], h["y"], h["z"]))
        ahead = [h for h in located
                 if math.dist((h["x"], h["y"], h["z"]), goal) < here]
        if not ahead:
            return None
        reach = self.boosted_range()
        return min([h for h in ahead if away(h) <= reach] or ahead, key=away)

    def follow_route(self, row):
        """Start following the chain `row` belongs to. Its hop is already copied."""
        label = row.get("route") or ("CARRIER" if row.get("row_grp") == ROW_CARRIER
                                     else None)
        if label is None:
            return
        self.follow = {"label": label, "next": row["system"]}
        self.note(f"following the chain to {self.chain_dest(label)} -- "
                  f"next {row['system']}. Copy any other row to stop.", "ok")

    def chain_dest(self, label):
        """-> where the chain `label` ends, or the label itself when nothing knows."""
        return (self._chains.get(label) or {}).get("dest", label)

    def advance_follow(self, system):
        """Arrived at `system`: if it is a hop of the route being followed, hand over
        the next one. -> True if the clipboard moved.

        MATCHES ANY HOP, not just the one that was copied. Arriving somewhere else on
        the chain -- because a jump was skipped, or the route rejoined further along --
        should still advance from where the ship actually is, and an arrival off the
        route leaves the clipboard alone rather than guessing.
        """
        if not self.follow:
            return False
        chain = self._chains.get(self.follow["label"]) or {}
        hops = chain.get("hops") or []
        at = next((h for h in hops if h["system"] == system), None)
        if at is None:
            return False
        nxt = next((h for h in hops if h["hop"] == at["hop"] + 1), None)
        if nxt is None:
            self.note(f"arrived at {chain.get('dest', 'the destination')} -- "
                      f"chain complete", "ok")
            self.follow = None
            return False
        self.follow["next"] = nxt["system"]
        if not clipboard.copy(nxt["system"], self.ui.root):
            self.note(f"could not reach the clipboard ({nxt['system']})", "warn")
            return False
        self.took_clipboard(nxt["system"])
        left = self.hops_left(hops, nxt["hop"], 1)
        self.note(f"hop {at['hop']} flown -- copied {nxt['system']}, {left} to go", "ok")
        return True

    def _arrived(self, r):
        """The arrival write landed. Its only visible product is the POI note."""
        _new, poi = r["record_arrival"]
        self.recount()                              # a write moved them
        if poi:
            self.note(f"POI logged here: {poi}", "ok")

    @staticmethod
    def _nearest(confirmed):
        """'962 ly (NEUTRON)' for the closest confirmed find, or why there is none.

        A MINIMUM OVER THE ROWS, not the first of them: the table is drawn in RARITY
        order, one line per kind, so its top row is the nearest black hole rather than
        the nearest anything. It names the kind, because with the rows no longer sorted
        by distance the number alone does not say which line to look at.
        """
        located = [r for r in confirmed if r.get("dist_ly") is not None]
        if not located:
            return "distance unknown" if confirmed else "none"
        row = min(located, key=lambda r: r["dist_ly"])
        return f"{row['dist_ly']:,.0f} ly ({row['type_label']})"

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

    def tick_failed(self, e):
        """Say what a tick raised. The clock re-arms either way -- see Overlay.every."""
        self.note(f"tick error: {type(e).__name__}: {e}", "warn")
        traceback.print_exc()

    def update_clock(self):
        """Put the time in the corner. Rewrites the label only when the minute turns."""
        text = time.strftime(CLOCK_FORMAT)
        if text != self._clock_text:
            self._clock_text = text
            self.clock.config(text=text)

    def _read_asks(self, moved):
        """Every query one repaint needs, as Asks. Call order is the order they run.

        Confirmed first: anything in it is EXCLUDED from the sector table, so a certain
        find appears exactly once. It and the carrier and adjacent lists are GALAXY-WIDE
        and position-ranked, so they are fetched whether or not the sector is procedural.

        *** CARRIERS AND NEUTRONS ONLY WHEN YOU HAVE ACTUALLY MOVED. *** Neither can
        have changed otherwise -- the reliable set is fixed between model rebuilds and
        the only variable is distance from here. Plotting a route does not move you.
        """
        asks = [Ask("confirmed_targets", (self.pos,))]
        if moved or self._carrier_rows is None:
            asks.append(Ask("carrier_targets", (self.pos,), {"limit": CARRIER_ROWS}))
        if moved or self._neutron_rows is None:
            asks.append(Ask("neutron_targets", (self.pos,), {"limit": NEUTRON_ROWS}))
        if moved or self._trader_rows is None:
            asks.append(Ask("trader_targets", (self.pos,), {"per_type": TRADER_PER_TYPE}))
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
            # The nearest carrier is a destination that MOVES: a new carrier row can
            # mean a different system, and the chain to it has to follow.
            self.solve_chains()
        if "neutron_targets" in r:
            self._neutron_rows = r["neutron_targets"]
        if "trader_targets" in r:
            self._trader_rows = r["trader_targets"]
        # THE ROUTE REPLACES THE NEUTRON ROW, AND ONLY THAT ROW: it answers "where is
        # the nearest cone", and while a route is up the useful answer is "the one you
        # are flying to". The carrier row answers something else and stays.
        nearest = self.dress_nearest(
            self._carrier_rows + (self.route[:NEUTRON_ROWS]
                                  if self.route is not None
                                  else self._neutron_rows) + self.route_rows()
            + (self._trader_rows or []))
        with self.timing.phase("paint"):
            self._paint(r["confirmed_targets"], nearest, r["adjacent_sectors"],
                        r.get("top_targets", []), r.get("unfound_targets", []),
                        r.get("sector_totals", []), r.get("region_totals") or [],
                        r.get("sector_summary", (0, 0, 0, 0)))

    def _paint(self, confirmed, nearest, adjacent, targets, unfound,
               totals, region, summary):
        """Everything after the reads: fill the grids, move the cursor, say what
        happened. Split out so timing.py can price it separately from the SQL, which
        has very different fixes."""
        # PHASED PER GRID. The expensive paint is the FIRST one -- Tk realising the
        # window when a hide_when_empty container is first packed, ~91 ms against ~10
        # in steady state. p_cursor is separate because it reaches the WIN32 CLIPBOARD.
        with self.timing.phase("p_nearest"):
            self.nearest.show(nearest)
            # The heading says which of its two jobs the table is doing. Retitled on
            # every repaint because the count in it changes with every hop flown.
            #
            # SHORT ENOUGH FOR THE SLOT. This title sits in the 394 px beside Confirmed,
            # and a title wider than its table widens the container and pushes the whole
            # top line past the tables below it.
            self.nearest.set_title(
                f"-> {self.route_dest} ({len(self.route)})"
                if self.route is not None else NEAREST_TITLE)
        with self.timing.phase("p_confirmed"):
            # NOT RETITLED. The count belongs to the kind rather than to the table, and
            # every row now carries its own in the tally column.
            self.confirmed.show(confirmed)
        with self.timing.phase("p_adjacent"):
            self.adjacent.show(adjacent)
            self.adjacent.set_title(self._title(ADJACENT_TITLE, adjacent))
        # Set BEFORE the hand-named early return below. All three of these tables are
        # position-ranked rather than sector-scoped, so they are on screen and
        # selectable even when there is no sector, and leaving their rows stale would
        # point the cursor at whatever was confirmed several jumps ago.
        self.rows[CONFIRMED_TITLE] = confirmed
        self.rows[ADJACENT_TITLE] = adjacent
        self.rows[NEAREST_TITLE] = nearest

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

    def targeted_class(self, status):
        """-> the arrival class of the next jump, or None if there is not one.

        Two sources have to agree. FSDTarget carries the class and NOTHING retracts it,
        so on its own it outlives the route and leaves the light lit at a star that is
        now behind you. Status.json's Destination is retracted -- it clears when the
        route ends and changes the moment anything else is targeted -- but never says
        what the star is. Requiring the same name from both means the light goes dark
        the tick the target does, and `!= self.system` covers arriving AT the target,
        where the game leaves the destination naming the system you are sitting in.
        """
        if not self.next_jump:
            return None
        name, star_class = self.next_jump
        dest = (status.get("Destination") or {}).get("Name")
        if dest != name or name == self.system:
            return None
        return star_class

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
        all three can move, shorten or reorder the list the cursor is sitting in. Four
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

        4. FLASH WHAT IS ON THE CLIPBOARD. Last, because the flash claims BOTH that the
           name is in the paste buffer and that the row under it is where it now
           belongs -- and only here are both true. See took_clipboard().
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
        # LAST, AND AFTER THE COPY ABOVE. Every path that moves a row ends here, so
        # this is the one point where the clipboard and the screen are both settled --
        # which is exactly what the flash is claiming when it fires.
        self._flash_copied()

    def remember(self):
        """Record what the cursor is on, so paging back to this table can return."""
        name, _t = self.tables[self.active]
        rows = self.rows[name]
        if 0 <= self.cursor < len(rows):
            self.marks[name] = self.target_of(rows[self.cursor])

    def recall(self, index):
        """-> the row of table `index` holding its mark, or 0 if it has gone."""
        name, _t = self.tables[index]
        mark = self.marks.get(name)
        if mark is None:
            return 0
        return next((i for i, r in enumerate(self.rows[name])
                     if self.target_of(r) == mark), 0)

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
            self.remember()
            self.active, self.cursor = nxt, self.recall(nxt)
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
            self.took_clipboard(text)
            # CHOOSING A ROUTE ROW IS WHAT STARTS THE MODE, and copying anything else is
            # what ends it: the clipboard is the commander's statement of intent, so the
            # row it came from decides whether a route is being flown.
            if row.get("row_grp") == ROW_ROUTE:
                self.follow_route(row)
            else:
                if self.follow:
                    self.note("stopped following "
                              f"{self.chain_dest(self.follow['label'])}", "dim")
                self.follow = None
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
        self.took_clipboard(nxt)
        self.note(f"{name} {self.cursor + 1}: answered -- copied {nxt}", "ok")
        return True

    def took_clipboard(self, text):
        """`text` is now on the clipboard: remember it, and QUEUE the flash for the row.

        THE ONE PLACE `copied` IS SET, so the flash cannot miss a handover. It is the
        automatic ones that need saying: plot to the best system in an adjacent sector
        and the plot answers it, so the row leaves and advance_clipboard() hands over
        its successor while you are still alt-tabbed in the galaxy map. Coming back to
        a table that has quietly reshuffled, the flash is what says WHICH line is in
        the paste buffer -- a sector row especially, since what it copies is a system
        that is written nowhere until the cursor is on it.

        *** QUEUED, NOT PAINTED. *** advance_clipboard() runs BEFORE the repaint, on
        purpose -- it is the fast path, ahead of ~2 s of SQL -- so flashing here would
        light the row up where it is standing now and then the repaint would move it,
        which draws the eye to a line that is about to be somewhere else. The flash
        belongs to the moment BOTH things are true: the clipboard holds the name and
        the row has arrived at its new place. place_cursor() is where that happens, and
        _flash_copied() fires it from there.
        """
        # Remembered so place_cursor() can tell "my target moved" from "my target is
        # gone" -- the two need opposite responses.
        self.copied = text
        self._pending_flash = text
        # SOUNDED HERE, WITH THE FLASH, because this is the one place every copy passes
        # through -- a key, an answered row, a flown hop. Unlike the flash it is not
        # queued: the sound says the clipboard changed, which is true now, and holding
        # it back until the repaint would put it ~2 s after the key.
        notify.copied(enabled=not self.args.no_sound)

    def _flash_copied(self):
        """Fire the queued clipboard flash, now that the rows are where they belong.

        Every table is offered the name and only the row holding it flashes, so this
        needs no opinion about which table the cursor is in. A name no table holds any
        more -- the row left the list entirely -- simply flashes nothing.
        """
        text, self._pending_flash = self._pending_flash, None
        if text is None:
            return
        for _name, t in self.tables:
            t.flash([text], FLASH_COPIED)

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
          2. CHIME_CLASSES. BH, WR, Herbig and O-type sound unconditionally.
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
            self.confirmed.flash([n for n, _ in finds], FLASH_CONFIRM)
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
        boosted = self.jump_range * ship.neutron_boost(self.loadout)
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
                "row_grp": ROW_NEUTRON,
                "wide_text": "DESTINATION" if final else "-",
                "detail": None, "mass_code": None, "boxel": None,
                "x": x, "y": y, "z": z, "dist_sol": None, "star_class": None}

    def _copy_next_hop(self, prefix):
        """Put the next system on the route on the clipboard, and say so."""
        if not self.route:
            return
        nxt = self.route[0]["system"]
        if clipboard.copy(nxt, self.ui.root):
            # Through took_clipboard(), so the cursor FOLLOWS the hop instead of
            # fighting it. The clipboard has exactly one owner either way.
            self.took_clipboard(nxt)
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
        with self.timing.phase("clock"):
            self.update_clock()
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
            targets = [journal.class_of(e) for e in events
                       if e.get("event") in journal.CLASS_EVENTS]
            rows += [(n, c, None, None, None) for n, c in targets if n and c]
            # The LAST one wins: two targets in one poll window means the commander
            # retargeted, and the light follows the newest.
            if targets and targets[-1][0]:
                self.next_jump = targets[-1]
        self.record_revealed(rows, note=note)
        for e in events:
            if e.get("event") in journal.SHIP_EVENTS:
                self.take_loadout(e)
            if e.get("event") in journal.POS_EVENTS:
                self.on_position(e)
        # AFTER the events, not before. Both lights read state the loops above have
        # just moved -- the target and the system it is compared against -- and a
        # reading taken first is a tick behind on every jump.
        #
        # mtime-gated like the route: the game rewrites Status.json whenever anything
        # changes, so an unchanged reading costs one getmtime, and a fuel light two
        # seconds behind the gauge is a fuel light nobody trusts. The status is KEPT,
        # because the target can move on a tick the file did not.
        with self.timing.phase("lights"):
            status, self._status_mtime = journal.read_status(
                self.args.journal_dir, self._status_mtime)
            self._status = status if status is not None else self._status
            if self._status is not None:
                self.lights.fuel(lights.fuel_fraction(self._status, self.loadout))
                self.lights.target(self.targeted_class(self._status))
                self.lights.ship(self._status, self.loadout)
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
        # SEED THE MIDDLE LIGHT. The harvest is in file order, so the last row is the
        # jump targeted most recently -- without it the light stays dark after a
        # restart until the commander happens to target something new. Safe to seed
        # from an old journal because targeted_class() still needs Status.json's
        # Destination to name the same system before it lights anything.
        if harvested:
            self.next_jump = harvested[-1]
        asks = []
        if harvested:
            asks.append(Ask("record_seen",
                            ([(nm, cl, None, None, None) for nm, cl in harvested],)))
        asks.append(Ask("promote_confirmed"))
        asks.append(Ask("route_hops"))
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
        self.ui.every(KEY_POLL_MS, self.tick, on_error=self.tick_failed)
        try:
            self.ui.run()
        finally:
            # *** DARKEN THE LEDS ON THE WAY OUT. *** An override holds until the
            # throttle is power-cycled, so an overlay that just exits leaves whatever
            # it last wrote -- a flash and all -- lit on hardware nothing is driving.
            self.lights.clear()
            # Closes the database on the thread that owns it. Without this the
            # process can outlive its window.
            self.worker.stop()

    def _took_routes(self, r):
        """Take the DESTINATIONS out of whatever routes are stored. Startup only.

        The hops are ignored: a stored chain was solved for another position and another
        ship, and this one plots its own. What is worth keeping is the far end of each --
        a name and a position -- because `main.route` is the only table in the app-state
        database that knows where "Shinrarta Dezhra" is.
        """
        for route, hops in sorted((r.get("route_hops") or {}).items()):
            for end in (hops[0], hops[-1]):
                label = ROUTE_ALIAS.get(end["system"],
                                        end["system"].split()[0].upper())[:7]
                if end["x"] is not None:
                    self._dests[label] = (end["system"],
                                          (end["x"], end["y"], end["z"]))
        if not self._dests:
            self.note("no destinations -- main.route is empty or not loaded yet", "dim")
        else:
            print("destinations: " + ", ".join(
                f"{k} = {v[0]}" for k, v in sorted(self._dests.items())), flush=True)

    def _caught_up(self, r, harvested):
        """Startup's own request landed. Prints rather than notes: this is the log."""
        self._took_routes(r)
        if harvested:
            print(f"harvested {harvested} revealed class(es) from the journal, "
                  f"{len(r.get('record_seen') or [])} new", flush=True)
        if r.get("promote_confirmed"):
            print(f"promoted {r['promote_confirmed']} rare sighting(s) into the find "
                  f"log", flush=True)
        self.recount()

    def show_jump_range(self):
        """Read the ship's range and PRINT it. Nothing goes on screen.

        *** THE LOG, NOT THE HUD. *** It is a standing fact about the ship and it does
        not change while you fly, so on screen it was a line that never moved, taking
        width from tables whose rows move on every jump. In the log it is still there
        when you want it -- next to the keybinds and the startup counts, which is the
        rest of what this session decided about itself.

        Still READ here rather than dropped: SHIFT+N routes on `self.jump_range` and
        lights.py turns `FuelCapacity` into a fraction, so the loadout has to be parsed
        whether or not a number is displayed.

        Silent on failure BY DESIGN. A missing Loadout or an unrecognised drive means
        ship.py refused to guess, and the honest report of "we do not know your jump
        range" is nothing at all -- not a plausible number nobody can check in flight.

        Read once, at startup, like the keys. An outfitting change mid-session will not
        update it: the price of keeping a journal re-read off the paint path.
        """
        self.take_loadout(journal.read_loadout(self.args.journal_dir))

    def take_loadout(self, loadout):
        """A `Loadout` event -- this is the ship now. Re-range, and re-plot if it moved.

        *** THE JUMP RANGE IS NOT A STARTUP CONSTANT. *** Every neutron chain on screen
        is solved against it, so a ship swap or an outfitting change that is not picked
        up leaves the overlay plotting for a ship that is in storage. The game says so in
        `Loadout` and the tick now watches for it.

        The BOOST comes from the HULL: nothing in the game reports a supercharged range,
        so ship.neutron_boost() reads `Loadout.Ship` -- 6x in a Caspian, 4x in everything
        else. Swapping between the two changes every chain on screen by half.
        """
        if not loadout:
            return
        # Kept for lights.py, which needs FuelCapacity to turn tonnes into a fraction.
        self.loadout = loadout
        was = self.jump_range
        self.jump_range = ship.jump_range(loadout)
        if self.jump_range is None or was == self.jump_range:
            return
        text = ship.summary(loadout)
        if text:
            print(f"ship: {text}", flush=True)
        if was is not None:
            self.note(f"ship changed: {text} -- re-plotting", "ok")
        # The range every chain was solved at has moved, so every one of them is stale.
        # chain_stale() sees that on its own; this only has to ask.
        self._unsolvable.clear()
        self.solve_chains()

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
                   help="release the app-state database after this many idle seconds, "
                        "so etl/ can write it (default 30). The model database is not "
                        "held at all: the overlay reads a mirror of it inside the "
                        "app-state file")
    p.add_argument("--slow-ms", type=int, default=250, metavar="MS",
                   help="log a breakdown for any tick slower than this (default 250; "
                        "0 logs every tick, -1 switches timing off)")
    p.add_argument("--no-sound", action="store_true",
                   help="never play the confirm chime (the flash still runs)")
    p.add_argument("--no-lights", action="store_true",
                   help="do not drive the VKB throttle LEDs")
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
