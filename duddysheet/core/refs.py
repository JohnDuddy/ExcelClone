"""Spreadsheet reference parsing, formatting, and translation."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

MAX_ROWS = 1_048_576
MAX_COLUMNS = 16_384

_CELL_RE = re.compile(
    r"^(?P<col_abs>\$?)(?P<column>[A-Za-z]{1,3})"
    r"(?P<row_abs>\$?)(?P<row>[1-9][0-9]*)$"
)
_COLUMN_RANGE_RE = re.compile(
    r"^(?P<left_abs>\$?)(?P<left>[A-Za-z]{1,3}):"
    r"(?P<right_abs>\$?)(?P<right>[A-Za-z]{1,3})$"
)
_ROW_RANGE_RE = re.compile(
    r"^(?P<top_abs>\$?)(?P<top>[1-9][0-9]*):"
    r"(?P<bottom_abs>\$?)(?P<bottom>[1-9][0-9]*)$"
)
_R1C1_CELL_RE = re.compile(
    r"^R(?P<row>\[-?[0-9]+\]|[1-9][0-9]*)?"
    r"C(?P<column>\[-?[0-9]+\]|[1-9][0-9]*)?$",
    re.IGNORECASE,
)
_UNQUOTED_SHEET_RE = re.compile(r"^[A-Za-z_\\][A-Za-z0-9_.\\]*$")


def column_to_index(label: str) -> int:
    """Convert an A1 column label to a zero-based column index."""
    if not label or not label.isascii() or not label.isalpha():
        raise ValueError(f"Invalid column label: {label!r}")

    value = 0
    for character in label.upper():
        value = value * 26 + ord(character) - ord("A") + 1
    index = value - 1
    if index >= MAX_COLUMNS:
        raise ValueError(f"Column exceeds XFD: {label!r}")
    return index


def index_to_column(index: int) -> str:
    """Convert a zero-based column index to its A1 label."""
    if not 0 <= index < MAX_COLUMNS:
        raise ValueError(f"Column index out of range: {index}")

    value = index + 1
    characters: list[str] = []
    while value:
        value, remainder = divmod(value - 1, 26)
        characters.append(chr(ord("A") + remainder))
    return "".join(reversed(characters))


def quote_sheet_name(name: str) -> str:
    """Quote a sheet name only when A1 syntax requires it."""
    if not name:
        raise ValueError("Sheet name cannot be empty")
    resembles_cell = _CELL_RE.fullmatch(name) is not None
    if _UNQUOTED_SHEET_RE.fullmatch(name) and not resembles_cell:
        return name
    return "'" + name.replace("'", "''") + "'"


@dataclass(frozen=True, slots=True)
class CellReference:
    """An immutable reference to one cell."""

    row: int
    column: int
    sheet: str | None = None
    row_absolute: bool = False
    column_absolute: bool = False

    def __post_init__(self) -> None:
        if not 0 <= self.row < MAX_ROWS:
            raise ValueError(f"Row index out of range: {self.row}")
        if not 0 <= self.column < MAX_COLUMNS:
            raise ValueError(f"Column index out of range: {self.column}")
        if self.sheet == "":
            raise ValueError("Sheet name cannot be empty")

    @property
    def coordinate(self) -> tuple[int, int]:
        """Return the zero-based row and column coordinate."""
        return self.row, self.column

    def to_a1(self, *, include_sheet: bool = True) -> str:
        """Render the reference in A1 notation."""
        column = ("$" if self.column_absolute else "") + index_to_column(self.column)
        row = ("$" if self.row_absolute else "") + str(self.row + 1)
        prefix = (
            f"{quote_sheet_name(self.sheet)}!"
            if include_sheet and self.sheet is not None
            else ""
        )
        return f"{prefix}{column}{row}"

    def to_r1c1(self, *, origin: tuple[int, int]) -> str:
        """Render the reference in R1C1 notation relative to an origin."""
        origin_row, origin_column = origin
        if self.row_absolute:
            row = str(self.row + 1)
        else:
            row_delta = self.row - origin_row
            row = "" if row_delta == 0 else f"[{row_delta}]"
        if self.column_absolute:
            column = str(self.column + 1)
        else:
            column_delta = self.column - origin_column
            column = "" if column_delta == 0 else f"[{column_delta}]"
        prefix = f"{quote_sheet_name(self.sheet)}!" if self.sheet is not None else ""
        return f"{prefix}R{row}C{column}"

    def shifted(self, *, rows: int = 0, columns: int = 0) -> CellReference:
        """Shift relative reference parts while preserving absolute parts."""
        return CellReference(
            row=self.row if self.row_absolute else self.row + rows,
            column=self.column if self.column_absolute else self.column + columns,
            sheet=self.sheet,
            row_absolute=self.row_absolute,
            column_absolute=self.column_absolute,
        )


@dataclass(frozen=True, slots=True)
class RangeReference:
    """An immutable rectangular reference with lazy coordinate iteration."""

    start: CellReference
    end: CellReference
    whole_row: bool = False
    whole_column: bool = False

    def __post_init__(self) -> None:
        if self.whole_row and self.whole_column:
            raise ValueError("A range cannot be both whole-row and whole-column")
        if self.start.sheet != self.end.sheet:
            raise ValueError("Both range endpoints must be on the same sheet")
        if self.whole_row and (
            self.start.column != 0 or self.end.column != MAX_COLUMNS - 1
        ):
            raise ValueError("Whole-row range must span every column")
        if self.whole_column and (
            self.start.row != 0 or self.end.row != MAX_ROWS - 1
        ):
            raise ValueError("Whole-column range must span every row")

    @property
    def sheet(self) -> str | None:
        """Return the sheet shared by both endpoints."""
        return self.start.sheet

    @property
    def min_row(self) -> int:
        return min(self.start.row, self.end.row)

    @property
    def max_row(self) -> int:
        return max(self.start.row, self.end.row)

    @property
    def min_column(self) -> int:
        return min(self.start.column, self.end.column)

    @property
    def max_column(self) -> int:
        return max(self.start.column, self.end.column)

    def __len__(self) -> int:
        return (self.max_row - self.min_row + 1) * (
            self.max_column - self.min_column + 1
        )

    def __iter__(self) -> Iterator[CellReference]:
        for row in range(self.min_row, self.max_row + 1):
            for column in range(self.min_column, self.max_column + 1):
                yield CellReference(row=row, column=column, sheet=self.sheet)

    def contains(self, row: int, column: int) -> bool:
        """Return whether a coordinate lies within the rectangle."""
        return (
            self.min_row <= row <= self.max_row
            and self.min_column <= column <= self.max_column
        )

    def to_a1(self) -> str:
        """Render the range in A1 notation."""
        prefix = f"{quote_sheet_name(self.sheet)}!" if self.sheet is not None else ""
        if self.whole_column:
            left = (
                ("$" if self.start.column_absolute else "")
                + index_to_column(self.start.column)
            )
            right = (
                ("$" if self.end.column_absolute else "")
                + index_to_column(self.end.column)
            )
            return f"{prefix}{left}:{right}"
        if self.whole_row:
            top = ("$" if self.start.row_absolute else "") + str(self.start.row + 1)
            bottom = ("$" if self.end.row_absolute else "") + str(self.end.row + 1)
            return f"{prefix}{top}:{bottom}"
        return (
            prefix
            + self.start.to_a1(include_sheet=False)
            + ":"
            + self.end.to_a1(include_sheet=False)
        )

    def shifted(self, *, rows: int = 0, columns: int = 0) -> RangeReference:
        """Shift relative endpoint parts while retaining range shape."""
        effective_rows = 0 if self.whole_column else rows
        effective_columns = 0 if self.whole_row else columns
        return RangeReference(
            start=self.start.shifted(
                rows=effective_rows,
                columns=effective_columns,
            ),
            end=self.end.shifted(
                rows=effective_rows,
                columns=effective_columns,
            ),
            whole_row=self.whole_row,
            whole_column=self.whole_column,
        )


Reference = CellReference | RangeReference


def parse_a1(text: str, *, default_sheet: str | None = None) -> Reference:
    """Parse a cell, rectangular range, whole row, or whole column."""
    sheet, coordinate_text = _split_sheet_reference(text)
    sheet = sheet if sheet is not None else default_sheet

    column_match = _COLUMN_RANGE_RE.fullmatch(coordinate_text)
    if column_match:
        left_column = column_to_index(column_match.group("left"))
        right_column = column_to_index(column_match.group("right"))
        return RangeReference(
            CellReference(
                row=0,
                column=left_column,
                sheet=sheet,
                column_absolute=bool(column_match.group("left_abs")),
            ),
            CellReference(
                row=MAX_ROWS - 1,
                column=right_column,
                sheet=sheet,
                column_absolute=bool(column_match.group("right_abs")),
            ),
            whole_column=True,
        )

    row_match = _ROW_RANGE_RE.fullmatch(coordinate_text)
    if row_match:
        top_row = int(row_match.group("top")) - 1
        bottom_row = int(row_match.group("bottom")) - 1
        if top_row >= MAX_ROWS or bottom_row >= MAX_ROWS:
            raise ValueError(f"Row exceeds {MAX_ROWS}: {text!r}")
        return RangeReference(
            CellReference(
                row=top_row,
                column=0,
                sheet=sheet,
                row_absolute=bool(row_match.group("top_abs")),
            ),
            CellReference(
                row=bottom_row,
                column=MAX_COLUMNS - 1,
                sheet=sheet,
                row_absolute=bool(row_match.group("bottom_abs")),
            ),
            whole_row=True,
        )

    if ":" in coordinate_text:
        left_text, separator, right_text = coordinate_text.partition(":")
        if not separator or ":" in right_text:
            raise ValueError(f"Invalid A1 range: {text!r}")
        start = _parse_a1_cell(left_text, sheet=sheet)
        end = _parse_a1_cell(right_text, sheet=sheet)
        return RangeReference(start, end)

    return _parse_a1_cell(coordinate_text, sheet=sheet)


def parse_r1c1(
    text: str,
    *,
    origin: tuple[int, int],
    default_sheet: str | None = None,
) -> Reference:
    """Parse an R1C1 cell or rectangular range relative to an origin."""
    sheet, coordinate_text = _split_sheet_reference(text)
    sheet = sheet if sheet is not None else default_sheet
    if ":" in coordinate_text:
        left_text, separator, right_text = coordinate_text.partition(":")
        if not separator or ":" in right_text:
            raise ValueError(f"Invalid R1C1 range: {text!r}")
        return RangeReference(
            _parse_r1c1_cell(left_text, origin=origin, sheet=sheet),
            _parse_r1c1_cell(right_text, origin=origin, sheet=sheet),
        )
    return _parse_r1c1_cell(coordinate_text, origin=origin, sheet=sheet)


def _parse_a1_cell(text: str, *, sheet: str | None) -> CellReference:
    match = _CELL_RE.fullmatch(text)
    if not match:
        raise ValueError(f"Invalid A1 reference: {text!r}")
    row = int(match.group("row")) - 1
    column = column_to_index(match.group("column"))
    if row >= MAX_ROWS:
        raise ValueError(f"Row exceeds {MAX_ROWS}: {text!r}")
    return CellReference(
        row=row,
        column=column,
        sheet=sheet,
        row_absolute=bool(match.group("row_abs")),
        column_absolute=bool(match.group("col_abs")),
    )


def _parse_r1c1_cell(
    text: str,
    *,
    origin: tuple[int, int],
    sheet: str | None,
) -> CellReference:
    match = _R1C1_CELL_RE.fullmatch(text)
    if not match:
        raise ValueError(f"Invalid R1C1 reference: {text!r}")

    row, row_absolute = _resolve_r1c1_axis(match.group("row"), origin[0])
    column, column_absolute = _resolve_r1c1_axis(
        match.group("column"), origin[1]
    )
    return CellReference(
        row=row,
        column=column,
        sheet=sheet,
        row_absolute=row_absolute,
        column_absolute=column_absolute,
    )


def _resolve_r1c1_axis(value: str | None, origin: int) -> tuple[int, bool]:
    if value is None or value == "":
        return origin, False
    if value.startswith("["):
        return origin + int(value[1:-1]), False
    return int(value) - 1, True


def _split_sheet_reference(text: str) -> tuple[str | None, str]:
    if not text:
        raise ValueError("Reference cannot be empty")
    if text.startswith("'"):
        position = 1
        characters: list[str] = []
        while position < len(text):
            if text[position] == "'":
                if position + 1 < len(text) and text[position + 1] == "'":
                    characters.append("'")
                    position += 2
                    continue
                if position + 1 < len(text) and text[position + 1] == "!":
                    coordinate = text[position + 2 :]
                    if not coordinate:
                        raise ValueError(f"Missing coordinate in reference: {text!r}")
                    return "".join(characters), coordinate
                raise ValueError(f"Invalid quoted sheet reference: {text!r}")
            characters.append(text[position])
            position += 1
        raise ValueError(f"Unterminated quoted sheet name: {text!r}")

    if "!" not in text:
        return None, text
    sheet, separator, coordinate = text.partition("!")
    if not separator or not sheet or not coordinate or "!" in coordinate:
        raise ValueError(f"Invalid sheet reference: {text!r}")
    return sheet, coordinate
