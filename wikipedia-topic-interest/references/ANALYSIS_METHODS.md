# Analysis methods

Why each number is computed the way it is, and what would go wrong otherwise.
Thresholds live at the top of `scripts/analyze.py`.

## The central correction: share, not raw views

Wikipedia pageviews are in a broad, sustained decline. Measured over 2023-09..2026-08:

| edition | edition-wide year-over-year |
|---|---|
| uk.wikipedia | −24.6% |
| es.wikipedia | −20.9% |
| tr.wikipedia | −16.3% |
| cs.wikipedia | −12.6% |
| pl.wikipedia | −8.8% |
| de.wikipedia | −7.3% |

So *almost every article* has falling raw views. A tool that reports raw change
would tell a founder that interest in every topic is collapsing in every market,
and would rank markets by how fast Wikipedia is shrinking there.

The fix is to run the same tests on the topic's **share of its edition's traffic**
(views per million edition views, from the `aggregate` endpoint), and to report both:

- raw change — what happened to the actual number of readers
- share change — whether the topic gained or lost ground against everything else
  people read in that language

`vs_edition` summarises the comparison:

| value | meaning | how to say it |
|---|---|---|
| outperforming its edition | share rising | interest is genuinely gaining ground |
| tracking its edition | share flat | interest is stable; the raw fall is platform-wide |
| underperforming its edition | share falling | losing ground faster than the platform |

Ranking and tiering use share change whenever a baseline is available.

## Trend direction

Three ingredients, all required to agree before a direction is claimed.

**Mann-Kendall test** (`mann_kendall`) — counts, for every pair of months, whether
the later value is higher or lower, giving a rank correlation (tau) and a two-sided
p-value from a normal approximation with tie correction. It is non-parametric, so it
assumes neither normal noise nor a straight line, and it uses every month rather
than just the endpoints.

**Theil-Sen slope** (`theil_sen_slope`) — the median of all pairwise slopes, fitted
on log views so the result reads as a multiplier per year. The median makes it
immune to a few spike months; ordinary least squares is not.

**Year-over-year block comparison** (`_year_over_year`) — the last 12 months against
the previous 12. This is the headline figure when at least 24 months are available,
because any calendar seasonality lands in both blocks and cancels out.

Direction is assigned in `_direction`:

1. Fewer than 6 months → `too_short_to_judge`.
2. `|headline| < 10%` → `flat`, **whatever the p-value is**. Over 30+ months the
   Mann-Kendall test will report p<0.001 for a drift of a fraction of a percent;
   that is statistically real and commercially irrelevant. Effect size gates first.
3. p ≥ 0.05 → `unclear` (it moved, but not consistently).
4. Headline and tau disagree in sign → `unclear`. A spike in the final months can
   lift the year-over-year figure while the month-by-month pattern falls; claiming
   a direction there would be picking the flattering number.
5. Otherwise `growing` or `declining`.

### Why not (last − first) / first

Given a flat series at 1000 views/month that ends with one viral month of 40,000,
that formula reports **+3900% growth**. This implementation reports `unclear`,
flags `2024-12` as a spike, notes that most views come from spike months, and drops
confidence below 60. That case is locked down by a test.

## Data quality

**Partial months.** Monthly pageview data is only meaningful for whole months. Asking
the API for `monthly/20240101/20240401` returns an "April" containing a single day —
72 views against a normal 3,000. `month_window()` therefore always aligns to the
first day of a month and ends on the last day of the last *complete* month.

**Incomplete months in Wikimedia's own data.** If an edition's total traffic for a
month is below half its median, that month's data is incomplete platform-wide, not a
real collapse in reading. Such months are dropped and listed in
`quality.excluded_months`. Using the edition baseline as the detector means the
judgement is made from data rather than guessed.

**Gaps.** The API omits months with no recorded views, so absent months are detected
by walking the calendar between the first and last observation and reported in
`quality.missing_months`.

**Bots.** All requests use `agent=user`, which excludes self-identified crawlers.
`all-agents` can inflate a quiet article several-fold and is the default in many
naive implementations.

## Spikes and seasonality

