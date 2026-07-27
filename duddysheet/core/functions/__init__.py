"""Formula function metadata and registration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

FunctionImplementation = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class FunctionSpec:
    """Registered formula function behavior and help metadata."""

    name: str
    implementation: FunctionImplementation
    min_args: int
    max_args: int
    volatile: bool
    argument_spec: str
    description: str
    lazy: bool = False


FUNCTION_REGISTRY: dict[str, FunctionSpec] = {}


def register(
    name: str,
    *,
    min_args: int = 0,
    max_args: int = 255,
    volatile: bool = False,
    argument_spec: str = "",
    lazy: bool = False,
) -> Callable[[FunctionImplementation], FunctionImplementation]:
    """Register a formula function and retain its help metadata."""

    def decorator(function: FunctionImplementation) -> FunctionImplementation:
        normalized_name = name.upper()
        description = (function.__doc__ or "").strip()
        if not description:
            raise ValueError(f"Function {normalized_name} requires a docstring")
        if normalized_name in FUNCTION_REGISTRY:
            raise ValueError(f"Function already registered: {normalized_name}")
        if min_args < 0 or max_args < min_args:
            raise ValueError(f"Invalid argument bounds for {normalized_name}")
        FUNCTION_REGISTRY[normalized_name] = FunctionSpec(
            name=normalized_name,
            implementation=function,
            min_args=min_args,
            max_args=max_args,
            volatile=volatile,
            argument_spec=argument_spec,
            description=description,
            lazy=lazy,
        )
        return function

    return decorator


# Import each family after registry construction so decorators populate one
# authoritative function table.
from duddysheet.core.functions import (  # noqa: E402,F401
    datetime_fn,
    finance_fn,
    info_fn,
    logical_fn,
    lookup_fn,
    math_fn,
    stats_fn,
    text_fn,
)
