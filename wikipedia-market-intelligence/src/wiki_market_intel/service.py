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
from wiki_market_intel.analytics import anomalies as anomaly_kpis
from wiki_market_intel.analytics import localization as localization_kpis
from wiki_market_intel.analytics import signals as signal_kpis
from wiki_market_intel.analytics import seasonality as seasonality_kpis
from wiki_market_intel.analytics.periods import build_periods, fetch_window, parse_period
from wiki_market_intel.analytics.summary import comparison_observations, observations
from wiki_market_intel.clients.http import HttpClient
from wiki_market_intel.clients.wikidata import WikidataClient, WikipediaClient
from wiki_market_intel.clients.wikimedia import AGGREGATE, PER_ARTICLE, WikimediaClient, last_complete_month
from wiki_market_intel.config import VERSION, Settings
from wiki_market_intel.data.cache import JsonFileCache, NullCache
from wiki_market_intel.data.normalizer import edition_totals, monthly_series, normalize
from wiki_market_intel.data.raw_store import RawStore
from wiki_market_intel.errors import AmbiguousTopicError, ArticleMissingError, TopicNotFoundError
from wiki_market_intel.i18n import Translator, resolve_report_language
from wiki_market_intel.models.analysis import (
    AnalysisResult, ComparisonMetadata, ComparisonResult, Metadata, SourceRecord, TopicSection,
)
from wiki_market_intel.models.metrics import LanguageOpportunityMetrics, Localization
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


def _window(period: str, start: date | str | None, end: date | str | None, today: date) -> tuple[date, int]:
    """(end month, number of months). The end is capped at the last complete month."""
    last = last_complete_month(today)
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
    return end_month, months


def _analyze_article(services: Services, topic: str, language: str, resolution: TopicResolution,
                     end_month: date, months: int, question: str | None, report_language: str) -> AnalysisResult:
    """Everything after resolution for one (topic, language): fetch, normalize, KPIs, quality."""
    settings = services.settings
    article = resolution.articles[language]
    project = f"{language}.wikipedia"
    periods = build_periods(end_month, months)
    window_start, window_end = fetch_window(periods)

    fetch = services.wikimedia.per_article(project, article.title, window_start, window_end)
    series = monthly_series(normalize(fetch.items, article), window_start, window_end)
    edition_fetch = services.wikimedia.aggregate(project, window_start, window_end)
    edition = edition_totals(edition_fetch.items, window_start, window_end)

    demand, gaps_d = demand_kpis.compute(series, periods)
    growth, gaps_g = growth_kpis.compute(series, periods)
    seasonality, gaps_s = seasonality_kpis.compute(series, periods["requested"])
    pen, gaps_p = localization_kpis.penetration(series, edition, periods["last_12m"], edition_fetch.status == "ok")
    found, anomaly_info = anomaly_kpis.detect(series, periods["requested"])
    anomaly_info.yoy_excluding_anomalies = anomaly_kpis.yoy_excluding(series, found, periods["last_12m"],
                                                                      periods["previous_12m"])
    api_errors = [] if fetch.status == "ok" else [f"{PER_ARTICLE}: HTTP 404, no pageviews stored for this article"]
    if edition_fetch.status != "ok":
        api_errors.append(f"{AGGREGATE}: HTTP 404, no edition totals for {project}")
    quality = quality_kpis.assess(series, periods["requested"], resolution, gaps_d + gaps_g + gaps_s + gaps_p,
                                  api_errors, denominator_available=edition_fetch.status == "ok",
                                  anomaly_count=len(found))

    signals, gaps_sig = signal_kpis.compute(demand.annual_views, growth, seasonality, [a.date for a in found],
                                            anomaly_info.months_checked)
    quality.missing_metrics += gaps_sig

    requested = periods["requested"]
    result = AnalysisResult(
        metadata=Metadata(
            topic=topic, language=language, project=project,
            period_start=f"{requested.start:%Y-%m}", period_end=f"{requested.end:%Y-%m}",
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            data_retrieved_at=fetch.fetched.retrieved_at, api=f"{settings.pageviews_base}/per-article",
            access=settings.access, agent=settings.agent, software_version=VERSION,
            question=question, report_language=resolve_report_language(question, report_language)[1]),
        topic=TopicSection(canonical_name=resolution.canonical_topic, wikidata_id=resolution.wikidata_id,
                           article_title=article.title,
                           article_id=str(article.page_id) if article.page_id is not None else None,
                           resolution_confidence=resolution.confidence, resolution=resolution),
        periods=[p.ref(series) for p in periods.values()],
        demand=demand, growth=growth, seasonality=seasonality, quality=quality,
        localization=Localization(topic_penetration=pen),
        anomalies=found, anomaly_analysis=anomaly_info,
        observations=observations(demand, growth, seasonality, periods, anomalies=found,
                                  anomaly_info=anomaly_info),
        monthly=series, edition_monthly=edition, formulas=formulas.REGISTRY,
        sources=[SourceRecord(endpoint=f.fetched.endpoint, url=f.fetched.url, retrieved_at=f.fetched.retrieved_at,
                              raw_path=f.fetched.raw_path) for f in (fetch, edition_fetch)],
        signals=signals,
    )
    result.signals.evidence = signal_kpis.explain(result, Translator("en"))
    return result


