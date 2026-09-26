#!/usr/bin/env python3
"""
Charts and a one-page, shareable PDF.

Two outputs:
  * chart PNG  - can be shown inline in a chat as well as embedded in the PDF
  * report PDF - a single A4 page: findings, chart, metrics table, limitations

Non-Latin titles are the norm here (Астрономія, Přerušovaný půst), and reportlab's
built-in fonts are Latin-1 only, so a Unicode TrueType font is registered first.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Keep matplotlib's cache inside the skill; otherwise it warns on read-only homes.
os.environ.setdefault(
    "MPLCONFIGDIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache", "mpl"),
)
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)

try:
    import matplotlib
    matplotlib.use("Agg")  # no display needed
    import matplotlib.pyplot as plt
    import matplotlib.ticker
    from matplotlib import font_manager
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except ImportError as exc:  # pragma: no cover - environment problem, not logic
    sys.stderr.write(
        f"Missing dependency: {exc}\n"
        "Install the skill's requirements:  python3 -m pip install -r requirements.txt\n"
    )
    raise SystemExit(3)

ACCENT = colors.HexColor("#1f4788")
MUTED = colors.HexColor("#5b6470")
PALETTE = ["#1f4788", "#c1442e", "#2e7d5b", "#8a5fbf", "#b5851f", "#3d7ea6", "#9c3d6b"]

_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"


def _register_unicode_font() -> None:
    """Use matplotlib's bundled DejaVu Sans so Cyrillic and diacritics render.

    Reusing a font that ships with an existing dependency avoids committing a
    binary asset while still covering Cyrillic, Greek and Central European scripts.
    """
    global _FONT, _FONT_BOLD
    if _FONT != "Helvetica":
        return
    try:
        regular = font_manager.findfont("DejaVu Sans", fallback_to_default=False)
        folder = os.path.dirname(regular)
        bold = os.path.join(folder, "DejaVuSans-Bold.ttf")
        pdfmetrics.registerFont(TTFont("DejaVuSans", regular))
        _FONT = "DejaVuSans"
        if os.path.exists(bold):
            pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold))
            _FONT_BOLD = "DejaVuSans-Bold"
        else:
            _FONT_BOLD = "DejaVuSans"
        pdfmetrics.registerFontFamily("DejaVuSans", normal="DejaVuSans", bold=_FONT_BOLD)
    except Exception as exc:  # pragma: no cover
        sys.stderr.write(
            f"Note: Unicode font unavailable ({exc}); non-Latin titles may not render in the PDF.\n"
        )


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------

def make_chart(results: List[Dict[str, Any]], title: str, path: str, normalise: bool = False) -> Optional[str]:
    """Time series of monthly views per series, with spike months marked.

    normalise=True plots views per million edition views instead of raw counts,
    which is the only fair way to put a large and a small edition on one axis.
    """
    usable = [r for r in results if r.get("status") == "ok" and r.get("series")]
    if not usable:
        return None

    figure, axis = plt.subplots(figsize=(9.2, 3.5), dpi=140)
    plotted = 0
    for index, result in enumerate(usable):
        months = [p["month"] for p in result["series"]]
        views = [p["views"] for p in result["series"]]
        if normalise:
            factor = result["volume"].get("per_million_edition_views")
            median = result["volume"]["median_monthly"] or 1
            if not factor:
                continue
            views = [v / median * factor for v in views]
        colour = PALETTE[index % len(PALETTE)]
        axis.plot(months, views, marker="o", markersize=2.5, linewidth=1.6,
                  color=colour, label=result["label"])
        spikes = set(result["quality"]["spike_months"])
        spike_x = [m for m in months if m in spikes]
        spike_y = [v for m, v in zip(months, views) if m in spikes]
        if spike_x:
            axis.scatter(spike_x, spike_y, s=52, facecolors="none", edgecolors=colour,
                         linewidths=1.5, zorder=5)
        plotted += 1

    if not plotted:
        plt.close(figure)
        return None

    axis.set_title(title, fontsize=11, fontweight="bold", color="#1f2933")
    axis.set_ylabel("views per million\nedition views" if normalise else "monthly pageviews", fontsize=8)
    # Headroom so the legend cannot sit on top of the first months' data points.
    top = max((max(p) for p in [[pt["views"] for pt in r["series"]] for r in usable]), default=1)
    axis.set_ylim(bottom=0, top=axis.get_ylim()[1] * 1.22)
    axis.grid(True, alpha=0.25, linewidth=0.6)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)

    labels = [p["month"] for p in usable[0]["series"]]
    step = max(1, len(labels) // 12)
    axis.set_xticks(range(0, len(labels), step))
    axis.set_xticklabels(labels[::step], rotation=45, ha="right", fontsize=7)
    axis.tick_params(axis="y", labelsize=7)
    legend = axis.legend(fontsize=7.5, frameon=False, loc="upper left", ncol=min(len(usable), 4))
    legend.set_zorder(6)
    if any(r["quality"]["spike_months"] for r in usable):
        axis.annotate("circles = spike months (event-driven, excluded from trend weight)",
                      xy=(0.995, -0.30), xycoords="axes fraction", ha="right",
                      fontsize=6.5, color="#6b7280")

    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path


def make_momentum_chart(results: List[Dict[str, Any]], path: str) -> Optional[str]:
    """Horizontal bars of momentum, shaded by confidence.

    Plots change in *share of edition traffic* whenever every series has it, to
    match what the ranking is based on. Charting raw change instead would suggest
    every topic is collapsing, when most of that movement is Wikipedia-wide.

    Faded bars are low-confidence numbers; the shading is there so a long bar
    cannot be read as a strong result at a glance.
    """
    usable = [r for r in results if r.get("status") == "ok"]
    if not usable:
        return None

    relative = all(r["trend"].get("relative") for r in usable)
    def momentum(result):
        return (result["trend"]["relative"]["share_change_pct"] if relative
                else result["trend"]["headline_change_pct"])

    usable = sorted(usable, key=momentum)
    labels = [r["label"] for r in usable]
    values = [momentum(r) for r in usable]
    alphas = [max(0.25, r["quality"]["confidence"] / 100) for r in usable]

    height = max(1.6, 0.42 * len(usable) + 0.9)
    figure, axis = plt.subplots(figsize=(9.2, height), dpi=140)
    for i, (value, alpha) in enumerate(zip(values, alphas)):
        axis.barh(i, value, color="#2e7d5b" if value >= 0 else "#c1442e", alpha=alpha, height=0.6)
        offset = max(values + [1]) * 0.015
        axis.text(value + (offset if value >= 0 else -offset), i, f"{value:+.0f}%",
                  va="center", ha="left" if value >= 0 else "right", fontsize=7.5)

    axis.set_yticks(range(len(labels)))
    axis.set_yticklabels(labels, fontsize=8)
    axis.axvline(0, color="#1f2933", linewidth=0.8)
    axis.set_xlabel(
        "change in share of edition traffic, year-over-year" if relative
        else "change in raw pageviews, year-over-year where available",
        fontsize=8,
    )
    axis.set_title(
        ("Momentum vs the rest of each edition (bars faded where confidence is low)" if relative
         else "Momentum, faded where confidence is low"),
        fontsize=10, fontweight="bold",
    )
    axis.grid(True, axis="x", alpha=0.2, linewidth=0.6)
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    axis.tick_params(axis="x", labelsize=7)
    axis.margins(x=0.16)
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight")
    plt.close(figure)
    return path


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

# Compaction levels, tried in order until the report fits on one page.
# Each level trades detail for space: smaller type, fewer bullets, smaller charts.
COMPACTION = [
    {"body": 8.0, "fine": 6.6, "findings": 7, "rows": 13, "image": 1.00},
    {"body": 7.4, "fine": 6.2, "findings": 6, "rows": 11, "image": 0.86},
    {"body": 6.9, "fine": 5.9, "findings": 5, "rows": 9, "image": 0.72},
    {"body": 6.5, "fine": 5.6, "findings": 4, "rows": 8, "image": 0.60},
]


def _styles(level: Dict[str, float]) -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body_size = level["body"]
    fine_size = level["fine"]
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontName=_FONT_BOLD,
                                fontSize=body_size + 7, leading=body_size + 9,
                                textColor=ACCENT, alignment=TA_LEFT, spaceAfter=1),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontName=_FONT, fontSize=fine_size + 0.9,
                              leading=fine_size + 3, textColor=MUTED),
        "h2": ParagraphStyle("h", parent=base["Normal"], fontName=_FONT_BOLD, fontSize=body_size + 1,
                             leading=body_size + 3, textColor=ACCENT, spaceBefore=4, spaceAfter=2),
        "body": ParagraphStyle("b", parent=base["Normal"], fontName=_FONT, fontSize=body_size,
                               leading=body_size + 2.5),
        "bullet": ParagraphStyle("bu", parent=base["Normal"], fontName=_FONT, fontSize=body_size,
                                 leading=body_size + 2.5, leftIndent=8, spaceAfter=1.5),
        "fine": ParagraphStyle("f", parent=base["Normal"], fontName=_FONT, fontSize=fine_size,
                               leading=fine_size + 1.8, textColor=MUTED),
    }


def build_pdf(
    path: str,
    title: str,
    question: str,
    findings: List[str],
    table_rows: List[List[str]],
    chart_paths: List[str],
    limitations: List[str],
    method_note: str = "",
    single_page: bool = True,
) -> Dict[str, Any]:
    """Compose the report. Returns {"path":..., "pages": n, "compaction": level}.

    A one-page deliverable was the requirement, but content varies from one series
    to a dozen, so a fixed layout cannot guarantee it. Instead the page is rendered
    and, if it overflows, re-rendered at the next compaction level. Charts and the
    metrics table shrink; the method and limitations notes are never dropped.
    """
    _register_unicode_font()
    attempts = COMPACTION if single_page else COMPACTION[:1]
    result = {"path": path, "pages": 0, "compaction": 0}

    for index, level in enumerate(attempts):
        result = _render(path, level, title, question, findings, table_rows,
                         chart_paths, limitations, method_note)
        result["compaction"] = index
        if result["pages"] <= 1:
            break
    return result


def _render(
    path: str,
    level: Dict[str, float],
    title: str,
    question: str,
    findings: List[str],
    table_rows: List[List[str]],
    chart_paths: List[str],
    limitations: List[str],
    method_note: str,
) -> Dict[str, Any]:
    style = _styles(level)
    document = SimpleDocTemplate(
        path, pagesize=A4,
        leftMargin=13 * mm, rightMargin=13 * mm, topMargin=11 * mm, bottomMargin=10 * mm,
        title=title, author="wikipedia-topic-interest skill",
    )
    frame_width = document.width
    story: List[Any] = [Paragraph(_escape(title), style["title"])]

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(
        f"Generated {stamp} &middot; source: Wikimedia Pageviews API (agent=user, bots excluded)",
        style["sub"]))
    if question:
        story.append(Paragraph(f"<b>Question:</b> {_escape(question)}", style["sub"]))
    story.append(Spacer(1, 2.5 * mm))

    if findings:
        story.append(Paragraph("What the data says", style["h2"]))
        for finding in findings[:int(level["findings"])]:
            story.append(Paragraph(f"&bull;&nbsp;{_escape(finding)}", style["bullet"]))

    image_width = frame_width * level["image"]
    for chart in chart_paths:
        if chart and os.path.exists(chart):
            story.append(Spacer(1, 1.5 * mm))
            story.append(_fit_image(chart, image_width))

    if table_rows and len(table_rows) > 1:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Metrics", style["h2"]))
        story.append(_metrics_table(table_rows, frame_width, style, int(level["rows"])))

    story.append(Spacer(1, 2 * mm))
    if method_note:
        story.append(Paragraph(f"<b>Method.</b> {_escape(method_note)}", style["fine"]))
    if limitations:
        story.append(Paragraph(
            "<b>Limitations.</b> " + " ".join(_escape(item) for item in limitations), style["fine"]))

    pages = {"n": 0}

    def stamp_page(canvas, _doc):
        pages["n"] += 1
        canvas.saveState()
        canvas.setFont(_FONT, 6.5)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(A4[0] - 13 * mm, 6 * mm,
                               "Wikipedia reading interest is a research signal, not proof of demand.")
        canvas.restoreState()

    document.build(story, onFirstPage=stamp_page, onLaterPages=stamp_page)
    return {"path": path, "pages": pages["n"]}


def _fit_image(path: str, max_width: float) -> Image:
    """Scale a PNG to the frame width, preserving aspect ratio."""
    from reportlab.lib.utils import ImageReader

    native_width, native_height = ImageReader(path).getSize()
    scale = max_width / float(native_width)
    return Image(path, width=max_width, height=native_height * scale)


def _metrics_table(
    rows: List[List[str]], width: float, style: Dict[str, ParagraphStyle], max_rows: int = 13
) -> Table:
    shown = rows[:1] + rows[1:max_rows]
    size = min(6.8, style["body"].fontSize - 0.6)
    cell = ParagraphStyle("cell", parent=style["body"], fontSize=size, leading=size + 1.4)
    head = ParagraphStyle("head", parent=cell, fontName=_FONT_BOLD, textColor=colors.white)
    data = [[Paragraph(_escape(str(c)), head) for c in shown[0]]]
    data += [[Paragraph(_escape(str(c)), cell) for c in row] for row in shown[1:]]

    # First column carries the long article titles, so give it the extra room.
    first = width * 0.30
    others = (width - first) / max(1, len(shown[0]) - 1)
    table = Table(data, colWidths=[first] + [others] * (len(shown[0]) - 1), repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f9")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c9d2dd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _escape(text: str) -> str:
    """Escape for reportlab's mini-markup so stray &, < or > cannot corrupt the PDF."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ---------------------------------------------------------------------------
