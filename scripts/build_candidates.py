"""Export a compact candidate-systems file for the BH/WR finder app.

A candidate = a system that is BH/WR-CAPABLE by mass code (e/f/g/h for black holes,
h for Wolf-Rayets) AND is NOT yet scanned (is_scanned=false) AND is not already in
EDAstro's rare-star catalogues -> i.e. a real, known system where an UNDISCOVERED
BH/WR could be. Output: candidates.parquet (read by app/ed_bh_overlay.py and
app/ed_router.py; no giant DB needed at runtime).

The probability model
---------------------
p_bh / p_wr answer "if I fly there, will I find one" -- not "what fraction of systems
like this hold one". Those are different numbers, because the pool is what is LEFT
after every catalogued rare has been removed from it.

    p = r_boxel(mass_code, boxel) * shape(mass_code, index_band) * source_mult

r_boxel  The boxel's own hit rate, shrunk toward the mass code's galactic level by a
         Beta prior of PRIOR_SYSTEMS pseudo-systems: (k + N0*L) / (seen + N0). Boxel
         content varies far more than the galactic mean admits -- Nuekau FG-Y g holds
         24 black holes in 25 seen systems, Clookia AA-A h holds 16 Wolf-Rayets in 22
         -- and the rich ones are where the remaining finds are. An untouched boxel has
         k=0, seen=0 and falls back exactly to L.

L        known / population, per mass code, from EDAstro's COMPLETE rare catalogues
         over the full boxel population (max(index)+1). Both halves matter: EDAstro is
         the only source that is not a 7-day slice, and the population is the only
         honest denominator -- sys_feat holds ~0.7% of f-mass systems and those rows
         are heavily enriched for black holes, because a sparse boxel only gets a spine
         entry for systems somebody found interesting.

shape    The in-boxel index gradient, normalised to mean 1.0, fitted only in boxels
         that are >=95% seen so no scan-selection can steer it. BH rises with index
         (h-mass 26.3% at 0-9 to 47.1% at 250+), WR falls (31.4% -> 25.0%). They are
         fitted separately: one shared p_any averages a rising and a falling curve into
         a flat line and destroys the signal.

The calibrated level comes from app/calibration.json, which
scripts/analyse_observations.py derives from what you actually found when you flew to
these systems -- the only unbiased measurement of the pool rate that exists, since
every database can only describe systems somebody already scanned. It carries the
selection effect too: seen systems were chosen partly BECAUSE they looked interesting,
so the unseen residue is poorer than its boxel average.

That multiplier is keyed (mass_code, source, kind) and applied ONCE, which is why the
level -- and `boxrate`, whose prior mean IS the level -- are both source-specific here.
Two separate families multiplied together corrected each residual twice and the loop
oscillated instead of converging.

Each system is rolled independently by the generator, so nothing here subtracts a
boxel's known rares from its remaining chance. Finding 24 black holes in a boxel is
evidence that it is rich, not that its quota is spent.

The EDAstro exclusion matters more than it sounds. `is_scanned` comes from
`spansh_body`, and Spansh is missing bodies EDAstro has held since 2017; every other
body source in `ingest_manifest` is a 7-day slice, so an old scan can never show up
in it. Without this filter 42% of the h-mass pool is already-catalogued black holes
and Wolf-Rayets. See scripts/ingest_edastro_rares.py.

p_hr -- helium-rich gas giants
------------------------------
A second, unrelated target on the same candidates, because it is the one PLANET class
that is predictable at all. Planet classes generally are not: Earth-likes, ammonia
worlds and water worlds show only 1.3-1.9x per-boxel overdispersion and that vanishes
once the arrival star is held fixed (see DEAD_ENDS.md). Helium-rich gas giants show
5.4x, with two hard gates and one very sharp continuous predictor:

    r_sgra >= 5500 ly   Zero hits in 690,795 fully-scanned systems inside 5,500 ly of
                        Sgr A*. Beyond it, 0.27-0.59%.
    mass_code <> 'h'    Zero hits in 64,315 fully-scanned h-mass systems where the
                        g-mass rate implies ~130, and 0 of 110 at helium >= 29% where
                        it implies ~20 (p ~ 4e-10). Gated out, like R1 gates BH/WR.
    helium_avg          EDAstro's published per-boxel gas-giant helium fraction. Flat
                        ZERO below 28%, then monotone to ~63% by 33.5%. Fitted here at
                        build time rather than hardcoded, so it tracks the data.

The curve is used as a lookup, not a shape multiplier: unlike p_bh/p_wr there is no
level to calibrate against flight outcomes yet, so p_hr is the raw observed rate of the
helium band and nothing else. It is also NOT normalised against p_bh/p_wr -- a system
can hold a black hole and a helium-rich gas giant at the same time; they are different
bodies, not competing classes for one star.

Caveat carried into the app: helium_avg is an aggregate of SCANNED gas giants, so it
can only rate a boxel somebody has already dipped into. It predicts the rest of a
sampled boxel, never a virgin one. See scripts/ingest_edastro_boxel_stats.py.
"""
import duckdb, pathlib, json, datetime
ROOT = pathlib.Path(__file__).resolve().parent.parent
con = duckdb.connect(str(ROOT / "elite_mapping.duckdb"))
con.execute("SET memory_limit='7GB'"); con.execute("SET threads=8")
KB=r"regexp_replace(name,'[0-9]+(-[0-9]+)?$','')"; TK=r"regexp_extract(name,'([0-9]+(-[0-9]+)?)$',1)"
BX=f"CASE WHEN {TK} LIKE '%-%' THEN {KB}||'#'||split_part({TK},'-',1) ELSE {KB} END"
IX=f"CASE WHEN {TK} LIKE '%-%' THEN CAST(split_part({TK},'-',2) AS BIGINT) ELSE CAST({TK} AS BIGINT) END"

