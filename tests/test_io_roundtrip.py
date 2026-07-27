from __future__ import annotations

from openpyxl import Workbook as OpenPyxlWorkbook, load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Border, Side

from duddysheet.core.cell import BorderStyle, CellFormat
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.data_tools import DataValidation, apply_filter
from duddysheet.core.refs import parse_a1
from duddysheet.core.workbook import Workbook
from duddysheet.io.xlsx_reader import read_xlsx
from duddysheet.io.xlsx_writer import write_xlsx


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
    sheet.data_validations.append(
        DataValidation(
            parse_a1("A1:A10"),
            "decimal",
            "greater_than",
            (0,),
        )
    )
    apply_filter(
        sheet,
        parse_a1("A1:A10"),
        column=0,
        allowed_values={1234.5},
        has_header=False,
    )
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
    assert sheet.data_validations == [
        DataValidation(
            parse_a1("A1:A10"),
            "decimal",
            "greater_than",
            (0,),
        )
    ]
    assert sheet.auto_filter is not None
    assert sheet.auto_filter.allowed_values == frozenset({1234.5})


def test_written_xlsx_reopens_with_openpyxl_and_requests_recalculation(tmp_path) -> None:
    path = tmp_path / "valid.xlsx"
    write_xlsx(xlsx_workbook(), path)

    package = load_workbook(path, data_only=False)

    assert package["Sheet1"]["B1"].value == "=A1*2"
    assert package.calculation.fullCalcOnLoad
    assert package.calculation.forceFullCalc
    package.close()


def test_xlsx_translates_future_function_prefixes_without_changing_text(tmp_path) -> None:
    path = tmp_path / "future-functions.xlsx"
    workbook = Workbook()
    sheet = workbook.active_sheet
    sheet.set_cell(0, 0, '=RRI(10,100,200)&" RRI(""text"")"')
    sheet.set_cell(1, 0, "=PDURATION(0.08,100,200)")

    write_xlsx(workbook, path)
    package = load_workbook(path, data_only=False)

    assert package.active["A1"].value == (
        '=_xlfn.RRI(10,100,200)&" RRI(""text"")"'
    )
    assert package.active["A2"].value == "=_xlfn.PDURATION(0.08,100,200)"
    package.close()

    loaded = read_xlsx(path).workbook.active_sheet
    assert loaded.get_cell(0, 0).raw_input == '=RRI(10,100,200)&" RRI(""text"")"'
    assert loaded.get_cell(1, 0).raw_input == "=PDURATION(0.08,100,200)"
    assert loaded.get_cell(1, 0).display_value > 0


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


def test_xlsx_reader_accepts_missing_individual_border_sides(tmp_path) -> None:
    path = tmp_path / "missing-border-side.xlsx"
    package = OpenPyxlWorkbook()
    cell = package.active["A1"]
    cell.value = "partial border"
    cell.border = Border(right=Side(style="thin", color="FF123456"))
    package.save(path)
    package.close()

    result = read_xlsx(path)
    cell_format = result.workbook.active_sheet.get_cell(0, 0).format

    assert cell_format.left_border == BorderStyle()
    assert cell_format.right_border == BorderStyle("thin", "#123456")
