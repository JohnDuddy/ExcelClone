"""Comprehensive offline financial-function and modeling guide."""

from __future__ import annotations

from html import escape
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from duddysheet.core.financial_help import (
    FINANCIAL_HELP_CATEGORIES,
    FINANCIAL_HELP_ENTRIES,
    FinancialHelpEntry,
)
from duddysheet.core.financial_models import FINANCIAL_MODEL_CATALOG


_TUTORIALS = (
    (
        "Start here: financial modeling rules",
        """
        <h1>Start with four rules</h1>
        <h2>1. Match rates to periods</h2>
        <p>A monthly payment model needs a monthly rate and a number of months:
        <code>=PMT(6.5%/12,30*12,350000)</code>. Do not mix an annual rate with
        monthly periods.</p>
        <h2>2. Use cash-flow signs consistently</h2>
        <p>Money received and money paid must have opposite signs. A positive
        loan principal normally produces a negative payment. If every cash flow
        has the same sign, IRR and RATE have no financial solution.</p>
        <h2>3. Separate assumptions from formulas</h2>
        <p>Place assumptions in clearly labeled input cells, then reference those
        cells from schedules. Built-in models use blue text on yellow fill for
        inputs and green text for cross-sheet links.</p>
        <h2>4. Add checks before trusting outputs</h2>
        <p>Recalculate with F9, run <b>Financial &gt; Model Audit</b>, and add
        explicit checks such as assets minus liabilities and equity, beginning
        balance plus activity minus ending balance, and sources minus uses.</p>
        """,
    ),
    (
        "Build a loan amortization schedule",
        """
        <h1>Loan amortization</h1>
        <p>Example assumptions: principal in B2, annual rate in B3, years in B4,
        and payments per year in B5.</p>
        <ol>
          <li>Periodic payment: <code>=-PMT($B$3/$B$5,$B$4*$B$5,$B$2)</code></li>
          <li>Period 1 interest: <code>=-IPMT($B$3/$B$5,A9,$B$4*$B$5,$B$2)</code></li>
          <li>Period 1 principal: <code>=-PPMT($B$3/$B$5,A9,$B$4*$B$5,$B$2)</code></li>
          <li>Ending balance: <code>=MAX(0,C9-F9)</code></li>
          <li>Next beginning balance links to the prior ending balance.</li>
        </ol>
        <p>Copy the schedule through the full term. The final balance should be
        approximately zero; total principal should equal the original loan.
        Use CUMIPMT and CUMPRINC for annual summaries.</p>
        <p>The built-in <b>Loan Amortization</b> model creates all 360 monthly
        rows for a 30-year loan and is the fastest starting point.</p>
        """,
    ),
    (
        "Build a discounted cash flow valuation",
        """
        <h1>Discounted cash flow valuation</h1>
        <ol>
          <li>Forecast revenue, operating profit, taxes, depreciation, capital
          expenditure, and changes in working capital.</li>
          <li>Calculate unlevered free cash flow:
          <code>EBIT*(1-tax rate)+D&amp;A-capex-change in NWC</code>.</li>
          <li>Discount explicit cash flows:
          <code>=NPV(WACC,Year1:Year5)</code>. NPV starts at period 1.</li>
          <li>Calculate terminal value:
          <code>=Year5_FCF*(1+g)/(WACC-g)</code>. WACC must exceed g.</li>
          <li>Discount terminal value separately, add it to explicit present
          values, subtract net debt, and divide by diluted shares.</li>
        </ol>
        <p>Use one- and two-variable sensitivity tables for WACC and terminal
        growth. Do not use a single point estimate without checking the range of
        outcomes. The built-in DCF includes a five-year forecast and model checks.</p>
        """,
    ),
    (
        "Choose NPV, IRR, XNPV, XIRR, or MIRR",
        """
        <h1>Return-function decision guide</h1>
        <table>
          <tr><th>Situation</th><th>Use</th></tr>
          <tr><td>Equal periods, value at a selected discount rate</td><td>NPV</td></tr>
          <tr><td>Equal periods, solve the implied periodic return</td><td>IRR</td></tr>
          <tr><td>Irregular dates, value at an annual rate</td><td>XNPV</td></tr>
          <tr><td>Irregular dates, solve annualized return</td><td>XIRR</td></tr>
          <tr><td>Different financing and reinvestment assumptions</td><td>MIRR</td></tr>
        </table>
        <p>For NPV, add the time-zero investment outside the function:
        <code>=NPV(10%,C3:G3)+B3</code>. XNPV includes the first dated value.
        IRR and XIRR require at least one positive and one negative cash flow.</p>
        <p>Projects with several cash-flow sign changes can have multiple IRRs.
        In that case, graph NPV across discount rates and emphasize NPV or MIRR.</p>
        """,
    ),
    (
        "Price and analyze a coupon bond",
        """
        <h1>Coupon-bond workflow</h1>
        <p>Set settlement date, maturity date, coupon rate, market yield,
        redemption value, payment frequency, and day-count basis in separate cells.</p>
        <ol>
          <li>Clean price: <code>=PRICE(settlement,maturity,coupon,yield,100,frequency,basis)</code></li>
          <li>Yield from market price: <code>=YIELD(settlement,maturity,coupon,price,100,frequency,basis)</code></li>
          <li>Macaulay duration: <code>=DURATION(settlement,maturity,coupon,yield,frequency,basis)</code></li>
          <li>Modified duration: <code>=MDURATION(settlement,maturity,coupon,yield,frequency,basis)</code></li>
          <li>Accrued interest: <code>=ACCRINT(issue,first_coupon,settlement,coupon,par,frequency,basis,TRUE)</code></li>
        </ol>
        <p>Frequency must be 1, 2, or 4. Basis must match the security's market
        convention. PRICE is clean price, so add accrued interest when a dirty
        settlement amount is required. Modified duration estimates small price
        changes; it does not capture convexity.</p>
        """,
    ),
    (
        "Create a depreciation schedule",
        """
        <h1>Depreciation methods</h1>
        <p>Use the method required by the accounting, tax, or analytical purpose:</p>
        <ul>
          <li><b>SLN</b>: equal expense each period.</li>
          <li><b>SYD</b>: accelerated expense based on remaining life.</li>
          <li><b>DB</b>: fixed declining rate with optional first-year months.</li>
          <li><b>DDB</b>: selected declining factor, normally 2.</li>
          <li><b>VDB</b>: fractional intervals and optional switch to straight line.</li>
        </ul>
        <p>Build one row per period with beginning book value, depreciation, and
        ending book value. The ending value must not fall below salvage, and total
        depreciation must not exceed cost minus salvage.</p>
        """,
    ),
    (
        "Use Goal Seek, sensitivity, and scenarios",
        """
        <h1>What-if analysis</h1>
        <h2>Goal Seek</h2>
        <p>Select a formula output, choose one numeric input, and specify a target.
        Duddy Spreadsheet solves on a copy of the workbook. The live input changes only
        after confirmation and the change is undoable.</p>
        <h2>Sensitivity tables</h2>
        <p>Use one variable for a single assumption range, such as revenue growth.
        Use two variables for combinations such as WACC by terminal growth or
        rent by vacancy. Write results to an unused area; the entire table is one
        undoable edit.</p>
        <h2>Scenarios</h2>
        <p>Enter one line per case:
        <code>Downside: B4=2%, B5=18%, B9=11%</code>. Choose output cells and
        compare base, downside, and upside cases without overwriting assumptions.</p>
        """,
    ),
    (
        "Audit and troubleshoot a model",
        """
        <h1>Model audit workflow</h1>
        <ol>
          <li>Press F9 to recalculate the entire workbook.</li>
          <li>Open <b>Financial &gt; Model Audit</b>.</li>
          <li>Resolve formula errors and circular references first.</li>
          <li>Review blank precedents and uncalculated formulas.</li>
          <li>Inspect embedded constants and move real assumptions to labeled cells.</li>
          <li>Confirm balance, roll-forward, sources-and-uses, and cash checks.</li>
        </ol>
        <p><b>#VALUE!</b> usually indicates the wrong data type or mismatched
        ranges. <b>#NUM!</b> indicates an invalid financial domain or a solver
        that could not find a result. <b>#DIV/0!</b> indicates a zero denominator.
        <b>#CIRC!</b> identifies a circular dependency.</p>
        """,
    ),
    (
        "Analyze a rental property",
        """
        <h1>Rental-property workflow</h1>
        <ol>
          <li>Calculate effective gross income from rent, vacancy, and other income.</li>
          <li>Subtract operating expenses to derive NOI before financing.</li>
          <li>Use PMT for debt service and FV for the remaining mortgage balance.</li>
          <li>Forecast property value, selling costs, and net sale proceeds.</li>
          <li>Place initial equity at time zero and calculate levered IRR from the
          full cash-flow range.</li>
        </ol>
        <p>Stress-test rent, vacancy, operating expenses, mortgage rate, exit value,
        and selling costs. Keep appreciation separate from operating performance.
        The built-in Rental Property model implements this structure.</p>
        """,
    ),
)


