#!/usr/bin/env python3
"""ED candidate ROUTER.

Reads your Elite Dangerous journal, and on every jump recomputes a short-as-possible
route through the undiscovered-candidate systems near you:

  * targets = BH/WR-capable systems (mass code f/g/h for black holes, h for
    Wolf-Rayets) that nobody has detail-scanned and that you have not visited;
  * on each jump, all targets within --radius (default 1000 ly) are collected and a
    travelling-salesman path is solved from your current position (nearest-neighbour
    construction + time-budgeted 2-opt);
  * the first --topn (default 10) waypoints are shown with the leg distance from the
    previous point on the route. Nothing is copied to the clipboard unless you pass
    --copy-next: the route re-solves on every jump, so copying by default would
    overwrite whatever you had there at moments you did not choose;
  * systems you have visited are remembered (journal-derived + a persistent store)
    so they never appear again.

If fewer than --topn targets lie within the radius, the route is extended past it by
nearest-neighbour so you always get a full list; extended waypoints are marked `+`.
The special case of ZERO targets in radius therefore behaves as: fly to the nearest
target, then continue through the next nine.

Usage:
  python ed_router.py                    # watch the journal live (default)
  python ed_router.py --once             # solve for current position and exit
  python ed_router.py --pos X Y Z        # solve for explicit coordinates
  python ed_router.py --radius 2000 --topn 10
  python ed_router.py --bh-codes efgh    # include mass code e as a BH target
  python ed_router.py --copy-next        # opt in to copying the next hop
  python ed_router.py --journal-dir "C:\\path\\to\\journals"

Needs: python + duckdb + numpy.
"""
import duckdb, os, sys, json, glob, time, argparse, pathlib, datetime, re, threading
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
CANDIDATES = HERE / "candidates.parquet"
REGIONS_FILE = HERE / "regions.parquet"
CARRIERS_FILE = HERE / "carriers.parquet"
NEUTRON_FILE = HERE / "neutron.parquet"
POI_FILE = HERE / "poi.parquet"
POI_SEEN_STORE = HERE / "poi_seen.json"
LEGACY_NSP_SEEN = HERE / "nsp_seen.json"     # pre-GGG name; merged in on load
CLASS_RATES_FILE = HERE / "class_rates.json"
REGION_NAMES_FILE = HERE / "region_names.json"
VISITED_STORE = HERE / "visited.json"
WRONG_STORE = HERE / "wrong.json"
STARCLASS_STORE = HERE / "starclass.json"
NAVROUTE_FILE = "NavRoute.json"
DEFAULT_JOURNAL_DIR = os.path.join(
    os.path.expanduser("~"), "Saved Games", "Frontier Developments", "Elite Dangerous")
POS_EVENTS = {"FSDJump", "CarrierJump", "Location"}

VISITED = set()          # system names the commander has already jumped to
WRONG = set()            # systems reported not to exist (bad PREDICTED gaps)
STARCLASS = {}           # system name -> arrival-star class, harvested from the journal

# Elite reports the ARRIVAL star's class without any scan, in FSDTarget / StartJump /
# NavRoute. That turns a probabilistic candidate into a confirmed one when the class
# is the thing we are hunting -- but it only ever describes the PRIMARY, so a normal
# class does not rule out a black hole or Wolf-Rayet deeper in the system.
BH_CLASSES = {"H", "SupermassiveBlackHole"}
WR_CLASSES = {"W", "WN", "WNC", "WC", "WO"}
CLASS_EVENTS = {"FSDTarget", "StartJump"}
# Plotting or clearing a route emits these. They carry no payload -- the route itself
# lands in NavRoute.json -- but they tell us the file just changed.
ROUTE_EVENTS = {"NavRoute", "NavRouteClear"}


def classify_star(cls):
    """'BH' | 'WR' | None for an Elite StarClass string."""
    if not cls:
        return None
    if cls in BH_CLASSES:
        return "BH"
    if cls in WR_CLASSES:
        return "WR"
    return None


# Journal StarClass -> the key used in class_rates.json. Pre-arrival events do not
# distinguish giants, so the table is keyed on the base letter; map defensively in
# case a giant code ever appears (e.g. 'B_BlueWhiteSuperGiant' -> 'B').
def journal_class_key(cls):
    if not cls:
        return None
    if cls in BH_CLASSES:
        return "H"
    if cls in WR_CLASSES or cls.startswith("W"):
        return "W*"
    if cls == "AeBe":
        return "AeBe"
    if cls == "TTS":
        return "TTS"
    if cls == "N":
        return "N"
    if cls.startswith("D"):
        return "D*"
    base = cls.split("_")[0]
    return base if base in {"O", "B", "A", "F", "G", "K", "M", "L", "T", "Y"} else None


# Never rule these out -- and only these. A revealed black-hole or Wolf-Rayet primary
# IS the find, so it cannot be disproved by its own class. Every other class, Herbig
# Ae/Be included, retires the system: a secondary is not what this tool hunts, and a
# class with a high secondary rate would otherwise hold a route slot forever.
PROTECTED_CLASSES = {"H", "W*"}

_CLASS_RATES = None


def load_class_rates():
    global _CLASS_RATES
    if _CLASS_RATES is not None:
        return _CLASS_RATES
    try:
        with open(CLASS_RATES_FILE, "r", encoding="utf-8") as f:
            _CLASS_RATES = json.load(f)
    except (OSError, ValueError):
        _CLASS_RATES = {}
    return _CLASS_RATES


def class_cell(star_class, mass_code=None):
    """(p_bh, p_wr, n) for the arrival class, or None if we have no measurement."""
    key = journal_class_key(star_class)
    if not key:
        return None
    R = load_class_rates()
    for k in ([mass_code] if mass_code else []) + ["*"]:
        d = (R.get(k) or {}).get(key)
        if d:
            return float(d["p_bh"]), float(d["p_wr"]), int(d.get("n", 0))
    return None


def class_prob(star_class, mass_code=None):
    """(p_bh, p_wr) point estimate for the arrival class -- the best guess."""
    c = class_cell(star_class, mass_code)
    return None if c is None else (c[0], c[1])


def class_bound(star_class, mass_code=None):
    """CONSERVATIVE P(BH or WR) for the arrival class -- never below its evidence.

    An observed 0% means very different things at n=83,588 and at n=146. By the rule
    of three, zero events in n trials implies the true rate is under 3/n at ~95%
    confidence, so that is the floor we use when deciding whether a system can be
    discarded. Discarding on a point estimate of 0 from a thin sample would throw
    away systems we simply have not looked at enough of.

    Display still shows the point estimate; only the DISCARD decision uses this.
    """
    c = class_cell(star_class, mass_code)
    if c is None:
        return None
    pb, pw, n = c
    tot = pb + pw
    return max(tot, 3.0 / n) if n > 0 else tot


def ruled_out(name, mass_code, floor):
    """True if the known arrival class puts this system below `floor`.

    Only fires when Elite has actually told us the class -- i.e. after you plot a
    route to it. Protected classes are never ruled out.
    """
    cls = STARCLASS.get(name)
    if not cls:
        return False
    key = journal_class_key(cls)
    if key in PROTECTED_CLASSES:
        return False
    b = class_bound(cls, mass_code)
    if b is None:
        return False
    return b < floor


def target_status(name, mass_code):
    """What, if anything, Elite has already told us about this candidate's primary.

    The label is PROVENANCE only -- it says which arrival class we saw, not how
    likely the system is. The probability itself is already folded into the BH/WR
    columns by effective_prob(), so repeating it here would duplicate the number.

    Returns (code, label):
      'primary' -- the arrival star IS a black hole / Wolf-Rayet: a CONFIRMED find
                   before you even arrive. Still undiscovered by anyone, so it is a
                   first-discovery just like a secondary one -- these are prizes, not
                   redundancies.
      'known'   -- arrival class known and is something else, so the BH/WR columns
                   now show the class-conditional rate rather than the prior.
      'unknown' -- no class known yet; plot to it and Elite will tell us for free.
    """
    cls = STARCLASS.get(name)
    if not cls:
        return "unknown", ""
    kind = classify_star(cls)
    if kind == "BH":
        return "primary", "*** PRIMARY:BH"
    if kind == "WR":
        return "primary", "*** PRIMARY:WR"
    pr = class_prob(cls, mass_code)
    b = class_bound(cls, mass_code)
    if pr is not None and b is not None and (pr[0] + pr[1]) <= 0 < b:
        # the column shows 0%; say how confident that zero actually is
        return "known", f"pri:{cls} <{b:.2%}"
    return "known", f"pri:{cls}"


