"""All database access for the overlay. The ONLY module here containing SQL.

Two databases, and the split is a rule rather than a convention:

    elite_mapping_v2_current.duckdb   WRITTEN. Everything the app records.
    elite_mapping_v2.duckdb           READ ONLY. The model: what the galaxy is.

The model is attached `READ_ONLY` by `common.current.attach_model()`, so an accidental
write raises instead of landing. The full rationale is in ETL.md §0; the short version
is that the model is derived and fully rebuilt by `etl/`, so anything the app wrote
there would be erased by the next merge with nothing to show it had gone.

*** NO JSON. *** A JSON-backed store means rewriting whole files on every
change. Every one of them is a table now, and every write below is an idempotent
`INSERT ... WHERE NOT EXISTS`, so a replayed journal event cannot double-count.

*** SELECTION AND LABELLING ARE SQL; NUMBER FORMATTING IS NOT. *** Which rows appear,
in what order, with what F-key and what "Mass H" type label -- all decided by the query.
But the eight probabilities come out as RAW DOUBLES and `table.py` formats them, because
a number is useful to more than one caller (the sub-0.05 dash, colour, a future re-sort)
while a pre-formatted string is useful only to the widget that prints it. The app
displays and it tracks; it does not decide what is worth showing.

Connections are SHORT-LIVED: DuckDB allows one process to hold a file, so an overlay
that kept the app-state database open would lock out every loader and every read. See
the Store docstring.
"""
import contextlib
import datetime
import pathlib
import sys
import time

import duckdb

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.current import CURRENT_DB, MODEL_DB, resolve_known, sector_sql

# What "best" means when ranking systems. THE ONLY SUCH EXPRESSION -- the Current
# sector table orders its ten rows by it, and the Adjacent sectors table picks each
# sector's destination by it, so the two can never recommend different places.
#
# *** NOT a combined probability. *** An earlier version ranked on
# `1 - (1-p_bh)*(1-p_wr)`, which the model's own documentation forbids: the p_wr column
# comment reads "Competes with p_bh for the same primary star -- one star cannot be
# both, so never add or multiply them." Independence is the wrong assumption and
# addition is the wrong one too, so the honest summary of a pair of mutually exclusive
# outcomes is simply the larger of the two.
#
# Only BH and WR enter the ranking, not all eight predictions. They are the RARE ones:
# neutrons and white dwarfs sit near their base rate in almost every system, so
# including them would rank by "how ordinary is this system" and swamp the signal.
# The other six are still shown -- they are just not what sorts the list.
RANK_BY = "greatest(p.p_bh, p.p_wr)"

# WHICH PREDICTIONS COUNT AS "RARE" for the visibility threshold below.
#
# Neutron and white dwarf are deliberately EXCLUDED even though both are displayed.
# The model calls neutrons "common enough that they are rarely worth routing for on
# their own", and both sit near their base rate almost everywhere -- p_neutron alone is
# 0.17 in ordinary f-mass space, so including them would pass essentially every system
# and the threshold would filter nothing at all.
#
# p_hr (helium-rich gas giant) is excluded as well: it is a PLANET class, and it is
# hard-gated to 0 for mass code h and inside 5.5 kly of the core, so it is absent
# exactly where the rare STARS are.
RARE_COLUMNS = ("p_bh", "p_wr", "p_herbig", "p_supergiant", "p_otype")

# A system must offer at least this much on at least ONE rare prediction to be shown.
# Applied per-column, never to a total: these are mutually exclusive outcomes for the
# same primary star and must not be summed (see RANK_BY).
#
# *** 0.01, NOT 0.05, AND THE TWO ARE DIFFERENT QUESTIONS. *** 0.05 was chosen as
# "worth flying to" and used as "worth showing", which are not the same bar. At 0.05
# the whole of mass code e is invisible -- its p_bh is 0.0544 inside 10 kly and 0.0236
# at 10-20k, so the core band scraped over and everything outside it vanished --
# and so is any sector whose best row is a long shot. A HUD that shows nothing cannot
# distinguish "this sector is picked over" from "this sector is below my threshold",
# and those call for opposite decisions.
#
# The odds are still on screen, in the number and in its gradient colour, so a 0.02
# row advertises itself as a 0.02 row. Deciding is the commander's job; this decides
# only what is worth a line of the display.
MIN_RARE = 0.01

# How many of the ten rows a sector's points of interest may take before predictions
# get the rest. A cap is needed in both directions: Blaa Hypai holds 20 POI systems and
# would fill the table on its own, while a sector with none must not waste slots.
# Three is a judgement call, not a derived number -- change it here.
MAX_POI_ROWS = 3

# NO PER-ROW KEY. Rows used to carry an `fkey` label ('[CTRL+F3]') built here so the
# text on screen and the chord registered came from one place. Four navigation keys
# replaced 33 chords, so a row is now reached by moving a cursor onto it and there is
# nothing per-row left to label.

# Row kinds, in the order they claim slots. The value is also the sort key.
#   poi        a CERTAIN find. The game credits a Lagrange cloud or a green giant to
#              YOU however many commanders logged it first, so a POI is never "taken".
#   predicted  boxel-predicted: in no dump at all, inferred from a gap in the Stellar
#              Forge index. The real target list, but only 61,763 exist galaxy-wide.
#   catalog    BACKFILL ONLY, and rendered in a different colour. Catalogued means the
#              system is in the dumps with exact coordinates and merely unscanned --
#              still worth flying to, but not a prediction, and the distinction must
#              stay visible rather than being quietly blended in.
ROW_CONFIRMED, ROW_POI, ROW_PREDICTED, ROW_CATALOG = -1, 0, 1, 2
# The totals row. Not a target and never gets an F-key -- you cannot fly to a sum.
ROW_TOTAL = 3
# A parked fleet carrier. Carries NO predictions at all -- it is a place to dock, not a
# system to gamble on -- so its row shows the carrier's name across the whole
# prediction area instead of eight dashes.
ROW_CARRIER = 4
# A whole SECTOR, summed. Like ROW_TOTAL its numbers are expected COUNTS rather than
# probabilities -- but unlike ROW_TOTAL it IS a destination, because it carries the best
# system in that sector as `copy_text`. That is the only reason the two are separate
# kinds: everything about how they render is identical.
ROW_SECTOR = 5
# A neutron star: a JET CONE BOOST, not a target. Shares the carrier table because both
# answer "somewhere to go that is not a gamble" -- and like a carrier it carries no
# predictions, so its wide area is blank rather than eight dashes.
ROW_NEUTRON = 6
# The CATALOGUED half of a summary pair. Everything about it behaves like ROW_TOTAL --
# expected counts, off the gradient, not a destination -- and it exists purely so the
# renderer can tint it the same blue-grey as the catalogued backfill ROWS it is summing.
# That is the whole point of the pair: the line and the rows it counts should be
# findable as the same population at a glance, without reading either.
ROW_TOTAL_CATALOG = 7
# A REAL CATALOGUED STAR (main.system_unfound) whose position falls in this sector and
# which no game system can be matched to. Carries NO predictions -- like a carrier it
# uses `wide_text`, because the useful thing is where to fly and how far the last hop
# is, not eight probabilities about a star we cannot even confirm exists.
#
# *** IT ASKS A DIFFERENT QUESTION FROM EVERY OTHER ROW ON THIS TABLE. *** The others
# ask what is IN a system the game certainly has; this asks whether the system is there
# at all. That is why it is its own kind rather than a flag on a prediction: the answer
# is a visit, not a scan, and the two must never be read as the same claim.
ROW_UNFOUND = 8


# ------------------------------------------------------------ probability columns
# (source column, output name) for the eight predictions, in display order. ONE list,
# so the SELECT and the renderer cannot disagree about which column is which.
#
# These leave SQL as RAW DOUBLES. Formatting -- two decimals, and a dash below
# MIN_RARE -- belongs to table.py, because a number is useful to more than one caller
# (thresholds, colour, a future re-sort) while a pre-formatted string is useful only to
# the widget that prints it.
DISPLAY_P = [
    ("p_bh",         "p_bh"),
    ("p_wr",         "p_wr"),
    ("p_herbig",     "p_herbig"),
    ("p_supergiant", "p_supg"),
    ("p_otype",      "p_otype"),
    ("p_neutron",    "p_neutron"),
    ("p_wd",         "p_wd"),
    ("p_hr",         "p_hegg"),
]


# The eight as a SELECT fragment, and as typed NULLs for rows that carry no
# probabilities at all -- a confirmed find is a certainty, and a POI is not a star.
P_COLUMNS = ", ".join(f"{c} AS {a}" if c != a else c for c, a in DISPLAY_P)
P_NULLS = ", ".join(f"NULL::DOUBLE AS {a}" for _c, a in DISPLAY_P)


