"""Headless chart specifications, recommendations, and data extraction."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from duddysheet.core.refs import CellReference, RangeReference
from duddysheet.core.workbook import Workbook


@dataclass(frozen=True, slots=True)
class ChartTypeInfo:
    """User-facing description of one chart type in the gallery."""

    key: str
    label: str
    family: str
    summary: str
    layout: str


_STANDARD_LAYOUT = (
    "Categories in the first column, one numeric column per series, with an "
    "optional header row naming each series."
)
_SINGLE_LAYOUT = (
    "Categories in the first column and one numeric column. Only the first "
    "series is drawn."
)
_XY_LAYOUT = (
    "X values in the first column and one Y column per series. Every column "
    "must be numeric."
)
_BUBBLE_LAYOUT = (
    "X values in the first column, then pairs of columns: Y value, bubble "
    "size. A Y column without a size column uses equal bubble sizes."
)
_SURFACE_LAYOUT = (
    "A grid: row labels in the first column, column labels in the header "
    "row, and a numeric height in every cell."
)
_HIERARCHY_LAYOUT = (
    "One or more text columns forming the levels (for example Region, "
    "Country, City) followed by one numeric value column. Blank level cells "
    "repeat the label above them."
)
_DISTRIBUTION_LAYOUT = (
    "One or more numeric columns of raw observations. Each column is one "
    "series; categories are ignored."
)


def _stock_layout(columns: str) -> str:
    return (
        f"Dates in the first column followed by exactly these columns in "
        f"order: {columns}."
    )


# Ordered like Excel's Insert Chart > All Charts gallery.
CHART_CATALOG: tuple[ChartTypeInfo, ...] = (
    ChartTypeInfo("column", "Clustered Column", "Column", "Compare values across categories with vertical bars side by side.", _STANDARD_LAYOUT),
    ChartTypeInfo("stacked_column", "Stacked Column", "Column", "Show each category's total and how every series contributes to it.", _STANDARD_LAYOUT),
    ChartTypeInfo("stacked_column_100", "100% Stacked Column", "Column", "Compare the percentage each series contributes to every category's total.", _STANDARD_LAYOUT),
    ChartTypeInfo("column_3d_clustered", "3-D Clustered Column", "Column", "Clustered columns drawn as three-dimensional blocks.", _STANDARD_LAYOUT),
    ChartTypeInfo("column_3d_stacked", "3-D Stacked Column", "Column", "Stacked columns drawn as three-dimensional blocks.", _STANDARD_LAYOUT),
    ChartTypeInfo("column_3d_stacked_100", "3-D 100% Stacked Column", "Column", "100% stacked columns drawn as three-dimensional blocks.", _STANDARD_LAYOUT),
    ChartTypeInfo("column_3d", "3-D Column", "Column", "Columns on a true depth axis: categories across, series front to back.", _STANDARD_LAYOUT),
    ChartTypeInfo("line_plain", "Line", "Line", "Show a trend over ordered categories such as months or years.", _STANDARD_LAYOUT),
    ChartTypeInfo("stacked_line", "Stacked Line", "Line", "Show the running total of several series over time.", _STANDARD_LAYOUT),
    ChartTypeInfo("stacked_line_100", "100% Stacked Line", "Line", "Show how each series' share of the total changes over time.", _STANDARD_LAYOUT),
    ChartTypeInfo("line", "Line with Markers", "Line", "A trend line with a marker on every data point; best for few points.", _STANDARD_LAYOUT),
    ChartTypeInfo("stacked_line_markers", "Stacked Line with Markers", "Line", "Stacked lines with a marker on every data point.", _STANDARD_LAYOUT),
    ChartTypeInfo("stacked_line_100_markers", "100% Stacked Line with Markers", "Line", "100% stacked lines with a marker on every data point.", _STANDARD_LAYOUT),
    ChartTypeInfo("line_3d", "3-D Line", "Line", "Each series drawn as a ribbon on its own depth row.", _STANDARD_LAYOUT),
    ChartTypeInfo("pie", "Pie", "Pie", "Show the proportions of a whole for one series.", _SINGLE_LAYOUT),
    ChartTypeInfo("pie_3d", "3-D Pie", "Pie", "A pie tilted into perspective with visible depth.", _SINGLE_LAYOUT),
    ChartTypeInfo("pie_of_pie", "Pie of Pie", "Pie", "Pull the smallest slices into a second pie so they stay readable.", _SINGLE_LAYOUT),
    ChartTypeInfo("bar_of_pie", "Bar of Pie", "Pie", "Pull the smallest slices into a stacked bar beside the pie.", _SINGLE_LAYOUT),
    ChartTypeInfo("donut", "Doughnut", "Pie", "A pie with a hole; several series draw as concentric rings.", _STANDARD_LAYOUT),
    ChartTypeInfo("bar", "Clustered Bar", "Bar", "Compare values across categories with horizontal bars; good for long labels.", _STANDARD_LAYOUT),
    ChartTypeInfo("stacked_bar", "Stacked Bar", "Bar", "Horizontal bars showing totals and each series' contribution.", _STANDARD_LAYOUT),
    ChartTypeInfo("stacked_bar_100", "100% Stacked Bar", "Bar", "Horizontal bars comparing each series' percentage of the total.", _STANDARD_LAYOUT),
    ChartTypeInfo("bar_3d_clustered", "3-D Clustered Bar", "Bar", "Clustered horizontal bars drawn as three-dimensional blocks.", _STANDARD_LAYOUT),
    ChartTypeInfo("bar_3d_stacked", "3-D Stacked Bar", "Bar", "Stacked horizontal bars drawn as three-dimensional blocks.", _STANDARD_LAYOUT),
    ChartTypeInfo("bar_3d_stacked_100", "3-D 100% Stacked Bar", "Bar", "100% stacked horizontal bars drawn as three-dimensional blocks.", _STANDARD_LAYOUT),
    ChartTypeInfo("area", "Area", "Area", "Emphasize the magnitude of change over time for each series.", _STANDARD_LAYOUT),
    ChartTypeInfo("stacked_area", "Stacked Area", "Area", "Show how each series adds to a changing total over time.", _STANDARD_LAYOUT),
    ChartTypeInfo("stacked_area_100", "100% Stacked Area", "Area", "Show how each series' share of the total changes over time.", _STANDARD_LAYOUT),
    ChartTypeInfo("area_3d", "3-D Area", "Area", "Each series drawn as a solid area on its own depth row.", _STANDARD_LAYOUT),
    ChartTypeInfo("area_3d_stacked", "3-D Stacked Area", "Area", "Stacked areas drawn with three-dimensional depth.", _STANDARD_LAYOUT),
    ChartTypeInfo("area_3d_stacked_100", "3-D 100% Stacked Area", "Area", "100% stacked areas drawn with three-dimensional depth.", _STANDARD_LAYOUT),
    ChartTypeInfo("scatter", "Scatter", "X Y (Scatter)", "Plot pairs of numbers to reveal relationships and correlation.", _XY_LAYOUT),
    ChartTypeInfo("scatter_smooth_markers", "Scatter with Smooth Lines and Markers", "X Y (Scatter)", "Points joined by a smoothed curve, with markers.", _XY_LAYOUT),
    ChartTypeInfo("scatter_smooth", "Scatter with Smooth Lines", "X Y (Scatter)", "A smoothed curve through numeric X/Y points without markers.", _XY_LAYOUT),
    ChartTypeInfo("scatter_lines_markers", "Scatter with Straight Lines and Markers", "X Y (Scatter)", "Points joined by straight segments, with markers.", _XY_LAYOUT),
    ChartTypeInfo("scatter_lines", "Scatter with Straight Lines", "X Y (Scatter)", "Straight segments through numeric X/Y points without markers.", _XY_LAYOUT),
    ChartTypeInfo("bubble", "Bubble", "X Y (Scatter)", "A scatter chart whose marker area encodes a third value.", _BUBBLE_LAYOUT),
    ChartTypeInfo("bubble_3d", "3-D Bubble", "X Y (Scatter)", "Bubbles shaded as spheres.", _BUBBLE_LAYOUT),
    ChartTypeInfo("stock_hlc", "High-Low-Close", "Stock", "Daily high-low range with a closing tick.", _stock_layout("High, Low, Close")),
    ChartTypeInfo("stock_ohlc", "Open-High-Low-Close", "Stock", "Candlesticks: a body from open to close and wicks to high and low.", _stock_layout("Open, High, Low, Close")),
    ChartTypeInfo("stock_vhlc", "Volume-High-Low-Close", "Stock", "Volume bars with a high-low-close chart on a secondary axis.", _stock_layout("Volume, High, Low, Close")),
    ChartTypeInfo("stock_vohlc", "Volume-Open-High-Low-Close", "Stock", "Volume bars with candlesticks on a secondary axis.", _stock_layout("Volume, Open, High, Low, Close")),
    ChartTypeInfo("surface_3d", "3-D Surface", "Surface", "A colored surface over a two-dimensional grid of values.", _SURFACE_LAYOUT),
    ChartTypeInfo("surface_wireframe", "Wireframe 3-D Surface", "Surface", "The 3-D surface drawn as a mesh of lines.", _SURFACE_LAYOUT),
    ChartTypeInfo("contour", "Contour", "Surface", "The surface seen from above, with color bands for value ranges.", _SURFACE_LAYOUT),
    ChartTypeInfo("contour_wireframe", "Wireframe Contour", "Surface", "Contour lines only, like a topographic map.", _SURFACE_LAYOUT),
    ChartTypeInfo("radar", "Radar", "Radar", "Compare several series across the same set of measures.", _STANDARD_LAYOUT),
    ChartTypeInfo("radar_markers", "Radar with Markers", "Radar", "Radar lines with a marker on every value.", _STANDARD_LAYOUT),
    ChartTypeInfo("radar_filled", "Filled Radar", "Radar", "Radar polygons filled with color.", _STANDARD_LAYOUT),
    ChartTypeInfo("treemap", "Treemap", "Treemap", "Nested rectangles sized by value, grouped by hierarchy level.", _HIERARCHY_LAYOUT),
    ChartTypeInfo("sunburst", "Sunburst", "Sunburst", "Concentric rings: inner rings are parents, outer rings their children.", _HIERARCHY_LAYOUT),
    ChartTypeInfo("histogram", "Histogram", "Histogram", "Group raw numbers into bins to show a distribution.", _DISTRIBUTION_LAYOUT),
    ChartTypeInfo("pareto", "Pareto", "Histogram", "Bars sorted from largest to smallest with a cumulative percentage line.", _SINGLE_LAYOUT),
    ChartTypeInfo("box", "Box and Whisker", "Box & Whisker", "Show median, quartiles, spread, mean, and outliers.", _DISTRIBUTION_LAYOUT),
    ChartTypeInfo("waterfall", "Waterfall", "Waterfall", "Show how positive and negative changes build a running total.", _SINGLE_LAYOUT),
    ChartTypeInfo("funnel", "Funnel", "Funnel", "Show values shrinking through the stages of a process.", _SINGLE_LAYOUT),
    ChartTypeInfo("combo", "Clustered Column - Line", "Combo", "The first series as columns and the others as lines.", _STANDARD_LAYOUT),
    ChartTypeInfo("combo_secondary", "Clustered Column - Line on Secondary Axis", "Combo", "Columns on the left axis and lines on their own right axis.", _STANDARD_LAYOUT),
    ChartTypeInfo("combo_area_column", "Stacked Area - Clustered Column", "Combo", "The first half of the series as stacked areas, the rest as columns.", _STANDARD_LAYOUT),
    ChartTypeInfo("combo_custom", "Custom Combination", "Combo", "Choose column, line, or area and the axis for every series.", _STANDARD_LAYOUT),
    ChartTypeInfo("step", "Step Line", "More", "A line that holds each value until the next category.", _STANDARD_LAYOUT),
    ChartTypeInfo("heatmap", "Heatmap", "More", "A color-intensity grid of series by category.", _STANDARD_LAYOUT),
)
CHART_INFO = {info.key: info for info in CHART_CATALOG}
CHART_TYPES = frozenset(CHART_INFO)
CHART_TYPE_LABELS = {info.key: info.label for info in CHART_CATALOG}
CHART_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = tuple(
    (
        family,
        tuple(info.key for info in CHART_CATALOG if info.family == family),
    )
    for family in dict.fromkeys(info.family for info in CHART_CATALOG)
)

THREE_D_TYPES = frozenset(
    {
        "column_3d_clustered",
        "column_3d_stacked",
        "column_3d_stacked_100",
        "column_3d",
        "bar_3d_clustered",
        "bar_3d_stacked",
        "bar_3d_stacked_100",
        "line_3d",
        "area_3d",
        "area_3d_stacked",
        "area_3d_stacked_100",
        "surface_3d",
        "surface_wireframe",
    }
)
POLAR_TYPES = frozenset({"radar", "radar_markers", "radar_filled"})
STOCK_COLUMNS = {
    "stock_hlc": ("High", "Low", "Close"),
    "stock_ohlc": ("Open", "High", "Low", "Close"),
    "stock_vhlc": ("Volume", "High", "Low", "Close"),
    "stock_vohlc": ("Volume", "Open", "High", "Low", "Close"),
}

LEGEND_POSITIONS = frozenset({"right", "left", "top", "bottom", "none"})
CHART_THEMES = frozenset(
    {"executive", "coastal", "editorial", "monochrome", "high_contrast"}
)
NUMBER_FORMATS = frozenset({"auto", "number", "currency", "percent"})
COLOR_SCHEMES = ("theme", "colorful", "blue", "orange", "green", "purple", "gray")
DATA_LABEL_POSITIONS = (
    "auto",
    "center",
    "inside_end",
    "inside_base",
    "outside_end",
)
DATA_LABEL_CONTENTS = ("value", "percent", "category", "series", "category_value")
ERROR_BAR_TYPES = (
    "none",
    "standard_error",
    "percentage",
    "standard_deviation",
    "fixed",
)
ERROR_BAR_DEFAULTS = {
    "none": 0.0,
    "standard_error": 1.0,
    "percentage": 5.0,
    "standard_deviation": 1.0,
    "fixed": 1.0,
}
TRENDLINE_TYPES = (
    "linear",
    "exponential",
    "logarithmic",
    "polynomial",
    "power",
    "moving_average",
)
DISPLAY_UNITS = {
    "none": 1.0,
    "hundreds": 100.0,
    "thousands": 1_000.0,
    "millions": 1_000_000.0,
    "billions": 1_000_000_000.0,
}
EMPTY_CELL_MODES = ("gaps", "zero", "connect")
COMBO_SERIES_TYPES = ("column", "line", "area")


@dataclass(frozen=True, slots=True)
class ChartSpec:
    """Immutable chart configuration bound to a worksheet range.

    The fields after ``number_format`` mirror Excel's chart elements and
    format options. Each one defaults to the look charts had before it
    existed, so older workbooks render unchanged.
    """

    chart_id: str
    sheet_name: str
    source_range: RangeReference
    chart_type: str
    title: str = ""
    x_axis_title: str = ""
    y_axis_title: str = ""
    legend_position: str = "right"
    has_headers: bool = True
    category_column: int | None = None
    series_columns: tuple[int, ...] | None = None
    theme: str = "executive"
    show_data_labels: bool = False
    show_trendline: bool = False
    highlight_extrema: bool = False
    show_grid: bool = True
    secondary_axis: bool = False
    number_format: str = "auto"
    # Data selection.
    switch_row_column: bool = False
    empty_cells: str = "gaps"
    # Chart elements.
    show_x_axis: bool = True
    show_y_axis: bool = True
    minor_gridlines: bool = False
    vertical_gridlines: bool = False
    data_label_position: str = "auto"
    data_label_content: str = "value"
    show_data_table: bool = False
    error_bars: str = "none"
    error_amount: float | None = None
    trendline_type: str = "linear"
    trendline_order: int = 2
    trendline_forward: float = 0.0
    trendline_backward: float = 0.0
    show_equation: bool = False
    show_r_squared: bool = False
    drop_lines: bool = False
    high_low_lines: bool = False
    up_down_bars: bool = False
    # Axis format.
    axis_min: float | None = None
    axis_max: float | None = None
    major_unit: float | None = None
    log_scale: bool = False
    reverse_categories: bool = False
    display_units: str = "none"
    # Series format.
    color_scheme: str = "theme"
    smooth_lines: bool = False
    gap_width: int = 22
    series_overlap: int = 0
    hole_size: int = 58
    first_slice_angle: int = 0
    pie_explosion: int = 0
    split_count: int = 3
    bin_count: int | None = None
    combo_series_types: tuple[str, ...] | None = None
    secondary_series: tuple[int, ...] = ()
    # A PivotChart follows this PivotTable's current layout instead of a range.
    pivot_name: str | None = None

    def __post_init__(self) -> None:
        if self.chart_type not in CHART_TYPES:
            raise ValueError(f"Unsupported chart type: {self.chart_type!r}")
        if self.legend_position not in LEGEND_POSITIONS:
            raise ValueError(
                f"Unsupported legend position: {self.legend_position!r}"
            )
        if self.theme not in CHART_THEMES:
            raise ValueError(f"Unsupported chart theme: {self.theme!r}")
        if self.number_format not in NUMBER_FORMATS:
            raise ValueError(
                f"Unsupported chart number format: {self.number_format!r}"
            )
        choices = (
            ("empty cell mode", self.empty_cells, EMPTY_CELL_MODES),
            ("data label position", self.data_label_position, DATA_LABEL_POSITIONS),
            ("data label content", self.data_label_content, DATA_LABEL_CONTENTS),
            ("error bar type", self.error_bars, ERROR_BAR_TYPES),
            ("trendline type", self.trendline_type, TRENDLINE_TYPES),
            ("display unit", self.display_units, tuple(DISPLAY_UNITS)),
            ("color scheme", self.color_scheme, COLOR_SCHEMES),
        )
        for name, value, allowed in choices:
            if value not in allowed:
                raise ValueError(f"Unsupported {name}: {value!r}")
        if self.error_amount is not None and self.error_amount < 0:
            raise ValueError("Error bar amount cannot be negative")
        if self.trendline_type == "polynomial" and not 2 <= self.trendline_order <= 6:
            raise ValueError("Polynomial trendline order must be 2 to 6")
        if self.trendline_type == "moving_average" and self.trendline_order < 2:
            raise ValueError("Moving average period must be at least 2")
        if self.trendline_forward < 0 or self.trendline_backward < 0:
            raise ValueError("Trendline forecast periods cannot be negative")
        if (
            self.axis_min is not None
            and self.axis_max is not None
            and self.axis_min >= self.axis_max
        ):
            raise ValueError("Axis minimum must be less than the axis maximum")
        if self.major_unit is not None and self.major_unit <= 0:
            raise ValueError("Axis major unit must be positive")
        if not 0 <= self.gap_width <= 500:
            raise ValueError("Gap width must be 0 to 500 percent")
        if not -100 <= self.series_overlap <= 100:
            raise ValueError("Series overlap must be -100 to 100 percent")
        if not 10 <= self.hole_size <= 90:
            raise ValueError("Doughnut hole size must be 10 to 90 percent")
        if not 0 <= self.first_slice_angle <= 360:
            raise ValueError("First slice angle must be 0 to 360 degrees")
        if not 0 <= self.pie_explosion <= 400:
            raise ValueError("Pie explosion must be 0 to 400 percent")
        if self.split_count < 1:
            raise ValueError("The second plot needs at least one value")
        if self.bin_count is not None and not 1 <= self.bin_count <= 1000:
            raise ValueError("Histogram bin count must be 1 to 1000")
        if self.combo_series_types is not None and any(
            kind not in COMBO_SERIES_TYPES for kind in self.combo_series_types
        ):
            raise ValueError(
                "Combo series types must each be column, line, or area"
            )
        if any(number < 1 for number in self.secondary_series):
            raise ValueError("Secondary axis series numbers start at 1")

    @property
    def effective_error_amount(self) -> float:
        """Return the error amount, falling back to Excel's per-type default."""
        if self.error_amount is not None:
            return self.error_amount
        return ERROR_BAR_DEFAULTS[self.error_bars]