# decision memo (the report a founder or CEO reads)
# ---------------------------------------------------------------------------

# Validated categorical palette (fixed order) and status colours. Status colours
# are always printed with a text label, never relied on alone.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
TONE = {"good": "#0a7d0a", "bad": "#c62f2f", "neutral": "#8a6100", "muted": "#6b6a66"}
TONE_BG = {"good": "#e8f5e8", "bad": "#fbeaea", "neutral": "#fdf4e1", "muted": "#f1f0ec"}
RISK = {"high": ("HIGH", "#c62f2f"), "medium": ("MED", "#8a6100"), "low": ("LOW", "#0a7d0a")}
INK, INK2, GRID_C, AXIS_C = "#0b0b0b", "#52514e", "#e1e0d9", "#c3c2b7"


def _style_axis(axis) -> None:
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    axis.spines["bottom"].set_color(AXIS_C)
    axis.tick_params(colors=INK2, labelsize=7, length=0)
    axis.set_axisbelow(True)


def make_share_chart(results: List[Dict[str, Any]], path: str, tr=None) -> Optional[str]:
    """Each topic's real share of its edition over time (views per million edition views).

    This is the chart that answers "is it the topic or the platform?": a line that
    falls here is losing readers relative to everything else in that language.
    """
    usable = [r for r in results if r.get("status") == "ok" and r.get("share_series")]
    if not usable:
        return None
    figure, axis = plt.subplots(figsize=(4.6, 2.6), dpi=200)
    _style_axis(axis)
    axis.grid(True, axis="y", color=GRID_C, linewidth=0.6)
    for index, result in enumerate(usable[:len(SERIES)]):
        colour = SERIES[index]
        months = [p["month"] for p in result["share_series"]]
        values = [p["per_million"] for p in result["share_series"]]
        smooth = [sum(values[max(0, i - 2):i + 1]) / len(values[max(0, i - 2):i + 1]) for i in range(len(values))]
        axis.plot(range(len(values)), values, color=colour, linewidth=0.8, alpha=0.3)
        axis.plot(range(len(values)), smooth, color=colour, linewidth=2, label=result["label"])
    labels = [p["month"] for p in usable[0]["share_series"]]
    step = max(1, len(labels) // 6)
    axis.set_xticks(range(0, len(labels), step))
    axis.set_xticklabels(labels[::step], fontsize=6.5)
    axis.set_ylim(bottom=0)
    tr = tr or _english()
    axis.set_title(tr("chart.share"),
                   fontsize=7.5, color=INK2, loc="left")
    axis.legend(fontsize=6.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12),
                ncol=min(4, len(usable)), labelcolor=INK2, handlelength=1.2)
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return path


