"""Scale face diagrams of a board's rip strips and cross-cuts.

``board_regions`` builds piece / kerf / waste rectangles in inches.
``board_svg`` draws them for markdown reports; the PDF reuses the same
regions with ReportLab.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from xml.sax.saxutils import escape

from lumber.dimensions import format_inches
from lumber.layout import resolve_board_layout
from lumber.models import BoardLayout, CutMode, Placement, StationPlan, StockPiece
from lumber.sequence import (
    RipStrip,
    gang_combined_width,
    iter_strip_runs,
    length_offcut,
    offcut_after_crosscut,
)


def diagram_filename(stock_id: str, prefix: str = "") -> str:
    """Safe sibling SVG name, e.g. ``storm_window-board-a.svg``."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stock_id)
    if prefix:
        return f"{prefix}-{safe}.svg"
    return f"{safe}.svg"

MAX_DIAGRAM_WIDTH = 800
MIN_BOARD_HEIGHT = 80
INCH_PX = 8
PAD_LEFT = 52
PAD_RIGHT = 16
PAD_TOP = 24
PAD_BOTTOM = 36

_FILLS = (
    "#c5d4e8",
    "#d4e8c5",
    "#e8d4c5",
    "#e8c5d4",
    "#d4c5e8",
    "#e8e4c5",
    "#c5e8e0",
)


@dataclass(frozen=True)
class DiagramRect:
    """A region on the board face, in inches (length along x, width along y)."""

    kind: str
    length_offset: Fraction
    rip_offset: Fraction
    length: Fraction
    width: Fraction
    label: str | None = None


def fill_for(name: str) -> str:
    """Stable fill color for a part name (same hue across boards)."""
    return _FILLS[sum(ord(ch) for ch in name) % len(_FILLS)]


def _fill_for(name: str) -> str:
    return fill_for(name)


def board_regions(
    stock: StockPiece,
    placements: list[Placement],
    kerf: Fraction,
    layout: BoardLayout | None = None,
) -> list[DiagramRect]:
    """Return piece, kerf, and offcut rectangles for one board."""
    resolved = layout or resolve_board_layout(placements, stock, kerf)
    if resolved.mode is CutMode.THROUGH_CROSSCUT and resolved.station is not None:
        return _regions_through_crosscut(stock, placements, kerf, resolved.station)
    if resolved.mode is CutMode.CROSSCUT_FIRST:
        return _regions_crosscut_first(stock, placements, kerf)
    return _regions_rip_first(stock, placements, kerf)


def _regions_rip_first(
    stock: StockPiece,
    placements: list[Placement],
    kerf: Fraction,
) -> list[DiagramRect]:
    """Strip regions along length, including gang-rip combined blanks."""
    regions: list[DiagramRect] = []
    occupied_width = Fraction(0)
    for run in iter_strip_runs(placements, kerf):
        first = run[0]
        if first.rip_offset > occupied_width:
            gap = first.rip_offset - occupied_width
            kind = "kerf" if gap <= kerf else "waste"
            regions.append(
                DiagramRect(
                    kind=kind,
                    length_offset=Fraction(0),
                    rip_offset=occupied_width,
                    length=stock.length,
                    width=gap,
                )
            )
        if len(run) >= 2:
            _add_gang_regions(regions, run, stock, kerf)
            occupied_width = run[-1].rip_offset + run[-1].width
        else:
            _add_strip_length_regions(regions, run[0], stock, kerf)
            occupied_width = run[0].rip_offset + run[0].width
    if occupied_width < stock.width:
        unused = stock.width - occupied_width
        kind = "kerf" if unused <= kerf else "waste"
        regions.append(
            DiagramRect(
                kind=kind,
                length_offset=Fraction(0),
                rip_offset=occupied_width,
                length=stock.length,
                width=unused,
            )
        )
    return regions


def _add_strip_length_regions(
    regions: list[DiagramRect],
    strip: RipStrip,
    stock: StockPiece,
    kerf: Fraction,
) -> None:
    """Pieces, kerf, and leftover along one rip-first strip."""
    cursor = Fraction(0)
    for placement in strip.placements:
        if placement.length_offset > cursor:
            gap = placement.length_offset - cursor
            kind = "kerf" if gap <= kerf else "waste"
            regions.append(
                DiagramRect(
                    kind=kind,
                    length_offset=cursor,
                    rip_offset=strip.rip_offset,
                    length=gap,
                    width=strip.width,
                )
            )
        regions.append(_piece_rect(placement))
        cursor = placement.length_offset + placement.cut.length
    if cursor < stock.length:
        unused = stock.length - cursor
        kind = "kerf" if unused <= kerf else "waste"
        regions.append(
            DiagramRect(
                kind=kind,
                length_offset=cursor,
                rip_offset=strip.rip_offset,
                length=unused,
                width=strip.width,
            )
        )