if not con.execute("""SELECT count(*) FROM duckdb_tables()
                      WHERE table_name='edastro_known_rare'""").fetchone()[0]:
    raise SystemExit("missing table edastro_known_rare -- run scripts/ingest_edastro_rares.py first")
con.execute("""
CREATE OR REPLACE TEMP TABLE known_rare AS
SELECT name,
       max(CASE WHEN kind='black_hole' THEN 1 ELSE 0 END) AS kbh,
       max(CASE WHEN kind='wolf_rayet' THEN 1 ELSE 0 END) AS kwr
FROM edastro_known_rare GROUP BY name
""")
nkr = con.execute("SELECT count(*) FROM known_rare").fetchone()[0]
print(f"excluding {nkr:,} systems EDAstro already catalogues as BH/WR (already mapped)", flush=True)

# --- per-system table: index and boxel completeness are both per-SYSTEM inputs now ---
print("building per-system stats (mass code x radius x boxel index)...", flush=True)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE sysb AS
SELECT name, mass_code, plane_r, is_scanned, has_bh, has_wr,
       {BX} AS boxel, {IX} AS idx
FROM sys_feat WHERE mass_code IN ('e','f','g','h') AND {TK} <> ''
""")
con.execute("""
CREATE OR REPLACE TEMP TABLE sysx AS
SELECT s.*, coalesce(k.kbh, 0) AS kbh, coalesce(k.kwr, 0) AS kwr
FROM sysb s LEFT JOIN known_rare k ON k.name = s.name
""")

# "seen" = somebody has looked: it has body data OR EDAstro lists its primary. This is
# the denominator that matters for what is LEFT, and it is deliberately broader than
# is_scanned, which only reflects Spansh's lossy body dump.
con.execute("""
CREATE OR REPLACE TEMP TABLE bx AS
SELECT boxel, any_value(mass_code) mass_code, avg(plane_r) plane_r,
       max(idx)+1 AS pop,
       count(*) FILTER (WHERE is_scanned) AS scanned,
       count(*) FILTER (WHERE is_scanned OR kbh=1 OR kwr=1) AS seen,
       sum(kbh) AS known_bh, sum(kwr) AS known_wr
