# Changelog

All notable changes follow Keep a Changelog conventions.

## [1.0.0] - 2026-07-27

First commercial release, as Duddy Spreadsheet.

### Added

- Printing, page setup, print preview, and print areas, with repeating title
  rows and columns, fit-to-page scaling, gridlines, headings, page order, and
  header/footer tokens. Page setup is saved with the workbook.
- Worksheet PDF export that works without printer drivers installed.
- Offline Ed25519 licence keys, a thirty-day trial, and an activation dialog.
- Commercial LICENSE, EULA, privacy statement, and third-party notices, with
  an in-application About dialog disclosing Qt's LGPL terms.
- Windows installer built with PyInstaller and Inno Setup, with code signing
  hooks and file associations.
- `--self-test` verification that runs inside the packaged application.
- `tools/release_check.py`, `tools/collect_licenses.py`, `tools/licence_admin.py`,
  and `tools/build_release.py`.
- `PACKAGING.md` release runbook and `GO-TO-MARKET.md` commercial plan.

### Changed

- Renamed from OpenGrid/ExcelClone to Duddy Spreadsheet; the Python package is
  now `duddysheet` and all product identity comes from `duddysheet/branding.py`.
- The native extension is now `.dsheet`. Existing `.ogrid` files still open.
- Native schema raised to 3 to carry page setup, with a migration from 2.
- Ships PySide6-Essentials instead of PySide6, taking the installed Qt
  footprint from 636 MB to 202 MB.

### Removed

- The wheelhouse ZIP distribution and its `INSTALL.bat` and `install.ps1`
  scripts, which required customers to install Python themselves. The signed
  installer replaces them.
- Qt's software OpenGL fallback and networking library from the shipped build.

## [Unreleased]

### Added

- Repository structure and standing documentation.
- Pinned Python 3.13 runtime and development dependencies.
- Side-effect-free application factory and launchable PySide6 main window.
- Offscreen application-shell regression test.
- Immutable cell and formatting values with sparse Excel-sized sheet storage.
- Ordered multi-sheet workbooks with active-sheet state and scoped defined names.
- A1 and R1C1 parsing, rendering, validation, lazy ranges, and mixed-reference
  translation.
- Formula lexer, recursive-descent parser, and immutable expression tree.
- Excel-style formula error values, type coercion, reference intersections and
  unions, arrays, comparisons, and 1900-system date serials.
- Bidirectional dependency graph with affected-subgraph recalculation,
  cross-sheet edges, range watchers, and deterministic cycle detection.
- Formula function registry with help metadata, arity, volatility, and lazy-call
  support.
- 196 math, statistical, logical, text, lookup, date/time, financial, and
  information functions.
- Lazy error-handling functions and volatile random, date/time, offset, and
  indirect functions.
- Dynamic-array spilling with read-only child ownership, blocker detection,
  `#SPILL!`, automatic recovery, and cleanup.
- A 200-formula golden workbook recalculated and cached by Microsoft Excel.
- Excel-sized `QAbstractTableModel` and `QTableView` backed by sparse sheets.
- Formula bar with name-box navigation and F4 absolute-reference cycling.
- Grid editing, selection statistics, keyboard undo/redo, and TSV clipboard
  interoperability.
- Tabbed ribbon shell and movable workbook sheet tabs.
- Reversible command history with a 200-entry limit, adjacent edit merging,
  atomic range edits, and sheet add/delete/rename restoration.
- Headless Excel-style number formatting with named presets, date/time serials,
  custom placeholders, four-section selection, scaling, literals, and colors.
- Immutable range-format commands and a multi-tab Format Cells dialog covering
  fonts, fills, alignment, wrapping, and eight border styles.
- Conditional formatting for value comparisons, rankings, averages,
  duplicates, formulas, color scales, data bars, and icon sets.
- A cell delegate for borders and conditional visuals, plus formula-view,
  gridline, zoom, and freeze-pane metadata controls.
- AST-level mixed-reference translation used by range-relative conditional
  formulas.
- Versioned `.dsheet` ZIP/JSON persistence with per-sheet payloads, typed scalar
  encoding, conditional formats, and an explicit migration registry.
- XLSX read/write for formulas, values, formats, merges, dimensions, sheet
  metadata, defined names, active sheet, and frozen panes.
- User-visible XLSX warnings for charts, images, pivots, tables, validations,
  comments, links, macros, and unsupported defined names that cannot round-trip.
- CSV and TSV import/export with delimiter, UTF-8/CP1252, scalar, formula, and
  optional date detection.
- File menu open/save workflows, dirty document titles, model-safe workbook
  replacement, and ten persisted recent files.
- AST rendering and reference translation for copy/fill, row/column
  insertion/deletion, range shrink/expansion, `#REF!`, and sheet renames.
