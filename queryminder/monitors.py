"""Monitor detection and window placement.

``fit()`` / ``is_reachable()`` are pure (unit tested). ``work_areas()`` asks
Windows for the current monitors via ctypes. All coordinates are physical
pixels in the virtual-screen space (the process is DPI aware, as is Tk), so
monitors left of / above the primary have negative coordinates.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

MARGIN = 40  # default distance from the work-area corner
GRIP_HEIGHT = 24  # top strip of the window that must stay grabbable
MIN_GRIP_VISIBLE = 40  # px of that strip that must be on a monitor


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def intersection_area(self, other: "Rect") -> int:
        w = min(self.right, other.right) - max(self.left, other.left)
        h = min(self.bottom, other.bottom) - max(self.top, other.top)
        return w * h if w > 0 and h > 0 else 0


@dataclass(frozen=True)
class Monitor:
    work: Rect  # work area (excludes the taskbar)
    primary: bool = False


def _primary(monitors: list[Monitor]) -> Monitor:
    return next((m for m in monitors if m.primary), monitors[0])


def default_position(width: int, monitors: list[Monitor]) -> tuple[int, int]:
    """Top-right corner of the primary monitor."""
    w = _primary(monitors).work
    return max(w.left, w.right - width - MARGIN), w.top + MARGIN


def is_reachable(x: int, y: int, width: int, monitors: list[Monitor]) -> bool:
    """True if enough of the window's top strip (where you drag it) is visible:
    at least MIN_GRIP_VISIBLE px wide and 10 px tall on a single monitor."""
    for m in monitors:
        w = min(x + width, m.work.right) - max(x, m.work.left)
        h = min(y + GRIP_HEIGHT, m.work.bottom) - max(y, m.work.top)
        if w >= MIN_GRIP_VISIBLE and h >= 10:
            return True
    return False


def fit(x: int | None, y: int | None, width: int, height: int, monitors: list[Monitor]) -> tuple[int, int]:
    """Where to put a ``width`` x ``height`` window that wants to be at (x, y).

    * No saved position, or it isn't on any current monitor (e.g. that monitor
      was unplugged) -> default position on the primary monitor.
    * Otherwise keep it on the monitor it overlaps most, nudged inside that
      monitor's work area so it is fully visible (handles resolution changes).
    """
    if not monitors:
        return (x or 0, y or 0)
    if x is None or y is None:
        return default_position(width, monitors)
    win = Rect(x, y, x + width, y + height)
    best = max(monitors, key=lambda m: win.intersection_area(m.work))
    if win.intersection_area(best.work) == 0 or not is_reachable(x, y, width, monitors):
        return default_position(width, monitors)
    w = best.work
    nx = max(w.left, min(x, w.right - width))
    ny = max(w.top, min(y, w.bottom - height))
    return nx, ny


# --------------------------------------------------------------------------- Windows


def work_areas() -> list[Monitor]:
    """Current monitors' work areas (empty list if unavailable)."""
    if sys.platform != "win32":
        return []
    from ctypes import wintypes

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    monitors: list[Monitor] = []
    MonitorEnumProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
    )

    def callback(hmon, _hdc, _rect, _data):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcWork
            monitors.append(Monitor(Rect(r.left, r.top, r.right, r.bottom), bool(info.dwFlags & 1)))
        return True

    try:
        user32.EnumDisplayMonitors(None, None, MonitorEnumProc(callback), 0)
    except OSError:
        return []
    return monitors
