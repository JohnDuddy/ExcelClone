"""Charts in XLSX: native Excel charts written and read back.

Classic chart types go through openpyxl's chart objects. Excel 2016 chart
types (histogram, Pareto, box and whisker, waterfall, funnel, treemap, and
sunburst) are ``chartEx`` parts that openpyxl cannot write or read, so they
are added to the saved package and parsed from it here.
"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, replace
from typing import Any

from openpyxl.chart import (
    AreaChart,
    AreaChart3D,
    BarChart,
    BarChart3D,
    BubbleChart,
    DoughnutChart,
    LineChart,
    LineChart3D,
    PieChart,
    PieChart3D,
    ProjectedPieChart,
    RadarChart,
    ScatterChart,
    StockChart,
    SurfaceChart,
    SurfaceChart3D,
)
from openpyxl.chart.axis import ChartLines, DisplayUnitsLabelList
from openpyxl.chart.data_source import AxDataSource, NumDataSource, NumRef, StrRef
from openpyxl.chart.error_bar import ErrorBars
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.marker import Marker
from openpyxl.chart.plotarea import DataTable
from openpyxl.chart.series import Series, SeriesLabel, XYSeries
from openpyxl.chart.trendline import Trendline
from openpyxl.chart.updown_bars import UpDownBars
from openpyxl.chart.data_source import NumFmt
from openpyxl.utils import get_column_letter

from duddysheet.core.chart import STOCK_COLUMNS, ChartSpec
from duddysheet.core.refs import CellReference, RangeReference, parse_a1
from duddysheet.io.xlsx_package import (
    RELATIONSHIPS_NS,
    XlsxPackage,
    anchor_bounds,
    drawing_anchors,
    quote_sheet,
    two_cell_anchor,
    xml_text,
)

CHARTEX_TYPES = frozenset({"histogram", "pareto", "box", "waterfall", "funnel", "treemap", "sunburst"})
UNSUPPORTED_TYPES = {"heatmap": "Heatmap"}
APPROXIMATED_TYPES = {"step": ("Step Line", "Line")}
CHART_WIDTH_COLUMNS = 8
CHART_HEIGHT_ROWS = 16
CHARTEX_REL = "http://schemas.microsoft.com/office/2014/relationships/chartEx"
CHARTEX_CONTENT_TYPE = "application/vnd.ms-office.chartex+xml"
CX_NS = "http://schemas.microsoft.com/office/drawing/2014/chartex"
_LEGEND = {"right": "r", "left": "l", "top": "t", "bottom": "b"}
_LEGEND_BACK = {value: key for key, value in _LEGEND.items()}
_LABEL_POSITIONS = {"center": "ctr", "inside_end": "inEnd", "inside_base": "inBase", "outside_end": "outEnd"}
_NUMBER_FORMATS = {"number": "#,##0.00", "currency": "$#,##0.00", "percent": "0%"}
_TRENDLINES = {
    "linear": "linear",
    "exponential": "exp",
    "logarithmic": "log",
    "polynomial": "poly",
    "power": "power",
    "moving_average": "movingAvg",
}
_ERROR_TYPES = {
    "standard_error": "stdErr",
    "percentage": "percentage",
    "standard_deviation": "stdDev",
    "fixed": "fixedVal",
}
_EMPTY = {"gaps": "gap", "zero": "zero", "connect": "span"}
_BAR_TYPES = {
    "column": ("col", "clustered", False),
    "stacked_column": ("col", "stacked", False),
    "stacked_column_100": ("col", "percentStacked", False),
    "column_3d_clustered": ("col", "clustered", True),
    "column_3d_stacked": ("col", "stacked", True),
    "column_3d_stacked_100": ("col", "percentStacked", True),
    "column_3d": ("col", "standard", True),
    "bar": ("bar", "clustered", False),
    "stacked_bar": ("bar", "stacked", False),
    "stacked_bar_100": ("bar", "percentStacked", False),
    "bar_3d_clustered": ("bar", "clustered", True),
    "bar_3d_stacked": ("bar", "stacked", True),
    "bar_3d_stacked_100": ("bar", "percentStacked", True),
}
_LINE_TYPES = {
    "line_plain": ("standard", False, False),
    "stacked_line": ("stacked", False, False),
    "stacked_line_100": ("percentStacked", False, False),
    "line": ("standard", True, False),
    "stacked_line_markers": ("stacked", True, False),
    "stacked_line_100_markers": ("percentStacked", True, False),
    "line_3d": ("standard", False, True),
    "step": ("standard", False, False),
}
_AREA_TYPES = {
    "area": ("standard", False),
    "stacked_area": ("stacked", False),
    "stacked_area_100": ("percentStacked", False),
    "area_3d": ("standard", True),
    "area_3d_stacked": ("stacked", True),
    "area_3d_stacked_100": ("percentStacked", True),
}
# scatterStyle, markers, line, smooth
_SCATTER_TYPES = {
    "scatter": ("lineMarker", True, False, False),
    "scatter_smooth_markers": ("smoothMarker", True, True, True),
    "scatter_smooth": ("smoothMarker", False, True, True),
    "scatter_lines_markers": ("lineMarker", True, True, False),
    "scatter_lines": ("lineMarker", False, True, False),
}


@dataclass(frozen=True, slots=True)
class _Layout:
    """Where a chart's categories, series names, and values live on the sheet."""

    sheet: str
    header_row: int | None
    first_row: int
    last_row: int
    category_column: int | None
    series_columns: tuple[int, ...]


def xlsx_chart_warnings(workbook: Any) -> tuple[str, ...]:
    """Explain charts that Excel cannot show exactly as Duddy Spreadsheet does."""
    warnings: list[str] = []
    for sheet in workbook:
        for chart in sheet.charts:
            if not isinstance(chart, ChartSpec):
                continue
            if chart.chart_type in UNSUPPORTED_TYPES:
                warnings.append(
                    f"Excel has no {UNSUPPORTED_TYPES[chart.chart_type]} chart; "
                    f"the chart {chart.title or 'untitled'!r} on {sheet.name!r} was not saved to .xlsx."
                )
            elif chart.chart_type in APPROXIMATED_TYPES:
                label, saved = APPROXIMATED_TYPES[chart.chart_type]
                warnings.append(
                    f"Excel has no {label} chart; {chart.title or 'the chart'!r} on {sheet.name!r} was saved as a {saved} chart."
                )
    return tuple(warnings)


def chart_anchor(sheet: Any, spec: ChartSpec, index: int) -> tuple[int, int]:
    """Return the zero-based top-left cell where a chart is placed in Excel."""
    source = spec.source_range
    used_column = max((column for (_row, column), _cell in sheet.iter_populated()), default=0)
    column = max(source.max_column, min(used_column, source.max_column + 12)) + 2
    return source.min_row + index * (CHART_HEIGHT_ROWS + 1), column


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
def write_charts(source_sheet: Any, worksheet: Any, workbook: Any = None) -> list[tuple[ChartSpec, tuple[int, int]]]:
    """Add classic charts to ``worksheet``; return chartEx charts still to write."""
    pending: list[tuple[ChartSpec, tuple[int, int]]] = []
    for index, spec in enumerate(chart for chart in source_sheet.charts if isinstance(chart, ChartSpec)):
        if spec.chart_type in UNSUPPORTED_TYPES:
            continue
        if spec.pivot_name:
            spec = pivot_chart_range(workbook, spec)
        row, column = chart_anchor(source_sheet, spec, index)
        if spec.chart_type in CHARTEX_TYPES:
            pending.append((spec, (row, column)))
            continue
        try:
            chart = _classic_chart(_data_sheet(workbook, source_sheet, spec), spec)
        except (ValueError, IndexError):
            continue
        chart.width = CHART_WIDTH_COLUMNS * 1.69
        chart.height = CHART_HEIGHT_ROWS * 0.53
        worksheet.add_chart(chart, f"{get_column_letter(column + 1)}{row + 1}")
    return pending