def make_range_chart(results: List[Dict[str, Any]], calls: List[Dict[str, Any]], path: str,
                     tr=None) -> Optional[str]:
    """Year-over-year change in share, with the 90% range and the recommendation per series.

    The whisker is the point: a bar whose range crosses zero is not a direction.
    """
    by_label = {c["label"]: c for c in calls}
    rows = []
    for result in results:
        relative = (result.get("trend") or {}).get("relative") if result.get("status") == "ok" else None
        if relative:
            rows.append((result["label"], relative["share_change_pct"], relative.get("share_ci90_pct"),
                         by_label.get(result["label"], {})))
    if not rows:
        return None
    rows.sort(key=lambda r: r[1])
    figure, axis = plt.subplots(figsize=(4.6, max(1.5, 0.36 * len(rows) + 1.0)), dpi=200)
    _style_axis(axis)
    axis.grid(True, axis="x", color=GRID_C, linewidth=0.6)
    values = [0.0] + [v for _, v, _, _ in rows] + [x for _, _, ci, _ in rows for x in (ci or [])]
    low, high = min(values), max(values)
    span = (high - low) or 10
    for i, (label, value, ci, call) in enumerate(rows):
        tone = TONE.get(call.get("tone"), TONE["muted"])
        axis.barh(i, value, height=0.5, color=tone, alpha=0.85)
        if ci:
            axis.plot(ci, [i, i], color=INK, linewidth=1)
            for x in ci:
                axis.plot([x, x], [i - 0.13, i + 0.13], color=INK, linewidth=1)
        action = call.get("action_label") or call.get("action", "").replace("_", " ")
        axis.text(high + 0.04 * span, i, f"{value:+.0f}%  {action}", va="center", fontsize=6.5, color=INK)
    axis.axvline(0, color=AXIS_C, linewidth=1)
    axis.set_yticks(range(len(rows)))
    axis.set_yticklabels([r[0] for r in rows], fontsize=6.8, color=INK2)
    axis.set_xlim(low - 0.06 * span, high + 0.62 * span)
    axis.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:+.0f}%"))
    tr = tr or _english()
    axis.set_title(tr("chart.range"),
                   fontsize=7.5, color=INK2, loc="left")
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return path