@dataclass(frozen=True, slots=True)
class ChartSeries:
    """One named numeric chart series."""

    name: str
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ChartData:
    """Prepared categories and series independent of a rendering library."""

    categories: tuple[Any, ...]
    series: tuple[ChartSeries, ...]


@dataclass(frozen=True, slots=True)
class ChartRecommendation:
    """One ranked chart recommendation with a user-facing explanation."""

    chart_type: str
    title: str
    reason: str
    score: int


@dataclass(frozen=True, slots=True)
class HierarchyNode:
    """One labelled node of a treemap or sunburst hierarchy."""

    label: str
    value: float
    children: tuple[HierarchyNode, ...] = ()


@dataclass(frozen=True, slots=True)
class LayoutRect:
    """An axis-aligned rectangle produced by a treemap layout."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class TrendlineFit:
    """A fitted regression trendline in Excel's equation forms."""

    kind: str
    coefficients: tuple[float, ...]
    r_squared: float

    def predict(self, x_value: float) -> float:
        """Return the fitted value at ``x_value`` (NaN outside the domain)."""
        if self.kind == "linear":
            slope, intercept = self.coefficients
            return slope * x_value + intercept
        if self.kind == "exponential":
            scale, rate = self.coefficients
            return scale * math.exp(rate * x_value)
        if self.kind == "logarithmic":
            slope, intercept = self.coefficients
            return slope * math.log(x_value) + intercept if x_value > 0 else math.nan
        if self.kind == "power":
            scale, exponent = self.coefficients
            return scale * x_value**exponent if x_value > 0 else math.nan
        # Polynomial coefficients run from the highest power down.
        result = 0.0
        for coefficient in self.coefficients:
            result = result * x_value + coefficient
        return result

    @property
    def equation(self) -> str:
        """Return the equation text Excel shows on the chart."""

        def number(value: float) -> str:
            return f"{value:.4g}"

        def signed(value: float) -> str:
            return f"- {number(abs(value))}" if value < 0 else f"+ {number(value)}"

        if self.kind == "linear":
            slope, intercept = self.coefficients
            return f"y = {number(slope)}x {signed(intercept)}"
        if self.kind == "exponential":
            scale, rate = self.coefficients
            return f"y = {number(scale)}e^({number(rate)}x)"
        if self.kind == "logarithmic":
            slope, intercept = self.coefficients
            return f"y = {number(slope)}ln(x) {signed(intercept)}"
        if self.kind == "power":
            scale, exponent = self.coefficients
            return f"y = {number(scale)}x^{number(exponent)}"
        degree = len(self.coefficients) - 1
        terms: list[str] = []
        for power, coefficient in zip(range(degree, -1, -1), self.coefficients):
            suffix = "" if power == 0 else ("x" if power == 1 else f"x^{power}")
            text = f"{number(abs(coefficient))}{suffix}"
            if not terms:
                terms.append(f"-{text}" if coefficient < 0 else text)
            else:
                terms.append(f"{'-' if coefficient < 0 else '+'} {text}")
        return "y = " + " ".join(terms)


