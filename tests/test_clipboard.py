from __future__ import annotations

import json
from datetime import date, datetime, time

import pytest

from duddysheet.core.cell import BorderStyle, Cell, CellFormat
from duddysheet.core.clipboard import decode_cell_matrix, encode_cell_matrix


def test_rich_clipboard_round_trip_preserves_typed_values_and_formats() -> None:
    cells = (
        (
            Cell(
                raw_input=datetime(2026, 7, 25, 9, 30),
                cached_value=datetime(2026, 7, 25, 9, 30),
                format=CellFormat(
                    bold=True,
                    bottom_border=BorderStyle("double", "#123456"),
                ),
            ),
            Cell(raw_input=date(2026, 7, 25), cached_value=date(2026, 7, 25)),
            Cell(raw_input=time(9, 30), cached_value=time(9, 30)),
        ),
    )

    restored, origin = decode_cell_matrix(encode_cell_matrix(cells, (4, 5)))

    assert restored == cells
    assert origin == (4, 5)


@pytest.mark.parametrize(
    "payload",
    [
        {"version": 2, "origin": [0, 0], "cells": [[{}]]},
        {"version": 1, "origin": [0], "cells": [[{}]]},
        {"version": 1, "origin": [0, 0], "cells": []},
        {"version": 1, "origin": [0, 0], "cells": [[{}], [{}, {}]]},
        {
            "version": 1,
            "origin": [0, 0],
            "cells": [[{"raw": {"type": "mystery"}, "format": {}}]],
        },
    ],
)
def test_rich_clipboard_rejects_invalid_payloads(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        decode_cell_matrix(json.dumps(payload).encode("utf-8"))
