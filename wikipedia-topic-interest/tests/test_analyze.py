#!/usr/bin/env python3
"""
Offline tests for the statistics. No network, deterministic.

The cases that matter most are the ones where a naive implementation gives a
confidently wrong answer: a flat series with one news spike, a partial final
month, and a tiny-traffic series.

Run:  python3 -m pytest tests -q     (from the skill directory)
"""

import math
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import analyze  # noqa: E402
from wm_api import month_window, parse_month, _encode_title, _ts_to_month  # noqa: E402


def months(count, start_year=2023, start_month=1):
    out = []
    year, month = start_year, start_month
    for _ in range(count):
        out.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def series(values, start_year=2023, start_month=1):
    return [{"month": m, "views": v} for m, v in zip(months(len(values), start_year, start_month), values)]


def flat_baseline(count, total=100_000_000, start_year=2023, start_month=1):
    return {m: total for m in months(count, start_year, start_month)}


# --------------------------------------------------------------------------
# statistical primitives
# --------------------------------------------------------------------------

def test_theil_sen_recovers_exact_slope_of_a_line():
    assert analyze.theil_sen_slope([10, 13, 16, 19, 22]) == 3.0


def test_theil_sen_ignores_a_single_wild_outlier():
    # Least squares would be dragged upward by the 9000; the median of pairwise
    # slopes should stay near the true slope of 1.
    clean = [float(v) for v in range(20)]
    dirty = list(clean)
    dirty[10] = 9000.0
    assert abs(analyze.theil_sen_slope(dirty) - 1.0) < 0.2


def test_mann_kendall_detects_monotonic_increase():
    result = analyze.mann_kendall(list(range(12)))
    assert result["tau"] == 1.0
    assert result["p_value"] < 0.001


def test_mann_kendall_finds_no_trend_in_an_alternating_series():
    result = analyze.mann_kendall([100, 90, 100, 90, 100, 90, 100, 90, 100, 90])
    assert result["p_value"] > 0.05


def test_mann_kendall_refuses_to_judge_very_short_series():
    assert analyze.mann_kendall([1, 5, 9])["p_value"] == 1.0


def test_mad_is_unmoved_by_an_extreme_value():
    assert analyze.mad([10, 10, 10, 10, 10_000]) == 0.0


def test_robust_cv_of_a_constant_series_is_zero():
    assert analyze.robust_cv([500] * 12) == 0.0


# --------------------------------------------------------------------------
# trend direction
# --------------------------------------------------------------------------

def test_steady_growth_is_reported_as_growing():
    values = [int(1000 * (1.03 ** i)) for i in range(30)]
    result = analyze.analyze_series(series(values), flat_baseline(30))
    assert result["trend"]["direction"] == "growing"
    assert result["trend"]["significant"] is True
    assert result["trend"]["headline_change_pct"] > 25
    assert result["quality"]["confidence"] >= 75


def test_steady_decline_is_reported_as_declining():
    values = [int(5000 * (0.97 ** i)) for i in range(30)]
    result = analyze.analyze_series(series(values), flat_baseline(30))
    assert result["trend"]["direction"] == "declining"
    assert result["trend"]["headline_change_pct"] < 0


def test_stable_series_is_reported_as_flat_not_growing():
    values = [1000, 1020, 990, 1010, 995, 1005, 1015, 985, 1000, 1008, 992, 1002] * 2
    result = analyze.analyze_series(series(values), flat_baseline(24))
    assert result["trend"]["direction"] == "flat"
    assert abs(result["trend"]["headline_change_pct"]) < analyze.FLAT_BAND_PCT


def test_one_news_spike_on_a_flat_series_is_not_called_growth():
    """The failure mode this whole module exists to prevent.

    A flat series whose final month happens to carry a viral spike looks like
    explosive growth to a first-vs-last calculation.
    """
    values = [1000] * 23 + [40_000]
    result = analyze.analyze_series(series(values), flat_baseline(24))

    naive_growth = ((values[-1] - values[0]) / values[0]) * 100
    assert naive_growth > 3000  # what the naive method would have claimed

    assert result["trend"]["direction"] != "growing"
    assert "2024-12" in result["quality"]["spike_months"]
    assert result["quality"]["spike_share_of_views"] > analyze.SPIKE_SHARE_WARN
    assert result["quality"]["confidence"] < 60
    assert any("spike" in reason for reason in result["quality"]["reasons"])


