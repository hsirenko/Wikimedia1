"""Anomaly detection (spec §13, §31): spikes flagged, seasonality and level shifts not, causes never."""

import random
from datetime import date

import pytest

from wiki_market_intel.analytics import anomalies
from wiki_market_intel.analytics.periods import build_periods
from wiki_market_intel.models.metrics import MonthlyPoint
from wiki_market_intel.data.normalizer import month_range
from tests.conftest import load

END = date(2026, 8, 1)
PERIODS = build_periods(END, 36)


def series(fn, months=60, noise=0.05, seed=3):
    """fn(month 'YYYY-MM', index) -> base views; multiplicative noise added."""
    rng = random.Random(seed)
    points = month_range(date(END.year - months // 12, END.month, 1), END)[-months:]
    return [MonthlyPoint(month=f"{m:%Y-%m}", views=None if fn(f"{m:%Y-%m}", i) is None
                         else int(fn(f"{m:%Y-%m}", i) * (1 + rng.uniform(-noise, noise))))
            for i, m in enumerate(points)]


def detect(s, period=PERIODS["requested"]):
    return anomalies.detect(s, period)


def test_normal_data_has_no_anomalies():
    found, info = detect(series(lambda m, i: 1000))
    assert found == [] and info.months_checked == 36


def test_a_spike_is_flagged_with_its_baseline_and_no_cause():
    found, _ = detect(series(lambda m, i: 3000 if m == "2025-03" else 1000))
    assert [a.date for a in found] == ["2025-03"]
    spike = found[0]
    assert spike.direction == "spike" and spike.severity == "high" and spike.cause == "unknown"
    assert spike.expected == pytest.approx(1000, rel=0.08)
    assert spike.change_vs_baseline == pytest.approx(spike.actual / spike.expected - 1, abs=1e-4)
    assert not spike.provisional


def test_a_drop_is_flagged():
    found, _ = detect(series(lambda m, i: 400 if m == "2024-11" else 1000))
    assert [(a.date, a.direction) for a in found] == [("2024-11", "drop")]


def test_recurring_seasonal_peaks_are_not_anomalies():
    found, info = detect(series(lambda m, i: 1800 if m.endswith("-01") else 1000))
    assert found == [] and info.seasonal_adjustment is True


def test_a_spike_on_top_of_a_seasonal_peak_is_still_flagged():
    base = lambda m, i: (4000 if m == "2025-01" else 1800) if m.endswith("-01") else 1000
    found, _ = detect(series(base))
    assert [a.date for a in found] == ["2025-01"]
    assert found[0].expected == pytest.approx(1800, rel=0.12)       # baseline includes the usual January lift


def test_a_permanent_level_shift_is_not_reported_as_a_run_of_anomalies():
    found, _ = detect(series(lambda m, i: 1000 if m < "2024-12" else 500))
    assert len(found) <= 1


def test_small_wobbles_on_a_smooth_series_are_not_flagged():
    # MAD is tiny on a near-noiseless series; the 25% effect-size gate stops a +10% month.
    found, _ = detect(series(lambda m, i: 1100 if m == "2025-05" else 1000, noise=0.001))
    assert found == []


def test_missing_months_are_skipped_and_only_the_requested_period_is_reported():
    s = series(lambda m, i: None if m == "2025-02" else (5000 if m == "2022-06" else 1000))
    found, _ = detect(s)
    assert all(PERIODS["requested"].start.strftime("%Y-%m") <= a.date for a in found)
    assert "2025-02" not in {a.date for a in found}


def test_recent_flags_are_provisional():
    found, _ = detect(series(lambda m, i: 3000 if m == "2026-07" else 1000))
    assert found and found[0].date == "2026-07" and found[0].provisional


def test_without_two_other_years_there_is_no_seasonal_adjustment():
    short = series(lambda m, i: 1000, months=18)
    _, info = anomalies.detect(short, build_periods(END, 12)["requested"])
    assert info.seasonal_adjustment is False


def test_yoy_excluding_anomalies_removes_the_spike():
    s = series(lambda m, i: 6000 if m == "2026-02" else 1000, noise=0.0)
    found, _ = detect(s)
    assert [a.date for a in found] == ["2026-02"]
    excluded = anomalies.yoy_excluding(s, found, PERIODS["last_12m"], PERIODS["previous_12m"])
    assert excluded == pytest.approx(0.0, abs=0.01)                  # flat once the spike is replaced
    assert anomalies.yoy_excluding(s, [], PERIODS["last_12m"], PERIODS["previous_12m"]) is None


def test_real_german_meditation_series():
    s = [MonthlyPoint(month=f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}", views=i["views"])
         for i in load("pageviews_meditation_de_2020-09_2026-08.json")["items"]]
    found, info = detect(s)
    dates = {a.date for a in found}
    assert info.seasonal_adjustment and not any(d.endswith("-01") for d in dates)   # January peaks recur
    assert "2025-11" in dates                                        # the visible November 2025 bump
