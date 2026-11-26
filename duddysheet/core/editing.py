"""Headless Excel editing operations: move, shift-insert/delete, clear, AutoSum.

These functions mutate a ``Workbook`` directly and are wrapped by undoable
commands. Reference rewriting follows Excel: moving cells (cut and paste)
re-points every formula that referred to them, and inserting or deleting
cells with a shift moves references within the shifted band.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from duddysheet.core.cell import Cell, CellFormat
from duddysheet.core.errors import REF_ERROR
from duddysheet.core.parser import ErrorNode, Node, parse_formula
from duddysheet.core.refs import MAX_COLUMNS, MAX_ROWS, CellReference, RangeReference, Reference
from duddysheet.core.translation import _map_references, formula_to_text
from duddysheet.core.workbook import Workbook

Rect = tuple[int, int, int, int]  # top, left, bottom, right (inclusive)

CLEAR_KINDS = ("all", "contents", "formats", "notes", "hyperlinks")


def _rewrite_workbook_formulas(
    workbook: Workbook,
    mapper_for: Callable[[str], Callable[[Reference], Reference | Node]],
) -> None:
    """Rewrite references in every formula; ``mapper_for(sheet)`` builds the mapper."""
    for sheet in workbook:
        mapper = mapper_for(sheet.name)
        for (row, column), cell in tuple(sheet.iter_populated()):
            if not cell.is_formula:
                continue
            try:
                ast = parse_formula(cell.raw_input)
            except ValueError:
                continue
            rewritten = formula_to_text(_map_references(ast, mapper))
            if rewritten != cell.raw_input:
                sheet.put_cell(row, column, replace(cell, raw_input=rewritten, cached_value=None))


def _endpoint_mapper(
    formula_sheet: str,
    target_sheet: str,
    move: Callable[[int, int], tuple[int, int] | None],
) -> Callable[[Reference], Reference | Node]:
    """Map each reference endpoint on ``target_sheet`` through ``move``."""

    def mapped_cell(reference: CellReference) -> CellReference | None:
        position = move(reference.row, reference.column)
        if position is None:
            return None
        if position == (reference.row, reference.column):
            return reference
        return replace(reference, row=position[0], column=position[1])

    def adjust(reference: Reference) -> Reference | Node:
        sheet = reference.sheet or formula_sheet
        if sheet.casefold() != target_sheet.casefold():
            return reference
        if isinstance(reference, CellReference):
            moved = mapped_cell(reference)
            return ErrorNode(REF_ERROR) if moved is None else moved
        if reference.whole_row or reference.whole_column:
            return reference
        start = mapped_cell(reference.start)
        end = mapped_cell(reference.end)
        if start is None or end is None:
            return ErrorNode(REF_ERROR)
        if start == reference.start and end == reference.end:
            return reference
        return RangeReference(start, end)

    return adjust


# ------------------------------------------------------------------ moving
def move_cells(
    workbook: Workbook,
    source_sheet: str,
    source: Rect,
    target_sheet: str,
    target_row: int,
    target_column: int,
) -> None:
    """Cut ``source`` and paste it with its top-left at the target cell.

    Formulas anywhere that referred to moved cells follow them; references to
    cells overwritten by the paste become #REF!, as in Excel.
    """
    top, left, bottom, right = source
    height, width = bottom - top + 1, right - left + 1
    if target_row + height > MAX_ROWS or target_column + width > MAX_COLUMNS:
        raise IndexError("The paste area extends beyond the worksheet")
    from_sheet = workbook.get_sheet(source_sheet)
    to_sheet = workbook.get_sheet(target_sheet)
    d_row, d_column = target_row - top, target_column - left
    same_sheet = from_sheet is to_sheet
    if same_sheet and d_row == 0 and d_column == 0:
        return

    def inside_source(row: int, column: int) -> bool:
        return top <= row <= bottom and left <= column <= right

    def inside_target(row: int, column: int) -> bool:
        return (
            target_row <= row < target_row + height
            and target_column <= column < target_column + width
        )

    moving = {
        (row, column): cell
        for (row, column), cell in from_sheet.iter_populated()
        if inside_source(row, column) and not cell.is_spill
    }
    moving_notes = {
        coordinate: note
        for coordinate, note in from_sheet.notes.items()
        if inside_source(*coordinate)
    }

    # Re-point references before cells move, so ASTs see the old layout.
    def mapper_for(formula_sheet: str) -> Callable[[Reference], Reference | Node]:
        def endpoint(reference: CellReference) -> CellReference | None | bool:
            """New endpoint, ``None`` for #REF!, or ``False`` when unchanged."""
            sheet = (reference.sheet or formula_sheet).casefold()
            if sheet == from_sheet.name.casefold() and inside_source(reference.row, reference.column):
                moved = replace(
                    reference,
                    row=reference.row + d_row,
                    column=reference.column + d_column,
                )
                if not same_sheet:
                    moved = replace(
                        moved,
                        sheet=None if to_sheet.name.casefold() == formula_sheet.casefold() else to_sheet.name,
                    )
                return moved
            if sheet == to_sheet.name.casefold() and inside_target(reference.row, reference.column):
                return None
            return False

        def adjust(reference: Reference) -> Reference | Node:
            if isinstance(reference, CellReference):
                result = endpoint(reference)
                if result is None:
                    return ErrorNode(REF_ERROR)
                return reference if result is False else result
            if reference.whole_row or reference.whole_column:
                return reference
            start_result = endpoint(reference.start)
            end_result = endpoint(reference.end)
            if start_result is False and end_result is False:
                return reference
            if start_result is None or end_result is None:
                return ErrorNode(REF_ERROR)
            new_start = reference.start if start_result is False else start_result
            new_end = reference.end if end_result is False else end_result
            if new_start.sheet != new_end.sheet:
                return reference
            return RangeReference(new_start, new_end)

        return adjust

    _rewrite_workbook_formulas(workbook, mapper_for)
    rewritten = {
        coordinate: from_sheet.get_cell(*coordinate)
        for coordinate in moving
    }
    for coordinate in moving:
        from_sheet.clear_cell(*coordinate)
    for coordinate in moving_notes:
        from_sheet.notes.pop(coordinate, None)
    for row in range(target_row, target_row + height):
        for column in range(target_column, target_column + width):
            to_sheet.clear_cell(row, column)
            to_sheet.notes.pop((row, column), None)
    for (row, column), cell in rewritten.items():
        to_sheet.put_cell(row + d_row, column + d_column, replace(cell, spill_parent=None))
    for (row, column), note in moving_notes.items():
        to_sheet.notes[(row + d_row, column + d_column)] = note


