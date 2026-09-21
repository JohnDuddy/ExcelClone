"""Sparse structural workbook operations."""

from __future__ import annotations

from dataclasses import replace

from duddysheet.core.conditional import ConditionalRule
from duddysheet.core.chart import ChartSpec
from duddysheet.core.data_tools import AutoFilter, DataValidation
from duddysheet.core.refs import CellReference, RangeReference
from duddysheet.core.refs import MAX_COLUMNS, MAX_ROWS
from duddysheet.core.sparkline import Sparkline
from duddysheet.core.translation import (
    translate_formula_structure,
    translate_reference_structure,
)
from duddysheet.core.workbook import Workbook


def edit_structure(
    workbook: Workbook,
    sheet_name: str,
    *,
    axis: str,
    index: int,
    count: int,
    delete: bool,
) -> None:
    """Insert or delete rows/columns and translate workbook references."""
    if axis not in ("row", "column"):
        raise ValueError(f"Unknown structure axis: {axis!r}")
    limit = MAX_ROWS if axis == "row" else MAX_COLUMNS
    if count < 1:
        raise ValueError("Structural edit count must be positive")
    if not 0 <= index < limit or index + count > limit:
        raise IndexError("Structural edit is outside the worksheet")
    target = workbook.get_sheet(sheet_name)

    for formula_sheet in workbook:
        for (row, column), cell in tuple(formula_sheet.iter_populated()):
            if not cell.is_formula:
                continue
            formula_sheet.put_cell(
                row,
                column,
                replace(
                    cell,
                    raw_input=translate_formula_structure(
                        cell.raw_input,
                        formula_sheet=formula_sheet.name,
                        target_sheet=target.name,
                        axis=axis,
                        index=index,
                        count=count,
                        delete=delete,
                    ),
                    cached_value=None,
                    error=None,
                ),
            )
        translated_charts: list[object] = []
        for chart in formula_sheet.charts:
            if not isinstance(chart, ChartSpec) or (
                chart.sheet_name.casefold() != target.name.casefold()
            ):
                translated_charts.append(chart)
                continue
            translated_range = translate_reference_structure(
                chart.source_range,
                axis=axis,
                index=index,
                count=count,
                delete=delete,
            )
            if isinstance(translated_range, RangeReference):
                translated_charts.append(
                    replace(chart, source_range=translated_range)
                )
        formula_sheet.charts = translated_charts
        formula_sheet.sparklines = _translate_sparklines(
            formula_sheet.sparklines,
            owner_name=formula_sheet.name,
            owner_is_target=formula_sheet is target,
            target_name=target.name,
            axis=axis,
            index=index,
            count=count,
            delete=delete,
        )

    _move_cells(target, axis=axis, index=index, count=count, delete=delete)
    if axis == "row":
        target.row_heights = _move_index_map(
            target.row_heights,
            index=index,
            count=count,
            delete=delete,
            limit=MAX_ROWS,
        )
        target.hidden_rows = _move_index_set(
            target.hidden_rows,
            index=index,
            count=count,
            delete=delete,
            limit=MAX_ROWS,
        )
    else:
        target.column_widths = _move_index_map(
            target.column_widths,
            index=index,
            count=count,
            delete=delete,
            limit=MAX_COLUMNS,
        )
        target.hidden_columns = _move_index_set(
            target.hidden_columns,
            index=index,
            count=count,
            delete=delete,
            limit=MAX_COLUMNS,
        )
    target.merged_ranges = [
        translated
        for reference in target.merged_ranges
        if (
            translated := translate_reference_structure(
                reference,
                axis=axis,
                index=index,
                count=count,
                delete=delete,
            )
        )
        is not None
    ]
    target.conditional_formats = [
        replace(rule, range=translated)
        for rule in target.conditional_formats
        if isinstance(rule, ConditionalRule)
        and (
            translated := translate_reference_structure(
                rule.range,
                axis=axis,
                index=index,
                count=count,
                delete=delete,
            )
        )
        is not None
    ]
    translated_validations: list[DataValidation] = []
    for validation in target.data_validations:
        if not isinstance(validation, DataValidation):
            continue
        translated_range = translate_reference_structure(
            validation.range,
            axis=axis,
            index=index,
            count=count,
            delete=delete,
        )
        if translated_range is None:
            continue
        formula = validation.formula
        if formula:
            formula = translate_formula_structure(
                formula,
                formula_sheet=target.name,
                target_sheet=target.name,
                axis=axis,
                index=index,
                count=count,
                delete=delete,
            )
        translated_validations.append(
            replace(validation, range=translated_range, formula=formula)
        )
    target.data_validations = translated_validations

    auto_filter = target.auto_filter
    if isinstance(auto_filter, AutoFilter):
        translated_range = translate_reference_structure(
            auto_filter.range,
            axis=axis,
            index=index,
            count=count,
            delete=delete,
        )
        translated_column = _move_index(
            auto_filter.column,
            index=index,
            count=count,
            delete=delete,
            limit=MAX_COLUMNS,
        ) if axis == "column" else auto_filter.column
        target.auto_filter = (
            replace(
                auto_filter,
                range=translated_range,
                column=translated_column,
            )
            if isinstance(translated_range, RangeReference)
            and translated_column is not None
            else None
        )
    if axis == "row":
        target.filtered_rows = _move_index_set(
            target.filtered_rows,
            index=index,
            count=count,
            delete=delete,
            limit=MAX_ROWS,
        )
    if target.freeze_panes is not None:
        row, column = target.freeze_panes
        coordinate = row if axis == "row" else column
        translated = _move_index(
            coordinate,
            index=index,
            count=count,
            delete=delete,
            limit=limit,
        )
        translated = index if translated is None else translated
        target.freeze_panes = (
            (translated, column) if axis == "row" else (row, translated)
        )


