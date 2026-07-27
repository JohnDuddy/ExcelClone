"""Differential backtest of Duddy Spreadsheet financial calculations against Excel."""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook as XlsxWorkbook
from openpyxl import load_workbook

from duddysheet.core.errors import SpreadsheetError
from duddysheet.core.evaluator import FormulaEvaluator
from duddysheet.core.financial_models import (
    FINANCIAL_MODEL_CATALOG,
    create_financial_model,
)
from duddysheet.core.functions import FUNCTION_REGISTRY
from duddysheet.core.refs import CellReference, parse_a1
from duddysheet.core.workbook import Workbook
from duddysheet.io.xlsx_writer import write_xlsx
from duddysheet.io.formula_compat import to_xlsx_formula


@dataclass(frozen=True, slots=True)
class FormulaCase:
    """One Excel/Duddy Spreadsheet differential formula."""

    case_id: str
    formula: str
    tolerance: float = 1e-7


@dataclass(frozen=True, slots=True)
class Mismatch:
    """One differing Excel and Duddy Spreadsheet result."""

    scope: str
    item: str
    formula: str
    opengrid: Any
    excel: Any
    difference: float | None


FINANCIAL_CASES = (
    FormulaCase(
        "ACCRINT",
        "=ACCRINT(DATE(2025,1,1),DATE(2025,7,1),DATE(2025,3,1),0.05,1000,2)",
    ),
    FormulaCase("COUPDAYBS", "=COUPDAYBS(DATE(2025,3,17),DATE(2030,2,28),2,1)"),
    FormulaCase("COUPDAYS", "=COUPDAYS(DATE(2025,3,17),DATE(2030,2,28),2,1)"),
    FormulaCase("COUPDAYSNC", "=COUPDAYSNC(DATE(2025,3,17),DATE(2030,2,28),2,1)"),
    FormulaCase("COUPNCD", "=COUPNCD(DATE(2025,3,17),DATE(2030,2,28),2,1)"),
    FormulaCase("COUPNUM", "=COUPNUM(DATE(2025,3,17),DATE(2030,2,28),2,1)"),
    FormulaCase("COUPPCD", "=COUPPCD(DATE(2025,3,17),DATE(2030,2,28),2,1)"),
    FormulaCase("CUMIPMT", "=CUMIPMT(0.065/12,360,350000,1,12,0)", 1e-5),
    FormulaCase("CUMPRINC", "=CUMPRINC(0.065/12,360,350000,1,12,0)", 1e-5),
    FormulaCase("DB", "=DB(100000,10000,7,3,9)"),
    FormulaCase("DDB", "=DDB(100000,10000,7,3,1.5)"),
    FormulaCase("DISC", "=DISC(DATE(2025,1,1),DATE(2025,7,1),97,100,1)"),
    FormulaCase("DOLLARDE", "=DOLLARDE(101.08,32)"),
    FormulaCase("DOLLARFR", "=DOLLARFR(101.25,32)"),
    FormulaCase(
        "DURATION",
        "=DURATION(DATE(2025,3,17),DATE(2030,2,28),0.045,0.052,2,1)",
    ),
    FormulaCase("EFFECT", "=EFFECT(0.0675,12)"),
    FormulaCase("FV", "=FV(0.065/12,360,-2212.24,350000,0)", 1e-4),
    FormulaCase("FVSCHEDULE", "=FVSCHEDULE(1000,{0.04,0.05,-0.02,0.06})"),
    FormulaCase("INTRATE", "=INTRATE(DATE(2025,1,1),DATE(2025,7,1),970,1000,1)"),
    FormulaCase("IPMT", "=IPMT(0.065/12,37,360,350000)"),
    FormulaCase("IRR", "=IRR({-500000,80000,90000,110000,130000,350000})"),
    FormulaCase("ISPMT", "=ISPMT(0.065/12,36,360,350000)"),
    FormulaCase(
        "MDURATION",
        "=MDURATION(DATE(2025,3,17),DATE(2030,2,28),0.045,0.052,2,1)",
    ),
    FormulaCase("MIRR", "=MIRR({-100000,20000,30000,40000,50000},0.08,0.1)"),
    FormulaCase("NOMINAL", "=NOMINAL(0.06965,12)"),
    FormulaCase("NPER", "=NPER(0.065/12,-2212.24,350000)"),
    FormulaCase("NPV", "=NPV(0.1,80000,90000,110000,130000,350000)-500000"),
    FormulaCase("PDURATION", "=PDURATION(0.08,100000,200000)"),
    FormulaCase("PMT", "=PMT(0.065/12,360,350000)"),
    FormulaCase("PPMT", "=PPMT(0.065/12,37,360,350000)"),
    FormulaCase(
        "PRICE",
        "=PRICE(DATE(2025,3,17),DATE(2030,2,28),0.045,0.052,100,2,1)",
    ),
    FormulaCase("PRICEDISC", "=PRICEDISC(DATE(2025,1,1),DATE(2025,7,1),0.055,100,1)"),
    FormulaCase("PV", "=PV(0.065/12,360,-2212.24)"),
    FormulaCase("RATE", "=RATE(360,-2212.24,350000)"),
    FormulaCase("RECEIVED", "=RECEIVED(DATE(2025,1,1),DATE(2025,7,1),970,0.055,1)"),
    FormulaCase("RRI", "=RRI(10,100000,200000)"),
    FormulaCase("SLN", "=SLN(100000,10000,7)"),
    FormulaCase("SYD", "=SYD(100000,10000,7,3)"),
    FormulaCase("TBILLEQ", "=TBILLEQ(DATE(2025,1,1),DATE(2025,7,1),0.05)"),
    FormulaCase("TBILLPRICE", "=TBILLPRICE(DATE(2025,1,1),DATE(2025,7,1),0.05)"),
    FormulaCase("TBILLYIELD", "=TBILLYIELD(DATE(2025,1,1),DATE(2025,7,1),97.5)"),
    FormulaCase("VDB", "=VDB(100000,10000,7,1.5,4.25,1.5,FALSE)"),
    FormulaCase(
        "XIRR",
        "=XIRR({-500000,80000,90000,110000,130000,350000},"
        "{45658,45901,46174,46600,47088,47484})",
    ),
    FormulaCase(
        "XNPV",
        "=XNPV(0.1,{-500000,80000,90000,110000,130000,350000},"
        "{45658,45901,46174,46600,47088,47484})",
        1e-5,
    ),
    FormulaCase(
        "YIELD",
        "=YIELD(DATE(2025,3,17),DATE(2030,2,28),0.045,96.8,100,2,1)",
    ),
    FormulaCase("YIELDDISC", "=YIELDDISC(DATE(2025,1,1),DATE(2025,7,1),97,100,1)"),
    FormulaCase(
        "PRICE_BASIS_0",
        "=PRICE(DATE(2025,3,17),DATE(2031,2,28),0.045,0.052,100,2,0)",
    ),
    FormulaCase(
        "PRICE_BASIS_2",
        "=PRICE(DATE(2025,3,17),DATE(2031,2,28),0.045,0.052,100,2,2)",
    ),
    FormulaCase(
        "PRICE_BASIS_3",
        "=PRICE(DATE(2025,3,17),DATE(2031,2,28),0.045,0.052,100,2,3)",
    ),
    FormulaCase(
        "PRICE_BASIS_4",
        "=PRICE(DATE(2025,3,17),DATE(2031,2,28),0.045,0.052,100,2,4)",
    ),
)

