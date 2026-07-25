"""Spreadsheet fill-series generation."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any

from excelclone.core.cell import Cell
from excelclone.core.refs import CellReference, RangeReference, Reference
from excelclone.core.sheet import Sheet
from excelclone.core.translation import translate_formula_copy

_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_WEEKDAYS_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_MONTHS_SHORT = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_NAME_SEQUENCES = (_WEEKDAYS, _WEEKDAYS_SHORT, _MONTHS, _MONTHS_SHORT)


def fill_range(sheet: Sheet, source: Reference, target: Reference) -> None:
    """Fill a target from a source with formula and series translation."""
    source_bounds = _bounds(source)
    target_bounds = _bounds(target)
    source_min_row, source_min_column, source_max_row, source_max_column = source_bounds
    target_min_row, target_min_column, target_max_row, target_max_column = target_bounds
    source_height = source_max_row - source_min_row + 1
    source_width = source_max_column - source_min_column + 1
    target_height = target_max_row - target_min_row + 1
    target_width = target_max_column - target_min_column + 1
    if target_width != source_width and target_height != source_height:
        raise ValueError("Fill target must extend the source along one axis")

    original = {
        (row, column): sheet.get_cell(row, column)
        for row in range(source_min_row, source_max_row + 1)
        for column in range(source_min_column, source_max_column + 1)
    }
    vertical = target_height != source_height
    for row in range(target_min_row, target_max_row + 1):
        for column in range(target_min_column, target_max_column + 1):
            if (row, column) in original:
                continue
            if vertical:
                source_column = source_min_column + (column - target_min_column)
                sequence = [
                    original[(source_row, source_column)]
                    for source_row in range(source_min_row, source_max_row + 1)
                ]
                position = row - target_min_row
                template_row = source_min_row + position % source_height
                template_column = source_column
            else:
                source_row = source_min_row + (row - target_min_row)
                sequence = [
                    original[(source_row, source_column)]
                    for source_column in range(source_min_column, source_max_column + 1)
                ]
                position = column - target_min_column
                template_row = source_row
                template_column = source_min_column + position % source_width
            template = original[(template_row, template_column)]
            generated = _filled_cell(
                sequence,
                position,
                template,
                row_delta=row - template_row,
                column_delta=column - template_column,
            )
            sheet.put_cell(row, column, generated)


def _filled_cell(
    sequence: list[Cell],
    position: int,
    template: Cell,
    *,
    row_delta: int,
    column_delta: int,
) -> Cell:
    if template.is_formula:
        return replace(
            template,
            raw_input=translate_formula_copy(
                template.raw_input,
                rows=row_delta,
                columns=column_delta,
            ),
            cached_value=None,
            error=None,
            spill_parent=None,
        )
    values = [cell.display_value for cell in sequence]
    generated = _series_value(values, position)
    if generated is None:
        generated = template.raw_input
    return Cell(
        raw_input=generated,
        cached_value=generated,
        format=template.format,
        hyperlink=template.hyperlink,
    )


def _series_value(values: list[Any], position: int) -> Any:
    if len(values) >= 2 and all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in values
    ):
        step = values[1] - values[0]
        result = values[0] + step * position
        return int(result) if all(isinstance(value, int) for value in values) else result
    if len(values) >= 2 and all(
        isinstance(value, (date, datetime)) for value in values
    ):
        step = values[1] - values[0]
        return values[0] + step * position
    if values and isinstance(values[0], str):
        for names in _NAME_SEQUENCES:
            folded = [name.casefold() for name in names]
            if values[0].casefold() in folded:
                start = folded.index(values[0].casefold())
                step = 1
                if len(values) >= 2 and isinstance(values[1], str):
                    if values[1].casefold() in folded:
                        step = folded.index(values[1].casefold()) - start
                return names[(start + step * position) % len(names)]
    return None


def _bounds(reference: Reference) -> tuple[int, int, int, int]:
    if isinstance(reference, CellReference):
        return reference.row, reference.column, reference.row, reference.column
    return (
        reference.min_row,
        reference.min_column,
        reference.max_row,
        reference.max_column,
    )
