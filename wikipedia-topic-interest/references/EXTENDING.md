# Extending this skill

The current version answers a bounded question: given topics and language editions,
is interest moving, can it be trusted, and which audience looks most promising. This
is the path from there to larger and harder research, ordered so each step pays off
before the next begins.

Every step should keep two invariants that make the skill usable by a small model:
**one command answers one question**, and **stdout stays short while detail goes to
files**. Adding scripts the agent must chain together is the main way this gets worse.

## Stage 1 — depth on a single question (small changes, high value)

**Explain a spike.** A flagged spike month is currently just a warning. Refetch that
month at `--granularity daily`, find the peak day, and look up what happened
(`action=query&list=recentchanges` on the article, or the edition's `top` endpoint for
that day). Turns "ignore this spike" into "this was a news event on 14 April".

**Widen the concept.** One article underestimates a topic: astronomy interest also
lives in *Solar System*, *Black hole*, *Telescope*. Add `--expand-category` to pull
members of a Wikidata class or a Wikipedia category and aggregate them into a topic
basket, reported with per-article contributions so the basket stays auditable.

**Add a control topic.** Even share-of-edition drifts. Comparing the topic against a
stable reference basket (a few evergreen articles) separates topic movement from
edition-wide composition changes more tightly than the aggregate baseline alone.

**Forecast with an interval.** A seasonal-naive or Holt-Winters projection 6–12 months
ahead, always reported as a range, not a point. Only worth doing once seasonality
strength is known, which it now is.

## Stage 2 — breadth and discovery

**Screening mode.** Instead of "is X growing", answer "what is growing". Pull the
`top` endpoint for an edition across months, rank by share momentum, and return the
20 fastest risers above a traffic floor. This inverts the tool from testing a
hypothesis to generating them, which is what founders actually lack.

**Topic sets from one call.** Accept `--topics-file topics.csv` with 50–500 rows and
return a ranked table plus a multi-page PDF. This is where the current design starts
to strain and Stage 3 becomes necessary.

**Geography.** `top-by-country` gives per-country reading for an edition, which
partly fixes the "a language is not a market" limitation. The data is privacy-rounded
and only covers top articles, so it must be reported as indicative.

**Other Wikimedia projects.** Wiktionary pageviews are a much better proxy for
language-learning demand than Wikipedia's *English language* article. The `project`
parameter already supports `xx.wiktionary`; only defaults and validation need work.

## Stage 3 — scale

At hundreds of series the current shape breaks in three places, in this order:

1. **Fetch volume.** The 7-day file cache and 4-way concurrency are right for tens of
   requests, wrong for thousands. Move to SQLite with a `(project, article, month)`
   primary key so partial windows are reused instead of refetched, and fetch only the
   months not already stored. This alone changes the cost profile more than anything
   else.
2. **Bulk data.** Past roughly a thousand articles, stop using the per-article API and
   read the published [pageview dumps](https://dumps.wikimedia.org/other/pageviews/)
   instead: one pass over a monthly file yields every article at once. Keep the API
   path for small interactive queries.
3. **Context budget.** A 300-row result cannot go through a model's context. Return
   only the top and bottom N with aggregate statistics, and keep the full table in
   SQLite/Parquet with a `query` subcommand the agent can filter against. The digest
   should describe the shape of the result set, not enumerate it.

Statistical work that becomes worthwhile at this scale: STL decomposition instead of
the current seasonality heuristic; change-point detection to date *when* a trend
turned; multiple-comparison correction, because testing 500 topics at p<0.05 yields
25 false trends by construction.

## Stage 4 — beyond Wikipedia

Wikipedia interest orders hypotheses; it cannot confirm demand. The natural
progression is to join it with signals that carry intent, keeping each source's
weight explicit: search volume, app-store search terms, subreddit or forum growth,
and finally the founder's own funnel data. The value of this skill at that point is
as the cheap first filter that decides what is worth paying to measure.

## Keeping quality while the surface grows

- Every new metric needs a test built from a case where the naive answer is wrong.
  The existing suite is written that way (spike-as-growth, partial final month,
  platform-wide decline, significant-but-tiny drift) and it caught three real bugs
  during development.
- Re-run `evals/run_eval.py` against a small cheap model after any change to SKILL.md
  or to stdout. Usability for a weak model is a feature that regresses silently.
- When adding a flag, ask whether the agent could plausibly get it wrong. If yes, it
  needs a default that is right, not documentation.
