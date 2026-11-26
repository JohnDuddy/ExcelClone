"""Lookup, reference, and dynamic-array worksheet functions."""

from __future__ import annotations

import fnmatch
from typing import Any

from duddysheet.core.errors import NA_ERROR, REF_ERROR, VALUE_ERROR, is_error
from duddysheet.core.functions import register
from duddysheet.core.functions.common import (
    flatten,
    matrix,
    number,
    rectangular,
    scalar,
    text,
    truthy,
)
from duddysheet.core.refs import (
    MAX_COLUMNS,
    MAX_ROWS,
    CellReference,
    RangeReference,
    parse_a1,
    parse_r1c1,
)


def _equal(left: Any, right: Any) -> bool:
    if isinstance(left, str) and isinstance(right, str):
        return left.casefold() == right.casefold()
    return left == right


def _kind(value: Any) -> int | None:
    """Comparison class used by lookups: 0 number, 1 text, 2 logical."""
    from datetime import date, datetime

    if isinstance(value, bool):
        return 2
    if isinstance(value, (int, float, date, datetime)):
        return 0
    if isinstance(value, str):
        return 1
    return None


def _key(value: Any) -> Any:
    from datetime import date, datetime

    from duddysheet.core.values import date_serial

    if isinstance(value, str):
        return value.casefold()
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (date, datetime)):
        return date_serial(value)
    return value


def _wildcard_match(pattern: str, value: Any) -> bool:
    from duddysheet.core.functions.common import _wildcard_pattern

    return isinstance(value, str) and _wildcard_pattern(pattern).fullmatch(value) is not None


def _has_wildcards(value: Any) -> bool:
    return isinstance(value, str) and any(character in value for character in "*?~")


def _lookup_index(
    lookup_value: Any,
    values: list[Any],
    *,
    match_mode: int = 0,
    search_mode: int = 1,
    wildcards: bool = False,
) -> int | None:
    """Excel lookup position: exact (0), next smaller (-1), next larger (1), wildcard (2).

    Search modes 1/-1 scan first-to-last or last-to-first; 2/-2 binary-search
    data sorted ascending or descending.
    """
    if lookup_value is None:
        lookup_value = 0 if match_mode != 2 else ""
    kind = _kind(lookup_value)
    if kind is None:
        return None
    target = _key(lookup_value)
    if search_mode in (2, -2):
        return _binary_index(target, kind, values, match_mode, descending=search_mode == -2)
    indexes = range(len(values) - 1, -1, -1) if search_mode == -1 else range(len(values))
    if match_mode == 2 or (wildcards and match_mode == 0 and _has_wildcards(lookup_value)):
        if not isinstance(lookup_value, str):
            match_mode = 0
        else:
            for index in indexes:
                if _wildcard_match(lookup_value, values[index]):
                    return index
            return None
    best: int | None = None
    best_key: Any = None
    for index in indexes:
        candidate = values[index]
        if _kind(candidate) != kind:
            continue
        candidate_key = _key(candidate)
        if candidate_key == target:
            return index
        if match_mode == -1 and candidate_key < target:
            if best is None or candidate_key > best_key:
                best, best_key = index, candidate_key
        elif match_mode == 1 and candidate_key > target:
            if best is None or candidate_key < best_key:
                best, best_key = index, candidate_key
    return best


def _binary_index(
    target: Any,
    kind: int,
    values: list[Any],
    match_mode: int,
    *,
    descending: bool,
) -> int | None:
    positions = [index for index, value in enumerate(values) if _kind(value) == kind]
    if not positions:
        return None
    keys = [_key(values[index]) for index in positions]
    low, high = 0, len(keys) - 1
    found: int | None = None
    # Last position whose key is on the "not past target" side of the order.
    while low <= high:
        middle = (low + high) // 2
        before = keys[middle] >= target if descending else keys[middle] <= target
        if before:
            found = middle
            low = middle + 1
        else:
            high = middle - 1
    if found is not None and keys[found] == target:
        return positions[found]
    if match_mode == 0:
        return None
    if match_mode == -1:
        if descending:
            following = (found + 1) if found is not None else 0
            return positions[following] if following < len(keys) else None
        return positions[found] if found is not None else None
    if match_mode == 1:
        if descending:
            return positions[found] if found is not None else None
        following = (found + 1) if found is not None else 0
        return positions[following] if following < len(keys) else None
    return None