FROM sysx GROUP BY 1
""")

# --- the rate model: LEVEL x SHAPE x RESIDUAL ------------------------------------
# Three factors, each fitted from the source that can actually measure it. The first
# version fitted one number from one source and got every part of this wrong.
#
#   p = L(mass_code) * S(mass_code, index band) * R(boxel)
#
# LEVEL L -- how often a system of this mass code holds one, per system in the FULL
#   boxel population. The denominator has to be max(idx)+1, not the sys_feat row
#   count: sys_feat holds only ~0.7% of f-mass systems (461,410 rows against a
#   population of 67.0M) and the rows it does hold are massively enriched for black
#   holes, because a sparse boxel only gets a spine entry for systems somebody found
#   interesting. Dividing by rows instead of population is what produced the old
#   "50.9% of f-mass systems contain a black hole" -- against a true figure near 0.3%.
#   EDAstro's catalogues are COMPLETE, so known/population is an unbiased lower bound
#   on L, and app/calibration.json (written by scripts/analyse_observations.py from
#   real hit/miss outcomes) overrides it once enough systems have been flown.
#
# SHAPE S -- the in-boxel index gradient, normalised to average 1.0. Fitted only in
#   boxels that are >=95% SEEN, where the catalogue is effectively complete so no
#   scan-selection can steer it. BH rises with index (h-mass 26.3% at 0-9 to 47.1% at
#   250+, g-mass 19.5% -> 41.5%); WR falls (31.4% -> 25.0%). They are fitted
#   separately because one shared p_any averages a rising and a falling curve into a
#   flat line and destroys the signal.
#
# RESIDUAL R -- what is LEFT in this boxel. The pool is not a population sample; it
#   is the leftovers after every catalogued rare has been removed. Take the total the
#   level implies, subtract what EDAstro already lists, and spread the deficit over
#   the unseen systems only. A fully-catalogued boxel goes to 0; an untouched one to 1.
IBAND_C = ("CASE WHEN {c} < 10 THEN 0 WHEN {c} < 25 THEN 10 WHEN {c} < 50 THEN 25 "
           "WHEN {c} < 100 THEN 50 WHEN {c} < 250 THEN 100 ELSE 250 END")
IBAND = IBAND_C.format(c="sysx.idx")

print("fitting LEVEL from EDAstro (complete) over full boxel populations...", flush=True)
con.execute("""
CREATE OR REPLACE TEMP TABLE level AS
SELECT mass_code,
       sum(known_bh)::DOUBLE / nullif(sum(pop), 0) AS l_bh,
       sum(known_wr)::DOUBLE / nullif(sum(pop), 0) AS l_wr,
       sum(pop) AS population, sum(known_bh) AS known_bh, sum(known_wr) AS known_wr
