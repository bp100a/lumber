from lumber.validate import expand_cuts, expand_stock, validate_problem
from lumber.models import CutPiece, Problem, StockPiece
from lumber.dimensions import parse_inches


def test_validate_rejects_cut_wider_than_stock() -> None:
    problem = Problem(
        stock=[StockPiece(id="a", width=parse_inches("2"), length=parse_inches("10"))],
        cuts=[CutPiece(name="wide", width=parse_inches("3"), length=parse_inches("8"))],
    )
    errors = validate_problem(problem)
    assert any("width" in e for e in errors)


def test_expand_quantities() -> None:
    cuts = expand_cuts(
        [CutPiece(name="Stiles", width=parse_inches("1 11/16"), length=parse_inches("62 1/4"), quantity=2)]
    )
    assert [c.instance_id for c in cuts] == ["Stiles #1", "Stiles #2"]

    stock = expand_stock(
        [StockPiece(id="board", width=parse_inches("5 1/2"), length=parse_inches("97 1/2"), quantity=2)]
    )
    assert [s.id for s in stock] == ["board-1", "board-2"]
