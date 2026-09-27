"""Jump range, from the ship you are actually flying.

THE OVERLAY'S ONLY PIECE OF PHYSICS. Everything else here reads a database or a log;
this computes a number the game never writes down.

    range = optmass/(unladen + fuel + reserve + cargo)
            * (min(maxfuel, fuel)/fuelmul) ** (1/fuelpower)
            + jumpboost

`optmass`, `unladen`, `fuel` and `reserve` come from the journal's `Loadout` event,
which is the ONLY source that knows your engineering. The other three are per-drive
constants that no journal event carries; they are the table below.

*** DO NOT USE `Loadout.MaxJumpRange`. *** It looks like the answer and is not. It is
the range at unladen mass carrying exactly ONE JUMP of fuel -- the on-fumes ceiling.
Verified on the Caspian Explorer: the formula above at (unladen + maxfuel) reproduces
the reported 82.615 to three decimals, while the real full-tank range is 75.3. Plotting
on 82.6 overstates by 10% and hands you legs you cannot fly.

WHY A FULL TANK IS THE RIGHT NUMBER TO PLOT ON. It is the heaviest fuelled state, so it
is the SHORTEST range you will have. Every leg stays flyable as the tank drains. The
opposite convention is the one that strands you.

PROVENANCE OF THE CONSTANTS: EDCD/coriolis-data, modules/standard/frame_shift_drive.json
and modules/internal/guardian_fsd_booster.json, transcribed here so the overlay never
reaches the network in flight. Checked with zero free parameters against 1,192 unboosted
jumps flown on one fingerprinted loadout: 24 breaches of the predicted ceiling, worst
+0.063 ly (0.08%).

*** UNLADEN MASS COMES FROM `Loadout.UnladenMass`, NEVER FROM SUMMING MODULE MASSES. ***
A module missing from coriolis-data contributes ZERO, so a reconstructed mass is silently
light and the resulting range silently OPTIMISTIC -- exactly the direction that strands
you between stars. The journal figure accounts for every module and every engineered
mass change, and cannot drift when Frontier ships a new part.
"""
import math

