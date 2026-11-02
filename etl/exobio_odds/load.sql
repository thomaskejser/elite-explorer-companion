MERGE INTO main.exobio_odds AS t
USING transform.exobio_odds AS s
   ON t.atmosphere = s.atmosphere AND t.body_type = s.body_type
  AND t.temp_band = s.temp_band AND t.star = s.star
WHEN MATCHED AND (t.bodies         IS DISTINCT FROM s.bodies
               OR t.p_bio          IS DISTINCT FROM s.p_bio
               OR t.signals_bio    IS DISTINCT FROM s.signals_bio
               OR t.codexed_bodies IS DISTINCT FROM s.codexed_bodies
               OR t.cr_species     IS DISTINCT FROM s.cr_species
               OR t.cr_bio         IS DISTINCT FROM s.cr_bio
               OR t.likely_species IS DISTINCT FROM s.likely_species)
THEN UPDATE SET bodies         = s.bodies,
                p_bio          = s.p_bio,
                signals_bio    = s.signals_bio,
                codexed_bodies = s.codexed_bodies,
                cr_species     = s.cr_species,
                cr_bio         = s.cr_bio,
                likely_species = s.likely_species
WHEN NOT MATCHED THEN INSERT
    (atmosphere, body_type, temp_band, star, bodies, p_bio, signals_bio, codexed_bodies,
     cr_species, cr_bio, likely_species)
VALUES
    (s.atmosphere, s.body_type, s.temp_band, s.star, s.bodies, s.p_bio, s.signals_bio,
     s.codexed_bodies, s.cr_species, s.cr_bio, s.likely_species);
