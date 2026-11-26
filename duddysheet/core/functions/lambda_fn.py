"""LET, LAMBDA, and the LAMBDA helper functions."""

from __future__ import annotations

from typing import Any

from duddysheet.core.errors import CALC_ERROR, NAME_ERROR, VALUE_ERROR, is_error
from duddysheet.core.functions import register
from duddysheet.core.functions.common import number, scalar


def _binding_name(node: Any) -> str | None:
    import re

    from duddysheet.core.parser import NameNode, StructuredReferenceNode

    if isinstance(node, NameNode) and node.sheet is None and "." not in node.name:
        return node.name
    # LAMBDA's optional parameters are written in brackets: LAMBDA(a, [b], ...).
    if (
        isinstance(node, StructuredReferenceNode)
        and node.table is None
        and re.fullmatch(r"\s*[A-Za-z_][A-Za-z0-9_]*\s*", node.inner)
    ):
        return node.inner.strip()
    return None


@register(
    "LET",
    min_args=3,
    max_args=253,
    argument_spec="name1, name_value1, [name2, name_value2], ..., calculation",
    lazy=True,
    category="Logical",
)
def let(context: Any, *nodes: Any) -> Any:
    """Assign names to calculation results, then evaluate a final calculation."""
    if len(nodes) % 2 == 0:
        return VALUE_ERROR
    current = context
    for index in range(0, len(nodes) - 1, 2):
        name = _binding_name(nodes[index])
        if name is None:
            return NAME_ERROR
        value = current.evaluate(nodes[index + 1])
        current = current.bind({name: value})
    return current.evaluate(nodes[-1])


@register(
    "LAMBDA",
    min_args=1,
    max_args=254,
    argument_spec="[parameter1, parameter2, ...], calculation",
    lazy=True,
    category="Logical",
)
def lambda_function(context: Any, *nodes: Any) -> Any:
    """Create a reusable function from parameter names and a calculation."""
    from duddysheet.core.evaluator import LambdaValue

    parameters: list[str] = []
    for node in nodes[:-1]:
        name = _binding_name(node)
        if name is None or name.casefold() in parameters:
            return VALUE_ERROR
        parameters.append(name.casefold())
    return LambdaValue(
        tuple(parameters),
        nodes[-1],
        tuple(context.bindings.items()),
    )


@register(
    "ISOMITTED",
    min_args=1,
    max_args=1,
    argument_spec="argument",
    lazy=True,
    category="Information",
)
def isomitted(context: Any, node: Any) -> Any:
    """Return TRUE when a LAMBDA parameter received no value."""
    from duddysheet.core.evaluator import OMITTED
    from duddysheet.core.parser import MissingNode

    if isinstance(node, MissingNode):
        return True
    name = _binding_name(node)
    if name is None:
        return False
    return context.bindings.get(name.casefold(), None) is OMITTED


def _require_lambda(value: Any) -> Any:
    from duddysheet.core.evaluator import LambdaValue

    if is_error(value):
        return value
    return value if isinstance(value, LambdaValue) else VALUE_ERROR


def _scalar_result(context: Any, value: Any) -> Any:
    """Reduce a LAMBDA result to one array element; nested arrays are #CALC!."""
    if is_error(value):
        return value
    if context.is_array(value):
        rows = context.matrix(value)
        if len(rows) == 1 and len(rows[0]) == 1:
            return rows[0][0]
        return CALC_ERROR
    return context.scalar(value)


def _as_array(rows: list[list[Any]]) -> tuple[tuple[Any, ...], ...]:
    return tuple(tuple(row) for row in rows)


@register(
    "MAP",
    min_args=2,
    max_args=254,
    argument_spec="array1, [array2], ..., lambda",
    category="Logical",
)
def map_function(context: Any, *arguments: Any) -> Any:
    """Apply a LAMBDA to each element of one or more arrays."""
    function = _require_lambda(arguments[-1])
    if is_error(function):
        return function
    arrays = arguments[:-1]
    return context.map_arrays(
        lambda *items: _scalar_result(context, context.call(function, *items)),
        *arrays,
    )


@register(
    "REDUCE",
    min_args=2,
    max_args=3,
    argument_spec="[initial_value], array, lambda",
    category="Logical",
)
def reduce_function(context: Any, *arguments: Any) -> Any:
    """Accumulate an array to one value by applying a LAMBDA to each element."""
    initial, array, function = (None, *arguments) if len(arguments) == 2 else arguments
    function = _require_lambda(function)
    if is_error(function):
        return function
    accumulator = context.scalar(initial) if not context.is_array(initial) else initial
    for row in context.matrix(array):
        for item in row:
            accumulator = context.call(function, accumulator, item)
            if is_error(accumulator):
                return accumulator
    return accumulator


@register(
    "SCAN",
    min_args=2,
    max_args=3,
    argument_spec="[initial_value], array, lambda",
    category="Logical",
)
def scan_function(context: Any, *arguments: Any) -> Any:
    """Return each intermediate value of accumulating an array with a LAMBDA."""
    initial, array, function = (None, *arguments) if len(arguments) == 2 else arguments
    function = _require_lambda(function)
    if is_error(function):
        return function
    accumulator = context.scalar(initial)
    result: list[list[Any]] = []
    for row in context.matrix(array):
        output: list[Any] = []
        for item in row:
            accumulator = _scalar_result(context, context.call(function, accumulator, item))
            output.append(accumulator)
        result.append(output)
    return _as_array(result)


@register(
    "BYROW",
    min_args=2,
    max_args=2,
    argument_spec="array, lambda",
    category="Logical",
)
def byrow(context: Any, array: Any, function: Any) -> Any:
    """Apply a LAMBDA to each row and return a column of results."""
    function = _require_lambda(function)
    if is_error(function):
        return function
    return _as_array(
        [
            [_scalar_result(context, context.call(function, (tuple(row),)))]
            for row in context.matrix(array)
        ]
    )


@register(
    "BYCOL",
    min_args=2,
    max_args=2,
    argument_spec="array, lambda",
    category="Logical",
)
def bycol(context: Any, array: Any, function: Any) -> Any:
    """Apply a LAMBDA to each column and return a row of results."""
    function = _require_lambda(function)
    if is_error(function):
        return function
    rows = context.matrix(array)
    columns = list(zip(*rows))
    return _as_array(
        [
            [
                _scalar_result(
                    context,
                    context.call(function, tuple((item,) for item in column)),
                )
                for column in columns
            ]
        ]
    )


@register(
    "MAKEARRAY",
    min_args=3,
    max_args=3,
    argument_spec="rows, columns, lambda",
    category="Logical",
)
def makearray(context: Any, rows: Any, columns: Any, function: Any) -> Any:
    """Build an array by calling a LAMBDA with each row and column number."""
    function = _require_lambda(function)
    if is_error(function):
        return function
    row_count = number(scalar(context, rows))
    column_count = number(scalar(context, columns))
    if is_error(row_count):
        return row_count
    if is_error(column_count):
        return column_count
    row_count = int(row_count)
    column_count = int(column_count)
    if row_count < 1 or column_count < 1:
        return VALUE_ERROR
    if row_count * column_count > 1_048_576 * 16:
        return VALUE_ERROR
    return _as_array(
        [
            [
                _scalar_result(context, context.call(function, row, column))
                for column in range(1, column_count + 1)
            ]
            for row in range(1, row_count + 1)
        ]
    )
