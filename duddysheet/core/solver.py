"""Solver: optimize an objective cell by changing variable cells under constraints.

Three solving methods mirror Excel's Solver add-in:

* ``simplex`` (Simplex LP) for linear models, with branch and bound for
  integer and binary constraints;
* ``grg`` (GRG Nonlinear) for smooth nonlinear models, here a
  quasi-Newton search on an augmented-Lagrangian penalty;
* ``evolutionary`` for non-smooth models, a seeded differential evolution.

Every trial runs on a copy of the workbook; the real workbook only changes
when the caller applies the solution (Keep Solver Solution).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from duddysheet.core.engine import FormulaEngine
from duddysheet.core.refs import CellReference, RangeReference, parse_a1

GOALS = ("max", "min", "value")
METHODS = ("grg", "simplex", "evolutionary")
METHOD_LABELS = {"grg": "GRG Nonlinear", "simplex": "Simplex LP", "evolutionary": "Evolutionary"}
RELATIONS = ("<=", "=", ">=", "int", "bin", "dif")
# Excel's solver_rel codes, used when a model is saved in a workbook.
RELATION_CODES = {"<=": 1, "=": 2, ">=": 3, "int": 4, "bin": 5, "dif": 6}
FOUND = "Solver found a solution. All Constraints and optimality conditions are satisfied."
CONVERGED = "Solver converged to the current solution. All Constraints are satisfied."
INFEASIBLE = "Solver could not find a feasible solution."
UNBOUNDED = "The Objective Cell values do not converge."
NOT_LINEAR = "The linearity conditions required by this LP Solver are not satisfied."
NEEDS_BOUNDS = (
    "All variables must have both upper and lower bounds for the Evolutionary method. "
    "Add constraints such as $B$1 <= 100 on each variable cell."
)
_BIG = 1e30


@dataclass(frozen=True, slots=True)
class SolverConstraint:
    """``left`` relation ``right``: cell references, or a number on the right."""

    left: str
    relation: str
    right: str = ""

    def __post_init__(self) -> None:
        if self.relation not in RELATIONS:
            raise ValueError(f"Unknown constraint relation {self.relation!r}")

    def describe(self) -> str:
        """Return the constraint as Solver's list shows it, e.g. '$B$5 <= 100'."""
        if self.relation in ("int", "bin", "dif"):
            return f"{self.left} = {'integer' if self.relation == 'int' else 'binary' if self.relation == 'bin' else 'AllDifferent'}"
        return f"{self.left} {self.relation} {self.right}"


@dataclass(frozen=True, slots=True)
class SolverModel:
    """What Solver Parameters holds for one sheet."""

    objective: str
    goal: str = "max"
    target: float = 0.0
    variables: str = ""
    constraints: tuple[SolverConstraint, ...] = ()
    non_negative: bool = True
    method: str = "grg"
    max_iterations: int = 400
    seed: int = 0

    def __post_init__(self) -> None:
        if self.goal not in GOALS:
            raise ValueError(f"Unknown Solver goal {self.goal!r}")
        if self.method not in METHODS:
            raise ValueError(f"Unknown solving method {self.method!r}")


@dataclass(slots=True)
class SolverResult:
    """The outcome of a solve, before it is kept or discarded."""

    success: bool
    message: str
    values: dict[tuple[str, int, int], float] = field(default_factory=dict)
    objective: float | None = None
    iterations: int = 0


class SolverError(ValueError):
    """A model Solver cannot run (bad references, no variables)."""


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------
def _cells(text: str, default_sheet: str) -> list[tuple[str, int, int]]:
    cells: list[tuple[str, int, int]] = []
    for part in [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]:
        try:
            reference = parse_a1(part.lstrip("=").replace("$", ""), default_sheet=default_sheet)
        except (ValueError, KeyError) as error:
            raise SolverError(f"{part!r} is not a valid cell reference.") from error
        if isinstance(reference, CellReference):
            reference = RangeReference(reference, reference)
        if not isinstance(reference, RangeReference):
            raise SolverError(f"{part!r} is not a valid cell reference.")
        sheet = reference.sheet or default_sheet
        cells.extend(
            (sheet, row, column)
            for row in range(reference.min_row, reference.max_row + 1)
            for column in range(reference.min_column, reference.max_column + 1)
        )
    return cells


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return math.nan


