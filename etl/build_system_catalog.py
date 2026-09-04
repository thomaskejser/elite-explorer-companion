"""SEED input/system_catalog.parquet -- real-world star catalogues, in game spelling.

ONE-TIME SEEDER. Writes only the PARQUET, and only if it does not already exist; it
never touches the `system_catalog` table (that is etl/load_system_catalog.py). There is
deliberately no --force, per ETL.md: once seeded the file is authoritative and
hand-editable, and regenerating it would silently discard corrections.

*** THIS IS THE ONLY BUILDER THAT READS THE NETWORK. *** Every other one reads staging,
which was filled by scripts/ingest_sources.py. There is no staging table here because
these catalogues are not an Elite Dangerous data source -- they are astronomy, they
change on the order of once a decade, and mirroring 4.7M rows of them into a 60 GiB
database so a builder can read them back out would buy nothing. Downloads are CACHED in
raw/catalog/ so a re-run after a failure resumes instead of refetching.

SOURCES, all official:
  VizieR / CDS Strasbourg   https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync
      the canonical archive for published catalogues. TAP/ADQL, returns CSV.
  NASA Exoplanet Archive    https://exoplanetarchive.ipac.caltech.edu/TAP/sync
      the source for KOI, which VizieR does not own.

WHY THESE FOURTEEN AND NOT MORE. Only catalogues Frontier appears to have ingested
WHOLESALE are here, because only for those does a coverage rate mean anything. Four
all-sky surveys turn up in-game in trace amounts -- 2MASS 8,205 systems, USNO-A2.0 188,
GSC 53, NOMAD1 43 -- and are excluded on purpose: complete, they are 3.83 BILLION rows
(measured at ~219 GB all in, of which ~146 GB is index) to produce a coverage rate of
0.000004%. CDS does not even distribute them in bulk -- their FTP directories hold a
ReadMe, a 1,000-row sample and a coverage map, nothing else -- so it would additionally
mean bulk requests to IRSA, USNO/NOFS and MAST. Resolve those names via SIMBAD instead.

Cluster members are excluded for a different reason: in-game "NGC 2539 ZUG 25" is
cluster PLUS member id, and NGC 2000.0 lists clusters, not their stars. ~6,000 in-game
systems are of that shape and need membership catalogues, not this.

Usage:  python etl/build_system_catalog.py   # refuses if the parquet exists
"""
import sys
import pathlib
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import ROOT, INPUT, connect

OUT = INPUT / "system_catalog.parquet"
CACHE = ROOT / "raw" / "catalog"
VIZIER = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"
NASA = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"


def _int(col, typ, prefix):
    """A catalogue keyed by one plain integer -- HIP, HD, HR, SAO."""
    num = 'CAST(CAST("{}" AS BIGINT) AS VARCHAR)'.format(col)
    return ("'{t}' AS type, {n} AS designation, '{p}' || {n} AS system"
            .format(t=typ, n=num, p=prefix))


