"""Formula function metadata and registration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

FunctionImplementation = Callable[..., Any]
#: Decides whether argument ``index`` of ``count`` is a scalar parameter that
#: lifts (broadcasts) element-wise over an array or multi-cell range.
LiftRule = Callable[[int, int], bool]


def lift_all(index: int, count: int) -> bool:
    """Lift every argument: the function is scalar in all parameters."""
    return True


def lift_positions(*positions: int) -> LiftRule:
    """Lift only the listed zero-based argument positions."""
    selected = frozenset(positions)
    return lambda index, count: index in selected


def lift_from(start: int, *, step: int = 1) -> LiftRule:
    """Lift arguments from ``start`` onward, every ``step`` positions."""
    return lambda index, count: index >= start and (index - start) % step == 0


@dataclass(frozen=True, slots=True)
class FunctionSpec:
    """Registered formula function behavior and help metadata."""

    name: str
    implementation: FunctionImplementation
    min_args: int
    max_args: int
    volatile: bool
    argument_spec: str
    description: str
    lazy: bool = False
    lift: LiftRule | None = None
    accepts_errors: bool = False
    category: str = ""


FUNCTION_REGISTRY: dict[str, FunctionSpec] = {}


def register(
    name: str,
    *,
    min_args: int = 0,
    max_args: int = 255,
    volatile: bool = False,
    argument_spec: str = "",
    lazy: bool = False,
    lift: LiftRule | None = None,
    accepts_errors: bool = False,
    category: str = "",
) -> Callable[[FunctionImplementation], FunctionImplementation]:
    """Register a formula function and retain its help metadata.

    ``lift`` marks scalar parameters that broadcast over arrays, and
    ``accepts_errors`` lets error values reach the implementation instead of
    short-circuiting the call.
    """

    def decorator(function: FunctionImplementation) -> FunctionImplementation:
        normalized_name = name.upper()
        description = (function.__doc__ or "").strip()
        if not description:
            raise ValueError(f"Function {normalized_name} requires a docstring")
        if normalized_name in FUNCTION_REGISTRY:
            raise ValueError(f"Function already registered: {normalized_name}")
        if min_args < 0 or max_args < min_args:
            raise ValueError(f"Invalid argument bounds for {normalized_name}")
        FUNCTION_REGISTRY[normalized_name] = FunctionSpec(
            name=normalized_name,
            implementation=function,
            min_args=min_args,
            max_args=max_args,
            volatile=volatile,
            argument_spec=argument_spec,
            description=description,
            lazy=lazy,
            lift=lift,
            accepts_errors=accepts_errors,
            category=category,
        )
        return function

    return decorator


# Import each family after registry construction so decorators populate one
# authoritative function table.
from duddysheet.core.functions import (  # noqa: E402,F401
    datetime_fn,
    datetime_more,
    engineering_fn,
    finance_fn,
    finance_more,
    info_fn,
    info_more,
    array_fn,
    database_fn,
    lambda_fn,
    math_more,
    misc_fn,
    stats_more,
    logical_fn,
    lookup_fn,
    math_fn,
    stats_fn,
    text_fn,
    text_more,
    whatif_fn,
)


def _apply_lift_table() -> None:
    """Attach Excel's array-lifting rules to the scalar parameters of each family."""
    from dataclasses import replace

    scalar_everywhere = (
        # Math and trigonometry
        "ABS ACOS ASIN ATAN ATAN2 CEILING COS DEGREES EXP FLOOR INT LN LOG LOG10 "
        "MOD MROUND POWER RADIANS ROUND ROUNDDOWN ROUNDUP SIGN SIN SQRT TAN TRUNC "
        "RANDBETWEEN "
        # Text
        "CHAR CODE CONCATENATE EXACT FIND LEFT LEN LOWER MID NUMBERVALUE PROPER "
        "REPLACE REPT RIGHT SEARCH SUBSTITUTE TEXT TRIM UPPER VALUE "
        # Date and time
        "DATE DATEDIF DATEVALUE DAY DAYS EDATE EOMONTH HOUR MINUTE MONTH SECOND "
        "TIME TIMEVALUE WEEKDAY WEEKNUM YEAR YEARFRAC "
        # Information and logical
        "ISBLANK ISERR ISERROR ISLOGICAL ISNA ISNUMBER ISTEXT N ERROR.TYPE NOT "
        # Financial (scalar parameters only)
        "ACCRINT COUPDAYBS COUPDAYS COUPDAYSNC COUPNCD COUPNUM COUPPCD CUMIPMT "
        "CUMPRINC DB DDB DISC DOLLARDE DOLLARFR DURATION EFFECT FV INTRATE IPMT "
        "ISPMT MDURATION NOMINAL NPER PDURATION PMT PPMT PRICE PRICEDISC PV RATE "
        "RECEIVED RRI SLN SYD TBILLEQ TBILLPRICE TBILLYIELD VDB YIELD YIELDDISC"
    ).split()
    partial: dict[str, LiftRule] = {
        "VLOOKUP": lift_positions(0, 2),
        "HLOOKUP": lift_positions(0, 2),
        "MATCH": lift_positions(0),
        "XLOOKUP": lift_positions(0),
        "XMATCH": lift_positions(0),
        "LOOKUP": lift_positions(0),
        "INDEX": lift_positions(1, 2),
        "CHOOSE": lift_positions(0),
        "TEXTBEFORE": lift_positions(0),
        "TEXTAFTER": lift_positions(0),
        "NETWORKDAYS": lift_positions(0, 1),
        "WORKDAY": lift_positions(0, 1),
        "COUNTIF": lift_positions(1),
        "SUMIF": lift_positions(1),
        "AVERAGEIF": lift_positions(1),
        "COUNTIFS": lift_from(1, step=2),
        "SUMIFS": lift_from(2, step=2),
        "AVERAGEIFS": lift_from(2, step=2),
        "MAXIFS": lift_from(2, step=2),
        "MINIFS": lift_from(2, step=2),
        "LARGE": lift_positions(1),
        "SMALL": lift_positions(1),
        "PERCENTILE": lift_positions(1),
        "QUARTILE": lift_positions(1),
        "RANK": lift_positions(0),
        "FORECAST": lift_positions(0),
        "FVSCHEDULE": lift_positions(0),
    }
    for name in scalar_everywhere:
        if name in FUNCTION_REGISTRY and FUNCTION_REGISTRY[name].lift is None:
            FUNCTION_REGISTRY[name] = replace(FUNCTION_REGISTRY[name], lift=lift_all)
    for name, rule in partial.items():
        if name in FUNCTION_REGISTRY and FUNCTION_REGISTRY[name].lift is None:
            FUNCTION_REGISTRY[name] = replace(FUNCTION_REGISTRY[name], lift=rule)


_apply_lift_table()
