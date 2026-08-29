"""Every colour, font and column definition the overlay uses. One place, no literals.

The old app scattered `"#39ff14"` and `("Consolas", a.font)` through a 1,700-line file,
so a palette change meant a careful grep. Here a widget asks for a ROLE -- `Palette.head`,
`Fonts.row` -- and never names a colour. That is the whole point: the modules that draw
things should not know what green is.

KEY is the transparency key, not a colour anyone should see. Windows treats a window's
`-transparentcolor` as fully see-through, so painting every background with KEY is what
makes the overlay a floating HUD rather than a black rectangle. It is #010101 and not
#000000 deliberately -- pure black is common enough in real content that a stray widget
using it would punch an invisible hole.
"""


class Palette:
    key = "#010101"      # transparency key -- a background, never a foreground
    fg = "#39ff14"       # primary text: the phosphor green the game's own UI suggests
    head = "#8fd0ff"     # column titles and table titles
    dim = "#aaaaaa"      # secondary text: the predictions you read second
    ok = "#ffd700"       # the columns that decide whether to go: BH and WR
    warn = "#ff9955"     # something is off but the app still works
    hot = "#ff4d4d"      # a mass code h target: rarest pool, highest payoff
    # Keybind hints, matching the neutral light grey Elite's galaxy map uses for
    # them -- deliberately NOT one of the data colours, so "[F4]" reads as a
    # control you press and never as a value you interpret.
    keycap = "#d6d6d6"
    # THE SELECTION BAND. A real background, not a foreground -- the cursor has to be
    # findable at a glance while flying, and re-colouring the text would compete with
    # the row-kind colours that are already saying something.
    #
    # *** MUST NOT BE Palette.key. *** #010101 is the window's -transparentcolor, so
    # painting the band with it would punch a hole rather than draw a stripe. A dark
    # desaturated blue reads as "selected" against every foreground in the palette
    # without being bright enough to drown the phosphor green sitting on top of it.
    sel_bg = "#14324e"
    sel_fg = "#ffffff"     # not used for data -- reserved for chrome ON the band

    # ROW KINDS. These override the per-column role for the WHOLE row, because what a
    # row IS matters more than which column you happen to be reading.
    # A CONFIRMED find: the game has already said it is there. Bright, saturated
    # green -- a step past the ordinary phosphor green a predicted system name
    # uses, so "certain" and "likely" never read alike.
    confirmed = "#00ff5f"
    poi = "#c78fff"        # a certainty of a different kind: go and look at it
    carrier = "#ffb347"    # a parked fleet carrier: somewhere to dock, not a gamble
    # A neutron star: a JET CONE BOOST. Shares a table with the carriers because both
    # are places to GO rather than things to find, and takes the pale blue-white of the
    # star itself -- close enough to `head` to group with the carrier amber as
    # "infrastructure", far enough from `confirmed` green that a boost never reads as
    # a find.
    neutron = "#9fd8ff"
    # A REAL CATALOGUED STAR THE GAME MAY NOT HAVE. Rose, and deliberately unlike
    # everything else here: every other row is a Stellar Forge system asking "what is
    # IN it", and this one asks "is it THERE AT ALL". A colour shared with any of them
    # would invite reading it as one of them.
    unfound = "#ff7ba8"
    catalog = "#5f7f8f"    # BACKFILL: already in the dumps, not a boxel prediction.
    #                        Deliberately the dimmest thing on screen -- it is what a
    #                        sector offers when it had nothing better.


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
# EVERY table on screen. Building a header and its cells separately means
# is why they drifted apart whenever a width changed.
#
# (attribute, heading, width, anchor, role, kind)
#   attribute -- key into the row dict from store.top_targets()/confirmed_targets()
#   role      -- a Palette attribute name, resolved at render time
#   kind      -- "text" is placed verbatim; "prob" goes through format_probability()
#
# The eight predictions are shown SEPARATELY and never combined: the model's own
# documentation says p_bh and p_wr "compete for the same primary star -- one star cannot
# be both, so never add or multiply them", which rules out any single headline number.
COLUMNS = [
    # NO CURSOR COLUMN, and no KEY column either. The 10-character KEY column spelled
    # out "[CTRL+F10]" against every row to advertise 33 chords; there are four keys
    # now and one help bar at the foot of the window says all of it once. The SELECTION
    # BAND is the entire indicator -- a whole row painted sel_bg, which is more legible
    # at a glance than a two-character glyph and costs no width at all.
    ("system",     "SYSTEM", 24, "w", "fg",     "text"),
    ("type_label", "TYPE",   7,  "w", "dim",    "text"),
    # Distance in ly. Only the Confirmed table fills it -- that list is GALAXY-WIDE and
    # ordered by it, and an ordering you cannot see is not one you can trust.
    ("dist_ly",    "DIST",   8,  "e", "dim",    "dist"),
    # Eight characters each. The four-character abbreviations these replaced (HERB,
    # SUPG, OSTR, HeGG) were guessable only once you already knew what they meant,
    # which is the wrong way round for a heading.
    ("p_bh",       "BLK HOLE", 8, "e", "ok",  "prob"),   # black hole
    ("p_wr",       "WOLF-RAY", 8, "e", "ok",  "prob"),   # Wolf-Rayet
    ("p_herbig",   "HERBIG",   8, "e", "dim", "prob"),   # Herbig Ae/Be
    ("p_supg",     "SUPERGNT", 8, "e", "dim", "prob"),   # supergiant, any class
    ("p_otype",    "O-TYPE",   8, "e", "dim", "prob"),   # O-type main-sequence star
    ("p_neutron",  "NEUTRON",  8, "e", "dim", "prob"),   # neutron star
    ("p_wd",       "WHT DWRF", 8, "e", "dim", "prob"),   # white dwarf, any variant
    ("p_hegg",     "He GIANT", 8, "e", "dim", "prob"),   # helium-rich gas giant
]

