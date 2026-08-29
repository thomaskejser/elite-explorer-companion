"""Where the overlay's time goes. One module, so instrumentation is not scattered.

*** THIS EXISTS BECAUSE GUESSING WAS WRONG THREE TIMES. *** Chasing overlay lag by
reasoning about the code produced a confident diagnosis of WAL checkpointing that
measurement flatly disproved, and an "optimisation" of the POI lookup that made it
slower. The overlay is a Tk single-threaded event loop over a 60 GiB database: the only
way to know what is slow is to time it in flight, on the real journal, with the real
game running.

TWO LEVELS, BOTH CHEAP:

    span()    wraps one whole operation -- a tick, a repaint, a reveal. Prints a
              breakdown ONLY when the operation was slower than `slow_ms`, so a healthy
              app is silent and a hitch explains itself.
    phase()   names a piece inside a span. Nests; the breakdown shows every phase that
              ran, in the order they finished, with its own total.

*** THE SINGLE-THREADED POINT IS THE WHOLE REASON TO MEASURE TICKS AND NOT QUERIES. ***
Tk runs the timer callback, the key handling and every repaint on one thread. A 900 ms
query does not cost 900 ms of database time and nothing else -- it costs 900 ms during
which no arrow key is read, no window is redrawn and the HUD is frozen. A breakdown of
queries alone would miss that, which is why the outermost span is the TICK.

Overhead is a time.perf_counter() pair and a dict update per phase, so this can stay on
in normal use rather than being a debug build. It is: --slow-ms controls the threshold,
never whether the timing runs.
"""
import contextlib
import time


class Phases:
    """Accumulates named phase timings and reports slow spans."""

    def __init__(self, slow_ms=250, out=print):
        self.slow_ms = slow_ms
        self.out = out
        self._t = {}        # phase name -> seconds accumulated in the current span
        self._n = {}        # phase name -> how many times it ran
        self._order = []    # completion order, so the report reads chronologically
        self._depth = 0

    @contextlib.contextmanager
    def phase(self, name):
        """Time a named piece of work. Nests freely; costs a perf_counter pair."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dt = time.perf_counter() - t0
            if name not in self._t:
                self._order.append(name)
                self._t[name] = 0.0
                self._n[name] = 0
            self._t[name] += dt
            self._n[name] += 1

    @contextlib.contextmanager
    def span(self, label):
        """Time a whole operation and print the breakdown if it was slow.

        RE-ENTRANT AND ONLY THE OUTERMOST ONE REPORTS. A tick can contain a reveal which
        contains a repaint, and three overlapping breakdowns for one hitch would be
        worse than none.
        """
        if self._depth:
            yield self
            return
        self._depth = 1
        self._t.clear()
        self._n.clear()
        self._order.clear()
        t0 = time.perf_counter()
        try:
            yield self
        finally:
            self._depth = 0
            total = (time.perf_counter() - t0) * 1000.0
            if total >= self.slow_ms:
                self.out(self._report(label, total))

    def _report(self, label, total):
        """'SLOW tick 812 ms | refresh 780 (read 640, paint 55) ...' -- one line.

        One line and not a table: this goes to the same stdout as every other message
        the overlay prints, and a twelve-line dump per hitch would bury the CONFIRMED
        notices that are the reason anyone is watching it.
        """
        # Accounted time is the sum of the TOP-LEVEL phases only; nested ones would be
        # double counted. We do not track the tree, so instead we report every phase and
        # let the label ordering show the nesting -- plus an explicit unaccounted figure,
        # which is the number that says "the cost is somewhere you did not instrument".
        parts = []
        for name in self._order:
            ms = self._t[name] * 1000.0
            n = self._n[name]
            parts.append(f"{name} {ms:.0f}" + (f" x{n}" if n > 1 else ""))
        return f"SLOW {label} {total:.0f} ms | " + "  ".join(parts)


class NullPhases:
    """The same interface, doing nothing. Used when timing is switched off entirely."""

    @contextlib.contextmanager
    def phase(self, name):
        yield

    @contextlib.contextmanager
    def span(self, label):
        yield self
