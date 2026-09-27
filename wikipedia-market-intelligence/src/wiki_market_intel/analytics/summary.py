"""Key observations: 3-5 factual sentences built only from computed KPIs (spec §24.1, §34).

Wording rules: state the measurement ("Pageviews increased 18.0% year over year"),
never an interpretation ("demand exploded", "a good opportunity").
"""

from __future__ import annotations

from wiki_market_intel.analytics.periods import Period
from wiki_market_intel.models.metrics import Demand, Growth, Seasonality


def compact(value: float | None) -> str:
    if value is None:
        return "n/a"
    for threshold, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= threshold:
            return f"{value / threshold:.1f}{suffix}"
    return f"{value:.0f}"


def pct(value: float | None, signed: bool = True) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:+.1f}%" if signed else f"{value * 100:.1f}%"


def _span(p: Period) -> str:
    return f"{p.start:%Y-%m}..{p.end:%Y-%m}"


def observations(demand: Demand, growth: Growth, seasonality: Seasonality, periods: dict[str, Period]) -> list[str]:
    out: list[str] = []
    if demand.annual_views is not None:
        out.append(f"Annual pageviews ({_span(periods['last_12m'])}) were {compact(demand.annual_views)} "
                   f"(about {compact(demand.monthly_average)} a month).")
    if growth.yoy is not None:
        verb = "increased" if growth.yoy > 0 else "decreased" if growth.yoy < 0 else "did not change"
        out.append(f"Pageviews {verb} {abs(growth.yoy) * 100:.1f}% year over year "
                   f"({_span(periods['last_12m'])} vs {_span(periods['previous_12m'])}).")
    if growth.three_year_cagr is not None:
        out.append(f"Three-year CAGR was {pct(growth.three_year_cagr)} "
                   f"(vs {_span(periods['twelve_months_3y_earlier'])}).")
    if growth.last_three_month_growth is not None:
        tail = f"; momentum {growth.momentum}" if growth.momentum else ""
        out.append(f"The last 3 months were {pct(growth.last_three_month_growth)} against the previous 3 months{tail}.")
    if seasonality.peak_month and seasonality.trough_month:
        out.append(f"{seasonality.peak_month} had the highest average monthly traffic "
                   f"({seasonality.peak_to_average:.2f}x the average) and {seasonality.trough_month} the lowest "
                   f"({seasonality.trough_to_average:.2f}x).")
    return out[:5]
