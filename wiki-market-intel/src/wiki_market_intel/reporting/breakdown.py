"""KPI breakdown: one entry per KPI, after the recommendation, in the report language.

A single analysis gets a table (KPI, value, reading). Several options (comparison editions or
portfolio pairs) get one line per KPI across all options: every value when there are up to
six options, otherwise the range and counts. Options keep their input order.
"""

from __future__ import annotations

from collections.abc import Callable

from wiki_market_intel.analytics import signals as signal_kpis
from wiki_market_intel.analytics.ecosystem import share_adjusted

LIST_ALL = 6


def analysis_rows(result, tr, missing: Callable[[str], str], quality_reasons: list[str]) -> list[tuple[str, str, str]]:
    """(KPI, value, reading) rows for one topic in one edition."""
    d, g, s, sig = result.demand, result.growth, result.seasonality, result.signals
    explained = signal_kpis.explain(result, tr)
    na = tr("na")

    def pct(v):
        return tr.percent(v) if v is not None else na

    def reading(name: str) -> str:
        label = getattr(sig, name)
        if not label:
            return missing(f"signals.{name}")
        return f"**{tr(f'sig.{name}.{label}')}**. {explained.get(name, '')}".strip()

    rows = []
    views = f"{tr.number(d.annual_views)} ({tr('kpi_monthly', views=tr.number(d.monthly_average))})" \
        if d.annual_views is not None else missing("demand.annual_views")
    rows.append((tr("kpi_demand"), views, reading("market_size")))

    edition = signal_kpis.edition_yoy(result)
    rel = share_adjusted(g.yoy, edition)
    yoy_reading = (tr("kpi_vs_edition", edition=tr.percent(edition), pct=tr.percent(abs(rel), signed=False),
                      side=tr("kpi_better") if rel > 0 else tr("kpi_worse")) if rel is not None else na)
    rows.append((tr("kpi_yoy"), pct(g.yoy), yoy_reading))
    rows.append((tr("kpi_cagr"), pct(g.three_year_cagr), reading("growth")))
    rows.append((tr("kpi_momentum"), tr("kpi_m3_value", recent=pct(g.last_three_month_growth),
                                        previous=pct(g.previous_three_month_growth)), reading("momentum")))
    def month(name):   # Ukrainian month names are lowercase inside a sentence
        text = tr.month(name)
        return text.lower() if text and tr.lang == "uk" else text

    season = (tr("kpi_season_value", peak=month(s.peak_month), ratio=tr.decimal(s.peak_to_average),
                 trough=month(s.trough_month)) if s.peak_month else missing("seasonality.peak_month"))
    rows.append((tr("kpi_season"), season, reading("stability")))
    pen = result.localization.topic_penetration
    rows.append((tr("kpi_local"), tr("kpi_pen_value", value=tr.decimal(pen * 1_000_000, 1)) if pen is not None
                 else missing("localization.topic_penetration"), reading("localization")))
    info = result.anomaly_analysis
    if result.anomalies:
        flags = "; ".join(f"{a.date} {tr.percent(a.change_vs_baseline)}"
                          + (f", {tr('kpi_provisional')}" if a.provisional else "") for a in result.anomalies)
        rows.append((tr("kpi_anomalies"), tr("kpi_anomaly_count", n=len(result.anomalies)),
                     f"{flags}; {tr('kpi_cause_unknown')}"))
    else:
        rows.append((tr("kpi_anomalies"), tr("kpi_anomaly_none", n=info.months_checked if info else 0), ""))
    rows.append((tr("kpi_quality"), f"**{tr('level.' + result.quality.quality_level)}**", "; ".join(quality_reasons)))
    return rows


def unit_from_analysis(label: str, a, affinity: float | None = None) -> dict:
    return {"label": label, "views": a.demand.annual_views, "yoy": a.growth.yoy, "cagr": a.growth.three_year_cagr,
            "m3": a.growth.last_three_month_growth, "momentum": a.growth.momentum,
            "affinity": affinity if affinity is not None else a.localization.topic_affinity,
            "stability": a.signals.stability, "quality": a.quality.quality_level, "anomalies": len(a.anomalies)}


def multi_lines(units: list[dict], tr) -> list[str]:
    """One line per KPI across several options (input order kept)."""
    if not units:
        return []
    na = tr("na")

    def listed(key: str, fmt) -> str:
        have = [u for u in units if u[key] is not None]
        if not have:
            return na
        if len(units) <= LIST_ALL:
            return " · ".join(f"{u['label']} {fmt(u[key]) if u[key] is not None else na}" for u in units)
        low = min(have, key=lambda u: u[key])
        high = max(have, key=lambda u: u[key])
        return tr("kpi_range", low=fmt(low[key]), low_label=low["label"], high=fmt(high[key]), high_label=high["label"])

    def grouped(key: str, name) -> str:
        groups: dict[str, list[str]] = {}
        for u in units:
            groups.setdefault(name(u[key]) if u[key] is not None else na, []).append(u["label"])
        if len(units) <= LIST_ALL:
            return "; ".join(f"{k}: {', '.join(v)}" for k, v in groups.items())
        return "; ".join(f"{k}: {len(v)}" for k, v in groups.items())

    pct = tr.percent
    return [
        f"**{tr('kpi_demand')}:** {listed('views', tr.number)}",
        f"**{tr('kpi_yoy')}:** {listed('yoy', pct)}",
        f"**{tr('kpi_cagr')}:** {listed('cagr', pct)}",
        f"**{tr('kpi_momentum')}:** {grouped('momentum', lambda v: tr('momentum.' + v))}",
        f"**{tr('col_aff')}:** {listed('affinity', tr.decimal)}",
        f"**{tr('kpi_season')}:** {grouped('stability', lambda v: tr('sig.stability.' + v))}",
        f"**{tr('kpi_anomalies')}:** {listed('anomalies', str)}",
        f"**{tr('kpi_quality')}:** {grouped('quality', lambda v: tr('level.' + v))}",
    ]


def comparison_units(c) -> list[dict]:
    return [unit_from_analysis(c.analyses[r.language].metadata.project, c.analyses[r.language], r.topic_affinity)
            for r in c.rows if r.language in c.analyses and r.status == "ok"]


def portfolio_units(p) -> list[dict]:
    from wiki_market_intel.analytics.portfolio import label
    return [{"label": label(r), "views": r.annual_views, "yoy": r.yoy_growth, "cagr": r.three_year_cagr,
             "m3": r.three_month_growth, "momentum": r.momentum, "affinity": r.topic_affinity,
             "stability": r.signals.stability if r.signals else None, "quality": r.quality_level,
             "anomalies": r.anomaly_count} for r in p.visible]
