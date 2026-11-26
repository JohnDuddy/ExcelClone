"""Logical and error-handling worksheet functions."""

from __future__ import annotations

from typing import Any

from duddysheet.core.errors import NA_ERROR, VALUE_ERROR, is_error
from duddysheet.core.functions import register
from duddysheet.core.functions.common import flatten, scalar, truthy


@register(
    "IF",
    min_args=2,
    max_args=3,
    argument_spec="logical_test, value_if_true, [value_if_false]",
    lazy=True,
)
def if_function(
    context: Any,
    condition_node: Any,
    true_node: Any,
    false_node: Any = None,
) -> Any:
    """Evaluate and return only the selected branch; arrays select per element."""
    raw_condition = context.evaluate(condition_node)
    if context.is_array(raw_condition):
        true_value = context.evaluate(true_node)
        false_value = False if false_node is None else context.evaluate(false_node)
        return context.map_arrays(_select, raw_condition, true_value, false_value)
    condition = truthy(context.scalar(raw_condition))
    if is_error(condition):
        return condition
    if condition:
        return context.evaluate(true_node)
    return False if false_node is None else context.evaluate(false_node)


def _select(condition: Any, true_value: Any, false_value: Any) -> Any:
    selected = truthy(condition)
    if is_error(selected):
        return selected
    return true_value if selected else false_value


@register(
    "IFS",
    min_args=2,
    argument_spec="logical_test1, value_if_true1, ...",
    lazy=True,
)
def ifs(context: Any, *nodes: Any) -> Any:
    """Return the result paired with the first true condition."""
    if len(nodes) % 2:
        return VALUE_ERROR
    for index in range(0, len(nodes), 2):
        raw_condition = context.evaluate(nodes[index])
        if context.is_array(raw_condition):
            values = [context.evaluate(node) for node in nodes]
            return context.map_arrays(_first_true, *values)
        condition = truthy(context.scalar(raw_condition))
        if is_error(condition):
            return condition
        if condition:
            return context.evaluate(nodes[index + 1])
    return NA_ERROR


def _first_true(*pairs: Any) -> Any:
    for index in range(0, len(pairs), 2):
        condition = truthy(pairs[index])
        if is_error(condition):
            return condition
        if condition:
            return pairs[index + 1]
    return NA_ERROR


@register(
    "IFERROR",
    min_args=2,
    max_args=2,
    argument_spec="value, value_if_error",
    lazy=True,
)
def iferror(context: Any, value_node: Any, fallback_node: Any) -> Any:
    """Return a fallback only when the first expression is an error."""
    value = context.evaluate(value_node)
    if context.is_array(value):
        fallback = context.evaluate(fallback_node)
        return context.map_arrays(
            lambda item, other: other if is_error(item) else item,
            value,
            fallback,
        )
    return context.evaluate(fallback_node) if is_error(context.scalar(value)) else value


@register(
    "IFNA",
    min_args=2,
    max_args=2,
    argument_spec="value, value_if_na",
    lazy=True,
)
def ifna(context: Any, value_node: Any, fallback_node: Any) -> Any:
    """Return a fallback only for the #N/A error."""
    value = context.evaluate(value_node)
    if context.is_array(value):
        fallback = context.evaluate(fallback_node)
        return context.map_arrays(
            lambda item, other: other if item == NA_ERROR else item,
            value,
            fallback,
        )
    return (
        context.evaluate(fallback_node)
        if context.scalar(value) == NA_ERROR
        else value
    )


def _logical_values(context: Any, arguments: tuple[Any, ...]) -> Any:
    """Collect logicals as Excel does: ranges skip text and blanks."""
    converted: list[bool] = []
    for argument in arguments:
        from_range = context.is_array(argument) or hasattr(argument, "areas")
        for value in flatten(context, argument):
            if is_error(value):
                return value
            if from_range and (value is None or isinstance(value, str)):
                continue
            logical = truthy(value)
            if is_error(logical):
                return logical
            converted.append(logical)
    if not converted:
        return VALUE_ERROR
    return converted


@register("AND", min_args=1, argument_spec="logical1, [logical2], ...")
def and_function(context: Any, *arguments: Any) -> Any:
    """Return true when every argument is true."""
    values = _logical_values(context, arguments)
    return values if is_error(values) else all(values)


@register("OR", min_args=1, argument_spec="logical1, [logical2], ...")
def or_function(context: Any, *arguments: Any) -> Any:
    """Return true when any argument is true."""
    values = _logical_values(context, arguments)
    return values if is_error(values) else any(values)


@register("NOT", min_args=1, max_args=1, argument_spec="logical")
def not_function(context: Any, argument: Any) -> Any:
    """Reverse a logical value."""
    value = truthy(scalar(context, argument))
    return value if is_error(value) else not value


@register("XOR", min_args=1, argument_spec="logical1, [logical2], ...")
def xor(context: Any, *arguments: Any) -> Any:
    """Return true when an odd number of arguments are true."""
    values = _logical_values(context, arguments)
    return values if is_error(values) else sum(values) % 2 == 1


@register("TRUE", max_args=0, argument_spec="")
def true_function(context: Any) -> bool:
    """Return the logical value TRUE."""
    return True


@register("FALSE", max_args=0, argument_spec="")
def false_function(context: Any) -> bool:
    """Return the logical value FALSE."""
    return False


@register(
    "SWITCH",
    min_args=3,
    argument_spec="expression, value1, result1, ..., [default]",
    lazy=True,
)
def switch(context: Any, expression_node: Any, *nodes: Any) -> Any:
    """Match an expression against cases and return the paired result."""
    raw_expression = context.evaluate(expression_node)
    if context.is_array(raw_expression):
        values = [context.evaluate(node) for node in nodes]
        return context.map_arrays(_switch_scalar, raw_expression, *values)
    expression = context.scalar(raw_expression)
    if is_error(expression):
        return expression
    pair_count = len(nodes) // 2
    for index in range(pair_count):
        candidate = context.scalar(context.evaluate(nodes[index * 2]))
        if _switch_equal(expression, candidate):
            return context.evaluate(nodes[index * 2 + 1])
    if len(nodes) % 2:
        return context.evaluate(nodes[-1])
    return NA_ERROR


def _switch_equal(expression: Any, candidate: Any) -> bool:
    from duddysheet.core.values import compare

    if is_error(expression) or is_error(candidate):
        return False
    return compare(expression, candidate, "=") is True


def _switch_scalar(expression: Any, *values: Any) -> Any:
    if is_error(expression):
        return expression
    pair_count = len(values) // 2
    for index in range(pair_count):
        if _switch_equal(expression, values[index * 2]):
            return values[index * 2 + 1]
    if len(values) % 2:
        return values[-1]
    return NA_ERROR
