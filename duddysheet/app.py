"""Application construction and entry-point behavior."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from duddysheet.branding import PRODUCT_NAME, VENDOR_NAME, VERSION
from duddysheet.ui.main_window import MainWindow
from duddysheet.util.logging_setup import configure_logging
from duddysheet.util.paths import resource_path


def create_application(
    argv: Sequence[str] | None = None,
) -> tuple[QApplication, MainWindow]:
    """Create the Qt application and its main window without starting the event loop."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv) if argv is not None else sys.argv)
    if not isinstance(app, QApplication):
        raise RuntimeError("An incompatible Qt application instance already exists")

    app.setApplicationName(PRODUCT_NAME)
    app.setApplicationDisplayName(PRODUCT_NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName(VENDOR_NAME)
    icon_path = resource_path("assets/duddysheet.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    configure_logging().info("%s %s starting", PRODUCT_NAME, VERSION)
    window = MainWindow()
    QTimer.singleShot(0, window.offer_recovery)
    return app, window


def main(argv: Sequence[str] | None = None) -> int:
    """Launch Duddy Spreadsheet and return the Qt process exit code."""
    app, window = create_application(argv)
    window.show()
    return app.exec()
