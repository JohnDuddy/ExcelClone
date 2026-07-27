from __future__ import annotations

import math
from datetime import date

from duddysheet.commands.base import CommandHistory
from duddysheet.commands.edits import (
    AddChartCommand,
    InsertRowsCommand,
    RemoveChartCommand,
    RenameSheetCommand,
    UpdateChartCommand,
)
from duddysheet.core.chart import (
    ChartSpec,
    chart_data,
    detect_chart_headers,
    expand_chart_range,
    recommend_charts,
)
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.refs import parse_a1
from duddysheet.core.workbook import Workbook


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


def test_single_cell_chart_selection_expands_to_contiguous_data_only() -> None:
    workbook = chart_workbook()
    workbook.active_sheet.set_cell(10, 10, "unrelated")

    expanded = expand_chart_range(
        workbook,
        "Sheet1",
        parse_a1("B2:B2"),
    )

    assert expanded.to_a1() == "A1:C4"


def test_chart_recommendations_are_ranked_by_data_shape() -> None:
    numeric = Workbook()
    for row, values in enumerate(((1, 2, 4), (2, 4, 8), (3, 6, 12))):
        for column, value in enumerate(values):
            numeric.active_sheet.set_cell(row, column, value)
    numeric_types = [
        item.chart_type
        for item in recommend_charts(
            numeric,
            "Sheet1",
            parse_a1("A1:C3"),
            has_headers=False,
        )
    ]

    dated = Workbook()
    for row, values in enumerate(
        (
            ("Date", "Revenue"),
            (date(2026, 1, 1), 10),
            (date(2026, 2, 1), 12),
            (date(2026, 3, 1), 15),
        )
    ):
        for column, value in enumerate(values):
            dated.active_sheet.set_cell(row, column, value)
    dated_types = [
        item.chart_type
        for item in recommend_charts(
            dated,
            "Sheet1",
            parse_a1("A1:B4"),
        )
    ]

    assert numeric_types[0] == "scatter"
    assert dated_types[0] == "line"
    assert detect_chart_headers(dated, "Sheet1", parse_a1("A1:B4"))
    assert not detect_chart_headers(numeric, "Sheet1", parse_a1("A1:C3"))


def test_waterfall_and_heatmap_recommendations_cover_analytical_shapes() -> None:
    bridge = Workbook()
    for row, values in enumerate(
        (("Stage", "Change"), ("Start", 100), ("Cost", -35), ("Growth", 20))
    ):
        for column, value in enumerate(values):
            bridge.active_sheet.set_cell(row, column, value)
    dense = Workbook()
    for row in range(6):
        for column in range(6):
            dense.active_sheet.set_cell(
                row,
                column,
                f"H{column}" if row == 0 else row * (column + 1),
            )

    bridge_choice = recommend_charts(
        bridge,
        "Sheet1",
        parse_a1("A1:B4"),
    )[0]
    dense_choice = recommend_charts(
        dense,
        "Sheet1",
        parse_a1("A1:F6"),
    )[0]

    assert bridge_choice.chart_type == "waterfall"
    assert dense_choice.chart_type == "heatmap"


def test_chart_missing_values_remain_gaps_instead_of_becoming_zero() -> None:
    workbook = chart_workbook()
    workbook.active_sheet.set_cell(2, 1, "not available")
    spec = ChartSpec("gaps", "Sheet1", parse_a1("A1:B4"), "line")

    data = chart_data(workbook, spec)

    assert math.isnan(data.series[0].values[1])


def test_chart_updates_are_undoable() -> None:
    workbook = chart_workbook()
    engine = FormulaEngine(workbook)
    history = CommandHistory()
    original = ChartSpec("sales", "Sheet1", parse_a1("A1:C4"), "column")
    updated = ChartSpec(
        "sales",
        "Sheet1",
        parse_a1("A1:C4"),
        "heatmap",
        theme="editorial",
        show_data_labels=True,
    )

    history.execute(AddChartCommand(engine, "Sheet1", original))
    history.execute(UpdateChartCommand(engine, "Sheet1", updated))
    assert workbook.active_sheet.charts == [updated]
    history.undo()
    assert workbook.active_sheet.charts == [original]