# Gap between columns, in pixels. Applied as the label's OWN padding (half on each
# side) and never as grid padx: grid padding sits OUTSIDE the widget, so it shows the
# container's background, and a selected row painted cell-by-cell would come out
# striped with transparent gaps instead of one continuous band.
PAD_X = 6
EDGE_MARGIN = 8    # gap from the screen's left edge, so the HUD is not flush against it

# Below this a probability renders as a dash rather than "0.004". Two decimals cannot
# tell 0.004 from 0.001, so printing either would be showing precision the cell does not
# have, and a dash says "too small to distinguish" in one glyph.
#
# LOWERED FROM 0.05 WITH store.MIN_RARE, and the two must stay equal -- that is what
# makes a row appear exactly when at least one of its cells is a number, instead of a
# row of dashes with nothing to justify it. 0.05 was a "worth flying to" bar being used
# as a "worth showing" bar; at 0.01 a long shot prints as the long shot it is and the
# reader decides.
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
# Measured rather than guessed. Across all eight displayed columns of
# system_predicted, values >= 0.05 have median 0.148, p99 0.538 and max 0.626, so the
# ceiling is 0.60 and the floor is the threshold below which a cell shows a dash
# anyway. The consequence is intended: most cells land red or orange, because most
# predictions really are unlikely, and green stays rare enough to mean something.
# *** DELIBERATELY NOT MIN_SHOWN_PROBABILITY, THOUGH IT USED TO BE. *** They answer
# different questions: MIN_SHOWN_PROBABILITY is "is this worth a line at all" and moved
# to 0.01 when mass code e entered the pool, while this is "what does a colour mean".
# Tying them would have re-coloured every cell on screen -- the same 0.40 that reads
# yellow-green today would shift a step -- to accommodate a change about which ROWS
# appear. The floor stays where it was measured, and the clamp does the rest: everything
# from 0.01 to 0.05 paints the bottom red, which is exactly the claim being made about
# it.
GRADIENT_MIN = 0.05
GRADIENT_MAX = 0.60

# The COUNT scale, for the expected-object totals on a sector row. Same ten colours,
# because they mean the same thing to the eye -- more is better -- but a different
# mapping, because a count is not a probability and running one through the probability
# scale would paint every sector holding 0.6 expected objects full green.
#
# LOGARITHMIC, and that is the whole point: sector totals span three orders of magnitude
# (a quiet sector offers 0.2 expected black holes, a rich one over 100), so a linear ramp
# would put almost every sector in the bottom step and waste the other nine. Log keeps a
# 10x difference a fixed distance apart in colour.
#
# FIXED, not stretched to whatever is on screen. Same rule as the probability ramp: a
# colour has to mean a quantity, not a rank among today's ten neighbours, or the best of
# a poor row of sectors would look like the best of a rich one.
# ------------------------------------------------------------- the confirm flash
# A new confirmation flashes its system name from white down to the confirmed green it
# will keep. White first because it is the only colour on this HUD that means nothing
# else -- every other shade is already spoken for by a row kind or a probability -- so
# the eye is drawn by something it has never had to interpret before.
#
# IT FADES INTO the resting colour rather than blinking on and off. A blink says "look
# here NOW" and keeps saying it; a fade says "this just happened" and then gets out of
# the way, which is the correct claim: the row is still there afterwards, and by then
# the green is doing the work.
#
# 12 steps at 60 ms is 0.72 s -- long enough to catch peripherally while jumping, short
# enough that it is over before the next repaint would fight it.
FLASH_RAMP = [
    "#ffffff", "#eaffea", "#d5ffd5", "#b8ffb8", "#96ff8a", "#75ff5c",
    "#5cff3f", "#4bff2b", "#42ff20", "#3dff1a", "#3aff16", "#39ff14",
]
FLASH_STEP_MS = 60

COUNT_GRADIENT_MIN = 0.1    # below this the cell is dim: nothing worth diverting for
COUNT_GRADIENT_MAX = 100.0  # a sector offering 100+ expected objects is as good as it gets

