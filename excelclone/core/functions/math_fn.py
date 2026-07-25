"""Mathematical and trigonometric worksheet functions."""

from __future__ import annotations

import math
import random
from functools import reduce
from typing import Any

from excelclone.core.errors import DIV_ZERO_ERROR, NUM_ERROR, VALUE_ERROR, is_error
from excelclone.core.functions import register
from excelclone.core.functions.common import (
    clean_number,
    criteria_match,
    first_error,
    flatten,
    number,
    numeric_values,
    round_away,
    scalar,
)


@register("SUM", min_args=1, argument_spec="number1, [number2], ...")
def sum_function(context: Any, *arguments: Any) -> Any:
    """Add numeric arguments and referenced values."""
    values = numeric_values(context, *arguments)
    return values if is_error(values) else clean_number(sum(values))


@register("SUMIF", min_args=2, max_args=3, argument_spec="range, criteria, [sum_range]")
def sumif(context: Any, criteria_range: Any, criterion: Any, sum_range: Any = None) -> Any:
    """Add cells whose corresponding values meet one criterion."""
    criteria_values = flatten(context, criteria_range)
    sum_values = (
        criteria_values if sum_range is None else flatten(context, sum_range)
    )
    error = first_error(criteria_values + sum_values)
    if error is not None:
        return error
    criterion = scalar(context, criterion)
    total = 0.0
    for candidate, value in zip(criteria_values, sum_values):
        if criteria_match(candidate, criterion):
            converted = number(value)
            if not is_error(converted):
                total += converted
    return clean_number(total)


@register(
    "SUMIFS",
    min_args=3,
    argument_spec="sum_range, criteria_range1, criteria1, ...",
)
def sumifs(context: Any, sum_range: Any, *criteria_arguments: Any) -> Any:
    """Add cells that satisfy every supplied criteria range."""
    if len(criteria_arguments) % 2:
        return VALUE_ERROR
    sum_values = flatten(context, sum_range)
    criteria_pairs = [
        (
            flatten(context, criteria_arguments[index]),
            scalar(context, criteria_arguments[index + 1]),
        )
        for index in range(0, len(criteria_arguments), 2)
    ]
    if any(len(values) != len(sum_values) for values, _ in criteria_pairs):
        return VALUE_ERROR
    error = first_error(
        sum_values + [item for values, _ in criteria_pairs for item in values]
    )
    if error is not None:
        return error
    total = 0.0
    for index, value in enumerate(sum_values):
        if all(
            criteria_match(values[index], criterion)
            for values, criterion in criteria_pairs
        ):
            converted = number(value)
            if not is_error(converted):
                total += converted
    return clean_number(total)


@register("SUMPRODUCT", min_args=1, argument_spec="array1, [array2], ...")
def sumproduct(context: Any, *arrays: Any) -> Any:
    """Multiply corresponding array entries and add the products."""
    flattened = [flatten(context, array) for array in arrays]
    if not flattened or any(len(values) != len(flattened[0]) for values in flattened):
        return VALUE_ERROR
    error = first_error([item for values in flattened for item in values])
    if error is not None:
        return error
    total = 0.0
    for entries in zip(*flattened):
        product = 1.0
        for entry in entries:
            converted = number(entry)
            product *= 0 if is_error(converted) else converted
        total += product
    return clean_number(total)


@register("PRODUCT", min_args=1, argument_spec="number1, [number2], ...")
def product(context: Any, *arguments: Any) -> Any:
    """Multiply numeric arguments and referenced values."""
    values = numeric_values(context, *arguments)
    if is_error(values):
        return values
    return clean_number(math.prod(values))


def _one_number(context: Any, value: Any) -> Any:
    return number(scalar(context, value))


@register("ABS", min_args=1, max_args=1, argument_spec="number")
def abs_function(context: Any, value: Any) -> Any:
    """Return the absolute value of a number."""
    converted = _one_number(context, value)
    return converted if is_error(converted) else abs(converted)


@register("SIGN", min_args=1, max_args=1, argument_spec="number")
def sign(context: Any, value: Any) -> Any:
    """Return -1, 0, or 1 according to a number's sign."""
    converted = _one_number(context, value)
    if is_error(converted):
        return converted
    return 0 if converted == 0 else (1 if converted > 0 else -1)


@register("ROUND", min_args=2, max_args=2, argument_spec="number, num_digits")
def round_function(context: Any, value: Any, digits: Any) -> Any:
    """Round a number to a specified number of digits."""
    converted = _one_number(context, value)
    digit_count = _one_number(context, digits)
    if is_error(converted) or is_error(digit_count):
        return VALUE_ERROR
    return clean_number(round_away(converted, int(digit_count)))