def _resolve_or_raise(services: Services, topic: str, languages: list[str]) -> TopicResolution:
    resolution = services.resolver.resolve(topic, languages)
    if resolution.status == "needs_review":
        raise AmbiguousTopicError(resolution)
    if resolution.status == "not_found":
        raise TopicNotFoundError(resolution)
    return resolution


def analyze(topic: str, language: str, period: str = "3y", *, start: date | str | None = None,
            end: date | str | None = None, question: str | None = None, report_language: str = "auto",
            services: Services | None = None) -> AnalysisResult:
    """Analyze one topic in one language edition.

    `period` ("3y", "18m") counts back from the last complete month. Alternatively pass
    `start`/`end`: a full date `end` is exclusive when it falls on the 1st (2026-01-01
    means "up to December 2025"), a "YYYY-MM" `end` is inclusive.
    `question` is the user's own request; the report is written in its language
    (English and Ukrainian are supported; others fall back to English). `report_language`
    ("auto", "en", "uk") overrides the detection. `language` is the Wikipedia edition analysed.
    Raises AmbiguousTopicError / TopicNotFoundError / ArticleMissingError / ApiError.
    """
    services = services or build_services()
    end_month, months = _window(period, start, end, services.today)
    resolution = _resolve_or_raise(services, topic, [language])
    if language not in resolution.articles:
        raise ArticleMissingError(resolution, language)
    return _analyze_article(services, topic, language, resolution, end_month, months, question, report_language)


