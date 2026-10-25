SELECT system, cr_expected, candidate_bodies, unmapped_bodies, worked_bodies,
       substr(best_body, length(system) + 2) AS best_body, best_species, year(last_reported) AS reported
FROM {{MODEL}}.system_exobio
WHERE system_id = ? OR (? IS NULL AND system = ?)
