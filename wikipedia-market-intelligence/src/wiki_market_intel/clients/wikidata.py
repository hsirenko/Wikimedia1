"""Wikipedia (MediaWiki Action API) and Wikidata clients used by topic resolution."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from wiki_market_intel.clients.http import HttpClient
from wiki_market_intel.config import Settings
from wiki_market_intel.data.cache import CacheKey
from wiki_market_intel.errors import ApiError
from wiki_market_intel.models.topic import TopicCandidate


@dataclass
class PageInfo:
    title: str                  # normalized title after redirects
    page_id: int
    wikidata_id: str | None
    description: str | None
    is_disambiguation: bool
    redirected_from: str | None


class _Page(BaseModel):
    title: str
    pageid: int | None = None
    missing: bool = False
    invalid: bool = False
    pageprops: dict[str, str] = {}
    index: int | None = None


def _pages(body: dict, url: str) -> list[_Page]:
    try:
        return [_Page.model_validate(p) for p in body.get("query", {}).get("pages", [])]
    except ValidationError as exc:
        raise ApiError(f"Malformed MediaWiki response: {exc.errors()[:2]}", url) from None


class WikipediaClient:
    def __init__(self, http: HttpClient, settings: Settings):
        self.http = http
        self.settings = settings

    def _get(self, lang: str, endpoint: str, params: dict, article: str, metric: str) -> dict:
        url = self.settings.wikipedia_api.format(lang=lang)
        key = CacheKey(source="wikipedia", endpoint=endpoint, language=lang, article=article,
                       start="", end="", metric=metric, extra=repr(sorted(params.items())))
        fetched = self.http.get(source="wikipedia", endpoint=endpoint, url=url, params=params,
                                key=key, immutable=False)
        if fetched.status != 200 or not isinstance(fetched.body, dict):
            raise ApiError(f"Unexpected MediaWiki response ({fetched.status})", fetched.url, fetched.status)
        return fetched.body

    def page_info(self, lang: str, title: str) -> PageInfo | None:
        """The page a title points to, following redirects. None if it does not exist."""
        params = {"action": "query", "format": "json", "formatversion": "2", "redirects": "1",
                  "titles": title, "prop": "pageprops|info",
                  "ppprop": "wikibase_item|disambiguation|wikibase-shortdesc"}
        body = self._get(lang, "action/query:pageinfo", params, title, "pageinfo")
        pages = _pages(body, self.settings.wikipedia_api.format(lang=lang))
        if not pages or pages[0].missing or pages[0].invalid or pages[0].pageid is None:
            return None
        page = pages[0]
        redirects = body.get("query", {}).get("redirects") or []
        return PageInfo(title=page.title, page_id=page.pageid, wikidata_id=page.pageprops.get("wikibase_item"),
                        description=page.pageprops.get("wikibase-shortdesc"),
                        is_disambiguation="disambiguation" in page.pageprops,
                        redirected_from=redirects[0]["from"] if redirects else None)

    def search(self, lang: str, query: str, limit: int = 5) -> list[TopicCandidate]:
        params = {"action": "query", "format": "json", "formatversion": "2", "generator": "search",
                  "gsrsearch": query, "gsrlimit": str(limit), "gsrnamespace": "0",
                  "prop": "pageprops", "ppprop": "wikibase_item|wikibase-shortdesc|disambiguation"}
        body = self._get(lang, "action/query:search", params, query, "search")
        pages = sorted(_pages(body, self.settings.wikipedia_api.format(lang=lang)), key=lambda p: p.index or 0)
        return [TopicCandidate(title=p.title, page_id=p.pageid, wikidata_id=p.pageprops.get("wikibase_item"),
                               description=p.pageprops.get("wikibase-shortdesc"))
                for p in pages if "disambiguation" not in p.pageprops]


class WikidataClient:
    def __init__(self, http: HttpClient, settings: Settings):
        self.http = http
        self.settings = settings

    def entity(self, qid: str, languages: list[str]) -> tuple[str | None, dict[str, str]]:
        """(English label, {language: article title}) for the requested languages."""
        sites = "|".join(f"{lang.replace('-', '_')}wiki" for lang in languages)
        params = {"action": "wbgetentities", "format": "json", "ids": qid, "props": "sitelinks|labels",
                  "sitefilter": sites, "languages": "en"}
        key = CacheKey(source="wikidata", endpoint="wbgetentities", language=",".join(languages), article=qid,
                       start="", end="", metric="sitelinks")
        fetched = self.http.get(source="wikidata", endpoint="wbgetentities", url=self.settings.wikidata_api,
                                params=params, key=key, immutable=False)
        entity = (fetched.body or {}).get("entities", {}).get(qid) if isinstance(fetched.body, dict) else None
        if not entity or "missing" in entity:
            return None, {}
        label = entity.get("labels", {}).get("en", {}).get("value")
        links = {site[:-4].replace("_", "-"): value["title"]
                 for site, value in entity.get("sitelinks", {}).items() if site.endswith("wiki")}
        return label, links
