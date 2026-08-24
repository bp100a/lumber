"""Data models for stock, cuts, and placement plans."""

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
    mode: CutMode
    station: StationPlan | None = None


@dataclass(frozen=True)
class StockPiece:
    id: str
    width: Fraction
    length: Fraction
    quantity: int = 1

    @property
    def area(self) -> Fraction:
        return self.width * self.length


@dataclass(frozen=True)
class CutPiece:
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
    stock_id: str
    cut: CutPiece
    rip_offset: Fraction
    length_offset: Fraction

    @property
    def cut_name(self) -> str:
        return self.cut.name


@dataclass
class CutPlan:
    placements: list[Placement] = field(default_factory=list)
    unplaced: list[CutPiece] = field(default_factory=list)
    kerf: Fraction = Fraction(1, 8)
    stock: list[StockPiece] = field(default_factory=list)
    board_layouts: dict[str, BoardLayout] = field(default_factory=dict)

    @property
    def placed_area(self) -> Fraction:
        return sum((p.cut.area for p in self.placements), Fraction(0))

    @property
    def used_stock(self) -> list[StockPiece]:
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
        basis = self.used_stock_area if self.placements else self.stock_area
        if basis == 0:
            return 0.0
        return float(self.waste_area / basis * 100)


@dataclass
class Problem:
    stock: list[StockPiece]
    cuts: list[CutPiece]
    kerf: Fraction = Fraction(1, 8)
