"""Excel's keyboard navigation and selection arithmetic, independent of Qt.

Coordinates are zero-based (row, column). Selection ranges are inclusive
``(top, left, bottom, right)`` tuples, so a whole column is one cheap range
rather than a million cell objects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from duddysheet.core.refs import MAX_COLUMNS, MAX_ROWS
from duddysheet.core.sheet import Sheet

SelectionRange = tuple[int, int, int, int]


def _filled(sheet: Sheet, row: int, column: int) -> bool:
    cell = sheet.get_cell(row, column)
    return cell.display_value not in (None, "") or cell.is_formula


def data_edge(sheet: Sheet, row: int, column: int, d_row: int, d_column: int) -> tuple[int, int]:
    """Return where Ctrl+Arrow lands from (row, column) moving (d_row, d_column).

    From a filled cell next to a filled cell, move to the last filled cell of
    that run; otherwise move to the next filled cell; with none, stop at the
    sheet edge.
    """
    limit_row = MAX_ROWS - 1
    limit_column = MAX_COLUMNS - 1

    def inside(r: int, c: int) -> bool:
        return 0 <= r <= limit_row and 0 <= c <= limit_column

    next_row, next_column = row + d_row, column + d_column
    if not inside(next_row, next_column):
        return row, column
    if _filled(sheet, row, column) and _filled(sheet, next_row, next_column):
        r, c = next_row, next_column
        while inside(r + d_row, c + d_column) and _filled(sheet, r + d_row, c + d_column):
            r, c = r + d_row, c + d_column
        return r, c
    # Jump to the next filled cell, scanning only populated coordinates.
    target = _next_filled(sheet, row, column, d_row, d_column)
    if target is not None:
        return target
    if d_row:
        return (limit_row if d_row > 0 else 0), column
    return row, (limit_column if d_column > 0 else 0)


def _next_filled(
    sheet: Sheet,
    row: int,
    column: int,
    d_row: int,
    d_column: int,
) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    best_distance = math.inf
    for (r, c), cell in sheet.iter_unordered():
        if cell.display_value in (None, "") and not cell.is_formula:
            continue
        if d_row and c == column:
            distance = (r - row) * d_row
        elif d_column and r == row:
            distance = (c - column) * d_column
        else:
            continue
        if 0 < distance < best_distance:
            best_distance = distance
            best = (r, c)
    return best


def current_region(sheet: Sheet, row: int, column: int) -> SelectionRange:
    """Return the data region around a cell, as Ctrl+A and Ctrl+* select it."""
    top = bottom = row
    left = right = column
    changed = True
    while changed:
        changed = False
        if top > 0 and any(_filled(sheet, top - 1, c) for c in range(max(0, left - 1), min(MAX_COLUMNS - 1, right + 1) + 1)):
            top -= 1
            changed = True
        if bottom < MAX_ROWS - 1 and any(_filled(sheet, bottom + 1, c) for c in range(max(0, left - 1), min(MAX_COLUMNS - 1, right + 1) + 1)):
            bottom += 1
            changed = True
        if left > 0 and any(_filled(sheet, r, left - 1) for r in range(max(0, top - 1), min(MAX_ROWS - 1, bottom + 1) + 1)):
            left -= 1
            changed = True
        if right < MAX_COLUMNS - 1 and any(_filled(sheet, r, right + 1) for r in range(max(0, top - 1), min(MAX_ROWS - 1, bottom + 1) + 1)):
            right += 1
            changed = True
    return top, left, bottom, right


def last_cell(sheet: Sheet) -> tuple[int, int]:
    """Return the cell Ctrl+End selects: the last used row and column."""
    max_row, max_column = sheet.extent
    return max(0, max_row), max(0, max_column)


def clip_range(sheet: Sheet, selection: SelectionRange) -> SelectionRange | None:
    """Clip a selection to the sheet's populated extent; ``None`` when empty."""
    top, left, bottom, right = selection
    max_row, max_column = sheet.extent
    bottom = min(bottom, max_row)
    right = min(right, max_column)
    if bottom < top or right < left:
        return None
    return top, left, bottom, right


@dataclass(frozen=True, slots=True)
class SelectionStatistics:
    """The status bar figures Excel shows for a multi-cell selection."""

    count: int
    numerical_count: int
    total: float
    minimum: float | None
    maximum: float | None

    @property
    def average(self) -> float | None:
        """Return the mean of numeric cells, if any."""
        return self.total / self.numerical_count if self.numerical_count else None


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (date, datetime)):
        from duddysheet.core.values import date_serial

        return date_serial(value)
    return None


def selection_statistics(sheet: Sheet, ranges: list[SelectionRange]) -> SelectionStatistics:
    """Count, sum, and bound the populated cells covered by selection ranges."""
    seen: set[tuple[int, int]] = set()
    count = numerical = 0
    total = 0.0
    minimum: float | None = None
    maximum: float | None = None
    area = sum((bottom - top + 1) * (right - left + 1) for top, left, bottom, right in ranges)
    if area <= 4096:
        coordinates = (
            (row, column)
            for top, left, bottom, right in ranges
            for row in range(top, bottom + 1)
            for column in range(left, right + 1)
        )
        cells = ((coordinate, sheet.get_cell(*coordinate)) for coordinate in coordinates)
    else:
        cells = (
            (coordinate, cell)
            for coordinate, cell in sheet.iter_unordered()
            if any(
                top <= coordinate[0] <= bottom and left <= coordinate[1] <= right
                for top, left, bottom, right in ranges
            )
        )
    for coordinate, cell in cells:
        if coordinate in seen:
            continue
        seen.add(coordinate)
        if cell.error is not None:
            count += 1
            continue
        value = cell.display_value
        if value is None or value == "":
            continue
        count += 1
        number = _numeric(value)
        if number is None:
            continue
        numerical += 1
        total += number
        minimum = number if minimum is None else min(minimum, number)
        maximum = number if maximum is None else max(maximum, number)
    return SelectionStatistics(count, numerical, total, minimum, maximum)
