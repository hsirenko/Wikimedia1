"""Topic ecosystem KPIs (spec §19-§20). Pure functions over already-collected series.

Each related topic is an *adjacent interest signal*: it says where Wikipedia readers'
attention sits around the focal topic, never that an article is a commercially adjacent
product (spec §19).

Signal rules, applied in this order (the first match wins):

| signal               | rule                                                                  |
|----------------------|-----------------------------------------------------------------------|
| too_small            | under 100 views a month (1,200 a year): any change is mostly noise    |
| larger_category      | a broader concept (subclass-of or facet-of target) with more views    |
| emerging_category    | share-adjusted YoY >= +10% (gaining attention relative to the edition)|
| declining_category   | share-adjusted YoY <= -10%                                            |
| adjacent_opportunity | annual views >= the focal topic's (and neither of the above)          |
| adjacent_interest    | everything else                                                       |

Share-adjusted YoY = (1 + topic YoY) / (1 + edition YoY) - 1. Wikipedia traffic is falling in
many editions, so raw YoY would label almost every topic "declining"; adjusting for the
edition keeps the label about the topic.

Concentration (spec §20) = views of the largest k articles / views of the whole cluster,
for k = 1, 5, 10, 20. The cluster is the focal topic plus its *typed* relations (broader,
narrower, facets). Text-similar articles are left out: search similarity pulls in popular,
unrelated pages (e.g. "Autism" next to "Meditation") that would dominate the shares. `None` when the cluster
has fewer than k articles. High concentration means attention sits on a few concepts; low
means it is spread out. Neither is labelled good or bad.
"""

from __future__ import annotations

from wiki_market_intel.analytics import formulas as f
from wiki_market_intel.analytics import growth as growth_kpis
from wiki_market_intel.analytics.periods import Period
from wiki_market_intel.models.metrics import Concentration, MonthlyPoint, RelatedTopic

SIGNAL_THRESHOLD = 0.10
MIN_ANNUAL_VIEWS = 1_200          # 100 a month: the same floor the confidence rules use
BROADER = ("broader", "facet_of")  # the related concept contains the focal topic


def edition_yoy(edition: list[MonthlyPoint], periods: dict[str, Period]) -> float | None:
    return f.yoy_growth(f.total(periods["last_12m"].values(edition)), f.total(periods["previous_12m"].values(edition)))


def share_adjusted(yoy: float | None, edition: float | None) -> float | None:
    """(1 + topic YoY) / (1 + edition YoY) - 1."""
    if yoy is None or edition is None or edition <= -1:
        return None
    return (1 + yoy) / (1 + edition) - 1


def signal(topic: RelatedTopic, focal_annual: int | None) -> str | None:
    if topic.annual_views is None:
        return None
    if topic.annual_views < MIN_ANNUAL_VIEWS:
        return "too_small"
    if topic.relationship in BROADER and focal_annual is not None and topic.annual_views > focal_annual:
        return "larger_category"
    if topic.share_adjusted_yoy is not None and topic.share_adjusted_yoy >= SIGNAL_THRESHOLD:
        return "emerging_category"
    if topic.share_adjusted_yoy is not None and topic.share_adjusted_yoy <= -SIGNAL_THRESHOLD:
        return "declining_category"
    if focal_annual is not None and topic.annual_views >= focal_annual:
        return "adjacent_opportunity"
    return "adjacent_interest"


def measure(topic: RelatedTopic, periods: dict[str, Period], focal_annual: int | None,
            edition: float | None) -> RelatedTopic:
    """Fill the KPIs and the signal of one related topic from its stored monthly series."""
    series = topic.monthly
    annual = f.total(periods["last_12m"].values(series))
    growth, _ = growth_kpis.compute(series, periods)
    topic.status = "ok" if any(p.views is not None for p in series) else "no_data"
    topic.annual_views = int(annual) if annual is not None else None
    topic.yoy_growth = growth.yoy
    topic.three_year_cagr = growth.three_year_cagr
    topic.three_month_growth = growth.last_three_month_growth
    topic.relative_size = (annual / focal_annual) if annual is not None and focal_annual else None
    topic.share_adjusted_yoy = share_adjusted(growth.yoy, edition)
    topic.signal = signal(topic, focal_annual)
    return topic


