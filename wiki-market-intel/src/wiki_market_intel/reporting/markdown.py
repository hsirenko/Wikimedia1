"""Markdown report in the fixed order of spec §24, in the report language.

Every section always appears. When a metric is missing, the report shows why
(unsupported, insufficient data, not implemented yet) instead of a blank or a zero.
All wording comes from `i18n.CATALOG`; explanations are rebuilt from the data in the
report language, never copied from the English JSON.
"""

from __future__ import annotations

from jinja2 import Environment, StrictUndefined

from wiki_market_intel.analytics import recommend
from wiki_market_intel.analytics import signals as signal_kpis
from wiki_market_intel.reporting import breakdown
from wiki_market_intel.analytics.summary import observations_from_spans
from wiki_market_intel.i18n import Translator, reason_text
from wiki_market_intel.models.analysis import AnalysisResult
from wiki_market_intel.models.metrics import AnomalyAnalysis

TEMPLATE = """\
# {{ t("title") }}

_{{ t("topic") }}: {{ r.topic.canonical_name or r.metadata.topic }} · {{ t("edition") }}: {{ r.metadata.project }} · {{ t("period") }}: {{ t("period_value", start=r.metadata.period_start, end=r.metadata.period_end) }}_

## {{ t("rec_title") }}

{% if rec_head -%}
**{{ rec_head }}**

{% for line in rec_points -%}
- {{ line }}
{% endfor %}
{{ rec_basis }}

_{{ rec_rule }}_
{%- endif %}

## {{ t("s1") }}

| {{ t("kpi_col_kpi") }} | {{ t("kpi_col_value") }} | {{ t("kpi_col_reading") }} |
|---|---|---|
{% for kpi, value, reading in kpi_rows -%}
| {{ kpi }} | {{ value }} | {{ reading }} |
{% endfor %}
{{ t("sig_intro") }}

### {{ t("observations") }}

{% for o in observations -%}
- {{ o }}
{% else -%}
- {{ t("no_observations") }}
{% endfor %}
## {{ t("s2") }}

| | |
|---|---|
| {{ t("canonical") }} | {{ r.topic.canonical_name or t("na") }} |
| {{ t("wikidata") }} | {{ r.topic.wikidata_id or t("no_wikidata") }} |
| {{ t("article") }} | {{ t("article_value", title=r.topic.article_title, id=r.topic.article_id or t("na")) }} |
| {{ t("method") }} | {{ t("method." ~ r.topic.resolution.method) }} |
| {{ t("confidence") }} | {{ dec(r.topic.resolution_confidence) }} |
| {{ t("mappings") }} | {% for lang, a in r.topic.resolution.articles.items() %}{{ lang }}: {{ a.title }}{% if not loop.last %}, {% endif %}{% endfor %} |
| {{ t("related") }} | {{ missing("ecosystem.related_topics") }} |
{% for n in notes %}
> {{ n }}
{% endfor %}
## {{ t("s3") }}

| {{ t("kpi") }} | {{ t("value") }} |
|---|---:|
| {{ t("annual") }} | {{ num(r.demand.annual_views, "demand.annual_views") }} |
| {{ t("monthly") }} | {{ num(r.demand.monthly_average, "demand.annual_views") }} |
| {{ t("daily") }} | {{ num(r.demand.daily_average, "demand.annual_views") }} |
| {{ t("requested_views") }} | {{ num(r.demand.requested_period_views, "demand.requested_period_views") }} |
| {{ t("unique") }} | {{ num(r.demand.unique_devices, "demand.unique_devices") }} |
| {{ t("per_device") }} | {{ num(r.demand.views_per_unique_device, "demand.views_per_unique_device") }} |

{% if chart %}![{{ t("chart_alt") }}]({{ chart }})
{% else %}_{{ t("no_chart") }}_
{% endif %}
## {{ t("s4") }}

| {{ t("kpi") }} | {{ t("value") }} |
|---|---:|
| {{ t("g_yoy") }} | {{ rate(r.growth.yoy, "growth.yoy") }} |
| {{ t("g_cagr") }} | {{ rate(r.growth.three_year_cagr, "growth.three_year_cagr") }} |
| {{ t("g_3m") }} | {{ rate(r.growth.last_three_month_growth, "growth.last_three_month_growth") }} |
| {{ t("g_prev3m") }} | {{ rate(r.growth.previous_three_month_growth, "growth.previous_three_month_growth") }} |
| {{ t("g_accel") }} | {% if r.growth.acceleration is not none %}{{ points(r.growth.acceleration) }} {{ t("pp") }} ({{ t("momentum." ~ r.growth.momentum) }}){% else %}{{ t("na") }}{% endif %} |
| {{ t("g_pop") }} | {{ rate(r.growth.period_over_period, "growth.period_over_period") }} |

{{ t("growth_note") }}

## {{ t("s5") }}

| {{ t("kpi") }} | {{ t("value") }} |
|---|---:|
| {{ t("peak") }} | {{ month(r.seasonality.peak_month) or missing("seasonality.peak_month") }} |
| {{ t("trough") }} | {{ month(r.seasonality.trough_month) or missing("seasonality.peak_month") }} |
| {{ t("peak_avg") }} | {{ dec(r.seasonality.peak_to_average) }} |
| {{ t("trough_avg") }} | {{ dec(r.seasonality.trough_to_average) }} |
| {{ t("volatility") }} | {{ dec(r.seasonality.volatility) }} |

{{ basis }}

## {{ t("s6") }}

{% if r.localization.topic_share is not none %}{{ t("col_share") }}: {{ rate(r.localization.topic_share, None, signed=False) }}{% else %}{{ missing("localization.topic_share") }}{% endif %}

## {{ t("s7") }}

| {{ t("metric") }} | {{ t("value") }} |
|---|---|
| {{ t("penetration") }} | {{ pen(r.localization.topic_penetration) }} |
| {{ t("affinity") }} | {{ dec(r.localization.topic_affinity) if r.localization.topic_affinity is not none else missing("localization.topic_affinity") }} |
| {{ t("countries") }} | {{ missing("localization.country_distribution") }} |

{{ t("not_country", project=r.metadata.project) }}

## {{ t("s8") }}

{% if not eco.computed -%}
{{ t("eco_not_computed") }}
{% else -%}
{{ t("eco_intro") }}{% if eco.edition_yoy is not none %} {{ t("eco_edition", pct=rate(eco.edition_yoy, None)) }}{% endif %}

{% if eco_chart %}![{{ t("eco_alt") }}]({{ eco_chart }})

{% endif -%}
| {{ t("col_topic") }} | {{ t("col_relationship") }} | {{ t("annual") }} | {{ t("col_relsize") }} | {{ t("yoy") }} | {{ t("col_adj_yoy") }} | {{ t("col_signal") }} |
|---|---|---:|---:|---:|---:|---|
| **{{ r.topic.article_title }}** | — | {{ num(r.demand.annual_views, "demand.annual_views") }} | 1× | {{ rate(r.growth.yoy, "growth.yoy") }} | — | — |
{% for x in eco.related_topics -%}
| {{ x.title }} | {{ t("rel." ~ x.relationship) }} | {{ num(x.annual_views, None) }} | {{ times(x.relative_size) }} | {{ rate(x.yoy_growth, None) }} | {{ rate(x.share_adjusted_yoy, None) }} | {{ t("signal." ~ x.signal) if x.signal else t("na") }} |
{% endfor %}
{{ t("eco_signals") }}
{% for s in ("larger_category", "emerging_category", "declining_category", "adjacent_opportunity", "adjacent_interest", "too_small") -%}
- **{{ t("signal." ~ s) }}**: {{ t("sdesc." ~ s) }}
{% endfor %}
### {{ t("conc_title") }}

{% set c = eco.concentration -%}
{{ t("conc_intro", n=c.articles) }}

| {{ t("conc_top", k=1) }} | {{ t("conc_top", k=5) }} | {{ t("conc_top", k=10) }} | {{ t("conc_top", k=20) }} |
|---:|---:|---:|---:|
| {{ share(c.top_1, 1) }} | {{ share(c.top_5, 5) }} | {{ share(c.top_10, 10) }} | {{ share(c.top_20, 20) }} |

{% if c.largest %}{{ t("conc_largest", title=c.largest, pct=share(c.top_1, 1)) }}

{% endif %}{{ t("conc_meaning") }}
{% if eco_notes %}
{% for n in eco_notes -%}
> {{ n }}
{% endfor %}{% endif %}{% endif %}

## {{ t("s9") }}

{{ t("an_intro") }} {{ t("an_rule", z=dec(an_info.z_threshold, 1), min_change=rate(an_info.min_change, None, signed=False)) }}
{% if an_info and not an_info.seasonal_adjustment %}
{{ t("an_no_season") }}
{% endif %}
{% if r.anomalies %}
| {{ t("an_date") }} | {{ t("an_actual") }} | {{ t("an_expected") }} | {{ t("an_change") }} | {{ t("an_z") }} | {{ t("an_severity") }} |
|---|---:|---:|---:|---:|---|
{% for a in r.anomalies -%}
| {{ a.date }} | {{ num(a.actual, None) }} | {{ num(a.expected, None) }} | {{ rate(a.change_vs_baseline, None) }} | {{ dec(a.robust_z, 1) }} | {{ t("severity." ~ a.severity) }}{% if a.provisional %}, {{ t("an_provisional") }}{% endif %} |
{% endfor %}
{% for a in r.anomalies -%}
- {{ t("an_line", month=a.date, pct=rate(a.change_vs_baseline | abs, None, signed=False), direction=t("an_above") if a.direction == "spike" else t("an_below")) }}
{% endfor %}
{% if an_info.yoy_excluding_anomalies is not none %}
{{ t("an_yoy_excl", pct=rate(an_info.yoy_excluding_anomalies, None), yoy=rate(r.growth.yoy, "growth.yoy")) }}
{% endif %}{% else %}
{{ t("an_none", n=an_info.months_checked) }}
{% endif %}

## {{ t("s10") }}

| | |
|---|---|
| {{ t("source") }} | {{ t("source_value", api=r.metadata.api, access=r.metadata.access, agent=r.metadata.agent) }} |
| {{ t("retrieved") }} | {{ r.metadata.data_retrieved_at }} |
| {{ t("generated") }} | {{ t("generated_value", at=r.metadata.generated_at, version=r.metadata.software_version) }} |
| {{ t("coverage") }} | {{ rate(r.quality.coverage, None, signed=False) }} |
| {{ t("missing_data") }} | {{ missing_months | join("; ") if missing_months else t("none") }} |
| {{ t("resolution_conf") }} | {{ dec(r.quality.topic_resolution_confidence) }} |
| {{ t("unique_avail") }} | {{ t("yes") if r.quality.unique_devices_available else t("no") }} |
| {{ t("country_avail") }} | {{ t("yes") if r.quality.country_data_available else t("no") }} |
| {{ t("denominator_avail") }} | {{ t("yes") if r.quality.project_denominator_available else t("no") }} |
| {{ t("api_errors") }} | {{ r.quality.api_errors | join("; ") if r.quality.api_errors else t("none") }} |
| {{ t("quality_level") }} | **{{ t("level." ~ r.quality.quality_level) }}**: {{ quality_reasons | join("; ") }} |

{{ t("not_computed") }}

| {{ t("metric") }} | {{ t("status") }} | {{ t("reason") }} |
|---|---|---|
{% for m in r.quality.missing_metrics -%}
| {{ m.metric }} | {{ t("status." ~ m.status) }} | {{ reason(m) }} |
{% endfor %}
{{ t("raw") }} {% for s in r.sources %}`{{ s.raw_path }}`{% if not loop.last %}, {% endif %}{% endfor %}

## {{ t("s11") }}

### {{ t("supports") }}

{% for o in observations -%}
- {{ o }}
{% endfor -%}
- {{ t("supports_tail", project=r.metadata.project) }}

### {{ t("not_establish") }}

- {{ t("ne1") }}
- {{ t("ne2") }}
- {{ t("ne3") }}
- {{ t("ne4", project=r.metadata.project) }}
- {{ t("ne5") }}

### {{ t("validate") }}

- {{ t("q1") }}
- {{ t("q2") }}
- {{ t("q3") }}
- {{ t("q4") }}
- {{ t("q5") }}
"""


