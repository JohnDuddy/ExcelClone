"""Excel's Go To Special: select cells by content type, structure, or relationship."""

from __future__ import annotations

from typing import Any

from duddysheet.core.navigation import SelectionRange, current_region, last_cell
from duddysheet.core.parser import collect_references, parse_formula
from duddysheet.core.refs import CellReference, RangeReference
from duddysheet.core.sheet import Sheet

GOTO_KINDS = (
    "notes",
    "constants",
    "formulas",
    "blanks",
    "current_region",
    "current_array",
    "precedents",
    "dependents",
    "last_cell",
    "visible",
    "conditional_formats",
    "data_validation",
    "row_differences",
    "column_differences",
)
VALUE_TYPES = ("numbers", "text", "logicals", "errors")


def _value_type(cell: Any) -> str | None:
    if cell.error is not None:
        return "errors"
    value = cell.display_value
    if isinstance(value, bool):
        return "logicals"
    if isinstance(value, (int, float)):
        return "numbers"
    if isinstance(value, str):
        return "text" if value != "" else None
    if value is not None:
        return "numbers"
    return None


def _scope(sheet: Sheet, selection: list[SelectionRange]) -> list[SelectionRange]:
    """Go To Special searches the selection, or the used range for one cell."""
    if len(selection) == 1 and selection[0][0] == selection[0][2] and selection[0][1] == selection[0][3]:
        max_row, max_column = sheet.extent
        if max_row < 0:
            return []
        return [(0, 0, max_row, max_column)]
    max_row, max_column = sheet.extent
    clipped = []
    for top, left, bottom, right in selection:
        bottom = min(bottom, max(max_row, top))
        right = min(right, max(max_column, left))
        clipped.append((top, left, bottom, right))
    return clipped


def _inside(row: int, column: int, ranges: list[SelectionRange]) -> bool:
    return any(t <= row <= b and l <= column <= r for t, l, b, r in ranges)


def goto_special(
    sheet: Sheet,
    workbook: Any,
    selection: list[SelectionRange],
    active: tuple[int, int],
    kind: str,
    *,
    value_types: tuple[str, ...] = VALUE_TYPES,
) -> list[tuple[int, int]]:
    """Return the cells Go To Special selects, as (row, column) pairs."""
    if kind not in GOTO_KINDS:
        raise ValueError(f"Unknown Go To Special option: {kind!r}")
    if kind == "last_cell":
        return [last_cell(sheet)]
    if kind == "current_region":
        top, left, bottom, right = current_region(sheet, *active)
        return [(row, column) for row in range(top, bottom + 1) for column in range(left, right + 1)]
    if kind == "current_array":
        cell = sheet.get_cell(*active)
        anchor = cell.spill_parent or (active if cell.is_formula else None)
        if anchor is None:
            return []
        cells = [anchor] + [
            coordinate
            for coordinate, item in sheet.iter_unordered()
            if item.spill_parent == anchor
        ]
        return sorted(cells)
    scope = _scope(sheet, selection)
    if kind == "notes":
        return sorted(coordinate for coordinate in sheet.notes if _inside(*coordinate, scope))
    if kind == "blanks":
        filled = {coordinate for coordinate, cell in sheet.iter_unordered() if cell.display_value not in (None, "")}
        return [
            (row, column)
            for top, left, bottom, right in scope
            for row in range(top, bottom + 1)
            for column in range(left, right + 1)
            if (row, column) not in filled
        ][:1_000_000]
    if kind == "visible":
        return [
            (row, column)
            for top, left, bottom, right in scope
            for row in range(top, bottom + 1)
            if row not in sheet.hidden_rows
            for column in range(left, right + 1)
            if column not in sheet.hidden_columns
        ][:1_000_000]
    if kind == "conditional_formats":
        return _covered_cells(sheet, [rule.range for rule in sheet.conditional_formats], scope)
    if kind == "data_validation":
        return _covered_cells(sheet, [rule.range for rule in sheet.data_validations], scope)
    if kind in ("precedents", "dependents"):
        from duddysheet.core.auditing import dependents, precedents

        function = precedents if kind == "precedents" else dependents
        found = function(workbook, sheet.name, *active)
        return sorted((row, column) for name, row, column in found if name.casefold() == sheet.name.casefold())
    if kind in ("row_differences", "column_differences"):
        return _differences(sheet, scope, active, by_row=kind == "row_differences")
    selected: list[tuple[int, int]] = []
    for coordinate, cell in sheet.iter_populated():
        if not _inside(*coordinate, scope) or cell.is_spill:
            continue
        if kind == "formulas" and not cell.is_formula:
            continue
        if kind == "constants" and (cell.is_formula or cell.raw_input in (None, "")):
            continue
        if _value_type(cell) in value_types:
            selected.append(coordinate)
    return selected


