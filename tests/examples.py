"""Paths to the two storm-window example files."""

from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
LIVE = EXAMPLES / "storm_window.yaml"
CRAFTSMANBLOG = EXAMPLES / "storm_window.craftsmanblog.yaml"
