"""Data quality (spec §21) with explicit, documented level rules.

HIGH    coverage >= 98%, resolution confidence >= 0.90, requested period >= 24 months, no API errors
MEDIUM  coverage >= 90% and resolution confidence >= 0.70
LOW     anything else
"""

from __future__ import annotations

from wiki_market_intel.analytics.periods import Period
from wiki_market_intel.models.analysis import Quality
from wiki_market_intel.models.metrics import MissingMetric, MonthlyPoint
from wiki_market_intel.models.topic import TopicResolution

NOT_YET = [
    ("ecosystem.related_topics", "Not computed by `analyze`: run `cluster` to measure related topics."),
    ("signals", "Decision signals are planned for a later milestone."),
]
COUNTRY_REASON = ("Wikimedia publishes country-level pageviews per project (top-by-country), "
                  "not per article, so a topic's country distribution cannot be measured.")


ONLY_IN_COMPARISON = ("Only defined across several editions: run `compare` with the languages to compare "
                      "(the per-language results inside a comparison carry this value).")


def assess(series: list[MonthlyPoint], requested: Period, resolution: TopicResolution,
           metric_gaps: list[MissingMetric], api_errors: list[str], denominator_available: bool = False,
           anomaly_count: int | None = None) -> Quality:
    values = requested.values(series)
    covered = sum(v is not None for v in values)
    coverage = covered / len(values) if values else None
    missing_months = [f"{p.month}: no pageviews returned (zero views or no data)"
                      for p in series if requested.start.strftime("%Y-%m") <= p.month <= requested.end.strftime("%Y-%m")
                      and p.views is None]
    gaps = list(metric_gaps)
    gaps.append(MissingMetric(metric="localization.country_distribution", status="unsupported", reason=COUNTRY_REASON))
    gaps += [MissingMetric(metric=m, status="unavailable", reason=ONLY_IN_COMPARISON)
             for m in ("localization.topic_share", "localization.topic_affinity")]
    gaps += [MissingMetric(metric=m, status="unavailable" if m == "ecosystem.related_topics" else "not_implemented",
                           reason=r) for m, r in NOT_YET]

    confidence = resolution.confidence
    reasons: list[str] = []
    if coverage is not None and coverage >= 0.98 and confidence >= 0.90 and requested.months >= 24 and not api_errors:
        level = "HIGH"
    elif coverage is not None and coverage >= 0.90 and confidence >= 0.70:
        level = "MEDIUM"
    else:
        level = "LOW"
    if coverage is not None and coverage < 0.98:
        reasons.append(f"coverage {coverage:.1%} is below 98%")
    if confidence < 0.90:
        reasons.append(f"topic resolution confidence {confidence:.2f} is below 0.90")
    if requested.months < 24:
        reasons.append(f"requested period is {requested.months} months (under 24: seasonality not repeated)")
    if api_errors:
        reasons.append(f"{len(api_errors)} API error(s)")
    if not reasons:
        reasons.append("full coverage, confident topic match, at least two years of data")

    return Quality(
        coverage=coverage, missing_data=missing_months, missing_metrics=gaps, api_errors=api_errors,
        topic_resolution_confidence=confidence,
        language_mapping_confidence=1.0 if resolution.method != "no_wikidata" else None,
        anomaly_count=anomaly_count, country_data_available=False, unique_devices_available=False,
        project_denominator_available=denominator_available, quality_level=level, quality_reasons=reasons)