class _Problem:
    """Evaluates the model on a workbook copy for any trial variable values."""

    def __init__(self, workbook: Any, model: SolverModel, sheet_name: str) -> None:
        self.model = model
        self.sheet_name = sheet_name
        self.engine = FormulaEngine(workbook.copy())
        self.engine.recalculate()
        self.variables = _cells(model.variables, sheet_name)
        if not self.variables:
            raise SolverError("Solver needs at least one variable cell (By Changing Variable Cells).")
        for sheet, row, column in self.variables:
            if self.engine.workbook.get_sheet(sheet).get_cell(row, column).is_formula:
                raise SolverError("Variable cells must be constants, not formulas.")
        objective = _cells(model.objective, sheet_name)
        if len(objective) != 1:
            raise SolverError("The objective must be a single cell.")
        self.objective = objective[0]
        self.index = {cell: position for position, cell in enumerate(self.variables)}
        self.integer: set[int] = set()
        self.binary: set[int] = set()
        self.different: list[list[int]] = []
        self.rows: list[tuple[tuple[str, int, int], str, Any]] = []
        for constraint in model.constraints:
            left = _cells(constraint.left, sheet_name)
            if constraint.relation in ("int", "bin", "dif"):
                positions = [self.index[cell] for cell in left if cell in self.index]
                if len(positions) != len(left):
                    raise SolverError("Integer, binary, and AllDifferent constraints apply to variable cells only.")
                if constraint.relation == "int":
                    self.integer.update(positions)
                elif constraint.relation == "bin":
                    self.binary.update(positions)
                else:
                    self.different.append(positions)
                continue
            try:
                constant = float(constraint.right)
                right: list[Any] = [constant] * len(left)
            except ValueError:
                cells = _cells(constraint.right, sheet_name)
                if len(cells) == 1:
                    right = cells * len(left)
                elif len(cells) == len(left):
                    right = cells
                else:
                    raise SolverError(f"The two sides of {constraint.describe()!r} have different sizes.") from None
            for cell, other in zip(left, right):
                self.rows.append((cell, constraint.relation, other))
        self.start = np.array([_number(self._read(cell)) for cell in self.variables], dtype=float)
        self.start = np.where(np.isfinite(self.start), self.start, 0.0)
        self.evaluations = 0

    def _read(self, cell: tuple[str, int, int]) -> Any:
        sheet, row, column = cell
        source = self.engine.workbook.get_sheet(sheet).get_cell(row, column)
        return None if source.error is not None else source.display_value

    def set(self, x: np.ndarray) -> None:
        for (sheet, row, column), value in zip(self.variables, x):
            current = self.engine.workbook.get_sheet(sheet).get_cell(row, column).raw_input
            number = float(value)
            if number.is_integer() and abs(number) < 2**53:
                number = int(number)
            if current != number:
                self.engine.set_cell(sheet, row, column, number)
        self.evaluations += 1

    @property
    def equality(self) -> np.ndarray:
        """Which constraint rows are equalities."""
        return np.array([relation == "=" for _cell, relation, _other in self.rows], dtype=bool)

    def evaluate(self, x: np.ndarray, *, signed: bool = False) -> tuple[float, np.ndarray]:
        """Return the objective and every constraint's slack (>= 0 means satisfied).

        An equality row's slack is ``-|right - left|``, or ``right - left``
        when ``signed`` (so it stays linear for Simplex LP).
        """
        self.set(x)
        objective = _number(self._read(self.objective))
        slacks = []
        for cell, relation, other in self.rows:
            left = _number(self._read(cell))
            right = other if isinstance(other, float) else _number(self._read(other))
            if relation == "<=":
                slacks.append(right - left)
            elif relation == ">=":
                slacks.append(left - right)
            else:
                slacks.append(right - left if signed else -abs(left - right))
        return objective, np.array(slacks, dtype=float)

    def lower_bounds(self) -> np.ndarray:
        lower = np.full(len(self.variables), -_BIG)
        if self.model.non_negative:
            lower[:] = 0.0
        for position in self.binary:
            lower[position] = 0.0
        return lower

    def upper_bounds(self) -> np.ndarray:
        upper = np.full(len(self.variables), _BIG)
        for position in self.binary:
            upper[position] = 1.0
        return upper

    def score(self, objective: float) -> float:
        """Turn the objective into a value to minimize."""
        if self.model.goal == "max":
            return -objective
        if self.model.goal == "min":
            return objective
        return (objective - self.model.target) ** 2


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def solve(workbook: Any, model: SolverModel, sheet_name: str) -> SolverResult:
    """Run Solver on a copy of ``workbook``; return the solution without applying it."""
    problem = _Problem(workbook, model, sheet_name)
    if model.method == "simplex":
        result = _solve_linear(problem)
    elif model.method == "evolutionary":
        result = _solve_evolutionary(problem)
    else:
        result = _solve_nonlinear(problem)
    result.iterations = problem.evaluations
    return result


