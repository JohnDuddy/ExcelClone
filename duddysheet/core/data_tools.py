"""Headless sort, filter, validation, find, and cleanup tools."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from functools import cmp_to_key
from typing import Any

from duddysheet.core.cell import Cell
from duddysheet.core.evaluator import FormulaEvaluator
from duddysheet.core.parser import parse_formula, shift_references
from duddysheet.core.refs import CellReference, RangeReference, Reference
from duddysheet.core.sheet import Sheet
from duddysheet.core.translation import translate_formula_copy
from duddysheet.core.workbook import Workbook


@dataclass(frozen=True, slots=True)
class SortKey:
    """One absolute worksheet column used by a range sort."""

    column: int
    ascending: bool = True
    case_sensitive: bool = False


@dataclass(frozen=True, slots=True)
class AutoFilter:
    """Current value-list filter for one table range."""

    range: RangeReference
    column: int
    allowed_values: frozenset[Any]
    has_header: bool = True


@dataclass(frozen=True, slots=True)
class DataValidation:
    """One input constraint applied to a cell range."""

    range: Reference
    kind: str
    operator: str = "between"
    values: tuple[Any, ...] = ()
    formula: str | None = None
    allow_blank: bool = True
    input_message: str = ""
    error_message: str = "The value does not satisfy this cell's validation rule."


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Validation outcome and optional user-facing error."""

    valid: bool
    message: str = ""


@dataclass(frozen=True, slots=True)
class FindOptions:
    """Search scope and matching behavior."""

    query: str
    replacement: str = ""
    match_case: bool = False
    regex: bool = False
    look_in: str = "values"
    whole_cell: bool = False


def sort_range(
    workbook: Workbook,
    sheet_name: str,
    target: RangeReference,
    keys: tuple[SortKey, ...],
    *,
    has_header: bool = False,
) -> None:
    """Sort complete rows in a rectangle using ordered keys."""
    if not keys:
        raise ValueError("Sort requires at least one key")
    if any(not target.min_column <= key.column <= target.max_column for key in keys):
        raise ValueError("Sort key is outside the target range")
    sheet = workbook.get_sheet(sheet_name)
    first_data_row = target.min_row + (1 if has_header else 0)
    rows = [
        (
            row,
            tuple(
                sheet.get_cell(row, column)
                for column in range(target.min_column, target.max_column + 1)
            ),
        )
        for row in range(first_data_row, target.max_row + 1)
    ]
    rows.sort(key=cmp_to_key(lambda left, right: _compare_rows(left, right, keys, target)))
    _write_rows(
        sheet,
        rows,
        first_data_row,
        target.min_column,
        target.max_column,
    )


def apply_filter(
    sheet: Sheet,
    target: RangeReference,
    *,
    column: int,
    allowed_values: set[Any] | frozenset[Any],
    has_header: bool = True,
) -> None:
    """Hide rows whose selected column value is not allowed."""
    if not target.min_column <= column <= target.max_column:
        raise ValueError("Filter column is outside the target range")
    clear_filter(sheet)
    first_data_row = target.min_row + (1 if has_header else 0)
    filtered = {
        row
        for row in range(first_data_row, target.max_row + 1)
        if sheet.get_cell(row, column).display_value not in allowed_values
    }
    sheet.filtered_rows = filtered
    sheet.hidden_rows.update(filtered)
    sheet.auto_filter = AutoFilter(
        target,
        column,
        frozenset(allowed_values),
        has_header,
    )


def clear_filter(sheet: Sheet) -> None:
    """Remove filter-generated row hiding while preserving manual hiding."""
    sheet.hidden_rows.difference_update(sheet.filtered_rows)
    sheet.filtered_rows.clear()
    sheet.auto_filter = None


def validation_for_cell(
    sheet: Sheet,
    row: int,
    column: int,
) -> DataValidation | None:
    """Return the last validation rule covering a coordinate."""
    for validation in reversed(sheet.data_validations):
        if isinstance(validation, DataValidation) and _reference_contains(
            validation.range,
            row,
            column,
        ):
            return validation
    return None


