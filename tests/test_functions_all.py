from __future__ import annotations

from datetime import date

import pytest

from excelclone.core.errors import NA_ERROR, SpreadsheetError, VALUE_ERROR
from excelclone.core.evaluator import FormulaEvaluator
from excelclone.core.functions import FUNCTION_REGISTRY
from excelclone.core.tokenizer import FormulaSyntaxError
from excelclone.core.workbook import Workbook


SMOKE_FORMULAS = {
    "ABS": "=ABS(-2)",
    "ACOS": "=ACOS(1)",
    "ACCRINT": "=ACCRINT(DATE(2025,1,1),DATE(2025,7,1),DATE(2025,3,1),0.05,1000,2)",
    "AND": "=AND(TRUE,FALSE)",
    "ASIN": "=ASIN(0)",
    "ATAN": "=ATAN(1)",
    "ATAN2": "=ATAN2(1,1)",
    "AVERAGE": "=AVERAGE({1,2,3})",
    "AVERAGEIF": '=AVERAGEIF({1,2,3},">1")',
    "AVERAGEIFS": '=AVERAGEIFS({1,2,3},{1,2,3},">1")',
    "CEILING": "=CEILING(5,2)",
    "CHAR": "=CHAR(65)",
    "CHOOSE": '=CHOOSE(2,"a","b")',
    "CODE": '=CODE("A")',
    "COLUMN": "=COLUMN()",
    "COLUMNS": "=COLUMNS({1,2})",
    "CONCAT": '=CONCAT("a","b")',
    "CONCATENATE": '=CONCATENATE("a","b")',
    "CORREL": "=CORREL({1,2,3},{2,4,6})",
    "COS": "=COS(0)",
    "COUPDAYBS": "=COUPDAYBS(DATE(2025,2,15),DATE(2027,2,15),2)",
    "COUPDAYS": "=COUPDAYS(DATE(2025,2,15),DATE(2027,2,15),2)",
    "COUPDAYSNC": "=COUPDAYSNC(DATE(2025,2,15),DATE(2027,2,15),2)",
    "COUPNCD": "=COUPNCD(DATE(2025,2,15),DATE(2027,2,15),2)",
    "COUPNUM": "=COUPNUM(DATE(2025,2,15),DATE(2027,2,15),2)",
    "COUPPCD": "=COUPPCD(DATE(2025,2,15),DATE(2027,2,15),2)",
    "COUNT": "=COUNT({1,2,\"x\"})",
    "COUNTA": "=COUNTA({1,\"\",2})",
    "COUNTBLANK": '=COUNTBLANK({1,""})',
    "COUNTIF": '=COUNTIF({1,2,3},">1")',
    "COUNTIFS": '=COUNTIFS({1,2,3},">1")',
    "CUMIPMT": "=CUMIPMT(0.01,12,1000,1,6,0)",
    "CUMPRINC": "=CUMPRINC(0.01,12,1000,1,6,0)",
    "DATE": "=DATE(2026,7,25)",
    "DATEDIF": '=DATEDIF(DATE(2020,1,1),DATE(2022,3,1),"Y")',
    "DATEVALUE": '=DATEVALUE("2026-07-25")',
    "DAY": "=DAY(DATE(2026,7,25))",
    "DAYS": "=DAYS(DATE(2026,1,2),DATE(2026,1,1))",
    "DB": "=DB(10000,1000,5,1)",
    "DDB": "=DDB(10000,1000,5,1)",
    "DEGREES": "=DEGREES(PI())",
    "DISC": "=DISC(DATE(2025,1,1),DATE(2025,7,1),97,100)",
    "DOLLARDE": "=DOLLARDE(1.02,16)",
    "DOLLARFR": "=DOLLARFR(1.125,16)",
    "DURATION": "=DURATION(DATE(2025,1,1),DATE(2030,1,1),0.05,0.06,2)",
    "EDATE": "=EDATE(DATE(2026,1,31),1)",
    "EOMONTH": "=EOMONTH(DATE(2026,1,15),0)",
    "EFFECT": "=EFFECT(0.06,12)",
    "ERROR.TYPE": "=ERROR.TYPE(NA())",
    "EXACT": '=EXACT("a","a")',
    "EXP": "=EXP(1)",
    "FALSE": "=FALSE()",
    "FILTER": "=FILTER({1;2},{TRUE;FALSE},0)",
    "FIND": '=FIND("b","abc")',
    "FLOOR": "=FLOOR(5,2)",
    "FORECAST": "=FORECAST(4,{2,4,6},{1,2,3})",
    "FV": "=FV(0.01,12,-100,0)",
    "FVSCHEDULE": "=FVSCHEDULE(100,{0.05,0.04,0.03})",
    "GCD": "=GCD(8,12)",
    "HLOOKUP": '=HLOOKUP("b",{"a","b";1,2},2,FALSE)',
    "HOUR": "=HOUR(TIME(13,30,15))",
    "IF": '=IF(TRUE,"yes","no")',
    "IFERROR": "=IFERROR(1/0,0)",
    "IFNA": "=IFNA(NA(),0)",
    "IFS": "=IFS(FALSE,1,TRUE,2)",
    "INDEX": "=INDEX({1,2;3,4},2,2)",
    "INDIRECT": '=INDIRECT("A1")',
    "INT": "=INT(1.9)",
    "INTERCEPT": "=INTERCEPT({2,4,6},{1,2,3})",
    "INTRATE": "=INTRATE(DATE(2025,1,1),DATE(2025,7,1),97,100)",
    "IPMT": "=IPMT(0.01,1,12,1000)",
    "IRR": "=IRR({-100,60,60})",
    "ISPMT": "=ISPMT(0.01,1,12,1000)",
    "ISBLANK": "=ISBLANK(A999)",
    "ISERR": "=ISERR(1/0)",
    "ISERROR": "=ISERROR(1/0)",
    "ISLOGICAL": "=ISLOGICAL(TRUE)",
    "ISNA": "=ISNA(NA())",
    "ISNUMBER": "=ISNUMBER(1)",
    "ISTEXT": '=ISTEXT("x")',
    "LARGE": "=LARGE({1,3,2},2)",
    "LCM": "=LCM(4,6)",
    "LEFT": '=LEFT("abc",2)',
    "LEN": '=LEN("abc")',
    "LN": "=LN(1)",
    "LOG": "=LOG(100,10)",
    "LOG10": "=LOG10(100)",
    "LOOKUP": "=LOOKUP(2,{1,2,3},{10,20,30})",
    "LOWER": '=LOWER("ABC")',
    "MATCH": "=MATCH(2,{1,2,3},0)",
    "MAX": "=MAX({1,2,3})",
    "MAXIFS": '=MAXIFS({1,2,3},{1,2,3},">1")',
    "MDURATION": "=MDURATION(DATE(2025,1,1),DATE(2030,1,1),0.05,0.06,2)",
    "MEDIAN": "=MEDIAN({1,3,2})",
    "MID": '=MID("abcd",2,2)',
    "MIN": "=MIN({1,2,3})",
    "MINIFS": '=MINIFS({1,2,3},{1,2,3},">1")',
    "MINUTE": "=MINUTE(TIME(13,30,15))",
    "MIRR": "=MIRR({-100,60,60},0.08,0.1)",
    "MOD": "=MOD(5,2)",
    "MODE": "=MODE({1,1,2})",
    "MONTH": "=MONTH(DATE(2026,7,25))",
    "MROUND": "=MROUND(5,2)",
    "N": "=N(TRUE)",
    "NA": "=NA()",
    "NETWORKDAYS": "=NETWORKDAYS(DATE(2026,7,20),DATE(2026,7,24))",
    "NOMINAL": "=NOMINAL(0.0617,12)",
    "NOT": "=NOT(FALSE)",
    "NOW": "=NOW()",
    "NPER": "=NPER(0.01,-88.85,1000)",
    "NPV": "=NPV(0.1,-100,60,60)",
    "NUMBERVALUE": '=NUMBERVALUE("1.234,5",",",".")',
    "OFFSET": "=OFFSET(A1,0,0)",
    "OR": "=OR(FALSE,TRUE)",
    "PERCENTILE": "=PERCENTILE({1,2,3,4},0.5)",
    "PDURATION": "=PDURATION(0.08,1000,2000)",
    "PI": "=PI()",
    "PMT": "=PMT(0.01,12,1000)",
    "POWER": "=POWER(2,3)",
    "PPMT": "=PPMT(0.01,1,12,1000)",
    "PRICE": "=PRICE(DATE(2025,1,1),DATE(2030,1,1),0.05,0.06,100,2)",
    "PRICEDISC": "=PRICEDISC(DATE(2025,1,1),DATE(2025,7,1),0.05,100)",
    "PRODUCT": "=PRODUCT({2,3,4})",
    "PROPER": '=PROPER("open grid")',
    "PV": "=PV(0.01,12,-100)",
    "QUARTILE": "=QUARTILE({1,2,3,4,5},2)",
    "RADIANS": "=RADIANS(180)",
    "RAND": "=RAND()",
    "RANDBETWEEN": "=RANDBETWEEN(1,3)",
    "RANK": "=RANK(2,{1,2,3},0)",
    "RATE": "=RATE(12,-88.85,1000)",
    "RECEIVED": "=RECEIVED(DATE(2025,1,1),DATE(2025,7,1),97,0.05)",
    "REPLACE": '=REPLACE("abcd",2,2,"X")',
    "REPT": '=REPT("x",3)',
    "RIGHT": '=RIGHT("abc",2)',
    "RRI": "=RRI(10,1000,2000)",
    "ROUND": "=ROUND(1.25,1)",
    "ROUNDDOWN": "=ROUNDDOWN(1.29,1)",
    "ROUNDUP": "=ROUNDUP(1.21,1)",
    "ROW": "=ROW()",
    "ROWS": "=ROWS({1;2})",
    "SEARCH": '=SEARCH("B*","abc")',
    "SECOND": "=SECOND(TIME(13,30,15))",
    "SIGN": "=SIGN(-2)",
    "SIN": "=SIN(0)",
    "SLN": "=SLN(100,10,9)",
    "SLOPE": "=SLOPE({2,4,6},{1,2,3})",
    "SMALL": "=SMALL({1,3,2},2)",
    "SORT": "=SORT({3;1;2})",
    "SQRT": "=SQRT(4)",
    "STDEV": "=STDEV({1,2,3})",
    "STDEVP": "=STDEVP({1,2,3})",
    "SUBSTITUTE": '=SUBSTITUTE("aba","a","x")',
    "SUM": "=SUM({1,2,3})",
    "SUMIF": '=SUMIF({1,2,3},">1")',
    "SUMIFS": '=SUMIFS({1,2,3},{1,2,3},">1")',
    "SUMPRODUCT": "=SUMPRODUCT({1,2},{3,4})",
    "SWITCH": '=SWITCH(2,1,"a",2,"b","x")',
    "SYD": "=SYD(10000,1000,5,1)",
    "TAN": "=TAN(0)",
    "TBILLEQ": "=TBILLEQ(DATE(2025,1,1),DATE(2025,7,1),0.05)",
    "TBILLPRICE": "=TBILLPRICE(DATE(2025,1,1),DATE(2025,7,1),0.05)",
    "TBILLYIELD": "=TBILLYIELD(DATE(2025,1,1),DATE(2025,7,1),97)",
    "TEXT": '=TEXT(12.3,"0.00")',
    "TEXTAFTER": '=TEXTAFTER("a-b","-")',
    "TEXTBEFORE": '=TEXTBEFORE("a-b","-")',
    "TEXTJOIN": '=TEXTJOIN("-",TRUE,"a","b")',
    "TEXTSPLIT": '=TEXTSPLIT("a,b",",")',
    "TIME": "=TIME(13,30,15)",
    "TIMEVALUE": '=TIMEVALUE("13:30:15")',
    "TODAY": "=TODAY()",
    "TRANSPOSE": "=TRANSPOSE({1,2;3,4})",
    "TREND": "=TREND({2,4,6},{1,2,3},{4})",
    "TRIM": '=TRIM("  a   b  ")',
    "TRUE": "=TRUE()",
    "TRUNC": "=TRUNC(1.29,1)",
    "TYPE": "=TYPE(1)",
    "UNIQUE": "=UNIQUE({1;1;2})",
    "UPPER": '=UPPER("abc")',
    "VALUE": '=VALUE("12.5")',
    "VAR": "=VAR({1,2,3})",
    "VARP": "=VARP({1,2,3})",
    "VDB": "=VDB(10000,1000,5,0,1)",
    "VLOOKUP": '=VLOOKUP("b",{"a",1;"b",2},2,FALSE)',
    "WEEKDAY": "=WEEKDAY(DATE(2026,7,25),2)",
    "WEEKNUM": "=WEEKNUM(DATE(2026,7,25),2)",
    "WORKDAY": "=WORKDAY(DATE(2026,7,24),1)",
    "XIRR": "=XIRR({-100,110},{DATE(2025,1,1),DATE(2026,1,1)})",
    "XLOOKUP": '=XLOOKUP("b",{"a","b"},{1,2})',
    "XMATCH": '=XMATCH("b",{"a","b"})',
    "XNPV": "=XNPV(0.1,{-100,110},{DATE(2025,1,1),DATE(2026,1,1)})",
    "XOR": "=XOR(TRUE,FALSE)",
    "YEAR": "=YEAR(DATE(2026,7,25))",
    "YEARFRAC": "=YEARFRAC(DATE(2025,1,1),DATE(2026,1,1),1)",
    "YIELD": "=YIELD(DATE(2025,1,1),DATE(2030,1,1),0.05,95,100,2)",
    "YIELDDISC": "=YIELDDISC(DATE(2025,1,1),DATE(2025,7,1),97,100)",
}


