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
    strikethrough: bool = False
    indent: int = 0
    text_rotation: int = 0
    shrink_to_fit: bool = False
    #: Protection flags take effect only while the sheet is protected.
    locked: bool = True
    formula_hidden: bool = False
    left_border: BorderStyle = field(default_factory=BorderStyle)
    right_border: BorderStyle = field(default_factory=BorderStyle)
    top_border: BorderStyle = field(default_factory=BorderStyle)
    bottom_border: BorderStyle = field(default_factory=BorderStyle)

    @property
    def is_default(self) -> bool:
        """Return whether every formatting attribute has its default value."""
        return self == DEFAULT_CELL_FORMAT


@dataclass(frozen=True, slots=True)
class Note:
    """A cell note (Excel's classic comment): text plus an author."""

    text: str
    author: str = ""


@dataclass(frozen=True, slots=True)
class SheetProtection:
    """Worksheet protection with Excel's permission switches.

    ``password_hash`` stores a salted SHA-256 digest, never the password.
    """

    password_hash: str = ""
    select_locked_cells: bool = True
    select_unlocked_cells: bool = True
    format_cells: bool = False
    format_columns: bool = False
    format_rows: bool = False
    insert_columns: bool = False
    insert_rows: bool = False
    insert_hyperlinks: bool = False
    delete_columns: bool = False
    delete_rows: bool = False
    sort: bool = False
    auto_filter: bool = False
    edit_objects: bool = False


@dataclass(frozen=True, slots=True)
class Hyperlink:
    """A cell hyperlink targeting a URL/file or an internal workbook location."""

    target: str
    internal: bool = False
    tooltip: str | None = None

    def __post_init__(self) -> None:
        if not self.target:
            raise ValueError("Hyperlink target cannot be empty")


@dataclass(frozen=True, slots=True)
class Cell:
    """Cell input, cached result, presentation format, and formula error."""

    raw_input: Any = None
    cached_value: Any = None
    format: CellFormat = field(default_factory=CellFormat)
    error: str | None = None
    spill_parent: tuple[int, int] | None = None
    hyperlink: Hyperlink | None = None

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
            and self.hyperlink is None
            and self.format.is_default
        )

    @property
    def is_spill(self) -> bool:
        """Return whether this cell is owned by a dynamic-array anchor."""
        return self.spill_parent is not None

    def with_result(self, cached_value: Any, error: str | None) -> Cell:
        """Return this cell with a new calculated value (fast ``replace``)."""
        return Cell(
            self.raw_input,
            cached_value,
            self.format,
            error,
            self.spill_parent,
            self.hyperlink,
        )

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
