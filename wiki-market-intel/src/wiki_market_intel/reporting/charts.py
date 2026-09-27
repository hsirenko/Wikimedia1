"""Charts. Reporting reads only the normalized result, never the API."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from wiki_market_intel.i18n import Translator  # noqa: E402
from wiki_market_intel.models.analysis import AnalysisResult  # noqa: E402

CHART_TEXT = {
    "en": {"title": "'{title}' on {project}: monthly pageviews, {start} to {end} ({agent} traffic)",
           "raw": "monthly pageviews", "avg": "3-month moving average"},
    "uk": {"title": "«{title}» у {project}: перегляди за місяць, {start}–{end} (трафік: {agent})",
           "raw": "перегляди за місяць", "avg": "ковзне середнє за 3 місяці"},
}

SERIES, INK2, GRID, AXIS, SURFACE = "#2a78d6", "#52514e", "#e1e0d9", "#c3c2b7", "#ffffff"


def trend_chart(result: AnalysisResult, path: Path, lang: str = "en") -> Path | None:
    """Monthly pageviews over the requested period, with a 3-month moving average.
    Months without data are gaps in the line, never zeros."""
    start, end = result.metadata.period_start, result.metadata.period_end
    points = [p for p in result.monthly if start <= p.month <= end]
    if not any(p.views is not None for p in points):
        return None
    xs = list(range(len(points)))
    values = [p.views for p in points]
    smooth: list[float | None] = []
    for i in xs:
        window = [v for v in values[max(0, i - 2):i + 1] if v is not None]
        smooth.append(sum(window) / len(window) if len(window) == len(values[max(0, i - 2):i + 1]) else None)

    tr = Translator(lang)
    text = CHART_TEXT.get(tr.lang, CHART_TEXT["en"])
    fig, ax = plt.subplots(figsize=(8.5, 3.4), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=8, length=0)
    ax.grid(True, axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.plot(xs, [v if v is not None else float("nan") for v in values], color=SERIES, linewidth=1,
            alpha=0.35, label=text["raw"])
    ax.plot(xs, [v if v is not None else float("nan") for v in smooth], color=SERIES, linewidth=2,
            label=text["avg"])
    flagged = {a.date for a in result.anomalies}
    marks = [(i, p.views) for i, p in enumerate(points) if p.month in flagged and p.views is not None]
    if marks:
        ax.scatter([i for i, _ in marks], [v for _, v in marks], s=70, facecolor=SURFACE, edgecolor="#e34948",
                   linewidth=1.8, zorder=4, label=tr("chart_anomaly"))
    step = max(1, len(points) // 9)
    ax.set_xticks(xs[::step])
    ax.set_xticklabels([p.month for p in points][::step])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: tr.compact(v)))
    ax.set_ylim(bottom=0)
    ax.set_title(text["title"].format(title=result.topic.article_title, project=result.metadata.project,
                                      start=start, end=end, agent=result.metadata.agent),
                 fontsize=9, color=INK2, loc="left")
    ax.legend(fontsize=7.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3,
              labelcolor=INK2)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# language comparison
# ---------------------------------------------------------------------------

# Validated categorical palette, fixed order: an edition keeps its colour across both charts.
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
MUTED = "#898781"


def _style(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.spines["left"].set_color(AXIS)
    ax.tick_params(colors=INK2, labelsize=8, length=0)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _log_axis(ax, tr) -> None:
    """Compact tick labels on a log axis; minor ticks are labelled only when the range is under one decade."""
    from matplotlib.ticker import NullFormatter
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: tr.compact(v)))
    low, high = ax.get_ylim()
    ax.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: tr.compact(v)) if high / low < 10 else NullFormatter())
    ax.tick_params(axis="y", which="minor", labelsize=7, colors=INK2, length=0)


def _place_labels(fig, ax, xs, ys, texts, fontsize=7) -> None:
    """Direct labels, biggest first; a label is kept only if its box clears every other marker and label."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    markers = [ax.transData.transform((x, y)) for x, y in zip(xs, ys)]
    boxes = []
    for i in sorted(range(len(xs)), key=lambda i: -ys[i]):
        note = ax.annotate(texts[i], (xs[i], ys[i]), xytext=(6, 3), textcoords="offset points", fontsize=fontsize,
                           color=INK2)
        box = note.get_window_extent(renderer).expanded(1.05, 1.2)
        hits = any(j != i and box.x0 - 9 <= mx <= box.x1 + 9 and box.y0 - 9 <= my <= box.y1 + 9
                   for j, (mx, my) in enumerate(markers))
        if hits or any(box.overlaps(b) for b in boxes):
            note.remove()
            continue
        boxes.append(box)