# ---------------------------------------------------------------------------------
# ONE ENTRY PER CATALOGUE: (tag, service, ADQL, SQL projecting type/designation/system).
#
# `system` is composed with the prefix THE GAME RENDERS, which is not always the one the
# catalogue prefers -- CDS writes "Gl 695", the game writes "Gliese 695". The game wins,
# because that column has to paste into the galaxy map's search box.
#
# A service of None means "reuse another catalogue's download"; see LP.
# ---------------------------------------------------------------------------------
CATALOGUES = [
    ("HIP", VIZIER, 'SELECT "HIP" FROM "I/239/hip_main"',
     _int("HIP", "HIP", "HIP ")),
    ("HD", VIZIER, 'SELECT "HD" FROM "III/135A/catalog"',
     _int("HD", "HD", "HD ")),
    # THE HENRY DRAPER NUMBERING DOES NOT STOP AT 272,150. III/135A carries HD 1 through
    # 272,150 (the original catalogue plus its first extension); the Extension CHARTS
    # continue 272,151..359,083 in a separate publication. The game uses both -- 1,800
    # in-game HD systems sit above 272,150, and without this they were 744 unexplained
    # misses that looked like Frontier inventing HD numbers. Same `type`, because it is
    # the same numbering space and splitting it would break the coverage rate.
    ("HDE", VIZIER, 'SELECT "HD" FROM "III/182/catalog"',
     _int("HD", "HD", "HD ")),
    ("HR", VIZIER, 'SELECT "HR" FROM "V/50/catalog"',
     _int("HR", "HR", "HR ")),
    ("SAO", VIZIER, 'SELECT "SAO" FROM "I/131A/sao"',
     _int("SAO", "SAO", "SAO ")),

    # LHS is fixed-width in the source ("1496 ", " 161 "), so it must be trimmed rather
    # than cast -- a cast would work here but would silently drop any non-numeric id.
    ("LHS", VIZIER, 'SELECT "LHS" FROM "I/87B/catalog"',
     """'LHS' AS type, trim("LHS") AS designation,
        'LHS ' || trim("LHS") AS system"""),

    # Tycho-2 is THREE numbers: TYC1-TYC2-TYC3 -> "TYC 149-1079-1".
    ("TYC", VIZIER, 'SELECT "TYC1","TYC2","TYC3" FROM "I/259/tyc2"',
     """'TYC' AS type,
        trim("TYC1") || '-' || trim("TYC2") || '-' || trim("TYC3") AS designation,
        'TYC ' || trim("TYC1") || '-' || trim("TYC2") || '-' || trim("TYC3")
          AS system"""),

    # *** THE DURCHMUSTERUNGS CARRY THEIR ZONE SIGN DIFFERENTLY AND IT MATTERS. ***
    # Bonner has a separate `zonesign` column beside an UNSIGNED zone (+, 13); Cordoba
    # and Cape bake the sign into `zone` (-42). Getting this wrong yields "BD13 2334",
    # which matches nothing in the game and still looks like a plausible name. Zones are
    # zero-padded to two digits because the game writes "BD+00 4448" and "BD-05 1290".
    ("BD", VIZIER, 'SELECT "zonesign","zone","num" FROM "I/122/bd"',
     """'BD' AS type,
        trim("zonesign") || printf('%02d', CAST("zone" AS INTEGER)) || ' '
          || trim("num") AS designation,
        'BD' || trim("zonesign") || printf('%02d', CAST("zone" AS INTEGER)) || ' '
          || trim("num") AS system"""),
    ("CD", VIZIER, 'SELECT "zone","num" FROM "I/114/cd"',
     """'CD' AS type,
        '-' || printf('%02d', abs(CAST("zone" AS INTEGER))) || ' ' || trim("num")
          AS designation,
        'CD-' || printf('%02d', abs(CAST("zone" AS INTEGER))) || ' ' || trim("num")
          AS system"""),
    ("CPD", VIZIER, 'SELECT "zone","num" FROM "I/108/cpd"',
     """'CPD' AS type,
        '-' || printf('%02d', abs(CAST("zone" AS INTEGER))) || ' ' || trim("num")
          AS designation,
        'CPD-' || printf('%02d', abs(CAST("zone" AS INTEGER))) || ' ' || trim("num")
          AS system"""),

    # *** CNS3 SPELLS ONE NUMBERING SPACE FOUR DIFFERENT WAYS AND ONLY ONE OF THEM
    # LOOKS LIKE "GLIESE". *** Its Name column holds Gl 1..99.1 (1,745), NN 3001..4388
    # (1,388), GJ 1001..2157 (384) and Wo 9003..9848 (285). NN and Wo are CNS3's
    # internal prefixes -- "no name" and Woolley -- for stars the rest of the world,
    # the game included, numbers as Gliese. In-game "Gliese 3273" IS CNS3 "NN 3273" and
    # "Gliese 9229" IS "Wo 9229".
    #
    # ALL FOUR PREFIXES ARE KEPT. Dropping NN and Wo loses 231 of the 293 in-game
    # Gliese systems and makes the catalogue look 3.6% present instead of ~99%. Only
    # "Sun" is dropped, by the empty-designation filter downstream.
    #
    # GJ keeps its own spelling because the game does too ("GJ 2015"); everything else
    # renders as "Gliese", which is what 293 of the 303 in-game systems use.
    ("GJ", VIZIER, 'SELECT "Name" FROM "V/70A/catalog"',
     """'GJ' AS type,
        trim(substring(trim("Name"), 4)) AS designation,
        CASE WHEN trim("Name") LIKE 'GJ %' THEN 'GJ ' ELSE 'Gliese ' END
          || trim(substring(trim("Name"), 4)) AS system"""),

    # *** NLTT'S NUMBER IS THE RECORD NUMBER. *** I/98A has no NLTT column: the
    # catalogue is ordered by NLTT number, so recno IS it. VALIDATED, not assumed --
    # recno 2269 carries Name "- 0:102" and SIMBAD's NLTT 2269 is BD-00 102; recno 8182
    # carries "-75:86" and SIMBAD's NLTT 8182 is CD-75 86. Both agree.
    ("NLTT", VIZIER, 'SELECT "recno","Name" FROM "I/98A/catalog"',
     """'NLTT' AS type, trim("recno") AS designation,
        'NLTT ' || trim("recno") AS system"""),

    # LP falls out of the SAME download: I/98A's Name field mixes Durchmusterung forms
    # ("-75:86") with Luyten-Palomar ones ("591-212"). Only the latter are LP, hence the
    # shape test in FILTERS below. The DM-shaped rows are skipped here because BD and CD
    # come from their own catalogues above, complete and unambiguous.
    ("LP", None, "NLTT",
     """'LP' AS type,
        regexp_replace(replace(trim("Name"), '*', ''), '\\s*-\\s*', '-')
          AS designation,
        'LP ' || regexp_replace(replace(trim("Name"), '*', ''), '\\s*-\\s*', '-')
          AS system"""),

    # KOI: kepoi_name is "K00752.01" -- planets .01/.02 of the SAME star. The game names
    # the STAR ("KOI 752"), so strip the planet suffix; DISTINCT collapses the rest.
    ("KOI", NASA, "SELECT kepoi_name FROM cumulative",
     """'KOI' AS type,
        CAST(CAST(substring(trim(kepoi_name), 2, 5) AS BIGINT) AS VARCHAR)
          AS designation,
        'KOI ' || CAST(CAST(substring(trim(kepoi_name), 2, 5) AS BIGINT) AS VARCHAR)
          AS system"""),
]

