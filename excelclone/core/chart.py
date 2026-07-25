"""Headless range-bound chart specifications and data extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from excelclone.core.refs import RangeReference
from excelclone.core.workbook import Workbook

CHART_TYPES = frozenset({"column", "bar", "line", "pie", "scatter", "area", "combo"})
LEGEND_POSITIONS = frozenset({"right", "left", "top", "bottom", "none"})


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

    def __post_init__(self) -> None:
        if self.chart_type not in CHART_TYPES:
            raise ValueError(f"Unsupported chart type: {self.chart_type!r}")
        if self.legend_position not in LEGEND_POSITIONS:
            raise ValueError(
                f"Unsupported legend position: {self.legend_position!r}"
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


def _numeric_value(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0
