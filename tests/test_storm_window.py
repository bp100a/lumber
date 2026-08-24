from fractions import Fraction

from lumber.io import load_problem
from lumber.models import CutPiece, CutPlan
from lumber.packer import optimize
from lumber.report import format_text
from lumber.validate import validate_problem

from tests.examples import CRAFTSMANBLOG


def test_storm_window_places_all_except_large_top_rail() -> None:
    """Three windows need 15 pieces. Under rip-then-crosscut, 14 fit.

    Six 62 1/4" stiles cannot share a strip with the 38 1/4" top rail, so that
    top rail needs its own 1 11/16" strip. Reserving width for the 2 9/16"
    bottom rails leaves room for only six 1 11/16" strips — the large top rail
    is reported as unplaced.
    """
    problem = load_problem(CRAFTSMANBLOG)
    assert validate_problem(problem) == []

    plan = optimize(problem)
    assert len(plan.placements) == 14
    assert len(plan.unplaced) == 1
    unplaced = plan.unplaced[0]
    assert unplaced.name == "Top Rail"
    assert unplaced.length == Fraction(153, 4)  # 38 1/4
    assert unplaced.width == Fraction(27, 16)  # 1 11/16

    stock = {s.id: s for s in plan.stock}
    for p in plan.placements:
        board = stock[p.stock_id]
        assert p.rip_offset + p.cut.width <= board.width
        assert p.length_offset + p.cut.length <= board.length

    report = format_text(plan)
    assert "INSUFFICIENT STOCK" in report
    assert "38 1/4" in report


def test_insufficient_stock_reports_unplaced() -> None:
    plan = CutPlan(
        kerf=Fraction(1, 8),
        unplaced=[
            CutPiece(
                name="Stiles",
                width=Fraction(27, 16),
                length=Fraction(249, 4),
                quantity=1,
                instance_id="Stiles #7",
            )
        ],
    )
    report = format_text(plan)
    assert "INSUFFICIENT STOCK" in report
    assert "Stiles #7" in report
