"""Offline Charts and Graphing Tutorial opened from the Help menu."""

from __future__ import annotations

from html import escape
from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from duddysheet.core.chart import CHART_FAMILIES, CHART_INFO, CHART_TYPES


def _type_table(keys: tuple[str, ...]) -> str:
    """Render catalog entries as a table so the text never drifts from code."""
    rows = "".join(
        f"<tr><td><b>{escape(CHART_INFO[key].label)}</b></td>"
        f"<td>{escape(CHART_INFO[key].summary)}</td></tr>"
        for key in keys
    )
    return f"<table><tr><th>Chart</th><th>Use it to</th></tr>{rows}</table>"


def _family(name: str) -> tuple[str, ...]:
    return dict(CHART_FAMILIES)[name]


# Each tutorial is (key, title, html). Keys are stable so other windows can
# open a specific lesson.
TUTORIALS: tuple[tuple[str, str, str], ...] = (
    (
        "start",
        "Start here: your first chart in one minute",
        """
        <h1>Your first chart in one minute</h1>
        <p>Charts in Duddy Spreadsheet are <b>live</b>: each one is bound to a
        worksheet range and redraws the moment a value in that range changes.
        Every chart action (adding, editing, deleting) is a normal undoable
        edit, and charts are saved inside your <code>.dsheet</code> workbook.</p>
        <h2>Step 1: type a small table</h2>
        <pre>     A        B         C
1    Month    Revenue   Cost
2    Jan      120       80
3    Feb      135       84
4    Mar      128       90
5    Apr      150       92
6    May      162       97
7    Jun      171       101</pre>
        <p>The first row holds <b>headers</b> (they become series names), the
        first column holds <b>categories</b> (they label the horizontal axis),
        and every other column is one <b>series</b> of numbers.</p>
        <h2>Step 2: click any cell inside the table</h2>
        <p>You do not have to select the whole table. When a single cell is
        selected, charting expands the selection to the surrounding block of
        filled cells (here <code>A1:C7</code>), exactly as Excel does.</p>
        <h2>Step 3: insert a chart</h2>
        <ul>
          <li><b>Fastest:</b> press <b>Alt+F1</b> (or <b>Insert &gt; Quick
          Chart</b>) to create the best-ranked chart immediately.</li>
          <li><b>Pick a type:</b> <b>Insert &gt; Column &gt; Clustered
          Column</b> (or any other type) inserts that chart immediately.</li>
          <li><b>Full control:</b> <b>Insert &gt; Recommended Charts...</b>
          opens <b>Chart Studio</b> with a live preview.</li>
        </ul>
        <h2>Step 4: change it</h2>
        <p>The chart opens in its own floating window. Click <b>Edit</b> on
        that window to reopen Chart Studio, change anything, and click
        <b>Update Chart</b>. Now type <code>200</code> into <code>B7</code>:
        the June bar grows at once.</p>
        <h2>Step 5: undo, save, export</h2>
        <p>Press <b>Ctrl+Z</b> to undo the last chart change. Save the
        workbook with <b>Ctrl+S</b>; the chart is stored with it. Use
        <b>Export</b> on the chart window for PNG, SVG, or PDF, or <b>Copy
        Image</b> to paste the chart into another program.</p>
        """,
    ),
    (
        "arrange",
        "Arranging your data for each chart type",
        """
        <h1>Arranging data for charts</h1>
        <p>Most problems with charts are really problems with the shape of
        the data. These are the layouts every chart type expects.</p>
        <h2>Standard layout (column, bar, line, area, radar, combo)</h2>
        <pre>Category   Series 1   Series 2   Series 3
Jan        10         6          4
Feb        15         8          7</pre>
        <p>Categories go down the first column; each further column is one
        series. The header row names the series. Tick or clear <b>First row
        contains headers</b> on the <b>Data</b> tab if detection guesses
        wrong. To plot the table the other way round (one series per row),
        tick <b>Switch row / column</b>.</p>
        <h2>One series (pie, pie of pie, bar of pie, waterfall, funnel, Pareto)</h2>
        <pre>Stage       Customers
Visitors    5000
Sign-ups    1800
Trials      720
Paid        260</pre>
        <p>Only the first series is drawn. Pie charts ignore negative
        values; a doughnut draws one ring per series.</p>
        <h2>X Y data (scatter)</h2>
        <pre>Hours studied   Score
1               52
2               58
3.5             71</pre>
        <p>The first column must be <b>numbers</b>. If it contains text, the
        points are placed at 0, 1, 2&hellip; instead, which is rarely what
        you want; use a line chart for text categories.</p>
        <h2>Bubble</h2>
        <pre>Price   Units sold   Profit
10      400          1200
14      310          1500</pre>
        <p>X in the first column, then pairs of columns: Y value, then bubble
        size. Bubble <b>area</b> is proportional to the size value.</p>
        <h2>Stock</h2>
        <pre>Date     Volume   Open   High   Low    Close
3 Mar    12000    41.2   42.9   40.8   42.5</pre>
        <p>The columns after the dates must appear in exactly the order the
        chart type names: High-Low-Close, Open-High-Low-Close,
        Volume-High-Low-Close, or Volume-Open-High-Low-Close. Use <b>Series
        columns</b> on the Data tab to pick them if your table has
        extras.</p>
        <h2>Surface and contour</h2>
        <pre>           0.5%   1.0%   1.5%
Year 1     101    102    103
Year 2     102    104    106</pre>
        <p>A grid of numbers with labels along the top and the left. At least
        two rows and two value columns are needed.</p>
        <h2>Hierarchy (treemap, sunburst)</h2>
        <pre>Region     Country    Sales
Europe     France     10
           Germany    14
Asia       Japan      20
           India      8</pre>
        <p>Text columns, outermost level first, then one value column (the
        last column, unless you choose one in <b>Series columns</b>). A blank
        label repeats the one above it, so outline-style tables work
        unchanged.</p>
        <h2>Distributions (histogram, box and whisker)</h2>
        <p>Raw observations, one column per group. Do not pre-count them: the
        histogram does the binning for you.</p>
        <h2>General rules</h2>
        <ul>
          <li>Keep the table contiguous: no fully blank rows or columns inside
          it, or single-cell expansion stops at the gap.</li>
          <li>Text in a numeric column is treated as an empty cell.</li>
          <li>Formulas are fine; charts use their calculated values.</li>
        </ul>
        """,
    ),
    (
        "insert",
        "Five ways to insert a chart",
        """
        <h1>Inserting a chart</h1>
        <p>Select a range, or click one cell inside a table, then use any of
        these.</p>
        <h2>1. Insert menu, by type</h2>
        <p><b>Insert</b> on the menu bar lists every chart family (Column,
        Line, Pie, Bar, Area, X Y (Scatter), Stock, Surface, Radar, Treemap,
        Sunburst, Histogram, Box &amp; Whisker, Waterfall, Funnel, Combo,
        More). Pick a type and the chart is created immediately with a title
        taken from your series names, just like clicking a chart icon in
        Excel's Insert tab.</p>
        <h2>2. Ribbon chart galleries</h2>
        <p>The ribbon's <b>Insert</b> tab groups the same types the way Excel
        does: <b>Column/Bar</b>, <b>Line/Area</b>, <b>Pie/Doughnut</b>,
        <b>Hierarchy</b>, <b>Statistic</b>, <b>Scatter/Bubble</b>,
        <b>Waterfall/Stock</b>, <b>Combo</b>, and <b>More Charts</b>. Click a
        gallery button to open its menu.</p>
        <h2>3. Quick Chart</h2>
        <p><b>Insert &gt; Quick Chart</b> (or the ribbon's <b>Quick
        Chart</b>) creates the top recommendation without asking anything.
        The status bar explains why that type was chosen.</p>
        <h2>4. Recommended Charts</h2>
        <p><b>Insert &gt; Recommended Charts...</b> (ribbon: <b>Chart
        Studio</b>) opens Chart Studio on its <b>Recommended</b> tab. Up to
        five suggestions are ranked with a percentage fit and a plain-language
        reason, for example <i>"Dates were detected, so a trend view is the
        clearest."</i></p>
        <h2>5. Chart Studio's All Charts gallery</h2>
        <p>In Chart Studio, the <b>All Charts</b> tab lists every type grouped
        by family. Selecting one shows what it is for and how to arrange the
        data, and the live preview updates instantly.</p>
        <h2>How recommendations are chosen</h2>
        <table>
        <tr><th>If your data has&hellip;</th><th>You will see&hellip;</th></tr>
        <tr><td>Dates in the first column</td><td>Line, Area</td></tr>
        <tr><td>Numbers in the first column</td><td>Scatter (and Bubble for two value columns)</td></tr>
        <tr><td>One numeric column</td><td>Histogram, Box and Whisker</td></tr>
        <tr><td>One series with positive and negative values</td><td>Waterfall</td></tr>
        <tr><td>One series that shrinks at every step</td><td>Funnel</td></tr>
        <tr><td>Text columns followed by one value column</td><td>Treemap, Sunburst</td></tr>
        <tr><td>Columns named Open, High, Low, Close (and Volume)</td><td>The matching stock chart</td></tr>
        <tr><td>Four or more series and rows</td><td>Heatmap</td></tr>
        <tr><td>Several series</td><td>Clustered Column, Combo, Stacked Column</td></tr>
        </table>
        """,
    ),
    (
        "studio",
        "Chart Studio: a tour of every tab",
        """
        <h1>Chart Studio</h1>
        <p>Chart Studio is where charts are created and changed. The left side
        holds five tabs; the right side is a <b>live preview</b> that redraws
        after every change. Nothing reaches the workbook until you click
        <b>Create Chart</b> or <b>Update Chart</b>, and that click is one
        undoable step. <b>Help</b> opens this tutorial at the lesson for the
        chart type you are working on.</p>
        <h2>Recommended</h2>
        <p>Ranked suggestions for the selected range, each with its fit score
        and reason. Clicking one sets the chart type and, if the title is
        empty, a suggested title.</p>
        <h2>All Charts</h2>
        <p>The <b>Chart type</b> list and a gallery tree of all chart types by
        family. The panel under the tree summarises the selected type and the
        data layout it needs.</p>
        <h2>Elements</h2>
        <p>Excel's <i>Add Chart Element</i> menu, as one form: chart and axis
        titles, axes, gridlines, legend, data labels, data table, error bars,
        trendline, drop lines, high-low lines, up/down bars, and minimum and
        maximum highlighting.</p>
        <h2>Format</h2>
        <p>Excel's <i>Format</i> pane: chart style (theme), colors, number
        style, value-axis bounds and units, logarithmic scale, reverse
        category order, smoothed lines, gap width and overlap, pie and
        doughnut options, and histogram bin count.</p>
        <h2>Data</h2>
        <p>Excel's <i>Select Data</i> dialog: the source range, header row,
        category and series columns, <b>Switch row / column</b>, how empty
        cells are shown, and the per-series settings for a Custom
        Combination chart.</p>
        <h2>Tips</h2>
        <ul>
          <li>Text boxes apply when you press Enter or move to another
          field.</li>
          <li>If the preview shows a message instead of a chart (for example
          <i>"This stock chart needs 4 data columns..."</i>), the chosen type
          does not fit the data; fix the range or choose another type.</li>
          <li>Leave the title blank to use a title inferred from the series
          names.</li>
        </ul>
        """,
    ),
    (
        "column_bar",
        "Column and bar charts",
        """
        <h1>Column and bar charts</h1>
        <p>Columns are vertical, bars are horizontal. Use bars when category
        labels are long or there are many categories.</p>
        """
        + _type_table(_family("Column") + _family("Bar"))
        + """
        <h2>Clustered, stacked, or 100% stacked?</h2>
        <ul>
          <li><b>Clustered</b> compares individual values: which month sold
          most?</li>
          <li><b>Stacked</b> shows totals and their parts: how big was each
          month, and what made it up?</li>
          <li><b>100% stacked</b> compares shares: did the product mix change?
          Each category totals 100%; a category with 30 and 10 draws as 75%
          and 25%.</li>
        </ul>
        <h2>3-D variants</h2>
        <p><b>3-D Clustered</b>, <b>3-D Stacked</b>, and <b>3-D 100%
        Stacked</b> draw the same layouts as solid blocks. <b>3-D Column</b>
        puts each series on its own row of a depth axis, which suits a
        category-by-series grid. Drag inside a 3-D chart window (with no
        toolbar tool selected) to rotate it. 3-D charts are harder to read precisely; prefer 2-D for
        exact comparisons.</p>
        <h2>Spacing: gap width and overlap (Format tab)</h2>
        <ul>
          <li><b>Gap width</b> (0&ndash;500%) is the space between category
          groups as a percentage of one bar's width. 0% makes bars touch;
          larger values make thinner bars.</li>
          <li><b>Series overlap</b> (&minus;100 to 100%) slides the bars in a
          cluster together. 100% draws them on top of each other; negative
          values add space between them.</li>
        </ul>
        <h2>Worked example</h2>
        <ol>
          <li>Enter the Month/Revenue/Cost table from <i>Start here</i>.</li>
          <li>Choose <b>Insert &gt; Column &gt; Stacked Column</b>.</li>
          <li>Click <b>Edit</b>, open <b>Elements</b>, tick <b>Show data
          labels</b>, and set <b>Label position</b> to <b>Center</b>.</li>
          <li>Open <b>Format</b> and set <b>Gap width</b> to 60%.</li>
          <li>Click <b>Update Chart</b>. Each segment is labelled in its middle
          and the stacks are wide and easy to compare.</li>
        </ol>
        <p>Error bars and trendlines work on clustered columns and clustered
        bars (trendlines on columns only), as in Excel.</p>
        """,
    ),
    (
        "line_area",
        "Line and area charts",
        """
        <h1>Line and area charts</h1>
        <p>Use lines for trends over ordered categories such as months, and
        areas when the size of the total matters as much as its shape.</p>
        """
        + _type_table(_family("Line") + _family("Area") + ("step",))
        + """
        <h2>Stacked lines are cumulative</h2>
        <p>In a <b>Stacked Line</b> each line is the running total of the
        series below it, so the top line is the grand total. This is easy to
        misread; if you want to compare series directly, use a plain
        <b>Line</b>. <b>100% Stacked Line</b> ends with a top line at 100%.</p>
        <h2>Smooth curves</h2>
        <p>Tick <b>Format &gt; Smoothed line</b> to draw a curve through every
        point instead of straight segments. The curve still passes through
        each data value.</p>
        <h2>Empty cells</h2>
        <p><b>Data &gt; Show empty cells as</b> chooses what happens at a
        blank cell: <b>Gaps</b> breaks the line, <b>Zero</b> drops it to
        zero, and <b>Connect data points with line</b> joins the neighbours
        across the gap.</p>
        <h2>Drop lines, high-low lines, and up/down bars</h2>
        <p>On line charts, <b>Elements &gt; Lines</b> and <b>Bars</b> add
        Excel's analysis lines:</p>
        <ul>
          <li><b>Drop lines</b>: a dotted line from each point down to the
          axis (also on area charts). Useful for reading exact positions.</li>
          <li><b>High-low lines</b>: at each category, a vertical line from the
          lowest to the highest series value. Needs two or more series.</li>
          <li><b>Up/down bars</b>: a bar from the first series to the last at
          each category; hollow when the last is higher (up), dark when lower
          (down). With Open and Close series this is a simple candlestick.</li>
        </ul>
        <h2>Worked example: budget vs actual</h2>
        <ol>
          <li>Enter columns Month, Budget, Actual.</li>
          <li><b>Insert &gt; Line &gt; Line with Markers</b>.</li>
          <li>Edit, tick <b>Up/down bars</b> on the Elements tab, and update.
          Hollow bars mark months that beat budget; dark bars mark months that
          missed.</li>
        </ol>
        """,
    ),
    (
        "pie",
        "Pie, doughnut, pie of pie, and bar of pie",
        """
        <h1>Pie and doughnut charts</h1>
        <p>A pie shows how one whole divides into parts. Use it for a handful
        of positive values; with more than about six slices, a bar chart is
        easier to read.</p>
        """
        + _type_table(_family("Pie"))
        + """
        <h2>Pie options (Format tab)</h2>
        <ul>
          <li><b>Angle of first slice</b> (0&ndash;360&deg;) rotates the pie.
          Slices run clockwise from 12 o'clock, as in Excel.</li>
          <li><b>Point explosion</b> (0&ndash;400%) pulls every slice away from
          the centre.</li>
          <li><b>Doughnut hole size</b> (10&ndash;90%) sets the size of the
          hole. Several series draw as concentric rings, the first series
          outermost.</li>
          <li><b>Values in second plot</b> sets how many of the <b>last</b>
          values move into the second pie or bar of a Pie of Pie or Bar of
          Pie. They are combined into one <b>Other</b> slice in the main pie.
          Sort your data so the smallest values come last.</li>
        </ul>
        <h2>Pie data labels</h2>
        <p>With <b>Show data labels</b> ticked, <b>Label contains</b> chooses
        the value, the <b>Percentage</b> of the whole, the category name, the
        series name, or category and value together. <b>Label position</b>
        places them in the centre of the slice (<b>Center</b>, <b>Inside
        end</b>, <b>Inside base</b>) or outside it (<b>Outside end</b>).</p>
        <h2>Worked example: pie of pie</h2>
        <pre>Expense      Amount
Rent         1800
Food         650
Transport    300
Phone        60
Streaming    30
Gym          25</pre>
        <ol>
          <li>Select the table and choose <b>Insert &gt; Pie &gt; Pie of
          Pie</b>.</li>
          <li>Phone, Streaming, and Gym (the last three) are combined into
          <b>Other</b> and expanded in the small pie on the right, so the tiny
          costs remain visible.</li>
          <li>Edit, set <b>Values in second plot</b> to 2, and only Streaming
          and Gym move across.</li>
        </ol>
        """,
    ),
    (
        "scatter",
        "Scatter and bubble charts",
        """
        <h1>Scatter and bubble charts</h1>
        <p>Scatter charts plot pairs of numbers to show whether and how two
        measures are related. Unlike a line chart, the horizontal axis is a
        true number scale: points at 1, 2, and 10 are spaced accordingly.</p>
        """
        + _type_table(_family("X Y (Scatter)"))
        + """
        <h2>Lines on a scatter chart</h2>
        <p>The <i>with lines</i> variants join points in order of increasing
        X, so an unsorted table still draws a sensible curve. Use the smooth
        variants for measured curves and the straight variants for piecewise
        data.</p>
        <h2>Bubble sizes</h2>
        <p>Bubble <b>area</b> (not diameter) is proportional to the size
        value, and the largest bubble is drawn at a fixed size, as in Excel.
        Negative sizes are drawn using their absolute value.</p>
        <h2>Worked example: does study time predict the score?</h2>
        <ol>
          <li>Enter <i>Hours</i> in column A and <i>Score</i> in column B.</li>
          <li><b>Insert &gt; X Y (Scatter) &gt; Scatter</b>.</li>
          <li>Edit, tick <b>Show trendline</b>, <b>Display equation</b>, and
          <b>Display R-squared</b>. An R-squared near 1 means hours explain
          most of the variation in scores; near 0 means they do not.</li>
        </ol>
        """,
    ),
    (
        "stock",
        "Stock charts",
        """
        <h1>Stock charts</h1>
        """
        + _type_table(_family("Stock"))
        + """
        <h2>Column order is strict</h2>
        <p>After the date column, the price columns must appear in exactly the
        order in the chart name. If the count is wrong the preview says, for
        example, <i>"This stock chart needs 4 data columns in this order:
        Open, High, Low, Close"</i>. When your table has other columns, list
        just the right ones in <b>Data &gt; Series columns</b>, such as
        <code>C,D,E,F</code>.</p>
        <h2>Reading the marks</h2>
        <ul>
          <li><b>High-Low-Close</b>: a vertical line from low to high, with a
          tick at the close.</li>
          <li><b>Open-High-Low-Close</b>: candlesticks. A hollow body means the
          price closed above the open (a rise); a filled body means it closed
          below (a fall). The thin wick spans the low to the high.</li>
          <li><b>Volume</b> variants draw volume as columns on the left axis
          and prices on a second axis on the right.</li>
        </ul>
        <h2>Worked example</h2>
        <pre>Date    Open   High   Low    Close
D1      10     12     9      11
D2      11     13     10     10.5
D3      10.5   14     10     13</pre>
        <p>Choose <b>Insert &gt; Stock &gt; Open-High-Low-Close</b>. D1 and D3
        draw hollow (up) candles; D2 draws a filled (down) candle.</p>
        <p>Name the columns Open, High, Low, Close (and Volume) and Quick Chart
        will recognise the table as stock data by itself.</p>
        """,
    ),
    (
        "surface",
        "Surface and contour charts",
        """
        <h1>Surface and contour charts</h1>
        <p>These show a value that depends on two things at once, such as
        loan cost by rate and term, or temperature by day and hour.</p>
        """
        + _type_table(_family("Surface"))
        + """
        <h2>Data</h2>
        <p>Row labels down the first column, column labels across the header
        row, and a number in every cell. Rows run along one horizontal
        direction, series (columns) along the other, and the value is the
        height.</p>
        <h2>Choosing between them</h2>
        <ul>
          <li><b>3-D Surface</b> gives the most intuitive picture of peaks and
          valleys, with a color scale beside it.</li>
          <li><b>Contour</b> is the same surface seen from directly above: easier
          to read exact positions, and it never hides one peak behind
          another.</li>
          <li>The <b>wireframe</b> variants draw only lines, which print well
          in black and white. Wireframe Contour labels each line with its
          value.</li>
        </ul>
        """,
    ),
    (
        "radar",
        "Radar charts",
        """
        <h1>Radar charts</h1>
        <p>A radar chart gives each category its own spoke radiating from the
        centre, and draws each series as a closed shape. It is good for
        comparing profiles, such as products scored on price, quality,
        support, and speed.</p>
        """
        + _type_table(_family("Radar"))
        + """
        <p>The first category sits at 12 o'clock and the rest follow
        clockwise. Every spoke shares one scale, so put measures on
        comparable scales (for example all scores out of 10) before charting.
        Set <b>Format &gt; Minimum</b> and <b>Maximum</b> to fix the scale,
        for example 0 to 10.</p>
        <p>Filled radars are clearest with two or three series; with more,
        use plain Radar or Radar with Markers.</p>
        """,
    ),
    (
        "hierarchy",
        "Treemap and sunburst charts",
        """
        <h1>Treemap and sunburst charts</h1>
        <p>Both show a hierarchy (groups inside groups) sized by value.</p>
        """
        + _type_table(_family("Treemap") + _family("Sunburst"))
        + """
        <h2>Data</h2>
        <pre>Region     Country    Sales
Europe     France     10
           Germany    14
Asia       Japan      20
           India      8
Americas   USA        30</pre>
        <p>Level columns come first, outermost on the left, then one value
        column. Blank cells in a level column repeat the label above, so
        Germany belongs to Europe. You can use as many levels as you like.
        Rows whose value is blank, zero, or negative are left out.</p>
        <h2>Reading them</h2>
        <ul>
          <li><b>Treemap</b>: each top-level group gets one color and a
          rectangle whose area matches its total; its members are the shaded
          rectangles inside, largest first. Group names appear in the top-left
          corner of each group.</li>
          <li><b>Sunburst</b>: the inner ring holds the top level, and each
          outer ring splits its parent. Angles are proportional to value.
          Sunbursts show deep hierarchies better; treemaps compare sizes
          better.</li>
        </ul>
        <p>Tick <b>Show data labels</b> to add each item's value under its
        name.</p>
        """,
    ),
    (
        "statistics",
        "Histogram, Pareto, and box and whisker",
        """
        <h1>Statistical charts</h1>
        """
        + _type_table(_family("Histogram") + _family("Box & Whisker"))
        + """
        <h2>Histogram</h2>
        <p>Put raw observations (for example 200 delivery times) in one
        column. The histogram groups them into bins and draws how many values
        fall in each. By default the number of bins is chosen automatically;
        set <b>Format &gt; Number of bins</b> to fix it. Fewer bins show the
        overall shape; more bins show detail. With several columns, each is
        drawn as a semi-transparent histogram so the distributions can be
        compared.</p>
        <h2>Pareto</h2>
        <p>A Pareto chart sorts categories from largest to smallest and adds a
        cumulative-percentage line on a 0&ndash;100% axis on the right. It
        answers "which few causes account for most of the problem?"</p>
        <pre>Complaint       Count
Late delivery   48
Damaged         22
Wrong item      15
Billing error   9
Other           6</pre>
        <p>The line reads 48%, 70%, 85%, 94%, 100%: two causes produce 70% of
        complaints, so fix those first.</p>
        <h2>Box and whisker</h2>
        <p>Each column becomes one box. The box spans the lower to the upper
        quartile (the middle half of the data) with a line at the median and
        a triangle at the mean. Whiskers reach the furthest points within 1.5
        box-lengths of the box; anything beyond is drawn as an individual
        outlier point.</p>
        """,
    ),
    (
        "flow",
        "Waterfall and funnel charts",
        """
        <h1>Waterfall and funnel charts</h1>
        """
        + _type_table(_family("Waterfall") + _family("Funnel"))
        + """
        <h2>Waterfall</h2>
        <p>Enter the <b>changes</b>, not running totals. Each bar starts where
        the previous one ended; increases use the first series color and
        decreases use the theme's accent color. A thin line traces the running
        total.</p>
        <pre>Item               Amount
Opening cash       500
Sales              320
Salaries           -210
Rent               -90
Tax refund         40</pre>
        <p>The bars climb to 820, fall to 610 and 520, then finish at 560.</p>
        <h2>Funnel</h2>
        <p>Enter the stages in order, largest first. Each stage draws as a
        centred bar with its value, so drop-off between stages is easy to see.
        To show conversion rates, add a column of formulas such as
        <code>=B3/B2</code> alongside and chart it separately.</p>
        """,
    ),
    (
        "combo",
        "Combo charts and the secondary axis",
        """
        <h1>Combo charts</h1>
        <p>A combo chart mixes columns, lines, and areas, usually because the
        series have different meanings or very different sizes, such as
        revenue in dollars and margin in percent.</p>
        """
        + _type_table(_family("Combo"))
        + """
        <h2>Secondary axis</h2>
        <p>A secondary axis is a second value scale on the right. Use it when
        one series would otherwise be a flat line along the bottom. With
        <b>Clustered Column - Line</b>, ticking <b>Format &gt; Combo lines on
        secondary axis</b> has the same effect as choosing the <i>on Secondary
        Axis</i> type.</p>
        <h2>Custom Combination</h2>
        <p>Choose <b>Combo &gt; Custom Combination</b>, then on the
        <b>Data</b> tab:</p>
        <ul>
          <li><b>Series chart types</b>: one entry per series, in order, each
          <code>column</code>, <code>line</code>, or <code>area</code>. For
          example <code>column,column,line</code>. Missing entries default to
          column for the first series and line for the rest.</li>
          <li><b>Series on secondary axis</b>: the series numbers (counting
          from 1) that use the right-hand axis, for example
          <code>3</code>.</li>
        </ul>
        <h2>Worked example: revenue and margin</h2>
        <pre>Month   Revenue   Cost   Margin %
Jan     120       80     0.33
Feb     135       84     0.38</pre>
        <ol>
          <li>Insert <b>Combo &gt; Custom Combination</b>.</li>
          <li>Set <b>Series chart types</b> to <code>column,column,line</code>
          and <b>Series on secondary axis</b> to <code>3</code>.</li>
          <li>Revenue and Cost are side-by-side columns on the left axis; Margin
          % is a line on its own right-hand scale.</li>
        </ol>
        """,
    ),
    (
        "elements",
        "Chart elements: titles, axes, legend, gridlines, labels, data table",
        """
        <h1>Chart elements</h1>
        <p>All of Excel's <i>Add Chart Element</i> items are on the
        <b>Elements</b> tab of Chart Studio.</p>
        <h2>Titles</h2>
        <p><b>Chart title</b> appears top left. <b>Horizontal axis title</b>
        labels the bottom axis and <b>Vertical axis title</b> the left axis.
        Leave the chart title blank to have one inferred, such as
        <i>Revenue vs Cost</i>.</p>
        <h2>Axes</h2>
        <p><b>Primary horizontal</b> (the bottom axis) and <b>Primary
        vertical</b> (the left axis) can each be hidden. Hiding an axis
        removes its labels and line but keeps the data in place, which is
        useful with data labels.</p>
        <h2>Legend</h2>
        <p>Right, left, top, bottom, or none. The legend appears only when
        there is more than one item to name.</p>
        <h2>Gridlines</h2>
        <ul>
          <li><b>Major (value)</b>: lines at each value-axis label. This is the
          usual horizontal gridline (vertical on bar charts).</li>
          <li><b>Major (category)</b>: lines at each category.</li>
          <li><b>Minor</b>: fainter lines between the major ones.</li>
        </ul>
        <h2>Data labels</h2>
        <p>Tick <b>Show data labels</b>, then choose:</p>
        <table>
        <tr><th>Label position</th><th>Columns and bars</th><th>Lines and points</th></tr>
        <tr><td>Automatic</td><td>Outside end (centre when stacked)</td><td>Above</td></tr>
        <tr><td>Center</td><td>Middle of the bar</td><td>On the point</td></tr>
        <tr><td>Inside end</td><td>Inside, at the tip</td><td>Above</td></tr>
        <tr><td>Inside base</td><td>Inside, at the axis</td><td>Below</td></tr>
        <tr><td>Outside end</td><td>Just beyond the tip</td><td>Above</td></tr>
        </table>
        <p><b>Label contains</b> selects the value, the percentage (of the
        category's total across series, or of the whole for pies), the
        category name, the series name, or category and value. Labels use the
        <b>Number style</b> from the Format tab.</p>
        <h2>Data table</h2>
        <p><b>Show data table</b> puts a grid of the plotted numbers under the
        chart, one row per series with a color key, in place of the category
        labels. It is available on column, line, area, step, and combo
        charts.</p>
        <h2>Highlight minimum / maximum</h2>
        <p>Circles the lowest and highest point of each series on column,
        line, step, and scatter charts.</p>
        """,
    ),
    (
        "trendlines",
        "Trendlines and forecasting",
        """
        <h1>Trendlines</h1>
        <p>A trendline fits a mathematical curve to a series to show its
        direction and to forecast beyond the data. Tick <b>Elements &gt; Show
        trendline</b>. Trendlines are available on clustered column, line,
        step, area, scatter, and bubble charts; one is drawn per series.</p>
        <h2>Types</h2>
        <table>
        <tr><th>Type</th><th>Equation</th><th>Use when</th></tr>
        <tr><td>Linear</td><td>y = mx + b</td><td>Values rise or fall at a steady rate.</td></tr>
        <tr><td>Exponential</td><td>y = ce<sup>bx</sup></td><td>Values grow or decay at a steady <i>percentage</i>. All values must be positive.</td></tr>
        <tr><td>Logarithmic</td><td>y = c ln(x) + b</td><td>Fast change that levels off.</td></tr>
        <tr><td>Polynomial</td><td>y = b + c<sub>1</sub>x + &hellip; + c<sub>n</sub>x<sup>n</sup></td><td>Data with bends. Set the <b>Order / period</b> to 2&ndash;6: order 2 allows one bend, order 3 two bends, and so on.</td></tr>
        <tr><td>Power</td><td>y = cx<sup>b</sup></td><td>Measurements that scale, such as area versus length. Positive values only.</td></tr>
        <tr><td>Moving average</td><td>average of the last <i>n</i> points</td><td>Smoothing noise. <b>Order / period</b> is <i>n</i> (2 or more).</td></tr>
        </table>
        <p>On category charts (columns, lines, areas) the categories are
        numbered 1, 2, 3&hellip; for the fit, exactly as Excel does, so the
        equations match Excel's. On scatter charts the real X values are
        used.</p>
        <h2>Equation and R-squared</h2>
        <p><b>Display equation</b> and <b>Display R-squared</b> print them in
        the top-left corner in the series color. R-squared runs from 0 (the
        curve explains nothing) to 1 (a perfect fit). For exponential and
        power fits it is computed on the logarithms of the values, as
        Excel does.</p>
        <h2>Forecasting</h2>
        <p><b>Forecast forward</b> and <b>Forecast backward</b> extend the
        line by that many periods (categories) or X units (scatter).</p>
        <h2>Worked example</h2>
        <p>With Revenue of 120, 135, 128, 150, 162, 171 for Jan&ndash;Jun on a
        line chart, a <b>Linear</b> trendline with the equation and R-squared
        shows:</p>
        <pre>y = 10.23x + 108.5, R² = 0.9148</pre>
        <p>Revenue grows by about 10.23 a month and the line explains about 91%
        of the variation. Setting <b>Forecast forward</b> to 2 extends the line
        to about 180.1 in period 7 and 190.4 in period 8. A <b>Polynomial</b>
        order-2 fit gives <code>y = 0.8214x^2 + 4.479x + 116.2</code> with
        R&sup2; = 0.9274: a slightly better fit that also bends upward, so
        compare forecasts before trusting either.</p>
        <p>A trendline describes the past; it does not know about future
        events. Treat forecasts as a starting point.</p>
        """,
    ),
    (
        "error_bars",
        "Error bars",
        """
        <h1>Error bars</h1>
        <p>Error bars show the uncertainty around each value as a line with
        caps above and below the point (left and right on bar charts). Choose
        a type in <b>Elements &gt; Error bars</b> and optionally an
        <b>Amount</b>; leave the amount blank for the default shown below.
        They are available on clustered column and bar, line, step, area,
        scatter, and bubble charts.</p>
        <table>
        <tr><th>Type</th><th>Size of each bar</th><th>Default amount</th></tr>
        <tr><td>Fixed value</td><td>&plusmn; the amount, for every point</td><td>1</td></tr>
        <tr><td>Percentage</td><td>&plusmn; that percent of each point's value</td><td>5%</td></tr>
        <tr><td>Standard deviation</td><td>&plusmn; amount &times; the series' sample standard deviation</td><td>1</td></tr>
        <tr><td>Standard error</td><td>&plusmn; amount &times; standard deviation &divide; &radic;n</td><td>1</td></tr>
        </table>
        <h2>Worked example</h2>
        <p>For Revenue 120, 135, 128, 150, 162, 171:</p>
        <ul>
          <li><b>Percentage</b> 5% gives &plusmn;6.0 on January and &plusmn;8.55 on
          June.</li>
          <li><b>Standard deviation</b> gives &plusmn;20.0 on every point.</li>
          <li><b>Standard error</b> gives &plusmn;8.17 on every point
          (20.0 &divide; &radic;6).</li>
        </ul>
        <p>Blank cells are ignored when the standard deviation is
        calculated.</p>
        """,
    ),
    (
        "axes",
        "Formatting the value axis: bounds, units, log scale, reverse order",
        """
        <h1>Formatting the value axis</h1>
        <p>These settings are on the <b>Format</b> tab. They apply to the
        value axis: the vertical axis on most charts, the horizontal axis on
        bar charts, and the height axis on 3-D charts.</p>
        <h2>Minimum, maximum, and major unit</h2>
        <p>Leave them blank for automatic scaling. Type a number to fix a
        bound, for example a Minimum of 0 so bars are not exaggerated, or a
        Maximum of 100 for percentages. <b>Major unit</b> sets the distance
        between axis labels, for example 25 for 0, 25, 50, 75, 100. The
        minimum must be less than the maximum.</p>
        <h2>Logarithmic scale</h2>
        <p>Each step up the axis multiplies the value by 10. Use it when
        values span several orders of magnitude, or to show steady percentage
        growth as a straight line. Zero and negative values cannot be plotted
        on a log scale, so use it only for positive data. Not available on
        3-D charts.</p>
        <h2>Display units</h2>
        <p>Divides the axis labels by a hundred, thousand, million, or
        billion and adds the unit to the axis title, so 2,500,000 shows as 2.5
        with the title <i>Millions</i>. Data labels are not affected.</p>
        <h2>Categories in reverse order</h2>
        <p>Flips the category axis. On bar charts this puts the first category
        at the top, the way a table reads. The data table follows the same
        order.</p>
        <h2>Number style</h2>
        <p>Auto (compact K, M, B), Number (two decimals), Currency ($), or
        Percent. Percent expects fractions: 0.25 shows as 25.0%.</p>
        """,
    ),
    (
        "style",
        "Chart styles and colors",
        """
        <h1>Styles and colors</h1>
        <h2>Chart style (theme)</h2>
        <p>Five complete styles set the background, text, gridlines, accent,
        and series colors together:</p>
        <ul>
          <li><b>executive</b>: warm neutral background with teal, coral, and
          gold. The default.</li>
          <li><b>coastal</b>: soft green-blue tones.</li>
          <li><b>editorial</b>: black with strong accent colors, like a
          newspaper graphic.</li>
          <li><b>monochrome</b>: shades of gray, ideal for black-and-white
          printing.</li>
          <li><b>high_contrast</b>: saturated, clearly separated colors on
          white for projection and accessibility.</li>
        </ul>
        <h2>Colors (Excel's Change Colors)</h2>
        <p><b>Theme colors</b> use the style's own palette. <b>Colorful</b>
        uses Office-style blue, orange, gray, gold, light blue, and green.
        The <b>Monochromatic</b> choices use shades of one hue, which suit
        ordered series such as years. The style still controls the background
        and text.</p>
        <h2>Tips</h2>
        <ul>
          <li>Use one hue for one meaning across a report: if Revenue is teal
          in one chart, keep it teal in the next by keeping the same series
          order.</li>
          <li>Waterfall decreases, stock down candles, and highlighted extremes
          use the style's accent color.</li>
        </ul>
        """,
    ),
    (
        "data",
        "Selecting data: series, filters, switch row/column, empty cells",
        """
        <h1>Selecting chart data</h1>
        <p>The <b>Data</b> tab plays the role of Excel's <i>Select Data</i>
        dialog and chart filters.</p>
        <h2>Data range</h2>
        <p>Type any range, such as <code>A1:D13</code> or
        <code>'Q1 Sales'!B2:F20</code>. The preview and recommendations update
        when you press Enter.</p>
        <h2>First row contains headers</h2>
        <p>When ticked, the first row names the series and is not plotted.
        It is detected automatically when text sits above numbers.</p>
        <h2>Category column and series columns (chart filters)</h2>
        <p>Leave both blank to use the first column as categories and every
        other column as a series. Enter a column letter in <b>Category
        column</b> to use a different one. Enter letters in <b>Series
        columns</b>, such as <code>B,D</code>, to plot only those series in
        that order; this is how you filter series out of a chart without
        changing the sheet.</p>
        <h2>Switch row / column</h2>
        <p>Plots the table the other way round: each row becomes a series and
        each column header becomes a category. For a table of regions (rows)
        by quarters (columns), the normal view compares regions within each
        quarter; switched, it compares quarters within each region.</p>
        <h2>Show empty cells as</h2>
        <p><b>Gaps</b> leaves a break, <b>Zero</b> plots zero, and
        <b>Connect data points with line</b> bridges the gap on line and
        scatter charts. Column charts show an empty cell as no bar.</p>
        <h2>Live links</h2>
        <p>A chart always reads the current values in its range, including
        formula results, so it updates as you type, recalculate, or change
        inputs. Inserting or deleting rows or columns inside the range moves
        and resizes the chart's range to match, and renaming a sheet updates
        it too.</p>
        """,
    ),
    (
        "working",
        "Working with chart windows: edit, copy, export, undo, save",
        """
        <h1>Working with charts</h1>
        <h2>The chart window</h2>
        <p>Each chart has its own window, which floats by default. Drag its
        title bar to dock it beside the grid, or drag it back out. The top row
        shows how many series and live values it contains, and has these
        buttons:</p>
        <ul>
          <li><b>Edit</b>: reopen Chart Studio for this chart.</li>
          <li><b>Copy Image</b>: copy a picture of the chart to the clipboard
          for pasting into email, documents, or slides.</li>
          <li><b>Export</b>: save as PNG (high-resolution image), SVG
          (scalable vector for design tools and the web), or PDF (vector,
          print-ready).</li>
          <li><b>Help</b>: open this tutorial at the lesson for the chart's
          type.</li>
        </ul>
        <p>The toolbar below them lets you <b>pan</b> and <b>zoom</b> into a
        region (Home resets the view) and adjust margins. With no tool
        selected, dragging inside a 3-D chart rotates it. These views are temporary and not
        saved.</p>
        <h2>Deleting and undoing</h2>
        <p>Closing a chart window deletes the chart. Press <b>Ctrl+Z</b> to
        bring it back. Creating, editing, and deleting charts are all on the
        undo history, with the rest of your edits.</p>
        <h2>Saving</h2>
        <p>Charts and sparklines are saved in <code>.dsheet</code> workbooks,
        with every setting, and reopen exactly as they were. Excel
        <code>.xlsx</code> and CSV files cannot carry these charts: saving to
        them keeps the data but not the charts, and charts inside an Excel
        file you open are not imported (you are told when this happens).</p>
        <h2>Charts on several sheets</h2>
        <p>Each sheet has its own charts. Switching sheets shows that sheet's
        charts, and a chart may plot data from a different sheet by naming
        it in the data range.</p>
        """,
    ),
    (
        "sparklines",
        "Sparklines: tiny charts inside cells",
        """
        <h1>Sparklines</h1>
        <p>A sparkline is a word-sized chart drawn inside one cell, placed next
        to the numbers it summarises. They are ideal for dashboards: one
        sparkline per row shows every row's trend at a glance.</p>
        <table>
        <tr><th>Type</th><th>Shows</th></tr>
        <tr><td><b>Line</b></td><td>The trend of a series.</td></tr>
        <tr><td><b>Column</b></td><td>Relative size of each value, with negatives below an axis.</td></tr>
        <tr><td><b>Win/Loss</b></td><td>Only the sign: an up block for positive, a down block for negative, nothing for zero. Good for results, targets hit, or profit and loss months.</td></tr>
        </table>
        <h2>Creating sparklines</h2>
        <ol>
          <li>Select the numbers, for example <code>B2:M5</code> (four
          products by twelve months).</li>
          <li>Choose <b>Insert &gt; Sparklines &gt; Line...</b> (or Column or
          Win/Loss), or use the ribbon's <b>Sparklines</b> gallery.</li>
          <li>The <b>Data range</b> is your selection. The <b>Location
          range</b> suggests the column just to the right,
          <code>N2:N5</code>. Change it if you like.</li>
          <li>Choose a color and which points to emphasise, then click
          OK.</li>
        </ol>
        <p>A location <b>column</b> takes one data <b>row</b> per cell; a
        location <b>row</b> takes one data <b>column</b> per cell; a single
        location cell takes a one-row or one-column data range. A sparkline
        placed on a cell that already has one replaces it.</p>
        <h2>Options</h2>
        <ul>
          <li><b>Markers</b> (line only): a dot on every value.</li>
          <li><b>High point</b>, <b>Low point</b>, <b>First point</b>, <b>Last
          point</b>: emphasise those values in the marker color.</li>
          <li><b>Negative points</b>: emphasise values below zero in red.</li>
          <li><b>Show axis</b>: draw a zero line when the data crosses
          zero.</li>
        </ul>
        <h2>Removing sparklines</h2>
        <p>Select the cells and choose <b>Insert &gt; Sparklines &gt; Clear
        Sparklines</b>. Like everything else, it can be undone with
        Ctrl+Z.</p>
        <p>Sparklines update with their data, move when rows or columns are
        inserted or deleted, and are saved in <code>.dsheet</code> files. They
        draw on top of any text in the cell, so place them in empty cells.</p>
        """,
    ),
    (
        "troubleshooting",
        "Troubleshooting",
        """
        <h1>Troubleshooting</h1>
        <table>
        <tr><th>Problem</th><th>Cause and fix</th></tr>
        <tr><td>"Select a data range or a cell inside a contiguous data table"</td>
        <td>The selected cell is empty or alone. Click inside your table, or
        select the range by dragging.</td></tr>
        <tr><td>The header row is plotted as a zero point</td>
        <td>Tick <b>Data &gt; First row contains headers</b>.</td></tr>
        <tr><td>A series is missing or flat at zero</td>
        <td>The column holds text that looks like numbers (for example numbers
        typed with a leading apostrophe). Re-enter them as numbers. Check
        <b>Series columns</b> is blank or lists the column.</td></tr>
        <tr><td>Scatter points sit at 0, 1, 2, 3</td>
        <td>The first column contains text. Scatter needs numeric X values; use
        a line chart for text categories.</td></tr>
        <tr><td>"This stock chart needs N data columns..."</td>
        <td>Choose price columns in the order the chart names using <b>Series
        columns</b>. See <i>Stock charts</i>.</td></tr>
        <tr><td>"Surface and contour charts need at least two rows and two value columns"</td>
        <td>Extend the range to a full grid.</td></tr>
        <tr><td>The pie shows only some categories</td>
        <td>Pies skip zero and negative values. Use a bar chart for data with
        negatives.</td></tr>
        <tr><td>No trendline appears</td>
        <td>Trendlines need at least two points (more than the polynomial
        order), and exponential or power trendlines need positive values.
        They are not drawn on stacked, pie, 3-D, or radar charts.</td></tr>
        <tr><td>The chart ignores Minimum or Maximum</td>
        <td>100% stacked charts are in percent: use values from 0 to 100. On
        radar charts the bounds set the spoke scale.</td></tr>
        <tr><td>A chart vanished</td>
        <td>Closing its window deletes it: press Ctrl+Z. Or it belongs to a
        different sheet: switch sheets.</td></tr>
        <tr><td>Charts disappeared after saving</td>
        <td>The workbook was saved as .xlsx or .csv. Save as
        <code>.dsheet</code> to keep charts.</td></tr>
        </table>
        """,
    ),
    (
        "differences",
        "How charting here compares with Excel",
        """
        <h1>Compared with Excel</h1>
        <p>Every chart family in Excel's Insert Chart gallery is here except
        <b>Map</b> charts, with all of Excel's chart elements and the main
        format options.</p>
        <h2>Included</h2>
        <ul>
          <li>Column, Line, Pie, Bar, Area, X Y (Scatter), Bubble, Stock,
          Surface, Radar, Treemap, Sunburst, Histogram, Pareto, Box &amp;
          Whisker, Waterfall, Funnel, and Combo charts, with their 2-D and 3-D
          subtypes, plus Step Line and Heatmap.</li>
          <li>Axes, axis titles, chart title, data labels, data table, error
          bars, gridlines, legend, drop lines, high-low lines, trendlines (six
          types, with forecasting, equation, and R-squared), and up/down
          bars.</li>
          <li>Axis bounds, units, logarithmic scale, and reverse order; gap
          width and overlap; pie angle, explosion, and doughnut hole; second
          plot size; histogram bins; smoothed lines; empty-cell handling;
          switch row/column; secondary axes; chart styles and color
          schemes.</li>
          <li>Recommended charts with reasons, Line/Column/Win-Loss sparklines,
          and PNG, SVG, and PDF export.</li>
        </ul>
        <h2>Not included</h2>
        <ul>
          <li><b>Map charts</b> need an online geography service, and Duddy
          Spreadsheet works entirely offline.</li>
          <li>Formatting one individual bar, slice, or label differently from
          the rest of its series.</li>
          <li>Dragging chart elements (titles, legend) to custom positions, and
          saving chart templates.</li>
          <li>Carrying charts in <code>.xlsx</code> files: use
          <code>.dsheet</code> to keep them.</li>
          <li>Logarithmic scales on 3-D charts.</li>
        </ul>
        """,
    ),
)

