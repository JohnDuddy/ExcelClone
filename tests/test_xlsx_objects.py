"""Charts, sparklines, and PivotTables survive a round trip through .xlsx."""

from __future__ import annotations

import zipfile
from dataclasses import replace
from xml.dom.minidom import parseString

import pytest

from duddysheet.core.chart import CHART_INFO, ChartSpec
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.refs import parse_a1
from duddysheet.core.sparkline import build_sparklines
from duddysheet.core.workbook import Workbook
from duddysheet.io.xlsx_charts import xlsx_chart_warnings
from duddysheet.io.xlsx_reader import read_xlsx
from duddysheet.io.xlsx_writer import write_xlsx

STANDARD = (
    "column", "stacked_column", "stacked_column_100", "column_3d_clustered", "column_3d_stacked",
    "column_3d_stacked_100", "column_3d", "line_plain", "stacked_line", "stacked_line_100", "line",
    "stacked_line_markers", "stacked_line_100_markers", "line_3d", "donut", "bar", "stacked_bar",
    "stacked_bar_100", "bar_3d_clustered", "bar_3d_stacked", "bar_3d_stacked_100", "area",
    "stacked_area", "stacked_area_100", "area_3d", "area_3d_stacked", "area_3d_stacked_100",
    "radar", "radar_markers", "radar_filled", "combo", "combo_secondary", "combo_area_column",
)
LAYOUTS = {
    "Standard": (
        [("Month", "East", "West", "North"), ("Jan", 10, 20, 15), ("Feb", 12, 18, 17), ("Mar", 15, 22, 14)],
        "A1:D4",
        STANDARD,
    ),
    "Single": (
        [("Item", "Value"), ("A", 30), ("B", -12), ("C", 25), ("D", 8)],
        "A1:B5",
        ("pie", "pie_3d", "pie_of_pie", "bar_of_pie", "pareto", "waterfall", "funnel"),
    ),
    "XY": (
        [("X", "Y", "Size"), (1, 2, 5), (2, 4, 3), (3, 5, 8)],
        "A1:C4",
        ("bubble", "bubble_3d"),
    ),
    "Pairs": (
        [("X", "Y"), (1, 2), (2, 4), (3, 5)],
        "A1:B4",
        ("scatter", "scatter_smooth_markers", "scatter_smooth", "scatter_lines_markers", "scatter_lines"),
    ),
    "Stock": (
        [("Date", "Open", "High", "Low", "Close"), (45000, 10, 12, 9, 11), (45001, 11, 13, 10, 12)],
        "A1:E3",
        ("stock_ohlc",),
    ),
    "Surface": (
        [("", 1, 2, 3), ("a", 1, 2, 3), ("b", 2, 3, 4), ("c", 3, 4, 5)],
        "A1:D4",
        ("surface_3d", "surface_wireframe", "contour", "contour_wireframe"),
    ),
    "Hierarchy": (
        [("Region", "City", "Sales"), ("East", "Boston", 10), ("East", "NYC", 20), ("West", "LA", 15)],
        "A1:C4",
        ("treemap", "sunburst"),
    ),
    "Dist": (
        [("A", "B"), (1, 4), (2, 6), (2, 7), (5, 3)],
        "A1:B5",
        ("histogram", "box"),
    ),
}


def _workbook() -> Workbook:
    workbook = Workbook(create_default=False)
    engine = FormulaEngine(workbook)
    for name, (rows, source, types) in LAYOUTS.items():
        sheet = workbook.add_sheet(name)
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                if value != "":
                    engine.set_cell(name, row, column, value)
        for chart_type in types:
            sheet.charts.append(
                ChartSpec(
                    chart_id=f"{name}-{chart_type}",
                    sheet_name=name,
                    source_range=parse_a1(source),
                    chart_type=chart_type,
                    title=CHART_INFO[chart_type].label,
                )
            )
    engine.recalculate()
    return workbook


def test_every_excel_chart_type_round_trips_through_xlsx(tmp_path) -> None:
    path = tmp_path / "charts.xlsx"
    original = _workbook()
    write_xlsx(original, path)
    loaded = read_xlsx(path)
    assert loaded.warnings == ()
    for sheet in original:
        expected = [chart.chart_type for chart in sheet.charts]
        actual = loaded.workbook.get_sheet(sheet.name).charts
        assert [chart.chart_type for chart in actual] == expected, sheet.name
        assert [chart.title for chart in actual] == [chart.title for chart in sheet.charts]
        for chart in actual:
            assert chart.source_range.min_row == 0 and chart.has_headers


