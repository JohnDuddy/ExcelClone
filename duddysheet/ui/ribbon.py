"""Compact tabbed spreadsheet ribbon."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
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
            ),
            "Insert": ("PivotTable", "Table", "Quick Chart", "Chart Studio", "Rows", "Columns"),
            "Data": (
                "Sort",
                "Filter",
                "Clear Filter",
                "Validate",
                "Remove Duplicates",
                "Text to Columns",
                "Refresh All",
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
