#!/usr/bin/env python3
"""
HTTP access to Wikimedia data, with an on-disk cache.

Three things live here:
  1. WikimediaClient - pageviews (per-article and project-wide baseline).
  2. resolve_topic() - a topic phrase -> exact article title in each language edition.
  3. A file cache, so repeat and follow-up questions cost no network time.

Pageview docs:
  https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html
No API key is needed. A descriptive User-Agent is required by Wikimedia policy.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

PAGEVIEWS_BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews"
DEFAULT_USER_AGENT = os.environ.get(
    "WIKITRENDS_USER_AGENT",
    "wikipedia-topic-interest-skill/1.0 (agent skill; https://agentskills.io)",
)
TIMEOUT = float(os.environ.get("WIKITRENDS_TIMEOUT", "30"))
MAX_RETRIES = 3
# Finalised monthly pageview counts never change, so the cache can be patient.
CACHE_TTL_SECONDS = int(os.environ.get("WIKITRENDS_CACHE_TTL", str(7 * 24 * 3600)))
# Wikimedia's pageview dataset starts here.
DATA_STARTS = date(2015, 7, 1)


class ApiError(Exception):
    """A request failed in a way the caller should report, not retry."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class OfflineMiss(Exception):
    """Offline mode needed a URL that is not in the cache.

    Raised only inside this module; every caller converts it into a normal
    "no data" result so one miss cannot abort a run. Missed URLs accumulate in
    MISSES so the `plan` command can list exactly what still has to be fetched.
    """

    def __init__(self, url: str):
        super().__init__(url)
        self.url = url


# URLs that offline mode could not serve from cache, in request order.
MISSES: List[str] = []


def offline() -> bool:
    """True when the network must not be touched (restricted sandboxes)."""
    return bool(os.environ.get("WIKITRENDS_OFFLINE"))


# --------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------

def cache_dir() -> str:
    override = os.environ.get("WIKITRENDS_CACHE_DIR")
    if override:
        path = override
    else:
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cache")
    os.makedirs(path, exist_ok=True)
    return path


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def _cache_path(url: str) -> str:
    return os.path.join(cache_dir(), cache_key(url) + ".json")


def cache_store(url: str, payload: Any, status: int = 200) -> str:
    """Put a response into the cache as if it had been fetched.

    Used by `ingest` so an agent whose sandbox has no network can hand over data
    it fetched with its own tools, after which everything else works unchanged.
    """
    _cache_write(url, status, payload)
    return _cache_path(url)


def _cache_read(url: str) -> Optional[dict]:
    if os.environ.get("WIKITRENDS_NO_CACHE"):
        return None
    path = _cache_path(url)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            entry = json.load(fh)
    except (OSError, ValueError):
        return None
    if time.time() - entry.get("fetched_at", 0) > CACHE_TTL_SECONDS:
        return None
    return entry


def _cache_write(url: str, status: int, payload: Any) -> None:
    if os.environ.get("WIKITRENDS_NO_CACHE"):
        return
    entry = {"fetched_at": time.time(), "url": url, "status": status, "payload": payload}
    try:
        path = _cache_path(url)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(entry, fh)
        os.replace(tmp, path)
    except OSError:
        pass  # A broken cache must never break an analysis.


def cache_stats() -> Dict[str, Any]:
    path = cache_dir()
    files = [f for f in os.listdir(path) if f.endswith(".json")]
    size = sum(os.path.getsize(os.path.join(path, f)) for f in files)
    return {"dir": path, "entries": len(files), "bytes": size}


def cache_clear() -> int:
    path = cache_dir()
    removed = 0
    for name in os.listdir(path):
        if name.endswith(".json"):
            os.remove(os.path.join(path, name))
            removed += 1
    return removed


# --------------------------------------------------------------------------
# http
# --------------------------------------------------------------------------

def _get_json(url: str, user_agent: str = DEFAULT_USER_AGENT) -> Tuple[int, Any]:
    """GET a JSON document. Returns (status, parsed). 404 is returned, not raised.

    404 from the pageviews API means "no data for this article/range", which is a
    normal analytical outcome (for example, the article does not exist in that
    language edition), so callers get to decide what it means.
    """
    cached = _cache_read(url)
    if cached is not None:
        return cached["status"], cached["payload"]

    if offline():
        if url not in MISSES:
            MISSES.append(url)
        raise OfflineMiss(url)

    last_error: Optional[str] = None
    for attempt in range(MAX_RETRIES):
        request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
                _cache_write(url, response.status, payload)
                return response.status, payload
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            try:
                payload = json.loads(body)
            except ValueError:
                payload = {"detail": body[:400]}
            if exc.code == 404:
                _cache_write(url, 404, payload)
                return 404, payload
            if exc.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                time.sleep(1.5 * (2 ** attempt))
                last_error = f"HTTP {exc.code}"
                continue
            raise ApiError(f"HTTP {exc.code} for {url}: {payload.get('detail', body[:200])}", exc.code)
        except urllib.error.URLError as exc:
            last_error = str(exc.reason)
            if attempt < MAX_RETRIES - 1:
                time.sleep(1.5 * (2 ** attempt))
                continue
        except (ValueError, TimeoutError) as exc:
            last_error = str(exc)
            if attempt < MAX_RETRIES - 1:
                time.sleep(1.5 * (2 ** attempt))
                continue
    raise ApiError(f"Network failure for {url}: {last_error}")


