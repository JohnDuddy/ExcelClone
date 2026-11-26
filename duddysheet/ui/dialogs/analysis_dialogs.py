"""Dialogs for Excel Tables, PivotTables, and What-If data tables."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from duddysheet.core.pivot import (
    FUNCTION_LABELS,
    FUNCTIONS,
    GROUPINGS,
    LAYOUTS,
    SHOW_AS,
    SHOW_AS_LABELS,
    PivotSpec,
    PivotValueField,
    field_items,
    source_fields,
)


def _buttons(dialog: QDialog) -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


class CreateTableDialog(QDialog):
    """Insert > Table (Ctrl+T): where is the data, and does it have headers?"""

    def __init__(self, range_text: str, has_headers: bool, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Table")
        form = QFormLayout(self)
        form.addRow(QLabel("Where is the data for your table?"))
        self.range = QLineEdit(range_text)
        self.range.setObjectName("tableRange")
        form.addRow(self.range)
        self.headers = QCheckBox("My table has headers")
        self.headers.setChecked(has_headers)
        form.addRow(self.headers)
        form.addRow(_buttons(self))


class CreatePivotDialog(QDialog):
    """Insert > PivotTable: choose the source and where to put the report."""

    def __init__(self, source_text: str, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create PivotTable")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose the data that you want to analyze"))
        form = QFormLayout()
        self.source = QLineEdit(source_text)
        self.source.setObjectName("pivotSource")
        form.addRow("Table/Range:", self.source)
        layout.addLayout(form)
        layout.addWidget(QLabel("Choose where you want the PivotTable report to be placed"))
        self.new_sheet = QRadioButton("New Worksheet")
        self.new_sheet.setChecked(True)
        self.existing = QRadioButton("Existing Worksheet")
        layout.addWidget(self.new_sheet)
        layout.addWidget(self.existing)
        location = QFormLayout()
        self.location = QLineEdit()
        self.location.setObjectName("pivotLocation")
        location.addRow("Location:", self.location)
        layout.addLayout(location)
        layout.addWidget(_buttons(self))


class ValueFieldDialog(QDialog):
    """Value Field Settings: summarize by, show values as, name, number format."""

    def __init__(self, value: PivotValueField, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Value Field Settings")
        form = QFormLayout(self)
        form.addRow("Source Name:", QLabel(value.field))
        self.caption = QLineEdit(value.name)
        form.addRow("Custom Name:", self.caption)
        self.function = QComboBox()
        for key in FUNCTIONS:
            self.function.addItem(FUNCTION_LABELS[key], key)
        self.function.setCurrentIndex(FUNCTIONS.index(value.function))
        form.addRow("Summarize value field by:", self.function)
        self.show_as = QComboBox()
        for key in SHOW_AS:
            self.show_as.addItem(SHOW_AS_LABELS[key], key)
        self.show_as.setCurrentIndex(SHOW_AS.index(value.show_as))
        form.addRow("Show values as:", self.show_as)
        self.number_format = QLineEdit(value.number_format or "")
        self.number_format.setPlaceholderText("General, #,##0, $#,##0.00, 0.0% ...")
        form.addRow("Number Format:", self.number_format)
        self.original = value
        form.addRow(_buttons(self))

    def value(self) -> PivotValueField:
        """Return the edited value field."""
        function = self.function.currentData()
        default_name = f"{FUNCTION_LABELS[function]} of {self.original.field}"
        caption = self.caption.text().strip()
        old_default = f"{FUNCTION_LABELS[self.original.function]} of {self.original.field}"
        if caption in ("", old_default, default_name):
            caption = None
        return replace(
            self.original,
            function=function,
            show_as=self.show_as.currentData(),
            caption=caption,
            number_format=self.number_format.text().strip() or None,
        )


class ItemFilterDialog(QDialog):
    """Choose which items of a field the PivotTable shows."""

    def __init__(self, field_name: str, items: list[Any], hidden: set[Any], parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Filter {field_name}")
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.setObjectName("filterItems")
        for item in items:
            entry = QListWidgetItem(str(item))
            entry.setData(Qt.ItemDataRole.UserRole, item)
            entry.setFlags(entry.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            entry.setCheckState(Qt.CheckState.Unchecked if item in hidden else Qt.CheckState.Checked)
            self.list.addItem(entry)
        row = QHBoxLayout()
        select_all = QPushButton("Select All")
        select_all.clicked.connect(lambda: self._set_all(True))
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: self._set_all(False))
        row.addWidget(select_all)
        row.addWidget(clear)
        layout.addLayout(row)
        layout.addWidget(self.list)
        layout.addWidget(_buttons(self))

    def _set_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in range(self.list.count()):
            self.list.item(index).setCheckState(state)

    def hidden_items(self) -> tuple[Any, ...]:
        """Return the unchecked items."""
        return tuple(
            self.list.item(index).data(Qt.ItemDataRole.UserRole)
            for index in range(self.list.count())
            if self.list.item(index).checkState() != Qt.CheckState.Checked
        )


class PivotFieldsDialog(QDialog):
    """The PivotTable Fields list: drag fields between Filters, Columns, Rows, and Values."""

    AREAS = (("page_fields", "Filters"), ("columns", "Columns"), ("rows", "Rows"), ("values", "Values"))

    def __init__(self, workbook: Any, spec: PivotSpec, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PivotTable Fields")
        self.resize(700, 680)
        self.workbook = workbook
        self.spec = spec
        self.fields = source_fields(workbook, spec)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose fields to add to report (check a field, or select it and pick an area):"))
        self.field_list = QListWidget()
        self.field_list.setObjectName("pivotFieldList")
        for name in self.fields:
            entry = QListWidgetItem(name)
            entry.setFlags(entry.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            entry.setCheckState(Qt.CheckState.Checked if self._used(name) else Qt.CheckState.Unchecked)
            self.field_list.addItem(entry)
        self.field_list.setMinimumHeight(170)
        self.field_list.itemChanged.connect(self._field_toggled)
        layout.addWidget(self.field_list)
        add_row = QHBoxLayout()
        for key, label in self.AREAS:
            button = QPushButton(f"Add to {label}")
            button.setObjectName(f"addTo{label}")
            button.clicked.connect(lambda checked=False, key=key: self.add_selected(key))
            add_row.addWidget(button)
        layout.addLayout(add_row)
        grid = QGridLayout()
        self.area_lists: dict[str, QListWidget] = {}
        for index, (key, label) in enumerate(self.AREAS):
            box = QGroupBox(label)
            inner = QVBoxLayout(box)
            widget = QListWidget()
            widget.setObjectName(f"{key}Area")
            widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            inner.addWidget(widget)
            buttons = QHBoxLayout()
            for text, handler in (("Up", -1), ("Down", 1)):
                button = QPushButton(text)
                button.clicked.connect(lambda checked=False, key=key, step=handler: self.move(key, step))
                buttons.addWidget(button)
            remove = QPushButton("Remove")
            remove.clicked.connect(lambda checked=False, key=key: self.remove(key))
            buttons.addWidget(remove)
            inner.addLayout(buttons)
            if key == "values":
                settings = QPushButton("Value Field Settings...")
                settings.clicked.connect(self.edit_value)
                inner.addWidget(settings)
            else:
                filter_button = QPushButton("Filter Items...")
                filter_button.clicked.connect(lambda checked=False, key=key: self.filter_items(key))
                inner.addWidget(filter_button)
                if key in ("rows", "columns"):
                    grouping = QComboBox()
                    grouping.addItems([group.title() if group != "none" else "No date grouping" for group in GROUPINGS])
                    grouping.setObjectName(f"{key}Grouping")
                    grouping.activated.connect(lambda index, key=key: self.set_grouping(key, GROUPINGS[index]))
                    inner.addWidget(grouping)
            self.area_lists[key] = widget
            grid.addWidget(box, index // 2, index % 2)
        layout.addLayout(grid)
        options = QHBoxLayout()
        self.layout_choice = QComboBox()
        self.layout_choice.addItems(["Compact Form", "Outline Form", "Tabular Form"])
        self.layout_choice.setCurrentIndex(LAYOUTS.index(spec.layout))
        self.subtotals = QCheckBox("Subtotals")
        self.subtotals.setChecked(spec.subtotals)
        self.grand_rows = QCheckBox("Grand Totals for Columns")
        self.grand_rows.setChecked(spec.grand_total_rows)
        self.grand_columns = QCheckBox("Grand Totals for Rows")
        self.grand_columns.setChecked(spec.grand_total_columns)
        for widget in (QLabel("Report Layout:"), self.layout_choice, self.subtotals, self.grand_rows, self.grand_columns):
            options.addWidget(widget)
        layout.addLayout(options)
        layout.addWidget(_buttons(self))
        self._refresh_lists()

    # -------------------------------------------------------------- state
    def _used(self, name: str) -> bool:
        spec = self.spec
        return name in spec.rows + spec.columns + spec.page_fields or any(value.field == name for value in spec.values)

    def _refresh_lists(self) -> None:
        for key, widget in self.area_lists.items():
            widget.clear()
            if key == "values":
                for value in self.spec.values:
                    widget.addItem(value.name)
            else:
                for name in getattr(self.spec, key):
                    grouping = self.spec.grouping_for(name)
                    widget.addItem(name if grouping == "none" else f"{name} ({grouping.title()})")
        self.field_list.blockSignals(True)
        for index in range(self.field_list.count()):
            entry = self.field_list.item(index)
            entry.setCheckState(Qt.CheckState.Checked if self._used(entry.text()) else Qt.CheckState.Unchecked)
        self.field_list.blockSignals(False)

    def _numeric(self, name: str) -> bool:
        from duddysheet.core.pivot import _records

        fields, records, _ = _records(self.workbook, self.spec)
        index = list(fields).index(name)
        values = [record[index] for record in records if record[index] is not None]
        return bool(values) and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values)

    def _field_toggled(self, entry: QListWidgetItem) -> None:
        name = entry.text()
        if entry.checkState() == Qt.CheckState.Checked:
            self.add_field(name, "values" if self._numeric(name) else "rows")
        else:
            self.remove_field(name)

    def add_field(self, name: str, area: str) -> None:
        """Place a field in an area (a field lives in one label area at a time)."""
        spec = self.remove_field_spec(self.spec, name, keep_values=area == "values")
        if area == "values":
            function = "sum" if self._numeric(name) else "count"
            spec = replace(spec, values=spec.values + (PivotValueField(name, function),))
        else:
            spec = replace(spec, **{area: getattr(spec, area) + (name,)})
        self.spec = spec
        self._refresh_lists()

    @staticmethod
    def remove_field_spec(spec: PivotSpec, name: str, *, keep_values: bool = False) -> PivotSpec:
        return replace(
            spec,
            rows=tuple(item for item in spec.rows if item != name),
            columns=tuple(item for item in spec.columns if item != name),
            page_fields=tuple(item for item in spec.page_fields if item != name),
            values=spec.values if keep_values else tuple(item for item in spec.values if item.field != name),
        )

    def remove_field(self, name: str) -> None:
        self.spec = self.remove_field_spec(self.spec, name)
        self._refresh_lists()

    def add_selected(self, area: str) -> None:
        entry = self.field_list.currentItem()
        if entry is not None:
            self.add_field(entry.text(), area)

    def _selected_index(self, area: str) -> int:
        return self.area_lists[area].currentRow()

    def remove(self, area: str) -> None:
        index = self._selected_index(area)
        if index < 0:
            return
        if area == "values":
            values = list(self.spec.values)
            del values[index]
            self.spec = replace(self.spec, values=tuple(values))
        else:
            items = list(getattr(self.spec, area))
            del items[index]
            self.spec = replace(self.spec, **{area: tuple(items)})
        self._refresh_lists()

    def move(self, area: str, step: int) -> None:
        index = self._selected_index(area)
        items = list(self.spec.values if area == "values" else getattr(self.spec, area))
        target = index + step
        if index < 0 or not 0 <= target < len(items):
            return
        items[index], items[target] = items[target], items[index]
        self.spec = replace(self.spec, **{area: tuple(items)})
        self._refresh_lists()
        self.area_lists[area].setCurrentRow(target)

    def edit_value(self) -> None:
        index = self._selected_index("values")
        if index < 0:
            return
        dialog = ValueFieldDialog(self.spec.values[index], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = list(self.spec.values)
            values[index] = dialog.value()
            self.spec = replace(self.spec, values=tuple(values))
            self._refresh_lists()

    def filter_items(self, area: str) -> None:
        index = self._selected_index(area)
        if index < 0:
            return
        name = getattr(self.spec, area)[index]
        items = field_items(self.workbook, replace(self.spec, hidden_items=()), name)
        hidden = {item for item in items if self.spec.hidden_for(name) and _hidden(self.spec, name, item)}
        dialog = ItemFilterDialog(name, items, hidden, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            others = tuple(entry for entry in self.spec.hidden_items if entry[0].casefold() != name.casefold())
            chosen = dialog.hidden_items()
            self.spec = replace(self.spec, hidden_items=others + (((name, chosen),) if chosen else ()))

    def set_grouping(self, area: str, grouping: str) -> None:
        index = self._selected_index(area)
        if index < 0:
            return
        name = getattr(self.spec, area)[index]
        others = tuple(entry for entry in self.spec.grouping if entry[0].casefold() != name.casefold())
        self.spec = replace(self.spec, grouping=others + (((name, grouping),) if grouping != "none" else ()))
        self._refresh_lists()

    def result_spec(self) -> PivotSpec:
        """Return the edited specification."""
        return replace(
            self.spec,
            layout=LAYOUTS[self.layout_choice.currentIndex()],
            subtotals=self.subtotals.isChecked(),
            grand_total_rows=self.grand_rows.isChecked(),
            grand_total_columns=self.grand_columns.isChecked(),
        )


def _hidden(spec: PivotSpec, name: str, item: Any) -> bool:
    from duddysheet.core.pivot import _identity

    return _identity(item) in spec.hidden_for(name)


class DataTableDialog(QDialog):
    """Data > What-If Analysis > Data Table: row and column input cells."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Data Table")
        form = QFormLayout(self)
        self.row_input = QLineEdit()
        self.row_input.setObjectName("rowInputCell")
        self.column_input = QLineEdit()
        self.column_input.setObjectName("columnInputCell")
        form.addRow("Row input cell:", self.row_input)
        form.addRow("Column input cell:", self.column_input)
        form.addRow(_buttons(self))
