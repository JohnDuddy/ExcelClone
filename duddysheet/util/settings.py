"""Small JSON settings store for recent files and UI preferences."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from duddysheet.util.paths import settings_path


class SettingsStore:
    """Persist application settings atomically in the user's local data."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else settings_path()
        self._data = self._load()

    @property
    def recent_files(self) -> tuple[str, ...]:
        """Return up to ten paths, most recently used first."""
        values = self._data.get("recent_files", [])
        if not isinstance(values, list):
            return ()
        return tuple(str(value) for value in values[:10])

    def add_recent_file(self, path: str | Path) -> None:
        """Move a path to the front of the persisted recent-file list."""
        selected = str(Path(path).resolve())
        values = [
            value
            for value in self.recent_files
            if value.casefold() != selected.casefold()
        ]
        self._data["recent_files"] = [selected, *values][:10]
        self.save()

    def get(self, key: str, default: Any = None) -> Any:
        """Read an arbitrary JSON-compatible setting."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Persist an arbitrary JSON-compatible setting."""
        self._data[key] = value
        self.save()

    def save(self) -> None:
        """Atomically write current settings."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}
