"""Interactive Matplotlib chart panel with live refresh, editing, and export."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)
from matplotlib.figure import Figure
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from duddysheet.core.chart import ChartSpec
from duddysheet.core.workbook import Workbook
from duddysheet.ui.chart_renderer import THEMES, draw_chart, render_chart

__all__ = ["THEMES", "ChartPanel", "render_chart"]


class ChartPanel(QDockWidget):
    """Movable chart studio panel with live refresh, editing, and export."""

    closeRequested = Signal(str)
    editRequested = Signal(str)
    helpRequested = Signal()

    def __init__(
        self,
        workbook: Workbook,
        spec: ChartSpec,
        parent: Any = None,
    ) -> None:
        super().__init__(spec.title or "Chart", parent)
        self.setObjectName(f"chart-{spec.chart_id}")
        self.workbook = workbook
        self.spec = spec
        self.figure = Figure(figsize=(7.4, 4.8), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.navigation = NavigationToolbar2QT(self.canvas, self)
        self.navigation.setIconSize(self.navigation.iconSize() * 0.8)
        self.summary = QLabel()
        self.summary.setObjectName("chartSummary")
        edit_button = QPushButton("Edit")
        edit_button.clicked.connect(
            lambda: self.editRequested.emit(self.spec.chart_id)
        )
        copy_button = QPushButton("Copy Image")
        copy_button.clicked.connect(self.copy_image)
        export_button = QPushButton("Export")
        export_button.clicked.connect(self.choose_export_path)
        help_button = QPushButton("Help")
        help_button.setToolTip("Open the Charts and Graphing Tutorial")
        help_button.clicked.connect(self.helpRequested.emit)
        controls = QHBoxLayout()
        controls.addWidget(self.summary)
        controls.addStretch(1)
        controls.addWidget(edit_button)
        controls.addWidget(copy_button)
        controls.addWidget(export_button)
        controls.addWidget(help_button)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(controls)
        layout.addWidget(self.navigation)
        layout.addWidget(self.canvas, 1)
        self.setWidget(content)
        self.setMinimumSize(420, 300)
        self.resize(760, 500)
        self.refresh()

    def refresh(self) -> None:
        """Redraw from current workbook cached values."""
        data = draw_chart(self.figure, self.workbook, self.spec)
        point_count = sum(len(series.values) for series in data.series)
        self.summary.setText(
            f"{len(data.series)} series  |  {point_count} live values"
        )
        self.setWindowTitle(self.spec.title or "Chart")
        self.canvas.draw_idle()

    def choose_export_path(self) -> None:
        """Prompt for a PNG, SVG, or PDF destination."""
        selected, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Chart",
            f"{self.spec.title or 'chart'}.png",
            "PNG Image (*.png);;SVG Vector (*.svg);;PDF Document (*.pdf)",
        )
        if not selected:
            return
        destination = Path(selected)
        if not destination.suffix:
            suffixes = {
                "SVG Vector (*.svg)": ".svg",
                "PDF Document (*.pdf)": ".pdf",
            }
            destination = destination.with_suffix(
                suffixes.get(selected_filter, ".png")
            )
        self.export(destination)

    def export(self, path: str | Path) -> Path:
        """Export based on the destination suffix."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        suffix = destination.suffix.lower()
        if suffix not in {".png", ".svg", ".pdf"}:
            raise ValueError("Charts can be exported as PNG, SVG, or PDF")
        self.figure.savefig(
            destination,
            format=suffix[1:],
            dpi=180 if suffix == ".png" else None,
            facecolor=self.figure.get_facecolor(),
        )
        return destination

    def export_png(self, path: str | Path) -> Path:
        """Retain the direct PNG export API."""
        destination = Path(path)
        if destination.suffix.lower() != ".png":
            destination = destination.with_suffix(".png")
        return self.export(destination)

    def copy_image(self) -> None:
        """Copy the rendered chart to the system clipboard."""
        QApplication.clipboard().setPixmap(self.canvas.grab())

    def closeEvent(self, event: Any) -> None:
        self.closeRequested.emit(self.spec.chart_id)
        super().closeEvent(event)
