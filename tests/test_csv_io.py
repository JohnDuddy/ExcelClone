from __future__ import annotations

from datetime import date

from duddysheet.core.workbook import Workbook
from duddysheet.io.csv_io import detect_delimiter, read_delimited, write_delimited


def test_detect_delimiter_handles_csv_tsv_and_semicolon_samples() -> None:
    assert detect_delimiter("a,b\n1,2\n") == ","
    assert detect_delimiter("a\tb\n1\t2\n") == "\t"
    assert detect_delimiter("a;b\n1;2\n") == ";"


def test_csv_round_trip_quotes_fields_and_preserves_formula_input(tmp_path) -> None:
    path = tmp_path / "values.csv"
    workbook = Workbook()
    sheet = workbook.active_sheet
    sheet.set_cell(0, 0, "comma,value")
    sheet.set_cell(0, 1, 2)
    sheet.set_cell(1, 0, "=B1*3")

    write_delimited(workbook, path, formulas=True)
    result = read_delimited(path)

    assert result.delimiter == ","
    assert result.encoding == "utf-8-sig"
    assert result.workbook.active_sheet.get_cell(0, 0).raw_input == "comma,value"
    assert result.workbook.active_sheet.get_cell(0, 1).raw_input == 2
    assert result.workbook.active_sheet.get_cell(1, 0).raw_input == "=B1*3"


def test_tsv_import_detects_types_dates_and_cp1252_encoding(tmp_path) -> None:
    path = tmp_path / "legacy.tsv"
    path.write_bytes("TRUE\t12\t3.5\t7/25/2026\tcaf\xe9\r\n".encode("latin-1"))

    result = read_delimited(path, parse_dates=True)
    sheet = result.workbook.active_sheet

    assert result.delimiter == "\t"
    assert result.encoding == "cp1252"
    assert sheet.get_cell(0, 0).raw_input is True
    assert sheet.get_cell(0, 1).raw_input == 12
    assert sheet.get_cell(0, 2).raw_input == 3.5
    assert sheet.get_cell(0, 3).raw_input == date(2026, 7, 25)
    assert sheet.get_cell(0, 4).raw_input == "café"


def test_delimited_export_defaults_to_calculated_values(tmp_path) -> None:
    path = tmp_path / "values.tsv"
    workbook = Workbook()
    sheet = workbook.active_sheet
    sheet.set_cell(0, 0, 2)
    sheet.set_cell(0, 1, "=A1*4", cached_value=8)

    write_delimited(workbook, path)

    assert path.read_bytes().decode("utf-8-sig") == "2\t8\r\n"
