"""Global navigation keys. The only module that knows about the `keyboard` library.

SIX KEYS:

    PAGE DOWN / PAGE UP   move to the next / previous table
    DOWN / UP             move to the next / previous row of that table
    SHIFT + BACKSPACE     the selected system DOES NOT EXIST -- the galaxy map
                          refused to plot to it. The only key that writes anything.
    SHIFT + N             plot a neutron-boosted route to the selected row, or clear
                          the one that is up.

A CURSOR RATHER THAN A KEY PER ROW: rows reorder and drop out as they are answered, so
a per-row chord would mean somewhere else a minute later, while a cursor stays wherever
you last put it.

GLOBAL, not Tk bindings: the overlay never has focus. Elite Dangerous does, and the
whole point is to press a key while flying. A `root.bind("<Down>", ...)` would only fire
when the HUD itself is focused, which is never.

*** AND THAT IS EXACTLY WHY THE CALLER MUST GATE ON FOCUS. *** These are ARROW KEYS. A
global hook on them fires while you are typing in an editor, scrolling a browser, or
renaming a file -- and every one of those presses would move the cursor and overwrite
your clipboard. main.py checks focus.is_foreground() before draining a press, and that
check is not optional.

suppress=False throughout: the game may want the arrows too, and swallowing them would
break the galaxy map for the sake of a HUD.

*** THE CALLBACK FIRES ON THE `keyboard` HOOK THREAD, AND TK IS NOT THREAD-SAFE. ***
Touching a widget or the Tk clipboard from there is a cross-thread call into Tk and
will eventually crash or hang. So this class does the one safe thing: it records the
press in a slot, and the Tk event loop drains that slot on its normal tick.

The library needs no elevation for ordinary keys, but a locked-down machine can refuse
the hook. Failure is reported and NOT fatal: the overlay is still worth having as a
display.
"""
try:
    import keyboard
except ImportError:               # pragma: no cover - optional dependency
    keyboard = None

# The things a press can mean. Names, not key spellings, so main.py never has to
# know which physical key did it.
NEXT_TABLE, PREV_TABLE = "next_table", "prev_table"
NEXT_ROW, PREV_ROW = "next_row", "prev_row"
# The fifth, and the only one that WRITES: "I tried to plot a route to this and the
# galaxy map would not take it." SHIFT+BACKSPACE rather than a bare key because it is
# the one press that cannot be undone by pressing something else, and because a bare
# BACKSPACE is bound to something in every text field on the machine.
MARK_WRONG = "mark_wrong"
# The sixth. A TOGGLE, not a one-shot: press it on a row to plot a neutron-boosted route
# there, press it again to tear the route down. SHIFT+N rather than a bare N because a
# bare letter is unusable as a global hook -- it fires in every text field on the machine
# -- and because it shares the SHIFT+ shape with the other key that changes state.
NEUTRON_ROUTE = "neutron_route"

# key chord -> action. `keyboard`'s own spelling for the page keys is two words.
DEFAULT_BINDINGS = {
    "page down":      NEXT_TABLE,
    "page up":        PREV_TABLE,
    "down":           NEXT_ROW,
    "up":             PREV_ROW,
    "shift+backspace": MARK_WRONG,
    "shift+n":        NEUTRON_ROUTE,
}

# How each action reads in the startup log and in a "no target" message.
DESCRIPTION = {
    PREV_TABLE: "previous table", NEXT_TABLE: "next table",
    PREV_ROW: "previous row", NEXT_ROW: "next row",
    MARK_WRONG: "mark the selected row as not existing",
    NEUTRON_ROUTE: "neutron route to the selected row (again to clear)",
}


# Compact spellings for the screen. `keyboard`'s own chord names are what get
# REGISTERED and must not change; these are only how they read. Abbreviated only where
# the short form is UNAMBIGUOUS and the long one is bulky -- there is headroom under
# the tables, so BACKSPACE stays spelled out.
SPELLING = {"page up": "Pg Up", "page down": "Pg Down"}


def key_label(chord):
    """'page up' -> '[Pg Up]'. The ONE place a key is spelled for the screen.

    Square brackets, the way Elite's own galaxy map writes a keybind hint -- the
    brackets are what make it read as a control rather than as a word. Built from the
    binding itself, so the hint on screen and the key actually registered cannot
    disagree.

    TITLE CASE, NOT UPPER, and abbreviated where there is a common short form. This bar
    competes with the tables for the width of the overlay, and "[PAGE DOWN]" spends
    eleven characters saying what "[Pg Down]" says in nine. Upper case reads as SHOUTING
    at this size besides -- the brackets already do the work of marking it as a control.
    """
    parts = [SPELLING.get(part, part.title()) for part in chord.split("+")]
    return f"[{'+'.join(parts)}]"


def key_pair(*labels):
    """Two keys that mean one thing, as one segment: '[Pg Up] / [Pg Down]'.

    A SLASH, not a space. PAGE UP and PAGE DOWN are opposite ends of a single control
    and the slash says so; two bracketed labels merely adjacent read as two separate
    bindings that happen to share a description.
    """
    return " / ".join(labels)


