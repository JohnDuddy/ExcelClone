from __future__ import annotations

import pytest

from excelclone.core.engine import FormulaEngine
from excelclone.core.financial_analysis import (
    Scenario,
    audit_financial_model,
    evaluate_scenarios,
    goal_seek,
    one_variable_sensitivity,
    two_variable_sensitivity,
)
from excelclone.core.workbook import Workbook


def model_workbook() -> Workbook:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    engine.set_cell("Sheet1", 0, 0, 2)
    engine.set_cell("Sheet1", 0, 1, 3)
    engine.set_cell("Sheet1", 0, 2, "=A1*A1+B1")
    return workbook


def test_goal_seek_solves_on_clone_without_mutating_source_workbook() -> None:
    workbook = model_workbook()

    result = goal_seek(workbook, "C1", "A1", 28)

    assert result.converged
    assert result.input_value == pytest.approx(5, abs=1e-7)
    assert result.result_value == pytest.approx(28, abs=1e-7)
    assert workbook.active_sheet.get_cell(0, 0).raw_input == 2
    assert workbook.active_sheet.get_cell(0, 2).display_value == 7


def test_goal_seek_supports_bracketed_bisection_and_validates_target() -> None:
    workbook = model_workbook()

    result = goal_seek(
        workbook,
        "C1",
        "A1",
        12,
        minimum=0,
        maximum=4,
    )

    assert result.converged
    assert result.input_value == pytest.approx(3, abs=1e-6)
    with pytest.raises(ValueError, match="formula cell"):
        goal_seek(workbook, "A1", "B1", 1)


def test_one_and_two_variable_sensitivity_tables_have_stable_axes() -> None:
    workbook = model_workbook()

    one = one_variable_sensitivity(workbook, "C1", "A1", (1, 2, 3))
    two = two_variable_sensitivity(
        workbook,
        "C1",
        "A1",
        (1, 2),
        "B1",
        (10, 20),
    )

    assert one.row_values == (1, 2, 3)
    assert one.values == ((4, 7, 12),)
    assert two.row_values == (1, 2)
    assert two.column_values == (10, 20)
    assert two.values == ((11, 14), (21, 24))
    assert workbook.active_sheet.get_cell(0, 0).raw_input == 2
    assert workbook.active_sheet.get_cell(0, 1).raw_input == 3


def test_scenario_evaluation_returns_named_outputs_without_mutation() -> None:
    workbook = model_workbook()
    scenarios = (
        Scenario("Base", (("A1", 2), ("B1", 3))),
        Scenario("Upside", (("A1", 4), ("B1", 5))),
    )

    results = evaluate_scenarios(workbook, scenarios, ("C1",))

    assert results[0].name == "Base"
    assert results[0].values == (("C1", 7),)
    assert results[1].values == (("C1", 21),)
    assert workbook.active_sheet.get_cell(0, 0).raw_input == 2


def test_model_audit_prioritizes_errors_blank_precedents_and_constants() -> None:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    engine.set_cell("Sheet1", 0, 0, 10)
    engine.set_cell("Sheet1", 0, 2, "=A1+B1+2")
    engine.set_cell("Sheet1", 1, 2, "=1/0")

    report = audit_financial_model(workbook)
    codes = [issue.code for issue in report.issues]

    assert report.formula_count == 2
    assert report.input_count == 1
    assert report.error_count == 1
    assert codes[0] == "FORMULA_ERROR"
    assert "BLANK_PRECEDENT" in codes
    assert "EMBEDDED_CONSTANT" in codes


def test_goal_seek_validates_domains_and_exact_initial_solution() -> None:
    workbook = model_workbook()

    exact = goal_seek(workbook, "C1", "A1", 7)

    assert exact.converged
    assert exact.iterations == 0
    with pytest.raises(ValueError, match="Tolerance"):
        goal_seek(workbook, "C1", "A1", 7, tolerance=0)
    with pytest.raises(ValueError, match="bracket"):
        goal_seek(workbook, "C1", "A1", 100, minimum=0, maximum=1)
    with pytest.raises(ValueError, match="Minimum"):
        goal_seek(workbook, "C1", "A1", 7, minimum=2, maximum=1)


def test_goal_seek_rejects_non_numeric_inputs_and_formula_errors() -> None:
    workbook = model_workbook()
    workbook.active_sheet.set_cell(0, 0, "text")

    with pytest.raises(ValueError, match="input must be numeric"):
        goal_seek(workbook, "C1", "A1", 7)

    engine = FormulaEngine(workbook)
    engine.set_cell("Sheet1", 0, 0, 2)
    engine.set_cell("Sheet1", 0, 2, "=1/A1")
    with pytest.raises(ValueError, match="returned"):
        goal_seek(workbook, "C1", "A1", 0, minimum=-1, maximum=1)


def test_scenario_and_sensitivity_services_validate_empty_and_duplicate_inputs() -> None:
    workbook = model_workbook()

    with pytest.raises(ValueError, match="scenario"):
        evaluate_scenarios(workbook, (), ("C1",))
    with pytest.raises(ValueError, match="output"):
        evaluate_scenarios(workbook, (Scenario("Base", (("A1", 1),)),), ())
    with pytest.raises(ValueError, match="sensitivity value"):
        one_variable_sensitivity(workbook, "C1", "A1", ())
    with pytest.raises(ValueError, match="Row and column"):
        two_variable_sensitivity(workbook, "C1", "A1", (), "B1", (1,))
    with pytest.raises(ValueError, match="different"):
        two_variable_sensitivity(workbook, "C1", "A1", (1,), "A1", (1,))


def test_model_audit_reports_circular_and_uncalculated_formulas() -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(2, 0, "=1+2")
    engine = FormulaEngine(workbook)
    engine.set_cell("Sheet1", 0, 0, "=B1")
    engine.set_cell("Sheet1", 0, 1, "=A1")

    report = audit_financial_model(workbook)
    codes = [issue.code for issue in report.issues]

    assert codes.count("CIRCULAR_REFERENCE") == 2
    assert "UNCALCULATED_FORMULA" in codes
