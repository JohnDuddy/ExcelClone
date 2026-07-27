from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QApplication

from duddysheet.core.chart import CHART_TYPES, ChartSpec
from duddysheet.commands.edits import AddChartCommand
from duddysheet.core.refs import parse_a1
from duddysheet.core.workbook import Workbook
from duddysheet.ui.charting import ChartPanel
from duddysheet.ui.dialogs.chart_wizard import ChartWizard
from duddysheet.ui.main_window import MainWindow


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
    sorted(CHART_TYPES),
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
    wizard.theme.setCurrentText("editorial")
    wizard.number_format.setCurrentText("currency")
    wizard.show_labels.setChecked(True)
    wizard.show_trendline.setChecked(True)

    spec = wizard.chart_spec()

    assert spec.sheet_name == "Sheet1"
    assert spec.source_range == parse_a1("A1:C4", default_sheet="Sheet1")
    assert spec.chart_type == "line"
    assert spec.title == "Trend"
    assert spec.legend_position == "bottom"
    assert spec.theme == "editorial"
    assert spec.number_format == "currency"
    assert spec.show_data_labels
    assert spec.show_trendline
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


def test_chart_studio_recommends_and_previews_selected_data() -> None:
    application()
    workbook = chart_workbook()
    wizard = ChartWizard(
        "Sheet1",
        "A1:C4",
        workbook=workbook,
    )

    assert wizard.recommendation_list.count() >= 3
    assert wizard.chart_type.currentData() == "column"
    assert wizard.title.text() == "Revenue vs Cost"
    assert wizard.preview_figure.axes
    wizard.close()


def test_chart_panel_exports_vector_and_pdf_formats(tmp_path) -> None:
    application()
    workbook = chart_workbook()
    spec = ChartSpec(
        "exports",
        "Sheet1",
        parse_a1("A1:C4"),
        "line",
        show_data_labels=True,
        show_trendline=True,
    )
    panel = ChartPanel(workbook, spec)

    svg = panel.export(tmp_path / "chart.svg")
    pdf = panel.export(tmp_path / "chart.pdf")

    assert svg.read_text(encoding="utf-8").startswith("<?xml")
    assert pdf.read_bytes().startswith(b"%PDF")
    panel.close()


def test_main_window_quick_chart_expands_one_cell_selection() -> None:
    application()
    workbook = chart_workbook()
    window = MainWindow(workbook)
    index = window.grid_model.index(1, 1)
    window.grid.setCurrentIndex(index)
    window.grid.selectionModel().select(
        index,
        QItemSelectionModel.SelectionFlag.ClearAndSelect,
    )

    window.insert_quick_chart()

    chart = workbook.active_sheet.charts[0]
    assert chart.source_range.to_a1() == "A1:C4"
    assert chart.chart_type == "column"
    assert chart.title == "Revenue vs Cost"
    assert window.ribbon.findChild(object, "quickChartButton") is not None
    assert window.ribbon.findChild(object, "chartStudioButton") is not None
    window._dispose_chart_panels()
    window.close()
