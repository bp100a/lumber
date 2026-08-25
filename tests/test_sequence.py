from fractions import Fraction

from lumber.diagram import board_regions
from lumber.dimensions import parse_inches
from lumber.io import load_problem
from lumber.models import CutMode, CutPiece, Placement, StockPiece
from lumber.packer import optimize
from lumber.report import format_text
from lumber.sequence import (
    board_instructions,
    is_crosscut_first,
    iter_strip_runs,
    shared_length,
)

from tests.examples import CRAFTSMANBLOG, LIVE


def _stile(instance: str, rip: Fraction = Fraction(0)) -> Placement:
    return Placement(
        stock_id="board-c",
        cut=CutPiece(
            name="Stiles",
            width=Fraction(27, 16),
            length=Fraction(249, 4),
            instance_id=instance,
        ),
        rip_offset=rip,
        length_offset=Fraction(0),
    )


def test_shared_length_detects_equal_and_mixed() -> None:
    same = [_stile("Stiles #1"), _stile("Stiles #2", Fraction(27, 16) + Fraction(1, 8))]
    assert shared_length(same) == Fraction(249, 4)
    assert is_crosscut_first(same)
    mixed = same + [
        Placement(
            stock_id="board-c",
            cut=CutPiece(
                name="Top Rail",
                width=Fraction(27, 16),
                length=Fraction(69, 4),
                instance_id="Top Rail #1",
            ),
            rip_offset=Fraction(0),
            length_offset=Fraction(249, 4) + Fraction(1, 8),
        )
    ]
    assert shared_length(mixed) is None
    assert not is_crosscut_first(mixed)


def test_crosscut_first_instructions_and_full_width_offcut() -> None:
    stock = StockPiece(id="board-c", width=Fraction(11, 2), length=Fraction(195, 2))
    kerf = Fraction(1, 8)
    placements = [
        _stile("Stiles #4"),
        _stile("Stiles #5", Fraction(27, 16) + kerf),
        _stile("Stiles #6", 2 * (Fraction(27, 16) + kerf)),
    ]
    steps = board_instructions(placements, stock, kerf)
    texts = [line for _indent, line in steps]
    assert any("cross-cut first" in line for line in texts)
    assert any(line.startswith("Cross-cut @") for line in texts)
    assert any(line.startswith("Rip @") for line in texts)
    assert any("Offcut:" in line and "full width" in line for line in texts)
    assert not any(line.startswith("Rip @") and "strip" in line for line in texts)

    regions = board_regions(stock, placements, kerf)
    length_offcuts = [
        r
        for r in regions
        if r.kind == "waste" and r.length_offset >= Fraction(249, 4)
    ]
    assert length_offcuts
    assert all(r.width == stock.width for r in length_offcuts)


def test_craftsmanblog_board_c_is_crosscut_first_board_a_is_rip_first() -> None:
    plan = optimize(load_problem(CRAFTSMANBLOG))
    report = format_text(plan)
    board_c = report.split("board-c")[1].split("Placed:")[0]
    board_a = report.split("board-a")[1].split("Board:")[0]
    assert "cross-cut first" in board_c
    assert "Offcut:" in board_c
    assert "full width" in board_c
    assert "cross-cut first" not in board_a
    assert "Rip @" in board_a
    assert "gang-rip" not in board_a


def test_craftsmanblog_board_b_gangs_stiles_then_splits() -> None:
    plan = optimize(load_problem(CRAFTSMANBLOG))
    report = format_text(plan)
    board_b = report.split("board-b")[1].split("Board:")[0]
    assert "gang-rip Stiles #2 and #3" in board_b
    assert 'Rip @ 0" -> 3 1/2" pair strip' in board_b
    assert 'Cross-cut @ 0" + 62 1/4" -> pair blank' in board_b
    assert 'Rip @ 0" -> 1 11/16" -> Stiles #2' in board_b
    assert 'Rip @ 1 13/16" -> 1 11/16" -> Stiles #3' in board_b
    assert 'Offcut: 35 1/8" x 3 1/2"' in board_b
    assert "full width" not in board_b
    assert 'Rip @ 3 5/8" -> 1 1/4" strip' in board_b
    assert "cross-cut first" not in board_b


