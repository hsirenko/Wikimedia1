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


class Localization(BaseModel):
    topic_share: float | None = None
    topic_affinity: float | None = None
    topic_penetration: float | None = None
    country_distribution: list[dict] = Field(default_factory=list)


class Signals(BaseModel):
    market_size: str | None = None
    growth: str | None = None
    momentum: str | None = None
    localization: str | None = None
    stability: str | None = None