def make_vs_platform_chart(result: Dict[str, Any], path: str, tr=None) -> Optional[str]:
    """One edition: the topic's readers against the whole edition, both indexed to 100.

    The gap between the two lines is the topic-specific part of any change. Falling
    together means the platform; the topic line below the edition means lost interest.
    """
    shares = {p["month"]: p["per_million"] for p in result.get("share_series", [])}
    points = [p for p in result.get("series", []) if shares.get(p["month"])]
    if len(points) < 12:
        return None
    topic = [p["views"] for p in points]
    edition = [p["views"] / shares[p["month"]] * 1_000_000 for p in points]

    def index(values):
        base = sum(values[:12]) / 12 or 1
        raw = [v / base * 100 for v in values]
        return [sum(raw[max(0, i - 2):i + 1]) / len(raw[max(0, i - 2):i + 1]) for i in range(len(raw))]

    tr = tr or _english()
    figure, axis = plt.subplots(figsize=(4.6, 2.6), dpi=200)
    _style_axis(axis)
    axis.grid(True, axis="y", color=GRID_C, linewidth=0.6)
    xs = range(len(points))
    axis.plot(xs, index(edition), color="#898781", linewidth=2, linestyle=(0, (4, 2)),
              label=tr("chart.vs.edition", project=f"{result.get('lang', '')}.wikipedia"))
    axis.plot(xs, index(topic), color=SERIES[0], linewidth=2, label=tr("chart.vs.topic", title=result.get("title", "")))
    axis.axhline(100, color=AXIS_C, linewidth=0.8)
    labels = [p["month"] for p in points]
    step = max(1, len(labels) // 6)
    axis.set_xticks(range(0, len(labels), step))
    axis.set_xticklabels(labels[::step], fontsize=6.5)
    axis.set_ylim(bottom=0)
    axis.set_title(tr("chart.vs"),
                   fontsize=7.5, color=INK2, loc="left")
    axis.legend(fontsize=6.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12),
                ncol=2, labelcolor=INK2, handlelength=1.8)
    figure.tight_layout()
    figure.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return path