@register(
    "VLOOKUP",
    min_args=3,
    max_args=4,
    argument_spec="lookup_value, table_array, col_index_num, [range_lookup]",
)
def vlookup(
    context: Any,
    lookup_value: Any,
    table_array: Any,
    column_index: Any,
    approximate: Any = True,
) -> Any:
    """Look down the first table column and return a selected column."""
    rows = matrix(context, table_array)
    selected_column = number(scalar(context, column_index))
    if is_error(selected_column) or selected_column < 1:
        return VALUE_ERROR
    selected_column = int(selected_column) - 1
    if not rows or selected_column >= max(len(row) for row in rows):
        return REF_ERROR
    lookup = scalar(context, lookup_value)
    first_column = [row[0] if row else None for row in rows]
    if bool(scalar(context, approximate)):
        index = _lookup_index(lookup, first_column, match_mode=-1, search_mode=2)
    else:
        index = _lookup_index(lookup, first_column, wildcards=True)
    if index is None or selected_column >= len(rows[index]):
        return NA_ERROR
    return rows[index][selected_column]


@register(
    "HLOOKUP",
    min_args=3,
    max_args=4,
    argument_spec="lookup_value, table_array, row_index_num, [range_lookup]",
)
def hlookup(
    context: Any,
    lookup_value: Any,
    table_array: Any,
    row_index: Any,
    approximate: Any = True,
) -> Any:
    """Look across the first table row and return a selected row."""
    rows = matrix(context, table_array)
    selected_row = number(scalar(context, row_index))
    if is_error(selected_row) or selected_row < 1:
        return VALUE_ERROR
    selected_row = int(selected_row) - 1
    if not rows or selected_row >= len(rows):
        return REF_ERROR
    lookup = scalar(context, lookup_value)
    approximate_match = bool(scalar(context, approximate))
    index = _lookup_index(
        lookup,
        rows[0],
        match_mode=-1 if approximate_match else 0,
        search_mode=2 if approximate_match else 1,
        wildcards=not approximate_match,
    )
    if index is None or index >= len(rows[selected_row]):
        return NA_ERROR
    return rows[selected_row][index]


@register(
    "XLOOKUP",
    min_args=3,
    max_args=6,
    argument_spec="lookup_value, lookup_array, return_array, [if_not_found], [match_mode], [search_mode]",
)
def xlookup(
    context: Any,
    lookup_value: Any,
    lookup_array: Any,
    return_array: Any,
    if_not_found: Any = NA_ERROR,
    match_mode: Any = 0,
    search_mode: Any = 1,
) -> Any:
    """Find an exact or approximate match and return corresponding values."""
    lookup = scalar(context, lookup_value)
    lookup_values = flatten(context, lookup_array)
    selected_match_mode = number(scalar(context, match_mode))
    selected_search_mode = number(scalar(context, search_mode))
    if is_error(selected_match_mode) or is_error(selected_search_mode):
        return VALUE_ERROR
    index = _lookup_index(
        lookup,
        lookup_values,
        match_mode=int(selected_match_mode),
        search_mode=int(selected_search_mode),
    )
    if index is None:
        return scalar(context, if_not_found)
    return_rows = matrix(context, return_array)
    if len(return_rows) == len(lookup_values):
        selected = return_rows[index]
        return selected[0] if len(selected) == 1 else rectangular([selected])
    if return_rows and len(return_rows[0]) == len(lookup_values):
        selected_column = [row[index] for row in return_rows]
        return (
            selected_column[0]
            if len(selected_column) == 1
            else rectangular([[value] for value in selected_column])
        )
    flattened = [item for row in return_rows for item in row]
    return flattened[index] if index < len(flattened) else VALUE_ERROR


