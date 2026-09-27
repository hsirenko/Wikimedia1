"""Anomaly detection (spec §13): flag unusual months, never explain them.

Expected value for month t (documented in the README and the formula registry):

    level(t)    = median of the 6 months before and the 6 months after t, excluding t itself
                  (at least 6 with data); used to learn the seasonal factors
    expected(t) = the better fit of  median(6 months before) x factor  and
                  median(6 months after) x factor  (each side needs 3 months with data)

Taking the better-fitting side matters at a permanent level shift: the last month before a
step matches the months before it, the first month after matches the months after, so a
step is not reported as a spike plus a drop. A real spike stands out against both sides.
    factor(m,t) = median over OTHER years of views / level for the same calendar month m
                  (leave-one-out, so a spike cannot inflate its own baseline);
                  1.0 when fewer than 2 other years exist (no seasonal adjustment)
    expected(t) = level(t) * factor(m,t)

Deviation is measured on a log scale, log(actual / expected), and scaled robustly:

    robust_z = 0.6745 * (dev - median(dev)) / MAD(dev)

A month is flagged when |robust_z| > 3.5 AND |actual / expected - 1| >= 25%. The effect-size
gate matters: on a very smooth series MAD is tiny and a 5% wobble would otherwise score as
"extreme". Recurring seasonal peaks are absorbed by the seasonal factor, so a January that is
high every year is not an anomaly; a January far above other Januaries is.

Severity: high if |change| >= 100% or |z| > 7; medium if |change| >= 50% or |z| > 5; else low.
Flags in the last 3 months are marked provisional: no later months exist yet to anchor their
baseline, so the next data release can change them.
Cause is always "unknown": the data shows that traffic moved, not why (spec §13, rule 5).
"""

from __future__ import annotations

import math
import statistics

from wiki_market_intel.analytics import formulas as f
from wiki_market_intel.analytics.periods import Period
from wiki_market_intel.models.metrics import Anomaly, AnomalyAnalysis, MonthlyPoint

Z_THRESHOLD = 3.5
MIN_CHANGE = 0.25
HALF_WINDOW = 6
MIN_LEVEL_MONTHS = 6
PROVISIONAL_MONTHS = 3


def _level(values: list[float | None], t: int) -> float | None:
    lo = max(0, t - HALF_WINDOW)
    window = [v for i, v in enumerate(values[lo:t + HALF_WINDOW + 1], start=lo)
              if i != t and v is not None and v > 0]
    return statistics.median(window) if len(window) >= MIN_LEVEL_MONTHS else None


def _side(values: list[float | None], t: int, before: bool) -> float | None:
    window = values[max(0, t - HALF_WINDOW):t] if before else values[t + 1:t + 1 + HALF_WINDOW]
    usable = [v for v in window if v is not None and v > 0]
    return statistics.median(usable) if len(usable) >= 3 else None


def seasonal_factors(series: list[MonthlyPoint]) -> tuple[list[float], bool]:
    """Leave-one-out seasonal factor per month (1.0 where fewer than 2 other years exist)."""
    values = [float(p.views) if p.views is not None else None for p in series]
    levels = [_level(values, t) for t in range(len(values))]
    ratios: dict[int, list[tuple[int, float]]] = {}
    for t, (point, v, level) in enumerate(zip(series, values, levels)):
        if v is not None and level:
            ratios.setdefault(int(point.month[5:7]), []).append((t, v / level))
    seasonal_used = False
    factors: list[float] = []
    for t, point in enumerate(series):
        others = [r for u, r in ratios.get(int(point.month[5:7]), []) if u != t]
        if len(others) >= 2:
            factors.append(statistics.median(others))
            seasonal_used = True
        else:
            factors.append(1.0)
    return factors, seasonal_used


def expected_values(series: list[MonthlyPoint]) -> tuple[list[float | None], bool]:
    """Expected views per month (None where no baseline exists), and whether seasonality was used."""
    values = [float(p.views) if p.views is not None else None for p in series]
    factors, seasonal_used = seasonal_factors(series)
    expected: list[float | None] = []
    for t, (actual, factor) in enumerate(zip(values, factors)):
        options = [side * factor for side in (_side(values, t, True), _side(values, t, False)) if side]
        if not options:
            expected.append(None)
        elif actual is None or actual <= 0 or len(options) == 1:
            expected.append(options[0])
        else:
            expected.append(min(options, key=lambda e: abs(math.log(actual / e))))
    return expected, seasonal_used


def detect(series: list[MonthlyPoint], period: Period) -> tuple[list[Anomaly], AnomalyAnalysis]:
    """Anomalies inside `period`. Months before it are used only to build baselines."""
    expected, seasonal_used = expected_values(series)
    start, end = f"{period.start:%Y-%m}", f"{period.end:%Y-%m}"
    candidates = []
    last_month = max((p.month for p in series if p.views is not None), default=end)
    recent = {m.month for m in series[-PROVISIONAL_MONTHS:]} if series else set()
    for point, exp in zip(series, expected):
        if exp and point.views is not None and point.views > 0:
            candidates.append((point, exp, math.log(point.views / exp)))
    info = AnomalyAnalysis(seasonal_adjustment=seasonal_used,
                           months_checked=sum(1 for p, _, _ in candidates if start <= p.month <= end))
    if len(candidates) < 6:
        return [], info
    deviations = [d for _, _, d in candidates]
    centre = statistics.median(deviations)
    mad = statistics.median(abs(d - centre) for d in deviations) or 1e-9
    found = []
    for point, exp, dev in candidates:
        if not start <= point.month <= end:
            continue
        z = 0.6745 * (dev - centre) / mad
        # The report shows expected as whole views; derive the change from that same number,
        # so anyone recomputing actual / expected - 1 from the table gets the printed figure.
        change = point.views / max(1, round(exp)) - 1
        if abs(z) > Z_THRESHOLD and abs(change) >= MIN_CHANGE:
            severity = ("high" if abs(change) >= 1.0 or abs(z) > 7 else
                        "medium" if abs(change) >= 0.5 or abs(z) > 5 else "low")
            found.append(Anomaly(date=point.month, actual=point.views, expected=round(exp),
                                 change_vs_baseline=round(change, 4), robust_z=round(z, 2),
                                 direction="spike" if change > 0 else "drop", severity=severity,
                                 provisional=point.month in recent and point.month <= last_month))
    return found, info


def yoy_excluding(series: list[MonthlyPoint], anomalies: list[Anomaly], last_12m: Period,
                  previous_12m: Period) -> float | None:
    """YoY with every flagged month replaced by its expected value (spec rule 6)."""
    if not anomalies:
        return None
    replaced = {a.date: a.expected for a in anomalies}
    adjusted = [MonthlyPoint(month=p.month, views=replaced.get(p.month, p.views)) for p in series]
    return f.yoy_growth(f.total(last_12m.values(adjusted)), f.total(previous_12m.values(adjusted)))
