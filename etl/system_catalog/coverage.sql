WITH hand_named AS (
    SELECT system_in_sector AS name, system_id FROM main.system_known WHERE sector_id = 0
)
SELECT c.type,
       count(*)                  AS names,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM hand_named h
                                      WHERE h.system_id = c.system_id
                                        AND h.name = c.system)) AS own_name,
       count(c.system_id)        AS in_game
FROM main.system_catalog c
GROUP BY 1
ORDER BY in_game DESC, names DESC;
