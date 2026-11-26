"""Quick Analysis, Forecast Sheet, and threaded comments."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from duddysheet.core.comments import (
    CommentThread,
    add_reply,
    set_resolved,
    shift_comments,
    start_thread,
    thread_from_dict,
    thread_to_dict,
)
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.forecast import ForecastOptions, build_forecast_sheet
from duddysheet.core.refs import parse_a1
from duddysheet.core.workbook import Workbook
from duddysheet.io.native import load_native, save_native
from duddysheet.io.xlsx_reader import read_xlsx
from duddysheet.io.xlsx_writer import write_xlsx
from duddysheet.ui.main_window import MainWindow


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _window_with_table() -> MainWindow:
    application()
    window = MainWindow()
    model = window.grid_model
    for row, values in enumerate((("Q1", "Q2", "Q3"), (10, 20, 30), (5, 15, 25), (1, 2, 3))):
        for column, value in enumerate(values):
            model.setData(model.index(row, column), str(value))
    window.grid.select_block(0, 0, 3, 2)
    return window


def test_quick_analysis_menu_offers_excels_five_sections() -> None:
    window = _window_with_table()
    menu = window.quick_analysis_menu()
    assert [action.text() for action in menu.actions()] == ["Formatting", "Charts", "Totals", "Tables", "Sparklines"]
    charts = next(section for section in menu.sections if section.title() == "Charts")
    assert charts.actions(), "the selection should get chart recommendations"
    assert window.excel_actions["quickAnalysis"].shortcut().toString() == "Ctrl+Q"
    window.close()


def test_quick_totals_formatting_tables_and_sparklines() -> None:
    window = _window_with_table()
    sheet = window.grid_model.sheet
    assert window.quick_total("sum")
    assert [sheet.get_cell(4, column).display_value for column in range(3)] == [16, 37, 58]
    assert sheet.get_cell(4, 0).raw_input == "=SUM(A2:A4)"
    window.history.undo()
    window.grid.select_block(0, 0, 3, 2)
    assert window.quick_total("percent_total")
    assert window.grid_model.sheet.get_cell(4, 2).display_value == pytest.approx(58 / 111)
    window.history.undo()
    window.grid.select_block(1, 0, 3, 2)
    assert window.quick_total("running_total", "right")
    assert [window.grid_model.sheet.get_cell(row, 3).display_value for row in (1, 2, 3)] == [60, 105, 111]
    window.history.undo()
    window.grid.select_block(1, 0, 3, 2)
    assert window.quick_format("data_bar")
    assert window.grid_model.sheet.conditional_formats[-1].kind == "data_bar"
    assert window.quick_format("clear")
    assert window.grid_model.sheet.conditional_formats == []
    assert window.quick_sparklines("line")
    assert len(window.grid_model.sheet.sparklines) == 3
    window.grid.select_block(0, 0, 3, 2)
    assert window.quick_chart("column").chart_type == "column"
    assert window.quick_table()
    assert window.grid_model.sheet.tables
    window.close()


def _monthly() -> tuple[Workbook, FormulaEngine, str]:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    name = workbook.active_sheet.name
    engine.set_cell(name, 0, 0, "Month")
    engine.set_cell(name, 0, 1, "Sales")
    for index in range(12):
        engine.set_cell(name, index + 1, 0, index + 1)
        engine.set_cell(name, index + 1, 1, 100 + 10 * index + (5 if index % 3 == 0 else 0))
    return workbook, engine, name


def test_forecast_sheet_extends_the_series_with_bounds_and_a_chart() -> None:
    workbook, engine, name = _monthly()
    created, chart = build_forecast_sheet(workbook, engine, name, parse_a1("A1:A13"), parse_a1("B1:B13"), ForecastOptions(periods=4, confidence=0.9))
    sheet = workbook.get_sheet(created)
    assert [sheet.get_cell(0, column).display_value for column in range(5)] == [
        "Month", "Sales", "Forecast(Sales)", "Lower Confidence Bound(Sales)", "Upper Confidence Bound(Sales)",
    ]
    assert sheet.get_cell(12, 2).display_value == sheet.get_cell(12, 1).display_value
    for row in range(13, 17):
        assert sheet.get_cell(row, 0).display_value == row
        lower, forecast, upper = (sheet.get_cell(row, column).display_value for column in (3, 2, 4))
        assert lower < forecast < upper
        assert sheet.get_cell(row, 2).raw_input.startswith("=FORECAST.ETS(")
    assert chart.sheet_name == created and sheet.charts == [chart]
    with pytest.raises(ValueError, match="evenly spaced"):
        engine.set_cell(name, 5, 0, 99)
        build_forecast_sheet(workbook, engine, name, parse_a1("A1:A13"), parse_a1("B1:B13"), ForecastOptions())
    with pytest.raises(ValueError):
        ForecastOptions(confidence=1.5)


def test_window_forecast_sheet_command_is_undoable() -> None:
    application()
    window = MainWindow()
    model = window.grid_model
    for index in range(8):
        model.setData(model.index(index, 0), str(index + 1))
        model.setData(model.index(index, 1), str(50 + index * 3))
    window.grid.select_block(0, 0, 7, 1)
    created = window.create_forecast_sheet(ForecastOptions(periods=3))
    assert created in window.engine.workbook.sheet_names
    assert window.grid_model.active_sheet_name == created
    window.history.undo()
    assert created not in window.engine.workbook.sheet_names
    window.close()


def test_comment_threads_model_and_persistence(tmp_path) -> None:
    thread = add_reply(start_thread("Is this right?", "Ana", "2026-11-26T10:00:00.00"), "Yes & <fine>", "Ben", "2026-11-26T11:00:00.00")
    assert thread.author == "Ana" and len(thread.entries) == 2 and not thread.resolved
    resolved = set_resolved(thread, True)
    assert add_reply(resolved, "Reopening", "Ana").resolved is False
    assert thread_from_dict(thread_to_dict(resolved)) == resolved
    with pytest.raises(ValueError):
        start_thread("   ", "Ana")
    moved = shift_comments({(1, 1): thread, (5, 0): resolved}, "row", 2, 2, False)
    assert set(moved) == {(1, 1), (7, 0)}
    assert set(shift_comments({(1, 1): thread, (5, 0): resolved}, "row", 4, 2, True)) == {(1, 1)}
    workbook = Workbook()
    sheet = workbook.active_sheet
    sheet.comments = {(1, 1): thread, (3, 0): resolved}
    native = tmp_path / "comments.dsheet"
    save_native(workbook, native)
    assert load_native(native).active_sheet.comments == sheet.comments
    excel = tmp_path / "comments.xlsx"
    write_xlsx(workbook, excel)
    loaded = read_xlsx(excel)
    assert loaded.warnings == ()
    assert loaded.workbook.active_sheet.comments == sheet.comments
    assert loaded.workbook.active_sheet.notes == {}


def test_window_comments_pane_reply_resolve_and_delete() -> None:
    application()
    window = MainWindow()
    assert window.add_comment(2, 1, "Check this total", "Ana")
    assert window.reply_to_comment(2, 1, "Done", "Ben")
    thread = window.grid_model.sheet.comments[(2, 1)]
    assert isinstance(thread, CommentThread) and [entry.author for entry in thread.entries] == ["Ana", "Ben"]
    tooltip = window.grid_model.data(window.grid_model.index(2, 1), Qt.ItemDataRole.ToolTipRole)
    assert "Ana: Check this total" in tooltip and "Ben: Done" in tooltip
    window.show_comments_pane()
    pane = window.comments_dock.widget()
    assert pane.threads.count() == 1
    pane.threads.setCurrentRow(0)
    pane.toggle_resolved()
    assert window.grid_model.sheet.comments[(2, 1)].resolved
    pane.reply.setPlainText("One more thing")
    pane.post()
    assert len(window.grid_model.sheet.comments[(2, 1)].entries) == 3
    pane.threads.setCurrentRow(0)
    pane.delete()
    assert window.grid_model.sheet.comments == {}
    window.history.undo()
    assert (2, 1) in window.grid_model.sheet.comments
    assert window.excel_actions["newComment"].shortcut().toString() == "Ctrl+Alt+M"
    window.close()