def pivot_chart_range(workbook: Any, spec: ChartSpec) -> ChartSpec:
    """Point a PivotChart at its PivotTable's body: labels and values, no grand totals."""
    from duddysheet.core.pivot import compute_pivot, find_pivot

    pivot = find_pivot(workbook, spec.sheet_name, spec.pivot_name or "") if workbook is not None else None
    if pivot is None or pivot.extent is None:
        return spec
    result = compute_pivot(workbook, pivot)
    top, left, bottom, right = pivot.extent
    header_rows = 1 + len(pivot.columns) + (1 if len(pivot.values) > 1 else 0) if pivot.columns else 1
    first = top + result.table_top + header_rows - 1
    last = bottom - (1 if pivot.grand_total_rows else 0)
    last_column = right - (1 if pivot.columns and pivot.grand_total_columns else 0)
    if last <= first or last_column <= left:
        return spec
    source = RangeReference(CellReference(first, left, spec.sheet_name), CellReference(last, last_column, spec.sheet_name))
    return replace(spec, source_range=source, category_column=None, series_columns=None, has_headers=True)


def _data_sheet(workbook: Any, host: Any, spec: ChartSpec) -> Any:
    """Return the sheet holding a chart's data (a chart may plot another sheet)."""
    if workbook is not None and spec.sheet_name in workbook.sheet_names:
        return workbook.get_sheet(spec.sheet_name)
    return host


def _layout(sheet: Any, spec: ChartSpec) -> _Layout:
    target = spec.source_range
    header_row = target.min_row if spec.has_headers else None
    first_row = target.min_row + (1 if spec.has_headers else 0)
    if spec.chart_type in ("histogram", "box") and spec.category_column is None and spec.series_columns is None:
        columns = tuple(range(target.min_column, target.max_column + 1))
        return _Layout(sheet.name, header_row, first_row, target.max_row, None, columns)
    category = target.min_column if spec.category_column is None else spec.category_column
    columns = (
        tuple(column for column in range(target.min_column, target.max_column + 1) if column != category)
        if spec.series_columns is None
        else tuple(spec.series_columns)
    )
    if not columns:
        return _Layout(sheet.name, header_row, first_row, target.max_row, None, (category,))
    return _Layout(sheet.name, header_row, first_row, target.max_row, category, columns)


def _ref(sheet: str, column: int, top: int, bottom: int | None = None, right: int | None = None) -> str:
    start = f"${get_column_letter(column + 1)}${top + 1}"
    last_column = column if right is None else right
    last_row = top if bottom is None else bottom
    if (last_column, last_row) == (column, top):
        return f"{quote_sheet(sheet)}!{start}"
    return f"{quote_sheet(sheet)}!{start}:${get_column_letter(last_column + 1)}${last_row + 1}"


def _is_text(sheet: Any, column: int, rows: range) -> bool:
    return any(isinstance(sheet.get_cell(row, column).display_value, str) for row in rows)


def _series_list(sheet: Any, spec: ChartSpec, layout: _Layout, *, xy: bool = False) -> list[Series]:
    """Build openpyxl series from the layout, honoring Switch Row/Column."""
    result: list[Series] = []
    rows = range(layout.first_row, layout.last_row + 1)
    columns = layout.series_columns
    contiguous = columns == tuple(range(columns[0], columns[-1] + 1))
    if spec.switch_row_column and contiguous and not xy and layout.category_column is not None:
        for row in rows:
            series = Series()
            series.val = NumDataSource(numRef=NumRef(f=_ref(layout.sheet, columns[0], row, row, columns[-1])))
            series.tx = SeriesLabel(strRef=StrRef(f=_ref(layout.sheet, layout.category_column, row)))
            if layout.header_row is not None:
                series.cat = AxDataSource(strRef=StrRef(f=_ref(layout.sheet, columns[0], layout.header_row, layout.header_row, columns[-1])))
            result.append(series)
    else:
        for column in columns:
            series = XYSeries() if xy else Series()
            series.val = NumDataSource(numRef=NumRef(f=_ref(layout.sheet, column, layout.first_row, layout.last_row)))
            if layout.header_row is not None:
                series.tx = SeriesLabel(strRef=StrRef(f=_ref(layout.sheet, column, layout.header_row)))
            if layout.category_column is not None:
                reference = _ref(layout.sheet, layout.category_column, layout.first_row, layout.last_row)
                if xy:
                    series.xVal = AxDataSource(numRef=NumRef(f=reference))
                elif _is_text(sheet, layout.category_column, rows):
                    series.cat = AxDataSource(strRef=StrRef(f=reference))
                else:
                    series.cat = AxDataSource(numRef=NumRef(f=reference))
            if xy:
                series.yVal = series.val
            result.append(series)
    for index, series in enumerate(result):
        series.idx = index
        series.order = index
    return result


