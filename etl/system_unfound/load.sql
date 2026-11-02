MERGE INTO main.system_unfound AS t
USING transform.system_unfound AS s ON t.system = s.system
WHEN MATCHED AND (t.type IS DISTINCT FROM s.type
      OR t.x IS DISTINCT FROM s.x OR t.y IS DISTINCT FROM s.y OR t.z IS DISTINCT FROM s.z
      OR t.dist_ly IS DISTINCT FROM s.dist_ly OR t.plx_snr IS DISTINCT FROM s.plx_snr
      OR t.vmag IS DISTINCT FROM s.vmag OR t.sp_type IS DISTINCT FROM s.sp_type
      OR t.band IS DISTINCT FROM s.band
      OR t.sector_id IS DISTINCT FROM s.sector_id OR t.sector IS DISTINCT FROM s.sector
      OR t.nearest IS DISTINCT FROM s.nearest OR t.nearest_ly IS DISTINCT FROM s.nearest_ly)
    THEN UPDATE SET type = s.type, x = s.x, y = s.y, z = s.z, dist_ly = s.dist_ly,
                    plx_snr = s.plx_snr, vmag = s.vmag, sp_type = s.sp_type,
                    band = s.band, sector_id = s.sector_id, sector = s.sector,
                    nearest = s.nearest, nearest_ly = s.nearest_ly
WHEN NOT MATCHED
    THEN INSERT (system, type, x, y, z, dist_ly, plx_snr, vmag, sp_type, band,
                 sector_id, sector, nearest, nearest_ly)
         VALUES (s.system, s.type, s.x, s.y, s.z, s.dist_ly, s.plx_snr, s.vmag,
                 s.sp_type, s.band, s.sector_id, s.sector, s.nearest, s.nearest_ly);
