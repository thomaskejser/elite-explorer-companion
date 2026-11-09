CREATE OR REPLACE MACRO ggg_kind(class) AS (
    CASE WHEN lower(replace(class, '-', ' ')) LIKE '%helium%' THEN 'helium'
         WHEN lower(replace(class, '-', ' ')) LIKE '%water giant%' THEN 'water_giant'
         WHEN lower(replace(class, '-', ' ')) LIKE '%ammonia%' AND lower(class) LIKE '%life%' THEN 'ammonia_life'
         WHEN lower(replace(class, '-', ' ')) LIKE '%water%' AND lower(class) LIKE '%life%' THEN 'water_life'
         WHEN lower(class) LIKE '%class v%' THEN 'class5'
         WHEN lower(class) LIKE '%class iv%' THEN 'class4'
         WHEN lower(class) LIKE '%class iii%' THEN 'class3'
         WHEN lower(class) LIKE '%class ii%' THEN 'class2'
         WHEN lower(class) LIKE '%class i%' THEN 'class1'
    END
);

CREATE OR REPLACE MACRO ggg_cracks(kind) AS (
    CASE WHEN kind IN ('class1', 'ammonia_life')
         THEN [115.0, 250.0, 270.0, 370.0, 700.0, 900.0, 1400.0]::DOUBLE[]
         ELSE [114.0, 210.0, 270.0, 370.0, 700.0, 900.0, 1400.0]::DOUBLE[]
    END
);

CREATE OR REPLACE MACRO ggg_ceiling(t) AS (
    CASE WHEN t < 75.0 THEN 100.0
         WHEN t < 330.0 THEN 340.0
         WHEN t < 680.0 THEN 700.0
         WHEN t < 900.0 THEN 1200.0
         WHEN t < 1400.0 THEN 1500.0
         ELSE 5000.0
    END
);

CREATE OR REPLACE MACRO ggg_min_step(kind) AS (
    CASE WHEN kind = 'class3' THEN 30.0 END
);

CREATE OR REPLACE MACRO ggg_nudged(kind, t) AS (
    (t >= 80.0 AND t < 122.0)
    OR t < CASE kind WHEN 'class2' THEN 280.0
                     WHEN 'class3' THEN 415.0
                     WHEN 'class4' THEN 700.0
                     WHEN 'class5' THEN 1500.0
                     ELSE '-inf'::DOUBLE
           END
);

CREATE OR REPLACE MACRO ggg_confirmed(kind) AS (
    kind NOT IN ('class2', 'class5', 'helium')
);

CREATE OR REPLACE MACRO ggg_depth(t, mass_em, radius_m) AS (
    5.0 / 9.0 * 1300.0 * pow(t / 1300.0, 1.2)
    * pow(mass_em * 5.97219e24 / (4.0 / 3.0 * pi() * pow(radius_m, 3)), 0.2)
);

CREATE OR REPLACE MACRO ggg_rungs(t, top, min_step) AS (
    list_transform(range(7), k ->
        (t::FLOAT::DOUBLE + k * greatest((top - t::FLOAT::DOUBLE) / 7.0, coalesce(min_step::DOUBLE, '-inf'::DOUBLE)))::FLOAT)
);

CREATE OR REPLACE MACRO ggg_land(rungs, cracks, one_off_counts) AS (
    CASE WHEN list_has_any(rungs, list_transform(cracks, c -> c::FLOAT))
         THEN 'ON'
         WHEN one_off_counts
              AND list_has_any(rungs, flatten(list_transform(cracks, c ->
                      [nextafter(c::FLOAT, 0::FLOAT), nextafter(c::FLOAT, 'inf'::FLOAT)])))
         THEN 'ONE_OFF'
         ELSE 'OFF'
    END
);

CREATE OR REPLACE MACRO ggg_landing(kind, t, reach) AS (
    ggg_land(ggg_rungs(t, least(t + reach, ggg_ceiling(t)), ggg_min_step(kind)),
             ggg_cracks(kind),
             t + reach < ggg_ceiling(t) AND ggg_min_step(kind) IS NULL)
);

CREATE OR REPLACE MACRO ggg_verdict_from(kind, t, landing) AS (
    CASE WHEN landing = 'ON' AND ggg_confirmed(kind) AND NOT ggg_nudged(kind, t)
         THEN 'GREEN'
         WHEN landing <> 'OFF'
         THEN 'GREEN_LOW_CONFIDENCE'
         WHEN ggg_nudged(kind, t)
         THEN 'UNPREDICTABLE'
         ELSE 'NOT_GREEN'
    END
);

CREATE OR REPLACE MACRO ggg_verdict_of(kind, t, mass_em, radius_m) AS (
    CASE WHEN kind IS NULL OR t IS NULL OR NOT (mass_em > 0) OR NOT (radius_m > 0)
         THEN 'UNPREDICTABLE'
         ELSE ggg_verdict_from(kind, t, ggg_landing(kind, t, ggg_depth(t, mass_em, radius_m)))
    END
);

CREATE OR REPLACE MACRO ggg_verdict(class, t, mass_em, radius_m) AS (
    ggg_verdict_of(ggg_kind(class), t, mass_em, radius_m)
);
