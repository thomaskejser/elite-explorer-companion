DELETE FROM main.system_predicted
WHERE NOT EXISTS (SELECT 1 FROM transform.system_predicted s
                  WHERE s.system = main.system_predicted.system);
