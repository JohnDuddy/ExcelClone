"""Logical and error-handling worksheet functions."""

from __future__ import annotations

from typing import Any

from excelclone.core.errors import NA_ERROR, VALUE_ERROR, is_error
from excelclone.core.functions import register
from excelclone.core.functions.common import flatten, scalar, truthy


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
    """Evaluate and return only the selected branch."""
    condition = truthy(context.scalar(context.evaluate(condition_node)))
    if is_error(condition):
        return condition
    if condition:
        return context.evaluate(true_node)
    return False if false_node is None else context.evaluate(false_node)


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
        condition = truthy(context.scalar(context.evaluate(nodes[index])))
        if is_error(condition):
            return condition
        if condition:
            return context.evaluate(nodes[index + 1])
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
    return (
        context.evaluate(fallback_node)
        if context.scalar(value) == NA_ERROR
        else value
    )


def _logical_values(context: Any, arguments: tuple[Any, ...]) -> Any:
    values = flatten(context, *arguments)
    converted: list[bool] = []
    for value in values:
        logical = truthy(value)
        if is_error(logical):
            return logical
        converted.append(logical)
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
    expression = context.scalar(context.evaluate(expression_node))
    pair_count = len(nodes) // 2
    for index in range(pair_count):
        candidate = context.scalar(context.evaluate(nodes[index * 2]))
        if expression == candidate or (
            isinstance(expression, str)
            and isinstance(candidate, str)
            and expression.casefold() == candidate.casefold()
        ):
            return context.evaluate(nodes[index * 2 + 1])
    if len(nodes) % 2:
        return context.evaluate(nodes[-1])
    return NA_ERROR
