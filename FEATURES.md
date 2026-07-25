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
- [x] Registered 162-function library with help metadata and per-function tests (`test_functions_all.py`, `test_function_edges.py`)
- [x] Dynamic-array spill ownership, blocking, and recovery (`test_spills.py`)
- [x] Volatile function recalculation (`test_spills.py`)
- [x] 200-case Microsoft Excel cached-value cross-check (`test_golden_workbook.py`)

## M5-M6 Grid And Formatting

- [x] Excel-sized virtualized editable grid and formula bar (`test_grid_model.py`, `test_ui_workflow.py`)
- [x] Selection summaries and TSV clipboard (`test_ui_workflow.py`)
- [x] Movable sheet-tab model with command-driven add/delete (`test_ui_workflow.py`, `test_commands.py`)
- [x] Command-based 200-level undo and redo (`test_commands.py`)
- [x] F4 absolute-reference cycling (`test_ui_workflow.py`)
- [x] Number formats, including four-section custom codes and Excel's 1900 leap-day behavior (`test_formats.py`)
- [x] Undoable fonts, fills, alignment, wrapping, and eight border styles (`test_commands.py`, `test_format_dialog.py`)
- [x] Conditional value, ranking, average, duplicate, formula, color-scale, data-bar, and icon rules (`test_conditional_formats.py`)
- [x] Delegate rendering and formula/gridline/zoom view controls (`test_grid_model.py`, `test_ui_workflow.py`)
- [x] Rich internal clipboard and Paste Special values/formulas/formats/transpose (`test_fill_and_paste.py`, `test_ui_workflow.py`)
- [x] Numeric/date/weekday/month/formula fill plus Ctrl+D/Ctrl+R (`test_fill_and_paste.py`)
- [x] Merge cells, row heights, column widths, and autofit command paths (`test_commands.py`)
- [x] Mouse fill handle, visible frozen panes, and split views (`test_polish_ui.py`)

## M7-M9 Data And Visualization

- [x] Lossless versioned OGrid ZIP/JSON round trips (`test_native_io.py`)
- [x] XLSX values, formulas, styles, merges, dimensions, sheets, names, and frozen-pane round trips (`test_io_roundtrip.py`)
- [x] Explicit XLSX dropped-feature warnings (`test_io_roundtrip.py`)
- [x] CSV/TSV encoding, delimiter, scalar/date detection, and export (`test_csv_io.py`)
- [x] File menu workflow and persisted ten-item recent-files list (`test_ui_workflow.py`, `test_settings.py`)
- [x] Reference-safe row/column insert-delete with atomic undo (`test_structural_commands.py`, `test_translation.py`)
- [x] Multi-key sort and value-list autofilter (`test_data_tools.py`, `test_data_dialogs.py`)
- [x] Find/replace with value/formula, regex, case, and whole-cell scope (`test_data_tools.py`)
- [x] List, numeric, date, length, and custom-formula validation (`test_data_tools.py`, `test_grid_model.py`)
- [x] Remove duplicates and text-to-columns (`test_data_tools.py`, `test_commands.py`)
- [x] Sheet rename/move/duplicate/hide/tab-color commands (`test_commands.py`)
- [x] Undo restores exact state across 50 mixed operations (`test_commands.py`)
- [x] Column, bar, line, pie, scatter, area, and combo charts (`test_chart_ui.py`)
- [x] Range-bound chart data live-updates after recalculation/edit (`test_charts.py`, `test_chart_ui.py`)
- [x] Chart wizard, movable panels, and PNG export (`test_chart_ui.py`)
- [x] Undoable chart add/remove and OGrid persistence (`test_charts.py`, `test_native_io.py`)

## M10 Distribution

- [x] Autosave, crash recovery, rotating logs, and performance targets (`test_autosave.py`, `test_performance.py`, `test_polish_ui.py`)
- [x] Idempotent offline Windows installer and desktop shortcut (`test_distribution.py`)
- [x] Self-contained `dist/ExcelClone.zip` (`test_distribution.py`, clean-install acceptance)
