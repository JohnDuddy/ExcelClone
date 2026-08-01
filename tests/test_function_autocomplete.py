from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from duddysheet.core.completion import (
    active_call_at,
    find_functions,
    function_prefix_at,
)
from duddysheet.ui.delegates import CellDelegate
from duddysheet.ui.formula_bar import FormulaBar
from duddysheet.ui.main_window import MainWindow


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def press(target: object, key: Qt.Key) -> None:
    """Deliver a key press to a focused editor the way Qt would."""
    application().sendEvent(
        target,
        QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier),
    )


def type_formula(editor: object, text: str) -> None:
    """Set editor text and announce it the way interactive typing does."""
    editor.setText(text)
    editor.setCursorPosition(len(text))
    editor.textEdited.emit(text)


def test_find_functions_returns_sorted_prefix_matches() -> None:
    matches = find_functions("S")
    names = [spec.name for spec in matches]

    assert names
    assert names == sorted(names)
    assert all(name.startswith("S") for name in names)
    assert "SUM" in names
    assert "AVERAGE" not in names


def test_find_functions_is_case_insensitive_and_handles_misses() -> None:
    assert [spec.name for spec in find_functions("su")] == [
        spec.name for spec in find_functions("SU")
    ]
    assert find_functions("zzzz") == ()
    assert len(find_functions("")) == 196


@pytest.mark.parametrize(
    ("text", "cursor", "expected"),
    [
        ("=SU", 3, ("SU", 1, 3)),
        ("=A1+SU", 6, ("SU", 4, 6)),
        ("=sum", 4, ("SUM", 1, 4)),
        ("=IF(A1,SU", 9, ("SU", 7, 9)),
    ],
)
def test_function_prefix_at_locates_the_name_being_typed(
    text: str,
    cursor: int,
    expected: tuple[str, int, int],
) -> None:
    prefix = function_prefix_at(text, cursor)

    assert prefix is not None
    assert (prefix.text, prefix.start, prefix.end) == expected


@pytest.mark.parametrize(
    ("text", "cursor"),
    [
        ("hello", 5),
        ('="SU', 4),
        ("=SUM(", 5),
        ("=Sheet1!A1", 10),
        ("=$A$1", 5),
        ("=", 1),
    ],
)
def test_function_prefix_at_rejects_non_function_contexts(
    text: str,
    cursor: int,
) -> None:
    assert function_prefix_at(text, cursor) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("=SUM(", ("SUM", 0)),
        ("=SUM(A1,", ("SUM", 1)),
        ("=SUM(A1,B1,C1,", ("SUM", 3)),
        ('=IF(A1="a,b",', ("IF", 1)),
        ("=SUM(MAX(1,2),", ("SUM", 1)),
        ("=SUM(A1, MAX(", ("MAX", 0)),
        ("=SUM((1+2),", ("SUM", 1)),
        ("=SUM({1,2},", ("SUM", 1)),
    ],
)
def test_active_call_at_tracks_nesting_strings_and_arrays(
    text: str,
    expected: tuple[str, int],
) -> None:
    call = active_call_at(text, len(text))

    assert call is not None
    assert (call.name, call.argument_index) == expected


@pytest.mark.parametrize("text", ["=SUM(A1)", "=(1+2", "=A1+2", "plain text"])
def test_active_call_at_reports_no_call_outside_one(text: str) -> None:
    assert active_call_at(text, len(text)) is None


def test_active_call_clamps_onto_the_repeating_field() -> None:
    call = active_call_at("=SUM(A1,A2,A3,A4,", 17)

    assert call is not None
    assert call.argument_index == 4
    assert call.fields == ("number1", "[number2]", "...")
    assert call.active_field == 2


def test_formula_bar_suggests_functions_while_typing() -> None:
    application()
    bar = FormulaBar()
    bar.show()

    type_formula(bar.editor, "=S")

    assert bar.completer.is_active()
    names = bar.completer.suggestions()
    assert "SUM" in names
    assert all(name.startswith("S") for name in names)

    bar.close()


