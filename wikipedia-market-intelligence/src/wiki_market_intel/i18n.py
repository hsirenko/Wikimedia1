"""Report language: every sentence a human reads, in each supported language.

The report follows the language of the user's request (detected from `--question`,
or set with `--report-lang`). Only words change: KPIs, rules and the JSON result are
identical in every language, and the JSON stays in English as the canonical record.

To add a language: copy the "en" block, translate every value, keep every {placeholder},
add 12 month names (and their "in <month>" form), and add the code to SUPPORTED.
tests/reporting/test_i18n.py fails if any key or placeholder is missing.
"""

from __future__ import annotations

import re
import string
from typing import Any

SUPPORTED = ("en", "uk")

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"],
    "uk": ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень", "Липень", "Серпень", "Вересень",
           "Жовтень", "Листопад", "Грудень"],
}
MONTHS_IN = {   # "in January" / "у січні"
    "en": MONTHS["en"],
    "uk": ["січні", "лютому", "березні", "квітні", "травні", "червні", "липні", "серпні", "вересні", "жовтні",
           "листопаді", "грудні"],
}

CATALOG: dict[str, dict[str, str]] = {
    "en": {
        "title": "Wikipedia Market Intelligence Report",
        "s1": "1. Executive Decision Card", "s2": "2. Topic Definition", "s3": "3. Demand", "s4": "4. Growth",
        "s5": "5. Seasonality", "s6": "6. Language Opportunity", "s7": "7. Localization", "s8": "8. Topic Ecosystem",
        "s9": "9. Anomalies", "s10": "10. Data Quality", "s11": "11. Business Implications",
        "topic": "Topic", "edition": "Language edition", "edition_note": "a language edition, not a country",
        "period": "Analysis period", "period_value": "{start} to {end}",
        "annual": "Annual views (last 12 months)", "monthly": "Monthly average", "daily": "Daily average",
        "requested_views": "Views in the requested period", "unique": "Unique devices",
        "per_device": "Views per unique device", "yoy": "YoY", "cagr": "3Y CAGR", "momentum": "Momentum",
        "seasonality": "Seasonality", "season_value": "peak {peak}, trough {trough}",
        "localization": "Localization metrics", "quality": "Data quality",
        "observations": "Key observations", "no_observations": "No observation could be computed: see Data Quality.",
        "canonical": "Canonical topic", "wikidata": "Wikidata ID", "no_wikidata": "n/a (no Wikidata entity)",
        "article": "Article used", "article_value": "{title} (page ID {id})", "method": "Resolution method",
        "confidence": "Resolution confidence", "mappings": "Language mappings", "related": "Related topics",
        "kpi": "KPI", "value": "Value", "metric": "Metric", "status": "Status", "reason": "Reason",
        "chart_alt": "Monthly pageviews", "no_chart": "Trend chart unavailable: no months with data in the requested period.",
        "g_yoy": "YoY (last 12M vs previous 12M)", "g_cagr": "3Y CAGR", "g_3m": "Last 3M vs previous 3M",
        "g_prev3m": "Previous 3M vs the 3M before", "g_accel": "Acceleration",
        "g_pop": "Requested period vs previous equivalent period", "pp": "pp",
        "growth_note": "These are historical measurements, not forecasts. A growth chart is planned for a later milestone; the Demand chart shows the trend.",
        "peak": "Peak month", "trough": "Trough month", "peak_avg": "Peak / average", "trough_avg": "Trough / average",
        "volatility": "Volatility (coefficient of variation)",
        "basis": "Basis: calendar-month means over {start}..{end} ({n} observation(s) per month).",
        "basis_single": "Basis: calendar-month means over {start}..{end} (a single year, so one unusual month can decide the peak).",
        "penetration": "Wikipedia topic penetration", "affinity": "Topic affinity", "countries": "Country distribution",
        "not_country": "A language edition is not a country: {project} is read wherever that language is read.",
        "source": "Source", "source_value": "Wikimedia Analytics API ({api}), access={access}, agent={agent}",
        "retrieved": "Data retrieved", "generated": "Report generated", "generated_value": "{at} (software {version})",
        "coverage": "Coverage", "missing_data": "Missing data", "resolution_conf": "Topic resolution confidence",
        "unique_avail": "Unique devices available", "country_avail": "Country data available",
        "denominator_avail": "Project-level denominator available", "api_errors": "API errors",
        "quality_level": "Quality level", "yes": "yes", "no": "no", "none": "none",
        "not_computed": "Metrics not computed:", "raw": "Raw responses:",
        "missing_month": "{month}: no pageviews returned (zero views or no data)",
        "supports": "What the data supports", "not_establish": "What the data does NOT establish",
        "validate": "Questions requiring further validation",
        "supports_tail": "These figures describe reader attention to one Wikipedia article in {project}.",
        "ne1": "Revenue, market size (TAM) or willingness to pay: pageviews measure attention, not purchasing.",
        "ne2": "Product-market fit, or that a product on this topic would succeed.",
        "ne3": "Causes of any change: the data shows that traffic moved, not why.",
        "ne4": "Country-level demand: {project} readers are not one country's population.",
        "ne5": "That readers of related articles, or of other language editions, share this trend.",
        "q1": "Does search volume (e.g. Google Trends) show the same direction in this language?",
        "q2": "Is there App Store / Google Play demand for products on this topic in this language?",
        "q3": "What do competitors in this category earn, and how large is the addressable market?",
        "q4": "Will people pay? What do customer interviews and landing-page conversion rates show?",
        "q5": "What would customer acquisition cost, retention and monetization look like?",
        # observations
        "obs_annual": "Annual pageviews ({span}) were {views} (about {monthly} a month).",
        "obs_yoy_up": "Pageviews increased {pct} year over year ({span} vs {prev}).",
        "obs_yoy_down": "Pageviews decreased {pct} year over year ({span} vs {prev}).",
        "obs_yoy_flat": "Pageviews did not change year over year ({span} vs {prev}).",
        "obs_cagr": "Three-year CAGR was {pct} (vs {span}).",
        "obs_3m": "The last 3 months were {pct} against the previous 3 months{tail}.",
        "obs_3m_tail": "; momentum {label}",
        "obs_season": "{peak} had the highest average monthly traffic ({peak_ratio}x the average) and {trough} the lowest ({trough_ratio}x).",
        # labels
        "momentum.accelerating": "accelerating", "momentum.stable": "stable", "momentum.decelerating": "decelerating",
        "level.HIGH": "HIGH", "level.MEDIUM": "MEDIUM", "level.LOW": "LOW",
        "method.exact_title": "exact title", "method.redirect": "redirect", "method.wikidata_id": "Wikidata ID",
        "method.no_wikidata": "article without Wikidata entity", "method.search": "search",
        "status.unsupported": "unsupported", "status.unavailable": "unavailable",
        "status.insufficient_data": "insufficient data", "status.not_implemented": "not implemented",
        "status.api_error": "API error", "na": "n/a",
        # quality reasons
        "qr.coverage": "coverage {pct} is below 98%", "qr.confidence": "topic resolution confidence {value} is below 0.90",
        "qr.short": "requested period is {months} months (under 24: seasonality not repeated)",
        "qr.api": "{n} API error(s)", "qr.ok": "full coverage, confident topic match, at least two years of data",
        # resolution notes
        "note.redirect": "'{query}' redirects to '{title}'.",
        "note.missing": "No article in: {langs} (Wikidata {qid} has no sitelink there).",
        "note.no_wikidata": "'{title}' has no Wikidata entity, so other languages cannot be matched.",
        # reasons for metrics that are not computed
        "reason.unique_devices": "Wikimedia publishes unique devices per project (whole language edition) only, never per article.",
        "reason.country": "Wikimedia publishes country-level pageviews per project (top-by-country), not per article, so a topic's country distribution cannot be measured.",
        "reason.anomalies": "Anomaly detection is planned for a later milestone.",
        "reason.related_topics": "Not computed by `analyze`: run `cluster` to measure related topics.",
        "reason.signals_market_size": "needs complete pageviews for the last 12 months",
        "reason.signals_growth": "needs at least 24 months of pageviews for YoY (48 for the 3-year CAGR)",
        "reason.signals_momentum": "needs the last 6 months of pageviews",
        "reason.signals_stability": "needs at least 2 years of each calendar month to separate seasonality from noise",
        "sig_title": "Decision signals",
        "sig_intro": "Five separate signals, each from one written rule. They are evidence for a human decision: "
                     "they are not combined into a score and are not a recommendation to buy or invest.",
        "sig_col_signal": "Signal", "sig_col_label": "Reading", "sig_col_evidence": "Evidence and rule",
        "sig_name.market_size": "Market size (reader attention)", "sig_name.growth": "Growth",
        "sig_name.momentum": "Momentum", "sig_name.localization": "Localization", "sig_name.stability": "Stability",
        "sig.market_size.very_low": "very low", "sig.market_size.low": "low", "sig.market_size.medium": "medium",
        "sig.market_size.high": "high", "sig.market_size.very_high": "very high",
        "sig.growth.declining": "declining", "sig.growth.stable": "stable", "sig.growth.growing": "growing",
        "sig.growth.strongly_growing": "strongly growing",
        "sig.momentum.decelerating": "decelerating", "sig.momentum.stable": "stable",
        "sig.momentum.accelerating": "accelerating",
        "sig.localization.weak": "weak", "sig.localization.moderate": "moderate", "sig.localization.strong": "strong",
        "sig.stability.stable": "stable", "sig.stability.moderately_seasonal": "moderately seasonal",
        "sig.stability.highly_seasonal": "highly seasonal", "sig.stability.volatile": "volatile",
        "sig_basis.three_year_cagr": "3-year CAGR", "sig_basis.yoy": "YoY",
        "sig_below": "under {upper}", "sig_at_least": "{lower} or more", "sig_between": "{lower} to under {upper}",
        "sigx.market_size": "{views} views in the last 12 months; {label} is {band}. This is absolute: "
                            "larger editions reach more readers.",
        "sigx.growth": "{basis} {value}; {label} is {band} a year.",
        "sigx.growth_edition": "For context, {project} as a whole changed {value} year over year.",
        "sigx.momentum": "Last 3 months {recent} against the 3 before them {previous} ({points} points); "
                         "above +5 points is accelerating, below -5 decelerating, otherwise stable.",
        "sigx.localization": "Affinity {value} (this edition's share of the topic compared with the compared "
                             "editions); {label} is {band}.",
        "sigx.flags": "{n} flagged months out of {months}, in {episodes} separate episodes",
        "sigx.volatile": "{flags}: at least 2 episodes, and at least one per 12 months checked, is volatile.",
        "sigx.stability": "The peak month, {month}, is {ratio}x the average month; {flags}. From {moderate}x the "
                          "topic is moderately seasonal, from {high}x highly seasonal.",
        "sig_missing": "not computed ({reason})",
        "pf_title": "Portfolio Report: {name}",
        "pf_meta": "Topics: {topics} · editions: {editions} · period {start} to {end} · generated {generated} · "
                   "source: Wikimedia Analytics API",
        "p1": "1. Summary", "p2": "2. Portfolio Matrix", "p3": "3. Decision Signals", "p4": "4. Filters and Excluded Rows",
        "p5": "5. Topic Definitions", "p6": "6. Data Quality", "p7": "7. Business Implications",
        "pf_matrix_intro": "One row per topic and edition, in the order given. Share and affinity are measured within "
                           "each topic, across these editions. Rows are not sorted by any KPI, because that order "
                           "would read as a ranking.",
        "pf_split": "Quadrant split: growth above 0% year over year; demand at or above the median of all measured "
                    "pairs ({threshold} views), taken before filters.",
        "pf_col_topic": "Topic", "pf_col_category": "Category", "pf_col_reason": "Reason",
        "pf_col_articles": "Articles",
        "pf_filters_none": "No filters: every measured pair is shown.",
        "pf_filters": "Filters applied: {filters}.",
        "pf_f_min_views": "at least {n} views in the last 12 months",
        "pf_f_min_growth": "year-over-year change of at least {pct}",
        "pf_f_categories": "categories {names}",
        "pf_excluded_intro": "Rows hidden from the matrix and the chart (they stay in portfolio.json):",
        "pf_no_excluded": "No rows are hidden.",
        "pf_ex.min_views": "fewer views in the last 12 months than the minimum",
        "pf_ex.min_growth": "year-over-year change below the minimum, or no year-over-year figure",
        "pf_ex.category": "category not selected",
        "pf_ex.status.no_article": "no article about this concept in this edition",
        "pf_ex.status.no_data": "the article has no pageview data",
        "pf_ex.status.needs_review": "ambiguous topic: several concepts match; rerun with an exact title or Wikidata ID",
        "pf_ex.status.not_found": "topic not found",
        "pf_ex.status.api_error": "API error",
        "pf_ex.status.ok": "incomplete data for the last 12 months",
        "pf_country": "Country filtering is not available: Wikimedia does not publish per-article pageviews by country.",
        "pf_ne_rank": "That one topic or edition is a better market than another: the quadrants describe Wikipedia "
                      "reading only.",
        "pf_obs_none": "No topic and edition pair is left after the filters: see section 4.",
        "pf_obs_count": "{n} topic and edition pairs are shown, across {topics} topics and {editions} editions.",
        "pf_obs_top": "{label} had the most pageviews: {views} in the last 12 months.",
        "pf_obs_all_declined": "Every shown pair with a year-over-year figure ({n}) declined year over year.",
        "pf_obs_more": " and others",
        "pf_obs_grew": "{n} of {total} shown pairs grew year over year: {names}.",
        "pf_chart_title": "Portfolio: demand and growth (descriptive quadrants)",
        "pf_legend_topics": "Topic (colour)", "pf_legend_editions": "Edition (shape)",
        "pf_alt": "Portfolio matrix",
        "sig_rules": "Rules: market size by views in the last 12 months (very low under 12,000, low under 60,000, "
                     "medium under 300,000, high under 1,500,000); growth by the 3-year CAGR (declining under -3%, "
                     "stable under +3%, growing under +15%); momentum by ±5 points of acceleration; localization by "
                     "affinity (weak under 0.80, strong from 1.25); stability by anomaly episodes, then the seasonal "
                     "peak (moderately seasonal from 1.12x, highly from 1.30x). Each edition's own report explains "
                     "its readings with the numbers.",
        "reason.insufficient": "some months needed for this metric have no data",
        "reason.season_months": "not every calendar month has data in the requested period",
        # --- language comparison (compare) ---
        "cmp_title": "Language Comparison Report: {topic}",
        "cmp_meta": "Editions: {editions} · period {start} to {end} · generated {generated} · source: Wikimedia Analytics API",
        "c1": "1. Summary", "c2": "2. Topic Definition", "c3": "3. Language Opportunity", "c4": "4. Opportunity Matrix",
        "c5": "5. Localization", "c6": "6. Definitions", "c7": "7. Data Quality", "c8": "8. Business Implications",
        "col_edition": "Edition", "col_article": "Article", "col_views": "Views (12M)", "col_yoy": "YoY",
        "col_cagr": "3Y CAGR", "col_3m": "3M", "col_unique": "Unique devices", "col_share": "Topic share",
        "col_pen": "Penetration (per M)", "col_aff": "Affinity", "col_quadrant": "Quadrant", "col_quality": "Quality",
        "col_page": "Page ID", "col_coverage": "Coverage", "col_status": "Status",
        "row.no_article": "no article", "row.no_data": "no data",
        "quadrant.investigate": "investigate", "quadrant.explore": "explore",
        "quadrant.established": "established", "quadrant.watch": "watch",
        "qdesc.investigate": "growing and above-median demand",
        "qdesc.explore": "growing, below-median demand",
        "qdesc.established": "not growing, above-median demand",
        "qdesc.watch": "not growing, below-median demand",
        "matrix_intro": "Each edition is a point: historical growth (YoY) across, absolute demand (views in the last 12 months, log scale) up.",
        "matrix_split": "Splits: growth above 0% YoY; demand at or above the median of the compared editions ({threshold} views). The split is relative to this set of editions.",
        "matrix_labels": "Quadrant names are descriptive labels, not investment recommendations.",
        "matrix_alt": "Opportunity matrix", "pen_alt": "Topic penetration over time",
        "pen_intro": "Topic penetration: the topic's views per million views of its edition, month by month.",
        "missing_langs": "No article about this concept in: {langs}.",
        "def_share": "Topic share: an edition's topic views / topic views across the compared editions (last 12 months).",
        "def_pen": "Wikipedia topic penetration: topic views / all views of that edition (last 12 months), shown per million views. Not market penetration.",
        "def_aff": "Topic affinity: (topic views / edition views) / (topic views / edition views across the compared editions). 1.0 means the same share of attention as the compared set; it is this system's own measure, relative to the editions compared, not an official Wikimedia metric.",
        "def_unique": "Unique devices: Wikimedia publishes them per edition only, never per article, so the column is always n/a.",
        "def_country": "Country distribution: Wikimedia publishes country data per edition, not per article, so it cannot be measured for a topic.",
        "notes": "Notes",
        "cmp_ne_country": "A language edition is not a country: readers of {project} live in many countries.",
        "cmp_ne_rank": "That the order of editions reflects market attractiveness: it reflects Wikipedia reading only.",
        "cmp_obs_views": "{lang} had the most pageviews: {views} in the last 12 months ({share} of the topic's views across the compared editions).",
        "cmp_obs_penetration": "The topic took the largest share of its edition's traffic in {lang}: {value} views per million.",
        "cmp_obs_affinity": "The highest topic affinity was in {lang}: {value}× the compared average.",
        "cmp_obs_growth": "Year-over-year change ranged from {low} ({low_lang}) to {high} ({high_lang}).",
        "cmp_obs_missing": "No article about this concept in: {langs}.",
        "per_million_value": "{value} per million edition views",
        "reason.only_in_comparison": "Only defined across several editions: run `compare` with the languages to compare.",
        "reason.penetration_unavailable": "The edition-wide pageview totals could not be retrieved.",
        "chart_matrix_x": "YoY change in pageviews", "chart_matrix_y": "Pageviews, last 12 months (log scale)",
        "chart_matrix_title": "Opportunity matrix: {topic} (descriptive quadrants)",
        "chart_pen_title": "Topic penetration: views per million edition views, 3-month average",
        # --- anomalies ---
        "obs_anomalies": "{n} potential anomalies flagged; the largest was {pct} against its baseline in {month} (cause unknown).",
        "obs_anomalies_one": "1 potential anomaly flagged: {pct} against its baseline in {month} (cause unknown).",
        "obs_rule6": "With the flagged months replaced by their expected values, the year-over-year change would be {pct}.",
        "an_intro": "Months far from their expected value. Expected = the median of the 6 months before and after, times the usual seasonal factor for that calendar month (from other years), so recurring seasonal peaks are not flagged.",
        "an_rule": "Flagged when the robust z-score exceeds {z} and the gap is at least {min_change}. Causes are not investigated.",
        "an_none": "No anomalies: {n} months checked.",
        "an_line": "Potential anomaly detected: {month} pageviews were {pct} {direction} baseline. Cause: unknown.",
        "an_above": "above", "an_below": "below",
        "an_date": "Month", "an_actual": "Actual", "an_expected": "Expected (baseline)", "an_change": "Change vs baseline",
        "an_z": "Robust z", "an_severity": "Severity",
        "severity.low": "low", "severity.medium": "medium", "severity.high": "high",
        "an_provisional": "provisional (recent month: the next data can change it)",
        "an_no_season": "Too few years for seasonal factors: the baseline is not seasonally adjusted.",
        "an_yoy_excl": "YoY with flagged months replaced by their expected values: {pct} (reported YoY: {yoy}).",
        "chart_anomaly": "potential anomaly", "col_anomalies": "Anomalies",
        # --- topic ecosystem (cluster) ---
        "eco_intro": "Related concepts found through typed Wikidata relations (broader, narrower, facets) and, separately, through text similarity. Each is an adjacent interest signal: where readers' attention sits around the topic, not a claim that it is a commercially adjacent product.",
        "eco_edition": "Share-adjusted YoY compares each topic with its whole edition, whose views changed {pct} year over year.",
        "eco_not_computed": "Not computed by `analyze`: run `cluster` to measure related topics.",
        "col_topic": "Topic", "col_relationship": "Relationship", "col_relsize": "Size vs topic", "col_adj_yoy": "Share-adjusted YoY", "col_signal": "Signal",
        "rel.broader": "broader", "rel.narrower": "narrower", "rel.facet_of": "facet of", "rel.has_facet": "has facet", "rel.similar_content": "similar text",
        "signal.larger_category": "larger category", "signal.emerging_category": "emerging category", "signal.declining_category": "declining category",
        "signal.adjacent_opportunity": "adjacent opportunity", "signal.adjacent_interest": "adjacent interest", "signal.too_small": "too small to judge",
        "sdesc.larger_category": "a broader concept with more views than the topic",
        "sdesc.emerging_category": "gaining at least 10% relative to its edition",
        "sdesc.declining_category": "losing at least 10% relative to its edition",
        "sdesc.adjacent_opportunity": "at least as many views as the topic; its change is within 10 points of its edition's (it may still be falling)",
        "sdesc.adjacent_interest": "fewer views than the topic; its change is within 10 points of its edition's (it may still be falling)",
        "sdesc.too_small": "under 100 views a month: any change is mostly noise",
        "eco_signals": "Signals (descriptive, not recommendations):",
        "conc_title": "Interest concentration",
        "conc_intro": "Share of the cluster's views held by its largest articles. The cluster is the topic plus its typed relations ({n} articles); text-similar articles are left out.",
        "conc_top": "Top {k}", "conc_short": "n/a (fewer than {k} articles)",
        "conc_largest": "Largest article: {title} ({pct} of the cluster's views).",
        "conc_meaning": "High concentration means attention sits on a few concepts; low means it is spread across many. Neither is good or bad in itself.",
        "eco_note_skipped": "{n} {relationship} concept(s) have no article in this edition and were skipped.",
        "eco_note_capped": "{n} related concepts were found; the first {cap} were measured (typed relations before text similarity).",
        "eco_note_similar": "Text similarity can include unrelated articles that share vocabulary.",
        "eco_note_no_qid": "The topic has no Wikidata entity, so only text-similar articles were considered.",
        "chart_eco_title": "Related topics: {topic} (adjacent interest signals)",
        "chart_eco_x": "Share-adjusted YoY (vs the whole edition)", "chart_eco_y": "Pageviews, last 12 months (log scale)",
        "chart_eco_focal": "the topic", "chart_eco_typed": "typed relation", "chart_eco_similar": "similar text",
        "eco_alt": "Related topics",
    },
    "uk": {
        "title": "Звіт ринкової аналітики на основі Вікіпедії",
        "s1": "1. Картка для ухвалення рішення", "s2": "2. Визначення теми", "s3": "3. Попит", "s4": "4. Зростання",
        "s5": "5. Сезонність", "s6": "6. Можливості за мовами", "s7": "7. Локалізація", "s8": "8. Екосистема теми",
        "s9": "9. Аномалії", "s10": "10. Якість даних", "s11": "11. Висновки для бізнесу",
        "topic": "Тема", "edition": "Мовний розділ", "edition_note": "мовний розділ, а не країна",
        "period": "Період аналізу", "period_value": "з {start} по {end}",
        "annual": "Перегляди за рік (останні 12 місяців)", "monthly": "Середнє на місяць", "daily": "Середнє на день",
        "requested_views": "Перегляди за вибраний період", "unique": "Унікальні пристрої",
        "per_device": "Переглядів на унікальний пристрій", "yoy": "Рік до року", "cagr": "CAGR за 3 роки",
        "momentum": "Імпульс", "seasonality": "Сезонність", "season_value": "пік — {peak}, спад — {trough}",
        "localization": "Показники локалізації", "quality": "Якість даних",
        "observations": "Ключові спостереження", "no_observations": "Жодне спостереження не вдалося обчислити: див. «Якість даних».",
        "canonical": "Канонічна тема", "wikidata": "Ідентифікатор Wikidata", "no_wikidata": "н/д (немає сутності у Wikidata)",
        "article": "Використана стаття", "article_value": "{title} (ID сторінки {id})", "method": "Спосіб зіставлення",
        "confidence": "Впевненість зіставлення", "mappings": "Відповідники в мовах", "related": "Пов'язані теми",
        "kpi": "Показник", "value": "Значення", "metric": "Показник", "status": "Статус", "reason": "Причина",
        "chart_alt": "Перегляди за місяць", "no_chart": "Графік тренду недоступний: за вибраний період немає місяців із даними.",
        "g_yoy": "Рік до року (останні 12 міс. проти попередніх 12)", "g_cagr": "CAGR за 3 роки",
        "g_3m": "Останні 3 міс. проти попередніх 3", "g_prev3m": "Попередні 3 міс. проти 3 міс. перед ними",
        "g_accel": "Прискорення", "g_pop": "Вибраний період проти попереднього такого самого періоду", "pp": "в. п.",
        "growth_note": "Це історичні вимірювання, а не прогнози. Графік зростання заплановано на наступний етап; тренд видно на графіку в розділі «Попит».",
        "peak": "Місяць піку", "trough": "Місяць спаду", "peak_avg": "Пік / середнє", "trough_avg": "Спад / середнє",
        "volatility": "Волатильність (коефіцієнт варіації)",
        "basis": "Основа: середні значення за календарними місяцями за {start}..{end} (спостережень на місяць: {n}).",
        "basis_single": "Основа: середні значення за календарними місяцями за {start}..{end} (лише один рік, тож один незвичний місяць може визначити пік).",
        "penetration": "Проникнення теми у Вікіпедії", "affinity": "Спорідненість теми", "countries": "Розподіл за країнами",
        "not_country": "Мовний розділ — це не країна: {project} читають усюди, де читають цією мовою.",
        "source": "Джерело", "source_value": "Wikimedia Analytics API ({api}), access={access}, agent={agent}",
        "retrieved": "Дані отримано", "generated": "Звіт створено", "generated_value": "{at} (версія програми {version})",
        "coverage": "Покриття", "missing_data": "Відсутні дані", "resolution_conf": "Впевненість зіставлення теми",
        "unique_avail": "Дані про унікальні пристрої", "country_avail": "Дані за країнами",
        "denominator_avail": "Загальний трафік розділу", "api_errors": "Помилки API",
        "quality_level": "Рівень якості", "yes": "так", "no": "ні", "none": "немає",
        "not_computed": "Показники, які не обчислено:", "raw": "Необроблені відповіді:",
        "missing_month": "{month}: переглядів не повернуто (нуль переглядів або немає даних)",
        "supports": "Що дані підтверджують", "not_establish": "Чого дані НЕ встановлюють",
        "validate": "Питання, які потребують додаткової перевірки",
        "supports_tail": "Ці цифри описують увагу читачів до однієї статті Вікіпедії в розділі {project}.",
        "ne1": "Виручку, розмір ринку (TAM) чи готовність платити: перегляди вимірюють увагу, а не купівлі.",
        "ne2": "Відповідність продукту ринку чи те, що продукт на цю тему буде успішним.",
        "ne3": "Причини змін: дані показують, що трафік змінився, але не чому.",
        "ne4": "Попит на рівні країни: читачі {project} — це не населення однієї країни.",
        "ne5": "Що читачі пов'язаних статей чи інших мовних розділів мають такий самий тренд.",
        "q1": "Чи показує обсяг пошукових запитів (напр., Google Trends) той самий напрям цією мовою?",
        "q2": "Чи є попит у App Store / Google Play на продукти з цієї теми цією мовою?",
        "q3": "Скільки заробляють конкуренти в цій категорії та який розмір доступного ринку?",
        "q4": "Чи готові люди платити? Що показують інтерв'ю з клієнтами та конверсія лендингів?",
        "q5": "Якими будуть вартість залучення клієнта, утримання та монетизація?",
        "obs_annual": "Перегляди за рік ({span}) становили {views} (приблизно {monthly} на місяць).",
        "obs_yoy_up": "Перегляди зросли на {pct} рік до року ({span} проти {prev}).",
        "obs_yoy_down": "Перегляди зменшилися на {pct} рік до року ({span} проти {prev}).",
        "obs_yoy_flat": "Перегляди не змінилися рік до року ({span} проти {prev}).",
        "obs_cagr": "CAGR за три роки становив {pct} (порівняно з {span}).",
        "obs_3m": "Останні 3 місяці: {pct} порівняно з попередніми 3 місяцями{tail}.",
        "obs_3m_tail": "; імпульс {label}",
        "obs_season": "Найвищий середній місячний трафік — у {peak} ({peak_ratio}× середнього), найнижчий — у {trough} ({trough_ratio}×).",
        "momentum.accelerating": "прискорюється", "momentum.stable": "стабільний", "momentum.decelerating": "сповільнюється",
        "level.HIGH": "ВИСОКА", "level.MEDIUM": "СЕРЕДНЯ", "level.LOW": "НИЗЬКА",
        "method.exact_title": "точна назва", "method.redirect": "перенаправлення", "method.wikidata_id": "ідентифікатор Wikidata",
        "method.no_wikidata": "стаття без сутності у Wikidata", "method.search": "пошук",
        "status.unsupported": "не підтримується", "status.unavailable": "недоступно",
        "status.insufficient_data": "недостатньо даних", "status.not_implemented": "ще не реалізовано",
        "status.api_error": "помилка API", "na": "н/д",
        "qr.coverage": "покриття {pct} нижче 98%", "qr.confidence": "впевненість зіставлення теми {value} нижче 0,90",
        "qr.short": "вибраний період — {months} міс. (менше 24: сезонність не повторюється)",
        "qr.api": "помилок API: {n}", "qr.ok": "повне покриття, надійне зіставлення теми, щонайменше два роки даних",
        "note.redirect": "«{query}» перенаправляє на «{title}».",
        "note.missing": "Немає статті в розділах: {langs} (у Wikidata {qid} немає там посилання).",
        "note.no_wikidata": "«{title}» не має сутності у Wikidata, тому інші мови зіставити неможливо.",
        "reason.unique_devices": "Wikimedia публікує унікальні пристрої лише для всього мовного розділу, а не для окремої статті.",
        "reason.country": "Wikimedia публікує перегляди за країнами лише для всього розділу (top-by-country), а не для статті, тому розподіл теми за країнами виміряти неможливо.",
        "reason.anomalies": "Виявлення аномалій заплановано на наступний етап.",
        "reason.related_topics": "Команда `analyze` цього не обчислює: запустіть `cluster`, щоб виміряти пов'язані теми.",
        "reason.signals_market_size": "потрібні повні дані про перегляди за останні 12 місяців",
        "reason.signals_growth": "потрібно щонайменше 24 місяці переглядів для зміни рік до року (48 для CAGR за 3 роки)",
        "reason.signals_momentum": "потрібні перегляди за останні 6 місяців",
        "reason.signals_stability": "потрібно щонайменше 2 роки даних для кожного календарного місяця, щоб відрізнити сезонність від шуму",
        "sig_title": "Сигнали для ухвалення рішень",
        "sig_intro": "П'ять окремих сигналів, кожен за одним письмовим правилом. Це докази для рішення людини: "
                     "їх не зводять в одну оцінку, і вони не є порадою купувати чи інвестувати.",
        "sig_col_signal": "Сигнал", "sig_col_label": "Значення", "sig_col_evidence": "Дані та правило",
        "sig_name.market_size": "Розмір ринку (увага читачів)", "sig_name.growth": "Зростання",
        "sig_name.momentum": "Динаміка", "sig_name.localization": "Локалізація", "sig_name.stability": "Стабільність",
        "sig.market_size.very_low": "дуже малий", "sig.market_size.low": "малий", "sig.market_size.medium": "середній",
        "sig.market_size.high": "великий", "sig.market_size.very_high": "дуже великий",
        "sig.growth.declining": "спад", "sig.growth.stable": "стабільно", "sig.growth.growing": "зростання",
        "sig.growth.strongly_growing": "сильне зростання",
        "sig.momentum.decelerating": "сповільнюється", "sig.momentum.stable": "стабільна",
        "sig.momentum.accelerating": "прискорюється",
        "sig.localization.weak": "слабка", "sig.localization.moderate": "помірна", "sig.localization.strong": "сильна",
        "sig.stability.stable": "стабільна", "sig.stability.moderately_seasonal": "помірно сезонна",
        "sig.stability.highly_seasonal": "сильно сезонна", "sig.stability.volatile": "нестабільна",
        "sig_basis.three_year_cagr": "CAGR за 3 роки", "sig_basis.yoy": "Зміна рік до року",
        "sig_below": "менше {upper}", "sig_at_least": "{lower} або більше", "sig_between": "від {lower} до менше {upper}",
        "sigx.market_size": "{views} переглядів за останні 12 місяців; «{label}» означає {band}. Це абсолютна "
                            "величина: більші мовні розділи мають більше читачів.",
        "sigx.growth": "{basis}: {value}; «{label}» означає {band} на рік.",
        "sigx.growth_edition": "Для порівняння: весь {project} змінився на {value} рік до року.",
        "sigx.momentum": "Останні 3 місяці {recent} проти 3 попередніх {previous} ({points} п. п.); "
                         "понад +5 п. п. означає прискорення, нижче −5 — сповільнення, інакше динаміка стабільна.",
        "sigx.localization": "Спорідненість {value} (частка теми в цьому розділі порівняно з іншими розділами); "
                             "«{label}» означає {band}.",
        "sigx.flags": "позначених місяців: {n} із {months}, окремих епізодів: {episodes}",
        "sigx.volatile": "{flags}: щонайменше 2 епізоди і не менше одного на кожні 12 перевірених місяців означає нестабільність.",
        "sigx.stability": "Пік — {month}: {ratio}× від середнього місяця; {flags}. Від {moderate}× тема помірно "
                          "сезонна, від {high}× — сильно сезонна.",
        "sig_missing": "не обчислено ({reason})",
        "pf_title": "Звіт портфеля: {name}",
        "pf_meta": "Теми: {topics} · розділи: {editions} · період з {start} по {end} · створено {generated} · "
                   "джерело: Wikimedia Analytics API",
        "p1": "1. Підсумок", "p2": "2. Матриця портфеля", "p3": "3. Сигнали для ухвалення рішень",
        "p4": "4. Фільтри та приховані рядки", "p5": "5. Визначення тем", "p6": "6. Якість даних",
        "p7": "7. Висновки для бізнесу",
        "pf_matrix_intro": "Один рядок на кожну пару тема–розділ у вказаному порядку. Частку та спорідненість "
                           "виміряно в межах кожної теми серед цих розділів. Рядки не впорядковано за жодним "
                           "показником, бо такий порядок читався б як рейтинг.",
        "pf_split": "Межі квадрантів: зростання вище 0% рік до року; попит на рівні медіани всіх виміряних пар "
                    "або вище ({threshold} переглядів), до застосування фільтрів.",
        "pf_col_topic": "Тема", "pf_col_category": "Категорія", "pf_col_reason": "Причина",
        "pf_col_articles": "Статті",
        "pf_filters_none": "Фільтрів немає: показано всі виміряні пари.",
        "pf_filters": "Застосовані фільтри: {filters}.",
        "pf_f_min_views": "щонайменше {n} переглядів за останні 12 місяців",
        "pf_f_min_growth": "зміна рік до року щонайменше {pct}",
        "pf_f_categories": "категорії {names}",
        "pf_excluded_intro": "Рядки, приховані з матриці та графіка (вони залишаються в portfolio.json):",
        "pf_no_excluded": "Прихованих рядків немає.",
        "pf_ex.min_views": "менше переглядів за останні 12 місяців, ніж мінімум",
        "pf_ex.min_growth": "зміна рік до року нижча за мінімум або відсутня",
        "pf_ex.category": "категорію не вибрано",
        "pf_ex.status.no_article": "у цьому розділі немає статті про це поняття",
        "pf_ex.status.no_data": "стаття не має даних про перегляди",
        "pf_ex.status.needs_review": "неоднозначна тема: підходять кілька понять; повторіть із точною назвою чи ID Wikidata",
        "pf_ex.status.not_found": "тему не знайдено",
        "pf_ex.status.api_error": "помилка API",
        "pf_ex.status.ok": "неповні дані за останні 12 місяців",
        "pf_country": "Фільтр за країнами недоступний: Wikimedia не публікує перегляди окремих статей за країнами.",
        "pf_ne_rank": "Що одна тема чи розділ є кращим ринком, ніж інші: квадранти описують лише читання Вікіпедії.",
        "pf_obs_none": "Після фільтрів не залишилося жодної пари тема–розділ: див. розділ 4.",
        "pf_obs_count": "Показано пар тема–розділ: {n}; тем: {topics}; розділів: {editions}.",
        "pf_obs_top": "Найбільше переглядів мала пара {label}: {views} за останні 12 місяців.",
        "pf_obs_all_declined": "Усі показані пари з даними рік до року ({n}) скоротилися рік до року.",
        "pf_obs_more": " та інші",
        "pf_obs_grew": "Зросли рік до року {n} із {total} показаних пар: {names}.",
        "pf_chart_title": "Портфель: попит і зростання (описові квадранти)",
        "pf_legend_topics": "Тема (колір)", "pf_legend_editions": "Розділ (форма)",
        "pf_alt": "Матриця портфеля",
        "sig_rules": "Правила: розмір ринку — за переглядами за останні 12 місяців (дуже малий — менше 12 000, "
                     "малий — менше 60 000, середній — менше 300 000, великий — менше 1 500 000); зростання — за CAGR "
                     "за 3 роки (спад — менше −3%, стабільно — менше +3%, зростання — менше +15%); динаміка — за "
                     "прискоренням ±5 п. п.; локалізація — за спорідненістю (слабка — менше 0,80, сильна — від 1,25); "
                     "стабільність — за епізодами аномалій, далі за сезонним піком (помірно сезонна — від 1,12×, "
                     "сильно — від 1,30×). Звіт кожного розділу пояснює свої значення з числами.",
        "reason.insufficient": "для цього показника бракує даних за деякі місяці",
        "reason.season_months": "не всі календарні місяці мають дані у вибраному періоді",
        "cmp_title": "Звіт порівняння мов: {topic}",
        "cmp_meta": "Розділи: {editions} · період з {start} по {end} · створено {generated} · джерело: Wikimedia Analytics API",
        "c1": "1. Підсумок", "c2": "2. Визначення теми", "c3": "3. Можливості за мовами", "c4": "4. Матриця можливостей",
        "c5": "5. Локалізація", "c6": "6. Визначення", "c7": "7. Якість даних", "c8": "8. Висновки для бізнесу",
        "col_edition": "Розділ", "col_article": "Стаття", "col_views": "Перегляди (12 міс.)", "col_yoy": "Рік до року",
        "col_cagr": "CAGR 3 р.", "col_3m": "3 міс.", "col_unique": "Унікальні пристрої", "col_share": "Частка теми",
        "col_pen": "Проникнення (на млн)", "col_aff": "Спорідненість", "col_quadrant": "Квадрант", "col_quality": "Якість",
        "col_page": "ID сторінки", "col_coverage": "Покриття", "col_status": "Статус",
        "row.no_article": "немає статті", "row.no_data": "немає даних",
        "quadrant.investigate": "дослідити", "quadrant.explore": "розвідати",
        "quadrant.established": "усталений", "quadrant.watch": "спостерігати",
        "qdesc.investigate": "зростає, попит вище медіани",
        "qdesc.explore": "зростає, попит нижче медіани",
        "qdesc.established": "не зростає, попит вище медіани",
        "qdesc.watch": "не зростає, попит нижче медіани",
        "matrix_intro": "Кожен розділ — точка: по горизонталі історичне зростання (рік до року), по вертикалі абсолютний попит (перегляди за останні 12 місяців, логарифмічна шкала).",
        "matrix_split": "Межі: зростання вище 0% рік до року; попит на рівні медіани порівнюваних розділів або вище ({threshold} переглядів). Межа відносна до цього набору розділів.",
        "matrix_labels": "Назви квадрантів — описові мітки, а не інвестиційні рекомендації.",
        "matrix_alt": "Матриця можливостей", "pen_alt": "Проникнення теми в часі",
        "pen_intro": "Проникнення теми: перегляди теми на мільйон переглядів її розділу, помісячно.",
        "missing_langs": "Немає статті про це поняття в розділах: {langs}.",
        "def_share": "Частка теми: перегляди теми в розділі / перегляди теми в усіх порівнюваних розділах (останні 12 місяців).",
        "def_pen": "Проникнення теми у Вікіпедії: перегляди теми / усі перегляди розділу (останні 12 місяців), показано на мільйон переглядів. Це не проникнення на ринок.",
        "def_aff": "Спорідненість теми: (перегляди теми / перегляди розділу) / (те саме для всіх порівнюваних розділів). 1,0 — така сама частка уваги, як у порівнюваному наборі; це власний показник цієї системи, відносний до порівнюваних розділів, а не офіційна метрика Wikimedia.",
        "def_unique": "Унікальні пристрої: Wikimedia публікує їх лише для всього розділу, а не для статті, тому стовпчик завжди н/д.",
        "def_country": "Розподіл за країнами: Wikimedia публікує дані за країнами для розділу, а не для статті, тому для теми їх виміряти неможливо.",
        "notes": "Примітки",
        "cmp_ne_country": "Мовний розділ — це не країна: читачі {project} живуть у багатьох країнах.",
        "cmp_ne_rank": "Що порядок розділів відображає привабливість ринку: він відображає лише читання Вікіпедії.",
        "cmp_obs_views": "Найбільше переглядів у {lang}: {views} за останні 12 місяців ({share} переглядів теми в порівнюваних розділах).",
        "cmp_obs_penetration": "Найбільшу частку трафіку свого розділу тема займає в {lang}: {value} переглядів на мільйон.",
        "cmp_obs_affinity": "Найвища спорідненість теми — у {lang}: {value}× середнього по порівнюваних розділах.",
        "cmp_obs_growth": "Зміна рік до року — від {low} ({low_lang}) до {high} ({high_lang}).",
        "cmp_obs_missing": "Немає статті про це поняття в розділах: {langs}.",
        "per_million_value": "{value} на мільйон переглядів розділу",
        "reason.only_in_comparison": "Визначено лише для кількох розділів: запустіть `compare` з мовами для порівняння.",
        "reason.penetration_unavailable": "Не вдалося отримати загальну кількість переглядів розділу.",
        "chart_matrix_x": "Зміна переглядів рік до року", "chart_matrix_y": "Перегляди за останні 12 місяців (лог. шкала)",
        "chart_matrix_title": "Матриця можливостей: {topic} (описові квадранти)",
        "chart_pen_title": "Проникнення теми: переглядів на мільйон переглядів розділу, середнє за 3 місяці",
        "obs_anomalies": "Позначено можливих аномалій: {n}; найбільша — {pct} відносно базового рівня у {month} (причина невідома).",
        "obs_anomalies_one": "Позначено одну можливу аномалію: {pct} відносно базового рівня у {month} (причина невідома).",
        "obs_rule6": "Якщо замінити позначені місяці очікуваними значеннями, зміна рік до року становила б {pct}.",
        "an_intro": "Місяці, що сильно відхиляються від очікуваного значення. Очікуване = медіана 6 місяців до і 6 після, помножена на звичайний сезонний коефіцієнт цього календарного місяця (з інших років), тож щорічні сезонні піки не позначаються.",
        "an_rule": "Позначається, коли робастний z-показник перевищує {z}, а відхилення становить щонайменше {min_change}. Причини не досліджуються.",
        "an_none": "Аномалій немає: перевірено місяців — {n}.",
        "an_line": "Можлива аномалія: у {month} перегляди були на {pct} {direction} базового рівня. Причина: невідома.",
        "an_above": "вище", "an_below": "нижче",
        "an_date": "Місяць", "an_actual": "Фактично", "an_expected": "Очікувано (базовий рівень)", "an_change": "Відхилення від базового рівня",
        "an_z": "Робастний z", "an_severity": "Серйозність",
        "severity.low": "низька", "severity.medium": "середня", "severity.high": "висока",
        "an_provisional": "попередньо (нещодавній місяць: наступні дані можуть це змінити)",
        "an_no_season": "Замало років для сезонних коефіцієнтів: базовий рівень без сезонного коригування.",
        "an_yoy_excl": "Рік до року, якщо замінити позначені місяці очікуваними значеннями: {pct} (показаний рік до року: {yoy}).",
        "chart_anomaly": "можлива аномалія", "col_anomalies": "Аномалії",
        "eco_intro": "Пов'язані поняття знайдено через типізовані зв'язки Wikidata (ширше, вужче, аспекти) і окремо — через схожість тексту. Кожне з них — сигнал суміжного інтересу: де зосереджена увага читачів навколо теми, а не твердження, що це комерційно суміжний продукт.",
        "eco_edition": "Рік до року з поправкою на розділ порівнює кожну тему з усім розділом, перегляди якого змінилися на {pct} рік до року.",
        "eco_not_computed": "Команда `analyze` цього не обчислює: запустіть `cluster`, щоб виміряти пов'язані теми.",
        "col_topic": "Тема", "col_relationship": "Зв'язок", "col_relsize": "Розмір відносно теми", "col_adj_yoy": "Рік до року з поправкою", "col_signal": "Сигнал",
        "rel.broader": "ширше", "rel.narrower": "вужче", "rel.facet_of": "аспект", "rel.has_facet": "має аспект", "rel.similar_content": "схожий текст",
        "signal.larger_category": "ширша категорія", "signal.emerging_category": "категорія, що зростає", "signal.declining_category": "категорія, що спадає",
        "signal.adjacent_opportunity": "суміжна можливість", "signal.adjacent_interest": "суміжний інтерес", "signal.too_small": "замало даних",
        "sdesc.larger_category": "ширше поняття з більшою кількістю переглядів, ніж тема",
        "sdesc.emerging_category": "зростає щонайменше на 10% відносно свого розділу",
        "sdesc.declining_category": "втрачає щонайменше 10% відносно свого розділу",
        "sdesc.adjacent_opportunity": "щонайменше стільки переглядів, як тема; її зміна в межах 10 пунктів від зміни розділу (може й надалі спадати)",
        "sdesc.adjacent_interest": "менше переглядів, ніж тема; її зміна в межах 10 пунктів від зміни розділу (може й надалі спадати)",
        "sdesc.too_small": "менше 100 переглядів на місяць: будь-яка зміна здебільшого є шумом",
        "eco_signals": "Сигнали (описові, не рекомендації):",
        "conc_title": "Концентрація інтересу",
        "conc_intro": "Частка переглядів кластера, яку мають найбільші статті. Кластер — це тема та її типізовані зв'язки ({n} статей); статті зі схожим текстом не враховано.",
        "conc_top": "Топ-{k}", "conc_short": "н/д (менше {k} статей)",
        "conc_largest": "Найбільша стаття: {title} ({pct} переглядів кластера).",
        "conc_meaning": "Висока концентрація означає, що увага зосереджена на кількох поняттях; низька — що вона розподілена між багатьма. Сама по собі жодна не є ні доброю, ні поганою.",
        "eco_note_skipped": "Понять ({relationship}) без статті в цьому розділі, які пропущено: {n}.",
        "eco_note_capped": "Знайдено пов'язаних понять: {n}; виміряно перші {cap} (типізовані зв'язки раніше за схожість тексту).",
        "eco_note_similar": "Схожість тексту може включати непов'язані статті зі спільною лексикою.",
        "eco_note_no_qid": "Тема не має сутності у Wikidata, тож розглянуто лише статті зі схожим текстом.",
        "chart_eco_title": "Пов'язані теми: {topic} (сигнали суміжного інтересу)",
        "chart_eco_x": "Рік до року з поправкою на розділ", "chart_eco_y": "Перегляди за останні 12 місяців (лог. шкала)",
        "chart_eco_focal": "тема", "chart_eco_typed": "типізований зв'язок", "chart_eco_similar": "схожий текст",
        "eco_alt": "Пов'язані теми",
    },
}

