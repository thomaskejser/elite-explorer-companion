-- Canonical COMMENT text for `body_type_census`: table plus EVERY column.
-- ETL.md requires a comment on every column of every table we own. Edit here only;
-- etl/build_body_type_census.py re-asserts this after each merge.

COMMENT ON TABLE body_type_census IS
'Galaxy-wide body census by type/sub_type, DERIVED from spansh_body by
etl/build_body_type_census.py. 63 rows. The denominator for "how rare is X".
*** Counts DISCOVERED bodies, not bodies in the galaxy, and NOT mapped bodies ***
-- no source carries a DSS/mapped flag, so every count is "at least FSS-detected".
Nor is it a galaxy census: only 38.6% of spine systems have any body data, and within
those we hold ~77% of the bodies the game itself declares. Never quote as a galaxy total.
Merged on the natural key (type, sub_type), never dropped (ETL.md). Counts are expected
to change on every Spansh refresh, so matched rows ARE updated.';

COMMENT ON COLUMN body_type_census.type IS
'''Star'' or ''Planet'', capitalised exactly as spansh_body.type stores it -- note this
DIFFERS from body.type, which is lowercase. Part of the natural key (type, sub_type).';

COMMENT ON COLUMN body_type_census.sub_type IS
'Body sub-type as spansh_body records it, e.g. ''Icy body'', ''Earth-like world'',
''M (Red dwarf) Star''. NULL is stored as the literal ''(unspecified)'' so it can take
part in the primary key. Joins to body.body for the 61 observed types. Part of the
natural key (type, sub_type).';

COMMENT ON COLUMN body_type_census.bodies IS
'count(*) of bodies of this type/sub_type in spansh_body. Rarity lives here: Icy body
196,229,831 down to Helium gas giant 18 -- the rarest planet class in the game. NOT a
galaxy total; see the table comment.';

COMMENT ON COLUMN body_type_census.share_all_pct IS
'This sub_type as a percentage of ALL 569.5M bodies with a non-null sub_type, stars and
planets together. Rounded to 6 dp.';

COMMENT ON COLUMN body_type_census.share_of_type_pct IS
'This sub_type as a percentage of its own `type` only -- i.e. of all Planets, or of all
Stars. Usually the more useful figure: Earth-like world is 0.1032% of planets but only
0.0793% of all bodies. Rounded to 6 dp.';
