"""Information and type-inspection worksheet functions."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from duddysheet.core.errors import NA_ERROR, SpreadsheetError, is_error
from duddysheet.core.functions import register
from duddysheet.core.functions.common import scalar


def _inspected(context: Any, value: Any) -> Any:
    return context.scalar(value)


@register("ISBLANK", min_args=1, max_args=1, argument_spec="value", accepts_errors=True)
def isblank(context: Any, node: Any) -> bool:
    """Return true only when a value is genuinely blank."""
    return _inspected(context, node) is None


@register("ISNUMBER", min_args=1, max_args=1, argument_spec="value", accepts_errors=True)
def isnumber(context: Any, node: Any) -> bool:
    """Return true for numeric values and date serials."""
    value = _inspected(context, node)
    return isinstance(value, (int, float, date, datetime)) and not isinstance(value, bool)


@register("ISTEXT", min_args=1, max_args=1, argument_spec="value", accepts_errors=True)
def istext(context: Any, node: Any) -> bool:
    """Return true for text values."""
    return isinstance(_inspected(context, node), str)


@register("ISERROR", min_args=1, max_args=1, argument_spec="value", accepts_errors=True)
def iserror(context: Any, node: Any) -> bool:
    """Return true for every spreadsheet error."""
    return is_error(_inspected(context, node))


@register("ISERR", min_args=1, max_args=1, argument_spec="value", accepts_errors=True)
def iserr(context: Any, node: Any) -> bool:
    """Return true for errors other than #N/A."""
    value = _inspected(context, node)
    return is_error(value) and value != NA_ERROR


@register("ISNA", min_args=1, max_args=1, argument_spec="value", accepts_errors=True)
def isna(context: Any, node: Any) -> bool:
    """Return true only for the #N/A error."""
    return _inspected(context, node) == NA_ERROR


@register("ISLOGICAL", min_args=1, max_args=1, argument_spec="value", accepts_errors=True)
def islogical(context: Any, node: Any) -> bool:
    """Return true for logical values."""
    return isinstance(_inspected(context, node), bool)


@register("N", min_args=1, max_args=1, argument_spec="value")
def n_function(context: Any, value: Any) -> Any:
    """Convert a value to its numeric information representation."""
    selected = scalar(context, value)
    if is_error(selected):
        return selected
    if isinstance(selected, bool):
        return int(selected)
    if isinstance(selected, (int, float)):
        return selected
    if isinstance(selected, (date, datetime)):
        from duddysheet.core.functions.common import number

        return number(selected)
    return 0


@register("NA", max_args=0, argument_spec="")
def na(context: Any) -> SpreadsheetError:
    """Return the #N/A error value."""
    return NA_ERROR


@register("TYPE", min_args=1, max_args=1, argument_spec="value", lazy=True)
def type_function(context: Any, node: Any) -> int:
    """Return Excel's numeric type code for a value."""
    raw = context.evaluate(node)
    value = context.scalar(raw)
    if is_error(value):
        return 16
    if isinstance(raw, tuple):
        return 64
    if isinstance(value, bool):
        return 4
    if isinstance(value, str):
        return 2
    return 1


@register("ERROR.TYPE", min_args=1, max_args=1, argument_spec="error_val", accepts_errors=True)
def error_type(context: Any, node: Any) -> Any:
    """Return Excel's numeric code for a standard error value."""
    value = _inspected(context, node)
    return value.type_number if isinstance(value, SpreadsheetError) and value.type_number else NA_ERROR
