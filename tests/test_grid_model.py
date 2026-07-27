from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from duddysheet.commands.base import CommandHistory
from duddysheet.core.cell import CellFormat
from duddysheet.core.conditional import ConditionalRule, FormatPatch
from duddysheet.core.data_tools import DataValidation
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.refs import MAX_COLUMNS, MAX_ROWS, parse_a1
from duddysheet.core.workbook import Workbook
from duddysheet.ui.grid_model import DATA_BAR_ROLE, ICON_ROLE, GridModel


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


def test_grid_model_uses_number_format_and_conditional_effective_format() -> None:
    application()
    workbook = Workbook()
    workbook.active_sheet.set_cell(
        0,
        0,
        1234.5,
        cell_format=CellFormat(number_format="#,##0.00"),
    )
    workbook.active_sheet.conditional_formats.append(
        ConditionalRule(
            parse_a1("A1:A2"),
            "cell_value",
            "greater_than",
            (1000,),
            FormatPatch(font_color="#cc0000", bold=True),
        )
    )
    model = GridModel(FormulaEngine(workbook), CommandHistory())
    index = model.index(0, 0)

    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "1,234.50"
    assert model.data(index, Qt.ItemDataRole.ForegroundRole).color() == QColor("#cc0000")
    assert model.data(index, Qt.ItemDataRole.FontRole).bold()


def test_grid_model_exposes_conditional_visual_roles() -> None:
    application()
    workbook = Workbook()
    sheet = workbook.active_sheet
    sheet.set_cell(0, 0, 0)
    sheet.set_cell(1, 0, 10)
    sheet.conditional_formats.extend(
        [
            ConditionalRule(parse_a1("A1:A2"), "data_bar"),
            ConditionalRule(parse_a1("A1:A2"), "icon_set"),
        ]
    )
    model = GridModel(FormulaEngine(workbook), CommandHistory())

    assert model.data(model.index(1, 0), DATA_BAR_ROLE) == 1.0
    assert model.data(model.index(1, 0), ICON_ROLE) == "up"


def test_grid_model_formula_view_toggles_raw_formula_display() -> None:
    application()
    engine = FormulaEngine(Workbook())
    engine.set_cell("Sheet1", 0, 0, 3)
    engine.set_cell("Sheet1", 0, 1, "=A1+2")
    model = GridModel(engine, CommandHistory())

    model.set_formula_view(True)
    assert model.data(model.index(0, 1)) == "=A1+2"
    model.set_formula_view(False)
    assert model.data(model.index(0, 1)) == "5"


def test_grid_model_rejects_values_that_fail_cell_validation() -> None:
    application()
    engine = FormulaEngine(Workbook())
    engine.workbook.active_sheet.data_validations.append(
        DataValidation(
            parse_a1("A1"),
            "whole_number",
            "between",
            (1, 10),
            error_message="Enter a whole number from 1 through 10.",
        )
    )
    model = GridModel(engine, CommandHistory())

    assert not model.setData(model.index(0, 0), "20")
    assert model.last_error == "Enter a whole number from 1 through 10."
    assert model.sheet.get_cell(0, 0).is_empty
    assert model.setData(model.index(0, 0), "5")
