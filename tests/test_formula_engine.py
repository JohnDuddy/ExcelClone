from __future__ import annotations

import pytest

from duddysheet.core.depgraph import CellAddress
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.tokenizer import FormulaSyntaxError
from duddysheet.core.workbook import Workbook


@pytest.fixture
def engine() -> FormulaEngine:
    return FormulaEngine(Workbook())


def test_setting_formula_calculates_and_tracks_precedents(
    engine: FormulaEngine,
) -> None:
    engine.set_cell("Sheet1", 0, 0, 6)

    result = engine.set_cell("Sheet1", 0, 1, "=A1*2")

    formula = CellAddress("Sheet1", 0, 1)
    assert engine.workbook.active_sheet.get_cell(0, 1).display_value == 12
    assert engine.graph.precedents_of(formula) == frozenset(
        {CellAddress("Sheet1", 0, 0)}
    )
    assert result.recalculated == (formula,)
    assert result.circular == ()


def test_edit_recalculates_only_transitive_dependents(
    engine: FormulaEngine,
) -> None:
    engine.set_cell("Sheet1", 0, 0, 2)
    engine.set_cell("Sheet1", 0, 1, "=A1+1")
    engine.set_cell("Sheet1", 0, 2, "=B1*3")
    engine.set_cell("Sheet1", 0, 3, "=10+1")

    result = engine.set_cell("Sheet1", 0, 0, 5)

    assert result.recalculated == (
        CellAddress("Sheet1", 0, 1),
        CellAddress("Sheet1", 0, 2),
    )
    assert engine.workbook.active_sheet.get_cell(0, 1).display_value == 6
    assert engine.workbook.active_sheet.get_cell(0, 2).display_value == 18
    assert engine.workbook.active_sheet.get_cell(0, 3).display_value == 11


def test_range_precedents_recalculate_when_blank_member_is_edited(
    engine: FormulaEngine,
) -> None:
    engine.set_cell("Sheet1", 3, 0, "=A1+A2+A3")

    result = engine.set_cell("Sheet1", 1, 0, 9)

    assert CellAddress("Sheet1", 3, 0) in result.recalculated
    assert engine.workbook.active_sheet.get_cell(3, 0).display_value == 9


def test_cross_sheet_dependencies_recalculate(
    engine: FormulaEngine,
) -> None:
    engine.workbook.add_sheet("Data")
    engine.set_cell("Sheet1", 0, 0, "=Data!A1+1")

    engine.set_cell("Data", 0, 0, 8)

    assert engine.workbook.get_sheet("Sheet1").get_cell(0, 0).display_value == 9


def test_replacing_formula_removes_old_dependency_edges(
    engine: FormulaEngine,
) -> None:
    engine.set_cell("Sheet1", 0, 2, "=A1+B1")
    engine.set_cell("Sheet1", 0, 2, "=B1")

    result = engine.set_cell("Sheet1", 0, 0, 100)

    assert CellAddress("Sheet1", 0, 2) not in result.recalculated


def test_direct_cycle_marks_cells_and_reports_first_offender(
    engine: FormulaEngine,
) -> None:
    engine.set_cell("Sheet1", 0, 0, "=B1+1")

    result = engine.set_cell("Sheet1", 0, 1, "=A1+1")

    assert set(result.circular) == {
        CellAddress("Sheet1", 0, 0),
        CellAddress("Sheet1", 0, 1),
    }
    assert result.first_circular in result.circular
    assert engine.workbook.active_sheet.get_cell(0, 0).display_value == "#CIRC!"
    assert engine.workbook.active_sheet.get_cell(0, 1).display_value == "#CIRC!"


def test_range_self_reference_is_detected(
    engine: FormulaEngine,
) -> None:
    result = engine.set_cell("Sheet1", 0, 0, "=A1:A2")

    assert result.circular == (CellAddress("Sheet1", 0, 0),)
    assert engine.workbook.active_sheet.get_cell(0, 0).display_value == "#CIRC!"


def test_breaking_cycle_recalculates_formulas_normally(
    engine: FormulaEngine,
) -> None:
    engine.set_cell("Sheet1", 0, 0, "=B1+1")
    engine.set_cell("Sheet1", 0, 1, "=A1+1")

    result = engine.set_cell("Sheet1", 0, 1, 4)

    assert result.circular == ()
    assert engine.workbook.active_sheet.get_cell(0, 0).display_value == 5
    assert engine.workbook.active_sheet.get_cell(0, 1).display_value == 4


def test_invalid_formula_does_not_replace_existing_cell(
    engine: FormulaEngine,
) -> None:
    engine.set_cell("Sheet1", 0, 0, 7)

    with pytest.raises(FormulaSyntaxError):
        engine.set_cell("Sheet1", 0, 0, "=1+")

    assert engine.workbook.active_sheet.get_cell(0, 0).display_value == 7


def test_full_and_sheet_recalculation_have_explicit_scope(
    engine: FormulaEngine,
) -> None:
    engine.workbook.add_sheet("Data")
    engine.set_cell("Sheet1", 0, 0, "=1+1")
    engine.set_cell("Data", 0, 0, "=2+2")

    sheet_result = engine.recalculate(sheet_name="Data")
    full_result = engine.recalculate()

    assert sheet_result.recalculated == (CellAddress("Data", 0, 0),)
    assert set(full_result.recalculated) == {
        CellAddress("Sheet1", 0, 0),
        CellAddress("Data", 0, 0),
    }


def test_engine_indexes_formulas_already_present_in_workbook() -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, 3)
    workbook.active_sheet.set_cell(0, 1, "=A1*4")

    engine = FormulaEngine(workbook)
    engine.recalculate()

    assert workbook.active_sheet.get_cell(0, 1).display_value == 12


def test_formula_errors_are_cached_as_cell_error_state(
    engine: FormulaEngine,
) -> None:
    engine.set_cell("Sheet1", 0, 0, "=1/0")
    cell = engine.workbook.active_sheet.get_cell(0, 0)

    assert cell.error == "#DIV/0!"
    assert cell.cached_value is None
    assert cell.display_value == "#DIV/0!"
