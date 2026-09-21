"""In-cell sparkline specifications and value extraction."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from duddysheet.core.refs import CellReference, RangeReference
from duddysheet.core.workbook import Workbook

SPARKLINE_KINDS = ("line", "column", "win_loss")
SPARKLINE_KIND_LABELS = {
    "line": "Line",
    "column": "Column",
    "win_loss": "Win/Loss",
}


@dataclass(frozen=True, slots=True)
class Sparkline:
    """A tiny chart drawn inside one cell from a one-dimensional data range."""

    row: int
    column: int
    data_range: RangeReference
    kind: str = "line"
    color: str = "#2f6fb0"
    negative_color: str = "#c0392b"
    marker_color: str = "#d9822b"
    show_markers: bool = False
    show_high: bool = False
    show_low: bool = False
    show_first: bool = False
    show_last: bool = False
    show_negative: bool = False
    show_axis: bool = False

    def __post_init__(self) -> None:
        if self.kind not in SPARKLINE_KINDS:
            raise ValueError(f"Unsupported sparkline type: {self.kind!r}")
        if (
            self.data_range.min_row != self.data_range.max_row
            and self.data_range.min_column != self.data_range.max_column
        ):
            raise ValueError("A sparkline's data must be a single row or column")


def build_sparklines(
    data_range: RangeReference,
    location: RangeReference | CellReference,
    kind: str,
    **options: Any,
) -> tuple[Sparkline, ...]:
    """Create one sparkline per location cell, as Excel's Create Sparklines does.

    A single location cell takes a one-row or one-column data range. A
    location column takes one data row per cell, and a location row takes one
    data column per cell.
    """
    if isinstance(location, CellReference):
        location = RangeReference(location, location)
    if location.min_row != location.max_row and location.min_column != location.max_column:
        raise ValueError("The location range must be a single row or column")
    cells = [(cell.row, cell.column) for cell in location]
    sheet = data_range.sheet
    if len(cells) == 1:
        row, column = cells[0]
        return (Sparkline(row, column, data_range, kind, **options),)
    height = data_range.max_row - data_range.min_row + 1
    width = data_range.max_column - data_range.min_column + 1
    vertical = location.min_column == location.max_column
    if vertical and height == len(cells):
        slices = [
            RangeReference(
                CellReference(data_range.min_row + offset, data_range.min_column, sheet),
                CellReference(data_range.min_row + offset, data_range.max_column, sheet),
            )
            for offset in range(height)
        ]
    elif not vertical and width == len(cells):
        slices = [
            RangeReference(
                CellReference(data_range.min_row, data_range.min_column + offset, sheet),
                CellReference(data_range.max_row, data_range.min_column + offset, sheet),
            )
            for offset in range(width)
        ]
    else:
        raise ValueError(
            "The data range must have one row (for a location column) or one "
            "column (for a location row) per location cell"
        )
    return tuple(
        Sparkline(row, column, data, kind, **options)
        for (row, column), data in zip(cells, slices)
    )


def sparkline_values(
    workbook: Workbook,
    sheet_name: str,
    sparkline: Sparkline,
) -> tuple[float, ...]:
    """Return the sparkline's current numeric values; blanks become NaN."""
    source = workbook.get_sheet(sparkline.data_range.sheet or sheet_name)
    values = []
    for cell in sparkline.data_range:
        value = source.get_cell(cell.row, cell.column).display_value
        values.append(
            float(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else math.nan
        )
    return tuple(values)


def sparkline_at(sparklines: list[Any], row: int, column: int) -> Sparkline | None:
    """Return the sparkline anchored at one cell, if any."""
    for item in sparklines:
        if isinstance(item, Sparkline) and item.row == row and item.column == column:
            return item
    return None