**Spikes** (`find_spikes`) use the Iglewicz-Hoaglin robust z-score: distance from the
median divided by a scaled median absolute deviation, flagged above 3.5. MAD is used
instead of standard deviation because a spike inflates the standard deviation enough
to hide itself.

MAD collapses to exactly zero when more than half the months share a value, which is
common on low-traffic articles and on any quiet series that later goes viral. A zero
scale would mean "no spikes" for the most obvious spike there is, so `robust_scale`
falls back to mean absolute deviation from the median.

`spike_share_of_views` is the fraction of all views contributed by spike months above
the median level. Above 0.25, growth is event-driven rather than a durable shift.

**Seasonality** (`seasonality_strength`, 0–1) detrends the series, groups residuals by
calendar month, and compares the spread of month-of-year means to the overall spread.
Above about 0.5 the topic has a strong cycle — education topics peak in term time —
and consecutive months must not be compared. Needs 24+ months.

## Confidence

A 0–100 score that always arrives with written reasons, so the agent can quote why a
signal is weak instead of presenting every number with equal authority. Penalties are
additive:

| condition | penalty |
|---|---|
| median < 100 views/month | −35 |
| median < 500 views/month | −20 |
| fewer than 6 months | −30 |
| fewer than 24 months (no year-over-year) | −10 |
| trend not significant (p ≥ 0.05) | −25 |
| spike share > 0.25 | −20 |
| robust CV > 60% | −15 |
| months missing from the response | −10 |
| raw view trend is just platform drift | −15 |

Bands: 75+ high, 50–74 moderate, 30–49 low, below 30 very low. The exact numbers are
a deliberately blunt heuristic; the reasons are the part with real value.

## Ranking and tiers

Three axes are reported separately rather than merged into one score, because they
answer different questions and combining them hides the trade-off:

- **reach** — median monthly views, a proxy for audience size
- **intensity** — views per million edition views, how much that audience cares
  relative to its size; lets a small edition beat a large one
- **momentum** — share-of-edition change

Tiers (`_tier`), for ordering research only:

- `deprioritise` — under 100 views/month (nothing is measurable), or losing share
  with confidence ≥ 50
- `investigate_first` — gaining share with confidence ≥ 55
- `worth_a_look` — gaining share but low confidence, or stable with meaningful reach

## Limitations that cannot be fixed by better statistics

- Pageviews measure curiosity. They are not demand, purchase intent, or willingness
  to pay. Use them to order hypotheses, then validate commercially.
- A language edition is not a country or a market.
- Article quality, internal links and search-engine ranking move traffic
  independently of public interest; a rewritten article can gain readers on merit.
- AI assistants and search features increasingly answer questions without a click,
  which is the most likely driver of the platform-wide decline above. It affects
  topics unevenly, so share comparisons are safer than raw ones but not immune.
- Redirects resolve to their target, so a renamed article's history can shift.
- Data begins July 2015.


## Intervals, separation and the claim check

**90% range on year-over-year change.** Resample the 12 paired calendar months (this month vs the
same month last year) 2,000 times with a fixed seed, and recompute the ratio of 12-month sums
each time. The range is the 5th to 95th percentile. Pairing keeps seasonality cancelled. The
fixed seed means the same data always gives the same range. It is computed for raw views
and for share of edition traffic, and needs 24 months.

**Separation.** Compare the ranking's leader with the runner-up on the measure the ranking
used: share of edition traffic when available, otherwise raw views. If their ranges overlap,
the order between them is not established by this data.

**Claim check (`check`, and automatically for `--finding`).** The draft is split into
sentences. A sentence that names exactly one edition (by code, language name in English or
Ukrainian, label or article title) must use that edition's figures. Point figures are always
accepted. Range bounds are accepted only in a sentence that talks about a range. Differences
between growth figures are accepted only as points (`pp`). The tolerance is 1.5 points for
rounding. A number that equals a confidence score and is written with `%` is flagged as a
score written as a percentage. A verdict label (GAINING/HOLDING/LOSING GROUND) attached to
the wrong edition is flagged. Limitations: the check does not understand free wording such as
"growing" or "stable". A wrong number within 1.5 points of a real figure for the same edition
passes.

