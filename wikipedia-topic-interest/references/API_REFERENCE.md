# Wikimedia and Wikipedia APIs used

All endpoints are public and need no key. A descriptive `User-Agent` is required by
Wikimedia policy; override the default with `WIKITRENDS_USER_AGENT`.

Official docs:
https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html

## 1. Per-article pageviews

```
GET https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article
    /{project}/{access}/{agent}/{article}/{granularity}/{start}/{end}
```

| part | values used here | notes |
|---|---|---|
| `project` | `uk.wikipedia`, `pl.wikipedia`, … | `{lang}.wikipedia` |
| `access` | `all-access` | also `desktop`, `mobile-web`, `mobile-app` |
| `agent` | `user` | **excludes bots.** `all-agents` can inflate quiet articles several-fold |
| `article` | `Астрономія` → percent-encoded | spaces become `_`; `/` must be `%2F` |
| `granularity` | `monthly` | `daily` also supported |
| `start`/`end` | `YYYYMMDD` | inclusive |

Response:

```json
{"items": [
  {"project":"uk.wikipedia","article":"Астрономія","granularity":"monthly",
   "timestamp":"2024010100","access":"all-access","agent":"user","views":3700}
]}
```

`timestamp` is `YYYYMMDDHH`; for monthly data only the year and month are meaningful.

### The partial-month trap

`monthly/20240101/20240401` returns four items, and the April one covers **one day**:

```
2024-01  3700
2024-02  3206
2024-03  2140
2024-04    72   <-- 1 April only, not a real month
```

Any first-vs-last growth calculation reads that as a 98% collapse. Always request
whole months ending with the last *complete* month — `month_window()` does this.

## 2. Project-wide pageviews (the baseline)

```
GET https://wikimedia.org/api/rest_v1/metrics/pageviews/aggregate
    /{project}/{access}/{agent}/{granularity}/{start}/{end}
```

Total views for an entire language edition per month. Used for two things:

1. **Normalisation** — views per million edition views, the only fair way to compare
   a 9-billion-views-a-year edition with a 700-million one.
2. **Incompleteness detection** — a month whose edition-wide total collapses is a
   data-pipeline gap, not a drop in reading.

Typical scale (12 months to 2026-08): de 8.46B, es 6.53B, pl 2.26B, uk 0.68B.

## 3. Topic to article title

The same concept has a different title in every edition, and it is not a translation
you can guess (`Intermittent fasting` → `Přerušovaný půst` → `Інтервальне голодування`).
Resolution is therefore concept-based:

**Step 1 — identify the concept** in a pivot edition (default `en`):

```
GET https://en.wikipedia.org/w/api.php?action=query&titles=Intermittent%20fasting
    &redirects=1&prop=pageprops&ppprop=wikibase_item&format=json&formatversion=2
```

Returns `pageprops.wikibase_item`, e.g. `Q1666254`. If the exact title misses, the
same endpoint is used with `generator=search` and the best-ranked hit is taken.

**Step 2 — read that concept's titles in every requested edition**, one request for
all languages:

```
GET https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q1666254
    &props=sitelinks&sitefilter=plwiki|cswiki|ukwiki&format=json&formatversion=2
```

```json
{"entities":{"Q1666254":{"sitelinks":{
  "cswiki":{"title":"Přerušovaný půst"},
  "ukwiki":{"title":"Інтервальне голодування"}}}}}
```

Note what is **absent**: there is no `plwiki` entry, because Polish Wikipedia has no
article on intermittent fasting. That is reported as a missing language, never
substituted with a lookalike. Verified by probing `Post przerywany`, `Przerywany post`
and `Okresowa głodówka`, all of which are missing; `Głodówka` is a different concept.

Site codes are `{lang}wiki` with hyphens replaced by underscores (`zh-min-nan` →
`zh_min_nanwiki`).

### Why not search each language separately

Full-text search in a language that lacks the article returns confident nonsense. For
`post przerywany`, Polish Wikipedia's top hits were *Charlie Kirk*, *Insulinooporność*
and *Aborcja*. Concept-based resolution fails honestly instead.

## Status codes and failures

| code | meaning | handling |
|---|---|---|
| 200 | data | parsed |
| 404 | no data for this article, project or range | returned as "not found", not an error — usually means the article does not exist in that edition |
| 429 | rate limited | retried with exponential backoff (1.5s, 3s) |
| 400 | malformed request, usually a bad project code | raised as `ApiError`; one bad language does not abort the run |
| 5xx | transient | retried up to 3 attempts |

## Rate limits and caching

Wikimedia asks for reasonable use rather than publishing a hard per-second limit. This
skill uses at most 4 concurrent requests and caches every response on disk for 7 days
(finalised monthly counts never change), so follow-up questions usually need no
network at all.

| environment variable | purpose |
|---|---|
| `WIKITRENDS_USER_AGENT` | identify yourself to Wikimedia |
| `WIKITRENDS_CACHE_DIR` | cache location (default `<skill>/.cache`) |
| `WIKITRENDS_CACHE_TTL` | cache lifetime in seconds |
| `WIKITRENDS_NO_CACHE` | set to disable caching |
| `WIKITRENDS_TIMEOUT` | per-request timeout in seconds |

## Language codes

`{lang}.wikipedia`, e.g. `en`, de`, `fr`, `es`, `pt`, `it`, `nl`, `pl`, `cs`, `sk`,
`uk`, `ru`, `tr`, `ro`, `hu`, `sv`, `fi`, `da`, `no`, `el`, `bg`, `hr`, `sr`, `lt`,
`lv`, `et`, `he`, `ar`, `fa`, `hi`, `id`, `vi`, `th`, `ja`, `ko`, `zh`.

Full list: https://en.wikipedia.org/wiki/List_of_Wikipedias

## Other endpoints worth knowing (not yet used)

- `top/{project}/{access}/{year}/{month}/{day}` — the 1000 most-read articles, useful
  for discovering topics rather than testing a known one.
- `top-by-country/{project}/{access}/{year}/{month}` — geography, with heavy privacy
  rounding.
- `per-article/.../daily/...` — daily granularity, already supported through
  `--granularity daily`; needed to pin down what a spike actually was.
