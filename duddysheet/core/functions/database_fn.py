"""Excel's database functions (DSUM, DAVERAGE, DGET, ...) over list ranges.

A database is a range whose first row holds field labels. A criteria range
also starts with labels; conditions in one row must all hold (AND), and any
row may match (OR). A criterion under a label that is not a field name, or
under an empty label, is a computed criterion: a formula evaluated for each
record, where references to the first data row move with the record.
"""

from __future__ import annotations

import math
from typing import Any

from duddysheet.core.errors import (
    DIV_ZERO_ERROR,
    NUM_ERROR,
    VALUE_ERROR,
    is_error,
)
from duddysheet.core.functions import register
from duddysheet.core.functions.common import criteria_match, number, scalar, text

DATABASE = "Database"


def _labels(row: list[Any]) -> list[str]:
    return [text(value).strip().casefold() for value in row]


def _field_index(context: Any, field: Any, labels: list[str]) -> Any:
    selected = scalar(context, field)
    if is_error(selected):
        return selected
    if selected is None:
        return None
    if isinstance(selected, str):
        folded = selected.strip().casefold()
        return labels.index(folded) if folded in labels else VALUE_ERROR
    converted = number(selected)
    if is_error(converted):
        return VALUE_ERROR
    index = math.trunc(converted) - 1
    return index if 0 <= index < len(labels) else VALUE_ERROR


def _computed_match(
    context: Any,
    formula_cell: Any,
    database_reference: Any,
    offset: int,
) -> bool:
    """Evaluate a computed criterion with references shifted to one record."""
    from duddysheet.core.parser import parse_formula, shift_references

    if formula_cell is None or not formula_cell.is_formula:
        return False
    try:
        ast = parse_formula(formula_cell.raw_input)
    except ValueError:
        return False
    shifted = shift_references(ast, rows=offset)
    result = context.evaluator.evaluate(
        shifted,
        sheet_name=context.sheet_name,
        origin=context.origin,
    )
    if is_error(result) or isinstance(result, tuple):
        return False
    return bool(result) if not isinstance(result, str) else False


def _criteria_cells(context: Any, criteria: Any) -> list[list[Any]]:
    """Cells (not just values) of the criteria range, so formulas are visible."""
    from duddysheet.core.refs import CellReference, RangeReference

    areas = getattr(criteria, "areas", None)
    if not areas:
        return []
    area = areas[0]
    if isinstance(area, CellReference):
        area = RangeReference(area, area)
    sheet = context.evaluator.workbook.get_sheet(area.sheet or context.sheet_name)
    min_row, max_row, min_column, max_column = context.evaluator.reference_bounds(area)
    return sheet.cell_block(min_row, min_column, max_row, max_column)


def _selected_records(context: Any, database: Any, criteria: Any) -> Any:
    rows = context.matrix(database)
    if len(rows) < 1:
        return VALUE_ERROR
    labels = _labels(rows[0])
    records = rows[1:]
    criteria_rows = context.matrix(criteria)
    if not criteria_rows:
        return VALUE_ERROR
    criteria_labels = _labels(criteria_rows[0])
    criteria_cells = _criteria_cells(context, criteria)
    conditions: list[list[tuple[str, Any, Any]]] = []
    for row_index, row in enumerate(criteria_rows[1:], start=1):
        line: list[tuple[str, Any, Any]] = []
        for column_index, value in enumerate(row):
            cell = (
                criteria_cells[row_index][column_index]
                if criteria_cells and row_index < len(criteria_cells)
                else None
            )
            label = criteria_labels[column_index] if column_index < len(criteria_labels) else ""
            if label and label in labels:
                if value is None or value == "":
                    continue
                line.append(("field", labels.index(label), value))
            elif cell is not None and cell.is_formula:
                line.append(("computed", cell, None))
        conditions.append(line)
    if not conditions or all(not line for line in conditions):
        return records
    selected: list[list[Any]] = []
    for offset, record in enumerate(records):
        for line in conditions:
            if all(
                criteria_match(record[target], value)
                if kind == "field"
                else _computed_match(context, target, database, offset)
                for kind, target, value in line
            ):
                selected.append(record)
                break
    return selected


def _column_values(context: Any, database: Any, field: Any, criteria: Any) -> Any:
    rows = context.matrix(database)
    if not rows:
        return VALUE_ERROR
    labels = _labels(rows[0])
    index = _field_index(context, field, labels)
    if is_error(index):
        return index
    records = _selected_records(context, database, criteria)
    if is_error(records):
        return records
    if index is None:
        return records, None
    return records, [record[index] for record in records]


def _numbers(values: list[Any]) -> Any:
    numbers: list[float] = []
    for value in values:
        if is_error(value):
            return value
        if isinstance(value, bool) or value is None or isinstance(value, str):
            continue
        converted = number(value)
        if not is_error(converted):
            numbers.append(converted)
    return numbers


def _register(name: str, description: str, summarize: Any, *, numeric: bool = True) -> None:
    def implementation(context: Any, database: Any, field: Any, criteria: Any) -> Any:
        selection = _column_values(context, database, field, criteria)
        if is_error(selection):
            return selection
        records, values = selection
        if values is None:
            if name in ("DCOUNT", "DCOUNTA"):
                values = [record for record in records]
                return len(values)
            return VALUE_ERROR
        if numeric:
            numbers = _numbers(values)
            if is_error(numbers):
                return numbers
            return summarize(numbers)
        return summarize(values)

    implementation.__doc__ = description
    register(
        name,
        min_args=3,
        max_args=3,
        argument_spec="database, field, criteria",
        category=DATABASE,
    )(implementation)


def _variance(values: list[float], sample: bool) -> Any:
    count = len(values)
    if count < (2 if sample else 1):
        return DIV_ZERO_ERROR
    centre = math.fsum(values) / count
    return math.fsum((value - centre) ** 2 for value in values) / (count - 1 if sample else count)


def _dget(values: list[Any]) -> Any:
    if not values:
        return VALUE_ERROR
    if len(values) > 1:
        return NUM_ERROR
    return values[0]


_register("DSUM", "Add the numbers in a database field that match criteria.", math.fsum)
_register(
    "DAVERAGE",
    "Average the numbers in a database field that match criteria.",
    lambda values: DIV_ZERO_ERROR if not values else math.fsum(values) / len(values),
)
_register("DCOUNT", "Count the numeric cells in a database field that match criteria.", len)
_register(
    "DCOUNTA",
    "Count the nonblank cells in a database field that match criteria.",
    lambda values: sum(value is not None and value != "" for value in values),
    numeric=False,
)
_register("DMAX", "Return the largest number in a database field that matches criteria.", lambda values: max(values) if values else 0)
_register("DMIN", "Return the smallest number in a database field that matches criteria.", lambda values: min(values) if values else 0)
_register("DPRODUCT", "Multiply the numbers in a database field that match criteria.", lambda values: math.prod(values) if values else 0)
_register("DSTDEV", "Estimate standard deviation from a database sample.", lambda values: _sqrt(_variance(values, True)))
_register("DSTDEVP", "Return the population standard deviation of database entries.", lambda values: _sqrt(_variance(values, False)))
_register("DVAR", "Estimate variance from a database sample.", lambda values: _variance(values, True))
_register("DVARP", "Return the population variance of database entries.", lambda values: _variance(values, False))
_register("DGET", "Extract the single record value that matches criteria.", _dget, numeric=False)


def _sqrt(value: Any) -> Any:
    return value if is_error(value) else math.sqrt(value)
