"""The target table widget. ONE header renderer and ONE row renderer, for every table.

Every table on screen -- Current sector, Confirmed, and whatever comes next -- is a
`TargetTable`, so they cannot drift apart: `build_header()` draws the heading row and
`render_row()` draws a data row, both walking the single `theme.COLUMNS` list. Adding a
column or changing a width is one edit in `theme.py` and every table follows.

It renders whatever dicts it is handed. It does no SQL and no ranking; `database.py`
decides what the rows are and this decides what they look like. The one thing it *does*
compute is the display form of a probability, because that is presentation: SQL hands
over raw doubles so thresholds and colour have a number to work with.

REFILLED, NOT REBUILT. Widgets are created once and only their text changes on update.
Destroying and recreating labels every jump makes the overlay flicker and slowly leaks
Tk objects -- the kind of thing that only shows up after an hour of flying.
"""
import tkinter as tk

import math

from .theme import (COLUMNS, COUNT_GRADIENT_MAX, COUNT_GRADIENT_MIN, FLASH_APPEAR,
                    FLASH_CONFIRM, FLASH_STEP_MS, FLASH_STEPS, GRADIENT, GRADIENT_MAX,
                    GRADIENT_MIN, MIN_SHOWN_PROBABILITY, PAD_X, Fonts, Palette, blend)

# A cell with no number: a probability below MIN_SHOWN_PROBABILITY, or a POI row, which
# is not a star at all. On a COUNT row it means zero -- see format_count, which
# deliberately does not apply the probability threshold. On a TALLY it means a kind
# nothing has confirmed yet.
BELOW_THRESHOLD = "-"

# database.ROW_* values. Duplicated as literals rather than imported so this module stays
# free of database: the mapping from row kind to appearance is a display decision.
KIND_CONFIRMED, KIND_POI, KIND_PREDICTED, KIND_CATALOG = -1, 0, 1, 2
KIND_TOTAL, KIND_CARRIER, KIND_SECTOR, KIND_NEUTRON = 3, 4, 5, 6
KIND_TOTAL_CATALOG = 7
# A real catalogued star we cannot match to any game system. Carries no probabilities
# and renders through `wide_text`, exactly as a carrier does.
KIND_UNFOUND = 8
# A STORED ROUTE, offered as one row per direction. Not a place: choosing it starts
# following that route, and what it copies is the hop to fly to next.
KIND_ROUTE = 9

# Row kinds whose colour overrides the per-column role.
#
# KIND_TOTAL_CATALOG SHARES "catalog" WITH KIND_CATALOG DELIBERATELY. A summary line and
# the rows it is summing should be the same colour, or the reader has to work out which
# total belongs to which half of the table by counting lines. The catalogued backfill
# rows are already the dimmest thing on screen; their total joins them there.
ROW_TINT = {KIND_CONFIRMED: "confirmed", KIND_POI: "poi",
            KIND_CATALOG: "catalog", KIND_TOTAL: "head", KIND_CARRIER: "carrier",
            KIND_SECTOR: "head", KIND_NEUTRON: "neutron",
            KIND_TOTAL_CATALOG: "catalog", KIND_UNFOUND: "unfound",
            # A control, not a value: `keycap` is the colour this HUD already uses for
            # something you press rather than something you read.
            KIND_ROUTE: "keycap"}

# Row kinds whose numbers are expected COUNTS rather than probabilities: a sector or
# region summed (TOTAL and TOTAL_CATALOG), or one next door (SECTOR). They render
# through format_count() and stay off the gradient -- a count is on an unbounded scale,
# so painting one green would be claiming something the scale cannot support.
#
# *** TOTAL_CATALOG MUST BE IN HERE. *** It differs from TOTAL only in colour; leaving
# it out would send a count of 74.60 expected Herbigs through format_probability(),
# which caps at two decimals on a 0-1 scale and would paint it full green as though it
# were a certainty.
COUNT_KINDS = frozenset({KIND_TOTAL, KIND_SECTOR, KIND_TOTAL_CATALOG})