# ------------------------------------------------------- insert/delete cells
def shift_cells(
    workbook: Workbook,
    sheet_name: str,
    area: Rect,
    *,
    direction: str,
) -> None:
    """Insert (``down``/``right``) or delete (``up``/``left``) cells, shifting the rest."""
    if direction not in ("down", "right", "up", "left"):
        raise ValueError(f"Unknown shift direction: {direction!r}")
    sheet = workbook.get_sheet(sheet_name)
    top, left, bottom, right = area
    height, width = bottom - top + 1, right - left + 1
    vertical = direction in ("down", "up")
    inserting = direction in ("down", "right")

    def move(row: int, column: int) -> tuple[int, int] | None:
        if vertical:
            if not left <= column <= right or row < top:
                return row, column
            if inserting:
                moved = row + height
                return (moved, column) if moved < MAX_ROWS else None
            if row <= bottom:
                return None
            return row - height, column
        if not top <= row <= bottom or column < left:
            return row, column
        if inserting:
            moved = column + width
            return (row, moved) if moved < MAX_COLUMNS else None
        if column <= right:
            return None
        return row, column - width

    def range_move(reference: RangeReference) -> Reference | Node:
        # Deleting part of a range shrinks it, like Excel, when the range runs
        # along the shift axis and covers the band's width.
        if inserting or reference.whole_row or reference.whole_column:
            return _range_endpoints(reference, move)
        if vertical:
            covers_band = left <= reference.min_column and reference.max_column <= right
            if not covers_band:
                return reference
            low, high = reference.min_row, reference.max_row
            if high < top:
                return reference
            if low > bottom:
                return _shifted_range(reference, -height, 0)
            new_low = low if low < top else top
            new_high = high - height if high > bottom else top - 1
            if new_high < new_low:
                return ErrorNode(REF_ERROR)
            return _rebuilt_range(reference, new_low, reference.min_column, new_high, reference.max_column)
        covers_band = top <= reference.min_row and reference.max_row <= bottom
        if not covers_band:
            return reference
        low, high = reference.min_column, reference.max_column
        if high < left:
            return reference
        if low > right:
            return _shifted_range(reference, 0, -width)
        new_low = low if low < left else left
        new_high = high - width if high > right else left - 1
        if new_high < new_low:
            return ErrorNode(REF_ERROR)
        return _rebuilt_range(reference, reference.min_row, new_low, reference.max_row, new_high)

    def mapper_for(formula_sheet: str) -> Callable[[Reference], Reference | Node]:
        cell_mapper = _endpoint_mapper(formula_sheet, sheet.name, move)

        def adjust(reference: Reference) -> Reference | Node:
            target = reference.sheet or formula_sheet
            if target.casefold() != sheet.name.casefold():
                return reference
            if isinstance(reference, RangeReference):
                return range_move(reference)
            return cell_mapper(reference)

        return adjust

    _rewrite_workbook_formulas(workbook, mapper_for)
    cells = [(coordinate, cell) for coordinate, cell in sheet.iter_populated()]
    notes = dict(sheet.notes)
    for coordinate, cell in cells:
        if move(*coordinate) != coordinate:
            sheet.clear_cell(*coordinate)
    moved_cells = [
        (move(*coordinate), cell)
        for coordinate, cell in cells
        if move(*coordinate) != coordinate
    ]
    for destination, cell in moved_cells:
        if destination is not None:
            sheet.put_cell(destination[0], destination[1], replace(cell, spill_parent=None))
    sheet.notes = {}
    for coordinate, note in notes.items():
        destination = move(*coordinate)
        if destination is not None:
            sheet.notes[destination] = note
    sheet.merged_ranges = [
        merged
        for merged in sheet.merged_ranges
        if not _overlaps(merged, area)
    ]


