"""Entry point: ``pythonw -m queryminder [--file PATH]``."""

from __future__ import annotations

import argparse
import ctypes
import sys
import tkinter as tk

from . import picker, settings as settings_mod
from .store import TodoFile
from .ui import App

MUTEX_NAME = "Local\\QueryminderSingleInstance"
ERROR_ALREADY_EXISTS = 183


def _single_instance() -> bool:
    """True if this is the only running instance (Windows named mutex)."""
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    except AttributeError:
        return True
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    globals()["_mutex_handle"] = handle  # keep it alive for the process lifetime
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def _dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="queryminder", description=__doc__)
    parser.add_argument("--file", help="path to the to-do Markdown file")
    parser.add_argument("--allow-multiple", action="store_true", help="skip the single-instance check")
    args = parser.parse_args(argv)

    if not args.allow_multiple and not _single_instance():
        return 0
    _dpi_aware()
    settings = settings_mod.load()
    path = settings_mod.resolve_todo_file(args.file, settings)
    root = tk.Tk()
    root.title("Queryminder")
    if path is None:  # first run: ask which file to use
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = picker.choose_file(root)
        if chosen is None:
            return 0
        path = str(chosen)
        settings["file"] = path
        settings_mod.save(settings)
        root.attributes("-topmost", False)
        root.deiconify()
    App(root, TodoFile(path), settings)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
