from fractions import Fraction

from lumber.diagram import board_regions, board_svg
from lumber.dimensions import format_inches
from lumber.io import load_problem
from lumber.models import CutPiece, CutPlan, Placement, StockPiece
from lumber.packer import optimize
from lumber.report import format_markdown

from tests.examples import CRAFTSMANBLOG


def test_board_regions_match_placements_and_stay_in_bounds() -> None:
    stock = StockPiece(id="board-1", width=Fraction(11, 2), length=Fraction(195, 2))
    placements = [
        Placement(
            stock_id="board-1",
            cut=CutPiece(
                name="Stiles",
                width=Fraction(27, 16),
                length=Fraction(249, 4),
                instance_id="Stiles #1",
            ),
            rip_offset=Fraction(0),
            length_offset=Fraction(0),
        ),
        Placement(
            stock_id="board-1",
            cut=CutPiece(
                name="Top Rail",
                width=Fraction(27, 16),
                length=Fraction(69, 4),
                instance_id="Top Rail #1",
            ),
            rip_offset=Fraction(0),
            length_offset=Fraction(249, 4) + Fraction(1, 8),
        ),
    ]
    regions = board_regions(stock, placements, kerf=Fraction(1, 8))
    pieces = [r for r in regions if r.kind == "piece"]
    assert {(r.label, r.length_offset, r.rip_offset, r.length, r.width) for r in pieces} == {
        ("Stiles #1", Fraction(0), Fraction(0), Fraction(249, 4), Fraction(27, 16)),
        (
            "Top Rail #1",
            Fraction(249, 4) + Fraction(1, 8),
            Fraction(0),
            Fraction(69, 4),
            Fraction(27, 16),
        ),
    }
    for region in regions:
        assert region.length_offset >= 0
        assert region.rip_offset >= 0
        assert region.length_offset + region.length <= stock.length
        assert region.rip_offset + region.width <= stock.width


def test_board_svg_marks_piece_coordinates() -> None:
    stock = StockPiece(id="board-1", width=Fraction(2), length=Fraction(20))
    placement = Placement(
        stock_id="board-1",
        cut=CutPiece(name="A", width=Fraction(2), length=Fraction(10), instance_id="A #1"),
        rip_offset=Fraction(0),
        length_offset=Fraction(0),
    )
    svg = board_svg(stock, [placement], kerf=Fraction(1, 8))
    assert 'data-kind="piece"' in svg
    assert 'data-label="A #1"' in svg
    assert f'data-length="{format_inches(Fraction(10))}"' in svg
    assert "<svg" in svg


def test_markdown_report_has_headings_diagrams_and_unplaced() -> None:
    plan = optimize(load_problem(CRAFTSMANBLOG))
    markdown = format_markdown(plan)
    assert markdown.startswith("# Lumber cut plan\n")
    used = {p.stock_id for p in plan.placements}
    for stock_id in used:
        assert f"## {stock_id}" in markdown
    unused = {s.id for s in plan.stock} - used
    for stock_id in unused:
        assert f"## {stock_id}" not in markdown
    for stock_id in used:
        assert f"![Cut diagram for {stock_id}]" in markdown
    assert "<svg" not in markdown
    assert "INSUFFICIENT STOCK" in markdown
    assert "## Unplaced" in markdown
    assert "38 1/4" in markdown


def test_craftsmanblog_board_b_offcut_is_combined_width() -> None:
    plan = optimize(load_problem(CRAFTSMANBLOG))
    stock = next(s for s in plan.stock if s.id == "board-b")
    placements = [p for p in plan.placements if p.stock_id == "board-b"]
    regions = board_regions(stock, placements, plan.kerf)
    stile_end = Fraction(249, 4)
    combined = Fraction(7, 2)
    after_stiles = [
        r
        for r in regions
        if r.kind == "waste" and r.length_offset >= stile_end and r.width == combined
    ]
    assert after_stiles
    assert all(r.width == combined for r in after_stiles)
    skinny = [
        r
        for r in regions
        if r.kind == "waste"
        and r.length_offset >= stile_end
        and r.width == Fraction(27, 16)
    ]
    assert skinny == []
    between = [
        r
        for r in regions
        if r.kind == "kerf"
        and r.rip_offset == Fraction(27, 16)
        and r.length == stock.length
    ]
    assert between == []


def test_markdown_unplaced_only() -> None:
    plan = CutPlan(
        kerf=Fraction(1, 8),
        unplaced=[
            CutPiece(
                name="Stiles",
                width=Fraction(27, 16),
                length=Fraction(249, 4),
                instance_id="Stiles #7",
            )
        ],
    )
    markdown = format_markdown(plan)
    assert "# Lumber cut plan" in markdown
    assert "INSUFFICIENT STOCK" in markdown
    assert "Stiles #7" in markdown
    assert "<svg" not in markdown
