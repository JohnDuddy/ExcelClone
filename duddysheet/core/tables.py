"""Excel Tables (ListObjects): geometry, structured references, styles, totals.

A table is a rectangle on one sheet with a header row, data rows, and an
optional total row. Formulas refer to its parts with structured references:
``Table1[Sales]``, ``Table1[[#Headers],[Sales]]``, ``Table1[#All]``,
``[@Qty]`` (this row), and ``Table1[[Qty]:[Price]]``. References resolve
against the table's current size, so they follow the table as it grows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from duddysheet.core.cell import BorderStyle, CellFormat
from duddysheet.core.refs import CellReference, RangeReference

SPECIFIERS = ("#All", "#Data", "#Headers", "#Totals", "#This Row")
TOTAL_FUNCTIONS = {
    "none": None,
    "average": 101,
    "count": 103,
    "count_numbers": 102,
    "max": 104,
    "min": 105,
    "sum": 109,
    "stddev": 107,
    "var": 110,
}
TOTAL_LABELS = {
    "none": "None",
    "average": "Average",
    "count": "Count",
    "count_numbers": "Count Numbers",
    "max": "Max",
    "min": "Min",
    "sum": "Sum",
    "stddev": "StdDev",
    "var": "Var",
}


@dataclass(frozen=True, slots=True)
class TableSpec:
    """One Excel Table: its rectangle (header through total row) and options."""

    name: str
    top: int
    left: int
    bottom: int
    right: int
    columns: tuple[str, ...]
    style: str = "TableStyleMedium2"
    show_totals: bool = False
    banded_rows: bool = True
    banded_columns: bool = False
    first_column: bool = False
    last_column: bool = False
    filter_button: bool = True
    totals: tuple[tuple[str, str], ...] = ()
    calculated: tuple[tuple[str, str], ...] = ()

    @property
    def header_row(self) -> int:
        return self.top

    @property
    def first_data_row(self) -> int:
        return self.top + 1

    @property
    def last_data_row(self) -> int:
        return self.bottom - 1 if self.show_totals else self.bottom

    @property
    def totals_row(self) -> int | None:
        return self.bottom if self.show_totals else None

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return self.top, self.left, self.bottom, self.right

    def contains(self, row: int, column: int) -> bool:
        return self.top <= row <= self.bottom and self.left <= column <= self.right

    def column_index(self, name: str) -> int | None:
        folded = name.strip().casefold()
        for index, column in enumerate(self.columns):
            if column.casefold() == folded:
                return self.left + index
        return None

    def total_function(self, column: str) -> str:
        return dict((key.casefold(), value) for key, value in self.totals).get(column.casefold(), "none")


# ------------------------------------------------------------------ lookups
def tables_in(workbook: Any) -> list[tuple[Any, TableSpec]]:
    """Return (sheet, table) pairs across the workbook."""
    return [(sheet, table) for sheet in workbook for table in sheet.tables]


def find_table(workbook: Any, name: str) -> tuple[Any, TableSpec] | None:
    folded = name.casefold()
    for sheet, table in tables_in(workbook):
        if table.name.casefold() == folded:
            return sheet, table
    return None


def table_at(sheet: Any, row: int, column: int) -> TableSpec | None:
    for table in sheet.tables:
        if table.contains(row, column):
            return table
    return None


def next_table_name(workbook: Any) -> str:
    used = {table.name.casefold() for _, table in tables_in(workbook)}
    number = 1
    while f"table{number}" in used:
        number += 1
    return f"Table{number}"


def validate_table_name(workbook: Any, name: str, *, current: str | None = None) -> None:
    """Raise ValueError when a table name is invalid or already used."""
    if not re.fullmatch(r"[A-Za-z_\\][A-Za-z0-9_.\\]*", name):
        raise ValueError(f"The name {name!r} is not valid. Table names start with a letter or underscore.")
    from duddysheet.core.refs import parse_a1

    try:
        parse_a1(name)
    except ValueError:
        pass
    else:
        raise ValueError(f"A table name cannot look like a cell reference: {name!r}")
    existing = find_table(workbook, name)
    if existing is not None and (current is None or existing[1].name.casefold() != current.casefold()):
        raise ValueError(f"A table named {name!r} already exists.")
    try:
        workbook.get_name(name)
    except (KeyError, ValueError):
        return
    raise ValueError(f"The name {name!r} is already used by a defined name.")


# --------------------------------------------------- structured references
@dataclass(frozen=True, slots=True)
class StructuredSpec:
    """The parsed inside of a structured reference's brackets."""

    specifiers: tuple[str, ...] = ()
    first_column: str | None = None
    last_column: str | None = None
    this_row: bool = False


