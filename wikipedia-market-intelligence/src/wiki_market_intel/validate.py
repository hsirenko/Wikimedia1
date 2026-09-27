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

from wiki_market_intel.analytics import demand, growth, seasonality
from wiki_market_intel.analytics.periods import build_periods
from wiki_market_intel.models.analysis import AnalysisResult


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    return a == b


def validate_file(path: Path) -> list[str]:
    text = Path(path).read_text("utf-8")
    try:
        result = AnalysisResult.model_validate_json(text)
        stored_raw = json.loads(text)
    except (ValidationError, ValueError) as exc:
        return [f"schema: {exc}"]
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
                problems.append(f"{section}.{field}: stored {getattr(stored, field)!r} "
                                f"!= recomputed {getattr(recomputed, field)!r}")
    return problems


def find_reports(root: Path) -> list[Path]:
    root = Path(root)
    return [root] if root.is_file() else sorted(root.rglob("analysis.json"))
