"""PDF report: the Markdown report as an A4 document, on request (`wiki-market pdf <report>`).

Uses reportlab (installed on first use by the skill launcher) and the DejaVu fonts that ship
with matplotlib, so Ukrainian (Cyrillic) renders. It reads the same Markdown subset as the
HTML converter: headings, pipe tables, bullet lists, block quotes, images, bold, italics, code.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

FONT, BOLD, MONO = "DejaVuSans", "DejaVuSans-Bold", "DejaVuSansMono"
INK, INK2, MUTED, LINE, ZEBRA, ACCENT = "#1f1e1c", "#52514e", "#898781", "#e1e0d9", "#f4f3ee", "#2a78d6"

_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\w*])_(?!\s)(.+?)(?<!\s)_(?![\w])")
_IMAGE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")


# DejaVu has no Chinese, Japanese or Korean glyphs; reportlab's built-in CID fonts do (no font files).
CJK_FONT, HANGUL_FONT = "HeiseiKakuGo-W5", "HYGothic-Medium"
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]+")
_HANGUL = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]+")


def _fonts() -> None:
    import matplotlib
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    if FONT in pdfmetrics.getRegisteredFontNames():
        return
    for cid in (CJK_FONT, HANGUL_FONT):
        pdfmetrics.registerFont(UnicodeCIDFont(cid))
    ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    for name, file in ((FONT, "DejaVuSans.ttf"), (BOLD, "DejaVuSans-Bold.ttf"), (MONO, "DejaVuSansMono.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(ttf / file)))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=BOLD, italic=FONT, boldItalic=BOLD)


def _inline(text: str) -> str:
    """Markdown inline marks -> reportlab paragraph markup (escaped)."""
    codes: list[str] = []

    def keep(m: re.Match) -> str:
        codes.append(f'<font name="{MONO}" size="7.5">{html.escape(m.group(1))}</font>')
        return f"\x00{len(codes) - 1}\x00"

    text = _CODE.sub(keep, text)
    text = html.escape(text, quote=False)
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _ITALIC.sub(rf'<font color="{INK2}">\1</font>', text)
    text = _CJK.sub(lambda m: f'<font name="{CJK_FONT}">{m.group(0)}</font>', text)
    text = _HANGUL.sub(lambda m: f'<font name="{HANGUL_FONT}">{m.group(0)}</font>', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def _styles():
    from reportlab.lib.styles import ParagraphStyle
    base = ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12.5, textColor=INK, spaceAfter=4)
    return {
        "body": base,
        "h1": ParagraphStyle("h1", parent=base, fontName=BOLD, fontSize=17, leading=21, spaceAfter=6, keepWithNext=1),
        "h2": ParagraphStyle("h2", parent=base, fontName=BOLD, fontSize=12.5, leading=16, spaceBefore=12, spaceAfter=5,
                             keepWithNext=1),
        "h3": ParagraphStyle("h3", parent=base, fontName=BOLD, fontSize=10, leading=13, spaceBefore=8,
                             textColor=INK2, keepWithNext=1),
        "meta": ParagraphStyle("meta", parent=base, fontSize=8, leading=11, textColor=MUTED),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=12, bulletIndent=2, spaceAfter=2),
        "quote": ParagraphStyle("quote", parent=base, leftIndent=10, textColor=INK2, borderPadding=(4, 6, 4, 6),
                                borderColor=ACCENT, borderWidth=0, backColor=ZEBRA),
        "cell": ParagraphStyle("cell", parent=base, fontSize=7.5, leading=9.5, spaceAfter=0),
        "cell_num": ParagraphStyle("cell_num", parent=base, fontSize=7.5, leading=9.5, spaceAfter=0, alignment=2),
        "head": ParagraphStyle("head", parent=base, fontName=BOLD, fontSize=7.5, leading=9.5, spaceAfter=0,
                               textColor=INK2),
    }


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table(lines: list[str], width: float, st):
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle
    header, spec, body = _cells(lines[0]), _cells(lines[1]), [_cells(l) for l in lines[2:]]
    n = len(header)
    right = [s.endswith(":") for s in spec] + [False] * n
    body = [row + [""] * (n - len(row)) for row in body]
    size = 7.5 if n <= 6 else 6.5 if n <= 9 else 6       # wide tables get a smaller font

    def style(name: str):
        s = st[name].clone(name + str(size))
        s.fontSize, s.leading = size, size + 2
        return s

    has_header = any(header)            # "| | |" tables are key/value lists without a header
    data = [[Paragraph(_inline(h), style("head")) for h in header]] if has_header else []
    data += [[Paragraph(_inline(c), style("cell_num" if right[i] else "cell")) for i, c in enumerate(row)] for row in body]
    # column widths in proportion to content length, within limits
    lengths = [max([len(header[i])] + [len(r[i]) for r in body]) for i in range(n)]
    lengths = [min(max(l, 6), 90) for l in lengths]
    total = sum(lengths)
    widths = [width * l / total for l in lengths]
    table = Table(data, colWidths=widths, repeatRows=1 if has_header else 0, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(ZEBRA if has_header else "#ffffff")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def flowables(md: str, base_dir: Path, width: float) -> list:
    from reportlab.platypus import Image, Paragraph, Spacer
    _fonts()
    st = _styles()
    out: list = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if heading:
            out.append(Paragraph(_inline(heading.group(2)), st[f"h{len(heading.group(1))}"]))
            i += 1
        elif stripped.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            if len(block) >= 2:
                out += [_table(block, width, st), Spacer(1, 6)]
        elif stripped.startswith("- "):
            while i < len(lines) and lines[i].strip().startswith("- "):
                out.append(Paragraph(_inline(lines[i].strip()[2:]), st["bullet"], bulletText="•"))
                i += 1
            out.append(Spacer(1, 3))
        elif stripped.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(Paragraph(" ".join(_inline(q) for q in quote if q), st["quote"]))
        elif _IMAGE.match(stripped):
            src = Path(base_dir) / _IMAGE.match(stripped).group(2)
            if src.is_file():
                img = Image(str(src))
                scale = min(1.0, width / img.imageWidth)
                img.drawWidth, img.drawHeight = img.imageWidth * scale, img.imageHeight * scale
                out += [Spacer(1, 4), img, Spacer(1, 6)]
            i += 1
        elif stripped.startswith("_") and stripped.endswith("_") and len(stripped) > 2:
            out.append(Paragraph(_inline(stripped[1:-1]), st["meta"]))
            i += 1
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||- |>|!\[)", lines[i].strip()):
                para.append(lines[i].strip())
                i += 1
            out.append(Paragraph(_inline(" ".join(para)), st["body"]))
    return out


FOOTER = {"en": "Page {page} · Wikipedia pageviews measure reader attention, not revenue or product demand.",
          "uk": "Сторінка {page} · Перегляди Вікіпедії вимірюють увагу читачів, а не виручку чи попит на продукт."}


def write(md_path: Path, lang: str = "en") -> Path:
    """report.md -> report.pdf in the same folder (images next to the report are embedded)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    _fonts()
    md_path = Path(md_path)
    out = md_path.with_suffix(".pdf")
    md = md_path.read_text("utf-8")
    first = re.search(r"^#\s+(.*)$", md, flags=re.MULTILINE)
    margin = 16 * mm
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=margin,
                            bottomMargin=margin + 4 * mm, title=first.group(1) if first else "Report",
                            author="wiki-market-intel")
    footer = FOOTER.get(lang, FOOTER["en"])

    def on_page(canvas, document):
        canvas.saveState()
        canvas.setFont(FONT, 7)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(margin, 9 * mm, footer.format(page=document.page))
        canvas.restoreState()

    doc.build(flowables(md, md_path.parent, doc.width), onFirstPage=on_page, onLaterPages=on_page)
    return out


