"""Euro conversion, XML filtering, exponential-smoothing forecasts, and offline stubs."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ElementTree
from typing import Any

from duddysheet.core.errors import (
    BLOCKED_ERROR,
    NA_ERROR,
    NUM_ERROR,
    VALUE_ERROR,
    is_error,
)
from duddysheet.core.functions import lift_all, register
from duddysheet.core.functions import special
from duddysheet.core.functions.common import flatten, number, round_away, scalar, text
from duddysheet.core.values import parse_number_text

# ------------------------------------------------------------- EUROCONVERT
_EURO_RATES = {
    "BEF": (40.3399, 0),
    "LUF": (40.3399, 0),
    "DEM": (1.95583, 2),
    "ESP": (166.386, 0),
    "FRF": (6.55957, 2),
    "IEP": (0.787564, 2),
    "ITL": (1936.27, 0),
    "NLG": (2.20371, 2),
    "ATS": (13.7603, 2),
    "PTE": (200.482, 0),
    "FIM": (5.94573, 2),
    "GRD": (340.75, 0),
    "SIT": (239.64, 2),
    "CYP": (0.585274, 2),
    "MTL": (0.4293, 2),
    "SKK": (30.126, 2),
    "EEK": (15.6466, 2),
    "LVL": (0.702804, 2),
    "LTL": (3.4528, 2),
    "EUR": (1.0, 2),
}


@register(
    "EUROCONVERT",
    min_args=3,
    max_args=5,
    argument_spec="number, source, target, [full_precision], [triangulation_precision]",
    lift=lift_all,
    category="Add-in",
)
def euroconvert(
    context: Any,
    value: Any,
    source: Any,
    target: Any,
    full_precision: Any = False,
    triangulation_precision: Any = None,
) -> Any:
    """Convert between the euro and former euro-member currencies at fixed rates."""
    amount = number(scalar(context, value))
    if is_error(amount):
        return amount
    source_code = text(scalar(context, source)).strip().upper()
    target_code = text(scalar(context, target)).strip().upper()
    if source_code not in _EURO_RATES or target_code not in _EURO_RATES:
        return VALUE_ERROR
    full = bool(scalar(context, full_precision)) if full_precision is not None else False
    source_rate, _ = _EURO_RATES[source_code]
    target_rate, target_digits = _EURO_RATES[target_code]
    euros = amount / source_rate
    if triangulation_precision is not None:
        digits = number(scalar(context, triangulation_precision))
        if is_error(digits) or math.trunc(digits) < 3:
            return VALUE_ERROR
        if source_code != "EUR" and target_code != "EUR":
            euros = round_away(euros, math.trunc(digits))
    result = euros * target_rate
    return result if full else round_away(result, target_digits)


# --------------------------------------------------------------- FILTERXML
def _typed(value: str) -> Any:
    parsed = parse_number_text(value) if value.strip() and not any(
        character in value for character in "/:"
    ) else None
    return parsed if parsed is not None else value


@register(
    "FILTERXML",
    min_args=2,
    max_args=2,
    argument_spec="xml, xpath",
    category="Web",
)
def filterxml(context: Any, xml: Any, xpath: Any) -> Any:
    """Return data from XML text using an XPath expression."""
    source = text(scalar(context, xml))
    path = text(scalar(context, xpath)).strip()
    try:
        root = ElementTree.fromstring(source)
    except ElementTree.ParseError:
        return VALUE_ERROR
    attribute = None
    if "/@" in path:
        path, _, attribute = path.rpartition("/@")
    wrapper = ElementTree.Element("document")
    wrapper.append(root)
    if path.startswith("//"):
        query = ".//" + path[2:]
    elif path.startswith("/"):
        query = "./" + path[1:]
    else:
        query = "./" + path
    try:
        nodes = wrapper.findall(query)
    except (SyntaxError, KeyError):
        return VALUE_ERROR
    values: list[Any] = []
    for node in nodes:
        if attribute is not None:
            if attribute in node.attrib:
                values.append(_typed(node.attrib[attribute]))
        else:
            values.append(_typed("".join(node.itertext())))
    if not values:
        return VALUE_ERROR
    if len(values) == 1:
        return values[0]
    return tuple((value,) for value in values)


# --------------------------------------------------------- FORECAST.ETS
_AGGREGATIONS = {
    1: lambda values: math.fsum(values) / len(values),
    2: len,
    3: len,
    4: max,
    5: lambda values: sorted(values)[len(values) // 2]
    if len(values) % 2
    else (sorted(values)[len(values) // 2 - 1] + sorted(values)[len(values) // 2]) / 2,
    6: min,
    7: math.fsum,
}


def _series(context: Any, values: Any, timeline: Any, completion: Any, aggregation: Any) -> Any:
    ys = flatten(context, values)
    xs = flatten(context, timeline)
    if len(ys) != len(xs):
        return VALUE_ERROR
    fill = 1 if completion is None else math.trunc(number(scalar(context, completion)))
    method = 1 if aggregation is None else math.trunc(number(scalar(context, aggregation)))
    if fill not in (0, 1) or method not in _AGGREGATIONS:
        return NUM_ERROR
    points: dict[float, list[float]] = {}
    for x, y in zip(xs, ys):
        if is_error(x):
            return x
        if is_error(y):
            return y
        if x is None or isinstance(x, (str, bool)):
            return VALUE_ERROR
        key = float(number(x))
        if y is None or isinstance(y, (str, bool)):
            points.setdefault(key, [])
            continue
        points.setdefault(key, []).append(float(number(y)))
    keys = sorted(points)
    if len(keys) < 3:
        return NUM_ERROR
    differences = [b - a for a, b in zip(keys, keys[1:])]
    step = min(difference for difference in differences if difference > 0)
    if any(abs(difference / step - round(difference / step)) > 1e-9 for difference in differences):
        return NUM_ERROR
    count = int(round((keys[-1] - keys[0]) / step)) + 1
    filled: list[float | None] = [None] * count
    for key in keys:
        bucket = points[key]
        if bucket:
            filled[int(round((key - keys[0]) / step))] = float(_AGGREGATIONS[method](bucket))
    for index, value in enumerate(filled):
        if value is not None:
            continue
        if fill == 0:
            filled[index] = 0.0
            continue
        previous = next((i for i in range(index - 1, -1, -1) if filled[i] is not None), None)
        following = next((i for i in range(index + 1, count) if filled[i] is not None), None)
        if previous is None and following is None:
            return NUM_ERROR
        if previous is None:
            filled[index] = filled[following]  # type: ignore[index]
        elif following is None:
            filled[index] = filled[previous]
        else:
            ratio = (index - previous) / (following - previous)
            filled[index] = filled[previous] + ratio * (filled[following] - filled[previous])  # type: ignore[operator]
    return [float(value) for value in filled], keys[0], step  # type: ignore[arg-type]


def detect_seasonality(series: list[float]) -> int:
    """Return the dominant season length by autocorrelation, or 0 when none.

    As in Excel, a pattern must repeat at least three times to be detected.
    """
    n = len(series)
    if n < 6:
        return 0
    # Remove a linear trend before measuring periodicity.
    xs = list(range(n))
    mean_x = (n - 1) / 2
    mean_y = math.fsum(series) / n
    sxx = math.fsum((x - mean_x) ** 2 for x in xs)
    slope = math.fsum((x - mean_x) * (y - mean_y) for x, y in zip(xs, series)) / sxx
    residual = [y - (mean_y + slope * (x - mean_x)) for x, y in zip(xs, series)]
    variance = math.fsum(value * value for value in residual)
    if variance == 0:
        return 0
    best_lag, best_value = 0, 0.0
    for lag in range(2, n // 3 + 1):
        value = math.fsum(residual[i] * residual[i + lag] for i in range(n - lag)) / variance
        if value > best_value + 1e-12:
            best_lag, best_value = lag, value
    return best_lag if best_value > 0.3 else 0


def _holt_winters(series: list[float], season: int, alpha: float, beta: float, gamma: float) -> tuple[float, float, list[float], list[float]]:
    if season > 1 and len(series) >= 2 * season:
        first = math.fsum(series[:season]) / season
        second = math.fsum(series[season : 2 * season]) / season
        level = first
        trend = (second - first) / season
        seasonal = [value - first for value in series[:season]]
    else:
        season = 1
        level = series[0]
        trend = series[1] - series[0]
        seasonal = [0.0]
    errors: list[float] = []
    for index, value in enumerate(series):
        seasonal_index = index % season
        forecast = level + trend + (seasonal[seasonal_index] if season > 1 else 0.0)
        errors.append(value - forecast)
        previous_level = level
        base = value - (seasonal[seasonal_index] if season > 1 else 0.0)
        level = alpha * base + (1 - alpha) * (level + trend)
        trend = beta * (level - previous_level) + (1 - beta) * trend
        if season > 1:
            seasonal[seasonal_index] = gamma * (value - level) + (1 - gamma) * seasonal[seasonal_index]
    return level, trend, seasonal, errors


def _fit(series: list[float], season: int) -> dict[str, Any]:
    best: tuple[float, float, float, float] | None = None
    grid = [i / 10 for i in range(0, 11)]
    gammas = grid if season > 1 else [0.0]
    for alpha in grid:
        for beta in grid:
            for gamma in gammas:
                *_, errors = _holt_winters(series, season, alpha, beta, gamma)
                sse = math.fsum(error * error for error in errors)
                if best is None or sse < best[0]:
                    best = (sse, alpha, beta, gamma)
    assert best is not None
    _, alpha, beta, gamma = best
    step = 0.05
    while step > 1e-4:
        improved = False
        for index in range(3 if season > 1 else 2):
            for direction in (-step, step):
                trial = [alpha, beta, gamma]
                trial[index] = min(1.0, max(0.0, trial[index] + direction))
                *_, errors = _holt_winters(series, season, *trial)
                sse = math.fsum(error * error for error in errors)
                if sse < best[0] - 1e-12:
                    best = (sse, *trial)
                    alpha, beta, gamma = trial
                    improved = True
        if not improved:
            step /= 2
    level, trend, seasonal, errors = _holt_winters(series, season, alpha, beta, gamma)
    return {
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma if season > 1 else 0.0,
        "level": level,
        "trend": trend,
        "seasonal": seasonal,
        "errors": errors,
        "season": season if len(series) >= 2 * season else 1,
    }


def _season_argument(context: Any, seasonality: Any, series: list[float]) -> Any:
    if seasonality is None:
        return detect_seasonality(series)
    selected = number(scalar(context, seasonality))
    if is_error(selected):
        return selected
    selected = math.trunc(selected)
    if selected < 0 or selected > 8760:
        return NUM_ERROR
    if selected == 1:
        return detect_seasonality(series)
    return max(1, selected)


def _forecast_value(model: dict[str, Any], steps: float, length: int) -> float:
    season = model["season"]
    value = model["level"] + steps * model["trend"]
    if season > 1:
        index = (length + max(0, math.ceil(steps)) - 1) % season
        value += model["seasonal"][index]
    return value


def _prepare(context: Any, values: Any, timeline: Any, seasonality: Any, completion: Any, aggregation: Any) -> Any:
    prepared = _series(context, values, timeline, completion, aggregation)
    if is_error(prepared):
        return prepared
    series, start, step = prepared
    season = _season_argument(context, seasonality, series)
    if is_error(season):
        return season
    return series, start, step, _fit(series, season)


@register(
    "FORECAST.ETS",
    min_args=3,
    max_args=6,
    argument_spec="target_date, values, timeline, [seasonality], [data_completion], [aggregation]",
    category="Statistical",
)
def forecast_ets(
    context: Any,
    target_date: Any,
    values: Any,
    timeline: Any,
    seasonality: Any = None,
    data_completion: Any = None,
    aggregation: Any = None,
) -> Any:
    """Forecast a future value with additive exponential smoothing (AAA)."""
    target = number(scalar(context, target_date))
    if is_error(target):
        return target
    prepared = _prepare(context, values, timeline, seasonality, data_completion, aggregation)
    if is_error(prepared):
        return prepared
    series, start, step, model = prepared
    last = start + (len(series) - 1) * step
    if target < start:
        return NUM_ERROR
    steps = (target - last) / step
    if steps <= 0:
        index = int(round((target - start) / step))
        return series[min(index, len(series) - 1)]
    return _forecast_value(model, steps, len(series))


@register(
    "FORECAST.ETS.CONFINT",
    min_args=3,
    max_args=7,
    argument_spec="target_date, values, timeline, [confidence_level], [seasonality], [data_completion], [aggregation]",
    category="Statistical",
)
def forecast_ets_confint(
    context: Any,
    target_date: Any,
    values: Any,
    timeline: Any,
    confidence_level: Any = 0.95,
    seasonality: Any = None,
    data_completion: Any = None,
    aggregation: Any = None,
) -> Any:
    """Return the half-width of the confidence interval around an ETS forecast."""
    target = number(scalar(context, target_date))
    level = number(scalar(context, 0.95 if confidence_level is None else confidence_level))
    if is_error(target):
        return target
    if is_error(level) or not 0 < level < 1:
        return NUM_ERROR
    prepared = _prepare(context, values, timeline, seasonality, data_completion, aggregation)
    if is_error(prepared):
        return prepared
    series, start, step, model = prepared
    errors = model["errors"]
    rmse = math.sqrt(math.fsum(error * error for error in errors) / len(errors))
    last = start + (len(series) - 1) * step
    steps = max(1.0, (target - last) / step)
    alpha, beta = model["alpha"], model["beta"]
    variance_factor = 1 + sum(
        (alpha * (1 + j * beta)) ** 2 for j in range(1, math.ceil(steps))
    )
    return special.normal_inverse((1 + level) / 2) * rmse * math.sqrt(variance_factor)


@register(
    "FORECAST.ETS.SEASONALITY",
    min_args=2,
    max_args=4,
    argument_spec="values, timeline, [data_completion], [aggregation]",
    category="Statistical",
)
def forecast_ets_seasonality(
    context: Any,
    values: Any,
    timeline: Any,
    data_completion: Any = None,
    aggregation: Any = None,
) -> Any:
    """Return the length of the repetitive pattern detected in a time series."""
    prepared = _series(context, values, timeline, data_completion, aggregation)
    if is_error(prepared):
        return prepared
    return detect_seasonality(prepared[0])


@register(
    "FORECAST.ETS.STAT",
    min_args=3,
    max_args=6,
    argument_spec="values, timeline, statistic_type, [seasonality], [data_completion], [aggregation]",
    category="Statistical",
)
def forecast_ets_stat(
    context: Any,
    values: Any,
    timeline: Any,
    statistic_type: Any,
    seasonality: Any = None,
    data_completion: Any = None,
    aggregation: Any = None,
) -> Any:
    """Return a smoothing parameter or error statistic of an ETS forecast model."""
    kind = number(scalar(context, statistic_type))
    if is_error(kind) or math.trunc(kind) not in range(1, 9):
        return NUM_ERROR
    prepared = _prepare(context, values, timeline, seasonality, data_completion, aggregation)
    if is_error(prepared):
        return prepared
    series, _, step, model = prepared
    errors = model["errors"]
    kind = math.trunc(kind)
    if kind == 1:
        return model["alpha"]
    if kind == 2:
        return model["beta"]
    if kind == 3:
        return model["gamma"]
    if kind == 8:
        return step
    absolute = [abs(error) for error in errors]
    if kind == 6:
        return math.fsum(absolute) / len(absolute)
    if kind == 7:
        return math.sqrt(math.fsum(error * error for error in errors) / len(errors))
    if kind == 5:
        terms = [
            2 * abs(error) / (abs(value) + abs(value - error))
            for error, value in zip(errors, series)
            if abs(value) + abs(value - error) > 0
        ]
        return math.fsum(terms) / len(terms) if terms else 0.0
    naive = [abs(b - a) for a, b in zip(series, series[1:])]
    scale = math.fsum(naive) / len(naive) if naive else 0.0
    return NA_ERROR if scale == 0 else (math.fsum(absolute) / len(absolute)) / scale


# --------------------------------------------- offline-unavailable functions
def _blocked(name: str, arguments: str, description: str, *, maximum: int) -> None:
    def implementation(context: Any, *values: Any) -> Any:
        return BLOCKED_ERROR

    implementation.__doc__ = (
        f"{description} Requires an online or external service, so this offline "
        "application returns #BLOCKED!."
    )
    register(
        name,
        min_args=0,
        max_args=maximum,
        argument_spec=arguments,
        category="Web" if name in ("WEBSERVICE", "IMAGE", "STOCKHISTORY", "TRANSLATE") else "Cube",
    )(implementation)


_blocked("WEBSERVICE", "url", "Return data from a web service.", maximum=1)
_blocked("STOCKHISTORY", "stock, start_date, [end_date], [interval], [headers], [property0], ...", "Return historical stock prices.", maximum=255)
_blocked("IMAGE", "source, [alt_text], [sizing], [height], [width]", "Insert an image from a URL into a cell.", maximum=5)
_blocked("TRANSLATE", "text, [source_language], [target_language]", "Translate text between languages.", maximum=3)
_blocked("RTD", "progID, server, topic1, [topic2], ...", "Return real-time data from a COM automation server.", maximum=255)
_blocked("FIELDVALUE", "value, field_name", "Return a field from a linked data type.", maximum=2)
_blocked("CALL", "register_id, [argument1], ...", "Call a procedure in a dynamic link library.", maximum=255)
_blocked("REGISTER.ID", "module_text, procedure, [type_text]", "Return the register ID of a DLL procedure.", maximum=3)
for _cube in (
    "CUBEKPIMEMBER",
    "CUBEMEMBER",
    "CUBEMEMBERPROPERTY",
    "CUBERANKEDMEMBER",
    "CUBESET",
    "CUBESETCOUNT",
    "CUBEVALUE",
):
    _blocked(_cube, "connection, ...", "Query an OLAP cube connection.", maximum=255)
