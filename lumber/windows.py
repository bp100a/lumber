"""Derive storm-window cut pieces from opening measurements.

Each opening becomes two stiles plus top, meeting, and bottom rails. Frame
size is opening minus expansion; rails sit between the stiles. Also builds
the per-window cut tables and completion summary for shop reports.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from lumber.dimensions import parse_inches
from lumber.models import CutPiece, CutPlan, WindowOpening

_PART_KEYS = ("stile", "top_rail", "meeting_rail", "bottom_rail")
_PART_LABELS = {
    "stile": "Stiles",
    "top_rail": "Top Rail",
    "meeting_rail": "Meeting rail",
    "bottom_rail": "Bottom rail",
}


@dataclass(frozen=True)
class StormParts:
    """Finished widths for stile, top rail, meeting rail, and bottom rail."""
    stile: Fraction
    top_rail: Fraction
    meeting_rail: Fraction
    bottom_rail: Fraction


def stile_length(height: Fraction, expansion: Fraction) -> Fraction:
    """Stile length is opening height minus expansion."""
    return height - expansion


def rail_length(width: Fraction, expansion: Fraction, stile_width: Fraction) -> Fraction:
    """Rail sits between stiles; frame is opening minus expansion on each axis."""
    return width - expansion - 2 * stile_width


def cuts_for_window(
    window: WindowOpening,
    parts: StormParts,
    expansion: Fraction,
) -> list[CutPiece]:
    """Two stiles and three rails for one opening."""
    length = stile_length(window.height, expansion)
    rail = rail_length(window.width, expansion, parts.stile)
    if length <= 0:
        raise ValueError(
            f"window {window.id!r} stile length is not positive "
            f"(height {window.height} − expansion {expansion})"
        )
    if rail <= 0:
        raise ValueError(
            f"window {window.id!r} rail length is not positive "
            f"(width {window.width} − expansion {expansion} − 2 × stile {parts.stile})"
        )
    prefix = window.id
    return [
        CutPiece(
            name=f"{prefix} {_PART_LABELS['stile']}",
            width=parts.stile,
            length=length,
            quantity=2,
            window_id=prefix,
        ),
        CutPiece(
            name=f"{prefix} {_PART_LABELS['top_rail']}",
            width=parts.top_rail,
            length=rail,
            quantity=1,
            window_id=prefix,
        ),
        CutPiece(
            name=f"{prefix} {_PART_LABELS['meeting_rail']}",
            width=parts.meeting_rail,
            length=rail,
            quantity=1,
            window_id=prefix,
        ),
        CutPiece(
            name=f"{prefix} {_PART_LABELS['bottom_rail']}",
            width=parts.bottom_rail,
            length=rail,
            quantity=1,
            window_id=prefix,
        ),
    ]


def cuts_from_windows(
    windows: list[WindowOpening],
    parts: StormParts,
    expansion: Fraction,
) -> list[CutPiece]:
    """Expand every opening into cut pieces, in file order."""
    cuts: list[CutPiece] = []
    for window in windows:
        cuts.extend(cuts_for_window(window, parts, expansion))
    return cuts


def _part_width(parts: dict[str, Any], key: str) -> Fraction:
    if key not in parts:
        raise ValueError(f"parts.{key} is required when windows are listed")
    item = parts[key]
    if isinstance(item, dict):
        if "width" not in item:
            raise ValueError(f"parts.{key}.width is required")
        return parse_inches(item["width"])
    return parse_inches(item)


def parse_parts(raw: dict[str, Any] | None) -> StormParts:
    """Read ``parts:`` widths from the problem file."""
    if not raw:
        raise ValueError("parts is required when windows are listed")
    widths = {key: _part_width(raw, key) for key in _PART_KEYS}
    return StormParts(**widths)


def parse_windows(items: list[dict[str, Any]]) -> list[WindowOpening]:
    """Read ``windows:`` openings from the problem file."""
    windows: list[WindowOpening] = []
    for index, item in enumerate(items):
        meeting_raw = item.get("meeting")
        windows.append(
            WindowOpening(
                id=str(item.get("id") or f"window-{index + 1}"),
                height=parse_inches(item["height"]),
                width=parse_inches(item["width"]),
                meeting=parse_inches(meeting_raw) if meeting_raw is not None else None,
            )
        )
    return windows


def cuts_from_problem_data(data: dict[str, Any]) -> list[CutPiece]:
    """Build the full cut list from a problem mapping that has ``windows:``."""
    expansion = parse_inches(data.get("expansion", "1/4"))
    parts = parse_parts(data.get("parts"))
    windows = parse_windows(data.get("windows") or [])
    return cuts_from_windows(windows, parts, expansion)


@dataclass(frozen=True)
class WindowStatus:
    """How many planned pieces for one window are placed vs needed."""
    window_id: str
    placed: int
    needed: int

    @property
    def complete(self) -> bool:
        return self.placed >= self.needed and self.needed > 0


@dataclass(frozen=True)
class WindowCompletionSummary:
    """Per-window completion counts for the shop report header."""
    windows: tuple[WindowStatus, ...]

    @property
    def completed(self) -> int:
        return sum(1 for window in self.windows if window.complete)

    @property
    def total(self) -> int:
        return len(self.windows)


def summarize_window_completion(plan: CutPlan) -> WindowCompletionSummary | None:
    """How many window frames have every planned piece placed.

    Only applies when cuts carry ``window_id`` (derived from openings).
    """
    needed: dict[str, int] = defaultdict(int)
    placed: dict[str, int] = defaultdict(int)
    for placement in plan.placements:
        window_id = placement.cut.window_id
        if window_id:
            needed[window_id] += 1
            placed[window_id] += 1
    for cut in plan.unplaced:
        if cut.window_id:
            needed[cut.window_id] += 1
    if not needed:
        return None
    return WindowCompletionSummary(
        windows=tuple(
            WindowStatus(
                window_id=window_id,
                placed=placed.get(window_id, 0),
                needed=needed[window_id],
            )
            for window_id in sorted(needed)
        )
    )


def window_completion_lines(plan: CutPlan) -> list[str]:
    """Text lines: how many windows are complete, plus id lists."""
    summary = summarize_window_completion(plan)
    if summary is None:
        return []
    lines = [f"Windows completed: {summary.completed} of {summary.total}"]
    done = [w.window_id for w in summary.windows if w.complete]
    missing = [w.window_id for w in summary.windows if not w.complete]
    if done:
        lines.append("Complete: " + ", ".join(done))
    if missing:
        lines.append("Incomplete: " + ", ".join(missing))
    return lines


@dataclass(frozen=True)
class WindowCutRow:
    """One part line in a window table: name, length, width, quantity."""
    name: str
    length: Fraction
    width: Fraction
    quantity: int


@dataclass(frozen=True)
class WindowCutTable:
    """Opening size plus grouped parts for one window on the PDF."""
    window_id: str
    height: Fraction | None
    width: Fraction | None
    parts: tuple[WindowCutRow, ...]


_PART_RANK = {label: index for index, label in enumerate(_PART_LABELS.values())}


def _part_label(cut: CutPiece) -> str:
    if cut.window_id and cut.name.startswith(cut.window_id):
        return cut.name[len(cut.window_id) :].strip()
    return cut.name


def window_cut_tables(plan: CutPlan) -> list[WindowCutTable]:
    """Per-window bill of materials: opening size plus each part L × W × qty."""
    pieces: list[CutPiece] = [p.cut for p in plan.placements] + list(plan.unplaced)
    by_window: dict[str, list[CutPiece]] = defaultdict(list)
    for cut in pieces:
        if cut.window_id:
            by_window[cut.window_id].append(cut)
    if not by_window:
        return []

    openings = {window.id: window for window in plan.windows}
    order = [window.id for window in plan.windows]
    for window_id in sorted(by_window):
        if window_id not in order:
            order.append(window_id)

    tables: list[WindowCutTable] = []
    for window_id in order:
        cuts = by_window.get(window_id)
        if not cuts:
            continue
        counts: dict[tuple[str, Fraction, Fraction], int] = defaultdict(int)
        for cut in cuts:
            counts[(_part_label(cut), cut.length, cut.width)] += cut.quantity
        rows = [
            WindowCutRow(name=name, length=length, width=width, quantity=qty)
            for (name, length, width), qty in counts.items()
        ]
        rows.sort(key=lambda row: (_PART_RANK.get(row.name, 99), row.name, -row.length))
        opening = openings.get(window_id)
        tables.append(
            WindowCutTable(
                window_id=window_id,
                height=opening.height if opening else None,
                width=opening.width if opening else None,
                parts=tuple(rows),
            )
        )
    return tables
