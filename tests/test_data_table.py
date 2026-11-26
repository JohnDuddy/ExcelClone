"""What-If data tables: one- and two-variable TABLE(), recalculation, and files."""

from __future__ import annotations

import pytest

from duddysheet.commands.analysis import WorkbookMutationCommand, create_data_table, delete_data_table
from duddysheet.commands.base import CommandHistory
from duddysheet.core.data_table import DataTableSpec, data_table_at
from duddysheet.core.editing import blocked_by_report, clear_ranges
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.workbook import Workbook
from duddysheet.io.native import load_native, save_native
from duddysheet.io.xlsx_reader import read_xlsx
from duddysheet.io.xlsx_writer import write_xlsx

RATE, MONTHS, PRINCIPAL = ("Sheet1", 0, 1), ("Sheet1", 1, 1), ("Sheet1", 2, 1)


def _loan() -> tuple[Workbook, FormulaEngine]:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    engine.set_cell("Sheet1", 0, 1, 0.05)
    engine.set_cell("Sheet1", 1, 1, 360)
    engine.set_cell("Sheet1", 2, 1, 200000)
    engine.set_cell("Sheet1", 3, 1, "=PMT(B1/12,B2,-B3)")
    return workbook, engine


def _values(workbook: Workbook, rows: range, columns: range) -> list[list[float]]:
    sheet = workbook.get_sheet("Sheet1")
    return [[round(sheet.get_cell(row, column).display_value, 2) for column in columns] for row in rows]


def _two_variable(workbook: Workbook, engine: FormulaEngine) -> DataTableSpec:
    engine.set_cell("Sheet1", 5, 3, "=B4")
    for index, rate in enumerate((0.04, 0.05, 0.06)):
        engine.set_cell("Sheet1", 5, 4 + index, rate)
    for index, months in enumerate((180, 360)):
        engine.set_cell("Sheet1", 6 + index, 3, months)
    spec = DataTableSpec(5, 3, 7, 6, RATE, MONTHS)
    create_data_table(workbook, "Sheet1", spec)
    engine.rebuild_index()
    return spec


def test_two_variable_data_table_matches_pmt() -> None:
    workbook, engine = _loan()
    _two_variable(workbook, engine)
    sheet = workbook.get_sheet("Sheet1")
    assert sheet.get_cell(6, 4).raw_input == "=TABLE(B1,B2)"
    assert _values(workbook, range(6, 8), range(4, 7)) == [
        [1479.38, 1581.59, 1687.71],
        [954.83, 1073.64, 1199.10],
    ]
    # The real inputs are untouched.
    assert sheet.get_cell(0, 1).display_value == 0.05
    assert round(sheet.get_cell(3, 1).display_value, 2) == 1073.64


def test_data_table_updates_when_the_model_changes() -> None:
    workbook, engine = _loan()
    _two_variable(workbook, engine)
    engine.set_cell("Sheet1", 2, 1, 100000)
    assert _values(workbook, range(6, 7), range(4, 7)) == [[739.69, 790.79, 843.86]]
    engine.set_cell("Sheet1", 6, 3, 120)
    assert round(workbook.get_sheet("Sheet1").get_cell(6, 4).display_value, 2) == 1012.45


def test_one_variable_column_table_with_two_formulas() -> None:
    workbook, engine = _loan()
    engine.set_cell("Sheet1", 4, 1, "=B4*B2")
    engine.set_cell("Sheet1", 0, 4, "=B4")
    engine.set_cell("Sheet1", 0, 5, "=B5")
    for index, rate in enumerate((0.03, 0.06)):
        engine.set_cell("Sheet1", 1 + index, 3, rate)
    create_data_table(workbook, "Sheet1", DataTableSpec(0, 3, 2, 5, None, RATE))
    engine.rebuild_index()
    sheet = workbook.get_sheet("Sheet1")
    assert sheet.get_cell(1, 4).raw_input == "=TABLE(,B1)"
    assert _values(workbook, range(1, 3), range(4, 6)) == [[843.21, 303554.9], [1199.10, 431676.38]]


def test_one_variable_row_table() -> None:
    workbook, engine = _loan()
    engine.set_cell("Sheet1", 10, 0, "=B4")
    for index, months in enumerate((120, 240)):
        engine.set_cell("Sheet1", 9, 1 + index, months)
    create_data_table(workbook, "Sheet1", DataTableSpec(9, 0, 10, 2, MONTHS, None))
    engine.rebuild_index()
    assert _values(workbook, range(10, 11), range(1, 3)) == [[2121.31, 1319.91]]


