"""SEED input/system_catalog_alias.parquet -- which catalogue names are the same star.

ONE-TIME SEEDER, per ETL.md rule 2: writes only the PARQUET, refuses if it exists, and
never touches the `system_catalog_alias` table (that is
etl/load_system_catalog_alias.py). There is deliberately no --force -- once seeded the
file is authoritative and hand-editable, and a cross-identification is exactly the kind
of thing you correct by hand when SIMBAD disagrees with a 1918 Durchmusterung.

*** WHY. *** `system_catalog.system_id` was resolved by exact NAME match, so a NULL
conflated two very different facts: "Frontier did not ship this star" and "Frontier
shipped it under a different catalogue's name". The second is the common case --
measured over Hipparcos, the game names a star HIP inside ~1000 ly and HD beyond it, and
98,421 of 118,218 HIP stars are in the game under exactly one of HIP/HD/BD/CD/CPD. These
edges let the loader walk from a name we hold to the name Frontier actually used.

*** THE SECOND OF TWO BUILDERS THAT READ THE NETWORK. *** Same rationale as
build_system_catalog.py: these catalogues are astronomy, not an Elite data source, they
change once a decade, and mirroring them into a 60 GiB database to read them straight
back out would buy nothing. Downloads are CACHED in raw/catalog/ so a re-run after a
failure resumes instead of refetching.

VizieR's TAP endpoint returns 503 often enough to be useless here; the ASU (asu-tsv)
interface serves the same tables and is what this uses.

SOURCES -- every edge is a cross-ID the catalogue itself publishes, never a positional
match we computed. Ordered MOST AUTHORITATIVE FIRST, because a duplicate edge keeps the
first source that produced it:

  hip_main  I/239/hip_main   HIP -> HD, BD, CoD, CPD   Hipparcos, modern and vetted
  tyc2      I/259/tyc2       TYC -> HIP                Tycho-2
  bsc       V/50/catalog     HR  -> HD, SAO, DM        Bright Star Catalogue, 5th ed.
  cns3      V/70A/catalog    GJ  -> HD, DM, LHS        CNS3 (preliminary 3rd ed.)
  sao       I/131A/sao       SAO -> HD, DM
  hd        III/135A/catalog HD  -> DM                  Henry Draper
  lhs       I/87B/catalog    LHS -> DM                  bare zone:num, prefix inferred
  nltt      I/98A/catalog    NLTT-> DM, LP              same file both catalogues come from

*** TWO OF THE SOURCES POINT AT A GAME NAME RATHER THAN A CATALOGUE NAME, AND THEY ARE
THE ONLY WAY TO REACH THE BRIGHT STARS. *** Frontier names its brightest systems Sirius,
Alpha Centauri, 61 Cygni -- proper, Bayer and Flamsteed names, which are not catalogue
designations and therefore cannot appear in system_catalog at all. No amount of
catalogue-to-catalogue linking reaches them: every edge above has both feet inside a
catalogue. These two put one foot in the game:

  bayer     IV/27A/catalog   HD/HR/HIP -> the Bayer or Flamsteed name, RENDERED into the
                             spelling the galaxy map uses ("alf Cen" -> "Alpha Centauri",
                             "61 Cyg" -> "61 Cygni") and kept only if that exact string is
                             a hand-named system in system_known.
  position  I/239/hip_main   THE ONE SOURCE THAT IS NOT A PUBLISHED CROSS-ID. Hipparcos
                             astrometry converted into game coordinates and matched to a
                             hand-named system SITTING ON THE SAME SPOT. Fenced hard --
                             see POSITIONAL below -- because a coincidence here would
                             assert that two unrelated stars are one.
  simbad_x  SIMBAD TAP       CATALOGUE name -> its other catalogue names. The pass above
                             asks only about names the GAME uses, which by construction
                             skips every game system already named after a catalogue --
                             so a star the game ships as "LHS 3558" resolves that row and
                             leaves its HIP row unlinked. This closes that blind spot.
  kepler    NASA archive     KOI number <-> the Kepler-NNN name of the same star. The
                             game uses one or the other and there is no rule to which,
                             so without this a system shipped as "Kepler-244" reads as
                             absent while its KOI row sits unresolved beside it.
  simbad    SIMBAD TAP       every game name that is NOT a catalogue designation, looked
                             up as an IDENTIFIER. SIMBAD knows "Wolf 359" and "NAME
                             Sirius" and returns the same star's HD/HIP/HR/GJ/LHS/NLTT/TYC
                             ids; those become edges. This is prefix-agnostic on purpose
                             -- it reaches survey names, variable-star names and exoplanet
                             host names without a rule for each, and simply returns
                             nothing for Frontier's ~20,000 invented names.

The RENDERING for Bayer names is a genitive table (88 constellations) plus a Greek-letter
table, and it is checked the same way as everything else: a rendered name that is not in
system_known is dropped, so a wrong genitive costs a missing edge, never a wrong one.

*** TWO FILTERS, AND BOTH ARE THE ERROR CHECK. ***

1. BOTH ENDPOINTS MUST EXIST IN system_catalog. A name this script renders wrongly matches nothing and drops out, so
a rendering bug shows up as a missing edge rather than as a wrong identity -- and the
per-source counts printed at the end are what make it visible. The name universe is read
from input/system_catalog.parquet, not from the database: this script needs no lock and
does not care whether the table has been loaded.

2. NO NAME MAY BE CLAIMED BY MORE THAN {MAX} STARS WITHIN ONE SOURCE COLUMN. A
   designation identifies ONE star, so a column asserting the same partner for dozens of
   different stars is not publishing an identity, it is publishing a footnote. This
   caught a real one on the first run: CNS3's LHS column carries the literal value `6` on
   65 different stars, which chained 159 unrelated catalogue names -- 61 Gliese, 17 HIP,
   17 TYC, 15 SAO -- onto the single game system `Gliese 452.3`. Nothing in filter 1 could
   see it: every endpoint was a real name.

   *** THE THRESHOLD IS MEASURED, NOT GUESSED. *** Across all 16 source columns, 2,050,826
   partner names are claimed by exactly one star, 4,371 by two (genuine close doubles the
   catalogues split differently), 17 by three or four -- and then nothing at all until 63.
   The gap is the whole justification: a cut anywhere in 5..62 keeps every real double and
   drops the one defect.

RENDERING IS THE WHOLE JOB. The catalogues spell their cross-IDs their own way and the
game spells them differently again; `system_catalog.system` is the game's spelling and is
the only thing worth matching. Two shapes need candidate lists rather than one answer:
  * a Durchmusterung with a component letter ("CP-24 1686A") may be in the game with or
    without it, so both are offered;
  * a BARE zone:num ("-37:15492", from LHS and NLTT) does not say WHICH Durchmusterung
    owns the zone, so BD, CD and CPD are all offered. The both-endpoints-exist filter
    picks the real one; a row that somehow matched two is dropped as ambiguous.

*** POSITIONAL MATCHING, AND WHY IT IS ALLOWED EXACTLY ONCE. *** Every other source here
is somebody publishing "these two names are one star". The positional source instead says
"a star we can place to a tenth of a light year and a hand-named game system are in the
same place, so they are the same object". That is weaker, and it is fenced accordingly:

  * PARALLAX SNR >= 10 and inside 200 ly. Beyond that the distance error exceeds the
    spacing between systems and the match means nothing -- at 1,000 ly a 10% parallax
    error is 100 ly of slop against a ~4 ly mean separation.
  * SEPARATION < 1 ly against the NEAREST hand-named system, and that system must be the
    only candidate within 3 ly. A tie is dropped rather than guessed.
  * The game system must NOT already be a catalogue name (those resolve by name) and the
    HIP row must NOT already resolve.

It exists because the residue it clears is not noise: Barnard''s Star, Lalande 21185,
Ross 128, Kapteyn''s Star -- the nearest stars in the sky, which the game names after
Luyten, Ross, Groombridge and Struve, catalogues this project does not hold. They read as
"Frontier did not ship HIP 87937" when Frontier shipped it as Barnard''s Star.

Usage:  python etl/build_system_catalog_alias.py   # refuses if the parquet exists
"""
import sys
import pathlib
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import re

