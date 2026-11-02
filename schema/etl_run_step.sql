CREATE TABLE IF NOT EXISTS etl_run_step (
    run_id      VARCHAR     NOT NULL,
    step_no     INTEGER     NOT NULL,
    kind        VARCHAR     NOT NULL,
    table_name  VARCHAR     NOT NULL,
    at_utc      TIMESTAMPTZ NOT NULL,
    rows_before BIGINT,
    rows_after  BIGINT,
    inserted    BIGINT,
    updated     BIGINT,
    orphaned    BIGINT,
    PRIMARY KEY (run_id, step_no)
);

COMMENT ON TABLE etl_run_step IS
'RUN LOG, NOT MODEL DATA, in etl_log.duckdb beside the model -- never in elite_mapping.duckdb: one row per stage or merge a run reported, in order. A merge is recorded by common.db.report_merge, a stage by common.db.record_ingest, so a merge a loader does without report_merge is not here. Written with its main.etl_run row at process exit. NEVER DELETED. Read by scripts/etl_report.py.';

COMMENT ON COLUMN etl_run_step.run_id IS 'main.etl_run.run_id of the run. Unenforced, like every reference in this database.';
COMMENT ON COLUMN etl_run_step.step_no IS 'Order within the run, from 1.';
COMMENT ON COLUMN etl_run_step.kind IS '''stage'': a staging table was filled (rows_after is its row count). ''merge'': a MERGE into a model or app-state table was reported.';
COMMENT ON COLUMN etl_run_step.table_name IS 'The staging table staged, or the table merged, as the script named it.';
COMMENT ON COLUMN etl_run_step.at_utc IS 'When the step was reported, which is when it finished.';
COMMENT ON COLUMN etl_run_step.rows_before IS 'Rows in the merged table before the merge; NULL for a stage.';
COMMENT ON COLUMN etl_run_step.rows_after IS 'Rows after the merge, or rows staged.';
COMMENT ON COLUMN etl_run_step.inserted IS 'Rows the merge inserted, from its counts.sql; NULL for a stage.';
COMMENT ON COLUMN etl_run_step.updated IS 'Rows the merge updated, from its counts.sql; NULL for a stage. A second run of a loader must record 0 here.';
COMMENT ON COLUMN etl_run_step.orphaned IS 'Rows in the table the source no longer produces, as report_merge listed them; NULL for a stage.';
