CREATE TABLE IF NOT EXISTS body_poi (
    system_id BIGINT  NOT NULL,
    body      VARCHAR NOT NULL,
    poi_id    INTEGER NOT NULL,
    source    VARCHAR NOT NULL,
    PRIMARY KEY (system_id, body, poi_id)
);

COMMENT ON TABLE body_poi IS
'One row per (body, point of interest) the model can place on a named body: the body-level half of system_poi with the body kept. *** A LOCATION, NOT A CENSUS. *** system_poi holds every POI of a system; most have no body here, because only Canonn names a body and a GEC write-up names one only in its prose. Absent here means nobody wrote down which body, NOT that the POI is not on one. DERIVED table: etl/body_poi/load.py, from main.system_body and staging.edastro_point_of_interest.';

COMMENT ON COLUMN body_poi.system_id IS
'The game''s id64, copied from system_body.system_id or the GEC row''s id64, which system_known.system_id is.';

COMMENT ON COLUMN body_poi.body IS
'The body''s name relative to its system, exactly as system_body.system_body spells it ("1 c", "AB 2 a", "7 B Ring"); '''' is the primary star. Every row matches a system_body row of the same system, so a GEC mention of a body nobody has reported is left out.';

COMMENT ON COLUMN body_poi.poi_id IS
'REFERENCES poi.poi_id: the POI''s name and class are read through the join.';

COMMENT ON COLUMN body_poi.source IS
'''canonn'' where system_body.poi_id attributes the POI (a Canonn report naming the body), ''gec'' where a GEC write-up''s summary or description names the body in full, system name then designation. Where both place one POI on one body the row is ''canonn''.';
