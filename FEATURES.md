# Feature Regression Contract

A checked capability is shipped behavior and must remain covered by the named
test. Unchecked capabilities are scheduled and must not be represented as
complete.

## M1 Skeleton

- [x] Application package imports without creating a GUI (`test_app_smoke.py`)
- [x] Application factory returns a reusable `QApplication` (`test_app_smoke.py`)
- [x] Main window uses the Duddy Spreadsheet product title (`test_app_smoke.py`)
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
- [x] Registered 196-function library with help metadata and per-function tests (`test_functions_all.py`, `test_function_edges.py`, `test_financial_functions.py`)
- [x] Dynamic-array spill ownership, blocking, and recovery (`test_spills.py`)
- [x] Volatile function recalculation (`test_spills.py`)
- [x] 200-case Microsoft Excel cached-value cross-check (`test_golden_workbook.py`)

## M5-M6 Grid And Formatting

- [x] Excel-sized virtualized editable grid and formula bar (`test_grid_model.py`, `test_ui_workflow.py`)
- [x] Selection summaries and TSV clipboard (`test_ui_workflow.py`)
- [x] Movable sheet-tab model with command-driven add/delete (`test_ui_workflow.py`, `test_commands.py`)
- [x] Command-based 200-level undo and redo (`test_commands.py`)
- [x] F4 absolute-reference cycling (`test_ui_workflow.py`)
- [x] Function-name autocomplete while typing a formula, in the grid and the formula bar (`test_function_autocomplete.py`)
- [x] Step-wise argument guide that emphasizes the field being typed and follows nested calls (`test_function_autocomplete.py`)
- [x] Number formats, including four-section custom codes and Excel's 1900 leap-day behavior (`test_formats.py`)
- [x] Undoable fonts, fills, alignment, wrapping, and eight border styles (`test_commands.py`, `test_format_dialog.py`)
- [x] Conditional value, ranking, average, duplicate, formula, color-scale, data-bar, and icon rules (`test_conditional_formats.py`)
- [x] Delegate rendering and formula/gridline/zoom view controls (`test_grid_model.py`, `test_ui_workflow.py`)
- [x] Rich internal clipboard and Paste Special values/formulas/formats/transpose (`test_fill_and_paste.py`, `test_ui_workflow.py`)
- [x] Numeric/date/weekday/month/formula fill plus Ctrl+D/Ctrl+R (`test_fill_and_paste.py`)
- [x] Merge cells, row heights, column widths, and autofit command paths (`test_commands.py`)
- [x] Mouse fill handle, visible frozen panes, and split views (`test_polish_ui.py`)

## M7-M9 Data And Visualization

- [x] Lossless versioned Duddy Spreadsheet ZIP/JSON round trips (`test_native_io.py`)
- [x] XLSX values, formulas, styles, merges, dimensions, sheets, names, and frozen-pane round trips (`test_io_roundtrip.py`)
- [x] External and internal XLSX hyperlinks, clickable grid styling, navigation, native persistence, and rich clipboard preservation (`test_hyperlinks.py`)
- [x] Explicit XLSX dropped-feature warnings (`test_io_roundtrip.py`)
- [x] CSV/TSV encoding, delimiter, scalar/date detection, and export (`test_csv_io.py`)
- [x] File menu workflow and persisted ten-item recent-files list (`test_ui_workflow.py`, `test_settings.py`)
- [x] Startup workbook from the command line via `--open PATH` or a bare path (`test_app_smoke.py`)
- [x] Reference-safe row/column insert-delete with atomic undo (`test_structural_commands.py`, `test_translation.py`)
- [x] Multi-key sort and value-list autofilter (`test_data_tools.py`, `test_data_dialogs.py`)
- [x] Find/replace with value/formula, regex, case, and whole-cell scope (`test_data_tools.py`)
- [x] List, numeric, date, length, and custom-formula validation (`test_data_tools.py`, `test_grid_model.py`)
- [x] Remove duplicates and text-to-columns (`test_data_tools.py`, `test_commands.py`)
- [x] Sheet rename/move/duplicate/hide/tab-color commands (`test_commands.py`)
- [x] Undo restores exact state across 50 mixed operations (`test_commands.py`)
- [x] Seventeen chart types including stacked, histogram, box, waterfall, heatmap, radar, donut, and combo charts (`test_chart_ui.py`)
- [x] Range-bound chart data live-updates after recalculation/edit (`test_charts.py`, `test_chart_ui.py`)
- [x] Ranked chart recommendations, contiguous-range expansion, Quick Chart, and live-preview Chart Studio (`test_charts.py`, `test_chart_ui.py`)
- [x] Professional themes, labels, trendlines, extrema, secondary axes, zoom/pan, clipboard copy, and PNG/SVG/PDF export (`test_chart_ui.py`)
- [x] Undoable chart add/update/remove and complete Duddy Spreadsheet persistence (`test_charts.py`, `test_native_io.py`)

## M10 Distribution