def _covered_cells(sheet: Sheet, ranges: list[Any], scope: list[SelectionRange]) -> list[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for reference in ranges:
        if isinstance(reference, CellReference):
            reference = RangeReference(reference, reference)
        for row in range(reference.min_row, min(reference.max_row, sheet.extent[0] + 1) + 1):
            for column in range(reference.min_column, min(reference.max_column, sheet.extent[1] + 1) + 1):
                cells.add((row, column))
    return sorted(cells)


def _differences(
    sheet: Sheet,
    scope: list[SelectionRange],
    active: tuple[int, int],
    *,
    by_row: bool,
) -> list[tuple[int, int]]:
    """Cells whose content differs from the comparison cell in their row/column."""
    found: list[tuple[int, int]] = []
    for top, left, bottom, right in scope:
        for outer in range(top, bottom + 1) if by_row else range(left, right + 1):
            if by_row:
                anchor = sheet.get_cell(outer, active[1])
                cells = [(outer, column) for column in range(left, right + 1)]
            else:
                anchor = sheet.get_cell(active[0], outer)
                cells = [(row, outer) for row in range(top, bottom + 1)]
            for coordinate in cells:
                cell = sheet.get_cell(*coordinate)
                if cell.is_formula or anchor.is_formula:
                    different = _relative_formula(cell, coordinate) != _relative_formula(
                        anchor,
                        (outer, active[1]) if by_row else (active[0], outer),
                    )
                else:
                    different = cell.display_value != anchor.display_value
                if different:
                    found.append(coordinate)
    return found


def _relative_formula(cell: Any, coordinate: tuple[int, int]) -> Any:
    """A formula in R1C1 form, so copies of the same formula compare equal."""
    if not cell.is_formula:
        return ("value", cell.display_value)
    try:
        references = collect_references(parse_formula(cell.raw_input))
    except ValueError:
        return ("text", cell.raw_input)
    row, column = coordinate
    relative = []
    for reference in references:
        if isinstance(reference, CellReference):
            relative.append(reference.to_r1c1(origin=(row, column)))
        elif isinstance(reference, RangeReference):
            relative.append(
                reference.start.to_r1c1(origin=(row, column))
                + ":"
                + reference.end.to_r1c1(origin=(row, column))
            )
        else:
            relative.append(str(reference))
    skeleton = cell.raw_input
    return ("formula", tuple(relative), len(skeleton))


def cells_to_ranges(cells: list[tuple[int, int]]) -> list[SelectionRange]:
    """Merge selected cells into vertical runs so selections stay compact."""
    by_column: dict[int, list[int]] = {}
    for row, column in cells:
        by_column.setdefault(column, []).append(row)
    ranges: list[SelectionRange] = []
    for column, rows in sorted(by_column.items()):
        rows.sort()
        start = previous = rows[0]
        for row in rows[1:]:
            if row == previous + 1:
                previous = row
                continue
            ranges.append((start, column, previous, column))
            start = previous = row
        ranges.append((start, column, previous, column))
    return ranges