def opportunity_matrix(comparison, path: Path, lang: str = "en") -> Path | None:
    """Demand x growth scatter (spec §23). Quadrant names are descriptive, never recommendations."""
    tr = Translator(lang)
    colours = {row.language: PALETTE[i % len(PALETTE)] for i, row in enumerate(comparison.rows)}
    points = [r for r in comparison.rows if r.annual_views and r.yoy_growth is not None]
    if not points or comparison.demand_threshold is None:
        return None
    fig, ax = plt.subplots(figsize=(7.5, 4.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    ax.set_yscale("log")
    xs = [r.yoy_growth * 100 for r in points]
    ys = [r.annual_views for r in points]
    span = max(10.0, max(abs(x) for x in xs) * 1.35)
    ax.set_xlim(-span, span)
    low, high = min(ys) / 2.5, max(ys) * 2.5
    ax.set_ylim(low, high)
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.axhline(comparison.demand_threshold, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    corners = {("investigate", 0.98, 0.97, "right", "top"), ("explore", 0.98, 0.03, "right", "bottom"),
               ("established", 0.02, 0.97, "left", "top"), ("watch", 0.02, 0.03, "left", "bottom")}
    for name, x, y, ha, va in corners:
        ax.text(x, y, tr(f"quadrant.{name}").upper(), transform=ax.transAxes, ha=ha, va=va,
                fontsize=8, color=MUTED, fontweight="bold")
    for row, x, y in zip(points, xs, ys):
        ax.scatter([x], [y], s=70, color=colours[row.language], edgecolor=SURFACE, linewidth=1.5, zorder=3)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: tr.percent(v / 100)))
    _log_axis(ax, tr)
    _place_labels(fig, ax, xs, ys, [r.project for r in points], fontsize=8)
    ax.set_xlabel(tr("chart_matrix_x"), fontsize=8, color=INK2)
    ax.set_ylabel(tr("chart_matrix_y"), fontsize=8, color=INK2)
    ax.set_title(tr("chart_matrix_title", topic=comparison.resolution.canonical_topic or comparison.metadata.topic),
                 fontsize=9, color=INK2, loc="left")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def penetration_chart(comparison, path: Path, lang: str = "en") -> Path | None:
    """Topic views per million edition views, month by month, per edition (3-month average)."""
    tr = Translator(lang)
    colours = {row.language: PALETTE[i % len(PALETTE)] for i, row in enumerate(comparison.rows)}
    start, end = comparison.metadata.period_start, comparison.metadata.period_end
    fig, ax = plt.subplots(figsize=(8.5, 3.4), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    ax.grid(False, axis="x")
    drawn, labels = 0, []
    for language, result in comparison.analyses.items():
        edition = {p.month: p.views for p in result.edition_monthly}
        points = [p for p in result.monthly if start <= p.month <= end]
        values = [p.views / edition[p.month] * 1e6 if p.views is not None and edition.get(p.month) else None
                  for p in points]
        if not any(v is not None for v in values):
            continue
        smooth = []
        for i in range(len(values)):
            window = values[max(0, i - 2):i + 1]
            smooth.append(sum(window) / len(window) if all(v is not None for v in window) else float("nan"))
        ax.plot(range(len(points)), smooth, color=colours[language], linewidth=2, label=result.metadata.project)
        labels = [p.month for p in points]
        drawn += 1
    if not drawn:
        plt.close(fig)
        return None
    step = max(1, len(labels) // 9)
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels(labels[::step])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: tr.decimal(v, 1)))
    ax.set_ylim(bottom=0)
    ax.set_title(tr("chart_pen_title"), fontsize=9, color=INK2, loc="left")
    ax.legend(fontsize=7.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1),
              ncol=min(6, drawn), labelcolor=INK2)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def ecosystem_chart(result: AnalysisResult, path: Path, lang: str = "en") -> Path | None:
    """Related topics: share-adjusted growth across, views up (log). The topic itself is highlighted;
    typed relations and text-similar articles have different colours, always with a legend."""
    tr = Translator(lang)
    eco = result.ecosystem
    # "too small" topics stay in the report table but not on the chart: their growth figures are noise.
    points = [t for t in eco.related_topics
              if t.annual_views and t.share_adjusted_yoy is not None and t.signal != "too_small"]
    focal_views = result.demand.annual_views
    if not points or not focal_views:
        return None
    focal_x = (ecosystem_share_adjusted(result.growth.yoy, eco.edition_yoy) or 0) * 100
    fig, ax = plt.subplots(figsize=(7.5, 4.8), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    ax.set_yscale("log")
    xs = [t.share_adjusted_yoy * 100 for t in points] + [focal_x]
    ys = [t.annual_views for t in points] + [focal_views]
    span = max(15.0, max(abs(x) for x in xs) * 1.3)
    ax.set_xlim(-span, span)
    ax.set_ylim(min(ys) / 2.5, max(ys) * 2.5)
    ax.axvline(0, color=MUTED, linewidth=1)
    for kind, colour, label in (("typed", PALETTE[0], tr("chart_eco_typed")), ("similar", PALETTE[3], tr("chart_eco_similar"))):
        group = [t for t in points if (t.relationship == "similar_content") == (kind == "similar")]
        if group:
            ax.scatter([t.share_adjusted_yoy * 100 for t in group], [t.annual_views for t in group], s=40,
                       color=colour, edgecolor=SURFACE, linewidth=1, zorder=3, label=label)
    ax.scatter([focal_x], [focal_views], s=120, color=PALETTE[1], edgecolor=INK2, linewidth=1.2, zorder=4,
               label=tr("chart_eco_focal"))
    ax.annotate(result.topic.article_title, (focal_x, focal_views), xytext=(8, 6), textcoords="offset points",
                fontsize=8, color=INK2, fontweight="bold")
    # Label the largest topics first; skip a label that would collide with one already placed.
    fig.canvas.draw()
    placed = [ax.transData.transform((focal_x, focal_views))]
    for t in sorted(points, key=lambda t: -t.annual_views):
        x, y = ax.transData.transform((t.share_adjusted_yoy * 100, t.annual_views))
        if any(abs(x - px) < 95 and abs(y - py) < 16 for px, py in placed):
            continue
        placed.append((x, y))
        ax.annotate(t.title[:26], (t.share_adjusted_yoy * 100, t.annual_views), xytext=(6, 3),
                    textcoords="offset points", fontsize=7, color=INK2)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: tr.percent(v / 100)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: tr.compact(v)))
    ax.set_xlabel(tr("chart_eco_x"), fontsize=8, color=INK2)
    ax.set_ylabel(tr("chart_eco_y"), fontsize=8, color=INK2)
    ax.set_title(tr("chart_eco_title", topic=result.topic.article_title), fontsize=9, color=INK2, loc="left")
    ax.legend(fontsize=7.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3, labelcolor=INK2)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def ecosystem_share_adjusted(yoy, edition):
    from wiki_market_intel.analytics.ecosystem import share_adjusted
    return share_adjusted(yoy, edition)


MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]


def portfolio_chart(portfolio, path: Path, lang: str = "en") -> Path | None:
    """Demand x growth for many (topic, edition) pairs (spec §37). Colour = topic (fixed input order,
    never cycled: a 9th topic is grey and labelled directly); shape = edition; quadrant names are
    descriptive."""
    tr = Translator(lang)
    points = [r for r in portfolio.visible if r.annual_views and r.yoy_growth is not None]
    if not points or portfolio.demand_threshold is None:
        return None
    topics = [t.topic for t in portfolio.metadata.topics]
    colour = {t: PALETTE[i] if i < len(PALETTE) else MUTED for i, t in enumerate(topics)}
    marker = {l: MARKERS[i % len(MARKERS)] for i, l in enumerate(portfolio.metadata.languages)}
    fig, ax = plt.subplots(figsize=(7.8, 5.0), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    ax.set_yscale("log")
    xs = [r.yoy_growth * 100 for r in points]
    ys = [r.annual_views for r in points]
    span = max(10.0, max(abs(x) for x in xs) * 1.3)
    ax.set_xlim(-span, span)
    ax.set_ylim(min(ys + [portfolio.demand_threshold]) / 2.5, max(ys + [portfolio.demand_threshold]) * 2.5)
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.axhline(portfolio.demand_threshold, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
    for name, x, y, ha, va in (("investigate", 0.98, 0.97, "right", "top"), ("explore", 0.98, 0.03, "right", "bottom"),
                               ("established", 0.02, 0.97, "left", "top"), ("watch", 0.02, 0.03, "left", "bottom")):
        ax.text(x, y, tr(f"quadrant.{name}").upper(), transform=ax.transAxes, ha=ha, va=va,
                fontsize=8, color=MUTED, fontweight="bold")
    for r, x, y in zip(points, xs, ys):
        ax.scatter([x], [y], s=60, color=colour.get(r.topic, MUTED), marker=marker[r.language],
                   edgecolor=SURFACE, linewidth=1.2, zorder=3)
    _place_labels(fig, ax, xs, ys, [f"{(r.canonical_topic or r.topic)[:18]} · {r.language}" for r in points])
    from matplotlib.lines import Line2D
    shown_topics = [t for t in topics if any(r.topic == t for r in points)]
    shown_langs = [l for l in portfolio.metadata.languages if any(r.language == l for r in points)]
    names = {r.topic: r.canonical_topic or r.topic for r in points}
    handles = ([Line2D([], [], linestyle="", marker="o", color=colour[t], label=names[t]) for t in shown_topics]
               + [Line2D([], [], linestyle="", marker=marker[l], color=INK2, label=f"{l}.wikipedia") for l in shown_langs])
    ax.legend(handles=handles, fontsize=7, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.13),
              ncol=min(5, len(handles)), labelcolor=INK2)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: tr.percent(v / 100)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: tr.compact(v)))
    ax.set_xlabel(tr("chart_matrix_x"), fontsize=8, color=INK2)
    ax.set_ylabel(tr("chart_matrix_y"), fontsize=8, color=INK2)
    _log_axis(ax, tr)
    ax.set_title(tr("pf_chart_title"), fontsize=9, color=INK2, loc="left")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path