def test_formula_bar_accepts_a_suggestion_with_return() -> None:
    application()
    bar = FormulaBar()
    bar.show()
    type_formula(bar.editor, "=SU")

    press(bar.editor, Qt.Key.Key_Down)
    press(bar.editor, Qt.Key.Key_Return)

    assert bar.completer.suggestions()[:2] == ("SUBSTITUTE", "SUM")
    assert bar.editor.text() == "=SUM"
    assert not bar.completer.is_active()

    bar.close()


def test_formula_bar_accepts_the_first_suggestion_with_tab() -> None:
    application()
    bar = FormulaBar()
    bar.show()
    type_formula(bar.editor, "=SUM")

    press(bar.editor, Qt.Key.Key_Tab)

    assert bar.editor.text() == "=SUM"
    assert bar.editor.cursorPosition() == 4
    assert not bar.completer.is_active()

    bar.close()


def test_accepting_a_function_inserts_the_bare_name() -> None:
    application()
    bar = FormulaBar()
    bar.show()
    type_formula(bar.editor, "=VLOO")

    press(bar.editor, Qt.Key.Key_Return)

    assert bar.editor.text() == "=VLOOKUP"
    assert not bar.completer.is_active()
    assert not bar.completer.is_tip_active()

    bar.close()


def test_typing_the_open_paren_starts_the_argument_guide() -> None:
    application()
    bar = FormulaBar()
    bar.show()
    type_formula(bar.editor, "=VLOO")
    press(bar.editor, Qt.Key.Key_Return)

    type_formula(bar.editor, "=VLOOKUP(")

    assert bar.completer.is_tip_active()
    assert bar.completer.argument_tip() == (
        "VLOOKUP(lookup_value, table_array, col_index_num, [range_lookup])"
    )
    assert bar.completer.active_argument() == "lookup_value"

    bar.close()


@pytest.mark.parametrize(
    ("typed", "expected_field"),
    [
        ("=VLOOKUP(", "lookup_value"),
        ("=VLOOKUP(A1,", "table_array"),
        ("=VLOOKUP(A1,B:C,", "col_index_num"),
        ("=VLOOKUP(A1,B:C,2,", "[range_lookup]"),
    ],
)
def test_argument_guide_steps_through_each_field(
    typed: str,
    expected_field: str,
) -> None:
    application()
    bar = FormulaBar()
    bar.show()

    type_formula(bar.editor, typed)

    assert bar.completer.is_tip_active()
    assert bar.completer.active_argument() == expected_field

    bar.close()


def test_argument_guide_holds_on_the_repeating_field() -> None:
    application()
    bar = FormulaBar()
    bar.show()

    type_formula(bar.editor, "=SUM(A1,A2,A3,")

    assert bar.completer.argument_tip() == "SUM(number1, [number2], ...)"
    assert bar.completer.active_argument() == "..."

    bar.close()


def test_argument_guide_tracks_the_innermost_call() -> None:
    application()
    bar = FormulaBar()
    bar.show()

    type_formula(bar.editor, "=SUM(A1, MAX(")
    assert bar.completer.argument_tip() == "MAX(number1, [number2], ...)"

    type_formula(bar.editor, "=SUM(MAX(1,2),")
    assert bar.completer.argument_tip() == "SUM(number1, [number2], ...)"

    bar.close()


def test_argument_guide_closes_with_the_call() -> None:
    application()
    bar = FormulaBar()
    bar.show()
    type_formula(bar.editor, "=SUM(A1,")
    assert bar.completer.is_tip_active()

    type_formula(bar.editor, "=SUM(A1)")

    assert not bar.completer.is_tip_active()
    assert bar.completer.argument_tip() is None

    bar.close()