def compare_languages(topic: str, languages: list[str], period: str = "3y", *, start: date | str | None = None,
                      end: date | str | None = None, question: str | None = None, report_language: str = "auto",
                      services: Services | None = None) -> ComparisonResult:
    """The same Wikidata concept across language editions (spec §14).

    The topic is resolved once, so every edition is measured on the same concept. An edition
    without an article becomes a row with status "no_article" - never a row of zeros.
    Raises AmbiguousTopicError / TopicNotFoundError / ApiError.
    """
    services = services or build_services()
    languages = list(dict.fromkeys(l.strip() for l in languages if l.strip()))
    if len(languages) < 2:
        raise ValueError("compare needs at least two languages")
    end_month, months = _window(period, start, end, services.today)
    resolution = _resolve_or_raise(services, topic, languages)
    report_lang = resolve_report_language(question, report_language)[1]

    analyses: dict[str, AnalysisResult] = {}
    rows: list[LanguageOpportunityMetrics] = []
    edition_annual: dict[str, float | None] = {}
    for language in languages:
        project = f"{language}.wikipedia"
        if language not in resolution.articles:
            rows.append(LanguageOpportunityMetrics(language=language, project=project, status="no_article"))
            continue
        result = _analyze_article(services, topic, language, resolution, end_month, months, question, report_lang)
        analyses[language] = result
        last_12m = build_periods(end_month, months)["last_12m"]
        edition_annual[language] = localization_kpis.edition_annual(result.edition_monthly, last_12m)
        has_data = any(p.views is not None for p in result.monthly)
        rows.append(LanguageOpportunityMetrics(
            language=language, project=project, article_title=result.topic.article_title,
            status="ok" if has_data else "no_data",
            annual_views=result.demand.annual_views, monthly_average=result.demand.monthly_average,
            yoy_growth=result.growth.yoy, three_year_cagr=result.growth.three_year_cagr,
            three_month_growth=result.growth.last_three_month_growth, momentum=result.growth.momentum,
            peak_month=result.seasonality.peak_month, topic_penetration=result.localization.topic_penetration,
            quality_level=result.quality.quality_level, anomaly_count=len(result.anomalies)))

    threshold, notes = localization_kpis.compare(rows, edition_annual)
    for result in analyses.values():   # each per-language result now knows its share and affinity
        row = next(r for r in rows if r.language == result.metadata.language)
        result.localization.topic_share = row.topic_share
        result.localization.topic_affinity = row.topic_affinity
        computed = {m for m, v in (("localization.topic_share", row.topic_share),
                                   ("localization.topic_affinity", row.topic_affinity)) if v is not None}
        result.signals.localization = signal_kpis.localization(row.topic_affinity)
        if result.signals.localization:
            computed.add("signals.localization")
        result.signals.evidence = signal_kpis.explain(result, Translator("en"))
        result.quality.missing_metrics = [m for m in result.quality.missing_metrics if m.metric not in computed]
    if resolution.missing_languages:
        notes.insert(0, f"No article about this concept in: {', '.join(resolution.missing_languages)} "
                        f"(Wikidata {resolution.wikidata_id} has no sitelink there).")

    periods = build_periods(end_month, months)
    retrieved = sorted(r.metadata.data_retrieved_at for r in analyses.values() if r.metadata.data_retrieved_at)
    return ComparisonResult(
        metadata=ComparisonMetadata(
            topic=topic, languages=languages, period_start=f"{periods['requested'].start:%Y-%m}",
            period_end=f"{periods['requested'].end:%Y-%m}",
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            data_retrieved_at=retrieved[0] if retrieved else None, software_version=VERSION,
            question=question, report_language=report_lang),
        resolution=resolution, rows=rows, analyses=analyses, demand_threshold=threshold,
        observations=comparison_observations(rows), notes=notes, formulas=formulas.REGISTRY)


# ---------------------------------------------------------------------------
# topic ecosystem (spec §19-§20)
# ---------------------------------------------------------------------------

# (relationship, how it is found, Wikidata property or None, reverse lookup?, per-kind cap)
RELATION_SOURCES = [
    ("broader", "wikidata:P279 subclass of", "P279", False, 10),
    ("facet_of", "wikidata:P1269 facet of", "P1269", False, 10),
    ("narrower", "wikidata:P279 subclass of (reverse)", "P279", True, 15),
    ("has_facet", "wikidata:P1269 facet of (reverse)", "P1269", True, 10),
    ("similar_content", "search:morelike (text similarity)", None, False, 10),
]
MAX_RELATED = 20