def _add_gang_regions(
    regions: list[DiagramRect],
    gang: list[RipStrip],
    stock: StockPiece,
    kerf: Fraction,
) -> None:
    """Pieces, between-strip kerf, and combined-width offcut for a gang rip."""
    for strip in gang:
        for placement in strip.placements:
            regions.append(_piece_rect(placement))

    blank_end = max(
        p.length_offset + p.cut.length for strip in gang for p in strip.placements
    )
    combined = gang_combined_width(gang)
    rip0 = gang[0].rip_offset

    for left, right in zip(gang, gang[1:]):
        gap_start = left.rip_offset + left.width
        gap = right.rip_offset - gap_start
        if gap > 0:
            kind = "kerf" if gap <= kerf else "waste"
            regions.append(
                DiagramRect(
                    kind=kind,
                    length_offset=Fraction(0),
                    rip_offset=gap_start,
                    length=blank_end,
                    width=gap,
                )
            )

    if kerf > 0 and blank_end + kerf <= stock.length:
        regions.append(
            DiagramRect(
                kind="kerf",
                length_offset=blank_end,
                rip_offset=rip0,
                length=kerf,
                width=combined,
            )
        )
    offcut = length_offcut(stock.length, blank_end, kerf, combined)
    if offcut:
        offcut_len, offcut_w = offcut
        start = stock.length - offcut_len
        regions.append(
            DiagramRect(
                kind="waste",
                length_offset=start,
                rip_offset=rip0,
                length=offcut_len,
                width=offcut_w,
            )
        )


def _regions_crosscut_first(
    stock: StockPiece,
    placements: list[Placement],
    kerf: Fraction,
) -> list[DiagramRect]:
    """Through cross-cut, then rips on the blank; offcut is full width."""
    regions: list[DiagramRect] = [_piece_rect(p) for p in placements]
    blank_end = max(p.length_offset + p.cut.length for p in placements)

    by_rip: dict[Fraction, list[Placement]] = defaultdict(list)
    for placement in placements:
        by_rip[placement.rip_offset].append(placement)
    _add_width_gaps(regions, stock, by_rip, kerf, span_length=blank_end)

    if kerf > 0 and blank_end + kerf <= stock.length:
        regions.append(
            DiagramRect(
                kind="kerf",
                length_offset=blank_end,
                rip_offset=Fraction(0),
                length=kerf,
                width=stock.width,
            )
        )
    offcut = offcut_after_crosscut(stock, blank_end, kerf)
    if offcut:
        offcut_len, offcut_w = offcut
        start = stock.length - offcut_len
        regions.append(
            DiagramRect(
                kind="waste",
                length_offset=start,
                rip_offset=Fraction(0),
                length=offcut_len,
                width=offcut_w,
            )
        )
    return regions


def _piece_rect(placement: Placement) -> DiagramRect:
    """Labeled rectangle for one finished part on the board face."""
    return DiagramRect(
        kind="piece",
        length_offset=placement.length_offset,
        rip_offset=placement.rip_offset,
        length=placement.cut.length,
        width=placement.cut.width,
        label=placement.cut.instance_id or placement.cut.name,
    )


def _add_width_gaps(
    regions: list[DiagramRect],
    stock: StockPiece,
    by_rip: dict[Fraction, list[Placement]],
    kerf: Fraction,
    span_length: Fraction,
    length_offset: Fraction = Fraction(0),
) -> None:
    """Kerf or waste between rip strips and leftover width on a blank."""
    occupied_width = Fraction(0)
    for rip_offset in sorted(by_rip):
        strip_width = by_rip[rip_offset][0].cut.width
        if rip_offset > occupied_width:
            gap = rip_offset - occupied_width
            kind = "kerf" if gap <= kerf else "waste"
            regions.append(
                DiagramRect(
                    kind=kind,
                    length_offset=length_offset,
                    rip_offset=occupied_width,
                    length=span_length,
                    width=gap,
                )
            )
        occupied_width = rip_offset + strip_width
    if occupied_width < stock.width:
        unused = stock.width - occupied_width
        kind = "kerf" if unused <= kerf else "waste"
        regions.append(
            DiagramRect(
                kind=kind,
                length_offset=length_offset,
                rip_offset=occupied_width,
                length=span_length,
                width=unused,
            )
        )


