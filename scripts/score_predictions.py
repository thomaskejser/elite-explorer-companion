"""Score a snapshot of `system_predicted` against what the galaxy has since revealed.

THE ONLY HONEST TEST OF THIS MODEL. Every rate in `system_predicted` is fitted on systems
commanders have already scanned, then used to answer a question about systems nobody has
scanned. Whether that transfer works cannot be checked against the data it was fitted on;
it can only be checked by predicting, waiting, and looking. That is what this does:

    1. Before a refresh, snapshot system_predicted and the set of systems that already
       had body data.  (staging.pred_snapshot_<date>, staging.scanned_before_<date>)
    2. Ingest a provider delta and merge it, so new scans land in system_body.
    3. Run this. A snapshot row whose system has body data NOW and had none THEN is a
       RESOLVED prediction, and the bodies are the answer we predicted before knowing it.

    python scripts/score_predictions.py                       # newest snapshot
    python scripts/score_predictions.py --snapshot pred_snapshot_20260829

*** THREE THINGS THIS CANNOT TELL YOU, ALL OF THEM STRUCTURAL. ***

1. THE RESOLVED SET IS NOT A RANDOM SAMPLE. Commanders fly to systems that already look
   interesting -- bright, close, on a neutron route, or flagged by a tool very much like
   this one. So the systems that got scanned this month are enriched for exotic stars
   relative to a random unscanned system, and an observed rate ABOVE the predicted one is
   the expected direction of that bias, not proof the model underestimates.

2. ABSENCE OF A BODY TYPE IS NOT ABSENCE IN THE SYSTEM. A system counts as scanned as soon
   as ONE body is reported. No source carries a DSS/mapped flag, so a system with a
   partial honk looks identical to a fully surveyed one, and every "no black hole here"
   is really "no black hole reported yet". Every observed rate below is therefore a LOWER
   BOUND, and the shortfall grows with how shallow the average scan was.

3. THE BOXEL-PREDICTED LAYER BARELY RESOLVES. is_catalog = FALSE rows are systems inferred
   from gaps in the Forge index; they are in no dump, so nothing links them to a scan
   except the name turning up. Expect a resolved count near zero there, and read it as
   "not yet testable" rather than "wrong".

WHAT A GOOD RESULT LOOKS LIKE. Not observed == predicted -- that would be luck given the
bias above. It is MONOTONICITY: sort the resolved systems by predicted probability and the
observed rate should climb with it. A model that ranks correctly is useful even when its
absolute numbers are off, and ranking is all the overlay ever asks of it.
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.db import connect

SNAP = (sys.argv[sys.argv.index("--snapshot") + 1]
        if "--snapshot" in sys.argv else None)

# Target -> the body.code values that settle it. Kept beside the model's own column names
# so a target cannot be scored against the wrong bodies.
TARGETS = [
    ("p_bh",         "black hole",   ("H", "SupermassiveBlackHole", "SuperMassiveBlackHole")),
    ("p_wr",         "Wolf-Rayet",   ("W", "WN", "WNC", "WC", "WO")),
    ("p_neutron",    "neutron",      ("N",)),
    ("p_wd",         "white dwarf",  ("D", "DA", "DAB", "DAO", "DAV", "DAZ", "DB", "DBV",
                                      "DBZ", "DC", "DCV", "DO", "DOV", "DQ", "DX")),
    ("p_herbig",     "Herbig Ae/Be", ("AeBe",)),
    ("p_otype",      "O-type",       ("O",)),
    ("p_supergiant", "supergiant",   ("A_BlueWhiteSuperGiant", "B_BlueWhiteSuperGiant",
                                      "F_WhiteSuperGiant", "G_WhiteSuperGiant",
                                      "M_RedSuperGiant")),
]

con = connect(read_only=True)

if not SNAP:
    rows = con.execute("""SELECT table_name FROM duckdb_tables()
                          WHERE schema_name = 'staging'
                            AND table_name LIKE 'pred_snapshot_%'
                          ORDER BY table_name DESC LIMIT 1""").fetchall()
    if not rows:
        sys.exit("no staging.pred_snapshot_* table -- nothing to score against.\n"
                 "Snapshot system_predicted BEFORE the next refresh, or there is no\n"
                 "before-picture to compare with.")
    SNAP = rows[0][0]
BEFORE = SNAP.replace("pred_snapshot_", "scanned_before_")
print(f"database: {con.execute('SELECT current_database()').fetchone()[0]}")
print(f"snapshot: staging.{SNAP}   watermark: staging.{BEFORE}\n")

# ---------------------------------------------------------------- resolve ------------
# Join on id64, never on the name: system_known.system_id IS the id64. A system counts as
# resolved only through a SURVEYED body -- a catalogue hit contains its target by construction.
CATALOGUE_ONLY = "('edastro_rare', 'edastro_neutron', 'canonn_codex')"
con.execute(f"""CREATE OR REPLACE TEMP TABLE newly AS
SELECT p.*, k.system_id,
       EXISTS (SELECT 1 FROM system_body b WHERE b.system_id = k.system_id
               AND b.source NOT IN {CATALOGUE_ONLY}) AS surveyed
