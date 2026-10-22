CREATE OR REPLACE VIEW system_all AS

SELECT k.system_id,

       CASE WHEN k.sector_id = 0 THEN k.system_in_sector
            ELSE sc.sector || ' ' || k.system_in_sector END AS system,
       CASE WHEN k.sector_id = 0 THEN NULL ELSE sc.sector END AS sector,
       r.region,
       k.mass_code,
       FALSE AS is_predicted,
       k.x, k.y, k.z
FROM system_known k
JOIN sector sc      ON sc.sector_id = k.sector_id

LEFT JOIN region r  ON r.region_id  = k.region_id

UNION ALL

SELECT p.system_id,
       p.system,
       p.sector,
       r.region,
       p.mass_code,
       TRUE AS is_predicted,
       p.x, p.y, p.z
FROM system_predicted p

LEFT JOIN sector sc ON sc.sector    = p.sector
LEFT JOIN region r  ON r.region_id  = sc.region_id
WHERE NOT p.is_catalog;

COMMENT ON VIEW system_all IS
'Every system we can name, observed and inferred, with its human-readable system, sector and region names and its mass code. 197,826,126 rows: 197,764,363 observed (is_predicted FALSE) plus 61,763 boxel-predicted (TRUE). A VIEW over system_known, system_predicted, sector and region -- nothing is stored, and it costs whatever the query over it costs.

*** ONE ROW PER SYSTEM. The catalogued half of system_predicted is EXCLUDED on purpose. *** system_predicted holds two populations and only one of them is a system we inferred: all 2,207,261 is_catalog rows resolve to a system_known row by id64 (measured, 100%), while all 61,763 boxel rows resolve to none. Including both halves would list 2.2M systems twice -- once observed, once predicted -- and silently inflate every count taken over this view. Those systems are still here, in the observed half, which is what they are.

*** is_predicted MEANS "WE INFERRED THIS SYSTEM EXISTS", NOT "WE HAVE ODDS FOR IT". *** A TRUE row is a Stellar-Forge-implied system in no dump anywhere, so it has BOXEL-CENTROID coordinates only -- x/y/z are good to about +/-640 ly at mass code h, and you can arrive and find nothing at the exact spot. A FALSE row has exact coordinates. Never compare the two on distance without saying which is which. For the per-target probabilities, join system_predicted directly; they are deliberately not here, because this view answers "what systems are there and what are they called".

Joining back: system_id is the game''s own key and is NULL on every boxel row -- a system nobody has reported has no id64 to know. Use system when you need a key that spans both halves.

DERIVED view: schema/system_all.sql, applied by scripts/apply_schema.py.';

COMMENT ON COLUMN system_all.system_id IS
'system_known.system_id, which IS the game''s id64 -- see that column''s comment. NULL on every predicted row: a boxel prediction has no system_known parent to take one from, and a system nobody has reported has no id64 to know. Use it to join back to system_known, system_body or poi; use system when the join has to cover both halves.';

COMMENT ON COLUMN system_all.system IS
'The full name the game uses, composed for the observed half as sector || '' '' || "system" and taken verbatim from system_predicted for the inferred half. THE ONLY KEY THAT SPANS BOTH HALVES. Hand-named systems (Sol, Colonia, 61 Ursae Majoris) stand alone: sector_id = 0 is the ''crafted'' SENTINEL and its name is not prefixed. Test that by sector_id and never by sector.is_crafted, which is TRUE for 424 real named sectors as well.';

COMMENT ON COLUMN system_all.sector IS
'Human-readable sector name (''Blaa Hypai''). NULL for the 149,749 hand-named systems, which carry no sector in their name -- that is a real absence and not a gap to fill. Every one of the 2,269,024 system_predicted rows resolves to a sector row, so this is never NULL on the inferred half.';

COMMENT ON COLUMN system_all.region IS
'Human-readable name of the galactic region, one of the game''s 42 hand-drawn regions (''Inner Orion Spur''). Reached two different ways by the two halves: directly from system_known.region_id, which is populated in all 197,764,363 rows, and for predicted systems the long way through the sector name to sector.region_id. Nullable by declaration on both sides rather than by observation -- the joins are LEFT so a lapsed assumption shows up as a NULL region instead of a silently shorter view.';

COMMENT ON COLUMN system_all.mass_code IS
'The size class of the generator cube the system sits in, ''a'' (smallest) to ''h'' (largest), read straight off the name. THE STRONGEST SINGLE PREDICTOR IN THE PROJECT: Wolf-Rayets are effectively absent outside h, and p_bh runs about 0.46 at h against 0.04 at e. NULL for the 149,724 hand-named systems, which have no procedural name to read it from.';

COMMENT ON COLUMN system_all.is_predicted IS
'FALSE if somebody has actually reported this system (it came from system_known), TRUE if we merely inferred that it exists from a gap in the Stellar Forge boxel index. *** THE TWO ARE NOT INTERCHANGEABLE AND THIS COLUMN IS THE ONLY THING THAT SAYS SO. *** A TRUE row is a place worth flying to and never evidence anything is there; its coordinates are a boxel centroid, up to 1280 ly across. It also means nobody has been there, which for an explorer is the point. Only 61,763 rows are TRUE, and RECOMMENDATIONS.md R2/R3 warn that this layer is thin and heavily CORE-BIASED -- a lower bound, and not a usable basis for fringe estimates.';

COMMENT ON COLUMN system_all.x IS
'Galactic x in light-years. EXACT on the observed half; a BOXEL CENTROID where is_predicted, good to roughly +/-640 ly at mass code h. Filter on is_predicted before measuring any distance you intend to trust.';

COMMENT ON COLUMN system_all.y IS
'Galactic y in light-years. EXACT on the observed half; a BOXEL CENTROID where is_predicted -- see system_all.x.';

COMMENT ON COLUMN system_all.z IS
'Galactic z in light-years. EXACT on the observed half; a BOXEL CENTROID where is_predicted -- see system_all.x.';