- [x] Autosave, crash recovery, rotating logs, and performance targets (`test_autosave.py`, `test_performance.py`, `test_polish_ui.py`)
- [x] Idempotent offline Windows installer and desktop shortcut (`test_distribution.py`)
- [x] Self-contained `dist/DuddySpreadsheet.zip` (`test_distribution.py`, clean-install acceptance)

## M11 Financial Modeling

- [x] 46-function financial library covering loans, cash flows, rates, depreciation, coupon securities, discount securities, and Treasury bills (`test_functions_all.py`, `test_financial_functions.py`)
- [x] Non-mutating Goal Seek with optional bracketed solve and confirmed undoable application (`test_financial_analysis.py`, `test_financial_ui.py`)
- [x] Named scenario analysis and one-/two-variable sensitivity tables calculated on workbook clones (`test_financial_analysis.py`)
- [x] Formula-error, circular, blank-precedent, stale-cache, and embedded-constant model audit (`test_financial_analysis.py`, `test_financial_ui.py`)
- [x] Editable DCF, three-statement, LBO, loan, rental-property, and budget/forecast models with live outputs and checks (`test_financial_models.py`)
- [x] Eight-sheet Financial Calculations Lab with all 46 financial functions, 30 common metrics, synthetic inputs, and 12 editable charts (`test_financial_models.py`)
- [x] Financial ribbon/menu, validated dialogs, undoable output tables, and dirty-workbook template replacement warning (`test_financial_ui.py`)
- [x] F1 offline financial help with complete 46-function coverage, searchable categories, copyable examples, twelve tutorials, quick reference, model instructions, and Help/ribbon access (`test_financial_help.py`, `test_financial_ui.py`)
- [x] Step-by-step tutorial for every Financial menu command, each with a worked example verified against a built-in model (`test_financial_tutorials.py`)
- [x] Hover bubbles and status-bar text on every Financial menu command and ribbon button, with worked examples (`test_financial_tool_help.py`)

## M13 Excel Charting Parity

- [x] 62 chart types covering every Excel chart family except Map, including 100% stacked, 3-D, stock, surface, treemap, sunburst, Pareto, funnel, and custom combo charts (`test_chart_catalog.py`, `test_chart_ui.py`)
- [x] Every chart type renders with every chart element and format option enabled, warning-free (`test_chart_studio.py`)
- [x] Chart elements: axes, titles, three gridline kinds, positioned data labels with five content choices, data table, error bars, trendlines, drop lines, high-low lines, up/down bars (`test_chart_studio.py`)
- [x] Excel-accurate trendline fits, equations, R-squared, forecasts, moving averages, and error-bar amounts (`test_chart_catalog.py`)
- [x] Axis bounds, major unit, log scale, display units, reverse order, color schemes, gap width, overlap, pie and doughnut options, histogram bins, Switch Row/Column, empty-cell modes (`test_chart_catalog.py`, `test_chart_studio.py`)
- [x] Treemap and sunburst hierarchies from level columns, with squarified layout (`test_chart_catalog.py`)
- [x] Chart Studio round-trips every option when editing and keeps the chart's own type (`test_chart_studio.py`)
- [x] Insert menu and ribbon chart galleries insert any chart type from the selection, undoably (`test_chart_studio.py`)
- [x] Line, Column, and Win/Loss sparklines: creation, replacement, clearing, undo, structural translation, sheet rename, live values, painting, and native persistence (`test_sparklines.py`)
- [x] Native schema 4 with lossless chart options and a migration from schema 3 (`test_chart_studio.py`)
- [x] Help > Charts and Graphing Tutorial with 25 searchable lessons, a generated reference for every chart type, and context help from Chart Studio and chart windows (`test_chart_studio.py`)

## M12 Commercial Readiness

- [x] Printing with page setup, print preview, and print areas (`test_printing.py`, `test_printing_ui.py`)
- [x] Deterministic Qt-free pagination shared by preview, printer, and PDF (`test_printing.py`)
- [x] Repeating title rows/columns, fit-to-page scaling, gridlines, headings, and page order (`test_printing.py`)
- [x] Header/footer token expansion (`test_printing.py`)
- [x] Worksheet PDF export without printer drivers (`test_printing_ui.py`)
- [x] Page setup persisted in the native format under schema 3 (`test_printing_ui.py`)
- [x] Ed25519 licence keys verified offline, rejecting forged, tampered, foreign, and malformed keys (`test_licensing.py`)
- [x] Thirty-day trial with signed state, resisting file edits and clock rollback (`test_licensing.py`)
- [x] Activation dialog and entitlement status indicator (`test_licensing.py`)
- [x] Commercial licence, EULA, privacy statement, and third-party notices (`test_licensing_compliance.py`)
- [x] In-application Qt/LGPL disclosure and licence browser (`test_licensing_compliance.py`)
- [x] PySide6-Essentials-only Qt surface enforced by test (`test_distribution.py`)
- [x] PyInstaller onedir freeze and Inno Setup installer configuration (`test_distribution.py`)
- [x] Packaged-build self-test covering formulas, both file formats, models, charts, PDF, and licensing (`duddysheet/selftest.py`)
- [x] Release checks blocking a placeholder signing key or missing licence texts (`test_distribution.py`, `test_licensing_compliance.py`)
