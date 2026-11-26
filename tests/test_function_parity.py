"""Excel function results checked against Microsoft's documented examples."""

from __future__ import annotations

import pytest

from duddysheet.core.engine import FormulaEngine
from duddysheet.core.evaluator import FormulaEvaluator
from duddysheet.core.functions import FUNCTION_REGISTRY
from duddysheet.core.workbook import Workbook

APPROXIMATE = [
    # Statistical distributions
    ("=NORM.S.DIST(1.333333,TRUE)", 0.908788726),
    ("=NORM.DIST(42,40,1.5,TRUE)", 0.9087888),
    ("=NORM.DIST(42,40,1.5,FALSE)", 0.10934005),
    ("=NORM.INV(0.908789,40,1.5)", 42.000002),
    ("=NORM.S.INV(0.908789)", 1.3333347),
    ("=T.DIST(60,1,TRUE)", 0.99469533),
    ("=T.DIST(8,3,FALSE)", 0.00073691),
    ("=T.DIST.2T(1.959999998,60)", 0.054644930),
    ("=T.DIST.RT(1.959999998,60)", 0.027322465),
    ("=T.INV(0.75,2)", 0.8164966),
    ("=T.INV.2T(0.546449,60)", 0.606533),
    ("=CHISQ.DIST(0.5,1,TRUE)", 0.52049988),
    ("=CHISQ.DIST(2,3,FALSE)", 0.20755375),
    ("=CHISQ.DIST.RT(18.307,10)", 0.0500006),
    ("=CHISQ.INV(0.93,1)", 3.283020287),
    ("=CHISQ.INV.RT(0.050001,10)", 18.306973),
    ("=F.DIST(15.2069,6,4,TRUE)", 0.99),
    ("=F.DIST(15.2069,6,4,FALSE)", 0.0012238),
    ("=F.DIST.RT(15.2069,6,4)", 0.01),
    ("=F.INV(0.01,6,4)", 0.10930991),
    ("=F.INV.RT(0.01,6,4)", 15.20686),
    ("=BINOM.DIST(6,10,0.5,FALSE)", 0.2050781),
    ("=BINOM.DIST.RANGE(60,0.75,45,50)", 0.52363),
    ("=BINOM.INV(6,0.5,0.75)", 4),
    ("=POISSON.DIST(2,5,TRUE)", 0.124652),
    ("=POISSON.DIST(2,5,FALSE)", 0.084224),
    ("=EXPON.DIST(0.2,10,TRUE)", 0.86466472),
    ("=EXPON.DIST(0.2,10,FALSE)", 1.35335283),
    ("=GAMMA.DIST(10.00001131,9,2,FALSE)", 0.032639),
    ("=GAMMA.DIST(10.00001131,9,2,TRUE)", 0.068094),
    ("=GAMMA.INV(0.068094,9,2)", 10.0000112),
    ("=BETA.DIST(2,8,10,TRUE,1,3)", 0.6854706),
    ("=BETA.DIST(2,8,10,FALSE,1,3)", 1.4837646),
    ("=BETA.INV(0.685470581,8,10,1,3)", 2),
    ("=WEIBULL.DIST(105,20,100,TRUE)", 0.929581),
    ("=WEIBULL.DIST(105,20,100,FALSE)", 0.035589),
    ("=LOGNORM.DIST(4,3.5,1.2,TRUE)", 0.0390836),
    ("=LOGNORM.DIST(4,3.5,1.2,FALSE)", 0.0176176),
    ("=LOGNORM.INV(0.039084,3.5,1.2)", 4.0000252),
    ("=NEGBINOM.DIST(10,5,0.25,TRUE)", 0.3135141),
    ("=NEGBINOM.DIST(10,5,0.25,FALSE)", 0.0550487),
    ("=HYPGEOM.DIST(1,4,8,20,TRUE)", 0.465428),
    ("=HYPGEOM.DIST(1,4,8,20,FALSE)", 0.363261),
    ("=CONFIDENCE.NORM(0.05,2.5,50)", 0.692952),
    ("=CONFIDENCE.T(0.05,1,50)", 0.284196855),
    # Descriptive statistics
    ("=GAMMA(2.5)", 1.329340),
    ("=GAMMALN(4)", 1.7917595),
    ("=FISHER(0.75)", 0.9729551),
    ("=FISHERINV(0.972955)", 0.75),
    ("=PHI(0.75)", 0.301137432),
    ("=GAUSS(2)", 0.47725),
    ("=SKEW(3,4,5,2,3,4,5,6,4,7)", 0.359543),
    ("=KURT(3,4,5,2,3,4,5,6,4,7)", -0.151799637),
    ("=SKEW.P(3,4,5,2,3,4,5,6,4,7)", 0.303193),
    ("=GEOMEAN(4,5,8,7,11,4,3)", 5.476987),
    ("=HARMEAN(4,5,8,7,11,4,3)", 5.028376),
    ("=TRIMMEAN({4,5,6,7,2,3,4,5,1,2,3},0.2)", 3.777778),
    ("=AVEDEV(4,5,6,7,5,4,3)", 1.020408),
    ("=DEVSQ(4,5,8,7,11,4,3)", 48),
    ("=STANDARDIZE(42,40,1.5)", 1.333333),
    ("=PERCENTILE.EXC({1,2,3,6,6,6,7,8,9},0.25)", 2.5),
    ("=QUARTILE.EXC({6,7,15,36,39,40,41,42,43,47,49},1)", 15),
    ("=QUARTILE.INC({1,2,4,7,8,9,10,12},1)", 3.5),
    ("=PERCENTRANK.INC({13,12,11,8,4,3,2,1,1,1},2)", 0.333),
    ("=PERCENTRANK.INC({13,12,11,8,4,3,2,1,1,1},5)", 0.583),
    ("=PERCENTRANK.EXC({1,2,3,6,6,6,7,8,9},7)", 0.7),
    ("=RANK.AVG(94,{89,88,92,101,94,97,95})", 4),
    ("=RANK.EQ(7,{7,3.5,3.5,1,2},1)", 5),
    ("=COVARIANCE.S({2,4,8},{5,11,12})", 9.666666667),
    ("=COVARIANCE.P({3,2,4,5,6},{9,7,12,15,17})", 5.2),
    ("=PEARSON({9,7,5,3,1},{10,6,1,5,3})", 0.699379),
    ("=RSQ({2,3,9,1,8,7,5},{6,5,11,7,5,4,4})", 0.05795),
    ("=STEYX({2,3,9,1,8,7,5},{6,5,11,7,5,4,4})", 3.305719),
    ("=Z.TEST({3,6,7,8,6,5,4,2,1,9},4)", 0.090574),
    ("=STDEV.S(1345,1301,1368,1322,1310,1370,1318,1350,1303,1299)", 27.46391572),
    ("=VAR.P(1345,1301,1368,1322,1310,1370,1318,1350,1303,1299)", 678.84),
    ("=F.TEST({6,7,9,15,21},{20,28,31,38,40})", 0.64831785),
    ("=CHISQ.TEST({58,35;11,25;10,23},{45.35,47.65;17.56,18.44;16.09,16.91})", 0.0003082),
    ("=T.TEST({3,4,5,8,9,1,2,4,5},{6,19,3,2,14,4,5,17,1},2,1)", 0.196016),
    ("=PERMUT(100,3)", 970200),
    # Math and trigonometry
    ("=SERIESSUM(PI()/4,0,2,{1,-0.5,0.041666667,-0.001388889})", 0.707103),
    ("=SQRTPI(1)", 1.772454),
    ("=COT(30)", -0.156119952),
    ("=COTH(2)", 1.037314721),
    ("=CSC(15)", 1.537780562),
    ("=CSCH(1.5)", 0.469642327),
    ("=SEC(45)", 1.903594407),
    ("=ACOT(2)", 0.463647609),
    ("=ACOTH(6)", 0.168236118),
    ("=SINH(1)", 1.175201194),
    ("=ACOSH(10)", 2.993222846),
    # Engineering
    ('=IMARGUMENT("3+4i")', 0.92729522),
    ("=BESSELJ(1.9,2)", 0.329925829),
    ("=BESSELY(2.5,1)", 0.145918138),
    ("=BESSELI(1.5,1)", 0.981666428),
    ("=BESSELK(1.5,1)", 0.277387804),
    ("=ERF(0.745)", 0.70792892),
    ("=ERF(1)", 0.84270079),
    ("=ERFC(1)", 0.15729921),
    ('=CONVERT(1,"lbm","kg")', 0.45359237),
    ('=CONVERT(CONVERT(100,"ft","m"),"ft","m")', 9.290304),
    ('=CONVERT(1,"gal","l")', 3.785411784),
    ('=CONVERT(100,"C","K")', 373.15),
    # Financial
    ("=ACCRINTM(DATE(2008,4,1),DATE(2008,6,15),0.1,1000,3)", 20.54794521),
    ("=PRICEMAT(DATE(2008,2,15),DATE(2008,4,13),DATE(2007,11,11),0.061,0.061,0)", 99.98449888),
    ("=YIELDMAT(DATE(2008,3,15),DATE(2008,11,3),DATE(2007,11,8),0.0625,100.0123,0)", 0.060954),
    ("=AMORLINC(2400,DATE(2008,8,19),DATE(2008,12,31),300,1,0.15,1)", 360),
    ("=AMORDEGRC(2400,DATE(2008,8,19),DATE(2008,12,31),300,1,0.15,1)", 776),
    (
        "=ODDFPRICE(DATE(2008,11,11),DATE(2021,3,1),DATE(2008,10,15),DATE(2009,3,1),0.0785,0.0625,100,2,1)",
        113.597717,
    ),
    (
        "=ODDFYIELD(DATE(2008,11,11),DATE(2021,3,1),DATE(2008,10,15),DATE(2009,3,1),0.0575,84.5,100,2,0)",
        0.077245542,
    ),
    ("=ODDLPRICE(DATE(2008,2,7),DATE(2008,6,15),DATE(2007,10,15),0.0375,0.0405,100,2,0)", 99.87829),
    ("=ODDLYIELD(DATE(2008,4,20),DATE(2008,6,15),DATE(2007,12,24),0.0375,99.875,100,2,0)", 0.045192),
    ('=EUROCONVERT(1,"FRF","DEM",TRUE,3)', 0.29728616),
]