**Run history.** Every `analyze` appends one line to `<out-dir>/runs.jsonl`: time, run
name, data window, weights, JSON path, and each series' verdict, raw and share change,
confidence and median views. A rerun with the same topics and languages prints
`SINCE_LAST_RUN` against the most recent earlier record.


## Decision rules

The recommendation in the digest, the JSON (`decision`) and the PDF comes from `scripts/decide.py`.
It is a fixed rule table, applied in order, to numbers computed in `analyze.py`. The same data
always gives the same call. Nothing in the call is generated freely.

"Direction" and "range" below mean the change in the topic's **share of edition traffic** when a
baseline exists. Without a baseline, raw views are used.

| Order | Condition | Action | Meaning for a decision-maker |
|---|---|---|---|
| 1 | confidence < 50, or median < 100 views/month, or < 6 months of data | INSUFFICIENT EVIDENCE | Don't decide on this; widen the question |
| 2 | direction growing and the whole 90% range above 0 | PRIORITISE | Gaining attention beyond platform noise: validate demand now |
| 3 | direction growing, range touches or crosses 0 | PROMISING | Looks like a gain, not yet established: treat as a hypothesis |
| 4 | direction declining | DEPRIORITISE | Losing attention faster than the platform: don't invest on this signal |
| 5 | direction flat (move under ±10%) | STABLE | Steady audience: decide on size and fit, not momentum |
| 6 | otherwise (moved, but not consistently) | NO CLEAR SIGNAL | Don't act on direction |

"Growing" or "declining" needs both a move of at least 10% and a significant trend (p < 0.05);
see "Trend label" above. A STABLE series whose whole range sits on one side of zero is marked
"softening slightly" or "slight real gain": the drift is real but too small to change the call.

**Overall call (several editions).** Candidates are ordered by action, from PRIORITISE down to
INSUFFICIENT EVIDENCE, then by the priority score. The best one is compared directly with every
other viable candidate. If their 90% ranges overlap, the memo says they are equal candidates.
DEPRIORITISE and INSUFFICIENT EVIDENCE editions are listed by name.

**Evidence chain.** Each call comes with numbered steps, each carrying its figure:
1. raw change and period;
2. whole-edition change;
3. share change with range and what the range means;
4. consistency (months above last year, trend test p);
5. intensity;
6. seasonal peak, if strong.

**Next steps and "what would change this call"** are fixed per action. PRIORITISE gets a
willingness-to-pay test. DEPRIORITISE requires independent evidence before going ahead.
Each has an explicit condition that would move it to a different action.

**Trust notes.** These are ordered high, then medium, then low risk, and computed for the run:
- audience size, with how much 50 readers move a month;
- whether the range establishes a direction;
- month-to-month volatility;
- one-off spikes vs recurring calendar peaks (the same calendar month spiking in different
  years is a yearly cycle, not news);
- which single article was counted;
- the fact that curiosity is not purchase intent.

These rules are defaults chosen for early-stage product decisions. They are not universal
truths. Change the thresholds in `decide.py` and `analyze.py` to match your own risk appetite.
The memo cites this file, so readers can see the rules that produced it.


## Report language

The memo's wording comes from `scripts/i18n.py`. It currently has English and Ukrainian.
The language is detected from the user's own words (`--question`, then `--summary`/`--finding`):
- Cyrillic with Ukrainian letters (і, ї, є, ґ) → Ukrainian.
- Other Cyrillic → Russian. There is no translation for it, so the memo is in English.
- Latin scripts → Polish, Czech, German, French, Spanish, Portuguese or Italian, by accented
  letters and common words. Anything else → English.

`--report-lang` overrides the detection. Only the words change. The action codes, numbers, rules
and the JSON are identical in every language, so a Ukrainian and an English memo of the same run
make the same recommendation.

To add a language, copy the `"en"` block in `CATALOG`. Translate every value and keep every
`{placeholder}`. Add 12 month names (in the grammatical form used after "in"), and add the code
to `SUPPORTED`. `tests/test_i18n.py` fails if any key or placeholder is missing.
