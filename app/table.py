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

from .theme import (COLUMNS, COUNT_GRADIENT_MAX, COUNT_GRADIENT_MIN, FLASH_RAMP,
                    FLASH_STEP_MS, GRADIENT, GRADIENT_MAX, GRADIENT_MIN,
                    MIN_SHOWN_PROBABILITY, PAD_X, Fonts, Palette)

# Placeholders for a cell with no number. They are different on purpose:
#   '--'  the value is KNOWN not to apply -- a confirmed find needs no probability,
#         the game has already said what is there.
#   '-'   a probability below MIN_SHOWN_PROBABILITY, or a POI row, which is not a star
#         at all. On a COUNT row it means zero -- see format_count, which deliberately
#         does not apply the probability threshold.
NOT_APPLICABLE = "--"
BELOW_THRESHOLD = "-"
# U+2713. A confirmed row puts this in the ONE column matching what the game revealed,
# so the same column reads "0.40, we think" on a prediction and "yes" on a
# confirmation. The other seven stay "--": the arrival star settles one question, not
# eight, and 0.00 there would be a claim nobody made.
CONFIRMED_MARK = "✓"

# database.ROW_* values. Duplicated as literals rather than imported so this module stays
# free of database: the mapping from row kind to appearance is a display decision.
KIND_CONFIRMED, KIND_POI, KIND_PREDICTED, KIND_CATALOG = -1, 0, 1, 2
KIND_TOTAL, KIND_CARRIER, KIND_SECTOR, KIND_NEUTRON = 3, 4, 5, 6
KIND_TOTAL_CATALOG = 7
# A real catalogued star we cannot match to any game system. Carries no probabilities
# and renders through `wide_text`, exactly as a carrier does.
KIND_UNFOUND = 8

# Row kinds whose colour overrides the per-column role.
#
# KIND_TOTAL_CATALOG SHARES "catalog" WITH KIND_CATALOG DELIBERATELY. A summary line and
# the rows it is summing should be the same colour, or the reader has to work out which
# total belongs to which half of the table by counting lines. The catalogued backfill
# rows are already the dimmest thing on screen; their total joins them there.
ROW_TINT = {KIND_CONFIRMED: "confirmed", KIND_POI: "poi",
            KIND_CATALOG: "catalog", KIND_TOTAL: "head", KIND_CARRIER: "carrier",
            KIND_SECTOR: "head", KIND_NEUTRON: "neutron",
            KIND_TOTAL_CATALOG: "catalog", KIND_UNFOUND: "unfound"}

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

# Index of the first probability column and how many there are -- the span a "wide"
# row writes across instead of showing eight dashes. Derived from COLUMNS so adding a
# prediction cannot leave the span stale.
_PROB_IDX = [i for i, c in enumerate(COLUMNS) if c[5] == "prob"]
WIDE_FROM, WIDE_SPAN = (_PROB_IDX[0], len(_PROB_IDX)) if _PROB_IDX else (0, 1)