_EXCEL_RECALCULATE = r"""
$ErrorActionPreference = "Stop"
$excel = $null
$book = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AutomationSecurity = 3
    $excelProcess = Get-CimInstance Win32_Process -Filter "Name = 'EXCEL.EXE'" |
        Sort-Object CreationDate -Descending |
        Select-Object -First 1
    Set-Content -LiteralPath $env:BACKTEST_EXCEL_PID -Value $excelProcess.ProcessId
    $book = $excel.Workbooks.Open($env:BACKTEST_XLSX, 0, $false)
    $excel.Calculation = -4135
    if ($env:BACKTEST_RANGE) {
        $sheet = $book.Worksheets.Item($env:BACKTEST_SHEET)
        $sheet.Range($env:BACKTEST_RANGE).Calculate()
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($sheet)
    } else {
        $excel.CalculateFullRebuild()
    }
    $book.CheckCompatibility = $false
    $book.Save()
    Write-Output $excel.Version
} finally {
    if ($null -ne $book) {
        $book.Close($false)
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($book)
    }
    if ($null -ne $excel) {
        $excel.Quit()
        [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
"""


def run_backtest(output: Path) -> tuple[int, int, tuple[Mismatch, ...], str]:
    """Run formula and model differential checks and write a Markdown report."""
    financial_names = {
        name
        for name, spec in FUNCTION_REGISTRY.items()
        if spec.implementation.__module__.endswith("finance_fn")
    }
    covered_names = {
        case.case_id
        for case in FINANCIAL_CASES
        if case.case_id in financial_names
    }
    if covered_names != financial_names:
        missing = ", ".join(sorted(financial_names - covered_names))
        raise RuntimeError(f"Financial backtest cases missing: {missing}")

    output.parent.mkdir(parents=True, exist_ok=True)
    mismatches: list[Mismatch] = []
    formula_checks = 0
    model_checks = 0
    excel_version = ""
    with tempfile.TemporaryDirectory(
        prefix="opengrid-financial-backtest-",
        dir=output.parent.resolve(),
        ignore_cleanup_errors=True,
    ) as temp:
        temporary = Path(temp)
        formula_path = temporary / "financial-functions.xlsx"
        _write_formula_cases(formula_path)
        print("Excel backtest: financial functions", flush=True)
        excel_version = _calculate_with_excel(
            formula_path,
            sheet_name="Financial Cases",
            range_address=f"C2:C{len(FINANCIAL_CASES) + 1}",
        )
        formula_mismatches = _compare_formula_cases(formula_path)
        formula_checks = len(FINANCIAL_CASES)
        mismatches.extend(formula_mismatches)

        for template in FINANCIAL_MODEL_CATALOG:
            print(f"Excel backtest: {template.name}", flush=True)
            workbook = create_financial_model(template.key)
            path = temporary / f"{template.key}.xlsx"
            expected = {
                (sheet.name, row, column): (
                    cell.raw_input,
                    cell.error if cell.error is not None else cell.display_value,
                )
                for sheet in workbook
                for (row, column), cell in sheet.iter_populated()
                if cell.is_formula
            }
            write_xlsx(workbook, path)
            _set_manual_calculation(path)
            _calculate_with_excel(path)
            model_checks += len(expected)
            mismatches.extend(
                _compare_model(template.name, path, expected)
            )

    output.write_text(
        _render_report(
            excel_version,
            formula_checks,
            model_checks,
            tuple(mismatches),
        ),
        encoding="utf-8",
    )
    return formula_checks, model_checks, tuple(mismatches), excel_version


