"""Global navigation keys. The only module that knows about the `keyboard` library.

FIVE KEYS, NOT THIRTY-THREE:

    PAGE DOWN / PAGE UP   move to the next / previous table
    DOWN / UP             move to the next / previous row of that table
    SHIFT + BACKSPACE     the selected system DOES NOT EXIST -- the galaxy map
                          refused to plot to it. The only key that writes anything.

That replaced a bank of F-keys -- F1..F10 for the sector table, CTRL+F1..F10 for
Confirmed, ALT+F1..F10 for Adjacent sectors, SHIFT+F1..F3 for carriers. Three things
were wrong with it and all three go away here:

  1. *** ALT+F4 IS "CLOSE THE FOREGROUND WINDOW" ON WINDOWS. *** Registered with
     suppress=False the chord passed straight through after we handled it, so pressing
     the fourth adjacent sector would have copied a system name AND closed Elite.
  2. A row's key changed under you. Consume a sector's last candidate and it drops out
     of the Adjacent list, so everything below shifts up and ALT+F2 means somewhere
     else than it did a minute ago. A cursor you move is immune: it is wherever you
     last put it.
  3. Thirty-three chords is thirty-three chances to collide with a game binding, and
     it cost a 10-character KEY column to advertise them all.

GLOBAL, not Tk bindings: the overlay never has focus. Elite Dangerous does, and the
whole point is to press a key while flying. A `root.bind("<Down>", ...)` would only fire
when the HUD itself is focused, which is never.

*** AND THAT IS EXACTLY WHY THE CALLER MUST GATE ON FOCUS. *** These are ARROW KEYS. A
global hook on them fires while you are typing in an editor, scrolling a browser, or
renaming a file -- and every one of those presses would move the cursor and overwrite
your clipboard. The F-keys were rare enough to get away with it; these are not.
main.py checks focus.is_foreground() before draining a press, and that check is not
optional.

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

# key chord -> action. `keyboard`'s own spelling for the page keys is two words.
DEFAULT_BINDINGS = {
    "page down":      NEXT_TABLE,
    "page up":        PREV_TABLE,
    "down":           NEXT_ROW,
    "up":             PREV_ROW,
    "shift+backspace": MARK_WRONG,
}

# How each action reads in the startup log and in a "no target" message.
DESCRIPTION = {
    PREV_TABLE: "previous table", NEXT_TABLE: "next table",
    PREV_ROW: "previous row", NEXT_ROW: "next row",
    MARK_WRONG: "mark the selected row as not existing",
}


def key_label(chord):
    """'page up' -> '[PAGE UP]'. The ONE place a key is spelled for the screen.

    Square brackets, the way Elite's own galaxy map writes a keybind hint -- the
    brackets are what make it read as a control rather than as a word. Built from the
    binding itself, so the hint on screen and the key actually registered cannot
    disagree; that was worth keeping from the F-key version even though there are only
    five keys left to get wrong.
    """
    return f"[{chord.upper()}]"


def help_segments(bindings=None):
    """The help bar, as (text, palette role) pairs.

    Segments rather than one string because the KEYS and the PROSE are coloured
    differently -- a Tk Label is one colour end to end, so the bar is several labels
    packed side by side and this decides where the joins go.
    """
    b = dict(bindings or DEFAULT_BINDINGS)
    k = {action: key_label(chord) for chord, action in b.items()}
    return [(k[PREV_TABLE], "keycap"), (" ", "dim"), (k[NEXT_TABLE], "keycap"),
            ("  table   ", "dim"),
            (k[PREV_ROW], "keycap"), (" ", "dim"), (k[NEXT_ROW], "keycap"),
            ("  row   ", "dim"),
            (k[MARK_WRONG], "keycap"), ("  no such system   ", "dim"),
            ("the highlighted row is copied", "dim")]


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
