from fractions import Fraction
from pathlib import Path

from lumber.dimensions import format_inches
from lumber.io import load_problem
from lumber.models import CutPiece, CutPlan, Placement, StockPiece
from lumber.packer import optimize
from lumber.pdf import write_pdf
from lumber.report import unused_stock_line

from tests.examples import CRAFTSMANBLOG, LIVE


def test_write_pdf_is_valid_and_contains_labels(tmp_path: Path) -> None:
    plan = optimize(load_problem(CRAFTSMANBLOG))
    out = tmp_path / "storm_window.pdf"
    write_pdf(plan, out)
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert b"board-a" in data
    assert b"INSUFFICIENT STOCK" in data
    assert b"Lumber cut plan" in data
    assert b"cross-cut first" in data
    assert b"gang-rip" in data


def test_write_pdf_includes_fixture_part_label(tmp_path: Path) -> None:
    plan = CutPlan(
        kerf=Fraction(1, 8),
        stock=[StockPiece(id="board-1", width=Fraction(2), length=Fraction(20))],
        placements=[
            Placement(
                stock_id="board-1",
                cut=CutPiece(
                    name="Stiles",
                    width=Fraction(2),
                    length=Fraction(10),
                    instance_id="Stiles #1",
                ),
                rip_offset=Fraction(0),
                length_offset=Fraction(0),
            )
        ],
    )
    out = tmp_path / "one.pdf"
    write_pdf(plan, out)
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert b"Stiles #1" in data
    assert b"board-1" in data


def test_unused_stock_line_includes_face_dimensions() -> None:
    plan = CutPlan(
        stock=[
            StockPiece(id="board-a", width=Fraction(7), length=Fraction(144)),
            StockPiece(
                id="board-f",
                width=Fraction(19, 4),
                length=Fraction(195, 2),
            ),
        ],
        placements=[
            Placement(
                stock_id="board-a",
                cut=CutPiece(
                    name="Stiles",
                    width=Fraction(2),
                    length=Fraction(10),
                    instance_id="Stiles #1",
                ),
                rip_offset=Fraction(0),
                length_offset=Fraction(0),
            )
        ],
    )
    assert unused_stock_line(plan) == (
        'Unused stock: board-f (97 1/2" × 4 3/4" × 1")'
    )


def test_write_pdf_reports_windows_completed_from_stock(tmp_path: Path) -> None:
    plan = optimize(load_problem(LIVE))
    out = tmp_path / "live.pdf"
    write_pdf(plan, out)
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert b"Windows completed: 7 of 7" in data
    assert b"Unused stock:" in data
    unused = unused_stock_line(plan)
    assert unused is not None
    assert "(" in unused
    leftover = [s for s in plan.stock if s.id not in {p.stock_id for p in plan.placements}]
    assert leftover
    assert leftover[0].id.encode() in data
    assert f'{format_inches(leftover[0].width)}"'.encode() in data
    assert f'{format_inches(leftover[0].length)}"'.encode() in data
    assert b"Board feet used:" in data
    used_bf = f"{plan.used_board_feet:.2f}".encode()
    waste_bf = f"{plan.waste_board_feet:.2f}".encode()
    assert used_bf in data
    assert waste_bf in data
    assert b" bf" in data
    assert b"sq in" not in data
    assert b"Cuts by window" in data
    assert b"dining-west" in data
    assert b"dining-side" in data
    assert b"Height" in data
    assert b"Width" in data
    assert b"Stiles" in data
    assert b"Meeting rail" in data
    assert b'62 1/2"' in data
    assert b'20 7/8"' in data
    assert b'62 1/4"' in data
    assert b'16 3/8"' in data
    assert b'2 1/8"' in data
    assert b'2 3/16"' in data
    assert b'35 1/2"' in data
    assert b"Stock used" in data
    assert b"board-a" in data
    assert b'7 3/8"' in data
    assert b"Assembled frames" in data
    assert b"Upper glass" in data
    assert b"Lower glass" in data
    assert b'16 3/4"' in data
    assert b'28 1/2"' in data
    assert b'27 5/8"' in data
    assert b"Rabbet" in data
    assert b"1/16" in data


def test_write_pdf_omits_window_tables_for_handwritten_cuts(tmp_path: Path) -> None:
    plan = optimize(load_problem(CRAFTSMANBLOG))
    out = tmp_path / "handwritten.pdf"
    write_pdf(plan, out)
    data = out.read_bytes()
    assert b"Cuts by window" not in data
    assert b"Height" not in data
    assert b"Assembled frames" not in data
    assert b"Stock used" in data
