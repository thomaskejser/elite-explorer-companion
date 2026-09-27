"""What the three throttle LEDs mean. The only module that decides an LED colour.

`common/vkb.py` is the wire; this is the policy. It holds the last state it wrote and
sends nothing when the answer has not changed, because the tick runs eight times a
second and the LEDs change a few times an hour.

LEFT LIGHT -- FUEL, as a fraction of the MAIN tank. Green above 80%, then a gradient
through yellow to red, and a fast red flash below 25%. Dark when there is no reading:
the game is not running, or no Loadout has said how big the tank is. An LED that keeps
showing the last known level after the game closes is a lie the commander cannot see.

MIDDLE LIGHT -- THE ARRIVAL STAR OF THE NEXT JUMP. Blue for a neutron, flashing blue
for a white dwarf, flashing red for a black hole; dark for everything else and dark
when no jump is targeted. The three it names are the three that BOOST, and the flash
says the boost costs something -- a white dwarf's cone is small and its radiation
hurts, a black hole has no cone at all and is there to be looked at. Which classes
count is kinds.py's answer, not this module's.

RIGHT LIGHT -- THE SHIP'S OWN STATE. White while the cargo scoop is out, flashing blue
while the shields are down. Shields WIN when both are true: one is a warning and the
other is a note, and a warning that a note can hide is not a warning. Dark unless the
commander is IN the ship: the main menu writes `Flags` as a plain zero, which is
shields-down and cargo-scoop-stowed and no ship at all, and reading it as a warning
leaves the light flashing at a game nobody is playing.

*** THE GRADIENT IS 15 STEPS, NOT 256. *** VKB gives 3 bits per channel, so red and
green each move in eighths and the ramp between the thresholds is coarse. It reads as a
gradient at a glance and will never match a hex code on screen.
"""
from common.vkb import CONSTANT, FAST_BLINK, Throttle, from_vkb
from .journal import flag
from .kinds import KEY_OF_CLASS

FUEL_GREEN_ABOVE = 0.80
FUEL_FLASH_BELOW = 0.25
LEVELS = 7

FUEL_LED, TARGET_LED, SHIP_LED = 0, 1, 2

TARGET_COLORS = {
    "NEUTRON": ("#0000ff", CONSTANT),
    "WHT DWRF": ("#0000ff", FAST_BLINK),
    "BH": ("#ff0000", FAST_BLINK),
}


def fuel_color(fraction):
    """-> (hex colour, LED mode) for a main-tank fraction, or (None, None) if unknown."""
    if fraction is None:
        return None, None
    fraction = max(0.0, min(1.0, float(fraction)))
    if fraction >= FUEL_GREEN_ABOVE:
        return from_vkb([0, LEVELS, 0]), CONSTANT
    if fraction < FUEL_FLASH_BELOW:
        return from_vkb([LEVELS, 0, 0]), FAST_BLINK
    # Yellow sits at the midpoint: red rises over the top half of the ramp, green falls
    # over the bottom half, so both are full where they cross.
    u = (fraction - FUEL_FLASH_BELOW) / (FUEL_GREEN_ABOVE - FUEL_FLASH_BELOW)
    red = round(LEVELS * min(1.0, 2.0 * (1.0 - u)))
    green = round(LEVELS * min(1.0, 2.0 * u))
    return from_vkb([red, green, 0]), CONSTANT


def target_color(star_class):
    """-> (hex colour, LED mode) for the arrival class of the next jump.

    (None, None) for an ordinary star, which darkens the light: only the three that
    boost are worth a colour, and lighting the rest would make the light mean "a jump
    is targeted" instead of "look at this one".
    """
    return TARGET_COLORS.get(KEY_OF_CLASS.get(star_class), (None, None))


def has_shields(loadout):
    """-> True if the ship carries a shield generator at all.

    *** WITHOUT THIS THE LIGHT LIES ON AN UNSHIELDED HULL. *** `ShieldsUp` is simply
    clear when there is no generator, which is indistinguishable from a shield that has
    just gone down, and an explorer flying stripped would get a permanent blue flash.
    """
    return any("shieldgenerator" in (m.get("Item") or "")
               for m in (loadout or {}).get("Modules", ()))


def ship_color(status, loadout):
    """-> (hex colour, LED mode) for the ship's own state, or (None, None) if neither."""
    if not flag(status, "InMainShip"):
        return None, None
    if flag(status, "ShieldsUp") is False and has_shields(loadout):
        return "#0000ff", FAST_BLINK
    if flag(status, "CargoScoopDeployed"):
        return "#ffffff", CONSTANT
    return None, None


def fuel_fraction(status, loadout):
    """-> main tank fraction from a `Status.json` event and a `Loadout`, or None."""
    if not status or not loadout:
        return None
    main = (status.get("Fuel") or {}).get("FuelMain")
    tank = (loadout.get("FuelCapacity") or {}).get("Main")
    if main is None or not tank:
        return None
    return float(main) / float(tank)


class Lights:
    """The three LEDs as one state, resent whole whenever any of it moves.

    *** ALL THREE, EVERY TIME. *** A report replaces the device's whole table, so an
    LED left out of one goes dark -- writing the middle light on its own would blank
    the fuel light beside it.
    """

    def __init__(self, throttle=None, enabled=True):
        self.throttle = throttle if throttle is not None else Throttle()
        self.enabled = enabled
        self._want = [(None, None)] * len(self.throttle.leds)
        self._sent = None

    @property
    def present(self):
        return self.enabled and self.throttle.present

    def fuel(self, fraction):
        return self._show(FUEL_LED, fuel_color(fraction))

    def target(self, star_class):
        return self._show(TARGET_LED, target_color(star_class))

    def ship(self, status, loadout):
        return self._show(SHIP_LED, ship_color(status, loadout))

    def clear(self):
        self._want = [(None, None)] * len(self.throttle.leds)
        self._sent = None
        return self.enabled and self.throttle.off()

    def _show(self, index, state):
        self._want[index] = state
        if not self.enabled or self._sent == self._want:
            return False
        if self.throttle.show(self._want):
            self._sent = list(self._want)
            return True
        return False