# ---------------------------------------------------------------- visited set
def load_visited_from_journals(journal_dir):
    """Scan ALL journal files for systems the commander has visited."""
    n0 = len(VISITED)
    for path in glob.glob(os.path.join(journal_dir, "Journal.*.log")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if '"StarPos"' not in line:   # only located events name a system
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    if e.get("event") in POS_EVENTS and e.get("StarSystem"):
                        VISITED.add(e["StarSystem"])
        except OSError:
            continue
    return len(VISITED) - n0


# ------------------------------------------------------------ persistent stores
# Every store here is one JSON file holding one in-memory container, loaded once at
# startup and rewritten whenever it changes. They share these two primitives so the
# atomic-replace and the "a missing or corrupt file is empty, not fatal" rule are
# stated once: the app must start even if a store was truncated by a crash.
def _load_store(path, into):
    """Merge `path` into the set or dict `into`. Returns how many entries it added."""
    before = len(into)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return 0
    into.update(data)
    return len(into) - before


def _save_store(path, data, label):
    """Write via a temp file + os.replace, so a crash mid-write cannot truncate it."""
    try:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(sorted(data) if isinstance(data, set) else data,
                      f, indent=0, sort_keys=not isinstance(data, set))
        os.replace(tmp, path)
        return True
    except OSError as e:
        print(f"  (warning: could not save {label} store: {e})")
        return False


def load_visited_store():
    """Durable record, so targets stay retired even after old journals are deleted."""
    return _load_store(VISITED_STORE, VISITED)


def save_visited_store():
    return _save_store(VISITED_STORE, VISITED, "visited")


def load_wrong_store():
    """Systems tagged as not actually existing.

    Kept in its own file, separate from `visited.json`: a visit is a fact about the
    commander, whereas this is a correction to the DATA -- an enumerated boxel gap
    that turned out to be empty space. Keeping them apart means the corrections
    survive any rebuild of the visited set, and can be fed back into the pipeline.
    """
    return _load_store(WRONG_STORE, WRONG)


def save_wrong_store():
    return _save_store(WRONG_STORE, WRONG, "wrong")


def mark_wrong(name):
    """Tag `name` as non-existent so it is never routed to again."""
    if not name:
        return False
    WRONG.add(name)
    return save_wrong_store()


# ---------------------------------------------------------------- star classes
def load_starclass_store():
    _load_store(STARCLASS_STORE, STARCLASS)
    return len(STARCLASS)


def save_starclass_store():
    return _save_store(STARCLASS_STORE, STARCLASS, "starclass")


def note_starclass(name, cls):
    """Record an arrival-star class; True if this is new information."""
    if not name or not cls or STARCLASS.get(name) == cls:
        return False
    STARCLASS[name] = cls
    return True


def harvest_starclass_from_journals(journal_dir):
    """Scan every journal for arrival-star classes Elite has already told us.

    FSDTarget names the system in `Name`, StartJump in `StarSystem`.
    """
    n0 = len(STARCLASS)
    for path in glob.glob(os.path.join(journal_dir, "Journal.*.log")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if '"StarClass"' not in line:
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    if e.get("event") in CLASS_EVENTS:
                        note_starclass(e.get("Name") or e.get("StarSystem"), e.get("StarClass"))
        except OSError:
            continue
    return len(STARCLASS) - n0


# ---------------------------------------------------------------- outcomes
# ------------------------------------------------------- confirmed-but-unvisited
# A system whose arrival class Elite has already revealed as H or W* is a certain
# find: a black hole / Wolf-Rayet that nobody has catalogued. You will not always be
# in a position to go there when that happens -- it is usually thousands of ly off
# your current heading -- so it must survive being out of range, out of the route,
# and out of the candidate pool entirely.
#
# That last one is why this is its own file rather than a query over starclass.json:
# STARCLASS is keyed by name and can only be interpreted against candidates.parquet,
# which gets rebuilt. When a rebuild drops a name (EDAstro catalogued it, the boxel
# enumeration changed), the knowledge that YOU found a black hole there would vanish
# with it. Here it is recorded standalone -- name, class, coordinates -- so it keeps
# its meaning on its own.
#
# Entries are never deleted, only marked visited, so the file doubles as the log of
# what this tool has actually turned up.
CONFIRMED_STORE = HERE / "confirmed.json"
CONFIRMED = {}
STARPOS = {}          # name -> [x, y, z], harvested from NavRoute / journal events
STARPOS_STORE = HERE / "starpos.json"


def load_starpos_store():
    _load_store(STARPOS_STORE, STARPOS)
    return len(STARPOS)


def save_starpos_store():
    return _save_store(STARPOS_STORE, STARPOS, "starpos")


def apply_starpos(T):
    """Replace boxel-centroid coordinates with the exact ones Elite has given us.

    PREDICTED systems ship with the centre of their boxel, because the in-boxel offset
    is not derivable from the name -- so every gap in one boxel starts life at the same
    point, and for mass code h that point is +/-640 ly from the truth. Five rows all
    reading 783.8 ly is the visible symptom.

    NavRoute.json carries exact StarPos for every hop, so the moment you plot through
    one of these the real position is known and there is no reason to keep routing on
    the centroid. Returns how many rows were corrected.
    """
    if T is None or not STARPOS or T.get("approx") is None:
        return 0
    idx = _name_index(T)
    n = 0
    for nm, xyz in STARPOS.items():
        i = idx.get(nm)
        if i is None or not T["approx"][i]:
            continue
        T["xyz"][i] = xyz
        T["approx"][i] = False
        n += 1
    return n

# ---- audible alert on a new find ------------------------------------------------
# Plotting a route is what reveals arrival classes, and it happens in the galaxy map
# with the HUD behind it -- so the one moment worth noticing is the one you are least
# likely to be looking at. A black hole gets a descending tone and a Wolf-Rayet a
# rising one, so the two are distinguishable without reading anything.
SOUND_ENABLED = True
SOUND_FILE = None                 # optional .wav; overrides the generated tones
_NEW_CONFIRMED = []               # (name, kind) revealed since the last drain
_ALERT_ARMED = False              # first sync is the backfill -- stay silent for it

_TONES = {
    "BH": [(880, 130), (659, 130), (440, 300)],      # descending: something collapsed
    "WR": [(523, 110), (784, 110), (1047, 300)],     # rising: something bright
    # Neither rising nor falling: an alternating chirp, high above both, because this
    # one means "look at the nav panel" rather than "you found a rare star".
    "NSP": [(1319, 90), (988, 90), (1319, 90), (988, 90), (1319, 240)],
}
# --alert-sound replaces the BH/WR tones only. NSP keeps its generated chirp even
# then: one wav for every event would make the three indistinguishable, which is the
# whole point of having separate tones.
_TONE_ONLY = {"NSP"}


def _play_alert(kind):
    try:
        import winsound
    except ImportError:
        return                                        # not Windows; silently no-op
    try:
        if SOUND_FILE and kind not in _TONE_ONLY:
            winsound.PlaySound(str(SOUND_FILE),
                               winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
        for freq, ms in _TONES.get(kind, _TONES["BH"]):
            winsound.Beep(freq, ms)                   # blocking, hence the thread
    except Exception:
        pass                                          # a missing sound card is not an error


def alert(kind):
    """Sound the alert for a `kind` of 'BH'/'WR'/'NSP'. False if sound is off.

    Always on its own daemon thread: winsound.Beep blocks for the length of the tone
    and this is called from the Tk callback that redraws the HUD.
    """
    if not SOUND_ENABLED:
        return False
    threading.Thread(target=_play_alert, args=(kind,), daemon=True).start()
    return True


# ------------------------------------------------- notable stellar phenomena (NSP)
# The game announces these in the journal before you would have looked at the nav
# panel: `FSSSignalDiscovered` with `SignalType: "Codex"`. Measured across 154
# journals, that type is an exact discriminator -- 66 of 73,000+ signals carry it and
# every one localises to "Notable stellar phenomena", with no other type ever doing
# so. Match on the TYPE, not the name: `$Fixed_Event_Life_Cloud;` is the only name
# these logs contain, but other phenomena have their own names and the same type.
#
# No discovery scan is needed. Of the 12 visits that produced one, 8 never honked at
# all and half arrived on the same timestamp as the FSDJump -- it comes in with the
# nav panel, not with the FSS.
NSP_SIGNAL_TYPE = "Codex"


def nsp_from_event(e):
    """(system_address, label) if this journal line reports an NSP, else None.

    The address is returned rather than assumed: the game re-emits the whole signal
    list in bursts on supercruise drops and relogs, so a signal read from the journal
    is often NOT about the system you are standing in. Binding by SystemAddress
    instead of by the last position event fixes 26 of 66 mis-attributions.
    """
    if e.get("event") != "FSSSignalDiscovered" or e.get("SignalType") != NSP_SIGNAL_TYPE:
        return None
    return (e.get("SystemAddress"),
            e.get("SignalName_Localised") or e.get("SignalName") or "stellar phenomena")


# --- catalogued points of interest as routing targets -----------------------------
# Neither phenomena nor green gas giants are predictable the way a black hole is: there
# is no per-boxel rate to fit, only the systems somebody has already reported one in
# (built by scripts/build_poi.py). That is a lookup, not a model -- which is exactly
# why an unseen one nearby is worth the detour and cannot be found any other way.
#
# They are also NOT restricted to uncatalogued systems, unlike the BH/WR pool: you get
# the codex credit however many commanders arrived first, so "has anyone been here"
# simply does not bear on whether it is worth your time.
#
# One labelled file rather than one per type -- NSP and GGG differ only in the label
# the HUD prints in its Mass column, so the loader, the store and the search are shared.
_POI = None
POI_SEEN = set()          # systems whose points of interest you have already been to


def load_poi_seen_store():
    n = _load_store(POI_SEEN_STORE, POI_SEEN)
    return n + _load_store(LEGACY_NSP_SEEN, POI_SEEN)


def save_poi_seen_store():
    return _save_store(POI_SEEN_STORE, POI_SEEN, "poi-seen")


def note_poi_seen(name):
    """Record that you have been to `name`'s points of interest. True if new.

    Arriving is what counts, not scanning: a phenomenon is in the nav panel the moment
    you drop in, so once you have been there the system has nothing left to offer and
    it should stop competing for a waypoint slot. A green giant does need you to look
    at the right body, so this is slightly generous for GGG -- but a system you flew
    to and left is one you decided you were finished with either way.
    """
    if not name or name in POI_SEEN:
        return False
    POI_SEEN.add(name)
    return True


def load_poi():
    """Catalogued points of interest: name -> xyz, label ('NSP'/'GGG'), kinds."""
    global _POI
    if _POI is not None:
        return _POI
    if not POI_FILE.exists():
        _POI = {}
        return _POI
    c = duckdb.connect(":memory:")
    c.execute("SET threads=4")
    df = c.execute(f"SELECT name, x, y, z, label, kinds "
                   f"FROM '{POI_FILE.as_posix()}'").df()
    c.close()
    _POI = {
        "name": df.name.values.astype(object),
        "label": df.label.values.astype(object),
        "kinds": df.kinds.values.astype(object),
        "xyz": np.ascontiguousarray(df[["x", "y", "z"]].values, dtype=np.float32),
    }
    return _POI


def poi_xyz(name):
    """Coordinates of a point-of-interest system, or None if not catalogued."""
    P = load_poi()
    if not P:
        return None
    hit = np.flatnonzero(P["name"] == name)
    return P["xyz"][hit[0]] if len(hit) else None


def nearest_poi(pos, radius=1000.0, n=3):
    """Unseen POIs within `radius`, nearest first: [(name, dist, label, kinds), ...].

    Excludes POI_SEEN and VISITED -- if you have jumped to the system at all, you have
    already had the chance. A system carrying both an NSP and a green giant has a row
    per label in the file; only the nearer one survives here, since they are the same
    trip.
    """
    P = load_poi()
    if not P:
        return []
    p = np.asarray(pos, dtype=np.float32)
    xyz = P["xyz"]
    # box first: 69k rows is small, but this runs on every journal tick
    m = ((np.abs(xyz[:, 0] - p[0]) < radius) & (np.abs(xyz[:, 1] - p[1]) < radius)
         & (np.abs(xyz[:, 2] - p[2]) < radius))
    idx = np.flatnonzero(m)
    if not len(idx):
        return []
    d = np.linalg.norm(xyz[idx].astype(np.float64) - p.astype(np.float64), axis=1)
    keep = d <= radius
    idx, d = idx[keep], d[keep]
    # distance first; where a system carries both labels, GGG wins the tie -- 67 exist
    # in the whole galaxy against 68,583 phenomena, so it is the rarer thing to name
    pref = (P["label"][idx] != "GGG").astype(np.int8)
    out, seen = [], set()
    for k in np.lexsort((pref, d)):
        nm = str(P["name"][idx[k]])
        if nm in POI_SEEN or nm in VISITED or nm in seen:
            continue
        seen.add(nm)
        out.append((nm, float(d[k]), str(P["label"][idx[k]]),
                    str(P["kinds"][idx[k]])))
        if len(out) >= n:
            break
    return out


def drain_new_confirmed():
    """(name, kind) pairs revealed since the last call. Empties the queue."""
    global _NEW_CONFIRMED
    out, _NEW_CONFIRMED = _NEW_CONFIRMED, []
    return out


_MC_RE = re.compile(r"[A-Z]{2}-[A-Z] ([a-h])\d", re.I)


def mass_code_of(name):
    """Mass code read straight off a procedural name ('... AA-A h50' -> 'h').

    Used only when the system is no longer in candidates.parquet, so its mass code
    cannot be looked up. Hand-named systems have no code and return '?'.
    """
    m = _MC_RE.search(name or "")
    return m.group(1).lower() if m else "?"


def load_confirmed_store():
    _load_store(CONFIRMED_STORE, CONFIRMED)
    return len(CONFIRMED)


def save_confirmed_store():
    return _save_store(CONFIRMED_STORE, CONFIRMED, "confirmed")


def sync_confirmed(T=None):
    """Fold every revealed BH/WR primary into the persistent store. True if changed.

    Driven off STARCLASS, so it inherits every reveal path the app already has
    (FSDTarget, StartJump, NavRoute) without needing a hook at each call site.
    Coordinates are copied from the candidate arrays while the name is still there --
    the one thing that must be captured before a rebuild can drop it.
    """
    global _ALERT_ARMED, _NEW_CONFIRMED
    idx = _name_index(T) if T is not None else {}
    changed = False
    for name, cls in STARCLASS.items():
        kind = classify_star(cls)
        if kind not in ("BH", "WR"):
            continue
        rec = CONFIRMED.get(name)
        if rec is None:
            rec = {"cls": cls, "kind": kind,
                   "found": datetime.datetime.now().strftime("%Y-%m-%d")}
            CONFIRMED[name] = rec
            _NEW_CONFIRMED.append((name, kind))
            changed = True
        elif rec.get("cls") != cls:
            rec["cls"], rec["kind"] = cls, kind
            changed = True
        i = idx.get(name)

        # `pred` means THIS SYSTEM WAS IN NO DATABASE WHEN WE FOUND IT -- not merely
        # "was predicted to exist". A candidate carries source='predicted' only when
        # its name appears in no catalogue at all: not the EDSM/Spansh spine, not
        # EDAstro. So the pool answers the question exactly, but only while the system
        # is still IN the pool -- and finding one is what removes it. You scan it, it
        # uploads, EDAstro catalogues it, and the next build_candidates.py run drops it
        # via the known_rare filter. From then on idx.get(name) is None.
        #
        # It is therefore decided ONCE, at first sight, and never re-derived. Deriving
        # it again later would silently flip every successful find to '-' and erase the
        # only record that the system had been undiscovered.
        if rec.get("pred") is None:
            rec["pred"] = bool(i is not None and T is not None
                               and T["source"][i] == "predicted")
            changed = True
        if rec.get("mc") in (None, "?"):
            rec["mc"] = str(T["mc"][i]) if i is not None else mass_code_of(name)
            changed = True

        # STARPOS is what Elite reported, so it beats both the boxel centroid a
        # predicted row carries and anything a later rebuild might change
        if "x" in rec and "exact" not in rec:
            # a record carrying coordinates but no verdict on them: only a PREDICTED
            # row is ever a centroid, so its source settles it
            rec["exact"] = not bool(rec.get("pred"))
            changed = True
        if name in STARPOS and rec.get("exact") is not True:
            rec["x"], rec["y"], rec["z"] = STARPOS[name]
            rec["exact"] = True
            changed = True
        elif "x" not in rec and i is not None:
            rec["x"], rec["y"], rec["z"] = (float(v) for v in T["xyz"][i])
            rec["exact"] = not bool(T["approx"][i]) if T.get("approx") is not None else True
            changed = True
    # visiting one does not remove it -- the record is the point -- but it stops
    # being something you still owe a trip to
    for name, rec in CONFIRMED.items():
        v = name in VISITED
        if rec.get("visited") != v:
            rec["visited"] = v
            changed = True
    # the first pass folds in everything already known, which is not news
    if not _ALERT_ARMED:
        _NEW_CONFIRMED = []
        _ALERT_ARMED = True
    return changed


def pending_confirmed(pos=None, predicted_only=False):
    """Confirmed BH/WR systems you have NOT visited: PREDICTED first, then nearest.

    `predicted_only` follows the same mode as the route list, so the two tables never
    disagree about what you are hunting.

    Predicted systems lead because they are worth more than the distance saved by
    taking a catalogued one first. A predicted system is an enumerated boxel gap that
    has never appeared in any source, so flying to it settles two things -- what is in
    it AND that it exists at all -- and it is the only way to score the gap
    enumeration, which currently runs at x0.37 against prediction. A catalogued
    unscanned system will still be there next week; nothing else is competing for it.

    Range-independent by design: these are trip planning, not the next hop, and the
    whole reason the list exists is that they are usually far away when found.
    Entries with no coordinates yet (name only) sort last within their group.
    """
    out = []
    for name, rec in CONFIRMED.items():
        if rec.get("visited") or name in WRONG:
            continue
        if predicted_only and not rec.get("pred"):
            continue
        d = None
        if pos is not None and "x" in rec:
            d = float(np.linalg.norm(np.array([rec["x"], rec["y"], rec["z"]])
                                     - np.asarray(pos, dtype=float)))
        out.append((name, rec, d))
    out.sort(key=lambda t: (not t[1].get("pred"),          # predicted block first
                            t[2] is None,                  # unlocated last within each
                            t[2] if t[2] is not None else 0.0))
    return out


# ------------------------------------------------------------- model calibration
# Every time the game reveals a candidate's arrival class, we learn whether a
# prediction was right. That is the only unbiased measurement of the pool rate we
# will ever get -- the database can only ever tell us about systems somebody already
# scanned, which is a different population -- so it is written down permanently.
#
# One line per (system, model_version). The model_version pairing is the important
# part: rebuild the model and every known outcome is re-scored against the new
# prediction on the next tick, so a change can be judged on the whole history
# instead of only on systems flown since. scripts/analyse_observations.py turns this
# file into app/calibration.json, which build_candidates.py reads back.
OBSERVATIONS = HERE / "observations.jsonl"
CANDIDATES_META = HERE / "candidates_meta.json"
_OBS_SEEN = set()          # (name, model_version) already written
_MODEL_VERSION = None


def model_version():
    global _MODEL_VERSION
    if _MODEL_VERSION is None:
        try:
            with open(CANDIDATES_META, "r", encoding="utf-8") as f:
                _MODEL_VERSION = json.load(f).get("model_version", "unknown")
        except (OSError, ValueError):
            _MODEL_VERSION = "unknown"
    return _MODEL_VERSION


def load_observations():
    """Index what has already been logged, so appends stay idempotent."""
    try:
        with open(OBSERVATIONS, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                _OBS_SEEN.add((o.get("name"), o.get("model_version")))
    except OSError:
        pass
    return len(_OBS_SEEN)


def log_observations(T):
    """Append an outcome row for every revealed class not yet logged. Returns count.

    The row carries the prediction AS IT STOOD, not a reference to it -- the parquet
    is rebuilt and would otherwise silently rewrite history.
    """
    if T is None or not STARCLASS:
        return 0
    idx = _name_index(T)
    mv = model_version()
    new = []
    for name, cls in STARCLASS.items():
        if (name, mv) in _OBS_SEEN:
            continue
        i = idx.get(name)
        if i is None:
            continue                      # not a candidate; nothing was predicted
        kind = classify_star(cls)
        new.append({
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "model_version": mv,
            "name": name,
            "mass_code": str(T["mc"][i]),
            "boxel": str(T["boxel"][i]) if T.get("boxel") is not None else None,
            "boxel_index": (int(T["boxel_index"][i])
                            if T.get("boxel_index") is not None else None),
            "source": str(T["source"][i]),
            "p_bh": round(float(T["p_bh"][i]), 6),
            "p_wr": round(float(T["p_wr"][i]), 6),
            # logged but never scored here: a revealed arrival class says nothing about
            # a gas giant, so p_hr can only be checked against a real system scan
            "p_hr": (round(float(T["p_hr"][i]), 6)
                     if T.get("p_hr") is not None else None),
            "star_class": cls,
            "kind": kind,                 # 'BH' / 'WR' / None
            "hit": kind in ("BH", "WR"),
            "visited": name in VISITED,
        })
        _OBS_SEEN.add((name, mv))
    if not new:
        return 0
    try:
        with open(OBSERVATIONS, "a", encoding="utf-8") as f:
            for o in new:
                f.write(json.dumps(o, sort_keys=True) + "\n")
    except OSError:
        return 0
    return len(new)


OUTCOMES_STORE = HERE / "outcomes.json"


def _blank_outcome():
    return {"body_count": None, "all_found": False, "stars": []}


def scan_outcomes(journal_dir):
    """Per-system exploration outcome harvested from every journal.

    Three journal facts combine into a verdict:
      Scan (StarType)     -- what each star actually is
      FSSDiscoveryScan    -- BodyCount: how many bodies the system holds
      FSSAllBodiesFound   -- every body has been identified

    A system only counts as a resolved MISS when we know we have seen everything:
    either all bodies were found, or the honk said there is exactly one body and we
    scanned it. Anything else stays 'partial' and is excluded from calibration --
    counting a half-explored system as a miss would bias the observed rate down.
    """
    out = {}
    for path in glob.glob(os.path.join(journal_dir, "Journal.*.log")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if '"FSS' not in line and '"Scan"' not in line:
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    k = e.get("event")
                    if k == "FSSDiscoveryScan":
                        n = e.get("SystemName")
                        if n:
                            out.setdefault(n, _blank_outcome())["body_count"] = e.get("BodyCount")
                    elif k == "FSSAllBodiesFound":
                        n = e.get("SystemName")
                        if n:
                            r = out.setdefault(n, _blank_outcome())
                            r["all_found"] = True
                            if e.get("Count") is not None:
                                r["body_count"] = e.get("Count")
                    elif k == "Scan" and e.get("StarType"):
                        n = e.get("StarSystem") or e.get("SystemName")
                        if n:
                            r = out.setdefault(n, _blank_outcome())
                            if e["StarType"] not in r["stars"]:
                                r["stars"].append(e["StarType"])
        except OSError:
            continue
    for r in out.values():
        r["verdict"] = _verdict(r)
    return out


def _verdict(r):
    """'hit' | 'miss' | 'partial' for one system's outcome record."""
    kinds = {classify_star(s) for s in r["stars"]}
    if "BH" in kinds or "WR" in kinds:
        return "hit"
    fully = r["all_found"] or (r["body_count"] == 1 and len(r["stars"]) >= 1)
    return "miss" if fully else "partial"


def save_outcomes(outcomes):
    try:
        tmp = OUTCOMES_STORE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(outcomes, f, indent=0, sort_keys=True)
        os.replace(tmp, OUTCOMES_STORE)
        return True
    except OSError:
        return False


def calibration(T, outcomes):
    """Observed hit rate vs predicted probability, over RESOLVED candidate systems.

    Only systems that were candidates in our snapshot carry a prediction, and only
    resolved ones carry a trustworthy answer, so the intersection is what we can
    honestly score. Returns (rows, totals).
    """
    idx = {str(n): i for i, n in enumerate(T["name"])}
    rows = []
    for name, r in outcomes.items():
        i = idx.get(name)
        if i is None or r["verdict"] == "partial":
            continue
        p = max(float(T["p_bh"][i]), float(T["p_wr"][i]))
        rows.append((name, str(T["mc"][i]), p, r["verdict"] == "hit",
                     r["body_count"], ",".join(r["stars"])))
    return rows
def read_navroute(journal_dir):
    """The route currently plotted in the galaxy map, or None.

    Elite rewrites NavRoute.json on every plot. Each hop carries StarClass, so
    plotting to a candidate immediately tells us its primary star type -- which is
    also harvested into STARCLASS here as a side effect.
    """
    p = os.path.join(journal_dir, NAVROUTE_FILE)
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    hops = d.get("Route") or []
    if not hops:
        return None
    new = False
    for h in hops:
        if note_starclass(h.get("StarSystem"), h.get("StarClass")):
            new = True
        # every hop carries exact coordinates -- the only source of them for a system
        # that is NOT in candidates.parquet, which is precisely the case for anything
        # a rebuild has since dropped. sync_confirmed() falls back to this.
        if h.get("StarSystem") and h.get("StarPos"):
            xyz = [float(v) for v in h["StarPos"]]
            if STARPOS.get(h["StarSystem"]) != xyz:
                STARPOS[h["StarSystem"]] = xyz
                new = True
    if new:
        save_starclass_store()
        save_starpos_store()
    return {
        "hops": [h.get("StarSystem") for h in hops],
        "pos": [h.get("StarPos") for h in hops],
        "timestamp": d.get("timestamp"),
        "destination": hops[-1].get("StarSystem"),
    }


def navroute_progress(route, current_system, pos):
    """(jump_index, total_jumps, ly_remaining) along the plotted route.

    Position in the route is taken by name where possible, falling back to the
    nearest hop by distance (you can jump onto a route part-way through).
    """
    if not route or not route["hops"]:
        return None
    hops, hp = route["hops"], route["pos"]
    total = len(hops) - 1
    idx = hops.index(current_system) if current_system in hops else None
    if idx is None and pos is not None:
        d = [float(np.linalg.norm(np.asarray(p, dtype=float) - pos)) for p in hp]
        idx = int(np.argmin(d))
    if idx is None:
        return None
    rem = 0.0
    for i in range(idx, total):
        rem += float(np.linalg.norm(np.asarray(hp[i + 1], dtype=float)
                                    - np.asarray(hp[i], dtype=float)))
    return idx, total, rem


# ---------------------------------------------------------------- clipboard
def copy_to_clipboard(text):
    """Win32 clipboard via ctypes (no dependencies, unicode-safe), then fallbacks."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
            u32, k32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GlobalAlloc.restype = wintypes.HGLOBAL
            k32.GlobalLock.restype, k32.GlobalLock.argtypes = ctypes.c_void_p, [wintypes.HGLOBAL]
            k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
            u32.SetClipboardData.restype = wintypes.HANDLE
            u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
            buf = ctypes.create_unicode_buffer(text)
            size = ctypes.sizeof(buf)
            if not u32.OpenClipboard(None):
                return False
            try:
                u32.EmptyClipboard()
                h = k32.GlobalAlloc(GMEM_MOVEABLE, size)
                if not h:
                    return False
                p = k32.GlobalLock(h)
                ctypes.memmove(p, buf, size)
                k32.GlobalUnlock(h)
                if not u32.SetClipboardData(CF_UNICODETEXT, h):
                    return False
            finally:
                u32.CloseClipboard()
            return True
        except Exception:
            pass
    try:
        import subprocess
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text, text=True, check=True)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, check=True)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- regions
_REG = None


def load_regions():
    """Region-labelled reference points, for naming the region you are in.

    ED's 42 regions are hand-drawn areas with no closed form, so position -> region
    is a nearest-neighbour lookup against EDAstro's labelled systems (99.55% accurate
    on a hold-out; see scripts/build_regions.py). 545k points is small enough to
    brute-force in numpy per jump, so no scipy dependency at runtime.
    """
    global _REG
    if _REG is not None:
        return _REG
    if not REGIONS_FILE.exists():
        _REG = {}
        return _REG
    c = duckdb.connect(":memory:")
    df = c.execute(f"SELECT x, y, z, region_id FROM '{REGIONS_FILE.as_posix()}'").df()
    c.close()
    names = {}
    try:
        with open(REGION_NAMES_FILE, "r", encoding="utf-8") as f:
            names = {int(k): v for k, v in json.load(f).items()}
    except (OSError, ValueError):
        pass
    _REG = {
        "xyz": np.ascontiguousarray(df[["x", "y", "z"]].values, dtype=np.float32),
        "id": df.region_id.values.astype(np.int16),
        "names": names,
    }
    return _REG


def region_name(rid):
    R = load_regions()
    if rid is None:
        return None
    return (R.get("names", {}) or {}).get(int(rid), f"Region {int(rid)}")


def region_of(pos, k=5):
    """(region_id, name, votes, dist_to_nearest_label_ly) for a position.

    `votes` (out of k) and the label distance are the confidence signals: a 5/5 vote
    a few ly away is certain; a split vote or a distant label means you are near a
    region boundary or out in sparsely-surveyed space.
    """
    R = load_regions()
    if not R:
        return None, None, 0, None
    d2 = ((R["xyz"] - np.asarray(pos, dtype=np.float32)) ** 2).sum(1)
    kk = min(k, len(d2))
    idx = np.argpartition(d2, kk - 1)[:kk]
    idx = idx[np.argsort(d2[idx])]
    labs = R["id"][idx]
    vals, cnt = np.unique(labs, return_counts=True)
    top = int(vals[cnt.argmax()])
    return top, region_name(top), int(cnt.max()), float(np.sqrt(d2[idx[0]]))


# ---------------------------------------------------------------- carriers
_CARRIERS = None


def load_carriers():
    """Fleet carriers offering Universal Cartographics (plus all DSSA carriers).

    Built by scripts/build_carriers.py from EDAstro. Empty dict if the file is
    missing, so the app degrades quietly rather than failing.
    """
    global _CARRIERS
    if _CARRIERS is not None:
        return _CARRIERS
    if not CARRIERS_FILE.exists():
        _CARRIERS = {}
        return _CARRIERS
    c = duckdb.connect(":memory:")
    df = c.execute(f"""SELECT callsign, name, system, x, y, z, region, last_moved,
                              has_uc, is_dssa
                       FROM '{CARRIERS_FILE.as_posix()}'""").df()
    c.close()
    _CARRIERS = {
        "callsign": df.callsign.values.astype(object),
        "name": df.name.values.astype(object),
        "system": df.system.values.astype(object),
        "xyz": np.ascontiguousarray(df[["x", "y", "z"]].values, dtype=np.float64),
        "last_moved": df.last_moved.values.astype(object),
        "has_uc": df.has_uc.values.astype(bool),
        "is_dssa": df.is_dssa.values.astype(bool),
    }
    return _CARRIERS


# Carriers MOVE. carriers.parquet is a snapshot, and the one thing it cannot tell you
# is that the carrier jumped away yesterday -- you find that out by flying there and
# arriving at an empty system, several thousand ly from an alternative. Tagging it
# retires it from every future suggestion, so the next-nearest one takes its place
# immediately. Same idea as WRONG for systems; kept in its own file because a carrier
# is keyed by callsign and comes back if a later carriers.parquet refresh proves it.
CARRIER_GONE_STORE = HERE / "carrier_gone.json"
CARRIER_GONE = set()


def load_carrier_gone_store():
    _load_store(CARRIER_GONE_STORE, CARRIER_GONE)
    return len(CARRIER_GONE)


def save_carrier_gone_store():
    return _save_store(CARRIER_GONE_STORE, CARRIER_GONE, "carrier-gone")


def mark_carrier_gone(callsign):
    """Tag a carrier as no longer at its recorded system. True if newly tagged."""
    if not callsign:
        return False
    cs = str(callsign).strip().upper()
    if cs in CARRIER_GONE:
        return False
    CARRIER_GONE.add(cs)
    save_carrier_gone_store()
    return True


def unmark_carrier_gone(callsign):
    """Untag a carrier (it was there after all, or it came back)."""
    cs = str(callsign or "").strip().upper()
    if cs not in CARRIER_GONE:
        return False
    CARRIER_GONE.discard(cs)
    save_carrier_gone_store()
    return True


def nearest_carriers(pos, n=1, require_uc=True, dssa_only=False, include_gone=False):
    """Closest carriers to `pos` as [(index, distance_ly), ...].

    Carriers you have tagged gone are skipped, so asking for one alternative really
    does return an alternative rather than the same empty system again.
    """
    C = load_carriers()
    if not C:
        return []
    sel = np.ones(len(C["callsign"]), dtype=bool)
    if require_uc:
        sel &= C["has_uc"]
    if dssa_only:
        sel &= C["is_dssa"]
    if CARRIER_GONE and not include_gone:
        for j, cs in enumerate(C["callsign"]):
            if str(cs).upper() in CARRIER_GONE:
                sel[j] = False
    idx = np.flatnonzero(sel)
    if len(idx) == 0:
        return []
    d = np.linalg.norm(C["xyz"][idx] - np.asarray(pos, dtype=float)[None, :], axis=1)
    order = np.argsort(d)[:n]
    return [(int(idx[k]), float(d[k])) for k in order]


# ---------------------------------------------------------------- neutron stars
_NEUTRON = None


def load_neutron():
    """CONFIRMED neutron-star systems (scanned and uploaded), for FSD supercharging.

    Not candidates -- these are systems where a neutron star has actually been seen,
    so a jet-cone boost is a certainty rather than a 27% bet.
    """
    global _NEUTRON
    if _NEUTRON is not None:
        return _NEUTRON
    if not NEUTRON_FILE.exists():
        _NEUTRON = {}
        return _NEUTRON
    c = duckdb.connect(":memory:")
    c.execute("SET threads=4")
    df = c.execute(f"SELECT name, x, y, z FROM '{NEUTRON_FILE.as_posix()}'").df()
    c.close()
    _NEUTRON = {
        "name": df.name.values.astype(object),
        "xyz": np.ascontiguousarray(df[["x", "y", "z"]].values, dtype=np.float32),
    }
    return _NEUTRON


def _neutron_box(p, n, seed=250.0, centre=None, reach=None):
    """Indices of neutron systems near `p`, widening a box until it holds >= n.

    3.5M rows, so a full norm on every jump would be wasteful. `centre`/`reach` let
    the box be placed and sized around a whole leg rather than around you.
    """
    N = load_neutron()
    xyz = N["xyz"]
    c = np.asarray(centre if centre is not None else p, dtype=np.float32)
    box = float(reach) if reach else seed
    m = None
    for _ in range(8):
        m = ((np.abs(xyz[:, 0] - c[0]) < box) & (np.abs(xyz[:, 1] - c[1]) < box)
             & (np.abs(xyz[:, 2] - c[2]) < box))
        if int(m.sum()) >= n:
            break
        box *= 3.0
    idx = np.flatnonzero(m)
    return idx if len(idx) else np.arange(len(xyz))   # fall back to the whole set


def nearest_neutron(pos, n=3, target=None):
    """Confirmed neutron stars as [(name, distance_from_you_ly), ...].

    With no `target`, ranks on distance from you: the closest supercharge.

    With a `target` -- the system you are actually trying to reach -- ranks on the
    length of the whole diverted leg instead:

        score = |you -> neutron| + |neutron -> target|

    A star sitting on the line scores the direct distance and costs nothing; one
    off to the side or behind you scores more, in proportion to the detour it
    forces. This is the difference between a supercharge that advances the trip and
    one that spends the 4x boost undoing the diversion that earned it. The reported
    distance is still the distance from YOU, because that is the jump you have to
    make; ranking and reporting answer different questions.
    """
    N = load_neutron()
    if not N:
        return []
    p = np.asarray(pos, dtype=np.float64)
    if target is None:
        idx = _neutron_box(p.astype(np.float32), n)
        d = np.linalg.norm(N["xyz"][idx].astype(np.float64) - p, axis=1)
        order = np.argsort(d)[:n]
        return [(str(N["name"][idx[k]]), float(d[k])) for k in order]

    t = np.asarray(target, dtype=np.float64)
    leg = float(np.linalg.norm(t - p))
    # a box over the whole leg: anything that could plausibly be on the way is inside
    # the midpoint box of half-length leg/2 plus a margin for stars slightly off-line
    idx = _neutron_box(p.astype(np.float32), n,
                       centre=(p + t) / 2.0, reach=leg / 2.0 + 200.0)
    xyz = N["xyz"][idx].astype(np.float64)
    d_you = np.linalg.norm(xyz - p, axis=1)
    score = d_you + np.linalg.norm(xyz - t, axis=1)
    order = np.argsort(score)[:n]
    return [(str(N["name"][idx[k]]), float(d_you[k])) for k in order]


# ---------------------------------------------------------------- targets
def load_targets(bh_codes):
    """Load every candidate that is a BH or WR target into memory once.

    Returns a dict of parallel numpy arrays. Held in RAM so each jump only costs
    vector maths, not a re-scan of the parquet.
    """
    if not CANDIDATES.exists():
        sys.exit(f"missing {CANDIDATES} -- run scripts/build_candidates.py first")
    codes = sorted(set(bh_codes) | {"h"})
    inlist = ",".join(f"'{c}'" for c in codes)
    con = duckdb.connect(":memory:")
    con.execute("SET threads=4")
    cols = {r[0] for r in con.execute(
        f"DESCRIBE SELECT * FROM '{CANDIDATES.as_posix()}' LIMIT 0").fetchall()}
    has_region = "region" in cols            # older candidates.parquet lacks it
    has_boxel = "boxel" in cols and "boxel_index" in cols   # added with the L*S*R model
    has_hr = "p_hr" in cols                  # added with the helium-rich gas giant model
    sel = ("name, x, y, z, mass_code, p_bh, p_wr, source"
           + (", p_hr" if has_hr else "")
           + (", region" if has_region else "")
           + (", boxel, boxel_index" if has_boxel else ""))
    df = con.execute(f"""
        SELECT {sel}
        FROM '{CANDIDATES.as_posix()}'
        WHERE mass_code IN ({inlist})
    """).df()
    con.close()
    bh_ok = df.mass_code.isin(list(bh_codes)).values
    df["p_bh"] = np.where(bh_ok, df.p_bh.values, 0.0)      # e excluded from BH unless asked for
    return {
        "name": df.name.values.astype(object),
        "xyz": np.ascontiguousarray(df[["x", "y", "z"]].values, dtype=np.float64),
        "mc": df.mass_code.values.astype(object),
        "p_bh": df.p_bh.values.astype(np.float64),
        "p_wr": df.p_wr.values.astype(np.float64),
        # a separate, unrelated target: a system can hold a black hole AND a helium-rich
        # gas giant, so p_hr never competes with p_bh/p_wr and is not part of the ranking
        "p_hr": (df.p_hr.values.astype(np.float64) if has_hr
                 else np.zeros(len(df), dtype=np.float64)),
        "source": df.source.values.astype(object),
        "region": (df.region.values.astype(np.int16) if has_region
                   else np.full(len(df), -1, dtype=np.int16)),
        # logged with every outcome: the index is the model's strongest feature, so a
        # calibration file without it cannot diagnose where the model goes wrong
        "boxel": df.boxel.values.astype(object) if has_boxel else None,
        "boxel_index": df.boxel_index.values.astype(np.int64) if has_boxel else None,
        # predicted rows start on the boxel centroid, so their distance is a guess
        # until apply_starpos() replaces it with what Elite actually reported
        "approx": (df.source.values == "predicted"),
    }


_NAME_IDX = None


def _name_index(T):
    """name -> row, so the per-jump work scales with what we KNOW, not with the corpus.

    The candidate arrays hold ~2.3M rows while the visited / star-class / wrong sets hold
    a few thousand names between them. Walking every row to test membership costs ~2.3M
    Python-level dict probes per call, and available_mask/p_any run several times on each
    jump; walking the small sets and indexing into the arrays is the same result for a
    fraction of the time.
    """
    global _NAME_IDX
    if _NAME_IDX is None or len(_NAME_IDX) != len(T["name"]):
        _NAME_IDX = {str(x): i for i, x in enumerate(T["name"])}
    return _NAME_IDX


def prob_cols(pb, pw, width=6):
    """(bh_str, wr_str) for rendering as two independent columns.

    A zero renders as '-' rather than '0%' because it is usually STRUCTURAL, not
    merely small: mass codes f and g cannot host a Wolf-Rayet at all (R1), so '-'
    says "impossible here" while '0%' would imply "possible but unlikely".
    """
    def f(v):
        return "-" if v <= 0 else f"{v:.0%}"
    return f"{f(pb):>{width}}", f"{f(pw):>{width}}"


# ------------------------------------------------------------- one row layout
# Every candidate table -- the route, the confirmed finds, the nearest predicted --
# renders through star_row(), so a system looks identical wherever it appears and the
# columns line up when the tables are stacked. Both frontends use it; only the width
# of the name column differs, because the terminal has more room than the HUD.
#
#   system   dist   Mass   BH   WR   HR   Pred   Conf
#
# Mass is the boxel mass code (e/f/g/h), which gates what can be there at all: h is
# the only Wolf-Rayet host and carries the best black-hole rate, e can barely hold
# one. Pred is Y for an enumerated boxel gap, '-' for a catalogued system. Conf is the
# arrival class Elite has revealed (WO, WNC, H, ...) or '-' if it is still unknown --
# which makes "confirmed" a property of the row rather than a separate table.
#
# HR is the chance of an undiscovered helium-rich gas giant, and it is shown ONLY on
# PREDICTED rows. On a catalogued system the number would be a lie of a different kind
# from the BH/WR ones: p_hr is driven by the boxel's published gas-giant helium, which
# exists precisely BECAUSE somebody scanned gas giants in that boxel -- so on a system
# that is already in a catalogue there is no way to tell whether the giant that set the
# helium figure is the very one you would be flying to. On a system in no catalogue at
# all, nobody has taken anything out of it. See scripts/build_candidates.py.
STAR_COLS = "{sys}{dist:>8}{mass:>6}{bh}{wr}{hr:>6}{pred:>6}{conf:>7}"


def star_header(name_w=24, extra=""):
    """Column header matching star_row. Leading space reserves the +/space flag."""
    return (" " + STAR_COLS.format(sys=f"{'system':{name_w}}", dist="dist", mass="Mass",
                                   bh=f"{'BH':>6}", wr=f"{'WR':>6}", hr="HR",
                                   pred="Pred", conf="Conf") + extra)


def confirmed_class(name):
    """The revealed arrival class if it is a BH/WR, else None -- the `Conf` column."""
    cls = STARCLASS.get(str(name))
    return cls if classify_star(cls) else None


def is_approx(T, i):
    """True while row `i` still sits on its boxel centroid rather than a real position."""
    return bool(T["approx"][i]) if T.get("approx") is not None else False


def star_row_at(T, i, dist, **kw):
    """star_row for candidate row `i`, reading every column off the target arrays."""
    return star_row(T["name"][i], dist, *effective_prob(T, i),
                    predicted=T["source"][i] != "unscanned",
                    conf=confirmed_class(T["name"][i]), approx=is_approx(T, i),
                    mass=str(T["mc"][i]),
                    p_hr=float(T["p_hr"][i]) if T.get("p_hr") is not None else 0.0, **kw)


def star_row_confirmed(name, rec, dist, **kw):
    """star_row for a CONFIRMED record, which may no longer be in the candidate pool.

    Its odds are the outcome, not a prior: the class is known, so one column is 100%
    and the other is structurally impossible.
    """
    p_bh, p_wr = (1.0, 0.0) if rec.get("kind") == "BH" else (0.0, 1.0)
    return star_row(name, dist, p_bh, p_wr, predicted=bool(rec.get("pred")),
                    conf=rec.get("cls"), approx=not rec.get("exact", False),
                    mass=rec.get("mc"), **kw)


def star_row(name, dist, p_bh, p_wr, predicted, conf=None, approx=False, ext=False,
             mass=None, p_hr=0.0, pred_text=None, name_w=24, extra=""):
    """One candidate as a table row.

    `dist` None renders '?' (no coordinates known); `approx` prefixes '~' to mean the
    row is still on its boxel centroid and can be out by half a boxel edge. `ext`
    marks a waypoint beyond the search radius. `extra` appends a trailing column --
    used only by `--sort route` for the cumulative distance, so the seven shared columns
    stay aligned across every table.
    """
    bh, wr = prob_cols(p_bh, p_wr)
    d = "?" if dist is None else f"{'~' if approx else ''}{dist:,.0f}"
    # HR only on predicted rows, and '-' everywhere else -- see the STAR_COLS note
    hr = f"{p_hr:.0%}" if (predicted and p_hr and p_hr > 0) else "-"
    # falling back to the name keeps the column filled for rows that carry no mass
    # code of their own -- a neutron star or a confirmed find that has left the pool
    return ("+" if ext else " ") + STAR_COLS.format(
        sys=f"{str(name)[:name_w]:{name_w}}", dist=d,
        mass=(mass or mass_code_of(name) or "?"), bh=bh, wr=wr, hr=hr,
        # 'Y' against '-' rather than 'Y'/'N': a column of Y and N reads as two equal
        # options, and a predicted system is the one worth spotting at a glance.
        # `pred_text` overrides it where the row is about more than one system -- the
        # adjacent-sector rows put the sector's predicted-system COUNT here.
        pred=(pred_text if pred_text is not None else ("Y" if predicted else "-")),
        conf=(conf or "-")) + extra


def sector_row(rec, name_w=24, extra=""):
    """An ADJACENT-SECTOR row: the destination system, rendered like any other.

    BH / WR / HR / Mass are the DESTINATION system's own numbers, on the same
    percentage rules as every other row, because that is the system the key copies and
    the one you will actually arrive in. Only `Pred` is repurposed -- it carries how
    many predicted systems the sector holds, which is what makes the row about a sector
    at all. The sector name is not printed: it is the leading words of the system name.

    The sector's expected BH+WR count is the RANKING (see adjacent_sector_targets) and
    shows up as the row order plus the status line when you press the key, rather than
    as a column -- mixing counts and percentages in one column reads badly.
    """
    return star_row(rec["name"], rec["dist"], rec["p_bh"], rec["p_wr"],
                    predicted=True, p_hr=rec.get("p_hr", 0.0),
                    pred_text=f"{rec['n_sys']:,}", name_w=name_w, extra=extra)


def prob_label(pb, pw):
    """(total, label) for a candidate's black-hole / Wolf-Rayet probabilities.

    The two are near-mutually-exclusive in a system (P(both)=0.0002 against 0.1267 if
    independent), so the total is their SUM and the split is real information: a
    mass-code-h candidate is not '72% black hole', it is 47% black hole OR 25%
    Wolf-Rayet. Collapsing that to one number hides which prize you are chasing.

    f/g candidates have p_wr identically 0 (R1: Wolf-Rayets occur only in h), so they
    correctly show as BH only.
    """
    tot = min(1.0, pb + pw)
    if pw <= 0:
        return tot, "BH"
    if pb <= 0:
        return tot, "WR"
    return tot, f"BH{pb*100:.0f}/WR{pw*100:.0f}"


def p_any(T, use_class=True):
    """P(black hole OR Wolf-Rayet) per candidate.

    Measured on scanned mass-code-h systems, the two are very nearly MUTUALLY
    EXCLUSIVE -- P(both)=0.0002 against 0.1267 if they were independent. So the union
    is the sum, not 1-(1-p)(1-q), which would understate an h system by ~13 points
    (61% vs the true 73%).
    """
    pb, pw = T["p_bh"], T["p_wr"]
    if use_class and STARCLASS:
        pb, pw = pb.copy(), pw.copy()
        idx = _name_index(T)
        for nm, cls in STARCLASS.items():
            i = idx.get(nm)
            if i is None:
                continue
            pr = class_prob(cls, str(T["mc"][i]))
            if pr is not None:
                pb[i], pw[i] = pr
    return np.minimum(1.0, pb + pw)


def region_target_count(T, mask, rid):
    """Routable targets (unvisited, not tagged wrong) that lie in region `rid`."""
    if rid is None or T["region"] is None:
        return 0
    return int(np.count_nonzero(mask & (T["region"] == np.int16(rid))))


# ------------------------------------------------------------ sector geometry
# Procedural sectors are 1280 ly cubes on a fixed lattice. Verified against our own
# 194.7M systems rather than taken on trust: per-sector bounding boxes span 1279.8-1280.0
# ly on every axis, and their lower corners share one residue mod 1280 (x 1215, y 1255,
# z 215), which pins the origin below. So a sector is exact arithmetic on coordinates --
# no name generation needed -- and "adjacent" is +/-1 on each axis, 26 neighbours.
#
# Caveat: ~2.3% of sector NAMES are hand-authored (Col 359 Sector spans 6 cells, NGC 2546
# eight) and break the name<->cell bijection near nebulae and clusters. Out in procgen
# space the mapping is clean, and that is where the candidate pool lives.
SECTOR_LY = 1280.0
SECTOR_ORIGIN = np.array([-49985.0, -40985.0, -24105.0])
_SECTOR_RE = re.compile(r" [A-Z][A-Z]-[A-Z] [a-h][0-9]+(-[0-9]+)?$")


def sector_of(name):
    """The procedural sector a system name belongs to, or None if it is not procgen."""
    s = _SECTOR_RE.sub("", str(name))
    return s if s != str(name) else None


def sector_cell(pos):
    """(i, j, k) lattice cell of a position, as plain ints."""
    c = np.floor((np.asarray(pos, dtype=np.float64) - SECTOR_ORIGIN) / SECTOR_LY)
    return tuple(int(v) for v in c)


_PRED_SEC = None


def _predicted_sectors(T):
    """(sector name, cell) per PREDICTED candidate, computed once and cached.

    Only the predicted rows: they are ~51k of 2.25M, so deriving sector names for the
    whole pool would cost 40x more for nothing. Cached on the array identity so a
    reload rebuilds it.
    """
    global _PRED_SEC
    if _PRED_SEC is not None and _PRED_SEC[0] is T["name"]:
        return _PRED_SEC[1]
    idx = np.flatnonzero(T["source"] == "predicted")
    sec = np.array([sector_of(T["name"][i]) or "" for i in idx], dtype=object)
    cell = np.floor((T["xyz"][idx] - SECTOR_ORIGIN[None, :]) / SECTOR_LY).astype(np.int32)
    _PRED_SEC = (T["name"], (idx, sec, cell))
    return _PRED_SEC[1]


def adjacent_sector_targets(pos, T, mask, include_own=False):
    """The best ADJACENT sectors for predicted BH/WR, most predicted systems first.

    Ordered by HOW MANY still-available predicted systems the sector holds, which is
    how much uncatalogued space there is to hunt in once you get there. The expected
    number of rares -- sum(p_bh + p_wr), kept as `exp` -- is the obvious alternative
    ordering and is a narrower question: it can rank a sector with four good systems
    above one with forty, which is the right answer for a single trip and the wrong one
    for somewhere to spend an evening. Ties break on `exp`, then on distance.

    Each row's destination is the sector's BEST predicted system -- highest
    p_bh + p_wr. The nearest one was the obvious alternative and is a worse row: the
    closest system in a rich sector is usually a ~0% one, so the row would advertise a
    dud while claiming the sector is worth the trip. Once you arrive, the main target
    list takes over anyway, so the extra few hundred ly to the good system costs little.

    Returns EVERY qualifying sector in that order -- the caller slices it, so it can
    also say how many there were:
    [{sector, cell, hops, exp, exp_bh, exp_wr, n_sys, name, dist, p_bh, p_wr, p_hr}, ...].
    """
    idx, sec, cell = _predicted_sectors(T)
    if not len(idx):
        return []
    keep = mask[idx]
    if not keep.any():
        return []
    here = np.array(sector_cell(pos), dtype=np.int32)
    # Chebyshev distance 1 = the 26 surrounding cubes; 0 = the one you are standing in
    hops = np.abs(cell - here[None, :]).max(axis=1)
    sel = keep & (hops <= 1) & ((hops > 0) | bool(include_own)) & (sec != "")
    if not sel.any():
        return []
    p = np.asarray(pos, dtype=np.float64)
    rows = {}
    for k in np.flatnonzero(sel):
        i = int(idx[k])
        s = str(sec[k])
        d = float(np.linalg.norm(T["xyz"][i] - p))
        r = rows.get(s)
        if r is None:
            r = rows[s] = {"sector": s, "cell": tuple(int(v) for v in cell[k]),
                           "hops": int(hops[k]), "exp_bh": 0.0, "exp_wr": 0.0,
                           "n_sys": 0, "name": None, "dist": 0.0, "best": -1.0,
                           "p_bh": 0.0, "p_wr": 0.0, "p_hr": 0.0}
        pb, pw = float(T["p_bh"][i]), float(T["p_wr"][i])
        r["exp_bh"] += pb
        r["exp_wr"] += pw
        r["n_sys"] += 1
        # the sector's BEST system is the destination; ties go to the nearer one
        if (pb + pw > r["best"]) or (pb + pw == r["best"] and d < r["dist"]):
            r["best"] = pb + pw
            r["name"], r["dist"] = str(T["name"][i]), d
            r["p_bh"], r["p_wr"] = pb, pw       # its OWN odds, for the BH/WR columns
            r["p_hr"] = float(T["p_hr"][i]) if T.get("p_hr") is not None else 0.0
    for r in rows.values():
        r["exp"] = r["exp_bh"] + r["exp_wr"]    # expected rares; the tie-break
    return sorted(rows.values(), key=lambda r: (-r["n_sys"], -r["exp"], r["dist"]))


def available_mask(T, rule_out_floor=None, keep_secondary=False, predicted_only=False):
    """Routable targets.

    Excludes systems you have visited, systems tagged non-existent, and -- when
    `rule_out_floor` is given -- systems whose probability falls below it. 99% of
    black holes are the arrival star, so once Elite reveals a non-BH primary (which
    it does the moment you plot) the system is very close to disproved.

    `predicted_only` narrows the whole app to systems that appear in no catalogue at
    all. It is a mode rather than a filter on one table, because the two ways of
    hunting do not mix well in one list: catalogued systems usually carry better odds
    (they are in the spine, so their boxels are better sampled) and would crowd out
    the gaps, but a gap is the only target nobody else can be flying to, and the only
    one whose existence is still an open question. Switch on it, rather than trying to
    rank one against the other.

    A REVEALED ARRIVAL CLASS IS FINAL. If the game has told us the primary and it is
    not a black hole or Wolf-Rayet, the system is retired outright rather than scored
    down and left in the list. A black hole is the arrival star in 99.0% of systems
    that have one and a Wolf-Rayet in 94.1%, so the reveal settles it; what remains is
    a chance of a SECONDARY, which is not what this tool hunts. Comparing the
    class-conditional rate against `rule_out_floor` instead would keep every revealed
    Herbig Ae/Be forever -- class_rates puts an h-mass Ae/Be primary at 27% for a black
    hole somewhere in the system, above any sane floor -- so confirming a system was
    NOT a black hole would leave it at the top of the route. `keep_secondary=True`
    selects that scoring behaviour when a secondary is worth the trip.

    Two things are never dropped:
      * PREDICTED systems whose class is still UNKNOWN. These are inferred boxel gaps
        whose very existence is unconfirmed, and confirming them is the point.
      * Protected classes -- black hole and Wolf-Rayet primaries, and nothing else.

    A predicted system STOPS being exempt the moment Elite reveals its arrival class,
    because that reveal is exactly the ground truth the exemption was protecting: the
    system showed up in the galaxy map / NavRoute, so it demonstrably exists and the
    gap enumeration is already vindicated -- without flying there. Past that point it
    is an ordinary candidate, and a disproving primary retires it like any other.
    """
    n = len(T["name"])
    idx = _name_index(T)
    m = (T["source"] == "predicted").copy() if predicted_only else np.ones(n, dtype=bool)
    for nm in VISITED:
        i = idx.get(nm)
        if i is not None:
            m[i] = False
    for nm in WRONG:
        i = idx.get(nm)
        if i is not None:
            m[i] = False

    # a revealed non-target primary retires the system, floor or no floor
    p = (T["p_bh"] + T["p_wr"]).copy()
    keep = T["source"] == "predicted"
    for nm, cls in STARCLASS.items():
        i = idx.get(nm)
        if i is None or not m[i]:
            continue
        # the reveal proves the system exists, which is all the predicted-system
        # exemption was ever protecting -- so it ends here
        keep[i] = journal_class_key(cls) in PROTECTED_CLASSES
        if keep[i]:
            continue
        if not keep_secondary:
            m[i] = False        # confirmed not a BH/WR primary -> done with it
            continue
        b = class_bound(cls, str(T["mc"][i]))
        if b is not None:
            p[i] = b            # conservative: never below what the sample supports
    if not rule_out_floor:
        return m
    return m & (keep | (p >= rule_out_floor))


def effective_prob(T, i):
    """(p_bh, p_wr) for one candidate, conditioned on the arrival class if known.

    A known class is far more informative than the mass-code/radius prior -- it is
    close to deterministic -- so it replaces the prior outright rather than blending.
    """
    pr = class_prob(STARCLASS.get(T["name"][i]), str(T["mc"][i]))
    if pr is None:
        return float(T["p_bh"][i]), float(T["p_wr"][i])
    return pr



# ---------------------------------------------------------------- routing
def _tsp_path(pos, pts, time_budget):
    """Open TSP path from `pos` through every row of `pts`.

    Nearest-neighbour construction, then 2-opt refinement until no improving move
    remains or the time budget expires. Returns indices into `pts` in visit order.
    Node 0 of the internal path is your position and is never moved.
    """
    n = len(pts)
    if n <= 1:
        return list(range(n))

    # nodes: 0 = current position, 1..n = targets
    nodes = np.vstack([pos[None, :], pts])
    diff = nodes[:, None, :] - nodes[None, :, :]
    D = np.sqrt((diff * diff).sum(-1))

    # --- nearest-neighbour construction ---
    order = [0]
    unused = np.ones(n + 1, dtype=bool)
    unused[0] = False
    cur = 0
    for _ in range(n):
        d = np.where(unused, D[cur], np.inf)
        nxt = int(d.argmin())
        order.append(nxt)
        unused[nxt] = False
        cur = nxt
    path = np.array(order)

    # --- 2-opt with a virtual tail node (index n+1) at zero distance, so the path
    #     stays OPEN: reversing through the end costs nothing extra. ---
    Dv = np.zeros((n + 2, n + 2))
    Dv[: n + 1, : n + 1] = D
    deadline = time.monotonic() + time_budget
    m = len(path)                       # == n+1
    while time.monotonic() < deadline:
        A = np.concatenate([path, [n + 1]])
        i = np.arange(1, m)
        j = np.arange(1, m)
        I, J = np.meshgrid(i, j, indexing="ij")
        valid = I < J
        prev, cur_, jn, nxt = A[I - 1], A[I], A[J], A[J + 1]
        delta = Dv[prev, jn] + Dv[cur_, nxt] - Dv[prev, cur_] - Dv[jn, nxt]
        delta = np.where(valid, delta, 0.0)
        k = int(delta.argmin())
        if delta.flat[k] >= -1e-9:
            break                        # local optimum
        bi, bj = int(I.flat[k]), int(J.flat[k])
        path[bi:bj + 1] = path[bi:bj + 1][::-1]
    return [int(v) - 1 for v in path[1:]]   # drop position node, back to pts indices


def build_route(pos, T, mask, radius, want, time_budget, max_nodes=2000):
    """Route for the current position.

    All unvisited targets within `radius` are routed (that is the set the user asked
    to be optimised). If that yields fewer than `want` waypoints -- including the
    zero case -- the route is extended past the radius by nearest-neighbour so a full
    list is always produced.

    `max_nodes` bounds the TSP: 2-opt needs several O(n^2) arrays (~72 bytes/pair),
    so an unbounded set would exhaust memory (a 5,000 ly radius over mass codes efgh
    is ~45k targets => ~143 GB). When the in-radius set is larger, the NEAREST
    `max_nodes` are routed; since only `want` waypoints are displayed and the route is
    re-solved every jump, the shown legs are unaffected in practice.

    Returns (indices, n_in_radius, n_extended, n_truncated).
    """
    idx_all = np.flatnonzero(mask)
    if len(idx_all) == 0:
        return [], 0, 0, 0
    d_all = np.linalg.norm(T["xyz"][idx_all] - pos[None, :], axis=1)
    sel = d_all <= radius
    in_r, d_in = idx_all[sel], d_all[sel]

    n_truncated = 0
    if len(in_r) > max_nodes:
        keep = np.argpartition(d_in, max_nodes)[:max_nodes]
        n_truncated = len(in_r) - max_nodes
        in_r = in_r[keep]

    route = []
    if len(in_r) > 0:
        sub = _tsp_path(pos, T["xyz"][in_r], time_budget)
        route = [int(in_r[k]) for k in sub]
    n_in_radius = len(route)

    # extend beyond the radius if the in-radius set is short (covers the zero case)
    if len(route) < want:
        remaining = set(idx_all.tolist()) - set(route)
        cur = T["xyz"][route[-1]] if route else pos
        while remaining and len(route) < want:
            rem = np.fromiter(remaining, dtype=np.int64, count=len(remaining))
            d = np.linalg.norm(T["xyz"][rem] - cur[None, :], axis=1)
            pick = int(rem[int(d.argmin())])
            route.append(pick)
            remaining.discard(pick)
            cur = T["xyz"][pick]
    out = route[:want] if want else route
    return out, min(n_in_radius, len(out)), max(0, len(out) - n_in_radius), n_truncated


def rank_targets(pos, T, mask, radius, want):
    """The `want` BEST-ODDS targets anywhere inside `radius`.

    The radius is the whole selection: every candidate within it is ranked, and the top
    `want` are returned. It is deliberately not "the nearest `want`, reordered" -- that
    would let a cluster of poor systems a few hundred ly away hide the 47% mass-code-h
    system at the edge of the radius, which is exactly the target you set the radius to
    find. Distance only decides ties.

    Sort order:
      1. PREDICTED h-mass systems, as a block, above everything else.
      2. then probability, highest first;
      3. then PREDICTED over catalogued;
      4. then nearest.

    Rule 1 is a deliberate override of the odds, not a tie-break. A predicted h-mass
    system is the only row that is undiscovered on BOTH counts at once: mass code h is
    the sole Wolf-Rayet host and carries the best black-hole rate, and `predicted` means
    the name is in no catalogue at all -- not the EDSM/Spansh spine, not EDAstro -- so
    nobody can have been there ahead of you. A catalogued system at better odds is a
    system somebody may already be flying to; this one cannot be. It also settles
    whether the boxel gap exists, which is the only way the gap enumeration ever gets
    scored.

    Probabilities are the class-conditioned ones (`p_any`), so a system whose primary
    Elite has already revealed is ranked on what we now know, not on its mass-code prior.

    If fewer than `want` lie in radius, the nearest targets BEYOND it are appended as a
    second block, ranked among themselves. Note the asymmetry: inside the radius the best
    odds win regardless of distance, but the fill is chosen by PROXIMITY first, because
    outside the radius there is always a better-odds system somewhere and picking on odds
    alone would offer you a 47% target 40,000 ly away.

    Returns (indices, n_in_radius, n_extended, 0); the trailing 0 mirrors build_route's
    truncation count, which has no analogue here (ranking is O(n log n), not O(n^2)).
    """
    idx_all = np.flatnonzero(mask)
    if len(idx_all) == 0:
        return [], 0, 0, 0
    d_all = np.linalg.norm(T["xyz"][idx_all] - pos[None, :], axis=1)
    p_all = p_any(T)[idx_all]
    pred_all = (T["source"][idx_all] == "predicted").astype(np.int8)
    # the top block: undiscovered on both counts at once
    predh_all = (pred_all & (T["mc"][idx_all] == "h")).astype(np.int8)

    def block(sel, n, nearest_first=False):
        """The best `n` rows of `sel`: predicted-h, then p desc, then pred, then nearer.

        `nearest_first` narrows to the `n` closest BEFORE ranking -- used only for the
        out-of-radius fill, where proximity has to bound the candidate set.
        """
        if n <= 0:
            return []
        pick = np.flatnonzero(sel)
        if len(pick) == 0:
            return []
        if nearest_first and len(pick) > n:
            pick = pick[np.argpartition(d_all[pick], n)[:n]]
        # np.lexsort takes the PRIMARY key LAST, so predh is the outermost sort
        order = np.lexsort((d_all[pick], -pred_all[pick], -p_all[pick],
                            -predh_all[pick]))[:n]
        return [int(idx_all[pick[k]]) for k in order]

    inside = d_all <= radius
    out = block(inside, want)
    n_in_radius = len(out)
    if n_in_radius < want:
        out += block(~inside, want - n_in_radius, nearest_first=True)
    return out, n_in_radius, len(out) - n_in_radius, 0


def select_targets(pos, T, mask, radius, want, time_budget, max_nodes=2000, sort="prob"):
    """Dispatch to the ranked list or the shortest-path route."""
    if sort == "route":
        return build_route(pos, T, mask, radius, want, time_budget, max_nodes)
    return rank_targets(pos, T, mask, radius, want)


# ---------------------------------------------------------------- display
def show_route(system, pos, T, args):
    t0 = time.monotonic()
    # before ranking, not after: routing is done on these coordinates
    apply_starpos(T)
    mask = available_mask(T, args.rule_out_below, args.keep_secondary,
                          args.predicted_only)
    route, n_in_radius, n_ext, n_trunc = select_targets(
        pos, T, mask, args.radius, args.topn, args.route_ms / 1000.0, args.max_nodes,
        sort=args.sort)
    elapsed = time.monotonic() - t0

    total_in_radius = int((np.linalg.norm(T["xyz"][mask] - pos[None, :], axis=1) <= args.radius).sum())
    rid, rname, votes, rdist = region_of(pos)
    n_region = region_target_count(T, mask, rid)

    print("\n" + "=" * 86)
    print(f"  @ {system}   ({pos[0]:.0f}, {pos[1]:.0f}, {pos[2]:.0f})")
    if rname:
        conf = "" if votes >= 5 else f"  [{votes}/5 vote, nearest label {rdist:,.0f} ly]"
        print(f"  region: {rname}   |  {n_region:,} routable target(s) in region{conf}")
    mode = "PREDICTED ONLY" if args.predicted_only else "predicted + catalogued"
    print(f"  {total_in_radius:,} unvisited target(s) within {args.radius:,.0f} ly"
          f"   |  {mode}   |  routed in {elapsed*1000:.0f} ms")
    print("=" * 86)

    if not route:
        print("\n  No unvisited targets remain. Nothing to route.")
        return

    if total_in_radius == 0:
        print(f"\n  ! Nothing within {args.radius:,.0f} ly -- routing to the nearest target,"
              f" then the next {max(0, len(route)-1)}.")
    elif n_ext:
        print(f"\n  ! Only {n_in_radius} target(s) in radius -- {n_ext} further waypoint(s)"
              f" added beyond it (marked +).")
    if n_trunc:
        print(f"  ! {n_trunc:,} in-radius target(s) beyond --max-nodes={args.max_nodes:,}"
              f" excluded from the solve (nearest {args.max_nodes:,} routed).")

    nav = read_navroute(args.journal_dir)
    if nav:
        prog = navroute_progress(nav, system, pos)
        if prog:
            i, tot, rem = prog
            nxt = str(T["name"][route[0]]) if route else None
            if system == nav["destination"]:
                print(f"  plotted route: ARRIVED at {nav['destination']}  ->  next: {nxt}")
            else:
                off = "" if nxt == nav["destination"] else "   (OFF-ROUTE)"
                print(f"  plotted route: {i}/{tot} jumps -> {nav['destination']}"
                      f"   {rem:,.0f} ly remaining{off}")

    # ranked rows are not a path, so a leg from the previous row would be meaningless:
    # show the distance from YOU instead, and drop the cumulative column
    ranked = args.sort != "route"
    NW = 29
    print(f"\n  {'#':>2}" + star_header(NW, extra="" if ranked else f"{'cum':>10}"))
    prev = pos
    cum = 0.0
    for i, gi in enumerate(route, 1):
        p = T["xyz"][gi]
        if ranked:
            d, extra = float(np.linalg.norm(p - pos)), ""
        else:
            d = float(np.linalg.norm(p - prev))
            cum += d
            extra = f"{cum:>10,.0f}"
        print(f"  {i:>2}" + star_row_at(T, gi, d, ext=i > n_in_radius,
                                        name_w=NW, extra=extra))
        prev = p

    # re-folded every jump: a reveal can land at any time, and arriving at one of
    # these is what flips it to visited
    if sync_confirmed(T):
        save_confirmed_store()
    for nm, kind in drain_new_confirmed():
        alert(kind)
        print(f"\n  *** {kind} DETECTED: {nm}   ({STARCLASS.get(nm)}) ***")
    log_observations(T)          # a reveal can land on any jump
    po = args.predicted_only
    todo = pending_confirmed(pos, po)[:args.found_n] if args.found_n else []
    if todo:
        print(f"\n  ** CONFIRMED BH/WR, not yet visited -- Pred first, then nearest "
              f"({len(pending_confirmed(None, po)):,} outstanding, any range) --")
        print("   " + star_header(NW))
        for name, rec, d in todo:
            print("   " + star_row_confirmed(name, rec, d, name_w=NW))

    if args.neutron_n:
        # aimed at the top-ranked target, so the supercharge advances the trip
        tgt = T["xyz"][route[0]] if route else None
        ns = nearest_neutron(pos, args.neutron_n, target=tgt)
        if ns:
            toward = f" toward {str(T['name'][route[0]])[:26]}" if tgt is not None else ""
            print(f"\n  -- confirmed neutron star(s) (FSD supercharge){toward} --")
            print("   " + star_header(NW))
            # a scanned, catalogued neutron star: no BH/WR odds to offer and never a
            # prediction, but Conf carries its class so it reads like every other row
            for nm, dist in ns:
                print("   " + star_row(nm, dist, 0.0, 0.0, predicted=False,
                                       conf="N", name_w=NW))

    C = load_carriers()
    if C and args.carrier_n:
        picks = nearest_carriers(pos, args.carrier_n, require_uc=True)
        if args.carrier_dssa and not any(C["is_dssa"][i] for i, _d in picks):
            picks += nearest_carriers(pos, 1, require_uc=True, dssa_only=True)
        if picks:
            print("\n  -- nearest Universal Cartographics carrier(s) --")
            print(f"     {'system':30}{'dist_ly':>10}  carrier")
            for i, dist in picks:
                tag = " [DSSA]" if C["is_dssa"][i] else ""
                nm = str(C["name"][i]) or str(C["callsign"][i])
                print(f"     {str(C['system'][i])[:29]:29s}{dist:>10,.0f}  "
                      f"{C['callsign'][i]} {nm[:22]}{tag}  moved {str(C['last_moved'][i])[:10]}")

    # nothing is written to the clipboard unless --copy-next is given: it is a shared
    # resource and the router re-solves on every jump, so it would clobber whatever you
    # had there at unpredictable moments
    nxt = str(T["name"][route[0]])
    if args.copy_next:
        ok = copy_to_clipboard(nxt)
        print(f"\n  next hop -> clipboard: {nxt}" if ok
              else f"\n  next hop: {nxt}   (clipboard copy failed)")
    else:
        print(f"\n  next hop: {nxt}")
    print("  probabilities are de-biased estimates; scan in-game to confirm.")
    print("  * PREDICTED = inferred boxel gap; likely-real but unconfirmed, coords approximate.")


# ---------------------------------------------------------------- journal
# ------------------------------------------------------- game session / throughput
# How long the GAME has been up, not how long this app has. They differ by however
# long the overlay was left running between sessions, which would silently deflate any
# per-hour rate computed against the app's own clock.
GAME_EXE = "EliteDangerous64.exe"
_PROC_CACHE = (0.0, None)      # (monotonic when probed, (pid, started_utc) or None)
_PROC_TTL = 15.0               # a process scan is ~300 OpenProcess calls; not per tick


def _process_start_utc(exe_name):
    """(pid, start time UTC) for a running process by exe name, or None.

    GetProcessTimes returns a FILETIME -- 100ns ticks since 1601-01-01 UTC -- so this
    is UTC with no local-time step, which matters because journal timestamps are UTC
    and converting through local time would break twice a year.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None
    try:
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class FILETIME(ctypes.Structure):
            _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]

        n = 1024
        while True:
            arr = (wintypes.DWORD * n)()
            need = wintypes.DWORD()
            if not psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr),
                                       ctypes.byref(need)):
                return None
            if need.value < ctypes.sizeof(arr):
                pids = list(arr[: need.value // ctypes.sizeof(wintypes.DWORD)])
                break
            n *= 2
        want = exe_name.lower()
        for pid in pids:
            h = k32.OpenProcess(0x1000, False, pid)   # QUERY_LIMITED_INFORMATION
            if not h:
                continue                              # a process we may not inspect
            try:
                buf = ctypes.create_unicode_buffer(32768)
                size = wintypes.DWORD(len(buf))
                if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    continue
                if buf.value.rsplit("\\", 1)[-1].lower() != want:
                    continue
                c, e_, kt, ut = FILETIME(), FILETIME(), FILETIME(), FILETIME()
                if not k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e_),
                                           ctypes.byref(kt), ctypes.byref(ut)):
                    continue
                ticks = (c.hi << 32) | c.lo
                return pid, (datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc)
                             + datetime.timedelta(microseconds=ticks / 10))
            finally:
                k32.CloseHandle(h)
    except Exception:
        return None                                   # never let this break the HUD
    return None


