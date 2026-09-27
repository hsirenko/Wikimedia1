"""`wiki-market validate`: check saved analyses against the schema and recompute their KPIs.

A report passes when its JSON matches the AnalysisResult schema and every KPI can be
recomputed from its own stored monthly series with the same result. That makes a
saved report self-verifying and guards against formula drift between versions.
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from wiki_market_intel.analytics import (
    anomalies, demand, growth, localization, portfolio, recommend, seasonality, signals,
)
from wiki_market_intel.analytics.periods import build_periods
from wiki_market_intel.models.analysis import AnalysisResult, ComparisonResult, PortfolioResult, PortfolioRow
from wiki_market_intel.models.metrics import LanguageOpportunityMetrics


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    return a == b


def _check_analysis(result: AnalysisResult, stored_raw: dict, prefix: str = "") -> list[str]:
    start = date.fromisoformat(result.metadata.period_start + "-01")
    end = date.fromisoformat(result.metadata.period_end + "-01")
    months = (end.year - start.year) * 12 + end.month - start.month + 1
    periods = build_periods(end, months)
    problems = []
    fresh = {"demand": demand.compute(result.monthly, periods)[0],
             "growth": growth.compute(result.monthly, periods)[0],
             "seasonality": seasonality.compute(result.monthly, periods["requested"])[0]}
    for section, recomputed in fresh.items():
        stored = getattr(result, section)
        for field in type(recomputed).model_fields:
            if field not in stored_raw.get(section, {}):
                continue   # written by an older version that did not have this field yet
            if not _same(getattr(stored, field), getattr(recomputed, field)):
                problems.append(f"{prefix}{section}.{field}: stored {getattr(stored, field)!r} "
                                f"!= recomputed {getattr(recomputed, field)!r}")
    if "anomalies" in stored_raw and result.anomaly_analysis is not None:
        found, info = anomalies.detect(result.monthly, periods["requested"])
        if [a.model_dump() for a in found] != [a.model_dump() for a in result.anomalies]:
            problems.append(f"{prefix}anomalies: stored {[a.date for a in result.anomalies]} "
                            f"!= recomputed {[a.date for a in found]}")
        excluded = anomalies.yoy_excluding(result.monthly, found, periods["last_12m"], periods["previous_12m"])
        if not _same(result.anomaly_analysis.yoy_excluding_anomalies, excluded):
            problems.append(f"{prefix}anomaly_analysis.yoy_excluding_anomalies: stored "
                            f"{result.anomaly_analysis.yoy_excluding_anomalies!r} != recomputed {excluded!r}")
    if result.ecosystem.computed:
        from wiki_market_intel.analytics import ecosystem as eco
        edition = eco.edition_yoy(result.edition_monthly, periods)
        for stored in result.ecosystem.related_topics:
            again = eco.measure(stored.model_copy(deep=True), periods, result.demand.annual_views, edition)
            for field in ("annual_views", "yoy_growth", "relative_size", "share_adjusted_yoy", "signal"):
                if not _same(getattr(stored, field), getattr(again, field)):
                    problems.append(f"{prefix}ecosystem[{stored.title}].{field}: stored {getattr(stored, field)!r} "
                                    f"!= recomputed {getattr(again, field)!r}")
        conc = eco.concentration(result.demand.annual_views, result.ecosystem.related_topics,
                                 result.topic.article_title)
        stored_conc = result.ecosystem.concentration
        if stored_raw.get("ecosystem", {}).get("concentration", {}).get("largest") is None:
            conc.largest = None      # written before the largest article was recorded
        if conc != stored_conc:
            problems.append(f"{prefix}ecosystem.concentration: stored != recomputed")
    if "growth_basis" in stored_raw.get("signals", {}):   # older reports had no signals
        # from KPIs recomputed out of the raw monthly series, not the stored ones
        found, info = anomalies.detect(result.monthly, periods["requested"])
        again, _ = signals.compute(fresh["demand"].annual_views, fresh["growth"], fresh["seasonality"],
                                   [a.date for a in found], info.months_checked,
                                   result.localization.topic_affinity)
        for field in (*signals.SIGNAL_NAMES, "growth_basis"):
            if getattr(result.signals, field) != getattr(again, field):
                problems.append(f"{prefix}signals.{field}: stored {getattr(result.signals, field)!r} "
                                f"!= recomputed {getattr(again, field)!r}")
    if result.recommendation is not None and "recommendation" in stored_raw:
        problems += _check_recommendation(result.recommendation, recommend.of_analysis(result, result.recommendation.criteria), prefix)
    if result.edition_monthly:
        pen, _ = localization.penetration(result.monthly, result.edition_monthly, periods["last_12m"], True)
        if not _same(result.localization.topic_penetration, pen):
            problems.append(f"{prefix}localization.topic_penetration: stored "
                            f"{result.localization.topic_penetration!r} != recomputed {pen!r}")
    return problems


def _check_recommendation(stored, again, prefix: str = "") -> list[str]:
    """The tiers and their order must follow from the report's own KPIs."""
    before = [(i.label, i.tier) for i in stored.items]
    after = [(i.label, i.tier) for i in again.items]
    if before != after:
        return [f"{prefix}recommendation: stored {before} != recomputed {after}"]
    return []