# ---------------------------------------------------------------- confirmed finds
# Arrival classes that mean the game has ALREADY TOLD US a rare object is there.
# Plotting a route reveals the arrival star of every hop, so a system can be a certain
# find long before anyone flies to it -- that is the whole edge this tool has.
#
# The keys mirror the displayed rare columns, so "confirmed" and "predicted" mean the
# same set of objects. Elite reports no distinct supergiant arrival class, so SUPG has
# no entry here and can only ever be a prediction.
# ORDERED BY RARITY, best first -- the dict order IS the Confirmed table's sort order,
# so a black hole always outranks a white dwarf for an F-key. Labels match the column
# headings, so "what the table predicts" and "what a route plot can confirm" read as
# one vocabulary.
#
# Every prediction we display can be confirmed here EXCEPT He GIANT: a helium-rich gas
# giant is a planet, and a route plot only ever reveals the ARRIVAL STAR.
#
# Both spellings of the supermassive black hole are listed on purpose. The journal
# writes "SupermassiveBlackHole" and the model's body table writes
# "SuperMassiveBlackHole" -- one capital apart, and matching only one of them would
# silently drop Sagittarius A*.
# kind -> (the prediction column it confirms, the arrival classes that mean it)
#
# The column is named here so a confirmed row can put a CHECKMARK in the very column
# that would otherwise hold a probability. That is the whole point: the same column
# reads "0.40, we think" on a prediction and "yes, definitely" on a confirmation.
CONFIRMED_CLASSES = {
    "BH":       ("p_bh", ("H", "SupermassiveBlackHole", "SuperMassiveBlackHole")),
    "WR":       ("p_wr", ("W", "WN", "WNC", "WC", "WO")),
    "SUPERGNT": ("p_supg", ("A_BlueWhiteSuperGiant", "B_BlueWhiteSuperGiant",
                            "F_WhiteSuperGiant", "G_WhiteSuperGiant",
                            "M_RedSuperGiant")),
    "HERBIG":   ("p_herbig", ("AeBe",)),
    "O-TYPE":   ("p_otype", ("O",)),
    "NEUTRON":  ("p_neutron", ("N",)),
    "WHT DWRF": ("p_wd", ("D", "DA", "DAB", "DAO", "DAV", "DAZ", "DB", "DBV", "DBZ",
                          "DC", "DCV", "DO", "DOV", "DQ", "DX")),
}

# Flat set of every arrival class that confirms something we predict.
RARE_CLASSES = {c for _col, v in CONFIRMED_CLASSES.values() for c in v}

# SQL: star_class -> label, and the membership test. Built from the one dict above.
_CLASS_CASE = " ".join(
    f"WHEN star_class IN ({', '.join(repr(c) for c in v)}) THEN '{k}'"
    for k, (_col, v) in CONFIRMED_CLASSES.items())
_ALL_CLASSES = ", ".join(repr(c) for c in sorted(RARE_CLASSES))
# kind -> the column its checkmark belongs in, emitted with each confirmed row so the
# renderer never has to know what a star class is.
_CONFIRMED_COL_CASE = " ".join(
    f"WHEN kind = '{k}' THEN {col!r}" for k, (col, _v) in CONFIRMED_CLASSES.items())

# The kinds numerous enough to crowd the Confirmed table out.
#
# *** EXPLICIT, and deliberately NOT derived from RARE_COLUMNS. *** An earlier version
# derived it, on the reasoning that "common" should mean the same thing everywhere. It
# does not: RARE_COLUMNS answers "is this prediction worth showing a system for", while
# this answers "would this kind swamp a ten-row list sorted by distance". Those are
# different questions that happened to give the same answer until O-TYPE needed capping
# -- p_otype is unambiguously a rare prediction AND the second most numerous confirmed
# kind. Deriving one from the other only looked tidy.
#
# Grounded in the confirmed population, which is what actually competes for the slots:
#
#     NEUTRON   1,041      O-TYPE  301      BH   70      SUPERGNT  0
#     HERBIG      122      WHT DWRF 50      WR   32
#
# HERBIG at 122 is the next candidate and is deliberately left uncapped for now: it
# already outnumbers black holes, so if the list starts filling with Herbigs this is
# the line to change.
CAPPED_KINDS = ("NEUTRON", "WHT DWRF", "O-TYPE")

# At most this many capped kinds among the visible rows -- unless there are not enough
# rare ones to fill the table, in which case the cap lifts rather than leave slots
# empty. Distance ordering alone gave a list of ten neutrons: there are 1,035 of them
# against 69 black holes, so the common kinds win on proximity essentially always.
MAX_CAPPED_CONFIRMED = 3

# Rarity rank from the dict order, so the sort cannot drift from the list above.
_RANK_CASE = " ".join(
    f"WHEN kind = '{k}' THEN {i}" for i, k in enumerate(CONFIRMED_CLASSES))

# A system is CONFIRMED if either
#   (a) system_seen holds a rare arrival class for it -- self-maintaining, written by
#       the overlay every time a route is plotted; or
#   (b) system_confirmed holds it -- the curated log, migrated from confirmed.json.
# Not yet visited, because a visited find is a collected one.
#
# *** GALAXY-WIDE, unlike everything else on the overlay, and ordered by DISTANCE. ***
# A confirmed find is a certainty and certainties are scarce, so hiding the ones outside
# the current sector threw away the point of having them -- these are worth diverting
# for. The sector table stays sector-scoped because predictions are plentiful
# everywhere and only the nearby ones are interesting.
#
# Coordinates come from whichever source has them: system_seen holds x/y/z only when a
# ROUTE PLOT revealed the system (an FSDTarget gives the class alone), so
# system_confirmed's copy is the fallback. max() picks the non-NULL one, and a system
# with neither still appears -- ranked last, because unlocated is not the same as near.
def confirmed_cte():
    """The `confirmed AS (...)` CTE.

    ONE definition, used by confirmed_targets() to build the table and by top_targets()
    to keep those systems out of the sector table -- so a find appears exactly once, and
    a system that stops counting as confirmed reappears among the predictions rather
    than vanishing from the overlay altogether.
    """
    return f"""
confirmed AS (
  SELECT system, max(kind) AS kind, max(star_class) AS star_class,
         max(x) AS x, max(y) AS y, max(z) AS z,
         -- bool_or, so one source saying "already reported" settles it for both.
         bool_or(is_known) AS is_known
  FROM (
    SELECT s.system,
           CASE {_CLASS_CASE} ELSE NULL END AS kind,
           s.star_class, s.x, s.y, s.z, s.is_known
    FROM system_seen s
    WHERE s.star_class IN ({_ALL_CLASSES})
    UNION ALL
    SELECT c.system, c.kind, c.star_class, c.x, c.y, c.z, c.is_known
    FROM system_confirmed c
    WHERE NOT c.visited
  )
  WHERE kind IS NOT NULL
    AND system NOT IN (SELECT system FROM system_visited)
    -- *** A SYSTEM SOMEBODY HAS ALREADY REPORTED IS NOT A FIND. ***
    -- system_known is "observed, NOT predicted -- every row is a system somebody has
    -- actually reported", and reporting one means honking it, which DISCOVERS the
    -- arrival star. So its rare object already has somebody else's name on it and
    -- calling it confirmed claims something this table cannot deliver.
    --
    -- Measured when this went in: 408 of 1,087 confirmed systems were in the dumps,
    -- and -- the finding that decided it -- that was ALL 11 confirmed black holes and
    -- ALL 9 Wolf-Rayets. Black holes are the most-hunted objects in the game and these
    -- sat near plotted routes, so the honest count of undiscovered confirmed BH/WR is
    -- zero rather than twenty. The table is now neutrons, O-types, Herbigs and white
    -- dwarfs; an empty BH column here is a true statement, not a broken query.
    --
    -- WHAT SURVIVES IS THE POINT: 455 confirmed systems are in NO dump AND in no
    -- prediction either. They are absent from system_predicted only because the
    -- boxel-gap enumeration is a documented lower bound (50,212 galaxy-wide, heavily
    -- core-biased), so "not predicted" must NOT be used as the filter here -- it would
    -- throw away the best rows in the table to keep 131 catalogued ones.
    --
    -- READS THE STORED FLAG, never the bridge. Probing staging.sys_bridge here was the
    -- obvious implementation and cost 1.8 SECONDS per call: the app opens a fresh
    -- connection per operation (see the Store docstring), so a 197M-row scan starts
    -- with a cold buffer pool EVERY time and there is no index to fall back on. An
    -- indexed probe through system_known's UNIQUE (sector_id, system_in_sector)
    -- was measured
    -- too -- no faster at this scale, and it disagreed on 21 names. Resolving once and
    -- storing the answer is the only shape that works.
    --
    -- IS NOT TRUE, not `= FALSE`: NULL means nobody has checked this row yet, and the
    -- honest default is to SHOW it. Hiding a genuine find until a loader has run would
    -- make the table wrong in the expensive direction.
  GROUP BY system
  -- HAVING, not WHERE: the test has to run on the GROUPED value. Filtering per row
  -- would drop the row that says TRUE and keep a NULL one for the same system from the
  -- other source, so a reported system would survive the filter it just failed.
  HAVING bool_or(is_known) IS NOT TRUE
)"""


