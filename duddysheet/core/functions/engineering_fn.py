"""Excel's Engineering functions: bases, bits, units, error functions, complex numbers, Bessel."""

from __future__ import annotations

import cmath
import math
import re
from typing import Any

from duddysheet.core.errors import DIV_ZERO_ERROR, NA_ERROR, NUM_ERROR, VALUE_ERROR, is_error
from duddysheet.core.functions import lift_all, register
from duddysheet.core.functions import special
from duddysheet.core.functions.common import flatten, number, scalar, text
from duddysheet.core.values import number_text

ENG = "Engineering"


def _num(context: Any, value: Any) -> Any:
    return number(scalar(context, value))


# ---------------------------------------------------------- base conversions
_BASES = {"BIN": (2, 10), "OCT": (8, 30), "DEC": (10, 0), "HEX": (16, 40)}
_LIMITS = {
    "BIN": (-512, 511),
    "OCT": (-536_870_912, 536_870_911),
    "HEX": (-549_755_813_888, 549_755_813_887),
}


def _parse_base(source: Any, name: str) -> Any:
    radix, bits = _BASES[name]
    if isinstance(source, bool):
        return VALUE_ERROR
    if isinstance(source, float) and source.is_integer():
        source = int(source)
    digits = text(source).strip().upper()
    if not digits:
        return 0
    if len(digits) > 10:
        return NUM_ERROR
    try:
        value = int(digits, radix)
    except ValueError:
        return NUM_ERROR
    if len(digits) == 10 and value >= 1 << (bits - 1):
        value -= 1 << bits
    return value


def _format_base(value: int, name: str, places: Any) -> Any:
    radix, bits = _BASES[name]
    low, high = _LIMITS[name]
    if not low <= value <= high:
        return NUM_ERROR
    if value < 0:
        value += 1 << bits
        rendered = _render(value, radix)
        return rendered.rjust(10, "F" if radix == 16 else "7" if radix == 8 else "1")
    rendered = _render(value, radix)
    if places is None:
        return rendered
    if is_error(places):
        return places
    width = math.trunc(places)
    if width < 0 or width > 10:
        return NUM_ERROR
    if width < len(rendered):
        return NUM_ERROR
    return rendered.rjust(width, "0")


def _render(value: int, radix: int) -> str:
    if value == 0:
        return "0"
    digits = "0123456789ABCDEF"
    output: list[str] = []
    while value:
        value, digit = divmod(value, radix)
        output.append(digits[digit])
    return "".join(reversed(output))


def _register_conversion(source: str, target: str) -> None:
    def implementation(context: Any, value: Any, places: Any = None) -> Any:
        raw = scalar(context, value)
        if is_error(raw):
            return raw
        if source == "DEC":
            converted = number(raw)
            if is_error(converted):
                return converted
            parsed: Any = math.trunc(converted)
        else:
            parsed = _parse_base(raw, source)
        if is_error(parsed):
            return parsed
        if target == "DEC":
            return parsed
        width = None if places is None else _num(context, places)
        return _format_base(parsed, target, width)

    implementation.__doc__ = (
        f"Convert a {_LABELS[source]} number to {_LABELS[target]}."
    )
    register(
        f"{source}2{target}",
        min_args=1,
        max_args=1 if target == "DEC" else 2,
        argument_spec="number" if target == "DEC" else "number, [places]",
        lift=lift_all,
        category=ENG,
    )(implementation)


_LABELS = {"BIN": "binary", "OCT": "octal", "DEC": "decimal", "HEX": "hexadecimal"}
for _source in _BASES:
    for _target in _BASES:
        if _source != _target:
            _register_conversion(_source, _target)


# --------------------------------------------------------------------- bits
_BIT_LIMIT = 2**48


def _bit_operand(context: Any, value: Any) -> Any:
    converted = _num(context, value)
    if is_error(converted):
        return converted
    if converted < 0 or converted >= _BIT_LIMIT or not float(converted).is_integer():
        return NUM_ERROR
    return int(converted)


