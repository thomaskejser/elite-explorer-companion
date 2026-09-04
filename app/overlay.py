"""The frameless always-on-top window. Knows Tk; knows nothing about the data.

This is the shell only: borderless, topmost, translucent, anchored to the LEFT edge of
the screen, and draggable by its title bar. What goes inside is somebody else's problem
-- `body` is handed out as a plain Frame and this module never looks in it again.

LEFT EDGE BY DEFAULT. Nothing here grabs focus: the game must keep it, which is also
why the navigation keys are registered globally in hotkeys.py rather than bound to this
window. `set_visible()` hides the whole thing when Elite is not in front.
"""
import tkinter as tk

from .theme import EDGE_MARGIN, HELP_GAP, HELP_PAD, Fonts, Palette


class Overlay:
    """A borderless HUD window pinned to the left of the screen."""

    def __init__(self, title, fonts=None, opacity=0.85, x=None, y=None,
                 draggable=True, chrome=False):
        """`chrome=False` (the default) shows the table and nothing else.

        With no title bar there is nothing conventional to drag by, so
        `enable_drag_on()` exists to make the content itself the handle. The caller
        invokes it once the content is built, because the widgets it must bind do not
        exist yet at this point.

        `set_status()` and `set_footer()` stay callable and simply do nothing when the
        chrome is off. That keeps the decision in ONE place -- callers never branch on
        whether a status line happens to exist.
        """
        self.fonts = fonts or Fonts()
        self.chrome = chrome
        self.draggable = draggable
        self.root = tk.Tk()
        self.root.title(title)
        self.root.overrideredirect(True)          # no title bar, no border
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", opacity)
        self.root.config(bg=Palette.key)
        try:
            # Windows-only: paints Palette.key as fully transparent, which is what
            # turns a rectangle into a HUD. Harmless to skip elsewhere -- the overlay
            # just shows its background instead.
            self.root.attributes("-transparentcolor", Palette.key)
        except tk.TclError:
            pass

        self._drag_from = (0, 0)
        self._shown = True
        self.title = self.status = self.footer = None

        if chrome:
            bar = tk.Frame(self.root, bg=Palette.key)
            bar.pack(anchor="w", fill="x")
            self.title = tk.Label(bar, text=title, font=self.fonts.title,
                                  fg=Palette.head, bg=Palette.key)
            self.title.pack(side="left")
            self.status = tk.Label(bar, text="", font=self.fonts.small,
                                   fg=Palette.dim, bg=Palette.key)
            self.status.pack(side="right", padx=(8, 2))
            if draggable:
                for w in (bar, self.title, self.status):
                    self._bind_drag(w)

        self.body = tk.Frame(self.root, bg=Palette.key)
        self.body.pack(anchor="w", fill="both", expand=True)

        # THE HELP BAR, and it is NOT part of the chrome. With no title bar there is
        # nothing else on screen saying the overlay responds to keys at all, so this
        # line has to survive `--chrome` being off -- which is the default and the way
        # it is actually flown.
        #
        # A Frame of several Labels rather than one Label: a Tk Label is a single
        # foreground colour end to end, and the KEYS have to read as keycaps while the
        # prose stays dim. hotkeys.help_segments() decides where the joins go.
        self.help = tk.Frame(self.root, bg=Palette.key)
        self.help.pack(anchor="w", fill="x", pady=(HELP_GAP, 0))

        if chrome:
            self.footer = tk.Label(self.root, text="", font=self.fonts.small,
                                   fg=Palette.dim, bg=Palette.key, justify="left",
                                   anchor="w")
            self.footer.pack(anchor="w", fill="x")

        self._place(x, y)

    def enable_drag_on(self, widget):
        """Make `widget` and everything inside it a drag handle. Idempotent.

        Needed only when the chrome is off: with no title bar, the table IS the window.
        Binding the whole subtree rather than the frame alone matters because the grid
        cells cover nearly all of it, and a drag that only works in the gaps between
        labels reads as broken.
        """
        if not self.draggable:
            return
        self._bind_drag(widget)
        for child in widget.winfo_children():
            self.enable_drag_on(child)

    def _bind_drag(self, w):
        w.bind("<Button-1>", self._grab)
        w.bind("<B1-Motion>", self._drag)

    # -- placement -------------------------------------------------------------
    def _place(self, x, y):
        """Pin to the TOP-LEFT corner unless told otherwise.

        Both defaults are the same EDGE_MARGIN, so the HUD sits the same distance from
        each edge rather than being flush against the corner.

        *** TOP, NOT CENTRED. *** Four tables stack downward from here, so anchoring
        the top edge means a table that grows or appears extends into empty screen and
        the ones above it never move.

        Still placed after update_idletasks(): the geometry manager has to have run for
        the window to have a size at all, and a zero-size window can be placed
        somewhere Windows then declines to move it from.
        """
        self.root.update_idletasks()
        if x is None:
            x = EDGE_MARGIN
        if y is None:
            y = EDGE_MARGIN
        self.root.geometry(f"+{int(x)}+{int(y)}")

    def _grab(self, e):
        self._drag_from = (e.x, e.y)

    def _drag(self, e):
        dx, dy = self._drag_from
        self.root.geometry(f"+{self.root.winfo_x() + e.x - dx}"
                           f"+{self.root.winfo_y() + e.y - dy}")

    # -- content ---------------------------------------------------------------
    # No-ops when the chrome is off, so callers never have to ask whether it is.
    def set_status(self, text):
        if self.status is not None:
            self.status.config(text=text)

    def set_help(self, rows):
        """Draw the help bar from ROWS of CELLS of (text, role). Built once, at startup.

        The keys never change while the app runs, so this is not on any hot path -- it
        rebuilds the widgets rather than reconfiguring them, which keeps it to one pass.

        GRIDDED, so the columns line up. Each cell is its own Frame of packed labels:
        grid aligns widgets, and a bare run of labels has nothing to align.

        AN EMPTY CELL IS ABSORBED INTO THE SPAN OF THE ONE BEFORE IT. That is what lets
        a row carry something that is not a keybind -- a whole line of prose sitting
        under the keys it describes -- without that line's width being forced into the
        first column and dragging every column after it out of true.
        """
        for w in self.help.winfo_children():
            w.destroy()
        width = max((len(cells) for cells in rows), default=0)
        for r, cells in enumerate(rows):
            filled = [c for c, segments in enumerate(cells) if segments]
            for i, c in enumerate(filled):
                segments = cells[c]
                # To the next filled cell, or to the end of the row.
                span = (filled[i + 1] if i + 1 < len(filled) else width) - c
                cell = tk.Frame(self.help, bg=Palette.key)
                # padx on the grid rather than inside the labels: unlike a table row
                # there is no selection band here to come out striped, and the gap shows
                # Palette.key, which is what is behind the bar anyway.
                #
                # The pad alternates by column because the columns alternate: a KEY is
                # followed by the words describing it, a DESCRIPTION by the next keybind
                # entirely. theme.HELP_PAD holds both, since widths live there.
                cell.grid(row=r, column=c, columnspan=span, sticky="w",
                          padx=(0, HELP_PAD[c % len(HELP_PAD)]))
                for text, role in segments:
                    lbl = tk.Label(cell, text=text, font=self.fonts.small,
                                   fg=getattr(Palette, role), bg=Palette.key,
                                   anchor="w")
                    lbl.pack(side="left")
                    if self.draggable:
                        self._bind_drag(lbl)
                if self.draggable:
                    self._bind_drag(cell)
        if self.draggable:
            self._bind_drag(self.help)
        self._clamp_help_width()

    def _clamp_help_width(self):
        """*** THE TABLES DICTATE THE WIDTH OF THE OVERLAY, NOTHING ELSE. ***

        Tk sizes a window to fit its widest child, so one long line of help text sets
        how much of the cockpit the HUD covers -- and the help text is the least
        important thing on screen. Two columns is what makes it fit; this makes it
        STAY fitting, whatever a future key description does to it.

        Fixes the bar to the body's requested width and turns geometry propagation off,
        so anything too wide is CLIPPED rather than allowed to widen the window. Clipping
        the hint is the right failure: the hint is recoverable by reading this file, the
        window covering the canopy is not.

        Runs after the body exists and has been measured -- update_idletasks() forces
        that measurement now rather than at the next idle moment, which would be after
        the window has already been placed at the wrong size.
        """
        self.help.update_idletasks()
        want = self.body.winfo_reqwidth()
        if want > 1 and self.help.winfo_reqwidth() > want:
            self.help.config(width=want, height=self.help.winfo_reqheight())
            # *** grid_propagate, NOT pack_propagate. *** The cells inside are
            # GRIDDED, and each geometry manager has its own propagation switch:
            # turning off the one that is not managing these children is a silent
            # no-op and the clamp does nothing at all.
            self.help.grid_propagate(False)
            self.help.pack_propagate(False)

    def set_footer(self, text, role="dim"):
        if self.footer is not None:
            self.footer.config(text=text, fg=getattr(Palette, role))

    def every(self, ms, fn):
        """Run `fn` every `ms` milliseconds on the Tk event loop.

        The app's only scheduling primitive. Using Tk's own timer rather than a thread
        means widget updates happen on the thread that owns them, which is the one rule
        Tk actually enforces.
        """
        # Tk's after() rejects a float outright ("bad argument 2000.0"), and --poll is
        # a float so a fractional interval can be asked for. Coerce here, once, rather
        # than making every caller remember.
        ms = max(1, int(ms))

        def tick():
            fn()
            self.root.after(ms, tick)
        self.root.after(ms, tick)

    def set_visible(self, visible):
        """Show or hide the whole HUD. Idempotent; -> True if the state changed.

        withdraw()/deiconify() rather than alpha, because a fully transparent window
        still sits on top and still swallows nothing but is still composited. Topmost
        is re-asserted on the way back: Windows does not reliably preserve it across a
        withdraw, and a HUD that comes back UNDER the game is the same as gone.
        """
        if visible == self._shown:
            return False
        if visible:
            self.root.deiconify()
            self.root.attributes("-topmost", True)
        else:
            self.root.withdraw()
        self._shown = visible
        return True

    def run(self):
        self.root.mainloop()