def full_name(k="k", sc="sc"):
    """SQL composing a system's FULL, PASTEABLE name from system_known + sector.

    *** sector_id = 0 IS THE 'crafted' SENTINEL AND ITS NAME STANDS ALONE. *** A
    hand-named system is stored with sector_id 0 -- the sector table's row 0 is
    literally named 'crafted' -- so the obvious `sc.sector || ' ' || k.system_in_sector`
    yields "crafted Charick Drift", which is not a place and which the galaxy map's
    search box rejects outright.

    THIS WAS A LIVE BUG IN THREE QUERIES AT ONCE, and the carrier list was the worst of
    them: 2,044 of the ~2,524 RELIABLE carriers are parked in hand-named systems, so
    most of the time the nearest carrier's name was uncopyable. 212 neutron systems and
    581 POI systems were affected the same way. Nothing complained, because the string
    looked plausible right up until you pasted it.

    Test by sector_id and NEVER by sector.is_crafted, which is TRUE for 424 real named
    sectors as well. Same rule as schema/system_all.sql, which had it right; these three
    predate it.
    """
    return (f"CASE WHEN {k}.sector_id = 0 THEN {k}.system_in_sector "
            f"ELSE {sc}.sector || ' ' || {k}.system_in_sector END")


# Straight-line distance from the commander to a POI system, computed over the
# AGGREGATED coordinates in the poi CTE. Separate from distance_sql() because that one
# takes a column prefix and this one has to sit inside max(); writing it out is clearer
# than teaching distance_sql about aggregation for its single aggregate caller.
POI_DIST = ("sqrt(pow(max(x) - ?, 2) + pow(max(y) - ?, 2) + pow(max(z) - ?, 2))")


def distance_sql(prefix=""):
    """SQL for straight-line distance in ly from the commander. NULL if unlocated.

    The three '?' bind x, y, z in order. A system with no coordinates yields NULL and
    must sort LAST: unlocated is not the same as nearby.
    """
    return (f"CASE WHEN {prefix}x IS NULL THEN NULL ELSE "
            f"sqrt(pow({prefix}x - ?, 2) + pow({prefix}y - ?, 2) "
            f"+ pow({prefix}z - ?, 2)) END")


class _NoTiming:
    """Timing that does nothing, so Store works standalone in scripts and tests."""

    @contextlib.contextmanager
    def phase(self, name):
        yield


_NO_TIMING = _NoTiming()


