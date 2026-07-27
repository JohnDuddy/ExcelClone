from __future__ import annotations

from datetime import date

import pytest

from duddysheet.core.cell import Cell, CellFormat
from duddysheet.core.refs import MAX_COLUMNS, MAX_ROWS
from duddysheet.core.sheet import Sheet


def test_default_cell_has_no_content_or_format() -> None:
    cell = Cell()

    assert cell.raw_input is None
    assert cell.cached_value is None
    assert cell.format == CellFormat()
    assert cell.error is None
    assert cell.is_empty
    assert not cell.is_formula


@pytest.mark.parametrize(
    ("raw_input", "is_formula"),
    [
        ("=SUM(A1:A3)", True),
        ("=", True),
        (" =SUM(A1:A3)", False),
        (12.5, False),
        (date(2026, 7, 25), False),
    ],
)
def test_cell_identifies_formula_input(raw_input: object, is_formula: bool) -> None:
    assert Cell(raw_input=raw_input).is_formula is is_formula


def test_cell_display_prefers_errors_then_cache_then_raw_input() -> None:
    assert Cell(raw_input="=1/0", cached_value=10, error="#DIV/0!").display_value == "#DIV/0!"
    assert Cell(raw_input="=2+3", cached_value=5).display_value == 5
    assert Cell(raw_input="plain").display_value == "plain"


def test_reading_blank_sheet_does_not_allocate_cells() -> None:
    sheet = Sheet("Sheet1")

    assert sheet.get_cell(999_999, 10_000).is_empty
    assert sheet.populated_count == 0
    assert list(sheet.iter_populated()) == []


def test_setting_and_clearing_values_preserves_sparse_storage() -> None:
    sheet = Sheet("Sheet1")

    sheet.set_cell(4, 2, "hello")
    sheet.set_cell(7, 9, 42)

    assert sheet.get_cell(4, 2).cached_value == "hello"
    assert sheet.get_cell(7, 9).display_value == 42
    assert sheet.populated_count == 2

    sheet.clear_cell(4, 2)
    assert sheet.get_cell(4, 2).is_empty
    assert sheet.populated_count == 1


def test_non_default_format_keeps_an_otherwise_blank_cell() -> None:
    sheet = Sheet("Sheet1")
    cell_format = CellFormat(number_format="0.00", bold=True)

    sheet.set_cell(1, 1, None, cell_format=cell_format)

    assert sheet.populated_count == 1
    assert sheet.get_cell(1, 1).format == cell_format


def test_replacing_with_empty_default_cell_deallocates_coordinate() -> None:
    sheet = Sheet("Sheet1")
    sheet.set_cell(1, 1, "value")

    previous = sheet.put_cell(1, 1, Cell())

    assert previous.raw_input == "value"
    assert sheet.populated_count == 0


def test_used_range_tracks_minimum_bounding_rectangle() -> None:
    sheet = Sheet("Sheet1")
    sheet.set_cell(10, 8, "lower-right")
    sheet.set_cell(2, 3, "upper-left")
    sheet.set_cell(7, 12, "right")

    used_range = sheet.used_range

    assert used_range is not None
    assert (used_range.min_row, used_range.min_column) == (2, 3)
    assert (used_range.max_row, used_range.max_column) == (10, 12)
    assert Sheet("Blank").used_range is None


def test_iter_populated_is_stable_row_major_order() -> None:
    sheet = Sheet("Sheet1")
    sheet.set_cell(3, 0, "C")
    sheet.set_cell(1, 5, "B")
    sheet.set_cell(1, 2, "A")

    items = list(sheet.iter_populated())

    assert [(coordinate, cell.raw_input) for coordinate, cell in items] == [
        ((1, 2), "A"),
        ((1, 5), "B"),
        ((3, 0), "C"),
    ]


@pytest.mark.parametrize(
    ("row", "column"),
    [
        (-1, 0),
        (0, -1),
        (MAX_ROWS, 0),
        (0, MAX_COLUMNS),
        (MAX_ROWS + 10, MAX_COLUMNS + 10),
    ],
)
def test_sheet_rejects_out_of_bounds_coordinates(row: int, column: int) -> None:
    sheet = Sheet("Sheet1")

    with pytest.raises(IndexError):
        sheet.get_cell(row, column)
    with pytest.raises(IndexError):
        sheet.set_cell(row, column, "value")


def test_sheet_copy_is_independent() -> None:
    original = Sheet("Original")
    original.set_cell(0, 0, "source")

    duplicate = original.copy(name="Copy")
    duplicate.set_cell(0, 0, "changed")

    assert original.name == "Original"
    assert original.get_cell(0, 0).raw_input == "source"
    assert duplicate.name == "Copy"
    assert duplicate.get_cell(0, 0).raw_input == "changed"