def game_session(force=False):
    """(pid, started_utc) for the running game, or None if it is not up.

    Cached for _PROC_TTL: the answer only changes when the game starts or stops, and
    the scan is far too heavy for a 2-second render tick.
    """
    global _PROC_CACHE
    now = time.monotonic()
    if not force and now - _PROC_CACHE[0] < _PROC_TTL:
        return _PROC_CACHE[1]
    _PROC_CACHE = (now, _process_start_utc(GAME_EXE))
    return _PROC_CACHE[1]


def game_uptime_s():
    """Seconds the game has been running, or None if it is not."""
    s = game_session()
    if not s:
        return None
    return max(0.0, (datetime.datetime.now(datetime.timezone.utc) - s[1]).total_seconds())


def jumps_since(journal_dir, since_utc):
    """Systems arrived at with a timestamp at or after `since_utc`.

    Returns (arrivals, distinct_systems). Reads only journals modified since that
    time -- a session's arrivals cannot be recorded in a file last written before it
    started, so the other 150+ files are skipped on their mtime alone.
    """
    if since_utc is None:
        return 0, 0
    cutoff = since_utc.timestamp() - 60.0        # a minute of slack for clock skew
    arrivals, seen = 0, set()
    stamp = since_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    for path in glob.glob(os.path.join(journal_dir, "Journal.*.log")):
        try:
            if os.path.getmtime(path) < cutoff:
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if '"StarPos"' not in line:
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    # ISO-8601 UTC with a fixed width, so a string compare orders the
                    # same as a parsed one -- and skips ~thousands of datetime parses
                    if (e.get("event") in POS_EVENTS and e.get("StarSystem")
                            and (e.get("timestamp") or "") >= stamp):
                        arrivals += 1
                        seen.add(e["StarSystem"])
        except OSError:
            continue
    return arrivals, len(seen)