def _quality_reasons(result: AnalysisResult, tr: Translator) -> list[str]:
    """The documented quality rules, restated in the report language."""
    q, m = result.quality, result.metadata
    months = next((p.months for p in result.periods if p.label == "requested period"), None)
    reasons = []
    if q.coverage is not None and q.coverage < 0.98:
        reasons.append(tr("qr.coverage", pct=tr.percent(q.coverage, signed=False)))
    if q.topic_resolution_confidence is not None and q.topic_resolution_confidence < 0.90:
        reasons.append(tr("qr.confidence", value=tr.decimal(q.topic_resolution_confidence)))
    if months is not None and months < 24:
        reasons.append(tr("qr.short", months=months))
    if q.api_errors:
        reasons.append(tr("qr.api", n=len(q.api_errors)))
    return reasons or [tr("qr.ok")]


def _notes(result: AnalysisResult, tr: Translator) -> list[str]:
    res = result.topic.resolution
    notes = []
    if res.method == "redirect":
        notes.append(tr("note.redirect", query=res.query, title=res.canonical_topic))
    if res.method == "no_wikidata":
        notes.append(tr("note.no_wikidata", title=res.canonical_topic))
    elif res.missing_languages:
        notes.append(tr("note.missing", langs=", ".join(res.missing_languages), qid=res.wikidata_id))
    return notes


