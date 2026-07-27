from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QToolButton

import excelclone.ui.main_window as main_window_module
from excelclone.core.financial_analysis import audit_financial_model
from excelclone.core.financial_models import create_financial_model
from excelclone.ui.dialogs.financial import (
    AuditReportDialog,
    GoalSeekDialog,
    ScenarioDialog,
    SensitivityDialog,
)
from excelclone.ui.dialogs.financial_help import FinancialHelpDialog
from excelclone.ui.main_window import MainWindow


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_ribbon_exposes_complete_financial_toolkit() -> None:
    application()
    window = MainWindow()

    assert window.ribbon.tabText(4) == "Financial"
    object_names = {
        button.objectName()
        for button in window.ribbon.findChildren(QToolButton)
    }
    assert {
        "modelTemplatesButton",
        "goalSeekButton",
        "sensitivityButton",
        "scenariosButton",
        "modelAuditButton",
    } <= object_names
    window.close()


def test_goal_seek_and_sensitivity_dialogs_validate_numeric_requests() -> None:
    application()
    goal_seek = GoalSeekDialog("C1")
    goal_seek.input_cell.setText("A1")
    goal_seek.target.setText("12.5")
    goal_seek.use_bounds.setChecked(True)
    goal_seek.minimum.setText("-10")
    goal_seek.maximum.setText("20")

    goal_request = goal_seek.request()

    assert goal_request.formula_cell == "C1"
    assert goal_request.target == 12.5
    assert goal_request.minimum == -10
    sensitivity = SensitivityDialog("C1")
    sensitivity.row_values.setText("-10%, 0%, 10%")
    sensitivity.column_input_cell.setText("B1")
    sensitivity.column_values.setText("1, 2")

    sensitivity_request = sensitivity.request()

    assert sensitivity_request.row_values == (-0.1, 0, 0.1)
    assert sensitivity_request.column_values == (1, 2)
    goal_seek.close()
    sensitivity.close()


def test_scenario_dialog_parses_named_typed_assignments() -> None:
    application()
    dialog = ScenarioDialog()
    dialog.scenarios.setPlainText(
        "Base: A1=100, B1=5%, C1=TRUE\nDownside: A1=90, B1=2%"
    )
    dialog.outputs.setText("D1, E1")

    request = dialog.request()

    assert request.scenarios[0].name == "Base"
    assert request.scenarios[0].values == (
        ("A1", 100),
        ("B1", 0.05),
        ("C1", True),
    )
    assert request.output_cells == ("D1", "E1")
    dialog.close()


def test_analysis_table_write_is_one_undoable_command() -> None:
    application()
    window = MainWindow()

    window._write_analysis_table("B2", (("Input", 1, 2), ("Result", 3, 4)))

    assert window.engine.workbook.active_sheet.get_cell(1, 1).raw_input == "Input"
    assert window.engine.workbook.active_sheet.get_cell(2, 3).raw_input == 4
    window.history.undo()
    assert window.engine.workbook.active_sheet.get_cell(1, 1).raw_input is None
    assert window.engine.workbook.active_sheet.get_cell(2, 3).raw_input is None
    window.close()


def test_new_financial_model_installs_selected_workbook(
    monkeypatch,
) -> None:
    application()
    window = MainWindow()

    class SelectedModelDialog:
        def __init__(self, parent: object) -> None:
            self.models = SimpleNamespace(currentText=lambda: "Discounted Cash Flow")

        def exec(self) -> QDialog.DialogCode:
            return QDialog.DialogCode.Accepted

        def template_key(self) -> str:
            return "dcf"

    monkeypatch.setattr(
        main_window_module,
        "FinancialModelDialog",
        SelectedModelDialog,
    )

    window.new_financial_model()

    assert window.engine.workbook.sheet_names == (
        "Inputs",
        "Forecast",
        "Valuation",
        "Checks",
    )
    assert window.dirty
    window.close()


def test_audit_report_dialog_renders_every_finding() -> None:
    application()
    workbook = create_financial_model("dcf")
    report = audit_financial_model(workbook)
    dialog = AuditReportDialog(report)

    assert dialog.table.rowCount() == len(report.issues)
    assert dialog.table.columnCount() == 5
    dialog.close()


def test_financial_help_searches_filters_and_copies_examples() -> None:
    app = application()
    dialog = FinancialHelpDialog()

    assert dialog.function_list.count() == 46
    dialog.search.setText("level-payment investment")
    names = [
        dialog.function_list.item(row).data(Qt.ItemDataRole.UserRole)
        for row in range(dialog.function_list.count())
    ]
    assert "PMT" in names
    assert len(names) < 46
    dialog.search.clear()
    dialog.category.setCurrentText("Depreciation")
    assert dialog.function_list.count() == 5
    dialog.category.setCurrentText("All financial functions")
    dialog.search.setText("PMT")
    for row in range(dialog.function_list.count()):
        if (
            dialog.function_list.item(row).data(Qt.ItemDataRole.UserRole)
            == "PMT"
        ):
            dialog.function_list.setCurrentRow(row)
            break
    assert "Important notes" in dialog.function_detail.toPlainText()

    dialog.copy_example.click()

    assert app.clipboard().text().startswith("=PMT(")
    app.clipboard().clear()
    dialog.close()


def test_financial_help_contains_tutorials_quick_reference_and_models() -> None:
    application()
    dialog = FinancialHelpDialog()

    assert dialog.tutorial_list.count() >= 9
    dialog.tutorial_list.setCurrentRow(1)
    assert "Loan amortization" in dialog.tutorial_detail.toPlainText()
    quick_reference = dialog.findChild(
        type(dialog.function_detail),
        "financialQuickReference",
    )
    models_guide = dialog.findChild(
        type(dialog.function_detail),
        "financialModelsGuide",
    )
    assert "Day-count basis" in quick_reference.toPlainText()
    assert "Discounted Cash Flow" in models_guide.toPlainText()
    dialog.close()


def test_main_window_exposes_help_menu_f1_and_financial_help_ribbon() -> None:
    application()
    window = MainWindow()

    menu_titles = [action.text() for action in window.menuBar().actions()]
    ribbon_buttons = {
        button.objectName()
        for button in window.ribbon.findChildren(QToolButton)
    }

    assert "&Help" in menu_titles
    assert window.financial_help_action.shortcut().toString() == "F1"
    assert "financialHelpButton" in ribbon_buttons
    window.close()
