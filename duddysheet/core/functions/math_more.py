"""Excel math and trigonometry functions beyond the core arithmetic set."""

from __future__ import annotations

import math
import random
from typing import Any

import numpy as np

from duddysheet.core.errors import (
    DIV_ZERO_ERROR,
    NUM_ERROR,
    VALUE_ERROR,
    is_error,
)
from duddysheet.core.functions import lift_all, register
from duddysheet.core.functions.common import (
    flatten,
    is_collection,
    number,
    numeric_values,
    scalar,
    text,
)

MATH = "Math & Trig"


def _num(context: Any, value: Any) -> Any:
    return number(scalar(context, value))


def _nums(context: Any, *values: Any) -> Any:
    converted = [_num(context, value) for value in values]
    for item in converted:
        if is_error(item):
            return item
    return converted


def _finite(value: float) -> Any:
    return value if math.isfinite(value) else NUM_ERROR


def _unary(name: str, description: str, function: Any, *, domain: Any = None) -> None:
    def implementation(context: Any, value: Any) -> Any:
        converted = _num(context, value)
        if is_error(converted):
            return converted
        if domain is not None:
            failure = domain(converted)
            if failure is not None:
                return failure
        try:
            return _finite(function(converted))
        except (ValueError, OverflowError):
            return NUM_ERROR
        except ZeroDivisionError:
            return DIV_ZERO_ERROR

    implementation.__doc__ = description
    register(
        name,
        min_args=1,
        max_args=1,
        argument_spec="number",
        lift=lift_all,
        category=MATH,
    )(implementation)


def _nonzero(value: float) -> Any:
    return DIV_ZERO_ERROR if value == 0 else None


def _limit(value: float) -> Any:
    return NUM_ERROR if abs(value) >= 2**27 else None


_unary("SINH", "Return the hyperbolic sine of a number.", math.sinh)
_unary("COSH", "Return the hyperbolic cosine of a number.", math.cosh)
_unary("TANH", "Return the hyperbolic tangent of a number.", math.tanh)
_unary("ASINH", "Return the inverse hyperbolic sine of a number.", math.asinh)
_unary("ACOSH", "Return the inverse hyperbolic cosine of a number.", math.acosh)
_unary("ATANH", "Return the inverse hyperbolic tangent of a number.", math.atanh)
_unary(
    "COT",
    "Return the cotangent of an angle in radians.",
    lambda x: 1 / math.tan(x),
    domain=lambda x: _nonzero(x) or _limit(x),
)
_unary(
    "COTH",
    "Return the hyperbolic cotangent of a number.",
    lambda x: 1 / math.tanh(x),
    domain=_nonzero,
)
_unary(
    "CSC",
    "Return the cosecant of an angle in radians.",
    lambda x: 1 / math.sin(x),
    domain=lambda x: _nonzero(x) or _limit(x),
)
_unary(
    "CSCH",
    "Return the hyperbolic cosecant of a number.",
    lambda x: 1 / math.sinh(x),
    domain=_nonzero,
)
_unary(
    "SEC",
    "Return the secant of an angle in radians.",
    lambda x: 1 / math.cos(x),
    domain=_limit,
)
_unary("SECH", "Return the hyperbolic secant of a number.", lambda x: 1 / math.cosh(x))
_unary("ACOT", "Return the arccotangent of a number.", lambda x: math.pi / 2 - math.atan(x))
_unary(
    "ACOTH",
    "Return the inverse hyperbolic cotangent of a number.",
    lambda x: 0.5 * math.log((x + 1) / (x - 1)),
    domain=lambda x: NUM_ERROR if abs(x) <= 1 else None,
)
_unary(
    "SQRTPI",
    "Return the square root of a number multiplied by pi.",
    lambda x: math.sqrt(x * math.pi),
    domain=lambda x: NUM_ERROR if x < 0 else None,
)


