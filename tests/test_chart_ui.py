from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from excelclone.core.chart import ChartSpec
from excelclone.commands.edits import AddChartCommand
from excelclone.core.refs import parse_a1
from excelclone.core.workbook import Workbook
from excelclone.ui.charting import ChartPanel
from excelclone.ui.dialogs.chart_wizard import ChartWizard
from excelclone.ui.main_window import MainWindow


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def chart_workbook() -> Workbook:
    workbook = Workbook()
    rows = (
        ("Month", "Revenue", "Cost"),
        ("Jan", 10, 6),
        ("Feb", 15, 8),
        ("Mar", 12, 7),
    )
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            workbook.active_sheet.set_cell(row, column, value)
    return workbook


@pytest.mark.parametrize(
    "chart_type",
    ["column", "bar", "line", "pie", "scatter", "area", "combo"],
)
def test_chart_panel_renders_every_supported_type_and_exports_png(
    chart_type: str,
    tmp_path,
) -> None:
    application()
    workbook = chart_workbook()
    spec = ChartSpec(
        chart_type,
        "Sheet1",
        parse_a1("A1:C4"),
        chart_type,
        title=f"{chart_type.title()} chart",
    )
    panel = ChartPanel(workbook, spec)

    panel.refresh()
    destination = tmp_path / f"{chart_type}.png"
    panel.export_png(destination)

    assert destination.exists()
    assert destination.stat().st_size > 1000
    panel.close()


def test_chart_wizard_builds_spec_from_user_fields() -> None:
    application()
    wizard = ChartWizard("Sheet1", "A1:C4")
    wizard.chart_type.setCurrentText("line")
    wizard.title.setText("Trend")
    wizard.x_axis.setText("Month")
    wizard.y_axis.setText("Dollars")
    wizard.legend.setCurrentText("bottom")

    spec = wizard.chart_spec()

    assert spec.sheet_name == "Sheet1"
    assert spec.source_range == parse_a1("A1:C4", default_sheet="Sheet1")
    assert spec.chart_type == "line"
    assert spec.title == "Trend"
    assert spec.legend_position == "bottom"
    wizard.close()


def test_main_window_chart_panel_live_updates_after_cell_edit() -> None:
    application()
    workbook = chart_workbook()
    window = MainWindow(workbook)
    spec = ChartSpec("live", "Sheet1", parse_a1("A1:B4"), "column")

    window.history.execute(AddChartCommand(window.engine, "Sheet1", spec))
    panel = window._chart_panels["live"]
    before = panel.figure.axes[0].patches[0].get_height()
    window.grid_model.setData(window.grid_model.index(1, 1), "25")
    after = panel.figure.axes[0].patches[0].get_height()

    assert before == 10
    assert after == 25
    window._dispose_chart_panels()
    window.close()
