import sys
import pathlib
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
import re

import duckdb
from common.db import INPUT, ROOT, connect, table_count

MAX_CLAIMS = 4

OUT = INPUT / "system_catalog_alias.parquet"
CATALOG = INPUT / "system_catalog.parquet"
CACHE = ROOT / "raw" / "catalog"
# READS THE NETWORK, which no other builder but system_catalog does: real star
# catalogues change once a decade, so mirroring them into staging buys nothing.
ASU = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"
NASA_KOI = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"

if OUT.exists():
    sys.exit("{} already exists and is AUTHORITATIVE (hand-editable) -- refusing to "
             "overwrite.\nTo apply it:  python etl/system_catalog_alias/load.py\n"
             "For a genuine fresh seed, delete it first.".format(OUT))
if not CATALOG.exists():
    sys.exit("{} is missing -- seed it first:\n  python etl/system_catalog/build.py"
             .format(CATALOG))

def _num(col):
    return "CAST(TRY_CAST(trim({}) AS BIGINT) AS VARCHAR)".format(col)

def one(prefix, col):
    return ("CASE WHEN TRY_CAST(trim({c}) AS BIGINT) IS NOT NULL "
            "THEN ['{p} ' || {n}] ELSE [] END".format(c=col, p=prefix, n=_num(col)))

def _dm_name(pfx, signzone, num):
    return "{p} || {sz} || ' ' || {n}".format(p=pfx, sz=signzone, n=num)

def _with_and_without_component(pfx, signzone, num):
    bare = "regexp_replace({}, '[A-Za-z]+$', '')".format(num)
    return "[{}, {}]".format(_dm_name(pfx, signzone, num),
                             _dm_name(pfx, signzone, bare))

def dm_prefixed(col):
    s = "trim({})".format(col)
    pfx = ("CASE substr({s}, 1, 2) WHEN 'BD' THEN 'BD' WHEN 'CD' THEN 'CD' "
           "WHEN 'CP' THEN 'CPD' END".format(s=s))
    signzone = "substr({s}, 3, 3)".format(s=s)
    num = "trim(substr({s}, 6))".format(s=s)
    return ("CASE WHEN {s} <> '' AND {p} IS NOT NULL AND {n} <> '' THEN {cands} "
            "ELSE [] END".format(s=s, p=pfx, n=num,
                                 cands=_with_and_without_component(pfx, signzone, num)))

def dm_bare(col):
    s = "trim({})".format(col)
    signzone = "split_part({s}, ':', 1)".format(s=s)
    raw = "split_part({s}, ':', 2)".format(s=s)
    num = ("CASE WHEN ltrim({r}, '0') = '' THEN '0' ELSE ltrim({r}, '0') END"
           .format(r=raw))
    cands = [_with_and_without_component("'{}'".format(pfx), signzone, num)
             for pfx in ("BD", "CD", "CPD")]
    return ("CASE WHEN regexp_matches({s}, '^[+-][0-9]{{2}}:[0-9]+[A-Za-z]?$') "
            "THEN list_concat(list_concat({a}, {b}), {c}) ELSE [] END"
            .format(s=s, a=cands[0], b=cands[1], c=cands[2]))

def lp_or_dm(col):
    s = "trim(replace({}, '*', ''))".format(col)
    lp = ("'LP ' || regexp_replace({s}, '\\s*-\\s*', '-')".format(s=s))
    return ("CASE WHEN regexp_matches({s}, '^[0-9]+\\s*-\\s*[0-9]+$') THEN [{lp}] "
            "ELSE {dm} END".format(s=s, lp=lp, dm=dm_bare(col)))

def gliese(col):
    s = "trim({})".format(col)
    tail = "trim(substr({s}, 4))".format(s=s)
    return ("CASE WHEN regexp_matches({s}, '^(Gl|NN|GJ|Wo) ') THEN "
            "[CASE WHEN {s} LIKE 'GJ %' THEN 'GJ ' ELSE 'Gliese ' END || {t}] "
            "ELSE [] END".format(s=s, t=tail))

