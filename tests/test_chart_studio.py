from __future__ import annotations

import json
import os
from dataclasses import replace
import warnings
from zipfile import ZipFile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from matplotlib.figure import Figure
from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QApplication, QMenu, QToolButton

import duddysheet.ui.main_window as main_window_module
from duddysheet.core.chart import (
    CHART_CATALOG,
    CHART_FAMILIES,
    CHART_INFO,
    CHART_TYPES,
    ChartSpec,
)
from duddysheet.core.refs import parse_a1
from duddysheet.core.workbook import Workbook
from duddysheet.io.native import load_native, save_native
from duddysheet.ui.chart_renderer import draw_chart
from duddysheet.ui.dialogs.chart_help import (
    TUTORIALS,
    ChartHelpDialog,
    topic_for_chart_type,
)
from duddysheet.ui.dialogs.chart_wizard import ChartWizard
from duddysheet.ui.main_window import MainWindow


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def sales_workbook() -> Workbook:
    workbook = Workbook()
    rows = (
        ("Month", "Revenue", "Cost", "Margin"),
        ("Jan", 120, 80, 40),
        ("Feb", 135, 84, 51),
        ("Mar", 128, 90, 38),
        ("Apr", 150, 92, 58),
        ("May", 162, 97, 65),
    )
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            workbook.active_sheet.set_cell(row, column, value)
    return workbook


def full_spec(chart_type: str = "column") -> ChartSpec:
    """A chart with every element and format option moved off its default."""
    return ChartSpec(
        "full",
        "Sheet1",
        parse_a1("A1:D6", default_sheet="Sheet1"),
        chart_type,
        title="Everything",
        x_axis_title="Month",
        y_axis_title="Dollars",
        legend_position="bottom",
        theme="coastal",
        show_data_labels=True,
        show_trendline=True,
        highlight_extrema=True,
        show_grid=False,
        secondary_axis=True,
        number_format="currency",
        switch_row_column=False,
        empty_cells="connect",
        show_x_axis=False,
        show_y_axis=False,
        minor_gridlines=True,
        vertical_gridlines=True,
        data_label_position="inside_base",
        data_label_content="category_value",
        show_data_table=True,
        error_bars="percentage",
        error_amount=7.5,
        trendline_type="polynomial",
        trendline_order=3,
        trendline_forward=2.0,
        trendline_backward=1.0,
        show_equation=True,
        show_r_squared=True,
        drop_lines=True,
        high_low_lines=True,
        up_down_bars=True,
        axis_min=0.0,
        axis_max=400.0,
        major_unit=50.0,
        log_scale=False,
        reverse_categories=True,
        display_units="hundreds",
        color_scheme="colorful",
        smooth_lines=True,
        gap_width=80,
        series_overlap=-20,
        hole_size=40,
        first_slice_angle=90,
        pie_explosion=15,
        split_count=2,
        bin_count=6,
        combo_series_types=("column", "area", "line"),
        secondary_series=(3,),
    )


def test_chart_studio_round_trips_every_option_when_editing() -> None:
    application()
    workbook = sales_workbook()
    original = full_spec()

    wizard = ChartWizard(
        "Sheet1",
        original.source_range.to_a1(),
        workbook=workbook,
        existing=original,
    )

    assert wizard.chart_spec() == original
    wizard.close()


def test_editing_a_chart_keeps_its_type_instead_of_the_top_recommendation() -> None:
    application()
    workbook = sales_workbook()
    pie = ChartSpec("pie", "Sheet1", parse_a1("A1:B6"), "pie", title="Share")

    wizard = ChartWizard("Sheet1", "A1:B6", workbook=workbook, existing=pie)

    assert wizard.recommendation_list.count() >= 1
    assert wizard.chart_type.currentData() == "pie"
    assert wizard.chart_spec().chart_type == "pie"
    wizard.close()


def test_all_charts_gallery_lists_every_type_and_selects_it() -> None:
    application()
    wizard = ChartWizard("Sheet1", "A1:D6", workbook=sales_workbook())
    keys = []
    for index in range(wizard.gallery.topLevelItemCount()):
        family = wizard.gallery.topLevelItem(index)
        for child in range(family.childCount()):
            keys.append(family.child(child).data(0, Qt.ItemDataRole.UserRole))
    funnel = next(
        family.child(child)
        for index in range(wizard.gallery.topLevelItemCount())
        for family in [wizard.gallery.topLevelItem(index)]
        for child in range(family.childCount())
        if family.child(child).data(0, Qt.ItemDataRole.UserRole) == "funnel"
    )

    wizard.gallery.setCurrentItem(funnel)

    assert sorted(keys) == sorted(CHART_TYPES)
    assert wizard.chart_type.currentData() == "funnel"
    assert "stages of a process" in wizard.type_description.text()
    wizard.close()


