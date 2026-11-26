"""Excel's dynamic-array shaping, sorting, grouping, and reference functions."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from duddysheet.core.errors import (
    CALC_ERROR,
    NA_ERROR,
    REF_ERROR,
    VALUE_ERROR,
    SpreadsheetError,
    is_error,
)
from duddysheet.core.functions import lift_all, register
from duddysheet.core.functions.common import number, scalar, text

LOOKUP = "Lookup & Reference"


def _num(context: Any, value: Any) -> Any:
    return number(scalar(context, value))


def _rows(context: Any, value: Any) -> list[list[Any]]:
    return [list(row) for row in context.matrix(value)]


def _array(rows: list[list[Any]]) -> Any:
    if not rows or not rows[0]:
        return CALC_ERROR
    return tuple(tuple(row) for row in rows)


def sort_key(value: Any) -> tuple[int, Any]:
    """Excel's ascending order: numbers, text, logicals, errors, then blanks."""
    from datetime import date, datetime

    from duddysheet.core.values import date_serial

    if value is None:
        return (0, 0)
    if isinstance(value, bool):
        return (2, int(value))
    if isinstance(value, (int, float)):
        return (0, value)
    if isinstance(value, (date, datetime)):
        return (0, date_serial(value))
    if isinstance(value, str):
        return (1, value.casefold())
    if isinstance(value, SpreadsheetError):
        return (3, value.type_number or 0)
    return (4, 0)


def _sort_rows(
    rows: list[list[Any]],
    keys: list[tuple[list[Any], bool]],
) -> list[list[Any]]:
    """Stable multi-key sort; each key is (values per row, descending)."""
    order = list(range(len(rows)))
    for values, descending in reversed(keys):
        order.sort(key=lambda index: sort_key(values[index]), reverse=descending)
    return [rows[index] for index in order]


def _transpose(rows: list[list[Any]]) -> list[list[Any]]:
    return [list(column) for column in zip(*rows)] if rows else []


def _int_list(context: Any, value: Any) -> Any:
    items: list[int] = []
    for row in context.matrix(value):
        for item in row:
            if is_error(item):
                return item
            converted = number(item)
            if is_error(converted):
                return VALUE_ERROR
            items.append(math.trunc(converted))
    return items


def _sort_impl(
    context: Any,
    array: Any,
    sort_index: Any,
    sort_order: Any,
    by_column: Any,
) -> Any:
    rows = _rows(context, array)
    columns = bool(scalar(context, by_column)) if by_column is not None else False
    if columns:
        rows = _transpose(rows)
    indexes = _int_list(context, 1 if sort_index is None else sort_index)
    orders = _int_list(context, 1 if sort_order is None else sort_order)
    if is_error(indexes):
        return indexes
    if is_error(orders):
        return orders
    if len(orders) == 1 and len(indexes) > 1:
        orders = orders * len(indexes)
    if len(orders) != len(indexes):
        return VALUE_ERROR
    width = len(rows[0]) if rows else 0
    keys: list[tuple[list[Any], bool]] = []
    for index, order in zip(indexes, orders):
        if order not in (1, -1) or not 1 <= index <= width:
            return VALUE_ERROR
        keys.append(([row[index - 1] for row in rows], order == -1))
    result = _sort_rows(rows, keys)
    return _array(_transpose(result) if columns else result)


def sort_function(
    context: Any,
    array: Any,
    sort_index: Any = 1,
    sort_order: Any = 1,
    by_column: Any = False,
) -> Any:
    """Sort the rows or columns of an array by one or more keys."""
    return _sort_impl(context, array, sort_index, sort_order, by_column)


