"""Markdown report: Recommendation, Graph, Key Observations, KPI breakdown.

The same four sections are used for every analysis (and cluster adds its chart and
related-topic table under Graph / KPI). Repeated demand, quality and implication
blocks are omitted; the recommendation already states the limits.
All wording comes from `i18n.CATALOG`.
"""

from __future__ import annotations

from jinja2 import Environment, StrictUndefined

from wiki_market_intel.analytics import recommend
from wiki_market_intel.reporting import breakdown
from wiki_market_intel.analytics.summary import observations_from_spans
from wiki_market_intel.i18n import Translator, reason_text
from wiki_market_intel.models.analysis import AnalysisResult

TEMPLATE = """\
# {{ t("title") }}

_{{ t("topic") }}: {{ r.topic.canonical_name or r.metadata.topic }} · {{ t("edition") }}: {{ r.metadata.project }} · {{ t("period") }}: {{ t("period_value", start=r.metadata.period_start, end=r.metadata.period_end) }}_
{% for n in notes %}
> {{ n }}
{% endfor %}
## {{ t("rec_title") }}

{% if rec_head -%}
**{{ rec_head }}**

{% for line in rec_points -%}
- {{ line }}
{% endfor %}
{{ rec_basis }}

_{{ rec_rule }}_
{%- endif %}

## {{ t("graph_title") }}

{% if chart %}![{{ t("chart_alt") }}]({{ chart }})
{% else %}_{{ t("no_chart") }}_
{% endif %}
{% if eco_chart %}![{{ t("eco_alt") }}]({{ eco_chart }})
{% endif %}
## {{ t("observations") }}

{% for o in observations -%}
- {{ o }}
{% else -%}
- {{ t("no_observations") }}
{% endfor %}
## {{ t("kpi_title") }}

| {{ t("kpi_col_kpi") }} | {{ t("kpi_col_value") }} | {{ t("kpi_col_reading") }} |
|---|---|---|
{% for kpi, value, reading in kpi_rows -%}
| {{ kpi }} | {{ value }} | {{ reading }} |
{% endfor %}
{{ t("sig_intro") }}
{% if eco.computed %}
{{ t("eco_intro") }}{% if eco.edition_yoy is not none %} {{ t("eco_edition", pct=rate(eco.edition_yoy, None)) }}{% endif %}

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
        r=result, chart=chart_path, kpi_rows=kpi_rows,
        rec_head=rec_lines[0], rec_points=rec_lines[1:-1], rec_basis=rec_lines[-1], rec_rule=recommend.rule_text(rec, tr),
        observations=observations_from_spans(result.demand, result.growth, result.seasonality, _spans(result), tr,
                                             result.anomalies, result.anomaly_analysis),
        eco=result.ecosystem, eco_chart=eco_chart, eco_notes=_eco_notes(result, tr) if result.ecosystem.computed else [],
        notes=_notes(result, tr))
