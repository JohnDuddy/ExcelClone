"""Crash-recovery snapshots stored in the user's local application data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from excelclone.core.workbook import Workbook
from excelclone.io.native import load_ogrid, save_ogrid
from excelclone.util.paths import autosave_dir


@dataclass(frozen=True)
class RecoveryCandidate:
    """One recoverable workbook snapshot and its source document."""

    autosave_path: Path
    metadata_path: Path
    source_path: Path | None
    saved_at: datetime


class AutosaveManager:
    """Create, enumerate, recover, and remove atomic workbook snapshots."""

    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = Path(directory) if directory is not None else autosave_dir()

    def save(
        self,
        workbook: Workbook,
        source_path: str | Path | None = None,
    ) -> RecoveryCandidate:
        """Replace the recovery snapshot for one source document."""
        source = (
            Path(source_path).resolve()
            if source_path is not None
            else None
        )
        key = self._document_key(source)
        self.directory.mkdir(parents=True, exist_ok=True)
        snapshot = self.directory / f"{key}.ogrid"
        metadata = self.directory / f"{key}.json"
        temporary_snapshot = snapshot.with_suffix(".ogrid.tmp")
        temporary_metadata = metadata.with_suffix(".json.tmp")
        saved_at = datetime.now(UTC)

        save_ogrid(workbook, temporary_snapshot)
        temporary_snapshot.replace(snapshot)
        temporary_metadata.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source_path": str(source) if source is not None else None,
                    "saved_at": saved_at.isoformat(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary_metadata.replace(metadata)
        return RecoveryCandidate(snapshot, metadata, source, saved_at)

    def candidates(self) -> tuple[RecoveryCandidate, ...]:
        """Return valid snapshots newest first, ignoring corrupt metadata."""
        if not self.directory.exists():
            return ()
        result: list[RecoveryCandidate] = []
        for metadata in self.directory.glob("*.json"):
            try:
                payload = json.loads(metadata.read_text(encoding="utf-8"))
                snapshot = metadata.with_suffix(".ogrid")
                saved_at = datetime.fromisoformat(payload["saved_at"])
                source_value = payload.get("source_path")
                source = Path(source_value) if source_value else None
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
            if snapshot.is_file():
                result.append(
                    RecoveryCandidate(snapshot, metadata, source, saved_at)
                )
        result.sort(key=lambda item: item.saved_at, reverse=True)
        return tuple(result)

    def recover(self, candidate: RecoveryCandidate) -> Workbook:
        """Load a candidate without deleting it."""
        return load_ogrid(candidate.autosave_path)

    def discard(self, candidate: RecoveryCandidate) -> None:
        """Remove one snapshot and its metadata."""
        candidate.autosave_path.unlink(missing_ok=True)
        candidate.metadata_path.unlink(missing_ok=True)

    def clear_for_source(self, source_path: str | Path | None) -> None:
        """Remove snapshots associated with a normally saved document."""
        source = (
            Path(source_path).resolve()
            if source_path is not None
            else None
        )
        for candidate in self.candidates():
            if candidate.source_path == source:
                self.discard(candidate)

    @staticmethod
    def _document_key(source_path: Path | None) -> str:
        value = str(source_path).casefold() if source_path is not None else "untitled"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
