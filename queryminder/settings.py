"""Small JSON settings file: %APPDATA%\\queryminder\\settings.json on Windows,
~/Library/Application Support/queryminder/settings.json on macOS."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def settings_path() -> Path:
    # APPDATA also wins on macOS, so tests can isolate settings the same way everywhere.
    base = os.environ.get("APPDATA")
    if not base:
        home = Path.home()
        base = str(home / "Library" / "Application Support") if sys.platform == "darwin" else str(home)
    return Path(base) / "queryminder" / "settings.json"


def load() -> dict:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data: dict) -> None:
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass  # settings are a convenience; never crash over them


def resolve_todo_file(cli_value: str | None, settings: dict) -> str | None:
    """CLI argument > QUERYMINDER_FILE env var > settings "file". None = not configured yet."""
    return cli_value or os.environ.get("QUERYMINDER_FILE") or settings.get("file") or None
