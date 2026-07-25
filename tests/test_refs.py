from __future__ import annotations

import pytest

from excelclone.core.refs import (
    MAX_COLUMNS,
    MAX_ROWS,
    CellReference,
    RangeReference,
    column_to_index,
    index_to_column,
    parse_a1,
    parse_r1c1,
    quote_sheet_name,
)


@pytest.mark.parametrize(
    ("label", "index"),
    [
        ("A", 0),
        ("Z", 25),
        ("AA", 26),
        ("AZ", 51),
        ("BA", 52),
        ("ZZ", 701),
        ("AAA", 702),
        ("XFD", 16383),
    ],
)
def test_column_labels_round_trip(label: str, index: int) -> None:
    assert column_to_index(label) == index
    assert index_to_column(index) == label


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("A1", CellReference(row=0, column=0)),
        ("XFD1048576", CellReference(row=MAX_ROWS - 1, column=MAX_COLUMNS - 1)),
        ("$C$9", CellReference(row=8, column=2, row_absolute=True, column_absolute=True)),
        ("D$12", CellReference(row=11, column=3, row_absolute=True)),
        ("$E13", CellReference(row=12, column=4, column_absolute=True)),
        ("Sheet2!B3", CellReference(row=2, column=1, sheet="Sheet2")),
        (
            "'My Sheet'!$A1",
            CellReference(row=0, column=0, sheet="My Sheet", column_absolute=True),
        ),
        (
            "'Owner''s Data'!A1",
            CellReference(row=0, column=0, sheet="Owner's Data"),
        ),
    ],
)
def test_parse_a1_cell_references(text: str, expected: CellReference) -> None:
    reference = parse_a1(text)

    assert reference == expected
    assert parse_a1(reference.to_a1()) == expected


@pytest.mark.parametrize(
    ("text", "start", "end", "count"),
    [
        ("A1:B2", (0, 0), (1, 1), 4),
        ("B2:A1", (0, 0), (1, 1), 4),
        ("A:A", (0, 0), (MAX_ROWS - 1, 0), MAX_ROWS),
        ("2:3", (1, 0), (2, MAX_COLUMNS - 1), MAX_COLUMNS * 2),
        ("'Data 1'!B2:C3", (1, 1), (2, 2), 4),
    ],
)
def test_parse_a1_ranges(
    text: str,
    start: tuple[int, int],
    end: tuple[int, int],
    count: int,
) -> None:
    reference = parse_a1(text)

    assert isinstance(reference, RangeReference)
    assert (reference.min_row, reference.min_column) == start
    assert (reference.max_row, reference.max_column) == end
    assert len(reference) == count


@pytest.mark.parametrize(
    "text",
    ["", "A0", "XFE1", "A1048577", "1A", "A", "0:1", "A:XFE", "A1:B"],
)
def test_invalid_a1_references_are_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        parse_a1(text)


@pytest.mark.parametrize(
    ("text", "origin", "expected"),
    [
        ("R1C1", (10, 10), CellReference(row=0, column=0, row_absolute=True, column_absolute=True)),
        ("R[-2]C[3]", (10, 10), CellReference(row=8, column=13)),
        ("RC", (4, 5), CellReference(row=4, column=5)),
        ("R5C[-1]", (10, 10), CellReference(row=4, column=9, row_absolute=True)),
        ("R[1]C7", (10, 10), CellReference(row=11, column=6, column_absolute=True)),
        ("Sheet2!R1C1", (0, 0), CellReference(row=0, column=0, sheet="Sheet2", row_absolute=True, column_absolute=True)),
    ],
)
def test_parse_r1c1_references(
    text: str,
    origin: tuple[int, int],
    expected: CellReference,
) -> None:
    assert parse_r1c1(text, origin=origin) == expected


def test_reference_translation_respects_absolute_parts() -> None:
    reference = parse_a1("$A1:B$2")
    assert isinstance(reference, RangeReference)

    translated = reference.shifted(rows=3, columns=4)

    assert translated.to_a1() == "$A4:F$2"


@pytest.mark.parametrize(
    ("name", "quoted"),
    [
        ("Sheet1", "Sheet1"),
        ("Data_2026", "Data_2026"),
        ("My Sheet", "'My Sheet'"),
        ("Owner's Data", "'Owner''s Data'"),
        ("A1", "'A1'"),
    ],
)
def test_sheet_name_quoting(name: str, quoted: str) -> None:
    assert quote_sheet_name(name) == quoted


@pytest.mark.parametrize("label", ["", "1", "A1", "A-B", "Ä", "XFE"])
def test_invalid_column_labels_are_rejected(label: str) -> None:
    with pytest.raises(ValueError):
        column_to_index(label)


@pytest.mark.parametrize("index", [-1, MAX_COLUMNS, MAX_COLUMNS + 1])
def test_invalid_column_indexes_are_rejected(index: int) -> None:
    with pytest.raises(ValueError):
        index_to_column(index)