import duckdb
from common.db import ROOT, INPUT, connect

# See filter 2 in the module docstring: measured, and the distribution has a hole from 5
# to 62, so anything in that range behaves identically on today's sources.
MAX_CLAIMS = 4

OUT = INPUT / "system_catalog_alias.parquet"
CATALOG = INPUT / "system_catalog.parquet"
CACHE = ROOT / "raw" / "catalog"
ASU = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"
# The NASA Exoplanet Archive TAP, the one non-CDS service here. It takes its ADQL
# in the query string rather than a POST body, hence fetch_url() beside fetch().
NASA_KOI = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"

if OUT.exists():
    sys.exit("{} already exists and is AUTHORITATIVE (hand-editable) -- refusing to "
             "overwrite.\nTo apply it:  python etl/load_system_catalog_alias.py\n"
             "For a genuine fresh seed, delete it first.".format(OUT))
if not CATALOG.exists():
    sys.exit("{} is missing -- seed it first:\n  python etl/build_system_catalog.py"
             .format(CATALOG))


# ---------------------------------------------------------------------------------
# NAME RENDERERS. Each returns a SQL expression producing a LIST of candidate game
# names for one source column; [] or NULL entries are harmless, the join drops them.
# ---------------------------------------------------------------------------------
def _num(col):
    """A plain integer id, zero-padding and blanks removed: ' 00123 ' -> '123'."""
    return "CAST(TRY_CAST(trim({}) AS BIGINT) AS VARCHAR)".format(col)


def one(prefix, col):
    """Single candidate: '<prefix> <number>'. NULL when the column is blank."""
    return ("CASE WHEN TRY_CAST(trim({c}) AS BIGINT) IS NOT NULL "
            "THEN ['{p} ' || {n}] ELSE [] END".format(c=col, p=prefix, n=_num(col)))


def _dm_name(pfx, signzone, num):
    """Assemble a Durchmusterung name in game spelling: BD+56 1773, CD-49 14337."""
    return "{p} || {sz} || ' ' || {n}".format(p=pfx, sz=signzone, n=num)


def _with_and_without_component(pfx, signzone, num):
    """Both spellings of a component: 'BD+24 3803B' and 'BD+24 3803'.

    The game splits some multiple stars the catalogue lists once, and vice versa, so
    which of the two exists is not predictable -- offer both and let the join decide.
    """
    bare = "regexp_replace({}, '[A-Za-z]+$', '')".format(num)
    return "[{}, {}]".format(_dm_name(pfx, signzone, num),
                             _dm_name(pfx, signzone, bare))


def dm_prefixed(col):
    """A DM field that CARRIES its catalogue: 'BD+82  748', 'CD-4914337', 'CP-54   19'.

    Fixed layout: 2 chars of catalogue, then sign, then a 2-digit zone, then the number
    -- which is why 'CD-4914337' parses at all. 'CP' is the Cape Photographic, which the
    game writes CPD.
    """
    s = "trim({})".format(col)
    pfx = ("CASE substr({s}, 1, 2) WHEN 'BD' THEN 'BD' WHEN 'CD' THEN 'CD' "
           "WHEN 'CP' THEN 'CPD' END".format(s=s))
    signzone = "substr({s}, 3, 3)".format(s=s)
    num = "trim(substr({s}, 6))".format(s=s)
    return ("CASE WHEN {s} <> '' AND {p} IS NOT NULL AND {n} <> '' THEN {cands} "
            "ELSE [] END".format(s=s, p=pfx, n=num,
                                 cands=_with_and_without_component(pfx, signzone, num)))


def dm_bare(col):
    """A DM field with NO catalogue: '-37:15492', '+43:00044A'.

    The zone alone does not identify the catalogue -- BD, CD and CPD share the southern
    zones at their boundaries -- so all three are offered and the both-endpoints-exist
    filter resolves it. Numbers here are zero-padded and must not stay that way.
    """
    s = "trim({})".format(col)
    signzone = "split_part({s}, ':', 1)".format(s=s)
    raw = "split_part({s}, ':', 2)".format(s=s)
    # Strip leading zeros without eating a lone '0'. DuckDB's regex engine is RE2 and
    # has no lookahead, so this is ltrim + a guard rather than '^0+(?=.)'.
    num = ("CASE WHEN ltrim({r}, '0') = '' THEN '0' ELSE ltrim({r}, '0') END"
           .format(r=raw))
    cands = [_with_and_without_component("'{}'".format(pfx), signzone, num)
             for pfx in ("BD", "CD", "CPD")]
    return ("CASE WHEN regexp_matches({s}, '^[+-][0-9]{{2}}:[0-9]+[A-Za-z]?$') "
            "THEN list_concat(list_concat({a}, {b}), {c}) ELSE [] END"
            .format(s=s, a=cands[0], b=cands[1], c=cands[2]))


