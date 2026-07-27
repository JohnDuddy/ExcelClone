"""Windows-local application data and bundled-resource paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from duddysheet.branding import SLUG


def install_root() -> Path:
    """Return the directory that bundled read-only resources are rooted at.

    A PyInstaller build unpacks data files under ``sys._MEIPASS``; a source
    checkout serves them from the repository root.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled is not None:
        return Path(bundled)
    return Path(__file__).resolve().parent.parent.parent


def resource_path(relative: str) -> Path:
    """Return the absolute path of a bundled resource such as an icon."""
    return install_root().joinpath(*relative.split("/"))


def app_data_dir() -> Path:
    """Return the per-user writable Duddy Spreadsheet data directory."""
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return root / SLUG


def settings_path() -> Path:
    """Return the default persisted settings path."""
    return app_data_dir() / "settings.json"


def autosave_dir() -> Path:
    """Return the default crash-recovery autosave directory."""
    return app_data_dir() / "autosave"


def log_dir() -> Path:
    """Return the default application log directory."""
    return app_data_dir() / "logs"