def test_chart_studio_reports_invalid_numbers_without_crashing() -> None:
    application()
    wizard = ChartWizard("Sheet1", "A1:D6", workbook=sales_workbook())
    wizard.axis_min.setText("lots")

    with pytest.raises(ValueError, match="Axis minimum must be a number"):
        wizard.chart_spec()
    wizard._refresh_preview()

    texts = [text.get_text() for text in wizard.preview_figure.axes[0].texts]
    assert "Axis minimum must be a number" in texts
    wizard.close()


def test_initial_type_opens_the_gallery_on_that_chart() -> None:
    application()
    wizard = ChartWizard(
        "Sheet1",
        "A1:D6",
        workbook=sales_workbook(),
        initial_type="radar_filled",
    )

    assert wizard.chart_type.currentData() == "radar_filled"
    assert wizard.tabs.tabText(wizard.tabs.currentIndex()) == "All Charts"
    wizard.close()


@pytest.mark.parametrize("chart_type", sorted(CHART_TYPES))
def test_every_chart_type_renders_with_every_element_enabled(chart_type: str) -> None:
    workbook = sales_workbook()
    spec = full_spec(chart_type)
    figure = Figure(figsize=(7, 4.6), constrained_layout=True)

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        draw_chart(figure, workbook, spec)
        figure.canvas.draw()

    assert figure.axes


def test_three_d_types_use_a_three_d_projection() -> None:
    figure = Figure()
    draw_chart(figure, sales_workbook(), ChartSpec("c", "Sheet1", parse_a1("A1:D6"), "column_3d"))

    assert figure.axes[0].name == "3d"


def test_trendline_equation_and_data_table_are_drawn() -> None:
    figure = Figure()
    spec = ChartSpec(
        "c",
        "Sheet1",
        parse_a1("A1:B6"),
        "line",
        show_trendline=True,
        show_equation=True,
        show_r_squared=True,
        show_data_table=True,
    )

    draw_chart(figure, sales_workbook(), spec)

    axes = figure.axes[0]
    assert any("R² = " in text.get_text() for text in axes.texts)
    assert axes.tables


def test_stock_chart_explains_a_wrong_column_count() -> None:
    figure = Figure()
    draw_chart(
        figure,
        sales_workbook(),
        ChartSpec("c", "Sheet1", parse_a1("A1:D6"), "stock_ohlc"),
    )

    assert any(
        "needs 4 data columns" in text.get_text() for text in figure.axes[0].texts
    )


def test_pareto_adds_a_cumulative_percent_axis() -> None:
    figure = Figure()
    draw_chart(
        figure,
        sales_workbook(),
        ChartSpec("c", "Sheet1", parse_a1("A1:B6"), "pareto"),
    )

    heights = [patch.get_height() for patch in figure.axes[0].patches]
    assert heights == sorted(heights, reverse=True)
    assert figure.axes[1].get_ylim() == (0, 105)


def test_extended_chart_options_round_trip_natively(tmp_path) -> None:
    workbook = sales_workbook()
    workbook.active_sheet.charts.append(full_spec("combo_custom"))

    restored = load_native(save_native(workbook, tmp_path / "charts.dsheet"))

    assert restored.active_sheet.charts == workbook.active_sheet.charts


def test_schema_three_workbooks_open_with_default_chart_options(tmp_path) -> None:
    workbook = sales_workbook()
    workbook.active_sheet.charts.append(
        ChartSpec("old", "Sheet1", parse_a1("A1:C6"), "radar", title="Legacy")
    )
    path = save_native(workbook, tmp_path / "legacy.dsheet")
    # Rewrite as a schema 3 file: no sparklines and only the original fields.
    original_fields = {
        "chart_id", "sheet_name", "source_range", "chart_type", "title",
        "x_axis_title", "y_axis_title", "legend_position", "has_headers",
        "category_column", "series_columns", "theme", "show_data_labels",
        "show_trendline", "highlight_extrema", "show_grid", "secondary_axis",
        "number_format",
    }
    with ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(entries["workbook.json"])
    manifest["schema_version"] = 3
    entries["workbook.json"] = json.dumps(manifest).encode()
    sheet_name = manifest["sheets"][0]["file"]
    sheet = json.loads(entries[sheet_name])
    sheet.pop("sparklines")
    sheet["charts"] = [
        {key: value for key, value in chart.items() if key in original_fields}
        for chart in sheet["charts"]
    ]
    entries[sheet_name] = json.dumps(sheet).encode()
    with ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)

    restored = load_native(path)

    chart = restored.active_sheet.charts[0]
    assert chart == ChartSpec("old", "Sheet1", parse_a1("A1:C6"), "radar", title="Legacy")
    assert restored.active_sheet.sparklines == []


def select_cell(window: MainWindow, row: int, column: int) -> None:
    index = window.grid_model.index(row, column)
    window.grid.setCurrentIndex(index)
    window.grid.selectionModel().select(
        index,
        QItemSelectionModel.SelectionFlag.ClearAndSelect,
    )