def lp_or_dm(col):
    """I/98A's Name column mixes both shapes: '591-212' is LP, '-75:86' is a DM."""
    s = "trim(replace({}, '*', ''))".format(col)
    lp = ("'LP ' || regexp_replace({s}, '\\s*-\\s*', '-')".format(s=s))
    return ("CASE WHEN regexp_matches({s}, '^[0-9]+\\s*-\\s*[0-9]+$') THEN [{lp}] "
            "ELSE {dm} END".format(s=s, lp=lp, dm=dm_bare(col)))


def gliese(col):
    """CNS3 spells one numbering space four ways; the game calls three of them Gliese.

    Same rule as build_system_catalog.py, and it has to stay the same rule: 'Gl 695',
    'NN 3273' and 'Wo 9229' are all 'Gliese n' in game, only 'GJ n' keeps its prefix.
    """
    s = "trim({})".format(col)
    tail = "trim(substr({s}, 4))".format(s=s)
    return ("CASE WHEN regexp_matches({s}, '^(Gl|NN|GJ|Wo) ') THEN "
            "[CASE WHEN {s} LIKE 'GJ %' THEN 'GJ ' ELSE 'Gliese ' END || {t}] "
            "ELSE [] END".format(s=s, t=tail))


def tyc(a, b, c):
    """Tycho-2 is three numbers: 'TYC 149-1079-1'."""
    return ("CASE WHEN trim({a}) <> '' THEN ['TYC ' || trim({a}) || '-' || trim({b}) "
            "|| '-' || trim({c})] ELSE [] END".format(a=a, b=b, c=c))


# ---------------------------------------------------------------------------------
# ONE ENTRY PER SOURCE: (tag, vizier table, out columns, own-name expr, {label: expr}).
# The own name is single-valued -- it is the catalogue's own id -- and each labelled
# expression is a LIST of candidate names for the star it cross-identifies.
# ---------------------------------------------------------------------------------
SOURCES = [
    ("hip_main", "I/239/hip_main", "HIP,HD,BD,CoD,CPD", "'HIP ' || " + _num("HIP"),
     {"HD": one("HD", "HD"),
      # hip_main writes a DM as one letter of catalogue then the zone: 'B+00 5077'.
      "BD": ("CASE WHEN trim(BD) <> '' THEN [{}] ELSE [] END".format(
          _dm_name("'BD'", "substr(trim(BD), 2, 3)", "trim(substr(trim(BD), 5))"))),
      "CoD": ("CASE WHEN trim(CoD) <> '' THEN [{}] ELSE [] END".format(
          _dm_name("'CD'", "substr(trim(CoD), 2, 3)", "trim(substr(trim(CoD), 5))"))),
      "CPD": ("CASE WHEN trim(CPD) <> '' THEN [{}] ELSE [] END".format(
          _dm_name("'CPD'", "substr(trim(CPD), 2, 3)", "trim(substr(trim(CPD), 5))")))},
     "TRY_CAST(trim(HIP) AS BIGINT) IS NOT NULL"),

    ("tyc2", "I/259/tyc2", "TYC1,TYC2,TYC3,HIP", None,
     {"HIP": one("HIP", "HIP")},
     "TRY_CAST(trim(TYC1) AS BIGINT) IS NOT NULL"),

    ("bsc", "V/50/catalog", "HR,HD,SAO,DM", "'HR ' || " + _num("HR"),
     {"HD": one("HD", "HD"), "SAO": one("SAO", "SAO"), "DM": dm_prefixed("DM")},
     "TRY_CAST(trim(HR) AS BIGINT) IS NOT NULL"),

    ("cns3", "V/70A/catalog", "Name,HD,DM,LHS", None,
     {"HD": one("HD", "HD"), "DM": dm_prefixed("DM"), "LHS": one("LHS", "LHS")},
     "regexp_matches(trim(Name), '^(Gl|NN|GJ|Wo) ')"),

    ("sao", "I/131A/sao", "SAO,HD,DM", "'SAO ' || " + _num("SAO"),
     {"HD": one("HD", "HD"), "DM": dm_prefixed("DM")},
     "TRY_CAST(trim(SAO) AS BIGINT) IS NOT NULL"),

    ("hd", "III/135A/catalog", "HD,DM", "'HD ' || " + _num("HD"),
     {"DM": dm_prefixed("DM")},
     "TRY_CAST(trim(HD) AS BIGINT) IS NOT NULL"),

    ("lhs", "I/87B/catalog", "LHS,Name", "'LHS ' || " + _num("LHS"),
     {"Name": dm_bare("Name")},
     "TRY_CAST(trim(LHS) AS BIGINT) IS NOT NULL"),

    # *** NLTT'S NUMBER IS THE RECORD NUMBER *** -- I/98A has no NLTT column, the
    # catalogue is ordered by it. Validated in build_system_catalog.py against SIMBAD.
    ("nltt", "I/98A/catalog", "recno,Name", "'NLTT ' || " + _num("recno"),
     {"Name": lp_or_dm("Name")},
     "TRY_CAST(trim(recno) AS BIGINT) IS NOT NULL"),
]
# The own-name expression for these two is not a plain integer id.
OWN_NAME = {"tyc2": tyc("TYC1", "TYC2", "TYC3"), "cns3": gliese("Name")}


def fetch(tag, table, out):
    """Download one catalogue's cross-ID columns to raw/catalog/xid_<tag>.tsv, or reuse.

    Three tries, for the same reason build_system_catalog.py takes three: a transient
    failure on a public academic service two sources into an eight-source run should not
    cost the two that already succeeded. The cache is the real protection.
    """
    path = CACHE / "xid_{}.tsv".format(tag)
    if path.exists() and path.stat().st_size > 0:
        print("  {:<9} cached  {:>12,} bytes".format(tag, path.stat().st_size))
        return path
    url = "{}?-source={}&-out={}&-out.max=unlimited".format(
        ASU, urllib.parse.quote(table), urllib.parse.quote(out))
    t0 = time.time()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=1800) as r:
                path.write_bytes(r.read())
            break
        except Exception as exc:                                       # noqa: BLE001
            if attempt == 2:
                raise SystemExit("  {}: download failed after 3 tries -- {}"
                                 .format(tag, exc))
            print("  {:<9} retry {} after {}".format(tag, attempt + 1, exc), flush=True)
            time.sleep(10)
    print("  {:<9} fetched {:>12,} bytes  {:>6.1f}s"
          .format(tag, path.stat().st_size, time.time() - t0))
    return path


