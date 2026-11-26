"""Outline groups (Data > Group) as Excel's outline bar shows them."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OutlineGroup:
    """A run of rows (or columns) at ``level`` or deeper.

    Excel puts a group's summary row just below it (or its summary column
    just to the right), which is where the bar draws the +/- button.
    """

    level: int
    start: int
    end: int

    @property
    def indexes(self) -> tuple[int, ...]:
        """Return every row or column in the group."""
        return tuple(range(self.start, self.end + 1))

    @property
    def summary(self) -> int:
        """Return the summary row or column that carries the button."""
        return self.end + 1


def max_level(levels: dict[int, int]) -> int:
    """Return the deepest outline level in use (0 when there is no outline)."""
    return max(levels.values(), default=0)


def outline_groups(levels: dict[int, int]) -> list[OutlineGroup]:
    """Return every group at every level, outermost first."""
    groups: list[OutlineGroup] = []
    for level in range(1, max_level(levels) + 1):
        members = sorted(index for index, depth in levels.items() if depth >= level)
        start = previous = None
        for index in members:
            if start is None:
                start = previous = index
            elif index == previous + 1:
                previous = index
            else:
                groups.append(OutlineGroup(level, start, previous))
                start = previous = index
        if start is not None:
            groups.append(OutlineGroup(level, start, previous))
    return groups


def is_collapsed(group: OutlineGroup, hidden: set[int]) -> bool:
    """Whether every row (or column) of a group is hidden."""
    return all(index in hidden for index in group.indexes)
