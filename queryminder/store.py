"""File I/O for the to-do Markdown file: encoding-preserving reads, atomic
writes with retry (OneDrive/Obsidian may briefly lock the file), and a cheap
change signature used for polling."""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

Signature = tuple[int, int]  # (mtime_ns, size)


@dataclass(frozen=True)
class Snapshot:
    text: str  # normalized to "\n"
    signature: Signature | None


class TodoFile:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self._newline = "\n"
        self._bom = False

    def signature(self) -> Signature | None:
        try:
            st = self.path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def read(self) -> Snapshot:
        raw = self._retry(self.path.read_bytes)
        self._bom = raw.startswith(b"\xef\xbb\xbf")
        decoded = raw.decode("utf-8-sig")
        self._newline = "\r\n" if "\r\n" in decoded else "\n"
        return Snapshot(decoded.replace("\r\n", "\n"), self.signature())

    def write(self, text: str) -> Snapshot:
        data = text.replace("\n", self._newline).encode("utf-8")
        if self._bom:
            data = b"\xef\xbb\xbf" + data
        fd, tmp = tempfile.mkstemp(prefix=".queryminder-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            self._retry(lambda: os.replace(tmp, self.path))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return Snapshot(text, self.signature())

    def update(self, edit: Callable[[str], str]) -> Snapshot:
        """Read the *current* file, apply ``edit`` and write it back.

        Always re-reading right before writing means edits made in Obsidian
        (or anything else) since the last poll are never overwritten.
        """
        current = self.read()
        new_text = edit(current.text)
        if new_text == current.text:
            return current
        return self.write(new_text)

    @staticmethod
    def _retry(fn, attempts: int = 8, delay: float = 0.1):
        for i in range(attempts):
            try:
                return fn()
            except PermissionError:
                if i == attempts - 1:
                    raise
                time.sleep(delay * (i + 1))


# --------------------------------------------------------------------------- choosing a file

NEW, EMPTY, OK, INCOMPLETE = "new", "empty", "ok", "incomplete"


def inspect_file(path: str | os.PathLike[str]) -> str:
    """``new`` (doesn't exist), ``empty``, ``ok`` (has Today + Done) or ``incomplete``."""
    from . import model

    p = Path(path)
    if not p.exists():
        return NEW
    text = p.read_bytes().decode("utf-8-sig")
    if not text.strip():
        return EMPTY
    return OK if model.has_section(text, model.TODAY) and model.has_section(text, model.DONE) else INCOMPLETE


def initialise_file(path: str | os.PathLike[str]) -> None:
    """Create a new file (or fill an empty one) with the Today / Rest / Done sections."""
    from . import model

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    TodoFile(p).write(model.NEW_FILE_TEMPLATE)


def add_missing_sections(path: str | os.PathLike[str]) -> None:
    """Append the missing Today / Done sections to an existing file; nothing else changes."""
    from . import model

    TodoFile(path).update(model.ensure_sections)
