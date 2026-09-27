CREATE OR REPLACE MACRO sector_id_from_cell(x, y, z) AS (
    CAST(x AS BIGINT) + 128 * CAST(y AS BIGINT) + 16384 * CAST(z AS BIGINT)
);

CREATE OR REPLACE MACRO sector_id_from_name(s) AS (
    -(CAST(hash(clean_sector_name(s)) % 4294967296 AS BIGINT) + 1)
);

CREATE OR REPLACE MACRO sector_id(s, x, y, z) AS (
    CASE WHEN x IS NULL OR y IS NULL OR z IS NULL
         THEN sector_id_from_name(s)
         ELSE sector_id_from_cell(x, y, z)
    END
);

CREATE OR REPLACE MACRO sector_id_from_id64(i) AS (
    sector_id_from_cell(
        ((i >> (30 - 2 * (i & 7))) & ((1 << (14 - (i & 7))) - 1)) >> (7 - (i & 7)),
        ((i >> (17 - (i & 7))) & ((1 << (13 - (i & 7))) - 1)) >> (7 - (i & 7)),
        ((i >> 3) & ((1 << (14 - (i & 7))) - 1)) >> (7 - (i & 7)))
);
