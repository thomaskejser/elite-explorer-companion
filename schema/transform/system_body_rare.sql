CREATE SCHEMA IF NOT EXISTS transform;

DROP TABLE IF EXISTS transform.system_body_rare;

CREATE TABLE transform.system_body_rare (
    system_id     BIGINT    NOT NULL,
    system_name   VARCHAR   NOT NULL,
    body_name     VARCHAR   NOT NULL,
    star_type     VARCHAR,
    is_main_star  BOOLEAN   NOT NULL,
    discovered_at TIMESTAMP,
    PRIMARY KEY (system_id, body_name)
);

INSERT INTO transform.system_body_rare
WITH wanted AS (
    SELECT DISTINCT system_name FROM staging.edastro_known_rare
    WHERE system_name IS NOT NULL AND body_name IS NOT NULL
),
named AS (
    SELECT k.system_id,
           CASE WHEN k.sector_id = 0 OR sc.sector IS NULL THEN k.system_in_sector
                ELSE sc.sector || ' ' || k.system_in_sector END AS full_name
    FROM main.system_known k
    LEFT JOIN main.sector sc ON sc.sector_id = k.sector_id
),
resolved AS (
    SELECT n.full_name, min(n.system_id) AS system_id
    FROM named n JOIN wanted w ON w.system_name = n.full_name
    GROUP BY 1
    HAVING count(*) = 1
)
SELECT r.system_id, any_value(k.system_name), k.body_name,
       any_value(k.star_type), coalesce(bool_or(k.is_main_star), false),
       min(TRY_CAST(k.discovered_at AS TIMESTAMP))
FROM staging.edastro_known_rare k
JOIN resolved r ON r.full_name = k.system_name
WHERE k.body_name IS NOT NULL
GROUP BY r.system_id, k.body_name;

COMMENT ON TABLE transform.system_body_rare IS
'TRANSFORM: staging.edastro_known_rare resolved from system NAME to system_id. Rebuilt on every system_body load -- derived, never edited, safe to drop.

It exists because that catalogue carries no id64, and resolving 400k names against 200M systems once is cheaper than doing it inside every bucket of the merge.

*** A NAME THAT RESOLVES TO MORE THAN ONE SYSTEM IS DROPPED, NOT GUESSED. *** 1,477 full system names belong to several systems, all hand-named; picking one would write a coin-flip id into a table that cannot be rebuilt. The full name is composed with the sector_id = 0 test, the only test that means a name stands alone.

(system_id, body_name) is the PRIMARY KEY: a star listed in both catalogues collapses to one row.';

COMMENT ON COLUMN transform.system_body_rare.system_id IS
'main.system_known.system_id for the unique system bearing that full name.';

COMMENT ON COLUMN transform.system_body_rare.system_name IS
'The full system name as the catalogue spells it, kept so the body name can be stripped to a designation.';

COMMENT ON COLUMN transform.system_body_rare.body_name IS
'Full body name including the system prefix. Half the key.';

COMMENT ON COLUMN transform.system_body_rare.star_type IS
'Catalogue star type, matched against main.body.body for type ''star''.';

COMMENT ON COLUMN transform.system_body_rare.is_main_star IS
'TRUE when either catalogue row marks it the arrival star.';

COMMENT ON COLUMN transform.system_body_rare.discovered_at IS
'Earliest EDSM discovery date the catalogue carries for the star. NULL on most rows; a NULL is "not recorded", never "undiscovered".';
