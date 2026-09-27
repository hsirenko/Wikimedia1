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
- **Portfolio mode** (`portfolio`): many topics × many editions in one matrix and chart, with
  filters and the decision signals for every pair.
- **Recommendation first:** every report opens with evidence-based next steps (what to validate
  first, monitor or deprioritise), followed by a KPI-by-KPI breakdown.
- **User criteria:** `--min-audience`, `--pace-margin` and `--drop-margin` set what counts as
  worth validating. The rule used is printed under every recommendation.
- **Missing editions:** when an edition has no article on the concept, the report says so and lists
  search results from that edition as stand-in candidates for the user to confirm.
- **PDF on request:** `wiki-market pdf <report folder>` writes a one-page `brief.pdf`
  (recommendation, KPI breakdown, main chart); `--full` writes the whole report.
- **HTML reports:** every command also writes a self-contained `report.html`, with the charts
  embedded, in light and dark mode.

## Skill layout

This folder is the Agent Skill (the folder name matches `name:` in `SKILL.md`), and everything the
skill needs lives inside it:

```text
wiki-market-intel/
├── SKILL.md               instructions for the agent (loaded by Claude)
├── scripts/wiki_market.py launcher: puts src/ on the path, installs missing libraries at locked versions
├── scripts/build_zip.sh   builds ../wiki-market-intel-skill-<N>.zip, numbered so the latest is the highest
│                          (leaves out .venv, caches, data, reports, examples, evals)
├── src/wiki_market_intel/ the code: clients, data, analytics, reporting, CLI
├── tests/                 217 offline tests (fake Wikimedia) + 5 live tests
├── examples/              real reports (JSON, Markdown, HTML, one-page PDF) that `validate` checks
├── evals/                 agent scenarios, pass criteria and a reply checker
├── requirements.lock      every dependency pinned (uv pip compile)
└── pyproject.toml, README.md
```

There are no compiled binaries. Python sources only; dependencies come from PyPI at the pinned
versions.

The uploadable zip leaves out `examples/` and `evals/`. In testing, Haiku found a saved sample
report that matched the user's question and answered from it instead of running the analysis, so
the installed skill carries no saved results.

## 1. What it does

```text
topic + language → topic resolution → Wikimedia collection → raw archive → normalized records
                 → KPIs (demand, growth, seasonality, quality) → recommendation + KPI breakdown
                 → JSON + Markdown + HTML + charts (+ PDF on request)
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
cd wiki-market-intel
uv venv --python 3.13 && uv pip sync requirements.lock && uv pip install -e ".[dev]" --no-deps
# or, without uv: python -m venv .venv && pip install -r requirements.lock && pip install -e ".[dev]" --no-deps
```

`requirements.lock` pins every package (regenerate it with
`uv pip compile pyproject.toml --extra pdf -o requirements.lock`). When the skill runs inside an
agent, `scripts/wiki_market.py` installs only the libraries that are missing, at the locked
versions.

PDF output needs `reportlab` (`pip install -e ".[pdf]"`). The skill installs it the first time
`pdf` is used.

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
wiki-market portfolio --topics examples/wellness-topics.yaml --languages de,en,fr,es
wiki-market portfolio --topics meditation,yoga,sleep --languages de,fr --min-views 20000 --min-growth -10
wiki-market topic --topic meditation --languages en,de,fr      # resolution only
wiki-market pdf reports/meditation/de/2026-09-27                # one-page brief.pdf (--full: report.pdf)
wiki-market compare --topic "intermittent fasting" --languages pl,cs --period 2y --min-audience 1000
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

