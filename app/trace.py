"""One-line records of the reveal path, for reproducing a bug rather than arguing about it.

    python -m app.main --trace

*** OFF UNLESS ASKED FOR, AND IT PRINTS RATHER THAN LOGGING ITSELF. *** Everything here
goes to stdout, which `common/runlog.py` already tees into `log/app-main.log`, so a
traced session leaves a file without a second logging mechanism to keep in step.

WHAT IT ANSWERS. A plot either moved the tables or it did not, and between those two
observations sit five steps that can each fail silently: the route file was read, the
hops carried classes, the write landed, the revealed names intersected
`system_predicted`, and the repaint used the result. One line per step, each naming the
numbers that decide the next one, so a log says WHICH step lost the plot.

Values are rendered `key=value` with no quoting beyond what a system name needs, because
these lines are read by a person looking for the one that disagrees with the screen.
"""
import datetime
import sys

_on = False


def enable(flag=True):
    global _on
    _on = bool(flag)


def enabled():
    return _on


def say(tag, **fields):
    """One record. Silent unless --trace."""
    if not _on:
        return
    stamp = f"{datetime.datetime.now(datetime.timezone.utc):%H:%M:%S}"
    body = "  ".join(f"{k}={_render(v)}" for k, v in fields.items())
    line = f"TRACE {stamp} {tag:<14} {body}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        # *** A DIAGNOSTIC MUST NOT BE ABLE TO KILL WHAT IT IS DIAGNOSING. *** main()
        # widens stdout to UTF-8, but that call can fail, and a sigma in a table's
        # sigma-count is enough to raise on a cp1252 console.
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(line.encode(enc, "replace").decode(enc), flush=True)


def rows(tag, rows, *keys):
    """One record per row, numbered. For dumping a table the way the screen has it."""
    if not _on:
        return
    say(tag, n=len(rows))
    for i, r in enumerate(rows):
        say(f"{tag}[{i}]", **{k: r.get(k) for k in keys})


def _render(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(str(x) for x in v[:4]) + ("...]" if len(v) > 4 else "]")
    text = str(v)
    return f"'{text}'" if " " in text else text
