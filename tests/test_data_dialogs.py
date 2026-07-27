from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from duddysheet.core.refs import parse_a1
from duddysheet.ui.dialogs.data_tools import (
    FilterDialog,
    FindReplaceDialog,
    PasteSpecialDialog,
    SortDialog,
    ValidationDialog,
)


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_sort_dialog_returns_ordered_multi_keys() -> None:
    application()
    dialog = SortDialog(parse_a1("B2:D10"))
    dialog.key_rows[0][0].setCurrentIndex(2)
    dialog.key_rows[0][1].setCurrentIndex(1)
    dialog.key_rows[1][0].setCurrentIndex(1)

    keys = dialog.sort_keys()

    assert [(key.column, key.ascending) for key in keys] == [(2, False), (1, True)]
    dialog.close()


def test_filter_validation_find_and_paste_dialog_values() -> None:
    application()
    filter_dialog = FilterDialog(("A", "B"))
    filter_dialog.list_widget.item(1).setCheckState(Qt.CheckState.Unchecked)
    assert filter_dialog.allowed_values() == frozenset({"A"})

    validation_dialog = ValidationDialog(parse_a1("A1:A5"))
    validation_dialog.kind.setCurrentText("whole_number")
    validation_dialog.value1.setText("1")
    validation_dialog.value2.setText("10")
    assert validation_dialog.validation().values == (1, 10)

    find_dialog = FindReplaceDialog()
    find_dialog.query.setText("alpha")
    find_dialog.regex.setChecked(True)
    assert find_dialog.options().query == "alpha"
    assert find_dialog.options().regex

    paste_dialog = PasteSpecialDialog()
    paste_dialog.mode.setCurrentText("values")
    paste_dialog.transpose.setChecked(True)
    assert paste_dialog.mode.currentText() == "values"
    assert paste_dialog.transpose.isChecked()

    for dialog in (
        filter_dialog,
        validation_dialog,
        find_dialog,
        paste_dialog,
    ):
        dialog.close()
