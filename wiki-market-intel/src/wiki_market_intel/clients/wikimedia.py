"""Wikimedia Analytics (AQS) pageviews client.

Endpoints and schemas follow the official specification at
https://wikimedia.org/api/rest_v1/metrics/pageviews/api-spec.json
(documented at https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, NonNegativeInt, ValidationError

from wiki_market_intel.clients.http import Fetched, HttpClient
from wiki_market_intel.config import Settings
from wiki_market_intel.data.cache import CacheKey
from wiki_market_intel.errors import ApiError

PER_ARTICLE = "pageviews/per-article"
AGGREGATE = "pageviews/aggregate"
ACCESS = ("all-access", "desktop", "mobile-app", "mobile-web")
AGENTS = ("all-agents", "user", "spider", "automated")


class PerArticleItem(BaseModel):
    """entities.PerArticle in the official spec."""

    project: str
    article: str
    granularity: str
    timestamp: str
    access: str
    agent: str
    views: NonNegativeInt


class PerArticleResponse(BaseModel):
    """entities.PerArticleResponse in the official spec."""

    items: list[PerArticleItem]


class AggregateItem(BaseModel):
    """entities.Aggregate in the official spec: all pageviews of one project in one period."""

    project: str
    granularity: str
    timestamp: str
    access: str
    agent: str
    views: NonNegativeInt


class AggregateResponse(BaseModel):
    """entities.AggregateResponse in the official spec."""

    items: list[AggregateItem]


@dataclass
class AggregateFetch:
    status: Literal["ok", "no_data"]
    items: list[AggregateItem]
    fetched: Fetched


@dataclass
class PageviewFetch:
    status: Literal["ok", "no_data"]    # no_data: HTTP 404, the API holds nothing for this request
    items: list[PerArticleItem]
    fetched: Fetched


def last_complete_month(today: date) -> date:
    """First day of the last calendar month that has fully ended."""
    return date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)


class WikimediaClient:
    def __init__(self, http: HttpClient, settings: Settings, today: date | None = None):
        self.http = http
        self.settings = settings
        self.today = today or date.today()

    def per_article(self, project: str, title: str, start: date, end: date,
                    granularity: Literal["monthly", "daily"] = "monthly") -> PageviewFetch:
        """Views of one article. `start` and `end` are the first and last months (inclusive)."""
        access, agent = self.settings.access, self.settings.agent
        if access not in ACCESS or agent not in AGENTS:
            raise ValueError(f"unsupported access/agent: {access}/{agent}")
        last_day = calendar.monthrange(end.year, end.month)[1]
        first, final = f"{start:%Y%m}0100", f"{end:%Y%m}{last_day:02d}00"
        article = quote(title.replace(" ", "_"), safe="")
        url = (f"{self.settings.pageviews_base}/per-article/{project}/{access}/{agent}/"
               f"{article}/{granularity}/{first}/{final}")
        key = CacheKey(source="wikimedia", endpoint=PER_ARTICLE, language=project.split(".")[0],
                       article=title, start=first, end=final, metric=f"pageviews:{granularity}",
                       extra=f"{access}|{agent}")
        fetched = self.http.get(source="wikimedia", endpoint=PER_ARTICLE, url=url, params=None,
                                key=key, immutable=self._is_final(end))
        if fetched.status == 404:
            return PageviewFetch(status="no_data", items=[], fetched=fetched)
        try:
            parsed = PerArticleResponse.model_validate(fetched.body)
        except ValidationError as exc:
            raise ApiError(f"Malformed pageviews response: {exc.errors()[:2]}", fetched.url, fetched.status) from None
        return PageviewFetch(status="ok", items=parsed.items, fetched=fetched)

    def aggregate(self, project: str, start: date, end: date) -> AggregateFetch:
        """All pageviews of a language edition per month: the denominator for topic penetration.
        Same traffic class (access, agent) as the per-article numbers, so the ratio is like for like."""
        access, agent = self.settings.access, self.settings.agent
        last_day = calendar.monthrange(end.year, end.month)[1]
        first, final = f"{start:%Y%m}0100", f"{end:%Y%m}{last_day:02d}00"
        url = f"{self.settings.pageviews_base}/aggregate/{project}/{access}/{agent}/monthly/{first}/{final}"
        key = CacheKey(source="wikimedia", endpoint=AGGREGATE, language=project.split(".")[0], article="*",
                       start=first, end=final, metric="pageviews:monthly", extra=f"{access}|{agent}")
        fetched = self.http.get(source="wikimedia", endpoint=AGGREGATE, url=url, params=None,
                                key=key, immutable=self._is_final(end))
        if fetched.status == 404:
            return AggregateFetch(status="no_data", items=[], fetched=fetched)
        try:
            parsed = AggregateResponse.model_validate(fetched.body)
        except ValidationError as exc:
            raise ApiError(f"Malformed aggregate response: {exc.errors()[:2]}", fetched.url, fetched.status) from None
        return AggregateFetch(status="ok", items=parsed.items, fetched=fetched)

    def _is_final(self, end: date) -> bool:
        # Monthly data lands a day or two after the month closes; after the 5th it no longer changes.
        last = last_complete_month(self.today)
        return end < last or (end == last and self.today.day >= 5)
