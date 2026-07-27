"""Workbook persistence adapters."""

from duddysheet.io.csv_io import read_delimited, write_delimited
from duddysheet.io.native import load_native, save_native
from duddysheet.io.xlsx_reader import read_xlsx
from duddysheet.io.xlsx_writer import write_xlsx

__all__ = [
    "load_native",
    "read_delimited",
    "read_xlsx",
    "save_native",
    "write_delimited",
    "write_xlsx",
]