def format_probability(value):
    """A probability as it should appear in a cell. The ONE place this is decided.

    Confirmed rows never reach here -- they render a checkmark or "--" instead, decided
    in cell_text() -- so this only ever handles a genuine prediction.
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
    if (kind == "text" and attr == "system" and selected
            and row is not None
            and row.get("row_grp") == KIND_SECTOR
            and row.get("copy_text")):
        text = row["copy_text"]
        return text if len(text) <= width else text[:width - 1] + "…"
    if kind == "prob":
        grp = row.get("row_grp")
        if grp in COUNT_KINDS:
            text = format_count(row.get(attr))
        elif grp == KIND_CONFIRMED:
            text = (CONFIRMED_MARK if attr == row.get("confirmed_col")
                    else NOT_APPLICABLE)
        else:
            text = format_probability(row.get(attr))
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

    THREE THINGS CARRY COLOUR, AND NOTHING ELSE DOES:

      SYSTEM   the row KIND: confirmed (bright green), POI, catalogued backfill. This
               is the cell that says "this system is a different sort of thing".
      numbers  the probability gradient -- and the confirmed checkmark, which takes the
               same bright green as the system name so the eye pairs them.

    Everything else stays on its column's default. The row tint is confined to SYSTEM:
    spread across every cell it would leave almost nothing on screen at its normal
    colour, and stop meaning anything by being everywhere.
    """

    grp = row.get("row_grp")
    value = row.get(attr)
    scored = kind == "prob" and grp not in COUNT_KINDS

    if kind == "prob" and grp == KIND_CONFIRMED:
        # The checkmark, in the confirmed green. The seven "--" beside it stay dim so
        # the single mark is what the eye lands on.
        return (Palette.confirmed if attr == row.get("confirmed_col")
                else Palette.dim)

    if scored:
        if value is not None and value >= MIN_SHOWN_PROBABILITY:
            return gradient_colour(value)
        # A dash means "nothing here" and must look the same in every column -- falling
        # through to the column role would paint the WOLF-RAY dash gold and the
        # SUPERGNT dash grey on one row, as though the gold one meant something.
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
                 hide_when_empty=False, before=None, wide_heading=None):
        """`wide_heading` replaces the seven prediction headings with one label.

        For a table whose rows are all WIDE -- carriers, which have no predictions --
        the prediction headings describe columns that are never filled. Naming the span
        once, here, keeps the header honest: whatever the rows put in that area is what
        the heading says it is.
        """
        self.fonts = fonts or Fonts()
        self.wide_heading = wide_heading
        self.n_rows = rows
        # WHICH ROW THE CURSOR IS ON, or None for "not this table". Pure UI state: the
        # query has no opinion about it, and it survives a repaint so a refresh does
        # not move the cursor out from under you.
        self.selected = None
        self._rows = []
        # system name -> index into FLASH_RAMP, for rows confirmed moments ago. Held on
        # the table rather than on the row dicts because a refresh REPLACES those dicts:
        # the flash has to survive the repaint that the confirmation itself triggers.
        self._flash = {}
        self._flash_job = None
        self.hide_when_empty = hide_when_empty
        self._before = before          # keeps pack order when re-shown after hiding
        self._visible = False

        self.container = tk.Frame(parent, bg=Palette.key)
        self.title = self.title_right = None
        if title:
            # A ROW, not a single Label, so something can sit at the far right of the
            # heading. A Tk Label is one string end to end: right-aligning a suffix
            # inside one would mean padding with spaces to a pixel width the font
            # decides, which breaks the moment the font or the column set changes.
            bar = tk.Frame(self.container, bg=Palette.key)
            bar.pack(anchor="w", fill="x")
            self.title = tk.Label(bar, text=title, font=self.fonts.title,
                                  fg=Palette.head, bg=Palette.key, anchor="w")
            self.title.pack(side="left")
            # Dim, not `head`: it is a standing fact about the ship, not a name for the
            # rows underneath, and it must not compete with the title it shares a line
            # with. Empty and therefore invisible unless someone sets it.
            self.title_right = tk.Label(bar, text="", font=self.fonts.small,
                                        fg=Palette.dim, bg=Palette.key, anchor="e")
            self.title_right.pack(side="right", padx=(8, PAD_X))
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
        for c, (_attr, heading, width, anchor, _role, kind) in enumerate(COLUMNS):
            if self.wide_heading and kind == "prob":
                continue
            tk.Label(self.frame, text=heading, width=width, anchor=anchor,
                     font=self.fonts.head, fg=Palette.head, bg=Palette.key,
                     padx=PAD_X // 2).grid(row=0, column=c, sticky="w")
        if self.wide_heading:
            tk.Label(self.frame, text=self.wide_heading, anchor="w",
                     font=self.fonts.head, fg=Palette.head, bg=Palette.key,
                     padx=PAD_X // 2).grid(row=0, column=WIDE_FROM,
                                           columnspan=WIDE_SPAN, sticky="w")

    def build_row(self, r):
        """Create the labels for one data row. -> (cells, wide label).

        The wide label sits on top of the whole prediction area and is hidden by
        default. A carrier has no predictions to show there, so rather than print eight
        dashes it gets one field wide enough for a carrier name -- which is the only
        thing worth knowing once you have arrived.
        """
        cells = []
        for c, (_attr, _heading, width, anchor, role, _kind) in enumerate(COLUMNS):
            lbl = tk.Label(self.frame, text="", width=width, anchor=anchor,
                           font=self.fonts.row, fg=getattr(Palette, role),
                           bg=Palette.key, padx=PAD_X // 2)
            # sticky="we" so the label fills its grid cell: without it a short label
            # leaves bare container either side and the selection band gets gaps.
            lbl.grid(row=r, column=c, sticky="we")
            cells.append(lbl)
        wide = tk.Label(self.frame, text="", anchor="w", font=self.fonts.row,
                        fg=Palette.carrier, bg=Palette.key, padx=PAD_X // 2)
        wide.grid(row=r, column=WIDE_FROM, columnspan=WIDE_SPAN, sticky="we")
        wide.grid_remove()
        return cells, wide

    def flash(self, names):
        """Start the confirm flash on every row whose system is in `names`.

        Driven by Tk's own `after` at FLASH_STEP_MS, NOT by the app's 2-second tick: an
        animation on the tick would be four frames a second, which is a stutter rather
        than a fade. One job at a time -- a second confirmation while the first is still
        fading joins the same schedule instead of starting a competing one.
        """
        if not names:
            return
        for name in names:
            self._flash[name] = 0
        # PAINT FRAME 0 NOW, then schedule frame 1. Scheduling first would step the
        # index before anything was drawn, and the brightest frame -- the white one the
        # eye is supposed to catch -- would never appear on screen.
        self._paint()
        if self._flash_job is None:
            self._flash_job = self.container.after(FLASH_STEP_MS, self._step_flash)

    def _step_flash(self):
        """Advance every flashing row one step; repaint; reschedule or stop."""
        self._flash_job = None
        done = [n for n, i in self._flash.items() if i >= len(FLASH_RAMP) - 1]
        for n in done:
            del self._flash[n]
        for n in list(self._flash):
            self._flash[n] += 1
        self._paint()
        if self._flash:
            self._flash_job = self.container.after(FLASH_STEP_MS, self._step_flash)

    def flash_colour(self, row):
        """The flash colour for this row, or None when it is not flashing."""
        if not self._flash or row is None:
            return None
        i = self._flash.get(row.get("system"))
        return FLASH_RAMP[min(i, len(FLASH_RAMP) - 1)] if i is not None else None

    def render_row(self, pair, row, selected=False):
        """Fill one data row, or blank it when `row` is None. Used by every table.

        `selected` paints the SELECTION BAND: every cell of the row takes sel_bg as its
        background instead of the transparency key, which is what turns a row into a
        continuous highlighted stripe. The foreground colours are untouched -- the band
        says WHERE the cursor is and the text colours go on saying what the row is.
        """
        cells, wide = pair
        text = row.get("wide_text") if row else None
        bg = Palette.sel_bg if selected and row is not None else Palette.key
        for c, (attr, _heading, width, _anchor, role, kind) in enumerate(COLUMNS):
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
                flash = self.flash_colour(row) if attr == "system" else None
                cells[c].config(text=cell_text(row, attr, kind, width, selected),
                                fg=flash or cell_colour(row, attr, role, kind), bg=bg)
        if text:
            wide.config(text=text, bg=bg)
            wide.grid()
        else:
            wide.grid_remove()

    # -- updating ---------------------------------------------------------------
    def show(self, rows):
        """Fill the grid from `rows`; blank any spare row. Hides if empty and asked."""
        self._rows = rows
        if self.hide_when_empty and not rows:
            self._show_container(False)
            return
        self._show_container(True)
        self._paint()

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

    def set_title_right(self, text):
        """Put `text` at the far right of the heading line. No-op without a title.

        Separate from set_title() because the two change on completely different
        clocks: the left side is retitled on every repaint to carry the row count,
        the right side is written once. Folding them together would mean every
        repaint had to remember to pass the right-hand text through or silently
        erase it.
        """
        if self.title_right is not None:
            self.title_right.config(text=text or "")

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
                self.container.pack(anchor="w", fill="x", before=self._before)
            else:
                self.container.pack(anchor="w", fill="x")
        else:
            self.container.pack_forget()
        self._visible = visible