def chart_data(workbook: Workbook, spec: ChartSpec) -> ChartData:
    """Extract current cached range values for a chart."""
    if spec.pivot_name:
        data = pivot_chart_data(workbook, spec.sheet_name, spec.pivot_name)
        return switch_rows_columns(data) if spec.switch_row_column else data
    sheet = workbook.get_sheet(spec.sheet_name)
    target = spec.source_range
    category_column = (
        target.min_column
        if spec.category_column is None
        else spec.category_column
    )
    if not target.min_column <= category_column <= target.max_column:
        raise ValueError("Chart category column is outside the source range")
    series_columns = (
        tuple(
            column
            for column in range(target.min_column, target.max_column + 1)
            if column != category_column
        )
        if spec.series_columns is None
        else spec.series_columns
    )
    if any(
        not target.min_column <= column <= target.max_column
        for column in series_columns
    ):
        raise ValueError("Chart series column is outside the source range")
    if not series_columns:
        series_columns = (category_column,)
        category_column = -1

    first_data_row = target.min_row + (1 if spec.has_headers else 0)
    categories = tuple(
        (
            sheet.get_cell(row, category_column).display_value
            if category_column >= 0
            else row - first_data_row + 1
        )
        for row in range(first_data_row, target.max_row + 1)
    )
    series: list[ChartSeries] = []
    for index, column in enumerate(series_columns):
        header = (
            sheet.get_cell(target.min_row, column).display_value
            if spec.has_headers
            else None
        )
        name = str(header) if header not in (None, "") else f"Series {index + 1}"
        values = tuple(
            _numeric_value(sheet.get_cell(row, column).display_value)
            for row in range(first_data_row, target.max_row + 1)
        )
        series.append(ChartSeries(name, values))
    data = ChartData(categories, tuple(series))
    return switch_rows_columns(data) if spec.switch_row_column else data


