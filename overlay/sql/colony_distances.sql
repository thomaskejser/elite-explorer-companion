SELECT species_key, colony_m
FROM {{MODEL}}.exobio_species
WHERE colony_m IS NOT NULL