def _classic_chart(sheet: Any, spec: ChartSpec) -> Any:
    layout = _layout(sheet, spec)
    kind = spec.chart_type
    if kind in _BAR_TYPES:
        direction, grouping, three_d = _BAR_TYPES[kind]
        chart = BarChart3D() if three_d else BarChart()
        chart.type = direction
        chart.grouping = grouping
        if grouping in ("stacked", "percentStacked"):
            chart.overlap = 100
        elif not three_d:
            chart.overlap = spec.series_overlap
        chart.gapWidth = spec.gap_width if spec.gap_width else 150
        chart.series = _series_list(sheet, spec, layout)
    elif kind in _LINE_TYPES:
        grouping, markers, three_d = _LINE_TYPES[kind]
        chart = LineChart3D() if three_d else LineChart()
        chart.grouping = grouping
        chart.series = _series_list(sheet, spec, layout)
        for series in chart.series:
            series.marker = Marker(symbol="circle" if markers else "none")
            series.smooth = bool(spec.smooth_lines)
        if not three_d:
            if spec.drop_lines:
                chart.dropLines = ChartLines()
            if spec.high_low_lines:
                chart.hiLowLines = ChartLines()
            if spec.up_down_bars:
                chart.upDownBars = UpDownBars(gapWidth=150)
    elif kind in _AREA_TYPES:
        grouping, three_d = _AREA_TYPES[kind]
        chart = AreaChart3D() if three_d else AreaChart()
        chart.grouping = grouping
        chart.series = _series_list(sheet, spec, layout)
    elif kind in _SCATTER_TYPES:
        style, markers, line, smooth = _SCATTER_TYPES[kind]
        chart = ScatterChart(scatterStyle=style)
        chart.series = _series_list(sheet, spec, layout, xy=True)
        for series in chart.series:
            series.marker = Marker(symbol="circle" if markers else "none")
            if not line:
                series.graphicalProperties.line.noFill = True
            series.smooth = smooth
    elif kind in ("bubble", "bubble_3d"):
        chart = BubbleChart()
        chart.series = _bubble_series(layout)
        for series in chart.series:
            series.bubble3D = kind == "bubble_3d"
    elif kind in ("pie", "pie_3d", "pie_of_pie", "bar_of_pie", "donut"):
        if kind == "donut":
            chart = DoughnutChart(holeSize=spec.hole_size, firstSliceAng=spec.first_slice_angle)
            chart.series = _series_list(sheet, spec, layout)
        else:
            if kind == "pie":
                chart = PieChart(firstSliceAng=spec.first_slice_angle)
            elif kind == "pie_3d":
                chart = PieChart3D()
            else:
                chart = ProjectedPieChart(
                    ofPieType="pie" if kind == "pie_of_pie" else "bar",
                    splitType="pos",
                    splitPos=spec.split_count,
                )
            chart.series = _series_list(sheet, spec, layout)[:1]
            for series in chart.series:
                if spec.pie_explosion:
                    series.explosion = spec.pie_explosion
    elif kind in STOCK_COLUMNS:
        chart = _stock_chart(sheet, spec, layout)
    elif kind in ("surface_3d", "surface_wireframe", "contour", "contour_wireframe"):
        chart = SurfaceChart3D() if kind.startswith("surface") else SurfaceChart()
        chart.wireframe = kind.endswith("wireframe")
        chart.series = _series_list(sheet, spec, layout)
    elif kind in ("radar", "radar_markers", "radar_filled"):
        chart = RadarChart(radarStyle="filled" if kind == "radar_filled" else "marker")
        chart.series = _series_list(sheet, spec, layout)
        for series in chart.series:
            series.marker = Marker(symbol="none" if kind == "radar" else "circle")
    elif kind.startswith("combo"):
        chart = _combo_chart(sheet, spec, layout)
    else:
        raise ValueError(f"No Excel chart for {kind!r}")
    _apply_options(chart, spec)
    return chart


def _bubble_series(layout: _Layout) -> list[Series]:
    result = []
    columns = layout.series_columns
    for position in range(0, len(columns), 2):
        series = XYSeries()
        y_column = columns[position]
        series.yVal = NumDataSource(numRef=NumRef(f=_ref(layout.sheet, y_column, layout.first_row, layout.last_row)))
        size_column = columns[position + 1] if position + 1 < len(columns) else y_column
        series.bubbleSize = NumDataSource(numRef=NumRef(f=_ref(layout.sheet, size_column, layout.first_row, layout.last_row)))
        if layout.category_column is not None:
            series.xVal = AxDataSource(numRef=NumRef(f=_ref(layout.sheet, layout.category_column, layout.first_row, layout.last_row)))
        if layout.header_row is not None:
            series.tx = SeriesLabel(strRef=StrRef(f=_ref(layout.sheet, y_column, layout.header_row)))
        series.idx = series.order = len(result)
        result.append(series)
    return result


def _stock_chart(sheet: Any, spec: ChartSpec, layout: _Layout) -> Any:
    names = STOCK_COLUMNS[spec.chart_type]
    series = _series_list(sheet, replace(spec, switch_row_column=False), layout)[: len(names)]
    if len(series) < len(names):
        raise ValueError("Stock chart needs one column per price")
    has_volume = names[0] == "Volume"
    prices = series[1:] if has_volume else series
    stock = StockChart()
    stock.series = prices
    for index, item in enumerate(prices):
        item.idx = item.order = index + (1 if has_volume else 0)
        item.graphicalProperties.line.noFill = True
        item.marker = Marker(symbol="none")
    if names[-1] == "Close" and "Open" not in names:
        prices[-1].marker = Marker(symbol="dash", size=6)
    stock.hiLowLines = ChartLines()
    if "Open" in names:
        stock.upDownBars = UpDownBars(gapWidth=150)
    if not has_volume:
        return stock
    volume = BarChart()
    volume.series = series[:1]
    volume.y_axis.title = "Volume"
    stock.y_axis.axId = 200
    stock.y_axis.crosses = "max"
    stock.y_axis.majorGridlines = None
    stock.y_axis.delete = False
    volume += stock
    return volume


