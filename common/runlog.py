import atexit
import datetime
import io
import json
import os
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG = ROOT / "log"
SCHEMA = ROOT / "schema"
LOG_DB = pathlib.Path(os.environ.get("ETL_LOG_DB") or (ROOT / "etl_log.duckdb"))
ROTATE_BYTES = 16 << 20
PENDING = LOG / "etl_run.pending.jsonl"
DONE_MARK = "DONE_"
RUN_TABLES = ("etl_run", "etl_run_step")

_run = None


class _Tee(io.TextIOBase):
    def __init__(self, stream, sink, on_write=None):
        self.stream = stream
        self.sink = sink
        self.on_write = on_write

    def write(self, text):
        self.sink.write(text)
        self.sink.flush()
        if self.on_write:
            self.on_write(text)
        return self.stream.write(text)

    def flush(self):
        self.sink.flush()
        self.stream.flush()

    def isatty(self):
        return self.stream.isatty()

    def fileno(self):
        return self.stream.fileno()


def log_name(argv0=None):
    path = pathlib.Path(argv0 or sys.argv[0] or "python")
    stem = path.stem or "python"
    parent = path.resolve().parent
    return stem if parent == LOG.parent else f"{parent.name}-{stem}"


def _rotate(path):
    if path.exists() and path.stat().st_size >= ROTATE_BYTES:
        path.replace(path.with_suffix(".1.log"))


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def start(name=None):
    global _run
    LOG.mkdir(parents=True, exist_ok=True)
    script = name or log_name()
    path = LOG / f"{script}.log"
    _rotate(path)
    sink = open(path, "a", encoding="utf-8", errors="replace")
    sink.write(f"\n=== {_stamp()}  {' '.join(sys.argv)}\n")
    _run = {"run_id": str(uuid.uuid4()), "script": script, "argv": " ".join(sys.argv[1:]),
            "started_utc": _now(), "done": False, "error": None, "interrupted": False,
            "last_err": "", "err_last": False, "steps": []}
    out, err = sys.stdout, sys.stderr
    sys.stdout = _Tee(out, sink, _saw_out)
    sys.stderr = _Tee(err, sink, _saw_err)
    previous_hook = sys.excepthook

    def hook(kind, value, tb):
        _run["interrupted"] = issubclass(kind, KeyboardInterrupt)
        _run["error"] = f"{kind.__name__}: {value}"
        previous_hook(kind, value, tb)

    sys.excepthook = hook

    def stop():
        sys.stdout, sys.stderr = out, err
        sink.write(f"=== ended {_stamp()}\n")
        sink.close()

    atexit.register(stop)
    atexit.register(_record)
    return path


def _saw_out(text):
    if DONE_MARK in text:
        _run["done"] = True
    if text.strip():
        _run["err_last"] = False


def _saw_err(text):
    line = text.strip()
    if line:
        _run["last_err"] = line.splitlines()[-1]
        _run["err_last"] = True


def note_step(kind, table, rows_before=None, rows_after=None, inserted=None, updated=None, orphaned=None):
    if _run is None:
        return
    _run["steps"].append({"kind": kind, "table_name": str(table), "at_utc": _now(),
                          "rows_before": rows_before, "rows_after": rows_after,
                          "inserted": inserted, "updated": updated, "orphaned": orphaned})


def _row():
    finished = _now()
    if _run["done"]:
        status, error = "ok", None
    elif _run["interrupted"]:
        status, error = "interrupted", _run["error"]
    elif _run["error"]:
        status, error = "failed", _run["error"]
    elif _run["err_last"]:
        status, error = "failed", _run["last_err"]
    else:
        status, error = "ok", None
    return {"run_id": _run["run_id"], "script": _run["script"], "argv": _run["argv"],
            "started_utc": _run["started_utc"].isoformat(), "finished_utc": finished.isoformat(),
            "seconds": round((finished - _run["started_utc"]).total_seconds(), 3),
            "status": status, "error": error,
            "steps": [{**s, "at_utc": s["at_utc"].isoformat()} for s in _run["steps"]]}


def _pending():
    if not PENDING.exists():
        return []
    return [json.loads(line) for line in PENDING.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write(con, runs):
    for table in RUN_TABLES:
        con.execute((SCHEMA / f"{table}.sql").read_text(encoding="utf-8"))
    for r in runs:
        con.execute("""INSERT INTO main.etl_run BY NAME
                       SELECT ?::VARCHAR AS run_id, ?::VARCHAR AS script, ?::VARCHAR AS argv,
                              ?::TIMESTAMPTZ AS started_utc, ?::TIMESTAMPTZ AS finished_utc,
                              ?::DOUBLE AS seconds, ?::VARCHAR AS status, ?::VARCHAR AS error
                       WHERE NOT EXISTS (SELECT 1 FROM main.etl_run WHERE run_id = ?)""",
                    [r["run_id"], r["script"], r["argv"], r["started_utc"], r["finished_utc"],
                     r["seconds"], r["status"], r["error"], r["run_id"]])
        for i, s in enumerate(r["steps"], 1):
            con.execute("""INSERT INTO main.etl_run_step BY NAME
                           SELECT ?::VARCHAR AS run_id, ?::INTEGER AS step_no, ?::VARCHAR AS kind,
                                  ?::VARCHAR AS table_name, ?::TIMESTAMPTZ AS at_utc,
                                  ?::BIGINT AS rows_before, ?::BIGINT AS rows_after,
                                  ?::BIGINT AS inserted, ?::BIGINT AS updated, ?::BIGINT AS orphaned
                           WHERE NOT EXISTS (SELECT 1 FROM main.etl_run_step
                                             WHERE run_id = ? AND step_no = ?)""",
                        [r["run_id"], i, s["kind"], s["table_name"], s["at_utc"], s["rows_before"],
                         s["rows_after"], s["inserted"], s["updated"], s["orphaned"], r["run_id"], i])


def _record():
    if _run is None:
        return
    row = _row()
    runs = _pending() + [row]
    try:
        import duckdb
        con = duckdb.connect(str(LOG_DB))
        con.execute("SET TimeZone='UTC'")
        try:
            con.execute("BEGIN TRANSACTION")
            _write(con, runs)
            con.execute("COMMIT")
        finally:
            con.close()
    except Exception as exc:
        with open(PENDING, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        print(f"run log: {LOG_DB.name} could not take this run's record ({exc}); "
              f"kept in {PENDING} for the next run", file=sys.stderr)
        return
    if PENDING.exists():
        PENDING.unlink()
    print(f"run log: {row['script']} {row['status']} in {row['seconds']:,.1f} s, "
          f"{len(row['steps'])} step(s) recorded in {LOG_DB.name}")


def _stamp():
    return f"{_now():%Y-%m-%d %H:%M:%SZ}"
