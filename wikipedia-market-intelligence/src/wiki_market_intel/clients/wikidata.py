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


# ---------------------------------------------------------------------------
# relations used by the topic ecosystem (spec §19)
# ---------------------------------------------------------------------------

def _wikidata_get(client: "WikidataClient", endpoint: str, params: dict, article: str, metric: str) -> dict:
    key = CacheKey(source="wikidata", endpoint=endpoint, language="", article=article, start="", end="",
                   metric=metric, extra=repr(sorted(params.items())))
    fetched = client.http.get(source="wikidata", endpoint=endpoint, url=client.settings.wikidata_api,
                              params=params, key=key, immutable=False)
    if fetched.status != 200 or not isinstance(fetched.body, dict):
        raise ApiError(f"Unexpected Wikidata response ({fetched.status})", fetched.url, fetched.status)
    return fetched.body


def claims(client: "WikidataClient", qid: str, properties: tuple[str, ...]) -> dict[str, list[str]]:
    """Item-valued statements of `qid` for the given properties, e.g. {"P279": ["Q955260", ...]}."""
    body = _wikidata_get(client, "wbgetentities:claims", {"action": "wbgetentities", "format": "json",
                                                            "ids": qid, "props": "claims"}, qid, "claims")
    entity = body.get("entities", {}).get(qid, {})
    out: dict[str, list[str]] = {}
    for prop in properties:
        for claim in entity.get("claims", {}).get(prop, []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(value, dict) and value.get("id"):
                out.setdefault(prop, []).append(value["id"])
    return out


def reverse(client: "WikidataClient", prop: str, qid: str, limit: int) -> list[str]:
    """Items that state `prop` = `qid` (e.g. subclasses of it), via Wikidata search haswbstatement."""
    body = _wikidata_get(client, "query:haswbstatement", {"action": "query", "format": "json", "list": "search",
                                                           "srsearch": f"haswbstatement:{prop}={qid}",
                                                           "srlimit": str(limit), "srnamespace": "0"},
                         qid, f"reverse:{prop}")
    return [hit["title"] for hit in body.get("query", {}).get("search", []) if hit.get("title", "").startswith("Q")]


def sitelinks(client: "WikidataClient", qids: list[str], language: str) -> dict[str, str]:
    """{qid: article title in `language`} for the items that have one (batched by 50)."""
    out: dict[str, str] = {}
    site = f"{language.replace('-', '_')}wiki"
    for i in range(0, len(qids), 50):
        batch = qids[i:i + 50]
        body = _wikidata_get(client, "wbgetentities:sitelinks", {"action": "wbgetentities", "format": "json",
                                                                  "ids": "|".join(batch), "props": "sitelinks",
                                                                  "sitefilter": site}, ",".join(batch), site)
        for qid, entity in body.get("entities", {}).items():
            title = entity.get("sitelinks", {}).get(site, {}).get("title")
            if title:
                out[qid] = title
    return out


def morelike(client: "WikipediaClient", lang: str, title: str, limit: int) -> list[TopicCandidate]:
    """Articles whose text is most similar ('more like this' search). Similar content is not a
    typed relationship, and the report labels it that way."""
    params = {"action": "query", "format": "json", "formatversion": "2", "generator": "search",
              "gsrsearch": f"morelike:{title}", "gsrlimit": str(limit), "gsrnamespace": "0",
              "prop": "pageprops", "ppprop": "wikibase_item|wikibase-shortdesc|disambiguation"}
    body = client._get(lang, "action/query:morelike", params, title, "morelike")
    pages = sorted(_pages(body, client.settings.wikipedia_api.format(lang=lang)), key=lambda p: p.index or 0)
    return [TopicCandidate(title=p.title, page_id=p.pageid, wikidata_id=p.pageprops.get("wikibase_item"),
                           description=p.pageprops.get("wikibase-shortdesc"))
            for p in pages if "disambiguation" not in p.pageprops]
