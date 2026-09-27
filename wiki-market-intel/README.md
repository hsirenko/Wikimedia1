# Wikipedia Market Intelligence

This repository is an [Agent Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview). It measures reader attention to a topic on Wikipedia language editions, using public Wikimedia pageview data, and writes a short decision memo: what to validate first, monitor, or deprioritise.

Use it when you are choosing a topic, course, or language market and want evidence from how much people *read* about that topic — not a forecast of revenue.

Pageviews are not demand. A language edition is not a country. The Skill never issues a go / no-go, buy, or invest call.

---

## What this Skill can do


| Question                                                                                    | Command     |
| ------------------------------------------------------------------------------------------- | ----------- |
| Is interest in this topic growing in one language, and can we trust the signal?             | `analyze`   |
| How does the same topic compare across language editions? Which audiences to research next? | `compare`   |
| What related topics sit around this one?                                                    | `cluster`   |
| How do several topics look across several editions at once?                                 | `portfolio` |
| Does this edition even have an article for the concept?                                     | `topic`     |
| A one-page PDF of a report you already ran (only after you ask)                             | `pdf`       |


For each run you get the same four-part report (`report.md`, self-contained `report.html`, JSON, charts):

1. Recommendation (validate first / monitor / deprioritise), the rule used, and the limit that this is attention, not demand
2. Graph
3. Key observations
4. KPI breakdown — views, year-over-year versus the whole edition, 3-year CAGR, momentum, seasonality, localization, anomalies, data quality

Signals stay separate. They are never combined into a score.

The Skill also:

- Resolves a topic to the same Wikidata concept in each edition, so you compare one idea, not mixed search hits
- Reports a missing article as a gap, with search candidates for you to confirm — it never substitutes another article
- Flags unusual months against a seasonal baseline (causes stay “unknown”)
- Writes reports in English or Ukrainian from `--question` (other languages fall back to English; JSON stays English)
- Lets you change what “worth validating” means (`--min-audience`, `--pace-margin`, `--drop-margin`)

No Wikimedia API key is required. You need outbound HTTPS to `wikimedia.org`, `*.wikipedia.org`, and `www.wikidata.org`, and a User-Agent that identifies you (`WMI_USER_AGENT` in `.env.example`).

## What this Skill cannot do

- Size a market, forecast revenue, or measure willingness to pay
- Tell you whether to launch, invest, or localise
- Map readers to a country (`de.wikipedia` is read wherever German is read). Per-article unique devices and country mix are not published by Wikimedia and are reported as unsupported
- Explain *why* views moved
- Rank editions as “best” or invent a single priority score
- Fill a month that has no data with zero
- Work in a sandbox with no network (including the Claude API Skills container, which has no outbound internet). Use claude.ai with code execution and network allowed, Claude Code, Cursor, or this repo on your machine

Confirm any recommendation with search volume, app-store demand, and customer interviews before you spend.

---

## What to do with this repository

This git repo is the source. The Skill Claude loads is the `wiki-market-intel/` folder inside it (`SKILL.md` at that folder’s root). You can:

