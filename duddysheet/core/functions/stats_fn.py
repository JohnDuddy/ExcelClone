"""Statistical worksheet functions."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from typing import Any

import numpy as np

from duddysheet.core.errors import DIV_ZERO_ERROR, NA_ERROR, NUM_ERROR, VALUE_ERROR, is_error
from duddysheet.core.functions import register
from duddysheet.core.functions.common import (
    clean_number,
    criteria_match,
    first_error,
    flatten,
    number,
    numeric_values,
    rectangular,
    scalar,
)


def _numbers(context: Any, *arguments: Any) -> Any:
    return numeric_values(context, *arguments)


@register("AVERAGE", min_args=1, argument_spec="number1, [number2], ...")
def average(context: Any, *arguments: Any) -> Any:
    """Return the arithmetic mean of numeric values."""
    values = _numbers(context, *arguments)
    if is_error(values):
        return values
    return DIV_ZERO_ERROR if not values else sum(values) / len(values)


def _criteria_average(
    context: Any,
    average_range: Any,
    criteria_pairs: list[tuple[Any, Any]],
) -> Any:
    average_values = flatten(context, average_range)
    pairs = [
        (flatten(context, criteria_range), scalar(context, criterion))
        for criteria_range, criterion in criteria_pairs
    ]
    if any(len(values) != len(average_values) for values, _ in pairs):
        return VALUE_ERROR
    error = first_error(
        average_values + [value for values, _ in pairs for value in values]
    )
    if error is not None:
        return error
    selected: list[int | float] = []
    for index, value in enumerate(average_values):
        if all(criteria_match(values[index], criterion) for values, criterion in pairs):
            converted = number(value)
            if not is_error(converted):
                selected.append(converted)
    return DIV_ZERO_ERROR if not selected else sum(selected) / len(selected)


@register(
    "AVERAGEIF",
    min_args=2,
    max_args=3,
    argument_spec="range, criteria, [average_range]",
)
def averageif(
    context: Any,
    criteria_range: Any,
    criterion: Any,
    average_range: Any = None,
) -> Any:
    """Average cells selected by one criterion."""
    selected_range = criteria_range if average_range is None else average_range
    return _criteria_average(
        context,
        selected_range,
        [(criteria_range, criterion)],
    )


@register(
    "AVERAGEIFS",
    min_args=3,
    argument_spec="average_range, criteria_range1, criteria1, ...",
)
def averageifs(context: Any, average_range: Any, *criteria_arguments: Any) -> Any:
    """Average cells selected by every supplied criterion."""
    if len(criteria_arguments) % 2:
        return VALUE_ERROR
    pairs = [
        (criteria_arguments[index], criteria_arguments[index + 1])
        for index in range(0, len(criteria_arguments), 2)
    ]
    return _criteria_average(context, average_range, pairs)


@register("MEDIAN", min_args=1, argument_spec="number1, [number2], ...")
def median(context: Any, *arguments: Any) -> Any:
    """Return the median of numeric values."""
    values = _numbers(context, *arguments)
    if is_error(values):
        return values
    return NUM_ERROR if not values else statistics.median(values)


@register("MODE", min_args=1, argument_spec="number1, [number2], ...")
def mode(context: Any, *arguments: Any) -> Any:
    """Return the most frequent numeric value."""
    values = _numbers(context, *arguments)
    if is_error(values):
        return values
    counts = Counter(values)
    if not counts:
        return NA_ERROR
    highest = max(counts.values())
    if highest == 1:
        return NA_ERROR
    return next(value for value in values if counts[value] == highest)


@register("COUNT", min_args=1, argument_spec="value1, [value2], ...")
def count(context: Any, *arguments: Any) -> int:
    """Count numeric values."""
    return sum(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in flatten(context, *arguments)
    )


@register("COUNTA", min_args=1, argument_spec="value1, [value2], ...")
def counta(context: Any, *arguments: Any) -> int:
    """Count nonblank values."""
    return sum(value is not None and value != "" for value in flatten(context, *arguments))


@register("COUNTBLANK", min_args=1, max_args=1, argument_spec="range")
def countblank(context: Any, argument: Any) -> int:
    """Count blank values in a range."""
    return sum(value is None or value == "" for value in flatten(context, argument))


@register("COUNTIF", min_args=2, max_args=2, argument_spec="range, criteria")
def countif(context: Any, argument: Any, criterion: Any) -> int:
    """Count values meeting one criterion."""
    selected = scalar(context, criterion)
    return sum(criteria_match(value, selected) for value in flatten(context, argument))


@register(
    "COUNTIFS",
    min_args=2,
    argument_spec="criteria_range1, criteria1, ...",
)
def countifs(context: Any, *arguments: Any) -> Any:
    """Count rows meeting every supplied criterion."""
    if len(arguments) % 2:
        return VALUE_ERROR
    pairs = [
        (flatten(context, arguments[index]), scalar(context, arguments[index + 1]))
        for index in range(0, len(arguments), 2)
    ]
    if not pairs or any(len(values) != len(pairs[0][0]) for values, _ in pairs):
        return VALUE_ERROR
    return sum(
        all(criteria_match(values[index], criterion) for values, criterion in pairs)
        for index in range(len(pairs[0][0]))
    )


def _extreme(context: Any, arguments: tuple[Any, ...], function: Any) -> Any:
    values = _numbers(context, *arguments)
    if is_error(values):
        return values
    return 0 if not values else function(values)


@register("MAX", min_args=1, argument_spec="number1, [number2], ...")
def max_function(context: Any, *arguments: Any) -> Any:
    """Return the largest numeric value."""
    return _extreme(context, arguments, max)


@register("MIN", min_args=1, argument_spec="number1, [number2], ...")
def min_function(context: Any, *arguments: Any) -> Any:
    """Return the smallest numeric value."""
    return _extreme(context, arguments, min)


def _extreme_ifs(
    context: Any,
    target_range: Any,
    criteria_arguments: tuple[Any, ...],
    function: Any,
) -> Any:
    if len(criteria_arguments) % 2:
        return VALUE_ERROR
    targets = flatten(context, target_range)
    pairs = [
        (
            flatten(context, criteria_arguments[index]),
            scalar(context, criteria_arguments[index + 1]),
        )
        for index in range(0, len(criteria_arguments), 2)
    ]
    if any(len(values) != len(targets) for values, _ in pairs):
        return VALUE_ERROR
    selected: list[int | float] = []
    for index, target in enumerate(targets):
        if all(criteria_match(values[index], criterion) for values, criterion in pairs):
            converted = number(target)
            if not is_error(converted):
                selected.append(converted)
    return 0 if not selected else function(selected)


@register("MAXIFS", min_args=3, argument_spec="max_range, criteria_range1, criteria1, ...")
def maxifs(context: Any, target_range: Any, *criteria_arguments: Any) -> Any:
    """Return the maximum value meeting every criterion."""
    return _extreme_ifs(context, target_range, criteria_arguments, max)


@register("MINIFS", min_args=3, argument_spec="min_range, criteria_range1, criteria1, ...")
def minifs(context: Any, target_range: Any, *criteria_arguments: Any) -> Any:
    """Return the minimum value meeting every criterion."""
    return _extreme_ifs(context, target_range, criteria_arguments, min)


def _kth(context: Any, array: Any, k: Any, *, largest: bool) -> Any:
    values = _numbers(context, array)
    index = number(scalar(context, k))
    if is_error(values) or is_error(index):
        return VALUE_ERROR
    index = int(index)
    if index < 1 or index > len(values):
        return NUM_ERROR
    return sorted(values, reverse=largest)[index - 1]


@register("LARGE", min_args=2, max_args=2, argument_spec="array, k")
def large(context: Any, array: Any, k: Any) -> Any:
    """Return the k-th largest value."""
    return _kth(context, array, k, largest=True)


@register("SMALL", min_args=2, max_args=2, argument_spec="array, k")
def small(context: Any, array: Any, k: Any) -> Any:
    """Return the k-th smallest value."""
    return _kth(context, array, k, largest=False)


@register("RANK", min_args=2, max_args=3, argument_spec="number, ref, [order]")
def rank(context: Any, value: Any, reference: Any, order: Any = 0) -> Any:
    """Return a number's rank within a numeric list."""
    target = number(scalar(context, value))
    values = _numbers(context, reference)
    direction = number(scalar(context, order))
    if is_error(target) or is_error(values) or is_error(direction):
        return VALUE_ERROR
    ordered = sorted(values, reverse=direction == 0)
    try:
        return ordered.index(target) + 1
    except ValueError:
        return NA_ERROR


