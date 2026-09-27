"""Live Wikimedia API checks. Skipped by default; run with:  pytest -m integration"""

import pytest

from wiki_market_intel import analyze
from wiki_market_intel.config import Settings
from wiki_market_intel.service import build_services

pytestmark = pytest.mark.integration


@pytest.fixture
def live(tmp_path):
    services = build_services(Settings(data_dir=tmp_path / "data", reports_dir=tmp_path / "reports"))
    yield services
    services.http.close()


def test_live_resolution_of_meditation(live):
    r = live.resolver.resolve("meditation", ["de", "fr"])
    assert r.status == "resolved" and r.wikidata_id == "Q108458"
    assert r.articles["de"].title == "Meditation"


def test_live_analysis_end_to_end(live):
    result = analyze("meditation", "de", "3y", services=live)
    assert result.demand.annual_views and result.demand.annual_views > 0
    assert result.growth.yoy is not None
    assert result.quality.coverage and result.quality.coverage > 0.9


def test_live_language_comparison(live):
    from wiki_market_intel import compare_languages
    result = compare_languages("meditation", ["en", "de", "fr"], "3y", services=live)
    ok = [r for r in result.rows if r.status == "ok"]
    assert len(ok) == 3 and abs(sum(r.topic_share for r in ok) - 1) < 1e-9
    assert all(r.topic_penetration and r.topic_affinity for r in ok)


def test_live_topic_ecosystem(live):
    from wiki_market_intel import analyze_cluster
    result = analyze_cluster("meditation", "de", "3y", max_related=8, services=live)
    eco = result.ecosystem
    assert eco.computed and 0 < len(eco.related_topics) <= 8
    assert any(t.relationship in ("broader", "narrower", "facet_of") for t in eco.related_topics)
    assert eco.concentration.top_1 is not None
