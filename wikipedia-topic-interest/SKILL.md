---
name: wikipedia-topic-interest
description: Measures how public interest in a topic changes across Wikipedia language editions, using Wikimedia pageview statistics. Answers which topics to build next and which languages to localise into. Compares topics and language editions, separates real topic trends from Wikipedia's platform-wide traffic decline, scores how much each signal can be trusted, and writes a one-page PDF with charts. Use when asked whether interest in a subject is growing or declining, to compare demand for a topic between countries or languages, to prioritise courses, content, markets or translations, to size an audience for a B2C app idea, or for any question about Wikipedia pageviews or article popularity over time.
license: MIT
compatibility: Requires Python 3.9+ and internet access to wikimedia.org and wikipedia.org. Fetching and analysis use only the Python standard library; charts and PDF output additionally need matplotlib and reportlab (see requirements.txt).
metadata:
  version: "1.5"
  data-source: Wikimedia Analytics Pageviews API (no API key required)
---

# Wikipedia Topic Interest

Turn Wikipedia pageview statistics into a defensible answer to "what should we build
next, and for whom?"

## Setup (once per machine)

Charts and PDFs need two libraries. Everything else runs on plain Python.

```bash
cd <skill directory>
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Use `.venv/bin/python` in the commands below if you created the venv. If installing
is not possible, add `--no-pdf` and you still get the full analysis as text, JSON
and CSV using only the standard library.

## The one command you need

```bash
python3 scripts/wikitrends.py analyze --topic "<topic>" --langs uk,pl,cs --months 24
```

This resolves the topic to the right article title in each language, fetches monthly
pageviews, runs the statistics, writes `wikitrends-out/*.{json,csv,png,pdf}` and
prints a short digest. One call is enough for a complete answer — do not chain
separate fetch and analyse steps.

Useful flags:

| Flag | Use it when |
|---|---|
| `--topic "X"` (repeat) | comparing several topics; combine with one `--langs` |
| `--langs uk,pl,cs` | language edition codes, comma separated |
| `--months 36` | longer history. Use **at least 24** so year-over-year works |
| `--articles "uk:Астрономія,pl:Astronomia"` | you already know exact titles (skips resolution, faster) |
| `--since 2022-01 --until 2023-12` | a fixed window instead of "last N months" |
| `--weights momentum=2` | the user states criteria ("growth matters twice as much as size"). Keys: `reach`, `intensity`, `momentum`, default 1 each. Prints a `PRIORITY` line |
| `--normalise` | charts in views per million edition views — required for fair cross-language charts |
| `--question "..."` | prints the user's question on the PDF |
| `--summary "..."` | your one- or two-sentence bottom line, shown as "Analyst note" in the PDF's decision box. Claim-checked like `--finding` |
| `--finding "..."` | one bullet for the PDF. Pass the flag again for each extra bullet: `--finding "A" --finding "B"`. Supplying any replaces the auto findings |
| `--no-pdf` | skip charts/PDF (no third-party libraries, faster) |
| `--brief` | shortest stdout |
| `--json` | full JSON to stdout instead of the digest |

Language codes are the Wikipedia edition prefixes, not country codes:
`en` English, `de` German, `fr` French, `es` Spanish, `pt` Portuguese, `it` Italian,
`nl` Dutch, `pl` Polish, `cs` Czech, `sk` Slovak, `uk` Ukrainian, `ru` Russian,
`tr` Turkish, `ro` Romanian, `hu` Hungarian, `sv` Swedish, `fi` Finnish, `da` Danish,
`no` Norwegian, `el` Greek, `bg` Bulgarian, `hr` Croatian, `sr` Serbian, `he` Hebrew,
`ar` Arabic, `fa` Persian, `hi` Hindi, `id` Indonesian, `vi` Vietnamese, `th` Thai,
`ja` Japanese, `ko` Korean, `zh` Chinese. An unknown code costs you that language
only; the rest of the run still completes.

Unsure which article a topic maps to? Check first, it is one cheap call:

```bash
python3 scripts/wikitrends.py resolve --topic "intermittent fasting" --langs pl,cs,uk
```

**If a command prints `NETWORK_BLOCKED` (exit code 5), do not stop and do not describe
hypothetical results.** Sandboxes such as Claude's code execution often cannot reach
Wikimedia. The output lists the exact commands to run next: `plan` lists URLs, you fetch
them with your own web-fetch tool, then `ingest` and `analyze --offline`. Details are
in "If your environment has no network access" below. Only if you have no web-fetch tool
either, ask the user to allow `wikimedia.org`, `wikipedia.org` and `www.wikidata.org`
in their code-execution network settings.

Expected runtime, so you do not assume it has hung: about 2 seconds per language
edition on first request, under a second for anything already cached (6 editions ×
36 months takes ~11s cold, ~1s warm). The very first PDF on a new machine adds a
one-off ~20s while matplotlib builds its font cache.

## Language: answer in the user's language

- **Reply in the language the user wrote in.** A Ukrainian question gets a Ukrainian answer, an
  English question an English one, and so on.
- **Always pass the user's own words as `--question`**, unchanged and untranslated. The memo's
  language is detected from them, so a Ukrainian question gives a Ukrainian PDF. Use
  `--report-lang` only if the user asks for the report in a different language from their question.
- **When the digest prints `REPORT_LANGUAGE uk`,** it also prints `RECOMMENDATION_UK ...`: the
  same recommendation in the user's language, worded exactly as in the PDF. Base your reply on
  that line. Write `--summary` in the same language.
- **Memo translations exist for:** English and Ukrainian. For any other language the digest says
  so (`REPORT_LANGUAGE en ... has no memo translation yet`). In that case, tell the user the PDF is
  in English and still reply in their language.
- **The claim check works on Ukrainian text too.** It handles decimal commas (45,5%) and Ukrainian
  language names and direction words (зростає, падає, стабільний).

## How to read the output

```
- uk: Англійська мова: raw -35.6% year over year (2025-09..2026-08 vs 2024-09..2025-08) (declining, p=0.0), median 9,189/mo, 136.82/M edition views, confidence 100/100 high
    verdict: LOSING GROUND - Raw pageviews -35.6% year over year (...) while the whole edition moved -24.6%,
      and its share of edition traffic is also falling (-13.9%), so the topic is losing
      ground faster than the platform overall.
    why: -15: high volatility, 94.2% robust CV against a 60.0% limit; ...
```

Read it in this order:

1. **The `verdict:` line is the answer.** It is written to be quoted as-is and is
   self-contained, so you cannot mix up figures between two different runs.
   - `GAINING GROUND` — the topic's share of its edition is rising. A genuine
     positive signal.
   - `HOLDING GROUND` — share is flat. Interest is **stable**: the negative `raw`
     number is Wikipedia shrinking, not this audience losing interest. Say this
     explicitly, or you will mislead the user.
   - `LOSING GROUND` — falling faster than the platform.

   Why this matters: Wikipedia traffic is down roughly 7–25% year over year in every
   edition, so `raw` is almost always negative and on its own means very little.
   Every verdict states the share-of-edition change as a number. Quote that number;
   never estimate one.
   The `raw` percentage covers the period printed next to it (normally the last 12
   months vs the 12 before), **not** the whole `--months` window. Say "year over year".
2. **`median/mo`** is audience size. Under 100 views/month nothing is reliable; under
   500 treat it as directional only.
3. **`/M edition views`** is interest intensity, comparable between a big and a small
   edition. Use it to rank *which audience cares most*, and `median/mo` to rank
   *which audience is biggest*. These often disagree — report both.
4. **`confidence N/100`** plus the `why:` lines, which state the penalty and the
   threshold that was tripped. Write it as "85/100", never "85%": it is a score, not a probability. Quote a reason whenever confidence is below 75. Below
   50, say plainly that the data cannot answer the question yet.
5. `direction` words in brackets: `growing` / `declining` require both a real effect
   (>10%) and statistical significance (p<0.05). `flat` means the move is too small
   to matter, `unclear` too noisy to call, `too_short_to_judge` not enough history.

Also printed when relevant:

- `spikes: 2025-04` — a one-off event, not a trend. If much of the growth sits in
  spike months, say the growth is event-driven.
- `seasonal: strength 0.71` — above 0.5 the topic has a strong calendar cycle.
  Never compare consecutive months; compare the same month year over year.
- `NOTE xx.wikipedia has no article ...` — that edition has no article at all. This
  is a finding: either an unserved audience or a concept that language frames
  differently. Never substitute another article silently.
- `TIER investigate_first / worth_a_look / deprioritise` — research ordering only.
- `RECOMMENDATION <ACTION>: ...` plus one line per edition with its first next step and
  what would change the call. This is produced by fixed rules (`scripts/decide.py`, listed
  in `references/ANALYSIS_METHODS.md#decision-rules`), and it is what the PDF leads with.
  **Build your answer around it. Do not contradict it.** If you think the rule misses
  something, say so explicitly as your own view, next to the rule's call.
- `90% range: raw -40..-31%, share -17..-10%`: how much the growth figure depends on which
  months happened to be good. A range that crosses zero means the direction is not
  established. Quote the range with the figure whenever a decision depends on it.
- `SEPARATION ...`: whether the top-ranked edition is really ahead of the runner-up. If it
  says "not clearly different", do not present the ranking between those two as a finding.
- `ASSUMPTIONS`: what this run's numbers rest on (which articles, which months, which
  traffic, what "flat" means). Put the ones that matter for the user's decision in your answer.
- `PRIORITY (weights ...)` — a 0-100 score from ranks of reach, intensity and share
  momentum *within this comparison*. It is not a percentage or a probability. When the
  user states criteria, re-run with `--weights` and say which weights you used; don't
  re-weight in your head.

## The PDF is a decision memo

Every `analyze` run without `--no-pdf` writes a one-page memo for founders and CEOs:
- **the recommendation** (colour plus label) with its one-sentence reason;
- **a scorecard** per edition: action, readers, share change with range, months up, confidence;
- **two charts**: share of edition over time, plus either the topic against the whole edition
  (one language) or share change with 90% ranges (several languages);
- **the evidence chain, next steps, and what would change the call**;
- **risk-rated trust notes** and the run's assumptions;
- **a command** to reproduce it.

Your part is `--question` (the user's words) and usually `--summary` (one or two sentences in
plain language for the reader). Everything else comes from the data.

**Writing a report takes two runs. Never write the summary before you have seen the results.**
1. Run `analyze` with the topic, languages and `--question`. Read the `RECOMMENDATION` line.
2. Write a `--summary` that says the same thing as the recommendation, in the user's language,
   using numbers from the digest. Then run the **same command** again with `--summary`. This
   takes about a second because the data is cached.

`--summary` or `--finding` on a run you haven't seen yet is refused (`SUMMARY_BEFORE_DATA`,
exit 7). A summary that contradicts the recommendation is refused (`CHECK_FAILED`, exit 6). For
example, calling a DEPRIORITISE topic "stable" or "growing" is refused.

## Answering the three common question shapes

**"Is interest in X growing in language Y, and can we trust it?"**

```bash
python3 scripts/wikitrends.py analyze --topic "astronomy" --langs uk --months 36
```
Answer with the share-of-edition direction, then the confidence and its reasons,
then the caveats (spikes, seasonality, traffic size). Answer the trust question
explicitly — it was asked.

**"Compare growth of X between languages A and B."**

```bash
python3 scripts/wikitrends.py analyze --topic "intermittent fasting" --langs pl,cs --months 24
```
Compare share change, not raw change: the two editions are shrinking at different
rates. Mention if one edition has no article.

**"Which markets/languages should we enter first?"**

```bash
python3 scripts/wikitrends.py analyze --topic "English language" --langs uk,pl,cs,de,es,tr --months 36 --normalise
```
Rank on share momentum, cross-check against reach and intensity, and name the
next validation step for the top one or two. Say which candidates you rejected and why.

## If your environment has no network access

Some sandboxes cannot reach `wikimedia.org` (you will see connection or "domain not
allowed" errors). Do not give up and do not describe what the answer might look like:
fetch the data with whatever web-fetch tool *you* have, and let the skill do the
analysis. There is a command pair for exactly this.

```bash
# 1. Ask what is needed. Prints a numbered list of URLs plus the filename for each.
python3 scripts/wikitrends.py plan --topic "astronomy" --langs uk,pl --months 24 --out-dir fetch

# 2. Fetch each URL with your own web tool and save the response body, raw and
#    unmodified, into fetch/ under the exact filename given. No extra text, no
#    reformatting, no commentary around the JSON.

# 3. Hand the responses over.
python3 scripts/wikitrends.py ingest --dir fetch

# 4. Repeat 1-3 until plan prints READY (at most three rounds), then:
python3 scripts/wikitrends.py analyze --topic "astronomy" --langs uk,pl --months 24 --offline
```

Why it loops: an article's Wikidata id has to be fetched before its titles in other
languages can be looked up. **If you already know the exact article titles, pass
`--articles uk:Астрономія,pl:Astronomia` instead of `--topic` and it needs only one
round.** Use the same arguments for `plan` and `analyze`, or the plan will not match.

Exit code 3 from `plan` or `analyze --offline` means data is still missing. Exit code 0
from `plan` means READY.

Faster when you know the article titles (for example from Wikipedia itself): pass
`--articles uk:Астрономія` so a single fetch round is enough.

## Check your answer before you send it

Every number and verdict label you write must come from the digest. The tool can verify this:

```bash
python3 scripts/wikitrends.py check --json <FILE json path from the digest> --text "<your draft>"
```

Check the **exact text you will send**, in the user's language. Don't check an English draft and then send a
different translation. `CHECK_OK` means you can send the draft. `CHECK_FAILED` (exit 6) lists what to fix:
- a percentage that matches no figure, or that belongs to a different edition than the one the
  sentence names;
- a confidence score written as a percentage (write 85/100);
- a verdict word on the wrong edition (e.g. GAINING GROUND for an edition that is HOLDING).

`--finding` text for the PDF gets the same check automatically. If it fails, the PDF is not
built (exit 6), JSON and CSV are still written, and you fix the text and rerun (cached, ~1s).
The check covers numbers and verdict labels. It does not check other wording, such as calling
a HOLDING series "growing", so read your own sentences against the verdict lines too.

## Rules for your written answer

- Lead with the decision-relevant finding, not the method.
- Always pair a number with its confidence. Never quote a growth figure alone.
- Always distinguish "interest fell" from "Wikipedia traffic fell". Getting this
  backwards is the single most likely way to mislead the user.
- Never say pageviews show demand, market size, or willingness to pay. They show
  reading curiosity. Recommend a concrete next check (ad test, search volume,
  landing page, interviews) rather than implying the decision is settled.
- A language edition is not a country: `en.wikipedia` is read worldwide, `ru.wikipedia`
  well beyond Russia. Say "readers of the X edition", not "people in country X".
- State what you excluded and why (missing article, too little traffic, short history).
- If the user's framing cannot be tested with this data, say so and offer the
  closest question that can.
- Put your own conclusions on the PDF with `--finding "..."` rather than leaving
  the auto-generated lines, which are deliberately mechanical.

## Follow-up and repeat questions

Responses are cached on disk for 7 days, so re-running with different languages,
months or topics re-uses what was already fetched and returns in about a second.

- "What changed since last time?" / repeat questions: rerun the same command. The digest prints
  `SINCE_LAST_RUN` with each edition's previous verdict and share change. Report that, not
  your memory of the earlier answer.
- Can't remember what was already run in this project? `python3 scripts/wikitrends.py history`
  lists earlier runs (from `wikitrends-out/runs.jsonl`) with verdicts and JSON paths.
  Use a listed JSON path with `check`.
- Changing the window, adding a language, or switching topics: just run `analyze`
  again with the new flags. New criteria ("growth matters more"): add `--weights`. Do not try to reuse a previous answer from memory.
- Same articles, new question: pass `--articles` with the titles from the first run
  to skip resolution entirely.
- Need the monthly numbers: read the CSV listed under `FILE csv`. Do not ask for
  `--json` unless you specifically need the full statistics; the digest plus CSV is
  cheaper.
- `python3 scripts/wikitrends.py cache --clear` forces fresh data.

## Troubleshooting

| Symptom | What to do |
|---|---|
| `UNRESOLVED` topic | try `--pivot` with the language the phrase is written in (`--pivot uk`), or pass `--articles` directly |
| resolver picked the wrong concept | run `resolve`, read `other possible concepts`, then use `--articles` |
| `NO DATA` for one language | usually no such article; confirm with `resolve` and report it as a gap |
| everything looks like it is declining | expected — compare `share` values, not raw |
| `confidence` very low everywhere | the topic is too niche on Wikipedia; widen to a broader article or a bigger edition |
| `pdf_pages: 2` | too much content to compress; drop a language or pass fewer `--finding` lines |
| network/403/sandbox errors | the skill needs outbound access to `wikimedia.org`, `wikipedia.org` and `www.wikidata.org`. In a sandboxed shell, re-run with full network permission; if the environment cannot reach them at all, use the no-network flow above |

## Files

- `scripts/wikitrends.py` — the CLI; run this
- `scripts/wm_api.py` — Wikimedia pageviews, title resolution, disk cache
- `scripts/analyze.py` — the statistics (importable, no network)
- `scripts/report.py` — charts and the one-page PDF
- `references/ANALYSIS_METHODS.md` — what each metric means, thresholds, and why
- `references/API_REFERENCE.md` — endpoints, language codes, limits, failure modes
- `references/EXTENDING.md` — how to grow this for larger studies
- `tests/` — `python3 -m pytest tests -q`, no network needed