def _unescape(text: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == "'" and index + 1 < len(text):
            result.append(text[index + 1])
            index += 2
            continue
        result.append(text[index])
        index += 1
    return "".join(result)


def _split_items(inner: str) -> list[str]:
    """Split ``[a],[b]:[c]`` at top-level commas."""
    items: list[str] = []
    depth = 0
    current: list[str] = []
    index = 0
    while index < len(inner):
        character = inner[index]
        if character == "'" and index + 1 < len(inner):
            current.append(inner[index : index + 2])
            index += 2
            continue
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
        if character == "," and depth == 0:
            items.append("".join(current).strip())
            current = []
        else:
            current.append(character)
        index += 1
    if current:
        items.append("".join(current).strip())
    return items


def _strip_brackets(text: str) -> str:
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        return text[1:-1]
    return text


def parse_structured(inner: str) -> StructuredSpec:
    """Parse the text between a table's outer brackets."""
    inner = inner.strip()
    specifiers: list[str] = []
    first: str | None = None
    last: str | None = None
    this_row = False
    if inner.startswith("@"):
        this_row = True
        inner = inner[1:].strip()
        if not inner:
            return StructuredSpec((), None, None, True)
        if inner.startswith("[") and "]:[" in inner:
            left, _, right = inner.partition("]:")
            first = _unescape(_strip_brackets(left + "]"))
            last = _unescape(_strip_brackets(right))
            return StructuredSpec((), first, last, True)
        name = _unescape(_strip_brackets(inner))
        return StructuredSpec((), name, name, True)
    items = _split_items(inner) if inner.startswith("[") else [inner]
    for item in items:
        if not item:
            continue
        if item.startswith("@"):
            this_row = True
            item = item[1:]
            if not item:
                continue
        if ":" in item and item.count("[") >= 2:
            left, _, right = item.partition("]:")
            first = _unescape(_strip_brackets(left + "]"))
            last = _unescape(_strip_brackets(right))
            continue
        name = _strip_brackets(item)
        unescaped = _unescape(name)
        canonical = next((value for value in SPECIFIERS if value.casefold() == unescaped.strip().casefold()), None)
        if canonical == "#This Row":
            this_row = True
        elif canonical is not None:
            specifiers.append(canonical)
        else:
            first = last = unescaped
    return StructuredSpec(tuple(specifiers), first, last, this_row)


def _escape(name: str) -> str:
    return re.sub(r"(['#\[\]@])", r"'\1", name)


def render_structured(table: str | None, spec: StructuredSpec, *, file_format: bool = False) -> str:
    """Render a structured reference; ``file_format`` spells ``@`` as [#This Row]."""
    prefix = table or ""
    columns = ""
    if spec.first_column is not None:
        columns = f"[{_escape(spec.first_column)}]"
        if spec.last_column is not None and spec.last_column.casefold() != spec.first_column.casefold():
            columns += f":[{_escape(spec.last_column)}]"
    if spec.this_row and not file_format:
        if not spec.specifiers:
            if spec.first_column is None:
                return f"{prefix}[@]"
            simple = spec.last_column is None or spec.last_column.casefold() == spec.first_column.casefold()
            if simple and re.fullmatch(r"[A-Za-z0-9_.]+", spec.first_column):
                return f"{prefix}[@{spec.first_column}]"
            return f"{prefix}[@{columns}]"
    items = list(spec.specifiers)
    if spec.this_row:
        items.insert(0, "#This Row")
    if not items:
        if not columns:
            return f"{prefix}[]" if table is None else prefix
        if ":" not in columns:
            return f"{prefix}{columns}"
        return f"{prefix}[{columns}]"
    parts = [f"[{item}]" for item in items]
    if columns:
        parts.append(columns)
    if len(parts) == 1 and not columns:
        return f"{prefix}{parts[0]}"
    return f"{prefix}[{','.join(parts)}]"


def resolve_structured(
    workbook: Any,
    table_name: str | None,
    spec: StructuredSpec,
    sheet_name: str,
    origin: tuple[int, int],
) -> CellReference | RangeReference | None:
    """Return the cells a structured reference names, or ``None`` (#REF!)."""
    if table_name is None:
        try:
            sheet = workbook.get_sheet(sheet_name)
        except KeyError:
            return None
        table = table_at(sheet, *origin)
        if table is None:
            return None
    else:
        found = find_table(workbook, table_name)
        if found is None:
            return None
        sheet, table = found
    if spec.first_column is None:
        left, right = table.left, table.right
    else:
        left = table.column_index(spec.first_column)
        right = table.column_index(spec.last_column or spec.first_column)
        if left is None or right is None:
            return None
        left, right = sorted((left, right))
    specifiers = set(spec.specifiers)
    if spec.this_row:
        row = origin[0]
        if not table.first_data_row <= row <= table.last_data_row:
            return None
        top = bottom = row
    elif "#All" in specifiers:
        top, bottom = table.top, table.bottom
    else:
        rows: list[tuple[int, int]] = []
        if "#Headers" in specifiers:
            rows.append((table.top, table.top))
        if "#Data" in specifiers or not specifiers:
            rows.append((table.first_data_row, table.last_data_row))
        if "#Totals" in specifiers:
            if table.totals_row is None:
                return None
            rows.append((table.totals_row, table.totals_row))
        top = min(item[0] for item in rows)
        bottom = max(item[1] for item in rows)
        if bottom < top:
            bottom = top
    start = CellReference(top, left, sheet=sheet.name, row_absolute=True, column_absolute=True)
    if top == bottom and left == right:
        return start
    end = CellReference(bottom, right, sheet=sheet.name, row_absolute=True, column_absolute=True)
    return RangeReference(start, end)


# ------------------------------------------------------------------- styles
_ACCENTS = ("#156082", "#e97132", "#196b24", "#0f9ed5", "#a02b93", "#4ea72e")
_NEUTRAL = "#404040"


def _tint(color: str, amount: float) -> str:
    red, green, blue = (int(color[index : index + 2], 16) for index in (1, 3, 5))
    return "#" + "".join(f"{round(channel + (255 - channel) * amount):02x}" for channel in (red, green, blue))


@dataclass(frozen=True, slots=True)
class TableStyle:
    """Colors for one table style's header, stripes, and borders."""

    name: str
    header_fill: str | None
    header_font: str
    band_fill: str | None
    border: str
    totals_border: str


def _styles() -> dict[str, TableStyle]:
    styles: dict[str, TableStyle] = {}
    colors = (_NEUTRAL,) + _ACCENTS
    for index, accent in enumerate(colors):
        number = index + 1
        # Light: accent rules and pale stripes; header text in accent.
        styles[f"TableStyleLight{number}"] = TableStyle(
            f"TableStyleLight{number}", None, accent, _tint(accent, 0.85), accent, accent
        )
        styles[f"TableStyleLight{number + 7}"] = TableStyle(
            f"TableStyleLight{number + 7}", accent, "#ffffff", None, accent, accent
        )
        # Medium: solid accent header with white bold text, tinted stripes.
        styles[f"TableStyleMedium{number}"] = TableStyle(
            f"TableStyleMedium{number}", accent, "#ffffff", _tint(accent, 0.8), _tint(accent, 0.4), accent
        )
        styles[f"TableStyleMedium{number + 7}"] = TableStyle(
            f"TableStyleMedium{number + 7}", accent, "#ffffff", _tint(accent, 0.6), "#ffffff", accent
        )
        # Dark: black header, deep accent stripes.
        styles[f"TableStyleDark{number}"] = TableStyle(
            f"TableStyleDark{number}", "#000000", "#ffffff", _tint(accent, 0.25), accent, "#000000"
        )
    # Excel's default is Medium 2 (first accent); Medium1 is the neutral one.
    return styles


TABLE_STYLES = _styles()
TABLE_STYLES["TableStyleMedium2"] = TableStyle(
    "TableStyleMedium2", _ACCENTS[0], "#ffffff", _tint(_ACCENTS[0], 0.8), _tint(_ACCENTS[0], 0.4), _ACCENTS[0]
)


def style_cell(table: TableSpec, row: int, column: int, base: CellFormat) -> CellFormat:
    """Overlay a table style on a cell's own format (explicit fills win)."""
    style = TABLE_STYLES.get(table.style)
    if style is None or table.style == "None":
        return base
    changes: dict[str, Any] = {}
    border = BorderStyle("thin", style.border)
    if row == table.header_row:
        if base.fill_color is None and style.header_fill:
            changes["fill_color"] = style.header_fill
        if base.font_color == "#000000":
            changes["font_color"] = style.header_font
        changes["bold"] = True
        changes["bottom_border"] = border if base.bottom_border.style == "none" else base.bottom_border
    elif table.totals_row is not None and row == table.totals_row:
        changes["bold"] = True
        if base.top_border.style == "none":
            changes["top_border"] = BorderStyle("double", style.totals_border)
    else:
        offset = row - table.first_data_row
        column_offset = column - table.left
        banded = (
            (table.banded_rows and offset % 2 == 0)
            or (table.banded_columns and column_offset % 2 == 0)
        )
        if banded and base.fill_color is None and style.band_fill:
            changes["fill_color"] = style.band_fill
        if base.bottom_border.style == "none" and style.header_fill is None:
            changes["bottom_border"] = BorderStyle("thin", _tint(style.border, 0.5))
    if (table.first_column and column == table.left) or (table.last_column and column == table.right):
        changes["bold"] = True
    return replace(base, **changes) if changes else base


# --------------------------------------------------------- table operations
def header_names(sheet: Any, top: int, left: int, right: int) -> tuple[str, ...]:
    """Return unique column names from a header row, filling blanks."""
    names: list[str] = []
    for index, column in enumerate(range(left, right + 1), start=1):
        value = sheet.get_cell(top, column).display_value
        text = "" if value is None else (str(int(value)) if isinstance(value, float) and value.is_integer() else str(value))
        text = text.strip() or f"Column{index}"
        base = text
        suffix = 2
        while text.casefold() in (name.casefold() for name in names):
            text = f"{base}{suffix}"
            suffix += 1
        names.append(text)
    return tuple(names)


def create_table(
    workbook: Any,
    sheet_name: str,
    area: tuple[int, int, int, int],
    *,
    has_headers: bool = True,
    name: str | None = None,
    style: str = "TableStyleMedium2",
) -> TableSpec:
    """Turn a range into a table; without headers a header row is inserted above."""
    from duddysheet.core.editing import shift_cells

    sheet = workbook.get_sheet(sheet_name)
    top, left, bottom, right = area
    for existing in sheet.tables:
        if not (existing.bottom < top or existing.top > bottom or existing.right < left or existing.left > right):
            raise ValueError("A table can't overlap another table.")
    if not has_headers:
        shift_cells(workbook, sheet_name, (top, left, top, right), direction="down")
        for index, column in enumerate(range(left, right + 1), start=1):
            sheet.set_cell(top, column, f"Column{index}")
        bottom += 1
    if bottom == top:
        bottom = top + 1
    table_name = name or next_table_name(workbook)
    validate_table_name(workbook, table_name)
    columns = header_names(sheet, top, left, right)
    for index, column in enumerate(range(left, right + 1)):
        cell = sheet.get_cell(top, column)
        if cell.display_value in (None, ""):
            sheet.set_cell(top, column, columns[index], cell_format=cell.format)
    table = TableSpec(table_name, top, left, bottom, right, columns, style=style)
    sheet.tables.append(table)
    return table


def update_table(sheet: Any, old: TableSpec, new: TableSpec) -> None:
    sheet.tables = [new if table.name == old.name else table for table in sheet.tables]


def set_totals_row(workbook: Any, sheet_name: str, table: TableSpec, show: bool) -> TableSpec:
    """Show or hide the total row, writing SUBTOTAL formulas as Excel does."""
    from duddysheet.core.editing import shift_cells

    sheet = workbook.get_sheet(sheet_name)
    if show == table.show_totals:
        return table
    if show:
        below = table.bottom + 1
        occupied = any(sheet.get_cell(below, column).display_value not in (None, "") for column in range(table.left, table.right + 1))
        if occupied:
            shift_cells(workbook, sheet_name, (below, table.left, below, table.right), direction="down")
        totals = dict(table.totals) or {table.columns[-1]: "sum"}
        updated = replace(table, bottom=below, show_totals=True, totals=tuple(totals.items()))
        update_table(sheet, table, updated)
        write_totals(sheet, updated)
        return updated
    for column in range(table.left, table.right + 1):
        sheet.clear_cell(table.bottom, column)
    updated = replace(table, bottom=table.bottom - 1, show_totals=False)
    update_table(sheet, table, updated)
    return updated


def write_totals(sheet: Any, table: TableSpec) -> None:
    """Fill the total row: a 'Total' label and SUBTOTAL formulas per column."""
    row = table.totals_row
    if row is None:
        return
    functions = dict((key.casefold(), value) for key, value in table.totals)
    for index, name in enumerate(table.columns):
        column = table.left + index
        function = functions.get(name.casefold(), "none")
        code = TOTAL_FUNCTIONS.get(function)
        cell_format = sheet.get_cell(row, column).format
        if code is not None:
            reference = render_structured(None, StructuredSpec(first_column=name, last_column=name))
            sheet.set_cell(row, column, f"=SUBTOTAL({code},{reference})", cell_format=cell_format)
        elif index == 0:
            sheet.set_cell(row, column, "Total", cell_format=cell_format)
        else:
            sheet.clear_cell(row, column)


def resize_table(sheet: Any, table: TableSpec, area: tuple[int, int, int, int]) -> TableSpec:
    """Change a table's rectangle (the header row must stay in the same row)."""
    top, left, bottom, right = area
    if top != table.top:
        raise ValueError("The headers must remain in the same row.")
    columns = header_names(sheet, top, left, right)
    updated = replace(table, left=left, bottom=bottom, right=right, columns=columns)
    update_table(sheet, table, updated)
    return updated


def expand_for_entry(sheet: Any, row: int, column: int) -> TableSpec | None:
    """AutoExpansion: a value typed just below or right of a table extends it."""
    for table in sheet.tables:
        below = row == table.bottom + 1 and table.left <= column <= table.right and not table.show_totals
        beside = column == table.right + 1 and table.top <= row <= table.bottom
        if below:
            updated = replace(table, bottom=row)
            update_table(sheet, table, updated)
            fill_calculated(sheet, updated, row)
            return updated
        if beside:
            columns = header_names(sheet, table.top, table.left, column)
            if sheet.get_cell(table.top, column).display_value in (None, ""):
                sheet.set_cell(table.top, column, columns[-1])
            updated = replace(table, right=column, columns=columns)
            update_table(sheet, table, updated)
            return updated
    return None


def fill_calculated(sheet: Any, table: TableSpec, row: int) -> None:
    """Give a new data row the table's calculated-column formulas.

    Calculated formulas are stored as they read in the first data row, so
    plain A1 references shift to the new row like a fill-down.
    """
    from duddysheet.core.translation import translate_formula_copy

    for name, formula in table.calculated:
        column = table.column_index(name)
        if column is not None and sheet.get_cell(row, column).raw_input in (None, ""):
            shifted = translate_formula_copy(formula, rows=row - table.first_data_row)
            sheet.set_cell(row, column, shifted, cell_format=sheet.get_cell(row, column).format)


def make_calculated_column(sheet: Any, table: TableSpec, row: int, column: int) -> TableSpec | None:
    """A formula typed into an otherwise empty table column fills the whole column."""
    cell = sheet.get_cell(row, column)
    if not cell.is_formula or not (table.first_data_row <= row <= table.last_data_row):
        return None
    others = [
        sheet.get_cell(other, column)
        for other in range(table.first_data_row, table.last_data_row + 1)
        if other != row
    ]
    if any(other.raw_input not in (None, "") for other in others):
        return None
    name = table.columns[column - table.left]
    from duddysheet.core.translation import translate_formula_copy

    for other in range(table.first_data_row, table.last_data_row + 1):
        if other != row:
            formula = translate_formula_copy(cell.raw_input, rows=other - row)
            sheet.set_cell(other, column, formula, cell_format=sheet.get_cell(other, column).format)
    calculated = dict(table.calculated)
    calculated[name] = translate_formula_copy(cell.raw_input, rows=table.first_data_row - row)
    updated = replace(table, calculated=tuple(calculated.items()))
    update_table(sheet, table, updated)
    return updated


def qualify_structured(formula: str, table_name: str) -> str:
    """Add the table name to bare [Column] references (Excel's file form needs it)."""
    from duddysheet.core.parser import StructuredReferenceNode, map_children, parse_formula
    from duddysheet.core.translation import formula_to_text

    try:
        ast = parse_formula(formula)
    except ValueError:
        return formula

    def qualify(node: Any) -> Any:
        if isinstance(node, StructuredReferenceNode) and node.table is None:
            return StructuredReferenceNode(table_name, node.inner)
        return map_children(node, qualify)

    return formula_to_text(qualify(ast))


def rename_table_references(formula: str, old: str, new: str) -> str:
    """Rewrite structured references after a table is renamed."""
    from duddysheet.core.parser import StructuredReferenceNode, map_children, parse_formula
    from duddysheet.core.translation import formula_to_text

    if old.casefold() not in formula.casefold():
        return formula
    try:
        ast = parse_formula(formula)
    except ValueError:
        return formula

    def rename(node: Any) -> Any:
        if isinstance(node, StructuredReferenceNode) and node.table and node.table.casefold() == old.casefold():
            return StructuredReferenceNode(new, node.inner)
        return map_children(node, rename)

    return formula_to_text(rename(ast))


def convert_to_range(sheet: Any, table: TableSpec) -> None:
    """Keep the cells and formats but remove the table object."""
    from dataclasses import replace as clone

    for row in range(table.top, table.bottom + 1):
        for column in range(table.left, table.right + 1):
            cell = sheet.get_cell(row, column)
            styled = style_cell(table, row, column, cell.format)
            if styled != cell.format:
                sheet.put_cell(row, column, clone(cell, format=styled))
    sheet.tables = [item for item in sheet.tables if item.name != table.name]


def table_to_dict(table: TableSpec) -> dict[str, Any]:
    data = {name: getattr(table, name) for name in TableSpec.__dataclass_fields__}
    data["columns"] = list(table.columns)
    data["totals"] = [list(item) for item in table.totals]
    data["calculated"] = [list(item) for item in table.calculated]
    return data


def table_from_dict(data: dict[str, Any]) -> TableSpec:
    values = dict(data)
    values["columns"] = tuple(values.get("columns", ()))
    values["totals"] = tuple(tuple(item) for item in values.get("totals", ()))
    values["calculated"] = tuple(tuple(item) for item in values.get("calculated", ()))
    return TableSpec(**{key: value for key, value in values.items() if key in TableSpec.__dataclass_fields__})



def structured_to_a1(workbook: Any, table_name: str) -> None:
    """Rewrite structured references to a table as A1 references (Convert to Range)."""
    from dataclasses import replace as clone

    from duddysheet.core.parser import ReferenceNode, StructuredReferenceNode, map_children, parse_formula
    from duddysheet.core.translation import formula_to_text

    found = find_table(workbook, table_name)
    if found is None:
        return
    host, table = found
    folded = table.name.casefold()
    for sheet in workbook:
        for (row, column), cell in tuple(sheet.iter_populated()):
            if not cell.is_formula or "[" not in cell.raw_input:
                continue
            try:
                ast = parse_formula(cell.raw_input)
            except ValueError:
                continue
            changed = False

            def convert(node: Any, sheet: Any = sheet, row: int = row, column: int = column) -> Any:
                nonlocal changed
                if isinstance(node, StructuredReferenceNode):
                    named = node.table.casefold() if node.table else None
                    inside = node.table is None and sheet is host and table.contains(row, column)
                    if named == folded or inside:
                        resolved = resolve_structured(workbook, table.name, node.spec, sheet.name, (row, column))
                        if resolved is not None:
                            changed = True
                            if sheet is host:
                                resolved = _without_sheet(resolved)
                            if node.spec.this_row:
                                resolved = _relative_rows(resolved)
                            return ReferenceNode(resolved)
                return map_children(node, convert)

            rewritten = convert(ast)
            if changed:
                sheet.put_cell(row, column, clone(cell, raw_input=formula_to_text(rewritten)))


def _without_sheet(reference: Any) -> Any:
    from dataclasses import replace as clone

    if isinstance(reference, CellReference):
        return clone(reference, sheet=None)
    return RangeReference(clone(reference.start, sheet=None), clone(reference.end, sheet=None))


def _relative_rows(reference: Any) -> Any:
    """[@Col] becomes a row-relative reference such as $B2, as in Excel."""
    from dataclasses import replace as clone

    if isinstance(reference, CellReference):
        return clone(reference, row_absolute=False)
    return RangeReference(clone(reference.start, row_absolute=False), clone(reference.end, row_absolute=False))
