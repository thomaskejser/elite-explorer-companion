SELECT count(*)
FROM (SELECT system_id FROM staging.sys_value USING SAMPLE 2000 ROWS) v
WHERE EXISTS (SELECT 1 FROM main.system_known k WHERE k.system_id = v.system_id);