def wide_span(columns):
    """-> (first column, how many) for the area a `wide_text` row writes across, or
    None when this layout has no such area.

    The prediction columns, so a carrier writes its name where a prediction row shows a
    line of dashes. Derived from the column list it is handed rather than from theme.py,
    so a table with its own layout cannot be given a stale span.

    *** NONE IS NOT (0, 1). *** A layout with no prediction cells has nowhere to put a
    span, and defaulting to column 0 lays the label over the SYSTEM cell -- which is
    how a carrier came to show its NAME where its system name belongs. Such a layout
    names `wide_text` as an ordinary column instead (Nearest calls it NAME), and the
    renderer must leave the span alone.
    """
    idx = [i for i, c in enumerate(columns) if c[5] == "prob"]
    return (idx[0], len(idx)) if idx else None


def format_probability(value):
    """A probability as it should appear in a cell. The ONE place this is decided.

    Only a genuine prediction reaches here: a totals row goes through format_count(),
    and a confirmed find has no probability cell to fill.
    """
    if value is None or value < MIN_SHOWN_PROBABILITY:
        return BELOW_THRESHOLD
    return f"{value:.2f}"


def format_count(value):
    """An expected COUNT, as it should appear in a totals cell.

    The same numbers the other rows show as probabilities, summed across the sector --
    a probability IS an expected count, and summing them is legitimate in a way that
    combining two of them on ONE row is not.

    TWO DECIMALS, exactly as the probability cells use, so every number in the column
    has its point in the same place and the column reads as one thing.

    *** MIN_SHOWN_PROBABILITY IS NOT APPLIED HERE. *** That threshold means "this
    probability is too small to be worth considering", which is a statement about ONE
    system's odds; a count is on an unbounded scale and describes a whole sector, so
    0.0099 expected black holes is the sum of everything left rather than a negligible
    figure -- and it is the number you compare against the sector above.

    A dash therefore means ONLY "nothing at all": no rows, or a genuine zero. Anything
    positive that would round away shows as "<0.01", because "0.00" claims a precision
    the sum does not have while a dash claims an emptiness that is false.
    """
    if value is None or value == 0:
        return BELOW_THRESHOLD
    if value < 0.005:
        return "<0.01"
    return f"{value:.2f}"


def format_tally(value):
    """A COUNT OF ROWS -- how many systems of one kind are confirmed and still
    uncollected. Thousands-separated; a dash means the kind has none at all."""
    if not value:
        return BELOW_THRESHOLD
    return f"{value:,}"


def format_distance(value, approx=False):
    """Light-years, whole numbers with thousands separators. The ONE place this is set.

    No decimals: at 12,000 ly nobody cares about the fraction, and at 40 ly the jump
    range decides the route anyway.

    A leading '~' means the coordinates are a BOXEL CENTROID rather than a position --
    good to about +/-640 ly at mass code h. POIs and catalogued systems come from the
    dumps with exact coordinates and get a plain number; only boxel-predicted rows are
    marked, because for those the distance really is a guess.

    A dash means unlocated, which is not the same as near.
    """
    if value is None:
        return BELOW_THRESHOLD
    return f"~{value:,.0f}" if approx else f"{value:,.0f}"