def pivot_chart_data(workbook: Workbook, sheet_name: str, pivot_name: str) -> ChartData:
    """Read a PivotChart's data from its PivotTable: one category per row item.

    Subtotal and grand-total rows and columns are left out, as in an Excel
    PivotChart; each remaining value column becomes a series.
    """
    from duddysheet.core.pivot import compute_pivot

    pivot = next(
        (item for sheet in workbook for item in sheet.pivots if item.name == pivot_name and sheet.name == sheet_name),
        None,
    ) or next((item for sheet in workbook for item in sheet.pivots if item.name == pivot_name), None)
    if pivot is None:
        raise ValueError(f"The PivotTable {pivot_name!r} no longer exists")
    result = compute_pivot(workbook, pivot)
    cells = result.cells
    leaf_rows = sorted({row for (row, _column), cell in cells.items() if cell.role == "row_label"})
    label_columns = max(1, len(pivot.rows)) if pivot.layout == "tabular" else 1
    if not leaf_rows:
        grand = [row for (row, column), cell in cells.items() if column == 0 and cell.role == "grand_total"]
        leaf_rows = grand[:1]
    first_data_row = min(leaf_rows + [row for (row, column), cell in cells.items() if cell.role == "group"], default=result.table_top + 1)
    header_rows = range(result.table_top, first_data_row)
    series: list[ChartSeries] = []
    for column in range(label_columns, result.width):
        parts = [
            str(cells[(row, column)].value)
            for row in header_rows
            if (row, column) in cells and cells[(row, column)].value not in (None, "", "Column Labels")
        ]
        name = " - ".join(parts)
        if name == "Grand Total" or name.endswith(" Total") or any(
            (row, column) in cells and cells[(row, column)].role == "grand_column" for row in leaf_rows
        ):
            continue
        values = tuple(
            _numeric_value(cells[(row, column)].value) if (row, column) in cells else math.nan
            for row in leaf_rows
        )
        series.append(ChartSeries(name or f"Series {len(series) + 1}", values))
    # Nested row items are labelled with their outer items, "East / Apple".
    labels_by_row: dict[int, str] = {}
    path: list[str] = []
    for row in range(first_data_row, result.height):
        if label_columns > 1:
            for column in range(label_columns):
                cell = cells.get((row, column))
                if cell is not None and cell.role == "row_label" and cell.value not in (None, ""):
                    path[column:] = [str(cell.value)]
            labels_by_row[row] = " / ".join(path)
            continue
        cell = cells.get((row, 0))
        if cell is None or cell.role not in ("group", "row_label"):
            continue
        path[cell.indent:] = [str(cell.value)]
        labels_by_row[row] = " / ".join(path[: cell.indent + 1])
    categories = tuple(labels_by_row.get(row) or "Total" for row in leaf_rows)
    return ChartData(categories, tuple(series))


