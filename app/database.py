"""All database access for the overlay. The ONLY module here containing SQL.

Two databases, and the split is a rule rather than a convention:

    elite_mapping_v2_current.duckdb   WRITTEN. Everything the app records.
    elite_mapping_v2.duckdb           READ ONLY. The model: what the galaxy is.

The model is attached `READ_ONLY` by `common.current.attach_model()`, so an accidental
write raises instead of landing. The full rationale is in ETL.md §0; the short version
is that the model is derived and fully rebuilt by `etl/`, so anything the app wrote
there would be erased by the next merge with nothing to show it had gone.

*** EVERY WRITE IS IDEMPOTENT. *** `INSERT ... WHERE NOT EXISTS` throughout, so a
replayed journal event cannot double-count.

*** SELECTION AND LABELLING ARE SQL; NUMBER FORMATTING IS NOT. *** Which rows appear,
in what order, and with what "Mass H" type label -- all decided by the query. But the
seven probabilities come out as RAW DOUBLES and `table.py` formats them, because a
number is useful to more than one caller (the threshold dash, colour, a re-sort) while
a pre-formatted string is useful only to the widget that prints it.

ONE CONNECTION, AND IT IS SHORT-LIVED: DuckDB allows one process to hold a file, so an
overlay that kept the app-state database open would lock out every loader and every
read. See the Database docstring.
"""
import contextlib
import datetime
import math
import pathlib
import sys
import threading
import time

import duckdb
import numpy

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.current import (CURRENT_DB, MODEL_DB, mass_code_sql,
                            resolve_known, sector_sql)
from .kinds import (ALL_CLASSES, BY_KEY, CAPPED, CHIME_CLASSES, CHIME_IF_PREDICTED,
                    COLUMNS as P_ALL, KINDS, RANKING, RARE)

# The connection's own name for each attached database. Module constants because every
# SQL string below interpolates the model alias, and there is exactly one of each.
MODEL_ALIAS, CURRENT_ALIAS = "model", "cur"

# What "best" means when ranking systems. THE ONLY SUCH EXPRESSION -- the Current
# sector table orders its ten rows by it, and the Adjacent sectors table picks each
# sector's destination by it, so the two can never recommend different places.
#
# *** NOT a combined probability. *** p_bh and p_wr compete for the same primary star
# -- one star cannot be both -- so they are never added, multiplied, or treated as
# independent. The honest summary of a pair of mutually exclusive outcomes is the
# larger of the two.
#
# WHICH kinds rank is `ranks` in kinds.py -- BH and WR -- and this expression is built
# from that flag, so the two cannot disagree. greatest() over one column would still be
# valid SQL if a flag were ever dropped, so the assert keeps the "mutually exclusive
# outcomes" reasoning above honest: it takes at least two to need a greatest().
assert len(RANKING) >= 2, "RANK_BY summarises competing outcomes; one is not a race"
RANK_BY = f"greatest({', '.join('p.' + c for c in RANKING)})"

# WHICH PREDICTIONS COUNT AS "RARE" for the visibility threshold below: the `rare`
# flag in kinds.py, where the reasoning for each lives. Two builders' comments refer to
# the set by this name.
RARE_COLUMNS = RARE

# A system must offer at least this much on at least ONE rare prediction to be shown.
# Applied per-column, never to a total: these are mutually exclusive outcomes for the
# same primary star and must not be summed (see RANK_BY).
MIN_RARE = 0.01

# How many of the ten rows a sector's points of interest may take before predictions
# get the rest. A cap is needed in both directions: Blaa Hypai holds 20 POI systems and
# would fill the table on its own, while a sector with none must not waste slots.
# Three is a judgement call, not a derived number -- change it here.
MAX_POI_ROWS = 3

# How many systems deep the Adjacent-sector pick is cached. One is enough to DISPLAY and
# not enough to REACT: a plot answers the pick, so the successor has to be in memory or
# it costs a re-query at the worst moment -- see App.advance_clipboard(). Ten because one
# plot often settles several at once. Costs ~3 ms: the window function already ranks the
# whole partition to find the first.
SECTOR_CANDIDATES = 10

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
# The totals row. Not a target -- you cannot fly to a sum.
ROW_TOTAL = 3
# A parked fleet carrier.
ROW_CARRIER = 4
# A whole SECTOR, summed. Like ROW_TOTAL its numbers are expected COUNTS rather than
# probabilities -- but unlike ROW_TOTAL it IS a destination, because it carries the best
# system in that sector as `copy_text`. That is the only reason the two are separate
# kinds: everything about how they render is identical.
ROW_SECTOR = 5
ROW_NEUTRON = 6
# The CATALOGUED half of a summary pair. 
ROW_TOTAL_CATALOG = 7
# A real world  STAR from a catalog (main.system_unfound) whose position falls in this sector and
# which no game system can be matched to. 
ROW_UNFOUND = 8


# ------------------------------------------------------------ probability columns
# The seven prediction columns, in kinds.py's order. ONE list, so the SELECT and the
# renderer cannot disagree about which column is which -- and since kinds.py names the
# system_predicted column and the row-dict key with the SAME string, there is no rename
# to keep in step either.
#
# These leave SQL as RAW DOUBLES; formatting belongs to table.py.
P_COLUMNS = ", ".join(P_ALL)
# ... and as typed NULLs for rows that carry no probabilities at all -- a confirmed
# find is a certainty, and a POI is not a star.
P_NULLS = ", ".join(f"NULL::DOUBLE AS {c}" for c in P_ALL)
# The same, as a dict, for the rows main.py computes rather than queries.
P_NONE = {c: None for c in P_ALL}


# ---------------------------------------------------------------- confirmed finds
# Arrival classes that mean the game has ALREADY TOLD US a rare object is there.
# Plotting a route reveals the arrival star of every hop, so a system can be a certain
# find long before anyone flies to it -- that is the whole edge this tool has.
#
# ALL OF IT COMES FROM kinds.py, which is the point: "what the table predicts" and
# "what a route plot can confirm" are the same list of objects, so they are one list.
# What is left here is the SQL that list generates.
RARE_CLASSES = ALL_CLASSES
CAPPED_KINDS = CAPPED