def _register_bitwise(name: str, description: str, operation: Any) -> None:
    def implementation(context: Any, first: Any, second: Any) -> Any:
        left = _bit_operand(context, first)
        right = _bit_operand(context, second)
        if is_error(left):
            return left
        if is_error(right):
            return right
        return operation(left, right)

    implementation.__doc__ = description
    register(
        name,
        min_args=2,
        max_args=2,
        argument_spec="number1, number2",
        lift=lift_all,
        category=ENG,
    )(implementation)


_register_bitwise("BITAND", "Return a bitwise AND of two numbers.", lambda a, b: a & b)
_register_bitwise("BITOR", "Return a bitwise OR of two numbers.", lambda a, b: a | b)
_register_bitwise("BITXOR", "Return a bitwise exclusive OR of two numbers.", lambda a, b: a ^ b)


def _shift(context: Any, value: Any, amount: Any, *, left: bool) -> Any:
    operand = _bit_operand(context, value)
    distance = _num(context, amount)
    if is_error(operand):
        return operand
    if is_error(distance):
        return distance
    distance = math.trunc(distance)
    if abs(distance) > 53:
        return NUM_ERROR
    if not left:
        distance = -distance
    result = operand << distance if distance >= 0 else operand >> -distance
    return NUM_ERROR if result >= _BIT_LIMIT else result


@register(
    "BITLSHIFT",
    min_args=2,
    max_args=2,
    argument_spec="number, shift_amount",
    lift=lift_all,
    category=ENG,
)
def bitlshift(context: Any, value: Any, amount: Any) -> Any:
    """Return a number shifted left by a number of bits."""
    return _shift(context, value, amount, left=True)


@register(
    "BITRSHIFT",
    min_args=2,
    max_args=2,
    argument_spec="number, shift_amount",
    lift=lift_all,
    category=ENG,
)
def bitrshift(context: Any, value: Any, amount: Any) -> Any:
    """Return a number shifted right by a number of bits."""
    return _shift(context, value, amount, left=False)


# ---------------------------------------------------- comparison and erf
@register(
    "DELTA",
    min_args=1,
    max_args=2,
    argument_spec="number1, [number2]",
    lift=lift_all,
    category=ENG,
)
def delta(context: Any, first: Any, second: Any = 0) -> Any:
    """Return 1 when two numbers are equal, otherwise 0."""
    left = _num(context, first)
    right = _num(context, second if second is not None else 0)
    if is_error(left):
        return left
    if is_error(right):
        return right
    return int(left == right)


@register(
    "GESTEP",
    min_args=1,
    max_args=2,
    argument_spec="number, [step]",
    lift=lift_all,
    category=ENG,
)
def gestep(context: Any, value: Any, step: Any = 0) -> Any:
    """Return 1 when a number is greater than or equal to a threshold."""
    left = _num(context, value)
    right = _num(context, step if step is not None else 0)
    if is_error(left):
        return left
    if is_error(right):
        return right
    return int(left >= right)


@register(
    "ERF",
    min_args=1,
    max_args=2,
    argument_spec="lower_limit, [upper_limit]",
    lift=lift_all,
    category=ENG,
)
def erf(context: Any, lower: Any, upper: Any = None) -> Any:
    """Return the error function integrated between limits."""
    low = _num(context, lower)
    if is_error(low):
        return low
    if upper is None:
        return math.erf(low)
    high = _num(context, upper)
    if is_error(high):
        return high
    return math.erf(high) - math.erf(low)


@register("ERF.PRECISE", min_args=1, max_args=1, argument_spec="x", lift=lift_all, category=ENG)
def erf_precise(context: Any, x: Any) -> Any:
    """Return the error function."""
    value = _num(context, x)
    return value if is_error(value) else math.erf(value)


@register("ERFC", min_args=1, max_args=1, argument_spec="x", lift=lift_all, category=ENG)
def erfc(context: Any, x: Any) -> Any:
    """Return the complementary error function."""
    value = _num(context, x)
    return value if is_error(value) else math.erfc(value)


@register("ERFC.PRECISE", min_args=1, max_args=1, argument_spec="x", lift=lift_all, category=ENG)
def erfc_precise(context: Any, x: Any) -> Any:
    """Return the complementary error function."""
    value = _num(context, x)
    return value if is_error(value) else math.erfc(value)


