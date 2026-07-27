from __future__ import annotations

from datetime import date

import pytest

from duddysheet.commands.base import CommandHistory
from duddysheet.commands.edits import FillRangeCommand, PasteCellsCommand
from duddysheet.core.cell import Cell, CellFormat
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.refs import parse_a1
from duddysheet.core.workbook import Workbook


def test_fill_range_extends_numeric_and_date_series_and_undoes() -> None:
    engine = FormulaEngine(Workbook())
    engine.set_cell("Sheet1", 0, 0, 1)
    engine.set_cell("Sheet1", 1, 0, 3)
    engine.set_cell("Sheet1", 0, 1, date(2026, 1, 1))
    engine.set_cell("Sheet1", 1, 1, date(2026, 1, 3))
    history = CommandHistory()

    history.execute(
        FillRangeCommand(
            engine,
            "Sheet1",
            parse_a1("A1:B2"),
            parse_a1("A1:B5"),
        )
    )

    sheet = engine.workbook.active_sheet
    assert [sheet.get_cell(row, 0).display_value for row in range(5)] == [
        1,
        3,
        5,
        7,
        9,
    ]
    assert sheet.get_cell(4, 1).display_value == date(2026, 1, 9)
    history.undo()
    assert engine.workbook.active_sheet.get_cell(4, 0).is_empty


def test_fill_range_cycles_weekday_month_names_and_translates_formulas() -> None:
    engine = FormulaEngine(Workbook())
    engine.set_cell("Sheet1", 0, 0, "Monday")
    engine.set_cell("Sheet1", 0, 1, "Jan")
    engine.set_cell("Sheet1", 0, 2, 2)
    engine.set_cell("Sheet1", 0, 3, "=C1*5")
    history = CommandHistory()

    history.execute(
        FillRangeCommand(engine, "Sheet1", parse_a1("A1:A1"), parse_a1("A1:A3"))
    )
    history.execute(
        FillRangeCommand(engine, "Sheet1", parse_a1("B1:B1"), parse_a1("B1:B4"))
    )
    history.execute(
        FillRangeCommand(engine, "Sheet1", parse_a1("D1:D1"), parse_a1("D1:D3"))
    )
    sheet = engine.workbook.active_sheet

    assert [sheet.get_cell(row, 0).display_value for row in range(3)] == [
        "Monday",
        "Tuesday",
        "Wednesday",
    ]
    assert [sheet.get_cell(row, 1).display_value for row in range(4)] == [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
    ]
    assert sheet.get_cell(2, 3).raw_input == "=C3*5"


def test_paste_cells_supports_all_values_formulas_formats_and_transpose() -> None:
    engine = FormulaEngine(Workbook())
    source = (
        (
            Cell(raw_input=2, cached_value=2, format=CellFormat(bold=True)),
            Cell(raw_input="=A1*3", cached_value=6, format=CellFormat(italic=True)),
        ),
    )
    history = CommandHistory()

    history.execute(PasteCellsCommand(engine, "Sheet1", 1, 1, source, (0, 0)))
    sheet = engine.workbook.active_sheet
    assert sheet.get_cell(1, 1).display_value == 2
    assert sheet.get_cell(1, 2).display_value == 6
    assert sheet.get_cell(1, 2).raw_input == "=B2*3"
    assert sheet.get_cell(1, 1).format.bold

    history.execute(
        PasteCellsCommand(
            engine,
            "Sheet1",
            3,
            0,
            source,
            (0, 0),
            mode="values",
            transpose=True,
        )
    )
    assert sheet.get_cell(3, 0).display_value == 2
    assert sheet.get_cell(4, 0).display_value == 6
    assert not sheet.get_cell(3, 0).format.bold

    sheet.set_cell(6, 0, "keep", cell_format=CellFormat(underline=True))
    history.execute(
        PasteCellsCommand(
            engine,
            "Sheet1",
            6,
            0,
            source,
            (0, 0),
            mode="formats",
        )
    )
    assert sheet.get_cell(6, 0).raw_input == "keep"
    assert sheet.get_cell(6, 0).format.bold


def test_paste_cells_undo_restores_exact_destination() -> None:
    engine = FormulaEngine(Workbook())
    engine.set_cell("Sheet1", 2, 2, "original")
    history = CommandHistory()
    history.execute(
        PasteCellsCommand(
            engine,
            "Sheet1",
            2,
            2,
            ((Cell(raw_input="new", cached_value="new"),),),
            (0, 0),
        )
    )

    history.undo()

    assert engine.workbook.active_sheet.get_cell(2, 2).raw_input == "original"


def test_horizontal_fill_extends_series_and_copies_unrecognized_text() -> None:
    engine = FormulaEngine(Workbook())
    engine.set_cell("Sheet1", 0, 0, 2)
    engine.set_cell("Sheet1", 0, 1, 4)
    engine.set_cell("Sheet1", 1, 0, "custom")
    history = CommandHistory()

    history.execute(
        FillRangeCommand(engine, "Sheet1", parse_a1("A1:B1"), parse_a1("A1:E1"))
    )
    history.execute(
        FillRangeCommand(engine, "Sheet1", parse_a1("A2:A2"), parse_a1("A2:C2"))
    )

    sheet = engine.workbook.active_sheet
    assert [sheet.get_cell(0, column).display_value for column in range(5)] == [
        2,
        4,
        6,
        8,
        10,
    ]
    assert [sheet.get_cell(1, column).display_value for column in range(3)] == [
        "custom",
        "custom",
        "custom",
    ]


def test_fill_rejects_target_that_extends_both_axes() -> None:
    engine = FormulaEngine(Workbook())
    engine.set_cell("Sheet1", 0, 0, 1)

    with pytest.raises(ValueError, match="one axis"):
        FillRangeCommand(
            engine,
            "Sheet1",
            parse_a1("A1:A1"),
            parse_a1("A1:B2"),
        ).do()
