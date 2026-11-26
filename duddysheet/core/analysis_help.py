"""Directions for Excel Tables, PivotTables, and What-If data tables.

Each lesson is plain data (title, purpose, steps, example, tips) so the Help
dialog, tests, and documentation all draw on one source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape
from typing import Any


@dataclass(frozen=True, slots=True)
class Lesson:
    """One tutorial topic."""

    key: str
    section: str
    title: str
    purpose: str
    steps: tuple[str, ...]
    example: tuple[str, ...] = ()
    tips: tuple[str, ...] = ()


LESSONS: tuple[Lesson, ...] = (
    # ------------------------------------------------------------ tables
    Lesson(
        "table-create",
        "Excel Tables",
        "Create a table",
        "Turn a list with a header row into a table that formats itself, grows as you add data, and can be referred to by name.",
        (
            "Click any cell inside your list (the list needs one header row).",
            "Press Ctrl+T (or Ctrl+L), or choose Insert > Table.",
            "Check the range in Create Table. Keep 'My table has headers' ticked if the first row holds column names; untick it and a header row named Column1, Column2, ... is inserted above.",
            "Click OK. The table gets a name (Table1, Table2, ...), banded rows, and a styled header.",
        ),
        (
            "A1: Product   B1: Qty   C1: Price",
            "A2: Apple     B2: 3     C2: 1.50",
            "A3: Pear      B3: 2     C3: 2.00",
            "Select A1, press Ctrl+T, click OK: A1:C3 becomes Table1.",
        ),
        ("Tables can't overlap other tables, PivotTables, or merged areas.",),
    ),
    Lesson(
        "table-references",
        "Excel Tables",
        "Structured references",
        "Refer to table parts by name instead of cell addresses, so formulas keep working when the table grows.",
        (
            "Table1[Qty] means every data cell of the Qty column.",
            "[@Qty] (inside the table) means the Qty cell in the same row as the formula; outside a table write Table1[@Qty] or Table1[[#This Row],[Qty]].",
            "Table1[#Headers], Table1[#Data], Table1[#Totals], and Table1[#All] mean the header row, the data rows, the total row, and everything.",
            "Table1[[Qty]:[Price]] spans adjacent columns; Table1[[#Headers],[Price]] is one header cell.",
            "Names with spaces or special characters go in brackets: Table1[[Unit Price]] or [@[Unit Price]].",
        ),
        (
            "=SUM(Table1[Qty])          total quantity",
            "=[@Qty]*[@Price]           line amount on each row",
            "=ROWS(Table1)              number of data rows",
            "=XLOOKUP(\"Pear\",Table1[Product],Table1[Price])",
        ),
        ("Structured references are saved to .xlsx in Excel's own form, so Excel reads them unchanged.",),
    ),
    Lesson(
        "table-calculated",
        "Excel Tables",
        "Calculated columns",
        "Type one formula and the whole column fills itself, including rows added later.",
        (
            "Type a heading in the first empty column to the right of the table (for example Amount in D1). The table grows to include it.",
            "In the first data row of that column type a formula such as =[@Qty]*[@Price] and press Enter.",
            "Because the rest of the column was empty, the formula fills every row: it is now a calculated column.",
            "New rows typed below the table, and rows inserted inside it, receive the same formula automatically.",
        ),
        ("D1: Amount", "D2: =[@Qty]*[@Price]  -> fills D2:D3 with 4.5 and 4"),
        ("If the column already has values, the formula affects only the cell you typed in, as in Excel.",),
    ),
    Lesson(
        "table-totals",
        "Excel Tables",
        "Total row",
        "Add a row at the bottom that sums, averages, or counts columns and ignores filtered-out rows.",
        (
            "Click inside the table and choose Data > Table > Total Row.",
            "A Total row appears below the data; the last column gets =SUBTOTAL(109,[Column]) (a sum).",
            "To change a column's total, click a cell in that column and choose Data > Table > Total Function, then None, Average, Count, Count Numbers, Max, Min, Sum, StdDev, or Var.",
            "Turn the total row off the same way. Totals use SUBTOTAL, so rows hidden by a filter are left out.",
        ),
        ("Data > Table > Total Row on Table1 adds row 4: 'Total' in A4 and =SUBTOTAL(109,[Price]) in C4.",),
    ),
    Lesson(
        "table-grow",
        "Excel Tables",
        "Growing and resizing a table",
        "Keep data in the table as it changes.",
        (
            "Type in the row just below the table: the table expands to include the new row (AutoExpansion).",
            "Type in the column just to the right: the table gains a column with that header.",
            "Insert rows or columns inside the table (Ctrl+Shift+= or Home > Insert): the table grows and calculated columns fill the new rows.",
            "To set the size exactly, choose Data > Table > Resize Table and enter the new range; the header row must stay where it is.",
        ),
    ),
    Lesson(
        "table-options",
        "Excel Tables",
        "Styles, options, renaming, and converting",
        "Change how a table looks and behaves.",
        (
            "Data > Table > Table Style picks Light, Medium, or Dark styles (Medium 2 is Excel's default).",
            "Toggle Banded Rows, Banded Columns, First Column, Last Column, and Filter Button in Data > Table.",
            "Data > Table > Table Name renames the table; every formula that used the old name is updated.",
            "Data > Table > Convert to Range keeps the cells and their current look but removes the table; structured references stop working, so convert formulas first if needed.",
            "Data > Table > Summarize with PivotTable builds a PivotTable whose source is the table and grows with it.",
        ),
    ),
    # ------------------------------------------------------------ pivots
    Lesson(
        "pivot-create",
        "PivotTables",
        "Create a PivotTable",
        "Summarize thousands of rows into totals by category, in seconds, without formulas.",
        (
            "Click inside a list with a header row (or an Excel Table).",
            "Choose Insert > PivotTable.",
            "Check Table/Range. Enter a table name (Table1) to make the PivotTable follow the table as it grows.",
            "Choose New Worksheet (the report starts at A3) or Existing Worksheet and type a location such as H2.",
            "Click OK. The PivotTable Fields dialog opens so you can choose what to summarize.",
        ),
        (
            "Region | Product | Date | Sales",
            "East   | Apple   | 1/5/2024 | 100",
            "Insert > PivotTable > OK, then tick Region and Sales: one row per region with Sum of Sales.",
        ),
    ),
    Lesson(
        "pivot-fields",
        "PivotTables",
        "The four field areas",
        "Decide what the report groups by and what it adds up.",
        (
            "Rows: each distinct item becomes a row (put Region here for one row per region). Several row fields nest: Region, then Product inside each region.",
            "Columns: items become columns (put Date grouped by Years here to compare years side by side).",
            "Values: the numbers to summarize. Numeric fields are summed; text fields are counted.",
            "Filters: a report filter above the table limits the whole report to chosen items.",
            "Tick a field to add it (text goes to Rows, numbers to Values), or select a field and click Add to Filters/Columns/Rows/Values. Use Up, Down, and Remove to rearrange.",
            "Click OK to rebuild the report.",
        ),
        ("Rows: Region, Product   Columns: Date (Years)   Values: Sum of Sales",),
    ),
    Lesson(
        "pivot-values",
        "PivotTables",
        "Value Field Settings",
        "Change how values are summarized and shown.",
        (
            "In PivotTable Fields select a field in Values and click Value Field Settings.",
            "Summarize value field by: Sum, Count, Average, Max, Min, Product, Count Numbers, StdDev, StdDevp, Var, or Varp.",
            "Show values as: No Calculation, % of Grand Total, % of Column Total, % of Row Total, or Running Total.",
            "Give the field a custom name and a number format such as $#,##0 or 0.0%.",
            "Add the same field twice to show, for example, Sum of Sales and % of Grand Total side by side.",
        ),
    ),
    Lesson(
        "pivot-filter",
        "PivotTables",
        "Filtering and grouping",
        "Focus the report and roll dates up into years, quarters, or months.",
        (
            "Select a field in Rows, Columns, or Filters and click Filter Items. Untick the items to hide and click OK.",
            "A field in the Filters area shows (All), the single chosen item, or (Multiple Items) above the report.",
            "Select a date field in Rows or Columns and choose Years, Quarters, Months, or Days in the grouping box. Dates may be real dates or date-formatted numbers.",
        ),
    ),
    Lesson(
        "pivot-layout",
        "PivotTables",
        "Layout, subtotals, and grand totals",
        "Choose how nested row fields are laid out.",
        (
            "Compact Form (default): all row fields share one column, indented, with each group's subtotal on its heading row.",
            "Outline Form: like compact, with group headings above their items.",
            "Tabular Form: each row field gets its own column, and subtotal rows labelled 'East Total' close each group.",
            "Untick Subtotals to drop group totals; untick Grand Totals for Columns or Rows to drop the bottom row or right-hand column.",
        ),
    ),
    Lesson(
        "pivot-refresh",
        "PivotTables",
        "Refresh, change source, details, and GETPIVOTDATA",
        "Keep the report current and pull its numbers into formulas.",
        (
            "A PivotTable is a snapshot: after changing the source data choose Data > PivotTable > Refresh (Alt+F5), or Refresh All (Ctrl+Alt+F5) for every PivotTable.",
            "Data > PivotTable > Change Data Source points the report at a different range or table.",
            "Click a value and choose Data > PivotTable > Show Details to list the source rows behind it on a new sheet.",
            "=GETPIVOTDATA(\"Sales\",A3,\"Region\",\"East\") returns the East total from the PivotTable that contains A3; add more field/item pairs to go deeper; omit them for the grand total.",
            "Cells inside a PivotTable can't be typed over; change the report through PivotTable Fields. Data > PivotTable > Delete PivotTable removes it.",
        ),
        ('=GETPIVOTDATA("Sum of Sales",Pivot!A3,"Region","West","Product","Apple")',),
        ("When saved as .xlsx the report's values are kept, but Excel won't treat them as a PivotTable; save as .dsheet to keep it live.",),
    ),
    # ------------------------------------------------------------ what-if
    Lesson(
        "datatable-column",
        "What-If Analysis",
        "One-variable data table (values down a column)",
        "See how one input changes one or more results, for many input values at once.",
        (
            "Build the model: an input cell (B1: interest rate) and a formula that uses it (B4: =PMT(B1/12,B2,-B3)).",
            "Type the input values down a column, starting one row below where the table starts (D2:D6: 3%, 4%, 5%, 6%, 7%).",
            "In the row above the first value and one column to the right, link to the formula (E1: =B4). Add more formulas to the right (F1, G1, ...) to see several results.",
            "Select the whole block including the formula row and the value column (D1:E6).",
            "Choose Data > What-If Analysis > Data Table, put the input cell in Column input cell (B1), leave Row input cell empty, and click OK.",
            "E2:E6 now show {=TABLE(,B1)}: the payment at each rate. They update whenever the model changes.",
        ),
        (
            "B1: 5%   B2: 360   B3: 200000   B4: =PMT(B1/12,B2,-B3)",
            "D2:D6: 3% 4% 5% 6% 7%    E1: =B4",
            "Select D1:E6 > Data Table > Column input cell B1 > OK",
        ),
    ),
    Lesson(
        "datatable-row",
        "What-If Analysis",
        "One-variable data table (values across a row)",
        "The same idea laid out horizontally.",
        (
            "Type the input values across a row, starting one column right of where the table starts (E1:I1).",
            "In the column to the left, one row below, link to the formula (D2: =B4); add more formulas below (D3, D4).",
            "Select D1:I2, choose Data > What-If Analysis > Data Table, put the input cell in Row input cell, and click OK.",
        ),
    ),
    Lesson(
        "datatable-two",
        "What-If Analysis",
        "Two-variable data table",
        "See one result for every combination of two inputs.",
        (
            "Put the formula in the top-left corner of the table (D1: =B4).",
            "Type the first input's values across the row to its right (E1:G1: 4%, 5%, 6%) and the second input's values down the column below it (D2:D3: 180, 360).",
            "Select D1:G3 and choose Data > What-If Analysis > Data Table.",
            "Row input cell is the cell the row values replace (B1, the rate); Column input cell is the cell the column values replace (B2, the term). Click OK.",
            "Each interior cell shows the payment for that rate and term, for example 1,073.64 for 5% over 360 months.",
        ),
        (
            "D1: =B4    E1:G1: 4% 5% 6%    D2:D3: 180 360",
            "Data Table: Row input B1, Column input B2  ->  E2:G3 = monthly payments",
        ),
    ),
    Lesson(
        "datatable-calc",
        "What-If Analysis",
        "Recalculation, editing, and other what-if tools",
        "Keep large models responsive and change a data table safely.",
        (
            "Data tables recalculate whenever an input they depend on changes. For big tables choose Formulas > Calculation Options > Automatic Except for Data Tables, then press F9 when you want them updated.",
            "You can't change one cell of a data table. To remove it, select its results and use Clear (Edit > Clear > Clear All), or choose Data > What-If Analysis > Delete Data Table.",
            "Your real input cells are never changed: each result is computed as if the input held that row's or column's value.",
            "Goal Seek (Data > What-If Analysis > Goal Seek) finds the input that makes a formula reach a target; Scenario Manager stores named sets of inputs and compares their results.",
            "Data tables are saved to .xlsx as Excel data tables and reopen live in Excel.",
        ),
    ),
)

SECTIONS = ("Excel Tables", "PivotTables", "What-If Analysis")


def lesson_html(lesson: Lesson) -> str:
    """Render a lesson as HTML for the Help browser."""
    parts = [f"<h2>{escape(lesson.title)}</h2>", f"<p><i>{escape(lesson.purpose)}</i></p>", "<h3>Steps</h3><ol>"]
    parts += [f"<li>{escape(step)}</li>" for step in lesson.steps]
    parts.append("</ol>")
    if lesson.example:
        parts.append("<h3>Example</h3><pre style='background:#f3f6f4;padding:6px'>")
        parts.append(escape("\n".join(lesson.example)))
        parts.append("</pre>")
    if lesson.tips:
        parts.append("<h3>Tips</h3><ul>")
        parts += [f"<li>{escape(tip)}</li>" for tip in lesson.tips]
        parts.append("</ul>")
    return "".join(parts)


def search_lessons(query: str) -> list[Lesson]:
    """Return lessons whose text mentions every word of the query."""
    words = [word.casefold() for word in query.split() if word]
    if not words:
        return list(LESSONS)
    found = []
    for lesson in LESSONS:
        haystack = " ".join((lesson.title, lesson.purpose, *lesson.steps, *lesson.example, *lesson.tips)).casefold()
        if all(word in haystack for word in words):
            found.append(lesson)
    return found


def build_practice_workbook() -> Any:
    """Return a workbook with a sales table, a PivotTable, and a loan data table to try."""
    from duddysheet.commands.analysis import add_pivot, create_data_table
    from duddysheet.core.data_table import DataTableSpec
    from duddysheet.core.engine import FormulaEngine
    from duddysheet.core.pivot import PivotSpec, PivotValueField
    from duddysheet.core.tables import create_table, make_calculated_column, set_totals_row, table_at
    from duddysheet.core.cell import CellFormat
    from duddysheet.core.workbook import Workbook

    workbook = Workbook(create_default=False)
    sales = workbook.add_sheet("Sales")
    rows = [
        ("Region", "Product", "Date", "Units", "Price"),
        ("East", "Apple", date(2024, 1, 15), 120, 1.25),
        ("East", "Pear", date(2024, 2, 10), 80, 1.6),
        ("West", "Apple", date(2024, 3, 22), 150, 1.2),
        ("West", "Kiwi", date(2024, 5, 3), 60, 2.4),
        ("North", "Pear", date(2024, 8, 19), 95, 1.55),
        ("East", "Apple", date(2025, 1, 12), 140, 1.3),
        ("West", "Apple", date(2025, 4, 8), 170, 1.25),
        ("North", "Kiwi", date(2025, 6, 30), 75, 2.5),
        ("East", "Kiwi", date(2025, 9, 14), 55, 2.45),
        ("North", "Apple", date(2025, 11, 2), 130, 1.3),
    ]
    date_format = CellFormat(number_format="m/d/yyyy")
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            sales.set_cell(row, column, value, cell_format=date_format if column == 2 and row else None)
    sales.set_cell(0, 5, "Amount")
    engine = FormulaEngine(workbook)
    create_table(workbook, "Sales", (0, 0, len(rows) - 1, 5), name="SalesTable")
    sales.set_cell(1, 5, "=[@Units]*[@Price]")
    make_calculated_column(sales, table_at(sales, 1, 5), 1, 5)
    table = set_totals_row(workbook, "Sales", table_at(sales, 0, 0), True)
    engine.rebuild_index()
    pivot_sheet = workbook.add_sheet("Pivot")
    add_pivot(
        workbook,
        pivot_sheet.name,
        PivotSpec(
            "PivotTable1",
            "Sales",
            (0, 0, table.last_data_row, 5),
            (2, 0),
            rows=("Region",),
            columns=("Date",),
            values=(PivotValueField("Amount", number_format="$#,##0.00"),),
            grouping=(("Date", "years"),),
            source_table="SalesTable",
        ),
    )
    loan = workbook.add_sheet("Loan")
    for row, (label, value) in enumerate(
        (("Annual rate", 0.05), ("Months", 360), ("Principal", 250000), ("Payment", "=PMT(B1/12,B2,-B3)"))
    ):
        loan.set_cell(row, 0, label)
        loan.set_cell(row, 1, value)
    loan.put_cell(0, 1, loan.get_cell(0, 1).__class__(raw_input=0.05, cached_value=0.05, format=CellFormat(number_format="0.00%")))
    loan.set_cell(5, 3, "=B4")
    for index, rate in enumerate((0.04, 0.05, 0.06, 0.07)):
        loan.set_cell(5, 4 + index, rate, cell_format=CellFormat(number_format="0.0%"))
    for index, months in enumerate((180, 240, 360)):
        loan.set_cell(6 + index, 3, months)
    create_data_table(workbook, "Loan", DataTableSpec(5, 3, 8, 7, ("Loan", 0, 1), ("Loan", 1, 1)))
    money = CellFormat(number_format="$#,##0.00")
    for row in range(6, 9):
        for column in range(4, 8):
            cell = loan.get_cell(row, column)
            loan.put_cell(row, column, cell.__class__(raw_input=cell.raw_input, format=money))
    workbook.active_sheet = "Sales"
    engine.rebuild_index()
    from duddysheet.commands.analysis import refresh_pivots

    refresh_pivots(workbook)
    engine.rebuild_index()
    return workbook