# ------------------------------------------------------------------ Bessel
def _register_bessel(name: str, description: str, function: Any, *, positive: bool) -> None:
    def implementation(context: Any, x: Any, n: Any) -> Any:
        value = _num(context, x)
        order = _num(context, n)
        if is_error(value):
            return value
        if is_error(order):
            return order
        order = math.trunc(order)
        if order < 0 or (positive and value <= 0):
            return NUM_ERROR
        try:
            result = function(value, order)
        except (ValueError, OverflowError):
            return NUM_ERROR
        return result if math.isfinite(result) else NUM_ERROR

    implementation.__doc__ = description
    register(
        name,
        min_args=2,
        max_args=2,
        argument_spec="x, n",
        lift=lift_all,
        category=ENG,
    )(implementation)


_register_bessel("BESSELJ", "Return the Bessel function Jn(x).", special.bessel_j, positive=False)
_register_bessel("BESSELI", "Return the modified Bessel function In(x).", special.bessel_i, positive=False)
_register_bessel("BESSELY", "Return the Bessel function Yn(x).", special.bessel_y, positive=True)
_register_bessel("BESSELK", "Return the modified Bessel function Kn(x).", special.bessel_k, positive=True)


# ---------------------------------------------------------- complex numbers
_COMPLEX_RE = re.compile(
    r"^(?P<real>[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)?"
    r"(?:(?P<imag>[+-]?(?:\d+\.?\d*|\.\d+)?(?:[eE][+-]?\d+)?)(?P<suffix>[ij]))?$"
)


def _parse_complex(value: Any) -> Any:
    """Return (complex, suffix) for Excel complex text or a real number."""
    if is_error(value):
        return value
    if isinstance(value, bool):
        return VALUE_ERROR
    if isinstance(value, (int, float)):
        return complex(value, 0), None
    if value is None:
        return complex(0, 0), None
    source = str(value).strip()
    if not source:
        return complex(0, 0), None
    match = _COMPLEX_RE.match(source)
    if not match or (match.group("real") is None and match.group("suffix") is None):
        return NUM_ERROR
    real_text = match.group("real")
    imag_text = match.group("imag")
    suffix = match.group("suffix")
    real = float(real_text) if real_text else 0.0
    if suffix is None:
        return complex(real, 0), None
    if imag_text in (None, "", "+"):
        imaginary = 1.0
    elif imag_text == "-":
        imaginary = -1.0
    else:
        imaginary = float(imag_text)
    if real_text and imag_text in (None, ""):
        # "3i" parses real_text as the coefficient.
        return complex(0, real), suffix
    return complex(real, imaginary), suffix


def format_complex(value: complex, suffix: str = "i") -> str:
    """Render a complex number as Excel complex text (15 significant digits)."""
    real = _clean(value.real)
    imaginary = _clean(value.imag)
    if imaginary == 0:
        return _component_text(real)
    if imaginary == 1:
        imag_text = suffix
    elif imaginary == -1:
        imag_text = "-" + suffix
    else:
        imag_text = _component_text(imaginary) + suffix
    if real == 0:
        return imag_text
    sign = "" if imag_text.startswith("-") else "+"
    return f"{_component_text(real)}{sign}{imag_text}"


def _component_text(component: float) -> str:
    if isinstance(component, int):
        return str(component)
    return format(component, ".15g").replace("e", "E")


def _clean(component: float) -> float:
    if abs(component) < 1e-15:
        return 0.0
    rounded = float(f"{component:.15g}")
    return int(rounded) if rounded.is_integer() and abs(rounded) < 2**53 else rounded


def _complex_argument(context: Any, value: Any) -> Any:
    return _parse_complex(scalar(context, value))


def _suffix(*suffixes: str | None) -> Any:
    selected = {suffix for suffix in suffixes if suffix is not None}
    if len(selected) > 1:
        return VALUE_ERROR
    return selected.pop() if selected else "i"