MEMO_LEVELS = [
    {"body": 8.2, "small": 6.9, "chart": 0.50},
    {"body": 7.6, "small": 6.5, "chart": 0.46},
    {"body": 7.1, "small": 6.1, "chart": 0.42},
    {"body": 6.6, "small": 5.8, "chart": 0.38},
]


def build_memo(
    path: str,
    title: str,
    subtitle: str,
    question: str,
    memo: Dict[str, Any],
    scorecard: List[List[str]],
    chart_paths: List[str],
    assumptions: List[str],
    method_note: str,
    analyst_notes: Optional[List[str]] = None,
    reproduce: str = "",
    tr=None,
) -> Dict[str, Any]:
    """One A4 page for decision-makers: the call, the evidence, the risks.

    Rendered at decreasing type sizes until it fits one page. Nothing is dropped:
    the recommendation, evidence and trust notes are the report.
    """
    _register_unicode_font()
    result = {"path": path, "pages": 0}
    for index, level in enumerate(MEMO_LEVELS):
        result = _render_memo(path, level, title, subtitle, question, memo, scorecard, chart_paths,
                              assumptions, method_note, analyst_notes or [], reproduce, tr or _english())
        result["compaction"] = index
        if result["pages"] <= 1:
            break
    return result


def _english():
    from i18n import Translator
    return Translator("en")


