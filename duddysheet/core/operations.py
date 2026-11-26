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

    _translate_tables(target, axis=axis, index=index, count=count, delete=delete)
    _translate_pivot_sources(workbook, target.name, axis=axis, index=index, count=count, delete=delete)
    if target.drawings:
        from duddysheet.core.drawings import shift_drawings

        target.drawings = shift_drawings(target.drawings, axis, index, count, delete)
    if target.comments:
        from duddysheet.core.comments import shift_comments

        target.comments = shift_comments(target.comments, axis, index, count, delete)
    _translate_defined_names(
        workbook,
        target_name=target.name,
        axis=axis,
        index=index,
        count=count,
        delete=delete,
    )
    _move_cells(target, axis=axis, index=index, count=count, delete=delete)
    _refresh_table_headers(target)
    if axis == "row" and not delete:
        _fill_inserted_table_rows(target, index, count)
    _move_notes(target, axis=axis, index=index, count=count, delete=delete)
    if axis == "row":
        target.row_outline = _move_index_map(
            target.row_outline,
            index=index,
            count=count,
            delete=delete,
            limit=MAX_ROWS,
        )
    else:
        target.column_outline = _move_index_map(
            target.column_outline,
            index=index,
            count=count,
            delete=delete,
            limit=MAX_COLUMNS,
        )
    if axis == "row":
        target.row_formats = _move_index_map(
            target.row_formats,
            index=index,
            count=count,
            delete=delete,
            limit=MAX_ROWS,
        )
    else:
        target.column_formats = _move_index_map(
            target.column_formats,
            index=index,
            count=count,
            delete=delete,
            limit=MAX_COLUMNS,
        )
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


def _move_notes(
    sheet: object,
    *,
    axis: str,
    index: int,
    count: int,
    delete: bool,
) -> None:
    limit = MAX_ROWS if axis == "row" else MAX_COLUMNS
    moved_notes: dict[tuple[int, int], object] = {}
    for (row, column), note in sheet.notes.items():
        coordinate = row if axis == "row" else column
        moved = _move_index(coordinate, index=index, count=count, delete=delete, limit=limit)
        if moved is None:
            continue
        moved_notes[(moved, column) if axis == "row" else (row, moved)] = note
    sheet.notes = moved_notes


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


def _translate_defined_names(
    workbook: Workbook,
    *,
    target_name: str,
    axis: str,
    index: int,
    count: int,
    delete: bool,
) -> None:
    """Move defined names with the cells they refer to, as Excel does."""
    for defined in workbook.defined_names:
        if defined.reference is not None:
            sheet = defined.reference.sheet
            if sheet is None or sheet.casefold() != target_name.casefold():
                continue
            translated = translate_reference_structure(
                defined.reference,
                axis=axis,
                index=index,
                count=count,
                delete=delete,
            )
            if translated is None:
                workbook.put_name(replace(defined, reference=None, formula="=#REF!"))
            elif translated != defined.reference:
                workbook.put_name(replace(defined, reference=translated))
            continue
        if defined.formula is None:
            continue
        formula = translate_formula_structure(
            defined.formula,
            formula_sheet=defined.scope or "\0",
            target_sheet=target_name,
            axis=axis,
            index=index,
            count=count,
            delete=delete,
        )
        if formula != defined.formula:
            workbook.put_name(replace(defined, formula=formula))


