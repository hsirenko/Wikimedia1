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
]