def _move_cells(
    sheet: object,
    *,
    axis: str,
    index: int,
    count: int,
    delete: bool,
) -> None:
    cells = tuple(sheet.iter_populated())
    for (row, column), _ in cells:
        sheet.clear_cell(row, column)
    limit = MAX_ROWS if axis == "row" else MAX_COLUMNS
    for (row, column), cell in cells:
        coordinate = row if axis == "row" else column
        moved = _move_index(
            coordinate,
            index=index,
            count=count,
            delete=delete,
            limit=limit,
        )
        if moved is None:
            continue
        target_row, target_column = (
            (moved, column) if axis == "row" else (row, moved)
        )
        sheet.put_cell(target_row, target_column, cell)


def _move_index(
    value: int,
    *,
    index: int,
    count: int,
    delete: bool,
    limit: int,
) -> int | None:
    if delete:
        if index <= value < index + count:
            return None
        return value - count if value >= index + count else value
    translated = value + count if value >= index else value
    return translated if translated < limit else None


def _move_index_map(
    values: dict[int, float],
    *,
    index: int,
    count: int,
    delete: bool,
    limit: int,
) -> dict[int, float]:
    result: dict[int, float] = {}
    for key, value in values.items():
        translated = _move_index(
            key,
            index=index,
            count=count,
            delete=delete,
            limit=limit,
        )
        if translated is not None:
            result[translated] = value
    return result


def _move_index_set(
    values: set[int],
    *,
    index: int,
    count: int,
    delete: bool,
    limit: int,
) -> set[int]:
    return {
        translated
        for value in values
        if (
            translated := _move_index(
                value,
                index=index,
                count=count,
                delete=delete,
                limit=limit,
            )
        )
        is not None
    }


def _translate_sparklines(
    sparklines: list[object],
    *,
    owner_name: str,
    owner_is_target: bool,
    target_name: str,
    axis: str,
    index: int,
    count: int,
    delete: bool,
) -> list[object]:
    """Move sparkline cells and data ranges with a structural edit.

    A sparkline whose cell or whole data range is deleted is removed, as in
    Excel.
    """
    translated: list[object] = []
    for sparkline in sparklines:
        if not isinstance(sparkline, Sparkline):
            translated.append(sparkline)
            continue
        data_range = sparkline.data_range
        data_sheet = data_range.sheet or owner_name
        if data_sheet.casefold() == target_name.casefold():
            moved_range = translate_reference_structure(
                data_range, axis=axis, index=index, count=count, delete=delete
            )
            if not isinstance(moved_range, RangeReference):
                continue
            data_range = moved_range
        row, column = sparkline.row, sparkline.column
        if owner_is_target:
            moved_cell = translate_reference_structure(
                CellReference(row, column),
                axis=axis,
                index=index,
                count=count,
                delete=delete,
            )
            if not isinstance(moved_cell, CellReference):
                continue
            row, column = moved_cell.row, moved_cell.column
        translated.append(
            replace(sparkline, row=row, column=column, data_range=data_range)
        )
    return translated