1. **Run it on your machine** — clone, install, call the CLI
2. **Upload it to [claude.ai](https://claude.ai)** — zip that folder and add it as a custom Skill
3. **Use it in Claude Code or Cursor** — copy or symlink the folder into the product’s skills directory

Do not zip the whole Wikimedia1 repo. Claude expects one Skill directory named `wiki-market-intel` that contains `SKILL.md`.

### Requirements

- Python 3.12 or later
- Network access to Wikimedia (see above)
- For claude.ai: a [Pro, Max, Team, or Enterprise](https://support.claude.com/en/articles/12512180-use-skills-in-claude) plan with [code execution](https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude) enabled. Custom Skills uploaded there are private to your account.



### Clone and install locally

```bash
git clone https://github.com/hsirenko/Wikimedia1.git
cd Wikimedia1/wiki-market-intel

uv venv --python 3.13 && uv pip sync requirements.lock && uv pip install -e ".[dev]" --no-deps
# or: python3 -m venv .venv && .venv/bin/pip install -r requirements.lock && .venv/bin/pip install -e ".[dev]" --no-deps
```

`scripts/wiki_market.py` installs any missing locked dependencies the first time an agent runs it.

### Upload to claude.ai as a custom Skill

1. From `wiki-market-intel/`, build the zip (numbered so an older build is never overwritten):
  ```bash
   sh scripts/build_zip.sh
  ```
   This writes `wiki-market-intel-skill-<N>.zip` one level up. The archive root is `wiki-market-intel/SKILL.md`, which is the [required layout](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills). `examples/`, `evals/`, caches, and generated reports are left out on purpose: a model that finds a saved sample will answer from the file instead of running the analysis.
2. In Claude, open **Customize → Skills** (on some accounts this is **Settings → Features → Skills**). See [Use skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude).
3. Click **+**, then **Upload a skill**, and choose the zip.
4. Toggle **wiki-market-intel** on.
5. Start a new chat. Ask a product question in your own words, for example: *Is interest in astronomy growing on Ukrainian Wikipedia?*

If Claude’s code-execution sandbox cannot reach Wikimedia, it will fail rather than invent numbers. Allow those domains, or run the same command locally and paste the report.

### Claude Code

```bash
mkdir -p ~/.claude/skills
cp -R wiki-market-intel ~/.claude/skills/wiki-market-intel
```

For one repository only, use `.claude/skills/wiki-market-intel` inside that repo. Restart the session, then ask the same kind of question.

### Cursor

```bash
mkdir -p ~/.cursor/skills
cp -R wiki-market-intel ~/.cursor/skills/wiki-market-intel
```

Or keep a project link at `.cursor/skills/wiki-market-intel` → this folder. Open a new chat and name the Skill if an older Wikipedia skill is also present.

Skills do not sync across products. Upload or copy separately for claude.ai, Claude Code, and Cursor. The Claude API Skills environment has **no network**, so this Skill cannot fetch pageviews there.

---



## How to use it

Pass the user’s words unchanged as `--question`. That sets report language. `--language` / `--languages` are Wikipedia edition codes (`uk`, `pl`, `de`, …), not countries.

```bash
wiki-market analyze --topic astronomy --language uk \
  --question "Is interest in astronomy growing on Ukrainian Wikipedia?"

wiki-market compare --topic "intermittent fasting" --languages pl,cs --period 2y \
  --question "Compare intermittent fasting in Polish and Czech Wikipedia over two years"

wiki-market cluster --topic meditation --language de --question "…"
wiki-market portfolio --topics meditation,yoga,sleep --languages de,fr,es --question "…"
wiki-market pdf reports/astronomy/uk/2026-09-27
```

`python -m wiki_market_intel …` is equivalent. `--period` defaults to `3y`; use `2y`, `18m`, or `--start` / `--end`. A `YYYY-MM` end month is inclusive; the window is capped at the last complete month.

**Exit codes:** `0` ok · `2` bad input · `3` ambiguous topic (candidates printed; nothing is chosen for you) · `4` not found · `5` API error · `1` `validate` failed.

Each run writes a dated folder with Markdown, HTML, JSON, and charts. `wiki-market validate` recomputes KPIs, signals, and the recommendation from that JSON.

Default recommendation rule (printed under every memo; override with flags):


| Tier           | When                                                                                                                                          |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Deprioritise   | Under 12,000 views a year, or 25% or more behind the edition                                                                                  |
| Validate first | At least 12,000 views a year and within 10% of the edition (or ahead). With several options, demand must also be at or above the set’s median |
| Monitor        | Everything else                                                                                                                               |




### How to read the numbers

- **Growth** is the last 12 months versus the 12 before, then the 3-year CAGR. The last three months are momentum only.
- **Share, affinity, and quadrants** are relative to the editions in *this* comparison. Change the set and they change. Affinity is this Skill’s location quotient, not a Wikimedia metric.
- **Anomalies** are months far from a seasonal baseline. The last three months are provisional.
- **Missing months** stay missing.
- **JSON is always English.** Markdown, HTML, charts, and PDF follow `--question`.

Example report: `[examples/meditation-de/report.md](examples/meditation-de/report.md)`.

```python
from wiki_market_intel import analyze

result = analyze(topic="meditation", language="de", period="3y", question="…")
result.recommendation, result.demand.annual_views, result.growth.yoy
```

Ambiguous topics raise `AmbiguousTopicError` with `.resolution.candidates`.

---



## For the next developer

This directory *is* the Skill. The folder name matches `name:` in `SKILL.md`. Agents read that file and run `scripts/wiki_market.py`. Do not add a second analysis path or a second launcher.

```text
SKILL.md                     instructions Claude loads when the Skill triggers
scripts/wiki_market.py       PYTHONPATH + locked dependency install
scripts/build_zip.sh         claude.ai upload artifact (no examples/, evals/, data)
src/wiki_market_intel/
  clients/                   only HTTP (Wikimedia, Wikipedia, Wikidata)
  data/                      raw archive, cache, normalize → MonthlyPoint
  analytics/                 pure KPIs, signals, recommend, formulas.py
  reporting/                 Markdown / HTML / charts / PDF from the result model
  i18n.py                    user-facing strings (en, uk)
  cli.py                     analyze, compare, cluster, portfolio, topic, pdf, validate
tests/                       fake Wikimedia; pytest -m integration hits the live API
evals/                       cheap-model scenarios + check_reply.py
```

**Layering.** Analytics never see an API payload. Reporting never fetches. A new source is a client plus a normalizer that emits the same records; KPI functions stay as they are. The cache is a `Cache` protocol (JSON files today). Complete historical months do not expire.

**Invariants.** One command answers one question. Stdout stays short; files hold detail. Recommendation first; no verdicts; no combined score. `--question` sets language. Every null KPI has a reason. Add a test from a case where the naive answer is wrong. After you change `SKILL.md` or CLI stdout, re-run `evals/` on a cheap model — unit tests will not catch an agent that ranks editions or skips the PDF offer.

**Where to change what.** Formulas: `analytics/formulas.py` (embedded in the JSON). Tiers: `analytics/recommend.py`. Report shape: `reporting/markdown.py` (four sections, every command). New language: copy the `"en"` block in `i18n.py` and keep every `{placeholder}`; `tests/reporting/test_i18n.py` fails if a key is missing.

**Extensions that fit the architecture:** treat a topic as a set of articles (`cluster` already finds relations); screening via the `top` endpoint; SQLite/DuckDB on `(project, article, month)`, then [pageview dumps](https://dumps.wikimedia.org/other/pageviews/) at hundreds of series. Do not invent causes, collapse the five signals, or treat pageviews as a launch decision.

```bash
pytest
pytest -m integration
```

[Wikimedia Pageviews API](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html)