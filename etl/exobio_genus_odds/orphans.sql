SELECT t.atmosphere, t.body_type, t.temp_band, t.star, t.genus
FROM main.exobio_genus_odds t
WHERE NOT EXISTS (SELECT 1 FROM transform.exobio_genus_odds s
                  WHERE s.atmosphere = t.atmosphere AND s.body_type = t.body_type
                    AND s.temp_band = t.temp_band AND s.star = t.star AND s.genus = t.genus)
ORDER BY ALL;
