"""Penetration, share, affinity and quadrants (spec §14-§18, §23)."""

import math

import pytest

from wiki_market_intel.analytics import formulas as f
from wiki_market_intel.analytics import localization
from wiki_market_intel.analytics.periods import build_periods
from wiki_market_intel.models.metrics import LanguageOpportunityMetrics, MonthlyPoint
from datetime import date


def test_affinity_is_a_location_quotient_relative_to_the_compared_set():
    # Topic takes 10 per million in L, 5 per million across the set: twice the average.
    assert math.isclose(f.topic_affinity(10, 1_000_000, 50, 10_000_000), 2.0)
    assert math.isclose(f.topic_affinity(5, 1_000_000, 50, 10_000_000), 1.0)
    assert f.topic_affinity(10, 0, 50, 10_000_000) is None
    assert f.topic_affinity(None, 1, 1, 1) is None


@pytest.mark.parametrize("growth, demand, label", [
    (0.1, 200, "investigate"), (0.1, 50, "explore"), (-0.1, 200, "established"), (-0.1, 50, "watch"),
    (0.0, 200, "established"),          # 0% is not growth
    (0.1, 100, "investigate"),          # at the median counts as high demand
])
def test_quadrants(growth, demand, label):
    assert f.quadrant(growth, demand, 100) == label


def test_quadrant_needs_all_inputs():
    assert f.quadrant(None, 100, 100) is None and f.quadrant(0.1, 100, None) is None


def _row(lang, views, yoy, status="ok"):
    return LanguageOpportunityMetrics(language=lang, project=f"{lang}.wikipedia", status=status,
                                      annual_views=views, yoy_growth=yoy)


def test_compare_fills_share_affinity_and_quadrants():
    rows = [_row("en", 300, -0.2), _row("de", 100, 0.1), _row("fr", 50, 0.3), _row("uk", None, None, "no_article")]
    editions = {"en": 30_000, "de": 5_000, "fr": 5_000}
    threshold, notes = localization.compare(rows, editions)
    en, de, fr, uk = rows
    assert math.isclose(en.topic_share + de.topic_share + fr.topic_share, 1.0)
    assert math.isclose(de.topic_share, 100 / 450)
    # pooled penetration 450 / 40,000; de has 100 / 5,000 -> 1.78x
    assert math.isclose(de.topic_affinity, (100 / 5000) / (450 / 40000))
    assert threshold == 100 and (en.quadrant, de.quadrant, fr.quadrant) == ("established", "investigate", "explore")
    assert uk.topic_share is None and uk.quadrant is None
    assert any("left out" in n and "uk" in n for n in notes)


def test_affinity_is_null_without_a_denominator_and_says_why():
    rows = [_row("en", 300, 0.1), _row("de", 100, 0.1), _row("fr", 50, 0.1)]
    _, notes = localization.compare(rows, {"en": 30_000, "de": None, "fr": 5_000})
    assert rows[1].topic_affinity is None and rows[0].topic_affinity is not None
    assert any("denominator is unavailable" in n for n in notes)


def test_penetration_uses_the_same_twelve_months_for_topic_and_edition():
    end = date(2026, 8, 1)
    months = [f"{y}-{m:02d}" for y in (2025, 2026) for m in range(1, 13)]
    topic = [MonthlyPoint(month=m, views=10) for m in months]
    edition = [MonthlyPoint(month=m, views=1_000_000) for m in months]
    value, gaps = localization.penetration(topic, edition, build_periods(end, 24)["last_12m"], True)
    assert math.isclose(value, 10 / 1_000_000) and not gaps
    none, gaps = localization.penetration(topic, edition, build_periods(end, 24)["last_12m"], False)
    assert none is None and gaps[0].status == "unavailable"
