from __future__ import annotations

from excelclone.commands.base import CommandHistory
from excelclone.commands.edits import (
    AddChartCommand,
    InsertRowsCommand,
    RemoveChartCommand,
    RenameSheetCommand,
)
from excelclone.core.chart import ChartSpec, chart_data
from excelclone.core.engine import FormulaEngine
from excelclone.core.refs import parse_a1
from excelclone.core.workbook import Workbook


def chart_workbook() -> Workbook:
    workbook = Workbook()
    sheet = workbook.active_sheet
    rows = (
        ("Month", "Revenue", "Cost"),
        ("Jan", 10, 6),
        ("Feb", 15, 8),
        ("Mar", 12, 7),
    )
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            sheet.set_cell(row, column, value)
    return workbook


def test_chart_data_detects_headers_categories_and_multiple_series() -> None:
    workbook = chart_workbook()
    spec = ChartSpec("sales", "Sheet1", parse_a1("A1:C4"), "column")

    data = chart_data(workbook, spec)

    assert data.categories == ("Jan", "Feb", "Mar")
    assert [series.name for series in data.series] == ["Revenue", "Cost"]
    assert data.series[0].values == (10.0, 15.0, 12.0)
    assert data.series[1].values == (6.0, 8.0, 7.0)


def test_chart_data_live_binding_observes_recalculated_values() -> None:
    workbook = chart_workbook()
    engine = FormulaEngine(workbook)
    engine.set_cell("Sheet1", 1, 1, "=10*2")
    spec = ChartSpec("sales", "Sheet1", parse_a1("A1:B4"), "line")

    before = chart_data(workbook, spec)
    engine.set_cell("Sheet1", 1, 1, "=10*3")
    after = chart_data(workbook, spec)

    assert before.series[0].values[0] == 20
    assert after.series[0].values[0] == 30


def test_chart_data_supports_no_header_and_explicit_series_columns() -> None:
    workbook = Workbook()
    sheet = workbook.active_sheet
    for row, values in enumerate(((1, 2, 3), (2, 4, 6), (3, 6, 9))):
        for column, value in enumerate(values):
            sheet.set_cell(row, column, value)
    spec = ChartSpec(
        "scatter",
        "Sheet1",
        parse_a1("A1:C3"),
        "scatter",
        has_headers=False,
        category_column=0,
        series_columns=(2,),
    )

    data = chart_data(workbook, spec)

    assert data.categories == (1, 2, 3)
    assert data.series[0].name == "Series 1"
    assert data.series[0].values == (3.0, 6.0, 9.0)


def test_chart_add_remove_commands_are_undoable() -> None:
    workbook = chart_workbook()
    engine = FormulaEngine(workbook)
    history = CommandHistory()
    spec = ChartSpec("sales", "Sheet1", parse_a1("A1:C4"), "combo")

    history.execute(AddChartCommand(engine, "Sheet1", spec))
    assert workbook.active_sheet.charts == [spec]
    history.execute(RemoveChartCommand(engine, "Sheet1", "sales"))
    assert workbook.active_sheet.charts == []
    history.undo()
    assert workbook.active_sheet.charts == [spec]
    history.undo()
    assert workbook.active_sheet.charts == []


def test_chart_binding_translates_with_structural_edit_and_sheet_rename() -> None:
    workbook = chart_workbook()
    engine = FormulaEngine(workbook)
    workbook.active_sheet.charts.append(
        ChartSpec("sales", "Sheet1", parse_a1("A1:C4"), "line")
    )

    InsertRowsCommand(engine, "Sheet1", 2, 1).do()
    assert workbook.active_sheet.charts[0].source_range.to_a1() == "A1:C5"
    RenameSheetCommand(engine, "Sheet1", "Data").do()
    assert workbook.active_sheet.charts[0].sheet_name == "Data"