_QUICK_REFERENCE = """
<h1>Financial quick reference</h1>
<h2>Cash-flow signs</h2>
<table>
  <tr><th>Item</th><th>Common sign</th></tr>
  <tr><td>Loan proceeds or investment received</td><td>Positive</td></tr>
  <tr><td>Payment, purchase, or investment made</td><td>Negative</td></tr>
  <tr><td>Sale proceeds or distribution received</td><td>Positive</td></tr>
</table>
<h2>Period matching</h2>
<table>
  <tr><th>Frequency</th><th>Periodic rate</th><th>Number of periods</th></tr>
  <tr><td>Monthly</td><td>annual rate / 12</td><td>years * 12</td></tr>
  <tr><td>Quarterly</td><td>annual rate / 4</td><td>years * 4</td></tr>
  <tr><td>Semiannual</td><td>annual rate / 2</td><td>years * 2</td></tr>
  <tr><td>Annual</td><td>annual rate</td><td>years</td></tr>
</table>
<h2>Payment type</h2>
<p><b>0</b> means payment at period end and is the default. <b>1</b> means
payment at period beginning.</p>
<h2>Coupon frequency</h2>
<p><b>1</b> annual, <b>2</b> semiannual, <b>4</b> quarterly.</p>
<h2>Day-count basis</h2>
<table>
  <tr><th>Basis</th><th>Convention</th><th>Typical interpretation</th></tr>
  <tr><td>0</td><td>US 30/360</td><td>US corporate and municipal conventions</td></tr>
  <tr><td>1</td><td>Actual/actual</td><td>Actual days and actual year length</td></tr>
  <tr><td>2</td><td>Actual/360</td><td>Actual days over a 360-day year</td></tr>
  <tr><td>3</td><td>Actual/365</td><td>Actual days over a 365-day year</td></tr>
  <tr><td>4</td><td>European 30/360</td><td>European 30-day month convention</td></tr>
</table>
<h2>Common errors</h2>
<table>
  <tr><th>Error</th><th>First checks</th></tr>
  <tr><td>#VALUE!</td><td>Text in numeric inputs, mismatched value/date ranges</td></tr>
  <tr><td>#NUM!</td><td>Invalid dates, frequency, basis, period, or no solver root</td></tr>
  <tr><td>#DIV/0!</td><td>Zero life, denominator, fraction, payment, or shares</td></tr>
  <tr><td>#CIRC!</td><td>Formula depends on itself directly or indirectly</td></tr>
</table>
"""


