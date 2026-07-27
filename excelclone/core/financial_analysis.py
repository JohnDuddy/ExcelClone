"""Headless what-if analysis and financial-model audit services."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from excelclone.core.engine import FormulaEngine
from excelclone.core.parser import (
    ArrayNode,
    BinaryNode,
    FunctionNode,
    LiteralNode,
    NameNode,
    Node,
    PercentNode,
    ReferenceNode,
    ReferenceOperatorNode,
    UnaryNode,
    collect_references,
    parse_formula,
)
from excelclone.core.refs import CellReference, RangeReference, parse_a1
from excelclone.core.workbook import Workbook


@dataclass(frozen=True, slots=True)
class GoalSeekResult:
    """One Goal Seek attempt and its best numeric solution."""

    input_value: float
    result_value: float
    target_value: float
    iterations: int
    converged: bool

    @property
    def residual(self) -> float:
        """Return the signed difference between the result and target."""
        return self.result_value - self.target_value


@dataclass(frozen=True, slots=True)
class Scenario:
    """Named set of A1 input overrides."""

    name: str
    values: tuple[tuple[str, Any], ...]


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Calculated outputs for one scenario."""

    name: str
    values: tuple[tuple[str, Any], ...]


@dataclass(frozen=True, slots=True)
class SensitivityTable:
    """One- or two-variable sensitivity output."""

    row_values: tuple[float, ...]
    column_values: tuple[float, ...]
    values: tuple[tuple[Any, ...], ...]


