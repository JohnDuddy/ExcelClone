from __future__ import annotations

from openpyxl import load_workbook
from openpyxl.chart import BarChart, Reference

from excelclone.core.cell import BorderStyle, CellFormat
from excelclone.core.engine import FormulaEngine
from excelclone.core.refs import parse_a1
from excelclone.core.workbook import Workbook
from excelclone.io.xlsx_reader import read_xlsx
from excelclone.io.xlsx_writer import write_xlsx


def xlsx_workbook() -> Workbook:
    workbook = Workbook()
    sheet = workbook.active_sheet
    sheet.set_cell(
        0,
        0,
        1234.5,
        cell_format=CellFormat(
            number_format="#,##0.00",
            font_family="Cambria",
            font_size=14,
            bold=True,
            italic=True,
            underline=True,
            font_color="#123456",
            fill_color="#fedcba",
            horizontal_alignment="center",
            vertical_alignment="top",
            wrap_text=True,
            left_border=BorderStyle("thin", "#112233"),
            bottom_border=BorderStyle("double", "#445566"),
        ),
    )
    sheet.set_cell(0, 1, "=A1*2")
    sheet.set_cell(2, 2, "merged")
    sheet.merged_ranges.append(parse_a1("C3:D4"))
    sheet.row_heights[0] = 30
    sheet.column_widths[0] = 22
    sheet.hidden_rows.add(5)
    sheet.hidden_columns.add(6)
    sheet.freeze_panes = (1, 1)
    sheet.tab_color = "#33aa55"
    workbook.add_sheet("Data").set_cell(0, 0, "other")
    workbook.active_sheet = "Data"
    workbook.define_name("InputValue", "Sheet1!$A$1")
    return workbook


def test_xlsx_round_trip_preserves_supported_workbook_features(tmp_path) -> None:
    path = tmp_path / "roundtrip.xlsx"
    write_xlsx(xlsx_workbook(), path)

    result = read_xlsx(path)
    loaded = result.workbook
    FormulaEngine(loaded).recalculate()
    sheet = loaded.get_sheet("Sheet1")
    formatted = sheet.get_cell(0, 0).format

    assert result.warnings == ()
    assert loaded.sheet_names == ("Sheet1", "Data")
    assert loaded.active_sheet.name == "Data"
    assert sheet.get_cell(0, 0).display_value == 1234.5
    assert sheet.get_cell(0, 1).raw_input == "=A1*2"
    assert sheet.get_cell(0, 1).display_value == 2469
    assert formatted.number_format == "#,##0.00"
    assert formatted.font_family == "Cambria"
    assert formatted.font_size == 14
    assert formatted.bold and formatted.italic and formatted.underline
    assert formatted.font_color == "#123456"
    assert formatted.fill_color == "#fedcba"
    assert formatted.horizontal_alignment == "center"
    assert formatted.vertical_alignment == "top"
    assert formatted.wrap_text
    assert formatted.left_border == BorderStyle("thin", "#112233")
    assert formatted.bottom_border == BorderStyle("double", "#445566")
    assert sheet.merged_ranges == [parse_a1("C3:D4")]
    assert sheet.row_heights[0] == 30
    assert sheet.column_widths[0] == 22
    assert 5 in sheet.hidden_rows
    assert 6 in sheet.hidden_columns
    assert sheet.freeze_panes == (1, 1)
    assert sheet.tab_color == "#33aa55"
    assert loaded.get_name("InputValue").reference == parse_a1("Sheet1!$A$1")


def test_written_xlsx_reopens_with_openpyxl_and_requests_recalculation(tmp_path) -> None:
    path = tmp_path / "valid.xlsx"
    write_xlsx(xlsx_workbook(), path)

    package = load_workbook(path, data_only=False)

    assert package["Sheet1"]["B1"].value == "=A1*2"
    assert package.calculation.fullCalcOnLoad
    assert package.calculation.forceFullCalc
    package.close()


def test_xlsx_reader_returns_warnings_for_dropped_chart_content(tmp_path) -> None:
    path = tmp_path / "chart.xlsx"
    write_xlsx(xlsx_workbook(), path)
    package = load_workbook(path)
    chart = BarChart()
    chart.add_data(Reference(package["Sheet1"], min_col=1, min_row=1, max_row=1))
    package["Sheet1"].add_chart(chart, "F2")
    package.save(path)
    package.close()

    result = read_xlsx(path)

    assert any("chart" in warning.lower() for warning in result.warnings)
