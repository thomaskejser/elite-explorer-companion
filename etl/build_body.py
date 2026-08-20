"""SEED input/body.parquet -- the authoritative reference dimension of body types.

ONE-TIME SEEDER. This script only writes the PARQUET, and only if it does not
already exist. It does NOT touch the `body` table: that is a merge target loaded by
etl/load_body.py, and is never dropped.

input/body.parquet is authoritative and safe to hand-edit, so this script REFUSES
to run at all once the file exists -- there is deliberately no --force. Regenerating
from these literals would discard hand edits, and there is no way for the script to
know whether that is what you meant. If the file is wrong, correct it by hand (or
delete it and reseed knowingly); if the TABLE is wrong, fix it and re-run
etl/load_body.py.

Normal workflow after the first seed is: edit input/body.parquet, then run
etl/load_body.py to merge.

One row per distinct body type, not per body. This is the lookup that everything
else should join to instead of re-hardcoding subtype strings.

  body_id                 INTEGER PRIMARY KEY, plain sequence number. THE key
                          other tables are meant to carry. Ids are STABLE across
                          rebuilds: this script reads the ids already in the table
                          and only allocates new ones (max+1) for types it has
                          never seen, so refreshing `bodies` never repoints a
                          foreign key. Never renumber, and never reuse a retired
                          id -- the script warns if a previously-keyed type
                          disappears.
  type                    'star' or 'planet'
  body                    canonical name. Matches spansh_body.sub_type exactly
                          wherever that type has ever been observed, so it joins
                          straight onto the 569M-row body table.
  is_terraform_candidate  TRUE if the game generates this type as a terraforming
                          candidate.
  code                    FULL journal star code, variant included (DA vs DAB vs
                          DAV vs DAZ; W vs WN vs WNC vs WC vs WO). NULL for
                          planets. This is what the journal's StarType field
                          carries, so it is the join key for live journal data --
                          sub_type names are a Spansh/EDSM presentation layer and
                          never appear in a journal.
  observed                TRUE if we hold at least one body of this type.
  bodies                  count in spansh_body (0 where observed is FALSE).
  cr_value                the `k` constant for Frontier's exploration-value formula,
  cr_value_terraformable  and its terraformable form (NULL where no bonus exists).
  value_formula           'star' or 'planet' -- which formula k feeds.

SCAN VALUE, and why these are not credit amounts. k IS denominated in credits, but the
payout depends on the body's MASS, so a single figure per type does not exist:

    planets:  base = max(k + k * mass_em^0.2 * 0.56591828, 500)
    stars:    base = k + solar_masses * k / 66.25

Then multipliers apply, none of them per-type, so none are stored here:
    first discovered                    x2.6
    already discovered + mapped         x3.3333333
    first mapped only                   x8.0956
    first discovered AND first mapped   x3.699622554  (then x2.6)
    efficient mapping bonus             x1.25
    Odyssey mapping bonus               + max(v * 0.3, 555)   on mapped values only
STARS CANNOT BE MAPPED, so only base and first-discovered apply to them.

SOURCE: EDDiscovery's ScanEstimatedValues, EliteDangerousCore at
EliteDangerous/FrontierData/Enumerations/EstimatedValues.cs, citing MattG's "Exploration
value formulae" thread on the Frontier forums. Re-fetched and byte-compared 2026-08-12:
unchanged. *** ONLY THE ED 3.3+ BRANCH IS CURRENT. *** That file carries three constant
sets (pre-2.2, pre-3.3, 3.3+) selected by the scan's timestamp. The higher figures quoted
in many places online -- 155581 for water worlds, 2880 for ordinary stars, 54309 for
black holes -- are the SUPERSEDED 3.2 set. Everything here is 3.3+.

Type lists come from the game's own enums (EDStar / EDPlanet in EDDiscovery's
EliteDangerousCore, "naming as per Journal 15.2"), NOT from what we happen to
have seen -- so types that exist but which nobody in our data has scanned still
get a row, flagged observed=FALSE. Six white-dwarf/carbon variants are in that
position. Non-star EDStar members (RoguePlanet, Nebula, StellarRemnantNebula) are
excluded, as is the speculative X.

TERRAFORMING, and why Earth-like is FALSE: only four types are ever generated
with terraforming_state='Terraformable' -- High metal content world (8,503,277),
Water world (1,986,211), Rocky body (284,686) and Metal-rich body (76). An
Earth-like world is the terraforming END STATE, not a candidate: across 451,680
ELWs not one is 'Terraformable' (333,518 'Not terraformable', 116,261 null, and
1,901 'Terraformed' in populated space). Note this is deliberately NOT the same
question as scan value -- EDDiscovery folds the terraform bonus into the ELW k
constant because a scanned ELW pays as if terraformable. If you want value, use
the k constants, not this column.

Usage:  python etl/build_body.py     # first seed only; refuses if the file exists
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import (ROOT, INPUT, connect, has_primary_key,
                       report_merge, apply_comment_file)

OUT = INPUT / "body.parquet"

# No --force, by design: regenerating would discard hand edits to an authoritative
# file and the script cannot know whether that was intended. Corrections are manual.
if OUT.exists():
    sys.exit(f"{OUT} already exists and is AUTHORITATIVE -- refusing to overwrite.\n"
             f"This seeder runs once. To apply the file:  python etl/load_body.py\n"
             f"If the file is wrong, correct it by hand. If you genuinely want a "
             f"fresh seed from the enum literals, delete the file first.")

# (code, canonical name) in EDStar enum order. Names match spansh_body.sub_type
# where observed; the six unobserved variants follow the same naming pattern.
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

# EDPlanet enum order.
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

# --- scan-value k constants: stars keyed on the journal code ------------------
WD = ("D", "DA", "DAB", "DAO", "DAZ", "DAV", "DB", "DBZ", "DBV", "DO", "DOV", "DQ",
      "DC", "DCV", "DX")
STAR_K = {c: 14057.0 for c in WD}          # every white dwarf variant
STAR_K["N"] = 22628.0                       # neutron star
STAR_K["H"] = 22628.0                       # black hole -- same k as a neutron
STAR_K["SuperMassiveBlackHole"] = 33.5678   # NOT a typo: three orders of magnitude LOWER
STAR_DEFAULT_K = 1200.0                     # every other star, Wolf-Rayet included

# --- planets: keyed on the body name, (non-terraformable, terraformable) ------
# Earth-like carries the terraform bonus unconditionally (k = 64831 + 116295), so it has
# no separate terraformable figure. Ammonia and Class I gas giants have no bonus at all.
PLANET_K = {
    "Metal-rich body":                  (21790.0, 21790.0 + 65631.0),
    "High metal content world":         (9654.0, 9654.0 + 100677.0),
    "Class II gas giant":               (9654.0, 9654.0 + 100677.0),
    "Water world":                      (64831.0, 64831.0 + 116295.0),
    "Earth-like world":                 (64831.0 + 116295.0, None),
    "Ammonia world":                    (96932.0, None),
    "Class I gas giant":                (1656.0, None),
}
PLANET_DEFAULT = (300.0, 300.0 + 93328.0)   # every other planet class

con = connect()

# Derive candidacy from the data rather than asserting it: any type the game has
# ever generated as 'Terraformable'. 437.7M planets is a large enough sample that
# absence is meaningful.
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

# body_id must be STABLE -- other tables key to it, so renumbering would silently
# repoint every foreign key. We never derive it from row order: an entry that
# already has an id anywhere (in the existing parquet, or in the table) keeps it,
# and only genuinely new types get one, from max+1. Reseeding after a data refresh
# is therefore a no-op for ids even though `bodies` changes.
existing = {}
if OUT.exists():
    existing = {(t, b): i for t, b, i in con.execute(
        f"""SELECT type, body, body_id FROM '{OUT.as_posix()}'""").fetchall()}
    print(f"reusing {len(existing)} body_id(s) from the existing {OUT.name}")
elif con.execute("""SELECT count(*) FROM duckdb_tables()
                    WHERE schema_name='main' AND table_name='body'""").fetchone()[0]:
    # No parquet yet but the table predates it: adopt the table's ids so the first
    # seed cannot renumber keys that already exist.
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

# Write the parquet ONLY. The `body` table is a merge target owned by
# load_body_dim.py and is deliberately not touched here.
assigned_cols = ["body_id", "type", "body", "is_terraform_candidate",
                 "code", "observed", "bodies", "cr_value", "cr_value_terraformable",
                 "value_formula"]
# Column ORDER matters and must match load_body.py's CREATE TABLE exactly: the scan-value
# columns are appended last there too, because ALTER TABLE ADD COLUMN can only append and
# a migrated database must end up the same shape as a freshly created one.
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
      "\n  python etl/load_body.py")
print("\nDONE_BUILD_BODY")
