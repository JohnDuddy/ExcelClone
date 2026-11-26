"""PivotTables: layouts, summaries, filters, grouping, refresh, GETPIVOTDATA, and files."""

from __future__ import annotations

from datetime import date

import pytest

from duddysheet.commands.analysis import WorkbookMutationCommand, add_pivot, delete_pivot, refresh_pivots, update_pivot
from duddysheet.commands.base import CommandHistory
from duddysheet.core.cell import CellFormat
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.pivot import (
    PivotSpec,
    PivotValueField,
    compute_pivot,
    details_at,
    field_items,
    pivot_at,
    summarize,
)
from duddysheet.core.tables import create_table
from duddysheet.core.workbook import Workbook
from duddysheet.io.native import load_native, save_native

ROWS = (
    ("Region", "Product", "Date", "Sales", "Units"),
    ("East", "Apple", date(2024, 1, 5), 100, 10),
    ("East", "Pear", date(2024, 2, 7), 50, 5),
    ("West", "Apple", date(2025, 3, 9), 70, 7),
    ("West", "Apple", date(2024, 4, 1), 30, 3),
    ("East", "Apple", date(2025, 5, 2), 20, 2),
    ("West", "Kiwi", date(2025, 6, 3), 40, 4),
)


def _workbook() -> tuple[Workbook, FormulaEngine]:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    sheet = workbook.active_sheet
    for row, values in enumerate(ROWS):
        for column, value in enumerate(values):
            sheet.set_cell(row, column, value)
    workbook.add_sheet("Pivot")
    engine.rebuild_index()
    return workbook, engine


def _spec(**changes: object) -> PivotSpec:
    base = {"rows": ("Region",), "values": (PivotValueField("Sales"),)}
    base.update(changes)
    return PivotSpec("PivotTable1", "Sheet1", (0, 0, 6, 4), (2, 0), **base)


def _grid(workbook: Workbook, spec: PivotSpec) -> list[list[object]]:
    result = compute_pivot(workbook, spec)
    return [
        [None if (cell := result.cells.get((row, column))) is None else cell.value for column in range(result.width)]
        for row in range(result.height)
    ]


def test_one_row_field_sums_values_with_grand_total() -> None:
    workbook, _ = _workbook()
    assert _grid(workbook, _spec()) == [
        ["Row Labels", "Sum of Sales"],
        ["East", 170],
        ["West", 140],
        ["Grand Total", 310],
    ]


def test_rows_and_grouped_date_columns_in_compact_form() -> None:
    workbook, _ = _workbook()
    grid = _grid(workbook, _spec(rows=("Region", "Product"), columns=("Date",), grouping=(("Date", "years"),)))
    assert grid[0][:2] == ["Sum of Sales", "Column Labels"]
    assert grid[1] == ["Row Labels", 2024, 2025, "Grand Total"]
    assert grid[2] == ["East", 150, 20, 170]
    assert grid[3] == ["Apple", 100, 20, 120]
    assert grid[4] == ["Pear", 50, None, 50]
    assert grid[-1] == ["Grand Total", 180, 130, 310]
    result = compute_pivot(workbook, _spec(rows=("Region", "Product")))
    assert result.cells[(2, 0)].indent == 1


def test_tabular_form_has_a_column_per_field_and_total_rows() -> None:
    workbook, _ = _workbook()
    grid = _grid(
        workbook,
        _spec(rows=("Region", "Product"), values=(PivotValueField("Sales"), PivotValueField("Units", "average")), layout="tabular"),
    )
    assert grid[0] == ["Region", "Product", "Sum of Sales", "Average of Units"]
    assert grid[1] == ["East", "Apple", 120, 6.0]
    assert grid[2] == [None, "Pear", 50, 5.0]
    assert grid[3][:3] == ["East Total", None, 170]
    assert grid[-1][0] == "Grand Total" and grid[-1][2] == 310


