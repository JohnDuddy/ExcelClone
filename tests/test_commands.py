from __future__ import annotations

from dataclasses import dataclass

from duddysheet.commands.base import Command, CommandHistory
from duddysheet.commands.edits import (
    AddSheetCommand,
    AddValidationCommand,
    ApplyFilterCommand,
    ClearFilterCommand,
    DeleteRowsCommand,
    DeleteSheetCommand,
    DuplicateSheetCommand,
    InsertRowsCommand,
    MergeCellsCommand,
    MoveSheetCommand,
    PasteCellsCommand,
    RemoveDuplicatesCommand,
    RenameSheetCommand,
    ReplaceAllCommand,
    SetColumnWidthCommand,
    SetCellCommand,
    SetFormatCommand,
    SetFreezePanesCommand,
    SetRangeCommand,
    SetRowHeightCommand,
    SetSheetTabColorCommand,
    SetSheetVisibilityCommand,
    SortRangeCommand,
    TextToColumnsCommand,
)
from duddysheet.core.conditional import FormatPatch
from duddysheet.core.cell import Cell, CellFormat
from duddysheet.core.data_tools import DataValidation, FindOptions, SortKey
from duddysheet.core.engine import FormulaEngine
from duddysheet.core.refs import parse_a1
from duddysheet.core.workbook import Workbook


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


def test_rename_sheet_command_updates_formula_references_on_do_and_undo() -> None:
    engine = FormulaEngine(Workbook())
    engine.workbook.add_sheet("Data")
    engine.set_cell("Data", 0, 0, 4)
    engine.set_cell("Sheet1", 0, 0, "=Data!A1*2")
    history = CommandHistory()

    history.execute(RenameSheetCommand(engine, "Data", "Inputs"))
    assert engine.workbook.active_sheet.get_cell(0, 0).raw_input == "=Inputs!A1*2"
    assert engine.workbook.active_sheet.get_cell(0, 0).display_value == 8

    history.undo()
    assert engine.workbook.active_sheet.get_cell(0, 0).raw_input == "=Data!A1*2"


def test_set_format_command_formats_range_without_changing_content() -> None:
    engine = FormulaEngine(Workbook())
    engine.set_cell("Sheet1", 0, 0, 4)
    engine.set_cell("Sheet1", 0, 1, "=A1*3")
    history = CommandHistory()

    history.execute(
        SetFormatCommand(
            engine,
            "Sheet1",
            0,
            0,
            0,
            1,
            FormatPatch(bold=True, number_format="#,##0.00"),
        )
    )

    sheet = engine.workbook.active_sheet
    assert sheet.get_cell(0, 0).format.bold
    assert sheet.get_cell(0, 1).format.number_format == "#,##0.00"
    assert sheet.get_cell(0, 1).raw_input == "=A1*3"
    assert sheet.get_cell(0, 1).display_value == 12


def test_set_format_command_undo_restores_individual_formats_and_sparse_cells() -> None:
    engine = FormulaEngine(Workbook())
    sheet = engine.workbook.active_sheet
    sheet.set_cell(0, 0, "keep", cell_format=CellFormat(italic=True))
    history = CommandHistory()
    history.execute(
        SetFormatCommand(
            engine,
            "Sheet1",
            0,
            0,
            0,
            1,
            FormatPatch(fill_color="#ffeeaa"),
        )
    )

    history.undo()

    assert sheet.get_cell(0, 0).format == CellFormat(italic=True)
    assert sheet.get_cell(0, 1).is_empty


def test_set_freeze_panes_command_is_reversible() -> None:
    engine = FormulaEngine(Workbook())
    history = CommandHistory()

    history.execute(SetFreezePanesCommand(engine, "Sheet1", (2, 3)))
    assert engine.workbook.active_sheet.freeze_panes == (2, 3)

    history.undo()
    assert engine.workbook.active_sheet.freeze_panes is None


