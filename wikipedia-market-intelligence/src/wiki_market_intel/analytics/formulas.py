"""Formula registry (spec §33). Every KPI in the system is defined here, once.

Conventions:
* Inputs that may be missing are `None`; a formula never treats missing as zero.
* Any formula whose inputs are missing, empty or would divide by zero returns `None`.
* Growth rates are fractions: 0.18 means +18%.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence

from wiki_market_intel.models.metrics import Formula


def total(values: Sequence[float | None]) -> float | None:
    """sum(values). None if the sequence is empty or any value is missing."""
    if not values or any(v is None for v in values):
        return None
    return sum(values)  # type: ignore[arg-type]


def average(values: Sequence[float | None]) -> float | None:
    """sum(values) / len(values). None if empty or any value is missing."""
    summed = total(values)
    return None if summed is None else summed / len(values)


def daily_average(period_total: float | None, days: int) -> float | None:
    """period_total / number of days in the period."""
    if period_total is None or days <= 0:
        return None
    return period_total / days


def growth_rate(current: float | None, previous: float | None) -> float | None:
    """current / previous - 1. Used for YoY, 3-month momentum and period-over-period.
    None if either side is missing or previous <= 0 (growth from zero is undefined)."""
    if current is None or previous is None or previous <= 0:
        return None
    return current / previous - 1


def yoy_growth(current_12m: float | None, previous_12m: float | None) -> float | None:
    """(current 12M / previous 12M) - 1."""
    return growth_rate(current_12m, previous_12m)


def cagr(start: float | None, end: float | None, years: float) -> float | None:
    """(end / start) ** (1 / years) - 1. None if start <= 0, end < 0, or years <= 0."""
    if start is None or end is None or start <= 0 or end < 0 or years <= 0:
        return None
    return (end / start) ** (1 / years) - 1


def acceleration(recent_growth: float | None, previous_growth: float | None) -> float | None:
    """recent 3M growth - previous 3M growth, in fraction points."""
    if recent_growth is None or previous_growth is None:
        return None
    return recent_growth - previous_growth


def peak_to_average(values: Sequence[float]) -> float | None:
    """max(values) / mean(values)."""
    if not values or statistics.fmean(values) <= 0:
        return None
    return max(values) / statistics.fmean(values)


def trough_to_average(values: Sequence[float]) -> float | None:
    """min(values) / mean(values)."""
    if not values or statistics.fmean(values) <= 0:
        return None
    return min(values) / statistics.fmean(values)


def volatility(values: Sequence[float]) -> float | None:
    """Coefficient of variation: population std(values) / mean(values).
    None with fewer than 3 values (too short to mean anything) or a zero mean."""
    if len(values) < 3 or statistics.fmean(values) <= 0:
        return None
    return statistics.pstdev(values) / statistics.fmean(values)


def views_per_unique_device(pageviews: float | None, unique_devices: float | None) -> float | None:
    """pageviews / unique devices. Not an engagement or retention measure."""
    if pageviews is None or unique_devices is None or unique_devices <= 0:
        return None
    return pageviews / unique_devices


def topic_share(topic_views: float | None, total_views: float | None) -> float | None:
    """topic views in one language / topic views across all compared languages."""
    if topic_views is None or total_views is None or total_views <= 0:
        return None
    return topic_views / total_views


def topic_penetration(topic_views: float | None, language_total_views: float | None) -> float | None:
    """topic views / all pageviews of that language edition ("Wikipedia topic penetration")."""
    return topic_share(topic_views, language_total_views)


def topic_affinity(topic_views: float | None, edition_views: float | None,
                   compared_topic_views: float | None, compared_edition_views: float | None) -> float | None:
    """Location quotient: how over- or under-represented the topic is in one edition,
    relative to the editions being compared.

        (topic views in L / all views of edition L)
        / (topic views in all compared editions / all views of those editions)

    1.0 = the topic takes the same share of attention as across the compared set; 2.0 = twice.
    This is this system's own formulation, relative to the compared set only - not an
    official Wikimedia metric, and it changes if you compare a different set of languages.
    None if any input is missing or a denominator is zero.
    """
    penetration = topic_penetration(topic_views, edition_views)
    pooled = topic_penetration(compared_topic_views, compared_edition_views)
    if penetration is None or pooled is None or pooled <= 0:
        return None
    return penetration / pooled


QUADRANTS = {   # (high growth, high demand) -> descriptive label, never a recommendation (spec §23)
    (True, True): "investigate", (True, False): "explore",
    (False, True): "established", (False, False): "watch",
}


def quadrant(growth: float | None, demand: float | None, demand_threshold: float | None,
             growth_threshold: float = 0.0) -> str | None:
    """Opportunity-matrix quadrant. High growth: YoY > growth_threshold (0 = any growth).
    High demand: annual views >= demand_threshold (the median of the compared editions)."""
    if growth is None or demand is None or demand_threshold is None:
        return None
    return QUADRANTS[(growth > growth_threshold, demand >= demand_threshold)]


MOMENTUM_THRESHOLD = 0.05   # 5 percentage points


def momentum_label(accel: float | None) -> str | None:
    """accelerating if acceleration > +5 pp, decelerating if < -5 pp, else stable.
    A historical measurement, not a prediction."""
    if accel is None:
        return None
    if accel > MOMENTUM_THRESHOLD:
        return "accelerating"
    if accel < -MOMENTUM_THRESHOLD:
        return "decelerating"
    return "stable"


REGISTRY: list[Formula] = [
    Formula(name="annual_views", definition="sum(monthly pageviews) over the last 12 complete months",
            edge_cases="null if any of the 12 months is missing"),
    Formula(name="monthly_average", definition="annual_views / 12"),
    Formula(name="daily_average", definition="annual_views / number of days in those 12 months"),
    Formula(name="yoy", definition="(last 12M / previous 12M) - 1", edge_cases="null if previous 12M <= 0 or incomplete"),
    Formula(name="three_year_cagr", definition="(last 12M / the 12M ending 36 months earlier) ** (1/3) - 1",
            edge_cases="null if the earlier 12M is incomplete or zero"),
    Formula(name="last_three_month_growth", definition="(last 3M / previous 3M) - 1"),
    Formula(name="previous_three_month_growth", definition="(previous 3M / the 3M before that) - 1"),
    Formula(name="acceleration", definition="last_three_month_growth - previous_three_month_growth",
            edge_cases="momentum: accelerating > +5 pp, decelerating < -5 pp, otherwise stable"),
    Formula(name="period_over_period", definition="(requested period total / previous equivalent period total) - 1"),
    Formula(name="peak_month / trough_month",
            definition="calendar month with the highest / lowest mean views across the requested period"),
    Formula(name="peak_to_average", definition="max(calendar-month means) / mean(calendar-month means)"),
    Formula(name="trough_to_average", definition="min(calendar-month means) / mean(calendar-month means)"),
    Formula(name="volatility", definition="pstdev(monthly views) / mean(monthly views) over the requested period",
            edge_cases="null with fewer than 3 months"),
    Formula(name="views_per_unique_device", definition="pageviews / unique devices",
            edge_cases="unique devices are published per project only, so this is null for articles"),
    Formula(name="coverage", definition="months with data / months in the requested period"),
    Formula(name="topic_penetration",
            definition="topic views / all views of that language edition, both over the last 12 months",
            edge_cases="same traffic class (access, agent) for both; 'Wikipedia topic penetration', not market penetration"),
    Formula(name="topic_share",
            definition="topic views in one edition / topic views across all compared editions (last 12 months)",
            edge_cases="relative to the compared set; editions without data are excluded and listed"),
    Formula(name="topic_affinity",
            definition="(topic views / edition views) / (compared topic views / compared edition views)",
            edge_cases="location quotient relative to the compared editions; not an official Wikimedia metric"),
    Formula(name="anomaly_expected",
            definition="better fit of median(6 months before) and median(6 months after) x seasonal factor; "
                       "seasonal factor = median over other years of views / centered 12-month median, same calendar month",
            edge_cases="leave-one-out, so a spike cannot raise its own baseline; factor 1.0 with fewer than 2 other years"),
    Formula(name="anomaly_flag",
            definition="robust z = 0.6745 x (log(actual/expected) - median) / MAD > 3.5 and |actual/expected - 1| >= 25%",
            edge_cases="flags in the last 3 months are provisional; cause is always 'unknown'"),
    Formula(name="yoy_excluding_anomalies",
            definition="YoY with every flagged month replaced by its expected value",
            edge_cases="null when nothing is flagged; shows whether growth rests on one-off months (spec rule 6)"),
    Formula(name="related_topics",
            definition="Wikidata P279 subclass-of (broader / reverse: narrower), P1269 facet-of (facet_of / "
                       "reverse: has_facet), and text similarity (similar_content, labelled separately)",
            edge_cases="deduplicated with typed relations first; capped at 20; concepts without an article in "
                       "the edition are skipped and counted"),
    Formula(name="share_adjusted_yoy", definition="(1 + topic YoY) / (1 + edition YoY) - 1"),
    Formula(name="ecosystem_signal",
            definition="too_small (<1,200 views/yr) > larger_category (broader or facet-of target, more views) > "
                       "emerging (share-adjusted YoY >= +10%) > declining (<= -10%) > adjacent_opportunity "
                       "(views >= topic) > adjacent_interest",
            edge_cases="adjacent interest signals only, never a claim of commercial adjacency"),
    Formula(name="concentration_top_k",
            definition="views of the k largest articles / views of the topic plus its typed relations, k = 1, 5, 10, 20",
            edge_cases="null when the cluster has fewer than k articles; text-similar articles excluded"),
    Formula(name="signal_market_size",
            definition="annual views (last 12 months): very_low < 12,000 <= low < 60,000 <= medium < 300,000 "
                       "<= high < 1,500,000 <= very_high",
            edge_cases="absolute on purpose (spec §22), so larger editions read higher for the same topic"),
    Formula(name="signal_growth",
            definition="3-year CAGR (YoY when there is no CAGR): declining < -3% <= stable < +3% <= growing "
                       "< +15% <= strongly_growing",
            edge_cases="raw pageviews; the explanation adds the whole edition's YoY for context"),
    Formula(name="signal_momentum", definition="the momentum label: acceleration > +5 points accelerating, "
                                               "< -5 points decelerating, else stable"),
    Formula(name="signal_localization",
            definition="topic affinity: weak < 0.80 <= moderate < 1.25 <= strong",
            edge_cases="null outside a comparison, because affinity needs other editions"),
    Formula(name="signal_stability",
            definition="volatile if >= 2 anomaly episodes (runs of consecutive flagged months) and >= 1 per "
                       "12 months checked; else peak-to-average "
                       ">= 1.30 highly_seasonal, >= 1.12 moderately_seasonal, else stable",
            edge_cases="null without 2 years of each calendar month (seasonality cannot be told from noise)"),
    Formula(name="decision_signals",
            definition="five separate labels (market size, growth, momentum, localization, stability)",
            edge_cases="never combined into a single score, never a BUY / INVEST recommendation"),
    Formula(name="quadrant",
            definition="growth: YoY > 0; demand: annual views >= median of compared editions; "
                       "labels investigate / explore / established / watch are descriptive, not recommendations"),
]