EXACT = [
    # Math
    ("=EVEN(1.5)", 2),
    ("=EVEN(-1)", -2),
    ("=ODD(2)", 3),
    ("=QUOTIENT(-10,3)", -3),
    ("=FACT(5)", 120),
    ("=FACTDOUBLE(7)", 105),
    ("=COMBIN(8,2)", 28),
    ("=COMBINA(4,3)", 20),
    ("=MULTINOMIAL(2,3,4)", 1260),
    ("=SUMX2MY2({2,3,9,1,8,7,5},{6,5,11,7,5,4,4})", -55),
    ("=SUMX2PY2({2,3,9,1,8,7,5},{6,5,11,7,5,4,4})", 521),
    ("=SUMXMY2({2,3,9,1,8,7,5},{6,5,11,7,5,4,4})", 79),
    ("=CEILING.MATH(-5.5,2,-1)", -6),
    ("=FLOOR.MATH(-8.1,2)", -10),
    ("=CEILING.PRECISE(4.3,-2)", 6),
    ("=ISO.CEILING(-4.3,2)", -4),
    ('=ARABIC("mcmxii")', 1912),
    ("=ROMAN(499,0)", "CDXCIX"),
    ("=ROMAN(499,1)", "LDVLIV"),
    ("=ROMAN(499,2)", "XDIX"),
    ("=ROMAN(499,3)", "VDIV"),
    ("=ROMAN(499,4)", "ID"),
    ("=BASE(15,2,10)", "0000001111"),
    ('=DECIMAL("zap",36)', 45745),
    ("=MDETERM({1,3,8,5;1,3,6,1;1,1,1,0;7,3,10,2})", 88),
    ("=AGGREGATE(14,6,{1,#DIV/0!,3},1)", 3),
    # Engineering
    ("=COMPLEX(3,4,\"j\")", "3+4j"),
    ('=IMCOS("1+i")', "0.833730025131149-0.988897705762865i"),
    ('=IMDIV("-238+240i","10+24i")', "5+12i"),
    ('=IMLN("3+4i")', "1.6094379124341+0.927295218001612i"),
    ('=IMPRODUCT("3+4i","5-3i")', "27+11i"),
    ('=IMSUB("13+4i","5+3i")', "8+i"),
    ('=HEX2DEC("FFFFFFFF9C")', -100),
    ("=DEC2BIN(-100)", "1110011100"),
    ("=DEC2OCT(-100)", "7777777634"),
    ('=BIN2HEX("1111111111")', "FFFFFFFFFF"),
    ("=DEC2BIN(512)", "#NUM!"),
    ('=CONVERT(2.5,"ft","sec")', "#N/A"),
    ('=CONVERT(68,"F","C")', 20),
    # Lookup
    ('=VLOOKUP(2,{1,"a";2,"b";2,"c";3,"d"},2,TRUE)', "c"),
    ('=VLOOKUP("m",{"a",1;"k",2;"z",3},2,TRUE)', 2),
    ('=VLOOKUP("b*",{"apple",1;"banana",2},2,FALSE)', 2),
    ('=MATCH("ba?ana",{"apple","banana"},0)', 2),
    ("=MATCH(25,{50,40,30,20},-1)", 3),
    ("=MATCH(39,{25,38,40,41})", 2),
    ('=XLOOKUP(5,{1,3,7},{"a","b","c"},,-1)', "b"),
    ('=XLOOKUP(5,{1,3,7},{"a","b","c"},,1)', "c"),
    ('=XLOOKUP("*an*",{"apple","banana"},{1,2},,2)', 2),
    ("=XMATCH(4,{5,4,3,2,1},0,-2)", 2),
    ('=LOOKUP(5,{4.14,4.19,5.17},{"red","orange","yellow"})', "orange"),
    ("=ADDRESS(2,3,2,FALSE)", "R2C[3]"),
    ('=ADDRESS(1,1,1,TRUE,"My Sheet")', "'My Sheet'!$A$1"),
    # Text and dates
    ('=TEXT(1234.567,"$#,##0.00")', "$1,234.57"),
    ('=TEXT(DATE(2025,12,9),"dddd, mmmm d")', "Tuesday, December 9"),
    ('=TEXT(4.34,"# ?/?")', "4 1/3"),
    ('=TEXT(TIME(13,29,0),"h:mm AM/PM")', "1:29 PM"),
    ('=TEXT("12.5","0.00")', "12.50"),
    ('=TRIM("  a   b  ")', "a b"),
    ("=DOLLAR(-1234.567,2)", "($1,234.57)"),
    ("=FIXED(1234.567,-1)", "1,230"),
    ('=REGEXEXTRACT("tel 555-1234","\\d{3}-\\d{4}")', "555-1234"),
    ('=REGEXREPLACE("a1b2","[0-9]","#")', "a#b#"),
    ('=VALUETOTEXT("x",1)', '"x"'),
    ("=DAYS360(DATE(2011,1,30),DATE(2011,12,31))", 330),
    ("=ISOWEEKNUM(DATE(2012,3,9))", 10),
    ("=NETWORKDAYS.INTL(DATE(2006,1,1),DATE(2006,1,31))", 22),
    ("=NETWORKDAYS.INTL(DATE(2006,2,28),DATE(2006,1,31))", -21),
    ('=NETWORKDAYS.INTL(DATE(2006,1,1),DATE(2006,2,1),"0010001",{"2006/1/2","2006/1/16"})', 20),
    ('=NETWORKDAYS.INTL(DATE(2006,1,1),DATE(2006,2,1),"0010001")', 22),
    ("=WORKDAY.INTL(DATE(2012,1,1),90,11)", 41013),
    # Counting semantics
    ('=COUNTA({1,"",2})', 3),
    ('=COUNTIF({1,"",0},0)', 1),
    ('=COUNTIF({"apple",10,"art"},"a*")', 2),
    ('=COUNTIF({TRUE,1},TRUE)', 1),
    ('=SUM({1,TRUE,"2"})', 1),
    ('=SUM("3",TRUE)', 4),
    ('=EUROCONVERT(1.2,"DEM","EUR")', 0.61),
]


