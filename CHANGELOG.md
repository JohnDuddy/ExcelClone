# Changelog

All notable changes follow Keep a Changelog conventions.

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
- 162 math, statistical, logical, text, lookup, date/time, financial, and
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
- Versioned `.ogrid` ZIP/JSON persistence with per-sheet payloads, typed scalar
  encoding, conditional formats, and an explicit migration registry.
- XLSX read/write for formulas, values, formats, merges, dimensions, sheet
  metadata, defined names, active sheet, and frozen panes.
- User-visible XLSX warnings for charts, images, pivots, tables, validations,
  comments, links, macros, and unsupported defined names that cannot round-trip.
- CSV and TSV import/export with delimiter, UTF-8/CP1252, scalar, formula, and
  optional date detection.
- File menu open/save workflows, dirty document titles, model-safe workbook
  replacement, and ten persisted recent files.

### Fixed

- Whole-row and whole-column references now ignore shifts along their fully
  spanned axis, preventing out-of-grid translation.
- Function-like identifiers such as `LOG10(` are no longer mistaken for A1 cell
  references.
- `NPER` now accepts valid same-sign logarithm terms while rejecting cash-flow
  sets that have no financial solution.
- Optional `#` integer placeholders now suppress insignificant zero values.
