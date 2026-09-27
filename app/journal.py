"""Reading Elite's journal. The ONLY module that knows the journal exists.

Elite appends newline-delimited JSON to `Journal.<timestamp>.log` in the saved-games
directory, starting a fresh file per session. Everything the overlay reacts to arrives
there, so this module's whole job is: find the newest file, replay enough of it to know
where the commander is right now, then tail it and hand each interesting event on.

DESIGN: this is a POLLED reader, not a thread. `poll()` is non-blocking and returns the
events it found; the caller drives it from the Tk event loop. A background thread would
need a queue and a lock to hand events to widgets that may only be touched from the UI
thread, and there is nothing here worth that -- the file is local and a jump takes
tens of seconds.

The reader is DELIBERATELY IGNORANT of what the events mean. It yields dicts and lets
the caller decide; a module that both parses the journal and decides what a jump implies
is the one that becomes unmaintainable.
"""
import glob
import json
import os

# Where Elite writes, unless told otherwise.
DEFAULT_JOURNAL_DIR = os.path.join(
    os.path.expanduser("~"), "Saved Games", "Frontier Developments", "Elite Dangerous")

# Events that place the commander somewhere. All three carry StarSystem + StarPos.
#   FSDJump      -- a hyperspace jump completed
#   CarrierJump  -- arrived aboard a fleet carrier that jumped
#   Location     -- emitted on load, and the only one present if you start the app
#                   while already in-game, which is the normal case
POS_EVENTS = {"FSDJump", "CarrierJump", "Location"}

# Events that REVEAL AN ARRIVAL STAR CLASS without going there. Targeting a system in
# the galaxy map is enough: the game tells you what you would arrive at.
#   FSDTarget  -- a jump destination was selected (carries Name + StarClass)
#   StartJump  -- the countdown began (carries StarSystem + StarClass)
# This is the tool's entire edge. A class revealed here is a CERTAINTY about a system
# nobody has scanned, obtained for free, thousands of ly before anyone flies to it.
CLASS_EVENTS = {"FSDTarget", "StartJump"}

# The ship itself. Elite writes `Loadout` on login, on every outfitting change AND on
# every ship swap, so this is how "you are flying something else now" arrives -- and the
# jump range is what every neutron chain is solved against, so it cannot be read once at
# startup and assumed for the session.
SHIP_EVENTS = {"Loadout"}

INTEREST_EVENTS = POS_EVENTS | CLASS_EVENTS | SHIP_EVENTS

# What _interesting() greps for before it parses. Position and class events are found by
# a field they all carry; Loadout has no such field, so it is found by its own name.
INTEREST_KEYS = ('"StarPos"', '"StarClass"', '"Loadout"')

# Elite rewrites this whole file every time a route is plotted. Each hop carries both
# StarClass and StarPos, which makes it far richer than the journal events above --
# one plot can reveal fifty systems at once.
NAVROUTE_FILE = "NavRoute.json"
STATUS_FILE = "Status.json"


def latest_journal(journal_dir):
    """Newest Journal.*.log in `journal_dir`, or None."""
    files = glob.glob(os.path.join(journal_dir, "Journal.*.log"))
    return max(files, key=os.path.getmtime) if files else None


def _parse(line):
    try:
        return json.loads(line)
    except ValueError:
        # A partially flushed last line is normal when tailing a file being written.
        return None


