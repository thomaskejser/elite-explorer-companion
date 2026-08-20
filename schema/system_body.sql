-- system_body: every body we know exists. Load order tier 3 (needs system_known).
--
-- *** PRIMARY KEY ONLY. NO FOREIGN KEYS, NO UNIQUE. *** This is a measured limit of
-- the hardware, not a design preference. Copying all 570,812,803 rows on a 33.5GB
-- machine:
--
--     no constraints                              134s
--     PRIMARY KEY only                            738s     <-- what this file declares
--     PRIMARY KEY + UNIQUE(system_id,system_body) OOM at 14.9GiB after 898s
--     PRIMARY KEY + 3 FOREIGN KEYs                OOM at 24.2GiB
--
-- Every secondary constraint builds its own ART index over 570.8M rows, and DuckDB
-- must pin those blocks to commit. For contrast system_known, at 197.6M rows, carries
-- a PRIMARY KEY, a composite UNIQUE and FOUR foreign keys without trouble -- so the
-- wall sits between those two sizes, not at "system_body is special".
--
-- WHAT STILL PROTECTS THIS TABLE:
--   * system_id -> system_known and body_id -> body are enforced by construction:
--     build_system_body.py only ever inserts rows it resolved through those tables.
--   * the natural key (system_id, system_body) is enforced by that builder's
--     `INSERT ... WHERE NOT EXISTS` merge.
--   * INVARIANT, at most one is_primary row per system_id, resolved by the cascade in
--     build_system_body.py.
-- None of the three is enforced by the DATABASE here. Verify them by query after any
-- load that bypasses the builder; scripts/verify_new_model.py does exactly that.
CREATE TABLE IF NOT EXISTS system_body (
    system_body_id   BIGINT  NOT NULL PRIMARY KEY,
    system_id        BIGINT  NOT NULL,
    body_id          INTEGER,
    system_body      VARCHAR NOT NULL,
    is_primary       BOOLEAN NOT NULL,
    discovered_time  TIMESTAMP,
    solar_masses     DOUBLE,
    earth_masses     DOUBLE,
    is_terraformable BOOLEAN,
    source           VARCHAR,
    id_poi           INTEGER
);

-- --------------------------------------------------------------------------
-- COMMENTS. Kept in this file, beside the DDL they describe, so a schema change
-- and its documentation cannot drift apart. Re-applied by the builder after every
-- merge via common.db.apply_comment_file(), because a migration is the one thing
-- that silently drops a comment.
-- --------------------------------------------------------------------------

-- Canonical COMMENT text for `system_body`: table plus EVERY column.
-- ETL.md requires a comment on every column of every table we own. Edit here only;
-- etl/build_system_body.py re-asserts this, because a schema change silently drops
-- comments.

COMMENT ON TABLE system_body IS
'One row per BODY in a system -- stars, planets, everything the game enumerates. The
child of system_known, which is one row per system. Created by etl/build_system_body.py.

*** NOT POPULATED YET (DDL created 2026-08-12). *** The DDL exists so the foreign keys
can be declared, since DuckDB has no ALTER TABLE ADD FOREIGN KEY and adding one later
means rebuilding the table.

KEYS. system_body_id is a SURROGATE BIGINT PRIMARY KEY -- our own sequence, not derived
from anything. (system_id, system_body) is the natural key and is declared UNIQUE.

DELIBERATE DENORMALISATION: the primary star is recorded TWICE -- here as the row with
is_primary = true, and again in system_known.primary_star_body_id. That is intended, so
"what do I arrive at" needs no join, but it creates an invariant NOTHING IN THE DDL CAN
ENFORCE: for every system there should be exactly ONE is_primary row, and its body_id
should equal that system''s system_known.primary_star_body_id. The loader must maintain
both, and a consistency check is worth running after any load.

SCALE. spansh_body holds 569,697,301 bodies across 75,066,911 systems, so expect
~570M rows -- roughly 3x system_known. Two consequences: DuckDB enforces the foreign
keys, which makes a bulk load of this size materially slower than into an unconstrained
table; and every body must belong to an ALREADY-LOADED system_known row, so
system_known must be fully populated first or the FK will reject the rows.';

COMMENT ON COLUMN system_body.system_body_id IS
'SURROGATE PRIMARY KEY: our own BIGINT sequence number. Not the game''s body id64, not
spansh_body.body_id (which is only unique within a system), and not derived from the
name. Allocated max+1 for new bodies and NEVER renumbered, since other tables may key to
it and DuckDB silently drops inbound foreign keys on a CREATE OR REPLACE (ETL.md).
Merges must match on the natural key (system_id, system_body), never on this.';

