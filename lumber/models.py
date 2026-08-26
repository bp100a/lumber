"""Data models for stock, cuts, and placement plans.

``Problem`` is the packer input. ``CutPlan`` is the result: placements,
unplaced pieces, per-board cut mode, and (when openings were used) the
original window measurements for the shop PDF.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction


class CutMode(Enum):
    """How the shop should approach one used board."""

    THROUGH_CROSSCUT = "through-crosscut"
    CROSSCUT_FIRST = "crosscut-first"
    RIP_FIRST = "rip-first"


@dataclass(frozen=True)
class StationPlan:
    """Through-cut stations plus a full-width remnant blank."""

    station: Fraction
    count: int
    remnant_start: Fraction
    remnant_length: Fraction


@dataclass(frozen=True)
class BoardLayout:
    """How this board should be cut, plus station geometry when through-cut."""
    mode: CutMode
    station: StationPlan | None = None


@dataclass(frozen=True)
class StockPiece:
    """One board (or a quantity of identical boards) from the stock list."""
    id: str
    width: Fraction
    length: Fraction
    quantity: int = 1

    @property
    def area(self) -> Fraction:
        return self.width * self.length


@dataclass(frozen=True)
class CutPiece:
    """One finished part to cut. ``window_id`` is set when derived from openings."""
    name: str
    width: Fraction
    length: Fraction
    quantity: int = 1
    instance_id: str | None = None
    window_id: str | None = None

    @property
    def area(self) -> Fraction:
        return self.width * self.length


@dataclass(frozen=True)
class Placement:
    """A cut sitting on a board: rip offset is across width, length along the board."""
    stock_id: str
    cut: CutPiece
    rip_offset: Fraction
    length_offset: Fraction

    @property
    def cut_name(self) -> str:
        return self.cut.name


@dataclass
class CutPlan:
    """Packed result: where each piece sits, leftover stock, and shop cut mode."""
    placements: list[Placement] = field(default_factory=list)
    unplaced: list[CutPiece] = field(default_factory=list)
    kerf: Fraction = Fraction(1, 8)
    stock: list[StockPiece] = field(default_factory=list)
    board_layouts: dict[str, BoardLayout] = field(default_factory=dict)
    windows: list[WindowOpening] = field(default_factory=list)

    @property
    def placed_area(self) -> Fraction:
        return sum((p.cut.area for p in self.placements), Fraction(0))

    @property
    def used_stock(self) -> list[StockPiece]:
        """Boards that received at least one cut."""
        used = {p.stock_id for p in self.placements}
        return [s for s in self.stock if s.id in used]

    @property
    def stock_area(self) -> Fraction:
        return sum((s.area * s.quantity for s in self.stock), Fraction(0))

    @property
    def used_stock_area(self) -> Fraction:
        return sum((s.area * s.quantity for s in self.used_stock), Fraction(0))

    @property
    def waste_area(self) -> Fraction:
        """Offcut and kerf on boards that received cuts, not unused stock."""
        if not self.placements:
            return self.stock_area
        return self.used_stock_area - self.placed_area

    @property
    def waste_percent(self) -> float:
        """Waste as a percent of used-board area (or all stock if nothing placed)."""
        basis = self.used_stock_area if self.placements else self.stock_area
        if basis == 0:
            return 0.0
        return float(self.waste_area / basis * 100)


@dataclass(frozen=True)
class WindowOpening:
    """Rough opening height and width; optional meeting-rail override."""
    id: str
    height: Fraction
    width: Fraction
    meeting: Fraction | None = None


@dataclass
class Problem:
    """Stock, cuts (or derived window parts), kerf, and original openings."""
    stock: list[StockPiece]
    cuts: list[CutPiece]
    kerf: Fraction = Fraction(1, 8)
    windows: list[WindowOpening] = field(default_factory=list)