@register(
    "SORTBY",
    min_args=2,
    argument_spec="array, by_array1, [sort_order1], [by_array2, sort_order2], ...",
    category=LOOKUP,
)
def sortby(context: Any, array: Any, *pairs: Any) -> Any:
    """Sort an array by the values in corresponding arrays."""
    rows = _rows(context, array)
    if not rows:
        return CALC_ERROR
    keys: list[tuple[list[Any], bool]] = []
    index = 0
    by_columns: bool | None = None
    while index < len(pairs):
        by_rows = _rows(context, pairs[index])
        order_value = pairs[index + 1] if index + 1 < len(pairs) else 1
        order = _num(context, 1 if order_value is None else order_value)
        if is_error(order):
            return order
        order = math.trunc(order)
        if order not in (1, -1):
            return VALUE_ERROR
        if len(by_rows[0]) == 1 and len(by_rows) == len(rows):
            orientation = False
            values = [row[0] for row in by_rows]
        elif len(by_rows) == 1 and len(by_rows[0]) == len(rows[0]):
            orientation = True
            values = by_rows[0]
        elif len(by_rows) == 1 and len(by_rows[0]) == len(rows) and len(rows[0]) == 1:
            orientation = False
            values = by_rows[0]
        else:
            return VALUE_ERROR
        if by_columns is not None and by_columns != orientation:
            return VALUE_ERROR
        by_columns = orientation
        keys.append((values, order == -1))
        index += 2
    if by_columns:
        return _array(_transpose(_sort_rows(_transpose(rows), keys)))
    return _array(_sort_rows(rows, keys))


def _identity(value: Any) -> Any:
    if isinstance(value, str):
        return ("t", value.casefold())
    if isinstance(value, bool):
        return ("b", value)
    if value is None:
        return ("n", 0)
    if isinstance(value, SpreadsheetError):
        return ("e", value.literal)
    try:
        from datetime import date, datetime

        from duddysheet.core.values import date_serial

        if isinstance(value, (date, datetime)):
            return ("n", date_serial(value))
    except ImportError:  # pragma: no cover
        pass
    return ("n", value)


def unique_function(
    context: Any,
    array: Any,
    by_column: Any = False,
    exactly_once: Any = False,
) -> Any:
    """Return distinct rows or columns, ignoring letter case."""
    rows = _rows(context, array)
    columns = bool(scalar(context, by_column)) if by_column is not None else False
    once = bool(scalar(context, exactly_once)) if exactly_once is not None else False
    items = _transpose(rows) if columns else rows
    keys = [tuple(_identity(value) for value in item) for item in items]
    counts: dict[Any, int] = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
    seen: set[Any] = set()
    selected: list[list[Any]] = []
    for item, key in zip(items, keys):
        if key in seen:
            continue
        seen.add(key)
        if once and counts[key] != 1:
            continue
        selected.append(item)
    if not selected:
        return CALC_ERROR
    return _array(_transpose(selected) if columns else selected)


def _pad(rows: list[list[Any]], width: int) -> list[list[Any]]:
    return [row + [NA_ERROR] * (width - len(row)) for row in rows]


@register("VSTACK", min_args=1, argument_spec="array1, [array2], ...", category=LOOKUP)
def vstack(context: Any, *arrays: Any) -> Any:
    """Append arrays vertically; short rows are padded with #N/A."""
    blocks = [_rows(context, array) for array in arrays]
    width = max(len(block[0]) for block in blocks)
    return _array([row for block in blocks for row in _pad(block, width)])


@register("HSTACK", min_args=1, argument_spec="array1, [array2], ...", category=LOOKUP)
def hstack(context: Any, *arrays: Any) -> Any:
    """Append arrays horizontally; short columns are padded with #N/A."""
    blocks = [_rows(context, array) for array in arrays]
    height = max(len(block) for block in blocks)
    result: list[list[Any]] = [[] for _ in range(height)]
    for block in blocks:
        width = len(block[0])
        for row in range(height):
            result[row].extend(block[row] if row < len(block) else [NA_ERROR] * width)
    return _array(result)


def _ignore(value: Any, mode: int) -> bool:
    blank = value is None
    error = is_error(value)
    return (mode in (1, 3) and blank) or (mode in (2, 3) and error)


