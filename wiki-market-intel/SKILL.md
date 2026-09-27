---
name: wiki-market-intel
description: Measures reader interest in topics on Wikipedia in any language edition, from Wikimedia pageview data, for B2C teams choosing which topic, course or language market to validate next. Answers questions such as is interest in a topic growing in a language, how far can that growth be trusted, compare interest across language editions, which audiences to research next, and which related topics draw readers. Each report opens with an evidence-based recommendation (validate first, monitor, deprioritise) and a KPI breakdown (views, year-over-year growth against the whole edition, 3-year CAGR, momentum, seasonality, anomalies, data quality), with charts, HTML and a one-page PDF. Use it for any question about Wikipedia pageviews or interest by language, in any language the user writes in (for example Ukrainian). It measures attention and never gives go/no-go or invest verdicts.
license: MIT
compatibility: Python 3.10+ with outbound access to wikimedia.org, *.wikipedia.org and www.wikidata.org. Missing libraries are installed on first run at the versions pinned in requirements.lock.
metadata:
  version: "0.2.0"
---

# Wikipedia Market Intelligence

## Hard rules

1. **Always run this skill's script** for any number, fresh for every question. Never answer from
   saved reports or files you find in this folder, never collect pageviews by browsing, the
   Pageviews Analysis website or your own API calls, and never write analysis code. Reruns are
   cached and fast.
2. **If the script fails, stop.** Tell the user the error and the fix from the exit-code table
   below. Don't fall back to other sources.
3. **Reply in the user's language**, in this order: the recommendation, the KPI breakdown, the
   details asked for (with limits and report paths), and **last, always**: "Would you like a
   one-page PDF summary of this report? I can create it for you." This also applies when you show
   the report in a canvas or artifact: the message that goes with it still ends with that question.
4. **No verdicts, no rankings of your own, no causes.** Never say go/no-go, buy, invest or "best".
   The only priority order is the recommendation's (validate first, monitor, deprioritise): never
   add "highest / second priority" lists, and never turn a missing article into a priority. Never
   guess why views changed (the tool says "cause unknown", and so do you).
5. **Quote numbers as printed.** Don't recompute, round differently or estimate missing values.

## Pick the command

Run from any writable folder, and always pass the user's words unchanged in `--question` (it sets
the report language: Ukrainian or English; other languages get English):

| The user wants | Command |
|---|---|
| Is interest in one topic growing in one language, and can we trust it? *"Чи зростає інтерес до астрономії в україномовній Wikipedia?"* | `analyze --topic astronomy --language uk` |
| Compare a topic across language editions, or which audiences to research next. *"Порівняй інтервальне голодування в польсько- та чеськомовній Wikipedia за два роки"* | `compare --topic "intermittent fasting" --languages pl,cs --period 2y` |
| Related topics around a topic (what to add next to a course or app) | `cluster --topic meditation --language de` |
| Many topics × many languages at once | `portfolio --topics meditation,yoga,sleep --languages de,fr,es` |
| Just check which editions have an article | `topic --topic "..." --languages pl,cs,uk` |
| A one-page PDF of a report (after the user says yes) | `pdf <report folder>` (`--full` for every section) |

Every command is `python3 <skill-dir>/scripts/wiki_market.py <command> ... --question "<the user's words>"`.

- `--language` / `--languages`: Wikipedia edition codes (`uk`, `pl`, `cs`, `de`, `es`, `en`, ...).
  An edition is a language, **not a country**: say "uk.wikipedia readers", not "Ukraine".
- `--period`: `3y` (default), `2y`, `18m`, or `--start 2023-09 --end 2026-08`. For "over the last
  two years" use `--period 2y`: the year-over-year figure then compares those two years.
- The first run can take about 30 seconds while libraries install.

## Choosing the topic

- Use the **English name of the concept** (or a Wikidata ID such as `Q108458`). The tool finds
  each edition's own article for that concept, so every edition measures the same thing.
- For broad requests, pick the closest concept and say which one you used. For "learning English",
  use `"English as a second or foreign language"`, and mention `"English language"` as a
  broader alternative the user can ask for.
- **No article in an edition** is a finding, not zero interest. The recommendation says so and
  lists search results from that edition. Ask the user whether one is the same concept before
  using it as a stand-in (`--topic "<that title>" --language pl`).
- **Exit code 3 (ambiguous):** show the candidates and ask which one they mean. Never pick one.

**When nothing stands out** (the recommendation says so), say that plainly. For niche topics, offer
to rerun with a lower `--min-audience` (for example 1000), and let the user decide.

## The user's criteria