def _combo_plan(spec: ChartSpec, count: int) -> tuple[list[str], set[int]]:
    if spec.chart_type == "combo_area_column":
        split = max(1, count // 2)
        return ["area"] * split + ["column"] * (count - split), set()
    if spec.chart_type == "combo_custom":
        kinds = list(spec.combo_series_types or ())
        defaults = ["column"] + ["line"] * max(0, count - 1)
        kinds = (kinds + defaults[len(kinds):])[:count]
        return kinds, {number - 1 for number in spec.secondary_series if number <= count}
    kinds = ["column"] + ["line"] * (count - 1)
    secondary = set(range(1, count)) if spec.chart_type == "combo_secondary" or spec.secondary_axis else set()
    return kinds, secondary


def _combo_chart(sheet: Any, spec: ChartSpec, layout: _Layout) -> Any:
    series = _series_list(sheet, spec, layout)
    kinds, secondary = _combo_plan(spec, len(series))
    groups: dict[tuple[str, bool], Any] = {}
    for index, (item, kind) in enumerate(zip(series, kinds)):
        key = (kind, index in secondary)
        if key not in groups:
            if kind == "column":
                chart = BarChart()
                chart.type = "col"
                chart.grouping = "clustered"
            elif kind == "area":
                chart = AreaChart()
                chart.grouping = "stacked" if spec.chart_type == "combo_area_column" else "standard"
            else:
                chart = LineChart()
            if key[1]:
                chart.y_axis.axId = 200
                chart.y_axis.crosses = "max"
                chart.y_axis.majorGridlines = None
                chart.y_axis.delete = False
            groups[key] = chart
        if kind == "line":
            item.marker = Marker(symbol="none")
        groups[key].series.append(item)
    ordered = sorted(groups.items(), key=lambda entry: (entry[0][1], {"area": 0, "column": 1, "line": 2}[entry[0][0]]))
    primary = ordered[0][1]
    for _key, chart in ordered[1:]:
        primary += chart
    return primary


def _apply_options(chart: Any, spec: ChartSpec) -> None:
    kind = spec.chart_type
    pie = kind in ("pie", "pie_3d", "pie_of_pie", "bar_of_pie", "donut")
    if spec.title:
        chart.title = spec.title
    if spec.legend_position == "none":
        chart.legend = None
    else:
        chart.legend.position = _LEGEND[spec.legend_position]
    chart.display_blanks = _EMPTY[spec.empty_cells]
    if spec.show_data_labels:
        labels = DataLabelList()
        content = spec.data_label_content
        labels.showVal = content in ("value", "category_value")
        labels.showPercent = content == "percent" and pie
        labels.showCatName = content in ("category", "category_value")
        labels.showSerName = content == "series"
        labels.showLegendKey = False
        if spec.data_label_position != "auto" and (kind in _BAR_TYPES and not _BAR_TYPES[kind][2] or kind in ("pie", "pie_of_pie", "bar_of_pie")):
            position = _LABEL_POSITIONS[spec.data_label_position]
            if not (pie and position == "inBase"):
                labels.dLblPos = position
        chart.dataLabels = labels
    if pie:
        return
    _apply_axes(chart, spec)
    two_d = kind in ("column", "bar", "line", "line_plain", "area", "step") or kind in _SCATTER_TYPES or kind in ("bubble",) or kind.startswith("combo")
    unstacked = kind in ("column", "bar", "line", "line_plain", "step") or kind in _SCATTER_TYPES
    for series in _all_series(chart):
        if spec.show_trendline and unstacked:
            series.trendline = Trendline(
                trendlineType=_TRENDLINES[spec.trendline_type],
                order=spec.trendline_order if spec.trendline_type == "polynomial" else None,
                period=spec.trendline_order if spec.trendline_type == "moving_average" else None,
                forward=spec.trendline_forward or None,
                backward=spec.trendline_backward or None,
                dispEq=spec.show_equation,
                dispRSqr=spec.show_r_squared,
            )
        if spec.error_bars != "none" and two_d:
            series.errBars = ErrorBars(
                errDir="y" if kind in _SCATTER_TYPES or kind == "bubble" else None,
                errBarType="both",
                errValType=_ERROR_TYPES[spec.error_bars],
                val=None if spec.error_bars == "standard_error" else spec.effective_error_amount,
            )
    if spec.show_data_table and (kind in _BAR_TYPES or kind in _LINE_TYPES or kind in _AREA_TYPES or kind.startswith("combo")):
        chart.plot_area.dTable = DataTable(showHorzBorder=True, showVertBorder=True, showOutline=True, showKeys=True)


def _apply_axes(chart: Any, spec: ChartSpec) -> None:
    x_axis, y_axis = chart.x_axis, chart.y_axis
    x_axis.delete = not spec.show_x_axis
    y_axis.delete = not spec.show_y_axis
    if spec.x_axis_title:
        x_axis.title = spec.x_axis_title
    if spec.y_axis_title:
        y_axis.title = spec.y_axis_title
    y_axis.majorGridlines = ChartLines() if spec.show_grid else None
    if spec.minor_gridlines:
        y_axis.minorGridlines = ChartLines()
    if spec.vertical_gridlines:
        x_axis.majorGridlines = ChartLines()
    if spec.axis_min is not None:
        y_axis.scaling.min = spec.axis_min
    if spec.axis_max is not None:
        y_axis.scaling.max = spec.axis_max
    if spec.major_unit is not None:
        y_axis.majorUnit = spec.major_unit
    if spec.log_scale:
        y_axis.scaling.logBase = 10
    if spec.reverse_categories:
        x_axis.scaling.orientation = "maxMin"
    if spec.display_units != "none":
        y_axis.dispUnits = DisplayUnitsLabelList(builtInUnit=spec.display_units)
    if spec.number_format in _NUMBER_FORMATS:
        y_axis.numFmt = NumFmt(formatCode=_NUMBER_FORMATS[spec.number_format], sourceLinked=False)
    for extra in chart._charts[1:]:
        extra.x_axis.delete = x_axis.delete
        if extra.y_axis.axId != y_axis.axId:
            extra.y_axis.delete = not spec.show_y_axis


def _all_series(chart: Any) -> list[Any]:
    return [series for part in chart._charts for series in part.series]


# ---------------------------------------------------------------------------
# chartEx (Office 2016 chart types)
# ---------------------------------------------------------------------------
def add_chartex_charts(package: XlsxPackage, workbook: Any, pending: dict[str, list[tuple[ChartSpec, tuple[int, int]]]]) -> None:
    """Write Office 2016 chart parts for the charts openpyxl cannot write."""
    sheet_parts = package.sheet_parts()
    for sheet_name, charts in pending.items():
        if not charts:
            continue
        host = workbook.get_sheet(sheet_name)
        drawing = package.drawing_for(sheet_parts[sheet_name])
        for spec, (row, column) in charts:
            xml = chartex_xml(_data_sheet(workbook, host, spec), spec)
            if xml is None:
                continue
            part = package.next_part("xl/charts/chartEx{}.xml")
            package.set_text(part, xml)
            package.add_override(part, CHARTEX_CONTENT_TYPE)
            _add_chart_style_parts(package, part)
            rel_id = package.add_relationship(drawing, CHARTEX_REL, part)
            shape_id = package.next_shape_id(drawing)
            package.add_anchor(
                drawing,
                two_cell_anchor(
                    column,
                    row,
                    column + CHART_WIDTH_COLUMNS,
                    row + CHART_HEIGHT_ROWS,
                    _chartex_frame(shape_id, spec.title or f"Chart {shape_id}", rel_id),
                ),
            )


_STYLE_ELEMENTS = (
    ("axisTitle", "", "text"),
    ("categoryAxis", "", "axis"),
    ("chartArea", ' mods="allowNoFillOverride allowNoLineOverride"', "area"),
    ("dataLabel", "", "text"),
    ("dataLabelCallout", "", "text"),
    ("dataPoint", "", "fill"),
    ("dataPoint3D", "", "fill"),
    ("dataPointLine", "", "line"),
    ("dataPointMarker", "", "fill"),
    ("dataPointMarkerLayout", ' symbol="circle" size="5"', "empty"),
    ("dataPointWireframe", "", "line"),
    ("dataTable", "", "text"),
    ("downBar", "", "fill"),
    ("dropLine", "", "grid"),
    ("errorBar", "", "grid"),
    ("floor", "", "plain"),
    ("gridlineMajor", "", "grid"),
    ("gridlineMinor", "", "grid"),
    ("hiLoLine", "", "grid"),
    ("leaderLine", "", "grid"),
    ("legend", "", "text"),
    ("plotArea", ' mods="allowNoFillOverride allowNoLineOverride"', "plain"),
    ("plotArea3D", ' mods="allowNoFillOverride allowNoLineOverride"', "plain"),
    ("seriesAxis", "", "axis"),
    ("seriesLine", "", "grid"),
    ("title", "", "text"),
    ("trendline", "", "line"),
    ("trendlineLabel", "", "text"),
    ("upBar", "", "fill"),
    ("valueAxis", "", "text"),
    ("wall", "", "plain"),
)
_GRAY_LINE = '<a:ln w="9525"><a:solidFill><a:srgbClr val="D9D9D9"/></a:solidFill></a:ln>'


def chart_style_xml() -> str:
    """Return a chart style part (Excel requires one beside every chartEx)."""
    refs = (
        '<cs:lnRef idx="0"/><cs:fillRef idx="0"/><cs:effectRef idx="0"/>'
        '<cs:fontRef idx="minor"><a:schemeClr val="tx1"><a:lumMod val="65000"/><a:lumOff val="35000"/></a:schemeClr></cs:fontRef>'
    )
    bodies = {
        "text": refs + '<cs:defRPr sz="900"/>',
        "axis": refs + f"<cs:spPr>{_GRAY_LINE}</cs:spPr>" + '<cs:defRPr sz="900"/>',
        "area": refs + f'<cs:spPr><a:solidFill><a:schemeClr val="bg1"/></a:solidFill>{_GRAY_LINE}</cs:spPr><cs:defRPr sz="1000"/>',
        "fill": refs.replace('<cs:fillRef idx="0"/>', '<cs:fillRef idx="0"><cs:styleClr val="auto"/></cs:fillRef>')
        + '<cs:spPr><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></cs:spPr>',
        "line": refs.replace('<cs:lnRef idx="0"/>', '<cs:lnRef idx="0"><cs:styleClr val="auto"/></cs:lnRef>')
        + '<cs:spPr><a:ln w="28575" cap="rnd"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln></cs:spPr>',
        "grid": refs + f"<cs:spPr>{_GRAY_LINE}</cs:spPr>",
        "plain": refs,
        "empty": "",
    }
    elements = "".join(
        f"<cs:{name}{attributes}/>" if kind == "empty" else f"<cs:{name}{attributes}>{bodies[kind]}</cs:{name}>"
        for name, attributes, kind in _STYLE_ELEMENTS
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<cs:chartStyle xmlns:cs="http://schemas.microsoft.com/office/drawing/2012/chartStyle" '
        f'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" id="366">{elements}</cs:chartStyle>'
    )


def chart_colors_xml() -> str:
    """Return a chart color style part cycling through the theme accents."""
    accents = "".join(f'<a:schemeClr val="accent{index}"/>' for index in range(1, 7))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<cs:colorStyle xmlns:cs="http://schemas.microsoft.com/office/drawing/2012/chartStyle" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" meth="cycle" id="10">'
        f'{accents}<cs:variation/><cs:variation><a:lumMod val="60000"/></cs:variation></cs:colorStyle>'
    )