def cell_text(row, attr, kind, width, selected=False):
    """The string for one cell, truncated to fit. The ONE place a value becomes text.

    `selected` exists for one case. An Adjacent sectors row displays a SECTOR but copies
    the best SYSTEM inside it, so what is on the clipboard is never written anywhere --
    you have to trust the footer. While the cursor is on such a row its SYSTEM cell
    shows the full destination instead, so the thing you are about to paste is on
    screen, in the row it came from.

    NOTHING IS LOST BY THE SWAP: a system name begins with its sector name, so
    "Preae Chruia" simply becomes "Preae Chruia FG-Y g7". It fits, too -- across all
    61,763 boxel-predicted systems only two names exceed the 24-wide column.
    """
    # ALREADY THERE. A row whose destination is the system the ship is in has nothing
    # left to jump to, so the cell says what is useful on arrival instead -- for a
    # carrier, which ship in orbit this row was about.
    if kind == "text" and attr == "system" and row is not None             and row.get("arrived_text"):
        text = row["arrived_text"]
        return text if len(text) <= width else text[:width - 1] + "…"
    if (kind == "text" and attr == "system" and selected
            and row is not None
            and row.get("row_grp") == KIND_SECTOR
            and row.get("copy_text")):
        text = row["copy_text"]
        return text if len(text) <= width else text[:width - 1] + "…"
    if kind == "prob":
        text = (format_count(row.get(attr))
                if row.get("row_grp") in COUNT_KINDS
                else format_probability(row.get(attr)))
    elif kind == "tally":
        text = format_tally(row.get(attr))
    elif kind == "dist":
        text = format_distance(row.get(attr), row.get("dist_approx"))
    else:
        text = "" if row.get(attr) is None else str(row[attr])
    # Truncate rather than let a long system name push the columns rightwards -- a HUD
    # that changes width every jump is unreadable.
    return text if len(text) <= width else text[:width - 1] + "…"


def gradient_colour(value):
    """Red (low) through orange and yellow to green (high). The ONE value->colour map.

    Linear over [GRADIENT_MIN, GRADIENT_MAX] and clamped at both ends, so a given
    probability is always the same colour -- the point is to read a cell at a glance
    without reading the number, which only works if the mapping is fixed.
    """
    span = GRADIENT_MAX - GRADIENT_MIN
    frac = (value - GRADIENT_MIN) / span if span else 0.0
    i = int(frac * len(GRADIENT))
    return GRADIENT[min(max(i, 0), len(GRADIENT) - 1)]


def count_colour(value):
    """The gradient for an expected COUNT -- a sector total, or a neighbouring sector.

    Logarithmic over [COUNT_GRADIENT_MIN, COUNT_GRADIENT_MAX] and clamped, so a 10x
    richer sector sits a fixed number of steps further up whatever the absolute
    numbers are. Shares the ten colours with the probability ramp on purpose: the
    reader learns one colour language, and both ramps answer "more or less of what I
    am looking for". The adjacent-sector table exists to answer "is anywhere next door
    better than here", and a ramp says that at a glance where ten grey numbers do not.
    """
    if value is None or value <= 0:
        return Palette.dim
    lo, hi = math.log10(COUNT_GRADIENT_MIN), math.log10(COUNT_GRADIENT_MAX)
    frac = (math.log10(max(value, 1e-9)) - lo) / (hi - lo) if hi > lo else 0.0
    i = int(frac * len(GRADIENT))
    return GRADIENT[min(max(i, 0), len(GRADIENT) - 1)]


def cell_colour(row, attr, role, kind="text"):
    """The colour for one cell. The ONE place emphasis is decided.

    TWO THINGS CARRY COLOUR, AND NOTHING ELSE DOES:

      SYSTEM   the row KIND: confirmed (bright green), POI, catalogued backfill. This
               is the cell that says "this system is a different sort of thing".
      numbers  the probability gradient.

    Everything else stays on its column's default. The row tint is confined to SYSTEM:
    spread across every cell it would leave almost nothing on screen at its normal
    colour, and stop meaning anything by being everywhere.
    """

    grp = row.get("row_grp")
    value = row.get(attr)
    scored = kind == "prob" and grp not in COUNT_KINDS

    if scored:
        if value is not None and value >= MIN_SHOWN_PROBABILITY:
            return gradient_colour(value)
        # A dash means "nothing here" and must look the same in every column -- falling
        # through to the column role would paint the WOLF-RAY dash gold and the
        # HERBIG dash grey on one row, as though the gold one meant something.
        return Palette.dim

    if attr == "system":
        tint = ROW_TINT.get(grp)
        if tint:
            return getattr(Palette, tint)
        # An ordinary prediction whose class the galaxy map has already revealed is not
        # a gamble, so its name dims.
        if row.get("star_class"):
            return Palette.dim
        return getattr(Palette, role)

    if attr == "type_label" and row.get("mass_code") == "h":
        return Palette.hot
    # Totals and neighbouring-sector counts: the COUNT ramp, not the probability one.
    # See count_colour() -- same colours, log scale, so "richer" reads at a glance
    # without pretending 0.6 expected objects is a 60% chance of anything.
    if grp in COUNT_KINDS:
        return count_colour(value) if kind == "prob" else Palette.dim
    return getattr(Palette, role)


