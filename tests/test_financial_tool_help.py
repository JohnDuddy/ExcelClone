from __future__ import annotations

import os
from html import escape

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication, QToolButton

from duddysheet.core.financial_help import (
    FINANCIAL_TOOL_HELP,
    FINANCIAL_TOOL_HELP_BY_KEY,
)
from duddysheet.ui.main_window import MainWindow
from duddysheet.ui.ribbon import FINANCIAL_RIBBON_HELP_KEYS, Ribbon
from duddysheet.ui.tool_help import tool_tip_html

# Menu action attribute on MainWindow -> help key it must carry.
MENU_ACTION_HELP_KEYS = {
    "financial_model_action": "new_model",
    "goal_seek_action": "goal_seek",
    "sensitivity_action": "sensitivity",
    "scenarios_action": "scenarios",
    "model_audit_action": "audit",
    "financial_help_action": "guide",
}


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_financial_menu_sits_between_formulas_and_help() -> None:
    application()
    window = MainWindow()
    titles = [action.text() for action in window.menuBar().actions()]
    window.close()

    assert titles.index("&Formulas") + 1 == titles.index("&Financial")
    assert titles.index("&Financial") + 1 == titles.index("&Help")


def test_financial_menu_shows_action_tooltips() -> None:
    application()
    window = MainWindow()
    visible = window.financial_menu.toolTipsVisible()
    window.close()

    # Without this Qt silently discards menu action tooltips.
    assert visible


@pytest.mark.parametrize(
    ("attribute", "help_key"),
    sorted(MENU_ACTION_HELP_KEYS.items()),
)
def test_every_financial_menu_command_has_a_bubble(
    attribute: str,
    help_key: str,
) -> None:
    application()
    window = MainWindow()
    action = getattr(window, attribute)
    tooltip = action.toolTip()
    status = action.statusTip()
    window.close()

    entry = FINANCIAL_TOOL_HELP_BY_KEY[help_key]
    assert tooltip == tool_tip_html(entry)
    # The bubble is rich text, so compare against the escaped copy.
    assert escape(entry.title) in tooltip
    assert escape(entry.summary) in tooltip
    assert escape(entry.scenario) in tooltip
    assert escape(entry.example_result) in tooltip
    assert status == f"{entry.title}: {entry.summary}"


def test_every_financial_menu_action_is_documented() -> None:
    application()
    window = MainWindow()
    labels = [
        action.text()
        for action in window.financial_menu.actions()
        if not action.isSeparator()
    ]
    documented = {
        getattr(window, attribute).text() for attribute in MENU_ACTION_HELP_KEYS
    }
    window.close()

    assert set(labels) == documented


def test_financial_ribbon_buttons_carry_the_same_bubbles() -> None:
    application()
    ribbon = Ribbon()
    page = next(
        ribbon.widget(index)
        for index in range(ribbon.count())
        if ribbon.tabText(index) == "Financial"
    )
    tooltips = {
        button.text(): button.toolTip()
        for button in page.findChildren(QToolButton)
    }
    ribbon.deleteLater()

    assert set(tooltips) == set(FINANCIAL_RIBBON_HELP_KEYS)
    for label, help_key in FINANCIAL_RIBBON_HELP_KEYS.items():
        assert tooltips[label] == tool_tip_html(FINANCIAL_TOOL_HELP_BY_KEY[help_key])


def test_help_keys_are_unique_and_fully_used() -> None:
    keys = [entry.key for entry in FINANCIAL_TOOL_HELP]

    assert len(keys) == len(set(keys))
    assert set(keys) == set(MENU_ACTION_HELP_KEYS.values())
    assert set(keys) == set(FINANCIAL_RIBBON_HELP_KEYS.values())


@pytest.mark.parametrize("entry", FINANCIAL_TOOL_HELP, ids=lambda e: e.key)
def test_every_bubble_is_complete(entry: object) -> None:
    assert entry.title
    assert entry.summary.endswith(".")
    assert entry.example_lines
    assert entry.example_result
    assert entry.detail


@pytest.mark.parametrize("entry", FINANCIAL_TOOL_HELP, ids=lambda e: e.key)
def test_every_bubble_grounds_the_command_in_a_real_situation(
    entry: object,
) -> None:
    # A scenario has to describe a situation, not restate the mechanics, so it
    # needs room to do so and must read as prose.
    assert len(entry.scenario) >= 120
    assert entry.scenario.endswith(".")
    assert entry.scenario[0].isupper()


def test_bubble_markup_preserves_example_alignment() -> None:
    html = tool_tip_html(FINANCIAL_TOOL_HELP_BY_KEY["goal_seek"])

    # Rich text collapses plain runs of spaces, which would break the columns.
    assert "&nbsp;&nbsp;" in html
    assert "<code>" in html


def test_bubble_markup_constrains_its_width() -> None:
    html = tool_tip_html(FINANCIAL_TOOL_HELP_BY_KEY["sensitivity"])

    # Without the fixed-width table the scenario paragraph will not wrap and
    # the bubble stretches to roughly three times the screen-friendly width.
    assert "<table width='380'" in html
