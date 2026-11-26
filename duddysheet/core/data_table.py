"""What-If Analysis data tables: Excel's {=TABLE(row_input, column_input)}.

A data table is a rectangle whose first row and/or first column holds input
values and whose corner (two-variable) or edge (one-variable) holds the
formula(s) to evaluate. Each interior cell shows the result of the formula
with the input cell temporarily replaced by that row's or column's value.

Results are computed without copying the workbook: a ``WhatIfEvaluator``
substitutes the input value and re-evaluates only the formulas that depend
on the input cell, reading everything else from the cached values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from duddysheet.core.depgraph import CellAddress
from duddysheet.core.errors import CIRC_ERROR, REF_ERROR
from duddysheet.core.evaluator import FormulaEvaluator, _cell_value
from duddysheet.core.refs import CellReference, RangeReference


@dataclass(frozen=True, slots=True)
class DataTableSpec:
    """A data table's rectangle (including its input row/column) and input cells."""

    top: int
    left: int
    bottom: int
    right: int
    row_input: tuple[str, int, int] | None = None
    column_input: tuple[str, int, int] | None = None

    @property
    def interior(self) -> tuple[int, int, int, int]:
        return self.top + 1, self.left + 1, self.bottom, self.right

    def contains_interior(self, row: int, column: int) -> bool:
        top, left, bottom, right = self.interior
        return top <= row <= bottom and left <= column <= right

    @property
    def kind(self) -> str:
        if self.row_input and self.column_input:
            return "two"
        return "row" if self.row_input else "column"


def table_formula(spec: DataTableSpec, sheet_name: str) -> str:
    """Return the ``=TABLE(...)`` text Excel shows in a data table's interior."""

    def text(address: tuple[str, int, int] | None) -> str:
        if address is None:
            return ""
        sheet, row, column = address
        reference = CellReference(row, column, row_absolute=False, column_absolute=False)
        rendered = reference.to_a1(include_sheet=False)
        if sheet.casefold() != sheet_name.casefold():
            from duddysheet.core.refs import quote_sheet_name

            rendered = f"{quote_sheet_name(sheet)}!{rendered}"
        return rendered

    return f"=TABLE({text(spec.row_input)},{text(spec.column_input)})"


def data_table_at(sheet: Any, row: int, column: int) -> DataTableSpec | None:
    for spec in sheet.data_tables:
        if spec.contains_interior(row, column):
            return spec
    return None


def dependency_ranges(spec: DataTableSpec, sheet_name: str) -> list[RangeReference]:
    """Cells a data table's results depend on: its input row, column, and formulas."""
    ranges = [
        RangeReference(
            CellReference(spec.top, spec.left, sheet=sheet_name),
            CellReference(spec.top, spec.right, sheet=sheet_name),
        ),
        RangeReference(
            CellReference(spec.top, spec.left, sheet=sheet_name),
            CellReference(spec.bottom, spec.left, sheet=sheet_name),
        ),
    ]
    return ranges


class WhatIfEvaluator(FormulaEvaluator):
    """Evaluate formulas as if some cells held other values."""

    def __init__(self, engine: Any, overrides: dict[CellAddress, Any]) -> None:
        super().__init__(engine.workbook)
        self.engine = engine
        self.overrides = overrides
        self.affected = engine._affected_formulas(set(overrides)) - set(overrides)
        self.memo: dict[CellAddress, Any] = {}
        self.active: set[CellAddress] = set()

    def _address(self, reference: CellReference, context: Any) -> CellAddress | None:
        try:
            sheet = self.workbook.get_sheet(reference.sheet or context.sheet_name)
        except KeyError:
            return None
        return CellAddress(sheet.name, reference.row, reference.column)

    def value_at(self, address: CellAddress) -> Any:
        """Return a cell's value under the overrides."""
        if address in self.overrides:
            return self.overrides[address]
        if address in self.affected and address in self.engine._asts:
            if address in self.memo:
                return self.memo[address]
            if address in self.active:
                return CIRC_ERROR
            ast = self.engine._asts[address]
            from duddysheet.core.parser import FunctionNode

            if isinstance(ast, FunctionNode) and ast.name == "TABLE":
                cell = self.workbook.get_sheet(address.sheet).get_cell(address.row, address.column)
                return _cell_value(cell)
            self.active.add(address)
            try:
                value = self.evaluate(ast, sheet_name=address.sheet, origin=(address.row, address.column))
            finally:
                self.active.discard(address)
            if isinstance(value, tuple):
                rows = value if value and isinstance(value[0], tuple) else (value,)
                value = rows[0][0] if rows and rows[0] else None
            self.memo[address] = value
            return value
        cell = self.workbook.get_sheet(address.sheet).get_cell(address.row, address.column)
        if cell.spill_parent is not None:
            parent = CellAddress(address.sheet, *cell.spill_parent)
            if parent in self.affected:
                # A spilled child of a re-evaluated array: recompute the array.
                value = self._spill_child(parent, address)
                if value is not None:
                    return value
        return _cell_value(cell)

    def _spill_child(self, parent: CellAddress, address: CellAddress) -> Any:
        ast = self.engine._asts.get(parent)
        if ast is None:
            return None
        value = self.evaluate(ast, sheet_name=parent.sheet, origin=(parent.row, parent.column))
        if not isinstance(value, tuple):
            return None
        rows = value if value and isinstance(value[0], tuple) else (value,)
        row_offset, column_offset = address.row - parent.row, address.column - parent.column
        if 0 <= row_offset < len(rows) and 0 <= column_offset < len(rows[0]):
            return rows[row_offset][column_offset]
        return None

    def _read_cell(self, reference: CellReference, context: Any) -> Any:
        address = self._address(reference, context)
        if address is None:
            return REF_ERROR
        return self.value_at(address)

    def _area_block(self, area: RangeReference, context: Any) -> list[list[Any]]:
        block = super()._area_block(area, context)
        try:
            sheet = self.workbook.get_sheet(area.sheet or context.sheet_name)
        except KeyError:
            return block
        min_row, max_row, min_column, max_column = self._clipped_bounds(area)
        for address in list(self.overrides) + list(self.affected):
            if address.sheet.casefold() != sheet.name.casefold():
                continue
            if min_row <= address.row <= max_row and min_column <= address.column <= max_column:
                block[address.row - min_row][address.column - min_column] = self.value_at(address)
        return block