def _add_chart_style_parts(package: XlsxPackage, chart_part: str) -> None:
    style = package.next_part("xl/charts/style{}.xml")
    package.set_text(style, chart_style_xml())
    package.add_override(style, "application/vnd.ms-office.chartstyle+xml")
    colors = package.next_part("xl/charts/colors{}.xml")
    package.set_text(colors, chart_colors_xml())
    package.add_override(colors, "application/vnd.ms-office.chartcolorstyle+xml")
    package.add_relationship(chart_part, "http://schemas.microsoft.com/office/2011/relationships/chartStyle", style)
    package.add_relationship(chart_part, "http://schemas.microsoft.com/office/2011/relationships/chartColorStyle", colors)


def _chartex_frame(shape_id: int, name: str, rel_id: str) -> str:
    return (
        '<mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
        '<mc:Choice xmlns:cx1="http://schemas.microsoft.com/office/drawing/2015/9/8/chartex" Requires="cx1">'
        f'<xdr:graphicFrame macro=""><xdr:nvGraphicFramePr><xdr:cNvPr id="{shape_id}" name="{xml_text(name)}"/>'
        "<xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr>"
        '<xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm>'
        f'<a:graphic><a:graphicData uri="{CX_NS}">'
        f'<cx:chart xmlns:cx="{CX_NS}" r:id="{rel_id}"/></a:graphicData></a:graphic></xdr:graphicFrame>'
        "</mc:Choice><mc:Fallback>"
        f'<xdr:sp macro="" textlink=""><xdr:nvSpPr><xdr:cNvPr id="{shape_id + 1000}" name="{xml_text(name)} fallback"/>'
        '<xdr:cNvSpPr><a:spLocks noTextEdit="1"/></xdr:cNvSpPr></xdr:nvSpPr>'
        '<xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="4572000" cy="2743200"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>'
        '<xdr:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US" sz="1100"/>'
        "<a:t>This chart needs Excel 2016 or later.</a:t></a:r></a:p></xdr:txBody></xdr:sp>"
        "</mc:Fallback></mc:AlternateContent>"
    )


def _points(values: list[Any], numeric: bool) -> str:
    parts = []
    for index, value in enumerate(values):
        if numeric:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                continue
            parts.append(f'<cx:pt idx="{index}">{value!r}</cx:pt>')
        else:
            parts.append(f'<cx:pt idx="{index}">{xml_text("" if value is None else value)}</cx:pt>')
    return "".join(parts)


def _num_dim(dim_type: str, reference: str, values: list[Any]) -> str:
    return (
        f'<cx:numDim type="{dim_type}"><cx:f>{xml_text(reference)}</cx:f>'
        f'<cx:lvl ptCount="{len(values)}" formatCode="General">{_points(values, True)}</cx:lvl></cx:numDim>'
    )


def _str_dim(reference: str, levels: list[list[Any]]) -> str:
    body = "".join(f'<cx:lvl ptCount="{len(level)}">{_points(level, False)}</cx:lvl>' for level in levels)
    return f'<cx:strDim type="cat"><cx:f>{xml_text(reference)}</cx:f>{body}</cx:strDim>'


def _series_name(sheet: Any, layout: _Layout, column: int, fallback: str) -> str:
    if layout.header_row is None:
        return f"<cx:tx><cx:txData><cx:v>{xml_text(fallback)}</cx:v></cx:txData></cx:tx>"
    value = sheet.get_cell(layout.header_row, column).display_value
    name = fallback if value in (None, "") else str(value)
    return (
        f"<cx:tx><cx:txData><cx:f>{xml_text(_ref(layout.sheet, column, layout.header_row))}</cx:f>"
        f"<cx:v>{xml_text(name)}</cx:v></cx:txData></cx:tx>"
    )


def _column_values(sheet: Any, column: int, layout: _Layout) -> list[Any]:
    return [sheet.get_cell(row, column).display_value for row in range(layout.first_row, layout.last_row + 1)]


def _labels(spec: ChartSpec) -> str:
    if not spec.show_data_labels:
        return ""
    content = spec.data_label_content
    return (
        '<cx:dataLabels pos="outEnd"><cx:visibility '
        f'seriesName="{int(content == "series")}" categoryName="{int(content in ("category", "category_value"))}" '
        f'value="{int(content in ("value", "category_value", "percent"))}"/></cx:dataLabels>'
    )


