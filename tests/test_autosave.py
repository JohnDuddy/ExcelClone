from __future__ import annotations

import logging

from duddysheet.core.workbook import Workbook
from duddysheet.util.autosave import AutosaveManager
from duddysheet.util.logging_setup import configure_logging


def test_autosave_round_trip_candidates_and_discard(tmp_path) -> None:
    manager = AutosaveManager(tmp_path / "autosave")
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, "recover me")
    source = tmp_path / "book.dsheet"

    candidate = manager.save(workbook, source)
    candidates = manager.candidates()
    recovered = manager.recover(candidate)

    assert candidates == (candidate,)
    assert candidate.source_path == source
    assert recovered.active_sheet.get_cell(0, 0).raw_input == "recover me"

    manager.discard(candidate)
    assert manager.candidates() == ()
    assert not candidate.autosave_path.exists()


def test_autosave_clear_for_source_preserves_other_documents(tmp_path) -> None:
    manager = AutosaveManager(tmp_path / "autosave")
    workbook = Workbook()
    first = tmp_path / "first.dsheet"
    second = tmp_path / "second.dsheet"
    manager.save(workbook, first)
    manager.save(workbook, second)

    manager.clear_for_source(first)

    assert [item.source_path for item in manager.candidates()] == [second]


def test_logging_setup_writes_rotating_local_log(tmp_path) -> None:
    logger = configure_logging(tmp_path)
    logger.info("diagnostic message")
    for handler in logger.handlers:
        handler.flush()

    log_path = tmp_path / "opengrid.log"
    assert log_path.exists()
    assert "diagnostic message" in log_path.read_text(encoding="utf-8")
    assert any(
        isinstance(handler, logging.handlers.RotatingFileHandler)
        for handler in logger.handlers
    )