COMMENT ON COLUMN system_body.system_id IS
'FK -> system_known.system_id. NOT NULL: a body cannot exist without its system. Note
this is the SURROGATE key of system_known, not the game''s id64 and not the boxel index --
so system_known must be populated before this table can be, or the foreign key rejects
every row.';

COMMENT ON COLUMN system_body.body_id IS
'FK -> body.body_id, the body TYPE -- one of the 49 star types or 19 planet types.
NULLABLE, and it genuinely happens: 13,616 planets in spansh_body carry a NULL sub_type,
and barycentres and belt clusters have no type at all. NULL means "type unknown", never
"no body".
Join body.code to match live journal StarType values and body.body to match the dumps''
sub_type strings. body.type tells you star vs planet, so there is no separate flag here.';

COMMENT ON COLUMN system_body.system_body IS
'The body''s designation WITHIN its system -- the body name with the system name stripped
off. The full name is system_known-derived-name || '' '' || system_body.
Two very different shapes, both normal:
  * PROCEDURAL systems use letter/number codes -- ''A'', ''B'', ''AB 1'', ''A 1'',
    ''A 2 a'' for a moon of the second planet of star A.
  * HAND-NAMED systems use real names -- in Sol these are ''Mercury'', ''Earth'',
    ''Moon'', ''Jupiter'', ''Io''. They are NOT codes and follow no pattern.
*** THE PRIMARY STAR IS USUALLY THE EMPTY STRING. *** Its body name equals the system
name exactly (body ''Sol'' in system ''Sol''), so stripping the prefix leaves ''''. That
is a real, distinct value and MUST NOT be converted to NULL -- this column is NOT NULL
and forms part of the unique key. Use is_primary rather than testing for '''' if you want
the arrival star.
Caveat: about 1 body in 200,000 has a name that does not start with its system name at
all, so the loader cannot assume the prefix strips cleanly.';

COMMENT ON COLUMN system_body.is_primary IS
'TRUE for the system''s PRIMARY (arrival) star -- the body you drop out of witchspace
beside. NOT NULL.
Redundant with system_known.primary_star_body_id BY DESIGN (see the table comment): the
same fact is stored in both places so neither query needs a join. The invariant is that
each system has exactly ONE is_primary row and that its body_id matches
system_known.primary_star_body_id -- and DuckDB cannot enforce either half of that, so
the loader owns it.
Do not confuse is_primary with "is a star": a system has many stars but one primary. And
the neutron-work gotcha applies -- in g/h-mass systems the neutron star is NEVER the
primary, so is_primary is no guide to whether a system contains a given class.';

COMMENT ON COLUMN system_body.discovered_time IS
'When the body was DISCOVERED. TIMESTAMP, naive, UTC by convention. NULLABLE -- and it
will be NULL for the overwhelming majority of rows, because almost nothing records this.

*** WHAT WE ACTUALLY HAVE. *** Searched every column in the database: there is no
per-body discovery timestamp for bodies in general. The only genuine one is
edastro_known_rare.discovered_at, and it covers just 101,943 of that catalogue''s 516,714
rows (19.7%) -- black holes and Wolf-Rayet stars only -- spanning 2016-10-25 to
2023-06-11, so it is also stale. Against ~570M bodies that is roughly 0.02% coverage.
edastro_neutron_star carries no time column at all.

*** WHAT LOOKS LIKE IT WOULD FILL THE GAP, AND MUST NOT. *** spansh_body.update_time is
populated for all 569,697,301 bodies and runs 2016-11-06 to the dump date, which makes it
tempting. It is LAST UPDATE, not discovery: a body re-scanned or re-uploaded years later
carries the later date, so it is only an UPPER BOUND on discovery and is simply wrong for
anything popular. Do NOT populate this column from it. If a "first time we saw any record
of this body" proxy is wanted, add a separate column named for what it is -- do not
overload this one, because a wrong timestamp here is indistinguishable from a right one.

Also distinct from edastro_known_rare.scanned_at (514,303 rows, 99.5% of that catalogue),
which is when EDAstro last saw a scan -- a third meaning again.

Note the game itself does not publish discovery attribution: there is no "First Discovered
by" or "First Mapped by" in any source we hold, and no DSS/mapped flag either. Your own
journals are the only place that records whether YOU were first (the WasDiscovered and
WasMapped flags on Scan events).';

