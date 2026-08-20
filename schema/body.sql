-- body: reference dimension of body TYPES. Load order tier 1 (no dependencies).
-- Comment text lives in schema/body_comment.sql -- apply both.
CREATE TABLE IF NOT EXISTS body (
    body_id                INTEGER NOT NULL PRIMARY KEY,
    type                   VARCHAR NOT NULL,
    body                   VARCHAR NOT NULL,
    is_terraform_candidate BOOLEAN NOT NULL,
    code                   VARCHAR,
    observed               BOOLEAN NOT NULL,
    bodies                 BIGINT  NOT NULL,
    cr_value               DOUBLE,
    cr_value_terraformable DOUBLE,
    value_formula          VARCHAR
);

-- --------------------------------------------------------------------------
-- COMMENTS. Kept in this file, beside the DDL they describe, so a schema change
-- and its documentation cannot drift apart. Re-applied by the builder after every
-- merge via common.db.apply_comment_file(), because a migration is the one thing
-- that silently drops a comment.
-- --------------------------------------------------------------------------

-- Canonical COMMENT for the `body` table. Kept in its own file because both the
-- seeder (build_body_dim.py) and the merge loader (load_body_dim.py) must assert
-- the SAME text, and comment_tables.py treats `body` as self-documented and only
-- verifies it is non-empty. Edit here, nowhere else.
COMMENT ON TABLE body IS
'REFERENCE DIMENSION: one row per body TYPE in the game (49 stars, 19 planets).
Join to it instead of hardcoding subtype strings.

AUTHORITY AND LOADING. input/body.parquet is AUTHORITATIVE and is safe to
hand-edit; this table is a MERGE TARGET, never dropped and never replaced. Load it
with etl/load_body.py, which creates the table IF NOT EXISTS, matches on
the NATURAL key (type, body), inserts only unseen entries, and updates attributes
of entries it already has. Rows present here but absent from the parquet are LEFT
IN PLACE and their ids retired, because something may already reference them --
deleting one is a manual decision. Do NOT use CREATE OR REPLACE TABLE on this
table: it would renumber body_id and silently drop any foreign key pointing at it,
and DuckDB does not warn.

COLUMNS. `body_id` is an INTEGER PRIMARY KEY sequence number and is THE key other
tables are meant to carry. Existing ids are never renumbered and retired ids are
never reused; a new entry takes the parquet''s id when free, else max+1. Ids were
assigned in enum order on the first build (stars 1-49, planets 50-68) but that is
incidental -- do NOT assume id order. `body` matches spansh_body.sub_type exactly
for observed types, so it joins straight onto the 569M-row body table. `code` is
the FULL journal star code WITH variant (DA/DAB/DAO/DAZ/DAV/DB/DBZ/DBV/DO/DOV/DQ/
DC/DCV/DX, and W/WN/WNC/WC/WO) and is the key for LIVE JOURNAL data -- the journal
StarType field carries these codes, never the sub_type display names, which are a
Spansh/EDSM presentation layer. `code` is NULL for planets. `observed` and
`bodies` are DERIVED statistics, not dimension attributes: they are recomputed
from spansh_body on every load, so the copies inside the parquet are only a
point-in-time snapshot and are ignored when merging. `cr_value`,
`cr_value_terraformable` and `value_formula` are the exploration-value `k`
CONSTANTS and are NOT credit payouts -- the payout needs the body''s mass through
the formula, then multipliers; see the per-column comments before using them.

HOW THE TYPE LIST WAS CREATED (etl/build_body.py, first built 2026-08-11):
1. TRANSCRIBED FROM THE GAME ENUMS, not discovered from our data -- EDStar and
   EDPlanet in EDDiscovery/EliteDangerousCore at
   EliteDangerous/FrontierData/Enumerations/{Stars,Planets}.cs, whose header states
   "naming is as per Journal 15.2". Enum order is preserved. Consequently 7 types
   that exist in the game but which nobody in our data has ever scanned still get a
   row, with observed=FALSE: white dwarfs DAO/DO/DOV/DX, carbon stars CS/CHd, and
   Water giant with life. Non-star EDStar members (RoguePlanet, Nebula,
   StellarRemnantNebula) and the speculative X are EXCLUDED.