def _flatten_ordered(rows: list[list[Any]], *, by_column: bool) -> list[Any]:
    if by_column:
        return [rows[r][c] for c in range(len(rows[0])) for r in range(len(rows))]
    return [item for row in rows for item in row]


def _to_vector(context: Any, array: Any, ignore: Any, scan_by_column: Any) -> Any:
    rows = _rows(context, array)
    mode = _num(context, 0 if ignore is None else ignore)
    if is_error(mode):
        return mode
    mode = math.trunc(mode)
    if mode not in (0, 1, 2, 3):
        return VALUE_ERROR
    by_column = bool(scalar(context, scan_by_column)) if scan_by_column is not None else False
    return [item for item in _flatten_ordered(rows, by_column=by_column) if not _ignore(item, mode)]


@register(
    "TOCOL",
    min_args=1,
    max_args=3,
    argument_spec="array, [ignore], [scan_by_column]",
    category=LOOKUP,
)
def tocol(context: Any, array: Any, ignore: Any = 0, scan_by_column: Any = False) -> Any:
    """Return an array as one column."""
    items = _to_vector(context, array, ignore, scan_by_column)
    if is_error(items):
        return items
    return _array([[item] for item in items])


@register(
    "TOROW",
    min_args=1,
    max_args=3,
    argument_spec="array, [ignore], [scan_by_column]",
    category=LOOKUP,
)
def torow(context: Any, array: Any, ignore: Any = 0, scan_by_column: Any = False) -> Any:
    """Return an array as one row."""
    items = _to_vector(context, array, ignore, scan_by_column)
    if is_error(items):
        return items
    return _array([items])


def _wrap(context: Any, vector: Any, count: Any, pad_with: Any, *, rows_first: bool) -> Any:
    rows = _rows(context, vector)
    if len(rows) != 1 and len(rows[0]) != 1:
        return VALUE_ERROR
    items = [item for row in rows for item in row]
    size = _num(context, count)
    if is_error(size):
        return size
    size = math.trunc(size)
    if size < 1:
        return VALUE_ERROR
    padding = NA_ERROR if pad_with is None else scalar(context, pad_with)
    chunks = [items[index : index + size] for index in range(0, len(items), size)]
    chunks = [chunk + [padding] * (size - len(chunk)) for chunk in chunks]
    return _array(chunks if rows_first else _transpose(chunks))


@register(
    "WRAPROWS",
    min_args=2,
    max_args=3,
    argument_spec="vector, wrap_count, [pad_with]",
    category=LOOKUP,
)
def wraprows(context: Any, vector: Any, wrap_count: Any, pad_with: Any = None) -> Any:
    """Wrap a row or column into rows of a given length."""
    return _wrap(context, vector, wrap_count, pad_with, rows_first=True)


@register(
    "WRAPCOLS",
    min_args=2,
    max_args=3,
    argument_spec="vector, wrap_count, [pad_with]",
    category=LOOKUP,
)
def wrapcols(context: Any, vector: Any, wrap_count: Any, pad_with: Any = None) -> Any:
    """Wrap a row or column into columns of a given length."""
    return _wrap(context, vector, wrap_count, pad_with, rows_first=False)


def _span(count: Any, total: int, *, take: bool) -> Any:
    if count is None:
        return range(total)
    if count == 0:
        return None
    if take:
        return range(0, min(count, total)) if count > 0 else range(max(0, total + count), total)
    return range(min(count, total), total) if count > 0 else range(0, max(0, total + count))


def _take_drop(context: Any, array: Any, rows: Any, columns: Any, *, take: bool) -> Any:
    data = _rows(context, array)
    row_count = None if rows is None else _num(context, rows)
    column_count = None if columns is None else _num(context, columns)
    for item in (row_count, column_count):
        if item is not None and is_error(item):
            return item
    row_count = None if row_count is None else math.trunc(row_count)
    column_count = None if column_count is None else math.trunc(column_count)
    row_span = _span(row_count, len(data), take=take)
    column_span = _span(column_count, len(data[0]), take=take)
    if row_span is None or column_span is None or not row_span or not column_span:
        return CALC_ERROR
    return _array([[data[r][c] for c in column_span] for r in row_span])


