from __future__ import annotations

import pytest

from duddysheet.core.depgraph import (
    CellAddress,
    CircularReferenceError,
    DependencyGraph,
)


def address(column: int, row: int = 0, sheet: str = "Sheet1") -> CellAddress:
    return CellAddress(sheet, row, column)


def test_set_precedents_builds_bidirectional_edges() -> None:
    graph = DependencyGraph()
    formula = address(2)
    first = address(0)
    second = address(1)

    graph.set_precedents(formula, {first, second})

    assert graph.precedents_of(formula) == frozenset({first, second})
    assert graph.dependents_of(first) == frozenset({formula})
    assert graph.dependents_of(second) == frozenset({formula})


def test_replacing_precedents_removes_stale_reverse_edges() -> None:
    graph = DependencyGraph()
    formula = address(2)
    old = address(0)
    new = address(1)
    graph.set_precedents(formula, {old})

    graph.set_precedents(formula, {new})

    assert graph.dependents_of(old) == frozenset()
    assert graph.dependents_of(new) == frozenset({formula})


def test_affected_by_walks_transitive_dependents() -> None:
    graph = DependencyGraph()
    graph.set_precedents(address(1), {address(0)})
    graph.set_precedents(address(2), {address(1)})
    graph.set_precedents(address(3), {address(0)})

    assert graph.affected_by({address(0)}) == frozenset(
        {address(0), address(1), address(2), address(3)}
    )


def test_topological_order_places_precedents_first() -> None:
    graph = DependencyGraph()
    graph.set_precedents(address(1), {address(0)})
    graph.set_precedents(address(2), {address(1)})
    graph.set_precedents(address(3), {address(0)})

    order = graph.topological_order(
        {address(0), address(1), address(2), address(3)}
    )

    assert order.index(address(0)) < order.index(address(1))
    assert order.index(address(1)) < order.index(address(2))
    assert order.index(address(0)) < order.index(address(3))


def test_cycle_detection_names_the_cycle_without_recursing() -> None:
    graph = DependencyGraph()
    graph.set_precedents(address(0), {address(2)})
    graph.set_precedents(address(1), {address(0)})
    graph.set_precedents(address(2), {address(1)})

    with pytest.raises(CircularReferenceError) as error:
        graph.topological_order({address(0), address(1), address(2)})

    assert set(error.value.cycle) == {address(0), address(1), address(2)}
    assert "Sheet1!" in str(error.value)


def test_self_reference_is_a_cycle() -> None:
    graph = DependencyGraph()
    graph.set_precedents(address(0), {address(0)})

    assert graph.find_cycle({address(0)}) == (address(0),)


def test_removing_a_cell_cleans_incoming_and_outgoing_edges() -> None:
    graph = DependencyGraph()
    graph.set_precedents(address(1), {address(0)})
    graph.set_precedents(address(2), {address(1)})

    graph.remove(address(1))

    assert graph.precedents_of(address(1)) == frozenset()
    assert graph.dependents_of(address(0)) == frozenset()
    assert graph.precedents_of(address(2)) == frozenset()


def test_empty_graph_operations_are_stable() -> None:
    graph = DependencyGraph()

    assert graph.affected_by(set()) == frozenset()
    assert graph.topological_order(set()) == ()
    assert graph.find_cycle(set()) == ()