@pytest.mark.parametrize(("formula", "expected"), APPROXIMATE)
def test_documented_numeric_results(formula: str, expected: float) -> None:
    result = FormulaEvaluator(Workbook()).evaluate(formula)

    assert isinstance(result, (int, float)), (formula, result)
    assert result == pytest.approx(expected, rel=2e-5, abs=1e-6)


@pytest.mark.parametrize(("formula", "expected"), EXACT)
def test_documented_exact_results(formula: str, expected: object) -> None:
    result = FormulaEvaluator(Workbook()).evaluate(formula)

    assert getattr(result, "literal", result) == expected


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ('=SORT({3,"b";1,"a";2,"c"},2,-1)', ((2, "c"), (3, "b"), (1, "a"))),
        ('=SORT({"b";TRUE;2;"A"})', ((2,), ("A",), ("b",), (True,))),
        ('=SORTBY({"x";"y";"z"},{3;1;2})', (("y",), ("z",), ("x",))),
        ('=UNIQUE({"a";"A";"b"})', (("a",), ("b",))),
        ("=FILTER({1,2,3;4,5,6},{TRUE,FALSE,TRUE})", ((1, 3), (4, 6))),
        ("=TOROW({1,2;3,4},0,TRUE)", ((1, 3, 2, 4),)),
        ("=WRAPCOLS({1,2,3,4,5},2,0)", ((1, 3, 5), (2, 4, 0))),
        ("=TAKE({1,2;3,4;5,6},-2,1)", ((3,), (5,))),
        ("=CHOOSEROWS({1,2;3,4;5,6},3,1)", ((5, 6), (1, 2))),
        ("=EXPAND({1,2},2,3,0)", ((1, 2, 0), (0, 0, 0))),
        ('=GROUPBY({"a";"b";"a"},{1;2;3},LAMBDA(v,SUM(v)))', (("a", 4), ("b", 2), ("Total", 6))),
        ("=MODE.MULT({1,2,3,4,3,2,1,2,3})", ((2,), (3,))),
        ("=FREQUENCY({79,85,78,85,50,81,95,88,97},{70,79,89})", ((1,), (2,), (4,), (2,))),
        ("=MMULT({1,3;7,2},{2,0;0,2})", ((2, 6), (14, 4))),
        ('=FILTERXML("<r><n>5</n><n>7</n></r>","//n")', ((5,), (7,))),
    ],
)
def test_dynamic_array_results(formula: str, expected: object) -> None:
    assert FormulaEvaluator(Workbook()).evaluate(formula) == expected


