SELECT
  (SELECT count(*) FROM transform.body s
   WHERE NOT EXISTS (SELECT 1 FROM main.body t WHERE t.type = s.type AND t.body = s.body)),
  (SELECT count(*) FROM main.body t JOIN transform.body s USING (type, body)
   WHERE t.is_terraform_candidate IS DISTINCT FROM s.is_terraform_candidate
      OR t.code                   IS DISTINCT FROM s.code
      OR t.observed               IS DISTINCT FROM s.observed
      OR t.bodies                 IS DISTINCT FROM s.bodies
      OR t.cr_value               IS DISTINCT FROM s.cr_value
      OR t.cr_value_terraformable IS DISTINCT FROM s.cr_value_terraformable
      OR t.value_formula          IS DISTINCT FROM s.value_formula);