# Row filters, kept beside the projections they belong to but separate because only two
# catalogues need one.
FILTERS = {
    # Gl / NN / GJ / Wo -- see the note on the GJ entry. All four are the same numbering
    # space. "Sun" is the only other value and falls out as an empty designation.
    "GJ": """WHERE regexp_matches(trim("Name"), '^(Gl|NN|GJ|Wo) ')""",
    "LP": """WHERE regexp_matches(trim("Name"), '^[0-9]+\\s*-\\s*[0-9]+\\*?$')""",
}

if OUT.exists():
    sys.exit("{} already exists and is AUTHORITATIVE (hand-editable) -- refusing to "
             "overwrite.\nTo apply it:  python etl/load_system_catalog.py\n"
             "For a genuine fresh seed, delete it first.".format(OUT))


def fetch(tag, service, adql):
    """Download one catalogue to raw/catalog/<tag>.csv, or reuse the cache.

    Three tries: these are 100 KB to 60 MB transfers from a public academic service, and
    a transient failure two catalogues into a thirteen-catalogue run should not cost the
    twelve that already succeeded. The cache is what actually protects that, but the
    retry saves the common case.
    """
    path = CACHE / "{}.csv".format(tag)
    if path.exists() and path.stat().st_size > 0:
        print("  {:<5} cached  {:>12,} bytes".format(tag, path.stat().st_size))
        return path
    body = urllib.parse.urlencode(
        {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
         "QUERY": adql}).encode()
    t0 = time.time()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(service, data=body, timeout=1800) as r:
                path.write_bytes(r.read())
            break
        except Exception as exc:                                      # noqa: BLE001
            if attempt == 2:
                raise SystemExit("  {}: download failed after 3 tries -- {}"
                                 .format(tag, exc))
            print("  {:<5} retry {} after {}".format(tag, attempt + 1, exc), flush=True)
            time.sleep(10)
    print("  {:<5} fetched {:>12,} bytes  {:>6.1f}s"
          .format(tag, path.stat().st_size, time.time() - t0))
    return path


