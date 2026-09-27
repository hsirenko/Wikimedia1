---
name: wiki-market-intel
description: Reports on reader attention to topics across Wikipedia language editions, from Wikimedia pageview data. Each report opens with an evidence-based recommendation (what to validate first, monitor or deprioritise), then a KPI breakdown of views, year-over-year growth, 3-year CAGR, momentum, seasonality, localization, anomalies, data quality and five decision signals. It compares editions (share, affinity, demand-by-growth matrix), measures related topics, and builds portfolio matrices of many topics and editions. Output is JSON, Markdown, HTML and charts, plus a PDF on request. Use when someone asks how much attention a topic gets in a language, whether it is growing, which language markets or product categories to validate first, which related topics draw readers, or wants a reproducible market-intelligence report. It measures attention and never gives go/no-go, buy or invest verdicts.
license: MIT
compatibility: Python 3.10+ and outbound access to wikimedia.org, *.wikipedia.org and www.wikidata.org. Libraries (httpx, pydantic, tenacity, python-dateutil, jinja2, matplotlib, pyyaml) are installed automatically on first run if missing.
metadata:
  version: "0.1.0"
  milestone: "6 - recommendation, KPI breakdown, PDF"
---

# Wikipedia Market Intelligence (wiki-market-intel)

Measures the **size, trajectory and seasonality of attention** to a topic in one Wikipedia
language edition, and states what the data cannot tell. All numbers come from the tool. **Never
compute KPIs yourself, and never write your own analysis code.**

**Every reply, in this order:** (1) the tool's recommendation, (2) the KPI breakdown, (3) the
details asked for, the limits and the report paths, (4) **the last line is always the question
"Would you like this report as a PDF? I can create it for you."**, in the user's language. The
tool's output ends with this same checklist.

## Run it

The scripts live in this skill's directory. Run them from any writable folder:

```bash
python3 <skill-dir>/scripts/wiki_market.py analyze --topic "meditation" --language de --period 3y \
  --question "<the user's request, copied word for word>"
```

**Always pass `--question` with the user's request exactly as written, not translated.** The
report is written in the language of that text: Ukrainian and English are available, and other
languages get an English report.

- `--language`: a Wikipedia edition code (`de` German, `fr` French, `uk` Ukrainian, `pl` Polish,
  `es` Spanish, `en` English, ...). It is a language edition, **not a country**.
- `--period`: `3y` (default), `2y`, `18m`. Alternatively use `--start 2023-09 --end 2026-08`.
- `--topic`: the English article title or the plain concept name. A Wikidata ID (`Q108458`) also
  works.

The first run may take about 30 seconds while missing libraries install. Output goes to
`./wiki_market_reports/<topic>/<language>/<date>/`, containing `analysis.json`, `report.md`,
`report.html` (the same report as one self-contained page, charts included: the easiest file to
share) and `charts/trend.png`. If `/mnt/user-data/outputs` exists, the report is also copied there so the
user can download it. Tell the user where the files are.

**Several language editions at once** (which markets, where is the topic relatively strongest):

```bash
python3 <skill-dir>/scripts/wiki_market.py compare --topic "meditation" --languages en,de,fr,es,it \
  --question "<the user's request, copied word for word>"
```

The topic is matched once, so every edition measures the same concept. The printed table has, per
edition:
- views in the last 12 months, and YoY;
- **share**: the edition's part of the topic's views across the compared editions;
- **penetration per million**: topic views per million views of that edition;
- **affinity**: 1.0 is average for the compared set; 1.6 means the topic takes 1.6× the usual share
  of attention;
- the **quadrant** of the opportunity matrix.

Share, affinity and quadrants are relative to the editions compared: adding or removing one
changes them. Say so. "no article" is a finding (the concept has no article in that edition),
not zero interest. Output goes to `./wiki_market_reports/<topic>/compare-<langs>/<date>/`.

**Related topics around one topic** (larger categories, emerging neighbours, how concentrated
interest is):

```bash
python3 <skill-dir>/scripts/wiki_market.py cluster --topic "meditation" --language de \
  --question "<the user's request, copied word for word>"
```

It prints the usual analysis plus a `RELATED` table.

- **Each row** gives the related article, its relationship, its views, its size relative to the
  topic, its YoY and its YoY relative to the whole edition, plus a signal.
- **Relationship values:** `broader`, `narrower`, `facet_of` and `has_facet` come from Wikidata.
  `similar_content` is text similarity only, which can include unrelated popular articles. When
  you mention one of those, say it was found by similarity.
