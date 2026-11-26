"""Offline tutorial for Excel Tables, PivotTables, and What-If data tables."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from duddysheet.core.analysis_help import LESSONS, SECTIONS, lesson_html, search_lessons
from duddysheet.ui.dialogs.chart_help import _styled_html

_INTRO = """
<h1>PivotTables, Tables, and What-If Analysis</h1>
<p>Three tools for working with lists of data and with models:</p>
<ul>
<li><b>Excel Tables</b> (Ctrl+T) turn a list into a named object that formats
itself, grows as you type, fills formulas down automatically, and can be used
in formulas by name, for example <code>=SUM(Sales[Amount])</code>.</li>
<li><b>PivotTables</b> (Insert &gt; PivotTable) summarize a list by category:
totals by region, by product, by year, without writing a formula.</li>
<li><b>Data tables</b> (Data &gt; What-If Analysis &gt; Data Table) show how a
result changes for many values of one or two inputs, for example a loan
payment for several rates and terms.</li>
</ul>
<p>Click <b>Open Practice Workbook</b> to load a workbook with a sales table, a
PivotTable built from it, and a loan data table, then follow the lessons on
the left.</p>
"""


class AnalysisHelpDialog(QDialog):
    """Searchable lessons grouped by Tables, PivotTables, and What-If Analysis."""

    practiceRequested = Signal()

    def __init__(self, parent: Any = None, *, topic: str | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("analysisHelpDialog")
        self.setWindowTitle("PivotTables, Tables, and What-If Analysis")
        self.resize(1000, 700)
        title = QLabel("PivotTables, Tables, and What-If Analysis")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #17324d; padding: 6px 0;")
        self.search = QLineEdit()
        self.search.setObjectName("analysisHelpSearch")
        self.search.setPlaceholderText("Search the lessons, e.g. total row, GETPIVOTDATA, two-variable")
        self.tree = QTreeWidget()
        self.tree.setObjectName("analysisLessonTree")
        self.tree.setHeaderHidden(True)
        self.detail = QTextBrowser()
        self.detail.setObjectName("analysisLessonDetail")
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.search)
        left_layout.addWidget(self.tree, 1)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.detail)
        splitter.setSizes((300, 700))
        practice = QPushButton("Open Practice Workbook")
        practice.setObjectName("openPracticeWorkbook")
        practice.clicked.connect(self._practice)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.addButton(practice, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(splitter, 1)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self._populate)
        self.tree.currentItemChanged.connect(self._show)
        self._populate()
        if topic:
            self.show_topic(topic)
        else:
            self.detail.setHtml(_styled_html(_INTRO))

    def _populate(self, query: str = "") -> None:
        matches = {lesson.key for lesson in search_lessons(query)}
        self.tree.blockSignals(True)
        self.tree.clear()
        for section in SECTIONS:
            parent = QTreeWidgetItem([section])
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for lesson in LESSONS:
                if lesson.section == section and lesson.key in matches:
                    child = QTreeWidgetItem([lesson.title])
                    child.setData(0, Qt.ItemDataRole.UserRole, lesson.key)
                    parent.addChild(child)
            if parent.childCount():
                self.tree.addTopLevelItem(parent)
                parent.setExpanded(True)
        self.tree.blockSignals(False)
        if query and self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0).child(0))
        elif query:
            self.detail.setHtml(_styled_html("<p>No lesson matches that search.</p>"))

    @property
    def current_topic(self) -> str | None:
        """Return the key of the lesson on screen."""
        item = self.tree.currentItem()
        return None if item is None else item.data(0, Qt.ItemDataRole.UserRole)

    def show_topic(self, key: str) -> None:
        """Select a lesson by key."""
        for index in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(index)
            for child_index in range(parent.childCount()):
                child = parent.child(child_index)
                if child.data(0, Qt.ItemDataRole.UserRole) == key:
                    self.tree.setCurrentItem(child)
                    return

    def _show(self, current: QTreeWidgetItem | None, previous: QTreeWidgetItem | None) -> None:
        del previous
        key = None if current is None else current.data(0, Qt.ItemDataRole.UserRole)
        lesson = next((item for item in LESSONS if item.key == key), None)
        if lesson is not None:
            self.detail.setHtml(_styled_html(lesson_html(lesson)))

    def _practice(self) -> None:
        self.accept()
        self.practiceRequested.emit()