- Atomic row/column structural commands that move sparse cells and metadata,
  update cross-sheet formulas, and rebuild dependencies.
- Multi-key sorting, value-list filters, find/replace scopes, data validation,
  duplicate removal, and text-to-columns as headless data services.
- Rich internal clipboard cells and Paste Special for all content, values,
  formulas, formats, and transpose.
- Numeric, date, weekday, month, and formula fill with Ctrl+D/Ctrl+R support.
- Command-driven merges, dimensions, sheet move/rename/duplicate/visibility/tab
  color, and a 50-operation mixed undo regression.
- XLSX and Duddy Spreadsheet persistence for autofilter and data-validation state.
- Immutable range-bound chart specifications and headless category/series
  extraction from current formula caches.
- Movable/resizable analytical chart panels with 17 chart types, including
  stacked, histogram, box, waterfall, heatmap, radar, donut, and combo views.
- Deterministic chart recommendations, contiguous-table discovery, one-click
  Quick Chart, and a live-preview Chart Studio.
- Five professional themes, data labels, trendlines, extrema highlighting,
  secondary-axis combos, zoom/pan, clipboard copy, and PNG/SVG/PDF export.
- Live chart refresh after edits, command changes, recalculation, sheet
  switches, and workbook loads.
- Undoable chart add/update/remove, structural range translation, sheet-rename
  translation, and complete native Duddy Spreadsheet chart persistence.
- Five-minute dirty-workbook autosave, recover/discard startup flow, and
  rotating `%LOCALAPPDATA%` diagnostics.
- Real frozen-row, frozen-column, and corner overlays plus a synchronized
  two-pane worksheet split view.
- Mouse fill-handle painting, drag preview, series/formula extension, and
  command-based undo.
- Searchable metadata-driven help and insertion for all 196 functions.
- Programmatically generated 16/32/48/256 Windows grid icon.
- Idempotent PowerShell installer with Python 3.13 discovery, isolated virtual
  environment, offline wheel installation, smoke test, and direct
  `pythonw.exe` Desktop shortcut.
- Self-contained `dist/DuddySpreadsheet.zip` with all Windows runtime wheels.
- External HTTPS/file/mail links and internal workbook-location links as
  immutable cell metadata, including clickable grid presentation, native and
  XLSX round trips, rich clipboard copies, and internal navigation.
- A 46-function financial library spanning annuities, cumulative loan cash
  flows, periodic and irregular returns, rate conversion, depreciation,
  coupon schedules, bond price/yield/duration, discount securities, Treasury
  bills, and fractional-dollar quotations.
- Clone-based Goal Seek, named scenario evaluation, one- and two-variable
  sensitivity tables, and a prioritized financial-model audit.
- Seven built-in editable financial workbooks: DCF, three-statement forecast,
  LBO, full-term loan amortization, rental property, budget/forecast, and an
  eight-sheet Financial Calculations Lab with 76 live examples and 12 charts.
- A Financial ribbon/menu with validated dialogs, confirmed Goal Seek writes,
  undoable analysis tables, and dirty-workbook protection during model
  creation.
- Comprehensive offline financial help for all 46 functions with searchable
  categories, copyable examples, nine modeling tutorials, sign/rate/day-count
  references, troubleshooting, model instructions, F1, and Help/ribbon access.
- Measured release targets: 1.12 s cold launch, 0.78 s 50,000-cell XLSX load,
  0.65 s 100,000-row scroll simulation, under 0.30 s 10,000-cell incremental
  chain recalculation, 3.83 s 100,000-formula full recalculation, and 0.18 s
  10,000-cell paste undo.

### Fixed

- Bond `PRICE` calculations now match Excel's day-count behavior for all five
  bases, including the distinct Actual/Actual `COUPDAYS` convention.
- Fractional-period `VDB` calculations now reproduce Excel's switching
  behavior, and XLSX files translate `RRI`/`PDURATION` through the required
  `_xlfn.` storage prefix without exposing it inside Duddy Spreadsheet.
- The built-in LBO model now calculates IRR from a normal cash-flow range
  instead of an array constant containing references, so exported LBO
  workbooks open and recalculate in Microsoft Excel.

- XLSX hyperlinks are no longer reported and discarded during import; external
  links open with the Windows default handler and internal links select their
  workbook destination.

- Whole-row and whole-column references now ignore shifts along their fully
  spanned axis, preventing out-of-grid translation.
- Function-like identifiers such as `LOG10(` are no longer mistaken for A1 cell
  references.
- `NPER` now accepts valid same-sign logarithm terms while rejecting cash-flow
  sets that have no financial solution.
- Optional `#` integer placeholders now suppress insignificant zero values.
