"""Formula translations required by the XLSX storage format."""

from __future__ import annotations

import re
from collections.abc import Callable


_FUTURE_FUNCTION_NAMES = ("PDURATION", "RRI")
_QUOTED_TEXT = re.compile(r'"(?:[^"]|"")*"')
_FUNCTION_CALL = re.compile(
    rf"(?<![A-Za-z0-9_.])({'|'.join(_FUTURE_FUNCTION_NAMES)})(?=\s*\()",
    re.IGNORECASE,
)
_XLFX_PREFIX = re.compile(
    rf"_xlfn\.(?=({'|'.join(_FUTURE_FUNCTION_NAMES)})\s*\()",
    re.IGNORECASE,
)


def to_xlsx_formula(formula: str) -> str:
    """Add OOXML future-function prefixes without changing formula text literals."""
    return _outside_quoted_text(
        formula,
        lambda part: _FUNCTION_CALL.sub(
            lambda match: f"_xlfn.{match.group(1).upper()}",
            part,
        ),
    )


def from_xlsx_formula(formula: str) -> str:
    """Remove storage-only future-function prefixes understood by Duddy Spreadsheet."""
    return _outside_quoted_text(
        formula,
        lambda part: _XLFX_PREFIX.sub("", part),
    )


def _outside_quoted_text(value: str, transform: Callable[[str], str]) -> str:
    parts: list[str] = []
    position = 0
    for match in _QUOTED_TEXT.finditer(value):
        parts.append(transform(value[position : match.start()]))
        parts.append(match.group(0))
        position = match.end()
    parts.append(transform(value[position:]))
    return "".join(parts)