def _round_to_parity(value: float, *, even: bool) -> int:
    sign = -1 if value < 0 else 1
    magnitude = math.ceil(abs(value))
    if even and magnitude % 2:
        magnitude += 1
    if not even and magnitude % 2 == 0:
        magnitude += 1
    return sign * magnitude


@register("EVEN", min_args=1, max_args=1, argument_spec="number", lift=lift_all, category=MATH)
def even(context: Any, value: Any) -> Any:
    """Round a number away from zero to the nearest even integer."""
    converted = _num(context, value)
    return converted if is_error(converted) else _round_to_parity(converted, even=True)


@register("ODD", min_args=1, max_args=1, argument_spec="number", lift=lift_all, category=MATH)
def odd(context: Any, value: Any) -> Any:
    """Round a number away from zero to the nearest odd integer."""
    converted = _num(context, value)
    return converted if is_error(converted) else _round_to_parity(converted, even=False)


@register(
    "QUOTIENT",
    min_args=2,
    max_args=2,
    argument_spec="numerator, denominator",
    lift=lift_all,
    category=MATH,
)
def quotient(context: Any, numerator: Any, denominator: Any) -> Any:
    """Return the integer portion of a division."""
    values = _nums(context, numerator, denominator)
    if is_error(values):
        return values
    if values[1] == 0:
        return DIV_ZERO_ERROR
    return math.trunc(values[0] / values[1])


@register("FACT", min_args=1, max_args=1, argument_spec="number", lift=lift_all, category=MATH)
def fact(context: Any, value: Any) -> Any:
    """Return the factorial of a number."""
    converted = _num(context, value)
    if is_error(converted):
        return converted
    n = math.trunc(converted)
    if n < 0 or n > 170:
        return NUM_ERROR
    return math.factorial(n)


@register(
    "FACTDOUBLE",
    min_args=1,
    max_args=1,
    argument_spec="number",
    lift=lift_all,
    category=MATH,
)
def factdouble(context: Any, value: Any) -> Any:
    """Return the double factorial of a number."""
    converted = _num(context, value)
    if is_error(converted):
        return converted
    n = math.trunc(converted)
    if n < -1 or n > 300:
        return NUM_ERROR
    result = 1
    while n > 1:
        result *= n
        n -= 2
    return result


@register(
    "COMBIN",
    min_args=2,
    max_args=2,
    argument_spec="number, number_chosen",
    lift=lift_all,
    category=MATH,
)
def combin(context: Any, total: Any, chosen: Any) -> Any:
    """Return the number of combinations for a given number of items."""
    values = _nums(context, total, chosen)
    if is_error(values):
        return values
    n, k = math.trunc(values[0]), math.trunc(values[1])
    if n < 0 or k < 0 or n < k:
        return NUM_ERROR
    return math.comb(n, k)


@register(
    "COMBINA",
    min_args=2,
    max_args=2,
    argument_spec="number, number_chosen",
    lift=lift_all,
    category=MATH,
)
def combina(context: Any, total: Any, chosen: Any) -> Any:
    """Return the number of combinations with repetitions."""
    values = _nums(context, total, chosen)
    if is_error(values):
        return values
    n, k = math.trunc(values[0]), math.trunc(values[1])
    if n < 0 or k < 0 or (n == 0 and k > 0):
        return NUM_ERROR
    if n == 0 and k == 0:
        return 1
    return math.comb(n + k - 1, k)


@register(
    "MULTINOMIAL",
    min_args=1,
    argument_spec="number1, [number2], ...",
    category=MATH,
)
def multinomial(context: Any, *arguments: Any) -> Any:
    """Return the multinomial coefficient of a set of numbers."""
    values = numeric_values(context, *arguments)
    if is_error(values):
        return values
    terms = [math.trunc(value) for value in values]
    if any(term < 0 for term in terms):
        return NUM_ERROR
    result = math.factorial(sum(terms))
    for term in terms:
        result //= math.factorial(term)
    return result