def test_smoke_map_covers_every_registered_function() -> None:
    assert set(SMOKE_FORMULAS) == set(FUNCTION_REGISTRY)


@pytest.mark.parametrize("name", sorted(SMOKE_FORMULAS))
def test_registered_function_has_successful_smoke_case(name: str) -> None:
    evaluator = FormulaEvaluator(Workbook())

    result = evaluator.evaluate(SMOKE_FORMULAS[name])

    if name == "NA":
        assert result == NA_ERROR
    else:
        assert not isinstance(result, SpreadsheetError), (name, result)


@pytest.mark.parametrize("name", sorted(SMOKE_FORMULAS))
def test_registered_function_rejects_invalid_arity(name: str) -> None:
    specification = FUNCTION_REGISTRY[name]
    if specification.min_args:
        formula = f"={name}()"
    else:
        arguments = ",".join("1" for _ in range(specification.max_args + 1))
        formula = f"={name}({arguments})"

    try:
        result = FormulaEvaluator(Workbook()).evaluate(formula)
    except FormulaSyntaxError:
        assert name in {"FALSE", "TRUE"}
    else:
        assert result == VALUE_ERROR


@pytest.mark.parametrize("name", sorted(SMOKE_FORMULAS))
def test_registered_function_exposes_complete_help_metadata(name: str) -> None:
    specification = FUNCTION_REGISTRY[name]

    assert specification.name == name
    assert specification.description
    assert 0 <= specification.min_args <= specification.max_args <= 255


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("=SUM(1,2,3)", 6),
        ('=SUMIFS({10,20,30,40},{1,1,2,2},2,{"a","b","a","b"},"b",{5,6,7,8},">7")', 40),
        ('=VLOOKUP("b",{"a",10;"b",20;"c",30},2,FALSE)', 20),
        ('=XLOOKUP("b",{"a","b","c"},{10,20,30})', 20),
        ("=INDEX({10,20;30,40},MATCH(30,{10;30},0),1)", 30),
        ('=IF(TRUE,IF(TRUE,IF(TRUE,IF(TRUE,IF(TRUE,"deep","x"),"x"),"x"),"x"),"x")', "deep"),
        ('=IFERROR(1/0,"caught")', "caught"),
        ("=ERROR.TYPE(#REF!)", 4),
        ("=DATE(1900,3,1)", 61),
        ("=ROUND(2.5,0)", 3),
        ("=ROUND(-2.5,0)", -3),
        ("=MOD(-3,2)", 1),
        ("=TEXTJOIN(\",\",TRUE,\"a\",\"\", \"b\")", "a,b"),
        ("=UNIQUE({1;1;2})", ((1,), (2,))),
        ("=FILTER({10;20;30},{FALSE;TRUE;TRUE})", ((20,), (30,))),
    ],
)
def test_critical_function_results_match_known_values(
    formula: str,
    expected: object,
) -> None:
    assert FormulaEvaluator(Workbook()).evaluate(formula) == expected


def test_date_functions_accept_real_date_cell_values() -> None:
    workbook = Workbook()
    workbook.active_sheet.set_cell(0, 0, date(2026, 7, 25))

    assert FormulaEvaluator(workbook).evaluate("=YEAR(A1)") == 2026
