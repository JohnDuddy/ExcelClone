"""Curated offline help content for every financial worksheet function."""

from __future__ import annotations

from dataclasses import dataclass

from duddysheet.core.functions import FUNCTION_REGISTRY


@dataclass(frozen=True, slots=True)
class FinancialHelpEntry:
    """Practical reference material for one financial function."""

    name: str
    category: str
    syntax: str
    summary: str
    use_when: str
    example: str
    notes: tuple[str, ...]
    related: tuple[str, ...]


_LOANS = "Loans and annuities"
_RETURNS = "Cash flow and returns"
_RATES = "Interest-rate conversion"
_DEPRECIATION = "Depreciation"
_BONDS = "Bonds and coupon schedules"
_DISCOUNT = "Discount securities"
_TREASURY = "Treasury bills"
_QUOTATIONS = "Fractional quotations"


_DETAILS: dict[
    str,
    tuple[str, str, str, tuple[str, ...], tuple[str, ...]],
] = {
    "PMT": (
        _LOANS,
        "Calculate the fixed payment for a loan or level-payment investment.",
        "=PMT(6.5%/12,30*12,350000)",
        (
            "Match the rate period to the payment period; monthly payments require a monthly rate.",
            "A positive present value normally produces a negative payment because cash paid out has the opposite sign.",
            "Set type to 1 for payments at the beginning of each period; the default 0 means period end.",
        ),
        ("PV", "FV", "IPMT", "PPMT", "NPER", "RATE"),
    ),
    "IPMT": (
        _LOANS,
        "Split one level payment into its interest component.",
        "=IPMT(6.5%/12,37,30*12,350000)",
        (
            "The period number starts at 1 and cannot exceed nper.",
            "Use the same rate, nper, pv, fv, and type assumptions used by PMT.",
            "IPMT plus PPMT equals PMT for the same period.",
        ),
        ("PMT", "PPMT", "CUMIPMT"),
    ),
    "PPMT": (
        _LOANS,
        "Split one level payment into its principal component.",
        "=PPMT(6.5%/12,37,30*12,350000)",
        (
            "The period number starts at 1 and cannot exceed nper.",
            "Principal usually has the same sign as the total payment.",
            "Use CUMPRINC when a total across several periods is required.",
        ),
        ("PMT", "IPMT", "CUMPRINC"),
    ),
    "PV": (
        _LOANS,
        "Value a future amount or payment stream in today's money.",
        "=PV(6.5%/12,30*12,-2212.24)",
        (
            "Rate and nper must use the same period.",
            "Use opposite signs for cash received and cash paid.",
            "The optional fv is the balance remaining after the final payment.",
        ),
        ("FV", "PMT", "NPV"),
    ),
    "FV": (
        _LOANS,
        "Calculate the ending value of an investment or remaining loan balance.",
        "=FV(6.5%/12,5*12,-2212.24,350000)",
        (
            "Use a negative payment when modeling payments made by the investor or borrower.",
            "For a loan balance, the result may need a leading minus sign for positive display.",
            "Set type to 1 only when payments occur at period start.",
        ),
        ("PV", "PMT", "FVSCHEDULE"),
    ),
    "RATE": (
        _LOANS,
        "Solve the periodic interest rate implied by payments and values.",
        "=RATE(30*12,-2212.24,350000)",
        (
            "RATE returns a per-period rate; multiply a monthly result by 12 only when a nominal annual rate is intended.",
            "At least one cash flow must have the opposite sign.",
            "Use the optional guess when the default 10% starting estimate does not converge.",
        ),
        ("PMT", "NPER", "RRI", "IRR"),
    ),
    "NPER": (
        _LOANS,
        "Solve the number of periods needed to pay or grow an amount.",
        "=NPER(6.5%/12,-2500,350000)",
        (
            "NPER returns periods, not years; divide a monthly result by 12 for years.",
            "Payment and present value normally require opposite signs.",
            "A zero-rate case is supported but still requires a nonzero payment.",
        ),
        ("PMT", "RATE", "PDURATION"),
    ),
    "CUMIPMT": (
        _LOANS,
        "Total the interest paid over a selected range of loan periods.",
        "=CUMIPMT(6.5%/12,30*12,350000,1,12,0)",
        (
            "Start and end periods are inclusive and begin at 1.",
            "Rate, nper, and period numbers must share the same frequency.",
            "Type must be 0 for period-end or 1 for period-start payments.",
        ),
        ("IPMT", "CUMPRINC", "PMT"),
    ),
    "CUMPRINC": (
        _LOANS,
        "Total the principal repaid over a selected range of loan periods.",
        "=CUMPRINC(6.5%/12,30*12,350000,1,12,0)",
        (
            "Start and end periods are inclusive and begin at 1.",
            "CUMIPMT plus CUMPRINC equals the payments made over the same interval.",
            "Use a positive pv and expect a negative repayment result under normal sign conventions.",
        ),
        ("PPMT", "CUMIPMT", "PMT"),
    ),
    "ISPMT": (
        _LOANS,
        "Calculate straight-line interest for a specific period.",
        "=ISPMT(6.5%/12,36,30*12,350000)",
        (
            "ISPMT uses even principal reduction, unlike IPMT's level-payment amortization.",
            "The per argument is zero-based in Excel-style usage.",
            "Do not substitute ISPMT for IPMT in a conventional mortgage schedule.",
        ),
        ("IPMT", "PPMT", "SLN"),
    ),
    "NPV": (
        _RETURNS,
        "Discount periodic cash flows that occur at equal intervals.",
        "=NPV(10%,C3:G3)+B3",
        (
            "NPV treats the first supplied cash flow as occurring at the end of period 1.",
            "Add a time-zero investment separately, as shown in the example.",
            "Use XNPV when cash-flow dates are irregular.",
        ),
        ("IRR", "XNPV", "PV"),
    ),
    "IRR": (
        _RETURNS,
        "Solve the periodic discount rate that makes periodic cash flows net to zero.",
        "=IRR(B3:G3)",
        (
            "The cash-flow range must contain at least one positive and one negative value.",
            "IRR is a per-period return; annualize only with the correct period frequency.",
            "Multiple sign changes can produce multiple valid IRRs; inspect NPV at several rates.",
        ),
        ("NPV", "XIRR", "MIRR"),
    ),
    "XNPV": (
        _RETURNS,
        "Discount cash flows using their actual calendar dates.",
        "=XNPV(10%,B2:B7,A2:A7)",
        (
            "Values and dates must contain the same number of entries.",
            "The first date is the valuation date and should be the earliest date.",
            "Use real date cells or DATE formulas rather than ambiguous date text.",
        ),
        ("XIRR", "NPV", "YEARFRAC"),
    ),
    "XIRR": (
        _RETURNS,
        "Solve an annualized return for irregularly dated cash flows.",
        "=XIRR(B2:B7,A2:A7)",
        (
            "Values and dates must have equal length and contain both positive and negative cash flows.",
            "XIRR annualizes using actual days divided by 365.",
            "Use the optional guess when the default starting estimate does not converge.",
        ),
        ("XNPV", "IRR", "MIRR"),
    ),
    "MIRR": (
        _RETURNS,
        "Calculate a return using separate financing and reinvestment rates.",
        "=MIRR(B3:G3,8%,10%)",
        (
            "The series must contain both positive and negative cash flows.",
            "The finance rate discounts negative cash flows; the reinvestment rate compounds positive cash flows.",
            "MIRR avoids IRR's assumption that interim proceeds reinvest at the project IRR.",
        ),
        ("IRR", "NPV", "FVSCHEDULE"),
    ),
    "RRI": (
        _RETURNS,
        "Find the constant growth rate between a present and future value.",
        "=RRI(10,100000,200000)",
        (
            "nper is the number of compounding periods.",
            "Present and future values must produce a nonnegative ratio.",
            "RRI ignores intermediate cash flows; use IRR or XIRR when they exist.",
        ),
        ("PDURATION", "RATE", "FV"),
    ),
    "PDURATION": (
        _RETURNS,
        "Find how many periods are needed for an amount to reach a target.",
        "=PDURATION(8%,100000,200000)",
        (
            "Rate, pv, and fv must be positive.",
            "The result uses the same period as the supplied rate.",
            "PDURATION assumes no intermediate additions or withdrawals.",
        ),
        ("RRI", "NPER", "FV"),
    ),
    "FVSCHEDULE": (
        _RETURNS,
        "Compound a principal through a changing series of periodic rates.",
        "=FVSCHEDULE(B2,C2:C6)",
        (
            "Each schedule cell is one period's rate.",
            "A -100% period reduces the result to zero.",
            "Use FV when the rate is constant and payments occur during the schedule.",
        ),
        ("FV", "RRI", "MIRR"),
    ),
    "EFFECT": (
        _RATES,
        "Convert a nominal annual rate to an effective annual rate.",
        "=EFFECT(6.75%,12)",
        (
            "npery is the number of compounding periods per year and must be at least 1.",
            "The nominal rate must be positive.",
            "Compare investments using effective rates when compounding frequencies differ.",
        ),
        ("NOMINAL", "RATE"),
    ),
    "NOMINAL": (
        _RATES,
        "Convert an effective annual rate to a nominal annual rate.",
        "=NOMINAL(6.965%,12)",
        (
            "npery is truncated to a whole number of compounding periods.",
            "The effective rate must be positive.",
            "NOMINAL is the inverse of EFFECT for the same compounding frequency.",
        ),
        ("EFFECT", "RATE"),
    ),
    "SLN": (
        _DEPRECIATION,
        "Calculate equal straight-line depreciation for each period.",
        "=SLN(100000,10000,7)",
        (
            "Cost, salvage, and life must use consistent units.",
            "The same depreciation amount applies to every full period.",
            "Life cannot be zero.",
        ),
        ("SYD", "DB", "DDB", "VDB"),
    ),
    "SYD": (
        _DEPRECIATION,
        "Calculate accelerated sum-of-years-digits depreciation.",
        "=SYD(100000,10000,7,3)",
        (
            "Period begins at 1 and cannot exceed life.",
            "Earlier periods receive more depreciation than later periods.",
            "The full schedule should sum to cost minus salvage.",
        ),
        ("SLN", "DDB", "VDB"),
    ),
    "DB": (
        _DEPRECIATION,
        "Calculate fixed-declining-balance depreciation.",
        "=DB(100000,10000,7,3,9)",
        (
            "The internally calculated declining rate is rounded to three decimals.",
            "month specifies the number of months in the asset's first year and defaults to 12.",
            "A final partial period may appear when month is less than 12.",
        ),
        ("DDB", "VDB", "SLN"),
    ),
    "DDB": (
        _DEPRECIATION,
        "Calculate declining-balance depreciation using a selected acceleration factor.",
        "=DDB(100000,10000,7,3,1.5)",
        (
            "The default factor is 2 for double-declining balance.",
            "Depreciation will not reduce book value below salvage.",
            "Use VDB when a fractional interval or straight-line switch is needed.",
        ),
        ("DB", "VDB", "SYD"),
    ),
    "VDB": (
        _DEPRECIATION,
        "Calculate variable declining-balance depreciation over an interval.",
        "=VDB(100000,10000,7,1.5,4.25,1.5,FALSE)",
        (
            "start_period is inclusive and end_period is exclusive; fractional periods are supported.",
            "When no_switch is FALSE, depreciation switches to straight line when that is larger.",
            "Set no_switch to TRUE to retain declining balance throughout.",
        ),
        ("DDB", "DB", "SLN"),
    ),
    "PRICE": (
        _BONDS,
        "Price a regular coupon bond per 100 of face value.",
        "=PRICE(B2,B3,B4,B5,100,B6,B7)",
        (
            "Settlement must be before maturity; frequency must be 1, 2, or 4.",
            "Rate and yield are annual rates, not coupon-period rates.",
            "The result is clean price and excludes accrued interest.",
        ),
        ("YIELD", "ACCRINT", "DURATION", "MDURATION"),
    ),
    "YIELD": (
        _BONDS,
        "Solve a regular coupon bond's annual yield from its clean price.",
        "=YIELD(B2,B3,B4,B5,100,B6,B7)",
        (
            "Use a positive clean price and redemption value.",
            "Frequency and basis must match the bond's market convention.",
            "PRICE using the returned yield should reproduce the supplied price within rounding tolerance.",
        ),
        ("PRICE", "DURATION", "YIELDDISC"),
    ),
    "DURATION": (
        _BONDS,
        "Calculate Macaulay duration in years for a regular coupon bond.",
        "=DURATION(B2,B3,B4,B5,B6,B7)",
        (
            "Duration is a present-value-weighted average time to cash flow, not maturity.",
            "Frequency must be 1, 2, or 4 and basis must be 0 through 4.",
            "Zero-coupon bond duration approaches time to maturity.",
        ),
        ("MDURATION", "PRICE", "YIELD"),
    ),
    "MDURATION": (
        _BONDS,
        "Calculate modified duration for approximate price sensitivity to yield.",
        "=MDURATION(B2,B3,B4,B5,B6,B7)",
        (
            "Approximate percentage price change as -modified duration times the yield change.",
            "The approximation is best for small parallel yield changes.",
            "Modified duration is Macaulay duration divided by 1 plus yield per coupon period.",
        ),
        ("DURATION", "PRICE", "YIELD"),
    ),
    "ACCRINT": (
        _BONDS,
        "Calculate accrued coupon interest between issue or coupon and settlement.",
        "=ACCRINT(B2,B3,B4,B5,1000,B6,B7,TRUE)",
        (
            "Issue must precede settlement and first_interest must follow issue.",
            "Frequency is 1, 2, or 4; basis is 0 through 4.",
            "calc_method TRUE accrues from issue; FALSE uses first_interest as the starting point.",
        ),
        ("PRICE", "COUPDAYBS", "COUPDAYS"),
    ),
    "COUPDAYBS": (
        _BONDS,
        "Count days from the previous coupon date to settlement.",
        "=COUPDAYBS(B2,B3,B4,B5)",
        (
            "Frequency must be annual, semiannual, or quarterly: 1, 2, or 4.",
            "Day count follows the selected basis.",
        ),
        ("COUPDAYS", "COUPDAYSNC", "COUPPCD"),
    ),
    "COUPDAYS": (
        _BONDS,
        "Return the day count in the coupon period containing settlement.",
        "=COUPDAYS(B2,B3,B4,B5)",
        (
            "For 30/360 conventions, a semiannual period normally returns 180.",
            "Actual bases reflect the dates in the containing coupon period.",
        ),
        ("COUPDAYBS", "COUPDAYSNC", "COUPNUM"),
    ),
    "COUPDAYSNC": (
        _BONDS,
        "Count days from settlement to the next coupon date.",
        "=COUPDAYSNC(B2,B3,B4,B5)",
        (
            "The result follows the selected day-count basis.",
            "COUPDAYBS plus COUPDAYSNC should reconcile to COUPDAYS under regular schedules.",
        ),
        ("COUPDAYBS", "COUPDAYS", "COUPNCD"),
    ),
    "COUPNCD": (
        _BONDS,
        "Return the next coupon date after settlement.",
        "=COUPNCD(B2,B3,B4,B5)",
        (
            "Format the result cell as a date.",
            "End-of-month maturities preserve end-of-month coupon scheduling.",
        ),
        ("COUPPCD", "COUPNUM", "EDATE"),
    ),
    "COUPNUM": (
        _BONDS,
        "Count coupon payments from settlement through maturity.",
        "=COUPNUM(B2,B3,B4,B5)",
        (
            "The count includes the maturity coupon.",
            "Settlement on a coupon date starts the count with the next coupon.",
        ),
        ("COUPNCD", "COUPPCD", "COUPDAYS"),
    ),
    "COUPPCD": (
        _BONDS,
        "Return the coupon date on or before settlement.",
        "=COUPPCD(B2,B3,B4,B5)",
        (
            "Format the result cell as a date.",
            "The date is derived backward from maturity using the coupon frequency.",
        ),
        ("COUPNCD", "COUPDAYBS", "COUPNUM"),
    ),
    "DISC": (
        _DISCOUNT,
        "Calculate a discount security's annual bank discount rate.",
        "=DISC(B2,B3,B4,B5,B6)",
        (
            "Price and redemption must be positive.",
            "Settlement must precede maturity.",
            "DISC divides the price discount by redemption, unlike YIELDDISC, which divides by price.",
        ),
        ("PRICEDISC", "YIELDDISC", "INTRATE"),
    ),
    "INTRATE": (
        _DISCOUNT,
        "Calculate the annual rate earned on a fully invested security.",
        "=INTRATE(B2,B3,B4,B5,B6)",
        (
            "Investment and redemption must be positive.",
            "The result annualizes the gain using the selected day-count basis.",
        ),
        ("RECEIVED", "DISC", "YIELDDISC"),
    ),
    "RECEIVED": (
        _DISCOUNT,
        "Calculate the maturity proceeds from an investment and discount rate.",
        "=RECEIVED(B2,B3,B4,B5,B6)",
        (
            "The discount times the year fraction must remain below 1.",
            "Investment and discount must be positive.",
        ),
        ("INTRATE", "PRICEDISC", "DISC"),
    ),
    "PRICEDISC": (
        _DISCOUNT,
        "Price a discount security per stated redemption value.",
        "=PRICEDISC(B2,B3,B4,100,B5)",
        (
            "The price equals redemption reduced by discount times the year fraction.",
            "Use the market's correct day-count basis.",
        ),
        ("DISC", "YIELDDISC", "TBILLPRICE"),
    ),
    "YIELDDISC": (
        _DISCOUNT,
        "Calculate annual yield on a discount security using price as the base.",
        "=YIELDDISC(B2,B3,B4,B5,B6)",
        (
            "Price and redemption must be positive.",
            "YIELDDISC is generally higher than DISC for a security priced below redemption.",
        ),
        ("DISC", "PRICEDISC", "TBILLYIELD"),
    ),
    "TBILLPRICE": (
        _TREASURY,
        "Price a Treasury bill per 100 face value from its discount rate.",
        "=TBILLPRICE(B2,B3,B4)",
        (
            "Maturity must be after settlement and no more than one year away.",
            "Treasury bill discount calculations use a 360-day convention.",
        ),
        ("TBILLYIELD", "TBILLEQ", "PRICEDISC"),
    ),
    "TBILLYIELD": (
        _TREASURY,
        "Calculate a Treasury bill's annualized investment yield from price.",
        "=TBILLYIELD(B2,B3,B4)",
        (
            "Price must be positive and maturity cannot exceed one year.",
            "This yield uses price in the denominator and a 360-day year.",
        ),
        ("TBILLPRICE", "TBILLEQ", "YIELDDISC"),
    ),
    "TBILLEQ": (
        _TREASURY,
        "Convert a Treasury bill discount rate to a bond-equivalent yield.",
        "=TBILLEQ(B2,B3,B4)",
        (
            "Maturity must be no more than one year after settlement.",
            "Bond-equivalent yield uses a 365-day numerator for comparison with coupon securities.",
        ),
        ("TBILLPRICE", "TBILLYIELD", "EFFECT"),
    ),
    "DOLLARDE": (
        _QUOTATIONS,
        "Convert a fractional price quotation into a decimal price.",
        "=DOLLARDE(101.08,32)",
        (
            "The fraction argument is the denominator, such as 32 for thirty-seconds.",
            "101.08 with denominator 32 means 101 and 8/32, or 101.25.",
            "A zero denominator returns a division-by-zero error.",
        ),
        ("DOLLARFR", "PRICE"),
    ),
    "DOLLARFR": (
        _QUOTATIONS,
        "Convert a decimal price into a fractional market quotation.",
        "=DOLLARFR(101.25,32)",
        (
            "The fraction argument is the quotation denominator.",
            "The result is a display convention, not an ordinary base-10 decimal fraction.",
            "Use DOLLARDE before arithmetic if fractional quotations are imported.",
        ),
        ("DOLLARDE", "PRICE"),
    ),
}


