"""Hover bubbles for the Financial menu and ribbon commands."""

from __future__ import annotations

from html import escape
from typing import Any

from duddysheet.core.financial_help import (
    FINANCIAL_TOOL_HELP_BY_KEY,
    FinancialToolHelp,
)


_BUBBLE_WIDTH = 380


def tool_tip_html(help_entry: FinancialToolHelp) -> str:
    """Render one command's hover bubble as rich text."""
    # Rich text collapses runs of spaces, which would destroy the column
    # alignment these example lines rely on.
    lines = "<br>".join(
        f"<code>{escape(line).replace(' ', '&nbsp;')}</code>"
        for line in help_entry.example_lines
    )
    # Rich-text tooltips do not wrap on their own; a fixed-width table is the
    # one width constraint Qt's tooltip layout reliably honours.
    body = (
        f"<p style='margin:0'><b>{escape(help_entry.title)}</b></p>"
        f"<p style='margin:4px 0 0 0'>{escape(help_entry.summary)}</p>"
        f"<p style='margin:8px 0 0 0'><i>In practice</i></p>"
        f"<p style='margin:2px 0 0 0'>{escape(help_entry.scenario)}</p>"
        f"<p style='margin:8px 0 0 0'><i>{escape(help_entry.example_title)}</i></p>"
        f"<p style='margin:2px 0 0 0'>{lines}</p>"
        f"<p style='margin:6px 0 0 0'>{escape(help_entry.example_result)}</p>"
        f"<p style='margin:8px 0 0 0'>{escape(help_entry.detail)}</p>"
    )
    return (
        f"<table width='{_BUBBLE_WIDTH}' cellspacing='0' cellpadding='0'>"
        f"<tr><td>{body}</td></tr></table>"
    )


def apply_tool_help(target: Any, key: str) -> None:
    """Attach the hover bubble and status-bar text for one command."""
    help_entry = FINANCIAL_TOOL_HELP_BY_KEY[key]
    target.setToolTip(tool_tip_html(help_entry))
    target.setStatusTip(f"{help_entry.title}: {help_entry.summary}")