def _check_comparison(result: ComparisonResult, raw: dict) -> list[str]:
    problems = []
    for language, analysis in result.analyses.items():
        problems += _check_analysis(analysis, raw["analyses"][language], prefix=f"{language}: ")
    # Rebuild the cross-language KPIs from the stored per-language numbers.
    fresh = [LanguageOpportunityMetrics(language=r.language, project=r.project, status=r.status,
                                        annual_views=r.annual_views, yoy_growth=r.yoy_growth) for r in result.rows]
    edition_annual = {}
    for language, analysis in result.analyses.items():
        end = date.fromisoformat(analysis.metadata.period_end + "-01")
        edition_annual[language] = localization.edition_annual(analysis.edition_monthly,
                                                               build_periods(end, 12)["last_12m"])
    threshold, _ = localization.compare(fresh, edition_annual)
    if not _same(result.demand_threshold, threshold):
        problems.append(f"demand_threshold: stored {result.demand_threshold!r} != recomputed {threshold!r}")
    if result.recommendation is not None and "recommendation" in raw:
        problems += _check_recommendation(result.recommendation, recommend.of_comparison(result, result.recommendation.criteria))
    for stored, again in zip(result.rows, fresh):
        for field in ("topic_share", "topic_affinity", "quadrant"):
            if not _same(getattr(stored, field), getattr(again, field)):
                problems.append(f"{stored.language}: {field}: stored {getattr(stored, field)!r} "
                                f"!= recomputed {getattr(again, field)!r}")
    return problems


def _check_portfolio(result: PortfolioResult, raw: dict) -> list[str]:
    """Every embedded comparison/analysis recomputes, and the rows, split and filters follow from them."""
    problems = []
    for topic, c in result.comparisons.items():
        problems += [f"{topic}: {p}" for p in _check_comparison(c, raw["comparisons"][topic])]
    for topic, a in result.analyses.items():
        problems += _check_analysis(a, raw["analyses"][topic], prefix=f"{topic}: ")
    fresh: list[PortfolioRow] = []
    for item in result.metadata.topics:
        if item.topic in result.comparisons:
            fresh += portfolio.rows_from_comparison(item, result.comparisons[item.topic])
        elif item.topic in result.analyses:
            fresh.append(portfolio.row_from_analysis(item, result.analyses[item.topic]))
        else:
            fresh += [r.model_copy(update={"quadrant": None, "excluded_by": None})
                      for r in result.rows if r.topic == item.topic]      # unresolved: status rows only
    threshold = portfolio.assign_quadrants(fresh)
    portfolio.apply_filters(fresh, result.metadata.filters)
    if not _same(result.demand_threshold, threshold):
        problems.append(f"demand_threshold: stored {result.demand_threshold!r} != recomputed {threshold!r}")
    if len(fresh) != len(result.rows):
        return problems + [f"rows: stored {len(result.rows)} != recomputed {len(fresh)}"]
    if result.recommendation is not None and "recommendation" in raw:
        problems += _check_recommendation(result.recommendation, recommend.of_portfolio(result, result.recommendation.criteria))
    for stored, again in zip(result.rows, fresh):
        for field in ("annual_views", "yoy_growth", "three_month_growth", "topic_affinity", "quadrant", "excluded_by"):
            if not _same(getattr(stored, field), getattr(again, field)):
                problems.append(f"{stored.topic} {stored.language}: {field}: stored {getattr(stored, field)!r} "
                                f"!= recomputed {getattr(again, field)!r}")
    return problems


def validate_file(path: Path) -> list[str]:
    text = Path(path).read_text("utf-8")
    try:
        raw = json.loads(text)
        if Path(path).name == "comparison.json":
            return _check_comparison(ComparisonResult.model_validate(raw), raw)
        if Path(path).name == "portfolio.json":
            return _check_portfolio(PortfolioResult.model_validate(raw), raw)
        return _check_analysis(AnalysisResult.model_validate(raw), raw)
    except (ValidationError, ValueError) as exc:
        return [f"schema: {exc}"]


def find_reports(root: Path) -> list[Path]:
    root = Path(root)
    if root.is_file():
        return [root]
    return sorted([*root.rglob("analysis.json"), *root.rglob("comparison.json"), *root.rglob("portfolio.json")])
