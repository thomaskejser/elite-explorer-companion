import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
from common.db import (ROOT, INPUT, connect, has_primary_key,
                       report_merge, apply_comment_file)

OUT = INPUT / "body.parquet"

if OUT.exists():
    sys.exit(f"{OUT} already exists and is AUTHORITATIVE -- refusing to overwrite.\n"
             f"This seeder runs once. To apply the file:  python etl/body/load.py\n"
             f"If the file is wrong, correct it by hand. If you genuinely want a "
             f"fresh seed from the enum literals, delete the file first.")

STARS = [
    ("O",                     "O (Blue-White) Star"),
    ("B",                     "B (Blue-White) Star"),
    ("A",                     "A (Blue-White) Star"),
    ("F",                     "F (White) Star"),
    ("G",                     "G (White-Yellow) Star"),
    ("K",                     "K (Yellow-Orange) Star"),
    ("M",                     "M (Red dwarf) Star"),
    ("L",                     "L (Brown dwarf) Star"),
    ("T",                     "T (Brown dwarf) Star"),
    ("Y",                     "Y (Brown dwarf) Star"),
    ("AeBe",                  "Herbig Ae/Be Star"),
    ("TTS",                   "T Tauri Star"),
    ("W",                     "Wolf-Rayet Star"),
    ("WN",                    "Wolf-Rayet N Star"),
    ("WNC",                   "Wolf-Rayet NC Star"),
    ("WC",                    "Wolf-Rayet C Star"),
    ("WO",                    "Wolf-Rayet O Star"),
    ("CS",                    "CS Star"),
    ("C",                     "C Star"),
    ("CN",                    "CN Star"),
    ("CJ",                    "CJ Star"),
    ("CHd",                   "CHd Star"),
    ("MS",                    "MS-type Star"),
    ("S",                     "S-type Star"),
    ("D",                     "White Dwarf (D) Star"),
    ("DA",                    "White Dwarf (DA) Star"),
    ("DAB",                   "White Dwarf (DAB) Star"),
    ("DAO",                   "White Dwarf (DAO) Star"),
    ("DAZ",                   "White Dwarf (DAZ) Star"),
    ("DAV",                   "White Dwarf (DAV) Star"),
    ("DB",                    "White Dwarf (DB) Star"),
    ("DBZ",                   "White Dwarf (DBZ) Star"),
    ("DBV",                   "White Dwarf (DBV) Star"),
    ("DO",                    "White Dwarf (DO) Star"),
    ("DOV",                   "White Dwarf (DOV) Star"),
    ("DQ",                    "White Dwarf (DQ) Star"),
    ("DC",                    "White Dwarf (DC) Star"),
    ("DCV",                   "White Dwarf (DCV) Star"),
    ("DX",                    "White Dwarf (DX) Star"),
    ("N",                     "Neutron Star"),
    ("H",                     "Black Hole"),
    ("SuperMassiveBlackHole", "Supermassive Black Hole"),
    ("A_BlueWhiteSuperGiant", "A (Blue-White super giant) Star"),
    ("B_BlueWhiteSuperGiant", "B (Blue-White super giant) Star"),
    ("F_WhiteSuperGiant",     "F (White super giant) Star"),
    ("G_WhiteSuperGiant",     "G (White-Yellow super giant) Star"),
    ("K_OrangeGiant",         "K (Yellow-Orange giant) Star"),
    ("M_RedGiant",            "M (Red giant) Star"),
    ("M_RedSuperGiant",       "M (Red super giant) Star"),
]

PLANETS = [
    "Metal-rich body",
    "High metal content world",
    "Rocky body",
    "Icy body",
    "Rocky Ice world",
    "Earth-like world",
    "Water world",
    "Ammonia world",
    "Water giant",
    "Water giant with life",
    "Gas giant with water-based life",
    "Gas giant with ammonia-based life",
    "Class I gas giant",
    "Class II gas giant",
    "Class III gas giant",
    "Class IV gas giant",
    "Class V gas giant",
    "Helium-rich gas giant",
    "Helium gas giant",
]

WD = ("D", "DA", "DAB", "DAO", "DAZ", "DAV", "DB", "DBZ", "DBV", "DO", "DOV", "DQ",
      "DC", "DCV", "DX")
STAR_K = {c: 14057.0 for c in WD}
STAR_K["N"] = 22628.0
STAR_K["H"] = 22628.0
STAR_K["SuperMassiveBlackHole"] = 33.5678
STAR_DEFAULT_K = 1200.0

PLANET_K = {
    "Metal-rich body":                  (21790.0, 21790.0 + 65631.0),
    "High metal content world":         (9654.0, 9654.0 + 100677.0),
    "Class II gas giant":               (9654.0, 9654.0 + 100677.0),
    "Water world":                      (64831.0, 64831.0 + 116295.0),
    "Earth-like world":                 (64831.0 + 116295.0, None),
    "Ammonia world":                    (96932.0, None),
    "Class I gas giant":                (1656.0, None),
}
PLANET_DEFAULT = (300.0, 300.0 + 93328.0)

