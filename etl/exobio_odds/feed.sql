INSERT INTO transform.exobio_feed
SELECT system_id64, name, sub_type, atmosphere_type, surface_temp_k, is_landable,
       signal_biology, genuses IS NOT NULL AS has_genus, update_time::TIMESTAMPTZ AS updated
FROM staging.${table}
WHERE type = 'Planet' AND atmosphere_type LIKE 'Thin%'
  AND sub_type IN ('High metal content world', 'Rocky body', 'Icy body',
                   'Rocky Ice world', 'Metal-rich body');
