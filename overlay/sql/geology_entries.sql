SELECT codex, min(entry) AS entry
FROM {{MODEL}}.codex_sighting
WHERE category = 'Geology'
GROUP BY codex
ORDER BY entry
