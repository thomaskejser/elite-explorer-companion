CREATE OR REPLACE MACRO wr_cross(x, z) AS (
    coalesce(floor((x + 49985) / 1280) BETWEEN 38 AND 40
             OR floor((z + 24105) / 1280) BETWEEN 18 AND 19, false)
);