def _directed_round(context: Any, value: Any, digits: Any, *, away: bool) -> Any:
    converted = _one_number(context, value)
    digit_count = _one_number(context, digits)
    if is_error(converted) or is_error(digit_count):
        return VALUE_ERROR
    factor = 10 ** int(digit_count)
    magnitude = abs(converted) * factor
    rounded = math.ceil(magnitude) if away else math.floor(magnitude)
    return clean_number(math.copysign(rounded / factor, converted))


@register("ROUNDUP", min_args=2, max_args=2, argument_spec="number, num_digits")
def roundup(context: Any, value: Any, digits: Any) -> Any:
    """Round a number away from zero."""
    return _directed_round(context, value, digits, away=True)


@register("ROUNDDOWN", min_args=2, max_args=2, argument_spec="number, num_digits")
def rounddown(context: Any, value: Any, digits: Any) -> Any:
    """Round a number toward zero."""
    return _directed_round(context, value, digits, away=False)


@register("MROUND", min_args=2, max_args=2, argument_spec="number, multiple")
def mround(context: Any, value: Any, multiple: Any) -> Any:
    """Round a number to the nearest supplied multiple."""
    converted = _one_number(context, value)
    step = _one_number(context, multiple)
    if is_error(converted) or is_error(step):
        return VALUE_ERROR
    if step == 0:
        return 0
    if converted * step < 0:
        return NUM_ERROR
    return clean_number(round_away(converted / step) * step)


def _multiple_round(context: Any, value: Any, significance: Any, *, upward: bool) -> Any:
    converted = _one_number(context, value)
    step = _one_number(context, significance)
    if is_error(converted) or is_error(step):
        return VALUE_ERROR
    if step == 0:
        return 0
    if converted * step < 0:
        return NUM_ERROR
    quotient = converted / step
    rounded = math.ceil(quotient) if upward else math.floor(quotient)
    return clean_number(rounded * step)


@register("CEILING", min_args=2, max_args=2, argument_spec="number, significance")
def ceiling(context: Any, value: Any, significance: Any) -> Any:
    """Round a number upward to a multiple."""
    return _multiple_round(context, value, significance, upward=True)


@register("FLOOR", min_args=2, max_args=2, argument_spec="number, significance")
def floor_function(context: Any, value: Any, significance: Any) -> Any:
    """Round a number downward to a multiple."""
    return _multiple_round(context, value, significance, upward=False)


@register("INT", min_args=1, max_args=1, argument_spec="number")
def int_function(context: Any, value: Any) -> Any:
    """Round a number down to the nearest integer."""
    converted = _one_number(context, value)
    return converted if is_error(converted) else math.floor(converted)


@register("TRUNC", min_args=1, max_args=2, argument_spec="number, [num_digits]")
def trunc(context: Any, value: Any, digits: Any = 0) -> Any:
    """Truncate a number toward zero at a digit position."""
    converted = _one_number(context, value)
    digit_count = _one_number(context, digits)
    if is_error(converted) or is_error(digit_count):
        return VALUE_ERROR
    factor = 10 ** int(digit_count)
    return clean_number(math.trunc(converted * factor) / factor)


@register("MOD", min_args=2, max_args=2, argument_spec="number, divisor")
def mod(context: Any, value: Any, divisor: Any) -> Any:
    """Return the remainder with the divisor's sign."""
    converted = _one_number(context, value)
    denominator = _one_number(context, divisor)
    if is_error(converted) or is_error(denominator):
        return VALUE_ERROR
    if denominator == 0:
        return DIV_ZERO_ERROR
    return clean_number(converted - denominator * math.floor(converted / denominator))


@register("POWER", min_args=2, max_args=2, argument_spec="number, power")
def power(context: Any, value: Any, exponent: Any) -> Any:
    """Raise a number to a power."""
    base = _one_number(context, value)
    exponent_value = _one_number(context, exponent)
    if is_error(base) or is_error(exponent_value):
        return VALUE_ERROR
    try:
        result = base**exponent_value
        return NUM_ERROR if isinstance(result, complex) else result
    except (ArithmeticError, ValueError):
        return NUM_ERROR


@register("SQRT", min_args=1, max_args=1, argument_spec="number")
def sqrt(context: Any, value: Any) -> Any:
    """Return a nonnegative square root."""
    converted = _one_number(context, value)
    if is_error(converted):
        return converted
    return NUM_ERROR if converted < 0 else math.sqrt(converted)


@register("EXP", min_args=1, max_args=1, argument_spec="number")
def exp(context: Any, value: Any) -> Any:
    """Return e raised to a supplied power."""
    converted = _one_number(context, value)
    if is_error(converted):
        return converted
    try:
        return math.exp(converted)
    except OverflowError:
        return NUM_ERROR


def _log(context: Any, value: Any, base: float) -> Any:
    converted = _one_number(context, value)
    if is_error(converted):
        return converted
    if converted <= 0 or base <= 0 or base == 1:
        return NUM_ERROR
    return math.log(converted, base)


