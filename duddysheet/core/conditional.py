"""Conditional-format rule evaluation independent of Qt painting."""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any

from duddysheet.core.cell import BorderStyle, CellFormat
from duddysheet.core.evaluator import FormulaEvaluator
from duddysheet.core.parser import parse_formula, shift_references
from duddysheet.core.refs import RangeReference
from duddysheet.core.sheet import Sheet
from duddysheet.core.workbook import Workbook


@dataclass(frozen=True, slots=True)
class FormatPatch:
    """Optional format attributes overlaid by a matching rule."""

    number_format: str | None = None
    font_family: str | None = None
    font_size: float | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    font_color: str | None = None
    fill_color: str | None = None
    horizontal_alignment: str | None = None
    vertical_alignment: str | None = None
    wrap_text: bool | None = None
    left_border: BorderStyle | None = None
    right_border: BorderStyle | None = None
    top_border: BorderStyle | None = None
    bottom_border: BorderStyle | None = None

    def apply(self, base: CellFormat) -> CellFormat:
        """Return a cell format with non-None attributes replaced."""
        changes = {
            item.name: getattr(self, item.name)
            for item in fields(self)
            if getattr(self, item.name) is not None
        }
        return replace(base, **changes)


@dataclass(frozen=True, slots=True)
class ConditionalRule:
    """A conditional rule scoped to one rectangular range."""

    range: RangeReference
    kind: str
    operator: str = "equal"
    values: tuple[Any, ...] = ()
    format_patch: FormatPatch = FormatPatch()
    rank: int = 10
    percent: bool = False
    above: bool = True
    formula: str | None = None
    colors: tuple[str, ...] = ("#f8696b", "#ffeb84", "#63be7b")
    stop_if_true: bool = False


@dataclass(frozen=True, slots=True)
class ConditionalResult:
    """Effective cell format and optional delegate visual data."""

    format: CellFormat
    data_bar: float | None = None
    icon: str | None = None


class ConditionalFormatEngine:
    """Evaluate ordered rules for cells in one workbook."""

    def __init__(self, workbook: Workbook) -> None:
        self.workbook = workbook
        self.evaluator = FormulaEvaluator(workbook)

    def evaluate(self, sheet: Sheet, row: int, column: int) -> ConditionalResult:
        """Return the effective presentation for a coordinate."""
        cell = sheet.get_cell(row, column)
        effective = cell.format
        data_bar: float | None = None
        icon: str | None = None
        for rule in sheet.conditional_formats:
            if not isinstance(rule, ConditionalRule):
                continue
            if rule.range.sheet is not None and (
                rule.range.sheet.casefold() != sheet.name.casefold()
            ):
                continue
            if not rule.range.contains(row, column):
                continue
            matched, visual_fill, rule_bar, rule_icon = self._evaluate_rule(
                rule,
                sheet,
                row,
                column,
            )
            if not matched:
                continue
            effective = rule.format_patch.apply(effective)
            if visual_fill is not None:
                effective = replace(effective, fill_color=visual_fill)
            data_bar = rule_bar if rule_bar is not None else data_bar
            icon = rule_icon if rule_icon is not None else icon
            if rule.stop_if_true:
                break
        return ConditionalResult(effective, data_bar, icon)

    def _evaluate_rule(
        self,
        rule: ConditionalRule,
        sheet: Sheet,
        row: int,
        column: int,
    ) -> tuple[bool, str | None, float | None, str | None]:
        value = sheet.get_cell(row, column).display_value
        if rule.kind == "cell_value":
            return _cell_value_matches(value, rule.operator, rule.values), None, None, None
        if rule.kind == "formula":
            if not rule.formula:
                return False, None, None, None
            try:
                formula = shift_references(
                    parse_formula(rule.formula),
                    rows=row - rule.range.min_row,
                    columns=column - rule.range.min_column,
                )
                result = self.evaluator.evaluate(
                    formula,
                    sheet_name=sheet.name,
                    origin=(row, column),
                )
            except ValueError:
                return False, None, None, None
            return bool(result) if not isinstance(result, str) else False, None, None, None

        numbers = _numeric_values(sheet, rule.range)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not numbers:
            return False, None, None, None
        numeric_value = float(value)
        minimum, maximum = min(numbers), max(numbers)
        ratio = 0.0 if maximum == minimum else (numeric_value - minimum) / (maximum - minimum)
        ratio = max(0.0, min(1.0, ratio))

        if rule.kind == "top_bottom":
            count = (
                max(1, round(len(numbers) * rule.rank / 100))
                if rule.percent
                else max(1, rule.rank)
            )
            ordered = sorted(numbers, reverse=rule.above)
            threshold = ordered[min(count, len(ordered)) - 1]
            matched = numeric_value >= threshold if rule.above else numeric_value <= threshold
            return matched, None, None, None
        if rule.kind == "above_average":
            average = sum(numbers) / len(numbers)
            matched = numeric_value > average if rule.above else numeric_value < average
            return matched, None, None, None
        if rule.kind == "duplicate":
            return numbers.count(numeric_value) > 1, None, None, None
        if rule.kind == "color_scale":
            return True, _scale_color(ratio, rule.colors), None, None
        if rule.kind == "data_bar":
            return True, None, ratio, None
        if rule.kind == "icon_set":
            selected_icon = "down" if ratio <= 1 / 3 else "sideways" if ratio <= 2 / 3 else "up"
            return True, None, None, selected_icon
        return False, None, None, None


def _numeric_values(sheet: Sheet, target: RangeReference) -> list[float]:
    return [
        float(cell.display_value)
        for (row, column), cell in sheet.iter_populated()
        if target.contains(row, column)
        and isinstance(cell.display_value, (int, float))
        and not isinstance(cell.display_value, bool)
    ]


def _cell_value_matches(
    value: Any,
    operator: str,
    operands: tuple[Any, ...],
) -> bool:
    if not operands:
        return False
    first = operands[0]
    if operator == "equal":
        return value == first
    if operator == "not_equal":
        return value != first
    try:
        if operator == "greater_than":
            return value > first
        if operator == "greater_equal":
            return value >= first
        if operator == "less_than":
            return value < first
        if operator == "less_equal":
            return value <= first
        if operator == "between" and len(operands) >= 2:
            return first <= value <= operands[1]
        if operator == "not_between" and len(operands) >= 2:
            return not first <= value <= operands[1]
    except TypeError:
        return False
    return False


def _scale_color(ratio: float, colors: tuple[str, ...]) -> str:
    selected = colors if len(colors) >= 2 else ("#ffffff", "#000000")
    if len(selected) >= 3:
        if ratio <= 0.5:
            return _interpolate_color(selected[0], selected[1], ratio * 2)
        return _interpolate_color(selected[1], selected[2], (ratio - 0.5) * 2)
    return _interpolate_color(selected[0], selected[1], ratio)


def _interpolate_color(start: str, end: str, ratio: float) -> str:
    start_rgb = tuple(int(start[index : index + 2], 16) for index in (1, 3, 5))
    end_rgb = tuple(int(end[index : index + 2], 16) for index in (1, 3, 5))
    mixed = tuple(
        round(start_component + (end_component - start_component) * ratio)
        for start_component, end_component in zip(start_rgb, end_rgb)
    )
    return "#" + "".join(f"{component:02x}" for component in mixed)
