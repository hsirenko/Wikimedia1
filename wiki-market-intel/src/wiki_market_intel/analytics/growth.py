"""Growth KPIs (spec §11). Historical measurements, not predictions."""

from __future__ import annotations

from wiki_market_intel.analytics import formulas as f
from wiki_market_intel.analytics.periods import Period
from wiki_market_intel.models.metrics import Growth, MissingMetric, MonthlyPoint


def _total(period: Period, series: list[MonthlyPoint]) -> float | None:
    return f.total(period.values(series))


def compute(series: list[MonthlyPoint], periods: dict[str, Period]) -> tuple[Growth, list[MissingMetric]]:
    missing: list[MissingMetric] = []

    def need(metric: str, value: float | None, *needed: Period) -> float | None:
        if value is None:
            gaps = [p for p in needed if not p.is_complete(series)]
            reason = ("; ".join(f"{p.label} ({p.start:%Y-%m}..{p.end:%Y-%m}) has months without data" for p in gaps)
                      or "the comparison base is zero, so a growth rate is undefined")
            missing.append(MissingMetric(metric=f"growth.{metric}", status="insufficient_data", reason=reason))
        return value

    p = periods
    yoy = need("yoy", f.yoy_growth(_total(p["last_12m"], series), _total(p["previous_12m"], series)),
               p["last_12m"], p["previous_12m"])
    cagr3 = need("three_year_cagr", f.cagr(_total(p["twelve_months_3y_earlier"], series),
                                           _total(p["last_12m"], series), 3),
                 p["twelve_months_3y_earlier"], p["last_12m"])
    last3 = need("last_three_month_growth", f.growth_rate(_total(p["last_3m"], series), _total(p["previous_3m"], series)),
                 p["last_3m"], p["previous_3m"])
    prev3 = need("previous_three_month_growth",
                 f.growth_rate(_total(p["previous_3m"], series), _total(p["preceding_3m"], series)),
                 p["previous_3m"], p["preceding_3m"])
    accel = f.acceleration(last3, prev3)
    pop = need("period_over_period",
               f.growth_rate(_total(p["requested"], series), _total(p["previous_equivalent"], series)),
               p["requested"], p["previous_equivalent"])
    return Growth(yoy=yoy, three_year_cagr=cagr3, last_three_month_growth=last3,
                  previous_three_month_growth=prev3, acceleration=accel,
                  momentum=f.momentum_label(accel), period_over_period=pop), missing