def _add_length_gaps(
    regions: list[DiagramRect],
    placements: list[Placement],
    rip_offset: Fraction,
    width: Fraction,
    start: Fraction,
    end: Fraction,
    kerf: Fraction,
) -> None:
    """Kerf or waste along one strip between ``start`` and ``end``."""
    cursor = start
    for placement in sorted(placements, key=lambda p: p.length_offset):
        if placement.length_offset > cursor:
            gap = placement.length_offset - cursor
            kind = "kerf" if gap <= kerf else "waste"
            regions.append(
                DiagramRect(
                    kind=kind,
                    length_offset=cursor,
                    rip_offset=rip_offset,
                    length=gap,
                    width=width,
                )
            )
        cursor = placement.length_offset + placement.cut.length
    if cursor < end:
        unused = end - cursor
        kind = "kerf" if unused <= kerf else "waste"
        regions.append(
            DiagramRect(
                kind=kind,
                length_offset=cursor,
                rip_offset=rip_offset,
                length=unused,
                width=width,
            )
        )


def _regions_through_crosscut(
    stock: StockPiece,
    placements: list[Placement],
    kerf: Fraction,
    plan: StationPlan,
) -> list[DiagramRect]:
    """Through-cut stations plus a full-width remnant blank."""
    regions: list[DiagramRect] = [_piece_rect(p) for p in placements]
    unit = plan.station + kerf
    station_parts = [p for p in placements if p.length_offset < plan.remnant_start]
    remnant_parts = [p for p in placements if p.length_offset >= plan.remnant_start]

    by_station: dict[Fraction, list[Placement]] = defaultdict(list)
    for placement in station_parts:
        start = (placement.length_offset // unit) * unit
        by_station[start].append(placement)

    offset = Fraction(0)
    while offset < plan.remnant_start:
        group = by_station.get(offset, [])
        by_rip: dict[Fraction, list[Placement]] = defaultdict(list)
        for placement in group:
            by_rip[placement.rip_offset].append(placement)
        _add_width_gaps(
            regions, stock, by_rip, kerf, span_length=plan.station, length_offset=offset
        )
        for rip_offset, strip_parts in by_rip.items():
            _add_length_gaps(
                regions,
                strip_parts,
                rip_offset,
                strip_parts[0].cut.width,
                offset,
                offset + plan.station,
                kerf,
            )
        if kerf > 0:
            regions.append(
                DiagramRect(
                    kind="kerf",
                    length_offset=offset + plan.station,
                    rip_offset=Fraction(0),
                    length=kerf,
                    width=stock.width,
                )
            )
        offset += unit

    remnant_by_rip: dict[Fraction, list[Placement]] = defaultdict(list)
    for placement in remnant_parts:
        remnant_by_rip[placement.rip_offset].append(placement)
    if remnant_parts:
        _add_width_gaps(
            regions,
            stock,
            remnant_by_rip,
            kerf,
            span_length=plan.remnant_length,
            length_offset=plan.remnant_start,
        )
        for rip_offset, strip_parts in remnant_by_rip.items():
            _add_length_gaps(
                regions,
                strip_parts,
                rip_offset,
                strip_parts[0].cut.width,
                plan.remnant_start,
                plan.remnant_start + plan.remnant_length,
                kerf,
            )
    else:
        regions.append(
            DiagramRect(
                kind="waste",
                length_offset=plan.remnant_start,
                rip_offset=Fraction(0),
                length=plan.remnant_length,
                width=stock.width,
            )
        )
    return regions


def _scales(stock: StockPiece) -> tuple[float, float]:
    """Pixels per inch (x = length, y = width); width may be exaggerated."""
    scale_x = min(INCH_PX, MAX_DIAGRAM_WIDTH / float(stock.length))
    scale_y = max(scale_x, MIN_BOARD_HEIGHT / float(stock.width))
    return scale_x, scale_y


def board_svg(
    stock: StockPiece,
    placements: list[Placement],
    kerf: Fraction,
    layout: BoardLayout | None = None,
) -> str:
    """SVG face view: length left-to-right, first rip strip at the top."""
    scale_x, scale_y = _scales(stock)
    board_w = float(stock.length) * scale_x
    board_h = float(stock.width) * scale_y
    svg_w = PAD_LEFT + board_w + PAD_RIGHT
    svg_h = PAD_TOP + board_h + PAD_BOTTOM
    exaggerated = scale_y > scale_x * 1.05

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w:.1f}" height="{svg_h:.1f}" '
        f'viewBox="0 0 {svg_w:.1f} {svg_h:.1f}" role="img" '
        f'aria-label="Cut diagram for {escape(stock.id)}">',
        "<defs>",
        f'<pattern id="waste-{escape(stock.id)}" width="6" height="6" patternUnits="userSpaceOnUse">',
        '<rect width="6" height="6" fill="#f4f4f4"/>',
        '<path d="M0 6 L6 0" stroke="#d0d0d0" stroke-width="1"/>',
        "</pattern>",
        "</defs>",
        f'<rect x="{PAD_LEFT:.1f}" y="{PAD_TOP:.1f}" width="{board_w:.1f}" height="{board_h:.1f}" '
        'fill="#ffffff" stroke="#333333" stroke-width="1.5"/>',
    ]

    for region in board_regions(stock, placements, kerf, layout=layout):
        x = PAD_LEFT + float(region.length_offset) * scale_x
        y = PAD_TOP + float(region.rip_offset) * scale_y
        w = float(region.length) * scale_x
        h = float(region.width) * scale_y
        if region.kind == "piece":
            name = (region.label or "").split(" #")[0]
            fill = _fill_for(name)
            size = f'{format_inches(region.length)}" × {format_inches(region.width)}"'
            parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
                f'fill="{fill}" stroke="#333333" stroke-width="0.75" '
                f'data-kind="piece" data-label="{escape(region.label or "")}" '
                f'data-length-offset="{escape(format_inches(region.length_offset))}" '
                f'data-rip-offset="{escape(format_inches(region.rip_offset))}" '
                f'data-length="{escape(format_inches(region.length))}" '
                f'data-width="{escape(format_inches(region.width))}">'
                f"<title>{escape(region.label or '')} — {escape(size)}</title>"
                "</rect>"
            )
            if w >= 56 and h >= 14 and region.label:
                tx = x + 4
                ty = y + min(h * 0.55, 12)
                parts.append(
                    f'<text x="{tx:.2f}" y="{ty:.2f}" font-family="sans-serif" '
                    f'font-size="10" fill="#222222">{escape(region.label)}</text>'
                )
            elif w >= 56 and h >= 10 and region.label:
                parts.append(
                    f'<text x="{x + 3:.2f}" y="{y + h - 2:.2f}" font-family="sans-serif" '
                    f'font-size="8" fill="#222222">{escape(region.label)}</text>'
                )
        elif region.kind == "kerf":
            parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
                'fill="#8a8a8a" data-kind="kerf"/>'
            )
        else:
            parts.append(
                f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
                f'fill="url(#waste-{escape(stock.id)})" stroke="#cccccc" stroke-width="0.5" data-kind="waste"/>'
            )

    parts.append(
        f'<rect x="{PAD_LEFT:.1f}" y="{PAD_TOP:.1f}" width="{board_w:.1f}" height="{board_h:.1f}" '
        'fill="none" stroke="#333333" stroke-width="1.5"/>'
    )
    parts.append(
        f'<text x="{PAD_LEFT:.1f}" y="{PAD_TOP + board_h + 22:.1f}" font-family="sans-serif" '
        f'font-size="11" fill="#333333">0"  ← length →  {escape(format_inches(stock.length))}"</text>'
    )
    parts.append(
        f'<text x="8" y="{PAD_TOP + board_h / 2:.1f}" font-family="sans-serif" '
        f'font-size="11" fill="#333333" transform="rotate(-90 8 {PAD_TOP + board_h / 2:.1f})">'
        f'0"  ← width →  {escape(format_inches(stock.width))}"</text>'
    )
    if exaggerated:
        parts.append(
            f'<text x="{PAD_LEFT:.1f}" y="{svg_h - 6:.1f}" font-family="sans-serif" '
            'font-size="9" fill="#666666">Width exaggerated for readability</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)
