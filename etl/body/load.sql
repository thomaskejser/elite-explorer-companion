MERGE INTO main.body AS t
USING transform.body AS s ON t.type = s.type AND t.body = s.body
WHEN MATCHED AND (t.is_terraform_candidate IS DISTINCT FROM s.is_terraform_candidate
               OR t.code                   IS DISTINCT FROM s.code
               OR t.observed               IS DISTINCT FROM s.observed
               OR t.bodies                 IS DISTINCT FROM s.bodies
               OR t.cr_value               IS DISTINCT FROM s.cr_value
               OR t.cr_value_terraformable IS DISTINCT FROM s.cr_value_terraformable
               OR t.value_formula          IS DISTINCT FROM s.value_formula)
THEN UPDATE SET is_terraform_candidate = s.is_terraform_candidate,
                code                   = s.code,
                observed               = s.observed,
                bodies                 = s.bodies,
                cr_value               = s.cr_value,
                cr_value_terraformable = s.cr_value_terraformable,
                value_formula          = s.value_formula
WHEN NOT MATCHED THEN INSERT
    (body_id, type, body, is_terraform_candidate, code, observed, bodies,
     cr_value, cr_value_terraformable, value_formula)
VALUES
    (s.body_id, s.type, s.body, s.is_terraform_candidate, s.code, s.observed, s.bodies,
     s.cr_value, s.cr_value_terraformable, s.value_formula);
