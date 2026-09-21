"""Application construction and entry-point behavior."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

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


def startup_path(arguments: Sequence[str]) -> Path | None:
    """Return the workbook named on the command line, if one was given.

    Accepts ``--open PATH``, ``--open=PATH``, or a single bare path, so the
    application can be started from a script, a shortcut, or a file
    association. An option given without a value yields no file rather than an
    error, because an empty window is a usable outcome.
    """
    remaining = list(arguments)
    while remaining:
        argument = remaining.pop(0)
        if argument.startswith("--open="):
            value = argument.partition("=")[2]
            return Path(value) if value else None
        if argument == "--open":
            return Path(remaining[0]) if remaining else None
        if not argument.startswith("-"):
            return Path(argument)
    return None


def open_startup_workbook(window: MainWindow, path: Path) -> None:
    """Load a startup workbook, reporting any failure in the window itself.

    A file that cannot be read leaves the application open and empty rather
    than exiting, so the user keeps a usable window and an explanation.
    """
    from PySide6.QtWidgets import QMessageBox

    try:
        warnings = window.open_path(path)
    except (OSError, ValueError, KeyError) as error:
        QMessageBox.critical(window, "Open Failed", f"{path}\n\n{error}")
        return
    if warnings:
        QMessageBox.information(window, "Import Notes", "\n".join(warnings))


def main(argv: Sequence[str] | None = None) -> int:
    """Launch Duddy Spreadsheet and return the Qt process exit code.

    ``--self-test`` verifies a packaged build instead of starting the UI, and
    ``--version`` reports the version, so a release can be checked from a
    script without a human driving the interface. ``--open PATH``, or a single
    bare path, opens that workbook once the window exists.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)

    if "--version" in arguments:
        print(f"{PRODUCT_NAME} {VERSION}")
        return 0

    if "--self-test" in arguments:
        from duddysheet.selftest import run_self_test

        print(f"{PRODUCT_NAME} {VERSION} self-test\n")
        return run_self_test()

    app, window = create_application(argv)
    window.show()
    requested = startup_path(arguments)
    if requested is not None:
        open_startup_workbook(window, requested)
    return app.exec()
