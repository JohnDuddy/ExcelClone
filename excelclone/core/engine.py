"""Incremental formula parsing, dependency indexing, and recalculation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from excelclone.core.cell import EMPTY_CELL, Cell, CellFormat
from excelclone.core.depgraph import CellAddress, DependencyGraph
from excelclone.core.errors import CIRC_ERROR, SPILL_ERROR, VALUE_ERROR, SpreadsheetError
from excelclone.core.evaluator import FormulaEvaluator
from excelclone.core.functions import FUNCTION_REGISTRY
from excelclone.core.parser import (
    Node,
    collect_function_names,
    collect_references,
    parse_formula,
)
from excelclone.core.refs import MAX_COLUMNS, MAX_ROWS, CellReference, RangeReference, Reference
from excelclone.core.workbook import Workbook

_RANGE_EDGE_LIMIT = 100_000


class SpillCellReadOnlyError(ValueError):
    """Raised when editing a cell owned by a dynamic-array formula."""


@dataclass(frozen=True, slots=True)
class RecalculationResult:
    """Observable outcome of one recalculation pass."""

    recalculated: tuple[CellAddress, ...]
    circular: tuple[CellAddress, ...]

    @property
    def first_circular(self) -> CellAddress | None:
        """Return the first deterministic circular-reference address."""
        return self.circular[0] if self.circular else None


class FormulaEngine:
    """The mutation and recalculation interface for a workbook."""

    def __init__(self, workbook: Workbook) -> None:
        self.workbook = workbook
        self.graph = DependencyGraph()
        self.evaluator = FormulaEvaluator(workbook)
        self._asts: dict[CellAddress, Node] = {}
        self._range_precedents: dict[CellAddress, tuple[RangeReference, ...]] = {}
        self._volatile: set[CellAddress] = set()
        self._spill_cells: dict[CellAddress, set[CellAddress]] = {}
        self._spill_owners: dict[CellAddress, CellAddress] = {}
        self._spill_blockers: dict[CellAddress, set[CellAddress]] = {}
        self._index_existing_formulas()

    def set_cell(
        self,
        sheet_name: str,
        row: int,
        column: int,
        raw_input: Any,
        *,
        cell_format: CellFormat | None = None,
    ) -> RecalculationResult:
        """Set a cell atomically and recalculate only affected formulas."""
        sheet = self.workbook.get_sheet(sheet_name)
        address = CellAddress(sheet.name, row, column)
        if address in self._spill_owners:
            owner = self._spill_owners[address]
            raise SpillCellReadOnlyError(
                f"{address.to_a1()} is owned by spill formula {owner.to_a1()}"
            )
        ast = (
            parse_formula(raw_input)
            if isinstance(raw_input, str) and raw_input.startswith("=")
            else None
        )

        changed = {address}
        changed.update(self._clear_spill(address))
        previous = sheet.get_cell(row, column)
        selected_format = previous.format if cell_format is None else cell_format
        sheet.set_cell(
            row,
            column,
            raw_input,
            cell_format=selected_format,
        )

        if ast is None:
            self._asts.pop(address, None)
            self._range_precedents.pop(address, None)
            self._volatile.discard(address)
            self.graph.set_precedents(address, set())
        else:
            self._asts[address] = ast
            self._install_dependencies(address, ast)

        affected = self._affected_formulas(changed | self._volatile)
        return self._calculate_nodes(affected)

    def recalculate(self, *, sheet_name: str | None = None) -> RecalculationResult:
        """Recalculate every formula, or formulas on one selected sheet."""
        if sheet_name is None:
            selected = set(self._asts)
        else:
            canonical = self.workbook.get_sheet(sheet_name).name.casefold()
            selected = {
                address
                for address in self._asts
                if address.sheet.casefold() == canonical
            }
        return self._calculate_nodes(selected)

    def _index_existing_formulas(self) -> None:
        for sheet in self.workbook:
            for (row, column), cell in sheet.iter_populated():
                if not cell.is_formula:
                    continue
                address = CellAddress(sheet.name, row, column)
                ast = parse_formula(cell.raw_input)
                self._asts[address] = ast
                self._install_dependencies(address, ast)

    def _install_dependencies(self, address: CellAddress, ast: Node) -> None:
        precedents: set[CellAddress] = set()
        ranges: list[RangeReference] = []
        for reference in collect_references(ast):
            resolved = self._resolve_reference(reference, scope=address.sheet)
            if resolved is None:
                continue
            if isinstance(resolved, CellReference):
                precedents.add(self._address_from_reference(resolved, address.sheet))
                continue

            normalized_range = self._normalize_range(resolved, address.sheet)
            ranges.append(normalized_range)
            if len(normalized_range) <= _RANGE_EDGE_LIMIT:
                precedents.update(
                    CellAddress(
                        normalized_range.sheet or address.sheet,
                        cell.row,
                        cell.column,
                    )
                    for cell in normalized_range
                )
            elif normalized_range.contains(address.row, address.column) and (
                normalized_range.sheet or address.sheet
            ).casefold() == address.sheet.casefold():
                precedents.add(address)

        self.graph.set_precedents(address, precedents)
        function_names = collect_function_names(ast)
        if any(
            name in FUNCTION_REGISTRY and FUNCTION_REGISTRY[name].volatile
            for name in function_names
        ):
            self._volatile.add(address)
        else:
            self._volatile.discard(address)
        if ranges:
            self._range_precedents[address] = tuple(ranges)
        else:
            self._range_precedents.pop(address, None)

    def _resolve_reference(
        self,
        reference: Reference | str,
        *,
        scope: str,
    ) -> Reference | None:
        if not isinstance(reference, str):
            return reference
        name_scope = scope
        name = reference
        if "!" in reference:
            name_scope, _, name = reference.partition("!")
        try:
            return self.workbook.get_name(name, scope=name_scope).reference
        except (KeyError, ValueError):
            return None

    def _address_from_reference(
        self,
        reference: CellReference,
        default_sheet: str,
    ) -> CellAddress:
        selected_sheet = reference.sheet or default_sheet
        try:
            selected_sheet = self.workbook.get_sheet(selected_sheet).name
        except KeyError:
            pass
        return CellAddress(selected_sheet, reference.row, reference.column)

    def _normalize_range(
        self,
        reference: RangeReference,
        default_sheet: str,
    ) -> RangeReference:
        selected_sheet = reference.sheet or default_sheet
        try:
            selected_sheet = self.workbook.get_sheet(selected_sheet).name
        except KeyError:
            pass
        return RangeReference(
            replace(reference.start, sheet=selected_sheet),
            replace(reference.end, sheet=selected_sheet),
            whole_row=reference.whole_row,
            whole_column=reference.whole_column,
        )

    def _affected_formulas(self, changed: set[CellAddress]) -> set[CellAddress]:
        affected = set(changed)
        queue = list(sorted(changed))
        while queue:
            current = queue.pop(0)
            candidates = set(self.graph.dependents_of(current))
            candidates.update(self._range_dependents(current))
            candidates.update(
                parent
                for parent, blockers in self._spill_blockers.items()
                if current in blockers
            )
            for dependent in sorted(candidates):
                if dependent not in affected:
                    affected.add(dependent)
                    queue.append(dependent)
        return affected & self._asts.keys()

    def _range_dependents(self, address: CellAddress) -> set[CellAddress]:
        dependents: set[CellAddress] = set()
        for formula, ranges in self._range_precedents.items():
            for reference in ranges:
                sheet_name = reference.sheet or formula.sheet
                if (
                    sheet_name.casefold() == address.sheet.casefold()
                    and reference.contains(address.row, address.column)
                ):
                    dependents.add(formula)
                    break
        return dependents

    def _calculate_nodes(
        self,
        selected: set[CellAddress],
    ) -> RecalculationResult:
        remaining = set(selected) & self._asts.keys()
        circular: list[CellAddress] = []
        while True:
            cycle = self.graph.find_cycle(remaining)
            if not cycle:
                break
            for address in sorted(cycle):
                self._cache_result(address, CIRC_ERROR)
                circular.append(address)
            remaining.difference_update(cycle)

        order = self.graph.topological_order(remaining)
        recalculated: list[CellAddress] = []
        for address in order:
            result = self.evaluator.evaluate(
                self._asts[address],
                sheet_name=address.sheet,
                origin=(address.row, address.column),
            )
            self._cache_result(address, result)
            recalculated.append(address)
        return RecalculationResult(
            tuple(recalculated),
            tuple(sorted(set(circular))),
        )

    def _cache_result(self, address: CellAddress, value: Any) -> None:
        sheet = self.workbook.get_sheet(address.sheet)
        if isinstance(value, tuple):
            self._cache_spill(address, value)
            return
        self._clear_spill(address)
        self._spill_blockers.pop(address, None)
        if isinstance(value, SpreadsheetError):
            sheet.update_cache(
                address.row,
                address.column,
                None,
                error=value.literal,
            )
        else:
            sheet.update_cache(address.row, address.column, value, error=None)

    def _cache_spill(self, address: CellAddress, value: tuple[Any, ...]) -> None:
        sheet = self.workbook.get_sheet(address.sheet)
        rows = (
            [list(row) for row in value]
            if value and all(isinstance(row, tuple) for row in value)
            else [list(value)]
        )
        if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
            self._clear_spill(address)
            sheet.update_cache(
                address.row,
                address.column,
                None,
                error=VALUE_ERROR.literal,
            )
            return

        desired: dict[CellAddress, Any] = {}
        out_of_bounds = False
        for row_offset, row_values in enumerate(rows):
            for column_offset, item in enumerate(row_values):
                row = address.row + row_offset
                column = address.column + column_offset
                if row >= MAX_ROWS or column >= MAX_COLUMNS:
                    out_of_bounds = True
                    continue
                desired[CellAddress(address.sheet, row, column)] = item

        old_children = self._spill_cells.get(address, set())
        blockers: set[CellAddress] = set()
        if out_of_bounds:
            blockers.add(address)
        for target in desired:
            if target == address or target in old_children:
                continue
            cell = sheet.get_cell(target.row, target.column)
            if not cell.is_empty:
                blockers.add(target)

        if blockers:
            self._clear_spill(address)
            self._spill_blockers[address] = blockers
            sheet.update_cache(
                address.row,
                address.column,
                None,
                error=SPILL_ERROR.literal,
            )
            return

        self._clear_spill(address)
        self._spill_blockers.pop(address, None)
        anchor_value = desired[address]
        if isinstance(anchor_value, SpreadsheetError):
            sheet.update_cache(
                address.row,
                address.column,
                None,
                error=anchor_value.literal,
            )
        else:
            sheet.update_cache(address.row, address.column, anchor_value, error=None)

        parent_cell = sheet.get_cell(address.row, address.column)
        children: set[CellAddress] = set()
        for target, item in desired.items():
            if target == address:
                continue
            child = (
                Cell(
                    cached_value=None,
                    format=parent_cell.format,
                    error=item.literal,
                    spill_parent=(address.row, address.column),
                )
                if isinstance(item, SpreadsheetError)
                else Cell(
                    cached_value=item,
                    format=parent_cell.format,
                    spill_parent=(address.row, address.column),
                )
            )
            sheet.put_cell(target.row, target.column, child)
            children.add(target)
            self._spill_owners[target] = address
        if children:
            self._spill_cells[address] = children

    def _clear_spill(self, address: CellAddress) -> set[CellAddress]:
        children = self._spill_cells.pop(address, set())
        if not children:
            return set()
        sheet = self.workbook.get_sheet(address.sheet)
        for child_address in children:
            cell = sheet.get_cell(child_address.row, child_address.column)
            if cell.spill_parent == (address.row, address.column):
                sheet.put_cell(child_address.row, child_address.column, EMPTY_CELL)
            self._spill_owners.pop(child_address, None)
        return children
