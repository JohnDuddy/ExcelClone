"""Excel Data-tab operations: Subtotal, Consolidate, and Advanced Filter."""

from __future__ import annotations

import math
from typing import Any

from duddysheet.core.operations import edit_structure
from duddysheet.core.refs import CellReference, RangeReference
from duddysheet.core.workbook import Workbook

Rect = tuple[int, int, int, int]
SUBTOTAL_FUNCTIONS = {
    "Sum": 9,
    "Count": 3,
    "Average": 1,
    "Max": 4,
    "Min": 5,
    "Product": 6,
    "Count Numbers": 2,
    "StdDev": 7,
    "StdDevp": 8,
    "Var": 10,
    "Varp": 11,
}


def _column_letter_range(column: int, first: int, last: int) -> str:
    start = CellReference(first, column)
    if first == last:
        return start.to_a1(include_sheet=False)
    return RangeReference(start, CellReference(last, column)).to_a1()


def insert_subtotals(
    workbook: Workbook,
    sheet_name: str,
    area: Rect,
    *,
    group_column: int,
    function: str,
    total_columns: list[int],
    summary_below: bool = True,
) -> int:
    """Insert a SUBTOTAL row at each change in ``group_column`` plus a Grand Total.

    ``area`` includes the header row. Rows are grouped in the outline with
    detail at level 2 and totals at level 1. Returns the inserted row count.
    """
    code = SUBTOTAL_FUNCTIONS[function]
    sheet = workbook.get_sheet(sheet_name)
    top, left, bottom, right = area
    first_data = top + 1
    groups: list[tuple[Any, int, int]] = []
    current_key: Any = object()
    for row in range(first_data, bottom + 1):
        key = sheet.get_cell(row, group_column).display_value
        normalized = key.casefold() if isinstance(key, str) else key
        if not groups or normalized != current_key:
            groups.append((key, row, row))
            current_key = normalized
        else:
            label, start, _ = groups[-1]
            groups[-1] = (label, start, row)
    inserted = 0
    # Work bottom-up so earlier row numbers stay valid.
    label_suffix = " Total"
    for label, start, end in reversed(groups):
        at = end + 1 if summary_below else start
        edit_structure(workbook, sheet_name, axis="row", index=at, count=1, delete=False)
        inserted += 1
        if not summary_below:
            start, end = start + 1, end + 1
        sheet.set_cell(at, group_column, f"{label}{label_suffix}")
        for column in total_columns:
            sheet.set_cell(at, column, f"=SUBTOTAL({code},{_column_letter_range(column, start, end)})")
    last_row = bottom + inserted
    grand = last_row + 1
    edit_structure(workbook, sheet_name, axis="row", index=grand, count=1, delete=False)
    inserted += 1
    sheet.set_cell(grand, group_column, f"Grand{label_suffix}")
    for column in total_columns:
        sheet.set_cell(grand, column, f"=SUBTOTAL({code},{_column_letter_range(column, first_data, last_row)})")
    # Excel's outline: detail rows at level 2, group totals at 1, grand total 0.
    for row in range(first_data, grand):
        label = sheet.get_cell(row, group_column).display_value
        is_total = isinstance(label, str) and label.endswith(label_suffix) and any(
            "SUBTOTAL(" in str(sheet.get_cell(row, column).raw_input).upper()
            for column in total_columns
        )
        sheet.row_outline[row] = 1 if is_total else 2
    return inserted


def remove_subtotals(workbook: Workbook, sheet_name: str, area: Rect) -> int:
    """Delete rows created by Subtotal and clear their outline; returns rows removed."""
    sheet = workbook.get_sheet(sheet_name)
    top, left, bottom, right = area
    doomed = [
        row
        for row in range(top, bottom + 1)
        if any(
            sheet.get_cell(row, column).is_formula
            and "SUBTOTAL(" in str(sheet.get_cell(row, column).raw_input).upper()
            for column in range(left, right + 1)
        )
    ]
    for row in reversed(doomed):
        edit_structure(workbook, sheet_name, axis="row", index=row, count=1, delete=True)
    for row in range(top, bottom + 1 - len(doomed)):
        sheet.row_outline.pop(row, None)
        sheet.hidden_rows.discard(row)
    return len(doomed)


CONSOLIDATE_FUNCTIONS = ("Sum", "Count", "Average", "Max", "Min", "Product", "Count Numbers", "StdDev", "StdDevp", "Var", "Varp")


