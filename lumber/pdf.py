"""PDF shop report: cut instructions and board-face diagrams."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from lumber.diagram import board_regions, fill_for
from lumber.dimensions import format_inches
from lumber.models import BoardLayout, CutPlan, Placement, StockPiece
from lumber.report import group_by_board, unused_stock_line
from lumber.sequence import board_instructions
from lumber.windows import window_completion_lines

PAGE_W, PAGE_H = letter
MARGIN = 48
DIAGRAM_MAX_W = PAGE_W - 2 * MARGIN
DIAGRAM_MIN_H = 72
TITLE_SIZE = 16
BODY_SIZE = 10
SMALL_SIZE = 8
LINE = 13


def _hex(color: str) -> HexColor:
    return HexColor(color)


def _board_scales(stock: StockPiece) -> tuple[float, float]:
    scale_x = DIAGRAM_MAX_W / float(stock.length)
    scale_y = max(scale_x, DIAGRAM_MIN_H / float(stock.width))
    return scale_x, scale_y


def _diagram_size(stock: StockPiece) -> tuple[float, float, bool]:
    scale_x, scale_y = _board_scales(stock)
    return (
        float(stock.length) * scale_x,
        float(stock.width) * scale_y,
        scale_y > scale_x * 1.05,
    )


def _cut_lines(
    placements: list[Placement],
    stock: StockPiece,
    kerf: Fraction,
    layout: BoardLayout | None = None,
) -> list[str]:
    lines: list[str] = []
    for indent, step in board_instructions(placements, stock, kerf, layout=layout):
        lines.append(("    " * indent) + step)
    return lines


def _section_height(
    stock: StockPiece,
    placements: list[Placement],
    kerf: Fraction,
    layout: BoardLayout | None = None,
) -> float:
    _w, diagram_h, exaggerated = _diagram_size(stock)
    extra = 14 if exaggerated else 0
    return (
        22
        + diagram_h
        + 28
        + extra
        + 16
        + LINE * len(_cut_lines(placements, stock, kerf, layout=layout))
        + 16
    )


class _Pdf:
    def __init__(self, path: Path) -> None:
        self.canvas = canvas.Canvas(str(path), pagesize=letter, pageCompression=0)
        self.y = PAGE_H - MARGIN

    def ensure(self, height: float) -> None:
        if self.y - height < MARGIN:
            self.canvas.showPage()
            self.y = PAGE_H - MARGIN

    def text(self, message: str, size: int = BODY_SIZE, leading: float | None = None) -> None:
        leading = LINE if leading is None else leading
        self.ensure(leading)
        self.canvas.setFillColor(black)
        self.canvas.setFont("Helvetica", size)
        self.canvas.drawString(MARGIN, self.y - size, message)
        self.y -= leading

    def gap(self, amount: float = 8) -> None:
        self.y -= amount

    def draw_board(
        self,
        stock: StockPiece,
        placements: list[Placement],
        kerf: Fraction,
        layout: BoardLayout | None = None,
    ) -> None:
        scale_x, scale_y = _board_scales(stock)
        board_w, board_h, exaggerated = _diagram_size(stock)
        label_band = 28 + (12 if exaggerated else 0)
        self.ensure(board_h + label_band)

        left = MARGIN
        top = self.y
        bottom = top - board_h

        self.canvas.setFillColor(white)
        self.canvas.setStrokeColor(black)
        self.canvas.setLineWidth(1)
        self.canvas.rect(left, bottom, board_w, board_h, fill=1, stroke=1)

        for region in board_regions(stock, placements, kerf, layout=layout):
            x = left + float(region.length_offset) * scale_x
            h = float(region.width) * scale_y
            w = float(region.length) * scale_x
            y = top - float(region.rip_offset) * scale_y - h
            if region.kind == "piece":
                name = (region.label or "").split(" #")[0]
                self.canvas.setFillColor(_hex(fill_for(name)))
                self.canvas.setStrokeColor(black)
                self.canvas.setLineWidth(0.5)
                self.canvas.rect(x, y, w, h, fill=1, stroke=1)
                if region.label and w >= 48 and h >= 10:
                    self.canvas.setFillColor(black)
                    self.canvas.setFont("Helvetica", 7)
                    self.canvas.drawString(x + 3, y + h / 2 - 2, region.label)
            elif region.kind == "kerf":
                self.canvas.setFillColor(_hex("#8a8a8a"))
                self.canvas.setStrokeColor(_hex("#8a8a8a"))
                self.canvas.rect(x, y, max(w, 0.4), max(h, 0.4), fill=1, stroke=0)
            else:
                self.canvas.setFillColor(_hex("#f0f0f0"))
                self.canvas.setStrokeColor(_hex("#cccccc"))
                self.canvas.setLineWidth(0.4)
                self.canvas.rect(x, y, w, h, fill=1, stroke=1)
                self.canvas.saveState()
                clip = self.canvas.beginPath()
                clip.moveTo(x, y)
                clip.lineTo(x + w, y)
                clip.lineTo(x + w, y + h)
                clip.lineTo(x, y + h)
                clip.close()
                self.canvas.clipPath(clip, stroke=0)
                self.canvas.setStrokeColor(_hex("#d0d0d0"))
                start = x - h
                while start < x + w:
                    self.canvas.line(start, y, start + h, y + h)
                    start += 6
                self.canvas.restoreState()

        self.canvas.setStrokeColor(black)
        self.canvas.setLineWidth(1.2)
        self.canvas.rect(left, bottom, board_w, board_h, fill=0, stroke=1)

        self.y = bottom - 12
        self.canvas.setFillColor(black)
        self.canvas.setFont("Helvetica", SMALL_SIZE)
        self.canvas.drawString(
            left,
            self.y,
            f'0"  <- length ->  {format_inches(stock.length)}"',
        )
        self.y -= 10
        self.canvas.drawString(
            left,
            self.y,
            f'0"  <- width ->  {format_inches(stock.width)}"',
        )
        self.y -= 10
        if exaggerated:
            self.canvas.setFillColor(_hex("#666666"))
            self.canvas.drawString(left, self.y, "Width exaggerated for readability")
            self.y -= 10
        self.gap(6)

    def save(self) -> None:
        self.canvas.save()


def write_pdf(plan: CutPlan, path: Path) -> None:
    """Write a letter-size PDF with diagrams and rip/cross-cut instructions."""
    path = Path(path)
    grouped = group_by_board(plan)
    stock_lookup = {s.id: s for s in plan.stock}
    doc = _Pdf(path)

    doc.text("Lumber cut plan", size=TITLE_SIZE, leading=22)
    doc.text(f'Kerf: {format_inches(plan.kerf)}"')
    doc.text(f"Placed: {len(plan.placements)} pieces")
    doc.text(
        f'Waste: {format_inches(plan.waste_area)} sq in ({plan.waste_percent:.1f}%)'
    )
    for line in window_completion_lines(plan):
        doc.text(line)
    unused = unused_stock_line(plan)
    if unused:
        doc.text(unused)
    doc.gap(10)

    for stock_id in sorted(grouped):
        stock = stock_lookup[stock_id]
        placements = grouped[stock_id]
        layout = plan.board_layouts.get(stock_id)
        doc.ensure(_section_height(stock, placements, plan.kerf, layout=layout))
        doc.text(
            f'{stock_id} - {format_inches(stock.width)}" x 1" x {format_inches(stock.length)}"',
            size=12,
            leading=16,
        )
        doc.draw_board(stock, placements, plan.kerf, layout=layout)
        doc.text("Cuts", size=11, leading=14)
        for line in _cut_lines(placements, stock, plan.kerf, layout=layout):
            doc.text(line, size=9, leading=12)
        doc.gap(14)

    if plan.unplaced:
        doc.ensure(LINE * (3 + len(plan.unplaced)))
        doc.text("Unplaced", size=12, leading=16)
        doc.text(
            f"INSUFFICIENT STOCK: {len(plan.unplaced)} piece(s) could not be placed"
        )
        for cut in plan.unplaced:
            label = cut.instance_id or cut.name
            doc.text(
                f'  {label}: {format_inches(cut.length)}" x {format_inches(cut.width)}"'
            )

    doc.save()
