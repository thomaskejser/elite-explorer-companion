UPDATE main.system_seen SET is_known = NULL;
UPDATE main.system_seen AS t SET is_known = FALSE
FROM model.system_predicted AS p
WHERE p.system = t.system AND t.is_known IS NULL;
UPDATE main.system_seen AS t SET is_known = TRUE
WHERE t.is_known IS NULL
  AND EXISTS (SELECT 1 FROM model.system_known_probe b WHERE b.system = t.system);
UPDATE main.system_confirmed SET is_known = NULL;
UPDATE main.system_confirmed AS t SET is_known = FALSE
FROM model.system_predicted AS p
WHERE p.system = t.system AND t.is_known IS NULL;
UPDATE main.system_confirmed AS t SET is_known = TRUE
WHERE t.is_known IS NULL
  AND EXISTS (SELECT 1 FROM model.system_known_probe b WHERE b.system = t.system);
