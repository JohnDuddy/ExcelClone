"""Solver: Simplex LP, GRG Nonlinear, and Evolutionary, checked against Excel's Solver."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from duddysheet.core.engine import FormulaEngine
from duddysheet.core.solver import (
    FOUND,
    INFEASIBLE,
    NEEDS_BOUNDS,
    NOT_LINEAR,
    UNBOUNDED,
    SolverConstraint,
    SolverError,
    SolverModel,
    model_from_dict,
    model_from_names,
    model_to_dict,
    model_to_names,
    solve,
)
from duddysheet.core.workbook import Workbook
from duddysheet.io.native import load_native, save_native
from duddysheet.io.xlsx_reader import read_xlsx
from duddysheet.io.xlsx_writer import write_xlsx
from duddysheet.ui.dialogs.solver_dialog import SolverDialog
from duddysheet.ui.main_window import MainWindow

LIMITS = (SolverConstraint("B4", "<=", "40"), SolverConstraint("B5", "<=", "60"))


def product_mix() -> tuple[Workbook, str]:
    """Maximize 20x + 30y with x + 2y <= 40 and 3x + 2y <= 60."""
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    name = workbook.active_sheet.name
    for row, value in enumerate((0, 0, "=20*B1+30*B2", "=B1+2*B2", "=3*B1+2*B2")):
        engine.set_cell(name, row, 1, value)
    return workbook, name


def test_simplex_finds_the_linear_optimum_without_touching_the_workbook() -> None:
    workbook, name = product_mix()
    result = solve(workbook, SolverModel("B3", "max", variables="B1:B2", method="simplex", constraints=LIMITS), name)
    assert result.success and result.message == FOUND
    assert result.values == {(name, 0, 1): 10.0, (name, 1, 1): 15.0} and result.objective == 650
    assert workbook.active_sheet.get_cell(0, 1).display_value == 0


def test_integer_answer_matches_excels_solver() -> None:
    # Excel's Solver (SOLVER.XLAM) returns B1=9, B2=16, objective 660 for this model.
    workbook, name = product_mix()
    model = SolverModel(
        "B3",
        "max",
        variables="B1:B2",
        method="simplex",
        constraints=(SolverConstraint("B4", "<=", "41"), SolverConstraint("B5", "<=", "61"), SolverConstraint("B1:B2", "int")),
    )
    result = solve(workbook, model, name)
    assert (result.values[(name, 0, 1)], result.values[(name, 1, 1)], result.objective) == (9, 16, 660)


def test_simplex_reports_value_unbounded_infeasible_and_nonlinear_models() -> None:
    workbook, name = product_mix()
    equal = solve(
        workbook,
        SolverModel("B3", "value", target=500, variables="B1:B2", method="simplex", constraints=(SolverConstraint("B1", "=", "B2"),)),
        name,
    )
    assert equal.success and equal.objective == 500 and equal.values[(name, 0, 1)] == equal.values[(name, 1, 1)]
    assert solve(workbook, SolverModel("B3", "max", variables="B1:B2", method="simplex"), name).message == UNBOUNDED
    contradictory = (SolverConstraint("B4", ">=", "100"), SolverConstraint("B4", "<=", "10"))
    infeasible = solve(workbook, SolverModel("B3", "max", variables="B1:B2", method="simplex", constraints=contradictory), name)
    assert infeasible.message == INFEASIBLE
    FormulaEngine(workbook).set_cell(name, 2, 1, "=B1^2+B2")
    assert solve(workbook, SolverModel("B3", "min", variables="B1:B2", method="simplex"), name).message == NOT_LINEAR


def test_grg_nonlinear_finds_smooth_minimum_with_and_without_bounds() -> None:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    name = workbook.active_sheet.name
    for row, value in enumerate((0, 0, "=(A1-3)^2+(A2+1)^2")):
        engine.set_cell(name, row, 0, value)
    free = solve(workbook, SolverModel("A3", "min", variables="A1:A2", non_negative=False), name)
    assert free.success
    assert free.values[(name, 0, 0)] == pytest.approx(3, abs=1e-4)
    assert free.values[(name, 1, 0)] == pytest.approx(-1, abs=1e-4)
    bounded = solve(workbook, SolverModel("A3", "min", variables="A1:A2"), name)
    assert bounded.values[(name, 1, 0)] == 0 and bounded.objective == pytest.approx(1, abs=1e-6)
    workbook2, name2 = product_mix()
    linear = solve(workbook2, SolverModel("B3", "max", variables="B1:B2", constraints=LIMITS), name2)
    assert linear.objective == pytest.approx(650, rel=1e-5)


def test_evolutionary_needs_bounds_and_then_finds_the_optimum() -> None:
    workbook, name = product_mix()
    model = SolverModel("B3", "max", variables="B1:B2", method="evolutionary", constraints=LIMITS)
    assert solve(workbook, model, name).message == NEEDS_BOUNDS
    bounded = SolverModel(
        "B3",
        "max",
        variables="B1:B2",
        method="evolutionary",
        constraints=LIMITS + (SolverConstraint("B1:B2", "<=", "30"), SolverConstraint("B1:B2", "int")),
    )
    result = solve(workbook, bounded, name)
    assert result.success and result.objective == 650


def test_bad_models_are_explained() -> None:
    workbook, name = product_mix()
    with pytest.raises(SolverError, match="variable cell"):
        solve(workbook, SolverModel("B3", "max"), name)
    with pytest.raises(SolverError, match="constants"):
        solve(workbook, SolverModel("B3", "max", variables="B3"), name)


def test_models_persist_in_both_file_formats(tmp_path) -> None:
    workbook, name = product_mix()
    model = SolverModel("B3", "max", variables="B1:B2", method="simplex", constraints=LIMITS + (SolverConstraint("B1:B2", "int"),))
    assert model_from_dict(model_to_dict(model)) == model
    names = model_to_names(model)
    assert names["solver_typ"] == "1" and names["solver_eng"] == "2" and names["solver_rhs3"] == '"integer"'
    assert model_from_names(names).constraints[2].relation == "int"
    workbook.active_sheet.solver = model
    native = tmp_path / "solver.dsheet"
    save_native(workbook, native)
    assert load_native(native).active_sheet.solver == model
    excel = tmp_path / "solver.xlsx"
    write_xlsx(workbook, excel)
    loaded = read_xlsx(excel)
    assert loaded.warnings == ()
    restored = loaded.workbook.active_sheet.solver
    assert restored.method == "simplex" and restored.variables == "$B$1:$B$2" and len(restored.constraints) == 3
    assert solve(loaded.workbook, restored, name).objective == 650


def test_window_solves_and_keeps_the_solution_undoably() -> None:
    QApplication.instance() or QApplication([])
    window = MainWindow()
    model = window.grid_model
    for row, value in enumerate(("0", "0", "=20*B1+30*B2", "=B1+2*B2", "=3*B1+2*B2")):
        model.setData(model.index(row, 1), value)
    dialog = SolverDialog(None, "$B$3", window)
    dialog.variables.setText("B1:B2")
    for constraint in LIMITS:
        dialog.add_constraint(constraint)
    dialog.method.setCurrentIndex(1)
    parameters = dialog.model()
    assert parameters.method == "simplex" and parameters.constraints == LIMITS
    result = window.run_solver(parameters)
    assert result.success
    sheet = window.grid_model.sheet
    assert (sheet.get_cell(0, 1).display_value, sheet.get_cell(1, 1).display_value, sheet.get_cell(2, 1).display_value) == (10, 15, 650)
    assert sheet.solver == parameters
    window.history.undo()
    assert window.grid_model.sheet.get_cell(2, 1).display_value == 0
    assert "solver" in window.excel_actions
    window.close()
