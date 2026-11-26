"""Solver Parameters and Add Constraint dialogs, laid out like Excel's Solver."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from duddysheet.core.solver import METHOD_LABELS, METHODS, RELATIONS, SolverConstraint, SolverModel

RELATION_LABELS = {"<=": "<=", "=": "=", ">=": ">=", "int": "int", "bin": "bin", "dif": "dif"}
METHOD_HELP = {
    "grg": "Select the GRG Nonlinear engine for Solver problems that are smooth nonlinear.",
    "simplex": "Select the LP Simplex engine for linear Solver problems.",
    "evolutionary": "Select the Evolutionary engine for Solver problems that are non-smooth.",
}


class ConstraintDialog(QDialog):
    """Add Constraint / Change Constraint."""

    def __init__(self, parent: QWidget | None = None, constraint: SolverConstraint | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Change Constraint" if constraint else "Add Constraint")
        layout = QGridLayout(self)
        self.left = QLineEdit(constraint.left if constraint else "")
        self.left.setObjectName("constraintCell")
        self.relation = QComboBox()
        self.relation.addItems([RELATION_LABELS[item] for item in RELATIONS])
        self.right = QLineEdit(constraint.right if constraint else "")
        self.right.setObjectName("constraintValue")
        if constraint:
            self.relation.setCurrentIndex(RELATIONS.index(constraint.relation))
        self.relation.currentIndexChanged.connect(self._relation_changed)
        layout.addWidget(QLabel("Cell Reference:"), 0, 0)
        layout.addWidget(QLabel("Constraint:"), 0, 2)
        layout.addWidget(self.left, 1, 0)
        layout.addWidget(self.relation, 1, 1)
        layout.addWidget(self.right, 1, 2)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons, 2, 0, 1, 3)
        self._relation_changed()

    def _relation_changed(self) -> None:
        relation = RELATIONS[self.relation.currentIndex()]
        fixed = {"int": "integer", "bin": "binary", "dif": "AllDifferent"}.get(relation)
        self.right.setEnabled(fixed is None)
        if fixed:
            self.right.setText(fixed)
        elif self.right.text() in ("integer", "binary", "AllDifferent"):
            self.right.clear()

    def constraint(self) -> SolverConstraint:
        """Return the constraint as entered."""
        relation = RELATIONS[self.relation.currentIndex()]
        right = "" if relation in ("int", "bin", "dif") else self.right.text().strip().lstrip("=")
        return SolverConstraint(self.left.text().strip().lstrip("="), relation, right)


class SolverDialog(QDialog):
    """Solver Parameters: objective, goal, variable cells, constraints, and method."""

    def __init__(self, model: SolverModel | None, default_objective: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Solver Parameters")
        self.resize(560, 520)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.objective = QLineEdit(model.objective if model else default_objective)
        self.objective.setObjectName("solverObjective")
        form.addRow("Set Objective:", self.objective)
        goals = QHBoxLayout()
        self.goal_buttons = QButtonGroup(self)
        self.maximize = QRadioButton("Max")
        self.minimize = QRadioButton("Min")
        self.value_of = QRadioButton("Value Of:")
        for index, button in enumerate((self.maximize, self.minimize, self.value_of)):
            self.goal_buttons.addButton(button, index)
            goals.addWidget(button)
        self.target = QLineEdit(str(model.target if model else 0).rstrip("0").rstrip(".") if model and model.target else "0")
        self.target.setObjectName("solverTarget")
        goals.addWidget(self.target)
        goal = model.goal if model else "max"
        {"max": self.maximize, "min": self.minimize, "value": self.value_of}[goal].setChecked(True)
        form.addRow("To:", goals)
        self.variables = QLineEdit(model.variables if model else "")
        self.variables.setObjectName("solverVariables")
        form.addRow("By Changing Variable Cells:", self.variables)
        layout.addLayout(form)
        layout.addWidget(QLabel("Subject to the Constraints:"))
        constraints_row = QHBoxLayout()
        self.constraints: list[SolverConstraint] = list(model.constraints if model else ())
        self.constraint_list = QListWidget()
        self.constraint_list.setObjectName("solverConstraints")
        constraints_row.addWidget(self.constraint_list, 1)
        side = QVBoxLayout()
        for label, handler in (("Add", self.add_constraint), ("Change", self.change_constraint), ("Delete", self.delete_constraint), ("Reset All", self.reset_all)):
            button = QPushButton(label)
            button.setObjectName(f"solver{label.replace(' ', '')}")
            button.clicked.connect(handler)
            side.addWidget(button)
        side.addStretch(1)
        constraints_row.addLayout(side)
        layout.addLayout(constraints_row)
        self.non_negative = QCheckBox("Make Unconstrained Variables Non-Negative")
        self.non_negative.setChecked(model.non_negative if model else True)
        layout.addWidget(self.non_negative)
        method_row = QHBoxLayout()
        method_row.addWidget(QLabel("Select a Solving Method:"))
        self.method = QComboBox()
        self.method.setObjectName("solverMethod")
        self.method.addItems([METHOD_LABELS[item] for item in METHODS])
        self.method.setCurrentIndex(METHODS.index(model.method if model else "grg"))
        method_row.addWidget(self.method, 1)
        layout.addLayout(method_row)
        self.method_help = QLabel()
        self.method_help.setWordWrap(True)
        self.method.currentIndexChanged.connect(lambda index: self.method_help.setText(METHOD_HELP[METHODS[index]]))
        self.method_help.setText(METHOD_HELP[METHODS[self.method.currentIndex()]])
        layout.addWidget(self.method_help)
        buttons = QDialogButtonBox()
        self.solve_button = buttons.addButton("Solve", QDialogButtonBox.ButtonRole.AcceptRole)
        self.solve_button.setObjectName("solverSolve")
        buttons.addButton("Close", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def _refresh(self) -> None:
        self.constraint_list.clear()
        self.constraint_list.addItems([item.describe() for item in self.constraints])

    def add_constraint(self, constraint: Any = None) -> None:
        """Add Constraint (pass a constraint to add it without the dialog)."""
        if not isinstance(constraint, SolverConstraint):
            dialog = ConstraintDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            constraint = dialog.constraint()
        self.constraints.append(constraint)
        self._refresh()

    def change_constraint(self) -> None:
        row = self.constraint_list.currentRow()
        if row < 0:
            return
        dialog = ConstraintDialog(self, self.constraints[row])
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.constraints[row] = dialog.constraint()
            self._refresh()

    def delete_constraint(self) -> None:
        row = self.constraint_list.currentRow()
        if row >= 0:
            del self.constraints[row]
            self._refresh()

    def reset_all(self) -> None:
        self.objective.clear()
        self.variables.clear()
        self.constraints.clear()
        self.maximize.setChecked(True)
        self.target.setText("0")
        self.non_negative.setChecked(True)
        self.method.setCurrentIndex(0)
        self._refresh()

    def model(self) -> SolverModel:
        """Return the parameters as a Solver model."""
        goal = ("max", "min", "value")[max(0, self.goal_buttons.checkedId())]
        try:
            target = float(self.target.text() or 0)
        except ValueError as error:
            raise ValueError("Value Of must be a number.") from error
        return SolverModel(
            objective=self.objective.text().strip().lstrip("="),
            goal=goal,
            target=target,
            variables=self.variables.text().strip().lstrip("="),
            constraints=tuple(self.constraints),
            non_negative=self.non_negative.isChecked(),
            method=METHODS[self.method.currentIndex()],
        )