def test_report_filter_and_percent_of_grand_total() -> None:
    workbook, _ = _workbook()
    spec = _spec(
        rows=("Product",),
        page_fields=("Region",),
        hidden_items=(("Region", ("West",)),),
        values=(PivotValueField("Sales", show_as="percent_of_grand_total"),),
    )
    grid = _grid(workbook, spec)
    assert grid[0] == ["Region", "East"]
    assert grid[3][0] == "Apple" and grid[3][1] == pytest.approx(120 / 170)
    assert grid[-1][1] == pytest.approx(1.0)
    assert compute_pivot(workbook, spec).cells[(3, 1)].number_format == "0.00%"


def test_running_total_and_counts() -> None:
    workbook, _ = _workbook()
    grid = _grid(workbook, _spec(rows=("Product",), values=(PivotValueField("Sales", show_as="running_total"), PivotValueField("Region", "count"))))
    assert [row[1] for row in grid[1:4]] == [220, 260, 310]
    assert [row[2] for row in grid[1:]] == [4, 1, 1, 6]


@pytest.mark.parametrize(
    ("function", "expected"),
    [("sum", 6), ("count", 3), ("average", 2.0), ("max", 3), ("min", 1), ("product", 6), ("count_numbers", 3), ("var", 1.0), ("varp", 2 / 3)],
)
def test_summary_functions(function: str, expected: float) -> None:
    assert summarize(function, [1, 2, 3]) == pytest.approx(expected)


def test_quarters_months_and_field_items() -> None:
    workbook, _ = _workbook()
    assert field_items(workbook, _spec(grouping=(("Date", "quarters"),)), "Date") == ["Qtr1", "Qtr2"]
    assert field_items(workbook, _spec(grouping=(("Date", "months"),)), "Date")[:2] == ["Jan", "Feb"]
    assert field_items(workbook, _spec(), "Product") == ["Apple", "Kiwi", "Pear"]


def test_date_serials_with_a_date_format_group_too() -> None:
    workbook, _ = _workbook()
    sheet = workbook.get_sheet("Sheet1")
    sheet.set_cell(1, 2, 45296, cell_format=CellFormat(number_format="m/d/yyyy"))
    assert field_items(workbook, _spec(grouping=(("Date", "years"),)), "Date") == [2024, 2025]


def test_render_refresh_getpivotdata_and_undo() -> None:
    workbook, engine = _workbook()
    history = CommandHistory()
    history.execute(WorkbookMutationCommand(engine, "Insert PivotTable", lambda: add_pivot(workbook, "Pivot", _spec())))
    pivot_sheet = workbook.get_sheet("Pivot")
    assert pivot_sheet.get_cell(2, 0).display_value == "Row Labels"
    assert pivot_sheet.get_cell(5, 1).display_value == 310
    assert pivot_sheet.get_cell(2, 0).format.bold
    assert pivot_at(pivot_sheet, 4, 1).name == "PivotTable1"
    engine.set_cell("Sheet1", 20, 0, '=GETPIVOTDATA("Sales",Pivot!A3,"Region","East")')
    engine.set_cell("Sheet1", 21, 0, '=GETPIVOTDATA("Sum of Sales",Pivot!$A$3)')
    engine.set_cell("Sheet1", 22, 0, '=GETPIVOTDATA("Sales",Pivot!A3,"Region","North")')
    sheet = workbook.get_sheet("Sheet1")
    assert sheet.get_cell(20, 0).display_value == 170
    assert sheet.get_cell(21, 0).display_value == 310
    assert sheet.get_cell(22, 0).error == "#REF!"
    # A PivotTable is a snapshot until it is refreshed.
    engine.set_cell("Sheet1", 1, 3, 1000)
    assert pivot_sheet.get_cell(3, 1).display_value == 170
    assert sheet.get_cell(20, 0).display_value == 170
    history.execute(WorkbookMutationCommand(engine, "Refresh", lambda: refresh_pivots(workbook)))
    assert pivot_sheet.get_cell(3, 1).display_value == 1070
    assert sheet.get_cell(20, 0).display_value == 1070
    history.undo()
    assert workbook.get_sheet("Pivot").get_cell(3, 1).display_value == 170