@register(
    "SERIESSUM",
    min_args=4,
    max_args=4,
    argument_spec="x, n, m, coefficients",
    category=MATH,
)
def seriessum(context: Any, x: Any, n: Any, m: Any, coefficients: Any) -> Any:
    """Return the sum of a power series."""
    values = _nums(context, x, n, m)
    if is_error(values):
        return values
    terms = flatten(context, coefficients)
    total = 0.0
    for index, coefficient in enumerate(terms):
        if is_error(coefficient):
            return coefficient
        converted = number(coefficient)
        if is_error(converted):
            return VALUE_ERROR
        try:
            total += converted * values[0] ** (values[1] + index * values[2])
        except (OverflowError, ZeroDivisionError):
            return NUM_ERROR
    return _finite(total)


@register("SUMSQ", min_args=1, argument_spec="number1, [number2], ...", category=MATH)
def sumsq(context: Any, *arguments: Any) -> Any:
    """Return the sum of the squares of the arguments."""
    values = numeric_values(context, *arguments)
    return values if is_error(values) else math.fsum(value * value for value in values)


def _paired_arrays(context: Any, first: Any, second: Any) -> Any:
    left = flatten(context, first)
    right = flatten(context, second)
    if len(left) != len(right):
        from duddysheet.core.errors import NA_ERROR

        return NA_ERROR
    pairs: list[tuple[float, float]] = []
    for a, b in zip(left, right):
        if is_error(a):
            return a
        if is_error(b):
            return b
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not (
            isinstance(a, bool) or isinstance(b, bool)
        ):
            pairs.append((float(a), float(b)))
    return pairs


def _register_pair_sum(name: str, description: str, function: Any) -> None:
    def implementation(context: Any, first: Any, second: Any) -> Any:
        pairs = _paired_arrays(context, first, second)
        if is_error(pairs):
            return pairs
        return math.fsum(function(a, b) for a, b in pairs)

    implementation.__doc__ = description
    register(
        name,
        min_args=2,
        max_args=2,
        argument_spec="array_x, array_y",
        category=MATH,
    )(implementation)


_register_pair_sum(
    "SUMX2MY2",
    "Return the sum of the difference of squares of corresponding values.",
    lambda a, b: a * a - b * b,
)
_register_pair_sum(
    "SUMX2PY2",
    "Return the sum of the sum of squares of corresponding values.",
    lambda a, b: a * a + b * b,
)
_register_pair_sum(
    "SUMXMY2",
    "Return the sum of squares of differences of corresponding values.",
    lambda a, b: (a - b) ** 2,
)


def _rounding(
    value: float,
    significance: float,
    *,
    upward: bool,
    away_from_zero: bool,
) -> float:
    if significance == 0:
        return 0
    significance = abs(significance)
    quotient_value = value / significance
    if value < 0 and away_from_zero:
        rounded = math.floor(quotient_value + 1e-12) if upward else math.ceil(quotient_value - 1e-12)
    else:
        rounded = math.ceil(quotient_value - 1e-12) if upward else math.floor(quotient_value + 1e-12)
    result = rounded * significance
    return int(result) if float(result).is_integer() else result


@register(
    "CEILING.MATH",
    min_args=1,
    max_args=3,
    argument_spec="number, [significance], [mode]",
    lift=lift_all,
    category=MATH,
)
def ceiling_math(context: Any, value: Any, significance: Any = 1, mode: Any = 0) -> Any:
    """Round up to the nearest integer or multiple; mode rounds negatives away from zero."""
    values = _nums(context, value, 1 if significance is None else significance, mode or 0)
    if is_error(values):
        return values
    return _rounding(values[0], values[1], upward=True, away_from_zero=values[2] != 0)


@register(
    "FLOOR.MATH",
    min_args=1,
    max_args=3,
    argument_spec="number, [significance], [mode]",
    lift=lift_all,
    category=MATH,
)
def floor_math(context: Any, value: Any, significance: Any = 1, mode: Any = 0) -> Any:
    """Round down to the nearest integer or multiple; mode rounds negatives toward zero."""
    values = _nums(context, value, 1 if significance is None else significance, mode or 0)
    if is_error(values):
        return values
    return _rounding(values[0], values[1], upward=False, away_from_zero=values[2] != 0)