def chartex_xml(sheet: Any, spec: ChartSpec) -> str | None:
    """Return the chartEx part for an Office 2016 chart type, or ``None``."""
    layout = _layout(sheet, spec)
    kind = spec.chart_type
    uid = lambda index: "{" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"{spec.chart_id}-{index}")).upper() + "}"  # noqa: E731
    data: list[str] = []
    series: list[str] = []
    axes = ""
    if kind in ("treemap", "sunburst"):
        target = spec.source_range
        value_column = spec.series_columns[0] if spec.series_columns else target.max_column
        level_columns = [column for column in range(target.min_column, target.max_column + 1) if column != value_column]
        if not level_columns or level_columns != list(range(level_columns[0], level_columns[-1] + 1)):
            return None
        levels = [_column_values(sheet, column, layout) for column in reversed(level_columns)]
        reference = _ref(layout.sheet, level_columns[0], layout.first_row, layout.last_row, level_columns[-1])
        values = _column_values(sheet, value_column, layout)
        data.append(
            '<cx:data id="0">'
            + _str_dim(reference, levels)
            + _num_dim("size", _ref(layout.sheet, value_column, layout.first_row, layout.last_row), values)
            + "</cx:data>"
        )
        layout_pr = (
            '<cx:layoutPr><cx:parentLabelLayout val="overlapping"/></cx:layoutPr>' if kind == "treemap" else ""
        )
        series.append(
            f'<cx:series layoutId="{kind}" uniqueId="{uid(0)}">{_series_name(sheet, layout, value_column, "Series1")}'
            f"{_labels(spec) or '<cx:dataLabels pos=\"inEnd\"><cx:visibility seriesName=\"0\" categoryName=\"1\" value=\"0\"/></cx:dataLabels>'}"
            f'<cx:dataId val="0"/>{layout_pr}</cx:series>'
        )
    elif kind in ("histogram", "box"):
        columns = layout.series_columns if kind == "box" else layout.series_columns[:1]
        for index, column in enumerate(columns):
            values = _column_values(sheet, column, layout)
            data.append(
                f'<cx:data id="{index}">'
                + _num_dim("val", _ref(layout.sheet, column, layout.first_row, layout.last_row), values)
                + "</cx:data>"
            )
            if kind == "histogram":
                binning = (
                    f'<cx:binning intervalClosed="r"><cx:binCount val="{spec.bin_count}"/></cx:binning>'
                    if spec.bin_count
                    else '<cx:binning intervalClosed="r"/>'
                )
                body = f'<cx:layoutPr>{binning}</cx:layoutPr>'
                layout_id = "clusteredColumn"
            else:
                body = (
                    '<cx:layoutPr><cx:visibility meanLine="0" meanMarker="1" nonoutliers="0" outliers="1"/>'
                    '<cx:statistics quartileMethod="exclusive"/></cx:layoutPr>'
                )
                layout_id = "boxWhisker"
            series.append(
                f'<cx:series layoutId="{layout_id}" uniqueId="{uid(index)}">'
                f"{_series_name(sheet, layout, column, f'Series{index + 1}')}{_labels(spec)}"
                f'<cx:dataId val="{index}"/>{body}</cx:series>'
            )
        gap = "0" if kind == "histogram" else "1"
        axes = _chartex_axes(spec, gap)
    else:
        if layout.category_column is None:
            return None
        column = layout.series_columns[0]
        categories = _column_values(sheet, layout.category_column, layout)
        values = _column_values(sheet, column, layout)
        data.append(
            '<cx:data id="0">'
            + _str_dim(_ref(layout.sheet, layout.category_column, layout.first_row, layout.last_row), [categories])
            + _num_dim("val", _ref(layout.sheet, column, layout.first_row, layout.last_row), values)
            + "</cx:data>"
        )
        name = _series_name(sheet, layout, column, "Series1")
        if kind == "pareto":
            series.append(
                f'<cx:series layoutId="clusteredColumn" uniqueId="{uid(0)}">{name}{_labels(spec)}'
                '<cx:dataId val="0"/><cx:layoutPr><cx:aggregation/></cx:layoutPr><cx:axisId val="1"/></cx:series>'
                f'<cx:series layoutId="paretoLine" ownerIdx="0" uniqueId="{uid(1)}"><cx:axisId val="2"/></cx:series>'
            )
            axes = (
                _chartex_axes(spec, "0")
                + '<cx:axis id="2"><cx:valScaling max="1" min="0"/><cx:units unit="percentage"/><cx:tickLabels/></cx:axis>'
            )
        elif kind == "waterfall":
            series.append(
                f'<cx:series layoutId="waterfall" uniqueId="{uid(0)}">{name}'
                f"{_labels(spec) or '<cx:dataLabels pos=\"outEnd\"><cx:visibility seriesName=\"0\" categoryName=\"0\" value=\"1\"/></cx:dataLabels>'}"
                '<cx:dataId val="0"/><cx:layoutPr/></cx:series>'
            )
            axes = _chartex_axes(spec, "0.5")
        else:
            series.append(
                f'<cx:series layoutId="funnel" uniqueId="{uid(0)}">{name}'
                f"{_labels(spec) or '<cx:dataLabels pos=\"inEnd\"><cx:visibility seriesName=\"0\" categoryName=\"0\" value=\"1\"/></cx:dataLabels>'}"
                '<cx:dataId val="0"/></cx:series>'
            )
            axes = '<cx:axis id="0"><cx:catScaling gapWidth="0.06"/><cx:tickLabels/></cx:axis>'
    title = (
        f'<cx:title pos="t" align="ctr" overlay="0"><cx:tx><cx:txData><cx:v>{xml_text(spec.title)}</cx:v>'
        "</cx:txData></cx:tx></cx:title>"
        if spec.title
        else ""
    )
    legend = (
        ""
        if spec.legend_position == "none" or kind in ("histogram", "pareto", "waterfall", "funnel", "treemap")
        else f'<cx:legend pos="{_LEGEND[spec.legend_position]}" align="ctr" overlay="0"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<cx:chartSpace xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        f'xmlns:r="{RELATIONSHIPS_NS}" xmlns:cx="{CX_NS}">'
        f"<cx:chartData>{''.join(data)}</cx:chartData>"
        f"<cx:chart>{title}<cx:plotArea><cx:plotAreaRegion>{''.join(series)}</cx:plotAreaRegion>{axes}</cx:plotArea>"
        f"{legend}</cx:chart></cx:chartSpace>"
    )