def test_tiny_but_statistically_significant_drift_is_called_flat():
    """Significance is not the same as mattering.

    A perfectly monotonic 0.03%-per-month creep is highly significant over 36
    months and completely irrelevant to a product decision.
    """
    values = [int(10_000 * (1.0003 ** i)) for i in range(36)]
    mk = analyze.mann_kendall([float(v) for v in values])
    assert mk["p_value"] < 0.01  # the test really does fire

    result = analyze.analyze_series(series(values), flat_baseline(36))
    assert abs(result["trend"]["headline_change_pct"]) < analyze.FLAT_BAND_PCT
    assert result["trend"]["direction"] == "flat"


def test_direction_is_unclear_when_headline_and_pattern_disagree():
    """A late spike lifts the year-over-year figure while the months trend down."""
    values = [int(3000 * (0.97 ** i)) for i in range(23)] + [90_000]
    result = analyze.analyze_series(series(values), flat_baseline(24))
    assert result["trend"]["headline_change_pct"] > 0      # YoY pulled up by the spike
    assert result["trend"]["kendall_tau"] < 0              # month-by-month pattern falls
    assert result["trend"]["direction"] == "unclear"


def test_short_series_is_not_given_a_trend_verdict():
    result = analyze.analyze_series(series([100, 400, 900]), flat_baseline(3))
    assert result["trend"]["direction"] == "too_short_to_judge"
    assert result["quality"]["confidence"] < 60


# --------------------------------------------------------------------------
# year over year and seasonality
# --------------------------------------------------------------------------

def test_year_over_year_uses_twelve_month_blocks():
    values = [100] * 12 + [150] * 12
    result = analyze.analyze_series(series(values), flat_baseline(24))
    yoy = result["trend"]["year_over_year"]
    assert yoy["previous_12m"]["total"] == 1200
    assert yoy["recent_12m"]["total"] == 1800
    assert yoy["change_pct"] == 50.0
    assert result["trend"]["headline_basis"].startswith("year-over-year")


def test_year_over_year_is_skipped_when_history_is_too_short():
    result = analyze.analyze_series(series([100] * 18), flat_baseline(18))
    assert result["trend"]["year_over_year"] is None
    assert "Theil-Sen" in result["trend"]["headline_basis"]


def test_seasonal_series_with_no_real_growth_reports_seasonality_and_stays_flat():
    # A school-year shape repeated twice: high autumn, low summer, no underlying growth.
    season = [120, 130, 140, 135, 110, 60, 50, 90, 160, 170, 150, 125]
    result = analyze.analyze_series(series(season * 2), flat_baseline(24))
    assert result["quality"]["seasonality_strength"] is not None
    assert result["quality"]["seasonality_strength"] > 0.5
    assert result["trend"]["year_over_year"]["change_pct"] == 0.0


# --------------------------------------------------------------------------
# data quality
# --------------------------------------------------------------------------

def test_month_with_incomplete_edition_totals_is_dropped():
    """A collapsed edition-wide total means Wikimedia's data is missing, not that
    interest fell off a cliff. Dropping it protects the trend."""
    values = [1000] * 11 + [30]
    baseline = flat_baseline(12)
    baseline["2023-12"] = 1_000_000  # 1% of a normal month
    result = analyze.analyze_series(series(values), baseline)

    assert result["months_observed"] == 11
    assert result["quality"]["excluded_months"][0]["month"] == "2023-12"
    assert all(point["month"] != "2023-12" for point in result["series"])


def test_complete_months_are_never_dropped():
    result = analyze.analyze_series(series([1000] * 12), flat_baseline(12))
    assert result["months_observed"] == 12
    assert result["quality"]["excluded_months"] == []


def test_gap_in_the_api_response_is_detected_and_penalised():
    points = series([500] * 12)
    del points[5]  # the API omits months that have no data at all
    result = analyze.analyze_series(points, flat_baseline(12))
    assert "2023-06" in result["quality"]["missing_months"]
    assert any("missing" in reason for reason in result["quality"]["reasons"])


def test_low_traffic_series_gets_a_low_confidence_and_says_why():
    values = [int(20 * (1.05 ** i)) for i in range(24)]
    result = analyze.analyze_series(series(values), flat_baseline(24))
    assert result["quality"]["confidence"] <= 65
    assert any("low traffic" in reason.lower() for reason in result["quality"]["reasons"])


def test_single_data_point_is_refused_rather_than_guessed():
    result = analyze.analyze_series(series([100]), flat_baseline(1))
    assert result["status"] == "insufficient_data"


