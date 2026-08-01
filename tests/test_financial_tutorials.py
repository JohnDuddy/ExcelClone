from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication, QToolButton

from duddysheet.core.engine import FormulaEngine
from duddysheet.core.financial_analysis import (
    Scenario,
    audit_financial_model,
    evaluate_scenarios,
    goal_seek,
    two_variable_sensitivity,
)
from duddysheet.core.financial_models import (
    FINANCIAL_MODEL_CATALOG,
    create_financial_model,
)
from duddysheet.ui.dialogs.financial_help import FinancialHelpDialog
from duddysheet.ui.ribbon import Ribbon

# Every command on the Financial ribbon tab and menu, paired with the tutorial
# that documents it. The tutorials quote live numbers, so the tests below
# recompute them rather than trusting the prose.
FINANCIAL_TOOL_TUTORIALS = {
    "New Financial Model": "Financial menu: New Financial Model",
    "Goal Seek": "Financial menu: Goal Seek",
    "Sensitivity Table": "Financial menu: Sensitivity Table",
    "Scenario Analysis": "Financial menu: Scenario Analysis",
    "Model Audit": "Financial menu: Model Audit",
}


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def tutorial_text(title: str) -> str:
    dialog = FinancialHelpDialog()
    titles = [
        dialog.tutorial_list.item(row).text()
        for row in range(dialog.tutorial_list.count())
    ]
    dialog.tutorial_list.setCurrentRow(titles.index(title))
    text = dialog.tutorial_detail.toPlainText()
    dialog.close()
    return text


@pytest.mark.parametrize("title", sorted(FINANCIAL_TOOL_TUTORIALS.values()))
def test_every_financial_tool_has_a_tutorial(title: str) -> None:
    application()
    dialog = FinancialHelpDialog()
    titles = [
        dialog.tutorial_list.item(row).text()
        for row in range(dialog.tutorial_list.count())
    ]
    dialog.close()

    assert title in titles


def test_the_financial_ribbon_tab_exposes_every_documented_tool() -> None:
    application()
    ribbon = Ribbon()
    financial = next(
        ribbon.widget(index)
        for index in range(ribbon.count())
        if ribbon.tabText(index) == "Financial"
    )
    buttons = {button.text() for button in financial.findChildren(QToolButton)}
    ribbon.deleteLater()

    # Ribbon labels are abbreviated; the tutorials use the full menu wording.
    assert {"Goal Seek", "Sensitivity", "Scenarios", "Model Audit"} <= buttons


def test_new_financial_model_tutorial_lists_every_catalog_model() -> None:
    application()
    text = tutorial_text("Financial menu: New Financial Model")

    for template in FINANCIAL_MODEL_CATALOG:
        assert template.name in text
        assert template.primary_output in text


def test_goal_seek_tutorial_example_solves_as_documented() -> None:
    result = goal_seek(
        create_financial_model("loan"),
        "Summary!B9",
        "Summary!B3",
        2000.0,
    )

    assert result.converged
    assert round(result.result_value, 2) == 2000.00
    assert round(result.input_value, 2) == 316421.64


def test_goal_seek_tutorial_quotes_the_solved_principal() -> None:
    application()
    text = tutorial_text("Financial menu: Goal Seek")

    assert "316,421.64" in text
    assert "Summary!B9" in text
    assert "Summary!B3" in text


def test_sensitivity_tutorial_grid_matches_a_live_calculation() -> None:
    table = two_variable_sensitivity(
        create_financial_model("dcf"),
        "Valuation!B15",
        "Inputs!B11",
        (0.09, 0.10, 0.11),
        "Inputs!B12",
        (0.02, 0.025, 0.03),
    )
    rounded = [[round(value, 2) for value in row] for row in table.values]

    assert rounded == [
        [18.13, 15.41, 13.30],
        [19.41, 16.35, 14.01],
        [20.91, 17.43, 14.82],
    ]


def test_sensitivity_tutorial_quotes_the_calculated_grid() -> None:
    application()
    text = tutorial_text("Financial menu: Sensitivity Table")

    for quoted in ("18.13", "15.41", "13.30", "19.41", "16.35", "14.82"):
        assert quoted in text


def test_scenario_tutorial_cases_evaluate_as_documented() -> None:
    results = evaluate_scenarios(
        create_financial_model("dcf"),
        (
            Scenario("Base", (("Inputs!B5", 0.08), ("Inputs!B6", 0.22))),
            Scenario("Downside", (("Inputs!B5", 0.03), ("Inputs!B6", 0.18))),
            Scenario("Upside", (("Inputs!B5", 0.12), ("Inputs!B6", 0.26))),
        ),
        ("Valuation!B15",),
    )
    calculated = {
        result.name: round(float(result.values[0][1]), 2) for result in results
    }

    assert calculated == {"Base": 16.35, "Downside": 8.52, "Upside": 25.83}


def test_scenario_tutorial_quotes_each_case() -> None:
    application()
    text = tutorial_text("Financial menu: Scenario Analysis")

    for quoted in ("16.35", "8.52", "25.83"):
        assert quoted in text


def test_model_audit_tutorial_example_reports_the_documented_finding() -> None:
    workbook = create_financial_model("loan")
    FormulaEngine(workbook).recalculate()
    report = audit_financial_model(workbook)

    assert report.error_count == 0
    assert [(issue.severity, issue.code, issue.cell) for issue in report.issues] == [
        ("info", "EMBEDDED_CONSTANT", "Summary!B7")
    ]


def test_model_audit_tutorial_documents_every_finding_code() -> None:
    application()
    text = tutorial_text("Financial menu: Model Audit")

    for code in (
        "FORMULA_ERROR",
        "CIRCULAR_REFERENCE",
        "UNCALCULATED_FORMULA",
        "BLANK_PRECEDENT",
        "EMBEDDED_CONSTANT",
    ):
        assert code in text
    assert "Summary!B7" in text