FROM bx GROUP BY 1
""")
print(f"  {'mc':>4}{'population':>16}{'EDAstro BH':>12}{'EDAstro WR':>12}{'L_bh':>9}{'L_wr':>9}")
for r in con.execute("SELECT mass_code, population, known_bh, known_wr, l_bh, l_wr "
                     "FROM level ORDER BY 1").fetchall():
    print(f"  {r[0]:>4}{r[1]:>16,}{r[2]:>12,}{r[3]:>12,}{r[4]:>9.2%}{r[5]:>9.2%}")

# observed hit rates override the EDAstro floor once we have flown enough of them
# known/population is a LOWER bound: it counts what EDAstro has found, not what is
# there. How much it undercounts differs wildly by mass code -- h boxels are swept
# almost exhaustively while only ~1% of f-mass systems sit in a near-complete boxel --
# and no query can settle it, because the missing ones are missing from every source.
# Flying to them can. calibration.json carries observed/predicted per mass code, from
# systems whose class the game has since revealed. See scripts/analyse_observations.py.
# The multiplier is keyed (mass_code, source, kind) and applied EXACTLY ONCE. It used
# to be two families -- one per mass code and one per source -- multiplied together,
# which corrected the same residual twice and made the loop oscillate rather than
# converge (see the header comment in scripts/analyse_observations.py). Because the
# level is now source-specific, so is everything downstream of it: `lvl` and `boxrate`
# both carry a source, and each export branch joins its own.
CALIB = ROOT / "app" / "calibration.json"
SOURCES = ("unscanned", "predicted")
calib = {}
if CALIB.exists():
    _c = json.loads(CALIB.read_text(encoding="utf-8"))
    calib = _c.get("multiplier", {})
    if not _c.get("cross_keyed"):
        # an old two-family file: collapse it to the product that was in force, which
        # is what the model was actually applying, so a stale file cannot silently
        # change the predictions on the way through
        _sm = _c.get("source_multiplier", {})
        calib = {mc: {s: {k: m * float(_sm.get(s, 1.0)) for k, m in kinds.items()}
                      for s in SOURCES} for mc, kinds in calib.items()}
        print(f"  {CALIB.name} predates the cross-keyed form -- collapsing "
              f"mass_code x source to the product in force", flush=True)
    print(f"  applying observed calibration from {CALIB.name}:", flush=True)
    for mc in sorted(calib):
        for s in sorted(calib[mc]):
            kk = ", ".join(f"{k} x{v:.4f}" for k, v in sorted(calib[mc][s].items()))
            print(f"    {mc}/{s:<10} {kk}", flush=True)
else:
    print("  no calibration.json yet -- using the raw EDAstro floor. Run "
          "scripts/analyse_observations.py to correct it from real outcomes.", flush=True)
# The multiplier is applied to the FINAL probability, not folded into the level.
# It is measured as observed/expected on the final probability, so that is the only
# place it composes exactly. Folding it into the level instead only shifts boxrate's
# prior mean, which a well-sampled boxel almost ignores -- doing that moved the
# predicted h-mass mean from 8% to 42% while the measured hit rate stayed put.
lv = con.execute("SELECT mass_code, l_bh, l_wr FROM level").fetchall()
con.execute("CREATE OR REPLACE TEMP TABLE lvl "
            "(mass_code VARCHAR, l_bh DOUBLE, l_wr DOUBLE)")
con.executemany("INSERT INTO lvl VALUES (?,?,?)",
                [(mc, lb or 0.0, lw or 0.0) for mc, lb, lw in lv])
con.execute("CREATE OR REPLACE TEMP TABLE cmult "
            "(mass_code VARCHAR, source VARCHAR, m_bh DOUBLE, m_wr DOUBLE)")
con.executemany("INSERT INTO cmult VALUES (?,?,?,?)",
                [(mc, src,
                  float(calib.get(mc, {}).get(src, {}).get("bh", 1.0)),
                  float(calib.get(mc, {}).get(src, {}).get("wr", 1.0)))
                 for mc, _lb, _lw in lv for src in SOURCES])

print("fitting SHAPE (index gradient) on >=95%-seen boxels...", flush=True)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE shape AS
WITH cell AS (
  SELECT sysx.mass_code, {IBAND} AS iband,
         sum(kbh)::DOUBLE/count(*) bh_rate, sum(kwr)::DOUBLE/count(*) wr_rate, count(*) n
  FROM sysx JOIN bx USING (boxel)
  WHERE bx.pop > 0 AND bx.seen::DOUBLE/bx.pop >= 0.95
  GROUP BY 1,2 HAVING count(*) >= 200
)
SELECT mass_code, iband, n,
       bh_rate / nullif(sum(bh_rate*n) OVER (PARTITION BY mass_code)
                        / sum(n) OVER (PARTITION BY mass_code), 0) AS s_bh,
       wr_rate / nullif(sum(wr_rate*n) OVER (PARTITION BY mass_code)
                        / sum(n) OVER (PARTITION BY mass_code), 0) AS s_wr
FROM cell
""")

# --- BOXEL RATE: what this specific boxel is actually like -----------------------
#     r_B = (k + N0*L) / (seen + N0)
#
# The boxel's own hit rate, shrunk toward the mass code's galactic level L. Boxel
# content varies far more than L admits -- Nuekau FG-Y g holds 24 black holes in 25
# seen systems, Clookia AA-A h holds 16 Wolf-Rayets in 22 -- so a single global rate
# cannot express either the rich boxels or the empty ones, and the rich ones are where
# the remaining finds are. An untouched boxel has k=0, seen=0 and falls back to L.
#
# N0 is the prior weight in PSEUDO-SYSTEMS, and the unit is load-bearing. Expressed in
# pseudo-RARES instead -- (k + a)/(seen + a/L) -- the implied sample size is a/L, which
# at the g-mass level of 2.1% is 94 pseudo-systems: a real 25-system boxel would be
# outvoted 4:1 by the prior and a 96%-black-hole boxel would read as 22%. In
# pseudo-systems the prior is a small fixed weight at any level, so a boxel that has
# actually been sampled speaks for itself.
#
# Nothing is subtracted for the rares already found here. The generator rolls each
# system independently, so 24 black holes in a boxel is evidence it is rich, not
# evidence its quota is spent. The selection effect -- seen systems were picked partly
# BECAUSE they looked interesting, leaving a poorer residue -- is a level correction
# and lives in calibration.json, measured from real outcomes.
PRIOR_SYSTEMS = 10.0
print(f"computing per-boxel rates (empirical Bayes, {PRIOR_SYSTEMS:g} pseudo-systems)...",
      flush=True)
