"""Excel's modern and legacy statistical functions and probability distributions."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np

from duddysheet.core.errors import (
    DIV_ZERO_ERROR,
    NA_ERROR,
    NUM_ERROR,
    VALUE_ERROR,
    is_error,
)
from duddysheet.core.functions import lift_all, lift_positions, register
from duddysheet.core.functions import special
from duddysheet.core.functions.common import (
    a_values,
    flatten,
    number,
    numeric_values,
    scalar,
    truthy,
)

STAT = "Statistical"
COMPAT = "Compatibility"


# ------------------------------------------------------------------ helpers
def _num(context: Any, value: Any) -> Any:
    return number(scalar(context, value))


def _nums(context: Any, *values: Any) -> Any:
    """Coerce several scalar arguments to numbers; return the first error."""
    converted = [_num(context, value) for value in values]
    for item in converted:
        if is_error(item):
            return item
    return converted


def _flag(context: Any, value: Any) -> Any:
    selected = scalar(context, value)
    if is_error(selected):
        return selected
    if isinstance(selected, str):
        logical = truthy(selected)
        return logical if is_error(logical) else logical
    converted = number(selected)
    return converted if is_error(converted) else bool(converted)


def _safe(function: Any, *arguments: Any) -> Any:
    """Run a numeric computation, mapping math failures to #NUM!."""
    try:
        result = function(*arguments)
    except (ValueError, OverflowError, ZeroDivisionError):
        return NUM_ERROR
    if isinstance(result, float) and not math.isfinite(result):
        return NUM_ERROR
    return result


def mean(values: list[float]) -> float:
    """Arithmetic mean."""
    return math.fsum(values) / len(values)


def variance(values: list[float], *, sample: bool) -> float:
    """Population or sample variance."""
    centre = mean(values)
    total = math.fsum((value - centre) ** 2 for value in values)
    return total / (len(values) - 1 if sample else len(values))


def percentile_inclusive(values: list[float], fraction: float) -> Any:
    """PERCENTILE.INC on a list of numbers."""
    if not values or not 0 <= fraction <= 1:
        return NUM_ERROR
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def percentile_exclusive(values: list[float], fraction: float) -> Any:
    """PERCENTILE.EXC on a list of numbers."""
    count = len(values)
    if not values or not 0 < fraction < 1:
        return NUM_ERROR
    position = fraction * (count + 1)
    if position < 1 or position > count:
        return NUM_ERROR
    ordered = sorted(values)
    lower = math.floor(position)
    if lower >= count:
        return ordered[-1]
    return ordered[lower - 1] + (position - lower) * (ordered[lower] - ordered[lower - 1])


def mode_single(values: list[float]) -> Any:
    """MODE.SNGL: the first value whose count is highest, if any repeats."""
    counts = Counter(values)
    if not counts:
        return NA_ERROR
    highest = max(counts.values())
    if highest == 1:
        return NA_ERROR
    return next(value for value in values if counts[value] == highest)


def _sample_values(context: Any, *arguments: Any) -> Any:
    values = numeric_values(context, *arguments)
    return values


def _stdev_family(values: Any, *, sample: bool, root: bool) -> Any:
    if is_error(values):
        return values
    if len(values) < (2 if sample else 1):
        return DIV_ZERO_ERROR
    result = variance(values, sample=sample)
    return math.sqrt(result) if root else result


def _pairs(context: Any, first: Any, second: Any) -> Any:
    """Aligned numeric pairs; mismatched sizes are #N/A, errors propagate."""
    left = flatten(context, first)
    right = flatten(context, second)
    if len(left) != len(right):
        return NA_ERROR
    xs: list[float] = []
    ys: list[float] = []
    for a, b in zip(left, right):
        if is_error(a):
            return a
        if is_error(b):
            return b
        if _is_number(a) and _is_number(b):
            xs.append(float(number(a)))
            ys.append(float(number(b)))
    return xs, ys


def _is_number(value: Any) -> bool:
    from datetime import date, datetime

    return (
        isinstance(value, (int, float, date, datetime)) and not isinstance(value, bool)
    )


def _as_column(values: list[Any]) -> tuple[tuple[Any, ...], ...]:
    return tuple((value,) for value in values)


# ------------------------------------------------------ descriptive statistics
def _register_dispersion(name: str, *, sample: bool, root: bool, a: bool, category: str) -> None:
    description = (
        ("Sample" if sample else "Population")
        + (" standard deviation" if root else " variance")
        + (", counting text as 0 and logicals as 1 or 0." if a else " of numeric values.")
    )

    def implementation(context: Any, *arguments: Any) -> Any:
        values = a_values(context, *arguments) if a else numeric_values(context, *arguments)
        return _stdev_family(values, sample=sample, root=root)

    implementation.__doc__ = description
    register(name, min_args=1, argument_spec="number1, [number2], ...", category=category)(
        implementation
    )


for _name, _sample, _root, _a in (
    ("STDEV.S", True, True, False),
    ("STDEV.P", False, True, False),
    ("STDEVA", True, True, True),
    ("STDEVPA", False, True, True),
    ("VAR.S", True, False, False),
    ("VAR.P", False, False, False),
    ("VARA", True, False, True),
    ("VARPA", False, False, True),
):
    _register_dispersion(_name, sample=_sample, root=_root, a=_a, category=STAT)


@register("AVERAGEA", min_args=1, argument_spec="value1, [value2], ...", category=STAT)
def averagea(context: Any, *arguments: Any) -> Any:
    """Average values, counting text as 0 and logicals as 1 or 0."""
    values = a_values(context, *arguments)
    if is_error(values):
        return values
    return DIV_ZERO_ERROR if not values else mean(values)


@register("MAXA", min_args=1, argument_spec="value1, [value2], ...", category=STAT)
def maxa(context: Any, *arguments: Any) -> Any:
    """Return the largest value, counting text as 0 and logicals as 1 or 0."""
    values = a_values(context, *arguments)
    if is_error(values):
        return values
    return 0 if not values else max(values)


@register("MINA", min_args=1, argument_spec="value1, [value2], ...", category=STAT)
def mina(context: Any, *arguments: Any) -> Any:
    """Return the smallest value, counting text as 0 and logicals as 1 or 0."""
    values = a_values(context, *arguments)
    if is_error(values):
        return values
    return 0 if not values else min(values)


@register("GEOMEAN", min_args=1, argument_spec="number1, [number2], ...", category=STAT)
def geomean(context: Any, *arguments: Any) -> Any:
    """Return the geometric mean of positive numbers."""
    values = numeric_values(context, *arguments)
    if is_error(values):
        return values
    if not values or any(value <= 0 for value in values):
        return NUM_ERROR
    return math.exp(math.fsum(math.log(value) for value in values) / len(values))


@register("HARMEAN", min_args=1, argument_spec="number1, [number2], ...", category=STAT)
def harmean(context: Any, *arguments: Any) -> Any:
    """Return the harmonic mean of positive numbers."""
    values = numeric_values(context, *arguments)
    if is_error(values):
        return values
    if not values or any(value <= 0 for value in values):
        return NUM_ERROR
    return len(values) / math.fsum(1 / value for value in values)


