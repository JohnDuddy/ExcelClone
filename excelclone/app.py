"""Application construction and entry-point behavior."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtWidgets import QApplication

from excelclone.ui.main_window import MainWindow


def create_application(
    argv: Sequence[str] | None = None,
) -> tuple[QApplication, MainWindow]:
    """Create the Qt application and its main window without starting the event loop."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv) if argv is not None else sys.argv)
    if not isinstance(app, QApplication):
        raise RuntimeError("An incompatible Qt application instance already exists")

    app.setApplicationName("OpenGrid")
    app.setApplicationDisplayName("OpenGrid — Personal Spreadsheet")
    app.setOrganizationName("OpenGrid")

    return app, MainWindow()


def main(argv: Sequence[str] | None = None) -> int:
    """Launch OpenGrid and return the Qt process exit code."""
    app, window = create_application(argv)
    window.show()
    return app.exec()

