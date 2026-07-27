from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from duddysheet.app import create_application


def test_application_shell_uses_product_title() -> None:
    app, window = create_application([])

    assert app.applicationName() == "Duddy Spreadsheet"
    assert window.windowTitle() == "Duddy Spreadsheet"
    assert window.minimumWidth() >= 800
    assert window.minimumHeight() >= 600

    window.close()
