"""Which application currently has the foreground. Windows-only; degrades to "yes".

The overlay should be on screen while you are flying and gone the moment you alt-tab to
a browser -- an always-on-top HUD over somebody else's window is just clutter, and this
one is 924 px wide.

Two windows count as "flying": Elite itself, and OUR OWN. Without the second, clicking
the overlay to drag it would take focus away from Elite and the overlay would vanish
under the cursor -- you could never move it. Ownership is decided by process id rather
than by title, so it holds no matter what Tk calls the window.

Elite is matched on its window TITLE. The process name differs between the Steam,
Epic and standalone builds ("EliteDangerous64.exe", launcher variants), whereas the
title has been "Elite - Dangerous (CLIENT)" throughout. Matching is case-insensitive
and on a prefix, so a version suffix cannot break it.

Everywhere that is not Windows, `is_foreground()` returns True: better a HUD that is
always visible than one that is never visible.
"""
import os
import sys

# Case-insensitive substring. "Elite - Dangerous (CLIENT)" is the real one; the bare
# form covers the launcher and any retitling.
ELITE_TITLE_MATCH = "elite - dangerous"

_user32 = None
_kernel32 = None


def _win32():
    """Load user32/kernel32 once. -> True on Windows with the DLLs available."""
    global _user32, _kernel32
    if _user32 is not None:
        return _user32 is not False
    if sys.platform != "win32":
        _user32 = _kernel32 = False
        return False
    try:
        import ctypes
        from ctypes import wintypes
        _user32 = ctypes.WinDLL("user32", use_last_error=True)
        _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _user32.GetForegroundWindow.restype = wintypes.HWND
        _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                     ctypes.POINTER(wintypes.DWORD)]
        return True
    except Exception:
        _user32 = _kernel32 = False
        return False


def foreground():
    """-> (title, pid) of the foreground window, or (None, None) if unavailable."""
    if not _win32():
        return None, None
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None, None
        buf = ctypes.create_unicode_buffer(512)
        _user32.GetWindowTextW(hwnd, buf, 512)
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return buf.value, int(pid.value)
    except Exception:
        return None, None


def is_foreground(title_match=ELITE_TITLE_MATCH):
    """True if Elite -- or this app -- currently has the foreground.

    True as well when the platform cannot tell us, so a non-Windows run or a blocked
    API leaves the overlay permanently visible rather than permanently hidden.
    """
    if not _win32():
        return True
    title, pid = foreground()
    if title is None:
        return True                      # could not tell -- do not hide
    if pid == os.getpid():
        return True                      # our own window: dragging must not hide it
    return title_match in title.lower()