def _result(problem: _Problem, x: np.ndarray, message: str, success: bool = True) -> SolverResult:
    objective, _slacks = problem.evaluate(x)
    values = {cell: float(value) for cell, value in zip(problem.variables, x)}
    return SolverResult(success, message, values, objective)


def _feasible(problem: _Problem, x: np.ndarray, tolerance: float = 1e-6) -> bool:
    _objective, slacks = problem.evaluate(x)
    if slacks.size and slacks.min() < -tolerance * max(1.0, float(np.abs(slacks).max(initial=0.0))):
        return False
    lower, upper = problem.lower_bounds(), problem.upper_bounds()
    if np.any(x < lower - 1e-7) or np.any(x > upper + 1e-7):
        return False
    for position in problem.integer | problem.binary:
        if abs(x[position] - round(x[position])) > 1e-6:
            return False
    return all(len({round(x[position]) for position in group}) == len(group) for group in problem.different)


# ---------------------------------------------------------------------------
# Simplex LP with branch and bound
# ---------------------------------------------------------------------------
def _linear_terms(problem: _Problem) -> tuple[np.ndarray, float, np.ndarray, np.ndarray] | None:
    """Measure the objective and constraint rows as linear functions; None if not linear."""
    n = len(problem.variables)
    base = np.zeros(n)
    objective0, slacks0 = problem.evaluate(base, signed=True)
    if not math.isfinite(objective0) or not np.all(np.isfinite(slacks0)):
        return None
    gradient = np.zeros(n)
    rows = np.zeros((slacks0.size, n))
    for position in range(n):
        step = np.zeros(n)
        step[position] = 1.0
        objective, slacks = problem.evaluate(step, signed=True)
        gradient[position] = objective - objective0
        rows[:, position] = slacks - slacks0
    # Excel checks linearity; here at two further points.
    for scale in (3.0, -2.5):
        trial = np.linspace(1.0, 2.0, n) * scale
        objective, slacks = problem.evaluate(trial, signed=True)
        expected = objective0 + gradient @ trial
        if not math.isclose(objective, expected, rel_tol=1e-7, abs_tol=1e-7):
            return None
        if slacks.size and not np.allclose(slacks, slacks0 + rows @ trial, rtol=1e-7, atol=1e-7):
            return None
    return gradient, objective0, rows, slacks0