def switch_rows_columns(data: ChartData) -> ChartData:
    """Transpose chart data so series become categories, like Excel's button."""
    categories = tuple(series.name for series in data.series)
    series = tuple(
        ChartSeries(
            str(category) if category not in (None, "") else f"Series {index + 1}",
            tuple(item.values[index] for item in data.series),
        )
        for index, category in enumerate(data.categories)
    )
    return ChartData(categories, series)


def apply_empty_cells(values: tuple[float, ...], mode: str) -> tuple[float, ...]:
    """Treat blank values as gaps, zeros, or points to connect across."""
    if mode == "zero":
        return tuple(0.0 if math.isnan(value) else value for value in values)
    return values


def percent_stack(
    matrix: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], ...]:
    """Scale series so each category's absolute values total 100 percent."""
    if not matrix:
        return ()
    width = len(matrix[0])
    totals = [
        sum(abs(row[index]) for row in matrix if math.isfinite(row[index]))
        for index in range(width)
    ]
    return tuple(
        tuple(
            (
                row[index] / totals[index] * 100.0
                if totals[index] and math.isfinite(row[index])
                else 0.0
            )
            for index in range(width)
        )
        for row in matrix
    )


def error_bar_amounts(
    values: tuple[float, ...],
    kind: str,
    amount: float,
) -> tuple[float, ...]:
    """Return the plus-or-minus error for every point in a series."""
    finite = [value for value in values if math.isfinite(value)]
    if kind == "none" or not finite:
        return tuple(0.0 for _ in values)
    if kind == "fixed":
        return tuple(amount for _ in values)
    if kind == "percentage":
        return tuple(
            abs(value) * amount / 100.0 if math.isfinite(value) else 0.0
            for value in values
        )
    count = len(finite)
    mean = sum(finite) / count
    deviation = (
        math.sqrt(sum((value - mean) ** 2 for value in finite) / (count - 1))
        if count > 1
        else 0.0
    )
    if kind == "standard_deviation":
        return tuple(deviation * amount for _ in values)
    if kind == "standard_error":
        return tuple(deviation / math.sqrt(count) * amount for _ in values)
    raise ValueError(f"Unsupported error bar type: {kind!r}")


