"""Board cut mode and station geometry.

The packer records a ``StationPlan`` when it packs through-cut blanks.
Sequence and diagrams read ``BoardLayout`` from the ``CutPlan`` instead of
reconstructing intent from rectangles. Callers without a stored layout can
still resolve one from geometry.
"""

from __future__ import annotations

from fractions import Fraction

from lumber.models import BoardLayout, CutMode, CutPlan, Placement, StationPlan, StockPiece


def common_length(placements: list[Placement]) -> Fraction | None:
    """Return the common finished length, or None if lengths differ or empty."""
    if not placements:
        return None
    lengths = {p.cut.length for p in placements}
    if len(lengths) != 1:
        return None
    return next(iter(lengths))


def station_plan(
    board_length: Fraction,
    station: Fraction,
    kerf: Fraction,
) -> StationPlan | None:
    """How many ``station`` blanks fit, remnant start, remnant length.

    Kerf sits between stations and after the last station (through-cut).
    One station is enough on a **10' or longer** board: one 62 1/4" blank
    plus leftover, instead of a full-length rip. Shorter 8' stock keeps
    rip-first / cross-cut-first / gang-rip (count would be 1 but remnant
    packing there loses strips the 8' fixture depends on).
    """
    if station <= 0 or station > board_length:
        return None
    count = 0
    used = Fraction(0)
    while True:
        extra = Fraction(0) if count == 0 else kerf
        if used + extra + station + kerf > board_length:
            break
        used += extra + station
        count += 1
    if count < 1:
        return None
    if count == 1 and board_length < 120:
        return None
    remnant_start = used + kerf
    remnant_length = board_length - remnant_start
    if remnant_length <= 0:
        return None
    return StationPlan(
        station=station,
        count=count,
        remnant_start=remnant_start,
        remnant_length=remnant_length,
    )


def _straddles(placement: Placement, at: Fraction) -> bool:
    start = placement.length_offset
    end = start + placement.cut.length
    return start < at < end


def _fits_through_cut(placements: list[Placement], plan: StationPlan, kerf: Fraction) -> bool:
    """True when no piece straddles a through-cut and remnant parts start after it."""
    cuts = [i * (plan.station + kerf) + plan.station for i in range(plan.count)]
    cuts.append(plan.remnant_start)
    if any(_straddles(p, at) for p in placements for at in cuts):
        return False
    if any(p.length_offset + p.cut.length > plan.remnant_start for p in placements):
        if not any(p.length_offset >= plan.remnant_start for p in placements):
            return False
    return True


def resolve_board_layout(
    placements: list[Placement],
    stock: StockPiece,
    kerf: Fraction,
    recorded: StationPlan | None = None,
) -> BoardLayout:
    """Stored station plan wins for mixed-length boards; else infer from geometry."""
    if not placements:
        return BoardLayout(CutMode.RIP_FIRST)
    if common_length(placements) is not None:
        return BoardLayout(CutMode.CROSSCUT_FIRST)
    if recorded is not None:
        return BoardLayout(CutMode.THROUGH_CROSSCUT, recorded)
    piece_station = max(p.cut.length for p in placements)
    plan = station_plan(stock.length, piece_station, kerf)
    if plan is not None and _fits_through_cut(placements, plan, kerf):
        return BoardLayout(CutMode.THROUGH_CROSSCUT, plan)
    return BoardLayout(CutMode.RIP_FIRST)


def annotate_board_layouts(plan: CutPlan, recorded: dict[str, StationPlan]) -> None:
    """Fill ``plan.board_layouts`` from recorded station plans plus geometry."""
    grouped: dict[str, list[Placement]] = {}
    for placement in plan.placements:
        grouped.setdefault(placement.stock_id, []).append(placement)
    stock_by_id = {s.id: s for s in plan.stock}
    plan.board_layouts = {
        stock_id: resolve_board_layout(
            grouped[stock_id],
            stock_by_id[stock_id],
            plan.kerf,
            recorded.get(stock_id),
        )
        for stock_id in grouped
    }
