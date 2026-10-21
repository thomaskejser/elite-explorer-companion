import atexit
import datetime
import io
import pathlib
import sys

LOG = pathlib.Path(__file__).resolve().parent.parent / "log"
ROTATE_BYTES = 16 << 20


class _Tee(io.TextIOBase):
    def __init__(self, stream, sink):
        self.stream = stream
        self.sink = sink

    def write(self, text):
        self.sink.write(text)
        self.sink.flush()
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


def start(name=None):
    LOG.mkdir(parents=True, exist_ok=True)
    path = LOG / f"{name or log_name()}.log"
    _rotate(path)
    sink = open(path, "a", encoding="utf-8", errors="replace")
    sink.write(f"\n=== {_stamp()}  {' '.join(sys.argv)}\n")
    out, err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = _Tee(out, sink), _Tee(err, sink)

    def stop():
        sys.stdout, sys.stderr = out, err
        sink.write(f"=== ended {_stamp()}\n")
        sink.close()

    atexit.register(stop)
    return path


def _stamp():
    return f"{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M:%SZ}"
