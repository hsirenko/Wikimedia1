"""Wikipedia market-intelligence engine.

    from wiki_market_intel import analyze
    result = analyze(topic="meditation", language="de", period="3y")
    result.summary, result.demand, result.growth, result.seasonality, result.quality

Pageviews measure attention, not revenue, market size or willingness to pay.
"""

from wiki_market_intel.config import VERSION as __version__
from wiki_market_intel.models.analysis import AnalysisResult
from wiki_market_intel.service import analyze, build_services, resolve_topic

__all__ = ["AnalysisResult", "analyze", "build_services", "resolve_topic", "__version__"]