def evaluate_with(engine: Any, formula_address: CellAddress, overrides: dict[CellAddress, Any]) -> Any:
    """Return a formula cell's value with some inputs replaced."""
    evaluator = WhatIfEvaluator(engine, overrides)
    if formula_address in overrides:
        return overrides[formula_address]
    ast = engine._asts.get(formula_address)
    if ast is None:
        cell = engine.workbook.get_sheet(formula_address.sheet).get_cell(formula_address.row, formula_address.column)
        return _cell_value(cell)
    value = evaluator.evaluate(ast, sheet_name=formula_address.sheet, origin=(formula_address.row, formula_address.column))
    if isinstance(value, tuple):
        rows = value if value and isinstance(value[0], tuple) else (value,)
        value = rows[0][0] if rows and rows[0] else None
    return value


def compute_data_table(engine: Any, sheet_name: str, spec: DataTableSpec) -> dict[tuple[int, int], Any]:
    """Return every interior cell's value for a data table."""
    workbook = engine.workbook
    sheet = workbook.get_sheet(sheet_name)

    def address(item: tuple[str, int, int]) -> CellAddress:
        return CellAddress(workbook.get_sheet(item[0]).name, item[1], item[2])

    top, left, bottom, right = spec.interior
    results: dict[tuple[int, int], Any] = {}
    for row in range(top, bottom + 1):
        for column in range(left, right + 1):
            overrides: dict[CellAddress, Any] = {}
            if spec.kind == "two":
                formula = CellAddress(sheet.name, spec.top, spec.left)
                overrides[address(spec.row_input)] = sheet.get_cell(spec.top, column).display_value
                overrides[address(spec.column_input)] = sheet.get_cell(row, spec.left).display_value
            elif spec.kind == "column":
                formula = CellAddress(sheet.name, spec.top, column)
                overrides[address(spec.column_input)] = sheet.get_cell(row, spec.left).display_value
            else:
                formula = CellAddress(sheet.name, row, spec.left)
                overrides[address(spec.row_input)] = sheet.get_cell(spec.top, column).display_value
            try:
                value = evaluate_with(engine, formula, overrides)
            except RecursionError:
                value = CIRC_ERROR
            results[(row, column)] = value
    return results


def table_value(engine: Any, sheet_name: str, row: int, column: int) -> Any:
    """TABLE()'s result at one interior cell (computed once per recalculation)."""
    sheet = engine.workbook.get_sheet(sheet_name)
    spec = data_table_at(sheet, row, column)
    if spec is None:
        return REF_ERROR
    key = (sheet.name.casefold(), spec.top, spec.left, spec.bottom, spec.right)
    generation = getattr(engine, "calc_generation", 0)
    cache = getattr(engine, "_data_table_cache", None)
    if cache is None or cache[0] != generation:
        cache = (generation, {})
        engine._data_table_cache = cache
    results = cache[1].get(key)
    if results is None:
        results = compute_data_table(engine, sheet.name, spec)
        cache[1][key] = results
    value = results.get((row, column))
    return 0 if value is None else value


def data_table_to_dict(spec: DataTableSpec) -> dict[str, Any]:
    return {
        "top": spec.top,
        "left": spec.left,
        "bottom": spec.bottom,
        "right": spec.right,
        "row_input": list(spec.row_input) if spec.row_input else None,
        "column_input": list(spec.column_input) if spec.column_input else None,
    }


def data_table_from_dict(data: dict[str, Any]) -> DataTableSpec:
    return DataTableSpec(
        int(data["top"]),
        int(data["left"]),
        int(data["bottom"]),
        int(data["right"]),
        tuple(data["row_input"]) if data.get("row_input") else None,
        tuple(data["column_input"]) if data.get("column_input") else None,
    )