con.execute(f"""
CREATE OR REPLACE TEMP TABLE boxrate AS
SELECT b.boxel,
       (b.known_bh + {PRIOR_SYSTEMS}*coalesce(l.l_bh, 0)) / (b.seen + {PRIOR_SYSTEMS}) AS r_bh,
       (b.known_wr + {PRIOR_SYSTEMS}*coalesce(l.l_wr, 0)) / (b.seen + {PRIOR_SYSTEMS}) AS r_wr
FROM bx b JOIN lvl l ON l.mass_code = b.mass_code
""")
# r_B already carries the level -- the prior's mean IS L -- so shape is the only other
# factor here; multiplying by L again would square it.
#
# The pair is then jointly normalised. A star is either a black hole or a Wolf-Rayet,
# never both, so p_bh + p_wr must not exceed 1. Clamping each to 1.0 independently
# does not enforce that; a rich h-mass boxel reaches 131% combined. When the sum
# overshoots, both are scaled down in proportion, preserving the ratio between them --
# the ratio is the well-measured part, the level is what calibration corrects.
# Emitted UNNORMALISED and without the calibration multiplier: both export branches
# apply their own multiplier and then normalise, so the two paths stay identical.
con.execute(f"""
CREATE OR REPLACE TEMP TABLE prob AS
SELECT sysx.name, sysx.boxel, sysx.idx, sysx.mass_code,
       greatest(0.0, coalesce(br.r_bh, l.l_bh) * coalesce(sh.s_bh, 1.0)) AS q_bh,
       CASE WHEN sysx.mass_code='h'
            THEN greatest(0.0, coalesce(br.r_wr, l.l_wr) * coalesce(sh.s_wr, 1.0))
            ELSE 0.0 END AS q_wr
FROM sysx
JOIN lvl l ON l.mass_code = sysx.mass_code
LEFT JOIN shape sh ON sh.mass_code = sysx.mass_code AND sh.iband = {IBAND}
LEFT JOIN boxrate br ON br.boxel = sysx.boxel
""")
con.execute("CREATE INDEX IF NOT EXISTS idx_prob_name ON prob(name)")

