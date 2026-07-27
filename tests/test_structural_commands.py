from __future__ import annotations

from duddysheet.commands.base import CommandHistory
from duddysheet.commands.edits import (
    DeleteColumnsCommand,
    DeleteRowsCommand,
    InsertColumnsCommand,
    InsertRowsCommand,
)
from duddysheet.core.data_tools import DataValidation, apply_filter
from duddysheet.core.refs import parse_a1
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.workbook import Workbook


def structural_engine() -> FormulaEngine:
    workbook = Workbook()
    workbook.add_sheet("Summary")
    engine = FormulaEngine(workbook)
    engine.set_cell("Sheet1", 0, 0, 1)
    engine.set_cell("Sheet1", 1, 0, 2)
    engine.set_cell("Sheet1", 2, 1, "=SUM(A1:A2)")
    engine.set_cell("Summary", 0, 0, "=Sheet1!A2")
    return engine


def test_insert_rows_moves_cells_expands_ranges_and_updates_cross_sheet_refs() -> None:
    engine = structural_engine()
    history = CommandHistory()

    history.execute(InsertRowsCommand(engine, "Sheet1", 1, 1))

    sheet = engine.workbook.get_sheet("Sheet1")
    assert sheet.get_cell(2, 0).display_value == 2
    assert sheet.get_cell(3, 1).display_value == 3
    assert "A1:A3" in sheet.get_cell(3, 1).raw_input
    assert engine.workbook.get_sheet("Summary").get_cell(0, 0).display_value == 2
    assert "A3" in engine.workbook.get_sheet("Summary").get_cell(0, 0).raw_input


def test_delete_rows_invalidates_single_reference_and_is_fully_undoable() -> None:
    engine = structural_engine()
    history = CommandHistory()
    before = engine.workbook.copy()

    history.execute(DeleteRowsCommand(engine, "Sheet1", 1, 1))
    assert (
        engine.workbook.get_sheet("Summary").get_cell(0, 0).display_value
        == "#REF!"
    )

    history.undo()
    assert engine.workbook.sheet_names == before.sheet_names
    assert tuple(engine.workbook.get_sheet("Sheet1").iter_populated()) == tuple(
        before.get_sheet("Sheet1").iter_populated()
    )
    assert tuple(engine.workbook.get_sheet("Summary").iter_populated()) == tuple(
        before.get_sheet("Summary").iter_populated()
    )


def test_insert_and_delete_columns_move_formulas_and_values() -> None:
    engine = FormulaEngine(Workbook())
    engine.set_cell("Sheet1", 0, 0, 5)
    engine.set_cell("Sheet1", 0, 1, "=A1*2")
    history = CommandHistory()

    history.execute(InsertColumnsCommand(engine, "Sheet1", 0, 1))
    assert engine.workbook.active_sheet.get_cell(0, 1).display_value == 5
    assert engine.workbook.active_sheet.get_cell(0, 2).display_value == 10

    history.execute(DeleteColumnsCommand(engine, "Sheet1", 0, 1))
    assert engine.workbook.active_sheet.get_cell(0, 0).display_value == 5
    assert engine.workbook.active_sheet.get_cell(0, 1).display_value == 10


def test_structural_command_rejects_nonpositive_count() -> None:
    engine = FormulaEngine(Workbook())

    try:
        InsertRowsCommand(engine, "Sheet1", 0, 0).do()
    except ValueError as error:
        assert "positive" in str(error)
    else:
        raise AssertionError("Expected nonpositive row count to be rejected")


def test_structural_edits_translate_validation_and_filter_ranges() -> None:
    engine = FormulaEngine(Workbook())
    sheet = engine.workbook.active_sheet
    sheet.data_validations.append(
        DataValidation(parse_a1("A2:A4"), "decimal", "greater_than", (0,))
    )
    apply_filter(
        sheet,
        parse_a1("A1:B4"),
        column=1,
        allowed_values={"keep"},
    )

    InsertRowsCommand(engine, "Sheet1", 1, 1).do()

    assert sheet.data_validations[0].range.to_a1() == "A3:A5"
    assert sheet.auto_filter.range.to_a1() == "A1:B5"
