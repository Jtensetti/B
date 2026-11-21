"""Small sample Python-source kernels for B's experimental adoption mechanism."""

# This module is NEVER imported when the B compiler adopts a leaf function.
# The safe arithmetic below is consumed as syntax and checked as native B.


def square(x: float) -> float:
    """Square a float; portable to B's typed arithmetic subset."""
    return x * x


def forward(x: int) -> int:
    return x + 1


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


def positive(x: int) -> bool:
    return x > 0


def ratio(x: float, divisor: float) -> float:
    return x / divisor


def unsafe_global(x: int) -> int:
    return x + HIDDEN_NUMBER  # Not adoptable: unknown global.


def unsafe_call(x: float) -> float:
    return print(x)  # Not adoptable: external effect.


def unsafe_default(x: int = 4) -> int:
    return x + 1  # Not adoptable: defaults change calling convention.


def unsafe_statement(x: int) -> int:
    y = x + 1
    return y  # Not adoptable: not an expression-only leaf.
