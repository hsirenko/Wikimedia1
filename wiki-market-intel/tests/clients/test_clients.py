"""HTTP and Wikimedia client behaviour (spec §31: success, HTTP error, timeout, malformed, retry)."""

import json
from datetime import date

import httpx
import pytest

from wiki_market_intel.errors import ApiError
from wiki_market_intel.service import build_services
from tests.conftest import TODAY, FakeWikimedia


def _pageviews(services, title="Meditation", start=date(2020, 9, 1), end=date(2026, 8, 1)):
    return services.wikimedia.per_article("de.wikipedia", title, start, end)


def _services(settings, fake, **kw):
    return build_services(settings, transport=httpx.MockTransport(fake), today=TODAY, backoff=0, **kw)


def test_successful_response_is_validated_and_complete(services, fake):
    result = _pageviews(services)
    assert result.status == "ok" and len(result.items) == 72
    url = str(fake.requests[0].url)
    assert url.endswith("/per-article/de.wikipedia/all-access/user/Meditation/monthly/2020090100/2026083100")
    assert fake.requests[0].headers["User-Agent"].startswith("wiki-market-intel/")


def test_titles_are_encoded_safely(services, fake):
    _pageviews(services, title="AC/DC (band)")
    assert "/AC%2FDC_%28band%29/" in str(fake.requests[0].url)


def test_404_means_no_data_not_zero(services):
    result = _pageviews(services, title="Nothing here")
    assert result.status == "no_data" and result.items == []


def test_http_error_raises_api_error(settings):
    fake = FakeWikimedia(fail={"per-article": [httpx.Response(400, json={"detail": "bad request"})]})
    with pytest.raises(ApiError) as err:
        _pageviews(_services(settings, fake))
    assert err.value.status == 400


def test_timeout_is_retried_then_reported(settings):
    fake = FakeWikimedia(fail={"per-article": [httpx.ReadTimeout("slow")] * 4})
    with pytest.raises(ApiError, match="Giving up after 4 attempts"):
        _pageviews(_services(settings, fake))
    assert len(fake.requests) == 4


def test_retry_recovers_from_transient_errors(settings):
    fake = FakeWikimedia(fail={"per-article": [httpx.Response(503), httpx.ConnectError("reset"), httpx.Response(429)]})
    result = _pageviews(_services(settings, fake))
    assert result.status == "ok" and len(fake.requests) == 4


def test_malformed_body_and_schema_are_rejected(settings):
    not_json = FakeWikimedia(fail={"per-article": [httpx.Response(200, content=b"<html>oops</html>")]})
    with pytest.raises(ApiError, match="not JSON"):
        _pageviews(_services(settings, not_json))
    wrong_shape = FakeWikimedia(pageviews={"items": [{"views": -5}]})
    with pytest.raises(ApiError, match="Malformed pageviews response"):
        _pageviews(_services(settings, wrong_shape))


def test_raw_response_is_archived_before_transformation(services, settings):
    result = _pageviews(services)
    envelope = json.loads(open(result.fetched.raw_path, encoding="utf-8").read())
    assert envelope["source"] == "wikimedia" and envelope["endpoint"] == "pageviews/per-article"
    assert envelope["retrieved_at"] and envelope["request"]["url"] == result.fetched.url
    assert len(envelope["response"]["items"]) == 72


def test_cache_prevents_repeat_requests(settings, fake):
    first = _services(settings, fake)
    _pageviews(first)
    second = _services(settings, fake)          # a new process, same cache directory
    result = _pageviews(second)
    assert len(fake.requests) == 1 and result.fetched.cached is True


def test_cache_can_be_disabled(settings, fake):
    _pageviews(_services(settings, fake, use_cache=False))
    _pageviews(_services(settings, fake, use_cache=False))
    assert len(fake.requests) == 2