# ---------------------------------------------------------------------------
# one-page brief (the shareable summary the brief asks for)
# ---------------------------------------------------------------------------

BRIEF_TEXT = {
    "en": {"rec": "Recommendation", "kpi": "KPI breakdown", "full": "Full report with every section: report.html "
           "(same folder). Source: Wikimedia Analytics API pageviews (user agent), {start} to {end}; generated {at}."},
    "uk": {"rec": "Рекомендація", "kpi": "Розбивка за показниками", "full": "Повний звіт з усіма розділами: "
           "report.html (та сама папка). Джерело: перегляди Wikimedia Analytics API (користувачі), з {start} по {end}; "
           "створено {at}."},
}


def _brief_content(folder: Path):
    """(lang, title, meta dict, recommendation lines, kpi rows or lines, chart path) from a saved report."""
    import json
    from wiki_market_intel.analytics import recommend
    from wiki_market_intel.i18n import Translator
    from wiki_market_intel.models.analysis import AnalysisResult, ComparisonResult, PortfolioResult
    from wiki_market_intel.reporting import breakdown, markdown

    folder = Path(folder)
    for name, model in (("analysis.json", AnalysisResult), ("comparison.json", ComparisonResult),
                        ("portfolio.json", PortfolioResult)):
        if (folder / name).is_file():
            result = model.model_validate(json.loads((folder / name).read_text("utf-8")))
            break
    else:
        raise FileNotFoundError(f"no analysis.json, comparison.json or portfolio.json in {folder}")
    lang = result.metadata.report_language
    tr = Translator(lang)
    meta = {"start": result.metadata.period_start, "end": result.metadata.period_end,
            "at": result.metadata.generated_at[:10]}
    if isinstance(result, AnalysisResult):
        title = f"{result.topic.article_title or result.metadata.topic} · {result.metadata.project}"
        rec = result.recommendation or recommend.of_analysis(result)
        reasons = {m.metric: m for m in result.quality.missing_metrics}

        def missing(metric):
            from wiki_market_intel.i18n import reason_text
            m = reasons.get(metric)
            return tr("sig_missing", reason=reason_text(m, tr).rstrip(".")) if m else tr("na")

        rows = breakdown.analysis_rows(result, tr, missing, markdown._quality_reasons(result, tr))
        kpis = [(k, v, _short(r)) for k, v, r in rows]
        chart = folder / "charts" / "trend.png"
    elif isinstance(result, ComparisonResult):
        title = f"{result.resolution.canonical_topic or result.metadata.topic} · " + \
                ", ".join(f"{l}.wikipedia" for l in result.metadata.languages)
        rec = result.recommendation or recommend.of_comparison(result)
        kpis = breakdown.multi_lines(breakdown.comparison_units(result), tr)
        chart = folder / "charts" / "opportunity.png"
    else:
        title = tr("pf_title", name=result.metadata.name)
        rec = result.recommendation or recommend.of_portfolio(result)
        kpis = breakdown.multi_lines(breakdown.portfolio_units(result), tr)
        chart = folder / "charts" / "portfolio.png"
    return lang, title, meta, recommend.sentences(rec, tr), kpis, (chart if chart.is_file() else None)


