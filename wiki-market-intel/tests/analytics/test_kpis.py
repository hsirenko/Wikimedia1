"""Periods, demand, growth, seasonality and quality on controlled series."""

from datetime import date

import pytest

from wiki_market_intel.analytics import demand, growth, quality, seasonality
from wiki_market_intel.analytics.periods import DATA_START, build_periods, fetch_window, parse_period
from wiki_market_intel.data.normalizer import month_range
from wiki_market_intel.models.metrics import MonthlyPoint
from wiki_market_intel.models.topic import TopicResolution

END = date(2026, 8, 1)


def series(values_by_offset, months=72, end=END):
    """values_by_offset(i) for i = 0 (oldest) .. months-1 (END). Return None for a missing month."""
    start = date(end.year - (months // 12), end.month, 1)
    points = month_range(start, end)[-months:]
    return [MonthlyPoint(month=f"{m:%Y-%m}", views=values_by_offset(i)) for i, m in enumerate(points)]


PERIODS = build_periods(END, 36)


def test_periods_are_whole_months_ending_at_the_given_month():
    p = PERIODS
    assert (p["last_12m"].start, p["last_12m"].end) == (date(2025, 9, 1), date(2026, 8, 1))
    assert (p["previous_12m"].start, p["previous_12m"].end) == (date(2024, 9, 1), date(2025, 8, 1))
    assert (p["twelve_months_3y_earlier"].start, p["twelve_months_3y_earlier"].end) == (date(2022, 9, 1), date(2023, 8, 1))
    assert (p["last_3m"].start, p["previous_3m"].start, p["preceding_3m"].start) == (
        date(2026, 6, 1), date(2026, 3, 1), date(2025, 12, 1))
    assert p["requested"].months == 36 and p["previous_equivalent"].end == date(2023, 8, 1)
    assert p["last_12m"].days == 365


def test_fetch_window_never_starts_before_the_data_does():
    early = build_periods(date(2017, 1, 1), 36)
    assert fetch_window(early)[0] == DATA_START


@pytest.mark.parametrize("text, months", [("3y", 36), ("18m", 18), ("24", 24), ("1.5y", 18)])
def test_parse_period(text, months):
    assert parse_period(text) == months


def test_parse_period_rejects_nonsense():
    with pytest.raises(ValueError):
        parse_period("0m")


def test_demand_from_a_flat_series():
    d, gaps = demand.compute(series(lambda i: 100), PERIODS)
    assert d.annual_views == 1200 and d.monthly_average == 100
    assert d.daily_average == pytest.approx(1200 / 365)
    assert d.requested_period_views == 3600
    assert d.unique_devices is None and any(g.metric == "demand.unique_devices" and g.status == "unsupported"
                                            for g in gaps)


def test_growth_from_a_series_that_grows_ten_percent_a_year():
    # Constant within each 12-month block, x1.1 per block: YoY 10%, CAGR 10%, flat 3M momentum.
    s = series(lambda i: round(1000 * 1.1 ** (i // 12)))
    g, gaps = growth.compute(s, PERIODS)
    assert g.yoy == pytest.approx(0.1, abs=1e-3)
    assert g.three_year_cagr == pytest.approx(0.1, abs=1e-3)
    assert g.last_three_month_growth == pytest.approx(0.0)
    assert g.momentum == "stable"
    assert not [x for x in gaps if x.metric.startswith("growth.")]


def test_acceleration_and_momentum():
    # Last 3 months jump 50% after a flat stretch: accelerating.
    s = series(lambda i: 150 if i >= 69 else 100)
    g, _ = growth.compute(s, PERIODS)
    assert g.last_three_month_growth == pytest.approx(0.5)
    assert g.previous_three_month_growth == pytest.approx(0.0)
    assert g.acceleration == pytest.approx(0.5) and g.momentum == "accelerating"


def test_missing_month_makes_growth_null_with_a_reason_not_zero():
    s = series(lambda i: None if i == 50 else 100)      # a gap inside the previous 12 months
    g, gaps = growth.compute(s, PERIODS)
    assert g.yoy is None
    reason = next(x for x in gaps if x.metric == "growth.yoy")
    assert reason.status == "insufficient_data" and "previous 12 months" in reason.reason


def test_cagr_needs_the_year_three_years_back():
    s = series(lambda i: None if i < 30 else 100)       # history starts 42 months ago
    g, gaps = growth.compute(s, PERIODS)
    assert g.three_year_cagr is None and g.yoy == 0
    assert any(x.metric == "growth.three_year_cagr" for x in gaps)


def test_seasonality_peak_trough_and_volatility():
    # January is twice the other months every year (chosen by month name, not by offset).
    s = [MonthlyPoint(month=p.month, views=200 if p.month.endswith("-01") else 100) for p in series(lambda i: 0)]
    season, gaps = seasonality.compute(s, PERIODS["requested"])
    assert season.peak_month == "January" and not gaps
    assert season.peak_to_average == pytest.approx(200 / (1300 / 12))
    assert season.volatility > 0


def test_seasonality_needs_every_calendar_month():
    s = series(lambda i: 100, months=8)
    season, gaps = seasonality.compute(s, build_periods(END, 8)["requested"])
    assert season.peak_month is None and gaps[0].status == "insufficient_data"


def _resolution(confidence):
    return TopicResolution(query="x", status="resolved", confidence=confidence, method="exact_title")


def test_quality_levels_follow_the_documented_rules():
    full = series(lambda i: 100)
    assert quality.assess(full, PERIODS["requested"], _resolution(0.98), [], []).quality_level == "HIGH"
    assert quality.assess(full, PERIODS["requested"], _resolution(0.8), [], []).quality_level == "MEDIUM"
    gappy = series(lambda i: None if i % 5 == 0 else 100)
    low = quality.assess(gappy, PERIODS["requested"], _resolution(0.98), [], [])
    assert low.quality_level == "LOW" and low.coverage < 0.9
    assert any("no pageviews returned" in m for m in low.missing_data)
    short = quality.assess(full, build_periods(END, 12)["requested"], _resolution(0.98), [], [])
    assert short.quality_level == "MEDIUM" and any("under 24" in r for r in short.quality_reasons)


def test_quality_states_what_is_unsupported_or_not_built_yet():
    q = quality.assess(series(lambda i: 100), PERIODS["requested"], _resolution(0.98), [], [])
    statuses = {m.metric: m.status for m in q.missing_metrics}
    assert statuses["localization.country_distribution"] == "unsupported"
    assert "signals" not in statuses and "not_implemented" not in statuses.values()   # all built
    assert statuses["ecosystem.related_topics"] == "unavailable"   # computed by `cluster`, not `analyze`
    assert "anomalies" not in statuses          # implemented: reported in the anomalies section
    assert q.country_data_available is False and q.unique_devices_available is False
