CREATE OR REPLACE TABLE staging.primary_star AS
SELECT b.system_id64,
       CAST(any_value(bo.body_id) AS INTEGER) AS primary_star_body_id
FROM staging.spansh_body b
JOIN main.body bo ON bo.type = 'star' AND bo.body = b.sub_type
WHERE b.main_star AND b.type = 'Star' AND b.sub_type IS NOT NULL
GROUP BY b.system_id64;

COMMENT ON TABLE staging.primary_star IS
'WORK TABLE, rebuilt on every system_known load and safe to drop: the ARRIVAL star of each system in the staged Spansh body dump, already resolved to a main.body row.

It exists to make the body dump readable ONCE. transform.system_known is built in buckets to bound memory, and joining 569.7M raw body rows inside each bucket would scan that table once per bucket; reducing it to one narrow row per system first turns that into one expensive pass plus a cheap join.

The sub_type -> body_id resolution happens HERE, in a join restricted to body.type = ''star'', which is what stops a planet id ever reaching system_known.primary_star_body_id -- nothing in that table''s DDL would refuse one.

*** ONLY AS WIDE AS THE STAGED WINDOW. *** Built from staging.spansh_body, so after a 1-day stage it describes the systems that changed that day and NOT the galaxy. A system missing from it has an unknown arrival star, never a starless one.';

COMMENT ON COLUMN staging.primary_star.system_id64 IS
'The GAME''s system address, which is also main.system_known.system_id -- the join needs no bridge. One row per system: any_value collapses the rare system reporting two main_star bodies, which is a source defect rather than a real second arrival star.';

COMMENT ON COLUMN staging.primary_star.primary_star_body_id IS
'main.body.body_id for the arrival star''s type. NOT a body instance -- main.body is a dimension of the 49 star types, so this says WHAT the arrival star is, never which body it is. GOTCHA: in g/h-mass systems the neutron star or black hole is never the arrival star, so this is not a test for what a system contains.';