def analyze_cluster(topic: str, language: str, period: str = "3y", *, start: date | str | None = None,
                    end: date | str | None = None, question: str | None = None, report_language: str = "auto",
                    max_related: int = MAX_RELATED, services: Services | None = None) -> AnalysisResult:
    """`analyze` plus the topic ecosystem: related concepts with their KPIs and signals.

    Related concepts come from typed Wikidata relations (broader / narrower / facets) and,
    labelled separately, from text similarity. Each is an adjacent *interest* signal only.
    """
    from concurrent.futures import ThreadPoolExecutor

    from wiki_market_intel.analytics import ecosystem as eco
    from wiki_market_intel.clients import wikidata as wd
    from wiki_market_intel.models.analysis import Ecosystem
    from wiki_market_intel.models.metrics import RelatedTopic

    services = services or build_services()
    result = analyze(topic, language, period, start=start, end=end, question=question,
                     report_language=report_language, services=services)
    wikipedia, wikidata = services.resolver.wikipedia, services.resolver.wikidata
    qid, focal_title = result.topic.wikidata_id, result.topic.article_title

    found: list[tuple[str, str, str | None, str]] = []   # (relationship, source, qid, title)
    notes: list[str] = []
    skipped: dict[str, int] = {}
    capped_from = None
    considered = 0
    for relationship, source, prop, is_reverse, cap in RELATION_SOURCES:
        if prop is None:
            candidates = wd.morelike(wikipedia, language, focal_title, cap)
            considered += len(candidates)
            found += [(relationship, source, c.wikidata_id, c.title) for c in candidates]
            continue
        if not qid:
            continue
        qids = (wd.reverse(wikidata, prop, qid, cap) if is_reverse
                else wd.claims(wikidata, qid, (prop,)).get(prop, [])[:cap])
        considered += len(qids)
        titles = wd.sitelinks(wikidata, qids, language) if qids else {}
        missing = [q for q in qids if q not in titles]
        if missing:
            skipped[relationship] = len(missing)
            notes.append(f"{len(missing)} {relationship} concept(s) have no {language}.wikipedia article "
                         f"and were skipped.")
        found += [(relationship, source, q, titles[q]) for q in qids if q in titles]
    if not qid:
        notes.append("The topic has no Wikidata entity, so only text-similar articles were considered.")

    seen: set[str] = {focal_title.casefold()} | ({qid} if qid else set())
    picked = []
    for relationship, source, rqid, title in found:            # typed relations come first and win
        keys = {title.casefold()} | ({rqid} if rqid else set())
        if keys & seen:
            continue
        seen |= keys
        picked.append((relationship, source, rqid, title))
    if len(picked) > max_related:
        capped_from = len(picked)
        notes.append(f"{len(picked)} related concepts found; the first {max_related} were measured "
                     f"(typed Wikidata relations before text similarity).")
        picked = picked[:max_related]

    end_month = date.fromisoformat(result.metadata.period_end + "-01")
    start_month = date.fromisoformat(result.metadata.period_start + "-01")
    months = (end_month.year - start_month.year) * 12 + end_month.month - start_month.month + 1
    periods = build_periods(end_month, months)
    window_start, window_end = fetch_window(periods)
    project = f"{language}.wikipedia"

    def fetch(item):
        relationship, source, rqid, title = item
        pv = services.wikimedia.per_article(project, title, window_start, window_end)
        article = result.topic.resolution.articles[language].model_copy(update={"title": title, "page_id": None})
        return RelatedTopic(title=title, wikidata_id=rqid, relationship=relationship, source=source,
                            monthly=monthly_series(normalize(pv.items, article), window_start, window_end))

    with ThreadPoolExecutor(max_workers=4) as pool:
        related = list(pool.map(fetch, picked))

    edition = eco.edition_yoy(result.edition_monthly, periods)
    focal_annual = result.demand.annual_views
    related = [eco.measure(r, periods, focal_annual, edition) for r in related]
    related.sort(key=lambda r: -(r.annual_views or -1))
    if any(r.relationship == "similar_content" for r in related):
        notes.append("'similar_content' comes from text similarity, not a stated relationship: it can include "
                     "unrelated articles that share vocabulary.")
    result.ecosystem = Ecosystem(computed=True, related_topics=related, edition_yoy=edition,
                                 concentration=eco.concentration(focal_annual, related, focal_title),
                                 candidates_considered=considered, skipped_without_article=skipped,
                                 capped_from=capped_from, has_wikidata=bool(qid), notes=notes)
    result.quality.missing_metrics = [m for m in result.quality.missing_metrics
                                      if m.metric != "ecosystem.related_topics"]
    return result