def test_database_functions_match_microsoft_example() -> None:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    data = [
        ["Tree", "Height", "Age", "Yield", "Profit"],
        ["Apple", 18, 20, 14, 105],
        ["Pear", 12, 12, 10, 96],
        ["Cherry", 13, 14, 9, 105],
        ["Apple", 14, 15, 10, 75],
        ["Pear", 9, 8, 8, 77],
        ["Apple", 8, 9, 6, 45],
    ]
    for row, values in enumerate(data):
        for column, value in enumerate(values):
            engine.set_cell("Sheet1", 4 + row, column, value)
    criteria = [
        ["Tree", "Height", "Age", "Yield", "Profit", "Height"],
        ['="=Apple"', ">10", None, None, None, "<16"],
        ['="=Pear"', None, None, None, None, None],
    ]
    for row, values in enumerate(criteria):
        for column, value in enumerate(values):
            if value is not None:
                engine.set_cell("Sheet1", row, column, value)
    expected = {
        '=DCOUNT(A5:E11,"Age",A1:F2)': 1,
        '=DMAX(A5:E11,"Profit",A1:A3)': 105,
        '=DMIN(A5:E11,"Profit",A1:B2)': 75,
        '=DSUM(A5:E11,"Profit",A1:A2)': 225,
        '=DSUM(A5:E11,"Profit",A1:F2)': 75,
        '=DPRODUCT(A5:E11,"Yield",A1:F2)': 10,
        '=DAVERAGE(A5:E11,"Yield",A1:B2)': 12,
        '=DAVERAGE(A5:E11,3,A5:E11)': 13,
        '=DSTDEV(A5:E11,"Yield",A1:A3)': pytest.approx(2.96647939),
        '=DVARP(A5:E11,"Yield",A1:A3)': pytest.approx(7.04),
    }
    for offset, (formula, value) in enumerate(expected.items()):
        engine.set_cell("Sheet1", 20 + offset, 8, formula)
        assert workbook.active_sheet.get_cell(20 + offset, 8).cached_value == value, formula
    engine.set_cell("Sheet1", 40, 8, '=DGET(A5:E11,"Yield",A1:A3)')
    assert workbook.active_sheet.get_cell(40, 8).error == "#NUM!"


