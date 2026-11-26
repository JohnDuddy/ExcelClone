"""Excel-style dialogs for editing, names, notes, protection, auditing, and data tools."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


def _buttons(dialog: QDialog, *, ok_text: str = "OK") -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    box.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


def _radio_group(parent: QWidget, layout: Any, options: list[tuple[str, str]], default: str) -> QButtonGroup:
    group = QButtonGroup(parent)
    for key, label in options:
        button = QRadioButton(label)
        button.setProperty("choice", key)
        button.setObjectName(f"choice_{key}")
        if key == default:
            button.setChecked(True)
        group.addButton(button)
        layout.addWidget(button)
    return group


def _checked(group: QButtonGroup) -> str:
    button = group.checkedButton()
    return str(button.property("choice")) if button is not None else ""


class InsertDeleteCellsDialog(QDialog):
    """Excel's Insert/Delete dialog: shift cells or affect entire rows/columns."""

    def __init__(self, delete: bool, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Delete" if delete else "Insert")
        layout = QVBoxLayout(self)
        box = QGroupBox("Delete" if delete else "Insert")
        inner = QVBoxLayout(box)
        options = (
            [("left", "Shift cells left"), ("up", "Shift cells up"), ("row", "Entire row"), ("column", "Entire column")]
            if delete
            else [("right", "Shift cells right"), ("down", "Shift cells down"), ("row", "Entire row"), ("column", "Entire column")]
        )
        self.group = _radio_group(self, inner, options, "up" if delete else "down")
        layout.addWidget(box)
        layout.addWidget(_buttons(self))

    def choice(self) -> str:
        """Return 'left', 'up', 'right', 'down', 'row', or 'column'."""
        return _checked(self.group)


class GoToDialog(QDialog):
    """F5 / Ctrl+G: jump to a reference or defined name."""

    def __init__(self, names: list[str], parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Go To")
        self.special_requested = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Go to:"))
        self.names = QListWidget()
        self.names.addItems(names)
        self.names.itemDoubleClicked.connect(lambda item: (self.reference.setText(item.text()), self.accept()))
        self.names.currentTextChanged.connect(lambda text: self.reference.setText(text))
        layout.addWidget(self.names)
        layout.addWidget(QLabel("Reference:"))
        self.reference = QLineEdit()
        self.reference.setObjectName("gotoReference")
        layout.addWidget(self.reference)
        row = QHBoxLayout()
        special = QPushButton("Special...")
        special.clicked.connect(self._special)
        row.addWidget(special)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(_buttons(self))

    def _special(self) -> None:
        self.special_requested = True
        self.accept()

    def target(self) -> str:
        """Return the reference or name to go to."""
        return self.reference.text().strip()


class GoToSpecialDialog(QDialog):
    """Select cells by kind: constants, formulas, blanks, notes, and more."""

    OPTIONS = [
        ("notes", "Notes"),
        ("constants", "Constants"),
        ("formulas", "Formulas"),
        ("blanks", "Blanks"),
        ("current_region", "Current region"),
        ("current_array", "Current array"),
        ("row_differences", "Row differences"),
        ("column_differences", "Column differences"),
        ("precedents", "Precedents"),
        ("dependents", "Dependents"),
        ("last_cell", "Last cell"),
        ("visible", "Visible cells only"),
        ("conditional_formats", "Conditional formats"),
        ("data_validation", "Data validation"),
    ]

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Go To Special")
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        self.group = QButtonGroup(self)
        for index, (key, label) in enumerate(self.OPTIONS):
            button = QRadioButton(label)
            button.setProperty("choice", key)
            if key == "constants":
                button.setChecked(True)
            self.group.addButton(button)
            grid.addWidget(button, index % 7, index // 7)
        layout.addLayout(grid)
        types = QHBoxLayout()
        self.types: dict[str, QCheckBox] = {}
        for key, label in (("numbers", "Numbers"), ("text", "Text"), ("logicals", "Logicals"), ("errors", "Errors")):
            box = QCheckBox(label)
            box.setChecked(True)
            self.types[key] = box
            types.addWidget(box)
        layout.addLayout(types)
        layout.addWidget(_buttons(self))

    def kind(self) -> str:
        """Return the selected Go To Special kind."""
        return _checked(self.group)

    def value_types(self) -> tuple[str, ...]:
        """Return the value types chosen for constants and formulas."""
        return tuple(key for key, box in self.types.items() if box.isChecked())


class NewNameDialog(QDialog):
    """Define or edit a name: name, scope, comment, and refers-to formula."""

    def __init__(
        self,
        scopes: list[str],
        parent: Any = None,
        *,
        name: str = "",
        scope: str | None = None,
        comment: str = "",
        refers_to: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Name" if not name else "Edit Name")
        form = QFormLayout(self)
        self.name = QLineEdit(name)
        self.scope = QComboBox()
        self.scope.addItem("Workbook", None)
        for sheet in scopes:
            self.scope.addItem(sheet, sheet)
        if scope is not None:
            self.scope.setCurrentIndex(max(0, self.scope.findData(scope)))
        self.comment = QPlainTextEdit(comment)
        self.comment.setFixedHeight(60)
        self.refers_to = QLineEdit(refers_to)
        form.addRow("Name:", self.name)
        form.addRow("Scope:", self.scope)
        form.addRow("Comment:", self.comment)
        form.addRow("Refers to:", self.refers_to)
        form.addRow(_buttons(self))

    def values(self) -> tuple[str, str | None, str, str]:
        """Return (name, scope, comment, refers-to text)."""
        return (
            self.name.text().strip(),
            self.scope.currentData(),
            self.comment.toPlainText().strip(),
            self.refers_to.text().strip(),
        )


class NameManagerDialog(QDialog):
    """Ctrl+F3: list, create, edit, and delete defined names."""

    def __init__(self, window: Any) -> None:
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Name Manager")
        self.resize(720, 360)
        layout = QVBoxLayout(self)
        buttons = QHBoxLayout()
        for text, handler in (("New...", self._new), ("Edit...", self._edit), ("Delete", self._delete)):
            button = QPushButton(text)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self.table = QTableWidget(0, 5)
        self.table.setObjectName("nameTable")
        self.table.setHorizontalHeaderLabels(["Name", "Value", "Refers To", "Scope", "Comment"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.refresh()

    def refresh(self) -> None:
        """Reload the table from the workbook."""
        names = self.window.engine.workbook.defined_names
        self.table.setRowCount(len(names))
        for row, item in enumerate(names):
            value = self.window.name_preview(item)
            for column, text in enumerate(
                (item.name, value, item.refers_to, item.scope or "Workbook", item.comment)
            ):
                cell = QTableWidgetItem(str(text))
                cell.setData(Qt.ItemDataRole.UserRole, (item.name, item.scope))
                self.table.setItem(row, column, cell)

    def _selected(self) -> tuple[str, str | None] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _new(self) -> None:
        self.window.define_name_dialog()
        self.refresh()

    def _edit(self) -> None:
        selected = self._selected()
        if selected is not None:
            self.window.edit_name_dialog(*selected)
            self.refresh()

    def _delete(self) -> None:
        selected = self._selected()
        if selected is None:
            return
        if QMessageBox.question(self, "Name Manager", f"Delete the name {selected[0]}?") == QMessageBox.StandardButton.Yes:
            self.window.delete_defined_name(*selected)
            self.refresh()


class CreateNamesDialog(QDialog):
    """Ctrl+Shift+F3: create names from row and column labels."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Names from Selection")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Create names from values in the:"))
        self.top = QCheckBox("Top row")
        self.left = QCheckBox("Left column")
        self.bottom = QCheckBox("Bottom row")
        self.right = QCheckBox("Right column")
        self.top.setChecked(True)
        for box in (self.top, self.left, self.bottom, self.right):
            layout.addWidget(box)
        layout.addWidget(_buttons(self))


class NoteDialog(QDialog):
    """Write or edit a cell note."""

    def __init__(self, text: str, author: str, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Note" if text else "New Note")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{author}:" if author else "Note:"))
        self.editor = QPlainTextEdit(text)
        self.editor.setObjectName("noteEditor")
        layout.addWidget(self.editor)
        layout.addWidget(_buttons(self))

    def text(self) -> str:
        """Return the note text."""
        return self.editor.toPlainText()


class ProtectSheetDialog(QDialog):
    """Protect Sheet: password and the actions users may still take."""

    OPTIONS = [
        ("select_locked_cells", "Select locked cells", True),
        ("select_unlocked_cells", "Select unlocked cells", True),
        ("format_cells", "Format cells", False),
        ("format_columns", "Format columns", False),
        ("format_rows", "Format rows", False),
        ("insert_columns", "Insert columns", False),
        ("insert_rows", "Insert rows", False),
        ("insert_hyperlinks", "Insert hyperlinks", False),
        ("delete_columns", "Delete columns", False),
        ("delete_rows", "Delete rows", False),
        ("sort", "Sort", False),
        ("auto_filter", "Use AutoFilter", False),
        ("edit_objects", "Edit objects", False),
    ]

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Protect Sheet")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Password to unprotect sheet:"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setObjectName("protectPassword")
        layout.addWidget(self.password)
        layout.addWidget(QLabel("Allow all users of this worksheet to:"))
        self.options: dict[str, QCheckBox] = {}
        for key, label, default in self.OPTIONS:
            box = QCheckBox(label)
            box.setChecked(default)
            self.options[key] = box
            layout.addWidget(box)
        layout.addWidget(_buttons(self))

    def permissions(self) -> dict[str, bool]:
        """Return the chosen permissions."""
        return {key: box.isChecked() for key, box in self.options.items()}


class PasswordDialog(QDialog):
    """Ask for a password (unprotect, confirm)."""

    def __init__(self, title: str, prompt: str, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(prompt))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setObjectName("passwordField")
        layout.addWidget(self.password)
        layout.addWidget(_buttons(self))


class IterationDialog(QDialog):
    """Formulas > Calculation Options > iterative calculation settings."""

    def __init__(self, enabled: bool, iterations: int, change: float, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Calculation Options")
        form = QFormLayout(self)
        self.enabled = QCheckBox("Enable iterative calculation")
        self.enabled.setChecked(enabled)
        self.iterations = QSpinBox()
        self.iterations.setRange(1, 32767)
        self.iterations.setValue(iterations)
        self.change = QDoubleSpinBox()
        self.change.setDecimals(6)
        self.change.setRange(0.0, 1e6)
        self.change.setValue(change)
        form.addRow(self.enabled)
        form.addRow("Maximum Iterations:", self.iterations)
        form.addRow("Maximum Change:", self.change)
        form.addRow(_buttons(self))


class EvaluateFormulaDialog(QDialog):
    """Formulas > Evaluate Formula: step through a formula's evaluation."""

    def __init__(self, reference: str, steps: list[Any], parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Evaluate Formula")
        self.resize(560, 260)
        self.steps = steps
        self.position = 0
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Reference:  {reference}"))
        self.view = QTextBrowser()
        self.view.setObjectName("evaluationView")
        layout.addWidget(self.view)
        row = QHBoxLayout()
        self.evaluate_button = QPushButton("Evaluate")
        self.evaluate_button.setObjectName("evaluateButton")
        self.evaluate_button.clicked.connect(self.advance)
        restart = QPushButton("Restart")
        restart.clicked.connect(self.restart)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addStretch(1)
        row.addWidget(self.evaluate_button)
        row.addWidget(restart)
        row.addWidget(close)
        layout.addLayout(row)
        self._show()

    def _show(self) -> None:
        from html import escape

        if not self.steps:
            self.view.setPlainText("This cell does not contain a formula.")
            self.evaluate_button.setEnabled(False)
            return
        step = self.steps[self.position]
        if step.underline is None:
            html = escape(step.text)
        else:
            start, end = step.underline
            html = (
                escape(step.text[:start])
                + "<u><b>"
                + escape(step.text[start:end])
                + "</b></u>"
                + escape(step.text[end:])
            )
        self.view.setHtml(f"<p style='font-family:Consolas,monospace;font-size:12pt'>{html}</p>")
        self.evaluate_button.setEnabled(self.position < len(self.steps) - 1)

    def advance(self) -> None:
        """Evaluate the underlined part."""
        if self.position < len(self.steps) - 1:
            self.position += 1
            self._show()

    def restart(self) -> None:
        """Return to the original formula."""
        self.position = 0
        self._show()

    def current_text(self) -> str:
        """Return the displayed formula state."""
        return self.steps[self.position].text if self.steps else ""


class SubtotalDialog(QDialog):
    """Data > Subtotal: group by a column and total others."""

    def __init__(self, headers: list[str], functions: list[str], parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Subtotal")
        form = QFormLayout(self)
        self.group = QComboBox()
        self.group.addItems(headers)
        self.function = QComboBox()
        self.function.addItems(functions)
        self.columns = QListWidget()
        for index, header in enumerate(headers):
            item = QListWidgetItem(header)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if index == len(headers) - 1 else Qt.CheckState.Unchecked)
            self.columns.addItem(item)
        self.below = QCheckBox("Summary below data")
        self.below.setChecked(True)
        self.remove = QPushButton("Remove All")
        self.remove_requested = False
        self.remove.clicked.connect(self._remove)
        form.addRow("At each change in:", self.group)
        form.addRow("Use function:", self.function)
        form.addRow("Add subtotal to:", self.columns)
        form.addRow(self.below)
        row = QHBoxLayout()
        row.addWidget(self.remove)
        row.addWidget(_buttons(self))
        form.addRow(row)

    def _remove(self) -> None:
        self.remove_requested = True
        self.accept()

    def total_indexes(self) -> list[int]:
        """Return checked column positions within the list."""
        return [
            index
            for index in range(self.columns.count())
            if self.columns.item(index).checkState() == Qt.CheckState.Checked
        ]


class ConsolidateDialog(QDialog):
    """Data > Consolidate: combine ranges by position or by labels."""

    def __init__(self, functions: tuple[str, ...], current: str, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Consolidate")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.function = QComboBox()
        self.function.addItems(functions)
        self.reference = QLineEdit(current)
        form.addRow("Function:", self.function)
        form.addRow("Reference:", self.reference)
        layout.addLayout(form)
        row = QHBoxLayout()
        add = QPushButton("Add")
        add.clicked.connect(self._add)
        delete = QPushButton("Delete")
        delete.clicked.connect(lambda: self.references.takeItem(self.references.currentRow()))
        row.addWidget(add)
        row.addWidget(delete)
        row.addStretch(1)
        layout.addLayout(row)
        self.references = QListWidget()
        layout.addWidget(QLabel("All references:"))
        layout.addWidget(self.references)
        self.top_row = QCheckBox("Top row")
        self.left_column = QCheckBox("Left column")
        layout.addWidget(self.top_row)
        layout.addWidget(self.left_column)
        layout.addWidget(_buttons(self))

    def _add(self) -> None:
        text = self.reference.text().strip()
        if text:
            self.references.addItem(text)

    def reference_texts(self) -> list[str]:
        """Return every added reference."""
        texts = [self.references.item(index).text() for index in range(self.references.count())]
        if not texts and self.reference.text().strip():
            texts.append(self.reference.text().strip())
        return texts


class AdvancedFilterDialog(QDialog):
    """Data > Advanced: filter a list in place or copy matches elsewhere."""

    def __init__(self, list_range: str, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Advanced Filter")
        layout = QVBoxLayout(self)
        self.action = _radio_group(
            self,
            layout,
            [("in_place", "Filter the list, in-place"), ("copy", "Copy to another location")],
            "in_place",
        )
        form = QFormLayout()
        self.list_range = QLineEdit(list_range)
        self.criteria = QLineEdit()
        self.copy_to = QLineEdit()
        form.addRow("List range:", self.list_range)
        form.addRow("Criteria range:", self.criteria)
        form.addRow("Copy to:", self.copy_to)
        layout.addLayout(form)
        self.unique = QCheckBox("Unique records only")
        layout.addWidget(self.unique)
        layout.addWidget(_buttons(self))

    def copy_mode(self) -> bool:
        """Return whether matches are copied rather than filtered in place."""
        return _checked(self.action) == "copy"


class ZoomDialog(QDialog):
    """View > Zoom: preset magnifications or a custom percentage."""

    def __init__(self, current: int, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Zoom")
        layout = QVBoxLayout(self)
        self.group = _radio_group(
            self,
            layout,
            [("200", "200%"), ("100", "100%"), ("75", "75%"), ("50", "50%"), ("25", "25%"), ("fit", "Fit selection"), ("custom", "Custom:")],
            str(current) if current in (200, 100, 75, 50, 25) else "custom",
        )
        self.custom = QSpinBox()
        self.custom.setRange(10, 400)
        self.custom.setValue(current)
        layout.addWidget(self.custom)
        layout.addWidget(_buttons(self))

    def choice(self) -> str:
        """Return a percentage string, 'fit', or 'custom'."""
        return _checked(self.group)


class PasteSpecialFullDialog(QDialog):
    """Excel's Paste Special: what to paste, operation, skip blanks, transpose, link."""

    PASTE = [
        ("all", "All"),
        ("formulas", "Formulas"),
        ("values", "Values"),
        ("formats", "Formats"),
        ("all_except_borders", "All except borders"),
        ("column_widths", "Column widths"),
        ("formulas_number_formats", "Formulas and number formats"),
        ("values_number_formats", "Values and number formats"),
    ]
    OPERATIONS = [("none", "None"), ("add", "Add"), ("subtract", "Subtract"), ("multiply", "Multiply"), ("divide", "Divide")]

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Paste Special")
        self.link_requested = False
        layout = QVBoxLayout(self)
        paste_box = QGroupBox("Paste")
        paste_layout = QGridLayout(paste_box)
        self.paste = QButtonGroup(self)
        for index, (key, label) in enumerate(self.PASTE):
            button = QRadioButton(label)
            button.setProperty("choice", key)
            button.setObjectName(f"paste_{key}")
            button.setChecked(key == "all")
            self.paste.addButton(button)
            paste_layout.addWidget(button, index % 4, index // 4)
        layout.addWidget(paste_box)
        operation_box = QGroupBox("Operation")
        operation_layout = QGridLayout(operation_box)
        self.operation = QButtonGroup(self)
        for index, (key, label) in enumerate(self.OPERATIONS):
            button = QRadioButton(label)
            button.setProperty("choice", key)
            button.setObjectName(f"operation_{key}")
            button.setChecked(key == "none")
            self.operation.addButton(button)
            operation_layout.addWidget(button, index % 3, index // 3)
        layout.addWidget(operation_box)
        options = QHBoxLayout()
        self.skip_blanks = QCheckBox("Skip blanks")
        self.transpose = QCheckBox("Transpose")
        options.addWidget(self.skip_blanks)
        options.addWidget(self.transpose)
        layout.addLayout(options)
        row = QHBoxLayout()
        link = QPushButton("Paste Link")
        link.clicked.connect(self._link)
        row.addWidget(link)
        row.addStretch(1)
        row.addWidget(_buttons(self))
        layout.addLayout(row)

    def _link(self) -> None:
        self.link_requested = True
        self.accept()

    def mode(self) -> str:
        """Return the paste mode key."""
        return "link" if self.link_requested else _checked(self.paste)

    def operation_name(self) -> str:
        """Return the arithmetic operation key."""
        return _checked(self.operation)