def _chartex_axes(spec: ChartSpec, gap: str) -> str:
    category_title = (
        f"<cx:title><cx:tx><cx:txData><cx:v>{xml_text(spec.x_axis_title)}</cx:v></cx:txData></cx:tx></cx:title>"
        if spec.x_axis_title
        else ""
    )
    value_title = (
        f"<cx:title><cx:tx><cx:txData><cx:v>{xml_text(spec.y_axis_title)}</cx:v></cx:txData></cx:tx></cx:title>"
        if spec.y_axis_title
        else ""
    )
    hidden_x = ' hidden="1"' if not spec.show_x_axis else ""
    hidden_y = ' hidden="1"' if not spec.show_y_axis else ""
    gridlines = "<cx:majorGridlines/>" if spec.show_grid else ""
    return (
        f'<cx:axis id="0"{hidden_x}><cx:catScaling gapWidth="{gap}"/>{category_title}<cx:tickLabels/></cx:axis>'
        f'<cx:axis id="1"{hidden_y}><cx:valScaling/>{value_title}{gridlines}<cx:tickLabels/></cx:axis>'
    )


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def read_classic_chart(chart: Any, sheet_name: str, chart_id: str) -> ChartSpec | None:
    """Map an openpyxl chart read from a file back to a chart specification."""
    parts = list(getattr(chart, "_charts", None) or [chart])
    first = parts[0]
    tag = first.tagname
    series = [item for part in parts for item in part.series]
    if not series:
        return None
    chart_type = _classic_type(first, parts, series)
    if chart_type is None:
        return None
    refs: list[RangeReference] = []
    value_refs: list[RangeReference] = []
    title_refs: list[RangeReference] = []
    category_refs: list[RangeReference] = []
    for item in series:
        for source, bucket in (
            (_formula(item.val) or _formula(item.yVal), value_refs),
            (_formula(item.bubbleSize), value_refs),
            (_formula(item.cat) or _formula(item.xVal), category_refs),
            (item.tx.strRef.f if item.tx is not None and item.tx.strRef is not None else None, title_refs),
        ):
            reference = _range(source, sheet_name)
            if reference is not None:
                bucket.append(reference)
                refs.append(reference)
    sheets = {ref.sheet or sheet_name for ref in refs}
    if not value_refs or len(sheets) != 1:
        return None
    sheet_name = sheets.pop()
    switched = all(ref.min_row == ref.max_row for ref in value_refs) and any(ref.min_column != ref.max_column for ref in value_refs)
    min_row = min(ref.min_row for ref in refs)
    max_row = max(ref.max_row for ref in refs)
    min_column = min(ref.min_column for ref in refs)
    max_column = max(ref.max_column for ref in refs)
    has_headers = bool(title_refs) and (
        all(ref.min_row < min(value.min_row for value in value_refs) for ref in title_refs)
        if not switched
        else bool(category_refs)
    )
    category_column = None
    series_columns: tuple[int, ...] | None = None
    if not switched:
        if category_refs:
            category_column = category_refs[0].min_column
        columns = tuple(dict.fromkeys(ref.min_column for ref in value_refs))
        default = tuple(column for column in range(min_column, max_column + 1) if column != (category_column if category_column is not None else min_column))
        if columns != default:
            series_columns = columns
    title = _text(getattr(first, "title", None) or getattr(chart, "title", None))
    legend = getattr(chart, "legend", None)
    options: dict[str, Any] = {
        "title": title,
        "legend_position": "none" if legend is None else _LEGEND_BACK.get(legend.position or "r", "right"),
        "has_headers": has_headers,
        "category_column": category_column,
        "series_columns": series_columns,
        "switch_row_column": switched,
    }
    if tag not in ("pieChart", "pie3DChart", "ofPieChart", "doughnutChart"):
        x_axis, y_axis = first.x_axis, first.y_axis
        options.update(
            x_axis_title=_text(x_axis.title),
            y_axis_title=_text(y_axis.title),
            show_grid=y_axis.majorGridlines is not None,
            minor_gridlines=y_axis.minorGridlines is not None,
            vertical_gridlines=x_axis.majorGridlines is not None,
            show_x_axis=not bool(x_axis.delete),
            show_y_axis=not bool(y_axis.delete),
            log_scale=bool(y_axis.scaling.logBase),
            reverse_categories=x_axis.scaling.orientation == "maxMin",
        )
        if y_axis.scaling.min is not None and y_axis.scaling.max is not None and y_axis.scaling.min < y_axis.scaling.max:
            options.update(axis_min=y_axis.scaling.min, axis_max=y_axis.scaling.max)
        if y_axis.majorUnit:
            options["major_unit"] = y_axis.majorUnit
        units = getattr(y_axis, "dispUnits", None)
        if units is not None and units.builtInUnit in ("hundreds", "thousands", "millions", "billions"):
            options["display_units"] = units.builtInUnit
    if tag == "barChart" and first.grouping == "clustered":
        options["gap_width"] = int(first.gapWidth or 150)
        options["series_overlap"] = int(first.overlap or 0)
    if tag == "doughnutChart":
        options["hole_size"] = int(first.holeSize or 50)
    if tag in ("pieChart", "doughnutChart") and first.firstSliceAng:
        options["first_slice_angle"] = int(first.firstSliceAng)
    if tag == "ofPieChart" and first.splitPos:
        options["split_count"] = max(1, int(first.splitPos))
    labels = getattr(first, "dataLabels", None)
    if labels is not None and (labels.showVal or labels.showPercent or labels.showCatName or labels.showSerName):
        options["show_data_labels"] = True
        if labels.showCatName and labels.showVal:
            options["data_label_content"] = "category_value"
        elif labels.showPercent:
            options["data_label_content"] = "percent"
        elif labels.showCatName:
            options["data_label_content"] = "category"
        elif labels.showSerName:
            options["data_label_content"] = "series"
    trend = next((item.trendline for item in series if item.trendline is not None), None)
    if trend is not None:
        kinds = {value: key for key, value in _TRENDLINES.items()}
        options.update(
            show_trendline=True,
            trendline_type=kinds.get(trend.trendlineType, "linear"),
            show_equation=bool(trend.dispEq),
            show_r_squared=bool(trend.dispRSqr),
            trendline_forward=float(trend.forward or 0),
            trendline_backward=float(trend.backward or 0),
        )
        if trend.trendlineType == "poly" and trend.order:
            options["trendline_order"] = int(trend.order)
        if trend.trendlineType == "movingAvg" and trend.period:
            options["trendline_order"] = int(trend.period)
    error = next((item.errBars for item in series if item.errBars is not None), None)
    if error is not None:
        kinds = {value: key for key, value in _ERROR_TYPES.items()}
        options["error_bars"] = kinds.get(error.errValType, "standard_error")
        if error.val is not None:
            options["error_amount"] = float(error.val)
    if chart_type.startswith("combo"):
        kinds = []
        secondary = []
        for part in parts:
            kind = {"barChart": "column", "lineChart": "line", "areaChart": "area"}.get(part.tagname, "line")
            for _item in part.series:
                kinds.append(kind)
                if part is not first and part.y_axis.axId != first.y_axis.axId:
                    secondary.append(len(kinds))
        chart_type = _normalize_combo(kinds, secondary)
        if chart_type == "combo_custom":
            options.update(combo_series_types=tuple(kinds), secondary_series=tuple(secondary))
    blanks = getattr(chart, "display_blanks", "gap")
    options["empty_cells"] = {value: key for key, value in _EMPTY.items()}.get(blanks, "gaps")
    source = RangeReference(CellReference(min_row, min_column, sheet_name), CellReference(max_row, max_column, sheet_name))
    try:
        return ChartSpec(chart_id=chart_id, sheet_name=sheet_name, source_range=source, chart_type=chart_type, **options)
    except (ValueError, TypeError):
        return None


def _classic_type(first: Any, parts: list[Any], series: list[Any]) -> str | None:
    tag = first.tagname
    tags = [part.tagname for part in parts]
    if len(parts) > 1:
        if tags[:2] == ["barChart", "stockChart"]:
            return "stock_vohlc" if parts[1].upDownBars is not None else "stock_vhlc"
        return "combo_custom"
    grouping = getattr(first, "grouping", None)
    if tag in ("barChart", "bar3DChart"):
        three_d = tag == "bar3DChart"
        for key, (direction, kind_grouping, is_3d) in _BAR_TYPES.items():
            if direction == (first.barDir or "col") and kind_grouping == (grouping or "clustered") and is_3d == three_d:
                return key
        return "column_3d" if three_d else "column"
    if tag == "lineChart":
        markers = any(_has_marker(item) for item in series)
        mapping = {
            ("standard", False): "line_plain",
            ("standard", True): "line",
            ("stacked", False): "stacked_line",
            ("stacked", True): "stacked_line_markers",
            ("percentStacked", False): "stacked_line_100",
            ("percentStacked", True): "stacked_line_100_markers",
        }
        return mapping.get((grouping or "standard", markers), "line")
    if tag == "line3DChart":
        return "line_3d"
    if tag in ("areaChart", "area3DChart"):
        suffix = {"standard": "", "stacked": "_stacked", "percentStacked": "_stacked_100"}.get(grouping or "standard", "")
        if tag == "area3DChart":
            return "area_3d" + suffix
        return {"": "area", "_stacked": "stacked_area", "_stacked_100": "stacked_area_100"}[suffix]
    if tag == "scatterChart":
        markers = any(_has_marker(item) for item in series)
        lines = any(
            not (item.spPr is not None and item.spPr.ln is not None and item.spPr.ln.noFill)
            for item in series
        )
        smooth = first.scatterStyle in ("smooth", "smoothMarker") or any(item.smooth for item in series)
        if not lines:
            return "scatter"
        if smooth:
            return "scatter_smooth_markers" if markers else "scatter_smooth"
        return "scatter_lines_markers" if markers else "scatter_lines"
    if tag == "bubbleChart":
        return "bubble_3d" if first.bubble3D or any(item.bubble3D for item in series) else "bubble"
    if tag == "pieChart":
        return "pie"
    if tag == "pie3DChart":
        return "pie_3d"
    if tag == "ofPieChart":
        return "bar_of_pie" if first.ofPieType == "bar" else "pie_of_pie"
    if tag == "doughnutChart":
        return "donut"
    if tag == "stockChart":
        return "stock_ohlc" if first.upDownBars is not None or len(series) >= 4 else "stock_hlc"
    if tag == "surface3DChart":
        return "surface_wireframe" if first.wireframe else "surface_3d"
    if tag == "surfaceChart":
        return "contour_wireframe" if first.wireframe else "contour"
    if tag == "radarChart":
        if first.radarStyle == "filled":
            return "radar_filled"
        markers = any(_has_marker(item) for item in series)
        return "radar_markers" if markers else "radar"
    return None


