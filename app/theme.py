"""Every colour, font and column definition the overlay uses. One place, no literals.

A widget asks for a ROLE -- `Palette.head`, `Fonts.row` -- and never names a colour: the
modules that draw things do not know what green is.

`Palette.key` is the transparency key, not a colour anyone should see. Windows treats a
window's `-transparentcolor` as fully see-through, so painting every background with KEY
is what makes the overlay a floating HUD rather than a black rectangle. It is #010101 and
not #000000 because pure black is common enough in real content that a stray widget using
it would punch an invisible hole.
"""

from .kinds import COLUMNS as KIND_COLUMNS, heading


class Palette:
    key = "#010101"      # transparency key -- a background, never a foreground
    fg = "#39ff14"       # primary text: the phosphor green the game's own UI suggests
    head = "#8fd0ff"     # column titles and table titles
    dim = "#aaaaaa"      # secondary text: the predictions you read second
    ok = "#ffd700"       # the columns that decide whether to go: BH and WR
    warn = "#ff9955"     # something is off but the app still works
    hot = "#ff4d4d"      # a mass code h target: rarest pool, highest payoff
    # Keybind hints. Deliberately not one of the data colours, so "[F4]" reads as a
    # control you press and never as a value you interpret.
    keycap = "#d6d6d6"
    # THE SELECTION BAND. A real background, not a foreground: the cursor has to be
    # findable at a glance while flying, and re-colouring the text would compete with
    # the row-kind colours that are already saying something.
    #
    # *** MUST NOT BE Palette.key. *** That is the window's -transparentcolor, so
    # painting the band with it would punch a hole rather than draw a stripe.
    sel_bg = "#14324e"
    sel_fg = "#ffffff"     # not used for data -- reserved for chrome ON the band

    # ROW KINDS. These override the per-column role for the WHOLE row: what a row IS
    # matters more than which column you happen to be reading.
    # A CONFIRMED find -- a step past the phosphor green a predicted system name uses,
    # so "certain" and "likely" never read alike.
    confirmed = "#00ff5f"
    poi = "#c78fff"        # a certainty of a different kind: go and look at it
    carrier = "#ffb347"    # a parked fleet carrier: somewhere to dock, not a gamble
    # A neutron star: a JET CONE BOOST. Shares a table with the carriers because both
    # are places to GO rather than things to find. Close enough to `head` to group with
    # the carrier amber as "infrastructure", far enough from `confirmed` that a boost
    # never reads as a find.
    neutron = "#9fd8ff"
    # A REAL CATALOGUED STAR THE GAME MAY NOT HAVE. Unlike everything else here: every
    # other row is a Stellar Forge system asking "what is IN it", and this one asks "is
    # it THERE AT ALL".
    unfound = "#ff7ba8"
    catalog = "#5f7f8f"    # BACKFILL: already in the dumps, not a boxel prediction.
    #                        The dimmest thing on screen -- what a sector offers when
    #                        it had nothing better.


class Fonts:
    """Built from one base size so `--font` scales the whole overlay coherently."""

    def __init__(self, base=11, family="Consolas"):
        self.family = family
        self.base = base
        self.row = (family, base)
        self.head = (family, base, "bold")
        self.small = (family, max(7, base - 2))
        self.title = (family, max(8, base - 1), "bold")


# Column layout. ONE definition, driving the header renderer AND the row renderer, for
# EVERY table on screen, so a width change cannot leave the two disagreeing.
#
# (attribute, heading, width, anchor, role, kind)
#   attribute -- key into the row dict from database.top_targets()/confirmed_targets()
#   role      -- a Palette attribute name, resolved at render time
#   kind      -- "text" is placed verbatim; "prob" goes through format_probability()
#
# The seven predictions are shown SEPARATELY and never combined: p_bh and p_wr compete
# for the same primary star -- one star cannot be both, so they are never added or
# multiplied, and there is no single headline number.
#
# *** THE HEADINGS ARE NOT WRITTEN HERE. *** `prob()` fetches the one abbreviation
# kinds.py holds for that object, which is the same string the TYPE cell of a confirmed
# row shows. What this file owns is the layout decision: which columns exist, how wide,
# and in what ORDER -- and the order here is not kinds.py's order, which is rarity.
def prob(column, role="dim"):
    """One probability column: eight characters, right-aligned, heading
    straight from kinds.py."""
    return (column, heading(column), 8, "e", role, "prob")


COLUMNS = [
    # NO CURSOR COLUMN and no KEY column: the SELECTION BAND is the entire indicator --
    # a whole row painted sel_bg -- and one help bar at the foot of the window names
    # the four keys once.
    ("system",     "SYSTEM", 24, "w", "fg",     "text"),
    # EIGHT, matching the probability columns: it holds the same abbreviations they use
    # as headings, and anything narrower truncates the widest of them.
    ("type_label", "TYPE",   8,  "w", "dim",    "text"),
    # Distance in ly. Only the Confirmed table fills it -- that list is GALAXY-WIDE and
    # ordered by it, and an ordering you cannot see is not one you can trust.
    ("dist_ly",    "DIST",   8,  "e", "dim",    "dist"),
    # *** SEVEN COLUMNS, ALL OF THEM STARS. *** A route plot reveals arrival stars and
    # only arrival stars, so nothing the overlay learns can ever confirm a planet.
    #
    # ORDER IS NOT RARITY: BLK HOLE and WOLF-RAY lead because they decide the ranking.
    # The assert underneath keeps the two lists honest -- they may disagree about
    # order, never about which kinds exist.
    prob("p_bh", "ok"),          # black hole
    prob("p_wr", "ok"),          # Wolf-Rayet
    prob("p_herbig"),            # Herbig Ae/Be
    prob("p_supergiant"),        # supergiant, any class
    prob("p_otype"),             # O-type main-sequence star
    prob("p_neutron"),           # neutron star
    prob("p_wd"),                # white dwarf, any variant
]

