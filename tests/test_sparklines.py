from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QDialog

import duddysheet.ui.main_window as main_window_module
from duddysheet.commands.base import CommandHistory
from duddysheet.commands.edits import (
    AddSparklinesCommand,
    ClearSparklinesCommand,
    DeleteRowsCommand,
    InsertRowsCommand,
    RenameSheetCommand,
)
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.refs import parse_a1
from duddysheet.core.sparkline import (
    Sparkline,
    build_sparklines,
    sparkline_at,
    sparkline_values,
)
from duddysheet.core.workbook import Workbook
from duddysheet.io.native import load_native, save_native
from duddysheet.ui.delegates import paint_sparkline
from duddysheet.ui.dialogs.sparklines import SparklineDialog, default_location
from duddysheet.ui.grid_model import SPARKLINE_ROLE
from duddysheet.ui.main_window import MainWindow


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def monthly_workbook() -> Workbook:
    workbook = Workbook()
    rows = (
        ("Product", "Jan", "Feb", "Mar", "Apr"),
        ("Tea", 5, 7, 6, 9),
        ("Coffee", 8, -2, 4, "n/a"),
        ("Cocoa", 1, 2, 3, 4),
    )
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            workbook.active_sheet.set_cell(row, column, value)
    return workbook


def test_location_column_takes_one_data_row_per_cell() -> None:
    sparklines = build_sparklines(parse_a1("B2:E4"), parse_a1("F2:F4"), "line")

    assert [(item.row, item.column) for item in sparklines] == [
        (1, 5),
        (2, 5),
        (3, 5),
    ]
    assert sparklines[1].data_range.to_a1() == "B3:E3"


def test_location_row_takes_one_data_column_per_cell() -> None:
    sparklines = build_sparklines(parse_a1("B2:E4"), parse_a1("B5:E5"), "column")

    assert len(sparklines) == 4
    assert sparklines[0].data_range.to_a1() == "B2:B4"
    assert sparklines[3].column == 4


def test_mismatched_or_two_dimensional_ranges_are_rejected() -> None:
    with pytest.raises(ValueError, match="one row"):
        build_sparklines(parse_a1("B2:E4"), parse_a1("F2:F3"), "line")
    with pytest.raises(ValueError, match="single row or column"):
        build_sparklines(parse_a1("B2:E4"), parse_a1("F2"), "line")
    with pytest.raises(ValueError, match="Unsupported"):
        build_sparklines(parse_a1("B2:E2"), parse_a1("F2"), "area")


def test_sparkline_values_treat_text_as_blank() -> None:
    workbook = monthly_workbook()
    coffee = build_sparklines(parse_a1("B3:E3"), parse_a1("F3"), "win_loss")[0]

    values = sparkline_values(workbook, "Sheet1", coffee)

    assert values[:3] == (8.0, -2.0, 4.0)
    assert math.isnan(values[3])


def test_add_replaces_existing_and_clear_removes_with_undo() -> None:
    workbook = monthly_workbook()
    engine = FormulaEngine(workbook)
    history = CommandHistory()
    first = build_sparklines(parse_a1("B2:E4"), parse_a1("F2:F4"), "line")
    replacement = build_sparklines(parse_a1("B2:E2"), parse_a1("F2"), "column")

    history.execute(AddSparklinesCommand(engine, "Sheet1", first))
    history.execute(AddSparklinesCommand(engine, "Sheet1", replacement))
    sheet = workbook.active_sheet
    assert len(sheet.sparklines) == 3
    assert sparkline_at(sheet.sparklines, 1, 5).kind == "column"

    history.execute(ClearSparklinesCommand(engine, "Sheet1", parse_a1("F2:F3")))
    assert [(item.row, item.column) for item in sheet.sparklines] == [(3, 5)]

    history.undo()
    history.undo()
    restored = workbook.active_sheet.sparklines
    assert sparkline_at(restored, 1, 5).kind == "line"
    with pytest.raises(ValueError, match="no sparklines"):
        history.execute(ClearSparklinesCommand(engine, "Sheet1", parse_a1("A1")))


def test_structural_edits_move_and_remove_sparklines() -> None:
    workbook = monthly_workbook()
    engine = FormulaEngine(workbook)
    history = CommandHistory()
    history.execute(
        AddSparklinesCommand(
            engine,
            "Sheet1",
            build_sparklines(parse_a1("B2:E4"), parse_a1("F2:F4"), "line"),
        )
    )

    history.execute(InsertRowsCommand(engine, "Sheet1", 0, 1))
    moved = sparkline_at(workbook.active_sheet.sparklines, 2, 5)
    assert moved is not None
    assert (moved.data_range.min_row, moved.data_range.max_row) == (2, 2)

    history.execute(DeleteRowsCommand(engine, "Sheet1", 2, 1))
    assert sparkline_at(workbook.active_sheet.sparklines, 2, 5) is not None
    assert len(workbook.active_sheet.sparklines) == 2


