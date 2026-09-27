# Wikipedia Market Intelligence

A tool for measuring reader interest in topics across Wikipedia language editions using public Wikimedia pageview data.

## Overview

Wikipedia Market Intelligence (WMI) helps product teams validate topic selection and language prioritization by analyzing reading patterns across Wikimedia. It measures **reader attention, not demand**—use it alongside search volume, app-store analytics, and customer research before making investment decisions.

### What this tool does


| Question                                                        | Command     |
| --------------------------------------------------------------- | ----------- |
| Is interest in this topic growing, and can we trust the signal? | `analyze`   |
| How does this topic compare across language editions?           | `compare`   |
| What related topics are nearby?                                 | `cluster`   |
| What does a portfolio of topics look like across editions?      | `portfolio` |
| Does this edition have an article for this concept?             | `topic`     |
| Export a previous report to PDF                                 | `pdf`       |




### What this tool does NOT do

- Size a market or forecast revenue
- Measure willingness to pay or demand
- Map readers to specific countries (de.wikipedia is read globally)
- Provide per-article geographic breakdowns (not published by Wikimedia)
- Explain *why* pageviews changed
- Rank editions or create combined priority scores
- Work in offline/sandboxed environments

---



## Quick Start



### Requirements

- **CPython 3.13** (pinned in `.python-version`; `requires-python = ">=3.13,<3.14"`)
- **Network access** to Wikimedia domains
- **Claude plan**: Pro, Max, Team, or Enterprise with code execution enabled (for claude.ai usage)



### Installation

#### Download the skill zip

The current release is **v0.3.1** (CPython 3.13, hashed lockfiles). The file Claude.ai can upload is that **GitHub Release** asset, not a zip of this repository.

