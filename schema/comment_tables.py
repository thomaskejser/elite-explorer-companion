"""Attach a COMMENT ON description to every table in elite_mapping.duckdb.

Why: a 73GB database with 30 tables and several near-identical names
(edastro_star vs edastro_star_system vs edastro_neutron_star; fringe_sectors vs
fringe_sectors_debiased) is unreadable without them, and the single most
expensive mistakes in this project have all been provenance mistakes -- treating
a 7-day slice as a full catalogue, or a lower bound as an estimator. Each comment
therefore says what the table IS, where it came from, and what it is NOT.

Read them back with:
    SELECT table_name, comment FROM duckdb_tables() ORDER BY table_name;

The script ASSERTS that every table has a description. Add a new table without
adding it to COMMENTS here and this fails -- that is deliberate.

Usage:  python schema/comment_tables.py
"""
import duckdb, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# --- RAW provider snapshots -------------------------------------------------
# The slice-vs-full distinction is the single most important fact about each one.
RAW = {
 "edsm_star_system":
   "RAW EDSM systemsWithCoordinates dump (2026-07-10), 97.1M systems. FULL. The "
   "origin of the system spine and of most name/coordinate resolution.",
 "edsm_celestial_body":
   "RAW EDSM bodies7days dump (2026-07-10), 2.5M bodies. *** 7-DAY SLICE, NOT a "
   "catalogue *** -- superseded by spansh_body for all body facts. Kept only for "
   "its richer per-body structs (atmosphereComposition, solidComposition, belts).",
 "edsm_codex_entry":
   "RAW EDSM codex dump (2026-07-10), 15.8M entries. FULL. Source of NSP labels "
   "and of name='Green Gas Giant' rows feeding app/poi.parquet.",
 "edastro_star_system":
   "RAW EDAstro edastro_systems7days (2026-07-10), 572,833 systems. *** 7-DAY "
   "SLICE *** . EDAstro is ~99.1% a SUBSET of EDSM, not a superset.",
 "edastro_star":
   "RAW EDAstro edastro_stars7days (2026-07-10), 890,185 stars. *** 7-DAY SLICE "
   "*** . For a full star census use edastro_known_rare / edastro_neutron_star.",
 "edastro_planet":
   "RAW EDAstro edastro_planets7days (2026-07-10), 2.7M planets. *** 7-DAY SLICE "
   "*** -- superseded by spansh_body. Retains a materials struct Spansh lacks.",
 "edastro_known_rare":
   "FULL EDAstro per-class catalogues, Black-Holes.csv + Wolf-Rayet-stars.csv "
   "(2026-08-09), 516,714 stars. NOT a slice: this is every BH/WR ever reported, "
   "and is what lets us EXCLUDE already-discovered systems from the candidate pool.",
 "edastro_neutron_star":
   "FULL EDAstro neutron-stars.csv (2026-08-09), 4,144,305 stars across 4,073,359 "
   "systems. Body level, carries rot_period_s. A NAVIGATION source (feeds "
   "app/neutron.parquet), NOT an exclusion signal -- neutrons stay valid targets. "
   "There is no 'pulsar' body type in the game; the whole population is pulsar-regime.",
 "edastro_boxel_stats":
   "FULL EDAstro boxel-stats.csv (2026-08-10), 794,017 boxels. *** e/f/g/h ONLY -- "
   "no d and below *** . helium_avg/gas_giants are aggregates of SCANNED bodies, "
   "not Stellar Forge generator inputs, so they carry the same discovery bias as "
   "any scan data. Drives p_hr in build_candidates.py. GOTCHA: EDAstro writes a "
   "SPACE before the boxel part number ('Thaileia ZK-O e 6'); our key has none. "
   "Column `boxel` is the translated key, `edastro_boxel` the original.",
 "canonn_codex_event":
   "RAW Canonn codex dump (2026-07-10), 4.7M events. hud_category='Cloud' is the "
   "reliable Notable Stellar Phenomena flag and is broader than its name suggests "
   "(crystals, trees, molluscs, pods all announce as NSP). 'Geology' is EXCLUDED "
   "from poi.parquet: it needs a landing, not a look.",
 "edastro_point_of_interest":
   "RAW EDAstro GEC combined feed (2026-07-10), 2,749 curated POIs. GOTCHA: `name` "
   "is the POI's own nickname, NOT the system name -- joining on name inflates the "
   "67 green-gas-giant systems to 117. Join on id64 only.",
 "spansh_system":
   "RAW Spansh galaxy dump, systems (2026-07-12), 194,696,927 systems, 0 duplicate "
   "ids. FULL galaxy. Origin of the sys_feat spine.",
 "spansh_body":
   "RAW Spansh galaxy dump, bodies (2026-07-12), 569,697,301 bodies (437.7M planets, "
   "132.0M stars) across 75,066,911 systems. FULL galaxy. *** CARRIES NO DSS/mapped "
   "FLAG *** -- no source does. Every row is at least FSS-detected; which bodies were "
   "probe-mapped is NOT recoverable. Nor is this a galaxy census: only 38.6% of "
   "spine systems have any body data at all, and within the systems that do we "
   "hold ~77% of the bodies the game itself declares. Never quote a count from "
   "here as a galaxy total.",
 "ingest_manifest":
   "Provenance ledger: one row per raw ingest with source URL, local path, byte size, "
   "row count, timestamp and a note recording slice-vs-full. Check here FIRST before "
   "trusting any raw table as complete.",
}

