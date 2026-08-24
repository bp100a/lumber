from fractions import Fraction
from pathlib import Path

from lumber.io import load_problem
from lumber.models import CutPiece, CutPlan, Placement, StockPiece
from lumber.packer import optimize
from lumber.pdf import write_pdf

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


def test_write_pdf_reports_windows_completed_from_stock(tmp_path: Path) -> None:
    plan = optimize(load_problem(LIVE))
    out = tmp_path / "live.pdf"
    write_pdf(plan, out)
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert b"Windows completed: 6 of 6" in data
    assert b"board-c" in data
    assert b"Unused stock:" in data
