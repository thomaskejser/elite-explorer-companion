CREATE TABLE IF NOT EXISTS system_green_giant (
    system_id      BIGINT  NOT NULL,
    body           VARCHAR NOT NULL,
    system         VARCHAR NOT NULL,
    class          VARCHAR NOT NULL,
    surface_temp_k DOUBLE  NOT NULL,
    verdict        VARCHAR NOT NULL,
    x              DOUBLE,
    y              DOUBLE,
    z              DOUBLE,
    PRIMARY KEY (system_id, body)
);

COMMENT ON TABLE system_green_giant IS
'DERIVED PREDICTION: gas giants somebody has scanned that probably render green in game, a "green gas giant". One row per body the model calls green. Built by etl/system_green_giant/refresh.py from staging.spansh_galaxy_body with the macros in schema/macro/ggg.sql; read by the overlay''s Nearest table through the mirror.

THE MODEL. Seven cloud layers step evenly up from SurfaceTemperature to the lower of a reach set by temperature and bulk density and a ceiling set by temperature; a giant is green when a layer lands exactly, to the last bit of a 32-bit float, on a colour band''s border. It is CMDR Arcanic and CMDR Regza''s model as edGGG''s Density Demo states it (ed-ggg.github.io/edggg/densitydemo.html), written afresh; overlay/DESIGN.md gives the rules, and the overlay''s ggg::predict is the same model in Rust with a test holding the two identical.

*** WHOLE-NUMBER TEMPERATURES ARE LEFT OUT. *** Spansh rounds some temperatures to whole kelvins and every border is a whole number, so a whole Spansh temperature cannot be told from a rounded one; a green giant at exactly 158 K or 640 K is missed here and found by the overlay from the journal.
*** A LEAD, NOT A FIND. *** Over Spansh''s 42,036,025 gas giants it calls 23 GREEN, 22 of them in a system with a catalogued green giant, and 32 GREEN_LOW_CONFIDENCE. A nudged giant off a border is unpredictable, not ruled out, so absence here says nothing about class II giants or any giant at 80-122 K.
*** THIS TABLE DELETES. *** A row is a prediction: a model change or a corrected temperature makes it false rather than stale, so the loader deletes rows the transform no longer produces and says how many.
*** THESE BODIES ARE ALREADY SCANNED. *** The model needs a measured temperature, mass and radius, so every row is somebody else''s discovery; the green is the find, not the body.';

COMMENT ON COLUMN system_green_giant.system_id IS 'The game''s id64 -- main.system_known.system_id. Half the key.';
COMMENT ON COLUMN system_green_giant.body IS 'Full body name as Spansh spells it, system prefix included. Half the key.';
COMMENT ON COLUMN system_green_giant.system IS 'Full, pasteable system name, composed with the sector_id = 0 test.';
COMMENT ON COLUMN system_green_giant.class IS 'Spansh sub_type, e.g. ''Class I gas giant''.';
COMMENT ON COLUMN system_green_giant.surface_temp_k IS 'Spansh surface_temp_k, the journal''s SurfaceTemperature; never a whole number here, because Spansh rounds some temperatures to whole kelvins and the model needs every digit.';
COMMENT ON COLUMN system_green_giant.verdict IS '''GREEN'': a layer exactly on a border, outside the nudge, on a kind with catalogued green giants. ''GREEN_LOW_CONFIDENCE'': a layer on a border of a nudged giant (one the game may have moved off it) or of a class II, class V or helium giant, or a layer one 32-bit step off a border on a ladder that tops out at its reach.';
COMMENT ON COLUMN system_green_giant.x IS 'main.system_known.x, ly.';
COMMENT ON COLUMN system_green_giant.y IS 'main.system_known.y, ly.';
COMMENT ON COLUMN system_green_giant.z IS 'main.system_known.z, ly.';
