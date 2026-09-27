SELECT system, dist_ly, plx_snr, vmag, coalesce(sp_type, ''), coalesce(nearest, '--'),
       nearest_ly
FROM main.system_unfound
WHERE band = 'near'
ORDER BY coalesce(nearest_ly, 1e9), dist_ly
LIMIT 12;