class FinancialHelpDialog(QDialog):
    """Searchable function reference, tutorials, quick guide, and model guide."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setObjectName("financialHelpDialog")
        self.setWindowTitle("Financial Functions and Modeling Guide")
        self.resize(1040, 720)
        self._entries = {entry.name: entry for entry in FINANCIAL_HELP_ENTRIES}

        title = QLabel("Financial Functions and Modeling Guide")
        title.setObjectName("financialHelpTitle")
        title.setStyleSheet(
            "font-family: 'Aptos Display'; font-size: 20px; font-weight: 700; "
            "color: #17324d; padding: 6px 0;"
        )
        subtitle = QLabel(
            "Offline reference for all 46 financial functions, practical "
            "tutorials, conventions, models, and troubleshooting."
        )
        subtitle.setWordWrap(True)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("financialHelpTabs")
        self.tabs.addTab(self._function_tab(), "Function Reference")
        self.tabs.addTab(self._tutorial_tab(), "Tutorials")
        self.tabs.addTab(self._quick_reference_tab(), "Quick Reference")
        self.tabs.addTab(self._models_tab(), "Built-in Models")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(buttons)

        self._populate_functions()
        self._populate_tutorials()

    @property
    def selected_entry(self) -> FinancialHelpEntry | None:
        """Return the selected financial help entry."""
        item = self.function_list.currentItem()
        return (
            self._entries.get(str(item.data(Qt.ItemDataRole.UserRole)))
            if item is not None
            else None
        )

    def _function_tab(self) -> QWidget:
        page = QWidget()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.search = QLineEdit()
        self.search.setObjectName("financialHelpSearch")
        self.search.setPlaceholderText(
            "Search name, purpose, syntax, example, or related function"
        )
        self.category = QComboBox()
        self.category.setObjectName("financialHelpCategory")
        self.category.addItem("All financial functions")
        self.category.addItems(FINANCIAL_HELP_CATEGORIES)
        self.function_list = QListWidget()
        self.function_list.setObjectName("financialHelpFunctionList")
        left_layout.addWidget(self.search)
        left_layout.addWidget(self.category)
        left_layout.addWidget(self.function_list, 1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.function_detail = QTextBrowser()
        self.function_detail.setObjectName("financialHelpFunctionDetail")
        self.function_detail.setOpenExternalLinks(False)
        self.copy_example = QPushButton("Copy Example Formula")
        self.copy_example.setObjectName("copyFinancialExampleButton")
        right_layout.addWidget(self.function_detail, 1)
        right_layout.addWidget(self.copy_example)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes((320, 700))
        layout = QVBoxLayout(page)
        layout.addWidget(splitter)

        self.search.textChanged.connect(self._populate_functions)
        self.category.currentTextChanged.connect(self._populate_functions)
        self.function_list.currentItemChanged.connect(self._show_function)
        self.copy_example.clicked.connect(self._copy_selected_example)
        return page

    def _tutorial_tab(self) -> QWidget:
        page = QWidget()
        self.tutorial_list = QListWidget()
        self.tutorial_list.setObjectName("financialTutorialList")
        self.tutorial_detail = QTextBrowser()
        self.tutorial_detail.setObjectName("financialTutorialDetail")
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.tutorial_list)
        splitter.addWidget(self.tutorial_detail)
        splitter.setSizes((300, 720))
        layout = QVBoxLayout(page)
        layout.addWidget(splitter)
        self.tutorial_list.currentRowChanged.connect(self._show_tutorial)
        return page

    def _quick_reference_tab(self) -> QWidget:
        page = QWidget()
        browser = QTextBrowser()
        browser.setObjectName("financialQuickReference")
        browser.setHtml(self._styled_html(_QUICK_REFERENCE))
        layout = QVBoxLayout(page)
        layout.addWidget(browser)
        return page

    def _models_tab(self) -> QWidget:
        page = QWidget()
        browser = QTextBrowser()
        browser.setObjectName("financialModelsGuide")
        sections = [
            "<h1>Built-in financial models</h1>",
            (
                "<p>Open <b>Financial &gt; New Financial Model</b>, choose a "
                "model, and replace the sample assumptions with your own. Press "
                "F9 and run Model Audit before relying on the result.</p>"
            ),
        ]
        guidance = {
            "dcf": "Use for enterprise and equity valuation. Review WACC, terminal growth, net debt, and diluted shares.",
            "three_statement": "Use for linked income statement, balance sheet, and cash flow forecasting. Keep balance checks at zero.",
            "lbo": "Use for entry valuation, debt paydown, exit proceeds, sponsor MOIC, and IRR. Stress entry/exit multiples and debt capacity.",
            "loan": "Use for a full monthly payment schedule. Replace principal, rate, term, frequency, and first payment date.",
            "rental": "Use for NOI, debt service, mortgage balance, sale proceeds, levered IRR, and equity multiple.",
            "budget": "Use for monthly revenue, cost, payroll, operating expense, actual-versus-budget variance, and annual margin.",
            "financial_lab": "Use as a guided, editable training workbook. It provides synthetic inputs, all 46 financial functions, 30 common calculations, and 12 charts across four galleries.",
        }
        for template in FINANCIAL_MODEL_CATALOG:
            sections.append(f"<h2>{escape(template.name)}</h2>")
            sections.append(f"<p>{escape(template.description)}</p>")
            sections.append(f"<p>{escape(guidance[template.key])}</p>")
            sections.append(
                f"<p><b>Primary output:</b> <code>{escape(template.primary_output)}</code></p>"
            )
        browser.setHtml(self._styled_html("".join(sections)))
        layout = QVBoxLayout(page)
        layout.addWidget(browser)
        return page

    def _populate_functions(self, unused: str = "") -> None:
        del unused
        selected_name = self.selected_entry.name if self.selected_entry else None
        tokens = tuple(
            token.casefold() for token in self.search.text().split() if token
        )
        selected_category = self.category.currentText()
        self.function_list.clear()
        for entry in FINANCIAL_HELP_ENTRIES:
            if (
                selected_category != "All financial functions"
                and entry.category != selected_category
            ):
                continue
            searchable = " ".join(
                (
                    entry.name,
                    entry.category,
                    entry.syntax,
                    entry.summary,
                    entry.use_when,
                    entry.example,
                    " ".join(entry.related),
                    " ".join(entry.notes),
                )
            ).casefold()
            if tokens and not all(token in searchable for token in tokens):
                continue
            item = QListWidgetItem(f"{entry.name}  |  {entry.category}")
            item.setData(Qt.ItemDataRole.UserRole, entry.name)
            self.function_list.addItem(item)
            if entry.name == selected_name:
                self.function_list.setCurrentItem(item)
        if self.function_list.currentItem() is None and self.function_list.count():
            self.function_list.setCurrentRow(0)

    def _show_function(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        entry = (
            self._entries.get(str(current.data(Qt.ItemDataRole.UserRole)))
            if current is not None
            else None
        )
        self.copy_example.setEnabled(entry is not None)
        if entry is None:
            self.function_detail.clear()
            return
        notes = "".join(f"<li>{escape(note)}</li>" for note in entry.notes)
        related = ", ".join(entry.related)
        content = f"""
        <h1>{escape(entry.name)}</h1>
        <p class="category">{escape(entry.category)}</p>
        <h2>Syntax</h2>
        <pre>{escape(entry.syntax)}</pre>
        <h2>What it does</h2>
        <p>{escape(entry.summary)}</p>
        <h2>When to use it</h2>
        <p>{escape(entry.use_when)}</p>
        <h2>Example</h2>
        <pre>{escape(entry.example)}</pre>
        <h2>Important notes</h2>
        <ul>{notes}</ul>
        <h2>Related functions</h2>
        <p>{escape(related)}</p>
        """
        self.function_detail.setHtml(self._styled_html(content))

    def _copy_selected_example(self) -> None:
        entry = self.selected_entry
        if entry is not None:
            QApplication.clipboard().setText(entry.example)

    def _populate_tutorials(self) -> None:
        for title, _ in _TUTORIALS:
            self.tutorial_list.addItem(title)
        self.tutorial_list.setCurrentRow(0)

    def _show_tutorial(self, row: int) -> None:
        if 0 <= row < len(_TUTORIALS):
            self.tutorial_detail.setHtml(
                self._styled_html(_TUTORIALS[row][1])
            )

    @staticmethod
    def _styled_html(content: str) -> str:
        return f"""
        <html><head><style>
        body {{ font-family: Aptos, sans-serif; color: #243746; line-height: 1.4; }}
        h1 {{ color: #17324d; font-size: 23px; margin-bottom: 8px; }}
        h2 {{ color: #2f6f6d; font-size: 16px; margin-top: 18px; }}
        code, pre {{ font-family: Consolas, monospace; background: #eef3f4; }}
        pre {{ padding: 10px; border-left: 4px solid #c69214; white-space: pre-wrap; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th {{ background: #17324d; color: white; text-align: left; padding: 7px; }}
        td {{ border-bottom: 1px solid #dce8ea; padding: 7px; }}
        .category {{ color: #2f6f6d; font-weight: 700; }}
        </style></head><body>{content}</body></html>
        """
