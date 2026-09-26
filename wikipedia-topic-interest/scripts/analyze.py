#!/usr/bin/env python3
"""
Turn monthly pageview series into trend statements a founder can act on.

Everything here is pure: dicts in, dicts out, no network. That keeps it testable
and keeps the numbers reproducible for the same input.

Design notes, because the obvious approach is wrong in a specific way:
  * Growth is NOT (last - first) / first. One noisy month at either end swings that
    number wildly, and a single news spike can invent a trend. Direction comes from
    a Mann-Kendall test over every month, magnitude from a Theil-Sen slope, and the
    headline figure from a year-over-year block comparison that cancels seasonality.
  * Every series gets a confidence score with written reasons, so a weak signal
    cannot be quoted as if it were strong.
See references/ANALYSIS_METHODS.md for the full rationale and thresholds.
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
from typing import Any, Dict, List, Optional, Sequence

# --- thresholds, all in one place so they can be cited and tuned ---
SIGNIFICANCE_P = 0.05          # Mann-Kendall p below this = a real monotonic trend
FLAT_BAND_PCT = 10.0           # |year-over-year| under this is called flat
SPIKE_Z = 3.5                  # Iglewicz-Hoaglin robust outlier cutoff
SPIKE_SHARE_WARN = 0.25        # this much of all views from spikes = event-driven
LOW_VOLUME_MONTHLY = 100       # below this, monthly counts are mostly noise
THIN_VOLUME_MONTHLY = 500      # below this, treat conclusions as directional only
MIN_MONTHS_FOR_TREND = 6
MIN_MONTHS_FOR_YOY = 24
HIGH_VOLATILITY = 60.0         # robust coefficient of variation, percent
BOOTSTRAP_ROUNDS = 2000        # resamples for the year-over-year interval
BOOTSTRAP_SEED = 7             # fixed, so the same data always gives the same interval
INTERVAL_LEVEL = 0.90


# ---------------------------------------------------------------------------
# small statistics helpers (no scipy/numpy needed)
# ---------------------------------------------------------------------------

def _median(values: Sequence[float]) -> float:
    return statistics.median(values) if values else 0.0


def mad(values: Sequence[float]) -> float:
    """Median absolute deviation - a spread measure that spikes cannot inflate."""
    if not values:
        return 0.0
    med = _median(values)
    return _median([abs(v - med) for v in values])


def theil_sen_slope(ys: Sequence[float]) -> float:
    """Median of all pairwise slopes against an implicit 0,1,2... x axis.

    Resistant to outliers in a way least squares is not, which matters because
    pageview series are full of one-month spikes.
    """
    n = len(ys)
    if n < 2:
        return 0.0
    slopes = [(ys[j] - ys[i]) / (j - i) for i in range(n - 1) for j in range(i + 1, n)]
    return _median(slopes)


def mann_kendall(ys: Sequence[float]) -> Dict[str, float]:
    """Non-parametric monotonic trend test.

    Counts how often later values exceed earlier ones. Makes no assumption that
    the data is normal or linear, and answers the question that actually matters:
    is this rising consistently, or just wandering?
    """
    n = len(ys)
    if n < MIN_MONTHS_FOR_TREND:
        return {"s": 0.0, "tau": 0.0, "p_value": 1.0, "n": n}

    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            s += (ys[j] > ys[i]) - (ys[j] < ys[i])

    # Variance of S, corrected for tied values.
    counts: Dict[float, int] = {}
    for y in ys:
        counts[y] = counts.get(y, 0) + 1
    tie_term = sum(c * (c - 1) * (2 * c + 5) for c in counts.values() if c > 1)
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if var_s <= 0:
        return {"s": float(s), "tau": 0.0, "p_value": 1.0, "n": n}

    # Continuity correction, then a two-sided normal-approximation p-value.
    z = (s - math.copysign(1, s)) / math.sqrt(var_s) if s != 0 else 0.0
    p = math.erfc(abs(z) / math.sqrt(2))
    tau = (2.0 * s) / (n * (n - 1))
    return {"s": float(s), "tau": round(tau, 3), "z": round(z, 2), "p_value": round(p, 4), "n": n}


def robust_scale(values: Sequence[float]) -> float:
    """A spread estimate that survives both outliers and flat series.

    MAD is the first choice, but it collapses to exactly zero whenever more than
    half the months share a value - common on low-traffic articles, and on any
    quiet series that later gets one viral month. A zero scale would make the
    spike detector divide by zero and report "no spikes" for the most obvious
    spike there is, so fall back to mean deviation from the median.
    """
    if not values:
        return 0.0
    scale = mad(values) * 1.4826
    if scale > 0:
        return scale
    med = _median(values)
    return statistics.mean([abs(v - med) for v in values])


def robust_cv(values: Sequence[float]) -> float:
    """Spread as a percentage of level, using median-based statistics."""
    med = _median(values)
    if med <= 0:
        return 0.0
    return round((robust_scale(values) / med) * 100, 1)


def find_spikes(values: Sequence[float]) -> List[int]:
    """Indices of months that stand far above the typical level."""
    if len(values) < 5:
        return []
    med = _median(values)
    scale = robust_scale(values)
    if scale <= 0:
        return []
    return [i for i, v in enumerate(values) if (v - med) / scale > SPIKE_Z]


def seasonality_strength(values: Sequence[float], months: Sequence[str]) -> Optional[float]:
    """How much of the month-to-month wobble repeats on a calendar cycle.

    Education and hobby topics are strongly seasonal (term time, holidays); knowing
    this stops the agent reading a September rise as genuine growth.
    """
    if len(values) < MIN_MONTHS_FOR_YOY:
        return None
    slope = theil_sen_slope(values)
    detrended = [v - slope * i for i, v in enumerate(values)]
    overall = statistics.pstdev(detrended)
    if overall <= 0:
        return None
    by_month: Dict[str, List[float]] = {}
    for month, value in zip(months, detrended):
        by_month.setdefault(month[5:7], []).append(value)
    month_means = [statistics.mean(v) for v in by_month.values() if v]
    if len(month_means) < 4:
        return None
    return round(min(1.0, statistics.pstdev(month_means) / overall), 2)


def seasonal_peak(values: Sequence[float], months: Sequence[str]) -> Optional[str]:
    """Calendar month ("09") that is highest on average after removing the trend.

    Only meaningful alongside a strong seasonality_strength; it tells a founder
    when a launch or campaign meets the most readers.
    """
    if len(values) < MIN_MONTHS_FOR_YOY:
        return None
    slope = theil_sen_slope(values)
    by_month: Dict[str, List[float]] = {}
    for month, value in zip(months, (v - slope * i for i, v in enumerate(values))):
        by_month.setdefault(month[5:7], []).append(value)
    return max(by_month, key=lambda m: statistics.mean(by_month[m])) if by_month else None


def months_above_last_year(values: Sequence[float]) -> Optional[int]:
    """Of the last 12 months, how many beat the same month a year earlier (0-12).

    The plainest consistency measure there is: 11/12 is a trend a CEO can see;
    6/12 is a coin toss whatever the headline says.
    """
    if len(values) < MIN_MONTHS_FOR_YOY:
        return None
    return sum(1 for recent, previous in zip(values[-12:], values[-24:-12]) if recent > previous)


# ---------------------------------------------------------------------------
# per-series analysis
# ---------------------------------------------------------------------------

def analyze_series(
    points: List[Dict[str, Any]],
    baseline: Optional[Dict[str, int]] = None,
    label: str = "",
) -> Dict[str, Any]:
    """Full statistical profile of one article in one language edition.

    points:   [{"month": "2024-01", "views": 1234}, ...] in chronological order
    baseline: {"2024-01": total_views_of_that_whole_edition, ...}, optional but
              needed for cross-language comparison and incompleteness detection
    """
    baseline = baseline or {}
    points = sorted(points, key=lambda p: p["month"])

    # Drop months where Wikimedia's own edition-wide total collapsed: that is a
    # pipeline gap, not a drop in interest. Without a baseline we cannot tell the
    # difference, so we only drop when we have evidence.
    excluded: List[Dict[str, Any]] = []
    if baseline:
        totals = [v for v in baseline.values() if v > 0]
        baseline_floor = _median(totals) * 0.5 if totals else 0
        kept = []
        for point in points:
            edition_total = baseline.get(point["month"])
            if edition_total is not None and edition_total < baseline_floor:
                excluded.append({"month": point["month"], "reason": "edition-wide pageview data incomplete"})
            else:
                kept.append(point)
        points = kept

    months = [p["month"] for p in points]
    views = [float(p["views"]) for p in points]

    if len(views) < 2:
        return {
            "label": label,
            "status": "insufficient_data",
            "months_observed": len(views),
            "note": "Fewer than two usable months of data; no trend can be computed.",
            "excluded_months": excluded,
            "series": [{"month": m, "views": int(v)} for m, v in zip(months, views)],
        }

    # Gaps: the API omits months with no recorded views entirely.
    gaps = _missing_months(months)

    mk = mann_kendall(views)
    spikes = find_spikes(views)
    spike_months = [months[i] for i in spikes]
    median_views = _median(views)
    spike_excess = sum(max(0.0, views[i] - median_views) for i in spikes)
    spike_share = round(spike_excess / sum(views), 3) if sum(views) else 0.0

    # Magnitude on a log scale, expressed as "x times per year", which is easier
    # to reason about than views-per-month and works across wildly different sizes.
    log_slope = theil_sen_slope([math.log(max(v, 1.0)) for v in views])
    annual_multiplier = round(math.exp(log_slope * 12), 2)

    yoy = _year_over_year(months, views)
    headline = yoy["change_pct"] if yoy else round((annual_multiplier - 1) * 100, 1)

    # Share of the edition's total traffic, in views per million. The comparable
    # number: 500 views in Czech Wikipedia is a far stronger signal than 500 in English.
    per_million = None
    if baseline:
        shares = [
            (v / baseline[m]) * 1_000_000
            for m, v in zip(months, views)
            if baseline.get(m)
        ]
        if shares:
            per_million = round(_median(shares), 2)

    direction = _direction(mk, headline)
    relative = relative_trend(months, views, baseline) if baseline else None
    confidence, reasons = _confidence(
        views=views, mk=mk, spike_share=spike_share, gaps=gaps, excluded=excluded,
        direction=direction, relative=relative,
    )
    seasonality = seasonality_strength(views, months)

    return {
        "label": label,
        "status": "ok",
        "months_observed": len(views),
        "period": {"from": months[0], "to": months[-1]},
        "volume": {
            "median_monthly": int(median_views),
            "latest_month": int(views[-1]),
            "total": int(sum(views)),
            "per_million_edition_views": per_million,
        },
        "trend": {
            "direction": direction,
            "headline_change_pct": headline,
            "headline_basis": "year-over-year (last 12 months vs previous 12)" if yoy
                              else "Theil-Sen slope extrapolated to 12 months",
            "annual_multiplier": annual_multiplier,
            "ci90_pct": yoy["ci90_pct"] if yoy else None,
            "months_up": months_above_last_year(views),
            "year_over_year": yoy,
            "kendall_tau": mk["tau"],
            "p_value": mk["p_value"],
            "significant": mk["p_value"] < SIGNIFICANCE_P,
            # Share-of-edition trend: isolates topic interest from platform-wide drift.
            "relative": relative,
            "headline_period": basis_short(yoy),
            "interpretation": interpret(
                {"direction": direction, "headline_change_pct": headline, "basis": basis_short(yoy)},
                relative,
            ),
        },
        "quality": {
            "confidence": confidence,
            "confidence_band": _band(confidence),
            "reasons": reasons,
            "volatility_pct": robust_cv(views),
            "spike_months": spike_months,
            "spike_share_of_views": spike_share,
            "seasonality_strength": seasonality,
            "seasonal_peak_month": seasonal_peak(views, months) if seasonality and seasonality > 0.5 else None,
            "missing_months": gaps,
            "excluded_months": excluded,
        },
        "series": [{"month": m, "views": int(v)} for m, v in zip(months, views)],
        # The topic's true share of its edition each month (views per million edition
        # views). Charting this, not rescaled raw views, is what shows whether a
        # decline is the topic's own or the platform's.
        "share_series": [
            {"month": m, "per_million": round(v / baseline[m] * 1_000_000, 3)}
            for m, v in zip(months, views) if baseline.get(m)
        ],
    }


def _missing_months(months: Sequence[str]) -> List[str]:
    if len(months) < 2:
        return []
    def index(month: str) -> int:
        year, mon = month.split("-")
        return int(year) * 12 + int(mon) - 1
    present = {index(m) for m in months}
    expected = range(index(months[0]), index(months[-1]) + 1)
    out = []
    for value in expected:
        if value not in present:
            out.append(f"{value // 12:04d}-{value % 12 + 1:02d}")
    return out


def _year_over_year(
    months: Sequence[str], views: Sequence[float], as_int: bool = True
) -> Optional[Dict[str, Any]]:
    """Compare the last 12 months with the 12 before them.

    Seasonal effects hit both blocks equally, so what is left is real movement.
    """
    if len(views) < MIN_MONTHS_FOR_YOY:
        return None
    recent, previous = views[-12:], views[-24:-12]
    recent_sum, previous_sum = sum(recent), sum(previous)
    if previous_sum <= 0:
        return None
    cast = (lambda v: int(v)) if as_int else (lambda v: round(v, 2))
    return {
        "recent_12m": {"period": f"{months[-12]}..{months[-1]}", "total": cast(recent_sum)},
        "previous_12m": {"period": f"{months[-24]}..{months[-13]}", "total": cast(previous_sum)},
        "change_pct": round(((recent_sum - previous_sum) / previous_sum) * 100, 1),
        "ci90_pct": yoy_interval(recent, previous),
    }


def yoy_interval(recent: Sequence[float], previous: Sequence[float]) -> Optional[List[float]]:
    """90% interval for the year-over-year change, by resampling calendar months.

    Each month is kept paired with the same month a year earlier, so seasonality
    stays cancelled. The width answers "how much does this figure depend on which
    months happened to be good?" - a -20% with an interval of -45..+5 is not a
    decline you can rely on. Fixed seed: same data, same interval, every run.
    """
    pairs = [(r, p) for r, p in zip(recent, previous)]
    if len(pairs) < 6 or sum(p for _, p in pairs) <= 0:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    changes = []
    for _ in range(BOOTSTRAP_ROUNDS):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        base = sum(p for _, p in sample)
        if base > 0:
            changes.append((sum(r for r, _ in sample) / base - 1) * 100)
    changes.sort()
    tail = (1 - INTERVAL_LEVEL) / 2
    low = changes[int(tail * len(changes))]
    high = changes[min(len(changes) - 1, int((1 - tail) * len(changes)))]
    return [round(low, 1), round(high, 1)]


def relative_trend(
    months: Sequence[str], views: Sequence[float], baseline: Dict[str, int]
) -> Optional[Dict[str, Any]]:
    """Trend in the topic's *share* of its edition's traffic.

    This is the single most important correction in the module. Wikipedia traffic
    is falling platform-wide (editions are down roughly 7-25% year over year), so
    almost every article's raw view count declines. Reporting that as "interest in
    your topic is falling" would be wrong: it is mostly the platform shrinking.

    Running the same tests on views-per-million-edition-views answers the question
    a founder actually asked - is this topic gaining or losing ground relative to
    everything else people read in that language?
    """
    paired = [(m, v, baseline[m]) for m, v in zip(months, views) if baseline.get(m)]
    if len(paired) < MIN_MONTHS_FOR_TREND:
        return None

    share_months = [m for m, _, _ in paired]
    shares = [(v / total) * 1_000_000 for _, v, total in paired]
    edition_views = [float(total) for _, _, total in paired]

    mk = mann_kendall(shares)
    share_yoy = _year_over_year(share_months, shares, as_int=False)
    edition_yoy = _year_over_year(share_months, edition_views)

    log_slope = theil_sen_slope([math.log(max(s, 1e-9)) for s in shares])
    headline = share_yoy["change_pct"] if share_yoy else round((math.exp(log_slope * 12) - 1) * 100, 1)
    direction = _direction(mk, headline)

    if direction == "growing":
        standing = "outperforming its edition"
    elif direction == "declining":
        standing = "underperforming its edition"
    else:
        standing = "tracking its edition"

    return {
        "direction": direction,
        "share_change_pct": headline,
        "share_ci90_pct": share_yoy["ci90_pct"] if share_yoy else None,
        "months_up": months_above_last_year(shares),
        "edition_change_pct": edition_yoy["change_pct"] if edition_yoy else None,
        "p_value": mk["p_value"],
        "significant": mk["p_value"] < SIGNIFICANCE_P,
        "vs_edition": standing,
        "basis": "year-over-year change in views per million edition views" if share_yoy
                 else "Theil-Sen slope of views per million, extrapolated to 12 months",
    }


def interpret(absolute: Dict[str, Any], relative: Optional[Dict[str, Any]]) -> str:
    """One sentence the agent can quote, holding both signals at once."""
    abs_pct = absolute["headline_change_pct"]
    # Name the period with the number: a bare "-59.6%" gets misquoted as "over the
    # whole window" by fast models.
    period = " " + absolute["basis"] if absolute.get("basis") else ""
    if not relative:
        return (
            f"Raw pageviews are {absolute['direction']} ({abs_pct:+.1f}%{period}). Without an "
            f"edition-wide baseline this cannot be separated from platform-wide traffic changes."
        )
    edition_pct = relative["edition_change_pct"]
    edition_clause = (
        f" while the whole edition moved {edition_pct:+.1f}%" if edition_pct is not None else ""
    )
    standing = relative["vs_edition"]
    if standing == "tracking its edition":
        # State the share figure here too. When it was omitted, models invented one.
        tail = (
            f"so the topic is holding its share (share of edition traffic "
            f"{relative['share_change_pct']:+.1f}%, within the ±{FLAT_BAND_PCT:.0f}% flat band): "
            "this looks like a platform-wide traffic change, "
            "not a change in how much this audience cares about the topic."
        )
    elif standing == "outperforming its edition":
        tail = (
            f"but its share of edition traffic is rising ({relative['share_change_pct']:+.1f}%), "
            f"so interest in the topic is gaining ground relative to everything else."
        )
    else:
        tail = (
            f"and its share of edition traffic is also falling ({relative['share_change_pct']:+.1f}%), "
            f"so the topic is losing ground faster than the platform overall."
        )
    return f"Raw pageviews {abs_pct:+.1f}%{period}{edition_clause}, {tail}"


def basis_short(yoy: Optional[Dict[str, Any]]) -> str:
    """The period a headline percentage covers, short enough to print beside it."""
    if yoy:
        return f"year over year ({yoy['recent_12m']['period']} vs {yoy['previous_12m']['period']})"
    return "per year, estimated from the trend slope (under 24 months, no year-over-year)"


def _direction(mk: Dict[str, float], headline: float) -> str:
    """Label the trend. Both effect size and significance must agree.

    The effect-size gate comes first and is not negotiable. Over 30-odd months the
    Mann-Kendall test will happily report p=0.0008 for a drift of a fraction of a
    percent, which is statistically real and commercially meaningless. Anything
    inside the flat band is called flat no matter how small the p-value.

    If the two tests disagree about the sign - a late spike can pull the headline
    one way while the month-by-month pattern points the other - the honest answer
    is "unclear" rather than picking whichever is more flattering.
    """
    if mk["n"] < MIN_MONTHS_FOR_TREND:
        return "too_short_to_judge"
    if abs(headline) < FLAT_BAND_PCT:
        return "flat"
    if mk["p_value"] >= SIGNIFICANCE_P:
        return "unclear"  # moved, but not consistently enough to call a trend
    if (headline > 0) != (mk["tau"] > 0):
        return "unclear"
    return "growing" if headline > 0 else "declining"


def _confidence(
    views: Sequence[float],
    mk: Dict[str, float],
    spike_share: float,
    gaps: Sequence[str],
    excluded: Sequence[Dict],
    direction: str,
    relative: Optional[Dict[str, Any]] = None,
) -> tuple:
    """A 0-100 trust score with the reasoning attached.

    Penalties are additive and deliberately blunt; the value of the score is that
    it always arrives with reasons the agent can quote verbatim.
    """
    score = 100.0
    reasons: List[str] = []
    median_views = _median(views)

    # Reasons name the threshold they tripped and the points they cost, so the agent
    # can explain a score instead of just repeating it.
    if median_views < LOW_VOLUME_MONTHLY:
        score -= 35
        reasons.append(
            f"-35: very low traffic, {int(median_views)} views/month median against a "
            f"{LOW_VOLUME_MONTHLY}/month floor for meaningful measurement; changes this small "
            f"are mostly noise."
        )
    elif median_views < THIN_VOLUME_MONTHLY:
        score -= 20
        reasons.append(
            f"-20: thin traffic, {int(median_views)} views/month median against a "
            f"{THIN_VOLUME_MONTHLY}/month reliability threshold; treat as directional only."
        )

    if len(views) < MIN_MONTHS_FOR_TREND:
        score -= 30
        reasons.append(
            f"-30: only {len(views)} months of data, below the {MIN_MONTHS_FOR_TREND} needed "
            f"for a trend test."
        )
    elif len(views) < MIN_MONTHS_FOR_YOY:
        score -= 10
        reasons.append(
            f"-10: {len(views)} months of data, below the {MIN_MONTHS_FOR_YOY} needed for a "
            f"year-over-year comparison, so seasonality is not cancelled out."
        )

    if mk["n"] >= MIN_MONTHS_FOR_TREND and mk["p_value"] >= SIGNIFICANCE_P:
        score -= 25
        reasons.append(
            f"-25: trend is not statistically significant (p={mk['p_value']}, needs <{SIGNIFICANCE_P}); "
            f"the movement is within what random variation would produce."
        )

    if spike_share > SPIKE_SHARE_WARN:
        score -= 20
        reasons.append(
            f"-20: {int(spike_share * 100)}% of all views come from isolated spike months "
            f"(over the {int(SPIKE_SHARE_WARN * 100)}% limit): likely news or an event, not a "
            f"durable shift in interest."
        )

    volatility = robust_cv(views)
    if volatility > HIGH_VOLATILITY:
        score -= 15
        reasons.append(
            f"-15: high volatility, {volatility}% robust CV against a {HIGH_VOLATILITY}% limit; "
            f"the series is unstable month to month."
        )

    if gaps:
        score -= 10
        reasons.append(
            f"-10: {len(gaps)} month(s) missing from the API response: {', '.join(gaps[:3])}."
        )

    if excluded:
        reasons.append(
            f"{len(excluded)} month(s) dropped because Wikimedia's edition-wide totals were "
            f"incomplete for them."
        )

    # A move that matches the whole edition tells you about Wikipedia, not the topic.
    if relative and direction in ("growing", "declining") and relative["vs_edition"] == "tracking its edition":
        score -= 15
        reasons.append(
            f"-15: raw views are {direction}, but the topic's share of edition traffic is not; the "
            f"edition as a whole moved {relative['edition_change_pct']:+.1f}%. This is platform "
            f"drift rather than a topic-specific signal."
        )

    score = max(0, min(100, round(score)))
    if not reasons:
        reasons.append("Long, stable, high-traffic series with a statistically significant trend.")
    return score, reasons


def _band(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 50:
        return "moderate"
    if score >= 30:
        return "low"
    return "very low"


# ---------------------------------------------------------------------------
# cross-series comparison
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = {"reach": 1.0, "intensity": 1.0, "momentum": 1.0}


def _percentile_ranks(values: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    """0..1 rank of each value among the others; ties share their average rank."""
    valid = {k: v for k, v in values.items() if v is not None}
    if len(valid) < 2:
        return {k: (0.5 if k in valid else None) for k in values}
    ordered = sorted(valid.values())
    last = len(ordered) - 1
    rank_of = {}
    for value in set(ordered):
        positions = [i for i, v in enumerate(ordered) if v == value]
        rank_of[value] = sum(positions) / len(positions) / last
    return {k: (rank_of[v] if v is not None else None) for k, v in values.items()}


def priority(rows: List[Dict[str, Any]], weights: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """Weighted priority score (0-100) from percentile ranks of reach, intensity, momentum.

    This lets a user's stated criteria ("growth matters twice as much as size") be
    computed rather than improvised by the model. Scores are relative to the series
    being compared: adding an edition can reorder the others. A missing axis (no
    baseline, so no intensity) is dropped and the remaining weights renormalised.
    """
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    axes = {
        "reach": _percentile_ranks({r["label"]: r["reach_median_monthly"] for r in rows}),
        "intensity": _percentile_ranks({r["label"]: r["intensity_per_million"] for r in rows}),
        "momentum": _percentile_ranks({
            r["label"]: r["relative_momentum_pct"] if r["relative_momentum_pct"] is not None
            else r["momentum_pct"] for r in rows}),
    }
    scored = []
    for row in rows:
        parts = {axis: ranks[row["label"]] for axis, ranks in axes.items()}
        used = {axis: w for axis, w in weights.items() if parts.get(axis) is not None and w > 0}
        total = sum(used.values())
        score = sum(parts[a] * w for a, w in used.items()) / total if total else 0.0
        scored.append({"label": row["label"], "priority_score": round(score * 100),
                       "confidence": row["confidence"], "tier": row["tier"]})
    return sorted(scored, key=lambda r: -r["priority_score"])


def compare(results: List[Dict[str, Any]], weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Rank analysed series and sort them into action tiers.

    Three axes are kept separate on purpose, because they answer different
    questions and conflating them into one number hides the trade-off:
      reach     - how many people look at this now (market size proxy)
      intensity - views per million edition views (how much this audience cares)
      momentum  - year-over-year change (is it heading up)
    `priority` combines them only when asked, with the user's weights stated.
    """
    usable = [r for r in results if r.get("status") == "ok"]
    if not usable:
        return {"ranking": [], "tiers": {}, "note": "No series had enough data to compare."}

    rows = []
    for result in usable:
        relative = result["trend"].get("relative")
        rows.append(
            {
                "label": result["label"],
                "reach_median_monthly": result["volume"]["median_monthly"],
                "intensity_per_million": result["volume"]["per_million_edition_views"],
                "momentum_pct": result["trend"]["headline_change_pct"],
                "direction": result["trend"]["direction"],
                "relative_momentum_pct": relative["share_change_pct"] if relative else None,
                "momentum_ci90_pct": result["trend"].get("ci90_pct"),
                "relative_ci90_pct": relative.get("share_ci90_pct") if relative else None,
                "relative_direction": relative["direction"] if relative else None,
                "vs_edition": relative["vs_edition"] if relative else None,
                "significant": result["trend"]["significant"],
                "confidence": result["quality"]["confidence"],
                "tier": _tier(result),
                "why": _why(result),
            }
        )

    # Rank on the share-of-edition move when we have it: with platform-wide traffic
    # falling, raw percentages would rank editions by how fast Wikipedia is shrinking
    # there rather than by interest in the topic.
    ranked = sorted(
        rows,
        key=lambda r: r["relative_momentum_pct"] if r["relative_momentum_pct"] is not None else r["momentum_pct"],
        reverse=True,
    )
    tiers: Dict[str, List[str]] = {"investigate_first": [], "worth_a_look": [], "deprioritise": []}
    for row in ranked:
        tiers[row["tier"]].append(row["label"])

    return {
        "ranking": ranked,
        "ranked_by": "share of edition traffic (falls back to raw views without a baseline)",
        "by_reach": [r["label"] for r in sorted(rows, key=lambda r: r["reach_median_monthly"], reverse=True)],
        "by_intensity": [
            r["label"]
            for r in sorted(
                [r for r in rows if r["intensity_per_million"] is not None],
                key=lambda r: r["intensity_per_million"],
                reverse=True,
            )
        ],
        "tiers": tiers,
        "separation": separation(ranked),
        "priority": priority(rows, weights),
        "weights": {**DEFAULT_WEIGHTS, **(weights or {})},
        "caveat": (
            "Tiers rank Wikipedia reading interest only. They are a research-ordering "
            "heuristic, not a demand forecast or a willingness-to-pay signal."
        ),
    }