@register(
    "COMPLEX",
    min_args=2,
    max_args=3,
    argument_spec='real_num, i_num, [suffix]',
    lift=lift_all,
    category=ENG,
)
def complex_function(context: Any, real: Any, imaginary: Any, suffix: Any = "i") -> Any:
    """Convert real and imaginary coefficients into a complex number."""
    real_value = _num(context, real)
    imaginary_value = _num(context, imaginary)
    if is_error(real_value):
        return real_value
    if is_error(imaginary_value):
        return imaginary_value
    selected = text(scalar(context, suffix)) if suffix is not None else "i"
    if selected == "":
        selected = "i"
    if selected not in ("i", "j"):
        return VALUE_ERROR
    return format_complex(complex(real_value, imaginary_value), selected)


def _register_complex_unary(
    name: str,
    description: str,
    function: Any,
    *,
    returns_complex: bool = True,
) -> None:
    def implementation(context: Any, value: Any) -> Any:
        parsed = _complex_argument(context, value)
        if is_error(parsed):
            return parsed
        number_value, suffix = parsed
        try:
            result = function(number_value)
        except (ValueError, OverflowError):
            return NUM_ERROR
        except ZeroDivisionError:
            return NUM_ERROR
        if is_error(result):
            return result
        if not returns_complex:
            return result
        if not (math.isfinite(result.real) and math.isfinite(result.imag)):
            return NUM_ERROR
        return format_complex(result, suffix or "i")

    implementation.__doc__ = description
    register(
        name,
        min_args=1,
        max_args=1,
        argument_spec="inumber",
        lift=lift_all,
        category=ENG,
    )(implementation)


def _nonzero_complex(function: Any) -> Any:
    def wrapped(value: complex) -> Any:
        if value == 0:
            return NUM_ERROR
        return function(value)

    return wrapped


_register_complex_unary("IMABS", "Return the absolute value (modulus) of a complex number.", abs, returns_complex=False)
_register_complex_unary("IMAGINARY", "Return the imaginary coefficient of a complex number.", lambda z: _clean(z.imag), returns_complex=False)
_register_complex_unary("IMREAL", "Return the real coefficient of a complex number.", lambda z: _clean(z.real), returns_complex=False)
_register_complex_unary(
    "IMARGUMENT",
    "Return the argument theta, an angle in radians.",
    lambda z: DIV_ZERO_ERROR if z == 0 else cmath.phase(z),
    returns_complex=False,
)
_register_complex_unary("IMCONJUGATE", "Return the complex conjugate of a complex number.", lambda z: z.conjugate())
_register_complex_unary("IMCOS", "Return the cosine of a complex number.", cmath.cos)
_register_complex_unary("IMCOSH", "Return the hyperbolic cosine of a complex number.", cmath.cosh)
_register_complex_unary("IMSIN", "Return the sine of a complex number.", cmath.sin)
_register_complex_unary("IMSINH", "Return the hyperbolic sine of a complex number.", cmath.sinh)
_register_complex_unary("IMTAN", "Return the tangent of a complex number.", cmath.tan)
_register_complex_unary("IMCOT", "Return the cotangent of a complex number.", _nonzero_complex(lambda z: 1 / cmath.tan(z)))
_register_complex_unary("IMCSC", "Return the cosecant of a complex number.", _nonzero_complex(lambda z: 1 / cmath.sin(z)))
_register_complex_unary("IMCSCH", "Return the hyperbolic cosecant of a complex number.", _nonzero_complex(lambda z: 1 / cmath.sinh(z)))
_register_complex_unary("IMSEC", "Return the secant of a complex number.", lambda z: 1 / cmath.cos(z))
_register_complex_unary("IMSECH", "Return the hyperbolic secant of a complex number.", lambda z: 1 / cmath.cosh(z))
_register_complex_unary("IMEXP", "Return the exponential of a complex number.", cmath.exp)
_register_complex_unary("IMLN", "Return the natural logarithm of a complex number.", _nonzero_complex(cmath.log))
_register_complex_unary("IMLOG10", "Return the base-10 logarithm of a complex number.", _nonzero_complex(cmath.log10))
_register_complex_unary(
    "IMLOG2",
    "Return the base-2 logarithm of a complex number.",
    _nonzero_complex(lambda z: cmath.log(z) / math.log(2)),
)
_register_complex_unary("IMSQRT", "Return the square root of a complex number.", cmath.sqrt)


