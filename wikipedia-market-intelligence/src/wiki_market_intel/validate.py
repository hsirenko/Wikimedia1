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

from wiki_market_intel.analytics import demand, growth, localization, seasonality
from wiki_market_intel.analytics.periods import build_periods
from wiki_market_intel.models.analysis import AnalysisResult, ComparisonResult
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
    for section, (recomputed, _) in (("demand", demand.compute(result.monthly, periods)),
                                     ("growth", growth.compute(result.monthly, periods)),
                                     ("seasonality", seasonality.compute(result.monthly, periods["requested"]))):
        stored = getattr(result, section)
        for field in type(recomputed).model_fields:
            if field not in stored_raw.get(section, {}):
                continue   # written by an older version that did not have this field yet
            if not _same(getattr(stored, field), getattr(recomputed, field)):
                problems.append(f"{prefix}{section}.{field}: stored {getattr(stored, field)!r} "
                                f"!= recomputed {getattr(recomputed, field)!r}")
    if result.edition_monthly:
        pen, _ = localization.penetration(result.monthly, result.edition_monthly, periods["last_12m"], True)
        if not _same(result.localization.topic_penetration, pen):
            problems.append(f"{prefix}localization.topic_penetration: stored "
                            f"{result.localization.topic_penetration!r} != recomputed {pen!r}")
    return problems


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
    for stored, again in zip(result.rows, fresh):
        for field in ("topic_share", "topic_affinity", "quadrant"):
            if not _same(getattr(stored, field), getattr(again, field)):
                problems.append(f"{stored.language}: {field}: stored {getattr(stored, field)!r} "
                                f"!= recomputed {getattr(again, field)!r}")
    return problems


def validate_file(path: Path) -> list[str]:
    text = Path(path).read_text("utf-8")
    try:
        raw = json.loads(text)
        if Path(path).name == "comparison.json":
            return _check_comparison(ComparisonResult.model_validate(raw), raw)
        return _check_analysis(AnalysisResult.model_validate(raw), raw)
    except (ValidationError, ValueError) as exc:
        return [f"schema: {exc}"]


def find_reports(root: Path) -> list[Path]:
    root = Path(root)
    if root.is_file():
        return [root]
    return sorted([*root.rglob("analysis.json"), *root.rglob("comparison.json")])
