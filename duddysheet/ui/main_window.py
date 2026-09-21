"""Main Duddy Spreadsheet window and UI command wiring."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from PySide6.QtCore import QModelIndex, QTimer, QUrl, Qt
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtGui import QColor
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from duddysheet.branding import (
    LEGACY_NATIVE_SUFFIX,
    NATIVE_FORMAT_LABEL,
    NATIVE_SUFFIX,
    PRODUCT_NAME,
)
from duddysheet.commands.base import CommandHistory
from duddysheet.commands.edits import (
    AddSheetCommand,
    AddChartCommand,
    AddSparklinesCommand,
    AddValidationCommand,
    ApplyFilterCommand,
    ClearFilterCommand,
    ClearSparklinesCommand,
    DeleteSheetCommand,
    DuplicateSheetCommand,
    InsertColumnsCommand,
    InsertRowsCommand,
    MergeCellsCommand,
    MoveSheetCommand,
    PasteCellsCommand,
    RemoveDuplicatesCommand,
    RemoveChartCommand,
    RenameSheetCommand,
    ReplaceAllCommand,
    SetCellCommand,
    SetColumnWidthCommand,
    SetFormatCommand,
    SetFreezePanesCommand,
    SetRangeCommand,
    SetRowHeightCommand,
    SetSheetTabColorCommand,
    SetSheetVisibilityCommand,
    SortRangeCommand,
    TextToColumnsCommand,
    UpdateChartCommand,
)
from duddysheet.core.chart import (
    CHART_FAMILIES,
    CHART_TYPE_LABELS,
    CHART_TYPES,
    ChartSpec,
    chart_data,
    detect_chart_headers,
    expand_chart_range,
    infer_chart_title,
    recommend_charts,
)
from duddysheet.core.clipboard import RICH_CELL_MIME, decode_cell_matrix
from duddysheet.core.conditional import FormatPatch
from duddysheet.core.data_tools import find_cells
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.financial_analysis import (
    audit_financial_model,
    evaluate_scenarios,
    goal_seek,
    one_variable_sensitivity,
    two_variable_sensitivity,
)
from duddysheet.core.financial_models import create_financial_model
from duddysheet.core.licensing import LicenseManager, LicenseStatus
from duddysheet.core.printing import (
    PageSetup,
    selection_to_area,
    with_print_area,
)
from duddysheet.core.refs import CellReference, RangeReference, parse_a1
from duddysheet.core.workbook import Workbook
from duddysheet.io.csv_io import read_delimited, write_delimited
from duddysheet.io.native import load_native, save_native
from duddysheet.io.xlsx_reader import read_xlsx
from duddysheet.io.xlsx_writer import write_xlsx
from duddysheet.ui.delegates import CellDelegate
from duddysheet.ui.charting import ChartPanel
from duddysheet.ui.dialogs.about import AboutDialog
from duddysheet.ui.dialogs.activation import ActivationDialog, prompt_when_trial_expired
from duddysheet.ui.dialogs.chart_help import ChartHelpDialog, topic_for_chart_type
from duddysheet.ui.dialogs.chart_wizard import ChartWizard
from duddysheet.ui.dialogs.sparklines import SparklineDialog, default_location
from duddysheet.ui.dialogs.format_cells import FormatCellsDialog
from duddysheet.ui.dialogs.function_help import FunctionHelpDialog
from duddysheet.ui.dialogs.page_setup import PageSetupDialog
from duddysheet.ui.printing import WorksheetRenderer, apply_setup_to_printer
from duddysheet.ui.dialogs.financial import (
    AuditReportDialog,
    FinancialModelDialog,
    GoalSeekDialog,
    ScenarioDialog,
    SensitivityDialog,
)
from duddysheet.ui.dialogs.financial_help import FinancialHelpDialog
from duddysheet.ui.dialogs.data_tools import (
    FilterDialog,
    FindReplaceDialog,
    PasteSpecialDialog,
    SortDialog,
    ValidationDialog,
)
from duddysheet.ui.formula_bar import FormulaBar
from duddysheet.ui.grid_model import GridModel
from duddysheet.ui.grid_view import GridView
from duddysheet.ui.ribbon import Ribbon, chart_menu_entries, sparkline_menu_entries
from duddysheet.ui.sheet_tabs import SheetTabs
from duddysheet.ui.tool_help import apply_tool_help
from duddysheet.util.paths import app_data_dir
from duddysheet.util.settings import SettingsStore
from duddysheet.util.autosave import AutosaveManager, RecoveryCandidate
from duddysheet.util.logging_setup import configure_logging


class MainWindow(QMainWindow):
    """Top-level Duddy Spreadsheet window using command-driven workbook mutations."""

    def __init__(
        self,
        workbook: Workbook | None = None,
        parent: Any = None,
        settings_store: SettingsStore | None = None,
        autosave_manager: AutosaveManager | None = None,
        hyperlink_opener: Callable[[QUrl], bool] | None = None,
        license_manager: LicenseManager | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Duddy Spreadsheet")
        self.setMinimumSize(800, 600)
        self.resize(1280, 800)
        self.settings = settings_store or SettingsStore()
        self.autosave_manager = autosave_manager or AutosaveManager()
        self.license_manager = license_manager or LicenseManager(app_data_dir())
        self.logger = configure_logging()
        self._hyperlink_opener = hyperlink_opener or QDesktopServices.openUrl
        self.current_path: Path | None = None
        self.dirty = False
        self._suppress_dirty = False
        self._chart_panels: dict[str, ChartPanel] = {}

        self.engine = FormulaEngine(workbook if workbook is not None else Workbook())
        self.history = CommandHistory(limit=200)
        self.grid_model = GridModel(self.engine, self.history, self)
        self.grid = GridView()
        self.grid.setModel(self.grid_model)
        self.grid.setItemDelegate(CellDelegate(self.grid))
        self.secondary_grid: GridView | None = None
        self.grid_splitter = QSplitter(Qt.Orientation.Vertical)
        self.grid_splitter.setChildrenCollapsible(False)
        self.grid_splitter.addWidget(self.grid)
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
        layout.addWidget(self.grid_splitter, 1)
        layout.addWidget(self.sheet_tabs)
        self.setCentralWidget(container)

        self.selection_label = QLabel("Count: 0")
        self.entitlement_label = QLabel("")
        self.statusBar().addPermanentWidget(self.entitlement_label)
        self.statusBar().addPermanentWidget(self.selection_label)
        self.statusBar().showMessage("Ready")

        self._create_actions()
        self._connect_signals()
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(5 * 60 * 1000)
        self.autosave_timer.timeout.connect(self.autosave_now)
        self.autosave_timer.start()
        self.on_current_cell_changed(self.grid_model.index(0, 0))
        self._update_title()
        self.refresh_entitlement()

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
        self.page_setup_action = QAction("Page Setup...", self)
        self.page_setup_action.triggered.connect(self.show_page_setup)
        self.print_preview_action = QAction("Print Preview...", self)
        self.print_preview_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self.print_preview_action.triggered.connect(self.show_print_preview)
        self.print_action = QAction("Print...", self)
        self.print_action.setShortcut(QKeySequence.StandardKey.Print)
        self.print_action.triggered.connect(self.print_sheet)
        self.export_pdf_action = QAction("Export to PDF...", self)
        self.export_pdf_action.triggered.connect(self.export_pdf)
        self.set_print_area_action = QAction("Set Print Area", self)
        self.set_print_area_action.triggered.connect(self.set_print_area)
        self.clear_print_area_action = QAction("Clear Print Area", self)
        self.clear_print_area_action.triggered.connect(self.clear_print_area)
        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.history.undo)
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.history.redo)
        self.recalculate_action = QAction("Recalculate", self)
        self.recalculate_action.setShortcut(Qt.Key.Key_F9)
        self.recalculate_action.triggered.connect(self.recalculate)
        self.financial_model_action = QAction("New Financial Model...", self)
        self.financial_model_action.triggered.connect(self.new_financial_model)
        self.goal_seek_action = QAction("Goal Seek...", self)
        self.goal_seek_action.triggered.connect(self.show_goal_seek)
        self.sensitivity_action = QAction("Sensitivity Table...", self)
        self.sensitivity_action.triggered.connect(self.show_sensitivity)
        self.scenarios_action = QAction("Scenario Analysis...", self)
        self.scenarios_action.triggered.connect(self.show_scenarios)
        self.model_audit_action = QAction("Model Audit...", self)
        self.model_audit_action.triggered.connect(self.show_model_audit)
        self.financial_help_action = QAction(
            "Financial Functions Guide...",
            self,
        )
        self.financial_help_action.setShortcut(Qt.Key.Key_F1)
        self.financial_help_action.triggered.connect(self.show_financial_help)
        for action, help_key in (
            (self.financial_model_action, "new_model"),
            (self.goal_seek_action, "goal_seek"),
            (self.sensitivity_action, "sensitivity"),
            (self.scenarios_action, "scenarios"),
            (self.model_audit_action, "audit"),
            (self.financial_help_action, "guide"),
        ):
            apply_tool_help(action, help_key)
        self.all_functions_help_action = QAction(
            "All Functions / Insert Function...",
            self,
        )
        self.all_functions_help_action.triggered.connect(self.insert_function)
        self.chart_help_action = QAction("Charts and Graphing Tutorial...", self)
        self.chart_help_action.setObjectName("chartHelpAction")
        self.chart_help_action.setStatusTip(
            "Step-by-step lessons for every chart type, chart element, and sparkline"
        )
        self.chart_help_action.triggered.connect(lambda: self.show_chart_help())
        self.recommended_charts_action = QAction("Recommended Charts...", self)
        self.recommended_charts_action.triggered.connect(self.insert_chart)
        self.quick_chart_action = QAction("Quick Chart", self)
        # Excel's Alt+F1 inserts a default chart without asking anything.
        self.quick_chart_action.setShortcut(QKeySequence("Alt+F1"))
        self.quick_chart_action.triggered.connect(self.insert_quick_chart)
        self.about_action = QAction(f"About {PRODUCT_NAME}...", self)
        self.about_action.triggered.connect(self.show_about)
        self.activation_action = QAction("Licence and Activation...", self)
        self.activation_action.triggered.connect(self.show_activation)
        self.add_sheet_action = QAction("New Sheet", self)
        self.add_sheet_action.triggered.connect(self.add_sheet)
        self.rename_sheet_action = QAction("Rename Sheet", self)
        self.rename_sheet_action.triggered.connect(self.rename_active_sheet)
        self.duplicate_sheet_action = QAction("Duplicate Sheet", self)
        self.duplicate_sheet_action.triggered.connect(self.duplicate_active_sheet)
        self.hide_sheet_action = QAction("Hide Sheet", self)
        self.hide_sheet_action.triggered.connect(self.hide_active_sheet)
        self.unhide_sheet_action = QAction("Unhide Sheet", self)
        self.unhide_sheet_action.triggered.connect(self.unhide_sheet)
        self.tab_color_action = QAction("Tab Color", self)
        self.tab_color_action.triggered.connect(self.choose_tab_color)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        self._recent_menu = file_menu.addMenu("Recent Files")
        self._refresh_recent_menu()
        file_menu.addSeparator()
        print_area_menu = file_menu.addMenu("Print Area")
        print_area_menu.addAction(self.set_print_area_action)
        print_area_menu.addAction(self.clear_print_area_action)
        file_menu.addAction(self.page_setup_action)
        file_menu.addAction(self.print_preview_action)
        file_menu.addAction(self.print_action)
        file_menu.addAction(self.export_pdf_action)
        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        self.insert_menu = self.menuBar().addMenu("&Insert")
        self._build_insert_menu(self.insert_menu)
        sheet_menu = self.menuBar().addMenu("&Sheet")
        sheet_menu.addAction(self.add_sheet_action)
        sheet_menu.addAction(self.rename_sheet_action)
        sheet_menu.addAction(self.duplicate_sheet_action)
        sheet_menu.addAction(self.hide_sheet_action)
        sheet_menu.addAction(self.unhide_sheet_action)
        sheet_menu.addAction(self.tab_color_action)
        formulas_menu = self.menuBar().addMenu("&Formulas")
        formulas_menu.addAction(self.recalculate_action)
        financial_menu = self.menuBar().addMenu("&Financial")
        self.financial_menu = financial_menu
        # Qt suppresses action tooltips inside menus unless this is enabled.
        financial_menu.setToolTipsVisible(True)
        financial_menu.addAction(self.financial_model_action)
        financial_menu.addSeparator()
        financial_menu.addAction(self.goal_seek_action)
        financial_menu.addAction(self.sensitivity_action)
        financial_menu.addAction(self.scenarios_action)
        financial_menu.addSeparator()
        financial_menu.addAction(self.model_audit_action)
        financial_menu.addAction(self.financial_help_action)
        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.chart_help_action)
        help_menu.addAction(self.financial_help_action)
        help_menu.addAction(self.all_functions_help_action)
        help_menu.addSeparator()
        help_menu.addAction(self.activation_action)
        help_menu.addAction(self.about_action)
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
                self.rename_sheet_action,
                self.duplicate_sheet_action,
                self.hide_sheet_action,
                self.unhide_sheet_action,
                self.tab_color_action,
                self.financial_model_action,
                self.goal_seek_action,
                self.sensitivity_action,
                self.scenarios_action,
                self.model_audit_action,
                self.financial_help_action,
                self.all_functions_help_action,
                self.quick_chart_action,
            ]
        )
        self._update_history_actions(self.history)

    def _connect_signals(self) -> None:
        self.grid.currentCellChanged.connect(self.on_current_cell_changed)
        self.grid.selectionSummaryChanged.connect(self.selection_label.setText)
        self.grid.externalHyperlinkRequested.connect(self._open_external_hyperlink)
        self.grid.internalHyperlinkRequested.connect(self.goto_reference)
        self.formula_bar.commitRequested.connect(self.commit_formula_bar)
        self.formula_bar.gotoRequested.connect(self.goto_reference)
        self.sheet_tabs.addRequested.connect(self.add_sheet)
        self.sheet_tabs.activeChanged.connect(self.switch_sheet)
        self.sheet_tabs.closeRequested.connect(self.delete_sheet)
        self.sheet_tabs.moved.connect(self.move_sheet)
        self.sheet_tabs.renameRequested.connect(self.rename_sheet_at)
        self.history.add_listener(self._update_history_actions)
        self.history.add_listener(self._mark_dirty)
        self.history.add_listener(self._sync_sheet_view)
        self.grid_model.editRejected.connect(
            lambda message: self.statusBar().showMessage(message, 5000)
        )
        self.ribbon.actionRequested.connect(self._ribbon_action)
        self._sync_grid_metadata()
        self._sync_charts()

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
                "Spreadsheets (*.dsheet *.ogrid *.xlsx *.xlsm *.csv *.tsv);;"
                f"{NATIVE_FORMAT_LABEL} (*.dsheet *.ogrid);;"
                "Excel Workbook (*.xlsx *.xlsm);;"
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
        if suffix in (NATIVE_SUFFIX, LEGACY_NATIVE_SUFFIX):
            workbook = load_native(source)
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
            str(self.current_path or Path.home() / f"Workbook{NATIVE_SUFFIX}"),
            (
                f"{NATIVE_FORMAT_LABEL} (*.dsheet);;Excel Workbook (*.xlsx);;"
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
        previous_path = self.current_path
        suffix = destination.suffix.lower()
        if suffix == ".dsheet":
            save_native(self.engine.workbook, destination)
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
        self.autosave_manager.clear_for_source(previous_path)
        if destination != previous_path:
            self.autosave_manager.clear_for_source(destination)
        self.settings.add_recent_file(destination)
        self._refresh_recent_menu()
        self._update_title()
        self.statusBar().showMessage(f"Saved {destination.name}", 3000)
        return destination

    def autosave_now(self) -> RecoveryCandidate | None:
        """Persist a recovery snapshot when the workbook has unsaved changes."""
        if not self.dirty:
            return None
        try:
            candidate = self.autosave_manager.save(
                self.engine.workbook,
                self.current_path,
            )
        except (OSError, ValueError, TypeError):
            self.logger.exception("Autosave failed")
            self.statusBar().showMessage("Autosave failed; see the local log", 5000)
            return None
        self.logger.info("Autosaved workbook to %s", candidate.autosave_path)
        self.statusBar().showMessage("Recovery copy saved", 2000)
        return candidate

    def offer_recovery(self) -> None:
        """Offer the newest recovery snapshot after application startup."""
        candidates = self.autosave_manager.candidates()
        if not candidates:
            return
        candidate = candidates[0]
        source_name = (
            candidate.source_path.name
            if candidate.source_path is not None
            else "Untitled workbook"
        )
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Recover Unsaved Workbook")
        dialog.setText(f"A recovery copy is available for {source_name}.")
        dialog.setInformativeText(
            f"Saved {candidate.saved_at.astimezone():%Y-%m-%d %H:%M:%S %Z}. "
            "Recover it, discard it, or keep it for the next launch."
        )
        recover_button = dialog.addButton(
            "Recover",
            QMessageBox.ButtonRole.AcceptRole,
        )
        discard_button = dialog.addButton(
            "Discard",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        dialog.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked is discard_button:
            self.autosave_manager.discard(candidate)
            self.logger.info("Discarded recovery copy %s", candidate.autosave_path)
            return
        if clicked is not recover_button:
            return
        try:
            workbook = self.autosave_manager.recover(candidate)
        except (OSError, ValueError):
            self.logger.exception("Recovery failed for %s", candidate.autosave_path)
            QMessageBox.critical(
                self,
                "Recovery Failed",
                "The recovery copy could not be opened. See the local log for details.",
            )
            return
        self._install_workbook(workbook, path=candidate.source_path)
        self.dirty = True
        self._update_title()
        self.statusBar().showMessage("Recovered unsaved workbook", 5000)

    def _install_workbook(
        self,
        workbook: Workbook,
        *,
        path: Path | None,
    ) -> None:
        self._dispose_chart_panels()
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
        self._sync_grid_metadata()
        self._sync_charts()
        self.current_path = path
        self.dirty = False
        if path is not None:
            self.settings.add_recent_file(path)
        self._refresh_recent_menu()
        self._update_title()

    def _mark_dirty(self, history: CommandHistory | None = None) -> None:
        """Flag unsaved changes.

        Accepts an optional history so it can serve both as a command-history
        listener and as a direct call for edits that are not commands, such as
        changing the page setup.
        """
        del history
        if not self._suppress_dirty:
            self.dirty = True
            self._update_title()

    def _update_title(self) -> None:
        base = PRODUCT_NAME
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
            try:
                reference = self.engine.workbook.get_name(
                    text.removeprefix("#"),
                    scope=self.grid_model.active_sheet_name,
                ).reference
            except (KeyError, ValueError):
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

    def _open_external_hyperlink(self, target: str) -> None:
        """Open a safe external hyperlink with the Windows default handler."""
        parsed = QUrl(target)
        if not parsed.scheme():
            path = Path(target)
            if not path.is_absolute() and self.current_path is not None:
                path = self.current_path.parent / path
            url = (
                QUrl.fromLocalFile(str(path.resolve()))
                if path.exists()
                else QUrl.fromUserInput(target)
            )
        else:
            url = parsed
        if not url.isValid() or url.scheme().casefold() not in {
            "http",
            "https",
            "mailto",
            "file",
            "ftp",
        }:
            self.statusBar().showMessage(
                f"Blocked unsupported hyperlink: {target}",
                5000,
            )
            return
        if not self._hyperlink_opener(url):
            self.statusBar().showMessage(f"Could not open hyperlink: {target}", 5000)

    def add_sheet(self) -> None:
        """Add a generated sheet through the command history."""
        self.history.execute(AddSheetCommand(self.engine))
        self.sheet_tabs.sync(self.engine.workbook)
        self.sheet_tabs.tab_bar.setCurrentIndex(len(self.engine.workbook) - 1)

    def move_sheet(self, old_index: int, new_index: int) -> None:
        """Move a dragged tab through history."""
        if old_index == new_index:
            return
        self.history.execute(
            MoveSheetCommand(self.engine, old_index, new_index)
        )
        self.sheet_tabs.sync(self.engine.workbook)

    def rename_sheet_at(self, index: int) -> None:
        """Prompt to rename a sheet tab."""
        if 0 <= index < len(self.engine.workbook):
            self._prompt_rename_sheet(index)

    def rename_active_sheet(self) -> None:
        """Prompt to rename the active sheet."""
        self._prompt_rename_sheet(self.engine.workbook.active_sheet_index)

    def _prompt_rename_sheet(self, index: int) -> None:
        sheet = self.engine.workbook.get_sheet(index)
        name, accepted = QInputDialog.getText(
            self,
            "Rename Sheet",
            "Sheet name",
            text=sheet.name,
        )
        if not accepted or name == sheet.name:
            return
        try:
            self.history.execute(
                RenameSheetCommand(self.engine, sheet.name, name)
            )
        except ValueError as error:
            self.statusBar().showMessage(str(error), 3000)

    def duplicate_active_sheet(self) -> None:
        """Duplicate the active sheet."""
        self.history.execute(
            DuplicateSheetCommand(
                self.engine,
                self.engine.workbook.active_sheet.name,
            )
        )

    def hide_active_sheet(self) -> None:
        """Hide the active sheet while retaining one visible sheet."""
        try:
            self.history.execute(
                SetSheetVisibilityCommand(
                    self.engine,
                    self.engine.workbook.active_sheet.name,
                    False,
                )
            )
        except ValueError as error:
            self.statusBar().showMessage(str(error), 3000)

    def unhide_sheet(self) -> None:
        """Prompt to unhide one hidden sheet."""
        hidden = [sheet.name for sheet in self.engine.workbook if not sheet.visible]
        if not hidden:
            self.statusBar().showMessage("There are no hidden sheets", 2000)
            return
        name, accepted = QInputDialog.getItem(
            self,
            "Unhide Sheet",
            "Sheet",
            hidden,
            editable=False,
        )
        if accepted:
            self.history.execute(
                SetSheetVisibilityCommand(self.engine, name, True)
            )

    def choose_tab_color(self) -> None:
        """Choose the active sheet's tab color."""
        sheet = self.engine.workbook.active_sheet
        selected = QColorDialog.getColor(
            QColor(sheet.tab_color or "#4f81bd"),
            self,
        )
        if selected.isValid():
            self.history.execute(
                SetSheetTabColorCommand(
                    self.engine,
                    sheet.name,
                    selected.name(),
                )
            )

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
            self._sync_grid_metadata()
            self._sync_charts()

    def recalculate(self) -> None:
        """Run full workbook recalculation."""
        result = self.engine.recalculate()
        self.grid_model.refresh()
        self._refresh_charts()
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

    def _sync_sheet_view(self, history: CommandHistory) -> None:
        """Synchronize tabs and sparse sheet metadata after a command."""
        active_name = self.engine.workbook.active_sheet.name
        if self.grid_model.active_sheet_name != active_name:
            self.grid_model.set_active_sheet(active_name)
        self.sheet_tabs.sync(self.engine.workbook)
        self._sync_grid_metadata()
        self._sync_charts()

    def _build_insert_menu(self, menu: Any) -> None:
        """Fill the Insert menu: chart families, sparklines, and help."""
        menu.addAction(self.recommended_charts_action)
        menu.addAction(self.quick_chart_action)
        menu.addSeparator()
        for family, entries in chart_menu_entries(
            tuple(family for family, _ in CHART_FAMILIES)
        ):
            submenu = menu.addMenu(family)
            for label, action_name in entries:
                action = submenu.addAction(label)
                action.triggered.connect(
                    lambda checked=False, name=action_name: self._ribbon_action(name)
                )
        menu.addSeparator()
        sparkline_menu = menu.addMenu("Sparklines")
        for _, entries in sparkline_menu_entries():
            for label, action_name in entries:
                if action_name == "Clear Sparklines":
                    sparkline_menu.addSeparator()
                action = sparkline_menu.addAction(label)
                action.triggered.connect(
                    lambda checked=False, name=action_name: self._ribbon_action(name)
                )
        menu.addSeparator()
        menu.addAction(self.chart_help_action)

    def _ribbon_action(self, name: str) -> None:
        if name.startswith("chart:"):
            self.insert_chart_of_type(name.partition(":")[2])
            return
        if name.startswith("sparkline:"):
            self.insert_sparklines(name.partition(":")[2])
            return
        actions = {
            "Undo": self.history.undo,
            "Redo": self.history.redo,
            "Copy": self.grid.copy_selection,
            "Paste": self.grid.paste_clipboard,
            "Paste Special": self.paste_special,
            "Recalculate": self.recalculate,
            "Insert Function": self.insert_function,
            "Sheet Recalculate": lambda: self.engine.recalculate(
                sheet_name=self.grid_model.active_sheet_name
            ),
            "Model Templates": self.new_financial_model,
            "Goal Seek": self.show_goal_seek,
            "Sensitivity": self.show_sensitivity,
            "Scenarios": self.show_scenarios,
            "Model Audit": self.show_model_audit,
            "Financial Help": self.show_financial_help,
            "Bold": lambda: self._toggle_format("bold"),
            "Italic": lambda: self._toggle_format("italic"),
            "Underline": lambda: self._toggle_format("underline"),
            "Font Color": lambda: self._choose_format_color("font_color"),
            "Fill": lambda: self._choose_format_color("fill_color"),
            "Wrap": lambda: self._toggle_format("wrap_text"),
            "Merge": self.merge_selection,
            "Row Height": self.set_row_height,
            "Column Width": self.set_column_width,
            "Autofit": self.autofit_selection,
            "Find": self.find_replace,
            "Format Cells": self.show_format_cells,
            "Gridlines": self.toggle_gridlines,
            "Formula View": self.toggle_formula_view,
            "Zoom": self.increase_zoom,
            "Freeze Panes": self.toggle_freeze_panes,
            "Split View": self.toggle_split_view,
            "Rows": self.insert_rows,
            "Columns": self.insert_columns,
            "Sort": self.sort_selection,
            "Filter": self.filter_selection,
            "Clear Filter": self.clear_active_filter,
            "Validate": self.validate_selection,
            "Remove Duplicates": self.remove_duplicates,
            "Text to Columns": self.text_to_columns,
            "Chart": self.insert_chart,
            "Chart Studio": self.insert_chart,
            "Quick Chart": self.insert_quick_chart,
            "Clear Sparklines": self.clear_sparklines,
            "Chart Help": self.show_chart_help,
        }
        action = actions.get(name)
        if action is not None:
            action()
        else:
            self.statusBar().showMessage(f"Unknown command: {name}", 3000)

    def insert_function(self) -> None:
        """Insert a selected registry function into the formula bar."""
        dialog = FunctionHelpDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        template = dialog.formula_template()
        if not template:
            return
        self.formula_bar.editor.setText(template)
        self.formula_bar.editor.setFocus()
        self.formula_bar.editor.setCursorPosition(len(template) - 1)

    def new_financial_model(self) -> None:
        """Replace the document with a selected built-in financial model."""
        dialog = FinancialModelDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if self.dirty:
            choice = QMessageBox.question(
                self,
                "Replace Unsaved Workbook",
                "The current workbook has unsaved changes. Replace it with the model?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if choice != QMessageBox.StandardButton.Yes:
                return
        try:
            workbook = create_financial_model(dialog.template_key())
        except ValueError as error:
            QMessageBox.critical(self, "Model Creation Failed", str(error))
            return
        self._install_workbook(workbook, path=None)
        self.dirty = True
        self._update_title()
        self.statusBar().showMessage(
            f"Created {dialog.models.currentText()} model",
            5000,
        )

    def show_goal_seek(self) -> None:
        """Solve a one-input target and optionally apply the result."""
        dialog = GoalSeekDialog(self._current_reference(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            request = dialog.request()
            result = goal_seek(
                self.engine.workbook,
                request.formula_cell,
                request.input_cell,
                request.target,
                default_sheet=self.grid_model.active_sheet_name,
                tolerance=request.tolerance,
                minimum=request.minimum,
                maximum=request.maximum,
            )
        except (ValueError, OverflowError) as error:
            QMessageBox.warning(self, "Goal Seek Failed", str(error))
            return
        if not result.converged:
            QMessageBox.warning(
                self,
                "Goal Seek Did Not Converge",
                (
                    f"Best input: {result.input_value:.12g}\n"
                    f"Result: {result.result_value:.12g}\n"
                    f"Residual: {result.residual:.6g}"
                ),
            )
            return
        choice = QMessageBox.question(
            self,
            "Apply Goal Seek Result",
            (
                f"Set {request.input_cell} to {result.input_value:.12g}?\n"
                f"{request.formula_cell} = {result.result_value:.12g}\n"
                f"Iterations: {result.iterations}"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if choice != QMessageBox.StandardButton.Yes:
            return
        reference = self._analysis_cell_reference(request.input_cell)
        self.history.execute(
            SetCellCommand(
                self.engine,
                reference.sheet,
                reference.row,
                reference.column,
                result.input_value,
            )
        )
        self.statusBar().showMessage("Goal Seek result applied", 4000)

    def show_sensitivity(self) -> None:
        """Calculate and write a one- or two-variable sensitivity table."""
        dialog = SensitivityDialog(self._current_reference(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            request = dialog.request()
            if request.column_input_cell is None:
                table = one_variable_sensitivity(
                    self.engine.workbook,
                    request.formula_cell,
                    request.row_input_cell,
                    request.row_values,
                    default_sheet=self.grid_model.active_sheet_name,
                )
                values = (
                    ("Input", *table.row_values),
                    ("Result", *table.values[0]),
                )
            else:
                table = two_variable_sensitivity(
                    self.engine.workbook,
                    request.formula_cell,
                    request.row_input_cell,
                    request.row_values,
                    request.column_input_cell,
                    request.column_values,
                    default_sheet=self.grid_model.active_sheet_name,
                )
                values = (
                    (request.formula_cell, *table.row_values),
                    *tuple(
                        (column_value, *row_values)
                        for column_value, row_values in zip(
                            table.column_values,
                            table.values,
                        )
                    ),
                )
            self._write_analysis_table(
                request.output_cell,
                tuple(tuple(row) for row in values),
            )
        except (ValueError, OverflowError) as error:
            QMessageBox.warning(self, "Sensitivity Failed", str(error))
            return
        self.statusBar().showMessage("Sensitivity table written", 4000)

    def show_scenarios(self) -> None:
        """Calculate named scenarios and write their output table."""
        dialog = ScenarioDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            request = dialog.request()
            results = evaluate_scenarios(
                self.engine.workbook,
                request.scenarios,
                request.output_cells,
                default_sheet=self.grid_model.active_sheet_name,
            )
            values = (
                ("Scenario", *request.output_cells),
                *tuple(
                    (result.name, *(value for _, value in result.values))
                    for result in results
                ),
            )
            self._write_analysis_table(
                request.destination_cell,
                tuple(tuple(row) for row in values),
            )
        except (ValueError, OverflowError) as error:
            QMessageBox.warning(self, "Scenario Analysis Failed", str(error))
            return
        self.statusBar().showMessage("Scenario analysis written", 4000)

    def show_model_audit(self) -> None:
        """Recalculate and display prioritized financial-model findings."""
        self.engine.recalculate()
        report = audit_financial_model(self.engine.workbook)
        AuditReportDialog(report, self).exec()

    def show_financial_help(self) -> None:
        """Open the comprehensive offline financial modeling guide."""
        FinancialHelpDialog(self).exec()

    def show_about(self) -> None:
        """Open product identity, licence, and third-party attribution."""
        AboutDialog(self).exec()

    def show_activation(self) -> None:
        """Open licence activation and refresh the status indicator."""
        ActivationDialog(self.license_manager, self).exec()
        self.refresh_entitlement()

    def refresh_entitlement(self) -> None:
        """Update the status-bar entitlement label."""
        entitlement = self.license_manager.entitlement()
        self.entitlement_label.setText(entitlement.summary)
        expiring_soon = (
            entitlement.status is LicenseStatus.TRIAL
            and entitlement.trial_days_remaining <= 5
        )
        self.entitlement_label.setStyleSheet(
            "color: #b00020;" if not entitlement.allows_use or expiring_soon else ""
        )

    def check_entitlement_on_start(self) -> bool:
        """Prompt for activation when the trial has lapsed.

        The application stays open when the trial ends. Refusing to launch
        would strand a user's own files behind a paywall, and a recovery
        snapshot may still be pending.
        """
        entitlement = self.license_manager.entitlement()
        allowed = prompt_when_trial_expired(entitlement, self.license_manager, self)
        self.refresh_entitlement()
        return allowed

    def active_page_setup(self) -> PageSetup:
        """Return the active sheet's print layout, or the default."""
        stored = getattr(self.engine.workbook.active_sheet, "page_setup", None)
        return stored if isinstance(stored, PageSetup) else PageSetup()

    def _renderer(self) -> WorksheetRenderer:
        """Build a renderer bound to the active sheet and its print layout."""
        return WorksheetRenderer(
            self.engine.workbook.active_sheet,
            self.active_page_setup(),
            workbook=self.engine.workbook,
            document_name=(
                self.current_path.name if self.current_path else "Untitled"
            ),
            document_path=str(self.current_path) if self.current_path else "",
        )

    def show_page_setup(self) -> None:
        """Edit and store the active sheet's print layout."""
        sheet = self.engine.workbook.active_sheet
        dialog = PageSetupDialog(
            self.active_page_setup(), self, sheet_name=sheet.name
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        sheet.page_setup = dialog.page_setup()
        self._mark_dirty()

    def set_print_area(self) -> None:
        """Restrict printing to the current selection."""
        selection = self.grid.selectionModel().selection()
        if not selection:
            QMessageBox.information(
                self, "Set Print Area", "Select the cells to print first."
            )
            return
        bounds = selection.first()
        sheet = self.engine.workbook.active_sheet
        sheet.page_setup = with_print_area(
            self.active_page_setup(),
            selection_to_area(
                bounds.top(),
                bounds.left(),
                bounds.bottom(),
                bounds.right(),
                sheet.name,
            ),
        )
        self._mark_dirty()
        self.statusBar().showMessage("Print area set", 3000)

    def clear_print_area(self) -> None:
        """Print the whole used range again."""
        sheet = self.engine.workbook.active_sheet
        sheet.page_setup = with_print_area(self.active_page_setup(), None)
        self._mark_dirty()
        self.statusBar().showMessage("Print area cleared", 3000)

    def _warn_if_nothing_to_print(self, renderer: WorksheetRenderer) -> bool:
        """Report an empty print job and return whether it was empty."""
        if renderer.page_count:
            return False
        QMessageBox.information(
            self,
            "Nothing to Print",
            "This sheet has no content in the selected print area.",
        )
        return True

    def show_print_preview(self) -> None:
        """Preview the active sheet exactly as it will print."""
        renderer = self._renderer()
        if self._warn_if_nothing_to_print(renderer):
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        apply_setup_to_printer(printer, renderer.setup)
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle(f"Print Preview - {self.engine.workbook.active_sheet.name}")
        preview.paintRequested.connect(
            lambda target: self._paint_preview(renderer, target)
        )
        preview.exec()

    @staticmethod
    def _paint_preview(renderer: WorksheetRenderer, printer: QPrinter) -> None:
        """Render every page onto the preview's printer device."""
        renderer.print_to(printer)

    def print_sheet(self) -> None:
        """Send the active sheet to a printer the user chooses."""
        renderer = self._renderer()
        if self._warn_if_nothing_to_print(renderer):
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        apply_setup_to_printer(printer, renderer.setup)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Print")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            pages = renderer.print_to(printer)
        except (OSError, RuntimeError) as error:
            QMessageBox.critical(self, "Print Failed", str(error))
            return
        self.statusBar().showMessage(f"Sent {pages} page(s) to the printer", 4000)

    def export_pdf(self) -> None:
        """Write the active sheet to a PDF file."""
        renderer = self._renderer()
        if self._warn_if_nothing_to_print(renderer):
            return

        default = self.current_path.with_suffix(".pdf") if self.current_path else (
            Path.home() / f"{self.engine.workbook.active_sheet.name}.pdf"
        )
        selected, _ = QFileDialog.getSaveFileName(
            self, "Export to PDF", str(default), "PDF Document (*.pdf)"
        )
        if not selected:
            return
        try:
            written = renderer.export_pdf(selected)
        except (OSError, RuntimeError) as error:
            QMessageBox.critical(self, "Export Failed", str(error))
            return
        self.statusBar().showMessage(
            f"Exported {renderer.page_count} page(s) to {written.name}", 4000
        )

    def _current_reference(self) -> str:
        current = self.grid.currentIndex()
        if not current.isValid():
            return "A1"
        return CellReference(current.row(), current.column()).to_a1()

    def _analysis_cell_reference(self, text: str) -> CellReference:
        parsed = parse_a1(
            text.strip(),
            default_sheet=self.grid_model.active_sheet_name,
        )
        if not isinstance(parsed, CellReference):
            raise ValueError(f"Expected one cell reference: {text!r}")
        sheet_name = self.engine.workbook.get_sheet(
            parsed.sheet or self.grid_model.active_sheet_name
        ).name
        return CellReference(parsed.row, parsed.column, sheet=sheet_name)

    def _write_analysis_table(
        self,
        destination: str,
        values: tuple[tuple[Any, ...], ...],
    ) -> None:
        reference = self._analysis_cell_reference(destination)
        self.history.execute(
            SetRangeCommand(
                self.engine,
                reference.sheet,
                reference.row,
                reference.column,
                values,
            )
        )

    def paste_special(self) -> None:
        """Paste rich clipboard cells using a selected content mode."""
        mime = QApplication.clipboard().mimeData()
        if not mime.hasFormat(RICH_CELL_MIME):
            self.statusBar().showMessage(
                "Paste Special requires cells copied inside Duddy Spreadsheet",
                3000,
            )
            return
        try:
            cells, origin = decode_cell_matrix(bytes(mime.data(RICH_CELL_MIME)))
        except ValueError as error:
            self.statusBar().showMessage(str(error), 3000)
            return
        dialog = PasteSpecialDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        current = self.grid.currentIndex()
        if not current.isValid():
            current = self.grid_model.index(0, 0)
        self.history.execute(
            PasteCellsCommand(
                self.engine,
                self.grid_model.active_sheet_name,
                current.row(),
                current.column(),
                cells,
                origin,
                dialog.mode.currentText(),
                dialog.transpose.isChecked(),
            )
        )

    def insert_chart(self) -> None:
        """Create a range-bound chart through the live-preview Chart Studio."""
        target = expand_chart_range(
            self.engine.workbook,
            self.grid_model.active_sheet_name,
            self._selected_range(),
        )
        if len(target) < 2:
            self.statusBar().showMessage(
                "Select a data range or a cell inside a contiguous data table",
                4000,
            )
            return
        wizard = ChartWizard(
            self.grid_model.active_sheet_name,
            target.to_a1(),
            self,
            workbook=self.engine.workbook,
        )
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            spec = wizard.chart_spec()
            self.history.execute(
                AddChartCommand(
                    self.engine,
                    self.grid_model.active_sheet_name,
                    spec,
                )
            )
        except ValueError as error:
            self.statusBar().showMessage(str(error), 3000)

    def insert_quick_chart(self) -> None:
        """Create the highest-ranked chart from the current data selection."""
        sheet_name = self.grid_model.active_sheet_name
        target = expand_chart_range(
            self.engine.workbook,
            sheet_name,
            self._selected_range(),
        )
        if len(target) < 2:
            self.statusBar().showMessage(
                "Quick Chart needs a data range or a cell inside a data table",
                4000,
            )
            return
        recommendations = recommend_charts(
            self.engine.workbook,
            sheet_name,
            target,
            has_headers=detect_chart_headers(
                self.engine.workbook,
                sheet_name,
                target,
            ),
        )
        if not recommendations:
            self.statusBar().showMessage(
                "No chart recommendation is available for this selection",
                4000,
            )
            return
        recommendation = recommendations[0]
        probe = ChartSpec(
            "quick-preview",
            sheet_name,
            target,
            recommendation.chart_type,
            has_headers=detect_chart_headers(
                self.engine.workbook,
                sheet_name,
                target,
            ),
        )
        title = recommendation.title or infer_chart_title(
            chart_data(self.engine.workbook, probe)
        )
        spec = ChartSpec(
            uuid4().hex,
            sheet_name,
            target,
            recommendation.chart_type,
            title=title,
            has_headers=probe.has_headers,
            show_grid=True,
            highlight_extrema=recommendation.chart_type in {"line", "scatter"},
        )
        self.history.execute(
            AddChartCommand(self.engine, sheet_name, spec)
        )
        self.statusBar().showMessage(
            f"Created {recommendation.chart_type.replace('_', ' ')}: "
            f"{recommendation.reason}",
            5000,
        )

    def insert_chart_of_type(self, chart_type: str) -> None:
        """Insert one chart type from the selection, as Excel's chart icons do."""
        if chart_type not in CHART_TYPES:
            self.statusBar().showMessage(f"Unknown chart type: {chart_type}", 4000)
            return
        sheet_name = self.grid_model.active_sheet_name
        target = expand_chart_range(
            self.engine.workbook,
            sheet_name,
            self._selected_range(),
        )
        if len(target) < 2:
            self.statusBar().showMessage(
                "Select a data range or a cell inside a contiguous data table",
                4000,
            )
            return
        has_headers = detect_chart_headers(self.engine.workbook, sheet_name, target)
        probe = ChartSpec(
            "insert-preview",
            sheet_name,
            target,
            chart_type,
            has_headers=has_headers,
        )
        spec = ChartSpec(
            uuid4().hex,
            sheet_name,
            target,
            chart_type,
            title=infer_chart_title(chart_data(self.engine.workbook, probe)),
            has_headers=has_headers,
        )
        self.history.execute(AddChartCommand(self.engine, sheet_name, spec))
        self.statusBar().showMessage(
            f"Inserted {CHART_TYPE_LABELS[chart_type]}. Click Edit on the chart "
            "to add elements or change its format.",
            5000,
        )

    def insert_sparklines(self, kind: str) -> None:
        """Open Create Sparklines for the selected data."""
        sheet_name = self.grid_model.active_sheet_name
        selection = self._selected_range()
        dialog = SparklineDialog(
            sheet_name,
            kind,
            selection.to_a1(),
            default_location(selection).to_a1(),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            sparklines = dialog.sparklines()
            self.history.execute(
                AddSparklinesCommand(self.engine, sheet_name, sparklines)
            )
        except (KeyError, ValueError) as error:
            self.statusBar().showMessage(str(error), 5000)
            return
        noun = "sparkline" if len(sparklines) == 1 else "sparklines"
        self.statusBar().showMessage(f"Inserted {len(sparklines)} {noun}", 4000)

    def clear_sparklines(self) -> None:
        """Remove sparklines from the selected cells."""
        try:
            self.history.execute(
                ClearSparklinesCommand(
                    self.engine,
                    self.grid_model.active_sheet_name,
                    self._selected_range(),
                )
            )
        except ValueError as error:
            self.statusBar().showMessage(str(error), 4000)

    def show_chart_help(
        self,
        topic: str | None = None,
        *,
        chart_type: str | None = None,
    ) -> None:
        """Open the Charts and Graphing Tutorial, optionally at one lesson."""
        ChartHelpDialog(
            self,
            topic=topic or topic_for_chart_type(chart_type),
        ).exec()

    def _sync_charts(self) -> None:
        active_specs = {
            chart.chart_id: chart
            for chart in self.engine.workbook.active_sheet.charts
            if hasattr(chart, "chart_id")
        }
        for chart_id, panel in tuple(self._chart_panels.items()):
            if chart_id not in active_specs or panel.workbook is not self.engine.workbook:
                self.removeDockWidget(panel)
                panel.setParent(None)
                panel.deleteLater()
                del self._chart_panels[chart_id]
        for chart_id, spec in active_specs.items():
            panel = self._chart_panels.get(chart_id)
            if panel is None:
                panel = ChartPanel(self.engine.workbook, spec, self)
                panel.closeRequested.connect(self._remove_chart)
                panel.editRequested.connect(self._edit_chart)
                panel.helpRequested.connect(
                    lambda panel=panel: self.show_chart_help(
                        chart_type=panel.spec.chart_type
                    )
                )
                self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, panel)
                panel.setFloating(True)
                panel.show()
                self._chart_panels[chart_id] = panel
            else:
                panel.spec = spec
                panel.refresh()

    def _refresh_charts(self) -> None:
        for panel in self._chart_panels.values():
            panel.refresh()

    def _remove_chart(self, chart_id: str) -> None:
        if any(
            getattr(chart, "chart_id", None) == chart_id
            for chart in self.engine.workbook.active_sheet.charts
        ):
            self.history.execute(
                RemoveChartCommand(
                    self.engine,
                    self.grid_model.active_sheet_name,
                    chart_id,
                )
            )

    def _edit_chart(self, chart_id: str) -> None:
        spec = next(
            (
                chart
                for chart in self.engine.workbook.active_sheet.charts
                if isinstance(chart, ChartSpec) and chart.chart_id == chart_id
            ),
            None,
        )
        if spec is None:
            return
        wizard = ChartWizard(
            spec.sheet_name,
            spec.source_range.to_a1(),
            self,
            workbook=self.engine.workbook,
            existing=spec,
        )
        if wizard.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.history.execute(
                UpdateChartCommand(
                    self.engine,
                    self.grid_model.active_sheet_name,
                    wizard.chart_spec(),
                )
            )
        except ValueError as error:
            self.statusBar().showMessage(str(error), 3000)

    def _dispose_chart_panels(self) -> None:
        for panel in self._chart_panels.values():
            self.removeDockWidget(panel)
            panel.setParent(None)
            panel.deleteLater()
        self._chart_panels.clear()

    def insert_rows(self) -> None:
        """Insert rows above the selected range."""
        target = self._selected_range()
        self.history.execute(
            InsertRowsCommand(
                self.engine,
                self.grid_model.active_sheet_name,
                target.min_row,
                target.max_row - target.min_row + 1,
            )
        )

    def insert_columns(self) -> None:
        """Insert columns left of the selected range."""
        target = self._selected_range()
        self.history.execute(
            InsertColumnsCommand(
                self.engine,
                self.grid_model.active_sheet_name,
                target.min_column,
                target.max_column - target.min_column + 1,
            )
        )

    def sort_selection(self) -> None:
        """Open the multi-key sort dialog for the current selection."""
        target = self._selected_range()
        dialog = SortDialog(target, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.sort_keys():
            self.history.execute(
                SortRangeCommand(
                    self.engine,
                    self.grid_model.active_sheet_name,
                    target,
                    dialog.sort_keys(),
                    dialog.has_header.isChecked(),
                )
            )

    def filter_selection(self) -> None:
        """Filter the selected range by checked values in the current column."""
        target = self._selected_range()
        current = self.grid.currentIndex()
        column = (
            current.column()
            if current.isValid()
            and target.min_column <= current.column() <= target.max_column
            else target.min_column
        )
        values = tuple(
            dict.fromkeys(
                self.grid_model.sheet.get_cell(row, column).display_value
                for row in range(target.min_row + 1, target.max_row + 1)
            )
        )
        dialog = FilterDialog(values, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.history.execute(
                ApplyFilterCommand(
                    self.engine,
                    self.grid_model.active_sheet_name,
                    target,
                    column,
                    dialog.allowed_values(),
                )
            )

    def clear_active_filter(self) -> None:
        """Clear the active sheet filter."""
        self.history.execute(
            ClearFilterCommand(
                self.engine,
                self.grid_model.active_sheet_name,
            )
        )

    def validate_selection(self) -> None:
        """Add a validation rule to the selected range."""
        target = self._selected_range()
        dialog = ValidationDialog(target, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.history.execute(
                AddValidationCommand(
                    self.engine,
                    self.grid_model.active_sheet_name,
                    dialog.validation(),
                )
            )

    def find_replace(self) -> None:
        """Find the first match or replace all matches."""
        dialog = FindReplaceDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = dialog.options()
        if not options.query:
            return
        if dialog.replace_all.isChecked():
            command = ReplaceAllCommand(self.engine, options)
            self.history.execute(command)
            self.statusBar().showMessage(
                f"Replaced {command.replaced_count} cells",
                3000,
            )
            return
        matches = find_cells(self.engine.workbook, options)
        if not matches:
            self.statusBar().showMessage("No matches found", 3000)
            return
        first = matches[0]
        self.grid_model.set_active_sheet(first.sheet or self.grid_model.active_sheet_name)
        self.sheet_tabs.sync(self.engine.workbook)
        index = self.grid_model.index(first.row, first.column)
        self.grid.setCurrentIndex(index)
        self.grid.scrollTo(index)
        self.statusBar().showMessage(f"Found {len(matches)} matches", 3000)

    def remove_duplicates(self) -> None:
        """Remove duplicate selected rows using all selected columns as keys."""
        target = self._selected_range()
        command = RemoveDuplicatesCommand(
            self.engine,
            self.grid_model.active_sheet_name,
            target,
            tuple(range(target.min_column, target.max_column + 1)),
        )
        self.history.execute(command)
        self.statusBar().showMessage(
            f"Removed {command.removed_count} duplicate rows",
            3000,
        )

    def text_to_columns(self) -> None:
        """Split selected text with a user-selected delimiter."""
        delimiter, accepted = QInputDialog.getText(
            self,
            "Text to Columns",
            "Delimiter",
            text=",",
        )
        if not accepted:
            return
        command = TextToColumnsCommand(
            self.engine,
            self.grid_model.active_sheet_name,
            self._selected_range(),
            delimiter,
        )
        try:
            self.history.execute(command)
        except ValueError as error:
            self.statusBar().showMessage(str(error), 3000)

    def merge_selection(self) -> None:
        """Merge selected cells and retain the upper-left value."""
        target = self._selected_range()
        if len(target) < 2:
            return
        try:
            self.history.execute(
                MergeCellsCommand(
                    self.engine,
                    self.grid_model.active_sheet_name,
                    target,
                )
            )
        except ValueError as error:
            self.statusBar().showMessage(str(error), 3000)

    def set_row_height(self) -> None:
        """Set selected row heights in points."""
        target = self._selected_range()
        height, accepted = QInputDialog.getDouble(
            self,
            "Row Height",
            "Height (points)",
            18.0,
            1.0,
            409.0,
            1,
        )
        if accepted:
            self.history.execute(
                SetRowHeightCommand(
                    self.engine,
                    self.grid_model.active_sheet_name,
                    tuple(range(target.min_row, target.max_row + 1)),
                    height,
                )
            )

    def set_column_width(self) -> None:
        """Set selected column widths in character units."""
        target = self._selected_range()
        width, accepted = QInputDialog.getDouble(
            self,
            "Column Width",
            "Width (characters)",
            12.0,
            1.0,
            255.0,
            1,
        )
        if accepted:
            self.history.execute(
                SetColumnWidthCommand(
                    self.engine,
                    self.grid_model.active_sheet_name,
                    tuple(range(target.min_column, target.max_column + 1)),
                    width,
                )
            )

    def autofit_selection(self) -> None:
        """Autofit selected columns from formatted display lengths."""
        target = self._selected_range()
        sheet = self.grid_model.sheet
        for column in range(target.min_column, target.max_column + 1):
            width = max(
                (
                    len(
                        str(
                            self.grid_model.data(
                                self.grid_model.index(row, column)
                            )
                            or ""
                        )
                    )
                    for row in range(target.min_row, target.max_row + 1)
                ),
                default=8,
            )
            self.history.execute(
                SetColumnWidthCommand(
                    self.engine,
                    self.grid_model.active_sheet_name,
                    (column,),
                    min(255.0, max(3.0, width + 2.0)),
                )
            )

    def _selected_range(self) -> RangeReference:
        bounds = self.grid.selection_bounds() or (0, 0, 0, 0)
        return RangeReference(
            CellReference(bounds[0], bounds[1]),
            CellReference(bounds[2], bounds[3]),
        )

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
        enabled = not self.grid.showGrid()
        for grid in self._grid_views():
            grid.setShowGrid(enabled)
            grid.sync_sheet_metadata()

    def toggle_formula_view(self) -> None:
        """Toggle calculated values versus raw formulas."""
        self.grid_model.set_formula_view(not self.grid_model.formula_view)

    def increase_zoom(self) -> None:
        """Cycle zoom upward in useful increments, wrapping after 400%."""
        selected = self.grid.zoom_percent + 25
        selected = 25 if selected > 400 else selected
        for grid in self._grid_views():
            grid.set_zoom(selected)
        self.statusBar().showMessage(f"Zoom: {self.grid.zoom_percent}%", 2000)

    def toggle_split_view(self) -> None:
        """Open or close a synchronized second view of the active worksheet."""
        if self.secondary_grid is not None:
            secondary = self.secondary_grid
            self.secondary_grid = None
            secondary.setParent(None)
            secondary.deleteLater()
            self.statusBar().showMessage("Split view closed", 2000)
            return
        secondary = GridView()
        secondary.setModel(self.grid_model)
        secondary.setItemDelegate(CellDelegate(secondary))
        secondary.currentCellChanged.connect(self.on_current_cell_changed)
        secondary.selectionSummaryChanged.connect(self.selection_label.setText)
        secondary.externalHyperlinkRequested.connect(self._open_external_hyperlink)
        secondary.internalHyperlinkRequested.connect(self.goto_reference)
        secondary.setShowGrid(self.grid.showGrid())
        secondary.set_zoom(self.grid.zoom_percent)
        secondary.sync_sheet_metadata()
        self.secondary_grid = secondary
        self.grid_splitter.addWidget(secondary)
        total_height = max(2, self.grid_splitter.height())
        self.grid_splitter.setSizes([total_height // 2, total_height // 2])
        self.statusBar().showMessage("Split view opened", 2000)

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

    def _grid_views(self) -> tuple[GridView, ...]:
        return (
            (self.grid, self.secondary_grid)
            if self.secondary_grid is not None
            else (self.grid,)
        )

    def _sync_grid_metadata(self) -> None:
        for grid in self._grid_views():
            grid.sync_sheet_metadata()
