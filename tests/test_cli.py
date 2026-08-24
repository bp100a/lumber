from pathlib import Path

from lumber.cli import main

from tests.examples import CRAFTSMANBLOG, LIVE


def test_cli_writes_text_plan(tmp_path: Path) -> None:
    example = CRAFTSMANBLOG
    out = tmp_path / "plan.txt"
    rc = main(["optimize", str(example), "-o", str(out)])
    text = out.read_text(encoding="utf-8")
    assert rc == 1  # one piece unplaced
    assert "LUMBER CUT PLAN" in text
    assert "INSUFFICIENT STOCK" in text


def test_cli_json_and_kerf_override(tmp_path: Path) -> None:
    example = CRAFTSMANBLOG
    out = tmp_path / "plan.json"
    rc = main(["optimize", str(example), "--format", "json", "--kerf", "1/8", "-o", str(out)])
    assert rc == 1
    payload = out.read_text(encoding="utf-8")
    assert '"placed": 14' in payload
    assert "Top Rail" in payload


def test_cli_writes_markdown_plan(tmp_path: Path) -> None:
    example = CRAFTSMANBLOG
    out = tmp_path / "storm_window.md"
    rc = main(["optimize", str(example), "--format", "markdown", "-o", str(out)])
    text = out.read_text(encoding="utf-8")
    assert rc == 1
    assert text.startswith("# Lumber cut plan")
    assert "![Cut diagram for board-a]" in text
    assert (tmp_path / "storm_window-board-a.svg").is_file()
    assert "<svg" in (tmp_path / "storm_window-board-a.svg").read_text(encoding="utf-8")
    assert "## board-a" in text
    assert "INSUFFICIENT STOCK" in text

    rc_alias = main(["optimize", str(example), "--format", "md", "-o", str(out)])
    assert rc_alias == 1
    assert out.read_text(encoding="utf-8").startswith("# Lumber cut plan")


def test_cli_pdf_requires_output(capsys) -> None:
    example = LIVE
    rc = main(["optimize", str(example), "--format", "pdf"])
    assert rc == 1
    assert "required for PDF" in capsys.readouterr().err


def test_cli_writes_pdf(tmp_path: Path) -> None:
    example = CRAFTSMANBLOG
    out = tmp_path / "plan.pdf"
    rc = main(["optimize", str(example), "--format", "pdf", "-o", str(out)])
    assert rc == 1
    assert out.read_bytes().startswith(b"%PDF")


def test_cli_infers_pdf_from_output_extension(tmp_path: Path) -> None:
    example = CRAFTSMANBLOG
    out = tmp_path / "storm_window.pdf"
    rc = main(["optimize", str(example), "-o", str(out)])
    assert rc == 1
    assert out.read_bytes().startswith(b"%PDF")


def test_cli_refuses_markdown_into_pdf_path(tmp_path: Path, capsys) -> None:
    example = LIVE
    out = tmp_path / "storm_window.pdf"
    rc = main(["optimize", str(example), "--format", "markdown", "-o", str(out)])
    assert rc == 1
    assert "refusing to write" in capsys.readouterr().err
    assert not out.exists() or out.read_bytes()[:4] != b"# Lu"
