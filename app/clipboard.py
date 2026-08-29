"""Putting a system name on the clipboard. The only thing this app sends outward.

THE CLIPBOARD IS THE USER'S. Nothing here runs on its own -- every call is the direct
result of a key the commander pressed. An overlay that quietly replaced your clipboard
because you jumped somewhere would be intolerable.

Win32 first, Tk second, and the order matters: Tk's clipboard is owned by the Tk
process and is EMPTIED WHEN THE APP EXITS. Copy a waypoint, close the overlay, paste
into the galaxy map, and you would get nothing. The Win32 clipboard outlives us, which
is the behaviour anyone actually expects.
"""
import sys

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _win32_copy(text):
    """-> True if the text reached the Windows clipboard."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        u32 = ctypes.WinDLL("user32", use_last_error=True)
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GlobalAlloc.restype = wintypes.HGLOBAL
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        u32.SetClipboardData.restype = wintypes.HANDLE
        u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]

        buf = ctypes.create_unicode_buffer(text)
        if not u32.OpenClipboard(None):
            return False
        try:
            u32.EmptyClipboard()
            handle = k32.GlobalAlloc(GMEM_MOVEABLE, ctypes.sizeof(buf))
            if not handle:
                return False
            ptr = k32.GlobalLock(handle)
            ctypes.memmove(ptr, buf, ctypes.sizeof(buf))
            k32.GlobalUnlock(handle)
            # On success the clipboard OWNS the block -- do not free it.
            return bool(u32.SetClipboardData(CF_UNICODETEXT, handle))
        finally:
            u32.CloseClipboard()
    except Exception:
        return False


def copy(text, tk_root=None):
    """Copy `text`. -> True if it landed anywhere.

    `tk_root` is the fallback path and must be the Tk root, called from the Tk thread.
    """
    if not text:
        return False
    if _win32_copy(text):
        return True
    if tk_root is not None:
        try:
            tk_root.clipboard_clear()
            tk_root.clipboard_append(text)
            tk_root.update()          # without this the clipboard is not published
            return True
        except Exception:
            return False
    return False
