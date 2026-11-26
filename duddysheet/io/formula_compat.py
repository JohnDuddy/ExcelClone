"""Formula translations required by the XLSX storage format.

Excel stores functions added after Excel 2007 with an ``_xlfn.`` prefix
(``_xlfn._xlws.`` for FILTER and SORT), LET/LAMBDA parameters with
``_xlpm.``, the spill operator ``A1#`` as ``_xlfn.ANCHORARRAY(A1)``, and the
``@`` operator as ``_xlfn.SINGLE(...)``. Without these spellings Excel shows
#NAME? when it opens the file.
"""

from __future__ import annotations

import re
from collections.abc import Callable

FUTURE_FUNCTIONS = frozenset(
    """
    ACOT ACOTH AGGREGATE ARABIC ARRAYTOTEXT BASE BETA.DIST BETA.INV BINOM.DIST
    BINOM.DIST.RANGE BINOM.INV BITAND BITLSHIFT BITOR BITRSHIFT BITXOR BYCOL BYROW
    CEILING.MATH CEILING.PRECISE CHISQ.DIST CHISQ.DIST.RT CHISQ.INV CHISQ.INV.RT
    CHISQ.TEST CHOOSECOLS CHOOSEROWS COMBINA CONCAT CONFIDENCE.NORM CONFIDENCE.T
    COT COTH COVARIANCE.P COVARIANCE.S CSC CSCH DAYS DECIMAL DROP ECMA.CEILING
    ENCODEURL ERF.PRECISE ERFC.PRECISE EXPAND EXPON.DIST F.DIST F.DIST.RT F.INV
    F.INV.RT F.TEST FIELDVALUE FILTERXML FLOOR.MATH FLOOR.PRECISE FORECAST.ETS
    FORECAST.ETS.CONFINT FORECAST.ETS.SEASONALITY FORECAST.ETS.STAT
    FORECAST.LINEAR FORMULATEXT GAMMA GAMMA.DIST GAMMA.INV GAMMALN.PRECISE GAUSS
    GROUPBY HSTACK HYPGEOM.DIST IFNA IFS IMAGE IMCOSH IMCOT IMCSC IMCSCH IMSEC IMSECH
    IMSINH IMTAN ISFORMULA ISO.CEILING ISOMITTED ISOWEEKNUM LAMBDA LET LOGNORM.DIST
    LOGNORM.INV MAKEARRAY MAP MAXIFS MINIFS MODE.MULT MODE.SNGL MUNIT NEGBINOM.DIST
    NETWORKDAYS.INTL NORM.DIST NORM.INV NORM.S.DIST NORM.S.INV NUMBERVALUE PDURATION
    PERCENTILE.EXC PERCENTILE.INC PERCENTOF PERCENTRANK.EXC PERCENTRANK.INC
    PERMUTATIONA PHI PIVOTBY POISSON.DIST QUARTILE.EXC QUARTILE.INC RANDARRAY
    RANK.AVG RANK.EQ REDUCE REGEXEXTRACT REGEXREPLACE REGEXTEST RRI SCAN SEC SECH
    SEQUENCE SHEET SHEETS SKEW.P SORTBY STDEV.P STDEV.S STOCKHISTORY SWITCH T.DIST
    T.DIST.2T T.DIST.RT T.INV T.INV.2T T.TEST TAKE TEXTAFTER TEXTBEFORE TEXTJOIN
    TEXTSPLIT TOCOL TOROW TRANSLATE TRIMRANGE UNICHAR UNICODE UNIQUE VALUETOTEXT
    VAR.P VAR.S VSTACK WEBSERVICE WEIBULL.DIST WORKDAY.INTL WRAPCOLS WRAPROWS
    XLOOKUP XMATCH XOR Z.TEST ANCHORARRAY SINGLE
    """.split()
)
WORKSHEET_FUNCTIONS = frozenset({"FILTER", "SORT"})
#: Functions whose results are arrays; formulas using them are stored as
#: dynamic-array formulas so Excel does not add implicit intersection.
DYNAMIC_ARRAY_FUNCTIONS = frozenset(
    """
    FILTER SORT SORTBY UNIQUE SEQUENCE RANDARRAY VSTACK HSTACK TOCOL TOROW WRAPROWS
    WRAPCOLS TAKE DROP CHOOSEROWS CHOOSECOLS EXPAND TEXTSPLIT GROUPBY PIVOTBY MAP
    SCAN BYROW BYCOL MAKEARRAY TRANSPOSE TRIMRANGE ANCHORARRAY REGEXEXTRACT
    """.split()
)

_QUOTED_TEXT = re.compile(r'"(?:[^"]|"")*"')
_PREFIX = re.compile(r"_xlfn\._xlws\.|_xlfn\.|_xlws\.|_xlpm\.", re.IGNORECASE)
_LEGACY_FUTURE = ("PDURATION", "RRI")
_FUNCTION_CALL = re.compile(
    rf"(?<![A-Za-z0-9_.])({'|'.join(_LEGACY_FUTURE)})(?=\s*\()",
    re.IGNORECASE,
)


def to_xlsx_formula(formula: str) -> str:
    """Render a formula with the prefixes Excel's file format requires."""
    from duddysheet.core.parser import parse_formula

    try:
        node = parse_formula(formula)
    except ValueError:
        return _outside_quoted_text(
            formula,
            lambda part: _FUNCTION_CALL.sub(
                lambda match: f"_xlfn.{match.group(1).upper()}",
                part,
            ),
        )
    from duddysheet.core.translation import formula_to_text

    return formula_to_text(node, dialect="xlsx")


def from_xlsx_formula(formula: str) -> str:
    """Remove storage-only prefixes so formulas read naturally.

    ``ANCHORARRAY(A1)`` and ``SINGLE(x)`` become Excel's ``A1#`` and ``@x``.
    """
    stripped = _outside_quoted_text(formula, lambda part: _PREFIX.sub("", part))
    upper = stripped.upper()
    if "ANCHORARRAY(" not in upper and "SINGLE(" not in upper:
        return stripped
    from duddysheet.core.parser import (
        FunctionNode,
        ImplicitIntersectionNode,
        SpillNode,
        map_children,
        parse_formula,
    )
    from duddysheet.core.translation import formula_to_text

    def restore(node: object) -> object:
        node = map_children(node, restore)
        if isinstance(node, FunctionNode) and len(node.arguments) == 1:
            if node.name == "ANCHORARRAY":
                return SpillNode(node.arguments[0])
            if node.name == "SINGLE":
                return ImplicitIntersectionNode(node.arguments[0])
        return node

    try:
        return formula_to_text(restore(parse_formula(stripped)))
    except ValueError:
        return stripped


def is_dynamic_formula(formula: str) -> bool:
    """Return whether a formula calls a function that returns an array."""
    from duddysheet.core.parser import collect_function_names, parse_formula

    try:
        names = collect_function_names(parse_formula(formula))
    except ValueError:
        return False
    return any(name in DYNAMIC_ARRAY_FUNCTIONS for name in names)


def _outside_quoted_text(value: str, transform: Callable[[str], str]) -> str:
    parts: list[str] = []
    position = 0
    for match in _QUOTED_TEXT.finditer(value):
        parts.append(transform(value[position : match.start()]))
        parts.append(match.group(0))
        position = match.end()
    parts.append(transform(value[position:]))
    return "".join(parts)