SIGNAL_ORDER = ["larger_category", "emerging_category", "adjacent_opportunity", "adjacent_interest",
                "declining_category", "too_small"]
SIGNAL_MEANING = {
    "larger_category": "a broader concept with more readers than the topic",
    "emerging_category": "gaining at least 10% relative to its edition",
    "adjacent_opportunity": "at least as many readers as the topic; its change is within 10 points of its "
                            "edition's, so it may still be falling",
    "adjacent_interest": "fewer readers than the topic; its change is within 10 points of its edition's, "
                         "so it may still be falling",
    "declining_category": "losing at least 10% relative to its edition",
    "too_small": "under 100 views a month, so its changes are mostly noise",
}


def headline(related: list[RelatedTopic], edition: float | None, project: str) -> str:
    """The honest answer to "which is the best?": how many related topics outpaced their edition.
    Counts only topics above the size floor that have a comparison."""
    measured = [t for t in related if t.signal not in (None, "too_small") and t.share_adjusted_yoy is not None]
    better = [t.title for t in measured if t.share_adjusted_yoy > 0]
    change = f" ({edition * 100:+.1f}% year over year)" if edition is not None else ""
    text = (f"Of {len(measured)} related topics with enough views and a year-over-year comparison, "
            f"{len(better)} grew faster than {project} as a whole{change}")
    text += f": {', '.join(better)}." if better else "."
    return text + " The data describes where readers' attention sits; it does not rank topics as opportunities."


def quote_ready(related: list[RelatedTopic], edition: float | None = None, project: str = "the edition") -> list[str]:
    """One complete, correct sentence per topic, grouped by signal, for an agent to quote verbatim.
    Each sentence already carries the caveats a small model tends to drop (text similarity,
    better/worse than the edition); none of them ranks topics. The first line is `headline`."""
    lines = [headline(related, edition, project)]
    for sig in SIGNAL_ORDER:
        group = [t for t in related if t.signal == sig]
        if not group:
            continue
        name = sig.replace("_", " ") + (" (a signal name, not a recommendation)" if sig == "adjacent_opportunity" else "")
        lines.append(f"{name}: {SIGNAL_MEANING[sig]}.")
        for t in group:
            parts = [f"{t.title}"]
            if t.relationship == "similar_content":
                parts[0] += " (found by text similarity only, not a stated relationship)"
            else:
                parts[0] += f" ({t.relationship.replace('_', ' ')} concept)"
            if t.annual_views is not None:
                size = f", {t.relative_size:.2f}x the topic" if t.relative_size is not None else ""
                parts.append(f"{t.annual_views:,} views in the last 12 months{size}")
            if t.yoy_growth is not None:
                parts.append(f"{t.yoy_growth * 100:+.1f}% year over year")
            if t.share_adjusted_yoy is not None:
                side = "better" if t.share_adjusted_yoy > 0 else "worse"
                parts.append(f"which is {abs(t.share_adjusted_yoy) * 100:.1f}% {side} than its edition")
            else:
                parts.append("no year-over-year comparison available")
            lines.append("  - " + ", ".join(parts) + ".")
    return lines


def concentration(focal_annual: int | None, related: list[RelatedTopic], focal_title: str | None = None) -> Concentration:
    typed = [r for r in related if r.relationship != "similar_content"]
    named = [(v, t) for v, t in [(focal_annual, focal_title), *((r.annual_views, r.title) for r in typed)] if v]
    named.sort(key=lambda pair: -pair[0])
    views = [v for v, _ in named]
    total = sum(views)
    if not total:
        return Concentration(articles=len(views))

    def top(k: int) -> float | None:
        return sum(views[:k]) / total if len(views) >= k else None

    return Concentration(articles=len(views), largest=named[0][1], top_1=top(1), top_5=top(5), top_10=top(10),
                         top_20=top(20))