@register(
    "TAKE",
    min_args=2,
    max_args=3,
    argument_spec="array, rows, [columns]",
    category=LOOKUP,
)
def take(context: Any, array: Any, rows: Any, columns: Any = None) -> Any:
    """Return rows or columns from the start (positive) or end (negative) of an array."""
    return _take_drop(context, array, rows, columns, take=True)


@register(
    "DROP",
    min_args=2,
    max_args=3,
    argument_spec="array, rows, [columns]",
    category=LOOKUP,
)
def drop(context: Any, array: Any, rows: Any, columns: Any = None) -> Any:
    """Exclude rows or columns from the start (positive) or end (negative) of an array."""
    return _take_drop(context, array, rows, columns, take=False)


def _choose(context: Any, array: Any, selectors: tuple[Any, ...], *, columns: bool) -> Any:
    data = _rows(context, array)
    if columns:
        data = _transpose(data)
    chosen: list[list[Any]] = []
    for selector in selectors:
        indexes = _int_list(context, selector)
        if is_error(indexes):
            return indexes
        for index in indexes:
            if index == 0 or abs(index) > len(data):
                return VALUE_ERROR
            chosen.append(data[index - 1] if index > 0 else data[len(data) + index])
    return _array(_transpose(chosen) if columns else chosen)


@register(
    "CHOOSEROWS",
    min_args=2,
    argument_spec="array, row_num1, [row_num2], ...",
    category=LOOKUP,
)
def chooserows(context: Any, array: Any, *rows: Any) -> Any:
    """Return the specified rows of an array."""
    return _choose(context, array, rows, columns=False)


@register(
    "CHOOSECOLS",
    min_args=2,
    argument_spec="array, col_num1, [col_num2], ...",
    category=LOOKUP,
)
def choosecols(context: Any, array: Any, *columns: Any) -> Any:
    """Return the specified columns of an array."""
    return _choose(context, array, columns, columns=True)


@register(
    "EXPAND",
    min_args=2,
    max_args=4,
    argument_spec="array, rows, [columns], [pad_with]",
    category=LOOKUP,
)
def expand(context: Any, array: Any, rows: Any, columns: Any = None, pad_with: Any = None) -> Any:
    """Expand or pad an array to the given dimensions."""
    data = _rows(context, array)
    height = len(data) if rows is None else _num(context, rows)
    width = len(data[0]) if columns is None else _num(context, columns)
    if is_error(height):
        return height
    if is_error(width):
        return width
    height, width = math.trunc(height), math.trunc(width)
    if height < len(data) or width < len(data[0]):
        return VALUE_ERROR
    padding = NA_ERROR if pad_with is None else scalar(context, pad_with)
    result = [row + [padding] * (width - len(row)) for row in data]
    result += [[padding] * width for _ in range(height - len(data))]
    return _array(result)


@register(
    "TRIMRANGE",
    min_args=1,
    max_args=3,
    argument_spec="range, [trim_rows], [trim_cols]",
    category=LOOKUP,
)
def trimrange(context: Any, reference: Any, trim_rows: Any = 3, trim_cols: Any = 3) -> Any:
    """Exclude empty rows and columns from the outer edges of a range."""
    from duddysheet.core.evaluator import ReferenceValue
    from duddysheet.core.refs import CellReference, RangeReference

    areas = getattr(reference, "areas", None)
    if not areas or len(areas) != 1:
        return VALUE_ERROR
    area = areas[0]
    if isinstance(area, CellReference):
        return reference
    rows_mode = math.trunc(_num(context, 3 if trim_rows is None else trim_rows))
    cols_mode = math.trunc(_num(context, 3 if trim_cols is None else trim_cols))
    min_row, max_row, min_column, max_column = context.evaluator.reference_bounds(area)
    sheet = context.evaluator.workbook.get_sheet(area.sheet or context.sheet_name)
    populated = [
        (row, column)
        for row in range(min_row, max_row + 1)
        for column in range(min_column, max_column + 1)
        if sheet.get_cell(row, column).display_value not in (None,)
    ]
    if not populated:
        return REF_ERROR
    top = min(row for row, _ in populated) if rows_mode in (1, 3) else min_row
    bottom = max(row for row, _ in populated) if rows_mode in (2, 3) else max_row
    left = min(column for _, column in populated) if cols_mode in (1, 3) else min_column
    right = max(column for _, column in populated) if cols_mode in (2, 3) else max_column
    start = CellReference(top, left, sheet=area.sheet)
    if top == bottom and left == right:
        return ReferenceValue((start,))
    return ReferenceValue((RangeReference(start, CellReference(bottom, right, sheet=area.sheet)),))