def latest_journal(jdir):
    files = glob.glob(os.path.join(jdir, "Journal.*.log"))
    return max(files, key=os.path.getmtime) if files else None


def last_position(path):
    sysname, pos = None, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if e.get("event") in POS_EVENTS and "StarPos" in e:
                    sysname, pos = e.get("StarSystem"), e["StarPos"]
    except FileNotFoundError:
        pass
    return sysname, pos


def watch(jdir, T, args):
    print(f"watching journals in: {jdir}")
    path = latest_journal(jdir)
    if not path:
        print("No Journal.*.log found. Is Elite Dangerous installed / has it run?")
        return
    sysname, pos = last_position(path)
    if pos:
        show_route(sysname, np.array(pos, dtype=np.float64), T, args)
    else:
        print("waiting for a jump / location event...")
    f = open(path, "r", encoding="utf-8")
    f.seek(0, os.SEEK_END)
    try:
        while True:
            line = f.readline()
            if not line:
                newp = latest_journal(jdir)          # session rolled to a new file?
                if newp and newp != path:
                    path = newp
                    f.close()
                    f = open(path, "r", encoding="utf-8")
                time.sleep(1)
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("event") in POS_EVENTS and "StarPos" in e:
                name = e.get("StarSystem")
                if name and name not in VISITED:
                    VISITED.add(name)
                    save_visited_store()             # retire it permanently
                show_route(name, np.array(e["StarPos"], dtype=np.float64), T, args)
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        f.close()


