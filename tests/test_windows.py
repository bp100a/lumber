from pathlib import Path

import pytest

from lumber.dimensions import parse_inches
from lumber.io import load_problem
from lumber.packer import optimize
from lumber.validate import expand_cuts
from lumber.windows import (
    StormParts,
    WindowOpening,
    cuts_from_windows,
    rail_length,
    stile_length,
    summarize_window_completion,
    window_completion_lines,
    window_cut_tables,
)

from tests.examples import CRAFTSMANBLOG, LIVE

CURRENT_PARTS = StormParts(
    stile=parse_inches("2 1/2"),
    top_rail=parse_inches("2 1/2"),
    meeting_rail=parse_inches("1 1/4"),
    bottom_rail=parse_inches("3 1/2"),
)
ORIGINAL_PARTS = StormParts(
    stile=parse_inches("1 11/16"),
    top_rail=parse_inches("1 11/16"),
    meeting_rail=parse_inches("1 1/4"),
    bottom_rail=parse_inches("2 9/16"),
)
EXPANSION = parse_inches("1/4")


def _dining_west() -> WindowOpening:
    return WindowOpening(
        id="dining-west",
        height=parse_inches("62 1/2"),
        width=parse_inches("20 7/8"),
        meeting=parse_inches("31 1/2"),
    )


def test_dining_west_lengths_with_current_stile_width() -> None:
    window = _dining_west()
    assert stile_length(window.height, EXPANSION) == parse_inches("62 1/4")
    assert rail_length(window.width, EXPANSION, CURRENT_PARTS.stile) == parse_inches(
        "15 5/8"
    )


def test_living_middle_rail_length() -> None:
    rail = rail_length(parse_inches("42"), EXPANSION, CURRENT_PARTS.stile)
    assert rail == parse_inches("36 3/4")


def test_six_windows_produce_thirty_pieces() -> None:
    problem = load_problem(LIVE)
    pieces = expand_cuts(problem.cuts)
    assert len(pieces) == 30


def test_original_stile_width_matches_first_cut_list() -> None:
    dining_west = rail_length(
        parse_inches("20 7/8"), EXPANSION, ORIGINAL_PARTS.stile
    )
    dining_middle = rail_length(
        parse_inches("41 7/8"), EXPANSION, ORIGINAL_PARTS.stile
    )
    assert dining_west == parse_inches("17 1/4")
    assert dining_middle == parse_inches("38 1/4")
    assert stile_length(parse_inches("62 1/2"), EXPANSION) == parse_inches("62 1/4")


def test_handwritten_cut_list_still_loads() -> None:
    problem = load_problem(CRAFTSMANBLOG)
    pieces = expand_cuts(problem.cuts)
    assert len(pieces) == 15
    assert {c.name for c in problem.cuts} >= {
        "Stiles",
        "Top Rail",
        "Meeting rail",
        "Bottom rail",
    }


def test_yaml_and_json_examples_match() -> None:
    yaml_problem = load_problem(LIVE)
    json_problem = load_problem(LIVE.with_suffix(".json"))
    yaml_cuts = {(c.name, c.width, c.length, c.quantity) for c in yaml_problem.cuts}
    json_cuts = {(c.name, c.width, c.length, c.quantity) for c in json_problem.cuts}
    assert yaml_cuts == json_cuts


def test_cuts_from_windows_labels_include_window_id() -> None:
    cuts = cuts_from_windows([_dining_west()], CURRENT_PARTS, EXPANSION)
    names = {c.name for c in cuts}
    assert "dining-west Stiles" in names
    assert "dining-west Top Rail" in names
    stile = next(c for c in cuts if c.name.endswith("Stiles"))
    top = next(c for c in cuts if c.name.endswith("Top Rail"))
    assert stile.quantity == 2
    assert stile.length == parse_inches("62 1/4")
    assert top.length == parse_inches("15 5/8")
    assert top.width == parse_inches("2 1/2")


def test_windows_and_cuts_together_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "both.yaml"
    path.write_text(
        "\n".join(
            [
                "stock:",
                '  - {id: board-1, width: "8", length: "96"}',
                "parts:",
                '  stile: {width: "2 1/2"}',
                '  top_rail: {width: "2 1/2"}',
                '  meeting_rail: {width: "1 1/4"}',
                '  bottom_rail: {width: "3 1/2"}',
                "windows:",
                '  - {id: w1, height: "62 1/2", width: "20 7/8"}',
                "cuts:",
                '  - {name: Stiles, length: "62 1/4", width: "2 1/2"}',
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="both"):
        load_problem(path)


def test_live_stock_completes_all_six_windows() -> None:
    plan = optimize(load_problem(LIVE))
    summary = summarize_window_completion(plan)
    assert summary is not None
    assert summary.total == 6
    assert summary.completed == 6
    assert plan.unplaced == []
    used = {p.stock_id for p in plan.placements}
    assert {"board-a", "board-b", "board-d", "board-e"} <= used
    assert "board-c" not in used
    lines = window_completion_lines(plan)
    assert lines[0] == "Windows completed: 6 of 6"
    assert plan.waste_percent < 35


def test_window_cut_tables_group_live_openings() -> None:
    plan = optimize(load_problem(LIVE))
    tables = window_cut_tables(plan)
    assert [t.window_id for t in tables] == [
        "dining-west",
        "dining-middle",
        "dining-east",
        "living-west",
        "living-middle",
        "living-east",
    ]
    dining_west = tables[0]
    assert dining_west.height == parse_inches("62 1/2")
    assert dining_west.width == parse_inches("20 7/8")
    parts = {row.name: row for row in dining_west.parts}
    assert parts["Stiles"].length == parse_inches("62 1/4")
    assert parts["Stiles"].width == parse_inches("2 1/8")
    assert parts["Stiles"].quantity == 2
    assert parts["Top Rail"].length == parse_inches("16 3/8")
    assert parts["Top Rail"].width == parse_inches("2 1/8")
    assert parts["Top Rail"].quantity == 1
    assert parts["Meeting rail"].width == parse_inches("1 1/4")
    assert parts["Bottom rail"].width == parse_inches("3 1/2")
    living_middle = next(t for t in tables if t.window_id == "living-middle")
    assert living_middle.width == parse_inches("42")
    rails = {row.name: row for row in living_middle.parts}
    assert rails["Top Rail"].length == parse_inches("37 1/2")


def test_handwritten_cuts_have_no_window_completion() -> None:
    plan = optimize(load_problem(CRAFTSMANBLOG))
    assert summarize_window_completion(plan) is None
    assert window_completion_lines(plan) == []
    assert window_cut_tables(plan) == []


def test_live_twelve_foot_boards_park_small_rails_in_remnant() -> None:
    plan = optimize(load_problem(LIVE))
    remnant_start = parse_inches("124 3/4")
    remnant_len = parse_inches("19 1/4")
    for stock_id in ("board-a", "board-b"):
        placed = [p for p in plan.placements if p.stock_id == stock_id]
        remnant_parts = [p for p in placed if p.length_offset >= remnant_start]
        for piece in remnant_parts:
            assert piece.cut.length <= remnant_len
        long_rails = [
            p
            for p in placed
            if p.cut.length >= parse_inches("36")
        ]
        for piece in long_rails:
            assert piece.length_offset < remnant_start
            assert piece.cut.length > remnant_len
