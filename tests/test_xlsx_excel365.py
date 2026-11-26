"""XLSX interoperability with Excel 365: function prefixes and dynamic arrays."""

from __future__ import annotations

import re
import zipfile

import openpyxl
import pytest
from openpyxl.worksheet.formula import ArrayFormula

from duddysheet.core.engine import FormulaEngine
from duddysheet.core.workbook import Workbook
from duddysheet.io.formula_compat import from_xlsx_formula, to_xlsx_formula
from duddysheet.io.xlsx_reader import read_xlsx
from duddysheet.io.xlsx_writer import write_xlsx


@pytest.mark.parametrize(
    ("native", "stored"),
    [
        ("=XLOOKUP(A1,B:B,C:C)", "=_xlfn.XLOOKUP(A1,B:B,C:C)"),
        ("=FILTER(A1:A5,A1:A5>2)", "=_xlfn._xlws.FILTER(A1:A5,A1:A5>2)"),
        ("=SORT(A1:A5)", "=_xlfn._xlws.SORT(A1:A5)"),
        ("=SUM(A1#)", "=SUM(_xlfn.ANCHORARRAY(A1))"),
        ("=@A1:A5", "=_xlfn.SINGLE(A1:A5)"),
        ("=LET(x,2,y,x*3,x+y)", "=_xlfn.LET(_xlpm.x,2,_xlpm.y,_xlpm.x*3,_xlpm.x+_xlpm.y)"),
        ("=LAMBDA(a,b,a+b)(1,2)", "=_xlfn.LAMBDA(_xlpm.a,_xlpm.b,_xlpm.a+_xlpm.b)(1,2)"),
        ("=TEXTJOIN(\",\",TRUE,A1:A3)", "=_xlfn.TEXTJOIN(\",\",TRUE,A1:A3)"),
        ("=IFS(A1>1,1,TRUE,2)", "=_xlfn.IFS(A1>1,1,TRUE,2)"),
        ("=STDEV.S(A1:A5)", "=_xlfn.STDEV.S(A1:A5)"),
        ("=SUM(A1:A5)*(1+B1)", "=SUM(A1:A5)*(1+B1)"),
        ('="_xlfn."&A1', '="_xlfn."&A1'),
    ],
)
def test_formulas_use_excel_storage_spellings(native: str, stored: str) -> None:
    assert to_xlsx_formula(native) == stored
    assert from_xlsx_formula(stored) == native


def test_spilled_formulas_round_trip_as_dynamic_arrays(tmp_path) -> None:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    for row in range(4):
        engine.set_cell("Sheet1", row, 0, row + 1)
    engine.set_cell("Sheet1", 0, 2, "=SEQUENCE(3)")
    engine.set_cell("Sheet1", 0, 3, "=SUM(C1#)")
    engine.set_cell("Sheet1", 0, 4, "=FILTER(A1:A4,A1:A4>1)")
    path = tmp_path / "dynamic.xlsx"

    write_xlsx(workbook, path)

    with zipfile.ZipFile(path) as archive:
        sheet_xml = archive.read("xl/worksheets/sheet1.xml").decode()
        assert "xl/metadata.xml" in archive.namelist()
        assert "sheetMetadata" in archive.read("xl/_rels/workbook.xml.rels").decode()
    assert re.search(r'<c r="C1" cm="1"><f t="array" ref="C1:C3">', sheet_xml)
    assert '<c r="C2"' not in sheet_xml  # spilled values are regenerated
    reopened = read_xlsx(path).workbook.active_sheet
    assert reopened.get_cell(0, 2).raw_input == "=SEQUENCE(3)"
    assert [reopened.get_cell(row, 2).display_value for row in range(3)] == [1, 2, 3]
    assert reopened.get_cell(0, 3).raw_input == "=SUM(C1#)"
    assert reopened.get_cell(0, 3).display_value == 6
    assert [reopened.get_cell(row, 4).display_value for row in range(3)] == [2, 3, 4]


def test_excel_saved_spill_caches_do_not_block_the_spill(tmp_path) -> None:
    package = openpyxl.Workbook()
    sheet = package.active
    sheet["B2"] = ArrayFormula("B2:B4", "=_xlfn.SEQUENCE(3)")
    # Excel writes the spilled results as plain cached values.
    sheet["B3"] = 2
    sheet["B4"] = 3
    path = tmp_path / "from_excel.xlsx"
    package.save(path)

    reopened = read_xlsx(path).workbook.active_sheet

    assert reopened.get_cell(1, 1).raw_input == "=SEQUENCE(3)"
    assert reopened.get_cell(2, 1).is_spill
    assert reopened.get_cell(3, 1).display_value == 3
    assert reopened.get_cell(1, 1).error is None


def test_named_formulas_round_trip(tmp_path) -> None:
    workbook = Workbook()
    workbook.define_name("TaxRate", "=0.07", comment="Sales tax")
    workbook.define_name("Double", "=LAMBDA(n,n*2)")
    path = tmp_path / "names.xlsx"

    write_xlsx(workbook, path)
    reopened = read_xlsx(path).workbook

    assert reopened.get_name("TaxRate").refers_to == "=0.07"
    assert reopened.get_name("TaxRate").comment == "Sales tax"
    assert reopened.get_name("Double").refers_to == "=LAMBDA(n,n*2)"
