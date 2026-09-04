"""The database on its own thread. A transport for `database.py`, nothing more.

*** WHY. *** Tk runs the timer, the keys and every repaint on one thread, so a query is
not just slow -- it is that long with no arrow key read and no window redrawn. A repaint
is ~100-145 ms of SQL against ~10 ms of drawing, so the freeze is almost entirely SQL,
and DuckDB releases the GIL: a slow query on this worker leaves the polling loop at its
2.1 ms idle gap, against 1,460 ms when it runs on the loop's own thread.

*** THIS MODULE KNOWS NOTHING ABOUT THE UI. *** Its vocabulary is `Database`'s public
method names and nothing else -- no repaint, no cursor, no table. Which datasets a view
needs stays in `main.py:_read_asks()`, because that is a UI decision: carriers are
skipped when only a reveal changed things, the sector reads are skipped in hand-named
space. If this cannot be driven from a plain script with no display, the boundary
leaked.

    Tk            ask([Ask("top_targets", (sector, 10), {"pos": pos}), ...])
    worker        runs them IN ONE SESSION, in order
    Tk            drain() -> (req_id, {name: result}) and paints

Two rules the FIFO enforces:

  ORDER. Writes are never reordered or dropped, so `record_seen` still lands before the
  reads that observe it. One worker, one queue; two workers would break this silently.
  LAST WINS, but only for UNSTARTED requests sharing a `key`. Jump twice quickly and the
  first request's answer describes the sector you left. Same decision `Hotkeys.take()`
  makes for keypresses.

A `Ref` in an ask's arguments is replaced by an earlier ask's result in the same request,
which is what lets a write and the read that depends on it share one session.
"""
import queue
import threading
from typing import NamedTuple


class Ask(NamedTuple):
    """One call on the Database. `name` is the method; that is the whole vocabulary."""
    name: str
    args: tuple = ()
    kwargs: dict = None


class Ref(NamedTuple):
    """Stands in for the result of an earlier Ask in the same request."""
    name: str


class Request(NamedTuple):
    req_id: int
    asks: tuple
    write: bool
    key: str            # None, or a coalescing group: last unstarted one wins


class DbWorker:
    """One thread, one Database, one FIFO in, one queue out."""

    def __init__(self, db, idle_seconds=30.0, on_error=None):
        self.db = db
        self.idle_seconds = idle_seconds
        self.on_error = on_error
        self._in = queue.Queue()
        self._out = queue.Queue()
        self._thread = None
        self._newest = {}          # key -> the highest req_id submitted under it
        self._lock = threading.Lock()

    # -- the Tk side ----------------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, name="db", daemon=True)
        self._thread.start()
        # The Database asserts it is only ever touched from ONE thread, and from here
        # that is this one. Set at construction to whoever built it, so a plain script
        # can drive a Database with no worker at all.
        self.db.claim_thread(self._thread.ident)

    def submit(self, req_id, asks, write=False, key=None):
        if key is not None:
            with self._lock:
                self._newest[key] = req_id
        self._in.put(Request(req_id, tuple(asks), write, key))

    def superseded(self, key, req_id):
        """-> True if a later request has been submitted under `key`."""
        with self._lock:
            return self._newest.get(key, req_id) != req_id

    def drain(self):
        """-> list of (req_id, results | Exception). Never blocks."""
        out = []
        while True:
            try:
                out.append(self._out.get_nowait())
            except queue.Empty:
                return out

    def stop(self):
        if self._thread is None:
            return
        self._in.put(None)
        self._thread.join(timeout=5)
        self._thread = None

    def busy(self):
        return not self._in.empty()

    # -- the worker side ------------------------------------------------------------
    def _run(self):
        while True:
            try:
                req = self._in.get(timeout=1.0)
            except queue.Empty:
                # ITS OWN HOUSEKEEPING, not a command. Handing the model back after a
                # quiet spell so etl/ can write it is a session-owning act, and only
                # this thread may perform one -- so it needs no vocabulary at all.
                self.db.release_if_idle(self.idle_seconds)
                continue
            if req is None:
                self.db.close()
                return
            if req.key is not None and self.superseded(req.key, req.req_id):
                continue           # its inputs are stale; nobody wants the answer
            try:
                with self.db.timing.span("db"):
                    result = self._serve(req)
                self._out.put((req.req_id, result))
            except Exception as e:                              # noqa: BLE001
                # A failure must arrive as a value. Vanishing into the thread would
                # leave the display frozen on stale rows with nothing said.
                self._out.put((req.req_id, e))
                if self.on_error:
                    self.on_error(e)

    def _serve(self, req):
        # A read request may not call a writing method -- see Database.WRITES.
        if not req.write:
            wrote = [a.name for a in req.asks if a.name in self.db.WRITES]
            assert not wrote, f"write method in a read request: {wrote}"
        results = {}
        for ask in req.asks:
            args = tuple(results[a.name] if isinstance(a, Ref) else a
                         for a in ask.args)
            kwargs = {k: results[v.name] if isinstance(v, Ref) else v
                      for k, v in (ask.kwargs or {}).items()}
            results[ask.name] = getattr(self.db, ask.name)(*args, **kwargs)
        return results
