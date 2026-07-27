"""Command interface and bounded undo/redo history."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable


class Command(ABC):
    """A reversible workbook mutation."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Return user-facing undo/redo text."""

    @abstractmethod
    def do(self) -> None:
        """Apply the mutation."""

    @abstractmethod
    def undo(self) -> None:
        """Reverse the mutation."""

    def merge_with(self, newer: Command) -> bool:
        """Merge an already-applied adjacent command when safe."""
        return False


HistoryListener = Callable[["CommandHistory"], None]


class CommandHistory:
    """Execute commands and retain a bounded reversible history."""

    def __init__(self, *, limit: int = 200) -> None:
        if limit < 1:
            raise ValueError("Undo limit must be positive")
        self.limit = limit
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._listeners: list[HistoryListener] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_description(self) -> str:
        return self._undo[-1].description if self._undo else ""

    @property
    def redo_description(self) -> str:
        return self._redo[-1].description if self._redo else ""

    def add_listener(self, listener: HistoryListener) -> None:
        """Subscribe to history state changes."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def execute(self, command: Command) -> None:
        """Apply a command and place it on the undo stack."""
        command.do()
        if not self._undo or not self._undo[-1].merge_with(command):
            self._undo.append(command)
            if len(self._undo) > self.limit:
                del self._undo[: len(self._undo) - self.limit]
        self._redo.clear()
        self._notify()

    def undo(self) -> None:
        """Undo the most recent command when available."""
        if not self._undo:
            return
        command = self._undo.pop()
        command.undo()
        self._redo.append(command)
        self._notify()

    def redo(self) -> None:
        """Redo the most recently undone command when available."""
        if not self._redo:
            return
        command = self._redo.pop()
        command.do()
        self._undo.append(command)
        self._notify()

    def clear(self) -> None:
        """Discard all history without changing workbook state."""
        self._undo.clear()
        self._redo.clear()
        self._notify()

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener(self)

