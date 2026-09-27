"""Topic resolution (spec §5): user text -> Wikidata entity -> article per language.

Confidence is a documented rule, not a model score:

| Match                                         | confidence |
|-----------------------------------------------|-----------:|
| Wikidata id given (Q123)                      | 1.00       |
| exact article title (ignoring case, _ vs " ") | 0.98       |
| title reached through a redirect              | 0.90       |
| article exists but has no Wikidata entity     | 0.70       |
| disambiguation page or search-only match      | needs review, no choice made |
"""

from __future__ import annotations

import re

from wiki_market_intel.clients.wikidata import PageInfo, WikidataClient, WikipediaClient
from wiki_market_intel.models.topic import ArticleRef, TopicResolution

CONFIDENCE = {"wikidata_id": 1.0, "exact_title": 0.98, "redirect": 0.90, "no_wikidata": 0.70}


def _norm(text: str) -> str:
    return re.sub(r"[\s_]+", " ", text).strip().casefold()


class TopicResolver:
    def __init__(self, wikipedia: WikipediaClient, wikidata: WikidataClient, pivot: str = "en"):
        self.wikipedia = wikipedia
        self.wikidata = wikidata
        self.pivot = pivot

    def resolve(self, query: str, languages: list[str]) -> TopicResolution:
        query = query.strip()
        if re.fullmatch(r"[Qq]\d+", query):
            return self._from_entity(query, query.upper(), languages, "wikidata_id", notes=[])

        # The phrase may be written in the pivot language or in any requested language.
        for lang in dict.fromkeys([self.pivot, *languages]):
            info = self.wikipedia.page_info(lang, query)
            if info is None:
                continue
            if info.is_disambiguation:
                return self._review(query, lang, f"'{info.title}' on {lang}.wikipedia is a disambiguation page.")
            return self._from_page(query, lang, info, languages)

        return self._review(query, self.pivot, f"No article titled '{query}' on "
                            f"{', '.join(dict.fromkeys([self.pivot, *languages]))}.wikipedia.")

    # -- helpers ----------------------------------------------------------------

    def _from_page(self, query: str, lang: str, info: PageInfo, languages: list[str]) -> TopicResolution:
        notes = []
        if info.redirected_from and _norm(info.redirected_from) != _norm(info.title):
            method = "redirect"
            notes.append(f"'{query}' redirects to '{info.title}' on {lang}.wikipedia.")
        else:
            method = "exact_title"
        if info.wikidata_id is None:
            return TopicResolution(
                query=query, status="resolved", canonical_topic=info.title, confidence=CONFIDENCE["no_wikidata"],
                method="no_wikidata", articles={lang: ArticleRef(language=lang, title=info.title, page_id=info.page_id)},
                missing_languages=[l for l in languages if l != lang],
                notes=notes + [f"'{info.title}' has no Wikidata entity, so other languages cannot be matched."])
        return self._from_entity(query, info.wikidata_id, languages, method, notes, found=(lang, info))

    def _from_entity(self, query: str, qid: str, languages: list[str], method: str, notes: list[str],
                     found: tuple[str, PageInfo] | None = None) -> TopicResolution:
        label, links = self.wikidata.entity(qid, list(dict.fromkeys([*languages, self.pivot])))
        if not links and found is None:
            return TopicResolution(query=query, status="not_found", wikidata_id=qid, method=method,
                                   notes=notes + [f"Wikidata {qid} does not exist or has no Wikipedia articles."])
        articles: dict[str, ArticleRef] = {}
        missing: list[str] = []
        for lang in languages:
            title = links.get(lang)
            if found and found[0] == lang:
                articles[lang] = ArticleRef(language=lang, title=found[1].title, page_id=found[1].page_id)
            elif title:
                info = self.wikipedia.page_info(lang, title)
                articles[lang] = ArticleRef(language=lang, title=title, page_id=info.page_id if info else None)
            else:
                missing.append(lang)
        if missing:
            notes.append(f"No article in: {', '.join(missing)} (Wikidata {qid} has no sitelink there).")
        # Prefer the article's own title: Wikidata lowercases labels of common nouns ("meditation").
        canonical = (found[1].title if found else links.get(self.pivot)) or label or query
        return TopicResolution(query=query, status="resolved", canonical_topic=canonical, wikidata_id=qid,
                               articles=articles, missing_languages=missing, confidence=CONFIDENCE[method],
                               method=method, notes=notes)

    def _review(self, query: str, lang: str, reason: str) -> TopicResolution:
        candidates = self.wikipedia.search(lang, query)
        if not candidates:
            return TopicResolution(query=query, status="not_found", method="search", notes=[reason])
        return TopicResolution(query=query, status="needs_review", method="search", candidates=candidates,
                               notes=[reason, "Several concepts are plausible; none was chosen automatically."])