def test_subtotal_skips_filtered_and_hidden_rows() -> None:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    for row, value in enumerate((10, 20, 30, 40)):
        engine.set_cell("Sheet1", row, 0, value)
    engine.set_cell("Sheet1", 4, 0, "=SUBTOTAL(9,A1:A4)")
    sheet = workbook.active_sheet
    sheet.hidden_rows.add(1)
    sheet.filtered_rows.add(2)
    sheet.hidden_rows.add(2)

    engine.set_cell("Sheet1", 5, 0, "=SUBTOTAL(9,A1:A5)")
    engine.set_cell("Sheet1", 6, 0, "=SUBTOTAL(109,A1:A4)")
    engine.set_cell("Sheet1", 7, 0, "=AGGREGATE(9,5,A1:A4)")

    assert sheet.get_cell(5, 0).cached_value == 70  # 10+20+40, nested SUBTOTAL ignored
    assert sheet.get_cell(6, 0).cached_value == 50  # 10+40
    assert sheet.get_cell(7, 0).cached_value == 50


def test_information_functions_inspect_cells() -> None:
    workbook = Workbook()
    engine = FormulaEngine(workbook)
    engine.set_cell("Sheet1", 0, 0, "=1+1")
    engine.set_cell("Sheet1", 1, 0, "text")
    for row, formula in enumerate(
        (
            "=FORMULATEXT(A1)",
            "=ISFORMULA(A1)",
            "=ISFORMULA(A2)",
            '=CELL("address",B7)',
            '=CELL("type",A2)',
            "=SHEET()",
            "=SHEETS()",
            "=ISREF(A1)",
        )
    ):
        engine.set_cell("Sheet1", row, 3, formula)
    sheet = workbook.active_sheet
    values = [sheet.get_cell(row, 3).cached_value for row in range(8)]
    assert values == ["=1+1", True, False, "$B$7", "l", 1, 1, True]


def test_offline_service_functions_are_blocked_not_unknown() -> None:
    evaluator = FormulaEvaluator(Workbook())

    for name in ("WEBSERVICE", "STOCKHISTORY", "IMAGE", "CUBEVALUE", "RTD"):
        assert name in FUNCTION_REGISTRY
        assert evaluator.evaluate(f'={name}("x")').literal == "#BLOCKED!"


def test_library_covers_excels_catalog() -> None:
    assert len(FUNCTION_REGISTRY) >= 520