```python
from wiki_market_intel import portfolio

matrix = portfolio(topics=["meditation", {"topic": "sleep", "category": "sleep"}], languages=["de", "en", "fr"],
                   min_views=20_000)
for row in matrix.visible:           # PortfolioRow, one per (topic, edition), in input order
    row.topic, row.language, row.annual_views, row.yoy_growth, row.topic_affinity, row.quadrant, row.signals
matrix.rows                          # every row, including hidden ones (row.excluded_by says why)
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

## Portfolio mode

`wiki-market portfolio --topics topics.yaml --languages de,en,fr,es` (spec §36-§37). Either
argument can be a comma list or a YAML file. A topics file is a list, or `topics:` with items
that are a name or `{topic: name, category: label}`
(see [`examples/wellness-topics.yaml`](examples/wellness-topics.yaml)).

- **Per topic:** each topic runs through the normal comparison (or a single analysis for one
  edition). Its rows therefore carry the same KPIs, affinity and decision signals as a `compare`
  report, and the portfolio JSON embeds the full results.
- **Affinity is within each topic,** across the portfolio's editions. It changes when the set of
  editions changes.
- **Portfolio quadrant:** YoY > 0; demand at or above the median annual views of every measured
  pair. The median is taken *before* filters, so a filter never moves the split.
- **Filters:**
  - `--min-views N`: annual views;
  - `--min-growth P`: YoY in percent, e.g. `5` or `-10` (write `--min-growth=-10%` with a % sign);
  - `--category a,b`: categories from the topics file;
  - languages and period: `--languages`, `--period` / `--start` / `--end`.

  Hidden rows stay in `portfolio.json`, with `excluded_by` saying why, and the report lists them.
  Country filtering is not available: Wikimedia publishes no per-article country data.
- **Topics that fail to resolve:** a topic that is ambiguous, not found or fails at the API becomes
  rows with that status and reason. It never stops the rest of the portfolio.
- **No ranking:** rows keep the input order and are never sorted by a KPI. The chart colours each
  topic (fixed order, never cycled) and gives each edition its own marker shape, with a legend.
  The CLI prints a `READY ANSWER` grouped by quadrant.
- **Output:** `reports/portfolio/{name}/{date}/`, with `portfolio.json`, `report.md`,
  `report.html` and `charts/portfolio.png`. `validate` rechecks every embedded result and
  rebuilds the rows, the split and the filters.

[`examples/wellness-portfolio/`](examples/wellness-portfolio/report.md) holds five wellness
topics across four editions. On this data, all 19 pairs with a year-over-year figure declined.

## Recommendation and KPI breakdown

Every report (analysis, comparison, cluster, portfolio) starts with two sections:

1. **Recommendation:** evidence-based next steps from written rules. Each option (a topic in one
   edition) gets one tier, the first rule that matches:

   | Tier | Rule |
   |---|---|
   | deprioritise | under 12,000 views a year, or 25% or more behind its edition (share-adjusted YoY) |
   | validate first | at least 12,000 views a year, within 10% of its edition or ahead of it, and (with several options) demand at or above the set's median |
   | monitor | everything else |

   - **Order:** within a tier, options are ordered by audience size.
   - **Extra notes:** timing from the lead option's seasonal peak; a caution when recent momentum
     rests on a provisional anomaly; for `cluster`, related topics to explore (text-similar ones
     marked `*`) and typed relations falling faster than the edition.
   - **Never a verdict:** every recommendation ends with its basis. It is Wikipedia reader
     attention only, not a go/no-go or investment call, and should be confirmed with search
     volume, app-store demand and interviews.
   - **Validated:** the rule is printed under the recommendation, and `validate` rebuilds the tiers.
   - **User criteria:** the three numbers are defaults. `--min-audience`, `--pace-margin` and
     `--drop-margin` (on analyze, compare, cluster and portfolio) change them. They are stored with
     the recommendation, so `validate` uses the same ones.
   - **Editions without an article:** the recommendation says interest can't be measured there
     and lists what a search in that edition finds. These are candidates for the user to confirm,
     never automatic substitutes.
2. **KPI breakdown:** one entry per KPI, namely demand, growth (YoY against the edition, and the
   3-year CAGR), momentum, seasonality and stability, localization, anomalies and data quality.
   For one topic it's a table whose "Reading" column carries the decision signal and its
   evidence. For several options it's one line per KPI across all of them.

The detailed sections follow, renumbered from 3.

The CLI prints the same two blocks first (`RECOMMENDATION`, `KPI BREAKDOWN`), and ends with a
`PDF_OFFER` line. The skill tells the agent to answer in that order and to end every reply by
offering a PDF of the report.

## PDF reports

`wiki-market pdf <report folder | report.md | result JSON>` writes a **one-page** A4
`brief.pdf`: title, recommendation, KPI breakdown and the main chart (trend, opportunity matrix or
portfolio chart). The builder checks the page count and shrinks the chart, then trims the
recommendation's points, until everything fits on one page. `--full` writes the whole report as
`report.pdf`, with table headers repeated across pages.

- **Language:** both follow the report's language. The DejaVu fonts come with matplotlib
  (Cyrillic), and reportlab's built-in CID fonts cover Chinese, Japanese and Korean.
- **Footer:** reminds readers that pageviews measure attention.
- **Dependency:** reportlab is installed on first use only.

## HTML reports

Every report folder also has `report.html`: the Markdown report as one self-contained page. The
charts are embedded as data URIs, so the file can be emailed or opened offline. It has light and
dark themes and works at phone width (wide tables scroll inside their own box). A small built-in
converter covers the reports' Markdown subset, so the HTML adds no dependency.

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
pytest                    # 217 offline tests; the network is replaced by a fake Wikimedia
pytest -m integration     # 5 tests against the live API
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
- **Portfolio:** input order, per-topic failures, the median split, filters, one-language
  portfolios, the ready answer, both report languages, the chart and self-contained HTML.
- **HTML:** tables, alignment, escaping, inline marks and embedded images.
- **Recommendation:** every tier boundary, share adjustment, comparison, cluster and portfolio
  recommendations, no verdict wording in either language, the report order, and `validate`
  catching an edited recommendation.
- **PDF:** the Markdown subset, key/value tables, and the `pdf` command in both languages.
- **`validate`,** including catching a tampered report.

## How it was built and verified

The code was written with an AI coding agent (Claude Code). None of its output was taken on
trust. Each layer has its own check:

1. **Numbers against an independent calculation.** The first KPIs were recomputed by hand from a
   real captured API response (`tests/fixtures/pageviews_meditation_de_2020-09_2026-08.json`).
   A test (`test_analysis_matches_an_independent_calculation`) keeps doing it. Comparison,
   anomaly and ecosystem figures were also cross-checked against raw API calls.
2. **Tests without the network.** 217 offline tests run against a fake Wikimedia that routes
   requests like the real APIs. They cover every formula boundary, missing data, errors and
   retries, both report languages, the CLI and exit codes, and tampered reports. 5 more tests hit
   the live API.
3. **Self-checking reports.** Every saved report embeds its monthly data and formula registry.
   `validate` recomputes every KPI, signal and recommendation tier from it; `examples/` is validated
   the same way.
4. **Rendered output inspected.** Charts were checked for label collisions. HTML was checked in a
   browser (light, dark, phone width) and PDFs by rasterising their pages.
5. **The whole scenario on a cheap model.** Claude Haiku 4.5 ran through the unpacked skill zip on
   realistic prompts, including leading ones ("top 3", "should we launch?", "score 1–10") in
   English and Ukrainian. Each failure was fixed in code or in the output format, not only in
   the prompt, and then re-run. Examples:
   - ranking language → quote-ready answer blocks;
   - misreading "worse than its edition" → explicit better/worse wording;
   - a made-up "Don't launch yet" → a `DECISION REQUEST` opener;
   - skipping the PDF offer → a reply checklist at the end of the output;
   - falling back to browsing → a hard rule;
   - answering from a bundled sample report → no samples in the zip, plus "run fresh every time".

   The scenarios, pass criteria and a reply checker are in [`evals/`](evals/README.md).

## Developing it further

The skill answers the basic questions (one topic in one language, several languages, related
topics, a portfolio) from monthly per-article pageviews. The next iterations, in the order they
unlock the most:

1. **Topics as sets of articles, not one article.** Real interest in "intermittent fasting" is
   spread over redirects, sub-articles and neighbouring concepts. The next step is aggregating a
   topic over a Wikidata subtree or category plus its redirects, with the set stored and shown.
   `cluster` already finds the relations.
2. **Bulk data instead of per-article calls.** For thousands of articles, read the monthly
   pageview dumps (dumps.wikimedia.org) instead of the REST API. Store normalized series in
   Parquet or DuckDB, and update them incrementally each month. The `clients/` layer isolates this
   switch, and analytics and reporting stay unchanged.
3. **Daily data and forecasts with uncertainty.** Use daily granularity for event-driven topics,
   and seasonal decomposition with prediction intervals, labelled as forecasts. This keeps the
   rule that the tool never explains causes.
4. **More sources behind the same interface.** Search volume (Google Trends), app-store ranks and
   edition-level unique devices and countries (published per project, not per article) can plug
   in as further providers (see "Adding another data provider"). The recommendation can then
   require agreement between sources.
5. **Research projects, not single questions.** Saved projects (topics, languages, criteria),
   diffs between runs ("what changed since last month"), scheduled refreshes and alerts when a
   topic crosses a user's criteria.
6. **Evaluation in CI.** Run the `evals/` scenarios on every change with a cheap model (Haiku, or a
   free OpenRouter model). Score the replies with `evals/check_reply.py`: order, PDF offer, no
   verdicts, every number found in the report.
7. **Leaner agent interface.** A compact `--json` summary for agents with small context windows,
   and an MCP server wrapping the same commands.

## Roadmap (done)

In the order the spec (§40) sets:

1. ~~**Language comparison and localization**~~ (done): `compare`, topic share, penetration from
   the project `aggregate` endpoint, affinity, and the opportunity matrix. Country distribution
   stays unsupported, because Wikimedia doesn't publish it per article.
2. ~~**Anomalies**~~ (done): seasonal, level-aware baseline; robust flags; causes stay "unknown".
3. ~~**Topic ecosystem and concentration**~~ (done): `cluster`.
4. ~~**Decision signals**~~ (done): market size, growth, momentum, localization, stability,
   each with its evidence. Kept separate, with no single score.
5. ~~**HTML report and portfolio mode**~~ (done): `report.html` for every report; `portfolio`
   with the matrix, chart, filters and signals.
6. ~~**Recommendation, KPI breakdown and PDF**~~ (done): every report opens with evidence-based
   next steps and a KPI-by-KPI breakdown; `pdf` on request.
7. ~~**Task-brief compliance**~~ (done): self-contained skill folder, pinned dependencies, user
   criteria, one-page PDF, stand-in candidates for missing editions, and agent evals.

[aqs]: https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html