def _spans(result: AnalysisResult) -> dict[str, str]:
    by_label = {p.label: f"{p.start}..{p.end}" for p in result.periods}
    return {"last_12m": by_label["last 12 months"], "previous_12m": by_label["previous 12 months"],
            "twelve_months_3y_earlier": by_label["12 months ending 3 years earlier"]}


def _eco_notes(result: AnalysisResult, tr: Translator) -> list[str]:
    """Ecosystem notes rebuilt from structured fields, so they exist in every report language."""
    eco = result.ecosystem
    notes = [tr("eco_note_skipped", n=n, relationship=tr(f"rel.{rel}")) for rel, n in eco.skipped_without_article.items()]
    if eco.capped_from:
        notes.append(tr("eco_note_capped", n=eco.capped_from, cap=len(eco.related_topics)))
    if not eco.has_wikidata:
        notes.append(tr("eco_note_no_qid"))
    if any(x.relationship == "similar_content" for x in eco.related_topics):
        notes.append(tr("eco_note_similar"))
    return notes


def render(result: AnalysisResult, chart_path: str | None = None, lang: str = "en",
           eco_chart: str | None = None) -> str:
    tr = Translator(lang)
    reasons = {m.metric: m for m in result.quality.missing_metrics}

    def reason(m) -> str:
        return reason_text(m, tr)

    def missing(metric: str) -> str:
        m = reasons.get(metric)
        return f"{tr('na')} ({tr('status.' + m.status)}: {reason(m)})" if m else tr("na")

    def num(value, metric: str) -> str:
        if value is None:
            return missing(metric) if metric else tr("na")
        return tr.number(value, 0 if abs(value) >= 100 else 1)

    def rate(value, metric: str | None, signed: bool = True) -> str:
        if value is None:
            return missing(metric) if metric else tr("na")
        return tr.percent(value, signed)

    def dec(value, decimals: int = 2) -> str:
        return tr.decimal(value, decimals) if value is not None else tr("na")

    def pen(value) -> str:
        if value is None:
            return missing("localization.topic_penetration")
        return tr("per_million_value", value=tr.decimal(value * 1_000_000, 1))

    def times(value) -> str:
        return f"{tr.decimal(value, 2)}×" if value is not None else tr("na")

    def share(value, k: int) -> str:
        return tr.percent(value, signed=False) if value is not None else tr("conc_short", k=k)

    def points(value: float) -> str:
        text = f"{value * 100:+.1f}"
        return text.replace(".", ",").replace("-", "−") if tr.lang == "uk" else text

    s = result.seasonality
    if s.basis and s.observations_per_month:
        basis = tr("basis" if s.observations_per_month > 1 else "basis_single",
                   start=result.metadata.period_start, end=result.metadata.period_end, n=s.observations_per_month)
    else:
        basis = ""

    def signal_missing(metric: str) -> str:
        gap = reasons.get(metric)
        return tr("sig_missing", reason=reason(gap)) if gap else missing(metric)

    q_reasons = _quality_reasons(result, tr)
    kpi_rows = breakdown.analysis_rows(result, tr, signal_missing, q_reasons)
    rec = result.recommendation or recommend.of_analysis(result)
    rec_lines = recommend.sentences(rec, tr)

    env = Environment(undefined=StrictUndefined, autoescape=False)
    def month_mid(name):
        # Inside a sentence Ukrainian month names are lowercase ("пік — січень"); English stay capitalised.
        text = tr.month(name)
        return text.lower() if text and tr.lang == "uk" else text

    env.globals.update(t=tr, missing=missing, num=num, rate=rate, dec=dec, points=points, reason=reason, pen=pen,
                       times=times, share=share,
                       month=tr.month, month_mid=month_mid)
    return env.from_string(TEMPLATE).render(
        r=result, chart=chart_path, basis=basis, kpi_rows=kpi_rows,
        rec_head=rec_lines[0], rec_points=rec_lines[1:-1], rec_basis=rec_lines[-1], rec_rule=recommend.rule_text(rec, tr),
        observations=observations_from_spans(result.demand, result.growth, result.seasonality, _spans(result), tr,
                                             result.anomalies, result.anomaly_analysis),
        an_info=result.anomaly_analysis or AnomalyAnalysis(),
        eco=result.ecosystem, eco_chart=eco_chart, eco_notes=_eco_notes(result, tr) if result.ecosystem.computed else [],
        quality_reasons=q_reasons, notes=_notes(result, tr),
        missing_months=[tr("missing_month", month=line[:7]) for line in result.quality.missing_data])
