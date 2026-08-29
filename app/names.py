"""Everything the app knows about how Elite spells a system name. No IO, no database.

A procedural system name is `<Sector> <AA-A> <mass_code><n>[-<n>]`:

    Aemorrs AC-I b2-26      sector 'Aemorrs',    mass code 'b'
    Blaa Hypai BA-A g5      sector 'Blaa Hypai', mass code 'g'

The sector is therefore everything before the first `AA-A` token, and the mass code is
the first character of the token after it. Both are pure string facts, which matters:
the overlay needs the sector on every jump, and a database round-trip against a 197M-row
name bridge is not something to do inside a UI callback.

VALIDATED, not assumed: parsed against 20,000 rows of `system_predicted` and compared
with the model's own `sector` column -- 0 mismatches. If that ever stops holding, the
model's column is right and this is wrong.

Hand-named systems (Sol, Achenar, 61 Ursae Majoris) have no procedural sector and
return None. That is not a failure to handle -- 630 of 3,108 visited systems are named,
because named space is the inhabited bubble, and the bubble is fully explored and holds
no predictions anyway.
"""
import re

# The boxel token: two letters, a hyphen, one letter. Anchored, so it cannot match a
# fragment of a longer word.
_BOXEL_TOKEN = re.compile(r"^[A-Z][A-Z]-[A-Z]$")

# The mass code and index that follow it: 'b2-26', 'g5', 'e1-7394'.
_MC_TOKEN = re.compile(r"^([a-h])(\d+)(?:-(\d+))?$")


def _split(system_name):
    """-> (parts, index of the boxel token) or (parts, None) for a hand-named system."""
    parts = (system_name or "").split()
    for i, part in enumerate(parts):
        # i > 0 because a sector name cannot be empty -- a leading AA-A token would
        # mean a name we do not understand, and guessing at it would be worse.
        if i and _BOXEL_TOKEN.match(part):
            return parts, i
    return parts, None


# The model's SENTINEL sector for hand-named systems. sector_id 0 in the sector table
# is literally named this, and every hand-named system -- Sol, Colonia, Beagle Point --
# points at it. Named here so the app and the database use one string rather than two
# that happen to match.
#
# It is NOT a place. It is every hand-named system in the galaxy collected under one
# key, so a distance ordering over it spans 65,000 ly and a "sector total" over it is a
# galaxy-wide total. Anything reading it has to know that; see App.crafted.
CRAFTED_SECTOR = "crafted"


def sector_of(system_name):
    """'Blaa Hypai' for 'Blaa Hypai BA-A g5'. None for a hand-named system."""
    parts, i = _split(system_name)
    return " ".join(parts[:i]) if i else None


def mass_code_of(system_name):
    """'g' for 'Blaa Hypai BA-A g5'. None if the name is not procedural.

    Mass code is the size class of the generator cube the system sits in -- 'a' the
    smallest, 'h' the largest -- and it is the strongest single predictor the model has,
    which is why it is worth reading straight off the name.
    """
    parts, i = _split(system_name)
    if not i or i + 1 >= len(parts):
        return None
    m = _MC_TOKEN.match(parts[i + 1])
    return m.group(1) if m else None


def is_procedural(system_name):
    """True if the name carries a sector and mass code we can read."""
    return sector_of(system_name) is not None
