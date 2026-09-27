"""`wiki-market pdf`: a saved report as an A4 PDF (reportlab), in the report's own language."""

import pytest

pytest.importorskip("reportlab")

from wiki_market_intel.reporting import pdf  # noqa: E402
from tests.reporting.test_end_to_end import run_cli  # noqa: E402,F401  (fixture)


def test_markdown_subset_becomes_flowables(tmp_path):
    from reportlab.platypus import Image, Paragraph, Table
    md = ("# Title\n\n_meta_\n\n## Section\n\n| A | B |\n|---|---:|\n| x | 1 |\n\n- one\n- two\n\n> note\n\n"
          "plain text\n\n![missing chart](charts/none.png)\n")
    items = pdf.flowables(md, tmp_path, 500)
    kinds = [type(i).__name__ for i in items]
    assert kinds.count("Paragraph") >= 6 and "Table" in kinds
    assert not any(isinstance(i, Image) for i in items)             # a missing image is skipped, not fatal
    assert isinstance(items[0], Paragraph) and isinstance(next(i for i in items if isinstance(i, Table)), Table)


def test_key_value_tables_have_no_empty_header(tmp_path):
    from reportlab.platypus import Table
    table = next(i for i in pdf.flowables("| | |\n|---|---|\n| Topic | Meditation |\n", tmp_path, 400)
                 if isinstance(i, Table))
    assert len(table._cellvalues) == 1                              # the blank header row is dropped


@pytest.mark.parametrize("args, lang", [(["analyze", "--topic", "meditation", "--language", "de"], "en"),
                                        (["analyze", "--topic", "meditation", "--language", "de",
                                          "--report-lang", "uk"], "uk")])
def test_cli_pdf_writes_report_pdf(run_cli, settings, capsys, args, lang):  # noqa: F811
    assert run_cli(*args) == 0
    folder = next(settings.reports_dir.rglob("analysis.json")).parent
    capsys.readouterr()
    assert run_cli("pdf", str(folder)) == 0
    out = folder / "report.pdf"
    assert out.is_file() and out.read_bytes().startswith(b"%PDF") and out.stat().st_size > 20_000
    assert "Wrote" in capsys.readouterr().out


def test_cli_pdf_needs_a_report(run_cli, tmp_path):  # noqa: F811
    assert run_cli("pdf", str(tmp_path)) == 2
