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

### Fixed

- Whole-row and whole-column references now ignore shifts along their fully
  spanned axis, preventing out-of-grid translation.
