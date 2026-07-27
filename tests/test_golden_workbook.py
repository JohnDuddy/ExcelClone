from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook

from duddysheet.core.evaluator import FormulaEvaluator
from duddysheet.core.workbook import Workbook

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "golden.xlsx"


def _golden_cases() -> list[tuple[str, object, object, str]]:
    formula_workbook = load_workbook(FIXTURE_PATH, data_only=False, read_only=True)
    cached_workbook = load_workbook(FIXTURE_PATH, data_only=True, read_only=True)
    formula_sheet = formula_workbook["Golden Cases"]
    cached_sheet = cached_workbook["Golden Cases"]
    cases = [
        (
            formula_row[0].value,
            formula_row[1].value,
            cached_row[0].value,
            formula_row[2].value,
        )
        for formula_row, cached_row in zip(
            formula_sheet.iter_rows(min_row=2),
            cached_sheet.iter_rows(min_row=2),
        )
    ]
    formula_workbook.close()
    cached_workbook.close()
    return cases


@pytest.mark.parametrize(
    ("formula", "expected", "excel_cached", "category"),
    _golden_cases(),
)
def test_evaluator_matches_excel_cached_golden_values(
    formula: str,
    expected: object,
    excel_cached: object,
    category: str,
) -> None:
    assert excel_cached == expected, f"Excel cache mismatch for {category}: {formula}"
    assert FormulaEvaluator(Workbook()).evaluate(formula) == pytest.approx(expected)
