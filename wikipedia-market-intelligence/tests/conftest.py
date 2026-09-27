"""Shared fixtures: a fake Wikimedia behind httpx.MockTransport. No test touches the network
except those marked `integration`."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pytest

from wiki_market_intel.config import Settings
from wiki_market_intel.service import build_services

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 9, 27)       # the real Meditation fixture ends at 2026-08, the last complete month


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text("utf-8"))


# (language, title) -> (page id, Wikidata id, is disambiguation, redirect target)
PAGES = {
    ("en", "meditation"): (20062, "Q108458", False, None),
    ("en", "Meditation"): (20062, "Q108458", False, None),
    ("de", "Meditation"): (28837, "Q108458", False, None),
    ("en", "Mindfulness meditation"): (111, "Q1935", False, "Mindfulness"),
    ("en", "Mindfulness"): (111, "Q1935", False, None),
    ("en", "Mercury"): (222, "Q1", True, None),
    ("en", "Obscurium"): (333, None, False, None),
}
ENTITIES = {
    "Q108458": {"label": "meditation", "sitelinks": {"enwiki": "Meditation", "dewiki": "Meditation"}},
    "Q1935": {"label": "mindfulness", "sitelinks": {"enwiki": "Mindfulness"}},
}
SEARCH = {
    "Mercury": [("Mercury (planet)", "Q308", "Smallest planet"), ("Mercury (element)", "Q925", "Chemical element")],
    "Meditaton": [("Meditation", "Q108458", "Techniques to train attention")],
}


class FakeWikimedia:
    """Routes requests like the real APIs. Records every request for assertions."""

    def __init__(self, pageviews: dict | None = None, fail: dict | None = None):
        self.requests: list[httpx.Request] = []
        self.pageviews = pageviews if pageviews is not None else load("pageviews_meditation_de_2020-09_2026-08.json")
        self.fail = fail or {}   # substring of URL -> list of responses/exceptions to return in order

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        for needle, outcomes in self.fail.items():
            if needle in url and outcomes:
                outcome = outcomes.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        if "/metrics/pageviews/per-article/" in url:
            return self._pageviews(url)
        query = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        if "wikidata.org" in url:
            return self._entity(query)
        lang = urlparse(url).hostname.split(".")[0]
        if query.get("generator") == "search":
            return self._search(query["gsrsearch"])
        return self._page(lang, query["titles"])

    def _pageviews(self, url: str) -> httpx.Response:
        article = unquote(url.split("/per-article/")[1].split("/")[3]).replace("_", " ")
        if article != "Meditation":
            return httpx.Response(404, json={"type": "not_found", "title": "Not found."})
        return httpx.Response(200, json=self.pageviews)

    def _page(self, lang: str, title: str) -> httpx.Response:
        hit = PAGES.get((lang, title))
        if hit is None:
            return httpx.Response(200, json={"query": {"pages": [{"ns": 0, "title": title, "missing": True}]}})
        page_id, qid, disamb, redirect = hit
        target = redirect or (title[0].upper() + title[1:])
        props = {"wikibase_item": qid} if qid else {}
        if disamb:
            props["disambiguation"] = ""
        body: dict = {"query": {"pages": [{"pageid": page_id, "ns": 0, "title": target, "pageprops": props}]}}
        if redirect:
            body["query"]["redirects"] = [{"from": title, "to": redirect}]
        return httpx.Response(200, json=body)

    def _search(self, text: str) -> httpx.Response:
        pages = [{"pageid": 900 + i, "ns": 0, "title": t, "index": i + 1,
                  "pageprops": {"wikibase_item": q, "wikibase-shortdesc": d}}
                 for i, (t, q, d) in enumerate(SEARCH.get(text, []))]
        return httpx.Response(200, json={"query": {"pages": pages}} if pages else {"batchcomplete": True})

    def _entity(self, query: dict) -> httpx.Response:
        qid = query["ids"]
        entity = ENTITIES.get(qid)
        if entity is None:
            return httpx.Response(200, json={"entities": {qid: {"id": qid, "missing": ""}}})
        wanted = set(query.get("sitefilter", "").split("|"))
        links = {site: {"site": site, "title": title} for site, title in entity["sitelinks"].items()
                 if not wanted or site in wanted}
        return httpx.Response(200, json={"entities": {qid: {
            "id": qid, "labels": {"en": {"language": "en", "value": entity["label"]}}, "sitelinks": links}}})


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", reports_dir=tmp_path / "reports")


@pytest.fixture
def fake() -> FakeWikimedia:
    return FakeWikimedia()


@pytest.fixture
def services(settings: Settings, fake: FakeWikimedia):
    built = build_services(settings, transport=httpx.MockTransport(fake), today=TODAY, backoff=0)
    yield built
    built.http.close()