1. Download **[wiki-market-intel-skill.zip](https://github.com/hsirenko/Wikimedia1/releases/latest/download/wiki-market-intel-skill.zip)** (always the latest) or the pinned [v0.3.1 zip](https://github.com/hsirenko/Wikimedia1/releases/download/v0.3.1/wiki-market-intel-skill.zip)
2. In Claude.ai, open **Customize → Skills** (or **Settings → Features → Skills**)
3. Click **+** → **Upload a skill** and select that zip
4. Toggle **wiki-market-intel** on and start a new chat

Do **not** use GitHub’s **Code → Download ZIP**. That archive is the whole repo. Claude needs a zip whose top folder is `wiki-market-intel/` with `SKILL.md` at its root.

To rebuild the same package locally (contributors):

```bash
cd wiki-market-intel
sh scripts/build_zip.sh
```

To publish a new downloadable zip, tag a release (see [Releasing a skill zip](#releasing-a-skill-zip)).

#### Clone and run locally

```bash
git clone https://github.com/hsirenko/Wikimedia1.git
cd Wikimedia1/wiki-market-intel

# Using uv (recommended) — installs the hashed lock, including pytest
uv venv --python 3.13 && uv pip sync requirements-dev.lock && uv pip install -e . --no-deps

# OR using standard venv
python3.13 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-dev.lock
.venv/bin/pip install -e . --no-deps
```



#### Claude Code or Cursor

**Claude Code:**

```bash
mkdir -p ~/.claude/skills
cp -R wiki-market-intel ~/.claude/skills/wiki-market-intel
# Restart the session
```

**Cursor:**

```bash
mkdir -p ~/.cursor/skills
cp -R wiki-market-intel ~/.cursor/skills/wiki-market-intel
# Or create a symlink: ln -s /path/to/wiki-market-intel ~/.cursor/skills/
```

> **Note:** Skills do not sync across products. Upload separately for claude.ai, Claude Code, and Cursor.

---



## Usage



### Basic syntax

```bash
wiki-market <command> --topic <topic> --language <code> \
  --question "<your question>"
```

All commands output a dated folder with:

- `report.md` — Markdown report
- `report.html` — Self-contained HTML (ready to share)
- `report.json` — Structured data
- `charts/` — Chart images



### Commands



#### `analyze`

Examine a single topic in a single language edition over time.

```bash
wiki-market analyze --topic astronomy --language uk \
  --question "Is interest in astronomy growing on Ukrainian Wikipedia?"
```

**Options:**

- `--period` — Time window: `2y`, `18m`, or `3y` (default: `3y`)
- `--start`, `--end` — Custom date range (format: `YYYY-MM`, inclusive)



#### `compare`

Compare the same topic across multiple language editions.

```bash
wiki-market compare --topic "intermittent fasting" --languages pl,cs \
  --period 2y \
  --question "Compare intermittent fasting in Polish and Czech"
```



#### `cluster`

Find related topics around a central concept.

```bash
wiki-market cluster --topic meditation --language de \
  --question "What meditation-related topics matter on German Wikipedia?"
```



#### `portfolio`

Analyze multiple topics across multiple editions at once.

```bash
wiki-market portfolio --topics meditation,yoga,sleep --languages de,fr,es \
  --question "Which wellness topics should we validate in German, French, and Spanish?"
```



#### `topic`

Check whether a specific concept has an article in an edition.

```bash
wiki-market topic --topic "quantum computing" --language ja
```

Returns either the article URL or a list of search candidates if ambiguous or missing.

#### `pdf`

Export a previously generated report to PDF.

```bash
wiki-market pdf reports/astronomy/uk/2026-09-27
```



#### `validate`

`analyze`, `compare`, `cluster` and `portfolio` already run this check after writing the JSON
and **before** printing the digest. A mismatch is exit code 1 and the numbers are not shown.
Use the command later to re-check a saved report (or after someone edits the JSON):

```bash
wiki-market validate reports/astronomy/uk/2026-09-27
```

---



## Understanding the output



### Recommendation tiers

Every report leads with a recommendation based on attention signals:


| Tier               | Condition                                                          | Meaning                                                       |
| ------------------ | ------------------------------------------------------------------ | ------------------------------------------------------------- |
| **Validate first** | ≥12k annual views AND within 10% of edition performance (or ahead) | Strong signal; prioritize validation with additional research |
| **Monitor**        | Falls between deprioritize and validate-first                      | Watch the trend; revisit after next period                    |
| **Deprioritise**   | <12k annual views OR 25%+ below edition                            | Weak signal; lower priority unless other signals are strong   |


> Tip: With multiple options, validate-first topics must also be at or above the median demand across your set.



### Key metrics

- **Annual views** — Total pageviews in the last 12 months
- **Year-over-year growth** — Last 12 months vs. prior 12 months, expressed as percentage
- **3-year CAGR** — Compound annual growth rate over three years
- **Momentum** — Trend in the last three months only (provisional)
- **Share** — Percentage of total edition views (context-dependent)
- **Affinity** — Location quotient relative to other editions in the comparison
- **Seasonality** — Recurring patterns in the data
- **Anomalies** — Months that deviate from seasonal baseline (unknown causes)

> **Important:** Growth rates and affinity are relative to the editions you're comparing. Changing your comparison set changes these values.



### Report sections

1. **Recommendation** — Decision guidance and the rule applied
2. **Graph** — Visual trend over the analysis period
3. **Key observations** — Highlights and anomalies
4. **KPI breakdown** — Detailed metrics (views, growth, affinity, seasonality, data quality)

---



## Customization

Override default recommendation thresholds with flags:

```bash
wiki-market analyze --topic meditation --language de \
  --min-audience 20000 \        # Higher minimum view threshold
  --pace-margin 15 \            # Allow 15% variance (default: 10%)
  --drop-margin 35 \            # Allow 35% decline (default: 25%)
  --question "Custom thresholds for German meditation"
```

---



## Configuration



### Environment variables

Create a `.env` file in the project root:

```bash
# User-Agent for Wikimedia API requests (required for network access)
WMI_USER_AGENT="YourName/YourProject (your.email@example.com)"

# Optional: Cache directory for faster re-runs
WMI_CACHE_DIR="./cache"
```



### Language codes

Use Wikipedia edition codes, not country codes:


| Language  | Code |
| --------- | ---- |
| English   | `en` |
| German    | `de` |
| Ukrainian | `uk` |
| Polish    | `pl` |
| Czech     | `cs` |
| French    | `fr` |
| Spanish   | `es` |
| Japanese  | `ja` |


[Full list of Wikipedia editions](https://en.wikipedia.org/wiki/List_of_Wikipedias)

---



## Output languages

Reports follow the language of your `--question`:

- **English** — Default; if question language is unrecognized
- **Ukrainian** — If question is in Ukrainian
- **Other languages** — Fall back to English

JSON output is always English.

---



## Examples



### Example 1: Single-topic growth analysis

```bash
wiki-market analyze --topic "artificial intelligence" --language en \
  --period 3y \
  --question "How has interest in AI grown on English Wikipedia over three years?"
```

**Output:** Long-term trend, seasonal patterns, anomalies, and recommendation.

### Example 2: Cross-language comparison

```bash
wiki-market compare --topic "climate change" --languages en,de,fr,es \
  --question "How does climate change reading vary across major European languages?"
```

**Output:** Relative performance, affinity scores, and language-specific insights.

### Example 3: Portfolio screening

```bash
wiki-market portfolio \
  --topics "sustainable energy,renewable energy,solar power,wind power" \
  --languages en,de,uk,es \
  --question "Which clean energy topics should we validate in each market?"
```

**Output:** Side-by-side comparison of multiple topics and editions, highlighting which combinations meet validation thresholds.

---



## Python API

Use WMI as a Python library:

```python
from wiki_market_intel import analyze

result = analyze(
    topic="meditation",
    language="de",
    period="3y",
    question="Is meditation growing on German Wikipedia?"
)

# Access results
print(result.recommendation)           # "validate_first", "monitor", or "deprioritise"
print(result.demand.annual_views)      # Integer
print(result.growth.yoy)               # Float: percentage growth
print(result.growth.cagr_3y)           # Float: 3-year CAGR
```



### Handling ambiguous topics

```python
from wiki_market_intel import analyze, AmbiguousTopicError

try:
    result = analyze(topic="python", language="en")
except AmbiguousTopicError as e:
    print("Candidates:", e.resolution.candidates)
    # Candidates: ["Python (programming language)", "Python (snake)", ...]
```

---



## Troubleshooting



### "Network error: Cannot reach Wikimedia"

**Cause:** Firewall or sandbox restrictions.

**Solution:**

- Run locally instead of in a sandboxed environment
- Ensure outbound HTTPS access to:
  - `wikimedia.org`
  - `*.wikipedia.org`
  - `www.wikidata.org`
- Check your `WMI_USER_AGENT` environment variable is set



### "Topic not found" or "Ambiguous topic"

**Cause:** Article doesn't exist or title is imprecise.

**Solution:**

```bash
# Use the topic command to search candidates
wiki-market topic --topic "your term" --language en
```

Then use the exact article title from the candidates list.

### "Missing or incomplete data for this period"

**Cause:** Data gaps in the Wikimedia archive (rare).

**Solution:**

- Adjust your `--period` to avoid the gap
- Check `data_quality` in the JSON report
- Run `validate` to see which months are affected

---



## Architecture

The skill is the `wiki-market-intel/` folder. `SKILL.md` is the agent contract (which command to run, reply order, no invented numbers). `scripts/wiki_market.py` is the launcher: it requires CPython 3.13, puts `src/` on `sys.path`, installs the hashed `requirements.lock` (or upgrades any mismatch), writes `data/` and `reports/` into the current working directory (never into the skill folder), and copies new reports to `/mnt/user-data/outputs` when that path exists (claude.ai). All application code is `src/wiki_market_intel/`.

`service.py` is the only orchestrator. It holds no formulas. The pipeline for one article is:

```text
resolve → collect → normalize → KPIs → quality → recommend → result
```

```text
question / CLI / Python API
  → build_services()
       HttpClient + RawStore + JsonFileCache (or NullCache)
       WikimediaClient
       TopicResolver(WikipediaClient, WikidataClient)
  → resolve     TopicResolver: query or Q-id → one Wikidata concept → sitelink per edition
                disambiguation / no match → needs_review / not_found (never a silent pick)
  → collect     Wikimedia per-article pageviews + project aggregate (same window)
  → persist     every HTTP response under data/raw/; cache under data/cache/
  → normalize   API items → MonthlyPoint[] (missing months stay None)
  → KPIs        demand, growth, seasonality, anomalies, localization, signals
  → quality     completeness, API errors, missing metrics
  → recommend   validate_first | monitor | deprioritise (printed rule + user's Criteria)
  → result      AnalysisResult | ComparisonResult | PortfolioResult
                JSON is always English; formulas.REGISTRY is embedded
  → report      report.md + report.html + charts/  (pdf is a separate command)
  → validate    recompute every KPI from the written JSON; only then print the digest
```

Commands compose that pipeline; they do not fetch or score on their own.


| Command     | What it runs                                                                                                                            |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `analyze`   | resolve once → `_analyze_article` for one edition                                                                                       |
| `cluster`   | `analyze`, then related concepts (Wikidata P279 / P1269 and reverse, plus `morelike` text similarity), measure each, attach `Ecosystem` |
| `compare`   | resolve once → `_analyze_article` per requested edition → share, affinity, quadrants. Missing sitelink → `no_article` row, not zeros    |
| `portfolio` | `compare` (or `analyze` if one language) per topic; a failed topic becomes status rows and does not stop the rest                       |
| `topic`     | resolve only, no pageviews                                                                                                              |
| `pdf`       | one-page PDF from a saved report folder (`--full` for every section)                                                                    |
| `validate`  | schema + recompute from `monthly[]` in the saved JSON                                                                                   |
| `cache`     | inspect / clear `data/cache/`                                                                                                           |


On disk, `reporting/generator.py` writes:

```text
reports/{topic}/{language}/{date}/           analyze
reports/{topic}/cluster-{language}/{date}/   cluster
reports/{topic}/compare-{lang}-{lang}/…      compare
reports/portfolio/{name}/{date}/             portfolio
  analysis.json | comparison.json | portfolio.json
  report.md   report.html   charts/*.png
```

Every Markdown report has the same four sections: **1. Recommendation**, **2. Graph**, **3. Key Observations**, **4. KPI Breakdown**. Cluster adds its ecosystem chart and related-topic table under Graph / KPI. The CLI digest prints those sections; the agent reply follows the same order and ends by offering a PDF.

```text
src/wiki_market_intel/
  service.py              pipeline wiring only
  cli.py                  the eight commands above
  config.py               WMI_* (User-Agent, data_dir, reports_dir, timeouts)
  i18n.py                 every user-facing string (en, uk)
  errors.py               AmbiguousTopicError, TopicNotFoundError, ArticleMissingError, ApiError
  validate.py             schema + KPI recompute
  resolution/
    topic_resolver.py     documented confidence rules; never chooses a disambiguation
  clients/
    http.py               the only HTTP: User-Agent, retries, archive, cache
    wikimedia.py          pageviews per-article and project aggregate
    wikidata.py           Wikidata + Wikipedia Action API (titles, sitelinks, search, morelike)
  data/
    raw_store.py          immutable envelopes under data/raw/<source>/<endpoint>/
    cache.py              Cache protocol; JsonFileCache (complete months never expire)
    normalizer.py         raw items → MonthlyPoint; edition_totals
  models/
    topic.py              TopicResolution, ArticleRef
    metrics.py            demand, growth, seasonality, anomalies, signals, Criteria
    analysis.py           AnalysisResult, ComparisonResult, PortfolioResult
  analytics/              pure functions over MonthlyPoint (no HTTP)
    periods.py            last-complete-month windows (3y, 2y, 18m, or start/end)
    demand.py growth.py seasonality.py anomalies.py localization.py quality.py
    signals.py            five separate labels + evidence sentences
    recommend.py          validate_first / monitor / deprioritise
    ecosystem.py          cluster concentration and related-topic KPIs
    portfolio.py          matrix rows, filters, quadrants
    summary.py            key-observation sentences
    formulas.py           named registry written into every JSON
  reporting/              reads the result model only
    generator.py          dated folders listed above
    markdown.py comparison.py portfolio.py
    breakdown.py charts.py html.py pdf.py
```

**Invariants**

- One command answers one question. Stdout is a digest; files hold the report.
- Analytics never see an API payload. Reporting never fetches.
- HTTP exists only in `clients/http.py`. A new source is a client plus a normalizer that emits `MonthlyPoint`; KPI functions do not change.
- Missing months stay `None`. Unique devices and country mix are not published at article level.
- Signals are never combined into a score. Causes of anomalies are never inferred.
- `--question` selects report language (en / uk; others fall back to English). JSON stays English so `validate` is language-independent.

---



## Reproducible environment

The same CPython minor and the same package versions must come out of a fresh clone:

| Pin | File |
|---|---|
| CPython 3.13 | `.python-version`, `requires-python` in `pyproject.toml` |
| Direct dependencies | exact `==` versions in `pyproject.toml` |
| Every transitive + SHA256 | `requirements.lock` (runtime + PDF) and `requirements-dev.lock` (+ pytest) |

The skill launcher (`scripts/wiki_market.py`) refuses anything other than 3.13 and runs
`pip install --require-hashes -r requirements.lock` unless **every** locked distribution is
already at the locked version. It will not keep a pre-installed older `httpx`.

Refresh the locks after changing `pyproject.toml`:

```bash
sh scripts/lock.sh
```

Commit both lockfiles. CI (`test.yml`) installs with `--require-hashes` on 3.13 and runs pytest.

---

## Development



### Running tests

```bash
# Unit tests
pytest

# Integration tests (hits live Wikimedia API)
pytest -m integration
```



### Adding a new language

1. Open `src/wiki_market_intel/i18n.py`
2. Copy the `"en"` block and create a new block for your language code
3. Translate all strings (keep `{placeholders}` unchanged)
4. Run `pytest tests/reporting/test_i18n.py` to validate all keys are present



### Extending the tool

**New data source:** Create a new client in `clients/` and a normalizer that emits `MonthlyPoint` records. KPI functions remain unchanged.

**New recommendation logic:** Edit `analytics/recommend.py` and update `analytics/formulas.py` for new KPIs.

**Report shape changes:** Modify `reporting/markdown.py` (maintains the four-section structure) and re-run evals with a cheap model.

---



## Best practices



### Before you invest

1. **Validate first** tier? Check:
  - Search volume (Google Trends, Keyword Planner)
  - App store demand (iOS App Store, Google Play)
  - Customer interviews
2. **Monitor** tier? Revisit after one quarter
3. **Deprioritise** tier? Confirm decision with other teams before rejecting



### Interpreting anomalies

Anomalies flag months far from seasonal baseline. This tool identifies *that* a spike or drop happened, not *why*. Always pair with qualitative research.

### Cross-language comparison tips

- Wikipedia editions are not countries (de.wikipedia is read globally)
- Smaller editions may have higher volatility
- Affinity is relative to your comparison set—add or remove editions and affinity scores shift

---



## Contributing

We welcome issues and pull requests. Before starting:

1. Read the **Architecture** section above
2. Write tests for new behavior
3. Update this README if you change flags or commands
4. Run `pytest` and `pytest -m integration` locally
5. If you modify SKILL.md or CLI stdout, re-run evals on a cheap model



### Releasing a skill zip

Do not commit zips. Publish one named `wiki-market-intel-skill.zip` on a GitHub Release so the latest-download URL stays stable.

From a **clean** commit that contains the skill (this branch, not an old default-branch snapshot):

```bash
sh wiki-market-intel/scripts/release.sh 0.3.1
```

That tags `v0.3.1`, pushes the tag, and attaches the zip. Pushing any `v*` tag also runs `.github/workflows/release-skill-zip.yml`, which rebuilds the same asset.

Users then download:

`https://github.com/hsirenko/Wikimedia1/releases/latest/download/wiki-market-intel-skill.zip`

---