FROM staging.{SNAP} p
JOIN system_known k ON k.system_id = p.system_id64
WHERE EXISTS (SELECT 1 FROM system_body b WHERE b.system_id = k.system_id)
  AND NOT EXISTS (SELECT 1 FROM staging.{BEFORE} s WHERE s.system_id = k.system_id)""")
con.execute("CREATE OR REPLACE TEMP TABLE resolved AS SELECT * EXCLUDE (surveyed) FROM newly WHERE surveyed")

tot, res, catalogue = con.execute(f"""SELECT (SELECT count(*) FROM staging.{SNAP}),
                                             (SELECT count(*) FROM resolved),
                                             (SELECT count(*) FROM newly WHERE NOT surveyed)""").fetchone()
print(f"  {tot:,} predictions in the snapshot")
print(f"  {res:,} RESOLVED -- no body data then, a surveyed body now")
print(f"  {catalogue:,} gained only a catalogue hit (BH/WR, neutron or Canonn list) and are NOT scored:")
print(f"     such a system contains its target by construction, so scoring it inflates 'found'")
if not res:
    sys.exit("\n  Nothing resolved: no snapshot system was newly scanned in this window.\n"
             "  That is a statement about the delta, not about the model.")
for lab, n in con.execute("""SELECT CASE WHEN is_catalog THEN 'catalogued'
                                         ELSE 'boxel-predicted' END, count(*)
                             FROM resolved GROUP BY 1 ORDER BY 2 DESC""").fetchall():
    print(f"     {lab:<18}{n:>10,}")

# ---------------------------------------------------------------- outcomes -----------
codes = {t: c for t, _, c in TARGETS}
sel = ",\n       ".join(
    "max(CASE WHEN b.code IN ({}) THEN 1 ELSE 0 END) AS found_{}"
    .format(",".join("'%s'" % c for c in codes[col]), col[2:])
    for col, _, _ in TARGETS)
con.execute(f"""CREATE OR REPLACE TEMP TABLE outcome AS
SELECT r.system_id, {sel}
FROM resolved r
JOIN system_body sb ON sb.system_id = r.system_id
LEFT JOIN body b ON b.body_id = sb.body_id
GROUP BY 1""")

print(f"\n  PREDICTED vs FOUND, over the {res:,} resolved systems")
print(f"    {'target':<14}{'mean p':>9}{'expected':>11}{'found':>9}{'ratio':>8}")
for col, label, _ in TARGETS:
    exp, got = con.execute(f"""SELECT sum(r.{col}), sum(o.found_{col[2:]})
                               FROM resolved r JOIN outcome o USING (system_id)""").fetchone()
    mean = exp / res
    ratio = (got / exp) if exp else 0
    print(f"    {label:<14}{mean:>9.4f}{exp:>11,.0f}{got:>9,}{ratio:>8.2f}x")

# ---------------------------------------------------------------- calibration --------
# THE MONOTONICITY TEST, which is the one that matters: does a higher predicted
# probability actually mean a higher hit rate? Deciles of p, not equal-width bins --
# the distribution is skewed and equal-width bins would put almost everything in one.
for col, label, _ in TARGETS[:2]:
    print(f"\n  CALIBRATION -- {label}: does a higher p mean a higher hit rate?")
    print(f"    {'decile':<8}{'p range':>18}{'systems':>10}{'expected':>10}{'found':>8}"
          f"{'rate':>9}")
    for r in con.execute(f"""
        WITH d AS (SELECT r.{col} AS p, o.found_{col[2:]} AS hit,
                          ntile(10) OVER (ORDER BY r.{col}) AS dec
                   FROM resolved r JOIN outcome o USING (system_id))
        SELECT dec, min(p), max(p), count(*), sum(p), sum(hit), avg(hit)
        FROM d GROUP BY 1 ORDER BY 1""").fetchall():
        rng = f"{r[1]:.3f}-{r[2]:.3f}"
        print(f"    {r[0]:<8}{rng:>18}{r[3]:>10,}{r[4]:>10,.0f}{r[5]:>8,}{r[6]:>9.4f}")

# ---------------------------------------------------------------- by mass code -------
print("\n  BY MASS CODE -- the gate the whole model rests on (RECOMMENDATIONS R1)")
print(f"    {'mc':<4}{'systems':>10}{'exp bh':>9}{'bh':>7}{'exp wr':>9}{'wr':>7}")
for r in con.execute("""SELECT r.mass_code, count(*), sum(r.p_bh), sum(o.found_bh),
                               sum(r.p_wr), sum(o.found_wr)
                        FROM resolved r JOIN outcome o USING (system_id)
                        GROUP BY 1 ORDER BY 1""").fetchall():
    print(f"    {r[0]:<4}{r[1]:>10,}{r[2]:>9.1f}{r[3]:>7,}{r[4]:>9.1f}{r[5]:>7,}")

print("\n  Read every 'found' as a LOWER BOUND: a system counts as scanned on its first"
      "\n  reported body, and no source says which bodies were actually surveyed.")
con.close()
print("\nDONE_SCORE_PREDICTIONS")
