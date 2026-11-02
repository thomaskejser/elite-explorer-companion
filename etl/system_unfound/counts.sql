SELECT
  (SELECT count(*) FROM transform.system_unfound s
   WHERE NOT EXISTS (SELECT 1 FROM main.system_unfound t WHERE t.system = s.system)),
  (SELECT count(*) FROM main.system_unfound t JOIN transform.system_unfound s USING (system)
   WHERE t.type IS DISTINCT FROM s.type
      OR t.x IS DISTINCT FROM s.x OR t.y IS DISTINCT FROM s.y OR t.z IS DISTINCT FROM s.z
      OR t.dist_ly IS DISTINCT FROM s.dist_ly OR t.plx_snr IS DISTINCT FROM s.plx_snr
      OR t.vmag IS DISTINCT FROM s.vmag OR t.sp_type IS DISTINCT FROM s.sp_type
      OR t.band IS DISTINCT FROM s.band
      OR t.sector_id IS DISTINCT FROM s.sector_id OR t.sector IS DISTINCT FROM s.sector
      OR t.nearest IS DISTINCT FROM s.nearest OR t.nearest_ly IS DISTINCT FROM s.nearest_ly);
