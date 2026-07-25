# Engineering Decisions

## 2026-07-25 — Test seams

Core behavior is tested through public `Cell`, `Sheet`, `Workbook`, reference,
formula, and command interfaces. UI tests observe application and widget
behavior. This keeps Qt out of engine tests and allows internal implementations
to change without rewriting behavioral tests.

## 2026-07-25 — Dependency pin baseline

Runtime packages are pinned to versions verified importable under the required
Python 3.13.7 installation. Pytest is isolated in `requirements-dev.txt` because
it is a build-time verification tool, not a shipped runtime dependency.

## 2026-07-25 — Internal coordinates

Core coordinates are zero-based tuples. A1 and R1C1 text is converted only at
the reference seam. This aligns with Qt model indexes and avoids repeated
off-by-one conversion inside storage and recalculation code.

## 2026-07-25 — User-visible punctuation

The required title uses a Unicode em dash. Source otherwise remains ASCII where
there is no product-text reason to use Unicode.

## 2026-07-25 — Immutable cells

`Cell` and `CellFormat` are immutable values. A `Sheet` replaces cells rather
than exposing in-place mutation, which makes command undo state reliable and
prevents blank reads from accidentally allocating or modifying storage.

## 2026-07-25 — Lazy ranges

`RangeReference` is iterable but does not materialize its coordinates. This is
required because valid whole-column and whole-row references can contain more
than one million cells while the workbook itself remains sparse.

## 2026-07-25 — Formula AST and evaluation

Formula parsing produces immutable AST values. Evaluation retains references as
lazy `ReferenceValue` areas until a scalar or function explicitly requests
values. This preserves range identity for unions, intersections, dependency
extraction, and later dynamic-array behavior.

## 2026-07-25 — Large-range dependency watchers

Ranges up to 100,000 cells receive explicit graph edges. Larger whole-axis
ranges remain lazy and are checked by range watchers when a coordinate changes.
This keeps `A:A` dependencies correct without allocating one million graph
nodes per formula.

## 2026-07-25 — Spill ownership

Dynamic-array anchors retain their formula while child cells store cached values
and an immutable parent coordinate. Editing a child is rejected at the engine
interface. Blocked target cells are tracked so clearing a blocker automatically
recalculates the anchor.

## 2026-07-25 — Golden fixture provenance

`tests/fixtures/golden.xlsx` is generated from 200 formulas with independently
derived literal expectations, then opened, fully recalculated, and saved by the
locally installed Microsoft Excel. Tests require both the Excel cache and the
OpenGrid evaluator to match those literals.