def _write_formula_cases(path: Path) -> None:
    workbook = XlsxWorkbook()
    sheet = workbook.active
    sheet.title = "Financial Cases"
    sheet.append(("Case", "Formula Text", "Excel Result"))
    for case in FINANCIAL_CASES:
        sheet.append(
            (
                case.case_id,
                case.formula,
                to_xlsx_formula(case.formula),
            )
        )
    workbook.calculation.fullCalcOnLoad = False
    workbook.calculation.forceFullCalc = False
    workbook.calculation.calcMode = "manual"
    workbook.save(path)


def _set_manual_calculation(path: Path) -> None:
    workbook = load_workbook(path)
    workbook.calculation.fullCalcOnLoad = False
    workbook.calculation.forceFullCalc = False
    workbook.calculation.calcMode = "manual"
    workbook.save(path)
    workbook.close()


def _calculate_with_excel(
    path: Path,
    *,
    sheet_name: str | None = None,
    range_address: str | None = None,
) -> str:
    environment = os.environ.copy()
    environment["BACKTEST_XLSX"] = str(path.resolve())
    pid_path = path.with_suffix(".excel.pid")
    environment["BACKTEST_EXCEL_PID"] = str(pid_path)
    environment["BACKTEST_SHEET"] = sheet_name or ""
    environment["BACKTEST_RANGE"] = range_address or ""
    process = subprocess.Popen(
        (
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            _EXCEL_RECALCULATE,
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        stdout, stderr = process.communicate(timeout=120)
    except subprocess.TimeoutExpired as error:
        subprocess.run(
            ("taskkill", "/PID", str(process.pid), "/T", "/F"),
            check=False,
            capture_output=True,
            text=True,
        )
        if pid_path.exists():
            excel_pid = pid_path.read_text(encoding="utf-8").strip()
            subprocess.run(
                ("taskkill", "/PID", excel_pid, "/F"),
                check=False,
                capture_output=True,
                text=True,
            )
        process.communicate()
        raise RuntimeError(
            f"Excel recalculation timed out for {path.name}"
        ) from error
    if process.returncode != 0:
        raise RuntimeError(
            f"Excel recalculation failed for {path.name}:\n"
            + (stderr.strip() or stdout.strip())
        )
    pid_path.unlink(missing_ok=True)
    return stdout.strip().splitlines()[-1]


def _compare_formula_cases(path: Path) -> tuple[Mismatch, ...]:
    cached = load_workbook(path, data_only=True, read_only=True)
    sheet = cached["Financial Cases"]
    evaluator = FormulaEvaluator(Workbook())
    mismatches: list[Mismatch] = []
    for row, case in enumerate(FINANCIAL_CASES, 2):
        opengrid = evaluator.evaluate(case.formula)
        excel = sheet.cell(row, 3).value
        if not _matches(opengrid, excel, case.tolerance):
            mismatches.append(
                Mismatch(
                    "Function",
                    case.case_id,
                    case.formula,
                    _normalized(opengrid),
                    _normalized(excel),
                    _difference(opengrid, excel),
                )
            )
    cached.close()
    return tuple(mismatches)


def _compare_model(
    model_name: str,
    path: Path,
    expected: dict[tuple[str, int, int], tuple[str, Any]],
) -> tuple[Mismatch, ...]:
    cached = load_workbook(path, data_only=True, read_only=True)
    mismatches: list[Mismatch] = []
    for (sheet_name, row, column), (formula, opengrid) in expected.items():
        excel = cached[sheet_name].cell(row + 1, column + 1).value
        if not _matches(opengrid, excel, 1e-6):
            address = CellReference(row, column, sheet=sheet_name).to_a1()
            mismatches.append(
                Mismatch(
                    model_name,
                    address,
                    formula,
                    _normalized(opengrid),
                    _normalized(excel),
                    _difference(opengrid, excel),
                )
            )
    cached.close()
    return tuple(mismatches)


def _normalized(value: Any) -> Any:
    if isinstance(value, SpreadsheetError):
        return value.literal
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        serial = (value - date(1899, 12, 31)).days
        return serial + (1 if value >= date(1900, 3, 1) else 0)
    return value


def _matches(left: Any, right: Any, tolerance: float) -> bool:
    normalized_left = _normalized(left)
    normalized_right = _normalized(right)
    if isinstance(normalized_left, bool) or isinstance(normalized_right, bool):
        return normalized_left is normalized_right
    if isinstance(normalized_left, (int, float)) and isinstance(
        normalized_right,
        (int, float),
    ):
        return math.isclose(
            float(normalized_left),
            float(normalized_right),
            rel_tol=tolerance,
            abs_tol=tolerance,
        )
    return normalized_left == normalized_right


def _difference(left: Any, right: Any) -> float | None:
    normalized_left = _normalized(left)
    normalized_right = _normalized(right)
    if isinstance(normalized_left, (int, float)) and isinstance(
        normalized_right,
        (int, float),
    ):
        return float(normalized_left) - float(normalized_right)
    return None


def _render_report(
    excel_version: str,
    formula_checks: int,
    model_checks: int,
    mismatches: tuple[Mismatch, ...],
) -> str:
    status = "PASS" if not mismatches else "FAIL"
    lines = [
        "# Duddy Spreadsheet Financial Backtest",
        "",
        f"- Status: **{status}**",
        f"- Microsoft Excel version: `{excel_version}`",
        f"- Financial formula cases: {formula_checks}",
        f"- Built-in model formula cells: {model_checks}",
        f"- Mismatches: {len(mismatches)}",
        "- Numeric comparison: relative and absolute tolerance by case; model tolerance `1e-6`",
        "",
        "## Mismatches",
        "",
    ]
    if not mismatches:
        lines.append("No differences exceeded the configured tolerances.")
    else:
        lines.extend(
            (
                "| Scope | Item | Formula | Duddy Spreadsheet | Excel | Difference |",
                "|---|---|---|---:|---:|---:|",
            )
        )
        for mismatch in mismatches:
            formula = mismatch.formula.replace("|", "\\|")
            difference = (
                ""
                if mismatch.difference is None
                else f"{mismatch.difference:.12g}"
            )
            lines.append(
                f"| {mismatch.scope} | {mismatch.item} | `{formula}` | "
                f"{mismatch.opengrid!s} | {mismatch.excel!s} | {difference} |"
            )
    lines.append("")
    return "\n".join(lines)


def _default_output() -> Path:
    return Path("outputs") / "financial-backtest.md"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=_default_output(),
        help="Markdown report path",
    )
    arguments = parser.parse_args()
    formula_checks, model_checks, mismatches, excel_version = run_backtest(
        arguments.output
    )
    print(
        f"Excel {excel_version}: {formula_checks} function cases, "
        f"{model_checks} model formulas, {len(mismatches)} mismatches"
    )
    print(f"Report: {arguments.output.resolve()}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
