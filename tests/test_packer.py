from collections import defaultdict
from fractions import Fraction

from lumber.dimensions import parse_inches
from lumber.models import CutPiece, Problem, StockPiece
from lumber.packer import optimize
from lumber.report import format_text


def _problem(
    stock: list[tuple[str, str, str]],
    cuts: list[tuple[str, str, str, int]],
    kerf: str = "1/8",
) -> Problem:
    return Problem(
        stock=[
            StockPiece(id=sid, width=parse_inches(w), length=parse_inches(length), quantity=1)
            for sid, w, length in stock
        ],
        cuts=[
            CutPiece(name=name, width=parse_inches(w), length=parse_inches(length), quantity=qty)
            for name, length, w, qty in cuts
        ],
        kerf=parse_inches(kerf),
    )


def test_two_end_to_end_cuts_include_kerf() -> None:
    problem = _problem(
        stock=[("board-1", "2", "20 5/8")],
        cuts=[("A", "10", "2", 2)],
        kerf="1/8",
    )
    plan = optimize(problem)
    assert plan.unplaced == []
    assert len(plan.placements) == 2
    offsets = sorted(p.length_offset for p in plan.placements)
    assert offsets == [Fraction(0), Fraction(10) + Fraction(1, 8)]


def test_kerf_can_make_second_cut_unplaced() -> None:
    problem = _problem(
        stock=[("board-1", "2", "20")],
        cuts=[("A", "10", "2", 2)],
        kerf="1/8",
    )
    plan = optimize(problem)
    assert len(plan.placements) == 1
    assert len(plan.unplaced) == 1


def _assert_no_overlap(plan) -> None:
    by_board: dict[str, list[tuple[Fraction, Fraction, Fraction, Fraction]]] = defaultdict(list)
    stock = {s.id: s for s in plan.stock}
    for p in plan.placements:
        board = stock[p.stock_id]
        assert p.rip_offset >= 0
        assert p.length_offset >= 0
        assert p.rip_offset + p.cut.width <= board.width
        assert p.length_offset + p.cut.length <= board.length
        by_board[p.stock_id].append(
            (p.rip_offset, p.length_offset, p.cut.width, p.cut.length)
        )
    for rects in by_board.values():
        for i, (ax, ay, aw, al) in enumerate(rects):
            for bx, by, bw, bl in rects[i + 1 :]:
                x_overlap = ax < bx + bw and bx < ax + aw
                y_overlap = ay < by + bl and by < ay + al
                assert not (x_overlap and y_overlap)


def test_placements_do_not_overlap() -> None:
    problem = _problem(
        stock=[("board-1", "5 1/2", "97 1/2")],
        cuts=[
            ("Stiles", "62 1/4", "1 11/16", 1),
            ("Top Rail", "17 1/4", "1 11/16", 1),
            ("Bottom rail", "17 1/4", "2 9/16", 1),
        ],
    )
    plan = optimize(problem)
    assert plan.unplaced == []
    _assert_no_overlap(plan)


def test_two_small_windows_place_all_ten() -> None:
    problem = _problem(
        stock=[
            ("board-a", "4 3/4", "97 1/2"),
            ("board-b", "4 7/8", "97 1/2"),
            ("board-c", "5 1/2", "97 1/2"),
        ],
        cuts=[
            ("Stiles", "62 1/4", "1 11/16", 4),
            ("Top Rail", "17 1/4", "1 11/16", 2),
            ("Meeting rail", "17 1/4", "1", 2),
            ("Bottom rail", "17 1/4", "2 9/16", 2),
        ],
    )
    plan = optimize(problem)
    assert len(plan.placements) == 10
    assert plan.unplaced == []
    _assert_no_overlap(plan)


def test_wider_kerf_changes_layout() -> None:
    stock = [("board-1", "5 1/2", "62 1/4")]
    cuts = [("Stiles", "62 1/4", "1 11/16", 3)]
    eighth = optimize(_problem(stock, cuts, kerf="1/8"))
    quarter = optimize(_problem(stock, cuts, kerf="1/4"))
    assert len(eighth.placements) == 3
    assert eighth.unplaced == []
    assert len(quarter.placements) == 2
    assert len(quarter.unplaced) == 1


def test_rip_strips_consume_kerf_across_width() -> None:
    # 1 11/16 + kerf + 1 11/16 = 3 1/2, so a 3 1/2 board fits two stile strips.
    problem = _problem(
        stock=[("board-1", "3 1/2", "62 1/4")],
        cuts=[("Stiles", "62 1/4", "1 11/16", 2)],
        kerf="1/8",
    )
    plan = optimize(problem)
    assert plan.unplaced == []
    offsets = sorted({p.rip_offset for p in plan.placements})
    assert offsets == [Fraction(0), Fraction(27, 16) + Fraction(1, 8)]


def test_insufficient_stock_message() -> None:
    problem = _problem(
        stock=[("short", "2", "10")],
        cuts=[("Stiles", "62 1/4", "1 11/16", 1)],
    )
    plan = optimize(problem)
    assert plan.unplaced
    assert "INSUFFICIENT STOCK" in format_text(plan)


def test_shorter_boards_take_stiles_that_cannot_pair_on_longest() -> None:
    """Two 62 1/4" stiles fit a 12' strip; they do not fit a 10' strip as a pair."""
    problem = _problem(
        stock=[
            ("long", "2 1/2", "144"),
            ("mid", "5 1/8", "120"),
        ],
        cuts=[("Stiles", "62 1/4", "2 1/2", 4)],
    )
    plan = optimize(problem)
    assert plan.unplaced == []
    assert {p.stock_id for p in plan.placements} == {"long", "mid"}
    assert sum(1 for p in plan.placements if p.stock_id == "long") == 2
    assert sum(1 for p in plan.placements if p.stock_id == "mid") == 2
    _assert_no_overlap(plan)


def test_station_plan_twelve_foot_and_ten_foot_remnants() -> None:
    from lumber.layout import station_plan

    twelve = station_plan(Fraction(144), Fraction(249, 4), Fraction(1, 8))
    assert twelve is not None
    assert twelve.count == 2
    assert twelve.remnant_start == Fraction(499, 4)  # 124 3/4
    assert twelve.remnant_length == Fraction(77, 4)  # 19 1/4

    ten = station_plan(Fraction(120), Fraction(249, 4), Fraction(1, 8))
    assert ten is not None
    assert ten.count == 1
    assert ten.remnant_start == Fraction(499, 8)  # 62 3/8
    assert ten.remnant_length == Fraction(461, 8)  # 57 5/8

    assert station_plan(Fraction(195, 2), Fraction(249, 4), Fraction(1, 8)) is None
    assert station_plan(Fraction(97), Fraction(249, 4), Fraction(1, 8)) is None


def test_waste_percent_ignores_unused_boards() -> None:
    from lumber.io import load_problem

    from tests.examples import LIVE

    plan = optimize(load_problem(LIVE))
    unused_ids = {s.id for s in plan.stock} - {p.stock_id for p in plan.placements}
    assert unused_ids
    assert plan.used_stock_area < plan.stock_area
    assert plan.waste_area == plan.used_stock_area - plan.placed_area
    all_stock_waste = float((plan.stock_area - plan.placed_area) / plan.stock_area * 100)
    assert plan.waste_percent < all_stock_waste