def test_saved_package_parts_are_well_formed_xml(tmp_path) -> None:
    path = tmp_path / "charts.xlsx"
    workbook = _workbook()
    sheet = workbook.get_sheet("Standard")
    sheet.sparklines.extend(build_sparklines(parse_a1("B2:D4"), parse_a1("E2:E4"), "line"))
    write_xlsx(workbook, path)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        for name in names:
            if name.endswith((".xml", ".rels")):
                parseString(archive.read(name))
    # Office 2016 charts need their own style and color parts to open in Excel.
    chartex = [name for name in names if name.startswith("xl/charts/chartEx")]
    assert len(chartex) == 7
    assert sum(name.startswith("xl/charts/style") for name in names) == 7
    assert sum(name.startswith("xl/charts/colors") for name in names) == 7


def test_chart_options_round_trip(tmp_path) -> None:
    workbook = _workbook()
    sheet = workbook.get_sheet("Standard")
    sheet.charts[:] = [
        replace(
            sheet.charts[0],
            title="Sales by month",
            x_axis_title="Month",
            y_axis_title="Units",
            legend_position="bottom",
            show_data_labels=True,
            data_label_content="category_value",
            show_trendline=True,
            trendline_type="polynomial",
            trendline_order=3,
            show_equation=True,
            minor_gridlines=True,
            vertical_gridlines=True,
            axis_min=0.0,
            axis_max=40.0,
            major_unit=5.0,
            reverse_categories=True,
            display_units="thousands",
            gap_width=80,
            empty_cells="zero",
            error_bars="percentage",
            error_amount=10.0,
        ),
        replace(sheet.charts[0], chart_id="switched", switch_row_column=True, legend_position="none"),
    ]
    path = tmp_path / "options.xlsx"
    write_xlsx(workbook, path)
    first, switched = read_xlsx(path).workbook.get_sheet("Standard").charts
    assert (first.title, first.x_axis_title, first.y_axis_title) == ("Sales by month", "Month", "Units")
    assert first.legend_position == "bottom"
    assert first.show_data_labels and first.data_label_content == "category_value"
    assert first.show_trendline and first.trendline_type == "polynomial" and first.trendline_order == 3
    assert first.show_equation and not first.show_r_squared
    assert first.minor_gridlines and first.vertical_gridlines
    assert (first.axis_min, first.axis_max, first.major_unit) == (0.0, 40.0, 5.0)
    assert first.reverse_categories and first.display_units == "thousands"
    assert first.gap_width == 80 and first.empty_cells == "zero"
    assert first.error_bars == "percentage" and first.error_amount == 10.0
    assert switched.switch_row_column and switched.legend_position == "none"
    assert switched.source_range.to_a1().endswith("A1:D4")


def test_charts_excel_cannot_draw_are_explained() -> None:
    workbook = _workbook()
    sheet = workbook.get_sheet("Standard")
    base = sheet.charts[0]
    sheet.charts[:] = [replace(base, chart_type="heatmap", title="Heat"), replace(base, chart_type="step", title="Steps")]
    warnings = xlsx_chart_warnings(workbook)
    assert any("Heatmap" in warning and "was not saved" in warning for warning in warnings)
    assert any("Step Line" in warning and "Line chart" in warning for warning in warnings)


def test_sparklines_round_trip_with_their_options(tmp_path) -> None:
    workbook = _workbook()
    sheet = workbook.get_sheet("Standard")
    sheet.charts.clear()
    lines = build_sparklines(parse_a1("B2:D4"), parse_a1("E2:E4"), "line")
    columns = [
        replace(item, show_high=True, show_markers=True, color="#112233", marker_color="#445566")
        for item in build_sparklines(parse_a1("B2:D4"), parse_a1("F2:F4"), "column")
    ]
    wins = build_sparklines(parse_a1("B2:D4"), parse_a1("G2:G4"), "win_loss")
    sheet.sparklines.extend([*lines, *columns, *wins])
    path = tmp_path / "sparklines.xlsx"
    write_xlsx(workbook, path)
    loaded = read_xlsx(path).workbook.get_sheet("Standard").sparklines
    key = lambda item: (item.row, item.column)  # noqa: E731
    assert sorted(loaded, key=key) == sorted(sheet.sparklines, key=key)


@pytest.mark.parametrize("chart_type", ["line_plain", "radar", "scatter_smooth"])
def test_marker_free_charts_stay_marker_free(tmp_path, chart_type) -> None:
    workbook = _workbook()
    sheet = workbook.get_sheet("Standard" if chart_type != "scatter_smooth" else "Pairs")
    sheet.charts[:] = [replace(sheet.charts[0], chart_type=chart_type)]
    path = tmp_path / "markers.xlsx"
    write_xlsx(workbook, path)
    assert read_xlsx(path).workbook.get_sheet(sheet.name).charts[0].chart_type == chart_type


