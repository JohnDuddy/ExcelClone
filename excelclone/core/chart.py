"""Headless chart specifications, recommendations, and data extraction."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from excelclone.core.refs import CellReference, RangeReference
from excelclone.core.workbook import Workbook

CHART_TYPES = frozenset(
    {
        "area",
        "bar",
        "box",
        "column",
        "combo",
        "donut",
        "heatmap",
        "histogram",
        "line",
        "pie",
        "radar",
        "scatter",
        "stacked_area",
        "stacked_bar",
        "stacked_column",
        "step",
        "waterfall",
    }
)
CHART_TYPE_LABELS = {
    "area": "Area",
    "bar": "Horizontal Bars",
    "box": "Box and Whisker",
    "column": "Clustered Columns",
    "combo": "Column + Line Combo",
    "donut": "Donut",
    "heatmap": "Heatmap",
    "histogram": "Histogram",
    "line": "Line",
    "pie": "Pie",
    "radar": "Radar",
    "scatter": "Scatter",
    "stacked_area": "Stacked Area",
    "stacked_bar": "Stacked Horizontal Bars",
    "stacked_column": "Stacked Columns",
    "step": "Step Line",
    "waterfall": "Waterfall",
}
LEGEND_POSITIONS = frozenset({"right", "left", "top", "bottom", "none"})
CHART_THEMES = frozenset(
    {"executive", "coastal", "editorial", "monochrome", "high_contrast"}
)
NUMBER_FORMATS = frozenset({"auto", "number", "currency", "percent"})


@dataclass(frozen=True, slots=True)
class ChartSpec:
    """Immutable chart configuration bound to a worksheet range."""

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


def chart_data(workbook: Workbook, spec: ChartSpec) -> ChartData:
    """Extract current cached range values for a chart."""
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
    return ChartData(categories, tuple(series))


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
    candidates: list[ChartRecommendation] = []

    def add(chart_type: str, score: int, reason: str) -> None:
        if not any(item.chart_type == chart_type for item in candidates):
            candidates.append(ChartRecommendation(chart_type, title, reason, score))

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
        if row_count <= 10 and finite_values and all(value >= 0 for value in finite_values):
            add(
                "donut",
                76,
                "A compact non-negative series can be read as part-to-whole.",
            )
    if row_count > 12:
        add("line", 88, "Many ordered observations are more legible as a trend.")
    add("bar", 70, "Horizontal bars remain readable when category labels are long.")
    add("line", 68, "A line chart provides a compact general trend view.")
    return tuple(sorted(candidates, key=lambda item: item.score, reverse=True)[:5])


def _numeric_value(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return math.nan
