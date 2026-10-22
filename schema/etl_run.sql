CREATE TABLE IF NOT EXISTS etl_run (
    run_id       VARCHAR     NOT NULL PRIMARY KEY,
    script       VARCHAR     NOT NULL,
    argv         VARCHAR     NOT NULL,
    started_utc  TIMESTAMPTZ NOT NULL,
    finished_utc TIMESTAMPTZ NOT NULL,
    seconds      DOUBLE      NOT NULL,
    status       VARCHAR     NOT NULL,
    error        VARCHAR
);

COMMENT ON TABLE etl_run IS
'RUN LOG, NOT MODEL DATA, in etl_log.duckdb beside the model -- never in elite_mapping.duckdb: one row per run of any script that calls common.runlog.start() -- every etl/ entry point and the scripts/ tools. Written by common/runlog.py when the process exits; when that file is locked the row waits in log/etl_run.pending.jsonl and is written by the next run that can. NEVER DELETED, and not reproducible from any source. Read by scripts/etl_report.py. Its steps are main.etl_run_step.';

COMMENT ON COLUMN etl_run.run_id IS 'A random UUID per run, the key etl_run_step points at.';
COMMENT ON COLUMN etl_run.script IS 'The script as <folder>-<file stem>, the same name as its log file in log/: etl-refresh_current, station-refresh, scripts-build_fresh_db.';
COMMENT ON COLUMN etl_run.argv IS 'The command-line arguments after the script path, space-joined; empty for none.';
COMMENT ON COLUMN etl_run.started_utc IS 'When common.runlog.start() ran, which is at the top of the script.';
COMMENT ON COLUMN etl_run.finished_utc IS 'When the process began to exit.';
COMMENT ON COLUMN etl_run.seconds IS 'finished_utc - started_utc in seconds, 3 dp: the wall-clock time of the run, downloads included.';
COMMENT ON COLUMN etl_run.status IS '''ok'' when the script printed its DONE_ line, ''interrupted'' on Ctrl+C, ''failed'' otherwise -- an exception or a SystemExit before the DONE_ line.';
COMMENT ON COLUMN etl_run.error IS 'For a failed or interrupted run, the exception or the last line the script wrote to stderr; NULL for ok.';
