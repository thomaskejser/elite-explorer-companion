CREATE TABLE IF NOT EXISTS staging.body_curated (
    body_id                INTEGER,
    type                   VARCHAR,
    body                   VARCHAR,
    is_terraform_candidate BOOLEAN,
    code                   VARCHAR,
    cr_value               DOUBLE,
    cr_value_terraformable DOUBLE,
    value_formula          VARCHAR
);

COMMENT ON TABLE staging.body_curated IS
'RAW SOURCE (not a work table): input/body.parquet copied in whole by etl/body/stage.py. That file is AUTHORITATIVE and hand-edited, so this table is the curated body-type vocabulary exactly as a person last left it -- no feed writes it and nothing here is derived.

It carries the curated attributes only. The observed/bodies statistics that main.body also holds are NOT taken from the parquet: transform.body recounts them from staging.spansh_galaxy_body on every load, so a stale count in the file can never reach the model.

Seeded once from enum literals by etl/body/seed.py, which refuses to overwrite the parquet. There is no other way to recreate it; restore it from git.';

COMMENT ON COLUMN staging.body_curated.body_id IS
'The id the parquet proposes. Honoured for a NEW row only when no other body already holds it; an existing row keeps the id main.body gave it, whatever the file says, because a body_id is never renumbered.';

COMMENT ON COLUMN staging.body_curated.type IS
'''star'' or ''planet''. Half the natural key (type, body) the merge matches on.';

COMMENT ON COLUMN staging.body_curated.body IS
'The sub-type name exactly as the dumps spell it (''Neutron Star'', ''Earth-like world''). Half the natural key; a spelling change here is a NEW body type, not a rename.';

COMMENT ON COLUMN staging.body_curated.is_terraform_candidate IS
'Curated flag. Earth-like is deliberately FALSE -- see main.body.is_terraform_candidate before using it.';

COMMENT ON COLUMN staging.body_curated.code IS
'Short star code (''H'', ''WN'', ''AeBe'') used by the prediction model. NULL for planets.';

COMMENT ON COLUMN staging.body_curated.cr_value IS
'Scan-value constant k for this type, as curated. See main.body.cr_value for the formula it feeds.';

COMMENT ON COLUMN staging.body_curated.cr_value_terraformable IS
'Scan-value constant for the terraformable variant, planets only. NULL where the type is never terraformable.';

COMMENT ON COLUMN staging.body_curated.value_formula IS
'''star'' or ''planet'': which scan-value formula applies to this type.';