COMMENT ON COLUMN system_body.solar_masses IS
'Mass in SOLAR masses. STARS ONLY -- NULL for every planet, which uses earth_masses
instead. Carried through from spansh_body.solar_masses (EDSM''s solarMasses fills the
handful of bodies Spansh lacks; EDAstro''s planet feed has no star data and supplies NULL).
Stored here so scan value is computable from this table plus `body` alone, without
re-joining the 569.7M-row spansh_body. Feeds the STAR branch of Frontier''s formula,
base = k + solar_masses * k / 66.25 with k = body.cr_value -- note the mass term is only
about 1.5% of an ordinary star''s value, so a NULL here costs little. NOT a scan value in
itself, and NOT the same quantity as earth_masses: 1 solar mass is ~333,000 Earth masses,
so never coalesce the two into one number.';

COMMENT ON COLUMN system_body.earth_masses IS
'Mass in EARTH masses. PLANETS ONLY -- NULL for every star, which uses solar_masses.
Carried through from spansh_body.earth_masses, with EDSM''s earthMasses and EDAstro''s
earthMasses filling bodies Spansh lacks. Feeds the PLANET branch of Frontier''s formula,
base = max(k + k * earth_masses^0.2 * 0.56591828, 500), with k = body.cr_value or
body.cr_value_terraformable where is_terraformable. *** The mass term is worth roughly 57%
of an Earth-like world''s value *** (181,126 Cr at mass 0 vs 283,617 Cr at 1 Earth mass),
so treating a NULL as 0 materially UNDERSTATES a planet -- unlike the star case. Check for
NULL rather than assuming.';

COMMENT ON COLUMN system_body.is_terraformable IS
'TRUE where the source recorded terraforming_state = ''Terraformable'' for this body.
Selects which k constant the value formula uses: body.cr_value_terraformable when TRUE,
body.cr_value otherwise. NULL means UNKNOWN, not FALSE -- the body predates the column or
came from a source that did not report the state -- so test IS NOT TRUE / IS TRUE rather
than relying on falsiness.
*** Deliberately NOT the same question as body.is_terraform_candidate. *** That column is
a per-TYPE fact ("does the game ever generate this type as a candidate"), this one is a
per-BODY fact ("was this particular body rolled terraformable"). They disagree on
Earth-like worlds by design: an ELW is never a candidate but always pays the terraform
bonus, which is folded into its cr_value. Use this column for value, is_terraform_candidate
for type-level reasoning, and never substitute one for the other.';

COMMENT ON COLUMN system_body.source IS
'Which feed contributed this body. *** READ THIS BEFORE TREATING A SYSTEM AS SCANNED. ***
  spansh           the only body source at galaxy scale; a real survey record
  edsm             7-DAY SLICE
  edastro          7-DAY SLICE, planets only
  edastro_rare     FULL Black-Holes/Wolf-Rayet-stars catalogue -- a CATALOGUE HIT
  edastro_neutron  FULL neutron-stars catalogue -- a CATALOGUE HIT
Where one designation was contributed by more than one feed the best-evidenced wins, in
the order above (a real scan beats a catalogue hit).

*** edastro_rare and edastro_neutron rows are NOT SCANS. *** They record that ONE object
is known to exist in that system and say nothing about the rest of it: a system whose
only row here is edastro_rare has never been surveyed. They were added because the full
per-class catalogues hold bodies no other feed has -- 63.7% of EDAstro''s 456,763 black
holes, 64.2% of its 59,960 Wolf-Rayets and 13.1% of its 4.14M neutron stars were absent
from this table, about 872,000 known bodies in total.

CONSEQUENCE: any "has this system been scanned" test must EXCLUDE these two sources,
e.g. `WHERE source NOT IN (''edastro_rare'',''edastro_neutron'')`. Counting a one-body
catalogue hit as a surveyed system puts a guaranteed positive into the numerator and a
near-empty system into the denominator, which inflates every rate fitted over scanned
space -- exactly the ``never fit rates on scanned systems'' failure in a new disguise.
Likewise exp_bodies/scan-value means must exclude them or they will be dragged toward 1
body per system. NULL means the row predates this column.';

COMMENT ON COLUMN system_body.id_poi IS
'FK to poi(poi_id): the point of interest catalogued ON THIS BODY, NULL for almost every row. *** THE FOREIGN KEY IS UNENFORCED ON ANY DATABASE THAT PREDATES THE COLUMN *** (no ALTER TABLE ADD CONSTRAINT in DuckDB); the --poi phase validates it in SQL after writing. Set only where Canonn names a body distinct from the system -- 8,166 events name the SYSTEM as the body, meaning "somewhere in here", and those go to system_known.id_poi instead of inventing a body. Rows inserted BY the --poi phase carry source=''canonn_codex'' and body_id NULL: a codex report proves the body exists but says nothing about its TYPE, and guessing one would corrupt the body census. Those inserts also make their system count as EXPLORED, so it leaves system_predicted -- correct, since somebody flew there and filed a report.';
