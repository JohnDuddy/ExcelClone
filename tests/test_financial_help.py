from __future__ import annotations

from excelclone.core.financial_help import (
    FINANCIAL_HELP_CATEGORIES,
    FINANCIAL_HELP_ENTRIES,
)
from excelclone.core.functions import FUNCTION_REGISTRY
from excelclone.core.parser import parse_formula


def test_financial_help_covers_every_registered_financial_function() -> None:
    financial_names = {
        name
        for name, spec in FUNCTION_REGISTRY.items()
        if spec.implementation.__module__.endswith("finance_fn")
    }

    assert len(FINANCIAL_HELP_ENTRIES) == 46
    assert {entry.name for entry in FINANCIAL_HELP_ENTRIES} == financial_names
    assert len(FINANCIAL_HELP_CATEGORIES) == 8


def test_every_financial_help_entry_is_detailed_and_examples_parse() -> None:
    for entry in FINANCIAL_HELP_ENTRIES:
        assert entry.category
        assert entry.syntax.startswith(f"{entry.name}(")
        assert len(entry.summary) >= 20
        assert len(entry.use_when) >= 30
        assert entry.example.startswith("=")
        assert len(entry.notes) >= 2
        assert entry.related
        assert set(entry.related) <= set(FUNCTION_REGISTRY)
        parse_formula(entry.example)
