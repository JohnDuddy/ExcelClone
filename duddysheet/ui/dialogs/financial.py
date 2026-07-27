"""Dialogs for financial models, what-if analysis, and model audit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from duddysheet.core.financial_analysis import AuditReport, Scenario
from duddysheet.core.financial_models import FINANCIAL_MODEL_CATALOG


@dataclass(frozen=True, slots=True)
class GoalSeekRequest:
    """Validated Goal Seek dialog values."""

    formula_cell: str
    target: float
    input_cell: str
    tolerance: float
    minimum: float | None
    maximum: float | None


@dataclass(frozen=True, slots=True)
class SensitivityRequest:
    """Validated sensitivity-table dialog values."""

    formula_cell: str
    row_input_cell: str
    row_values: tuple[float, ...]
    column_input_cell: str | None
    column_values: tuple[float, ...]
    output_cell: str


@dataclass(frozen=True, slots=True)
class ScenarioRequest:
    """Validated scenario-analysis dialog values."""

    scenarios: tuple[Scenario, ...]
    output_cells: tuple[str, ...]
    destination_cell: str


class _AcceptedDialog(QDialog):
    def _add_buttons(self, layout: QVBoxLayout) -> None:
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class FinancialModelDialog(_AcceptedDialog):
    """Choose one built-in model workbook."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Financial Model")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Create an editable, fully linked workbook. Blue/yellow cells are "
            "assumptions; green cells are cross-sheet links."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.models = QComboBox()
        for template in FINANCIAL_MODEL_CATALOG:
            self.models.addItem(template.name, template.key)
        layout.addWidget(self.models)
        self.description = QLabel()
        self.description.setWordWrap(True)
        layout.addWidget(self.description)
        self.models.currentIndexChanged.connect(self._sync_description)
        self._sync_description()
        self._add_buttons(layout)

    def _sync_description(self) -> None:
        template = FINANCIAL_MODEL_CATALOG[self.models.currentIndex()]
        self.description.setText(
            f"{template.description}\n\nPrimary output: {template.primary_output}"
        )

    def template_key(self) -> str:
        """Return the selected template identifier."""
        return str(self.models.currentData())