def test_empty_input_is_handled():
    assert analyze.analyze_series([], {})["status"] == "insufficient_data"


def test_per_million_normalisation_makes_editions_comparable():
    # Same 1000 views, but one edition is 100x bigger than the other.
    big = analyze.analyze_series(series([1000] * 12), flat_baseline(12, total=100_000_000))
    small = analyze.analyze_series(series([1000] * 12), flat_baseline(12, total=1_000_000))
    assert big["volume"]["per_million_edition_views"] == 10.0
    assert small["volume"]["per_million_edition_views"] == 1000.0


def test_per_million_is_none_without_a_baseline():
    result = analyze.analyze_series(series([1000] * 12), None)
    assert result["volume"]["per_million_edition_views"] is None


# --------------------------------------------------------------------------
# topic signal vs platform-wide drift
# --------------------------------------------------------------------------

def declining_baseline(count, start=100_000_000, rate=0.98):
    """An edition losing traffic month after month, as real editions currently are."""
    return {m: int(start * (rate ** i)) for i, m in enumerate(months(count))}


def test_article_falling_only_as_fast_as_its_edition_is_called_tracking():
    """The correction that matters most in practice.

    Wikipedia traffic is down platform-wide, so raw views decline for almost
    everything. A topic that keeps its share has not lost audience interest.
    """
    baseline = declining_baseline(30)
    # Exactly 50 views per million every month: share is perfectly constant.
    values = [int(baseline[m] / 1_000_000 * 50) for m in months(30)]
    result = analyze.analyze_series(series(values), baseline)

    assert result["trend"]["direction"] == "declining"        # raw views really do fall
    relative = result["trend"]["relative"]
    assert relative["vs_edition"] == "tracking its edition"   # but share is flat
    assert abs(relative["share_change_pct"]) < 1.0
    assert relative["edition_change_pct"] < 0
    assert "platform drift" in " ".join(result["quality"]["reasons"])
    assert "holding its share" in result["trend"]["interpretation"]


def test_article_losing_share_is_called_underperforming():
    baseline = declining_baseline(30)
    # Share halves over the window on top of the edition's own decline.
    values = [int(baseline[m] / 1_000_000 * (50 * (0.97 ** i))) for i, m in enumerate(months(30))]
    result = analyze.analyze_series(series(values), baseline)
    relative = result["trend"]["relative"]
    assert relative["vs_edition"] == "underperforming its edition"
    assert relative["share_change_pct"] < -10


def test_article_growing_while_its_edition_shrinks_is_outperforming():
    baseline = declining_baseline(30)
    values = [int(baseline[m] / 1_000_000 * (50 * (1.04 ** i))) for i, m in enumerate(months(30))]
    result = analyze.analyze_series(series(values), baseline)
    relative = result["trend"]["relative"]
    assert relative["vs_edition"] == "outperforming its edition"
    assert relative["share_change_pct"] > 20
    assert "gaining ground" in result["trend"]["interpretation"]


def test_tiering_does_not_punish_a_topic_for_platform_wide_decline():
    baseline = declining_baseline(30)
    holding = analyze.analyze_series(
        series([int(baseline[m] / 1_000_000 * 60) for m in months(30)]), baseline, label="holds share"
    )
    losing = analyze.analyze_series(
        series([int(baseline[m] / 1_000_000 * (60 * (0.96 ** i))) for i, m in enumerate(months(30))]),
        baseline, label="loses share",
    )
    comparison = analyze.compare([losing, holding])
    assert comparison["ranking"][0]["label"] == "holds share"
    assert "loses share" in comparison["tiers"]["deprioritise"]
    assert "holds share" not in comparison["tiers"]["deprioritise"]


def test_relative_trend_is_absent_without_a_baseline():
    result = analyze.analyze_series(series([1000] * 24), None)
    assert result["trend"]["relative"] is None
    assert "cannot be separated from platform-wide" in result["trend"]["interpretation"]


# --------------------------------------------------------------------------
# comparison and tiering
# --------------------------------------------------------------------------

