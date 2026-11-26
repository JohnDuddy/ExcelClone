"""Compact tabbed spreadsheet ribbon."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFontComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QTabWidget,
    QToolButton,
    QWidget,
)

from duddysheet.core.chart import CHART_FAMILIES, CHART_INFO
from duddysheet.core.sparkline import SPARKLINE_KIND_LABELS, SPARKLINE_KINDS
from duddysheet.ui.tool_help import apply_tool_help

# Ribbon labels are abbreviated; map them onto the shared Financial help copy.
FINANCIAL_RIBBON_HELP_KEYS = {
    "Model Templates": "new_model",
    "Goal Seek": "goal_seek",
    "Sensitivity": "sensitivity",
    "Scenarios": "scenarios",
    "Model Audit": "audit",
    "Financial Help": "guide",
}


# Excel's Insert tab groups chart families into these galleries.
CHART_RIBBON_GALLERIES = (
    ("Column/Bar", ("Column", "Bar")),
    ("Line/Area", ("Line", "Area")),
    ("Pie/Doughnut", ("Pie",)),
    ("Hierarchy", ("Treemap", "Sunburst")),
    ("Statistic", ("Histogram", "Box & Whisker")),
    ("Scatter/Bubble", ("X Y (Scatter)",)),
    ("Waterfall/Stock", ("Waterfall", "Funnel", "Stock", "Surface", "Radar")),
    ("Combo", ("Combo",)),
    ("More Charts", ("More",)),
)


def chart_menu_entries(families: tuple[str, ...]) -> list[tuple[str, list[tuple[str, str]]]]:
    """Return (family, [(label, action name)]) sections for chart menus."""
    by_family = dict(CHART_FAMILIES)
    return [
        (
            family,
            [(CHART_INFO[key].label, f"chart:{key}") for key in by_family[family]],
        )
        for family in families
    ]


def sparkline_menu_entries() -> list[tuple[str, list[tuple[str, str]]]]:
    """Return the Sparklines gallery: one entry per type, then Clear."""
    return [
        (
            "Sparklines",
            [
                (f"{SPARKLINE_KIND_LABELS[kind]}...", f"sparkline:{kind}")
                for kind in SPARKLINE_KINDS
            ]
            + [("Clear Sparklines", "Clear Sparklines")],
        )
    ]


FONT_SIZES = (8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72)


class Ribbon(QTabWidget):
    """Tabbed command surface with deliberately small action groups."""

    actionRequested = Signal(str)

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setObjectName("ribbon")
        self.setDocumentMode(True)
        self.setMaximumHeight(104)
        definitions = {
            "Home": (
                "Undo",
                "Redo",
                "Copy",
                "Paste",
                "Paste Special",
                "Bold",
                "Italic",
                "Underline",
                "Font Color",
                "Fill",
                "Wrap",
                "Merge",
                "Row Height",
                "Column Width",
                "Autofit",
                "Find",
                "Format Cells",
                "Quick Analysis",
            ),
            "Insert": ("PivotTable", "PivotChart", "Slicer", "Table", "Pictures", "Text Box", "Quick Chart", "Chart Studio", "Rows", "Columns"),
            "Data": (
                "Sort",
                "Filter",
                "Clear Filter",
                "Validate",
                "Remove Duplicates",
                "Text to Columns",
                "Refresh All",
                "Solver",
                "Forecast Sheet",
            ),
            "Formulas": ("Insert Function", "Recalculate", "Sheet Recalculate"),
            "Financial": (
                "Model Templates",
                "Goal Seek",
                "Sensitivity",
                "Scenarios",
                "Model Audit",
                "Financial Help",
            ),
            "View": (
                "Freeze Panes",
                "Split View",
                "Gridlines",
                "Formula View",
                "Zoom",
            ),
        }
        for tab_name, actions in definitions.items():
            page = QWidget()
            layout = QHBoxLayout(page)
            layout.setContentsMargins(10, 6, 10, 6)
            for action_name in actions:
                if tab_name == "Home" and action_name == "Bold":
                    layout.addWidget(self._font_family_box())
                    layout.addWidget(self._font_size_box())
                button = QToolButton()
                button.setText(action_name)
                button.setObjectName(
                    action_name.replace(" ", "")[0].lower()
                    + action_name.replace(" ", "")[1:]
                    + "Button"
                )
                help_key = FINANCIAL_RIBBON_HELP_KEYS.get(action_name)
                if help_key is not None:
                    apply_tool_help(button, help_key)
                button.clicked.connect(
                    lambda checked=False, name=action_name: self.actionRequested.emit(name)
                )
                layout.addWidget(button)
            if tab_name == "Insert":
                from duddysheet.core.drawings import SHAPES

                layout.addWidget(self._menu_button("Shapes", [("Shapes", [(label, f"shape:{key}") for key, label in SHAPES.items()])]))
                for text, families in CHART_RIBBON_GALLERIES:
                    layout.addWidget(
                        self._menu_button(text, chart_menu_entries(families))
                    )
                layout.addWidget(
                    self._menu_button("Sparklines", sparkline_menu_entries())
                )
                help_button = QToolButton()
                help_button.setText("Chart Help")
                help_button.setObjectName("chartHelpButton")
                help_button.setToolTip("Open the Charts and Graphing Tutorial")
                help_button.clicked.connect(
                    lambda checked=False: self.actionRequested.emit("Chart Help")
                )
                layout.addWidget(help_button)
            if tab_name == "Data":
                layout.addWidget(
                    self._menu_button(
                        "What-If Analysis",
                        [
                            (
                                "What-If Analysis",
                                [
                                    ("Scenario Manager...", "Scenarios"),
                                    ("Goal Seek...", "Goal Seek"),
                                    ("Data Table...", "Data Table"),
                                ],
                            )
                        ],
                    )
                )
                analysis_help = QToolButton()
                analysis_help.setText("Analysis Help")
                analysis_help.setObjectName("analysisHelpButton")
                analysis_help.setToolTip("Open the PivotTables, Tables, and What-If tutorial")
                analysis_help.clicked.connect(
                    lambda checked=False: self.actionRequested.emit("Analysis Help")
                )
                layout.addWidget(analysis_help)
            layout.addStretch(1)
            self.addTab(page, tab_name)

    def _font_family_box(self) -> QFontComboBox:
        """The Home tab's Font box: picking a font applies it to the selection."""
        box = QFontComboBox()
        box.setObjectName("fontFamilyBox")
        box.setToolTip("Font")
        box.setMaximumWidth(170)
        box.setCurrentFont(QFont("Aptos"))
        box.activated.connect(lambda _index: self.actionRequested.emit(f"fontFamily:{box.currentFont().family()}"))
        self.font_family_box = box
        return box

    def _font_size_box(self) -> QComboBox:
        """The Home tab's Font Size box: pick a size or type one and press Enter."""
        box = QComboBox()
        box.setObjectName("fontSizeBox")
        box.setToolTip("Font Size")
        box.setEditable(True)
        box.addItems([str(size) for size in FONT_SIZES])
        box.setCurrentText("11")
        box.setMaximumWidth(64)
        box.activated.connect(lambda _index: self.actionRequested.emit(f"fontSize:{box.currentText()}"))
        self.font_size_box = box
        return box

    def show_font(self, family: str, size: float) -> None:
        """Show the active cell's font in the Font and Font Size boxes."""
        for box in (self.font_family_box, self.font_size_box):
            box.blockSignals(True)
        self.font_family_box.setCurrentFont(QFont(family))
        self.font_size_box.setCurrentText(f"{size:g}")
        for box in (self.font_family_box, self.font_size_box):
            box.blockSignals(False)

    def _menu_button(
        self,
        text: str,
        sections: list[tuple[str, list[tuple[str, str]]]],
    ) -> QToolButton:
        """Create a gallery button whose menu emits one action per entry."""
        button = QToolButton()
        button.setText(text)
        button.setObjectName(
            "".join(character for character in text if character.isalnum())
            + "GalleryButton"
        )
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        for section, entries in sections:
            if len(sections) > 1:
                menu.addSection(section)
            for label, action_name in entries:
                action = menu.addAction(label)
                action.setData(action_name)
        menu.triggered.connect(
            lambda action: self.actionRequested.emit(str(action.data()))
        )
        button.setMenu(menu)
        return button
