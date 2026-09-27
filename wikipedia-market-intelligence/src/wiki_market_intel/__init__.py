"""Wikipedia market-intelligence engine.

    from wiki_market_intel import analyze
    result = analyze(topic="meditation", language="de", period="3y")
    result.summary, result.demand, result.growth, result.seasonality, result.quality

    from wiki_market_intel import compare_languages
    comparison = compare_languages(topic="meditation", languages=["en", "de", "fr", "es"])
    comparison.rows        # one LanguageOpportunityMetrics per edition

Pageviews measure attention, not revenue, market size or willingness to pay.
"""

from wiki_market_intel.config import VERSION as __version__
from wiki_market_intel.models.analysis import AnalysisResult, ComparisonResult
from wiki_market_intel.service import analyze, analyze_cluster, build_services, compare_languages, resolve_topic

__all__ = ["AnalysisResult", "ComparisonResult", "analyze", "analyze_cluster", "build_services", "compare_languages",
           "resolve_topic", "__version__"]