@register("LOOKUP", min_args=2, max_args=3, argument_spec="lookup_value, lookup_vector, [result_vector]")
def lookup(
    context: Any,
    lookup_value: Any,
    lookup_vector: Any,
    result_vector: Any = None,
) -> Any:
    """Return the last value less than or equal to a lookup value."""
    lookup_values = flatten(context, lookup_vector)
    results = lookup_values if result_vector is None else flatten(context, result_vector)
    if len(results) != len(lookup_values):
        return NA_ERROR
    index = _lookup_index(
        scalar(context, lookup_value),
        lookup_values,
        match_mode=-1,
        search_mode=2,
    )
    return NA_ERROR if index is None else results[index]


@register(
    "INDEX",
    min_args=2,
    max_args=4,
    argument_spec="array, row_num, [column_num], [area_num]",
)
def index(
    context: Any,
    array: Any,
    row_number: Any,
    column_number: Any = None,
    area_number: Any = 1,
) -> Any:
    """Return a cell, row, or column of a reference or array; references stay live."""
    selected_row = number(scalar(context, row_number))
    selected_column = (
        None if column_number is None else number(scalar(context, column_number))
    )
    if is_error(selected_row) or is_error(selected_column):
        return VALUE_ERROR
    areas = getattr(array, "areas", None)
    if areas:
        return _index_reference(context, areas, selected_row, selected_column, area_number)
    rows = matrix(context, array)
    row_index = int(selected_row)
    if selected_column is None:
        if len(rows) == 1 and len(rows[0]) > 1:
            row_index, column_index = 1, row_index
        elif rows and len(rows[0]) == 1:
            column_index = 1
        else:
            column_index = 0
    else:
        column_index = int(selected_column)
    if row_index < 0 or column_index < 0:
        return VALUE_ERROR
    if row_index == 0 and column_index == 0:
        return rectangular(rows)
    if row_index == 0:
        if any(column_index > len(row) for row in rows):
            return REF_ERROR
        return rectangular([[row[column_index - 1]] for row in rows])
    if column_index == 0:
        if row_index > len(rows):
            return REF_ERROR
        return rectangular([rows[row_index - 1]])
    if row_index > len(rows) or column_index > len(rows[row_index - 1]):
        return REF_ERROR
    return rows[row_index - 1][column_index - 1]


def _index_reference(
    context: Any,
    areas: tuple[Any, ...],
    selected_row: Any,
    selected_column: Any,
    area_number: Any,
) -> Any:
    from duddysheet.core.evaluator import ReferenceValue

    selected_area = number(scalar(context, area_number))
    if is_error(selected_area) or not 1 <= int(selected_area) <= len(areas):
        return REF_ERROR
    area = areas[int(selected_area) - 1]
    if isinstance(area, CellReference):
        area = RangeReference(area, area)
    height = area.max_row - area.min_row + 1
    width = area.max_column - area.min_column + 1
    row_index = int(selected_row)
    if selected_column is None:
        if height == 1 and width > 1:
            row_index, column_index = 1, row_index
        elif width == 1:
            column_index = 1
        else:
            column_index = 0
    else:
        column_index = int(selected_column)
    if row_index < 0 or column_index < 0:
        return VALUE_ERROR
    if row_index > height or column_index > width:
        return REF_ERROR
    sheet = area.sheet
    top = area.min_row if row_index == 0 else area.min_row + row_index - 1
    bottom = area.max_row if row_index == 0 else top
    left = area.min_column if column_index == 0 else area.min_column + column_index - 1
    right = area.max_column if column_index == 0 else left
    start = CellReference(top, left, sheet=sheet)
    if top == bottom and left == right:
        return ReferenceValue((start,))
    return ReferenceValue(
        (
            RangeReference(
                start,
                CellReference(bottom, right, sheet=sheet),
                whole_row=column_index == 0 and area.whole_row,
                whole_column=row_index == 0 and area.whole_column,
            ),
        )
    )