# Which catalog reason explains which not-computed metric.
REASON_KEYS = {
    "demand.unique_devices": "reason.unique_devices", "demand.views_per_unique_device": "reason.unique_devices",
    "localization.country_distribution": "reason.country",
    "localization.topic_share": "reason.only_in_comparison", "localization.topic_affinity": "reason.only_in_comparison",
    "ecosystem.related_topics": "reason.related_topics",
    "seasonality.peak_month": "reason.season_months",
    "signals.market_size": "reason.signals_market_size", "signals.growth": "reason.signals_growth",
    "signals.momentum": "reason.signals_momentum", "signals.localization": "reason.only_in_comparison",
    "signals.stability": "reason.signals_stability",
}


class Translator:
    """tr("key", **values) in the report language; English when a key is missing."""

    def __init__(self, lang: str = "en"):
        self.lang = lang if lang in SUPPORTED else "en"

    def __call__(self, key: str, **values: Any) -> str:
        return CATALOG[self.lang].get(key, CATALOG["en"][key]).format(**values)

    def month(self, english_name: str | None, *, in_form: bool = False) -> str | None:
        if not english_name:
            return None
        index = MONTHS["en"].index(english_name)
        return (MONTHS_IN if in_form else MONTHS)[self.lang][index]

    # Numbers: 56,910 and -17.2% in English; 56 910 and −17,2% in Ukrainian.
    def number(self, value: float, decimals: int = 0) -> str:
        text = f"{value:,.{decimals}f}"
        if self.lang == "uk":
            text = text.replace(",", " ").replace(".", ",")
        return text

    def percent(self, fraction: float, signed: bool = True) -> str:
        text = f"{fraction * 100:+.1f}%" if signed else f"{fraction * 100:.1f}%"
        return text.replace(".", ",").replace("-", "−") if self.lang == "uk" else text

    def decimal(self, value: float, decimals: int = 2) -> str:
        text = f"{value:.{decimals}f}"
        return text.replace(".", ",") if self.lang == "uk" else text

    def compact(self, value: float) -> str:
        for threshold, suffix_en, suffix_uk in ((1e9, "B", " млрд"), (1e6, "M", " млн"), (1e3, "K", " тис.")):
            if abs(value) >= threshold:
                return f"{self.decimal(value / threshold, 1)}{suffix_uk if self.lang == 'uk' else suffix_en}"
        return self.number(value)


