MERGE INTO main.exobio_genus_odds AS t
USING transform.exobio_genus_odds AS s
   ON t.atmosphere = s.atmosphere AND t.body_type = s.body_type
  AND t.temp_band = s.temp_band AND t.star = s.star AND t.genus = s.genus
WHEN MATCHED AND (t.genus_key IS DISTINCT FROM s.genus_key
               OR t.bodies    IS DISTINCT FROM s.bodies
               OR t.share     IS DISTINCT FROM s.share
               OR t.cr_genus  IS DISTINCT FROM s.cr_genus)
THEN UPDATE SET genus_key = s.genus_key,
                bodies    = s.bodies,
                share     = s.share,
                cr_genus  = s.cr_genus
WHEN NOT MATCHED THEN INSERT
    (atmosphere, body_type, temp_band, star, genus, genus_key, bodies, share, cr_genus)
VALUES
    (s.atmosphere, s.body_type, s.temp_band, s.star, s.genus, s.genus_key, s.bodies, s.share,
     s.cr_genus);
