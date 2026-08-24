"""Per-board shop sequence: rip-first, cross-cut-first, gang-rip, or through-cut."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction

from lumber.dimensions import format_inches
from lumber.layout import common_length, resolve_board_layout
from lumber.models import BoardLayout, CutMode, Placement, StationPlan, StockPiece


@dataclass(frozen=True)
class RipStrip:
    """Placements that share one rip offset (one finished strip width)."""

    rip_offset: Fraction
    width: Fraction
    placements: tuple[Placement, ...]

    @property
    def shared_length(self) -> Fraction | None:
        lengths = {p.cut.length for p in self.placements}
        if len(lengths) != 1:
            return None
        return next(iter(lengths))

    @property
    def gang_eligible(self) -> bool:
        """One finished length, one station — no other parts on the strip."""
        if self.shared_length is None or not self.placements:
            return False
        return len({p.length_offset for p in self.placements}) == 1


def shared_length(placements: list[Placement]) -> Fraction | None:
    """Return the common finished length, or None if lengths differ or empty."""
    return common_length(placements)


def is_crosscut_first(placements: list[Placement]) -> bool:
    return common_length(placements) is not None


def collect_strips(placements: list[Placement]) -> list[RipStrip]:
    by_rip: dict[Fraction, list[Placement]] = defaultdict(list)
    for placement in placements:
        by_rip[placement.rip_offset].append(placement)
    strips: list[RipStrip] = []
    for rip_offset in sorted(by_rip):
        group = tuple(sorted(by_rip[rip_offset], key=lambda p: p.length_offset))
        strips.append(
            RipStrip(
                rip_offset=rip_offset,
                width=group[0].cut.width,
                placements=group,
            )
        )
    return strips


def _adjacent(left: RipStrip, right: RipStrip, kerf: Fraction) -> bool:
    gap = right.rip_offset - (left.rip_offset + left.width)
    return Fraction(0) <= gap <= kerf


def next_strip_run(
    strips: list[RipStrip],
    start: int,
    kerf: Fraction,
) -> list[RipStrip]:
    """Maximal adjacent same-length gang from ``start``, or a single strip."""
    first = strips[start]
    if not first.gang_eligible:
        return [first]
    run = [first]
    index = start + 1
    while index < len(strips):
        nxt = strips[index]
        if (
            nxt.gang_eligible
            and nxt.shared_length == first.shared_length
            and _adjacent(run[-1], nxt, kerf)
        ):
            run.append(nxt)
            index += 1
        else:
            break
    return run


def iter_strip_runs(
    placements: list[Placement],
    kerf: Fraction,
) -> list[list[RipStrip]]:
    """Partition strips into gangs (len >= 2) and singleton rip strips."""
    strips = collect_strips(placements)
    runs: list[list[RipStrip]] = []
    index = 0
    while index < len(strips):
        run = next_strip_run(strips, index, kerf)
        if len(run) >= 2:
            runs.append(run)
            index += len(run)
        else:
            runs.append([strips[index]])
            index += 1
    return runs


def gang_combined_width(gang: list[RipStrip]) -> Fraction:
    return gang[-1].rip_offset + gang[-1].width - gang[0].rip_offset


def length_offcut(
    stock_length: Fraction,
    blank_end: Fraction,
    kerf: Fraction,
    offcut_width: Fraction,
) -> tuple[Fraction, Fraction] | None:
    """Offcut after a through length cut ending at ``blank_end``."""
    used = blank_end + kerf
    if used >= stock_length:
        remnant = stock_length - blank_end
        if remnant <= 0:
            return None
        return remnant, offcut_width
    remnant = stock_length - used
    if remnant <= 0:
        return None
    return remnant, offcut_width


def offcut_after_crosscut(
    stock: StockPiece,
    blank_end: Fraction,
    kerf: Fraction,
) -> tuple[Fraction, Fraction] | None:
    """Full-width offcut after through cross-cuts ending at ``blank_end``."""
    return length_offcut(stock.length, blank_end, kerf, stock.width)


def board_instructions(
    placements: list[Placement],
    stock: StockPiece,
    kerf: Fraction,
    layout: BoardLayout | None = None,
) -> list[tuple[int, str]]:
    """Shop steps as (indent, line) pairs. Indent 0 is a top-level step."""
    resolved = layout or resolve_board_layout(placements, stock, kerf)
    if resolved.mode is CutMode.THROUGH_CROSSCUT and resolved.station is not None:
        return _through_crosscut_instructions(
            placements, stock, kerf, resolved.station
        )
    if resolved.mode is CutMode.CROSSCUT_FIRST:
        length = common_length(placements)
        assert length is not None
        return _crosscut_first_instructions(placements, stock, kerf, length)
    return _rip_first_instructions(placements, stock, kerf)


def _through_crosscut_instructions(
    placements: list[Placement],
    stock: StockPiece,
    kerf: Fraction,
    plan: StationPlan,
) -> list[tuple[int, str]]:
    steps: list[tuple[int, str]] = [
        (0, "Sequence: through cross-cut (shorten long rips)"),
    ]
    station_parts = [p for p in placements if p.length_offset < plan.remnant_start]
    remnant_parts = [p for p in placements if p.length_offset >= plan.remnant_start]

    unit = plan.station + kerf
    by_station: dict[Fraction, list[Placement]] = defaultdict(list)
    for placement in station_parts:
        start = (placement.length_offset // unit) * unit
        by_station[start].append(placement)

    for index, offset in enumerate(sorted(by_station)):
        blank = chr(ord("A") + index)
        steps.append(
            (
                0,
                f'Cross-cut @ {format_inches(offset)}" + {format_inches(plan.station)}" '
                f"-> blank {blank}",
            )
        )
        group = by_station[offset]
        if common_length(group) == plan.station:
            for placement in sorted(group, key=lambda p: p.rip_offset):
                label = placement.cut.instance_id or placement.cut.name
                steps.append(
                    (
                        1,
                        f'Rip @ {format_inches(placement.rip_offset)}" -> '
                        f'{format_inches(placement.cut.width)}" -> {label}',
                    )
                )
        else:
            for strip in collect_strips(group):
                for indent, line in _strip_rip_first_instructions(strip):
                    steps.append((indent + 1, line))

    steps.append(
        (
            0,
            f'Leftover blank: {format_inches(plan.remnant_length)}" x '
            f'{format_inches(stock.width)}"',
        )
    )
    if remnant_parts:
        for strip in collect_strips(remnant_parts):
            for indent, line in _strip_rip_first_instructions(strip):
                steps.append((indent + 1, line))
    else:
        steps.append((1, "(empty)"))
    return steps


def _rip_first_instructions(
    placements: list[Placement],
    stock: StockPiece,
    kerf: Fraction,
) -> list[tuple[int, str]]:
    runs = iter_strip_runs(placements, kerf)
    steps: list[tuple[int, str]] = []
    header_emitted = False
    for run in runs:
        if len(run) >= 2:
            if not header_emitted:
                steps.extend(_gang_header(run))
                header_emitted = True
            steps.extend(_gang_instructions(run, stock, kerf))
        else:
            steps.extend(_strip_rip_first_instructions(run[0]))
    return steps


def _strip_rip_first_instructions(strip: RipStrip) -> list[tuple[int, str]]:
    steps: list[tuple[int, str]] = [
        (
            0,
            f'Rip @ {format_inches(strip.rip_offset)}" -> '
            f'{format_inches(strip.width)}" strip',
        )
    ]
    for placement in strip.placements:
        label = placement.cut.instance_id or placement.cut.name
        steps.append(
            (
                1,
                f'Cross-cut @ {format_inches(placement.length_offset)}" '
                f'+ {format_inches(placement.cut.length)}" -> {label}',
            )
        )
    return steps


def _gang_header(gang: list[RipStrip]) -> list[tuple[int, str]]:
    length = gang[0].shared_length
    assert length is not None
    labels = [p.cut.instance_id or p.cut.name for strip in gang for p in strip.placements]
    return [
        (
            0,
            f"Sequence: gang-rip {_join_part_labels(labels)} "
            f'(same length {format_inches(length)}")',
        )
    ]


def _gang_instructions(
    gang: list[RipStrip],
    stock: StockPiece,
    kerf: Fraction,
) -> list[tuple[int, str]]:
    length = gang[0].shared_length
    assert length is not None
    combined = gang_combined_width(gang)
    noun = "pair" if len(gang) == 2 else "gang"
    offset = min(p.length_offset for strip in gang for p in strip.placements)
    blank_end = max(
        p.length_offset + p.cut.length for strip in gang for p in strip.placements
    )
    steps: list[tuple[int, str]] = [
        (
            0,
            f'Rip @ {format_inches(gang[0].rip_offset)}" -> '
            f'{format_inches(combined)}" {noun} strip',
        ),
        (
            1,
            f'Cross-cut @ {format_inches(offset)}" + {format_inches(length)}" '
            f"-> {noun} blank",
        ),
    ]
    for strip in gang:
        for placement in strip.placements:
            label = placement.cut.instance_id or placement.cut.name
            steps.append(
                (
                    2,
                    f'Rip @ {format_inches(placement.rip_offset)}" -> '
                    f'{format_inches(placement.cut.width)}" -> {label}',
                )
            )
    offcut = length_offcut(stock.length, blank_end, kerf, combined)
    if offcut:
        offcut_len, offcut_w = offcut
        steps.append(
            (
                1,
                f'Offcut: {format_inches(offcut_len)}" x '
                f'{format_inches(offcut_w)}"',
            )
        )
    return steps


def _join_part_labels(labels: list[str]) -> str:
    prefixes: list[str] = []
    tails: list[str] = []
    for label in labels:
        if " #" in label:
            name, number = label.rsplit(" #", 1)
            prefixes.append(name)
            tails.append(f"#{number}")
        else:
            return _join_and(labels)
    if len(set(prefixes)) == 1:
        return f"{prefixes[0]} {_join_and(tails)}"
    return _join_and(labels)


def _join_and(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def _crosscut_first_instructions(
    placements: list[Placement],
    stock: StockPiece,
    kerf: Fraction,
    length: Fraction,
) -> list[tuple[int, str]]:
    steps: list[tuple[int, str]] = [
        (0, f'Sequence: cross-cut first (all parts {format_inches(length)}")'),
    ]
    by_station: dict[Fraction, list[Placement]] = defaultdict(list)
    for placement in placements:
        by_station[placement.length_offset].append(placement)

    for index, offset in enumerate(sorted(by_station)):
        blank = chr(ord("A") + index)
        steps.append(
            (
                0,
                f'Cross-cut @ {format_inches(offset)}" + {format_inches(length)}" '
                f"-> blank {blank}",
            )
        )
        group = sorted(by_station[offset], key=lambda p: p.rip_offset)
        for placement in group:
            label = placement.cut.instance_id or placement.cut.name
            steps.append(
                (
                    1,
                    f'Rip @ {format_inches(placement.rip_offset)}" -> '
                    f'{format_inches(placement.cut.width)}" -> {label}',
                )
            )

    blank_end = max(p.length_offset + p.cut.length for p in placements)
    offcut = offcut_after_crosscut(stock, blank_end, kerf)
    if offcut:
        offcut_len, offcut_w = offcut
        steps.append(
            (
                0,
                f'Offcut: {format_inches(offcut_len)}" x '
                f'{format_inches(offcut_w)}" (full width)',
            )
        )
    return steps