# ---------------------------------------------------------------- PivotTables
FIXTURE = __import__("pathlib").Path(__file__).parent / "fixtures" / "excel_objects.xlsx"


def _pivot_workbook():
    from duddysheet.core.analysis_help import build_practice_workbook
    from duddysheet.core.pivot import PivotValueField, render_pivot

    workbook = build_practice_workbook()
    base = workbook.get_sheet("Pivot").pivots[0]
    workbook.add_sheet("More")
    extra = replace(
        base,
        name="Detail",
        anchor=(4, 0),
        extent=None,
        columns=(),
        grouping=(),
        rows=("Region", "Product"),
        values=(PivotValueField("Amount"), PivotValueField("Units", "average", "percent_of_grand_total")),
        page_fields=("Date",),
        hidden_items=(("Region", ("West",)),),
        layout="tabular",
        subtotals=False,
        grand_total_columns=False,
    )
    workbook.get_sheet("More").pivots.append(extra)
    render_pivot(workbook, "More", extra)
    return workbook


def _comparable(spec):
    return replace(spec, cache=None)


def test_pivot_tables_round_trip_as_excel_pivot_tables(tmp_path) -> None:
    workbook = _pivot_workbook()
    path = tmp_path / "pivots.xlsx"
    write_xlsx(workbook, path)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert sum(name.startswith("xl/pivotTables/pivotTable") and name.endswith(".xml") for name in names) == 2
        definition = archive.read("xl/pivotCache/pivotCacheDefinition1.xml").decode()
        assert 'refreshOnLoad="1"' in definition and '<worksheetSource name="SalesTable"/>' in definition
        assert 'groupBy="years"' in definition
        assert "<pivotCaches>" in archive.read("xl/workbook.xml").decode()
        content_types = archive.read("[Content_Types].xml").decode()
        assert content_types.count("pivotTable+xml") == 2
    loaded = read_xlsx(path)
    assert loaded.warnings == ()
    for sheet in workbook:
        assert [_comparable(spec) for spec in loaded.workbook.get_sheet(sheet.name).pivots] == [
            _comparable(spec) for spec in sheet.pivots
        ]


def test_workbook_saved_by_excel_reads_back_its_objects() -> None:
    from duddysheet.core.pivot import render_pivot

    loaded = read_xlsx(FIXTURE)
    assert loaded.warnings == ()
    workbook = loaded.workbook
    data = workbook.get_sheet("Data")
    assert [chart.chart_type for chart in data.charts] == ["column", "histogram", "pareto"]
    assert [chart.title for chart in data.charts] == ["Units by region", "Amounts", "Amount by product"]
    assert data.charts[2].source_range.to_a1() == "Data!B1:E7"
    assert sorted((item.row, item.column, item.kind) for item in data.sparklines) == [(7, 3, "column"), (7, 4, "column")]
    # Excel's hidden chart-data names are not imported as user names.
    assert not any(str(name).startswith("_xlchart") for name in getattr(workbook, "names", {}) or {})
    (spec,) = workbook.get_sheet("Report").pivots
    assert spec.name == "Sales" and spec.rows == ("Region",) and spec.page_fields == ("Product",)
    assert [(item.field, item.function, item.show_as) for item in spec.values] == [
        ("Amount", "sum", "normal"),
        ("Units", "average", "percent_of_grand_total"),
    ]
    assert spec.hidden_items == (("Region", ("West",)),)
    rendered = render_pivot(workbook, "Report", spec)
    report = workbook.get_sheet("Report")
    labels = {report.get_cell(row, 0).display_value: report.get_cell(row, 1).display_value for row in range(rendered.extent[0], rendered.extent[2] + 1)}
    assert labels["East"] == 204 and labels["North"] == 249 and labels["Grand Total"] == 453


def test_excel_saved_workbook_survives_another_save(tmp_path) -> None:
    first = read_xlsx(FIXTURE).workbook
    path = tmp_path / "again.xlsx"
    write_xlsx(first, path)
    second = read_xlsx(path)
    assert second.warnings == ()
    for sheet in first:
        again = second.workbook.get_sheet(sheet.name)
        assert [chart.chart_type for chart in again.charts] == [chart.chart_type for chart in sheet.charts]
        assert sorted(again.sparklines, key=lambda item: item.column) == sorted(sheet.sparklines, key=lambda item: item.column)
        assert [_comparable(spec) for spec in again.pivots] == [_comparable(spec) for spec in sheet.pivots]