def _encode_title(title: str) -> str:
    """Wikimedia wants underscores for spaces and everything else percent-encoded."""
    return urllib.parse.quote(title.replace(" ", "_"), safe="")


# --------------------------------------------------------------------------
# pageviews
# --------------------------------------------------------------------------

class WikimediaClient:
    def __init__(self, user_agent: str = DEFAULT_USER_AGENT, agent: str = "user", access: str = "all-access"):
        # agent="user" excludes self-identified bots and crawlers. This matters:
        # "all-agents" can inflate a quiet article by an order of magnitude.
        self.user_agent = user_agent
        self.agent = agent
        self.access = access

    def article_pageviews(
        self, project: str, title: str, start: str, end: str, granularity: str = "monthly"
    ) -> Dict[str, Any]:
        """Monthly (or daily) views for one article. Never raises on a missing article."""
        url = (
            f"{PAGEVIEWS_BASE}/per-article/{project}/{self.access}/{self.agent}/"
            f"{_encode_title(title)}/{granularity}/{start}/{end}"
        )
        try:
            status, payload = _get_json(url, self.user_agent)
        except OfflineMiss:
            return {
                "project": project, "title": title, "found": False,
                "reason": "offline mode and this data is not cached yet; run the plan command",
                "points": [],
            }
        if status == 404:
            return {
                "project": project,
                "title": title,
                "found": False,
                "reason": "no pageview data returned for this article and date range",
                "points": [],
            }
        points = [
            {"month": _ts_to_month(item["timestamp"]), "views": int(item["views"])}
            for item in payload.get("items", [])
        ]
        return {"project": project, "title": title, "found": bool(points), "points": points}

    def project_baseline(self, project: str, start: str, end: str, granularity: str = "monthly") -> Dict[str, int]:
        """Total views for a whole language edition, per month.

        Used for two things: making numbers comparable between a huge edition and a
        small one, and detecting months where Wikimedia's own data is incomplete.
        """
        url = (
            f"{PAGEVIEWS_BASE}/aggregate/{project}/{self.access}/{self.agent}/"
            f"{granularity}/{start}/{end}"
        )
        try:
            status, payload = _get_json(url, self.user_agent)
        except OfflineMiss:
            return {}
        if status == 404:
            return {}
        return {_ts_to_month(i["timestamp"]): int(i["views"]) for i in payload.get("items", [])}


def _ts_to_month(timestamp: str) -> str:
    """'2024030100' -> '2024-03'."""
    return f"{timestamp[0:4]}-{timestamp[4:6]}"


# --------------------------------------------------------------------------
# topic -> article titles
# --------------------------------------------------------------------------

def _wiki_api(host: str, params: Dict[str, str], user_agent: str) -> Any:
    params = dict(params, format="json", formatversion="2")
    url = f"https://{host}/w/api.php?" + urllib.parse.urlencode(params)
    try:
        _, payload = _get_json(url, user_agent)
    except OfflineMiss:
        return {}  # resolution then reports "unresolved"; plan lists the URL
    return payload


def search_articles(topic: str, lang: str = "en", limit: int = 5, user_agent: str = DEFAULT_USER_AGENT) -> List[Dict]:
    """Full-text search one edition. Returns candidate titles with Wikidata ids."""
    payload = _wiki_api(
        f"{lang}.wikipedia.org",
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": topic,
            "gsrlimit": str(limit),
            "gsrnamespace": "0",
            "prop": "pageprops",
            "ppprop": "wikibase_item|wikibase-shortdesc",
        },
        user_agent,
    )
    pages = payload.get("query", {}).get("pages", []) or []
    # The generator does not preserve relevance order in the response, index does.
    pages.sort(key=lambda p: p.get("index", 999))
    out = []
    for page in pages:
        props = page.get("pageprops", {}) or {}
        out.append(
            {
                "title": page.get("title"),
                "qid": props.get("wikibase_item"),
                "description": props.get("wikibase-shortdesc", ""),
            }
        )
    return out


def exact_title(title: str, lang: str, user_agent: str = DEFAULT_USER_AGENT) -> Optional[Dict]:
    """Normalise a title in one edition, following redirects, and get its Wikidata id."""
    payload = _wiki_api(
        f"{lang}.wikipedia.org",
        {
            "action": "query",
            "titles": title,
            "redirects": "1",
            "prop": "pageprops",
            "ppprop": "wikibase_item|wikibase-shortdesc",
        },
        user_agent,
    )
    pages = payload.get("query", {}).get("pages", []) or []
    for page in pages:
        if "missing" in page:
            continue
        props = page.get("pageprops", {}) or {}
        return {
            "title": page.get("title"),
            "qid": props.get("wikibase_item"),
            "description": props.get("wikibase-shortdesc", ""),
        }
    return None


