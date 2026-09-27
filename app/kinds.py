"""The vocabulary of predictable objects. ONE ROW PER KIND, carrying every name the app
calls it by. Everything about WHAT a kind is lives here; the other modules ask.

    kinds.py      what a kind IS -- names, arrival classes, what it is for
    database.py   which rows appear; every SQL fragment below is generated from KINDS
    theme.py      how wide, what colour, and in WHAT ORDER the columns sit
    table.py      places text, computes nothing

*** THE FOUR NAMES ARE FOUR NAMES ON PURPOSE. ***

  `key`     is DATA, stored in system_confirmed.kind in the one database that cannot be
            rebuilt, so it is FROZEN. Every row of system_confirmed carries one. Renaming one
            splits a kind in two and every count is wrong after. Change `abbr` instead.
  `column`  the system_predicted column AND the row-dict key -- one name, no
            translation layer.
  `abbr`    the ONE on-screen abbreviation, used for the heading AND the TYPE cell, so a
            confirmed black hole reads `BLK HOLE` under a heading reading `BLK HOLE`.
            Eight characters, the width of a probability column.
  `name`    prose, for footers, where an abbreviation reads as noise.

ORDER IS RARITY, BEST FIRST, and the Confirmed table is drawn in it: that table shows
one line per kind, so this order IS its row order and a black hole sits above a white
dwarf whatever the distances are. NOT the column order -- theme.py owns that, and the two
genuinely differ. theme.py asserts they cover the same kinds.
"""
from typing import NamedTuple


class Kind(NamedTuple):
    """One predictable object, and every name and flag that belongs to it."""
    key: str            # STORED in system_confirmed.kind. Frozen -- see the header.
    column: str         # system_predicted column, and the row-dict key
    abbr: str           # the one on-screen abbreviation: heading AND type cell
    name: str           # prose, for footers and notes
    classes: tuple      # the arrival star classes that CONFIRM this kind
    ranks: bool         # enters the ranking expression
    rare: bool          # enters the "worth showing at all" test
    chime: bool         # worth a sound on sight
    chime_predicted: bool   # worth a sound only where WE predicted the system


# *** EVERY KIND HERE CAN BE CONFIRMED, without exception. *** A route plot only ever
# reveals the ARRIVAL STAR, so a prediction with no arrival class is a number that stays
# a guess forever. Anything added here needs one, or it does not belong.
#
# AND THE CLASS MUST BE ONE THE JOURNAL'S `StarClass` FIELD ACTUALLY WRITES, which is a
# SHORT-CODE vocabulary: across 201 journals it is M K N F G TTS A L T Y H B AeBe WO DC
# O DA WNC D WN WC SupermassiveBlackHole DQ DAZ DAB CN, and nothing else. The long
# `B_BlueWhiteSuperGiant` spellings belong to the `Scan` event's StarType, which needs
# the ship to be IN the system -- see DEAD_ENDS.md on the supergiant.
#
# BOTH SPELLINGS of the supermassive black hole are listed on purpose. The journal
# writes "SupermassiveBlackHole" and the model's body table writes
# "SuperMassiveBlackHole" -- one capital apart, and matching only one of them would
# silently drop Sagittarius A*.
KINDS = (
    Kind("BH", "p_bh", "BLK HOLE", "black hole",
         ("H", "SupermassiveBlackHole", "SuperMassiveBlackHole"),
         ranks=True, rare=True, chime=True, chime_predicted=False),
    Kind("WR", "p_wr", "WOLF-RAY", "Wolf-Rayet",
         ("W", "WN", "WNC", "WC", "WO"),
         ranks=True, rare=True, chime=True, chime_predicted=False),
    Kind("HERBIG", "p_herbig", "HERBIG", "Herbig Ae/Be",
         ("AeBe",),
         ranks=False, rare=True, chime=True, chime_predicted=False),
    Kind("O-TYPE", "p_otype", "O-TYPE", "O-type star",
         ("O",),
         ranks=False, rare=True, chime=True, chime_predicted=False),
    Kind("NEUTRON", "p_neutron", "NEUTRON", "neutron star",
         ("N",),
         ranks=False, rare=False, chime=False, chime_predicted=True),
    Kind("WHT DWRF", "p_wd", "WHT DWRF", "white dwarf",
         ("D", "DA", "DAB", "DAO", "DAV", "DAZ", "DB", "DBV", "DBZ",
          "DC", "DCV", "DO", "DOV", "DQ", "DX"),
         ranks=False, rare=False, chime=False, chime_predicted=False),
)


# --------------------------------------------------------------- the three flags
# Each answers a DIFFERENT question, and they are deliberately not derived from one
# another even where they name the same kinds today.
#
# `ranks`   -- "does this decide which system is best?" BH and WR only. Neutrons and
#              white dwarfs sit near their base rate in almost every system, so
#              ranking on them would rank by how ORDINARY a system is and swamp the
#              signal. The other five are still shown; they just do not sort the list.
#
# `rare`    -- "is this prediction worth showing a system for?" Neutron and white
#              dwarf are out: p_neutron alone is 0.17 in ordinary f-mass space, so
#              including them would pass essentially every system and the threshold
#              would filter nothing.
#
# `chime` /  -- "should the commander look UP from what they are doing?" Strictly
# `chime_       narrower than the rest, because a sound interrupts and has to earn it.
#  predicted`   A neutron on a route is one you steered TOWARD, so NEUTRON sounds only
#              under `chime_predicted` -- where the system is a boxel prediction of
#              OURS, which is the model being right about a place nobody had looked.
#              White dwarfs are not a target at all and sound never. O-TYPE is the
#              first flag to flip if the chime still feels frequent.

BY_KEY = {k.key: k for k in KINDS}
BY_COLUMN = {k.column: k for k in KINDS}

# The prediction columns, in rarity order. The SELECT order; NOT the screen order.
COLUMNS = tuple(k.column for k in KINDS)

RANKING = tuple(k.column for k in KINDS if k.ranks)
RARE = tuple(k.column for k in KINDS if k.rare)

# Flat sets of ARRIVAL CLASSES, which is what the journal actually hands us.
ALL_CLASSES = {c for k in KINDS for c in k.classes}
CHIME_CLASSES = {c for k in KINDS if k.chime for c in k.classes}
CHIME_IF_PREDICTED = {c for k in KINDS if k.chime_predicted for c in k.classes}

# An arrival class names at most ONE kind, asserted because two kinds claiming the same
# class would make "what did I just jump into" ambiguous.
KEY_OF_CLASS = {c: k.key for k in KINDS for c in k.classes}
assert len(KEY_OF_CLASS) == sum(len(k.classes) for k in KINDS)


def heading(column):
    """-> the on-screen abbreviation for a prediction column.

    theme.py calls this rather than spelling the heading out beside the width, so the
    heading and the TYPE cell of a confirmed row cannot say different words.
    """
    return BY_COLUMN[column].abbr
