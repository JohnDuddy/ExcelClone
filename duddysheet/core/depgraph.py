"""Bidirectional dependency graph and iterative cycle detection."""

from __future__ import annotations

from collections import deque
from typing import NamedTuple

from duddysheet.core.refs import CellReference


class CellAddress(NamedTuple):
    """Workbook-qualified cell identity used by recalculation.

    A named tuple, so hashing and ordering run at C speed in graph walks.
    """

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
        """Return one deterministic cycle among ``cells``, or ``()`` when acyclic."""
        components = self.cyclic_components(cells)
        if not components:
            return ()
        component = components[0]
        members = set(component)
        start = component[0]
        # Walk precedents inside the component until a cell repeats.
        path: list[CellAddress] = []
        indexes: dict[CellAddress, int] = {}
        current = start
        while current not in indexes:
            indexes[current] = len(path)
            path.append(current)
            current = min(self._precedents.get(current, set()) & members)
        return tuple(path[indexes[current] :])

    def cyclic_components(
        self,
        cells: set[CellAddress] | frozenset[CellAddress],
    ) -> list[tuple[CellAddress, ...]]:
        """Return every strongly connected component that forms a cycle.

        Uses an iterative Tarjan walk over precedent edges restricted to
        ``cells``, so each cycle is found regardless of edge order.
        """
        selected = cells if isinstance(cells, (set, frozenset)) else set(cells)
        precedents = self._precedents
        index_of: dict[CellAddress, int] = {}
        low: dict[CellAddress, int] = {}
        on_stack: set[CellAddress] = set()
        stack: list[CellAddress] = []
        components: list[tuple[CellAddress, ...]] = []
        counter = 0
        for root in sorted(selected):
            if root in index_of:
                continue
            work: list[tuple[CellAddress, list[CellAddress], int]] = []
            index_of[root] = low[root] = counter
            counter += 1
            stack.append(root)
            on_stack.add(root)
            work.append((root, sorted(precedents.get(root, ()) & selected) if root in precedents else [], 0))
            while work:
                node, edges, position = work[-1]
                if position < len(edges):
                    work[-1] = (node, edges, position + 1)
                    child = edges[position]
                    if child not in index_of:
                        index_of[child] = low[child] = counter
                        counter += 1
                        stack.append(child)
                        on_stack.add(child)
                        child_edges = (
                            sorted(precedents[child] & selected) if child in precedents else []
                        )
                        work.append((child, child_edges, 0))
                    elif child in on_stack:
                        low[node] = min(low[node], index_of[child])
                    continue
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index_of[node]:
                    component: list[CellAddress] = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member == node:
                            break
                    if len(component) > 1 or node in precedents.get(node, ()):
                        components.append(tuple(sorted(component)))
        components.sort()
        return components

    def recalculation_plan(
        self,
        cells: set[CellAddress] | frozenset[CellAddress],
    ) -> tuple[tuple[CellAddress, ...], tuple[CellAddress, ...]]:
        """Return (evaluation order, circular cells) for a set of formulas.

        Circular cells are every member of a cycle; the order covers the rest
        with in-scope precedents first.
        """
        selected = set(cells)
        if not selected:
            return (), ()
        ordered = self._kahn(selected)
        if len(ordered) == len(selected):
            return tuple(ordered), ()
        # Only cells Kahn could not order can sit on, or below, a cycle.
        leftover = selected.difference(ordered)
        circular: set[CellAddress] = set()
        for component in self.cyclic_components(leftover):
            circular.update(component)
        downstream = leftover - circular
        ordered.extend(self._kahn(downstream))
        return tuple(ordered), tuple(sorted(circular))

    def _kahn(self, selected: set[CellAddress]) -> list[CellAddress]:
        """Topologically order ``selected``; cells on cycles are omitted."""
        precedents = self._precedents
        dependents = self._dependents
        indegree: dict[CellAddress, int] = {}
        for cell in selected:
            incoming = precedents.get(cell)
            if not incoming:
                indegree[cell] = 0
            elif len(incoming) == 1:
                indegree[cell] = 1 if next(iter(incoming)) in selected else 0
            else:
                indegree[cell] = len(incoming & selected)
        ready = deque(sorted(cell for cell, degree in indegree.items() if degree == 0))
        ordered: list[CellAddress] = []
        append = ordered.append
        while ready:
            current = ready.popleft()
            append(current)
            outgoing = dependents.get(current)
            if not outgoing:
                continue
            for dependent in sorted(outgoing) if len(outgoing) > 1 else outgoing:
                degree = indegree.get(dependent)
                if degree is not None:
                    degree -= 1
                    indegree[dependent] = degree
                    if degree == 0:
                        ready.append(dependent)
        return ordered

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

