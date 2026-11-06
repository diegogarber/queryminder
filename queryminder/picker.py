"""Dialogs to choose (or create) the backing Markdown file."""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from . import compat, store


FILE_TYPES = [("Markdown", "*.md"), ("All files", "*.*")]


def _owner(parent: tk.Misc) -> dict:
    """Dialog options naming the parent. On macOS a parent turns a dialog into a sheet: stuck
    to that window, which here is hidden (first run) or a card much smaller than the dialog."""
    return {} if compat.IS_MAC else {"parent": parent}


def _ask_mac(title: str, where: dict) -> str:
    """macOS's save panel asks to replace an existing file, whatever confirmoverwrite says,
    so one panel can't do both jobs: open an existing file, and offer a new one on Cancel."""
    chosen = filedialog.askopenfilename(
        title=title, message=f"{title}. Cancel to create a new one instead.", filetypes=FILE_TYPES, **where
    )
    if chosen or not messagebox.askyesno("Queryminder", "Create a new to-do file?"):
        return chosen
    return filedialog.asksaveasfilename(
        title="New to-do file", defaultextension=".md", filetypes=FILE_TYPES, **where
    )


def choose_file(parent: tk.Misc, current: str | os.PathLike[str] | None = None, title: str = "Choose your to-do file") -> Path | None:
    """Ask for an existing ``.md`` file or a new name to create. Returns a ready-to-use
    path (sections created/added if needed) or None if the user cancelled."""
    initial = Path(current).parent if current else Path.home()
    owner = _owner(parent)
    while True:
        where = {
            "initialdir": str(initial) if initial.is_dir() else str(Path.home()),
            "initialfile": Path(current).name if current else "todos.md",
        }
        chosen = _ask_mac(title, where) if compat.IS_MAC else filedialog.asksaveasfilename(
            **owner,
            title=f"{title} — pick an existing .md file or type a new name",
            defaultextension=".md",
            filetypes=FILE_TYPES,
            confirmoverwrite=False,
            **where,
        )
        if not chosen:
            return None
        path = Path(chosen)
        if path.suffix.lower() != ".md":
            messagebox.showerror("Queryminder", "Please choose a Markdown (.md) file.", **owner)
            continue
        try:
            state = store.inspect_file(path)
            if state in (store.NEW, store.EMPTY):
                store.initialise_file(path)
            elif state == store.INCOMPLETE:
                if not messagebox.askyesno(
                    "Queryminder",
                    f"{path.name} has no '## Today' / '## Done' sections.\n\n"
                    "Add the missing sections at the end of the file? Nothing else in it will change.",
                    **owner,
                ):
                    continue
                store.add_missing_sections(path)
        except (OSError, UnicodeDecodeError) as e:
            messagebox.showerror("Queryminder", f"Can't use that file:\n{e}", **owner)
            continue
        return path
