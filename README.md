# Lumber Cut Optimizer

Takes **stock lumber** and either **window openings** or a handwritten **cut list**, then says **which cuts to take from which board**.

The shop workflow is **rip to width, then cross-cut to length**. Grain stays along the board; pieces are not rotated. All stock and cuts are **1" thick** (thickness is not an input). Kerf defaults to **1/8"** and is consumed on every extra rip and cross-cut.

The shop-facing deliverable is a **PDF**: instructions, board-face diagrams, windows completed, unused stock, and (when openings were used) a per-window cut table.

## Install

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+. From the repo root:

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
uv run lumber optimize examples/storm_window.yaml --kerf 1/8 -o plan.txt
uv run python -m lumber optimize examples/storm_window.yaml
```

- **PDF** is the shop report (instructions + diagrams + per-window tables). `-o` is required.
- **Markdown** also writes one sibling `.svg` per used board.
- If `-o` is set and `--format` is omitted, the format is inferred from the suffix (`.pdf`, `.md`, `.json`, `.txt`).

Exit code is `0` when every piece is placed, `1` when stock is insufficient (unplaced pieces are listed as `INSUFFICIENT STOCK`).

## Problem file

YAML or JSON. Dimensions are fractional inches (`4 3/4`, `1 11/16`, `1/8`). List either `windows` or `cuts`, not both.

### Windows (usual for storm frames)

Openings expand into stiles and rails. Stiles run full height; rails sit between the stiles. Default expansion is **1/4"** under the opening on both axes:

```
stile_length = height − expansion
rail_length  = width − expansion − 2 × stile_width
```

```yaml
kerf: "1/8"
expansion: "1/4"

parts:
  stile: { width: "2 1/8" }
  top_rail: { width: "2 1/8" }
  meeting_rail: { width: "1 1/4" }
  bottom_rail: { width: "3 1/2" }

stock:
  - id: board-a
    width: "7 3/8"
    length: "144"      # 12'
    quantity: 1

windows:
  - id: dining-west
    height: "62 1/2"
    width: "20 7/8"
    meeting: "31 1/2"  # glazing later; not used for lumber lengths
```

### Handwritten cuts

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

## Examples

**Live job:** `examples/storm_window.yaml` (same data in `.json`) — six openings (dining and living, west/middle/east) and eight boards (12', 10', and 8'). Stile and top-rail width is **2 1/8"**. That derives **30 pieces**; all place; **6 of 6** windows complete; waste about **30%** on used boards. Used: board-a, board-b, board-d, board-e. Unused leftover: board-c, board-f, board-g, board-h.

**Shortage fixture:** `examples/storm_window.craftsmanblog.yaml` — three 8' boards and a handwritten 15-piece list. **14 of 15** place; the 38 1/4" top rail is unplaced. Tests for gang-rip, whole-board cross-cut-first, and `INSUFFICIENT STOCK` use this file.

## How it works

1. Load the problem; if `windows` are listed, derive the cut list.
2. Pack by stock **length** (longest boards first). Strips of one width are packed along the blank, then assigned widest-first with the tightest remaining width (kerf between rips and cross-cuts).
3. On **12' and 10'** boards, through-cut 62 1/4" station blanks so rips are not full length (12': two stations + 19 1/4" leftover; 10': one station + 57 5/8" leftover). Small parts go in that leftover. **8'** stock stays rip-first / cross-cut-first / gang-rip.
4. Write shop instructions for each used board:
   - **Through-cut** when station blanks were packed
   - **Cross-cut first** when every piece on the board is the same length
   - **Gang-rip** when adjacent strips are same-length only
   - Otherwise **rip first**, then cross-cut
5. Report waste on **used boards only**, which windows are complete, and which stock was leftover.

Packing rules, formulas, and rebuild notes are in [`PLAN.md`](PLAN.md).

## Tests

```bash
uv run pytest
```