@register(
    "IMPOWER",
    min_args=2,
    max_args=2,
    argument_spec="inumber, number",
    lift=lift_all,
    category=ENG,
)
def impower(context: Any, value: Any, power: Any) -> Any:
    """Return a complex number raised to a real power."""
    parsed = _complex_argument(context, value)
    exponent = _num(context, power)
    if is_error(parsed):
        return parsed
    if is_error(exponent):
        return exponent
    number_value, suffix = parsed
    if number_value == 0:
        return NUM_ERROR if exponent <= 0 else "0"
    modulus = abs(number_value) ** exponent
    angle = cmath.phase(number_value) * exponent
    return format_complex(cmath.rect(modulus, angle), suffix or "i")


@register(
    "IMDIV",
    min_args=2,
    max_args=2,
    argument_spec="inumber1, inumber2",
    lift=lift_all,
    category=ENG,
)
def imdiv(context: Any, first: Any, second: Any) -> Any:
    """Return the quotient of two complex numbers."""
    left = _complex_argument(context, first)
    right = _complex_argument(context, second)
    if is_error(left):
        return left
    if is_error(right):
        return right
    suffix = _suffix(left[1], right[1])
    if is_error(suffix):
        return suffix
    if right[0] == 0:
        return NUM_ERROR
    return format_complex(left[0] / right[0], suffix)


@register(
    "IMSUB",
    min_args=2,
    max_args=2,
    argument_spec="inumber1, inumber2",
    lift=lift_all,
    category=ENG,
)
def imsub(context: Any, first: Any, second: Any) -> Any:
    """Return the difference of two complex numbers."""
    left = _complex_argument(context, first)
    right = _complex_argument(context, second)
    if is_error(left):
        return left
    if is_error(right):
        return right
    suffix = _suffix(left[1], right[1])
    if is_error(suffix):
        return suffix
    return format_complex(left[0] - right[0], suffix)


def _complex_values(context: Any, arguments: tuple[Any, ...]) -> Any:
    parsed: list[tuple[complex, str | None]] = []
    for argument in arguments:
        for value in flatten(context, argument):
            if value is None:
                continue
            item = _parse_complex(value)
            if is_error(item):
                return item
            parsed.append(item)
    return parsed


@register("IMSUM", min_args=1, argument_spec="inumber1, [inumber2], ...", category=ENG)
def imsum(context: Any, *arguments: Any) -> Any:
    """Return the sum of complex numbers."""
    parsed = _complex_values(context, arguments)
    if is_error(parsed):
        return parsed
    suffix = _suffix(*(item[1] for item in parsed))
    if is_error(suffix):
        return suffix
    return format_complex(sum((item[0] for item in parsed), complex(0, 0)), suffix)


@register("IMPRODUCT", min_args=1, argument_spec="inumber1, [inumber2], ...", category=ENG)
def improduct(context: Any, *arguments: Any) -> Any:
    """Return the product of complex numbers."""
    parsed = _complex_values(context, arguments)
    if is_error(parsed):
        return parsed
    suffix = _suffix(*(item[1] for item in parsed))
    if is_error(suffix):
        return suffix
    result = complex(1, 0)
    for item in parsed:
        result *= item[0]
    return format_complex(result, suffix)


# ------------------------------------------------------------------ CONVERT
_PREFIXES = {
    "Y": 1e24, "Z": 1e21, "E": 1e18, "P": 1e15, "T": 1e12, "G": 1e9, "M": 1e6,
    "k": 1e3, "h": 1e2, "da": 1e1, "e": 1e1, "d": 1e-1, "c": 1e-2, "m": 1e-3,
    "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15, "a": 1e-18, "z": 1e-21, "y": 1e-24,
}
_BINARY_PREFIXES = {
    "Yi": 2.0**80, "Zi": 2.0**70, "Ei": 2.0**60, "Pi": 2.0**50, "Ti": 2.0**40,
    "Gi": 2.0**30, "Mi": 2.0**20, "ki": 2.0**10,
}
# unit: (category, factor to base unit, accepts metric prefixes)
_UNITS: dict[str, tuple[str, float, bool]] = {}


def _unit(category: str, factor: float, prefixable: bool, *names: str) -> None:
    for name in names:
        _UNITS[name] = (category, factor, prefixable)