def main():
    ap = argparse.ArgumentParser(description="Route through nearby undiscovered BH/WR candidates.")
    ap.add_argument("--pos", nargs=3, type=float, metavar=("X", "Y", "Z"))
    ap.add_argument("--radius", type=float, default=1000.0, help="target search radius in ly (default 1000)")
    ap.add_argument("--no-sound", dest="sound", action="store_false",
                    help="do not play a tone when a BH/WR is revealed by a route plot")
    ap.add_argument("--alert-sound", default=None, metavar="WAV",
                    help="play this .wav instead of the built-in tones")
    ap.add_argument("--keep-secondary", action="store_true",
                    help="keep systems whose revealed primary is NOT a BH/WR, scored on the "
                         "chance of a secondary one. Off by default: the primary is the find "
                         "in 99%% of black holes and 94%% of Wolf-Rayets.")
    ap.add_argument("--found-n", type=int, default=10,
                    help="rows in the confirmed-but-unvisited BH/WR table (default 10; 0 = off). "
                         "The store itself is never truncated.")
    ap.add_argument("--predicted-only", action="store_true",
                    help="hunt ONLY systems that appear in no catalogue at all. Narrows "
                         "both the route list and the confirmed table; the overlay "
                         "toggles this live.")
    ap.add_argument("--rule-out-below", type=float, default=0.0005,
                    help="drop candidates whose CONFIDENCE-BOUNDED P(BH or WR) is below this "
                         "fraction (default 0.0005 = 0.05%%). The bound is max(observed, 3/n), so "
                         "a zero from a thin sample is not treated as a real zero. PREDICTED "
                         "systems and revealed BH/WR primaries are never dropped. 0 disables.")
    ap.add_argument("--topn", type=int, default=12, help="waypoints to display (default 12)")
    ap.add_argument("--sort", choices=("prob", "route"), default="prob",
                    help="'prob' (default): the nearest --topn targets in radius, best odds "
                         "first, ties to PREDICTED then to the nearer system. 'route': the "
                         "shortest path through them (leg/cum columns).")
    ap.add_argument("--bh-codes", default="fgh", help="mass codes treated as black-hole targets (default fgh)")
    ap.add_argument("--route-ms", type=int, default=400, help="2-opt refinement budget in ms (default 400)")
    ap.add_argument("--max-nodes", type=int, default=2000,
                    help="max targets fed to the TSP; nearest-first (default 2000). "
                         "2-opt is O(n^2) in memory, so raising this costs ~72 bytes per pair.")
    ap.add_argument("--neutron-n", type=int, default=1,
                    help="nearest confirmed neutron stars to show (default 1; 0 = off)")
    ap.add_argument("--carrier-n", type=int, default=1,
                    help="nearest Universal Cartographics carriers to show (default 1; 0 = off)")
    ap.add_argument("--no-carrier-dssa", dest="carrier_dssa", action="store_false",
                    help="do not always append the nearest DSSA carrier")
    ap.add_argument("--carrier-gone", metavar="CALLSIGN", action="append", default=[],
                    help="tag a carrier as no longer at its recorded system, so it is "
                         "never suggested again and the next-nearest takes its place. "
                         "Repeatable.")
    ap.add_argument("--carrier-back", metavar="CALLSIGN", action="append", default=[],
                    help="untag a carrier tagged with --carrier-gone. Repeatable.")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--journal-dir", default=DEFAULT_JOURNAL_DIR)
    ap.add_argument("--include-visited", action="store_true", help="do NOT hide systems you've already visited")
    ap.add_argument("--include-wrong", action="store_true",
                    help="do NOT hide systems tagged non-existent in wrong.json")
    ap.add_argument("--wrong", metavar="SYSTEM", action="append",
                    help="tag a system as non-existent and exit (repeatable)")
    ap.add_argument("--calibration", action="store_true",
                    help="score predicted probability against what you actually found, and exit")
    ap.add_argument("--copy-next", action="store_true",
                    help="copy the next hop to the clipboard. Off by default -- the "
                         "clipboard is left alone unless you ask for it.")
    a = ap.parse_args()

    if a.wrong:
        load_wrong_store()
        for name in a.wrong:
            mark_wrong(name)
            print(f"tagged non-existent: {name}")
        print(f"wrong.json now holds {len(WRONG):,} system(s) -> {WRONG_STORE}")
        return

    if a.carrier_gone or a.carrier_back:
        load_carrier_gone_store()
        C = load_carriers()
        by_cs = {str(c).upper(): j for j, c in enumerate(C.get("callsign", []))}
        for cs in a.carrier_gone:
            key = cs.strip().upper()
            where = (f" (was {C['system'][by_cs[key]]})" if key in by_cs else
                     "  [WARNING: no carrier with that callsign in carriers.parquet]")
            print(f"{'tagged gone' if mark_carrier_gone(key) else 'already tagged'}: "
                  f"{key}{where}")
        for cs in a.carrier_back:
            key = cs.strip().upper()
            print(f"{'untagged' if unmark_carrier_gone(key) else 'was not tagged'}: {key}")
        print(f"carrier_gone.json now holds {len(CARRIER_GONE):,} carrier(s) "
              f"-> {CARRIER_GONE_STORE}")
        return

    if a.calibration:
        print("harvesting outcomes from journals...", flush=True)
        outcomes = scan_outcomes(a.journal_dir)
        save_outcomes(outcomes)
        v = {}
        for r in outcomes.values():
            v[r["verdict"]] = v.get(r["verdict"], 0) + 1
        print(f"systems with exploration data: {len(outcomes):,}   "
              f"resolved={v.get('hit',0)+v.get('miss',0):,} "
              f"(hit={v.get('hit',0):,} miss={v.get('miss',0):,})  partial={v.get('partial',0):,}")

        T = load_targets("efgh")          # score every mass code we ever predict for
        rows = calibration(T, outcomes)
        if not rows:
            print("\nNo resolved system in your journals was a candidate in our snapshot,")
            print("so there is nothing to score yet. Keep flying -- this fills up as you honk")
            print("systems the community had never scanned.")
            return

        hits = sum(1 for *_x, h, _b, _s in rows if h)
        mean_p = sum(r[2] for r in rows) / len(rows)
        print(f"\n=== CALIBRATION over {len(rows):,} resolved candidate system(s) ===")
        print(f"  predicted (mean p): {mean_p:6.1%}")
        print(f"  observed  (hits)  : {hits/len(rows):6.1%}   ({hits:,}/{len(rows):,})")

        print(f"\n  {'predicted band':>16}{'n':>7}{'expected':>10}{'observed':>10}")
        bands = [(0.0, .05), (.05, .10), (.10, .20), (.20, .35), (.35, .50), (.50, 1.01)]
        for lo, hi in bands:
            sub = [r for r in rows if lo <= r[2] < hi]
            if not sub:
                continue
            exp = sum(r[2] for r in sub) / len(sub)
            obs = sum(1 for r in sub if r[3]) / len(sub)
            print(f"  {lo:6.0%}-{hi:<6.0%}{len(sub):>7,}{exp:>10.1%}{obs:>10.1%}")

        print(f"\n  {'by mass code':>16}{'n':>7}{'expected':>10}{'observed':>10}")
        for mc in ("e", "f", "g", "h"):
            sub = [r for r in rows if r[1] == mc]
            if not sub:
                continue
            exp = sum(r[2] for r in sub) / len(sub)
            obs = sum(1 for r in sub if r[3]) / len(sub)
            print(f"  {mc:>16}{len(sub):>7,}{exp:>10.1%}{obs:>10.1%}")

        hit_rows = [r for r in rows if r[3]]
        if hit_rows:
            print(f"\n  HITS ({len(hit_rows)}):")
            for n, mc, p, _h, bc, st in hit_rows[:20]:
                print(f"    {n[:34]:34s} mc={mc} p={p:5.0%} bodies={bc} stars={st}")
        print(f"\n  outcomes written to {OUTCOMES_STORE}")
        print("  NOTE: 'partial' systems are excluded -- scoring a half-explored system")
        print("  as a miss would bias the observed rate downward.")
        return

    if not a.include_visited:
        nj = load_visited_from_journals(a.journal_dir)
        ns = load_visited_store()
        print(f"visited: {nj:,} from journals + {ns:,} remembered = {len(VISITED):,} systems hidden")
        save_visited_store()
    if not a.include_wrong:
        nw = load_wrong_store()
        if nw:
            print(f"wrong: {nw:,} system(s) tagged non-existent, excluded from routing")
    global SOUND_ENABLED, SOUND_FILE
    SOUND_ENABLED, SOUND_FILE = a.sound, a.alert_sound

    load_starclass_store()
    load_starpos_store()
    ng = load_carrier_gone_store()
    if ng:
        print(f"carriers: {ng:,} tagged gone, excluded from suggestions")
    nc = harvest_starclass_from_journals(a.journal_dir)
    read_navroute(a.journal_dir)          # the plotted route reveals classes too
    save_starclass_store()
    conf = [n for n, c in STARCLASS.items() if classify_star(c)]
    print(f"star classes known: {len(STARCLASS):,} (+{nc:,} new from journals); "
          f"{len(conf):,} confirmed black-hole / Wolf-Rayet primaries")

    T = load_targets(a.bh_codes)
    print(f"targets loaded: {len(T['name']):,} candidates (BH codes: {a.bh_codes}, WR: h)")
    # A confirmed primary you have not been to is the best thing this tool can find:
    # a guaranteed black hole / Wolf-Rayet that nobody has catalogued yet. Recorded
    # permanently, because you will rarely be able to divert there when it turns up.
    load_confirmed_store()
    if sync_confirmed(T):
        save_confirmed_store()
    todo = pending_confirmed()
    print(f"confirmed BH/WR primaries: {len(CONFIRMED):,} recorded, "
          f"{len(todo):,} not yet visited -> {CONFIRMED_STORE.name}")

    load_observations()
    nobs = log_observations(T)
    print(f"calibration: model {model_version()}, {len(_OBS_SEEN):,} logged outcome(s)"
          + (f" (+{nobs:,} new)" if nobs else "")
          + f" -> {OBSERVATIONS.name}")

    if a.pos:
        show_route("(manual position)", np.array(a.pos, dtype=np.float64), T, a)
    elif a.once:
        p = latest_journal(a.journal_dir)
        if not p:
            sys.exit("no journal found")
        s, pos = last_position(p)
        if not pos:
            sys.exit("no position event in latest journal yet")
        show_route(s, np.array(pos, dtype=np.float64), T, a)
    else:
        watch(a.journal_dir, T, a)


if __name__ == "__main__":
    main()
