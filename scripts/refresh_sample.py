"""Rebuild the frozen shop-report sample in docs/sample/.

Run from the repo root:

    uv run --with pymupdf python scripts/refresh_sample.py

PNG crops are the README figures. They stay unchanged until this script is run
on purpose.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from lumber.io import load_problem
from lumber.packer import optimize
from lumber.pdf import write_pdf

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "docs" / "sample"
PROBLEM = ROOT / "examples" / "storm_window.yaml"
PDF = SAMPLE / "storm_window.pdf"

# Letter-page crops in PDF points (origin top-left).
CUTS_BY_WINDOW = pymupdf.Rect(36, 36, 524, 552)
BOARD_A_HEIGHT = 360
SCALE = pymupdf.Matrix(2, 2)


def _line_top(page: pymupdf.Page, needle: str) -> float | None:
    """Top of the first text line that contains ``needle`` (PDF points from page top)."""
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"])
            if needle in text:
                return float(line["bbox"][1])
    return None


def _render(page: pymupdf.Page, clip: pymupdf.Rect, dest: Path) -> None:
    pix = page.get_pixmap(matrix=SCALE, clip=clip, alpha=False)
    dest.write_bytes(pix.tobytes("png"))


def main() -> None:
    SAMPLE.mkdir(parents=True, exist_ok=True)
    write_pdf(optimize(load_problem(PROBLEM)), PDF)
    doc = pymupdf.open(PDF)
    _render(doc[0], CUTS_BY_WINDOW, SAMPLE / "cuts-by-window.png")
    board_page = doc[1]
    board_top = _line_top(board_page, "board-a -") or 36
    board_clip = pymupdf.Rect(
        36,
        max(board_top - 6, 36),
        580,
        min(board_top - 6 + BOARD_A_HEIGHT, board_page.rect.height - 36),
    )
    _render(board_page, board_clip, SAMPLE / "board-a.png")
    doc.close()
    print(f"wrote {PDF.relative_to(ROOT)}")
    print("wrote docs/sample/cuts-by-window.png")
    print("wrote docs/sample/board-a.png")


if __name__ == "__main__":
    main()
