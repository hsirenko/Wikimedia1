"""Portfolio mode (spec §36-§37): many topics x many language editions in one matrix.

Every value in a row comes from that topic's own comparison (or single analysis), so share
and affinity keep their comparison meaning: *within the topic, across the portfolio's
editions*. The portfolio adds only two things:

* a portfolio-wide quadrant: growth YoY > 0; demand >= the median annual views of every
  measured (topic, edition) pair, taken before filters so a filter never moves the split;
* filters (minimum views, minimum YoY growth, categories) that hide rows from the matrix
  and chart but keep them, marked `excluded_by`, in the JSON.

Rows keep the input order (topics as listed, then editions as listed). Nothing is sorted by
a KPI, because an order by size or growth would read as a ranking.
"""

from __future__ import annotations

import re
import statistics

from wiki_market_intel.analytics import formulas as f
from wiki_market_intel.analytics import signals as signal_kpis
from wiki_market_intel.models.analysis import (
    AnalysisResult, ComparisonResult, PortfolioFilters, PortfolioRow, PortfolioTopic,
)

QUADRANT_ORDER = ("investigate", "explore", "established", "watch")
QUADRANT_MEANING = {
    "investigate": "growing year over year, with demand at or above the portfolio median",
    "explore": "growing year over year, with demand below the portfolio median",
    "established": "not growing year over year, with demand at or above the portfolio median",
    "watch": "not growing year over year, with demand below the portfolio median",
}
NO_VERDICT = ("The quadrants below describe demand and growth; they are not a verdict. Wikipedia pageviews measure "
              "reader attention, not revenue or demand for a product.")


def rows_from_comparison(item: PortfolioTopic, c: ComparisonResult) -> list[PortfolioRow]:
    rows = []
    for r in c.rows:
        a = c.analyses.get(r.language)
        rows.append(PortfolioRow(
            topic=item.topic, category=item.category, canonical_topic=c.resolution.canonical_topic,
            wikidata_id=c.resolution.wikidata_id, language=r.language, project=r.project,
            article_title=r.article_title, status=r.status,
            reason="no article about this concept in this edition" if r.status == "no_article" else None,
            annual_views=r.annual_views, yoy_growth=r.yoy_growth, three_year_cagr=r.three_year_cagr,
            three_month_growth=r.three_month_growth, momentum=r.momentum, topic_share=r.topic_share,
            topic_affinity=r.topic_affinity, topic_penetration=r.topic_penetration,
            signals=a.signals if a else None, quality_level=r.quality_level, anomaly_count=r.anomaly_count,
            edition_yoy=signal_kpis.edition_yoy(a) if a else None))
    return rows


def row_from_analysis(item: PortfolioTopic, a: AnalysisResult) -> PortfolioRow:
    has_data = any(p.views is not None for p in a.monthly)
    return PortfolioRow(
        topic=item.topic, category=item.category, canonical_topic=a.topic.canonical_name,
        wikidata_id=a.topic.wikidata_id, language=a.metadata.language, project=a.metadata.project,
        article_title=a.topic.article_title, status="ok" if has_data else "no_data",
        annual_views=a.demand.annual_views, yoy_growth=a.growth.yoy, three_year_cagr=a.growth.three_year_cagr,
        three_month_growth=a.growth.last_three_month_growth, momentum=a.growth.momentum,
        topic_penetration=a.localization.topic_penetration, signals=a.signals,
        quality_level=a.quality.quality_level, anomaly_count=len(a.anomalies), edition_yoy=signal_kpis.edition_yoy(a))


def failed_rows(item: PortfolioTopic, languages: list[str], status: str, reason: str) -> list[PortfolioRow]:
    return [PortfolioRow(topic=item.topic, category=item.category, language=lang, project=f"{lang}.wikipedia",
                         status=status, reason=reason) for lang in languages]


def measured(rows: list[PortfolioRow]) -> list[PortfolioRow]:
    return [r for r in rows if r.status == "ok" and r.annual_views is not None]


def assign_quadrants(rows: list[PortfolioRow]) -> float | None:
    """Portfolio-wide split (in place). Returns the demand threshold: the median of measured pairs."""
    usable = measured(rows)
    threshold = statistics.median([r.annual_views for r in usable]) if usable else None
    for r in usable:
        r.quadrant = f.quadrant(r.yoy_growth, r.annual_views, threshold)
    return threshold