# Weight and mass (base: gram)
_unit("mass", 1.0, True, "g")
_unit("mass", 14593.90293720636, False, "sg")
_unit("mass", 453.59237, False, "lbm")
_unit("mass", 1.66053906660e-24, True, "u")
_unit("mass", 28.349523125, False, "ozm")
_unit("mass", 6350.29318, False, "stone")
_unit("mass", 907184.74, False, "ton")
_unit("mass", 45359.237, False, "cwt", "shweight")
_unit("mass", 50802.34544, False, "uk_cwt", "lcwt", "hweight")
_unit("mass", 1016046.9088, False, "uk_ton", "LTON", "brton")
_unit("mass", 64.79891e-3, False, "grain")
# Distance (base: metre)
_unit("distance", 1.0, True, "m")
_unit("distance", 1609.344, False, "mi")
_unit("distance", 1852.0, False, "Nmi")
_unit("distance", 0.0254, False, "in")
_unit("distance", 0.3048, False, "ft")
_unit("distance", 0.9144, False, "yd")
_unit("distance", 1e-10, True, "ang")
_unit("distance", 0.0254 / 72, False, "Picapt", "Pica")
_unit("distance", 0.0254 / 6, False, "pica")
_unit("distance", 1200 / 3937, False, "survey_mi")
_unit("distance", 9.4607304725808e15, True, "ly")
_unit("distance", 3.08567758149137e16, True, "pc", "parsec")
_unit("distance", 5.0292, False, "ell")
# Time (base: second)
_unit("time", 365.25 * 86400, False, "yr")
_unit("time", 86400.0, False, "day", "d")
_unit("time", 3600.0, False, "hr")
_unit("time", 60.0, False, "mn", "min")
_unit("time", 1.0, True, "sec", "s")
# Pressure (base: pascal)
_unit("pressure", 1.0, True, "Pa", "p")
_unit("pressure", 101325.0, True, "atm", "at")
_unit("pressure", 133.322, True, "mmHg")
_unit("pressure", 6894.757293168, False, "psi")
_unit("pressure", 101325 / 760, False, "Torr")
# Force (base: newton)
_unit("force", 1.0, True, "N")
_unit("force", 1e-5, True, "dyn", "dy")
_unit("force", 4.4482216152605, False, "lbf")
_unit("force", 9.80665, True, "pond")
# Energy (base: joule)
_unit("energy", 1.0, True, "J")
_unit("energy", 1e-7, True, "e")
_unit("energy", 4.1868, True, "c")
_unit("energy", 4.184, True, "cal")
_unit("energy", 1.602176634e-19, True, "eV", "ev")
_unit("energy", 2684519.53769617, False, "HPh", "hh")
_unit("energy", 3600.0, True, "Wh", "wh")
_unit("energy", 1.3558179483314, False, "flb")
_unit("energy", 1055.05585262, False, "BTU", "btu")
# Power (base: watt)
_unit("power", 745.69987158227, False, "HP", "h")
_unit("power", 735.49875, False, "PS")
_unit("power", 1.0, True, "W", "w")
# Magnetism (base: tesla)
_unit("magnetism", 1.0, True, "T")
_unit("magnetism", 1e-4, True, "ga")
# Temperature handled separately
for _temperature in ("C", "cel", "F", "fah", "K", "kel", "Rank", "Reau"):
    _UNITS[_temperature] = ("temperature", 1.0, _temperature in ("K", "kel"))