def _translate_tables(
    sheet: object,
    *,
    axis: str,
    index: int,
    count: int,
    delete: bool,
) -> None:
    """Grow, shrink, or move tables, pivots, and data tables with inserted cells."""
    from duddysheet.core.tables import TableSpec

    kept: list[TableSpec] = []
    for table in sheet.tables:
        reference = RangeReference(
            CellReference(table.top, table.left),
            CellReference(table.bottom, table.right),
        )
        moved = translate_reference_structure(reference, axis=axis, index=index, count=count, delete=delete)
        if moved is None:
            continue
        if isinstance(moved, CellReference):
            moved = RangeReference(moved, moved)
        if axis == "row" and delete and table.top >= index and table.top < index + count:
            continue
        kept.append(
            replace(
                table,
                top=moved.min_row,
                left=moved.min_column,
                bottom=moved.max_row,
                right=moved.max_column,
            )
        )
    sheet.tables = kept

    def move_rect(rect: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
        reference = RangeReference(CellReference(rect[0], rect[1]), CellReference(rect[2], rect[3]))
        moved = translate_reference_structure(reference, axis=axis, index=index, count=count, delete=delete)
        if moved is None:
            return None
        if isinstance(moved, CellReference):
            moved = RangeReference(moved, moved)
        return (moved.min_row, moved.min_column, moved.max_row, moved.max_column)

    def move_cell(sheet_name: str, row: int, column: int) -> tuple[str, int, int] | None:
        moved = translate_reference_structure(
            CellReference(row, column), axis=axis, index=index, count=count, delete=delete
        )
        if not isinstance(moved, CellReference):
            return None
        return (sheet_name, moved.row, moved.column)

    pivots = []
    for pivot in sheet.pivots:
        anchor = move_cell(sheet.name, *pivot.anchor)
        if anchor is None:
            continue
        extent = move_rect(pivot.extent) if pivot.extent is not None else None
        pivots.append(replace(pivot, anchor=anchor[1:], extent=extent))
    sheet.pivots = pivots
    data_tables = []
    for spec in sheet.data_tables:
        rect = move_rect((spec.top, spec.left, spec.bottom, spec.right))
        if rect is None or rect[2] <= rect[0] or rect[3] <= rect[1]:
            continue
        row_input = spec.row_input
        column_input = spec.column_input
        if row_input is not None and row_input[0].casefold() == sheet.name.casefold():
            row_input = move_cell(*row_input)
        if column_input is not None and column_input[0].casefold() == sheet.name.casefold():
            column_input = move_cell(*column_input)
        data_tables.append(replace(spec, top=rect[0], left=rect[1], bottom=rect[2], right=rect[3], row_input=row_input, column_input=column_input))
    sheet.data_tables = data_tables


def _translate_pivot_sources(workbook: object, sheet_name: str, *, axis: str, index: int, count: int, delete: bool) -> None:
    """PivotTable sources follow structural edits on their source sheet."""
    folded = sheet_name.casefold()
    for host in workbook:
        updated = []
        for pivot in host.pivots:
            if pivot.source_sheet.casefold() == folded and pivot.source_table is None:
                top, left, bottom, right = pivot.source
                reference = RangeReference(CellReference(top, left), CellReference(bottom, right))
                moved = translate_reference_structure(reference, axis=axis, index=index, count=count, delete=delete)
                if isinstance(moved, CellReference):
                    moved = RangeReference(moved, moved)
                if moved is not None:
                    pivot = replace(pivot, source=(moved.min_row, moved.min_column, moved.max_row, moved.max_column))
            updated.append(pivot)
        host.pivots = updated


def _refresh_table_headers(sheet: object) -> None:
    """After cells move, name new table columns and write their headers."""
    from duddysheet.core.tables import header_names

    refreshed = []
    for table in sheet.tables:
        if len(table.columns) != table.right - table.left + 1:
            columns = header_names(sheet, table.top, table.left, table.right)
            for offset, name in enumerate(columns):
                if sheet.get_cell(table.top, table.left + offset).display_value in (None, ""):
                    sheet.set_cell(table.top, table.left + offset, name)
            table = replace(table, columns=columns)
        refreshed.append(table)
    sheet.tables = refreshed


def _fill_inserted_table_rows(sheet: object, index: int, count: int) -> None:
    """Rows inserted inside a table pick up its calculated-column formulas."""
    from duddysheet.core.tables import fill_calculated

    for table in sheet.tables:
        if not table.calculated:
            continue
        for row in range(index, index + count):
            if table.first_data_row <= row <= table.last_data_row:
                fill_calculated(sheet, table, row)