_TUTORIAL_KEYS = tuple(key for key, _, _ in TUTORIALS)

# Which lesson explains each chart family.
_FAMILY_TOPICS = {
    "Column": "column_bar",
    "Bar": "column_bar",
    "Line": "line_area",
    "Area": "line_area",
    "Pie": "pie",
    "X Y (Scatter)": "scatter",
    "Stock": "stock",
    "Surface": "surface",
    "Radar": "radar",
    "Treemap": "hierarchy",
    "Sunburst": "hierarchy",
    "Histogram": "statistics",
    "Box & Whisker": "statistics",
    "Waterfall": "flow",
    "Funnel": "flow",
    "Combo": "combo",
    "More": "line_area",
}


def topic_for_chart_type(chart_type: str | None) -> str:
    """Return the tutorial key that explains a chart type."""
    if chart_type not in CHART_TYPES:
        return "start"
    if chart_type == "heatmap":
        return "arrange"
    return _FAMILY_TOPICS.get(CHART_INFO[chart_type].family, "start")


def _reference_html() -> str:
    sections = [
        "<h1>Chart type reference</h1>",
        f"<p>All {len(CHART_TYPES)} chart types, in the order of Excel's "
        "All Charts gallery, with the data layout each one expects.</p>",
    ]
    for family, keys in CHART_FAMILIES:
        sections.append(f"<h2>{escape(family)}</h2><table>")
        sections.append("<tr><th>Chart</th><th>Purpose</th><th>Data layout</th></tr>")
        for key in keys:
            info = CHART_INFO[key]
            sections.append(
                f"<tr><td><b>{escape(info.label)}</b></td>"
                f"<td>{escape(info.summary)}</td>"
                f"<td>{escape(info.layout)}</td></tr>"
            )
        sections.append("</table>")
    return "".join(sections)


