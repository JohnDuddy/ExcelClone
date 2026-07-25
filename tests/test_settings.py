from __future__ import annotations

import json

from excelclone.util.settings import SettingsStore


def test_settings_store_persists_ten_deduplicated_recent_files(tmp_path) -> None:
    path = tmp_path / "settings.json"
    settings = SettingsStore(path)
    for index in range(12):
        settings.add_recent_file(tmp_path / f"book-{index}.ogrid")
    settings.add_recent_file(tmp_path / "book-5.ogrid")

    restored = SettingsStore(path)

    assert len(restored.recent_files) == 10
    assert restored.recent_files[0].endswith("book-5.ogrid")
    assert len(set(restored.recent_files)) == 10
    assert json.loads(path.read_text(encoding="utf-8"))["recent_files"] == list(
        restored.recent_files
    )


def test_invalid_settings_json_falls_back_to_defaults(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")

    settings = SettingsStore(path)

    assert settings.recent_files == ()
