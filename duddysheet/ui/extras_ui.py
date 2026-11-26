"""Quick Analysis (Ctrl+Q), Forecast Sheet, and threaded comments."""

from __future__ import annotations

import getpass
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from duddysheet.commands.analysis import WorkbookMutationCommand
from duddysheet.core.comments import add_reply, set_resolved, start_thread
from duddysheet.core.conditional import ConditionalRule, FormatPatch
from duddysheet.core.refs import CellReference, RangeReference

QUICK_FORMATS = (
    ("data_bar", "Data Bars"),
    ("color_scale", "Color Scale"),
    ("icon_set", "Icon Set"),
    ("greater_than", "Greater Than Average"),
    ("top_10", "Top 10%"),
    ("clear", "Clear Format"),
)
QUICK_TOTALS = (
    ("sum", "Sum"),
    ("average", "Average"),
    ("count", "Count"),
    ("percent_total", "% Total"),
    ("running_total", "Running Total"),
)


def default_author() -> str:
    """The comment author: the signed-in user name, as Excel shows it."""
    try:
        return getpass.getuser() or "Author"
    except (KeyError, OSError):
        return "Author"


class ForecastDialog(QDialog):
    """Create Forecast Worksheet: forecast length, confidence, seasonality, chart."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Forecast Worksheet")
        layout = QFormLayout(self)
        self.periods = QSpinBox()
        self.periods.setRange(1, 10_000)
        self.periods.setValue(6)
        self.periods.setObjectName("forecastPeriods")
        self.confidence = QDoubleSpinBox()
        self.confidence.setRange(1, 99.9)
        self.confidence.setValue(95)
        self.confidence.setSuffix("%")
        self.automatic = QCheckBox("Detect Automatically")
        self.automatic.setChecked(True)
        self.season = QSpinBox()
        self.season.setRange(1, 8760)
        self.season.setValue(12)
        self.season.setEnabled(False)
        self.automatic.toggled.connect(lambda checked: self.season.setEnabled(not checked))
        self.chart = QComboBox()
        self.chart.addItems(["Line chart", "Column chart"])
        seasonality = QHBoxLayout()
        seasonality.addWidget(self.automatic)
        seasonality.addWidget(self.season)
        layout.addRow("Periods to forecast:", self.periods)
        layout.addRow("Confidence Interval:", self.confidence)
        layout.addRow("Seasonality:", seasonality)
        layout.addRow("Chart:", self.chart)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def options(self) -> Any:
        from duddysheet.core.forecast import ForecastOptions

        return ForecastOptions(
            periods=self.periods.value(),
            confidence=self.confidence.value() / 100,
            seasonality=None if self.automatic.isChecked() else self.season.value(),
            chart_type="column" if self.chart.currentIndex() else "line",
        )


class CommentsPane(QWidget):
    """The Comments pane: every thread on the sheet, with reply and resolve."""

    def __init__(self, window: Any) -> None:
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        self.threads = QListWidget()
        self.threads.setObjectName("commentThreads")
        self.threads.currentRowChanged.connect(self._thread_selected)
        layout.addWidget(self.threads, 1)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.detail)
        self.reply = QPlainTextEdit()
        self.reply.setObjectName("commentReply")
        self.reply.setPlaceholderText("Reply...")
        self.reply.setMaximumHeight(70)
        layout.addWidget(self.reply)
        buttons = QHBoxLayout()
        for label, handler in (("Post", self.post), ("Resolve", self.toggle_resolved), ("Delete", self.delete)):
            button = QPushButton(label)
            button.setObjectName(f"comment{label}")
            button.clicked.connect(handler)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.cells: list[tuple[int, int]] = []

    def refresh(self) -> None:
        sheet = self.window.grid_model.sheet
        current = self.selected_cell()
        self.cells = sorted(sheet.comments)
        self.threads.blockSignals(True)
        self.threads.clear()
        for row, column in self.cells:
            thread = sheet.comments[(row, column)]
            mark = " (Resolved)" if thread.resolved else ""
            first = thread.entries[0]
            self.threads.addItem(f"{CellReference(row, column).to_a1()}  {first.author}: {first.text[:60]}{mark}")
        if current in self.cells:
            self.threads.setCurrentRow(self.cells.index(current))
        self.threads.blockSignals(False)
        self._thread_selected(self.threads.currentRow())

    def selected_cell(self) -> tuple[int, int] | None:
        row = self.threads.currentRow()
        return self.cells[row] if 0 <= row < len(self.cells) else None

    def _thread_selected(self, row: int) -> None:
        cell = self.cells[row] if 0 <= row < len(self.cells) else None
        thread = self.window.grid_model.sheet.comments.get(cell) if cell else None
        self.detail.setText(thread.summary() if thread else "Select a comment to read it.")

    def post(self) -> None:
        cell = self.selected_cell()
        text = self.reply.toPlainText().strip()
        if cell and text:
            self.window.reply_to_comment(cell[0], cell[1], text)
            self.reply.clear()

    def toggle_resolved(self) -> None:
        cell = self.selected_cell()
        if cell:
            thread = self.window.grid_model.sheet.comments[cell]
            self.window.resolve_comment(cell[0], cell[1], not thread.resolved)

    def delete(self) -> None:
        cell = self.selected_cell()
        if cell:
            self.window.delete_comment(cell[0], cell[1])


class ExtrasMixin:
    """Quick Analysis, Forecast Sheet, and threaded comments for the main window."""

    def _install_extras(self) -> None:
        a = self._action
        a("quickAnalysis", "Quick Analysis", self.show_quick_analysis, ("Ctrl+Q",), tip="Format, chart, total, or table the selection in one click")
        a("forecastSheet", "Forecast Sheet...", self.forecast_sheet_dialog, tip="Forecast a time series on a new sheet")
        a("newComment", "New Comment", self.new_comment_dialog, ("Ctrl+Alt+M",), tip="Start a conversation about this cell")
        a("showComments", "Show Comments", self.show_comments_pane, tip="Open the Comments pane")
        data = self._menu("Data")
        self._add(data, "forecastSheet")
        review = self._menu("Review")
        first = review.actions()[0] if review.actions() else None
        review.insertAction(first, self.excel_actions["newComment"])
        review.insertAction(first, self.excel_actions["showComments"])
        review.insertSeparator(first)
        handlers = self.excel_ribbon_handlers
        handlers["Forecast Sheet"] = self.forecast_sheet_dialog
        handlers["Quick Analysis"] = self.show_quick_analysis
        self.comments_dock: QDockWidget | None = None
        self.history.add_listener(lambda history: self._refresh_comments_pane())

    def _extras_mutation(self, label: str, mutate: Any) -> bool:
        return self._run(WorkbookMutationCommand(self.engine, label, mutate))

    # ------------------------------------------------------- Quick Analysis
    def _selection_area(self) -> tuple[int, int, int, int] | None:
        bounds = self.grid.selection_bounds()
        if bounds is None:
            index = self.grid.currentIndex()
            if not index.isValid():
                return None
            return index.row(), index.column(), index.row(), index.column()
        return bounds

    def quick_analysis_menu(self) -> QMenu:
        """Build the Quick Analysis menu for the selection."""
        menu = QMenu("Quick Analysis", self)
        menu.setObjectName("quickAnalysisMenu")
        sections: list[QMenu] = []

        def section(title: str, parent: QMenu) -> QMenu:
            child = QMenu(title, parent)
            parent.addMenu(child)
            sections.append(child)
            return child

        menu.sections = sections  # keep the submenus' Python wrappers alive
        formatting = section("Formatting", menu)
        for key, label in QUICK_FORMATS:
            formatting.addAction(label).triggered.connect(lambda checked=False, key=key: self.quick_format(key))
        charts = section("Charts", menu)
        area = self._selection_area()
        if area is not None:
            from duddysheet.core.chart import CHART_TYPE_LABELS, recommend_charts

            source = RangeReference(CellReference(area[0], area[1]), CellReference(area[2], area[3]))
            try:
                recommendations = recommend_charts(self.engine.workbook, self.grid_model.active_sheet_name, source)
            except (ValueError, KeyError):
                recommendations = ()
            for recommendation in recommendations[:5]:
                charts.addAction(CHART_TYPE_LABELS[recommendation.chart_type]).triggered.connect(
                    lambda checked=False, kind=recommendation.chart_type: self.quick_chart(kind)
                )
        totals = section("Totals", menu)
        for direction, label in (("below", "Row below"), ("right", "Column to the right")):
            group = section(label, totals)
            for key, text in QUICK_TOTALS:
                group.addAction(text).triggered.connect(lambda checked=False, key=key, direction=direction: self.quick_total(key, direction))
        tables = section("Tables", menu)
        tables.addAction("Table").triggered.connect(lambda: self.quick_table())
        tables.addAction("PivotTable").triggered.connect(lambda: self.quick_pivot())
        sparklines = section("Sparklines", menu)
        for kind, label in (("line", "Line"), ("column", "Column"), ("win_loss", "Win/Loss")):
            sparklines.addAction(label).triggered.connect(lambda checked=False, kind=kind: self.quick_sparklines(kind))
        return menu

    def show_quick_analysis(self) -> None:
        """Ctrl+Q: open Quick Analysis beside the selection."""
        menu = self.quick_analysis_menu()
        area = self._selection_area()
        if area is None:
            return
        rect = self.grid.visualRect(self.grid_model.index(area[2], area[3]))
        point = self.grid.viewport().mapToGlobal(rect.bottomRight()) if rect.isValid() else QCursor.pos()
        menu.popup(point)

    def quick_format(self, kind: str) -> bool:
        """Quick Analysis > Formatting: add (or clear) a conditional format for the selection."""
        area = self._selection_area()
        if area is None:
            return False
        sheet_name = self.grid_model.active_sheet_name
        target = RangeReference(CellReference(area[0], area[1]), CellReference(area[2], area[3]))

        def mutate() -> None:
            sheet = self.engine.workbook.get_sheet(sheet_name)
            if kind == "clear":
                sheet.conditional_formats = [rule for rule in sheet.conditional_formats if rule.range != target]
                return
            highlight = FormatPatch(fill_color="#ffc7ce", font_color="#9c0006")
            rule = {
                "data_bar": ConditionalRule(target, "data_bar", colors=("#638ec6",)),
                "color_scale": ConditionalRule(target, "color_scale"),
                "icon_set": ConditionalRule(target, "icon_set"),
                "greater_than": ConditionalRule(target, "above_average", format_patch=highlight, above=True),
                "top_10": ConditionalRule(target, "top_bottom", format_patch=highlight, rank=10, percent=True),
            }[kind]
            sheet.conditional_formats = [*sheet.conditional_formats, rule]

        return self._extras_mutation("Quick Analysis formatting", mutate)

    def quick_chart(self, chart_type: str) -> Any:
        from uuid import uuid4

        from duddysheet.commands.edits import AddChartCommand
        from duddysheet.core.chart import ChartSpec

        area = self._selection_area()
        if area is None:
            return None
        sheet_name = self.grid_model.active_sheet_name
        source = RangeReference(CellReference(area[0], area[1], sheet_name), CellReference(area[2], area[3], sheet_name))
        chart = ChartSpec(uuid4().hex, sheet_name, source, chart_type)
        self._run(AddChartCommand(self.engine, sheet_name, chart))
        return chart

    def quick_total(self, kind: str, direction: str = "below") -> bool:
        """Quick Analysis > Totals: a row of totals below (or a column to the right of) the data."""
        area = self._selection_area()
        if area is None:
            return False
        top, left, bottom, right = area
        sheet = self.grid_model.sheet
        # A text header row is left out of the totals, as in Excel.
        if direction == "below" and bottom > top and all(isinstance(sheet.get_cell(top, column).display_value, str) for column in range(left, right + 1)):
            top += 1
        if direction == "right" and right > left and all(isinstance(sheet.get_cell(row, left).display_value, str) for row in range(top, bottom + 1)):
            left += 1
        sheet_name = self.grid_model.active_sheet_name
        whole = RangeReference(CellReference(top, left, None, True, True), CellReference(bottom, right, None, True, True)).to_a1()
        cells: list[tuple[int, int, str, str | None]] = []
        lines = range(left, right + 1) if direction == "below" else range(top, bottom + 1)
        for position, line in enumerate(lines):
            if direction == "below":
                span = RangeReference(CellReference(top, line), CellReference(bottom, line)).to_a1()
                running = RangeReference(CellReference(top, left, None, True, True), CellReference(bottom, line, None, False, False)).to_a1()
                target = (bottom + 1, line)
            else:
                span = RangeReference(CellReference(line, left), CellReference(line, right)).to_a1()
                running = RangeReference(CellReference(top, left, None, True, True), CellReference(line, right, None, False, False)).to_a1()
                target = (line, right + 1)
            formula, number_format = {
                "sum": (f"=SUM({span})", None),
                "average": (f"=AVERAGE({span})", None),
                "count": (f"=COUNT({span})", None),
                "percent_total": (f"=SUM({span})/SUM({whole})", "0.00%"),
                "running_total": (f"=SUM({running})", None),
            }[kind]
            cells.append((*target, formula, number_format))

        def mutate() -> None:
            from duddysheet.core.cell import CellFormat

            for row, column, formula, number_format in cells:
                cell_format = CellFormat(number_format=number_format, bold=True) if number_format else CellFormat(bold=True)
                self.engine.set_cell(sheet_name, row, column, formula, cell_format=cell_format)

        return self._extras_mutation("Quick Analysis totals", mutate)

    def quick_table(self) -> bool:
        area = self._selection_area()
        return bool(area) and self.create_table_at(area)

    def quick_pivot(self) -> bool:
        area = self._selection_area()
        if area is None:
            return False
        source = RangeReference(CellReference(area[0], area[1], None, True, True), CellReference(area[2], area[3], None, True, True))
        try:
            spec = self.pivot_from_source(f"{self.grid_model.active_sheet_name}!{source.to_a1()}")
        except ValueError as error:
            QMessageBox.warning(self, "Quick Analysis", str(error))
            return False
        return self.create_pivot(spec)

    def quick_sparklines(self, kind: str) -> bool:
        """Quick Analysis > Sparklines: one sparkline per row in the column to the right."""
        from duddysheet.commands.edits import AddSparklinesCommand
        from duddysheet.core.sparkline import build_sparklines

        area = self._selection_area()
        if area is None or area[3] == area[1]:
            return False
        top, left, bottom, right = area
        data = RangeReference(CellReference(top, left), CellReference(bottom, right))
        location = RangeReference(CellReference(top, right + 1), CellReference(bottom, right + 1))
        sparklines = build_sparklines(data, location, kind)
        return self._run(AddSparklinesCommand(self.engine, self.grid_model.active_sheet_name, sparklines))

    # ------------------------------------------------------- Forecast Sheet
    def forecast_sheet_dialog(self) -> None:
        """Data > Forecast Sheet for a selected timeline and values column."""
        dialog = ForecastDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.create_forecast_sheet(dialog.options())
            except ValueError as error:
                QMessageBox.warning(self, "Forecast Sheet", str(error))

    def create_forecast_sheet(self, options: Any) -> str:
        """Build the forecast sheet from the selected two columns (timeline, values)."""
        from duddysheet.core.forecast import build_forecast_sheet

        area = self._selection_area()
        if area is None or area[3] - area[1] != 1:
            raise ValueError("Select two columns: a timeline and the values to forecast.")
        top, left, bottom, right = area
        sheet_name = self.grid_model.active_sheet_name
        timeline = RangeReference(CellReference(top, left), CellReference(bottom, left))
        values = RangeReference(CellReference(top, right), CellReference(bottom, right))
        created: list[str] = []

        def mutate() -> None:
            name, _chart = build_forecast_sheet(self.engine.workbook, self.engine, sheet_name, timeline, values, options)
            created.append(name)

        self._extras_mutation("Forecast Sheet", mutate)
        if created:
            workbook = self.engine.workbook
            self.sheet_tabs.sync(workbook)
            self.sheet_tabs.tab_bar.setCurrentIndex(workbook.sheet_names.index(created[0]))
        return created[0] if created else ""

    # ------------------------------------------------------- comments
    def new_comment_dialog(self) -> None:
        """Review > New Comment: start a thread (or reply) on the active cell."""
        from PySide6.QtWidgets import QInputDialog

        index = self.grid.currentIndex()
        if not index.isValid():
            return
        existing = self.grid_model.sheet.comments.get((index.row(), index.column()))
        title = "Reply" if existing else "New Comment"
        text, accepted = QInputDialog.getMultiLineText(self, title, existing.summary() + "\n\nReply:" if existing else "Start a conversation:")
        if accepted and text.strip():
            if existing:
                self.reply_to_comment(index.row(), index.column(), text)
            else:
                self.add_comment(index.row(), index.column(), text)
        self.show_comments_pane()

    def _set_thread(self, label: str, row: int, column: int, thread: Any) -> bool:
        sheet_name = self.grid_model.active_sheet_name

        def mutate() -> None:
            sheet = self.engine.workbook.get_sheet(sheet_name)
            comments = dict(sheet.comments)
            if thread is None:
                comments.pop((row, column), None)
            else:
                comments[(row, column)] = thread
            sheet.comments = comments

        done = self._extras_mutation(label, mutate)
        self.grid_model.refresh()
        return done

    def add_comment(self, row: int, column: int, text: str, author: str | None = None) -> bool:
        return self._set_thread("New Comment", row, column, start_thread(text.strip(), author or default_author()))

    def reply_to_comment(self, row: int, column: int, text: str, author: str | None = None) -> bool:
        thread = self.grid_model.sheet.comments.get((row, column))
        if thread is None:
            return self.add_comment(row, column, text, author)
        return self._set_thread("Reply", row, column, add_reply(thread, text.strip(), author or default_author()))

    def resolve_comment(self, row: int, column: int, resolved: bool = True) -> bool:
        thread = self.grid_model.sheet.comments.get((row, column))
        return thread is not None and self._set_thread("Resolve Thread" if resolved else "Reopen Thread", row, column, set_resolved(thread, resolved))

    def delete_comment(self, row: int, column: int) -> bool:
        return (row, column) in self.grid_model.sheet.comments and self._set_thread("Delete Comment", row, column, None)

    def show_comments_pane(self) -> None:
        if self.comments_dock is None:
            dock = QDockWidget("Comments", self)
            dock.setObjectName("commentsDock")
            dock.setWidget(CommentsPane(self))
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            self.comments_dock = dock
        self.comments_dock.show()
        self.comments_dock.widget().refresh()

    def _refresh_comments_pane(self) -> None:
        if self.comments_dock is not None and not self.comments_dock.isHidden():
            self.comments_dock.widget().refresh()


__all__ = ["CommentsPane", "ExtrasMixin", "ForecastDialog"]
