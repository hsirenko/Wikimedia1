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