# --- DERIVED model / feature layers ----------------------------------------
DERIVED = {
 "sys_feat":
   "THE SYSTEM SPINE (03a_build_features.py), 194,696,927 rows -- the table almost "
   "everything joins to. mass_code is parsed from the procedural NAME and is a hard "
   "Stellar Forge gate: black holes occur only in e/f/g/h, Wolf-Rayet only in h. "
   "r_sgra/plane_r/height are galactic position features. is_scanned marks the 38.6% "
   "with body facts; has_bh/has_wr/has_neutron are meaningful ONLY where n_stars>0.",
 "bhwr_system":
   "Per-system BH/WR/neutron labels over SCANNED systems only (03a_build_features.py), "
   "75.1M rows. The supervised training target: positives plus reliable negatives.",
 "star_agg":
   "Per-system rare-star-class flags -- neutron, white dwarf, Herbig Ae/Be, O-type, "
   "supergiant (03m_rare_stars_build.py), 74.7M rows. Scanned systems only.",
 "bhwr_candidates":
   "Scored unscanned candidate pool (03c_model.py), 2.26M systems. Trained only on "
   "scanned systems using features also known for unscanned ones (mass_code + "
   "position). RANKINGS are the trustworthy output; absolute probabilities here are "
   "superseded by app/candidates.parquet, which applies flight calibration.",
 "star_boxels":
   "Per-boxel aggregates (03m_rare_stars_build.py, corrected by 03u_star_boxels_fix.py), "
   "981,286 boxels. *** `pop` = max(index)+1 is a LOWER BOUND on boxel population, NOT "
   "an estimator -- it converges from below and understates sparsely-visited boxels. *** "
   "`missing` = internal index gaps strictly between min_idx and max_idx, counted ONLY in "
   "`dense` boxels; it is NOT pop-in_db (that was the fill-from-0 bug 03u fixed).",
 "theorised_boxels":
   "Boxel-level expected-undiscovered counts (03e/03f/03s/03t). Stellar-Forge-implied, "
   "not observed. Thin and heavily core-biased after the 03s correction.",
 "theorised_system":
   "Individual Stellar-Forge-implied systems not present in any dump (03f, fixed by 03s), "
   "57,700 rows -- enumerated internal index gaps in dense boxels. A valid LOWER bound on "
   "what exists. Only ~208k galaxy-wide and near zero in the fringe, which is why "
   "sector_unscanned prefers real catalogued-but-unscanned systems instead.",
 "sector_lookup":
   "Procedural sector name -> position (pgnames.py), 12,064 sectors. GOTCHA: ~2.3% "
   "(277) of sector names span more than one 1280-ly cell, 263 of them hand-authored "
   "('Col 359 Sector' spans 6 cells, 'NGC 2546 Sector' 8), so sector name is NOT a "
   "safe proxy for a lattice cell. Lattice: 1280 ly, origin (-49985,-40985,-24105).",
}

# --- DERIVED ranking / scoping layers --------------------------------------
RANKING = {
 "sector_unscanned":
   "Per-sector expected finds over the RELIABLE pool (03v_unscanned_pool.py), 9,586 "
   "sectors: real catalogued-but-unscanned systems with exact coordinates, preferred "
   "over the thin theorised layer.",
 "rare_star_sectors":
   "Tier-1 rare-star sector ranking (03n_rare_stars_rank.py), 9,586 sectors, via the "
   "kNN local de-biased rate validated for BH/WR.",
 "explore_sectors":
   "Best sectors to explore, local de-biased rate with a near-Sol preference "
   "(03l_local_debias_rank.py), 4,396 sectors. Local because BH rate has directional "
   "structure, so a radius-only curve fails cross-region (shown by 03k).",
 "fringe_sectors":
   "Outer-disk (fringe) sectors likely to hold undiscovered BH/WR (03g_fringe_sectors.py), "
   "239 sectors. Fringe metric is plane_r; core excluded. RANKINGS are trustworthy, "
   "absolute counts are upper-ish.",
 "fringe_sectors_debiased":
   "De-biased fringe counts (03j_debias_apply.py), 6 rows. True Forge rate is estimated "
   "from WELL-SAMPLED boxels (>=10 scanned AND >=80% of pop scanned), where the scanned "
   "set approximates the full population and the rate is therefore unbiased.",
 "special_systems":
   "Raxxla-hunt scoping (03p_special_systems.py), 15,405 rows: hand-authored "
   "non-procedural systems plus the curated mystery/restricted/historical POI layer. "
   "Search-space narrowing ONLY -- explicitly NOT a prediction (n=0 known Raxxla).",
}