2. The code->name mapping is a hand-authored literal in the seeder, verified
   against the 43 distinct star sub_types actually present in spansh_body. The six
   unobserved star variants follow the same observed naming pattern.
3. is_terraform_candidate was DERIVED FROM THE DATA, not asserted: TRUE for any
   type the game has ever generated with terraforming_state=''Terraformable''
   across all 437.7M planets in spansh_body. That query returns exactly four --
   High metal content world (8,503,277), Water world (1,986,211), Rocky body
   (284,686), Metal-rich body (76). Absence in a sample that size is meaningful.
4. `bodies` inherits spansh_body''s coverage limits: only 38.6% of spine systems
   have any body data at all, so these are NOT galaxy totals.

CAVEAT: Earth-like is is_terraform_candidate=FALSE because an ELW is the
terraforming END STATE, never a candidate -- of 451,680 ELWs, none is
''Terraformable'' (333,518 ''Not terraformable'', 116,261 null, 1,901
''Terraformed'' in populated space). This is deliberately NOT the same question as
scan value: EDDiscovery folds the terraform bonus into the ELW k constant because a
scanned ELW does pay as if terraformable. For value use the k constants, never this
column.';

-- Column-level documentation (ETL.md: every column of every table we own).
COMMENT ON COLUMN body.body_id IS
'INTEGER PRIMARY KEY, plain sequence number. THE key other tables should carry.
STABLE: the loader reads back existing ids and only allocates new ones as max+1, so a
data refresh never repoints a foreign key. A new entry takes the parquet''s id when
that id is free, else max+1. Retired ids are never reused. Assigned in enum order on
the first build (stars 1-49, planets 50-68) but that is incidental -- do NOT assume
id order.';