def _short(reading: str, limit: int = 110) -> str:
    """The first sentence of a KPI reading, for the one-page table."""
    first = reading.split(". ")[0].rstrip(".")
    return first if len(first) <= limit else first[: limit - 1].rstrip() + "…"


def _brief_story(lang, title, meta, rec_lines, kpis, chart, width, chart_mm, max_points):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle
    st = _styles()
    text = BRIEF_TEXT.get(lang, BRIEF_TEXT["en"])
    small = st["body"].clone("small")
    small.fontSize, small.leading = 8, 10.5
    story = [Paragraph(_inline(title), st["h1"]),
             Paragraph(_inline(text["full"].format(**meta)), st["meta"]), Spacer(1, 4),
             Paragraph(text["rec"], st["h2"]), Paragraph(f"<b>{_inline(rec_lines[0])}</b>", st["body"])]
    points = rec_lines[1:-1]
    shown = points[:max_points]
    story += [Paragraph(_inline(p), small, bulletText="•") for p in shown]
    story.append(Paragraph(_inline(rec_lines[-1]), st["meta"]))
    story += [Paragraph(text["kpi"], st["h2"])]
    if kpis and isinstance(kpis[0], tuple):
        data = [[Paragraph(_inline(k), st["cell"]), Paragraph(_inline(v), st["cell"]), Paragraph(_inline(r), st["cell"])]
                for k, v, r in kpis]
        table = Table(data, colWidths=[width * 0.27, width * 0.25, width * 0.48], hAlign="LEFT")
        table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor(LINE)),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        story.append(table)
    else:
        story += [Paragraph(_inline(line), small, bulletText="•") for line in kpis]
    if chart and chart_mm:
        img = Image(str(chart))
        scale = min(width / img.imageWidth, chart_mm * mm / img.imageHeight)
        img.drawWidth, img.drawHeight = img.imageWidth * scale, img.imageHeight * scale
        story += [Spacer(1, 4), img]
    return story


def write_brief(folder: Path) -> Path:
    """A one-page A4 summary (recommendation, KPI breakdown, main chart) -> brief.pdf in the report folder.
    Shrinks the chart, then trims the recommendation points, until it fits on one page."""
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    _fonts()
    folder = Path(folder)
    lang, title, meta, rec_lines, kpis, chart = _brief_content(folder)
    margin = 14 * mm
    footer = FOOTER.get(lang, FOOTER["en"]).split(" · ", 1)[1]

    def on_page(canvas, document):
        canvas.saveState()
        canvas.setFont(FONT, 7)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(margin, 8 * mm, footer)
        canvas.restoreState()

    attempts = [(chart_mm, points) for points in (6, 4, 3, 2) for chart_mm in (85, 70, 55, 40)] + [(0, 2)]
    for chart_mm, points in attempts:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=margin,
                                bottomMargin=margin, title=title, author="wiki-market-intel")
        doc.build(_brief_story(lang, title, meta, rec_lines, kpis, chart, doc.width, chart_mm, points),
                  onFirstPage=on_page, onLaterPages=on_page)
        if doc.page == 1:
            out = folder / "brief.pdf"
            out.write_bytes(buffer.getvalue())
            return out
    raise RuntimeError("the summary does not fit on one page")
