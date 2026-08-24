# Lumber Cut Optimizer

Given an inventory of lumber and a list of pieces to cut, this tool decides **which cuts to take from which board** using a rip-to-width, cross-cut-to-length workflow.

All stock and cuts are assumed to be **1" thick**.

## Install

Requires [uv](https://docs.astral.sh/uv/). Then from the repo root:

```bash
uv sync
```

That creates `.venv`, installs the package in editable mode, and installs the `dev` group (pytest).

## Usage

```bash
uv run lumber optimize examples/storm_window.yaml
uv run lumber optimize examples/storm_window.yaml --format json
uv run lumber optimize examples/storm_window.yaml --format pdf -o storm_window.pdf
uv run lumber optimize examples/storm_window.yaml --format markdown -o storm_window.md
# PDF is the shop report (instructions + diagrams). Markdown also writes sibling .svg files.
uv run lumber optimize examples/storm_window.yaml --kerf 1/8 -o plan.txt
uv run python -m lumber optimize examples/storm_window.yaml
```

Exit code is `0` when every piece is placed, `1` when stock is insufficient (unplaced pieces are listed).

## Problem file format

```yaml
kerf: "1/8"

stock:
  - id: board-a
    width: "4 3/4"
    length: "97 1/2"
    quantity: 1

cuts:
  - name: Stiles
    length: "62 1/4"
    width: "1 11/16"
    quantity: 4
```

Dimensions use fractional inches (`4 3/4`, `1 11/16`, etc.).

## How it works

1. Expand stock and cuts by quantity
2. Group cuts by finished width and pack lengths onto rip strips (kerf between cross-cuts)
3. Assign those strips to boards, widest first (kerf between rips)
4. Report per-board rip and cross-cut instructions, waste, and any unplaced cuts

The worked example is `examples/storm_window.yaml`: two small storm windows plus one larger window. With the three listed boards, 14 of 15 pieces fit; the remaining 38 1/4" top rail is reported as insufficient stock. See `PLAN.md` for the packing rules and why that piece does not fit.

## Tests

```bash
uv run pytest
```
