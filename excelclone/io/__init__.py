"""Workbook persistence adapters."""

from excelclone.io.csv_io import read_delimited, write_delimited
from excelclone.io.native import load_ogrid, save_ogrid
from excelclone.io.xlsx_reader import read_xlsx
from excelclone.io.xlsx_writer import write_xlsx

__all__ = [
    "load_ogrid",
    "read_delimited",
    "read_xlsx",
    "save_ogrid",
    "write_delimited",
    "write_xlsx",
]