class TargetTable:
    """A titled `rows` x len(COLUMNS) grid of labels."""

    def __init__(self, parent, rows=10, fonts=None, title=None,
                 hide_when_empty=False, before=None, wide_heading=None,
                 flash_new=False, columns=None, pack_opts=None):
        """`columns` is the layout, defaulting to every column theme.py defines.

        A table may take a SUBSET -- Confirmed takes theme.CONFIRMED_COLUMNS, the text
        columns and the tally with no predictions, so it draws narrow. It is still the
        same two renderers walking the same tuples; only the list differs.

        `pack_opts` is how the container packs itself, for a table that is not simply
        another full-width row of the window: Nearest sits to the RIGHT of Confirmed
        inside a frame of their own, so the two of them share one line.

        `wide_heading` replaces the prediction headings with one label.

        For a table whose rows are all WIDE -- carriers, which have no predictions --
        the prediction headings describe columns that are never filled. Naming the span
        once, here, keeps the header honest: whatever the rows put in that area is what
        the heading says it is.

        `flash_new` makes the table flash any row whose system was not in the previous
        fill. For Confirmed that is the point: a find can be revealed by a route plot
        thousands of light years away, with nothing on screen moving except one new
        line, and the flash is what says a line arrived.
        """
        self.fonts = fonts or Fonts()
        self.columns = columns or COLUMNS
        span = wide_span(self.columns)
        self.wide_from, self.wide_span = span or (0, 0)
        self.has_span = span is not None
        self.wide_heading = wide_heading
        self.n_rows = rows
        # WHICH ROW THE CURSOR IS ON, or None for "not this table". Pure UI state: the
        # query has no opinion about it, and it survives a repaint so a refresh does
        # not move the cursor out from under you.
        self.selected = None
        self._rows = []
        # system name -> [highlight colour, step], for the rows flashing right now.
        # Held on the table rather than on the row dicts because a refresh REPLACES
        # those dicts: the flash has to survive the repaint its own event triggers.
        self._flash = {}
        self._flash_job = None
        self.flash_new = flash_new
        # The systems the LAST fill held, or None before the first one. None and empty
        # are different: the first fill flashes nothing, or the overlay would flash
        # every row it has the moment it starts.
        self._keys = None
        self.hide_when_empty = hide_when_empty
        self._before = before          # keeps pack order when re-shown after hiding
        self._pack_opts = pack_opts or {"anchor": "w", "fill": "x"}
        self._visible = False

        self.container = tk.Frame(parent, bg=Palette.key)
        self.title = None
        if title:
            self.title = tk.Label(self.container, text=title, font=self.fonts.title,
                                  fg=Palette.head, bg=Palette.key, anchor="w")
            self.title.pack(anchor="w", fill="x")
        self.frame = tk.Frame(self.container, bg=Palette.key)
        self.frame.pack(anchor="w", fill="x")

        self.build_header()
        self._cells = [self.build_row(r) for r in range(1, rows + 1)]
        self._show_container(True)

    # -- the two renderers everything shares -----------------------------------
    def build_header(self):
        """Draw the heading row. One function, every table.

        With `wide_heading` set, the prediction headings are dropped and a single
        spanning label takes their place -- so a carrier table says "CARRIER NAME" over
        the area its rows actually use, instead of eight column names that will never
        hold a number.
        """
        for c, (_attr, heading, width, anchor, _role, kind) in enumerate(self.columns):
            if self.wide_heading and kind == "prob":
                continue
            tk.Label(self.frame, text=heading, width=width, anchor=anchor,
                     font=self.fonts.head, fg=Palette.head, bg=Palette.key,
                     padx=PAD_X // 2).grid(row=0, column=c, sticky="w")
        if self.wide_heading and self.has_span:
            tk.Label(self.frame, text=self.wide_heading, anchor="w",
                     font=self.fonts.head, fg=Palette.head, bg=Palette.key,
                     padx=PAD_X // 2).grid(row=0, column=self.wide_from,
                                           columnspan=self.wide_span, sticky="w")

    def build_row(self, r):
        """Create the labels for one data row. -> (cells, wide label).

        The wide label sits on top of the whole prediction area and is hidden by
        default. A carrier has no predictions to show there, so rather than print eight
        dashes it gets one field wide enough for a carrier name -- which is the only
        thing worth knowing once you have arrived.
        """
        cells = []
        for c, (_attr, _heading, width, anchor, role, _kind) in enumerate(self.columns):
            lbl = tk.Label(self.frame, text="", width=width, anchor=anchor,
                           font=self.fonts.row, fg=getattr(Palette, role),
                           bg=Palette.key, padx=PAD_X // 2)
            # sticky="we" so the label fills its grid cell: without it a short label
            # leaves bare container either side and the selection band gets gaps.
            lbl.grid(row=r, column=c, sticky="we")
            cells.append(lbl)
        if not self.has_span:
            return cells, None
        wide = tk.Label(self.frame, text="", anchor="w", font=self.fonts.row,
                        fg=Palette.carrier, bg=Palette.key, padx=PAD_X // 2)
        wide.grid(row=r, column=self.wide_from, columnspan=self.wide_span,
                  sticky="we")
        wide.grid_remove()
        return cells, wide

    def flash(self, names, colour=FLASH_CONFIRM):
        """Start a flash on every row named in `names`. A name the table does not hold
        is ignored, so a caller may flash all four tables and let the rows answer.

        A NAME IS EITHER THE DISPLAYED SYSTEM OR THE COPIED ONE. An Adjacent sectors row
        displays a sector and copies the best system inside it, so a clipboard flash
        arrives under a string that appears nowhere in the SYSTEM column.

        Driven by Tk's own `after` at FLASH_STEP_MS, NOT by the app's 2-second tick: an
        animation on the tick would be four frames a second, which is a stutter rather
        than a fade. One job at a time -- a second event while the first is still fading
        joins the same schedule instead of starting a competing one.
        """
        if not names:
            return
        for name in names:
            self._flash[name] = [colour, 0]
        # PAINT FRAME 0 NOW, then schedule frame 1. Scheduling first would step the
        # index before anything was drawn, and the brightest frame -- the one the eye is
        # supposed to catch -- would never appear on screen.
        self._paint()
        if self._flash_job is None:
            self._flash_job = self.container.after(FLASH_STEP_MS, self._step_flash)

    def _step_flash(self):
        """Advance every flashing row one step; repaint; reschedule or stop."""
        self._flash_job = None
        for name in [n for n, (_c, i) in self._flash.items() if i >= FLASH_STEPS - 1]:
            del self._flash[name]
        for state in self._flash.values():
            state[1] += 1
        self._paint()
        if self._flash:
            self._flash_job = self.container.after(FLASH_STEP_MS, self._step_flash)

    def flash_colour(self, row, natural):
        """`natural`, faded up from the highlight, or None when the row is not flashing.

        The fade ENDS on the colour the cell would have had anyway, so a flash never
        leaves a row a colour it does not settle at -- which is what lets one animation
        serve a confirmed find, a new arrival and a clipboard handover alike.
        """
        if not self._flash or row is None:
            return None
        state = (self._flash.get(row.get("system"))
                 or self._flash.get(row.get("copy_text")))
        if state is None:
            return None
        colour, step = state
        return blend(colour, natural, min(step, FLASH_STEPS) / FLASH_STEPS)

    def render_row(self, pair, row, selected=False):
        """Fill one data row, or blank it when `row` is None. Used by every table.

        `selected` paints the SELECTION BAND: every cell of the row takes sel_bg as its
        background instead of the transparency key, which is what turns a row into a
        continuous highlighted stripe. The foreground colours are untouched -- the band
        says WHERE the cursor is and the text colours go on saying what the row is.
        """
        cells, wide = pair
        # Only where there IS a span. Without one the layout gives `wide_text` a column
        # of its own and this must not draw it a second time, on top of another cell.
        text = row.get("wide_text") if (row and self.has_span) else None
        bg = Palette.sel_bg if selected and row is not None else Palette.key
        for c, (attr, _heading, width, _anchor, role, kind) in enumerate(self.columns):
            # A wide row hides the cells it spans, or they would show through it.
            if text and kind == "prob":
                cells[c].grid_remove()
                continue
            cells[c].grid()
            if row is None:
                cells[c].config(text="", fg=getattr(Palette, role), bg=bg)
            else:
                # THE FLASH OVERRIDES ONE CELL, NOT THE ROW. Tinting every cell would
                # wash out the probabilities at exactly the moment they are worth
                # reading, and the system name is what the commander copies anyway.
                natural = cell_colour(row, attr, role, kind)
                flash = self.flash_colour(row, natural) if attr == "system" else None
                cells[c].config(text=cell_text(row, attr, kind, width, selected),
                                fg=flash or natural, bg=bg)
        if wide is None:                 # a layout with no span never built one
            return
        if text:
            wide.config(text=text, bg=bg)
            wide.grid()
        else:
            wide.grid_remove()

    # -- updating ---------------------------------------------------------------
    def show(self, rows):
        """Fill the grid from `rows`; blank any spare row. Hides if empty and asked."""
        self._rows = rows
        self._note_arrivals(rows)
        if self.hide_when_empty and not rows:
            self._show_container(False)
            return
        self._show_container(True)
        self._paint()

    def _note_arrivals(self, rows):
        """Flash whatever `rows` holds that the last fill did not. Off unless asked for.

        MEMBERSHIP ONLY, never the values. Every row's distance changes on every jump,
        so flashing a changed cell would flash the whole table each time the ship moves,
        and a signal that fires constantly says nothing.
        """
        keys = {r.get("system") for r in rows if r.get("system")}
        if self.flash_new and self._keys is not None:
            self.flash(keys - self._keys, FLASH_APPEAR)
        self._keys = keys

    def _paint(self):
        for i, pair in enumerate(self._cells):
            row = self._rows[i] if i < len(self._rows) else None
            self.render_row(pair, row, selected=(i == self.selected))

    def set_selected(self, index):
        """Move the cursor to grid row `index`, or None to clear it. Repaints.

        Cheap enough to call on every keypress: it only reconfigures existing labels,
        and the table is at most eleven rows.
        """
        if index == self.selected:
            return
        self.selected = index
        if self._visible or not self.hide_when_empty:
            self._paint()

    def set_title(self, text):
        """Retitle the table. Used to show a count, and -- more importantly -- to say
        when there are more rows than the grid can display, so truncation is never
        silent."""
        if self.title is not None:
            self.title.config(text=text)

    def blank(self):
        self.show([])

    def _show_container(self, visible):
        if visible == self._visible:
            return
        if visible:
            # `before` matters: pack() appends, so a table re-shown after hiding would
            # jump to the BOTTOM of the window without it. Confirmed must stay on top.
            #
            # But only if the reference table is on screen RIGHT NOW -- pack() raises if
            # it is not, and every hide_when_empty table spends some of its life
            # unpacked. Appending is the correct answer in that case anyway: if the
            # table we are supposed to sit above is hidden, last IS above it.
            if self._before is not None and self._before.winfo_manager() == "pack":
                self.container.pack(before=self._before, **self._pack_opts)
            else:
                self.container.pack(**self._pack_opts)
        else:
            self.container.pack_forget()
        self._visible = visible
