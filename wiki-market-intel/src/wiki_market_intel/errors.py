"""Errors that keep 'no data', 'API failure' and 'not found' distinct (spec §30)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wiki_market_intel.models.topic import TopicResolution


class WikiMarketError(Exception):
    """Base class for every error this package raises on purpose."""


class ApiError(WikiMarketError):
    """A request failed: network, HTTP error status, or a malformed response."""

    def __init__(self, message: str, url: str, status: int | None = None):
        super().__init__(message)
        self.url = url
        self.status = status


class TopicNotFoundError(WikiMarketError):
    """No Wikipedia article or Wikidata entity matches the requested topic."""

    def __init__(self, resolution: "TopicResolution"):
        super().__init__(f"Topic not found: {resolution.query!r}")
        self.resolution = resolution


class AmbiguousTopicError(WikiMarketError):
    """Several concepts are plausible. The system never picks one silently (spec §5, rule 8)."""

    def __init__(self, resolution: "TopicResolution"):
        names = ", ".join(c.title for c in resolution.candidates) or "none"
        super().__init__(f"Topic resolution requires review for {resolution.query!r}. Candidates: {names}")
        self.resolution = resolution


class ArticleMissingError(WikiMarketError):
    """The concept exists, but the requested language edition has no article about it."""

    def __init__(self, resolution: "TopicResolution", language: str):
        super().__init__(f"{language}.wikipedia has no article for {resolution.canonical_topic!r} "
                         f"(Wikidata {resolution.wikidata_id}).")
        self.resolution = resolution
        self.language = language