def apply_filters(rows: list[PortfolioRow], filters: PortfolioFilters) -> None:
    """Mark rows hidden by a filter (in place), with a code the report translates:
    `status:<status>`, `category`, `min_views` or `min_growth`. Unmeasured rows are hidden too."""
    wanted = {c.lower() for c in filters.categories}
    for r in rows:
        if r.status != "ok" or r.annual_views is None:
            r.excluded_by = f"status:{r.status}"
        elif wanted and (r.category or "").lower() not in wanted:
            r.excluded_by = "category"
        elif filters.min_views is not None and r.annual_views < filters.min_views:
            r.excluded_by = "min_views"
        elif filters.min_growth is not None and (r.yoy_growth is None or r.yoy_growth < filters.min_growth):
            r.excluded_by = "min_growth"


def label(r: PortfolioRow) -> str:
    return f"{r.canonical_topic or r.topic} · {r.project}"


def observations(rows: list[PortfolioRow], tr=None) -> list[str]:
    """Factual sentences over the visible rows, in the report language. No ranking words."""
    if tr is None:
        from wiki_market_intel.i18n import Translator
        tr = Translator("en")
    shown = [r for r in rows if r.excluded_by is None]
    if not shown:
        return [tr("pf_obs_none")]
    out = [tr("pf_obs_count", n=len(shown), topics=len({r.topic for r in shown}),
              editions=len({r.language for r in shown}))]
    top = max(shown, key=lambda r: r.annual_views)
    out.append(tr("pf_obs_top", label=label(top), views=tr.number(top.annual_views)))
    with_yoy = [r for r in shown if r.yoy_growth is not None]
    grew = [r for r in with_yoy if r.yoy_growth > 0]
    if with_yoy and not grew:
        out.append(tr("pf_obs_all_declined", n=len(with_yoy)))
    elif grew:
        names = ", ".join(label(r) for r in grew[:5]) + (tr("pf_obs_more") if len(grew) > 5 else "")
        out.append(tr("pf_obs_grew", n=len(grew), total=len(with_yoy), names=names))
    return out


def ready_answer(rows: list[PortfolioRow]) -> list[str]:
    """Quote-ready lines grouped by quadrant (input order inside each group), for agents."""
    shown = [r for r in rows if r.excluded_by is None]
    lines = [NO_VERDICT]
    for q in QUADRANT_ORDER:
        group = [r for r in shown if r.quadrant == q]
        if not group:
            continue
        lines.append(f"{q} ({QUADRANT_MEANING[q]}):")
        for r in group:
            parts = [f"{r.annual_views:,} views in the last 12 months"]
            parts.append(f"{r.yoy_growth * 100:+.1f}% year over year" if r.yoy_growth is not None
                         else "no year-over-year figure")
            if r.topic_affinity is not None:
                parts.append(f"affinity {r.topic_affinity:.2f} within the topic's editions")
            if r.momentum:
                parts.append(f"momentum {r.momentum}")
            lines.append(f"  - {label(r)}: " + ", ".join(parts) + ".")
    no_quadrant = [r for r in shown if r.quadrant is None]
    if no_quadrant:
        lines.append("no quadrant (no year-over-year figure for the last 12 months):")
    for r in no_quadrant:
        lines.append(f"  - {label(r)}: {r.annual_views:,} views in the last 12 months.")
    return lines


# A question that asks the data to pick or rank ("top 3", "best", "should we build").
RANKING_WORDS = re.compile(
    r"\b(top[\s-]*\d+|top|best|rank\w*|winners?|most promising|most attractive|priorit[iy]\w*|"
    r"should we (?:build|launch|pick|choose|go|enter|expand)|which (?:\w+ ){0,4}should|go/no-go|go or no-go)\b"
    r"|найкращ\w*|топ[\s-]*\d*|рейтинг\w*|пріоритет\w*|варто|обрати|вибрати",
    flags=re.IGNORECASE)
RANKING_OPENER = ("You asked {phrase}. Wikipedia pageviews can't decide that: they measure how much people read about "
                  "a topic, not revenue or demand for a product. What they can show is where attention is sizeable "
                  "and holding up, so the recommendation below gives the next step to validate.")


def ranking_phrase(question: str | None) -> str | None:
    """The words in the user's question that ask for a ranking or a pick, or None."""
    if not question:
        return None
    match = RANKING_WORDS.search(question)
    return f"'{match.group(0).strip()}'" if match else None