COMMENTS = {**RAW, **DERIVED, **RANKING}

# Tables whose own build script writes a fuller COMMENT than belongs here, so that
# the description lives next to the code that produces it. This script does not
# overwrite them -- it only VERIFIES they carry a non-empty comment, and fails if
# one has been dropped (e.g. by a CREATE OR REPLACE that forgot to re-comment).
SELF_DOCUMENTED = {
    # comment TEXT lives in schema/<table>_comment.sql; these scripts re-assert it
    "body":             "etl/load_body.py",  # text: schema/body_comment.sql
    "body_type_census": "etl/build_body_type_census.py",
    "sector":           "etl/build_sector.py",
    "region":           "etl/load_region.py",
    "system_known":     "etl/build_system_known.py",
    "system_body":      "etl/build_system_body.py",
    "system_predicted": "etl/build_system_predicted.py",
}

con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"))
have = {r[0] for r in con.execute(
    "SELECT table_name FROM duckdb_tables() WHERE schema_name='main'").fetchall()}

documented = COMMENTS.keys() | SELF_DOCUMENTED.keys()
missing = sorted(have - documented)
stale   = sorted(documented - have)

# Verify, do not touch, the self-documented ones.
blank = []
for t in sorted(have & SELF_DOCUMENTED.keys()):
    c = con.execute("SELECT comment FROM duckdb_tables() WHERE schema_name='main' "
                    "AND table_name = ?", [t]).fetchone()
    if not (c and c[0] and c[0].strip()):
        blank.append(t)
    else:
        print(f"kept self-documented comment on {t} "
              f"({len(c[0]):,} chars, from {SELF_DOCUMENTED[t]})")
if blank:
    print(f"\nFAIL: self-documented table(s) have lost their comment: {', '.join(blank)}")
    for t in blank:
        print(f"  re-run {SELF_DOCUMENTED[t]}")
    con.close()
    sys.exit(1)

if stale:
    print(f"NOTE: {len(stale)} described table(s) no longer exist: {', '.join(stale)}")

applied = 0
for t in sorted(have & COMMENTS.keys()):
    body = COMMENTS[t].replace("'", "''")
    con.execute(f"COMMENT ON TABLE {t} IS '{body}'")
    applied += 1
print(f"applied {applied} table comment(s)")

if missing:
    print(f"\nFAIL: {len(missing)} table(s) have NO description:")
    for t in missing:
        print(f"  - {t}")
    print("Add them to COMMENTS in schema/comment_tables.py.")
    con.close()
    sys.exit(1)

# ETL.md also requires a comment on every COLUMN of every table we own. Enforced for
# the etl/-managed tables only; the legacy scripts/ pipeline is a known deviation.
gaps = []
for t in sorted(have & SELF_DOCUMENTED.keys()):
    miss = [r[0] for r in con.execute(
        """SELECT column_name FROM duckdb_columns()
           WHERE schema_name='main' AND table_name = ? AND comment IS NULL
           ORDER BY column_index""", [t]).fetchall()]
    if miss:
        gaps.append((t, miss))
if gaps:
    print("\nFAIL: etl-managed table(s) have undocumented COLUMNS:")
    for t, miss in gaps:
        print(f"  {t}: {', '.join(miss)}  -> re-run {SELF_DOCUMENTED[t]}")
    con.close()
    sys.exit(1)
for t in sorted(have & SELF_DOCUMENTED.keys()):
    n = con.execute("""SELECT count(*) FROM duckdb_columns()
                       WHERE schema_name='main' AND table_name = ?""", [t]).fetchone()[0]
    print(f"  {t}: all {n} column(s) documented")

print(f"\nall {len(have)} tables in main have a description\n")
print(f"  {'table':<30}{'rows':>14}  description")
for t, n, c in con.execute("""SELECT table_name, estimated_size, comment
        FROM duckdb_tables() WHERE schema_name='main'
        ORDER BY estimated_size DESC""").fetchall():
    flag = "" if c else "  <== MISSING"
    print(f"  {t:<30}{(n or 0):>14,}  {(c or '')[:64]}{flag}")
con.close()
print("\nDONE_COMMENT_TABLES")