def _dispersion(context: Any, arguments: tuple[Any, ...], *, variance: bool, sample: bool) -> Any:
    values = _numbers(context, *arguments)
    if is_error(values):
        return values
    minimum = 2 if sample else 1
    if len(values) < minimum:
        return DIV_ZERO_ERROR
    result = (
        statistics.variance(values)
        if variance and sample
        else statistics.pvariance(values)
        if variance
        else statistics.stdev(values)
        if sample
        else statistics.pstdev(values)
    )
    return result


@register("STDEV", min_args=1, argument_spec="number1, [number2], ...")
def stdev(context: Any, *arguments: Any) -> Any:
    """Return sample standard deviation."""
    return _dispersion(context, arguments, variance=False, sample=True)


@register("STDEVP", min_args=1, argument_spec="number1, [number2], ...")
def stdevp(context: Any, *arguments: Any) -> Any:
    """Return population standard deviation."""
    return _dispersion(context, arguments, variance=False, sample=False)


@register("VAR", min_args=1, argument_spec="number1, [number2], ...")
def var(context: Any, *arguments: Any) -> Any:
    """Return sample variance."""
    return _dispersion(context, arguments, variance=True, sample=True)


@register("VARP", min_args=1, argument_spec="number1, [number2], ...")
def varp(context: Any, *arguments: Any) -> Any:
    """Return population variance."""
    return _dispersion(context, arguments, variance=True, sample=False)


