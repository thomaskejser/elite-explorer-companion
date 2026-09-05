import sys
import pathlib
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import ROOT, INPUT, connect

OUT = INPUT / "system_catalog.parquet"
CACHE = ROOT / "raw" / "catalog"
# READS THE NETWORK, which no other builder but its alias twin does: real star
# catalogues change once a decade, so mirroring them into staging buys nothing.
VIZIER = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"
NASA = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"

def _int(col, typ, prefix):
    num = 'CAST(CAST("{}" AS BIGINT) AS VARCHAR)'.format(col)
    return ("'{t}' AS type, {n} AS designation, '{p}' || {n} AS system"
            .format(t=typ, n=num, p=prefix))

CATALOGUES = [
    ("HIP", VIZIER, 'SELECT "HIP" FROM "I/239/hip_main"',
     _int("HIP", "HIP", "HIP ")),
    ("HD", VIZIER, 'SELECT "HD" FROM "III/135A/catalog"',
     _int("HD", "HD", "HD ")),
    ("HDE", VIZIER, 'SELECT "HD" FROM "III/182/catalog"',
     _int("HD", "HD", "HD ")),
    ("HR", VIZIER, 'SELECT "HR" FROM "V/50/catalog"',
     _int("HR", "HR", "HR ")),
    ("SAO", VIZIER, 'SELECT "SAO" FROM "I/131A/sao"',
     _int("SAO", "SAO", "SAO ")),

    ("LHS", VIZIER, 'SELECT "LHS" FROM "I/87B/catalog"',
     """'LHS' AS type, trim("LHS") AS designation,
        'LHS ' || trim("LHS") AS system"""),

    ("TYC", VIZIER, 'SELECT "TYC1","TYC2","TYC3" FROM "I/259/tyc2"',
     """'TYC' AS type,
        trim("TYC1") || '-' || trim("TYC2") || '-' || trim("TYC3") AS designation,
        'TYC ' || trim("TYC1") || '-' || trim("TYC2") || '-' || trim("TYC3")
          AS system"""),

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

    ("GJ", VIZIER, 'SELECT "Name" FROM "V/70A/catalog"',
     """'GJ' AS type,
        trim(substring(trim("Name"), 4)) AS designation,
        CASE WHEN trim("Name") LIKE 'GJ %' THEN 'GJ ' ELSE 'Gliese ' END
          || trim(substring(trim("Name"), 4)) AS system"""),

    ("NLTT", VIZIER, 'SELECT "recno","Name" FROM "I/98A/catalog"',
     """'NLTT' AS type, trim("recno") AS designation,
        'NLTT ' || trim("recno") AS system"""),

    ("LP", None, "NLTT",
     """'LP' AS type,
        regexp_replace(replace(trim("Name"), '*', ''), '\\s*-\\s*', '-')
          AS designation,
        'LP ' || regexp_replace(replace(trim("Name"), '*', ''), '\\s*-\\s*', '-')
          AS system"""),

    ("KOI", NASA, "SELECT kepoi_name FROM cumulative",
     """'KOI' AS type,
        CAST(CAST(substring(trim(kepoi_name), 2, 5) AS BIGINT) AS VARCHAR)
          AS designation,
        'KOI ' || CAST(CAST(substring(trim(kepoi_name), 2, 5) AS BIGINT) AS VARCHAR)
          AS system"""),
]

FILTERS = {
    "GJ": """WHERE regexp_matches(trim("Name"), '^(Gl|NN|GJ|Wo) ')""",
    "LP": """WHERE regexp_matches(trim("Name"), '^[0-9]+\\s*-\\s*[0-9]+\\*?$')""",
}

if OUT.exists():
    sys.exit("{} already exists and is AUTHORITATIVE (hand-editable) -- refusing to "
             "overwrite.\nTo apply it:  python etl/system_catalog/load.py\n"
             "For a genuine fresh seed, delete it first.".format(OUT))

def fetch(tag, service, adql):
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
        except Exception as exc:
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
      "\n  python etl/system_catalog/load.py")
print("\nDONE_BUILD_SYSTEM_CATALOG")