def test_insert_menu_offers_every_family_and_inserts_the_chosen_type() -> None:
    application()
    window = MainWindow(sales_workbook())
    select_cell(window, 2, 1)
    families = [
        action.text()
        for action in window.insert_menu.actions()
        if action.menu() is not None
    ]

    column_menu = next(
        menu for menu in window.insert_menu.findChildren(QMenu) if menu.title() == "Column"
    )
    stacked = next(
        action for action in column_menu.actions() if action.text() == "100% Stacked Column"
    )
    stacked.trigger()

    assert families == [family for family, _ in CHART_FAMILIES] + ["Sparklines"]
    chart = window.engine.workbook.active_sheet.charts[0]
    assert chart.chart_type == "stacked_column_100"
    assert chart.source_range.to_a1() == "A1:D6"
    assert chart.title == "Revenue and 2 other series"
    window.history.undo()
    assert window.engine.workbook.active_sheet.charts == []
    window._dispose_chart_panels()
    window.close()


def test_ribbon_insert_tab_has_excel_chart_galleries() -> None:
    application()
    window = MainWindow(sales_workbook())
    select_cell(window, 1, 1)
    gallery = window.ribbon.findChild(QToolButton, "WaterfallStockGalleryButton")
    funnel = next(
        action for action in gallery.menu().actions() if action.data() == "chart:funnel"
    )

    funnel.trigger()

    names = {
        button.objectName()
        for button in window.ribbon.findChildren(QToolButton)
        if button.objectName().endswith("GalleryButton")
    }
    assert {
        "ColumnBarGalleryButton",
        "LineAreaGalleryButton",
        "PieDoughnutGalleryButton",
        "HierarchyGalleryButton",
        "StatisticGalleryButton",
        "ScatterBubbleGalleryButton",
        "WaterfallStockGalleryButton",
        "ComboGalleryButton",
        "MoreChartsGalleryButton",
        "SparklinesGalleryButton",
    } <= names
    assert window.engine.workbook.active_sheet.charts[0].chart_type == "funnel"
    window._dispose_chart_panels()
    window.close()


def test_help_menu_opens_the_charts_tutorial(monkeypatch) -> None:
    application()
    window = MainWindow(sales_workbook())
    opened: list[str | None] = []

    def fake_exec(dialog: ChartHelpDialog) -> int:
        opened.append(dialog.current_topic)
        return 0

    monkeypatch.setattr(main_window_module.ChartHelpDialog, "exec", fake_exec)
    help_menu = next(
        menu for menu in window.menuBar().findChildren(QMenu) if menu.title() == "&Help"
    )

    assert window.chart_help_action in help_menu.actions()
    window.chart_help_action.trigger()
    window._ribbon_action("Chart Help")
    window.show_chart_help(chart_type="stock_vohlc")

    assert opened == ["start", "start", "stock"]
    window.close()


def test_tutorial_covers_every_chart_type_and_is_searchable() -> None:
    application()
    dialog = ChartHelpDialog()

    assert dialog.tutorial_list.count() == len(TUTORIALS) >= 25
    for key in CHART_TYPES:
        assert topic_for_chart_type(key) in {item[0] for item in TUTORIALS}
    reference = dialog.findChild(object, "chartTypeReference").toPlainText()
    for info in CHART_CATALOG:
        assert info.label in reference

    dialog.search.setText("R-squared")
    titles = [
        dialog.tutorial_list.item(row).text()
        for row in range(dialog.tutorial_list.count())
    ]
    assert "Trendlines and forecasting" in titles
    assert len(titles) < len(TUTORIALS)

    dialog.show_topic("sparklines")
    assert dialog.search.text() == ""
    assert dialog.current_topic == "sparklines"
    assert "Win/Loss" in dialog.tutorial_detail.toPlainText()
    dialog.close()


def test_every_tutorial_family_lesson_names_its_chart_types() -> None:
    lessons = {key: html for key, _, html in TUTORIALS}
    for info in CHART_CATALOG:
        lesson = lessons[topic_for_chart_type(info.key)]
        if info.key == "heatmap":
            continue
        assert info.label.replace("&", "&amp;") in lesson or info.label in lesson, info.key
    assert CHART_INFO["funnel"].family == "Funnel"


def test_radar_gridlines_can_be_turned_off() -> None:
    figure = Figure()
    base = ChartSpec("c", "Sheet1", parse_a1("A1:D6"), "radar")

    draw_chart(figure, sales_workbook(), base)
    shown = [line.get_visible() for line in figure.axes[0].get_ygridlines()]
    draw_chart(figure, sales_workbook(), replace(base, show_grid=False))
    hidden = [line.get_visible() for line in figure.axes[0].get_ygridlines()]

    assert any(shown)
    assert not any(hidden)
