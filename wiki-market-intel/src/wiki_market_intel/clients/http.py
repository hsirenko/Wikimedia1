"""The only place in the package that performs HTTP (spec §6).

Timeouts, retries with exponential backoff, error classification, logging,
raw-response archiving and caching all happen here, once.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from tenacity import RetryError, Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from wiki_market_intel.config import Settings
from wiki_market_intel.data.cache import Cache, CacheKey
from wiki_market_intel.data.raw_store import RawStore
from wiki_market_intel.errors import ApiError

log = logging.getLogger("wiki_market_intel.http")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class _Retryable(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class Fetched:
    """A response plus where it came from. `cached` tells whether a request was made."""

    status: int
    body: Any
    url: str
    endpoint: str
    retrieved_at: str
    raw_path: str
    cached: bool


class HttpClient:
    def __init__(self, settings: Settings, raw_store: RawStore, cache: Cache,
                 transport: httpx.BaseTransport | None = None, backoff: float = 0.5,
                 sleep: Callable[[float], None] = time.sleep):
        self.settings = settings
        self.raw_store = raw_store
        self.cache = cache
        self.backoff = backoff
        self.sleep = sleep
        self._client = httpx.Client(
            headers={"User-Agent": settings.user_agent, "Accept": "application/json"},
            timeout=settings.timeout_seconds, transport=transport, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    # -- public ---------------------------------------------------------------

    def get(self, *, source: str, endpoint: str, url: str, params: dict[str, Any] | None,
            key: CacheKey, immutable: bool) -> Fetched:
        """GET JSON through the cache. 404 is returned (not raised): for pageviews it
        means 'no data', which callers must report explicitly rather than as zero."""
        hit = self.cache.get(key)
        if hit is not None:
            return Fetched(cached=True, **hit)

        status, body, final_url = self._request(url, params)
        raw_path, retrieved_at = self.raw_store.save(
            source=source, endpoint=endpoint, url=final_url, request={"params": params or {}},
            status=status, response=body)
        fetched = Fetched(status=status, body=body, url=final_url, endpoint=endpoint,
                          retrieved_at=retrieved_at, raw_path=str(raw_path), cached=False)
        self.cache.set(key, {k: v for k, v in fetched.__dict__.items() if k != "cached"},
                       immutable=immutable and status == 200)
        return fetched

    # -- internals --------------------------------------------------------------

    def _request(self, url: str, params: dict[str, Any] | None) -> tuple[int, Any, str]:
        retrying = Retrying(
            stop=stop_after_attempt(self.settings.max_attempts),
            wait=wait_exponential(multiplier=self.backoff, max=8) if self.backoff else (lambda _: 0),
            retry=retry_if_exception_type(_Retryable),
            sleep=self.sleep,
        )
        try:
            for attempt in retrying:
                with attempt:
                    return self._once(url, params, attempt.retry_state.attempt_number)
        except RetryError as exc:
            last = exc.last_attempt.exception()
            raise ApiError(f"Giving up after {self.settings.max_attempts} attempts: {last}", url,
                           getattr(last, "status", None)) from None
        raise AssertionError("unreachable")

    def _once(self, url: str, params: dict[str, Any] | None, attempt: int) -> tuple[int, Any, str]:
        started = time.monotonic()
        try:
            response = self._client.get(url, params=params)
        except httpx.TimeoutException as exc:
            log.warning("timeout attempt=%d url=%s", attempt, url)
            raise _Retryable(f"timeout: {exc}") from None
        except httpx.TransportError as exc:
            log.warning("network error attempt=%d url=%s error=%s", attempt, url, exc)
            raise _Retryable(f"network error: {exc}") from None

        elapsed = (time.monotonic() - started) * 1000
        log.info("GET %s -> %d (%.0f ms, attempt %d)", response.url, response.status_code, elapsed, attempt)
        if response.status_code in RETRYABLE_STATUS:
            raise _Retryable(f"HTTP {response.status_code}", response.status_code)
        if response.status_code not in (200, 404):
            raise ApiError(f"HTTP {response.status_code}: {response.text[:200]}", str(response.url),
                           response.status_code)
        try:
            body = response.json()
        except ValueError:
            raise ApiError("Malformed response: body is not JSON", str(response.url), response.status_code) from None
        return response.status_code, body, str(response.url)