def fit_trendline(
    x_values: tuple[float, ...],
    y_values: tuple[float, ...],
    kind: str,
    order: int = 2,
) -> TrendlineFit | None:
    """Fit an Excel-style regression trendline, or return None if impossible.

    Exponential and power fits are least squares on the log-transformed data
    and report R-squared on that scale, exactly as Excel does. Points outside
    a model's domain (non-positive y for exponential and power, non-positive x
    for logarithmic and power) are ignored.
    """
    if kind not in TRENDLINE_TYPES or kind == "moving_average":
        raise ValueError(f"Not a regression trendline: {kind!r}")
    pairs = [
        (x, y)
        for x, y in zip(x_values, y_values)
        if math.isfinite(x) and math.isfinite(y)
    ]
    if kind in {"logarithmic", "power"}:
        pairs = [(x, y) for x, y in pairs if x > 0]
    if kind in {"exponential", "power"}:
        pairs = [(x, y) for x, y in pairs if y > 0]
    degree = order if kind == "polynomial" else 1
    if len(pairs) <= degree:
        return None
    xs = [
        math.log(x) if kind in {"logarithmic", "power"} else x for x, _ in pairs
    ]
    ys = [math.log(y) if kind in {"exponential", "power"} else y for _, y in pairs]
    coefficients = _least_squares_polynomial(xs, ys, degree)
    if coefficients is None:
        return None
    fitted = [_evaluate_polynomial(coefficients, x) for x in xs]
    mean = sum(ys) / len(ys)
    total = sum((y - mean) ** 2 for y in ys)
    residual = sum((y - estimate) ** 2 for y, estimate in zip(ys, fitted))
    r_squared = 1.0 - residual / total if total else 1.0
    if kind == "polynomial":
        return TrendlineFit(kind, tuple(coefficients), r_squared)
    slope, intercept = coefficients
    if kind in {"exponential", "power"}:
        return TrendlineFit(kind, (math.exp(intercept), slope), r_squared)
    return TrendlineFit(kind, (slope, intercept), r_squared)


def moving_average(
    values: tuple[float, ...],
    period: int,
) -> tuple[float, ...]:
    """Return a trailing moving average; the first ``period - 1`` are NaN."""
    result: list[float] = []
    for index in range(len(values)):
        window = values[index - period + 1 : index + 1] if index >= period - 1 else ()
        finite = [value for value in window if math.isfinite(value)]
        result.append(
            sum(finite) / len(finite) if window and len(finite) == period else math.nan
        )
    return tuple(result)


