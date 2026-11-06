"""macOS calls Tk has no command for, made through the Objective-C runtime (ctypes only).

Every public function raises OSError / AttributeError / ValueError if the runtime isn't
usable; callers treat these features as optional. Call on the main thread, after Tk starts.
"""

from __future__ import annotations

import ctypes
import platform

_ACCESSORY_POLICY = 1  # NSApplicationActivationPolicyAccessory: no Dock icon, no menu bar
_CAN_JOIN_ALL_SPACES = 1 << 0
_IGNORES_CYCLE = 1 << 6  # stay out of Cmd-` window cycling, like the Windows card
_FULL_SCREEN_AUXILIARY = 1 << 8  # may share a Space with another app's full-screen window


class NSRect(ctypes.Structure):
    _fields_ = [(n, ctypes.c_double) for n in ("x", "y", "width", "height")]


def _objc() -> ctypes.CDLL:
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    ctypes.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")  # defines the classes used
    objc.objc_getClass.restype = objc.sel_registerName.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = objc.sel_registerName.argtypes = [ctypes.c_char_p]
    return objc


def _send(objc: ctypes.CDLL, obj, selector: bytes, restype=ctypes.c_void_p, argtypes=(), args=()):
    pointer = ctypes.c_void_p
    # Large structs come back through a different entry point on Intel.
    entry = "objc_msgSend_stret" if restype is NSRect and platform.machine() == "x86_64" else "objc_msgSend"
    fn = ctypes.CFUNCTYPE(restype, pointer, pointer, *argtypes)((entry, objc))
    return fn(obj, objc.sel_registerName(selector), *args)


def _items(objc: ctypes.CDLL, array) -> list:
    if not array:
        return []
    count = _send(objc, array, b"count", ctypes.c_ulong)
    return [_send(objc, array, b"objectAtIndex:", argtypes=(ctypes.c_ulong,), args=(i,)) for i in range(count)]


def _app(objc: ctypes.CDLL):
    return _send(objc, objc.objc_getClass(b"NSApplication"), b"sharedApplication")


def screen_frames() -> list[tuple[NSRect, NSRect]]:
    """(frame, visibleFrame) of each screen; the first is the primary one."""
    objc = _objc()
    screens = _send(objc, objc.objc_getClass(b"NSScreen"), b"screens")
    return [
        (_send(objc, s, b"frame", NSRect), _send(objc, s, b"visibleFrame", NSRect)) for s in _items(objc, screens)
    ]


def show_everywhere() -> None:
    """Drop the Dock icon and keep the app's visible windows on every Space, including over
    other apps' full-screen windows (macOS allows that only for accessory apps)."""
    objc = _objc()
    app = _app(objc)
    _send(objc, app, b"setActivationPolicy:", ctypes.c_bool, (ctypes.c_long,), (_ACCESSORY_POLICY,))
    behavior = _CAN_JOIN_ALL_SPACES | _IGNORES_CYCLE | _FULL_SCREEN_AUXILIARY
    for window in _items(objc, _send(objc, app, b"windows")):
        if _send(objc, window, b"isVisible", ctypes.c_bool):
            _send(objc, window, b"setCollectionBehavior:", None, (ctypes.c_ulong,), (behavior,))


def activate() -> None:
    """Bring the app forward: an accessory app's dialogs otherwise open behind other apps."""
    objc = _objc()
    _send(objc, _app(objc), b"activateIgnoringOtherApps:", None, (ctypes.c_bool,), (True,))
