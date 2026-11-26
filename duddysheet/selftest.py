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

    # Draw a 2-D and a 3-D chart: the 3-D toolkit is loaded by name at run
    # time, so a frozen build can lack it while every import still succeeds.
    from dataclasses import replace

    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from duddysheet.ui.chart_renderer import draw_chart

    for chart_type in ("column", "column_3d"):
        figure = Figure(figsize=(4, 3))
        FigureCanvasAgg(figure)
        draw_chart(figure, workbook, replace(spec, chart_type=chart_type))
        figure.canvas.draw()
    return f"charts ok ({len(data.series)} series, 2-D and 3-D rendered)"


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


def _check_analysis_features() -> str:
    """Tables, PivotTables, and data tables calculate and survive both file formats."""
    from duddysheet.core.analysis_help import build_practice_workbook
    from duddysheet.core.engine import FormulaEngine
    from duddysheet.io.native import load_native, save_native
    from duddysheet.io.xlsx_reader import read_xlsx
    from duddysheet.io.xlsx_writer import write_xlsx

    workbook = build_practice_workbook()
    if workbook.get_sheet("Sales").get_cell(11, 5).display_value != 1635:
        raise AssertionError("table total row did not calculate")
    if workbook.get_sheet("Pivot").get_cell(7, 3).display_value != 1635:
        raise AssertionError("PivotTable grand total is wrong")
    payment = workbook.get_sheet("Loan").get_cell(8, 5).display_value
    if not isinstance(payment, float) or round(payment, 2) != 1342.05:
        raise AssertionError(f"data table returned {payment!r}")
    with tempfile.TemporaryDirectory() as directory:
        native = Path(directory) / "analysis.dsheet"
        save_native(workbook, native)
        reloaded = load_native(native)
        FormulaEngine(reloaded).recalculate()
        excel = Path(directory) / "analysis.xlsx"
        write_xlsx(workbook, excel)
        loaded = read_xlsx(excel)
    for copy, label in ((reloaded, ".dsheet"), (loaded.workbook, ".xlsx")):
        if not copy.get_sheet("Sales").tables or not copy.get_sheet("Pivot").pivots:
            raise AssertionError(f"{label} lost a table or PivotTable")
        if not copy.get_sheet("Loan").data_tables:
            raise AssertionError(f"{label} lost a data table")
    if loaded.warnings:
        raise AssertionError(f"xlsx round trip warned: {loaded.warnings}")
    return "tables, PivotTables, and data tables ok"


def _check_excel_objects() -> str:
    """Charts and sparklines are written as Excel objects and read back."""
    from duddysheet.core.chart import ChartSpec
    from duddysheet.core.engine import FormulaEngine
    from duddysheet.core.refs import parse_a1
    from duddysheet.core.sparkline import build_sparklines
    from duddysheet.core.workbook import Workbook
    from duddysheet.io.xlsx_reader import read_xlsx
    from duddysheet.io.xlsx_writer import write_xlsx

    workbook = Workbook()
    engine = FormulaEngine(workbook)
    sheet = workbook.active_sheet
    for row, values in enumerate((("Month", "Sales"), ("Jan", 4), ("Feb", 7), ("Mar", 5))):
        for column, value in enumerate(values):
            engine.set_cell(sheet.name, row, column, value)
    for chart_type in ("column", "pie", "histogram", "waterfall"):
        sheet.charts.append(ChartSpec(chart_type, sheet.name, parse_a1("A1:B4"), chart_type, title=chart_type))
    sheet.sparklines.extend(build_sparklines(parse_a1("B2:B4"), parse_a1("C1"), "line"))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "objects.xlsx"
        write_xlsx(workbook, path)
        loaded = read_xlsx(path).workbook.active_sheet
    kinds = [chart.chart_type for chart in loaded.charts]
    if kinds != ["column", "pie", "histogram", "waterfall"] or len(loaded.sparklines) != 1:
        raise AssertionError(f"xlsx objects came back as {kinds} and {len(loaded.sparklines)} sparklines")
    return "Excel charts and sparklines ok"


def _check_excel_parity() -> str:
    """A sample of results verified in Microsoft Excel, and its entry rules."""
    from duddysheet.core.entry_rules import validate_entry
    from duddysheet.core.evaluator import FormulaEvaluator
    from duddysheet.core.tokenizer import FormulaSyntaxError
    from duddysheet.core.workbook import Workbook

    samples = {
        "=ACCRINT(DATE(2025,1,1),DATE(2025,7,1),DATE(2026,1,1),0.06,1000,2,1)": 60.49723756906077,
        "=CEILING(-4.5,2)": -4,
        "=NPER(0.01,1,1)": -1,
        "=XLOOKUP(\"b\",{\"a\",\"b\",\"c\"},{10,20,30})": 20,
        "=FORECAST.ETS.SEASONALITY({1,2,3,4,1,2,3,4,1,2,3,4},{1,2,3,4,5,6,7,8,9,10,11,12})": 4,
    }
    evaluator = FormulaEvaluator(Workbook())
    for formula, expected in samples.items():
        actual = evaluator.evaluate(formula)
        if not isinstance(actual, (int, float)) or abs(actual - expected) > 1e-9 * max(1, abs(expected)):
            raise AssertionError(f"{formula} gave {actual!r}, Excel gives {expected!r}")
    try:
        validate_entry('=COUNTIF({1,2,3},">1")')
    except FormulaSyntaxError:
        pass
    else:
        raise AssertionError("a formula Excel refuses was accepted")
    return f"Excel parity ok ({len(samples)} samples)"


CHECKS: tuple[tuple[str, Callable[[], str]], ...] = (
    ("Bundled resources", _check_bundled_resources),
    ("Formula engine", _check_formula_engine),
    ("Excel parity", _check_excel_parity),
    ("Native file format", _check_native_round_trip),
    ("Excel interoperability", _check_xlsx_round_trip),
    ("Excel charts and sparklines", _check_excel_objects),
    ("Tables, PivotTables, data tables", _check_analysis_features),
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