@register("LN", min_args=1, max_args=1, argument_spec="number")
def ln(context: Any, value: Any) -> Any:
    """Return the natural logarithm of a positive number."""
    return _log(context, value, math.e)


@register("LOG", min_args=1, max_args=2, argument_spec="number, [base]")
def log(context: Any, value: Any, base: Any = 10) -> Any:
    """Return a logarithm using an optional base."""
    converted_base = _one_number(context, base)
    return converted_base if is_error(converted_base) else _log(context, value, converted_base)


@register("LOG10", min_args=1, max_args=1, argument_spec="number")
def log10(context: Any, value: Any) -> Any:
    """Return the base-10 logarithm of a positive number."""
    return _log(context, value, 10)


@register("RAND", max_args=0, volatile=True, argument_spec="")
def rand(context: Any) -> float:
    """Return a volatile random number from zero through one."""
    return random.random()


@register(
    "RANDBETWEEN",
    min_args=2,
    max_args=2,
    volatile=True,
    argument_spec="bottom, top",
)
def randbetween(context: Any, bottom: Any, top: Any) -> Any:
    """Return a volatile random integer between inclusive limits."""
    lower = _one_number(context, bottom)
    upper = _one_number(context, top)
    if is_error(lower) or is_error(upper):
        return VALUE_ERROR
    if lower > upper:
        return NUM_ERROR
    return random.randint(math.ceil(lower), math.floor(upper))


def _integer_arguments(context: Any, arguments: tuple[Any, ...]) -> Any:
    values = numeric_values(context, *arguments, ignore_non_numeric=False)
    if is_error(values):
        return values
    if any(value < 0 for value in values):
        return NUM_ERROR
    return [int(value) for value in values]


@register("GCD", min_args=1, argument_spec="number1, [number2], ...")
def gcd(context: Any, *arguments: Any) -> Any:
    """Return the greatest common divisor of integers."""
    values = _integer_arguments(context, arguments)
    return values if is_error(values) else reduce(math.gcd, values)


@register("LCM", min_args=1, argument_spec="number1, [number2], ...")
def lcm(context: Any, *arguments: Any) -> Any:
    """Return the least common multiple of integers."""
    values = _integer_arguments(context, arguments)
    return values if is_error(values) else reduce(math.lcm, values)


def _trig_one(context: Any, value: Any, function: Any) -> Any:
    converted = _one_number(context, value)
    if is_error(converted):
        return converted
    try:
        return function(converted)
    except ValueError:
        return NUM_ERROR


@register("SIN", min_args=1, max_args=1, argument_spec="number")
def sin(context: Any, value: Any) -> Any:
    """Return the sine of an angle in radians."""
    return _trig_one(context, value, math.sin)


@register("COS", min_args=1, max_args=1, argument_spec="number")
def cos(context: Any, value: Any) -> Any:
    """Return the cosine of an angle in radians."""
    return _trig_one(context, value, math.cos)


@register("TAN", min_args=1, max_args=1, argument_spec="number")
def tan(context: Any, value: Any) -> Any:
    """Return the tangent of an angle in radians."""
    return _trig_one(context, value, math.tan)


@register("ASIN", min_args=1, max_args=1, argument_spec="number")
def asin(context: Any, value: Any) -> Any:
    """Return the inverse sine in radians."""
    return _trig_one(context, value, math.asin)


@register("ACOS", min_args=1, max_args=1, argument_spec="number")
def acos(context: Any, value: Any) -> Any:
    """Return the inverse cosine in radians."""
    return _trig_one(context, value, math.acos)


@register("ATAN", min_args=1, max_args=1, argument_spec="number")
def atan(context: Any, value: Any) -> Any:
    """Return the inverse tangent in radians."""
    return _trig_one(context, value, math.atan)


@register("ATAN2", min_args=2, max_args=2, argument_spec="x_num, y_num")
def atan2(context: Any, x_value: Any, y_value: Any) -> Any:
    """Return the angle from the positive x-axis to a point."""
    x_number = _one_number(context, x_value)
    y_number = _one_number(context, y_value)
    if is_error(x_number) or is_error(y_number):
        return VALUE_ERROR
    if x_number == 0 and y_number == 0:
        return DIV_ZERO_ERROR
    return math.atan2(y_number, x_number)


@register("PI", max_args=0, argument_spec="")
def pi(context: Any) -> float:
    """Return the mathematical constant pi."""
    return math.pi


@register("DEGREES", min_args=1, max_args=1, argument_spec="angle")
def degrees(context: Any, value: Any) -> Any:
    """Convert radians to degrees."""
    return _trig_one(context, value, math.degrees)


@register("RADIANS", min_args=1, max_args=1, argument_spec="angle")
def radians(context: Any, value: Any) -> Any:
    """Convert degrees to radians."""
    return _trig_one(context, value, math.radians)