def test_sort_filter_and_validation_commands_are_reversible() -> None:
    engine = FormulaEngine(Workbook())
    sheet = engine.workbook.active_sheet
    for row, value in enumerate(("Value", 3, 1, 2)):
        engine.set_cell("Sheet1", row, 0, value)
    history = CommandHistory()

    history.execute(
        SortRangeCommand(
            engine,
            "Sheet1",
            parse_a1("A1:A4"),
            (SortKey(0),),
            has_header=True,
        )
    )
    assert [sheet.get_cell(row, 0).display_value for row in range(1, 4)] == [1, 2, 3]
    history.undo()
    sheet = engine.workbook.active_sheet
    assert [sheet.get_cell(row, 0).display_value for row in range(1, 4)] == [3, 1, 2]

    history.execute(
        ApplyFilterCommand(
            engine,
            "Sheet1",
            parse_a1("A1:A4"),
            0,
            frozenset({1, 3}),
        )
    )
    sheet = engine.workbook.active_sheet
    assert sheet.filtered_rows == {3}
    history.execute(ClearFilterCommand(engine, "Sheet1"))
    sheet = engine.workbook.active_sheet
    assert sheet.filtered_rows == set()
    history.undo()
    sheet = engine.workbook.active_sheet
    assert sheet.filtered_rows == {3}

    validation = DataValidation(
        parse_a1("A2:A4"),
        "whole_number",
        "between",
        (1, 3),
    )
    history.execute(AddValidationCommand(engine, "Sheet1", validation))
    sheet = engine.workbook.active_sheet
    assert sheet.data_validations == [validation]
    history.undo()
    sheet = engine.workbook.active_sheet
    assert sheet.data_validations == []


def test_undo_restores_state_across_50_mixed_operations() -> None:
    engine = FormulaEngine(Workbook())
    history = CommandHistory(limit=200)
    original = engine.workbook.copy()

    for cycle in range(10):
        history.execute(SetCellCommand(engine, "Sheet1", cycle + 5, 0, cycle))
        history.execute(InsertRowsCommand(engine, "Sheet1", 1, 1))
        history.execute(DeleteRowsCommand(engine, "Sheet1", 1, 1))
        history.execute(
            SetRangeCommand(
                engine,
                "Sheet1",
                cycle + 20,
                1,
                ((cycle, cycle + 1),),
            )
        )
        history.execute(
            PasteCellsCommand(
                engine,
                "Sheet1",
                cycle + 40,
                3,
                ((Cell(raw_input=cycle, cached_value=cycle),),),
                (0, 0),
            )
        )

    for _ in range(50):
        history.undo()

    assert tuple(engine.workbook.active_sheet.iter_populated()) == tuple(
        original.active_sheet.iter_populated()
    )
    assert not history.can_undo


def test_merge_dimensions_replace_and_cleanup_commands_undo() -> None:
    engine = FormulaEngine(Workbook())
    history = CommandHistory()
    for row, values in enumerate((("Name", "Data"), ("A", "x|y"), ("A", "z"))):
        for column, value in enumerate(values):
            engine.set_cell("Sheet1", row, column, value)

    history.execute(
        MergeCellsCommand(engine, "Sheet1", parse_a1("D1:E2"))
    )
    history.execute(SetRowHeightCommand(engine, "Sheet1", (0, 1), 25))
    history.execute(SetColumnWidthCommand(engine, "Sheet1", (0,), 20))
    history.execute(
        ReplaceAllCommand(
            engine,
            FindOptions("Name", "Label", whole_cell=True),
            "Sheet1",
        )
    )
    history.execute(
        RemoveDuplicatesCommand(
            engine,
            "Sheet1",
            parse_a1("A1:B3"),
            (0,),
        )
    )
    history.execute(
        TextToColumnsCommand(engine, "Sheet1", parse_a1("B2:B2"), "|")
    )

    sheet = engine.workbook.active_sheet
    assert sheet.merged_ranges == [parse_a1("D1:E2")]
    assert sheet.row_heights[0] == 25
    assert sheet.column_widths[0] == 20
    assert sheet.get_cell(0, 0).raw_input == "Label"
    assert sheet.get_cell(1, 2).raw_input == "y"

    for _ in range(6):
        history.undo()
    restored = engine.workbook.active_sheet
    assert restored.merged_ranges == []
    assert restored.row_heights == {}
    assert restored.column_widths == {}
    assert restored.get_cell(0, 0).raw_input == "Name"


def test_sheet_move_duplicate_visibility_and_tab_color_commands_undo() -> None:
    engine = FormulaEngine(Workbook())
    engine.workbook.add_sheet("Data")
    history = CommandHistory()

    history.execute(MoveSheetCommand(engine, 1, 0))
    assert engine.workbook.sheet_names == ("Data", "Sheet1")
    history.execute(DuplicateSheetCommand(engine, "Data", "Data Copy"))
    assert "Data Copy" in engine.workbook.sheet_names
    history.execute(SetSheetTabColorCommand(engine, "Data", "#123456"))
    assert engine.workbook.get_sheet("Data").tab_color == "#123456"
    history.execute(SetSheetVisibilityCommand(engine, "Data", False))
    assert not engine.workbook.get_sheet("Data").visible
    assert engine.workbook.active_sheet.visible

    for _ in range(4):
        history.undo()
    assert engine.workbook.sheet_names == ("Sheet1", "Data")
    assert engine.workbook.get_sheet("Data").visible
    assert engine.workbook.get_sheet("Data").tab_color is None
