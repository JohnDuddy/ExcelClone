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

### Fixed

- Whole-row and whole-column references now ignore shifts along their fully
  spanned axis, preventing out-of-grid translation.
