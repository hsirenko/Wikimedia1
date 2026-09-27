# wiki-market-intel

A market-intelligence engine built on Wikimedia pageview data. It measures the **size, trajectory
and seasonality of attention** to a topic in a Wikipedia language edition. It also states **what
the data cannot tell you** and what must be validated elsewhere before a product or investment
decision.

> Wikipedia pageviews measure attention. They are not revenue, market size, willingness to pay,
> or proof of product demand. This system never turns them into a "buy" or "invest" call.

**Status:** built and fully tested.
- **Milestone 1:** one topic in one language, meaning explicit topic resolution, monthly
  pageviews, core KPIs, and a JSON result, a Markdown report and a trend chart.
- **Language comparison:** one topic across editions, with topic share, Wikipedia topic
  penetration, topic affinity and the demand × growth opportunity matrix.
- **Anomaly detection:** unusual months flagged against a seasonal, level-aware baseline, with
  causes always left as "unknown".
- **Topic ecosystem** (`cluster`): related concepts through typed Wikidata relations and text
  similarity, their demand and growth, descriptive signals, and interest concentration.
- **Decision signals:** five separate readings (market size, growth, momentum, localization,
  stability), each with its evidence and rule, and never combined into a score or verdict.
- **Later milestone:** the HTML report and portfolio mode (see [Roadmap](#roadmap)).

## 1. What it does

```text
topic + language → topic resolution → Wikimedia collection → raw archive → normalized records
                 → KPIs (demand, growth, seasonality, quality) → JSON + Markdown + chart
```

The layers are separate packages. `clients/` is the only place that does HTTP. `data/` holds the
raw archive, the cache and normalization. `analytics/` holds pure functions over normalized data.
`reporting/` reads only the result model. The analytics code never sees an API response.

## 2. What Wikimedia data represents

- **Pageviews** of one article, monthly, from the [Wikimedia Analytics API][aqs]
  (`/metrics/pageviews/per-article`). The defaults are `agent=user` (humans; known bots and
  spiders excluded) and `access=all-access` (all devices). Data starts in July 2015.
- **A language edition is not a country.** `de.wikipedia` is read in Germany, Austria,
  Switzerland and anywhere German is read.
- **Unique devices** are published only per project (a whole language edition), never per
  article, so the article-level `unique_devices` field is always `null`, with that reason.
- **Country data** (`top-by-country`) is published per project, not per article, so a topic's
  country distribution cannot be measured and is reported as *unsupported*.
- The per-article endpoint omits months with no recorded views, so a missing month can't be told
  apart from a zero. Missing months are reported as missing and never filled with zero.

## 3. Installation

Python 3.12 or newer.

```bash
cd wikipedia-market-intelligence
uv venv --python 3.13 && uv pip install -e ".[dev]"      # or: python -m venv .venv && pip install -e ".[dev]"
```

## 4. Configuration

Settings come from `WMI_*` environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `WMI_USER_AGENT` | `wiki-market-intel/0.1 (https://github.com/hsirenko/Wikimedia1)` | Wikimedia requires a User-Agent that identifies you; put your contact in it |
| `WMI_DATA_DIR` | `data` | raw responses (`data/raw`) and cache (`data/cache`) |
| `WMI_REPORTS_DIR` | `reports` | report output |
| `WMI_TIMEOUT` / `WMI_MAX_ATTEMPTS` | `30` / `4` | per-request timeout; attempts with exponential backoff |

## 5. CLI

```bash
wiki-market analyze --topic "meditation" --language de --period 3y
wiki-market analyze --topic meditation --language de --start 2023-09 --end 2026-08
wiki-market analyze --input examples/meditation-de.yaml
wiki-market compare --topic meditation --languages en,de,fr,es,it
wiki-market cluster --topic meditation --language de           # analyze + related topics
wiki-market topic --topic meditation --languages en,de,fr      # resolution only
wiki-market validate                                             # check every saved report
wiki-market cache clear
```

`python -m wiki_market_intel ...` works the same way.

**Dates.** A `YYYY-MM` end month is inclusive. A full date that falls on the 1st is exclusive:
`2026-01-01` means "up to December 2025", as in the spec's YAML example. The end is always capped
at the last complete month, so an incomplete month is never compared with a full one.

**Exit codes:**
- `0` OK
- `1` validation failed
- `2` bad input
- `3` the topic needs review (ambiguous; the candidates are printed)
- `4` topic or article not found
- `5` API error

## 6. Python API

```python
from wiki_market_intel import analyze

result = analyze(topic="meditation", language="de", period="3y")
result.summary          # 3-5 factual observations
result.demand.annual_views, result.growth.yoy, result.growth.three_year_cagr
result.seasonality.peak_month, result.quality.quality_level
result.quality.missing_metrics      # every null KPI, with its reason
result.model_dump_json()            # the machine-readable result
```

```python
from wiki_market_intel import compare_languages

comparison = compare_languages(topic="meditation", languages=["en", "de", "fr", "es", "it"])
for row in comparison.rows:          # LanguageOpportunityMetrics, one per edition
    row.language, row.annual_views, row.yoy_growth, row.topic_share, row.topic_penetration, row.topic_affinity
comparison.analyses["de"]            # the full single-language result for each edition
```

If the topic is ambiguous, `analyze` and `compare_languages` raise `AmbiguousTopicError`, and its `.resolution.candidates`
lists the plausible concepts. The system never picks one silently.

## Report language

The report follows the language of the user's request. Pass the request word for word with
`--question`, or `question=` in `analyze()`. That is separate from `--language`, which is the
Wikipedia edition being analysed:

```bash
wiki-market analyze --topic meditation --language de \
  --question "Як змінюється інтерес до медитації в німецькомовній Вікіпедії?"
```

- **Supported languages:** English and Ukrainian, via the catalogue in `src/wiki_market_intel/i18n.py`.
- **What is translated:** every heading, label, observation, explanation of a missing metric,
  quality reason and business-implication line, plus the chart. Numbers follow the language's
  conventions (`56 910`, `−17,2%`).
- **Overrides and fallback:** `--report-lang en|uk` forces a language. Any other detected
  language gets an English report, and the CLI prints a `REPORT_LANGUAGE` line so an agent
  tells the user and still replies in their language.
- **The JSON result is always in English:** it is the canonical record, so reports in any
  language validate and compare the same way.
- **Adding a language:** copy the `"en"` block in `CATALOG`, translate it and add the code to
  `SUPPORTED`. `tests/reporting/test_i18n.py` fails if any key or placeholder is missing.

## 7. KPI definitions

| KPI | Period | Notes |
|---|---|---|
| Annual views, monthly and daily average | last 12 complete months | |
| YoY | last 12M vs previous 12M | |
| 3Y CAGR | last 12M vs the 12M ending 36 months earlier | needs 48 months of history |
| 3-month growth | last 3M vs previous 3M | |
| Previous 3-month growth | previous 3M vs the 3M before | |
| Acceleration and momentum | difference of the two 3-month growths | accelerating above +5 pp, decelerating below −5 pp; a measurement, not a forecast |
| Period over period | requested period vs the previous equivalent period | |
| Peak / trough month | calendar month with the highest / lowest mean over the requested period | |
| Peak/average, trough/average | ratio of calendar-month means | |
| Volatility | coefficient of variation of monthly views | |
| Coverage | months with data / months in the requested period | |
| Wikipedia topic penetration | topic views / all views of the edition, last 12 months | same traffic class for both; shown per million; not market penetration |
| Topic share | an edition's topic views / topic views across the compared editions | relative to the compared set; editions without data are left out and named |
| Topic affinity | (topic views / edition views) / (compared topic views / compared edition views) | a location quotient; 1.0 is average for the compared set; this system's own measure, not an official Wikimedia metric |
| Anomaly | a month far from its expected value (see below) | cause always "unknown"; flags in the last 3 months are provisional |
| YoY excluding anomalies | YoY with flagged months replaced by their expected values | shows whether growth rests on one-off months (spec rule 6) |
| Quadrant | growth: YoY > 0%; demand: views ≥ median of the compared editions | labels are investigate, explore, established and watch; descriptive, never recommendations |

## Anomaly detection

For each month the system computes an **expected value**. It flags the month only when the actual
value is far from it, both statistically and in size.

1. **Seasonal factor:** how that calendar month usually compares with the surrounding level in
   *other* years. It's computed leave-one-out, so a spike can't raise its own baseline. January
   peaks that recur every year are therefore expected, not flagged.
2. **Level:** the median of the 6 months before *or* the 6 months after, whichever fits the month
   better. At a permanent change in level, each month matches its own side, so a step isn't
   reported as a spike plus a drop. A genuine spike stands out against both sides.
3. **Flag:** a robust z-score (median/MAD on the log gap) above 3.5 **and** a gap of at least 25%.
   The size gate stops tiny wobbles on very smooth series from counting as "extreme".
4. **Severity:** high at ≥ 100% gap or z > 7, medium at ≥ 50% or z > 5, otherwise low.
   - Flags in the **last 3 months are provisional**: no later months exist yet to anchor them.
   - **Causes are never inferred.**

Checked on real data, these three results come out right:
- German "Meditation": January peaks are not flagged; the November 2025 bump (+43%) is.
- Italian: a real 2024 drop to a lower level is not reported as a run of anomalies.
- English: June to August 2026 are flagged (+122%, +40% and +46%, all provisional). Replacing
  them shows YoY at −31.7% instead of the reported −20.8%, so the recent rise was masking a
  steeper decline.

## Topic ecosystem

`wiki-market cluster` (or `analyze_cluster()` in Python) runs the single-language analysis and
fills report section 8 with related concepts.

**Where related concepts come from.** Each concept records its relationship and its source:

| Relationship | Found through |
|---|---|
| broader | Wikidata P279 *subclass of* (the topic is a kind of it) |
| narrower | the reverse of P279 (kinds of the topic) |
| facet of / has facet | Wikidata P1269 *facet of*, both ways |
| similar text | Wikipedia's "more like this" search, labelled separately because it's not a stated relationship and can pull in popular unrelated articles |

Typed relations are listed before text similarity, duplicates are removed, and at most 20 are
measured. Concepts without an article in the edition are skipped, and the report says how many.

**Per related topic:** views in the last 12 months, YoY, 3Y CAGR, 3-month change, size relative
to the topic, and **share-adjusted YoY**, meaning growth relative to the whole edition, so
platform-wide decline doesn't make everything look like it's declining.

**Signals.** These are descriptive *adjacent interest signals*, never claims that an article is
a commercially adjacent product. The first matching rule wins:

1. **too small to judge:** under 100 views a month;
2. **larger category:** a broader concept with more views than the topic;
3. **emerging category:** share-adjusted YoY ≥ +10%;
4. **declining category:** share-adjusted YoY ≤ −10%;
5. **adjacent opportunity:** at least as many views as the topic;
6. **adjacent interest:** everything else.

**Concentration.** This is the share of views held by the top 1, 5, 10 and 20 articles of the
topic plus its typed relations (text-similar articles are excluded), and is null when there are
fewer than k articles. It's reported without a good/bad judgement.

On real data, German "Meditation" lost 17.2% year over year. Every typed relation lost more
relative to its edition, so the topic is holding up better than its neighbourhood. The cluster
is concentrated: Buddhism, a larger category, holds 62% of its views.

## Decision signals

Spec §22 asks for business-relevant signals without pretending that Wikipedia can make an
investment decision. So there are five **separate** labels. Each comes from one rule on KPIs
already in the report, and each carries a sentence with its evidence (`signals.evidence` in the
JSON; section 1 of the report, in the report language). They are never combined into a score,
and never turned into BUY / INVEST.

| Signal | Input | Rule |
|---|---|---|
| market size | views in the last 12 months | very low < 12,000 ≤ low < 60,000 ≤ medium < 300,000 ≤ high < 1.5M ≤ very high |
| growth | 3-year CAGR (YoY without 4 years of data) | declining < −3% ≤ stable < +3% ≤ growing < +15% ≤ strongly growing |
| momentum | 3M growth minus previous 3M growth | accelerating > +5 points, decelerating < −5, else stable |
| localization | affinity (only in `compare`) | weak < 0.80 ≤ moderate < 1.25 ≤ strong |
| stability | anomaly episodes, then seasonal peak | volatile: ≥ 2 episodes and ≥ 1 per 12 months checked; else peak ≥ 1.30× highly seasonal, ≥ 1.12× moderately seasonal, else stable |

- **Market size** is absolute on purpose (the spec says "based on absolute demand"), so the same
  topic reads higher in a larger edition.
- **Growth** uses raw pageviews. Its evidence adds the whole edition's YoY, because Wikipedia
  traffic falls in many editions.
- **An anomaly episode** is a run of consecutive flagged months. English "Meditation" has a spike
  in June 2026 and two flagged months after it. That is one event, not volatility.
- **A missing signal** is listed in the data-quality table with its reason. For example,
  localization is `unavailable` outside a comparison, and stability needs two years of each
  calendar month.
- **`validate`** recomputes every signal from the report's own monthly series.

On real data (2023-09 to 2026-08), the signals for "Meditation" read as follows:

| Edition | Market size | Growth | Momentum | Localization | Stability |
|---|---|---|---|---|---|
| en | high | declining | accelerating | moderate | moderately seasonal |
| de | low | declining | accelerating | strong | moderately seasonal |
| fr | low | declining | accelerating | moderate | highly seasonal |
| es | low | declining | decelerating | moderate | highly seasonal |
| it | low | declining | accelerating | moderate | highly seasonal |

## 8. Formulas

All formulas live in [`analytics/formulas.py`](src/wiki_market_intel/analytics/formulas.py).
Each has a docstring with its definition and edge cases, plus its own unit tests. The result JSON
includes the registry (`formulas`), so every report carries its own definitions. Any formula
whose inputs are missing, empty or zero returns `null`. It never returns `0`.

## 9. Data limitations and quality

Every report has a Data Quality section. The quality level follows fixed rules:

| Level | Rule |
|---|---|
| HIGH | coverage ≥ 98%, topic resolution confidence ≥ 0.90, ≥ 24 months, no API errors |
| MEDIUM | coverage ≥ 90%, confidence ≥ 0.70 |
| LOW | anything else |

Topic resolution confidence also follows fixed rules:

| Match | Confidence |
|---|---|
| Wikidata ID given | 1.00 |
| Exact title | 0.98 |
| Redirect | 0.90 |
| No Wikidata entity | 0.70 |
| Disambiguation page or search-only match | needs review, no choice made |

## 10. Example report

[`examples/meditation-de/report.md`](examples/meditation-de/report.md) is German Wikipedia's
"Meditation" article, 2023-09 to 2026-08:
- annual views 56,910;
- YoY −17.2%;
- 3Y CAGR −15.1%;
- peak in January;
- quality HIGH.

The KPIs were cross-checked against an independent calculation from the raw API response. A
test (`test_analysis_matches_an_independent_calculation`) keeps them checked.

## 11. Adding another data provider

Providers are future work (spec §35). The seam is already in place: analytics consume
`MonthlyPoint` series and `PageviewRecord`s, not API payloads. A Google Trends or App Store
provider would add a client under `clients/` and a normalizer producing the same records. The
KPI functions would not change.

## 12. Caching and raw data

- **Raw archive.** Every API response is written to `data/raw/<source>/<endpoint>/` as an
  envelope `{source, endpoint, retrieved_at, request, status, response}` before it is used, and
  is never deleted (spec §7). The result JSON lists the raw file for every number.
- **Cache.** Responses are cached in `data/cache/`, keyed by source, endpoint, language, article,
  start, end, metric and traffic class.
- **Expiry.** Complete historical months never change, so those entries never expire. Everything
  else expires after 24 hours.
- **Swappable backend.** The cache is a small `Cache` protocol, so the JSON-file backend can be
  replaced by SQLite, DuckDB, PostgreSQL or object storage without touching analytics.
- **Clearing.** `wiki-market cache clear` removes cached entries and keeps the raw archive.

## 13. Tests

```bash
pytest                    # 159 offline tests; the network is replaced by a fake Wikimedia
pytest -m integration     # 4 tests against the live API
```

The fixture `tests/fixtures/pageviews_meditation_de_2020-09_2026-08.json` is a real captured API
response. The tests cover:
- **Clients:** success, HTTP error, timeout, malformed body or schema, retry, 404 treated as "no
  data", the cache and the raw archive.
- **Resolution:** exact title, redirect, disambiguation, search-only match, missing language,
  not found, Wikidata ID, no Wikidata entity.
- **Formulas and KPIs,** including missing-month handling.
- **Periods and quality levels.**
- **Reporting:** section order, missing-metric rendering, incomplete data.
- **The CLI and its exit codes.**
- **Decision signals:** every band boundary, episodes versus volatility, missing signals with
  reasons, and both report languages.
- **`validate`,** including catching a tampered report.

## Roadmap

In the order the spec (§40) sets:

1. ~~**Language comparison and localization**~~ (done): `compare`, topic share, penetration from
   the project `aggregate` endpoint, affinity, and the opportunity matrix. Country distribution
   stays unsupported, because Wikimedia doesn't publish it per article.
2. ~~**Anomalies**~~ (done): seasonal, level-aware baseline; robust flags; causes stay "unknown".
3. ~~**Topic ecosystem and concentration**~~ (done): `cluster`.
4. ~~**Decision signals**~~ (done): market size, growth, momentum, localization, stability,
   each with its evidence. Kept separate, with no single score.
5. **HTML report and portfolio mode:** a matrix of many topics × languages (the opportunity matrix already exists per topic).

[aqs]: https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html