# (fuelmul, fuelpower, maxfuel) per drive symbol. optmass is NOT here: the base value is
# useless once engineered, and the Loadout event carries the real one.
FSD = {
    "int_hyperdrive_overcharge_size2_class1":                        (0.008, 2.0, 0.6),
    "int_hyperdrive_overcharge_size2_class2":                        (0.012, 2.0, 0.9),
    "int_hyperdrive_overcharge_size2_class3":                        (0.012, 2.0, 0.9),
    "int_hyperdrive_overcharge_size2_class4":                        (0.012, 2.0, 0.9),
    "int_hyperdrive_overcharge_size2_class5":                        (0.013, 2.0, 1),
    "int_hyperdrive_overcharge_size3_class1":                        (0.008, 2.15, 1.2),
    "int_hyperdrive_overcharge_size3_class2":                        (0.012, 2.15, 1.8),
    "int_hyperdrive_overcharge_size3_class3":                        (0.012, 2.15, 1.8),
    "int_hyperdrive_overcharge_size3_class4":                        (0.012, 2.15, 1.8),
    "int_hyperdrive_overcharge_size3_class5":                        (0.013, 2.15, 1.9),
    "int_hyperdrive_overcharge_size4_class1":                        (0.008, 2.3, 2),
    "int_hyperdrive_overcharge_size4_class2":                        (0.012, 2.3, 3),
    "int_hyperdrive_overcharge_size4_class3":                        (0.012, 2.3, 3),
    "int_hyperdrive_overcharge_size4_class4":                        (0.012, 2.3, 3),
    "int_hyperdrive_overcharge_size4_class5":                        (0.013, 2.3, 3.2),
    "int_hyperdrive_overcharge_size5_class1":                        (0.008, 2.45, 3.3),
    "int_hyperdrive_overcharge_size5_class2":                        (0.012, 2.45, 5),
    "int_hyperdrive_overcharge_size5_class3":                        (0.012, 2.45, 5),
    "int_hyperdrive_overcharge_size5_class4":                        (0.012, 2.45, 5),
    "int_hyperdrive_overcharge_size5_class5":                        (0.012, 2.45, 5.2),
    "int_hyperdrive_overcharge_size6_class1":                        (0.008, 2.6, 5.3),
    "int_hyperdrive_overcharge_size6_class2":                        (0.012, 2.6, 8),
    "int_hyperdrive_overcharge_size6_class3":                        (0.012, 2.6, 8),
    "int_hyperdrive_overcharge_size6_class4":                        (0.012, 2.6, 8),
    "int_hyperdrive_overcharge_size6_class5":                        (0.013, 2.6, 8.3),
    "int_hyperdrive_overcharge_size7_class1":                        (0.008, 2.75, 8.5),
    "int_hyperdrive_overcharge_size7_class2":                        (0.012, 2.75, 12.8),
    "int_hyperdrive_overcharge_size7_class3":                        (0.012, 2.75, 12.8),
    "int_hyperdrive_overcharge_size7_class4":                        (0.012, 2.75, 12.8),
    "int_hyperdrive_overcharge_size7_class5":                        (0.013, 2.75, 13.1),
    "int_hyperdrive_overcharge_size8_class1":                        (0.008, 2.9, 13.6),
    "int_hyperdrive_overcharge_size8_class2":                        (0.012, 2.9, 20.4),
    "int_hyperdrive_overcharge_size8_class3":                        (0.012, 2.9, 20.4),
    "int_hyperdrive_overcharge_size8_class4":                        (0.012, 2.9, 20.4),
    "int_hyperdrive_overcharge_size8_class5":                        (0.013, 2.9, 20.7),
    "int_hyperdrive_overcharge_size8_class5_overchargebooster_mkii": (0.011, 2.5025, 6.8),
    "int_hyperdrive_size2_class1":                                   (0.011, 2, 0.6),
    "int_hyperdrive_size2_class2":                                   (0.01, 2, 0.6),
    "int_hyperdrive_size2_class3":                                   (0.008, 2, 0.6),
    "int_hyperdrive_size2_class4":                                   (0.01, 2, 0.8),
    "int_hyperdrive_size2_class5":                                   (0.012, 2, 0.9),
    "int_hyperdrive_size3_class1":                                   (0.011, 2.15, 1.2),
    "int_hyperdrive_size3_class2":                                   (0.01, 2.15, 1.2),
    "int_hyperdrive_size3_class3":                                   (0.008, 2.15, 1.2),
    "int_hyperdrive_size3_class4":                                   (0.01, 2.15, 1.5),
    "int_hyperdrive_size3_class5":                                   (0.012, 2.15, 1.8),
    "int_hyperdrive_size4_class1":                                   (0.011, 2.3, 2),
    "int_hyperdrive_size4_class2":                                   (0.01, 2.3, 2),
    "int_hyperdrive_size4_class3":                                   (0.008, 2.3, 2),
    "int_hyperdrive_size4_class4":                                   (0.01, 2.3, 2.5),
    "int_hyperdrive_size4_class5":                                   (0.012, 2.3, 3),
    "int_hyperdrive_size5_class1":                                   (0.011, 2.45, 3.3),
    "int_hyperdrive_size5_class2":                                   (0.01, 2.45, 3.3),
    "int_hyperdrive_size5_class3":                                   (0.008, 2.45, 3.3),
    "int_hyperdrive_size5_class4":                                   (0.01, 2.45, 4.1),
    "int_hyperdrive_size5_class5":                                   (0.012, 2.45, 5),
    "int_hyperdrive_size6_class1":                                   (0.011, 2.6, 5.3),
    "int_hyperdrive_size6_class2":                                   (0.01, 2.6, 5.3),
    "int_hyperdrive_size6_class3":                                   (0.008, 2.6, 5.3),
    "int_hyperdrive_size6_class4":                                   (0.01, 2.6, 6.6),
    "int_hyperdrive_size6_class5":                                   (0.012, 2.6, 8),
    "int_hyperdrive_size7_class1":                                   (0.011, 2.75, 8.5),
    "int_hyperdrive_size7_class2":                                   (0.01, 2.75, 8.5),
    "int_hyperdrive_size7_class3":                                   (0.008, 2.75, 8.5),
    "int_hyperdrive_size7_class4":                                   (0.01, 2.75, 10.6),
    "int_hyperdrive_size7_class5":                                   (0.012, 2.75, 12.8),
    "int_missing_hyperdrive":                                        (0, 0, 0),
}

# Flat ly added to jump range, not scaled by mass.
BOOSTER = {
    "int_guardianfsdbooster_size1": 4,
    "int_guardianfsdbooster_size2": 6,
    "int_guardianfsdbooster_size3": 7.75,
    "int_guardianfsdbooster_size4": 9.25,
    "int_guardianfsdbooster_size5": 10.5,
}