@register("MATCH", min_args=2, max_args=3, argument_spec="lookup_value, lookup_array, [match_type]")
def match(
    context: Any,
    lookup_value: Any,
    lookup_array: Any,
    match_type: Any = 1,
) -> Any:
    """Return the one-based position of a lookup value."""
    selected_match = number(scalar(context, match_type))
    if is_error(selected_match) or int(selected_match) not in (-1, 0, 1):
        return NA_ERROR
    selected_match = int(selected_match)
    mode = 0 if selected_match == 0 else (-1 if selected_match == 1 else 1)
    index_value = _lookup_index(
        scalar(context, lookup_value),
        flatten(context, lookup_array),
        match_mode=mode,
        search_mode=1 if selected_match == 0 else (2 if selected_match == 1 else -2),
        wildcards=selected_match == 0,
    )
    return NA_ERROR if index_value is None else index_value + 1


@register(
    "XMATCH",
    min_args=2,
    max_args=4,
    argument_spec="lookup_value, lookup_array, [match_mode], [search_mode]",
)
def xmatch(
    context: Any,
    lookup_value: Any,
    lookup_array: Any,
    match_mode: Any = 0,
    search_mode: Any = 1,
) -> Any:
    """Return a flexible one-based lookup position."""
    selected_match = number(scalar(context, match_mode))
    selected_search = number(scalar(context, search_mode))
    if is_error(selected_match) or is_error(selected_search):
        return VALUE_ERROR
    index_value = _lookup_index(
        scalar(context, lookup_value),
        flatten(context, lookup_array),
        match_mode=int(selected_match),
        search_mode=int(selected_search),
    )
    return NA_ERROR if index_value is None else index_value + 1


@register(
    "OFFSET",
    min_args=3,
    max_args=5,
    volatile=True,
    argument_spec="reference, rows, cols, [height], [width]",
)
def offset(
    context: Any,
    reference: Any,
    rows: Any,
    columns: Any,
    height: Any = None,
    width: Any = None,
) -> Any:
    """Return a reference offset from a starting cell or range."""
    from duddysheet.core.evaluator import ReferenceValue

    areas = getattr(reference, "areas", None)
    if not areas:
        return VALUE_ERROR
    source = areas[0]
    start_row = source.row if isinstance(source, CellReference) else source.min_row
    start_column = source.column if isinstance(source, CellReference) else source.min_column
    source_height = 1 if isinstance(source, CellReference) else source.max_row - source.min_row + 1
    source_width = 1 if isinstance(source, CellReference) else source.max_column - source.min_column + 1
    row_offset = number(scalar(context, rows))
    column_offset = number(scalar(context, columns))
    selected_height = source_height if height is None else number(scalar(context, height))
    selected_width = source_width if width is None else number(scalar(context, width))
    if any(is_error(value) for value in (row_offset, column_offset, selected_height, selected_width)):
        return VALUE_ERROR
    top = start_row + int(row_offset)
    left = start_column + int(column_offset)
    bottom = top + int(selected_height) - 1
    right = left + int(selected_width) - 1
    if not (0 <= top <= bottom < MAX_ROWS and 0 <= left <= right < MAX_COLUMNS):
        return REF_ERROR
    sheet = source.sheet
    result = (
        CellReference(top, left, sheet=sheet)
        if top == bottom and left == right
        else RangeReference(
            CellReference(top, left, sheet=sheet),
            CellReference(bottom, right, sheet=sheet),
        )
    )
    return ReferenceValue((result,))


@register(
    "INDIRECT",
    min_args=1,
    max_args=2,
    volatile=True,
    argument_spec="ref_text, [a1]",
)
def indirect(context: Any, reference_text: Any, a1_style: Any = True) -> Any:
    """Convert reference text into a live reference."""
    from duddysheet.core.evaluator import ReferenceValue

    source = text(scalar(context, reference_text))
    try:
        reference = (
            parse_a1(source, default_sheet=context.sheet_name)
            if bool(scalar(context, a1_style))
            else parse_r1c1(
                source,
                origin=context.origin,
                default_sheet=context.sheet_name,
            )
        )
    except ValueError:
        return REF_ERROR
    return ReferenceValue((reference,))


def _first_area(value: Any) -> Any:
    areas = getattr(value, "areas", None)
    return areas[0] if areas else None


@register("ROW", max_args=1, argument_spec="[reference]")
def row(context: Any, reference: Any = None) -> Any:
    """Return the one-based row number of a reference or formula cell."""
    if reference is None:
        return context.origin[0] + 1
    area = _first_area(reference)
    return VALUE_ERROR if area is None else (area.row if isinstance(area, CellReference) else area.min_row) + 1