def validate_value(
    validation: DataValidation,
    value: Any,
    workbook: Workbook,
    sheet_name: str,
    origin: tuple[int, int],
) -> ValidationResult:
    """Evaluate one candidate value against a validation rule."""
    if value in (None, ""):
        valid = validation.allow_blank
        return ValidationResult(valid, "" if valid else validation.error_message)
    kind = validation.kind
    valid = False
    if kind == "list":
        valid = value in validation.values
    elif kind == "whole_number":
        valid = (
            isinstance(value, int)
            and not isinstance(value, bool)
            and _compare_validation(value, validation.operator, validation.values)
        )
    elif kind == "decimal":
        valid = (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and _compare_validation(float(value), validation.operator, validation.values)
        )
    elif kind == "date":
        converted = value.date() if isinstance(value, datetime) else value
        valid = isinstance(converted, date) and _compare_validation(
            converted,
            validation.operator,
            validation.values,
        )
    elif kind == "text_length":
        valid = _compare_validation(
            len(str(value)),
            validation.operator,
            validation.values,
        )
    elif kind == "custom" and validation.formula:
        try:
            base_row, base_column = _reference_origin(validation.range)
            evaluation_workbook = workbook.copy()
            evaluation_sheet = evaluation_workbook.get_sheet(sheet_name)
            current = evaluation_sheet.get_cell(*origin)
            evaluation_sheet.set_cell(
                origin[0],
                origin[1],
                value,
                cell_format=current.format,
            )
            formula = shift_references(
                parse_formula(validation.formula),
                rows=origin[0] - base_row,
                columns=origin[1] - base_column,
            )
            valid = bool(
                FormulaEvaluator(evaluation_workbook).evaluate(
                    formula,
                    sheet_name=sheet_name,
                    origin=origin,
                )
            )
        except ValueError:
            valid = False
    return ValidationResult(valid, "" if valid else validation.error_message)


def find_cells(
    workbook: Workbook,
    options: FindOptions,
    *,
    sheet_name: str | None = None,
) -> tuple[CellReference, ...]:
    """Find populated cells in deterministic workbook order."""
    if options.look_in not in ("values", "formulas"):
        raise ValueError("Find scope must be 'values' or 'formulas'")
    flags = 0 if options.match_case else re.IGNORECASE
    pattern = (
        re.compile(options.query, flags)
        if options.regex
        else re.compile(re.escape(options.query), flags)
    )
    sheets = (
        (workbook.get_sheet(sheet_name),)
        if sheet_name is not None
        else tuple(workbook)
    )
    found: list[CellReference] = []
    for sheet in sheets:
        for (row, column), cell in sheet.iter_populated():
            if options.look_in == "formulas":
                if not cell.is_formula:
                    continue
                text = str(cell.raw_input)
            else:
                text = "" if cell.display_value is None else str(cell.display_value)
            matched = (
                pattern.fullmatch(text) is not None
                if options.whole_cell
                else pattern.search(text) is not None
            )
            if matched:
                found.append(CellReference(row, column, sheet=sheet.name))
    return tuple(found)


def replace_matches(
    workbook: Workbook,
    options: FindOptions,
    *,
    sheet_name: str | None = None,
) -> int:
    """Replace matching formula text or scalar text and return the count."""
    matches = find_cells(workbook, options, sheet_name=sheet_name)
    flags = 0 if options.match_case else re.IGNORECASE
    pattern = (
        re.compile(options.query, flags)
        if options.regex
        else re.compile(re.escape(options.query), flags)
    )
    for reference in matches:
        sheet = workbook.get_sheet(reference.sheet or workbook.active_sheet.name)
        cell = sheet.get_cell(reference.row, reference.column)
        source = (
            str(cell.raw_input)
            if options.look_in == "formulas"
            else str(cell.display_value)
        )
        replacement = pattern.sub(options.replacement, source)
        sheet.put_cell(
            reference.row,
            reference.column,
            replace(cell, raw_input=replacement, cached_value=None, error=None),
        )
    return len(matches)


def remove_duplicates(
    sheet: Sheet,
    target: RangeReference,
    *,
    key_columns: tuple[int, ...],
    has_header: bool = True,
) -> int:
    """Remove duplicate rows in-place, retaining the first key occurrence."""
    if not key_columns:
        raise ValueError("Duplicate removal requires key columns")
    if any(not target.min_column <= value <= target.max_column for value in key_columns):
        raise ValueError("Duplicate key column is outside the target range")
    first = target.min_row + (1 if has_header else 0)
    seen: set[tuple[Any, ...]] = set()
    retained: list[tuple[int, tuple[Cell, ...]]] = []
    for row in range(first, target.max_row + 1):
        key = tuple(sheet.get_cell(row, column).display_value for column in key_columns)
        if key in seen:
            continue
        seen.add(key)
        retained.append(
            (
                row,
                tuple(
                    sheet.get_cell(row, column)
                    for column in range(target.min_column, target.max_column + 1)
                ),
            )
        )
    _write_rows(
        sheet,
        retained,
        first,
        target.min_column,
        target.max_column,
        clear_through=target.max_row,
    )
    return target.max_row - first + 1 - len(retained)


