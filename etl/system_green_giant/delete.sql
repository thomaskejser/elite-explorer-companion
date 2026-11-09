DELETE FROM main.system_green_giant
WHERE NOT EXISTS (SELECT 1 FROM transform.system_green_giant s
                  WHERE s.system_id = main.system_green_giant.system_id
                    AND s.body = main.system_green_giant.body);
