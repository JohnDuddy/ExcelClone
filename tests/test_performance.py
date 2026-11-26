from __future__ import annotations

import os
import subprocess
import sys
from time import perf_counter

import pytest
from openpyxl import Workbook as OpenPyxlWorkbook
from PySide6.QtWidgets import QApplication

from duddysheet.commands.base import CommandHistory
from duddysheet.commands.edits import SetRangeCommand
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.workbook import Workbook
from duddysheet.io.xlsx_reader import read_xlsx
from duddysheet.ui.grid_model import GridModel


@pytest.mark.performance
def test_cold_application_launch_is_under_three_seconds() -> None:
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    started = perf_counter()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from duddysheet.app import create_application;"
                "app,window=create_application([]);"
                "window.close()"
            ),
        ],
        cwd=os.getcwd(),
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    elapsed = perf_counter() - started

    assert result.returncode == 0, result.stderr
    assert elapsed < 3.0


@pytest.mark.performance
def test_load_50_000_cell_xlsx_is_under_five_seconds(tmp_path) -> None:
    path = tmp_path / "50k.xlsx"
    package = OpenPyxlWorkbook(write_only=True)
    sheet = package.create_sheet("Data")
    for row in range(500):
        sheet.append([row * 100 + column for column in range(100)])
    package.save(path)

    started = perf_counter()
    result = read_xlsx(path)
    elapsed = perf_counter() - started

    assert result.workbook.total_populated_cells == 50_000
    assert elapsed < 5.0


@pytest.mark.performance
def test_virtual_scroll_reads_sustain_sixty_frames_per_second() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QApplication.instance() or QApplication([])
    workbook = Workbook()
    for row in range(100_000):
        workbook.active_sheet.set_cell(row, 0, row)
    model = GridModel(FormulaEngine(workbook), CommandHistory())

    started = perf_counter()
    for frame in range(120):
        first_row = frame * 800
        for row in range(first_row, first_row + 40):
            model.data(model.index(row, 0))
    elapsed = perf_counter() - started

    assert elapsed / 120 < 1 / 60


@pytest.mark.performance
def test_single_edit_recalculates_10_000_dependency_chain_under_300ms() -> None:
    workbook = Workbook()
    sheet = workbook.active_sheet
    sheet.set_cell(0, 0, 1)
    for row in range(1, 10_001):
        sheet.set_cell(row, 0, f"=A{row}+1")
    engine = FormulaEngine(workbook)
    engine.recalculate()

    started = perf_counter()
    engine.set_cell("Sheet1", 0, 0, 2)
    elapsed = perf_counter() - started

    assert sheet.get_cell(10_000, 0).display_value == 10_002
    assert elapsed < 0.300


@pytest.mark.performance
def test_full_recalc_100_000_formulas_is_under_ten_seconds() -> None:
    workbook = Workbook()
    sheet = workbook.active_sheet
    for row in range(100_000):
        sheet.set_cell(row, 0, "=1+1")
    engine = FormulaEngine(workbook)

    started = perf_counter()
    result = engine.recalculate()
    elapsed = perf_counter() - started

    assert len(result.recalculated) == 100_000
    assert elapsed < 10.0


@pytest.mark.performance
def test_undo_10_000_cell_paste_is_under_500ms() -> None:
    engine = FormulaEngine(Workbook())
    history = CommandHistory()
    values = tuple(tuple(row * 100 + column for column in range(100)) for row in range(100))
    history.execute(SetRangeCommand(engine, "Sheet1", 0, 0, values))

    started = perf_counter()
    history.undo()
    elapsed = perf_counter() - started

    assert engine.workbook.active_sheet.populated_count == 0
    assert elapsed < 0.500


@pytest.mark.performance
def test_pivot_table_over_100_000_rows_is_under_two_seconds() -> None:
    from duddysheet.core.cell import Cell
    from duddysheet.core.pivot import PivotSpec, PivotValueField, compute_pivot

    workbook = Workbook()
    sheet = workbook.active_sheet
    for column, header in enumerate(("Region", "Product", "Amount")):
        sheet.put_cell(0, column, Cell(header, header))
    regions = ("East", "West", "North", "South")
    for row in range(1, 100_001):
        for column, value in enumerate((regions[row % 4], f"P{row % 25}", float(row % 97))):
            sheet.put_cell(row, column, Cell(value, value))
    spec = PivotSpec("P", sheet.name, (0, 0, 100_000, 2), (0, 5), rows=("Region",), columns=("Product",), values=(PivotValueField("Amount"),))

    started = perf_counter()
    result = compute_pivot(workbook, spec)
    elapsed = perf_counter() - started

    grand_total = max(row for row, _column in result.cells)
    assert result.cells[(grand_total, 0)].value == "Grand Total"
    assert elapsed < 2.0


@pytest.mark.performance
def test_400_cell_data_table_recalculates_under_two_seconds() -> None:
    from duddysheet.commands.analysis import create_data_table
    from duddysheet.core.data_table import DataTableSpec

    workbook = Workbook()
    engine = FormulaEngine(workbook)
    name = workbook.active_sheet.name
    for row, value in enumerate((0.05, 360, 200000, "=PMT(A1/12,A2,-A3)")):
        engine.set_cell(name, row, 0, value)
    for step in range(4, 54):
        engine.set_cell(name, step, 0, f"=A{step}*1.0001")
    engine.set_cell(name, 0, 3, "=A54")
    for index in range(20):
        engine.set_cell(name, 0, 4 + index, 0.03 + index * 0.002)
        engine.set_cell(name, 1 + index, 3, 120 + index * 12)
    create_data_table(workbook, name, DataTableSpec(0, 3, 20, 23, (name, 0, 0), (name, 1, 0)))
    engine.rebuild_index()

    started = perf_counter()
    engine.recalculate()
    full = perf_counter() - started
    started = perf_counter()
    engine.set_cell(name, 2, 0, 250000)
    edit = perf_counter() - started

    assert isinstance(workbook.active_sheet.get_cell(20, 23).display_value, float)
    assert full < 2.0
    assert edit < 1.0
