"""Excel Tables, PivotTables, and What-If data tables in the main window.

``AnalysisFeaturesMixin`` sits in front of ``ExcelFeaturesMixin`` in
``MainWindow``'s bases and reuses its action, menu, and command helpers.
Each feature has a dialog entry point plus a plain method that applies the
choice, so the work is testable without opening dialogs.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from PySide6.QtWidgets import QDialog, QInputDialog, QMenu, QMessageBox

from duddysheet.commands.analysis import (
    CreateTableCommand,
    WorkbookMutationCommand,
    add_pivot,
    create_data_table,
    delete_data_table,
    delete_pivot,
    refresh_pivots,
    rename_table,
    update_pivot,
)
from duddysheet.core.data_table import DataTableSpec, data_table_at
from duddysheet.core.pivot import PivotSpec, details_at, next_pivot_name, pivot_at
from duddysheet.core.refs import CellReference, RangeReference, parse_a1
from duddysheet.core.tables import (
    TABLE_STYLES,
    TOTAL_FUNCTIONS,
    TOTAL_LABELS,
    convert_to_range,
    find_table,
    resize_table,
    set_totals_row,
    table_at,
    update_table,
    write_totals,
)

_TITLE = "Duddy Spreadsheet"
_TABLE_OPTIONS = (
    ("bandedRows", "Banded Rows", "banded_rows"),
    ("bandedColumns", "Banded Columns", "banded_columns"),
    ("firstColumn", "First Column", "first_column"),
    ("lastColumn", "Last Column", "last_column"),
    ("filterButton", "Filter Button", "filter_button"),
)
_FIELD_NAME_MESSAGE = (
    "The PivotTable field name is not valid. To create a PivotTable report, you must use "
    "data that is organized as a list with labeled columns."
)


class AnalysisFeaturesMixin:
    """Tables, PivotTables, What-If data tables, and their tutorial."""

    # ---------------------------------------------------------------- setup
    def _install_analysis_features(self) -> None:
        a = self._action
        a("createTable", "Table...", self.create_table_dialog, ("Ctrl+T", "Ctrl+L"), tip="Organize data in a table that formats itself and grows")
        a("insertPivot", "PivotTable...", self.insert_pivot_dialog, tip="Summarize data in a PivotTable")
        a("pivotFields", "PivotTable Fields...", self.edit_pivot_fields)
        a("refreshPivot", "Refresh", self.refresh_pivot, ("Alt+F5",))
        a("refreshAll", "Refresh All", self.refresh_all, ("Ctrl+Alt+F5",))
        a("pivotSource", "Change Data Source...", self.change_pivot_source)
        a("pivotDetails", "Show Details", self.show_pivot_details)
        a("deletePivot", "Delete PivotTable", self.delete_pivot_at_cell)
        a("dataTable", "Data Table...", self.data_table_dialog, tip="Show results of a formula for many input values")
        a("deleteDataTable", "Delete Data Table", self.delete_data_table_at_cell)
        a("tableName", "Table Name...", self.rename_table_dialog)
        a("resizeTable", "Resize Table...", self.resize_table_dialog)
        a("convertToRange", "Convert to Range", self.convert_table_to_range)
        a("totalRow", "Total Row", self.toggle_total_row, ("Ctrl+Shift+T",), checkable=True)
        for key, text, option in _TABLE_OPTIONS:
            a(key, text, lambda option=option: self.toggle_table_option(option), checkable=True)
        a("summarizeWithPivot", "Summarize with PivotTable...", self.summarize_table_with_pivot)
        a("analysisHelp", "PivotTables, Tables, and What-If Tutorial...", lambda: self.show_analysis_help())
        a("practiceWorkbook", "Open Practice Workbook", self.open_practice_workbook)
        handlers = self.excel_ribbon_handlers
        handlers["PivotTable"] = self.insert_pivot_dialog
        handlers["Table"] = self.create_table_dialog
        handlers["Refresh All"] = self.refresh_all
        handlers["Data Table"] = self.data_table_dialog
        handlers["Analysis Help"] = lambda: self.show_analysis_help()
        self._extend_analysis_menus()
        self.grid.currentCellChanged.connect(lambda *_: self._update_table_actions())
        self.history.add_listener(lambda history: self._update_table_actions())
        self._update_table_actions()

    def _extend_analysis_menus(self) -> None:
        insert = self._menu("Insert")
        first = insert.actions()[0] if insert.actions() else None
        insert.insertAction(first, self.excel_actions["insertPivot"])
        insert.insertAction(first, self.excel_actions["createTable"])
        insert.insertSeparator(first)
        data = self._menu("Data")
        data.addSeparator()
        table = data.addMenu("Table")
        table.setObjectName("tableMenu")
        self._add(table, "createTable", "tableName", "resizeTable", "convertToRange", "-", "totalRow")
        totals = table.addMenu("Total Function")
        for key in TOTAL_FUNCTIONS:
            action = totals.addAction(TOTAL_LABELS[key])
            action.triggered.connect(lambda checked=False, key=key: self.set_total_function(key))
        self._add(table, *[key for key, _, _ in _TABLE_OPTIONS], "-")
        styles = table.addMenu("Table Style")
        groups: dict[str, QMenu] = {}
        for name in sorted(TABLE_STYLES, key=_style_order):
            group, number = _style_order(name)
            group_name = ("Light", "Medium", "Dark")[group]
            if group_name not in groups:
                groups[group_name] = styles.addMenu(group_name)
            action = groups[group_name].addAction(f"{group_name} {number}")
            action.triggered.connect(lambda checked=False, name=name: self.set_table_style(name))
        self._add(table, "-", "summarizeWithPivot")
        pivot = data.addMenu("PivotTable")
        pivot.setObjectName("pivotMenu")
        self._add(pivot, "insertPivot", "pivotFields", "-", "refreshPivot", "refreshAll", "pivotSource", "-", "pivotDetails", "deletePivot")
        what_if = data.addMenu("What-If Analysis")
        what_if.setObjectName("whatIfMenu")
        what_if.addAction(self.scenarios_action)
        what_if.addAction(self.goal_seek_action)
        self._add(what_if, "dataTable", "deleteDataTable")
        self._add(data, "refreshAll")
        help_menu = self._menu("Help")
        help_menu.insertAction(self.financial_help_action, self.excel_actions["analysisHelp"])

    def cell_context_menu(self) -> QMenu:
        """Add Table, PivotTable, and data table items to the cell menu."""
        menu = super().cell_context_menu()
        row, column = self._active()
        sheet = self._sheet()
        if table_at(sheet, row, column) is not None:
            menu.addSeparator()
            table = menu.addMenu("Table")
            self._add(table, "totalRow", "convertToRange", "resizeTable", "tableName", "-", "summarizeWithPivot")
        if pivot_at(sheet, row, column) is not None:
            menu.addSeparator()
            self._add(menu, "refreshPivot", "pivotFields", "pivotDetails", "pivotSource", "deletePivot")
        if data_table_at(sheet, row, column) is not None:
            menu.addSeparator()
            self._add(menu, "deleteDataTable")
        return menu

    def _update_table_actions(self) -> None:
        actions = getattr(self, "excel_actions", {})
        if "totalRow" not in actions:
            return
        row, column = self._active()
        table = table_at(self._sheet(), row, column)
        for key in ("totalRow", "tableName", "resizeTable", "convertToRange", "summarizeWithPivot") + tuple(
            key for key, _, _ in _TABLE_OPTIONS
        ):
            actions[key].setEnabled(table is not None)
        actions["totalRow"].setChecked(bool(table and table.show_totals))
        for key, _, option in _TABLE_OPTIONS:
            actions[key].setChecked(bool(table and getattr(table, option)))

    def _warn(self, text: str) -> None:
        QMessageBox.warning(self, _TITLE, text)

    def _mutate(self, label: str, mutate: Any) -> bool:
        return self._run(WorkbookMutationCommand(self.engine, label, mutate))

    def clear_selection(self, kind: str) -> None:
        """Refuse to clear part of a PivotTable or data table, as Excel does."""
        from duddysheet.core.editing import blocked_by_report

        if kind in ("all", "contents"):
            message = blocked_by_report(self._sheet(), list(self.grid.selection_ranges()))
            if message:
                self._warn(message)
                return
        super().clear_selection(kind)

    # ---------------------------------------------------------------- tables
    def _active_table(self, *, warn: bool = True) -> Any:
        row, column = self._active()
        table = table_at(self._sheet(), row, column)
        if table is None and warn:
            self._warn("Select a cell in a table first.")
        return table

    def _default_table_area(self) -> tuple[int, int, int, int]:
        from duddysheet.core.navigation import current_region

        bounds = self.grid.selection_bounds()
        row, column = self._active()
        if bounds is None or (bounds[0] == bounds[2] and bounds[1] == bounds[3]):
            return current_region(self._sheet(), row, column)
        return bounds

    def create_table_dialog(self) -> None:
        """Ctrl+T: confirm the range and headers, then create a table."""
        from duddysheet.ui.dialogs.analysis_dialogs import CreateTableDialog

        if self._protected():
            return
        row, column = self._active()
        if table_at(self._sheet(), row, column) is not None:
            self._warn("A table can't overlap another table.")
            return
        area = self._default_table_area()
        dialog = CreateTableDialog(_absolute(area), self._has_headers(area), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            _, area = self._parse_area(dialog.range.text())
        except ValueError:
            self._warn("The reference isn't valid.")
            return
        self.create_table_at(area, has_headers=dialog.headers.isChecked())

    def _has_headers(self, area: tuple[int, int, int, int]) -> bool:
        top, left, bottom, right = area
        sheet = self._sheet()
        values = [sheet.get_cell(top, column).display_value for column in range(left, right + 1)]
        if not all(isinstance(value, str) and value.strip() for value in values):
            return False
        return bottom > top

    def create_table_at(self, area: tuple[int, int, int, int], *, has_headers: bool = True, style: str = "TableStyleMedium2") -> bool:
        """Turn a range into an Excel Table."""
        done = self._run(CreateTableCommand(self.engine, self._sheet_name(), area, has_headers, style))
        if done:
            table = table_at(self._sheet(), area[0], area[1])
            if table is not None:
                self.statusBar().showMessage(f"Created {table.name}. Type below or beside it to grow it.", 5000)
        self._update_table_actions()
        return done

    def _change_table(self, label: str, change: Any) -> bool:
        table = self._active_table()
        if table is None:
            return False
        sheet_name = self._sheet_name()

        def mutate() -> None:
            sheet = self.engine.workbook.get_sheet(sheet_name)
            current = next(item for item in sheet.tables if item.name == table.name)
            change(sheet, current)

        return self._mutate(label, mutate)

    def toggle_total_row(self) -> None:
        """Show or hide the table's total row."""
        table = self._active_table()
        if table is None:
            return
        self._change_table(
            "Total row",
            lambda sheet, current: set_totals_row(self.engine.workbook, sheet.name, current, not current.show_totals),
        )
        self._update_table_actions()

    def toggle_table_option(self, option: str) -> None:
        """Toggle Banded Rows, Banded Columns, First/Last Column, or Filter Button."""
        self._change_table(
            "Table style options",
            lambda sheet, current: update_table(sheet, current, replace(current, **{option: not getattr(current, option)})),
        )
        self._update_table_actions()

    def set_table_style(self, style: str) -> None:
        """Apply a table style from the gallery."""
        self._change_table("Table style", lambda sheet, current: update_table(sheet, current, replace(current, style=style)))

    def set_total_function(self, function: str) -> None:
        """Choose the active column's total: Sum, Average, Count, and so on."""
        table = self._active_table()
        if table is None:
            return
        _, column = self._active()
        name = table.columns[column - table.left]

        def change(sheet: Any, current: Any) -> None:
            if not current.show_totals:
                current = set_totals_row(self.engine.workbook, sheet.name, current, True)
            totals = dict(current.totals)
            totals = {key: value for key, value in totals.items() if key.casefold() != name.casefold()}
            totals[name] = function
            updated = replace(current, totals=tuple(totals.items()))
            update_table(sheet, current, updated)
            write_totals(sheet, updated)

        self._change_table("Total function", change)
        self._update_table_actions()

    def rename_table_dialog(self) -> None:
        """Rename the active table; formulas follow the new name."""
        table = self._active_table()
        if table is None:
            return
        name, accepted = QInputDialog.getText(self, "Table Name", "Table Name:", text=table.name)
        if accepted and name.strip() and name.strip() != table.name:
            self.rename_table_to(table.name, name.strip())

    def rename_table_to(self, old: str, new: str) -> bool:
        """Rename a table and every structured reference to it."""
        return self._mutate("Rename table", lambda: rename_table(self.engine.workbook, old, new))

    def resize_table_dialog(self) -> None:
        """Select a new range for the table."""
        table = self._active_table()
        if table is None:
            return
        text, accepted = QInputDialog.getText(
            self,
            "Resize Table",
            "Select the new data range for your table:",
            text=_absolute(table.rect),
        )
        if accepted and text.strip():
            try:
                _, area = self._parse_area(text)
            except ValueError:
                self._warn("The reference isn't valid.")
                return
            self.resize_active_table(area)

    def resize_active_table(self, area: tuple[int, int, int, int]) -> bool:
        """Give the active table a new rectangle (headers stay in their row)."""
        return self._change_table("Resize table", lambda sheet, current: resize_table(sheet, current, area))

    def convert_table_to_range(self) -> None:
        """Keep the cells and look, but remove the table."""
        table = self._active_table()
        if table is None:
            return
        answer = QMessageBox.question(self, _TITLE, "Do you want to convert the table to a normal range?")
        if answer == QMessageBox.StandardButton.Yes:
            self.convert_active_table()

    def convert_active_table(self) -> bool:
        """Convert the active table to a range, rewriting structured references as A1."""
        from duddysheet.core.tables import structured_to_a1

        def change(sheet: Any, current: Any) -> None:
            structured_to_a1(self.engine.workbook, current.name)
            convert_to_range(sheet, current)

        done = self._change_table("Convert to range", change)
        self._update_table_actions()
        return done

    def summarize_table_with_pivot(self) -> None:
        """Start a PivotTable whose source is the active table."""
        table = self._active_table()
        if table is not None:
            self.insert_pivot_dialog(source=table.name)

    # ---------------------------------------------------------------- pivots
    def _default_pivot_source(self) -> str:
        row, column = self._active()
        table = table_at(self._sheet(), row, column)
        if table is not None:
            return table.name
        return f"{_quoted(self._sheet_name())}!{_absolute(self._default_table_area())}"

    def pivot_from_source(self, source_text: str, anchor: tuple[int, int] = (2, 0)) -> PivotSpec:
        """Build an empty PivotTable spec from a range or table name."""
        text = source_text.strip().lstrip("=")
        workbook = self.engine.workbook
        found = find_table(workbook, text)
        if found is not None:
            sheet, table = found
            spec = PivotSpec(
                next_pivot_name(workbook),
                sheet.name,
                (table.top, table.left, table.last_data_row, table.right),
                anchor,
                source_table=table.name,
            )
        else:
            try:
                sheet_name, area = self._parse_area(text)
                sheet = workbook.get_sheet(sheet_name)
            except (ValueError, KeyError) as error:
                raise ValueError("The PivotTable source reference isn't valid.") from error
            spec = PivotSpec(next_pivot_name(workbook), sheet.name, area, anchor)
        top, left, bottom, right = spec.source
        if bottom <= top:
            raise ValueError(_FIELD_NAME_MESSAGE)
        if any(sheet.get_cell(top, column).display_value in (None, "") for column in range(left, right + 1)):
            raise ValueError(_FIELD_NAME_MESSAGE)
        return spec

    def insert_pivot_dialog(self, source: str | None = None) -> None:
        """Insert > PivotTable: source, destination, then the field list."""
        from duddysheet.ui.dialogs.analysis_dialogs import CreatePivotDialog, PivotFieldsDialog

        dialog = CreatePivotDialog(source or self._default_pivot_source(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        location = None if dialog.new_sheet.isChecked() else dialog.location.text()
        try:
            host, anchor = self._pivot_location(location)
            spec = self.pivot_from_source(dialog.source.text(), anchor)
        except ValueError as error:
            self._warn(str(error))
            return
        fields = PivotFieldsDialog(self.engine.workbook, spec, self)
        if fields.exec() == QDialog.DialogCode.Accepted:
            self.create_pivot(fields.result_spec(), host)

    def _pivot_location(self, text: str | None) -> tuple[str | None, tuple[int, int]]:
        if text is None:
            return None, (2, 0)
        if not text.strip():
            raise ValueError("Enter a destination cell for the PivotTable report.")
        try:
            reference = parse_a1(text.strip().lstrip("="), default_sheet=self._sheet_name())
        except ValueError as error:
            raise ValueError("The destination reference isn't valid.") from error
        start = reference if isinstance(reference, CellReference) else reference.start
        sheet = reference.sheet or self._sheet_name()
        return self.engine.workbook.get_sheet(sheet).name, (start.row, start.column)

    def create_pivot(self, spec: PivotSpec, host: str | None = None) -> bool:
        """Create a PivotTable on a sheet, or on a new sheet when host is None."""
        workbook = self.engine.workbook

        def mutate() -> None:
            if host is None:
                sheet = workbook.add_sheet(index=workbook.active_sheet_index)
            else:
                sheet = workbook.get_sheet(host)
            add_pivot(workbook, sheet.name, spec)
            workbook.active_sheet = sheet.name

        done = self._mutate("Insert PivotTable", mutate)
        if done:
            self.sheet_tabs.sync(workbook)
            self.sheet_tabs.tab_bar.setCurrentIndex(workbook.active_sheet_index)
            self.grid.setCurrentIndex(self.grid_model.index(*spec.anchor))
        return done

    def _active_pivot(self, *, warn: bool = True) -> PivotSpec | None:
        row, column = self._active()
        spec = pivot_at(self._sheet(), row, column)
        if spec is None and warn:
            self._warn("Select a cell in a PivotTable first.")
        return spec

    def edit_pivot_fields(self) -> None:
        """Open the PivotTable Fields list for the active PivotTable."""
        from duddysheet.ui.dialogs.analysis_dialogs import PivotFieldsDialog

        spec = self._active_pivot()
        if spec is None:
            return
        dialog = PivotFieldsDialog(self.engine.workbook, spec, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_pivot(dialog.result_spec())

    def apply_pivot(self, spec: PivotSpec) -> bool:
        """Replace a PivotTable's layout and redraw it."""
        sheet_name = self._sheet_name()
        return self._mutate("PivotTable fields", lambda: update_pivot(self.engine.workbook, sheet_name, spec))

    def refresh_pivot(self) -> None:
        """Alt+F5: recompute the active PivotTable from its source."""
        spec = self._active_pivot()
        if spec is not None:
            self._mutate("Refresh PivotTable", lambda: refresh_pivots(self.engine.workbook, spec.name))

    def refresh_all(self) -> None:
        """Ctrl+Alt+F5: refresh every PivotTable and recalculate."""
        count = sum(len(sheet.pivots) for sheet in self.engine.workbook)
        if count:
            self._mutate("Refresh All", lambda: refresh_pivots(self.engine.workbook))
        else:
            self.engine.recalculate()
            self.grid_model.refresh()
        self.statusBar().showMessage(f"Refreshed {count} PivotTable(s)", 4000)

    def change_pivot_source(self) -> None:
        """Point the active PivotTable at another range or table."""
        spec = self._active_pivot()
        if spec is None:
            return
        current = spec.source_table or f"{_quoted(spec.source_sheet)}!{_absolute(spec.source)}"
        text, accepted = QInputDialog.getText(self, "Change PivotTable Data Source", "Table/Range:", text=current)
        if accepted and text.strip():
            self.set_pivot_source(text)

    def set_pivot_source(self, text: str) -> bool:
        """Change the active PivotTable's source and refresh it."""
        spec = self._active_pivot()
        if spec is None:
            return False
        try:
            fresh = self.pivot_from_source(text, spec.anchor)
        except ValueError as error:
            self._warn(str(error))
            return False
        changed = replace(spec, source_sheet=fresh.source_sheet, source=fresh.source, source_table=fresh.source_table)
        return self.apply_pivot(changed)

    def show_pivot_details(self) -> bool:
        """Show Details: list the source rows behind a value on a new sheet."""
        spec = self._active_pivot()
        if spec is None:
            return False
        row, column = self._active()
        records = details_at(self.engine.workbook, spec, row, column)
        if records is None:
            self._warn("Select a value in the PivotTable to see its details.")
            return False
        workbook = self.engine.workbook

        def mutate() -> None:
            from duddysheet.core.tables import create_table

            sheet = workbook.add_sheet(index=workbook.active_sheet_index)
            for r, values in enumerate(records):
                for c, value in enumerate(values):
                    if value not in (None, ""):
                        sheet.set_cell(r, c, value)
            if len(records) > 1:
                create_table(workbook, sheet.name, (0, 0, len(records) - 1, len(records[0]) - 1), style="TableStyleMedium2")
            workbook.active_sheet = sheet.name

        done = self._mutate("Show Details", mutate)
        if done:
            self.sheet_tabs.sync(workbook)
            self.sheet_tabs.tab_bar.setCurrentIndex(workbook.active_sheet_index)
        return done

    def delete_pivot_at_cell(self) -> None:
        """Remove the active PivotTable and its output."""
        spec = self._active_pivot()
        if spec is not None:
            sheet_name = self._sheet_name()
            self._mutate("Delete PivotTable", lambda: delete_pivot(self.engine.workbook, sheet_name, spec.name))

    # ----------------------------------------------------------- data tables
    def data_table_dialog(self) -> None:
        """Data > What-If Analysis > Data Table."""
        from duddysheet.ui.dialogs.analysis_dialogs import DataTableDialog

        bounds = self.grid.selection_bounds()
        if bounds is None or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            self._warn(
                "Select the data table range first: the formula(s) and the input values, "
                "at least two rows and two columns."
            )
            return
        dialog = DataTableDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.create_data_table_at(bounds, dialog.row_input.text(), dialog.column_input.text())

    def _input_cell(self, text: str) -> tuple[str, int, int] | None:
        text = text.strip().lstrip("=")
        if not text:
            return None
        try:
            reference = parse_a1(text, default_sheet=self._sheet_name())
        except ValueError as error:
            raise ValueError("Input cell reference is not valid.") from error
        if isinstance(reference, RangeReference):
            if reference.min_row != reference.max_row or reference.min_column != reference.max_column:
                raise ValueError("Input cell reference is not valid.")
            reference = reference.start
        sheet = reference.sheet or self._sheet_name()
        if sheet.casefold() != self._sheet_name().casefold():
            raise ValueError("Input cell reference is not valid.")
        return (self._sheet_name(), reference.row, reference.column)

    def create_data_table_at(self, bounds: tuple[int, int, int, int], row_input: str, column_input: str) -> bool:
        """Create a one- or two-variable data table over a selected range."""
        try:
            spec = DataTableSpec(*bounds, self._input_cell(row_input), self._input_cell(column_input))
        except ValueError as error:
            self._warn(str(error))
            return False
        sheet_name = self._sheet_name()
        return self._mutate("Data Table", lambda: create_data_table(self.engine.workbook, sheet_name, spec))

    def delete_data_table_at_cell(self) -> None:
        """Remove the data table under the active cell."""
        row, column = self._active()
        spec = data_table_at(self._sheet(), row, column)
        if spec is None:
            self._warn("Select a cell in a data table's results first.")
            return
        sheet_name = self._sheet_name()
        self._mutate("Delete Data Table", lambda: delete_data_table(self.engine.workbook, sheet_name, spec))

    # ------------------------------------------------------------------ help
    def show_analysis_help(self, topic: str | None = None) -> None:
        """Open the PivotTables, Tables, and What-If Analysis tutorial."""
        from duddysheet.ui.dialogs.analysis_help import AnalysisHelpDialog

        dialog = AnalysisHelpDialog(self, topic=topic)
        dialog.practiceRequested.connect(self.open_practice_workbook)
        dialog.exec()

    def open_practice_workbook(self) -> None:
        """Open a ready-made workbook with a table, a PivotTable, and a data table."""
        from duddysheet.core.analysis_help import build_practice_workbook

        if getattr(self, "dirty", False):
            answer = QMessageBox.question(
                self,
                _TITLE,
                "Open the practice workbook? Unsaved changes in this workbook will be lost.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._install_workbook(build_practice_workbook(), path=None)
        self.statusBar().showMessage("Practice workbook: Sales (table), Pivot (PivotTable), Loan (data table)", 8000)


def _style_order(name: str) -> tuple[int, int]:
    """Sort key and parts for 'TableStyleMedium2': (1, 2)."""
    for index, group in enumerate(("Light", "Medium", "Dark")):
        prefix = f"TableStyle{group}"
        if name.startswith(prefix) and name[len(prefix):].isdigit():
            return index, int(name[len(prefix):])
    return 3, 0


def _absolute(area: tuple[int, int, int, int]) -> str:
    top, left, bottom, right = area
    start = CellReference(top, left, row_absolute=True, column_absolute=True)
    end = CellReference(bottom, right, row_absolute=True, column_absolute=True)
    return RangeReference(start, end).to_a1()


def _quoted(name: str) -> str:
    from duddysheet.core.refs import quote_sheet_name

    return quote_sheet_name(name)
