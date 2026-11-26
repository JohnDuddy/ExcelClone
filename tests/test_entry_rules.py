"""Formulas Excel refuses when typed are refused in the grid with Excel's message."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from duddysheet.core.engine import FormulaEngine
from duddysheet.core.entry_rules import PROBLEM, TOO_FEW, TOO_MANY, validate_entry
from duddysheet.core.tokenizer import FormulaSyntaxError
from duddysheet.core.workbook import Workbook
from duddysheet.ui.main_window import MainWindow


@pytest.mark.parametrize(
    ("formula", "message"),
    [
        ('=COUNTIF({1,2,3},">1")', PROBLEM),
        ('=SUMIF(A1:A3,">1",-B1:B3)', PROBLEM),
        ("={1+1}", PROBLEM),
        ("=LET(1,2,3)", PROBLEM),
        ("=ABS()", TOO_FEW),
        ("=ABS(1,2)", TOO_MANY),
        ("=IFS(TRUE,1,FALSE)", TOO_FEW),
    ],
)
def test_excel_entry_errors(formula: str, message: str) -> None:
    with pytest.raises(FormulaSyntaxError, match=message.replace("?", r"\?")):
        validate_entry(formula)


@pytest.mark.parametrize(
    "formula",
    [
        '=COUNTIF(A1:A3,">1")',
        '=SUMIF(A1:A3,">1",IF(TRUE,B1:B3))',
        '=COUNTIF((A1:A3),">1")',
        "={-1,\"a\",TRUE,#N/A}",
        "=LAMBDA(a,[b],a)(1)",
        "=AGGREGATE(14,6,{1,2,3},1)",
    ],
)
def test_formulas_excel_accepts_are_accepted(formula: str) -> None:
    validate_entry(formula)


def test_grid_refuses_a_formula_excel_refuses() -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow()
    model = window.grid_model
    assert not model.setData(model.index(0, 0), '=COUNTIF({1,2,3},">1")')
    assert model.last_error == PROBLEM
    assert model.sheet.get_cell(0, 0).raw_input in (None, "")
    assert not model.setData(model.index(0, 0), "=ABS()")
    assert model.last_error == TOO_FEW
    for row, value in enumerate(("1", "2", "3")):
        model.setData(model.index(row, 0), value)
    assert model.setData(model.index(0, 1), '=COUNTIF(A1:A3,">1")')
    assert model.sheet.get_cell(0, 1).display_value == 2
    window.close()


def test_formulas_already_in_a_workbook_still_calculate() -> None:
    # Workbooks written before the entry rules keep working when they load.
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, '=COUNTIF({1,2,3},">1")')
    FormulaEngine(workbook).recalculate()
    assert workbook.active_sheet.get_cell(0, 0).display_value == 2