_QUICK_REFERENCE = """
<h1>Chart elements quick reference</h1>
<table>
<tr><th>Excel's command</th><th>Where it is here</th></tr>
<tr><td>Insert &gt; Recommended Charts</td><td>Insert &gt; Recommended Charts... (Chart Studio, Recommended tab)</td></tr>
<tr><td>Insert &gt; (chart icon)</td><td>Insert &gt; family &gt; type, or the ribbon galleries</td></tr>
<tr><td>Change Chart Type</td><td>Edit &gt; All Charts</td></tr>
<tr><td>Add Chart Element &gt; Axes, Axis Titles, Chart Title, Legend, Gridlines</td><td>Edit &gt; Elements</td></tr>
<tr><td>Add Chart Element &gt; Data Labels, Data Table</td><td>Edit &gt; Elements</td></tr>
<tr><td>Add Chart Element &gt; Error Bars, Trendline</td><td>Edit &gt; Elements</td></tr>
<tr><td>Add Chart Element &gt; Lines, Up/Down Bars</td><td>Edit &gt; Elements &gt; Lines and bars</td></tr>
<tr><td>Chart Styles, Change Colors</td><td>Edit &gt; Format &gt; Chart style, Colors</td></tr>
<tr><td>Format Axis</td><td>Edit &gt; Format &gt; Value axis</td></tr>
<tr><td>Format Data Series (gap width, overlap, smoothing, explosion, hole size)</td><td>Edit &gt; Format &gt; Series, Pie and doughnut</td></tr>
<tr><td>Select Data, Switch Row/Column, Hidden and Empty Cells</td><td>Edit &gt; Data</td></tr>
<tr><td>Chart Filters</td><td>Edit &gt; Data &gt; Series columns</td></tr>
<tr><td>Copy chart, Save as Picture</td><td>Copy Image, Export on the chart window</td></tr>
<tr><td>Insert &gt; Sparklines</td><td>Insert &gt; Sparklines</td></tr>
<tr><td>Sparkline &gt; Clear</td><td>Insert &gt; Sparklines &gt; Clear Sparklines</td></tr>
</table>
<h2>Keyboard</h2>
<table>
<tr><th>Key</th><th>Action</th></tr>
<tr><td>Alt+F1</td><td>Quick Chart from the selected data</td></tr>
<tr><td>Ctrl+Z / Ctrl+Y</td><td>Undo / redo chart and sparkline changes</td></tr>
<tr><td>F9</td><td>Recalculate; charts redraw with the new values</td></tr>
<tr><td>Enter</td><td>Apply a typed value in Chart Studio</td></tr>
</table>
"""