def financial_help_entries() -> tuple[FinancialHelpEntry, ...]:
    """Return complete curated help for the registered financial library."""
    financial_specs = {
        name: spec
        for name, spec in FUNCTION_REGISTRY.items()
        if spec.implementation.__module__.endswith("finance_fn")
    }
    if set(financial_specs) != set(_DETAILS):
        missing = sorted(set(financial_specs) - set(_DETAILS))
        stale = sorted(set(_DETAILS) - set(financial_specs))
        raise RuntimeError(
            f"Financial help is out of sync; missing={missing}, stale={stale}"
        )
    entries = []
    for name, details in _DETAILS.items():
        category, use_when, example, notes, related = details
        spec = financial_specs[name]
        entries.append(
            FinancialHelpEntry(
                name,
                category,
                f"{name}({spec.argument_spec or 'no arguments'})",
                spec.description,
                use_when,
                example,
                notes,
                related,
            )
        )
    return tuple(sorted(entries, key=lambda entry: (entry.category, entry.name)))


FINANCIAL_HELP_ENTRIES = financial_help_entries()
FINANCIAL_HELP_CATEGORIES = tuple(
    dict.fromkeys(entry.category for entry in FINANCIAL_HELP_ENTRIES)
)


@dataclass(frozen=True, slots=True)
class FinancialToolHelp:
    """Hover help for one command on the Financial menu."""

    key: str
    title: str
    summary: str
    example_title: str
    example_lines: tuple[str, ...]
    example_result: str
    detail: str


