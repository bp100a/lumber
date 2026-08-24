"""Parse and format fractional inch dimensions."""

from __future__ import annotations

import re
from fractions import Fraction

_MIXED = re.compile(
    r"^\s*(?:(?P<whole>-?\d+)\s+)?(?P<frac>\d+\s*/\s*\d+|-?\d+\.\d+|-?\d+)\s*$"
)


def parse_inches(value: str | Fraction | int | float) -> Fraction:
    """Parse a dimension string like ``4 3/4`` or ``1 11/16`` into a Fraction."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        return Fraction(value).limit_denominator(64)

    text = str(value).strip().replace('"', "").replace("'", "")
    if not text:
        raise ValueError("empty dimension")

    if "/" in text or " " in text:
        match = _MIXED.match(text)
        if not match:
            raise ValueError(f"invalid dimension: {value!r}")
        whole = int(match.group("whole") or 0)
        frac_part = match.group("frac").replace(" ", "")
        if "/" in frac_part:
            num, den = frac_part.split("/", 1)
            fraction = Fraction(int(num), int(den))
        else:
            fraction = Fraction(frac_part).limit_denominator(64)
        return Fraction(whole) + fraction

    if "." in text:
        return Fraction(text).limit_denominator(64)

    return Fraction(int(text))


def format_inches(value: Fraction, denominator: int = 16) -> str:
    """Format a Fraction as a mixed number in inches (e.g. ``4 3/4``)."""
    if value.denominator == 1:
        return str(value.numerator)

    limited = Fraction(value.numerator, value.denominator).limit_denominator(denominator)
    whole = limited.numerator // limited.denominator
    remainder = abs(limited.numerator % limited.denominator)
    sign = "-" if limited < 0 and whole == 0 else ""
    if whole != 0 and remainder == 0:
        return f"{limited.numerator // limited.denominator}"
    if whole == 0:
        return f"{sign}{remainder}/{limited.denominator}"
    if remainder == 0:
        return str(whole)
    return f"{whole} {remainder}/{limited.denominator}"
