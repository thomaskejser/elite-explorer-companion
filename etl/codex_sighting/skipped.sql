SELECT count(*) FILTER (WHERE r.region_id IS NULL) AS no_region,
       count(*) FILTER (WHERE r.region_id IS NOT NULL AND k.system_id IS NULL) AS no_system
FROM staging.edsm_codex_entry e
LEFT JOIN main.region r ON r.region = e.region
LEFT JOIN main.system_known k ON k.system_id = e.systemId64;
