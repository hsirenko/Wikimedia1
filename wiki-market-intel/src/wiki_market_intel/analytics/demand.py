"""Demand KPIs (spec §10)."""

from __future__ import annotations

from wiki_market_intel.analytics import formulas as f
from wiki_market_intel.analytics.periods import Period
from wiki_market_intel.models.metrics import Demand, MissingMetric, MonthlyPoint

UNIQUE_DEVICES_REASON = ("Wikimedia publishes unique devices per project (whole language edition) only, "
                         "never per article.")


def compute(series: list[MonthlyPoint], periods: dict[str, Period]) -> tuple[Demand, list[MissingMetric]]:
    missing: list[MissingMetric] = []
    last12 = periods["last_12m"]
    annual = f.total(last12.values(series))
    if annual is None:
        missing.append(MissingMetric(metric="demand.annual_views", status="insufficient_data",
                                     reason=f"{last12.label} ({last12.start:%Y-%m}..{last12.end:%Y-%m}) has months "
                                            f"without data"))
    requested = periods["requested"]
    requested_total = f.total(requested.values(series))
    if requested_total is None:
        missing.append(MissingMetric(metric="demand.requested_period_views", status="insufficient_data",
                                     reason="the requested period has months without data"))
    missing += [
        MissingMetric(metric="demand.unique_devices", status="unsupported", reason=UNIQUE_DEVICES_REASON),
        MissingMetric(metric="demand.views_per_unique_device", status="unsupported", reason=UNIQUE_DEVICES_REASON),
    ]
    return Demand(
        annual_views=int(annual) if annual is not None else None,
        monthly_average=annual / 12 if annual is not None else None,
        daily_average=f.daily_average(annual, last12.days),
        requested_period_views=int(requested_total) if requested_total is not None else None,
        unique_devices=None,
        views_per_unique_device=None,
    ), missing
