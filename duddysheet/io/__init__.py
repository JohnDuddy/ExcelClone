"""Workbook persistence adapters.

The XLSX adapters import openpyxl, which costs about half a second, so they
load on first use rather than at application start.
"""

from typing import Any

from duddysheet.io.csv_io import read_delimited, write_delimited
from duddysheet.io.native import load_native, save_native

__all__ = [
    "load_native",
    "read_delimited",
    "read_xlsx",
    "save_native",
    "write_delimited",
    "write_xlsx",
]


def __getattr__(name: str) -> Any:
    """Resolve the openpyxl-backed adapters lazily."""
    if name == "read_xlsx":
        from duddysheet.io.xlsx_reader import read_xlsx

        return read_xlsx
    if name == "write_xlsx":
        from duddysheet.io.xlsx_writer import write_xlsx

        return write_xlsx
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
