"""Dialogs to choose (or create) the backing Markdown file."""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from . import store


def choose_file(parent: tk.Misc, current: str | os.PathLike[str] | None = None, title: str = "Choose your to-do file") -> Path | None:
    """Ask for an existing ``.md`` file or a new name to create. Returns a ready-to-use
    path (sections created/added if needed) or None if the user cancelled."""
    initial = Path(current).parent if current else Path.home()
    while True:
        chosen = filedialog.asksaveasfilename(
            parent=parent,
            title=f"{title} — pick an existing .md file or type a new name",
            initialdir=str(initial) if initial.is_dir() else str(Path.home()),
            initialfile=Path(current).name if current else "todos.md",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
            confirmoverwrite=False,
        )
        if not chosen:
            return None
        path = Path(chosen)
        if path.suffix.lower() != ".md":
            messagebox.showerror("Queryminder", "Please choose a Markdown (.md) file.", parent=parent)
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
                    parent=parent,
                ):
                    continue
                store.add_missing_sections(path)
        except (OSError, UnicodeDecodeError) as e:
            messagebox.showerror("Queryminder", f"Can't use that file:\n{e}", parent=parent)
            continue
        return path
