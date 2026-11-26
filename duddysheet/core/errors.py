"""Spreadsheet error values and Excel-compatible literals."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpreadsheetError:
    """An error value that propagates through formula evaluation."""

    literal: str
    type_number: int | None = None

    def __str__(self) -> str:
        return self.literal


NULL_ERROR = SpreadsheetError("#NULL!", 1)
DIV_ZERO_ERROR = SpreadsheetError("#DIV/0!", 2)
VALUE_ERROR = SpreadsheetError("#VALUE!", 3)
REF_ERROR = SpreadsheetError("#REF!", 4)
NAME_ERROR = SpreadsheetError("#NAME?", 5)
NUM_ERROR = SpreadsheetError("#NUM!", 6)
NA_ERROR = SpreadsheetError("#N/A", 7)
GETTING_DATA_ERROR = SpreadsheetError("#GETTING_DATA", 8)
SPILL_ERROR = SpreadsheetError("#SPILL!", 9)
CONNECT_ERROR = SpreadsheetError("#CONNECT!", 10)
BLOCKED_ERROR = SpreadsheetError("#BLOCKED!", 11)
UNKNOWN_ERROR = SpreadsheetError("#UNKNOWN!", 12)
FIELD_ERROR = SpreadsheetError("#FIELD!", 13)
CALC_ERROR = SpreadsheetError("#CALC!", 14)
CIRC_ERROR = SpreadsheetError("#CIRC!")

ERRORS_BY_LITERAL = {
    error.literal: error
    for error in (
        NULL_ERROR,
        DIV_ZERO_ERROR,
        VALUE_ERROR,
        REF_ERROR,
        NAME_ERROR,
        NUM_ERROR,
        NA_ERROR,
        GETTING_DATA_ERROR,
        SPILL_ERROR,
        CONNECT_ERROR,
        BLOCKED_ERROR,
        UNKNOWN_ERROR,
        FIELD_ERROR,
        CALC_ERROR,
        CIRC_ERROR,
    )
}


def error_from_literal(literal: str) -> SpreadsheetError:
    """Return the canonical error value for an error literal."""
    try:
        return ERRORS_BY_LITERAL[literal.upper()]
    except KeyError:
        raise ValueError(f"Unknown spreadsheet error: {literal!r}") from None


def is_error(value: object) -> bool:
    """Return whether a value is a spreadsheet error."""
    return isinstance(value, SpreadsheetError)

