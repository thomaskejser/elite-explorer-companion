SELECT system,
       sqrt((x - ?) ^ 2 + (y - ?) ^ 2 + (z - ?) ^ 2) AS ly,
       cr_expected, candidate_bodies, unmapped_bodies, worked_bodies, year(last_reported) AS reported
FROM {{MODEL}}.system_exobio
WHERE x BETWEEN ? - {{EXOBIO_RANGE_LY}} AND ? + {{EXOBIO_RANGE_LY}}
  AND y BETWEEN ? - {{EXOBIO_RANGE_LY}} AND ? + {{EXOBIO_RANGE_LY}}
  AND z BETWEEN ? - {{EXOBIO_RANGE_LY}} AND ? + {{EXOBIO_RANGE_LY}}
  AND sqrt((x - ?) ^ 2 + (y - ?) ^ 2 + (z - ?) ^ 2) <= {{EXOBIO_RANGE_LY}}
  AND system NOT IN (SELECT system FROM system_visited)
ORDER BY cr_expected DESC, ly
LIMIT ?