def test_input_values_can_come_from_formulas_and_chained_models() -> None:
    workbook, engine = _loan()
    engine.set_cell("Sheet1", 4, 1, "=ROUND(B4,0)")
    engine.set_cell("Sheet1", 0, 6, "=B5")
    engine.set_cell("Sheet1", 1, 5, "=0.02+0.02")
    create_data_table(workbook, "Sheet1", DataTableSpec(0, 5, 1, 6, None, RATE))
    engine.rebuild_index()
    assert workbook.get_sheet("Sheet1").get_cell(1, 6).display_value == 955


def test_automatic_except_tables_defers_data_tables() -> None:
    workbook, engine = _loan()
    _two_variable(workbook, engine)
    workbook.calculation_mode = "automatic_except_tables"
    engine.set_cell("Sheet1", 2, 1, 100000)
    sheet = workbook.get_sheet("Sheet1")
    assert round(sheet.get_cell(3, 1).display_value, 2) == 536.82
    assert round(sheet.get_cell(6, 4).display_value, 2) == 1479.38
    engine.recalculate()
    assert round(sheet.get_cell(6, 4).display_value, 2) == 739.69


def test_data_table_validation_and_partial_edits() -> None:
    workbook, engine = _loan()
    with pytest.raises(ValueError):
        create_data_table(workbook, "Sheet1", DataTableSpec(5, 3, 5, 6, RATE, None))
    with pytest.raises(ValueError):
        create_data_table(workbook, "Sheet1", DataTableSpec(5, 3, 7, 6, None, None))
    spec = _two_variable(workbook, engine)
    sheet = workbook.get_sheet("Sheet1")
    assert data_table_at(sheet, 6, 4) == spec
    assert data_table_at(sheet, 5, 4) is None
    assert blocked_by_report(sheet, [(6, 4, 6, 4)]) == "Cannot change part of a data table."
    assert blocked_by_report(sheet, [(6, 4, 7, 6)]) is None
    clear_ranges(workbook, "Sheet1", [(6, 4, 7, 6)], kind="contents")
    assert sheet.data_tables == []


def test_create_and_delete_are_undoable() -> None:
    workbook, engine = _loan()
    history = CommandHistory()
    engine.set_cell("Sheet1", 5, 3, "=B4")
    engine.set_cell("Sheet1", 6, 2, 0.04)
    spec = DataTableSpec(5, 2, 6, 3, None, RATE)
    history.execute(WorkbookMutationCommand(engine, "Data Table", lambda: create_data_table(workbook, "Sheet1", spec)))
    assert round(workbook.get_sheet("Sheet1").get_cell(6, 3).display_value, 2) == 954.83
    history.execute(WorkbookMutationCommand(engine, "Delete", lambda: delete_data_table(workbook, "Sheet1", spec)))
    assert workbook.get_sheet("Sheet1").get_cell(6, 3).raw_input is None
    history.undo()
    assert round(workbook.get_sheet("Sheet1").get_cell(6, 3).display_value, 2) == 954.83
    history.undo()
    assert workbook.get_sheet("Sheet1").data_tables == []


def test_data_tables_round_trip_through_native_and_xlsx(tmp_path) -> None:
    import openpyxl

    workbook, engine = _loan()
    spec = _two_variable(workbook, engine)
    xlsx = write_xlsx(workbook, tmp_path / "d.xlsx")
    worksheet = openpyxl.load_workbook(xlsx).active
    formula = worksheet["E7"].value
    assert type(formula).__name__ == "DataTableFormula"
    assert (formula.ref, formula.r1, formula.r2) == ("E7:G8", "B1", "B2")
    for loaded in (load_native(save_native(workbook, tmp_path / "d.dsheet")), read_xlsx(xlsx).workbook):
        FormulaEngine(loaded)
        assert loaded.get_sheet("Sheet1").data_tables == [spec]
        assert _values(loaded, range(6, 8), range(4, 7)) == [[1479.38, 1581.59, 1687.71], [954.83, 1073.64, 1199.10]]


def test_inserting_rows_above_moves_the_data_table() -> None:
    from duddysheet.core.operations import edit_structure

    workbook, engine = _loan()
    _two_variable(workbook, engine)
    edit_structure(workbook, "Sheet1", axis="row", index=0, count=1, delete=False)
    engine.rebuild_index()
    sheet = workbook.get_sheet("Sheet1")
    assert sheet.data_tables == [DataTableSpec(6, 3, 8, 6, ("Sheet1", 1, 1), ("Sheet1", 2, 1))]
    assert sheet.get_cell(7, 4).raw_input == "=TABLE(B2,B3)"
    assert round(sheet.get_cell(7, 4).display_value, 2) == 1479.38