# Volume (base: cubic metre)
_unit("volume", 4.92892159375e-6, False, "tsp")
_unit("volume", 5e-6, False, "tspm")
_unit("volume", 1.478676478125e-5, False, "tbs")
_unit("volume", 2.95735295625e-5, False, "oz")
_unit("volume", 2.365882365e-4, False, "cup")
_unit("volume", 4.73176473e-4, False, "pt", "us_pt")
_unit("volume", 5.6826125e-4, False, "uk_pt")
_unit("volume", 9.46352946e-4, False, "qt")
_unit("volume", 1.1365225e-3, False, "uk_qt")
_unit("volume", 3.785411784e-3, False, "gal")
_unit("volume", 4.54609e-3, False, "uk_gal")
_unit("volume", 1e-3, True, "l", "L", "lt")
_unit("volume", 1.0, True, "m3")
_unit("volume", 4.16818182544058e9, False, "mi3")
_unit("volume", 0.764554857984, False, "yd3")
_unit("volume", 0.028316846592, False, "ft3")
_unit("volume", 1.6387064e-5, False, "in3")
_unit("volume", 1e-30, True, "ang3")
_unit("volume", 0.158987294928, False, "barrel")
_unit("volume", 0.03523907016688, False, "bushel")
_unit("volume", 2.8316846592, False, "regton")
_unit("volume", 1.13267386368, False, "MTON")
# Area (base: square metre)
_unit("area", 4046.8564224, False, "uk_acre")
_unit("area", 4046.87260987425, False, "us_acre")
_unit("area", 1e-20, True, "ang2")
_unit("area", 100.0, False, "ar")
_unit("area", 0.09290304, False, "ft2")
_unit("area", 10000.0, False, "ha")
_unit("area", 6.4516e-4, False, "in2")
_unit("area", 8.9468e30, False, "ly2")
_unit("area", 1.0, True, "m2")
_unit("area", 2589988.110336, False, "mi2")
_unit("area", 3429904, False, "Nmi2")
_unit("area", 0.83612736, False, "yd2")
# Information (base: bit)
_unit("information", 1.0, True, "bit")
_unit("information", 8.0, True, "byte")
# Speed (base: metre per second)
_unit("speed", 0.514444444444444, False, "admkn", "kn")
_unit("speed", 1.0, True, "m/s", "m/sec")
_unit("speed", 1 / 3600, True, "m/h", "m/hr")
_unit("speed", 0.44704, False, "mph")


def _resolve_unit(name: str) -> tuple[str, float, str] | None:
    if name in _UNITS:
        category, factor, _ = _UNITS[name]
        return category, factor, name
    for table in (_BINARY_PREFIXES, _PREFIXES):
        for prefix in sorted(table, key=len, reverse=True):
            if name.startswith(prefix) and len(name) > len(prefix):
                base_name = name[len(prefix) :]
                entry = _UNITS.get(base_name)
                if entry is None or not entry[2]:
                    continue
                category, factor, _ = entry
                if table is _BINARY_PREFIXES and category != "information":
                    continue
                scale = table[prefix]
                if base_name.endswith("2") and category == "area":
                    scale = scale**2
                elif base_name.endswith("3") and category == "volume":
                    scale = scale**3
                return category, factor * scale, base_name
    return None


def _to_kelvin(value: float, unit: str, scale: float) -> float:
    if unit in ("C", "cel"):
        return value + 273.15
    if unit in ("F", "fah"):
        return (value - 32) * 5 / 9 + 273.15
    if unit in ("K", "kel"):
        return value * scale
    if unit == "Rank":
        return value * 5 / 9
    return value * 5 / 4 + 273.15  # Reaumur


def _from_kelvin(value: float, unit: str, scale: float) -> float:
    if unit in ("C", "cel"):
        return value - 273.15
    if unit in ("F", "fah"):
        return (value - 273.15) * 9 / 5 + 32
    if unit in ("K", "kel"):
        return value / scale
    if unit == "Rank":
        return value * 9 / 5
    return (value - 273.15) * 4 / 5


@register(
    "CONVERT",
    min_args=3,
    max_args=3,
    argument_spec="number, from_unit, to_unit",
    lift=lift_all,
    category=ENG,
)
def convert(context: Any, value: Any, from_unit: Any, to_unit: Any) -> Any:
    """Convert a number from one measurement system to another."""
    amount = _num(context, value)
    if is_error(amount):
        return amount
    source = _resolve_unit(text(scalar(context, from_unit)))
    target = _resolve_unit(text(scalar(context, to_unit)))
    if source is None or target is None or source[0] != target[0]:
        return NA_ERROR
    if source[0] == "temperature":
        kelvin = _to_kelvin(amount, source[2], source[1])
        return _from_kelvin(kelvin, target[2], target[1])
    result = amount * source[1] / target[1]
    rounded = float(f"{result:.15g}")
    return int(rounded) if rounded.is_integer() and abs(rounded) < 2**53 else rounded

