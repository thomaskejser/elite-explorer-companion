MERGE INTO main.exobio_species AS t
USING transform.exobio_species AS s ON t.species_key = s.species_key
WHEN MATCHED AND (t.genus_key      IS DISTINCT FROM s.genus_key
               OR t.species        IS DISTINCT FROM s.species
               OR t.genus          IS DISTINCT FROM s.genus
               OR t.cr_value       IS DISTINCT FROM s.cr_value
               OR t.colony_m       IS DISTINCT FROM s.colony_m
               OR t.bodies_codexed IS DISTINCT FROM s.bodies_codexed)
THEN UPDATE SET genus_key      = s.genus_key,
                species        = s.species,
                genus          = s.genus,
                cr_value       = s.cr_value,
                colony_m       = s.colony_m,
                bodies_codexed = s.bodies_codexed
WHEN NOT MATCHED THEN INSERT
    (species_key, genus_key, species, genus, cr_value, colony_m, bodies_codexed)
VALUES
    (s.species_key, s.genus_key, s.species, s.genus, s.cr_value, s.colony_m, s.bodies_codexed);
