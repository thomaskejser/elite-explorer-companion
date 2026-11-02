SELECT
  (SELECT count(*) FROM transform.exobio_genus_odds s
   WHERE NOT EXISTS (SELECT 1 FROM main.exobio_genus_odds t
                     WHERE t.atmosphere = s.atmosphere AND t.body_type = s.body_type
                       AND t.temp_band = s.temp_band AND t.star = s.star AND t.genus = s.genus)),
  (SELECT count(*) FROM main.exobio_genus_odds t
   JOIN transform.exobio_genus_odds s USING (atmosphere, body_type, temp_band, star, genus)
   WHERE t.genus_key IS DISTINCT FROM s.genus_key
      OR t.bodies    IS DISTINCT FROM s.bodies
      OR t.share     IS DISTINCT FROM s.share
      OR t.cr_genus  IS DISTINCT FROM s.cr_genus);