def test_pivot_from_a_table_follows_the_table_as_it_grows() -> None:
    from duddysheet.core.tables import expand_for_entry

    workbook, engine = _workbook()
    create_table(workbook, "Sheet1", (0, 0, 6, 4), name="Sales")
    spec = PivotSpec("PivotTable1", "Sheet1", (0, 0, 6, 4), (2, 0), rows=("Region",), values=(PivotValueField("Sales"),), source_table="Sales")
    add_pivot(workbook, "Pivot", spec)
    for column, value in enumerate(("North", "Pear", date(2025, 7, 1), 5, 1)):
        engine.set_cell("Sheet1", 7, column, value)
        expand_for_entry(workbook.get_sheet("Sheet1"), 7, column)
    refresh_pivots(workbook)
    pivot_sheet = workbook.get_sheet("Pivot")
    assert [pivot_sheet.get_cell(row, 0).display_value for row in range(3, 7)] == ["East", "North", "West", "Grand Total"]
    assert pivot_sheet.get_cell(6, 1).display_value == 315


def test_layout_change_clears_old_output_and_refuses_to_overwrite_data() -> None:
    workbook, _ = _workbook()
    pivot_sheet = workbook.get_sheet("Pivot")
    spec = add_pivot(workbook, "Pivot", _spec(rows=("Region", "Product")))
    assert pivot_sheet.get_cell(9, 0).display_value == "Grand Total"
    update_pivot(workbook, "Pivot", _spec())
    assert pivot_sheet.get_cell(9, 0).display_value is None
    pivot_sheet.set_cell(7, 1, "keep")
    with pytest.raises(ValueError):
        update_pivot(workbook, "Pivot", _spec(rows=("Date",)))
    delete_pivot(workbook, "Pivot", spec.name)
    assert pivot_sheet.pivots == [] and pivot_sheet.get_cell(2, 0).display_value is None


def test_show_details_lists_source_rows() -> None:
    workbook, _ = _workbook()
    add_pivot(workbook, "Pivot", _spec(rows=("Region",), columns=("Product",)))
    pivot_sheet = workbook.get_sheet("Pivot")
    # Row 4 is East; column 1 is Apple.
    assert pivot_sheet.get_cell(4, 0).display_value == "East"
    assert pivot_sheet.get_cell(3, 1).display_value == "Apple"
    records = details_at(workbook, pivot_sheet.pivots[0], 4, 1)
    assert records[0] == list(ROWS[0])
    assert sorted(record[3] for record in records[1:]) == [20, 100]


def test_empty_report_shows_a_placeholder() -> None:
    workbook, _ = _workbook()
    grid = _grid(workbook, _spec(rows=(), values=()))
    assert grid[0][0] == "PivotTable1"
    assert "PivotTable Field List" in grid[1][0]


def test_unknown_field_is_rejected() -> None:
    workbook, _ = _workbook()
    with pytest.raises(ValueError):
        compute_pivot(workbook, _spec(rows=("Nope",)))


def test_pivots_round_trip_natively_and_move_with_rows(tmp_path) -> None:
    from duddysheet.core.operations import edit_structure

    workbook, _ = _workbook()
    add_pivot(
        workbook,
        "Pivot",
        _spec(
            rows=("Region",),
            columns=("Date",),
            grouping=(("Date", "years"),),
            hidden_items=(("Region", ("West",)),),
            values=(PivotValueField("Sales", "average", "percent_of_row_total", "Share", "0.0%"),),
            layout="outline",
        ),
    )
    loaded = load_native(save_native(workbook, tmp_path / "p.dsheet"))
    assert loaded.get_sheet("Pivot").pivots[0] == workbook.get_sheet("Pivot").pivots[0]
    edit_structure(workbook, "Pivot", axis="row", index=0, count=2, delete=False)
    moved = workbook.get_sheet("Pivot").pivots[0]
    assert moved.anchor == (4, 0) and moved.extent[0] == 4
    edit_structure(workbook, "Sheet1", axis="row", index=0, count=1, delete=False)
    assert workbook.get_sheet("Pivot").pivots[0].source == (1, 0, 7, 4)