- **Signals** (larger category, emerging, declining, adjacent opportunity, adjacent interest,
  too small) are *adjacent interest signals*: where readers' attention sits.
  - **Don't rank them.** Group topics by signal and describe them. Don't use the words
    "best", "most promising", "primary", "secondary", "top opportunity", "winner" or "inflection
    point". Even "adjacent opportunity" is only a signal name: "at least as many readers as
    the topic, changing within 10 points of its edition". It can still be falling.
  - Don't draw conclusions from `too_small` topics.
- **"better / worse than its edition by X%"** is the topic's growth compared with its whole
  edition. The edition's own YoY is printed once, in the `RELATED:` header. Don't confuse the two.
- **Topics marked `*` were found by text similarity only.** Say so whenever you mention one.
- **`RELATED TOPICS BY SIGNAL` is part 3 of your reply**, after the recommendation and the KPI
  breakdown. Give its sentences as written (translated if needed), including "found by text
  similarity only" and the group names. Don't add headings such as "Best", "Primary",
  "Secondary", "Resilient" or "Most viable". The `DETAIL TABLE` below it is for reference only.
- **Concentration** (top 1 / top 5 share) is neither good nor bad: describe it, don't judge it.
  The `RELATED:` header names the largest article. It's often a broader concept, not the topic
  itself.

**Many topics across many editions** (a portfolio: which categories and markets draw attention):

```bash
python3 <skill-dir>/scripts/wiki_market.py portfolio --topics meditation,yoga,sleep --languages de,fr,es \
  --question "<the user's request, copied word for word>"
```

- `--topics` and `--languages` take a comma list or a YAML file. Topics can carry a category:
  `topics: [{topic: sleep, category: sleep}, ...]`.
- Filters: `--min-views 20000`, `--min-growth 5` or `--min-growth -10` (percent; with a % sign
  write `--min-growth=-10%`), `--category sleep,mindfulness`. There is no country filter:
  Wikimedia publishes no per-article country data.
- It prints the `RECOMMENDATION` and `KPI BREAKDOWN` first, then a `DETAIL TABLE` (one row per
  topic and edition, in the order given) and the `QUADRANTS`. Answer in the reply order below.
- The recommendation's "validate first" order is the tool's written rule. Keep it as printed.
  Don't add your own "top N", "best" or "winner" list, don't re-sort the rows, and don't add
  generalisations the rows don't state (such as "German markets are stronger").
- When the output prints `DECISION REQUEST` (the user asked for a "top 3", the "best" topic or what
  to build), start your reply with the sentence it gives, then continue with the recommendation.
- `HIDDEN` rows were removed by a filter or couldn't be measured (ambiguous topic, no article).
  Say which ones and why. An ambiguous topic needs an exact title or Wikidata ID; ask the user.
- Affinity in a portfolio is measured within each topic, across the listed editions.
- Output goes to `./wiki_market_reports/portfolio/<name>/<date>/` (`--name wellness`).

Only resolving a topic, without fetching views:
`python3 <skill-dir>/scripts/wiki_market.py topic --topic meditation --languages en,de,fr`

## Exit codes: what to do

| Code | Meaning | Your action |
|---|---|---|
| 0 | done | answer from the printed summary and `report.md` |
| 3 | topic is ambiguous; candidates printed | show the candidates to the user and ask which one they mean. **Never pick one yourself.** Rerun with `--topic <exact title or Q-ID>` |
| 4 | topic not found, or no article in that language | say so. A missing article in a language is itself a finding |
| 5 | API error or network blocked | if it says connection refused or not allowed, the sandbox cannot reach Wikimedia. Tell the user to allow `wikimedia.org`, `*.wikipedia.org` and `www.wikidata.org` under Settings → Capabilities → Code execution (network egress) |

## How to answer

- **Write your whole answer in the language the user wrote in.** A Ukrainian question gets a
  Ukrainian answer, an English question an English one, and so on.
  - When the output prints `REPORT_LANGUAGE uk`, the report and chart are in Ukrainian, and the
    output repeats the observations in Ukrainian. Quote those lines.
  - When it prints `REPORT_LANGUAGE en ... has no report translation yet`, reply in the user's
    language and tell them the report file is in English.