con = connect()

tf = {r[0] for r in con.execute("""
    SELECT DISTINCT sub_type FROM spansh_body
    WHERE type = 'Planet' AND terraforming_state = 'Terraformable'
      AND sub_type IS NOT NULL""").fetchall()}
print(f"terraforming candidates observed in the data: {', '.join(sorted(tf))}")

counts = dict(con.execute("""
    SELECT sub_type, count(*) FROM spansh_body
    WHERE sub_type IS NOT NULL GROUP BY 1""").fetchall())

rows = []
for code, name in STARS:
    rows.append(["star", name, False, code, name in counts, counts.get(name, 0),
                 STAR_K.get(code, STAR_DEFAULT_K), None, "star"])
for name in PLANETS:
    k, kt = PLANET_K.get(name, PLANET_DEFAULT)
    rows.append(["planet", name, name in tf, None, name in counts, counts.get(name, 0),
                 k, kt, "planet"])

existing = {}
if OUT.exists():
    existing = {(t, b): i for t, b, i in con.execute(
        f"""SELECT type, body, body_id FROM '{OUT.as_posix()}'""").fetchall()}
    print(f"reusing {len(existing)} body_id(s) from the existing {OUT.name}")
elif con.execute("""SELECT count(*) FROM duckdb_tables()
                    WHERE schema_name='main' AND table_name='body'""").fetchone()[0]:
    existing = {(t, b): i for t, b, i
                in con.execute("SELECT type, body, body_id FROM body").fetchall()}
    print(f"adopting {len(existing)} existing body_id(s) from the body table")

next_id = (max(existing.values()) + 1) if existing else 1
assigned, fresh = [], []
for r in rows:
    key = (r[0], r[1])
    if key in existing:
        bid = existing[key]
    else:
        bid = next_id
        next_id += 1
        fresh.append(f"{bid}={r[0]}/{r[1]}")
    assigned.append([bid] + r)
assigned.sort(key=lambda r: r[0])
if fresh:
    print(f"assigned {len(fresh)} new body_id(s): {', '.join(fresh)}")

gone = sorted(set(existing) - {(r[1], r[2]) for r in assigned})
if gone:
    print(f"WARNING: {len(gone)} previously-keyed type(s) no longer present, their "
          f"body_id is now RETIRED and must not be reused: {gone}")

assigned_cols = ["body_id", "type", "body", "is_terraform_candidate",
                 "code", "observed", "bodies", "cr_value", "cr_value_terraformable",
                 "value_formula"]
con.execute("CREATE OR REPLACE TEMP TABLE seed (body_id INTEGER, type VARCHAR, "
            "body VARCHAR, is_terraform_candidate BOOLEAN, code VARCHAR, "
            "observed BOOLEAN, bodies BIGINT, cr_value DOUBLE, "
            "cr_value_terraformable DOUBLE, value_formula VARCHAR)")
con.executemany("INSERT INTO seed VALUES (?,?,?,?,?,?,?,?,?,?)", assigned)

n, ns, np_, ntf, nobs = con.execute("""
    SELECT count(*), count(*) FILTER (WHERE type='star'),
           count(*) FILTER (WHERE type='planet'),
           count(*) FILTER (WHERE is_terraform_candidate),
           count(*) FILTER (WHERE NOT observed) FROM seed""").fetchone()
print(f"\nseeded {n} rows ({ns} star, {np_} planet), "
      f"{ntf} terraform candidates, {nobs} unobserved")

print(f"\n  {'id':>4}  {'type':<8}{'code':<24}{'body':<36}{'tf':>4}{'bodies':>14}")
for r in con.execute("""SELECT body_id, type, coalesce(code,''), body,
        is_terraform_candidate, bodies, observed FROM seed
        ORDER BY body_id""").fetchall():
    flag = "" if r[6] else "   (unobserved)"
    print(f"  {r[0]:>4}  {r[1]:<8}{r[2]:<24}{r[3]:<36}"
          f"{('Y' if r[4] else '-'):>4}{r[5]:>14,}{flag}")

INPUT.mkdir(exist_ok=True)
con.execute(f"""COPY (SELECT * FROM seed ORDER BY body_id)
                TO '{OUT.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
back = con.execute(f"""SELECT count(*), count(DISTINCT body_id), min(body_id), max(body_id)
                       FROM '{OUT.as_posix()}'""").fetchone()
print(f"\nwrote {OUT}  ({back[0]} rows, {OUT.stat().st_size:,} bytes)")
print(f"  read back: {back[1]} distinct body_id, range {back[2]}..{back[3]}")
same = con.execute(f"""SELECT count(*) FROM (
    SELECT * FROM seed EXCEPT SELECT * FROM '{OUT.as_posix()}')""").fetchone()[0]
print(f"  round-trips identical: {same == 0}")

con.close()
print("\nNOTE the `body` table was NOT touched. Merge with:"
      "\n  python etl/body/load.py")
print("\nDONE_BUILD_BODY")
