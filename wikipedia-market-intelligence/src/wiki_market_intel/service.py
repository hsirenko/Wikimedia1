"""The pipeline: resolve -> collect -> normalize -> KPIs -> quality -> result.

This module wires layers together and holds no business logic of its own; each
step lives in its layer (clients, resolution, data, analytics).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx
from dateutil.relativedelta import relativedelta

from wiki_market_intel.analytics import demand as demand_kpis
from wiki_market_intel.analytics import formulas, growth as growth_kpis, quality as quality_kpis
from wiki_market_intel.analytics import seasonality as seasonality_kpis
from wiki_market_intel.analytics.periods import build_periods, fetch_window, parse_period
from wiki_market_intel.analytics.summary import observations
from wiki_market_intel.clients.http import HttpClient
from wiki_market_intel.clients.wikidata import WikidataClient, WikipediaClient
from wiki_market_intel.clients.wikimedia import PER_ARTICLE, WikimediaClient, last_complete_month
from wiki_market_intel.config import VERSION, Settings
from wiki_market_intel.data.cache import JsonFileCache, NullCache
from wiki_market_intel.data.normalizer import monthly_series, normalize
from wiki_market_intel.data.raw_store import RawStore
from wiki_market_intel.errors import AmbiguousTopicError, ArticleMissingError, TopicNotFoundError
from wiki_market_intel.models.analysis import AnalysisResult, Metadata, SourceRecord, TopicSection
from wiki_market_intel.models.topic import TopicResolution
from wiki_market_intel.resolution.topic_resolver import TopicResolver


@dataclass
class Services:
    settings: Settings
    http: HttpClient
    wikimedia: WikimediaClient
    resolver: TopicResolver
    today: date


def build_services(settings: Settings | None = None, *, transport: httpx.BaseTransport | None = None,
                   today: date | None = None, use_cache: bool = True, backoff: float = 0.5) -> Services:
    settings = settings or Settings()
    cache = JsonFileCache(settings.cache_dir) if use_cache else NullCache()
    http = HttpClient(settings, RawStore(settings.raw_dir), cache, transport=transport, backoff=backoff)
    today = today or date.today()
    resolver = TopicResolver(WikipediaClient(http, settings), WikidataClient(http, settings), settings.pivot_language)
    return Services(settings=settings, http=http, wikimedia=WikimediaClient(http, settings, today),
                    resolver=resolver, today=today)


def resolve_topic(topic: str, languages: list[str], services: Services | None = None) -> TopicResolution:
    services = services or build_services()
    return services.resolver.resolve(topic, languages)


def _month(value: date | str) -> date:
    if isinstance(value, str):
        value = date.fromisoformat(value if len(value) > 7 else f"{value}-01")
    return date(value.year, value.month, 1)


def analyze(topic: str, language: str, period: str = "3y", *, start: date | str | None = None,
            end: date | str | None = None, services: Services | None = None) -> AnalysisResult:
    """Analyze one topic in one language edition.

    `period` ("3y", "18m") counts back from the last complete month. Alternatively pass
    `start`/`end`: a full date `end` is exclusive when it falls on the 1st (2026-01-01
    means "up to December 2025"), a "YYYY-MM" `end` is inclusive.
    Raises AmbiguousTopicError / TopicNotFoundError / ArticleMissingError / ApiError.
    """
    services = services or build_services()
    settings = services.settings
    last = last_complete_month(services.today)

    if end is None:
        end_month = last
    elif isinstance(end, str) and len(end) == 7:
        end_month = _month(end)
    else:
        end_date = end if isinstance(end, date) else date.fromisoformat(end)
        end_month = _month(end_date - relativedelta(days=1)) if end_date.day == 1 else _month(end_date)
    end_month = min(end_month, last)   # never include an incomplete month
    months = (parse_period(period) if start is None else
              (end_month.year - _month(start).year) * 12 + end_month.month - _month(start).month + 1)

    resolution = services.resolver.resolve(topic, [language])
    if resolution.status == "needs_review":
        raise AmbiguousTopicError(resolution)
    if resolution.status == "not_found":
        raise TopicNotFoundError(resolution)
    if language not in resolution.articles:
        raise ArticleMissingError(resolution, language)
    article = resolution.articles[language]
    project = f"{language}.wikipedia"

    periods = build_periods(end_month, months)
    window_start, window_end = fetch_window(periods)
    fetch = services.wikimedia.per_article(project, article.title, window_start, window_end)
    records = normalize(fetch.items, article)
    series = monthly_series(records, window_start, window_end)

    demand, gaps_d = demand_kpis.compute(series, periods)
    growth, gaps_g = growth_kpis.compute(series, periods)
    seasonality, gaps_s = seasonality_kpis.compute(series, periods["requested"])
    api_errors = [] if fetch.status == "ok" else [f"{PER_ARTICLE}: HTTP 404, no pageviews stored for this article"]
    quality = quality_kpis.assess(series, periods["requested"], resolution, gaps_d + gaps_g + gaps_s, api_errors)

    requested = periods["requested"]
    return AnalysisResult(
        metadata=Metadata(
            topic=topic, language=language, project=project,
            period_start=f"{requested.start:%Y-%m}", period_end=f"{requested.end:%Y-%m}",
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            data_retrieved_at=fetch.fetched.retrieved_at, api=f"{settings.pageviews_base}/per-article",
            access=settings.access, agent=settings.agent, software_version=VERSION),
        topic=TopicSection(canonical_name=resolution.canonical_topic, wikidata_id=resolution.wikidata_id,
                           article_title=article.title,
                           article_id=str(article.page_id) if article.page_id is not None else None,
                           resolution_confidence=resolution.confidence, resolution=resolution),
        periods=[p.ref(series) for p in periods.values()],
        demand=demand, growth=growth, seasonality=seasonality, quality=quality,
        observations=observations(demand, growth, seasonality, periods),
        monthly=series, formulas=formulas.REGISTRY,
        sources=[SourceRecord(endpoint=fetch.fetched.endpoint, url=fetch.fetched.url,
                              retrieved_at=fetch.fetched.retrieved_at, raw_path=fetch.fetched.raw_path)],
    )