def _precise(name: str, *, upward: bool, category: str = MATH) -> None:
    def implementation(context: Any, value: Any, significance: Any = 1) -> Any:
        values = _nums(context, value, 1 if significance is None else significance)
        if is_error(values):
            return values
        return _rounding(values[0], values[1], upward=upward, away_from_zero=False)

    direction = "up" if upward else "down"
    implementation.__doc__ = (
        f"Round a number {direction} to the nearest multiple, regardless of sign."
    )
    register(
        name,
        min_args=1,
        max_args=2,
        argument_spec="number, [significance]",
        lift=lift_all,
        category=category,
    )(implementation)


_precise("CEILING.PRECISE", upward=True)
_precise("ISO.CEILING", upward=True)
_precise("FLOOR.PRECISE", upward=False)


_ROMAN_CHARS = "MDCLXVI"
_ROMAN_VALUES = (1000, 500, 100, 50, 10, 5, 1)


def roman_numeral(value: int, mode: int) -> str:
    """Render 0..3999 as Roman numerals in Excel's five forms (0 classic .. 4 simplified)."""
    result: list[str] = []
    remaining = value
    max_index = len(_ROMAN_VALUES) - 1
    for step in range(max_index // 2 + 1):
        index = 2 * step
        digit = remaining // _ROMAN_VALUES[index]
        if digit % 5 == 4:
            second = index - 1 if digit == 4 else index - 2
            steps = 0
            while steps < mode and index < max_index:
                steps += 1
                if _ROMAN_VALUES[second] - _ROMAN_VALUES[index + 1] <= remaining:
                    index += 1
                else:
                    steps = mode
            result.append(_ROMAN_CHARS[index] + _ROMAN_CHARS[second])
            remaining += _ROMAN_VALUES[index]
            remaining -= _ROMAN_VALUES[second]
        else:
            if digit > 4:
                result.append(_ROMAN_CHARS[index - 1])
            result.append(_ROMAN_CHARS[index] * (digit % 5))
            remaining %= _ROMAN_VALUES[index]
    return "".join(result)


@register(
    "ROMAN",
    min_args=1,
    max_args=2,
    argument_spec="number, [form]",
    lift=lift_all,
    category=MATH,
)
def roman(context: Any, value: Any, form: Any = 0) -> Any:
    """Convert an Arabic number to Roman numerals as text."""
    selected = _num(context, value)
    if is_error(selected):
        return selected
    raw_form = scalar(context, form)
    if isinstance(raw_form, bool):
        mode = 0 if raw_form else 4
    else:
        converted = number(raw_form if raw_form is not None else 0)
        if is_error(converted):
            return converted
        mode = math.trunc(converted)
    number_value = math.trunc(selected)
    if not 0 <= number_value <= 3999 or not 0 <= mode <= 4:
        return VALUE_ERROR
    return roman_numeral(number_value, mode)


_ARABIC_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


@register("ARABIC", min_args=1, max_args=1, argument_spec="text", lift=lift_all, category=MATH)
def arabic(context: Any, value: Any) -> Any:
    """Convert a Roman numeral to an Arabic number."""
    source = text(scalar(context, value)).strip().upper()
    negative = source.startswith("-")
    source = source.removeprefix("-")
    if len(source) > 255 or any(character not in _ARABIC_VALUES for character in source):
        return VALUE_ERROR
    total = 0
    for index, character in enumerate(source):
        current = _ARABIC_VALUES[character]
        following = _ARABIC_VALUES[source[index + 1]] if index + 1 < len(source) else 0
        total += -current if current < following else current
    return -total if negative else total


_DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@register(
    "BASE",
    min_args=2,
    max_args=3,
    argument_spec="number, radix, [min_length]",
    lift=lift_all,
    category=MATH,
)
def base(context: Any, value: Any, radix: Any, min_length: Any = 0) -> Any:
    """Convert a number into text in another base."""
    values = _nums(context, value, radix, min_length or 0)
    if is_error(values):
        return values
    number_value, base_value, length = (math.trunc(item) for item in values)
    if number_value < 0 or number_value >= 2**53 or not 2 <= base_value <= 36 or not 0 <= length <= 255:
        return NUM_ERROR
    digits: list[str] = []
    remaining = number_value
    while remaining:
        remaining, digit = divmod(remaining, base_value)
        digits.append(_DIGITS[digit])
    rendered = "".join(reversed(digits)) or "0"
    return rendered.rjust(length, "0")


@register(
    "DECIMAL",
    min_args=2,
    max_args=2,
    argument_spec="text, radix",
    lift=lift_all,
    category=MATH,
)
def decimal(context: Any, value: Any, radix: Any) -> Any:
    """Convert a text representation of a number in a given base into a decimal number."""
    source = text(scalar(context, value)).strip().upper()
    base_value = _num(context, radix)
    if is_error(base_value):
        return base_value
    base_value = math.trunc(base_value)
    if not 2 <= base_value <= 36 or len(source) > 255:
        return NUM_ERROR
    if not source:
        return 0
    try:
        return int(source, base_value)
    except ValueError:
        return NUM_ERROR


# ----------------------------------------------------------------- matrices
def _numeric_matrix(context: Any, value: Any) -> Any:
    rows = context.matrix(value)
    result: list[list[float]] = []
    for row in rows:
        converted_row: list[float] = []
        for item in row:
            if is_error(item):
                return item
            if isinstance(item, bool) or item is None or isinstance(item, str):
                return VALUE_ERROR
            converted = number(item)
            if is_error(converted):
                return VALUE_ERROR
            converted_row.append(float(converted))
        result.append(converted_row)
    return np.array(result, dtype=float)


def _array_result(matrix: np.ndarray) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        tuple(int(item) if float(item).is_integer() and abs(item) < 2**53 else float(item) for item in row)
        for row in matrix
    )


