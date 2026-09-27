"""Localization KPIs (spec §14-§18): penetration within an edition, and share, affinity
and quadrant across compared editions. These stay separate KPIs; nothing here
collapses them into one score (spec §18)."""

from __future__ import annotations

import statistics

from wiki_market_intel.analytics import formulas as f
from wiki_market_intel.analytics.periods import Period
from wiki_market_intel.models.metrics import LanguageOpportunityMetrics, MissingMetric, MonthlyPoint


def penetration(series: list[MonthlyPoint], edition: list[MonthlyPoint], last_12m: Period,
                edition_available: bool) -> tuple[float | None, list[MissingMetric]]:
    """Topic views / all views of the edition over the last 12 complete months."""
    if not edition_available:
        return None, [MissingMetric(metric="localization.topic_penetration", status="unavailable",
                                    reason="The edition-wide pageview totals could not be retrieved.")]
    topic = f.total(last_12m.values(series))
    total = f.total(last_12m.values(edition))
    value = f.topic_penetration(topic, total)
    if value is None:
        return None, [MissingMetric(metric="localization.topic_penetration", status="insufficient_data",
                                    reason="the last 12 months have months without topic or edition data")]
    return value, []


def edition_annual(edition: list[MonthlyPoint], last_12m: Period) -> float | None:
    return f.total(last_12m.values(edition))


def compare(rows: list[LanguageOpportunityMetrics], edition_totals: dict[str, float | None]) -> tuple[float | None, list[str]]:
    """Fill topic_share, topic_affinity and quadrant on the rows (in place).

    Share and affinity are relative to the editions compared *with data*; editions left out
    are named in the returned notes. Returns (demand threshold used for quadrants, notes).
    """
    notes: list[str] = []
    usable = [r for r in rows if r.status == "ok" and r.annual_views is not None]
    left_out = [r.language for r in rows if r not in usable]
    if left_out:
        notes.append(f"Share, affinity and quadrants are computed over {', '.join(r.language for r in usable) or 'no'} "
                     f"editions; left out (no article or incomplete data): {', '.join(left_out)}.")
    total_topic = sum(r.annual_views for r in usable) if usable else None   # type: ignore[misc]
    for row in usable:
        row.topic_share = f.topic_share(row.annual_views, total_topic)

    pooled = [r for r in usable if edition_totals.get(r.language) is not None]
    if pooled:
        pooled_topic = sum(r.annual_views for r in pooled)                  # type: ignore[misc]
        pooled_edition = sum(edition_totals[r.language] for r in pooled)    # type: ignore[misc]
        for row in pooled:
            row.topic_affinity = f.topic_affinity(row.annual_views, edition_totals[row.language],
                                                  pooled_topic, pooled_edition)
    missing_denominator = [r.language for r in usable if r not in pooled]
    if missing_denominator:
        notes.append(f"Topic affinity is null for {', '.join(missing_denominator)}: the edition-wide "
                     f"denominator is unavailable.")

    threshold = statistics.median([r.annual_views for r in usable]) if usable else None
    for row in usable:
        row.quadrant = f.quadrant(row.yoy_growth, row.annual_views, threshold)
    if len(usable) < 3:
        notes.append("With fewer than 3 editions the median split of the opportunity matrix is not meaningful.")
    return threshold, notes