class Store:
    """Reads the model, writes app state. Every SQL string in the app lives here.

    *** CONNECTIONS ARE SHORT-LIVED, AND THAT IS THE WHOLE DESIGN. ***

    DuckDB allows exactly one process to hold a database file. An overlay that kept the
    app-state database open for its whole session would lock everyone else out of it --
    not just the loaders in `etl/`, but any read at all, including a read-only one. You
    could not inspect your own flight log while flying.

    So the file is opened per operation and closed immediately. Measured at ~175 ms for
    open + attach the model + query + close, which is nothing against a jump every
    thirty seconds, but far too slow for the two-second UI tick -- hence `counts()` is
    cached by the caller and the tick touches no database at all. The file ends up free
    essentially all the time, and `python etl/load_system_seen.py` can run mid-flight.
    """

    def __init__(self, timing=None):
        # Set by batch() while a group of reads shares one connection. None otherwise.
        self._pinned = None
        # The persistent hub, built on first use -- see _hub_connection().
        self._hub = None
        self._last_used = 0.0
        # Optional timing.Phases. The Store prices its OWN internals -- opening a
        # session, resolving is_known -- because from main.py they are invisible inside
        # one call, and they turned out to be most of it.
        self.timing = timing or _NO_TIMING
        if not MODEL_DB.exists():
            raise SystemExit(
                f"model database not found: {MODEL_DB}\n"
                f"The overlay needs it to know what is out there. It is read-only;\n"
                f"app state is written to {CURRENT_DB.name} and is unaffected.")

    # The hub connection's own name for each database.
    MODEL_ALIAS, CURRENT_ALIAS = "model", "cur"

    def _hub_connection(self):
        """The persistent in-memory connection with the MODEL attached. Built once.

        *** THIS IS THE INVERSION THAT MADE THE OVERLAY FAST, AND IT IS WORTH KNOWING
        WHY THE OBVIOUS ARRANGEMENT WAS BACKWARDS. ***

        The original design opened the app-state database per operation and attached the
        model to it, because DuckDB allows one writer per file and holding the app-state
        database open would lock out every loader. That reasoning was right about the
        app-state database and silently wrong about the model. Measured:

            connect to the app-state db     10 ms
            ATTACH the 60 GiB model        140 ms
            close (which detaches it)       72 ms

        212 of 222 ms was the model -- a read-only file the app never writes, re-opened
        and re-closed several times a second. So the two are swapped: the model is
        attached ONCE to a connection that outlives the operation, and the app-state
        database is attached and detached per operation instead, which costs 0.9 ms and
        0.2 ms. Session overhead went from 212 ms to about 1 ms.

        *** THE SINGLE-WRITER RULE IS UNCHANGED, because it was never about the model.
        *** The app-state file is still held only for the length of one operation, so
        `python etl/load_system_seen.py` still runs mid-flight -- verified, not assumed.

        THE COST: this process holds the model open read-only for as long as it is
        active, which blocks etl/ from WRITING the model. release_if_idle() gives it
        back after a spell of inactivity, so a builder only has to wait for the
        commander to stop flying.
        """
        if self._hub is None:
            with self.timing.phase("db_attach_model"):
                self._hub = duckdb.connect()
                self._hub.execute("SET memory_limit='4GB'")
                self._hub.execute("SET threads=8")
                self._hub.execute("SET preserve_insertion_order=false")
                self._hub.execute(
                    f"ATTACH '{MODEL_DB.as_posix()}' AS {self.MODEL_ALIAS} (READ_ONLY)")
        self._last_used = time.monotonic()
        return self._hub

    def release_if_idle(self, seconds=30.0):
        """Drop the model attachment after `seconds` without a query. -> True if freed.

        The overlay is bursty: a flurry around a jump or a plot, then nothing. Holding
        the model through the quiet stretches buys nothing and blocks etl/ from writing
        it, so it goes back. Re-attaching costs 131 ms, paid once on the next jump,
        against 212 ms saved on every operation in between.
        """
        if self._hub is None or self._pinned is not None:
            return False
        if time.monotonic() - self._last_used < seconds:
            return False
        self._hub.close()
        self._hub = None
        return True

    @contextlib.contextmanager
    def _session(self, read_only=False):
        """Attach the app-state db to the hub, hand over, detach. -> (con, model alias).

        REUSES A PINNED SESSION if batch() is holding one, so a repaint attaches once
        for all six of its reads.

        `USE cur` so unqualified table names mean the app-state tables, exactly as they
        did when that database was the connection's main one -- every query in this
        module is written that way and none of them had to change.

        read_only is a SAFETY property: a repaint must not be able to write. It costs
        nothing either way.
        """
        if self._pinned is not None:
            yield self._pinned
            return
        con = self._hub_connection()
        mode = " (READ_ONLY)" if read_only else ""
        with self.timing.phase("db_attach"):
            con.execute(f"ATTACH '{CURRENT_DB.as_posix()}' "
                        f"AS {self.CURRENT_ALIAS}{mode}")
            con.execute(f"USE {self.CURRENT_ALIAS}")
        try:
            yield con, self.MODEL_ALIAS
        finally:
            with self.timing.phase("db_detach"):
                # Back to the in-memory main database first: DETACH refuses to drop the
                # database that is currently in use.
                con.execute("USE memory")
                con.execute(f"DETACH {self.CURRENT_ALIAS}")

    @contextlib.contextmanager
    def batch(self, read_only=True):
        """Run several reads on ONE connection. READ-ONLY unless told otherwise.

        Two costs this removes, both measured:

        *** OPENING THE DATABASE COSTS ~170 ms AND A REPAINT MAKES SIX READS. *** That
        was a full second of every repaint spent on open + attach + close, more than any
        single query in it. Pinning one session removes five of the six.

        *** CLOSING ONE COSTS ANOTHER ~85 ms *** because the 60 GiB model has to be
        detached; without it attached, close is 1 ms. So a session is ~245 ms of
        overhead end to end, whatever it does.

        NESTS. batch() inside batch() reuses the outer session rather than opening a
        second, which is what lets record_revealed() wrap a WRITE around a refresh that
        opens its own read batch -- one session for the pair instead of two.

        read_only defaults to True because a repaint must not be able to write. It is a
        safety property, not a speed one: read-only and read-write open and close in the
        same time.

        This does NOT walk back the short-lived-connection rule in the Store docstring.
        The point of that rule is that the file must not be held for the SESSION, so
        loaders and ad-hoc reads can have it; a batch is held for one repaint and then
        released, which is the same bargain at a coarser grain.
        """
        with self._session(read_only=read_only) as pinned:
            self._pinned = pinned
            try:
                yield
            finally:
                self._pinned = None

    # -- reads (model) ------------------------------------------------------------
    RARE_MAX = ", ".join(f"p.{c}" for c in RARE_COLUMNS)

    def confirmed_targets(self, pos=None, limit=None):
        """Every unvisited system the game has ALREADY confirmed holds a rare object.

        GALAXY-WIDE and NEAREST FIRST. Not a prediction and not a probability: plotting
        a route reveals the arrival star of every hop, so these are certainties waiting
        to be collected -- the whole edge this tool has over flying at random. Scarce
        enough that the nearest one is worth knowing about from anywhere, which is why
        this alone ignores the current sector.

        `pos` is (x, y, z). Without one -- before the journal reports a position -- the
        list falls back to rarest-first, which is the best that can be said.

        Returns the SAME row shape as top_targets(), so one renderer draws both tables.
        """
        rarity = f"CASE {_RANK_CASE} ELSE 99 END"
        if pos:
            # Distance decides; rarity only breaks ties, so at equal range a black hole
            # still beats a white dwarf.
            order = f"dist_ly IS NULL, dist_ly, {rarity}, system"
            dist, params = distance_sql(), list(pos)
        else:
            order = f"{rarity}, system"
            dist, params = "NULL::DOUBLE", []
        cap = f"LIMIT {int(limit)}" if limit else ""
        capped_in = ", ".join(repr(k) for k in CAPPED_KINDS)
        slots = int(limit) if limit else 10
        with self._session() as (con, _model):
            cur = con.execute(f"""
                WITH {confirmed_cte()},
                scored AS (SELECT *, {dist} AS dist_ly FROM confirmed),
                -- QUOTA. Ordering purely by distance produced ten neutrons: the galaxy
                -- holds 1,035 confirmed neutrons against 69 black holes, so the common
                -- kinds are nearer essentially always and a distance-sorted list stops
                -- being a list of finds. Cap them, and let the cap LIFT when there are
                -- not enough rare ones to fill the table -- an empty slot helps nobody.
                quota AS (
                  SELECT *,
                         kind IN ({capped_in}) AS is_capped,
                         row_number() OVER (
                           PARTITION BY kind IN ({capped_in})
                           ORDER BY {order}) AS kind_rn,
                         sum(CASE WHEN kind IN ({capped_in}) THEN 0 ELSE 1 END)
                           OVER () AS n_rare
                  FROM scored
                ),
                kept AS (
                  SELECT * FROM quota
                  WHERE NOT is_capped
                     OR kind_rn <= greatest({MAX_CAPPED_CONFIRMED}, {slots} - n_rare)
                )
                SELECT
                    row_number() OVER (ORDER BY {order}) AS rank,
                    system                                           AS system,
                    kind                                                  AS type_label,
                    dist_ly, FALSE AS dist_approx,
                    -- No probabilities: the game already told us what is there. The
                    -- renderer shows '--' for these (known) rather than the '-' it uses
                    -- for a POI row, so certainty and not-applicable stay apart.
                    {P_NULLS},
                    CASE {_CONFIRMED_COL_CASE} END AS confirmed_col,
                    {ROW_CONFIRMED} AS row_grp, NULL::VARCHAR AS wide_text,
                    star_class AS detail,
                    NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
                    x, y, z,
                    NULL::DOUBLE AS dist_sol, star_class
                FROM kept ORDER BY rank {cap}""", params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def top_targets(self, sector, limit=10, pos=None):
        """The best unvisited targets in `sector`, best first. -> list of dicts.

        RANKED BY PROBABILITY, NOT DISTANCE -- sorting by how far away a
        candidate was, which meant grinding outward through whatever happened to be
        nearby. Within one sector everything is close, so the question becomes purely
        "which of these is most likely to hold something".

        Three kinds of row compete for the ten slots, in this order: points of interest
        (capped at MAX_POI_ROWS, certain finds), boxel-predicted systems, then
        catalogued systems as BACKFILL, rendered in a different colour so an inferred
        target and a merely-unscanned one never look alike.

        *** A caveat that shapes how every column should be read: EVERY p is fitted per
        (mass_code, plane_r band), and a single sector spans one band. So a sector
        offers only about FOUR distinct prediction ROWS -- one per mass code present --
        and two systems of the same mass code here are, to this model, identical. ***
        The ordering is therefore "highest mass code first"; the tiebreak does the rest
        of the visible work: expected body count, then system so the order is
        deterministic and the F-key assignments do not shuffle between refreshes.

        Keys are this table's own F1..F10; the Confirmed table uses CTRL+F1..F10, so
        neither can consume the other's.

        Anything in the CONFIRMED table is excluded here -- it must appear once, in the
        table that says it is certain, and never again among the guesses.
        """
        with self._session() as (con, model):
            cur = con.execute(f"""
                WITH {confirmed_cte()},
                sys AS (
                  SELECT p.*, s.star_class,
                         CASE WHEN p.is_catalog THEN {ROW_CATALOG}
                              ELSE {ROW_PREDICTED} END AS row_grp
                  FROM {model}.main.system_predicted p
                  LEFT JOIN system_visited v ON v.system = p.system
                  LEFT JOIN system_seen    s ON s.system = p.system
                  WHERE p.sector = ? AND v.system IS NULL
                    AND p.system NOT IN (SELECT system FROM confirmed)
                    -- *** THE COMMANDER TRIED TO PLOT TO IT AND WAS REFUSED. *** A
                    -- boxel prediction enumerates an index gap the Forge may never have
                    -- filled, so misses were always expected; this is the only way one
                    -- can be reported. Filtered rather than deleted -- the model is
                    -- rebuildable and this correction is not. See mark_wrong().
                    AND p.system NOT IN (SELECT system FROM system_wrong)
                    -- *** ONCE THE GAME HAS TOLD US THE ARRIVAL CLASS, THE ROW LEAVES
                    -- THIS TABLE. *** Plotting a route resolves the only question a
                    -- prediction row asks. If the class is rare it reappears in
                    -- Confirmed; if it is an ordinary M dwarf there is nothing left to
                    -- gamble on, and leaving it here showing "BLK HOLE 0.39" would be
                    -- advertising odds we have already seen settled.
                    --
                    -- s.star_class, not s.system: a system can be in system_seen
                    -- with COORDINATES ONLY (a route plot gives both, an FSDTarget
                    -- gives the class alone, and the migration left some with
                    -- neither). Position tells us nothing about what is there, so
                    -- those must stay.
                    AND s.star_class IS NULL
                    -- At least one RARE prediction must clear the bar. Per-column, and
                    -- never a sum: mutually exclusive outcomes for one star.
                    AND greatest({self.RARE_MAX}) >= {MIN_RARE}
                ),
                -- Points of interest here: CERTAIN finds, not predictions. System-level
                -- and body-level attribution are unioned because a POI pinned to a
                -- named body is recorded against the BODY, so system_known alone would
                -- miss it.
                poi_raw AS (
                  SELECT {full_name()} AS system,
                         po.poi, po.poi_class, k.x, k.y, k.z
                  FROM {model}.main.system_known k
                  JOIN {model}.main.sector sc ON sc.sector_id = k.sector_id
                  JOIN {model}.main.poi po    ON po.poi_id = k.id_poi
                  WHERE sc.sector = ?
                  UNION
                  SELECT {full_name()}, po.poi, po.poi_class,
                         k.x, k.y, k.z
                  FROM {model}.main.system_body sb
                  JOIN {model}.main.system_known k ON k.system_id = sb.system_id
                  JOIN {model}.main.sector sc      ON sc.sector_id = k.sector_id
                  JOIN {model}.main.poi po         ON po.poi_id = sb.id_poi
                  WHERE sc.sector = ? AND sb.id_poi IS NOT NULL
                ),
                poi AS (
                  -- One row per SYSTEM: a system can hold several POIs on several
                  -- bodies, and ten slots are too few to spend on repeats of the same
                  -- destination. min() is arbitrary but stable across refreshes.
                  --
                  -- ORDERED BY DISTANCE, not by poi_class. Inside a real sector this
                  -- barely matters -- everything is within 1280 ly of everything else
                  -- -- but the 'crafted' sentinel sector holds every hand-named system
                  -- in the GALAXY, so there the alphabetical-by-class order picked
                  -- three POIs essentially at random from 65,000 ly of space. NULLS
                  -- LAST: unlocated is not the same as near. poi_class then system
                  -- still break ties, so the order stays deterministic.
                  SELECT system, min(poi) AS poi, min(poi_class) AS poi_class,
                         max(x) AS x, max(y) AS y, max(z) AS z,
                         row_number() OVER (ORDER BY {POI_DIST} NULLS LAST,
                                                     min(poi_class), system) AS pr
                  FROM poi_raw
                  WHERE system NOT IN (SELECT system FROM poi_visited)
                    AND system NOT IN (SELECT system FROM system_visited)
                    AND system NOT IN (SELECT system FROM confirmed)
                  GROUP BY system
                ),
                unioned AS (
                  SELECT {ROW_POI} AS row_grp, pr AS ord, system,
                         upper(poi_class) AS type_label, poi AS detail,
                         NULL::DOUBLE AS p_bh,     NULL::DOUBLE AS p_wr,
                         NULL::DOUBLE AS p_herbig, NULL::DOUBLE AS p_supergiant,
                         NULL::DOUBLE AS p_otype,  NULL::DOUBLE AS p_neutron,
                         NULL::DOUBLE AS p_wd,     NULL::DOUBLE AS p_hr,
                         NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
                         x, y, z,
                         -- A POI's coordinates come from system_known and are EXACT.
                         FALSE AS dist_approx,
                         NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
                  FROM poi WHERE pr <= {MAX_POI_ROWS}
                  UNION ALL
                  SELECT row_grp,
                         row_number() OVER (PARTITION BY row_grp
                                            ORDER BY {RANK_BY.replace('p.', '')} DESC,
                                                     exp_bodies DESC, system),
                         system,
                         CASE WHEN mass_code IS NULL THEN '?'
                              ELSE 'Mass ' || upper(mass_code) END,
                         NULL,
                         p_bh, p_wr, p_herbig, p_supergiant, p_otype,
                         p_neutron, p_wd, p_hr,
                         mass_code, boxel, x, y, z,
                         -- *** A BOXEL-PREDICTED system carries its BOXEL CENTROID,
                         -- not its position. *** A boxel is up to 1280 ly across, so
                         -- the distance is good to about +/-640 ly and the renderer
                         -- marks it with a leading '~'. Catalogued systems are in the
                         -- dumps with exact coordinates and need no such warning.
                         NOT is_catalog AS dist_approx,
                         dist_sol, star_class
                  FROM sys
                ),
                ranked AS (
                  SELECT *, {distance_sql()} AS dist_ly,
                         row_number() OVER (ORDER BY row_grp, ord) AS rank
                  FROM unioned
                )
                SELECT
                    rank,
                    system                       AS system,
                    type_label,
                    {P_COLUMNS},
                    -- Not displayed: these drive per-row colour and per-cell emphasis
                    -- in table.py, which needs the fact and not its wording.
                    NULL::VARCHAR AS confirmed_col, dist_ly, dist_approx,
                    NULL::VARCHAR AS wide_text,
                    row_grp, detail, mass_code, boxel, x, y, z, dist_sol, star_class
                FROM ranked ORDER BY rank LIMIT ?""",
                # THREE sector binds, then the position TWICE: once for the POI
                # ordering inside the poi CTE and once for the displayed distance in
                # `ranked`. DuckDB binds positionally, so the order here follows the
                # order the '?' appear in the SQL above and nothing else.
                [sector, sector, sector,
                 *(pos or (None, None, None)),
                 *(pos or (None, None, None)), limit])
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def unfound_targets(self, sector, limit=3, pos=None):
        """Real catalogued stars whose POSITION falls in `sector`. -> shared row shape.

        main.system_unfound: HIP, GJ and HR stars with a trustworthy parallax that no
        game system can be matched to, by name or by any cross-identification the alias
        bridge holds. 235 of them galaxy-wide, spread over 43 sectors.

        *** THEY ARE NOT PREDICTIONS AND THEY CARRY NO PROBABILITIES. *** Every other
        row on this table is a Stellar Forge system the game certainly has, asking what
        is inside it. These ask whether the system EXISTS -- the answer is one of "the
        game has it under a name no catalogue assigns", "nobody has visited it", or
        "Frontier did not ship it", and only flying there tells you which. So the
        prediction area holds `wide_text` (where to fly, and how far the last hop is)
        rather than eight numbers nobody computed.

        THE SECTOR IS ASSIGNED BY NEAREST CENTROID, not parsed from a name -- these
        stars have no procedural name to parse, which is the whole reason they are
        here. Reliable for a "near" row, a hint for a "mid" one whose position is good
        only to 100-333 ly; see the column comment on system_unfound.sector_id. That is
        also why `dist_approx` is set for the mid band and not the near one: the '~' is
        carrying a real 100 ly uncertainty, exactly as it does on a boxel centroid.

        NEAR BAND FIRST, then shortest last hop. `nearest` is a HAND-NAMED game system
        -- the galaxy map takes a name and not a coordinate, so it is the only practical
        way in, and a row without one is a harder trip rather than a better lead.
        """
        if not sector:
            return []
        with self._session() as (con, model):
            cur = con.execute(f"""
                SELECT row_number() OVER (ORDER BY u.band, u.nearest_ly NULLS LAST,
                                                   u.system) AS rank,
                       u.system,
                       'UNFOUND' AS type_label,
                       {distance_sql('u.')} AS dist_ly,
                       -- A "mid" position is good to 100-333 ly. Same warning the
                       -- boxel centroids carry, for the same reason.
                       u.band <> 'near' AS dist_approx,
                       {P_NULLS},
                       NULL::VARCHAR AS confirmed_col,
                       {ROW_UNFOUND} AS row_grp,
                       printf('%-4s %-9s  %s',
                              upper(u.band), coalesce(u.sp_type, ''),
                              CASE WHEN u.nearest IS NULL
                                   THEN 'no hand-named system within 20 ly'
                                   ELSE printf('fly to %s  (%.2f ly)',
                                               u.nearest, u.nearest_ly)
                              END) AS wide_text,
                       u.nearest AS detail,
                       NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
                       u.x, u.y, u.z, u.dist_ly AS dist_sol,
                       NULL::VARCHAR AS star_class
                FROM {model}.main.system_unfound u
                WHERE u.sector = ?
                  -- Visited means the question was answered on the ground, whichever
                  -- way it went. Marked wrong means the commander answered it by being
                  -- refused a route -- see mark_wrong().
                  AND u.system NOT IN (SELECT system FROM system_visited)
                  AND u.system NOT IN (SELECT system FROM system_wrong)
                ORDER BY rank LIMIT {int(limit)}""",
                [*(pos or (None, None, None)), sector])
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    # -- writes (app state) -------------------------------------------------------
    def mark_wrong(self, system, source, sector=None, note=None, timestamp=None):
        """Record that a system DOES NOT EXIST. -> True if this is the first time.

        Written when the commander presses SHIFT+BACKSPACE on a row: the galaxy map
        refused to plot to it, or the arrival found nothing.

        *** THIS IS A FILTER, NOT A DELETE, AND THE DISTINCTION IS THE WHOLE DESIGN. ***
        The obvious implementation is to delete the row from system_predicted or
        system_unfound. Two reasons that is wrong, and either alone settles it:

          1. THE APP MAY NEVER WRITE THE MODEL (common/current.py). Both those tables
             are derived and both their builders DELETE rows their pool no longer
             produces, so the correction would survive exactly until the next rebuild
             and then vanish with nothing to show it had ever been made.
          2. IT IS THE ONLY NEGATIVE EVIDENCE THIS PROJECT CAN COLLECT. Every other
             table here is built from what somebody reported SEEING; nobody reports an
             absence. Deleting the row would throw the finding away in the act of
             recording it.

        So the prediction stays exactly where it is and this says the commander has
        settled it. Every read that offers a destination filters against this table.

        Idempotent -- pressing the key twice on the same row is not an error, and the
        original marking time is what makes an old row weaker evidence than a new one,
        so it is never overwritten.
        """
        stamp = timestamp or (datetime.datetime.now(datetime.timezone.utc)
                              .strftime("%Y-%m-%dT%H:%M:%SZ"))
        with self._session() as (con, _model):
            if con.execute("SELECT count(*) FROM system_wrong WHERE system = ?",
                           [system]).fetchone()[0]:
                return False
            # id64 IS LEFT NULL, ON PURPOSE. Resolving it means probing
            # staging.sys_bridge, which is 197M rows with no index on the name and
            # costs ~1.7 s -- a freeze that long on a keypress, while flying, is worse
            # than a NULL in a column whose own comment says NULL is normal and which
            # nothing joins on. etl/load_system_wrong.py can fill it later, off the
            # flight path, if it ever turns out to be wanted.
            con.execute(f"""
                INSERT INTO system_wrong (system, source, sector, id64, marked_utc, note)
                VALUES (?, ?, coalesce(?, {sector_sql('?')}), NULL, ?, ?)""",
                [system, source, sector, system, stamp, note])
        return True

    # The shared shape of a summary row. Sector and region each emit a PAIR of these
    # -- boxel-predicted, then catalogued -- and every field below is identical between
    # them, which is the point: two lines formatted differently invite the reader to
    # think they measure different things.
    @staticmethod
    def _totals_row(label, n, sums, catalogued=False):
        row = dict(sums)
        row.update({
            "rank": None, "n": n, "system": label,
            # Sigma + the size of the pool being summed. Fits the 7-character TYPE
            # column at four-figure sector sizes, where "2,788 sys" did not.
            "type_label": f"\u03a3 {n:,}",
            # ROW_TOTAL, or ROW_TOTAL_CATALOG for the catalogued half. Both are totals
            # rows in every behavioural sense -- counts rather than probabilities, off
            # the colour gradient, and not somewhere you can fly -- and the kinds differ
            # for ONE reason: colour. The catalogued line takes the same blue-grey as
            # the catalogued rows above it, so the sum and the things it sums read as
            # one population.
            #
            # Neither can be selected, and that is by construction rather than by this
            # value: _paint() builds the cursor's row list from `targets` alone and
            # appends the summary lines afterwards, so nothing here can ever reach it.
            "row_grp": ROW_TOTAL_CATALOG if catalogued else ROW_TOTAL,
            "detail": None, "mass_code": None, "boxel": None,
            "confirmed_col": None, "dist_ly": None, "dist_approx": False,
            "wide_text": None, "x": None, "y": None, "z": None,
            "dist_sol": None, "star_class": None,
        })
        return row

    # The second line of each pair. SHORT, and the pool word leads. Sector names reach
    # 32 characters and region names 27, against a 24-wide SYSTEM column, so anything
    # appended to a name is the first thing truncated away -- and the pool word is the
    # only information on this line that the line above does not already carry. The
    # name is not repeated because this row sits directly beneath the one that has it.
    CATALOGUED_LABEL = "  + CATALOGUED"

    def _totals_pair(self, con, model, label, where, params):
        """Run one grouped query; return [boxel row, catalogued row]. Always both.

        *** ONE QUERY GROUPED BY is_catalog, NOT TWO QUERIES. *** The two lines read the
        same columns of the same table under the same predicate; splitting them would
        double the scan to produce halves of one answer.

        BOTH ROWS ALWAYS COME BACK, zeroed when their half of the pool is empty. A line
        that vanishes at zero is the bug this pair exists to fix -- a missing line reads
        as a disagreement, where an explicit 0 reads as a fact.
        """
        cur = con.execute(f"""
            SELECT p.is_catalog AS is_cat, count(*) AS n,
                   {", ".join(f"sum(p.{c}) AS {a}" for c, a in DISPLAY_P)}
            FROM {model}.main.system_predicted p
            LEFT JOIN system_visited v ON v.system = p.system
            WHERE {where} AND v.system IS NULL
            GROUP BY 1""", params)
        cols = [d[0] for d in cur.description]
        by_cat = {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}
        out = []
        for is_cat, text in ((False, label), (True, self.CATALOGUED_LABEL)):
            got = by_cat.get(is_cat)
            n = got["n"] if got else 0
            sums = ({a: got[a] for _c, a in DISPLAY_P} if got
                    else {a: None for _c, a in DISPLAY_P})
            out.append(self._totals_row(text, n, sums, catalogued=is_cat))
        return out

    def sector_totals(self, sector):
        """Expected UNDISCOVERED objects of each type left in `sector`.

        -> a PAIR of rows: boxel-predicted first, catalogued second.

        A probability IS an expected count. p_bh = 0.40 on one system means 0.4 black
        holes expected there, so summing p_bh across the systems gives the expected
        number in the sector -- and unlike the per-row probabilities, these sums are
        additive and mean exactly what they look like.

        *** TWO LINES BECAUSE THERE ARE TWO POPULATIONS, AND ONE LINE HID THAT. ***
        This used to sum boxel-predicted systems ONLY, while the table above it lists
        POI, boxel AND catalogued rows. Measured when it was fixed: the total agreed
        with the list it sat under in 53 of 8,790 sectors, and in 3,385 of them the
        table showed rows while the total read zero. Galaxy-wide the sum covered
        215,845 systems and ignored 2,206,986.

        The exclusion was not arbitrary, but its stated reason does not survive:
        catalogued systems were said to be "in the dumps already, so whatever they hold
        is not undiscovered". The catalogued half of system_predicted is built as
        system_known MINUS system_body -- systems with NO reported bodies at all. Their
        POSITION is known and their CONTENTS are not, which is exactly why top_targets
        offers them.

        So neither population is dropped and neither is folded into the other. They are
        different kinds of target -- one inferred from a gap in the Forge index, one a
        real system nobody has scanned -- and a single number would average two things
        you would act on differently.

        THE POOL IS THE NOT-YET-VISITED SYSTEMS, split by is_catalog. No MIN_RARE bar
        and no LIMIT: this counts the WHOLE sector, not the ten rows on screen, which is
        the point of showing it. The pair can therefore exceed what the table lists, and
        should -- the rows are the top ten, these are the sector.
        """
        with self._session() as (con, model):
            return self._totals_pair(
                con, model,
                # "SECTOR <name>", matching "REGION <name>" below. The word leads for
                # the same reason it does there: sector names reach 32 characters
                # against a 24-wide column, so a trailing label would be truncated away
                # and the one word saying this is not a destination is the one that has
                # to survive. It also puts the two scope lines in the same shape, so the
                # eye reads them as a pair of the same kind of statement.
                f"SECTOR {sector}", "p.sector = ?", [sector])

    def region_totals(self, sector):
        """The same pair of sums, over the WHOLE REGION `sector` sits in.

        -> a PAIR of rows, or None when the sector is not one the model knows.

        THE LINES THAT SAY WHETHER TO STAY. The sector pair directly above answers "what
        is left here" and the Adjacent sectors table answers "what is next door", but
        neither says how big the pot is -- and the region is the natural unit for that,
        because it is the scale at which the model's own fit changes. Every probability
        is fitted per (mass_code, plane_r band), so two sectors in the same region draw
        from the same distribution and the sums really are comparable.

        THE POOL IS EXACTLY sector_totals()' POOL, WIDENED, and split the same way on
        is_catalog. It has to be, or lines stacked on top of each other would measure
        different things, and the only reason to show them together is that they do not.
        Verified: summing per-sector totals within a region reproduces the region figure
        exactly, to the last decimal, in every region -- and zero prediction rows fail
        to join the sector table, so nothing is lost on the way up.

        *** THE CURRENT SECTOR IS INCLUDED, NOT SUBTRACTED. *** "The region" means the
        region. Reading the pair as "41 of 1,387 are here" is the comparison these lines
        exist for, and it only works if the larger number contains the smaller.

        Region comes the long way round, through the sector NAME: system_predicted
        carries no region_id, only the parsed sector string.
        """
        with self._session() as (con, model):
            region = con.execute(
                f"""SELECT r.region FROM {model}.main.sector sc
                    JOIN {model}.main.region r ON r.region_id = sc.region_id
                    WHERE sc.sector = ?""", [sector]).fetchone()
            # No region means the sector name is not one the model knows -- nothing to
            # summarise, as against a region that is merely empty.
            if not region:
                return None
            return self._totals_pair(
                con, model, f"REGION {region[0]}",
                f"""p.sector IN (SELECT sc.sector FROM {model}.main.sector sc
                                 WHERE sc.region_id = (SELECT sc2.region_id
                                                       FROM {model}.main.sector sc2
                                                       WHERE sc2.sector = ?))""",
                [sector])

    def adjacent_sectors(self, sector, pos=None, limit=10):
        """The nearest OTHER sectors, with the expected objects left in each.

        Where the totals row says what is left HERE, this says what is left next door
        -- so the decision "is this sector worth staying in" can be made against
        something instead of in the abstract. Every number is an expected COUNT summed
        over the whole sector, not a probability, exactly as the totals row is.

        THE POOL IS THE SAME as sector_totals(): boxel-predicted, not catalogued, not
        visited. It has to be, or the row you compare against would be measuring a
        different thing from the row above it.

        *** ORDERED BY DISTANCE TO THE SECTOR CENTROID, AND THAT IS APPROXIMATE. ***
        A sector's bounding ball has a median radius of 1,727 ly while neighbouring
        centroids sit about 1,280 ly apart, so the balls overlap heavily and the nearest
        centroid is not always the nearest system. Rows are marked `dist_approx`, which
        the renderer shows as a leading '~'.

        ONLY SECTORS YOU CAN ACTUALLY GO TO appear, which is a stronger test than
        "holds a prediction". The ten nearest sectors outright would usually be ten
        empty ones -- just 2,874 of 12,065 sectors hold any boxel prediction at all --
        and beyond that, a sector whose every prediction has already been settled by the
        galaxy map has expected objects on paper and nowhere to fly. Both are dropped
        BEFORE the limit, so the ten slots always hold ten usable rows.

        Each row carries `copy_text`: the best system IN that sector, so ALT+Fn hands
        over somewhere you can actually plot a route to rather than a sector name the
        galaxy map will not accept.

        *** "BEST" IS RANK_BY -- THE SAME EXPRESSION THE CURRENT-SECTOR TABLE RANKS ON,
        DELIBERATELY. *** So ALT+Fn hands back exactly the system F1 would offer once
        you arrived, and the two tables cannot recommend different places. An earlier
        version ranked on the summed per-type probabilities instead, on the reasoning
        that a table of aggregates should hand over the system with the largest
        aggregate. Measured, that cost real ground: across the 2,874 sectors holding a
        boxel prediction the two picks differed in 444, differed about the MASS CODE in
        all 444, and the summed pick was worse on greatest(p_bh, p_wr) in 444 of 444 --
        mean 0.46 down to 0.40. Summing lets neutrons and white dwarfs, which are
        numerous, outweigh the one column the whole project is about.

        The SECTOR columns are still sums, and should be: they answer "is this sector
        worth the trip", which is a question about everything in it. Only the choice of
        SYSTEM within the winning sector is a rarity ranking.
        """
        if not pos:
            # Distance is the entire ordering; without a position there is no table.
            return []
        sums = ", ".join(f"sum({c}) AS {a}" for c, a in DISPLAY_P)
        with self._session() as (con, model):
            cur = con.execute(f"""
                WITH pool AS (
                  SELECT p.sector, p.system, p.exp_bodies,
                         {", ".join(f"p.{c}" for c, _a in DISPLAY_P)},
                         {RANK_BY} AS rank_score,
                         -- Carried, not filtered on, because the sums and the pick
                         -- want different things from it. See `best` below.
                         s.star_class
                  FROM {model}.main.system_predicted p
                  LEFT JOIN system_visited v ON v.system = p.system
                  LEFT JOIN system_seen    s ON s.system = p.system
                  WHERE NOT p.is_catalog AND v.system IS NULL
                    AND p.sector IS NOT NULL
                    -- The sector we are standing in already has a table of its own,
                    -- with the individual systems rather than a sum. `sector` is NULL
                    -- in hand-named space, where IS DISTINCT FROM keeps every row.
                    AND p.sector IS DISTINCT FROM ?
                ),
                agg AS (SELECT sector, count(*) AS n, {sums} FROM pool GROUP BY sector),
                -- The destination each key copies, and -- via the INNER JOIN below --
                -- the test of whether a sector is offerable at all.
                --
                -- *** TWO FILTERS THE SUMS ABOVE DO NOT APPLY, because a sum and a
                -- destination are asked different questions. *** The sums answer "what
                -- is left in this sector" and must match what sector_totals() reports
                -- for the sector we are standing in, or the row you compare against
                -- would be measuring something else. The pick answers "where should I
                -- go", and the Current sector table refuses to offer a system for two
                -- reasons that apply just as much from a sector away:
                --
                --   star_class IS NULL   the galaxy map has ALREADY revealed what is
                --                        there, so the question the prediction asks is
                --                        settled. Not hypothetical: every boxel
                --                        prediction in Cyoagea is a known B star, and
                --                        without this ALT+Fn sent you to one.
                --   the MIN_RARE bar     nothing here clears the threshold that makes
                --                        a row worth displaying at all.
                --
                best AS (
                  SELECT sector, system FROM (
                    SELECT p.sector, p.system,
                           row_number() OVER (
                             PARTITION BY p.sector
                             ORDER BY p.rank_score DESC, p.exp_bodies DESC,
                                      p.system) AS rn
                    FROM pool p
                    WHERE p.star_class IS NULL
                      AND greatest({", ".join(f"p.{c}" for c in RARE_COLUMNS)})
                            >= {MIN_RARE}
                      -- A THIRD FILTER ON THE PICK AND NOT ON THE SUMS, for the same
                      -- reason as the two above: a system the commander could not plot
                      -- to is nowhere to send them. Deliberately NOT applied to `agg`
                      -- -- those sums have to keep matching sector_totals(), and one
                      -- commander's refused route is not a fact about the sector.
                      AND p.system NOT IN (SELECT system FROM system_wrong)
                  ) WHERE rn = 1
                ),
                -- INNER JOIN to best, and BEFORE the LIMIT. A sector with no reachable
                -- target must not occupy one of the ten slots: it would show real sums
                -- against a key that has nowhere to send you. Cyoagea is the live
                -- example -- both its boxel predictions are already-revealed B stars,
                -- so it has expected objects on paper and nothing to fly to.
                near AS (
                  SELECT a.*, b.system AS best_system,
                         {distance_sql('k.')} AS dist_ly
                  FROM agg a
                  JOIN {model}.main.sector k ON k.sector = a.sector
                  JOIN best b ON b.sector = a.sector
                  ORDER BY dist_ly LIMIT {int(limit)}
                )
                SELECT row_number() OVER (ORDER BY dist_ly) AS rank,
                       n.sector AS system,
                       -- Sigma and the size of the pool summed, the same shorthand the
                       -- totals row uses -- these rows mean the same kind of thing.
                       'Σ ' || format('{{:,}}', n.n) AS type_label,
                       n.dist_ly,
                       -- A centroid, not a position. The '~' is not decoration.
                       TRUE AS dist_approx,
                       {", ".join(f"n.{a}" for _c, a in DISPLAY_P)},
                       NULL::VARCHAR AS confirmed_col,
                       {ROW_SECTOR} AS row_grp, NULL::VARCHAR AS wide_text,
                       n.best_system AS detail, n.best_system AS copy_text,
                       NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
                       NULL::DOUBLE AS x, NULL::DOUBLE AS y, NULL::DOUBLE AS z,
                       NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
                FROM near n
                ORDER BY rank""", [sector, *pos])
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def sector_summary(self, sector):
        """-> (eligible, visited, catalogued_excluded) for `sector`.

        `catalogued_excluded` exists so an empty table can say WHY it is empty. Only
        2,874 of 8,741 sectors hold any boxel-predicted system at all, so a blank
        overlay is the common case, not a fault -- and "0 predicted, 90 catalogued and
        excluded" is a very different message from "0 of anything here".
        """
        with self._session() as (con, model):
            return con.execute(f"""
                SELECT count(*) FILTER (WHERE eligible),
                       count(*) FILTER (WHERE eligible AND visited),
                       count(*) FILTER (WHERE p.is_catalog)
                FROM (
                  SELECT p.is_catalog,
                         NOT p.is_catalog
                           AND greatest({self.RARE_MAX}) >= {MIN_RARE} AS eligible,
                         v.system IS NOT NULL                     AS visited
                  FROM {model}.main.system_predicted p
                  LEFT JOIN system_visited v ON v.system = p.system
                  WHERE p.sector = ?
                ) p""", [sector]).fetchone()

    def poi_in_system(self, system):
        """-> (poi_id, poi, poi_class) if the model knows a POI here, else None.

        Checks system-level attribution first, then body-level: a POI pinned to a named
        body is recorded against the body, so system_known alone would miss it.
        """
        with self._session() as (con, model):
            return self._poi_lookup(con, model, system)

    @staticmethod
    def _poi_lookup(con, model, system):
        """The POI query itself, on an ALREADY OPEN session -- so record_poi_visit()
        can look up and insert without opening the database twice."""
        return con.execute(f"""
            WITH ids AS (
              SELECT system_id FROM {model}.staging.sys_bridge WHERE sys_name = ?
            ), found AS (
              SELECT min(coalesce(k.id_poi, sb.id_poi)) AS poi_id
              FROM ids i
              LEFT JOIN {model}.main.system_known k ON k.system_id = i.system_id
              LEFT JOIN {model}.main.system_body  sb
                     ON sb.system_id = i.system_id AND sb.id_poi IS NOT NULL
            )
            SELECT f.poi_id, p.poi, p.poi_class
            FROM found f JOIN {model}.main.poi p ON p.poi_id = f.poi_id""",
            [system]).fetchone()

    # -- writes (app state only) ---------------------------------------------------
    # id64 is left NULL by every write here ON PURPOSE. Resolving it means probing a
    # 197M-row name bridge, which is seconds of work -- fine in a loader, not inside a
    # UI callback on every jump. `etl/load_system_*.py` backfill it later; NULL is a
    # documented, expected value on all four tables.
    def record_arrival(self, system, timestamp=None):
        """Record an arrival in ONE session: the visit, and the POI if there is one.

        -> (was_new_system, poi_label_or_None)

        Both writes share a session deliberately. They fire on the same event, and
        opening the database twice per jump doubles the only expensive thing the app
        does. Idempotent: a replayed journal event changes nothing but the timestamp.
        """
        with self._session() as (con, model):
            new = not con.execute(
                "SELECT count(*) FROM system_visited WHERE system = ?",
                [system]).fetchone()[0]
            if new:
                con.execute(f"""
                    INSERT INTO system_visited
                        (system, id64, sector, first_visited_utc, last_visited_utc)
                    VALUES (?, NULL, {sector_sql('?')},
                            try_cast(? AS TIMESTAMP), try_cast(? AS TIMESTAMP))""",
                    [system, system, timestamp, timestamp])
            elif timestamp:
                # Revisits are normal -- a carrier system or a staging point gets
                # passed through repeatedly -- so only the last-seen time moves.
                con.execute("""
                    UPDATE system_visited SET last_visited_utc = try_cast(? AS TIMESTAMP)
                    WHERE system = ?""", [timestamp, system])

            poi = None
            already = con.execute(
                "SELECT count(*) FROM poi_visited WHERE system = ?",
                [system]).fetchone()[0]
            if not already and model:
                hit = self._poi_lookup(con, model, system)
                if hit:
                    poi_id, poi, poi_class = hit
                    con.execute(f"""
                        INSERT INTO poi_visited (system, id64, sector,
                                                 poi_id, poi, poi_class, visited_utc)
                        VALUES (?, NULL, {sector_sql('?')}, ?, ?, ?,
                                try_cast(? AS TIMESTAMP))""",
                        [system, system, poi_id, poi, poi_class, timestamp])
        return new, poi

    def record_seen(self, rows, timestamp=None):
        """Record arrival classes revealed WITHOUT visiting. -> number of new systems.

        `rows` are (system, star_class, x, y, z) from a plotted route or a jump
        target. This is the single most valuable write the app makes: an H or a W* here
        is a black hole or Wolf-Rayet nobody has catalogued, known for free, and the
        Confirmed table is built straight out of it.

        NEVER DOWNGRADES. A route plot gives class AND exact position; an FSDTarget
        gives class only. coalesce on the target side means the second kind of event
        cannot blank the coordinates the first one supplied.
        """
        rows = [r for r in rows if r and r[0]]
        if not rows:
            return 0
        with self._session() as (con, _model):
            con.execute("""CREATE OR REPLACE TEMP TABLE seen_in
                           (system VARCHAR, star_class VARCHAR,
                            x DOUBLE, y DOUBLE, z DOUBLE)""")
            con.executemany("INSERT INTO seen_in VALUES (?, ?, ?, ?, ?)", rows)
            # One row per system: a route can list the same system twice, and the
            # richest version of it wins.
            con.execute("""CREATE OR REPLACE TEMP TABLE seen_src AS
                SELECT system, max(star_class) AS star_class,
                       max(x) AS x, max(y) AS y, max(z) AS z
                FROM seen_in WHERE system IS NOT NULL GROUP BY 1""")
            con.execute("""
                UPDATE system_seen AS t
                SET star_class = coalesce(s.star_class, t.star_class),
                    x = coalesce(s.x, t.x), y = coalesce(s.y, t.y),
                    z = coalesce(s.z, t.z)
                FROM seen_src AS s WHERE s.system = t.system""")
            new = con.execute("""SELECT count(*) FROM seen_src s WHERE NOT EXISTS
                (SELECT 1 FROM system_seen t WHERE t.system = s.system)"""
                ).fetchone()[0]
            if new:
                con.execute(f"""
                    INSERT INTO system_seen (system, star_class, x, y, z,
                                             id64, sector, first_seen_utc)
                    SELECT s.system, s.star_class, s.x, s.y, s.z, NULL,
                           {sector_sql('s.system')}, try_cast(? AS TIMESTAMP)
                    FROM seen_src s WHERE NOT EXISTS
                      (SELECT 1 FROM system_seen t
                       WHERE t.system = s.system)""", [timestamp])
            if new:
              with self.timing.phase("resolve_known"):
                # RESOLVE IN THE SAME SESSION AS THE INSERT. A row with is_known NULL is
                # shown as a find (the CTE's IS NOT TRUE), which is the right default
                # but is wrong for the ~40% of reveals that are already in the dumps --
                # and a route plot is exactly the moment a batch of them arrives.
                #
                # *** SCOPED TO RARE CLASSES, WHICH IS WHAT MAKES A PLOT FEEL INSTANT.
                # *** is_known is read in exactly one place, the confirmed CTE, which
                # has already filtered to these classes -- an M dwarf's flag is never
                # looked at. Only 1,673 of 13,671 rows we hold are rare, and a typical
                # route reveals NONE, so this usually resolves nothing and costs
                # nothing. Unscoped it scanned a 197M-row table on every plot: 1,729 ms
                # of dead time between plotting a route and the clipboard catching up.
                #
                # Ordinary rows are left NULL on purpose. The loaders fill them in via
                # finish(), where a scan is affordable.
                resolve_known(con, "system_seen",
                              only=f"star_class IN ({_ALL_CLASSES})")
        return new

    def carrier_targets(self, pos=None, limit=3):
        """The nearest RELIABLE fleet carriers. -> rows in the shared shape.

        Reliable means `carrier.is_reliable`: parked over a year ago AND seen within
        the last 90 days. Unfiltered, this would offer carriers whose recorded position
        is years-old hearsay -- 30,262 of them have not been laid eyes on since they
        supposedly stopped -- and arriving to find empty space is the one outcome that
        makes a carrier list worthless.

        No predictions: a carrier row sets `wide_text` to the carrier's name, which the
        renderer spans across the whole prediction area. Nothing about a black hole is
        being claimed, so eight dashes would be eight small lies.
        """
        if not pos:
            return []
        with self._session() as (con, model):
            cur = con.execute(f"""
                WITH near AS (
                  SELECT c.callsign, c.carrier_name,
                         {full_name()} AS system,
                         {distance_sql('k.')} AS dist_ly,
                         c.has_universal_cartographics AS uc
                  FROM {model}.main.carrier c
                  JOIN {model}.main.system_known k ON k.system_id = c.system_id
                  JOIN {model}.main.sector sc ON sc.sector_id = k.sector_id
                  WHERE c.is_reliable
                )
                SELECT row_number() OVER (ORDER BY dist_ly) AS rank,
                       system,
                       CASE WHEN uc THEN 'CARR+UC' ELSE 'CARRIER' END AS type_label,
                       dist_ly, FALSE AS dist_approx,
                       {P_NULLS},
                       NULL::VARCHAR AS confirmed_col,
                       {ROW_CARRIER} AS row_grp,
                       -- The whole prediction area, given over to the carrier's
                       -- callsign and name. That is the only thing worth knowing once
                       -- you are in the system.
                       --
                       -- CALLSIGN FIRST, AND PADDED TO 8. It is the fixed-width half --
                       -- 2,513 of the 2,524 reliable carriers have a 7-character
                       -- callsign, 10 have 4 and one has 8 -- while names run from
                       -- "Barachiel" to "CONSTELLATION EURYALE". Putting the ragged
                       -- field first left the callsigns scattered across the width of
                       -- the table; this way the names all start in the same column and
                       -- the callsigns line up under each other. %-8s not %-7s so the
                       -- single 8-character outlier cannot shunt one row out of step.
                       printf('%-8s  %s', callsign,
                              coalesce(carrier_name, '(unnamed)')) AS wide_text,
                       callsign AS detail,
                       NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
                       NULL::DOUBLE AS x, NULL::DOUBLE AS y, NULL::DOUBLE AS z,
                       NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
                FROM near ORDER BY dist_ly LIMIT {int(limit)}""", list(pos))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def neutron_targets(self, pos=None, limit=3):
        """The nearest systems whose PRIMARY star is a neutron. -> shared row shape.

        A jet cone boost: 300% on the FSD, and because the primary IS the arrival star
        you take it without supercruising anywhere. That is the whole reason this list
        is worth three rows next to the carriers -- both answer "somewhere to go that is
        not a gamble", as against the three tables above them which are all guesses.

        *** NOT FILTERED AGAINST system_visited OR is_known, AND THAT IS DELIBERATE. ***
        Everything else on this overlay is about finding something nobody has found. A
        neutron is about GETTING somewhere: the boost works exactly as well the second
        time you use it and whether or not somebody else logged the star first. Applying
        the discovery filters here would hide the nearest boost because you already used
        it, which is precisely backwards.

        Reads main.system_neutron, which is materialised for this -- 3.4M rows instead
        of a 197.6M-row scan of system_known on every jump.
        """
        if not pos:
            return []
        with self._session() as (con, model):
            cur = con.execute(f"""
                WITH near AS (
                  SELECT {full_name()} AS system,
                         {distance_sql('k.')} AS dist_ly, k.mass_code
                  FROM {model}.main.system_neutron k
                  JOIN {model}.main.sector sc ON sc.sector_id = k.sector_id
                  WHERE k.x IS NOT NULL
                )
                SELECT row_number() OVER (ORDER BY dist_ly) AS rank,
                       system,
                       'NEUTRON' AS type_label,
                       dist_ly, FALSE AS dist_approx,
                       {P_NULLS},
                       NULL::VARCHAR AS confirmed_col,
                       {ROW_NEUTRON} AS row_grp,
                       -- A dash across the callsign/name area. A neutron has neither,
                       -- and the columns beneath that heading belong to carriers; a
                       -- blank would read as missing data rather than not-applicable.
                       '-' AS wide_text,
                       mass_code AS detail, mass_code,
                       NULL::VARCHAR AS boxel,
                       NULL::DOUBLE AS x, NULL::DOUBLE AS y, NULL::DOUBLE AS z,
                       NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
                FROM near ORDER BY dist_ly LIMIT {int(limit)}""", list(pos))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def counts(self):
        """-> dict of app-state row counts, for the status line."""
        tables = ("system_seen", "system_visited", "system_confirmed", "poi_visited")
        # One query, not four: each open costs ~175 ms and the status line is not
        # worth four of them. UNION ALL keeps it to a single scan per table.
        sql = " UNION ALL ".join(
            f"SELECT '{t}' AS t, count(*) AS n FROM {t}" for t in tables)
        with self._session() as (con, _model):
            return dict(con.execute(sql).fetchall())