def _render_memo(path, level, title, subtitle, question, memo, scorecard, chart_paths,
                 assumptions, method_note, analyst_notes, reproduce, tr) -> Dict[str, Any]:
    body, small = level["body"], level["small"]
    base = getSampleStyleSheet()["Normal"]
    st = {
        "title": ParagraphStyle("mt", parent=base, fontName=_FONT_BOLD, fontSize=body + 7.5,
                                leading=body + 10, textColor=colors.HexColor(INK)),
        "sub": ParagraphStyle("ms", parent=base, fontName=_FONT, fontSize=small, leading=small + 2.4,
                              textColor=colors.HexColor(INK2)),
        "h": ParagraphStyle("mh", parent=base, fontName=_FONT_BOLD, fontSize=body + 0.8, leading=body + 3,
                            textColor=colors.HexColor(INK), spaceBefore=3, spaceAfter=1.5),
        "body": ParagraphStyle("mb", parent=base, fontName=_FONT, fontSize=body, leading=body + 2.6,
                               textColor=colors.HexColor(INK)),
        "item": ParagraphStyle("mi", parent=base, fontName=_FONT, fontSize=body - 0.3, leading=body + 2.2,
                               leftIndent=9, firstLineIndent=-9, spaceAfter=1.2, textColor=colors.HexColor(INK)),
        "small": ParagraphStyle("mf", parent=base, fontName=_FONT, fontSize=small, leading=small + 2,
                                textColor=colors.HexColor(INK2)),
        "cell": ParagraphStyle("mc", parent=base, fontName=_FONT, fontSize=small + 0.4, leading=small + 2.4),
    }
    document = SimpleDocTemplate(path, pagesize=A4, leftMargin=13 * mm, rightMargin=13 * mm,
                                 topMargin=11 * mm, bottomMargin=11 * mm, title=title,
                                 author="wikipedia-topic-interest skill")
    width = document.width
    story: List[Any] = [Paragraph(_escape(title), st["title"]), Paragraph(_escape(subtitle), st["sub"])]
    if question:
        story.append(Paragraph(f"<b>{_escape(tr('memo.question'))}</b> {_escape(question)}", st["sub"]))
    story.append(Spacer(1, 3 * mm))

    # 1. The call.
    tone = memo["overall_tone"]
    action = memo.get("overall_action_label") or memo["overall_action"].replace("_", " ")
    box = [Paragraph(f'<font color="{TONE[tone]}"><b>{_escape(tr("memo.recommendation", action=action))}</b></font>',
                     ParagraphStyle("ma", parent=st["body"], fontSize=body + 2.2, leading=body + 5)),
           Paragraph(_escape(memo["overall"]), st["body"])]
    for note in analyst_notes:
        box.append(Paragraph(f"<b>{_escape(tr('memo.analyst_note'))}</b> {_escape(note)}", st["body"]))
    decision = Table([["", box]], colWidths=[2.2 * mm, width - 2.2 * mm])
    decision.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor(TONE[tone])),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(TONE_BG[tone])),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (1, 0), (1, 0), 7), ("RIGHTPADDING", (1, 0), (1, 0), 7),
        ("TOPPADDING", (1, 0), (1, 0), 5), ("BOTTOMPADDING", (1, 0), (1, 0), 6),
    ]))
    story += [decision, Spacer(1, 3 * mm)]

    # 2. Scorecard: one row per edition, recommendation first.
    tones = {c["label"]: c["tone"] for c in memo["calls"]}
    head = ParagraphStyle("mhd", parent=st["cell"], fontName=_FONT_BOLD, textColor=colors.HexColor(INK2))
    rows = [[Paragraph(_escape(h), head) for h in scorecard[0]]]
    for row in scorecard[1:]:
        cells = [Paragraph(_escape(c), st["cell"]) for c in row]
        colour = TONE.get(tones.get(row[0]), TONE["muted"])
        cells[1] = Paragraph(f'<font color="{colour}"><b>{_escape(row[1])}</b></font>', st["cell"])
        rows.append(cells)
    fractions = [0.22, 0.17, 0.11, 0.24, 0.12, 0.14]
    table = Table(rows, colWidths=[f * width for f in fractions], repeatRows=1)
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(AXIS_C)),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor(GRID_C)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story += [table, Spacer(1, 2.5 * mm)]

    # 3. Charts side by side.
    charts = [c for c in chart_paths if c and os.path.exists(c)]
    if charts:
        chart_w = width * level["chart"] * (2 if len(charts) == 1 else 1) * 0.98
        images = [_fit_image(c, min(chart_w, width / len(charts) - 2 * mm)) for c in charts]
        grid = Table([images], colWidths=[width / len(images)] * len(images))
        grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story += [grid, Spacer(1, 2 * mm)]

    # 4. Two columns: why + what next | how far to trust it.
    lead = memo["calls"][0]
    left: List[Any] = [Paragraph(_escape(tr("memo.why", label=lead["label"])), st["h"])]
    left += [Paragraph(f"{i}.&nbsp;{_escape(step)}", st["item"]) for i, step in enumerate(lead["evidence"], 1)]
    left.append(Paragraph(_escape(tr("memo.next")), st["h"]))
    left += [Paragraph(f"&bull;&nbsp;{_escape(step)}", st["item"]) for step in lead["next_steps"]]
    left.append(Paragraph(_escape(tr("memo.change")), st["h"]))
    left.append(Paragraph(_escape(lead["would_change"]), st["item"]))

    right: List[Any] = [Paragraph(_escape(tr("memo.trust")), st["h"])]
    for note in lead["trust"][:6]:
        colour = RISK[note["risk"]][1]
        tag = tr(f"risk.{note['risk']}")
        right.append(Paragraph(f'<font color="{colour}"><b>{tag}</b></font>&nbsp; {_escape(note["text"])}',
                               st["item"]))
    right.append(Paragraph(_escape(tr("memo.assumptions")), st["h"]))
    right += [Paragraph(f"&bull;&nbsp;{_escape(a)}", st["item"]) for a in assumptions]
    columns = Table([[left, right]], colWidths=[width * 0.54, width * 0.46])
    columns.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 8)]))
    story += [columns, Spacer(1, 2 * mm)]

    # 5. Method and reproducibility.
    fine = f"<b>{_escape(tr('memo.method'))}</b> {_escape(method_note)} {_escape(tr('memo.rules'))}"
    if reproduce:
        fine += f" <b>{_escape(tr('memo.reproduce'))}</b> {_escape(reproduce)}"
    story.append(Paragraph(fine, st["small"]))

    pages = {"n": 0}

    def stamp(canvas, _doc):
        pages["n"] += 1
        canvas.saveState()
        canvas.setFont(_FONT, 6.3)
        canvas.setFillColor(colors.HexColor(INK2))
        canvas.drawRightString(A4[0] - 13 * mm, 6 * mm, tr("memo.footer"))
        canvas.restoreState()

    document.build(story, onFirstPage=stamp, onLaterPages=stamp)
    return {"path": path, "pages": pages["n"]}


