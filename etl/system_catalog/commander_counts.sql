SELECT
  (SELECT count(*) FROM staging.commander_alias),
  (SELECT count(*) FROM staging.commander_alias a
   JOIN main.system_catalog t ON t.system = a.system
   WHERE t.system_id IS NULL AND a.system_id IS NOT NULL
     AND EXISTS (SELECT 1 FROM main.system_known k WHERE k.system_id = a.system_id)),
  (SELECT count(*) FROM staging.commander_alias a
   WHERE a.system_id IS NULL
      OR NOT EXISTS (SELECT 1 FROM main.system_known k WHERE k.system_id = a.system_id)
      OR NOT EXISTS (SELECT 1 FROM main.system_catalog t WHERE t.system = a.system));
