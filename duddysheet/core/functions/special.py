"""Special functions for the statistical and engineering families.

Pure-Python implementations of the regularized incomplete gamma and beta
functions, probability distribution CDFs and inverses, and Bessel functions,
accurate to roughly 1e-12. No third-party numerics are required.
"""

from __future__ import annotations

import math
from collections.abc import Callable

_EPSILON = 3e-16
_TINY = 1e-300


def regularized_gamma_p(a: float, x: float) -> float:
    """Return the lower regularized incomplete gamma function P(a, x)."""
    if x <= 0:
        return 0.0
    if a <= 0:
        raise ValueError("a must be positive")
    if x < a + 1:
        term = 1.0 / a
        total = term
        denominator = a
        for _ in range(10_000):
            denominator += 1
            term *= x / denominator
            total += term
            if abs(term) < abs(total) * _EPSILON:
                break
        return min(1.0, total * math.exp(-x + a * math.log(x) - math.lgamma(a)))
    return 1.0 - regularized_gamma_q(a, x)


def regularized_gamma_q(a: float, x: float) -> float:
    """Return the upper regularized incomplete gamma function Q(a, x)."""
    if x <= 0:
        return 1.0
    if x < a + 1:
        return 1.0 - regularized_gamma_p(a, x)
    b = x + 1 - a
    c = 1 / _TINY
    d = 1 / b
    h = d
    for index in range(1, 10_000):
        an = -index * (index - a)
        b += 2
        d = an * d + b
        if abs(d) < _TINY:
            d = _TINY
        c = b + an / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < _EPSILON:
            break
    return max(0.0, math.exp(-x + a * math.log(x) - math.lgamma(a)) * h)


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    qab = a + b
    qap = a + 1
    qam = a - 1
    c = 1.0
    d = 1 - qab * x / qap
    if abs(d) < _TINY:
        d = _TINY
    d = 1 / d
    h = d
    for m in range(1, 10_000):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        if abs(d) < _TINY:
            d = _TINY
        c = 1 + aa / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        if abs(d) < _TINY:
            d = _TINY
        c = 1 + aa / c
        if abs(c) < _TINY:
            c = _TINY
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < _EPSILON:
            break
    return h


