"""Key observations: 3-5 factual sentences built only from computed KPIs (spec §24.1, §34).

Wording rules: state the measurement ("Pageviews increased 18.0% year over year"),
never an interpretation ("demand exploded", "a good opportunity"). The sentences come
from the i18n catalog, so they read the same way in every report language.
"""

from __future__ import annotations

from wiki_market_intel.analytics.periods import Period
from wiki_market_intel.i18n import Translator
from wiki_market_intel.models.metrics import Demand, Growth, Seasonality

ENGLISH = Translator("en")


def compact(value: float | None) -> str:
    return "n/a" if value is None else ENGLISH.compact(value)


def pct(value: float | None, signed: bool = True) -> str:
    return "n/a" if value is None else ENGLISH.percent(value, signed)


def _span(start: str, end: str) -> str:
    return f"{start}..{end}"


def observations(demand: Demand, growth: Growth, seasonality: Seasonality, periods: dict[str, Period],
                 tr: Translator = ENGLISH) -> list[str]:
    spans = {name: _span(f"{p.start:%Y-%m}", f"{p.end:%Y-%m}") for name, p in periods.items()}
    return observations_from_spans(demand, growth, seasonality, spans, tr)


def observations_from_spans(demand: Demand, growth: Growth, seasonality: Seasonality, spans: dict[str, str],
                            tr: Translator = ENGLISH) -> list[str]:
    """`spans` maps period names (last_12m, previous_12m, twelve_months_3y_earlier) to 'YYYY-MM..YYYY-MM'."""
    out: list[str] = []
    if demand.annual_views is not None and demand.monthly_average is not None:
        out.append(tr("obs_annual", span=spans["last_12m"], views=tr.compact(demand.annual_views),
                      monthly=tr.compact(demand.monthly_average)))
    if growth.yoy is not None:
        key = "obs_yoy_up" if growth.yoy > 0 else "obs_yoy_down" if growth.yoy < 0 else "obs_yoy_flat"
        out.append(tr(key, pct=tr.percent(abs(growth.yoy), signed=False), span=spans["last_12m"],
                      prev=spans["previous_12m"]))
    if growth.three_year_cagr is not None:
        out.append(tr("obs_cagr", pct=tr.percent(growth.three_year_cagr), span=spans["twelve_months_3y_earlier"]))
    if growth.last_three_month_growth is not None:
        tail = tr("obs_3m_tail", label=tr(f"momentum.{growth.momentum}")) if growth.momentum else ""
        out.append(tr("obs_3m", pct=tr.percent(growth.last_three_month_growth), tail=tail))
    if seasonality.peak_month and seasonality.trough_month:
        out.append(tr("obs_season", peak=tr.month(seasonality.peak_month, in_form=True),
                      trough=tr.month(seasonality.trough_month, in_form=True),
                      peak_ratio=tr.decimal(seasonality.peak_to_average),
                      trough_ratio=tr.decimal(seasonality.trough_to_average)))
    return out[:5]
