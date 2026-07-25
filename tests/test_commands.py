from __future__ import annotations

from dataclasses import dataclass

from excelclone.commands.base import Command, CommandHistory
from excelclone.commands.edits import (
    AddSheetCommand,
    DeleteSheetCommand,
    RenameSheetCommand,
    SetCellCommand,
    SetRangeCommand,
)
from excelclone.core.engine import FormulaEngine
from excelclone.core.workbook import Workbook


@dataclass
class CounterCommand(Command):
    target: list[int]
    amount: int

    @property
    def description(self) -> str:
        return "Change counter"

    def do(self) -> None:
        self.target[0] += self.amount

    def undo(self) -> None:
        self.target[0] -= self.amount


def test_history_executes_undoes_and_redoes_commands() -> None:
    value = [0]
    history = CommandHistory()

    history.execute(CounterCommand(value, 3))
    history.undo()
    history.redo()

    assert value == [3]
    assert history.can_undo
    assert not history.can_redo
    assert history.undo_description == "Change counter"


def test_new_command_clears_redo_stack() -> None:
    value = [0]
    history = CommandHistory()
    history.execute(CounterCommand(value, 1))
    history.undo()

    history.execute(CounterCommand(value, 4))

    assert value == [4]
    assert not history.can_redo


def test_history_enforces_configured_undo_limit() -> None:
    value = [0]
    history = CommandHistory(limit=200)
    for _ in range(250):
        history.execute(CounterCommand(value, 1))

    undo_count = 0
    while history.can_undo:
        history.undo()
        undo_count += 1

    assert undo_count == 200
    assert value == [50]


def test_history_notifies_listeners_after_state_changes() -> None:
    history = CommandHistory()
    events: list[tuple[bool, bool]] = []
    history.add_listener(lambda current: events.append((current.can_undo, current.can_redo)))

    history.execute(CounterCommand([0], 1))
    history.undo()
    history.redo()

    assert events == [(True, False), (False, True), (True, False)]


def test_set_cell_command_recalculates_and_undoes_formula_dependencies() -> None:
    engine = FormulaEngine(Workbook())
    history = CommandHistory()
    history.execute(SetCellCommand(engine, "Sheet1", 0, 0, 4))
    history.execute(SetCellCommand(engine, "Sheet1", 0, 1, "=A1*3"))

    history.execute(SetCellCommand(engine, "Sheet1", 0, 0, 10))
    assert engine.workbook.active_sheet.get_cell(0, 1).display_value == 30

    history.undo()
    assert engine.workbook.active_sheet.get_cell(0, 0).display_value == 4
    assert engine.workbook.active_sheet.get_cell(0, 1).display_value == 12


def test_consecutive_cell_edits_merge_into_one_undo_step() -> None:
    engine = FormulaEngine(Workbook())
    history = CommandHistory()

    history.execute(SetCellCommand(engine, "Sheet1", 0, 0, "a"))
    history.execute(SetCellCommand(engine, "Sheet1", 0, 0, "ab"))
    history.execute(SetCellCommand(engine, "Sheet1", 0, 0, "abc"))
    history.undo()

    assert engine.workbook.active_sheet.get_cell(0, 0).is_empty
    assert not history.can_undo


def test_set_range_is_one_atomic_undo_step() -> None:
    engine = FormulaEngine(Workbook())
    history = CommandHistory()
    command = SetRangeCommand(
        engine,
        "Sheet1",
        1,
        2,
        (("a", "b"), ("c", "d")),
    )

    history.execute(command)
    history.undo()

    sheet = engine.workbook.active_sheet
    assert all(sheet.get_cell(row, column).is_empty for row in (1, 2) for column in (2, 3))


def test_add_delete_and_restore_sheet_commands_preserve_data() -> None:
    engine = FormulaEngine(Workbook())
    history = CommandHistory()
    history.execute(AddSheetCommand(engine, "Data"))
    engine.set_cell("Data", 0, 0, 42)

    history.execute(DeleteSheetCommand(engine, "Data"))
    assert engine.workbook.sheet_names == ("Sheet1",)

    history.undo()
    assert engine.workbook.sheet_names == ("Sheet1", "Data")
    assert engine.workbook.get_sheet("Data").get_cell(0, 0).display_value == 42


def test_rename_sheet_command_is_reversible() -> None:
    engine = FormulaEngine(Workbook())
    engine.workbook.add_sheet("Data")
    history = CommandHistory()

    history.execute(RenameSheetCommand(engine, "Data", "Inputs"))
    history.undo()

    assert engine.workbook.sheet_names == ("Sheet1", "Data")