class GoalSeekDialog(_AcceptedDialog):
    """Collect a one-input Goal Seek problem."""

    def __init__(self, formula_cell: str = "A1", parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Goal Seek")
        layout = QVBoxLayout(self)
        note = QLabel(
            "Goal Seek changes one numeric input until a formula reaches the target. "
            "Calculations run on a copy; only the accepted solution is written."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.formula_cell = QLineEdit(formula_cell)
        self.target = QLineEdit("0")
        self.input_cell = QLineEdit("A1")
        self.tolerance = QLineEdit("0.0000001")
        self.use_bounds = QCheckBox("Use bracketed minimum and maximum")
        self.minimum = QLineEdit()
        self.maximum = QLineEdit()
        form.addRow("Set formula cell", self.formula_cell)
        form.addRow("To value", self.target)
        form.addRow("By changing cell", self.input_cell)
        form.addRow("Tolerance", self.tolerance)
        form.addRow(self.use_bounds)
        form.addRow("Minimum", self.minimum)
        form.addRow("Maximum", self.maximum)
        layout.addLayout(form)
        self._add_buttons(layout)

    def request(self) -> GoalSeekRequest:
        """Return validated numeric and reference text."""
        formula_cell = self.formula_cell.text().strip()
        input_cell = self.input_cell.text().strip()
        if not formula_cell or not input_cell:
            raise ValueError("Formula and input cell references are required")
        target = _parse_number(self.target.text())
        tolerance = _parse_number(self.tolerance.text())
        if tolerance <= 0:
            raise ValueError("Tolerance must be greater than zero")
        minimum = maximum = None
        if self.use_bounds.isChecked():
            minimum = _parse_number(self.minimum.text())
            maximum = _parse_number(self.maximum.text())
            if minimum >= maximum:
                raise ValueError("Minimum must be less than maximum")
        return GoalSeekRequest(
            formula_cell,
            target,
            input_cell,
            tolerance,
            minimum,
            maximum,
        )


class SensitivityDialog(_AcceptedDialog):
    """Configure a one- or two-variable sensitivity table."""

    def __init__(self, formula_cell: str = "A1", parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sensitivity Table")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Enter comma-separated values. Leave the column input blank for a "
            "one-variable table; provide it for a two-variable grid."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.formula_cell = QLineEdit(formula_cell)
        self.row_input_cell = QLineEdit("A1")
        self.row_values = QLineEdit("-10%, -5%, 0%, 5%, 10%")
        self.column_input_cell = QLineEdit()
        self.column_values = QLineEdit()
        self.output_cell = QLineEdit("A20")
        form.addRow("Formula cell", self.formula_cell)
        form.addRow("Row input cell", self.row_input_cell)
        form.addRow("Row values", self.row_values)
        form.addRow("Column input cell", self.column_input_cell)
        form.addRow("Column values", self.column_values)
        form.addRow("Write table at", self.output_cell)
        layout.addLayout(form)
        self._add_buttons(layout)

    def request(self) -> SensitivityRequest:
        """Return validated sensitivity inputs."""
        formula_cell = self.formula_cell.text().strip()
        row_input = self.row_input_cell.text().strip()
        output_cell = self.output_cell.text().strip()
        if not formula_cell or not row_input or not output_cell:
            raise ValueError("Formula, row input, and output cells are required")
        row_values = _parse_number_series(self.row_values.text())
        column_input = self.column_input_cell.text().strip() or None
        column_text = self.column_values.text().strip()
        if bool(column_input) != bool(column_text):
            raise ValueError(
                "Column input cell and column values must both be provided"
            )
        column_values = _parse_number_series(column_text) if column_text else ()
        return SensitivityRequest(
            formula_cell,
            row_input,
            row_values,
            column_input,
            column_values,
            output_cell,
        )


class ScenarioDialog(_AcceptedDialog):
    """Collect named scenarios and output cells."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Scenario Analysis")
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)
        note = QLabel(
            "One scenario per line: Base: A1=100, B1=5%. Values may be numbers, "
            "percentages, TRUE/FALSE, or text."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.scenarios = QPlainTextEdit(
            "Base: A1=100, B1=5%\n"
            "Downside: A1=90, B1=2%\n"
            "Upside: A1=110, B1=8%"
        )
        layout.addWidget(self.scenarios)
        form = QFormLayout()
        self.outputs = QLineEdit("C1")
        self.destination = QLineEdit("A20")
        form.addRow("Output cells", self.outputs)
        form.addRow("Write table at", self.destination)
        layout.addLayout(form)
        self._add_buttons(layout)

    def request(self) -> ScenarioRequest:
        """Parse scenario lines and output references."""
        scenarios: list[Scenario] = []
        for line_number, raw_line in enumerate(
            self.scenarios.toPlainText().splitlines(),
            1,
        ):
            line = raw_line.strip()
            if not line:
                continue
            name, separator, assignments = line.partition(":")
            if not separator or not name.strip() or not assignments.strip():
                raise ValueError(f"Invalid scenario on line {line_number}")
            values: list[tuple[str, Any]] = []
            for assignment in assignments.split(","):
                reference, equals, raw_value = assignment.partition("=")
                if not equals or not reference.strip():
                    raise ValueError(
                        f"Invalid assignment on scenario line {line_number}"
                    )
                values.append((reference.strip(), _parse_scalar(raw_value.strip())))
            scenarios.append(Scenario(name.strip(), tuple(values)))
        if not scenarios:
            raise ValueError("At least one scenario is required")
        outputs = tuple(
            value.strip()
            for value in self.outputs.text().split(",")
            if value.strip()
        )
        destination = self.destination.text().strip()
        if not outputs or not destination:
            raise ValueError("Output and destination cells are required")
        return ScenarioRequest(tuple(scenarios), outputs, destination)


class AuditReportDialog(QDialog):
    """Display an ordered financial-model audit report."""

    def __init__(self, report: AuditReport, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Financial Model Audit")
        self.resize(860, 520)
        layout = QVBoxLayout(self)
        summary = QLabel(
            f"{report.formula_count} formulas | {report.input_count} inputs | "
            f"{report.error_count} formula errors | {len(report.issues)} findings"
        )
        layout.addWidget(summary)
        self.table = QTableWidget(len(report.issues), 5)
        self.table.setHorizontalHeaderLabels(
            ("Severity", "Code", "Sheet", "Cell", "Finding")
        )
        for row, issue in enumerate(report.issues):
            for column, value in enumerate(
                (
                    issue.severity.upper(),
                    issue.code,
                    issue.sheet,
                    issue.cell,
                    issue.message,
                )
            ):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


def _parse_number(value: str) -> float:
    selected = value.strip()
    if not selected:
        raise ValueError("A numeric value is required")
    if selected.endswith("%"):
        return float(selected[:-1].replace(",", "")) / 100
    return float(selected.replace(",", ""))


def _parse_number_series(value: str) -> tuple[float, ...]:
    result = tuple(
        _parse_number(item)
        for item in value.replace(";", ",").split(",")
        if item.strip()
    )
    if not result:
        raise ValueError("At least one numeric value is required")
    return result


def _parse_scalar(value: str) -> Any:
    if value.upper() == "TRUE":
        return True
    if value.upper() == "FALSE":
        return False
    try:
        converted = _parse_number(value)
    except ValueError:
        return value
    return int(converted) if converted.is_integer() and not value.endswith("%") else converted