def separation(ranked: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Is the top-ranked series really ahead of the runner-up, or within noise?

    Uses the 90% intervals of the same measure the ranking used (share of edition
    when available). Overlapping intervals mean the order between the two is not
    established by this data, and the agent must not present it as if it were.
    """
    if len(ranked) < 2:
        return None
    first, second = ranked[0], ranked[1]
    use_share = first["relative_ci90_pct"] is not None and second["relative_ci90_pct"] is not None
    a = first["relative_ci90_pct"] if use_share else first["momentum_ci90_pct"]
    b = second["relative_ci90_pct"] if use_share else second["momentum_ci90_pct"]
    measure = "share of edition traffic" if use_share else "raw views"
    if not a or not b:
        return {"leader": first["label"], "runner_up": second["label"], "reliable": None,
                "statement": f"{first['label']} ranks above {second['label']}, but there is not enough "
                             f"history (24 months) to put an interval on the gap."}
    reliable = a[0] > b[1]
    statement = (
        f"{first['label']} is ahead of {second['label']} on {measure} growth and the 90% intervals "
        f"do not overlap ({a[0]:+.0f}..{a[1]:+.0f}% vs {b[0]:+.0f}..{b[1]:+.0f}%): the gap is reliable."
        if reliable else
        f"{first['label']} ranks above {second['label']} on {measure} growth, but the 90% intervals "
        f"overlap ({a[0]:+.0f}..{a[1]:+.0f}% vs {b[0]:+.0f}..{b[1]:+.0f}%): treat them as not clearly different."
    )
    return {"leader": first["label"], "runner_up": second["label"], "measure": measure,
            "reliable": reliable, "statement": statement}


def _tier(result: Dict[str, Any]) -> str:
    """Sort a series into an action tier.

    Momentum is judged on share of edition traffic where available, so a topic is
    not condemned for a decline that the entire platform shares.
    """
    relative = result["trend"].get("relative")
    direction = relative["direction"] if relative else result["trend"]["direction"]
    reach = result["volume"]["median_monthly"]
    confidence = result["quality"]["confidence"]

    if reach < LOW_VOLUME_MONTHLY:
        return "deprioritise"  # too little traffic to conclude anything either way
    if direction == "declining" and confidence >= 50:
        return "deprioritise"
    if direction == "growing" and confidence >= 55:
        return "investigate_first"
    if direction == "growing" or reach >= THIN_VOLUME_MONTHLY:
        return "worth_a_look"
    return "deprioritise"


def _why(result: Dict[str, Any]) -> str:
    trend, volume, quality = result["trend"], result["volume"], result["quality"]
    parts = [
        f"raw {trend['headline_change_pct']:+.1f}% ({trend['direction']}, p={trend['p_value']})",
        f"{volume['median_monthly']:,} views/month",
    ]
    relative = trend.get("relative")
    if relative:
        parts.append(f"share {relative['share_change_pct']:+.1f}% ({relative['vs_edition']})")
    if volume["per_million_edition_views"] is not None:
        parts.append(f"{volume['per_million_edition_views']} per million edition views")
    parts.append(f"confidence {quality['confidence']}/100 ({quality['confidence_band']})")
    return "; ".join(parts)


def main() -> int:
    """Analyse a JSON bundle: {"series": [{"label":..,"points":[..],"baseline":{..}}]}"""
    source = sys.stdin if len(sys.argv) < 2 else open(sys.argv[1], encoding="utf-8")
    with source as fh:
        bundle = json.load(fh)
    results = [
        analyze_series(item["points"], item.get("baseline"), item.get("label", ""))
        for item in bundle["series"]
    ]
    print(json.dumps({"series": results, "comparison": compare(results)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
