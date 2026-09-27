# Wikipedia Market Intelligence

Turn Wikimedia pageviews into a short report that tells a product team **which topic or language
edition is worth validating next** — and which is not, on this evidence.

It answers questions such as: is interest in astronomy growing on Ukrainian Wikipedia, and can we
trust that? How does intermittent fasting compare in Polish and Czech? Which related topics sit
around meditation in German? Which wellness ideas to research across several languages?

Pageviews measure **reader attention**, not revenue, market size, willingness to pay or
product-market fit. A language edition is not a country (`uk.wikipedia` is read wherever Ukrainian
is read). The tool never says buy, invest, go or no-go. It recommends only what to **validate
first**, **monitor**, or **deprioritise**, and asks you to confirm with search volume, app stores
and interviews.

## What you run

Install once (Python 3.12+):

```bash
cd wiki-market-intel
uv venv --python 3.13 && uv pip sync requirements.lock && uv pip install -e ".[dev]" --no-deps
# or: python -m venv .venv && pip install -r requirements.lock && pip install -e ".[dev]" --no-deps
```

Always pass the user's own words as `--question`. That sets the report language (English or
Ukrainian; anything else falls back to English). `--language` is the Wikipedia *edition*, not the
report language.

| You want | Command |
|---|---|
| One topic in one edition | `wiki-market analyze --topic astronomy --language uk --question "…"` |
| The same topic across editions | `wiki-market compare --topic "intermittent fasting" --languages pl,cs --period 2y --question "…"` |
| Related topics around one article | `wiki-market cluster --topic meditation --language de --question "…"` |
| Many topics × many editions | `wiki-market portfolio --topics meditation,yoga,sleep --languages de,fr,es --question "…"` |
| Does this edition even have an article? | `wiki-market topic --topic "…" --languages pl,cs,uk` |
| A one-page PDF, after they ask | `wiki-market pdf <report folder>` (`--full` writes every section) |

`python -m wiki_market_intel …` and `python3 scripts/wiki_market.py …` do the same thing. The
script installs any missing libraries at the versions in `requirements.lock`.

Useful flags: `--period 3y` (default), `2y`, `18m`, or `--start 2023-09 --end 2026-08`.
`--min-audience`, `--pace-margin` and `--drop-margin` change what “worth validating” means; the
rule used is printed under the recommendation. `--report-lang en|uk` overrides language detection.

Exit codes: `0` ok, `2` bad input, `3` ambiguous topic (candidates are printed — never picked for
you), `4` not found, `5` API error, `1` `validate` failed.

## What you get

Each run writes a folder with `report.md`, `report.html` (charts embedded; works offline),
`analysis.json` / `comparison.json` / `portfolio.json`, and `charts/`. Every report has the same
four sections:

1. **Recommendation** — validate first / monitor / deprioritise, then the basis (attention, not
   demand) and the rule used.
2. **Graph** — trend, opportunity matrix, related-topic chart, or portfolio chart.
3. **Key observations** — a few factual sentences from the KPIs. Not repeated later.
4. **KPI breakdown** — demand, year-over-year vs the whole edition, 3-year CAGR, momentum,
   seasonality, localization, anomalies, data quality. Each signal stays separate; they are never
   scored into one number.

Default rule: **deprioritise** under 12,000 views a year or 25%+ behind the edition;
**validate first** at least 12,000 views and within 10% of the edition (or ahead); **monitor**
everything else. An edition with no article is reported as a gap, with search hits for you to
confirm — never as a substitute article.

`wiki-market pdf <folder>` writes a one-page `brief.pdf`. `wiki-market validate` recomputes every
KPI, signal and recommendation from a saved JSON so a report cannot silently drift.

Settings (`WMI_USER_AGENT`, `WMI_DATA_DIR`, `WMI_REPORTS_DIR`) are in `.env.example`. Wikimedia
requires a User-Agent that identifies you.

