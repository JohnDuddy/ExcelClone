"""Main application window."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow


class MainWindow(QMainWindow):
    """Top-level OpenGrid window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OpenGrid — Personal Spreadsheet")
        self.setMinimumSize(800, 600)
        self.resize(1200, 760)

        welcome = QLabel("OpenGrid")
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome.setStyleSheet(
            "font-size: 28px; font-weight: 600; color: #1f4e3d; "
            "background: #f6f3e8;"
        )
        self.setCentralWidget(welcome)
        self.statusBar().showMessage("Ready")

