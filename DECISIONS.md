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