# Every example below is calculated by the built-in models named in it, and is
# pinned by tests so the wording cannot drift from what the tools produce.
FINANCIAL_TOOL_HELP: tuple[FinancialToolHelp, ...] = (
    FinancialToolHelp(
        "new_model",
        "New Financial Model",
        "Build a complete, editable workbook from one of seven templates.",
        "Example: Loan Amortization",
        (
            "Summary!B3   350,000 principal",
            "Summary!B4   6.5% annual rate",
            "Summary!B5   30 year term",
            "Summary!B9   =-PMT(B4/B6,B5*B6,B3)",
        ),
        "Monthly payment 2,212.24, plus a full 360-month schedule.",
        "Replaces the current document, so save your work first. "
        "Everything it builds is ordinary and editable.",
    ),
    FinancialToolHelp(
        "goal_seek",
        "Goal Seek",
        "Change one input until a formula reaches the value you want.",
        "Example: what principal fits a 2,000 payment?",
        (
            "Set formula cell    Summary!B9",
            "To value            2000",
            "By changing cell    Summary!B3",
        ),
        "Solves to a principal of 316,421.64.",
        "Runs on a copy, so nothing changes until you accept. "
        "The changing cell must hold a number, not a formula.",
    ),
    FinancialToolHelp(
        "sensitivity",
        "Sensitivity Table",
        "Recalculate one formula across a range of input values.",
        "Example: DCF value per share by WACC and terminal growth",
        (
            "Formula cell        Valuation!B15",
            "Row input cell      Inputs!B11   9%, 10%, 11%",
            "Column input cell   Inputs!B12   2%, 2.5%, 3%",
        ),
        "Writes a 3x3 grid from 13.30 to 20.91, centred on the model's 16.35.",
        "Row values run across the top, not down the side. "
        "Leave the column input blank for a one-variable table.",
    ),
    FinancialToolHelp(
        "scenarios",
        "Scenario Analysis",
        "Compare named sets of assumptions side by side.",
        "Example: growth and margin cases in the DCF model",
        (
            "Base: Inputs!B5=8%, Inputs!B6=22%",
            "Downside: Inputs!B5=3%, Inputs!B6=18%",
            "Upside: Inputs!B5=12%, Inputs!B6=26%",
        ),
        "Value per share of 16.35, 8.52, and 25.83.",
        "One scenario per line. Every case is calculated on a copy, so your "
        "live assumptions are never overwritten.",
    ),
    FinancialToolHelp(
        "audit",
        "Model Audit",
        "Recalculate the workbook, then rank everything worth checking.",
        "Example: the Loan Amortization model",
        (
            "2,527 formulas, 384 inputs, no errors",
            "info  EMBEDDED_CONSTANT  Summary!B7",
        ),
        "That finding is =DATE(2026,8,1); a start date belongs in the model.",
        "Errors first, then warnings, then information. A finding is a prompt "
        "to look, not proof of a mistake.",
    ),
    FinancialToolHelp(
        "guide",
        "Financial Functions Guide",
        "The full offline reference, and where these examples are worked "
        "through step by step.",
        "Contains",
        (
            "All 46 financial functions, searchable",
            "Twelve tutorials, one per Financial command",
            "Quick reference and built-in model guide",
        ),
        "Press F1 to open it from anywhere.",
        "Everything is stored in the application; nothing is fetched.",
    ),
)

FINANCIAL_TOOL_HELP_BY_KEY = {help.key: help for help in FINANCIAL_TOOL_HELP}