def test_renaming_the_data_sheet_updates_sparkline_ranges() -> None:
    workbook = monthly_workbook()
    engine = FormulaEngine(workbook)
    history = CommandHistory()
    sparkline = Sparkline(1, 5, parse_a1("Sheet1!B2:E2"))
    history.execute(AddSparklinesCommand(engine, "Sheet1", (sparkline,)))

    history.execute(RenameSheetCommand(engine, "Sheet1", "Sales"))

    assert workbook.active_sheet.sparklines[0].data_range.sheet == "Sales"


def test_sparklines_round_trip_through_native_files(tmp_path) -> None:
    workbook = monthly_workbook()
    workbook.active_sheet.sparklines = list(
        build_sparklines(
            parse_a1("Sheet1!B2:E4"),
            parse_a1("F2:F4"),
            "win_loss",
            show_high=True,
            show_negative=True,
            color="#0b6e75",
        )
    )

    restored = load_native(save_native(workbook, tmp_path / "spark.dsheet"))

    assert restored.active_sheet.sparklines == workbook.active_sheet.sparklines


@pytest.mark.parametrize("kind", ("line", "column", "win_loss"))
def test_every_sparkline_kind_paints_inside_the_cell(kind: str) -> None:
    application()
    image = QImage(120, 24, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    sparkline = Sparkline(
        0,
        0,
        parse_a1("A1:E1"),
        kind,
        show_markers=True,
        show_high=True,
        show_low=True,
        show_first=True,
        show_last=True,
        show_negative=True,
        show_axis=True,
    )
    painter = QPainter(image)
    paint_sparkline(
        painter,
        QRectF(0, 0, 120, 24),
        sparkline,
        (3.0, -1.0, math.nan, 5.0, 2.0),
    )
    painter.end()

    colored = sum(
        1
        for x in range(120)
        for y in range(24)
        if image.pixelColor(x, y) != QColor("white")
    )
    assert colored > 20


def test_grid_model_serves_live_sparkline_values() -> None:
    application()
    workbook = monthly_workbook()
    window = MainWindow(workbook)
    window.history.execute(
        AddSparklinesCommand(
            window.engine,
            "Sheet1",
            build_sparklines(parse_a1("B2:E2"), parse_a1("F2"), "line"),
        )
    )

    sparkline, values = window.grid_model.index(1, 5).data(SPARKLINE_ROLE)
    window.grid_model.setData(window.grid_model.index(1, 1), "50")
    _, updated = window.grid_model.index(1, 5).data(SPARKLINE_ROLE)

    assert sparkline.kind == "line"
    assert values == (5.0, 7.0, 6.0, 9.0)
    assert updated[0] == 50.0
    assert window.grid_model.index(0, 0).data(SPARKLINE_ROLE) is None
    window.close()


def test_dialog_suggests_the_column_right_of_the_data() -> None:
    application()
    dialog = SparklineDialog(
        "Sheet1",
        "column",
        "B2:E4",
        default_location(parse_a1("B2:E4")).to_a1(),
    )
    dialog.show_high.setChecked(True)

    sparklines = dialog.sparklines()

    assert dialog.location_range.text() == "F2:F4"
    assert [item.kind for item in sparklines] == ["column"] * 3
    assert all(item.show_high for item in sparklines)
    assert not dialog.show_markers.isEnabled()
    dialog.close()


def test_insert_menu_sparklines_command_is_undoable(monkeypatch) -> None:
    application()
    workbook = monthly_workbook()
    window = MainWindow(workbook)

    class AcceptingDialog(SparklineDialog):
        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module, "SparklineDialog", AcceptingDialog)
    monkeypatch.setattr(window, "_selected_range", lambda: parse_a1("B2:E4"))

    window._ribbon_action("sparkline:win_loss")
    sheet = window.engine.workbook.active_sheet
    assert [(item.row, item.column, item.kind) for item in sheet.sparklines] == [
        (1, 5, "win_loss"),
        (2, 5, "win_loss"),
        (3, 5, "win_loss"),
    ]

    monkeypatch.setattr(window, "_selected_range", lambda: parse_a1("F2:F4"))
    window._ribbon_action("Clear Sparklines")
    assert sheet.sparklines == []
    window.history.undo()
    assert len(window.engine.workbook.active_sheet.sparklines) == 3
    window.close()