def fetch_url(tag, service, query):
    """Cache one TAP query to raw/catalog/<tag>.csv. Same contract as fetch()."""
    path = CACHE / "{}.csv".format(tag)
    if path.exists() and path.stat().st_size > 0:
        print("  {:<9} cached  {:>12,} bytes".format(tag, path.stat().st_size))
        return path
    url = service + "?" + urllib.parse.urlencode({"query": query, "format": "csv"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=900) as r:
                path.write_bytes(r.read())
            break
        except Exception as exc:                                       # noqa: BLE001
            if attempt == 2:
                raise SystemExit("  {}: download failed -- {}".format(tag, exc))
            time.sleep(10)
    print("  {:<9} fetched {:>12,} bytes".format(tag, path.stat().st_size))
    return path


def header_skip(path):
    """How many lines precede the header row.

    ASU prefixes every response with a variable-length '#'-commented preamble, and the
    two rows AFTER the header are units and a dashed rule. Counting the preamble here
    beats hardcoding a skip that changes with the service's mood; the units and rule
    rows are dropped downstream by each source's numeric filter.
    """
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            if line.strip() and not line.startswith("#"):
                return i
    raise SystemExit("{}: no header row -- download looks empty".format(path))


CACHE.mkdir(parents=True, exist_ok=True)
print("downloading {} cross-ID sources to {} ...".format(len(SOURCES), CACHE), flush=True)
paths = {tag: fetch(tag, table, out) for tag, table, out, _, _, _ in SOURCES}

# In-memory: this builder writes a parquet and never a table, so it needs no database
# and takes no lock. The name universe comes from the authoritative parquet.
con = duckdb.connect()
con.execute("SET preserve_insertion_order=false")
con.execute("CREATE TABLE names AS SELECT DISTINCT system FROM '{}'"
            .format(CATALOG.as_posix()))
n_names = con.execute("SELECT count(*) FROM names").fetchone()[0]
print("\nname universe: {:,} catalogue names from {}".format(n_names, CATALOG.name))

print("\nrendering edges ...", flush=True)
parts = []
for tag, table, out, own, xids, keep in SOURCES:
    src = ("read_csv('{}', delim='\t', skip={}, header=true, all_varchar=true, "
           "quote='')".format(paths[tag].as_posix(), header_skip(paths[tag])))
    own_expr = OWN_NAME.get(tag, "[{}]".format(own) if own else None)
    if own_expr is None:
        raise SystemExit("{}: no own-name expression".format(tag))
    for label, cand in xids.items():
        # UNNEST both sides: the own name is a 1-element list, the cross-ID may offer
        # several spellings. Only pairs where BOTH names exist survive the joins.
        con.execute("""CREATE OR REPLACE TEMP TABLE raw_e AS
            WITH r AS (SELECT unnest({own}) AS a, unnest({cand}) AS b
                       FROM {src} WHERE {keep})
            SELECT DISTINCT least(a, b) AS system_a, greatest(a, b) AS system_b,
                            r.a AS own, r.b AS partner
            FROM r JOIN names na ON na.system = r.a JOIN names nb ON nb.system = r.b
            WHERE r.a IS NOT NULL AND r.b IS NOT NULL AND r.a <> r.b"""
                    .format(own=own_expr, cand=cand, src=src, keep=keep))
        # Filter 2: a partner name claimed by too many stars is a footnote, not an
        # identity. Dropped LOUDLY -- a silent drop here would look like a rendering bug.
        junk = con.execute("""SELECT partner, count(DISTINCT own) AS k FROM raw_e
                              GROUP BY 1 HAVING k > {m} ORDER BY k DESC"""
                           .format(m=MAX_CLAIMS)).fetchall()
        for partner, k in junk:
            print("    DROPPED {!r}: claimed by {} different stars (> {})"
                  .format(partner, k, MAX_CLAIMS))
        con.execute("""CREATE OR REPLACE TEMP TABLE e AS
            SELECT DISTINCT system_a, system_b FROM raw_e
            WHERE partner NOT IN (SELECT partner FROM raw_e GROUP BY 1
                                  HAVING count(DISTINCT own) > {m})"""
                    .format(m=MAX_CLAIMS))
        n = con.execute("SELECT count(*) FROM e").fetchone()[0]
        con.execute("CREATE OR REPLACE TEMP TABLE e_{}_{} AS SELECT * FROM e"
                    .format(tag, label))
        parts.append(("{}:{}".format(tag, label), "e_{}_{}".format(tag, label), n))
        print("  {:<16} {:>9,} edges".format("{}:{}".format(tag, label), n), flush=True)

# =================================================================================
# GAME-NAME SOURCES. Everything above links a catalogue name to another catalogue
# name. These two link a catalogue name to the name FRONTIER used, which is the only
# way to reach a star the game calls Sirius or Alpha Centauri.
# =================================================================================
BAYER_SRC = "IV/27A/catalog"
SIMBAD = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
CHUNK = 500          # identifiers per SIMBAD query; 120 values answer in ~0.4s
# The positional fence. Every one of these was measured, not chosen: at SNR 10 the
# distance error is 10%, which at 200 ly is 20 ly of slop -- already several times the
# mean separation between systems, so nothing looser could be trusted.
POS_SNR, POS_MAX_LY, POS_MAX_SEP = 10.0, 200.0, 1.0
# *** UNIQUENESS IS A RATIO, NOT A COUNT, AND THE COUNT VERSION THREW AWAY THE ANSWER. ***
# The first fence demanded that the nearest hand-named system be the ONLY one within 3 ly.
# In the solar neighbourhood that is routinely false and says nothing: Ross 128 sits 0.12
# ly from where its astrometry puts it and has other named systems within 3 ly, so it was
# rejected as ambiguous while being as unambiguous as a match can get. What actually
# distinguishes a real match from a coincidence is the GAP to the runner-up.
POS_RATIO, POS_RUNNER_UP = 4.0, 2.0   # 2nd nearest must be >= 4x the 1st AND >= 2 ly
# Catalogue prefixes worth asking SIMBAD for -- exactly the ones system_catalog holds.
SIMBAD_WANT = ("HD ", "HIP ", "HR ", "GJ ", "LHS ", "NLTT ", "TYC ", "SAO ", "LP ",
                "BD", "CD-", "CPD-")

# THE GENITIVE IS THE WHOLE RENDERING PROBLEM. The game writes a Bayer name as
# "<letter> <constellation in the genitive>", which is the IAU form, so this is the
# standard 88-entry table and not a Frontier invention.
GENITIVE = {
    "And": "Andromedae", "Ant": "Antliae", "Aps": "Apodis", "Aqr": "Aquarii",
    "Aql": "Aquilae", "Ara": "Arae", "Ari": "Arietis", "Aur": "Aurigae",
    "Boo": "Bootis", "Cae": "Caeli", "Cam": "Camelopardalis", "Cnc": "Cancri",
    "CVn": "Canum Venaticorum", "CMa": "Canis Majoris", "CMi": "Canis Minoris",
    "Cap": "Capricorni", "Car": "Carinae", "Cas": "Cassiopeiae", "Cen": "Centauri",
    "Cep": "Cephei", "Cet": "Ceti", "Cha": "Chamaeleontis", "Cir": "Circini",
    "Col": "Columbae", "Com": "Comae Berenices", "CrA": "Coronae Australis",
    "CrB": "Coronae Borealis", "Crv": "Corvi", "Crt": "Crateris", "Cru": "Crucis",
    "Cyg": "Cygni", "Del": "Delphini", "Dor": "Doradus", "Dra": "Draconis",
    "Equ": "Equulei", "Eri": "Eridani", "For": "Fornacis", "Gem": "Geminorum",
    "Gru": "Gruis", "Her": "Herculis", "Hor": "Horologii", "Hya": "Hydrae",
    "Hyi": "Hydri", "Ind": "Indi", "Lac": "Lacertae", "Leo": "Leonis",
    "LMi": "Leonis Minoris", "Lep": "Leporis", "Lib": "Librae", "Lup": "Lupi",
    "Lyn": "Lyncis", "Lyr": "Lyrae", "Men": "Mensae", "Mic": "Microscopii",
    "Mon": "Monocerotis", "Mus": "Muscae", "Nor": "Normae", "Oct": "Octantis",
    "Oph": "Ophiuchi", "Ori": "Orionis", "Pav": "Pavonis", "Peg": "Pegasi",
    "Per": "Persei", "Phe": "Phoenicis", "Pic": "Pictoris", "Psc": "Piscium",
    "PsA": "Piscis Austrini", "Pup": "Puppis", "Pyx": "Pyxidis", "Ret": "Reticuli",
    "Sge": "Sagittae", "Sgr": "Sagittarii", "Sco": "Scorpii", "Scl": "Sculptoris",
    "Sct": "Scuti", "Ser": "Serpentis", "Sex": "Sextantis", "Tau": "Tauri",
    "Tel": "Telescopii", "Tri": "Trianguli", "TrA": "Trianguli Australis",
    "Tuc": "Tucanae", "UMa": "Ursae Majoris", "UMi": "Ursae Minoris", "Vel": "Velorum",
    "Vir": "Virginis", "Vol": "Volantis", "Vul": "Vulpeculae",
}
# *** THE GAME MISSPELLS SOME OF THEM, AND THE GAME WINS. *** These are alternates
# offered ALONGSIDE the IAU form, never instead of it: whichever string is actually a
# system in system_known is the one that survives, so an entry here can only ever add
# matches. "Chamaelontis" is Frontier dropping an 'e'.
GENITIVE_ALT = {"Cha": ["Chamaelontis"], "Com": ["Comae"], "PsA": ["Piscis Austrini"],
                # Corona Australis takes the genitive "Coronae Australis" in the IAU
                # list; the game writes "Coronae Austrinae", which is the other correct
                # Latin form. Both are offered and the game's is the one that matches.
                "CrA": ["Coronae Austrinae"]}

GREEK = {
    "alf": "Alpha", "bet": "Beta", "gam": "Gamma", "del": "Delta", "eps": "Epsilon",
    "zet": "Zeta", "eta": "Eta", "the": "Theta", "tet": "Theta", "iot": "Iota",
    "kap": "Kappa", "lam": "Lambda", "mu.": "Mu", "nu.": "Nu", "ksi": "Xi",
    "omi": "Omicron", "pi.": "Pi", "rho": "Rho", "sig": "Sigma", "tau": "Tau",
    "ups": "Upsilon", "phi": "Phi", "chi": "Chi", "psi": "Psi", "ome": "Omega",
}


def game_names():
    """The hand-named systems, and which of them no catalogue name can reach.

    Read from the model READ-ONLY. This is the one thing the builder cannot get from
    input/: what Frontier calls a system is a fact about the game, and system_known is
    where it lives.
    """
    con = connect(read_only=True)
    try:
        allnames = {r[0] for r in con.execute(
            "SELECT system_in_sector FROM system_known WHERE sector_id = 0").fetchall()}
        unreachable = {r[0] for r in con.execute(
            """SELECT k.system_in_sector FROM system_known k WHERE k.sector_id = 0
               AND NOT EXISTS (SELECT 1 FROM system_catalog c
                               WHERE c.system = k.system_in_sector)""").fetchall()}
    finally:
        con.close()
    return allnames, unreachable


def bayer_edges(names, catalogue):
    """HD/HR/HIP -> the Bayer or Flamsteed name, in the galaxy map's spelling.

    Emits every plausible rendering and keeps only the ones that ARE a game system, which
    is what makes a wrong genitive harmless. The shapes come from reading the names the
    game actually uses: "Sigma Orionis", "28 Hydrae", "56 Omicron Serpentis",
    "Omicron-1 Centauri", "4 Omicron-1 Orionis".
    """
    path = fetch("bayer", BAYER_SRC, "HD,HR,HIP,Fl,Bayer,Cst")
    mem = duckdb.connect()
    rows = mem.execute(
        """SELECT trim(HD), trim(HR), trim(HIP), trim(Fl), trim(Bayer), trim(Cst)
           FROM read_csv('{}', delim='\t', skip={}, header=true, all_varchar=true,
                         quote='')
           WHERE TRY_CAST(trim(HD) AS BIGINT) IS NOT NULL"""
        .format(path.as_posix(), header_skip(path))).fetchall()
    mem.close()

    edges, no_genitive = set(), {}
    for hd, hr, hip, fl, bayer, cst in rows:
        gens = ([GENITIVE[cst]] + GENITIVE_ALT.get(cst, [])) if cst in GENITIVE else []
        if not gens:
            no_genitive[cst] = no_genitive.get(cst, 0) + 1
            continue
        cands = set()
        for gen in gens:
            if fl:
                cands.add("{} {}".format(fl, gen))
            if bayer:
                m = re.match(r"^([A-Za-z.]+?)(\d*)$", bayer)
                if not m:
                    continue
                stem, sup = m.group(1), m.group(2).lstrip("0")
                letter = GREEK.get(stem, stem)
                forms = [letter]
                if sup:
                    forms += ["{}-{}".format(letter, sup), "{}{}".format(letter, sup)]
                for form in forms:
                    cands.add("{} {}".format(form, gen))
                    if fl:
                        cands.add("{} {} {}".format(fl, form, gen))
        for hit in (c for c in cands if c in names):
            for prefix, num in (("HD", hd), ("HR", hr), ("HIP", hip)):
                if num and "{} {}".format(prefix, num) in catalogue:
                    edges.add(("{} {}".format(prefix, num), hit))
    if no_genitive:
        print("    no genitive for: {}".format(sorted(no_genitive)))
    return edges


def _norm(s):
    """The comparison key for a name: whitespace collapsed, case folded.

    Everything SIMBAD returns goes through this before it is matched against what we
    asked for. It is deliberately not clever -- no punctuation stripping, no fuzzy
    distance -- because a looser key would start matching different stars.
    """
    return re.sub(r"\s+", " ", s).strip().casefold()


# The genitive table, inverted once: "Aquarii" -> "Aqr". Built from GENITIVE and its
# game-spelling alternates so both forms resolve.
_ABBREV = {}
for _abb, _gen in GENITIVE.items():
    _ABBREV[_gen.casefold()] = _abb
for _abb, _alts in GENITIVE_ALT.items():
    for _alt in _alts:
        _ABBREV[_alt.casefold()] = _abb


# The Greek table inverted, into the spelling SIMBAD uses: "Zeta" -> "zet". SIMBAD files
# a Bayer star as "* zet Dor", lower case and abbreviated, so "Zeta Doradus" has to be
# folded on BOTH halves before it will look up.
_GREEK_ABB = {full.casefold(): abb for abb, full in GREEK.items()}


def _abbreviate(name):
    """Every SIMBAD-shaped spelling of a game name. Empty when none applies.

    Returns a LIST because one game name can need two different folds and there is no
    way to know in advance which SIMBAD holds:
      "IL Aquarii"     -> ["IL Aqr"]            variable star
      "Zeta Doradus"   -> ["Zeta Dor", "zet Dor"]   Bayer, and SIMBAD prefers the second
      "Gliese 665"     -> ["GJ 665"]            CDS writes GJ where the game writes Gliese
    """
    out = []
    if name.startswith("Gliese "):
        out.append("GJ " + name[7:])
    stem = None
    bits = name.split(" ")
    for n_words in (1, 2, 3):                   # "Ceti", "Canis Majoris", "Coronae Aus.."
        if len(bits) > n_words:
            tail = " ".join(bits[-n_words:]).casefold()
            if tail in _ABBREV:
                stem = " ".join(bits[:-n_words])
                out.append("{} {}".format(stem, _ABBREV[tail]))
                break
    if stem:
        head = stem.split(" ")[-1].casefold()
        if head in _GREEK_ABB:                  # "Zeta Dor" -> "zet Dor"
            rest = " ".join(stem.split(" ")[:-1])
            greek = _GREEK_ABB[head]
            out.append(("{} {}".format(rest, greek) if rest else greek)
                       + " " + out[-1].rsplit(" ", 1)[1])
    return out


def positional_edges(unreachable, catalogue):
    """HIP astrometry -> the hand-named game system standing on the same spot.

    The ED frame is the galactic one, rotated: x = -Y_gal, y = Z_gal, z = X_gal. That was
    not assumed -- it was fitted against the 71,098 HIP rows that resolve BY NAME, where
    both the catalogue position and the game position are known, and it reproduces them
    with a residual of a few light years at distance and well under one nearby.
    """
    path = fetch("hip_astro", "I/239/hip_main", "HIP,Plx,e_Plx,_Glon,_Glat")
    # The model, read-only, for the one thing input/ cannot supply: where the game puts
    # its hand-named systems. Pulled into the in-memory connection so the rest of the
    # matching costs no lock.
    mcon = connect(read_only=True)
    try:
        pts = mcon.execute("""SELECT system_in_sector, x, y, z FROM system_known
            WHERE sector_id = 0 AND abs(x) < 220 AND abs(y) < 220
              AND abs(z) < 220""").fetchall()
    finally:
        mcon.close()
    con.execute("CREATE OR REPLACE TEMP TABLE game_xyz "
                "(s VARCHAR, x DOUBLE, y DOUBLE, z DOUBLE)")
    con.executemany("INSERT INTO game_xyz VALUES (?,?,?,?)", pts)
    con.execute("""CREATE OR REPLACE TEMP TABLE hip_xyz AS
        SELECT 'HIP ' || CAST(CAST(TRY_CAST(trim(HIP) AS BIGINT) AS BIGINT) AS VARCHAR)
                 AS name,
               -3.26156 * 1000 / plx * cos(radians(glat)) * sin(radians(glon)) AS ex,
                3.26156 * 1000 / plx * sin(radians(glat))                      AS ey,
                3.26156 * 1000 / plx * cos(radians(glat)) * cos(radians(glon)) AS ez
        FROM (SELECT trim(HIP) AS HIP, TRY_CAST(trim(Plx) AS DOUBLE) AS plx,
                     TRY_CAST(trim(e_Plx) AS DOUBLE) AS eplx,
                     TRY_CAST(trim(_Glon) AS DOUBLE) AS glon,
                     TRY_CAST(trim(_Glat) AS DOUBLE) AS glat
              FROM read_csv('{}', delim='\t', skip={}, header=true, all_varchar=true,
                            quote=''))
        WHERE plx > 0 AND eplx > 0 AND plx / eplx >= {} AND 3.26156 * 1000 / plx < {}
        """.format(path.as_posix(), header_skip(path), POS_SNR, POS_MAX_LY))
    rows = con.execute("""
        WITH m AS (
          SELECT h.name, g.s, sqrt((h.ex-g.x)^2 + (h.ey-g.y)^2 + (h.ez-g.z)^2) AS sep
          FROM hip_xyz h JOIN game_xyz g
            ON abs(h.ex-g.x) < 3 AND abs(h.ey-g.y) < 3 AND abs(h.ez-g.z) < 3),
        r AS (SELECT name, s, sep,
                     row_number() OVER (PARTITION BY name ORDER BY sep) AS rk,
                     lead(sep) OVER (PARTITION BY name ORDER BY sep) AS next_sep
              FROM m)
        SELECT name, s FROM r
        WHERE rk = 1 AND sep < {sep}
          AND (next_sep IS NULL
               OR (next_sep >= {ratio} * sep AND next_sep >= {runner}))"""
        .format(sep=POS_MAX_SEP, ratio=POS_RATIO, runner=POS_RUNNER_UP)).fetchall()
    # Both ends must still be ours, and the game name must be one no catalogue reaches --
    # if it were a catalogue name it would have resolved by name and this edge would be
    # asserting something already known, or contradicting it.
    return {(cat, game) for cat, game in rows
            if cat in catalogue and game in unreachable}


# The catalogues small enough to ask SIMBAD about wholesale, and the ones where a
# cross-ID is likely to exist at all. TYC/HD/SAO/BD/CD/CPD are millions of rows of faint
# stars; asking about them would cost thousands of queries to learn that most have no
# other name.
XID_TYPES = ("HIP", "HR", "GJ", "LHS")


def simbad_catalogue_edges(catalogue):
    """Catalogue name -> its other catalogue names, straight from SIMBAD.

    *** THE BLIND SPOT THIS FIXES. *** simbad_edges() asks only about game names that are
    NOT catalogue designations, because its job is to reach the names no catalogue
    assigns. The consequence went unnoticed for a while: where the game ships a star as
    `LHS 3558`, that row resolves by NAME and is therefore never asked about -- so the
    same star`s HIP row stays NULL with nothing to link it. 227 HIP stars were sitting on
    top of a game system named after a catalogue we already hold.

    Asked by OUR spelling and matched back through _norm(), same as the other pass.
    """
    names = sorted(n for n, in con.execute(
        "SELECT system FROM names WHERE regexp_matches(system, '^({})[ 0-9]')"
        .format("|".join(XID_TYPES) + "|Gliese")).fetchall())
    key = {_norm(n): n for n in names}
    want = " OR ".join("b.id LIKE '{}%'".format(p) for p in SIMBAD_WANT)
    edges, batches = set(), (len(names) + CHUNK - 1) // CHUNK
    print("    asking SIMBAD about {:,} catalogue names in {} batch(es)"
          .format(len(names), batches), flush=True)
    for i in range(0, len(names), CHUNK):
        vals = ",".join("'" + n.replace("'", "''") + "'" for n in names[i:i + CHUNK])
        query = ("SELECT a.id AS asked, b.id AS other FROM ident a "
                 "JOIN ident b ON a.oidref = b.oidref "
                 "WHERE a.id IN ({}) AND ({})".format(vals, want))
        body = urllib.parse.urlencode({"request": "doQuery", "lang": "adql",
                                       "format": "csv", "query": query}).encode()
        for attempt in range(3):
            try:
                with urllib.request.urlopen(SIMBAD, data=body, timeout=600) as r:
                    text = r.read().decode("utf-8", "replace")
                break
            except Exception as exc:                                   # noqa: BLE001
                if attempt == 2:
                    raise SystemExit("  simbad_x: failed -- {}".format(exc))
                time.sleep(10)
        for line in text.splitlines()[1:]:
            parts = [c.strip().strip('"') for c in line.split('","')]
            if len(parts) != 2:
                continue
            a_id, b_id = parts[0].strip('"'), parts[1].strip('"')
            a = key.get(_norm(re.sub(r"^(NAME|V\*|\*)\s+", "", a_id)))
            b_clean = re.sub(r"\s+", " ", b_id).strip()
            forms = [b_clean] + (["Gliese " + b_clean[3:]] if b_clean.startswith("GJ ")
                                 else [])
            forms += [re.sub(r"[A-Za-z]$", "", f).strip() for f in list(forms)]
            b = next((f for f in forms if f in catalogue), None)
            if a and b and a != b:
                edges.add((a, b))
        if (i // CHUNK) % 40 == 0:
            print("    simbad_x batch {}/{}  {:,} edges".format(i // CHUNK + 1, batches,
                                                                len(edges)), flush=True)
    return edges


def kepler_edges(unreachable, catalogue):
    """KOI number <-> Kepler-NNN, from the table that carries both.

    The Kepler field is faint -- V~14 is typical -- so almost none of these stars has an
    HD, HIP or Tycho designation, and SIMBAD has nothing to trade. The one identifier
    that links them is the archive''s own: `cumulative` lists `kepoi_name` (K00752.01)
    and `kepler_name` (Kepler-22 b) on the same row, and stripping the planet letter off
    the second gives the host. 339 game systems are reachable by this and nothing else.

    *** THE PLANET SUFFIX IS NOT PART OF THE STAR. *** "Kepler-22 b" is a planet; the
    game names the SYSTEM "Kepler-22". Two planets of one star would otherwise arrive as
    two different hosts and assert two identities for the same pair.
    """
    path = fetch_url("kepler_names", NASA_KOI,
                     "SELECT DISTINCT kepoi_name, kepler_name FROM cumulative "
                     "WHERE kepler_name IS NOT NULL")
    edges = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        parts = [c.strip().strip('"') for c in line.split(",")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            continue
        m = re.match(r"^K(\d+)\.\d+$", parts[0])
        host = re.sub(r"\s+[a-z]$", "", parts[1]).strip()
        if not m or not host:
            continue
        koi = "KOI " + str(int(m.group(1)))
        if koi in catalogue and host in unreachable:
            edges.add((koi, host))
    return edges


def simbad_edges(unreachable, catalogue):
    """Ask SIMBAD what else each unreachable game name is called.

    PREFIX-AGNOSTIC ON PURPOSE. Asking by identifier rather than by pattern means survey
    names (Wolf 359, Ross 128, LFT 1358), variable-star names and exoplanet-host names all
    resolve without a rule apiece -- and Frontier's invented names simply come back empty,
    which costs one row in a batched query and no special case in this script.

    Names are asked BARE, once each. SIMBAD files a proper name under its NAME namespace
    ("NAME Sirius") but matches an `id IN (...)` lookup through its own normalisation, so
    asking for "Sirius" already returns the NAME row -- a second pass over "NAME <x>" was
    measured and produced 0 additional edges for twice the queries.
    """
    # *** SIMBAD ANSWERS IN ITS OWN SPELLING, AND MATCHING ON THE RAW STRING LOST THE
    # ANSWER. *** Ask for "Ross 128" and the reply says "Ross  128" -- two spaces, its
    # internal padded form. Ask for "Luyten's Star" and the reply is "NAME Luyten's star",
    # lower-cased. Both were dropped by a straight `in` test, so the source silently
    # returned nothing for exactly the families it existed to catch. Compare on a
    # NORMALISED key -- whitespace collapsed, case folded -- and keep a map back to the
    # game's own spelling, which is what the edge has to carry.
    todo = sorted(unreachable)
    key = {_norm(n): n for n in todo}
    # ALSO ASK IN SIMBAD'S CONSTELLATION FORM. The game writes variable stars and Bayer
    # names out in full ("IL Aquarii", "YZ Ceti"); SIMBAD abbreviates ("V* IL Aqr"). The
    # genitive table already in this file inverts cleanly, so the abbreviated spelling
    # costs one dict lookup and reaches ~1,500 variable-star systems that no catalogue
    # here designates at all.
    abbrev = {}
    for n in todo:
        for a in _abbreviate(n):
            if a and a != n:
                abbrev.setdefault(_norm(a), n)
    edges = set()
    want = " OR ".join("b.id LIKE '{}%'".format(p) for p in SIMBAD_WANT)
    asked = todo + sorted(abbrev)
    batches = (len(asked) + CHUNK - 1) // CHUNK
    for i in range(0, len(asked), CHUNK):
        chunk = asked[i:i + CHUNK]
        vals = ",".join("'" + n.replace("'", "''") + "'" for n in chunk)
        query = ("SELECT a.id AS game_name, b.id AS cat_id FROM ident a "
                 "JOIN ident b ON a.oidref = b.oidref "
                 "WHERE a.id IN ({}) AND ({})".format(vals, want))
        body = urllib.parse.urlencode({"request": "doQuery", "lang": "adql",
                                       "format": "csv", "query": query}).encode()
        for attempt in range(3):
            try:
                with urllib.request.urlopen(SIMBAD, data=body, timeout=600) as r:
                    text = r.read().decode("utf-8", "replace")
                break
            except Exception as exc:                                   # noqa: BLE001
                if attempt == 2:
                    raise SystemExit("  simbad: failed after 3 tries -- {}".format(exc))
                time.sleep(10)
        for line in text.splitlines()[1:]:
            parts = [p.strip().strip('"') for p in line.split('","')]
            if len(parts) != 2:
                continue
            game, cat = parts[0].strip('"'), parts[1].strip('"')
            # SIMBAD pads inside identifiers ("HD  78791") and prefixes proper names,
            # variable stars ("V* IL Aqr") and plain stars ("* alf Cen").
            cat = re.sub(r"\s+", " ", cat).strip()
            game = re.sub(r"^(NAME|V\*|\*)\s+", "", game).strip()
            game = key.get(_norm(game)) or abbrev.get(_norm(game)) or game
            # SPELLING IS OURS, NOT SIMBAD'S. Two systematic differences, both worth a
            # candidate rather than a rule: SIMBAD writes Gliese as "GJ 406" while the
            # game writes "Gliese 406" (system_catalog follows the game), and SIMBAD keeps
            # the component letter on a double ("HD 48915A") where the game usually drops
            # it. Offer every form and let the membership test pick.
            forms = [cat]
            if cat.startswith("GJ "):
                forms.append("Gliese " + cat[3:])
            forms += [re.sub(r"[A-Za-z]$", "", f).strip() for f in list(forms)]
            # BOTH ENDPOINTS MUST BE OURS -- SIMBAD's own normalisation can answer with a
            # name we did not ask about, and an edge from a name the game does not use
            # would resolve nothing while looking like it did.
            if game not in unreachable:
                continue
            for form in forms:
                if form in catalogue:
                    edges.add((form, game))
                    break
        if (i // CHUNK) % 20 == 0:
            print("    simbad batch {}/{}  {:,} edges so far"
                  .format(i // CHUNK + 1, batches, len(edges)), flush=True)
    return edges


print("\nlinking catalogue names to the names the GAME uses ...", flush=True)
all_game, unreachable_game = game_names()
cat_names = {r[0] for r in con.execute("SELECT system FROM names").fetchall()}
print("  {:,} hand-named systems, {:,} of them reachable by no catalogue name"
      .format(len(all_game), len(unreachable_game)))

for tag, produce in (("bayer:IV/27A", lambda: bayer_edges(all_game, cat_names)),
                     ("simbad:ident", lambda: simbad_edges(unreachable_game, cat_names)),
                     ("position:hip", lambda: positional_edges(unreachable_game,
                                                               cat_names)),
                     ("kepler:koi", lambda: kepler_edges(unreachable_game, cat_names)),
                     ("simbad:xid", lambda: simbad_catalogue_edges(cat_names))):
    pairs = produce()
    # Inserted as PARAMETERS, not interpolated: these strings come from a web service
    # and from a catalogue, and one apostrophe would otherwise end the statement.
    con.execute("CREATE OR REPLACE TEMP TABLE g (a VARCHAR, b VARCHAR)")
    if pairs:
        con.executemany("INSERT INTO g VALUES (?, ?)", sorted(pairs))
    # Same claim guard as the catalogue sources, oriented the same way: the GAME name is
    # the star, so a catalogue id claimed by more than MAX_CLAIMS different game systems
    # is not an identity.
    junk = con.execute("""SELECT a, count(DISTINCT b) k FROM g GROUP BY 1
                          HAVING k > {} ORDER BY k DESC""".format(MAX_CLAIMS)).fetchall()
    for partner, k in junk:
        print("    DROPPED {!r}: claimed by {} different game systems (> {})"
              .format(partner, k, MAX_CLAIMS))
    tbl = "e_" + tag.replace(":", "_").replace("/", "_")
    con.execute("""CREATE OR REPLACE TEMP TABLE {} AS
        SELECT DISTINCT least(a, b) AS system_a, greatest(a, b) AS system_b FROM g
        WHERE a NOT IN (SELECT a FROM g GROUP BY 1 HAVING count(DISTINCT b) > {})"""
                .format(tbl, MAX_CLAIMS))
    n = con.execute("SELECT count(*) FROM {}".format(tbl)).fetchone()[0]
    parts.append((tag, tbl, n))
    print("  {:<16} {:>9,} edges".format(tag, n), flush=True)

# Union in SOURCE ORDER and keep the first spelling of each identity: the priority is
# declared by the order of SOURCES, so row_number() over it is the whole tie-break.
union = "\nUNION ALL\n".join(
    "SELECT system_a, system_b, '{}' AS source, {} AS pri FROM {}".format(label, i, tbl)
    for i, (label, tbl, _) in enumerate(parts))
con.execute("""CREATE OR REPLACE TEMP TABLE edges AS
    SELECT system_a, system_b, source FROM (
      SELECT *, row_number() OVER (PARTITION BY system_a, system_b ORDER BY pri) AS rn
      FROM ({})) WHERE rn = 1""".format(union))

total, dupes = con.execute("SELECT count(*), {} - count(*) FROM edges"
                           .format(sum(n for _, _, n in parts))).fetchone()
con.execute("COPY (SELECT system_a, system_b, source FROM edges ORDER BY system_a, "
            "system_b) TO '{}' (FORMAT parquet)".format(OUT.as_posix()))

print("\n  {:,} distinct identities ({:,} duplicate assertions collapsed)"
      .format(total, dupes))
print("  names reachable from at least one edge: {:,}".format(
    con.execute("""SELECT count(DISTINCT s) FROM (
                     SELECT system_a AS s FROM edges
                     UNION ALL SELECT system_b FROM edges)""").fetchone()[0]))
print("\nwrote {}  ({:,} bytes)".format(OUT, OUT.stat().st_size))
con.close()
print("\nDONE_BUILD_SYSTEM_CATALOG_ALIAS")