# At most this many capped kinds among the visible rows -- unless there are not enough
# rare ones to fill the table, in which case the cap lifts rather than leave slots
# empty. Distance ordering alone gave a list of ten neutrons: there are 1,257 of them
# against 71 black holes, so the common kinds win on proximity essentially always.
MAX_CAPPED_CONFIRMED = 3

# SQL: star_class -> the STORED classification, and the membership test.
#
# *** THIS CASE WRITES system_confirmed.kind, WHICH IS DATA. *** `key`, never `abbr`:
# the app-state database is the one thing here that cannot be rebuilt, and a kind
# renamed in flight splits its own history in two. See the header of kinds.py.
_CLASS_CASE = " ".join(
    f"WHEN star_class IN ({', '.join(repr(c) for c in k.classes)}) THEN {k.key!r}"
    for k in KINDS)
_ALL_CLASSES = ", ".join(repr(c) for c in sorted(RARE_CLASSES))
# ... and the stored kind -> what the TYPE cell shows. The one place the two
# vocabularies meet, so a confirmed row's TYPE reads the same word as the heading its
# checkmark sits under.
_ABBR_CASE = " ".join(f"WHEN kind = {k.key!r} THEN {k.abbr!r}" for k in KINDS)
# kind -> the column its checkmark belongs in, emitted with each confirmed row so the
# renderer never has to know what a star class is. That is the whole point: the same
# column reads "0.40, we think" on a prediction and "yes, definitely" on a confirmation.
_CONFIRMED_COL_CASE = " ".join(
    f"WHEN kind = {k.key!r} THEN {k.column!r}" for k in KINDS)
# Rarity rank from kinds.py's ORDER, so the sort cannot drift from the list.
_RANK_CASE = " ".join(f"WHEN kind = {k.key!r} THEN {i}" for i, k in enumerate(KINDS))


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
    -- The most-hunted classes are the most affected: essentially every confirmed
    -- black hole and Wolf-Rayet sits near a plotted route somebody else has already
    -- flown, so an empty BH column here is a true statement, not a broken query. The
    -- table is mostly neutrons, O-types, Herbigs and white dwarfs.
    --
    -- *** "NOT PREDICTED" MUST NOT BE USED AS THE FILTER. *** Hundreds of confirmed
    -- systems are in no dump AND in no prediction, because the boxel-gap enumeration
    -- is a documented lower bound; filtering on it would throw away the best rows in
    -- the table to keep the catalogued ones.
    --
    -- READS THE STORED FLAG, never the bridge. Probing staging.sys_bridge here costs
    -- 1.8 SECONDS per call -- a 197M-row scan against a cold buffer pool, with no
    -- index to fall back on -- and an indexed probe through system_known is no faster
    -- at this scale and disagrees on 21 names. Resolve once, store the answer.
    --
    -- IS NOT TRUE, not `= FALSE`: NULL means nobody has checked this row yet, and the
    -- honest default is to SHOW it. Hiding a genuine find until a loader has run makes
    -- the table wrong in the expensive direction.
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

    It matters most for carriers: 2,044 of the ~2,524 reliable ones are parked in
    hand-named systems. Nothing complains when this is wrong, because the string looks
    plausible right up until you paste it.

    Test by sector_id and NEVER by sector.is_crafted, which is TRUE for 424 real named
    sectors as well. Same rule as schema/system_all.sql.
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
    """Timing that does nothing, so Database works standalone in scripts and tests."""

    @contextlib.contextmanager
    def phase(self, name):
        yield


_NO_TIMING = _NoTiming()


