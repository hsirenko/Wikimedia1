# wikipedia-topic-interest

An [Agent Skill](https://agentskills.io/specification) that turns Wikimedia pageview
statistics into decisions for B2C product teams: which topic to build next, and which
language to launch in.

`SKILL.md` is the agent-facing entry point. This file is for humans working on the skill.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Charts and PDFs need `matplotlib` and `reportlab`. Fetching and analysis use only the
standard library, so `--no-pdf` runs on a bare Python 3.9+ install with nothing to
install at all.

## Try it

```bash
# Is interest in astronomy growing in Ukrainian Wikipedia, and can we trust it?
.venv/bin/python scripts/wikitrends.py analyze --topic astronomy --langs uk --months 36

# Which language audience should a language-learning app research next?
.venv/bin/python scripts/wikitrends.py analyze --topic "English language" \
    --langs uk,pl,cs,de,es,tr --months 36 --normalise

# What is this topic called in each edition?
.venv/bin/python scripts/wikitrends.py resolve --topic "intermittent fasting" --langs pl,cs,uk
```

Results land in `wikitrends-out/`: a one-page PDF, two PNG charts, the full statistics
as JSON, and every monthly observation as CSV.

## Running where there is no network

Some agent sandboxes cannot reach `wikimedia.org` at all — Claude's code execution
container is one. Rather than failing there, the skill can split fetching from
analysis: the agent retrieves the URLs with its own web tool, and the skill does the
statistics.

```bash
python3 scripts/wikitrends.py plan   --topic astronomy --langs uk,pl --months 24 --out-dir fetch
# fetch each listed URL with any tool, save the raw body under the given filename
python3 scripts/wikitrends.py ingest --dir fetch
# repeat until plan prints READY, then
python3 scripts/wikitrends.py analyze --topic astronomy --langs uk,pl --months 24 --offline
```

`plan` does not rebuild URLs by hand. It runs the real pipeline with the network
switched off and reports whatever the cache could not serve, so it can never drift out
of step with what `analyze` actually requests. Resolution gates pageviews (an article's
Wikidata id must be known before its translated titles are), so it takes up to three
rounds — or exactly one if you pass `--articles lang:Title` instead of `--topic`.

## Tests

```bash
.venv/bin/python -m pytest tests -q        # 73 tests, no network required
```

`tests/test_analyze.py` covers the statistics, `tests/test_pipeline.py` drives the CLI
end to end with the Wikimedia API stubbed out, and `tests/test_offline.py` exercises the
whole plan/ingest bridge including a guard that fails if offline mode so much as opens a
socket. All deterministic and offline.

Every test is written around a case where the obvious implementation gives a
confidently wrong answer — a flat series ending in a viral spike, a partial final
month, a decline that is really platform-wide, a statistically significant drift of
0.0%. Three of those were real bugs found this way during development.

## Evaluating against a small model

The skill is meant to be usable by a cheap fast model, which is a property that
regresses silently. `evals/run_eval.py` gives such a model `SKILL.md` and a shell tool,
asks a founder's question, and grades what it does:

```bash
export OPENROUTER_API_KEY=sk-or-...
.venv/bin/python evals/run_eval.py --model anthropic/claude-haiku-4.5 -v
```

Model slugs are worth copying exactly; `anthropic/claude-haiku-4-5` (with hyphens) does
not exist and returns a 404. Verify any slug against the public list, which needs no key:

```bash
curl -s https://openrouter.ai/api/v1/models | \
  python3 -c "import json,sys; print([m['id'] for m in json.load(sys.stdin)['data'] if 'haiku' in m['id']])"
```

To run at zero cost, pick a free model that still supports tool calling, for example
`--model qwen/qwen3.8-27b:free`. Free tiers are rate-limited, so add `--case` to run one
scenario at a time.

It checks that the model used the CLI rather than writing its own analysis, needed few
commands, and produced an answer that keeps the share-vs-raw distinction, the
confidence score and the "interest is not demand" caveat.

Re-run it after any change to `SKILL.md` or to what the CLI prints.

## How the pieces fit

| file | role |
|---|---|
| `SKILL.md` | what the agent reads: commands, how to read output, rules for the written answer |
| `scripts/wikitrends.py` | the CLI; resolve → fetch → analyse → chart → PDF in one call |
| `scripts/wm_api.py` | pageviews, project baselines, topic→title resolution, disk cache |
| `scripts/analyze.py` | the statistics; pure functions, no network, no third-party imports |
| `scripts/report.py` | matplotlib charts and the one-page reportlab PDF |
| `references/ANALYSIS_METHODS.md` | every metric, its threshold, and what it prevents |
| `references/API_REFERENCE.md` | endpoints, encoding, failure modes, rate limits |
| `references/EXTENDING.md` | the roadmap to larger studies |

## Design decisions worth knowing

**Share of edition traffic, not raw views.** Wikipedia traffic is falling platform-wide
(7–25% year over year depending on edition). Reporting raw change would tell every
founder that interest in every topic is collapsing everywhere. The skill reports both
and bases its recommendations on the share.

**Robust statistics over endpoint arithmetic.** Direction comes from a Mann-Kendall
test across all months, magnitude from a Theil-Sen slope and a year-over-year block
comparison. A direction is only claimed when the effect exceeds 10% *and* is
significant *and* both tests agree on the sign.

**Confidence always travels with reasons.** Each score names the penalty and the
threshold it tripped, so an agent can explain a weak signal instead of quoting a
number with false authority.

**Concept-based title resolution.** A topic is pinned to a Wikidata item once, then
each edition's title is read from its sitelinks. Per-language full-text search was
tried and rejected: searching Polish Wikipedia for "post przerywany" confidently
returns *Charlie Kirk*. A missing sitelink is reported as a genuine gap.

**Whole months only.** Requesting `monthly/20240101/20240401` yields an "April" of one
day, which reads as a 98% crash. Windows always end on the last complete month.

## Development notes

AI assistance was used throughout; everything was verified rather than trusted:

- Live API responses were inspected before any code was written against them. This is
  how the partial-month trap and the missing Polish article were found.
- Statistical claims were checked against hand-constructed series with known answers
  (`theil_sen_slope([10,13,16,19,22]) == 3.0`), and the platform-wide decline was
  confirmed by querying the `aggregate` endpoint directly for six editions.
- The "no Polish article" result was cross-checked by probing four plausible Polish
  titles individually before letting the skill report it.
- PDFs were rendered to images and read back to confirm Cyrillic and Czech characters
  appear rather than falling back to empty boxes.
- The skill was driven by Claude Haiku 4.5 cold, with only `SKILL.md` for guidance. It
  answered all three example questions in one command each, and its critique produced
  four fixes: a self-contained `verdict:` line (it had transposed a percentage between
  two runs), plain-language `LOSING GROUND`/`HOLDING GROUND` labels, explicit
  thresholds in confidence reasons, and a language-code list in `SKILL.md`.

## License

MIT.
