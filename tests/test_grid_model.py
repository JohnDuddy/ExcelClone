from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from excelclone.commands.base import CommandHistory
from excelclone.core.engine import FormulaEngine
from excelclone.core.refs import MAX_COLUMNS, MAX_ROWS
from excelclone.core.workbook import Workbook
from excelclone.ui.grid_model import GridModel


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_grid_model_advertises_excel_dimensions_without_allocating() -> None:
    application()
    engine = FormulaEngine(Workbook())
    model = GridModel(engine, CommandHistory())

    assert model.rowCount() == MAX_ROWS
    assert model.columnCount() == MAX_COLUMNS
    assert model.headerData(0, Qt.Orientation.Horizontal) == "A"
    assert model.headerData(MAX_COLUMNS - 1, Qt.Orientation.Horizontal) == "XFD"
    assert model.headerData(MAX_ROWS - 1, Qt.Orientation.Vertical) == str(MAX_ROWS)
    assert model.data(model.index(500_000, 10_000)) is None
    assert engine.workbook.active_sheet.populated_count == 0


def test_model_edits_flow_through_history_and_recalculate() -> None:
    application()
    engine = FormulaEngine(Workbook())
    history = CommandHistory()
    model = GridModel(engine, history)

    assert model.setData(model.index(0, 0), "5", Qt.ItemDataRole.EditRole)
    assert model.setData(model.index(0, 1), "=A1*2", Qt.ItemDataRole.EditRole)

    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "5"
    assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "10"
    assert model.data(model.index(0, 1), Qt.ItemDataRole.EditRole) == "=A1*2"

    history.undo()
    assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) is None


def test_spill_cells_are_selectable_but_not_editable() -> None:
    application()
    engine = FormulaEngine(Workbook())
    model = GridModel(engine, CommandHistory())
    model.setData(
        model.index(0, 0),
        "=TRANSPOSE({1;2})",
        Qt.ItemDataRole.EditRole,
    )

    spill_index = model.index(0, 1)

    assert model.data(spill_index, Qt.ItemDataRole.DisplayRole) == "2"
    assert model.flags(spill_index) & Qt.ItemFlag.ItemIsSelectable
    assert not model.flags(spill_index) & Qt.ItemFlag.ItemIsEditable
    assert not model.setData(spill_index, 9, Qt.ItemDataRole.EditRole)


def test_switching_active_sheet_resets_model_data() -> None:
    application()
    workbook = Workbook()
    workbook.add_sheet("Data").set_cell(0, 0, "other")
    engine = FormulaEngine(workbook)
    model = GridModel(engine, CommandHistory())

    model.set_active_sheet("Data")

    assert model.active_sheet_name == "Data"
    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "other"