def test_nonadjacent_same_length_strips_are_not_ganged() -> None:
    kerf = Fraction(1, 8)
    stile_w = Fraction(27, 16)
    stock = StockPiece(id="board-x", width=Fraction(6), length=Fraction(195, 2))
    rail_w = Fraction(5, 4)
    placements = [
        Placement(
            stock_id="board-x",
            cut=CutPiece(
                name="Stiles",
                width=stile_w,
                length=Fraction(249, 4),
                instance_id="Stiles #1",
            ),
            rip_offset=Fraction(0),
            length_offset=Fraction(0),
        ),
        Placement(
            stock_id="board-x",
            cut=CutPiece(
                name="Meeting rail",
                width=rail_w,
                length=Fraction(153, 4),
                instance_id="Meeting rail #1",
            ),
            rip_offset=stile_w + kerf,
            length_offset=Fraction(0),
        ),
        Placement(
            stock_id="board-x",
            cut=CutPiece(
                name="Stiles",
                width=stile_w,
                length=Fraction(249, 4),
                instance_id="Stiles #2",
            ),
            rip_offset=stile_w + kerf + rail_w + kerf,
            length_offset=Fraction(0),
        ),
    ]
    runs = iter_strip_runs(placements, kerf)
    assert all(len(run) == 1 for run in runs)
    steps = [line for _indent, line in board_instructions(placements, stock, kerf)]
    assert not any("gang-rip" in line for line in steps)


def test_live_board_a_is_through_crosscut() -> None:
    plan = optimize(load_problem(LIVE))
    layout = plan.board_layouts["board-a"]
    assert layout.mode is CutMode.THROUGH_CROSSCUT
    assert layout.station is not None

    report = format_text(plan)
    board_a = report.split("board-a")[1].split("Board:")[0]
    assert "through cross-cut" in board_a
    assert "shorten long rips" in board_a
    assert "Leftover blank:" in board_a
    assert '19 1/4"' in board_a

    stock = next(s for s in plan.stock if s.id == "board-a")
    placed = [p for p in plan.placements if p.stock_id == "board-a"]
    remnant_start = layout.station.remnant_start
    remnant_parts = [p for p in placed if p.length_offset >= remnant_start]
    assert remnant_parts
    regions = board_regions(stock, placed, plan.kerf, layout=layout)
    through_kerfs = [
        r
        for r in regions
        if r.kind == "kerf" and r.width == stock.width and r.length == plan.kerf
    ]
    assert {r.length_offset for r in through_kerfs} >= {
        layout.station.station,
        remnant_start - plan.kerf,
    }


def test_live_ten_foot_boards_are_through_crosscut_not_full_rips() -> None:
    plan = optimize(load_problem(LIVE))
    report = format_text(plan)
    for stock_id in ("board-d", "board-e"):
        layout = plan.board_layouts[stock_id]
        assert layout.mode is CutMode.THROUGH_CROSSCUT
        assert layout.station is not None
        assert layout.station.count == 1
        assert layout.station.remnant_length == parse_inches("57 5/8")
        chunk = report.split(stock_id)[1].split("Board:")[0]
        if "Placed:" in chunk:
            chunk = chunk.split("Placed:")[0]
        assert "through cross-cut" in chunk
        assert 'Leftover blank: 57 5/8"' in chunk
        placed = [p for p in plan.placements if p.stock_id == stock_id]
        remnant_parts = [
            p for p in placed if p.length_offset >= layout.station.remnant_start
        ]
        assert remnant_parts
        assert all(p.cut.length <= layout.station.remnant_length for p in remnant_parts)


def test_live_skips_the_wide_ten_foot_board() -> None:
    plan = optimize(load_problem(LIVE))
    used = {p.stock_id for p in plan.placements}
    assert "board-c" not in used
    assert plan.unplaced == []