# --- p_hr: helium-rich gas giants ------------------------------------------------
# Fitted from fully-scanned systems only. A partly-scanned system that reports no
# helium-rich giant may simply not have had its gas giants looked at, and counting
# those as negatives would drag every band toward zero.
HR_GATE_SGRA = 5500.0
# 29.0, not 28.0. The observed rate is a flat zero below 28% and still rounds to 0% at
# 28.0-28.5 (1 and 5 hits); emitting those would render as "0%", which in this app means
# "possible but unlikely" while a real zero renders as "-" for "impossible here". 29.0 is
# where the signal is first worth a column (1.0%, 27 hits in 2,653) and it costs almost
# nothing: a >=29% cut still captures 99.9% of every helium-rich hit in scope.
HR_MIN_HE = 29.0
HR_BAND = 0.5             # helium bands, in percentage points
if con.execute("""SELECT count(*) FROM duckdb_tables()
                  WHERE table_name='edastro_boxel_stats'""").fetchone()[0]:
    print("fitting p_hr (helium-rich gas giants) from published boxel helium...",
          flush=True)
    con.execute(f"""
    CREATE OR REPLACE TEMP TABLE hr_fit AS
    WITH scanned AS (
      SELECT b.helium_avg he, coalesce(hb.hr, 0) hr
      FROM sys_feat f
      JOIN spansh_system sp ON sp.system_id64 = f.system_id64
      JOIN sysb s           ON s.name = f.name
      JOIN edastro_boxel_stats b ON b.boxel = s.boxel
      LEFT JOIN (SELECT system_id64,
                        max(CASE WHEN sub_type='Helium-rich gas giant' THEN 1 ELSE 0 END) hr
                 FROM spansh_body GROUP BY 1) hb ON hb.system_id64 = f.system_id64
      WHERE sp.declared_body_count > 0
        AND sp.scanned_body_count >= sp.declared_body_count
        AND f.r_sgra >= {HR_GATE_SGRA} AND f.mass_code <> 'h'
        AND b.helium_avg IS NOT NULL
    )
    SELECT floor(he / {HR_BAND}) * {HR_BAND} AS he_band,
           count(*) AS n, sum(hr) AS k, avg(hr) AS rate
    FROM scanned GROUP BY 1 HAVING count(*) >= 200
    """)
    print(f"  {'helium':>8}{'systems':>11}{'hits':>9}{'rate':>9}")
    for r in con.execute("""SELECT he_band, n, k, rate FROM hr_fit
                            WHERE rate > 0 OR he_band >= 27 ORDER BY 1""").fetchall():
        print(f"  {r[0]:>8.1f}{r[1]:>11,}{r[2]:>9,}{r[3]:>9.1%}")
    HR_EXPR = f"""
        CASE WHEN {{mc}} = 'h' THEN 0.0
             WHEN {{sgra}} < {HR_GATE_SGRA} THEN 0.0
             WHEN hb.helium_avg IS NULL OR hb.helium_avg < {HR_MIN_HE} THEN 0.0
             ELSE coalesce(hf.rate, 0.0) END"""
    HR_JOIN = f"""
      LEFT JOIN edastro_boxel_stats hb ON hb.boxel = {{boxel}}
      LEFT JOIN hr_fit hf ON hf.he_band = floor(hb.helium_avg / {HR_BAND}) * {HR_BAND}"""
else:
    print("  no edastro_boxel_stats table -- p_hr will be 0. Run "
          "scripts/ingest_edastro_boxel_stats.py to enable it.", flush=True)
    HR_EXPR, HR_JOIN = "0.0", ""

out = ROOT / "app" / "candidates.parquet"
tmp = ROOT / "app" / "candidates.tmp.parquet"
(ROOT / "app").mkdir(exist_ok=True)
print("exporting candidates: in-db-unscanned (real) + predicted (theorised internal gaps)...", flush=True)
# name reconstruction for predicted systems: boxel_key '...#preA' + idx -> '...preA-idx'; else boxel_key||idx
NAME = ("CASE WHEN boxel_key LIKE '%#%' "
        "THEN split_part(boxel_key,'#',1)||split_part(boxel_key,'#',2)||'-'||boxel_index "
        "ELSE boxel_key||boxel_index END")
