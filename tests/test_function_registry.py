from __future__ import annotations

import pytest

from duddysheet.core.functions import FUNCTION_REGISTRY, register


def test_register_retains_function_help_and_execution_metadata() -> None:
    name = "__TEST_REGISTERED"
    FUNCTION_REGISTRY.pop(name, None)

    @register(
        name,
        min_args=1,
        max_args=2,
        volatile=True,
        argument_spec="value, [value]",
        lazy=True,
    )
    def sample_function(context: object, *values: object) -> int:
        """Return the number of supplied values."""
        return len(values)

    specification = FUNCTION_REGISTRY.pop(name)
    assert specification.name == name
    assert specification.implementation is sample_function
    assert specification.min_args == 1
    assert specification.max_args == 2
    assert specification.volatile
    assert specification.lazy
    assert specification.argument_spec == "value, [value]"
    assert specification.description == "Return the number of supplied values."


def test_register_rejects_missing_docstring() -> None:
    decorator = register("__TEST_NO_DOC")

    with pytest.raises(ValueError, match="docstring"):
        decorator(lambda: None)


def test_register_rejects_duplicate_names_case_insensitively() -> None:
    name = "__TEST_DUPLICATE"
    FUNCTION_REGISTRY.pop(name, None)

    @register(name)
    def first() -> None:
        """First registration."""

    try:
        with pytest.raises(ValueError, match="already"):

            @register(name.lower())
            def second() -> None:
                """Second registration."""
    finally:
        FUNCTION_REGISTRY.pop(name, None)


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [(-1, 1), (2, 1)],
)
def test_register_rejects_invalid_argument_bounds(
    minimum: int,
    maximum: int,
) -> None:
    decorator = register(
        f"__TEST_BOUNDS_{minimum}_{maximum}",
        min_args=minimum,
        max_args=maximum,
    )

    with pytest.raises(ValueError, match="bounds"):

        @decorator
        def invalid() -> None:
            """Invalid bounds."""