The recommendation follows a written rule (it is printed under it). Users can change it; pass what
they ask for on any command:
- `--min-audience 5000`: the minimum views a year worth validating (default 12,000);
- `--pace-margin 15`: how far behind the whole edition, in percent, still counts as keeping pace
  (default 10);
- `--drop-margin 30`: how far behind the whole edition means deprioritise (default 25).

## Follow-up questions

Rerun the command with the changed assumption: another period, more languages, other criteria or a
different concept. Responses are cached, so reruns are fast. Don't redo the maths yourself. To
compare with an earlier answer, read that report's `analysis.json` / `comparison.json`.

## Reading the output

The output starts with `RECOMMENDATION` and `KPI BREAKDOWN` (in the user's language when a
`REPORT_LANGUAGE` block is printed; use that one). It ends with `PDF_OFFER` (the folder for
`pdf`) and a `REPLY CHECKLIST`.

1. **Recommendation.** Give it first, as written: headline, points, "Basis". It says what to
   validate first, monitor or deprioritise. It is not a go/no-go. Put nothing of your own before
   it. If the user wants a short version, the headline *is* the short version. When a
   `DECISION REQUEST` line is printed ("should we launch", "top 3", "best"), start with the
   sentence it gives.
2. **KPI breakdown.** One item per KPI, as written: demand, growth (YoY against the whole edition,
   3-year CAGR), momentum, seasonality, localization, anomalies, data quality.
   - **Growth** means YoY first (last 12 months vs the 12 before), then the 3-year CAGR. The
     3-month figure is short-term momentum and can be swung by seasonality, so never present it
     alone as growth.
   - **"How far can we trust it?"**: answer with the data-quality level and its reasons, the
     anomaly flags (a spike can inflate growth; flags in the last 3 months are provisional; when
     the output gives the YoY with flagged months replaced, mention it), and the comparison with
     the whole edition (Wikipedia traffic falls in many editions).
   - **Market size** is reader attention in that edition, not money or users. The five signals
     (market size, growth, momentum, localization, stability) are separate readings. Never combine
     them into a score.
   - A KPI shown as `n/a` comes with a reason. Give the reason, never an estimate.
3. **Details** the user asked for, then the limits: pageviews measure attention, not revenue,
   willingness to pay or product-market fit. Then the report files: `report.html` (easiest to
   share), `report.md`, `analysis.json`, `charts/`.
4. **Last line:** the one-page PDF question, every time, including after a report shown in a
   canvas or artifact. If the user says yes, run `pdf <folder from PDF_OFFER>` and give them
   `brief.pdf` (on Claude.ai it is also copied to the downloads folder).

### compare

- Share, affinity and quadrants are relative to the editions compared: adding or removing one
  changes them. Say so.
- The `SIGNALS per edition` labels are the tool's. If every edition reads "market size low", say
  "low" for each. Don't re-rank them as highest, medium or lowest.

### cluster (related topics)

- `RELATED TOPICS BY SIGNAL` comes third in your reply. Give its sentences as written.
- Topics marked `*` were found by text similarity only: say so every time.
- "better / worse than its edition by X%" compares the topic with its whole edition. The edition's
  own YoY is in the `RELATED:` header.
- Don't rank related topics or use "best", "primary" or "winner". "adjacent opportunity" is only a
  signal name, and such a topic can still be falling. Ignore `too_small` topics.
- Concentration names the largest article. Describe it; don't judge it.

### portfolio

- Topics and languages take a comma list or a YAML file (`topics: [{topic: sleep, category: sleep}]`).
- Filters: `--min-views 20000`, `--min-growth 5` or `--min-growth -10` (percent),
  `--category sleep`. There is no country filter: Wikimedia has no per-article country data.
- Keep the recommendation's "validate first" order. Don't add your own top-N, don't re-sort, and
  don't add generalisations the rows don't state.
- `HIDDEN` rows were filtered out or couldn't be measured. Say which ones and why.

## Exit codes

| Code | Meaning | Your action |
|---|---|---|
| 0 | done | answer as above |
| 2 | bad input | fix the flags and rerun |
| 3 | ambiguous topic; candidates printed | ask the user which one; rerun with `--topic "<exact title or Q-ID>"` |
| 4 | topic not found, or no article in that language | say so; a missing article is itself a finding |
| 5 | API error or network blocked | tell the user the sandbox can't reach Wikimedia and to allow `wikimedia.org`, `*.wikipedia.org` and `www.wikidata.org` under Settings → Capabilities → Code execution. Don't use other sources |

## Checking a result

`validate <report folder or JSON>` recomputes every KPI, signal and recommendation tier from the
report's own stored monthly data. Run it when the user doubts a number or edits a report.

More detail (KPI definitions, formulas, quality rules, data limitations, how the skill was
verified and how to extend it): `README.md`.
