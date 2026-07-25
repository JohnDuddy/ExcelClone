"""CSV and TSV import/export over one active worksheet."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from dateutil.parser import ParserError, parse as parse_datetime

from excelclone.core.engine import FormulaEngine
from excelclone.core.workbook import Workbook

_INTEGER_RE = re.compile(r"^[+-]?[0-9]+$")
_FLOAT_RE = re.compile(
    r"^[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+(?:\.[0-9]*)?[Ee][+-]?[0-9]+)$"
)


@dataclass(frozen=True, slots=True)
class DelimitedLoadResult:
    """Imported workbook and detected source settings."""

    workbook: Workbook
    delimiter: str
    encoding: str


def detect_delimiter(sample: str) -> str:
    """Detect a common field delimiter from a text sample."""
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
    except csv.Error:
        return "\t" if sample.count("\t") > sample.count(",") else ","


def read_delimited(
    path: str | Path,
    *,
    delimiter: str | None = None,
    encoding: str | None = None,
    parse_dates: bool = False,
) -> DelimitedLoadResult:
    """Import a delimited text file with encoding and scalar detection."""
    source = Path(path)
    selected_encoding, text = _read_text(source, encoding)
    selected_delimiter = delimiter or detect_delimiter(text[:8192])
    workbook = Workbook()
    sheet = workbook.active_sheet
    reader = csv.reader(text.splitlines(), delimiter=selected_delimiter)
    for row, values in enumerate(reader):
        for column, value in enumerate(values):
            parsed = _parse_scalar(value, parse_dates=parse_dates)
            if parsed != "":
                sheet.set_cell(row, column, parsed)
    FormulaEngine(workbook).recalculate()
    return DelimitedLoadResult(workbook, selected_delimiter, selected_encoding)


def write_delimited(
    workbook: Workbook,
    path: str | Path,
    *,
    delimiter: str | None = None,
    encoding: str = "utf-8-sig",
    formulas: bool = False,
) -> Path:
    """Export the active sheet's used rectangle as CSV or TSV."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    selected_delimiter = delimiter or (
        "\t" if destination.suffix.lower() == ".tsv" else ","
    )
    used_range = workbook.active_sheet.used_range
    with destination.open("w", encoding=encoding, newline="") as stream:
        writer = csv.writer(
            stream,
            delimiter=selected_delimiter,
            lineterminator="\r\n",
        )
        if used_range is not None:
            for row in range(used_range.min_row, used_range.max_row + 1):
                values: list[Any] = []
                for column in range(
                    used_range.min_column,
                    used_range.max_column + 1,
                ):
                    cell = workbook.active_sheet.get_cell(row, column)
                    value = (
                        cell.raw_input
                        if formulas and cell.is_formula
                        else cell.display_value
                    )
                    values.append("" if value is None else value)
                writer.writerow(values)
    return destination


def _read_text(path: Path, encoding: str | None) -> tuple[str, str]:
    if encoding is not None:
        return encoding, path.read_text(encoding=encoding)
    data = path.read_bytes()
    try:
        return "utf-8-sig", data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "cp1252", data.decode("cp1252")


def _parse_scalar(value: str, *, parse_dates: bool) -> Any:
    if value == "":
        return ""
    if value.startswith("="):
        return value
    upper = value.upper()
    if upper == "TRUE":
        return True
    if upper == "FALSE":
        return False
    if _INTEGER_RE.fullmatch(value):
        try:
            return int(value)
        except ValueError:
            return value
    if _FLOAT_RE.fullmatch(value):
        try:
            return float(value)
        except ValueError:
            return value
    if parse_dates:
        try:
            parsed = parse_datetime(value, fuzzy=False)
        except (ParserError, OverflowError):
            return value
        if any(separator in value for separator in ("/", "-", ".")):
            return date(parsed.year, parsed.month, parsed.day)
    return value