def test_argument_less_function_shows_no_guide() -> None:
    application()
    bar = FormulaBar()
    bar.show()
    type_formula(bar.editor, "=TODA")
    press(bar.editor, Qt.Key.Key_Return)

    assert bar.editor.text() == "=TODAY"

    type_formula(bar.editor, "=TODAY(")

    assert not bar.completer.is_tip_active()

    bar.close()


def test_suggestion_list_and_argument_guide_are_never_both_shown() -> None:
    application()
    bar = FormulaBar()
    bar.show()

    type_formula(bar.editor, "=SU")
    assert bar.completer.is_active()
    assert not bar.completer.is_tip_active()

    type_formula(bar.editor, "=SUM(")
    assert not bar.completer.is_active()
    assert bar.completer.is_tip_active()

    bar.close()


def test_escape_dismisses_suggestions_without_clearing_the_editor() -> None:
    application()
    bar = FormulaBar()
    bar.show()
    type_formula(bar.editor, "=SU")

    press(bar.editor, Qt.Key.Key_Escape)

    assert not bar.completer.is_active()
    assert bar.editor.text() == "=SU"

    bar.close()


def test_moving_the_cursor_out_of_a_name_dismisses_suggestions() -> None:
    application()
    bar = FormulaBar()
    bar.show()
    type_formula(bar.editor, "=SUM(1)")
    assert not bar.completer.is_active()

    bar.editor.setCursorPosition(4)
    assert bar.completer.is_active()

    bar.editor.setCursorPosition(7)
    assert not bar.completer.is_active()

    bar.close()


def test_plain_text_entry_shows_no_suggestions() -> None:
    application()
    bar = FormulaBar()
    bar.show()

    type_formula(bar.editor, "Salary")

    assert not bar.completer.is_active()

    bar.close()


def test_selecting_another_cell_dismisses_suggestions() -> None:
    application()
    bar = FormulaBar()
    bar.show()
    type_formula(bar.editor, "=S")
    assert bar.completer.is_active()

    bar.set_cell("B2", "=1+1")

    assert not bar.completer.is_active()
    assert bar.editor.text() == "=1+1"

    bar.close()


def test_cell_editor_suggests_functions_and_keeps_model_commits() -> None:
    application()
    window = MainWindow()
    delegate = window.grid.itemDelegate()
    assert isinstance(delegate, CellDelegate)
    index = window.grid_model.index(0, 0)
    window.show()
    window.grid.setCurrentIndex(index)
    window.grid.edit(index)
    editor = window.grid.focusWidget()
    assert editor.objectName() == "cellEditor"

    type_formula(editor, "=SU")
    completer = editor.findChild(type(window.formula_bar.completer))
    assert completer is not None
    assert completer.is_active()
    assert "SUM" in completer.suggestions()

    # The open list claims Return, so the key completes the name instead of
    # committing the half-typed cell.
    press(editor, Qt.Key.Key_Return)
    assert editor.text() == "=SUBSTITUTE"
    assert not completer.is_active()
    assert window.grid_model.sheet.get_cell(0, 0).raw_input is None

    # The guide takes over once the call is opened, inside the cell too.
    type_formula(editor, "=SUBSTITUTE(A1,")
    assert completer.active_argument() == "old_text"

    editor.setText("=SUM(2,3)")
    delegate.setModelData(editor, window.grid_model, index)
    cell = window.grid_model.sheet.get_cell(0, 0)
    assert cell.raw_input == "=SUM(2,3)"
    assert cell.display_value == 5

    window.close()


def test_cell_editor_round_trips_existing_raw_input() -> None:
    application()
    window = MainWindow()
    delegate = window.grid.itemDelegate()
    index = window.grid_model.index(1, 1)
    window.grid_model.setData(index, "=1+1")

    editor = delegate.createEditor(window.grid.viewport(), QStyleOptionViewItem(), index)
    delegate.setEditorData(editor, index)

    assert editor.text() == "=1+1"

    window.close()