def _percentile(context: Any, array: Any, fraction: Any) -> Any:
    values = _numbers(context, array)
    percentile = number(scalar(context, fraction))
    if is_error(values) or is_error(percentile):
        return VALUE_ERROR
    if not values or not 0 <= percentile <= 1:
        return NUM_ERROR
    return float(np.percentile(values, percentile * 100, method="linear"))


@register("PERCENTILE", min_args=2, max_args=2, argument_spec="array, k")
def percentile(context: Any, array: Any, fraction: Any) -> Any:
    """Return an inclusive percentile."""
    return _percentile(context, array, fraction)


@register("QUARTILE", min_args=2, max_args=2, argument_spec="array, quart")
def quartile(context: Any, array: Any, quart: Any) -> Any:
    """Return an inclusive quartile."""
    selected = number(scalar(context, quart))
    if is_error(selected) or int(selected) not in range(5):
        return NUM_ERROR
    return _percentile(context, array, int(selected) / 4)


def _paired_numbers(context: Any, known_y: Any, known_x: Any) -> Any:
    y_values = _numbers(context, known_y)
    x_values = _numbers(context, known_x)
    if is_error(y_values) or is_error(x_values):
        return VALUE_ERROR
    if len(y_values) != len(x_values) or len(y_values) < 2:
        return NA_ERROR
    return np.asarray(x_values, dtype=float), np.asarray(y_values, dtype=float)


@register("CORREL", min_args=2, max_args=2, argument_spec="array1, array2")
def correl(context: Any, array1: Any, array2: Any) -> Any:
    """Return the Pearson correlation coefficient."""
    paired = _paired_numbers(context, array1, array2)
    if is_error(paired):
        return paired
    x_values, y_values = paired
    if np.std(x_values) == 0 or np.std(y_values) == 0:
        return DIV_ZERO_ERROR
    return float(np.corrcoef(x_values, y_values)[0, 1])


def _linear_fit(context: Any, known_y: Any, known_x: Any) -> Any:
    paired = _paired_numbers(context, known_y, known_x)
    if is_error(paired):
        return paired
    x_values, y_values = paired
    if np.std(x_values) == 0:
        return DIV_ZERO_ERROR
    slope_value, intercept_value = np.polyfit(x_values, y_values, 1)
    return float(slope_value), float(intercept_value)


@register("SLOPE", min_args=2, max_args=2, argument_spec="known_y's, known_x's")
def slope(context: Any, known_y: Any, known_x: Any) -> Any:
    """Return a least-squares regression slope."""
    fit = _linear_fit(context, known_y, known_x)
    return fit if is_error(fit) else fit[0]


@register("INTERCEPT", min_args=2, max_args=2, argument_spec="known_y's, known_x's")
def intercept(context: Any, known_y: Any, known_x: Any) -> Any:
    """Return a least-squares regression intercept."""
    fit = _linear_fit(context, known_y, known_x)
    return fit if is_error(fit) else fit[1]


@register("FORECAST", min_args=3, max_args=3, argument_spec="x, known_y's, known_x's")
def forecast(context: Any, x_value: Any, known_y: Any, known_x: Any) -> Any:
    """Forecast a y value using linear regression."""
    selected_x = number(scalar(context, x_value))
    fit = _linear_fit(context, known_y, known_x)
    if is_error(selected_x) or is_error(fit):
        return VALUE_ERROR if is_error(selected_x) else fit
    return fit[0] * selected_x + fit[1]


@register("TREND", min_args=1, max_args=4, argument_spec="known_y's, [known_x's], [new_x's], [const]")
def trend(
    context: Any,
    known_y: Any,
    known_x: Any = None,
    new_x: Any = None,
    constant: Any = True,
) -> Any:
    """Return linear-trend predictions as a dynamic array."""
    y_values = _numbers(context, known_y)
    if is_error(y_values) or not y_values:
        return VALUE_ERROR
    x_values = (
        list(range(1, len(y_values) + 1))
        if known_x is None
        else _numbers(context, known_x)
    )
    if is_error(x_values) or len(x_values) != len(y_values):
        return NA_ERROR
    include_intercept = bool(scalar(context, constant))
    if include_intercept:
        slope_value, intercept_value = np.polyfit(x_values, y_values, 1)
    else:
        x_array = np.asarray(x_values, dtype=float)
        y_array = np.asarray(y_values, dtype=float)
        denominator = float(np.dot(x_array, x_array))
        if denominator == 0:
            return DIV_ZERO_ERROR
        slope_value = float(np.dot(x_array, y_array) / denominator)
        intercept_value = 0.0
    targets = x_values if new_x is None else _numbers(context, new_x)
    if is_error(targets):
        return targets
    return rectangular([[slope_value * value + intercept_value] for value in targets])