def regularized_beta(x: float, a: float, b: float) -> float:
    """Return the regularized incomplete beta function I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    if x < (a + 1) / (a + b + 2):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1 - front * _beta_continued_fraction(b, a, 1 - x) / b


def invert(
    function: Callable[[float], float],
    target: float,
    low: float,
    high: float,
    *,
    expand_high: bool = False,
    tolerance: float = 1e-14,
) -> float:
    """Solve ``function(x) == target`` for a monotone increasing function."""
    if expand_high:
        for _ in range(2000):
            if function(high) >= target:
                break
            low, high = high, high * 2 + 1
    f_low = function(low) - target
    for _ in range(400):
        middle = (low + high) / 2
        f_middle = function(middle) - target
        if f_middle == 0 or (high - low) / 2 < tolerance * max(1.0, abs(middle)):
            return middle
        if (f_middle < 0) == (f_low < 0):
            low, f_low = middle, f_middle
        else:
            high = middle
    return (low + high) / 2


# ----------------------------------------------------------- distributions
def normal_cdf(z: float) -> float:
    """Return the standard normal cumulative distribution."""
    return 0.5 * math.erfc(-z / math.sqrt(2))


def normal_pdf(z: float) -> float:
    """Return the standard normal density."""
    return math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)


def normal_inverse(p: float) -> float:
    """Return the standard normal quantile (Acklam's method refined by Newton)."""
    if not 0 < p < 1:
        raise ValueError("probability must be in (0, 1)")
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    low = 0.02425
    if p < low:
        q = math.sqrt(-2 * math.log(p))
        x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    elif p <= 1 - low:
        q = p - 0.5
        r = q * q
        x = (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
            * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
        )
    else:
        q = math.sqrt(-2 * math.log1p(-p))
        x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    for _ in range(3):
        error = normal_cdf(x) - p
        density = normal_pdf(x)
        if density == 0:
            break
        x -= error / density
    return x


def t_cdf(t: float, degrees: float) -> float:
    """Return the Student's t cumulative distribution."""
    x = degrees / (degrees + t * t)
    tail = 0.5 * regularized_beta(x, degrees / 2, 0.5)
    return 1 - tail if t > 0 else tail


def t_pdf(t: float, degrees: float) -> float:
    """Return the Student's t density."""
    return math.exp(
        math.lgamma((degrees + 1) / 2)
        - math.lgamma(degrees / 2)
        - 0.5 * math.log(degrees * math.pi)
        - (degrees + 1) / 2 * math.log1p(t * t / degrees)
    )


def t_inverse(p: float, degrees: float) -> float:
    """Return the Student's t quantile."""
    if p == 0.5:
        return 0.0
    if p < 0.5:
        return -t_inverse(1 - p, degrees)
    return invert(lambda t: t_cdf(t, degrees), p, 0.0, 10.0, expand_high=True)


def chi_square_cdf(x: float, degrees: float) -> float:
    """Return the chi-squared cumulative distribution."""
    return regularized_gamma_p(degrees / 2, x / 2) if x > 0 else 0.0


def gamma_cdf(x: float, alpha: float, beta: float) -> float:
    """Return the gamma cumulative distribution with shape and scale."""
    return regularized_gamma_p(alpha, x / beta) if x > 0 else 0.0


def gamma_pdf(x: float, alpha: float, beta: float) -> float:
    """Return the gamma density with shape and scale."""
    if x < 0:
        return 0.0
    if x == 0:
        return (1 / beta) if alpha == 1 else (0.0 if alpha > 1 else math.inf)
    return math.exp(
        (alpha - 1) * math.log(x) - x / beta - math.lgamma(alpha) - alpha * math.log(beta)
    )


def gamma_inverse(p: float, alpha: float, beta: float) -> float:
    """Return the gamma quantile."""
    return invert(
        lambda x: gamma_cdf(x, alpha, beta),
        p,
        0.0,
        max(1.0, alpha * beta * 2),
        expand_high=True,
    )


def beta_pdf(x: float, alpha: float, beta: float) -> float:
    """Return the standard beta density on [0, 1]."""
    if x < 0 or x > 1:
        return 0.0
    if x in (0.0, 1.0):
        if (x == 0 and alpha < 1) or (x == 1 and beta < 1):
            return math.inf
        if (x == 0 and alpha == 1) or (x == 1 and beta == 1):
            return math.exp(math.lgamma(alpha + beta) - math.lgamma(alpha) - math.lgamma(beta))
        return 0.0
    return math.exp(
        (alpha - 1) * math.log(x)
        + (beta - 1) * math.log1p(-x)
        + math.lgamma(alpha + beta)
        - math.lgamma(alpha)
        - math.lgamma(beta)
    )


def f_cdf(x: float, d1: float, d2: float) -> float:
    """Return the F cumulative distribution."""
    if x <= 0:
        return 0.0
    return regularized_beta(d1 * x / (d1 * x + d2), d1 / 2, d2 / 2)


def f_pdf(x: float, d1: float, d2: float) -> float:
    """Return the F density."""
    if x < 0:
        return 0.0
    if x == 0:
        return 0.0 if d1 > 2 else (1.0 if d1 == 2 else math.inf)
    return math.exp(
        0.5 * (d1 * math.log(d1 * x) + d2 * math.log(d2) - (d1 + d2) * math.log(d1 * x + d2))
        - math.log(x)
        - (math.lgamma(d1 / 2) + math.lgamma(d2 / 2) - math.lgamma((d1 + d2) / 2))
    )


def binomial_pmf(k: int, n: int, p: float) -> float:
    """Return the binomial probability mass."""
    if k < 0 or k > n:
        return 0.0
    if p == 0:
        return 1.0 if k == 0 else 0.0
    if p == 1:
        return 1.0 if k == n else 0.0
    return math.exp(
        math.lgamma(n + 1)
        - math.lgamma(k + 1)
        - math.lgamma(n - k + 1)
        + k * math.log(p)
        + (n - k) * math.log1p(-p)
    )


def binomial_cdf(k: int, n: int, p: float) -> float:
    """Return the binomial cumulative distribution."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return min(1.0, sum(binomial_pmf(i, n, p) for i in range(k + 1)))


def poisson_pmf(k: int, mean: float) -> float:
    """Return the Poisson probability mass."""
    if k < 0:
        return 0.0
    if mean == 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(k * math.log(mean) - mean - math.lgamma(k + 1))


def poisson_cdf(k: int, mean: float) -> float:
    """Return the Poisson cumulative distribution."""
    if k < 0:
        return 0.0
    return regularized_gamma_q(k + 1, mean) if mean > 0 else 1.0


# ------------------------------------------------------------------- Bessel
def bessel_j(x: float, order: int) -> float:
    """Return the Bessel function of the first kind J_n(x)."""
    if order < 0:
        raise ValueError("order must be non-negative")
    total = 0.0
    term_sign = 1.0
    half = x / 2
    for k in range(0, 300):
        log_term = (2 * k + order) * math.log(abs(half)) if half else (0.0 if 2 * k + order == 0 else -math.inf)
        if log_term == -math.inf:
            term = 0.0
        else:
            term = math.exp(log_term - math.lgamma(k + 1) - math.lgamma(k + order + 1))
            if half < 0 and (2 * k + order) % 2:
                term = -term
        total += term_sign * term
        term_sign = -term_sign
        if k > abs(x) and abs(term) < 1e-17 * max(1.0, abs(total)):
            break
    if abs(x) > 25:
        return _bessel_j_asymptotic(x, order)
    return total


def _bessel_j_asymptotic(x: float, order: int) -> float:
    mu = 4 * order * order
    z = abs(x)
    omega = z - (order / 2 + 0.25) * math.pi
    p = 1.0
    q = (mu - 1) / (8 * z)
    term_p = 1.0
    term_q = q
    for k in range(1, 30):
        term_p *= -((mu - (4 * k - 3) ** 2) * (mu - (4 * k - 1) ** 2)) / (
            (2 * k - 1) * (2 * k) * (8 * z) ** 2
        )
        term_q *= -((mu - (4 * k - 1) ** 2) * (mu - (4 * k + 1) ** 2)) / (
            (2 * k) * (2 * k + 1) * (8 * z) ** 2
        )
        if abs(term_p) < 1e-17 and abs(term_q) < 1e-17:
            break
        p += term_p
        q += term_q
    value = math.sqrt(2 / (math.pi * z)) * (p * math.cos(omega) - q * math.sin(omega))
    return -value if x < 0 and order % 2 else value


def bessel_i(x: float, order: int) -> float:
    """Return the modified Bessel function of the first kind I_n(x)."""
    if order < 0:
        raise ValueError("order must be non-negative")
    total = 0.0
    half = x / 2
    for k in range(0, 500):
        power = 2 * k + order
        if half == 0:
            term = 1.0 if power == 0 else 0.0
        else:
            term = math.exp(power * math.log(abs(half)) - math.lgamma(k + 1) - math.lgamma(k + order + 1))
            if half < 0 and power % 2:
                term = -term
        total += term
        if k > abs(x) and abs(term) < 1e-17 * max(1.0, abs(total)):
            break
    return total


def bessel_y(x: float, order: int) -> float:
    """Return the Bessel function of the second kind Y_n(x) for x > 0."""
    if x <= 0 or order < 0:
        raise ValueError("Y_n requires x > 0 and n >= 0")
    y0 = _bessel_y0(x)
    if order == 0:
        return y0
    y1 = _bessel_y1(x)
    for n in range(1, order):
        y0, y1 = y1, 2 * n / x * y1 - y0
    return y1


def _bessel_y0(x: float) -> float:
    # Y0 = (2/pi)(ln(x/2) + gamma) J0 + series
    if x > 25:
        return _bessel_y_asymptotic(x, 0)
    euler = 0.5772156649015329
    j0 = bessel_j(x, 0)
    half_sq = (x / 2) ** 2
    total = 0.0
    harmonic = 0.0
    term = 1.0
    for k in range(1, 300):
        harmonic += 1 / k
        term *= -half_sq / (k * k)
        total += -term * harmonic
        if abs(term * harmonic) < 1e-18:
            break
    return 2 / math.pi * ((math.log(x / 2) + euler) * j0 + total)


def _bessel_y1(x: float) -> float:
    if x > 25:
        return _bessel_y_asymptotic(x, 1)
    euler = 0.5772156649015329
    j1 = bessel_j(x, 1)
    half = x / 2
    total = 0.0
    harmonic_k = 0.0
    term = half  # (x/2)^(2k+1) / (k!(k+1)!) at k=0
    total += -term * (0 + 1.0)  # H_0 + H_1 = 1
    for k in range(1, 300):
        term *= -(half * half) / (k * (k + 1))
        harmonic_k += 1 / k
        combined = harmonic_k + harmonic_k + 1 / (k + 1)
        total += -term * combined
        if abs(term * combined) < 1e-18:
            break
    return 2 / math.pi * (math.log(half) + euler) * j1 - 2 / (math.pi * x) + total / math.pi


def _bessel_y_asymptotic(x: float, order: int) -> float:
    mu = 4 * order * order
    omega = x - (order / 2 + 0.25) * math.pi
    p = 1.0
    q = (mu - 1) / (8 * x)
    term_p = 1.0
    term_q = q
    for k in range(1, 30):
        term_p *= -((mu - (4 * k - 3) ** 2) * (mu - (4 * k - 1) ** 2)) / (
            (2 * k - 1) * (2 * k) * (8 * x) ** 2
        )
        term_q *= -((mu - (4 * k - 1) ** 2) * (mu - (4 * k + 1) ** 2)) / (
            (2 * k) * (2 * k + 1) * (8 * x) ** 2
        )
        if abs(term_p) < 1e-17 and abs(term_q) < 1e-17:
            break
        p += term_p
        q += term_q
    return math.sqrt(2 / (math.pi * x)) * (p * math.sin(omega) + q * math.cos(omega))


def bessel_k(x: float, order: int) -> float:
    """Return the modified Bessel function of the second kind K_n(x) for x > 0."""
    if x <= 0 or order < 0:
        raise ValueError("K_n requires x > 0 and n >= 0")
    k0 = _bessel_k0(x)
    if order == 0:
        return k0
    k1 = _bessel_k1(x)
    for n in range(1, order):
        k0, k1 = k1, 2 * n / x * k1 + k0
    return k1


def _bessel_k0(x: float) -> float:
    if x > 2:
        return _bessel_k_large(x, 0)
    euler = 0.5772156649015329
    half_sq = (x / 2) ** 2
    total = 0.0
    harmonic = 0.0
    term = 1.0
    for k in range(1, 200):
        harmonic += 1 / k
        term *= half_sq / (k * k)
        total += term * harmonic
        if term * harmonic < 1e-18:
            break
    return -(math.log(x / 2) + euler) * bessel_i(x, 0) + total


def _bessel_k1(x: float) -> float:
    if x > 2:
        return _bessel_k_large(x, 1)
    # Wronskian: I1 K0 + I0 K1 = 1/x
    return (1 / x - bessel_i(x, 1) * _bessel_k0(x)) / bessel_i(x, 0)


def _bessel_k_large(x: float, order: int) -> float:
    # Integral representation K_n(x) = integral_0^inf exp(-x cosh t) cosh(n t) dt
    steps = 2000
    upper = math.acosh(max(1.0, 50 / x + 1)) + 1
    width = upper / steps
    total = 0.0
    for index in range(steps + 1):
        t = index * width
        weight = 0.5 if index in (0, steps) else 1.0
        total += weight * math.exp(-x * math.cosh(t)) * math.cosh(order * t)
    return total * width
