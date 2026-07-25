"""Build the 200-case workbook that Microsoft Excel recalculates and caches."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "golden.xlsx"


def build_fixture() -> Path:
    """Create formula cases and independent literal expectations."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Golden Cases"
    sheet.append(("Formula", "Independent Expected", "Category"))

    cases: list[tuple[str, object, str]] = []
    for value in range(1, 51):
        cases.append(
            (
                f"={value}+{value + 1}*2",
                value + (value + 1) * 2,
                "operator precedence",
            )
        )
    for value in range(1, 26):
        cases.append((f'="{value}"+1', value + 1, "text coercion"))
        cases.append(
            (
                f"=SUM({value},{value + 1},{value + 2})",
                value + value + 1 + value + 2,
                "SUM",
            )
        )
        cases.append(
            (
                f"=IF({value}>12,{value}*2,{value}+2)",
                value * 2 if value > 12 else value + 2,
                "IF",
            )
        )
        rounded = Decimal(value) / Decimal(4)
        cases.append(
            (
                f"=ROUND({value}/4,2)",
                float(rounded.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "ROUND",
            )
        )
        cases.append(
            (
                f'=LEN("Case {value}")',
                len(f"Case {value}"),
                "LEN",
            )
        )
        cases.append(
            (
                f'=VLOOKUP("b",{{"a",{value};"b",{value + 10}}},2,FALSE)',
                value + 10,
                "VLOOKUP",
            )
        )

    if len(cases) != 200:
        raise RuntimeError(f"Golden fixture must contain 200 cases, got {len(cases)}")

    for formula, expected, category in cases:
        sheet.append((formula, expected, category))

    header_fill = PatternFill("solid", fgColor="1F4E3D")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
    sheet.freeze_panes = "A2"
    sheet.column_dimensions["A"].width = 54
    sheet.column_dimensions["B"].width = 23
    sheet.column_dimensions["C"].width = 24
    sheet.auto_filter.ref = f"A1:C{sheet.max_row}"

    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.calculation.calcMode = "auto"
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(FIXTURE_PATH)
    return FIXTURE_PATH


if __name__ == "__main__":
    print(build_fixture())