class JournalReader:
    """Tails the newest journal, yielding position events.

    Usage:
        r = JournalReader(dir)
        start = r.prime()      # where we are right now, from the existing file
        ...
        for e in r.poll():     # call periodically; returns [] when nothing is new
            ...
    """

    def __init__(self, journal_dir=DEFAULT_JOURNAL_DIR):
        self.journal_dir = journal_dir
        self.path = None
        self._fh = None

    # -- lifecycle ---------------------------------------------------------------
    def prime(self):
        """Read the current journal from the top to find the LAST position event.

        Returns that event, or None. This is what makes the overlay useful the moment
        it starts rather than only after the next jump -- and the reason it reads the
        whole file instead of seeking to the end is that `Location` is written once, at
        load, so the only record of where you are may be thousands of lines back.

        Leaves the handle positioned at EOF, ready for poll().
        """
        self.path = latest_journal(self.journal_dir)
        if not self.path:
            return None
        last = None
        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"StarPos"' not in line:      # cheap reject before parsing JSON
                    continue
                e = _parse(line)
                if e and e.get("event") in POS_EVENTS and e.get("StarSystem"):
                    last = e
        self._open_at_end(self.path)
        return last

    def _open_at_end(self, path):
        self.close()
        self._fh = open(path, "r", encoding="utf-8", errors="replace")
        self._fh.seek(0, os.SEEK_END)

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None

    # -- polling -----------------------------------------------------------------
    def harvest_classes(self):
        """Re-read the current journal for every arrival class in it. -> list of rows.

        Run once at startup. A session's journal holds every system targeted since the
        game launched, and those reveals are free knowledge that would otherwise be
        thrown away because the tail only starts at EOF.
        """
        if not self.path:
            self.path = latest_journal(self.journal_dir)
        if not self.path:
            return []
        rows = []
        try:
            with open(self.path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    e = _interesting(line)
                    if e and e.get("event") in CLASS_EVENTS:
                        rows.append(class_of(e))
        except OSError:
            return []
        return [r for r in rows if r[0] and r[1]]

    def poll(self):
        """Non-blocking. -> list of new events of interest, oldest first.

        Handles the session rolling to a new journal file: Elite starts a new one on
        every launch, and an overlay that kept reading the old handle would silently
        stop updating while looking perfectly healthy.
        """
        if self._fh is None:
            primed = self.prime()
            return [primed] if primed else []

        events = []
        while True:
            line = self._fh.readline()
            if not line:
                break
            e = _interesting(line)
            if e:
                events.append(e)

        newest = latest_journal(self.journal_dir)
        if newest and newest != self.path:
            # Rolled over. Read the new file from the START -- not the end -- or the
            # Location event written at load is missed and the overlay sits blank
            # until the next jump.
            self.path = newest
            self.close()
            with open(newest, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    e = _interesting(line)
                    if e:
                        events.append(e)
            self._open_at_end(newest)
        return events


def _interesting(line):
    """Parse `line` if it is an event we care about, else None. One cheap reject first.

    *** THE REJECT HAS TO NAME EVERY EVENT SET. *** It runs on every line of a journal
    that is hundreds of thousands long, so it stays a substring test -- but a set left
    out of it is a set the tail silently never delivers, however carefully the caller
    handles it. `Loadout` carries neither `StarPos` nor `StarClass`.
    """
    if not any(k in line for k in INTEREST_KEYS):
        return None
    e = _parse(line)
    if not e or e.get("event") not in INTEREST_EVENTS:
        return None
    if e.get("event") in POS_EVENTS and not e.get("StarSystem"):
        return None
    return e


def class_of(event):
    """-> (system_name, star_class) from a class event. Either may be None.

    FSDTarget names the system in `Name`; StartJump uses `StarSystem`. Same fact,
    two spellings, so the caller should not have to know which event it has.
    """
    return (event.get("Name") or event.get("StarSystem"), event.get("StarClass"))


def read_loadout(journal_dir):
    """The ship you are flying right now. -> the newest `Loadout` event, or None.

    Elite writes `Loadout` on login and again on every outfitting change, so the LAST
    one in the newest journal is current. Read whole-file like prime() does, and for the
    same reason: the only copy may be thousands of lines back at the session start.

    Walks BACKWARDS through the journals rather than reading only the newest, because a
    session that began before the app did can leave the newest file with no `Loadout` in
    it at all -- the overlay is routinely started mid-flight. Newest by MTIME, the same
    answer `latest_journal()` gives: the old `Journal.<yymmddhhmmss>` naming still sits
    in the directory beside the current `Journal.<iso8601>` one and sorts ABOVE it.

    Returns the raw event. This module stays ignorant of what it means; ship.py decides.
    """
    for path in sorted(glob.glob(os.path.join(journal_dir, "Journal.*.log")),
                       key=os.path.getmtime, reverse=True):
        last = None
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"Loadout"' not in line:      # cheap reject before parsing JSON
                        continue
                    e = _parse(line)
                    if e and e.get("event") == "Loadout":
                        last = e
        except OSError:
            continue
        if last:
            return last
    return None


def read_navroute(journal_dir, last_mtime=None):
    """The plotted route. -> (rows, mtime), or (None, last_mtime) if unchanged.

    rows are (system_name, star_class, x, y, z) -- every hop, each one a system whose
    arrival star the game has just told us about. mtime-gated because the file is
    rewritten only on a plot and re-parsing it every tick is pure waste.
    """
    path = os.path.join(journal_dir, NAVROUTE_FILE)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None, last_mtime
    if last_mtime is not None and mtime <= last_mtime:
        return None, last_mtime
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None, mtime
    rows = []
    for hop in (data.get("Route") or []):
        name = hop.get("StarSystem")
        if not name:
            continue
        pos = hop.get("StarPos") or [None, None, None]
        rows.append((name, hop.get("StarClass"),
                     *(float(v) if v is not None else None for v in pos)))
    return rows, mtime


# Bit positions in Status.json's `Flags`. The names are Frontier's; what any of them is
# worth is lights.py's problem, not this module's.
STATUS_FLAGS = {
    "Docked": 0, "Landed": 1, "LandingGearDown": 2, "ShieldsUp": 3, "Supercruise": 4,
    "FlightAssistOff": 5, "HardpointsDeployed": 6, "InWing": 7, "LightsOn": 8,
    "CargoScoopDeployed": 9, "SilentRunning": 10, "ScoopingFuel": 11,
    "SrvHandbrake": 12, "SrvTurretView": 13, "SrvTurretRetracted": 14,
    "SrvDriveAssist": 15, "FsdMassLocked": 16, "FsdCharging": 17, "FsdCooldown": 18,
    "LowFuel": 19, "OverHeating": 20, "HasLatLong": 21, "IsInDanger": 22,
    "BeingInterdicted": 23, "InMainShip": 24, "InFighter": 25, "InSRV": 26,
    "HudAnalysisMode": 27, "NightVision": 28, "AltitudeFromAverageRadius": 29,
    "FsdJump": 30, "SrvHighBeam": 31,
}


def flag(status, name):
    """-> True/False for one Status.json flag, or None when there is no status."""
    if not status or "Flags" not in status:
        return None
    return bool(status["Flags"] >> STATUS_FLAGS[name] & 1)


def read_status(journal_dir, last_mtime=None):
    """The live ship state. -> (event, mtime), or (None, last_mtime) if unchanged.

    Elite rewrites `Status.json` IN PLACE on every change, so a read can catch it
    half-written. That returns the OLD mtime rather than the new one, leaving the gate
    open so the next tick tries again -- a swallowed parse error here would freeze the
    reading until the game happened to write once more.

    Returns the raw event. `Fuel`, `Flags`, `Pips`, `Cargo` and `GuiFocus` are all in
    it; this module stays ignorant of what any of them mean.
    """
    path = os.path.join(journal_dir, STATUS_FILE)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None, last_mtime
    if last_mtime is not None and mtime <= last_mtime:
        return None, last_mtime
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return json.load(f), mtime
    except (OSError, ValueError):
        return None, last_mtime


def position_of(event):
    """-> (system_name, (x, y, z), timestamp) from a position event."""
    pos = event.get("StarPos") or [None, None, None]
    return (event.get("StarSystem"),
            tuple(float(v) if v is not None else None for v in pos),
            event.get("timestamp"))