def _aggregate(function: str, values: list[Any]) -> Any:
    numbers = [float(value) for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    if function == "Count":
        return sum(value not in (None, "") for value in values)
    if function == "Count Numbers":
        return len(numbers)
    if not numbers:
        return None
    if function == "Sum":
        return math.fsum(numbers)
    if function == "Average":
        return math.fsum(numbers) / len(numbers)
    if function == "Max":
        return max(numbers)
    if function == "Min":
        return min(numbers)
    if function == "Product":
        return math.prod(numbers)
    mean = math.fsum(numbers) / len(numbers)
    squares = math.fsum((value - mean) ** 2 for value in numbers)
    sample = function in ("StdDev", "Var")
    if sample and len(numbers) < 2:
        return None
    variance = squares / (len(numbers) - 1 if sample else len(numbers))
    return math.sqrt(variance) if function.startswith("StdDev") else variance


def consolidate(
    workbook: Workbook,
    sources: list[tuple[str, Rect]],
    *,
    function: str = "Sum",
    top_row: bool = False,
    left_column: bool = False,
) -> list[list[Any]]:
    """Combine source ranges by position, or by row/column labels; return the grid."""
    if function not in CONSOLIDATE_FUNCTIONS:
        raise ValueError(f"Unknown consolidation function: {function!r}")
    blocks: list[list[list[Any]]] = []
    for sheet_name, (top, left, bottom, right) in sources:
        sheet = workbook.get_sheet(sheet_name)
        blocks.append(
            [
                [sheet.get_cell(row, column).display_value for column in range(left, right + 1)]
                for row in range(top, bottom + 1)
            ]
        )
    if not blocks:
        return []
    if not top_row and not left_column:
        height = max(len(block) for block in blocks)
        width = max(len(block[0]) for block in blocks)
        return [
            [
                _aggregate(
                    function,
                    [
                        block[row][column]
                        for block in blocks
                        if row < len(block) and column < len(block[0])
                    ],
                )
                for column in range(width)
            ]
            for row in range(height)
        ]
    row_labels: list[Any] = []
    column_labels: list[Any] = []
    cells: dict[tuple[Any, Any], list[Any]] = {}

    def key(value: Any) -> Any:
        return value.casefold() if isinstance(value, str) else value

    for block in blocks:
        headers = block[0][1 if left_column else 0 :] if top_row else None
        body = block[1:] if top_row else block
        for row_index, row in enumerate(body):
            label = row[0] if left_column else row_index
            values = row[1:] if left_column else row
            if key(label) not in [key(item) for item in row_labels]:
                row_labels.append(label)
            for column_index, value in enumerate(values):
                column_label = headers[column_index] if headers is not None else column_index
                if key(column_label) not in [key(item) for item in column_labels]:
                    column_labels.append(column_label)
                cells.setdefault((key(label), key(column_label)), []).append(value)
    grid: list[list[Any]] = []
    if top_row:
        grid.append(([None] if left_column else []) + list(column_labels))
    for label in row_labels:
        line = [label] if left_column else []
        for column_label in column_labels:
            line.append(_aggregate(function, cells.get((key(label), key(column_label)), [])))
        grid.append(line)
    return grid


def advanced_filter(
    workbook: Workbook,
    sheet_name: str,
    list_area: Rect,
    criteria: tuple[str, Rect] | None,
    *,
    unique_only: bool = False,
) -> list[int]:
    """Return data rows of ``list_area`` (excluding the header) that meet the criteria."""
    from duddysheet.core.evaluator import EvaluationContext, FormulaEvaluator, ReferenceValue
    from duddysheet.core.functions.database_fn import _selected_records

    sheet = workbook.get_sheet(sheet_name)
    top, left, bottom, right = list_area
    rows = list(range(top + 1, bottom + 1))
    if criteria is not None:
        criteria_sheet, (c_top, c_left, c_bottom, c_right) = criteria
        evaluator = FormulaEvaluator(workbook)
        context = EvaluationContext(evaluator, sheet.name, (top, left))
        database = ReferenceValue(
            (RangeReference(CellReference(top, left, sheet=sheet.name), CellReference(bottom, right, sheet=sheet.name)),)
        )
        criteria_value = ReferenceValue(
            (
                RangeReference(
                    CellReference(c_top, c_left, sheet=criteria_sheet),
                    CellReference(c_bottom, c_right, sheet=criteria_sheet),
                ),
            )
        )
        records = _selected_records(context, database, criteria_value)
        if not isinstance(records, list):
            return []
        all_records = context.matrix(database)[1:]
        selected_positions: list[int] = []
        position = 0
        for index, record in enumerate(all_records):
            if position < len(records) and record == records[position]:
                selected_positions.append(index)
                position += 1
        rows = [top + 1 + index for index in selected_positions]
    if unique_only:
        seen: set[tuple[Any, ...]] = set()
        unique: list[int] = []
        for row in rows:
            signature = tuple(
                (lambda value: value.casefold() if isinstance(value, str) else value)(
                    sheet.get_cell(row, column).display_value
                )
                for column in range(left, right + 1)
            )
            if signature not in seen:
                seen.add(signature)
                unique.append(row)
        rows = unique
    return rows