# *** THE ONE CHECK THAT A KIND CANNOT BE HALF-ADDED. *** kinds.py can gain or lose an
# object and every SQL fragment in database.py follows automatically; this file cannot,
# because a column also needs a width and a place to sit. Without this, the symptom of
# forgetting is a prediction that is computed, ranked, chimed for and never shown.
_SHOWN = {c for c, _h, _w, _a, _r, k in COLUMNS if k == "prob"}
assert _SHOWN == set(KIND_COLUMNS), (
    "theme.COLUMNS and kinds.KINDS disagree about which predictions exist: "
    f"{_SHOWN ^ set(KIND_COLUMNS)}")

# Gap between columns, in pixels. Applied as the label's OWN padding (half on each
# side) and never as grid padx: grid padding sits OUTSIDE the widget, so it shows the
# container's background, and a selected row painted cell-by-cell would come out
# striped with transparent gaps instead of one continuous band.
PAD_X = 6

# Gap after a help-bar column, in pixels: (after a KEY column, after a TEXT column).
# A key and the words describing it are one phrase and want the tighter gap; the gap
# after the description separates one keybind from the next and must be the wider of
# the two, or the eye groups a description with the key to its RIGHT.
HELP_PAD = (10, 26)
# Vertical gap between the last table and the help bar, in pixels -- roughly half a
# line, enough that the bar does not read as one more row of the table above it.
HELP_GAP = 7

EDGE_MARGIN = 8    # gap from the screen's left edge, so the HUD is not flush against it

# Below this a probability renders as a dash rather than "0.004". Two decimals cannot
# tell 0.004 from 0.001, so a dash says "too small to distinguish" in one glyph.
#
# *** MUST EQUAL database.MIN_RARE. *** That is what makes a row appear exactly when at
# least one of its cells is a number, instead of a row of dashes with nothing to
# justify it.
MIN_SHOWN_PROBABILITY = 0.01

# ---------------------------------------------------------------- value gradient
# Ten steps, red -> orange -> amber -> yellow-green -> green, for the probability
# cells. Tuned for a dark HUD: ColorBrewer's RdYlGn bottoms out at #a50026, which is
# nearly invisible on black. The top step is the palette's own phosphor green, so the
# best cell on screen matches the colour the rest of the UI already uses for "good".
GRADIENT = [
    "#ff4d4d",  # 0
    "#ff6a3d",
    "#ff8730",
    "#ffa424",
    "#ffc01a",
    "#ffd633",
    "#e8e04a",
    "#c2e04f",
    "#8ed957",
    "#39ff14",  # 9
]

# The scale the gradient spans. LINEAR, and deliberately not a quantile stretch: a
# colour has to mean a probability, not a rank among whatever happens to be on screen,
# or the same 0.40 would look different in two sectors.
#
# Measured, not guessed. Across all displayed probability columns of system_predicted,
# values >= 0.05 have median 0.148, p99 0.538 and max 0.626. Most cells therefore land
# red or orange, because most predictions really are unlikely, and green stays rare
# enough to mean something.
#
# *** DELIBERATELY NOT MIN_SHOWN_PROBABILITY. *** They answer different questions: that
# one is "is this worth a line at all", this one is "what does a colour mean". Values
# between the two clamp to the bottom step, which is the claim being made about them.
GRADIENT_MIN = 0.05
GRADIENT_MAX = 0.60

# ------------------------------------------------------------- the confirm flash
# A new confirmation fades its system name from white down to the confirmed green it
# keeps. White because it is the only colour on this HUD not already spoken for by a row
# kind or a probability. 12 steps at 60 ms is 0.72 s -- long enough to catch
# peripherally while jumping, short enough to be over before the next repaint.
FLASH_RAMP = [
    "#ffffff", "#eaffea", "#d5ffd5", "#b8ffb8", "#96ff8a", "#75ff5c",
    "#5cff3f", "#4bff2b", "#42ff20", "#3dff1a", "#3aff16", "#39ff14",
]
FLASH_STEP_MS = 60

# The COUNT scale, for the expected-object totals on a sector row. Same ten colours --
# more is better -- but LOGARITHMIC: sector totals span three orders of magnitude, so a
# linear ramp would put almost every sector in the bottom step. Fixed rather than
# stretched to what is on screen, for the same reason the probability ramp is.
COUNT_GRADIENT_MIN = 0.1    # below this the cell is dim: nothing worth diverting for
COUNT_GRADIENT_MAX = 100.0  # a sector offering 100+ expected objects is as good as it gets

