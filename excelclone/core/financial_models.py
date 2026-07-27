"""Built-in, editable financial-model workbooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from excelclone.core.cell import BorderStyle, CellFormat
from excelclone.core.chart import ChartSpec
from excelclone.core.engine import FormulaEngine
from excelclone.core.refs import CellReference, RangeReference, parse_a1
from excelclone.core.sheet import Sheet
from excelclone.core.workbook import Workbook


@dataclass(frozen=True, slots=True)
class FinancialModelTemplate:
    """Metadata for one built-in financial model."""

    key: str
    name: str
    description: str
    primary_output: str


FINANCIAL_MODEL_CATALOG = (
    FinancialModelTemplate(
        "dcf",
        "Discounted Cash Flow",
        "Five-year unlevered forecast, terminal value, enterprise value, and equity value.",
        "Valuation!B15",
    ),
    FinancialModelTemplate(
        "three_statement",
        "Three-Statement Forecast",
        "Linked income statement, balance sheet, cash flow statement, and balance check.",
        "'Balance Sheet'!F16",
    ),
    FinancialModelTemplate(
        "lbo",
        "Leveraged Buyout",
        "Entry sources, operating case, debt paydown, exit proceeds, MOIC, and IRR.",
        "Returns!B12",
    ),
    FinancialModelTemplate(
        "loan",
        "Loan Amortization",
        "Loan summary plus a complete monthly principal and interest schedule.",
        "Summary!B10",
    ),
    FinancialModelTemplate(
        "rental",
        "Rental Property",
        "Property operations, mortgage balance, sale proceeds, levered IRR, and equity multiple.",
        "Returns!B8",
    ),
    FinancialModelTemplate(
        "budget",
        "Budget and Forecast",
        "Monthly operating budget, editable actuals, variance analysis, and annual dashboard.",
        "Dashboard!B8",
    ),
    FinancialModelTemplate(
        "financial_lab",
        "Financial Calculations Lab",
        "Synthetic sample data, 76 live calculations, and 12 editable analytical charts.",
        "Guide!B6",
    ),
)

_BUILDERS: dict[str, Callable[[], Workbook]] = {}

_THIN_GRAY = BorderStyle("thin", "#b8c2cc")
TITLE = CellFormat(
    font_family="Aptos Display",
    font_size=18,
    bold=True,
    font_color="#ffffff",
    fill_color="#17324d",
    vertical_alignment="center",
)
SECTION = CellFormat(
    font_family="Aptos Display",
    font_size=11,
    bold=True,
    font_color="#ffffff",
    fill_color="#2f6f6d",
    bottom_border=_THIN_GRAY,
)
HEADER = CellFormat(
    bold=True,
    font_color="#17324d",
    fill_color="#dce8ea",
    horizontal_alignment="center",
    bottom_border=_THIN_GRAY,
)
LABEL = CellFormat(font_color="#243746")
INPUT = CellFormat(
    font_color="#0066cc",
    fill_color="#fff4cc",
    number_format="#,##0.00",
    bottom_border=_THIN_GRAY,
)
FORMULA = CellFormat(
    font_color="#000000",
    number_format="#,##0.00;[Red](#,##0.00);-",
)
LINK = CellFormat(
    font_color="#008000",
    number_format="#,##0.00;[Red](#,##0.00);-",
)
CURRENCY = CellFormat(
    number_format="$#,##0;[Red]($#,##0);-",
)
PERCENT = CellFormat(number_format="0.0%")
INPUT_PERCENT = CellFormat(
    font_color="#0066cc",
    fill_color="#fff4cc",
    number_format="0.0%",
    bottom_border=_THIN_GRAY,
)
OUTPUT = CellFormat(
    font_size=12,
    bold=True,
    font_color="#17324d",
    fill_color="#d7ebe3",
    number_format="$#,##0.00;[Red]($#,##0.00);-",
    top_border=BorderStyle("double", "#2f6f6d"),
)
CHECK = CellFormat(
    bold=True,
    number_format="#,##0.00;[Red](#,##0.00);-",
    top_border=_THIN_GRAY,
)
DATE_FORMAT = CellFormat(number_format="mmm-yy")

FINANCIAL_LAB_FUNCTIONS = (
    (
        "Loans and annuities",
        "PMT",
        "Monthly payment on a fixed-rate mortgage",
        "=-PMT('Sample Data'!B5/'Sample Data'!B7,'Sample Data'!B6*'Sample Data'!B7,'Sample Data'!B4)",
        "currency",
    ),
    (
        "Loans and annuities",
        "IPMT",
        "Interest portion of payment 37",
        "=-IPMT('Sample Data'!B5/'Sample Data'!B7,'Sample Data'!B8,'Sample Data'!B6*'Sample Data'!B7,'Sample Data'!B4)",
        "currency",
    ),
    (
        "Loans and annuities",
        "PPMT",
        "Principal portion of payment 37",
        "=-PPMT('Sample Data'!B5/'Sample Data'!B7,'Sample Data'!B8,'Sample Data'!B6*'Sample Data'!B7,'Sample Data'!B4)",
        "currency",
    ),
    (
        "Loans and annuities",
        "PV",
        "Present value of a fixed payment stream",
        "=PV('Sample Data'!B5/'Sample Data'!B7,'Sample Data'!B6*'Sample Data'!B7,-2500)",
        "currency",
    ),
    (
        "Loans and annuities",
        "FV",
        "Future value of an opening balance plus contributions",
        "=FV('Sample Data'!B14/'Sample Data'!B15,'Sample Data'!B11*'Sample Data'!B15,-1000,-'Sample Data'!B9)",
        "currency",
    ),
    (
        "Loans and annuities",
        "RATE",
        "Annualized rate implied by a $2,500 payment",
        "=RATE('Sample Data'!B6*'Sample Data'!B7,-2500,'Sample Data'!B4)*'Sample Data'!B7",
        "percent",
    ),
    (
        "Loans and annuities",
        "NPER",
        "Years needed to repay at a $2,500 payment",
        "=NPER('Sample Data'!B5/'Sample Data'!B7,-2500,'Sample Data'!B4)/'Sample Data'!B7",
        "number",
    ),
    (
        "Loans and annuities",
        "CUMIPMT",
        "Interest paid during the first loan year",
        "=-CUMIPMT('Sample Data'!B5/'Sample Data'!B7,'Sample Data'!B6*'Sample Data'!B7,'Sample Data'!B4,1,12,0)",
        "currency",
    ),
    (
        "Loans and annuities",
        "CUMPRINC",
        "Principal repaid during the first loan year",
        "=-CUMPRINC('Sample Data'!B5/'Sample Data'!B7,'Sample Data'!B6*'Sample Data'!B7,'Sample Data'!B4,1,12,0)",
        "currency",
    ),
    (
        "Loans and annuities",
        "ISPMT",
        "Simple-interest allocation for period 36",
        "=-ISPMT('Sample Data'!B5/'Sample Data'!B7,36,'Sample Data'!B6*'Sample Data'!B7,'Sample Data'!B4)",
        "currency",
    ),
    (
        "Rates and growth",
        "EFFECT",
        "Effective annual rate from a nominal rate",
        "=EFFECT('Sample Data'!B14,'Sample Data'!B15)",
        "percent",
    ),
    (
        "Rates and growth",
        "NOMINAL",
        "Nominal rate recovered from an effective rate",
        "=NOMINAL(EFFECT('Sample Data'!B14,'Sample Data'!B15),'Sample Data'!B15)",
        "percent",
    ),
    (
        "Rates and growth",
        "FVSCHEDULE",
        "Future value under a changing rate schedule",
        "=FVSCHEDULE('Sample Data'!B9,'Sample Data'!J4:J7)",
        "currency",
    ),
    (
        "Rates and growth",
        "RRI",
        "Compound rate required to double the investment",
        "=RRI('Sample Data'!B11,'Sample Data'!B9,'Sample Data'!B10)",
        "percent",
    ),
    (
        "Rates and growth",
        "PDURATION",
        "Years required to double at the finance rate",
        "=PDURATION('Sample Data'!B12,'Sample Data'!B9,'Sample Data'!B10)",
        "number",
    ),
    (
        "Cash flow and returns",
        "NPV",
        "Periodic net present value including time-zero cash flow",
        "=NPV('Sample Data'!B12,'Sample Data'!E5:E9)+'Sample Data'!E4",
        "currency",
    ),
    (
        "Cash flow and returns",
        "IRR",
        "Periodic internal rate of return",
        "=IRR('Sample Data'!E4:E9)",
        "percent",
    ),
    (
        "Cash flow and returns",
        "XNPV",
        "Date-aware net present value",
        "=XNPV('Sample Data'!B12,'Sample Data'!H4:H7,'Sample Data'!G4:G7)",
        "currency",
    ),
    (
        "Cash flow and returns",
        "XIRR",
        "Date-aware internal rate of return",
        "=XIRR('Sample Data'!H4:H7,'Sample Data'!G4:G7)",
        "percent",
    ),
    (
        "Cash flow and returns",
        "MIRR",
        "Return using separate finance and reinvestment rates",
        "=MIRR('Sample Data'!E4:E9,'Sample Data'!B12,'Sample Data'!B13)",
        "percent",
    ),
    (
        "Depreciation",
        "SLN",
        "Straight-line annual depreciation",
        "=SLN('Sample Data'!B16,'Sample Data'!B17,'Sample Data'!B18)",
        "currency",
    ),
    (
        "Depreciation",
        "SYD",
        "Sum-of-years-digits depreciation",
        "=SYD('Sample Data'!B16,'Sample Data'!B17,'Sample Data'!B18,'Sample Data'!B19)",
        "currency",
    ),
    (
        "Depreciation",
        "DB",
        "Fixed declining-balance depreciation",
        "=DB('Sample Data'!B16,'Sample Data'!B17,'Sample Data'!B18,'Sample Data'!B19)",
        "currency",
    ),
    (
        "Depreciation",
        "DDB",
        "Double-declining-balance depreciation",
        "=DDB('Sample Data'!B16,'Sample Data'!B17,'Sample Data'!B18,'Sample Data'!B19)",
        "currency",
    ),
    (
        "Depreciation",
        "VDB",
        "Variable declining balance across a fractional interval",
        "=VDB('Sample Data'!B16,'Sample Data'!B17,'Sample Data'!B18,1.5,4.25,1.5,FALSE)",
        "currency",
    ),
    (
        "Fractional quotations",
        "DOLLARDE",
        "Convert a 32nds quotation to decimal dollars",
        "=DOLLARDE(101.08,32)",
        "number",
    ),
    (
        "Fractional quotations",
        "DOLLARFR",
        "Convert decimal dollars to a 32nds quotation",
        "=DOLLARFR(101.25,32)",
        "number",
    ),
    (
        "Bonds",
        "PRICE",
        "Price a coupon bond per $100 face value",
        "=PRICE('Sample Data'!B20,'Sample Data'!B21,'Sample Data'!B22,'Sample Data'!B23,'Sample Data'!B24,'Sample Data'!B25,'Sample Data'!B26)",
        "number",
    ),
    (
        "Bonds",
        "YIELD",
        "Yield implied by a coupon bond market price",
        "=YIELD('Sample Data'!B20,'Sample Data'!B21,'Sample Data'!B22,'Sample Data'!B34,'Sample Data'!B24,'Sample Data'!B25,'Sample Data'!B26)",
        "percent",
    ),
    (
        "Bonds",
        "DURATION",
        "Macaulay duration of a coupon bond",
        "=DURATION('Sample Data'!B20,'Sample Data'!B21,'Sample Data'!B22,'Sample Data'!B23,'Sample Data'!B25,'Sample Data'!B26)",
        "number",
    ),
    (
        "Bonds",
        "MDURATION",
        "Modified duration of a coupon bond",
        "=MDURATION('Sample Data'!B20,'Sample Data'!B21,'Sample Data'!B22,'Sample Data'!B23,'Sample Data'!B25,'Sample Data'!B26)",
        "number",
    ),
    (
        "Bonds",
        "ACCRINT",
        "Accrued interest from issue through settlement",
        "=ACCRINT('Sample Data'!B46,'Sample Data'!B47,'Sample Data'!B20,'Sample Data'!B22,'Sample Data'!B33,'Sample Data'!B25,'Sample Data'!B26)",
        "currency",
    ),
    (
        "Bonds",
        "COUPDAYBS",
        "Days from previous coupon to settlement",
        "=COUPDAYBS('Sample Data'!B20,'Sample Data'!B21,'Sample Data'!B25,'Sample Data'!B26)",
        "number",
    ),
    (
        "Bonds",
        "COUPDAYS",
        "Days in the coupon period",
        "=COUPDAYS('Sample Data'!B20,'Sample Data'!B21,'Sample Data'!B25,'Sample Data'!B26)",
        "number",
    ),
    (
        "Bonds",
        "COUPDAYSNC",
        "Days from settlement to next coupon",
        "=COUPDAYSNC('Sample Data'!B20,'Sample Data'!B21,'Sample Data'!B25,'Sample Data'!B26)",
        "number",
    ),
    (
        "Bonds",
        "COUPNCD",
        "Next coupon date",
        "=COUPNCD('Sample Data'!B20,'Sample Data'!B21,'Sample Data'!B25,'Sample Data'!B26)",
        "date",
    ),
    (
        "Bonds",
        "COUPNUM",
        "Coupon payments remaining",
        "=COUPNUM('Sample Data'!B20,'Sample Data'!B21,'Sample Data'!B25,'Sample Data'!B26)",
        "number",
    ),
    (
        "Bonds",
        "COUPPCD",
        "Previous coupon date",
        "=COUPPCD('Sample Data'!B20,'Sample Data'!B21,'Sample Data'!B25,'Sample Data'!B26)",
        "date",
    ),
    (
        "Discount securities",
        "DISC",
        "Discount rate from price and redemption",
        "=DISC('Sample Data'!B27,'Sample Data'!B28,'Sample Data'!B30,'Sample Data'!B24,1)",
        "percent",
    ),
    (
        "Discount securities",
        "INTRATE",
        "Interest rate on a fully invested security",
        "=INTRATE('Sample Data'!B27,'Sample Data'!B28,'Sample Data'!B31,'Sample Data'!B32,1)",
        "percent",
    ),
    (
        "Discount securities",
        "PRICEDISC",
        "Price from a quoted discount rate",
        "=PRICEDISC('Sample Data'!B27,'Sample Data'!B28,'Sample Data'!B29,'Sample Data'!B24,1)",
        "number",
    ),
    (
        "Discount securities",
        "RECEIVED",
        "Amount received at maturity",
        "=RECEIVED('Sample Data'!B27,'Sample Data'!B28,'Sample Data'!B31,'Sample Data'!B29,1)",
        "currency",
    ),
    (
        "Discount securities",
        "YIELDDISC",
        "Annual yield of a discounted security",
        "=YIELDDISC('Sample Data'!B27,'Sample Data'!B28,'Sample Data'!B30,'Sample Data'!B24,1)",
        "percent",
    ),
    (
        "Treasury bills",
        "TBILLEQ",
        "Bond-equivalent yield of a Treasury bill",
        "=TBILLEQ('Sample Data'!B27,'Sample Data'!B28,'Sample Data'!B29)",
        "percent",
    ),
    (
        "Treasury bills",
        "TBILLPRICE",
        "Treasury bill price per $100 face value",
        "=TBILLPRICE('Sample Data'!B27,'Sample Data'!B28,'Sample Data'!B29)",
        "number",
    ),
    (
        "Treasury bills",
        "TBILLYIELD",
        "Treasury bill yield from market price",
        "=TBILLYIELD('Sample Data'!B27,'Sample Data'!B28,'Sample Data'!B30)",
        "percent",
    ),
)

COMMON_FINANCIAL_METRICS = (
    ("Growth", "Revenue growth", "Latest year-over-year growth", "='Sample Data'!E18/'Sample Data'!E17-1", "percent"),
    ("Growth", "Revenue CAGR", "Compound annual growth since 2022", "=('Sample Data'!E18/'Sample Data'!E14)^(1/('Sample Data'!D18-'Sample Data'!D14))-1", "percent"),
    ("Profitability", "Gross profit", "Revenue less cost of goods sold", "='Sample Data'!E18-'Sample Data'!F18", "currency"),
    ("Profitability", "Gross margin", "Gross profit divided by revenue", "=('Sample Data'!E18-'Sample Data'!F18)/'Sample Data'!E18", "percent"),
    ("Profitability", "EBITDA margin", "EBITDA divided by revenue", "='Sample Data'!G18/'Sample Data'!E18", "percent"),
    ("Profitability", "Net margin", "Net income divided by revenue", "='Sample Data'!H18/'Sample Data'!E18", "percent"),
    ("Returns", "Return on assets", "Net income divided by total assets", "='Sample Data'!H18/'Sample Data'!I18", "percent"),
    ("Returns", "Return on equity", "Net income divided by shareholders' equity", "='Sample Data'!H18/'Sample Data'!J18", "percent"),
    ("Efficiency", "Asset turnover", "Revenue generated per dollar of assets", "='Sample Data'!E18/'Sample Data'!I18", "number"),
    ("Cash flow", "Operating cash flow margin", "Operating cash flow divided by revenue", "='Sample Data'!K18/'Sample Data'!E18", "percent"),
    ("Cash flow", "Free cash flow", "Operating cash flow less capital expenditures", "=SUM('Sample Data'!K18:L18)", "currency"),
    ("Cash flow", "Free cash flow margin", "Free cash flow divided by revenue", "=SUM('Sample Data'!K18:L18)/'Sample Data'!E18", "percent"),
    ("Liquidity", "Current ratio", "Current assets divided by current liabilities", "='Sample Data'!B35/'Sample Data'!B37", "number"),
    ("Liquidity", "Quick ratio", "Current assets excluding inventory", "=('Sample Data'!B35-'Sample Data'!B36)/'Sample Data'!B37", "number"),
    ("Liquidity", "Cash ratio", "Cash divided by current liabilities", "='Sample Data'!B38/'Sample Data'!B37", "number"),
    ("Leverage", "Debt to equity", "Total debt divided by shareholders' equity", "='Sample Data'!B39/'Sample Data'!J18", "number"),
    ("Leverage", "Debt to assets", "Total debt divided by total assets", "='Sample Data'!B39/'Sample Data'!I18", "percent"),
    ("Leverage", "Interest coverage", "EBIT divided by interest expense", "='Sample Data'!B40/'Sample Data'!B41", "number"),
    ("Per share", "Earnings per share", "Net income divided by diluted shares", "='Sample Data'!H18/'Sample Data'!B43", "currency"),
    ("Per share", "Dividend payout ratio", "Dividends divided by net income", "='Sample Data'!B44/'Sample Data'!H18", "percent"),
    ("Per share", "Dividend yield", "Dividend per share divided by market price", "=('Sample Data'!B44/'Sample Data'!B43)/'Sample Data'!B45", "percent"),
    ("Valuation", "Price / earnings", "Market price divided by earnings per share", "='Sample Data'!B45/('Sample Data'!H18/'Sample Data'!B43)", "number"),
    ("Statistics", "Average revenue", "Mean annual revenue", "=AVERAGE('Sample Data'!E14:E18)", "currency"),
    ("Statistics", "Median revenue", "Middle annual revenue observation", "=MEDIAN('Sample Data'!E14:E18)", "currency"),
    ("Statistics", "Revenue standard deviation", "Sample volatility of annual revenue", "=STDEV('Sample Data'!E14:E18)", "currency"),
    ("Statistics", "Revenue variance", "Sample variance of annual revenue", "=VAR('Sample Data'!E14:E18)", "number"),
    ("Statistics", "Minimum revenue", "Lowest annual revenue", "=MIN('Sample Data'!E14:E18)", "currency"),
    ("Statistics", "Maximum revenue", "Highest annual revenue", "=MAX('Sample Data'!E14:E18)", "currency"),
    ("Statistics", "Revenue / EBITDA correlation", "Linear relationship between revenue and EBITDA", "=CORREL('Sample Data'!E14:E18,'Sample Data'!G14:G18)", "number"),
    ("Forecasting", "Forecast 2027 revenue", "Linear forecast from the historical series", "=FORECAST(2027,'Sample Data'!E14:E18,'Sample Data'!D14:D18)", "currency"),
)


def create_financial_model(key: str) -> Workbook:
    """Create and calculate one built-in financial model."""
    try:
        workbook = _BUILDERS[key]()
    except KeyError:
        available = ", ".join(template.key for template in FINANCIAL_MODEL_CATALOG)
        raise ValueError(f"Unknown financial model {key!r}; choose {available}") from None
    FormulaEngine(workbook).rebuild_index()
    workbook.active_sheet = 0
    return workbook


def _workbook(*sheet_names: str) -> Workbook:
    workbook = Workbook(create_default=False)
    for name in sheet_names:
        workbook.add_sheet(name)
    return workbook


def _cell(sheet: Sheet, reference: str, value: Any, style: CellFormat = LABEL) -> None:
    parsed = parse_a1(reference)
    assert isinstance(parsed, CellReference)
    sheet.set_cell(parsed.row, parsed.column, value, cell_format=style)


def _title(sheet: Sheet, text: str, last_column: int) -> None:
    _cell(sheet, "A1", text, TITLE)
    for column in range(1, last_column + 1):
        sheet.set_cell(0, column, None, cell_format=TITLE)
    sheet.row_heights[0] = 28
    sheet.freeze_panes = (2, 1)
    sheet.column_widths[0] = 30


def _years(sheet: Sheet, years: int, *, start_year: int = 2026) -> None:
    for offset in range(years):
        sheet.set_cell(2, offset + 1, start_year + offset, cell_format=HEADER)
        sheet.column_widths[offset + 1] = 14


def _assumption(
    sheet: Sheet,
    row: int,
    label: str,
    value: Any,
    *,
    percent: bool = False,
) -> None:
    sheet.set_cell(row, 0, label, cell_format=LABEL)
    sheet.set_cell(
        row,
        1,
        value,
        cell_format=INPUT_PERCENT if percent else INPUT,
    )


def _build_dcf() -> Workbook:
    workbook = _workbook("Inputs", "Forecast", "Valuation", "Checks")
    inputs = workbook.get_sheet("Inputs")
    _title(inputs, "Discounted Cash Flow | Inputs", 2)
    _cell(inputs, "A3", "Operating Assumptions", SECTION)
    assumptions = (
        ("Revenue (LTM)", 1_000.0, False),
        ("Revenue growth", 0.08, True),
        ("EBITDA margin", 0.22, True),
        ("Cash tax rate", 0.25, True),
        ("D&A / revenue", 0.03, True),
        ("Capex / revenue", 0.04, True),
        ("Change NWC / revenue", 0.02, True),
        ("WACC", 0.10, True),
        ("Terminal growth", 0.025, True),
        ("Net debt", 300.0, False),
        ("Diluted shares", 100.0, False),
    )
    for row, (label, value, percent) in enumerate(assumptions, 3):
        _assumption(inputs, row, label, value, percent=percent)
    _cell(
        inputs,
        "A16",
        "Blue/yellow cells are user inputs. Green formulas link across sheets.",
        CellFormat(italic=True, font_color="#5d6d7e"),
    )
    inputs.column_widths[1] = 18
    inputs.tab_color = "#2f6f6d"

    forecast = workbook.get_sheet("Forecast")
    _title(forecast, "Discounted Cash Flow | Operating Forecast", 5)
    _years(forecast, 5)
    labels = (
        "Revenue",
        "EBITDA",
        "D&A",
        "EBIT",
        "Cash taxes",
        "NOPAT",
        "D&A add-back",
        "Capital expenditures",
        "Change in NWC",
        "Unlevered free cash flow",
    )
    for row, label in enumerate(labels, 3):
        forecast.set_cell(row, 0, label, cell_format=SECTION if row == 12 else LABEL)
    for column in range(1, 6):
        letter = chr(ord("A") + column)
        previous = chr(ord("A") + column - 1)
        revenue_formula = (
            "=Inputs!$B$4*(1+Inputs!$B$5)"
            if column == 1
            else f"={previous}4*(1+Inputs!$B$5)"
        )
        formulas = (
            revenue_formula,
            f"={letter}4*Inputs!$B$6",
            f"=-{letter}4*Inputs!$B$8",
            f"=SUM({letter}5:{letter}6)",
            f"=-MAX(0,{letter}7*Inputs!$B$7)",
            f"=SUM({letter}7:{letter}8)",
            f"=-{letter}6",
            f"=-{letter}4*Inputs!$B$9",
            f"=-{letter}4*Inputs!$B$10",
            f"=SUM({letter}9:{letter}12)",
        )
        for row, formula in enumerate(formulas, 3):
            forecast.set_cell(row, column, formula, cell_format=FORMULA)
    forecast.tab_color = "#4f81bd"

    valuation = workbook.get_sheet("Valuation")
    _title(valuation, "Discounted Cash Flow | Valuation", 5)
    _years(valuation, 5)
    _cell(valuation, "A4", "Unlevered free cash flow")
    _cell(valuation, "A5", "Discount period")
    _cell(valuation, "A6", "Present value of FCF")
    for column in range(1, 6):
        letter = chr(ord("A") + column)
        valuation.set_cell(3, column, f"=Forecast!{letter}13", cell_format=LINK)
        valuation.set_cell(4, column, column, cell_format=FORMULA)
        valuation.set_cell(
            5,
            column,
            f"={letter}4/(1+Inputs!$B$11)^{letter}5",
            cell_format=FORMULA,
        )
    _cell(valuation, "A8", "Terminal value", SECTION)
    _cell(
        valuation,
        "B8",
        "=F4*(1+Inputs!$B$12)/(Inputs!$B$11-Inputs!$B$12)",
        FORMULA,
    )
    _cell(valuation, "A9", "Present value of terminal value")
    _cell(valuation, "B9", "=B8/(1+Inputs!$B$11)^F5", FORMULA)
    _cell(valuation, "A11", "Enterprise value", SECTION)
    _cell(valuation, "B11", "=SUM(B6:F6)+B9", CURRENCY)
    _cell(valuation, "A12", "Less: net debt")
    _cell(valuation, "B12", "=-Inputs!B13", LINK)
    _cell(valuation, "A13", "Equity value")
    _cell(valuation, "B13", "=SUM(B11:B12)", CURRENCY)
    _cell(valuation, "A14", "Diluted shares")
    _cell(valuation, "B14", "=Inputs!B14", LINK)
    _cell(valuation, "A15", "Implied value per share", SECTION)
    _cell(valuation, "B15", "=B13/B14", OUTPUT)
    valuation.tab_color = "#c69214"

    checks = workbook.get_sheet("Checks")
    _title(checks, "Discounted Cash Flow | Model Checks", 2)
    _cell(checks, "A3", "Check")
    _cell(checks, "B3", "Status", HEADER)
    _cell(checks, "A4", "WACC exceeds terminal growth")
    _cell(checks, "B4", '=IF(Inputs!B11>Inputs!B12,"OK","ERROR")', CHECK)
    _cell(checks, "A5", "Forecast free cash flow is positive")
    _cell(checks, "B5", '=IF(MIN(Forecast!B13:F13)>0,"OK","REVIEW")', CHECK)
    _cell(checks, "A6", "Equity value is positive")
    _cell(checks, "B6", '=IF(Valuation!B13>0,"OK","REVIEW")', CHECK)
    checks.column_widths[1] = 18
    checks.tab_color = "#d95f59"
    return workbook


def _build_three_statement() -> Workbook:
    workbook = _workbook(
        "Assumptions",
        "Income Statement",
        "Balance Sheet",
        "Cash Flow",
        "Checks",
    )
    assumptions = workbook.get_sheet("Assumptions")
    _title(assumptions, "Three-Statement Forecast | Assumptions", 2)
    rows = (
        ("Starting revenue", 1_000.0, False),
        ("Revenue growth", 0.08, True),
        ("Gross margin", 0.45, True),
        ("EBITDA margin", 0.20, True),
        ("D&A / revenue", 0.03, True),
        ("Tax rate", 0.25, True),
        ("Capex / revenue", 0.05, True),
        ("Accounts receivable days", 45.0, False),
        ("Inventory days", 35.0, False),
        ("Accounts payable days", 30.0, False),
        ("Interest rate", 0.06, True),
        ("Opening cash", 100.0, False),
        ("Opening PP&E", 400.0, False),
        ("Opening debt", 300.0, False),
        ("Opening shareholders' equity", 330.8219178082192, False),
        ("Annual debt paydown", 40.0, False),
    )
    for row, (label, value, percent) in enumerate(rows, 2):
        _assumption(assumptions, row, label, value, percent=percent)
    assumptions.tab_color = "#2f6f6d"

    income = workbook.get_sheet("Income Statement")
    _title(income, "Three-Statement Forecast | Income Statement", 5)
    _years(income, 5)
    income_labels = (
        "Revenue",
        "Cost of goods sold",
        "Gross profit",
        "Operating expenses",
        "EBITDA",
        "D&A",
        "EBIT",
        "Interest expense",
        "Earnings before tax",
        "Cash taxes",
        "Net income",
    )
    for row, label in enumerate(income_labels, 3):
        income.set_cell(row, 0, label, cell_format=SECTION if row in (5, 7, 13) else LABEL)
    for column in range(1, 6):
        letter = chr(65 + column)
        previous = chr(64 + column)
        revenue = (
            "=Assumptions!$B$3*(1+Assumptions!$B$4)"
            if column == 1
            else f"={previous}4*(1+Assumptions!$B$4)"
        )
        formulas = (
            revenue,
            f"=-{letter}4*(1-Assumptions!$B$5)",
            f"=SUM({letter}4:{letter}5)",
            f"={letter}8-{letter}6",
            f"={letter}4*Assumptions!$B$6",
            f"=-{letter}4*Assumptions!$B$7",
            f"=SUM({letter}8:{letter}9)",
            f"=-'Balance Sheet'!{letter}10*Assumptions!$B$13",
            f"=SUM({letter}10:{letter}11)",
            f"=-MAX(0,{letter}12*Assumptions!$B$8)",
            f"=SUM({letter}12:{letter}13)",
        )
        for row, formula in enumerate(formulas, 3):
            income.set_cell(row, column, formula, cell_format=FORMULA)
    income.tab_color = "#4f81bd"

    cash_flow = workbook.get_sheet("Cash Flow")
    _title(cash_flow, "Three-Statement Forecast | Cash Flow Statement", 5)
    _years(cash_flow, 5)
    cf_labels = (
        "Net income",
        "D&A add-back",
        "Change in accounts receivable",
        "Change in inventory",
        "Change in accounts payable",
        "Cash flow from operations",
        "Capital expenditures",
        "Cash flow from investing",
        "Debt paydown",
        "Net change in cash",
        "Opening cash",
        "Ending cash",
    )
    for row, label in enumerate(cf_labels, 3):
        cash_flow.set_cell(
            row,
            0,
            label,
            cell_format=SECTION if row in (8, 10, 12, 14) else LABEL,
        )
    for column in range(1, 6):
        letter = chr(65 + column)
        previous = chr(64 + column)
        change_ar = (
            f"=-('Balance Sheet'!{letter}5-Assumptions!$B$3/365*Assumptions!$B$10)"
            if column == 1
            else f"=-('Balance Sheet'!{letter}5-'Balance Sheet'!{previous}5)"
        )
        change_inventory = (
            f"=-('Balance Sheet'!{letter}6-(Assumptions!$B$3*(1-Assumptions!$B$5)/365*Assumptions!$B$11))"
            if column == 1
            else f"=-('Balance Sheet'!{letter}6-'Balance Sheet'!{previous}6)"
        )
        change_ap = (
            f"='Balance Sheet'!{letter}10-(Assumptions!$B$3*(1-Assumptions!$B$5)/365*Assumptions!$B$12)"
            if column == 1
            else f"='Balance Sheet'!{letter}10-'Balance Sheet'!{previous}10"
        )
        opening_cash = (
            "=Assumptions!$B$14"
            if column == 1
            else f"={previous}15"
        )
        formulas = (
            f"='Income Statement'!{letter}14",
            f"=-'Income Statement'!{letter}9",
            change_ar,
            change_inventory,
            change_ap,
            f"=SUM({letter}4:{letter}8)",
            f"=-'Income Statement'!{letter}4*Assumptions!$B$9",
            f"={letter}10",
            f"=-MIN(Assumptions!$B$18,'Balance Sheet'!{letter}10)",
            f"=SUM({letter}9,{letter}11,{letter}12)",
            opening_cash,
            f"=SUM({letter}13:{letter}14)",
        )
        for row, formula in enumerate(formulas, 3):
            cash_flow.set_cell(row, column, formula, cell_format=FORMULA)
    cash_flow.tab_color = "#7f8c8d"

    balance = workbook.get_sheet("Balance Sheet")
    _title(balance, "Three-Statement Forecast | Balance Sheet", 5)
    _years(balance, 5)
    bs_labels = (
        "Cash",
        "Accounts receivable",
        "Inventory",
        "PP&E, net",
        "Total assets",
        "",
        "Accounts payable",
        "Debt",
        "Total liabilities",
        "Retained earnings",
        "Shareholders' equity",
        "Liabilities and equity",
        "Balance check",
    )
    for row, label in enumerate(bs_labels, 3):
        balance.set_cell(
            row,
            0,
            label,
            cell_format=SECTION if row in (7, 10, 14, 15) else LABEL,
        )
    for column in range(1, 6):
        letter = chr(65 + column)
        previous = chr(64 + column)
        ppe = (
            f"=Assumptions!$B$15-'Cash Flow'!{letter}10+'Income Statement'!{letter}9"
            if column == 1
            else f"={previous}7-'Cash Flow'!{letter}10+'Income Statement'!{letter}9"
        )
        debt = (
            f"=Assumptions!$B$16+'Cash Flow'!{letter}12"
            if column == 1
            else f"={previous}11+'Cash Flow'!{letter}12"
        )
        retained = (
            f"='Income Statement'!{letter}14"
            if column == 1
            else f"={previous}13+'Income Statement'!{letter}14"
        )
        formulas = (
            f"='Cash Flow'!{letter}15",
            f"='Income Statement'!{letter}4/365*Assumptions!$B$10",
            f"=-'Income Statement'!{letter}5/365*Assumptions!$B$11",
            ppe,
            f"=SUM({letter}4:{letter}7)",
            None,
            f"=-'Income Statement'!{letter}5/365*Assumptions!$B$12",
            debt,
            f"=SUM({letter}10:{letter}11)",
            retained,
            f"=Assumptions!$B$17+{letter}13",
            f"=SUM({letter}12,{letter}14)",
            f"={letter}8-{letter}15",
        )
        for row, formula in enumerate(formulas, 3):
            if formula is not None:
                balance.set_cell(
                    row,
                    column,
                    formula,
                    cell_format=CHECK if row == 15 else FORMULA,
                )
    balance.tab_color = "#c69214"

    checks = workbook.get_sheet("Checks")
    _title(checks, "Three-Statement Forecast | Checks", 5)
    _years(checks, 5)
    _cell(checks, "A4", "Balance sheet check")
    _cell(checks, "A5", "Cash linkage check")
    for column in range(1, 6):
        letter = chr(65 + column)
        checks.set_cell(
            3,
            column,
            f"='Balance Sheet'!{letter}16",
            cell_format=CHECK,
        )
        checks.set_cell(
            4,
            column,
            f"='Balance Sheet'!{letter}4-'Cash Flow'!{letter}15",
            cell_format=CHECK,
        )
    checks.tab_color = "#d95f59"
    return workbook


def _build_lbo() -> Workbook:
    workbook = _workbook("Assumptions", "Operating Case", "Debt Schedule", "Returns")
    assumptions = workbook.get_sheet("Assumptions")
    _title(assumptions, "Leveraged Buyout | Assumptions", 2)
    rows = (
        ("Entry EBITDA", 100.0, False),
        ("Entry EBITDA multiple", 10.0, False),
        ("Annual EBITDA growth", 0.08, True),
        ("D&A / EBITDA", 0.10, True),
        ("Cash tax rate", 0.25, True),
        ("Opening debt", 600.0, False),
        ("Cash interest rate", 0.08, True),
        ("Required annual amortization", 40.0, False),
        ("Capex / EBITDA", 0.10, True),
        ("Change NWC / EBITDA", 0.02, True),
        ("Exit EBITDA multiple", 11.0, False),
    )
    for row, (label, value, percent) in enumerate(rows, 2):
        _assumption(assumptions, row, label, value, percent=percent)
    assumptions.tab_color = "#2f6f6d"

    operating = workbook.get_sheet("Operating Case")
    _title(operating, "Leveraged Buyout | Operating Case", 5)
    _years(operating, 5)
    labels = (
        "EBITDA",
        "D&A",
        "EBIT",
        "Cash taxes",
        "Capital expenditures",
        "Change in NWC",
        "Cash flow available for debt service",
    )
    for row, label in enumerate(labels, 3):
        operating.set_cell(row, 0, label, cell_format=SECTION if row == 9 else LABEL)
    for column in range(1, 6):
        letter = chr(65 + column)
        previous = chr(64 + column)
        ebitda = (
            "=Assumptions!$B$3*(1+Assumptions!$B$5)"
            if column == 1
            else f"={previous}4*(1+Assumptions!$B$5)"
        )
        formulas = (
            ebitda,
            f"=-{letter}4*Assumptions!$B$6",
            f"=SUM({letter}4:{letter}5)",
            f"=-MAX(0,{letter}6*Assumptions!$B$7)",
            f"=-{letter}4*Assumptions!$B$11",
            f"=-{letter}4*Assumptions!$B$12",
            f"=SUM({letter}4,{letter}7:{letter}9)",
        )
        for row, formula in enumerate(formulas, 3):
            operating.set_cell(row, column, formula, cell_format=FORMULA)
    operating.tab_color = "#4f81bd"

    debt = workbook.get_sheet("Debt Schedule")
    _title(debt, "Leveraged Buyout | Debt Schedule", 5)
    _years(debt, 5)
    labels = (
        "Beginning debt",
        "Cash interest",
        "Required amortization",
        "Excess cash sweep",
        "Ending debt",
    )
    for row, label in enumerate(labels, 3):
        debt.set_cell(row, 0, label, cell_format=SECTION if row == 7 else LABEL)
    for column in range(1, 6):
        letter = chr(65 + column)
        previous = chr(64 + column)
        beginning = "=Assumptions!$B$8" if column == 1 else f"={previous}8"
        formulas = (
            beginning,
            f"=-{letter}4*Assumptions!$B$9",
            f"=-MIN({letter}4,Assumptions!$B$10)",
            (
                f"=-MIN(MAX(0,'Operating Case'!{letter}10+{letter}5+{letter}6),"
                f"{letter}4+{letter}6)"
            ),
            f"=MAX(0,SUM({letter}4,{letter}6:{letter}7))",
        )
        for row, formula in enumerate(formulas, 3):
            debt.set_cell(row, column, formula, cell_format=FORMULA)
    debt.tab_color = "#7f8c8d"

    returns = workbook.get_sheet("Returns")
    _title(returns, "Leveraged Buyout | Sponsor Returns", 2)
    lines = (
        ("Entry enterprise value", "=Assumptions!B3*Assumptions!B4"),
        ("Opening debt", "=Assumptions!B8"),
        ("Sponsor equity invested", "=B3-B4"),
        ("Exit EBITDA", "='Operating Case'!F4"),
        ("Exit EBITDA multiple", "=Assumptions!B13"),
        ("Exit enterprise value", "=B6*B7"),
        ("Less: exit debt", "=-'Debt Schedule'!F8"),
        ("Sponsor proceeds", "=SUM(B8:B9)"),
        ("Gross MOIC", "=B10/B5"),
        ("Gross IRR", "=IRR(B13:G13)"),
    )
    for row, (label, formula) in enumerate(lines, 2):
        returns.set_cell(row, 0, label, cell_format=SECTION if row in (4, 9, 11) else LABEL)
        returns.set_cell(
            row,
            1,
            formula,
            cell_format=OUTPUT if row in (10, 11) else FORMULA,
        )
    _cell(returns, "A13", "Sponsor cash flows")
    _cell(returns, "B13", "=-B5", FORMULA)
    for reference in ("C13", "D13", "E13", "F13"):
        _cell(returns, reference, 0, FORMULA)
    _cell(returns, "G13", "=B10", FORMULA)
    returns.tab_color = "#c69214"
    return workbook


def _build_loan() -> Workbook:
    workbook = _workbook("Summary", "Amortization")
    summary = workbook.get_sheet("Summary")
    _title(summary, "Loan Amortization | Summary", 2)
    assumptions = (
        ("Original principal", 350_000.0, False),
        ("Annual interest rate", 0.065, True),
        ("Term (years)", 30.0, False),
        ("Payments per year", 12.0, False),
        ("First payment date", "=DATE(2026,8,1)", False),
    )
    for row, (label, value, percent) in enumerate(assumptions, 2):
        _assumption(summary, row, label, value, percent=percent)
    summary.set_cell(6, 1, "=DATE(2026,8,1)", cell_format=DATE_FORMAT)
    _cell(summary, "A9", "Monthly payment", SECTION)
    _cell(summary, "B9", "=-PMT(B4/B6,B5*B6,B3)", OUTPUT)
    _cell(summary, "A10", "Total payments")
    _cell(summary, "B10", "=B9*B5*B6", CURRENCY)
    _cell(summary, "A11", "Total interest")
    _cell(summary, "B11", "=B10-B3", CURRENCY)
    summary.tab_color = "#2f6f6d"

    schedule = workbook.get_sheet("Amortization")
    _title(schedule, "Loan Amortization | Monthly Schedule", 7)
    headings = (
        "Period",
        "Payment date",
        "Beginning balance",
        "Payment",
        "Interest",
        "Principal",
        "Ending balance",
        "Cumulative interest",
    )
    for column, heading in enumerate(headings):
        schedule.set_cell(2, column, heading, cell_format=HEADER)
        schedule.column_widths[column] = 17 if column else 10
    schedule.set_cell(3, 0, 0, cell_format=FORMULA)
    schedule.set_cell(3, 1, "=Summary!B7", cell_format=DATE_FORMAT)
    schedule.set_cell(3, 2, "=Summary!B3", cell_format=CURRENCY)
    schedule.set_cell(3, 6, "=Summary!B3", cell_format=CURRENCY)
    schedule.set_cell(3, 7, 0, cell_format=CURRENCY)
    for period in range(1, 361):
        row = period + 3
        excel_row = row + 1
        previous_row = excel_row - 1
        schedule.set_cell(row, 0, period, cell_format=FORMULA)
        schedule.set_cell(
            row,
            1,
            f"=EDATE(Summary!$B$7,A{excel_row})",
            cell_format=DATE_FORMAT,
        )
        schedule.set_cell(row, 2, f"=G{previous_row}", cell_format=CURRENCY)
        schedule.set_cell(
            row,
            3,
            "=Summary!$B$9",
            cell_format=LINK,
        )
        schedule.set_cell(
            row,
            4,
            (
                f"=-IPMT(Summary!$B$4/Summary!$B$6,A{excel_row},"
                "Summary!$B$5*Summary!$B$6,Summary!$B$3)"
            ),
            cell_format=CURRENCY,
        )
        schedule.set_cell(
            row,
            5,
            (
                f"=-PPMT(Summary!$B$4/Summary!$B$6,A{excel_row},"
                "Summary!$B$5*Summary!$B$6,Summary!$B$3)"
            ),
            cell_format=CURRENCY,
        )
        schedule.set_cell(
            row,
            6,
            f"=MAX(0,C{excel_row}-F{excel_row})",
            cell_format=CURRENCY,
        )
        schedule.set_cell(
            row,
            7,
            f"=H{previous_row}+E{excel_row}",
            cell_format=CURRENCY,
        )
    schedule.freeze_panes = (3, 2)
    schedule.tab_color = "#4f81bd"
    return workbook


def _build_rental() -> Workbook:
    workbook = _workbook("Inputs", "Projection", "Returns", "Checks")
    inputs = workbook.get_sheet("Inputs")
    _title(inputs, "Rental Property | Inputs", 2)
    assumptions = (
        ("Purchase price", 500_000.0, False),
        ("Down payment", 0.25, True),
        ("Closing costs", 0.03, True),
        ("Monthly rent", 4_500.0, False),
        ("Vacancy", 0.05, True),
        ("Monthly other income", 200.0, False),
        ("Operating expense ratio", 0.35, True),
        ("Annual appreciation", 0.03, True),
        ("Annual rent growth", 0.03, True),
        ("Mortgage rate", 0.065, True),
        ("Mortgage term (years)", 30.0, False),
        ("Holding period (years)", 5.0, False),
        ("Selling costs", 0.06, True),
    )
    for row, (label, value, percent) in enumerate(assumptions, 2):
        _assumption(inputs, row, label, value, percent=percent)
    _cell(inputs, "A17", "Loan amount")
    _cell(inputs, "B17", "=B3*(1-B4)", LINK)
    _cell(inputs, "A18", "Initial equity required")
    _cell(inputs, "B18", "=B3*B4+B3*B5", OUTPUT)
    inputs.tab_color = "#2f6f6d"

    projection = workbook.get_sheet("Projection")
    _title(projection, "Rental Property | Five-Year Projection", 5)
    _years(projection, 5)
    labels = (
        "Gross scheduled rent",
        "Vacancy loss",
        "Other income",
        "Effective gross income",
        "Operating expenses",
        "Net operating income",
        "Annual debt service",
        "Levered cash flow",
        "Ending loan balance",
        "Property value",
        "Selling costs",
        "Net sale proceeds",
        "Total cash flow",
    )
    for row, label in enumerate(labels, 3):
        projection.set_cell(
            row,
            0,
            label,
            cell_format=SECTION if row in (6, 8, 10, 15) else LABEL,
        )
    for column in range(1, 6):
        letter = chr(65 + column)
        previous = chr(64 + column)
        rent = (
            "=Inputs!$B$6*12"
            if column == 1
            else f"={previous}4*(1+Inputs!$B$11)"
        )
        value = (
            "=Inputs!$B$3*(1+Inputs!$B$10)"
            if column == 1
            else f"={previous}13*(1+Inputs!$B$10)"
        )
        formulas = (
            rent,
            f"=-{letter}4*Inputs!$B$7",
            "=Inputs!$B$8*12",
            f"=SUM({letter}4:{letter}6)",
            f"=-{letter}7*Inputs!$B$9",
            f"=SUM({letter}7:{letter}8)",
            "=PMT(Inputs!$B$12/12,Inputs!$B$13*12,Inputs!$B$17)*12",
            f"=SUM({letter}9:{letter}10)",
            (
                f"=-FV(Inputs!$B$12/12,{column}*12,"
                "PMT(Inputs!$B$12/12,Inputs!$B$13*12,Inputs!$B$17),Inputs!$B$17)"
            ),
            value,
            f"=IF({column}=Inputs!$B$14,-{letter}13*Inputs!$B$15,0)",
            f"=IF({column}=Inputs!$B$14,{letter}13+{letter}14-{letter}12,0)",
            f"=SUM({letter}11,{letter}15)",
        )
        for row, formula in enumerate(formulas, 3):
            projection.set_cell(row, column, formula, cell_format=FORMULA)
    projection.tab_color = "#4f81bd"

    returns = workbook.get_sheet("Returns")
    _title(returns, "Rental Property | Investor Returns", 6)
    _cell(returns, "A3", "Period", HEADER)
    for column, label in enumerate(("Initial", "Year 1", "Year 2", "Year 3", "Year 4", "Year 5"), 1):
        returns.set_cell(2, column, label, cell_format=HEADER)
    _cell(returns, "A4", "Levered cash flow")
    _cell(returns, "B4", "=-Inputs!B18", LINK)
    for column in range(2, 7):
        source = chr(64 + column)
        returns.set_cell(3, column, f"=Projection!{source}16", cell_format=LINK)
    _cell(returns, "A6", "Initial equity")
    _cell(returns, "B6", "=Inputs!B18", CURRENCY)
    _cell(returns, "A7", "Total positive distributions")
    _cell(returns, "B7", "=SUM(C4:G4)", CURRENCY)
    _cell(returns, "A8", "Levered IRR", SECTION)
    _cell(returns, "B8", "=IRR(B4:G4)", OUTPUT)
    returns.get_cell(7, 1)
    returns.set_cell(7, 1, "=IRR(B4:G4)", cell_format=CellFormat(
        font_size=12,
        bold=True,
        font_color="#17324d",
        fill_color="#d7ebe3",
        number_format="0.0%",
        top_border=BorderStyle("double", "#2f6f6d"),
    ))
    _cell(returns, "A9", "Equity multiple")
    _cell(returns, "B9", "=B7/B6", OUTPUT)
    returns.tab_color = "#c69214"

    checks = workbook.get_sheet("Checks")
    _title(checks, "Rental Property | Checks", 2)
    _cell(checks, "A3", "Mortgage balance non-negative")
    _cell(checks, "B3", '=IF(MIN(Projection!B12:F12)>=0,"OK","ERROR")', CHECK)
    _cell(checks, "A4", "Holding period supported")
    _cell(checks, "B4", '=IF(Inputs!B14=5,"OK","Set projection years")', CHECK)
    checks.tab_color = "#d95f59"
    return workbook


def _build_budget() -> Workbook:
    workbook = _workbook("Assumptions", "Budget", "Actuals", "Variance", "Dashboard")
    assumptions = workbook.get_sheet("Assumptions")
    _title(assumptions, "Budget and Forecast | Assumptions", 2)
    rows = (
        ("Starting monthly revenue", 150_000.0, False),
        ("Annual revenue growth", 0.08, True),
        ("Gross margin", 0.55, True),
        ("Monthly payroll", 45_000.0, False),
        ("Annual payroll growth", 0.04, True),
        ("Monthly operating expenses", 25_000.0, False),
        ("Annual opex growth", 0.03, True),
    )
    for row, (label, value, percent) in enumerate(rows, 2):
        _assumption(assumptions, row, label, value, percent=percent)
    _cell(assumptions, "A11", "Monthly seasonality", SECTION)
    seasonality = (0.00, -0.03, 0.01, 0.02, 0.03, 0.00, -0.04, -0.02, 0.02, 0.04, 0.08, 0.15)
    for column, value in enumerate(seasonality, 1):
        assumptions.set_cell(11, column, value, cell_format=INPUT_PERCENT)
        assumptions.column_widths[column] = 12
    assumptions.tab_color = "#2f6f6d"

    budget = workbook.get_sheet("Budget")
    _title(budget, "Budget and Forecast | Monthly Budget", 12)
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    for column, month in enumerate(months, 1):
        budget.set_cell(2, column, month, cell_format=HEADER)
        budget.column_widths[column] = 12
    labels = ("Revenue", "Cost of goods sold", "Gross profit", "Payroll", "Operating expenses", "EBITDA", "EBITDA margin")
    for row, label in enumerate(labels, 3):
        budget.set_cell(row, 0, label, cell_format=SECTION if row in (5, 8, 9) else LABEL)
    for column in range(1, 13):
        letter = chr(65 + column)
        formulas = (
            f"=Assumptions!$B$3*(1+Assumptions!$B$4)^(({column}-1)/12)*(1+Assumptions!{letter}12)",
            f"=-{letter}4*(1-Assumptions!$B$5)",
            f"=SUM({letter}4:{letter}5)",
            f"=-Assumptions!$B$6*(1+Assumptions!$B$7)^(({column}-1)/12)",
            f"=-Assumptions!$B$8*(1+Assumptions!$B$9)^(({column}-1)/12)",
            f"=SUM({letter}6:{letter}8)",
            f"={letter}9/{letter}4",
        )
        for row, formula in enumerate(formulas, 3):
            budget.set_cell(
                row,
                column,
                formula,
                cell_format=PERCENT if row == 9 else FORMULA,
            )
    budget.tab_color = "#4f81bd"

    actuals = workbook.get_sheet("Actuals")
    _title(actuals, "Budget and Forecast | Actual Results", 12)
    for column, month in enumerate(months, 1):
        actuals.set_cell(2, column, month, cell_format=HEADER)
        actuals.column_widths[column] = 12
    actual_labels = ("Revenue", "Cost of goods sold", "Payroll", "Operating expenses", "EBITDA", "EBITDA margin")
    for row, label in enumerate(actual_labels, 3):
        actuals.set_cell(row, 0, label, cell_format=SECTION if row in (7, 8) else LABEL)
    multipliers = (0.98, 1.01, 1.02, 0.99, 1.03, 1.00, 0.97, 1.02, 1.01, 1.04, 1.02, 1.05)
    for column, multiplier in enumerate(multipliers, 1):
        letter = chr(65 + column)
        actuals.set_cell(3, column, f"=Budget!{letter}4*{multiplier}", cell_format=LINK)
        actuals.set_cell(4, column, f"=Budget!{letter}5", cell_format=LINK)
        actuals.set_cell(5, column, f"=Budget!{letter}7", cell_format=LINK)
        actuals.set_cell(6, column, f"=Budget!{letter}8", cell_format=LINK)
        actuals.set_cell(7, column, f"=SUM({letter}4:{letter}7)", cell_format=FORMULA)
        actuals.set_cell(8, column, f"={letter}8/{letter}4", cell_format=PERCENT)
    actuals.tab_color = "#7f8c8d"

    variance = workbook.get_sheet("Variance")
    _title(variance, "Budget and Forecast | Actual vs Budget", 12)
    for column, month in enumerate(months, 1):
        variance.set_cell(2, column, month, cell_format=HEADER)
        variance.column_widths[column] = 12
    _cell(variance, "A4", "Revenue variance")
    _cell(variance, "A5", "EBITDA variance")
    _cell(variance, "A6", "EBITDA margin variance")
    for column in range(1, 13):
        letter = chr(65 + column)
        variance.set_cell(3, column, f"=Actuals!{letter}4-Budget!{letter}4", cell_format=FORMULA)
        variance.set_cell(4, column, f"=Actuals!{letter}8-Budget!{letter}9", cell_format=FORMULA)
        variance.set_cell(5, column, f"=Actuals!{letter}9-Budget!{letter}10", cell_format=PERCENT)
    variance.tab_color = "#c69214"

    dashboard = workbook.get_sheet("Dashboard")
    _title(dashboard, "Budget and Forecast | Annual Dashboard", 3)
    _cell(dashboard, "A3", "Metric", HEADER)
    _cell(dashboard, "B3", "Budget", HEADER)
    _cell(dashboard, "C3", "Actual", HEADER)
    _cell(dashboard, "D3", "Variance", HEADER)
    metrics = (
        ("Revenue", "=SUM(Budget!B4:M4)", "=SUM(Actuals!B4:M4)"),
        ("EBITDA", "=SUM(Budget!B9:M9)", "=SUM(Actuals!B8:M8)"),
        ("EBITDA margin", "=B5/B4", "=C5/C4"),
    )
    for row, (label, budget_formula, actual_formula) in enumerate(metrics, 3):
        dashboard.set_cell(row, 0, label, cell_format=SECTION if row == 5 else LABEL)
        dashboard.set_cell(row, 1, budget_formula, cell_format=FORMULA)
        dashboard.set_cell(row, 2, actual_formula, cell_format=FORMULA)
        dashboard.set_cell(
            row,
            3,
            f"=C{row + 1}-B{row + 1}",
            cell_format=PERCENT if row == 5 else FORMULA,
        )
    _cell(dashboard, "A8", "Actual EBITDA margin", SECTION)
    dashboard.set_cell(7, 1, "=C6", cell_format=CellFormat(
        font_size=12,
        bold=True,
        font_color="#17324d",
        fill_color="#d7ebe3",
        number_format="0.0%",
        top_border=BorderStyle("double", "#2f6f6d"),
    ))
    dashboard.column_widths.update({1: 18, 2: 18, 3: 18})
    dashboard.tab_color = "#d95f59"
    return workbook


def _lab_result_format(format_key: str) -> CellFormat:
    """Return the display format used by a Financial Lab result."""
    formats = {
        "currency": CURRENCY,
        "date": CellFormat(number_format="mmm d, yyyy"),
        "number": FORMULA,
        "percent": PERCENT,
    }
    return formats[format_key]


def _lab_chart(
    owner: Sheet,
    chart_id: str,
    source_sheet: str,
    source_range: str,
    chart_type: str,
    title: str,
    *,
    category_column: int | None = None,
    series_columns: tuple[int, ...] | None = None,
    theme: str = "executive",
    legend_position: str = "right",
    show_data_labels: bool = False,
    show_trendline: bool = False,
    highlight_extrema: bool = False,
    secondary_axis: bool = False,
    number_format: str = "auto",
    x_axis_title: str = "",
    y_axis_title: str = "",
) -> None:
    """Attach an editable chart to a Financial Lab gallery sheet."""
    parsed = parse_a1(source_range, default_sheet=source_sheet)
    assert isinstance(parsed, RangeReference)
    owner.charts.append(
        ChartSpec(
            chart_id=chart_id,
            sheet_name=source_sheet,
            source_range=parsed,
            chart_type=chart_type,
            title=title,
            x_axis_title=x_axis_title,
            y_axis_title=y_axis_title,
            legend_position=legend_position,
            category_column=category_column,
            series_columns=series_columns,
            theme=theme,
            show_data_labels=show_data_labels,
            show_trendline=show_trendline,
            highlight_extrema=highlight_extrema,
            secondary_axis=secondary_axis,
            number_format=number_format,
        )
    )


def _build_financial_lab() -> Workbook:
    workbook = _workbook(
        "Guide",
        "Sample Data",
        "Function Lab",
        "Common Metrics",
        "Charts - Performance",
        "Charts - Cash Flow",
        "Charts - Portfolio",
        "Charts - Risk",
    )

    guide = workbook.get_sheet("Guide")
    _title(guide, "Financial Calculations Lab | Guide", 5)
    _cell(guide, "A3", "Lab inventory", SECTION)
    _cell(guide, "A4", "Financial-function examples")
    _cell(guide, "A5", "Common financial metrics")
    _cell(guide, "A6", "Total live calculations", SECTION)
    _cell(guide, "A7", "Editable analytical charts")
    guide.set_cell(3, 1, "=COUNTA('Function Lab'!C4:C49)", cell_format=FORMULA)
    guide.set_cell(4, 1, "=COUNTA('Common Metrics'!C4:C33)", cell_format=FORMULA)
    guide.set_cell(
        5,
        1,
        "=SUM(B4:B5)",
        cell_format=CellFormat(
            font_size=12,
            bold=True,
            font_color="#17324d",
            fill_color="#d7ebe3",
            number_format="0",
            top_border=BorderStyle("double", "#2f6f6d"),
        ),
    )
    guide.set_cell(6, 1, 12, cell_format=FORMULA)
    _cell(guide, "A10", "How to use the lab", SECTION)
    instructions = (
        "1. Start on Sample Data. Blue text on yellow cells identifies editable assumptions.",
        "2. Open Function Lab for one live example of every supported financial function.",
        "3. Open Common Metrics for operating, cash-flow, liquidity, leverage, valuation, and statistical calculations.",
        "4. Select any result to inspect its exact formula in the formula bar; edit an input and press F9 to recalculate.",
        "5. Open the four Charts sheets. Each contains three editable charts linked to the sample data.",
        "6. Use Insert > Chart or Quick Chart to change chart type, theme, labels, axes, series, or source range.",
        "7. Press F1 for the full function reference and tutorials; run Financial > Model Audit before trusting a model.",
    )
    for row, instruction in enumerate(instructions, 11):
        _cell(
            guide,
            f"A{row}",
            instruction,
            CellFormat(wrap_text=True, font_color="#243746"),
        )
        guide.row_heights[row - 1] = 30
    _cell(
        guide,
        "A20",
        "Training data only",
        CellFormat(
            bold=True,
            font_color="#8a3f14",
            fill_color="#fde7d3",
            bottom_border=_THIN_GRAY,
        ),
    )
    _cell(
        guide,
        "A21",
        "All companies, securities, cash flows, and returns in this workbook are synthetic. This lab teaches calculation mechanics; it is not accounting, tax, legal, or investment advice.",
        CellFormat(wrap_text=True, italic=True, font_color="#5d6d7e"),
    )
    guide.row_heights[20] = 42
    guide.column_widths.update({0: 92, 1: 18})
    guide.tab_color = "#17324d"

    sample = workbook.get_sheet("Sample Data")
    _title(sample, "Financial Calculations Lab | Synthetic Sample Data", 22)
    _cell(sample, "A3", "Assumption", HEADER)
    _cell(sample, "B3", "Sample value", HEADER)
    assumptions = (
        ("Loan principal", 350_000, "currency"),
        ("Annual loan rate", 0.065, "percent"),
        ("Loan term (years)", 30, "number"),
        ("Payments per year", 12, "number"),
        ("Payment period", 37, "number"),
        ("Investment present value", 100_000, "currency"),
        ("Investment future value", 180_000, "currency"),
        ("Investment horizon (years)", 8, "number"),
        ("Finance rate", 0.07, "percent"),
        ("Reinvestment rate", 0.09, "percent"),
        ("Nominal annual rate", 0.06, "percent"),
        ("Compounding periods", 12, "number"),
        ("Asset cost", 125_000, "currency"),
        ("Asset salvage value", 15_000, "currency"),
        ("Useful life (years)", 7, "number"),
        ("Depreciation period", 3, "number"),
        ("Security settlement", "=DATE(2026,5,15)", "date"),
        ("Security maturity", "=DATE(2032,7,15)", "date"),
        ("Coupon rate", 0.0475, "percent"),
        ("Market yield", 0.0525, "percent"),
        ("Redemption value", 100, "number"),
        ("Coupon frequency", 2, "number"),
        ("Day-count basis", 0, "number"),
        ("T-bill settlement", "=DATE(2026,7,15)", "date"),
        ("T-bill maturity", "=DATE(2026,12,15)", "date"),
        ("T-bill discount rate", 0.041, "percent"),
        ("Discount security price", 97.5, "number"),
        ("Discount security investment", 97_500, "currency"),
        ("Discount security redemption", 100_000, "currency"),
        ("Par value", 100_000, "currency"),
        ("Bond market price", 98.25, "number"),
        ("Current assets", 640, "currency"),
        ("Inventory", 170, "currency"),
        ("Current liabilities", 330, "currency"),
        ("Cash", 120, "currency"),
        ("Total debt", 520, "currency"),
        ("EBIT", 205, "currency"),
        ("Interest expense", 38, "currency"),
        ("Tax rate", 0.25, "percent"),
        ("Diluted shares", 50, "number"),
        ("Dividends", 35, "currency"),
        ("Market price per share", 42, "currency"),
        ("Security issue date", "=DATE(2026,1,15)", "date"),
        ("Security first coupon", "=DATE(2026,7,15)", "date"),
    )
    input_date = CellFormat(
        font_color="#0066cc",
        fill_color="#fff4cc",
        number_format="mmm d, yyyy",
        bottom_border=_THIN_GRAY,
    )
    input_currency = CellFormat(
        font_color="#0066cc",
        fill_color="#fff4cc",
        number_format="$#,##0.00;[Red]($#,##0.00);-",
        bottom_border=_THIN_GRAY,
    )
    input_formats = {
        "currency": input_currency,
        "date": input_date,
        "number": INPUT,
        "percent": INPUT_PERCENT,
    }
    for row, (label, value, format_key) in enumerate(assumptions, 4):
        sample.set_cell(row - 1, 0, label, cell_format=LABEL)
        sample.set_cell(
            row - 1,
            1,
            value,
            cell_format=input_formats[format_key],
        )

    _cell(sample, "D3", "Period", HEADER)
    _cell(sample, "E3", "Project cash flow", HEADER)
    for row, (period, cash_flow) in enumerate(
        ((0, -100_000), (1, 20_000), (2, 30_000), (3, 40_000), (4, 45_000), (5, 50_000)),
        4,
    ):
        sample.set_cell(row - 1, 3, period, cell_format=LABEL)
        sample.set_cell(row - 1, 4, cash_flow, cell_format=input_currency)

    _cell(sample, "G3", "Date", HEADER)
    _cell(sample, "H3", "Irregular cash flow", HEADER)
    irregular_flows = (
        ("=DATE(2026,1,15)", -100_000),
        ("=DATE(2026,10,1)", 24_000),
        ("=DATE(2027,8,15)", 38_000),
        ("=DATE(2028,12,31)", 72_000),
    )
    for row, (flow_date, cash_flow) in enumerate(irregular_flows, 4):
        sample.set_cell(row - 1, 6, flow_date, cell_format=input_date)
        sample.set_cell(row - 1, 7, cash_flow, cell_format=input_currency)

    _cell(sample, "J3", "Rate schedule", HEADER)
    for row, rate in enumerate((0.04, 0.05, -0.02, 0.07), 4):
        sample.set_cell(row - 1, 9, rate, cell_format=INPUT_PERCENT)

    operating_headers = (
        "Year",
        "Revenue",
        "COGS",
        "EBITDA",
        "Net income",
        "Assets",
        "Equity",
        "Operating CF",
        "Capex",
    )
    for column, header in enumerate(operating_headers, 3):
        sample.set_cell(12, column, header, cell_format=HEADER)
    operating_data = (
        (2022, 800, 480, 144, 70, 1_100, 650, 110, -60),
        (2023, 880, 510, 167, 82, 1_180, 700, 128, -66),
        (2024, 970, 548, 194, 97, 1_270, 760, 150, -72),
        (2025, 1_080, 594, 227, 118, 1_380, 830, 178, -80),
        (2026, 1_200, 648, 264, 140, 1_500, 900, 210, -90),
    )
    for row, values in enumerate(operating_data, 13):
        for column, value in enumerate(values, 3):
            sample.set_cell(
                row,
                column,
                value,
                cell_format=LABEL if column == 3 else input_currency,
            )

    _cell(sample, "N3", "Month", HEADER)
    _cell(sample, "O3", "Budget revenue", HEADER)
    _cell(sample, "P3", "Actual revenue", HEADER)
    months = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )
    budgets = (100, 102, 105, 108, 110, 112, 115, 118, 120, 123, 126, 130)
    actuals = (98, 104, 103, 111, 109, 116, 114, 121, 119, 128, 129, 135)
    for row, (month, budget, actual) in enumerate(
        zip(months, budgets, actuals),
        4,
    ):
        sample.set_cell(row - 1, 13, month, cell_format=LABEL)
        sample.set_cell(row - 1, 14, budget, cell_format=input_currency)
        sample.set_cell(row - 1, 15, actual, cell_format=input_currency)

    _cell(sample, "R3", "Asset class", HEADER)
    _cell(sample, "S3", "Allocation", HEADER)
    allocations = (
        ("US Equity", 0.45),
        ("International", 0.20),
        ("Bonds", 0.20),
        ("REIT", 0.10),
        ("Cash", 0.05),
    )
    for row, (asset, allocation) in enumerate(allocations, 4):
        sample.set_cell(row - 1, 17, asset, cell_format=LABEL)
        sample.set_cell(row - 1, 18, allocation, cell_format=INPUT_PERCENT)

    _cell(sample, "U3", "Asset class", HEADER)
    _cell(sample, "V3", "Risk", HEADER)
    _cell(sample, "W3", "Expected return", HEADER)
    risk_return = (
        ("Bonds", 0.05, 0.06),
        ("US Equity", 0.15, 0.11),
        ("International", 0.18, 0.10),
        ("REIT", 0.20, 0.09),
        ("Cash", 0.01, 0.03),
    )
    for row, (asset, risk, expected_return) in enumerate(risk_return, 4):
        sample.set_cell(row - 1, 20, asset, cell_format=LABEL)
        sample.set_cell(row - 1, 21, risk, cell_format=INPUT_PERCENT)
        sample.set_cell(row - 1, 22, expected_return, cell_format=INPUT_PERCENT)

    _cell(sample, "N19", "Month", HEADER)
    _cell(sample, "O19", "Fund A", HEADER)
    _cell(sample, "P19", "Fund B", HEADER)
    _cell(sample, "Q19", "Benchmark", HEADER)
    monthly_returns = (
        ("Jan", 0.021, 0.012, 0.018),
        ("Feb", -0.015, -0.008, -0.011),
        ("Mar", 0.032, 0.024, 0.028),
        ("Apr", 0.008, 0.011, 0.009),
        ("May", -0.022, -0.014, -0.018),
        ("Jun", 0.017, 0.009, 0.014),
        ("Jul", 0.026, 0.018, 0.022),
        ("Aug", -0.009, 0.003, -0.004),
        ("Sep", 0.014, 0.012, 0.013),
        ("Oct", 0.029, 0.021, 0.025),
        ("Nov", -0.012, -0.006, -0.009),
        ("Dec", 0.023, 0.017, 0.020),
    )
    for row, values in enumerate(monthly_returns, 20):
        sample.set_cell(row - 1, 13, values[0], cell_format=LABEL)
        for column, value in enumerate(values[1:], 14):
            sample.set_cell(row - 1, column, value, cell_format=INPUT_PERCENT)
    sample.column_widths.update(
        {
            0: 31,
            1: 19,
            3: 12,
            4: 18,
            6: 16,
            7: 19,
            9: 16,
            13: 12,
            14: 18,
            15: 18,
            17: 18,
            18: 14,
            20: 18,
            21: 14,
            22: 18,
        }
    )
    sample.tab_color = "#c69214"

    function_lab = workbook.get_sheet("Function Lab")
    _title(function_lab, "Financial Calculations Lab | 46 Financial Functions", 5)
    for column, header in enumerate(
        (
            "#",
            "Category",
            "Function",
            "What it demonstrates",
            "Live result",
            "Learning note",
        )
    ):
        function_lab.set_cell(2, column, header, cell_format=HEADER)
    for row, (category, name, purpose, formula, format_key) in enumerate(
        FINANCIAL_LAB_FUNCTIONS,
        4,
    ):
        function_lab.set_cell(row - 1, 0, row - 3, cell_format=LABEL)
        function_lab.set_cell(row - 1, 1, category, cell_format=LABEL)
        function_lab.set_cell(
            row - 1,
            2,
            name,
            cell_format=CellFormat(bold=True, font_color="#17324d"),
        )
        function_lab.set_cell(
            row - 1,
            3,
            purpose,
            cell_format=CellFormat(wrap_text=True, font_color="#243746"),
        )
        function_lab.set_cell(
            row - 1,
            4,
            formula,
            cell_format=_lab_result_format(format_key),
        )
        function_lab.set_cell(
            row - 1,
            5,
            "Edit Sample Data, press F9, and inspect this cell's formula.",
            cell_format=CellFormat(
                wrap_text=True,
                italic=True,
                font_color="#5d6d7e",
            ),
        )
        function_lab.row_heights[row - 1] = 30
    function_lab.freeze_panes = (3, 3)
    function_lab.column_widths.update(
        {0: 8, 1: 24, 2: 17, 3: 48, 4: 20, 5: 42}
    )
    function_lab.tab_color = "#2f6f6d"

    metrics = workbook.get_sheet("Common Metrics")
    _title(metrics, "Financial Calculations Lab | 30 Common Metrics", 5)
    for column, header in enumerate(
        (
            "#",
            "Category",
            "Calculation",
            "What it measures",
            "Live result",
            "Interpretation",
        )
    ):
        metrics.set_cell(2, column, header, cell_format=HEADER)
    for row, (category, name, purpose, formula, format_key) in enumerate(
        COMMON_FINANCIAL_METRICS,
        4,
    ):
        metrics.set_cell(row - 1, 0, row - 3, cell_format=LABEL)
        metrics.set_cell(row - 1, 1, category, cell_format=LABEL)
        metrics.set_cell(
            row - 1,
            2,
            name,
            cell_format=CellFormat(bold=True, font_color="#17324d"),
        )
        metrics.set_cell(
            row - 1,
            3,
            purpose,
            cell_format=CellFormat(wrap_text=True, font_color="#243746"),
        )
        metrics.set_cell(
            row - 1,
            4,
            formula,
            cell_format=_lab_result_format(format_key),
        )
        metrics.set_cell(
            row - 1,
            5,
            "Compare the ratio or trend with peers, history, and business context.",
            cell_format=CellFormat(
                wrap_text=True,
                italic=True,
                font_color="#5d6d7e",
            ),
        )
        metrics.row_heights[row - 1] = 30
    metrics.freeze_panes = (3, 3)
    metrics.column_widths.update(
        {0: 8, 1: 20, 2: 28, 3: 48, 4: 20, 5: 45}
    )
    metrics.tab_color = "#3f7fbf"

    performance = workbook.get_sheet("Charts - Performance")
    _title(performance, "Chart Gallery | Performance and Variance", 5)
    _cell(
        performance,
        "A3",
        "Select this sheet to explore three live charts: revenue trend, profitability, and budget versus actual.",
        CellFormat(wrap_text=True, font_color="#243746"),
    )
    _lab_chart(
        performance,
        "lab-revenue-trend",
        "Sample Data",
        "D13:E18",
        "line",
        "Revenue Trend",
        theme="coastal",
        legend_position="none",
        show_data_labels=True,
        show_trendline=True,
        highlight_extrema=True,
        number_format="currency",
        x_axis_title="Year",
        y_axis_title="Revenue",
    )
    _lab_chart(
        performance,
        "lab-profitability",
        "Sample Data",
        "D13:H18",
        "column",
        "Revenue, EBITDA, and Net Income",
        category_column=3,
        series_columns=(4, 6, 7),
        theme="executive",
        show_data_labels=True,
        number_format="currency",
        x_axis_title="Year",
        y_axis_title="Amount",
    )
    _lab_chart(
        performance,
        "lab-budget-actual",
        "Sample Data",
        "N3:P15",
        "column",
        "Monthly Budget vs Actual",
        theme="editorial",
        show_data_labels=True,
        highlight_extrema=True,
        number_format="currency",
        x_axis_title="Month",
        y_axis_title="Revenue",
    )
    performance.column_widths[0] = 95
    performance.row_heights[2] = 34
    performance.tab_color = "#d95f59"

    cash_flow = workbook.get_sheet("Charts - Cash Flow")
    _title(cash_flow, "Chart Gallery | Cash Flow and Margins", 5)
    _cell(cash_flow, "A3", "Year", HEADER)
    _cell(cash_flow, "B3", "Revenue", HEADER)
    _cell(cash_flow, "C3", "EBITDA margin", HEADER)
    for row, source_row in enumerate(range(14, 19), 4):
        cash_flow.set_cell(
            row - 1,
            0,
            f"='Sample Data'!D{source_row}",
            cell_format=LINK,
        )
        cash_flow.set_cell(
            row - 1,
            1,
            f"='Sample Data'!E{source_row}",
            cell_format=CURRENCY,
        )
        cash_flow.set_cell(
            row - 1,
            2,
            f"='Sample Data'!G{source_row}/'Sample Data'!E{source_row}",
            cell_format=PERCENT,
        )
    _cell(
        cash_flow,
        "A11",
        "The helper table above demonstrates a dual-axis combo chart with revenue and margin in different units.",
        CellFormat(wrap_text=True, italic=True, font_color="#5d6d7e"),
    )
    _lab_chart(
        cash_flow,
        "lab-project-waterfall",
        "Sample Data",
        "D3:E9",
        "waterfall",
        "Project Cash-Flow Waterfall",
        theme="high_contrast",
        legend_position="none",
        show_data_labels=True,
        highlight_extrema=True,
        number_format="currency",
        x_axis_title="Period",
        y_axis_title="Cash flow",
    )
    _lab_chart(
        cash_flow,
        "lab-operating-cash-flow",
        "Sample Data",
        "D13:L18",
        "stacked_column",
        "Operating Cash Flow and Capital Expenditure",
        category_column=3,
        series_columns=(10, 11),
        theme="coastal",
        show_data_labels=True,
        number_format="currency",
        x_axis_title="Year",
        y_axis_title="Cash flow",
    )
    _lab_chart(
        cash_flow,
        "lab-revenue-margin-combo",
        "Charts - Cash Flow",
        "A3:C8",
        "combo",
        "Revenue and EBITDA Margin",
        category_column=0,
        series_columns=(1, 2),
        theme="executive",
        show_data_labels=True,
        secondary_axis=True,
        x_axis_title="Year",
    )
    cash_flow.column_widths.update({0: 22, 1: 18, 2: 18})
    cash_flow.row_heights[10] = 34
    cash_flow.tab_color = "#4c956c"

    portfolio = workbook.get_sheet("Charts - Portfolio")
    _title(portfolio, "Chart Gallery | Portfolio and Distribution", 5)
    _cell(
        portfolio,
        "A3",
        "Select this sheet to explore allocation, risk/return, and monthly-return distribution charts.",
        CellFormat(wrap_text=True, font_color="#243746"),
    )
    _lab_chart(
        portfolio,
        "lab-allocation",
        "Sample Data",
        "R3:S8",
        "donut",
        "Portfolio Allocation",
        theme="editorial",
        legend_position="right",
        show_data_labels=True,
        number_format="percent",
    )
    _lab_chart(
        portfolio,
        "lab-risk-return",
        "Sample Data",
        "U3:W8",
        "scatter",
        "Risk vs Expected Return",
        category_column=21,
        series_columns=(22,),
        theme="executive",
        legend_position="none",
        show_data_labels=True,
        show_trendline=True,
        highlight_extrema=True,
        number_format="percent",
        x_axis_title="Risk",
        y_axis_title="Expected return",
    )
    _lab_chart(
        portfolio,
        "lab-return-histogram",
        "Sample Data",
        "O19:O31",
        "histogram",
        "Fund A Monthly Return Distribution",
        theme="monochrome",
        legend_position="none",
        show_data_labels=True,
        highlight_extrema=True,
        number_format="percent",
        x_axis_title="Monthly return",
        y_axis_title="Frequency",
    )
    portfolio.column_widths[0] = 95
    portfolio.row_heights[2] = 34
    portfolio.tab_color = "#7d5ba6"

    risk = workbook.get_sheet("Charts - Risk")
    _title(risk, "Chart Gallery | Risk and Comparisons", 5)
    _cell(risk, "A3", "Metric", HEADER)
    _cell(risk, "B3", "Company", HEADER)
    _cell(risk, "C3", "Benchmark", HEADER)
    radar_metrics = (
        ("Revenue growth", "='Common Metrics'!E4", 0.08),
        ("Gross margin", "='Common Metrics'!E7", 0.42),
        ("EBITDA margin", "='Common Metrics'!E8", 0.18),
        ("Net margin", "='Common Metrics'!E9", 0.10),
        ("Return on assets", "='Common Metrics'!E10", 0.09),
    )
    for row, (name, formula, benchmark) in enumerate(radar_metrics, 4):
        risk.set_cell(row - 1, 0, name, cell_format=LABEL)
        risk.set_cell(row - 1, 1, formula, cell_format=PERCENT)
        risk.set_cell(row - 1, 2, benchmark, cell_format=INPUT_PERCENT)
    _cell(
        risk,
        "A11",
        "The heatmap and box plot compare the three synthetic return series; the radar chart compares operating ratios with a synthetic benchmark.",
        CellFormat(wrap_text=True, italic=True, font_color="#5d6d7e"),
    )
    _lab_chart(
        risk,
        "lab-return-heatmap",
        "Sample Data",
        "N19:Q31",
        "heatmap",
        "Monthly Return Heatmap",
        category_column=13,
        series_columns=(14, 15, 16),
        theme="high_contrast",
        show_data_labels=True,
        number_format="percent",
        x_axis_title="Month",
    )
    _lab_chart(
        risk,
        "lab-ratio-radar",
        "Charts - Risk",
        "A3:C8",
        "radar",
        "Operating Ratio Benchmark",
        category_column=0,
        series_columns=(1, 2),
        theme="coastal",
        show_data_labels=True,
        number_format="percent",
    )
    _lab_chart(
        risk,
        "lab-return-box",
        "Sample Data",
        "N19:Q31",
        "box",
        "Monthly Return Range and Outliers",
        category_column=13,
        series_columns=(14, 15, 16),
        theme="editorial",
        show_data_labels=True,
        highlight_extrema=True,
        number_format="percent",
    )
    risk.column_widths.update({0: 28, 1: 18, 2: 18})
    risk.row_heights[10] = 40
    risk.tab_color = "#b94a48"
    return workbook


_BUILDERS.update(
    {
        "dcf": _build_dcf,
        "three_statement": _build_three_statement,
        "lbo": _build_lbo,
        "loan": _build_loan,
        "rental": _build_rental,
        "budget": _build_budget,
        "financial_lab": _build_financial_lab,
    }
)