- **Structure every reply in this order:**
  1. **Recommendation.** Give the `RECOMMENDATION` block first, as written (translated if needed):
     the headline, its points and the "Basis" sentence. It is evidence-based next steps (what to
     validate first, what to monitor or deprioritise), not a go/no-go or investment call.
     **Nothing of your own goes before it**, no "short answer", no "don't launch", no "go". When
     the user asks for a short version, the recommendation's headline *is* the short version. When
     the output prints `DECISION REQUEST` ("should we launch?", "top 3", "best"), start with the
     sentence it gives, then the recommendation.
  2. **KPI breakdown.** Give the `KPI BREAKDOWN` block next, one item per KPI, as written: demand,
     growth (YoY and 3-year CAGR), momentum, seasonality, localization, anomalies, data quality.
  3. **Details the user asked about** (related topics, signals per edition, hidden rows), then
     the limits and where the report files are (`report.html` is the easiest to share).
  4. **Last line of every reply, always: offer a PDF.** End with "Would you like this report as a
     PDF? I can create it for you." (in the user's language). Don't skip it, even in a short
     reply. If they say yes, run `python3 <skill-dir>/scripts/wiki_market.py pdf <folder>`, using
     the folder on the `PDF_OFFER` line, and give them the path of `report.pdf`.
  When the output has a `REPORT_LANGUAGE` block, use the recommendation and KPI breakdown
  printed there, which are already in the user's language.
- **"Growing?" means year over year first.** Answer questions about growth with the YoY change
  (last 12 months vs the 12 before) and, when present, the 3-year CAGR. The 3-month figure is
  short-term momentum and can be swung by seasonality. Mention it only after YoY, and never present
  it alone as growth. If every edition declined year over year, say so plainly, even when some
  recent 3-month figures are positive.
- **Anomalies (`ANOMALY ...` lines, section 10 of the report):** say the month, the views, the
  expected views and the gap, as printed. **Never suggest a cause**, not even a likely one: the
  tool reports "cause unknown", and so do you. Call flags in the last 3 months provisional.
  When the summary says the year-over-year change would differ with the flagged months replaced,
  mention it. It shows whether a trend rests on a one-off spike (for example, a 3-month rise
  driven by one unusual month).
- **Quote numbers exactly as printed.** Growth figures are relative changes in %, not percentage
  points. The momentum label (accelerating / stable / decelerating) compares two 3-month growth
  rates. It is a historical measurement, not a forecast.
- **When a KPI is `n/a`, give its reason** from the report (for example, unique devices and
  country data are published by Wikimedia only for whole editions, not per article). Never
  replace it with an estimate.
- **Decision signals** (in the KPI breakdown; section 2 of the report): five separate readings:
  market size, growth, momentum, localization and stability. Each comes with its evidence and rule.
  - Give each one with its evidence, as printed, for example: "growth: declining (3-year CAGR
    -15.1%; de.wikipedia as a whole changed -7.3%)".
  - **Never combine them** into a score or grade. The only recommendation is the tool's
    `RECOMMENDATION` block. Never turn it into "buy", "invest", "go" or "no-go", even when the
    user asks "should we launch?".
  - Market size is absolute reader attention in that edition, not market size in money or users.
    Larger editions read higher for the same topic.
  - In `compare`, the `SIGNALS per edition` lines carry each edition's labels. Use them as
    written: if every edition reads "market size low", say "low" for each.
    Don't re-rank them as highest, medium or lowest, and don't add an "assessment", a "most
    favourable" market or a go/no-go line per market.
  - Localization only exists in `compare`. In a single-edition analysis it is `n/a`; give that
    reason.
- **Quadrant names are descriptive, not advice.** Investigate, explore, established and watch
  describe growth vs demand; never turn them into "buy", "best market" or "winner".
- **Precise language:** "Pageviews decreased 17.2% year over year", not "demand collapsed".
  "de.wikipedia readers", not "Germany".
- **Wikipedia pageviews measure attention.** They do not show revenue, market size, willingness to
  pay or product-market fit, and they do not explain causes. Say this when the user is making a
  business decision. Point to section 11 of the report for what needs validating (search volume,
  app stores, interviews, conversion).

## Checking a report

`python3 <skill-dir>/scripts/wiki_market.py validate <analysis.json, comparison.json or portfolio.json>` recomputes every
KPI from the report's own stored monthly data and confirms that the stored numbers match.

## Current scope

Everything in the spec's roadmap is built:
- single-language analysis and language comparison (share, penetration, affinity, opportunity matrix);
- anomaly detection and the topic ecosystem (`cluster`);
- decision signals;
- portfolio mode;
- HTML reports.

Country breakdowns and unique devices are not published per article by Wikimedia, so they are
always n/a. Never estimate them.

More detail: `references/README.md` (KPI definitions, formulas, quality rules, data limitations).
