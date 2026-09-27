-- body_type_census: body census by type/sub_type, over the MODEL's own bodies.
-- Database: elite_mapping_v2.duckdb (the model).
-- A VIEW, not a table -- nothing here is stored, so it has no builder and no merge.
--
-- *** CREATE OR REPLACE VIEW SILENTLY DROPS EVERY COMMENT ON IT. *** The comments
-- therefore live in this file beside the definition, and scripts/apply_schema.py
-- re-applies the whole file every run and refuses to finish if one is missing.
CREATE OR REPLACE VIEW body_type_census AS
WITH t AS (
    SELECT coalesce(b.type, '(unspecified)') AS type,
           coalesce(b.body, '(unspecified)') AS sub_type,
           count(*)                          AS bodies
    FROM main.system_body sb
    LEFT JOIN main.body b ON b.body_id = sb.body_id
    GROUP BY 1, 2
)
SELECT type, sub_type, bodies,
       round(100.0 * bodies / sum(bodies) OVER (),                  6) AS share_all_pct,
       round(100.0 * bodies / sum(bodies) OVER (PARTITION BY type), 6) AS share_of_type_pct
FROM t;

COMMENT ON VIEW body_type_census IS
'Body census by type/sub_type over main.system_body, the model''s own 577,639,044 bodies. 62 rows, 2.7 s. The denominator for "how rare is X".

*** IT COUNTS THE MODEL, NOT ONE PROVIDER''S DUMP, AND THAT IS THE POINT. *** It was built from staging.spansh_galaxy_body, which is one feed''s snapshot; main.system_body merges Spansh, EDSM, EDAstro and Canonn, and it is what system_predicted and every rate in this project actually reason about. So the numbers differ from the old ones and the new ones are the right denominator: Icy body is 198,693,967 here against 196,229,831 counted off Spansh alone.

Reading the model also removes a whole class of mistake. A staging table is reached through a ROLE view that is repointed at whatever was staged last, so a 1-day stage would have silently turned this into a census of one day''s changes -- a rate quoted off a delta, the most expensive error this project makes (ETL.md). A `main` table cannot be repointed.

*** IT IS A VIEW, so it cannot go stale. *** It was a merged table with a builder, which meant the numbers were only as fresh as the last time somebody ran it. There is nothing worth storing: 62 rows, no code reads it, and a stored copy of a pure aggregate is one more thing that drifts from its source.

*** Counts DISCOVERED bodies, not bodies in the galaxy, and NOT mapped bodies *** -- no source carries a DSS/mapped flag, so every count is "at least FSS-detected". Nor is it a galaxy census: only 38.6% of systems have any body data, and within those we hold ~77% of the bodies the game itself declares. Never quote as a galaxy total.

The bodies column SUMS TO EXACTLY main.system_body''s row count, which is the check that it hides nothing -- the 237,793 rows with no body_id are counted under ''(unspecified)'' rather than dropped by the join.';

COMMENT ON COLUMN body_type_census.type IS
'''star'' or ''planet'', LOWERCASE, because it is main.body.type -- the opposite of the raw dumps, where staging.spansh_galaxy_body.type is capitalised. ''(unspecified)'' for the 237,793 system_body rows carrying no body_id: a body we know exists without knowing what it is, mostly Spansh rows whose sub_type the parser could not resolve, plus Canonn reports that name a body as evidence it exists.';

COMMENT ON COLUMN body_type_census.sub_type IS
'main.body.body -- the specific type, e.g. ''Icy body'', ''Earth-like world'', ''M (Red dwarf) Star''. 61 of the dimension''s 68 declared types are observed; the absent ones are real classes nothing in the model has yet been resolved to, NOT types that do not exist. ''(unspecified)'' where body_id is NULL.';

COMMENT ON COLUMN body_type_census.bodies IS
'count(*) of main.system_body rows of this type. Rarity lives here: Icy body 198,693,967 down to the single-digit planet classes. NOT a galaxy total; see the view comment.';

COMMENT ON COLUMN body_type_census.share_all_pct IS
'This sub_type as a percentage of ALL bodies the model holds, stars and planets together. Rounded to 6 dp: a float aggregate summed in parallel varies in its last bits between runs (ETL.md), and rounding is what stops two queries of the same unchanged data disagreeing.';

COMMENT ON COLUMN body_type_census.share_of_type_pct IS
'This sub_type as a percentage of its own `type` only -- of all planets, or of all stars. Usually the more useful figure: Earth-like world is a far larger share of planets than of all bodies. Rounded to 6 dp.';
