"""Main OpenGrid window and UI command wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from excelclone.commands.base import CommandHistory
from excelclone.commands.edits import (
    AddSheetCommand,
    DeleteSheetCommand,
    SetFormatCommand,
    SetFreezePanesCommand,
)
from excelclone.core.conditional import FormatPatch
from excelclone.core.engine import FormulaEngine
from excelclone.core.refs import CellReference, parse_a1
from excelclone.core.workbook import Workbook
from excelclone.io.csv_io import read_delimited, write_delimited
from excelclone.io.native import load_ogrid, save_ogrid
from excelclone.io.xlsx_reader import read_xlsx
from excelclone.io.xlsx_writer import write_xlsx
from excelclone.ui.delegates import CellDelegate
from excelclone.ui.dialogs.format_cells import FormatCellsDialog
from excelclone.ui.formula_bar import FormulaBar
from excelclone.ui.grid_model import GridModel
from excelclone.ui.grid_view import GridView
from excelclone.ui.ribbon import Ribbon
from excelclone.ui.sheet_tabs import SheetTabs
from excelclone.util.settings import SettingsStore


class MainWindow(QMainWindow):
    """Top-level OpenGrid window using command-driven workbook mutations."""

    def __init__(
        self,
        workbook: Workbook | None = None,
        parent: Any = None,
        settings_store: SettingsStore | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("OpenGrid — Personal Spreadsheet")
        self.setMinimumSize(800, 600)
        self.resize(1280, 800)
        self.settings = settings_store or SettingsStore()
        self.current_path: Path | None = None
        self.dirty = False
        self._suppress_dirty = False

        self.engine = FormulaEngine(workbook if workbook is not None else Workbook())
        self.history = CommandHistory(limit=200)
        self.grid_model = GridModel(self.engine, self.history, self)
        self.grid = GridView()
        self.grid.setModel(self.grid_model)
        self.grid.setItemDelegate(CellDelegate(self.grid))
        self.formula_bar = FormulaBar()
        self.ribbon = Ribbon()
        self.sheet_tabs = SheetTabs()
        self.sheet_tabs.sync(self.engine.workbook)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.ribbon)
        layout.addWidget(self.formula_bar)
        layout.addWidget(self.grid, 1)
        layout.addWidget(self.sheet_tabs)
        self.setCentralWidget(container)

        self.selection_label = QLabel("Count: 0")
        self.statusBar().addPermanentWidget(self.selection_label)
        self.statusBar().showMessage("Ready")

        self._create_actions()
        self._connect_signals()
        self.on_current_cell_changed(self.grid_model.index(0, 0))
        self._update_title()

    def _create_actions(self) -> None:
        self.new_action = QAction("New", self)
        self.new_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self.new_workbook)
        self.open_action = QAction("Open...", self)
        self.open_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_file)
        self.save_action = QAction("Save", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save)
        self.save_as_action = QAction("Save As...", self)
        self.save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.save_as_action.triggered.connect(self.save_as)
        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.history.undo)
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.history.redo)
        self.recalculate_action = QAction("Recalculate", self)
        self.recalculate_action.setShortcut(Qt.Key.Key_F9)
        self.recalculate_action.triggered.connect(self.recalculate)
        self.add_sheet_action = QAction("New Sheet", self)
        self.add_sheet_action.triggered.connect(self.add_sheet)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        self._recent_menu = file_menu.addMenu("Recent Files")
        self._refresh_recent_menu()
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        sheet_menu = self.menuBar().addMenu("&Sheet")
        sheet_menu.addAction(self.add_sheet_action)
        formulas_menu = self.menuBar().addMenu("&Formulas")
        formulas_menu.addAction(self.recalculate_action)
        self.addActions(
            [
                self.undo_action,
                self.redo_action,
                self.recalculate_action,
                self.add_sheet_action,
                self.new_action,
                self.open_action,
                self.save_action,
                self.save_as_action,
            ]
        )
        self._update_history_actions(self.history)

    def _connect_signals(self) -> None:
        self.grid.currentCellChanged.connect(self.on_current_cell_changed)
        self.grid.selectionSummaryChanged.connect(self.selection_label.setText)
        self.formula_bar.commitRequested.connect(self.commit_formula_bar)
        self.formula_bar.gotoRequested.connect(self.goto_reference)
        self.sheet_tabs.addRequested.connect(self.add_sheet)
        self.sheet_tabs.activeChanged.connect(self.switch_sheet)
        self.sheet_tabs.closeRequested.connect(self.delete_sheet)
        self.history.add_listener(self._update_history_actions)
        self.history.add_listener(self._mark_dirty)
        self.grid_model.editRejected.connect(
            lambda message: self.statusBar().showMessage(message, 5000)
        )
        self.ribbon.actionRequested.connect(self._ribbon_action)

    def new_workbook(self) -> None:
        """Replace the current document with a blank workbook."""
        self._install_workbook(Workbook(), path=None)

    def open_file(self) -> None:
        """Prompt for and open a supported workbook or delimited file."""
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Open Spreadsheet",
            str(self.current_path.parent if self.current_path else Path.home()),
            (
                "Spreadsheets (*.ogrid *.xlsx *.xlsm *.csv *.tsv);;"
                "OpenGrid (*.ogrid);;Excel Workbook (*.xlsx *.xlsm);;"
                "Delimited Text (*.csv *.tsv)"
            ),
        )
        if not selected:
            return
        try:
            warnings = self.open_path(selected)
        except (OSError, ValueError, KeyError) as error:
            QMessageBox.critical(self, "Open Failed", str(error))
            return
        self._show_import_warnings(warnings)

    def open_path(self, path: str | Path) -> tuple[str, ...]:
        """Open a known path and return any dropped-feature warnings."""
        source = Path(path)
        suffix = source.suffix.lower()
        warnings: tuple[str, ...] = ()
        if suffix == ".ogrid":
            workbook = load_ogrid(source)
        elif suffix in (".xlsx", ".xlsm"):
            result = read_xlsx(source)
            workbook = result.workbook
            warnings = result.warnings
        elif suffix in (".csv", ".tsv"):
            workbook = read_delimited(source, parse_dates=True).workbook
        else:
            raise ValueError(
                f"Unsupported spreadsheet file type: {suffix or '(none)'}"
            )
        self._install_workbook(workbook, path=source)
        self.statusBar().showMessage(f"Opened {source.name}", 3000)
        return warnings

    def save(self) -> None:
        """Save to the current path or prompt for one."""
        if self.current_path is None:
            self.save_as()
            return
        try:
            self.save_path(self.current_path)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Save Failed", str(error))

    def save_as(self) -> None:
        """Prompt for a destination and save in the selected format."""
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Save Spreadsheet",
            str(self.current_path or Path.home() / "Workbook.ogrid"),
            (
                "OpenGrid (*.ogrid);;Excel Workbook (*.xlsx);;"
                "CSV (*.csv);;TSV (*.tsv)"
            ),
        )
        if not selected:
            return
        try:
            self.save_path(selected)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Save Failed", str(error))

    def save_path(self, path: str | Path) -> Path:
        """Save the current workbook using extension-based dispatch."""
        destination = Path(path)
        suffix = destination.suffix.lower()
        if suffix == ".ogrid":
            save_ogrid(self.engine.workbook, destination)
        elif suffix == ".xlsx":
            write_xlsx(self.engine.workbook, destination)
        elif suffix in (".csv", ".tsv"):
            write_delimited(self.engine.workbook, destination)
        else:
            raise ValueError(
                f"Unsupported spreadsheet file type: {suffix or '(none)'}"
            )
        self.current_path = destination
        self.dirty = False
        self.settings.add_recent_file(destination)
        self._refresh_recent_menu()
        self._update_title()
        self.statusBar().showMessage(f"Saved {destination.name}", 3000)
        return destination

    def _install_workbook(
        self,
        workbook: Workbook,
        *,
        path: Path | None,
    ) -> None:
        self.engine = FormulaEngine(workbook)
        self.grid_model.replace_engine(self.engine)
        self._suppress_dirty = True
        self.history.clear()
        self._suppress_dirty = False
        self.sheet_tabs.sync(workbook)
        self.sheet_tabs.tab_bar.setCurrentIndex(workbook.active_sheet_index)
        index = self.grid_model.index(0, 0)
        self.grid.setCurrentIndex(index)
        self.on_current_cell_changed(index)
        self.current_path = path
        self.dirty = False
        if path is not None:
            self.settings.add_recent_file(path)
        self._refresh_recent_menu()
        self._update_title()

    def _mark_dirty(self, history: CommandHistory) -> None:
        if not self._suppress_dirty:
            self.dirty = True
            self._update_title()

    def _update_title(self) -> None:
        base = "OpenGrid — Personal Spreadsheet"
        marker = "*" if self.dirty else ""
        if self.current_path is not None:
            self.setWindowTitle(f"{self.current_path.name}{marker} - {base}")
        elif self.dirty:
            self.setWindowTitle(f"Untitled{marker} - {base}")
        else:
            self.setWindowTitle(base)

    def _refresh_recent_menu(self) -> None:
        self._recent_menu.clear()
        for path in self.settings.recent_files:
            action = self._recent_menu.addAction(path)
            action.triggered.connect(
                lambda checked=False, selected=path: self._open_recent(selected)
            )
        self._recent_menu.setEnabled(bool(self.settings.recent_files))

    def _open_recent(self, path: str) -> None:
        try:
            warnings = self.open_path(path)
        except (OSError, ValueError, KeyError) as error:
            QMessageBox.critical(self, "Open Failed", str(error))
            return
        self._show_import_warnings(warnings)

    def _show_import_warnings(self, warnings: tuple[str, ...]) -> None:
        if warnings:
            QMessageBox.warning(
                self,
                "Workbook Imported With Warnings",
                "\n".join(f"- {warning}" for warning in warnings),
            )

    def on_current_cell_changed(self, index: QModelIndex) -> None:
        """Synchronize the formula bar with a current grid index."""
        if not index.isValid():
            return
        reference = CellReference(index.row(), index.column()).to_a1()
        cell = self.grid_model.sheet.get_cell(index.row(), index.column())
        self.formula_bar.set_cell(reference, cell.raw_input)

    def commit_formula_bar(self) -> None:
        """Commit formula-bar text to the current cell through the model."""
        index = self.grid.currentIndex()
        if not index.isValid():
            index = self.grid_model.index(0, 0)
            self.grid.setCurrentIndex(index)
        if self.grid_model.setData(index, self.formula_bar.editor.text()):
            self.on_current_cell_changed(index)

    def goto_reference(self, text: str) -> None:
        """Navigate to an A1 cell and optional sheet."""
        try:
            reference = parse_a1(text, default_sheet=self.grid_model.active_sheet_name)
        except ValueError as error:
            self.statusBar().showMessage(str(error), 5000)
            return
        if not isinstance(reference, CellReference):
            row, column = reference.min_row, reference.min_column
            sheet_name = reference.sheet
        else:
            row, column = reference.row, reference.column
            sheet_name = reference.sheet
        if sheet_name is not None:
            self.grid_model.set_active_sheet(sheet_name)
            self.sheet_tabs.sync(self.engine.workbook)
        index = self.grid_model.index(row, column)
        self.grid.setCurrentIndex(index)
        self.grid.scrollTo(index)
        self.on_current_cell_changed(index)

    def add_sheet(self) -> None:
        """Add a generated sheet through the command history."""
        self.history.execute(AddSheetCommand(self.engine))
        self.sheet_tabs.sync(self.engine.workbook)
        self.sheet_tabs.tab_bar.setCurrentIndex(len(self.engine.workbook) - 1)

    def delete_sheet(self, index: int) -> None:
        """Delete a tab through the command history."""
        if len(self.engine.workbook) == 1:
            self.statusBar().showMessage("A workbook must contain one sheet", 5000)
            return
        self.history.execute(DeleteSheetCommand(self.engine, index))
        self.sheet_tabs.sync(self.engine.workbook)
        self.grid_model.set_active_sheet(self.engine.workbook.active_sheet.name)

    def switch_sheet(self, index: int) -> None:
        """Switch the grid when the active tab changes."""
        if 0 <= index < len(self.engine.workbook):
            self.grid_model.set_active_sheet(self.engine.workbook.get_sheet(index).name)
            self.on_current_cell_changed(self.grid.currentIndex())

    def recalculate(self) -> None:
        """Run full workbook recalculation."""
        result = self.engine.recalculate()
        self.grid_model.refresh()
        if result.first_circular is not None:
            self.statusBar().showMessage(
                f"Circular reference: {result.first_circular.to_a1()}",
                5000,
            )
        else:
            self.statusBar().showMessage(
                f"Recalculated {len(result.recalculated)} formula cells",
                3000,
            )

    def _update_history_actions(self, history: CommandHistory) -> None:
        self.undo_action.setEnabled(history.can_undo)
        self.redo_action.setEnabled(history.can_redo)
        self.undo_action.setText(
            f"Undo {history.undo_description}" if history.can_undo else "Undo"
        )
        self.redo_action.setText(
            f"Redo {history.redo_description}" if history.can_redo else "Redo"
        )

    def _ribbon_action(self, name: str) -> None:
        actions = {
            "Undo": self.history.undo,
            "Redo": self.history.redo,
            "Copy": self.grid.copy_selection,
            "Paste": self.grid.paste_clipboard,
            "Recalculate": self.recalculate,
            "Sheet Recalculate": lambda: self.engine.recalculate(
                sheet_name=self.grid_model.active_sheet_name
            ),
            "Bold": lambda: self._toggle_format("bold"),
            "Italic": lambda: self._toggle_format("italic"),
            "Underline": lambda: self._toggle_format("underline"),
            "Font Color": lambda: self._choose_format_color("font_color"),
            "Fill": lambda: self._choose_format_color("fill_color"),
            "Wrap": lambda: self._toggle_format("wrap_text"),
            "Format Cells": self.show_format_cells,
            "Gridlines": self.toggle_gridlines,
            "Formula View": self.toggle_formula_view,
            "Zoom": self.increase_zoom,
            "Freeze Panes": self.toggle_freeze_panes,
        }
        action = actions.get(name)
        if action is not None:
            action()
        else:
            self.statusBar().showMessage(f"{name} is scheduled for a later milestone", 3000)

    def format_selection(self, patch: FormatPatch) -> None:
        """Apply a format patch to the selected bounding rectangle."""
        bounds = self.grid.selection_bounds()
        if bounds is None:
            return
        self.history.execute(
            SetFormatCommand(
                self.engine,
                self.grid_model.active_sheet_name,
                *bounds,
                patch,
            )
        )
        self.grid_model.refresh()

    def _toggle_format(self, attribute: str) -> None:
        current = self.grid.currentIndex()
        if not current.isValid():
            current = self.grid_model.index(0, 0)
            self.grid.setCurrentIndex(current)
        cell_format = self.grid_model.sheet.get_cell(
            current.row(),
            current.column(),
        ).format
        self.format_selection(FormatPatch(**{attribute: not getattr(cell_format, attribute)}))

    def _choose_format_color(self, attribute: str) -> None:
        current = self.grid.currentIndex()
        if not current.isValid():
            current = self.grid_model.index(0, 0)
        current_format = self.grid_model.sheet.get_cell(
            current.row(),
            current.column(),
        ).format
        initial = getattr(current_format, attribute) or "#ffffff"
        selected = QColorDialog.getColor(QColor(initial), self)
        if selected.isValid():
            self.format_selection(FormatPatch(**{attribute: selected.name()}))

    def show_format_cells(self) -> None:
        """Open the multi-tab Format Cells dialog for the current selection."""
        current = self.grid.currentIndex()
        if not current.isValid():
            current = self.grid_model.index(0, 0)
            self.grid.setCurrentIndex(current)
        base = self.grid_model.sheet.get_cell(current.row(), current.column()).format
        dialog = FormatCellsDialog(base, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.format_selection(dialog.format_patch())

    def toggle_gridlines(self) -> None:
        """Toggle standard grid rendering."""
        self.grid.setShowGrid(not self.grid.showGrid())

    def toggle_formula_view(self) -> None:
        """Toggle calculated values versus raw formulas."""
        self.grid_model.set_formula_view(not self.grid_model.formula_view)

    def increase_zoom(self) -> None:
        """Cycle zoom upward in useful increments, wrapping after 400%."""
        selected = self.grid.zoom_percent + 25
        self.grid.set_zoom(25 if selected > 400 else selected)
        self.statusBar().showMessage(f"Zoom: {self.grid.zoom_percent}%", 2000)

    def toggle_freeze_panes(self) -> None:
        """Freeze rows above and columns left of the current cell."""
        sheet = self.grid_model.sheet
        if sheet.freeze_panes is not None:
            self.history.execute(
                SetFreezePanesCommand(
                    self.engine,
                    self.grid_model.active_sheet_name,
                    None,
                )
            )
            self.statusBar().showMessage("Panes unfrozen", 2000)
            return
        current = self.grid.currentIndex()
        if not current.isValid() or (current.row() == 0 and current.column() == 0):
            self.statusBar().showMessage(
                "Select the first scrolling cell before freezing panes",
                3000,
            )
            return
        self.history.execute(
            SetFreezePanesCommand(
                self.engine,
                self.grid_model.active_sheet_name,
                (current.row(), current.column()),
            )
        )
        self.statusBar().showMessage(
            f"Frozen above row {current.row() + 1} and left of "
            f"{CellReference(current.row(), current.column()).to_a1()}",
            3000,
        )
