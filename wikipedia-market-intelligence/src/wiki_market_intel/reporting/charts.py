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
    step = max(1, len(points) // 9)
    ax.set_xticks(xs[::step])
    ax.set_xticklabels([p.month for p in points][::step])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: tr.compact(v)))
    ax.set_ylim(bottom=0)
    ax.set_title(text["title"].format(title=result.topic.article_title, project=result.metadata.project,
                                      start=start, end=end, agent=result.metadata.agent),
                 fontsize=9, color=INK2, loc="left")
    ax.legend(fontsize=7.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2,
              labelcolor=INK2)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path
