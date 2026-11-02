SELECT sector
FROM {{MODEL}}.sector
WHERE sector_id <> 0
ORDER BY sector
