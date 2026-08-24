from fractions import Fraction

import pytest

from lumber.dimensions import format_inches, parse_inches


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4 3/4", Fraction(19, 4)),
        ("1 11/16", Fraction(27, 16)),
        ("97 1/2", Fraction(195, 2)),
        ("17 1/4", Fraction(69, 4)),
        ("2 9/16", Fraction(41, 16)),
        ("1/8", Fraction(1, 8)),
        ("1", Fraction(1)),
    ],
)
def test_parse_inches(raw: str, expected: Fraction) -> None:
    assert parse_inches(raw) == expected


def test_format_inches_round_trip() -> None:
    for raw in ("4 3/4", "1 11/16", "62 1/4", "2 9/16"):
        assert parse_inches(format_inches(parse_inches(raw))) == parse_inches(raw)