def help_segments(bindings=None):
    """The help bar, as ROWS of CELLS of (text, palette role) segments.

    Three levels, and each one earns itself:

      * SEGMENTS, because the KEYS and the PROSE are coloured differently and a Tk Label
        is one colour end to end. So a cell is several labels packed side by side and
        this decides where the joins go.
      * CELLS, because they are gridded into COLUMNS and a column only lines up if the
        thing in it is one widget. A flat run of labels cannot be aligned.
      * ROWS, because *** THE TABLES MUST DICTATE THE WIDTH OF THE OVERLAY. *** In one
        line these six keys run wider than the grid they describe, which would let the
        least important thing on screen set how much of the cockpit the HUD covers.
        Two pairs of columns roughly halves it.

    DESCRIPTIONS ARE CAPITALISED. They are labels, not sentence fragments, and at this
    size a lower-case run after a bracketed keycap reads as continuing the key rather
    than naming it.

    FOUR COLUMNS, NOT TWO: key, description, key, description. The keys are ragged --
    "[Up] / [Down]" against "[Shift+Backspace]" -- so a key and its description in one
    cell would start every description at a different x. Giving the descriptions their
    own grid column is what lines them up, and alignment is the whole reason to grid
    rather than pack.

    Two PAIRS and not three: the width won back by a third is small, and every extra
    column is another line of vertical space over a HUD already competing with the
    game's own.
    """
    b = dict(bindings or DEFAULT_BINDINGS)
    k = {action: key_label(chord) for chord, action in b.items()}
    return [
        [[(key_pair(k[PREV_TABLE], k[NEXT_TABLE]), "keycap")], [("Table", "dim")],
         [(k[MARK_WRONG], "keycap")], [("No such system", "dim")]],
        [[(key_pair(k[PREV_ROW], k[NEXT_ROW]), "keycap")], [("Row", "dim")],
         [(k[NEUTRON_ROUTE], "keycap")], [("Neutron route", "dim")]],
        # NOT A KEYBIND -- it is what the four keys ABOVE IT do, so it belongs on its
        # own line under them rather than tucked into a description column where it
        # would read as the label for a fifth key that is not there. Empty cells after
        # it, which set_help() turns into a span across the full width, so this line is
        # laid out independently of the four columns above and cannot stretch them.
        [[("The highlighted row is copied", "dim")], [], [], []],
    ]


class Hotkeys:
    """Registers the navigation keys globally and hands presses to the Tk loop."""

    def __init__(self, bindings=None):
        self.bindings = dict(bindings or DEFAULT_BINDINGS)
        self._pending = None
        # *** MARK_WRONG GETS ITS OWN SLOT, AND THAT IS NOT TIDINESS. *** The shared
        # slot is last-press-wins, which is right for a cursor and wrong for a write:
        # an arrow arriving in the same 120 ms tick would silently swallow the one
        # press that records a finding. Two slots means neither can eat the other.
        self._wrong = False
        # And SHIFT+N gets a third, for the same reason and one more: it TOGGLES. Losing
        # a toggle to a same-tick arrow does not just drop an action, it leaves the key
        # meaning the opposite of what it should on the next press.
        self._route = False
        self.registered = []
        self.failed = []

    @property
    def available(self):
        return keyboard is not None

    def register(self):
        """Hook every key. -> (registered, failed). Never raises."""
        if not self.available:
            self.failed = ["keyboard library not installed (pip install keyboard)"]
            return self.registered, self.failed
        for chord, action in self.bindings.items():
            try:
                # suppress=False: the game may want the key too. This app only ever
                # copies a name, so there is no reason to swallow the keystroke.
                keyboard.add_hotkey(chord, self._fire, args=(action,), suppress=False)
                self.registered.append(chord)
            except Exception as e:
                self.failed.append(f"{chord}: {e}")
        return self.registered, self.failed

    def _fire(self, action):
        """Hook-thread callback. Records ONLY -- see the module docstring."""
        if action == MARK_WRONG:
            self._wrong = True
        elif action == NEUTRON_ROUTE:
            self._route = True
        else:
            self._pending = action

    def take(self):
        """-> the pending action, clearing it. None if nothing is waiting.

        LAST PRESS WINS if two arrive between ticks, which is the right call for a
        cursor: holding DOWN should land you where you stopped, not replay every
        intermediate row and copy each one. The tick runs every 120 ms, so a normal
        keypress is never lost and a key-repeat burst collapses to its endpoint.
        """
        p, self._pending = self._pending, None
        return p

    def take_wrong(self):
        """-> True if SHIFT+BACKSPACE is waiting, clearing it.

        Separate from take() so a navigation key pressed in the same tick cannot
        discard it. Collapses repeats the same way: holding the chord down marks the
        row once, not once per repeat, and the row is gone from the list by the next
        repaint anyway.
        """
        w, self._wrong = self._wrong, False
        return w

    def take_route(self):
        """-> True if SHIFT+N is waiting, clearing it.

        Collapses a key-repeat burst to ONE toggle. Holding the chord through four
        ticks would otherwise plot, clear, plot and clear again, leaving the state
        decided by exactly when you let go.
        """
        r, self._route = self._route, False
        return r

    def describe(self):
        """One line per binding, for the startup log."""
        return [f"{chord} -> {DESCRIPTION[action]}"
                for chord, action in self.bindings.items()]

    def unregister(self):
        if self.available and self.registered:
            try:
                keyboard.unhook_all()
            except Exception:
                pass
            self.registered = []
