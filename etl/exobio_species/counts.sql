SELECT
  (SELECT count(*) FROM transform.exobio_species s
   WHERE NOT EXISTS (SELECT 1 FROM main.exobio_species t WHERE t.species_key = s.species_key)),
  (SELECT count(*) FROM main.exobio_species t JOIN transform.exobio_species s USING (species_key)
   WHERE t.genus_key      IS DISTINCT FROM s.genus_key
      OR t.species        IS DISTINCT FROM s.species
      OR t.genus          IS DISTINCT FROM s.genus
      OR t.cr_value       IS DISTINCT FROM s.cr_value
      OR t.colony_m       IS DISTINCT FROM s.colony_m
      OR t.bodies_codexed IS DISTINCT FROM s.bodies_codexed);
