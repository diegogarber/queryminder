"""Windows / macOS differences that don't belong to a specific module. No Tk import."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from typing import IO

from . import settings

IS_MAC = sys.platform == "darwin"

# Root background: see-through everywhere it shows. Windows keys out a colour
# (-transparentcolor, so skins must not use it); Aqua has a real transparent colour.
TRANSPARENT = "systemTransparent" if IS_MAC else "#ff00fe"

# What opens the context menu. Aqua's right button is 2 in Tk 8.6, not 3 as elsewhere:
# bind both so no Tk version misses it. Control-click is the Mac convention.
MENU_EVENTS = ("<Button-2>", "<Button-3>", "<Control-Button-1>") if IS_MAC else ("<Button-3>",)

MUTEX_NAME = "Local\\QueryminderSingleInstance"
ERROR_ALREADY_EXISTS = 183

_instance_lock: IO[str] | None = None  # kept open for the process lifetime


def single_instance() -> bool:
    """True if this is the only running instance: a named mutex on Windows, an
    flock elsewhere (the OS drops it when the process dies, however it dies)."""
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        globals()["_mutex_handle"] = handle  # keep it alive for the process lifetime
        return kernel32.GetLastError() != ERROR_ALREADY_EXISTS

    import fcntl

    global _instance_lock
    path = settings.settings_path().with_name("instance.lock")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = open(path, "a", encoding="utf-8")
    except OSError:
        return True  # can't tell: better a second card than no card
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return False
    except OSError:
        lock.close()
        return True
    _instance_lock = lock
    return True


def open_path(path: str | os.PathLike[str]) -> None:
    """Open a file in its default app. Raises OSError / subprocess.SubprocessError."""
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.run(["open" if IS_MAC else "xdg-open", str(path)], check=True, capture_output=True)


def wheel_units(delta: int) -> int:
    """<MouseWheel> delta -> canvas scroll units. Windows and Tk 9 report multiples of
    120 per notch; Aqua on Tk 8.6 reports a small line count (a trackpad's flicks too)."""
    if abs(delta) >= 120:
        return int(-delta / 120) * 3
    return -delta
