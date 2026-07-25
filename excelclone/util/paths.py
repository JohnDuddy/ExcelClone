"""Windows-local application data paths."""

from __future__ import annotations

import os
from pathlib import Path


def app_data_dir() -> Path:
    """Return the per-user writable OpenGrid data directory."""
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return root / "ExcelClone"


def settings_path() -> Path:
    """Return the default persisted settings path."""
    return app_data_dir() / "settings.json"


def autosave_dir() -> Path:
    """Return the default crash-recovery autosave directory."""
    return app_data_dir() / "autosave"


def log_dir() -> Path:
    """Return the default application log directory."""
    return app_data_dir() / "logs"
