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
                                          "--report-lang", "uk"], "uk"),
                                        (["compare", "--topic", "meditation", "--languages", "de,en,fr"], "en"),
                                        (["portfolio", "--topics", "meditation,sleep", "--languages", "de,en,fr",
                                          "--report-lang", "uk"], "uk")])
def test_cli_pdf_writes_a_one_page_brief(run_cli, settings, capsys, args, lang):  # noqa: F811
    assert run_cli(*args) == 0
    folder = next(p for name in ("analysis.json", "comparison.json", "portfolio.json")
                  for p in settings.reports_dir.rglob(name)).parent
    capsys.readouterr()
    assert run_cli("pdf", str(folder)) == 0
    brief = folder / "brief.pdf"
    assert brief.is_file() and brief.read_bytes().startswith(b"%PDF") and _pages(brief) == 1


def _pages(path) -> int:
    import re
    return len(re.findall(rb"/Type\s*/Page(?!s)", path.read_bytes()))


def test_brief_is_exactly_one_page_and_full_is_longer(run_cli, settings):  # noqa: F811
    run_cli("analyze", "--topic", "meditation", "--language", "de")
    folder = next(settings.reports_dir.rglob("analysis.json")).parent
    assert run_cli("pdf", str(folder)) == 0 and run_cli("pdf", str(folder), "--full") == 0
    assert _pages(folder / "brief.pdf") == 1 and _pages(folder / "report.pdf") > 1


def test_cjk_text_uses_a_cjk_font():
    text = pdf._inline("A search finds 英語教育, 英語 and 영어")
    assert f'<font name="{pdf.CJK_FONT}">英語教育</font>' in text and f'<font name="{pdf.HANGUL_FONT}">영어</font>' in text


def test_cli_pdf_needs_a_report(run_cli, tmp_path):  # noqa: F811
    assert run_cli("pdf", str(tmp_path)) == 2
