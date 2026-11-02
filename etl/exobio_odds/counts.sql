SELECT
  (SELECT count(*) FROM transform.exobio_odds s
   WHERE NOT EXISTS (SELECT 1 FROM main.exobio_odds t
                     WHERE t.atmosphere = s.atmosphere AND t.body_type = s.body_type
                       AND t.temp_band = s.temp_band AND t.star = s.star)),
  (SELECT count(*) FROM main.exobio_odds t
   JOIN transform.exobio_odds s USING (atmosphere, body_type, temp_band, star)
   WHERE t.bodies         IS DISTINCT FROM s.bodies
      OR t.p_bio          IS DISTINCT FROM s.p_bio
      OR t.signals_bio    IS DISTINCT FROM s.signals_bio
      OR t.codexed_bodies IS DISTINCT FROM s.codexed_bodies
      OR t.cr_species     IS DISTINCT FROM s.cr_species
      OR t.cr_bio         IS DISTINCT FROM s.cr_bio
      OR t.likely_species IS DISTINCT FROM s.likely_species);