def text_to_columns(
    sheet: Sheet,
    target: RangeReference,
    *,
    delimiter: str = ",",
) -> int:
    """Split the first target column into adjacent columns."""
    if len(delimiter) != 1:
        raise ValueError("Text-to-columns delimiter must be one character")
    parsed_rows: list[list[str]] = []
    for row in range(target.min_row, target.max_row + 1):
        value = sheet.get_cell(row, target.min_column).display_value
        parsed_rows.append(next(csv.reader([str(value or "")], delimiter=delimiter)))
    width = max((len(items) for items in parsed_rows), default=0)
    for row_offset, values in enumerate(parsed_rows):
        row = target.min_row + row_offset
        for column_offset in range(width):
            value = values[column_offset] if column_offset < len(values) else None
            sheet.set_cell(row, target.min_column + column_offset, value)
    return width


def _compare_rows(
    left: tuple[int, tuple[Cell, ...]],
    right: tuple[int, tuple[Cell, ...]],
    keys: tuple[SortKey, ...],
    target: RangeReference,
) -> int:
    for key in keys:
        offset = key.column - target.min_column
        left_value = left[1][offset].display_value
        right_value = right[1][offset].display_value
        comparison = _compare_values(
            left_value,
            right_value,
            case_sensitive=key.case_sensitive,
        )
        if comparison:
            return comparison if key.ascending else -comparison
    return left[0] - right[0]


def _compare_values(left: Any, right: Any, *, case_sensitive: bool) -> int:
    if left is None and right is None:
        return 0
    if left is None:
        return 1
    if right is None:
        return -1
    if isinstance(left, str) and isinstance(right, str) and not case_sensitive:
        left, right = left.casefold(), right.casefold()
    try:
        return (left > right) - (left < right)
    except TypeError:
        left_text, right_text = str(left), str(right)
        return (left_text > right_text) - (left_text < right_text)


def _write_rows(
    sheet: Sheet,
    rows: list[tuple[int, tuple[Cell, ...]]],
    destination_start: int,
    minimum_column: int,
    maximum_column: int,
    *,
    clear_through: int | None = None,
) -> None:
    final_row = (
        clear_through
        if clear_through is not None
        else destination_start + len(rows) - 1
    )
    for row in range(destination_start, final_row + 1):
        for column in range(minimum_column, maximum_column + 1):
            sheet.clear_cell(row, column)
    for destination_offset, (source_row, cells) in enumerate(rows):
        destination_row = destination_start + destination_offset
        for column_offset, cell in enumerate(cells):
            selected = cell
            if cell.is_formula and destination_row != source_row:
                selected = replace(
                    cell,
                    raw_input=translate_formula_copy(
                        cell.raw_input,
                        rows=destination_row - source_row,
                    ),
                    cached_value=None,
                    error=None,
                )
            sheet.put_cell(
                destination_row,
                minimum_column + column_offset,
                selected,
            )


def _compare_validation(
    value: Any,
    operator: str,
    operands: tuple[Any, ...],
) -> bool:
    if not operands:
        return False
    first = operands[0]
    try:
        if operator == "equal":
            return value == first
        if operator == "not_equal":
            return value != first
        if operator == "greater_than":
            return value > first
        if operator == "greater_equal":
            return value >= first
        if operator == "less_than":
            return value < first
        if operator == "less_equal":
            return value <= first
        if operator == "between" and len(operands) >= 2:
            return first <= value <= operands[1]
        if operator == "not_between" and len(operands) >= 2:
            return not first <= value <= operands[1]
    except TypeError:
        return False
    return False


def _reference_origin(reference: Reference) -> tuple[int, int]:
    if isinstance(reference, CellReference):
        return reference.row, reference.column
    return reference.min_row, reference.min_column


def _reference_contains(
    reference: Reference,
    row: int,
    column: int,
) -> bool:
    if isinstance(reference, CellReference):
        return reference.row == row and reference.column == column
    return reference.contains(row, column)