@register("MMULT", min_args=2, max_args=2, argument_spec="array1, array2", category=MATH)
def mmult(context: Any, first: Any, second: Any) -> Any:
    """Return the matrix product of two arrays."""
    left = _numeric_matrix(context, first)
    right = _numeric_matrix(context, second)
    if is_error(left):
        return left
    if is_error(right):
        return right
    if left.shape[1] != right.shape[0]:
        return VALUE_ERROR
    return _array_result(left @ right)


@register("MDETERM", min_args=1, max_args=1, argument_spec="array", category=MATH)
def mdeterm(context: Any, array: Any) -> Any:
    """Return the matrix determinant of an array."""
    matrix = _numeric_matrix(context, array)
    if is_error(matrix):
        return matrix
    if matrix.shape[0] != matrix.shape[1]:
        return VALUE_ERROR
    result = float(np.linalg.det(matrix))
    rounded = round(result)
    return rounded if abs(result - rounded) < 1e-9 * max(1.0, abs(result)) else result


@register("MINVERSE", min_args=1, max_args=1, argument_spec="array", category=MATH)
def minverse(context: Any, array: Any) -> Any:
    """Return the inverse matrix of an array."""
    matrix = _numeric_matrix(context, array)
    if is_error(matrix):
        return matrix
    if matrix.shape[0] != matrix.shape[1]:
        return VALUE_ERROR
    if abs(np.linalg.det(matrix)) < 1e-15:
        return NUM_ERROR
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError:
        return NUM_ERROR
    return tuple(tuple(float(item) for item in row) for row in inverse)


