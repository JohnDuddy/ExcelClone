"""Immutable cell content and formatting values."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class BorderStyle:
    """One edge of a cell border."""

    style: str = "none"
    color: str = "#000000"


@dataclass(frozen=True, slots=True)
class CellFormat:
    """Presentation attributes stored independently from cell content."""

    number_format: str = "General"
    font_family: str = "Aptos"
    font_size: float = 11.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    font_color: str = "#000000"
    fill_color: str | None = None
    horizontal_alignment: str = "general"
    vertical_alignment: str = "bottom"
    wrap_text: bool = False
    left_border: BorderStyle = field(default_factory=BorderStyle)
    right_border: BorderStyle = field(default_factory=BorderStyle)
    top_border: BorderStyle = field(default_factory=BorderStyle)
    bottom_border: BorderStyle = field(default_factory=BorderStyle)

    @property
    def is_default(self) -> bool:
        """Return whether every formatting attribute has its default value."""
        return self == DEFAULT_CELL_FORMAT


@dataclass(frozen=True, slots=True)
class Cell:
    """Cell input, cached result, presentation format, and formula error."""

    raw_input: Any = None
    cached_value: Any = None
    format: CellFormat = field(default_factory=CellFormat)
    error: str | None = None
    spill_parent: tuple[int, int] | None = None

    @property
    def is_formula(self) -> bool:
        """Return whether the raw input begins with the formula marker."""
        return isinstance(self.raw_input, str) and self.raw_input.startswith("=")

    @property
    def is_empty(self) -> bool:
        """Return whether the cell has no content, result, error, or formatting."""
        return (
            self.raw_input is None
            and self.cached_value is None
            and self.error is None
            and self.spill_parent is None
            and self.format.is_default
        )

    @property
    def is_spill(self) -> bool:
        """Return whether this cell is owned by a dynamic-array anchor."""
        return self.spill_parent is not None

    @property
    def display_value(self) -> Any:
        """Return the value suitable for display before number formatting."""
        if self.error is not None:
            return self.error
        if self.cached_value is not None:
            return self.cached_value
        return self.raw_input


DEFAULT_CELL_FORMAT = CellFormat()
EMPTY_CELL = Cell()