COMMENT ON COLUMN body.type IS
'''star'' or ''planet''. Lowercase, unlike spansh_body.type which is ''Star''/''Planet''
-- join with lower(s.type) = b.type. Part of the NATURAL KEY (type, body) that merges
match on.';

COMMENT ON COLUMN body.body IS
'Canonical body-type name, e.g. ''Water world'', ''White Dwarf (DAB) Star''. Matches
spansh_body.sub_type EXACTLY for every observed type, so it joins straight onto the
569M-row body table. Part of the NATURAL KEY (type, body) -- never match on body_id.';

COMMENT ON COLUMN body.is_terraform_candidate IS
'TRUE if the game generates this type as a terraforming candidate. DERIVED from the
data, not asserted: TRUE for any type ever seen with terraforming_state=''Terraformable''
across all 437.7M planets. Exactly four qualify -- High metal content world (8,503,277),
Water world (1,986,211), Rocky body (284,686), Metal-rich body (76).
*** Earth-like world is FALSE *** because an ELW is the terraforming END STATE, never a
candidate: of 451,680 ELWs none is ''Terraformable'' (333,518 ''Not terraformable'',
116,261 null, 1,901 ''Terraformed'' in populated space). DO NOT USE THIS COLUMN FOR
SCAN VALUE -- a scanned ELW does pay the terraform bonus, which EDDiscovery folds into
the ELW k constant. For credits use the k constants, not this flag.';

COMMENT ON COLUMN body.code IS
'FULL journal star code WITH variant: DA/DAB/DAO/DAZ/DAV/DB/DBZ/DBV/DO/DOV/DQ/DC/DCV/DX
for white dwarfs, W/WN/WNC/WC/WO for Wolf-Rayet, N for neutron, H for black hole, plus
AeBe, TTS, MS, S, the C-family and the *_SuperGiant forms. NULL for planets.
This is the key for LIVE JOURNAL DATA: the journal StarType field carries these codes
and NEVER the sub_type display names, which are a Spansh/EDSM presentation layer. Use
`code` to join journal events, `body` to join the dumps.';

COMMENT ON COLUMN body.observed IS
'TRUE if we hold at least one body of this type. DERIVED, recomputed from spansh_body on
every load -- the parquet''s copy is an ignored snapshot. FALSE for 7 types that exist in
the game but which nobody in our data has scanned: white dwarfs DAO/DO/DOV/DX, carbon
stars CS/CHd, and Water giant with life. Filter on this rather than assuming every row
has bodies behind it.';

COMMENT ON COLUMN body.bodies IS
'Count of bodies of this type in spansh_body; 0 where observed is FALSE. DERIVED and
recomputed on every load, so the parquet''s copy is only a snapshot. *** NOT A GALAXY
TOTAL: *** only 38.6% of spine systems have any body data at all, so this counts
DISCOVERED bodies, and not even all of those -- nor does any source distinguish
DSS-mapped from merely FSS-detected.';

COMMENT ON COLUMN body.cr_value IS
'*** NOT A CREDIT PAYOUT. *** The `k` CONSTANT this body type contributes to Frontier''s
exploration-value formula, in its NON-terraformable form. k is denominated in credits but
the payout depends on the body''s MASS, so no single per-type credit figure exists:
  planets:  base = max(k + k * mass_em^0.2 * 0.56591828, 500)
  stars:    base = k + solar_masses * k / 66.25
Multipliers then apply and NONE are per-type, so none are stored here: first discovered
x2.6, already-discovered+mapped x3.3333333, first mapped only x8.0956, first discovered
AND first mapped x3.699622554 then x2.6, efficient mapping x1.25, Odyssey mapping bonus
+max(v*0.3, 555) on mapped values only. STARS CANNOT BE MAPPED -- only base and
first-discovered apply to them.
Ordinary stars are all 1200; white dwarfs 14057; neutron stars AND black holes 22628.
Supermassive Black Hole is 33.5678 -- three orders of magnitude LOWER, and NOT a typo.
SOURCE: EDDiscovery ScanEstimatedValues (EliteDangerousCore,
EliteDangerous/FrontierData/Enumerations/EstimatedValues.cs), citing MattG''s "Exploration
value formulae" thread. *** ED 3.3+ BRANCH ONLY. *** That file holds three constant sets
selected by scan timestamp; the higher figures widely quoted online (155581 water world,
2880 ordinary star, 54309 black hole) are the SUPERSEDED 3.2 set. Re-fetched and
byte-compared 2026-08-12: unchanged.';

COMMENT ON COLUMN body.cr_value_terraformable IS
'The `k` constant in its TERRAFORMABLE form -- same formula and same caveats as cr_value,
which see. NULL where the type has no terraform bonus at all: every star, plus Ammonia
world and Class I gas giant. Earth-like world is ALSO NULL, but for the opposite reason:
its bonus is UNCONDITIONAL, so it is already folded into cr_value (64831 + 116295 =
181126) and a scanned ELW always pays as if terraformable. That is why this column and
body.is_terraform_candidate disagree on ELWs and MUST NOT be used interchangeably --
is_terraform_candidate answers "does the game generate it as a candidate" (ELW: no),
this answers "does it pay a terraform bonus" (ELW: yes, always).';

COMMENT ON COLUMN body.value_formula IS
'Which of the two formulae cr_value feeds: ''star'' or ''planet''. Tracks body.type today
and is kept as its own column because the FORMULA is the thing that actually differs --
stars scale k by solar_masses/66.25 with no floor, planets by earth_masses^0.2 with a 500
Cr floor. Branch on this, not on type, so a future type that breaks the correspondence
does not silently take the wrong formula.';
