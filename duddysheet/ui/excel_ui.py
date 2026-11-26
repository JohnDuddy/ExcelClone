"""Excel's editing commands, shortcuts, menus, and context menus for the main window.

``ExcelFeaturesMixin`` is mixed into ``MainWindow``. It owns no state of its
own beyond the watch list, trace arrows, and format painter; every mutation
goes through an undoable command.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from duddysheet.commands.editing import (
    ClearRangesCommand,
    CollapseOutlineCommand,
    OutlineCommand,
    SetHiddenCommand,
    SetNoteCommand,
    SetProtectionCommand,
    SetWorkbookOptionCommand,
    ShiftCellsCommand,
)
from duddysheet.commands.edits import (
    DeleteColumnsCommand,
    DeleteRowsCommand,
    InsertColumnsCommand,
    InsertRowsCommand,
    MergeCellsCommand,
    PasteCellsCommand,
    SetCellCommand,
    SetFormatCommand,
    SetRangeCommand,
    _WorkbookSnapshotCommand,
)
from duddysheet.core.cell import BorderStyle, Hyperlink, Note, SheetProtection
from duddysheet.core.conditional import FormatPatch
from duddysheet.core.refs import MAX_COLUMNS, MAX_ROWS, CellReference, RangeReference, parse_a1

PROTECTED_MESSAGE = (
    "The cell or chart you're trying to change is on a protected sheet. "
    "To make a change, unprotect the sheet. You might be requested to enter a password."
)


class _FunctionCommand(_WorkbookSnapshotCommand):
    """Snapshot command that runs an arbitrary workbook mutation."""

    def __init__(self, engine: Any, label: str, mutate: Callable[[], None]) -> None:
        self.engine = engine
        self.snapshot = None
        self._label = label
        self._mutate = mutate

    @property
    def description(self) -> str:
        return self._label

    def do(self) -> None:
        self._capture()
        self._mutate()
        self._rebuild()


class ExcelFeaturesMixin:
    """Excel editing, formatting, names, notes, auditing, outline, and protection."""

    # ---------------------------------------------------------------- setup
    def _install_excel_features(self) -> None:
        self.watch_cells: list[tuple[str, int, int]] = []
        self.watch_dock: QDockWidget | None = None
        self.excel_actions: dict[str, QAction] = {}
        self._painter_cells: Any = None
        self.excel_ribbon_handlers: dict[str, Callable[[], None]] = {}
        self._make_excel_actions()
        self._extend_menus()
        self._install_context_menus()
        self.grid.sheetStepRequested.connect(self.step_sheet)
        self.grid.selectionModel().selectionChanged.connect(lambda *_: self._apply_format_painter())
        self.calculation_label = QLabel("")
        self.calculation_label.setObjectName("calculationLabel")
        self.statusBar().addPermanentWidget(self.calculation_label)
        self.history.add_listener(lambda history: self._update_calculation_status())
        self._update_calculation_status()

    def _action(
        self,
        key: str,
        text: str,
        handler: Callable[[], None],
        shortcuts: tuple[str, ...] = (),
        *,
        tip: str = "",
        checkable: bool = False,
    ) -> QAction:
        action = QAction(text, self)
        action.setObjectName(f"{key}Action")
        if shortcuts:
            action.setShortcuts([QKeySequence(item) for item in shortcuts])
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        if tip:
            action.setStatusTip(tip)
        action.setCheckable(checkable)
        action.triggered.connect(lambda checked=False: handler())
        self.excel_actions[key] = action
        self.excel_ribbon_handlers[key] = handler
        self.addAction(action)
        return action

    def _make_excel_actions(self) -> None:
        a = self._action
        # Clipboard and editing
        a("cut", "Cut", self.grid.cut_selection, ("Ctrl+X",))
        a("copy", "Copy", self.grid.copy_selection, ("Ctrl+C",))
        a("paste", "Paste", self.grid.paste_clipboard, ("Ctrl+V",))
        a("pasteSpecial", "Paste Special...", self.paste_special_full, ("Ctrl+Alt+V",))
        a("fillDown", "Down", self.grid.fill_down, ("Ctrl+D",))
        a("fillRight", "Right", self.grid.fill_right, ("Ctrl+R",))
        a("fillUp", "Up", lambda: self._fill_toward("up"))
        a("fillLeft", "Left", lambda: self._fill_toward("left"))
        a("flashFill", "Flash Fill", self.flash_fill, ("Ctrl+E",))
        for kind, label in (("all", "Clear All"), ("formats", "Clear Formats"), ("contents", "Clear Contents"), ("notes", "Clear Notes"), ("hyperlinks", "Clear Hyperlinks")):
            a(f"clear_{kind}", label, lambda kind=kind: self.clear_selection(kind))
        a("deleteCells", "Delete...", self.delete_cells_dialog, ("Ctrl+-",))
        a("insertCells", "Insert Cells...", self.insert_cells_dialog, ("Ctrl+Shift+=", "Ctrl++"))
        a("goTo", "Go To...", self.go_to_dialog, ("Ctrl+G", "F5"))
        a("goToSpecial", "Go To Special...", self.go_to_special_dialog)
        a("selectAll", "Select All", self.grid.select_current_region_or_all, ("Ctrl+A",))
        a("replace", "Replace...", self.find_replace, ("Ctrl+H",))
        a("findAction2", "Find...", self.find_replace, ("Ctrl+F",))
        a("insertDate", "Insert Current Date", lambda: self._stamp("date"), ("Ctrl+;",))
        a("insertTime", "Insert Current Time", lambda: self._stamp("time"), ("Ctrl+Shift+;", "Ctrl+:"))
        a("copyAbove", "Copy Formula From Above", lambda: self._copy_from_above(formula=True), ("Ctrl+'",))
        a("copyValueAbove", "Copy Value From Above", lambda: self._copy_from_above(formula=False), ('Ctrl+Shift+"',))
        # Formatting
        a("formatCells", "Format Cells...", self.show_format_cells, ("Ctrl+1",))
        a("bold", "Bold", lambda: self._toggle_format("bold"), ("Ctrl+B", "Ctrl+2"))
        a("italic", "Italic", lambda: self._toggle_format("italic"), ("Ctrl+I", "Ctrl+3"))
        a("underline", "Underline", lambda: self._toggle_format("underline"), ("Ctrl+U", "Ctrl+4"))
        a("strikethrough", "Strikethrough", lambda: self._toggle_format("strikethrough"), ("Ctrl+5",))
        from duddysheet.core.styles import SHORTCUT_FORMATS

        for key, sequence in (
            ("general", ("Ctrl+Shift+~", "Ctrl+~")),
            ("currency", ("Ctrl+Shift+$", "Ctrl+$")),
            ("percent", ("Ctrl+Shift+%", "Ctrl+%")),
            ("scientific", ("Ctrl+Shift+^", "Ctrl+^")),
            ("date", ("Ctrl+Shift+#", "Ctrl+#")),
            ("time", ("Ctrl+Shift+@", "Ctrl+@")),
            ("number", ("Ctrl+Shift+!", "Ctrl+!")),
        ):
            a(f"format_{key}", f"{key.title()} Format", lambda code=SHORTCUT_FORMATS[key]: self.set_number_format(code), sequence)
        a("accounting", "Accounting Number Format", lambda: self.set_number_format("accounting"))
        a("percentStyle", "Percent Style", lambda: self.set_number_format("0%"))
        a("commaStyle", "Comma Style", lambda: self.set_number_format("comma"))
        a("increaseDecimal", "Increase Decimal", lambda: self.change_decimals(1))
        a("decreaseDecimal", "Decrease Decimal", lambda: self.change_decimals(-1))
        a("increaseFont", "Increase Font Size", lambda: self.step_font_size(1), ("Ctrl+Shift+>",))
        a("decreaseFont", "Decrease Font Size", lambda: self.step_font_size(-1), ("Ctrl+Shift+<",))
        a("outlineBorder", "Outside Borders", lambda: self.apply_borders("outside"), ("Ctrl+Shift+&", "Ctrl+&"))
        a("noBorder", "No Border", lambda: self.apply_borders("none"), ("Ctrl+Shift+_", "Ctrl+_"))
        for key, label in (("bottom", "Bottom Border"), ("top", "Top Border"), ("left", "Left Border"), ("right", "Right Border"), ("all", "All Borders"), ("thick_outside", "Thick Outside Borders"), ("bottom_double", "Bottom Double Border"), ("thick_bottom", "Thick Bottom Border"), ("top_bottom", "Top and Bottom Border")):
            a(f"border_{key}", label, lambda key=key: self.apply_borders(key))
        for key, label, attribute, value in (
            ("alignLeft", "Align Left", "horizontal_alignment", "left"),
            ("alignCenter", "Center", "horizontal_alignment", "center"),
            ("alignRight", "Align Right", "horizontal_alignment", "right"),
            ("alignTop", "Top Align", "vertical_alignment", "top"),
            ("alignMiddle", "Middle Align", "vertical_alignment", "center"),
            ("alignBottom", "Bottom Align", "vertical_alignment", "bottom"),
        ):
            a(key, label, lambda attribute=attribute, value=value: self.format_selection(FormatPatch(**{attribute: value})))
        a("increaseIndent", "Increase Indent", lambda: self.step_indent(1), ("Ctrl+Alt+Tab",))
        a("decreaseIndent", "Decrease Indent", lambda: self.step_indent(-1), ("Ctrl+Alt+Shift+Tab",))
        for key, label, angle in (("angleCounter", "Angle Counterclockwise", 45), ("angleClockwise", "Angle Clockwise", -45), ("rotateUp", "Rotate Text Up", 90), ("rotateDown", "Rotate Text Down", -90), ("noRotation", "No Rotation", 0)):
            a(key, label, lambda angle=angle: self.format_selection(FormatPatch(text_rotation=angle)))
        a("mergeCenter", "Merge & Center", lambda: self.merge_cells("center"))
        a("mergeAcross", "Merge Across", lambda: self.merge_cells("across"))
        a("mergeCells", "Merge Cells", lambda: self.merge_cells("merge"))
        a("unmerge", "Unmerge Cells", lambda: self.merge_cells("unmerge"))
        a("formatPainter", "Format Painter", self.start_format_painter)
        a("lockCell", "Lock Cell", self.toggle_lock)
        # Rows and columns
        a("hideRows", "Hide Rows", lambda: self.set_hidden("row", True), ("Ctrl+9",))
        a("unhideRows", "Unhide Rows", lambda: self.set_hidden("row", False), ("Ctrl+Shift+9", "Ctrl+("))
        a("hideColumns", "Hide Columns", lambda: self.set_hidden("column", True), ("Ctrl+0",))
        a("unhideColumns", "Unhide Columns", lambda: self.set_hidden("column", False), ("Ctrl+Shift+0", "Ctrl+)"))
        a("deleteRows", "Delete Sheet Rows", self.delete_rows)
        a("deleteColumns", "Delete Sheet Columns", self.delete_columns)
        a("autofitColumns", "AutoFit Column Width", self.autofit_selection)
        a("defaultWidth", "Default Width...", self.set_default_width)
        # Sheets
        a("newSheet", "Insert Sheet", self.add_sheet, ("Shift+F11",))
        a("nextSheet", "Next Sheet", lambda: self.step_sheet(1))
        a("previousSheet", "Previous Sheet", lambda: self.step_sheet(-1))
        # Formulas
        a("autoSum", "AutoSum", lambda: self.auto_sum("SUM"), ("Alt+=",))
        for function in ("AVERAGE", "COUNT", "MAX", "MIN"):
            a(f"autoSum_{function}", {"AVERAGE": "Average", "COUNT": "Count Numbers", "MAX": "Max", "MIN": "Min"}[function], lambda function=function: self.auto_sum(function))
        a("insertFunctionAction", "Insert Function...", self.insert_function, ("Shift+F3",))
        a("nameManager", "Name Manager...", self.name_manager, ("Ctrl+F3",))
        a("defineName", "Define Name...", self.define_name_dialog)
        a("createNames", "Create from Selection...", self.create_names_dialog, ("Ctrl+Shift+F3",))
        a("pasteName", "Use in Formula...", self.paste_name, ("F3",))
        a("tracePrecedents", "Trace Precedents", lambda: self.trace("precedents"))
        a("traceDependents", "Trace Dependents", lambda: self.trace("dependents"))
        a("removeArrows", "Remove Arrows", self.remove_arrows)
        a("showFormulas", "Show Formulas", self.toggle_formula_view, ("Ctrl+`",))
        a("errorChecking", "Error Checking...", self.error_checking)
        a("evaluateFormula", "Evaluate Formula...", self.evaluate_formula)
        a("watchWindow", "Watch Window", self.show_watch_window)
        a("calcAutomatic", "Automatic", lambda: self.set_calculation_mode("automatic"), checkable=True)
        a("calcExceptTables", "Automatic Except for Data Tables", lambda: self.set_calculation_mode("automatic_except_tables"), checkable=True)
        a("calcManual", "Manual", lambda: self.set_calculation_mode("manual"), checkable=True)
        a("iteration", "Iterative Calculation...", self.iteration_settings)
        a("calcSheet", "Calculate Sheet", self.calculate_sheet, ("Shift+F9",))
        a("calcFull", "Calculate Full", self.recalculate, ("Ctrl+Alt+F9",))
        # Data
        a("sortAscending", "Sort A to Z", lambda: self.quick_sort(False))
        a("sortDescending", "Sort Z to A", lambda: self.quick_sort(True))
        a("toggleFilter", "Filter", self.toggle_filter, ("Ctrl+Shift+L",))
        a("advancedFilter", "Advanced...", self.advanced_filter_dialog)
        a("group", "Group", lambda: self.outline(True), ("Alt+Shift+Right",))
        a("ungroup", "Ungroup", lambda: self.outline(False), ("Alt+Shift+Left",))
        a("hideDetail", "Hide Detail", lambda: self.outline_detail(False))
        a("showDetail", "Show Detail", lambda: self.outline_detail(True))
        for level in range(1, 9):
            a(f"outlineLevel{level}", f"Show Level {level}", lambda level=level: self.outline_level(level))
        a("subtotal", "Subtotal...", self.subtotal_dialog)
        a("consolidate", "Consolidate...", self.consolidate_dialog)
        # Review
        a("newNote", "New Note", self.edit_note, ("Shift+F2",))
        a("deleteNote", "Delete Note", self.delete_note)
        a("nextNote", "Next Note", lambda: self.step_note(1))
        a("previousNote", "Previous Note", lambda: self.step_note(-1))
        a("protectSheet", "Protect Sheet...", self.protect_sheet)
        a("protectWorkbook", "Protect Workbook...", self.protect_workbook)
        a("hyperlink", "Link...", self.insert_hyperlink, ("Ctrl+K",))
        # View
        a("freezeTopRow", "Freeze Top Row", lambda: self.freeze_at(1, 0))
        a("freezeFirstColumn", "Freeze First Column", lambda: self.freeze_at(0, 1))
        a("unfreeze", "Unfreeze Panes", lambda: self.freeze_at(0, 0))
        a("toggleHeadings", "Headings", self.toggle_headings, checkable=True)
        a("toggleFormulaBar", "Formula Bar", self.toggle_formula_bar, checkable=True)
        a("zoomDialog", "Zoom...", self.zoom_dialog)
        a("zoom100", "100%", lambda: self.grid.set_zoom(100))
        a("zoomSelection", "Zoom to Selection", self.zoom_to_selection)
        a("zoomIn", "Zoom In", lambda: self.grid.set_zoom(self.grid.zoom_percent + 10), ("Ctrl+Alt+=",))
        a("zoomOut", "Zoom Out", lambda: self.grid.set_zoom(self.grid.zoom_percent - 10), ("Ctrl+Alt+-",))
        self.excel_actions["toggleHeadings"].setChecked(True)
        self.excel_actions["toggleFormulaBar"].setChecked(True)

    def _menu(self, title: str) -> QMenu:
        # Menus may be children of the menu bar or of the window itself.
        bar_actions = self.menuBar().actions()
        for menu in self.findChildren(QMenu):
            if menu.title().replace("&", "") == title and menu.menuAction() in bar_actions:
                return menu
        anchors = ("Formulas",) if title == "Format" else ("Financial", "Help")
        before = next(
            (action for action in self.menuBar().actions() if action.text().replace("&", "") in anchors),
            None,
        )
        menu = QMenu(f"&{title}", self)
        if before is not None:
            self.menuBar().insertMenu(before, menu)
        else:
            self.menuBar().addMenu(menu)
        return menu

    def _add(self, menu: QMenu, *keys: str) -> None:
        for key in keys:
            if key == "-":
                menu.addSeparator()
            else:
                menu.addAction(self.excel_actions[key])

    def _extend_menus(self) -> None:
        edit = self._menu("Edit")
        edit.addSeparator()
        self._add(edit, "cut", "copy", "paste", "pasteSpecial", "-")
        fill = edit.addMenu("Fill")
        self._add(fill, "fillDown", "fillRight", "fillUp", "fillLeft", "-", "flashFill")
        clear = edit.addMenu("Clear")
        self._add(clear, "clear_all", "clear_formats", "clear_contents", "clear_notes", "clear_hyperlinks")
        self._add(edit, "deleteCells", "-", "findAction2", "replace", "goTo", "goToSpecial", "selectAll")
        insert = self._menu("Insert")
        insert.insertSeparator(insert.actions()[0] if insert.actions() else None)
        first = insert.actions()[0] if insert.actions() else None
        for key in ("insertCells", "newSheet", "insertFunctionAction", "newNote", "hyperlink"):
            insert.insertAction(first, self.excel_actions[key])
        format_menu = self._menu("Format")
        self._add(format_menu, "formatCells", "-", "bold", "italic", "underline", "strikethrough", "-")
        number = format_menu.addMenu("Number")
        self._add(number, "format_general", "format_number", "format_currency", "accounting", "format_percent", "format_scientific", "format_date", "format_time", "-", "increaseDecimal", "decreaseDecimal", "commaStyle")
        borders = format_menu.addMenu("Borders")
        self._add(borders, "border_bottom", "border_top", "border_left", "border_right", "-", "noBorder", "border_all", "outlineBorder", "border_thick_outside", "-", "border_bottom_double", "border_thick_bottom", "border_top_bottom")
        alignment = format_menu.addMenu("Alignment")
        self._add(alignment, "alignLeft", "alignCenter", "alignRight", "-", "alignTop", "alignMiddle", "alignBottom", "-", "increaseIndent", "decreaseIndent", "-", "angleCounter", "angleClockwise", "rotateUp", "rotateDown", "noRotation")
        merge = format_menu.addMenu("Merge")
        self._add(merge, "mergeCenter", "mergeAcross", "mergeCells", "unmerge")
        styles = format_menu.addMenu("Cell Styles")
        self._populate_styles(styles)
        rows = format_menu.addMenu("Rows and Columns")
        self._add(rows, "hideRows", "unhideRows", "hideColumns", "unhideColumns", "-", "autofitColumns", "defaultWidth")
        self._add(format_menu, "-", "formatPainter", "lockCell", "increaseFont", "decreaseFont")
        formulas = self._menu("Formulas")
        formulas.addSeparator()
        self._add(formulas, "insertFunctionAction")
        autosum = formulas.addMenu("AutoSum")
        self._add(autosum, "autoSum", "autoSum_AVERAGE", "autoSum_COUNT", "autoSum_MAX", "autoSum_MIN")
        self._add(formulas, "-", "nameManager", "defineName", "createNames", "pasteName", "-", "tracePrecedents", "traceDependents", "removeArrows", "showFormulas", "errorChecking", "evaluateFormula", "watchWindow", "-")
        calculation = formulas.addMenu("Calculation Options")
        self._add(calculation, "calcAutomatic", "calcExceptTables", "calcManual", "-", "iteration")
        self._add(formulas, "calcSheet", "calcFull")
        data = self._menu("Data")
        self._add(data, "sortAscending", "sortDescending", "toggleFilter", "advancedFilter", "-", "flashFill", "-", "group", "ungroup", "hideDetail", "showDetail")
        levels = data.addMenu("Outline Level")
        self._add(levels, *[f"outlineLevel{level}" for level in range(1, 9)])
        self._add(data, "subtotal", "consolidate")
        review = self._menu("Review")
        self._add(review, "newNote", "deleteNote", "previousNote", "nextNote", "-", "protectSheet", "protectWorkbook")
        view = self._menu("View")
        self._add(view, "toggleHeadings", "toggleFormulaBar", "-", "zoomDialog", "zoom100", "zoomSelection", "zoomIn", "zoomOut", "-", "freezeTopRow", "freezeFirstColumn", "unfreeze")

    def _populate_styles(self, menu: QMenu) -> None:
        from duddysheet.core.styles import CELL_STYLES

        groups: dict[str, QMenu] = {}
        for name, (group, _) in CELL_STYLES.items():
            if group not in groups:
                groups[group] = menu.addMenu(group)
            action = groups[group].addAction(name)
            action.triggered.connect(lambda checked=False, name=name: self.apply_cell_style(name))

    # ------------------------------------------------------- context menus
    def _install_context_menus(self) -> None:
        for view in (self.grid,):
            view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            view.customContextMenuRequested.connect(self._cell_menu)
            for header, axis in ((view.horizontalHeader(), "column"), (view.verticalHeader(), "row")):
                header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                header.customContextMenuRequested.connect(
                    lambda point, header=header, axis=axis: self._header_menu(header, axis, point)
                )

    def cell_context_menu(self) -> QMenu:
        """Build Excel's cell right-click menu."""
        menu = QMenu(self)
        self._add(menu, "cut", "copy", "paste", "pasteSpecial", "-", "insertCells", "deleteCells", "clear_contents", "-")
        sort = menu.addMenu("Sort")
        self._add(sort, "sortAscending", "sortDescending")
        self._add(menu, "toggleFilter", "-")
        row, column = self._active()
        if (row, column) in self.grid_model.sheet.notes:
            edit_note = menu.addAction("Edit Note")
            edit_note.triggered.connect(self.edit_note)
            self._add(menu, "deleteNote")
        else:
            self._add(menu, "newNote")
        self._add(menu, "-", "formatCells", "defineName", "hyperlink")
        return menu

    def _cell_menu(self, point: QPoint) -> None:
        self.cell_context_menu().exec(self.grid.viewport().mapToGlobal(point))

    def header_context_menu(self, axis: str) -> QMenu:
        """Build Excel's row or column header right-click menu."""
        menu = QMenu(self)
        self._add(menu, "cut", "copy", "paste", "pasteSpecial", "-")
        insert = menu.addAction("Insert")
        insert.triggered.connect(self.insert_rows if axis == "row" else self.insert_columns)
        self._add(menu, "deleteRows" if axis == "row" else "deleteColumns", "clear_contents", "-", "formatCells")
        size = menu.addAction("Row Height..." if axis == "row" else "Column Width...")
        size.triggered.connect(self.set_row_height if axis == "row" else self.set_column_width)
        if axis == "row":
            self._add(menu, "hideRows", "unhideRows")
        else:
            self._add(menu, "hideColumns", "unhideColumns")
        return menu

    def _header_menu(self, header: Any, axis: str, point: QPoint) -> None:
        index = header.logicalIndexAt(point)
        bounds = self.grid.selection_bounds()
        whole = bounds is not None and (
            (axis == "row" and bounds[1] == 0 and bounds[3] == MAX_COLUMNS - 1 and bounds[0] <= index <= bounds[2])
            or (axis == "column" and bounds[0] == 0 and bounds[2] == MAX_ROWS - 1 and bounds[1] <= index <= bounds[3])
        )
        if index >= 0 and not whole:
            if axis == "row":
                self.grid.select_block(index, 0, index, MAX_COLUMNS - 1)
            else:
                self.grid.select_block(0, index, MAX_ROWS - 1, index)
        self.header_context_menu(axis).exec(header.mapToGlobal(point))

    # -------------------------------------------------------------- helpers
    def _sheet(self) -> Any:
        return self.grid_model.sheet

    def _sheet_name(self) -> str:
        return self.grid_model.active_sheet_name

    def _active(self) -> tuple[int, int]:
        current = self.grid.currentIndex()
        return (current.row(), current.column()) if current.isValid() else (0, 0)

    def _run(self, command: Any) -> bool:
        try:
            self.history.execute(command)
        except (ValueError, IndexError, KeyError) as error:
            QMessageBox.warning(self, "Duddy Spreadsheet", str(error))
            return False
        self.grid_model.refresh()
        self.grid.sync_sheet_metadata()
        self.grid.viewport().update()
        return True

    def _protected(self, permission: str | None = None) -> bool:
        """Return True (and warn) when protection forbids changing the selection."""
        sheet = self._sheet()
        if sheet.protection is None:
            return False
        if permission is not None and getattr(sheet.protection, permission, False):
            return False
        if permission is None:
            from duddysheet.core.protection import can_edit_cell

            for top, left, bottom, right in self.grid.selection_ranges():
                if bottom - top > 2000 or right - left > 200:
                    break
                if all(can_edit_cell(sheet, row, column) for row in range(top, bottom + 1) for column in range(left, right + 1)):
                    continue
                break
            else:
                return False
        QMessageBox.warning(self, "Duddy Spreadsheet", PROTECTED_MESSAGE)
        return True

    # ------------------------------------------------------------- editing
    def clear_selection(self, kind: str) -> None:
        """Clear contents, formats, notes, hyperlinks, or everything."""
        if self._protected("format_cells" if kind == "formats" else None):
            return
        self._run(ClearRangesCommand(self.engine, self._sheet_name(), tuple(self.grid.selection_ranges()), kind))

    def _fill_toward(self, direction: str) -> None:
        bounds = self.grid.selection_bounds()
        if bounds is None:
            return
        from duddysheet.commands.edits import FillRangeCommand

        top, left, bottom, right = bounds
        source = (
            RangeReference(CellReference(bottom, left), CellReference(bottom, right))
            if direction == "up"
            else RangeReference(CellReference(top, right), CellReference(bottom, right))
        )
        target = RangeReference(CellReference(top, left), CellReference(bottom, right))
        self._run(FillRangeCommand(self.engine, self._sheet_name(), source, target))

    def insert_cells_dialog(self) -> None:
        """Insert cells, shifting existing cells, or insert entire rows/columns."""
        from duddysheet.ui.dialogs.excel_dialogs import InsertDeleteCellsDialog

        bounds = self.grid.selection_bounds()
        if bounds is None:
            return
        if bounds[1] == 0 and bounds[3] == MAX_COLUMNS - 1:
            choice = "row"
        elif bounds[0] == 0 and bounds[2] == MAX_ROWS - 1:
            choice = "column"
        else:
            dialog = InsertDeleteCellsDialog(False, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            choice = dialog.choice()
        if choice == "row":
            if not self._protected("insert_rows"):
                self.insert_rows()
        elif choice == "column":
            if not self._protected("insert_columns"):
                self.insert_columns()
        elif not self._protected():
            self._run(ShiftCellsCommand(self.engine, self._sheet_name(), bounds, choice))

    def delete_cells_dialog(self) -> None:
        """Delete cells, shifting neighbors, or delete entire rows/columns."""
        from duddysheet.ui.dialogs.excel_dialogs import InsertDeleteCellsDialog

        bounds = self.grid.selection_bounds()
        if bounds is None:
            return
        if bounds[1] == 0 and bounds[3] == MAX_COLUMNS - 1:
            choice = "row"
        elif bounds[0] == 0 and bounds[2] == MAX_ROWS - 1:
            choice = "column"
        else:
            dialog = InsertDeleteCellsDialog(True, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            choice = dialog.choice()
        if choice == "row":
            self.delete_rows()
        elif choice == "column":
            self.delete_columns()
        elif not self._protected():
            self._run(ShiftCellsCommand(self.engine, self._sheet_name(), bounds, choice))

    def delete_rows(self) -> None:
        """Delete the selected rows."""
        bounds = self.grid.selection_bounds()
        if bounds is None or self._protected("delete_rows"):
            return
        self._run(DeleteRowsCommand(self.engine, self._sheet_name(), bounds[0], bounds[2] - bounds[0] + 1))

    def delete_columns(self) -> None:
        """Delete the selected columns."""
        bounds = self.grid.selection_bounds()
        if bounds is None or self._protected("delete_columns"):
            return
        self._run(DeleteColumnsCommand(self.engine, self._sheet_name(), bounds[1], bounds[3] - bounds[1] + 1))

    def _stamp(self, kind: str) -> None:
        """Ctrl+; and Ctrl+Shift+; enter today's date or the current time."""
        row, column = self._active()
        now = datetime.now()
        editor = self.grid._open_editor()
        if editor is None and self.formula_bar.editor.hasFocus():
            editor = self.formula_bar.editor
        if editor is not None:
            stamp = now.strftime("%#m/%#d/%Y") if kind == "date" else now.strftime("%#I:%M %p")
            editor.insert(stamp)
            return
        from duddysheet.core.values import date_serial

        if kind == "date":
            value: Any = int(date_serial(now.date()))
            number_format = "m/d/yyyy"
        else:
            serial = date_serial(now)
            value = serial - int(serial)
            number_format = "h:mm AM/PM"
        if self._protected():
            return
        self._run(SetCellCommand(self.engine, self._sheet_name(), row, column, value))
        cell = self._sheet().get_cell(row, column)
        if cell.format.number_format == "General":
            self._run(SetFormatCommand(self.engine, self._sheet_name(), row, column, row, column, FormatPatch(number_format=number_format)))

    def _copy_from_above(self, *, formula: bool) -> None:
        row, column = self._active()
        if row == 0:
            return
        above = self._sheet().get_cell(row - 1, column)
        value = above.raw_input if formula else above.display_value
        if value is None or self._protected():
            return
        self._run(SetCellCommand(self.engine, self._sheet_name(), row, column, value))

    def paste_special_full(self) -> None:
        """Paste Special with Excel's paste, operation, skip-blanks, and link options."""
        from duddysheet.core.clipboard import RICH_CELL_MIME, decode_cell_matrix
        from duddysheet.ui.dialogs.excel_dialogs import PasteSpecialFullDialog

        mime = QApplication.clipboard().mimeData()
        if not mime.hasFormat(RICH_CELL_MIME):
            self.statusBar().showMessage("Paste Special needs cells copied in Duddy Spreadsheet", 3000)
            return
        try:
            cells, origin = decode_cell_matrix(bytes(mime.data(RICH_CELL_MIME)))
        except ValueError as error:
            self.statusBar().showMessage(str(error), 3000)
            return
        dialog = PasteSpecialFullDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted or self._protected():
            return
        row, column = self._active()
        source_sheet = self.grid.cut_source[0] if self.grid.cut_source else self._sheet_name()
        widths: tuple[float | None, ...] = ()
        if dialog.mode() == "column_widths":
            sheet = self._sheet()
            widths = tuple(sheet.column_widths.get(origin[1] + offset) for offset in range(len(cells[0])))
        self._run(
            PasteCellsCommand(
                self.engine,
                self._sheet_name(),
                row,
                column,
                cells,
                origin,
                dialog.mode(),
                dialog.transpose.isChecked(),
                dialog.operation_name(),
                dialog.skip_blanks.isChecked(),
                source_sheet,
                widths,
            )
        )

    def flash_fill(self) -> None:
        """Ctrl+E: fill the column from the pattern of examples already typed."""
        from duddysheet.core.flash_fill import flash_fill

        row, column = self._active()
        sheet = self._sheet()
        sources = [c for c in (column - 1, column - 2, column + 1) if 0 <= c < MAX_COLUMNS and any(sheet.get_cell(r, c).display_value not in (None, "") for r in range(max(0, row - 5), row + 5))]
        if column > 0 and column - 1 not in sources:
            sources.insert(0, column - 1)
        top = row
        while top > 0 and any(sheet.get_cell(top - 1, source).display_value not in (None, "") for source in sources):
            top -= 1
        bottom = row
        while bottom < MAX_ROWS - 1 and any(sheet.get_cell(bottom + 1, source).display_value not in (None, "") for source in sources):
            bottom += 1
        if top > 0 or sheet.get_cell(top, column).display_value is None:
            pass
        filled = flash_fill(sheet, column, top, bottom, sorted(sources))
        if not filled:
            QMessageBox.information(
                self,
                "Flash Fill",
                "Flash Fill didn't recognize a pattern. Type an example of the result in the "
                "column, then press Ctrl+E.",
            )
            return
        if self._protected():
            return

        def mutate() -> None:
            for target_row, value in filled.items():
                sheet.set_cell(target_row, column, value, cell_format=sheet.effective_format(target_row, column))

        self._run(_FunctionCommand(self.engine, "Flash Fill", mutate))
        self.statusBar().showMessage(f"Flash Fill changed {len(filled)} cells", 4000)

    # ---------------------------------------------------------- formatting
    def set_number_format(self, code: str) -> None:
        """Apply a number format (or the 'accounting'/'comma' shortcut styles)."""
        from duddysheet.core.styles import ACCOUNTING, COMMA

        code = {"accounting": ACCOUNTING, "comma": COMMA}.get(code, code)
        if not self._protected("format_cells"):
            self.format_selection(FormatPatch(number_format=code))

    def change_decimals(self, delta: int) -> None:
        """Increase or decrease displayed decimals, as Excel's Home buttons do."""
        from duddysheet.core.styles import change_decimals

        row, column = self._active()
        cell = self._sheet().get_cell(row, column)
        code = change_decimals(self._sheet().effective_format(row, column).number_format, delta, cell.display_value)
        if not self._protected("format_cells"):
            self.format_selection(FormatPatch(number_format=code))

    def step_font_size(self, direction: int) -> None:
        """Grow or shrink the font through Excel's size list."""
        sizes = [8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72]
        row, column = self._active()
        current = self._sheet().effective_format(row, column).font_size
        if direction > 0:
            size = next((value for value in sizes if value > current), current + 10)
        else:
            size = next((value for value in reversed(sizes) if value < current), max(1, current - 1))
        self.format_selection(FormatPatch(font_size=float(size)))

    def step_indent(self, direction: int) -> None:
        """Increase or decrease the indent level (0-15)."""
        row, column = self._active()
        fmt = self._sheet().effective_format(row, column)
        level = max(0, min(15, fmt.indent + direction))
        alignment = fmt.horizontal_alignment if fmt.horizontal_alignment in ("left", "right", "distributed") else "left"
        self.format_selection(FormatPatch(indent=level, horizontal_alignment=alignment))

    def apply_borders(self, kind: str) -> None:
        """Apply one of Excel's border presets to the selection."""
        bounds = self.grid.selection_bounds()
        if bounds is None or self._protected("format_cells"):
            return
        top, left, bottom, right = bounds
        thin = BorderStyle("thin", "#000000")
        thick = BorderStyle("thick", "#000000")
        double = BorderStyle("double", "#000000")
        none = BorderStyle()
        name = self._sheet_name()
        commands: list[Any] = []

        def patch(t: int, l: int, b: int, r: int, **edges: BorderStyle) -> None:
            commands.append(SetFormatCommand(self.engine, name, t, l, b, r, FormatPatch(**edges)))

        if kind == "none":
            patch(top, left, bottom, right, left_border=none, right_border=none, top_border=none, bottom_border=none)
        elif kind == "all":
            patch(top, left, bottom, right, left_border=thin, right_border=thin, top_border=thin, bottom_border=thin)
        elif kind in ("outside", "thick_outside"):
            style = thick if kind == "thick_outside" else thin
            patch(top, left, top, right, top_border=style)
            patch(bottom, left, bottom, right, bottom_border=style)
            patch(top, left, bottom, left, left_border=style)
            patch(top, right, bottom, right, right_border=style)
        elif kind == "bottom":
            patch(bottom, left, bottom, right, bottom_border=thin)
        elif kind == "top":
            patch(top, left, top, right, top_border=thin)
        elif kind == "left":
            patch(top, left, bottom, left, left_border=thin)
        elif kind == "right":
            patch(top, right, bottom, right, right_border=thin)
        elif kind == "bottom_double":
            patch(bottom, left, bottom, right, bottom_border=double)
        elif kind == "thick_bottom":
            patch(bottom, left, bottom, right, bottom_border=thick)
        elif kind == "top_bottom":
            patch(top, left, top, right, top_border=thin)
            patch(bottom, left, bottom, right, bottom_border=thin)
        for command in commands:
            self.history.execute(command)
        self.grid_model.refresh()

    def merge_cells(self, kind: str) -> None:
        """Merge & Center, Merge Across, Merge Cells, or Unmerge."""
        bounds = self.grid.selection_bounds()
        if bounds is None or self._protected("format_cells"):
            return
        top, left, bottom, right = bounds
        sheet = self._sheet()
        if kind == "unmerge":
            def mutate() -> None:
                sheet.merged_ranges = [
                    merged
                    for merged in sheet.merged_ranges
                    if merged.max_row < top or merged.min_row > bottom or merged.max_column < left or merged.min_column > right
                ]

            self._run(_FunctionCommand(self.engine, "Unmerge cells", mutate))
            return
        if kind == "across":
            def mutate_across() -> None:
                for row in range(top, bottom + 1):
                    if right > left:
                        sheet.merged_ranges.append(RangeReference(CellReference(row, left), CellReference(row, right)))

            self._run(_FunctionCommand(self.engine, "Merge across", mutate_across))
            return
        self.merge_selection()
        if kind == "center":
            self.format_selection(FormatPatch(horizontal_alignment="center"))

    def start_format_painter(self) -> None:
        """Copy the active cell's format; the next selection receives it."""
        row, column = self._active()
        self._painter_cells = self._sheet().effective_format(row, column)
        self.statusBar().showMessage("Select destination to paste formatting", 5000)

    def _apply_format_painter(self) -> None:
        if self._painter_cells is None or QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            return
        source = self._painter_cells
        self._painter_cells = None
        from dataclasses import fields

        patch = FormatPatch(**{item.name: getattr(source, item.name) for item in fields(FormatPatch) if hasattr(source, item.name)})
        self.format_selection(patch)

    def apply_cell_style(self, name: str) -> None:
        """Apply a built-in cell style to the selection."""
        from duddysheet.core.styles import style_patch

        patch = style_patch(name)
        if patch.fill_color == "":
            patch = replace(patch, fill_color=None)
            self._run(ClearRangesCommand(self.engine, self._sheet_name(), tuple(self.grid.selection_ranges()), "formats"))
        if not self._protected("format_cells"):
            self.format_selection(patch)

    def toggle_lock(self) -> None:
        """Toggle the Locked protection flag on the selection."""
        row, column = self._active()
        locked = self._sheet().effective_format(row, column).locked
        self.format_selection(FormatPatch(locked=not locked))

    def set_default_width(self) -> None:
        """Set the sheet's standard column width."""
        sheet = self._sheet()
        width, accepted = QInputDialog.getDouble(self, "Standard Width", "Standard column width:", sheet.default_column_width or 8.43, 0, 255, 2)
        if accepted:
            self._run(_FunctionCommand(self.engine, "Default width", lambda: setattr(sheet, "default_column_width", width)))

    # ---------------------------------------------------------- rows/columns
    def set_hidden(self, axis: str, hidden: bool) -> None:
        """Hide or unhide the selected rows or columns."""
        bounds = self.grid.selection_bounds()
        if bounds is None or self._protected("format_rows" if axis == "row" else "format_columns"):
            return
        first, last = (bounds[0], bounds[2]) if axis == "row" else (bounds[1], bounds[3])
        sheet = self._sheet()
        if not hidden:
            existing = sheet.hidden_rows if axis == "row" else sheet.hidden_columns
            indexes = tuple(index for index in existing if first - 1 <= index <= last + 1) or tuple(range(first, last + 1))
        else:
            indexes = tuple(range(first, last + 1))
        if len(indexes) > 100_000:
            return
        self._run(SetHiddenCommand(self.engine, self._sheet_name(), axis, indexes, hidden))

    def step_sheet(self, direction: int) -> None:
        """Ctrl+PgDn / Ctrl+PgUp: activate the next or previous visible sheet."""
        workbook = self.engine.workbook
        index = workbook.index_of(self._sheet_name())
        count = len(workbook)
        for step in range(1, count):
            candidate = (index + direction * step) % count
            if workbook.get_sheet(candidate).visible:
                self.switch_sheet(candidate)
                self.sheet_tabs.sync(workbook)
                return

    # -------------------------------------------------------------- go to
    def go_to_dialog(self) -> None:
        """F5: go to a reference or name, or open Go To Special."""
        from duddysheet.ui.dialogs.excel_dialogs import GoToDialog

        names = [item.name for item in self.engine.workbook.defined_names if item.reference is not None]
        dialog = GoToDialog(names, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.special_requested:
            self.go_to_special_dialog()
            return
        target = dialog.target()
        if target:
            self.goto_reference(target)

    def go_to_special_dialog(self) -> None:
        """Select cells by type, as Excel's Go To Special does."""
        from duddysheet.core.goto_special import cells_to_ranges, goto_special
        from duddysheet.ui.dialogs.excel_dialogs import GoToSpecialDialog

        dialog = GoToSpecialDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        cells = goto_special(
            self._sheet(),
            self.engine.workbook,
            self.grid.selection_ranges(),
            self._active(),
            dialog.kind(),
            value_types=dialog.value_types(),
        )
        self.select_cells(cells)
        if not cells:
            QMessageBox.information(self, "Go To Special", "No cells were found.")

    def select_cells(self, cells: list[tuple[int, int]]) -> None:
        """Select a set of cells compactly and activate the first."""
        from PySide6.QtCore import QItemSelection, QItemSelectionModel

        from duddysheet.core.goto_special import cells_to_ranges

        if not cells:
            return
        selection = QItemSelection()
        for top, left, bottom, right in cells_to_ranges(cells)[:5000]:
            selection.select(self.grid_model.index(top, left), self.grid_model.index(bottom, right))
        model = self.grid.selectionModel()
        model.select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        first = self.grid_model.index(*cells[0])
        model.setCurrentIndex(first, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.grid.scrollTo(first)

    # -------------------------------------------------------------- names
    def name_preview(self, defined: Any) -> str:
        """Return a short value preview for the Name Manager."""
        from duddysheet.core.evaluator import FormulaEvaluator

        try:
            value = FormulaEvaluator(self.engine.workbook).evaluate(
                "=" + defined.name if defined.scope is None else f"='{defined.scope}'!{defined.name}",
                sheet_name=defined.scope or self._sheet_name(),
            )
        except (ValueError, KeyError):
            return ""
        if isinstance(value, tuple):
            from duddysheet.core.values import to_text

            flat = [to_text(item) for row in value for item in (row if isinstance(row, tuple) else (row,))]
            return "{" + ",".join(flat[:6]) + ("..." if len(flat) > 6 else "") + "}"
        return str(getattr(value, "literal", value))

    def define_name_dialog(self) -> None:
        """Define a new name for the selection or a formula."""
        from duddysheet.ui.dialogs.excel_dialogs import NewNameDialog

        bounds = self.grid.selection_bounds() or (0, 0, 0, 0)
        reference = RangeReference(
            CellReference(bounds[0], bounds[1], sheet=self._sheet_name(), row_absolute=True, column_absolute=True),
            CellReference(bounds[2], bounds[3], sheet=self._sheet_name(), row_absolute=True, column_absolute=True),
        )
        text = reference.to_a1() if bounds[:2] != bounds[2:] else reference.start.to_a1()
        label = self._sheet().get_cell(bounds[0], bounds[1]).display_value
        from duddysheet.core.name_tools import name_from_label

        suggestion = name_from_label(label) if isinstance(label, str) else ""
        dialog = NewNameDialog(list(self.engine.workbook.sheet_names), self, name=suggestion or "", refers_to="=" + text)
        dialog.setWindowTitle("New Name")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, scope, comment, refers_to = dialog.values()
            self._define(name, refers_to, scope, comment)

    def _define(self, name: str, refers_to: str, scope: str | None, comment: str, *, replace_existing: Any = None) -> bool:
        workbook = self.engine.workbook

        def mutate() -> None:
            if replace_existing is not None:
                workbook.delete_name(*replace_existing)
            workbook.define_name(name, refers_to if refers_to.startswith("=") else "=" + refers_to, scope=scope, comment=comment)

        try:
            return self._run_strict(_FunctionCommand(self.engine, "Define name", mutate))
        except ValueError as error:
            QMessageBox.warning(self, "Name Manager", str(error))
            return False

    def _run_strict(self, command: Any) -> bool:
        self.history.execute(command)
        self.grid_model.refresh()
        return True

    def edit_name_dialog(self, name: str, scope: str | None) -> None:
        """Edit an existing defined name."""
        from duddysheet.ui.dialogs.excel_dialogs import NewNameDialog

        defined = self.engine.workbook.get_name(name, scope=scope)
        dialog = NewNameDialog(list(self.engine.workbook.sheet_names), self, name=defined.name, scope=defined.scope, comment=defined.comment, refers_to=defined.refers_to)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name, new_scope, comment, refers_to = dialog.values()
            self._define(new_name, refers_to, new_scope, comment, replace_existing=(defined.name, defined.scope))

    def delete_defined_name(self, name: str, scope: str | None) -> None:
        """Delete a defined name."""
        workbook = self.engine.workbook
        self._run(_FunctionCommand(self.engine, "Delete name", lambda: workbook.delete_name(name, scope=scope)))

    def name_manager(self) -> None:
        """Open the Name Manager."""
        from duddysheet.ui.dialogs.excel_dialogs import NameManagerDialog

        NameManagerDialog(self).exec()

    def create_names_dialog(self) -> None:
        """Create names from the selection's row and column labels."""
        from duddysheet.core.name_tools import names_from_selection
        from duddysheet.ui.dialogs.excel_dialogs import CreateNamesDialog

        bounds = self.grid.selection_bounds()
        if bounds is None:
            return
        dialog = CreateNamesDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        pairs = names_from_selection(
            self._sheet(),
            bounds,
            top_row=dialog.top.isChecked(),
            left_column=dialog.left.isChecked(),
            bottom_row=dialog.bottom.isChecked(),
            right_column=dialog.right.isChecked(),
        )
        workbook = self.engine.workbook

        def mutate() -> None:
            for name, reference in pairs:
                try:
                    workbook.delete_name(name)
                except KeyError:
                    pass
                try:
                    workbook.define_name(name, reference)
                except ValueError:
                    continue

        self._run(_FunctionCommand(self.engine, "Create names", mutate))
        self.statusBar().showMessage(f"Created {len(pairs)} names", 4000)

    def paste_name(self) -> None:
        """F3: insert a defined name into the formula being typed."""
        names = [item.name for item in self.engine.workbook.defined_names]
        if not names:
            self.statusBar().showMessage("This workbook has no defined names", 3000)
            return
        name, accepted = QInputDialog.getItem(self, "Paste Name", "Paste name:", names, 0, False)
        if not accepted:
            return
        editor = self.formula_bar.editor
        text = editor.text() or "="
        position = editor.cursorPosition() if editor.text() else 1
        editor.setText(text[:position] + name + text[position:])
        editor.setFocus()
        editor.setCursorPosition(position + len(name))

    # ---------------------------------------------------------------- notes
    def edit_note(self) -> None:
        """Shift+F2: add or edit the active cell's note."""
        from duddysheet.ui.dialogs.excel_dialogs import NoteDialog

        row, column = self._active()
        existing = self._sheet().notes.get((row, column))
        author = existing.author if existing else self.note_author()
        dialog = NoteDialog(existing.text if existing else "", author, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            text = dialog.text()
            note = Note(text, author) if text.strip() else None
            self._run(SetNoteCommand(self.engine, self._sheet_name(), row, column, note))

    def note_author(self) -> str:
        """Return the author name used for new notes."""
        import getpass

        try:
            return getpass.getuser()
        except (OSError, KeyError):
            return ""

    def delete_note(self) -> None:
        """Delete the notes in the selection."""
        self.clear_selection("notes")

    def step_note(self, direction: int) -> None:
        """Move to the next or previous note in sheet order."""
        notes = sorted(self._sheet().notes)
        if not notes:
            return
        current = self._active()
        if direction > 0:
            target = next((item for item in notes if item > current), notes[0])
        else:
            target = next((item for item in reversed(notes) if item < current), notes[-1])
        self.grid.set_active_cell(*target)

    def insert_hyperlink(self) -> None:
        """Ctrl+K: link the active cell to a URL, file, or place in the workbook."""
        row, column = self._active()
        cell = self._sheet().get_cell(row, column)
        current = cell.hyperlink.target if cell.hyperlink else "https://"
        target, accepted = QInputDialog.getText(self, "Insert Hyperlink", "Address (URL, file, or Sheet!A1):", text=current)
        if not accepted or self._protected("insert_hyperlinks"):
            return
        sheet = self._sheet()
        target = target.strip()

        def mutate() -> None:
            existing = sheet.get_cell(row, column)
            link = None
            if target:
                internal = "!" in target and "://" not in target
                link = Hyperlink(target.removeprefix("#"), internal)
            if existing.raw_input is None and target:
                sheet.set_cell(row, column, target, cell_format=existing.format, hyperlink=link)
            else:
                sheet.put_cell(row, column, replace(existing, hyperlink=link))

        self._run(_FunctionCommand(self.engine, "Insert hyperlink", mutate))

    # ------------------------------------------------------------- formulas
    def auto_sum(self, function: str) -> None:
        """Alt+=: insert SUM (or AVERAGE/COUNT/MAX/MIN) over the adjacent numbers."""
        from duddysheet.core.editing import autosum_range, range_text

        sheet = self._sheet()
        bounds = self.grid.selection_bounds()
        if bounds is None or self._protected():
            return
        top, left, bottom, right = bounds
        if (top, left) != (bottom, right):
            # A selected block gets totals below each column (and right of rows).
            values: dict[tuple[int, int], str] = {}
            for column in range(left, right + 1):
                values[(bottom + 1, column)] = f"={function}({range_text((top, column, bottom, column))})"
            def mutate() -> None:
                for (row, column), formula in values.items():
                    sheet.set_cell(row, column, formula, cell_format=sheet.effective_format(row, column))
            self._run(_FunctionCommand(self.engine, "AutoSum", mutate))
            return
        area = autosum_range(sheet, top, left)
        argument = range_text(area) if area is not None else ""
        formula = f"={function}({argument})"
        editor = self.formula_bar.editor
        editor.setText(formula)
        editor.setFocus()
        if area is None:
            editor.setCursorPosition(len(formula) - 1)
        else:
            editor.setSelection(len(function) + 2, len(argument))

    def trace(self, kind: str) -> None:
        """Draw arrows from precedents to the active cell, or to its dependents."""
        from duddysheet.core.auditing import dependents, precedents

        row, column = self._active()
        function = precedents if kind == "precedents" else dependents
        found = function(self.engine.workbook, self._sheet_name(), row, column)
        arrows = getattr(self.grid, "trace_arrows", [])
        for sheet_name, other_row, other_column in found:
            if sheet_name.casefold() != self._sheet_name().casefold():
                continue
            arrow = ((other_row, other_column), (row, column)) if kind == "precedents" else ((row, column), (other_row, other_column))
            if arrow not in arrows:
                arrows.append(arrow)
        self.grid.trace_arrows = arrows
        self.grid.viewport().update()
        if not found:
            self.statusBar().showMessage(f"This cell has no {kind}", 3000)

    def remove_arrows(self) -> None:
        """Remove trace arrows."""
        self.grid.trace_arrows = []
        self.grid.viewport().update()

    def error_checking(self) -> None:
        """Find the next cell that fails an error-checking rule."""
        from duddysheet.core.auditing import error_flags

        sheet = self._sheet()
        current = self._active()
        messages = {
            "error_value": "Error in value",
            "number_stored_as_text": "Number stored as text",
            "inconsistent_formula": "Inconsistent formula",
        }
        for coordinate, _ in sorted(sheet.iter_unordered()):
            if coordinate <= current:
                continue
            flags = error_flags(sheet, *coordinate)
            if flags:
                self.grid.set_active_cell(*coordinate)
                QMessageBox.information(self, "Error Checking", f"{CellReference(*coordinate).to_a1(include_sheet=False)}: {messages[flags[0]]}")
                return
        QMessageBox.information(self, "Error Checking", "The error check is complete for the entire sheet.")

    def evaluate_formula(self) -> None:
        """Step through the active cell's formula evaluation."""
        from duddysheet.core.auditing import evaluation_steps
        from duddysheet.ui.dialogs.excel_dialogs import EvaluateFormulaDialog

        row, column = self._active()
        steps = evaluation_steps(self.engine.workbook, self._sheet_name(), row, column)
        reference = f"{self._sheet_name()}!{CellReference(row, column).to_a1(include_sheet=False)}"
        EvaluateFormulaDialog(reference, steps, self).exec()

    def show_watch_window(self) -> None:
        """Open the Watch Window, a dock listing watched cells and values."""
        if self.watch_dock is None:
            dock = QDockWidget("Watch Window", self)
            dock.setObjectName("watchWindow")
            widget = QWidget()
            layout = QVBoxLayout(widget)
            add = QPushButton("Add Watch...")
            add.clicked.connect(self.add_watch)
            remove = QPushButton("Delete Watch")
            remove.clicked.connect(self.delete_watch)
            layout.addWidget(add)
            layout.addWidget(remove)
            self.watch_table = QTableWidget(0, 4)
            self.watch_table.setHorizontalHeaderLabels(["Sheet", "Cell", "Value", "Formula"])
            self.watch_table.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(self.watch_table)
            dock.setWidget(widget)
            self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
            self.watch_dock = dock
            self.history.add_listener(lambda history: self.refresh_watches())
        self.watch_dock.show()
        self.refresh_watches()

    def add_watch(self) -> None:
        """Watch the selected cells."""
        for top, left, bottom, right in self.grid.selection_ranges():
            for row in range(top, min(bottom, top + 50) + 1):
                for column in range(left, min(right, left + 50) + 1):
                    item = (self._sheet_name(), row, column)
                    if item not in self.watch_cells:
                        self.watch_cells.append(item)
        self.refresh_watches()

    def delete_watch(self) -> None:
        """Stop watching the selected Watch Window row."""
        row = self.watch_table.currentRow() if self.watch_dock is not None else -1
        if 0 <= row < len(self.watch_cells):
            del self.watch_cells[row]
            self.refresh_watches()

    def refresh_watches(self) -> None:
        """Refresh Watch Window values."""
        if self.watch_dock is None:
            return
        from duddysheet.core.formats import format_value

        self.watch_table.setRowCount(len(self.watch_cells))
        workbook = self.engine.workbook
        for index, (sheet_name, row, column) in enumerate(self.watch_cells):
            try:
                cell = workbook.get_sheet(sheet_name).get_cell(row, column)
            except KeyError:
                continue
            value = cell.error or format_value(cell.display_value, cell.format.number_format).text
            for position, text in enumerate((sheet_name, CellReference(row, column).to_a1(include_sheet=False), value, cell.raw_input if cell.is_formula else "")):
                self.watch_table.setItem(index, position, QTableWidgetItem(str(text)))

    def set_calculation_mode(self, mode: str) -> None:
        """Choose automatic, automatic-except-tables, or manual calculation."""
        self._run(SetWorkbookOptionCommand(self.engine, "calculation_mode", mode))
        self._update_calculation_status()

    def iteration_settings(self) -> None:
        """Enable iterative calculation and set its limits."""
        from duddysheet.ui.dialogs.excel_dialogs import IterationDialog

        workbook = self.engine.workbook
        dialog = IterationDialog(workbook.iterative_calculation, workbook.max_iterations, workbook.max_change, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = {
            "iterative_calculation": dialog.enabled.isChecked(),
            "max_iterations": dialog.iterations.value(),
            "max_change": dialog.change.value(),
        }

        def mutate() -> None:
            for key, value in settings.items():
                setattr(workbook, key, value)

        self._run(_FunctionCommand(self.engine, "Calculation options", mutate))

    def calculate_sheet(self) -> None:
        """Shift+F9: recalculate the active sheet."""
        self.engine.recalculate(sheet_name=self._sheet_name())
        self.grid_model.refresh()
        self._update_calculation_status()

    def _update_calculation_status(self) -> None:
        mode = self.engine.workbook.calculation_mode
        for key, value in (("calcAutomatic", "automatic"), ("calcExceptTables", "automatic_except_tables"), ("calcManual", "manual")):
            action = self.excel_actions.get(key)
            if action is not None:
                action.setChecked(mode == value)
        pending = mode == "manual" and bool(self.engine.pending)
        self.calculation_label.setText("Calculate" if pending else "")

    # ----------------------------------------------------------------- data
    def quick_sort(self, descending: bool) -> None:
        """Sort the current region by the active column."""
        from duddysheet.commands.edits import SortRangeCommand
        from duddysheet.core.data_tools import SortKey
        from duddysheet.core.navigation import current_region

        if self._protected("sort"):
            return
        row, column = self._active()
        bounds = self.grid.selection_bounds()
        if bounds is None:
            return
        if bounds[0] == bounds[2] and bounds[1] == bounds[3]:
            bounds = current_region(self._sheet(), row, column)
        top, left, bottom, right = bounds
        header = self._looks_like_header(top, left, right)
        target = RangeReference(CellReference(top, left), CellReference(bottom, right))
        self._run(SortRangeCommand(self.engine, self._sheet_name(), target, (SortKey(column, not descending),), header))

    def _looks_like_header(self, row: int, left: int, right: int) -> bool:
        sheet = self._sheet()
        first = [sheet.get_cell(row, column).display_value for column in range(left, right + 1)]
        second = [sheet.get_cell(row + 1, column).display_value for column in range(left, right + 1)]
        return all(isinstance(value, str) for value in first if value is not None) and any(
            isinstance(value, (int, float)) for value in second
        )

    def toggle_filter(self) -> None:
        """Ctrl+Shift+L: turn the filter on for the data region, or off."""
        if self._sheet().auto_filter is not None:
            self.clear_active_filter()
        else:
            self.filter_selection()

    def advanced_filter_dialog(self) -> None:
        """Filter a list with a criteria range, in place or copied."""
        from duddysheet.core.data_ops import advanced_filter
        from duddysheet.core.navigation import current_region
        from duddysheet.ui.dialogs.excel_dialogs import AdvancedFilterDialog

        row, column = self._active()
        region = current_region(self._sheet(), row, column)
        from duddysheet.core.editing import range_text

        dialog = AdvancedFilterDialog(range_text(region), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            list_area = self._parse_area(dialog.list_range.text())
            criteria = self._parse_area(dialog.criteria.text(), with_sheet=True) if dialog.criteria.text().strip() else None
        except ValueError as error:
            QMessageBox.warning(self, "Advanced Filter", str(error))
            return
        rows = advanced_filter(self.engine.workbook, self._sheet_name(), list_area[1], criteria, unique_only=dialog.unique.isChecked())
        sheet = self._sheet()
        top, left, bottom, right = list_area[1]
        if dialog.copy_mode():
            try:
                destination = parse_a1(dialog.copy_to.text().strip(), default_sheet=self._sheet_name())
            except ValueError as error:
                QMessageBox.warning(self, "Advanced Filter", str(error))
                return
            start = destination if isinstance(destination, CellReference) else destination.start
            values = [tuple(sheet.get_cell(top, c).display_value for c in range(left, right + 1))]
            values += [tuple(sheet.get_cell(r, c).display_value for c in range(left, right + 1)) for r in rows]
            self._run(SetRangeCommand(self.engine, start.sheet or self._sheet_name(), start.row, start.column, tuple(values)))
            return
        hidden = tuple(r for r in range(top + 1, bottom + 1) if r not in rows)

        def mutate() -> None:
            sheet.hidden_rows.difference_update(range(top + 1, bottom + 1))
            sheet.filtered_rows.difference_update(range(top + 1, bottom + 1))
            sheet.hidden_rows.update(hidden)
            sheet.filtered_rows.update(hidden)

        self._run(_FunctionCommand(self.engine, "Advanced filter", mutate))

    def _parse_area(self, text: str, *, with_sheet: bool = False) -> Any:
        reference = parse_a1(text.strip().lstrip("="), default_sheet=self._sheet_name())
        if isinstance(reference, CellReference):
            reference = RangeReference(reference, reference)
        area = (reference.min_row, reference.min_column, reference.max_row, reference.max_column)
        sheet = reference.sheet or self._sheet_name()
        return (sheet, area)

    def outline(self, group: bool) -> None:
        """Group or ungroup the selected rows (or columns)."""
        bounds = self.grid.selection_bounds()
        if bounds is None:
            return
        whole_columns = bounds[0] == 0 and bounds[2] == MAX_ROWS - 1
        axis = "column" if whole_columns else "row"
        if not whole_columns and not (bounds[1] == 0 and bounds[3] == MAX_COLUMNS - 1):
            choice, accepted = QInputDialog.getItem(self, "Group" if group else "Ungroup", "Group:", ["Rows", "Columns"], 0, False)
            if not accepted:
                return
            axis = "row" if choice == "Rows" else "column"
        first, last = (bounds[0], bounds[2]) if axis == "row" else (bounds[1], bounds[3])
        self._run(OutlineCommand(self.engine, self._sheet_name(), axis, first, last, group))

    def outline_detail(self, show: bool) -> None:
        """Show or hide the detail rows of the outline group at the active cell."""
        sheet = self._sheet()
        row, _ = self._active()
        level = sheet.row_outline.get(row, 0) or sheet.row_outline.get(row + 1, 0) or sheet.row_outline.get(row - 1, 0)
        if not level:
            return
        start = row
        while start > 0 and sheet.row_outline.get(start - 1, 0) >= level:
            start -= 1
        end = row
        while sheet.row_outline.get(end + 1, 0) >= level:
            end += 1
        indexes = tuple(index for index in range(start, end + 1) if sheet.row_outline.get(index, 0) >= level)
        self._run(CollapseOutlineCommand(self.engine, self._sheet_name(), "row", level, indexes, show))

    def outline_level(self, level: int) -> None:
        """Show outline levels up to ``level`` (the 1, 2, 3 buttons)."""
        self._run(CollapseOutlineCommand(self.engine, self._sheet_name(), "row", level))

    def subtotal_dialog(self) -> None:
        """Data > Subtotal: insert grouped SUBTOTAL rows with an outline."""
        from duddysheet.core.data_ops import SUBTOTAL_FUNCTIONS, insert_subtotals, remove_subtotals
        from duddysheet.core.navigation import current_region
        from duddysheet.ui.dialogs.excel_dialogs import SubtotalDialog

        row, column = self._active()
        region = current_region(self._sheet(), row, column)
        top, left, bottom, right = region
        headers = [str(self._sheet().get_cell(top, c).display_value or f"Column {c + 1}") for c in range(left, right + 1)]
        dialog = SubtotalDialog(headers, list(SUBTOTAL_FUNCTIONS), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        workbook = self.engine.workbook
        name = self._sheet_name()
        if dialog.remove_requested:
            self._run(_FunctionCommand(self.engine, "Remove subtotals", lambda: remove_subtotals(workbook, name, region)))
            return
        group = left + dialog.group.currentIndex()
        totals = [left + index for index in dialog.total_indexes()]
        function = dialog.function.currentText()
        below = dialog.below.isChecked()
        self._run(
            _FunctionCommand(
                self.engine,
                "Subtotal",
                lambda: insert_subtotals(workbook, name, region, group_column=group, function=function, total_columns=totals, summary_below=below),
            )
        )

    def consolidate_dialog(self) -> None:
        """Data > Consolidate: combine ranges into the active cell."""
        from duddysheet.core.data_ops import CONSOLIDATE_FUNCTIONS, consolidate
        from duddysheet.ui.dialogs.excel_dialogs import ConsolidateDialog

        dialog = ConsolidateDialog(CONSOLIDATE_FUNCTIONS, "", self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            sources = [self._parse_area(text, with_sheet=True) for text in dialog.reference_texts()]
        except ValueError as error:
            QMessageBox.warning(self, "Consolidate", str(error))
            return
        grid = consolidate(
            self.engine.workbook,
            sources,
            function=dialog.function.currentText(),
            top_row=dialog.top_row.isChecked(),
            left_column=dialog.left_column.isChecked(),
        )
        if not grid:
            return
        row, column = self._active()
        self._run(SetRangeCommand(self.engine, self._sheet_name(), row, column, tuple(tuple(line) for line in grid)))

    # ----------------------------------------------------------- protection
    def protect_sheet(self) -> None:
        """Protect the sheet, or unprotect it (asking for the password)."""
        from duddysheet.core.protection import hash_password, verify_password
        from duddysheet.ui.dialogs.excel_dialogs import PasswordDialog, ProtectSheetDialog

        sheet = self._sheet()
        if sheet.protection is not None:
            if sheet.protection.password_hash:
                dialog = PasswordDialog("Unprotect Sheet", "Password:", self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    return
                if not verify_password(sheet.protection.password_hash, dialog.password.text()):
                    QMessageBox.warning(self, "Duddy Spreadsheet", "The password you supplied is not correct.")
                    return
            self._run(SetProtectionCommand(self.engine, self._sheet_name(), None))
            self.excel_actions["protectSheet"].setText("Protect Sheet...")
            return
        dialog = ProtectSheetDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        password = dialog.password.text()
        if password:
            confirm = PasswordDialog("Confirm Password", "Reenter password to proceed.", self)
            if confirm.exec() != QDialog.DialogCode.Accepted or confirm.password.text() != password:
                QMessageBox.warning(self, "Duddy Spreadsheet", "Confirmation password is not identical.")
                return
        protection = SheetProtection(password_hash=hash_password(password), **dialog.permissions())
        self._run(SetProtectionCommand(self.engine, self._sheet_name(), protection))
        self.excel_actions["protectSheet"].setText("Unprotect Sheet...")

    def protect_workbook(self) -> None:
        """Protect or unprotect the workbook structure."""
        from duddysheet.core.protection import hash_password, verify_password
        from duddysheet.ui.dialogs.excel_dialogs import PasswordDialog

        workbook = self.engine.workbook
        if workbook.structure_protected:
            if workbook.structure_password_hash:
                dialog = PasswordDialog("Unprotect Workbook", "Password:", self)
                if dialog.exec() != QDialog.DialogCode.Accepted or not verify_password(workbook.structure_password_hash, dialog.password.text()):
                    return
            self._run(_FunctionCommand(self.engine, "Unprotect workbook", lambda: (setattr(workbook, "structure_protected", False), setattr(workbook, "structure_password_hash", ""))))
            return
        dialog = PasswordDialog("Protect Structure and Windows", "Password (optional):", self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        stored = hash_password(dialog.password.text())
        self._run(_FunctionCommand(self.engine, "Protect workbook", lambda: (setattr(workbook, "structure_protected", True), setattr(workbook, "structure_password_hash", stored))))

    # ----------------------------------------------------------------- view
    def freeze_at(self, rows: int, columns: int) -> None:
        """Freeze the top rows and/or first columns, or unfreeze."""
        from duddysheet.commands.edits import SetFreezePanesCommand

        panes = None if (rows, columns) == (0, 0) else (rows, columns)
        self._run(SetFreezePanesCommand(self.engine, self._sheet_name(), panes))

    def toggle_headings(self) -> None:
        """Show or hide row and column headings."""
        visible = self.excel_actions["toggleHeadings"].isChecked()
        self.grid.horizontalHeader().setVisible(visible)
        self.grid.verticalHeader().setVisible(visible)

    def toggle_formula_bar(self) -> None:
        """Show or hide the formula bar."""
        self.formula_bar.setVisible(self.excel_actions["toggleFormulaBar"].isChecked())

    def zoom_dialog(self) -> None:
        """View > Zoom."""
        from duddysheet.ui.dialogs.excel_dialogs import ZoomDialog

        dialog = ZoomDialog(self.grid.zoom_percent, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        choice = dialog.choice()
        if choice == "fit":
            self.zoom_to_selection()
        elif choice == "custom":
            self.grid.set_zoom(dialog.custom.value())
        else:
            self.grid.set_zoom(int(choice))

    def zoom_to_selection(self) -> None:
        """Zoom so the selection fills the window."""
        bounds = self.grid.selection_bounds()
        if bounds is None:
            return
        top, left, bottom, right = bounds
        rows = max(1, min(bottom, top + 400) - top + 1)
        columns = max(1, min(right, left + 100) - left + 1)
        viewport = self.grid.viewport().size()
        scale_rows = viewport.height() / (rows * 22)
        scale_columns = viewport.width() / (columns * 96)
        self.grid.set_zoom(int(max(10, min(400, 100 * min(scale_rows, scale_columns)))))
        self.grid.scrollTo(self.grid_model.index(top, left))
