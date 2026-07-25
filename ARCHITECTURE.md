# Architecture

OpenGrid separates spreadsheet behavior from its desktop presentation. The core
is a deep module: callers learn a small workbook interface while parsing,
dependency tracking, recalculation, spill management, and formatting remain
local to its implementation.

## Data Flow

```text
User gesture
    |
    v
Qt view/model -----> Command interface -----> Workbook / Sheet
    ^                                             |
    |                                             v
    +---------- display values <---------- Recalculation engine
                                                  |
Disk dialogs -> I/O adapter <---------------------+
```

Qt types stop at the UI seam. File-format types stop at the I/O seam. Core
objects never import either.

## Recalculation

The formula parser will expose cell and range precedents while building an AST.
On edit, the dependency graph replaces the edited cell's incoming edges, marks
its transitive dependents dirty, detects cycles, and evaluates the affected
subgraph in topological order. Cached values make display reads constant-time.
Volatile cells are added to every recalculation pass.

## Commands

Every mutation is represented by a command with `do`, `undo`, and optional
`merge_with` behavior. Commands retain only the prior state required to reverse
their own mutation. The UI submits commands to a bounded history rather than
editing a sheet directly, giving the same seam to toolbar actions, keyboard
editing, paste, sorting, and tests.

## Performance Shape

Sheets allocate cells only when content or non-default formatting exists. The Qt
model advertises Excel-sized dimensions without materializing them. Dependency
edges and cached formula values scale with populated and referenced cells.