# --------------------------------------------------------------- references
@register(
    "ADDRESS",
    min_args=2,
    max_args=5,
    argument_spec="row_num, column_num, [abs_num], [a1], [sheet_text]",
    lift=lift_all,
    category=LOOKUP,
)
def address(
    context: Any,
    row_number: Any,
    column_number: Any,
    abs_number: Any = 1,
    a1_style: Any = True,
    sheet_text: Any = None,
) -> Any:
    """Return a cell address as text."""
    from duddysheet.core.refs import MAX_COLUMNS, MAX_ROWS, index_to_column, quote_sheet_name

    values = [_num(context, row_number), _num(context, column_number), _num(context, 1 if abs_number is None else abs_number)]
    for value in values:
        if is_error(value):
            return value
    row, column, mode = (math.trunc(value) for value in values)
    a1 = True if a1_style is None else bool(scalar(context, a1_style))
    if mode not in (1, 2, 3, 4) or row < 1 or column < 1 or row > MAX_ROWS or column > MAX_COLUMNS:
        return VALUE_ERROR
    absolute_row = mode in (1, 2)
    absolute_column = mode in (1, 3)
    if a1:
        rendered = (
            ("$" if absolute_column else "")
            + index_to_column(column - 1)
            + ("$" if absolute_row else "")
            + str(row)
        )
    else:
        rendered = (
            (f"R{row}" if absolute_row else f"R[{row}]")
            + (f"C{column}" if absolute_column else f"C[{column}]")
        )
    if sheet_text is not None:
        sheet = text(scalar(context, sheet_text))
        if sheet:
            rendered = f"{quote_sheet_name(sheet)}!{rendered}"
    return rendered


@register("AREAS", min_args=1, max_args=1, argument_spec="reference", category=LOOKUP)
def areas(context: Any, reference: Any) -> Any:
    """Return the number of areas in a reference."""
    selected = getattr(reference, "areas", None)
    return VALUE_ERROR if not selected else len(selected)


@register(
    "HYPERLINK",
    min_args=1,
    max_args=2,
    argument_spec="link_location, [friendly_name]",
    lift=lift_all,
    category=LOOKUP,
)
def hyperlink(context: Any, link_location: Any, friendly_name: Any = None) -> Any:
    """Return a jump target's friendly name; the grid makes the cell clickable."""
    if friendly_name is None:
        return text(scalar(context, link_location))
    selected = scalar(context, friendly_name)
    return 0 if selected is None else selected


@register(
    "ANCHORARRAY",
    min_args=1,
    max_args=1,
    argument_spec="reference",
    category=LOOKUP,
)
def anchorarray(context: Any, reference: Any) -> Any:
    """Return the spilled range anchored at a cell (the # operator)."""
    return context.evaluator._spill_range(reference, context)


@register("SINGLE", min_args=1, max_args=1, argument_spec="value", category=LOOKUP)
def single(context: Any, value: Any) -> Any:
    """Return one value by implicit intersection (the @ operator)."""
    return context.evaluator._implicit_intersection(value, context)