@register("TRIMMEAN", min_args=2, max_args=2, argument_spec="array, percent", category=STAT)
def trimmean(context: Any, array: Any, percent: Any) -> Any:
    """Return the mean after excluding a percentage of points from both tails."""
    values = numeric_values(context, array)
    fraction = _num(context, percent)
    if is_error(values):
        return values
    if is_error(fraction):
        return fraction
    if not values or not 0 <= fraction < 1:
        return NUM_ERROR
    excluded = int(len(values) * fraction)
    excluded -= excluded % 2
    trimmed = sorted(values)[excluded // 2 : len(values) - excluded // 2]
    return mean(trimmed)


@register("AVEDEV", min_args=1, argument_spec="number1, [number2], ...", category=STAT)
def avedev(context: Any, *arguments: Any) -> Any:
    """Return the average absolute deviation from the mean."""
    values = numeric_values(context, *arguments)
    if is_error(values):
        return values
    if not values:
        return NUM_ERROR
    centre = mean(values)
    return math.fsum(abs(value - centre) for value in values) / len(values)


@register("DEVSQ", min_args=1, argument_spec="number1, [number2], ...", category=STAT)
def devsq(context: Any, *arguments: Any) -> Any:
    """Return the sum of squared deviations from the mean."""
    values = numeric_values(context, *arguments)
    if is_error(values):
        return values
    if not values:
        return NUM_ERROR
    centre = mean(values)
    return math.fsum((value - centre) ** 2 for value in values)


@register("SKEW", min_args=1, argument_spec="number1, [number2], ...", category=STAT)
def skew(context: Any, *arguments: Any) -> Any:
    """Return the sample skewness of a distribution."""
    values = numeric_values(context, *arguments)
    if is_error(values):
        return values
    count = len(values)
    if count < 3:
        return DIV_ZERO_ERROR
    deviation = math.sqrt(variance(values, sample=True))
    if deviation == 0:
        return DIV_ZERO_ERROR
    centre = mean(values)
    total = math.fsum(((value - centre) / deviation) ** 3 for value in values)
    return count / ((count - 1) * (count - 2)) * total


@register("SKEW.P", min_args=1, argument_spec="number1, [number2], ...", category=STAT)
def skew_p(context: Any, *arguments: Any) -> Any:
    """Return the population skewness of a distribution."""
    values = numeric_values(context, *arguments)
    if is_error(values):
        return values
    if len(values) < 1:
        return DIV_ZERO_ERROR
    deviation = math.sqrt(variance(values, sample=False))
    if deviation == 0:
        return DIV_ZERO_ERROR
    centre = mean(values)
    return math.fsum(((value - centre) / deviation) ** 3 for value in values) / len(values)


@register("KURT", min_args=1, argument_spec="number1, [number2], ...", category=STAT)
def kurt(context: Any, *arguments: Any) -> Any:
    """Return the sample excess kurtosis of a data set."""
    values = numeric_values(context, *arguments)
    if is_error(values):
        return values
    n = len(values)
    if n < 4:
        return DIV_ZERO_ERROR
    deviation = math.sqrt(variance(values, sample=True))
    if deviation == 0:
        return DIV_ZERO_ERROR
    centre = mean(values)
    total = math.fsum(((value - centre) / deviation) ** 4 for value in values)
    return n * (n + 1) / ((n - 1) * (n - 2) * (n - 3)) * total - 3 * (n - 1) ** 2 / (
        (n - 2) * (n - 3)
    )


@register(
    "STANDARDIZE",
    min_args=3,
    max_args=3,
    argument_spec="x, mean, standard_dev",
    lift=lift_all,
    category=STAT,
)
def standardize(context: Any, x: Any, centre: Any, deviation: Any) -> Any:
    """Return a normalized z-score."""
    values = _nums(context, x, centre, deviation)
    if is_error(values):
        return values
    if values[2] <= 0:
        return NUM_ERROR
    return (values[0] - values[1]) / values[2]


@register("MODE.SNGL", min_args=1, argument_spec="number1, [number2], ...", category=STAT)
def mode_sngl(context: Any, *arguments: Any) -> Any:
    """Return the most frequently occurring value."""
    values = numeric_values(context, *arguments)
    return values if is_error(values) else mode_single(values)


@register("MODE.MULT", min_args=1, argument_spec="number1, [number2], ...", category=STAT)
def mode_mult(context: Any, *arguments: Any) -> Any:
    """Return a vertical array of every most-frequent value."""
    values = numeric_values(context, *arguments)
    if is_error(values):
        return values
    counts = Counter(values)
    if not counts or max(counts.values()) == 1:
        return NA_ERROR
    highest = max(counts.values())
    modes = list(dict.fromkeys(value for value in values if counts[value] == highest))
    return _as_column(modes)


def _register_percentile(name: str, exclusive: bool, quartile: bool, category: str) -> None:
    def implementation(context: Any, array: Any, k: Any) -> Any:
        values = numeric_values(context, array)
        selected = _num(context, k)
        if is_error(values):
            return values
        if is_error(selected):
            return selected
        if quartile:
            quart = math.trunc(selected)
            if exclusive and not 1 <= quart <= 3:
                return NUM_ERROR
            if not exclusive and not 0 <= quart <= 4:
                return NUM_ERROR
            selected = quart / 4
        function = percentile_exclusive if exclusive else percentile_inclusive
        return function(values, selected)

    kind = "quartile" if quartile else "k-th percentile"
    scope = "exclusive of 0 and 1" if exclusive else "inclusive of 0 and 1"
    implementation.__doc__ = f"Return the {kind} of values, {scope}."
    register(
        name,
        min_args=2,
        max_args=2,
        argument_spec="array, quart" if quartile else "array, k",
        lift=lift_positions(1),
        category=category,
    )(implementation)


_register_percentile("PERCENTILE.INC", False, False, STAT)
_register_percentile("PERCENTILE.EXC", True, False, STAT)
_register_percentile("QUARTILE.INC", False, True, STAT)
_register_percentile("QUARTILE.EXC", True, True, STAT)


def _percentrank(context: Any, array: Any, x: Any, significance: Any, *, exclusive: bool) -> Any:
    values = numeric_values(context, array)
    target = _num(context, x)
    digits = _num(context, significance)
    if is_error(values):
        return values
    if is_error(target):
        return target
    if is_error(digits):
        return digits
    digits = math.trunc(digits)
    if digits < 1 or not values:
        return NUM_ERROR
    ordered = sorted(values)
    n = len(ordered)
    if target < ordered[0] or target > ordered[-1]:
        return NA_ERROR
    below = sum(value < target for value in ordered)
    if target in ordered:
        rank = float(below)
    else:
        lower = ordered[below - 1]
        upper = ordered[below]
        rank = below - 1 + (target - lower) / (upper - lower)
    if exclusive:
        result = (rank + 1) / (n + 1)
    else:
        if n == 1:
            return 1.0
        result = rank / (n - 1)
    factor = 10**digits
    return math.floor(result * factor + 1e-9) / factor


@register(
    "PERCENTRANK.INC",
    min_args=2,
    max_args=3,
    argument_spec="array, x, [significance]",
    lift=lift_positions(1),
    category=STAT,
)
def percentrank_inc(context: Any, array: Any, x: Any, significance: Any = 3) -> Any:
    """Return the rank of a value as a percentage of the data set, inclusive."""
    return _percentrank(context, array, x, significance, exclusive=False)


@register(
    "PERCENTRANK.EXC",
    min_args=2,
    max_args=3,
    argument_spec="array, x, [significance]",
    lift=lift_positions(1),
    category=STAT,
)
def percentrank_exc(context: Any, array: Any, x: Any, significance: Any = 3) -> Any:
    """Return the rank of a value as a percentage of the data set, exclusive."""
    return _percentrank(context, array, x, significance, exclusive=True)


@register(
    "PERCENTRANK",
    min_args=2,
    max_args=3,
    argument_spec="array, x, [significance]",
    lift=lift_positions(1),
    category=COMPAT,
)
def percentrank(context: Any, array: Any, x: Any, significance: Any = 3) -> Any:
    """Return the percentage rank of a value in a data set."""
    return _percentrank(context, array, x, significance, exclusive=False)


def _rank(context: Any, value: Any, reference: Any, order: Any, *, average: bool) -> Any:
    target = _num(context, value)
    values = numeric_values(context, reference)
    direction = _num(context, order)
    if is_error(target):
        return target
    if is_error(values):
        return values
    if is_error(direction):
        return direction
    if target not in values:
        return NA_ERROR
    if direction == 0:
        better = sum(item > target for item in values)
    else:
        better = sum(item < target for item in values)
    ties = sum(item == target for item in values)
    return better + (1 + ties) / 2 if average else better + 1


@register(
    "RANK.EQ",
    min_args=2,
    max_args=3,
    argument_spec="number, ref, [order]",
    lift=lift_positions(0),
    category=STAT,
)
def rank_eq(context: Any, value: Any, reference: Any, order: Any = 0) -> Any:
    """Return the rank of a number; ties share the top rank."""
    return _rank(context, value, reference, order, average=False)


@register(
    "RANK.AVG",
    min_args=2,
    max_args=3,
    argument_spec="number, ref, [order]",
    lift=lift_positions(0),
    category=STAT,
)
def rank_avg(context: Any, value: Any, reference: Any, order: Any = 0) -> Any:
    """Return the rank of a number; ties share their average rank."""
    return _rank(context, value, reference, order, average=True)


# ---------------------------------------------------------- paired statistics
def _covariance(context: Any, first: Any, second: Any, *, sample: bool) -> Any:
    paired = _pairs(context, first, second)
    if is_error(paired):
        return paired
    xs, ys = paired
    n = len(xs)
    if n < (2 if sample else 1):
        return DIV_ZERO_ERROR
    mx, my = mean(xs), mean(ys)
    total = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return total / (n - 1 if sample else n)


@register("COVARIANCE.P", min_args=2, max_args=2, argument_spec="array1, array2", category=STAT)
def covariance_p(context: Any, first: Any, second: Any) -> Any:
    """Return population covariance."""
    return _covariance(context, first, second, sample=False)


@register("COVARIANCE.S", min_args=2, max_args=2, argument_spec="array1, array2", category=STAT)
def covariance_s(context: Any, first: Any, second: Any) -> Any:
    """Return sample covariance."""
    return _covariance(context, first, second, sample=True)


@register("COVAR", min_args=2, max_args=2, argument_spec="array1, array2", category=COMPAT)
def covar(context: Any, first: Any, second: Any) -> Any:
    """Return population covariance."""
    return _covariance(context, first, second, sample=False)


def _pearson(context: Any, first: Any, second: Any) -> Any:
    paired = _pairs(context, first, second)
    if is_error(paired):
        return paired
    xs, ys = paired
    if len(xs) < 2:
        return DIV_ZERO_ERROR
    mx, my = mean(xs), mean(ys)
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    syy = math.fsum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return DIV_ZERO_ERROR
    return sxy / math.sqrt(sxx * syy)


@register("PEARSON", min_args=2, max_args=2, argument_spec="array1, array2", category=STAT)
def pearson(context: Any, first: Any, second: Any) -> Any:
    """Return the Pearson product-moment correlation coefficient."""
    return _pearson(context, first, second)


@register("RSQ", min_args=2, max_args=2, argument_spec="known_y's, known_x's", category=STAT)
def rsq(context: Any, known_y: Any, known_x: Any) -> Any:
    """Return the square of the Pearson correlation coefficient."""
    result = _pearson(context, known_y, known_x)
    return result if is_error(result) else result * result


@register("STEYX", min_args=2, max_args=2, argument_spec="known_y's, known_x's", category=STAT)
def steyx(context: Any, known_y: Any, known_x: Any) -> Any:
    """Return the standard error of the predicted y for each x in a regression."""
    paired = _pairs(context, known_y, known_x)
    if is_error(paired):
        return paired
    ys, xs = paired
    n = len(xs)
    if n < 3:
        return DIV_ZERO_ERROR
    mx, my = mean(xs), mean(ys)
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return DIV_ZERO_ERROR
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = math.fsum((y - my) ** 2 for y in ys)
    return math.sqrt((syy - sxy * sxy / sxx) / (n - 2))


@register(
    "FORECAST.LINEAR",
    min_args=3,
    max_args=3,
    argument_spec="x, known_y's, known_x's",
    lift=lift_positions(0),
    category=STAT,
)
def forecast_linear(context: Any, x: Any, known_y: Any, known_x: Any) -> Any:
    """Predict a future value with linear regression."""
    target = _num(context, x)
    if is_error(target):
        return target
    paired = _pairs(context, known_y, known_x)
    if is_error(paired):
        return paired
    ys, xs = paired
    if len(xs) < 2:
        return DIV_ZERO_ERROR
    mx, my = mean(xs), mean(ys)
    sxx = math.fsum((value - mx) ** 2 for value in xs)
    if sxx == 0:
        return DIV_ZERO_ERROR
    slope = math.fsum((a - mx) * (b - my) for a, b in zip(xs, ys)) / sxx
    return my - slope * mx + slope * target


# -------------------------------------------------------------- regression
def _regression_inputs(
    context: Any,
    known_y: Any,
    known_x: Any,
) -> Any:
    y_rows = context.matrix(known_y)
    y_values = [item for row in y_rows for item in row]
    for item in y_values:
        if is_error(item):
            return item
        if not _is_number(item):
            return VALUE_ERROR
    y = np.array([float(number(item)) for item in y_values])
    if known_x is None:
        x = np.arange(1, len(y) + 1, dtype=float).reshape(-1, 1)
        return y, x, (len(y_rows), len(y_rows[0]))
    x_rows = context.matrix(known_x)
    for row in x_rows:
        for item in row:
            if is_error(item):
                return item
            if not _is_number(item):
                return VALUE_ERROR
    x_array = np.array([[float(number(item)) for item in row] for row in x_rows])
    y_shape = (len(y_rows), len(y_rows[0]))
    if y_shape[1] == 1:
        if x_array.shape[0] != len(y):
            return NA_ERROR if x_array.size != len(y) else VALUE_ERROR
        x = x_array
    elif y_shape[0] == 1:
        if x_array.shape[1] != len(y):
            return VALUE_ERROR
        x = x_array.T
    else:
        if x_array.shape != y_shape:
            return VALUE_ERROR
        x = x_array.reshape(-1, 1)
    return y, x, y_shape


def _fit(y: np.ndarray, x: np.ndarray, constant: bool) -> dict[str, Any]:
    n, variables = x.shape
    design = np.column_stack([x, np.ones(n)]) if constant else x
    coefficients, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ coefficients
    residual = y - fitted
    ss_resid = float(residual @ residual)
    if constant:
        ss_total = float(((y - y.mean()) ** 2).sum())
    else:
        ss_total = float((y**2).sum())
    ss_reg = ss_total - ss_resid
    df = n - rank
    return {
        "coefficients": coefficients,
        "design": design,
        "ss_resid": ss_resid,
        "ss_reg": ss_reg,
        "ss_total": ss_total,
        "df": df,
        "rank": rank,
        "variables": variables,
    }


def _linest_output(fit: dict[str, Any], constant: bool, stats: bool) -> Any:
    coefficients = fit["coefficients"]
    variables = fit["variables"]
    slopes = list(coefficients[:variables])[::-1]
    intercept = float(coefficients[variables]) if constant else 0.0
    first_row = [float(value) for value in slopes] + [intercept]
    if not stats:
        return (tuple(first_row),)
    df = fit["df"]
    ss_resid = fit["ss_resid"]
    ss_reg = fit["ss_reg"]
    ss_total = fit["ss_total"]
    width = len(first_row)
    if df > 0:
        sigma_squared = ss_resid / df
        try:
            covariance = sigma_squared * np.linalg.pinv(fit["design"].T @ fit["design"])
            errors = np.sqrt(np.clip(np.diag(covariance), 0, None))
        except np.linalg.LinAlgError:
            errors = np.zeros(width)
        slope_errors = [float(value) for value in errors[:variables]][::-1]
        intercept_error: Any = float(errors[variables]) if constant else NA_ERROR
        sey = math.sqrt(sigma_squared)
    else:
        slope_errors = [0.0] * variables
        intercept_error = 0.0 if constant else NA_ERROR
        sey = 0.0
    r_squared = ss_reg / ss_total if ss_total else 1.0
    regressors = fit["rank"] - (1 if constant else 0)
    f_statistic: Any = (
        (ss_reg / regressors) / (ss_resid / df) if df > 0 and ss_resid and regressors else NUM_ERROR
    )
    filler = [NA_ERROR] * (width - 2)
    return (
        tuple(first_row),
        tuple(slope_errors + [intercept_error]),
        tuple([r_squared, sey] + filler),
        tuple([f_statistic, float(df)] + filler),
        tuple([ss_reg, ss_resid] + filler),
    )


@register(
    "LINEST",
    min_args=1,
    max_args=4,
    argument_spec="known_y's, [known_x's], [const], [stats]",
    category=STAT,
)
def linest(
    context: Any,
    known_y: Any,
    known_x: Any = None,
    constant: Any = True,
    stats: Any = False,
) -> Any:
    """Return least-squares line statistics as an array."""
    inputs = _regression_inputs(context, known_y, known_x)
    if is_error(inputs):
        return inputs
    y, x, _ = inputs
    use_constant = True if constant is None else _flag(context, constant)
    with_stats = False if stats is None else _flag(context, stats)
    if is_error(use_constant) or is_error(with_stats):
        return VALUE_ERROR
    return _linest_output(_fit(y, x, bool(use_constant)), bool(use_constant), bool(with_stats))


@register(
    "LOGEST",
    min_args=1,
    max_args=4,
    argument_spec="known_y's, [known_x's], [const], [stats]",
    category=STAT,
)
def logest(
    context: Any,
    known_y: Any,
    known_x: Any = None,
    constant: Any = True,
    stats: Any = False,
) -> Any:
    """Return exponential-curve statistics as an array."""
    inputs = _regression_inputs(context, known_y, known_x)
    if is_error(inputs):
        return inputs
    y, x, _ = inputs
    if (y <= 0).any():
        return NUM_ERROR
    use_constant = True if constant is None else _flag(context, constant)
    with_stats = False if stats is None else _flag(context, stats)
    if is_error(use_constant) or is_error(with_stats):
        return VALUE_ERROR
    output = _linest_output(_fit(np.log(y), x, bool(use_constant)), bool(use_constant), bool(with_stats))
    first = tuple(math.exp(value) for value in output[0])
    return (first, *output[1:])


@register(
    "GROWTH",
    min_args=1,
    max_args=4,
    argument_spec="known_y's, [known_x's], [new_x's], [const]",
    category=STAT,
)
def growth(
    context: Any,
    known_y: Any,
    known_x: Any = None,
    new_x: Any = None,
    constant: Any = True,
) -> Any:
    """Predict exponential growth from existing data."""
    inputs = _regression_inputs(context, known_y, known_x)
    if is_error(inputs):
        return inputs
    y, x, y_shape = inputs
    if (y <= 0).any():
        return NUM_ERROR
    use_constant = True if constant is None else _flag(context, constant)
    if is_error(use_constant):
        return use_constant
    fit = _fit(np.log(y), x, bool(use_constant))
    coefficients = fit["coefficients"]
    if new_x is None:
        targets_rows = (
            [[float(value) for value in row] for row in x]
            if known_x is not None
            else [[float(index)] for index in range(1, len(y) + 1)]
        )
        shape = y_shape
    else:
        rows = context.matrix(new_x)
        for row in rows:
            for item in row:
                if is_error(item):
                    return item
        if x.shape[1] == 1:
            flat = [float(number(item)) for row in rows for item in row]
            targets_rows = [[value] for value in flat]
            shape = (len(rows), len(rows[0]))
        else:
            targets_rows = [[float(number(item)) for item in row] for row in rows]
            shape = (len(rows), 1)
    predictions = []
    for row in targets_rows:
        total = float(coefficients[-1]) if use_constant else 0.0
        total += sum(coefficients[i] * row[i] for i in range(len(row)))
        predictions.append(math.exp(total))
    height, width = shape
    if height * width != len(predictions):
        return _as_column(predictions)
    return tuple(
        tuple(predictions[r * width + c] for c in range(width)) for r in range(height)
    )


@register(
    "FREQUENCY",
    min_args=2,
    max_args=2,
    argument_spec="data_array, bins_array",
    category=STAT,
)
def frequency(context: Any, data: Any, bins: Any) -> Any:
    """Count how often values fall within each bin; the last count is above all bins."""
    values = numeric_values(context, data)
    edges = numeric_values(context, bins)
    if is_error(values):
        return values
    if is_error(edges):
        return edges
    order = sorted(range(len(edges)), key=lambda index: edges[index])
    counts = [0] * (len(edges) + 1)
    for value in values:
        placed = False
        for index in order:
            if value <= edges[index]:
                counts[index] += 1
                placed = True
                break
        if not placed:
            counts[-1] += 1
    return _as_column(counts)


@register(
    "PROB",
    min_args=3,
    max_args=4,
    argument_spec="x_range, prob_range, lower_limit, [upper_limit]",
    category=STAT,
)
def prob(context: Any, x_range: Any, probabilities: Any, lower: Any, upper: Any = None) -> Any:
    """Return the probability that values fall between two limits."""
    xs = flatten(context, x_range)
    ps = flatten(context, probabilities)
    if len(xs) != len(ps):
        return NA_ERROR
    low = _num(context, lower)
    high = low if upper is None else _num(context, upper)
    if is_error(low):
        return low
    if is_error(high):
        return high
    total = 0.0
    selected = 0.0
    for x, p in zip(xs, ps):
        if is_error(x):
            return x
        if is_error(p):
            return p
        if not _is_number(p):
            continue
        probability = float(number(p))
        if probability < 0 or probability > 1:
            return NUM_ERROR
        total += probability
        if _is_number(x) and low <= float(number(x)) <= high:
            selected += probability
    if abs(total - 1) > 1e-9:
        return NUM_ERROR
    return selected


# ------------------------------------------------------------- special math
@register("GAMMA", min_args=1, max_args=1, argument_spec="x", lift=lift_all, category=STAT)
def gamma_function(context: Any, x: Any) -> Any:
    """Return the gamma function value."""
    value = _num(context, x)
    if is_error(value):
        return value
    if value <= 0 and float(value).is_integer():
        return NUM_ERROR
    return _safe(math.gamma, value)


@register("GAMMALN", min_args=1, max_args=1, argument_spec="x", lift=lift_all, category=STAT)
def gammaln(context: Any, x: Any) -> Any:
    """Return the natural logarithm of the gamma function."""
    value = _num(context, x)
    if is_error(value):
        return value
    return NUM_ERROR if value <= 0 else math.lgamma(value)


@register(
    "GAMMALN.PRECISE",
    min_args=1,
    max_args=1,
    argument_spec="x",
    lift=lift_all,
    category=STAT,
)
def gammaln_precise(context: Any, x: Any) -> Any:
    """Return the natural logarithm of the gamma function."""
    value = _num(context, x)
    if is_error(value):
        return value
    return NUM_ERROR if value <= 0 else math.lgamma(value)


@register("FISHER", min_args=1, max_args=1, argument_spec="x", lift=lift_all, category=STAT)
def fisher(context: Any, x: Any) -> Any:
    """Return the Fisher transformation."""
    value = _num(context, x)
    if is_error(value):
        return value
    if not -1 < value < 1:
        return NUM_ERROR
    return 0.5 * math.log((1 + value) / (1 - value))


@register("FISHERINV", min_args=1, max_args=1, argument_spec="y", lift=lift_all, category=STAT)
def fisherinv(context: Any, y: Any) -> Any:
    """Return the inverse of the Fisher transformation."""
    value = _num(context, y)
    if is_error(value):
        return value
    return math.tanh(value)


@register("PHI", min_args=1, max_args=1, argument_spec="x", lift=lift_all, category=STAT)
def phi(context: Any, x: Any) -> Any:
    """Return the standard normal density."""
    value = _num(context, x)
    return value if is_error(value) else special.normal_pdf(value)


@register("GAUSS", min_args=1, max_args=1, argument_spec="z", lift=lift_all, category=STAT)
def gauss(context: Any, z: Any) -> Any:
    """Return the probability a standard normal value lies between the mean and z."""
    value = _num(context, z)
    return value if is_error(value) else special.normal_cdf(value) - 0.5


@register(
    "PERMUT",
    min_args=2,
    max_args=2,
    argument_spec="number, number_chosen",
    lift=lift_all,
    category=STAT,
)
def permut(context: Any, total: Any, chosen: Any) -> Any:
    """Return the number of ordered selections."""
    values = _nums(context, total, chosen)
    if is_error(values):
        return values
    n, k = math.trunc(values[0]), math.trunc(values[1])
    if n < 0 or k < 0 or n < k:
        return NUM_ERROR
    return math.perm(n, k)


@register(
    "PERMUTATIONA",
    min_args=2,
    max_args=2,
    argument_spec="number, number_chosen",
    lift=lift_all,
    category=STAT,
)
def permutationa(context: Any, total: Any, chosen: Any) -> Any:
    """Return the number of ordered selections with repetition."""
    values = _nums(context, total, chosen)
    if is_error(values):
        return values
    n, k = math.trunc(values[0]), math.trunc(values[1])
    if n < 0 or k < 0:
        return NUM_ERROR
    return n**k


# ----------------------------------------------------------- distributions
def _distribution(
    name: str,
    arguments: str,
    description: str,
    compute: Any,
    *,
    count: int,
    optional: int = 0,
    category: str = STAT,
    flags: tuple[int, ...] = (),
) -> None:
    """Register a scalar distribution function from a compute callback.

    Optional trailing arguments reach ``compute`` as ``None`` when omitted;
    ``flags`` marks logical (TRUE/FALSE) argument positions.
    """

    def implementation(context: Any, *values: Any) -> Any:
        converted: list[Any] = []
        for index, value in enumerate(values):
            if value is None and index >= count:
                converted.append(None)
                continue
            item = _flag(context, value) if index in flags else _num(context, value)
            if is_error(item):
                return item
            converted.append(item)
        converted.extend([None] * (count + optional - len(converted)))
        return _safe(compute, *converted)

    implementation.__doc__ = description
    register(
        name,
        min_args=count,
        max_args=count + optional,
        argument_spec=arguments,
        lift=lift_all,
        category=category,
    )(implementation)


def _normal_dist(x: float, mu: float, sigma: float, cumulative: bool) -> Any:
    if sigma <= 0:
        return NUM_ERROR
    z = (x - mu) / sigma
    return special.normal_cdf(z) if cumulative else special.normal_pdf(z) / sigma


def _normal_inv(p: float, mu: float, sigma: float) -> Any:
    if not 0 < p < 1 or sigma <= 0:
        return NUM_ERROR
    return mu + sigma * special.normal_inverse(p)


def _normal_s_inv(p: float) -> Any:
    if not 0 < p < 1:
        return NUM_ERROR
    return special.normal_inverse(p)


_distribution("NORM.DIST", "x, mean, standard_dev, cumulative", "Return the normal distribution.", _normal_dist, count=4, flags=(3,))
_distribution("NORMDIST", "x, mean, standard_dev, cumulative", "Return the normal distribution.", _normal_dist, count=4, flags=(3,), category=COMPAT)
_distribution("NORM.INV", "probability, mean, standard_dev", "Return the inverse of the normal cumulative distribution.", _normal_inv, count=3)
_distribution("NORMINV", "probability, mean, standard_dev", "Return the inverse of the normal cumulative distribution.", _normal_inv, count=3, category=COMPAT)
_distribution(
    "NORM.S.DIST",
    "z, cumulative",
    "Return the standard normal distribution.",
    lambda z, cumulative: special.normal_cdf(z) if cumulative else special.normal_pdf(z),
    count=2,
    flags=(1,),
)
_distribution("NORMSDIST", "z", "Return the standard normal cumulative distribution.", special.normal_cdf, count=1, category=COMPAT)
_distribution("NORM.S.INV", "probability", "Return the inverse of the standard normal cumulative distribution.", _normal_s_inv, count=1)
_distribution("NORMSINV", "probability", "Return the inverse of the standard normal cumulative distribution.", _normal_s_inv, count=1, category=COMPAT)


def _lognorm_dist(x: float, mu: float, sigma: float, cumulative: bool) -> Any:
    if x <= 0 or sigma <= 0:
        return NUM_ERROR
    z = (math.log(x) - mu) / sigma
    return special.normal_cdf(z) if cumulative else special.normal_pdf(z) / (x * sigma)


def _lognorm_inv(p: float, mu: float, sigma: float) -> Any:
    if not 0 < p < 1 or sigma <= 0:
        return NUM_ERROR
    return math.exp(mu + sigma * special.normal_inverse(p))


_distribution("LOGNORM.DIST", "x, mean, standard_dev, cumulative", "Return the lognormal distribution.", _lognorm_dist, count=4, flags=(3,))
_distribution(
    "LOGNORMDIST",
    "x, mean, standard_dev",
    "Return the cumulative lognormal distribution.",
    lambda x, mu, sigma: _lognorm_dist(x, mu, sigma, True),
    count=3,
    category=COMPAT,
)
_distribution("LOGNORM.INV", "probability, mean, standard_dev", "Return the inverse of the lognormal cumulative distribution.", _lognorm_inv, count=3)
_distribution("LOGINV", "probability, mean, standard_dev", "Return the inverse of the lognormal cumulative distribution.", _lognorm_inv, count=3, category=COMPAT)


def _expon(x: float, rate: float, cumulative: bool) -> Any:
    if x < 0 or rate <= 0:
        return NUM_ERROR
    return 1 - math.exp(-rate * x) if cumulative else rate * math.exp(-rate * x)


_distribution("EXPON.DIST", "x, lambda, cumulative", "Return the exponential distribution.", _expon, count=3, flags=(2,))
_distribution("EXPONDIST", "x, lambda, cumulative", "Return the exponential distribution.", _expon, count=3, flags=(2,), category=COMPAT)


def _poisson(x: float, mean_value: float, cumulative: bool) -> Any:
    k = math.trunc(x)
    if k < 0 or mean_value < 0:
        return NUM_ERROR
    return special.poisson_cdf(k, mean_value) if cumulative else special.poisson_pmf(k, mean_value)


_distribution("POISSON.DIST", "x, mean, cumulative", "Return the Poisson distribution.", _poisson, count=3, flags=(2,))
_distribution("POISSON", "x, mean, cumulative", "Return the Poisson distribution.", _poisson, count=3, flags=(2,), category=COMPAT)


def _binom(successes: float, trials: float, p: float, cumulative: bool) -> Any:
    k, n = math.trunc(successes), math.trunc(trials)
    if k < 0 or n < 0 or k > n or not 0 <= p <= 1:
        return NUM_ERROR
    return special.binomial_cdf(k, n, p) if cumulative else special.binomial_pmf(k, n, p)


_distribution("BINOM.DIST", "number_s, trials, probability_s, cumulative", "Return the binomial distribution probability.", _binom, count=4, flags=(3,))
_distribution("BINOMDIST", "number_s, trials, probability_s, cumulative", "Return the binomial distribution probability.", _binom, count=4, flags=(3,), category=COMPAT)


def _binom_range(trials: float, p: float, first: float, last: float | None = None) -> Any:
    n = math.trunc(trials)
    low = math.trunc(first)
    high = low if last is None else math.trunc(last)
    if n < 0 or not 0 <= p <= 1 or low < 0 or low > n or high < low or high > n:
        return NUM_ERROR
    return math.fsum(special.binomial_pmf(k, n, p) for k in range(low, high + 1))


_distribution(
    "BINOM.DIST.RANGE",
    "trials, probability_s, number_s, [number_s2]",
    "Return the probability of a trial result between two counts.",
    _binom_range,
    count=3,
    optional=1,
)


def _binom_inv(trials: float, p: float, alpha: float) -> Any:
    n = math.trunc(trials)
    if n < 0 or not 0 <= p <= 1 or not 0 < alpha < 1:
        return NUM_ERROR
    total = 0.0
    for k in range(n + 1):
        total += special.binomial_pmf(k, n, p)
        if total >= alpha - 1e-12:
            return k
    return n


_distribution("BINOM.INV", "trials, probability_s, alpha", "Return the smallest count whose cumulative binomial probability reaches alpha.", _binom_inv, count=3)
_distribution("CRITBINOM", "trials, probability_s, alpha", "Return the smallest count whose cumulative binomial probability reaches alpha.", _binom_inv, count=3, category=COMPAT)


def _negbinom_pmf(failures: int, successes: int, p: float) -> float:
    return math.comb(failures + successes - 1, successes - 1) * p**successes * (1 - p) ** failures


def _negbinom(failures: float, successes: float, p: float, cumulative: bool) -> Any:
    f, s = math.trunc(failures), math.trunc(successes)
    if f < 0 or s < 1 or not 0 < p < 1:
        return NUM_ERROR
    if cumulative:
        return special.regularized_beta(p, s, f + 1)
    return _negbinom_pmf(f, s, p)


_distribution("NEGBINOM.DIST", "number_f, number_s, probability_s, cumulative", "Return the negative binomial distribution.", _negbinom, count=4, flags=(3,))
_distribution(
    "NEGBINOMDIST",
    "number_f, number_s, probability_s",
    "Return the negative binomial probability.",
    lambda f, s, p: _negbinom(f, s, p, False),
    count=3,
    category=COMPAT,
)


def _hypgeom_pmf(k: int, n: int, big_k: int, big_n: int) -> float:
    return math.comb(big_k, k) * math.comb(big_n - big_k, n - k) / math.comb(big_n, n)


def _hypgeom(sample_s: float, sample: float, population_s: float, population: float, cumulative: bool) -> Any:
    k, n, big_k, big_n = (math.trunc(value) for value in (sample_s, sample, population_s, population))
    if (
        k < 0
        or n <= 0
        or big_k <= 0
        or big_n <= 0
        or k > n
        or k > big_k
        or n > big_n
        or big_k > big_n
        or n - k > big_n - big_k
    ):
        return NUM_ERROR
    if cumulative:
        low = max(0, n - (big_n - big_k))
        return math.fsum(_hypgeom_pmf(i, n, big_k, big_n) for i in range(low, k + 1))
    return _hypgeom_pmf(k, n, big_k, big_n)


_distribution(
    "HYPGEOM.DIST",
    "sample_s, number_sample, population_s, number_pop, cumulative",
    "Return the hypergeometric distribution.",
    _hypgeom,
    count=5,
    flags=(4,),
)
_distribution(
    "HYPGEOMDIST",
    "sample_s, number_sample, population_s, number_pop",
    "Return the hypergeometric probability.",
    lambda k, n, big_k, big_n: _hypgeom(k, n, big_k, big_n, False),
    count=4,
    category=COMPAT,
)


def _weibull(x: float, alpha: float, beta: float, cumulative: bool) -> Any:
    if x < 0 or alpha <= 0 or beta <= 0:
        return NUM_ERROR
    ratio = (x / beta) ** alpha
    if cumulative:
        return 1 - math.exp(-ratio)
    return alpha / beta**alpha * x ** (alpha - 1) * math.exp(-ratio)


_distribution("WEIBULL.DIST", "x, alpha, beta, cumulative", "Return the Weibull distribution.", _weibull, count=4, flags=(3,))
_distribution("WEIBULL", "x, alpha, beta, cumulative", "Return the Weibull distribution.", _weibull, count=4, flags=(3,), category=COMPAT)


def _gamma_dist(x: float, alpha: float, beta: float, cumulative: bool) -> Any:
    if x < 0 or alpha <= 0 or beta <= 0:
        return NUM_ERROR
    return special.gamma_cdf(x, alpha, beta) if cumulative else special.gamma_pdf(x, alpha, beta)


def _gamma_inv(p: float, alpha: float, beta: float) -> Any:
    if not 0 <= p < 1 or alpha <= 0 or beta <= 0:
        return NUM_ERROR
    if p == 0:
        return 0.0
    return special.gamma_inverse(p, alpha, beta)


_distribution("GAMMA.DIST", "x, alpha, beta, cumulative", "Return the gamma distribution.", _gamma_dist, count=4, flags=(3,))
_distribution("GAMMADIST", "x, alpha, beta, cumulative", "Return the gamma distribution.", _gamma_dist, count=4, flags=(3,), category=COMPAT)
_distribution("GAMMA.INV", "probability, alpha, beta", "Return the inverse of the gamma cumulative distribution.", _gamma_inv, count=3)
_distribution("GAMMAINV", "probability, alpha, beta", "Return the inverse of the gamma cumulative distribution.", _gamma_inv, count=3, category=COMPAT)


def _beta_dist(
    x: float,
    alpha: float,
    beta: float,
    cumulative: bool,
    low: float | None = None,
    high: float | None = None,
) -> Any:
    low = 0.0 if low is None else low
    high = 1.0 if high is None else high
    if alpha <= 0 or beta <= 0 or low >= high or x < low or x > high:
        return NUM_ERROR
    scaled = (x - low) / (high - low)
    if cumulative:
        return special.regularized_beta(scaled, alpha, beta)
    return special.beta_pdf(scaled, alpha, beta) / (high - low)


def _beta_inv(p: float, alpha: float, beta: float, low: float | None = None, high: float | None = None) -> Any:
    low = 0.0 if low is None else low
    high = 1.0 if high is None else high
    if not 0 < p < 1 or alpha <= 0 or beta <= 0 or low >= high:
        return NUM_ERROR
    scaled = special.invert(lambda x: special.regularized_beta(x, alpha, beta), p, 0.0, 1.0)
    return low + scaled * (high - low)


_distribution(
    "BETA.DIST",
    "x, alpha, beta, cumulative, [A], [B]",
    "Return the beta distribution.",
    _beta_dist,
    count=4,
    optional=2,
    flags=(3,),
)
_distribution(
    "BETADIST",
    "x, alpha, beta, [A], [B]",
    "Return the cumulative beta distribution.",
    lambda x, a, b, low=None, high=None: _beta_dist(x, a, b, True, low, high),
    count=3,
    optional=2,
    category=COMPAT,
)
_distribution(
    "BETA.INV",
    "probability, alpha, beta, [A], [B]",
    "Return the inverse of the cumulative beta distribution.",
    _beta_inv,
    count=3,
    optional=2,
)
_distribution(
    "BETAINV",
    "probability, alpha, beta, [A], [B]",
    "Return the inverse of the cumulative beta distribution.",
    _beta_inv,
    count=3,
    optional=2,
    category=COMPAT,
)


def _degrees(value: float) -> int:
    return math.trunc(value)


def _t_dist(x: float, df: float, cumulative: bool) -> Any:
    degrees = _degrees(df)
    if degrees < 1:
        return NUM_ERROR
    return special.t_cdf(x, degrees) if cumulative else special.t_pdf(x, degrees)


def _t_two_tail(x: float, df: float) -> Any:
    degrees = _degrees(df)
    if x < 0 or degrees < 1:
        return NUM_ERROR
    return 2 * (1 - special.t_cdf(x, degrees))


def _t_right(x: float, df: float) -> Any:
    degrees = _degrees(df)
    if degrees < 1:
        return NUM_ERROR
    return 1 - special.t_cdf(x, degrees)


def _tdist(x: float, df: float, tails: float) -> Any:
    selected = math.trunc(tails)
    if selected not in (1, 2) or x < 0 or _degrees(df) < 1:
        return NUM_ERROR
    one = 1 - special.t_cdf(x, _degrees(df))
    return one * selected


def _t_inv(p: float, df: float) -> Any:
    degrees = _degrees(df)
    if not 0 < p < 1 or degrees < 1:
        return NUM_ERROR
    return special.t_inverse(p, degrees)


def _t_inv_two(p: float, df: float) -> Any:
    degrees = _degrees(df)
    if not 0 < p <= 1 or degrees < 1:
        return NUM_ERROR
    return special.t_inverse(1 - p / 2, degrees)


_distribution("T.DIST", "x, deg_freedom, cumulative", "Return the left-tailed Student's t-distribution.", _t_dist, count=3, flags=(2,))
_distribution("T.DIST.2T", "x, deg_freedom", "Return the two-tailed Student's t-distribution.", _t_two_tail, count=2)
_distribution("T.DIST.RT", "x, deg_freedom", "Return the right-tailed Student's t-distribution.", _t_right, count=2)
_distribution("TDIST", "x, deg_freedom, tails", "Return the Student's t-distribution.", _tdist, count=3, category=COMPAT)
_distribution("T.INV", "probability, deg_freedom", "Return the left-tailed inverse of the Student's t-distribution.", _t_inv, count=2)
_distribution("T.INV.2T", "probability, deg_freedom", "Return the two-tailed inverse of the Student's t-distribution.", _t_inv_two, count=2)
_distribution("TINV", "probability, deg_freedom", "Return the two-tailed inverse of the Student's t-distribution.", _t_inv_two, count=2, category=COMPAT)


def _chisq_dist(x: float, df: float, cumulative: bool) -> Any:
    degrees = _degrees(df)
    if x < 0 or degrees < 1:
        return NUM_ERROR
    if cumulative:
        return special.chi_square_cdf(x, degrees)
    return special.gamma_pdf(x, degrees / 2, 2)


def _chisq_right(x: float, df: float) -> Any:
    degrees = _degrees(df)
    if x < 0 or degrees < 1:
        return NUM_ERROR
    return special.regularized_gamma_q(degrees / 2, x / 2)


def _chisq_inv(p: float, df: float) -> Any:
    degrees = _degrees(df)
    if not 0 <= p < 1 or degrees < 1:
        return NUM_ERROR
    return special.gamma_inverse(p, degrees / 2, 2) if p > 0 else 0.0


def _chisq_inv_right(p: float, df: float) -> Any:
    degrees = _degrees(df)
    if not 0 < p <= 1 or degrees < 1:
        return NUM_ERROR
    return special.gamma_inverse(1 - p, degrees / 2, 2) if p < 1 else 0.0


_distribution("CHISQ.DIST", "x, deg_freedom, cumulative", "Return the left-tailed chi-squared distribution.", _chisq_dist, count=3, flags=(2,))
_distribution("CHISQ.DIST.RT", "x, deg_freedom", "Return the right-tailed chi-squared distribution.", _chisq_right, count=2)
_distribution("CHIDIST", "x, deg_freedom", "Return the right-tailed chi-squared distribution.", _chisq_right, count=2, category=COMPAT)
_distribution("CHISQ.INV", "probability, deg_freedom", "Return the inverse of the left-tailed chi-squared distribution.", _chisq_inv, count=2)
_distribution("CHISQ.INV.RT", "probability, deg_freedom", "Return the inverse of the right-tailed chi-squared distribution.", _chisq_inv_right, count=2)
_distribution("CHIINV", "probability, deg_freedom", "Return the inverse of the right-tailed chi-squared distribution.", _chisq_inv_right, count=2, category=COMPAT)


def _f_dist(x: float, d1: float, d2: float, cumulative: bool) -> Any:
    first, second = _degrees(d1), _degrees(d2)
    if x < 0 or first < 1 or second < 1:
        return NUM_ERROR
    return special.f_cdf(x, first, second) if cumulative else special.f_pdf(x, first, second)


def _f_right(x: float, d1: float, d2: float) -> Any:
    first, second = _degrees(d1), _degrees(d2)
    if x < 0 or first < 1 or second < 1:
        return NUM_ERROR
    return 1 - special.f_cdf(x, first, second)


def _f_inv(p: float, d1: float, d2: float) -> Any:
    first, second = _degrees(d1), _degrees(d2)
    if not 0 <= p < 1 or first < 1 or second < 1:
        return NUM_ERROR
    if p == 0:
        return 0.0
    return special.invert(lambda x: special.f_cdf(x, first, second), p, 0.0, 10.0, expand_high=True)


def _f_inv_right(p: float, d1: float, d2: float) -> Any:
    if not 0 < p <= 1:
        return NUM_ERROR
    return _f_inv(1 - p, d1, d2)


_distribution("F.DIST", "x, deg_freedom1, deg_freedom2, cumulative", "Return the left-tailed F probability distribution.", _f_dist, count=4, flags=(3,))
_distribution("F.DIST.RT", "x, deg_freedom1, deg_freedom2", "Return the right-tailed F probability distribution.", _f_right, count=3)
_distribution("FDIST", "x, deg_freedom1, deg_freedom2", "Return the right-tailed F probability distribution.", _f_right, count=3, category=COMPAT)
_distribution("F.INV", "probability, deg_freedom1, deg_freedom2", "Return the inverse of the left-tailed F distribution.", _f_inv, count=3)
_distribution("F.INV.RT", "probability, deg_freedom1, deg_freedom2", "Return the inverse of the right-tailed F distribution.", _f_inv_right, count=3)
_distribution("FINV", "probability, deg_freedom1, deg_freedom2", "Return the inverse of the right-tailed F distribution.", _f_inv_right, count=3, category=COMPAT)


def _confidence_norm(alpha: float, deviation: float, size: float) -> Any:
    n = math.trunc(size)
    if not 0 < alpha < 1 or deviation <= 0 or n < 1:
        return NUM_ERROR
    return special.normal_inverse(1 - alpha / 2) * deviation / math.sqrt(n)


def _confidence_t(alpha: float, deviation: float, size: float) -> Any:
    n = math.trunc(size)
    if not 0 < alpha < 1 or deviation <= 0 or n < 1:
        return NUM_ERROR
    if n == 1:
        return DIV_ZERO_ERROR
    return special.t_inverse(1 - alpha / 2, n - 1) * deviation / math.sqrt(n)


_distribution("CONFIDENCE.NORM", "alpha, standard_dev, size", "Return the confidence interval for a population mean (normal).", _confidence_norm, count=3)
_distribution("CONFIDENCE", "alpha, standard_dev, size", "Return the confidence interval for a population mean (normal).", _confidence_norm, count=3, category=COMPAT)
_distribution("CONFIDENCE.T", "alpha, standard_dev, size", "Return the confidence interval for a population mean (Student's t).", _confidence_t, count=3)


# ------------------------------------------------------------ hypothesis tests
def _t_test(context: Any, first: Any, second: Any, tails: Any, test_type: Any) -> Any:
    settings = _nums(context, tails, test_type)
    if is_error(settings):
        return settings
    tail_count, kind = math.trunc(settings[0]), math.trunc(settings[1])
    if tail_count not in (1, 2) or kind not in (1, 2, 3):
        return NUM_ERROR
    if kind == 1:
        paired = _pairs(context, first, second)
        if is_error(paired):
            return paired
        xs, ys = paired
        differences = [x - y for x, y in zip(xs, ys)]
        n = len(differences)
        if n < 2:
            return DIV_ZERO_ERROR
        deviation = math.sqrt(variance(differences, sample=True))
        if deviation == 0:
            return DIV_ZERO_ERROR
        statistic = abs(mean(differences)) / (deviation / math.sqrt(n))
        degrees = n - 1
    else:
        xs = numeric_values(context, first)
        ys = numeric_values(context, second)
        if is_error(xs):
            return xs
        if is_error(ys):
            return ys
        n1, n2 = len(xs), len(ys)
        if n1 < 2 or n2 < 2:
            return DIV_ZERO_ERROR
        v1, v2 = variance(xs, sample=True), variance(ys, sample=True)
        difference = abs(mean(xs) - mean(ys))
        if kind == 2:
            pooled = ((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2)
            standard_error = math.sqrt(pooled * (1 / n1 + 1 / n2))
            degrees = n1 + n2 - 2
        else:
            a, b = v1 / n1, v2 / n2
            standard_error = math.sqrt(a + b)
            degrees = (a + b) ** 2 / (a * a / (n1 - 1) + b * b / (n2 - 1))
        if standard_error == 0:
            return DIV_ZERO_ERROR
        statistic = difference / standard_error
    one_tail = 1 - special.t_cdf(statistic, degrees)
    return one_tail * tail_count


@register(
    "T.TEST",
    min_args=4,
    max_args=4,
    argument_spec="array1, array2, tails, type",
    category=STAT,
)
def t_test(context: Any, first: Any, second: Any, tails: Any, test_type: Any) -> Any:
    """Return the probability associated with a Student's t-test."""
    return _t_test(context, first, second, tails, test_type)


@register(
    "TTEST",
    min_args=4,
    max_args=4,
    argument_spec="array1, array2, tails, type",
    category=COMPAT,
)
def ttest(context: Any, first: Any, second: Any, tails: Any, test_type: Any) -> Any:
    """Return the probability associated with a Student's t-test."""
    return _t_test(context, first, second, tails, test_type)


def _chisq_test(context: Any, actual: Any, expected: Any) -> Any:
    actual_rows = context.matrix(actual)
    expected_rows = context.matrix(expected)
    if len(actual_rows) != len(expected_rows) or len(actual_rows[0]) != len(expected_rows[0]):
        return NA_ERROR
    statistic = 0.0
    for actual_row, expected_row in zip(actual_rows, expected_rows):
        for a, e in zip(actual_row, expected_row):
            if is_error(a):
                return a
            if is_error(e):
                return e
            if not _is_number(a) or not _is_number(e):
                continue
            expected_value = float(number(e))
            if expected_value == 0:
                return DIV_ZERO_ERROR
            statistic += (float(number(a)) - expected_value) ** 2 / expected_value
    rows, columns = len(actual_rows), len(actual_rows[0])
    if rows > 1 and columns > 1:
        degrees = (rows - 1) * (columns - 1)
    else:
        degrees = rows * columns - 1
    if degrees < 1:
        return NA_ERROR
    return special.regularized_gamma_q(degrees / 2, statistic / 2)


@register(
    "CHISQ.TEST",
    min_args=2,
    max_args=2,
    argument_spec="actual_range, expected_range",
    category=STAT,
)
def chisq_test(context: Any, actual: Any, expected: Any) -> Any:
    """Return the chi-squared test for independence."""
    return _chisq_test(context, actual, expected)


@register(
    "CHITEST",
    min_args=2,
    max_args=2,
    argument_spec="actual_range, expected_range",
    category=COMPAT,
)
def chitest(context: Any, actual: Any, expected: Any) -> Any:
    """Return the chi-squared test for independence."""
    return _chisq_test(context, actual, expected)


def _f_test(context: Any, first: Any, second: Any) -> Any:
    xs = numeric_values(context, first)
    ys = numeric_values(context, second)
    if is_error(xs):
        return xs
    if is_error(ys):
        return ys
    if len(xs) < 2 or len(ys) < 2:
        return DIV_ZERO_ERROR
    v1, v2 = variance(xs, sample=True), variance(ys, sample=True)
    if v1 == 0 or v2 == 0:
        return DIV_ZERO_ERROR
    statistic = v1 / v2
    cumulative = special.f_cdf(statistic, len(xs) - 1, len(ys) - 1)
    return 2 * min(cumulative, 1 - cumulative)


@register("F.TEST", min_args=2, max_args=2, argument_spec="array1, array2", category=STAT)
def f_test(context: Any, first: Any, second: Any) -> Any:
    """Return the two-tailed probability that two variances do not differ."""
    return _f_test(context, first, second)


@register("FTEST", min_args=2, max_args=2, argument_spec="array1, array2", category=COMPAT)
def ftest(context: Any, first: Any, second: Any) -> Any:
    """Return the two-tailed probability that two variances do not differ."""
    return _f_test(context, first, second)


def _z_test(context: Any, array: Any, x: Any, sigma: Any) -> Any:
    values = numeric_values(context, array)
    target = _num(context, x)
    if is_error(values):
        return values
    if is_error(target):
        return target
    if not values:
        return NA_ERROR
    if sigma is None:
        if len(values) < 2:
            return DIV_ZERO_ERROR
        deviation = math.sqrt(variance(values, sample=True))
    else:
        deviation = _num(context, sigma)
        if is_error(deviation):
            return deviation
    if deviation == 0:
        return DIV_ZERO_ERROR
    z = (mean(values) - target) / (deviation / math.sqrt(len(values)))
    return 1 - special.normal_cdf(z)


@register(
    "Z.TEST",
    min_args=2,
    max_args=3,
    argument_spec="array, x, [sigma]",
    lift=lift_positions(1),
    category=STAT,
)
def z_test(context: Any, array: Any, x: Any, sigma: Any = None) -> Any:
    """Return the one-tailed P-value of a z-test."""
    return _z_test(context, array, x, sigma)


@register(
    "ZTEST",
    min_args=2,
    max_args=3,
    argument_spec="array, x, [sigma]",
    lift=lift_positions(1),
    category=COMPAT,
)
def ztest(context: Any, array: Any, x: Any, sigma: Any = None) -> Any:
    """Return the one-tailed P-value of a z-test."""
    return _z_test(context, array, x, sigma)


def statistic(name: str, values: list[float], k: float | None = None) -> Any:
    """Compute a named statistic for SUBTOTAL and AGGREGATE."""
    if name in ("AVERAGE",):
        return DIV_ZERO_ERROR if not values else mean(values)
    if name == "COUNT":
        return len(values)
    if name == "MAX":
        return max(values) if values else 0
    if name == "MIN":
        return min(values) if values else 0
    if name == "PRODUCT":
        return math.prod(values) if values else 0
    if name == "SUM":
        return math.fsum(values)
    if name in ("STDEV.S", "STDEV.P", "VAR.S", "VAR.P"):
        return _stdev_family(
            values,
            sample=name.endswith(".S"),
            root=name.startswith("STDEV"),
        )
    if name == "MEDIAN":
        if not values:
            return NUM_ERROR
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) / 2
    if name == "MODE.SNGL":
        return mode_single(values)
    if k is None:
        return VALUE_ERROR
    if name in ("LARGE", "SMALL"):
        index = math.ceil(k) if k != int(k) else int(k)
        if index < 1 or index > len(values):
            return NUM_ERROR
        return sorted(values, reverse=name == "LARGE")[index - 1]
    if name == "PERCENTILE.INC":
        return percentile_inclusive(values, k)
    if name == "PERCENTILE.EXC":
        return percentile_exclusive(values, k)
    if name == "QUARTILE.INC":
        quart = math.trunc(k)
        return NUM_ERROR if not 0 <= quart <= 4 else percentile_inclusive(values, quart / 4)
    if name == "QUARTILE.EXC":
        quart = math.trunc(k)
        return NUM_ERROR if not 1 <= quart <= 3 else percentile_exclusive(values, quart / 4)
    return VALUE_ERROR

