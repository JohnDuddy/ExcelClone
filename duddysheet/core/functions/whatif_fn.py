"""TABLE (What-If data tables) and GETPIVOTDATA."""

from __future__ import annotations

from typing import Any

from duddysheet.core.errors import REF_ERROR, VALUE_ERROR, is_error
from duddysheet.core.functions import register
from duddysheet.core.functions.common import scalar, text


@register(
    "TABLE",
    min_args=2,
    max_args=2,
    argument_spec="row_input_cell, column_input_cell",
    lazy=True,
    category="What-If",
)
def table_function(context: Any, row_input: Any, column_input: Any) -> Any:
    """Return a What-If data table result; created by Data > What-If Analysis > Data Table."""
    del row_input, column_input
    engine = getattr(context.evaluator, "engine", None)
    if engine is None:
        return REF_ERROR
    from duddysheet.core.data_table import table_value

    return table_value(engine, context.sheet_name, *context.origin)


@register(
    "GETPIVOTDATA",
    min_args=2,
    argument_spec="data_field, pivot_table, [field1, item1], ...",
    category="Lookup & Reference",
)
def getpivotdata(context: Any, data_field: Any, pivot_table: Any, *pairs: Any) -> Any:
    """Return a summary value from a PivotTable for the given field/item pairs."""
    from duddysheet.core.pivot import getpivotdata as lookup
    from duddysheet.core.pivot import pivot_at
    from duddysheet.core.refs import CellReference

    areas = getattr(pivot_table, "areas", None)
    if not areas:
        return REF_ERROR
    area = areas[0]
    reference = area if isinstance(area, CellReference) else area.start
    try:
        sheet = context.evaluator.workbook.get_sheet(reference.sheet or context.sheet_name)
    except KeyError:
        return REF_ERROR
    spec = pivot_at(sheet, reference.row, reference.column)
    if spec is None:
        return REF_ERROR
    if len(pairs) % 2:
        return VALUE_ERROR
    field = text(scalar(context, data_field))
    filters = []
    for index in range(0, len(pairs), 2):
        name = scalar(context, pairs[index])
        item = scalar(context, pairs[index + 1])
        if is_error(name):
            return name
        if is_error(item):
            return item
        filters.append((text(name), item))
    try:
        value = lookup(context.evaluator.workbook, spec, field, filters)
    except (KeyError, ValueError):
        return REF_ERROR
    return 0 if value is None else value
