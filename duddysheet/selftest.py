"""Post-build verification that a packaged application actually works.

Freezing can break things the test suite never sees: a missing font cache, a
data file left out of the bundle, a Qt plugin that failed to collect. This
exercises the paths most likely to break in a packaged build and reports a
non-zero exit code when any of them fail, so a broken installer is caught
before a customer meets it.

Run it against a frozen build with::

    DuddySpreadsheet.exe --self-test
"""

from __future__ import annotations

import tempfile
import traceback
from collections.abc import Callable
from pathlib import Path


def _check_formula_engine() -> str:
    """Evaluate formulas through the real engine."""
    from duddysheet.core.engine import FormulaEngine
    from duddysheet.core.workbook import Workbook

    engine = FormulaEngine(Workbook())
    sheet = engine.workbook.active_sheet
    engine.set_cell(sheet.name, 0, 0, 2)
    engine.set_cell(sheet.name, 1, 0, 3)
    engine.set_cell(sheet.name, 2, 0, "=SUM(A1:A2)*PMT(0.05/12,12,-1000)")
    value = sheet.get_cell(2, 0).display_value

    if not isinstance(value, (int, float)):
        raise AssertionError(f"expected a number, got {value!r}")
    return f"formula engine ok (={value:.4f})"


def _check_native_round_trip() -> str:
    """Save and reload a workbook through the native adapter."""
    from duddysheet.core.workbook import Workbook
    from duddysheet.io.native import load_native, save_native

    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, "round trip")

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "selftest.dsheet"
        save_native(workbook, path)
        reloaded = load_native(path)

    if reloaded.active_sheet.get_cell(0, 0).display_value != "round trip":
        raise AssertionError("native round trip lost data")
    return "native file format ok"


def _check_xlsx_round_trip() -> str:
    """Save and reload through the Excel adapter."""
    from duddysheet.core.workbook import Workbook
    from duddysheet.io.xlsx_reader import read_xlsx
    from duddysheet.io.xlsx_writer import write_xlsx

    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, 42)

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "selftest.xlsx"
        write_xlsx(workbook, path)
        reloaded = read_xlsx(path).workbook

    if reloaded.active_sheet.get_cell(0, 0).display_value != 42:
        raise AssertionError("xlsx round trip lost data")
    return "xlsx interoperability ok"


def _check_financial_models() -> str:
    """Build a bundled model, which exercises the widest formula surface."""
    from duddysheet.core.financial_models import create_financial_model

    workbook = create_financial_model("dcf")
    populated = sum(sheet.populated_count for sheet in workbook)

    if populated < 50:
        raise AssertionError(f"DCF model looks empty ({populated} cells)")
    return f"financial models ok ({populated} cells)"


def _check_pdf_export() -> str:
    """Render a worksheet to PDF, which needs Qt fonts and the PDF writer."""
    from duddysheet.core.workbook import Workbook
    from duddysheet.ui.printing import WorksheetRenderer

    workbook = Workbook()
    sheet = workbook.active_sheet
    for row in range(40):
        for column in range(4):
            sheet.set_cell(row, column, row * 10 + column)

    renderer = WorksheetRenderer(sheet, workbook=workbook)
    with tempfile.TemporaryDirectory() as directory:
        written = renderer.export_pdf(Path(directory) / "selftest.pdf")
        data = written.read_bytes()

    if not data.startswith(b"%PDF") or len(data) < 1000:
        raise AssertionError("PDF export produced no usable document")
    return f"pdf export ok ({renderer.page_count} pages, {len(data)} bytes)"


def _check_charts() -> str:
    """Render a chart, which needs matplotlib's font cache and backend."""
    from duddysheet.core.chart import ChartSpec, chart_data
    from duddysheet.core.refs import parse_a1
    from duddysheet.core.workbook import Workbook

    workbook = Workbook()
    sheet = workbook.active_sheet
    for row, value in enumerate((3, 1, 4, 1, 5)):
        sheet.set_cell(row, 0, f"Item {row}")
        sheet.set_cell(row, 1, value)

    spec = ChartSpec(
        chart_id="selftest",
        sheet_name=sheet.name,
        source_range=parse_a1(f"{sheet.name}!A1:B5"),
        chart_type="column",
        has_headers=False,
    )
    data = chart_data(workbook, spec)

    if not data.series:
        raise AssertionError("chart extraction produced no series")
    return f"charts ok ({len(data.series)} series)"


def _check_bundled_resources() -> str:
    """Confirm the icon and legal documents survived packaging."""
    from duddysheet.util.paths import resource_path

    required = ("assets/duddysheet.ico", "EULA.md", "THIRD-PARTY-NOTICES.md")
    missing = [name for name in required if not resource_path(name).is_file()]

    if missing:
        raise AssertionError(f"missing bundled resources: {', '.join(missing)}")
    return "bundled resources ok"


def _check_licensing() -> str:
    """Verify the licence subsystem loads and rejects a bad key."""
    from duddysheet.core.licensing import (
        Edition,
        License,
        LicenseError,
        generate_key_pair,
        issue_license,
        verify_license,
    )
    from datetime import date

    private_key, public_key = generate_key_pair()
    licence = License("Self Test", "s@t", Edition.PERSONAL, 1, date.today())
    verify_license(issue_license(licence, private_key), public_key)

    try:
        verify_license("DS1-bogus.bogus", public_key)
    except LicenseError:
        return "licensing ok"
    raise AssertionError("a forged key was accepted")


CHECKS: tuple[tuple[str, Callable[[], str]], ...] = (
    ("Bundled resources", _check_bundled_resources),
    ("Formula engine", _check_formula_engine),
    ("Native file format", _check_native_round_trip),
    ("Excel interoperability", _check_xlsx_round_trip),
    ("Financial models", _check_financial_models),
    ("Charts", _check_charts),
    ("PDF export", _check_pdf_export),
    ("Licensing", _check_licensing),
)


def run_self_test(verbose: bool = True) -> int:
    """Run every check and return a process exit code."""
    from PySide6.QtWidgets import QApplication

    # A QApplication is required for the rendering checks.
    application = QApplication.instance() or QApplication([])

    failures = 0
    for label, check in CHECKS:
        try:
            detail = check()
        except Exception as error:  # noqa: BLE001 - reporting every failure
            failures += 1
            print(f"  FAIL  {label}: {error}")
            if verbose:
                traceback.print_exc()
        else:
            print(f"  ok    {detail}")

    del application
    if failures:
        print(f"\n{failures} of {len(CHECKS)} checks failed. This build is broken.")
        return 1
    print(f"\nAll {len(CHECKS)} checks passed.")
    return 0
