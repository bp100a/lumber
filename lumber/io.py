"""Load optimization problems from YAML or JSON files.

A problem lists stock boards plus either handwritten ``cuts`` or ``windows``
(openings that expand into stiles and rails). Kerf defaults to 1/8".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from lumber.dimensions import parse_inches
from lumber.models import CutPiece, Problem, StockPiece
from lumber.windows import cuts_from_problem_data, parse_windows


def _load_raw(path: Path) -> dict[str, Any]:
    """Read a YAML or JSON mapping from disk."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    elif path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        raise ValueError(f"unsupported file type: {path.suffix}")
    if not isinstance(data, dict):
        raise ValueError("problem file must be a mapping at the top level")
    return data


def _parse_stock(items: list[dict[str, Any]]) -> list[StockPiece]:
    """Build stock boards from the ``stock:`` list in the problem file."""
    stock: list[StockPiece] = []
    for index, item in enumerate(items):
        stock_id = str(item.get("id") or f"board-{index + 1}")
        stock.append(
            StockPiece(
                id=stock_id,
                width=parse_inches(item["width"]),
                length=parse_inches(item["length"]),
                quantity=int(item.get("quantity", 1)),
            )
        )
    return stock


def _parse_cuts(items: list[dict[str, Any]]) -> list[CutPiece]:
    """Build handwritten cut pieces from the ``cuts:`` list."""
    cuts: list[CutPiece] = []
    for item in items:
        cuts.append(
            CutPiece(
                name=str(item["name"]),
                width=parse_inches(item["width"]),
                length=parse_inches(item["length"]),
                quantity=int(item.get("quantity", 1)),
            )
        )
    return cuts


def load_problem(path: str | Path) -> Problem:
    """Load stock, kerf, and either handwritten cuts or window-derived parts."""
    data = _load_raw(Path(path))
    kerf = parse_inches(data.get("kerf", "1/8"))
    stock = _parse_stock(data.get("stock") or [])
    has_windows = bool(data.get("windows"))
    has_cuts = bool(data.get("cuts"))
    if has_windows and has_cuts:
        raise ValueError("problem file has both 'windows' and 'cuts'; provide only one")
    if has_windows:
        cuts = cuts_from_problem_data(data)
        windows = parse_windows(data.get("windows") or [])
    else:
        cuts = _parse_cuts(data.get("cuts") or [])
        windows = []
    return Problem(stock=stock, cuts=cuts, kerf=kerf, windows=windows)