Sample output: [`examples/meditation-de/report.md`](examples/meditation-de/report.md).

## How to read the numbers

- **Growth** is last 12 months vs the 12 before, then the 3-year CAGR. The last-3-month figure is
  momentum only; seasonality can swing it.
- **Share / affinity / quadrants** are relative to the editions you compared. Add or drop one
  language and they change. Affinity is this tool's location quotient, not a Wikimedia metric.
- **Anomalies** are months far from a seasonal baseline. Causes stay “unknown”. Flags in the last
  three months are provisional.
- **Missing months** are missing, never filled with zero. Unique devices and country mix are
  *unsupported* at article level: Wikimedia does not publish them that way.
- **JSON is always English.** It is the canonical record. Markdown, HTML, charts and PDF follow
  `--question`.

Python, if you need it:

```python
from wiki_market_intel import analyze, compare_languages, portfolio

r = analyze(topic="meditation", language="de", period="3y", question="…")
r.recommendation, r.demand.annual_views, r.growth.yoy, r.quality.quality_level
```

Ambiguous topics raise `AmbiguousTopicError` with `.resolution.candidates`.

## For the next developer

This folder *is* the Agent Skill (`name:` in `SKILL.md` matches the directory). Agents read
`SKILL.md` and run `scripts/wiki_market.py`. Do not add a second analysis path or a second
launcher.

```text
SKILL.md                     what the agent is allowed to do
scripts/wiki_market.py       puts src/ on PYTHONPATH; installs missing locked deps
src/wiki_market_intel/
  clients/                   the only HTTP (Wikimedia, Wikipedia, Wikidata)
  data/                      raw archive, cache, normalization → MonthlyPoint records
  analytics/                 pure functions: KPIs, signals, recommend, formulas.py
  reporting/                 Markdown / HTML / charts / PDF from the result model
  i18n.py                    every user-facing string (en, uk)
  cli.py                     analyze, compare, cluster, portfolio, topic, pdf, validate
tests/                       fake Wikimedia; no network unless pytest -m integration
evals/                       cheap-model scenarios + check_reply.py
requirements.lock            pin with: uv pip compile pyproject.toml --extra pdf -o …
```

**Layering.** Analytics never see an API payload. Reporting never fetches. A new source (Trends,
app stores, dumps) is a client + a normalizer that emits the same records; KPI functions stay
put. The cache is a small `Cache` protocol (JSON files today). Complete historical months do not
expire; `wiki-market cache clear` keeps the raw archive.

**Invariants when you change it.** One command still answers one question. Stdout stays short;
detail goes to the report files. Recommendation first, no verdicts, no combined score. `--question`
still sets language. Every null KPI still carries a reason. Tests are written from cases where
the naive answer is wrong — add one of those for each new metric. After you change `SKILL.md` or
CLI stdout, re-run `evals/` on a cheap model; Python tests will not catch an agent that ranks
editions or skips the PDF offer.

**Where to look.** Formulas and edge cases: `analytics/formulas.py` (the JSON embeds this
registry). Recommendation tiers: `analytics/recommend.py`. Report shape: `reporting/markdown.py`
(same four sections for every command). New report language: copy the `"en"` block in `i18n.py`
and keep every `{placeholder}`; `tests/reporting/test_i18n.py` fails if a key is missing.

**Natural next work** (do not break the layers above): treat a topic as a *set* of articles
(`cluster` already finds relations; summing them is the missing step); screening via the `top`
endpoint; SQLite/DuckDB keyed by `(project, article, month)` then [pageview
dumps](https://dumps.wikimedia.org/other/pageviews/) once you have hundreds of series; keep the
agent digest to top/bottom N. Do not invent causes, collapse the five signals, or treat
pageviews as a go/no-go.

```bash
pytest                    # offline
pytest -m integration     # live Wikimedia
```

[Wikimedia pageviews API](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html)