@register(
    "ENCODEURL",
    min_args=1,
    max_args=1,
    argument_spec="text",
    lift=lift_all,
    category="Web",
)
def encodeurl(context: Any, value: Any) -> Any:
    """Return a URL-encoded string."""
    from urllib.parse import quote

    return quote(text(scalar(context, value)), safe="-_.~")


# ------------------------------------------------------------ GROUPBY etc.
def _aggregate_function(context: Any, function: Any) -> Any:
    from duddysheet.core.evaluator import LambdaValue

    if isinstance(function, LambdaValue):
        return lambda values: context.call(function, tuple((value,) for value in values))
    return VALUE_ERROR


def _apply(context: Any, function: Callable[[list[Any]], Any], values: list[Any]) -> Any:
    result = function(values)
    if context.is_array(result):
        rows = context.matrix(result)
        return rows[0][0] if len(rows) == 1 and len(rows[0]) == 1 else CALC_ERROR
    return context.scalar(result)


def _field_rows(context: Any, value: Any) -> list[list[Any]]:
    return _rows(context, value)


def _group_key(values: list[Any]) -> tuple[Any, ...]:
    return tuple(_identity(value) for value in values)


@register(
    "GROUPBY",
    min_args=3,
    max_args=8,
    argument_spec="row_fields, values, function, [field_headers], [total_depth], [sort_order], [filter_array], [field_relationship]",
    category=LOOKUP,
)
def groupby(
    context: Any,
    row_fields: Any,
    values: Any,
    function: Any,
    field_headers: Any = None,
    total_depth: Any = None,
    sort_order: Any = None,
    filter_array: Any = None,
    field_relationship: Any = None,
) -> Any:
    """Group rows by fields and aggregate the values with a LAMBDA such as SUM."""
    del field_relationship
    aggregator = _aggregate_function(context, function)
    if is_error(aggregator):
        return aggregator
    keys = _field_rows(context, row_fields)
    data = _field_rows(context, values)
    if len(keys) != len(data):
        return VALUE_ERROR
    headers_mode = 0 if field_headers is None else math.trunc(_num(context, field_headers))
    header_keys: list[Any] = []
    header_values: list[Any] = []
    if headers_mode in (1, 3):
        header_keys, header_values = keys[0], data[0]
        keys, data = keys[1:], data[1:]
    if filter_array is not None:
        flags = [row[0] for row in _rows(context, filter_array)]
        if headers_mode in (1, 3):
            flags = flags[1:]
        if len(flags) != len(keys):
            return VALUE_ERROR
        keys = [key for key, flag in zip(keys, flags) if flag is True or (isinstance(flag, (int, float)) and flag)]
        data = [row for row, flag in zip(data, flags) if flag is True or (isinstance(flag, (int, float)) and flag)]
    groups: dict[tuple[Any, ...], tuple[list[Any], list[list[Any]]]] = {}
    for key_row, data_row in zip(keys, data):
        identity = _group_key(key_row)
        if identity not in groups:
            groups[identity] = (key_row, [])
        groups[identity][1].append(data_row)
    width = len(data[0]) if data else 1
    output: list[list[Any]] = []
    for key_row, members in groups.values():
        aggregated = [
            _apply(context, aggregator, [member[column] for member in members])
            for column in range(width)
        ]
        output.append(list(key_row) + aggregated)
    order = 1 if sort_order is None else math.trunc(_num(context, sort_order))
    if order:
        column = abs(order) - 1
        if column < len(output[0]) if output else True:
            output.sort(key=lambda row: sort_key(row[column]), reverse=order < 0)
    depth = 1 if total_depth is None else math.trunc(_num(context, total_depth))
    if depth and output and data:
        totals = [
            _apply(context, aggregator, [row[column] for row in data])
            for column in range(width)
        ]
        total_row = ["Total"] + [""] * (len(keys[0]) - 1) + totals
        if depth < 0:
            output.insert(0, total_row)
        else:
            output.append(total_row)
    if headers_mode in (1, 2, 3) and header_keys:
        output.insert(0, list(header_keys) + list(header_values))
    if not output:
        return CALC_ERROR
    return _array([row + [None] * (len(output[0]) - len(row)) for row in output])


