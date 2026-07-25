# Feature Regression Contract

A checked capability is shipped behavior and must remain covered by the named
test. Unchecked capabilities are scheduled and must not be represented as
complete.

## M1 Skeleton

- [x] Application package imports without creating a GUI (`test_app_smoke.py`)
- [x] Application factory returns a reusable `QApplication` (`test_app_smoke.py`)
- [x] Main window uses the OpenGrid product title (`test_app_smoke.py`)
- [x] Main window provides a usable minimum desktop size (`test_app_smoke.py`)

## M2 Core Model

- [x] Sparse immutable cell storage (`test_sheet.py`)
- [x] Multi-sheet workbook and scoped named ranges (`test_workbook.py`)
- [x] A1, absolute, range, whole-row, whole-column, and R1C1 references (`test_refs.py`)
- [x] Lazy range iteration and reference translation (`test_refs.py`)

## M3-M4 Formula Engine

- [x] Tokenizer and recursive-descent parser with documented precedence (`test_tokenizer.py`, `test_parser.py`)
- [x] AST evaluator with coercion, references, arrays, and Excel date serials (`test_evaluator.py`)
- [x] Incremental bidirectional dependency graph (`test_depgraph.py`, `test_formula_engine.py`)
- [x] Circular-reference and formula-error behavior (`test_formula_engine.py`, `test_evaluator.py`)
- [ ] Registered 120-function library
- [ ] Dynamic-array spill behavior

## M5-M6 Grid And Formatting

- [ ] Virtualized editable grid and formula bar
- [ ] Command-based undo and redo
- [ ] Fill, clipboard, sheet tabs, formatting, freeze panes, and views
- [ ] Number and conditional-format engines

## M7-M9 Data And Visualization

- [ ] XLSX, CSV, TSV, and OGrid round trips
- [ ] Sort, filter, validation, find/replace, and paste special
- [ ] Live range-bound charts

## M10 Distribution

- [ ] Autosave, crash recovery, and performance targets
- [ ] Idempotent Windows installer and desktop shortcut
- [ ] Self-contained `dist/ExcelClone.zip`