def _simplex(c: np.ndarray, a: np.ndarray, b: np.ndarray) -> tuple[str, np.ndarray | None]:
    """Minimize c.x subject to a.x <= b and x >= 0 (two-phase tableau, Bland's rule)."""
    m, n = a.shape
    a = a.astype(float).copy()
    b = b.astype(float).copy()
    negative = b < 0
    a[negative] *= -1
    b[negative] *= -1
    # Slack (+1 or, for flipped rows, surplus -1) and an artificial for flipped rows.
    slack = np.eye(m) * np.where(negative, -1.0, 1.0)
    artificial_rows = np.flatnonzero(negative)
    artificial = np.zeros((m, artificial_rows.size))
    for column, row in enumerate(artificial_rows):
        artificial[row, column] = 1.0
    tableau = np.hstack([a, slack, artificial, b.reshape(-1, 1)])
    total = n + m + artificial_rows.size
    basis = [n + row if not negative[row] else n + m + list(artificial_rows).index(row) for row in range(m)]

    def pivot(row: int, column: int) -> None:
        tableau[row] /= tableau[row, column]
        for other in range(m):
            if other != row and tableau[other, column] != 0:
                tableau[other] -= tableau[other, column] * tableau[row]
        basis[row] = column

    def run(cost: np.ndarray, allowed: int) -> str:
        for _ in range(5000):
            reduced = cost[:allowed] - cost[basis] @ tableau[:, :allowed]
            entering = next((column for column in range(allowed) if reduced[column] < -1e-9), None)
            if entering is None:
                return "optimal"
            column_values = tableau[:, entering]
            ratios = [
                (tableau[row, -1] / column_values[row], basis[row], row)
                for row in range(m)
                if column_values[row] > 1e-12
            ]
            if not ratios:
                return "unbounded"
            _ratio, _basis, leaving = min(ratios)
            pivot(leaving, entering)
        return "iterations"

    if artificial_rows.size:
        phase_one = np.zeros(total)
        phase_one[n + m :] = 1.0
        run(phase_one, total)
        if phase_one[basis] @ tableau[:, -1] > 1e-7:
            return "infeasible", None
        for row in range(m):
            if basis[row] >= n + m:
                column = next((column for column in range(n + m) if abs(tableau[row, column]) > 1e-9), None)
                if column is not None:
                    pivot(row, column)
    cost = np.zeros(total)
    cost[:n] = c
    status = run(cost, n + m)
    if status != "optimal":
        return status, None
    x = np.zeros(total)
    for row, column in enumerate(basis):
        x[column] = tableau[row, -1]
    return "optimal", x[:n]


def _solve_lp(problem: _Problem, terms: tuple[np.ndarray, float, np.ndarray, np.ndarray], lower: np.ndarray, upper: np.ndarray) -> tuple[str, np.ndarray | None]:
    gradient, _objective0, rows, slacks0 = terms
    n = len(problem.variables)
    sign = -1.0 if problem.model.goal == "max" else 1.0
    # Shift x = lower + y (y >= 0); free variables split into two parts.
    free = lower <= -_BIG / 2
    shift = np.where(free, 0.0, lower)
    columns = []
    for position in range(n):
        unit = np.zeros(n)
        unit[position] = 1.0
        columns.append(unit)
        if free[position]:
            columns.append(-unit)
    transform = np.array(columns).T  # x - shift = transform @ y
    constraints_a: list[np.ndarray] = []
    constraints_b: list[float] = []
    # Constraint rows: slack = slacks0 + rows @ x >= 0  ->  -rows @ x <= slacks0.
    for index, (_cell, relation, _other) in enumerate(problem.rows):
        row = rows[index]
        constant = slacks0[index] + row @ shift
        if relation == "=":
            # slack is -|difference|; measure the signed difference instead.
            constraints_a.append(row @ transform)
            constraints_b.append(-constant)
            constraints_a.append(-row @ transform)
            constraints_b.append(constant)
        else:
            constraints_a.append(-row @ transform)
            constraints_b.append(constant)
    for position in range(n):
        if upper[position] < _BIG / 2:
            unit = np.zeros(n)
            unit[position] = 1.0
            constraints_a.append(unit @ transform)
            constraints_b.append(upper[position] - shift[position])
    if problem.model.goal == "value":
        target = problem.model.target - _objective0 - gradient @ shift
        constraints_a.append(gradient @ transform)
        constraints_b.append(target)
        constraints_a.append(-gradient @ transform)
        constraints_b.append(-target)
        cost = np.zeros(transform.shape[1])
    else:
        cost = sign * gradient @ transform
    a = np.array(constraints_a) if constraints_a else np.zeros((0, transform.shape[1]))
    b = np.array(constraints_b) if constraints_b else np.zeros(0)
    status, y = _simplex(cost, a, b)
    if y is None:
        return status, None
    return status, shift + transform @ y


