---
name: wiki-market-intel
description: KPI reports on reader attention to a topic across Wikipedia language editions, from Wikimedia pageview data. For one edition it covers annual views, year-over-year growth, 3-year CAGR, 3-month momentum, seasonality, anomalies, penetration, data quality and five separate decision signals (market size, growth, momentum, localization, stability). Across editions it adds share, affinity and a demand-by-growth matrix; around a topic it measures related topics and concentration. Output is JSON, a Markdown report and charts. Use when someone asks how much attention a topic gets in a language, whether it is growing, which language markets show the most interest, which related topics draw readers, or wants a reproducible market-intelligence report. It measures attention and does not give buy or invest recommendations.
license: MIT
compatibility: Python 3.10+ and outbound access to wikimedia.org, *.wikipedia.org and www.wikidata.org. Libraries (httpx, pydantic, tenacity, python-dateutil, jinja2, matplotlib, pyyaml) are installed automatically on first run if missing.
metadata:
  version: "0.1.0"
  milestone: "4 - decision signals"
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
- **Your reply is the `READY ANSWER` block**, which comes right after the `RELATED:` header.
  Give it to the user as written (translated into the user's language if needed), then add the
  report path and the limits. Keep every sentence, including "found by text similarity only",
  and the group names as they are. Don't add headings such as "Best", "Primary", "Secondary",
  "Resilient" or "Most viable", and don't pick a winner, even when the user asks for "the best".
  The first sentence of the block already answers that question. The `DETAIL TABLE` below it
  is for reference only.
- **Concentration** (top 1 / top 5 share) is neither good nor bad: describe it, don't judge it.
  The `RELATED:` header names the largest article. It's often a broader concept, not the topic
  itself.

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
- **"Growing?" means year over year first.** Answer questions about growth with the YoY change
  (last 12 months vs the 12 before) and, when present, the 3-year CAGR. The 3-month figure is
  short-term momentum and can be swung by seasonality. Mention it only after YoY, and never present
  it alone as growth. If every edition declined year over year, say so plainly, even when some
  recent 3-month figures are positive.
- **Anomalies (`ANOMALY ...` lines, section 9 of the report):** say the month, the views, the
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
- **Decision signals (`SIGNALS` lines; the table in section 1 of the report):** five separate
  readings: market size, growth, momentum, localization and stability. Each comes with its
  evidence and rule.
  - Give each one with its evidence, as printed, for example: "growth: declining (3-year CAGR
    -15.1%; de.wikipedia as a whole changed -7.3%)".
  - **Never combine them** into an overall score, grade, verdict or recommendation. Never say
    "buy", "invest", "go" or "no-go", even when the user asks "should we launch?". Answer with the
    five readings and what they can't show.
  - Market size is absolute reader attention in that edition, not market size in money or users.
    Larger editions read higher for the same topic.
  - In `compare`, give the `READY ANSWER on signals` block as written (translated if needed).
    Its labels are the tool's: if every edition reads "market size low", say "low" for each.
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

`python3 <skill-dir>/scripts/wiki_market.py validate <path/to/analysis.json>` recomputes every
KPI from the report's own stored monthly data and confirms that the stored numbers match.

## Current scope

Single-language analysis, language comparison (share, penetration, affinity, opportunity matrix),
anomaly detection, the topic ecosystem (`cluster`) and decision signals are built. Country breakdowns
and unique devices are not published per article by Wikimedia, so they are always n/a. Never estimate
them.

More detail: `references/README.md` (KPI definitions, formulas, quality rules, data limitations).