@register("ROWS", min_args=1, max_args=1, argument_spec="array")
def rows(context: Any, array: Any) -> int:
    """Return the number of rows in an array or range."""
    return len(matrix(context, array))


@register("COLUMN", max_args=1, argument_spec="[reference]")
def column(context: Any, reference: Any = None) -> Any:
    """Return the one-based column number of a reference or formula cell."""
    if reference is None:
        return context.origin[1] + 1
    area = _first_area(reference)
    return VALUE_ERROR if area is None else (area.column if isinstance(area, CellReference) else area.min_column) + 1


@register("COLUMNS", min_args=1, max_args=1, argument_spec="array")
def columns(context: Any, array: Any) -> int:
    """Return the number of columns in an array or range."""
    rows_value = matrix(context, array)
    return max((len(row_value) for row_value in rows_value), default=0)


@register("TRANSPOSE", min_args=1, max_args=1, argument_spec="array")
def transpose(context: Any, array: Any) -> Any:
    """Swap rows and columns in a dynamic array."""
    rows_value = matrix(context, array)
    width = max((len(row_value) for row_value in rows_value), default=0)
    padded = [row_value + [None] * (width - len(row_value)) for row_value in rows_value]
    return rectangular([list(column_value) for column_value in zip(*padded)])


@register("CHOOSE", min_args=2, argument_spec="index_num, value1, [value2], ...")
def choose(context: Any, index_number: Any, *values: Any) -> Any:
    """Return a value selected by one-based index."""
    selected = number(scalar(context, index_number))
    if is_error(selected) or selected < 1 or selected > len(values):
        return VALUE_ERROR
    return values[int(selected) - 1]


@register("UNIQUE", min_args=1, max_args=3, argument_spec="array, [by_col], [exactly_once]")
def unique(
    context: Any,
    array: Any,
    by_column: Any = False,
    exactly_once: Any = False,
) -> Any:
    """Return distinct rows or columns as a dynamic array, ignoring case."""
    from duddysheet.core.functions.array_fn import unique_function

    return unique_function(context, array, by_column, exactly_once)


@register("SORT", min_args=1, max_args=4, argument_spec="array, [sort_index], [sort_order], [by_col]")
def sort_function(
    context: Any,
    array: Any,
    sort_index: Any = 1,
    sort_order: Any = 1,
    by_column: Any = False,
) -> Any:
    """Sort rows or columns of a dynamic array by one or more keys."""
    from duddysheet.core.functions.array_fn import sort_function as excel_sort

    return excel_sort(context, array, sort_index, sort_order, by_column)


@register("FILTER", min_args=2, max_args=3, argument_spec="array, include, [if_empty]")
def filter_function(
    context: Any,
    array: Any,
    include: Any,
    if_empty: Any = None,
) -> Any:
    """Filter the rows (or columns) of an array using a logical include array."""
    from duddysheet.core.errors import CALC_ERROR

    rows_value = matrix(context, array)
    include_rows = context.matrix(include)
    height = len(rows_value)
    width = len(rows_value[0]) if rows_value else 0
    include_height = len(include_rows)
    include_width = len(include_rows[0]) if include_rows else 0
    if include_width == 1 and include_height == height:
        by_columns = False
        flags = [row[0] for row in include_rows]
    elif include_height == 1 and include_width == width and (width > 1 or height == 1):
        by_columns = True
        flags = include_rows[0]
    else:
        return VALUE_ERROR
    keep: list[bool] = []
    for flag in flags:
        if is_error(flag):
            return flag
        include_value = truthy(flag)
        if is_error(include_value):
            return include_value
        keep.append(bool(include_value))
    if by_columns:
        selected = [[item for item, flag in zip(row, keep) if flag] for row in rows_value]
        if not selected or not selected[0]:
            return CALC_ERROR if if_empty is None else if_empty
        return rectangular(selected)
    selected = [row for row, flag in zip(rows_value, keep) if flag]
    if not selected:
        return CALC_ERROR if if_empty is None else if_empty
    return rectangular(selected)