CACHE.mkdir(parents=True, exist_ok=True)
print("downloading {} catalogues to {} ...".format(len(CATALOGUES), CACHE), flush=True)
paths = {}
for tag, service, adql, _ in CATALOGUES:
    paths[tag] = paths[adql] if service is None else fetch(tag, service, adql)

con = connect(read_only=True)
print("\ncomposing names ...", flush=True)
parts = []
for tag, service, _, project in CATALOGUES:
    src = ("read_csv('{}', all_varchar=true, header=true)"
           .format(paths[tag].as_posix()))
    con.execute("CREATE OR REPLACE TEMP TABLE c_{} AS SELECT DISTINCT {} FROM {} {}"
                .format(tag, project, src, FILTERS.get(tag, "")))
    n = con.execute("SELECT count(*) FROM c_{}".format(tag)).fetchone()[0]
    parts.append("SELECT * FROM c_{}".format(tag))
    ex = con.execute("SELECT system FROM c_{} ORDER BY random() LIMIT 3"
                     .format(tag)).fetchall()
    print("  {:<5}{:>10,}   {}".format(tag, n, " | ".join(e[0] for e in ex)))

# `system` is the PRIMARY KEY, so it has to be unique across ALL types before the file
# is written. The LOADER must never be the thing that discovers a collision -- by then
# it is a constraint violation halfway through a merge rather than a fixable seed.
con.execute("CREATE OR REPLACE TEMP TABLE seed AS SELECT * FROM ({}) "
            "WHERE designation <> '' AND system IS NOT NULL"
            .format(" UNION ALL ".join(parts)))
total, distinct = con.execute(
    "SELECT count(*), count(DISTINCT system) FROM seed").fetchone()
print("\n  {:,} rows, {:,} distinct system names".format(total, distinct))
if total != distinct:
    print("  COLLISIONS -- one name claimed by two catalogues. Keeping the first by "
          "type so the choice is deterministic rather than whichever scanned first:")
    for r in con.execute("""SELECT system, string_agg(DISTINCT type, ',') AS types,
                                   count(*) AS n
                            FROM seed GROUP BY 1 HAVING count(*) > 1
                            ORDER BY n DESC, system LIMIT 10""").fetchall():
        print("    {:<26} {}".format(r[0], r[1]))
    con.execute("""CREATE OR REPLACE TEMP TABLE seed AS
                   SELECT system, type, designation FROM (
                     SELECT *, row_number() OVER (PARTITION BY system
                                                  ORDER BY type, designation) AS rk
                     FROM seed) WHERE rk = 1""")

INPUT.mkdir(exist_ok=True)
con.execute("""COPY (SELECT system, type, designation,
                       CAST(NULL AS BIGINT) AS system_id
                     FROM seed ORDER BY type, system)
               TO '{}' (FORMAT PARQUET, COMPRESSION ZSTD)""".format(OUT.as_posix()))
back = con.execute("SELECT count(*), count(DISTINCT system) FROM '{}'"
                   .format(OUT.as_posix())).fetchone()
print("\nwrote {}  ({:,} rows, {:,} bytes)".format(OUT, back[0], OUT.stat().st_size))
print("  read back: {:,} distinct system -- unique: {}"
      .format(back[1], back[0] == back[1]))

con.close()
print("\nNOTE the `system_catalog` table was NOT touched. Merge with:"
      "\n  python etl/load_system_catalog.py")
print("\nDONE_BUILD_SYSTEM_CATALOG")