def tyc(a, b, c):
    return ("CASE WHEN trim({a}) <> '' THEN ['TYC ' || trim({a}) || '-' || trim({b}) "
            "|| '-' || trim({c})] ELSE [] END".format(a=a, b=b, c=c))

SOURCES = [
    ("hip_main", "I/239/hip_main", "HIP,HD,BD,CoD,CPD", "'HIP ' || " + _num("HIP"),
     {"HD": one("HD", "HD"),
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

    ("nltt", "I/98A/catalog", "recno,Name", "'NLTT ' || " + _num("recno"),
     {"Name": lp_or_dm("Name")},
     "TRY_CAST(trim(recno) AS BIGINT) IS NOT NULL"),
]
OWN_NAME = {"tyc2": tyc("TYC1", "TYC2", "TYC3"), "cns3": gliese("Name")}

def fetch(tag, table, out):
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
        except Exception as exc:
            if attempt == 2:
                raise SystemExit("  {}: download failed after 3 tries -- {}"
                                 .format(tag, exc))
            print("  {:<9} retry {} after {}".format(tag, attempt + 1, exc), flush=True)
            time.sleep(10)
    print("  {:<9} fetched {:>12,} bytes  {:>6.1f}s"
          .format(tag, path.stat().st_size, time.time() - t0))
    return path

def fetch_url(tag, service, query):
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
        except Exception as exc:
            if attempt == 2:
                raise SystemExit("  {}: download failed -- {}".format(tag, exc))
            time.sleep(10)
    print("  {:<9} fetched {:>12,} bytes".format(tag, path.stat().st_size))
    return path

def header_skip(path):
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            if line.strip() and not line.startswith("#"):
                return i
    raise SystemExit("{}: no header row -- download looks empty".format(path))

CACHE.mkdir(parents=True, exist_ok=True)
print("downloading {} cross-ID sources to {} ...".format(len(SOURCES), CACHE), flush=True)
paths = {tag: fetch(tag, table, out) for tag, table, out, _, _, _ in SOURCES}

con = duckdb.connect()
con.execute("SET preserve_insertion_order=false")
con.execute("CREATE TABLE names AS SELECT DISTINCT system FROM '{}'"
            .format(CATALOG.as_posix()))
n_names = table_count(con, 'names')
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
        con.execute("""CREATE OR REPLACE TEMP TABLE raw_e AS
            WITH r AS (SELECT unnest({own}) AS a, unnest({cand}) AS b
                       FROM {src} WHERE {keep})
            SELECT DISTINCT least(a, b) AS system_a, greatest(a, b) AS system_b,
                            r.a AS own, r.b AS partner
            FROM r JOIN names na ON na.system = r.a JOIN names nb ON nb.system = r.b
            WHERE r.a IS NOT NULL AND r.b IS NOT NULL AND r.a <> r.b"""
                    .format(own=own_expr, cand=cand, src=src, keep=keep))
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
        n = table_count(con, 'e')
        con.execute("CREATE OR REPLACE TEMP TABLE e_{}_{} AS SELECT * FROM e"
                    .format(tag, label))
        parts.append(("{}:{}".format(tag, label), "e_{}_{}".format(tag, label), n))
        print("  {:<16} {:>9,} edges".format("{}:{}".format(tag, label), n), flush=True)

BAYER_SRC = "IV/27A/catalog"
SIMBAD = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
CHUNK = 500
POS_SNR, POS_MAX_LY, POS_MAX_SEP = 10.0, 200.0, 1.0
POS_RATIO, POS_RUNNER_UP = 4.0, 2.0
SIMBAD_WANT = ("HD ", "HIP ", "HR ", "GJ ", "LHS ", "NLTT ", "TYC ", "SAO ", "LP ",
                "BD", "CD-", "CPD-")

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
GENITIVE_ALT = {"Cha": ["Chamaelontis"], "Com": ["Comae"], "PsA": ["Piscis Austrini"],
                "CrA": ["Coronae Austrinae"]}

GREEK = {
    "alf": "Alpha", "bet": "Beta", "gam": "Gamma", "del": "Delta", "eps": "Epsilon",
    "zet": "Zeta", "eta": "Eta", "the": "Theta", "tet": "Theta", "iot": "Iota",
    "kap": "Kappa", "lam": "Lambda", "mu.": "Mu", "nu.": "Nu", "ksi": "Xi",
    "omi": "Omicron", "pi.": "Pi", "rho": "Rho", "sig": "Sigma", "tau": "Tau",
    "ups": "Upsilon", "phi": "Phi", "chi": "Chi", "psi": "Psi", "ome": "Omega",
}

def game_names():
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
    return re.sub(r"\s+", " ", s).strip().casefold()

_ABBREV = {}
for _abb, _gen in GENITIVE.items():
    _ABBREV[_gen.casefold()] = _abb
for _abb, _alts in GENITIVE_ALT.items():
    for _alt in _alts:
        _ABBREV[_alt.casefold()] = _abb

_GREEK_ABB = {full.casefold(): abb for abb, full in GREEK.items()}

def _abbreviate(name):
    out = []
    if name.startswith("Gliese "):
        out.append("GJ " + name[7:])
    stem = None
    bits = name.split(" ")
    for n_words in (1, 2, 3):
        if len(bits) > n_words:
            tail = " ".join(bits[-n_words:]).casefold()
            if tail in _ABBREV:
                stem = " ".join(bits[:-n_words])
                out.append("{} {}".format(stem, _ABBREV[tail]))
                break
    if stem:
        head = stem.split(" ")[-1].casefold()
        if head in _GREEK_ABB:
            rest = " ".join(stem.split(" ")[:-1])
            greek = _GREEK_ABB[head]
            out.append(("{} {}".format(rest, greek) if rest else greek)
                       + " " + out[-1].rsplit(" ", 1)[1])
    return out

def positional_edges(unreachable, catalogue):
    path = fetch("hip_astro", "I/239/hip_main", "HIP,Plx,e_Plx,_Glon,_Glat")
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
    return {(cat, game) for cat, game in rows
            if cat in catalogue and game in unreachable}

XID_TYPES = ("HIP", "HR", "GJ", "LHS")

def simbad_catalogue_edges(catalogue):
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
            except Exception as exc:
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
    todo = sorted(unreachable)
    key = {_norm(n): n for n in todo}
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
            except Exception as exc:
                if attempt == 2:
                    raise SystemExit("  simbad: failed after 3 tries -- {}".format(exc))
                time.sleep(10)
        for line in text.splitlines()[1:]:
            parts = [p.strip().strip('"') for p in line.split('","')]
            if len(parts) != 2:
                continue
            game, cat = parts[0].strip('"'), parts[1].strip('"')
            cat = re.sub(r"\s+", " ", cat).strip()
            game = re.sub(r"^(NAME|V\*|\*)\s+", "", game).strip()
            game = key.get(_norm(game)) or abbrev.get(_norm(game)) or game
            forms = [cat]
            if cat.startswith("GJ "):
                forms.append("Gliese " + cat[3:])
            forms += [re.sub(r"[A-Za-z]$", "", f).strip() for f in list(forms)]
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
    con.execute("CREATE OR REPLACE TEMP TABLE g (a VARCHAR, b VARCHAR)")
    if pairs:
        con.executemany("INSERT INTO g VALUES (?, ?)", sorted(pairs))
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
    n = table_count(con, tbl)
    parts.append((tag, tbl, n))
    print("  {:<16} {:>9,} edges".format(tag, n), flush=True)

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