# theorised systems are not in sys_feat, so the same three factors are applied to
# their own (mass_code, index band) and their own boxel
TIB = IBAND_C.format(c="t.boxel_index")
# The calibration multiplier lands HERE, on the final probability, once -- the same
# place the old source multiplier did, and the place observed/expected measures it.
# The pair is normalised AFTER it, because a multiplier above 1.0 can push the sum
# over 1.0 and a star is either a black hole or a Wolf-Rayet, never both.
con.execute(f"""
COPY (
  -- (1) real, known-but-unscanned systems
  SELECT s.name, s.x, s.y, s.z, s.mass_code,
         round(p.q_bh * c.m_bh
               / greatest(1.0, p.q_bh*c.m_bh + p.q_wr*c.m_wr), 4) AS p_bh,
         round(p.q_wr * c.m_wr
               / greatest(1.0, p.q_bh*c.m_bh + p.q_wr*c.m_wr), 4) AS p_wr,
         round({HR_EXPR.format(mc='s.mass_code', sgra='s.r_sgra')}, 4) AS p_hr,
         'unscanned' AS source, p.boxel, p.idx AS boxel_index
  FROM sys_feat s JOIN prob p ON p.name = s.name
  JOIN cmult c ON c.mass_code = s.mass_code AND c.source = 'unscanned'
  {HR_JOIN.format(boxel='p.boxel')}
  WHERE NOT s.is_scanned AND s.mass_code IN ('e','f','g','h')
    AND NOT EXISTS (SELECT 1 FROM known_rare k WHERE k.name = s.name)
  UNION ALL
  -- (2) predicted internal-gap systems (likely-real, boxel-centroid coords)
  SELECT name, x, y, z, mass_code,
         round(q_bh / greatest(1.0, q_bh + q_wr), 4) AS p_bh,
         round(q_wr / greatest(1.0, q_bh + q_wr), 4) AS p_wr,
         round(q_hr, 4) AS p_hr,
         source, boxel, boxel_index
  FROM (
    SELECT {NAME} AS name, t.x, t.y, t.z, t.mass_code,
           greatest(0.0, coalesce(br.r_bh, l.l_bh) * coalesce(sh.s_bh, 1.0) * c.m_bh) AS q_bh,
           CASE WHEN t.mass_code='h'
                THEN greatest(0.0, coalesce(br.r_wr, l.l_wr) * coalesce(sh.s_wr, 1.0) * c.m_wr)
                ELSE 0.0 END AS q_wr,
           {HR_EXPR.format(mc='t.mass_code', sgra='t.r_sgra')} AS q_hr,
           'predicted' AS source, t.boxel_key AS boxel, t.boxel_index
    FROM theorised_system t
    JOIN lvl l ON l.mass_code = t.mass_code
    JOIN cmult c ON c.mass_code = t.mass_code AND c.source = 'predicted'
    {HR_JOIN.format(boxel='t.boxel_key')}
    LEFT JOIN shape sh ON sh.mass_code = t.mass_code AND sh.iband = {TIB}
    LEFT JOIN boxrate br ON br.boxel = t.boxel_key
    WHERE NOT EXISTS (SELECT 1 FROM known_rare k WHERE k.name = {NAME})
  )
) TO '{tmp.as_posix()}' (FORMAT PARQUET)
""")

# --- attach the galactic region to every candidate -------------------------------
# The app shows the current region and counts how many routable targets share it.
# Regions are hand-drawn areas with no closed form, so each candidate is labelled by
# nearest neighbour against EDAstro's 545k region-tagged systems (99.55% accurate on
# a hold-out -- see scripts/build_regions.py). Done here, once, rather than at
# runtime: the app has no database and 2.3M x 545k brute force is far too slow.
print("labelling candidates with galactic region (kNN over edastro labels)...", flush=True)
import numpy as np
from scipy.spatial import cKDTree
anchors = con.execute("""
    SELECT CAST(e.region AS SMALLINT) rid, s.x, s.y, s.z
    FROM edastro_star_system e JOIN spansh_system s ON s.name = e.name
    WHERE e.region IS NOT NULL""").df()
tree = cKDTree(anchors[["x", "y", "z"]].values)
alab = anchors.rid.values.astype(np.int16)

cand = con.execute(f"SELECT x, y, z FROM '{tmp.as_posix()}'").df()
print(f"    anchors={len(anchors):,}  candidates={len(cand):,}", flush=True)
region = np.empty(len(cand), dtype=np.int16)
CH = 250_000
for i in range(0, len(cand), CH):
    _, idx = tree.query(cand[["x", "y", "z"]].values[i:i + CH], k=5, workers=-1)
    lab = alab[idx]                                    # (n,5) neighbour labels
    # majority vote across the 5 nearest, ties broken by the closest neighbour
    n_reg = int(alab.max()) + 1
    counts = np.zeros((lab.shape[0], n_reg), dtype=np.int8)
    np.add.at(counts, (np.arange(lab.shape[0])[:, None], lab), 1)
    best = counts.argmax(1).astype(np.int16)
    top = counts.max(1)
    tie = (counts == top[:, None]).sum(1) > 1
    best[tie] = lab[tie, 0]                            # tie -> nearest neighbour wins
    region[i:i + CH] = best
    print(f"      {min(i+CH, len(cand)):,}/{len(cand):,}", flush=True)