def _has_marker(series: Any) -> bool:
    """Whether a series read from a file draws markers (openpyxl reads "none" as None)."""
    return series.marker is None or series.marker.symbol not in (None, "none")


def _normalize_combo(kinds: list[str], secondary: list[int]) -> str:
    count = len(kinds)
    if kinds == ["column"] + ["line"] * (count - 1) and count > 1:
        if not secondary:
            return "combo"
        if secondary == list(range(2, count + 1)):
            return "combo_secondary"
    split = max(1, count // 2)
    if not secondary and kinds == ["area"] * split + ["column"] * (count - split):
        return "combo_area_column"
    return "combo_custom"


def _formula(source: Any) -> str | None:
    if source is None:
        return None
    for name in ("numRef", "strRef", "multiLvlStrRef"):
        reference = getattr(source, name, None)
        if reference is not None and reference.f:
            return reference.f
    return None


def _range(formula: str | None, sheet_name: str) -> RangeReference | None:
    if not formula:
        return None
    text = formula.strip().lstrip("=").replace("$", "")
    if text.startswith("(") and text.endswith(")"):
        return None
    try:
        reference = parse_a1(text, default_sheet=sheet_name)
    except (ValueError, KeyError):
        return None
    if isinstance(reference, CellReference):
        return RangeReference(reference, reference)
    return reference if isinstance(reference, RangeReference) else None


def _text(title: Any) -> str:
    if title is None:
        return ""
    if isinstance(title, str):
        return title
    tx = getattr(title, "tx", None)
    rich = getattr(tx, "rich", None) if tx is not None else None
    if rich is None:
        return ""
    lines = []
    for paragraph in rich.p or []:
        lines.append("".join(run.t or "" for run in paragraph.r or []))
    return "\n".join(lines).strip()


def read_chartex_charts(package: XlsxPackage, sheet_part: str, sheet_name: str) -> list[ChartSpec]:
    """Return Office 2016 charts found in a worksheet's drawing."""
    drawing = package.drawing_for(sheet_part, create=False)
    if drawing is None:
        return []
    result: list[ChartSpec] = []
    names = package.defined_names()
    drawing_xml = package.text(drawing)
    relationships = sorted(
        package.relationships(drawing),
        key=lambda rel: drawing_xml.find(f'r:id="{rel[0]}"') % (len(drawing_xml) + 1),
    )
    for _rel_id, rel_type, target in relationships:
        if rel_type != CHARTEX_REL or target not in package.entries:
            continue
        xml = re.sub(
            r"(<cx:f(?:\s[^>]*)?>)([^<]+)(</cx:f>)",
            lambda found: found.group(1) + xml_text(names.get(_unescape(found.group(2)), _unescape(found.group(2)))) + found.group(3),
            package.text(target),
        )
        spec = _chartex_spec(xml, sheet_name, f"xlsx-{uuid.uuid5(uuid.NAMESPACE_URL, target).hex}")
        if spec is not None:
            result.append(spec)
    return result


def _chartex_spec(xml: str, sheet_name: str, chart_id: str) -> ChartSpec | None:
    layout_ids = re.findall(r'layoutId="(\w+)"', xml)
    if not layout_ids:
        return None
    first = layout_ids[0]
    if first == "clusteredColumn":
        chart_type = "pareto" if "paretoLine" in layout_ids else "histogram"
    else:
        chart_type = {"boxWhisker": "box", "waterfall": "waterfall", "funnel": "funnel", "treemap": "treemap", "sunburst": "sunburst", "regionMap": None}.get(first)
    if chart_type is None:
        return None
    references = [_range(_unescape(found), sheet_name) for found in re.findall(r"<cx:f(?:\s[^>]*)?>([^<]+)</cx:f>", xml)]
    references = [reference for reference in references if reference is not None]
    sheets = {reference.sheet or sheet_name for reference in references}
    if len(sheets) != 1:
        return None
    sheet_name = sheets.pop()
    data_refs = [reference for reference in references if reference.min_row != reference.max_row or reference.min_column != reference.max_column]
    name_refs = [reference for reference in references if reference not in data_refs]
    if not data_refs:
        return None
    min_row = min(reference.min_row for reference in references)
    max_row = max(reference.max_row for reference in references)
    min_column = min(reference.min_column for reference in references)
    max_column = max(reference.max_column for reference in references)
    has_headers = bool(name_refs) and min(reference.min_row for reference in name_refs) < min(reference.min_row for reference in data_refs)
    if not has_headers:
        min_row = min(reference.min_row for reference in data_refs)
    title = re.search(r"<cx:title\b[^>]*>.*?<cx:v>([^<]*)</cx:v>", xml, re.DOTALL)
    chart_title = _unescape(title.group(1)) if title and xml.find("<cx:title") < xml.find("<cx:plotArea") else ""
    legend = re.search(r'<cx:legend\b[^>]*\bpos="(\w)"', xml)
    bins = re.search(r'<cx:binCount val="(\d+)"', xml)
    source = RangeReference(CellReference(min_row, min_column, sheet_name), CellReference(max_row, max_column, sheet_name))
    options: dict[str, Any] = {
        "title": chart_title,
        "has_headers": has_headers,
        "legend_position": _LEGEND_BACK.get(legend.group(1), "right") if legend else "none",
    }
    if bins:
        options["bin_count"] = int(bins.group(1))
    try:
        return ChartSpec(chart_id=chart_id, sheet_name=sheet_name, source_range=source, chart_type=chart_type, **options)
    except (ValueError, TypeError):
        return None


def drawing_anchor_cells(package: XlsxPackage, drawing: str) -> list[tuple[int, int, int, int]]:
    """Return the cell bounds of each anchor in a drawing part."""
    bounds = []
    for anchor in drawing_anchors(package.text(drawing)):
        found = anchor_bounds(anchor)
        if found is not None:
            bounds.append(found[:4])
    return bounds


def _unescape(text: str) -> str:
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")