class ChartHelpDialog(QDialog):
    """Searchable tutorials, chart type reference, and quick reference."""

    def __init__(
        self,
        parent: Any = None,
        *,
        topic: str | None = None,
        chart_type: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("chartHelpDialog")
        self.setWindowTitle("Charts and Graphing Tutorial")
        self.resize(1060, 740)

        title = QLabel("Charts and Graphing Tutorial")
        title.setStyleSheet(
            "font-family: 'Aptos Display'; font-size: 20px; font-weight: 700; "
            "color: #17324d; padding: 6px 0;"
        )
        subtitle = QLabel(
            f"{len(TUTORIALS)} lessons covering all {len(CHART_TYPES)} chart "
            "types, every chart element, formatting, sparklines, and "
            "troubleshooting."
        )
        subtitle.setWordWrap(True)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("chartHelpTabs")
        self.tabs.addTab(self._tutorial_tab(), "Tutorials")
        self.tabs.addTab(self._browser_tab(_reference_html(), "chartTypeReference"), "Chart Types")
        self.tabs.addTab(self._browser_tab(_QUICK_REFERENCE, "chartQuickReference"), "Quick Reference")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(buttons)

        self._populate_tutorials()
        self.show_topic(topic or topic_for_chart_type(chart_type))

    def _tutorial_tab(self) -> QWidget:
        page = QWidget()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.search = QLineEdit()
        self.search.setObjectName("chartHelpSearch")
        self.search.setPlaceholderText("Search the tutorials, e.g. trendline")
        self.tutorial_list = QListWidget()
        self.tutorial_list.setObjectName("chartTutorialList")
        left_layout.addWidget(self.search)
        left_layout.addWidget(self.tutorial_list, 1)
        self.tutorial_detail = QTextBrowser()
        self.tutorial_detail.setObjectName("chartTutorialDetail")
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.tutorial_detail)
        splitter.setSizes((320, 720))
        layout = QVBoxLayout(page)
        layout.addWidget(splitter)
        self.search.textChanged.connect(self._populate_tutorials)
        self.tutorial_list.currentItemChanged.connect(self._show_tutorial)
        return page

    def _browser_tab(self, content: str, name: str) -> QWidget:
        page = QWidget()
        browser = QTextBrowser()
        browser.setObjectName(name)
        browser.setHtml(_styled_html(content))
        layout = QVBoxLayout(page)
        layout.addWidget(browser)
        return page

    @property
    def current_topic(self) -> str | None:
        """Return the key of the tutorial on screen."""
        item = self.tutorial_list.currentItem()
        return None if item is None else str(item.data(Qt.ItemDataRole.UserRole))

    def show_topic(self, key: str) -> None:
        """Select a tutorial by key, clearing any search that hides it."""
        if key not in _TUTORIAL_KEYS:
            key = "start"
        if self.search.text():
            self.search.clear()
        for row in range(self.tutorial_list.count()):
            item = self.tutorial_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                self.tabs.setCurrentIndex(0)
                self.tutorial_list.setCurrentItem(item)
                return

    def _populate_tutorials(self, unused: str = "") -> None:
        del unused
        selected = self.current_topic
        tokens = [token.casefold() for token in self.search.text().split()]
        self.tutorial_list.blockSignals(True)
        self.tutorial_list.clear()
        for key, title, content in TUTORIALS:
            searchable = f"{title} {content}".casefold()
            if tokens and not all(token in searchable for token in tokens):
                continue
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.tutorial_list.addItem(item)
            if key == selected:
                self.tutorial_list.setCurrentItem(item)
        self.tutorial_list.blockSignals(False)
        if self.tutorial_list.currentItem() is None and self.tutorial_list.count():
            self.tutorial_list.setCurrentRow(0)
        self._show_tutorial(self.tutorial_list.currentItem(), None)

    def _show_tutorial(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            self.tutorial_detail.setHtml(
                _styled_html("<p>No lesson matches that search.</p>")
            )
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        content = next(html for item_key, _, html in TUTORIALS if item_key == key)
        self.tutorial_detail.setHtml(_styled_html(content))


def _styled_html(content: str) -> str:
    return f"""
    <html><head><style>
    body {{ font-family: Aptos, sans-serif; color: #243746; line-height: 1.4; }}
    h1 {{ color: #17324d; font-size: 23px; margin-bottom: 8px; }}
    h2 {{ color: #0b6e75; font-size: 16px; margin-top: 18px; }}
    code, pre {{ font-family: Consolas, monospace; background: #eef3f4; }}
    pre {{ padding: 10px; border-left: 4px solid #0b6e75; white-space: pre-wrap; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th {{ background: #17324d; color: white; text-align: left; padding: 7px; }}
    td {{ border-bottom: 1px solid #dce8ea; padding: 7px; vertical-align: top; }}
    </style></head><body>{content}</body></html>
    """