def test_empty_sheet_name_cannot_be_quoted() -> None:
    with pytest.raises(ValueError):
        quote_sheet_name("")


@pytest.mark.parametrize(
    "arguments",
    [
        {"row": -1, "column": 0},
        {"row": MAX_ROWS, "column": 0},
        {"row": 0, "column": -1},
        {"row": 0, "column": MAX_COLUMNS},
        {"row": 0, "column": 0, "sheet": ""},
    ],
)
def test_cell_reference_rejects_invalid_state(arguments: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        CellReference(**arguments)


def test_cell_reference_coordinate_and_sheet_suppression() -> None:
    reference = CellReference(2, 4, sheet="Data")

    assert reference.coordinate == (2, 4)
    assert reference.to_a1(include_sheet=False) == "E3"


@pytest.mark.parametrize(
    ("reference", "origin", "expected"),
    [
        (CellReference(4, 5), (4, 5), "RC"),
        (CellReference(6, 2), (4, 5), "R[2]C[-3]"),
        (
            CellReference(4, 5, row_absolute=True, column_absolute=True),
            (10, 10),
            "R5C6",
        ),
        (
            CellReference(0, 0, sheet="Data", row_absolute=True, column_absolute=True),
            (10, 10),
            "Data!R1C1",
        ),
    ],
)
def test_cell_reference_renders_r1c1(
    reference: CellReference,
    origin: tuple[int, int],
    expected: str,
) -> None:
    assert reference.to_r1c1(origin=origin) == expected


def test_range_iteration_and_membership_are_rectangular() -> None:
    reference = parse_a1("B2:C3")
    assert isinstance(reference, RangeReference)

    assert [item.coordinate for item in reference] == [
        (1, 1),
        (1, 2),
        (2, 1),
        (2, 2),
    ]
    assert reference.contains(2, 2)
    assert not reference.contains(0, 0)


@pytest.mark.parametrize(
    ("text", "rendered"),
    [
        ("$A:$C", "$A:$C"),
        ("$2:$4", "$2:$4"),
        ("'My Data'!A:A", "'My Data'!A:A"),
        ("Data!1:2", "Data!1:2"),
        ("Data!B2:A1", "Data!B2:A1"),
    ],
)
def test_ranges_render_to_a1(text: str, rendered: str) -> None:
    reference = parse_a1(text)
    assert isinstance(reference, RangeReference)
    assert reference.to_a1() == rendered


def test_whole_axis_translation_ignores_the_spanned_axis() -> None:
    whole_rows = parse_a1("2:3")
    whole_columns = parse_a1("B:C")
    assert isinstance(whole_rows, RangeReference)
    assert isinstance(whole_columns, RangeReference)

    assert whole_rows.shifted(rows=2, columns=500).to_a1() == "4:5"
    assert whole_columns.shifted(rows=500, columns=2).to_a1() == "D:E"


def test_range_reference_rejects_inconsistent_construction() -> None:
    with pytest.raises(ValueError, match="both"):
        RangeReference(
            CellReference(0, 0),
            CellReference(MAX_ROWS - 1, MAX_COLUMNS - 1),
            whole_row=True,
            whole_column=True,
        )
    with pytest.raises(ValueError, match="same sheet"):
        RangeReference(
            CellReference(0, 0, sheet="One"),
            CellReference(1, 1, sheet="Two"),
        )
    with pytest.raises(ValueError, match="Whole-row"):
        RangeReference(
            CellReference(0, 1),
            CellReference(1, MAX_COLUMNS - 1),
            whole_row=True,
        )
    with pytest.raises(ValueError, match="Whole-column"):
        RangeReference(
            CellReference(1, 0),
            CellReference(MAX_ROWS - 1, 1),
            whole_column=True,
        )


def test_r1c1_ranges_and_default_sheet_are_supported() -> None:
    reference = parse_r1c1(
        "R[-1]C[-1]:R[1]C[1]",
        origin=(5, 5),
        default_sheet="Data",
    )

    assert isinstance(reference, RangeReference)
    assert reference.to_a1() == "Data!E5:G7"


@pytest.mark.parametrize(
    "text",
    [
        "R:C",
        "R1C1:R2C2:R3C3",
        "R[1C1",
        "'Sheet'!",
        "'Sheet'A1",
        "'Sheet!A1",
        "Sheet!!A1",
        "!A1",
        "Sheet!",
        "A1:B2:C3",
        "1048577:1048578",
    ],
)
def test_malformed_reference_syntax_is_rejected(text: str) -> None:
    parser = parse_r1c1 if text.upper().startswith("R") else parse_a1
    arguments = {"origin": (0, 0)} if parser is parse_r1c1 else {}
    with pytest.raises(ValueError):
        parser(text, **arguments)
