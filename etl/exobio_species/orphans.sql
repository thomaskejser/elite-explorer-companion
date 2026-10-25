SELECT t.species_key, t.species
FROM main.exobio_species t
WHERE NOT EXISTS (SELECT 1 FROM transform.exobio_species s WHERE s.species_key = t.species_key)
ORDER BY t.species;
