"""Seasonality KPIs (spec §12), computed over the requested period."""

from __future__ import annotations

import calendar
import statistics

from wiki_market_intel.analytics import formulas as f
from wiki_market_intel.analytics.periods import Period
from wiki_market_intel.models.metrics import MissingMetric, MonthlyPoint, Seasonality


def compute(series: list[MonthlyPoint], period: Period) -> tuple[Seasonality, list[MissingMetric]]:
    months = [p for p in series if f"{period.start:%Y-%m}" <= p.month <= f"{period.end:%Y-%m}" and p.views is not None]
    values = [float(p.views) for p in months]  # type: ignore[arg-type]
    by_calendar: dict[int, list[float]] = {}
    for point in months:
        by_calendar.setdefault(int(point.month[5:7]), []).append(float(point.views))  # type: ignore[arg-type]

    if len(by_calendar) < 12:
        return Seasonality(volatility=f.volatility(values)), [MissingMetric(
            metric="seasonality.peak_month", status="insufficient_data",
            reason=f"only {len(by_calendar)} of 12 calendar months have data in the requested period")]

    means = {m: statistics.fmean(v) for m, v in by_calendar.items()}
    years = min(len(v) for v in by_calendar.values())
    basis = (f"calendar-month means over {period.start:%Y-%m}..{period.end:%Y-%m} "
             f"({years} observation{'s' if years > 1 else ''} per month"
             + (": a single year, so one unusual month can decide the peak)" if years < 2 else ")"))
    peak = max(means, key=means.get)
    trough = min(means, key=means.get)
    return Seasonality(
        peak_month=calendar.month_name[peak],
        trough_month=calendar.month_name[trough],
        peak_to_average=f.peak_to_average(list(means.values())),
        trough_to_average=f.trough_to_average(list(means.values())),
        volatility=f.volatility(values),
        basis=basis,
    ), []
