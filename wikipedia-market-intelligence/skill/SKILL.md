---
name: wiki-market-intel
description: KPI report on reader attention to a topic in one Wikipedia language edition, from Wikimedia pageview data. Covers annual views, year-over-year growth, 3-year CAGR, 3-month momentum, seasonality and data quality, as JSON, a Markdown report and a trend chart. Use when someone asks how much attention a topic gets in a language, whether it is growing or declining, when it peaks, or wants a structured, reproducible market-intelligence report for a topic and language. It measures attention and does not give buy or invest recommendations.
license: MIT
compatibility: Python 3.10+ and outbound access to wikimedia.org, *.wikipedia.org and www.wikidata.org. Libraries (httpx, pydantic, tenacity, python-dateutil, jinja2, matplotlib, pyyaml) are installed automatically on first run if missing.
metadata:
  version: "0.1.0"
  milestone: "1 - one topic, one language"
---

# Wikipedia Market Intelligence (wiki-market-intel)

Measures the **size, trajectory and seasonality of attention** to a topic in one Wikipedia
language edition, and states what the data cannot tell. All numbers come from the tool. **Never
compute KPIs yourself, and never write your own analysis code.**

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
`./wiki_market_reports/<topic>/<language>/<date>/`, containing `analysis.json`, `report.md` and
`charts/trend.png`. If `/mnt/user-data/outputs` exists, the report is also copied there so the
user can download it. Tell the user where the files are.

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
- **Lead with the measured facts** from the printed summary: annual views, YoY, 3-year CAGR,
  3-month momentum, peak and trough months, data-quality level.
- **Quote numbers exactly as printed.** Growth figures are relative changes in %, not percentage
  points. The momentum label (accelerating / stable / decelerating) compares two 3-month growth
  rates. It is a historical measurement, not a forecast.
- **When a KPI is `n/a`, give its reason** from the report (for example, unique devices and
  country data are published by Wikimedia only for whole editions, not per article). Never
  replace it with an estimate.
- **Precise language:** "Pageviews decreased 17.2% year over year", not "demand collapsed".
  "de.wikipedia readers", not "Germany".
- **Wikipedia pageviews measure attention.** They do not show revenue, market size, willingness to
  pay or product-market fit, and they do not explain causes. Say this when the user is making a
  business decision. Point to section 11 of the report for what needs validating (search volume,
  app stores, interviews, conversion).

## Checking a report

`python3 <skill-dir>/scripts/wiki_market.py validate <path/to/analysis.json>` recomputes every
KPI from the report's own stored monthly data and confirms that the stored numbers match.

## Current scope (milestone 1)

This version covers one topic in one language. Language comparison, localization (penetration,
affinity), anomalies, the topic ecosystem and decision signals are not built yet. The report shows
those sections with "not implemented" and the reason. If the user asks for them, say they are
planned, and offer to run the single-language analysis for each language separately.

More detail: `references/README.md` (KPI definitions, formulas, quality rules, data limitations).
