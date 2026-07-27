from __future__ import annotations

import pytest

from duddysheet.core.refs import CellReference, RangeReference
from duddysheet.core.workbook import Workbook


def test_new_workbook_contains_one_active_sheet() -> None:
    workbook = Workbook()

    assert workbook.sheet_names == ("Sheet1",)
    assert workbook.active_sheet.name == "Sheet1"
    assert workbook.active_sheet_index == 0


def test_sheet_names_are_generated_without_collisions() -> None:
    workbook = Workbook()

    assert workbook.add_sheet().name == "Sheet2"
    assert workbook.add_sheet("Data").name == "Data"
    assert workbook.add_sheet().name == "Sheet3"
    assert workbook.sheet_names == ("Sheet1", "Sheet2", "Data", "Sheet3")


def test_sheet_lookup_is_case_insensitive_and_supports_indexes() -> None:
    workbook = Workbook()
    data = workbook.add_sheet("Quarterly Data")

    assert workbook.get_sheet("quarterly data") is data
    assert workbook.get_sheet(1) is data
    with pytest.raises(KeyError):
        workbook.get_sheet("missing")
    with pytest.raises(IndexError):
        workbook.get_sheet(9)


@pytest.mark.parametrize(
    "name",
    ["", "A" * 32, "Bad/Name", "Bad\\Name", "Bad:Name", "[Bad]", "Bad?Name", "*"],
)
def test_invalid_sheet_names_are_rejected(name: str) -> None:
    workbook = Workbook()

    with pytest.raises(ValueError):
        workbook.add_sheet(name)


def test_duplicate_sheet_names_are_rejected_case_insensitively() -> None:
    workbook = Workbook()
    workbook.add_sheet("Data")

    with pytest.raises(ValueError):
        workbook.add_sheet("DATA")


def test_rename_move_duplicate_and_delete_sheet() -> None:
    workbook = Workbook()
    source = workbook.add_sheet("Data")
    source.set_cell(0, 0, 42)

    workbook.rename_sheet("Data", "Inputs")
    duplicate = workbook.duplicate_sheet("Inputs")
    workbook.move_sheet(duplicate.name, 0)
    removed = workbook.delete_sheet("Inputs")

    assert removed.name == "Inputs"
    assert workbook.sheet_names == ("Inputs (2)", "Sheet1")
    assert workbook.get_sheet("Inputs (2)").get_cell(0, 0).display_value == 42


def test_cannot_delete_only_remaining_sheet() -> None:
    workbook = Workbook()

    with pytest.raises(ValueError, match="last"):
        workbook.delete_sheet("Sheet1")


def test_active_sheet_tracks_insert_move_and_delete() -> None:
    workbook = Workbook()
    workbook.add_sheet("Data")
    workbook.add_sheet("Results")
    workbook.active_sheet = "Data"

    workbook.move_sheet("Data", 0)
    assert workbook.active_sheet.name == "Data"

    workbook.delete_sheet("Data")
    assert workbook.active_sheet.name in {"Sheet1", "Results"}
    assert 0 <= workbook.active_sheet_index < len(workbook)


def test_workbook_named_ranges_support_global_and_sheet_scope() -> None:
    workbook = Workbook()
    workbook.add_sheet("Data")
    global_reference = RangeReference(
        CellReference(0, 0, sheet="Data"),
        CellReference(9, 0, sheet="Data"),
    )
    local_reference = CellReference(4, 2, sheet="Data")

    workbook.define_name("Sales", global_reference)
    workbook.define_name("Sales", local_reference, scope="Data")

    assert workbook.get_name("sales").reference == global_reference
    assert workbook.get_name("SALES", scope="data").reference == local_reference
    assert workbook.get_name("Sales", scope="Sheet1").reference == global_reference


@pytest.mark.parametrize("name", ["A1", "R1C1", "1Sales", "Has Space", "A-B", ""])
def test_invalid_defined_names_are_rejected(name: str) -> None:
    workbook = Workbook()

    with pytest.raises(ValueError):
        workbook.define_name(name, CellReference(0, 0, sheet="Sheet1"))


def test_sheet_rename_updates_named_range_references_and_scope() -> None:
    workbook = Workbook()
    workbook.add_sheet("Data")
    workbook.define_name(
        "LocalValue",
        CellReference(3, 4, sheet="Data"),
        scope="Data",
    )

    workbook.rename_sheet("Data", "Inputs")

    defined_name = workbook.get_name("LocalValue", scope="Inputs")
    assert defined_name.scope == "Inputs"
    assert defined_name.reference.to_a1() == "Inputs!E4"


def test_workbook_copy_is_independent() -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, "original")
    workbook.define_name("Start", CellReference(0, 0, sheet="Sheet1"))

    duplicate = workbook.copy()
    duplicate.active_sheet.set_cell(0, 0, "changed")
    duplicate.rename_sheet("Sheet1", "Copy")

    assert workbook.sheet_names == ("Sheet1",)
    assert workbook.active_sheet.get_cell(0, 0).display_value == "original"
    assert duplicate.sheet_names == ("Copy",)
    assert duplicate.get_name("Start").reference.to_a1() == "Copy!A1"
