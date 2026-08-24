"""Validate problem inputs before optimization."""

from __future__ import annotations

from lumber.models import CutPiece, Problem, StockPiece


def expand_cuts(cuts: list[CutPiece]) -> list[CutPiece]:
    """Expand quantity > 1 into individual cut instances."""
    expanded: list[CutPiece] = []
    counters: dict[str, int] = {}
    for cut in cuts:
        for _ in range(cut.quantity):
            counters[cut.name] = counters.get(cut.name, 0) + 1
            expanded.append(
                CutPiece(
                    name=cut.name,
                    width=cut.width,
                    length=cut.length,
                    quantity=1,
                    instance_id=f"{cut.name} #{counters[cut.name]}",
                    window_id=cut.window_id,
                )
            )
    return expanded


def expand_stock(stock: list[StockPiece]) -> list[StockPiece]:
    """Expand stock quantity into individual boards."""
    expanded: list[StockPiece] = []
    for piece in stock:
        for index in range(piece.quantity):
            suffix = f"-{index + 1}" if piece.quantity > 1 else ""
            expanded.append(
                StockPiece(
                    id=f"{piece.id}{suffix}",
                    width=piece.width,
                    length=piece.length,
                    quantity=1,
                )
            )
    return expanded


def validate_problem(problem: Problem) -> list[str]:
    """Return a list of validation errors (empty if valid)."""
    errors: list[str] = []
    if not problem.stock:
        errors.append("no stock lumber defined")
    if not problem.cuts:
        errors.append("no cuts defined")
    if problem.kerf < 0:
        errors.append("kerf must be non-negative")

    for piece in problem.stock:
        if piece.width <= 0 or piece.length <= 0:
            errors.append(f"stock {piece.id!r} must have positive width and length")
        if piece.quantity <= 0:
            errors.append(f"stock {piece.id!r} quantity must be positive")

    for cut in problem.cuts:
        if cut.width <= 0 or cut.length <= 0:
            errors.append(f"cut {cut.name!r} must have positive width and length")
        if cut.quantity <= 0:
            errors.append(f"cut {cut.name!r} quantity must be positive")

    max_stock_width = max((s.width for s in problem.stock), default=0)
    max_stock_length = max((s.length for s in problem.stock), default=0)
    for cut in problem.cuts:
        if cut.width > max_stock_width:
            errors.append(
                f"cut {cut.name!r} width {cut.width} exceeds widest stock ({max_stock_width})"
            )
        if cut.length > max_stock_length:
            errors.append(
                f"cut {cut.name!r} length {cut.length} exceeds longest stock ({max_stock_length})"
            )

    return errors