def main() -> int:
    """Render a demo PDF from synthetic data, including non-Latin titles."""
    demo = [
        {
            "label": "uk: Астрономія", "status": "ok",
            "series": [{"month": f"2025-{m:02d}", "views": 400 + m * 25} for m in range(1, 13)],
            "volume": {"median_monthly": 550, "per_million_edition_views": 5.1, "latest_month": 700},
            "trend": {"direction": "growing", "headline_change_pct": 42.0, "p_value": 0.01},
            "quality": {"confidence": 71, "confidence_band": "moderate", "spike_months": ["2025-07"],
                        "reasons": ["Thin traffic."]},
        }
    ]
    chart = make_chart(demo, "Demo: interest over time", "demo_chart.png")
    momentum = make_momentum_chart(demo, "demo_momentum.png")
    result = build_pdf(
        "demo_report.pdf", "Demo report: Астрономія / Přerušovaný půst",
        "Is interest growing?",
        ["Ukrainian interest grew 42% year-over-year, confidence 71/100 (moderate)."],
        [["Language / article", "Views/mo", "Per million", "Change", "Confidence"],
         ["uk: Астрономія", "550", "5.1", "+42%", "71 (moderate)"]],
        [c for c in (chart, momentum) if c],
        ["Pageviews measure curiosity, not willingness to pay."],
        "Mann-Kendall for direction, Theil-Sen for magnitude.",
    )
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