@register("MUNIT", min_args=1, max_args=1, argument_spec="dimension", category=MATH)
def munit(context: Any, dimension: Any) -> Any:
    """Return the unit matrix of a given dimension."""
    size = _num(context, dimension)
    if is_error(size):
        return size
    size = math.trunc(size)
    if size < 1:
        return VALUE_ERROR
    return tuple(tuple(1 if row == column else 0 for column in range(size)) for row in range(size))


# --------------------------------------------------------- dynamic arrays
@register(
    "SEQUENCE",
    min_args=1,
    max_args=4,
    argument_spec="rows, [columns], [start], [step]",
    category=MATH,
)
def sequence(
    context: Any,
    rows: Any,
    columns: Any = 1,
    start: Any = 1,
    step: Any = 1,
) -> Any:
    """Generate a list of sequential numbers in an array."""
    values = _nums(
        context,
        rows,
        1 if columns is None else columns,
        1 if start is None else start,
        1 if step is None else step,
    )
    if is_error(values):
        return values
    row_count, column_count = math.trunc(values[0]), math.trunc(values[1])
    if row_count < 1 or column_count < 1:
        from duddysheet.core.errors import CALC_ERROR

        return CALC_ERROR
    if row_count * column_count > 1_048_576 * 16:
        return NUM_ERROR
    first, increment = values[2], values[3]
    return tuple(
        tuple(first + (row * column_count + column) * increment for column in range(column_count))
        for row in range(row_count)
    )


@register(
    "RANDARRAY",
    min_args=0,
    max_args=5,
    volatile=True,
    argument_spec="[rows], [columns], [min], [max], [whole_number]",
    category=MATH,
)
def randarray(
    context: Any,
    rows: Any = 1,
    columns: Any = 1,
    minimum: Any = 0,
    maximum: Any = 1,
    whole_number: Any = False,
) -> Any:
    """Return an array of random numbers."""
    values = _nums(
        context,
        1 if rows is None else rows,
        1 if columns is None else columns,
        0 if minimum is None else minimum,
        1 if maximum is None else maximum,
    )
    if is_error(values):
        return values
    row_count, column_count = math.trunc(values[0]), math.trunc(values[1])
    low, high = values[2], values[3]
    whole = bool(scalar(context, whole_number)) if whole_number is not None else False
    if row_count < 1 or column_count < 1 or low > high:
        return VALUE_ERROR
    if whole and (not float(low).is_integer() or not float(high).is_integer()):
        return VALUE_ERROR

    def draw() -> Any:
        if whole:
            return random.randint(int(low), int(high))
        return low + random.random() * (high - low)

    return tuple(tuple(draw() for _ in range(column_count)) for _ in range(row_count))


# ------------------------------------------------------ SUBTOTAL / AGGREGATE
_SUBTOTAL_FUNCTIONS = {
    1: "AVERAGE",
    2: "COUNT",
    3: "COUNTA",
    4: "MAX",
    5: "MIN",
    6: "PRODUCT",
    7: "STDEV.S",
    8: "STDEV.P",
    9: "SUM",
    10: "VAR.S",
    11: "VAR.P",
}
_AGGREGATE_FUNCTIONS = {
    **_SUBTOTAL_FUNCTIONS,
    12: "MEDIAN",
    13: "MODE.SNGL",
    14: "LARGE",
    15: "SMALL",
    16: "PERCENTILE.INC",
    17: "QUARTILE.INC",
    18: "PERCENTILE.EXC",
    19: "QUARTILE.EXC",
}


def _is_subtotal_cell(cell: Any) -> bool:
    if not cell.is_formula:
        return False
    upper = cell.raw_input.upper()
    return "SUBTOTAL(" in upper or "AGGREGATE(" in upper


