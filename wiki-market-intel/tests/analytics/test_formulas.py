"""Every formula in the registry: the definition, and the edge cases that must give None."""

import math

import pytest

from wiki_market_intel.analytics import formulas as f


def test_total_and_average():
    assert f.total([1, 2, 3]) == 6
    assert f.average([2, 4]) == 3
    assert f.total([]) is None
    assert f.total([1, None, 3]) is None          # missing is never treated as zero
    assert f.average([1, None]) is None


def test_daily_average():
    assert f.daily_average(365, 365) == 1
    assert f.daily_average(None, 30) is None
    assert f.daily_average(10, 0) is None


@pytest.mark.parametrize("current, previous, expected", [
    (118, 100, 0.18), (82, 100, -0.18), (100, 100, 0.0),
    (100, 0, None), (None, 100, None), (100, None, None),
])
def test_growth_rate_and_yoy(current, previous, expected):
    for fn in (f.growth_rate, f.yoy_growth):
        result = fn(current, previous)
        assert (result is None and expected is None) or math.isclose(result, expected)


def test_cagr():
    assert math.isclose(f.cagr(100, 133.1, 3), 0.10)
    assert math.isclose(f.cagr(100, 100, 3), 0.0)
    assert f.cagr(0, 100, 3) is None
    assert f.cagr(100, -1, 3) is None
    assert f.cagr(100, 120, 0) is None
    assert f.cagr(None, 120, 3) is None


def test_acceleration_and_momentum_labels():
    assert math.isclose(f.acceleration(0.10, -0.05), 0.15)
    assert f.acceleration(None, 0.1) is None
    assert f.momentum_label(0.051) == "accelerating"
    assert f.momentum_label(-0.051) == "decelerating"
    assert f.momentum_label(0.05) == "stable"
    assert f.momentum_label(None) is None


def test_seasonality_ratios_and_volatility():
    values = [50, 100, 150]
    assert math.isclose(f.peak_to_average(values), 1.5)
    assert math.isclose(f.trough_to_average(values), 0.5)
    assert math.isclose(f.volatility([10, 10, 10]), 0.0)
    # pstdev([50, 100, 150]) = sqrt(5000/3) = 40.8248; mean = 100
    assert math.isclose(f.volatility(values), 0.408248290463863, rel_tol=1e-12)
    assert f.volatility([1, 2]) is None           # too short
    assert f.peak_to_average([]) is None
    assert f.peak_to_average([0, 0]) is None


def test_ratio_formulas():
    assert f.views_per_unique_device(300, 100) == 3
    assert f.views_per_unique_device(300, None) is None
    assert f.topic_share(25, 100) == 0.25
    assert f.topic_penetration(5, 1_000_000) == 5e-06
    assert f.topic_share(1, 0) is None


def test_registry_documents_every_reported_kpi():
    names = " ".join(entry.name for entry in f.REGISTRY)
    for kpi in ("annual_views", "monthly_average", "daily_average", "yoy", "three_year_cagr",
                "last_three_month_growth", "acceleration", "peak_to_average", "volatility", "coverage"):
        assert kpi in names
