"""Derive storm-window cut pieces from opening measurements."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from lumber.dimensions import parse_inches
from lumber.models import CutPiece, CutPlan

_PART_KEYS = ("stile", "top_rail", "meeting_rail", "bottom_rail")
_PART_LABELS = {
    "stile": "Stiles",
    "top_rail": "Top Rail",
    "meeting_rail": "Meeting rail",
    "bottom_rail": "Bottom rail",
}


@dataclass(frozen=True)
class StormParts:
    stile: Fraction
    top_rail: Fraction
    meeting_rail: Fraction
    bottom_rail: Fraction


@dataclass(frozen=True)
class WindowOpening:
    id: str
    height: Fraction
    width: Fraction
    meeting: Fraction | None = None


def stile_length(height: Fraction, expansion: Fraction) -> Fraction:
    return height - expansion


def rail_length(width: Fraction, expansion: Fraction, stile_width: Fraction) -> Fraction:
    """Rail sits between stiles; frame is opening minus expansion on each axis."""
    return width - expansion - 2 * stile_width


def cuts_for_window(
    window: WindowOpening,
    parts: StormParts,
    expansion: Fraction,
) -> list[CutPiece]:
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
    if not raw:
        raise ValueError("parts is required when windows are listed")
    widths = {key: _part_width(raw, key) for key in _PART_KEYS}
    return StormParts(**widths)


def parse_windows(items: list[dict[str, Any]]) -> list[WindowOpening]:
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
    expansion = parse_inches(data.get("expansion", "1/4"))
    parts = parse_parts(data.get("parts"))
    windows = parse_windows(data.get("windows") or [])
    return cuts_from_windows(windows, parts, expansion)


@dataclass(frozen=True)
class WindowStatus:
    window_id: str
    placed: int
    needed: int

    @property
    def complete(self) -> bool:
        return self.placed >= self.needed and self.needed > 0


@dataclass(frozen=True)
class WindowCompletionSummary:
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
