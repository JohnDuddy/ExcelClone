# Testing

Tests specify behavior at the public module seams documented in `AGENTS.md`.
Headless engine tests never construct a `QApplication`. UI tests set
`QT_QPA_PLATFORM=offscreen` before importing Qt-facing modules.

## Run

```powershell
python -W error -m pytest
python -W error -m pytest -m "not performance" --cov=excelclone.core --cov-report=term-missing
python -m pytest tests/test_performance.py
```

The coverage gate applies once the core engine exists. Performance tests are
marked `performance` and remain part of the full release verification. They run
without coverage instrumentation because tracing changes the wall-clock result.

## Test Rules

- Use known literals or independent fixtures for expected values.
- Exercise public interfaces, not private helpers.
- Add a regression test before implementing every bug fix.
- Keep each red-green slice narrow enough that a failed assertion identifies one
  behavior.
- Re-run the complete suite before checking a capability in `FEATURES.md`.

## Golden Workbook

The M4 fixture `tests/fixtures/golden.xlsx` contains 200 formula cases and cached
values calculated by Microsoft Excel. Each case records the source formula,
input cells, expected value, and comparison tolerance. New cases must be
calculated in Excel rather than derived by the OpenGrid evaluator.

## File Round Trips

`test_native_io.py` compares all serialized domain fields and inspects the ZIP
manifest. `test_io_roundtrip.py` writes XLSX through OpenPyXL, reads it back
through the adapter, recalculates formulas, and independently reopens the file
with OpenPyXL. `test_csv_io.py` verifies raw bytes where newline or encoding
behavior matters.

`test_hyperlinks.py` creates only synthetic external and internal links. It
verifies XLSX and OGrid round trips, rich clipboard preservation, link styling,
external activation requests, internal navigation, and removal after editing.

## Structural And Data Operations

Translation tests inspect parsed references rather than depending only on
formula spelling. Structural command tests cover cross-sheet recalculation,
range growth/shrinkage, deleted-reference errors, and metadata movement. A
mixed-operation regression executes and undoes 50 edits including inserts,
deletes, ranges, and rich pastes.

## Charts

Headless tests prove category/series extraction, missing-value gaps,
contiguous-range expansion, header detection, explainable recommendation
ranking, live value changes, and undoable chart updates. Qt tests render all 17
chart types offscreen under warnings-as-errors, export PNG/SVG/PDF, validate
Chart Studio controls and preview, exercise one-click Quick Chart, and inspect a
bar height before and after a grid edit to prove panel refresh behavior.

## Financial Modeling

`test_financial_functions.py` checks known results and cross-function identities
such as price/yield round trips and cumulative payment decomposition.
`test_financial_analysis.py` verifies Goal Seek, scenarios, sensitivity tables,
audit ordering, and source-workbook immutability. `test_financial_models.py`
recalculates every built-in model, rejects formula errors, validates integrity
checks, confirms primary outputs, and verifies the Financial Calculations Lab's
76 calculations, 12 chart datasets, and native round trip. Qt tests cover
dialog parsing, Financial ribbon exposure, model installation, and undoable
table output.
`test_financial_help.py` requires every registered financial function to have
detailed curated help and a parseable example; UI tests cover search, category
filters, tutorials, quick-reference content, model guidance, clipboard copying,
F1, and Help/ribbon discoverability.

`backtest_financial.py` exports representative formulas and all seven generated
models, recalculates them through desktop Microsoft Excel, and compares cached
results cell by cell:

```powershell
python backtest_financial.py --output outputs\financial-backtest-final.md
```

## Distribution Acceptance

`test_distribution.py` validates ICO frames, required package inputs, offline
pip flags, and direct shortcut configuration. Release verification additionally
builds the ZIP, extracts it to a clean directory, runs `install.ps1` against a
temporary Desktop folder, inspects the resulting `.lnk`, launches the app with
`pythonw.exe`, and round-trips a formatted 50,000-cell XLSX.
