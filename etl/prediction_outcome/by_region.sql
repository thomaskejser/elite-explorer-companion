WITH located AS (
    SELECT coalesce(r.region, '(no region)') AS region, o.*
    FROM main.prediction_outcome o
    LEFT JOIN main.system_known k ON k.system_id = o.system_id
    LEFT JOIN main.region r ON r.region_id = k.region_id
    WHERE o.revealed_by = 'survey'
),
largest AS (
    SELECT region, mass_code, max(n) AS top
    FROM (SELECT region, mass_code, sector, count(*) AS n FROM located GROUP BY 1, 2, 3)
    GROUP BY 1, 2
)
SELECT l.region, l.mass_code, count(*) AS n, count(DISTINCT l.sector) AS sectors,
       any_value(g.top) / count(*) AS top_share,
       sum(l.found_bh::INTEGER) / nullif(sum(l.p_bh), 0) AS oe_bh,
       sum(l.found_wr::INTEGER) / nullif(sum(l.p_wr), 0) AS oe_wr,
       sum(l.found_neutron::INTEGER) / nullif(sum(l.p_neutron), 0) AS oe_neutron,
       sum(l.found_herbig::INTEGER) / nullif(sum(l.p_herbig), 0) AS oe_herbig,
       sum(l.found_otype::INTEGER) / nullif(sum(l.p_otype), 0) AS oe_otype
FROM located l
JOIN largest g USING (region, mass_code)
GROUP BY 1, 2
HAVING count(*) >= ?
ORDER BY 2, 3 DESC;