# ---------------------------------------------------------------------------
# detecting the user's language from their own words
# ---------------------------------------------------------------------------

LATIN_HINTS = {
    "pl": (r"[ąęłśżźćń]", r"\b(czy|jest|nie|oraz|jak)\b"),
    "cs": (r"[ěščřžůý]", r"\b(je|jak|zda|není|pro)\b"),
    "de": (r"[äöüß]", r"\b(und|ist|nicht|wie|der|die|das)\b"),
    "fr": (r"[éèêàçù]", r"\b(est|pour|les|des|une|dans)\b"),
    "es": (r"[ñ¿¡áéíóú]", r"\b(es|para|los|las|una|cómo)\b"),
    "pt": (r"[ãõçáéê]", r"\b(é|para|os|uma|como|não)\b"),
    "it": (r"[àèìòù]", r"\b(è|per|gli|una|come|non)\b"),
}


def detect_language(text: str | None) -> str:
    """Language code of the user's request. May return a code without a translation."""
    if not text or not text.strip():
        return "en"
    cyrillic = len(re.findall(r"[а-яА-ЯіїєґІЇЄҐ]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cyrillic > latin:
        return "uk" if re.search(r"[іїєґІЇЄҐ']", text) else "ru"
    lowered = text.lower()
    scores = {lang: len(re.findall(chars, lowered)) * 2 + len(re.findall(words, lowered))
              for lang, (chars, words) in LATIN_HINTS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else "en"


def resolve_report_language(question: str | None, requested: str = "auto") -> tuple[str, str]:
    """(language the user wrote in, language the report will use)."""
    wanted = detect_language(question) if requested == "auto" else requested.lower()
    return wanted, (wanted if wanted in SUPPORTED else "en")


def placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}
