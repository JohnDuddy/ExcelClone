"""Incremental formula parsing, dependency indexing, and recalculation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from excelclone.core.cell import CellFormat
from excelclone.core.depgraph import CellAddress, DependencyGraph
from excelclone.core.errors import CIRC_ERROR, SpreadsheetError
from excelclone.core.evaluator import FormulaEvaluator
from excelclone.core.parser import Node, collect_references, parse_formula
from excelclone.core.refs import CellReference, RangeReference, Reference
from excelclone.core.workbook import Workbook

_RANGE_EDGE_LIMIT = 100_000


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
        ast = (
            parse_formula(raw_input)
            if isinstance(raw_input, str) and raw_input.startswith("=")
            else None
        )

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
            self.graph.set_precedents(address, set())
        else:
            self._asts[address] = ast
            self._install_dependencies(address, ast)

        affected = self._affected_formulas({address})
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
        if isinstance(value, SpreadsheetError):
            sheet.update_cache(
                address.row,
                address.column,
                None,
                error=value.literal,
            )
        else:
            sheet.update_cache(address.row, address.column, value, error=None)
