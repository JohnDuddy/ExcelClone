"""Excel Tables: creation, structured references, calculated columns, totals, and files."""

from __future__ import annotations

import pytest

from duddysheet.commands.analysis import CreateTableCommand, TableEntryCommand, rename_table
from duddysheet.commands.base import CommandHistory
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.errors import REF_ERROR
from duddysheet.core.tables import (
    convert_to_range,
    create_table,
    find_table,
    resize_table,
    set_totals_row,
    structured_to_a1,
    table_at,
)
from duddysheet.core.workbook import Workbook
from duddysheet.io.native import load_native, save_native
from duddysheet.io.xlsx_reader import read_xlsx
from duddysheet.io.xlsx_writer import write_xlsx


def _products() -> tuple[Workbook, FormulaEngine]:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    for row, values in enumerate((("Product", "Qty", "Price"), ("Apple", 3, 1.5), ("Pear", 2, 2.0), ("Kiwi", 5, 0.5))):
        for column, value in enumerate(values):
            engine.set_cell("Sheet1", row, column, value)
    return workbook, engine


def _value(workbook: Workbook, row: int, column: int, sheet: str = "Sheet1") -> object:
    cell = workbook.get_sheet(sheet).get_cell(row, column)
    return cell.error or cell.display_value


def _table() -> tuple[Workbook, FormulaEngine, CommandHistory]:
    workbook, engine = _products()
    history = CommandHistory()
    history.execute(CreateTableCommand(engine, "Sheet1", (0, 0, 3, 2)))
    return workbook, engine, history


def test_create_table_names_it_and_reads_headers() -> None:
    workbook, _, history = _table()
    table = table_at(workbook.get_sheet("Sheet1"), 2, 1)
    assert table is not None
    assert table.name == "Table1"
    assert table.columns == ("Product", "Qty", "Price")
    assert table.style == "TableStyleMedium2"
    history.undo()
    assert workbook.get_sheet("Sheet1").tables == []


def test_create_table_without_headers_inserts_column_names() -> None:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    engine.set_cell("Sheet1", 0, 0, 1)
    engine.set_cell("Sheet1", 1, 0, 2)
    table = create_table(workbook, "Sheet1", (0, 0, 1, 0), has_headers=False)
    assert table.columns == ("Column1",)
    assert (table.top, table.bottom) == (0, 2)
    assert _value(workbook, 0, 0) == "Column1"
    assert _value(workbook, 1, 0) == 1


def test_tables_cannot_overlap_and_names_must_be_valid() -> None:
    workbook, _, _ = _table()
    with pytest.raises(ValueError):
        create_table(workbook, "Sheet1", (2, 1, 5, 4))
    with pytest.raises(ValueError):
        create_table(workbook, "Sheet1", (10, 0, 12, 1), name="A1")
    with pytest.raises(ValueError):
        create_table(workbook, "Sheet1", (10, 0, 12, 1), name="table1")


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=SUM(Table1[Qty])", 10),
        ("=ROWS(Table1)", 3),
        ("=ROWS(Table1[#All])", 4),
        ("=COLUMNS(Table1[[Qty]:[Price]])", 2),
        ("=Table1[[#Headers],[Price]]", "Price"),
        ("=SUMPRODUCT(Table1[Qty],Table1[Price])", 11.0),
        ('=XLOOKUP("Pear",Table1[Product],Table1[Price])', 2.0),
        ("=SUM(table1[qty])", 10),
        ("=SUM(Table9[Qty])", REF_ERROR.literal),
        ("=SUM(Table1[Missing])", REF_ERROR.literal),
    ],
)
def test_structured_references_resolve(formula: str, expected: object) -> None:
    workbook, engine, _ = _table()
    engine.set_cell("Sheet1", 10, 0, formula)
    assert _value(workbook, 10, 0) == expected


def test_this_row_reference_and_calculated_column_fill() -> None:
    workbook, engine, history = _table()
    history.execute(TableEntryCommand(engine, "Sheet1", 0, 3, "Amount"))
    table = table_at(workbook.get_sheet("Sheet1"), 0, 3)
    assert table is not None and table.columns[-1] == "Amount"
    history.execute(TableEntryCommand(engine, "Sheet1", 1, 3, "=[@Qty]*[@Price]"))
    assert [_value(workbook, row, 3) for row in (1, 2, 3)] == [4.5, 4.0, 2.5]
    # A new row typed below the table joins it and receives the formula.
    history.execute(TableEntryCommand(engine, "Sheet1", 4, 0, "Fig"))
    history.execute(TableEntryCommand(engine, "Sheet1", 4, 1, 4))
    history.execute(TableEntryCommand(engine, "Sheet1", 4, 2, 3))
    assert table_at(workbook.get_sheet("Sheet1"), 4, 0) is not None
    assert _value(workbook, 4, 3) == 12
    engine.set_cell("Sheet1", 10, 0, "=SUM(Table1[Amount])")
    assert _value(workbook, 10, 0) == 23
    history.undo()
    history.undo()
    history.undo()
    assert table_at(workbook.get_sheet("Sheet1"), 4, 0) is None


def test_formula_in_a_filled_column_is_not_a_calculated_column() -> None:
    workbook, engine, history = _table()
    history.execute(TableEntryCommand(engine, "Sheet1", 1, 1, "=10"))
    assert _value(workbook, 2, 1) == 2
    assert table_at(workbook.get_sheet("Sheet1"), 0, 0).calculated == ()


