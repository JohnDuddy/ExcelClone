"""The PivotTable Fields pane, calculated fields, slicers, and PivotCharts."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication

from duddysheet.core.analysis_help import build_practice_workbook
from duddysheet.core.chart import ChartSpec, chart_data
from duddysheet.core.pivot import (
    PivotSlicer,
    PivotValueField,
    apply_slicer,
    compute_pivot,
    pivot_from_dict,
    pivot_to_dict,
    render_pivot,
    slicer_from_dict,
    slicer_items,
    slicer_to_dict,
    substitute_fields,
)
from duddysheet.core.refs import parse_a1
from duddysheet.io.native import load_native, save_native
from duddysheet.io.xlsx_reader import read_xlsx
from duddysheet.io.xlsx_writer import write_xlsx
from duddysheet.ui.dialogs.analysis_dialogs import PivotFieldsPanel
from duddysheet.ui.main_window import MainWindow


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _by_region(workbook, **changes):
    spec = workbook.get_sheet("Pivot").pivots[0]
    spec = replace(spec, columns=(), grouping=(), **changes)
    workbook.get_sheet("Pivot").pivots[0] = spec
    return render_pivot(workbook, "Pivot", spec)


def _labels(result) -> dict:
    return {result.cells[(row, 0)].value: [result.cells.get((row, column)).value if (row, column) in result.cells else None for column in range(1, result.width)] for row in range(result.height) if (row, 0) in result.cells}


def test_calculated_fields_work_on_sums_like_excel() -> None:
    workbook = build_practice_workbook()
    spec = _by_region(
        workbook,
        calculated_fields=(("Avg Price", "=Amount/Units"), ("Bonus", "='Amount'*0.1")),
        values=(PivotValueField("Amount"), PivotValueField("Units"), PivotValueField("Avg Price"), PivotValueField("Bonus")),
    )
    rows = _labels(compute_pivot(workbook, spec))
    # The grand total is Sum(Amount)/Sum(Units), not a sum of the row ratios.
    assert rows["Grand Total"][2] == pytest.approx(1635 / 1075)
    assert rows["East"][2] == pytest.approx(594.75 / 395)
    assert rows["East"][3] == pytest.approx(59.475)
    assert substitute_fields('=Amount/Units&"Units"', {"Amount": 10.0, "Units": -2.0}) == '=10.0/(-2.0)&"Units"'
    assert pivot_from_dict(pivot_to_dict(spec)).calculated_fields == spec.calculated_fields


def test_calculated_fields_round_trip_through_xlsx(tmp_path) -> None:
    workbook = build_practice_workbook()
    _by_region(workbook, calculated_fields=(("Avg Price", "=Amount/Units"),), values=(PivotValueField("Amount"), PivotValueField("Avg Price")))
    path = tmp_path / "calc.xlsx"
    write_xlsx(workbook, path)
    loaded = read_xlsx(path)
    assert loaded.warnings == ()
    spec = loaded.workbook.get_sheet("Pivot").pivots[0]
    assert spec.calculated_fields == (("Avg Price", "=Amount/Units"),)
    assert [value.field for value in spec.values] == ["Amount", "Avg Price"]


def test_slicers_filter_their_pivot_table(tmp_path) -> None:
    workbook = build_practice_workbook()
    spec = _by_region(workbook)
    slicer = PivotSlicer("Slicer_Region", "Pivot", spec.name, "Region")
    assert [item for item, selected in slicer_items(workbook, slicer) if selected] == ["East", "North", "West"]
    filtered = apply_slicer(workbook, slicer, ["East"])
    assert list(_labels(compute_pivot(workbook, filtered))) == ["Row Labels", "East", "Grand Total"]
    assert [selected for _item, selected in slicer_items(workbook, slicer)] == [True, False, False]
    cleared = apply_slicer(workbook, slicer, None)
    assert cleared.hidden_items == ()
    assert slicer_from_dict(slicer_to_dict(slicer)) == slicer
    workbook.get_sheet("Pivot").slicers.append(slicer)
    path = tmp_path / "slicer.dsheet"
    save_native(workbook, path)
    assert load_native(path).get_sheet("Pivot").slicers == [slicer]


def test_pivot_chart_follows_the_pivot_layout() -> None:
    workbook = build_practice_workbook()
    spec = workbook.get_sheet("Pivot").pivots[0]
    chart = ChartSpec("pc", "Pivot", parse_a1("A3:D8"), "column", pivot_name=spec.name)
    data = chart_data(workbook, chart)
    assert data.categories == ("East", "North", "West")
    assert [series.name for series in data.series] == ["2024", "2025"]
    _by_region(workbook, rows=("Region", "Product"))
    data = chart_data(workbook, chart)
    assert data.categories[0] == "East / Apple" and len(data.series) == 1


def test_fields_panel_drag_and_drop_and_deferred_updates() -> None:
    application()
    workbook = build_practice_workbook()
    spec = _by_region(workbook)
    panel = PivotFieldsPanel(workbook, spec, live=True)
    emitted = []
    panel.specChanged.connect(emitted.append)
    panel.drop_field("fields", 1, "Product", "columns", None)
    assert emitted[-1].columns == ("Product",)
    panel.drop_field("columns", 0, "Product", "rows", 0)
    assert emitted[-1].rows == ("Product", "Region") and emitted[-1].columns == ()
    panel.drop_field("rows", 0, "Product", "rows", None)
    assert emitted[-1].rows == ("Region", "Product")
    panel.drop_field("values", 0, "Amount", "page_fields", None)
    assert emitted[-1].values == () and emitted[-1].page_fields == ("Amount",)
    panel.remove_at("page_fields", 0)
    assert emitted[-1].page_fields == ()
    count = len(emitted)
    panel.defer.setChecked(True)
    panel.add_field("Amount", "values")
    assert len(emitted) == count
    panel.update_button.click()
    assert emitted[-1].values == (PivotValueField("Amount"),)
    panel.define_calculated_field("Per Unit", "=Amount/Units")
    assert "Per Unit" in panel.fields and panel.spec.values[-1].field == "Per Unit"


def test_window_pane_slicers_and_pivot_chart() -> None:
    application()
    window = MainWindow()
    window.open_practice_workbook()
    workbook = window.engine.workbook
    window.sheet_tabs.tab_bar.setCurrentIndex(workbook.sheet_names.index("Pivot"))
    window.grid.setCurrentIndex(window.grid_model.index(4, 1))
    dock = window.pivot_fields_dock
    assert dock is not None and dock.isVisibleTo(window)
    panel = dock.widget()
    panel.drop_field("columns", 0, "Date", "page_fields", None)
    pivot = window.grid_model.sheet.pivots[0]
    assert pivot.page_fields == ("Date",) and pivot.columns == ()
    window.history.undo()
    assert window.grid_model.sheet.pivots[0].columns == ("Date",)
    window.grid.setCurrentIndex(window.grid_model.index(4, 1))
    (slicer,) = window.insert_slicers(["Region"])
    assert slicer.name in window._slicer_panels
    window.apply_slicer_selection(slicer.name, ["West"])
    labels = [window.grid_model.sheet.get_cell(row, 0).display_value for row in range(3, 8)]
    assert "East" not in labels and "West" in labels
    slicer_panel = window._slicer_panels[slicer.name]
    assert [entry.text() for entry in slicer_panel.items.selectedItems()] == ["West"]
    slicer_panel.clear_filter()
    assert window.grid_model.sheet.pivots[0].hidden_items == ()
    window.grid.setCurrentIndex(window.grid_model.index(4, 1))
    chart = window.insert_pivot_chart()
    assert chart.pivot_name == "PivotTable1" and chart.chart_id in window._chart_panels
    assert window.add_calculated_field("Bonus", "=Amount*0.1")
    assert window.grid_model.sheet.pivots[0].values[-1].field == "Bonus"
    window.remove_slicer(slicer.name)
    assert window.grid_model.sheet.slicers == []
    window.grid.setCurrentIndex(window.grid_model.index(30, 10))
    assert not dock.isVisibleTo(window)
    window.close()