def _range_endpoints(
    reference: RangeReference,
    move: Callable[[int, int], tuple[int, int] | None],
) -> Reference | Node:
    if reference.whole_row or reference.whole_column:
        return reference
    start = move(reference.start.row, reference.start.column)
    end = move(reference.end.row, reference.end.column)
    if start is None or end is None:
        return ErrorNode(REF_ERROR)
    return RangeReference(
        replace(reference.start, row=start[0], column=start[1]),
        replace(reference.end, row=end[0], column=end[1]),
    )


def _shifted_range(reference: RangeReference, d_row: int, d_column: int) -> RangeReference:
    return RangeReference(
        replace(reference.start, row=reference.start.row + d_row, column=reference.start.column + d_column),
        replace(reference.end, row=reference.end.row + d_row, column=reference.end.column + d_column),
    )


def _rebuilt_range(reference: RangeReference, top: int, left: int, bottom: int, right: int) -> Reference:
    start = replace(reference.start, row=top, column=left)
    end = replace(reference.end, row=bottom, column=right)
    if (top, left) == (bottom, right):
        return start
    return RangeReference(start, end)


def _overlaps(reference: RangeReference, area: Rect) -> bool:
    top, left, bottom, right = area
    return not (
        reference.max_row < top
        or reference.min_row > bottom
        or reference.max_column < left
        or reference.min_column > right
    )