cand_region = np.asarray(region)
con.register("reg_col", __import__("pandas").DataFrame({"region": cand_region}))
con.execute(f"""
COPY (SELECT c.*, r.region
      FROM (SELECT *, row_number() OVER () AS _rn FROM '{tmp.as_posix()}') c
      JOIN (SELECT *, row_number() OVER () AS _rn FROM reg_col) r USING(_rn)
     ) TO '{out.as_posix()}' (FORMAT PARQUET)
""")
con.unregister("reg_col")
tmp.unlink(missing_ok=True)

n = con.execute(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()[0]
print(f"\nwrote {out}  ({n:,} candidate systems, {out.stat().st_size/1e6:.1f} MB)")
print(f"  {'source':>10}{'mc':>3}{'systems':>11}{'mean p_bh':>11}{'mean p_wr':>11}{'max p':>8}")
for r in con.execute(f"""SELECT source, mass_code, count(*) c, avg(p_bh), avg(p_wr),
                                max(p_bh+p_wr)
                         FROM '{out.as_posix()}' GROUP BY 1,2 ORDER BY 1,2""").fetchall():
    print(f"  {r[0]:>10}{r[1]:>3}{r[2]:>11,}{r[3]:>11.2%}{r[4]:>11.2%}{r[5]:>8.1%}")

print(f"\n  p_hr (helium-rich gas giants) -- nonzero only where the boxel's published")
print(f"  helium is >= {HR_MIN_HE:g}%, mass code is not h, and r_sgra >= {HR_GATE_SGRA:g} ly:")
print(f"  {'source':>10}{'mc':>3}{'systems':>11}{'p_hr>0':>10}{'>=10%':>9}{'>=25%':>9}"
      f"{'max p_hr':>10}")
for r in con.execute(f"""SELECT source, mass_code, count(*) c,
                                count(*) FILTER (WHERE p_hr > 0) nz,
                                count(*) FILTER (WHERE p_hr >= 0.10) n10,
                                count(*) FILTER (WHERE p_hr >= 0.25) n25,
                                max(p_hr)
                         FROM '{out.as_posix()}' GROUP BY 1,2 ORDER BY 1,2""").fetchall():
    print(f"  {r[0]:>10}{r[1]:>3}{r[2]:>11,}{r[3]:>10,}{r[4]:>9,}{r[5]:>9,}{r[6]:>10.1%}")

# --- model card: the app stamps this onto every logged observation ---------------
# Without it a calibration file spanning two rebuilds silently mixes two models.
meta = ROOT / "app" / "candidates_meta.json"
version = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
meta.write_text(json.dumps({
    "model_version": version,
    "built_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "rows": n,
    "model": "p = r_boxel(mass_code, source, boxel) * S(mass_code, index_band)",
    "features": ["mass_code", "index_band", "boxel_empirical_bayes_rate", "source"],
    # the exact multipliers this build applied, so a calibration file that has since
    # been overwritten cannot make an old model_version unscoreable
    "calibration_applied": calib,
    "p_hr_model": ("observed rate of the boxel's published helium band; 0 when "
                   f"mass_code='h', r_sgra < {HR_GATE_SGRA:g}, or helium < {HR_MIN_HE:g}%"),
    "p_hr_gates": {"min_r_sgra_ly": HR_GATE_SGRA, "min_helium_pct": HR_MIN_HE,
                   "excluded_mass_codes": ["h"], "helium_band_pct": HR_BAND},
    "level_source": "calibration.json" if calib else "edastro_over_population",
    "boxel_prior_pseudo_systems": PRIOR_SYSTEMS,
    "shape_fit_population": "boxels with >=95% of the population seen",
    "target": "P(an UNDISCOVERED BH/WR remains in this system)",
    "index_bands": [0, 10, 25, 50, 100, 250],
    "known_rare_excluded": nkr,
}, indent=1), encoding="utf-8")
print(f"\nmodel_version {version} -> {meta}")

print("\n  fitted index shape (normalised; BH should rise, WR should fall):")
print(f"  {'mc':>4}{'iband':>7}{'s_bh':>9}{'s_wr':>9}{'n':>12}")
for r in con.execute("""SELECT mass_code, iband, s_bh, s_wr, n FROM shape
                        ORDER BY mass_code, iband""").fetchall():
    print(f"  {r[0]:>4}{r[1]:>7}{r[2]:>9.2f}{(r[3] or 0):>9.2f}{r[4]:>12,}")
con.close()
