DELETE FROM main.system_exobio
WHERE NOT EXISTS (SELECT 1 FROM transform.system_exobio s
                  WHERE s.system_id = main.system_exobio.system_id);
