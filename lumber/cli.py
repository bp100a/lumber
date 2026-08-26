"""Command-line interface.

``lumber optimize <file>`` loads a problem, packs the cuts, and writes a
text, JSON, markdown, or PDF shop report. Format is inferred from ``-o``
when ``--format`` is omitted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lumber.dimensions import parse_inches
from lumber.io import load_problem
from lumber.packer import optimize
from lumber.report import format_json, format_markdown, format_text, write_markdown_report
from lumber.validate import validate_problem

_SUFFIX_FORMATS = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".markdown": "markdown",
    ".json": "json",
    ".txt": "text",
}


def _resolve_format(fmt: str, output: Path | None, explicit: bool) -> str:
    """Pick an output format from ``--format`` or the ``-o`` file suffix."""
    if output is None:
        return fmt
    inferred = _SUFFIX_FORMATS.get(output.suffix.lower())
    if inferred and not explicit:
        return inferred
    if inferred == "pdf" and fmt != "pdf":
        raise ValueError(
            f"refusing to write {fmt} data to {output.name}; use --format pdf"
        )
    return fmt


def main(argv: list[str] | None = None) -> int:
    """Parse argv, optimize the problem file, and write the shop report.

    Returns 1 if the problem is invalid or pieces remain unplaced.
    """
    parser = argparse.ArgumentParser(
        description="Optimize lumber usage: rip to width, cut to length.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    optimize_parser = sub.add_parser("optimize", help="Compute a cut plan from a problem file")
    optimize_parser.add_argument("problem", type=Path, help="YAML or JSON problem file")
    optimize_parser.add_argument(
        "--format",
        choices=("text", "json", "markdown", "md", "pdf"),
        default=None,
        help="Output format (default: text, or inferred from --output extension)",
    )
    optimize_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write plan to file instead of stdout",
    )
    optimize_parser.add_argument(
        "--kerf",
        help="Override kerf from the problem file (e.g. 1/8 or 3/16)",
    )

    args = parser.parse_args(argv)

    if args.command == "optimize":
        try:
            problem = load_problem(args.problem)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.kerf is not None:
            problem.kerf = parse_inches(args.kerf)
        errors = validate_problem(problem)
        if errors:
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            return 1

        explicit_format = args.format is not None
        try:
            fmt = _resolve_format(args.format or "text", args.output, explicit_format)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        plan = optimize(problem)
        if fmt == "pdf":
            if args.output is None:
                print("error: --output is required for PDF", file=sys.stderr)
                return 1
            from lumber.pdf import write_pdf

            write_pdf(plan, args.output)
        elif fmt in {"markdown", "md"}:
            if args.output:
                write_markdown_report(plan, args.output)
            else:
                print(format_markdown(plan), end="")
        else:
            output = format_json(plan) if fmt == "json" else format_text(plan)
            if args.output:
                args.output.write_text(output, encoding="utf-8")
            else:
                print(output)

        return 1 if plan.unplaced else 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