def test_total_row_uses_subtotal_and_can_be_removed() -> None:
    workbook, engine, _ = _table()
    sheet = workbook.get_sheet("Sheet1")
    table = set_totals_row(workbook, "Sheet1", table_at(sheet, 0, 0), True)
    engine.rebuild_index()
    assert table.totals_row == 4
    assert sheet.get_cell(4, 2).raw_input == "=SUBTOTAL(109,[Price])"
    assert _value(workbook, 4, 0) == "Total"
    assert _value(workbook, 4, 2) == 4.0
    engine.set_cell("Sheet1", 10, 0, "=Table1[#Totals]")
    assert _value(workbook, 10, 0) == "Total"
    table = set_totals_row(workbook, "Sheet1", table, False)
    assert table.totals_row is None and sheet.get_cell(4, 2).raw_input is None


def test_inserting_rows_inside_a_table_grows_it() -> None:
    from duddysheet.commands.edits import InsertRowsCommand

    workbook, engine, history = _table()
    history.execute(TableEntryCommand(engine, "Sheet1", 0, 3, "Amount"))
    history.execute(TableEntryCommand(engine, "Sheet1", 1, 3, "=[@Qty]*[@Price]"))
    history.execute(InsertRowsCommand(engine, "Sheet1", 2, 1))
    table = table_at(workbook.get_sheet("Sheet1"), 0, 0)
    assert table.bottom == 4
    assert workbook.get_sheet("Sheet1").get_cell(2, 3).raw_input == "=[@Qty]*[@Price]"


def test_resize_and_rename_update_formulas() -> None:
    workbook, engine, _ = _table()
    engine.set_cell("Sheet1", 10, 0, "=SUM(Table1[Qty])")
    rename_table(workbook, "Table1", "Fruit")
    engine.rebuild_index()
    assert workbook.get_sheet("Sheet1").get_cell(10, 0).raw_input == "=SUM(Fruit[Qty])"
    assert _value(workbook, 10, 0) == 10
    sheet = workbook.get_sheet("Sheet1")
    resize_table(sheet, find_table(workbook, "Fruit")[1], (0, 0, 2, 2))
    engine.rebuild_index()
    assert _value(workbook, 10, 0) == 5
    with pytest.raises(ValueError):
        resize_table(sheet, find_table(workbook, "Fruit")[1], (1, 0, 2, 2))


def test_convert_to_range_rewrites_structured_references() -> None:
    workbook, engine, history = _table()
    history.execute(TableEntryCommand(engine, "Sheet1", 0, 3, "Amount"))
    history.execute(TableEntryCommand(engine, "Sheet1", 1, 3, "=[@Qty]*[@Price]"))
    engine.set_cell("Sheet1", 10, 0, "=SUM(Table1[Qty])")
    sheet = workbook.get_sheet("Sheet1")
    structured_to_a1(workbook, "Table1")
    convert_to_range(sheet, table_at(sheet, 0, 0))
    engine.rebuild_index()
    assert sheet.tables == []
    assert sheet.get_cell(10, 0).raw_input == "=SUM($B$2:$B$4)"
    assert sheet.get_cell(2, 3).raw_input == "=$B3*$C3"
    assert _value(workbook, 2, 3) == 4.0
    assert sheet.get_cell(0, 0).format.bold


def test_tables_round_trip_through_native_and_xlsx(tmp_path) -> None:
    workbook, engine, history = _table()
    history.execute(TableEntryCommand(engine, "Sheet1", 0, 3, "Amount"))
    history.execute(TableEntryCommand(engine, "Sheet1", 1, 3, "=[@Qty]*[@Price]"))
    sheet = workbook.get_sheet("Sheet1")
    set_totals_row(workbook, "Sheet1", table_at(sheet, 0, 0), True)
    engine.set_cell("Sheet1", 10, 0, "=SUM(Table1[Amount])")
    for loader, path in (
        (load_native, save_native(workbook, tmp_path / "t.dsheet")),
        (lambda p: read_xlsx(p).workbook, write_xlsx(workbook, tmp_path / "t.xlsx")),
    ):
        loaded = loader(path)
        FormulaEngine(loaded)
        table = table_at(loaded.get_sheet("Sheet1"), 1, 1)
        assert table is not None and table.name == "Table1"
        assert table.columns == ("Product", "Qty", "Price", "Amount")
        assert table.show_totals and table.totals_row == 4
        assert _value(loaded, 10, 0, "Sheet1") == 11.0
        assert _value(loaded, 2, 3, "Sheet1") == 4.0


def test_xlsx_writes_qualified_structured_references(tmp_path) -> None:
    import openpyxl

    workbook, engine, history = _table()
    history.execute(TableEntryCommand(engine, "Sheet1", 0, 3, "Amount"))
    history.execute(TableEntryCommand(engine, "Sheet1", 1, 3, "=[@Qty]*[@Price]"))
    path = write_xlsx(workbook, tmp_path / "q.xlsx")
    worksheet = openpyxl.load_workbook(path).active
    assert worksheet["D2"].value == "=Table1[[#This Row],[Qty]]*Table1[[#This Row],[Price]]"
    assert "Table1" in worksheet.tables