def test_comparison_ranks_by_momentum_and_assigns_tiers():
    growing = analyze.analyze_series(
        series([int(2000 * (1.04 ** i)) for i in range(30)]), flat_baseline(30), label="uk: Astronomy"
    )
    declining = analyze.analyze_series(
        series([int(8000 * (0.96 ** i)) for i in range(30)]), flat_baseline(30), label="pl: Astronomia"
    )
    tiny = analyze.analyze_series(series([7] * 30), flat_baseline(30), label="cs: Astronomie")

    comparison = analyze.compare([declining, tiny, growing])

    assert comparison["ranking"][0]["label"] == "uk: Astronomy"
    assert "uk: Astronomy" in comparison["tiers"]["investigate_first"]
    assert "pl: Astronomia" in comparison["tiers"]["deprioritise"]
    assert "cs: Astronomie" in comparison["tiers"]["deprioritise"]
    assert "not a demand forecast" in comparison["caveat"]


def test_comparison_by_intensity_can_disagree_with_raw_reach():
    """The point of normalisation: a small edition can care more per capita."""
    big = analyze.analyze_series(
        series([5000] * 24), flat_baseline(24, total=500_000_000), label="en"
    )
    small = analyze.analyze_series(
        series([800] * 24), flat_baseline(24, total=2_000_000), label="cs"
    )
    comparison = analyze.compare([big, small])
    assert comparison["by_reach"][0] == "en"
    assert comparison["by_intensity"][0] == "cs"


def test_comparison_handles_all_series_failing():
    comparison = analyze.compare([analyze.analyze_series([], {})])
    assert comparison["ranking"] == []


# --------------------------------------------------------------------------
# date and URL handling
# --------------------------------------------------------------------------

def test_month_window_stops_at_the_last_complete_month():
    """Never include the month in progress: its total is partial and would read
    as a crash in interest."""
    start, end, start_m, end_m = month_window(12, today=date(2026, 3, 15))
    assert end_m == "2026-02"
    assert end == "20260228"
    assert start_m == "2025-03"
    assert start == "20250301"


def test_month_window_handles_january_rollover():
    _, end, _, end_m = month_window(6, today=date(2026, 1, 9))
    assert end_m == "2025-12"
    assert end == "20251231"


def test_month_window_ends_on_a_leap_day():
    _, end, _, _ = month_window(3, today=date(2024, 3, 1))
    assert end == "20240229"


def test_month_window_clamps_to_start_of_available_data():
    start, _, start_m, _ = month_window(600, today=date(2026, 3, 1))
    assert start_m == "2015-07"


def test_month_window_length_is_exact():
    start_m, end_m = month_window(24, today=date(2026, 6, 20))[2:]
    assert (start_m, end_m) == ("2024-06", "2026-05")


def test_parse_month_accepts_common_formats():
    for value in ("2024-03", "2024/03", "202403", "2024-03-15"):
        assert parse_month(value) == "2024-03"


def test_parse_month_rejects_nonsense():
    try:
        parse_month("last spring")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_titles_are_encoded_for_the_api():
    assert _encode_title("Intermittent fasting") == "Intermittent_fasting"
    assert _encode_title("Астрономія") == "%D0%90%D1%81%D1%82%D1%80%D0%BE%D0%BD%D0%BE%D0%BC%D1%96%D1%8F"
    # Slashes must be escaped or they break the REST path.
    assert "/" not in _encode_title("AC/DC")


def test_timestamp_parsing():
    assert _ts_to_month("2024030100") == "2024-03"


# ---------------------------------------------------------------------------
# regressions from Haiku 4.5 end-to-end runs
# ---------------------------------------------------------------------------

def test_holding_verdict_states_the_share_figure():
    """With no share number in a 'holding' verdict, models invented one (e.g. '-1.3%')."""
    baseline = declining_baseline(30)
    values = [int(baseline[m] / 1_000_000 * 50) for m in months(30)]
    result = analyze.analyze_series(series(values), baseline)
    relative = result["trend"]["relative"]

    assert relative["vs_edition"] == "tracking its edition"
    assert f"share of edition traffic {relative['share_change_pct']:+.1f}%" in result["trend"]["interpretation"]


def test_headline_names_the_period_it_covers():
    """A bare '-59.6%' was quoted as 'over 36 months'. The period must travel with it."""
    result = analyze.analyze_series(series([int(2000 * (0.97 ** i)) for i in range(30)]), flat_baseline(30))
    period = result["trend"]["headline_period"]
    assert period.startswith("year over year (2024-07..2025-06 vs 2023-07..2024-06)")
    assert period in result["trend"]["interpretation"]

    short = analyze.analyze_series(series([int(2000 * (0.97 ** i)) for i in range(12)]), flat_baseline(12))
    assert "no year-over-year" in short["trend"]["headline_period"]