def pareto_data(
    categories: tuple[Any, ...],
    values: tuple[float, ...],
) -> tuple[tuple[Any, ...], tuple[float, ...], tuple[float, ...]]:
    """Sort values descending and return categories, values, cumulative percent."""
    pairs = sorted(
        (
            (category, value)
            for category, value in zip(categories, values)
            if math.isfinite(value)
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    total = sum(value for _, value in pairs)
    running = 0.0
    cumulative: list[float] = []
    for _, value in pairs:
        running += value
        cumulative.append(running / total * 100.0 if total else 0.0)
    return (
        tuple(category for category, _ in pairs),
        tuple(value for _, value in pairs),
        tuple(cumulative),
    )


def bubble_series(
    data: ChartData,
) -> tuple[tuple[str, tuple[float, ...], tuple[float, ...]], ...]:
    """Pair Y and size columns into bubble series of (name, y, size)."""
    result = []
    series = data.series
    for index in range(0, len(series), 2):
        y_series = series[index]
        sizes = (
            series[index + 1].values
            if index + 1 < len(series)
            else tuple(1.0 for _ in y_series.values)
        )
        result.append((y_series.name, y_series.values, sizes))
    return tuple(result)


def hierarchy_data(workbook: Workbook, spec: ChartSpec) -> tuple[HierarchyNode, ...]:
    """Build a treemap or sunburst tree from level columns and one value column.

    The value column is the first explicit series column or, by default, the
    last column of the range. Every other column is a level from outermost to
    innermost. Blank level labels repeat the label above, and rows without a
    positive value are skipped.
    """
    sheet = workbook.get_sheet(spec.sheet_name)
    target = spec.source_range
    value_column = (
        spec.series_columns[0] if spec.series_columns else target.max_column
    )
    level_columns = [
        column
        for column in range(target.min_column, target.max_column + 1)
        if column != value_column
    ]
    first_row = target.min_row + (1 if spec.has_headers else 0)
    previous = ["" for _ in level_columns]
    paths: list[tuple[tuple[str, ...], float]] = []
    for row in range(first_row, target.max_row + 1):
        labels: list[str] = []
        fresh = False
        for position, column in enumerate(level_columns):
            raw = sheet.get_cell(row, column).display_value
            text = "" if raw is None else str(raw).strip()
            if text:
                fresh = True
            elif not fresh:
                # Inherit only while every outer level was inherited too; a
                # fresh outer label starts a new branch.
                text = previous[position]
            previous[position] = text
            labels.append(text)
        value = _numeric_value(sheet.get_cell(row, value_column).display_value)
        if not math.isfinite(value) or value <= 0:
            continue
        path = tuple(label for label in labels if label) or (f"Item {row + 1}",)
        paths.append((path, value))
    return _build_tree(paths)


def _build_tree(
    paths: list[tuple[tuple[str, ...], float]],
) -> tuple[HierarchyNode, ...]:
    groups: dict[str, list[tuple[tuple[str, ...], float]]] = {}
    for path, value in paths:
        groups.setdefault(path[0], []).append((path[1:], value))
    nodes = []
    for label, members in groups.items():
        leaf_value = sum(value for rest, value in members if not rest)
        children = _build_tree([(rest, value) for rest, value in members if rest])
        total = leaf_value + sum(child.value for child in children)
        nodes.append(HierarchyNode(label, total, children))
    return tuple(nodes)


def squarify(
    values: tuple[float, ...],
    x: float,
    y: float,
    width: float,
    height: float,
) -> tuple[LayoutRect, ...]:
    """Lay out values as rectangles filling a box, keeping them near-square.

    Implements the squarified treemap algorithm of Bruls, Huizing, and van
    Wijk. Rectangles are returned in input order; the input should be sorted
    descending for the best aspect ratios.
    """
    positive = [max(0.0, value) for value in values]
    total = sum(positive)
    if total <= 0 or width <= 0 or height <= 0:
        return tuple(LayoutRect(x, y, 0.0, 0.0) for _ in values)
    scale = width * height / total
    areas = [value * scale for value in positive]
    remaining = list(range(len(areas)))
    box = [x, y, width, height]

    def worst(row: list[float], side: float) -> float:
        if not row or side <= 0:
            return math.inf
        area = sum(row)
        if area <= 0:
            return math.inf
        biggest, smallest = max(row), min(row)
        if smallest <= 0:
            return math.inf
        return max(
            side * side * biggest / (area * area),
            (area * area) / (side * side * smallest),
        )

    placed: dict[int, LayoutRect] = {}
    while remaining:
        bx, by, bw, bh = box
        side = min(bw, bh)
        row = [remaining[0]]
        while len(row) < len(remaining):
            candidate = row + [remaining[len(row)]]
            if worst([areas[i] for i in candidate], side) <= worst(
                [areas[i] for i in row], side
            ):
                row = candidate
            else:
                break
        row_area = sum(areas[i] for i in row)
        if bw >= bh:
            column_width = row_area / bh if bh else 0.0
            offset = by
            for i in row:
                item_height = areas[i] / column_width if column_width else 0.0
                placed[i] = LayoutRect(bx, offset, column_width, item_height)
                offset += item_height
            box = [bx + column_width, by, bw - column_width, bh]
        else:
            row_height = row_area / bw if bw else 0.0
            offset = bx
            for i in row:
                item_width = areas[i] / row_height if row_height else 0.0
                placed[i] = LayoutRect(offset, by, item_width, row_height)
                offset += item_width
            box = [bx, by + row_height, bw, bh - row_height]
        remaining = remaining[len(row) :]
    return tuple(placed[index] for index in range(len(areas)))


def expand_chart_range(
    workbook: Workbook,
    sheet_name: str,
    selection: RangeReference,
) -> RangeReference:
    """Expand a single selected cell to its contiguous populated data island."""
    if len(selection) > 1:
        return selection
    sheet = workbook.get_sheet(sheet_name)
    populated = {
        (row, column)
        for (row, column), cell in sheet.iter_populated()
        if cell.display_value not in (None, "")
    }
    origin = (selection.min_row, selection.min_column)
    if origin not in populated:
        return selection
    connected = {origin}
    pending = [origin]
    while pending:
        row, column = pending.pop()
        for candidate in (
            (row - 1, column),
            (row + 1, column),
            (row, column - 1),
            (row, column + 1),
        ):
            if candidate in populated and candidate not in connected:
                connected.add(candidate)
                pending.append(candidate)
    min_row = min(row for row, _ in connected)
    max_row = max(row for row, _ in connected)
    min_column = min(column for _, column in connected)
    max_column = max(column for _, column in connected)
    return RangeReference(
        CellReference(min_row, min_column, selection.sheet),
        CellReference(max_row, max_column, selection.sheet),
    )


def infer_chart_title(data: ChartData) -> str:
    """Infer a concise title from series names."""
    names = [series.name for series in data.series if series.name]
    if not names:
        return "Data overview"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} vs {names[1]}"
    return f"{names[0]} and {len(names) - 1} other series"


def detect_chart_headers(
    workbook: Workbook,
    sheet_name: str,
    source_range: RangeReference,
) -> bool:
    """Detect a text header row above numeric data."""
    if source_range.max_row <= source_range.min_row:
        return False
    sheet = workbook.get_sheet(sheet_name)
    first_row = [
        sheet.get_cell(source_range.min_row, column).display_value
        for column in range(source_range.min_column, source_range.max_column + 1)
    ]
    second_row = [
        sheet.get_cell(source_range.min_row + 1, column).display_value
        for column in range(source_range.min_column, source_range.max_column + 1)
    ]
    return any(
        isinstance(header, str)
        and header.strip()
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        for header, value in zip(first_row, second_row)
    )


def recommend_charts(
    workbook: Workbook,
    sheet_name: str,
    source_range: RangeReference,
    *,
    has_headers: bool = True,
) -> tuple[ChartRecommendation, ...]:
    """Rank useful charts for a range using transparent deterministic rules."""
    probe = ChartSpec(
        "recommendation",
        sheet_name,
        source_range,
        "column",
        has_headers=has_headers,
    )
    data = chart_data(workbook, probe)
    title = infer_chart_title(data)
    row_count = len(data.categories)
    series_count = len(data.series)
    finite_values = [
        value
        for series in data.series
        for value in series.values
        if math.isfinite(value)
    ]
    mixed_signs = any(value < 0 for value in finite_values) and any(
        value > 0 for value in finite_values
    )
    dated_categories = bool(data.categories) and all(
        isinstance(value, (date, datetime)) for value in data.categories
    )
    numeric_categories = bool(data.categories) and all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in data.categories
    )
    one_column = source_range.min_column == source_range.max_column
    names = tuple(series.name.strip().casefold() for series in data.series)
    text_series = [
        series
        for series in data.series
        if series.values and not any(math.isfinite(value) for value in series.values)
    ]
    candidates: list[ChartRecommendation] = []

    def add(chart_type: str, score: int, reason: str) -> None:
        if not any(item.chart_type == chart_type for item in candidates):
            candidates.append(ChartRecommendation(chart_type, title, reason, score))

    for stock_type, columns in STOCK_COLUMNS.items():
        if names == tuple(column.casefold() for column in columns):
            add(
                stock_type,
                101,
                "The columns are named like stock prices, in the order this "
                "stock chart expects.",
            )
    if (
        text_series
        and series_count >= 2
        and all(math.isfinite(value) for value in data.series[-1].values)
        and all(series in text_series for series in data.series[:-1])
    ):
        add(
            "treemap",
            98,
            "Text columns followed by one value column form a hierarchy; a "
            "treemap sizes every group by its total.",
        )
        add(
            "sunburst",
            94,
            "A sunburst shows the same hierarchy as rings, parents inside.",
        )
    if one_column:
        add(
            "histogram",
            100,
            "One numeric field is best explored as a distribution.",
        )
        add("box", 92, "A box plot exposes median, spread, and outliers.")
    if dated_categories:
        add("line", 100, "Dates were detected, so a trend view is the clearest.")
        add("area", 86, "An area view emphasizes cumulative magnitude over time.")
    if numeric_categories and not one_column:
        add(
            "scatter",
            97,
            "The category field is numeric, making an X/Y relationship meaningful.",
        )
        if series_count == 2:
            add(
                "bubble",
                80,
                "Two numeric columns beside the X values can be read as Y "
                "and bubble size.",
            )
    if mixed_signs and series_count == 1:
        add(
            "waterfall",
            96,
            "Positive and negative changes are ideal for a waterfall bridge.",
        )
    if series_count >= 4 and row_count >= 4:
        add(
            "heatmap",
            99,
            "A dense multi-series matrix is easier to scan as color intensity.",
        )
    if series_count >= 3 and 3 <= row_count <= 10:
        add(
            "radar",
            82,
            "Several series across a compact category set support profile comparison.",
        )
    if series_count > 1:
        add(
            "column",
            90 if row_count <= 12 else 80,
            "Clustered columns compare multiple series category by category.",
        )
        add(
            "combo",
            84,
            "A combo view separates a primary measure from supporting trends.",
        )
        add(
            "stacked_column",
            78,
            "Stacking shows both total scale and series contribution.",
        )
    else:
        add(
            "column",
            89 if row_count <= 15 else 74,
            "Columns provide the fastest comparison across discrete categories.",
        )
        non_negative = finite_values and all(value >= 0 for value in finite_values)
        if row_count <= 10 and non_negative:
            add(
                "donut",
                76,
                "A compact non-negative series can be read as part-to-whole.",
            )
        if non_negative and len(finite_values) >= 3:
            ordered = [value for value in data.series[0].values if math.isfinite(value)]
            if ordered == sorted(ordered, reverse=True):
                add(
                    "funnel",
                    85,
                    "The values shrink stage by stage, the shape of a funnel.",
                )
            add(
                "pareto",
                72,
                "A Pareto chart ranks the categories and shows which few "
                "account for most of the total.",
            )
    if row_count > 12:
        add("line", 88, "Many ordered observations are more legible as a trend.")
    add("bar", 70, "Horizontal bars remain readable when category labels are long.")
    add("line", 68, "A line chart provides a compact general trend view.")
    return tuple(sorted(candidates, key=lambda item: item.score, reverse=True)[:5])


