"""Normalized records and KPI sections.

Every KPI is nullable. A null value is never a zero: its reason is recorded in
`Quality.missing_metrics` (spec §30).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, NonNegativeInt


class PageviewRecord(BaseModel):
    """One normalized observation (spec §8). Raw API structures never reach analytics."""

    project: str
    language: str
    article_title: str
    article_id: str | None = None
    date: date                      # first day of the month for monthly data
    views: NonNegativeInt
    unique_devices: int | None = None
    access: str | None = None
    agent: str | None = None
    granularity: Literal["monthly", "daily"] = "monthly"
    source: str = "wikimedia"


class PeriodRef(BaseModel):
    label: str
    start: str                      # YYYY-MM
    end: str                        # YYYY-MM, inclusive
    months: int
    complete: bool                  # every month in the period has data


class Demand(BaseModel):
    annual_views: int | None = None             # last 12 complete months
    monthly_average: float | None = None
    daily_average: float | None = None
    requested_period_views: int | None = None
    unique_devices: int | None = None
    views_per_unique_device: float | None = None


class Growth(BaseModel):
    yoy: float | None = None                    # fractions: 0.18 means +18%
    three_year_cagr: float | None = None
    last_three_month_growth: float | None = None
    previous_three_month_growth: float | None = None
    acceleration: float | None = None           # difference of the two growth rates above
    momentum: Literal["accelerating", "stable", "decelerating"] | None = None
    period_over_period: float | None = None     # requested period vs previous equivalent period


class Seasonality(BaseModel):
    peak_month: str | None = None               # calendar month name, e.g. "January"
    trough_month: str | None = None
    peak_to_average: float | None = None
    trough_to_average: float | None = None
    volatility: float | None = None             # coefficient of variation of monthly views
    basis: str | None = None
    observations_per_month: int | None = None   # years behind each calendar-month mean


class MissingMetric(BaseModel):
    metric: str
    status: Literal["unsupported", "unavailable", "insufficient_data", "not_implemented", "api_error"]
    reason: str


class MonthlyPoint(BaseModel):
    month: str
    views: int | None               # None: the API returned nothing for this month


class Formula(BaseModel):
    name: str
    definition: str
    edge_cases: str = ""


class LanguageOpportunityMetrics(BaseModel):
    """One row of a language comparison (spec §14). Every value is nullable; `status` says why."""

    language: str
    project: str
    article_title: str | None = None
    status: Literal["ok", "no_article", "no_data"] = "ok"
    annual_views: int | None = None
    monthly_average: float | None = None
    unique_devices: int | None = None           # not published per article (see demand.unique_devices)
    yoy_growth: float | None = None
    three_year_cagr: float | None = None
    three_month_growth: float | None = None
    momentum: Literal["accelerating", "stable", "decelerating"] | None = None
    peak_month: str | None = None
    topic_share: float | None = None
    topic_penetration: float | None = None
    topic_affinity: float | None = None
    quadrant: Literal["investigate", "explore", "established", "watch"] | None = None
    quality_level: Literal["HIGH", "MEDIUM", "LOW"] | None = None
    anomaly_count: int | None = None


class Anomaly(BaseModel):
    date: str                                   # YYYY-MM
    actual: int
    expected: int
    change_vs_baseline: float                   # actual / expected - 1
    robust_z: float
    direction: Literal["spike", "drop"]
    severity: Literal["low", "medium", "high"]
    cause: Literal["unknown"] = "unknown"
    provisional: bool = False                   # too recent for a two-sided baseline


class AnomalyAnalysis(BaseModel):
    method: str = ("centered 12-month median level (6 before, 6 after) x leave-one-out seasonal factor; "
                   "robust z on log deviation")
    z_threshold: float = 3.5
    min_change: float = 0.25
    seasonal_adjustment: bool = False           # False when there were too few years for seasonal factors
    months_checked: int = 0
    yoy_excluding_anomalies: float | None = None


class RelatedTopic(BaseModel):
    """One adjacent concept (spec §19). An *adjacent interest signal*, not a product claim."""

    title: str                                  # article title in the analysed edition
    wikidata_id: str | None = None
    relationship: Literal["broader", "narrower", "facet_of", "has_facet", "similar_content"]
    source: str                                 # where the link came from, e.g. "wikidata:P279"
    status: Literal["ok", "no_data"] = "ok"
    annual_views: int | None = None
    yoy_growth: float | None = None
    three_year_cagr: float | None = None
    three_month_growth: float | None = None
    relative_size: float | None = None          # annual views / the focal topic's annual views
    share_adjusted_yoy: float | None = None     # YoY relative to the whole edition's YoY
    signal: Literal["larger_category", "emerging_category", "declining_category", "adjacent_opportunity",
                    "adjacent_interest", "too_small"] | None = None
    monthly: list[MonthlyPoint] = Field(default_factory=list)


class Concentration(BaseModel):
    """Share of cluster views held by the largest articles (spec §20). Neither good nor bad.
    The cluster is the focal topic plus its typed relations; text-similar articles are left out."""

    articles: int = 0
    largest: str | None = None                  # the article holding the top-1 share (may not be the topic)
    top_1: float | None = None
    top_5: float | None = None                  # None when the cluster has fewer articles than k
    top_10: float | None = None
    top_20: float | None = None


class Localization(BaseModel):
    topic_share: float | None = None
    topic_affinity: float | None = None
    topic_penetration: float | None = None
    country_distribution: list[dict] = Field(default_factory=list)


class Signals(BaseModel):
    """Five separate decision signals (spec §22); never combined into one score or verdict."""
    market_size: Literal["very_low", "low", "medium", "high", "very_high"] | None = None
    growth: Literal["declining", "stable", "growing", "strongly_growing"] | None = None
    momentum: Literal["decelerating", "stable", "accelerating"] | None = None
    localization: Literal["weak", "moderate", "strong"] | None = None
    stability: Literal["stable", "moderately_seasonal", "highly_seasonal", "volatile"] | None = None
    growth_basis: Literal["three_year_cagr", "yoy"] | None = None
    evidence: dict[str, str] = Field(default_factory=dict)   # English; the report rebuilds it per language