def _reach_vs_momentum_pair():
    big_falling = analyze.analyze_series(
        series([int(9000 * (0.97 ** i)) for i in range(30)]), flat_baseline(30), label="de")
    small_growing = analyze.analyze_series(
        series([int(900 * (1.03 ** i)) for i in range(30)]), flat_baseline(30), label="pl")
    return big_falling, small_growing


def test_priority_weights_change_the_ranking():
    """'Growth matters twice as much' must be computed, not improvised by the model."""
    big_falling, small_growing = _reach_vs_momentum_pair()

    equal = analyze.compare([big_falling, small_growing])
    assert [r["label"] for r in equal["priority"]] == ["de", "pl"]   # reach + intensity win 2:1
    assert equal["weights"] == {"reach": 1.0, "intensity": 1.0, "momentum": 1.0}

    growth_heavy = analyze.compare([big_falling, small_growing], {"momentum": 5})
    assert [r["label"] for r in growth_heavy["priority"]] == ["pl", "de"]
    assert growth_heavy["priority"][0]["priority_score"] == 71     # 5 / 7 of the weight
    assert growth_heavy["weights"]["momentum"] == 5


def test_priority_drops_an_axis_that_has_no_data():
    """Without an edition baseline there is no intensity; weights renormalise over the rest."""
    no_base_big = analyze.analyze_series(series([5000] * 30), {}, label="a")
    no_base_small = analyze.analyze_series(series([500] * 30), {}, label="b")
    result = analyze.compare([no_base_big, no_base_small])
    scores = {r["label"]: r["priority_score"] for r in result["priority"]}
    assert scores["a"] > scores["b"]
    assert all(0 <= s <= 100 for s in scores.values())


def test_percentile_ranks_share_ties():
    ranks = analyze._percentile_ranks({"a": 1, "b": 1, "c": 3, "d": None})
    assert ranks == {"a": 0.25, "b": 0.25, "c": 1.0, "d": None}


# ---------------------------------------------------------------------------
# evaluating results: intervals and whether a lead is real
# ---------------------------------------------------------------------------

def noisy(start, growth, noise, count=30, seed=1):
    """Monthly views with seeded random noise: realistic enough for intervals to mean something.
    (A perfectly smooth series gives every month the same year-over-year ratio, so any
    interval over it correctly collapses to a point.)"""
    import random
    rng = random.Random(seed)
    return [max(1, int(start * (growth ** i) * (1 + rng.uniform(-noise, noise)))) for i in range(count)]


def test_yoy_interval_contains_the_estimate_and_is_reproducible():
    values = noisy(1000, 1.02, 0.25)
    first = analyze.analyze_series(series(values), flat_baseline(30))
    second = analyze.analyze_series(series(values), flat_baseline(30))
    low, high = first["trend"]["ci90_pct"]
    assert low < first["trend"]["headline_change_pct"] < high
    assert first["trend"]["ci90_pct"] == second["trend"]["ci90_pct"]      # fixed seed
    assert first["trend"]["relative"]["share_ci90_pct"] is not None


def test_noisy_series_gets_a_wider_interval_than_a_smooth_one():
    calm = analyze.analyze_series(series(noisy(1000, 1.02, 0.05)), flat_baseline(30))
    wild = analyze.analyze_series(series(noisy(1000, 1.02, 0.60)), flat_baseline(30))
    width = lambda r: r["trend"]["ci90_pct"][1] - r["trend"]["ci90_pct"][0]
    assert width(wild) > 3 * width(calm)


def test_no_interval_without_two_full_years():
    result = analyze.analyze_series(series([1000 + i for i in range(18)]), flat_baseline(18))
    assert result["trend"]["ci90_pct"] is None


def test_separation_says_reliable_only_when_intervals_do_not_overlap():
    fast = analyze.analyze_series(series(noisy(1000, 1.05, 0.15, seed=1)), flat_baseline(30), label="a")
    slow = analyze.analyze_series(series(noisy(1000, 0.97, 0.15, seed=2)), flat_baseline(30), label="b")
    close = analyze.analyze_series(series(noisy(1000, 1.045, 0.15, seed=3)), flat_baseline(30), label="c")

    clear = analyze.compare([fast, slow])["separation"]
    assert clear["leader"] == "a" and clear["reliable"] is True and "reliable" in clear["statement"]

    tied = analyze.compare([fast, close])["separation"]
    assert tied["reliable"] is False and "not clearly different" in tied["statement"]