class Database:
    """Reads the model, writes app state. Every SQL string in the app lives here.

    Reads go through `_rows()` (a table) or `_one()` (a single row); only a method
    running several statements in order takes a connection handle of its own.

    *** THE CONNECTION IS SHORT-LIVED, AND THAT IS THE WHOLE DESIGN. ***

    DuckDB allows exactly one process to hold a database file, so an overlay that kept
    the app-state database open for its whole session would lock out every loader in
    `etl/` and every read, including a read-only one.

    So BOTH files go back when the overlay falls idle: one connection holds both, and
    release_if_idle() closes it after a quiet spell -- which is exactly when a loader
    wants them. Rebuilding costs ~145 ms on the next request. Nothing else releases
    them, so a `duckdb` CLI against the app-state file has to wait for `--model-idle`
    seconds of stillness.
    """

    def __init__(self, timing=None):
        # *** ONE THREAD OWNS THE CONNECTION. *** DuckDB accepts a DETACH of a database
        # another cursor is reading without complaint -- verified -- so no error means no
        # guard and the invariant is asserted in _connection(). Set to the caller here
        # (startup work runs on the main thread), moved by DbWorker.claim_thread().
        self._owner = threading.get_ident()
        # The one connection, built on first use -- see _connection().
        self._con = None
        self._last_used = 0.0
        # Optional timing.Phases. The Database prices its OWN internals -- opening a
        # session, resolving is_known -- because from main.py they are invisible inside
        # one call, and they turned out to be most of it.
        self.timing = timing or _NO_TIMING
        if not MODEL_DB.exists():
            raise SystemExit(
                f"model database not found: {MODEL_DB}\n"
                f"The overlay needs it to know what is out there. It is read-only;\n"
                f"app state is written to {CURRENT_DB.name} and is unaffected.")

    def claim_thread(self, ident):
        """Hand ownership to another thread. See _owner."""
        self._owner = ident

    # WHICH METHODS WRITE. DbWorker refuses a write method in a request not declared
    # as a write, and names it. Add a writing method here or the guard will not see it.
    WRITES = frozenset({"record_arrival", "record_seen", "record_poi_visit",
                        "mark_wrong", "promote_confirmed"})

    def _connection(self):
        """The one connection, with BOTH databases attached. Built on first use.

        *** ONE THREAD TALKS TO THE DATABASE, SO ONE CONNECTION IS ENOUGH. *** The
        worker owns it, so there is nothing to amortise and nothing to coordinate.

        Attaching the 60 GiB model costs ~140 ms against ~10 ms for the app-state file,
        and it is a read-only file the app never writes, so it is attached once and
        outlives the operation rather than being re-opened per request.

        THE COST, and it is the whole reason release_if_idle() exists: while this is
        open the process holds the model read-only AND the app-state file read-write, so
        etl/ can write neither. Both go back together after a quiet spell, which is
        exactly when a loader wants them.

        `USE cur` so unqualified table names mean the app-state tables -- every query in
        this module is written that way.
        """
        # *** THE OWNERSHIP CHECK FOR THE WHOLE MODULE. *** Every read and every write
        # reaches the database through here, so one assert covers all of them.
        assert threading.get_ident() == self._owner, (
            "database opened off the owning thread -- see Database._owner")
        if self._con is None:
            with self.timing.phase("db_connect"):
                self._con = duckdb.connect()
                self._con.execute("SET memory_limit='4GB'")
                self._con.execute("SET threads=8")
                self._con.execute("SET preserve_insertion_order=false")
                self._con.execute(f"ATTACH '{MODEL_DB.as_posix()}' "
                                  f"AS {MODEL_ALIAS} (READ_ONLY)")
                self._con.execute(f"ATTACH '{CURRENT_DB.as_posix()}' "
                                  f"AS {CURRENT_ALIAS}")
                self._con.execute(f"USE {CURRENT_ALIAS}")
        self._last_used = time.monotonic()
        return self._con

    def release_if_idle(self, seconds=30.0):
        """Hand both databases back after `seconds` without a query. -> True if freed.

        The overlay is bursty: a flurry around a jump or a plot, then nothing. Holding
        the files through the quiet stretches buys nothing and blocks every loader, so
        they go back. Rebuilding costs ~145 ms, paid once on the next request.
        """
        if self._con is None or time.monotonic() - self._last_used < seconds:
            return False
        self.close()
        return True

    def close(self):
        """Detach everything. On the owning thread only."""
        if self._con is not None:
            self._con.close()
            self._con = None

    # -- running a query -----------------------------------------------------------
    def _rows(self, sql, params=()):
        """Run a SELECT; -> the result set as a list of dicts keyed by column name.

        *** THE ONE PLACE A CURSOR BECOMES PYTHON. *** Every read below returns this,
        and the dicts ARE the app's row shape: `table.py` looks up `row["p_bh"]` and
        `theme.COLUMNS` names the same strings, so a query's SELECT list is the schema
        of what reaches the screen. Nothing here renames, reorders or formats -- a
        column arrives on screen under the name the SQL gave it, or not at all.
        """
        cur = self._connection().execute(sql, list(params))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def _one(self, sql, params=()):
        """Run a SELECT of at most one row; -> that row as a tuple, or None.

        For the answers that are a fixed handful of numbers rather than a table -- a
        summary line, a lookup -- where the caller unpacks positionally and naming the
        columns would buy nothing.
        """
        return self._connection().execute(sql, list(params)).fetchone()

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
        return self._rows(f"""
                WITH {confirmed_cte()},
                scored AS (SELECT *, {dist} AS dist_ly FROM confirmed),
                -- QUOTA. The galaxy holds ~1,035 confirmed neutrons against ~69 black
                -- holes, so ordering purely by distance fills the table with the
                -- common kinds. Cap them, and let the cap LIFT when there are not
                -- enough rare ones to fill the table -- an empty slot helps nobody.
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
                    -- The STORED kind translated to the on-screen abbreviation, so
                    -- this cell reads the same word as the heading its checkmark sits
                    -- under: 'BLK HOLE' under BLK HOLE.
                    CASE {_ABBR_CASE} END                            AS type_label,
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

    def top_targets(self, sector, limit=10, pos=None):
        """The best unvisited targets in `sector`, best first. -> list of dicts.

        RANKED BY PROBABILITY, NOT DISTANCE. Within one sector everything is close, so
        the question is purely "which of these is most likely to hold something".

        Three kinds of row compete for the ten slots, in this order: points of interest
        (capped at MAX_POI_ROWS, certain finds), boxel-predicted systems, then
        catalogued systems as BACKFILL, rendered in a different colour so an inferred
        target and a merely-unscanned one never look alike.

        *** A caveat that shapes how every column should be read: EVERY p is fitted per
        (mass_code, plane_r band), and a single sector spans one band. So a sector
        offers only about FOUR distinct prediction ROWS -- one per mass code present --
        and two systems of the same mass code here are, to this model, identical. ***
        The ordering is therefore "highest mass code first"; the tiebreak does the rest
        of the visible work: expected body count, then system, so the order is
        deterministic and rows do not shuffle between refreshes.

        Anything in the CONFIRMED table is excluded here -- it must appear once, in the
        table that says it is certain, and never again among the guesses.
        """
        return self._rows(f"""
                WITH {confirmed_cte()},
                sys AS (
                  SELECT p.*, s.star_class,
                         CASE WHEN p.is_catalog THEN {ROW_CATALOG}
                              ELSE {ROW_PREDICTED} END AS row_grp
                  FROM {MODEL_ALIAS}.main.system_predicted p
                  LEFT JOIN system_visited v ON v.system = p.system
                  LEFT JOIN system_seen    s ON s.system = p.system
                  WHERE p.sector = ? AND v.system IS NULL
                    AND p.system NOT IN (SELECT system FROM confirmed)
                    -- *** THE COMMANDER TRIED TO PLOT TO IT AND WAS REFUSED. *** A
                    -- boxel prediction enumerates an index gap the Forge may never
                    -- have filled, so misses are expected and this is the only way one
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
                    -- s.star_class, not s.system: a system can be in system_seen with
                    -- COORDINATES ONLY, and a position tells us nothing about what is
                    -- there, so those rows must stay.
                    AND s.star_class IS NULL
                    -- At least one RARE prediction must clear the bar. Per-column, and
                    -- never a sum: mutually exclusive outcomes for one star.
                    AND greatest({self.RARE_MAX}) >= {MIN_RARE}
                ),
                -- Points of interest: CERTAIN finds, not predictions. system_poi is a
                -- materialised union of the two attributions -- body-level and
                -- system-level, either alone missing real POIs -- because computing it
                -- here scans system_body's 577.6M rows: 1.6 ms against seconds.
                poi_raw AS (
                  SELECT sp.system, po.poi, po.poi_class, sp.x, sp.y, sp.z
                  FROM {MODEL_ALIAS}.main.system_poi sp
                  JOIN {MODEL_ALIAS}.main.poi po ON po.poi_id = sp.poi_id
                  WHERE sp.sector = ?
                ),
                poi AS (
                  -- One row per SYSTEM: a system can hold several POIs on several
                  -- bodies, and ten slots are too few to spend on repeats of the same
                  -- destination. min() is arbitrary but stable across refreshes.
                  --
                  -- ORDERED BY DISTANCE, not by poi_class. Inside a real sector this
                  -- barely matters -- everything is within 1280 ly of everything else
                  -- -- but the 'crafted' sentinel sector holds every hand-named system
                  -- in the GALAXY, where an alphabetical order would pick three POIs
                  -- at random from 65,000 ly of space. NULLS LAST: unlocated is not
                  -- the same as near. poi_class then system break ties, so the order
                  -- stays deterministic.
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
                         NULL::DOUBLE AS p_wd,
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
                         p_neutron, p_wd,
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
                # TWO sector binds -- the `sys` CTE and the POI probe -- then the
                # position TWICE: once for the POI ordering inside the poi CTE and once
                # for the displayed distance in `ranked`. DuckDB binds positionally, so
                # this order follows the order the '?' appear in the SQL above.
                [sector, sector,
                 *(pos or (None, None, None)),
                 *(pos or (None, None, None)), limit])

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
        return self._rows(f"""
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
                FROM {MODEL_ALIAS}.main.system_unfound u
                WHERE u.sector = ?
                  -- Visited means the question was answered on the ground, whichever
                  -- way it went. Marked wrong means the commander answered it by being
                  -- refused a route -- see mark_wrong().
                  AND u.system NOT IN (SELECT system FROM system_visited)
                  AND u.system NOT IN (SELECT system FROM system_wrong)
                ORDER BY rank LIMIT {int(limit)}""",
                [*(pos or (None, None, None)), sector])

    # -- writes (app state) -------------------------------------------------------
    def mark_wrong(self, system, source, sector=None, note=None, timestamp=None):
        """Record that a system DOES NOT EXIST. -> True if this is the first time.

        Written when the commander presses SHIFT+BACKSPACE on a row: the galaxy map
        refused to plot to it, or the arrival found nothing.

        *** THIS IS A FILTER, NOT A DELETE, AND THE DISTINCTION IS THE WHOLE DESIGN. ***
        Deleting the row from system_predicted or system_unfound is wrong for two
        reasons, either of which settles it:

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
        if self._one("SELECT count(*) FROM system_wrong WHERE system = ?",
                     [system])[0]:
            return False
            # id64 IS LEFT NULL, ON PURPOSE. Resolving it means probing
            # staging.sys_bridge -- 197M rows, no index on the name, ~1.7 s -- and a
            # freeze that long on a keypress while flying is worse than a NULL in a
            # column whose own comment says NULL is normal and which nothing joins on.
        self._connection().execute(f"""
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
            # ROW_TOTAL, or ROW_TOTAL_CATALOG for the catalogued half. Both behave
            # identically -- counts rather than probabilities, off the colour gradient,
            # not somewhere you can fly -- and differ for ONE reason: colour. The
            # catalogued line takes the same blue-grey as the rows it sums.
            #
            # Neither can be selected, by construction: _paint() builds the cursor's
            # row list from `targets` alone and appends the summary lines afterwards.
            "row_grp": ROW_TOTAL_CATALOG if catalogued else ROW_TOTAL,
            "detail": None, "mass_code": None, "boxel": None,
            "confirmed_col": None, "dist_ly": None, "dist_approx": False,
            "wide_text": None, "x": None, "y": None, "z": None,
            "dist_sol": None, "star_class": None,
        })
        return row

    # The second line of each pair. SHORT, and the pool word leads: sector names reach
    # 32 characters against a 24-wide SYSTEM column, so anything appended to a name is
    # the first thing truncated away. The name is not repeated because this row sits
    # directly beneath the one that has it.
    CATALOGUED_LABEL = "  + CATALOGUED"

    def _totals_pair(self, label, where, params):
        """Run one grouped query; return [boxel row, catalogued row]. Always both.

        *** ONE QUERY GROUPED BY is_catalog, NOT TWO QUERIES. *** The two lines read the
        same columns of the same table under the same predicate; splitting them would
        double the scan to produce halves of one answer.

        BOTH ROWS ALWAYS COME BACK, zeroed when their half of the pool is empty. A line
        that vanishes at zero is the bug this pair exists to fix -- a missing line reads
        as a disagreement, where an explicit 0 reads as a fact.
        """
        by_cat = {r["is_cat"]: r for r in self._rows(f"""
            SELECT p.is_catalog AS is_cat, count(*) AS n,
                   {", ".join(f"sum(p.{c}) AS {c}" for c in P_ALL)}
            FROM {MODEL_ALIAS}.main.system_predicted p
            LEFT JOIN system_visited v ON v.system = p.system
            -- *** A REVEALED ARRIVAL CLASS TAKES THE ROW OUT OF THESE SUMS, exactly
            -- as it takes it out of the table above them. *** A prediction asks one
            -- question and the game has answered it; leaving it in a sum of "what is
            -- left here" would make the line disagree with the ten rows it sits under.
            -- Matches top_targets() and adjacent_sectors(): these three pools are one
            -- pool.
            LEFT JOIN system_seen    s ON s.system = p.system
            WHERE {where} AND v.system IS NULL AND s.star_class IS NULL
            GROUP BY 1""", params)}
        out = []
        for is_cat, text in ((False, label), (True, self.CATALOGUED_LABEL)):
            got = by_cat.get(is_cat)
            n = got["n"] if got else 0
            sums = ({c: got[c] for c in P_ALL} if got else dict(P_NONE))
            out.append(self._totals_row(text, n, sums, catalogued=is_cat))
        return out

    def sector_totals(self, sector):
        """Expected UNDISCOVERED objects of each type left in `sector`.

        -> a PAIR of rows: boxel-predicted first, catalogued second.

        A probability IS an expected count. p_bh = 0.40 on one system means 0.4 black
        holes expected there, so summing p_bh across the systems gives the expected
        number in the sector -- and unlike the per-row probabilities, these sums are
        additive and mean exactly what they look like.

        *** TWO LINES BECAUSE THERE ARE TWO POPULATIONS. *** The table above lists POI,
        boxel AND catalogued rows, so a total covering only the boxel half would
        disagree with the list it sits under -- galaxy-wide that is 215,845 systems
        counted against 2,206,986 ignored.

        Neither population is dropped and neither is folded into the other. They are
        different kinds of target -- one inferred from a gap in the Forge index, one a
        real system nobody has scanned (the catalogued half is system_known MINUS
        system_body: position known, contents not) -- and a single number would average
        two things you would act on differently.

        THE POOL IS THE STILL-OPEN SYSTEMS -- not visited, and not already classed by
        a route plot or an FSDTarget -- split by is_catalog. No MIN_RARE bar and no
        LIMIT: this counts the WHOLE sector, not the ten rows on screen, which is the
        point of showing it. The pair can therefore exceed what the table lists, and
        should -- the rows are the top ten, these are the sector.
        """
        # "SECTOR <name>", matching "REGION <name>" below. The word leads because
        # sector names reach 32 characters against a 24-wide column, so a trailing
        # label would be truncated away -- and the word saying this is not a
        # destination is the one that has to survive.
        return self._totals_pair(f"SECTOR {sector}", "p.sector = ?", [sector])

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
        different things. Summing per-sector totals within a region reproduces the
        region figure exactly, to the last decimal.

        *** THE CURRENT SECTOR IS INCLUDED, NOT SUBTRACTED. *** "The region" means the
        region. Reading the pair as "41 of 1,387 are here" is the comparison these lines
        exist for, and it only works if the larger number contains the smaller.

        Region comes the long way round, through the sector NAME: system_predicted
        carries no region_id, only the parsed sector string.
        """
        region = self._one(
            f"""SELECT r.region FROM {MODEL_ALIAS}.main.sector sc
                JOIN {MODEL_ALIAS}.main.region r ON r.region_id = sc.region_id
                WHERE sc.sector = ?""", [sector])
        # No region means the sector name is not one the model knows -- nothing to
        # summarise, as against a region that is merely empty.
        if not region:
            return None
        return self._totals_pair(
            f"REGION {region[0]}",
            f"""p.sector IN (SELECT sc.sector FROM {MODEL_ALIAS}.main.sector sc
                             WHERE sc.region_id = (SELECT sc2.region_id
                                                   FROM {MODEL_ALIAS}.main.sector sc2
                                                   WHERE sc2.sector = ?))""",
            [sector])

    def adjacent_sectors(self, sector, pos=None, limit=10):
        """The nearest OTHER sectors, with the expected objects left in each.

        Where the totals row says what is left HERE, this says what is left next door
        -- so the decision "is this sector worth staying in" can be made against
        something instead of in the abstract. Every number is an expected COUNT summed
        over the whole sector, not a probability, exactly as the totals row is.

        THE POOL IS THE SAME as sector_totals(): boxel-predicted, not catalogued, not
        visited, and not already settled by a revealed arrival class. It has to be, or
        the row you compare against would be measuring a different thing from the row
        above it.

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

        Each row carries `copy_text`: the best system IN that sector, so copying hands
        over somewhere you can actually plot a route to rather than a sector name the
        galaxy map will not accept. It also carries `candidates` -- the same ranking ten
        deep, cached on the row -- so that when a plot answers the pick, the overlay can
        hand over the next one without a query. See SECTOR_CANDIDATES.

        *** "BEST" IS RANK_BY -- THE SAME EXPRESSION THE CURRENT-SECTOR TABLE RANKS
        ON. *** So the copied system is exactly the one the sector table would offer
        once you arrived, and the two tables cannot recommend different places. Ranking
        on the SUMMED per-type probabilities instead would let neutrons and white
        dwarfs, which are numerous, outweigh the one column the project is about: it
        picks a different system in 444 of the 2,874 sectors holding a prediction, and
        is worse on greatest(p_bh, p_wr) in all 444 -- mean 0.46 down to 0.40.

        The SECTOR columns are still sums, and should be: they answer "is this sector
        worth the trip", which is a question about everything in it. Only the choice of
        SYSTEM within the winning sector is a rarity ranking.
        """
        if not pos:
            # Distance is the entire ordering; without a position there is no table.
            return []
        sums = ", ".join(f"sum({c}) AS {c}" for c in P_ALL)
        return self._rows(f"""
                WITH pool AS (
                  SELECT p.sector, p.system, p.exp_bodies,
                         {", ".join("p." + c for c in P_ALL)},
                         {RANK_BY} AS rank_score,
                         s.star_class
                  FROM {MODEL_ALIAS}.main.system_predicted p
                  LEFT JOIN system_visited v ON v.system = p.system
                  LEFT JOIN system_seen    s ON s.system = p.system
                  WHERE NOT p.is_catalog AND v.system IS NULL
                    AND p.sector IS NOT NULL
                    -- *** A SETTLED PREDICTION LEAVES THE SUMS, NOT JUST THE PICK. ***
                    -- Plotting a route rewrites NavRoute.json with the arrival class of
                    -- EVERY hop, so one plot into a neighbouring sector can answer the
                    -- question dozens of its predictions were asking. top_targets
                    -- applies this same test, and a sum that disagreed with the rows
                    -- under it would leave the plot changing nothing on screen.
                    --
                    -- s.star_class, not s.system: a system can be in system_seen with
                    -- a position and no class, and a position says nothing about what
                    -- is there.
                    --
                    -- A CLASS IS A FACT ABOUT THE SYSTEM, which is why it belongs in
                    -- the sums where system_wrong (below) does not: that one is a fact
                    -- about one commander's route plotter.
                    AND s.star_class IS NULL
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
                -- destination answer different questions. *** The sums answer "what is
                -- left in this sector" and must match what sector_totals() reports for
                -- the sector we are standing in. The pick answers "where should I go",
                -- and the Current sector table refuses to offer a system for two more
                -- reasons that apply just as much from a sector away:
                --
                --   the MIN_RARE bar     nothing here clears the threshold that makes
                --                        a row worth displaying at all.
                --   system_wrong         the commander tried to plot to it and the
                --                        game refused. One commander's refused route
                --                        is not a fact about the sector, so the sums
                --                        keep it.
                --
                -- TEN DEEP. candidates[1] is the pick; ORDER BY rn means element 2 is
                -- exactly what this query returns as the pick once element 1 is
                -- answered, which is what lets the overlay skip ahead without asking.
                best AS (
                  SELECT sector, list(system ORDER BY rn) AS candidates FROM (
                    SELECT p.sector, p.system,
                           row_number() OVER (
                             PARTITION BY p.sector
                             ORDER BY p.rank_score DESC, p.exp_bodies DESC,
                                      p.system) AS rn
                    FROM pool p
                    WHERE greatest({", ".join(f"p.{c}" for c in RARE_COLUMNS)})
                            >= {MIN_RARE}
                      -- Not applied to `agg` -- those sums have to keep matching
                      -- sector_totals(), and one commander's refused route is not a
                      -- fact about the sector.
                      AND p.system NOT IN (SELECT system FROM system_wrong)
                  ) WHERE rn <= {SECTOR_CANDIDATES}
                  GROUP BY sector
                ),
                -- INNER JOIN to best, and BEFORE the LIMIT. A sector whose every
                -- prediction is already settled has expected objects on paper and
                -- nowhere to fly, so it must not occupy one of the ten slots.
                near AS (
                  SELECT a.*, b.candidates[1] AS best_system, b.candidates,
                         {distance_sql('k.')} AS dist_ly
                  FROM agg a
                  JOIN {MODEL_ALIAS}.main.sector k ON k.sector = a.sector
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
                       {", ".join("n." + c for c in P_ALL)},
                       NULL::VARCHAR AS confirmed_col,
                       {ROW_SECTOR} AS row_grp, NULL::VARCHAR AS wide_text,
                       n.best_system AS detail, n.best_system AS copy_text,
                       n.candidates AS candidates,
                       NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
                       NULL::DOUBLE AS x, NULL::DOUBLE AS y, NULL::DOUBLE AS z,
                       NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
                FROM near n
                ORDER BY rank""", [sector, *pos])

    def sector_summary(self, sector):
        """-> (eligible, visited, settled, catalogued_excluded) for `sector`.

        `catalogued_excluded` exists so an empty table can say WHY it is empty. Only
        2,874 of 8,741 sectors hold any boxel-predicted system at all, so a blank
        overlay is the common case, not a fault -- and "0 predicted, 90 catalogued and
        excluded" is a very different message from "0 of anything here".

        `settled` is the second way a sector empties out, and it is NOT the same fact as
        `visited`: the arrival class arrived from a route plot or an FSDTarget, so the
        prediction is answered without the commander ever having flown there. Counted
        DISJOINTLY -- visited wins -- so the two can be added without double-counting.
        """
        return self._one(f"""
                SELECT count(*) FILTER (WHERE eligible),
                       count(*) FILTER (WHERE eligible AND visited),
                       count(*) FILTER (WHERE eligible AND NOT visited AND settled),
                       count(*) FILTER (WHERE p.is_catalog)
                FROM (
                  SELECT p.is_catalog,
                         NOT p.is_catalog
                           AND greatest({self.RARE_MAX}) >= {MIN_RARE} AS eligible,
                         v.system IS NOT NULL                     AS visited,
                         -- star_class, not system: system_seen holds position-only rows
                         -- and a position settles nothing.
                         s.star_class IS NOT NULL                 AS settled
                  FROM {MODEL_ALIAS}.main.system_predicted p
                  LEFT JOIN system_visited v ON v.system = p.system
                  LEFT JOIN system_seen    s ON s.system = p.system
                  WHERE p.sector = ?
                ) p""", [sector])

    def poi_in_system(self, system):
        """-> (poi_id, poi, poi_class) if the model knows a POI here, else None.

        ONE 66,548-row probe, 2.2 ms: system_poi carries the pasteable name, so the
        name is the key and no staging table is touched. It already unions the two
        attributions -- a POI pinned to a named body is recorded against the body, so
        system_known alone would miss it.

        min(poi_id) where a system holds several: arbitrary but stable across runs, the
        same rule as the poi CTE in top_targets.
        """
        return self._one(f"""
            WITH found AS (
              SELECT min(sp.poi_id) AS poi_id
              FROM {MODEL_ALIAS}.main.system_poi sp WHERE sp.system = ?
            )
            SELECT f.poi_id, p.poi, p.poi_class
            FROM found f JOIN {MODEL_ALIAS}.main.poi p ON p.poi_id = f.poi_id""",
            [system])

    # -- writes (app state only) ---------------------------------------------------
    # id64 is left NULL by every write here ON PURPOSE. Resolving it means probing a
    # 197M-row name bridge, which is seconds of work -- fine in a loader, not inside a
    # UI callback on every jump. `etl/load_system_*.py` backfill it later; NULL is a
    # documented, expected value on all four tables.
    def record_arrival(self, system, timestamp=None):
        """Record an arrival: the visit, and the POI if there is one.

        -> (was_new_system, poi_label_or_None)

        Both writes belong to the same journal event, so they go in together and the
        caller gets one answer. Idempotent: a replayed event changes nothing but the
        timestamp.
        """
        con = self._connection()
        new = not self._one(
            "SELECT count(*) FROM system_visited WHERE system = ?", [system])[0]
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
        already = self._one(
            "SELECT count(*) FROM poi_visited WHERE system = ?", [system])[0]
        if not already:
            hit = self.poi_in_system(system)
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
        """Record arrival classes revealed WITHOUT visiting. -> names of new systems.

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
            return []
        # A HANDLE, because this is five statements over two temp tables that later
        # ones read. Everything single-statement goes through _rows()/_one().
        con = self._connection()
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
        # THE NAMES, NOT A COUNT. The caller needs to know WHICH systems were
        # new, because "this route revealed a black hole" and "this route runs
        # past a black hole you confirmed last week" are different events and
        # only the first one is worth a sound. Read before the INSERT below, so
        # this is genuinely "not seen until now".
        new = [r[0] for r in con.execute(
            """SELECT s.system FROM seen_src s WHERE NOT EXISTS
               (SELECT 1 FROM system_seen t WHERE t.system = s.system)"""
            ).fetchall()]
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
            # looked at, and a typical route reveals no rare class at all, so this
            # usually resolves nothing. Unscoped it scans a 197M-row table on every
            # plot: 1,729 ms between plotting a route and the clipboard catching up.
            #
            # Ordinary rows are left NULL on purpose. The loaders fill them in via
            # finish(), where a scan is affordable.
            resolve_known(con, "system_seen",
                          only=f"star_class IN ({_ALL_CLASSES})")
        return new

    def predicted_boxel(self, names):
        """Which of `names` are BOXEL PREDICTIONS of ours? -> set of names.

        `is_catalog = FALSE` is the whole test. The table's two populations split on
        that flag: TRUE means a real catalogued system nobody has detail-scanned, FALSE
        means a system implied by a gap in the Stellar Forge boxel index that appears in
        NO dump. So FALSE is precisely "we said this was here, and nobody knows it" --
        which is what makes a reveal there a confirmed GUESS rather than a fact
        somebody else already had.

        No is_known probe, deliberately. That would be a scan of the 197M-row bridge,
        1,729 ms, to re-derive what is_catalog already states by construction.
        """
        names = [n for n in names if n]
        if not names:
            return set()
        marks = ", ".join("?" * len(names))
        return {r["system"] for r in self._rows(f"""
            SELECT system FROM {MODEL_ALIAS}.main.system_predicted
            WHERE system IN ({marks}) AND is_catalog = FALSE""", names)}

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
        return self._rows(f"""
                WITH near AS (
                  -- carrier_position, not system_known: resolving 2,524 carriers
                  -- through 200.7M rows has nothing to probe on and scans the lot
                  -- (1,440 ms warm, 5,224 cold, every jump) against 1.8 ms here. The
                  -- pasteable name is pre-composed, so no full_name() and no join.
                  SELECT c.callsign, c.carrier_name, cp.system,
                         {distance_sql('cp.')} AS dist_ly,
                         c.has_universal_cartographics AS uc
                  FROM {MODEL_ALIAS}.main.carrier c
                  JOIN {MODEL_ALIAS}.main.carrier_position cp ON cp.callsign = c.callsign
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
                       -- CALLSIGN FIRST, AND PADDED TO 8. It is the fixed-width half
                       -- -- almost every callsign is 7 characters -- while names run
                       -- from "Barachiel" to "CONSTELLATION EURYALE", so leading with
                       -- the ragged field would scatter the callsigns across the
                       -- table. %-8s not %-7s, so the single 8-character outlier
                       -- cannot shunt one row out of step.
                       printf('%-8s  %s', callsign,
                              coalesce(carrier_name, '(unnamed)')) AS wide_text,
                       callsign AS detail,
                       NULL::VARCHAR AS mass_code, NULL::VARCHAR AS boxel,
                       NULL::DOUBLE AS x, NULL::DOUBLE AS y, NULL::DOUBLE AS z,
                       NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
                FROM near ORDER BY dist_ly LIMIT {int(limit)}""", list(pos))

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

        Reads main.system_neutron, materialised for this -- 3.4M rows instead of a
        197.6M-row scan of system_known on every jump. The nearest are picked from the
        coordinates ALONE and named afterwards; see the comment on the query.
        """
        if not pos:
            return []
        return self._rows(f"""
                -- RANK FIRST, JOIN AFTER. The name needs `sector`, and joining all
                -- 3.4M rows before the ORDER BY builds 3.4M names to keep three: the
                -- scan is 30 ms, the join the other 250. Coordinates rank alone.
                WITH nearest AS (
                  SELECT k.sector_id, k.system_in_sector, k.mass_code, k.x, k.y, k.z,
                         {distance_sql('k.')} AS dist_ly
                  FROM {MODEL_ALIAS}.main.system_neutron k
                  WHERE k.x IS NOT NULL
                  ORDER BY dist_ly LIMIT {int(limit)}
                ),
                near AS (
                  SELECT {full_name()} AS system, k.dist_ly, k.mass_code,
                         k.x, k.y, k.z
                  FROM nearest k
                  JOIN {MODEL_ALIAS}.main.sector sc ON sc.sector_id = k.sector_id
                )
                SELECT row_number() OVER (ORDER BY dist_ly) AS rank,
                       system,
                       -- The same word the NEUTRON column heading uses: these cones
                       -- are that kind of star, and one abbreviation covers both.
                       {BY_KEY['NEUTRON'].abbr!r} AS type_label,
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
                       x, y, z,
                       NULL::DOUBLE AS dist_sol, NULL::VARCHAR AS star_class
                FROM near ORDER BY dist_ly LIMIT {int(limit)}""", list(pos))

    def promote_confirmed(self, only=None):
        """Copy every rare sighting in system_seen into system_confirmed. -> inserted.

        *** system_seen IS A SIGHTING LOG; system_confirmed IS THE FIND LOG. *** The
        difference matters because they are not the same lifetime. system_seen is
        derived: it holds whatever the journal has told us lately, and its rows lose
        their meaning the moment a rebuild changes what counts as rare or a name stops
        parsing. system_confirmed is standalone by design -- name, class, mass code AND
        coordinates on the row -- so a find survives all of that. Its own comment calls
        it the least reproducible table in the project.

        MERGE, NEVER DROP, on the natural key `system`: insert what is missing, leave
        everything already there untouched. That is what makes it safe to run on every
        start, and a full pass self-healing where a one-off migration would fall behind
        the moment anything changed.

        `found_date` comes from system_seen.first_seen_utc, NOT from today: stamping
        historic finds with today's date would destroy the one thing the column is for.
        NULL only where the sighting predates that column.

        `only` restricts to a list of names, for the promotion that rides a route plot.
        None means the whole table, which is what startup does.
        """
        where = ""
        params = []
        if only is not None:
            only = [n for n in only if n]
            if not only:
                return 0
            where = f"AND s.system IN ({', '.join('?' * len(only))})"
            params = list(only)
        cur = self._connection().execute(f"""
            INSERT INTO system_confirmed
                (system, kind, star_class, mass_code, x, y, z, id64, sector,
                 was_exact, was_predicted, visited, found_date, is_known)
            SELECT src.system,
                   src.kind,
                   src.star_class,
                   {mass_code_sql('src.system')},
                   src.x, src.y, src.z, src.id64, src.sector,
                   -- was_exact: TRUE when the game gave us coordinates. A route
                   -- plot carries StarPos for every hop; a bare FSDTarget carries
                   -- the class alone. For an app-written row FALSE therefore means
                   -- NO coordinates at all rather than a boxel centroid standing
                   -- in -- a stronger reason to re-fix before flying, not a weaker
                   -- one. See the column comment.
                   src.x IS NOT NULL AS was_exact,
                   -- *** THE COLUMN THAT SCORES THE MODEL. *** is_catalog = FALSE
                   -- is the boxel-predicted half of system_predicted: systems in NO
                   -- dump that the gap enumeration proposed. Exactly "we called
                   -- this one". The catalogued half is by construction already
                   -- known, so it is not a prediction being scored.
                   p.system IS NOT NULL AS was_predicted,
                   EXISTS (SELECT 1 FROM system_visited v
                           WHERE v.system = src.system) AS visited,
                   cast(src.first_seen_utc AS DATE) AS found_date,
                   src.is_known
            FROM (
                SELECT s.system, s.star_class, s.x, s.y, s.z, s.id64, s.sector,
                       s.is_known, s.first_seen_utc,
                       CASE {_CLASS_CASE} ELSE NULL END AS kind
                FROM system_seen s
                WHERE s.star_class IN ({_ALL_CLASSES})
                  AND NOT EXISTS (SELECT 1 FROM system_confirmed c
                                  WHERE c.system = s.system)
                  {where}
            ) src
            LEFT JOIN {MODEL_ALIAS}.main.system_predicted p
                   ON p.system = src.system AND p.is_catalog = FALSE
            WHERE src.kind IS NOT NULL""", params)
        # DuckDB reports affected rows on the cursor for INSERT.
        got = cur.fetchall()
        return int(got[0][0]) if got else 0

    def neutron_corridor(self, start, dest, pad=600.0):
        """Neutrons in a corridor from `start` to `dest`. -> (names, Nx3 float array).

        *** NOT ALL 3.4 MILLION. *** A galaxy-wide fetch is 3.4M rows into Python on
        every plot; the router only ever expands nodes that lie roughly between the two
        ends, so the rest is pure cost. The filter is

            dist(start) + dist(dest) <= direct + pad

        which is a PROLATE SPHEROID with the two systems as its foci -- the natural
        shape for "somewhere along the way", and one line of SQL.

        *** pad IS AN ABSOLUTE DETOUR ALLOWANCE, NOT A PERCENTAGE. *** A proportional
        slack of 15% permits a 3,423 ly detour on a 22,820 ly run, which selects 654,108
        of the 3.4M neutrons and costs 789 ms. The spheroid fattens with the SQUARE of
        the allowance while the useful corridor does not, so a fixed few hundred light
        years keeps a long route as cheap as a short one.

        Too tight and a route that exists is reported missing, so the caller widens
        before believing a failure. A corridor is a statement about where we LOOKED,
        never about the galaxy.

        Reads main.system_neutron, materialised for exactly this kind of question.
        """
        sx, sy, sz = start
        dx, dy, dz = dest
        budget = math.dist((sx, sy, sz), (dx, dy, dz)) + pad
        rows = self._rows(f"""
            SELECT {full_name()} AS system, k.x, k.y, k.z
            FROM {MODEL_ALIAS}.main.system_neutron k
            JOIN {MODEL_ALIAS}.main.sector sc ON sc.sector_id = k.sector_id
            WHERE k.x IS NOT NULL
              AND sqrt(pow(k.x - ?, 2) + pow(k.y - ?, 2) + pow(k.z - ?, 2))
                + sqrt(pow(k.x - ?, 2) + pow(k.y - ?, 2) + pow(k.z - ?, 2)) <= ?""",
            [sx, sy, sz, dx, dy, dz, budget])
        names = [r["system"] for r in rows]
        xyz = (numpy.array([[r["x"], r["y"], r["z"]] for r in rows], dtype=float)
               if rows else numpy.empty((0, 3)))
        return names, xyz

    def counts(self):
        """-> dict of app-state row counts, for the status line."""
        tables = ("system_seen", "system_visited", "system_confirmed", "poi_visited")
        # One query, not four: UNION ALL keeps it to a single scan per table.
        sql = " UNION ALL ".join(
            f"SELECT '{t}' AS t, count(*) AS n FROM {t}" for t in tables)
        return {r["t"]: r["n"] for r in self._rows(sql)}