def _solve_linear(problem: _Problem) -> SolverResult:
    terms = _linear_terms(problem)
    if terms is None:
        return SolverResult(False, NOT_LINEAR)
    integers = problem.integer | problem.binary
    best: tuple[float, np.ndarray] | None = None
    sign = -1.0 if problem.model.goal == "max" else 1.0
    stack = [(problem.lower_bounds(), problem.upper_bounds())]
    unbounded = False
    explored = 0
    while stack and explored < 2000:
        explored += 1
        lower, upper = stack.pop()
        status, x = _solve_lp(problem, terms, lower, upper)
        if status == "unbounded":
            unbounded = True
            continue
        if x is None:
            continue
        value = sign * float(terms[0] @ x)
        if best is not None and value >= best[0] - 1e-9:
            continue
        fractional = next((position for position in sorted(integers) if abs(x[position] - round(x[position])) > 1e-7), None)
        if fractional is None:
            x = np.where(np.isin(np.arange(len(x)), list(integers)), np.round(x), x)
            best = (value, x)
            continue
        down_upper = upper.copy()
        down_upper[fractional] = math.floor(x[fractional])
        up_lower = lower.copy()
        up_lower[fractional] = math.ceil(x[fractional])
        stack.append((lower, down_upper))
        stack.append((up_lower, upper))
    if best is None:
        return SolverResult(False, UNBOUNDED if unbounded else INFEASIBLE)
    x = np.where(np.abs(best[1] - np.round(best[1])) < 1e-9, np.round(best[1]), best[1])
    return _result(problem, x, FOUND)


