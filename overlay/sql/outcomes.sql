SELECT system, strftime(first_visited_utc, '%Y-%m-%d') AS visited, is_catalog, {{P_COLUMNS}}, {{FOUND_COLUMNS}},
       len(scanned_stars) AS stars, all_bodies_found
FROM system_outcome
ORDER BY first_visited_utc DESC
