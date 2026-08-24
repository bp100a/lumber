"""Rip-to-width packer, with through-cut stations on long boards.

Default geometry: rip a board into strips of one width, then cross-cut each
strip (1D packing along length, 1D assignment of strips across width, kerf
between cuts).

When two or more of the longest piece fit on a stock length, pack that class
as station blanks plus a full-width remnant so a through cross-cut shortens
the rips. Those boards are recorded on the plan as through-cut layouts.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from fractions import Fraction

from lumber.layout import annotate_board_layouts, station_plan
from lumber.models import CutPiece, CutPlan, Placement, Problem, StationPlan, StockPiece
from lumber.validate import expand_cuts, expand_stock


@dataclass
class _PackedStrip:
    width: Fraction
    pieces: list[CutPiece] = field(default_factory=list)
    used_length: Fraction = field(default_factory=lambda: Fraction(0))


@dataclass
class _BoardState:
    stock: StockPiece
    used_width: Fraction = field(default_factory=lambda: Fraction(0))
    blank_length: Fraction | None = None
    length_offset: Fraction = field(default_factory=lambda: Fraction(0))

    @property
    def pack_length(self) -> Fraction:
        return self.stock.length if self.blank_length is None else self.blank_length


def _length_needed(used_length: Fraction, piece_length: Fraction, kerf: Fraction) -> Fraction:
    if used_length == 0:
        return piece_length
    return piece_length + kerf


def _pack_width_group(
    pieces: list[CutPiece],
    board_length: Fraction,
    kerf: Fraction,
) -> list[_PackedStrip]:
    """Best-fit decreasing along length: longest pieces first, tightest strip remnant."""
    ordered = sorted(pieces, key=lambda p: p.length, reverse=True)
    strips: list[_PackedStrip] = []

    for piece in ordered:
        best_index: int | None = None
        best_remnant: Fraction | None = None
        for index, strip in enumerate(strips):
            needed = _length_needed(strip.used_length, piece.length, kerf)
            remnant = board_length - strip.used_length - needed
            if remnant < 0:
                continue
            if best_remnant is None or remnant < best_remnant:
                best_index = index
                best_remnant = remnant

        if best_index is not None:
            strip = strips[best_index]
            strip.used_length += _length_needed(strip.used_length, piece.length, kerf)
            strip.pieces.append(piece)
            continue

        if piece.length <= board_length:
            strips.append(
                _PackedStrip(width=piece.width, pieces=[piece], used_length=piece.length)
            )

    return strips


def _width_needed(used_width: Fraction, strip_width: Fraction, kerf: Fraction) -> Fraction:
    if used_width == 0:
        return strip_width
    return strip_width + kerf


def _best_board(
    boards: list[_BoardState],
    strip: _PackedStrip,
    kerf: Fraction,
    lengths: set[Fraction] | None = None,
) -> _BoardState | None:
    """Tightest remaining-width fit among boards that can take this strip."""
    best: tuple[Fraction, _BoardState] | None = None
    for board in boards:
        if lengths is not None and board.stock.length not in lengths:
            continue
        if strip.used_length > board.pack_length:
            continue
        needed = _width_needed(board.used_width, strip.width, kerf)
        remnant = board.stock.width - board.used_width - needed
        if remnant < 0:
            continue
        if best is None or remnant < best[0]:
            best = (remnant, board)
    return best[1] if best else None


def _placements_for_strip(
    stock_id: str,
    rip_offset: Fraction,
    strip: _PackedStrip,
    kerf: Fraction,
    length_offset: Fraction = Fraction(0),
) -> list[Placement]:
    placements: list[Placement] = []
    cursor = length_offset
    for index, piece in enumerate(strip.pieces):
        if index > 0:
            cursor += kerf
        placements.append(
            Placement(
                stock_id=stock_id,
                cut=piece,
                rip_offset=rip_offset,
                length_offset=cursor,
            )
        )
        cursor += piece.length
    return placements


def _place_strips(
    strips: list[_PackedStrip],
    boards: list[_BoardState],
    kerf: Fraction,
    lengths: set[Fraction] | None,
) -> tuple[list[Placement], list[CutPiece]]:
    """Assign strips to boards. Pieces on strips that do not fit stay unplaced."""
    strips = sorted(strips, key=lambda s: (s.width, s.used_length), reverse=True)
    placements: list[Placement] = []
    unplaced: list[CutPiece] = []
    for strip in strips:
        board = _best_board(boards, strip, kerf, lengths=lengths)
        if board is None:
            unplaced.extend(strip.pieces)
            continue
        needed = _width_needed(board.used_width, strip.width, kerf)
        rip_offset = Fraction(0) if board.used_width == 0 else board.used_width + kerf
        board.used_width += needed
        placements.extend(
            _placements_for_strip(
                board.stock.id,
                rip_offset,
                strip,
                kerf,
                length_offset=board.length_offset,
            )
        )
    return placements, unplaced


def _partition_by_length(
    pieces: list[CutPiece],
    board_length: Fraction,
) -> tuple[list[CutPiece], list[CutPiece]]:
    fit: list[CutPiece] = []
    too_long: list[CutPiece] = []
    for piece in pieces:
        if piece.length > board_length:
            too_long.append(piece)
        else:
            fit.append(piece)
    return fit, too_long


def _strips_for_pieces(
    pieces: list[CutPiece],
    board_length: Fraction,
    kerf: Fraction,
) -> list[_PackedStrip]:
    by_width: dict[Fraction, list[CutPiece]] = defaultdict(list)
    for piece in pieces:
        by_width[piece.width].append(piece)
    strips: list[_PackedStrip] = []
    for width in sorted(by_width, reverse=True):
        strips.extend(_pack_width_group(by_width[width], board_length, kerf))
    return strips


def _virtual_blanks(
    boards: list[_BoardState],
    physical_length: Fraction,
    plan: StationPlan,
    kerf: Fraction,
) -> tuple[list[_BoardState], list[_BoardState]]:
    stations: list[_BoardState] = []
    remnants: list[_BoardState] = []
    for board in boards:
        if board.stock.length != physical_length:
            continue
        offset = Fraction(0)
        for _ in range(plan.count):
            stations.append(
                _BoardState(
                    stock=board.stock,
                    blank_length=plan.station,
                    length_offset=offset,
                )
            )
            offset += plan.station + kerf
        remnants.append(
            _BoardState(
                stock=board.stock,
                blank_length=plan.remnant_length,
                length_offset=plan.remnant_start,
            )
        )
    return stations, remnants


def _mark_consumed(boards: list[_BoardState], stock_ids: set[str]) -> None:
    """Physical boards that received station pieces cannot take later strips."""
    for board in boards:
        if board.stock.id in stock_ids:
            board.used_width = board.stock.width


def _place_station_pack(
    pieces: list[CutPiece],
    boards: list[_BoardState],
    physical_length: Fraction,
    plan: StationPlan,
    kerf: Fraction,
) -> tuple[list[Placement], list[CutPiece]]:
    """Pack a length class as station blanks plus a full-width remnant blank."""
    if not pieces:
        return [], []
    stations, remnants = _virtual_blanks(boards, physical_length, plan, kerf)
    if not stations:
        return [], pieces

    short_parts = [p for p in pieces if p.length <= plan.remnant_length]
    long_parts = [p for p in pieces if p.length > plan.remnant_length]
    placements: list[Placement] = []

    strips = _strips_for_pieces(long_parts, plan.station, kerf)
    placed, unplaced_long = _place_strips(strips, stations, kerf, lengths=None)
    placements.extend(placed)

    overflow_short = short_parts
    if remnants:
        strips = _strips_for_pieces(overflow_short, plan.remnant_length, kerf)
        placed, overflow_short = _place_strips(strips, remnants, kerf, lengths=None)
        placements.extend(placed)

    if overflow_short:
        strips = _strips_for_pieces(overflow_short, plan.station, kerf)
        placed, overflow_short = _place_strips(strips, stations, kerf, lengths=None)
        placements.extend(placed)

    _mark_consumed(boards, {p.stock_id for p in placements})
    return placements, unplaced_long + overflow_short


def optimize(problem: Problem) -> CutPlan:
    """Assign cuts to stock by length class, longest boards first.

    Strips are packed to each distinct stock length so a pair of 62 1/4" stiles
    can share a 12' strip without blocking 10' boards that can only take one
    stile per strip.

    On a length class that fits two or more long stations, short parts go in
    the remnant blank so a through cross-cut shortens the rips. Those boards
    get a stored through-cut layout.
    """
    stock = expand_stock(problem.stock)
    pending = expand_cuts(problem.cuts)
    kerf = problem.kerf

    plan = CutPlan(kerf=kerf, stock=stock)
    if not stock:
        plan.unplaced = pending
        return plan

    boards = [_BoardState(stock=piece) for piece in stock]
    placements: list[Placement] = []
    remaining = pending
    recorded_stations: dict[str, StationPlan] = {}
    for length in sorted({piece.length for piece in stock}, reverse=True):
        if not remaining:
            break
        fit, remaining = _partition_by_length(remaining, length)
        if not fit:
            continue
        stations = station_plan(length, max(p.length for p in fit), kerf)
        if stations is not None:
            placed, overflow = _place_station_pack(fit, boards, length, stations, kerf)
            for placement in placed:
                recorded_stations[placement.stock_id] = stations
        else:
            strips = _strips_for_pieces(fit, length, kerf)
            placed, overflow = _place_strips(strips, boards, kerf, lengths={length})
        placements.extend(placed)
        remaining = overflow + remaining

    plan.placements = placements
    plan.unplaced = remaining
    annotate_board_layouts(plan, recorded_stations)
    return plan