def _least_squares_polynomial(
    xs: list[float],
    ys: list[float],
    degree: int,
) -> list[float] | None:
    """Solve the normal equations; coefficients run highest power first."""
    size = degree + 1
    matrix = [
        [sum(x ** (row + column) for x in xs) for column in range(size)]
        for row in range(size)
    ]
    vector = [sum(y * x**row for x, y in zip(xs, ys)) for row in range(size)]
    # Gaussian elimination with partial pivoting.
    for pivot in range(size):
        best = max(range(pivot, size), key=lambda row: abs(matrix[row][pivot]))
        if abs(matrix[best][pivot]) < 1e-12:
            return None
        matrix[pivot], matrix[best] = matrix[best], matrix[pivot]
        vector[pivot], vector[best] = vector[best], vector[pivot]
        for row in range(pivot + 1, size):
            factor = matrix[row][pivot] / matrix[pivot][pivot]
            for column in range(pivot, size):
                matrix[row][column] -= factor * matrix[pivot][column]
            vector[row] -= factor * vector[pivot]
    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        remainder = vector[row] - sum(
            matrix[row][column] * solution[column] for column in range(row + 1, size)
        )
        solution[row] = remainder / matrix[row][row]
    # solution[k] is the coefficient of x**k; return highest power first.
    return list(reversed(solution))


def _evaluate_polynomial(coefficients: list[float], x_value: float) -> float:
    result = 0.0
    for coefficient in coefficients:
        result = result * x_value + coefficient
    return result


def _numeric_value(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return math.nan
