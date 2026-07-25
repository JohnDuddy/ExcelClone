from __future__ import annotations

import pytest

from excelclone.core.depgraph import CellAddress
from excelclone.core.engine import FormulaEngine, SpillCellReadOnlyError
from excelclone.core.workbook import Workbook


def test_dynamic_array_spills_values_and_marks_children_read_only() -> None:
    engine = FormulaEngine(Workbook())

    engine.set_cell("Sheet1", 0, 0, "=TRANSPOSE({1,2;3,4})")

    sheet = engine.workbook.active_sheet
    assert sheet.get_cell(0, 0).display_value == 1
    assert sheet.get_cell(0, 1).display_value == 3
    assert sheet.get_cell(1, 0).display_value == 2
    assert sheet.get_cell(1, 1).display_value == 4
    assert sheet.get_cell(1, 1).spill_parent == (0, 0)
    assert sheet.get_cell(1, 1).is_spill

    with pytest.raises(SpillCellReadOnlyError, match="owned"):
        engine.set_cell("Sheet1", 1, 1, 99)


def test_blocked_spill_returns_error_and_recovers_when_blocker_clears() -> None:
    engine = FormulaEngine(Workbook())
    engine.set_cell("Sheet1", 0, 1, 99)

    blocked = engine.set_cell("Sheet1", 0, 0, "=TRANSPOSE({1;2})")

    sheet = engine.workbook.active_sheet
    assert blocked.recalculated == (CellAddress("Sheet1", 0, 0),)
    assert sheet.get_cell(0, 0).display_value == "#SPILL!"
    assert sheet.get_cell(0, 1).display_value == 99

    recovered = engine.set_cell("Sheet1", 0, 1, None)

    assert CellAddress("Sheet1", 0, 0) in recovered.recalculated
    assert sheet.get_cell(0, 0).display_value == 1
    assert sheet.get_cell(0, 1).display_value == 2
    assert sheet.get_cell(0, 1).is_spill


def test_replacing_spill_formula_clears_owned_children() -> None:
    engine = FormulaEngine(Workbook())
    engine.set_cell("Sheet1", 0, 0, "=UNIQUE({1;1;2})")

    engine.set_cell("Sheet1", 0, 0, "fixed")

    sheet = engine.workbook.active_sheet
    assert sheet.get_cell(0, 0).display_value == "fixed"
    assert sheet.get_cell(1, 0).is_empty


def test_xlookup_can_spill_a_return_row() -> None:
    engine = FormulaEngine(Workbook())

    engine.set_cell(
        "Sheet1",
        0,
        0,
        '=XLOOKUP("b",{"a";"b"},{1,2;3,4})',
    )

    sheet = engine.workbook.active_sheet
    assert sheet.get_cell(0, 0).display_value == 3
    assert sheet.get_cell(0, 1).display_value == 4


def test_volatile_function_recalculates_on_unrelated_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = iter((0.1, 0.8))
    monkeypatch.setattr(
        "excelclone.core.functions.math_fn.random.random",
        lambda: next(values),
    )
    engine = FormulaEngine(Workbook())

    engine.set_cell("Sheet1", 0, 0, "=RAND()")
    result = engine.set_cell("Sheet1", 5, 5, "unrelated")

    assert CellAddress("Sheet1", 0, 0) in result.recalculated
    assert engine.workbook.active_sheet.get_cell(0, 0).display_value == 0.8


def test_indirect_is_volatile_and_observes_new_reference_value() -> None:
    engine = FormulaEngine(Workbook())
    engine.set_cell("Sheet1", 0, 1, '=INDIRECT("A1")+1')

    engine.set_cell("Sheet1", 0, 0, 9)

    assert engine.workbook.active_sheet.get_cell(0, 1).display_value == 10
