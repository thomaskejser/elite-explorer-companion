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
