import ctypes
import os
import pathlib
import uuid
from ctypes import wintypes

SAVED_GAMES = uuid.UUID("{4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}")
GAME_DIR = pathlib.Path("Frontier Developments") / "Elite Dangerous"


def known_folder(folder_id):
    guid = (ctypes.c_byte * 16).from_buffer_copy(folder_id.bytes_le)
    path = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32
    shell32.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE,
                                             ctypes.POINTER(ctypes.c_wchar_p)]
    if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path)):
        return None
    try:
        return pathlib.Path(path.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(path)


def journal_dir():
    given = os.environ.get("ELITE_JOURNAL_DIR")
    if given:
        return pathlib.Path(given)
    base = known_folder(SAVED_GAMES) if os.name == "nt" else None
    return (base or pathlib.Path.home() / "Saved Games") / GAME_DIR
