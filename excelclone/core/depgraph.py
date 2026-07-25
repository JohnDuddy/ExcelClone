"""Bidirectional dependency graph and iterative cycle detection."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from excelclone.core.refs import CellReference


@dataclass(frozen=True, slots=True, order=True)
class CellAddress:
    """Workbook-qualified cell identity used by recalculation."""

    sheet: str
    row: int
    column: int

    def to_a1(self) -> str:
        """Render this address for diagnostics."""
        return CellReference(self.row, self.column, sheet=self.sheet).to_a1()


class CircularReferenceError(ValueError):
    """A cycle returned by topological sorting."""

    def __init__(self, cycle: tuple[CellAddress, ...]) -> None:
        self.cycle = cycle
        description = " -> ".join(address.to_a1() for address in cycle)
        super().__init__(f"Circular reference: {description}")


class DependencyGraph:
    """Cell precedents and dependents with deterministic graph operations."""

    def __init__(self) -> None:
        self._precedents: dict[CellAddress, set[CellAddress]] = {}
        self._dependents: dict[CellAddress, set[CellAddress]] = {}

    def set_precedents(
        self,
        cell: CellAddress,
        precedents: set[CellAddress] | frozenset[CellAddress],
    ) -> None:
        """Atomically replace a cell's incoming dependency edges."""
        old_precedents = self._precedents.get(cell, set())
        for old in old_precedents - set(precedents):
            dependents = self._dependents.get(old)
            if dependents is not None:
                dependents.discard(cell)
                if not dependents:
                    self._dependents.pop(old, None)

        normalized = set(precedents)
        if normalized:
            self._precedents[cell] = normalized
        else:
            self._precedents.pop(cell, None)
        for precedent in normalized:
            self._dependents.setdefault(precedent, set()).add(cell)

    def precedents_of(self, cell: CellAddress) -> frozenset[CellAddress]:
        """Return direct precedents of a cell."""
        return frozenset(self._precedents.get(cell, ()))

    def dependents_of(self, cell: CellAddress) -> frozenset[CellAddress]:
        """Return direct dependents of a cell."""
        return frozenset(self._dependents.get(cell, ()))

    def affected_by(
        self,
        changed: set[CellAddress] | frozenset[CellAddress],
    ) -> frozenset[CellAddress]:
        """Return changed cells and every transitive dependent."""
        affected = set(changed)
        queue = deque(sorted(changed))
        while queue:
            current = queue.popleft()
            for dependent in sorted(self._dependents.get(current, ())):
                if dependent not in affected:
                    affected.add(dependent)
                    queue.append(dependent)
        return frozenset(affected)

    def topological_order(
        self,
        cells: set[CellAddress] | frozenset[CellAddress],
    ) -> tuple[CellAddress, ...]:
        """Order cells with in-scope precedents before their dependents."""
        selected = set(cells)
        if not selected:
            return ()
        indegree = {
            cell: len(self._precedents.get(cell, set()) & selected)
            for cell in selected
        }
        ready = deque(sorted(cell for cell, degree in indegree.items() if degree == 0))
        ordered: list[CellAddress] = []

        while ready:
            current = ready.popleft()
            ordered.append(current)
            for dependent in sorted(self._dependents.get(current, set()) & selected):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)

        if len(ordered) != len(selected):
            raise CircularReferenceError(self.find_cycle(selected))
        return tuple(ordered)

    def find_cycle(
        self,
        cells: set[CellAddress] | frozenset[CellAddress],
    ) -> tuple[CellAddress, ...]:
        """Return one deterministic cycle using an iterative walk."""
        selected = set(cells)
        visited: set[CellAddress] = set()
        for start in sorted(selected):
            if start in visited:
                continue
            path: list[CellAddress] = []
            indexes: dict[CellAddress, int] = {}
            current = start
            while True:
                if current in indexes:
                    return tuple(path[indexes[current] :])
                if current in visited:
                    break
                indexes[current] = len(path)
                path.append(current)
                candidates = sorted(self._precedents.get(current, set()) & selected)
                if not candidates:
                    break
                current = candidates[0]
            visited.update(path)
        return ()

    def remove(self, cell: CellAddress) -> None:
        """Remove a cell and every edge touching it."""
        for precedent in self._precedents.pop(cell, set()):
            dependents = self._dependents.get(precedent)
            if dependents is not None:
                dependents.discard(cell)
                if not dependents:
                    self._dependents.pop(precedent, None)
        for dependent in self._dependents.pop(cell, set()):
            precedents = self._precedents.get(dependent)
            if precedents is not None:
                precedents.discard(cell)
                if not precedents:
                    self._precedents.pop(dependent, None)