def _collect_cells(
    context: Any,
    argument: Any,
    *,
    skip_hidden: bool,
    skip_nested: bool,
) -> list[Any]:
    """Values of a reference, excluding filtered (and optionally hidden) rows."""
    from duddysheet.core.evaluator import _cell_value
    from duddysheet.core.refs import CellReference, RangeReference

    areas = getattr(argument, "areas", None)
    if not areas:
        return context.values(argument)
    workbook = context.evaluator.workbook
    values: list[Any] = []
    for area in areas:
        sheet_name = area.sheet or context.sheet_name
        try:
            sheet = workbook.get_sheet(sheet_name)
        except KeyError:
            from duddysheet.core.errors import REF_ERROR

            values.append(REF_ERROR)
            continue
        if isinstance(area, CellReference):
            area = RangeReference(area, area)
        min_row, max_row, min_column, max_column = context.evaluator.reference_bounds(area)
        excluded = sheet.hidden_rows if skip_hidden else sheet.filtered_rows
        for row in range(min_row, max_row + 1):
            if row in excluded:
                continue
            for column in range(min_column, max_column + 1):
                cell = sheet.get_cell(row, column)
                if skip_nested and _is_subtotal_cell(cell):
                    continue
                values.append(_cell_value(cell))
    return values


def _summarize(name: str, values: list[Any], *, ignore_errors: bool, k: Any = None) -> Any:
    from duddysheet.core.functions.stats_more import statistic

    if name == "COUNTA":
        return sum(value is not None for value in values if not (ignore_errors and is_error(value)))
    numbers: list[float] = []
    for value in values:
        if is_error(value):
            if ignore_errors:
                continue
            return value
        if isinstance(value, bool) or value is None or isinstance(value, str):
            continue
        converted = number(value)
        if not is_error(converted):
            numbers.append(converted)
    return statistic(name, numbers, k)


@register(
    "SUBTOTAL",
    min_args=2,
    argument_spec="function_num, ref1, [ref2], ...",
    category=MATH,
)
def subtotal(context: Any, function_number: Any, *references: Any) -> Any:
    """Return a subtotal that skips filtered rows, nested subtotals, and (101-111) hidden rows."""
    selected = _num(context, function_number)
    if is_error(selected):
        return selected
    code = math.trunc(selected)
    skip_hidden = code > 100
    name = _SUBTOTAL_FUNCTIONS.get(code - 100 if skip_hidden else code)
    if name is None:
        return VALUE_ERROR
    values: list[Any] = []
    for reference in references:
        if not hasattr(reference, "areas"):
            return VALUE_ERROR
        values.extend(
            _collect_cells(context, reference, skip_hidden=skip_hidden, skip_nested=True)
        )
    return _summarize(name, values, ignore_errors=False)


@register(
    "AGGREGATE",
    min_args=3,
    argument_spec="function_num, options, ref1, [ref2 | k], ...",
    category=MATH,
)
def aggregate(context: Any, function_number: Any, options: Any, *arguments: Any) -> Any:
    """Return an aggregate that can ignore hidden rows, errors, and nested subtotals."""
    settings = [_num(context, function_number), _num(context, options if options is not None else 0)]
    for item in settings:
        if is_error(item):
            return item
    code, option = (math.trunc(item) for item in settings)
    name = _AGGREGATE_FUNCTIONS.get(code)
    if name is None or not 0 <= option <= 7:
        return VALUE_ERROR
    skip_nested = option in (0, 1, 2, 3)
    skip_hidden = option in (1, 3, 5, 7)
    ignore_errors = option in (2, 3, 6, 7)
    k = None
    sources = list(arguments)
    if code >= 14:
        if len(sources) < 2:
            return VALUE_ERROR
        k = _num(context, sources.pop())
        if is_error(k):
            return k
    elif any(not hasattr(source, "areas") for source in sources):
        # Functions 1-13 use AGGREGATE's reference form, which needs ranges.
        return VALUE_ERROR
    values: list[Any] = []
    for source in sources:
        if is_collection(source):
            values.extend(
                _collect_cells(
                    context,
                    source,
                    skip_hidden=skip_hidden,
                    skip_nested=skip_nested,
                )
            )
        else:
            values.append(scalar(context, source))
    return _summarize(name, values, ignore_errors=ignore_errors, k=k)


__all__ = ["roman_numeral"]