def sitelinks(qid: str, langs: List[str], user_agent: str = DEFAULT_USER_AGENT) -> Dict[str, str]:
    """Article titles for one Wikidata concept across many editions, in one request."""
    sites = "|".join(f"{lang.replace('-', '_')}wiki" for lang in langs)
    payload = _wiki_api(
        "www.wikidata.org",
        {"action": "wbgetentities", "ids": qid, "props": "sitelinks", "sitefilter": sites},
        user_agent,
    )
    out: Dict[str, str] = {}
    for entity in (payload.get("entities") or {}).values():
        for site, link in (entity.get("sitelinks") or {}).items():
            out[site[:-4].replace("_", "-")] = link["title"]
    return out


def resolve_topic(
    topic: str,
    langs: List[str],
    pivot: str = "en",
    user_agent: str = DEFAULT_USER_AGENT,
) -> Dict[str, Any]:
    """Map a topic phrase to the exact article title in each requested edition.

    Strategy: pin down the *concept* once (in a pivot edition the phrase is written
    in), then read its Wikidata sitelinks. One concept lookup covers every language,
    and translated titles come from editors rather than from a guess.

    A language with no sitelink is reported as missing rather than substituted --
    "this edition has no article on the topic" is a finding worth surfacing.
    """
    candidates: List[Dict] = []
    entry = exact_title(topic, pivot, user_agent)
    if entry and entry.get("qid"):
        method = "exact title match"
        candidates = [entry]
    else:
        candidates = [c for c in search_articles(topic, pivot, 5, user_agent) if c.get("qid")]
        method = "full-text search"
        entry = candidates[0] if candidates else None

    if not entry or not entry.get("qid"):
        return {
            "topic": topic,
            "status": "unresolved",
            "reason": (
                f"No {pivot}.wikipedia article with a Wikidata item matched '{topic}'. "
                f"Try a different pivot language (--pivot) or pass titles directly with --articles."
            ),
            "articles": {},
            "candidates": candidates,
        }

    qid = entry["qid"]
    links = sitelinks(qid, langs, user_agent)
    if pivot in langs and pivot not in links:
        links[pivot] = entry["title"]

    return {
        "topic": topic,
        "status": "resolved",
        "qid": qid,
        "concept": entry["title"],
        "description": entry.get("description", ""),
        "resolved_via": f"{method} in {pivot}.wikipedia, then Wikidata sitelinks ({qid})",
        "articles": {lang: links[lang] for lang in langs if lang in links},
        "missing_languages": [lang for lang in langs if lang not in links],
        # Kept so the agent can offer alternatives if it picked the wrong concept.
        "other_candidates": [c["title"] for c in candidates[1:4]],
    }


# --------------------------------------------------------------------------
# dates
# --------------------------------------------------------------------------

def month_window(months: int, today: Optional[date] = None) -> Tuple[str, str, str, str]:
    """A whole-month window ending with the last *complete* month.

    Returns (start_yyyymmdd, end_yyyymmdd, start_month, end_month). Aligning to
    month boundaries is what keeps partial-month counts out of the series: asking
    the API for .../monthly/20240101/20240401 yields an "April" of one single day.
    """
    today = today or date.today()
    end_year, end_month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    total = end_year * 12 + (end_month - 1) - (months - 1)
    start_year, start_month = divmod(total, 12)
    start_month += 1
    start = date(start_year, start_month, 1)
    if start < DATA_STARTS:
        start = DATA_STARTS
    last_day = _last_day(end_year, end_month)
    return (
        start.strftime("%Y%m%d"),
        date(end_year, end_month, last_day).strftime("%Y%m%d"),
        start.strftime("%Y-%m"),
        f"{end_year:04d}-{end_month:02d}",
    )


def _last_day(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date.resolution).day


def parse_month(value: str) -> str:
    """Accept 2024-03, 2024/03, 202403, 2024-03-15 -> '2024-03'."""
    cleaned = value.strip().replace("/", "-")
    for fmt in ("%Y-%m", "%Y-%m-%d", "%Y%m", "%Y%m%d"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m")
        except ValueError:
            continue
    raise ValueError(f"Cannot read '{value}' as a month (use YYYY-MM)")


def main() -> int:
    """Smoke test against the live API."""
    client = WikimediaClient()
    start, end, start_m, end_m = month_window(6)
    print(f"window {start_m}..{end_m}", file=sys.stderr)
    resolution = resolve_topic("astronomy", ["uk", "pl"])
    print(json.dumps(resolution, ensure_ascii=False, indent=2))
    for lang, title in resolution["articles"].items():
        series = client.article_pageviews(f"{lang}.wikipedia", title, start, end)
        print(lang, title, [p["views"] for p in series["points"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