@register(
    "PIVOTBY",
    min_args=4,
    max_args=11,
    argument_spec="row_fields, col_fields, values, function, [field_headers], [row_total_depth], [row_sort_order], [col_total_depth], [col_sort_order], [filter_array], [relative_to]",
    category=LOOKUP,
)
def pivotby(
    context: Any,
    row_fields: Any,
    column_fields: Any,
    values: Any,
    function: Any,
    field_headers: Any = None,
    row_total_depth: Any = None,
    row_sort_order: Any = None,
    column_total_depth: Any = None,
    column_sort_order: Any = None,
    filter_array: Any = None,
    relative_to: Any = None,
) -> Any:
    """Summarize values in a grid of row and column groups."""
    del field_headers, row_sort_order, column_sort_order, relative_to
    aggregator = _aggregate_function(context, function)
    if is_error(aggregator):
        return aggregator
    row_keys = [row[0] for row in _rows(context, row_fields)]
    column_keys = [row[0] for row in _rows(context, column_fields)]
    data = [row[0] for row in _rows(context, values)]
    if not (len(row_keys) == len(column_keys) == len(data)):
        return VALUE_ERROR
    if filter_array is not None:
        flags = [row[0] for row in _rows(context, filter_array)]
        if len(flags) != len(data):
            return VALUE_ERROR
        selected = [index for index, flag in enumerate(flags) if flag]
        row_keys = [row_keys[i] for i in selected]
        column_keys = [column_keys[i] for i in selected]
        data = [data[i] for i in selected]
    rows_order = sorted({_identity(key): key for key in row_keys}.values(), key=sort_key)
    columns_order = sorted({_identity(key): key for key in column_keys}.values(), key=sort_key)
    show_row_totals = row_total_depth is None or math.trunc(_num(context, row_total_depth)) != 0
    show_column_totals = column_total_depth is None or math.trunc(_num(context, column_total_depth)) != 0
    header = [""] + list(columns_order) + (["Total"] if show_column_totals else [])
    output: list[list[Any]] = [header]
    for row_key in rows_order:
        line: list[Any] = [row_key]
        row_identity = _identity(row_key)
        for column_key in columns_order:
            column_identity = _identity(column_key)
            members = [
                data[index]
                for index in range(len(data))
                if _identity(row_keys[index]) == row_identity
                and _identity(column_keys[index]) == column_identity
            ]
            line.append(_apply(context, aggregator, members) if members else "")
        if show_column_totals:
            line.append(
                _apply(
                    context,
                    aggregator,
                    [data[index] for index in range(len(data)) if _identity(row_keys[index]) == row_identity],
                )
            )
        output.append(line)
    if show_row_totals:
        total_line: list[Any] = ["Total"]
        for column_key in columns_order:
            column_identity = _identity(column_key)
            total_line.append(
                _apply(
                    context,
                    aggregator,
                    [data[index] for index in range(len(data)) if _identity(column_keys[index]) == column_identity],
                )
            )
        if show_column_totals:
            total_line.append(_apply(context, aggregator, data))
        output.append(total_line)
    return _array(output)


@register(
    "PERCENTOF",
    min_args=2,
    max_args=2,
    argument_spec="data_subset, data_all",
    category="Math & Trig",
)
def percentof(context: Any, subset: Any, everything: Any) -> Any:
    """Return the percentage that a subset makes up of all data."""
    from duddysheet.core.functions.common import numeric_values

    part = numeric_values(context, subset)
    whole = numeric_values(context, everything)
    if is_error(part):
        return part
    if is_error(whole):
        return whole
    total = math.fsum(whole)
    if total == 0:
        from duddysheet.core.errors import DIV_ZERO_ERROR

        return DIV_ZERO_ERROR
    return math.fsum(part) / total