# NEUTRON JET CONE, as a multiple of the unboosted range at the same fuel load.
#
# *** IT IS A PROPERTY OF THE SHIP, NOT OF THE DRIVE. *** Everything flies at 4.0 -- the
# "300% boost" everyone quotes -- except the Caspian, which gets 6.0. So this is a lookup
# on `Loadout.Ship` and not a constant: plotting a chain at one hull's multiplier while
# flying another is how you get legs that will not plot.
#
# BOTH FIGURES ARE MEASURED, from `BoostUsed: 4` jumps in this commander's own journals,
# against the laden range this module computes for the loadout flown at the time:
#
#     explorer_nx (Caspian)   563 jumps   max 469.06 ly / 78.6 = 5.97x
#     mandalay                 10 jumps   max 360.14 ly / 93.0 = 3.87x
#
# Neither maximum EXCEEDS its multiplier, which is what a hard game-side cap looks like
# rather than a lucky tail; both fall just under it because the longest jump on record
# was not flown at the heaviest fuel state. A ship absent from the table gets 4.0, which
# is the rule rather than a guess -- though it has not been measured here, and a boosted
# range that is too generous is the direction that strands you.
DEFAULT_NEUTRON_BOOST = 4.0
SHIP_NEUTRON_BOOST = {"explorer_nx": 6.0}      # the Caspian, and nothing else


def neutron_boost(loadout):
    """-> what a jet cone multiplies this ship's range by. The ONE place that is decided.

    Falls back to the 4.0 every other hull flies at when there is no loadout to read,
    which keeps a chain plotted from a shorter range than the ship may really have:
    conservative in the direction that leaves you able to make the jump.
    """
    return SHIP_NEUTRON_BOOST.get((loadout or {}).get("Ship"), DEFAULT_NEUTRON_BOOST)


def drive_of(loadout):
    """-> the FSD's item name, lower case, or None if there is no drive we know."""
    for m in (loadout or {}).get("Modules", ()):
        item = (m.get("Item") or "").lower()
        if item in FSD:
            return item
    return None


def _fsd_of(loadout):
    """-> (constants, engineered optmass, booster ly), or None if unrecognised.

    Returns None rather than guessing. A drive missing from the table above means the
    game shipped something new, and a plausible-looking wrong range is worse than no
    range at all -- the caller shows nothing and you go and look it up.
    """
    spec = optmass = None
    boost = 0.0
    for m in loadout.get("Modules", ()):
        item = m.get("Item", "").lower()
        if item in FSD:
            spec = FSD[item]
            eng = m.get("Engineering") or {}
            optmass = next((d.get("Value") for d in eng.get("Modifiers", ())
                            if d.get("Label") == "FSDOptimalMass"), None)
        boost += BOOSTER.get(item, 0.0)
    if spec is None:
        return None
    return spec, optmass, boost


def jump_range(loadout, fuel=None, cargo=0.0):
    """Range in ly at `fuel` tonnes aboard, or None if the drive is unknown.

    `fuel=None` means a full tank, which is what the overlay plots on. `cargo` defaults
    to empty: this is an exploration build and a hold that is full on the way out and
    empty on the way back would make the displayed number a lie half the time.
    """
    found = _fsd_of(loadout)
    if not found:
        return None
    (fuelmul, fuelpower, maxfuel), optmass, boost = found
    if optmass is None:
        return None                 # unengineered drives are not something this ship has
    capacity = loadout.get("FuelCapacity") or {}
    tank = capacity.get("Main")
    reserve = capacity.get("Reserve", 0.0)
    if tank is None or not loadout.get("UnladenMass"):
        return None
    fuel = tank if fuel is None else min(fuel, tank)
    mass = loadout["UnladenMass"] + fuel + reserve + cargo
    return optmass / mass * (min(maxfuel, fuel) / fuelmul) ** (1 / fuelpower) + boost


def summary(loadout):
    """The overlay's one line about the ship, or None when it cannot be computed.

    Display-ready, like everything database.py returns, and for the same reason: the
    caller places text and does not do arithmetic.
    """
    laden = jump_range(loadout)
    if laden is None:
        return None
    return (f"jump {laden:.1f} ly   neutron "
            f"{laden * neutron_boost(loadout):.0f} ly "
            f"(x{neutron_boost(loadout):g}, {loadout.get('Ship')})")
