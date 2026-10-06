"""PDF shop report: cut instructions and board-face diagrams.

Letter-size cutsheet: summary, per-window cut tables (when openings were
used), used-stock dimensions, a face diagram of each used board, the rip /
cross-cut list, and assembled frames with glass sizes.
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from lumber.diagram import board_regions, fill_for
from lumber.dimensions import format_inches
from lumber.models import BoardLayout, CutPlan, Placement, StockPiece
from lumber.report import (
    format_stock_dims,
    group_by_board,
    summary_volume_lines,
    unused_stock_line,
)
from lumber.sequence import board_instructions
from lumber.windows import (
    FrameAssembly,
    GLASS_CLEARANCE,
    RABBET_DEPTH,
    RABBET_FACE,
    UsedStockRow,
    WindowCutRow,
    WindowCutTable,
    frame_assemblies,
    used_stock_rows,
    window_completion_lines,
    window_cut_tables,
)

PAGE_W, PAGE_H = letter
MARGIN = 48
DIAGRAM_MAX_W = PAGE_W - 2 * MARGIN
DIAGRAM_MIN_H = 72
TITLE_SIZE = 16
BODY_SIZE = 10
SMALL_SIZE = 8
LINE = 13
TABLE_ROW = 15
TABLE_TITLE = 12
TABLE_TITLE_GAP = 6
TABLE_NAME_W = 88
TABLE_MEAS_W = 56
TABLE_QTY_W = 28
TABLE_GAP = 16
GRID = HexColor("#c8c8c8")
TABLE_W = TABLE_NAME_W + TABLE_MEAS_W + TABLE_MEAS_W + TABLE_QTY_W
WOOD = HexColor("#e8d5b0")
GLASS_FILL = HexColor("#c5dff0")
FRAME_DIAGRAM_MAX_H = 250
FRAME_LEFT_DIM = 28
FRAME_BOTTOM_DIM = 16
FRAME_COL_GAP = 16
RABBET_NOTE = (
    f'Rabbet {format_inches(RABBET_FACE)}" wide × {format_inches(RABBET_DEPTH)}" deep; '
    f'glass 1/8" DS, {format_inches(GLASS_CLEARANCE)}" per side'
)


def _inch_label(value: Fraction) -> str:
    """Mixed-number inches with a ``"`` suffix, e.g. ``62 1/2"``."""
    return f'{format_inches(value)}"'


def _hex(color: str) -> HexColor:
    return HexColor(color)


def _board_scales(stock: StockPiece) -> tuple[float, float]:
    """Points per inch so the board fits the page; width may be exaggerated."""
    scale_x = DIAGRAM_MAX_W / float(stock.length)
    scale_y = max(scale_x, DIAGRAM_MIN_H / float(stock.width))
    return scale_x, scale_y


def _diagram_size(stock: StockPiece) -> tuple[float, float, bool]:
    """Board diagram width, height, and whether width is exaggerated."""
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
    """Indented shop instruction lines for one board."""
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
    """Vertical space needed for one board heading, diagram, and cut list."""
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
    """Letter-page canvas with a downward y cursor and page breaks."""
    def __init__(self, path: Path) -> None:
        self.canvas = canvas.Canvas(str(path), pagesize=letter, pageCompression=0)
        self.y = PAGE_H - MARGIN

    def ensure(self, height: float) -> None:
        """Start a new page if ``height`` would run past the bottom margin."""
        if self.y - height < MARGIN:
            self.canvas.showPage()
            self.y = PAGE_H - MARGIN

    def text(self, message: str, size: int = BODY_SIZE, leading: float | None = None) -> None:
        """Draw one left-aligned line and advance the cursor."""
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
        """Draw the board face (pieces, kerf, hatched waste) and axis labels."""
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

    def cell(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        text: str,
        align: str = "center",
    ) -> None:
        """One table cell; mixed numbers stay in a single cell with ``"``."""
        self.canvas.setFillColor(white)
        self.canvas.setStrokeColor(GRID)
        self.canvas.setLineWidth(0.4)
        self.canvas.rect(x, y, width, height, fill=1, stroke=1)
        self.canvas.setFillColor(black)
        self.canvas.setFont("Helvetica", 8)
        baseline = y + 4
        if align == "left":
            self.canvas.drawString(x + 4, baseline, text)
        else:
            self.canvas.drawCentredString(x + width / 2, baseline, text)

    def _opening_row(
        self, left: float, bottom: float, label: str, value: Fraction
    ) -> None:
        x = left
        self.cell(x, bottom, TABLE_NAME_W, TABLE_ROW, label, align="left")
        x += TABLE_NAME_W
        self.cell(x, bottom, TABLE_MEAS_W, TABLE_ROW, _inch_label(value))

    def _part_row(self, left: float, bottom: float, row: WindowCutRow) -> None:
        x = left
        self.cell(x, bottom, TABLE_NAME_W, TABLE_ROW, row.name, align="left")
        x += TABLE_NAME_W
        self.cell(x, bottom, TABLE_MEAS_W, TABLE_ROW, _inch_label(row.length))
        x += TABLE_MEAS_W
        self.cell(x, bottom, TABLE_MEAS_W, TABLE_ROW, _inch_label(row.width))
        x += TABLE_MEAS_W
        self.cell(x, bottom, TABLE_QTY_W, TABLE_ROW, str(row.quantity))

    def _window_block_height(self, table: WindowCutTable) -> float:
        """Height of one window table including title gap and opening rows."""
        rows = len(table.parts)
        if table.height is not None and table.width is not None:
            rows += 2
            spacer = 8
        else:
            spacer = 0
        return TABLE_TITLE + TABLE_TITLE_GAP + TABLE_ROW * rows + spacer + 10

    def _draw_window_block(self, left: float, top: float, table: WindowCutTable) -> None:
        """Draw one window's heading, opening size, and part rows."""
        self.canvas.setFillColor(black)
        self.canvas.setFont("Helvetica-Bold", 9)
        title_baseline = top - TABLE_TITLE
        self.canvas.drawString(left, title_baseline, table.window_id)
        y = title_baseline - TABLE_TITLE_GAP - TABLE_ROW
        if table.height is not None and table.width is not None:
            self._opening_row(left, y, "Height", table.height)
            y -= TABLE_ROW
            self._opening_row(left, y, "Width", table.width)
            y -= TABLE_ROW + 8
        for row in table.parts:
            self._part_row(left, y, row)
            y -= TABLE_ROW

    def draw_window_tables(self, tables: list[WindowCutTable]) -> None:
        """Two-up 'Cuts by window' grids: opening size plus part L × W × qty."""
        if not tables:
            return
        self.text("Cuts by window", size=12, leading=16)
        col_w = TABLE_W
        usable = PAGE_W - 2 * MARGIN
        two_up = col_w * 2 + TABLE_GAP <= usable
        index = 0
        while index < len(tables):
            left_table = tables[index]
            right_table = None
            if two_up and index + 1 < len(tables):
                right_table = tables[index + 1]
            height = self._window_block_height(left_table)
            if right_table is not None:
                height = max(height, self._window_block_height(right_table))
            self.ensure(height)
            top = self.y
            self._draw_window_block(MARGIN, top, left_table)
            if right_table is not None:
                self._draw_window_block(MARGIN + col_w + TABLE_GAP, top, right_table)
                index += 2
            else:
                index += 1
            self.y = top - height
        self.gap(8)

    def draw_stock_used(self, rows: list[UsedStockRow]) -> None:
        """List used boards with largest face dim first, 1\" last."""
        if not rows:
            return
        self.ensure(16 + LINE * len(rows) + 8)
        self.text("Stock used", size=12, leading=16)
        for row in rows:
            extra = f"  ×{row.quantity}" if row.quantity != 1 else ""
            self.text(f"{row.id}  {format_stock_dims(row.width, row.length)}{extra}")
        self.gap(8)

    def _frame_scale(self, frame: FrameAssembly, col_w: float) -> float:
        """Points per inch so the frame face fits the column."""
        max_w = max(col_w - FRAME_LEFT_DIM - 4, 40)
        return min(max_w / float(frame.outer_width), FRAME_DIAGRAM_MAX_H / float(frame.outer_height))

    def _frame_diagram_size(self, frame: FrameAssembly, col_w: float) -> tuple[float, float]:
        scale = self._frame_scale(frame, col_w)
        return float(frame.outer_width) * scale, float(frame.outer_height) * scale

    def _frame_block_height(self, frame: FrameAssembly, col_w: float) -> float:
        _w, diagram_h = self._frame_diagram_size(frame, col_w)
        glass_lines = len(frame.glass)
        return TABLE_TITLE + diagram_h + FRAME_BOTTOM_DIM + 14 * (1 + glass_lines) + 16

    def _meeting_band(self, frame: FrameAssembly) -> tuple[Fraction, Fraction]:
        """Meeting-rail bottom and top, inches from the outer bottom."""
        if frame.glass:
            lower = frame.glass[1]
            lower_daylight = lower.height - 2 * RABBET_FACE + 2 * GLASS_CLEARANCE
            meeting_bottom = frame.bottom_rail + lower_daylight
        else:
            remaining = (
                frame.outer_height
                - frame.top_rail
                - frame.bottom_rail
                - frame.meeting_rail
            )
            meeting_bottom = frame.bottom_rail + remaining / 2
        return meeting_bottom, meeting_bottom + frame.meeting_rail

    def _draw_frame_face(
        self,
        left: float,
        bottom: float,
        frame: FrameAssembly,
        scale: float,
    ) -> None:
        """Stiles full height; rails between; glass in the daylight openings."""
        w = float(frame.outer_width) * scale
        h = float(frame.outer_height) * scale
        stile = float(frame.stile) * scale
        top = float(frame.top_rail) * scale
        bottom_rail = float(frame.bottom_rail) * scale
        meeting_bottom_in, meeting_top_in = self._meeting_band(frame)
        meeting_y = bottom + float(meeting_bottom_in) * scale
        meeting_h = float(frame.meeting_rail) * scale
        inner_w = w - 2 * stile

        self.canvas.setFillColor(WOOD)
        self.canvas.setStrokeColor(black)
        self.canvas.setLineWidth(0.8)
        self.canvas.rect(left, bottom, w, h, fill=1, stroke=1)

        if frame.glass and inner_w > 1:
            upper_bottom = meeting_y + meeting_h
            upper_h = h - top - (upper_bottom - bottom)
            lower_h = meeting_y - bottom - bottom_rail
            self.canvas.setFillColor(GLASS_FILL)
            self.canvas.setStrokeColor(HexColor("#8ab0c8"))
            self.canvas.setLineWidth(0.4)
            if upper_h > 1:
                self.canvas.rect(left + stile, upper_bottom, inner_w, upper_h, fill=1, stroke=1)
            if lower_h > 1:
                self.canvas.rect(
                    left + stile, bottom + bottom_rail, inner_w, lower_h, fill=1, stroke=1
                )

        self.canvas.setStrokeColor(black)
        self.canvas.setLineWidth(0.6)
        self.canvas.setFillColor(WOOD)
        self.canvas.rect(left, bottom, stile, h, fill=1, stroke=1)
        self.canvas.rect(left + w - stile, bottom, stile, h, fill=1, stroke=1)
        self.canvas.rect(left + stile, bottom + h - top, inner_w, top, fill=1, stroke=1)
        self.canvas.rect(left + stile, bottom, inner_w, bottom_rail, fill=1, stroke=1)
        self.canvas.rect(left + stile, meeting_y, inner_w, meeting_h, fill=1, stroke=1)

        self.canvas.setStrokeColor(black)
        self.canvas.setLineWidth(1)
        self.canvas.rect(left, bottom, w, h, fill=0, stroke=1)

        self.canvas.setFillColor(black)
        self.canvas.setFont("Helvetica", 6)
        if inner_w >= 36:
            if frame.glass:
                upper, lower = frame.glass[0], frame.glass[1]
                upper_bottom = meeting_y + meeting_h
                upper_h = h - top - (upper_bottom - bottom)
                lower_h = meeting_y - bottom - bottom_rail
                if upper_h >= 10:
                    self.canvas.drawCentredString(
                        left + w / 2,
                        upper_bottom + upper_h / 2 - 2,
                        f'{_inch_label(upper.width)} × {_inch_label(upper.height)}',
                    )
                if lower_h >= 10:
                    self.canvas.drawCentredString(
                        left + w / 2,
                        bottom + bottom_rail + lower_h / 2 - 2,
                        f'{_inch_label(lower.width)} × {_inch_label(lower.height)}',
                    )

    def _draw_frame_block(self, left: float, top: float, frame: FrameAssembly, col_w: float) -> None:
        """One assembled frame: heading, face drawing, outer size, glass list."""
        scale = self._frame_scale(frame, col_w)
        diagram_w, diagram_h = self._frame_diagram_size(frame, col_w)
        self.canvas.setFillColor(black)
        self.canvas.setFont("Helvetica-Bold", 9)
        title_baseline = top - TABLE_TITLE
        self.canvas.drawString(left, title_baseline, frame.window_id)

        origin_x = left + FRAME_LEFT_DIM
        origin_y = title_baseline - TABLE_TITLE_GAP - diagram_h
        self._draw_frame_face(origin_x, origin_y, frame, scale)

        self.canvas.setFillColor(black)
        self.canvas.setFont("Helvetica", 7)
        self.canvas.drawCentredString(
            origin_x + diagram_w / 2,
            origin_y - 10,
            _inch_label(frame.outer_width),
        )
        self.canvas.saveState()
        self.canvas.translate(left + 8, origin_y + diagram_h / 2)
        self.canvas.rotate(90)
        self.canvas.drawCentredString(0, 0, _inch_label(frame.outer_height))
        self.canvas.restoreState()

        y = origin_y - FRAME_BOTTOM_DIM - 2
        self.canvas.setFont("Helvetica", 8)
        self.canvas.drawString(
            left,
            y,
            f'Outer {_inch_label(frame.outer_width)} × {_inch_label(frame.outer_height)}',
        )
        y -= 12
        for lite in frame.glass:
            self.canvas.drawString(
                left,
                y,
                f'{lite.name} glass {_inch_label(lite.width)} × {_inch_label(lite.height)}',
            )
            y -= 12

    def draw_assembled_frames(self, frames: list[FrameAssembly]) -> None:
        """Face drawings of each storm frame plus glass sizes, two-up when they fit."""
        if not frames:
            return
        self.text("Assembled frames", size=12, leading=16)
        self.text(RABBET_NOTE, size=9, leading=12)
        usable = PAGE_W - 2 * MARGIN
        two_up = True
        col_w = (usable - FRAME_COL_GAP) / 2 if two_up else usable
        index = 0
        while index < len(frames):
            left_frame = frames[index]
            right_frame = None
            if two_up and index + 1 < len(frames):
                right_frame = frames[index + 1]
            height = self._frame_block_height(left_frame, col_w)
            if right_frame is not None:
                height = max(height, self._frame_block_height(right_frame, col_w))
            self.ensure(height)
            top = self.y
            self._draw_frame_block(MARGIN, top, left_frame, col_w)
            if right_frame is not None:
                self._draw_frame_block(MARGIN + col_w + FRAME_COL_GAP, top, right_frame, col_w)
                index += 2
            else:
                index += 1
            self.y = top - height
        self.gap(8)

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
    for line in summary_volume_lines(plan):
        doc.text(line)
    for line in window_completion_lines(plan):
        doc.text(line)
    unused = unused_stock_line(plan)
    if unused:
        doc.text(unused)
    doc.gap(8)
    doc.draw_window_tables(window_cut_tables(plan))
    doc.draw_stock_used(used_stock_rows(plan))

    for stock_id in sorted(grouped):
        stock = stock_lookup[stock_id]
        placements = grouped[stock_id]
        layout = plan.board_layouts.get(stock_id)
        doc.ensure(_section_height(stock, placements, plan.kerf, layout=layout))
        doc.text(
            f"{stock_id} - {format_stock_dims(stock.width, stock.length)}",
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

    doc.draw_assembled_frames(frame_assemblies(plan))

    doc.save()
