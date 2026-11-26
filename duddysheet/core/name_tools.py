"""Name Manager helpers: Create from Selection and name suggestions."""

from __future__ import annotations

import re
from typing import Any

from duddysheet.core.refs import CellReference, RangeReference

_INVALID = re.compile(r"[^A-Za-z0-9_.\\]")


def name_from_label(label: Any) -> str | None:
    """Turn a heading such as 'Unit Price' into a valid name such as 'Unit_Price'."""
    if label is None:
        return None
    text = str(label).strip()
    if not text:
        return None
    candidate = _INVALID.sub("_", text)
    if candidate[0].isdigit():
        candidate = "_" + candidate
    return candidate


def names_from_selection(
    sheet: Any,
    area: tuple[int, int, int, int],
    *,
    top_row: bool = False,
    left_column: bool = False,
    bottom_row: bool = False,
    right_column: bool = False,
) -> list[tuple[str, RangeReference | CellReference]]:
    """Return (name, reference) pairs Excel's Create from Selection would define."""
    top, left, bottom, right = area
    created: list[tuple[str, RangeReference | CellReference]] = []

    def reference(row1: int, column1: int, row2: int, column2: int) -> RangeReference | CellReference:
        start = CellReference(row1, column1, sheet=sheet.name, row_absolute=True, column_absolute=True)
        if (row1, column1) == (row2, column2):
            return start
        end = CellReference(row2, column2, sheet=sheet.name, row_absolute=True, column_absolute=True)
        return RangeReference(start, end)

    body_top = top + (1 if top_row else 0)
    body_bottom = bottom - (1 if bottom_row else 0)
    body_left = left + (1 if left_column else 0)
    body_right = right - (1 if right_column else 0)
    if top_row or bottom_row:
        label_row = top if top_row else bottom
        for column in range(body_left, body_right + 1):
            name = name_from_label(sheet.get_cell(label_row, column).display_value)
            if name and body_top <= body_bottom:
                created.append((name, reference(body_top, column, body_bottom, column)))
    if left_column or right_column:
        label_column = left if left_column else right
        for row in range(body_top, body_bottom + 1):
            name = name_from_label(sheet.get_cell(row, label_column).display_value)
            if name and body_left <= body_right:
                created.append((name, reference(row, body_left, row, body_right)))
    return created