@dataclass(frozen=True, slots=True)
class AuditIssue:
    """One model-audit finding."""

    severity: Literal["error", "warning", "info"]
    code: str
    sheet: str
    cell: str
    message: str


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Summary and ordered findings from a workbook audit."""

    formula_count: int
    input_count: int
    error_count: int
    issues: tuple[AuditIssue, ...]


def goal_seek(
    workbook: Workbook,
    formula_cell: str,
    input_cell: str,
    target: float,
    *,
    default_sheet: str | None = None,
    tolerance: float = 1e-7,
    max_iterations: int = 100,
    minimum: float | None = None,
    maximum: float | None = None,
) -> GoalSeekResult:
    """Solve one formula target by varying one numeric input on a clone."""
    if tolerance <= 0:
        raise ValueError("Tolerance must be greater than zero")
    if max_iterations < 1:
        raise ValueError("Maximum iterations must be at least one")
    target_ref = _cell_reference(workbook, formula_cell, default_sheet)
    input_ref = _cell_reference(workbook, input_cell, default_sheet)
    target_cell = workbook.get_sheet(target_ref.sheet).get_cell(
        target_ref.row,
        target_ref.column,
    )
    if not target_cell.is_formula:
        raise ValueError("Goal Seek target must be a formula cell")

    engine = FormulaEngine(workbook.copy())
    engine.recalculate()
    initial = _numeric_value(
        engine.workbook.get_sheet(input_ref.sheet).get_cell(
            input_ref.row,
            input_ref.column,
        ).display_value,
        label="Goal Seek input",
    )

    def probe(value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Goal Seek produced a non-finite input")
        engine.set_cell(
            input_ref.sheet,
            input_ref.row,
            input_ref.column,
            value,
        )
        cell = engine.workbook.get_sheet(target_ref.sheet).get_cell(
            target_ref.row,
            target_ref.column,
        )
        if cell.error is not None:
            raise ValueError(f"Target formula returned {cell.error}")
        return _numeric_value(cell.display_value, label="Goal Seek result")

    target_value = float(target)
    if minimum is not None and maximum is not None:
        if minimum >= maximum:
            raise ValueError("Minimum must be less than maximum")
        lower_result = probe(float(minimum))
        upper_result = probe(float(maximum))
        lower_delta = lower_result - target_value
        upper_delta = upper_result - target_value
        if lower_delta == 0:
            return GoalSeekResult(float(minimum), lower_result, target_value, 1, True)
        if upper_delta == 0:
            return GoalSeekResult(float(maximum), upper_result, target_value, 1, True)
        if lower_delta * upper_delta > 0:
            raise ValueError("Goal Seek bounds do not bracket the target")
        return _bisection_goal_seek(
            probe,
            target_value,
            float(minimum),
            float(maximum),
            lower_delta,
            tolerance,
            max_iterations,
        )

    first_value = initial
    first_result = probe(first_value)
    first_delta = first_result - target_value
    if abs(first_delta) <= tolerance:
        return GoalSeekResult(first_value, first_result, target_value, 0, True)
    step = max(1.0, abs(initial) * 0.1)
    second_value = initial + step
    second_result = probe(second_value)
    second_delta = second_result - target_value
    best = min(
        ((abs(first_delta), first_value, first_result), (abs(second_delta), second_value, second_result)),
        key=lambda item: item[0],
    )

    for iteration in range(1, max_iterations + 1):
        denominator = second_delta - first_delta
        if abs(denominator) < 1e-14:
            candidate = second_value + step * (2**min(iteration, 12))
        else:
            candidate = second_value - second_delta * (
                second_value - first_value
            ) / denominator
        candidate_result = probe(candidate)
        candidate_delta = candidate_result - target_value
        if abs(candidate_delta) < best[0]:
            best = (abs(candidate_delta), candidate, candidate_result)
        if abs(candidate_delta) <= tolerance:
            return GoalSeekResult(
                candidate,
                candidate_result,
                target_value,
                iteration,
                True,
            )
        first_value, first_delta = second_value, second_delta
        second_value, second_delta = candidate, candidate_delta

    return GoalSeekResult(best[1], best[2], target_value, max_iterations, False)


def _bisection_goal_seek(
    probe: Any,
    target: float,
    lower: float,
    upper: float,
    lower_delta: float,
    tolerance: float,
    max_iterations: int,
) -> GoalSeekResult:
    result = probe(lower)
    midpoint = lower
    for iteration in range(1, max_iterations + 1):
        midpoint = (lower + upper) / 2
        result = probe(midpoint)
        delta = result - target
        if abs(delta) <= tolerance or abs(upper - lower) <= tolerance:
            return GoalSeekResult(midpoint, result, target, iteration, True)
        if lower_delta * delta <= 0:
            upper = midpoint
        else:
            lower = midpoint
            lower_delta = delta
    return GoalSeekResult(midpoint, result, target, max_iterations, False)


def evaluate_scenarios(
    workbook: Workbook,
    scenarios: tuple[Scenario, ...],
    output_cells: tuple[str, ...],
    *,
    default_sheet: str | None = None,
) -> tuple[ScenarioResult, ...]:
    """Calculate named input sets against selected output cells."""
    if not scenarios:
        raise ValueError("At least one scenario is required")
    if not output_cells:
        raise ValueError("At least one output cell is required")
    output_refs = tuple(
        _cell_reference(workbook, reference, default_sheet)
        for reference in output_cells
    )
    results: list[ScenarioResult] = []
    for scenario in scenarios:
        engine = FormulaEngine(workbook.copy())
        for reference, value in scenario.values:
            selected = _cell_reference(engine.workbook, reference, default_sheet)
            engine.set_cell(
                selected.sheet,
                selected.row,
                selected.column,
                value,
            )
        engine.recalculate()
        outputs = tuple(
            (
                label,
                _display_value(engine.workbook, reference),
            )
            for label, reference in zip(output_cells, output_refs)
        )
        results.append(ScenarioResult(scenario.name, outputs))
    return tuple(results)


def one_variable_sensitivity(
    workbook: Workbook,
    formula_cell: str,
    input_cell: str,
    values: tuple[float, ...],
    *,
    default_sheet: str | None = None,
) -> SensitivityTable:
    """Calculate one formula across a series of input values."""
    if not values:
        raise ValueError("At least one sensitivity value is required")
    target_ref = _cell_reference(workbook, formula_cell, default_sheet)
    input_ref = _cell_reference(workbook, input_cell, default_sheet)
    engine = FormulaEngine(workbook.copy())
    calculated: list[Any] = []
    for value in values:
        engine.set_cell(
            input_ref.sheet,
            input_ref.row,
            input_ref.column,
            float(value),
        )
        calculated.append(_display_value(engine.workbook, target_ref))
    return SensitivityTable(
        tuple(float(value) for value in values),
        (),
        (tuple(calculated),),
    )


def two_variable_sensitivity(
    workbook: Workbook,
    formula_cell: str,
    row_input_cell: str,
    row_values: tuple[float, ...],
    column_input_cell: str,
    column_values: tuple[float, ...],
    *,
    default_sheet: str | None = None,
) -> SensitivityTable:
    """Calculate one formula across a two-input sensitivity grid."""
    if not row_values or not column_values:
        raise ValueError("Row and column sensitivity values are required")
    target_ref = _cell_reference(workbook, formula_cell, default_sheet)
    row_ref = _cell_reference(workbook, row_input_cell, default_sheet)
    column_ref = _cell_reference(workbook, column_input_cell, default_sheet)
    if row_ref == column_ref:
        raise ValueError("Row and column input cells must be different")
    engine = FormulaEngine(workbook.copy())
    rows: list[tuple[Any, ...]] = []
    for column_value in column_values:
        engine.set_cell(
            column_ref.sheet,
            column_ref.row,
            column_ref.column,
            float(column_value),
        )
        calculated: list[Any] = []
        for row_value in row_values:
            engine.set_cell(
                row_ref.sheet,
                row_ref.row,
                row_ref.column,
                float(row_value),
            )
            calculated.append(_display_value(engine.workbook, target_ref))
        rows.append(tuple(calculated))
    return SensitivityTable(
        tuple(float(value) for value in row_values),
        tuple(float(value) for value in column_values),
        tuple(rows),
    )


def audit_financial_model(workbook: Workbook) -> AuditReport:
    """Scan formulas, cached errors, blank precedents, and embedded constants."""
    issues: list[AuditIssue] = []
    formula_count = 0
    input_count = 0
    error_count = 0
    for sheet in workbook:
        for (row, column), cell in sheet.iter_populated():
            address = CellReference(row, column, sheet=sheet.name).to_a1()
            if cell.is_formula:
                formula_count += 1
            elif cell.raw_input is not None:
                input_count += 1
            if cell.error is not None:
                error_count += 1
                code = (
                    "CIRCULAR_REFERENCE"
                    if cell.error == "#CIRC!"
                    else "FORMULA_ERROR"
                )
                issues.append(
                    AuditIssue(
                        "error",
                        code,
                        sheet.name,
                        address,
                        f"Formula evaluates to {cell.error}.",
                    )
                )
            if not cell.is_formula:
                continue
            if cell.cached_value is None and cell.error is None:
                issues.append(
                    AuditIssue(
                        "warning",
                        "UNCALCULATED_FORMULA",
                        sheet.name,
                        address,
                        "Formula has no cached result; recalculate the workbook.",
                    )
                )
            try:
                ast = parse_formula(cell.raw_input)
            except ValueError:
                continue
            blank_references = _blank_direct_references(workbook, sheet.name, ast)
            for reference in blank_references:
                issues.append(
                    AuditIssue(
                        "warning",
                        "BLANK_PRECEDENT",
                        sheet.name,
                        address,
                        f"Formula directly references blank cell {reference}.",
                    )
                )
            constants = _embedded_constants(ast)
            if constants:
                rendered = ", ".join(f"{value:g}" for value in constants[:4])
                issues.append(
                    AuditIssue(
                        "info",
                        "EMBEDDED_CONSTANT",
                        sheet.name,
                        address,
                        f"Review hard-coded formula constant(s): {rendered}.",
                    )
                )
    severity_order = {"error": 0, "warning": 1, "info": 2}
    issues.sort(
        key=lambda issue: (
            severity_order[issue.severity],
            issue.sheet.casefold(),
            issue.cell,
            issue.code,
        )
    )
    return AuditReport(formula_count, input_count, error_count, tuple(issues))


def _cell_reference(
    workbook: Workbook,
    reference: str,
    default_sheet: str | None,
) -> CellReference:
    selected_sheet = default_sheet or workbook.active_sheet.name
    parsed = parse_a1(reference.strip(), default_sheet=selected_sheet)
    if not isinstance(parsed, CellReference):
        raise ValueError(f"Expected one cell reference: {reference!r}")
    canonical_sheet = workbook.get_sheet(parsed.sheet or selected_sheet).name
    return CellReference(parsed.row, parsed.column, sheet=canonical_sheet)


def _display_value(workbook: Workbook, reference: CellReference) -> Any:
    cell = workbook.get_sheet(reference.sheet).get_cell(
        reference.row,
        reference.column,
    )
    return cell.error if cell.error is not None else cell.display_value


def _numeric_value(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be finite")
    return converted


def _blank_direct_references(
    workbook: Workbook,
    source_sheet: str,
    ast: Node,
) -> tuple[str, ...]:
    blank: list[str] = []
    for reference in collect_references(ast):
        if not isinstance(reference, CellReference):
            continue
        sheet_name = workbook.get_sheet(reference.sheet or source_sheet).name
        if workbook.get_sheet(sheet_name).get_cell(
            reference.row,
            reference.column,
        ).raw_input is None:
            blank.append(
                CellReference(
                    reference.row,
                    reference.column,
                    sheet=sheet_name,
                ).to_a1()
            )
    return tuple(dict.fromkeys(blank))


def _embedded_constants(ast: Node) -> tuple[float, ...]:
    constants: list[float] = []

    def visit(node: Node) -> None:
        if isinstance(node, LiteralNode):
            if (
                isinstance(node.value, (int, float))
                and not isinstance(node.value, bool)
                and float(node.value) not in (0.0, 1.0)
            ):
                constants.append(float(node.value))
        elif isinstance(node, (UnaryNode, PercentNode)):
            visit(node.operand)
        elif isinstance(node, (BinaryNode, ReferenceOperatorNode)):
            visit(node.left)
            visit(node.right)
        elif isinstance(node, FunctionNode):
            for argument in node.arguments:
                visit(argument)
        elif isinstance(node, ArrayNode):
            for row in node.rows:
                for item in row:
                    visit(item)
        elif isinstance(node, (ReferenceNode, NameNode)):
            return

    visit(ast)
    return tuple(dict.fromkeys(constants))
