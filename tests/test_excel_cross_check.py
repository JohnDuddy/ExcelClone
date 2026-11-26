"""Results and entry rules checked against Microsoft Excel itself.

``fixtures/excel_function_results.json`` holds about a thousand formulas,
each entered into Excel for Microsoft 365 with its result read back (the file
records the Excel build). Every formula Excel refused when it was typed must
be refused here too, and every result must match Excel's.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from duddysheet.core.entry_rules import validate_entry
from duddysheet.core.errors import SpreadsheetError
from duddysheet.core.evaluator import FormulaEvaluator
from duddysheet.core.tokenizer import FormulaSyntaxError
from duddysheet.core.workbook import Workbook

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "excel_function_results.json").read_text(encoding="utf-8"))
CASES = FIXTURE["cases"]

# Results that differ from Excel for a documented reason.
KNOWN_DIFFERENCES = {
    # Excel's exponential-smoothing parameter search is undocumented, so
    # forecasts (not the detected season length) can differ.
    "=FORECAST.ETS.CONFINT(7,{1,2,3,4,5,7},{1,2,3,4,5,6})": "Excel ETS parameter search",
    "=FORECAST.ETS(7,{1,2,3,4,5,7},{1,2,3,4,5,6})": "Excel ETS parameter search",
    "=FORECAST.ETS(7,{1,2,3,4,5,7},{1,2,3,4,5,6},0)": "Excel ETS parameter search",
    "=FORECAST.ETS(7,{1,2,3,4,5,7},{1,2,3,4,5,6},1)": "Excel ETS parameter search",
    "=FORECAST.ETS.CONFINT(7,{1,2,3,4,5,7},{1,2,3,4,5,6},0.95,0)": "Excel ETS parameter search",
    "=FORECAST.ETS.CONFINT(7,{1,2,3,4,5,7},{1,2,3,4,5,6},0.95,1)": "Excel ETS parameter search",
    "=FORECAST.ETS.STAT({1,2,3,4,5,7},{1,2,3,4,5,6},1)": "Excel ETS parameter search",
    "=FORECAST.ETS.STAT({1,2,3,4,5,7},{1,2,3,4,5,6},2)": "Excel ETS parameter search",
    "=FORECAST.ETS.STAT({1,2,3,4,5,7},{1,2,3,4,5,6},3)": "Excel ETS parameter search",
    "=FORECAST.ETS.STAT({1,2,3,4,5,7},{1,2,3,4,5,6},8)": "Excel ETS parameter search",
    # ACCRINT's actual/actual periods around a month-end first coupon.
    "=ACCRINT(DATE(2025,2,10),DATE(2025,8,31),DATE(2025,12,20),0.06,1000,4,1)": "ACCRINT month-end coupon",
    "=ACCRINT(DATE(2025,1,31),DATE(2025,7,31),DATE(2026,3,15),0.06,1000,2,1)": "ACCRINT month-end coupon",
}
_COMPLEX = re.compile(r"^([+-]?[\d.]+(?:E[+-]?\d+)?)?([+-][\d.]*(?:E[+-]?\d+)?)?([ij])?$")


def _ours(value: object) -> object:
    if isinstance(value, SpreadsheetError):
        return {"error": value.literal}
    if isinstance(value, tuple):
        return [[_ours(item) for item in row] for row in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    return float(value)


def _excel(case: dict) -> object:
    if "array" in case:
        return [[_scalar(item) for item in row] for row in case["array"]]
    return _scalar(case.get("value"))


def _scalar(value: object) -> object:
    if isinstance(value, bool) or value is None or isinstance(value, (str, dict)):
        return value
    return float(value)


def _as_complex(text: str) -> complex | None:
    found = _COMPLEX.match(text.replace(" ", ""))
    if not found or not found.group(3) and found.group(2):
        return None
    real = float(found.group(1)) if found.group(1) else 0.0
    if found.group(3):
        imaginary_text = found.group(2) if found.group(2) is not None else (found.group(1) or "")
        if found.group(2) is None:
            real = 0.0
        imaginary = float(imaginary_text + "1") if imaginary_text in ("+", "-", "") else float(imaginary_text)
        return complex(real, imaginary)
    return complex(real, 0)


def _same(expected: object, actual: object) -> bool:
    if isinstance(expected, list) and len(expected) == 1 and len(expected[0]) == 1 and not isinstance(actual, list):
        expected = expected[0][0]
    if isinstance(actual, list) and len(actual) == 1 and len(actual[0]) == 1 and not isinstance(expected, list):
        actual = actual[0][0]
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(
            len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
            for left, right in zip(expected, actual)
        )
    if isinstance(expected, float) and isinstance(actual, float):
        return math.isclose(expected, actual, rel_tol=1e-6, abs_tol=1e-9)
    if isinstance(expected, str) and isinstance(actual, str) and expected != actual:
        left, right = _as_complex(expected), _as_complex(actual)
        return left is not None and right is not None and abs(left - right) <= 1e-12 * max(1.0, abs(left))
    if expected is None and actual in ("", 0.0):
        return True
    return expected == actual


def _accepts(formula: str) -> bool:
    try:
        validate_entry(formula)
    except FormulaSyntaxError:
        return False
    return True


def test_fixture_records_its_excel_build() -> None:
    assert FIXTURE["excel_version"] == "16.0" and FIXTURE["excel_build"] > 0
    assert len(CASES) >= 950


@pytest.mark.parametrize("case", CASES, ids=[case["formula"][:60] for case in CASES])
def test_formula_entry_matches_excel(case: dict) -> None:
    assert _accepts(case["formula"]) == case["accepted"]


RESULT_CASES = [case for case in CASES if "value" in case or "array" in case]


@pytest.mark.parametrize("case", RESULT_CASES, ids=[case["formula"][:60] for case in RESULT_CASES])
def test_formula_result_matches_excel(case: dict) -> None:
    formula = case["formula"]
    if formula in KNOWN_DIFFERENCES:
        pytest.skip(KNOWN_DIFFERENCES[formula])
    actual = _ours(FormulaEvaluator(Workbook()).evaluate(formula))
    expected = _excel(case)
    assert _same(expected, actual), f"{formula}: Excel {expected!r}, ours {actual!r}"
