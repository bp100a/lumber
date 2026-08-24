"""Format cut plans for the shop."""

from __future__ import annotations

import json
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

from lumber.diagram import board_svg, diagram_filename
from lumber.dimensions import format_inches
from lumber.models import CutPlan, Placement, StockPiece
from lumber.sequence import board_instructions
from lumber.windows import summarize_window_completion, window_completion_lines


def _unused_stock(plan: CutPlan) -> list[StockPiece]:
    used = {p.stock_id for p in plan.placements}
    return [s for s in plan.stock if s.id not in used]


def unused_stock_line(plan: CutPlan) -> str | None:
    unused = _unused_stock(plan)
    if not unused:
        return None
    names = ", ".join(s.id for s in unused)
    return f"Unused stock: {names}"


def group_by_board(plan: CutPlan) -> dict[str, list[Placement]]:
    grouped: dict[str, list[Placement]] = defaultdict(list)
    for placement in plan.placements:
        grouped[placement.stock_id].append(placement)
    for placements in grouped.values():
        placements.sort(key=lambda p: (p.rip_offset, p.length_offset))
    return grouped


def _stock_lookup(plan: CutPlan) -> dict[str, tuple[Fraction, Fraction]]:
    return {s.id: (s.width, s.length) for s in plan.stock}


def format_text(plan: CutPlan) -> str:
    lines: list[str] = []
    stock_by_id = _stock_lookup(plan)
    grouped = group_by_board(plan)

    lines.append("LUMBER CUT PLAN")
    lines.append(f"Kerf: {format_inches(plan.kerf)}\"")
    lines.append("")

    for stock_id in sorted(grouped):
        width, length = stock_by_id[stock_id]
        lines.append(f"Board: {format_inches(width)}\" x 1\" x {format_inches(length)}\" ({stock_id})")
        stock = next(s for s in plan.stock if s.id == stock_id)
        layout = plan.board_layouts.get(stock_id)
        for indent, step in board_instructions(
            grouped[stock_id], stock, plan.kerf, layout=layout
        ):
            pad = "  " + "  " * indent
            lines.append(f"{pad}{step}")
        lines.append("")

    lines.append(f"Placed: {len(plan.placements)} pieces")
    lines.append(f"Waste: {format_inches(plan.waste_area)} sq in ({plan.waste_percent:.1f}%)")
    for line in window_completion_lines(plan):
        lines.append(line)
    unused = unused_stock_line(plan)
    if unused:
        lines.append(unused)

    if plan.unplaced:
        lines.append("")
        lines.append(f"INSUFFICIENT STOCK: {len(plan.unplaced)} piece(s) could not be placed")
        lines.append("UNPLACED:")
        for cut in plan.unplaced:
            label = cut.instance_id or cut.name
            lines.append(
                f"  {label}: {format_inches(cut.length)}\" x {format_inches(cut.width)}\""
            )

    return "\n".join(lines)


def format_json(plan: CutPlan) -> str:
    payload = {
        "kerf": format_inches(plan.kerf),
        "placements": [
            {
                "stock_id": p.stock_id,
                "cut": p.cut.name,
                "instance": p.cut.instance_id,
                "rip_offset": format_inches(p.rip_offset),
                "length_offset": format_inches(p.length_offset),
                "width": format_inches(p.cut.width),
                "length": format_inches(p.cut.length),
            }
            for p in plan.placements
        ],
        "unplaced": [
            {
                "cut": c.name,
                "instance": c.instance_id,
                "width": format_inches(c.width),
                "length": format_inches(c.length),
            }
            for c in plan.unplaced
        ],
        "placed": len(plan.placements),
        "waste_area": format_inches(plan.waste_area),
        "waste_percent": round(plan.waste_percent, 2),
    }
    summary = summarize_window_completion(plan)
    if summary is not None:
        payload["windows_completed"] = summary.completed
        payload["windows_total"] = summary.total
        payload["windows_complete"] = [w.window_id for w in summary.windows if w.complete]
        payload["windows_incomplete"] = [
            w.window_id for w in summary.windows if not w.complete
        ]
    unused_boards = _unused_stock(plan)
    if unused_boards:
        payload["unused_stock"] = [s.id for s in unused_boards]
    return json.dumps(payload, indent=2)


def format_markdown(plan: CutPlan, images: dict[str, str] | None = None) -> str:
    """Shop report: summary, per-board diagram image, and rip/cross-cut list.

    Markdown previews strip raw ``<svg>``, so diagrams are referenced as
    sibling image files (see ``write_markdown_report``).
    """
    stock_by_id = _stock_lookup(plan)
    grouped = group_by_board(plan)
    lines: list[str] = [
        "# Lumber cut plan",
        "",
        f'Kerf: {format_inches(plan.kerf)}"',
        f"Placed: {len(plan.placements)} pieces",
        f'Waste: {format_inches(plan.waste_area)} sq in ({plan.waste_percent:.1f}%)',
    ]
    lines.extend(window_completion_lines(plan))
    unused = unused_stock_line(plan)
    if unused:
        lines.append(unused)
    lines.append("")

    for stock_id in sorted(grouped):
        width, length = stock_by_id[stock_id]
        image = (images or {}).get(stock_id) or diagram_filename(stock_id)
        lines.append(
            f'## {stock_id} — {format_inches(width)}" × 1" × {format_inches(length)}"'
        )
        lines.append("")
        lines.append(f"![Cut diagram for {stock_id}]({image})")
        lines.append("")
        lines.append("### Cuts")
        stock = next(s for s in plan.stock if s.id == stock_id)
        layout = plan.board_layouts.get(stock_id)
        for indent, step in board_instructions(
            grouped[stock_id], stock, plan.kerf, layout=layout
        ):
            lines.append(f'{"  " * indent}- {step}')
        lines.append("")

    if plan.unplaced:
        lines.append("## Unplaced")
        lines.append("")
        lines.append(
            f"INSUFFICIENT STOCK: {len(plan.unplaced)} piece(s) could not be placed"
        )
        for cut in plan.unplaced:
            label = cut.instance_id or cut.name
            lines.append(
                f'- {label}: {format_inches(cut.length)}" × {format_inches(cut.width)}"'
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_markdown_report(plan: CutPlan, path: Path) -> None:
    """Write ``path`` plus one SVG diagram per used board in the same folder."""
    grouped = group_by_board(plan)
    stock_lookup = {s.id: s for s in plan.stock}
    images: dict[str, str] = {}
    for stock_id in sorted(grouped):
        name = diagram_filename(stock_id, prefix=path.stem)
        (path.parent / name).write_text(
            board_svg(
                stock_lookup[stock_id],
                grouped[stock_id],
                plan.kerf,
                layout=plan.board_layouts.get(stock_id),
            ),
            encoding="utf-8",
        )
        images[stock_id] = name
    path.write_text(format_markdown(plan, images=images), encoding="utf-8")