# ---------------------------------------------------------------------------
# GRG Nonlinear (quasi-Newton on an augmented Lagrangian)
# ---------------------------------------------------------------------------
def _solve_nonlinear(problem: _Problem) -> SolverResult:
    lower, upper = problem.lower_bounds(), problem.upper_bounds()
    x = np.clip(problem.start.copy(), lower, upper)
    multipliers = np.zeros(len(problem.rows))
    penalty = 10.0

    equality = problem.equality

    def merit(trial: np.ndarray) -> float:
        objective, slacks = problem.evaluate(trial, signed=True)
        if not math.isfinite(objective) or not np.all(np.isfinite(slacks)):
            return math.inf
        shifted = slacks + multipliers / penalty
        violation = np.where(equality, shifted, np.minimum(shifted, 0.0))
        return problem.score(objective) + 0.5 * penalty * float(violation @ violation)

    def gradient(trial: np.ndarray, value: float) -> np.ndarray:
        result = np.zeros_like(trial)
        for position in range(trial.size):
            step = 1e-6 * max(1.0, abs(trial[position]))
            moved = trial.copy()
            moved[position] += step
            if moved[position] > upper[position]:
                moved[position] -= 2 * step
                step = -step
            result[position] = (merit(moved) - value) / step
        return result

    budget = problem.model.max_iterations
    for _outer in range(12):
        value = merit(x)
        hessian = np.eye(x.size)
        grad = gradient(x, value)
        for _ in range(budget // 12 + 1):
            direction = -hessian @ grad
            free = ~(((x <= lower + 1e-12) & (direction < 0)) | ((x >= upper - 1e-12) & (direction > 0)))
            direction = np.where(free, direction, 0.0)
            if np.linalg.norm(direction) < 1e-10:
                break
            step = 1.0
            improved = False
            for _search in range(40):
                trial = np.clip(x + step * direction, lower, upper)
                trial_value = merit(trial)
                if trial_value < value - 1e-4 * step * abs(grad @ direction):
                    improved = True
                    break
                step *= 0.5
            if not improved:
                break
            new_grad = gradient(trial, trial_value)
            s, y = trial - x, new_grad - grad
            if s @ y > 1e-12:
                rho = 1.0 / (y @ s)
                identity = np.eye(x.size)
                hessian = (identity - rho * np.outer(s, y)) @ hessian @ (identity - rho * np.outer(y, s)) + rho * np.outer(s, s)
            converged = abs(value - trial_value) <= 1e-10 * max(1.0, abs(value))
            x, value, grad = trial, trial_value, new_grad
            if converged:
                break
        _objective, slacks = problem.evaluate(x, signed=True)
        if slacks.size:
            updated = multipliers + penalty * slacks
            multipliers = np.where(equality, updated, np.minimum(updated, 0.0))
        measured = np.where(equality, -np.abs(slacks), slacks) if slacks.size else slacks
        if not measured.size or measured.min() > -1e-7:
            if _outer >= 1:
                break
        penalty *= 10
    for position in problem.integer | problem.binary:
        x[position] = round(x[position])
    x = np.where(np.abs(x - np.round(x)) < 1e-7, np.round(x), x)
    if not _feasible(problem, x, 1e-5):
        return _result(problem, x, INFEASIBLE, success=False)
    if problem.model.goal == "value":
        objective, _slacks = problem.evaluate(x)
        if not math.isclose(objective, problem.model.target, rel_tol=1e-6, abs_tol=1e-6):
            return _result(problem, x, INFEASIBLE, success=False)
    return _result(problem, x, FOUND)


# ---------------------------------------------------------------------------
# Evolutionary (seeded differential evolution)
# ---------------------------------------------------------------------------
def _solve_evolutionary(problem: _Problem) -> SolverResult:
    rng = np.random.default_rng(problem.model.seed)
    low, high = problem.lower_bounds(), problem.upper_bounds()
    for cell, relation, other in problem.rows:
        if cell in problem.index and isinstance(other, float):
            position = problem.index[cell]
            if relation == "<=":
                high[position] = min(high[position], other)
            elif relation == ">=":
                low[position] = max(low[position], other)
    if np.any(low <= -_BIG / 2) or np.any(high >= _BIG / 2):
        return SolverResult(False, NEEDS_BOUNDS)
    integers = sorted(problem.integer | problem.binary)

    def repair(x: np.ndarray) -> np.ndarray:
        x = np.clip(x, low, high)
        if integers:
            x[integers] = np.round(x[integers])
        return x

    def fitness(x: np.ndarray) -> float:
        objective, slacks = problem.evaluate(x)
        if not math.isfinite(objective):
            return math.inf
        violation = float(np.minimum(slacks, 0.0) @ np.minimum(slacks, 0.0)) if slacks.size else 0.0
        return problem.score(objective) + 1e6 * violation

    size = max(12, 6 * len(problem.variables))
    population = np.array([repair(low + rng.random(len(low)) * (high - low)) for _ in range(size)])
    population[0] = repair(problem.start.copy())
    scores = np.array([fitness(member) for member in population])
    generations = max(20, problem.model.max_iterations // 4)
    for _generation in range(generations):
        for index in range(size):
            choices = rng.choice([item for item in range(size) if item != index], 3, replace=False)
            a, b, c = population[choices]
            mutant = repair(a + 0.7 * (b - c))
            cross = rng.random(len(low)) < 0.8
            cross[rng.integers(len(low))] = True
            trial = repair(np.where(cross, mutant, population[index]))
            trial_score = fitness(trial)
            if trial_score <= scores[index]:
                population[index], scores[index] = trial, trial_score
    best = population[int(np.argmin(scores))]
    if not _feasible(problem, best, 1e-4):
        return _result(problem, best, INFEASIBLE, success=False)
    return _result(problem, best, CONVERGED)


# ---------------------------------------------------------------------------
# Saving the model in a workbook (Excel's hidden solver_* names)
# ---------------------------------------------------------------------------
def model_to_names(model: SolverModel) -> dict[str, str]:
    """Return Excel's hidden sheet-level names that store a Solver model."""
    names = {
        "solver_opt": _absolute(model.objective),
        "solver_typ": str({"max": 1, "min": 2, "value": 3}[model.goal]),
        "solver_val": repr(float(model.target)).rstrip("0").rstrip(".") if model.target else "0",
        "solver_adj": ",".join(_absolute(part) for part in model.variables.split(",") if part.strip()),
        "solver_neg": "1" if model.non_negative else "2",
        "solver_eng": str({"grg": 1, "simplex": 2, "evolutionary": 3}[model.method]),
        "solver_num": str(len(model.constraints)),
        "solver_ver": "3",
    }
    for index, constraint in enumerate(model.constraints, 1):
        names[f"solver_lhs{index}"] = _absolute(constraint.left)
        names[f"solver_rel{index}"] = str(RELATION_CODES[constraint.relation])
        right = constraint.right
        if constraint.relation == "int":
            right = '"integer"'
        elif constraint.relation == "bin":
            right = '"binary"'
        elif constraint.relation == "dif":
            right = '"AllDifferent"'
        else:
            try:
                float(right)
            except ValueError:
                right = _absolute(right)
        names[f"solver_rhs{index}"] = right
    return names


def model_from_names(names: dict[str, str]) -> SolverModel | None:
    """Rebuild a Solver model from Excel's solver_* names (None if absent)."""
    if "solver_opt" not in names:
        return None
    relations = {code: relation for relation, code in RELATION_CODES.items()}
    constraints = []
    for index in range(1, int(float(names.get("solver_num", "0") or 0)) + 1):
        relation = relations.get(int(float(names.get(f"solver_rel{index}", "1"))), "<=")
        right = names.get(f"solver_rhs{index}", "")
        if relation in ("int", "bin", "dif"):
            right = ""
        constraints.append(SolverConstraint(_plain(names.get(f"solver_lhs{index}", "")), relation, _plain(right)))
    goal = {"1": "max", "2": "min", "3": "value"}.get(names.get("solver_typ", "1").split(".")[0], "max")
    method = {"1": "grg", "2": "simplex", "3": "evolutionary"}.get(names.get("solver_eng", "1").split(".")[0], "grg")
    try:
        target = float(names.get("solver_val", "0") or 0)
    except ValueError:
        target = 0.0
    return SolverModel(
        objective=_plain(names["solver_opt"]),
        goal=goal,
        target=target,
        variables=_plain(names.get("solver_adj", "")),
        constraints=tuple(constraints),
        non_negative=names.get("solver_neg", "1").split(".")[0] != "2",
        method=method,
    )


def model_to_dict(model: SolverModel) -> dict[str, Any]:
    return {
        "objective": model.objective,
        "goal": model.goal,
        "target": model.target,
        "variables": model.variables,
        "constraints": [[item.left, item.relation, item.right] for item in model.constraints],
        "non_negative": model.non_negative,
        "method": model.method,
    }


def model_from_dict(data: dict[str, Any]) -> SolverModel:
    return SolverModel(
        objective=str(data["objective"]),
        goal=str(data.get("goal", "max")),
        target=float(data.get("target", 0.0)),
        variables=str(data.get("variables", "")),
        constraints=tuple(SolverConstraint(*item) for item in data.get("constraints", ())),
        non_negative=bool(data.get("non_negative", True)),
        method=str(data.get("method", "grg")),
    )


def _absolute(text: str) -> str:
    text = text.strip().lstrip("=")
    if not text:
        return text
    try:
        reference = parse_a1(text.replace("$", ""))
    except (ValueError, KeyError):
        return text
    if isinstance(reference, CellReference):
        return reference.__class__(reference.row, reference.column, reference.sheet, True, True).to_a1()
    if isinstance(reference, RangeReference):
        start = CellReference(reference.min_row, reference.min_column, reference.sheet, True, True)
        end = CellReference(reference.max_row, reference.max_column, reference.sheet, True, True)
        return RangeReference(start, end).to_a1()
    return text


def _plain(text: str) -> str:
    return text.strip().lstrip("=")
