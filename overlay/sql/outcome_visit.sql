INSERT INTO system_outcome
    (system, system_id, sector, first_visited_utc, is_catalog, mass_code, {{P_COLUMNS}}, {{FOUND_COLUMNS}},
     scanned_stars, all_bodies_found, updated_utc)
SELECT p.system, p.system_id, p.sector, coalesce(try_cast(? AS TIMESTAMPTZ), now()), p.is_catalog, p.mass_code,
       {{P_COLUMNS_P}}, {{FOUND_FALSE}}, []::VARCHAR[], false, now()
FROM {{MODEL}}.system_predicted p
WHERE p.system = ? AND NOT EXISTS (SELECT 1 FROM system_outcome o WHERE o.system = p.system)