# ------------------------------------------------------------------ clearing
def clear_ranges(
    workbook: Workbook,
    sheet_name: str,
    ranges: list[Rect],
    *,
    kind: str = "contents",
) -> None:
    """Clear contents, formats, notes, hyperlinks, or everything in ranges."""
    if kind not in CLEAR_KINDS:
        raise ValueError(f"Unknown clear kind: {kind!r}")
    sheet = workbook.get_sheet(sheet_name)

    def covered(row: int, column: int) -> bool:
        return any(
            top <= row <= bottom and left <= column <= right
            for top, left, bottom, right in ranges
        )

    for (row, column), cell in tuple(sheet.iter_populated()):
        if not covered(row, column) or cell.is_spill:
            continue
        if kind == "all":
            sheet.clear_cell(row, column)
        elif kind == "contents":
            sheet.put_cell(
                row,
                column,
                Cell(format=cell.format, hyperlink=cell.hyperlink),
            )
        elif kind == "formats":
            sheet.put_cell(row, column, replace(cell, format=CellFormat()))
        elif kind == "hyperlinks":
            sheet.put_cell(row, column, replace(cell, hyperlink=None))
    if kind in ("all", "notes"):
        for coordinate in [coordinate for coordinate in sheet.notes if covered(*coordinate)]:
            del sheet.notes[coordinate]
    if kind in ("all", "formats"):
        sheet.merged_ranges = [
            merged
            for merged in sheet.merged_ranges
            if not any(_overlaps(merged, rect) for rect in ranges)
        ]
    if kind in ("all", "contents"):
        _drop_cleared_reports(sheet, ranges)


def _rects_overlap(first: Rect, second: Rect) -> bool:
    return not (first[2] < second[0] or first[0] > second[2] or first[3] < second[1] or first[1] > second[3])


def _contains(outer: Rect, inner: Rect) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def _drop_cleared_reports(sheet: Any, ranges: list[Rect]) -> None:
    """Clearing all of a PivotTable or a data table's results removes it, as in Excel."""
    sheet.data_tables = [
        spec for spec in sheet.data_tables if not any(_contains(rect, spec.interior) for rect in ranges)
    ]
    sheet.pivots = [
        pivot
        for pivot in sheet.pivots
        if pivot.extent is None or not any(_contains(rect, pivot.extent) for rect in ranges)
    ]


def blocked_by_report(sheet: Any, ranges: list[Rect]) -> str | None:
    """Explain why an edit would change only part of a PivotTable or data table."""
    for pivot in sheet.pivots:
        if pivot.extent is not None and any(
            _rects_overlap(pivot.extent, rect) and not _contains(rect, pivot.extent) for rect in ranges
        ):
            return "Cannot change this part of a PivotTable report."
    for spec in sheet.data_tables:
        if any(_rects_overlap(spec.interior, rect) and not _contains(rect, spec.interior) for rect in ranges):
            return "Cannot change part of a data table."
    return None


# ------------------------------------------------------------------- AutoSum
def autosum_range(sheet: Any, row: int, column: int) -> Rect | None:
    """Return the range AutoSum proposes for a formula at (row, column).

    Excel looks up for a run of numbers ending just above the cell, and
    otherwise left along the row.
    """

    def numeric(r: int, c: int) -> bool:
        value = sheet.get_cell(r, c).display_value
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def has_value(r: int, c: int) -> bool:
        return sheet.get_cell(r, c).display_value not in (None, "")

    if row > 0 and numeric(row - 1, column):
        start = row - 1
        while start > 0 and numeric(start - 1, column):
            start -= 1
        return start, column, row - 1, column
    if column > 0 and numeric(row, column - 1):
        start = column - 1
        while start > 0 and numeric(row, start - 1):
            start -= 1
        return row, start, row, column - 1
    if row > 0 and has_value(row - 1, column):
        start = row - 1
        while start > 0 and has_value(start - 1, column):
            start -= 1
        return start, column, row - 1, column
    return None


def range_text(area: Rect) -> str:
    """Render a rectangle as an A1 reference without a sheet."""
    top, left, bottom, right = area
    start = CellReference(top, left)
    if (top, left) == (bottom, right):
        return start.to_a1(include_sheet=False)
    return RangeReference(start, CellReference(bottom, right)).to_a1()

